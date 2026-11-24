"""Install or update scoped worker access after checking the exact IAM change set."""

import hashlib
import json
import re
import subprocess
import time
import uuid

from deployment_profile import DEVELOPER, identities

TARGET = identities(DEVELOPER)
ACCOUNT = TARGET["account"]
REGION = TARGET["region"]
STACK = TARGET["setup_stack"]
ROLE = TARGET["operator_role"]
POLICY_NAME = TARGET.get("lifecycle_policy", "ProbeLifecycle")


def require(value, message):
    """Stop on an unmet execution prerequisite."""
    if not value:
        raise RuntimeError(message)


def template_hash(template):
    """Hash the canonical CloudFormation template bytes."""
    data = json.dumps(template, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def validate_update(installed, candidate, stack_id, target):
    """Allow reviewed worker reads and the same repository's immutable subject upgrade."""
    prefix = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
    require(
        isinstance(stack_id, str)
        and re.fullmatch(re.escape(prefix + target["setup_stack"] + "/") + r"[a-f0-9-]+", stack_id),
        "Exact installed IAM owner stack ARN required",
    )
    # Undo only the explicitly allowed policy changes, then compare the whole base template.
    before = json.loads(json.dumps(candidate))
    role = before["Resources"]["OperatorRole"]["Properties"]
    original_role = installed["Resources"]["OperatorRole"]["Properties"]
    trust = role["AssumeRolePolicyDocument"]
    if {"github_owner_id", "github_repository_id"} <= target.keys() and trust != original_role[
        "AssumeRolePolicyDocument"
    ]:
        # The planner validated the candidate against this profile. Only undo the subject
        # substitution. The full-template comparison still covers every other trust field.
        sub_key = "token.actions.githubusercontent.com:sub"
        equals = trust["Statement"][0]["Condition"]["StringEquals"]
        require(
            equals.get(sub_key) == target["oidc_subject"], "Reviewed immutable subject required"
        )
        environment = target["oidc_subject"].split(":environment:", 1)[1]
        equals[sub_key] = f"repo:{target['github_repository']}:environment:{environment}"
    staff = (
        f"arn:aws:lambda:{target['region']}:{target['account']}:function:"
        + target["runtime_function"]
    )

    def documents(template):
        resources = template["Resources"]
        return (
            resources["OperatorRole"]["Properties"]["Policies"][0]["PolicyDocument"],
            resources["OperatorBoundary"]["Properties"]["PolicyDocument"],
        )

    for policy, original in zip(documents(before), documents(installed), strict=True):
        for row in policy["Statement"][:]:
            if row in original["Statement"]:
                continue
            actions = row["Action"]
            if actions in ("ec2:DescribeVpcs", "ec2:GetSecurityGroupsForVpc"):
                policy["Statement"].remove(row)
            elif actions == ["ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"]:
                row.pop("Condition")
            elif row["Resource"] == staff and "lambda:ListTags" in actions:
                actions.remove("lambda:ListTags")
    require(
        before == installed and candidate != installed,
        "Installed IAM template differs beyond the reviewed operator access or is already current",
    )
    return {
        key
        for key in ("OperatorRole", "OperatorBoundary")
        if installed["Resources"][key] != candidate["Resources"][key]
    }


def validate_change_set(change_set, *, modified=None):
    """Permit the fresh resources or exactly the in-place changes present in the reviewed update."""
    require(
        change_set.get("Status") == "CREATE_COMPLETE"
        and change_set.get("ExecutionStatus") == "AVAILABLE",
        "Change set is not executable",
    )
    expected = {
        "RuntimeBoundary": "AWS::IAM::ManagedPolicy",
        "OperatorBoundary": "AWS::IAM::ManagedPolicy",
        "OperatorRole": "AWS::IAM::Role",
    }
    if modified is not None:
        require(
            modified and modified <= {"OperatorRole", "OperatorBoundary"},
            "Only reviewed operator and boundary changes are allowed",
        )
        expected = {key: expected[key] for key in modified}
    rows = change_set.get("Changes", [])
    require(len(rows) == len(expected), "Unexpected resource count")
    actual = {}
    for row in rows:
        resource = row.get("ResourceChange", {})
        require(
            resource.get("Action") == ("Modify" if modified is not None else "Add")
            and resource.get("Replacement")
            in (("False",) if modified is not None else (None, "False"))
            and resource.get("LogicalResourceId") not in actual,
            "Existing resource change refused",
        )
        actual[resource.get("LogicalResourceId")] = resource.get("ResourceType")
    require(actual == expected, "Unexpected resource identity or type")


def verify_role(template, call):
    """Check actual role trust, inline policy and both permission ceilings."""
    resources = template["Resources"]
    props = resources["OperatorRole"]["Properties"]
    role = call("iam", "get-role", "--role-name", ROLE)["Role"]
    boundary = f"arn:aws:iam::{ACCOUNT}:policy/{ROLE}-boundary"
    require(
        role.get("Arn") == f"arn:aws:iam::{ACCOUNT}:role/{ROLE}"
        and role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") == boundary
        and role.get("AssumeRolePolicyDocument") == props["AssumeRolePolicyDocument"],
        "Created operator trust or boundary differs",
    )
    inline = call("iam", "get-role-policy", "--role-name", ROLE, "--policy-name", POLICY_NAME)
    require(
        inline.get("PolicyDocument") == props["Policies"][0]["PolicyDocument"],
        "Operator policy differs",
    )
    require(
        call("iam", "list-attached-role-policies", "--role-name", ROLE).get("AttachedPolicies")
        == [],
        "Unexpected attached operator policies",
    )
    require(
        call("iam", "list-role-policies", "--role-name", ROLE).get("PolicyNames") == [POLICY_NAME],
        "Unexpected inline operator policies",
    )
    for name in ("RuntimeBoundary", "OperatorBoundary"):
        prop = resources[name]["Properties"]
        arn = f"arn:aws:iam::{ACCOUNT}:policy/" + prop["ManagedPolicyName"]
        policy = call("iam", "get-policy", "--policy-arn", arn)["Policy"]
        version = call(
            "iam",
            "get-policy-version",
            "--policy-arn",
            arn,
            "--version-id",
            policy["DefaultVersionId"],
        )["PolicyVersion"]
        require(
            version.get("Document") == prop["PolicyDocument"],
            "Created permissions boundary differs",
        )


def verify_installed(template, update, call):
    """Bind an UPDATE to the observed stack, physical resources and effective original policies."""
    stack_id = update["stack_id"]
    rows = call("cloudformation", "describe-stacks", "--stack-name", stack_id)["Stacks"]
    require(
        len(rows) == 1
        and rows[0].get("StackId") == stack_id
        and rows[0].get("StackName") == STACK
        and rows[0].get("StackStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
        "Stable original IAM stack required",
    )
    result = call(
        "cloudformation", "get-template", "--stack-name", stack_id, "--template-stage", "Original"
    )["TemplateBody"]
    original = json.loads(result) if isinstance(result, str) else result
    require(template_hash(original) == update["original_sha256"], "Installed IAM template changed")
    modified = validate_update(original, template, stack_id, TARGET)
    resources = template["Resources"]
    owners = {
        key: (
            row["Type"],
            ROLE
            if key == "OperatorRole"
            else f"arn:aws:iam::{ACCOUNT}:policy/" + row["Properties"]["ManagedPolicyName"],
        )
        for key, row in resources.items()
    }
    actual = call("cloudformation", "list-stack-resources", "--stack-name", stack_id)[
        "StackResourceSummaries"
    ]
    require(
        len(actual) == len(owners)
        and {
            row.get("LogicalResourceId"): (row.get("ResourceType"), row.get("PhysicalResourceId"))
            for row in actual
        }
        == owners,
        "Installed role or boundaries belong to another IAM owner",
    )
    verify_role(original, call)
    return modified


def install(template, directory, call, pause=time.sleep, *, update=None):
    """Apply one reviewed IAM change set and preserve the intent on an uncertain response."""
    if update is not None:
        require(
            isinstance(update, dict)
            and set(update) == {"stack_id", "original_sha256"}
            and isinstance(update["original_sha256"], str)
            and re.fullmatch(r"[a-f0-9]{64}", update["original_sha256"])
            and isinstance(update["stack_id"], str)
            and re.fullmatch(
                rf"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{re.escape(STACK)}/[a-f0-9-]+",
                update["stack_id"],
            ),
            "Exact original IAM stack ARN and template hash required for UPDATE",
        )
    require(call("sts", "get-caller-identity").get("Account") == ACCOUNT, "Wrong AWS account")
    provider = call(
        "iam",
        "get-open-id-connect-provider",
        "--open-id-connect-provider-arn",
        f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com",
    )
    audiences = provider.get("ClientIDList")
    require(
        provider.get("Url") == "token.actions.githubusercontent.com"
        and isinstance(audiences, list)
        and all(isinstance(audience, str) for audience in audiences)
        and any(audience == "sts.amazonaws.com" for audience in audiences),
        "OIDC provider differs",
    )
    modified = None
    if update:
        modified = verify_installed(template, update, call)
    else:
        require(
            call("iam", "get-role", "--role-name", ROLE, missing="NoSuchEntity") is None,
            "Operator role already exists; inspect instead of adopting or overwriting it",
        )
        for name in ("RuntimeBoundary", "OperatorBoundary"):
            arn = (
                f"arn:aws:iam::{ACCOUNT}:policy/"
                + template["Resources"][name]["Properties"]["ManagedPolicyName"]
            )
            require(
                call("iam", "get-policy", "--policy-arn", arn, missing="NoSuchEntity") is None,
                "Boundary already exists; inspect instead of overwriting it",
            )
        require(
            call("cloudformation", "describe-stacks", "--stack-name", STACK, missing="MissingStack")
            is None,
            "Setup stack already exists; inspect its previous operation before proceeding",
        )
    change_type = "UPDATE" if update else "CREATE"
    directory.mkdir(parents=True, exist_ok=False)
    template_path = directory / "template.json"
    template_path.write_text(json.dumps(template))
    receipt_path = directory / "receipt.json"
    operation = uuid.uuid4().hex
    receipt = {
        "account": ACCOUNT,
        "region": REGION,
        "profile_sha256": TARGET["profile_sha256"],
        "stack_name": STACK,
        "operation_id": operation,
        "state": "prepared",
        "application_deployed": False,
        "template_sha256": template_hash(template),
        "change_set_type": change_type,
    }
    if update:
        receipt.update(update)

    def save(state):
        receipt["state"] = state
        receipt_path.write_text(json.dumps(receipt, indent=2))

    save("change_set_request_started")
    try:
        created = call(
            "cloudformation",
            "create-change-set",
            "--stack-name",
            update["stack_id"] if update else STACK,
            "--change-set-name",
            "probe-access-" + operation,
            "--change-set-type",
            change_type,
            "--template-body",
            "file://" + str(template_path.resolve()),
            "--capabilities",
            "CAPABILITY_NAMED_IAM",
            "--client-token",
            operation,
        )
        change_id, stack_id = created["Id"], created["StackId"]
        require(
            re.fullmatch(
                rf"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/[\w-]+", stack_id
            )
            and (not update or stack_id == update["stack_id"]),
            "Created stack identity differs",
        )
        require(
            change_id.startswith(
                f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:changeSet/probe-access-{operation}/"
            ),
            "Created change set identity differs",
        )
        receipt.update(change_set_id=change_id, stack_id=stack_id)
        save("change_set_created")
        for _attempt in range(60):
            change = call("cloudformation", "describe-change-set", "--change-set-name", change_id)
            if change.get("Status") not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
                break
            pause(5)
        validate_change_set(change, modified=modified)
        if update:
            require(
                change.get("StackId") == stack_id and change.get("ChangeSetId") == change_id,
                "IAM UPDATE change set belongs to another stack or request",
            )
        observed = call(
            "cloudformation",
            "get-template",
            "--change-set-name",
            change_id,
            "--stack-name",
            stack_id,
            "--template-stage",
            "Original",
        )["TemplateBody"]
        require(
            (json.loads(observed) if isinstance(observed, str) else observed) == template,
            "AWS change-set template differs from reviewed bytes",
        )
        save("execute_request_started")
        call(
            "cloudformation",
            "execute-change-set",
            "--change-set-name",
            change_id,
            "--client-request-token",
            operation,
        )
        save("execution_submitted")
        for _attempt in range(120):
            stack = call("cloudformation", "describe-stacks", "--stack-name", stack_id)["Stacks"][0]
            status = stack["StackStatus"]
            receipt["stack_status"] = status
            save("execution_submitted")
            if update and status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
                change = call(
                    "cloudformation", "describe-change-set", "--change-set-name", change_id
                )
                execution = change.get("ExecutionStatus")
                if execution in {"AVAILABLE", "EXECUTE_IN_PROGRESS"}:
                    pause(5)
                    continue
                require(execution == "EXECUTE_COMPLETE", "IAM UPDATE execution did not complete")
            if status == change_type + "_COMPLETE":
                verify_role(template, call)
                save("iam_setup_verified")
                return receipt
            require(
                status
                in {
                    "REVIEW_IN_PROGRESS",
                    change_type + "_IN_PROGRESS",
                    change_type + "_COMPLETE_CLEANUP_IN_PROGRESS",
                },
                "Setup did not complete; inspect stack events, do not replay",
            )
            pause(5)
        raise RuntimeError("Setup is still pending; inspect existing stack, do not replay")
    except Exception:
        receipt["next"] = (
            "Inspect retained stack/change set before any retry; no automatic deletion"
        )
        save("failed_or_uncertain")
        raise


def aws(service, operation, *args, missing=None):
    """Run the setup command without automatic retries or raw provider error output."""
    import os

    result = subprocess.run(
        [
            "aws",
            service,
            operation,
            *args,
            "--region",
            REGION,
            "--output",
            "json",
            "--no-cli-pager",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env={
            **os.environ,
            "AWS_PAGER": "",
            "AWS_MAX_ATTEMPTS": "1",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
        },
    )
    if result.returncode:
        match = re.search(r"An error occurred \(([^)]+)\)", result.stderr)
        code = match.group(1) if match else "AWS_COMMAND_FAILED"
        if missing == "NoSuchEntity" and code == missing:
            return None
        if (
            missing == "MissingStack"
            and code == "ValidationError"
            and (f"Stack with id {STACK} does not exist" in result.stderr)
        ):
            return None
        raise RuntimeError(f"{service}/{operation}: {code}; inspect state before retry")
    return json.loads(result.stdout) if result.stdout.strip() else {}
