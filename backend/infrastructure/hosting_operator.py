"""User-run first TEST login deployment; no migrations, passwords or account writes."""

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import hosting_binding as binding
import hosting_design as design
import hosting_frontend as frontend
import private_runtime_preflight as pf
from private_runtime import atomic_json

ROOT = Path(__file__).parent
require, note = pf.require, pf.note
READS = {
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "get-template"),
    ("cloudformation", "list-stack-resources"),
    ("cloudformation", "describe-change-set"),
    ("cloudformation", "validate-template"),
    ("cloudformation", "describe-stack-events"),
    ("lambda", "get-function"),
    ("lambda", "get-alias"),
    ("lambda", "get-account-settings"),
    ("lambda", "get-function-concurrency"),
    ("lambda", "get-policy"),
    ("lambda", "get-function-url-config"),
    ("lambda", "list-event-source-mappings"),
    ("ecr", "get-repository-policy"),
    ("cloudfront", "get-distribution"),
    ("cloudfront", "get-cache-policy"),
    ("cloudfront", "get-origin-access-control"),
    ("s3api", "head-object"),
    ("s3api", "get-public-access-block"),
    ("s3api", "get-bucket-policy"),
    ("s3api", "get-bucket-encryption"),
    ("s3api", "get-bucket-versioning"),
    ("iam", "get-role-policy"),
    ("iam", "get-role"),
    ("iam", "list-role-policies"),
    ("iam", "list-attached-role-policies"),
    ("apigateway", "get-stage"),
    ("apigateway", "get-rest-api"),
    ("apigateway", "get-integration"),
    ("wafv2", "get-web-acl-for-resource"),
    ("wafv2", "get-web-acl"),
}
WRITES = {
    ("cloudformation", "create-change-set"),
    ("cloudformation", "execute-change-set"),
    ("cloudformation", "delete-stack"),
    ("s3api", "put-object"),
}


def digest(value):
    return hashlib.sha256(design.compact(value).encode()).hexdigest()


def configured_equal(actual, expected):
    """Compare every configured field, allowing provider-added descriptive/default fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and configured_equal(actual[k], v) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(configured_equal(a, b) for a, b in zip(actual, expected, strict=True))
        )
    return actual == expected


def flag(args, name):
    require(
        name in args and args.index(name) + 1 < len(args), "Missing scoped AWS argument " + name
    )
    return args[args.index(name) + 1]


class HostingAWS:
    def __init__(self, report, state, save, runner=subprocess.run):
        self.report, self.state, self.save, self.runner = report, state, save, runner

    def __call__(self, service, operation, *args, region=design.REGION, absent=False):
        pair = (service, operation)
        require(pair in READS | WRITES, "AWS operation outside test-login scope")
        require(
            region in {design.REGION, design.EDGE_REGION}, "AWS region outside test-login scope"
        )
        require(
            not set(args)
            & {
                "--output",
                "--debug",
                "--endpoint-url",
                "--no-verify-ssl",
                "--profile",
                "--region",
                "--cli-input-json",
                "--cli-input-yaml",
            },
            "AWS override refused",
        )
        if pair in WRITES:
            require(
                self.state.get("execution_authorized") is True, "Hosting execution not authorized"
            )
            self.guard_write(service, operation, args, region)
            if operation != "delete-stack":
                pf.evidence(self.report, pf.now())
            self.report["read_only"] = False
            self.report["cloud_writes"].append(
                {
                    "service": service,
                    "operation": operation,
                    "region": region,
                    "arguments_sha256": digest(args),
                }
            )
        call = {"service": service, "operation": operation, "region": region, "status": "started"}
        self.report["calls"].append(call)
        note(("WRITE " if pair in WRITES else "  READ ") + service + " " + operation)
        command = [
            "aws",
            service,
            operation,
            *args,
            "--region",
            region,
            "--output",
            "json",
            "--no-cli-pager",
            "--no-cli-auto-prompt",
            "--cli-error-format",
            "legacy",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "30",
        ]
        env = {
            **os.environ,
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
            "AWS_MAX_ATTEMPTS": "1" if pair in WRITES else "2",
        }
        try:
            result = self.runner(command, capture_output=True, text=True, timeout=90, env=env)
        except subprocess.TimeoutExpired:
            call["status"] = "response-uncertain" if pair in WRITES else "timeout"
            raise RuntimeError(
                service + " " + operation + " timed out; state preserved, do not repeat it manually"
            ) from None
        if result.returncode:
            error = re.search(r"\(([A-Za-z0-9]+)\)", result.stderr or "")
            code = error[1] if error else ""
            missing = (
                (pair == ("s3api", "head-object") and code in {"404", "NoSuchKey", "NotFound"})
                or (
                    pair
                    in {
                        ("lambda", "get-function"),
                        ("lambda", "get-function-url-config"),
                        ("lambda", "get-policy"),
                    }
                    and code == "ResourceNotFoundException"
                )
                or (
                    pair == ("cloudformation", "describe-stacks")
                    and code == "ValidationError"
                    and ("Stack with id " + flag(args, "--stack-name") + " does not exist")
                    in result.stderr
                )
            )
            if absent and missing:
                call["status"] = "absent"
                return None
            call.update(
                status="failed-or-uncertain" if pair in WRITES else "failed",
                error=pf.safe_error(service, operation, result),
            )
            raise RuntimeError(call["error"])
        try:
            value = json.loads(result.stdout) if result.stdout.strip() else {}
        except ValueError:
            raise RuntimeError("Invalid AWS response; state preserved") from None
        pf.no_secret_fields(value)
        require(
            not any(
                value.get(k)
                for k in [
                    "NextToken",
                    "nextToken",
                    "NextMarker",
                    "Marker",
                    "IsTruncated",
                    "position",
                ]
            ),
            "Incomplete provider pagination",
        )
        call.update(status="complete", response_sha256=digest(value))
        return value

    def guard_write(self, service, operation, args, region):
        if service == "cloudformation":
            name = flag(args, "--stack-name")
            matches = [
                (k, row)
                for k, row in self.state.get("stacks", {}).items()
                if name in {design.STACKS[k][0], row.get("stack_id")}
            ]
            require(len(matches) == 1, "Unowned stack write refused")
            key, row = matches[0]
            require(region == design.STACKS[key][1], "Wrong stack region")
            modes = {
                "create-change-set": "prepare",
                "execute-change-set": "execute",
                "delete-stack": "rollback",
            }
            require(
                self.state.get("mode") == modes[operation], "Write outside selected hosting phase"
            )
            if operation == "create-change-set":
                require(
                    row.get("create_intent")
                    and row["create_intent"]["arguments_sha256"] == digest(args),
                    "Missing exact change-set intent",
                )
                path = Path(flag(args, "--template-body").removeprefix("file://"))
                require(
                    not path.is_symlink()
                    and digest(json.loads(path.read_text())) == row["template_sha256"],
                    "Template bytes changed before request",
                )
                require(
                    flag(args, "--role-arn")
                    == ("arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation"),
                    "Unreviewed service role",
                )
            elif operation == "execute-change-set":
                require(
                    row.get("reviewed_change_set") is True
                    and row.get("execute_intent", {}).get("arguments_sha256") == digest(args),
                    "Unreviewed change set refused",
                )
            else:
                require(
                    self.state.get("cleanup_authorized") is True
                    and row.get("delete_intent", {}).get("arguments_sha256") == digest(args),
                    "Unowned cleanup refused",
                )
        else:
            require(self.state.get("mode") == "execute", "Upload outside execution phase")
            artifact = self.state["frontend"]
            name = flag(args, "--key").removeprefix(artifact["prefix"] + "/")
            require(
                name in artifact["manifest"]
                and flag(args, "--bucket") == self.state["outputs"]["FrontendBucket"],
                "Unowned frontend upload refused",
            )
            row = artifact["manifest"][name]
            source = Path(flag(args, "--body"))
            require(
                source == Path(artifact["directory"]) / name
                and not source.is_symlink()
                and hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"],
                "Frontend upload bytes differ",
            )
            require(
                flag(args, "--if-none-match") == "*"
                and flag(args, "--checksum-sha256") == row["checksum"]
                and flag(args, "--content-type") == row["content_type"]
                and flag(args, "--cache-control") == row["cache_control"]
                and flag(args, "--server-side-encryption") == "AES256",
                "Frontend upload policy differs",
            )
            require(
                self.state.get("upload_intent", {}).get("arguments_sha256") == digest(args),
                "Missing exact upload intent",
            )


class Operator:
    def __init__(self, directory, state, report, aws=None, sleep=time.sleep, clock=time.monotonic):
        self.directory, self.state, self.report = directory, state, report
        self.sleep, self.clock = sleep, clock
        self.aws = aws or HostingAWS(report, state, self.save)

    def save(self):
        atomic_json(self.directory / "state.json", self.state)
        self.report["checkpoint"] = deepcopy(self.state)

    def tags(self, key):
        return {
            "Application": "Fitfinity",
            "Environment": "test",
            "Purpose": "first-login-v1",
            "OperationId": self.state["operation_id"],
            "TemplateSHA256": self.state["stacks"][key]["template_sha256"],
        }

    def stack(self, key):
        row = self.state["stacks"][key]
        name, region = design.STACKS[key]
        result = self.aws(
            "cloudformation",
            "describe-stacks",
            "--stack-name",
            row.get("stack_id") or name,
            region=region,
            absent=True,
        )
        if result is None:
            return None
        require(len(result.get("Stacks", [])) == 1, "Ambiguous owned stack")
        remote = result["Stacks"][0]
        require(
            row.get("create_intent")
            and remote["StackName"] == name
            and re.fullmatch(
                r"arn:aws:cloudformation:"
                + region
                + ":"
                + design.ACCOUNT
                + ":stack/"
                + name
                + r"/[A-Za-z0-9-]+",
                remote["StackId"],
            ),
            "Existing stack is not owned by this operation",
        )
        require(
            not row.get("stack_id") or row["stack_id"] == remote["StackId"],
            "Owned stack ID changed",
        )
        placeholder = remote["StackStatus"] == "REVIEW_IN_PROGRESS" and not remote.get("Tags")
        if placeholder:
            # CREATE change sets have an unexecuted stack shell. Its proposed tags
            # belong to the change set; never adopt an untagged shell by name.
            require(
                row.get("create_response_received") is True
                and row.get("stack_id") == remote["StackId"]
                and row.get("change_set_id"),
                "Untagged review stack requires acknowledged creation identities",
            )
            change = self.aws(
                "cloudformation",
                "describe-change-set",
                "--stack-name",
                row["stack_id"],
                "--change-set-name",
                row["change_set_id"],
                region=region,
            )
            require(
                change.get("StackId") == row["stack_id"]
                and change.get("StackName") == name
                and change.get("ChangeSetId") == row["change_set_id"]
                and change.get("ChangeSetName") == row["change_set_name"],
                "Review stack change-set identity differs",
            )
            require(
                len(change.get("Tags", [])) == len(self.tags(key))
                and {x["Key"]: x["Value"] for x in change.get("Tags", [])} == self.tags(key),
                "Change-set ownership tags differ",
            )
            require(
                change.get("ExecutionStatus") in {"UNAVAILABLE", "AVAILABLE"}
                or row.get("execute_intent"),
                "Review stack executed outside this operation",
            )
            if not row.get("execute_intent"):
                inventory = self.aws(
                    "cloudformation",
                    "list-stack-resources",
                    "--stack-name",
                    row["stack_id"],
                    region=region,
                )
                require(
                    inventory.get("StackResourceSummaries") == [],
                    "Unexecuted review stack contains resources",
                )
            self.report.setdefault("review_stack_ownership", {})[key] = {
                "stack_id": remote["StackId"],
                "stack_tags": remote.get("Tags", []),
                "stack_role": remote.get("RoleARN"),
                "change_set_id": change["ChangeSetId"],
                "change_set_tags": change["Tags"],
            }
        else:
            require(
                len(remote.get("Tags", [])) == len(self.tags(key))
                and {x["Key"]: x["Value"] for x in remote.get("Tags", [])} == self.tags(key),
                "Stack ownership tags differ",
            )
        require(
            remote.get("RoleARN")
            == "arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation",
            "Stack service role differs",
        )
        row["stack_id"] = remote["StackId"]
        self.save()
        if remote["StackStatus"] == "DELETE_COMPLETE":
            require(row.get("delete_intent"), "Stack was deleted outside this operator")
            return None
        return remote

    def check_template(self, key, changeset=False):
        row = self.state["stacks"][key]
        args = ["--stack-name", row["stack_id"], "--template-stage", "Original"]
        if changeset:
            args += ["--change-set-name", row.get("change_set_id") or row["change_set_name"]]
        result = self.aws("cloudformation", "get-template", *args, region=design.STACKS[key][1])
        body = result["TemplateBody"]
        body = json.loads(body) if isinstance(body, str) else body
        require(
            digest(body) == row["template_sha256"],
            "Remote owned template differs; no write will continue",
        )
        return body

    def create(self, key, template):
        name, region = design.STACKS[key]
        rows = self.state.setdefault("stacks", {})
        row = rows.setdefault(
            key,
            {
                "template_sha256": digest(template),
                "change_set_name": "first-login-" + self.state["operation_id"],
            },
        )
        require(row["template_sha256"] == digest(template), "Saved deployment template differs")
        path = self.directory / (key + "-template.json")
        atomic_json(path, template)
        self.save()
        remote = self.stack(key)
        if remote is None:
            require(
                not row.get("create_intent"),
                (
                    "Create response is uncertain or owned stack disappeared; pre"
                    "serve receipt for review"
                ),
            )
            self.aws(
                "cloudformation",
                "validate-template",
                "--template-body",
                "file://" + str(path),
                region=region,
            )
            args = [
                "--stack-name",
                name,
                "--change-set-name",
                row["change_set_name"],
                "--change-set-type",
                "CREATE",
                "--client-token",
                self.state["operation_id"] + "-" + key,
                "--role-arn",
                "arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation",
                "--template-body",
                "file://" + str(path),
                "--capabilities",
                "CAPABILITY_NAMED_IAM",
                "--tags",
                design.compact([{"Key": k, "Value": v} for k, v in self.tags(key).items()]),
            ]
            row["create_intent"] = {"arguments_sha256": digest(args), "at": pf.now().isoformat()}
            self.save()
            created = self.aws("cloudformation", "create-change-set", *args, region=region)
            require(
                created.get("StackId") and created.get("Id"),
                "Change-set create returned no identity",
            )
            row.update(
                stack_id=created["StackId"],
                change_set_id=created["Id"],
                create_response_received=True,
            )
            self.save()
            remote = self.stack(key)
        if remote["StackStatus"] == "REVIEW_IN_PROGRESS":
            end = self.clock() + 180
            while True:
                change = self.aws(
                    "cloudformation",
                    "describe-change-set",
                    "--stack-name",
                    row["stack_id"],
                    "--change-set-name",
                    row.get("change_set_id") or row["change_set_name"],
                    region=region,
                )
                if change["Status"] == "CREATE_COMPLETE":
                    break
                if change["Status"] not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
                    # These reviewed templates contain ARNs/configuration only, never secret values.
                    reason = str(change.get("StatusReason", "No provider reason returned"))[:2000]
                    self.report["cloudformation_failure"] = {
                        "stack": name,
                        "status": change["Status"],
                        "reason": reason,
                    }
                    raise RuntimeError("Change-set preparation failed: " + reason)
                require(
                    self.clock() < end,
                    "Change-set preparation still running; rerun --run to resume",
                )
                self.sleep(5)
            self.check_template(key, changeset=True)
            require(
                change.get("StackId") == row["stack_id"]
                and change.get("ChangeSetName") == row["change_set_name"]
                and (
                    not row.get("change_set_id")
                    or change.get("ChangeSetId") == row["change_set_id"]
                ),
                "Change-set identity differs",
            )
            require(
                len(change.get("Tags", [])) == len(self.tags(key))
                and {x["Key"]: x["Value"] for x in change.get("Tags", [])} == self.tags(key),
                "Change-set ownership tags differ",
            )
            changes = [x.get("ResourceChange", {}) for x in change.get("Changes", [])]
            expected = {k: r["Type"] for k, r in template["Resources"].items()}
            require(
                len(changes) == len(expected)
                and {r.get("LogicalResourceId"): r.get("ResourceType") for r in changes} == expected
                and all(r.get("Action") == "Add" for r in changes),
                "Change set contains unexpected resources or non-create actions",
            )
            row["change_set_id"] = change.get("ChangeSetId", row.get("change_set_id"))
            token = digest(
                {
                    "operation": self.state["operation_id"],
                    "stack": row["stack_id"],
                    "change_set": row["change_set_id"],
                    "template": row["template_sha256"],
                }
            )
            row["review_token"] = token
            row["reviewed_changes"] = changes
            self.save()
            if self.state.get("mode") == "prepare":
                self.report.update(
                    status="change_set_review_required", review_token=token, review_stack=key
                )
                return None
            require(
                self.state.get("review_token") == token,
                "Explicit exact change-set review token required",
            )
            row["reviewed_change_set"] = True
            self.save()
            if change.get("ExecutionStatus") == "AVAILABLE":
                require(
                    not row.get("execute_intent"),
                    "Execute response is uncertain; do not replay it without receipt review",
                )
                pf.evidence(self.report, pf.now())
                args = [
                    "--stack-name",
                    row["stack_id"],
                    "--change-set-name",
                    row["change_set_name"],
                    "--client-request-token",
                    self.state["operation_id"] + "-execute-" + key,
                ]
                row["execute_intent"] = {
                    "arguments_sha256": digest(args),
                    "at": pf.now().isoformat(),
                }
                self.save()
                self.aws("cloudformation", "execute-change-set", *args, region=region)
                row["execute_response_received"] = True
                self.save()
            else:
                require(
                    change.get("ExecutionStatus") in {"EXECUTE_IN_PROGRESS", "EXECUTE_COMPLETE"},
                    "Unexpected change-set execution state",
                )
        require(row.get("execute_intent"), "Existing live stack has no owned execution intent")
        end = self.clock() + 1800
        propagation = self.clock() + 60
        while True:
            remote = self.stack(key)
            require(remote is not None, "Owned stack unexpectedly absent")
            status = remote["StackStatus"]
            note(name + ": " + status)
            if status == "CREATE_COMPLETE":
                break
            if status != "CREATE_IN_PROGRESS" and not (
                status == "REVIEW_IN_PROGRESS" and self.clock() < propagation
            ):
                events = self.aws(
                    "cloudformation",
                    "describe-stack-events",
                    "--stack-name",
                    row["stack_id"],
                    region=region,
                )
                self.report["cloudformation_failure"] = {
                    "stack": name,
                    "status": status,
                    "events": [
                        {
                            k: event.get(k)
                            for k in [
                                "LogicalResourceId",
                                "ResourceType",
                                "ResourceStatus",
                                "ResourceStatusReason",
                                "Timestamp",
                            ]
                        }
                        for event in events.get("StackEvents", [])
                        if event.get("ResourceStatus", "").endswith("FAILED")
                    ][:10],
                }
                raise RuntimeError(
                    "Stack did not complete: "
                    + status
                    + ". Provider failure details are in the receipt; do not recreate it"
                )
            require(self.clock() < end, "CloudFormation is still running; rerun --run to resume")
            self.sleep(10)
        self.check_template(key)
        resources = self.aws(
            "cloudformation", "list-stack-resources", "--stack-name", row["stack_id"], region=region
        )["StackResourceSummaries"]
        require(
            len(resources) == len(template["Resources"])
            and {r["LogicalResourceId"]: r["ResourceType"] for r in resources}
            == {k: v["Type"] for k, v in template["Resources"].items()}
            and all(r["ResourceStatus"] == "CREATE_COMPLETE" for r in resources),
            "Stack resource inventory differs",
        )
        row["resource_ids"] = {r["LogicalResourceId"]: r["PhysicalResourceId"] for r in resources}
        row["outputs"] = {r["OutputKey"]: r["OutputValue"] for r in remote.get("Outputs", [])}
        row["complete"] = True
        self.save()
        return row["outputs"]

    def upload(self):
        release, outputs = self.state["frontend"], self.state["outputs"]
        require(
            frontend.inventory(Path(release["directory"])) == release["manifest"],
            "Saved frontend artifact changed",
        )
        for name, row in release["manifest"].items():
            key = release["prefix"] + "/" + name
            args = ["--bucket", outputs["FrontendBucket"], "--key", key]
            existing = self.aws(
                "s3api", "head-object", *args, "--checksum-mode", "ENABLED", absent=True
            )
            if existing is None:
                write = args + [
                    "--body",
                    str(Path(release["directory"]) / name),
                    "--if-none-match",
                    "*",
                    "--content-type",
                    row["content_type"],
                    "--cache-control",
                    row["cache_control"],
                    "--checksum-sha256",
                    row["checksum"],
                    "--server-side-encryption",
                    "AES256",
                ]
                self.state["upload_intent"] = {
                    "arguments_sha256": digest(write),
                    "key": key,
                    "at": pf.now().isoformat(),
                }
                self.save()
                self.aws("s3api", "put-object", *write)
                existing = self.aws("s3api", "head-object", *args, "--checksum-mode", "ENABLED")
            require(
                existing.get("ContentLength") == row["bytes"]
                and existing.get("ChecksumSHA256") == row["checksum"]
                and existing.get("ContentType") == row["content_type"]
                and existing.get("CacheControl") == row["cache_control"]
                and existing.get("ServerSideEncryption") == "AES256",
                "Existing/uploaded frontend object differs; no overwrite attempted",
            )
        self.state["frontend_uploaded"] = True
        self.save()

    def cleanup(self):
        require(self.state.get("stacks"), "No owned deployment state to clean up")
        self.state["cleanup_authorized"] = True
        self.save()
        for key in ("app", "edge"):
            if key not in self.state["stacks"]:
                continue
            row = self.state["stacks"][key]
            remote = self.stack(key)
            if remote is None:
                require(row.get("delete_intent"), "Owned stack disappeared before cleanup")
                continue
            if not row.get("delete_intent"):
                require(
                    remote["StackStatus"]
                    in {
                        "CREATE_COMPLETE",
                        "CREATE_FAILED",
                        "ROLLBACK_COMPLETE",
                        "ROLLBACK_FAILED",
                        "REVIEW_IN_PROGRESS",
                    },
                    "Wait for stack operation before cleanup",
                )
                checked_template = self.check_template(
                    key, changeset=remote["StackStatus"] == "REVIEW_IN_PROGRESS"
                )
                if remote["StackStatus"] != "REVIEW_IN_PROGRESS":
                    inventory = self.aws(
                        "cloudformation",
                        "list-stack-resources",
                        "--stack-name",
                        row["stack_id"],
                        region=design.STACKS[key][1],
                    )["StackResourceSummaries"]
                    declared = {n: v["Type"] for n, v in checked_template["Resources"].items()}
                    require(
                        all(
                            r["LogicalResourceId"] in declared
                            and declared[r["LogicalResourceId"]] == r["ResourceType"]
                            for r in inventory
                        ),
                        "Foreign cleanup resource refused",
                    )
                    if row.get("resource_ids"):
                        require(
                            {r["LogicalResourceId"]: r.get("PhysicalResourceId") for r in inventory}
                            == row["resource_ids"],
                            "Cleanup physical inventory changed",
                        )
                if key == "app" and remote["StackStatus"] != "REVIEW_IN_PROGRESS":
                    resources = self.aws(
                        "cloudformation",
                        "list-stack-resources",
                        "--stack-name",
                        row["stack_id"],
                        region=design.REGION,
                    )["StackResourceSummaries"]
                    buckets = [
                        r.get("PhysicalResourceId")
                        for r in resources
                        if r["LogicalResourceId"] == "FrontendBucket"
                        and r["ResourceType"] == "AWS::S3::Bucket"
                    ]
                    if buckets:
                        self.state["retained_frontend_bucket"] = buckets[0]
                args = [
                    "--stack-name",
                    row["stack_id"],
                    "--client-request-token",
                    self.state["operation_id"] + "-cleanup-" + key,
                ]
                row["delete_intent"] = {
                    "arguments_sha256": digest(args),
                    "at": pf.now().isoformat(),
                }
                self.save()
                self.aws("cloudformation", "delete-stack", *args, region=design.STACKS[key][1])
            end = self.clock() + 1800
            propagation = self.clock() + 60
            while (remote := self.stack(key)) is not None:
                require(
                    remote["StackStatus"] == "DELETE_IN_PROGRESS" or self.clock() < propagation,
                    "Cleanup is not progressing; preserve receipt for review",
                )
                require(self.clock() < end, "Cleanup still running; rerun --cleanup to resume")
                note(design.STACKS[key][0] + ": DELETE_IN_PROGRESS")
                self.sleep(10)
            row["deleted"] = True
            self.save()
        self.state["cleaned_up"] = True
        self.save()
        self.report.update(
            status="test_login_resources_removed_frontend_bucket_retained",
            application_deployed=False,
            retained_frontend_bucket=self.state.get("retained_frontend_bucket")
            or self.state.get("outputs", {}).get("FrontendBucket"),
        )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, headers=None):
    request = Request(
        url, headers={"User-Agent": design.MARKER, "Accept-Encoding": "identity", **(headers or {})}
    )
    try:
        response = build_opener(NoRedirect()).open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        data = response.read(21 * 1024 * 1024)
        require(len(data) < 21 * 1024 * 1024, "Unexpectedly large smoke response")
        return response.status, {k.lower(): v for k, v in response.headers.items()}, data


def smoke(state, report, getter=fetch):
    domain = state["outputs"]["FrontendDomain"]
    require(re.fullmatch(r"d[a-z0-9]+\.cloudfront\.net", domain), "Unexpected frontend domain")
    origin = "https://" + domain
    proof = []
    for name, row in state["frontend"]["manifest"].items():
        status, headers, body = getter(origin + ("/" if name == "index.html" else "/" + name))
        require(
            status == 200 and hashlib.sha256(body).hexdigest() == row["sha256"],
            "Public frontend bytes differ: " + name,
        )
        require(
            headers.get("x-content-type-options") == "nosniff", "Security response headers missing"
        )
        require(
            headers.get("content-type", "").split(";", 1)[0] == row["content_type"],
            "Public frontend content type differs: " + name,
        )
        proof.append(
            {
                "path": "/" if name == "index.html" else "/" + name,
                "status": status,
                "sha256": row["sha256"],
            }
        )
    for path, expected in [
        ("/health/live", 200),
        ("/health/ready", 200),
        ("/auth/policy", 200),
        ("/me", 401),
        ("/auth/session", 401),
    ]:
        status, headers, body = getter(
            origin + path, {"Origin": origin, "Accept": "application/json"}
        )
        require(
            status == expected and "application/json" in headers.get("content-type", ""),
            "API smoke response differs: " + path,
        )
        result = json.loads(body)
        if path == "/health/live":
            require(result == {"status": "alive"}, "Live health body differs")
        if path == "/health/ready":
            require(result == {"status": "ready"}, "Readiness health body differs")
        if path == "/auth/policy":
            require(
                result
                == {
                    "password": {
                        "minimumLength": 15,
                        "maximumLength": 128,
                        "spacesAllowed": False,
                        "requiresCharacterMix": False,
                        "scheduledRotation": False,
                    },
                    "mfa": {"required": True, "method": "totp"},
                    "recovery": "verified_email",
                },
                "Live authentication policy differs",
            )
        if expected == 401:
            require(
                result.get("error", {}).get("code") == "SESSION_EXPIRED",
                "Unauthenticated route did not fail closed",
            )
        require(
            not headers.get("age")
            and "hit from cloudfront" not in headers.get("x-cache", "").lower(),
            "API response was cached",
        )
        proof.append(
            {"path": path, "status": status, "response_sha256": hashlib.sha256(body).hexdigest()}
        )
    # A request from an untrusted site must not gain a CORS credential grant.
    _, headers, _ = getter(origin + "/me", {"Origin": "https://untrusted.invalid"})
    require("access-control-allow-origin" not in headers, "Untrusted browser origin was allowed")
    report["public_smoke"] = proof
    report["test_url"] = origin
    report["unauthenticated_smoke_verified"] = True


def verify_live(operator, template):
    state, aws, report = operator.state, operator.aws, operator.report
    outputs = state["outputs"]
    ids = state["stacks"]["app"]["resource_ids"]
    configured = template["Resources"]["ApiFunction"]["Properties"]
    fn = aws(
        "lambda",
        "get-function",
        "--function-name",
        design.FUNCTION,
        "--qualifier",
        outputs["FunctionVersion"],
    )
    config = fn["Configuration"]
    require(
        fn["Code"].get("ResolvedImageUri") == design.IMAGE
        and config["FunctionName"] == design.FUNCTION
        and config["Version"] == outputs["FunctionVersion"]
        and config["State"] == "Active"
        and config["MemorySize"] == 512
        and config["Timeout"] == 25
        and config["Architectures"] == ["x86_64"],
        "Versioned API runtime differs",
    )
    expected_env = deepcopy(configured["Environment"]["Variables"])
    expected_env["FITFINITY_ALLOWED_HOSTS"] = (
        '["127.0.0.1","' + outputs["ApiId"] + '.execute-api.ap-southeast-1.amazonaws.com"]'
    )
    expected_env["FITFINITY_AUTH_ORIGINS"] = '["https://' + outputs["FrontendDomain"] + '"]'
    require(config["Environment"]["Variables"] == expected_env, "API origins/settings differ")
    vpc = config["VpcConfig"]
    require(
        set(vpc["SubnetIds"]) == set(configured["VpcConfig"]["SubnetIds"])
        and vpc["SecurityGroupIds"] == configured["VpcConfig"]["SecurityGroupIds"]
        and vpc["VpcId"] == "vpc-0b55320bb1a054441"
        and not vpc.get("Ipv6AllowedForDualStack"),
        "API private network differs",
    )
    role = aws("iam", "get-role", "--role-name", outputs["RuntimeRole"])["Role"]
    require(
        config["Role"] == role["Arn"]
        and role["AssumeRolePolicyDocument"]
        == template["Resources"]["ApiRole"]["Properties"]["AssumeRolePolicyDocument"],
        "API role identity/trust differs",
    )
    require(
        role.get("RoleName") == "fitfinity-test-hosting-api"
        and role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
        == ("arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary"),
        "Runtime boundary differs",
    )
    policy = aws(
        "iam",
        "get-role-policy",
        "--role-name",
        outputs["RuntimeRole"],
        "--policy-name",
        "FitfinityTestLogin",
    )["PolicyDocument"]
    require(policy == design.runtime_policy(), "API role permissions differ")
    require(
        aws("iam", "list-role-policies", "--role-name", outputs["RuntimeRole"])["PolicyNames"]
        == ["FitfinityTestLogin"]
        and not aws("iam", "list-attached-role-policies", "--role-name", outputs["RuntimeRole"])[
            "AttachedPolicies"
        ],
        "Unexpected API role policy",
    )
    alias = aws("lambda", "get-alias", "--function-name", design.FUNCTION, "--name", "first-test")
    require(
        alias["FunctionVersion"] == outputs["FunctionVersion"]
        and not alias.get("RoutingConfig", {}).get("AdditionalVersionWeights"),
        "API alias points at another version",
    )
    require(
        aws("lambda", "get-function-concurrency", "--function-name", design.FUNCTION)[
            "ReservedConcurrentExecutions"
        ]
        == 2,
        "API concurrency cap differs",
    )
    require(
        aws("lambda", "get-function-url-config", "--function-name", design.FUNCTION, absent=True)
        is None,
        "Unreviewed function URL exists",
    )
    require(
        aws(
            "lambda",
            "get-function-url-config",
            "--function-name",
            design.FUNCTION,
            "--qualifier",
            "first-test",
            absent=True,
        )
        is None,
        "Unreviewed alias function URL exists",
    )
    require(
        aws("lambda", "get-policy", "--function-name", design.FUNCTION, absent=True) is None,
        "Unqualified function has an invocation policy",
    )
    permission = json.loads(
        aws(
            "lambda", "get-policy", "--function-name", design.FUNCTION, "--qualifier", "first-test"
        )["Policy"]
    )
    statements = permission.get("Statement", [])
    require(
        len(statements) == 1
        and statements[0].get("Effect") == "Allow"
        and statements[0].get("Action") == "lambda:InvokeFunction"
        and statements[0].get("Principal") == {"Service": "apigateway.amazonaws.com"}
        and statements[0].get("Resource") == outputs["FunctionAlias"]
        and statements[0].get("Condition")
        == {
            "StringEquals": {"AWS:SourceAccount": design.ACCOUNT},
            "ArnLike": {
                "AWS:SourceArn": (
                    f"arn:aws:execute-api:ap-southeast-1:418638389566:{outputs['ApiId']}/test/*/*"
                )
            },
        },
        "Alias invocation permission differs",
    )
    require(
        not aws("lambda", "list-event-source-mappings", "--function-name", design.FUNCTION)[
            "EventSourceMappings"
        ],
        "Unreviewed event source exists",
    )
    distribution = aws("cloudfront", "get-distribution", "--id", outputs["DistributionId"])[
        "Distribution"
    ]
    require(
        distribution["Status"] == "Deployed"
        and distribution["DomainName"] == outputs["FrontendDomain"],
        "CloudFront is not deployed at the recorded domain",
    )
    c = distribution["DistributionConfig"]
    require(
        c["Enabled"] is True
        and c["WebACLId"] == state["stacks"]["edge"]["outputs"]["WebAclArn"]
        and c["DefaultRootObject"] == "index.html"
        and c.get("Aliases", {}).get("Quantity", 0) == 0
        and c["ViewerCertificate"].get("CloudFrontDefaultCertificate") is True,
        "CloudFront identity/security differs",
    )
    default = c["DefaultCacheBehavior"]
    require(
        default["TargetOriginId"] == "frontend"
        and default["ViewerProtocolPolicy"] == "redirect-to-https"
        and default["CachePolicyId"] == ids["StaticCache"]
        and default["ResponseHeadersPolicyId"] == ids["ResponseHeaders"]
        and not c.get("Logging", {}).get("Enabled"),
        "Frontend cache/security/logging differs",
    )
    behaviors = c["CacheBehaviors"]["Items"]
    require(
        [b["PathPattern"] for b in behaviors] == design.API_PATHS
        and all(
            b["TargetOriginId"] == "api"
            and b["CachePolicyId"] == design.CACHE_DISABLED
            and b["OriginRequestPolicyId"] == design.ORIGIN_FORWARD
            and b["ViewerProtocolPolicy"] == "https-only"
            for b in behaviors
        ),
        "API forwarding/cache policy differs",
    )
    require(
        all(
            not b.get("FunctionAssociations", {}).get("Quantity", 0)
            and not b.get("LambdaFunctionAssociations", {}).get("Quantity", 0)
            for b in [default, *behaviors]
        ),
        "Unreviewed edge function association",
    )
    origins = {o["Id"]: o for o in c["Origins"]["Items"]}
    require(
        set(origins) == {"api", "frontend"}
        and origins["api"]["DomainName"]
        == outputs["ApiId"] + ".execute-api.ap-southeast-1.amazonaws.com"
        and origins["api"]["OriginPath"] == "/test"
        and origins["api"]["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"
        and origins["frontend"]["DomainName"]
        == outputs["FrontendBucket"] + ".s3.ap-southeast-1.amazonaws.com"
        and origins["frontend"]["OriginPath"] == "/" + state["frontend"]["prefix"]
        and origins["frontend"]["OriginAccessControlId"] == ids["OriginAccess"],
        "CloudFront origins differ",
    )
    cache = aws("cloudfront", "get-cache-policy", "--id", ids["StaticCache"])["CachePolicy"][
        "CachePolicyConfig"
    ]
    require(
        configured_equal(
            cache, template["Resources"]["StaticCache"]["Properties"]["CachePolicyConfig"]
        ),
        "Static cache policy differs",
    )
    oac = aws("cloudfront", "get-origin-access-control", "--id", ids["OriginAccess"])[
        "OriginAccessControl"
    ]["OriginAccessControlConfig"]
    require(
        all(
            oac.get(k) == v
            for k, v in template["Resources"]["OriginAccess"]["Properties"][
                "OriginAccessControlConfig"
            ].items()
        ),
        "Private S3 signing differs",
    )
    bucket = outputs["FrontendBucket"]
    require(
        aws("s3api", "get-public-access-block", "--bucket", bucket)[
            "PublicAccessBlockConfiguration"
        ]
        == template["Resources"]["FrontendBucket"]["Properties"]["PublicAccessBlockConfiguration"],
        "Frontend bucket public access differs",
    )
    require(
        aws("s3api", "get-bucket-versioning", "--bucket", bucket)["Status"] == "Enabled",
        "Frontend versioning missing",
    )
    encryption = aws("s3api", "get-bucket-encryption", "--bucket", bucket)[
        "ServerSideEncryptionConfiguration"
    ]
    rules = encryption.get("Rules", [])
    require(
        len(rules) == 1
        and rules[0].get("ApplyServerSideEncryptionByDefault") == {"SSEAlgorithm": "AES256"},
        "Frontend encryption differs",
    )
    policy = json.loads(aws("s3api", "get-bucket-policy", "--bucket", bucket)["Policy"])
    bucket_arn = "arn:aws:s3:::" + bucket
    expected_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "cloudfront.amazonaws.com"},
                "Action": "s3:GetObject",
                "Resource": bucket_arn + "/*",
                "Condition": {
                    "StringEquals": {
                        "AWS:SourceArn": "arn:aws:cloudfront::418638389566:distribution/"
                        + outputs["DistributionId"]
                    }
                },
            },
            {
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [bucket_arn, bucket_arn + "/*"],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
        ],
    }
    require(policy == expected_policy, "Private bucket policy differs")
    stage = aws(
        "apigateway", "get-stage", "--rest-api-id", outputs["ApiId"], "--stage-name", "test"
    )
    settings = stage["methodSettings"].get("*/*", {})
    require(
        stage["deploymentId"] == ids["ApiDeployment"]
        and not stage.get("cacheClusterEnabled")
        and not stage.get("accessLogSettings")
        and settings.get("dataTraceEnabled") is False
        and settings.get("loggingLevel") == "OFF"
        and settings.get("throttlingRateLimit") == 5
        and settings.get("throttlingBurstLimit") == 10
        and not settings.get("cachingEnabled"),
        "API throttling/cache/logging differs",
    )
    integration = aws(
        "apigateway",
        "get-integration",
        "--rest-api-id",
        outputs["ApiId"],
        "--resource-id",
        ids["ProxyResource"],
        "--http-method",
        "ANY",
    )
    require(
        integration.get("type") == "AWS_PROXY"
        and integration.get("httpMethod") == "POST"
        and integration.get("uri")
        == "arn:aws:apigateway:ap-southeast-1:lambda:path/2015-03-31/functions/"
        + outputs["FunctionAlias"]
        + "/invocations",
        "API integration differs",
    )
    acl = aws(
        "wafv2",
        "get-web-acl-for-resource",
        "--resource-arn",
        f"arn:aws:apigateway:ap-southeast-1::/restapis/{outputs['ApiId']}/stages/test",
    )["WebACL"]
    require(
        acl["ARN"] == outputs["RegionalWebAclArn"]
        and configured_equal(acl["Rules"], design.waf("REGIONAL")["Properties"]["Rules"])
        and acl["VisibilityConfig"]["SampledRequestsEnabled"] is False,
        "Regional API WAF differs",
    )
    edge_arn = state["stacks"]["edge"]["outputs"]["WebAclArn"]
    edge_acl = aws(
        "wafv2",
        "get-web-acl",
        "--name",
        "fitfinity-test-login-cloudfront",
        "--id",
        edge_arn.rsplit("/", 1)[1],
        "--scope",
        "CLOUDFRONT",
        region=design.EDGE_REGION,
    )["WebACL"]
    require(
        edge_acl["ARN"] == edge_arn
        and configured_equal(edge_acl["Rules"], design.waf("CLOUDFRONT")["Properties"]["Rules"])
        and edge_acl["VisibilityConfig"]["SampledRequestsEnabled"] is False,
        "Edge WAF differs",
    )
    report["live_configuration_verified"] = True


def main(argv=None):
    import argparse

    from private_runtime import RuntimeOperator

    parser = argparse.ArgumentParser(description="Persistent TEST hosting; first release only")
    parser.add_argument(
        "--mode", choices=["plan", "prepare", "execute", "verify", "rollback"], default="plan"
    )
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--release-run", type=int)
    parser.add_argument("--resume-run", type=int)
    parser.add_argument("--review-token", default="")
    args = parser.parse_args(argv)
    require(re.fullmatch(r"[a-f0-9]{32}", args.operation_id), "Invalid operation ID")
    require(
        not args.directory.is_symlink() and not args.directory.exists(),
        "Evidence directory must be new and unredirected",
    )
    directory = args.directory.resolve()
    directory.mkdir(mode=0o700, parents=True)
    report = pf.receipt_initial()
    report.update(operator_revision=design.REVISION, mode=args.mode)
    state = {}
    previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.mode == "plan":
            report.update(
                status="offline_plan",
                architecture="CloudFront/private S3/regional REST API/pinned Lambda/two WAF ACLs",
                image_digest=pf.binding.DIGEST,
                source_provenance="hosting-source.json",
                procedure=[
                    "release artifact",
                    "prepare edge",
                    "review/execute edge",
                    "prepare app",
                    "review/execute app",
                    "verify",
                ],
                rollback=(
                    "Owned app then edge stacks; frontend bucket retained; no dat"
                    "abase or Owner writes"
                ),
            )
            atomic_json(directory / "edge-template.json", design.edge_template())
            return 0
        pf.binding.actions_environment()
        pf.binding.verify_main(report)
        source = report["operator_commit"]
        state = {
            "operator_revision": design.REVISION,
            "operator_commit": source,
            "operation_id": args.operation_id,
            "image_digest": pf.binding.DIGEST,
        }
        if args.resume_run:
            state, report["recovery_artifact"] = binding.restore(
                args.resume_run, args.operation_id, source
            )
        require(
            args.mode not in {"execute", "verify", "rollback"} or args.resume_run,
            "Authenticated recovery state required",
        )
        require(not state.get("cleaned_up"), "Completed rollback cannot be redeployed")
        state.update(mode=args.mode, review_token=args.review_token, execution_authorized=True)
        op = Operator(directory, state, report)
        op.save()
        report["identity"] = binding.EvidenceAWS(report).environment()
        if args.mode == "rollback":
            op.cleanup()
            return 0
        require(args.release_run and args.release_run > 0, "Verified release run required")
        new_release = binding.release(args.release_run, source, directory / "frontend")
        if state.get("frontend"):
            require(
                {k: v for k, v in state["frontend"].items() if k != "directory"}
                == {k: v for k, v in new_release.items() if k != "directory"},
                "Recovery release input differs",
            )
        state["frontend"] = new_release
        op.save()
        pf.binding.collect_binding(report)
        binding.runtime_proof(report)
        pf.collect(report, binding.EvidenceAWS(report))
        RuntimeOperator.verify_ecr_pull_policy(
            SimpleNamespace(aws=op.aws, report=report), names=[design.FUNCTION]
        )
        if args.mode in {"prepare", "execute"}:
            key = "edge" if not state.get("stacks", {}).get("edge", {}).get("complete") else "app"
            require(
                not state.get("complete"),
                "First release already complete; use verify or scoped rollback",
            )
            row = state.get("stacks", {}).get(key, {})
            if args.mode == "execute":
                require(
                    row.get("create_intent")
                    and row.get("review_token") == args.review_token
                    and re.fullmatch(r"[a-f0-9]{64}", args.review_token),
                    "Prepared change-set review token required",
                )
            template = (
                design.edge_template()
                if key == "edge"
                else design.app_template(
                    state["frontend"]["prefix"], state["stacks"]["edge"]["outputs"]["WebAclArn"]
                )
            )
            if key == "app" and not row.get("execute_intent"):
                require(
                    op.aws(
                        "lambda", "get-function", "--function-name", design.FUNCTION, absent=True
                    )
                    is None,
                    "Existing API function will not be adopted",
                )
            outputs = op.create(key, template)
            if outputs is None:
                return 0
            if key == "edge":
                report["status"] = "edge_complete_prepare_app"
                return 0
            if args.mode == "prepare":
                report["status"] = "app_complete_execute_to_resume_upload"
                return 0
            state["outputs"] = outputs
            op.save()
            op.upload()
        else:
            require(state.get("complete"), "No completed deployment to verify")
            template = design.app_template(
                state["frontend"]["prefix"], state["stacks"]["edge"]["outputs"]["WebAclArn"]
            )
        for key in ("edge", "app"):
            require(op.stack(key)["StackStatus"] == "CREATE_COMPLETE", "Owned deployment changed")
            op.check_template(key)
        verify_live(op, template)
        smoke(state, report)
        pf.evidence(report, pf.now())
        state.update(complete=True, completed_at=pf.now().isoformat())
        op.save()
        report.update(
            status="hosting_deployed_sign_in_acceptance_pending", application_deployed=True
        )
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        report.update(
            status="stopped",
            error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__,
        )
        note("STOPPED — " + report["error"], "31")
        return 1
    finally:
        report["checkpoint"] = deepcopy(state)
        report["completed_at"] = pf.now().isoformat()
        atomic_json(directory / "receipt.json", report)
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
