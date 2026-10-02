import ast
import copy
import hmac
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_support import partial

ROOT = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("recovery", ROOT / "test-cognito-execute.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def scenario(case):
    m = load()
    writes = []
    confirmations = []
    updated = case in {"rerun", "rotation_off", "weak_email_guard", "broad_writes", "replacement"}
    policy = m.POOL_POLICY if updated else None

    def fake(service, op, *args, **kw):
        nonlocal updated, policy
        if op == "get-caller-identity":
            return {
                "Account": m.ACCOUNT,
                "Arn": f"arn:aws:iam::{m.ACCOUNT}:user/"
                + ("other" if case == "wrong_identity" else "fitfinity-deployer"),
            }
        if op == "get-account-plan-state":
            return {"accountPlanStatus": "ACTIVE", "accountPlanType": "FREE"}
        if op == "describe-stacks":
            if args[1] == m.FOUNDATION:
                return {"Stacks": [{"StackId": m.FOUNDATION, "StackStatus": "UPDATE_COMPLETE"}]}
            tags = dict(m.TAGS)
            if case == "foreign":
                tags["ManagedBy"] = "other"
            return {
                "Stacks": [
                    {
                        "StackId": m.STACK_ID,
                        "StackStatus": "UPDATE_COMPLETE" if updated else "CREATE_FAILED",
                        "EnableTerminationProtection": True,
                        "Parameters": [{"ParameterKey": "SessionHours", "ParameterValue": "8"}],
                        "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
                        "Outputs": [
                            {"OutputKey": "PoolId", "OutputValue": m.POOL_ID},
                            {"OutputKey": "ClientId", "OutputValue": "client"},
                        ],
                    }
                ]
            }
        if op == "get-template":
            template = copy.deepcopy(m.TEMPLATE)
            if not updated:
                del template["Resources"]["StaffPool"]["Properties"]["UserAttributeUpdateSettings"]
                template["Resources"]["StaffClient"]["Properties"]["WriteAttributes"] = ["name"]
            if case == "template":
                template["Description"] = "wrong"
            return {"TemplateBody": template}
        if op == "list-stack-resources":
            return {
                "StackResourceSummaries": [
                    {
                        "LogicalResourceId": "StaffPool",
                        "ResourceType": "AWS::Cognito::UserPool",
                        "PhysicalResourceId": "different" if case == "replacement" else m.POOL_ID,
                        "ResourceStatus": "UPDATE_COMPLETE" if updated else "CREATE_COMPLETE",
                    },
                    {
                        "LogicalResourceId": "StaffClient",
                        "ResourceType": "AWS::Cognito::UserPoolClient",
                        "ResourceStatus": "CREATE_COMPLETE" if updated else "CREATE_FAILED",
                        **({"PhysicalResourceId": "client"} if updated else {}),
                        "ResourceStatusReason": "Quota exceeded"
                        if case == "wrong_failure"
                        else "Invalid write attributes specified while creating a client",
                    },
                ]
            }
        if op == "describe-user-pool":
            p = copy.deepcopy(m.TEMPLATE["Resources"]["StaffPool"]["Properties"])
            p.update(
                Id=m.POOL_ID,
                Name=m.STACK + "-staff",
                SchemaAttributes=[
                    {"Name": "email", "Required": case != "schema", "Mutable": True},
                    {"Name": "name", "Required": False, "Mutable": True},
                ],
            )
            if case == "weak_email_guard":
                p["UserAttributeUpdateSettings"] = {}
            return {"UserPool": p}
        if op == "list-user-pool-clients":
            return {
                "UserPoolClients": [{"ClientId": "unexpected"}] if case == "existing_client" else []
            }
        if op == "validate-template":
            return {}
        if op == "get-stack-policy":
            return (
                {
                    "StackPolicyBody": json.dumps(
                        {"unexpected": True} if case == "foreign_policy" else policy
                    )
                }
                if policy or case == "foreign_policy"
                else {}
            )
        if op == "set-stack-policy":
            writes.append(op)
            policy = json.loads(args[-1])
            return {}
        if op == "update-stack":
            writes.append(op)
            if case == "update_denied":
                raise RuntimeError("Access denied")
            updated = True
            return {"StackId": m.STACK_ID}
        if op == "get-user-pool-mfa-config":
            return {"MfaConfiguration": "ON", "SoftwareTokenMfaConfiguration": {"Enabled": True}}
        if op == "describe-user-pool-client":
            assert args[-1] == m.CLIENT_QUERY
            c = copy.deepcopy(m.TEMPLATE["Resources"]["StaffClient"]["Properties"])
            c.update(
                ClientId="client",
                UserPoolId=m.POOL_ID,
                RefreshTokenValidity=8,
                HasClientSecret=True,
            )
            if case == "rotation_off":
                c["RefreshTokenRotation"]["Feature"] = "DISABLED"
            if case == "broad_writes":
                c["WriteAttributes"].append("email_verified")
            return c
        raise AssertionError(op)

    def confirm():
        confirmations.append(True)
        if case == "decline":
            raise RuntimeError("Declined")

    m.aws = fake
    m.confirm = confirm
    m.note = lambda _: None
    try:
        with patch.dict(m.os.environ, {}, clear=True):
            m.main()
        assert case in {"recover", "rerun"}
        assert m.REPORT["cognito_verified"]
    except RuntimeError:
        assert case not in {"recover", "rerun"}, case
        assert not m.REPORT["cognito_verified"]
    assert writes == (
        ["set-stack-policy", "update-stack"] if case in {"recover", "update_denied"} else []
    ), (case, writes)
    if case == "rerun":
        assert not confirmations


cases = [
    "recover",
    "rerun",
    "decline",
    "wrong_identity",
    "foreign",
    "template",
    "wrong_failure",
    "schema",
    "existing_client",
    "foreign_policy",
    "update_denied",
    "rotation_off",
    "weak_email_guard",
    "broad_writes",
    "replacement",
]


def test_invariants():
    # Run the canonical config audit directly, isolated from unavailable DB/boto runtime.
    admin = ROOT.parent / "app/auth/admin.py"
    node = next(
        n
        for n in ast.parse(admin.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "check_configuration"
    )
    ns = {"hmac": hmac}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(admin), "exec"), ns)
    m = load()
    pool = copy.deepcopy(m.TEMPLATE["Resources"]["StaffPool"]["Properties"])
    client = copy.deepcopy(m.TEMPLATE["Resources"]["StaffClient"]["Properties"])
    client.update(ClientSecret="test-only", RefreshTokenValidity=8)
    settings = SimpleNamespace(
        cognito_pool_id="pool",
        cognito_client_id="client",
        cognito_client_secret=SimpleNamespace(get_secret_value=lambda: "test-only"),
        auth_session_hours=8,
    )
    remote = SimpleNamespace(
        describe_user_pool=lambda **kw: {"UserPool": pool},
        describe_user_pool_client=lambda **kw: {"UserPoolClient": client},
        get_user_pool_mfa_config=lambda **kw: {
            "MfaConfiguration": "ON",
            "SoftwareTokenMfaConfiguration": {"Enabled": True},
        },
    )
    assert ns["check_configuration"](settings, remote) == 18
    for key, value in [
        ("WriteAttributes", ["name"]),
        ("WriteAttributes", ["email", "name", "email_verified"]),
        ("WriteAttributes", None),
    ]:
        client[key] = value
        try:
            ns["check_configuration"](settings, remote)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe attribute permissions accepted")
    client["WriteAttributes"] = ["name", "email"]
    assert ns["check_configuration"](settings, remote) == 18
    pool["UserAttributeUpdateSettings"] = {}
    try:
        ns["check_configuration"](settings, remote)
    except ValueError:
        pass
    else:
        raise AssertionError("Unverified email update accepted")
    # Existing canonical template test.
    p = ROOT.parent / "tests/test_auth_security.py"
    node = next(
        n
        for n in ast.parse(p.read_text()).body
        if isinstance(n, ast.FunctionDef)
        and n.name == "test_reviewed_template_keeps_staff_pool_private_and_mfa_required"
    )
    ns = {"Path": Path, "json": json, "__file__": str(p.resolve())}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(p), "exec"), ns)
    ns[node.name]()
    print(
        "PASS: 15 recovery scenarios; canonical configuration audit p"
        "ermission/email checks; canonical template test. No AWS call"
        "s."
    )


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        [
            *(
                unittest.FunctionTestCase(partial(scenario, value), description=str(value))
                for value in cases
            ),
            unittest.FunctionTestCase(
                test_invariants, description="template, IAM and transport invariants"
            ),
        ]
    )
