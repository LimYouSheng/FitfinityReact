"""Offline adversarial checks for first-release scope, resume, bytes and HTTP acceptance."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import hosting_design as d
import hosting_frontend as f
import hosting_operator as o

EDGE = (
    "arn:aws:wafv2:us-east-1:418638389566:global/webacl/fitfinity"
    "-test-login-cloudfront/11111111-1111-1111-1111-111111111111"
)
PREFIX = "releases/" + d.ADAPTATION_BASE + "/" + "a" * 64


def all_refs(value):
    result = set()
    if isinstance(value, dict):
        if "Ref" in value:
            result.add(value["Ref"])
        if "Fn::GetAtt" in value:
            result.add(value["Fn::GetAtt"][0])
        if "Fn::Sub" in value:
            result |= {r.split(".")[0] for r in re.findall(r"\$\{([^}]+)\}", value["Fn::Sub"])}
        for child in value.values():
            result |= all_refs(child)
    elif isinstance(value, list):
        for child in value:
            result |= all_refs(child)
    return result


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.t = d.app_template(PREFIX, EDGE)

    def test_existing_owner_receipt_validates_without_executing_bootstrap(self):
        provenance = json.loads((o.ROOT / "hosting-source.json").read_text())
        self.assertEqual(
            provenance["manifest"]["accepted-first-owner.json"], d.OWNER_RECEIPT_SHA256
        )
        self.assertEqual(len(provenance["manifest"]), 57)

    def test_template_has_no_dependency_cycle(self):
        resources = self.t["Resources"]
        graph = {k: all_refs(v) | set(v.get("DependsOn", [])) for k, v in resources.items()}
        visited, visiting = set(), set()

        def visit(k):
            self.assertIn(k, resources)
            self.assertNotIn(k, visiting)
            if k in visited:
                return
            visiting.add(k)
            for child in graph[k]:
                visit(child)
            visiting.remove(k)
            visited.add(k)

        for k in graph:
            visit(k)

    def test_runtime_uses_accepted_digest_default_image_command(self):
        p = self.t["Resources"]["ApiFunction"]["Properties"]
        self.assertEqual(p["Code"]["ImageUri"], d.IMAGE)
        self.assertNotIn("ImageConfig", p)
        self.assertEqual(p["ReservedConcurrentExecutions"], 2)
        self.assertEqual(
            p["VpcConfig"]["SubnetIds"], ["subnet-0a6ea67e00f370997", "subnet-0fcdf32ab544f1207"]
        )

    def test_no_bootstrap_migrations_or_identity_admin_permissions(self):
        raw = d.compact(self.t)
        for forbidden in [
            "bootstrap-owner",
            "AdminCreateUser",
            "AdminSetUserPassword",
            "secretsmanager:*",
            "lambda:*",
            "SecretString",
            "FITFINITY_DATABASE_URL",
        ]:
            self.assertNotIn(forbidden, raw)
        policy = d.runtime_policy()
        self.assertEqual(len(policy["Statement"][0]["Resource"]), 2)
        self.assertFalse(any("cognito-idp:" in d.compact(x) for x in policy["Statement"]))

    def test_api_paths_forward_credentials_without_cache(self):
        cfg = self.t["Resources"]["Distribution"]["Properties"]["DistributionConfig"]
        self.assertEqual(
            [x["PathPattern"] for x in cfg["CacheBehaviors"]], ["auth/*", "api/*", "me", "health/*"]
        )
        for row in cfg["CacheBehaviors"]:
            self.assertEqual(row["CachePolicyId"], d.CACHE_DISABLED)
            self.assertEqual(row["OriginRequestPolicyId"], d.ORIGIN_FORWARD)
            self.assertEqual(row["ViewerProtocolPolicy"], "https-only")

    def test_exact_origin_and_private_storage(self):
        env = self.t["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
        self.assertEqual(
            env["FITFINITY_AUTH_ORIGINS"], {"Fn::Sub": '["https://${Distribution.DomainName}"]'}
        )
        self.assertEqual(env["FITFINITY_AUTH_COOKIE_SECURE"], "true")
        bucket = self.t["Resources"]["FrontendBucket"]
        self.assertTrue(all(bucket["Properties"]["PublicAccessBlockConfiguration"].values()))
        self.assertEqual(bucket["DeletionPolicy"], "Retain")

    def test_no_logging_of_authentication_request_bodies_or_cookies(self):
        cfg = self.t["Resources"]["Distribution"]["Properties"]["DistributionConfig"]
        self.assertNotIn("Logging", cfg)
        stage = self.t["Resources"]["ApiStage"]["Properties"]
        self.assertNotIn("AccessLogSetting", stage)
        self.assertFalse(stage["MethodSettings"][0]["DataTraceEnabled"])
        for scope in ["REGIONAL", "CLOUDFRONT"]:
            acl = d.waf(scope)["Properties"]
            self.assertFalse(acl["VisibilityConfig"]["SampledRequestsEnabled"])
            self.assertTrue(
                all(not r["VisibilityConfig"]["SampledRequestsEnabled"] for r in acl["Rules"])
            )

    def test_schema_and_output_sizes_allow_local_template_transport(self):
        self.assertLess(len(d.compact(self.t).encode()), 51200)
        self.assertEqual(len(self.t["Resources"]), 20)
        self.assertEqual(set(d.edge_template()["Resources"]), {"EdgeAcl"})

    def test_wrong_region_account_or_unreviewed_paths_are_refused(self):
        for prefix, arn in [
            (PREFIX + "/../other", EDGE),
            (PREFIX, EDGE.replace("418638389566", "123456789012")),
            (PREFIX, EDGE.replace("us-east-1", "ap-southeast-1")),
        ]:
            with self.subTest(prefix=prefix, arn=arn), self.assertRaises(RuntimeError):
                d.app_template(prefix, arn)


class CloudFormationFixture:
    def __init__(self, operator, template):
        self.op, self.template = operator, template
        self.remote = None
        self.calls = []
        self.bad_action = False
        self.lose_create = False
        self.lose_execute = False
        self.placeholder = False
        self.change_overrides = {}
        self.stack_id = (
            "arn:aws:cloudformation:us-east-1:418638389566:stack/fitfinit"
            "y-test-login-edge/11111111-1111-1111-1111-111111111111"
        )

    def __call__(self, service, operation, *args, **kwargs):
        self.calls.append((service, operation))
        if operation == "describe-stacks":
            return {"Stacks": [deepcopy(self.remote)]} if self.remote else None
        if operation == "validate-template":
            return {}
        if operation == "create-change-set":
            self.remote = {
                "StackId": self.stack_id,
                "StackName": "fitfinity-test-login-edge",
                "StackStatus": "REVIEW_IN_PROGRESS",
                "RoleARN": "arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation",
                "Tags": [{"Key": k, "Value": v} for k, v in self.op.tags("edge").items()],
                "Outputs": [{"OutputKey": "WebAclArn", "OutputValue": EDGE}],
            }
            if self.placeholder:
                self.remote["Tags"] = []
            if self.lose_create:
                raise RuntimeError("Lost create response")
            return {"StackId": self.stack_id, "Id": "change-set-id"}
        if operation == "describe-change-set":
            return {
                "Status": "CREATE_COMPLETE",
                "ExecutionStatus": "AVAILABLE",
                "StackId": self.stack_id,
                "StackName": "fitfinity-test-login-edge",
                "ChangeSetName": self.op.state["stacks"]["edge"]["change_set_name"],
                "ChangeSetId": "change-set-id",
                "Tags": [{"Key": k, "Value": v} for k, v in self.op.tags("edge").items()],
                "Changes": [
                    {
                        "ResourceChange": {
                            "LogicalResourceId": k,
                            "ResourceType": v["Type"],
                            "Action": "Modify" if self.bad_action else "Add",
                        }
                    }
                    for k, v in self.template["Resources"].items()
                ],
                **self.change_overrides,
            }
        if operation == "get-template":
            return {"TemplateBody": self.template}
        if operation == "execute-change-set":
            self.remote["StackStatus"] = "CREATE_COMPLETE"
            self.remote["Tags"] = [{"Key": k, "Value": v} for k, v in self.op.tags("edge").items()]
            self.remote["RoleARN"] = (
                "arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation"
            )
            if self.lose_execute:
                raise RuntimeError("Lost execute response")
            return {}
        if operation == "list-stack-resources":
            if self.remote["StackStatus"] == "REVIEW_IN_PROGRESS":
                return {"StackResourceSummaries": []}
            return {
                "StackResourceSummaries": [
                    {
                        "LogicalResourceId": k,
                        "ResourceType": v["Type"],
                        "PhysicalResourceId": "fixture-" + k,
                        "ResourceStatus": "CREATE_COMPLETE",
                    }
                    for k, v in self.template["Resources"].items()
                ]
            }
        if operation == "delete-stack":
            self.remote["StackStatus"] = "DELETE_COMPLETE"
            return {}
        raise AssertionError((service, operation, args))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = {"operation_id": "f" * 32}
        self.report = {"current_scan_pages": []}
        self.op = o.Operator(Path(self.tmp.name), self.state, self.report, sleep=lambda _: None)
        self.t = d.edge_template()
        self.aws = CloudFormationFixture(self.op, self.t)
        self.op.aws = self.aws
        self.state["review_token"] = o.digest(
            {
                "operation": self.state["operation_id"],
                "stack": self.aws.stack_id,
                "change_set": "change-set-id",
                "template": o.digest(self.t),
            }
        )
        for target in ["hosting_operator.pf.evidence"]:
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_create_reviews_exact_adds_before_execute(self):
        self.assertEqual(self.op.create("edge", self.t), {"WebAclArn": EDGE})
        names = [x[1] for x in self.aws.calls]
        self.assertLess(names.index("describe-change-set"), names.index("execute-change-set"))
        self.assertTrue(self.state["stacks"]["edge"]["reviewed_change_set"])

    def test_rerun_does_not_recreate_or_execute(self):
        self.op.create("edge", self.t)
        self.aws.calls.clear()
        self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_existing_unowned_stack_refused(self):
        self.aws.remote = {
            "StackId": self.aws.stack_id,
            "StackName": "fitfinity-test-login-edge",
            "StackStatus": "CREATE_COMPLETE",
            "Tags": [],
        }
        with self.assertRaisesRegex(RuntimeError, "not owned"):
            self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_non_add_changes_never_execute(self):
        self.aws.bad_action = True
        with self.assertRaisesRegex(RuntimeError, "non-create"):
            self.op.create("edge", self.t)
        self.assertNotIn(("cloudformation", "execute-change-set"), self.aws.calls)

    def test_lost_create_response_reconciles_owned_review_stack(self):
        self.aws.lose_create = True
        with self.assertRaisesRegex(RuntimeError, "Lost create"):
            self.op.create("edge", self.t)
        self.aws.calls.clear()
        self.aws.lose_create = False
        self.op.create("edge", self.t)
        self.assertNotIn(("cloudformation", "create-change-set"), self.aws.calls)

    def test_lost_execute_response_resumes_completed_stack(self):
        self.aws.lose_execute = True
        with self.assertRaisesRegex(RuntimeError, "Lost execute"):
            self.op.create("edge", self.t)
        self.aws.calls.clear()
        self.aws.lose_execute = False
        self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_uncertain_execute_still_available_is_not_replayed(self):
        self.aws.lose_execute = True
        with self.assertRaises(RuntimeError):
            self.op.create("edge", self.t)
        self.aws.remote["StackStatus"] = "REVIEW_IN_PROGRESS"
        self.aws.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.op.create("edge", self.t)
        self.assertNotIn(("cloudformation", "execute-change-set"), self.aws.calls)

    def test_missing_stack_with_prior_intent_is_not_recreated(self):
        self.aws.lose_create = True
        with self.assertRaises(RuntimeError):
            self.op.create("edge", self.t)
        self.aws.remote = None
        self.aws.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_changed_tags_prevent_adoption(self):
        self.op.create("edge", self.t)
        self.aws.remote["Tags"][0]["Value"] = "Foreign"
        with self.assertRaisesRegex(RuntimeError, "ownership tags"):
            self.op.create("edge", self.t)

    def test_changed_template_prevents_cleanup(self):
        self.op.create("edge", self.t)
        self.aws.template = {**self.t, "Description": "foreign change"}
        self.aws.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "template differs"):
            self.op.cleanup()
        self.assertNotIn(("cloudformation", "delete-stack"), self.aws.calls)

    def test_scoped_cleanup_resumes_without_second_delete(self):
        self.op.create("edge", self.t)
        self.op.cleanup()
        self.aws.calls.clear()
        self.op.cleanup()
        self.assertTrue(self.state["cleaned_up"])
        self.assertNotIn(("cloudformation", "delete-stack"), self.aws.calls)
        self.assertEqual((Path(self.tmp.name) / "state.json").stat().st_mode & 0o777, 0o600)

    def prepare_placeholder(self):
        self.aws.placeholder = True
        self.state["mode"] = "prepare"
        self.assertIsNone(self.op.create("edge", self.t))
        self.aws.calls.clear()

    def test_untagged_review_shell_requires_owned_change_set(self):
        self.prepare_placeholder()
        row = self.state["stacks"]["edge"]
        self.assertTrue(row["create_response_received"])
        self.assertEqual(self.report["status"], "change_set_review_required")
        self.assertEqual(self.report["review_token"], row["review_token"])
        self.assertFalse(row.get("execute_intent"))
        self.assertEqual(self.report["review_stack_ownership"]["edge"]["stack_tags"], [])

    def test_untagged_review_resume_never_recreates_or_executes(self):
        self.prepare_placeholder()
        self.assertIsNone(self.op.create("edge", self.t))
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_review_change_set_foreign_identity_or_tags_refused(self):
        self.prepare_placeholder()
        tags = [{"Key": k, "Value": v} for k, v in self.op.tags("edge").items()]
        bad_tags = deepcopy(tags)
        bad_tags[-1]["Value"] = "foreign-template"
        for override in [
            {"StackId": self.aws.stack_id + "-foreign"},
            {"StackName": "foreign"},
            {"ChangeSetId": "foreign"},
            {"ChangeSetName": "foreign"},
            {"Tags": []},
            {"Tags": bad_tags},
            {"Tags": tags + tags[:1]},
            {"ExecutionStatus": "EXECUTE_COMPLETE"},
        ]:
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                self.aws.change_overrides = override
                self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_untagged_review_without_acknowledged_create_refused(self):
        self.prepare_placeholder()
        self.state["stacks"]["edge"].pop("create_response_received")
        with self.assertRaisesRegex(RuntimeError, "acknowledged"):
            self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_deployed_stack_cannot_use_placeholder_tag_exception(self):
        self.prepare_placeholder()
        self.aws.remote["StackStatus"] = "CREATE_COMPLETE"
        with self.assertRaisesRegex(RuntimeError, "ownership tags"):
            self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_review_shell_with_resources_refused(self):
        self.prepare_placeholder()
        original = self.op.aws

        def unexpected(service, operation, *args, **kwargs):
            if operation == "list-stack-resources":
                return {"StackResourceSummaries": [{"PhysicalResourceId": "foreign"}]}
            return original(service, operation, *args, **kwargs)

        self.op.aws = unexpected
        with self.assertRaisesRegex(RuntimeError, "contains resources"):
            self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_review_shell_template_drift_refused(self):
        self.prepare_placeholder()
        self.aws.template = {**self.t, "Description": "foreign"}
        with self.assertRaisesRegex(RuntimeError, "template differs"):
            self.op.create("edge", self.t)
        self.assertFalse(set(self.aws.calls) & o.WRITES)

    def test_review_shell_foreign_role_or_partial_tags_refused(self):
        self.prepare_placeholder()
        for field, value in [
            ("RoleARN", "arn:aws:iam::418638389566:role/foreign"),
            ("RoleARN", None),
            ("Tags", [{"Key": "Application", "Value": "Fitfinity"}]),
        ]:
            original = self.aws.remote[field]
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.aws.remote[field] = value
                self.op.create("edge", self.t)
            self.aws.remote[field] = original
        self.assertFalse(set(self.aws.calls) & o.WRITES)


class ArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        for name, body in [
            ("index.html", "<html></html>"),
            ("sw.js", "// fixture worker"),
            ("manifest.webmanifest", "{}"),
        ]:
            (self.path / name).write_text(body)
        self.manifest = f.inventory(self.path)

    def test_inventory_is_content_bound(self):
        first = f.manifest_hash(self.manifest)
        (self.path / "index.html").write_text("<html>changed</html>")
        self.assertNotEqual(first, f.manifest_hash(f.inventory(self.path)))

    def test_symlink_output_is_refused(self):
        (self.path / "foreign.js").symlink_to(self.path / "sw.js")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            f.inventory(self.path)

    def test_source_maps_are_refused(self):
        (self.path / "main.js.map").write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "Unreviewed"):
            f.inventory(self.path)

    def test_missing_shell_is_refused(self):
        (self.path / "sw.js").unlink()
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            f.inventory(self.path)

    def test_private_file_is_refused(self):
        (self.path / ".env").write_text("sentinel")
        with self.assertRaisesRegex(RuntimeError, "Unsafe"):
            f.inventory(self.path)

    def test_conditional_upload_and_recovery_use_exact_bytes(self):
        state = {
            "frontend": {"directory": str(self.path), "manifest": self.manifest, "prefix": PREFIX},
            "outputs": {"FrontendBucket": "owned-bucket"},
        }
        saved, writes = {}, []

        def aws(service, operation, *args, **kwargs):
            key = o.flag(args, "--key")
            name = key.rsplit("/", 1)[1]
            if operation == "head-object":
                return saved.get(key)
            self.assertEqual(operation, "put-object")
            self.assertEqual(o.flag(args, "--if-none-match"), "*")
            row = self.manifest[name]
            saved[key] = {
                "ContentLength": row["bytes"],
                "ChecksumSHA256": row["checksum"],
                "ContentType": row["content_type"],
                "CacheControl": row["cache_control"],
                "ServerSideEncryption": "AES256",
            }
            writes.append(key)
            if len(writes) == 1:
                raise RuntimeError("Upload response lost after committed object")
            return {}

        op = o.Operator(self.path, state, {}, aws=aws)
        # Persist operator files outside the public artifact directory.
        with tempfile.TemporaryDirectory() as evidence:
            op.directory = Path(evidence)
            with self.assertRaisesRegex(RuntimeError, "response lost"):
                op.upload()
            saved_state = json.loads((op.directory / "state.json").read_text())
            self.assertIn("upload_intent", saved_state)
            self.assertFalse(saved_state.get("frontend_uploaded", False))
            op.upload()
            op.upload()
            self.assertEqual(len(writes), 3)
            self.assertTrue(state["frontend_uploaded"])

    def test_upload_refuses_an_existing_wrong_object(self):
        state = {
            "frontend": {"directory": str(self.path), "manifest": self.manifest, "prefix": PREFIX},
            "outputs": {"FrontendBucket": "owned-bucket"},
        }
        calls = []

        def aws(service, operation, *args, **kwargs):
            calls.append(operation)
            return {"ContentLength": 0}

        op = o.Operator(self.path, state, {}, aws=aws)
        op.save = lambda: None
        with self.assertRaisesRegex(RuntimeError, "differs"):
            op.upload()
        self.assertEqual(calls, ["head-object"])

    def test_smoke_verifies_all_public_bytes_and_unauthenticated_api(self):
        state = {
            "frontend": {"manifest": self.manifest},
            "outputs": {"FrontendDomain": "dexample.cloudfront.net"},
        }

        def getter(url, headers=None):
            path = url.split(".net", 1)[1]
            h = {
                "x-content-type-options": "nosniff",
                "content-type": "application/json",
                "x-cache": "Miss from cloudfront",
            }
            if path in ["/health/live", "/health/ready"]:
                return (
                    200,
                    h,
                    json.dumps({"status": "alive" if path.endswith("live") else "ready"}).encode(),
                )
            if path == "/auth/policy":
                return (
                    200,
                    h,
                    json.dumps(
                        {
                            "password": {
                                "minimumLength": 15,
                                "maximumLength": 128,
                                "spacesAllowed": False,
                                "requiresCharacterMix": False,
                                "scheduledRotation": False,
                            },
                            "mfa": {"required": True, "method": "totp"},
                            "recovery": "verified_email",
                        }
                    ).encode(),
                )
            if path in ["/me", "/auth/session"]:
                return 401, h, b'{"error":{"code":"SESSION_EXPIRED"}}'
            name = "index.html" if path == "/" else path[1:]
            h["content-type"] = self.manifest[name]["content_type"]
            return 200, h, (self.path / name).read_bytes()

        report = {}
        o.smoke(state, report, getter)
        self.assertEqual(len(report["public_smoke"]), 8)
        self.assertNotIn("live_authentication_accepted", report)

        def bad(url, headers=None):
            status, h, b = getter(url, headers)
            if url.endswith("/me"):
                h["age"] = "1"
            return status, h, b

        with self.assertRaisesRegex(RuntimeError, "cached"):
            o.smoke(state, {}, bad)


class BoundaryTests(unittest.TestCase):
    def test_unknown_write_and_endpoint_override_never_reach_cli(self):
        calls = []
        aws = o.HostingAWS(
            {"calls": [], "cloud_writes": []},
            {},
            lambda: None,
            runner=lambda *a, **k: calls.append(a),
        )
        for args in [
            ("cognito-idp", "admin-create-user"),
            ("lambda", "invoke"),
            ("cloudfront", "get-distribution", "--endpoint-url", "http://localhost"),
        ]:
            with self.assertRaises(RuntimeError):
                aws(*args)
        self.assertEqual(calls, [])

    def test_create_template_tamper_stops_before_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "template.json"
            p.write_text("{}")
            args = [
                "--stack-name",
                "fitfinity-test-login-edge",
                "--template-body",
                "file://" + str(p),
            ]
            state = {
                "execution_authorized": True,
                "mode": "prepare",
                "stacks": {
                    "edge": {
                        "template_sha256": o.digest({"unexpected": True}),
                        "create_intent": {"arguments_sha256": o.digest(args)},
                    }
                },
            }
            aws = o.HostingAWS({"calls": [], "cloud_writes": []}, state, lambda: None)
            with self.assertRaisesRegex(RuntimeError, "Template bytes"):
                aws("cloudformation", "create-change-set", *args, region="us-east-1")

    def test_actual_write_boundary_rechecks_approval_and_serializes_scoped_oidc_call(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "template.json"
            path.write_text("{}")
            args = [
                "--stack-name",
                "fitfinity-test-login-edge",
                "--template-body",
                "file://" + str(path),
                "--role-arn",
                "arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation",
            ]
            state = {
                "execution_authorized": True,
                "mode": "prepare",
                "stacks": {
                    "edge": {
                        "template_sha256": o.digest({}),
                        "create_intent": {"arguments_sha256": o.digest(args)},
                    }
                },
            }
            report = {"calls": [], "cloud_writes": []}
            from unittest.mock import Mock

            runner = Mock(return_value=subprocess.CompletedProcess([], 0, "{}", ""))
            aws = o.HostingAWS(report, state, lambda: None, runner)
            with patch.object(o.pf, "evidence", side_effect=RuntimeError("Approval expired")):
                with self.assertRaisesRegex(RuntimeError, "expired"):
                    aws("cloudformation", "create-change-set", *args, region="us-east-1")
            runner.assert_not_called()
            self.assertEqual(report["cloud_writes"], [])
            with patch.object(o.pf, "evidence") as check:
                aws("cloudformation", "create-change-set", *args, region="us-east-1")
                check.assert_called_once()
            self.assertNotIn("--profile", runner.call_args.args[0])
            self.assertEqual(runner.call_args.kwargs["env"]["AWS_MAX_ATTEMPTS"], "1")
            self.assertIn("--role-arn", runner.call_args.args[0])
            state["mode"] = "verify"
            runner.reset_mock()
            with self.assertRaisesRegex(RuntimeError, "phase"):
                aws("cloudformation", "create-change-set", *args, region="us-east-1")
            runner.assert_not_called()

    def test_unknown_stack_cannot_be_deleted(self):
        aws = o.HostingAWS(
            {"calls": [], "cloud_writes": []},
            {"execution_authorized": True, "stacks": {}},
            lambda: None,
        )
        with self.assertRaisesRegex(RuntimeError, "Unowned stack"):
            aws("cloudformation", "delete-stack", "--stack-name", "unrelated")

    def test_expired_credentials_report_safe_actionable_error(self):
        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(
                args[0],
                255,
                "",
                "An error occurred (ExpiredToken) when calling operation: private-sentinel",
            )

        report = {"calls": [], "cloud_writes": []}
        aws = o.HostingAWS(report, {}, lambda: None, runner)
        with self.assertRaisesRegex(RuntimeError, "OIDC session expired"):
            aws("lambda", "get-account-settings")
        self.assertNotIn("private-sentinel", json.dumps(report))

    def test_provider_secret_output_is_discarded(self):
        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 0, '{"SecretString":"sentinel"}', "")

        report = {"calls": [], "cloud_writes": []}
        with self.assertRaisesRegex(RuntimeError, "secret field"):
            o.HostingAWS(report, {}, lambda: None, runner)("lambda", "get-account-settings")
        self.assertNotIn("sentinel", json.dumps(report))

    def test_pagination_is_not_accepted_as_complete(self):
        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 0, '{"NextToken":"more"}', "")

        with self.assertRaisesRegex(RuntimeError, "pagination"):
            o.HostingAWS({"calls": [], "cloud_writes": []}, {}, lambda: None, runner)(
                "lambda", "get-account-settings"
            )

    def test_s3_missing_and_denied_are_distinguished(self):
        for code, absent in [("404", True), ("AccessDenied", False)]:

            def runner(*args, code=code, **kwargs):
                return subprocess.CompletedProcess(
                    args[0], 255, "", f"An error occurred ({code}) when calling HeadObject: safe"
                )

            aws = o.HostingAWS({"calls": [], "cloud_writes": []}, {}, lambda: None, runner)
            if absent:
                self.assertIsNone(
                    aws("s3api", "head-object", "--bucket", "bucket", "--key", "key", absent=True)
                )
            else:
                with self.assertRaises(RuntimeError):
                    aws("s3api", "head-object", "--bucket", "bucket", "--key", "key", absent=True)


class LiveVerificationTests(unittest.TestCase):
    def setUp(self):
        self.template = d.app_template(PREFIX, EDGE)
        self.outputs = {
            "FrontendDomain": "dexample.cloudfront.net",
            "ApiId": "abcdef1234",
            "FrontendBucket": "fitfinity-test-login-bucket",
            "FunctionVersion": "1",
            "FunctionAlias": (
                "arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinit"
                "y-test-staff-api:first-test"
            ),
            "RuntimeRole": "fitfinity-role",
            "DistributionId": "EDIST",
            "RegionalWebAclArn": (
                "arn:aws:wafv2:ap-southeast-1:418638389566:regional/webacl/fi"
                "tfinity-test-login-regional/11111111-1111-1111-1111-11111111"
                "1111"
            ),
        }
        ids = {
            "OriginAccess": "EOAC",
            "StaticCache": "static-cache-id",
            "ResponseHeaders": "headers-id",
            "ApiDeployment": "deployment-id",
            "ProxyResource": "proxy-id",
        }
        self.state = {
            "outputs": self.outputs,
            "frontend": {"prefix": PREFIX},
            "stacks": {"app": {"resource_ids": ids}, "edge": {"outputs": {"WebAclArn": EDGE}}},
        }
        role_arn = "arn:aws:iam::418638389566:role/fitfinity-role"
        env = deepcopy(
            self.template["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
        )
        env.update(
            FITFINITY_ALLOWED_HOSTS=(
                '["127.0.0.1","abcdef1234.execute-api.ap-southeast-1.amazonaws.com"]'
            ),
            FITFINITY_AUTH_ORIGINS='["https://dexample.cloudfront.net"]',
        )
        config = {
            "FunctionName": d.FUNCTION,
            "Version": "1",
            "State": "Active",
            "MemorySize": 512,
            "Timeout": 25,
            "Architectures": ["x86_64"],
            "Environment": {"Variables": env},
            "Role": role_arn,
            "VpcConfig": {
                "SubnetIds": ["subnet-0a6ea67e00f370997", "subnet-0fcdf32ab544f1207"],
                "SecurityGroupIds": ["sg-09bcb69b70968f702"],
                "VpcId": "vpc-0b55320bb1a054441",
                "Ipv6AllowedForDualStack": False,
            },
        }
        dist = {
            "Enabled": True,
            "WebACLId": EDGE,
            "DefaultRootObject": "index.html",
            "Aliases": {"Quantity": 0},
            "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
            "DefaultCacheBehavior": {
                "TargetOriginId": "frontend",
                "ViewerProtocolPolicy": "redirect-to-https",
                "CachePolicyId": ids["StaticCache"],
                "ResponseHeadersPolicyId": ids["ResponseHeaders"],
            },
            "CacheBehaviors": {
                "Items": [
                    {
                        "PathPattern": p,
                        "TargetOriginId": "api",
                        "CachePolicyId": d.CACHE_DISABLED,
                        "OriginRequestPolicyId": d.ORIGIN_FORWARD,
                        "ViewerProtocolPolicy": "https-only",
                    }
                    for p in d.API_PATHS
                ]
            },
            "Origins": {
                "Items": [
                    {
                        "Id": "api",
                        "DomainName": "abcdef1234.execute-api.ap-southeast-1.amazonaws.com",
                        "OriginPath": "/test",
                        "CustomOriginConfig": {"OriginProtocolPolicy": "https-only"},
                    },
                    {
                        "Id": "frontend",
                        "DomainName": "fitfinity-test-login-bucket.s3.ap-southeast-1.amazonaws.com",
                        "OriginPath": "/" + PREFIX,
                        "OriginAccessControlId": "EOAC",
                    },
                ]
            },
        }
        permission = {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "lambda:InvokeFunction",
                    "Principal": {"Service": "apigateway.amazonaws.com"},
                    "Resource": self.outputs["FunctionAlias"],
                    "Condition": {
                        "StringEquals": {"AWS:SourceAccount": d.ACCOUNT},
                        "ArnLike": {
                            "AWS:SourceArn": (
                                "arn:aws:execute-api:ap-southeast-1:418638389566:abcdef1234/t"
                                "est/*/*"
                            )
                        },
                    },
                }
            ]
        }
        self.responses = {
            "get-function": {"Code": {"ResolvedImageUri": d.IMAGE}, "Configuration": config},
            "get-role": {
                "Role": {
                    "Arn": role_arn,
                    "AssumeRolePolicyDocument": self.template["Resources"]["ApiRole"]["Properties"][
                        "AssumeRolePolicyDocument"
                    ],
                }
            },
            "get-role-policy": {"PolicyDocument": d.runtime_policy()},
            "list-role-policies": {"PolicyNames": ["FitfinityTestLogin"]},
            "list-attached-role-policies": {"AttachedPolicies": []},
            "get-alias": {"FunctionVersion": "1"},
            "get-function-concurrency": {"ReservedConcurrentExecutions": 2},
            "get-function-url-config": None,
            "get-policy": {"Policy": json.dumps(permission)},
            "list-event-source-mappings": {"EventSourceMappings": []},
            "get-distribution": {
                "Distribution": {
                    "Status": "Deployed",
                    "DomainName": "dexample.cloudfront.net",
                    "DistributionConfig": dist,
                }
            },
            "get-cache-policy": {
                "CachePolicy": {
                    "CachePolicyConfig": {
                        **self.template["Resources"]["StaticCache"]["Properties"][
                            "CachePolicyConfig"
                        ],
                        "Comment": "",
                    }
                }
            },
            "get-origin-access-control": {
                "OriginAccessControl": {
                    "OriginAccessControlConfig": self.template["Resources"]["OriginAccess"][
                        "Properties"
                    ]["OriginAccessControlConfig"]
                }
            },
            "get-public-access-block": {
                "PublicAccessBlockConfiguration": self.template["Resources"]["FrontendBucket"][
                    "Properties"
                ]["PublicAccessBlockConfiguration"]
            },
            "get-bucket-versioning": {"Status": "Enabled"},
            "get-stage": {
                "deploymentId": "deployment-id",
                "cacheClusterEnabled": False,
                "methodSettings": {
                    "*/*": {
                        "dataTraceEnabled": False,
                        "loggingLevel": "OFF",
                        "throttlingRateLimit": 5,
                        "throttlingBurstLimit": 10,
                        "cachingEnabled": False,
                    }
                },
            },
            "get-integration": {
                "type": "AWS_PROXY",
                "httpMethod": "POST",
                "uri": "arn:aws:apigateway:ap-southeast-1:lambda:path/2015-03-31/functions/"
                + self.outputs["FunctionAlias"]
                + "/invocations",
            },
            "get-web-acl-for-resource": {
                "WebACL": {
                    **d.waf("REGIONAL")["Properties"],
                    "ARN": self.outputs["RegionalWebAclArn"],
                }
            },
            "get-web-acl": {"WebACL": {**d.waf("CLOUDFRONT")["Properties"], "ARN": EDGE}},
        }

        self.responses["get-role"]["Role"].update(
            RoleName="fitfinity-test-hosting-api",
            PermissionsBoundary={
                "PermissionsBoundaryArn": (
                    "arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary"
                )
            },
        )
        bucket = "arn:aws:s3:::" + self.outputs["FrontendBucket"]
        self.responses["get-bucket-encryption"] = {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        }
        self.responses["get-bucket-policy"] = {
            "Policy": json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "cloudfront.amazonaws.com"},
                            "Action": "s3:GetObject",
                            "Resource": bucket + "/*",
                            "Condition": {
                                "StringEquals": {
                                    "AWS:SourceArn": (
                                        "arn:aws:cloudfront::418638389566:distribution/EDIST"
                                    )
                                }
                            },
                        },
                        {
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:*",
                            "Resource": [bucket, bucket + "/*"],
                            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                        },
                    ],
                }
            )
        }

        def aws(service, operation, *args, **kwargs):
            if operation == "get-policy" and "--qualifier" not in args:
                return None
            return deepcopy(self.responses[operation])

        self.op = SimpleNamespace(state=self.state, aws=aws, report={})

    def test_live_readback_contract_accepts_provider_descriptive_fields(self):
        o.verify_live(self.op, self.template)
        self.assertTrue(self.op.report["live_configuration_verified"])

    def test_each_security_boundary_rejects_drift(self):
        mutations = [
            (
                "runtime-boundary",
                lambda: self.responses["get-role"]["Role"].update(PermissionsBoundary={}),
            ),
            (
                "public-bucket-policy",
                lambda: self.responses["get-bucket-policy"].update(Policy="{}"),
            ),
            (
                "unencrypted-bucket",
                lambda: self.responses["get-bucket-encryption"].update(
                    ServerSideEncryptionConfiguration={}
                ),
            ),
            (
                "image",
                lambda: self.responses["get-function"]["Code"].update(ResolvedImageUri="foreign"),
            ),
            (
                "origin",
                lambda: self.responses["get-function"]["Configuration"]["Environment"][
                    "Variables"
                ].update(FITFINITY_AUTH_ORIGINS='["https://foreign.example"]'),
            ),
            (
                "role",
                lambda: self.responses["list-attached-role-policies"]["AttachedPolicies"].append(
                    {"PolicyArn": "AdministratorAccess"}
                ),
            ),
            ("alias", lambda: self.responses["get-alias"].update(FunctionVersion="2")),
            (
                "concurrency",
                lambda: self.responses["get-function-concurrency"].update(
                    ReservedConcurrentExecutions=20
                ),
            ),
            (
                "cache",
                lambda: self.responses["get-distribution"]["Distribution"]["DistributionConfig"][
                    "CacheBehaviors"
                ]["Items"][0].update(CachePolicyId="cache-enabled"),
            ),
            (
                "public-bucket",
                lambda: self.responses["get-public-access-block"][
                    "PublicAccessBlockConfiguration"
                ].update(BlockPublicPolicy=False),
            ),
            (
                "trace",
                lambda: self.responses["get-stage"]["methodSettings"]["*/*"].update(
                    dataTraceEnabled=True
                ),
            ),
            (
                "edge-sampling",
                lambda: self.responses["get-web-acl"]["WebACL"]["VisibilityConfig"].update(
                    SampledRequestsEnabled=True
                ),
            ),
            (
                "origin-bucket",
                lambda: self.responses["get-distribution"]["Distribution"]["DistributionConfig"][
                    "Origins"
                ]["Items"][1].update(DomainName="foreign.s3.amazonaws.com"),
            ),
        ]
        initial = deepcopy(self.responses)
        for name, mutate in mutations:
            with self.subTest(boundary=name):
                self.responses = deepcopy(initial)
                mutate()
                with self.assertRaises(RuntimeError):
                    o.verify_live(self.op, self.template)


class CheckoutGuardTests(unittest.TestCase):
    def setUp(self):
        source_env = patch.dict(os.environ, {"GITHUB_SHA": d.ADAPTATION_BASE})
        source_env.start()
        self.addCleanup(source_env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "checkout"
        self.repo.mkdir()
        (self.repo / "main.js").write_text("export const api = true;\n")
        raw = (self.repo / "main.js").read_bytes()
        self.blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.hidden = False

        def run(*args):
            if args[0] == "update-index":
                self.hidden = True
                return ""
            if args[0] == "status":
                return ""
            raise AssertionError(args)

        self.git = run

        def git(repo, *args):
            if args == ("rev-parse", "--show-toplevel"):
                return str(self.repo).encode()
            if args == ("rev-parse", "HEAD"):
                return d.ADAPTATION_BASE.encode()
            if args[0] == "status":
                return b"extra" if (self.repo / "unreviewed.js").exists() else b""
            if args[0] == "ls-tree":
                return f"100644 blob {self.blob}\tmain.js\0".encode()
            if args[0] == "ls-files":
                return f"100644 {self.blob} 0\tmain.js\0".encode()
            raise AssertionError(args)

        self.source_git = git
        patcher = patch.object(f, "git", side_effect=git)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_real_clean_git_checkout_accepts_complete_manifest(self):
        self.assertEqual(f.source_check(self.repo)["source_files"], 1)

    def test_assume_unchanged_cannot_hide_modified_source(self):
        self.git("update-index", "--assume-unchanged", "main.js")
        (self.repo / "main.js").write_text("changed despite clean git status")
        self.assertEqual(self.git("status", "--porcelain"), "")
        with self.assertRaisesRegex(RuntimeError, "source bytes differ"):
            f.source_check(self.repo)

    def test_untracked_source_and_redirected_checkout_are_refused(self):
        (self.repo / "unreviewed.js").write_text("extra")
        with self.assertRaisesRegex(RuntimeError, "untracked"):
            f.source_check(self.repo)
        (self.repo / "unreviewed.js").unlink()
        link = self.root / "redirect"
        link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "redirected"):
            f.source_check(link)

    def test_index_and_manifest_mismatch_is_refused(self):
        with patch.object(
            f,
            "git",
            side_effect=lambda repo, *args: (
                b"" if args[0] == "ls-tree" else self.source_git(repo, *args)
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "inventory differs"):
                f.source_check(self.repo)


class NodeActivationTests(unittest.TestCase):
    def test_existing_nvm_activation_with_spaces_is_child_process_only(self):
        with tempfile.TemporaryDirectory(prefix="fitfinity node ") as temp:
            root = Path(temp)
            bindir = root / "bin"
            bindir.mkdir()
            node = bindir / "node"
            data = json.dumps({"executable": str(node), "version": "v24.1.0"})
            node.write_text(
                '#!/bin/bash\nif [ "$1" = "-p" ]; then echo 24; else cat <<\'JSON\'\n'
                + data
                + "\nJSON\nfi\n"
            )
            node.chmod(0o700)
            nvm = root / "nvm"
            nvm.mkdir()
            (nvm / "nvm.sh").write_text('nvm() { export PATH="$NVM_DIR/../bin:$PATH"; }\n')
            original = os.environ.copy()
            with patch.dict(
                os.environ,
                {
                    "PATH": "/usr/bin:/bin",
                    "HOME": temp,
                    "NVM_DIR": str(nvm),
                    "VITE_PORTAL_MODE": "mock",
                    "NODE_OPTIONS": "--unreviewed",
                },
                clear=True,
            ):
                with patch.object(
                    f.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, data, "")
                ) as runner:
                    env, info = f.node_environment()
                    self.assertNotIn("NODE_OPTIONS", runner.call_args.kwargs["env"])
                self.assertEqual(info["version"], "v24.1.0")
                self.assertEqual(env["PATH"].split(os.pathsep)[0], str(bindir))
                self.assertNotIn("VITE_PORTAL_MODE", env)
                self.assertNotIn("NODE_OPTIONS", env)
                self.assertEqual(os.environ["PATH"], "/usr/bin:/bin")
            self.assertEqual(os.environ, original)

    def test_missing_existing_node24_stops_without_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(
                os.environ, {"PATH": "/usr/bin:/bin", "HOME": temp, "NVM_DIR": temp}, clear=True
            ):
                with patch.object(
                    f.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 1, "", "missing"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "could not be activated"):
                        f.node_environment()


class CloudBindingTests(unittest.TestCase):
    def setUp(self):
        import hosting_binding as binding

        self.b = binding
        self.source = "a" * 40
        self.run = {
            "id": 42,
            "run_attempt": 1,
            "repository": {"full_name": binding.GITHUB_REPO},
            "head_repository": {"full_name": binding.GITHUB_REPO},
            "head_sha": self.source,
            "head_branch": "main",
            "event": "workflow_dispatch",
            "path": binding.WORKFLOW,
            "status": "completed",
            "conclusion": "success",
        }
        self.raw = self.zip({"release.json": b"{}"})
        self.artifact = {
            "id": 5,
            "expired": False,
            "name": "release-42-1",
            "workflow_run": {"id": 42, "head_sha": self.source},
            "digest": "sha256:" + hashlib.sha256(self.raw).hexdigest(),
        }

        def github(_image, path, binary=False):
            if path.endswith("/zip"):
                return self.raw
            if "/artifacts?" in path:
                return {"total_count": 1, "artifacts": [self.artifact]}
            return self.run

        patcher = patch.object(binding.ExistingImage, "github", github)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def zip(files):
        import io
        import zipfile

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for name, body in files.items():
                archive.writestr(name, body)
        return out.getvalue()

    def fetch(self):
        return self.b.artifact(42, "release-{run}-{attempt}", self.source)

    def test_authenticated_source_and_artifact_are_required(self):
        files, origin = self.fetch()
        self.assertEqual(files, {"release.json": b"{}"})
        self.assertEqual(origin["artifact_id"], 5)

    def test_wrong_source_fork_workflow_event_or_failed_run_rejected(self):
        original = deepcopy(self.run)
        mutations = {
            "head_sha": "b" * 40,
            "head_branch": "feature",
            "event": "push",
            "path": ".github/workflows/other.yml",
            "conclusion": "failure",
            "head_repository": {"full_name": "foreign/repo"},
        }
        for field, value in mutations.items():
            self.run = {**original, field: value}
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.fetch()

    def test_expired_wrong_name_or_rebound_artifact_rejected(self):
        original = deepcopy(self.artifact)
        for field, value in {
            "expired": True,
            "name": "foreign",
            "workflow_run": {"id": 99},
        }.items():
            self.artifact = {**original, field: value}
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.fetch()

    def test_modified_zip_and_wrong_expected_hash_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.b.artifact(42, "release-{run}-{attempt}", self.source, checksum="0" * 64)
        self.raw += b"changed"
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.fetch()

    def test_unsafe_paths_and_symlinks_refused(self):
        import io
        import zipfile

        for name in ["../outside", "/outside", "a\\outside"]:
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "Unsafe"):
                self.b.unpack(self.zip({name: b"x"}))
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "../outside")
        with self.assertRaisesRegex(RuntimeError, "Unsafe"):
            self.b.unpack(data.getvalue())

    def test_image_compatibility_checks_actual_backend_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "compatibility"):
                self.b.compatibility(Path(folder))

    def test_runtime_role_cannot_act_as_hosting_role(self):
        for role, accepted in [
            ("fitfinity-test-github-runtime", False),
            ("fitfinity-test-github-hosting", True),
        ]:
            with (
                patch.object(self.b.runtime, "actions_environment"),
                patch.object(
                    self.b.EvidenceAWS,
                    "__call__",
                    return_value={
                        "Account": d.ACCOUNT,
                        "Arn": f"arn:aws:sts::{d.ACCOUNT}:assumed-role/{role}/session",
                    },
                ),
            ):
                aws = self.b.EvidenceAWS({"calls": []})
                if accepted:
                    self.assertIn(role, aws.environment())
                else:
                    with self.assertRaisesRegex(RuntimeError, "Separate hosting"):
                        aws.environment()

    def test_release_refuses_wrong_image_source_configuration_and_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            original = directory / "original"
            original.mkdir()
            for name in ["index.html", "sw.js", "manifest.webmanifest"]:
                (original / name).write_text("fixture")
            inventory = f.inventory(original)
            compatibility = {
                "image_digest": self.b.runtime.DIGEST,
                "image_source": self.b.runtime.SOURCE,
            }
            manifest = {
                "operator_source": self.source,
                "frontend_source": {"revision": self.source},
                "compatibility": compatibility,
                "manifest": inventory,
                "frontend_build": {
                    "mode": "api",
                    "base_path": "/",
                    "api_base_url": "",
                    "pwa_verified": True,
                    "manifest_sha256": f.manifest_hash(inventory),
                },
            }
            files = {"frontend/" + name: (original / name).read_bytes() for name in inventory}
            cases = [
                lambda m: m.update(operator_source="b" * 40),
                lambda m: m["compatibility"].update(image_digest="sha256:" + "0" * 64),
                lambda m: m["frontend_build"].update(mode="demo"),
                lambda m: m["frontend_build"].update(pwa_verified=False),
            ]
            for i, mutate in enumerate(cases):
                bad = deepcopy(manifest)
                mutate(bad)
                with (
                    patch.object(
                        self.b,
                        "artifact",
                        return_value=({**files, "release.json": json.dumps(bad).encode()}, {}),
                    ),
                    patch.object(self.b, "compatibility", return_value=compatibility),
                ):
                    with self.assertRaises(RuntimeError):
                        self.b.release(42, self.source, directory / str(i))
            files["frontend/index.html"] = b"tampered"
            with (
                patch.object(
                    self.b,
                    "artifact",
                    return_value=({**files, "release.json": json.dumps(manifest).encode()}, {}),
                ),
                patch.object(self.b, "compatibility", return_value=compatibility),
            ):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    self.b.release(42, self.source, directory / "tampered")

    def test_recovery_refuses_different_operator_operation_or_image(self):
        state = {
            "operator_commit": self.source,
            "operation_id": "f" * 32,
            "operator_revision": d.REVISION,
            "image_digest": self.b.runtime.DIGEST,
        }
        for key in state:
            bad = {**state, key: "foreign"}
            with patch.object(
                self.b,
                "artifact",
                return_value=({"hosting/state.json": json.dumps(bad).encode()}, {}),
            ):
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    self.b.restore(42, "f" * 32, self.source)

    def test_historical_runtime_image_cannot_satisfy_current_proof(self):
        state = {"image_digest": "sha256:" + "0" * 64, "operator_commit": self.b.RUNTIME_SOURCE}
        receipt = {
            "checkpoint": state,
            "accepted": True,
            "aws_runtime_verified": True,
            "temporary_cleanup_complete": True,
            "application_deployed": False,
            "live_authentication_accepted": False,
        }
        files = {
            "private-runtime/state.json": json.dumps(state).encode(),
            "private-runtime/receipt.json": json.dumps(receipt).encode(),
        }
        with patch.object(self.b, "artifact", return_value=(files, {})):
            with self.assertRaisesRegex(RuntimeError, "Current-image"):
                self.b.runtime_proof({})


class ReviewPhaseTests(unittest.TestCase):
    setUp = ResumeTests.setUp

    def test_prepare_stops_before_execute_and_emits_bound_token(self):
        self.state["mode"] = "prepare"
        self.assertIsNone(self.op.create("edge", self.t))
        self.assertNotIn(("cloudformation", "execute-change-set"), self.aws.calls)
        token = self.report["review_token"]
        self.assertEqual(len(token), 64)
        self.state.update(mode="execute", review_token="0" * 64)
        with self.assertRaisesRegex(RuntimeError, "review token"):
            self.op.create("edge", self.t)
        self.state["review_token"] = token
        self.assertEqual(self.op.create("edge", self.t), {"WebAclArn": EDGE})

    def test_permission_denial_preserves_create_intent_without_retry(self):
        original = self.aws

        def denied(service, operation, *args, **kwargs):
            if operation == "create-change-set":
                raise RuntimeError("AccessDenied")
            return original(service, operation, *args, **kwargs)

        self.op.aws = denied
        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            self.op.create("edge", self.t)
        self.assertIn(
            "create_intent",
            json.loads((self.op.directory / "state.json").read_text())["stacks"]["edge"],
        )
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.op.create("edge", self.t)


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((o.ROOT / "test-github-hosting-role.json").read_text())
        self.resources = self.template["Resources"]

    def test_hosting_authority_is_separate_and_cannot_bootstrap_or_publish_image(self):
        role = self.resources["HostingRole"]["Properties"]
        self.assertEqual(role["RoleName"], "fitfinity-test-github-hosting")
        raw = json.dumps(role)
        for forbidden in [
            "GetSecretValue",
            "AdminCreateUser",
            "PutImage",
            "StartImageScan",
            "CreateStack",
            "lambda:InvokeFunction",
        ]:
            self.assertNotIn(forbidden, raw)
        subject = role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["StringEquals"][
            "token.actions.githubusercontent.com:sub"
        ]
        self.assertEqual(
            subject, "repo:LimYouSheng@141623519/FitfinityReact@1353173586:environment:aws-test"
        )

    def test_creation_and_passrole_are_bounded(self):
        statements = self.resources["CloudFormationRole"]["Properties"]["Policies"][0][
            "PolicyDocument"
        ]["Statement"]
        create = next(s for s in statements if "iam:CreateRole" in s["Action"])
        self.assertEqual(
            create["Resource"], "arn:aws:iam::418638389566:role/fitfinity-test-hosting-api"
        )
        self.assertEqual(
            create["Condition"]["StringEquals"]["iam:PermissionsBoundary"],
            "arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary",
        )
        for role in ["HostingRole", "CloudFormationRole"]:
            statements = self.resources[role]["Properties"]["Policies"][0]["PolicyDocument"][
                "Statement"
            ]
            for s in statements:
                self.assertNotIn("*", s["Action"])
                if "iam:PassRole" in s["Action"]:
                    self.assertNotIn("*", s["Resource"])
                    self.assertIn("iam:PassedToService", s["Condition"]["StringEquals"])

    def test_cloudfront_creation_uses_valid_action_and_required_request_tags(self):
        rows = self.resources["CloudFormationRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ]
        create = [row for row in rows if "cloudfront:CreateDistribution" in row["Action"]]
        self.assertEqual(len(create), 1)
        self.assertEqual(create[0]["Resource"], "*")
        expected = {
            "aws:RequestTag/Application": "Fitfinity",
            "aws:RequestTag/Environment": "test",
            "aws:RequestTag/Purpose": "first-login-v1",
        }
        self.assertEqual(create[0]["Condition"]["StringEquals"], expected)
        self.assertNotIn("cloudfront:CreateDistributionWithTags", json.dumps(rows))
        tags = d.app_template(PREFIX, EDGE)["Resources"]["Distribution"]["Properties"]["Tags"]
        self.assertEqual({"aws:RequestTag/" + t["Key"]: t["Value"] for t in tags}, expected)

    def test_runtime_boundary_matches_exact_application_policy(self):
        self.assertEqual(
            self.resources["ApiBoundary"]["Properties"]["PolicyDocument"], d.runtime_policy()
        )
        template = d.app_template(PREFIX, EDGE)
        props = template["Resources"]["ApiRole"]["Properties"]
        self.assertEqual(
            props["PermissionsBoundary"],
            "arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary",
        )
        self.assertEqual(props["RoleName"], "fitfinity-test-hosting-api")


class EntryPointTests(unittest.TestCase):
    def test_failed_initial_smoke_never_records_deployment_acceptance(self):
        from contextlib import ExitStack

        source, operation, token = "a" * 40, "f" * 32, "b" * 64
        state = {
            "operator_commit": source,
            "operator_revision": d.REVISION,
            "operation_id": operation,
            "image_digest": o.pf.binding.DIGEST,
            "stacks": {
                "edge": {"complete": True, "outputs": {"WebAclArn": EDGE}},
                "app": {
                    "create_intent": {},
                    "review_token": token,
                    "execute_intent": {"sent": True},
                },
            },
        }
        state["stacks"]["app"]["create_intent"] = {"sent": True}
        release = {
            "prefix": PREFIX,
            "manifest": {},
            "artifact": {"run_id": 12},
            "directory": "fixture",
        }

        class FakeOperator:
            def __init__(self, directory, state, report):
                self.state, self.report = state, report
                self.aws = lambda *args, **kwargs: None

            def save(self):
                pass

            def create(self, key, template):
                return {"FrontendDomain": "dexample.cloudfront.net"}

            def upload(self):
                self.state["frontend_uploaded"] = True

            def stack(self, key):
                return {"StackStatus": "CREATE_COMPLETE"}

            def check_template(self, key):
                pass

        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            for target in [
                "hosting_operator.pf.binding.actions_environment",
                "hosting_operator.pf.binding.collect_binding",
                "hosting_operator.pf.collect",
                "hosting_operator.binding.runtime_proof",
                "hosting_operator.verify_live",
                "private_runtime.RuntimeOperator.verify_ecr_pull_policy",
            ]:
                stack.enter_context(patch(target))
            stack.enter_context(
                patch.object(
                    o.pf.binding,
                    "verify_main",
                    side_effect=lambda report: report.update(operator_commit=source),
                )
            )
            stack.enter_context(patch.object(o.binding, "restore", return_value=(state, {})))
            stack.enter_context(patch.object(o.binding, "release", return_value=release))
            stack.enter_context(
                patch.object(o.binding.EvidenceAWS, "environment", return_value="hosting-role")
            )
            stack.enter_context(patch.object(o, "Operator", FakeOperator))
            stack.enter_context(
                patch.object(o, "smoke", side_effect=RuntimeError("Public smoke failed"))
            )
            directory = Path(folder) / "evidence"
            result = o.main(
                [
                    "--mode",
                    "execute",
                    "--operation-id",
                    operation,
                    "--directory",
                    str(directory),
                    "--release-run",
                    "12",
                    "--resume-run",
                    "13",
                    "--review-token",
                    token,
                ]
            )
            self.assertEqual(result, 1)
            receipt = json.loads((directory / "receipt.json").read_text())
            self.assertEqual(receipt["error"], "Public smoke failed")
            self.assertFalse(receipt["application_deployed"])
            self.assertFalse(receipt["live_authentication_accepted"])
            self.assertFalse(receipt["checkpoint"].get("complete", False))
            self.assertTrue(receipt["checkpoint"]["frontend_uploaded"])


class SourceTransitionTests(unittest.TestCase):
    def setUp(self):
        from contextlib import ExitStack

        self.b = o.binding
        self.source = "c" * 40
        self.original = {
            "operator_commit": self.b.TRANSITION_SOURCE,
            "operator_revision": d.REVISION,
            "operation_id": self.b.TRANSITION_OPERATION,
            "image_digest": self.b.runtime.DIGEST,
            "frontend": {"prefix": "original-release", "artifact": {"run_id": 37885447016}},
            "stacks": {
                "edge": {
                    "create_response_received": True,
                    "create_intent": {"arguments_sha256": "retained", "at": "original-time"},
                    "stack_id": "pinned-stack",
                    "change_set_id": "pinned-change",
                }
            },
        }
        self.raw = json.dumps(self.original).encode()
        self.files = {
            "hosting/state.json": self.raw,
            "hosting/receipt.json": json.dumps(
                {
                    "checkpoint": self.original,
                    "status": "stopped",
                    "error": "Stack ownership tags differ",
                }
            ).encode(),
        }
        self.pr = {
            "merged": True,
            "merged_by": {"login": "LimYouSheng"},
            "merge_commit_sha": self.source,
            "base": {"ref": "main", "repo": {"full_name": self.b.GITHUB_REPO}},
            "head": {"repo": {"full_name": self.b.GITHUB_REPO}},
        }
        self.origin = {
            "artifact_id": self.b.TRANSITION_ARTIFACT,
            "sha256": self.b.TRANSITION_ZIP_SHA,
        }
        stack = self.enterContext(ExitStack())
        self.github = stack.enter_context(
            patch.object(self.b.ExistingImage, "github", return_value=self.pr)
        )
        self.artifact = stack.enter_context(
            patch.object(self.b, "artifact", return_value=(self.files, self.origin))
        )
        stack.enter_context(patch.object(self.b, "TRANSITION_STATE_SHA", self.b.sha(self.raw)))

    def restore(self):
        return self.b.restore_transition(
            self.b.TRANSITION_RUN, self.b.TRANSITION_OPERATION, self.source
        )

    def test_exact_transition_preserves_original_checkpoint_and_pinned_inputs(self):
        state, origin = self.restore()
        self.assertEqual(state["operator_commit"], self.source)
        self.assertEqual(state["stacks"], self.original["stacks"])
        self.assertEqual(state["source_transition"]["original_checkpoint"], self.original)
        self.assertEqual(state["source_transition"]["state_sha256"], self.b.sha(self.raw))
        self.assertFalse(state["execution_authorized"])
        self.assertEqual(origin, self.origin)
        self.github.assert_called_once_with(f"repos/{self.b.GITHUB_REPO}/pulls/19")
        self.artifact.assert_called_once_with(
            self.b.TRANSITION_RUN,
            "fitfinity-hosting-" + self.b.TRANSITION_OPERATION + "-{run}-{attempt}",
            self.b.TRANSITION_SOURCE,
            success=False,
            artifact_id=self.b.TRANSITION_ARTIFACT,
            checksum=self.b.TRANSITION_ZIP_SHA,
        )
        state["stacks"]["edge"]["create_intent"]["at"] = "changed"
        self.assertEqual(state["source_transition"]["original_checkpoint"], self.original)
        self.assertEqual(self.files["hosting/state.json"], self.raw)

    def test_transition_refuses_unmerged_foreign_or_advanced_source(self):
        for change in [
            {"merged": False},
            {"merged_by": {"login": "other"}},
            {"merge_commit_sha": "d" * 40},
            {"base": {"ref": "feature", "repo": {"full_name": self.b.GITHUB_REPO}}},
            {"head": {"repo": {"full_name": "foreign/repository"}}},
        ]:
            with (
                self.subTest(change=change),
                patch.object(self.b.ExistingImage, "github", return_value={**self.pr, **change}),
            ):
                with self.assertRaisesRegex(RuntimeError, "owner-merged"):
                    self.restore()
        self.artifact.assert_not_called()

    def test_transition_refuses_different_operation_or_run(self):
        for run, operation in [(1, self.b.TRANSITION_OPERATION), (self.b.TRANSITION_RUN, "f" * 32)]:
            with self.subTest(run=run, operation=operation), self.assertRaises(RuntimeError):
                self.b.restore_transition(run, operation, self.source)
        self.github.assert_not_called()
        self.artifact.assert_not_called()

    def test_transition_refuses_changed_bytes_or_receipt(self):
        self.files["hosting/state.json"] = self.raw + b" "
        with self.assertRaisesRegex(RuntimeError, "checkpoint differs"):
            self.restore()
        self.files["hosting/state.json"] = self.raw
        self.files["hosting/receipt.json"] = b"{}"
        with self.assertRaisesRegex(RuntimeError, "unexecuted checkpoint"):
            self.restore()

    def test_transition_refuses_executed_uploaded_or_already_transitioned_state(self):
        for changed in [
            {"frontend_uploaded": True},
            {"complete": True},
            {"source_transition": {"review_pr": 19}},
            {
                "stacks": {
                    "edge": {**self.original["stacks"]["edge"], "execute_intent": {"sent": True}}
                }
            },
            {"stacks": {"edge": self.original["stacks"]["edge"], "app": {}}},
        ]:
            state = {**self.original, **changed}
            raw = json.dumps(state).encode()
            self.files["hosting/state.json"] = raw
            self.files["hosting/receipt.json"] = json.dumps(
                {"checkpoint": state, "status": "stopped", "error": "Stack ownership tags differ"}
            ).encode()
            with (
                self.subTest(changed=changed),
                patch.object(self.b, "TRANSITION_STATE_SHA", self.b.sha(raw)),
            ):
                with self.assertRaisesRegex(RuntimeError, "unexecuted checkpoint"):
                    self.restore()

    def test_normal_restore_still_refuses_old_source_and_incomplete_transition(self):
        with self.assertRaisesRegex(RuntimeError, "Recovery identity"):
            self.b.restore(self.b.TRANSITION_RUN, self.b.TRANSITION_OPERATION, self.source)
        state, _ = self.restore()
        self.files["hosting/state.json"] = json.dumps(state).encode()
        with self.assertRaisesRegex(RuntimeError, "Recovery identity"):
            self.b.restore(123, self.b.TRANSITION_OPERATION, self.source)
        state["source_transition"]["reconciled"] = True
        self.files["hosting/state.json"] = json.dumps(state).encode()
        restored, _ = self.b.restore(123, self.b.TRANSITION_OPERATION, self.source)
        self.assertEqual(restored, state)

    def test_transition_disables_every_cloud_write_before_runner(self):
        state, _ = self.restore()
        runner = unittest.mock.Mock()
        aws = o.HostingAWS(o.pf.receipt_initial(), state, lambda: None, runner=runner)
        for service, action in o.WRITES:
            with (
                self.subTest(action=action),
                self.assertRaisesRegex(RuntimeError, "not authorized"),
            ):
                aws(service, action, region="ap-southeast-1")
        runner.assert_not_called()

    def test_transition_flag_refuses_execution_and_unbound_plan(self):
        for mode in ["plan", "execute", "verify", "rollback", "prepare"]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder) / "evidence"
                result = o.main(
                    [
                        "--mode",
                        mode,
                        "--operation-id",
                        self.b.TRANSITION_OPERATION,
                        "--directory",
                        str(directory),
                        "--source-transition",
                    ]
                )
                self.assertEqual(result, 1)
                receipt = json.loads((directory / "receipt.json").read_text())
                self.assertEqual(receipt["cloud_writes"], [])
                self.assertIn("read-only prepare", receipt["error"])

    def test_entry_point_transition_reconciles_without_replacing_identities(self):
        from contextlib import ExitStack

        for status, execution in [
            (None, "AVAILABLE"),
            ("CREATE_COMPLETE", "AVAILABLE"),
            ("REVIEW_IN_PROGRESS", "UNAVAILABLE"),
            ("REVIEW_IN_PROGRESS", "EXECUTE_COMPLETE"),
            ("REVIEW_IN_PROGRESS", "AVAILABLE"),
        ]:
            with (
                self.subTest(status=status, execution=execution),
                tempfile.TemporaryDirectory() as folder,
                ExitStack() as stack,
            ):
                state, _ = self.restore()
                before = deepcopy(state["stacks"])
                release = {
                    "prefix": "releases/" + self.source + "/new",
                    "artifact": {"run_id": 99},
                    "manifest": {},
                    "directory": "new-directory",
                }

                class FakeOperator:
                    def __init__(
                        inner,
                        directory,
                        state,
                        report,
                        stack_status=status,
                        change_execution=execution,
                        expected_stacks=before,
                    ):
                        inner.state, inner.report = state, report
                        inner.stack_status = stack_status
                        inner.expected_stacks = expected_stacks
                        inner.aws = unittest.mock.Mock(
                            return_value={
                                "StackId": "pinned-stack",
                                "ChangeSetId": "pinned-change",
                                "Status": "CREATE_COMPLETE",
                                "ExecutionStatus": change_execution,
                            }
                        )

                    def save(inner):
                        pass

                    def stack(inner, key):
                        return {"StackStatus": inner.stack_status} if inner.stack_status else None

                    def create(inner, key, template):
                        self.assertFalse(inner.state["execution_authorized"])
                        self.assertEqual(key, "edge")
                        self.assertEqual(inner.state["stacks"], inner.expected_stacks)
                        inner.report["status"] = "change_set_review_required"

                for target in [
                    "hosting_operator.pf.binding.actions_environment",
                    "hosting_operator.pf.binding.collect_binding",
                    "hosting_operator.pf.collect",
                    "hosting_operator.binding.runtime_proof",
                    "private_runtime.RuntimeOperator.verify_ecr_pull_policy",
                ]:
                    stack.enter_context(patch(target))
                stack.enter_context(
                    patch.object(
                        o.pf.binding,
                        "verify_main",
                        side_effect=lambda report: report.update(operator_commit=self.source),
                    )
                )
                stack.enter_context(
                    patch.object(self.b, "restore_transition", return_value=(state, self.origin))
                )
                stack.enter_context(patch.object(self.b, "release", return_value=release))
                stack.enter_context(
                    patch.object(self.b.EvidenceAWS, "environment", return_value="hosting-role")
                )
                stack.enter_context(patch.object(o, "Operator", FakeOperator))
                directory = Path(folder) / "evidence"
                result = o.main(
                    [
                        "--mode",
                        "prepare",
                        "--operation-id",
                        self.b.TRANSITION_OPERATION,
                        "--directory",
                        str(directory),
                        "--resume-run",
                        str(self.b.TRANSITION_RUN),
                        "--release-run",
                        "99",
                        "--source-transition",
                    ]
                )
                receipt = json.loads((directory / "receipt.json").read_text())
                self.assertEqual(
                    result, 0 if status == "REVIEW_IN_PROGRESS" and execution == "AVAILABLE" else 1
                )
                self.assertEqual(receipt["cloud_writes"], [])
                self.assertEqual(receipt["checkpoint"]["stacks"], before)
                self.assertEqual(
                    receipt["checkpoint"]["source_transition"]["original_checkpoint"], self.original
                )
                if result == 0:
                    self.assertTrue(receipt["checkpoint"]["source_transition"]["reconciled"])
                    self.assertEqual(receipt["checkpoint"]["frontend"], release)


if __name__ == "__main__":
    unittest.main(verbosity=2)
