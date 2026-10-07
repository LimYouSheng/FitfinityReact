import asyncio
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import private_runtime as op
import private_runtime_design as design
import private_runtime_preflight as pf

ROOT = Path(__file__).parent
PACKAGE = ROOT

STAMP = datetime(2026, 10, 4, 15, 15, tzinfo=UTC)


def valid_result(contract, nonce, action):
    value = {
        "ok": True,
        "nonce": nonce,
        "action": action,
        "runtime_identity": [993, 993, 990, 990],
        "image_digest": contract["image_digest"],
        "revision": contract["revision"],
        "stage": "complete",
        "source_files_verified": 54,
        "dependencies_verified": 33,
    }
    if action == "current-runtime":
        value.update(
            proof={
                "secret_version_id": pf.deploy.CONFIG["auth_version"],
                "auth_secret_verified": True,
                "encryption_verified": True,
                "cognito_checks": 18,
                "managed_settings_verified": True,
                "database_read_only": True,
                "target_revision": "20260924_0006",
                "user": "fitfinity_app",
                "database": "fitfinity",
                "sslmode": "verify-full",
                "tls": "TLSv1.3",
                "server_version_num": 170011,
            },
            jwks_reachable=True,
            jwks_key_count=2,
            application_startup_verified=True,
            application_shutdown_verified=True,
            liveness_status=200,
            readiness_status=200,
            untrusted_host_status=400,
        )
    return value


class FakeCLI:
    def __init__(self):
        self.metadata = {}
        self.exists = False
        self.deleted = False
        self.stack_id = (
            f"arn:aws:cloudformation:{op.REGION}:{op.ACCOUNT}:stack/{design.STACK}/offline-fixture"
        )
        self.template = None
        self.physical_ids = {}
        self.tags = []
        self.counts = {}
        self.lose = None
        self.omit_response = False
        self.logs = {}
        self.fail_proof = False
        self.drift = None
        self.pull_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                }
            ],
        }
        self.source, self.contract = design.source_bundle()

    def reply(self, value):
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr="")

    def absent(self, code="ResourceNotFoundException", message="missing"):
        return SimpleNamespace(
            returncode=254, stdout="", stderr=f"An error occurred ({code}): {message}"
        )

    def __call__(self, command, **kwargs):
        assert command[0] == "aws", command
        service, action = command[1:3]
        args = command[3 : command.index("--region")]

        def value(flag):
            return args[args.index(flag) + 1]

        pair = service, action
        self.counts[pair] = self.counts.get(pair, 0) + 1
        key = service, action, tuple(args)
        if key in self.metadata:
            return self.reply(copy.deepcopy(self.metadata[key]))
        if pair == ("ecr", "get-repository-policy"):
            return self.reply(
                {
                    "registryId": op.ACCOUNT,
                    "repositoryName": "fitfinity-test-api",
                    "policyText": json.dumps(self.pull_policy),
                }
            )
        if pair == ("cloudformation", "create-stack"):
            assert not self.exists
            self.exists = True
            self.deleted = False
            self.physical_ids = {}
            self.stack_id = (
                f"arn:aws:cloudformation:{op.REGION}:{op.ACCOUNT}:"
                f"stack/{design.STACK}/offline-fixture"
            )
            self.template = json.loads(
                Path(value("--template-body").removeprefix("file://")).read_text()
            )
            self.tags = [
                {
                    "Key": item.split(",Value=")[0].removeprefix("Key="),
                    "Value": item.split(",Value=")[1],
                }
                for item in args[args.index("--tags") + 1 :]
            ]
            if self.lose == action:
                self.lose = None
                raise subprocess.TimeoutExpired(command, 90)
            return self.reply({"StackId": self.stack_id})
        if pair == ("cloudformation", "describe-stacks"):
            if not self.exists:
                if self.deleted and value("--stack-name") == self.stack_id:
                    return self.reply(
                        {"Stacks": [{"StackId": self.stack_id, "StackStatus": "DELETE_COMPLETE"}]}
                    )
                return self.absent(
                    "ValidationError", f"Stack with id {value('--stack-name')} does not exist"
                )
            return self.reply(
                {
                    "Stacks": [
                        {
                            "StackName": design.STACK,
                            "StackId": self.stack_id,
                            "StackStatus": "CREATE_COMPLETE",
                            "Tags": self.tags,
                        }
                    ]
                }
            )
        if pair == ("cloudformation", "get-template"):
            return self.reply({"TemplateBody": self.template})
        if pair == ("cloudformation", "list-stack-resources"):
            rows = []
            for name, resource in self.template["Resources"].items():
                props = resource["Properties"]
                identity = (
                    props.get("FunctionName")
                    or props.get("LogGroupName")
                    or design.STACK + "-" + name + "-fixture"
                )
                identity = self.physical_ids.get(name, identity)
                rows.append(
                    {
                        "LogicalResourceId": name,
                        "PhysicalResourceId": identity,
                        "ResourceType": resource["Type"],
                        "ResourceStatus": "CREATE_COMPLETE",
                    }
                )
            return self.reply({"StackResourceSummaries": rows})
        if pair == ("cloudformation", "delete-stack"):
            assert value("--stack-name") == self.stack_id
            self.exists, self.deleted = False, True
            if self.lose == action:
                self.lose = None
                raise subprocess.TimeoutExpired(command, 90)
            return self.reply({})
        if service == "lambda":
            name = value("--function-name")
            prefix = next(p for p, n in design.NAMES.items() if n == name)
            if not self.exists or action in {"get-policy", "get-function-url-config"}:
                return self.absent()
            if action == "list-event-source-mappings":
                return self.reply({"EventSourceMappings": []})
            if action == "get-function":
                properties = self.template["Resources"][prefix + "Function"]["Properties"]
                conf = {
                    k: copy.deepcopy(properties[k])
                    for k in [
                        "PackageType",
                        "Architectures",
                        "Timeout",
                        "MemorySize",
                        "Environment",
                        "VpcConfig",
                    ]
                }
                conf.update(
                    FunctionArn=f"arn:aws:lambda:{op.REGION}:{op.ACCOUNT}:function:{name}",
                    State="Active",
                    LastUpdateStatus="Successful",
                    Role=f"arn:aws:iam::{op.ACCOUNT}:role/"
                    + self.physical_ids.get(
                        prefix + "Role", f"{design.STACK}-{prefix}Role-fixture"
                    ),
                    ImageConfigResponse={"ImageConfig": copy.deepcopy(properties["ImageConfig"])},
                )
                conf["VpcConfig"]["VpcId"] = "vpc-0b55320bb1a054441"
                if self.drift == "network":
                    conf["VpcConfig"]["SubnetIds"] = ["wrong"]
                result = {
                    "Configuration": conf,
                    "Code": {"ResolvedImageUri": properties["Code"]["ImageUri"]},
                }
                if self.drift == "image":
                    result["Code"]["ResolvedImageUri"] = "wrong"
                return self.reply(result)
            if action == "invoke":
                event = json.loads(Path(value("--payload").removeprefix("fileb://")).read_text())
                body = json.loads(event["body"])
                result = valid_result(self.contract, body["nonce"], body["action"])
                if self.fail_proof and body["action"] == "current-runtime":
                    result = {
                        "ok": False,
                        "nonce": body["nonce"],
                        "stage": "read_only_database",
                        "error_type": "RuntimeError",
                    }
                self.logs[body["nonce"]] = result
                if not self.omit_response:
                    Path(args[-1]).write_text(
                        json.dumps({"statusCode": 200, "body": json.dumps(result)})
                    )
                if self.lose == action:
                    self.lose = None
                    raise subprocess.TimeoutExpired(command, 200)
                return self.reply({"StatusCode": 200})
        if service == "iam":
            if not self.exists:
                return self.absent("NoSuchEntity")
            role_name = value("--role-name")
            prefix = "Setup" if "SetupRole" in role_name else "Application"
            props = self.template["Resources"][prefix + "Role"]["Properties"]
            if action == "get-role":
                return self.reply(
                    {
                        "Role": {
                            "Arn": f"arn:aws:iam::{op.ACCOUNT}:role/{role_name}",
                            "AssumeRolePolicyDocument": props["AssumeRolePolicyDocument"],
                            "PermissionsBoundary": {
                                "PermissionsBoundaryArn": props["PermissionsBoundary"]
                            },
                        }
                    }
                )
            if action == "list-role-policies":
                return self.reply({"PolicyNames": [design.POLICY]})
            if action == "list-attached-role-policies":
                return self.reply({"AttachedPolicies": []})
            if action == "get-role-policy":
                policy = copy.deepcopy(props["Policies"][0]["PolicyDocument"])
                if self.drift == "iam":
                    policy["Statement"][0]["Resource"] = "*"
                return self.reply({"PolicyDocument": policy})
        if pair == ("logs", "describe-log-groups"):
            return self.reply(
                {
                    "logGroups": [
                        {"logGroupName": value("--log-group-name-prefix"), "retentionInDays": 1}
                    ]
                    if self.exists
                    else []
                }
            )
        if pair == ("logs", "filter-log-events"):
            nonce = value("--filter-pattern").split('"')[-2]
            result = self.logs.get(nonce)
            return self.reply(
                {
                    "events": [{"message": "FITFINITY_RUNTIME_PROOF " + json.dumps(result)}]
                    if result
                    else []
                }
            )
        raise AssertionError("Unexpected offline AWS call " + repr((service, action, args)))


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.report = pf.receipt_initial()
        self.state = {"operation_id": "a" * 32, "execution_authorized": True}
        self.cli = FakeCLI()
        self.checkpoints = []

        def checkpoint():
            op.atomic_json(self.path / "state.json", self.state)
            self.checkpoints.append(copy.deepcopy(self.state))

        self.aws = op.RuntimeAWS(self.report, self.state, checkpoint, runner=self.cli)
        self.operator = op.RuntimeOperator(
            self.aws, self.state, self.report, self.path, checkpoint, sleeper=lambda s: None
        )
        self.report.update(
            approval=pf.binding.local_approval(),
            candidate_provenance=pf.binding.local_approval()["provenance"],
            candidate={},
        )
        self.addCleanup(patch.stopall)
        patch.object(pf, "now", return_value=datetime(2026, 10, 7, 13, 0, tzinfo=UTC)).start()
        patch.object(pf, "collect").start()
        patch.object(pf, "image_review").start()
        patch.object(pf, "secrets_review").start()
        patch.object(pf.EvidenceAWS, "environment", return_value="offline-runtime-role").start()
        patch.dict(os.environ, {}, clear=True).start()

    def test_full_metadata_to_two_subnet_runtime_and_cleanup(self):
        self.operator.run()
        self.assertTrue(self.state["complete"])
        self.assertTrue(self.report["aws_runtime_verified"])
        self.assertTrue(self.report["temporary_cleanup_complete"])
        self.assertEqual(self.cli.counts[("lambda", "invoke")], 4)
        self.assertEqual(self.cli.counts[("cloudformation", "create-stack")], 1)
        self.assertEqual(self.cli.counts[("cloudformation", "delete-stack")], 1)
        self.assertFalse(self.report["application_deployed"])
        self.assertFalse(self.report["scan_policy_passed"])
        self.assertFalse(self.report["owner_created"])

    def test_completed_rerun_is_noop(self):
        self.operator.run()
        counts = dict(self.cli.counts)
        self.operator.run()
        self.assertEqual(counts, self.cli.counts)
        self.assertEqual(self.report["status"], "previous_runtime_proof_complete_noop")

    def test_create_lost_response_resumes_without_duplicate_create(self):
        self.cli.lose = "create-stack"
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.operator.run()
        self.assertTrue(self.state["create_intent"])
        self.operator.run()
        self.assertEqual(self.cli.counts[("cloudformation", "create-stack")], 1)
        self.assertTrue(self.state["complete"])

    def test_lost_invocation_recovers_response_without_duplicate(self):
        self.cli.lose = "invoke"
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.operator.run()
        self.operator.run()
        self.assertEqual(self.cli.counts[("lambda", "invoke")], 4)

    def test_lost_invocation_recovers_nonce_bound_log_without_duplicate(self):
        self.cli.lose, self.cli.omit_response = "invoke", True
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.operator.run()
        self.cli.omit_response = False
        self.operator.run()
        self.assertEqual(self.cli.counts[("lambda", "invoke")], 4)
        self.assertEqual(self.cli.counts[("logs", "filter-log-events")], 1)

    def test_uncertain_invocation_without_evidence_is_never_resent(self):
        self.cli.lose, self.cli.omit_response = "invoke", True
        with self.assertRaises(RuntimeError):
            self.operator.run()
        self.cli.logs.clear()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.operator.run()
        self.assertEqual(self.cli.counts[("lambda", "invoke")], 1)
        self.assertTrue(self.cli.exists)

    def test_lost_delete_response_resumes_cleanup_without_duplicate(self):
        self.cli.lose = "delete-stack"
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.operator.run()
        self.operator.run()
        self.assertTrue(self.state["complete"])
        self.assertEqual(self.cli.counts[("cloudformation", "delete-stack")], 1)

    def test_runtime_failure_preserves_resources_and_does_not_retry(self):
        self.cli.fail_proof = True
        with self.assertRaisesRegex(RuntimeError, "proof failed"):
            self.operator.run()
        self.assertTrue(self.cli.exists)
        self.assertNotIn(("cloudformation", "delete-stack"), self.cli.counts)
        count = self.cli.counts[("lambda", "invoke")]
        with self.assertRaisesRegex(RuntimeError, "recorded runtime proof failed"):
            self.operator.run()
        self.assertEqual(self.cli.counts[("lambda", "invoke")], count)
        self.operator.cleanup()
        self.assertTrue(self.state["temporary_cleanup_complete"])
        self.assertFalse(self.report["aws_runtime_verified"])

    def test_changed_live_image_network_and_iam_stop_before_invocation(self):
        for drift in ["image", "network", "iam"]:
            with self.subTest(drift=drift):
                self.cli.drift = drift
                with self.assertRaises(RuntimeError):
                    self.operator.run()
                self.assertNotIn(("lambda", "invoke"), self.cli.counts)
                self.assertNotIn(("cloudformation", "delete-stack"), self.cli.counts)

    def test_preexisting_stack_is_not_adopted(self):
        self.cli.exists = True
        self.cli.template = self.operator.template
        with self.assertRaisesRegex(RuntimeError, "not owned"):
            self.operator.run()
        self.assertNotIn(("cloudformation", "create-stack"), self.cli.counts)

    def test_missing_stack_after_create_intent_is_not_recreated(self):
        self.state["create_intent"] = {"client_request_token": "uncertain"}
        with self.assertRaisesRegex(RuntimeError, "No duplicate create"):
            self.operator.ensure_stack()
        self.assertNotIn(("cloudformation", "create-stack"), self.cli.counts)

    def test_forged_write_intent_cannot_target_foundation(self):
        self.state["stack_id"] = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:"
            "stack/fitfinity-test-foundation/unknown"
        )
        self.state["delete_intent"] = {"client_request_token": "bad"}
        with self.assertRaisesRegex(RuntimeError, "Unowned stack deletion"):
            self.aws.write(
                "cloudformation",
                "delete-stack",
                ["--stack-name", self.state["stack_id"], "--client-request-token", "bad"],
            )
        self.assertNotIn(("cloudformation", "delete-stack"), self.cli.counts)

    def test_unpersisted_mutation_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.aws("cloudformation", "delete-stack", "--stack-name", design.STACK)
        self.assertNotIn(("cloudformation", "delete-stack"), self.cli.counts)

    def test_secret_value_and_direct_updates_are_impossible(self):
        for pair in [
            ("secretsmanager", "get-secret-value"),
            ("lambda", "update-function-code"),
            ("iam", "put-role-policy"),
            ("cognito-idp", "admin-create-user"),
            ("ssm", "send-command"),
        ]:
            with self.subTest(pair=pair), self.assertRaises(RuntimeError):
                self.aws(*pair)

    def test_template_has_only_app_auth_access_no_public_services(self):
        text = json.dumps(self.operator.template)
        auth = pf.AuthenticationSecretOperator(context=pf.OperatorContext())
        self.assertNotIn(auth.db.ADMIN_ARN, text)
        self.assertNotIn(auth.MIGRATION["secret_arns"]["migration"], text)
        self.assertEqual(len(self.operator.template["Resources"]), 6)
        for prefix in design.NAMES:
            resources = self.operator.template["Resources"]
            props = resources[prefix + "Function"]["Properties"]
            self.assertEqual(props["VpcConfig"]["SecurityGroupIds"], [auth.db.APP_SG])
            self.assertIn(self.operator.contract["image_digest"], props["Code"]["ImageUri"])
            policy = resources[prefix + "Role"]["Properties"]["Policies"][0]["PolicyDocument"]
            self.assertEqual(
                set(policy["Statement"][0]["Resource"]),
                {auth.MIGRATION["secret_arns"]["app"], pf.deploy.CONFIG["auth_secret"]},
            )
            self.assertEqual(policy["Statement"][3]["Effect"], "Deny")
            self.assertEqual(resources[prefix + "Logs"]["Properties"]["RetentionInDays"], 1)

    def test_payload_and_lambda_configuration_size_budgets(self):
        self.assertLessEqual(len(self.operator.source.encode()), 32768)
        for name in design.NAMES.values():
            event = self.operator.event(name, "current-runtime", "b" * 32)
            self.assertLessEqual(len(event["body"].encode()), 49152)
        for prefix in design.NAMES:
            props = self.operator.template["Resources"][prefix + "Function"]["Properties"]
            design.database_templates.configuration_sizes(props, account=op.ACCOUNT)

    def test_result_nonce_tls_source_and_health_cannot_be_forged(self):
        good = valid_result(self.operator.contract, "b" * 32, "current-runtime")
        for path, value in [
            ("nonce", "wrong"),
            ("source_files_verified", 51),
            ("readiness_status", 503),
            ("runtime_identity", [0] * 4),
        ]:
            bad = copy.deepcopy(good)
            bad[path] = value
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                design.validate_result(
                    bad, nonce="b" * 32, action="current-runtime", contract=self.operator.contract
                )
        bad = copy.deepcopy(good)
        bad["proof"]["sslmode"] = "require"
        with self.assertRaises(RuntimeError):
            design.validate_result(
                bad, nonce="b" * 32, action="current-runtime", contract=self.operator.contract
            )

    def test_private_state_refuses_symlinks_and_preserves_permissions(self):
        path = self.path / "state.json"
        op.atomic_json(path, {"example": True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        link = self.path / "redirect.json"
        link.symlink_to(path)
        with self.assertRaises(RuntimeError):
            op.atomic_json(link, {})

    def test_ecr_policy_gap_stops_before_create_without_policy_change(self):
        self.cli.pull_policy["Statement"] = []
        with self.assertRaisesRegex(RuntimeError, "ECR policy does not cover"):
            self.operator.run()
        self.assertNotIn(("cloudformation", "create-stack"), self.cli.counts)
        self.assertNotIn(("ecr", "set-repository-policy"), self.cli.counts)

    def test_ecr_scoped_source_conditions_match_both_functions(self):
        statement = self.cli.pull_policy["Statement"][0]
        statement["Condition"] = {
            "StringEquals": {"aws:SourceAccount": op.ACCOUNT},
            "ArnLike": {
                ("aws:SourceArn"): (
                    f"arn:aws:lambda:{op.REGION}:{op.ACCOUNT}:function:fitfinity-test-runtime-*"
                )
            },
        }
        self.operator.verify_ecr_pull_policy()
        statement["Condition"]["StringEquals"]["aws:SourceAccount"] = "000000000000"
        with self.assertRaises(RuntimeError):
            self.operator.verify_ecr_pull_policy()

    def test_ecr_policy_for_another_repository_is_not_accepted(self):
        self.cli.pull_policy["Statement"][0]["Resource"] = (
            f"arn:aws:ecr:{op.REGION}:{op.ACCOUNT}:repository/other"
        )
        with self.assertRaises(RuntimeError):
            self.operator.verify_ecr_pull_policy()

    def test_run_after_failed_proof_cleanup_does_not_claim_runtime_pass(self):
        self.cli.fail_proof = True
        with self.assertRaises(RuntimeError):
            self.operator.run()
        self.operator.cleanup()
        self.operator.run()
        self.assertEqual(self.report["status"], "temporary_cleanup_complete_runtime_unverified")
        self.assertFalse(self.report["aws_runtime_verified"])

    def test_remote_source_compiles_and_request_failures_are_redacted(self):
        namespace = {"__name__": "offline_current_runtime"}
        exec(compile(self.operator.source, "current_runtime_proof", "exec"), namespace)

        class Request:
            async def body(self):
                return b'{"action":"forbidden","nonce":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'

        result = asyncio.run(namespace["run"](Request()))
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "request")
        self.assertNotIn("traceback", result)

    def test_remote_preflight_never_loads_managed_secret_helpers(self):
        namespace = {"__name__": "offline_current_runtime"}
        exec(compile(self.operator.source, "current_runtime_proof", "exec"), namespace)
        namespace["runtime_preflight"] = lambda: {"source_files_verified": 54}
        load = Mock(side_effect=AssertionError("must not initialize managed proof"))
        namespace["load_auth_proof"] = load

        class Request:
            async def body(self):
                return b'{"action":"preflight","nonce":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'

        result = asyncio.run(namespace["run"](Request()))
        self.assertTrue(result["ok"])
        load.assert_not_called()

    def test_remote_runtime_handler_assembles_valid_proof_without_initializer(self):
        namespace = {"__name__": "offline_current_runtime"}
        exec(compile(self.operator.source, "current_runtime_proof", "exec"), namespace)
        nonce = "a" * 32
        expected = valid_result(self.operator.contract, nonce, "current-runtime")
        namespace["runtime_preflight"] = lambda: {
            k: expected[k]
            for k in [
                "runtime_identity",
                "source_files_verified",
                "dependencies_verified",
                "image_digest",
                "revision",
            ]
        }
        helper = Mock()
        helper.application_proof.return_value = expected["proof"]
        namespace["load_auth_proof"] = lambda: helper
        namespace["application_startup"] = AsyncMock(
            return_value={
                k: expected[k]
                for k in [
                    "application_startup_verified",
                    "application_shutdown_verified",
                    "liveness_status",
                    "readiness_status",
                    "untrusted_host_status",
                ]
            }
        )
        config = ModuleType("app.config")
        config.load_settings = lambda: SimpleNamespace(
            cognito_issuer=(
                "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_La0Y3MXCj"
            )
        )
        jwt = ModuleType("app.auth.jwt")
        jwt.download_keys = lambda url: {"keys": [{"kid": "offline-key"}]}
        jwt.AccessVerifier = Mock(return_value=SimpleNamespace(_key=lambda kid: None))

        class Request:
            async def body(self):
                return json.dumps({"action": "current-runtime", "nonce": nonce}).encode()

        with patch.dict(
            sys.modules,
            {
                "app": ModuleType("app"),
                "app.auth": ModuleType("app.auth"),
                "app.auth.jwt": jwt,
                "app.config": config,
            },
        ):
            result = asyncio.run(namespace["run"](Request()))
        design.validate_result(
            result, nonce=nonce, action="current-runtime", contract=self.operator.contract
        )
        helper.application_proof.assert_called_once_with(pf.deploy.CONFIG["auth_secret"])
        helper.initialize.assert_not_called()

    def probe_namespace(self):
        namespace = {"__name__": "offline_runtime_transport"}
        exec(compile(self.operator.source, "current_runtime_proof", "exec"), namespace)
        return namespace

    def run_startup_fixture(self, override=None):
        namespace = self.probe_namespace()
        events = []
        fixture_settings = SimpleNamespace(
            allowed_hosts=["runtime.invalid"],
            auth_origins=["https://runtime.invalid"],
            auth_enabled=True,
            auth_cookie_secure=True,
            staff_invitations_enabled=False,
        )

        class App:
            @asynccontextmanager
            async def lifespan_context(self, app):
                events.append("startup")
                try:
                    yield
                finally:
                    events.append("shutdown")

            async def __call__(self, scope, receive, send):
                self_test.assertIn("startup", events)
                self_test.assertNotIn("shutdown", events)
                self_test.assertEqual(
                    await receive(), {"type": "http.request", "body": b"", "more_body": False}
                )
                host = dict(scope["headers"])[b"host"].decode()
                events.append((scope["path"], host))
                status = 400 if host != "runtime.invalid" else 200
                body = (
                    b"Invalid host header"
                    if status == 400
                    else json.dumps(
                        {"status": "alive" if scope["path"].endswith("live") else "ready"}
                    ).encode()
                )
                if override:
                    status, body = override(scope, status, body)
                await send({"type": "http.response.start", "status": status})
                await send({"type": "http.response.body", "body": body[:4], "more_body": True})
                await send({"type": "http.response.body", "body": body[4:]})
                self_test.assertEqual(await receive(), {"type": "http.disconnect"})

        self_test = self
        app = App()
        app.router = app
        config, main = ModuleType("app.config"), ModuleType("app.main")
        config.load_settings = lambda: fixture_settings
        main.create_app = lambda settings: app
        modules = {"app": ModuleType("app"), "app.config": config, "app.main": main, "httpx": None}
        with patch.dict(sys.modules, modules):
            try:
                result = asyncio.run(namespace["application_startup"]())
            finally:
                self.assertEqual(events[0], "startup")
                self.assertEqual(events[-1], "shutdown")
        return result, events

    def test_actual_startup_function_checks_all_health_and_lifespan_without_httpx(self):
        result, events = self.run_startup_fixture()
        self.assertEqual(
            events[1:-1],
            [
                ("/health/live", "runtime.invalid"),
                ("/health/ready", "runtime.invalid"),
                ("/health/live", "untrusted.invalid"),
            ],
        )
        self.assertTrue(result["application_startup_verified"])
        self.assertTrue(result["application_shutdown_verified"])

    def test_startup_keeps_health_assertions_and_closes_on_failure(self):
        for override, message in [
            (
                lambda s, c, b: (503, b) if s["path"].endswith("ready") else (c, b),
                "database readiness",
            ),
            (lambda s, c, b: (200, b) if c == 400 else (c, b), "untrusted host"),
            (lambda s, c, b: (c, b'{"status":"wrong"}') if c == 200 else (c, b), "liveness"),
        ]:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    self.run_startup_fixture(override)

    def test_asgi_rejects_incomplete_oversized_and_invalid_response_frames(self):
        namespace = self.probe_namespace()
        scenarios = [
            [],
            [{"type": "http.response.body", "body": b""}],
            [
                {"type": "http.response.start", "status": 200},
                {"type": "http.response.body", "body": b"x" * 4097},
            ],
            [
                {"type": "http.response.start", "status": 200},
                {"type": "http.response.body", "body": b"", "more_body": True},
            ],
        ]
        for frames in scenarios:
            with self.subTest(frames=len(frames)):

                async def app(scope, receive, send, frames=frames):
                    for frame in frames:
                        await send(frame)

                with self.assertRaises(RuntimeError):
                    asyncio.run(namespace["asgi_get"](app, "/health/live"))


class CloudBindingChecks(unittest.TestCase):
    def test_offline_plan_never_calls_subprocess(self):
        with patch.object(op.subprocess, "run", side_effect=AssertionError("network")):
            self.assertEqual(
                op.main(
                    ["--mode", "plan", "--operation-id", "a" * 32, "--directory", "/tmp/unused"]
                ),
                0,
            )

    def test_expired_or_changed_approval_refused(self):
        approval = pf.binding.local_approval()
        for changed, stamp in [
            (approval, datetime(2026, 10, 12, tzinfo=UTC)),
            ({**approval, "reason": "changed"}, datetime(2026, 10, 7, 13, tzinfo=UTC)),
        ]:
            with self.assertRaises(RuntimeError):
                pf.binding.check_approval(changed, approval["provenance"], stamp)

    def test_wrong_provenance_refused(self):
        approval = pf.binding.local_approval()
        with self.assertRaises(RuntimeError):
            pf.binding.check_approval(approval, {}, datetime(2026, 10, 7, 13, tzinfo=UTC))

    def test_identity_rejects_wrong_account_and_role(self):
        for account, arn in [("0", "bad"), ("418638389566", "arn:aws:iam::418638389566:root")]:
            runner = Mock(
                return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps({"Account": account, "Arn": arn}), stderr=""
                )
            )
            with patch.object(pf.binding, "actions_environment"), self.assertRaises(RuntimeError):
                pf.EvidenceAWS(pf.receipt_initial(), runner).environment()

    def test_capacity_below_102_stops_collection(self):
        report = pf.receipt_initial()
        report.update(
            approval=pf.binding.local_approval(),
            candidate_provenance=pf.binding.local_approval()["provenance"],
            candidate={},
        )
        aws = Mock(return_value={"AccountLimit": {"UnreservedConcurrentExecutions": 101}})
        with (
            patch.object(pf, "now", return_value=datetime(2026, 10, 7, 13, tzinfo=UTC)),
            self.assertRaisesRegex(RuntimeError, "capacity"),
        ):
            pf.collect(report, aws)
        self.assertEqual(aws.call_count, 1)

    def test_cli_has_no_profile_and_keeps_tls_and_bounded_timeouts(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="{}", stderr=""))
        pf.EvidenceAWS(pf.receipt_initial(), runner)("sts", "get-caller-identity")
        command = runner.call_args.args[0]
        self.assertNotIn("--profile", command)
        self.assertNotIn("--no-verify-ssl", command)
        self.assertEqual(command[command.index("--cli-read-timeout") + 1], "30")
        self.assertEqual(runner.call_args.kwargs["timeout"], 90)

    def test_manual_main_and_temporary_credentials_required(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            pf.binding.actions_environment()

    def test_recovery_rejects_untrusted_workflow_before_artifact_read(self):
        with (
            patch.object(
                pf.binding.ExistingImage, "github", return_value={"path": "other"}
            ) as github,
            self.assertRaises(RuntimeError),
        ):
            pf.binding.restore_state(123, "a" * 32, "b" * 40)
        self.assertEqual(github.call_count, 1)


class RuntimePolicyChecks(unittest.TestCase):
    """Focused documented permission contracts, not a live IAM evaluator."""

    FUNCTIONS = [
        f"arn:aws:lambda:ap-southeast-1:418638389566:function:fitfinity-test-runtime-{x}"
        for x in "ab"
    ]
    LOGS = [
        f"arn:aws:logs:ap-southeast-1:418638389566:log-group:/aws/lambda/fitfinity-test-runtime-{x}"
        for x in "ab"
    ]
    REPO = "arn:aws:ecr:ap-southeast-1:418638389566:repository/fitfinity-test-api"
    ROLES = "arn:aws:iam::418638389566:role/fitfinity-test-current-runtime-*"
    BOUNDARY = "arn:aws:iam::418638389566:policy/fitfinity-test-private-runtime-boundary"
    REGION = {"StringEquals": {"aws:RequestedRegion": "ap-southeast-1"}}

    def setUp(self):
        self.template = json.loads((ROOT / "test-github-runtime-role.json").read_text())
        self.role = self.template["Resources"]["RuntimeRole"]["Properties"]
        self.statements = self.role["Policies"][0]["PolicyDocument"]["Statement"]

    def statement(self, action):
        rows = [s for s in self.statements if action in s["Action"]]
        self.assertEqual(len(rows), 1, action)
        self.assertEqual(rows[0]["Effect"], "Allow")
        return rows[0]

    def check_mapping_list(self):
        self.assertEqual(
            self.statement("lambda:ListEventSourceMappings"),
            {
                "Effect": "Allow",
                "Action": ["lambda:ListEventSourceMappings"],
                "Resource": "*",
                "Condition": self.REGION,
            },
        )

    def check_layer_read(self):
        self.assertEqual(self.statement("ecr:GetDownloadUrlForLayer")["Resource"], self.REPO)

    def test_event_mapping_list_is_only_regional_list_action(self):
        self.check_mapping_list()

    def test_reject_original_function_scoped_mapping_list(self):
        self.statements = [
            s for s in self.statements if "lambda:ListEventSourceMappings" not in s["Action"]
        ]
        self.statement("lambda:GetFunction")["Action"].append("lambda:ListEventSourceMappings")
        with self.assertRaises(AssertionError):
            self.check_mapping_list()

    def test_image_layer_retrieval_is_exact_repository_read(self):
        self.check_layer_read()
        actions = {a for s in self.statements for a in s["Action"] if a.startswith("ecr:")}
        self.assertEqual(
            actions,
            {
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer",
                "ecr:DescribeImageScanFindings",
                "ecr:GetRepositoryPolicy",
            },
        )
        for action in actions:
            self.assertEqual(self.statement(action)["Resource"], self.REPO)

    def test_reject_original_missing_image_layer_permission(self):
        for statement in self.statements:
            statement["Action"] = [
                a for a in statement["Action"] if a != "ecr:GetDownloadUrlForLayer"
            ]
        with self.assertRaises(AssertionError):
            self.check_layer_read()

    def test_reject_broad_image_layer_permission(self):
        self.statement("ecr:GetDownloadUrlForLayer")["Resource"] = "*"
        with self.assertRaises(AssertionError):
            self.check_layer_read()

    def test_tagged_function_reads_and_lifecycle_are_exact(self):
        for action in (
            "CreateFunction",
            "GetFunction",
            "GetFunctionConfiguration",
            "ListTags",
            "GetPolicy",
            "GetFunctionUrlConfig",
            "InvokeFunction",
            "TagResource",
            "UntagResource",
            "DeleteFunction",
        ):
            self.assertEqual(self.statement("lambda:" + action)["Resource"], self.FUNCTIONS)

    def test_vpc_creator_dependencies_have_supported_scopes(self):
        statement = self.statement("ec2:DescribeVpcs")
        self.assertEqual(
            statement,
            {
                "Effect": "Allow",
                "Action": ["ec2:DescribeVpcs"],
                "Resource": "*",
                "Condition": self.REGION,
            },
        )
        statement = self.statement("ec2:GetSecurityGroupsForVpc")
        self.assertEqual(
            statement["Resource"],
            "arn:aws:ec2:ap-southeast-1:418638389566:vpc/vpc-0b55320bb1a054441",
        )
        self.assertEqual(statement["Condition"], self.REGION)
        for action in ("ec2:DescribeSecurityGroups", "ec2:DescribeSubnets"):
            self.assertEqual(self.statement(action)["Resource"], "*")

    def test_logs_tagging_uses_action_specific_arns(self):
        for action in ("logs:TagResource", "logs:UntagResource"):
            self.assertEqual(self.statement(action)["Resource"], self.LOGS)
        for action in (
            "CreateLogGroup",
            "DeleteLogGroup",
            "PutRetentionPolicy",
            "DeleteRetentionPolicy",
            "FilterLogEvents",
            "TagLogGroup",
            "ListTagsLogGroup",
        ):
            self.assertEqual(
                self.statement("logs:" + action)["Resource"], [arn + ":*" for arn in self.LOGS]
            )

    def test_iam_creation_passing_and_cleanup_stay_bounded(self):
        self.assertEqual(
            self.statement("iam:CreateRole")["Condition"],
            {"StringEquals": {"iam:PermissionsBoundary": self.BOUNDARY}},
        )
        self.assertEqual(
            self.statement("iam:PassRole")["Condition"],
            {"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}},
        )
        expected = {
            "CreateRole",
            "DeleteRole",
            "GetRole",
            "ListRolePolicies",
            "GetRolePolicy",
            "ListAttachedRolePolicies",
            "PutRolePolicy",
            "DeleteRolePolicy",
            "TagRole",
            "UntagRole",
            "PassRole",
        }
        self.assertEqual(
            {
                a.removeprefix("iam:")
                for s in self.statements
                for a in s["Action"]
                if a.startswith("iam:")
            },
            expected,
        )
        for action in expected:
            self.assertEqual(self.statement("iam:" + action)["Resource"], self.ROLES)
        for action in ("cloudformation:CreateStack", "cloudformation:DeleteStack"):
            self.assertEqual(
                self.statement(action)["Resource"],
                "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-current-runtime/*",
            )

    def test_operator_has_metadata_only_secret_access_and_no_wildcard_writes(self):
        actions = {a for s in self.statements for a in s["Action"]}
        self.assertEqual(
            {a for a in actions if a.startswith("secretsmanager:")},
            {"secretsmanager:DescribeSecret", "secretsmanager:GetResourcePolicy"},
        )
        wildcard = {a for s in self.statements if s["Resource"] == "*" for a in s["Action"]}
        self.assertEqual(
            wildcard,
            {
                "sts:GetCallerIdentity",
                "lambda:GetAccountSettings",
                "lambda:ListEventSourceMappings",
                "freetier:GetAccountPlanState",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeRouteTables",
                "ec2:DescribeInstances",
                "ec2:DescribeVolumes",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeInstanceCreditSpecifications",
                "rds:DescribeDBInstances",
                "rds:DescribeDBParameters",
                "logs:DescribeLogGroups",
            },
        )

    def test_boundary_matches_generated_roles_and_preserves_secret_and_eni_guards(self):
        boundary = self.template["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"][
            "Statement"
        ]
        source, _ = design.source_bundle()
        resources = design.template(source)["Resources"]
        for resource in resources.values():
            if resource["Type"] != "AWS::IAM::Role":
                continue
            self.assertEqual(resource["Properties"]["PermissionsBoundary"], self.BOUNDARY)
            for statement in resource["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]:
                self.assertIn(statement, boundary)
        secrets = [s for s in boundary if "secretsmanager:GetSecretValue" in s["Action"]]
        self.assertEqual(len(secrets), 1)
        self.assertEqual(
            secrets[0]["Resource"],
            [
                "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/database/app-cqKagk",
                "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/auth-Y2c7Xy",
            ],
        )
        self.assertEqual(
            secrets[0]["Condition"], {"StringEquals": {"secretsmanager:VersionStage": "AWSCURRENT"}}
        )
        denies = [s for s in boundary if s["Effect"] == "Deny"]
        self.assertEqual(
            [s["Condition"]["ArnEquals"]["lambda:SourceFunctionArn"] for s in denies],
            self.FUNCTIONS,
        )
        for statement in denies:
            self.assertIn("ec2:DeleteNetworkInterface", statement["Action"])
            self.assertIn("ec2:DetachNetworkInterface", statement["Action"])

    def test_oidc_trust_is_exact_repository_environment_and_audience(self):
        self.assertEqual(
            self.role["AssumeRolePolicyDocument"]["Statement"],
            [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": (
                            "arn:aws:iam::418638389566:oidc-provider/"
                            "token.actions.githubusercontent.com"
                        )
                    },
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                            "token.actions.githubusercontent.com:sub": (
                                "repo:LimYouSheng/FitfinityReact:environment:aws-test"
                            ),
                        }
                    },
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
