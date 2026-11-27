"""Prove retirement preserves evidence, requires live deletion and never replays AWS writes."""

import base64
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from deployment_journal import MissingJournalObject
from deployment_profile import DEVELOPER, identities
from release_record import ReleaseRecord, claim_target, initial, next_stage
from release_recovery import claim_key, inspect_record
from release_retirement import apply, bindings, digest, prepare
from retirement_observation import observe
from schema_probe_plan import prepare_review


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.profile = DEVELOPER
        self.target = identities(self.profile)
        self.source, self.successor = "a" * 40, "b" * 40
        self.objects, self.writes = {}, []
        self.record = ReleaseRecord(self.profile, self.source, self.read, self.write)
        owner = self.record.identity
        prefix = f"arn:aws:cloudformation:{self.target['region']}:{self.target['account']}:stack/"
        self.host = prefix + self.target["hosting_stack"] + "/hosting-id"
        self.probe_id = prefix + self.target["probe_name"] + "/probe-id"
        self.maintenance = {
            **owner,
            "operation_id": "c" * 32,
            "function_revision": "original",
            "previous_concurrency": 10,
            "expires_at": 99,
            "hosting_stack_arn": self.host,
            "database_resource_id": "db-physical",
            "hosting_template_sha256": hashlib.sha256(b"{}").hexdigest(),
        }
        self.probe = {
            **owner,
            "operation_id": "d" * 32,
            "stack_id": self.probe_id,
            "state": "create_submitted",
        }
        sql = b"synthetic catalog"
        self.probe_review = prepare_review(
            {
                "account": self.target["account"],
                "region": self.target["region"],
                "source_sha": self.source,
                "image_digest": "sha256:" + "b" * 64,
                "sql_sha256": hashlib.sha256(sql).hexdigest(),
                "db_host": f"database.example.{self.target['region']}.rds.amazonaws.com",
                "db_name": "synthetic",
                "migration_secret_arn": (
                    f"arn:aws:secretsmanager:{self.target['region']}:{self.target['account']}:"
                    f"secret:{self.target['secret_prefix']}/database/migration-abcdef"
                ),
                "subnet_ids": ["subnet-00000001", "subnet-00000002"],
                "security_group_id": "sg-00000001",
                "expires_at": 99,
            },
            self.source,
            sql,
            now=50,
            profile=self.profile,
        )
        seed = initial(
            self.profile,
            self.source,
            {
                "state": "source_verified",
                "source_sha": self.source,
                "repository": owner["repository"],
            },
            50,
        )
        docs = {
            "maintenance-review/review.json": self.maintenance,
            "schema-probe-review/review.json": self.probe_review,
        }
        for name in ("image", "observation", "prepare", "probe_create", "catalog"):
            evidence = {
                "documents": docs
                if name == "prepare"
                else {"schema-probe-receipt.json": self.probe}
                if name == "probe_create"
                else {}
            }
            if name == "probe_create":
                evidence["dispatch_inputs"] = {
                    "mode": "create",
                    "operation_id": "d" * 32,
                    "template_sha256": self.probe_review["template_sha256"],
                }
            seed["stages"][name] = {
                "outcome": "complete",
                "evidence": evidence,
                "evidence_sha256": digest(evidence),
            }
        seed["pending"] = {
            "stage": "backup",
            "state": "dispatch_intent",
            "operation_id": "e" * 32,
            "inputs": {"workflow": "aws-maintenance.yml", "inputs": {"mode": "backup"}},
        }
        self.record.commit(seed)
        claim_target(self.profile, self.source, self.read, self.write, 50)
        self.evidence = {
            "main_source": self.successor,
            "ancestor": True,
            "maintenance_runs": 0,
            "maintenance_runs_since_intent": 0,
            "active_original_runs": 0,
            "original_coordinator_finished": True,
            "required_input_absent": True,
            "workflow_sha256": "f" * 64,
            "runtime_state": "Active",
            "runtime_update": "Successful",
            "runtime_revision": "original",
            "capacity": 10,
            "maintenance_markers": {},
            "hosting_stack_id": self.host,
            "hosting_status": "UPDATE_COMPLETE",
            "hosting_template_sha256": self.maintenance["hosting_template_sha256"],
            "database_resource_id": "db-physical",
            "database_status": "available",
            "probe_stack_id": self.probe_id,
            "probe_status": "DELETE_COMPLETE",
            "probe_template_sha256": self.probe_review["template_sha256"],
            "probe_tags": {
                "FitfinityOperation": "d" * 32,
                "FitfinitySource": self.source,
                "FitfinityProfile": owner["profile_sha256"],
                "FitfinityTemplate": self.probe_review["template_sha256"],
            },
        }
        self.plan = self.prepare()

    def read(self, key):
        if key not in self.objects:
            raise MissingJournalObject("absent")
        value, etag = self.objects[key]
        return json.loads(value), etag

    def write(self, key, body, *, if_match=None, if_none_match=None):
        if if_none_match and key in self.objects:
            raise RuntimeError("PreconditionFailed")
        if if_match and self.objects.get(key, (None, None))[1] != if_match:
            raise RuntimeError("PreconditionFailed")
        self.writes.append(key)
        etag = str(len(self.writes))
        self.objects[key] = (body, etag)
        return etag

    def claim(self):
        return self.read(claim_key(self.profile))

    def prepare(self):
        return prepare(
            self.record.value,
            self.profile,
            self.successor,
            self.evidence,
            self.claim()[1],
            self.record.etag,
            100,
        )

    def apply(self, **overrides):
        args = {"read_claim": self.claim, "observe": lambda *_: self.evidence, "now": 101}
        args.update(overrides)
        return apply(self.record, self.profile, self.plan, digest(self.plan), **args)

    def test_probe_attempt_uses_creation_dispatch_not_prepared_review(self):
        self.assertNotIn("operation_id", self.probe_review["bindings"])
        original = deepcopy(self.record.value)
        self.assertEqual(bindings(original)[1]["operation_id"], "d" * 32)
        count = len(self.writes)
        for changed in (
            None,
            {},
            {"mode": "collect"},
            {"operation_id": "e" * 32},
            {"operation_id": ""},
            {"template_sha256": "0" * 64},
        ):
            record = deepcopy(original)
            evidence = record["stages"]["probe_create"]["evidence"]
            if changed is None:
                del evidence["dispatch_inputs"]
            elif not changed:
                evidence["dispatch_inputs"] = changed
            else:
                evidence["dispatch_inputs"].update(changed)
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                bindings(record)
        self.assertEqual(len(self.writes), count)

    def test_retirement_preserves_pending_history_and_does_not_transfer_claim(self):
        original = deepcopy(self.record.value)
        claim = self.claim()
        count = len(self.writes)
        self.prepare()
        self.assertEqual(len(self.writes), count)
        self.assertEqual(self.apply()["state"], "retired")
        value = self.record.refresh()
        self.assertEqual(value["pending"], original["pending"])
        self.assertEqual(value["stages"], original["stages"])
        self.assertEqual(self.claim(), claim)
        self.assertEqual(
            next_stage(value, self.record.identity),
            {"action": "retired", "successor_source": self.successor},
        )
        self.assertEqual(
            inspect_record(value, self.profile, self.successor, Mock())["action"], "retired"
        )
        from release_coordinator import tick

        stopped = Mock(side_effect=AssertionError("Retired source must not continue"))
        result = tick(
            self.record,
            verify=lambda: original["verification"],
            plan=stopped,
            read_runs=stopped,
            authenticate=stopped,
            read=stopped,
            send=stopped,
            now=102,
        )
        self.assertEqual(result["reason"], "release_retired")
        stopped.assert_not_called()
        with self.assertRaises(RuntimeError):
            self.record.intent("backup", "f" * 32, {}, 102)
        with self.assertRaises(RuntimeError):
            self.record.complete("e" * 32, {}, outcome="complete", now=102)

    def test_only_exact_reviewed_successor_can_acquire_target(self):
        self.apply()
        with self.assertRaisesRegex(RuntimeError, "Prior release"):
            claim_target(self.profile, "c" * 40, self.read, self.write, 102)
        result = claim_target(self.profile, self.successor, self.read, self.write, 102)
        self.assertEqual(result["identity"]["source_sha"], self.successor)
        self.assertEqual(self.record.refresh()["retirement"]["plan"], self.plan)
        from release_coordinator import load_or_start

        successor_record = ReleaseRecord(self.profile, self.successor, self.read, self.write)
        proof = {
            "state": "source_verified",
            "source_sha": self.successor,
            "repository": self.profile["github_repository"],
        }
        self.assertEqual(
            load_or_start(successor_record, self.profile, lambda: proof, 103)["state"],
            "release_created",
        )
        self.assertEqual(successor_record.value["stages"], {})
        self.assertIsNone(successor_record.value["pending"])

    def test_every_live_safety_binding_rejects_changed_evidence(self):
        mutations = {
            "maintenance_runs": 1,
            "maintenance_runs_since_intent": 1,
            "active_original_runs": 1,
            "original_coordinator_finished": False,
            "required_input_absent": False,
            "main_source": "c" * 40,
            "ancestor": False,
            "runtime_state": "Inactive",
            "runtime_update": "InProgress",
            "runtime_revision": "new",
            "capacity": 0,
            "maintenance_markers": {"FitfinitySnapshot": "other"},
            "hosting_stack_id": "foreign",
            "hosting_status": "UPDATE_IN_PROGRESS",
            "hosting_template_sha256": "0" * 64,
            "database_resource_id": "replaced",
            "database_status": "modifying",
            "probe_stack_id": "other",
            "probe_status": "DELETE_IN_PROGRESS",
            "probe_template_sha256": "0" * 64,
            "probe_tags": {},
        }
        count = len(self.writes)
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                prepare(
                    self.record.value,
                    self.profile,
                    self.successor,
                    {**self.evidence, key: value},
                    "claim",
                    "record",
                    100,
                )
        self.assertEqual(len(self.writes), count)

    def test_expired_tampered_or_changed_review_never_writes(self):
        count = len(self.writes)
        for now in (99, 701):
            with self.assertRaisesRegex(RuntimeError, "expired"):
                self.apply(now=now)
        with self.assertRaisesRegex(RuntimeError, "expired during"):
            self.apply(clock=lambda: 701)
        with self.assertRaisesRegex(RuntimeError, "plan changed"):
            apply(self.record, self.profile, self.plan, "0" * 64, self.claim, Mock(), 101)
        with self.assertRaisesRegex(RuntimeError, "observations changed"):
            self.apply(observe=lambda *_: {**self.evidence, "capacity": 9})
        with self.assertRaisesRegex(RuntimeError, "claim changed"):
            self.apply(read_claim=lambda: (self.claim()[0], "changed"))
        self.assertEqual(len(self.writes), count)

    def test_unexpired_or_different_dispatch_is_not_retirable(self):
        for mutate in (
            lambda r: r["pending"]["inputs"]["inputs"].update(review_sha256="f" * 64),
            lambda r: r["pending"].update(state="dispatched"),
            lambda r: r["stages"].pop("catalog"),
        ):
            value = deepcopy(self.record.value)
            mutate(value)
            with self.assertRaises(RuntimeError):
                prepare(value, self.profile, self.successor, self.evidence, "claim", "record", 100)
        with self.assertRaisesRegex(RuntimeError, "must be expired"):
            prepare(
                self.record.value,
                self.profile,
                self.successor,
                self.evidence,
                "claim",
                "record",
                98,
            )

    def test_lost_pointer_ack_is_reconciled_without_a_second_write(self):
        original = self.record.write

        def lose_ack(key, body, **conditions):
            result = original(key, body, **conditions)
            if key.endswith("current.json"):
                raise RuntimeError("lost acknowledgement")
            return result

        self.record.write = lose_ack
        with self.assertRaisesRegex(RuntimeError, "lost acknowledgement"):
            self.apply()
        count = len(self.writes)
        result = self.apply(observe=Mock(side_effect=AssertionError("Must not reobserve")), now=900)
        self.assertEqual(result["state"], "already_retired")
        self.assertEqual(len(self.writes), count)

    def test_concurrent_writer_and_failed_history_cannot_advance_pointer(self):
        def race(*_):
            key = self.record.prefix + "current.json"
            self.objects[key] = (self.objects[key][0], "racing-etag")
            return self.evidence

        with self.assertRaisesRegex(RuntimeError, "PreconditionFailed"):
            self.apply(observe=race)
        self.assertNotIn("retirement", self.record.refresh())
        self.plan = self.prepare()
        self.record.write = Mock(side_effect=RuntimeError("history unavailable"))
        with self.assertRaisesRegex(RuntimeError, "history unavailable"):
            self.apply()
        self.assertNotIn("retirement", self.record.refresh())

    def test_sealed_history_and_successor_cannot_be_edited(self):
        self.apply()
        for mutate in (
            lambda r: r["pending"].update(operation_id="0" * 32),
            lambda r: r["retirement"]["plan"].update(successor_source="c" * 40),
            lambda r: r.update(generation=r["generation"] + 1),
        ):
            value = deepcopy(self.record.value)
            mutate(value)
            with self.assertRaises(RuntimeError):
                next_stage(value, self.record.identity)

    def providers(self):
        content = b"archived contract"

        def github(path):
            if "/git/ref/" in path:
                return {"object": {"sha": self.successor}}
            if "/compare/" in path:
                return {"status": "ahead", "merge_base_commit": {"sha": self.source}}
            if "/contents/" in path:
                return {
                    "encoding": "base64",
                    "content": base64.b64encode(content).decode(),
                    "sha": hashlib.sha1(
                        b"blob " + str(len(content)).encode() + b"\0" + content
                    ).hexdigest(),
                }
            if "/actions/runs?" in path:
                return {
                    "total_count": 1,
                    "workflow_runs": [
                        {
                            "id": 1,
                            "status": "completed",
                            "path": ".github/workflows/aws-release.yml",
                            "head_sha": self.source,
                        }
                    ],
                }
            return {"total_count": 0, "workflow_runs": []}

        def aws(service, operation, values):
            if operation == "get_caller_identity":
                return {"Account": self.target["account"]}
            if operation == "get_function":
                arn = (
                    f"arn:aws:lambda:{self.target['region']}:{self.target['account']}:function:"
                    + self.target["runtime_function"]
                )
                return {
                    "Tags": {},
                    "Configuration": {
                        "FunctionArn": arn,
                        "State": "Active",
                        "LastUpdateStatus": "Successful",
                        "RevisionId": "original",
                    },
                }
            if operation == "get_function_concurrency":
                return {"ReservedConcurrentExecutions": 10}
            if operation == "get_template":
                return {
                    "TemplateBody": "{}"
                    if values["StackName"] == self.host
                    else json.dumps(self.probe_review["template"])
                }
            if operation == "describe_stacks":
                arn = values["StackName"]
                return {
                    "Stacks": [
                        {
                            "StackId": arn,
                            "StackStatus": "UPDATE_COMPLETE"
                            if arn == self.host
                            else "DELETE_COMPLETE",
                            "Tags": [
                                {"Key": k, "Value": v}
                                for k, v in self.evidence["probe_tags"].items()
                            ],
                        }
                    ]
                }
            if operation == "describe_db_instances":
                arn = (
                    f"arn:aws:rds:{self.target['region']}:{self.target['account']}:db:"
                    + self.target["database"]
                )
                return {
                    "DBInstances": [
                        {
                            "DBInstanceArn": arn,
                            "StorageEncrypted": True,
                            "PubliclyAccessible": False,
                            "Engine": "postgres",
                            "DbiResourceId": "db-physical",
                            "DBInstanceStatus": "available",
                        }
                    ]
                }
            self.fail("Unexpected provider operation: " + operation)

        return github, aws

    def test_provider_observation_reads_exact_original_resources_and_rechecks_main(self):
        github, aws = self.providers()
        git_calls, aws_calls = Mock(side_effect=github), Mock(side_effect=aws)
        result = observe(
            self.record.value,
            self.profile,
            self.successor,
            git_calls,
            aws_calls,
            lambda _: "f" * 64,
        )
        self.assertEqual(result, self.evidence)
        self.assertEqual(sum("/git/ref/" in c.args[0] for c in git_calls.call_args_list), 2)
        self.assertTrue(any("created=" in c.args[0] for c in git_calls.call_args_list))
        self.assertEqual(
            {c.args[1] for c in aws_calls.call_args_list},
            {
                "get_caller_identity",
                "get_function",
                "get_function_concurrency",
                "get_template",
                "describe_stacks",
                "describe_db_instances",
            },
        )

    def test_cross_source_maintenance_and_incomplete_inventory_hold_before_live_checks(self):
        github, aws = self.providers()
        for response in (
            {"total_count": 1, "workflow_runs": [{"id": 5}]},
            {"total_count": 1, "workflow_runs": []},
        ):

            def changed(path, response=response):
                return response if "created=" in path else github(path)

            calls = Mock(side_effect=aws)
            with self.assertRaises(RuntimeError):
                observe(self.record.value, self.profile, self.successor, changed, calls, Mock())
            self.assertEqual([c.args[1] for c in calls.call_args_list], ["get_caller_identity"])

    def test_missing_deleted_stack_or_wrong_account_is_not_deletion_proof(self):
        github, aws = self.providers()

        def missing(service, operation, values):
            if operation == "describe_stacks" and values["StackName"] == self.probe_id:
                raise RuntimeError("AccessDenied or missing")
            return aws(service, operation, values)

        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            observe(
                self.record.value, self.profile, self.successor, github, missing, lambda _: "f" * 64
            )
        with self.assertRaisesRegex(RuntimeError, "account"):
            observe(
                self.record.value,
                self.profile,
                self.successor,
                github,
                lambda *_: {"Account": "000000000000"},
                Mock(),
            )

    def test_cli_prepare_then_reviewed_apply_without_resource_mutations(self):
        from retirement_operator import main

        session = Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile.json"
            profile.write_text(json.dumps(self.profile))
            review = root / "review.json"
            args = ["retirement_operator.py", "--profile", str(profile), "--review", str(review)]
            count = len(self.writes)
            with (
                patch.dict(
                    "sys.modules",
                    {
                        "boto3": SimpleNamespace(Session=Mock(return_value=session)),
                        "botocore.config": SimpleNamespace(Config=lambda **kw: kw),
                    },
                ),
                patch("retirement_operator.release_store", return_value=(self.read, self.write)),
                patch("retirement_operator.subprocess.check_output", return_value=self.successor),
                patch(
                    "retirement_operator.subprocess.run", return_value=SimpleNamespace(returncode=0)
                ),
                patch("retirement_operator.time.time", return_value=100),
                patch("retirement_operator.os.umask"),
                patch("retirement_operator.observe", return_value=self.evidence),
                redirect_stdout(io.StringIO()),
            ):
                with patch("sys.argv", args + ["--mode", "prepare"]):
                    main()
                self.assertEqual(len(self.writes), count)
                plan = json.loads(review.read_text())
                with patch("sys.argv", args + ["--mode", "apply", "--sha256", digest(plan)]):
                    main()
                self.assertEqual(len(self.writes), count + 2)
                self.assertEqual(self.record.refresh()["retirement"]["plan"], plan)
                session.client.assert_not_called()
                failure = RuntimeError("private provider text")
                failure.response = {"Error": {"Code": "AccessDenied", "Message": "private"}}
                session.client.return_value.get_caller_identity.side_effect = failure

                def denied(record, profile, source, github, aws, contract):
                    return aws("sts", "get_caller_identity", {})

                with patch("retirement_operator.observe", side_effect=denied):
                    with patch("sys.argv", args + ["--mode", "prepare"]):
                        with self.assertRaisesRegex(RuntimeError, "code=AccessDenied") as error:
                            main()
                self.assertNotIn("private", str(error.exception))
                self.assertEqual(len(self.writes), count + 2)

    def test_main_advance_during_observation_is_rejected(self):
        github, aws = self.providers()
        count = 0

        def advance(path):
            nonlocal count
            if "/git/ref/" in path:
                count += 1
                if count == 2:
                    return {"object": {"sha": "c" * 40}}
            return github(path)

        with self.assertRaisesRegex(RuntimeError, "Main changed"):
            observe(
                self.record.value, self.profile, self.successor, advance, aws, lambda _: "f" * 64
            )


if __name__ == "__main__":
    unittest.main()
