"""PrivateEgressOperator: explicit per-run dependencies and receipt state."""

import base64
import datetime
import hashlib
import io
import json
import os
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from decimal import Decimal
from pathlib import Path

from egress_execution import EgressOperator
from operator_context import OperatorContext


class PrivateEgressOperator:
    def __init__(self, *, context=None, aws_call=None):
        self.context = context if context is not None else OperatorContext(aws_call=aws_call)
        self.TEMPLATE = json.loads(
            (Path(__file__).resolve().parent / "test-private-egress-probe.json").read_text()
        )
        self.e = EgressOperator(aws_call=self.context.aws_call)
        self.ACCOUNT, self.REGION, self.PROFILE = self.e.ACCOUNT, self.e.REGION, self.e.PROFILE
        self.STACK = "fitfinity-test-private-egress-probe"
        self.SHA = hashlib.sha256(json.dumps(self.TEMPLATE, sort_keys=True).encode()).hexdigest()
        self.TAGS = {
            "Application": "Fitfinity",
            "Environment": "test",
            "ManagedBy": "fitfinity-private-probe",
            "TemplateSHA256": self.SHA,
        }
        if context is None:
            self.context.report.update(
                {
                    "account": self.ACCOUNT,
                    "region": self.REGION,
                    "stack": self.STACK,
                    "template_sha256": self.SHA,
                    "private_runtime_connectivity_verified": False,
                    "cleanup_complete": False,
                    "app_deployed": False,
                }
            )
        self.require = self.e.require
        self.note = self.e.note
        self.ALLOWED = {
            ("sts", "get-caller-identity"),
            ("freetier", "get-account-plan-state"),
            ("cloudformation", "describe-stacks"),
            ("cloudformation", "get-template"),
            ("cloudformation", "validate-template"),
            ("cloudformation", "create-stack"),
            ("cloudformation", "delete-stack"),
            ("cloudformation", "describe-events"),
            ("cloudformation", "list-stack-resources"),
            ("lambda", "get-function"),
            ("lambda", "invoke"),
        }

    def aws(self, service, operation, *args, region=None, missing=False):
        if region is None:
            region = self.REGION
        self.require((service, operation) in self.ALLOWED, "Operation refused")
        if operation in {"create-stack", "delete-stack"}:
            self.require(
                "--stack-name" in args and args[args.index("--stack-name") + 1] == self.STACK,
                "Only the temporary probe stack may be changed",
            )
        if operation == "invoke":
            self.require(
                args[args.index("--function-name") + 1]
                in ["fitfinity-test-egress-probe-a", "fitfinity-test-egress-probe-b"],
                "Only fixed probe functions may be invoked",
            )
        if self.context.aws_call is not None:
            return self.context.aws_call(service, operation, *args, region=region, missing=missing)
        p = subprocess.run(
            [
                "aws",
                service,
                operation,
                *args,
                "--profile",
                self.PROFILE,
                "--region",
                region,
                "--output",
                "json",
                "--no-cli-pager",
                "--no-cli-auto-prompt",
                "--cli-connect-timeout",
                "10",
                "--cli-read-timeout",
                "60",
            ],
            capture_output=True,
            text=True,
            timeout=150,
        )
        if p.returncode:
            if (
                missing
                and operation == "describe-stacks"
                and "(ValidationError)" in p.stderr
                and f"Stack with id {self.STACK} does not exist" in p.stderr
            ):
                return None
            raise RuntimeError(service + " " + operation + ": " + p.stderr.strip())
        return json.loads(p.stdout) if p.stdout.strip() else {}

    def stack(self):
        r = self.aws("cloudformation", "describe-stacks", "--stack-name", self.STACK, missing=True)
        if r is None:
            return None
        s = r["Stacks"][0]
        self.require(
            s["StackId"].startswith(
                f"arn:aws:cloudformation:{self.REGION}:{self.ACCOUNT}:stack/{self.STACK}/"
            ),
            "Probe stack identity differs",
        )
        self.require(
            {x["Key"]: x["Value"] for x in s.get("Tags", [])} == self.TAGS,
            "Probe stack ownership differs",
        )
        t = self.aws("cloudformation", "get-template", "--stack-name", self.STACK)["TemplateBody"]
        self.require(
            (json.loads(t) if isinstance(t, str) else t) == self.TEMPLATE, "Probe template differs"
        )
        return s

    def check_network(self):
        s = self.e.stack_info()
        self.require(
            s["StackId"] == self.e.FAILED_ARN and s["StackStatus"] == "UPDATE_COMPLETE",
            "Accepted NAT stack is not complete",
        )
        # Use the existing cloud configuration checks, without running its SSM host command.
        self.e.host_check = lambda _: {"not_run": "cloud configuration review only"}
        self.e.verify(s)
        self.require(
            self.e.context.report["outputs"].get("PublicIp") == "52.77.93.192",
            "NAT public IP changed",
        )
        for arn in [self.e.pf.FOUNDATION, self.e.pf.COGNITO]:
            row = self.aws("cloudformation", "describe-stacks", "--stack-name", arn)["Stacks"][0]
            self.require(
                row["StackId"] == arn
                and row["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
                "Foundation/Cognito state differs",
            )

    def costs(self):
        rate = self.e.pf.rate
        base = {
            "productFamily": "Compute Instance",
            "operatingSystem": "Linux",
            "tenancy": "Shared",
            "preInstalledSw": "NA",
            "capacitystatus": "Used",
            "instanceType": "t4g.micro",
        }
        p = {
            "nat_compute": rate("AmazonEC2", base, "Hrs"),
            "nat_storage": rate(
                "AmazonEC2", {"productFamily": "Storage", "volumeApiName": "gp3"}, "GB-Mo"
            ),
            "ipv4": rate("AmazonVPC", {"usagetype": "APS1-PublicIPv4:InUseAddress"}, "Hrs"),
        }
        db = {"databaseEngine": "PostgreSQL", "deploymentOption": "Single-AZ"}
        p["db_compute"] = rate(
            "AmazonRDS",
            {**db, "instanceType": "db.t4g.micro", "productFamily": "Database Instance"},
            "Hrs",
        )
        p["db_storage"] = rate(
            "AmazonRDS",
            {**db, "productFamily": "Database Storage", "volumeType": "General Purpose-GP3"},
            "GB-Mo",
        )

        def d(k):
            return Decimal(p[k]["usd"])

        nat = 730 * (d("nat_compute") + d("ipv4")) + 8 * d("nat_storage")
        foundation = 730 * d("db_compute") + 20 * d("db_storage") + Decimal("0.40")
        self.context.report["prices"] = p
        self.context.report["monthly_base_usd"] = {
            "foundation": str(foundation),
            "nat": str(nat),
            "combined": str(foundation + nat),
            "secret_allowance_not_live_quoted": "0.40",
        }
        self.note(
            f"Current quoted rates: foundation US${foundation:.2f}/month; NAT US${nat:.2f}/month; "
            f"combined US${foundation + nat:.2f}/month (730 hours, 20 GiB DB, 8 GiB NAT)."
        )
        self.note(
            "Secret allowance US$0.40 is a planning assumption. ECR, app "
            "services, transfer, tax/FX, backups and other usage are extr"
            "a; this is not billed spend or a cap."
        )

    def verify_function(self, suffix):
        name = "fitfinity-test-egress-probe-" + suffix.lower()
        r = self.aws("lambda", "get-function", "--function-name", name)
        c = r["Configuration"]
        p = self.TEMPLATE["Resources"]["Probe" + suffix]["Properties"]
        self.require(
            c.get("State") == "Active" and c.get("LastUpdateStatus", "Successful") == "Successful",
            "Probe function not ready",
        )
        self.require(
            c["FunctionArn"] == f"arn:aws:lambda:{self.REGION}:{self.ACCOUNT}:function:{name}",
            "Function identity differs",
        )
        self.require(
            c["VpcConfig"]["SubnetIds"] == p["VpcConfig"]["SubnetIds"]
            and c["VpcConfig"]["SecurityGroupIds"] == p["VpcConfig"]["SecurityGroupIds"]
            and c["VpcConfig"]["VpcId"] == self.e.VPC
            and not c["VpcConfig"].get("Ipv6AllowedForDualStack", False),
            "Probe VPC configuration differs",
        )
        self.require(
            c["Runtime"] == "python3.12"
            and c["Handler"] == "index.handler"
            and c["Architectures"] == ["arm64"]
            and c["Timeout"] == 30
            and c["MemorySize"] == 128,
            "Probe runtime differs",
        )
        self.require(
            not c.get("Environment", {}).get("Variables") and not c.get("Layers"),
            "Unexpected probe environment/layers",
        )
        # Download only AWS's returned temporary code URL; never log the URL.
        self.require(r["Code"]["Location"].startswith("https://"), "Unexpected code URL scheme")
        diagnostic = {"stage": "download", "function": name}
        self.context.report.setdefault("code_verification", {})[suffix] = diagnostic
        try:
            with urllib.request.urlopen(r["Code"]["Location"], timeout=20) as f:
                blob = f.read(2097153)
        except urllib.error.HTTPError as ex:
            diagnostic.update(error_type="HTTPError", http_status=ex.code)
            raise RuntimeError(
                "Probe code download returned HTTP " + str(ex.code) + "; signed URL omitted"
            ) from None
        except (ssl.SSLError, urllib.error.URLError, TimeoutError, OSError) as ex:
            reason = getattr(ex, "reason", ex)
            certificate = isinstance(reason, ssl.SSLCertVerificationError)
            diagnostic.update(
                error_type=type(ex).__name__,
                reason_type=type(reason).__name__,
                certificate_verification_failed=certificate,
            )
            message = (
                "Local Python could not verify the HTTPS certificate for the code download"
                if certificate
                else "Probe code download failed (" + type(reason).__name__ + ")"
            )
            raise RuntimeError(message + "; no invocation occurred for this function") from None
        diagnostic["stage"] = "package_hash"
        diagnostic["download_bytes"] = len(blob)
        self.require(len(blob) <= 2097152, "Probe code package too large")
        digest = base64.b64encode(hashlib.sha256(blob).digest()).decode()
        diagnostic.update(download_sha256=digest, aws_sha256=c["CodeSha256"])
        self.require(
            digest == c["CodeSha256"],
            "Downloaded package SHA-256 differs from AWS; invocation blocked",
        )
        diagnostic["stage"] = "archive"
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                names = z.namelist()
                diagnostic["entry_names"] = names[:20]
                self.require(
                    names == ["index.py"],
                    (
                        "Probe archive entries differ from the expected single index."
                        "py; invocation blocked"
                    ),
                )
                self.require(z.getinfo("index.py").file_size <= 131072, "Probe source too large")
                actual = z.read("index.py")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as ex:
            if isinstance(ex, RuntimeError) and str(ex).startswith("Probe "):
                raise
            diagnostic["error_type"] = type(ex).__name__
            raise RuntimeError(
                "Probe archive could not be validated ("
                + type(ex).__name__
                + "); invocation blocked"
            ) from None
        diagnostic["stage"] = "source_bytes"
        expected = p["Code"]["ZipFile"].encode()
        diagnostic.update(
            actual_source_sha256=hashlib.sha256(actual).hexdigest(),
            expected_source_sha256=hashlib.sha256(expected).hexdigest(),
            actual_source_bytes=len(actual),
            expected_source_bytes=len(expected),
        )
        self.require(
            actual == expected,
            "Probe index.py bytes differ from the reviewed source; invocation blocked",
        )
        diagnostic["stage"] = "verified"
        return name

    def confirm(self):
        self.note(
            "New run creates; exact existing-stack rerun reuses 5 tempora"
            "ry resources: two private Lambda probes, one execution role,"
            " two 1-day log groups. No public URL, DB calls or secrets pe"
            "rmissions."
        )
        self.note(
            "Invokes each once (128 MiB, 30-second timeout). Small Lambda"
            "/log/transfer usage may consume credits; no additional alway"
            "s-on compute."
        )
        self.note(
            "After BOTH probes pass, deletes ONLY this exact temporary st"
            "ack and its test logs. On failure resources are preserved fo"
            "r review. Existing foundation, Cognito and NAT remain."
        )
        with open("/dev/tty", "w") as f:
            f.write("To run this test and its successful-test cleanup, type " + self.ACCOUNT + ": ")
            f.flush()
        with open("/dev/tty") as f:
            self.require(f.readline().strip() == self.ACCOUNT, "Confirmation did not match")

    def main(self):
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
        self.require(
            not any(
                v and (k in forbidden or k.startswith("AWS_ENDPOINT_URL"))
                for k, v in os.environ.items()
            ),
            "Remove AWS credential/config/endpoint overrides",
        )
        os.environ.update(
            AWS_PAGER="",
            AWS_CLI_AUTO_PROMPT="off",
            AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
            AWS_MAX_ATTEMPTS="2",
        )
        self.note("Fitfinity AWS — private-subnet HTTPS probe and current base rates")
        who = self.aws("sts", "get-caller-identity")
        self.require(
            who.get("Account") == self.ACCOUNT
            and who.get("Arn") == f"arn:aws:iam::{self.ACCOUNT}:user/fitfinity-deployer",
            "Expected test identity was not verified",
        )
        plan = self.aws("freetier", "get-account-plan-state", region="us-east-1")
        self.context.report["plan"] = plan
        self.require(
            plan.get("accountPlanType") == "FREE" and plan.get("accountPlanStatus") == "ACTIVE",
            "Account plan changed; review required",
        )
        self.check_network()
        self.costs()
        s = self.stack()
        self.require(
            s is None or s["StackStatus"] in {"CREATE_IN_PROGRESS", "CREATE_COMPLETE"},
            "Probe stack needs review; no automatic repair",
        )
        with tempfile.TemporaryDirectory(prefix="fitfinity-private-probe-") as td:
            path = Path(td) / "template.json"
            path.write_text(json.dumps(self.TEMPLATE))
            self.aws(
                "cloudformation", "validate-template", "--template-body", "file://" + str(path)
            )
            started = time.monotonic()
            self.confirm()
            self.require(
                time.monotonic() - started < 600,
                "Review exceeded 10 minutes; rerun for fresh prices",
            )
            self.check_network()
            if s is None:
                self.require(self.stack() is None, "Probe stack appeared; rerun to inspect")
                self.context.report["create_attempted"] = True
                made = self.aws(
                    "cloudformation",
                    "create-stack",
                    "--stack-name",
                    self.STACK,
                    "--template-body",
                    "file://" + str(path),
                    "--capabilities",
                    "CAPABILITY_IAM",
                    "--disable-rollback",
                    "--tags",
                    *["Key=" + k + ",Value=" + v for k, v in self.TAGS.items()],
                )
                self.context.report["stack_id"] = made["StackId"]
            deadline = time.monotonic() + 1500
            while True:
                s = self.stack()
                self.require(s is not None, "Probe stack missing")
                self.context.report["stack_id"] = s["StackId"]
                self.note("Probe stack: " + s["StackStatus"])
                if s["StackStatus"] == "CREATE_COMPLETE":
                    break
                if s["StackStatus"] != "CREATE_IN_PROGRESS":
                    self.context.report["failures"] = self.aws(
                        "cloudformation",
                        "describe-events",
                        "--stack-name",
                        self.STACK,
                        "--filters",
                        "FailedEvents=true",
                    )
                    raise RuntimeError("Probe creation failed; inspect receipt")
                self.require(
                    time.monotonic() < deadline, "Provisioning timed out; resources preserved"
                )
                time.sleep(15)
            self.context.report["results"] = {}
            for suffix in ["A", "B"]:
                name = self.verify_function(suffix)
                output = Path(td) / ("result-" + suffix + ".json")
                metadata = self.aws(
                    "lambda",
                    "invoke",
                    "--function-name",
                    name,
                    "--invocation-type",
                    "RequestResponse",
                    "--payload",
                    "{}",
                    "--cli-binary-format",
                    "raw-in-base64-out",
                    str(output),
                )
                self.require(
                    metadata.get("StatusCode") == 200 and not metadata.get("FunctionError"),
                    "Subnet " + suffix + " probe failed; inspect its CloudWatch test log",
                )
                proof = json.loads(output.read_text())
                self.context.report["results"][suffix] = proof
                self.require(
                    proof.get("https_verified") is True
                    and proof.get("egress_ip") == "52.77.93.192"
                    and 1 <= proof.get("jwks_key_count", 0) <= 8,
                    "Subnet " + suffix + " proof differs",
                )
                self.note("Subnet " + suffix + ": HTTPS and NAT public IP passed.")
            self.context.report["private_runtime_connectivity_verified"] = True
            self.require(
                self.stack()["StackId"] == self.context.report["stack_id"], "Cleanup target changed"
            )
            rows = self.aws("cloudformation", "list-stack-resources", "--stack-name", self.STACK)[
                "StackResourceSummaries"
            ]
            self.require(
                len(rows) == 5
                and {x["LogicalResourceId"] for x in rows} == set(self.TEMPLATE["Resources"]),
                "Unexpected resources; cleanup refused",
            )
            self.require(
                all(
                    x["ResourceType"] == self.TEMPLATE["Resources"][x["LogicalResourceId"]]["Type"]
                    for x in rows
                ),
                "Unexpected resource types",
            )
            self.context.report["cleanup_requested"] = True
            self.aws("cloudformation", "delete-stack", "--stack-name", self.STACK)
            deadline = time.monotonic() + 1800
            while True:
                r = self.aws(
                    "cloudformation", "describe-stacks", "--stack-name", self.STACK, missing=True
                )
                if r is None or r["Stacks"][0]["StackStatus"] == "DELETE_COMPLETE":
                    break
                self.require(
                    r["Stacks"][0]["StackId"] == self.context.report["stack_id"]
                    and r["Stacks"][0]["StackStatus"] == "DELETE_IN_PROGRESS",
                    "Cleanup needs review",
                )
                self.require(
                    time.monotonic() < deadline,
                    (
                        "Cleanup still pending; receipt records successful tests but "
                        "not complete cleanup"
                    ),
                )
                self.note(
                    "Waiting for probe cleanup, including Lambda network interfaces (15 seconds)..."
                )
                time.sleep(15)
            self.context.report["cleanup_complete"] = True
            self.note(
                "PRIVATE HTTPS PROBE PASSED — both application subnets; tempo"
                "rary stack removed. App deployment and DB authentication rem"
                "ain pending."
            )

    def save(self):
        self.context.report["checked_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        folder = Path.home() / "Downloads"
        folder.mkdir(exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix="Fitfinity_AWS_Private_Egress_Probe_", suffix=".json", dir=folder
        )
        with os.fdopen(fd, "w") as f:
            json.dump(self.context.report, f, indent=2)
        self.note("Receipt: " + name)

    def run(self):
        try:
            self.main()
        except (Exception, KeyboardInterrupt) as ex:
            self.context.report["error"] = str(ex) or "Interrupted"
            self.note("STOPPED: " + self.context.report["error"])
            self.save()
            raise SystemExit(1) from None
        self.save()
