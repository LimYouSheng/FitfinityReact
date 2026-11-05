"""Offline private catalog-probe template; does not create, invoke or delete AWS resources."""

import argparse
import json
import re
import time
from pathlib import Path

import hosting_design as design
from operator_checks import require
from release_image import URI


def prepare(binding, *, now=None):
    require(
        set(binding)
        == {
            "account",
            "region",
            "source_sha",
            "image_digest",
            "sql_sha256",
            "db_host",
            "db_name",
            "migration_secret_arn",
            "subnet_ids",
            "security_group_id",
            "expires_at",
        },
        "Exact reviewed probe bindings required",
    )
    require(
        binding["account"] == design.ACCOUNT and binding["region"] == design.REGION,
        "Wrong developer target",
    )
    for field, pattern in {
        "source_sha": r"[0-9a-f]{40}",
        "image_digest": r"sha256:[0-9a-f]{64}",
        "sql_sha256": r"[0-9a-f]{64}",
        "db_host": rf"[a-z0-9][a-z0-9-]{{0,62}}\.[a-z0-9]+\.{design.REGION}\.rds\.amazonaws\.com",
        "db_name": r"[A-Za-z][A-Za-z0-9_]{0,62}",
        "security_group_id": r"sg-[0-9a-f]{8,17}",
        "migration_secret_arn": (
            rf"arn:aws:secretsmanager:{design.REGION}:{design.ACCOUNT}:"
            r"secret:fitfinity/test/[A-Za-z0-9/_+=.@-]+-[A-Za-z0-9]{6}"
        ),
    }.items():
        require(
            isinstance(binding[field], str) and re.fullmatch(pattern, binding[field]),
            f"Invalid {field}",
        )
    subnets = binding["subnet_ids"]
    require(
        isinstance(subnets, list)
        and len(subnets) == 2
        and all(
            isinstance(value, str) and re.fullmatch(r"subnet-[0-9a-f]{8,17}", value)
            for value in subnets
        )
        and len(set(subnets)) == 2,
        "Two reviewed distinct private subnets required",
    )
    require(
        type(binding["expires_at"]) is int
        and 0 < binding["expires_at"] - (time.time() if now is None else now) <= 3600,
        "Probe requires a future expiry within one hour",
    )
    name = "fitfinity-test-schema-observe"
    function_arn = f"arn:aws:lambda:{design.REGION}:{design.ACCOUNT}:function:{name}"
    log_name = f"/aws/lambda/{name}"
    eni = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses",
    ]
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Temporary private catalog probe; no public trigger or migrations",
        "Resources": {
            "ProbeLogs": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {"LogGroupName": log_name, "RetentionInDays": 1},
            },
            "ProbeRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "lambda.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    },
                    "Policies": [
                        {
                            "PolicyName": "ReadCatalogProbe",
                            "PolicyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": "secretsmanager:GetSecretValue",
                                        "Resource": binding["migration_secret_arn"],
                                        "Condition": {
                                            "StringEquals": {
                                                "secretsmanager:VersionStage": "AWSCURRENT"
                                            }
                                        },
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                                        "Resource": (
                                            f"arn:aws:logs:{design.REGION}:{design.ACCOUNT}:"
                                            f"log-group:{log_name}:*"
                                        ),
                                    },
                                    {"Effect": "Allow", "Action": eni, "Resource": "*"},
                                    {
                                        "Effect": "Deny",
                                        "Action": eni + ["ec2:DetachNetworkInterface"],
                                        "Resource": "*",
                                        "Condition": {
                                            "ArnEquals": {"lambda:SourceFunctionArn": function_arn}
                                        },
                                    },
                                ],
                            },
                        }
                    ],
                },
            },
            "Probe": {
                "Type": "AWS::Lambda::Function",
                "DependsOn": "ProbeLogs",
                "Properties": {
                    "FunctionName": name,
                    "PackageType": "Image",
                    "Architectures": ["x86_64"],
                    "Code": {"ImageUri": URI + "@" + binding["image_digest"]},
                    "Role": {"Fn::GetAtt": ["ProbeRole", "Arn"]},
                    "MemorySize": 512,
                    "Timeout": 60,
                    "ReservedConcurrentExecutions": 1,
                    "VpcConfig": {
                        "SubnetIds": list(subnets),
                        "SecurityGroupIds": [binding["security_group_id"]],
                    },
                    "ImageConfig": {
                        "EntryPoint": [],
                        "WorkingDirectory": "/app",
                        "Command": [
                            "python",
                            "-m",
                            "uvicorn",
                            "app.schema_probe:create_app",
                            "--factory",
                            "--host",
                            "0.0.0.0",
                            "--port",
                            "8080",
                            "--no-access-log",
                            "--no-proxy-headers",
                            "--log-level",
                            "critical",
                        ],
                    },
                    "Environment": {
                        "Variables": {
                            "AWS_LWA_PORT": "8080",
                            "AWS_LWA_READINESS_CHECK_PATH": "/health/live",
                            "AWS_LWA_PASS_THROUGH_PATH": "/events",
                            "FITFINITY_CONFIG_SOURCE": "aws-secrets-manager",
                            "FITFINITY_ENVIRONMENT": "staging",
                            "FITFINITY_AWS_ACCOUNT_ID": design.ACCOUNT,
                            "FITFINITY_DATABASE_SECRET_ARN": binding["migration_secret_arn"],
                            "FITFINITY_DB_HOST": binding["db_host"],
                            "FITFINITY_DB_NAME": binding["db_name"],
                            "FITFINITY_PROBE_SOURCE_SHA": binding["source_sha"],
                            "FITFINITY_PROBE_SQL_SHA256": binding["sql_sha256"],
                            "FITFINITY_PROBE_EXPIRES_AT": str(binding["expires_at"]),
                        }
                    },
                },
            },
        },
    }
    return {
        "decision": "HOLD",
        "template": template,
        "invoke_payload": {"operation": "observe-schema"},
        "required_evidence": [
            "Account-plan eligibility, cost and explicit create/invoke/delete authority",
            "Review secret KMS key; any required customer-key decrypt grant must be exact",
            "Verify subnet/VPC/security-group/secret identities and private connectivity",
            "Scanned image/source/SQL bindings; reviewed operator IAM; no hosting-role broadening",
            "Inspect function bindings and no public triggers before synchronous invocation",
            "Retain receipt; delete only the probe stack; verify cleanup; expiry is not cleanup",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(prepare(json.loads(args.bindings.read_text())), indent=2))
