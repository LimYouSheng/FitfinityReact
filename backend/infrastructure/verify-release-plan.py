"""Offline rollout/rollback preservation probes using synthetic deployment templates."""

import json
import unittest
from copy import deepcopy

import hosting_design as design
from deployment_profile import DEVELOPER, fingerprint
from release_image import URI
from release_observation import digest
from release_plan import prepare


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.template = design.app_template(
            "releases/" + "a" * 40 + "/" + "b" * 64,
            "arn:aws:wafv2:us-east-1:418638389566:global/webacl/"
            "fitfinity-test-login-cloudfront/00000000-0000-0000-0000-000000000000",
        )
        self.arguments = dict(
            observed_template_sha256=digest(self.template),
            source_sha="c" * 40,
            image_digest="sha256:" + "d" * 64,
            frontend_sha256="e" * 64,
        )

    def test_only_reviewed_targets_change_and_original_is_untouched(self):
        original = deepcopy(self.template)
        result = prepare(self.template, **self.arguments)
        self.assertEqual(self.template, original)
        candidate = result["candidate_template"]["Resources"]
        self.assertEqual(result["deployment_decision"], "HOLD")
        version = candidate["ApiAlias"]["Properties"]["FunctionVersion"]["Fn::GetAtt"][0]
        self.assertRegex(version, r"^ReleaseVersionc{40}[0-9a-f]{16}$")
        self.assertEqual(set(candidate) - set(original["Resources"]), {version})
        for name, resource in original["Resources"].items():
            if name not in {"ApiFunction", "ApiAlias", "Distribution"}:
                self.assertEqual(candidate[name], resource)
        before = original["Resources"]["ApiFunction"]["Properties"]
        after = candidate["ApiFunction"]["Properties"]
        self.assertEqual(
            {k: v for k, v in before.items() if k not in {"Code", "ReservedConcurrentExecutions"}},
            {k: v for k, v in after.items() if k not in {"Code", "ReservedConcurrentExecutions"}},
        )
        self.assertEqual(after["Code"]["ImageUri"], URI + "@sha256:" + "d" * 64)
        self.assertEqual(after["ReservedConcurrentExecutions"], 0)

    def test_rollback_keeps_all_versions_and_original_alias_assets(self):
        result = prepare(self.template, **self.arguments)
        rollback = result["rollback_template"]["Resources"]
        for name, resource in self.template["Resources"].items():
            expected = deepcopy(resource)
            if name == "ApiFunction":
                expected["Properties"]["ReservedConcurrentExecutions"] = 0
            self.assertEqual(rollback[name], expected)
        self.assertEqual(set(rollback), set(result["candidate_template"]["Resources"]))
        version = result["candidate_template"]["Resources"]["ApiAlias"]["Properties"][
            "FunctionVersion"
        ]["Fn::GetAtt"][0]
        self.assertEqual(rollback[version]["DeletionPolicy"], "Retain")
        self.assertIn("no downgrade", result["migration"])

    def test_stale_observation_refused(self):
        self.template["Description"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "template changed"):
            prepare(self.template, **self.arguments)

    def test_floating_or_invalid_artifact_rejected(self):
        for field, value in (
            ("source_sha", "main"),
            ("image_digest", "latest"),
            ("frontend_sha256", "unknown"),
        ):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                prepare(self.template, **{**self.arguments, field: value})

    def test_wrong_target_or_weighted_routing_rejected(self):
        for change in ("function", "image", "routing"):
            template = deepcopy(self.template)
            resources = template["Resources"]
            if change == "function":
                resources["ApiFunction"]["Properties"]["FunctionName"] = "other"
            elif change == "image":
                resources["ApiFunction"]["Properties"]["Code"]["ImageUri"] = "other:latest"
            else:
                resources["ApiAlias"]["Properties"]["RoutingConfig"] = {"weighted": True}
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                prepare(
                    template, **{**self.arguments, "observed_template_sha256": digest(template)}
                )

    def test_repeat_candidate_refused_without_deleting_retained_versions(self):
        template = prepare(self.template, **self.arguments)["candidate_template"]
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            prepare(template, **{**self.arguments, "observed_template_sha256": digest(template)})

    def test_client_rollout_and_rollback_preserve_independent_target(self):
        profile = {
            **DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "resource_prefix": "client-prod",
            "runtime_alias": "live",
        }
        uri = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/client-prod-api"
        template = {
            "Resources": {
                "ApiFunction": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "FunctionName": "client-prod-staff-api",
                        "ReservedConcurrentExecutions": 2,
                        "PackageType": "Image",
                        "Code": {"ImageUri": uri + "@sha256:" + "f" * 64},
                    },
                },
                "ApiAlias": {
                    "Type": "AWS::Lambda::Alias",
                    "Properties": {
                        "Name": "live",
                        "FunctionName": {"Ref": "ApiFunction"},
                        "FunctionVersion": {"Fn::GetAtt": ["PreviousVersion", "Version"]},
                    },
                },
                "PreviousVersion": {
                    "Type": "AWS::Lambda::Version",
                    "Properties": {"FunctionName": {"Ref": "ApiFunction"}},
                },
                "Distribution": {
                    "Properties": {
                        "DistributionConfig": {
                            "Origins": [
                                {
                                    "Id": "frontend",
                                    "OriginPath": "/releases/" + "a" * 40 + "/" + "b" * 64,
                                }
                            ]
                        }
                    }
                },
            }
        }
        result = prepare(
            template,
            **{**self.arguments, "observed_template_sha256": digest(template)},
            profile=profile,
        )
        self.assertEqual(result["profile_sha256"], fingerprint(profile))
        self.assertEqual(
            result["candidate_template"]["Resources"]["ApiFunction"]["Properties"]["Code"],
            {"ImageUri": uri + "@sha256:" + "d" * 64},
        )
        self.assertEqual(
            result["rollback_template"]["Resources"]["ApiAlias"], template["Resources"]["ApiAlias"]
        )
        self.assertEqual(
            result["rollback_template"]["Resources"]["PreviousVersion"],
            template["Resources"]["PreviousVersion"],
        )
        with self.assertRaises(RuntimeError):
            prepare(template, **{**self.arguments, "observed_template_sha256": digest(template)})


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        from deployment_profile import identities

        self.profile = {
            **DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "resource_prefix": "client-prod",
            "secret_prefix": "client/production",
            "github_repository": "client-example/portal",
        }
        self.target = identities(self.profile)
        self.review = {
            "profile_sha256": self.target["profile_sha256"],
            "source_sha": "a" * 40,
            "operation_id": "b" * 32,
            "expires_at": 1200,
            "function_revision": "exact-revision",
            "database_resource_id": "db-unique",
            "previous_concurrency": 2,
        }
        self.tags, self.events, self.saved = {}, [], []
        self.concurrency = 2
        self.failure = None
        self.backup_tags = []
        self.snapshot = None

    def call(self, service, operation, values):
        self.events.append((service, operation, values))
        if operation == "get-caller-identity":
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/client-prod-github-maintenance/run",
            }
        if operation == "get-function":
            return {
                "Configuration": {
                    "FunctionArn": "arn:aws:lambda:eu-west-1:123456789012:function:"
                    + self.target["runtime_function"],
                    "RevisionId": "exact-revision",
                    "LastUpdateStatus": "Successful",
                    "Timeout": 30,
                },
                "Tags": dict(self.tags),
            }
        if operation == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "DBInstanceArn": "arn:aws:rds:eu-west-1:123456789012:db:client-prod-db",
                        "DbiResourceId": "db-unique",
                        "DBInstanceStatus": "available",
                        "Engine": "postgres",
                        "StorageEncrypted": True,
                        "PubliclyAccessible": False,
                    }
                ]
            }
        if operation == "get-function-concurrency":
            return {"ReservedConcurrentExecutions": self.concurrency}
        if operation == "tag-resource":
            self.tags.update(values["Tags"])
        elif operation == "put-function-concurrency":
            self.concurrency = values["ReservedConcurrentExecutions"]
        elif operation == "create-db-snapshot":
            self.backup_tags = values["Tags"]
            self.snapshot = {
                "DBSnapshotArn": "arn:aws:rds:eu-west-1:123456789012:snapshot:"
                + values["DBSnapshotIdentifier"],
                "DbiResourceId": "db-unique",
                "DBInstanceIdentifier": "client-prod-db",
                "SnapshotType": "manual",
                "Encrypted": True,
                "Status": "available",
            }
        elif operation == "describe-db-snapshots":
            return {"DBSnapshots": [self.snapshot]}
        elif operation == "list-tags-for-resource":
            return {"TagList": self.backup_tags}
        else:
            self.fail("Unexpected provider operation: " + operation)
        if operation == self.failure:
            raise RuntimeError("synthetic lost response")
        return {}

    def step(self, mode, prior=None, **kwargs):
        from release_maintenance import execute

        return execute(
            mode,
            self.review,
            self.call,
            kwargs.pop("persist", lambda row: self.saved.append(deepcopy(row))),
            profile=self.profile,
            prior=prior,
            now=kwargs.pop("now", 1000),
            **kwargs,
        )

    def paused(self):
        return self.step("inspect", self.step("pause"))

    def test_pause_snapshot_observation_retains_exact_target_and_original_concurrency(self):
        paused = self.paused()
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(paused["previous_concurrency"], 2)
        self.assertEqual(self.concurrency, 0)
        with self.assertRaisesRegex(RuntimeError, "in-flight"):
            self.step("snapshot", paused, now=1029)
        requested = self.step("snapshot", paused, now=1030)
        self.assertEqual(requested["state"], "snapshot_submitted")
        ready = self.step("snapshot-check", requested)
        self.assertEqual(ready["state"], "snapshot_ready")
        self.assertEqual(
            ready["snapshot_arn"],
            "arn:aws:rds:eu-west-1:123456789012:snapshot:client-prod-release-" + "b" * 32,
        )
        writes = [
            row[1]
            for row in self.events
            if row[1] in {"put-function-concurrency", "create-db-snapshot"}
        ]
        self.assertEqual(writes, ["put-function-concurrency", "create-db-snapshot"])
        self.assertEqual(self.saved[0]["state"], "pause_submitted")

    def test_lost_pause_response_is_observed_and_never_replayed(self):
        self.failure = "put-function-concurrency"
        with self.assertRaisesRegex(RuntimeError, "lost response"):
            self.step("pause")
        prior = self.saved[-1]
        self.assertEqual(prior["state"], "pause_submitted")
        self.assertEqual(self.step("inspect", prior)["state"], "paused")
        with self.assertRaisesRegex(RuntimeError, "do not replay"):
            self.step("pause")
        self.assertEqual(sum(row[1] == "put-function-concurrency" for row in self.events), 1)

    def test_cloud_snapshot_marker_rejects_old_pause_receipt_and_recovers_lost_response(self):
        paused = self.paused()
        self.failure = "create-db-snapshot"
        with self.assertRaisesRegex(RuntimeError, "lost response"):
            self.step("snapshot", paused, now=1030)
        with self.assertRaisesRegex(RuntimeError, "do not replay"):
            self.step("snapshot", paused, now=1030)
        recovered = self.step("inspect", paused)
        self.assertTrue(recovered["snapshot_requested"])
        self.assertEqual(self.step("snapshot-check", recovered)["state"], "snapshot_ready")
        self.assertEqual(sum(row[1] == "create-db-snapshot" for row in self.events), 1)

    def test_receipt_failure_prevents_any_provider_write(self):
        def fail(_):
            raise OSError("synthetic disk failure")

        with self.assertRaises(OSError):
            self.step("pause", persist=fail)
        self.assertEqual(self.tags, {})
        self.assertEqual(self.concurrency, 2)
        self.assertFalse(any(row[1] == "put-function-concurrency" for row in self.events))

    def test_drift_foreign_marker_or_missing_snapshot_encryption_is_refused(self):
        for key, value in [
            ("function_revision", "changed"),
            ("database_resource_id", "foreign"),
            ("profile_sha256", "0" * 64),
            ("previous_concurrency", True),
        ]:
            original = self.review[key]
            self.review[key] = value
            with self.assertRaises(RuntimeError):
                self.step("pause")
            self.review[key] = original
            self.assertEqual(self.tags, {})
        paused = self.paused()
        requested = self.step("snapshot", paused, now=1030)
        self.snapshot["Encrypted"] = False
        with self.assertRaisesRegex(RuntimeError, "encryption"):
            self.step("snapshot-check", requested)
        self.snapshot["Encrypted"] = True
        self.tags["FitfinityMaintenance"] = "foreign"
        with self.assertRaisesRegex(RuntimeError, "marker"):
            self.step("inspect", paused)

    def test_expiry_blocks_new_writes_but_keeps_read_only_recovery_available(self):
        paused = self.paused()
        with self.assertRaisesRegex(RuntimeError, "unexpired"):
            self.step("snapshot", paused, now=1200)
        self.assertEqual(self.step("inspect", paused, now=5000)["state"], "paused")
        self.assertFalse(any(row[1] == "create-db-snapshot" for row in self.events))


class MaintenanceOperatorTests(unittest.TestCase):
    setUp = MaintenanceTests.setUp

    def test_operator_rejects_other_actions_and_never_exposes_provider_errors(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import maintenance_operator as operator

        with patch.object(operator.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "not allowed"):
                operator.aws("rds", "delete-db-snapshot", {}, profile=self.profile)
            run.assert_not_called()
            run.return_value = SimpleNamespace(returncode=1, stdout="sensitive", stderr="sensitive")
            with self.assertRaisesRegex(RuntimeError, "inspect retained") as caught:
                operator.aws("rds", "describe-db-instances", {}, profile=self.profile)
            self.assertNotIn("sensitive", str(caught.exception))
            self.assertEqual(run.call_args.kwargs["env"]["AWS_MAX_ATTEMPTS"], "1")
            self.assertIn("eu-west-1", run.call_args.args[0])

    def test_operator_checks_review_digest_and_target_before_execution(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        import maintenance_operator as operator

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "maintenance-review/maintenance-review"
            folder.mkdir(parents=True)
            (folder / "review.json").write_text(json.dumps(self.review))
            with (
                patch.dict(operator.os.environ, {"REVIEW_SHA256": operator.digest(self.review)}),
                patch.object(operator.time, "time", return_value=1000),
            ):
                self.assertEqual(
                    operator.reviewed_input(root, self.profile, "a" * 40, False), self.review
                )
                with self.assertRaisesRegex(RuntimeError, "source differs"):
                    operator.reviewed_input(root, self.profile, "c" * 40, False)
                changed = {**self.review, "function_revision": "tampered"}
                (folder / "review.json").write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError, "digest differs"):
                    operator.reviewed_input(root, self.profile, "a" * 40, False)

    def test_prior_failed_run_can_recover_but_foreign_workflow_cannot_supply_intent(self):
        from pathlib import Path
        from unittest.mock import patch

        import maintenance_operator as operator

        run = {
            "path": ".github/workflows/aws-maintenance.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": self.profile["github_repository"]},
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "a" * 40,
            "run_attempt": 2,
        }
        with (
            patch.object(operator.subprocess, "check_output", return_value=json.dumps(run)),
            patch.object(operator.subprocess, "run") as download,
        ):
            operator.fetch_prior("123", Path("/tmp/synthetic"), self.profile)
            self.assertIn("fitfinity-maintenance-123-2", download.call_args.args[0])
        run["path"] = ".github/workflows/foreign.yml"
        with (
            patch.object(operator.subprocess, "check_output", return_value=json.dumps(run)),
            patch.object(operator.subprocess, "run") as download,
        ):
            with self.assertRaises(RuntimeError):
                operator.fetch_prior("123", Path("/tmp/synthetic"), self.profile)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
