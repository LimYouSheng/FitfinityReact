"""Prepare bounded probe IAM resources offline; never apply changes or enable workflows."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from operator_checks import require
from release_image import ACCOUNT, REGION
from schema_probe_iam import BOUNDARY, NAME, RUNTIME_ROLE, runtime_policy

OPERATOR_ROLE = "fitfinity-test-github-schema-probe"


def policy(statements):
    """Build a versioned IAM policy from explicit statements."""
    return {"Version": "2012-10-17", "Statement": statements}


def allow(actions, resources, **extra):
    """Construct one scoped allow statement."""
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def prepare(secret_arn):
    """Return a review-only setup template for the exact developer account and secret."""
    require(
        isinstance(secret_arn, str)
        and re.fullmatch(
            rf"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:fitfinity/test/database/migration-[A-Za-z0-9]{{6}}",
            secret_arn,
        ),
        "Exact developer migration secret metadata required",
    )
    function = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{NAME}"
    runtime = f"arn:aws:iam::{ACCOUNT}:role/{RUNTIME_ROLE}"
    logs = f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/lambda/{NAME}"
    operator_policy = policy(
        [
            allow("sts:GetCallerIdentity", "*"),
            allow(["lambda:GetAccountSettings", "lambda:ListEventSourceMappings"], "*"),
            allow(["ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "*"),
            allow(
                "rds:DescribeDBInstances", f"arn:aws:rds:{REGION}:{ACCOUNT}:db:fitfinity-test-db"
            ),
            allow("secretsmanager:DescribeSecret", secret_arn),
            allow(
                [
                    "ecr:DescribeImageScanFindings",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetRepositoryPolicy",
                ],
                f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/fitfinity-test-api",
            ),
            allow(
                [
                    "cloudformation:CreateStack",
                    "cloudformation:DescribeStacks",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStackResource",
                    "cloudformation:DescribeStackResources",
                    "cloudformation:ListStackResources",
                    "cloudformation:GetTemplate",
                    "cloudformation:DeleteStack",
                ],
                f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{NAME}/*",
            ),
            allow(
                [
                    "lambda:CreateFunction",
                    "lambda:DeleteFunction",
                    "lambda:GetFunction",
                    "lambda:GetFunctionConfiguration",
                    "lambda:GetFunctionConcurrency",
                    "lambda:PutFunctionConcurrency",
                    "lambda:DeleteFunctionConcurrency",
                    "lambda:GetPolicy",
                    "lambda:ListFunctionUrlConfigs",
                    "lambda:InvokeFunction",
                    "lambda:TagResource",
                    "lambda:UntagResource",
                    "lambda:ListTags",
                ],
                function,
            ),
            allow(
                "iam:CreateRole",
                runtime,
                Condition={"StringEquals": {"iam:PermissionsBoundary": BOUNDARY}},
            ),
            allow(
                [
                    "iam:GetRole",
                    "iam:DeleteRole",
                    "iam:PutRolePolicy",
                    "iam:GetRolePolicy",
                    "iam:DeleteRolePolicy",
                    "iam:ListRolePolicies",
                    "iam:ListAttachedRolePolicies",
                    "iam:TagRole",
                    "iam:UntagRole",
                ],
                runtime,
            ),
            allow(
                "iam:PassRole",
                runtime,
                Condition={"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}},
            ),
            allow(
                [
                    "logs:CreateLogGroup",
                    "logs:DeleteLogGroup",
                    "logs:PutRetentionPolicy",
                    "logs:TagResource",
                    "logs:UntagResource",
                    "logs:ListTagsForResource",
                ],
                [logs, logs + ":*"],
            ),
            allow("logs:DescribeLogGroups", "*"),
        ]
    )
    trust = policy(
        [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Principal": {
                    "Federated": (
                        f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
                    )
                },
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": (
                            "repo:LimYouSheng/FitfinityReact:environment:aws-test"
                        ),
                    }
                },
            }
        ]
    )
    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Fitfinity probe operator and runtime permissions boundary",
        "Resources": {
            "RuntimeBoundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": NAME + "-runtime-boundary",
                    "PolicyDocument": runtime_policy(secret_arn),
                },
            },
            "OperatorBoundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": OPERATOR_ROLE + "-boundary",
                    "PolicyDocument": operator_policy,
                },
            },
            "OperatorRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": OPERATOR_ROLE,
                    "MaxSessionDuration": 3600,
                    "PermissionsBoundary": {"Ref": "OperatorBoundary"},
                    "AssumeRolePolicyDocument": trust,
                    "Policies": [
                        {"PolicyName": "ProbeLifecycle", "PolicyDocument": operator_policy}
                    ],
                },
            },
        },
    }
    return {
        "decision": "HOLD",
        "account": ACCOUNT,
        "region": REGION,
        "template": template,
        "required_before_execution": [
            "Verify existing GitHub OIDC provider and aws-test main-only environment protection",
            "Inspect a CREATE-only named-IAM change set; "
            "reject existing resource adoption or unrelated changes",
            "Review exact account/secret and grants; no hosting/image/foundation role changes",
            "Keep AWS_SCHEMA_PROBE_ENABLED disabled until "
            "source, image, network and role acceptance",
        ],
    }


def write_bundle(review, output):
    """Package the reviewed template and tested standalone CloudShell installer."""
    template = review["template"]
    data = json.dumps(template, sort_keys=True, separators=(",", ":")).encode()
    review = {**review, "template_sha256": hashlib.sha256(data).hexdigest()}
    output.mkdir(parents=True, exist_ok=False)
    (output / "template.json").write_bytes(data)
    (output / "review.json").write_text(json.dumps(review, indent=2))
    operator = Path(__file__).with_name("schema_probe_setup_operator.py").read_text()
    entry = (
        "\n\nfrom pathlib import Path\n\nTEMPLATE = json.loads(" + repr(data.decode()) + ")\n"
        "TEMPLATE_SHA256 = " + repr(review["template_sha256"]) + "\n"
        "\nif __name__ == '__main__':\n"
        "    require(hashlib.sha256(json.dumps(TEMPLATE, sort_keys=True, s"
        "eparators=(',', ':')).encode()).hexdigest() == TEMPLATE_SHA256, '"
        "Installer template changed')\n"
        "    print('Creating only the dedicated probe IAM role and two bou"
        "ndaries. No application deployment.')\n"
        "    try:\n"
        "        result = install(TEMPLATE, Path.cwd() / 'fitfinity-probe-iam-setup', aws)\n"
        "        print(json.dumps(result, indent=2))\n"
        "        print('IAM setup verified. Probe workflow remains disable"
        "d until separately configured.')\n"
        "    except Exception as error:\n"
        "        raise SystemExit(str(error) + '\\nDo not rerun. Inspect fi"
        "tfinity-probe-iam-setup/receipt.json and stack events first.') fr"
        "om None\n"
    )
    installer = operator + entry
    compile(installer, "fitfinity-install-probe-iam.py", "exec")
    (output / "fitfinity-install-probe-iam.py").write_text(installer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration-secret-arn", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = prepare(args.migration_secret_arn)
    write_bundle(review, args.output)
    print("IAM setup prepared locally; HOLD. No AWS calls or workflow activation.")
