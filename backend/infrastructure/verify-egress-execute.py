import copy
import importlib.util
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from test_support import partial

ROOT = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("egress_exec", ROOT / "test-egress-execute.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m = m.create_operator() if hasattr(m, "create_operator") else m
    return m


def run(case):
    m = load()
    recovery = case.startswith("repair")
    updated = False
    present = case not in {"new", "decline", "ineligible", "ami_ineligible", "create_denied"}
    writes = []
    confirmations = []
    proof = {
        "bootstrap_files_match": True,
        "forward_policy": "drop",
        "forward_rule_count": 4,
        "nat_rule_count": 1,
        "ip_forward": "1",
        "jwks_key_count": 2,
    }
    ids = {k: k for k in m.TEMPLATE["Resources"]}
    ids["NatInstance"] = "i-test"
    arn = (
        m.FAILED_ARN
        if recovery
        else f"arn:aws:cloudformation:{m.REGION}:{m.ACCOUNT}:stack/{m.STACK}/test"
    )
    receipt = json.loads(
        (ROOT / "fixtures/Fitfinity_AWS_Egress_Preflight_qpz7194_.json").read_text()
    )
    if case == "ineligible":
        for x in receipt["instance_types"]:
            x["FreeTierEligible"] = False
    m.pf.main = lambda: None
    m.pf.context.report = receipt
    m.note = lambda _: None

    def fake(service, op, *args, **kw):
        nonlocal present, updated
        if op == "get-caller-identity":
            return {
                "Account": m.ACCOUNT,
                "Arn": f"arn:aws:iam::{m.ACCOUNT}:user/"
                + ("other" if case == "identity" else "fitfinity-deployer"),
            }
        if op == "describe-stacks":
            if not present:
                return None
            tags = dict(m.TAGS)
            if recovery:
                tags["TemplateSHA256"] = m.OLD_SHA
            if case == "foreign":
                tags["ManagedBy"] = "other"
            return {
                "Stacks": [
                    {
                        "StackId": arn,
                        "StackStatus": "CREATE_FAILED"
                        if case == "failed" or (recovery and not updated)
                        else ("UPDATE_COMPLETE" if recovery else "CREATE_COMPLETE"),
                        "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
                        "EnableTerminationProtection": True,
                    }
                ]
            }
        if op == "get-template":
            t = copy.deepcopy(m.OLD_TEMPLATE if recovery and not updated else m.TEMPLATE)
            if case == "template":
                t["Description"] = "other"
            return {"TemplateBody": t}
        if op == "describe-images":
            return {
                "Images": [] if case == "ami_ineligible" else [{"ImageId": "ami-021e6de04c7a84a9f"}]
            }
        if op == "validate-template":
            return {}
        if op == "create-stack":
            writes.append(op)
            if case == "create_denied":
                raise RuntimeError("Rejected")
            present = True
            return {"StackId": arn}
        if op == "describe-events":
            e = json.loads(
                (ROOT / "fixtures/Fitfinity_AWS_Egress_Failure_Details.json").read_text()
            )
            if case == "repair_wrong_error":
                e["OperationEvents"][-1]["ValidationStatusReason"] = "Different failure"
            return e
        if op == "update-stack":
            assert (
                args[args.index("--stack-name") + 1] == m.FAILED_ARN
                and "--disable-rollback" in args
            )
            writes.append(op)
            updated = True
            return {"StackId": arn}
        if op == "list-stack-resources" and recovery and not updated:
            return {
                "StackResourceSummaries": []
                if case != "repair_nonempty"
                else [{"PhysicalResourceId": "i-existing"}]
            }
        if op == "list-stack-resources":
            return {
                "StackResourceSummaries": [
                    {
                        "LogicalResourceId": k,
                        "PhysicalResourceId": ids[k],
                        "ResourceType": v["Type"],
                        "ResourceStatus": "CREATE_COMPLETE",
                    }
                    for k, v in m.TEMPLATE["Resources"].items()
                ]
            }
        if op == "describe-instances":
            return {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "ImageId": "ami-021e6de04c7a84a9f",
                                "InstanceType": "t4g.micro",
                                "VpcId": m.VPC,
                                "SubnetId": "PublicSubnet",
                                "State": {"Name": "running"},
                                "Placement": {"AvailabilityZone": "ap-southeast-1a"},
                                "MetadataOptions": {
                                    "HttpTokens": "optional" if case == "imds" else "required",
                                    "HttpPutResponseHopLimit": 1,
                                },
                                "BlockDeviceMappings": [
                                    {"DeviceName": "/dev/xvda", "Ebs": {"VolumeId": "vol"}}
                                ],
                            }
                        ]
                    }
                ]
            }
        if op == "describe-network-interfaces":
            return {
                "NetworkInterfaces": [
                    {
                        "SourceDestCheck": False,
                        "Attachment": {"InstanceId": "i-test"},
                        "Groups": [{"GroupId": "NatSecurityGroup"}],
                        "Association": {"PublicIp": "192.0.2.1"},
                    }
                ]
            }
        if op == "describe-volumes":
            return {
                "Volumes": [
                    {
                        "Encrypted": case != "unencrypted",
                        "Size": 8,
                        "VolumeType": "gp3",
                        "Iops": 3000,
                        "Throughput": 125,
                    }
                ]
            }
        if op == "describe-instance-credit-specifications":
            return {
                "InstanceCreditSpecifications": [
                    {"CpuCredits": "unlimited" if case == "credits" else "standard"}
                ]
            }
        if op == "describe-security-groups":

            def p(cidr):
                return {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": cidr}],
                }

            return {
                "SecurityGroups": [
                    {
                        "IpPermissions": [
                            p("0.0.0.0/0" if case == "public_ingress" else "10.84.32.0/23")
                        ],
                        "IpPermissionsEgress": [p("0.0.0.0/0")],
                    }
                ]
            }
        if op == "describe-route-tables":
            return {
                "RouteTables": [
                    *[
                        {
                            "RouteTableId": rid,
                            "Associations": [{"SubnetId": sid}],
                            "Routes": [
                                {"GatewayId": "local"},
                                {
                                    "DestinationCidrBlock": "0.0.0.0/0",
                                    "NetworkInterfaceId": "NatInterface",
                                    "State": "active",
                                },
                            ],
                        }
                        for rid, sid in m.pf.APP_ROUTES.items()
                    ],
                    {
                        "RouteTableId": "PublicRoutes",
                        "Routes": [{"GatewayId": "InternetGateway", "State": "active"}],
                    },
                    {
                        "RouteTableId": "DatabaseRoutes",
                        "Routes": [{"GatewayId": "bad" if case == "db_route" else "local"}],
                    },
                ]
            }
        if op == "describe-stack-events":
            return [{"Resource": "NatInstance", "Status": "CREATE_FAILED", "Reason": "Rejected"}]
        if op == "describe-instance-information":
            return {"InstanceInformationList": [{"PingStatus": "Online"}]}
        if op == "send-command":
            assert args[args.index("--document-name") + 1] == "AWS-RunShellScript"
            assert json.loads(args[args.index("--parameters") + 1])["commands"] == [m.CHECK_COMMAND]
            writes.append("host-check")
            return {"Command": {"CommandId": "cmd-test"}}
        if op == "get-command-invocation":
            return {
                "Status": "Failed" if case == "host_failed" else "Success",
                "StandardOutputContent": json.dumps(proof),
            }
        raise AssertionError(op)

    def confirm():
        confirmations.append(True)
        if case in {"decline", "repair_decline"}:
            raise RuntimeError("Declined")

    m.aws = fake
    m.confirm = confirm
    try:
        with patch.dict(os.environ, {}, clear=True):
            if case == "audit":
                m.verify({"StackId": arn}, check_host=False)
                assert writes == [] and m.context.report["host_check"] == {"performed": False}
            else:
                m.main()
        assert case in {"new", "rerun", "repair", "audit"}, case
        assert (
            m.context.report["egress_configuration_verified"]
            and not m.context.report["private_runtime_connectivity_verified"]
        )
    except RuntimeError:
        assert case not in {"new", "rerun", "repair", "audit"}, case
    assert ("create-stack" in writes) == (case in {"new", "create_denied"})
    assert ("update-stack" in writes) == (case == "repair")
    if case == "rerun":
        assert confirmations == []


cases = [
    "audit",
    "repair",
    "repair_nonempty",
    "repair_wrong_error",
    "repair_decline",
    "new",
    "rerun",
    "decline",
    "identity",
    "foreign",
    "template",
    "ineligible",
    "ami_ineligible",
    "create_denied",
    "failed",
    "imds",
    "unencrypted",
    "credits",
    "public_ingress",
    "db_route",
    "host_failed",
]


def test_invariants():
    m = load()
    # Regression: operator cannot run arbitrary host commands or issue destructive operations.
    for service, op, args in [
        ("ec2", "terminate-instances", []),
        ("ssm", "send-command", ["--parameters", '{"commands":["whoami"]}']),
    ]:
        with patch.object(subprocess, "run") as call:
            try:
                m.aws(service, op, *args)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unsafe operation accepted")
            call.assert_not_called()
    # CFN dependency cycle and forbidden resource/property checks.
    t = m.TEMPLATE
    resources = t["Resources"]
    graph = {k: set() for k in resources}

    def refs(x):
        if isinstance(x, dict):
            if "Ref" in x and x["Ref"] in resources:
                yield x["Ref"]
            if "Fn::GetAtt" in x:
                yield x["Fn::GetAtt"][0]
            for v in x.values():
                yield from refs(v)
        elif isinstance(x, list):
            for v in x:
                yield from refs(v)

    for k, v in resources.items():
        graph[k].update(refs(v.get("Properties", {})))
        d = v.get("DependsOn", [])
        graph[k].update([d] if isinstance(d, str) else d)

    def visit(k, path):
        assert k not in path, ("Dependency cycle", k, path)
        for d in graph[k]:
            visit(d, path | {k})

    for k in graph:
        visit(k, set())
    assert len(resources) == 15
    assert all(
        x["Type"] not in {"AWS::EC2::NatGateway", "AWS::RDS::DBInstance", "AWS::Lambda::Function"}
        for x in resources.values()
    )
    assert (
        resources["NatInstance"]["Properties"]["UserData"]["Fn::Base64"]
        == (ROOT.parent / "infrastructure/test-egress-bootstrap.sh").read_text()
    )
    assert resources["NatInstance"]["Properties"]["BlockDeviceMappings"][0]["Ebs"]["Encrypted"]
    assert resources["NatInstance"]["Properties"]["InstanceType"] == "t4g.micro"
    assert set(resources["NatInstance"]["Properties"]["BlockDeviceMappings"][0]["Ebs"]) <= {
        "DeleteOnTermination",
        "Encrypted",
        "Iops",
        "KmsKeyId",
        "SnapshotId",
        "VolumeSize",
        "VolumeType",
    }
    assert (
        m.OLD_TEMPLATE["Resources"]["NatInstance"]["Properties"]["BlockDeviceMappings"][0]["Ebs"][
            "Throughput"
        ]
        == 125
    )
    print(
        "PASS: 20 mocked execution scenarios, command/mutation guards"
        ", template dependency/security checks. No AWS calls."
    )


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        [
            *(
                unittest.FunctionTestCase(partial(run, value), description=str(value))
                for value in cases
            ),
            unittest.FunctionTestCase(
                test_invariants, description="template, IAM and transport invariants"
            ),
        ]
    )
