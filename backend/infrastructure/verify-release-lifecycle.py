"""Exercise release handoffs on one synthetic client stack, database and object store."""

import json
import shutil
import time
import unittest
from copy import deepcopy
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import resumption_operator
import rollout_operator
from deployment_profile import identities
from hosting_frontend import inventory, manifest_hash
from release_access import service_role_arn
from release_artifacts import collect
from release_evidence import file_hash
from release_observation import digest
from release_plan import prepare
from schema_upgrade_plan import prepare as prepare_upgrade

BACKEND = Path(__file__).resolve().parents[1]
START = "20260924_0006"
HEAD = "20261101_0052"


def stamped(seconds):
    return datetime.fromtimestamp(seconds, UTC).isoformat()


class LifecycleTests(unittest.TestCase):
    def fixture(self, module, name):
        case = getattr(import_module(module), name)()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def setUp(self):
        self.now = int(time.time())
        self.worker = self.fixture("verify-schema-upgrade-plan", "UpgradeExecutionTests")
        self.upgrade_files = set(self.worker.image["source_files"])
        self.profile = self.worker.profile
        self.target = identities(self.profile)
        self.maintenance = self.fixture("verify-release-plan", "MaintenanceTests")
        self.host = self.fixture("verify-release-execution", "ExecutionTests")
        self.host.use_client_profile()
        self.host.profile, self.host.target = self.profile, self.target
        self.host.stack["RoleARN"] = service_role_arn(self.profile)
        self.host.current_template, self.features = import_module(
            "verify-release-features"
        ).fixture(self.profile)
        self.host.concurrency = 2
        self.host.function["Tags"] = {"Keep": "owned-by-another-service"}
        self.host.resources["StackResourceSummaries"].append(
            {
                "LogicalResourceId": "RuntimeBoundary",
                "ResourceType": "AWS::IAM::ManagedPolicy",
                "PhysicalResourceId": (
                    "arn:aws:iam::123456789012:policy/client-prod-hosting-api-boundary"
                ),
            }
        )
        self.store = self.fixture("verify-release-readiness", "FrontendTransferTests")
        self.store.stack = self.host.stack["StackId"]
        self.store.receipts = self.host.receipts
        self.schema = START
        self.operations, self.public_reads = [], []

    def pause(self, source, operation, *, snapshot):
        state = self.maintenance
        state.profile, state.target = self.profile, self.target
        state.tags = self.host.function["Tags"]
        state.concurrency = self.host.concurrency
        state.host_template = deepcopy(self.host.current_template)
        state.review.update(
            profile_sha256=self.target["profile_sha256"],
            operation_id=operation,
            source_sha=source,
            expires_at=self.now + 600,
            function_revision=state.revision,
            hosting_stack_arn=state.host_stack,
            hosting_template_sha256=digest(state.host_template),
        )
        provider = state.call

        def call(service, action, args):
            result = provider(service, action, args)
            if action == "describe-stacks":
                result["Stacks"][0]["RoleARN"] = self.host.stack["RoleARN"]
            if action == "create-db-snapshot":
                state.snapshot.update(
                    Engine="postgres",
                    SnapshotCreateTime=stamped(self.now),
                    TagList=deepcopy(state.backup_tags),
                )
            return result

        with patch.object(state, "call", call):
            paused = state.step("inspect", state.step("pause", now=self.now), now=self.now)
            created = state.step("record-pause-create", paused, now=self.now)
            submitted = state.step("record-pause-execute", created, now=self.now)
            paused = state.step("record-pause-verify", submitted, now=self.now)
            self.assertEqual(paused["pause_record"]["state"], "template_verified")
            self.now += 31
            if snapshot:
                submitted = state.step("snapshot", paused, now=self.now)
                paused = state.step("snapshot-check", submitted, now=self.now)
                self.assertEqual(paused["state"], "snapshot_ready")
        self.host.current_template = deepcopy(state.host_template)
        self.host.concurrency = state.concurrency
        self.assertEqual(self.host.concurrency, 0)
        self.assertEqual(
            self.host.current_template["Resources"]["ApiFunction"]["Properties"][
                "ReservedConcurrentExecutions"
            ],
            0,
        )
        return paused

    def prepare_artifacts(self, source, image_digest, content):
        """Publish fixture bytes for one revision, including the actual schema and grant files."""
        bundle = self.fixture("verify-release-readiness", "ArtifactCollectionTests")
        bundle.profile = self.profile
        for path in (bundle.root / "backend/migrations/versions").glob("*.py"):
            path.unlink()
        names = self.upgrade_files | {
            "backend/Dockerfile",
            "backend/infrastructure/read-schema.sql",
            "backend/app/api/email_changes.py",
        }
        for name in names:
            path = bundle.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BACKEND / Path(name).relative_to("backend"), path)
        # Isolate the code/UI change from the real migration and correction-aware code inventory.
        (bundle.root / "backend/app/release_label.py").write_text(f"TITLE = {content!r}\n")
        (bundle.folder / "index.html").write_text(f"<!doctype html><title>{content}</title>")
        names.add("backend/app/release_label.py")
        files = {name: file_hash(bundle.root / name) for name in names}
        bundle.source.update(
            revision=source,
            files=dict.fromkeys([*names, "package-lock.json"], {"mode": "100644"}),
        )
        manifest = inventory(bundle.folder)
        bundle.frontend.update(
            source_sha=source,
            profile_sha256=self.target["profile_sha256"],
            frontend_source=bundle.source,
            frontend_source_after_build=bundle.source,
            frontend_manifest=manifest,
        )
        bundle.frontend["frontend_build"]["manifest_sha256"] = manifest_hash(manifest)
        bundle.image.update(
            revision=source,
            profile_sha256=self.target["profile_sha256"],
            image_digest=image_digest,
            image_uri=self.target["registry"] + "/client-prod-api@" + image_digest,
            source_files=files,
        )
        bundle.probe.update(source_sha=source, profile_sha256=self.target["profile_sha256"])
        bundle.probe["receipt"].update(
            source_sha=source, sql_sha256=files["backend/infrastructure/read-schema.sql"]
        )
        grants = json.loads((bundle.root / "backend/app/runtime-grants.json").read_text())
        catalog = bundle.probe["receipt"]["catalog"]
        privileges = tuple(catalog["tables"][0]["runtime_privileges"])
        catalog["tables"] = [
            {
                "name": table,
                "owner": "fitfinity_migrator",
                "row_security": False,
                "force_row_security": False,
                "runtime_privileges": {action: action in allowed for action in privileges},
            }
            for table, allowed in grants["tables"].items()
        ]
        return bundle

    def upgrade(self, bundle, backup):
        worker = self.worker
        worker.binding["expires_at"] = self.now + 600
        worker.review = prepare_upgrade(
            worker.binding, profile=self.profile, source_sha=bundle.source["revision"], now=self.now
        )
        worker.tags["FitfinityTemplate"] = worker.review["template_sha256"]
        worker.image = bundle.image
        worker.evidence["snapshot_arn"] = backup["snapshot_arn"]
        worker.evidence["maintenance"] = backup
        worker.evidence["catalog"].update(
            observed_at=stamped(self.now - 32), alembic_revisions=[self.schema]
        )
        provider = worker.call

        def call(service, action, args):
            if action == "describe-db-snapshots":
                self.assertEqual(args["DBSnapshotIdentifier"], backup["snapshot_arn"])
                return self.maintenance.call(service, action, args)
            if action == "get-template" and args.get("StackName") == self.maintenance.host_stack:
                return {"TemplateBody": deepcopy(self.host.current_template)}
            if (
                action in {"get-function", "get-function-concurrency"}
                and args.get("FunctionName") == self.target["runtime_function"]
            ):
                return self.host.call(service, action, args)
            result = provider(service, action, args)
            if action == "describe-db-instances":
                result["DBInstances"][0]["DbiResourceId"] = self.maintenance.review[
                    "database_resource_id"
                ]
            if action == "describe-image-scan-findings":
                result["imageScanFindings"]["imageScanCompletedAt"] = stamped(self.now - 1)
            if action == "invoke":
                self.assertEqual(self.schema, START)
                self.schema = result["Payload"]["schema"]
            return result

        with patch.object(worker, "call", call):
            created = worker.run_mode("create", now=self.now)
            verified = worker.run_mode("inspect", created, now=self.now)
            result = worker.run_mode("invoke", verified, now=self.now)
        self.assertEqual(result["state"], "upgraded")
        self.assertEqual(self.schema, HEAD)
        return result

    def collect(self, bundle):
        source = bundle.source["revision"]
        catalog = bundle.probe["receipt"]["catalog"]
        catalog.update(observed_at=stamped(self.now), alembic_revisions=[self.schema])
        action = "upgrade" if bundle.upgrade else "unchanged"
        runs = {k: v for k, v in bundle.runs.items() if k != "upgrade" or bundle.upgrade}

        def metadata(command, **kwargs):
            run = json.loads(bundle.metadata(command, **kwargs))
            run["head_sha"] = source
            return json.dumps(run)

        with (
            patch("release_artifacts.source_check", return_value=bundle.source),
            patch("schema_probe_artifacts.subprocess.check_output", side_effect=metadata),
            patch("schema_probe_artifacts.subprocess.run", side_effect=bundle.download),
        ):
            return collect(
                bundle.root,
                bundle.destination,
                runs,
                source=source,
                profile=self.profile,
                database="fitfinity",
                schema_action=action,
                clock=lambda: self.now,
            )

    def deploy(self, bundle, evidence, operation, resumption, *, activate, batched=False):
        host = self.host
        original = deepcopy(host.current_template)
        source = bundle.source["revision"]
        feature_args = {"feature_values": self.features} if activate else {}
        package = prepare(
            original,
            observed_template_sha256=digest(original),
            source_sha=source,
            image_digest=bundle.image["image_digest"],
            frontend_sha256=evidence["frontend_sha256"],
            profile=self.profile,
            **feature_args,
        )
        candidate = package["candidate_template"]
        meta = {
            "source_sha": source,
            "profile_sha256": self.target["profile_sha256"],
            "operation_id": operation,
            "expires_at": self.now + 600,
            "stack_arn": host.stack["StackId"],
            "maintenance_marker": host.function["Tags"]["FitfinityMaintenance"],
            "original_template_sha256": digest(original),
            "candidate_template_sha256": digest(candidate),
            **feature_args,
        }
        host.review.update(
            source_sha=source,
            operation_id=operation,
            mode="rollout",
            original_template=original,
            candidate_template=candidate,
            boundary_resource="RuntimeBoundary" if activate else None,
            maintenance_marker=meta["maintenance_marker"],
            expires_at=meta["expires_at"],
            profile_sha256=meta["profile_sha256"],
        )
        host.stack["Outputs"] = [
            {"OutputKey": key, "OutputValue": value}
            for key, value in (
                ("FrontendDomain", "client123.cloudfront.net"),
                ("DistributionId", "D123"),
                ("FunctionVersion", "9"),
            )
        ]

        def call(service, action, args):
            self.operations.append((service, action))
            resources = host.current_template["Resources"]
            config = resources["ApiFunction"]["Properties"]
            distribution = resources["Distribution"]["Properties"]["DistributionConfig"]
            if service == "s3api" or (
                action == "describe-stack-resource"
                and args["LogicalResourceId"] == "FrontendBucket"
            ):
                return self.store.call(service, action, args)
            if action == "describe-image-scan-findings":
                self.assertEqual(args["imageId"]["imageDigest"], bundle.image["image_digest"])
                return {
                    "registryId": self.target["account"],
                    "repositoryName": self.target["image_repository"],
                    "imageId": args["imageId"],
                    "imageScanStatus": {"status": "COMPLETE"},
                    "imageScanFindings": {
                        "findingSeverityCounts": {},
                        "findings": [],
                        "imageScanCompletedAt": stamped(self.now),
                    },
                }
            if action == "get-distribution":
                return {
                    "Distribution": {
                        "ARN": "arn:aws:cloudfront::123456789012:distribution/D123",
                        "DomainName": "client123.cloudfront.net",
                        "Status": "Deployed",
                        "DistributionConfig": {
                            "Enabled": True,
                            "Origins": {"Items": distribution["Origins"]},
                        },
                    }
                }
            if action == "get-alias":
                self.assertEqual(args["Name"], self.target["runtime_alias"])
                return {"FunctionVersion": "9"}
            if action == "get-function" and args.get("Qualifier"):
                return {
                    "Configuration": {"Version": "9"},
                    "Code": {"ResolvedImageUri": config["Code"]["ImageUri"]},
                }
            if action == "untag-resource":
                self.assertTrue(host.receipts[-1]["finalization_requested"])
                for key in args["TagKeys"]:
                    del host.function["Tags"][key]
                return {}
            return host.call(service, action, args)

        def read(url):
            path = url.removeprefix("https://client123.cloudfront.net/")
            self.public_reads.append(path)
            if path == "index.html":
                wanted = evidence["frontend_prefix"] + "/index.html"
                return next(row["Body"] for row in self.store.writes if row["Key"] == wanted)
            self.assertIn(path, {"health/live", "health/ready"})
            self.assertEqual(host.concurrency, 2)
            self.assertEqual(self.schema, HEAD)
            return b'{"status":"alive"}' if path == "health/live" else b'{"status":"ready"}'

        def step(mode, prior=None, persist=None):
            def save(value):
                host.receipts.append(value)
                if persist is not None:
                    persist(value)

            resume = mode in resumption_operator.MODES
            with patch("time.time", return_value=self.now), patch("release_health.read_url", read):
                (resumption_operator if resume else rollout_operator).execute_step(
                    mode,
                    resume_meta if resume else meta,
                    evidence,
                    bundle.destination,
                    call,
                    save,
                    profile=self.profile,
                    prior=prior,
                    **({"verified": verified} if resume else {}),
                )
            return deepcopy(host.receipts[-1])

        if batched:
            from release_milestones import rollout_milestone

            verified = rollout_milestone("deploy", step, lambda value: None, clock=lambda: self.now)
        else:
            uploaded = step("upload")
            self.assertEqual(uploaded["state"], "verified")
            self.assertTrue(all(value == "verified" for value in uploaded["objects"].values()))
            self.assertEqual(step("upload-inspect", uploaded)["objects"], uploaded["objects"])
            created = step("create")
            host.uncertain = "execute-change-set"
            with self.assertRaisesRegex(TimeoutError, "lost execute"):
                step("execute", created)
            submitted = deepcopy(host.receipts[-1])
            observed = step("inspect", submitted)
            host.uncertain = None
            verified = step("verify", observed)
        self.assertEqual(verified["state"], "template_verified")
        self.assertEqual(host.concurrency, 0)
        self.assertEqual(verified["evidence"], evidence)
        with self.assertRaisesRegex(RuntimeError, "Original review"):
            step("verify", {**verified, "review_sha256": "0" * 64})
        resume_meta = {
            **meta,
            "resumption": {
                "operation_id": resumption,
                "expires_at": self.now + 600,
                "concurrency": 2,
                "verified_run": "105",
            },
        }
        resumed = deepcopy(candidate)
        resumed["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"] = 2
        host.review.update(
            mode="resume",
            operation_id=resumption,
            original_template=candidate,
            candidate_template=resumed,
            boundary_resource=None,
        )
        if batched:
            finalized = rollout_milestone(
                "resume", step, lambda value: None, clock=lambda: self.now
            )
        else:
            created = step("resume-create")
            submitted = step("resume-execute", created)
            active = step("resume-verify", submitted)
            healthy = step("resume-health", active)
            self.assertEqual(healthy["health"]["state"], "health_verified")
            finalized = step("resume-finalize-inspect", step("resume-finalize", healthy))
        self.assertEqual(finalized["state"], "maintenance_finalized")
        self.assertEqual(host.function["Tags"], {"Keep": "owned-by-another-service"})
        self.assertEqual(host.current_template, resumed)
        self.assertEqual(host.concurrency, 2)
        self.assertNotIn('"Environment"', json.dumps(host.receipts))
        return verified

    def test_upgrade_feature_release_then_reviewed_code_rollback_keeps_current_schema(self):
        previous = self.prepare_artifacts("9" * 40, "sha256:" + "a" * 64, "prior view")
        old_manifest = previous.frontend["frontend_build"]["manifest_sha256"]
        origins = self.host.current_template["Resources"]["Distribution"]["Properties"][
            "DistributionConfig"
        ]["Origins"]
        next(row for row in origins if row["Id"] == "frontend")["OriginPath"] = (
            "/releases/" + previous.source["revision"] + "/" + old_manifest
        )
        bundle = self.prepare_artifacts("a" * 40, "sha256:" + "b" * 64, "updated view")
        backup = self.pause("a" * 40, "b" * 32, snapshot=True)
        bundle.upgrade = self.upgrade(bundle, backup)
        evidence = self.collect(bundle)
        self.assertEqual(evidence["schema_action"], "upgrade")
        self.deploy(bundle, evidence, "d" * 32, "e" * 32, activate=True)
        first_template = deepcopy(self.host.current_template)
        self.assertEqual(sum(op == "invoke" for op, _ in self.worker.calls), 1)
        worker_calls = deepcopy(self.worker.calls)

        rollback = self.prepare_artifacts("f" * 40, "sha256:" + "8" * 64, "prior view")
        rollback.upgrade = None
        self.pause("f" * 40, "1" * 32, snapshot=False)
        changed_file = "backend/app/release_label.py"
        self.assertNotEqual(
            bundle.image["source_files"][changed_file], previous.image["source_files"][changed_file]
        )
        self.assertEqual(
            rollback.image["source_files"][changed_file],
            previous.image["source_files"][changed_file],
        )
        self.assertEqual(rollback.frontend["frontend_build"]["manifest_sha256"], old_manifest)
        data_files = {
            name: value
            for name, value in bundle.image["source_files"].items()
            if name != "backend/app/release_label.py"
        }
        self.assertTrue(all(rollback.image["source_files"][k] == v for k, v in data_files.items()))
        evidence = self.collect(rollback)
        self.assertEqual(evidence["schema_action"], "unchanged")
        self.assertNotIn("upgrade", evidence["producer_runs"])
        self.deploy(rollback, evidence, "2" * 32, "3" * 32, activate=False)
        deployed = self.host.current_template["Resources"]
        self.assertEqual(
            deployed["ApiFunction"]["Properties"]["Code"]["ImageUri"], rollback.image["image_uri"]
        )
        self.assertTrue(first_template["Resources"].keys() < deployed.keys())
        self.assertEqual(
            deployed["ApiFunction"]["Properties"]["Environment"]["Variables"][
                "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED"
            ],
            "true",
        )
        self.assertEqual(self.schema, HEAD)
        self.assertEqual(self.worker.calls, worker_calls)
        self.assertEqual(len(self.store.writes), 6)
        self.assertFalse(any(service == "rds" for service, _ in self.operations))
        self.assertEqual(self.operations.count(("cloudformation", "execute-change-set")), 4)
        self.assertEqual(self.public_reads, ["index.html", "health/live", "health/ready"] * 4)

    def test_batched_release_and_resume_use_real_owners_and_preserve_schema(self):
        self.schema = HEAD
        bundle = self.prepare_artifacts("a" * 40, "sha256:" + "b" * 64, "milestone view")
        bundle.upgrade = None
        self.pause("a" * 40, "b" * 32, snapshot=False)
        evidence = self.collect(bundle)
        self.deploy(bundle, evidence, "d" * 32, "e" * 32, activate=True, batched=True)
        self.assertEqual(self.host.concurrency, 2)
        self.assertEqual(self.schema, HEAD)
        self.assertEqual(self.operations.count(("cloudformation", "execute-change-set")), 2)
        self.assertEqual(self.public_reads, ["index.html", "health/live", "health/ready"] * 2)
        self.assertFalse(self.worker.calls)

    def test_incompatible_rollback_holds_before_upload_or_traffic(self):
        self.schema = HEAD
        rollback = self.prepare_artifacts("f" * 40, "sha256:" + "8" * 64, "prior view")
        rollback.upgrade = None
        self.pause("f" * 40, "1" * 32, snapshot=False)
        # Model a rebuild from an old source tree that would require a database downgrade.
        migrations = rollback.root / "backend/migrations/versions"
        for path in migrations.glob("*.py"):
            if HEAD in path.name:
                del rollback.image["source_files"]["backend/migrations/versions/" + path.name]
                del rollback.source["files"]["backend/migrations/versions/" + path.name]
                path.unlink()
        grants_file = "backend/app/runtime-grants.json"
        path = rollback.root / grants_file
        previous_grants = json.loads(path.read_text())
        previous_grants["schema_revision"] = "20261031_0051"
        path.write_text(json.dumps(previous_grants))
        rollback.image["source_files"][grants_file] = file_hash(path)
        with self.assertRaisesRegex(RuntimeError, "Fresh target schema observation required"):
            self.collect(rollback)
        self.assertEqual(self.schema, HEAD)
        self.assertEqual(self.host.concurrency, 0)
        self.assertFalse(self.host.receipts)
        self.assertFalse(self.store.writes)
        self.assertFalse(self.worker.calls)


if __name__ == "__main__":
    unittest.main()
