"""Prepare resource-bound routine-release policies without installing IAM changes."""

import re
from copy import deepcopy

from deployment_profile import identities
from operator_checks import require
from portable_services import policy, trust
from release_features import boundary_arn


def service_role_arn(profile):
    """Identify the retained CloudFormation role for the selected hosting stack."""
    target = identities(profile)
    return (
        f"arn:aws:iam::{target['account']}:role/{target['resource_prefix']}-hosting-cloudformation"
    )


def prepare(profile, stack, resource_inventory, *, boundary_stack=None, boundary_resources=None):
    """Generate operator and service-role policy replacements from owned resource metadata."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    stack_prefix = f"arn:aws:cloudformation:{region}:{account}:stack/{target['hosting_stack']}/"
    require(
        stack.get("StackName") == target["hosting_stack"]
        and re.fullmatch(re.escape(stack_prefix) + r"[a-f0-9-]+", stack.get("StackId", ""))
        and stack.get("StackStatus")
        in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}
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
    boundary_policy = boundary_arn(profile)
    role_arn = f"arn:aws:iam::{account}:role/{target['resource_prefix']}-hosting-api"
    require(
        (boundary_stack is None) == (boundary_resources is None),
        "Supply both external owner stack and inventory",
    )
    boundary_owner = None
    owner_rows = rows
    if boundary_stack is not None:
        owner_prefix = f"arn:aws:cloudformation:{region}:{account}:stack/"
        owner_name = boundary_stack.get("StackName")
        require(
            isinstance(owner_name, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,127}", owner_name)
            and owner_name != target["hosting_stack"]
            and re.fullmatch(
                re.escape(owner_prefix + owner_name + "/") + r"[a-f0-9-]+",
                boundary_stack.get("StackId", ""),
            )
            and boundary_stack.get("StackStatus")
            in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"}
            and not boundary_stack.get("ParentId")
            and not boundary_stack.get("RootId")
            and not any(row.get("PhysicalResourceId") == boundary_policy for row in rows),
            "Distinct stable external boundary owner required",
        )
        owner_rows = boundary_resources.get("StackResourceSummaries", [])
        require(
            owner_rows
            and not boundary_resources.get("NextToken")
            and len({row.get("LogicalResourceId") for row in owner_rows}) == len(owner_rows),
            "Complete external owner resource inventory required",
        )
    matches = [row for row in owner_rows if row.get("PhysicalResourceId") == boundary_policy]
    if matches or boundary_stack:
        require(
            len(matches) == 1
            and matches[0].get("ResourceType") == "AWS::IAM::ManagedPolicy"
            and re.fullmatch(
                r"[A-Za-z][A-Za-z0-9]{0,254}", matches[0].get("LogicalResourceId", "")
            ),
            "Exact managed policy in its owning stack required",
        )
        boundary_owner = {
            "stack_arn": (boundary_stack or stack)["StackId"],
            "logical_id": matches[0]["LogicalResourceId"],
        }
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
    role_reads = [
        "iam:GetRole",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:GetRolePolicy",
    ]
    policy_reads = ["iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListEntitiesForPolicy"]
    change_names = {"cloudformation:ChangeSetName": ["release-*", changes]}

    def allow(actions, resource, **extra):
        return {"Effect": "Allow", "Action": actions, "Resource": resource, **extra}

    operator = policy(
        [
            allow(["sts:GetCallerIdentity"], "*"),
            # The release-observation workflow also uses this role with a read-only session.
            allow(
                ["rds:DescribeDBInstances"],
                f"arn:aws:rds:{region}:{account}:db:{target['database']}",
            ),
            allow(
                [
                    "cloudformation:DescribeStacks",
                    "cloudformation:DescribeStackResource",
                    "cloudformation:ListStackResources",
                    "cloudformation:GetTemplate",
                    "cloudformation:DescribeChangeSet",
                ],
                stack["StackId"],
            ),
            allow(
                ["cloudformation:ExecuteChangeSet"],
                stack["StackId"],
                Condition={"StringLike": change_names},
            ),
            allow(
                ["cloudformation:CreateChangeSet"],
                stack["StackId"],
                Condition={
                    "StringEquals": {"cloudformation:RoleArn": service_role_arn(profile)},
                    "StringLike": change_names,
                },
            ),
            allow(
                ["iam:PassRole"],
                service_role_arn(profile),
                Condition={"StringEquals": {"iam:PassedToService": "cloudformation.amazonaws.com"}},
            ),
            allow(role_reads, role_arn),
            allow(policy_reads, boundary_policy),
            allow(
                ["lambda:GetFunction", "lambda:GetFunctionConcurrency", "lambda:GetAlias"],
                [function, function + ":*"],
            ),
            # GetFunction returns the maintenance/snapshot tags only with ListTags.
            allow(["lambda:ListTags"], function),
            allow(
                ["cloudfront:GetDistribution"],
                f"arn:aws:cloudfront::{account}:distribution/{distribution}",
            ),
            allow(
                ["lambda:UntagResource"],
                function,
                Condition={
                    "ForAllValues:StringEquals": {
                        "aws:TagKeys": ["FitfinityMaintenance", "FitfinitySnapshot"]
                    },
                    "Null": {"aws:TagKeys": "false"},
                },
            ),
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
    if boundary_stack:
        operator["Statement"].append(
            allow(
                [
                    "cloudformation:DescribeStacks",
                    "cloudformation:DescribeStackResource",
                    "cloudformation:GetTemplate",
                ],
                boundary_owner["stack_arn"],
            )
        )
    service = policy(
        [
            allow(
                ["ec2:DescribeSecurityGroups", "ec2:DescribeSubnets", "ec2:DescribeVpcs"],
                "*",
                Condition={"StringEquals": {"aws:RequestedRegion": target["region"]}},
            ),
            allow(
                [
                    "lambda:GetFunction",
                    "lambda:GetFunctionConfiguration",
                    "lambda:GetFunctionConcurrency",
                    "lambda:GetFunctionCodeSigningConfig",
                    "lambda:GetFunctionRecursionConfig",
                    "lambda:GetFunctionScalingConfig",
                    "lambda:GetProvisionedConcurrencyConfig",
                    "lambda:GetRuntimeManagementConfig",
                    "lambda:GetAlias",
                    "lambda:ListVersionsByFunction",
                    "lambda:ListTags",
                ],
                [function, function + ":*"],
            ),
            allow(
                [
                    "lambda:UpdateFunctionCode",
                    "lambda:UpdateFunctionConfiguration",
                    "lambda:PublishVersion",
                    "lambda:PutFunctionConcurrency",
                ],
                function,
            ),
            allow(
                ["iam:PassRole"],
                f"arn:aws:iam::{account}:role/{target['resource_prefix']}-hosting-api",
                Condition={"StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}},
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
    # AWS::IAM::ManagedPolicy versions its document in place. The handler may remove a
    # nondefault version; the existing boundary and its consumers must be retained.
    managed_update = allow(
        [
            *policy_reads,
            "iam:ListPolicyVersions",
            "iam:CreatePolicyVersion",
            "iam:DeletePolicyVersion",
        ],
        boundary_policy,
    )
    if boundary_owner:
        service["Statement"].append(allow([*role_reads, "iam:PutRolePolicy"], role_arn))
        if boundary_stack is None:
            service["Statement"].append(managed_update)
    return {
        "decision": "HOLD",
        "profile_sha256": target["profile_sha256"],
        "stack_arn": stack["StackId"],
        "frontend_bucket": bucket,
        "distribution_id": distribution,
        "runtime_boundary_owner": boundary_owner,
        "external_owner_handler_policy": policy([managed_update]) if boundary_stack else None,
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
            "source review gates control pause/resumption. Feature-update grants require an "
            "observed boundary owner. The external owner keeps managed-policy updates. "
            "Confirm regional handlers and installed permissions before activation."
        ),
    }


def reconcile_owner(profile, stack, resource_inventory, owner_template, owner_sha256, **boundary):
    """Prepare policy changes in the existing IAM owner without replacing its roles."""
    from release_observation import digest

    require(digest(owner_template) == owner_sha256, "IAM owner template hash differs")
    review = prepare(profile, stack, resource_inventory, **boundary)
    target = identities(profile)
    candidate = deepcopy(owner_template)
    resources = candidate.get("Resources", {})
    changed = []
    for logical, kind, boundary in (
        ("HostingRole", "operator", "ReleaseOperatorBoundary"),
        ("CloudFormationRole", "service", "ReleaseServiceBoundary"),
    ):
        row = resources.get(logical, {})
        props = row.get("Properties", {})
        expected_trust = deepcopy(review[kind + "_trust"])
        if kind == "operator" and "github_owner_id" not in target:
            statements = props.get("AssumeRolePolicyDocument", {}).get("Statement", [])
            if len(statements) == 1:
                conditions = statements[0].get("Condition", {}).get("StringEquals", {})
                subject = conditions.get("token.actions.githubusercontent.com:sub", "")
                owner, repository = target["github_repository"].split("/")
                environment = target["oidc_subject"].split(":environment:", 1)[1]
                if isinstance(subject, str) and re.fullmatch(
                    "repo:"
                    + re.escape(owner)
                    + r"@[1-9][0-9]*/"
                    + re.escape(repository)
                    + r"@[1-9][0-9]*:environment:"
                    + re.escape(environment),
                    subject,
                ):
                    expected_trust["Statement"][0]["Condition"]["StringEquals"][
                        "token.actions.githubusercontent.com:sub"
                    ] = subject
        require(
            row.get("Type") == "AWS::IAM::Role"
            and props.get("RoleName") == review[kind + "_role"].split("/")[-1]
            and props.get("AssumeRolePolicyDocument") == expected_trust
            and not props.get("ManagedPolicyArns")
            and props.get("Path", "/") == "/",
            "Existing release role identity, trust or attachments require reconciliation",
        )
        policies = props.get("Policies", [])
        require(
            len(policies) == 1
            and isinstance(policies[0].get("PolicyName"), str)
            and bool(policies[0]["PolicyName"])
            and isinstance(policies[0].get("PolicyDocument"), dict),
            "Single existing inline policy owner required",
        )
        expected_name = target["resource_prefix"] + "-release-" + kind + "-boundary"
        if props.get("PermissionsBoundary") is not None:
            require(
                props["PermissionsBoundary"] == {"Ref": boundary}
                and resources.get(boundary, {}).get("Type") == "AWS::IAM::ManagedPolicy"
                and resources[boundary].get("Properties", {}).get("ManagedPolicyName")
                == expected_name
                and set(resources[boundary]["Properties"])
                == {"ManagedPolicyName", "PolicyDocument"},
                "Existing boundary has another owner or attachments",
            )
        else:
            require(boundary not in resources, "New boundary logical ID already exists")
        policies[0]["PolicyDocument"] = deepcopy(review[kind + "_policy"])
        props["PermissionsBoundary"] = {"Ref": boundary}
        if boundary not in resources:
            resources[boundary] = {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {"ManagedPolicyName": expected_name},
            }
        resources[boundary]["Properties"]["PolicyDocument"] = deepcopy(review[kind + "_boundary"])
        changed.extend([logical, boundary])
    return {
        "decision": "HOLD",
        "profile_sha256": target["profile_sha256"],
        "original_template_sha256": owner_sha256,
        "candidate_template_sha256": digest(candidate),
        "candidate_template": candidate,
        "reviewed_resources": changed,
        "limits": (
            "Template preparation only. Verify actual owner stack, role drift and boundary-name "
            "availability before a separately reviewed change set. Preserve existing role IDs. "
            "Verify retained OIDC numeric identities and emitted subject "
            "against GitHub configuration. "
            "Provider-handler permissions and rollback authority require validation."
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
    parser.add_argument("--owner-template", type=Path)
    parser.add_argument("--owner-sha256")
    parser.add_argument("--boundary-stack", type=Path)
    parser.add_argument("--boundary-resources", type=Path)
    args = parser.parse_args()
    require(
        bool(args.owner_template) == bool(args.owner_sha256),
        "Owner file and hash required together",
    )
    stack = json.loads(args.stack.read_text())
    inventory = json.loads(args.resources.read_text())
    require(
        bool(args.boundary_stack) == bool(args.boundary_resources),
        "External owner files required together",
    )
    external = {}
    if args.boundary_stack:
        external = {
            "boundary_stack": json.loads(args.boundary_stack.read_text()),
            "boundary_resources": json.loads(args.boundary_resources.read_text()),
        }
    result = prepare(load(args.profile), stack, inventory, **external)
    package = {
        "review_sha256": digest(result),
        "observations_sha256": digest({"stack": stack, "resources": inventory, **external}),
        "review": result,
    }
    if args.owner_template:
        package["owner_plan"] = reconcile_owner(
            load(args.profile),
            stack,
            inventory,
            json.loads(args.owner_template.read_text()),
            args.owner_sha256,
            **external,
        )
    with args.output.open("x") as stream:
        stream.write(json.dumps(package, indent=2) + "\n")
    print("Release policy package prepared; deployment HOLD. No AWS changes made.")


if __name__ == "__main__":
    main()
