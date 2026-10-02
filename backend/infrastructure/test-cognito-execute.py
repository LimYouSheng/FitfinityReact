import datetime
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

TEMPLATE = json.loads((Path(__file__).resolve().parent / "test-cognito-accepted.json").read_text())
TEMPLATE_SHA = "c54ad8e8034cd6258dbc5fd25be078d861343e04e3c8821deb35ee51bb804887"
ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
PROFILE = "fitfinity-test"
STACK = "fitfinity-test-cognito"
FOUNDATION = (
    "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fit"
    "finity-test-foundation/6b51b020-b65f-11f1-82ee-0a2a8f1e9b2d"
)
ORIGINAL_SHA = "3fd67c4720badfc8a9e57e0febb0d38a8f4c6cc8ed11239c39015b4e64a9a5f1"
STACK_ID = (
    "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fit"
    "finity-test-cognito/776045f0-b66b-11f1-92b4-06ffd526f669"
)
POOL_ID = "ap-southeast-1_La0Y3MXCj"
TAGS = {
    "Application": "Fitfinity",
    "Environment": "test",
    "ManagedBy": "fitfinity-cognito-operator",
    "TemplateSHA256": ORIGINAL_SHA,
}
ALLOWED = {
    ("sts", "get-caller-identity"),
    ("freetier", "get-account-plan-state"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "get-template"),
    ("cloudformation", "validate-template"),
    ("cloudformation", "update-stack"),
    ("cloudformation", "set-stack-policy"),
    ("cloudformation", "get-stack-policy"),
    ("cloudformation", "list-stack-resources"),
    ("cloudformation", "describe-stack-events"),
    ("cognito-idp", "list-user-pool-clients"),
    ("cognito-idp", "describe-user-pool"),
    ("cognito-idp", "describe-user-pool-client"),
    ("cognito-idp", "get-user-pool-mfa-config"),
}
REPORT = {
    "account": ACCOUNT,
    "region": REGION,
    "stack": STACK,
    "template_sha256": TEMPLATE_SHA,
    "cognito_verified": False,
    "app_deployed": False,
    "write_attempted": False,
}


def note(message):
    print(message, flush=True)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def aws(service, operation, *args, region=REGION, missing_ok=False):
    require((service, operation) in ALLOWED, "Operation refused")
    if operation == "describe-user-pool-client":
        require(
            "--query" in args and args[args.index("--query") + 1] == CLIENT_QUERY,
            "Secret-safe client query required",
        )
    result = subprocess.run(
        [
            "aws",
            service,
            operation,
            *args,
            "--profile",
            PROFILE,
            "--region",
            region,
            "--output",
            "json",
            "--no-cli-pager",
            "--no-cli-auto-prompt",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        if (
            missing_ok
            and operation == "describe-stacks"
            and "(ValidationError)" in result.stderr
            and f"Stack with id {STACK} does not exist" in result.stderr
        ):
            return None
        # Do not expose arbitrary response bodies from credential-bearing API operations.
        if operation == "describe-user-pool-client":
            raise RuntimeError(
                "Cognito client configuration lookup failed; response suppres"
                "sed to protect credentials"
            )
        raise RuntimeError(service + " " + operation + ": " + result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


CLIENT_FIELDS = [
    "ClientId",
    "UserPoolId",
    "ClientName",
    "ExplicitAuthFlows",
    "EnableTokenRevocation",
    "PreventUserExistenceErrors",
    "RefreshTokenRotation",
    "AccessTokenValidity",
    "IdTokenValidity",
    "RefreshTokenValidity",
    "TokenValidityUnits",
    "AuthSessionValidity",
    "ReadAttributes",
    "WriteAttributes",
    "AllowedOAuthFlowsUserPoolClient",
    "CallbackURLs",
    "LogoutURLs",
    "SupportedIdentityProviders",
]
CLIENT_QUERY = (
    "UserPoolClient.{"
    + ",".join(k + ":" + k for k in CLIENT_FIELDS)
    + ',HasClientSecret:ClientSecret != `null` && ClientSecret != `""`}'
)


def confirm():
    with open("/dev/tty", "w") as terminal:
        terminal.write(
            ("To repair the existing Cognito test stack with the displayed permissions, type ")
            + ACCOUNT
            + ": "
        )
        terminal.flush()
    with open("/dev/tty") as terminal:
        require(
            terminal.readline().strip() == ACCOUNT,
            "Confirmation did not match; no creation request sent",
        )


def get_stack(missing_ok=False):
    result = aws("cloudformation", "describe-stacks", "--stack-name", STACK, missing_ok=missing_ok)
    if result is None:
        return None
    stack = result["Stacks"][0]
    require(stack["StackId"] == STACK_ID, "Stack identity mismatch")
    tags = {x["Key"]: x["Value"] for x in stack.get("Tags", [])}
    require(
        all(tags.get(k) == v for k, v in TAGS.items()),
        "Existing stack ownership/template tags differ",
    )
    require(
        {x["ParameterKey"]: x.get("ParameterValue") for x in stack.get("Parameters", [])}
        == {"SessionHours": "8"},
        "Session duration differs",
    )
    live = aws(
        "cloudformation",
        "get-template",
        "--stack-name",
        stack["StackId"],
        "--template-stage",
        "Original",
    )["TemplateBody"]
    if isinstance(live, str):
        live = json.loads(live)
    original = json.loads(json.dumps(TEMPLATE))
    del original["Resources"]["StaffPool"]["Properties"]["UserAttributeUpdateSettings"]
    original["Resources"]["StaffClient"]["Properties"]["WriteAttributes"] = ["name"]
    require(
        live == TEMPLATE or (stack["StackStatus"] == "CREATE_FAILED" and live == original),
        "Existing stack template differs from reviewed recovery",
    )
    stack["_original_template"] = live == original
    require(
        stack.get("EnableTerminationProtection") is True, "Stack termination protection is missing"
    )
    return stack


def verify(stack):
    resources = aws("cloudformation", "list-stack-resources", "--stack-name", stack["StackId"])[
        "StackResourceSummaries"
    ]
    require(
        len(resources) == 2
        and {x["LogicalResourceId"] for x in resources} == set(TEMPLATE["Resources"]),
        "Unexpected resource inventory",
    )
    for item in resources:
        require(
            item["ResourceType"] == TEMPLATE["Resources"][item["LogicalResourceId"]]["Type"]
            and item["ResourceStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
            "Unexpected resource state/type",
        )
    ids = {x["LogicalResourceId"]: x["PhysicalResourceId"] for x in resources}
    outputs = {x["OutputKey"]: x["OutputValue"] for x in stack.get("Outputs", [])}
    require(
        outputs == {"PoolId": ids["StaffPool"], "ClientId": ids["StaffClient"]},
        "Outputs do not match the created resources",
    )
    pool_id, client_id = outputs["PoolId"], outputs["ClientId"]
    require(pool_id == POOL_ID, "Preserved pool identity differs")
    pool = aws("cognito-idp", "describe-user-pool", "--user-pool-id", pool_id)["UserPool"]
    expected = TEMPLATE["Resources"]["StaffPool"]["Properties"]
    for key in [
        "UserPoolTier",
        "DeletionProtection",
        "UsernameAttributes",
        "UsernameConfiguration",
        "AutoVerifiedAttributes",
        "MfaConfiguration",
        "AccountRecoverySetting",
        "UserAttributeUpdateSettings",
    ]:
        require(pool.get(key) == expected[key], "Pool setting differs: " + key)
    require(pool.get("Name") == STACK + "-staff", "Pool name differs")
    require(
        pool.get("AdminCreateUserConfig", {}).get("AllowAdminCreateUserOnly") is True,
        "Public signup is enabled",
    )
    password = pool.get("Policies", {}).get("PasswordPolicy", {})
    require(
        all(password.get(k) == v for k, v in expected["Policies"]["PasswordPolicy"].items()),
        "Password policy differs",
    )
    require(
        not pool.get("DeviceConfiguration")
        and not pool.get("Domain")
        and not pool.get("CustomDomain")
        and not pool.get("LambdaConfig"),
        "Unexpected device/domain/trigger configuration",
    )
    mfa = aws("cognito-idp", "get-user-pool-mfa-config", "--user-pool-id", pool_id)
    require(
        mfa.get("MfaConfiguration") == "ON"
        and mfa.get("SoftwareTokenMfaConfiguration", {}).get("Enabled") is True
        and not mfa.get("SmsMfaConfiguration")
        and not mfa.get("EmailMfaConfiguration"),
        "Required TOTP-only MFA differs",
    )
    client = aws(
        "cognito-idp",
        "describe-user-pool-client",
        "--user-pool-id",
        pool_id,
        "--client-id",
        client_id,
        "--query",
        CLIENT_QUERY,
    )
    require(
        client.get("HasClientSecret") is True
        and client.get("ClientId") == client_id
        and client.get("UserPoolId") == pool_id,
        "Confidential client identity differs",
    )
    for key, value in TEMPLATE["Resources"]["StaffClient"]["Properties"].items():
        if key in {"UserPoolId", "GenerateSecret"}:
            continue
        if key == "RefreshTokenValidity":
            value = 8
        actual = client.get(key)
        require(
            (sorted(actual or []) == sorted(value)) if isinstance(value, list) else actual == value,
            "Client setting differs: " + key,
        )
    require(
        not client.get("AllowedOAuthFlowsUserPoolClient")
        and not client.get("CallbackURLs")
        and not client.get("LogoutURLs"),
        "Unexpected OAuth configuration",
    )
    require(
        client.get("SupportedIdentityProviders") in (None, [], ["COGNITO"]),
        "Unexpected identity provider",
    )
    REPORT.update(
        stack_id=stack["StackId"],
        status=stack["StackStatus"],
        outputs=outputs,
        tier=pool["UserPoolTier"],
        client_configuration=client,
        cognito_verified=True,
    )


POOL_POLICY = {
    "Statement": [
        {"Effect": "Allow", "Principal": "*", "Action": "Update:*", "Resource": "*"},
        {
            "Effect": "Deny",
            "Principal": "*",
            "Action": ["Update:Replace", "Update:Delete"],
            "Resource": "LogicalResourceId/StaffPool",
        },
    ]
}


def recovery_inventory():
    resources = aws("cloudformation", "list-stack-resources", "--stack-name", STACK_ID)[
        "StackResourceSummaries"
    ]
    require(
        len(resources) == 2
        and {x["LogicalResourceId"] for x in resources} == {"StaffPool", "StaffClient"},
        "Unexpected preserved resource inventory",
    )
    for item in resources:
        require(
            item["ResourceType"] == TEMPLATE["Resources"][item["LogicalResourceId"]]["Type"],
            "Resource type mismatch",
        )
        if item["LogicalResourceId"] == "StaffPool":
            require(
                item.get("PhysicalResourceId") == POOL_ID
                and item["ResourceStatus"] == "CREATE_COMPLETE",
                "Pool identity/state mismatch",
            )
        else:
            require(
                item["ResourceStatus"] == "CREATE_FAILED"
                and "invalid write attributes" in item.get("ResourceStatusReason", "").lower(),
                "Client failure differs from the reviewed receipt",
            )
            require(
                not item.get("PhysicalResourceId"),
                "Failed client already has a physical identity; review required",
            )
    pool = aws("cognito-idp", "describe-user-pool", "--user-pool-id", POOL_ID)["UserPool"]
    require(
        pool.get("Id") == POOL_ID
        and pool.get("Name") == STACK + "-staff"
        and pool.get("UserPoolTier") == "ESSENTIALS",
        "Preserved pool differs",
    )
    schema = {x["Name"]: x for x in pool.get("SchemaAttributes", [])}
    require(
        schema.get("email", {}).get("Required") is True
        and schema["email"].get("Mutable") is True
        and schema.get("name", {}).get("Mutable") is True,
        "Live schema differs from the supplied diagnosis",
    )
    require(
        {x["Name"] for x in schema.values() if x.get("Required") and x.get("Mutable")} == {"email"},
        "Unexpected required writable attribute",
    )
    clients = aws(
        "cognito-idp", "list-user-pool-clients", "--user-pool-id", POOL_ID, "--max-results", "60"
    )["UserPoolClients"]
    require(not clients, "Pool already has a client; review instead of creating another")


def main():
    note("Fitfinity AWS — recover Cognito client attribute configuration")
    forbidden = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
    }
    require(
        not any(
            v and (k in forbidden or k.startswith("AWS_ENDPOINT_URL"))
            for k, v in os.environ.items()
        ),
        "Remove AWS credential/config/endpoint environment overrides",
    )
    os.environ.update(
        AWS_PAGER="",
        AWS_CLI_AUTO_PROMPT="off",
        AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
        AWS_MAX_ATTEMPTS="2",
    )
    who = aws("sts", "get-caller-identity")
    require(
        who.get("Account") == ACCOUNT
        and who.get("Arn") == f"arn:aws:iam::{ACCOUNT}:user/fitfinity-deployer",
        "Expected test IAM identity was not verified",
    )
    foundation = aws("cloudformation", "describe-stacks", "--stack-name", FOUNDATION)["Stacks"][0]
    require(
        foundation.get("StackId") == FOUNDATION
        and foundation.get("StackStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
        "Expected completed foundation was not verified",
    )
    plan = aws("freetier", "get-account-plan-state", region="us-east-1")
    require(
        plan.get("accountPlanStatus") == "ACTIVE" and plan.get("accountPlanType") == "FREE",
        "Expected ACTIVE FREE test account; review changed plan before proceeding",
    )
    note("Account: " + ACCOUNT + " | Region: " + REGION + " | Stack: " + STACK)
    note("Preserves existing Essentials pool " + POOL_ID + "; repairs its failed backend client.")
    note("Client WriteAttributes: [name] -> [email, name]. Required email must be writable.")
    note(
        "Pool: require verification BEFORE an email update takes effe"
        "ct. Schema/sign-in method remain unchanged."
    )
    note(
        "Mandatory TOTP, invitation-only signup, confidential client "
        "and rotating 8-hour refresh sessions remain required."
    )
    note(
        "Sets a stack policy denying replacement/deletion of StaffPoo"
        "l. No pool recreation or automatic deletion."
    )
    note(
        "No users, invitations, sign-ins or new service tier. Existin"
        "g database costs continue; later Cognito usage may be charge"
        "able."
    )
    note(
        "Pricing: https://aws.amazon.com/cognito/pricing/ (reviewed 2"
        "026-09-22). No account-plan upgrade."
    )
    note(
        "Client secrets are not printed or saved. Application integra"
        "tion and updated backend audit/image remain pending."
    )
    stack = get_stack()
    if stack["StackStatus"] == "CREATE_FAILED":
        require(
            stack["_original_template"], "Failed stack no longer has the known original template"
        )
        recovery_inventory()
        with tempfile.TemporaryDirectory(prefix="fitfinity-cognito-recovery-") as directory:
            path = Path(directory) / "template.json"
            path.write_text(json.dumps(TEMPLATE))
            aws("cloudformation", "validate-template", "--template-body", "file://" + str(path))
            existing_policy = aws(
                "cloudformation", "get-stack-policy", "--stack-name", STACK_ID
            ).get("StackPolicyBody")
            require(
                not existing_policy or json.loads(existing_policy) == POOL_POLICY,
                "Existing stack policy needs review; refusing to overwrite it",
            )
            confirm()
            current = get_stack()
            require(
                current["StackStatus"] == "CREATE_FAILED" and current["_original_template"],
                "Stack changed during review",
            )
            recovery_inventory()
            REPORT["write_attempted"] = True
            aws(
                "cloudformation",
                "set-stack-policy",
                "--stack-name",
                STACK_ID,
                "--stack-policy-body",
                json.dumps(POOL_POLICY),
            )
            aws(
                "cloudformation",
                "update-stack",
                "--stack-name",
                STACK_ID,
                "--template-body",
                "file://" + str(path),
                "--parameters",
                "ParameterKey=SessionHours,UsePreviousValue=true",
                "--disable-rollback",
                "--client-request-token",
                "fitfinity-cognito-repair-" + TEMPLATE_SHA[:24],
            )
    else:
        require(
            not stack["_original_template"]
            and stack["StackStatus"]
            in {"UPDATE_IN_PROGRESS", "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS", "UPDATE_COMPLETE"},
            "Stack state requires separate review",
        )
        note("Resuming exact recovery; no new update request.")
    deadline = time.monotonic() + 1200
    while True:
        stack = get_stack()
        require(
            not stack["_original_template"],
            ("AWS has not exposed the recovery template yet; rerun to inspect before proceeding"),
        )
        status = stack["StackStatus"]
        REPORT.update(stack_id=stack["StackId"], status=status)
        note("CloudFormation: " + status)
        if status == "UPDATE_COMPLETE":
            break
        if status not in {"UPDATE_IN_PROGRESS", "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS"}:
            REPORT["failures"] = aws(
                "cloudformation",
                "describe-stack-events",
                "--stack-name",
                STACK_ID,
                "--query",
                (
                    "StackEvents[?contains(ResourceStatus, 'FAILED')].{Resource:L"
                    "ogicalResourceId,Status:ResourceStatus,Reason:ResourceStatus"
                    "Reason}"
                ),
            )
            raise RuntimeError(
                "Recovery needs review; resources are preserved. Upload the receipt."
            )
        require(
            time.monotonic() < deadline,
            "Wait timed out; AWS update may continue. Rerun to resume verification.",
        )
        time.sleep(15)
    policy = aws("cloudformation", "get-stack-policy", "--stack-name", STACK_ID).get(
        "StackPolicyBody", "{}"
    )
    require(json.loads(policy) == POOL_POLICY, "Pool replacement/deletion guard differs")
    verify(stack)
    note(
        "COGNITO PASSED — recovered settings verified. App integratio"
        "n, updated backend image and physical testing remain pending"
        "."
    )


def save():
    REPORT["checked_at"] = datetime.datetime.now(datetime.UTC).isoformat()
    folder = Path.home() / "Downloads"
    folder.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix="Fitfinity_AWS_Cognito_Execution_", suffix=".json", dir=folder
    )
    with os.fdopen(fd, "w") as stream:
        json.dump(REPORT, stream, indent=2)
        stream.write("\n")
    note("Receipt: " + name)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        REPORT["error"] = (
            str(error)
            if not isinstance(error, KeyboardInterrupt)
            else "Interrupted; AWS creation may continue"
        )
        note("STOPPED: " + REPORT["error"])
        note("No resources are automatically deleted. A submitted creation may still be running.")
        save()
        raise SystemExit(1) from None
    save()
