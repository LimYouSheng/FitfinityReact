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
            grant = next(row for row in rows if row["Action"] == [action])
            self.assertEqual(grant["Resource"], "arn:aws:iam::418638389566:" + resource)
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
        alias = next(row for row in rows if "lambda:UpdateAlias" in row["Action"])
        self.assertEqual(
            alias["Resource"],
            f"arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-staff-api:{DEVELOPER['runtime_alias']}",
        )
        distribution = next(row for row in rows if "cloudfront:UpdateDistribution" in row["Action"])
        self.assertEqual(
            distribution["Resource"], "arn:aws:cloudfront::418638389566:distribution/E123456789"
        )
        self.assertFalse(any(action.startswith("iam:") for row in rows for action in row["Action"]))

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
            ("lambda", "get-function-concurrency"): "lambda:GetFunctionConcurrency",
            ("iam", "get-role"): "iam:GetRole",
            ("iam", "list-entities-for-policy"): "iam:ListEntitiesForPolicy",
        }
        self.assertEqual(OPERATIONS, set(permissions))
        stack, inventory = self.fixture(DEVELOPER)
        result = prepare(DEVELOPER, stack, inventory)
        actions = {
            action for row in result["operator_policy"]["Statement"] for action in row["Action"]
        }
        self.assertEqual(actions, set(permissions.values()) | {"s3:ListBucket", "iam:PassRole"})

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
