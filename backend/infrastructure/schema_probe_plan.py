"""Offline private catalog-probe template; does not create, invoke or delete AWS resources."""

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from deployment_profile import DEVELOPER, identities, load
from operator_checks import require
from schema_probe_iam import runtime_policy


def prepare(binding, *, now=None, profile=DEVELOPER):
    target = identities(profile)
    account, region = target["account"], target["region"]
    secret_prefix = re.escape(target["secret_prefix"])
    uri = target["registry"] + "/" + target["image_repository"]
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
        binding["account"] == account and binding["region"] == region,
        "Wrong deployment target",
    )
    for field, pattern in {
        "source_sha": r"[0-9a-f]{40}",
        "image_digest": r"sha256:[0-9a-f]{64}",
        "sql_sha256": r"[0-9a-f]{64}",
        "db_host": rf"[a-z0-9][a-z0-9-]{{0,62}}\.[a-z0-9]+\.{region}\.rds\.amazonaws\.com",
        "db_name": r"[A-Za-z][A-Za-z0-9_]{0,62}",
        "security_group_id": r"sg-[0-9a-f]{8,17}",
        "migration_secret_arn": (
            rf"arn:aws:secretsmanager:{region}:{account}:"
            rf"secret:{secret_prefix}/database/migration-[A-Za-z0-9]{{6}}"
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
    name = target["probe_name"]
    log_name = f"/aws/lambda/{name}"
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
                    "RoleName": target["runtime_role"],
                    "PermissionsBoundary": target["runtime_boundary"],
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
                            "PolicyDocument": runtime_policy(
                                binding["migration_secret_arn"], profile=profile
                            ),
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
                    "Code": {"ImageUri": uri + "@" + binding["image_digest"]},
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
                            "FITFINITY_AWS_ACCOUNT_ID": account,
                            "FITFINITY_AWS_REGION": region,
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


def prepare_review(binding, source_sha, sql, *, now=None, profile=DEVELOPER):
    """Bind the offline probe review to the checked-out source and packaged SQL."""
    require(binding.get("source_sha") == source_sha, "Probe source differs from checkout")
    require(
        binding.get("sql_sha256") == hashlib.sha256(sql).hexdigest(),
        "Probe SQL differs from packaged catalog query",
    )
    plan = prepare(binding, now=now, profile=profile)
    template_bytes = json.dumps(plan["template"], sort_keys=True, separators=(",", ":")).encode()
    return {
        **plan,
        "profile": dict(profile),
        "profile_sha256": identities(profile)["profile_sha256"],
        "bindings": dict(binding),
        "source_sha": source_sha,
        "sql_sha256": binding["sql_sha256"],
        "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
        "expires_at": binding["expires_at"],
        "image_attestation": "Not verified; review exact published image and scan receipt",
    }


def write_review(review, output):
    """Write a new immutable review directory with the exact probe request bytes."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "review.json").write_text(json.dumps(review, indent=2))
    (output / "template.json").write_text(
        json.dumps(review["template"], sort_keys=True, separators=(",", ":"))
    )
    (output / "invoke.json").write_text(json.dumps(review["invoke_payload"], separators=(",", ":")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--profile", type=Path, default=Path(__file__).with_name("targets") / "developer.json"
    )
    args = parser.parse_args()
    review = prepare_review(
        json.loads(args.bindings.read_text()),
        args.source_sha,
        Path(__file__).with_name("read-schema.sql").read_bytes(),
        profile=load(args.profile),
    )
    write_review(review, args.output)
