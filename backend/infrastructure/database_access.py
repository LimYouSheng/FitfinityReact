"""DatabaseAccessOperator: explicit per-run dependencies and receipt state."""

import base64
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import database_review
import database_templates
from operator_checks import one, require
from operator_context import OperatorContext


class DatabaseAccessOperator:
    def __init__(self, *, context=None, aws_call=None):
        self.context = context if context is not None else OperatorContext(aws_call=aws_call)
        self.ACCOUNT = "418638389566"
        self.REGION = "ap-southeast-1"
        self.PROFILE = "fitfinity-test"
        self.FOUNDATION = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-tes"
            "t-foundation/6b51b020-b65f-11f1-82ee-0a2a8f1e9b2d"
        )
        self.VPC = "vpc-0b55320bb1a054441"
        self.HOST = "fitfinity-test-db.c1ak66620gza.ap-southeast-1.rds.amazonaws.com"
        self.ADMIN_ARN = (
            "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:rds!db-06e1f"
            "fee-8cb6-422d-96d2-f941519d6a9d-f2CW3j"
        )
        self.APP_SG = "sg-09bcb69b70968f702"
        self.MIGRATION_SG = "sg-0e900a9be9ca081a8"
        self.DB_SG = "sg-02e32d9cff9e4e8b6"
        self.SUBNET_A = "subnet-0a6ea67e00f370997"
        self.SUBNET_B = "subnet-0fcdf32ab544f1207"
        self.DIGEST = "sha256:efa53edd08c54786bb7e04cc2509b6ace31ff903d1a2c473f203548b2e4d6d12"
        self.IMAGE = (
            f"{self.ACCOUNT}.dkr.ecr.{self.REGION}.amazonaws.com/fitfinity-test-api@{self.DIGEST}"
        )
        self.SECRETS_STACK = "fitfinity-test-db-access"
        self.PROBE_STACK = "fitfinity-test-db-bootstrap"
        self.REVIEWED_PROBE_ID = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/"
            "fitfinity-test-db-bootstrap/4f92faf0-b890-11f1-8866-066e2b180577"
        )
        self.PREVIOUS_TEMPLATE_SHA256 = (
            "9c2a025c81c26e93de49526cebe7ca08f91508914dc78d574fc41c8da9392d15"
        )
        self.FAILED_TEMPLATE_SHA256 = (
            "9ee4c2ae78d1ed4c87cd27e2263ffca243c33f58e3c6302b4549e9a6846c2c2c"
        )
        self.TRANSPORT_TEMPLATE_SHA256 = (
            "ae592c424ff6cb6d8e090a2974e6295722cd87c652d3de37d5de6f39932c79f2"
        )
        self.IDENTITY_TEMPLATE_SHA256 = (
            "1768b444cc695fc41e3af6ed764ebf3dd0d4a5193fef06d10bf3e519a37c0265"
        )
        self.CLIENT_TEMPLATE_SHA256 = (
            "42dedd7436d7aa4efe9613f1331993cdca90b1ba65647d3620cfec7efab6c2e3"
        )
        self.DIAGNOSTIC_TEMPLATE_SHA256 = (
            "88064cbb2703b61874e482bb9fdeaff9af4b4839e65d37bcdc5777b821fb33a9"
        )
        self.REVIEWED_CONFIG_HASHES = {
            "Setup": {
                "27add2c158f6baf0a31a337cae91d99633497b2c6eecd55e1ba601b80c4f5e87",
                "5ff2345878f8c28234cdef9c15b19fbc1a416259ae1960d3c8b7d79013999172",
            },
            "Application": {
                "803734f4b4d4723a06d99123a429cd62accac3a5e35fc84873c34f21adb40cb0",
                "b95e1a69b01d3ec8b64bf4c99478d5cb8c251f1bb28f3d068d359ecf53c9e2d1",
            },
        }
        self.STABLE_CONFIG_HASHES = {
            "Setup": {"27add2c158f6baf0a31a337cae91d99633497b2c6eecd55e1ba601b80c4f5e87"},
            "Application": {"803734f4b4d4723a06d99123a429cd62accac3a5e35fc84873c34f21adb40cb0"},
        }
        self.RETAINED_FAILURE_TIMES = {
            "ApplicationFunction": "2026-09-25T05:57:53.221000+00:00",
            "SetupFunction": "2026-09-25T05:57:53.252000+00:00",
        }
        self.REVIEWED_PHYSICAL_RESOURCES = {
            "ApplicationFunction": "fitfinity-test-db-app-probe",
            "ApplicationLogs": "/aws/lambda/fitfinity-test-db-app-probe",
            "ApplicationRole": "fitfinity-test-db-bootstrap-ApplicationRole-NF8mXUbui3by",
            "SetupFunction": "fitfinity-test-db-setup",
            "SetupLogs": "/aws/lambda/fitfinity-test-db-setup",
            "SetupRole": "fitfinity-test-db-bootstrap-SetupRole-VvysP0EEFXFJ",
        }
        self.RECOVERY_OPERATIONS = {
            ("cloudformation", "rollback-stack"),
            ("cloudformation", "continue-update-rollback"),
        }
        self.REQUEST_SIZE_ERROR = (
            "Request must be smaller than 5120 bytes for the UpdateFunctionConfiguration operation"
        )
        self.TAGS = {
            "Application": "Fitfinity",
            "Environment": "test",
            "Purpose": "database-access-v1",
        }
        self.EXPIRY = dt.datetime(2026, 9, 29, 15, 59, tzinfo=dt.UTC)
        self.ROOT = Path(__file__).resolve().parent
        if context is None:
            self.context.report.update(
                {
                    "operator_revision": "2026-09-25-rds-tls-verification",
                    "account": self.ACCOUNT,
                    "region": self.REGION,
                    "image_digest": self.DIGEST,
                    "database_access_verified": False,
                    "temporary_cleanup_complete": False,
                    "app_deployed": False,
                    "migrations_applied": False,
                    "owner_created": False,
                    "auth_secret_created": False,
                    "cloud_writes": [],
                }
            )
        self.context.reads = {
            ("sts", "get-caller-identity"),
            ("freetier", "get-account-plan-state"),
            ("cloudformation", "describe-stacks"),
            ("cloudformation", "get-template"),
            ("cloudformation", "list-stack-resources"),
            ("cloudformation", "describe-stack-events"),
            ("cloudformation", "validate-template"),
            ("rds", "describe-db-instances"),
            ("rds", "describe-db-parameters"),
            ("ec2", "describe-security-groups"),
            ("ec2", "describe-subnets"),
            ("ec2", "describe-route-tables"),
            ("ec2", "describe-instances"),
            ("ec2", "describe-volumes"),
            ("secretsmanager", "describe-secret"),
            ("secretsmanager", "get-resource-policy"),
            ("pricing", "get-products"),
            ("ecr", "describe-image-scan-findings"),
            ("lambda", "get-function"),
            ("lambda", "get-policy"),
            ("lambda", "get-function-url-config"),
            ("lambda", "list-event-source-mappings"),
            ("iam", "get-role"),
            ("iam", "list-role-policies"),
            ("iam", "get-role-policy"),
            ("iam", "list-attached-role-policies"),
            ("logs", "describe-log-groups"),
        }
        self.context.writes = {
            ("cloudformation", "create-stack"),
            ("cloudformation", "update-stack"),
            ("cloudformation", "delete-stack"),
            ("cloudformation", "update-termination-protection"),
            ("lambda", "invoke"),
        } | self.RECOVERY_OPERATIONS

    require = staticmethod(require)

    def note(self, message):
        print(message, flush=True)

    def aws(self, service, operation, *args, region=None, missing=False):
        if region is None:
            region = self.REGION
        pair = (service, operation)
        self.require(
            pair in self.context.reads or pair in self.context.writes,
            "Operation outside this operator's scope",
        )
        self.require(
            pair not in self.context.writes or self.context.write_allowed,
            "Write attempted before execution confirmation",
        )
        if pair in self.RECOVERY_OPERATIONS:
            self.require(
                self.context.report.get("recovery_only") is True,
                "Rollback requires explicit recovery mode",
            )
            self.require(
                "--stack-name" in args
                and args[args.index("--stack-name") + 1] == self.REVIEWED_PROBE_ID,
                "Rollback is restricted to the reviewed temporary stack",
            )
            allowed_flags = {"--stack-name", "--client-request-token"}
            if operation == "continue-update-rollback":
                allowed_flags.add("--resources-to-skip")
                self.require(
                    "--resources-to-skip" in args, "Recovery requires verified resource selection"
                )
                at = args.index("--resources-to-skip") + 1
                selected = []
                while at < len(args) and not args[at].startswith("--"):
                    selected.append(args[at])
                    at += 1
                self.require(
                    selected
                    and len(selected) == len(set(selected))
                    and set(selected) <= {"SetupFunction", "ApplicationFunction"},
                    "Recovery may skip only the two reviewed functions",
                )
            self.require(
                {arg for arg in args if arg.startswith("--")} <= allowed_flags,
                "Unexpected recovery option",
            )
        if pair in self.context.writes and self.context.report.get("recovery_only"):
            self.require(
                pair in self.RECOVERY_OPERATIONS,
                "Recovery mode cannot update, invoke, create or delete",
            )
        if pair in self.context.writes and self.context.report.get("diagnostic_only"):
            self.require(
                pair in {("cloudformation", "update-stack"), ("lambda", "invoke")},
                "Diagnostic mode cannot create or delete resources",
            )
            if pair == ("lambda", "invoke"):
                request = json.loads(args[args.index("--payload") + 1])
                self.require(
                    json.loads(request["body"]).get("action") == "preflight",
                    "Diagnostic mode permits only preflight invocation",
                )
        if pair == ("cloudformation", "update-stack"):
            rollback_flags = {"--disable-rollback", "--no-disable-rollback"} & set(args)
            self.require(
                "--stack-name" in args
                and args[args.index("--stack-name") + 1] == self.REVIEWED_PROBE_ID
                and len(rollback_flags) == 1,
                "Update is restricted to the reviewed temporary stack",
            )
            if "--no-disable-rollback" in args:
                review = self.context.report.get("retained_rollback_review", {})
                self.require(
                    self.context.report.get("preview_update_rollback_enabled") is True
                    and review.get("stack_id") == self.REVIEWED_PROBE_ID
                    and review.get("state") == "UPDATE_ROLLBACK_COMPLETE"
                    and review.get("live_template_sha256") == self.PREVIOUS_TEMPLATE_SHA256,
                    "Enabled rollback requires the reviewed retained-failure baseline and preview",
                )
        if pair in self.context.writes:
            self.context.report["cloud_writes"].append({"service": service, "operation": operation})
        if self.context.aws_call is not None:
            return self.context.aws_call(service, operation, *args, region=region, missing=missing)
        command = [
            "aws",
            service,
            operation,
            "--profile",
            self.PROFILE,
            "--region",
            region,
            "--output",
            "json",
            "--no-cli-pager",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "150",
            *args,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=190)
        if result.returncode:
            error = result.stderr
            absent = "ResourceNotFoundException" in error or (
                service == "cloudformation"
                and "ValidationError" in error
                and "does not exist" in error
            )
            if missing and absent:
                return None
            if any(
                word in error.lower()
                for word in ["session has expired", "reauthenticate", "authorization grant"]
            ):
                raise RuntimeError("AWS session expired. Run: aws login --profile fitfinity-test")
            match = re.search(r"\(([A-Za-z0-9]+)\) when calling", error)
            # These reviewed stack requests contain no credentials or secret values.
            # Preserve the single service explanation, not raw CLI/debug output.
            detail = re.search(r"when calling the [A-Za-z]+ operation: ([^\r\n]+)", error)
            if (
                service == "cloudformation"
                and operation in {"update-stack", "rollback-stack", "continue-update-rollback"}
                and detail
            ):
                message = detail.group(1)[:1500]
                self.context.report["cloudformation_rejection"] = {
                    "operation": operation,
                    "code": match.group(1) if match else "CLI error",
                    "message": message,
                }
                raise RuntimeError(f"{service} {operation}: {message}")
            raise RuntimeError(
                f"{service} {operation} failed "
                f"({match.group(1) if match else 'CLI error'}); raw output omitted"
            )
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def environment(self):
        forbidden = {
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_SECURITY_TOKEN",
            "AWS_ROLE_ARN",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
            "AWS_CONFIG_FILE",
            "AWS_SHARED_CREDENTIALS_FILE",
            "AWS_CA_BUNDLE",
        }
        self.require(
            not any(
                value and (key in forbidden or key.startswith("AWS_ENDPOINT_URL"))
                for key, value in os.environ.items()
            ),
            "Remove AWS credential/config/endpoint/CA overrides",
        )
        os.environ.update(
            AWS_PAGER="",
            AWS_CLI_AUTO_PROMPT="off",
            AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
            AWS_MAX_ATTEMPTS="2",
        )
        identity = self.aws("sts", "get-caller-identity")
        self.require(
            identity.get("Account") == self.ACCOUNT
            and identity.get("Arn") == f"arn:aws:iam::{self.ACCOUNT}:user/fitfinity-deployer",
            "Expected fitfinity-deployer identity was not verified",
        )
        plan = self.aws("freetier", "get-account-plan-state", region="us-east-1")
        self.context.report["plan"] = plan
        self.require(
            plan.get("accountPlanType") == "FREE" and plan.get("accountPlanStatus") == "ACTIVE",
            "Account plan changed; review required",
        )

    def owned_stack(self, name, template=None, *, tags=None):
        result = self.aws("cloudformation", "describe-stacks", "--stack-name", name, missing=True)
        if result is None:
            return None
        self.require(len(result["Stacks"]) == 1, "Ambiguous stack")
        row = result["Stacks"][0]
        self.require(
            row["StackId"].startswith(
                f"arn:aws:cloudformation:{self.REGION}:{self.ACCOUNT}:stack/{name}/"
            ),
            "Stack identity differs",
        )
        actual_tags = {item["Key"]: item["Value"] for item in row.get("Tags", [])}
        self.require(
            all(actual_tags.get(key) == value for key, value in (tags or self.TAGS).items()),
            "Stack ownership differs",
        )
        if template is not None:
            self.require(
                self.stack_template(row) == template,
                "Existing stack template differs; no unreviewed update or repair",
            )
        return row

    def stack_template(self, row):
        return database_review.stack_template(
            row,
            aws=self.aws,
        )

    one = staticmethod(one)

    def network(self):
        return database_review.network(
            account=self.ACCOUNT,
            admin_arn=self.ADMIN_ARN,
            app_sg=self.APP_SG,
            db_sg=self.DB_SG,
            foundation=self.FOUNDATION,
            host=self.HOST,
            migration_sg=self.MIGRATION_SG,
            subnet_a=self.SUBNET_A,
            subnet_b=self.SUBNET_B,
            vpc=self.VPC,
            aws=self.aws,
            report=self.context.report,
        )

    def scan(self):
        return database_review.scan(
            account=self.ACCOUNT,
            digest=self.DIGEST,
            expiry=self.EXPIRY,
            aws=self.aws,
            report=self.context.report,
        )

    def price(self, service, filters, unit):
        return database_review.price(
            service,
            filters,
            unit,
            aws=self.aws,
        )

    def costs(self, db_gib, nat_gib, *, authentication=False):
        return database_review.costs(
            db_gib,
            nat_gib,
            authentication=authentication,
            report=self.context.report,
            note=self.note,
            price_lookup=self.price,
        )

    def template_path(self, template, directory, name):
        path = directory / (name + ".json")
        body = json.dumps(template, separators=(",", ":"))
        self.require(len(body.encode()) <= 51200, "CloudFormation template exceeds inline size")
        path.write_text(body)
        return path

    def provision(
        self, name, template, directory, *, create_if_missing=True, tags=None, protect=False
    ):
        if name == self.PROBE_STACK:
            existing = self.owned_stack(name)
            if existing is not None and self.stack_template(existing) != template:
                self.update_probe_stack(existing, template, directory)
        row = self.owned_stack(name, tags=tags)
        if row is not None and name != self.PROBE_STACK:
            self.require(self.stack_template(row) == template, "Existing stack template differs")
        if row is None:
            self.require(
                create_if_missing, "Diagnostic target disappeared; no resources will be created"
            )
            path = self.template_path(template, directory, name)
            self.aws(
                "cloudformation", "validate-template", "--template-body", "file://" + str(path)
            )
            response = self.aws(
                "cloudformation",
                "create-stack",
                "--stack-name",
                name,
                "--template-body",
                "file://" + str(path),
                "--capabilities",
                "CAPABILITY_IAM",
                "--disable-rollback",
                "--client-request-token",
                uuid.uuid4().hex,
                "--tags",
                *["Key=" + k + ",Value=" + v for k, v in (tags or self.TAGS).items()],
                *(["--enable-termination-protection"] if protect else []),
            )
            self.context.report.setdefault("stacks", {})[name] = response["StackId"]
        deadline = time.monotonic() + 1800
        last_print = 0
        while True:
            row = self.owned_stack(name, tags=tags)
            self.require(row is not None, "Created stack missing")
            self.context.report.setdefault("stacks", {})[name] = row["StackId"]
            status = row["StackStatus"]
            self.context.report["provisioning_stack_status"] = status
            pending = {
                "CREATE_IN_PROGRESS",
                "UPDATE_IN_PROGRESS",
                "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
            }
            if time.monotonic() - last_print >= 60 or status not in pending:
                self.note(name + ": " + status)
                last_print = time.monotonic()
            if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
                self.require(
                    self.stack_template(row) == template, "Completed stack template differs"
                )
                return row
            if status not in pending:
                events = self.aws(
                    "cloudformation", "describe-stack-events", "--stack-name", row["StackId"]
                )["StackEvents"]
                self.context.report["failed_resources"] = [
                    {
                        k: e.get(k)
                        for k in [
                            "LogicalResourceId",
                            "ResourceType",
                            "ResourceStatus",
                            "ResourceStatusReason",
                        ]
                    }
                    for e in events
                    if e.get("ResourceStatus", "").endswith("FAILED")
                ][:12]
                raise RuntimeError("Stack did not complete the update; see receipt before retrying")
            self.require(self.stack_template(row) == template, "In-progress stack template differs")
            self.require(
                time.monotonic() < deadline,
                "Provisioning still in progress; rerun to resume verification",
            )
            time.sleep(15)

    def secret_metadata(self, arn, name):
        return database_review.secret_metadata(
            arn,
            name,
            tags=self.TAGS,
            aws=self.aws,
        )

    def credentials(self, row):
        return database_review.credentials(
            row,
            account=self.ACCOUNT,
            region=self.REGION,
            report=self.context.report,
            review_secret=self.secret_metadata,
        )

    def probe_template(self, arns, *, source=None):
        return database_templates.probe_template(
            arns,
            source=source,
            account=self.ACCOUNT,
            admin_arn=self.ADMIN_ARN,
            app_sg=self.APP_SG,
            image=self.IMAGE,
            migration_sg=self.MIGRATION_SG,
            region=self.REGION,
            root=self.ROOT,
            subnet_a=self.SUBNET_A,
            subnet_b=self.SUBNET_B,
            check_sizes=self.configuration_sizes,
        )

    def configuration_sizes(self, properties):
        return database_templates.configuration_sizes(
            properties,
            account=self.ACCOUNT,
        )

    def canonical_hash(self, value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def review_transport_update(self, row, template, previous):
        self.require(
            row["StackId"] == self.REVIEWED_PROBE_ID
            and row["StackStatus"] in {"UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"},
            "Only a reviewed successful native baseline may receive the bootstrap correction",
        )
        comparable = json.loads(json.dumps(template))
        for prefix in ("Setup", "Application"):
            command = comparable["Resources"][prefix + "Function"]["Properties"]["ImageConfig"][
                "Command"
            ]
            previous_command = previous["Resources"][prefix + "Function"]["Properties"][
                "ImageConfig"
            ]["Command"]
            self.require(
                len(command) == len(previous_command) == 4 and command[:3] == previous_command[:3],
                "Update changes the verified loader",
            )
            command[3] = previous_command[3]
        self.require(
            comparable == previous, "Update proposes changes beyond the bootstrap source pins"
        )
        self.require(
            self.stack_inventory(row, previous, successful=True)
            == self.REVIEWED_PHYSICAL_RESOURCES,
            "Native transport resource identities differ",
        )
        self.verify_functions(row, previous)
        self.context.report["reviewed_probe_update"] = {
            "stack_id": row["StackId"],
            "previous_template_sha256": self.canonical_hash(previous),
            "previous_stack_status": row["StackStatus"],
            "scope": "only the two bootstrap source SHA-256 pins in existing loader commands",
            "rollback_enabled": False,
        }
        return False

    def review_probe_update(self, row, template, *, recovery=False):
        self.context.report.pop("retained_rollback_review", None)
        previous = self.stack_template(row)
        digest = self.canonical_hash(previous)
        if digest in {
            self.TRANSPORT_TEMPLATE_SHA256,
            self.IDENTITY_TEMPLATE_SHA256,
            self.CLIENT_TEMPLATE_SHA256,
            self.DIAGNOSTIC_TEMPLATE_SHA256,
        }:
            self.require(
                not recovery, "Native transport is deployed; use --diagnose, not --recover"
            )
            return self.review_transport_update(row, template, previous)
        failed = row["StackStatus"] in {"UPDATE_FAILED", "UPDATE_ROLLBACK_FAILED"}
        self.require(
            not failed or recovery, "Run this operator with --recover before another update"
        )
        self.require(
            row["StackId"] == self.REVIEWED_PROBE_ID
            and row["StackStatus"]
            in {
                "UPDATE_COMPLETE",
                "UPDATE_FAILED",
                "UPDATE_ROLLBACK_FAILED",
                "UPDATE_ROLLBACK_COMPLETE",
            }
            and (
                row["StackStatus"] in {"UPDATE_ROLLBACK_FAILED", "UPDATE_ROLLBACK_COMPLETE"}
                or row.get("DisableRollback") is True
            ),
            "Only the recorded temporary stack may receive this transport repair",
        )
        self.require(
            digest in {self.PREVIOUS_TEMPLATE_SHA256, self.FAILED_TEMPLATE_SHA256},
            "Previous stack template differs from reviewed receipt",
        )
        if row["StackStatus"] == "UPDATE_ROLLBACK_COMPLETE":
            self.require(
                digest == self.PREVIOUS_TEMPLATE_SHA256, "Recovered stack template differs"
            )
        comparable = json.loads(json.dumps(template))
        for prefix in ["Setup", "Application"]:
            properties = comparable["Resources"][prefix + "Function"]["Properties"]
            old = previous["Resources"][prefix + "Function"]["Properties"]
            properties["ImageConfig"]["Command"] = old["ImageConfig"]["Command"]
            properties["Environment"]["Variables"]["FITFINITY_DB_BOOTSTRAP_TAIL"] = old[
                "Environment"
            ]["Variables"]["FITFINITY_DB_BOOTSTRAP_TAIL"]
        self.require(comparable == previous, "Update proposes changes beyond bootstrap diagnostics")
        rows = self.aws("cloudformation", "list-stack-resources", "--stack-name", row["StackId"])[
            "StackResourceSummaries"
        ]
        self.context.report["probe_resource_review"] = [
            {
                key: resource.get(key)
                for key in (
                    "LogicalResourceId",
                    "PhysicalResourceId",
                    "ResourceType",
                    "ResourceStatus",
                    "LastUpdatedTimestamp",
                    "ResourceStatusReason",
                )
            }
            for resource in rows
        ]
        self.require(
            len(rows) == 6 and {r["LogicalResourceId"] for r in rows} == set(template["Resources"]),
            "Temporary stack resource inventory differs",
        )
        failed_ids = set()
        retained_ids = set()
        for resource in rows:
            logical = resource["LogicalResourceId"]
            states = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}
            if failed and logical in {"SetupFunction", "ApplicationFunction"}:
                states |= {"UPDATE_FAILED", "UPDATE_ROLLBACK_FAILED"}
                if resource["ResourceStatus"].endswith("FAILED"):
                    failed_ids.add(logical)
            if (
                row["StackStatus"] == "UPDATE_ROLLBACK_COMPLETE"
                and logical in self.RETAINED_FAILURE_TIMES
                and resource["ResourceStatus"] == "UPDATE_ROLLBACK_FAILED"
            ):
                try:
                    updated = dt.datetime.fromisoformat(resource.get("LastUpdatedTimestamp", ""))
                except (TypeError, ValueError):
                    updated = None
                self.require(
                    updated == dt.datetime.fromisoformat(self.RETAINED_FAILURE_TIMES[logical])
                    and self.REQUEST_SIZE_ERROR in resource.get("ResourceStatusReason", ""),
                    "Retained function failure differs from the reviewed timestamp/reason",
                )
                states.add("UPDATE_ROLLBACK_FAILED")
                retained_ids.add(logical)
            self.require(
                resource["ResourceType"] == template["Resources"][logical]["Type"]
                and resource["ResourceStatus"] in states,
                f"Temporary stack resource type/state differs: {logical} "
                f"({resource.get('ResourceType')}, {resource.get('ResourceStatus')})",
            )
        if retained_ids:
            self.require(
                {r["LogicalResourceId"]: r["PhysicalResourceId"] for r in rows}
                == self.REVIEWED_PHYSICAL_RESOURCES,
                "Retained-failure resource identities differ from the reviewed inventory",
            )
        if failed:
            events = self.aws(
                "cloudformation", "describe-stack-events", "--stack-name", row["StackId"]
            )["StackEvents"]
            self.require(failed_ids, "No matching failed functions to recover")
            stable = [
                event
                for event in events
                if event.get("ResourceType") == "AWS::CloudFormation::Stack"
                and event.get("PhysicalResourceId") == self.REVIEWED_PROBE_ID
                and event.get("ResourceStatus") == "UPDATE_COMPLETE"
            ]
            self.require(
                stable, "Previous successful stack state was not verified; rollback refused"
            )
            failures = {}
            boundary = False
            for event in events:
                if event.get("ResourceType") == "AWS::CloudFormation::Stack" and event.get(
                    "ResourceStatus"
                ) == (
                    "UPDATE_ROLLBACK_IN_PROGRESS"
                    if row["StackStatus"] == "UPDATE_ROLLBACK_FAILED"
                    else "UPDATE_IN_PROGRESS"
                ):
                    boundary = True
                    break
                if (
                    event.get("ResourceStatus", "").endswith("FAILED")
                    and event.get("ResourceType") != "AWS::CloudFormation::Stack"
                ):
                    self.require(
                        event.get("LogicalResourceId") in {"SetupFunction", "ApplicationFunction"}
                        and self.REQUEST_SIZE_ERROR in event.get("ResourceStatusReason", ""),
                        "Failed update contains an unreviewed resource error",
                    )
                    failures[event["LogicalResourceId"]] = True
            self.require(
                boundary and failed_ids <= set(failures),
                "Latest failed update does not match the recorded configuration-size failure",
            )
        verified = self.verify_functions(
            row,
            previous,
            recovering=failed or row["StackStatus"] == "UPDATE_ROLLBACK_COMPLETE",
            config_hashes=self.STABLE_CONFIG_HASHES
            if recovery or row["StackStatus"] == "UPDATE_ROLLBACK_COMPLETE"
            else None,
        )
        if retained_ids:
            self.require(
                self.canonical_hash(verified) == self.PREVIOUS_TEMPLATE_SHA256,
                "Retained-failure live configuration differs from the successful template",
            )
            self.context.report["retained_rollback_review"] = {
                "stack_id": row["StackId"],
                "state": row["StackStatus"],
                "resource_ids": sorted(retained_ids),
                "live_template_sha256": self.canonical_hash(verified),
            }
        if recovery:
            self.require(
                self.canonical_hash(verified) == self.PREVIOUS_TEMPLATE_SHA256,
                "Live resources do not match the last successful template",
            )
            self.context.report["recovery_review"] = {
                "stack_id": row["StackId"],
                "state": row["StackStatus"],
                "stable_template_sha256": self.PREVIOUS_TEMPLATE_SHA256,
                "failed_functions": sorted(failed_ids),
                "physical_resources": {
                    r["LogicalResourceId"]: r["PhysicalResourceId"] for r in rows
                },
            }
            return sorted(failed_ids)
        self.context.report["reviewed_probe_update"] = {
            "stack_id": row["StackId"],
            "previous_template_sha256": digest,
            "previous_stack_status": row["StackStatus"],
            "scope": "two function loader commands and removal of source environment variables",
            "rollback_enabled": bool(retained_ids),
        }
        return bool(retained_ids)

    def update_probe_stack(self, row, template, directory):
        # Recheck ownership, state, old template and live function/IAM configuration
        # before updating the one recorded stack; never recreate or delete it here.
        live = self.owned_stack(self.PROBE_STACK)
        self.require(live and live["StackId"] == row["StackId"], "Repair stack identity changed")
        rollback_enabled = self.review_probe_update(live, template)
        self.require(
            not rollback_enabled
            or self.context.report.get("preview_update_rollback_enabled") is True,
            "Rollback behavior changed after the execution preview; rerun to review",
        )
        path = self.template_path(template, directory, self.PROBE_STACK)
        self.aws("cloudformation", "validate-template", "--template-body", "file://" + str(path))
        response = self.aws(
            "cloudformation",
            "update-stack",
            "--stack-name",
            row["StackId"],
            "--template-body",
            "file://" + str(path),
            "--capabilities",
            "CAPABILITY_IAM",
            "--no-disable-rollback" if rollback_enabled else "--disable-rollback",
            "--client-request-token",
            uuid.uuid4().hex,
        )
        self.require(response.get("StackId") == row["StackId"], "Repair response identity differs")
        self.context.report["probe_update_requested"] = True

    def stack_inventory(self, row, template, *, successful=False):
        rows = self.aws("cloudformation", "list-stack-resources", "--stack-name", row["StackId"])[
            "StackResourceSummaries"
        ]
        self.require(
            len(rows) == len(template["Resources"])
            and {x["LogicalResourceId"] for x in rows} == set(template["Resources"]),
            "Unexpected stack resources",
        )
        self.require(
            all(
                x["ResourceType"] == template["Resources"][x["LogicalResourceId"]]["Type"]
                for x in rows
            ),
            "Resource types differ",
        )
        if successful:
            self.require(
                all(
                    x.get("ResourceStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"} for x in rows
                ),
                "Resource completion was not verified; invocation stopped",
            )
        return {x["LogicalResourceId"]: x["PhysicalResourceId"] for x in rows}

    def verify_functions(self, row, template, *, recovering=False, config_hashes=None):
        verified_template = json.loads(json.dumps(template))
        physical = self.stack_inventory(row, template, successful=not recovering)
        for prefix in ["Setup", "Application"]:
            properties = template["Resources"][prefix + "Function"]["Properties"]
            name = properties["FunctionName"]
            self.require(physical[prefix + "Function"] == name, "Function resource differs")
            function = self.aws("lambda", "get-function", "--function-name", name)
            config = function["Configuration"]
            last_update_ok = config.get("LastUpdateStatus", "Successful") == "Successful"
            if recovering and config.get("LastUpdateStatus") == "Failed":
                last_update_ok = self.REQUEST_SIZE_ERROR in config.get("LastUpdateStatusReason", "")
            self.require(
                config.get("FunctionArn")
                == f"arn:aws:lambda:{self.REGION}:{self.ACCOUNT}:function:{name}"
                and config.get("State") == "Active"
                and last_update_ok,
                "Function not active",
            )
            self.require(
                function["Code"].get("ResolvedImageUri") == self.IMAGE,
                "Resolved function image differs",
            )
            self.require(
                config.get("PackageType") == "Image"
                and config.get("Architectures") == ["x86_64"]
                and config.get("Timeout") == 120
                and config.get("MemorySize") == 256
                and not config.get("Layers"),
                "Function settings differ",
            )
            actual_image = config.get("ImageConfigResponse", {}).get("ImageConfig", {})
            if recovering:
                actual = {"ImageConfig": actual_image, "Environment": config.get("Environment", {})}
                self.require(
                    self.canonical_hash(actual)
                    in (config_hashes or self.REVIEWED_CONFIG_HASHES)[prefix],
                    "Function code/configuration differs from both reviewed revisions",
                )
                properties = {**properties, **actual}
                verified_template["Resources"][prefix + "Function"]["Properties"] = properties
                self.context.report.setdefault("recovery_live_config_sha256", {})[prefix] = (
                    self.canonical_hash(actual)
                )
            self.require(
                config.get("Environment", {}).get("Variables")
                == properties["Environment"]["Variables"]
                and actual_image.get("Command") == properties["ImageConfig"]["Command"]
                and actual_image.get("EntryPoint", []) == []
                and actual_image.get("WorkingDirectory") == "/app",
                "Function code/configuration differs",
            )
            vpc = config["VpcConfig"]
            self.require(
                vpc["VpcId"] == self.VPC
                and vpc["SubnetIds"] == properties["VpcConfig"]["SubnetIds"]
                and vpc["SecurityGroupIds"] == properties["VpcConfig"]["SecurityGroupIds"]
                and not vpc.get("Ipv6AllowedForDualStack"),
                "Function networking differs",
            )
            self.require(
                self.aws("lambda", "get-function-url-config", "--function-name", name, missing=True)
                is None,
                "Unexpected function URL",
            )
            self.require(
                self.aws("lambda", "get-policy", "--function-name", name, missing=True) is None,
                "Unexpected function resource policy",
            )
            self.require(
                not self.aws("lambda", "list-event-source-mappings", "--function-name", name).get(
                    "EventSourceMappings"
                ),
                "Unexpected event source",
            )
            role_name = physical[prefix + "Role"]
            role = self.aws("iam", "get-role", "--role-name", role_name)["Role"]
            role_properties = template["Resources"][prefix + "Role"]["Properties"]
            self.require(
                role["Arn"] == config["Role"]
                and role["AssumeRolePolicyDocument"] == role_properties["AssumeRolePolicyDocument"],
                "Role trust differs",
            )
            self.require(
                self.aws("iam", "list-role-policies", "--role-name", role_name)["PolicyNames"]
                == ["FitfinityDatabaseBootstrap"]
                and not self.aws("iam", "list-attached-role-policies", "--role-name", role_name)[
                    "AttachedPolicies"
                ],
                "Role has unexpected policies",
            )
            policy = self.aws(
                "iam",
                "get-role-policy",
                "--role-name",
                role_name,
                "--policy-name",
                "FitfinityDatabaseBootstrap",
            )["PolicyDocument"]
            self.require(
                policy == role_properties["Policies"][0]["PolicyDocument"],
                "Role permissions differ",
            )
            log_name = template["Resources"][prefix + "Logs"]["Properties"]["LogGroupName"]
            logs = self.aws("logs", "describe-log-groups", "--log-group-name-prefix", log_name)[
                "logGroups"
            ]
            self.require(
                self.one(
                    [x for x in logs if x["logGroupName"] == log_name], "Log group missing"
                ).get("retentionInDays")
                == 1,
                "Log retention differs",
            )

        return verified_template

    def recover_probe(self, template):
        initial = self.owned_stack(self.PROBE_STACK)
        self.require(
            initial and initial["StackId"] == self.REVIEWED_PROBE_ID, "Recovery stack changed"
        )
        inventory = self.stack_inventory(initial, template)
        requested = set()
        deadline = time.monotonic() + 1800
        last_print = 0
        while True:
            row = self.owned_stack(self.PROBE_STACK)
            self.require(
                row and row["StackId"] == self.REVIEWED_PROBE_ID,
                "Recovery stack missing or changed",
            )
            self.require(
                self.stack_inventory(row, template) == inventory,
                "Recovery resource identities changed",
            )
            self.require(
                self.canonical_hash(self.stack_template(row))
                in {self.PREVIOUS_TEMPLATE_SHA256, self.FAILED_TEMPLATE_SHA256},
                "Recovery template changed",
            )
            status = row["StackStatus"]
            self.context.report["recovery_stack_status"] = status
            if time.monotonic() - last_print >= 30:
                self.note("Temporary stack recovery: " + status)
                last_print = time.monotonic()
            if status == "UPDATE_ROLLBACK_COMPLETE":
                self.require(
                    self.canonical_hash(self.stack_template(row)) == self.PREVIOUS_TEMPLATE_SHA256,
                    "Recovered template is not the last successful revision",
                )
                self.review_probe_update(row, template, recovery=True)
                self.context.report["stack_recovery_verified"] = True
                self.note(
                    "STACK RECOVERY PASSED — previous function configuration verified; "
                    "no invocation or SQL."
                )
                return
            if status in {"UPDATE_FAILED", "UPDATE_ROLLBACK_FAILED"}:
                selected = self.review_probe_update(row, template, recovery=True)
                operation = (
                    "rollback-stack" if status == "UPDATE_FAILED" else "continue-update-rollback"
                )
                self.require(
                    operation not in requested, "Recovery attempt failed again; resources preserved"
                )
                args = [
                    "--stack-name",
                    self.REVIEWED_PROBE_ID,
                    "--client-request-token",
                    uuid.uuid4().hex,
                ]
                if operation == "continue-update-rollback":
                    args += ["--resources-to-skip", *selected]
                    self.context.report["verified_rollback_skips"] = selected
                response = self.aws("cloudformation", operation, *args)
                if operation == "rollback-stack":
                    self.require(
                        response.get("StackId") == self.REVIEWED_PROBE_ID,
                        "Rollback response differs",
                    )
                requested.add(operation)
                self.context.report.setdefault("recovery_requests", []).append(operation)
                # Allow for read-after-write propagation without submitting another request.
                grace = time.monotonic() + 60
                while True:
                    latest = self.owned_stack(self.PROBE_STACK)
                    self.require(
                        latest and latest["StackId"] == self.REVIEWED_PROBE_ID,
                        "Recovery stack changed",
                    )
                    if latest["StackStatus"] != status:
                        break
                    self.require(
                        time.monotonic() < grace,
                        "Recovery accepted; state unchanged, rerun --recover",
                    )
                    time.sleep(5)
                continue
            self.require(
                status
                in {"UPDATE_ROLLBACK_IN_PROGRESS", "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS"},
                "Unexpected recovery state; resources preserved",
            )
            self.require(
                time.monotonic() < deadline, "Recovery still pending; rerun --recover to resume"
            )
            time.sleep(10)

    def invoke(
        self, name, mode, directory, *, preflight=False, database_diagnostic=False, source=None
    ):
        self.require(
            not database_diagnostic or (mode == "setup" and not preflight),
            "Database diagnostic requires only the setup function",
        )
        nonce = uuid.uuid4().hex
        target = directory / (mode + ("-preflight" if preflight else "") + "-result.json")
        # A synthetic HTTP-v2 event gives a defined HTTP response envelope. This is an
        # IAM-authorized Invoke, not a deployed API Gateway or public URL.
        event = {
            "version": "2.0",
            "routeKey": "POST /events",
            "rawPath": "/events",
            "rawQueryString": "",
            "headers": {"content-type": "application/json"},
            "requestContext": {
                "accountId": self.ACCOUNT,
                "apiId": "fitfinity-db-bootstrap",
                "domainName": "bootstrap.invalid",
                "domainPrefix": "bootstrap",
                "http": {
                    "method": "POST",
                    "path": "/events",
                    "protocol": "HTTP/1.1",
                    "sourceIp": "127.0.0.1",
                    "userAgent": "FitfinityOperator",
                },
                "requestId": nonce,
                "routeKey": "POST /events",
                "stage": "$default",
                "timeEpoch": int(time.time() * 1000),
            },
            "body": json.dumps(
                {
                    "action": "preflight"
                    if preflight
                    else "database-diagnostic"
                    if database_diagnostic
                    else mode,
                    "nonce": nonce,
                    "bootstrap_source": source
                    if source is not None
                    else (self.ROOT / "test-db-bootstrap.py").read_text(),
                }
            ),
            "isBase64Encoded": False,
        }
        self.require(
            len(event["body"].encode()) <= 49152, "Bootstrap invocation envelope exceeds limit"
        )
        result = self.aws(
            "lambda",
            "invoke",
            "--function-name",
            name,
            "--invocation-type",
            "RequestResponse",
            "--payload",
            json.dumps(event),
            "--cli-binary-format",
            "raw-in-base64-out",
            str(target),
        )
        self.require(
            result.get("StatusCode") == 200 and not result.get("FunctionError"),
            "Private invocation failed; inspect the preserved temporary stack",
        )
        envelope = json.loads(target.read_text())
        self.require(envelope.get("statusCode") == 200, "Private HTTP adapter response differs")
        body = envelope.get("body", "")
        if envelope.get("isBase64Encoded"):
            body = base64.b64decode(body, validate=True).decode()
        proof = json.loads(body)
        # The fixed service only emits whitelisted diagnostics/proofs, never secret fields.
        self.require(proof.get("nonce") == nonce, "Invocation response nonce differs")
        if proof.get("ok") is not True:
            diagnostics = {
                k: proof.get(k)
                for k in ["stage", "error_type", "sqlstate", "runtime_identity", "ca_sha256"]
            }
            if preflight:
                return {"ok": False, **diagnostics}
            self.context.report["bootstrap_failure"] = diagnostics
            raise RuntimeError(
                "Private database check stopped at "
                + str(proof.get("stage"))
                + "; resources preserved, see receipt"
            )
        self.require(proof.get("mode") == mode, "Invocation mode differs")
        if preflight:
            self.require(proof.get("preflight_only") is True, "Preflight-only response missing")
        return proof

    def cleanup(self, row, template, *, name=None, tags=None):
        if name is None:
            name = self.PROBE_STACK
        live = self.owned_stack(name, template, tags=tags)
        self.require(
            live
            and live["StackId"] == row["StackId"]
            and live["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
            "Cleanup identity/state changed",
        )
        self.stack_inventory(live, template)
        self.context.report["cleanup_requested"] = True
        self.aws("cloudformation", "delete-stack", "--stack-name", row["StackId"])
        deadline = time.monotonic() + 2100
        last_print = 0
        while True:
            result = self.aws(
                "cloudformation", "describe-stacks", "--stack-name", row["StackId"], missing=True
            )
            if result is None or result["Stacks"][0]["StackStatus"] == "DELETE_COMPLETE":
                self.context.report["temporary_cleanup_complete"] = True
                return
            self.require(
                result["Stacks"][0]["StackId"] == row["StackId"]
                and result["Stacks"][0]["StackStatus"] == "DELETE_IN_PROGRESS",
                "Temporary cleanup needs review",
            )
            self.require(
                time.monotonic() < deadline,
                "Database checks passed; temporary cleanup still pending",
            )
            if time.monotonic() - last_print >= 60:
                self.note(
                    "Database checks passed. Waiting for "
                    "temporary Lambda/network-interface cleanup..."
                )
                last_print = time.monotonic()
            time.sleep(15)

    def main(self, *, diagnose=False, recover=False, database_diagnostic=False):

        self.note("Fitfinity AWS — restricted database accounts and private TLS verification")
        self.require(
            sum((diagnose, recover, database_diagnostic)) <= 1,
            "Choose either diagnostic or recovery mode; only one mode is permitted",
        )
        reuse_only = diagnose or database_diagnostic
        self.context.report["diagnostic_only"] = diagnose
        self.context.report["database_diagnostic_only"] = database_diagnostic
        self.context.report["recovery_only"] = recover
        # Check deployable sizes even before AWS reads. Generated secret suffixes
        # always have six characters, so these placeholders have their exact length.
        preview_arns = {
            suffix: f"arn:aws:secretsmanager:{self.REGION}:{self.ACCOUNT}:secret:"
            f"fitfinity/test/database/{suffix}-ABC123"
            for suffix in ["app", "migration"]
        }
        self.probe_template(preview_arns)
        self.environment()
        db_gib, nat_gib = self.network()
        self.scan()
        self.costs(db_gib, nat_gib)
        persistent = json.loads((self.ROOT / "test-db-access.json").read_text())
        previous = self.owned_stack(self.SECRETS_STACK, persistent)
        self.require(
            previous is None
            or previous["StackStatus"]
            in {"CREATE_IN_PROGRESS", "CREATE_COMPLETE", "UPDATE_COMPLETE"},
            "Database-secret stack needs review",
        )
        if previous is None:
            for name in ["fitfinity/test/database/app", "fitfinity/test/database/migration"]:
                self.require(
                    self.aws("secretsmanager", "describe-secret", "--secret-id", name, missing=True)
                    is None,
                    "A credential with the proposed name already exists outside this stack",
                )
        elif previous["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
            preview_arns = self.credentials(previous)
        preview_template = self.probe_template(preview_arns)
        self.context.report["bootstrap_configuration_bytes"] = {
            prefix: self.configuration_sizes(
                preview_template["Resources"][prefix + "Function"]["Properties"]
            )
            for prefix in ["Setup", "Application"]
        }
        existing_probe = self.owned_stack(self.PROBE_STACK)
        if reuse_only or recover:
            self.require(
                previous
                and previous["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
                and previous.get("EnableTerminationProtection") is True
                and existing_probe,
                "Diagnostics require the existing protected secret stack and temporary functions",
            )
        if existing_probe:
            self.require(
                existing_probe["StackStatus"]
                in {
                    "CREATE_IN_PROGRESS",
                    "CREATE_COMPLETE",
                    "UPDATE_IN_PROGRESS",
                    "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
                    "UPDATE_COMPLETE",
                    "UPDATE_FAILED",
                    "UPDATE_ROLLBACK_FAILED",
                    "UPDATE_ROLLBACK_IN_PROGRESS",
                    "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
                    "UPDATE_ROLLBACK_COMPLETE",
                },
                "Temporary stack is still deleting or needs review; do not recreate it",
            )
            if recover:
                self.require(
                    existing_probe["StackId"] == self.REVIEWED_PROBE_ID, "Recovery stack differs"
                )
                if existing_probe["StackStatus"] in {
                    "UPDATE_ROLLBACK_IN_PROGRESS",
                    "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
                }:
                    self.require(
                        self.canonical_hash(self.stack_template(existing_probe))
                        in {self.PREVIOUS_TEMPLATE_SHA256, self.FAILED_TEMPLATE_SHA256},
                        "In-progress recovery template differs",
                    )
                    self.stack_inventory(existing_probe, preview_template)
                else:
                    self.require(
                        existing_probe["StackStatus"]
                        in {"UPDATE_FAILED", "UPDATE_ROLLBACK_FAILED", "UPDATE_ROLLBACK_COMPLETE"},
                        "Stack does not need the reviewed rollback recovery",
                    )
                    self.review_probe_update(existing_probe, preview_template, recovery=True)
            elif self.stack_template(existing_probe) != preview_template:
                self.review_probe_update(existing_probe, preview_template)
                self.note(
                    "Update only the verified temporary functions "
                    "to deliver hash-verified code through private invocation payloads."
                )
        self.context.report["preview_update_rollback_enabled"] = bool(
            self.context.report.get("retained_rollback_review") and not recover
        )
        if self.context.report["preview_update_rollback_enabled"]:
            self.note(
                "The completed rollback retains the two recorded resource failures. "
                "Their live settings match the previous successful template."
            )
            self.note(
                "This update explicitly ENABLES CloudFormation rollback on failure; "
                "the disabled-rollback path was rejected by AWS for these resources."
            )
            self.note(
                "Only the two temporary function code transports change. "
                "A failed update may trigger rollback and will stop before invocation."
            )
        if recover:
            self.note(
                "Recovery only: roll back the exact "
                "temporary stack to its verified previous revision."
            )
            self.note(
                "If rollback repeats the known size failure, skip only failed functions "
                "already verified at that revision."
            )
            self.note(
                "No template update, Lambda invocation, database/secret-value access, "
                "resource creation or cleanup."
            )
        elif database_diagnostic:
            self.note(
                "Database diagnostic: reuse existing "
                "resources; update only reviewed bootstrap pins."
            )
            self.note(
                "Repeat both runtime preflights, then read the administrator secret inside AWS "
                "and run fixed SQL checks in a verified READ ONLY transaction."
            )
            self.note(
                "No role/schema/permission changes or cleanup. No passwords or raw errors returned."
            )
        elif diagnose:
            self.note(
                "Diagnostic run: reuse the existing resources; "
                "update only the reviewed bootstrap code if needed."
            )
            self.note(
                "Invoke preflight in both private functions. "
                "No secret values, SQL connections, role setup or cleanup."
            )
            self.note("The current UID, TLS, account and permission requirements remain enforced.")
        else:
            self.execution_preview()
        reviewed = time.monotonic()
        with open("/dev/tty", "w") as terminal:
            action = (
                "recover the temporary stack, including verified rollback skips if required"
                if recover
                else "run the reviewed update and read-only database diagnostic"
                if database_diagnostic
                else "run the reviewed diagnostic update and private preflight"
                if diagnose
                else "execute this database setup and successful-test cleanup"
            )
            terminal.write("To " + action + ", type " + self.ACCOUNT + ": ")
            terminal.flush()
        with open("/dev/tty") as terminal:
            self.require(
                terminal.readline().strip() == self.ACCOUNT, "Confirmation did not match; no writes"
            )
        self.require(
            time.monotonic() - reviewed < 600, "Preview is older than 10 minutes; rerun to refresh"
        )
        self.environment()
        self.require(self.network() == (db_gib, nat_gib), "Storage changed after price preview")
        self.scan()
        self.context.write_allowed = True
        if recover:
            retained = self.owned_stack(self.SECRETS_STACK, persistent)
            self.require(
                retained
                and retained["StackId"] == previous["StackId"]
                and retained.get("EnableTerminationProtection") is True,
                "Existing secret stack changed before recovery",
            )
            self.recover_probe(preview_template)
            return
        with tempfile.TemporaryDirectory(prefix="fitfinity-db-access-") as temporary:
            directory = Path(temporary)
            if reuse_only:
                row = self.owned_stack(self.SECRETS_STACK, persistent)
                self.require(
                    row
                    and row["StackId"] == previous["StackId"]
                    and row["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
                    and row.get("EnableTerminationProtection") is True,
                    "Existing secret stack changed before diagnostics",
                )
                live_probe = self.owned_stack(self.PROBE_STACK)
                self.require(
                    live_probe and live_probe["StackId"] == existing_probe["StackId"],
                    "Existing temporary stack changed before diagnostics",
                )
            else:
                row = self.provision(self.SECRETS_STACK, persistent, directory)
            self.stack_inventory(row, persistent)
            if not row.get("EnableTerminationProtection"):
                protection = self.aws(
                    "cloudformation",
                    "update-termination-protection",
                    "--enable-termination-protection",
                    "--stack-name",
                    row["StackId"],
                )
                self.require(
                    protection.get("StackId") == row["StackId"],
                    "Secret stack protection response differs",
                )
                protected = self.owned_stack(self.SECRETS_STACK, persistent)
                self.require(
                    protected and protected.get("EnableTerminationProtection") is True,
                    "Secret stack termination protection was not verified",
                )
            arns = self.credentials(row)
            template = self.probe_template(arns)
            self.context.report["bootstrap_source_sha256"] = hashlib.sha256(
                (self.ROOT / "test-db-bootstrap.py").read_bytes()
            ).hexdigest()
            self.context.report["bootstrap_loader_sha256"] = hashlib.sha256(
                (self.ROOT / "test-db-loader.py").read_bytes()
            ).hexdigest()
            self.context.report["persistent_template_sha256"] = hashlib.sha256(
                json.dumps(persistent, sort_keys=True).encode()
            ).hexdigest()
            temporary_stack = self.provision(
                self.PROBE_STACK, template, directory, create_if_missing=not reuse_only
            )
            self.verify_functions(temporary_stack, template)
            self.require(
                dt.datetime.now(dt.UTC) < self.EXPIRY,
                "Exception expired during provisioning; invocation stopped",
            )
            self.context.report["runtime_preflight"] = {
                mode: self.invoke(name, mode, directory, preflight=True)
                for name, mode in [
                    ("fitfinity-test-db-setup", "setup"),
                    ("fitfinity-test-db-app-probe", "app-probe"),
                ]
            }
            self.context.report["runtime_preflight_verified"] = all(
                p.get("ok") is True for p in self.context.report["runtime_preflight"].values()
            )
            self.require(
                self.context.report["runtime_preflight_verified"],
                "Runtime preflight stopped; see per-function checks. "
                "No secret values or database calls made",
            )
            if diagnose:
                self.note(
                    "RUNTIME PREFLIGHT PASSED — no database actions; "
                    "temporary stack retained for the next step."
                )
                return
            if database_diagnostic:
                proof = self.invoke(
                    "fitfinity-test-db-setup", "setup", directory, database_diagnostic=True
                ).get("database_diagnostic", {})
                self.context.report["database_diagnostic"] = proof
                self.require(
                    proof.get("database_diagnostic_only") is True
                    and proof.get("read_only") is True
                    and proof.get("rolled_back") is True,
                    "Read-only database diagnostic proof missing",
                )
                for label, result in proof.get("checks", {}).items():
                    self.note(label + ": " + ("PASS" if result.get("ok") is True else "FAILED"))
                self.note(
                    "DATABASE DIAGNOSTIC COMPLETE — inspect the receipt; "
                    "no database changes or cleanup. Database access is not yet accepted."
                )
                return
            self.context.report["setup_proof"] = self.invoke(
                "fitfinity-test-db-setup", "setup", directory
            )
            self.require(
                self.context.report["setup_proof"].get("migration", {}).get("ddl_rollback_verified")
                is True,
                "Migration DDL verification missing",
            )
            self.note(
                "Migration account: verified TLS, restricted privileges and rolled-back DDL passed."
            )
            self.context.report["application_proof"] = self.invoke(
                "fitfinity-test-db-app-probe", "app-probe", directory
            )
            application = self.context.report["application_proof"].get("application", {})
            self.require(
                application.get("ddl_denied") is True
                and application.get("migration_role_denied") is True,
                "Application privilege-denial checks missing",
            )
            self.note(
                "Application account: verified TLS; schema "
                "mutation and migration-role access denied."
            )
            self.context.report["database_access_verified"] = True
            self.cleanup(temporary_stack, template)
        self.note(
            "DATABASE ACCESS PASSED — restricted "
            "accounts and verified TLS; temporary stack removed."
        )
        self.note(
            "Migrations, authentication secret, first Owner and app deployment remain pending."
        )

    def execution_preview(self):
        self.note(
            "Creates/reuses 2 retained database secrets and 6 temporary resources: "
            "2 private functions, 2 roles, 2 one-day log groups."
        )
        self.note(
            "Creates fitfinity_app and fitfinity_migrator in the empty fitfinity da"
            "tabase; restricts PUBLIC database/schema access and preinstalls btree_"
            "gist."
        )
        self.note(
            "The app account cannot create schema objects or assume the migration r"
            "ole. The migration account can create schema objects, but cannot creat"
            "e databases or roles."
        )
        self.note(
            "Uses the approved image only for this private setup service. No staff "
            "API, public URL, migrations, users, emails or authentication secret ar"
            "e deployed."
        )
        self.note(
            "Passwords remain in AWS. On success only the exact temporary stack and"
            " its test logs are removed; the two credentials/database roles remain."
        )
        self.note(
            "On failure resources are preserved. No password reset, secret rotation"
            ", database deletion, Git push or source installation is performed."
        )

    def save(self):
        self.context.report["checked_at"] = dt.datetime.now(dt.UTC).isoformat()
        folder = Path.home() / "Downloads"
        folder.mkdir(exist_ok=True)
        descriptor, filename = tempfile.mkstemp(
            prefix="Fitfinity_AWS_Database_Access_", suffix=".json", dir=folder
        )
        with os.fdopen(descriptor, "w") as stream:
            json.dump(self.context.report, stream, indent=2)
        self.note("Receipt: " + filename)

    def run(self):
        try:
            self.require(
                sys.argv[1:] in ([], ["--diagnose"], ["--recover"], ["--diagnose-database"]),
                "Usage: operator [--diagnose | --diagnose-database | --recover]",
            )
            self.main(
                diagnose=sys.argv[1:] == ["--diagnose"],
                recover=sys.argv[1:] == ["--recover"],
                database_diagnostic=sys.argv[1:] == ["--diagnose-database"],
            )
        except (Exception, KeyboardInterrupt) as error:
            self.context.report["error"] = (
                str(error) if isinstance(error, RuntimeError) else type(error).__name__
            )
            self.note("STOPPED: " + self.context.report["error"])
            self.note("Existing resources are preserved; inspect the receipt before any cleanup.")
            self.save()
            raise SystemExit(1) from None
        self.save()
