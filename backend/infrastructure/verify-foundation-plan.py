import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import partial

ROOT = Path(__file__).resolve().parent

script = ROOT / "test-foundation-plan.py"
code = script.read_text()
compile(code, str(script), "exec")
t = json.loads((ROOT / "test-foundation.json").read_text())
r = t["Resources"]
p = r["Database"]["Properties"]


def refs(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "Ref":
                yield v
            elif k == "Fn::GetAtt":
                yield v[0]
            else:
                yield from refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from refs(v)


changes = [
    {"ResourceChange": {"LogicalResourceId": n, "ResourceType": v["Type"], "Action": "Add"}}
    for n, v in r.items()
]


def scenario(case):
    calls = []
    created = False

    def fake(args, **kw):
        nonlocal created
        service, op = args[1:3]
        calls.append((service, op))
        assert op not in {"execute-change-set", "delete-stack", "delete-change-set"}
        assert args[args.index("--profile") + 1] == "fitfinity-test"

        def result(value):
            return subprocess.CompletedProcess(args, 0, json.dumps(value), "")

        def missing():
            return subprocess.CompletedProcess(
                args, 254, "", "ValidationError: Stack or change set does not exist"
            )

        if op == "get-caller-identity":
            return result(
                {
                    "Account": "418638389566",
                    "Arn": "arn:aws:iam::418638389566:"
                    + ("root" if case == "wrong_identity" else "user/fitfinity-deployer"),
                }
            )
        if case == "access_denied":
            return subprocess.CompletedProcess(args, 254, "", "AccessDenied: not authorized")
        if op == "describe-stacks":
            if case in {"rerun", "existing_deployed"}:
                return result(
                    {
                        "Stacks": [
                            {
                                "StackStatus": "CREATE_COMPLETE"
                                if case == "existing_deployed"
                                else "REVIEW_IN_PROGRESS",
                                "Tags": [],
                            }
                        ]
                    }
                )
            return missing()
        if op == "describe-change-set":
            if not created and case != "rerun":
                return missing()
            c = json.loads(json.dumps(changes))
            if case == "unexpected_action":
                c[0]["ResourceChange"]["Action"] = "Remove"
            return result(
                {
                    "Status": "CREATE_COMPLETE",
                    "ExecutionStatus": "AVAILABLE",
                    "ChangeSetId": "arn:aws:cloudformation:ap-southeast-1:418638389566:"
                    "changeSet/mock/123",
                    "Changes": c,
                }
            )
        if op == "describe-vpcs":
            return result(
                {"Vpcs": [{"CidrBlock": "10.84.0.0/16" if case == "overlap" else "172.31.0.0/16"}]}
            )
        if op == "describe-db-instances":
            return result({"DBInstances": []})
        if op == "describe-orderable-db-instance-options":
            return result(
                {
                    "OrderableDBInstanceOptions": [
                        {
                            "StorageType": "gp3",
                            "SupportsStorageEncryption": True,
                            "MinStorageSize": 20,
                            "MaxStorageSize": 6144,
                            "AvailabilityZones": [
                                {"Name": "ap-southeast-1a"},
                                {"Name": "ap-southeast-1b"},
                            ],
                        }
                    ]
                }
            )
        if op == "validate-template":
            return result({})
        if op == "create-change-set":
            created = True
            assert args[args.index("--change-set-type") + 1] == "CREATE"
            return result({})
        if op == "get-template":
            return result({"TemplateBody": {} if case == "unexpected_template" else t})
        raise AssertionError(op)

    with tempfile.TemporaryDirectory() as td:
        status = 0
        with (
            patch.dict(os.environ, {"HOME": td}, clear=True),
            patch("subprocess.run", fake),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                exec(
                    compile(code, str(script), "exec"),
                    {"__name__": "__main__", "__file__": str(script)},
                )
            except SystemExit as ex:
                status = ex.code
        reports = list(Path(td).glob("Downloads/*.json"))
        if case in {"new", "rerun"}:
            assert status == 0 and len(reports) == 1
            receipt = json.loads(reports[0].read_text())
            assert not receipt["executed"]
            assert receipt["template"] == t and reports[0].stat().st_mode & 0o777 == 0o600
            assert created == (case == "new")
        else:
            assert status == 1 and not reports
        if case in {"wrong_identity", "overlap", "access_denied", "existing_deployed"}:
            assert not created
    print("PASS", case)


def test_invariants():
    assert len(r) == 20
    assert (
        p["PubliclyAccessible"] is False and p["StorageEncrypted"] and p["ManageMasterUserPassword"]
    )
    assert p["DeletionProtection"] and p["BackupRetentionPeriod"] == 1 and not p["MultiAZ"]
    assert "MasterUserPassword" not in p and p["MaxAllocatedStorage"] == 30
    assert r["Database"]["DeletionPolicy"] == r["Database"]["UpdateReplacePolicy"] == "Snapshot"
    assert r["DatabaseParameters"]["Properties"]["Parameters"]["rds.force_ssl"] == "1"
    assert all(
        x["Type"]
        not in {
            "AWS::EC2::Route",
            "AWS::EC2::InternetGateway",
            "AWS::EC2::NatGateway",
            "AWS::IAM::Role",
        }
        for x in r.values()
    )
    for v in r.values():
        if v["Type"] == "AWS::EC2::Subnet":
            assert not v["Properties"]["MapPublicIpOnLaunch"]
        if v["Type"] == "AWS::EC2::SecurityGroupIngress":
            assert v["Properties"]["FromPort"] == v["Properties"]["ToPort"] == 5432
            assert "SourceSecurityGroupId" in v["Properties"] and "CidrIp" not in v["Properties"]
    assert set(refs(t)) <= set(r)
    print(
        "PASS template protection, references, embedded template equa"
        "lity, and no-execution invariants"
    )


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        [
            *(
                unittest.FunctionTestCase(partial(scenario, value), description=str(value))
                for value in (
                    "new",
                    "rerun",
                    "wrong_identity",
                    "overlap",
                    "access_denied",
                    "unexpected_template",
                    "unexpected_action",
                    "existing_deployed",
                )
            ),
            unittest.FunctionTestCase(
                test_invariants, description="template, IAM and transport invariants"
            ),
        ]
    )
