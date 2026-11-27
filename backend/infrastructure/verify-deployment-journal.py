"""Verify target-bound journal storage and uncertain acknowledgement handling."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from deployment_journal import (
    MissingJournalObject,
    RemoteJournal,
    access,
    aws,
    bucket_name,
    read_event,
    release_store,
    template,
)
from deployment_profile import DEVELOPER
from operator_errors import safe_reason


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            **DEVELOPER,
            "account": "123456789012",
            "resource_prefix": "client-test",
            "github_repository": "client/portal",
        }
        self.context = {
            "repository": "client/portal",
            "source_sha": "a" * 40,
            "run_id": "12",
            "attempt": "2",
            "workflow_ref": "client/portal/.github/workflows/aws-rollout.yml@refs/heads/main",
        }
        self.calls = []

    def call(self, operation, values, body=None):
        self.calls.append((operation, values, body))

    def test_operator_journal_persists_local_intent_before_remote_acknowledgement(self):
        from operation_journal import Journal

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout-receipt.json"
            remote = Mock()
            journal = Journal(path, remote=remote)
            self.assertEqual(remote.save.call_args.args[0]["state"], "not_started")

            def check_local(value):
                self.assertEqual(json.loads(path.read_text()), value)
                raise RuntimeError("storage acknowledgement failed")

            remote.save.side_effect = check_local
            with self.assertRaisesRegex(RuntimeError, "acknowledgement failed"):
                journal.save({"state": "execution_requested", "operation_id": "b" * 32})
            self.assertEqual(json.loads(path.read_text())["state"], "execution_requested")
            self.assertEqual(journal.value["operation_id"], "b" * 32)
            self.assertEqual(remote.save.call_count, 2)

    def test_unconfigured_operator_keeps_existing_local_only_contract(self):
        from operation_journal import Journal

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("operation_journal.configured", return_value=None),
        ):
            path = Path(directory) / "receipt.json"
            journal = Journal(path)
            journal.save({"state": "complete"})
            self.assertIsNone(journal.remote)
            self.assertEqual(json.loads(path.read_text()), {"state": "complete"})
            with self.assertRaises(FileExistsError):
                Journal(path)

    def test_events_are_sequenced_and_target_bound(self):
        journal = RemoteJournal(self.profile, self.context, "rollout-receipt.json", self.call)
        journal.save({"state": "intent"})
        first_hash = journal.previous
        journal.save({"state": "submitted"})
        self.assertEqual(journal.sequence, 2)
        self.assertEqual(self.calls[0][1]["Key"], "runs/12/2/rollout-receipt.json/00000000.json")
        self.assertEqual(self.calls[1][1]["ExpectedBucketOwner"], "123456789012")
        self.assertEqual(self.calls[1][1]["IfNoneMatch"], "*")
        self.assertEqual(json.loads(self.calls[1][2])["previous_sha256"], first_hash)

    def test_acknowledgement_failure_does_not_advance_sequence(self):
        def fail(*args):
            raise RuntimeError("lost acknowledgement")

        journal = RemoteJournal(self.profile, self.context, "rollout-receipt.json", fail)
        with self.assertRaises(RuntimeError):
            journal.save({"state": "intent"})
        self.assertEqual(journal.sequence, 0)
        self.assertIsNone(journal.previous)
        journal.call = self.call
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            journal.save({"state": "intent"})
        self.assertEqual(self.calls, [])

    def test_foreign_producer_and_path_traversal_are_rejected(self):
        for context, name in (
            ({**self.context, "repository": "foreign/repo"}, "rollout-receipt.json"),
            ({**self.context, "run_id": "../12"}, "rollout-receipt.json"),
            (self.context, "../receipt.json"),
        ):
            with self.subTest(context=context, name=name), self.assertRaises(RuntimeError):
                RemoteJournal(self.profile, context, name, self.call)
        self.assertEqual(self.calls, [])

    def test_event_read_rejects_wrong_chain(self):
        journal = RemoteJournal(self.profile, self.context, "rollout-receipt.json", self.call)
        journal.save({"state": "intent"})
        body = self.calls[0][2]
        args = {
            "run": "12",
            "attempt": "2",
            "name": "rollout-receipt.json",
            "sequence": 0,
            "context": self.context,
            "previous_sha256": None,
            "call": lambda *args: body,
        }
        event, digest = read_event(self.profile, **args)
        self.assertEqual(event["receipt"], {"state": "intent"})
        self.assertEqual(digest, journal.previous)
        with self.assertRaises(RuntimeError):
            read_event(self.profile, **{**args, "previous_sha256": "b" * 64})

    def test_storage_is_private_retained_and_conditional(self):
        resources = template(self.profile)["Resources"]
        self.assertEqual(set(resources), {"Journal", "JournalPolicy"})
        bucket = resources["Journal"]
        self.assertEqual(bucket["DeletionPolicy"], "Retain")
        self.assertTrue(all(bucket["Properties"]["PublicAccessBlockConfiguration"].values()))
        rules = bucket["Properties"]["LifecycleConfiguration"]["Rules"]
        self.assertEqual(rules[0]["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"], 7)
        self.assertNotIn("ExpirationInDays", rules[0])
        policy = resources["JournalPolicy"]["Properties"]["PolicyDocument"]["Statement"]
        self.assertEqual(
            policy[2]["Condition"], {"Null": {"s3:if-none-match": "true", "s3:if-match": "true"}}
        )
        self.assertEqual(access(self.profile, write=False)["Action"], ["s3:GetObject"])
        self.assertNotIn("418638389566", json.dumps(resources))

    def test_only_explicit_missing_key_allows_initialization(self):
        for code in ("NoSuchKey", "AccessDenied", "NoSuchBucket", "404", "RequestTimeout"):
            with self.subTest(code=code):
                response = Mock(
                    returncode=1,
                    stderr=(
                        f"An error occurred ({code}) when calling the GetObject operation: detail"
                    ).encode(),
                )
                with patch("deployment_journal.subprocess.run", return_value=response):
                    expected = MissingJournalObject if code == "NoSuchKey" else RuntimeError
                    with self.assertRaises(expected) as raised:
                        aws(self.profile, "get-object", {"Key": "releases/example/current.json"})
                    if code != "NoSuchKey":
                        self.assertNotIsInstance(raised.exception, MissingJournalObject)
                    self.assertNotIn("detail", str(raised.exception))
                    if code != "NoSuchKey":
                        expected_code = "UnknownProviderError" if code == "404" else code
                        self.assertIn(
                            f"s3/get-object failed; code={expected_code}",
                            safe_reason(raised.exception),
                        )
        for code in ("AccessDenied", "PreconditionFailed", "ConditionalRequestConflict"):
            response = Mock(
                returncode=1,
                stderr=(
                    f"An error occurred ({code}) when calling the PutObject operation: "
                    "private-detail"
                ).encode(),
            )
            with (
                self.subTest(write_code=code),
                patch("deployment_journal.subprocess.run", return_value=response) as call,
            ):
                with self.assertRaises(RuntimeError) as raised:
                    aws(self.profile, "put-object", {"Key": "releases/example/current.json"}, b"{}")
                self.assertIn(f"s3/put-object failed; code={code}", safe_reason(raised.exception))
                self.assertNotIn("private-detail", safe_reason(raised.exception))
                self.assertEqual(call.call_count, 1)

    def test_release_store_requires_exact_conditional_write(self):
        with patch("deployment_journal.aws", return_value={"ETag": '"version"'}) as call:
            _, write = release_store(self.profile)
            self.assertEqual(
                write("releases/key/current.json", b"{}", if_match='"old"'), '"version"'
            )
            args = call.call_args.args
            self.assertEqual(args[2]["Bucket"], bucket_name(self.profile))
            self.assertEqual(args[2]["IfMatch"], '"old"')
            with self.assertRaises(RuntimeError):
                write("releases/key/current.json", b"{}")
            self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
