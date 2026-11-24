"""Prove release verification reuse rejects missing, stale and substituted CI evidence."""

import unittest
from copy import deepcopy

from deployment_profile import DEVELOPER
from release_verification import verify


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        self.profile = {**DEVELOPER, "github_repository": "client-example/portal"}
        repo = {"full_name": self.profile["github_repository"]}
        self.run = {
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
        for defect in ("scan", "jobs", "result", "publisher", "incomplete", "newer_failed"):
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
