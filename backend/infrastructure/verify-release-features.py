"""Verify feature rollout and boundary ownership without cloud mutations."""

import unittest
from copy import deepcopy

from deployment_profile import DEVELOPER
from portable_hosting import prepare as hosting
from release_features import prepare
from release_observation import digest
from release_plan import prepare as release

CLIENT = {
    **DEVELOPER,
    "account": "123456789012",
    "region": "eu-west-1",
    "resource_prefix": "client-prod",
    "secret_prefix": "client/production",
    "github_repository": "client-example/portal",
}


def fixture(profile):
    account, region, prefix = (profile[key] for key in ("account", "region", "resource_prefix"))
    secret = f"arn:aws:secretsmanager:{region}:{account}:secret:{profile['secret_prefix']}"
    values = {
        "database_secret": secret + "/database/app-aBc123",
        "auth_secret": secret + "/auth-aBc123",
        "db_host": f"{prefix}-db.abcdefghijk.{region}.rds.amazonaws.com",
        "pool": region + "_Example123",
        "client": "example123",
        "subnets": ["subnet-" + "1" * 17, "subnet-" + "2" * 17],
        "security_groups": ["sg-" + "3" * 17],
        "environment": "staging",
        "stage": "live",
        "image": f"{account}.dkr.ecr.{region}.amazonaws.com/{prefix}-api@sha256:" + "a" * 64,
    }
    template = hosting(
        profile,
        values,
        frontend_prefix="releases/" + "a" * 40 + "/" + "b" * 64,
        edge_arn=f"arn:aws:wafv2:us-east-1:{account}:global/webacl/{prefix}-login-cloudfront/"
        + "c" * 36,
    )
    values["features"] = {"media": True, "invitations": True, "email_changes": True}
    return template, values


class FeaturePlanTests(unittest.TestCase):
    def test_two_targets_preserve_every_unrelated_resource_and_owned_boundary(self):
        for profile in (DEVELOPER, CLIENT):
            original, values = fixture(profile)
            before = deepcopy(original)
            result = prepare(original, values, profile=profile)
            candidate = result["candidate_template"]
            self.assertEqual(original, before)
            self.assertIsNone(result["boundary_candidate_template"])
            self.assertEqual(result["base_template_sha256"], digest(before))
            self.assertEqual(set(candidate["Resources"]), set(before["Resources"]))
            for name, resource in before["Resources"].items():
                if name not in {"ApiRole", "ApiFunction", "RuntimeBoundary"}:
                    self.assertEqual(candidate["Resources"][name], resource)
            props = candidate["Resources"]["ApiFunction"]["Properties"]
            self.assertEqual(props["Environment"]["Variables"]["FITFINITY_MEDIA_ENABLED"], "true")
            self.assertEqual(
                props["VpcConfig"], before["Resources"]["ApiFunction"]["Properties"]["VpcConfig"]
            )
            self.assertEqual(
                candidate["Resources"]["ApiRole"]["Properties"]["Policies"][0]["PolicyDocument"],
                candidate["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"],
            )

    def test_external_boundary_remains_in_its_observed_owner_with_exact_rollback(self):
        original, values = fixture(CLIENT)
        boundary = original["Resources"].pop("RuntimeBoundary")
        external = {
            "Description": "existing owner",
            "Resources": {
                "ExistingBoundary": boundary,
                "OtherRole": {"Type": "AWS::IAM::Role", "Properties": {"RoleName": "untouched"}},
            },
        }
        original["Resources"]["ApiRole"]["Properties"]["PermissionsBoundary"] = (
            "arn:aws:iam::123456789012:policy/client-prod-hosting-api-boundary"
        )
        result = prepare(
            original,
            values,
            profile=CLIENT,
            boundary_template=external,
            boundary_template_sha256=digest(external),
        )
        self.assertEqual(result["rollback_template"], original)
        self.assertEqual(result["boundary_rollback_template"], external)
        self.assertEqual(set(result["candidate_template"]["Resources"]), set(original["Resources"]))
        self.assertEqual(
            result["boundary_candidate_template"]["Resources"]["OtherRole"],
            external["Resources"]["OtherRole"],
        )
        self.assertNotEqual(
            result["boundary_candidate_template"]["Resources"]["ExistingBoundary"], boundary
        )
        with self.assertRaises(RuntimeError):
            prepare(original, values, profile=CLIENT)
        with self.assertRaises(RuntimeError):
            prepare(
                original,
                values,
                profile=CLIENT,
                boundary_template=external,
                boundary_template_sha256="0" * 64,
            )

    def test_prepared_external_boundary_allows_exact_feature_activation_only(self):
        for profile in (DEVELOPER, CLIENT):
            with self.subTest(profile=profile["resource_prefix"]):
                original, values = fixture(profile)
                boundary = original["Resources"].pop("RuntimeBoundary")
                original["Resources"]["ApiRole"]["Properties"]["PermissionsBoundary"] = (
                    f"arn:aws:iam::{profile['account']}:policy/"
                    + profile["resource_prefix"]
                    + "-hosting-api-boundary"
                )
                owner = {"Resources": {"ExistingBoundary": boundary}}
                first = prepare(
                    original,
                    values,
                    profile=profile,
                    boundary_template=owner,
                    boundary_template_sha256=digest(owner),
                )
                self.assertTrue(first["boundary_update_required"])
                installed = first["boundary_candidate_template"]
                second = prepare(
                    original,
                    values,
                    profile=profile,
                    boundary_template=installed,
                    boundary_template_sha256=digest(installed),
                )
                self.assertFalse(second["boundary_update_required"])
                self.assertEqual(second["candidate_template"], first["candidate_template"])
                self.assertEqual(second["boundary_candidate_template"], installed)
                self.assertNotIn("RuntimeBoundary", second["candidate_template"]["Resources"])
                self.assertEqual(
                    original["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"][
                        "FITFINITY_MEDIA_ENABLED"
                    ],
                    "false",
                )
                foreign = deepcopy(installed)
                foreign["Resources"]["ExistingBoundary"]["Properties"]["PolicyDocument"][
                    "Statement"
                ].append({"Effect": "Allow", "Action": "*", "Resource": "*"})
                with self.assertRaisesRegex(RuntimeError, "boundary permissions differ"):
                    prepare(
                        original,
                        values,
                        profile=profile,
                        boundary_template=foreign,
                        boundary_template_sha256=digest(foreign),
                    )

    def test_feature_recovery_reconstructs_exact_original_without_secret_receipts(self):
        import json

        from rollout_operator import original_metadata, restore_original

        for profile in (DEVELOPER, CLIENT):
            with self.subTest(profile=profile["resource_prefix"]):
                original, values = fixture(profile)
                props = original["Resources"]["ApiFunction"]["Properties"]
                props["ReservedConcurrentExecutions"] = 0
                props["Environment"]["Variables"]["PRIVATE_SETTING"] = "never-in-receipts"
                plan = release(
                    original,
                    observed_template_sha256=digest(original),
                    source_sha="c" * 40,
                    image_digest="sha256:" + "d" * 64,
                    frontend_sha256="e" * 64,
                    profile=profile,
                    feature_values=values,
                )
                receipt = original_metadata(original, profile=profile, feature_values=values)
                self.assertNotIn("PRIVATE_SETTING", json.dumps(receipt))
                self.assertNotIn("never-in-receipts", json.dumps(receipt))
                restored = restore_original(
                    plan["candidate_template"], receipt, profile=profile, feature_values=values
                )
                self.assertEqual(restored, original)
                self.assertNotEqual(plan["candidate_template"], original)

    def test_feature_recovery_rejects_private_or_foreign_settings(self):
        from release_features import checked_state

        for state in (
            {"PASSWORD": "secret"},
            {"FITFINITY_MEDIA_ENABLED": "maybe"},
            {"FITFINITY_AWS_REGION": "foreign"},
            {"FITFINITY_MEDIA_BUCKET": "foreign"},
            {"FITFINITY_STAFF_PORTAL_URL": "https://user:secret@example.test/"},
            {"FITFINITY_STAFF_PORTAL_URL": "https://example.test/?token=secret"},
        ):
            with self.subTest(state=state), self.assertRaises(RuntimeError):
                checked_state(state, CLIENT)

    def test_unreviewed_secrets_extra_authority_or_foreign_boundary_are_refused(self):
        original, values = fixture(CLIENT)
        for mode in ("secret", "policy", "trust", "boundary"):
            changed = deepcopy(original)
            role = changed["Resources"]["ApiRole"]["Properties"]
            if mode == "secret":
                changed["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"][
                    "FITFINITY_AUTH_SECRET_ARN"
                ] += "foreign"
            elif mode == "policy":
                role["Policies"][0]["PolicyDocument"]["Statement"].append(
                    {"Effect": "Allow", "Action": "*", "Resource": "*"}
                )
            elif mode == "trust":
                role["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] = {"AWS": "*"}
            else:
                role["PermissionsBoundary"] = "arn:aws:iam::000000000000:policy/foreign"
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                prepare(changed, values, profile=CLIENT)

    def test_enabled_media_cannot_silently_switch_bucket_and_disabling_keeps_resources(self):
        original, values = fixture(CLIENT)
        enabled = prepare(original, values, profile=CLIENT)["candidate_template"]
        wrong = deepcopy(enabled)
        wrong["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"][
            "FITFINITY_MEDIA_BUCKET"
        ] = "foreign-bucket"
        with self.assertRaisesRegex(RuntimeError, "redirected"):
            prepare(wrong, values, profile=CLIENT)
        disabled = prepare(
            enabled,
            {**values, "features": dict.fromkeys(values["features"], False)},
            profile=CLIENT,
        )
        candidate = disabled["candidate_template"]
        self.assertEqual(set(candidate["Resources"]), set(enabled["Resources"]))
        self.assertNotIn(
            "FITFINITY_MEDIA_BUCKET",
            candidate["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"],
        )
        statements = candidate["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"][
            "Statement"
        ]
        self.assertFalse(
            any(action.startswith("s3:") for row in statements for action in row["Action"])
        )

    def test_release_combines_feature_plan_without_mutating_its_observed_base(self):
        original, values = fixture(CLIENT)
        result = release(
            original,
            observed_template_sha256=digest(original),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256="e" * 64,
            profile=CLIENT,
            feature_values=values,
        )
        self.assertEqual(result["base_template_sha256"], digest(original))
        self.assertEqual(result["feature_review"]["base_template_sha256"], digest(original))
        self.assertEqual(
            result["feature_review"]["candidate_template"]["Resources"]["ApiFunction"][
                "Properties"
            ]["Code"],
            original["Resources"]["ApiFunction"]["Properties"]["Code"],
        )
        self.assertTrue(
            result["candidate_template"]["Resources"]["ApiFunction"]["Properties"]["Code"][
                "ImageUri"
            ].endswith("d" * 64)
        )

    def test_same_source_with_different_feature_configurations_gets_distinct_versions(self):
        original, values = fixture(CLIENT)
        arguments = dict(
            observed_template_sha256=digest(original),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256="e" * 64,
            profile=CLIENT,
        )
        enabled = release(original, **arguments, feature_values=values)
        disabled = release(
            original,
            **arguments,
            feature_values={**values, "features": dict.fromkeys(values["features"], False)},
        )

        def version(value):
            return value["candidate_template"]["Resources"]["ApiAlias"]["Properties"][
                "FunctionVersion"
            ]

        self.assertNotEqual(version(enabled), version(disabled))


class ChangeSetTests(unittest.TestCase):
    def setUp(self):
        self.original, _ = fixture(CLIENT)
        self.original["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 0
        self.candidate = release(
            self.original,
            observed_template_sha256=digest(self.original),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256="e" * 64,
            profile=CLIENT,
        )["candidate_template"]
        version = self.candidate["Resources"]["ApiAlias"]["Properties"]["FunctionVersion"][
            "Fn::GetAtt"
        ][0]
        self.stack = "arn:aws:cloudformation:eu-west-1:123456789012:stack/client-prod-login/abcd"
        self.change_set = {
            "Status": "CREATE_COMPLETE",
            "ExecutionStatus": "AVAILABLE",
            "StackId": self.stack,
            "Changes": [
                self.change("ApiFunction", "AWS::Lambda::Function", ["Code"]),
                self.change("ApiAlias", "AWS::Lambda::Alias", ["FunctionVersion"]),
                self.change(
                    "Distribution", "AWS::CloudFront::Distribution", ["DistributionConfig"]
                ),
                {
                    "Type": "Resource",
                    "ResourceChange": {
                        "Action": "Add",
                        "LogicalResourceId": version,
                        "ResourceType": "AWS::Lambda::Version",
                    },
                },
            ],
        }

    @staticmethod
    def change(name, kind, properties):
        return {
            "Type": "Resource",
            "ResourceChange": {
                "Action": "Modify",
                "LogicalResourceId": name,
                "ResourceType": kind,
                "Replacement": "False",
                "Scope": ["Properties"],
                "Details": [
                    {
                        "Target": {
                            "Attribute": "Properties",
                            "Name": name,
                            "RequiresRecreation": "Never",
                        }
                    }
                    for name in properties
                ],
            },
        }

    def validate(self, candidate=None, change_set=None, **kwargs):
        from release_changes import validate

        candidate = self.candidate if candidate is None else candidate
        return validate(
            self.original,
            candidate,
            self.change_set if change_set is None else change_set,
            profile=CLIENT,
            stack_arn=self.stack,
            reviewed_template_sha256=digest(candidate),
            **kwargs,
        )

    def test_complete_paused_rollout_accepts_only_exact_resource_and_property_changes(self):
        result = self.validate()
        self.assertEqual(result["stack_arn"], self.stack)
        self.assertEqual(result["mode"], "rollout")
        self.assertEqual(result["template_sha256"], digest(self.candidate))
        changed = deepcopy(self.change_set)
        changed["Changes"].reverse()
        self.assertEqual(self.validate(change_set=changed), result)

    def test_replacement_deletion_foreign_stack_incomplete_and_extra_changes_are_denied(self):
        for failure in (
            "replacement",
            "unknown-replacement",
            "deletion",
            "foreign",
            "missing",
            "duplicate",
            "page",
            "property",
            "recreate",
            "empty",
        ):
            changed = deepcopy(self.change_set)
            row = changed["Changes"][0]["ResourceChange"]
            if failure == "replacement":
                row["Replacement"] = "Conditional"
            elif failure == "unknown-replacement":
                del row["Replacement"]
            elif failure == "deletion":
                row["Action"] = "Remove"
            elif failure == "foreign":
                changed["StackId"] += "foreign"
            elif failure == "missing":
                changed["Changes"].pop()
            elif failure == "duplicate":
                changed["Changes"].append(deepcopy(changed["Changes"][0]))
            elif failure == "page":
                changed["NextToken"] = "remaining-page"
            elif failure == "property":
                row["Details"][0]["Target"]["Name"] = "Role"
            elif failure == "recreate":
                row["Details"][0]["Target"]["RequiresRecreation"] = "Conditionally"
            else:
                row["Details"] = []
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                self.validate(change_set=changed)

    def test_even_a_rehashed_template_cannot_delete_resources_or_resume_during_rollout(self):
        for failure in ("delete", "resume", "role", "attributes", "extra", "null-property"):
            changed = deepcopy(self.candidate)
            if failure == "delete":
                changed["Resources"].pop("ApiRole")
            elif failure == "resume":
                changed["Resources"]["ApiFunction"]["Properties"][
                    "ReservedConcurrentExecutions"
                ] = 2
            elif failure == "role":
                changed["Resources"]["ApiFunction"]["Properties"]["Role"] = "foreign"
            elif failure == "attributes":
                changed["Resources"]["ApiRole"]["DeletionPolicy"] = "Delete"
            elif failure == "null-property":
                changed["Resources"]["ApiFunction"]["Properties"]["VpcConfig"] = None
            else:
                changed["Resources"]["Extra"] = {"Type": "AWS::S3::Bucket"}
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                self.validate(candidate=changed)

    def test_resumption_is_a_separate_concurrency_only_change(self):
        self.original = deepcopy(self.candidate)
        resumed = deepcopy(self.original)
        resumed["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 2
        change_set = {
            **self.change_set,
            "Changes": [
                self.change(
                    "ApiFunction", "AWS::Lambda::Function", ["ReservedConcurrentExecutions"]
                )
            ],
        }
        self.assertEqual(self.validate(resumed, change_set, mode="resume")["mode"], "resume")
        for value in (True, -1, 0, "2"):
            wrong = deepcopy(resumed)
            wrong["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                self.validate(wrong, change_set, mode="resume")
        resumed["Resources"]["ApiFunction"]["Properties"]["Code"]["ImageUri"] += "changed"
        with self.assertRaises(RuntimeError):
            self.validate(resumed, change_set, mode="resume")

    def test_external_boundary_change_keeps_other_owner_resources_intact(self):
        boundary = self.original["Resources"]["RuntimeBoundary"]
        self.original = {
            "Resources": {"OriginalBoundary": boundary, "Untouched": {"Type": "AWS::IAM::Role"}}
        }
        candidate = deepcopy(self.original)
        candidate["Resources"]["OriginalBoundary"]["Properties"]["PolicyDocument"] = {
            "Version": "2012-10-17",
            "Statement": [],
        }
        change_set = {
            **self.change_set,
            "Changes": [
                self.change("OriginalBoundary", "AWS::IAM::ManagedPolicy", ["PolicyDocument"])
            ],
        }
        self.assertEqual(
            self.validate(
                candidate, change_set, mode="boundary", boundary_resource="OriginalBoundary"
            )["mode"],
            "boundary",
        )
        candidate["Resources"]["Untouched"]["Properties"] = {"RoleName": "changed"}
        with self.assertRaises(RuntimeError):
            self.validate(
                candidate, change_set, mode="boundary", boundary_resource="OriginalBoundary"
            )
