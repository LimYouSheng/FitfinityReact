"""Prove release verification reuse rejects missing, stale and substituted CI evidence."""

import time
import unittest
from copy import deepcopy

from deployment_profile import DEVELOPER
from release_verification import discover, verify


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        self.profile = {**DEVELOPER, "github_repository": "client-example/portal"}
        repo = {"full_name": self.profile["github_repository"]}
        from datetime import UTC, datetime

        self.run = {
            "created_at": datetime.fromtimestamp(time.time(), UTC).isoformat(),
            "id": 123,
            "run_attempt": 2,
            "path": ".github/workflows/pages.yml",
            "event": "push",
            "head_branch": "main",
            "head_sha": self.source,
            "repository": repo,
            "head_repository": repo,
            "status": "completed",
            "conclusion": "success",
        }
        self.scan = {**self.run, "id": 124, "path": ".github/workflows/codeql.yml"}
        names = [
            "quality",
            "unit",
            "browser-build",
            "backend-checks",
            "infrastructure",
            "frontend",
            "backend",
            "api-browser",
            "browser-profile (desktop-chromium)",
            "browser-profile (phone)",
            "browser-profile (tablet)",
            "backend-group (identity-clients)",
            "backend-group (scheduling-packages)",
            "backend-group (records-platform)",
            "api-browser-shard (1)",
            "api-browser-shard (2)",
        ]
        self.jobs = {
            "total_count": 16,
            "jobs": [self.job("verify / " + name, 123) for name in names],
        }
        self.scan_jobs = {
            "total_count": 2,
            "jobs": [
                self.job(name, 124)
                for name in ("CodeQL (javascript-typescript)", "CodeQL (python)")
            ],
        }
        self.scans = {"total_count": 1, "workflow_runs": [self.scan]}
        self.results = {
            "total_count": 1,
            "check_runs": [
                {
                    "name": "CodeQL",
                    "head_sha": self.source,
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 57789, "slug": "github-advanced-security"},
                }
            ],
        }
        self.paths = []

    def discovery_read(self, path):
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": self.source}}
        if "/workflows/pages.yml/runs?" in path:
            return {"total_count": len(self.candidates), "workflow_runs": self.candidates}
        return self.read(path)

    def test_discovery_authenticates_latest_main_run(self):
        self.candidates = [self.run]
        result = discover(self.source, self.profile, self.discovery_read)
        self.assertEqual(result["verification_run"], 123)
        self.assertEqual(result["codeql_run"], 124)
        self.assertEqual(len(self.paths), 5)

    def test_discovery_does_not_fall_back_from_newer_failed_run(self):
        self.candidates = [self.run, {**self.run, "id": 125, "conclusion": "failure"}]
        with self.assertRaises(RuntimeError):
            discover(self.source, self.profile, self.discovery_read)
        self.assertEqual(self.paths, [])

    def test_discovery_rejects_main_moving_during_verification(self):
        self.candidates = [self.run]
        calls = []

        def read(path):
            if path.endswith("/git/ref/heads/main"):
                calls.append(path)
                return {"object": {"sha": self.source if len(calls) == 1 else "b" * 40}}
            return self.discovery_read(path)

        with self.assertRaisesRegex(RuntimeError, "Main changed"):
            discover(self.source, self.profile, read)
        self.assertEqual(len(self.paths), 5)

    def job(self, name, run_id):
        return {
            "name": name,
            "run_id": run_id,
            "run_attempt": 2,
            "head_sha": self.source,
            "status": "completed",
            "conclusion": "success",
        }

    def read(self, path):
        self.paths.append(path)
        root = "repos/client-example/portal"
        values = {
            f"{root}/actions/runs/123": self.run,
            f"{root}/actions/runs/123/attempts/2/jobs?per_page=100": self.jobs,
            (
                f"{root}/actions/workflows/codeql.yml/runs?head_sha={self.source}"
                "&branch=main&per_page=100"
            ): self.scans,
            f"{root}/actions/runs/124/attempts/2/jobs?per_page=100": self.scan_jobs,
            (
                f"{root}/commits/{self.source}/check-runs?check_name=CodeQL"
                "&filter=latest&per_page=100"
            ): self.results,
        }
        return deepcopy(values[path])

    def test_exact_main_source_requires_every_gate_and_codeql_result(self):
        result = verify("123", self.source, self.profile, self.read)
        self.assertEqual(
            result,
            {
                "source_sha": self.source,
                "repository": "client-example/portal",
                "verification_run": 123,
                "verification_attempt": 2,
                "codeql_run": 124,
                "codeql_attempt": 2,
                "codeql_result": "success",
                "state": "source_verified",
            },
        )
        self.assertEqual(len(self.paths), 5)
        self.assertFalse(any("LimYouSheng" in path for path in self.paths))

    def test_foreign_or_incomplete_workflow_runs_are_rejected(self):
        for field, value in (
            ("path", ".github/workflows/other.yml"),
            ("event", "pull_request"),
            ("head_branch", "feature"),
            ("head_sha", "b" * 40),
            ("repository", {"full_name": "foreign/repo"}),
            ("head_repository", {"full_name": "foreign/repo"}),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("run_attempt", True),
            ("id", 999),
        ):
            with self.subTest(field=field):
                self.setUp()
                self.run[field] = value
                with self.assertRaises(RuntimeError):
                    verify("123", self.source, self.profile, self.read)

    def test_missing_skipped_duplicate_or_wrong_attempt_jobs_fail(self):
        for defect in (
            "missing",
            "skipped",
            "duplicate",
            "attempt",
            "source",
            "run",
            "paged",
            "extra",
        ):
            with self.subTest(defect=defect):
                self.setUp()
                if defect == "missing":
                    self.jobs["jobs"].pop()
                    self.jobs["total_count"] -= 1
                elif defect == "duplicate":
                    self.jobs["jobs"][-1] = deepcopy(self.jobs["jobs"][0])
                elif defect == "paged":
                    self.jobs["total_count"] += 1
                elif defect == "extra":
                    self.jobs["jobs"].append(self.job("verify / unreviewed", 123))
                    self.jobs["total_count"] += 1
                else:
                    field, value = {
                        "skipped": ("conclusion", "skipped"),
                        "attempt": ("run_attempt", 1),
                        "source": ("head_sha", "b" * 40),
                        "run": ("run_id", 999),
                    }[defect]
                    self.jobs["jobs"][-1][field] = value
                with self.assertRaises(RuntimeError):
                    verify("123", self.source, self.profile, self.read)

    def test_codeql_jobs_and_any_emitted_publisher_result_must_pass(self):
        for defect in (
            "scan",
            "jobs",
            "result",
            "publisher",
            "incomplete",
            "newer_failed",
        ):
            with self.subTest(defect=defect):
                self.setUp()
                if defect == "scan":
                    self.scan["head_sha"] = "b" * 40
                elif defect == "jobs":
                    self.scan_jobs["jobs"][0]["conclusion"] = "skipped"
                elif defect == "result":
                    self.results["check_runs"][0]["conclusion"] = "failure"
                elif defect == "publisher":
                    self.results["check_runs"][0]["app"]["id"] = 1
                elif defect == "incomplete":
                    self.results["total_count"] = 2
                else:
                    self.scans["workflow_runs"].append(
                        {**self.scan, "id": 125, "conclusion": "failure"}
                    )
                    self.scans["total_count"] += 1
                with self.assertRaises(RuntimeError):
                    verify("123", self.source, self.profile, self.read)

    def test_main_without_pr_result_still_requires_both_codeql_analyses(self):
        self.results = {"total_count": 0, "check_runs": []}
        self.scan["event"] = "schedule"
        result = verify("123", self.source, self.profile, self.read)
        self.assertEqual(result["codeql_result"], "not_emitted_for_main")
        self.assertEqual(result["codeql_run"], 124)
        self.scan_jobs["jobs"].pop()
        self.scan_jobs["total_count"] -= 1
        with self.assertRaises(RuntimeError):
            verify("123", self.source, self.profile, self.read)

    def test_metadata_reads_pin_github_host_and_suppress_provider_errors(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from release_verification import api

        with patch("release_verification.subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout='{"id":123}', stderr="")
            self.assertEqual(api("repos/client-example/portal/actions/runs/123"), {"id": 123})
            self.assertEqual(
                run.call_args.args[0],
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "repos/client-example/portal/actions/runs/123",
                ],
            )
            run.return_value = SimpleNamespace(returncode=1, stdout="private", stderr="secret")
            with self.assertRaisesRegex(RuntimeError, "^Verification metadata unavailable$"):
                api("repos/client-example/portal/actions/runs/123")

    def test_image_and_rollout_entrypoints_bind_workflow_and_keep_separate_receipts(
        self,
    ):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        import release_verification as verification

        with tempfile.TemporaryDirectory() as directory:
            for purpose in ("image", "rollout"):
                env = {
                    "GITHUB_REPOSITORY": self.profile["github_repository"],
                    "GITHUB_REF": "refs/heads/main",
                    "GITHUB_SHA": self.source,
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_WORKFLOW_REF": self.profile["github_repository"]
                    + f"/.github/workflows/aws-{purpose}.yml@refs/heads/main",
                    "RUNNER_TEMP": directory,
                    "VERIFICATION_RUN": "123",
                }
                with (
                    patch.dict(os.environ, env, clear=True),
                    patch(
                        "sys.argv",
                        ["verify", "--profile", "fixture", "--purpose", purpose],
                    ),
                    patch.object(verification, "load", return_value=self.profile),
                    patch.object(
                        verification,
                        "verify",
                        return_value={"state": "source_verified"},
                    ) as check,
                ):
                    verification.main()
                    check.assert_called_once_with("123", self.source, self.profile)
                    self.assertTrue((Path(directory) / f"{purpose}-verification.json").is_file())
                    for key, bad in (
                        ("GITHUB_EVENT_NAME", "pull_request"),
                        ("GITHUB_REF", "refs/heads/other"),
                        ("GITHUB_WORKFLOW_REF", "foreign/workflow"),
                    ):
                        with patch.dict(os.environ, {key: bad}):
                            check.reset_mock()
                            with self.assertRaises(RuntimeError):
                                verification.main()
                            check.assert_not_called()


class ScopeTests(unittest.TestCase):
    def test_unknown_application_dependency_and_policy_files_require_full_ci(self):
        from ci_scope import application_input

        for path in (
            "src/app.jsx",
            "backend/app/main.py",
            "backend/migrations/a.py",
            "backend/Dockerfile",
            "package-lock.json",
            "tests-api/a.js",
            ".github/workflows/verify.yml",
            "new-unknown-file",
            "backend/infrastructure/ci_scope.py",
            "backend/infrastructure/release_verification.py",
            "backend/infrastructure/read-schema.sql",
        ):
            self.assertTrue(application_input(path), path)
        for path in (
            "backend/infrastructure/release_maintenance.py",
            "docs/runbook.md",
        ):
            self.assertFalse(application_input(path), path)

    def test_git_fingerprint_covers_mode_path_deletion_and_blob(self):
        from unittest.mock import patch

        from ci_scope import tree_fingerprint

        original = b"100644 blob aaa\tsrc/a.js\0"
        with patch("ci_scope.subprocess.check_output", return_value=original):
            expected = tree_fingerprint("a" * 40)
        for changed in (
            b"100755 blob aaa\tsrc/a.js\0",
            b"100644 blob bbb\tsrc/a.js\0",
            b"100644 blob aaa\tsrc/b.js\0",
        ):
            with patch("ci_scope.subprocess.check_output", return_value=changed):
                self.assertNotEqual(tree_fingerprint("b" * 40), expected)
        with patch(
            "ci_scope.subprocess.check_output",
            return_value=original + b"100644 blob ccc\tdocs/a.md\0",
        ):
            self.assertEqual(tree_fingerprint("b" * 40), expected)
        with patch("ci_scope.subprocess.check_output", return_value=b""):
            with self.assertRaises(RuntimeError):
                tree_fingerprint("b" * 40)

    def test_baseline_requires_recent_full_main_evidence_and_identical_inputs(self):
        from ci_scope import MAX_AGE_SECONDS, baseline

        fixture = VerificationTests()
        fixture.setUp()
        fixture.run["created_at"] = "1970-01-01T00:16:40+00:00"

        def read(path):
            if "pages.yml/runs?branch=main" in path:
                return {"workflow_runs": [deepcopy(fixture.run)]}
            return fixture.read(path)

        def equivalent(old, new):
            self.assertEqual((old, new), ("a" * 40, "b" * 40))
            return True

        result = baseline(
            fixture.profile["github_repository"],
            "b" * 40,
            read,
            now=1001,
            equivalent=equivalent,
        )
        self.assertEqual(result["run_id"], 123)
        for now in (999, 1001 + MAX_AGE_SECONDS):
            self.assertIsNone(
                baseline(
                    fixture.profile["github_repository"],
                    "b" * 40,
                    read,
                    now=now,
                    equivalent=equivalent,
                )
            )
        self.assertIsNone(
            baseline(
                fixture.profile["github_repository"],
                "b" * 40,
                read,
                now=1001,
                equivalent=lambda *_: False,
            )
        )
        fixture.jobs["jobs"][1]["conclusion"] = "skipped"
        self.assertIsNone(
            baseline(
                fixture.profile["github_repository"],
                "b" * 40,
                read,
                now=1001,
                equivalent=equivalent,
            )
        )

    def test_scoped_release_checks_current_jobs_and_independent_baseline(self):
        from unittest.mock import patch

        from ci_scope import APP_JOBS

        fixture = VerificationTests()
        fixture.setUp()
        fixture.jobs["jobs"].append(fixture.job("verify / scope", 123))
        fixture.jobs["total_count"] += 1
        for row in fixture.jobs["jobs"]:
            if row["name"].removeprefix("verify / ") in APP_JOBS:
                row["conclusion"] = "skipped"
        with patch("ci_scope.baseline", return_value={"run_id": 111}) as resolve:
            result = verify("123", fixture.source, fixture.profile, fixture.read)
            self.assertEqual(result["application_baseline"], {"run_id": 111})
            resolve.assert_called_once()
            fixture.jobs["jobs"][0]["conclusion"] = "failure"
            with self.assertRaises(RuntimeError):
                verify("123", fixture.source, fixture.profile, fixture.read)
        fixture.jobs["jobs"][0]["conclusion"] = "success"
        for group in ("browser-profile", "backend-group", "api-browser-shard"):
            names = [
                row
                for row in fixture.jobs["jobs"]
                if row["name"].startswith("verify / " + group + " (")
            ]
            fixture.jobs["jobs"] = [row for row in fixture.jobs["jobs"] if row not in names]
            fixture.jobs["jobs"].append({**names[0], "name": "verify / " + group})
        fixture.jobs["total_count"] = len(fixture.jobs["jobs"])
        with patch("ci_scope.baseline", return_value={"run_id": 111}):
            self.assertEqual(
                verify("123", fixture.source, fixture.profile, fixture.read)["state"],
                "source_verified",
            )
        with patch("ci_scope.baseline", return_value=None):
            with self.assertRaises(RuntimeError):
                verify("123", fixture.source, fixture.profile, fixture.read)

    def test_reuse_aggregate_rejects_unexpected_skips_failures_and_missing_scope(self):
        from ci_scope import aggregate

        needs = {
            "scope": {
                "result": "success",
                "outputs": {"run_application": "false", "baseline_run": "123"},
            },
            "quality": {"result": "success"},
            "unit": {"result": "skipped"},
        }
        aggregate(needs)
        for name, result in (
            ("scope", "failure"),
            ("quality", "skipped"),
            ("unit", "success"),
        ):
            bad = deepcopy(needs)
            bad[name]["result"] = result
            with self.assertRaises(RuntimeError):
                aggregate(bad)
        with self.assertRaises(RuntimeError):
            aggregate({})
