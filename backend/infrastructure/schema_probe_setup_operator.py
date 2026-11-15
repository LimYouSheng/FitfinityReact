"""Create only the reviewed probe IAM stack after checking its exact change set."""

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


def validate_change_set(change_set):
    """Permit only the three new reviewed IAM resources."""
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
    rows = change_set.get("Changes", [])
    require(len(rows) == 3, "Unexpected resource count")
    actual = {}
    for row in rows:
        resource = row.get("ResourceChange", {})
        require(
            resource.get("Action") == "Add"
            and resource.get("Replacement") in (None, "False")
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


def install(template, directory, call, pause=time.sleep):
    """Create a new IAM-only stack; preserve receipts and refuse replay or adoption."""
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
        "template_sha256": hashlib.sha256(
            json.dumps(template, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }

    def save(state):
        receipt["state"] = state
        receipt_path.write_text(json.dumps(receipt, indent=2))

    save("change_set_request_started")
    try:
        created = call(
            "cloudformation",
            "create-change-set",
            "--stack-name",
            STACK,
            "--change-set-name",
            "probe-access-" + operation,
            "--change-set-type",
            "CREATE",
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
            ),
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
        validate_change_set(change)
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
            if status == "CREATE_COMPLETE":
                verify_role(template, call)
                save("iam_setup_verified")
                return receipt
            require(
                status in {"REVIEW_IN_PROGRESS", "CREATE_IN_PROGRESS"},
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
