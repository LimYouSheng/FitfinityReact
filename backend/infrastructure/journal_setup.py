"""Prepare target-bound journal storage and narrowly scoped operator IAM updates."""

from copy import deepcopy

from deployment_journal import access, bucket_name, template
from deployment_profile import identities, template_rules
from operator_checks import require


def operator_access(profile):
    """Permit child operators to append receipts without changing release pointers."""
    return {
        "Sid": "DeploymentJournalWrite",
        "Effect": "Allow",
        "Action": "s3:PutObject",
        "Resource": f"arn:aws:s3:::{bucket_name(profile)}/runs/*",
    }


def coordinator_template(profile):
    """Render private journal storage and its separate non-deployment coordinator role."""
    target = identities(profile)
    document = template(profile)
    document["Rules"] = template_rules(profile)
    role_name = target["resource_prefix"] + "-github-journal"
    provider = f"arn:aws:iam::{target['account']}:oidc-provider/token.actions.githubusercontent.com"
    trust_condition = {
        "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": target["oidc_subject"],
        }
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            access(profile, write=True),
            {
                "Effect": "Allow",
                "Action": "s3:ListBucket",
                "Resource": f"arn:aws:s3:::{bucket_name(profile)}",
            },
            {
                "Effect": "Allow",
                "Action": "cloudformation:GetTemplate",
                "Resource": f"arn:aws:cloudformation:{target['region']}:{target['account']}:"
                f"stack/{target['hosting_stack']}/*",
                "Condition": {"StringEquals": {"aws:RequestedRegion": target["region"]}},
            },
            {
                "Effect": "Allow",
                "Action": "cloudformation:DescribeStacks",
                "Resource": [
                    f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/{name}/*"
                    for name in (target["probe_name"], target["upgrade_name"])
                ],
                "Condition": {"StringEquals": {"aws:RequestedRegion": target["region"]}},
            },
        ],
    }
    document["Resources"].update(
        {
            "CoordinatorBoundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": role_name + "-boundary",
                    "PolicyDocument": policy,
                },
            },
            "CoordinatorRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": role_name,
                    "MaxSessionDuration": 3600,
                    "PermissionsBoundary": {"Ref": "CoordinatorBoundary"},
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "sts:AssumeRoleWithWebIdentity",
                                "Principal": {"Federated": provider},
                                "Condition": trust_condition,
                            }
                        ],
                    },
                    "Policies": [
                        {"PolicyName": "DeploymentJournal", "PolicyDocument": deepcopy(policy)}
                    ],
                },
            },
        }
    )
    document["Outputs"] = {
        "JournalBucket": {"Value": {"Ref": "Journal"}},
        "JournalRoleArn": {"Value": {"Fn::GetAtt": ["CoordinatorRole", "Arn"]}},
    }
    return document


def operator_owner(profile, purpose):
    """Identify the existing CloudFormation owner for each receipt-writing operator."""
    target = identities(profile)
    owners = {
        "maintenance": (
            target["resource_prefix"] + "-maintenance-access",
            "MaintenanceRole",
            "MaintenanceBoundary",
            target["maintenance_role"],
        ),
        "probe": (
            target["setup_stack"],
            "OperatorRole",
            "OperatorBoundary",
            target["operator_role"],
        ),
        "upgrade": (
            target["upgrade_setup_stack"],
            "OperatorRole",
            "OperatorBoundary",
            target["upgrade_operator_role"],
        ),
        "hosting": (
            target["resource_prefix"] + "-github-hosting",
            "HostingRole",
            "ReleaseOperatorBoundary",
            target["hosting_role"],
        ),
    }
    require(purpose in owners, "Unknown journal operator")
    return owners[purpose]


def augment_operator(installed, profile, purpose):
    """Extend only the owning role policy and boundary without changing trust or identity."""
    _, role_id, boundary_id, role_name = operator_owner(profile, purpose)
    candidate = deepcopy(installed)
    resources = candidate.get("Resources", {})
    role = resources.get(role_id, {})
    boundary = resources.get(boundary_id, {})
    props = role.get("Properties", {})
    require(
        role.get("Type") == "AWS::IAM::Role"
        and props.get("RoleName") == role_name
        and props.get("PermissionsBoundary") == {"Ref": boundary_id}
        and boundary.get("Type") == "AWS::IAM::ManagedPolicy",
        "Installed journal operator owner differs",
    )
    policies = props.get("Policies", [])
    require(len(policies) == 1, "Review the actual operator policy inventory")
    grant = operator_access(profile)
    for document in (policies[0]["PolicyDocument"], boundary["Properties"]["PolicyDocument"]):
        statements = document.get("Statement")
        require(isinstance(statements, list), "Explicit policy statements required")
        existing = [row for row in statements if row.get("Sid") == grant["Sid"]]
        require(not existing or existing == [grant], "Installed journal grant differs")
        if not existing:
            statements.append(deepcopy(grant))
    return candidate
