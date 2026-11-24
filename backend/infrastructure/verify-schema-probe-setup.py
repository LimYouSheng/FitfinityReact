"""Verify IAM setup boundaries without provisioning roles or changing trust."""

import copy
import json
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from schema_probe_iam import BOUNDARY, RUNTIME_ROLE, runtime_policy
from schema_probe_network_check import collect, read
from schema_probe_setup import ACCOUNT, OPERATOR_ROLE, REGION, prepare, write_bundle
from schema_probe_setup_operator import STACK, install, template_hash, validate_change_set

SECRET = (
    f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:fitfinity/test/database/migration-abcdef"
)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.review = prepare(SECRET, vpc_id="vpc-aaaaaaaa")
        self.resources = self.review["template"]["Resources"]
        self.operator = self.resources["OperatorRole"]["Properties"]
        self.statements = self.operator["Policies"][0]["PolicyDocument"]["Statement"]

    def statement(self, action):
        return next(
            row
            for row in self.statements
            if action in (row["Action"] if isinstance(row["Action"], list) else [row["Action"]])
        )

    def test_only_three_iam_resources_and_no_activation(self):
        self.assertEqual(self.review["decision"], "HOLD")
        self.assertEqual(
            set(self.resources), {"RuntimeBoundary", "OperatorBoundary", "OperatorRole"}
        )
        self.assertEqual(self.operator["RoleName"], OPERATOR_ROLE)
        self.assertEqual(self.operator["PermissionsBoundary"], {"Ref": "OperatorBoundary"})
        self.assertEqual(
            self.resources["OperatorBoundary"]["Properties"]["PolicyDocument"],
            self.operator["Policies"][0]["PolicyDocument"],
        )

    def test_trust_is_exact_repository_environment_and_audience(self):
        statement = self.operator["AssumeRolePolicyDocument"]["Statement"][0]
        self.assertEqual(statement["Action"], "sts:AssumeRoleWithWebIdentity")
        self.assertEqual(
            statement["Principal"],
            {
                "Federated": (
                    f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
                )
            },
        )
        self.assertEqual(
            statement["Condition"]["StringEquals"],
            {
                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                "token.actions.githubusercontent.com:sub": (
                    "repo:LimYouSheng/FitfinityReact:environment:aws-test"
                ),
            },
        )

    def test_runtime_boundary_matches_canonical_runtime_policy(self):
        self.assertEqual(
            self.resources["RuntimeBoundary"]["Properties"]["PolicyDocument"],
            runtime_policy(SECRET),
        )
        rows = runtime_policy(SECRET)["Statement"]
        self.assertEqual(rows[0]["Resource"], SECRET)
        self.assertEqual(rows[-1]["Effect"], "Deny")
        self.assertIn("lambda:SourceFunctionArn", rows[-1]["Condition"]["ArnEquals"])

    def test_create_requires_boundary_and_passrole_only_targets_lambda(self):
        create = self.statement("iam:CreateRole")
        self.assertEqual(create["Resource"], f"arn:aws:iam::{ACCOUNT}:role/{RUNTIME_ROLE}")
        self.assertEqual(
            create["Condition"], {"StringEquals": {"iam:PermissionsBoundary": BOUNDARY}}
        )
        self.assertEqual(
            self.statement("iam:PassRole")["Condition"],
            {"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}},
        )

    def test_both_private_worker_creators_have_only_region_and_vpc_scoped_network_reads(self):
        from deployment_profile import DEVELOPER

        client = {
            **DEVELOPER,
            "account": "123456789012",
            "region": "eu-west-1",
            "resource_prefix": "customer-prod",
            "secret_prefix": "customer/prod",
        }
        for profile, vpc in ((DEVELOPER, "vpc-0123456789abcdef0"), (client, "vpc-12345678")):
            account, region = profile["account"], profile["region"]
            secret = (
                f"arn:aws:secretsmanager:{region}:{account}:secret:"
                + profile["secret_prefix"]
                + "/database/migration-abc123"
            )
            resources_by_action = {
                "ec2:DescribeVpcs": "*",
                "ec2:DescribeSubnets": "*",
                "ec2:DescribeSecurityGroups": "*",
                "ec2:GetSecurityGroupsForVpc": f"arn:aws:ec2:{region}:{account}:vpc/{vpc}",
            }
            for purpose in ("probe", "upgrade"):
                with self.subTest(purpose=purpose, vpc=vpc):
                    review = prepare(secret, profile=profile, vpc_id=vpc, purpose=purpose)
                    resources = review["template"]["Resources"]
                    for policy in (
                        resources["OperatorRole"]["Properties"]["Policies"][0]["PolicyDocument"],
                        resources["OperatorBoundary"]["Properties"]["PolicyDocument"],
                    ):
                        grants = [
                            (action, row["Resource"], row.get("Condition"))
                            for row in policy["Statement"]
                            for action in (
                                row["Action"]
                                if isinstance(row["Action"], list)
                                else [row["Action"]]
                            )
                            if action.startswith("ec2:")
                        ]
                        self.assertCountEqual(
                            grants,
                            [
                                (
                                    action,
                                    resource,
                                    {"StringEquals": {"aws:RequestedRegion": region}},
                                )
                                for action, resource in resources_by_action.items()
                            ],
                        )
                    runtime = resources["RuntimeBoundary"]["Properties"]["PolicyDocument"]
                    self.assertNotIn("ec2:GetSecurityGroupsForVpc", json.dumps(runtime))
        for invalid in (None, "*", "vpc-*", "vpc-123456789", "subnet-12345678"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(RuntimeError, "VPC"):
                prepare(SECRET, vpc_id=invalid)

    def test_no_secret_reads_policy_escalation_or_existing_application_changes(self):
        actions = {
            action
            for row in self.statements
            for action in (row["Action"] if isinstance(row["Action"], list) else [row["Action"]])
        }
        self.assertTrue(
            actions.isdisjoint(
                {
                    "secretsmanager:GetSecretValue",
                    "iam:AttachRolePolicy",
                    "iam:DeleteRolePermissionsBoundary",
                    "iam:PutRolePermissionsBoundary",
                    "iam:CreatePolicyVersion",
                    "iam:UpdateAssumeRolePolicy",
                    "cloudformation:UpdateStack",
                    "lambda:UpdateFunctionCode",
                }
            )
        )
        self.assertFalse(any("*" in action for action in actions))
        self.assertTrue(
            self.statement("cloudformation:CreateStack")["Resource"].endswith(
                "stack/fitfinity-test-schema-observe/*"
            )
        )
        self.assertTrue(
            self.statement("lambda:InvokeFunction")["Resource"].endswith(
                "function:fitfinity-test-schema-observe"
            )
        )

    def test_foreign_wrong_type_or_wildcard_secret_is_refused(self):
        for secret in (
            SECRET.replace(ACCOUNT, "000000000000"),
            SECRET.replace("migration-", "app-"),
            SECRET.replace(REGION, "us-east-1"),
            "*",
            None,
        ):
            with self.subTest(secret=secret), self.assertRaises(RuntimeError):
                prepare(secret, vpc_id="vpc-aaaaaaaa")

    def test_network_collection_stops_before_reads_in_foreign_account(self):
        calls = []

        def call(service, operation, *args):
            calls.append(operation)
            return {"Account": "000000000000"}

        with self.assertRaises(RuntimeError):
            collect(call)
        self.assertEqual(calls, ["get-caller-identity"])

    def test_network_collection_excludes_environment_values_and_unrelated_fields(self):
        def call(service, operation, *args):
            if operation == "get-caller-identity":
                return {"Account": ACCOUNT}
            if operation == "get-function-configuration":
                return {
                    "State": "Inactive",
                    "StateReasonCode": "Idle",
                    "Environment": {"Variables": {"SECRET": "sensitive-marker"}},
                }
            if operation == "get-open-id-connect-provider":
                return {
                    "Url": "token.actions.githubusercontent.com",
                    "ClientIDList": ["sts.amazonaws.com"],
                    "Tags": "sensitive-marker",
                }
            return {}

        result = collect(call)
        self.assertNotIn("sensitive-marker", json.dumps(result))
        self.assertEqual(result["runtime_state"]["StateReasonCode"], "Idle")
        self.assertEqual(result["github_oidc"]["ClientIDList"], ["sts.amazonaws.com"])

    def test_network_tool_refuses_mutations_and_secret_retrieval(self):
        for service, operation in (
            ("ec2", "start-instances"),
            ("secretsmanager", "get-secret-value"),
        ):
            with self.assertRaises(RuntimeError):
                read(service, operation)

    def changes(self):
        return {
            "Status": "CREATE_COMPLETE",
            "ExecutionStatus": "AVAILABLE",
            "Changes": [
                {
                    "ResourceChange": {
                        "Action": "Add",
                        "LogicalResourceId": name,
                        "ResourceType": row["Type"],
                    }
                }
                for name, row in self.resources.items()
            ],
        }

    def test_setup_change_set_accepts_only_exact_three_additions(self):
        validate_change_set(self.changes())
        for key, value in (
            ("Action", "Modify"),
            ("Action", "Remove"),
            ("Replacement", "True"),
            ("ResourceType", "AWS::Lambda::Function"),
            ("LogicalResourceId", "Unexpected"),
        ):
            changed = self.changes()
            changed["Changes"][0]["ResourceChange"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                validate_change_set(changed)
        changed = self.changes()
        changed["Changes"].append(copy.deepcopy(changed["Changes"][0]))
        with self.assertRaises(RuntimeError):
            validate_change_set(changed)

    def test_setup_refuses_existing_operator_without_mutation(self):
        calls = []

        def call(service, operation, *args, **kwargs):
            calls.append(operation)
            if operation == "get-caller-identity":
                return {"Account": ACCOUNT}
            if operation == "get-open-id-connect-provider":
                return {
                    "Url": "token.actions.githubusercontent.com",
                    "ClientIDList": ["sts.amazonaws.com"],
                }
            if operation == "get-role":
                return {"Role": {}}
            raise AssertionError(operation)

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                install(
                    self.review["template"], Path(folder) / "review", call, pause=lambda _: None
                )
        self.assertNotIn("create-change-set", calls)

    def test_setup_rejects_malformed_or_substring_oidc_audiences_before_mutation(self):
        for audiences in (
            None,
            "sts.amazonaws.com",
            "evil.sts.amazonaws.com",
            [],
            ["sts.amazonaws.com.evil"],
            ["prefix-sts.amazonaws.com"],
            ["sts.amazonaws.com", None],
            {"sts.amazonaws.com": True},
        ):
            calls = []

            def call(service, operation, *args, calls=calls, audiences=audiences, **kwargs):
                calls.append(operation)
                if operation == "get-caller-identity":
                    return {"Account": ACCOUNT}
                if operation == "get-open-id-connect-provider":
                    return {"Url": "token.actions.githubusercontent.com", "ClientIDList": audiences}
                raise AssertionError("Unexpected call after malformed OIDC provider")

            with self.subTest(audiences=audiences), tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(RuntimeError, "OIDC provider differs"):
                    install(self.review["template"], Path(folder) / "review", call)
                self.assertEqual(calls, ["get-caller-identity", "get-open-id-connect-provider"])
                self.assertEqual(list(Path(folder).iterdir()), [])

    def installer_call(self, calls, fail_create=False):
        state = {"applied": False}

        def call(service, operation, *args, **kwargs):
            calls.append(operation)
            if operation == "get-caller-identity":
                return {"Account": ACCOUNT}
            if operation == "get-open-id-connect-provider":
                return {
                    "Url": "token.actions.githubusercontent.com",
                    "ClientIDList": ["sts.amazonaws.com"],
                }
            if kwargs.get("missing"):
                return None
            if operation == "create-change-set":
                if fail_create:
                    raise RuntimeError("lost response")
                token = args[args.index("--client-token") + 1]
                return {
                    "Id": (
                        f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:"
                        f"changeSet/probe-access-{token}/synthetic"
                    ),
                    "StackId": f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/synthetic",
                }
            if operation == "describe-change-set":
                return self.changes()
            if operation == "get-template":
                return {"TemplateBody": self.review["template"]}
            if operation == "execute-change-set":
                state["applied"] = True
                return {}
            if operation == "describe-stacks":
                return {"Stacks": [{"StackStatus": "CREATE_COMPLETE"}]}
            if operation == "get-role":
                return {
                    "Role": {
                        "Arn": f"arn:aws:iam::{ACCOUNT}:role/{OPERATOR_ROLE}",
                        "PermissionsBoundary": {
                            "PermissionsBoundaryArn": (
                                f"arn:aws:iam::{ACCOUNT}:policy/{OPERATOR_ROLE}-boundary"
                            )
                        },
                        "AssumeRolePolicyDocument": self.operator["AssumeRolePolicyDocument"],
                    }
                }
            if operation == "get-role-policy":
                return {"PolicyDocument": self.operator["Policies"][0]["PolicyDocument"]}
            if operation == "list-role-policies":
                return {"PolicyNames": ["ProbeLifecycle"]}
            if operation == "list-attached-role-policies":
                return {"AttachedPolicies": []}
            if operation == "get-policy":
                return {"Policy": {"DefaultVersionId": "v1"}}
            if operation == "get-policy-version":
                arn = args[args.index("--policy-arn") + 1]
                key = "RuntimeBoundary" if "schema-observe-runtime" in arn else "OperatorBoundary"
                return {
                    "PolicyVersion": {
                        "Document": self.resources[key]["Properties"]["PolicyDocument"]
                    }
                }
            raise AssertionError(operation)

        return call

    def test_setup_executes_once_and_verifies_installed_iam(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            result = install(
                self.review["template"],
                Path(folder) / "review",
                self.installer_call(calls),
                pause=lambda _: None,
            )
            self.assertEqual(result["state"], "iam_setup_verified")
            self.assertFalse(result["application_deployed"])
        self.assertEqual(calls.count("execute-change-set"), 1)
        self.assertNotIn("delete-stack", calls)

    def test_setup_preserves_uncertain_creation_without_retry(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review"
            with self.assertRaisesRegex(RuntimeError, "lost response"):
                install(
                    self.review["template"],
                    path,
                    self.installer_call(calls, True),
                    pause=lambda _: None,
                )
            receipt = json.loads((path / "receipt.json").read_text())
            self.assertEqual(receipt["state"], "failed_or_uncertain")
        self.assertEqual(calls.count("create-change-set"), 1)
        self.assertNotIn("execute-change-set", calls)

    def test_installed_iam_update_rechecks_original_and_effective_permissions(self):
        original = json.loads(
            (Path(__file__).parent / "fixtures/installed-probe-iam-template.json").read_text()
        )
        original_resources = original["Resources"]
        secret = original_resources["RuntimeBoundary"]["Properties"]["PolicyDocument"]["Statement"][
            0
        ]["Resource"]
        review = prepare(secret, vpc_id="vpc-0b55320bb1a054441")
        candidate = review["template"]
        stack_id = f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/abcd"

        def exercise(defect):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundle = root / "bundle"
                write_bundle(review, bundle, installed_template=original, stack_id=stack_id)
                operator = runpy.run_path(str(bundle / "fitfinity-update-probe-iam.py"))
                calls = []
                state = {"executed": False, "change": None, "polls": 0}
                fallback = self.installer_call(calls)

                def provider(service, operation, *args):
                    # Existing account/OIDC/role-list observations match the setup fixture.
                    if operation in {
                        "get-caller-identity",
                        "get-open-id-connect-provider",
                        "get-role",
                        "list-role-policies",
                        "list-attached-role-policies",
                        "get-policy",
                    }:
                        return fallback(service, operation, *args)
                    calls.append(operation)
                    active = candidate if state["executed"] else original
                    if operation == "describe-stacks":
                        self.assertEqual(args[-1], stack_id)
                        return {
                            "Stacks": [
                                {
                                    "StackId": stack_id,
                                    "StackName": STACK,
                                    "StackStatus": "UPDATE_COMPLETE",
                                }
                            ]
                        }
                    if operation == "list-stack-resources":
                        physical = []
                        for key, resource in original_resources.items():
                            name = (
                                OPERATOR_ROLE
                                if key == "OperatorRole"
                                else f"arn:aws:iam::{ACCOUNT}:policy/"
                                + resource["Properties"]["ManagedPolicyName"]
                            )
                            physical.append(
                                {
                                    "LogicalResourceId": key,
                                    "ResourceType": resource["Type"],
                                    "PhysicalResourceId": name,
                                }
                            )
                        if defect == "foreign_owner":
                            physical[0]["PhysicalResourceId"] += "-other"
                        return {"StackResourceSummaries": physical}
                    if operation == "get-template":
                        proposal = "--change-set-name" in args
                        value = candidate if proposal else original
                        if defect == ("proposed" if proposal else "original"):
                            value = {**value, "Description": "unexpected"}
                        return {"TemplateBody": json.dumps(value)}
                    if operation == "get-role-policy":
                        role = active["Resources"]["OperatorRole"]["Properties"]
                        return {"PolicyDocument": role["Policies"][0]["PolicyDocument"]}
                    if operation == "get-policy-version":
                        arn = args[args.index("--policy-arn") + 1]
                        name = (
                            "RuntimeBoundary"
                            if "schema-observe-runtime" in arn
                            else "OperatorBoundary"
                        )
                        value = active["Resources"][name]["Properties"]["PolicyDocument"]
                        if name == "OperatorBoundary" and (
                            defect == "readback"
                            and state["executed"]
                            or defect == "live_boundary"
                            and not state["executed"]
                        ):
                            value = {"Statement": []}
                        return {"PolicyVersion": {"Document": value}}
                    if operation == "create-change-set":
                        self.assertEqual(args[args.index("--change-set-type") + 1], "UPDATE")
                        self.assertEqual(args[args.index("--stack-name") + 1], stack_id)
                        name = args[args.index("--change-set-name") + 1]
                        state["change"] = (
                            f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:changeSet/{name}/id"
                        )
                        return {"StackId": stack_id, "Id": state["change"]}
                    if operation == "describe-change-set":
                        execution = "AVAILABLE"
                        if state["executed"]:
                            state["polls"] += 1
                            execution = (
                                "EXECUTE_COMPLETE" if state["polls"] > 1 else "EXECUTE_IN_PROGRESS"
                            )
                        return {
                            "Status": "CREATE_COMPLETE",
                            "ExecutionStatus": execution,
                            "ChangeSetId": state["change"],
                            "StackId": stack_id
                            + ("1" if defect == "wrong_change_set_stack" else ""),
                            "Changes": [
                                {
                                    "ResourceChange": {
                                        "Action": "Add" if defect == "add" else "Modify",
                                        "ResourceType": original_resources[key]["Type"],
                                        "LogicalResourceId": key,
                                        "Replacement": "Conditional"
                                        if defect == "replace"
                                        else "False",
                                    }
                                }
                                for key in ("OperatorRole", "OperatorBoundary")
                            ],
                        }
                    if operation == "execute-change-set":
                        self.assertEqual(args[args.index("--change-set-name") + 1], state["change"])
                        state["executed"] = True
                        if defect == "lost_execute":
                            raise RuntimeError("lost reply")
                        return {}
                    self.fail(operation)

                def run():
                    return operator["install"](
                        operator["TEMPLATE"],
                        root / "journal",
                        provider,
                        pause=lambda _: None,
                        update=operator["UPDATE"],
                    )

                if defect is None:
                    result = run()
                    self.assertEqual(result["state"], "iam_setup_verified")
                    self.assertEqual(result["original_sha256"], template_hash(original))
                    self.assertEqual(result["stack_id"], stack_id)
                    self.assertEqual(state["polls"], 2)
                else:
                    with self.assertRaises(RuntimeError):
                        run()
                if defect in ("original", "foreign_owner", "live_boundary"):
                    self.assertNotIn("create-change-set", calls)
                self.assertEqual(
                    calls.count("execute-change-set"),
                    int(defect in (None, "lost_execute", "readback")),
                )
                if defect in ("lost_execute", "readback"):
                    receipt = json.loads((root / "journal/receipt.json").read_text())
                    self.assertEqual(receipt["state"], "failed_or_uncertain")
                    self.assertEqual(receipt["change_set_id"], state["change"])

        for defect in (
            None,
            "original",
            "foreign_owner",
            "live_boundary",
            "add",
            "replace",
            "wrong_change_set_stack",
            "proposed",
            "lost_execute",
            "readback",
        ):
            exercise(defect)

    def test_installed_update_rejects_other_grants_or_iam_owners_before_packaging(self):
        old = json.loads(
            (Path(__file__).parent / "fixtures/installed-probe-iam-template.json").read_text()
        )
        secret = old["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"]["Statement"][
            0
        ]["Resource"]
        review = prepare(secret, vpc_id="vpc-0b55320bb1a054441")
        stack = f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/abcd"
        for defect in (
            "trust",
            "extra_permission",
            "runtime",
            "different_role",
            "current",
            "wrong_stack",
            "no_stack",
            "no_template",
        ):
            installed = copy.deepcopy(old)
            stack_id = stack
            if defect == "trust":
                installed["Resources"]["OperatorRole"]["Properties"][
                    "AssumeRolePolicyDocument"
                ] = {}
            elif defect == "extra_permission":
                installed["Resources"]["OperatorRole"]["Properties"]["Policies"][0][
                    "PolicyDocument"
                ]["Statement"].append({"Effect": "Allow", "Action": "*", "Resource": "*"})
            elif defect == "runtime":
                installed["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"] = {}
            elif defect == "different_role":
                installed["Resources"]["OperatorRole"]["Properties"]["RoleName"] += "-foreign"
            elif defect == "current":
                installed = review["template"]
            elif defect == "wrong_stack":
                stack_id = stack.replace(STACK, "different-owner")
            elif defect == "no_stack":
                stack_id = None
            elif defect == "no_template":
                installed = None
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "bundle"
                with self.assertRaises(RuntimeError):
                    write_bundle(review, output, installed_template=installed, stack_id=stack_id)
                self.assertFalse(output.exists())

    def test_setup_refuses_template_drift_before_execution(self):
        calls = []
        base = self.installer_call(calls)

        def call(service, operation, *args, **kwargs):
            if operation == "get-template":
                return {"TemplateBody": {"Resources": {}}}
            return base(service, operation, *args, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "reviewed bytes"):
                install(
                    self.review["template"], Path(folder) / "review", call, pause=lambda _: None
                )
        self.assertNotIn("execute-change-set", calls)

    def test_packaged_standalone_installer_uses_reviewed_template_and_tested_flow(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "bundle"
            write_bundle(self.review, output)
            module = runpy.run_path(str(output / "fitfinity-install-probe-iam.py"))
            self.assertEqual(module["TEMPLATE"], self.review["template"])
            result = module["install"](
                module["TEMPLATE"],
                Path(folder) / "execution",
                self.installer_call(calls),
                pause=lambda _: None,
            )
            self.assertEqual(result["state"], "iam_setup_verified")
            self.assertEqual(result["template_sha256"], module["TEMPLATE_SHA256"])
        self.assertEqual(calls.count("execute-change-set"), 1)

        with patch("subprocess.run") as command:
            command.return_value = subprocess.CompletedProcess(
                [], 0, stdout='{"Account":"000000000000"}', stderr=""
            )
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "bundle"
                write_bundle(self.review, output)
                with self.assertRaisesRegex(SystemExit, "Wrong AWS account"):
                    runpy.run_path(
                        str(output / "fitfinity-install-probe-iam.py"), run_name="__main__"
                    )
            command.assert_called_once()
            self.assertEqual(command.call_args.args[0][:3], ["aws", "sts", "get-caller-identity"])
