"""Prepare bounded probe IAM resources offline; never apply changes or enable workflows."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from deployment_profile import DEVELOPER, identities, load, template_rules
from operator_checks import require
from schema_probe_iam import runtime_policy

ACCOUNT, REGION = DEVELOPER["account"], DEVELOPER["region"]

OPERATOR_ROLE = identities(DEVELOPER)["operator_role"]


def policy(statements):
    """Build a versioned IAM policy from explicit statements."""
    return {"Version": "2012-10-17", "Statement": statements}


def allow(actions, resources, **extra):
    """Construct one scoped allow statement."""
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def prepare(secret_arn, *, profile=DEVELOPER, purpose="probe"):
    """Return scoped IAM resources for one validated deployment profile."""
    require(purpose in {"probe", "upgrade"}, "Unknown private job purpose")
    target = identities(profile)
    account, region = target["account"], target["region"]
    if purpose == "probe":
        name, runtime_role = target["probe_name"], target["runtime_role"]
        operator_role, boundary = target["operator_role"], target["runtime_boundary"]
    else:
        name, runtime_role = target["upgrade_name"], target["upgrade_runtime_role"]
        operator_role, boundary = target["upgrade_operator_role"], target["upgrade_boundary"]
    secret_prefix = re.escape(target["secret_prefix"])
    require(
        isinstance(secret_arn, str)
        and re.fullmatch(
            rf"arn:aws:secretsmanager:{region}:{account}:secret:{secret_prefix}/database/migration-[A-Za-z0-9]{{6}}",
            secret_arn,
        ),
        "Exact target migration secret metadata required",
    )
    function = f"arn:aws:lambda:{region}:{account}:function:{name}"
    runtime = f"arn:aws:iam::{account}:role/{runtime_role}"
    logs = f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/{name}"
    operator_policy = policy(
        [
            allow("sts:GetCallerIdentity", "*"),
            allow(["lambda:GetAccountSettings", "lambda:ListEventSourceMappings"], "*"),
            allow(["ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "*"),
            allow(
                "rds:DescribeDBInstances", f"arn:aws:rds:{region}:{account}:db:{target['database']}"
            ),
            allow("secretsmanager:DescribeSecret", secret_arn),
            allow(
                [
                    "ecr:DescribeImageScanFindings",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetRepositoryPolicy",
                ],
                f"arn:aws:ecr:{region}:{account}:repository/{target['image_repository']}",
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
                f"arn:aws:cloudformation:{region}:{account}:stack/{name}/*",
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
                Condition={"StringEquals": {"iam:PermissionsBoundary": boundary}},
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
                        f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"
                    )
                },
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": (target["oidc_subject"]),
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
                    "ManagedPolicyName": name + "-runtime-boundary",
                    "PolicyDocument": runtime_policy(secret_arn, profile=profile, purpose=purpose),
                },
            },
            "OperatorBoundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": operator_role + "-boundary",
                    "PolicyDocument": operator_policy,
                },
            },
            "OperatorRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": operator_role,
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
    if purpose == "upgrade":
        template["Description"] = "Private upgrade operator and separate runtime permission ceiling"
        template["Rules"] = template_rules(profile)
        template["Resources"]["OperatorRole"]["Properties"]["Policies"][0]["PolicyName"] = (
            "UpgradeLifecycle"
        )
    return {
        "decision": "HOLD",
        "profile": dict(profile),
        "profile_sha256": target["profile_sha256"],
        "account": account,
        "region": region,
        "template": template,
        "required_before_execution": [
            "Verify existing GitHub OIDC provider and "
            "the selected main-only environment protection",
            "Inspect a CREATE-only named-IAM change set; "
            "reject existing resource adoption or unrelated changes",
            "Review exact account/secret and grants; no hosting/image/foundation role changes",
            (
                "Keep AWS_SCHEMA_PROBE_ENABLED disabled until "
                "source, image, network and role acceptance"
                if purpose == "probe"
                else "Upgrade IAM is preparation only; require maintenance, backup "
                "and a reviewed executor"
            ),
        ],
    }


def write_bundle(review, output):
    """Package the reviewed template and tested standalone CloudShell installer."""
    target = identities(review["profile"])
    require(review["profile_sha256"] == target["profile_sha256"], "Profile fingerprint differs")
    template = review["template"]
    secret = template["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"]["Statement"][
        0
    ]["Resource"]
    require(
        template == prepare(secret, profile=review["profile"])["template"],
        "Template differs from selected profile",
    )
    data = json.dumps(template, sort_keys=True, separators=(",", ":")).encode()
    review = {**review, "template_sha256": hashlib.sha256(data).hexdigest()}
    output.mkdir(parents=True, exist_ok=False)
    (output / "template.json").write_bytes(data)
    (output / "review.json").write_text(json.dumps(review, indent=2))
    operator = Path(__file__).with_name("schema_probe_setup_operator.py").read_text()
    target_import = "from deployment_profile import DEVELOPER, identities"
    target_assignment = "TARGET = identities(DEVELOPER)"
    require(
        operator.count(target_import) == 1 and operator.count(target_assignment) == 1,
        "Installer target binding changed",
    )
    operator = operator.replace(target_import, "").replace(
        target_assignment, "TARGET = json.loads(" + repr(json.dumps(target, sort_keys=True)) + ")"
    )
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
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--migration-secret-arn", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = prepare(args.migration_secret_arn, profile=load(args.profile))
    write_bundle(review, args.output)
    print("IAM setup prepared locally; HOLD. No AWS calls or workflow activation.")
