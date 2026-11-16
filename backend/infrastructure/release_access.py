"""Prepare resource-bound routine-release policies without installing IAM changes."""

import re
from copy import deepcopy

from deployment_profile import identities
from operator_checks import require
from portable_services import policy, trust


def service_role_arn(profile):
    """Identify the retained CloudFormation role for the selected hosting stack."""
    target = identities(profile)
    return (
        f"arn:aws:iam::{target['account']}:role/{target['resource_prefix']}-hosting-cloudformation"
    )


def prepare(profile, stack, resource_inventory):
    """Generate operator and service-role policy replacements from owned resource metadata."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    stack_prefix = f"arn:aws:cloudformation:{region}:{account}:stack/{target['hosting_stack']}/"
    require(
        stack.get("StackName") == target["hosting_stack"]
        and re.fullmatch(re.escape(stack_prefix) + r"[a-f0-9-]+", stack.get("StackId", ""))
        and stack.get("StackStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
        and stack.get("RoleARN") == service_role_arn(profile)
        and not stack.get("ParentId")
        and not stack.get("RootId"),
        "Stable owned stack and retained service role required",
    )
    rows = resource_inventory.get("StackResourceSummaries", [])
    resources = {row.get("LogicalResourceId"): row for row in rows}
    require(
        rows and len(resources) == len(rows) and not resource_inventory.get("NextToken"),
        "Complete unique resource inventory required",
    )
    for logical, kind, physical in (
        ("ApiFunction", "AWS::Lambda::Function", target["runtime_function"]),
        ("ApiRole", "AWS::IAM::Role", target["resource_prefix"] + "-hosting-api"),
        ("FrontendBucket", "AWS::S3::Bucket", None),
        ("Distribution", "AWS::CloudFront::Distribution", None),
    ):
        row = resources.get(logical, {})
        require(
            row.get("ResourceType") == kind
            and (physical is None or row.get("PhysicalResourceId") == physical),
            "Hosting resource identity differs",
        )
    bucket = resources["FrontendBucket"].get("PhysicalResourceId", "")
    distribution = resources["Distribution"].get("PhysicalResourceId", "")
    require(
        re.fullmatch(
            re.escape(target["hosting_stack"] + "-frontendbucket-") + r"[a-z0-9-]+", bucket
        )
        and len(bucket) <= 63,
        "Exact retained frontend bucket required",
    )
    require(re.fullmatch(r"[A-Z0-9]{1,32}", distribution), "Exact distribution ID required")
    function = f"arn:aws:lambda:{region}:{account}:function:{target['runtime_function']}"
    repository = f"arn:aws:ecr:{region}:{account}:repository/{target['image_repository']}"
    changes = f"arn:aws:cloudformation:{region}:{account}:changeSet/release-*/*"
    objects = f"arn:aws:s3:::{bucket}/releases/*"

    def allow(actions, resource, **extra):
        return {"Effect": "Allow", "Action": actions, "Resource": resource, **extra}

    operator = policy(
        [
            allow(["sts:GetCallerIdentity"], "*"),
            allow(
                [
                    "cloudformation:DescribeStacks",
                    "cloudformation:DescribeStackResource",
                    "cloudformation:ListStackResources",
                    "cloudformation:GetTemplate",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:ExecuteChangeSet",
                ],
                [stack["StackId"], changes],
            ),
            allow(
                ["cloudformation:CreateChangeSet"],
                [stack["StackId"], changes],
                Condition={"StringEquals": {"cloudformation:RoleArn": service_role_arn(profile)}},
            ),
            allow(
                ["iam:PassRole"],
                service_role_arn(profile),
                Condition={"StringEquals": {"iam:PassedToService": "cloudformation.amazonaws.com"}},
            ),
            allow(
                ["iam:GetRole"],
                f"arn:aws:iam::{account}:role/{target['resource_prefix']}-hosting-api",
            ),
            allow(
                ["iam:ListEntitiesForPolicy"],
                f"arn:aws:iam::{account}:policy/{target['resource_prefix']}-hosting-api-boundary",
            ),
            allow(["lambda:GetFunction", "lambda:GetFunctionConcurrency"], function),
            allow(["ecr:DescribeImageScanFindings"], repository),
            allow(["s3:GetObject"], objects),
            # HeadObject needs ListBucket to distinguish absence (404) from denial (403).
            allow(["s3:ListBucket"], f"arn:aws:s3:::{bucket}"),
            allow(
                ["s3:PutObject"],
                objects,
                Condition={
                    "StringEquals": {
                        "s3:x-amz-server-side-encryption": "AES256",
                        "s3:if-none-match": "*",
                    }
                },
            ),
        ]
    )
    service = policy(
        [
            allow(
                [
                    "lambda:GetFunction",
                    "lambda:GetFunctionConfiguration",
                    "lambda:GetFunctionConcurrency",
                    "lambda:GetAlias",
                    "lambda:ListVersionsByFunction",
                    "lambda:ListTags",
                ],
                [function, function + ":*"],
            ),
            allow(
                [
                    "lambda:UpdateFunctionCode",
                    "lambda:PublishVersion",
                    "lambda:PutFunctionConcurrency",
                ],
                function,
            ),
            allow(["lambda:UpdateAlias"], function + ":" + target["runtime_alias"]),
            allow(["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], repository),
            allow(
                [
                    "cloudfront:GetDistribution",
                    "cloudfront:GetDistributionConfig",
                    "cloudfront:ListTagsForResource",
                    "cloudfront:UpdateDistribution",
                ],
                f"arn:aws:cloudfront::{account}:distribution/{distribution}",
            ),
        ]
    )
    return {
        "decision": "HOLD",
        "profile_sha256": target["profile_sha256"],
        "stack_arn": stack["StackId"],
        "frontend_bucket": bucket,
        "distribution_id": distribution,
        "operator_role": f"arn:aws:iam::{account}:role/{target['hosting_role']}",
        "service_role": service_role_arn(profile),
        "operator_trust": trust(profile),
        "service_trust": policy(
            [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "cloudformation.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ]
        ),
        "operator_policy": operator,
        "operator_boundary": deepcopy(operator),
        "service_policy": service,
        "service_boundary": deepcopy(service),
        "installation": (
            "Review and update existing IAM owners; do not recreate roles or replay bootstrap"
        ),
        "limits": (
            "Code/assets and recorded concurrency. IAM cannot constrain numeric concurrency; "
            "source review gates control pause/resumption. Feature policies and bootstrap "
            "require separate authority. Validate current CloudFormation handler permissions "
            "and actual IAM boundaries before activation."
        ),
    }


def main():
    """Write a review-only policy package from saved target and resource observations."""
    import argparse
    import json
    from pathlib import Path

    from deployment_profile import load
    from release_observation import digest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--stack", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stack = json.loads(args.stack.read_text())
    inventory = json.loads(args.resources.read_text())
    result = prepare(load(args.profile), stack, inventory)
    package = {
        "review_sha256": digest(result),
        "observations_sha256": digest({"stack": stack, "resources": inventory}),
        "review": result,
    }
    with args.output.open("x") as stream:
        stream.write(json.dumps(package, indent=2) + "\n")
    print("Release policy package prepared; deployment HOLD. No AWS changes made.")


if __name__ == "__main__":
    main()
