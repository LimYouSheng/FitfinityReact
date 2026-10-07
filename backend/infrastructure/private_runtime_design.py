"""Compose a temporary current-image probe using the existing template and proof owners."""

import base64
import hashlib
import json
import zlib
from pathlib import Path

import database_templates
import private_runtime_preflight as preflight
from authentication_secrets import AuthenticationSecretOperator
from operator_context import OperatorContext

ROOT = Path(__file__).parent
STACK = "fitfinity-test-current-runtime"
NAMES = {"Setup": "fitfinity-test-runtime-a", "Application": "fitfinity-test-runtime-b"}
POLICY = "FitfinityCurrentRuntime"
REVISION = "2026-10-07-private-runtime-1"
PREVIOUS_REVISION = "2026-10-04-current-runtime-1"
FAILED_RECEIPT_SHA256 = "8ea3724a5b0b0c806e51ff4fa5d6ba25d6c057aeb04d0d5a5ab11e329bd41253"
MARKER = "Fitfinity_AWS_Current_Runtime_2026-10-04"
require = preflight.require


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def source_bundle():
    auth = AuthenticationSecretOperator(context=OperatorContext())
    contract = json.loads((ROOT / "private-runtime-contract.json").read_text())
    approval = preflight.binding.local_approval()
    contract.update(
        authorized_at=approval["approved_at"],
        expires_at=approval["expires_at"],
        function_names=list(NAMES.values()),
        image_digest=preflight.binding.DIGEST,
        auth_secret_arn=preflight.deploy.CONFIG["auth_secret"],
    )
    require(bool(contract["files"]) and bool(contract["dependencies"]), "Missing runtime inventory")
    packed = base64.b64encode(zlib.compress(auth.source_bundle().encode(), 9)).decode()
    source = (
        "import base64, types, zlib\n" + f"FITFINITY_CURRENT_CONTRACT = {json.dumps(contract)!r}\n"
        "def load_auth_proof():\n"
        "    module = types.ModuleType('fitfinity_current_auth_proof')\n"
        f"    exec(compile(zlib.decompress(base64.b64decode({packed!r})), "
        "'accepted_auth_helpers', 'exec'), module.__dict__)\n"
        "    return module\n" + (ROOT / "private_runtime_probe.py").read_text()
    )
    require(len(source.encode()) <= 32768, "Current probe exceeds loader transport budget")
    return source, contract


def template(source):
    auth = AuthenticationSecretOperator(context=OperatorContext())
    db = auth.db
    image = preflight.binding.URI + "@" + preflight.binding.DIGEST
    result = database_templates.probe_template(
        auth.MIGRATION["secret_arns"],
        source=source.encode(),
        account=db.ACCOUNT,
        admin_arn=db.ADMIN_ARN,
        app_sg=db.APP_SG,
        image=image,
        migration_sg=db.MIGRATION_SG,
        region=db.REGION,
        root=db.ROOT,
        subnet_a=db.SUBNET_A,
        subnet_b=db.SUBNET_B,
        check_sizes=db.configuration_sizes,
    )
    result["Description"] = (
        "Temporary private Fitfinity current-image runtime "
        "verification. No public API or Owner creation."
    )
    for prefix, name in NAMES.items():
        resources = result["Resources"]
        props = resources[prefix + "Function"]["Properties"]
        arn = f"arn:aws:lambda:{db.REGION}:{db.ACCOUNT}:function:{name}"
        logs = "/aws/lambda/" + name
        props["FunctionName"] = name
        props["VpcConfig"]["SecurityGroupIds"] = [db.APP_SG]
        props["Environment"]["Variables"] = {
            "AWS_LWA_PASS_THROUGH_PATH": "/events",
            "AWS_LWA_PORT": "8080",
            "AWS_LWA_READINESS_CHECK_PATH": "/health/live",
            "AWS_LWA_READINESS_CHECK_HEALTHY_STATUS": "200",
            "FITFINITY_CONFIG_SOURCE": "aws-secrets-manager",
            "FITFINITY_ENVIRONMENT": "staging",
            "FITFINITY_AWS_ACCOUNT_ID": db.ACCOUNT,
            "FITFINITY_DATABASE_SECRET_ARN": auth.MIGRATION["secret_arns"]["app"],
            "FITFINITY_AUTH_SECRET_ARN": preflight.deploy.CONFIG["auth_secret"],
            "FITFINITY_DB_HOST": db.HOST,
            "FITFINITY_DB_NAME": "fitfinity",
            "FITFINITY_AUTH_ENABLED": "true",
            "FITFINITY_COGNITO_POOL_ID": auth.CONTRACT["pool_id"],
            "FITFINITY_COGNITO_CLIENT_ID": auth.CONTRACT["client_id"],
            "FITFINITY_ALLOWED_HOSTS": '["runtime.invalid"]',
            "FITFINITY_AUTH_ORIGINS": '["https://runtime.invalid"]',
            "FITFINITY_AUTH_COOKIE_SECURE": "true",
            "FITFINITY_STAFF_INVITATIONS_ENABLED": "false",
            "FITFINITY_DB_POOL_SIZE": "1",
        }
        resources[prefix + "Logs"]["Properties"]["LogGroupName"] = logs
        resources[prefix + "Role"]["Properties"]["PermissionsBoundary"] = (
            "arn:aws:iam::418638389566:policy/fitfinity-test-private-runtime-boundary"
        )
        policy = resources[prefix + "Role"]["Properties"]["Policies"][0]
        policy["PolicyName"] = POLICY
        statements = policy["PolicyDocument"]["Statement"]
        statements[0]["Resource"] = [
            auth.MIGRATION["secret_arns"]["app"],
            preflight.deploy.CONFIG["auth_secret"],
        ]
        statements[1]["Resource"] = f"arn:aws:logs:{db.REGION}:{db.ACCOUNT}:log-group:{logs}:*"
        statements[3]["Condition"]["ArnEquals"]["lambda:SourceFunctionArn"] = arn
        statements.append(
            {
                "Effect": "Allow",
                "Action": ["secretsmanager:DescribeSecret"],
                "Resource": preflight.deploy.CONFIG["auth_secret"],
            }
        )
        statements.append(
            {
                "Effect": "Allow",
                "Action": [
                    "cognito-idp:DescribeUserPool",
                    "cognito-idp:DescribeUserPoolClient",
                    "cognito-idp:GetUserPoolMfaConfig",
                ],
                "Resource": (
                    f"arn:aws:cognito-idp:{db.REGION}:{db.ACCOUNT}:"
                    f"userpool/{auth.CONTRACT['pool_id']}"
                ),
            }
        )
        db.configuration_sizes(props)
    serialized = json.dumps(result)
    require(
        db.ADMIN_ARN not in serialized
        and auth.MIGRATION["secret_arns"]["migration"] not in serialized,
        "Temporary runtime must not access administrator/migration secrets",
    )
    require(len(serialized.encode()) <= 51200, "Template exceeds inline budget")
    return result


def validate_result(value, *, nonce, action, contract):
    require(value.get("nonce") == nonce, "Runtime response nonce differs")
    if value.get("ok") is not True:
        raise RuntimeError(
            "Runtime proof failed at "
            + str(value.get("stage"))
            + "; preserve receipt and resources"
        )
    require(
        value.get("action") == action
        and value.get("image_digest") == contract["image_digest"]
        and value.get("revision") == contract["revision"]
        and value.get("stage") == "complete"
        and value.get("source_files_verified") == len(contract["files"])
        and value.get("dependencies_verified") == len(contract["dependencies"])
        and value.get("runtime_identity") in [[993, 993, 990, 990], [10001] * 4],
        "Runtime source/identity evidence differs",
    )
    if action == "current-runtime":
        proof = value.get("proof", {})
        auth = AuthenticationSecretOperator(context=OperatorContext())
        auth.validate_proof(proof, contract["auth_secret_arn"], application=True)
        require(
            value.get("jwks_reachable") is True
            and 1 <= value.get("jwks_key_count", 0) <= 8
            and value.get("application_startup_verified") is True
            and value.get("application_shutdown_verified") is True
            and (
                value.get("liveness_status"),
                value.get("readiness_status"),
                value.get("untrusted_host_status"),
            )
            == (200, 200, 400),
            "Application health/JWKS proof differs",
        )
