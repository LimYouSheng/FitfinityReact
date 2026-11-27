"""Verify portable journal IAM templates preserve existing owner boundaries."""

import unittest
from copy import deepcopy

from deployment_profile import DEVELOPER, identities
from journal_setup import augment_operator, coordinator_template, operator_access, operator_owner


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            **DEVELOPER,
            "account": "123456789012",
            "resource_prefix": "client-prod",
            "github_repository": "client/portal",
            "github_environment": "client-production",
        }

    def installed(self, purpose):
        _, role, boundary, name = operator_owner(self.profile, purpose)
        policy = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "existing:Action", "Resource": "existing"}],
        }
        return {
            "Parameters": {"Preserved": {"Type": "String"}},
            "Resources": {
                role: {
                    "Type": "AWS::IAM::Role",
                    "Properties": {
                        "RoleName": name,
                        "PermissionsBoundary": {"Ref": boundary},
                        "AssumeRolePolicyDocument": {"original": "trust"},
                        "Policies": [
                            {"PolicyName": "Existing", "PolicyDocument": deepcopy(policy)}
                        ],
                    },
                },
                boundary: {
                    "Type": "AWS::IAM::ManagedPolicy",
                    "Properties": {"PolicyDocument": deepcopy(policy)},
                },
            },
        }

    def test_coordinator_has_only_target_storage_permissions(self):
        value = coordinator_template(self.profile)
        role = value["Resources"]["CoordinatorRole"]["Properties"]
        self.assertEqual(role["RoleName"], "client-prod-github-journal")
        policy = role["Policies"][0]["PolicyDocument"]
        self.assertEqual(policy["Statement"][0]["Action"], ["s3:GetObject", "s3:PutObject"])
        self.assertTrue(
            all(
                "client-prod-journal-123456789012" in resource
                for resource in policy["Statement"][0]["Resource"]
            )
        )
        self.assertEqual(
            policy["Statement"][1],
            {
                "Effect": "Allow",
                "Action": "s3:ListBucket",
                "Resource": "arn:aws:s3:::client-prod-journal-123456789012-ap-southeast-1",
            },
        )
        condition = role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"]
        self.assertEqual(
            condition["token.actions.githubusercontent.com:sub"],
            identities(self.profile)["oidc_subject"],
        )
        self.assertEqual(role["PermissionsBoundary"], {"Ref": "CoordinatorBoundary"})
        self.assertEqual(
            value["Resources"]["CoordinatorBoundary"]["Properties"]["PolicyDocument"], policy
        )

    def test_each_operator_update_preserves_trust_resources_and_prior_grants(self):
        for purpose in ("maintenance", "probe", "upgrade", "hosting"):
            with self.subTest(purpose=purpose):
                original = self.installed(purpose)
                retained = deepcopy(original)
                candidate = augment_operator(original, self.profile, purpose)
                _, role, boundary, _ = operator_owner(self.profile, purpose)
                self.assertEqual(original, retained)
                self.assertEqual(set(candidate["Resources"]), set(original["Resources"]))
                self.assertEqual(candidate["Parameters"], original["Parameters"])
                props = candidate["Resources"][role]["Properties"]
                self.assertEqual(props["AssumeRolePolicyDocument"], {"original": "trust"})
                for document in (
                    props["Policies"][0]["PolicyDocument"],
                    candidate["Resources"][boundary]["Properties"]["PolicyDocument"],
                ):
                    self.assertEqual(document["Statement"][0]["Action"], "existing:Action")
                    self.assertEqual(document["Statement"][1], operator_access(self.profile))
                self.assertEqual(augment_operator(candidate, self.profile, purpose), candidate)

    def test_foreign_role_external_boundary_and_conflicting_grant_stop(self):
        original = self.installed("probe")
        for change in ("role", "boundary", "grant"):
            value = deepcopy(original)
            props = value["Resources"]["OperatorRole"]["Properties"]
            if change == "role":
                props["RoleName"] = "foreign"
            elif change == "boundary":
                props["PermissionsBoundary"] = "arn:aws:iam::123456789012:policy/external"
            else:
                props["Policies"][0]["PolicyDocument"]["Statement"].append(
                    {**operator_access(self.profile), "Resource": "*"}
                )
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                augment_operator(value, self.profile, "probe")


if __name__ == "__main__":
    unittest.main()
