"""Verify portable provisioning output without creating resources or changing existing stacks."""

import copy
import json
import unittest
from pathlib import Path

from deployment_profile import DEVELOPER
from portable_foundation import prepare
from portable_hosting import edge
from portable_hosting import prepare as hosting
from portable_services import identity, image_access, storage

CLIENT = {
    **DEVELOPER,
    "account": "123456789012",
    "region": "eu-west-1",
    "github_repository": "client-example/portal",
    "github_environment": "production",
    "resource_prefix": "client-prod",
    "secret_prefix": "client/production",
    "runtime_alias": "live",
}
OPTIONS = {
    "vpc_cidr": "10.95.0.0/16",
    "engine_version": "17.11",
    "database_class": "db.t4g.micro",
    "storage_gib": 20,
    "max_storage_gib": 30,
    "multi_az": False,
    "backup_days": 14,
    "egress": "none",
}


class PortableFoundationTests(unittest.TestCase):
    def test_two_targets_never_inherit_developer_account_region_or_az(self):
        for profile in (DEVELOPER, CLIENT):
            result = prepare(profile, OPTIONS)
            self.assertEqual(result["mode"], "new-environment-only")
            self.assertEqual(result["decision"], "HOLD")
            database = result["template"]["Resources"]["Database"]["Properties"]
            self.assertEqual(database["DBInstanceIdentifier"], profile["resource_prefix"] + "-db")
            self.assertFalse(database["PubliclyAccessible"])
            self.assertEqual(database["BackupRetentionPeriod"], 14)
        text = json.dumps(prepare(CLIENT, OPTIONS))
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test", "Singapore"):
            self.assertNotIn(forbidden, text)

    def test_private_tls_and_retained_database_survive_template_generation(self):
        result = prepare(CLIENT, OPTIONS)["template"]["Resources"]
        database = result["Database"]
        self.assertEqual(database["DeletionPolicy"], "Retain")
        self.assertEqual(database["UpdateReplacePolicy"], "Retain")
        self.assertTrue(database["Properties"]["DeletionProtection"])
        self.assertTrue(database["Properties"]["ManageMasterUserPassword"])
        self.assertNotIn("MasterUserPassword", database["Properties"])
        self.assertEqual(
            result["DatabaseParameters"]["Properties"]["Parameters"]["rds.force_ssl"], "1"
        )
        ingress = [
            v["Properties"]
            for v in result.values()
            if v["Type"] == "AWS::EC2::SecurityGroupIngress"
        ]
        self.assertEqual(len(ingress), 2)
        self.assertTrue(
            all(
                v["FromPort"] == 5432 and "SourceSecurityGroupId" in v and "CidrIp" not in v
                for v in ingress
            )
        )
        self.assertFalse(any(v["Type"] == "AWS::EC2::NatGateway" for v in result.values()))

    def test_paid_egress_is_explicit_and_never_routes_database_subnets(self):
        resources = prepare(CLIENT, {**OPTIONS, "egress": "nat-per-az", "multi_az": True})[
            "template"
        ]["Resources"]
        self.assertEqual(sum(v["Type"] == "AWS::EC2::NatGateway" for v in resources.values()), 2)
        self.assertNotIn("AvailabilityZone", resources["Database"]["Properties"])
        for resource in resources.values():
            if resource["Type"] == "AWS::EC2::Route":
                self.assertNotIn("DatabaseSubnet", json.dumps(resource))
            if resource["Type"] == "AWS::EC2::Subnet":
                self.assertFalse(resource["Properties"]["MapPublicIpOnLaunch"])

    def test_unsafe_or_unreviewed_foundation_options_are_refused(self):
        for key, value in [
            ("vpc_cidr", "0.0.0.0/16"),
            ("vpc_cidr", "127.0.0.0/16"),
            ("backup_days", 0),
            ("backup_days", True),
            ("multi_az", "false"),
            ("egress", "automatic"),
            ("engine_version", "18.1"),
            ("storage_gib", 100),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, RuntimeError)):
                prepare(CLIENT, {**OPTIONS, key: value})
        with self.assertRaises(RuntimeError):
            prepare(CLIENT, {**OPTIONS, "admin_password": "not-accepted"})

    def test_cognito_policy_is_preserved_and_only_target_fields_change(self):
        baseline = json.loads(Path(__file__).with_name("cognito.json").read_text())
        original = copy.deepcopy(baseline["Resources"]["StaffPool"]["Properties"])
        actual = identity(CLIENT, session_hours=8, staff_portal_url="https://staff.client.example")
        changed = actual["Resources"]["StaffPool"]["Properties"]
        self.assertEqual(
            {k: v for k, v in changed.items() if k != "UserPoolName"},
            {k: v for k, v in original.items() if k != "UserPoolName"},
        )
        self.assertEqual(changed["MfaConfiguration"], "ON")
        self.assertEqual(actual["Resources"]["StaffPool"]["DeletionPolicy"], "Retain")
        self.assertNotIn("ap-southeast-1", json.dumps(actual))
        with self.assertRaises(RuntimeError):
            identity(CLIENT, session_hours=8, staff_portal_url="https://user:secret@evil.example")

    def test_media_remains_private_tls_only_and_delete_does_not_create_hidden_versions(self):
        resources = storage(CLIENT, browser_origin="https://staff.client.example")["Resources"]
        media = resources["Media"]
        self.assertEqual(media["DeletionPolicy"], "Retain")
        self.assertTrue(all(media["Properties"]["PublicAccessBlockConfiguration"].values()))
        self.assertNotIn("VersioningConfiguration", media["Properties"])
        self.assertNotIn("LifecycleConfiguration", media["Properties"])
        self.assertEqual(
            media["Properties"]["CorsConfiguration"]["CorsRules"][0]["AllowedOrigins"],
            ["https://staff.client.example"],
        )
        deny = resources["MediaPolicy"]["Properties"]["PolicyDocument"]["Statement"][0]
        self.assertEqual(deny["Effect"], "Deny")
        self.assertEqual(deny["Condition"], {"Bool": {"aws:SecureTransport": "false"}})
        self.assertEqual(resources["Images"]["Properties"]["ImageTagMutability"], "IMMUTABLE")
        with self.assertRaises(RuntimeError):
            storage(CLIENT, browser_origin="https://*.example")

    def test_image_role_cannot_deploy_or_read_secrets_and_trust_is_client_only(self):
        resources = image_access(CLIENT)["Resources"]
        role = resources["ImageRole"]["Properties"]
        self.assertEqual(role["RoleName"], "client-prod-github-image")
        self.assertEqual(role["PermissionsBoundary"], {"Ref": "ImageBoundary"})
        statements = role["Policies"][0]["PolicyDocument"]["Statement"]
        self.assertTrue(
            all(
                action.startswith("ecr:") and "*" not in action
                for row in statements
                for action in row["Action"]
            )
        )
        self.assertEqual(
            statements[1]["Resource"],
            "arn:aws:ecr:eu-west-1:123456789012:repository/client-prod-api",
        )
        trust = role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"]
        self.assertEqual(
            trust["token.actions.githubusercontent.com:sub"],
            "repo:client-example/portal:environment:production",
        )
        self.assertNotIn("418638389566", json.dumps(resources))


class PortableHostingTests(unittest.TestCase):
    def values(self, profile=CLIENT):
        account, region, prefix = (profile[k] for k in ("account", "region", "resource_prefix"))
        secret = f"arn:aws:secretsmanager:{region}:{account}:secret:{profile['secret_prefix']}"
        return {
            "database_secret": secret + "/database/app-aBc123",
            "auth_secret": secret + "/auth-xYz456",
            "db_host": f"{prefix}-db.abcdefghijk.{region}.rds.amazonaws.com",
            "pool": region + "_Example123",
            "client": "a1234567890",
            "subnets": ["subnet-" + "1" * 17, "subnet-" + "2" * 17],
            "security_groups": ["sg-" + "3" * 17],
            "image": f"{account}.dkr.ecr.{region}.amazonaws.com/{prefix}-api@sha256:" + "a" * 64,
            "environment": "production",
            "stage": "live",
        }

    def render(self, profile=CLIENT, values=None):
        return hosting(
            profile,
            self.values(profile) if values is None else values,
            frontend_prefix="releases/" + "a" * 40 + "/" + "b" * 64,
            edge_arn=f"arn:aws:wafv2:us-east-1:{profile['account']}:global/webacl/"
            + profile["resource_prefix"]
            + "-login-cloudfront/"
            + "a" * 36,
        )

    def test_client_hosting_has_no_developer_bindings_and_keeps_protections(self):
        result = self.render()
        text = json.dumps(result)
        for forbidden in ("418638389566", "ap-southeast-1", "fitfinity-test", "first-test"):
            self.assertNotIn(forbidden, text)
        resources = result["Resources"]
        env = resources["ApiFunction"]["Properties"]["Environment"]["Variables"]
        self.assertEqual(env["FITFINITY_AWS_REGION"], "eu-west-1")
        self.assertEqual(env["FITFINITY_AUTH_COOKIE_SECURE"], "true")
        self.assertEqual(env["FITFINITY_STAFF_INVITATIONS_ENABLED"], "false")
        self.assertEqual(resources["ApiAlias"]["Properties"]["Name"], "live")
        self.assertEqual(resources["ApiStage"]["Properties"]["StageName"], "live")
        self.assertFalse(resources["ApiStage"]["Properties"]["CacheClusterEnabled"])
        access = resources["RuntimeBoundary"]["Properties"]["PolicyDocument"]["Statement"]
        self.assertEqual(
            access[0]["Resource"], [self.values()["database_secret"], self.values()["auth_secret"]]
        )
        self.assertEqual(access[-1]["Effect"], "Deny")
        self.assertIn("lambda:SourceFunctionArn", access[-1]["Condition"]["ArnEquals"])
        self.assertTrue(
            all(
                resources["FrontendBucket"]["Properties"]["PublicAccessBlockConfiguration"].values()
            )
        )

    def test_enabled_features_match_target_resources_and_minimal_provider_permissions(self):
        for profile in (CLIENT, DEVELOPER):
            values = self.values(profile)
            values["features"] = {"media": True, "invitations": True, "email_changes": True}
            result = self.render(profile, values)
            resources = result["Resources"]
            env = resources["ApiFunction"]["Properties"]["Environment"]["Variables"]
            self.assertEqual(env["FITFINITY_MEDIA_ENABLED"], "true")
            self.assertEqual(env["FITFINITY_STAFF_INVITATIONS_ENABLED"], "true")
            self.assertEqual(env["FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED"], "true")
            self.assertEqual(
                env["FITFINITY_STAFF_PORTAL_URL"],
                {"Fn::Sub": "https://${Distribution.DomainName}/"},
            )
            bucket = (
                profile["resource_prefix"]
                + "-media-"
                + profile["account"]
                + "-"
                + profile["region"]
            )
            self.assertEqual(env["FITFINITY_MEDIA_BUCKET"], bucket)
            statements = resources["RuntimeBoundary"]["Properties"]["PolicyDocument"]["Statement"]
            providers = [
                item
                for item in statements
                if any(action.startswith(("s3:", "cognito-idp:")) for action in item["Action"])
            ]
            self.assertEqual(
                providers,
                [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "cognito-idp:DescribeUserPool",
                            "cognito-idp:AdminGetUser",
                            "cognito-idp:AdminCreateUser",
                        ],
                        "Resource": (
                            f"arn:aws:cognito-idp:{profile['region']}:{profile['account']}"
                            f":userpool/{values['pool']}"
                        ),
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        "Resource": [
                            f"arn:aws:s3:::{bucket}/library/*",
                            f"arn:aws:s3:::{bucket}/recordings/*",
                        ],
                    },
                ],
            )
            self.assertEqual(
                resources["ApiRole"]["Properties"]["Policies"][0]["PolicyDocument"],
                resources["RuntimeBoundary"]["Properties"]["PolicyDocument"],
            )

    def test_closed_features_have_no_provider_access_and_reject_ambiguous_flags(self):
        result = self.render()
        statements = result["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"][
            "Statement"
        ]
        self.assertFalse(
            any(
                action.startswith(("s3:", "cognito-idp:"))
                for item in statements
                for action in item["Action"]
            )
        )
        for flags in (
            {"media": True},
            {"media": "false", "invitations": False, "email_changes": False},
            {"media": False, "invitations": False, "email_changes": False, "unknown": True},
        ):
            with self.assertRaises(RuntimeError):
                self.render(values={**self.values(), "features": flags})

    def test_new_image_publishes_distinct_version_and_alias_tracks_it(self):
        first = self.render()
        values = self.values()
        values["image"] = values["image"].replace("a" * 64, "b" * 64)
        second = self.render(values=values)

        def version(template):
            return template["Resources"]["ApiAlias"]["Properties"]["FunctionVersion"]["Fn::GetAtt"][
                0
            ]

        self.assertNotEqual(version(first), version(second))
        changed_config = self.render(values={**self.values(), "client": "differentClient123"})
        self.assertNotEqual(version(first), version(changed_config))
        self.assertEqual(version(first), version(self.render()))
        for result in (first, second, changed_config):
            self.assertEqual(result["Resources"][version(result)]["Type"], "AWS::Lambda::Version")
            self.assertEqual(
                result["Outputs"]["FunctionVersion"]["Value"]["Fn::GetAtt"][0], version(result)
            )

    def test_mixed_account_region_unknown_secrets_and_duplicate_subnets_fail(self):
        for key, value in [
            ("auth_secret", self.values(DEVELOPER)["auth_secret"]),
            ("image", self.values(DEVELOPER)["image"]),
            ("pool", "ap-southeast-1_Foreign"),
            ("subnets", ["subnet-" + "1" * 17] * 2),
            ("db_host", "other-db.abcdefghijk.eu-west-1.rds.amazonaws.com"),
        ]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.render(values={**self.values(), key: value})
        with self.assertRaises(RuntimeError):
            self.render(values={**self.values(), "password": "rejected"})

    def test_templates_bind_actual_stack_account_and_service_region(self):
        templates = [
            (prepare(CLIENT, OPTIONS)["template"], "eu-west-1"),
            (identity(CLIENT, session_hours=8, staff_portal_url=""), "eu-west-1"),
            (storage(CLIENT, browser_origin="https://staff.client.example"), "eu-west-1"),
            (image_access(CLIENT), "eu-west-1"),
            (self.render(), "eu-west-1"),
            (edge(CLIENT), "us-east-1"),
        ]
        for template, region in templates:
            rules = template["Rules"]["SelectedTarget"]["Assertions"]
            self.assertEqual(
                [row["Assert"]["Fn::Equals"] for row in rules],
                [
                    [{"Ref": "AWS::AccountId"}, "123456789012"],
                    [{"Ref": "AWS::Region"}, region],
                ],
            )

    def test_edge_region_constraint_does_not_change_application_region(self):
        template = edge(CLIENT)
        acl = template["Resources"]["EdgeAcl"]["Properties"]
        self.assertEqual(acl["Scope"], "CLOUDFRONT")
        self.assertEqual(acl["Name"], "client-prod-login-cloudfront")
        self.assertFalse(acl["VisibilityConfig"]["SampledRequestsEnabled"])
        self.assertIn("us-east-1", template["Description"])
        self.assertEqual(
            self.render()["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"][
                "FITFINITY_AWS_REGION"
            ],
            "eu-west-1",
        )


class MaintenanceAccessTests(unittest.TestCase):
    def test_two_target_roles_have_exact_identity_and_no_deploy_or_secret_permissions(self):
        from portable_services import maintenance_access

        for profile in (DEVELOPER, CLIENT):
            result = maintenance_access(profile)
            resources = result["Resources"]
            self.assertEqual(set(resources), {"MaintenanceRole", "MaintenanceBoundary"})
            role = resources["MaintenanceRole"]["Properties"]
            self.assertEqual(role["RoleName"], profile["resource_prefix"] + "-github-maintenance")
            access = role["Policies"][0]["PolicyDocument"]
            self.assertEqual(
                access, resources["MaintenanceBoundary"]["Properties"]["PolicyDocument"]
            )
            rules = access["Statement"]
            actions = {
                action
                for row in rules
                for action in (
                    row["Action"] if isinstance(row["Action"], list) else [row["Action"]]
                )
            }
            self.assertEqual(
                actions,
                {
                    "sts:GetCallerIdentity",
                    "lambda:GetFunction",
                    "lambda:GetFunctionConcurrency",
                    "lambda:PutFunctionConcurrency",
                    "lambda:TagResource",
                    "rds:DescribeDBInstances",
                    "rds:CreateDBSnapshot",
                    "rds:AddTagsToResource",
                    "rds:DescribeDBSnapshots",
                    "rds:ListTagsForResource",
                },
            )
            self.assertEqual(
                rules[1]["Resource"],
                f"arn:aws:lambda:{profile['region']}:{profile['account']}:function:{profile['resource_prefix']}-staff-api",
            )
            self.assertEqual(
                rules[-1]["Resource"],
                f"arn:aws:rds:{profile['region']}:{profile['account']}:snapshot:{profile['resource_prefix']}-release-*",
            )
            trust = role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"]
            self.assertEqual(
                trust["token.actions.githubusercontent.com:sub"],
                "repo:"
                + profile["github_repository"]
                + ":environment:"
                + profile["github_environment"],
            )
            self.assertEqual(
                rules[2]["Condition"]["ForAllValues:StringEquals"]["aws:TagKeys"],
                ["FitfinityMaintenance", "FitfinitySnapshot"],
            )

    def test_client_maintenance_template_contains_no_developer_resource_bindings(self):
        from portable_services import maintenance_access

        rendered = json.dumps(maintenance_access(CLIENT))
        for old in ("418638389566", "fitfinity-test", "ap-southeast-1", "LimYouSheng"):
            self.assertNotIn(old, rendered)
