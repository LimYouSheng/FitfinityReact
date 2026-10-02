import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import partial

ROOT = Path(__file__).resolve().parent

script = ROOT / "test-foundation-execute.py"
code = script.read_text()
compile(code, str(script), "exec")
definitions = code


def scenario(case):
    ns = {"__file__": str(script), "__name__": "operator"}
    exec(compile(definitions, str(script), "exec"), ns)
    calls = []
    executed = False
    tags = [
        {"Key": k, "Value": v}
        for k, v in {
            "Application": "Fitfinity",
            "Environment": "test",
            "ManagedBy": "fitfinity-foundation-planner",
            "TemplateSHA256": ns["HASH"],
        }.items()
    ]
    outputs = {
        "Vpc": "vpc-test",
        "DatabaseSecurityGroup": "sg-db",
        "AdminSecretArn": "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:rds-test",
    }

    def fake(service, op, *args, **kwargs):
        nonlocal executed
        assert (service, op) in ns["ALLOWED"]
        calls.append((service, op))
        if op == "get-caller-identity":
            return {
                "Account": ns["ACCOUNT"],
                "Arn": f"arn:aws:iam::{ns['ACCOUNT']}:"
                + ("root" if case == "wrong_identity" else "user/fitfinity-deployer"),
            }
        if op == "describe-stacks":
            return {
                "Stacks": [
                    {
                        "StackId": f"arn:aws:cloudformation:{ns['REGION']}:{ns['ACCOUNT']}:"
                        f"stack/{ns['STACK']}/123",
                        "StackStatus": "UPDATE_COMPLETE"
                        if executed or case == "resume_complete"
                        else "CREATE_FAILED",
                        "Tags": tags,
                        "Outputs": [{"OutputKey": k, "OutputValue": v} for k, v in outputs.items()],
                    }
                ]
            }
        if op == "describe-change-set":
            return {
                "ChangeSetId": ns["CHANGE"],
                "Status": "CREATE_COMPLETE",
                "ExecutionStatus": "AVAILABLE",
                "Tags": tags,
                "Changes": [
                    {
                        "ResourceChange": {
                            "LogicalResourceId": n,
                            "ResourceType": v["Type"],
                            "Action": "Add",
                        }
                    }
                    for n, v in ns["TEMPLATE"]["Resources"].items()
                ],
            }
        if op == "get-template":
            template = json.loads(json.dumps(ns["TEMPLATE"]))
            if not executed and case != "resume_complete":
                template["Resources"]["Database"]["Properties"]["BackupRetentionPeriod"] = 14
            return {"TemplateBody": {} if case == "tampered_template" else template}
        if op == "list-stack-resources":
            resources = [
                {
                    "LogicalResourceId": n,
                    "ResourceType": v["Type"],
                    "ResourceStatus": "CREATE_FAILED" if n == "Database" else "CREATE_COMPLETE",
                    "ResourceStatusReason": (
                        "unrelated failure"
                        if case == "different_failure"
                        else (
                            "The specified backup retention period exceeds the maximum av"
                            "ailable to free tier customers"
                        )
                    ),
                }
                for n, v in ns["TEMPLATE"]["Resources"].items()
            ]
            if case == "incomplete_network":
                resources[0]["ResourceStatus"] = "CREATE_FAILED"
            return {"StackResourceSummaries": resources}
        if op == "describe-db-instances" and "--query" in args:
            return ["fitfinity-test-db"] if case == "existing_database" else []
        if op == "get-account-plan-state":
            return {
                "accountPlanType": "FREE",
                "accountPlanStatus": "ACTIVE",
                "accountPlanRemainingCredits": {"amount": 100, "unit": "USD"},
            }
        if op == "get-products":
            if case == "pricing_missing":
                return {"PriceList": []}
            filters = json.loads(args[args.index("--filters") + 1])
            storage = any(x["Value"] == "Database Storage" for x in filters)
            return {
                "PriceList": [
                    json.dumps(
                        {
                            "product": {
                                "sku": "storage" if storage else "compute",
                                "attributes": {"volumeType": "General Purpose-GP3"},
                            },
                            "terms": {
                                "OnDemand": {
                                    "mock": {
                                        "effectiveDate": "2026-09-22",
                                        "priceDimensions": {
                                            "dimension": {
                                                "unit": "GB-Mo" if storage else "Hrs",
                                                "beginRange": "0",
                                                "endRange": "Inf",
                                                "pricePerUnit": {
                                                    "USD": "0.138" if storage else "0.026"
                                                },
                                                "description": "mock only",
                                            }
                                        },
                                    }
                                }
                            },
                        }
                    )
                ]
            }
        if op == "update-stack":
            assert "--disable-rollback" in args
            submitted = json.loads(
                Path(args[args.index("--template-body") + 1].removeprefix("file://")).read_text()
            )
            assert submitted == ns["TEMPLATE"]
            assert submitted["Resources"]["Database"]["Properties"]["BackupRetentionPeriod"] == 1
            if case == "execution_denied":
                raise RuntimeError("AccessDenied")
            executed = True
            return {}
        if op == "describe-db-instances":
            return {
                "DBInstances": [
                    {
                        "Engine": "postgres",
                        "EngineVersion": "17.11",
                        "DBInstanceClass": "db.t4g.micro",
                        "PubliclyAccessible": case == "wrong_database",
                        "StorageEncrypted": True,
                        "DeletionProtection": True,
                        "MultiAZ": False,
                        "BackupRetentionPeriod": 1,
                        "StorageType": "gp3",
                        "MaxAllocatedStorage": 30,
                        "DBInstanceStatus": "available",
                        "AllocatedStorage": 20,
                        "DBSubnetGroup": {"VpcId": "vpc-test"},
                        "VpcSecurityGroups": [{"VpcSecurityGroupId": "sg-db"}],
                        "MasterUserSecret": {
                            "SecretStatus": "active",
                            "SecretArn": outputs["AdminSecretArn"],
                        },
                        "DBParameterGroups": [
                            {"DBParameterGroupName": "test", "ParameterApplyStatus": "in-sync"}
                        ],
                    }
                ]
            }
        if op == "describe-db-parameters":
            return [{"Name": "rds.force_ssl", "Value": "1"}]
        if op in ("update-termination-protection", "set-stack-policy"):
            return {}
        raise AssertionError(op)

    def confirm():
        if case == "declined":
            raise RuntimeError("Confirmation declined")

    ns["aws"] = fake
    ns["confirm"] = confirm
    with tempfile.TemporaryDirectory() as td:
        failed = False
        with (
            patch.dict(os.environ, {"HOME": td}, clear=True),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                ns["main"]()
            except RuntimeError:
                failed = True
        receipts = list(Path(td).glob("Downloads/*.json"))
        if case in ("success", "resume_complete"):
            assert not failed and len(receipts) == 1
            assert json.loads(receipts[0].read_text())["foundation_verified"]
            assert receipts[0].stat().st_mode & 0o777 == 0o600
        else:
            assert failed and not receipts
        if case in (
            "declined",
            "pricing_missing",
            "tampered_template",
            "wrong_identity",
            "resume_complete",
            "existing_database",
            "different_failure",
            "incomplete_network",
        ):
            assert ("cloudformation", "update-stack") not in calls
        if case == "wrong_database":
            assert ("cloudformation", "set-stack-policy") not in calls
    print("PASS", case)


def test_invariants():
    # Ensure the actual low-level wrapper blocks unrelated writes before invoking a subprocess.
    ns = {"__file__": str(script), "__name__": "operator"}
    exec(compile(definitions, str(script), "exec"), ns)
    with patch("subprocess.run", side_effect=AssertionError("must not run")):
        try:
            ns["aws"]("cloudformation", "delete-stack", "--stack-name", "anything")
        except RuntimeError:
            pass
        else:
            raise AssertionError("delete was allowed")
    print("PASS disallowed operation refusal")


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        [
            *(
                unittest.FunctionTestCase(partial(scenario, value), description=str(value))
                for value in (
                    "success",
                    "declined",
                    "pricing_missing",
                    "tampered_template",
                    "wrong_identity",
                    "wrong_database",
                    "resume_complete",
                    "execution_denied",
                    "existing_database",
                    "different_failure",
                    "incomplete_network",
                )
            ),
            unittest.FunctionTestCase(
                test_invariants, description="template, IAM and transport invariants"
            ),
        ]
    )
