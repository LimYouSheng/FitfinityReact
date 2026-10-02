"""EgressOperator: explicit per-run dependencies and receipt state."""

import copy
import datetime
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from egress_preflight import EgressPreflightOperator
from operator_context import OperatorContext


class EgressOperator:
    def __init__(self, *, context=None, aws_call=None):
        self.context = context if context is not None else OperatorContext(aws_call=aws_call)
        self.TEMPLATE = json.loads(
            (Path(__file__).resolve().parent / "test-egress.json").read_text()
        )
        self.TEMPLATE_SHA = "ffe82f91c2715188f9a399d76f7e79ca7a24e1f1011d06195cfbc736e5644952"
        self.CHECK_COMMAND = (
            "python3 - <<'FITFINITY_HOST_CHECK'\nimport hashlib,http.clien"
            "t,json,pathlib,subprocess,time\nexpected={'/etc/sysctl.d/90-f"
            "itfinity-nat.conf': '2b4e9c488f9437c6c8df8dffb82beb76ba8cde5"
            "00fd44c39740ffb0697a87333', '/usr/local/sbin/fitfinity-nat-s"
            "tart': '1cda50ef12e944b1c4e00a70b77046d64e2535ac1f8df985e732"
            "943763679e3e', '/etc/systemd/system/fitfinity-nat.service': "
            "'7552bc04391529e869eeee08e70138cd044e4d6c395f168c175af1042eb"
            "8608f'}\nfor attempt in range(40):\n    if pathlib.Path('/var/"
            "lib/fitfinity-nat-ready').is_file():break\n    time.sleep(15)"
            "\nassert pathlib.Path('/var/lib/fitfinity-nat-ready').is_file"
            "(), 'Bootstrap not ready'\nassert all(hashlib.sha256(pathlib."
            "Path(p).read_bytes()).hexdigest()==h for p,h in expected.ite"
            "ms()), 'Installed NAT files differ'\nsubprocess.run(['systemc"
            "tl','is-active','--quiet','fitfinity-nat.service'],check=Tru"
            "e)\nforward=subprocess.check_output(['sysctl','-n','net.ipv4."
            "ip_forward'],text=True).strip()\nassert forward=='1'\nrules=js"
            "on.loads(subprocess.check_output(['nft','-j','list','table',"
            "'ip','fitfinity_nat'],text=True))['nftables']\nchains={x['cha"
            "in']['name']:x['chain'] for x in rules if 'chain' in x}\nasse"
            "rt set(chains)=={'forward','postrouting'}\nassert chains['for"
            "ward']['policy']=='drop' and chains['forward']['hook']=='for"
            "ward'\nassert chains['postrouting']['type']=='nat' and chains"
            "['postrouting']['hook']=='postrouting'\ncounts={k:sum(1 for x"
            " in rules if 'rule' in x and x['rule']['chain']==k) for k in"
            " chains}\nassert counts=={'forward':4,'postrouting':1}\nconn=h"
            "ttp.client.HTTPSConnection('cognito-idp.ap-southeast-1.amazo"
            "naws.com',timeout=10)\nconn.request('GET','/ap-southeast-1_La"
            "0Y3MXCj/.well-known/jwks.json')\nresponse=conn.getresponse();"
            "assert response.status==200\nbody=response.read(131073);asser"
            "t len(body)<=131072\nkeys=json.loads(body)['keys'];assert 1<="
            "len(keys)<=8\nprint(json.dumps({'bootstrap_files_match':True,"
            "'ip_forward':forward,'forward_policy':'drop','forward_rule_c"
            "ount':counts['forward'],'nat_rule_count':counts['postrouting"
            "'],'jwks_key_count':len(keys),'forwarding_probe_from_private"
            "_subnet':False}))\nFITFINITY_HOST_CHECK\n"
        )
        self.pf = EgressPreflightOperator(aws_call=self.context.aws_call)
        self.ACCOUNT, self.REGION, self.PROFILE, self.VPC = (
            self.pf.ACCOUNT,
            self.pf.REGION,
            self.pf.PROFILE,
            self.pf.VPC,
        )
        self.STACK = "fitfinity-test-egress"
        self.FAILED_ARN = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fit"
            "finity-test-egress/91ae3440-b683-11f1-a1c7-0216717a447b"
        )
        self.OLD_SHA = "7f932464a445c2a1b2bb6607bfae46edb37623635a4ee42bf30fbd76053c0a1c"
        self.OLD_TEMPLATE = copy.deepcopy(self.TEMPLATE)
        self.OLD_TEMPLATE["Resources"]["NatInstance"]["Properties"]["BlockDeviceMappings"][0][
            "Ebs"
        ]["Throughput"] = 125
        self.TAGS = {
            "Application": "Fitfinity",
            "Environment": "test",
            "ManagedBy": "fitfinity-egress-operator",
            "TemplateSHA256": self.TEMPLATE_SHA,
        }
        self.ALLOWED = self.pf.ALLOWED | {
            ("cloudformation", "update-stack"),
            ("cloudformation", "describe-events"),
            ("cloudformation", "get-template"),
            ("cloudformation", "validate-template"),
            ("cloudformation", "create-stack"),
            ("cloudformation", "list-stack-resources"),
            ("cloudformation", "describe-stack-events"),
            ("ec2", "describe-network-interfaces"),
            ("ec2", "describe-volumes"),
            ("ec2", "describe-instance-credit-specifications"),
            ("ssm", "describe-instance-information"),
            ("ssm", "send-command"),
            ("ssm", "get-command-invocation"),
        }
        if context is None:
            self.context.report.update(
                {
                    "account": self.ACCOUNT,
                    "region": self.REGION,
                    "stack": self.STACK,
                    "template_sha256": self.TEMPLATE_SHA,
                    "write_attempted": False,
                    "selected_instance_type": "t4g.micro",
                    "egress_configuration_verified": False,
                    "private_runtime_connectivity_verified": False,
                    "app_deployed": False,
                }
            )
        self.note = self.pf.note
        self.require = self.pf.require

    def aws(self, service, operation, *args, region=None, missing_stack=False):
        if region is None:
            region = self.REGION
        self.require((service, operation) in self.ALLOWED, "Operation refused")
        if operation == "send-command":
            self.require(
                "--parameters" in args
                and json.loads(args[args.index("--parameters") + 1])
                == {"commands": [self.CHECK_COMMAND], "executionTimeout": ["900"]},
                "Only the fixed non-secret host check may run",
            )
        if self.context.aws_call is not None:
            return self.context.aws_call(
                service, operation, *args, region=region, missing=missing_stack
            )
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
                "30",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if p.returncode:
            if (
                missing_stack
                and operation == "describe-stacks"
                and "(ValidationError)" in p.stderr
                and f"Stack with id {self.STACK} does not exist" in p.stderr
            ):
                return None
            raise RuntimeError(service + " " + operation + ": " + p.stderr.strip())
        return json.loads(p.stdout) if p.stdout.strip() else {}

    def stack_info(self, missing=False):
        result = self.aws(
            "cloudformation", "describe-stacks", "--stack-name", self.STACK, missing_stack=missing
        )
        if result is None:
            return None
        s = result["Stacks"][0]
        self.require(
            s["StackId"].startswith(
                f"arn:aws:cloudformation:{self.REGION}:{self.ACCOUNT}:stack/{self.STACK}/"
            ),
            "Stack identity differs",
        )
        tags = {x["Key"]: x["Value"] for x in s.get("Tags", [])}
        self.require(
            all(tags.get(k) == v for k, v in self.TAGS.items() if k != "TemplateSHA256"),
            "Existing stack ownership differs",
        )
        self.require(
            tags.get("TemplateSHA256") in {self.TEMPLATE_SHA, self.OLD_SHA},
            "Unrecognized template ownership hash",
        )
        self.require(
            s.get("EnableTerminationProtection") is True, "Stack termination protection missing"
        )
        live = self.aws(
            "cloudformation",
            "get-template",
            "--stack-name",
            s["StackId"],
            "--template-stage",
            "Original",
        )["TemplateBody"]
        if isinstance(live, str):
            live = json.loads(live)
        old = live == self.OLD_TEMPLATE and tags.get("TemplateSHA256") == self.OLD_SHA
        self.require(
            live == self.TEMPLATE or old, "Existing stack template differs; review required"
        )
        if old:
            self.require(
                s["StackId"] == self.FAILED_ARN and s["StackStatus"] == "CREATE_FAILED",
                "Old template is only recoverable in the exact failed stack",
            )
        s["_recover_old"] = old
        return s

    def recovery_guard(self, s):
        self.require(
            s["StackId"] == self.FAILED_ARN
            and s["StackStatus"] == "CREATE_FAILED"
            and s.get("_recover_old"),
            "Recovery target changed",
        )
        rows = self.aws("cloudformation", "list-stack-resources", "--stack-name", self.FAILED_ARN)[
            "StackResourceSummaries"
        ]
        self.require(
            not rows, "Existing resource records require review before recovery; no update sent"
        )
        events = self.aws(
            "cloudformation",
            "describe-events",
            "--stack-name",
            self.FAILED_ARN,
            "--filters",
            "FailedEvents=true",
        )
        failures = [
            x for x in events.get("OperationEvents", []) if x.get("EventType") == "VALIDATION_ERROR"
        ]
        self.require(
            len(failures) == 1
            and failures[0].get("LogicalResourceId") == "NatInstance"
            and failures[0].get("ValidationStatusReason") == "Unsupported property [Throughput]"
            and failures[0].get("ValidationPath")
            == "/Resources/NatInstance/Properties/BlockDeviceMappings/0/Ebs",
            "Validation failure differs from reviewed receipt",
        )
        self.context.report["recovery_events"] = events

    def confirm(self):
        with open("/dev/tty", "w") as t:
            t.write(
                "To provision this NAT instance and accept its running costs, type "
                + self.ACCOUNT
                + ": "
            )
            t.flush()
        with open("/dev/tty") as t:
            self.require(
                t.readline().strip() == self.ACCOUNT,
                "Confirmation did not match; no creation request sent",
            )

    def host_check(self, instance_id):
        deadline = time.monotonic() + 1200
        while True:
            items = self.aws(
                "ssm",
                "describe-instance-information",
                "--filters",
                "Key=InstanceIds,Values=" + instance_id,
            )["InstanceInformationList"]
            if len(items) == 1 and items[0].get("PingStatus") == "Online":
                break
            self.require(
                time.monotonic() < deadline,
                "SSM not online yet; resources remain running. Upload receipt for review.",
            )
            self.note("Waiting for NAT bootstrap and SSM (15 seconds)...")
            time.sleep(15)
        response = self.aws(
            "ssm",
            "send-command",
            "--instance-ids",
            instance_id,
            "--document-name",
            "AWS-RunShellScript",
            "--parameters",
            json.dumps({"commands": [self.CHECK_COMMAND], "executionTimeout": ["900"]}),
            "--timeout-seconds",
            "120",
            "--comment",
            "Fitfinity fixed non-secret NAT bootstrap check",
        )
        command = response["Command"]["CommandId"]
        self.context.report["host_check_command_id"] = command
        deadline = time.monotonic() + 1000
        while True:
            try:
                result = self.aws(
                    "ssm",
                    "get-command-invocation",
                    "--command-id",
                    command,
                    "--instance-id",
                    instance_id,
                )
            except RuntimeError as e:
                if "InvocationDoesNotExist" not in str(e):
                    raise
                result = {"Status": "Pending"}
            if result["Status"] == "Success":
                proof = json.loads(result["StandardOutputContent"])
                self.require(
                    proof.get("bootstrap_files_match") is True
                    and proof.get("forward_policy") == "drop"
                    and proof.get("forward_rule_count") == 4
                    and proof.get("nat_rule_count") == 1
                    and proof.get("ip_forward") == "1"
                    and proof.get("jwks_key_count", 0) > 0,
                    "NAT host proof differs",
                )
                return proof
            self.require(
                result["Status"] in {"Pending", "InProgress", "Delayed"},
                "NAT host check failed: "
                + result["Status"]
                + "; bootstrap or networking needs review. No automatic cleanup.",
            )
            self.require(
                time.monotonic() < deadline, "Host check timed out; resources remain running"
            )
            time.sleep(5)

    def verify(self, s, *, check_host=True):
        rows = self.aws("cloudformation", "list-stack-resources", "--stack-name", s["StackId"])[
            "StackResourceSummaries"
        ]
        self.require(
            len(rows) == len(self.TEMPLATE["Resources"])
            and {x["LogicalResourceId"] for x in rows} == set(self.TEMPLATE["Resources"]),
            "Unexpected resource inventory",
        )
        for x in rows:
            self.require(
                x["ResourceStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
                and x["ResourceType"] == self.TEMPLATE["Resources"][x["LogicalResourceId"]]["Type"],
                "Unexpected resource state/type",
            )
        ids = {x["LogicalResourceId"]: x["PhysicalResourceId"] for x in rows}
        instance = self.aws("ec2", "describe-instances", "--instance-ids", ids["NatInstance"])[
            "Reservations"
        ][0]["Instances"][0]
        self.require(
            instance.get("ImageId") == "ami-021e6de04c7a84a9f"
            and instance.get("InstanceType") == "t4g.micro"
            and instance.get("VpcId") == self.VPC
            and instance.get("SubnetId") == ids["PublicSubnet"]
            and instance.get("State", {}).get("Name") == "running",
            "Instance configuration differs",
        )
        self.require(
            instance.get("Placement", {}).get("AvailabilityZone") == "ap-southeast-1a",
            "NAT AZ differs",
        )
        metadata = instance.get("MetadataOptions", {})
        self.require(
            metadata.get("HttpTokens") == "required"
            and metadata.get("HttpPutResponseHopLimit") == 1,
            "IMDSv2 protection differs",
        )
        self.require(not instance.get("KeyName"), "Unexpected SSH key")
        # Exact CloudFormation template was verified; native host file hashes are checked below.
        eni = self.aws(
            "ec2", "describe-network-interfaces", "--network-interface-ids", ids["NatInterface"]
        )["NetworkInterfaces"][0]
        self.require(
            eni.get("SourceDestCheck") is False
            and eni.get("Attachment", {}).get("InstanceId") == ids["NatInstance"]
            and {g["GroupId"] for g in eni.get("Groups", [])} == {ids["NatSecurityGroup"]},
            "NAT ENI configuration differs",
        )
        self.require(bool(eni.get("Association", {}).get("PublicIp")), "NAT public address missing")
        vols = [
            x["Ebs"]["VolumeId"]
            for x in instance.get("BlockDeviceMappings", [])
            if x["DeviceName"] == "/dev/xvda"
        ]
        self.require(len(vols) == 1, "Expected one root volume")
        v = self.aws("ec2", "describe-volumes", "--volume-ids", vols[0])["Volumes"][0]
        self.require(
            v.get("Encrypted") is True
            and v.get("Size") == 8
            and v.get("VolumeType") == "gp3"
            and v.get("Iops") == 3000
            and v.get("Throughput") == 125,
            "Encrypted storage configuration differs",
        )
        credits = self.aws(
            "ec2", "describe-instance-credit-specifications", "--instance-ids", ids["NatInstance"]
        )["InstanceCreditSpecifications"]
        self.require(
            len(credits) == 1 and credits[0].get("CpuCredits") == "standard",
            "CPU credits must remain standard",
        )
        sg = self.aws("ec2", "describe-security-groups", "--group-ids", ids["NatSecurityGroup"])[
            "SecurityGroups"
        ][0]
        for name, cidr in [
            ("IpPermissions", "10.84.32.0/23"),
            ("IpPermissionsEgress", "0.0.0.0/0"),
        ]:
            rules = sg[name]
            self.require(
                len(rules) == 1
                and rules[0].get("IpProtocol") == "tcp"
                and rules[0].get("FromPort") == 443
                and rules[0].get("ToPort") == 443
                and [x["CidrIp"] for x in rules[0].get("IpRanges", [])] == [cidr]
                and not rules[0].get("Ipv6Ranges")
                and not rules[0].get("UserIdGroupPairs")
                and not rules[0].get("PrefixListIds"),
                "NAT security group differs",
            )
        routes = self.aws(
            "ec2", "describe-route-tables", "--filters", "Name=vpc-id,Values=" + self.VPC
        )["RouteTables"]
        self.require(
            set(self.pf.APP_ROUTES) <= {x["RouteTableId"] for x in routes},
            "App route table missing",
        )
        for table in routes:
            nonlocal_routes = [r for r in table["Routes"] if r.get("GatewayId") != "local"]
            rid = table["RouteTableId"]
            if rid in self.pf.APP_ROUTES:
                self.require(
                    any(
                        a.get("SubnetId") == self.pf.APP_ROUTES[rid] for a in table["Associations"]
                    ),
                    "App route association differs",
                )
                self.require(
                    len(nonlocal_routes) == 1
                    and nonlocal_routes[0].get("DestinationCidrBlock") == "0.0.0.0/0"
                    and nonlocal_routes[0].get("NetworkInterfaceId") == ids["NatInterface"]
                    and nonlocal_routes[0].get("State") == "active",
                    "App NAT route differs",
                )
            elif rid == ids["PublicRoutes"]:
                self.require(
                    len(nonlocal_routes) == 1
                    and nonlocal_routes[0].get("GatewayId") == ids["InternetGateway"]
                    and nonlocal_routes[0].get("State") == "active",
                    "Public route differs",
                )
            else:
                self.require(not nonlocal_routes, "Database/default routes must remain local-only")
        self.context.report["outputs"] = {
            x["OutputKey"]: x["OutputValue"] for x in s.get("Outputs", [])
        }
        self.context.report["host_check"] = (
            self.host_check(ids["NatInstance"]) if check_host else {"performed": False}
        )
        self.context.report["egress_configuration_verified"] = True

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
            "Remove AWS credential/config/endpoint environment overrides",
        )
        os.environ.update(
            AWS_PAGER="",
            AWS_CLI_AUTO_PROMPT="off",
            AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
            AWS_MAX_ATTEMPTS="2",
        )
        self.note("Fitfinity AWS — deploy the reviewed single-instance test egress")
        who = self.aws("sts", "get-caller-identity")
        self.require(
            who.get("Account") == self.ACCOUNT
            and who.get("Arn") == f"arn:aws:iam::{self.ACCOUNT}:user/fitfinity-deployer",
            "Expected test IAM identity was not verified",
        )
        s = self.stack_info(missing=True)
        recover = bool(s and s.get("_recover_old"))
        if recover:
            self.recovery_guard(s)
        if s is None or recover:
            self.pf.main()
            self.context.report["preflight"] = self.pf.context.report
            self.require(
                self.pf.context.report["ami_candidate"]["ImageId"] == "ami-021e6de04c7a84a9f",
                (
                    "Public AMI changed; review the new "
                    "image before provisioning this pinned template"
                ),
            )
            self.require(
                any(
                    x.get("InstanceType") == "t4g.micro" and x.get("FreeTierEligible") is True
                    for x in self.pf.context.report["instance_types"]
                ),
                "Selected micro is not Free Tier eligible in the live response",
            )
            eligible = self.aws(
                "ec2",
                "describe-images",
                "--image-ids",
                "ami-021e6de04c7a84a9f",
                "--owners",
                "amazon",
                "--filters",
                "Name=free-tier-eligible,Values=true",
            )["Images"]
            self.require(
                len(eligible) == 1,
                "Pinned Amazon Linux AMI is not currently marked Free Tier eligible",
            )
            # The concrete design expects the default allow-all ACL collected in the receipt.
            acls = self.pf.context.report["network_acls"]
            self.require(
                len(acls) == 1 and acls[0].get("IsDefault") is True,
                "Unexpected network ACL configuration",
            )
            for egress in [False, True]:
                rules = sorted(
                    [x for x in acls[0]["Entries"] if x["Egress"] == egress],
                    key=lambda x: x["RuleNumber"],
                )
                self.require(
                    rules
                    and rules[0].get("Protocol") == "-1"
                    and rules[0].get("CidrBlock") == "0.0.0.0/0"
                    and rules[0].get("RuleAction") == "allow",
                    "Existing ACL differs from reviewed path",
                )
            if recover:
                self.note(
                    "Recovery: update the exact empty failed stack; remove only u"
                    "nsupported EBS Throughput. No deletion or replacement of exi"
                    "sting resources."
                )
            self.note(
                "Concrete action: create 15 resources for one t4g.micro NAT, "
                "encrypted 8 GiB gp3, one EIP, dedicated public subnet/IGW, S"
                "SM role, and two app default routes."
            )
            self.note(
                "Additional base: US$"
                + self.pf.context.report["monthly_base_usd"]["t4g.micro"]
                + ("/month at 730 hours; see exclusions above. Existing foundation costs continue.")
            )
            self.note(
                "Single instance/AZ: an egress failure point requiring patchi"
                "ng and recovery. Standard CPU credits may throttle sustained"
                " load."
            )
            self.note(
                "No inbound SSH, app deployment, database changes, secret ret"
                "rieval or automatic deletion. Database routes remain local-o"
                "nly."
            )
            self.note(
                "A fixed read-only SSM command checks installed NAT configura"
                "tion and host HTTPS to Cognito JWKS. Private app-subnet prob"
                "e remains next."
            )
            with tempfile.TemporaryDirectory(prefix="fitfinity-egress-") as td:
                path = Path(td) / "template.json"
                path.write_text(json.dumps(self.TEMPLATE))
                self.aws(
                    "cloudformation", "validate-template", "--template-body", "file://" + str(path)
                )
                started = time.monotonic()
                self.confirm()
                self.require(
                    time.monotonic() - started < 600,
                    "Review exceeded 10 minutes; rerun to refresh state/prices before creating",
                )
                if recover:
                    self.recovery_guard(self.stack_info())
                else:
                    self.require(
                        self.stack_info(missing=True) is None,
                        "Stack appeared during review; rerun to inspect",
                    )
                self.context.report["write_attempted"] = True
                if recover:
                    made = self.aws(
                        "cloudformation",
                        "update-stack",
                        "--stack-name",
                        self.FAILED_ARN,
                        "--template-body",
                        "file://" + str(path),
                        "--capabilities",
                        "CAPABILITY_IAM",
                        "--disable-rollback",
                        "--client-request-token",
                        "fitfinity-egress-repair-" + self.TEMPLATE_SHA[:24],
                    )
                    self.context.report["recovery_update_sent"] = True
                else:
                    made = self.aws(
                        "cloudformation",
                        "create-stack",
                        "--stack-name",
                        self.STACK,
                        "--template-body",
                        "file://" + str(path),
                        "--capabilities",
                        "CAPABILITY_IAM",
                        "--tags",
                        *["Key=" + k + ",Value=" + v for k, v in self.TAGS.items()],
                        "--enable-termination-protection",
                        "--disable-rollback",
                        "--client-request-token",
                        "fitfinity-egress-" + self.TEMPLATE_SHA[:24],
                    )
                self.context.report["stack_id"] = made["StackId"]
        else:
            self.note("Resuming checks of the exact existing stack; no new creation/update.")
        deadline = time.monotonic() + 1800
        while True:
            s = self.stack_info()
            status = s["StackStatus"]
            self.context.report.update(stack_id=s["StackId"], status=status)
            self.note("CloudFormation: " + status)
            if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
                break
            if status not in {
                "CREATE_IN_PROGRESS",
                "UPDATE_IN_PROGRESS",
                "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
            }:
                self.context.report["failures"] = self.aws(
                    "cloudformation",
                    "describe-events",
                    "--stack-name",
                    self.STACK,
                    "--filters",
                    "FailedEvents=true",
                )
                raise RuntimeError(
                    "Creation needs review; partial resources may incur costs. Upload this receipt."
                )
            self.require(
                time.monotonic() < deadline,
                "Creation wait timed out; AWS may still be provisioning. Rerun to inspect.",
            )
            time.sleep(15)
        self.verify(s)
        self.note(
            "EGRESS CONFIGURATION PASSED — NAT host and cloud settings ve"
            "rified. Actual private-runtime forwarding probe and app depl"
            "oyment remain pending."
        )

    def save(self):
        self.context.report["checked_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        folder = Path.home() / "Downloads"
        folder.mkdir(exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix="Fitfinity_AWS_Egress_Execution_", suffix=".json", dir=folder
        )
        with os.fdopen(fd, "w") as f:
            json.dump(self.context.report, f, indent=2)
            f.write("\n")
        self.note("Receipt: " + name)

    def run(self):
        try:
            self.main()
        except (Exception, KeyboardInterrupt) as e:
            self.context.report["error"] = str(e) or "Interrupted"
            self.note("STOPPED: " + self.context.report["error"])
            self.note("Resources may be running. Nothing is automatically deleted.")
            self.save()
            raise SystemExit(1) from None
        self.save()
