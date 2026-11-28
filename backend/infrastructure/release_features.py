"""Prepare explicit feature changes while preserving the existing IAM boundary owner."""

import json
import re
from copy import deepcopy
from urllib.parse import unquote

import email_runtime
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
        and function["Properties"].get("VpcConfig", {}).get("SubnetIds") == values["subnets"]
        and function["Properties"].get("VpcConfig", {}).get("SecurityGroupIds")
        == values["security_groups"]
        and resources["ApiStage"]["Properties"].get("StageName") == values["stage"]
        and role["Type"] == "AWS::IAM::Role"
        and role["Properties"]["RoleName"] == target["resource_prefix"] + "-hosting-api"
        and role["Properties"].get("Path", "/") == "/",
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
        "FITFINITY_AWS_ACCOUNT_ID": target["account"],
    }.items():
        require(env.get(key) == value, "Existing runtime configuration differs")
    previous_email = email_runtime.from_environment(target, env)
    values = {**values, "email": values.get("email", previous_email)}
    previous_flags = {}
    for key, flag in FEATURE_FLAGS.items():
        value = env.get(flag, "false")
        require(value in {"true", "false"}, "Existing feature state is ambiguous")
        previous_flags[key] = value == "true"
    if previous_flags["media"]:
        require(
            env.get("FITFINITY_MEDIA_BUCKET") == media_bucket(target),
            "Existing media storage must not be silently redirected",
        )
    previous_access = runtime_access(
        target, {**values, "features": previous_flags, "email": previous_email}
    )
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
    access = runtime_access(target, values)
    accepted_boundary_policies = [previous_access]
    if external is not None:
        accepted_boundary_policies.append(access)
    require(
        observed.get("Type") == "AWS::IAM::ManagedPolicy"
        and observed.get("Properties", {}).get("ManagedPolicyName") == policy_name
        and observed["Properties"].get("PolicyDocument") in accepted_boundary_policies
        and observed["Properties"].get("Path", "/") == "/"
        and not any(observed["Properties"].get(key) for key in ("Roles", "Users", "Groups")),
        "Existing boundary permissions differ",
    )
    candidate = deepcopy(template)
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
    for name in email_runtime.KEYS:
        desired.pop(name, None)
    desired.update(email_runtime.environment(target, values.get("email")))
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
        "boundary_update_required": external is not None and external != boundary_template,
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


FEATURE_FLAGS = {
    "media": "FITFINITY_MEDIA_ENABLED",
    "invitations": "FITFINITY_STAFF_INVITATIONS_ENABLED",
    "email_changes": "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED",
}
FEATURE_KEYS = (
    set(FEATURE_FLAGS.values())
    | email_runtime.KEYS
    | {
        "FITFINITY_AWS_REGION",
        "FITFINITY_MEDIA_BUCKET",
        "FITFINITY_STAFF_PORTAL_URL",
    }
)


def boundary_arn(profile):
    """Identify the sole supported staff-runtime boundary in this account."""
    target = identities(profile)
    return (
        f"arn:aws:iam::{target['account']}:policy/{target['resource_prefix']}-hosting-api-boundary"
    )


def external_identity(owner, profile):
    """Bind an external owner to one separate stack, logical resource and exact template."""
    target = identities(profile)
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
    require(
        isinstance(owner, dict)
        and set(owner) == {"stack_arn", "logical_id", "template_sha256"}
        and isinstance(owner["stack_arn"], str)
        and re.fullmatch(
            re.escape(prefix) + r"[A-Za-z][A-Za-z0-9-]{0,127}/[a-f0-9-]+", owner["stack_arn"]
        )
        and owner["stack_arn"].split("/")[1] != target["hosting_stack"]
        and isinstance(owner["logical_id"], str)
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,254}", owner["logical_id"])
        and isinstance(owner["template_sha256"], str)
        and re.fullmatch(r"[a-f0-9]{64}", owner["template_sha256"]),
        "Exact separate boundary owner and template digest required",
    )
    return owner


def check_boundary_resource(call, profile, stack_arn, logical_id):
    """Confirm this stack physically owns the named staff-runtime boundary."""
    row = call(
        "cloudformation",
        "describe-stack-resource",
        {"StackName": stack_arn, "LogicalResourceId": logical_id},
    )["StackResourceDetail"]
    require(
        row.get("StackId") == stack_arn
        and row.get("LogicalResourceId") == logical_id
        and row.get("ResourceType") == "AWS::IAM::ManagedPolicy"
        and row.get("PhysicalResourceId") == boundary_arn(profile)
        and row.get("ResourceStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"},
        "Actual managed policy owner differs",
    )


def installed_owner(call, owner, profile):
    """Read the installed external template through the routine operator's read-only scope."""
    from release_execution import template

    external_identity(owner, profile)
    stack_arn = owner["stack_arn"]
    stacks = call("cloudformation", "describe-stacks", {"StackName": stack_arn})["Stacks"]
    require(
        len(stacks) == 1
        and stacks[0].get("StackId") == stack_arn
        and stacks[0].get("StackName") == stack_arn.split("/")[1]
        and not stacks[0].get("ParentId")
        and not stacks[0].get("RootId")
        and stacks[0].get("StackStatus")
        in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"},
        "Stable reviewed external root stack required",
    )
    check_boundary_resource(call, profile, stack_arn, owner["logical_id"])
    value = template(call, stack_arn)
    require(digest(value) == owner["template_sha256"], "Installed external owner template differs")
    return value


def iam_document(value):
    """Read the JSON or RFC 3986 encoded document returned by IAM."""
    if isinstance(value, str):
        return json.loads(value if value.lstrip().startswith("{") else unquote(value))
    return value


def verify_effective(call, profile, role, boundary_document):
    """Verify the actual runtime identity, inline policy and boundary's active default version."""
    target = identities(profile)
    name = target["resource_prefix"] + "-hosting-api"
    arn = boundary_arn(profile)
    role_args = {"RoleName": name}
    observed = call("iam", "get-role", role_args)["Role"]
    require(
        observed.get("RoleName") == name
        and observed.get("Arn") == f"arn:aws:iam::{target['account']}:role/{name}"
        and observed.get("Path") == "/"
        and iam_document(observed.get("AssumeRolePolicyDocument"))
        == role["AssumeRolePolicyDocument"]
        and observed.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") == arn,
        "Actual runtime trust, identity or boundary differs",
    )
    expected = role["Policies"][0]
    inline = call("iam", "list-role-policies", role_args)
    attached = call("iam", "list-attached-role-policies", role_args)
    require(
        not any(page.get(key) for page in (inline, attached) for key in ("IsTruncated", "Marker"))
        and inline.get("PolicyNames") == [expected["PolicyName"]]
        and attached.get("AttachedPolicies") == [],
        "Actual runtime policy inventory differs",
    )
    document = call("iam", "get-role-policy", {**role_args, "PolicyName": expected["PolicyName"]})
    require(
        document.get("RoleName") == name
        and document.get("PolicyName") == expected["PolicyName"]
        and iam_document(document.get("PolicyDocument")) == expected["PolicyDocument"],
        "Actual runtime inline policy differs",
    )
    policy_args = {"PolicyArn": arn}
    current = call("iam", "get-policy", policy_args)["Policy"]
    version_id = current.get("DefaultVersionId")
    require(
        current.get("Arn") == arn
        and isinstance(version_id, str)
        and re.fullmatch(r"v[1-9][0-9]*(\.[A-Za-z0-9-]+)?", version_id)
        and current.get("AttachmentCount") == 0
        and current.get("PermissionsBoundaryUsageCount") == 1,
        "Runtime boundary has another attachment, consumer or identity",
    )
    consumers = call(
        "iam",
        "list-entities-for-policy",
        {**policy_args, "PolicyUsageFilter": "PermissionsBoundary"},
    )
    require(
        not consumers.get("IsTruncated")
        and not consumers.get("Marker")
        and not consumers.get("PolicyUsers")
        and not consumers.get("PolicyGroups")
        and [row.get("RoleName") for row in consumers.get("PolicyRoles", [])] == [name],
        "Runtime boundary does not have its sole reviewed consumer",
    )
    version = call("iam", "get-policy-version", {**policy_args, "VersionId": version_id})[
        "PolicyVersion"
    ]
    require(
        version.get("VersionId") == version_id
        and version.get("IsDefaultVersion") is True
        and iam_document(version.get("Document")) == boundary_document,
        "Effective default boundary policy differs",
    )


def check_rollout_access(review, hosting, call, profile, external=None):
    """Check the effective permissions required by a reviewed feature rollout or resumption."""
    role = hosting["Resources"]["ApiRole"]["Properties"]
    owner = review.get("external_boundary")
    expected = role["Policies"][0]["PolicyDocument"]
    if owner is not None:
        if external is None:
            external = installed_owner(call, owner, profile)
        policy_resource = external["Resources"][owner["logical_id"]]
        values = review["feature_values"]
        target = bindings(profile, values)
        env = hosting["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
        expected = runtime_access(
            target,
            {**values, "email": values.get("email", email_runtime.from_environment(target, env))},
        )
        require(
            role["PermissionsBoundary"] == boundary_arn(profile),
            "External boundary association differs",
        )
    else:
        boundary = role["PermissionsBoundary"]
        require(
            isinstance(boundary, dict) and set(boundary) == {"Ref"},
            "External boundary owner review required",
        )
        logical = boundary["Ref"]
        check_boundary_resource(call, profile, review["stack_arn"], logical)
        policy_resource = hosting["Resources"][logical]
    require(
        policy_resource.get("Type") == "AWS::IAM::ManagedPolicy"
        and policy_resource["Properties"].get("ManagedPolicyName")
        == boundary_arn(profile).split("/")[-1]
        and policy_resource["Properties"].get("PolicyDocument") == expected,
        "Installed owner does not contain the reviewed boundary policy",
    )
    verify_effective(call, profile, role, expected)


def checked_state(state, profile):
    """Allow only public feature settings in original-operation recovery metadata."""
    from urllib.parse import urlsplit

    target = identities(profile)
    require(
        isinstance(state, dict) and set(state) <= FEATURE_KEYS,
        "Exact public feature recovery settings required",
    )
    email_runtime.from_environment(target, state)
    for key, value in state.items():
        if key in email_runtime.KEYS:
            continue
        if key in FEATURE_FLAGS.values():
            require(value in {"true", "false"}, "Boolean feature state required")
        elif key == "FITFINITY_AWS_REGION":
            require(value == target["region"], "Original feature region differs")
        elif key == "FITFINITY_MEDIA_BUCKET":
            require(value == media_bucket(target), "Original media bucket differs")
        elif value != sub("https://${Distribution.DomainName}/"):
            require(isinstance(value, str), "Public portal origin required")
            parsed = urlsplit(value)
            require(
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and parsed.path in {"", "/"}
                and parsed.port in {None, 443},
                "Credential-free public portal origin required",
            )
    return deepcopy(state)


def recovery_state(template, profile):
    """Retain feature switches and public destinations, never arbitrary runtime values."""
    env = template["Resources"]["ApiFunction"]["Properties"]["Environment"]["Variables"]
    return checked_state({key: env[key] for key in FEATURE_KEYS if key in env}, profile)


def restore_state(template, state, values, profile):
    """Reconstruct previous feature settings and derived permissions in their existing owners."""
    target = bindings(profile, values)
    previous = checked_state(state, profile)
    restored = deepcopy(template)
    resources = restored["Resources"]
    env = resources["ApiFunction"]["Properties"]["Environment"]["Variables"]
    for key in FEATURE_KEYS:
        env.pop(key, None)
    env.update(previous)
    flags = {name: previous.get(key, "false") == "true" for name, key in FEATURE_FLAGS.items()}
    access = runtime_access(
        target,
        {**values, "features": flags, "email": email_runtime.from_environment(target, previous)},
    )
    role = resources["ApiRole"]["Properties"]
    role["Policies"][0]["PolicyDocument"] = access
    boundary = role["PermissionsBoundary"]
    if isinstance(boundary, dict) and set(boundary) == {"Ref"}:
        resources[boundary["Ref"]]["Properties"]["PolicyDocument"] = deepcopy(access)
    return restored
