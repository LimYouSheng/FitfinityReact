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
    s = importlib.util.spec_from_file_location("egress", ROOT / "test-egress-preflight.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    m = m.create_operator() if hasattr(m, "create_operator") else m
    return m


def run(case):
    m = load()

    def fake(service, op, *args, **kwargs):
        if op == "get-caller-identity":
            return {
                "Account": m.ACCOUNT,
                "Arn": f"arn:aws:iam::{m.ACCOUNT}:user/"
                + ("other" if case == "identity" else "fitfinity-deployer"),
            }
        if op == "get-account-plan-state":
            return {"accountPlanStatus": "ACTIVE", "accountPlanType": "FREE"}
        if op == "describe-stacks":
            return {"Stacks": [{"StackId": args[1], "StackStatus": "UPDATE_COMPLETE"}]}
        if op == "describe-vpcs":
            return {
                "Vpcs": [{"CidrBlock": "10.84.0.0/16", "IsDefault": False, "State": "available"}]
            }
        if op == "describe-subnets":
            return {
                "Subnets": [
                    {
                        "SubnetId": v,
                        "CidrBlock": (
                            "10.84.0.0/24" if case == "cidr" else "10.84." + str(32 + i) + ".0/24"
                        ),
                        "MapPublicIpOnLaunch": False,
                    }
                    for i, v in enumerate(m.APP_ROUTES.values())
                ]
            }
        if op == "describe-route-tables":
            return {
                "RouteTables": [
                    {
                        "RouteTableId": k,
                        "Associations": [{"SubnetId": v}],
                        "Routes": [
                            {
                                "GatewayId": "igw-other" if case == "route" else "local",
                                "DestinationCidrBlock": "10.84.0.0/16",
                                "State": "active",
                            }
                        ],
                    }
                    for k, v in m.APP_ROUTES.items()
                ]
            }
        for operation, key in [
            ("describe-internet-gateways", "InternetGateways"),
            ("describe-nat-gateways", "NatGateways"),
            ("describe-vpc-endpoints", "VpcEndpoints"),
            ("describe-security-groups", "SecurityGroups"),
            ("describe-network-acls", "NetworkAcls"),
        ]:
            if op == operation:
                assert args[0] == ("--filter" if op == "describe-nat-gateways" else "--filters"), (
                    op,
                    args,
                )
                return {
                    key: [{"State": "available"}]
                    if case == "existing_egress" and key == "NatGateways"
                    else []
                }
        if op == "describe-instances":
            return {"Reservations": []}
        if op == "get-parameter":
            return {"Parameter": {"Value": "ami-test"}}
        if op == "describe-images":
            return {
                "Images": [
                    {
                        "ImageId": "ami-test",
                        "Architecture": "x86_64" if case == "ami" else "arm64",
                        "State": "available",
                        "RootDeviceType": "ebs",
                        "VirtualizationType": "hvm",
                        "RootDeviceName": "/dev/xvda",
                        "BlockDeviceMappings": [
                            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 8}}
                        ],
                    }
                ]
            }
        if op == "describe-instance-type-offerings":
            return {
                "InstanceTypeOfferings": [
                    {"InstanceType": s}
                    for s in (["t4g.nano"] if case == "offering" else ["t4g.nano", "t4g.micro"])
                ]
            }
        if op == "describe-instance-types":
            return {"InstanceTypes": []}
        if op == "get-products":
            filters = {f["Field"]: f["Value"] for f in json.loads(args[-1])}
            amount = "0.005"
            unit = "Hrs"
            if filters.get("instanceType") == "t4g.nano":
                amount = "0.0056"
            if filters.get("instanceType") == "t4g.micro":
                amount = "0.0112"
            if filters.get("volumeApiName") == "gp3":
                amount = "0.096"
                unit = "GB-Mo"
            product = {
                "product": {"sku": "test"},
                "terms": {
                    "OnDemand": {
                        "t": {
                            "priceDimensions": {
                                "d": {
                                    "unit": unit,
                                    "beginRange": "0",
                                    "endRange": "Inf",
                                    "pricePerUnit": {"USD": amount},
                                    "description": "test rate",
                                }
                            }
                        }
                    }
                },
            }
            return {
                "PriceList": []
                if case == "price_missing"
                else [json.dumps(product)] * (2 if case == "price_ambiguous" else 1)
            }
        raise AssertionError(op)

    m.aws = fake
    m.note = lambda _: None
    try:
        with patch.dict(os.environ, {}, clear=True):
            m.main()
        assert case == "ok"
        assert (
            m.context.report["preflight_passed"]
            and m.context.report["monthly_base_usd"]["t4g.nano"] == "8.5060"
        )
    except RuntimeError:
        assert case != "ok"


def test_invariants():
    m = load()
    for operation in [("ec2", "run-instances"), ("ec2", "create-route"), ("ssm", "get-parameter")]:
        with patch.object(subprocess, "run") as call:
            try:
                m.aws(*operation, "--name", "/private/secret")
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unsafe operation allowed")
            call.assert_not_called()
    print(
        "PASS: 9 mocked preflight scenarios; cloud-write and private-"
        "parameter guards. No AWS calls."
    )


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        [
            *(
                unittest.FunctionTestCase(partial(run, value), description=str(value))
                for value in [
                    "ok",
                    "identity",
                    "cidr",
                    "route",
                    "existing_egress",
                    "ami",
                    "offering",
                    "price_missing",
                    "price_ambiguous",
                ]
            ),
            unittest.FunctionTestCase(
                test_invariants, description="template, IAM and transport invariants"
            ),
        ]
    )
