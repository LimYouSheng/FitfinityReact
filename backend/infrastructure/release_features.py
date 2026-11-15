"""Prepare explicit feature changes while preserving the existing IAM boundary owner."""

from copy import deepcopy

from deployment_profile import identities
from hosting_design import sub
from operator_checks import require
from portable_hosting import bindings, features, runtime_access
from portable_services import media_bucket, policy
from release_observation import digest


def prepare(template, values, *, profile, boundary_template=None, boundary_template_sha256=None):
    """Change only feature environment and matching role/boundary policies in their owners."""
    target = bindings(profile, values)
    require("features" in values, "Explicit reviewed feature flags required")
    resources = template["Resources"]
    function = resources["ApiFunction"]
    role = resources["ApiRole"]
    require(
        function["Type"] == "AWS::Lambda::Function"
        and function["Properties"]["FunctionName"] == target["runtime_function"]
        and function["Properties"]["Role"] == {"Fn::GetAtt": ["ApiRole", "Arn"]}
        and function["Properties"]["Code"]["ImageUri"] == values["image"]
        and role["Type"] == "AWS::IAM::Role"
        and role["Properties"]["RoleName"] == target["resource_prefix"] + "-hosting-api",
        "Existing runtime identity or role binding differs",
    )
    require(
        role["Properties"].get("AssumeRolePolicyDocument")
        == policy(
            [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ]
        ),
        "Runtime role trust requires separate review",
    )
    env = function["Properties"]["Environment"]["Variables"]
    for key, value in {
        "FITFINITY_DATABASE_SECRET_ARN": values["database_secret"],
        "FITFINITY_AUTH_SECRET_ARN": values["auth_secret"],
        "FITFINITY_DB_HOST": values["db_host"],
        "FITFINITY_COGNITO_POOL_ID": values["pool"],
        "FITFINITY_COGNITO_CLIENT_ID": values["client"],
        "FITFINITY_ENVIRONMENT": values["environment"],
    }.items():
        require(env.get(key) == value, "Existing runtime configuration differs")
    previous_flags = {}
    for key, flag in {
        "media": "FITFINITY_MEDIA_ENABLED",
        "invitations": "FITFINITY_STAFF_INVITATIONS_ENABLED",
        "email_changes": "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED",
    }.items():
        value = env.get(flag, "false")
        require(value in {"true", "false"}, "Existing feature state is ambiguous")
        previous_flags[key] = value == "true"
    if previous_flags["media"]:
        require(
            env.get("FITFINITY_MEDIA_BUCKET") == media_bucket(target),
            "Existing media storage must not be silently redirected",
        )
    previous_access = runtime_access(target, {**values, "features": previous_flags})
    policies = role["Properties"].get("Policies", [])
    require(
        len(policies) == 1
        and policies[0].get("PolicyDocument") == previous_access
        and not role["Properties"].get("ManagedPolicyArns"),
        "Existing runtime permissions require separate reconciliation",
    )
    boundary = role["Properties"]["PermissionsBoundary"]
    policy_name = target["resource_prefix"] + "-hosting-api-boundary"
    boundary_resource = None
    external = None
    if isinstance(boundary, dict) and set(boundary) == {"Ref"}:
        require(
            boundary_template is None and boundary_template_sha256 is None,
            "An owned boundary must remain in its current hosting stack",
        )
        boundary_resource = boundary["Ref"]
        require(boundary_resource in resources, "Owned boundary resource is missing")
        observed = resources[boundary_resource]
    else:
        require(
            boundary == f"arn:aws:iam::{target['account']}:policy/{policy_name}"
            and isinstance(boundary_template, dict)
            and boundary_template_sha256 == digest(boundary_template),
            "Exact external boundary owner template and digest required",
        )
        matches = [
            (name, row)
            for name, row in boundary_template["Resources"].items()
            if row.get("Type") == "AWS::IAM::ManagedPolicy"
            and row.get("Properties", {}).get("ManagedPolicyName") == policy_name
        ]
        require(len(matches) == 1, "External boundary ownership is ambiguous")
        boundary_resource, observed = matches[0]
        external = deepcopy(boundary_template)
    require(
        observed.get("Type") == "AWS::IAM::ManagedPolicy"
        and observed.get("Properties", {}).get("ManagedPolicyName") == policy_name
        and observed["Properties"].get("PolicyDocument") == previous_access
        and observed["Properties"].get("Path", "/") == "/"
        and not any(observed["Properties"].get(key) for key in ("Roles", "Users", "Groups")),
        "Existing boundary permissions differ",
    )
    candidate = deepcopy(template)
    access = runtime_access(target, values)
    candidate["Resources"]["ApiRole"]["Properties"]["Policies"][0]["PolicyDocument"] = access
    boundary_owner = external if external is not None else candidate
    boundary_owner["Resources"][boundary_resource]["Properties"]["PolicyDocument"] = deepcopy(
        access
    )
    enabled = features(values)
    desired = candidate["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
    desired.update(
        {
            "FITFINITY_AWS_REGION": target["region"],
            "FITFINITY_MEDIA_ENABLED": str(enabled["media"]).lower(),
            "FITFINITY_STAFF_INVITATIONS_ENABLED": str(enabled["invitations"]).lower(),
            "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED": str(enabled["email_changes"]).lower(),
        }
    )
    if enabled["media"]:
        desired["FITFINITY_MEDIA_BUCKET"] = media_bucket(target)
    else:
        desired.pop("FITFINITY_MEDIA_BUCKET", None)
    if enabled["invitations"]:
        desired["FITFINITY_STAFF_PORTAL_URL"] = env.get(
            "FITFINITY_STAFF_PORTAL_URL", sub("https://${Distribution.DomainName}/")
        )
    else:
        desired.pop("FITFINITY_STAFF_PORTAL_URL", None)
    return {
        "decision": "HOLD",
        "profile_sha256": identities(profile)["profile_sha256"],
        "base_template_sha256": digest(template),
        "candidate_template": candidate,
        "boundary_resource": boundary_resource,
        "boundary_base_template_sha256": boundary_template_sha256,
        "boundary_candidate_template": external,
        "rollback_template": deepcopy(template),
        "boundary_rollback_template": deepcopy(boundary_template),
        "required_evidence": [
            "Verify actual boundary-to-stack ownership and its single runtime-role consumer "
            "before applying its change set",
            "Verify target media bucket, origin and Cognito invitation configuration",
            "Apply the reviewed boundary policy before enabling runtime features",
        ],
    }
