"""Advance one reviewed existing-stack release step with durable uncertain-write receipts."""

import json
import re
import time

from deployment_profile import identities
from operator_checks import require
from release_access import service_role_arn
from release_changes import expected_changes, validate
from release_observation import digest
from release_pause import require_recorded_pause


def review_identity(review, profile, now, *, recovery=False):
    """Bind a release to one target, source, operation and expiring template review."""
    target = identities(profile)
    require(
        set(review)
        == {
            "profile_sha256",
            "source_sha",
            "operation_id",
            "expires_at",
            "stack_arn",
            "original_template",
            "candidate_template",
            "mode",
            "boundary_resource",
            "maintenance_marker",
        }
        and review["profile_sha256"] == target["profile_sha256"]
        and re.fullmatch(r"[a-f0-9]{40}", review["source_sha"])
        and re.fullmatch(r"[a-f0-9]{32}", review["operation_id"])
        and type(review["expires_at"]) is int
        and (recovery or 0 < review["expires_at"] - now <= 3600),
        "Exact current release review required",
    )
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
    require(
        isinstance(review["stack_arn"], str)
        and re.fullmatch(
            re.escape(prefix) + r"[A-Za-z][A-Za-z0-9-]*/[a-f0-9-]+", review["stack_arn"]
        )
        and (
            review["mode"] == "boundary"
            or review["stack_arn"].split("/")[1] == target["hosting_stack"]
        ),
        "Release stack target differs",
    )
    require(
        re.fullmatch(
            r"[a-f0-9]{32}:[a-f0-9]{40}:" + target["profile_sha256"], review["maintenance_marker"]
        ),
        "Exact target maintenance ownership required",
    )
    expected_changes(
        review["original_template"],
        review["candidate_template"],
        mode=review["mode"],
        boundary_resource=review["boundary_resource"],
    )
    return {
        "profile_sha256": target["profile_sha256"],
        "review_sha256": digest(review),
        "operation_id": review["operation_id"],
        "source_sha": review["source_sha"],
    }


def template(call, stack_arn, change_set=None):
    """Read the original template without emitting provider metadata or secret values."""
    arguments = {"StackName": stack_arn, "TemplateStage": "Original"}
    if change_set is not None:
        arguments["ChangeSetName"] = change_set
    value = call("cloudformation", "get-template", arguments)["TemplateBody"]
    return json.loads(value) if isinstance(value, str) else value


def check_change_set_arn(value, name, profile):
    """Reject a change-set response outside the original target and operation name."""
    target = identities(profile)
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:changeSet/"
    require(
        isinstance(value, str) and re.fullmatch(re.escape(prefix + name) + r"/[a-f0-9-]+", value),
        "Change-set ARN differs from the original target operation",
    )


def live_target(review, call, profile, *, after=False, inspecting=False, boundary_authority=None):
    """Verify resource ownership and paused traffic before allowing stack writes."""
    target = identities(profile)
    service_roles = (None, service_role_arn(profile))
    if boundary_authority is not None:
        require(
            review["mode"] == "boundary", "Separate owner authority applies only to its boundary"
        )
        service_roles = (boundary_authority["service_role_arn"],)
    rows = call("cloudformation", "describe-stacks", {"StackName": review["stack_arn"]})["Stacks"]
    require(
        len(rows) == 1
        and rows[0].get("StackId") == review["stack_arn"]
        and rows[0].get("StackName") == review["stack_arn"].split("/")[1]
        and not rows[0].get("ParentId")
        and not rows[0].get("RootId")
        and rows[0].get("RoleARN") in service_roles,
        "Exact root stack with only its reviewed service role required",
    )
    function = call("lambda", "get-function", {"FunctionName": target["runtime_function"]})
    config = function.get("Configuration", {})
    require(
        config.get("FunctionArn")
        == f"arn:aws:lambda:{target['region']}:{target['account']}:function:"
        + target["runtime_function"]
        and config.get("Role")
        == f"arn:aws:iam::{target['account']}:role/{target['resource_prefix']}-hosting-api"
        and function.get("Tags", {}).get("FitfinityMaintenance") == review["maintenance_marker"]
        and not function.get("TagsError"),
        "Runtime identity or maintenance ownership differs",
    )
    concurrency = call(
        "lambda", "get-function-concurrency", {"FunctionName": target["runtime_function"]}
    ).get("ReservedConcurrentExecutions")
    expected = (
        review["candidate_template"]["Resources"]["ApiFunction"]["Properties"][
            "ReservedConcurrentExecutions"
        ]
        if after and review["mode"] == "resume"
        else 0
    )
    allowed = {expected}
    if inspecting and review["mode"] in {"pause", "resume"}:
        allowed.update(
            review[key]["Resources"]["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"]
            for key in ("original_template", "candidate_template")
        )
    require(type(concurrency) is int and concurrency in allowed, "Runtime concurrency differs")
    if not inspecting:
        # An idle Lambda can remain Inactive while its reserved capacity is zero.
        # Traffic verification still requires an Active runtime after capacity is restored.
        require(
            config.get("LastUpdateStatus") == "Successful"
            and (
                config.get("State") == "Active"
                or (concurrency == 0 and config.get("State") == "Inactive")
            ),
            "Runtime configuration is not stable",
        )
    resources = call("cloudformation", "list-stack-resources", {"StackName": review["stack_arn"]})
    require(not resources.get("NextToken"), "Complete stack resource inventory required")
    rows_by_name = {}
    for resource in resources.get("StackResourceSummaries", []):
        name = resource.get("LogicalResourceId")
        require(name not in rows_by_name, "Duplicate stack resource identity")
        rows_by_name[name] = resource
    if review["mode"] != "boundary":
        for name, kind, physical in (
            ("ApiFunction", "AWS::Lambda::Function", target["runtime_function"]),
            ("ApiRole", "AWS::IAM::Role", target["resource_prefix"] + "-hosting-api"),
        ):
            row = rows_by_name.get(name, {})
            require(
                row.get("ResourceType") == kind and row.get("PhysicalResourceId") == physical,
                "Hosting stack does not own the expected runtime resource",
            )
    if review["boundary_resource"] is not None:
        boundary_arn = (
            f"arn:aws:iam::{target['account']}:policy/"
            + target["resource_prefix"]
            + "-hosting-api-boundary"
        )
        row = rows_by_name.get(review["boundary_resource"], {})
        require(
            row.get("ResourceType") == "AWS::IAM::ManagedPolicy"
            and row.get("PhysicalResourceId") == boundary_arn,
            "Reviewed stack does not own the runtime boundary",
        )
        role = call("iam", "get-role", {"RoleName": target["resource_prefix"] + "-hosting-api"})[
            "Role"
        ]
        require(
            role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") == boundary_arn,
            "Runtime boundary association differs",
        )
        consumers = call(
            "iam",
            "list-entities-for-policy",
            {"PolicyArn": boundary_arn, "PolicyUsageFilter": "PermissionsBoundary"},
        )
        require(
            not consumers.get("IsTruncated")
            and not consumers.get("Marker")
            and not consumers.get("PolicyUsers")
            and not consumers.get("PolicyGroups")
            and [row.get("RoleName") for row in consumers.get("PolicyRoles", [])]
            == [target["resource_prefix"] + "-hosting-api"],
            "Boundary has unknown or additional consumers",
        )
    return rows[0]


def validate_authority(authority, profile):
    """Keep the existing owner session and its retained CloudFormation service role separate."""
    target = identities(profile)
    prefix = rf"arn:aws:iam::{target['account']}:"
    path = r"(?:[\w+=,.@-]+/)*[\w+=,.@-]+"
    require(isinstance(authority, dict), "Exact external owner authority required")
    service = authority.get("service_role_arn")
    require(
        "service_role_arn" in authority
        and (
            service is None
            or isinstance(service, str)
            and re.fullmatch(prefix + "role/" + path, service)
        ),
        "Exact existing owner service role or no attached role required",
    )
    if set(authority) == {"operator_user_arn", "operator_user_id", "service_role_arn"}:
        require(
            isinstance(authority["operator_user_arn"], str)
            and re.fullmatch(prefix + "user/" + path, authority["operator_user_arn"])
            and isinstance(authority["operator_user_id"], str)
            and re.fullmatch(r"AIDA[A-Z0-9]{12,124}", authority["operator_user_id"]),
            "Exact direct IAM user ARN and immutable user ID required",
        )
        return
    role = authority.get("operator_role_arn")
    require(
        set(authority) == {"operator_role_arn", "service_role_arn"}
        and isinstance(role, str)
        and re.fullmatch(prefix + "role/" + path, role)
        and role != service
        and role.split("/")[-1]
        not in {
            target["hosting_role"],
            target["maintenance_role"],
            service_role_arn(profile).split("/")[-1],
            target["resource_prefix"] + "-hosting-api",
        },
        "Exact separate owner operator and existing service role required",
    )


def check_caller(mode, authority, call, profile):
    """Bind an operation to its routine role or its separately reviewed boundary owner."""
    target = identities(profile)
    if mode == "boundary":
        validate_authority(authority, profile)
    else:
        require(authority is None, "External owner authority is confined to its boundary")
    caller = call("sts", "get-caller-identity", {})
    require(caller.get("Account") == target["account"], "Wrong release account or role")
    if authority and "operator_user_arn" in authority:
        require(
            caller.get("Arn") == authority["operator_user_arn"]
            and caller.get("UserId") == authority["operator_user_id"],
            "Current direct IAM user differs from the reviewed owner",
        )
        return
    role = target["maintenance_role"] if mode == "pause" else target["hosting_role"]
    if authority:
        role = authority["operator_role_arn"].split("/")[-1]
    require(
        re.fullmatch(
            rf"arn:aws:sts::{target['account']}:assumed-role/{re.escape(role)}/[\w+=,.@-]+",
            caller.get("Arn", ""),
        ),
        "Wrong release account or role",
    )
    if authority:
        owner = call("iam", "get-role", {"RoleName": role})["Role"]
        require(
            owner.get("Arn") == authority["operator_role_arn"],
            "Existing owner role ARN or path differs",
        )


def execute(
    action, review, call, persist, *, profile, prior=None, now=None, boundary_authority=None
):
    """Persist each intent before one cloud write and recover by reading its original identity."""
    require(action in {"create", "inspect", "execute", "verify"}, "Unknown release action")
    require(callable(persist), "Durable release receipt writer required")
    clock = time.time if now is None else lambda: now
    observed_at = clock()
    identity = review_identity(
        review, profile, observed_at, recovery=action in {"inspect", "verify"}
    )
    check_caller(review["mode"], boundary_authority, call, profile)
    name = "release-" + review["operation_id"]
    receipt = {
        "identity": identity,
        "stack_arn": review["stack_arn"],
        "change_set": name,
        "state": "checked",
    }
    if prior is not None:
        require(
            prior.get("identity") == identity
            and prior.get("stack_arn") == review["stack_arn"]
            and prior.get("change_set") == name,
            "Prior release identity differs",
        )
    stack = live_target(
        review,
        call,
        profile,
        after=action == "verify",
        inspecting=action == "inspect",
        boundary_authority=boundary_authority,
    )
    receipt["service_role_arn"] = stack.get("RoleARN")
    if prior is not None:
        require(
            prior.get("service_role_arn") == receipt["service_role_arn"],
            "CloudFormation service role changed during the original operation",
        )
    if action in {"create", "execute"} and review["mode"] in {"rollout", "boundary"}:
        require_recorded_pause(call, profile)
    if action == "create":
        require(prior is None, "Inspect the original create; do not replay")
        require(
            stack.get("StackStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
            "Stable stack required",
        )
        require(
            template(call, review["stack_arn"]) == review["original_template"],
            "Observed base template changed",
        )
        body = json.dumps(review["candidate_template"], separators=(",", ":"))
        require(
            len(body.encode()) <= 51200, "Reviewed template exceeds inline CloudFormation limit"
        )
        review_identity(review, profile, clock())
        receipt["state"] = "create_submitted"
        persist(dict(receipt))
        result = call(
            "cloudformation",
            "create-change-set",
            {
                "StackName": review["stack_arn"],
                "ChangeSetName": name,
                "ChangeSetType": "UPDATE",
                **(
                    {"RoleARN": stack["RoleARN"]}
                    if stack.get("RoleARN") and review["mode"] not in {"pause", "boundary"}
                    else {}
                ),
                "TemplateBody": body,
                "Capabilities": ["CAPABILITY_NAMED_IAM"],
                "ClientToken": review["operation_id"] + "-create",
                "Description": "Fitfinity reviewed release " + identity["review_sha256"],
                "Parameters": [
                    {"ParameterKey": row["ParameterKey"], "UsePreviousValue": True}
                    for row in stack.get("Parameters", [])
                ],
            },
        )
        require(result.get("StackId") == review["stack_arn"], "Created change-set stack differs")
        check_change_set_arn(result.get("Id"), name, profile)
        receipt["change_set_arn"] = result["Id"]
    elif action == "verify":
        require(
            prior is not None and prior.get("execution_requested") is True,
            "Original execution intent required",
        )
        check_change_set_arn(prior.get("change_set_arn"), name, profile)
        require(stack.get("StackStatus") == "UPDATE_COMPLETE", "Original release is not complete")
        require(
            template(call, review["stack_arn"]) == review["candidate_template"],
            "Deployed template differs",
        )
        receipt.update(
            state="template_verified",
            execution_requested=True,
            change_set_arn=prior["change_set_arn"],
        )
    else:
        require(prior is not None, "Original release intent required")
        change_set = call(
            "cloudformation",
            "describe-change-set",
            {"StackName": review["stack_arn"], "ChangeSetName": name},
        )
        require(
            change_set.get("StackId") == review["stack_arn"]
            # DescribeChangeSet has no RoleARN field. Creation pins the retained service
            # role and DescribeStacks checks it against the original receipt at each step.
            and change_set.get("RoleARN", receipt["service_role_arn"])
            == receipt["service_role_arn"]
            and change_set.get("ChangeSetName") == name
            and change_set.get("Description")
            == "Fitfinity reviewed release " + identity["review_sha256"]
            and (
                not prior.get("change_set_arn")
                or prior["change_set_arn"] == change_set.get("ChangeSetId")
            ),
            "Original change-set identity differs",
        )
        check_change_set_arn(change_set.get("ChangeSetId"), name, profile)
        receipt["change_set_arn"] = change_set["ChangeSetId"]
        if action == "inspect":
            receipt.update(
                state="observed",
                stack_status=stack.get("StackStatus"),
                change_set_status=change_set.get("Status"),
                execution_status=change_set.get("ExecutionStatus"),
            )
            if (
                prior.get("execution_requested")
                or prior.get("state") == "execute_submitted"
                or change_set.get("ExecutionStatus") in {"EXECUTE_IN_PROGRESS", "EXECUTE_COMPLETE"}
            ):
                receipt["execution_requested"] = True
        elif action == "execute":
            require(
                not prior.get("execution_requested")
                and prior.get("state") in {"create_submitted", "observed"},
                "Inspect the original execution; do not replay",
            )
            require(
                stack.get("StackStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
                "Stable stack required",
            )
            require(
                template(call, review["stack_arn"]) == review["original_template"],
                "Observed base template changed",
            )
            require(
                template(call, review["stack_arn"], name) == review["candidate_template"],
                "Change-set template differs",
            )
            validate(
                review["original_template"],
                review["candidate_template"],
                change_set,
                profile=profile,
                stack_arn=review["stack_arn"],
                reviewed_template_sha256=digest(review["candidate_template"]),
                mode=review["mode"],
                boundary_resource=review["boundary_resource"],
            )
            review_identity(review, profile, clock())
            receipt.update(state="execute_submitted", execution_requested=True)
            persist(dict(receipt))
            call(
                "cloudformation",
                "execute-change-set",
                {
                    "StackName": review["stack_arn"],
                    "ChangeSetName": receipt["change_set_arn"],
                    "ClientRequestToken": review["operation_id"] + "-execute",
                },
            )
    persist(dict(receipt))
    return receipt
