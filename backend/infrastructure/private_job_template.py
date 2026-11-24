"""Render fixed private probe/upgrade Lambda entry points and their narrow runtime policies."""

import re
import time

from deployment_profile import identities, template_rules
from operator_checks import require
from schema_probe_iam import runtime_policy


def validate_binding(binding, *, profile, extra_patterns, now=None):
    """Validate shared target, image, secret, network and short-lived intent bindings."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    secret_prefix = re.escape(target["secret_prefix"])
    require(
        isinstance(binding, dict)
        and set(binding)
        == {
            "account",
            "region",
            "source_sha",
            "image_digest",
            "db_host",
            "db_name",
            "migration_secret_arn",
            "subnet_ids",
            "security_group_id",
            "expires_at",
        }
        | set(extra_patterns),
        "Exact reviewed private-job bindings required",
    )
    require(
        binding["account"] == account and binding["region"] == region,
        "Wrong deployment target",
    )
    for field, pattern in {
        "source_sha": r"[0-9a-f]{40}",
        "image_digest": r"sha256:[0-9a-f]{64}",
        **extra_patterns,
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
        "Private job requires a future expiry within one hour",
    )
    return target


def render(binding, *, profile, kind):
    """Render only a known private handler after the owning planner validates bindings."""
    target = identities(profile)
    require(kind in {"probe", "upgrade"}, "Unknown private job kind")
    account, region = target["account"], target["region"]
    uri = target["registry"] + "/" + target["image_repository"]
    subnets = binding["subnet_ids"]
    name = target["probe_name" if kind == "probe" else "upgrade_name"]
    log_name = f"/aws/lambda/{name}"
    function_id = "Probe" if kind == "probe" else "Upgrade"
    role_id, logs_id = function_id + "Role", function_id + "Logs"
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Temporary private catalog probe; no public trigger or migrations",
        "Resources": {
            logs_id: {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {"LogGroupName": log_name, "RetentionInDays": 1},
            },
            role_id: {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": target[
                        "runtime_role" if kind == "probe" else "upgrade_runtime_role"
                    ],
                    "PermissionsBoundary": target[
                        "runtime_boundary" if kind == "probe" else "upgrade_boundary"
                    ],
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
                            "PolicyName": "ReadCatalogProbe"
                            if kind == "probe"
                            else "ReviewedUpgrade",
                            "PolicyDocument": runtime_policy(
                                binding["migration_secret_arn"], profile=profile, purpose=kind
                            ),
                        }
                    ],
                },
            },
            function_id: {
                "Type": "AWS::Lambda::Function",
                "DependsOn": logs_id,
                "Properties": {
                    "FunctionName": name,
                    "PackageType": "Image",
                    "Architectures": ["x86_64"],
                    "Code": {"ImageUri": uri + "@" + binding["image_digest"]},
                    "Role": {"Fn::GetAtt": [role_id, "Arn"]},
                    "MemorySize": 512,
                    "Timeout": 60 if kind == "probe" else 120,
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
                            (
                                "app.schema_probe:create_app"
                                if kind == "probe"
                                else "app.release_upgrade_service:create_app"
                            ),
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
                        }
                    },
                },
            },
        },
    }
    environment = template["Resources"][function_id]["Properties"]["Environment"]["Variables"]
    if kind == "probe":
        environment.update(
            {
                "FITFINITY_PROBE_SOURCE_SHA": binding["source_sha"],
                "FITFINITY_PROBE_SQL_SHA256": binding["sql_sha256"],
                "FITFINITY_PROBE_EXPIRES_AT": str(binding["expires_at"]),
            }
        )
    else:
        template["Description"] = (
            "Private reviewed populated upgrade; no public trigger or bootstrap"
        )
        template["Rules"] = template_rules(profile)
        environment.update(
            {
                "FITFINITY_UPGRADE_SOURCE_SHA": binding["source_sha"],
                "FITFINITY_UPGRADE_OPERATION_ID": binding["operation_id"],
                "FITFINITY_UPGRADE_FROM": binding["from_revision"],
                "FITFINITY_UPGRADE_TO": binding["to_revision"],
                "FITFINITY_UPGRADE_EXPIRES_AT": str(binding["expires_at"]),
            }
        )
    return template
