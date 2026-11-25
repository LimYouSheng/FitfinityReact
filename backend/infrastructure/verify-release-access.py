"""Check resource-bound release authority without calling IAM or changing policies."""

import json
import unittest
from copy import deepcopy

from deployment_profile import DEVELOPER, identities
from release_access import prepare, service_role_arn


class ReleaseAccessTests(unittest.TestCase):
    def fixture(self, profile):
        target = identities(profile)
        stack = {
            "StackId": (
                f"arn:aws:cloudformation:{target['region']}:{target['account']}:"
                f"stack/{target['hosting_stack']}/abcd"
            ),
            "StackName": target["hosting_stack"],
            "StackStatus": "UPDATE_COMPLETE",
            "RoleARN": service_role_arn(profile),
        }
        rows = [
            ("ApiFunction", "AWS::Lambda::Function", target["runtime_function"]),
            ("ApiRole", "AWS::IAM::Role", target["resource_prefix"] + "-hosting-api"),
            (
                "FrontendBucket",
                "AWS::S3::Bucket",
                target["hosting_stack"] + "-frontendbucket-abc123",
            ),
            ("Distribution", "AWS::CloudFront::Distribution", "E123456789"),
        ]
        return stack, {
            "StackResourceSummaries": [
                {"LogicalResourceId": name, "ResourceType": kind, "PhysicalResourceId": physical}
                for name, kind, physical in rows
            ]
        }

    def test_two_targets_retain_identities_and_no_bootstrap_or_secret_authority(self):
        profiles = [
            DEVELOPER,
            {
                **DEVELOPER,
                "account": "123456789012",
                "region": "eu-west-1",
                "resource_prefix": "client-prod",
                "github_repository": "client-example/portal",
            },
        ]
        for profile in profiles:
            stack, inventory = self.fixture(profile)
            result = prepare(profile, stack, inventory)
            self.assertEqual(result["decision"], "HOLD")
            self.assertEqual(result["service_role"], stack["RoleARN"])
            for kind in ("operator", "service"):
                self.assertEqual(result[kind + "_policy"], result[kind + "_boundary"])
                for row in result[kind + "_policy"]["Statement"]:
                    for action in row["Action"]:
                        self.assertNotIn("*", action)
                        self.assertFalse(
                            any(
                                part in action
                                for part in (
                                    "Delete",
                                    "CreateStack",
                                    "CreateFunction",
                                    "CreateDistribution",
                                    "GetSecretValue",
                                    "InvokeFunction",
                                )
                            )
                        )
            database = [
                row
                for row in result["operator_policy"]["Statement"]
                if "rds:DescribeDBInstances" in row["Action"]
            ]
            self.assertEqual(
                database,
                [
                    {
                        "Effect": "Allow",
                        "Action": ["rds:DescribeDBInstances"],
                        "Resource": (
                            f"arn:aws:rds:{profile['region']}:{profile['account']}:"
                            f"db:{profile['resource_prefix']}-db"
                        ),
                    }
                ],
            )
            if profile is not DEVELOPER:
                encoded = json.dumps(result)
                for forbidden in (
                    "418638389566",
                    "ap-southeast-1",
                    "fitfinity-test",
                    "LimYouSheng",
                ):
                    self.assertNotIn(forbidden, encoded)

    def test_s3_absence_read_and_conditional_encrypted_upload_are_bound_to_owned_bucket(self):
        stack, inventory = self.fixture(DEVELOPER)
        result = prepare(DEVELOPER, stack, inventory)
        rows = result["operator_policy"]["Statement"]
        for action, resource in (
            ("iam:GetRole", "role/fitfinity-test-hosting-api"),
            ("iam:ListEntitiesForPolicy", "policy/fitfinity-test-hosting-api-boundary"),
        ):
            grant = next(row for row in rows if action in row["Action"])
            self.assertEqual(grant["Resource"], "arn:aws:iam::418638389566:" + resource)
        for action in ("CreateChangeSet", "DescribeChangeSet", "ExecuteChangeSet"):
            grant = next(row for row in rows if "cloudformation:" + action in row["Action"])
            self.assertEqual(grant["Resource"], stack["StackId"])
            self.assertEqual(
                grant["Condition"]["StringLike"]["cloudformation:ChangeSetName"],
                [
                    "release-*",
                    "arn:aws:cloudformation:ap-southeast-1:418638389566:changeSet/release-*/*",
                ],
            )
        listing = next(row for row in rows if row["Action"] == ["s3:ListBucket"])
        self.assertEqual(
            listing["Resource"], "arn:aws:s3:::fitfinity-test-login-frontendbucket-abc123"
        )
        upload = next(row for row in rows if row["Action"] == ["s3:PutObject"])
        self.assertEqual(upload["Resource"], listing["Resource"] + "/releases/*")
        self.assertEqual(
            upload["Condition"],
            {
                "StringEquals": {
                    "s3:x-amz-server-side-encryption": "AES256",
                    "s3:if-none-match": "*",
                }
            },
        )
        delegation = next(row for row in rows if row["Action"] == ["iam:PassRole"])
        self.assertEqual(delegation["Resource"], result["service_role"])
        self.assertEqual(
            delegation["Condition"],
            {"StringEquals": {"iam:PassedToService": "cloudformation.amazonaws.com"}},
        )

    def test_service_writes_are_scoped_to_the_owned_function_alias_and_distribution(self):
        stack, inventory = self.fixture(DEVELOPER)
        result = prepare(DEVELOPER, stack, inventory)
        rows = result["service_policy"]["Statement"]
        handler_reads = {
            "lambda:GetFunctionCodeSigningConfig",
            "lambda:GetFunctionRecursionConfig",
            "lambda:GetFunctionScalingConfig",
            "lambda:GetProvisionedConcurrencyConfig",
            "lambda:GetRuntimeManagementConfig",
        }
        function = "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api"
        for action in handler_reads:
            self.assertEqual(
                [row["Resource"] for row in rows if action in row["Action"]],
                [[function, function + ":*"]],
            )
        actions = {action for row in rows for action in row["Action"]}
        self.assertTrue(
            actions.isdisjoint(
                {
                    "lambda:PutFunctionCodeSigningConfig",
                    "lambda:PutFunctionRecursionConfig",
                    "lambda:PutFunctionScalingConfig",
                    "lambda:PutProvisionedConcurrencyConfig",
                    "lambda:PutRuntimeManagementConfig",
                    "kms:Decrypt",
                    "ec2:DescribeVpcs",
                }
            )
        )
        alias = next(row for row in rows if "lambda:UpdateAlias" in row["Action"])
        self.assertEqual(
            alias["Resource"],
            f"arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api:{DEVELOPER['runtime_alias']}",
        )
        distribution = next(row for row in rows if "cloudfront:UpdateDistribution" in row["Action"])
        self.assertEqual(
            distribution["Resource"], "arn:aws:cloudfront::418638389566:distribution/E123456789"
        )
        iam = [row for row in rows if any(action.startswith("iam:") for action in row["Action"])]
        self.assertEqual(
            iam,
            [
                {
                    "Effect": "Allow",
                    "Action": ["iam:PassRole"],
                    "Resource": "arn:aws:iam::418638389566:role/fitfinity-test-hosting-api",
                    "Condition": {"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}},
                }
            ],
        )
        configuration = next(
            row for row in rows if "lambda:UpdateFunctionConfiguration" in row["Action"]
        )
        self.assertEqual(
            configuration["Resource"],
            "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api",
        )

    def test_wrong_stack_role_missing_duplicate_or_foreign_resources_fail_closed(self):
        original_stack, original_inventory = self.fixture(DEVELOPER)
        for error in (
            "stack",
            "role",
            "bucket",
            "distribution",
            "function",
            "missing",
            "duplicate",
            "page",
        ):
            stack, inventory = deepcopy(original_stack), deepcopy(original_inventory)
            rows = inventory["StackResourceSummaries"]
            if error == "stack":
                stack["StackId"] = "foreign"
            elif error == "role":
                stack["RoleARN"] = "foreign"
            elif error == "bucket":
                rows[2]["PhysicalResourceId"] = "foreign-bucket"
            elif error == "distribution":
                rows[3]["PhysicalResourceId"] = "*"
            elif error == "function":
                rows[0]["PhysicalResourceId"] = "foreign"
            elif error == "missing":
                rows.pop()
            elif error == "duplicate":
                rows.append(rows[0])
            else:
                inventory["NextToken"] = "more"
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                prepare(DEVELOPER, stack, inventory)

    def test_operator_policy_covers_the_complete_fixed_provider_surface(self):
        from rollout_provider import OPERATIONS

        permissions = {
            ("sts", "get-caller-identity"): "sts:GetCallerIdentity",
            ("ecr", "describe-image-scan-findings"): "ecr:DescribeImageScanFindings",
            ("s3api", "head-object"): "s3:GetObject",
            ("s3api", "put-object"): "s3:PutObject",
            ("cloudformation", "describe-stacks"): "cloudformation:DescribeStacks",
            ("cloudformation", "get-template"): "cloudformation:GetTemplate",
            ("cloudformation", "describe-stack-resource"): "cloudformation:DescribeStackResource",
            ("cloudformation", "list-stack-resources"): "cloudformation:ListStackResources",
            ("cloudformation", "create-change-set"): "cloudformation:CreateChangeSet",
            ("cloudformation", "describe-change-set"): "cloudformation:DescribeChangeSet",
            ("cloudformation", "execute-change-set"): "cloudformation:ExecuteChangeSet",
            ("lambda", "get-function"): "lambda:GetFunction",
            ("lambda", "get-alias"): "lambda:GetAlias",
            ("lambda", "untag-resource"): "lambda:UntagResource",
            ("cloudfront", "get-distribution"): "cloudfront:GetDistribution",
            ("lambda", "get-function-concurrency"): "lambda:GetFunctionConcurrency",
            ("iam", "get-role"): "iam:GetRole",
            ("iam", "list-role-policies"): "iam:ListRolePolicies",
            ("iam", "list-attached-role-policies"): "iam:ListAttachedRolePolicies",
            ("iam", "get-role-policy"): "iam:GetRolePolicy",
            ("iam", "get-policy"): "iam:GetPolicy",
            ("iam", "get-policy-version"): "iam:GetPolicyVersion",
            ("iam", "list-entities-for-policy"): "iam:ListEntitiesForPolicy",
        }
        self.assertEqual(OPERATIONS, set(permissions))
        stack, inventory = self.fixture(DEVELOPER)
        result = prepare(DEVELOPER, stack, inventory)
        actions = {
            action for row in result["operator_policy"]["Statement"] for action in row["Action"]
        }
        self.assertEqual(
            actions,
            set(permissions.values())
            | {"s3:ListBucket", "iam:PassRole", "lambda:ListTags", "rds:DescribeDBInstances"},
        )
        tag_read = next(
            row
            for row in result["operator_policy"]["Statement"]
            if "lambda:ListTags" in row["Action"]
        )
        self.assertEqual(
            tag_read["Resource"],
            "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api",
        )
        removal = [
            row
            for row in result["operator_policy"]["Statement"]
            if "lambda:UntagResource" in row["Action"]
        ]
        self.assertEqual(len(removal), 1)
        self.assertEqual(
            removal[0]["Resource"],
            "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api",
        )
        self.assertEqual(
            removal[0]["Condition"],
            {
                "ForAllValues:StringEquals": {
                    "aws:TagKeys": ["FitfinityMaintenance", "FitfinitySnapshot"]
                },
                "Null": {"aws:TagKeys": "false"},
            },
        )

    def test_feature_handler_permissions_follow_only_the_observed_boundary_owner(self):
        from importlib import import_module

        for profile in (DEVELOPER, import_module("verify-release-features").CLIENT):
            stack, inventory = self.fixture(profile)
            role = (
                f"arn:aws:iam::{profile['account']}:role/{profile['resource_prefix']}-hosting-api"
            )
            boundary = role.replace(":role/", ":policy/") + "-boundary"
            row = {
                "LogicalResourceId": "ExistingBoundary",
                "ResourceType": "AWS::IAM::ManagedPolicy",
                "PhysicalResourceId": boundary,
            }
            owned = deepcopy(inventory)
            owned["StackResourceSummaries"].append(row)
            name = profile["resource_prefix"] + "-iam-owner"
            external = {
                **stack,
                "StackName": name,
                "StackId": stack["StackId"].replace(stack["StackName"], name),
            }
            external_inventory = {"StackResourceSummaries": [row]}
            for where in ("hosting", "external"):
                with self.subTest(profile=profile["account"], owner=where):
                    args = (
                        {}
                        if where == "hosting"
                        else {"boundary_stack": external, "boundary_resources": external_inventory}
                    )
                    result = prepare(
                        profile, stack, owned if where == "hosting" else inventory, **args
                    )
                    grants = result["service_policy"]["Statement"]
                    inline = [grant for grant in grants if "iam:PutRolePolicy" in grant["Action"]]
                    self.assertEqual(len(inline), 1)
                    self.assertEqual(inline[0]["Resource"], role)
                    self.assertEqual(
                        set(inline[0]["Action"]),
                        {
                            "iam:GetRole",
                            "iam:GetRolePolicy",
                            "iam:ListRolePolicies",
                            "iam:ListAttachedRolePolicies",
                            "iam:PutRolePolicy",
                        },
                    )
                    managed = [
                        grant for grant in grants if "iam:CreatePolicyVersion" in grant["Action"]
                    ]
                    if where == "external":
                        self.assertEqual(managed, [])
                        managed = result["external_owner_handler_policy"]["Statement"]
                        external_read = [
                            grant
                            for grant in result["operator_policy"]["Statement"]
                            if grant["Resource"] == external["StackId"]
                        ]
                        self.assertEqual(len(external_read), 1)
                        self.assertEqual(
                            set(external_read[0]["Action"]),
                            {
                                "cloudformation:DescribeStacks",
                                "cloudformation:GetTemplate",
                                "cloudformation:DescribeStackResource",
                            },
                        )
                        self.assertTrue(
                            all(
                                external["StackId"] not in grant["Resource"]
                                for grant in result["operator_policy"]["Statement"]
                                if set(grant["Action"])
                                & {
                                    "cloudformation:ExecuteChangeSet",
                                    "cloudformation:CreateChangeSet",
                                }
                            )
                        )
                    self.assertEqual(len(managed), 1)
                    self.assertEqual(managed[0]["Resource"], boundary)
                    self.assertEqual(
                        set(managed[0]["Action"]),
                        {
                            "iam:GetPolicy",
                            "iam:GetPolicyVersion",
                            "iam:ListEntitiesForPolicy",
                            "iam:ListPolicyVersions",
                            "iam:CreatePolicyVersion",
                            "iam:DeletePolicyVersion",
                        },
                    )
                    self.assertEqual(result["service_policy"], result["service_boundary"])
                    self.assertEqual(result["operator_policy"], result["operator_boundary"])
            for owner, rows, extra in (
                (stack, external_inventory, inventory),
                (external, external_inventory, owned),
                (external, {**external_inventory, "NextToken": "more"}, inventory),
                (
                    external,
                    {"StackResourceSummaries": [{**row, "PhysicalResourceId": "foreign"}]},
                    inventory,
                ),
            ):
                with self.assertRaises(RuntimeError):
                    prepare(profile, stack, extra, boundary_stack=owner, boundary_resources=rows)

    def test_command_exports_review_digest_without_overwriting_prior_package(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from release_access import main
        from release_observation import digest

        stack, inventory = self.fixture(DEVELOPER)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (("profile", DEVELOPER), ("stack", stack), ("resources", inventory)):
                (root / name).write_text(json.dumps(value))
            args = ["release_access.py"]
            for name in ("profile", "stack", "resources", "output"):
                args.extend(["--" + name, str(root / name)])
            with patch("sys.argv", args):
                main()
                original = (root / "output").read_bytes()
                package = json.loads(original)
                self.assertEqual(package["review"]["decision"], "HOLD")
                self.assertEqual(package["review_sha256"], digest(package["review"]))
                self.assertEqual(
                    package["observations_sha256"],
                    digest({"stack": stack, "resources": inventory}),
                )
                with self.assertRaises(FileExistsError):
                    main()
                self.assertEqual((root / "output").read_bytes(), original)
                (root / "output").unlink()
                stack["RoleARN"] = "foreign"
                (root / "stack").write_text(json.dumps(stack))
                with self.assertRaises(RuntimeError):
                    main()
                self.assertFalse((root / "output").exists())

    def test_owner_plan_preserves_historical_roles_and_unrelated_runtime_boundary(self):
        from pathlib import Path

        from release_access import reconcile_owner
        from release_observation import digest

        owner = json.loads(Path(__file__).with_name("test-github-hosting-role.json").read_text())
        original = deepcopy(owner)
        stack, inventory = self.fixture(DEVELOPER)
        result = reconcile_owner(DEVELOPER, stack, inventory, owner, digest(owner))
        self.assertEqual(owner, original)
        candidate = result["candidate_template"]
        resources = candidate["Resources"]
        self.assertEqual(resources["ApiBoundary"], owner["Resources"]["ApiBoundary"])
        self.assertEqual(
            set(resources) - set(owner["Resources"]),
            {
                "ReleaseOperatorBoundary",
                "ReleaseServiceBoundary",
            },
        )
        for logical in ("HostingRole", "CloudFormationRole"):
            before = deepcopy(owner["Resources"][logical])
            after = deepcopy(resources[logical])
            before["Properties"].pop("Policies")
            after["Properties"].pop("Policies")
            after["Properties"].pop("PermissionsBoundary")
            self.assertEqual(after, before)
            self.assertEqual(
                resources[logical]["Properties"]["Policies"][0]["PolicyName"],
                owner["Resources"][logical]["Properties"]["Policies"][0]["PolicyName"],
            )
        self.assertEqual(result["candidate_template_sha256"], digest(candidate))
        self.assertEqual(result["decision"], "HOLD")
        candidate["Resources"]["ReleaseOperatorBoundary"].update(
            DeletionPolicy="Retain",
            Metadata={"Owner": "existing-operations"},
        )
        repeat = reconcile_owner(DEVELOPER, stack, inventory, candidate, digest(candidate))
        self.assertEqual(repeat["candidate_template"], candidate)

    def test_owner_plan_rejects_drift_or_foreign_boundary_instead_of_replacing_it(self):
        from pathlib import Path

        from release_access import reconcile_owner
        from release_observation import digest

        original = json.loads(Path(__file__).with_name("test-github-hosting-role.json").read_text())
        stack, inventory = self.fixture(DEVELOPER)
        for error in (
            "hash",
            "name",
            "trust",
            "attached",
            "policies",
            "boundary",
            "collision",
            "foreign-subject",
        ):
            owner = deepcopy(original)
            props = owner["Resources"]["HostingRole"]["Properties"]
            if error == "name":
                props["RoleName"] = "foreign"
            elif error == "trust":
                props["AssumeRolePolicyDocument"] = {}
            elif error == "foreign-subject":
                props["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"][
                    "token.actions.githubusercontent.com:sub"
                ] = "repo:foreign@123/portal@456:environment:aws-test"
            elif error == "attached":
                props["ManagedPolicyArns"] = ["foreign"]
            elif error == "policies":
                props["Policies"].append(deepcopy(props["Policies"][0]))
            elif error == "boundary":
                props["PermissionsBoundary"] = "foreign"
            elif error == "collision":
                owner["Resources"]["ReleaseOperatorBoundary"] = {}
            fingerprint = "0" * 64 if error == "hash" else digest(owner)
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                reconcile_owner(DEVELOPER, stack, inventory, owner, fingerprint)

    def test_client_owner_retains_standard_trust_without_developer_identity_leakage(self):
        from release_access import reconcile_owner
        from release_observation import digest

        profile = {
            **DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "resource_prefix": "client-prod",
            "github_repository": "client-example/portal",
        }
        owner = {"Resources": {"Unrelated": {"Type": "AWS::S3::Bucket"}}}
        for logical, name, principal, action, condition in (
            (
                "HostingRole",
                "client-prod-github-hosting",
                {
                    "Federated": (
                        "arn:aws:iam::123456789012:oidc-provider/"
                        "token.actions.githubusercontent.com"
                    )
                },
                "sts:AssumeRoleWithWebIdentity",
                {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": (
                            "repo:client-example/portal:environment:aws-test"
                        ),
                    }
                },
            ),
            (
                "CloudFormationRole",
                "client-prod-hosting-cloudformation",
                {"Service": "cloudformation.amazonaws.com"},
                "sts:AssumeRole",
                None,
            ),
        ):
            statement = {"Effect": "Allow", "Principal": principal, "Action": action}
            if condition is not None:
                statement["Condition"] = condition
            owner["Resources"][logical] = {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": name,
                    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [statement]},
                    "Policies": [{"PolicyName": "Existing", "PolicyDocument": {}}],
                },
            }
        stack, inventory = self.fixture(profile)
        result = reconcile_owner(profile, stack, inventory, owner, digest(owner))
        candidate = result["candidate_template"]
        self.assertEqual(candidate["Resources"]["Unrelated"], owner["Resources"]["Unrelated"])
        self.assertEqual(
            candidate["Resources"]["HostingRole"]["Properties"]["AssumeRolePolicyDocument"],
            owner["Resources"]["HostingRole"]["Properties"]["AssumeRolePolicyDocument"],
        )
        for forbidden in ("418638389566", "fitfinity-test", "ap-southeast-1", "LimYouSheng"):
            self.assertNotIn(forbidden, json.dumps(result))
        pinned = {**profile, "github_owner_id": "123", "github_repository_id": "456"}
        conditions = owner["Resources"]["HostingRole"]["Properties"]["AssumeRolePolicyDocument"][
            "Statement"
        ][0]["Condition"]["StringEquals"]
        key = "token.actions.githubusercontent.com:sub"
        for subject in (
            "repo:client-example/portal:environment:aws-test",
            "repo:client-example@999/portal@456:environment:aws-test",
            "repo:client-example@123/portal@999:environment:aws-test",
        ):
            conditions[key] = subject
            with self.subTest(subject=subject), self.assertRaisesRegex(RuntimeError, "trust"):
                reconcile_owner(pinned, stack, inventory, owner, digest(owner))
        conditions[key] = "repo:client-example@123/portal@456:environment:aws-test"
        matched = reconcile_owner(pinned, stack, inventory, owner, digest(owner))
        self.assertEqual(
            matched["candidate_template"]["Resources"]["HostingRole"]["Properties"][
                "AssumeRolePolicyDocument"
            ],
            owner["Resources"]["HostingRole"]["Properties"]["AssumeRolePolicyDocument"],
        )
