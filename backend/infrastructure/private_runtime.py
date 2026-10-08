"""Guarded temporary AWS current-image execution. No public API, migration or Owner creation."""

import base64
import fnmatch
import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import private_runtime_design as design
import private_runtime_preflight as preflight

ROOT = Path(__file__).parent
require = preflight.require
note = preflight.note
ACCOUNT = preflight.deploy.CONFIG["account"]
REGION = preflight.deploy.CONFIG["region"]
EXTRA_READS = {
    ("lambda", "get-function"),
    ("lambda", "get-policy"),
    ("lambda", "get-function-url-config"),
    ("lambda", "list-event-source-mappings"),
    ("iam", "get-role"),
    ("iam", "list-role-policies"),
    ("iam", "get-role-policy"),
    ("iam", "list-attached-role-policies"),
    ("logs", "describe-log-groups"),
    ("logs", "filter-log-events"),
    ("cloudformation", "describe-stack-events"),
    ("ecr", "get-repository-policy"),
}
WRITES = {
    ("cloudformation", "create-stack"),
    ("cloudformation", "delete-stack"),
    ("lambda", "invoke"),
}


def atomic_json(path, value):
    path = Path(path)
    require(not path.is_symlink(), "Redirected state/receipt refused")
    fd, temporary = tempfile.mkstemp(prefix=".fitfinity-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RuntimeAWS(preflight.EvidenceAWS):
    def __init__(self, report, state, checkpoint, runner=subprocess.run):
        super().__init__(report, runner)
        self.state, self.checkpoint = state, checkpoint

    def __call__(self, service, operation, *args, region=None, missing=False):
        pair = service, operation
        if pair in preflight.READS:
            return super().__call__(service, operation, *args, region=region, missing=missing)
        require(pair in EXTRA_READS | WRITES, "Operation outside current-runtime scope")
        require(region in (None, REGION), "Unexpected runtime region")
        require(
            not (
                set(args)
                & {
                    "--debug",
                    "--endpoint-url",
                    "--no-verify-ssl",
                    "--profile",
                    "--region",
                    "--output",
                    "--cli-input-json",
                    "--cli-input-yaml",
                }
            ),
            "CLI override refused",
        )
        if service == "lambda":
            require(
                "--function-name" in args
                and args[args.index("--function-name") + 1] in design.NAMES.values(),
                "Unowned function refused",
            )
        if service == "ecr":
            require(
                args == ("--repository-name", "fitfinity-test-api"),
                "Unowned ECR repository refused",
            )
        if service == "iam":
            require(
                "--role-name" in args
                and args[args.index("--role-name") + 1] in self.state.get("roles", []),
                "Unowned role refused",
            )
        if service == "logs":
            key = (
                "--log-group-name"
                if operation == "filter-log-events"
                else "--log-group-name-prefix"
            )
            require(
                key in args
                and args[args.index(key) + 1]
                in ["/aws/lambda/" + n for n in design.NAMES.values()],
                "Unowned log group refused",
            )
        if pair in WRITES:
            require(self.state.get("execution_authorized") is True, "Execution was not authorized")
            self.validate_write(service, operation, list(args))
            intent = self.state.get("pending_write")
            require(
                intent
                and intent["operation"] == [service, operation]
                and intent["arguments_sha256"] == design.canonical_hash(list(args)),
                "Write has no matching persisted intent",
            )
            self.report["read_only"] = False
        call = {"service": service, "operation": operation, "status": "started"}
        self.calls.append(call)
        if pair in WRITES:
            self.report["cloud_writes"].append(dict(self.state["pending_write"]))
        note(("WRITE " if pair in WRITES else "  READ ") + service + " " + operation)
        command = [
            "aws",
            service,
            operation,
            *args,
            "--region",
            REGION,
            "--output",
            "json",
            "--no-cli-pager",
            "--no-cli-auto-prompt",
            "--cli-error-format",
            "legacy",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "180" if operation == "invoke" else "30",
        ]
        env = {
            **os.environ,
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
            "AWS_MAX_ATTEMPTS": "1" if pair in WRITES else "2",
        }
        try:
            response = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=200 if operation == "invoke" else 90,
                env=env,
            )
        except subprocess.TimeoutExpired:
            call["status"] = "response-uncertain" if pair in WRITES else "timeout"
            raise RuntimeError(
                service
                + " "
                + operation
                + " timed out; intent preserved, do not manually repeat the AWS command"
            ) from None
        if response.returncode:
            if (
                missing
                and pair
                in {
                    ("lambda", "get-function"),
                    ("lambda", "get-policy"),
                    ("lambda", "get-function-url-config"),
                    ("iam", "get-role"),
                }
                and re.search(r"\((ResourceNotFoundException|NoSuchEntity)\)", response.stderr)
            ):
                call["status"] = "absent"
                return None
            call["status"] = "failed-or-uncertain" if pair in WRITES else "failed"
            message = preflight.safe_error(service, operation, response)
            call["error"] = message
            raise RuntimeError(message)
        try:
            value = json.loads(response.stdout) if response.stdout.strip() else {}
        except ValueError:
            raise RuntimeError(
                service + " " + operation + " returned invalid JSON; state preserved"
            ) from None
        preflight.no_secret_fields(value)
        require(
            not any(
                value.get(k)
                for k in ["NextToken", "nextToken", "NextMarker", "Marker", "IsTruncated"]
            ),
            "Incomplete runtime metadata pagination",
        )
        # Function environment/remote log messages remain in memory until validated.
        call["status"] = "complete"
        return value

    def validate_write(self, service, operation, args):
        require(
            self.state.get("operator_revision") != design.PREVIOUS_REVISION
            or (service, operation) == ("cloudformation", "delete-stack"),
            "Historical probe permits cleanup only",
        )

        def value(flag):
            require(
                flag in args and args.index(flag) + 1 < len(args),
                "Missing reviewed write argument: " + flag,
            )
            return args[args.index(flag) + 1]

        if service == "cloudformation":
            target = value("--stack-name")
            if operation == "create-stack":
                require(
                    target == design.STACK and self.state.get("create_intent"),
                    "Unowned stack creation refused",
                )
                require(
                    value("--client-request-token")
                    == self.state["create_intent"]["client_request_token"]
                    and value("--on-failure") == "DO_NOTHING"
                    and value("--capabilities") == "CAPABILITY_IAM",
                    "Create intent/rollback/capability differs",
                )
                body = value("--template-body")
                require(body.startswith("file:///"), "Expected a local reviewed template")
                path = Path(body.removeprefix("file://"))
                require(
                    path.is_file()
                    and not path.is_symlink()
                    and design.canonical_hash(json.loads(path.read_text()))
                    == self.state["template_sha256"],
                    "Create template differs",
                )
                require(
                    {x for x in args if x.startswith("--")}
                    == {
                        "--stack-name",
                        "--template-body",
                        "--capabilities",
                        "--on-failure",
                        "--client-request-token",
                        "--tags",
                    },
                    "Unreviewed creation option",
                )
            else:
                require(
                    target == self.state.get("stack_id")
                    and target.startswith(
                        f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{design.STACK}/"
                    )
                    and self.state.get("delete_intent")
                    and value("--client-request-token")
                    == self.state["delete_intent"]["client_request_token"],
                    "Unowned stack deletion refused",
                )
                require(
                    {x for x in args if x.startswith("--")}
                    == {"--stack-name", "--client-request-token"},
                    "Unreviewed cleanup option",
                )
        else:
            require(
                operation == "invoke"
                and self.report.get("temporary_runtime_configuration_verified") is True,
                "Runtime invocation requires verified live configuration",
            )
            require(
                value("--invocation-type") == "RequestResponse"
                and value("--cli-binary-format") == "raw-in-base64-out",
                "Unreviewed invocation mode",
            )
            payload = value("--payload")
            require(
                payload.startswith("fileb:///"), "Expected the private persisted invocation file"
            )
            path = Path(payload.removeprefix("fileb://"))
            require(
                path.is_file() and not path.is_symlink(), "Invocation payload missing or redirected"
            )
            event = json.loads(path.read_text())
            body = json.loads(event["body"])
            key = value("--function-name") + ":" + body["action"]
            entry = self.state.get("invocations", {}).get(key)
            require(
                entry
                and entry["nonce"] == body["nonce"]
                and entry["status"] == "intent"
                and entry["payload_sha256"] == design.canonical_hash(event)
                and hashlib.sha256(body["bootstrap_source"].encode()).hexdigest()
                == self.state["source_sha256"],
                "Invocation payload/intent differs",
            )
            require(
                {x for x in args if x.startswith("--")}
                == {"--function-name", "--invocation-type", "--payload", "--cli-binary-format"},
                "Unreviewed invocation option",
            )

    def write(self, service, operation, args):
        self.state["pending_write"] = {
            "operation": [service, operation],
            "arguments_sha256": design.canonical_hash(args),
            "intent_at": preflight.now().isoformat(),
        }
        self.checkpoint()
        result = self(service, operation, *args)
        self.state["pending_write"]["response_received"] = True
        self.checkpoint()
        return result


class RuntimeOperator:
    def __init__(
        self,
        aws,
        state,
        report,
        directory,
        checkpoint,
        *,
        sleeper=time.sleep,
        monotonic=time.monotonic,
    ):
        self.aws, self.state, self.report = aws, state, report
        self.directory, self.checkpoint = Path(directory), checkpoint
        self.sleep, self.monotonic = sleeper, monotonic
        self.source, self.contract = design.source_bundle()
        self.template = design.template(self.source)
        self.template_hash = design.canonical_hash(self.template)
        self.source_hash = hashlib.sha256(self.source.encode()).hexdigest()
        self.tags = {
            "Application": "Fitfinity",
            "Environment": "test",
            "Purpose": "current-runtime-v1",
            "OperationId": state["operation_id"],
            "TemplateSHA256": self.template_hash,
        }
        require(
            state.get("template_sha256", self.template_hash) == self.template_hash
            and state.get("source_sha256", self.source_hash) == self.source_hash,
            "Saved runtime source/template differs; preserve the existing state",
        )
        state.update(template_sha256=self.template_hash, source_sha256=self.source_hash)

    def stack(self):
        name = self.state.get("stack_id") or design.STACK
        result = self.aws("cloudformation", "describe-stacks", "--stack-name", name, missing=True)
        if result is None:
            return None
        require(len(result.get("Stacks", [])) == 1, "Runtime stack identity is ambiguous")
        row = result["Stacks"][0]
        if row["StackStatus"] == "DELETE_COMPLETE":
            require(self.state.get("stack_id") == row["StackId"], "Unowned deleted stack")
            return None
        require(
            self.state.get("create_intent")
            and row["StackName"] == design.STACK
            and re.fullmatch(
                r"arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-current-runtime/[a-zA-Z0-9-]+",
                row["StackId"],
            ),
            "Existing runtime stack is not owned by this operation",
        )
        require(
            {x["Key"]: x["Value"] for x in row.get("Tags", [])} == self.tags,
            "Runtime stack ownership tags differ",
        )
        require(
            not self.state.get("stack_id") or self.state["stack_id"] == row["StackId"],
            "Runtime stack ID changed",
        )
        body = self.aws(
            "cloudformation",
            "get-template",
            "--stack-name",
            row["StackId"],
            "--template-stage",
            "Original",
        )["TemplateBody"]
        body = json.loads(body) if isinstance(body, str) else body
        require(body == self.template, "Runtime template drift; no update or deletion attempted")
        self.state["stack_id"] = row["StackId"]
        self.checkpoint()
        return row

    def absent_names(self):
        for name in design.NAMES.values():
            require(
                self.aws("lambda", "get-function", "--function-name", name, missing=True) is None,
                "Runtime function name is already occupied",
            )
            logs = self.aws(
                "logs", "describe-log-groups", "--log-group-name-prefix", "/aws/lambda/" + name
            )
            require(
                not any(
                    x["logGroupName"] == "/aws/lambda/" + name for x in logs.get("logGroups", [])
                ),
                "Runtime log group already exists",
            )

    def verify_ecr_pull_policy(self, names=None):
        value = self.aws("ecr", "get-repository-policy", "--repository-name", "fitfinity-test-api")
        require(
            value.get("registryId") == ACCOUNT
            and value.get("repositoryName") == "fitfinity-test-api",
            "ECR policy identity differs",
        )
        policy = json.loads(value["policyText"])
        require(
            not any(s.get("Effect") == "Deny" for s in policy.get("Statement", [])),
            "ECR deny policy requires a scoped review",
        )
        required_actions = {"ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"}

        def allows(statement, arn):
            principal = statement.get("Principal", {})
            services = principal.get("Service", []) if isinstance(principal, dict) else []
            services = [services] if isinstance(services, str) else services
            actions = statement.get("Action", [])
            actions = [actions] if isinstance(actions, str) else actions
            if (
                statement.get("Effect") != "Allow"
                or "lambda.amazonaws.com" not in services
                or not required_actions <= set(actions)
            ):
                return False
            resources = statement.get("Resource")
            if resources is not None:
                resources = [resources] if isinstance(resources, str) else resources
                target = f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/fitfinity-test-api"
                if not any(fnmatch.fnmatchcase(target, item) for item in resources):
                    return False
            for operator, conditions in statement.get("Condition", {}).items():
                for key, values in conditions.items():
                    values = [values] if isinstance(values, str) else values
                    if key.lower() == "aws:sourcearn" and operator in {"ArnLike", "StringLike"}:
                        if not any(fnmatch.fnmatchcase(arn, v) for v in values):
                            return False
                    elif key.lower() == "aws:sourcearn" and operator in {
                        "ArnEquals",
                        "StringEquals",
                    }:
                        if arn not in values:
                            return False
                    elif key.lower() == "aws:sourceaccount" and operator == "StringEquals":
                        if ACCOUNT not in values:
                            return False
                    else:
                        return False
            return True

        for name in design.NAMES.values() if names is None else names:
            arn = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{name}"
            require(
                any(allows(s, arn) for s in policy.get("Statement", [])),
                (
                    "Existing ECR policy does not cover the temporary Lambda "
                    "image pull. No policy change was attempted"
                ),
            )
        self.report["existing_ecr_lambda_pull_policy_verified"] = True

    def ensure_stack(self):
        row = self.stack()
        if row is None:
            require(
                not self.state.get("create_intent"),
                (
                    "Creation intent exists but stack is absent; response is "
                    "uncertain. No duplicate create was sent"
                ),
            )
            self.absent_names()
            template_path = self.directory / "reviewed-template.json"
            atomic_json(template_path, self.template)
            token = "fitfinity-runtime-" + self.state["operation_id"]
            self.state["create_intent"] = {
                "client_request_token": token,
                "started_at": preflight.now().isoformat(),
            }
            self.checkpoint()
            args = [
                "--stack-name",
                design.STACK,
                "--template-body",
                "file://" + str(template_path),
                "--capabilities",
                "CAPABILITY_IAM",
                "--on-failure",
                "DO_NOTHING",
                "--client-request-token",
                token,
                "--tags",
                *["Key=" + k + ",Value=" + v for k, v in self.tags.items()],
            ]
            response = self.aws.write("cloudformation", "create-stack", args)
            arn = response.get("StackId", "")
            require(
                re.fullmatch(
                    r"arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-current-runtime/[a-zA-Z0-9-]+",
                    arn,
                ),
                "Create response stack ID differs",
            )
            self.state["stack_id"] = arn
            self.checkpoint()
        deadline = self.monotonic() + 1200
        while True:
            row = self.stack()
            require(row is not None, "Runtime stack disappeared during creation")
            status = row["StackStatus"]
            self.report["runtime_stack_status"] = status
            note("Temporary stack: " + status)
            if status == "CREATE_COMPLETE":
                return row
            if status != "CREATE_IN_PROGRESS":
                self.report["stack_events"] = self.aws(
                    "cloudformation", "describe-stack-events", "--stack-name", row["StackId"]
                )
                raise RuntimeError(
                    "Temporary stack " + status + "; resources preserved for diagnosis"
                )
            require(
                self.monotonic() < deadline,
                "Stack still creating; rerun the same --run command to resume",
            )
            self.sleep(10)

    def inventory(self, row, *, successful):
        rows = self.aws("cloudformation", "list-stack-resources", "--stack-name", row["StackId"])[
            "StackResourceSummaries"
        ]
        expected = self.template["Resources"]
        require(
            len(rows) == len(expected) and {r["LogicalResourceId"] for r in rows} == set(expected),
            "Unexpected runtime resource inventory",
        )
        for r in rows:
            require(
                r["ResourceType"] == expected[r["LogicalResourceId"]]["Type"],
                "Runtime resource type differs",
            )
            if successful:
                require(
                    r["ResourceStatus"] == "CREATE_COMPLETE", "Runtime resource is not complete"
                )
        ids = {r["LogicalResourceId"]: r.get("PhysicalResourceId") for r in rows}
        if self.state.get("resource_ids"):
            require(ids == self.state["resource_ids"], "Runtime physical resources changed")
        self.state["resource_ids"] = ids
        self.state["roles"] = [ids[p + "Role"] for p in design.NAMES if ids.get(p + "Role")]
        self.checkpoint()
        return ids

    def verify_live(self, row):
        ids = self.inventory(row, successful=True)
        image_uri = preflight.binding.URI + "@" + self.contract["image_digest"]
        for prefix, name in design.NAMES.items():
            p = self.template["Resources"][prefix + "Function"]["Properties"]
            require(ids[prefix + "Function"] == name, "Function physical name differs")
            value = self.aws("lambda", "get-function", "--function-name", name)
            c = value["Configuration"]
            require(
                c.get("FunctionArn") == f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{name}"
                and c.get("State") == "Active"
                and c.get("LastUpdateStatus", "Successful") == "Successful"
                and value.get("Code", {}).get("ResolvedImageUri") == image_uri,
                "Lambda state or exact image differs",
            )
            for key in ["PackageType", "Architectures", "MemorySize", "Timeout"]:
                require(c.get(key) == p[key], "Lambda setting differs: " + key)
            require(
                not c.get("Layers") and not c.get("DeadLetterConfig") and not c.get("KMSKeyArn"),
                "Unexpected Lambda configuration",
            )
            cfg = c.get("ImageConfigResponse", {}).get("ImageConfig", {})
            require(
                cfg.get("Command") == p["ImageConfig"]["Command"]
                and cfg.get("EntryPoint", []) == []
                and cfg.get("WorkingDirectory") == "/app"
                and c.get("Environment", {}).get("Variables") == p["Environment"]["Variables"],
                "Lambda environment or command drift",
            )
            vpc = c.get("VpcConfig", {})
            require(
                vpc.get("VpcId") == "vpc-0b55320bb1a054441"
                and vpc.get("SubnetIds") == p["VpcConfig"]["SubnetIds"]
                and vpc.get("SecurityGroupIds") == p["VpcConfig"]["SecurityGroupIds"]
                and not vpc.get("Ipv6AllowedForDualStack"),
                "Lambda VPC drift",
            )
            for action in ["get-policy", "get-function-url-config"]:
                require(
                    self.aws("lambda", action, "--function-name", name, missing=True) is None,
                    "Unexpected public/invocation configuration",
                )
            require(
                not self.aws("lambda", "list-event-source-mappings", "--function-name", name).get(
                    "EventSourceMappings"
                ),
                "Unexpected event source",
            )
            role_name = ids[prefix + "Role"]
            rp = self.template["Resources"][prefix + "Role"]["Properties"]
            role = self.aws("iam", "get-role", "--role-name", role_name)["Role"]
            require(
                role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
                == rp["PermissionsBoundary"]
                and role["Arn"] == c["Role"]
                and role["AssumeRolePolicyDocument"] == rp["AssumeRolePolicyDocument"],
                "Runtime role trust differs",
            )
            require(
                self.aws("iam", "list-role-policies", "--role-name", role_name)["PolicyNames"]
                == [design.POLICY]
                and not self.aws("iam", "list-attached-role-policies", "--role-name", role_name)[
                    "AttachedPolicies"
                ],
                "Unexpected runtime role policy",
            )
            policy = self.aws(
                "iam", "get-role-policy", "--role-name", role_name, "--policy-name", design.POLICY
            )["PolicyDocument"]
            require(policy == rp["Policies"][0]["PolicyDocument"], "Runtime permissions differ")
            logs = self.aws(
                "logs", "describe-log-groups", "--log-group-name-prefix", "/aws/lambda/" + name
            )["logGroups"]
            matches = [r for r in logs if r["logGroupName"] == "/aws/lambda/" + name]
            require(
                len(matches) == 1 and matches[0].get("retentionInDays") == 1,
                "Runtime log retention differs",
            )
        self.report["temporary_runtime_configuration_verified"] = True

    def event(self, name, action, nonce):
        return {
            "version": "2.0",
            "routeKey": "POST /events",
            "rawPath": "/events",
            "rawQueryString": "",
            "headers": {"content-type": "application/json", "host": "runtime.invalid"},
            "requestContext": {
                "accountId": ACCOUNT,
                "apiId": "fitfinity-current-runtime",
                "domainName": "runtime.invalid",
                "domainPrefix": "runtime",
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
            "body": json.dumps({"action": action, "nonce": nonce, "bootstrap_source": self.source}),
            "isBase64Encoded": False,
        }

    def parse_response(self, path):
        require(not path.is_symlink() and path.is_file(), "Missing or redirected invocation result")
        envelope = json.loads(path.read_text())
        require(envelope.get("statusCode") == 200, "Private adapter response is not HTTP 200")
        body = envelope.get("body", "")
        if envelope.get("isBase64Encoded"):
            body = base64.b64decode(body, validate=True).decode()
        result = json.loads(body)
        preflight.no_secret_fields(result)
        return result

    def recover_result(self, name, entry, path):
        if path.is_file() and path.stat().st_size:
            try:
                return self.parse_response(path)
            except (RuntimeError, ValueError):
                pass
        events = self.aws(
            "logs",
            "filter-log-events",
            "--log-group-name",
            "/aws/lambda/" + name,
            "--filter-pattern",
            '"FITFINITY_RUNTIME_PROOF" "' + entry["nonce"] + '"',
            "--start-time",
            str(entry["start_time_ms"]),
        )
        results = []
        for event in events.get("events", []):
            message = event.get("message", "")
            if "FITFINITY_RUNTIME_PROOF " in message:
                value = json.loads(message.split("FITFINITY_RUNTIME_PROOF ", 1)[1].strip())
                if value.get("nonce") == entry["nonce"]:
                    preflight.no_secret_fields(value)
                    results.append(value)
        require(
            results and all(value == results[0] for value in results),
            (
                "Invocation response remains uncertain; no duplicate "
                "invocation was sent. Preserve state and receipt"
            ),
        )
        return results[0]

    def invoke(self, name, action):
        key = name + ":" + action
        entries = self.state.setdefault("invocations", {})
        entry = entries.get(key)
        if entry and entry.get("status") == "passed":
            design.validate_result(
                entry["result"], nonce=entry["nonce"], action=action, contract=self.contract
            )
            return
        if entry and entry.get("status") == "failed":
            raise RuntimeError(
                "A recorded runtime proof failed; inspect the existing receipt before retrying"
            )
        if entry:
            path = self.directory / (entry["nonce"] + ".response.json")
            result = self.recover_result(name, entry, path)
        else:
            nonce = uuid.uuid4().hex
            event = self.event(name, action, nonce)
            require(len(event["body"].encode()) <= 49152, "Invocation transport envelope too large")
            entry = {
                "nonce": nonce,
                "action": action,
                "status": "intent",
                "start_time_ms": int(time.time() * 1000),
                "payload_sha256": design.canonical_hash(event),
            }
            entries[key] = entry
            payload = self.directory / (nonce + ".request.json")
            path = self.directory / (nonce + ".response.json")
            atomic_json(payload, event)
            require(
                not path.exists() and not path.is_symlink(), "Invocation result path already exists"
            )
            self.checkpoint()
            metadata = self.aws.write(
                "lambda",
                "invoke",
                [
                    "--function-name",
                    name,
                    "--invocation-type",
                    "RequestResponse",
                    "--payload",
                    "fileb://" + str(payload),
                    "--cli-binary-format",
                    "raw-in-base64-out",
                    str(path),
                ],
            )
            entry["invoke_metadata"] = metadata
            self.checkpoint()
            require(
                metadata.get("StatusCode") == 200 and not metadata.get("FunctionError"),
                "Private Lambda invocation failed; preserve stack and receipt",
            )
            result = self.parse_response(path)
        entry["result"] = result
        try:
            design.validate_result(
                result, nonce=entry["nonce"], action=action, contract=self.contract
            )
        except Exception:
            entry["status"] = "failed"
            self.checkpoint()
            raise
        entry["status"] = "passed"
        if action == "current-runtime":
            self.report["database_sql_executed"] = True
            self.report["database_sql_scope"] = (
                "read-only transaction plus application health SELECTs"
            )
        self.checkpoint()
        note("PASS " + name + " " + action, "32")

    def cleanup(self):
        row = self.stack()
        if row is not None:
            if not self.state.get("delete_intent"):
                require(
                    row["StackStatus"]
                    in {"CREATE_COMPLETE", "CREATE_FAILED", "ROLLBACK_COMPLETE", "ROLLBACK_FAILED"},
                    "Stack is not ready for scoped cleanup; preserve it",
                )
                if row["StackStatus"] == "CREATE_COMPLETE":
                    self.verify_live(row)
                else:
                    # A failed create can have only a subset of physical resources.
                    rows = self.aws(
                        "cloudformation", "list-stack-resources", "--stack-name", row["StackId"]
                    )["StackResourceSummaries"]
                    expected = self.template["Resources"]
                    require(
                        all(
                            r["LogicalResourceId"] in expected
                            and r["ResourceType"] == expected[r["LogicalResourceId"]]["Type"]
                            for r in rows
                        ),
                        "Unexpected failed-stack resources",
                    )
                    self.state["resource_ids"] = {
                        r["LogicalResourceId"]: r.get("PhysicalResourceId") for r in rows
                    }
                    self.state["roles"] = [
                        self.state["resource_ids"][p + "Role"]
                        for p in design.NAMES
                        if self.state["resource_ids"].get(p + "Role")
                    ]
                self.state["delete_intent"] = {
                    "client_request_token": "fitfinity-cleanup-" + self.state["operation_id"],
                    "started_at": preflight.now().isoformat(),
                }
                self.checkpoint()
                self.aws.write(
                    "cloudformation",
                    "delete-stack",
                    [
                        "--stack-name",
                        row["StackId"],
                        "--client-request-token",
                        self.state["delete_intent"]["client_request_token"],
                    ],
                )
                self.state["delete_response_received"] = True
                self.checkpoint()
            deadline = self.monotonic() + 1200
            propagation_deadline = self.monotonic() + 60
            while True:
                row = self.stack()
                if row is None:
                    break
                note("Temporary cleanup: " + row["StackStatus"])
                if (
                    row["StackStatus"]
                    in {"CREATE_COMPLETE", "CREATE_FAILED", "ROLLBACK_COMPLETE", "ROLLBACK_FAILED"}
                    and self.monotonic() < propagation_deadline
                ):
                    self.sleep(5)
                    continue
                require(
                    row["StackStatus"] == "DELETE_IN_PROGRESS",
                    (
                        "Cleanup response uncertain or stack deletion failed; no "
                        "duplicate delete was sent"
                    ),
                )
                require(
                    self.monotonic() < deadline, "Cleanup still running; rerun --cleanup to resume"
                )
                self.sleep(10)
        require(self.state.get("delete_intent"), "No owned cleanup intent; nothing was deleted")
        self.absent_names()
        for name in self.state.get("roles", []):
            require(
                self.aws("iam", "get-role", "--role-name", name, missing=True) is None,
                "Temporary execution role remains",
            )
        self.state["temporary_cleanup_complete"] = True
        self.checkpoint()
        self.report["temporary_cleanup_complete"] = True

    def validate_saved_proof(self):
        for name in design.NAMES.values():
            for action in ["preflight", "current-runtime"]:
                entry = self.state.get("invocations", {}).get(name + ":" + action, {})
                require(entry.get("status") == "passed", "Missing runtime evidence")
                design.validate_result(
                    entry["result"], nonce=entry["nonce"], action=action, contract=self.contract
                )

    def run(self):
        require(
            self.state.get("operator_revision") != design.PREVIOUS_REVISION,
            "Historical failed probe cannot be invoked",
        )
        preflight.evidence(self.report, preflight.now())
        if self.state.get("complete"):
            for name in design.NAMES.values():
                for action in ["preflight", "current-runtime"]:
                    entry = self.state["invocations"][name + ":" + action]
                    require(
                        entry["status"] == "passed", "Completed state lacks successful evidence"
                    )
                    design.validate_result(
                        entry["result"], nonce=entry["nonce"], action=action, contract=self.contract
                    )
            require(self.state.get("temporary_cleanup_complete"), "Completed state lacks cleanup")
            self.report.update(
                status="previous_runtime_proof_complete_noop",
                aws_runtime_verified=True,
                temporary_cleanup_complete=True,
                evidence_source="previous persisted proof; no new AWS execution",
            )
            note(
                "Previously completed runtime proof and cleanup. Safe no-op; no new AWS execution.",
                "32",
            )
            return
        if self.state.get("delete_intent"):
            self.report["identity"] = self.aws.environment()
            self.cleanup()
            if self.state.get("runtime_proof_complete"):
                self.validate_saved_proof()
                self.state["complete"] = True
                self.checkpoint()
                self.report.update(
                    status="aws_runtime_verified_with_exception", aws_runtime_verified=True
                )
            else:
                self.report.update(
                    status="temporary_cleanup_complete_runtime_unverified",
                    aws_runtime_verified=False,
                )
            return
        note(
            "Refreshing the current image, scan and accepted resource "
            "metadata before any AWS writes."
        )
        preflight.collect(self.report, self.aws)
        self.report["status"] = "runtime_in_progress"
        self.report["runtime_execution_authorized"] = True
        self.verify_ecr_pull_policy()
        row = self.ensure_stack()
        self.verify_live(row)
        candidate = preflight.evidence(self.report, preflight.now())
        preflight.image_review(self.report, self.aws, candidate, preflight.now())
        for action in ["preflight", "current-runtime"]:
            for name in design.NAMES.values():
                preflight.evidence(self.report, preflight.now())
                self.invoke(name, action)
        self.state["runtime_proof_complete"] = True
        self.checkpoint()
        self.report["aws_runtime_verified"] = True
        self.report["runtime_verified"] = True
        self.report["database_sql_executed"] = True
        self.report["database_sql_scope"] = "read-only transaction plus application health SELECTs"
        self.report["runtime_scope"] = (
            "two private temporary image Lambdas with hash-pinned "
            "command override, real managed-settings/Cognito/JWKS/read-only SQL "
            "and actual FastAPI startup/health; no public API release"
        )
        # Recheck retained metadata before deleting the temporary resources.
        context = preflight.OperatorContext(report=self.report, aws_call=self.aws)
        auth = preflight.AuthenticationSecretOperator(context=context)
        preflight.secrets_review(self.report, auth)
        self.cleanup()
        self.state["complete"] = True
        self.checkpoint()
        self.report.update(
            status="aws_runtime_verified_with_exception",
            scan_policy_passed=False,
            application_deployed=False,
            live_authentication_accepted=False,
            owner_created=False,
        )


def main(argv=None):
    """Cloud entry point; persisted artifacts are required for cross-run recovery."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["plan", "collect", "run", "cleanup"], default="plan")
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--resume-run", type=int)
    args = parser.parse_args(argv)
    require(
        re.fullmatch("[a-f0-9]{32}", args.operation_id),
        "Operation ID must be 32 lowercase hex characters",
    )
    source, contract = design.source_bundle()
    template = design.template(source)
    if args.mode == "plan":
        print(
            json.dumps(
                {
                    "account": ACCOUNT,
                    "region": REGION,
                    "operation_id": args.operation_id,
                    "image_digest": contract["image_digest"],
                    "template_sha256": design.canonical_hash(template),
                    "probe_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "template": template,
                    "aws_runtime_verified": False,
                    "application_deployed": False,
                },
                indent=2,
            )
        )
        return 0
    preflight.binding.actions_environment()
    directory = Path(args.directory).absolute()
    require(
        directory.resolve() == directory and not directory.exists(),
        "Use a new nonredirected evidence directory",
    )
    directory.mkdir(mode=0o700)
    report = preflight.receipt_initial()
    state = {
        "operator_revision": design.REVISION,
        "operation_id": args.operation_id,
        "execution_authorized": args.mode in {"run", "cleanup"},
    }

    def checkpoint():
        atomic_json(directory / "state.json", state)
        report["checkpoint"] = state
        atomic_json(directory / "receipt.json", report)

    def interrupt(signum, frame):
        raise KeyboardInterrupt()

    previous = signal.signal(signal.SIGTERM, interrupt)
    code = 1
    try:
        preflight.binding.verify_main(report)
        state["operator_commit"] = report["operator_commit"]
        if args.resume_run:
            state.clear()
            state.update(
                preflight.binding.restore_state(
                    args.resume_run, args.operation_id, report["operator_commit"]
                )
            )
        require(
            args.mode != "cleanup" or state.get("create_intent"),
            "Cleanup needs authenticated previous operation state",
        )
        # Cleanup does not depend on an expired image approval or unavailable build artifact.
        if args.mode != "cleanup":
            preflight.binding.collect_binding(report)
        state["execution_authorized"] = args.mode in {"run", "cleanup"}
        state.update(image_digest=preflight.binding.DIGEST, approval_id=preflight.binding.APPROVAL)
        checkpoint()
        aws = RuntimeAWS(report, state, checkpoint)
        report["identity"] = aws.environment()
        operator = RuntimeOperator(aws, state, report, directory, checkpoint)
        report.update(
            operation_id=args.operation_id,
            template_sha256=operator.template_hash,
            probe_sha256=operator.source_hash,
            approval_id=preflight.binding.APPROVAL,
            subnets=[
                r["Properties"]["VpcConfig"]["SubnetIds"][0]
                for r in template["Resources"].values()
                if r["Type"] == "AWS::Lambda::Function"
            ],
        )
        if args.mode == "collect":
            preflight.collect(report, aws)
        elif args.mode == "cleanup":
            operator.cleanup()
            report["status"] = "cleanup_complete_runtime_not_reasserted"
        else:
            operator.run()
        code = 0
    except (Exception, KeyboardInterrupt) as error:
        report["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "stopped"
        report["failure"] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        report["accepted"] = False
    finally:
        report["accepted"] = (
            code == 0
            and report.get("aws_runtime_verified") is True
            and report.get("temporary_cleanup_complete") is True
        )
        report["completed_at"] = preflight.now().isoformat()
        checkpoint()
        signal.signal(signal.SIGTERM, previous)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
