"""AuthenticationSecretOperator: explicit per-run dependencies and receipt state."""

import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import zlib
from pathlib import Path

from database_access import DatabaseAccessOperator
from operator_context import OperatorContext


class AuthenticationSecretOperator:
    def __init__(self, *, context=None, aws_call=None):
        self.context = context if context is not None else OperatorContext(aws_call=aws_call)
        self.ROOT = Path(__file__).resolve().parent
        self.db = DatabaseAccessOperator(context=self.context)
        self.CONTRACT = json.loads((self.ROOT / "test-auth-contract.json").read_text())
        self.MIGRATION = json.loads((self.ROOT / "test-db-migration-contract.json").read_text())
        self.SECRET_STACK = "fitfinity-test-auth-secret"
        self.PROBE_STACK = "fitfinity-test-auth-bootstrap"
        self.SECRET_NAME = "fitfinity/test/auth"
        self.TAGS = {"Application": "Fitfinity", "Environment": "test", "Purpose": "auth-secret-v1"}
        self.MODES = {"Setup": "auth-initialize", "Application": "auth-app-probe"}
        self.NAMES = {
            "Setup": "fitfinity-test-auth-initialize",
            "Application": "fitfinity-test-auth-app-probe",
        }
        if context is None:
            self.context.report.update(
                {
                    "operator_revision": "2026-09-25-auth-secret",
                    "account": self.db.ACCOUNT,
                    "region": self.db.REGION,
                    "image_digest": self.db.DIGEST,
                    "auth_secret_verified": False,
                    "managed_runtime_verified": False,
                    "temporary_cleanup_complete": False,
                    "owner_created": False,
                    "app_deployed": False,
                    "cloud_writes": [],
                }
            )
        self.db.context.reads = self.db.context.reads | {
            ("cognito-idp", "describe-user-pool"),
            ("cognito-idp", "describe-user-pool-client"),
            ("cognito-idp", "get-user-pool-mfa-config"),
        }
        self.db.context.writes = {
            ("cloudformation", "create-stack"),
            ("cloudformation", "delete-stack"),
            ("lambda", "invoke"),
        }
        self.require = self.db.require

    def source_bundle(self):
        def packed(name):
            return base64.b64encode(zlib.compress((self.ROOT / name).read_bytes(), 9)).decode()

        contract = {
            **self.CONTRACT,
            "tags": self.TAGS,
            "files": self.MIGRATION["files"],
            "migration_contract_sha256": self.db.canonical_hash(self.MIGRATION),
            "app_secret_arn": self.MIGRATION["secret_arns"]["app"],
        }
        manifest = base64.b64encode(zlib.compress(json.dumps(contract).encode(), 9)).decode()
        source = (
            "import base64, sys, types, zlib\n"
            "shared_module = types.ModuleType('fitfinity_db_shared')\n"
            f"exec(compile(zlib.decompress(base64.b64decode({packed('test-db-bootstrap.py')!r},"
            "validate=True)), 'fitfinity_db_shared', 'exec'),shared_module.__dict__)\n"
            "sys.modules['fitfinity_db_shared'] = shared_module\n"
            f"FITFINITY_AUTH_CONTRACT = zlib.decompress(base64.b64decode({manifest!r},"
            "validate=True)).decode()\n"
            f"exec(compile(zlib.decompress(base64.b64decode({packed('test-auth-bootstrap.py')!r},"
            "validate=True)), 'fitfinity_auth_bootstrap','exec'),globals())\n"
        )
        self.require(len(source.encode()) <= 32768, "Auth source exceeds loader budget")
        return source

    def secret_template(self):
        # No SecretString or GenerateSecretString: CFN creates an empty, retained container.
        # Only the private initializer can create the single reviewed current version.
        return {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Description": "Retained Fitfinity test authentication secret; initialized privately.",
            "Resources": {
                "AuthenticationSecret": {
                    "Type": "AWS::SecretsManager::Secret",
                    "DeletionPolicy": "Retain",
                    "UpdateReplacePolicy": "Retain",
                    "Properties": {
                        "Name": self.SECRET_NAME,
                        "Description": (
                            "Fitfinity test Cognito credential and session encryption key"
                        ),
                        "Tags": [{"Key": k, "Value": v} for k, v in self.TAGS.items()],
                    },
                }
            },
            "Outputs": {"AuthenticationSecretArn": {"Value": {"Ref": "AuthenticationSecret"}}},
        }

    def secret_state(self, row):
        self.require(
            row["StackStatus"] == "CREATE_COMPLETE"
            and row.get("EnableTerminationProtection") is True,
            "Authentication stack completion/protection differs",
        )
        ids = self.db.stack_inventory(row, self.secret_template(), successful=True)
        arn = ids["AuthenticationSecret"]
        self.require(
            {x["OutputKey"]: x["OutputValue"] for x in row.get("Outputs", [])}
            == {"AuthenticationSecretArn": arn},
            "Authentication output differs",
        )
        self.require(
            re.fullmatch(
                r"arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/auth-[A-Za-z0-9]{6}",
                arn,
            ),
            "Authentication ARN differs",
        )
        value = self.db.aws("secretsmanager", "describe-secret", "--secret-id", arn)
        self.require(
            value.get("ARN") == arn
            and value.get("Name") == self.SECRET_NAME
            and not value.get("DeletedDate")
            and not value.get("RotationEnabled")
            and not value.get("OwningService")
            and not value.get("ReplicationStatus")
            and value.get("KmsKeyId") in {None, "alias/aws/secretsmanager"},
            "Authentication metadata differs",
        )
        tags = {x["Key"]: x["Value"] for x in value.get("Tags", [])}
        self.require(
            all(tags.get(k) == v for k, v in self.TAGS.items()), "Authentication secret tags differ"
        )
        version = hashlib.sha256(("fitfinity-auth-initial-v1:" + arn).encode()).hexdigest()
        versions = value.get("VersionIdsToStages", {})
        self.require(
            versions in ({}, {version: ["AWSCURRENT"]}), "Authentication version drift; no rotation"
        )
        policy = self.db.aws("secretsmanager", "get-resource-policy", "--secret-id", arn)
        self.require(not policy.get("ResourcePolicy"), "Unexpected authentication resource policy")
        self.context.report.update(
            auth_secret_arn=arn,
            auth_secret_version_id=version,
            auth_secret_has_value=bool(versions),
        )
        return arn

    def cognito_review(self):
        result = self.db.aws(
            "cloudformation", "describe-stacks", "--stack-name", self.CONTRACT["cognito_stack_id"]
        )
        self.require(len(result["Stacks"]) == 1, "Cognito stack ambiguity")
        row = result["Stacks"][0]
        self.require(
            row["StackId"] == self.CONTRACT["cognito_stack_id"]
            and row["StackStatus"] == "UPDATE_COMPLETE"
            and row.get("EnableTerminationProtection") is True,
            "Accepted Cognito stack differs",
        )
        template = self.db.stack_template(row)
        self.require(
            self.db.canonical_hash(template) == self.CONTRACT["cognito_template_sha256"],
            "Cognito template changed",
        )
        ids = self.db.stack_inventory(row, template, successful=True)
        self.require(
            ids
            == {"StaffPool": self.CONTRACT["pool_id"], "StaffClient": self.CONTRACT["client_id"]},
            "Cognito resources differ",
        )
        self.require(
            {x["OutputKey"]: x["OutputValue"] for x in row["Outputs"]}
            == {"PoolId": self.CONTRACT["pool_id"], "ClientId": self.CONTRACT["client_id"]},
            "Cognito outputs differ",
        )
        pool = self.db.aws(
            "cognito-idp", "describe-user-pool", "--user-pool-id", self.CONTRACT["pool_id"]
        )["UserPool"]
        expected = template["Resources"]["StaffPool"]["Properties"]
        for key in (
            "UserPoolTier",
            "DeletionProtection",
            "UsernameAttributes",
            "UsernameConfiguration",
            "AutoVerifiedAttributes",
            "MfaConfiguration",
            "AccountRecoverySetting",
            "UserAttributeUpdateSettings",
        ):
            self.require(pool.get(key) == expected[key], "Cognito pool setting differs: " + key)
        self.require(
            pool.get("Id") == self.CONTRACT["pool_id"]
            and pool.get("Name") == "fitfinity-test-cognito-staff"
            and pool.get("AdminCreateUserConfig", {}).get("AllowAdminCreateUserOnly") is True
            and not pool.get("DeviceConfiguration")
            and not pool.get("LambdaConfig")
            and not pool.get("Domain")
            and not pool.get("CustomDomain"),
            "Cognito identity/signup/device differs",
        )
        policy = pool.get("Policies", {}).get("PasswordPolicy", {})
        self.require(
            all(policy.get(k) == v for k, v in expected["Policies"]["PasswordPolicy"].items()),
            "Cognito password policy differs",
        )
        mfa = self.db.aws(
            "cognito-idp", "get-user-pool-mfa-config", "--user-pool-id", self.CONTRACT["pool_id"]
        )
        self.require(
            mfa.get("MfaConfiguration") == "ON"
            and mfa.get("SoftwareTokenMfaConfiguration", {}).get("Enabled") is True
            and not mfa.get("SmsMfaConfiguration")
            and not mfa.get("EmailMfaConfiguration"),
            "Cognito MFA differs",
        )
        desired = template["Resources"]["StaffClient"]["Properties"]
        keys = sorted(
            set(desired) - {"GenerateSecret"}
            | {
                "ClientId",
                "AllowedOAuthFlowsUserPoolClient",
                "CallbackURLs",
                "LogoutURLs",
                "SupportedIdentityProviders",
            }
        )
        query = (
            "UserPoolClient.{"
            + ",".join(k + ":" + k for k in keys)
            + ',HasClientSecret:ClientSecret != `null` && ClientSecret != `""`}'
        )
        response = self.db.aws(
            "cognito-idp",
            "describe-user-pool-client",
            "--user-pool-id",
            self.CONTRACT["pool_id"],
            "--client-id",
            self.CONTRACT["client_id"],
            "--query",
            query,
        )
        self.require(
            "ClientSecret" not in response
            and response.get("HasClientSecret") is True
            and response.get("ClientId") == self.CONTRACT["client_id"]
            and response.get("UserPoolId") == self.CONTRACT["pool_id"],
            "Cognito client differs",
        )
        for key, value in desired.items():
            if key in {"GenerateSecret", "UserPoolId"}:
                continue
            if key == "RefreshTokenValidity":
                value = 8
            self.require(response.get(key) == value, "Cognito client setting differs: " + key)
        self.require(
            not response.get("AllowedOAuthFlowsUserPoolClient")
            and not response.get("CallbackURLs")
            and not response.get("LogoutURLs")
            and response.get("SupportedIdentityProviders") in (None, [], ["COGNITO"]),
            "Unexpected OAuth/provider",
        )
        self.context.report["cognito_configuration_verified"] = True

    def credentials_review(self):
        expected = json.loads((self.ROOT / "test-db-access.json").read_text())
        row = self.db.owned_stack(self.db.SECRETS_STACK, expected)
        self.require(
            row
            and row["StackId"]
            == (
                "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-db-access/"
                "3ec5d530-b890-11f1-b0be-0ab91b93bd7d"
            )
            and row["StackStatus"] == "CREATE_COMPLETE"
            and row.get("EnableTerminationProtection") is True,
            "Database credential stack differs",
        )
        self.db.stack_inventory(row, expected, successful=True)
        self.require(
            self.db.credentials(row) == self.MIGRATION["secret_arns"],
            "Database credential identities differ",
        )

    def probe_template(self, arn, source):
        result = self.db.probe_template(self.MIGRATION["secret_arns"], source=source.encode())
        result["Description"] = (
            "Temporary private authentication secret "
            "initializer and independent managed-runtime proof."
        )
        pool_arn = (
            f"arn:aws:cognito-idp:{self.db.REGION}:{self.db.ACCOUNT}:"
            f"userpool/{self.CONTRACT['pool_id']}"
        )
        for prefix, mode in self.MODES.items():
            name = self.NAMES[prefix]
            resources = result["Resources"]
            properties = resources[prefix + "Function"]["Properties"]
            properties["FunctionName"] = name
            env = {
                k: v
                for k, v in properties["Environment"]["Variables"].items()
                if k.startswith("AWS_LWA_")
            }
            env.update(FITFINITY_DB_ACCESS_MODE=mode, FITFINITY_AUTH_SECRET_ARN=arn)
            if prefix == "Application":
                env.update(
                    FITFINITY_CONFIG_SOURCE="aws-secrets-manager",
                    FITFINITY_ENVIRONMENT="staging",
                    FITFINITY_AWS_ACCOUNT_ID=self.db.ACCOUNT,
                    FITFINITY_DATABASE_SECRET_ARN=self.MIGRATION["secret_arns"]["app"],
                    FITFINITY_DB_HOST=self.db.HOST,
                    FITFINITY_DB_NAME="fitfinity",
                    FITFINITY_AUTH_ENABLED="true",
                    FITFINITY_COGNITO_POOL_ID=self.CONTRACT["pool_id"],
                    FITFINITY_COGNITO_CLIENT_ID=self.CONTRACT["client_id"],
                    FITFINITY_ALLOWED_HOSTS='["bootstrap.invalid"]',
                    FITFINITY_AUTH_ORIGINS='["https://bootstrap.invalid"]',
                    FITFINITY_AUTH_COOKIE_SECURE="true",
                    FITFINITY_STAFF_INVITATIONS_ENABLED="false",
                )
            properties["Environment"]["Variables"] = env
            log_name = "/aws/lambda/" + name
            resources[prefix + "Logs"]["Properties"]["LogGroupName"] = log_name
            statements = resources[prefix + "Role"]["Properties"]["Policies"][0]["PolicyDocument"][
                "Statement"
            ]
            statements[0]["Resource"] = [arn] + (
                [self.MIGRATION["secret_arns"]["app"]] if prefix == "Application" else []
            )
            statements[1]["Resource"] = (
                f"arn:aws:logs:{self.db.REGION}:{self.db.ACCOUNT}:log-group:{log_name}:*"
            )
            statements[3]["Condition"]["ArnEquals"]["lambda:SourceFunctionArn"] = (
                f"arn:aws:lambda:{self.db.REGION}:{self.db.ACCOUNT}:function:{name}"
            )
            statements.append(
                {"Effect": "Allow", "Action": ["secretsmanager:DescribeSecret"], "Resource": [arn]}
            )
            statements.append(
                {
                    "Effect": "Allow",
                    "Action": [
                        "cognito-idp:DescribeUserPool",
                        "cognito-idp:DescribeUserPoolClient",
                        "cognito-idp:GetUserPoolMfaConfig",
                    ],
                    "Resource": [pool_arn],
                }
            )
            if prefix == "Setup":
                statements.append(
                    {
                        "Effect": "Allow",
                        "Action": ["secretsmanager:PutSecretValue"],
                        "Resource": [arn],
                    }
                )
            self.db.configuration_sizes(properties)
        self.require(
            self.db.ADMIN_ARN not in json.dumps(result)
            and self.MIGRATION["secret_arns"]["migration"] not in json.dumps(result),
            "Excess database access",
        )
        return result

    def before_secret(self):
        row = self.db.owned_stack(self.SECRET_STACK, self.secret_template(), tags=self.TAGS)
        if row:
            self.require(
                row["StackStatus"] in {"CREATE_IN_PROGRESS", "CREATE_COMPLETE"}
                and row.get("EnableTerminationProtection") is True,
                "Authentication stack requires review",
            )
            if row["StackStatus"] == "CREATE_COMPLETE":
                self.secret_state(row)
        else:
            self.require(
                self.db.aws(
                    "secretsmanager",
                    "describe-secret",
                    "--secret-id",
                    self.SECRET_NAME,
                    missing=True,
                )
                is None,
                "Authentication secret exists outside the reviewed stack",
            )
        return row

    def before_probe(self, expected=None):
        row = self.db.owned_stack(self.PROBE_STACK, expected, tags=self.TAGS)
        if row:
            self.require(
                expected is not None
                and row["StackStatus"] in {"CREATE_IN_PROGRESS", "CREATE_COMPLETE"},
                "Auth probe requires review",
            )
        else:
            for name in self.NAMES.values():
                self.require(
                    self.db.aws("lambda", "get-function", "--function-name", name, missing=True)
                    is None,
                    "Auth function already exists",
                )
                logs = self.db.aws(
                    "logs", "describe-log-groups", "--log-group-name-prefix", "/aws/lambda/" + name
                )
                self.require(
                    not any(
                        x["logGroupName"] == "/aws/lambda/" + name
                        for x in logs.get("logGroups", [])
                    ),
                    "Auth log group already exists",
                )
        return row

    def confirmation(self):
        start = time.monotonic()
        with open("/dev/tty", "w") as terminal:
            terminal.write(
                "To create/verify the authentication "
                "secret and remove successful temporary probes, "
                f"type {self.db.ACCOUNT}: "
            )
            terminal.flush()
        with open("/dev/tty") as terminal:
            self.require(
                terminal.readline().strip() == self.db.ACCOUNT, "Confirmation differs; no writes"
            )
        self.require(time.monotonic() - start < 600, "Preview expired")

    def validate_proof(self, proof, arn, *, application):
        version = hashlib.sha256(("fitfinity-auth-initial-v1:" + arn).encode()).hexdigest()
        self.require(
            proof.get("secret_version_id") == version
            and proof.get("auth_secret_verified") is True
            and proof.get("encryption_verified") is True
            and proof.get("cognito_checks") == 18,
            "Authentication proof differs",
        )
        if application:
            self.require(
                proof.get("managed_settings_verified") is True
                and proof.get("database_read_only") is True
                and proof.get("target_revision") == "20260924_0006"
                and proof.get("user") == "fitfinity_app"
                and proof.get("database") == "fitfinity"
                and proof.get("sslmode") == "verify-full"
                and proof.get("tls") in {"TLSv1.2", "TLSv1.3"}
                and 170000 <= proof.get("server_version_num", 0) < 180000,
                "Managed runtime/database proof differs",
            )

    def main(self):
        self.require(not sys.argv[1:], "Usage: no arguments")
        self.db.note(
            "Fitfinity AWS — authentication secret and independent runtime settings verification"
        )
        source = self.source_bundle()
        self.db.environment()
        storage = self.db.network()
        self.db.scan()
        self.db.costs(*storage, authentication=True)
        self.cognito_review()
        self.credentials_review()
        before = self.before_secret()
        self.before_probe(
            self.probe_template(self.secret_state(before), source)
            if before and before["StackStatus"] == "CREATE_COMPLETE"
            else None
        )
        self.db.note(
            "Creates one retained, deletion-protected "
            "auth secret and six temporary private resources."
        )
        self.db.note(
            "Initializes one session-encryption key and copies the existing Cognito credential "
            "entirely inside AWS."
        )
        self.db.note(
            "Reruns verify the same version; no key rotation. Independent "
            "managed-settings and read-only TLS/database proof."
        )
        self.db.note(
            "Deletes only the temporary stack after both proofs. No users, "
            "invitations or app deployment."
        )
        self.confirmation()
        self.db.environment()
        self.require(self.db.network() == storage, "Storage changed after quote")
        self.db.scan()
        self.cognito_review()
        self.credentials_review()
        after = self.before_secret()
        self.require(
            (before is None and after is None)
            or (before and after and before["StackId"] == after["StackId"]),
            "Auth stack changed after preview",
        )
        self.db.context.write_allowed = True
        with tempfile.TemporaryDirectory(prefix="fitfinity-auth-") as temp:
            directory = Path(temp)
            secret_row = self.db.provision(
                self.SECRET_STACK, self.secret_template(), directory, tags=self.TAGS, protect=True
            )
            arn = self.secret_state(secret_row)
            expected = self.probe_template(arn, source)
            self.before_probe(expected)
            self.context.report["bootstrap_source_sha256"] = hashlib.sha256(
                source.encode()
            ).hexdigest()
            self.context.report["bootstrap_configuration_bytes"] = {
                p: self.db.configuration_sizes(expected["Resources"][p + "Function"]["Properties"])
                for p in self.MODES
            }
            row = self.db.provision(self.PROBE_STACK, expected, directory, tags=self.TAGS)
            self.db.verify_functions(row, expected)
            for prefix, mode in self.MODES.items():
                proof = self.db.invoke(
                    self.NAMES[prefix], mode, directory, preflight=True, source=source
                )
                self.context.report.setdefault("runtime_preflight", {})[mode] = proof
                self.require(
                    proof.get("ok") is True
                    and proof.get("image_files_sha256")
                    == self.db.canonical_hash(self.MIGRATION["files"]),
                    "Authentication preflight failed; see receipt",
                )
            self.context.report["initialization_attempted"] = True
            self.context.report["initialization_status"] = "unknown_until_verified"
            proof = self.db.invoke(
                self.NAMES["Setup"], self.MODES["Setup"], directory, source=source
            )["proof"]
            self.context.report["initialization_proof"] = proof
            self.validate_proof(proof, arn, application=False)
            self.context.report.update(auth_secret_verified=True, initialization_status="verified")
            self.db.verify_functions(row, expected)
            proof = self.db.invoke(
                self.NAMES["Application"], self.MODES["Application"], directory, source=source
            )["proof"]
            self.context.report["application_proof"] = proof
            self.validate_proof(proof, arn, application=True)
            self.context.report["managed_runtime_verified"] = True
            self.secret_state(
                self.db.owned_stack(self.SECRET_STACK, self.secret_template(), tags=self.TAGS)
            )
            self.db.cleanup(row, expected, name=self.PROBE_STACK, tags=self.TAGS)
        self.db.note(
            "AUTHENTICATION SECRET PASSED — retained secret verified; temporary stack removed."
        )
        self.db.note("First Owner and application deployment remain pending.")

    def save(self):
        self.context.report["checked_at"] = self.db.dt.datetime.now(self.db.dt.UTC).isoformat()
        folder = Path.home() / "Downloads"
        folder.mkdir(exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix="Fitfinity_AWS_Auth_Secret_", suffix=".json", dir=folder
        )
        with os.fdopen(descriptor, "w") as stream:
            json.dump(self.context.report, stream, indent=2)
        self.db.note("Receipt: " + name)

    def run(self):
        try:
            self.main()
        except (Exception, KeyboardInterrupt) as error:
            self.context.report["error"] = (
                str(error) if isinstance(error, RuntimeError) else type(error).__name__
            )
            self.db.note("STOPPED: " + self.context.report["error"])
            self.db.note(
                "Resources preserved. If initialization "
                "started, its outcome requires verification; "
                "do not rotate keys."
            )
            self.save()
            raise SystemExit(1) from None
        self.save()
