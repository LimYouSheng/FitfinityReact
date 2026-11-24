"""Verify exact release health evidence and reject substituted provider/public state."""

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from deployment_profile import DEVELOPER, identities
from hosting_frontend import inventory, manifest_hash
from release_health import read_url, verify


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.target = identities(DEVELOPER)
        self.template = {
            "Resources": {
                "ApiAlias": {"Properties": {"Name": "staff"}},
                "ApiFunction": {"Properties": {"ReservedConcurrentExecutions": 2}},
            }
        }
        self.review = {"stack_arn": "owned-stack", "candidate_template": self.template}
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        for name, content in (
            ("index.html", b"reviewed frontend"),
            ("sw.js", b"reviewed worker"),
            ("manifest.webmanifest", b"{}"),
        ):
            (self.folder / name).write_bytes(content)
        self.evidence = {
            "frontend_prefix": "releases/reviewed",
            "frontend_sha256": manifest_hash(inventory(self.folder)),
            "image_digest": "sha256:" + "a" * 64,
        }
        self.responses = {
            "describe-stacks": {
                "Stacks": [
                    {
                        "StackId": "owned-stack",
                        "StackStatus": "UPDATE_COMPLETE",
                        "Outputs": [
                            {"OutputKey": key, "OutputValue": value}
                            for key, value in (
                                ("FrontendDomain", "d123.cloudfront.net"),
                                ("DistributionId", "D123"),
                                ("FunctionVersion", "7"),
                            )
                        ],
                    }
                ]
            },
            "get-template": {"TemplateBody": self.template},
            "get-distribution": {
                "Distribution": {
                    "ARN": f"arn:aws:cloudfront::{self.target['account']}:distribution/D123",
                    "DomainName": "d123.cloudfront.net",
                    "Status": "Deployed",
                    "DistributionConfig": {
                        "Enabled": True,
                        "Origins": {
                            "Items": [{"Id": "frontend", "OriginPath": "/releases/reviewed"}]
                        },
                    },
                }
            },
            "get-alias": {"FunctionVersion": "7"},
            "get-function": {
                "Configuration": {"Version": "7"},
                "Code": {
                    "ResolvedImageUri": self.target["registry"]
                    + "/"
                    + self.target["image_repository"]
                    + "@sha256:"
                    + "a" * 64
                },
            },
            "get-function-concurrency": {"ReservedConcurrentExecutions": 2},
        }
        self.urls = []
        self.payloads = {
            "index.html": b"reviewed frontend",
            "health/live": b'{"status":"alive"}',
            "health/ready": b'{"status":"ready"}',
        }

    def call(self, service, operation, values):
        self.assertNotIn(operation, {"create-change-set", "execute-change-set", "untag-resource"})
        return deepcopy(self.responses[operation])

    def read(self, url):
        self.assertTrue(url.startswith("https://d123.cloudfront.net/"))
        self.urls.append(url)
        return self.payloads[url.removeprefix("https://d123.cloudfront.net/")]

    def run_health(self):
        return verify(
            self.review,
            self.evidence,
            self.call,
            self.read,
            self.folder,
            profile=DEVELOPER,
            now=1500,
        )

    def test_exact_public_and_provider_evidence_is_required(self):
        receipt = self.run_health()
        self.assertEqual(receipt["state"], "health_verified")
        self.assertEqual(receipt["function_version"], "7")
        self.assertEqual(len(self.urls), 3)
        self.assertEqual(receipt["observed_at"], 1500)

    def test_wrong_deployment_and_public_payloads_are_rejected(self):
        for problem in (
            "image",
            "alias",
            "weighted",
            "distribution",
            "template",
            "capacity",
            "index",
            "ready",
        ):
            with self.subTest(problem=problem):
                self.setUp()
                if problem == "image":
                    self.responses["get-function"]["Code"]["ResolvedImageUri"] = "foreign"
                elif problem == "alias":
                    self.responses["get-alias"]["FunctionVersion"] = "8"
                elif problem == "weighted":
                    self.responses["get-alias"]["RoutingConfig"] = {
                        "AdditionalVersionWeights": {"8": 0.1}
                    }
                elif problem == "distribution":
                    self.responses["get-distribution"]["Distribution"]["Status"] = "InProgress"
                elif problem == "template":
                    self.responses["get-template"] = {"TemplateBody": {}}
                elif problem == "capacity":
                    self.responses["get-function-concurrency"]["ReservedConcurrentExecutions"] = 0
                elif problem == "index":
                    self.payloads["index.html"] = b"old frontend"
                else:
                    self.payloads["health/ready"] = b'{"status":"not_ready"}'
                with self.assertRaises(RuntimeError):
                    self.run_health()

    def test_http_target_cannot_be_redirected_to_arbitrary_hosts(self):
        from release_health import NoRedirect

        with patch("release_health.build_opener") as opener:
            for url in (
                "http://d123.cloudfront.net/health/ready",
                "https://evil.test/health/ready",
                "https://d123.cloudfront.net.evil.test/health/ready",
                "https://d123.cloudfront.net/private",
            ):
                with self.subTest(url=url), self.assertRaises(RuntimeError):
                    read_url(url)
            opener.assert_not_called()
        self.assertIsNone(
            NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.test")
        )
