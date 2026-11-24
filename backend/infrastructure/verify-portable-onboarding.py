"""Exercise the operator's offline first-install commands on an independent target."""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from deployment_profile import workflow_target
from portable_onboarding import main

PROFILE = {
    "schema_version": 1,
    "github_repository": "NorthStudio/staff-portal",
    "github_owner_id": "97311",
    "github_repository_id": "8013142",
    "github_environment": "client-live",
    "account": "203000000473",
    "region": "ca-central-1",
    "resource_prefix": "north-live",
    "secret_prefix": "north/live",
    "runtime_alias": "serving",
}
FOUNDATION = {
    "foundation": {
        "vpc_cidr": "172.28.0.0/16",
        "engine_version": "17.11",
        "database_class": "db.t4g.micro",
        "storage_gib": 20,
        "max_storage_gib": 40,
        "multi_az": False,
        "backup_days": 7,
        "egress": "none",
    },
    "session_hours": 8,
    "staff_portal_url": "",
    "browser_origin": "https://staff.north.example",
}
HOSTING = {
    "hosting": {
        "database_secret": "arn:aws:secretsmanager:ca-central-1:203000000473:secret:"
        "north/live/database/app-aB3vF1",
        "auth_secret": "arn:aws:secretsmanager:ca-central-1:203000000473:secret:"
        "north/live/auth-xY987Z",
        "db_host": "north-live-db.a123bc.ca-central-1.rds.amazonaws.com",
        "pool": "ca-central-1_North123",
        "client": "northpublicidentifier123",
        "subnets": ["subnet-" + "1" * 17, "subnet-" + "2" * 17],
        "security_groups": ["sg-" + "a" * 17],
        "image": "203000000473.dkr.ecr.ca-central-1.amazonaws.com/north-live-api@sha256:"
        + "9" * 64,
        "environment": "production",
        "stage": "staff",
        "features": {"media": True, "invitations": True, "email_changes": True},
    },
    "frontend_prefix": "releases/" + "6" * 40 + "/" + "7" * 64,
    "edge_arn": "arn:aws:wafv2:us-east-1:203000000473:global/webacl/"
    "north-live-login-cloudfront/01010101-1234-5678-9012-abcdefabcdef",
}


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.profile = self.root / "target.json"
        self.profile.write_text(json.dumps(PROFILE, indent=2))

    def export(self, phase, data, *, output=None):
        inputs = self.root / (phase + ".json")
        inputs.write_text(data if isinstance(data, str) else json.dumps(data) + "\n")
        output = output or self.root / (phase + ".zip")
        main(
            [
                phase,
                "--profile",
                str(self.profile),
                "--inputs",
                str(inputs),
                "--output",
                str(output),
            ]
        )
        return output

    def test_client_prepares_foundation_then_hosting_and_selects_the_same_actions_target(self):
        with patch.dict(
            "os.environ", {"GITHUB_REPOSITORY_OWNER_ID": "97311", "GITHUB_REPOSITORY_ID": "8013142"}
        ):
            target = workflow_target(
                "north", "NorthStudio/staff-portal", configuration=json.dumps({"north": PROFILE})
            )
        self.assertEqual(target["profile"], "env:north")
        self.assertEqual(target["environment"], "client-live")
        expected = {
            "foundation": {
                "foundation.json",
                "storage.json",
                "identity.json",
                "image-access.json",
                "maintenance-access.json",
                "edge.json",
            },
            "hosting": {"hosting.json"},
        }
        documents = {}
        for phase, inputs in (("foundation", FOUNDATION), ("hosting", HOSTING)):
            with ZipFile(self.export(phase, inputs)) as package:
                self.assertEqual(set(package.namelist()), expected[phase] | {"receipt.json"})
                receipt = json.loads(package.read("receipt.json"))
                self.assertEqual(receipt["phase"], phase)
                self.assertEqual(receipt["profile_sha256"], target["profile_sha256"])
                self.assertEqual(
                    receipt["input_file_sha256"],
                    {
                        key: hashlib.sha256(path.read_bytes()).hexdigest()
                        for key, path in (
                            ("profile", self.profile),
                            ("inputs", self.root / (phase + ".json")),
                        )
                    },
                )
                self.assertEqual(
                    receipt["template_file_sha256"],
                    {
                        name: hashlib.sha256(package.read(name)).hexdigest()
                        for name in expected[phase]
                    },
                )
                for name in package.namelist():
                    content = package.read(name)
                    for forbidden in (
                        b"418638389566",
                        b"ap-southeast-1",
                        b"LimYouSheng",
                        b"fitfinity-test",
                        b"aws-test",
                        b"first-test",
                    ):
                        self.assertNotIn(forbidden, content)
                    if name != "receipt.json":
                        documents[name] = json.loads(content)
                        assertions = documents[name]["Rules"]["SelectedTarget"]["Assertions"]
                        region = "us-east-1" if name == "edge.json" else "ca-central-1"
                        self.assertEqual(
                            assertions[1]["Assert"],
                            {"Fn::Equals": [{"Ref": "AWS::Region"}, region]},
                        )
        db = documents["foundation.json"]["Resources"]["Database"]["Properties"]
        self.assertEqual(db["DBInstanceIdentifier"], "north-live-db")
        self.assertTrue(db["ManageMasterUserPassword"])
        role = documents["image-access.json"]["Resources"]["ImageRole"]["Properties"]
        self.assertEqual(target["image_role"], "arn:aws:iam::203000000473:role/" + role["RoleName"])
        self.assertEqual(
            role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"][
                "token.actions.githubusercontent.com:sub"
            ],
            "repo:NorthStudio@97311/staff-portal@8013142:environment:client-live",
        )
        runtime = documents["hosting.json"]["Resources"]["ApiFunction"]["Properties"]
        env = runtime["Environment"]["Variables"]
        self.assertEqual(
            env["FITFINITY_DATABASE_SECRET_ARN"], HOSTING["hosting"]["database_secret"]
        )
        self.assertEqual(
            env["FITFINITY_MEDIA_BUCKET"],
            documents["storage.json"]["Resources"]["Media"]["Properties"]["BucketName"],
        )
        self.assertEqual(env["FITFINITY_MEDIA_ENABLED"], "true")
        self.assertEqual(env["FITFINITY_STAFF_INVITATIONS_ENABLED"], "true")
        self.assertEqual(env["FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED"], "true")

    def test_refuses_secret_contents_duplicate_keys_and_foreign_resources_before_publication(self):
        wrong_secret = HOSTING["hosting"]["auth_secret"].replace("203000000473", "999999999999")
        cases = [
            ("foundation", {**FOUNDATION, "password": "synthetic-confidential-marker"}),
            ("foundation", {**FOUNDATION, "session_hours": 4}),
            ("foundation", json.dumps(FOUNDATION)[:-1] + ', "session_hours": 8}'),
            (
                "hosting",
                {**HOSTING, "hosting": {**HOSTING["hosting"], "auth_secret": wrong_secret}},
            ),
            (
                "hosting",
                {
                    **HOSTING,
                    "hosting": {
                        **HOSTING["hosting"],
                        "cognito_client_secret": "synthetic-confidential-marker",
                    },
                },
            ),
        ]
        for phase, inputs in cases:
            with self.subTest(phase=phase), redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as refused:
                    self.export(phase, inputs)
                self.assertEqual(refused.exception.code, 1)
                self.assertNotIn("synthetic-confidential-marker", errors.getvalue())
                self.assertFalse((self.root / (phase + ".zip")).exists())

    def test_existing_package_and_symlink_targets_cannot_be_overwritten(self):
        target = self.export("foundation", FOUNDATION)
        original = target.read_bytes()
        link = self.root / "redirected.zip"
        link.symlink_to(target)
        for path in (target, link):
            with self.subTest(path=path), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as refused:
                    self.export("hosting", HOSTING, output=path)
                self.assertEqual(refused.exception.code, 1)
                self.assertEqual(target.read_bytes(), original)
        self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
