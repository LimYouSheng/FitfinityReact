import base64
import hashlib
import importlib.util
import io
import json
import os
import ssl
import subprocess
import unittest
import urllib
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_support import partial

ROOT = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("probe", ROOT / "test-private-egress.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m = m.create_operator() if hasattr(m, "create_operator") else m
    return m


def run(case):
    m = load()
    present = case == "rerun"
    deleted = False
    writes = []
    confirmations = []
    arn = f"arn:aws:cloudformation:{m.REGION}:{m.ACCOUNT}:stack/{m.STACK}/probe-test"
    m.note = lambda _: None
    m.check_network = lambda: None
    m.costs = lambda: None

    def fake(service, op, *args, **kw):
        nonlocal present, deleted
        if op == "get-caller-identity":
            return {
                "Account": m.ACCOUNT,
                "Arn": f"arn:aws:iam::{m.ACCOUNT}:user/"
                + ("other" if case == "identity" else "fitfinity-deployer"),
            }
        if op == "get-account-plan-state":
            return {"accountPlanType": "FREE", "accountPlanStatus": "ACTIVE"}
        if op == "describe-stacks":
            if not present or deleted:
                return None
            return {
                "Stacks": [
                    {
                        "StackId": arn,
                        "StackStatus": "CREATE_COMPLETE",
                        "Tags": [{"Key": k, "Value": v} for k, v in m.TAGS.items()],
                    }
                ]
            }
        if op == "get-template":
            return {"TemplateBody": m.TEMPLATE}
        if op == "validate-template":
            return {}
        if op == "create-stack":
            present = True
            writes.append(op)
            return {"StackId": arn}
        if op == "get-function":
            suffix = args[1][-1].upper()
            p = m.TEMPLATE["Resources"]["Probe" + suffix]["Properties"]
            return {
                "Configuration": {
                    "FunctionArn": f"arn:aws:lambda:{m.REGION}:{m.ACCOUNT}:function:" + args[1],
                    "State": "Active",
                    "Runtime": "python3.12",
                    "Handler": "index.handler",
                    "Architectures": ["arm64"],
                    "MemorySize": 128,
                    "Timeout": 30,
                    "VpcConfig": {**p["VpcConfig"], "VpcId": m.e.VPC},
                    "CodeSha256": "wrong"
                    if case == "hash"
                    else base64.b64encode(hashlib.sha256(blob).digest()).decode(),
                },
                "Code": {"Location": "https://example.invalid/code"},
            }
        if op == "invoke":
            writes.append(args[1])
            suffix = args[1][-1].upper()
            if case == "fail" + suffix:
                return {"StatusCode": 200, "FunctionError": "Unhandled"}
            Path(args[-1]).write_text(
                json.dumps(
                    {
                        "https_verified": True,
                        "egress_ip": "wrong" if case == "ip" else "52.77.93.192",
                        "jwks_key_count": 2,
                    }
                )
            )
            return {"StatusCode": 200}
        if op == "list-stack-resources":
            return {
                "StackResourceSummaries": [
                    {"LogicalResourceId": k, "ResourceType": v["Type"]}
                    for k, v in m.TEMPLATE["Resources"].items()
                ]
                + ([{"LogicalResourceId": "unexpected"}] if case == "inventory" else [])
            }
        if op == "delete-stack":
            writes.append(op)
            deleted = True
            return {}
        raise AssertionError(op)

    def confirm():
        confirmations.append(True)
        if case == "decline":
            raise RuntimeError("declined")

    m.aws = fake
    m.confirm = confirm
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(
            "unexpected.py" if case == "entries" else "index.py",
            "changed"
            if case == "code"
            else m.TEMPLATE["Resources"]["ProbeA"]["Properties"]["Code"]["ZipFile"],
        )
    blob = b"not a zip" if case == "archive" else b.getvalue()

    def download(*a, **kw):
        if case == "tls":
            raise urllib.error.URLError(
                ssl.SSLCertVerificationError(1, "certificate verify failed")
            )
        if case == "http":
            raise urllib.error.HTTPError(
                "https://example.invalid/?SECRET", 403, "forbidden", {}, None
            )
        return io.BytesIO(blob)

    try:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(urllib.request, "urlopen", side_effect=download),
        ):
            m.main()
        assert case in {"new", "rerun"}
        assert (
            m.context.report["private_runtime_connectivity_verified"]
            and m.context.report["cleanup_complete"]
        )
    except RuntimeError as ex:
        assert case not in {"new", "rerun"}
        assert "SECRET" not in str(ex) and "https://" not in str(ex)
    assert ("delete-stack" in writes) == (case in {"new", "rerun"})
    if case in {"tls", "http", "hash", "entries", "archive", "code"}:
        assert not any(x.startswith("fitfinity-test-egress-probe-") for x in writes)
        assert m.context.report["code_verification"]["A"]["stage"] != "verified"
        assert "SECRET" not in json.dumps(m.context.report)
    if case in {"identity", "decline"}:
        assert not writes
    if case == "failA":
        assert "fitfinity-test-egress-probe-b" not in writes


def test_invariants():
    m = load()
    for args in [
        ("cloudformation", "delete-stack", "--stack-name", "fitfinity-test-foundation"),
        ("lambda", "invoke", "--function-name", "other"),
        ("secretsmanager", "get-secret-value"),
    ]:
        with patch.object(subprocess, "run") as call:
            try:
                m.aws(*args)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Guard bypass")
            call.assert_not_called()
    # Actual probe handler rejects wrong NAT address and non-200 responses.
    spec = importlib.util.spec_from_file_location("handler", ROOT / "private-egress-probe.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    h = h.create_operator() if hasattr(h, "create_operator") else h
    for address, passes in [("52.77.93.192", True), ("203.0.113.1", False)]:
        with patch.object(h, "read_https", side_effect=[b'{"keys":[{}]}', address.encode()]):
            try:
                assert h.handler({}, None)["https_verified"] and passes
            except RuntimeError:
                assert not passes

    class Response:
        status = 302

    with patch.object(h.http.client, "HTTPSConnection") as conn:
        conn.return_value.getresponse.return_value = Response()
        try:
            h.read_https("example.invalid", "/", 1)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Redirect accepted")
    # Prices must use refreshed numbers, not hard-coded previous totals.
    prices = {
        "nat_compute": "0.0106",
        "nat_storage": "0.096",
        "ipv4": "0.005",
        "db_compute": "0.025",
        "db_storage": "0.138",
    }
    with patch.object(m.e.pf, "rate", side_effect=[{"usd": v} for v in prices.values()]):
        m.costs()
    from decimal import Decimal

    assert Decimal(m.context.report["monthly_base_usd"]["combined"]) == Decimal("33.566")
    assert len(m.TEMPLATE["Resources"]) == 5
    assert all("secretsmanager" not in json.dumps(r) for r in m.TEMPLATE["Resources"].values())
    print(
        "PASS: 14 orchestration scenarios; mutation guards; exact-cod"
        "e, handler and cost checks. No AWS calls."
    )


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        [
            *(
                unittest.FunctionTestCase(partial(run, value), description=str(value))
                for value in [
                    "tls",
                    "http",
                    "hash",
                    "entries",
                    "archive",
                    "new",
                    "rerun",
                    "identity",
                    "decline",
                    "code",
                    "ip",
                    "failA",
                    "failB",
                    "inventory",
                ]
            ),
            unittest.FunctionTestCase(
                test_invariants, description="template, IAM and transport invariants"
            ),
        ]
    )
