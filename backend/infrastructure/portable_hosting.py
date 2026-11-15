"""Bind shared hosting resources to independently reviewed target metadata."""

import hashlib
import json
import re

from deployment_profile import identities, template_rules
from hosting_design import app_template, attr, resource, waf
from operator_checks import require
from portable_services import policy

FIELDS = {
    "database_secret",
    "auth_secret",
    "db_host",
    "pool",
    "client",
    "subnets",
    "security_groups",
    "image",
    "environment",
    "stage",
}


def bindings(profile, values):
    """Reject mixed target identities and secret values before rendering hosting."""
    target = identities(profile)
    require(isinstance(values, dict) and set(values) == FIELDS, "Exact hosting bindings required")
    account, region = target["account"], target["region"]
    secret_root = (
        rf"arn:aws:secretsmanager:{re.escape(region)}:{account}:secret:"
        rf"{re.escape(target['secret_prefix'])}/"
    )
    patterns = {
        "database_secret": secret_root + r"database/app-[A-Za-z0-9]{6}",
        "auth_secret": secret_root + r"auth-[A-Za-z0-9]{6}",
        "db_host": (
            re.escape(target["database"])
            + r"\.[a-z0-9]+\."
            + re.escape(region)
            + r"\.rds\.amazonaws\.com"
        ),
        "pool": re.escape(region) + r"_[A-Za-z0-9]{1,64}",
        "client": r"[A-Za-z0-9]{1,128}",
        "image": re.escape(target["registry"] + "/" + target["image_repository"])
        + r"@sha256:[a-f0-9]{64}",
        "stage": r"[a-z][a-z0-9-]{0,31}",
        "environment": r"staging|production",
    }
    for key, pattern in patterns.items():
        require(
            isinstance(values[key], str) and re.fullmatch(pattern, values[key]),
            f"Invalid hosting {key}",
        )
    for key, prefix, minimum in (("subnets", "subnet", 2), ("security_groups", "sg", 1)):
        rows = values[key]
        require(
            isinstance(rows, list)
            and minimum <= len(rows) <= (16 if key == "subnets" else 5)
            and all(
                isinstance(row, str) and re.fullmatch(prefix + r"-[a-f0-9]{17}", row)
                for row in rows
            )
            and len(set(rows)) == len(rows),
            f"Invalid hosting {key}",
        )
    return target


def runtime_access(target, values):
    """Limit runtime secrets/logging and prevent application use of Lambda ENI privileges."""
    account, region, function = (target[k] for k in ("account", "region", "runtime_function"))
    eni = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses",
    ]
    return policy(
        [
            {
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": [values["database_secret"], values["auth_secret"]],
                "Condition": {"StringEquals": {"secretsmanager:VersionStage": "AWSCURRENT"}},
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/{function}:*",
            },
            {"Effect": "Allow", "Action": eni, "Resource": "*"},
            {
                "Effect": "Deny",
                "Action": eni + ["ec2:DetachNetworkInterface"],
                "Resource": "*",
                "Condition": {
                    "ArnEquals": {
                        "lambda:SourceFunctionArn": (
                            f"arn:aws:lambda:{region}:{account}:function:{function}"
                        )
                    }
                },
            },
        ]
    )


def prepare(profile, values, *, frontend_prefix, edge_arn):
    """Render portable hosting while retaining shared cache, cookie and gateway protections."""
    target = bindings(profile, values)
    access = runtime_access(target, values)
    deployment = {
        **values,
        "account": target["account"],
        "region": target["region"],
        "prefix": target["resource_prefix"],
        "function": target["runtime_function"],
        "alias": target["runtime_alias"],
        "environment_tag": target["environment_tag"],
        "policy": access,
    }
    template = app_template(frontend_prefix, edge_arn, deployment=deployment)
    template["Description"] = "Portable staff hosting; no database bootstrap or migration"
    template["Rules"] = template_rules(profile)
    template["Metadata"] = {"FitfinityProfile": target["profile_sha256"]}
    resources = template["Resources"]
    resources["RuntimeBoundary"] = resource(
        "IAM::ManagedPolicy",
        {
            "ManagedPolicyName": target["resource_prefix"] + "-hosting-api-boundary",
            "PolicyDocument": access,
        },
    )
    resources["ApiRole"]["Properties"]["PermissionsBoundary"] = {"Ref": "RuntimeBoundary"}
    resources["ApiRole"]["Properties"]["Policies"][0]["PolicyName"] = "StaffRuntime"
    resources["Distribution"]["Properties"]["DistributionConfig"]["Comment"] = (
        "Fitfinity staff portal " + frontend_prefix.split("/")[1]
    )
    resources["Distribution"]["Properties"]["Tags"] = [
        {"Key": "Application", "Value": "Fitfinity"},
        {"Key": "Environment", "Value": target["environment_tag"]},
    ]
    resources["ApiErrors"]["Properties"]["AlarmDescription"] = (
        "Staff API errors; notification destinations require separate configuration"
    )
    # Lambda versions capture configuration as well as code.
    version_input = json.dumps(
        {"runtime": resources["ApiFunction"]["Properties"], "frontend": frontend_prefix},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    version = "ApiVersion" + hashlib.sha256(version_input).hexdigest()[:16]
    resources[version] = resources.pop("ApiVersion")
    resources[version].update(DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    resources["ApiAlias"]["Properties"]["FunctionVersion"] = attr(version, "Version")
    template["Outputs"]["FunctionVersion"]["Value"] = attr(version, "Version")
    return template


def edge(profile):
    """Render the target edge ACL for CloudFront's required us-east-1 control plane."""
    target = identities(profile)
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Staff CloudFront WAF; deploy in us-east-1",
        "Rules": template_rules(profile, edge=True),
        "Metadata": {"FitfinityProfile": target["profile_sha256"]},
        "Resources": {"EdgeAcl": waf("CLOUDFRONT", target["resource_prefix"] + "-login")},
        "Outputs": {"WebAclArn": {"Value": attr("EdgeAcl", "Arn")}},
    }
