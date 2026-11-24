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


def prepare(secret_arn, *, vpc_id, profile=DEVELOPER, purpose="probe"):
    """Return scoped IAM resources for one validated deployment profile."""
    require(purpose in {"probe", "upgrade"}, "Unknown private job purpose")
    target = identities(profile)
    account, region = target["account"], target["region"]
    require(
        isinstance(vpc_id, str) and re.fullmatch(r"vpc-(?:[a-f0-9]{8}|[a-f0-9]{17})", vpc_id),
        "Exact database VPC ID required",
    )
    regional = {"StringEquals": {"aws:RequestedRegion": region}}
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
            allow(["ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "*", Condition=regional),
            allow("ec2:DescribeVpcs", "*", Condition=regional),
            allow(
                "ec2:GetSecurityGroupsForVpc",
                f"arn:aws:ec2:{region}:{account}:vpc/{vpc_id}",
                Condition=regional,
            ),
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
    if purpose == "upgrade":
        operator_policy["Statement"].extend(
            [
                allow(
                    ["cloudformation:DescribeStacks", "cloudformation:GetTemplate"],
                    f"arn:aws:cloudformation:{region}:{account}:stack/{target['hosting_stack']}/*",
                ),
                allow(
                    ["lambda:GetFunction", "lambda:GetFunctionConcurrency", "lambda:ListTags"],
                    f"arn:aws:lambda:{region}:{account}:function:{target['runtime_function']}",
                ),
                allow(
                    "rds:DescribeDBSnapshots",
                    f"arn:aws:rds:{region}:{account}:snapshot:{target['resource_prefix']}-*",
                ),
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
        "vpc_id": vpc_id,
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


def write_bundle(review, output, *, purpose="probe", installed_template=None, stack_id=None):
    """Package a fresh installation or a bounded UPDATE to the original IAM stack."""
    target = identities(review["profile"])
    require(review["profile_sha256"] == target["profile_sha256"], "Profile fingerprint differs")
    template = review["template"]
    secret = template["Resources"]["RuntimeBoundary"]["Properties"]["PolicyDocument"]["Statement"][
        0
    ]["Resource"]
    require(
        template
        == prepare(secret, vpc_id=review["vpc_id"], profile=review["profile"], purpose=purpose)[
            "template"
        ],
        "Template differs from selected profile",
    )
    if purpose == "upgrade":
        target = {
            **target,
            "setup_stack": target["upgrade_setup_stack"],
            "operator_role": target["upgrade_operator_role"],
            "lifecycle_policy": "UpgradeLifecycle",
        }
    data = json.dumps(template, sort_keys=True, separators=(",", ":")).encode()
    review = {**review, "template_sha256": hashlib.sha256(data).hexdigest()}
    require(
        (stack_id is None) == (installed_template is None),
        "Both the installed IAM stack ARN and its original template are required for UPDATE",
    )
    update = None
    if stack_id is not None:
        from schema_probe_setup_operator import validate_update

        validate_update(installed_template, template, stack_id, target)
        update = {
            "stack_id": stack_id,
            "original_sha256": hashlib.sha256(
                json.dumps(installed_template, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        review.update(
            update=update,
            required_before_execution=[
                "Compare the original stack ARN, template, operator trust and effective policies",
                "Review only in-place operator policy and operator boundary modifications",
                "Verify trust, the inline policy and both boundaries before worker creation",
            ],
        )
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
    action = "update" if update else "install"
    directory = f"fitfinity-{purpose}-iam-{'update' if update else 'setup'}"
    entry = f"""

from pathlib import Path

TEMPLATE = json.loads({data.decode()!r})
TEMPLATE_SHA256 = {review["template_sha256"]!r}
UPDATE = {update!r}

if __name__ == '__main__':
    require(template_hash(TEMPLATE) == TEMPLATE_SHA256, 'Installer template changed')
    try:
        result = install(TEMPLATE, Path.cwd() / {directory!r}, aws, update=UPDATE)
        print(json.dumps(result, indent=2))
    except Exception as error:
        next_step = 'Inspect {directory}/receipt.json and stack events before retry.'
        raise SystemExit(str(error) + '\\n' + next_step) from None
"""
    installer = operator + entry
    filename = f"fitfinity-{action}-{purpose}-iam.py"
    compile(installer, filename, "exec")
    (output / filename).write_text(installer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--purpose", choices=["probe", "upgrade"], default="probe")
    parser.add_argument("--migration-secret-arn", required=True)
    parser.add_argument("--vpc-id", required=True, help="VPC ID from the target RDS subnet group")
    parser.add_argument("--installed-template", type=Path, help="Original installed IAM template")
    parser.add_argument("--installed-stack-arn", help="Exact existing access stack ARN for UPDATE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = prepare(
        args.migration_secret_arn,
        vpc_id=args.vpc_id,
        profile=load(args.profile),
        purpose=args.purpose,
    )
    original = json.loads(args.installed_template.read_text()) if args.installed_template else None
    write_bundle(
        review,
        args.output,
        purpose=args.purpose,
        installed_template=original,
        stack_id=args.installed_stack_arn,
    )
    print("IAM setup prepared locally; HOLD. No AWS calls or workflow activation.")
