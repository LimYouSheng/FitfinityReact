"""Offline rejection probes for the current-source release inventory."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from release_readiness import migration_chain, report


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "backend/migrations/versions"
        self.directory.mkdir(parents=True)
        infrastructure = self.root / "backend/infrastructure"
        infrastructure.mkdir()
        (infrastructure / "test-db-migration-contract.json").write_text(
            json.dumps({"revisions": ["old_schema"]})
        )
        (infrastructure / "private-runtime-contract.json").write_text(
            json.dumps({"revision": "b" * 40})
        )

    def write(self, name, revision, parent):
        path = self.directory / name
        path.write_text(f"revision = {revision!r}\ndown_revision = {parent!r}\n")
        return path

    def test_order_and_content_fingerprint(self):
        tail = self.write("a.py", "second", "first")
        self.write("z.py", "first", None)
        chain = migration_chain(self.directory)
        self.assertEqual([item["revision"] for item in chain], ["first", "second"])
        self.assertEqual(chain[-1]["sha256"], hashlib.sha256(tail.read_bytes()).hexdigest())
        tail.write_text(tail.read_text() + "# changed\n")
        self.assertNotEqual(chain[-1]["sha256"], migration_chain(self.directory)[-1]["sha256"])

    def test_missing_parent(self):
        self.write("a.py", "first", "missing")
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_cycle(self):
        self.write("a.py", "first", "second")
        self.write("b.py", "second", "first")
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_branch(self):
        self.write("a.py", "first", None)
        self.write("b.py", "second", "first")
        self.write("c.py", "third", "first")
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_duplicate_and_empty(self):
        with self.assertRaises(ValueError):
            migration_chain(self.directory)
        self.write("a.py", "first", None)
        self.write("b.py", "first", None)
        with self.assertRaises(ValueError):
            migration_chain(self.directory)

    def test_dynamic_declaration_never_executed(self):
        marker = self.root / "executed"
        (self.directory / "a.py").write_text(
            f"revision = open({str(marker)!r}, 'w')\ndown_revision = None\n"
        )
        with self.assertRaises(ValueError):
            migration_chain(self.directory)
        self.assertFalse(marker.exists())

    def test_report_always_holds_and_preserves_historical_contracts(self):
        self.write("a.py", "current", None)
        before = {path: path.read_bytes() for path in self.root.rglob("*.json")}
        result = report(self.root, "a" * 40)
        self.assertEqual(result["deployment_decision"], "HOLD")
        self.assertEqual(result["current_schema_head"], "current")
        self.assertEqual(result["historical_bootstrap_head"], "old_schema")
        self.assertEqual(result["aws_observation"], "not performed")
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertTrue(result["required_before_rollout"])
        self.assertTrue(result["not_established"])

    def test_reject_nonexact_source(self):
        for revision in ["main", "a" * 39, "a" * 41, "$(command)"]:
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                report(self.root, revision)


class RolloutEvidenceTests(unittest.TestCase):
    def setUp(self):
        from deployment_profile import DEVELOPER, identities
        from hosting_frontend import inventory, manifest_hash

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = {
            **DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "resource_prefix": "client-prod",
            "github_repository": "client-example/portal",
        }
        target = identities(self.profile)
        self.profile_hash = target["profile_sha256"]
        files = {
            "package-lock.json": '{"lockfileVersion":3}',
            "backend/Dockerfile": "FROM reviewed-base\n",
            "backend/migrations/versions/first.py": (
                "revision='20260924_0006'\ndown_revision=None\n"
            ),
            "backend/migrations/versions/second.py": (
                "revision='20261101_0052'\ndown_revision='20260924_0006'\n"
            ),
            "backend/app/runtime-grants.json": json.dumps(
                {
                    "schema_revision": "20261101_0052",
                    "tables": {
                        "clients": ["SELECT", "INSERT", "UPDATE"],
                        "alembic_version": ["SELECT"],
                    },
                }
            ),
            "backend/infrastructure/read-schema.sql": (
                "BEGIN READ ONLY; SELECT 'synthetic'; ROLLBACK;\n"
            ),
        }
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.source = {
            "revision": "a" * 40,
            "git_tree_verified": True,
            "files": dict.fromkeys(files, {"mode": "100644"}),
        }
        self.folder = self.root / "frontend"
        self.folder.mkdir()
        for name, content in {
            "index.html": "<!doctype html><p>synthetic</p>",
            "sw.js": "// synthetic",
            "manifest.webmanifest": "{}",
        }.items():
            (self.folder / name).write_text(content)
        manifest = inventory(self.folder)
        self.frontend = {
            "source_sha": "a" * 40,
            "profile_sha256": self.profile_hash,
            "frontend_source": self.source,
            "frontend_source_after_build": self.source,
            "frontend_manifest": manifest,
            "frontend_build": {
                "mode": "api",
                "base_path": "/",
                "api_base_url": "",
                "pwa_verified": True,
                "files": 3,
                "manifest_sha256": manifest_hash(manifest),
            },
            "frontend_dependencies": {
                "npm_ls_passed": True,
                "package_lock_sha256": hashlib.sha256(
                    files["package-lock.json"].encode()
                ).hexdigest(),
            },
        }
        self.image = {
            "revision": "a" * 40,
            "profile_sha256": self.profile_hash,
            "account": "123456789012",
            "region": "eu-west-1",
            "image_digest": "sha256:" + "b" * 64,
            "image_uri": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/client-prod-api@sha256:"
            + "b" * 64,
            "candidate_ready": True,
            "image_published": True,
            "scan_policy_passed": True,
            "source_files": {
                name: hashlib.sha256(content.encode()).hexdigest()
                for name, content in files.items()
                if name.startswith("backend/")
            },
        }
        self.upgrade = {
            "state": "upgraded",
            "identity": {
                "FitfinitySource": "a" * 40,
                "FitfinityProfile": self.profile_hash,
                "FitfinityOperation": "c" * 32,
                "FitfinityTemplate": "d" * 64,
            },
            "result": {
                "source_sha": "a" * 40,
                "operation_id": "c" * 32,
                "from_revision": "20260924_0006",
                "schema": "20261101_0052",
                "outcome": "upgraded",
            },
        }
        permissions = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
        self.probe = {
            "state": "observed",
            "source_sha": "a" * 40,
            "profile_sha256": self.profile_hash,
            "receipt": {
                "source_sha": "a" * 40,
                "sql_sha256": hashlib.sha256(
                    files["backend/infrastructure/read-schema.sql"].encode()
                ).hexdigest(),
                "catalog": {
                    "observed_at": "1970-01-01T00:16:30+00:00",
                    "database": "fitfinity",
                    "database_user": "fitfinity_migrator",
                    "transaction_read_only": "on",
                    "alembic_revisions": ["20261101_0052"],
                    "tables": [
                        {
                            "name": name,
                            "owner": "fitfinity_migrator",
                            "row_security": False,
                            "force_row_security": False,
                            "runtime_privileges": {priv: priv in actions for priv in permissions},
                        }
                        for name, actions in {
                            "clients": {"SELECT", "INSERT", "UPDATE"},
                            "alembic_version": {"SELECT"},
                        }.items()
                    ],
                    "roles": [
                        {
                            "name": name,
                            "superuser": False,
                            "create_role": False,
                            "create_database": False,
                            "bypass_row_security": False,
                            "login": True,
                            "database_connect": True,
                            "schema_usage": True,
                        }
                        for name in ("fitfinity_app", "fitfinity_migrator")
                    ],
                },
            },
        }

    def check(self):
        from release_evidence import validate

        return validate(
            self.frontend,
            self.folder,
            self.image,
            self.upgrade,
            self.probe,
            repo=self.root,
            source_inventory=self.source,
            profile=self.profile,
            database="fitfinity",
            schema_action="upgrade",
            now=1000,
        )

    def test_matching_artifacts_remain_hold_until_live_scan_upload_and_rollout(self):
        result = self.check()
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["schema"], "20261101_0052")
        self.assertEqual(result["image_digest"], "sha256:" + "b" * 64)
        self.assertEqual(
            result["frontend_prefix"], "releases/" + "a" * 40 + "/" + result["frontend_sha256"]
        )
        self.assertIn("Fresh live image scan", result["remaining"])
        self.assertEqual(result["required_image_files"], self.image["source_files"])

    def test_frontend_bytes_mode_source_or_lock_drift_are_rejected(self):
        from copy import deepcopy

        original = deepcopy(self.frontend)
        for failure in ("mode", "source", "profile", "lock", "files"):
            self.frontend = deepcopy(original)
            if failure == "mode":
                self.frontend["frontend_build"]["mode"] = "demo"
            elif failure == "source":
                self.frontend["source_sha"] = "0" * 40
            elif failure == "profile":
                self.frontend["profile_sha256"] = "0" * 64
            elif failure == "lock":
                self.frontend["frontend_dependencies"]["package_lock_sha256"] = "0" * 64
            else:
                self.frontend["frontend_manifest"].pop("sw.js")
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                self.check()
        self.frontend = original
        (self.folder / "index.html").write_text("changed")
        with self.assertRaisesRegex(RuntimeError, "Frontend bytes"):
            self.check()

    def test_old_foreign_unpublished_or_incomplete_image_is_rejected(self):
        from copy import deepcopy

        original = deepcopy(self.image)
        for field, value in (
            ("revision", "0" * 40),
            ("account", "000000000000"),
            ("region", "ap-southeast-1"),
            ("image_published", False),
            ("scan_policy_passed", False),
            ("source_files", {}),
        ):
            self.image = {**deepcopy(original), field: value}
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.check()
        self.image = original
        (self.root / "backend/Dockerfile").write_text("changed runtime")
        with self.assertRaisesRegex(RuntimeError, "backend file inventory"):
            self.check()

    def test_uncertain_upgrade_and_stale_foreign_or_wrong_schema_catalog_are_rejected(self):
        from copy import deepcopy

        self.upgrade["state"] = "invoke_submitted"
        with self.assertRaises(RuntimeError):
            self.check()
        self.upgrade["state"] = "upgraded"
        original = deepcopy(self.probe)
        for key, value in (
            ("database", "foreign"),
            ("observed_at", "1970-01-01T01:00:00+00:00"),
            ("observed_at", "1969-12-31T00:00:00+00:00"),
            ("alembic_revisions", ["20260924_0006"]),
        ):
            self.probe = deepcopy(original)
            self.probe["receipt"]["catalog"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                self.check()
        self.probe = original
        self.probe["receipt"]["sql_sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.check()

    def test_catalog_must_match_exact_tables_roles_and_runtime_privileges(self):
        from copy import deepcopy

        original = deepcopy(self.probe)
        for failure in (
            "missing",
            "duplicate",
            "extra-grant",
            "missing-grant",
            "rls",
            "elevated-role",
            "unknown-privilege",
        ):
            self.probe = deepcopy(original)
            catalog = self.probe["receipt"]["catalog"]
            if failure == "missing":
                catalog["tables"].pop()
            elif failure == "duplicate":
                catalog["tables"].append(deepcopy(catalog["tables"][0]))
            elif failure == "extra-grant":
                catalog["tables"][0]["runtime_privileges"]["DELETE"] = True
            elif failure == "missing-grant":
                catalog["tables"][0]["runtime_privileges"]["SELECT"] = False
            elif failure == "rls":
                catalog["tables"][0]["row_security"] = True
            elif failure == "elevated-role":
                catalog["roles"][0]["superuser"] = True
            else:
                catalog["tables"][0]["runtime_privileges"]["INSERT"] = None
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                self.check()

    def test_code_only_release_requires_explicit_unchanged_schema_and_fresh_grants(self):
        from release_evidence import validate

        args = dict(
            repo=self.root,
            source_inventory=self.source,
            profile=self.profile,
            database="fitfinity",
            schema_action="unchanged",
            now=1000,
        )
        result = validate(self.frontend, self.folder, self.image, None, self.probe, **args)
        self.assertEqual(result["schema_action"], "unchanged")
        self.assertEqual(result["decision"], "HOLD")
        with self.assertRaises(RuntimeError):
            validate(self.frontend, self.folder, self.image, self.upgrade, self.probe, **args)
        self.probe["receipt"]["catalog"]["alembic_revisions"] = ["20260924_0006"]
        with self.assertRaises(RuntimeError):
            validate(self.frontend, self.folder, self.image, None, self.probe, **args)


class FrontendTransferTests(unittest.TestCase):
    def setUp(self):
        from deployment_profile import identities
        from hosting_frontend import inventory, manifest_hash

        RolloutEvidenceTests.setUp(self)
        self.target = identities(self.profile)
        self.stack = "arn:aws:cloudformation:eu-west-1:123456789012:stack/client-prod-login/abcdef"
        self.review = dict(
            source_sha="a" * 40,
            profile_sha256=self.profile_hash,
            manifest_sha256=manifest_hash(inventory(self.folder)),
            stack_arn=self.stack,
            expires_at=2000,
        )
        self.remote = {}
        self.receipts = []
        self.writes = []
        self.lose_response = False
        self.clock = 1000
        self.foreign = False

    def call(self, service, action, args):
        if action == "get-caller-identity":
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/client-prod-github-hosting/test",
            }
        if action == "describe-stacks":
            return {"Stacks": [{"StackId": self.stack, "StackStatus": "UPDATE_COMPLETE"}]}
        if action == "describe-stack-resource":
            return {
                "StackResourceDetail": {
                    "StackId": self.stack if not self.foreign else "foreign",
                    "LogicalResourceId": "FrontendBucket",
                    "ResourceType": "AWS::S3::Bucket",
                    "ResourceStatus": "CREATE_COMPLETE",
                    "PhysicalResourceId": "owned-client-site",
                }
            }
        self.assertEqual(service, "s3api")
        self.assertEqual(args["ExpectedBucketOwner"], "123456789012")
        self.assertEqual(args["Bucket"], "owned-client-site")
        if action == "head-object":
            return self.remote.get(args["Key"])
        self.assertEqual(action, "put-object")
        self.assertEqual(args["IfNoneMatch"], "*")
        self.assertNotIn(args["Key"], self.remote)
        self.assertEqual(self.receipts[-1]["objects"][args["Key"].split("/")[-1]], "submitted")
        self.writes.append(args)
        self.remote[args["Key"]] = {
            "ContentLength": len(args["Body"]),
            **{
                k: args[k]
                for k in ("ChecksumSHA256", "ContentType", "CacheControl", "ServerSideEncryption")
            },
        }
        if self.lose_response:
            raise RuntimeError("lost response")
        return {}

    def run_transfer(self, **kwargs):
        from release_frontend import transfer

        return transfer(
            self.review,
            self.folder,
            self.profile,
            self.call,
            self.receipts.append,
            clock=lambda: self.clock,
            **kwargs,
        )

    def test_exact_objects_verified_and_repeat_never_writes(self):
        result = self.run_transfer()
        self.assertEqual(result["state"], "verified")
        self.assertEqual(len(self.writes), 3)
        self.clock = 3000
        self.assertEqual(self.run_transfer(prior=result, inspect=True), result)
        self.assertEqual(len(self.writes), 3)

    def test_lost_response_recovers_by_observation_without_replaying_put(self):
        self.lose_response = True
        with self.assertRaisesRegex(RuntimeError, "lost response"):
            self.run_transfer()
        prior = self.receipts[-1]
        self.lose_response = False
        result = self.run_transfer(prior=prior)
        self.assertEqual(result["state"], "verified")
        self.assertEqual(len(self.writes), 3)
        self.assertEqual(len({r["Key"] for r in self.writes}), 3)

    def test_absent_uncertain_object_is_never_blindly_replayed(self):
        self.lose_response = True
        with self.assertRaises(RuntimeError):
            self.run_transfer()
        self.remote.clear()
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.run_transfer(prior=self.receipts[-1])
        self.assertEqual(len(self.writes), 1)

    def test_expired_review_and_foreign_bucket_never_write(self):
        self.clock = 3000
        with self.assertRaisesRegex(RuntimeError, "expired"):
            self.run_transfer()
        self.clock = 1000
        self.foreign = True
        with self.assertRaisesRegex(RuntimeError, "Owned frontend"):
            self.run_transfer()
        self.assertFalse(self.writes)

    def test_changed_remote_content_is_not_overwritten(self):
        result = self.run_transfer()
        next(iter(self.remote.values()))["ChecksumSHA256"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "overwrite refused"):
            self.run_transfer(prior=result)
        self.assertEqual(len(self.writes), 3)

    def test_journal_failure_prevents_put_and_inspection_never_writes(self):
        from release_frontend import transfer

        with self.assertRaisesRegex(RuntimeError, "inspection never uploads"):
            self.run_transfer(inspect=True)

        def fail(_):
            raise OSError("disk full")

        with self.assertRaises(OSError):
            transfer(self.review, self.folder, self.profile, self.call, fail, clock=lambda: 1000)
        self.assertFalse(self.writes)

    def test_changed_artifact_and_receipt_identity_fail_before_provider_calls(self):
        from copy import deepcopy
        from unittest.mock import Mock

        from release_frontend import transfer

        caller = Mock()
        prior = {"identity": {**self.review, "source_sha": "b" * 40}, "objects": {}}
        with self.assertRaisesRegex(RuntimeError, "Original frontend receipt"):
            transfer(
                self.review,
                self.folder,
                self.profile,
                caller,
                self.receipts.append,
                prior=prior,
                clock=lambda: 1000,
            )
        changed = deepcopy(self.review)
        (self.folder / "index.html").write_text("different frontend")
        with self.assertRaisesRegex(RuntimeError, "artifact changed"):
            transfer(
                changed, self.folder, self.profile, caller, self.receipts.append, clock=lambda: 1000
            )
        caller.assert_not_called()

    def test_expiry_during_journalling_prevents_write(self):
        from release_frontend import transfer

        def persist(receipt):
            self.receipts.append(receipt)
            self.clock = 3000

        with self.assertRaisesRegex(RuntimeError, "expired"):
            transfer(
                self.review, self.folder, self.profile, self.call, persist, clock=lambda: self.clock
            )
        self.assertTrue(self.receipts)
        self.assertFalse(self.writes)


class ArtifactCollectionTests(unittest.TestCase):
    def setUp(self):
        RolloutEvidenceTests.setUp(self)
        self.destination = self.root.parent / (self.root.name + "-artifacts")
        import shutil

        self.addCleanup(shutil.rmtree, self.destination, True)
        self.runs = {"frontend": "101", "image": "102", "catalog": "103", "upgrade": "104"}
        self.downloads = []
        self.bad_kind = None
        self.bad_fields = {}

    def metadata(self, command, **kwargs):
        run_id = command[-1].rsplit("/", 1)[-1]
        kind = next(k for k, v in self.runs.items() if v == run_id)
        workflow = {
            "frontend": "aws-release-prepare",
            "image": "aws-image",
            "catalog": "aws-schema-probe",
            "upgrade": "aws-schema-upgrade",
        }[kind]
        data = {
            "path": f".github/workflows/{workflow}.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": "client-example/portal"},
            "status": "completed",
            "conclusion": "success",
            "head_sha": "a" * 40,
            "run_attempt": 2,
        }
        if kind == self.bad_kind:
            data.update(self.bad_fields)
        return json.dumps(data)

    def download(self, command, **kwargs):
        import shutil

        self.downloads.append(command)
        folder = Path(command[command.index("--dir") + 1])
        folder.mkdir()
        kind = folder.name
        names = {
            "frontend": "release-readiness.json",
            "image": "fitfinity-image-candidate.json",
            "catalog": "schema-probe-receipt.json",
            "upgrade": "schema-upgrade-receipt.json",
        }
        values = {
            "frontend": self.frontend,
            "image": self.image,
            "catalog": self.probe,
            "upgrade": self.upgrade,
        }
        (folder / names[kind]).write_text(json.dumps(values[kind]))
        if kind == "frontend":
            shutil.copytree(self.folder, folder / "release-frontend/dist-api-test")

    def collect(self, schema_action="upgrade"):
        from unittest.mock import patch

        from release_artifacts import collect

        runs = (
            self.runs
            if schema_action == "upgrade"
            else {k: v for k, v in self.runs.items() if k != "upgrade"}
        )
        with (
            patch("release_artifacts.source_check", return_value=self.source),
            patch("schema_probe_artifacts.subprocess.check_output", side_effect=self.metadata),
            patch("schema_probe_artifacts.subprocess.run", side_effect=self.download),
        ):
            return collect(
                self.root,
                self.destination,
                runs,
                source="a" * 40,
                profile=self.profile,
                database="fitfinity",
                schema_action=schema_action,
                clock=lambda: 1000,
            )

    def test_real_binding_and_content_checks_accept_only_matching_producers(self):
        result = self.collect()
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["producer_runs"], self.runs)
        self.assertEqual(len(self.downloads), 4)
        self.assertTrue(all("client-example/portal" in command for command in self.downloads))
        self.assertTrue(
            all(command[command.index("--name") + 1].endswith("-2") for command in self.downloads)
        )

    def test_each_failed_producer_is_rejected_even_if_it_retained_an_artifact(self):
        import shutil

        for kind in self.runs:
            self.bad_kind = kind
            self.bad_fields = {"conclusion": "failure"}
            self.downloads.clear()
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.collect()
            self.assertFalse(any(command[3] == self.runs[kind] for command in self.downloads))
            shutil.rmtree(self.destination)

    def test_foreign_branch_event_repository_workflow_and_source_are_rejected(self):
        import shutil

        self.bad_kind = "catalog"
        for fields in (
            {"head_sha": "b" * 40},
            {"head_branch": "feature"},
            {"event": "pull_request"},
            {"path": ".github/workflows/other.yml"},
            {"head_repository": {"full_name": "foreign/project"}},
            {"status": "in_progress"},
        ):
            self.bad_fields = fields
            with self.subTest(fields=fields), self.assertRaises(RuntimeError):
                self.collect()
            self.assertFalse(self.downloads)
            shutil.rmtree(self.destination)

    def test_code_only_release_fetches_no_upgrade_and_still_checks_schema(self):
        result = self.collect("unchanged")
        self.assertEqual(result["schema_action"], "unchanged")
        self.assertEqual(len(self.downloads), 3)
        self.assertNotIn("upgrade", result["producer_runs"])

    def test_code_only_release_requires_runtime_login_database_connect_and_schema_usage(self):
        from unittest.mock import patch

        roles = self.probe["receipt"]["catalog"]["roles"]
        runtime = next(row for row in roles if row["name"] == "fitfinity_app")
        destinations = self.destination
        for field in ("login", "database_connect", "schema_usage"):
            for value in (False, None, 1):
                with self.subTest(field=field, value=value), patch.dict(runtime):
                    self.destination = destinations / f"{field}-{value}"
                    if value is None:
                        del runtime[field]
                    else:
                        runtime[field] = value
                    with self.assertRaisesRegex(RuntimeError, "runtime login, database CONNECT"):
                        self.collect("unchanged")

    def test_existing_destination_preserves_earlier_evidence_without_download(self):
        self.destination.mkdir()
        (self.destination / "receipt").write_text("original")
        with self.assertRaisesRegex(RuntimeError, "new artifact directory"):
            self.collect()
        self.assertEqual((self.destination / "receipt").read_text(), "original")
        self.assertFalse(self.downloads)


if __name__ == "__main__":
    unittest.main()
