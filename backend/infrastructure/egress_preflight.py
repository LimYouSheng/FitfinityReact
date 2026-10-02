"""EgressPreflightOperator: explicit per-run dependencies and receipt state."""

import datetime
import ipaddress
import json
import os
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

from operator_context import OperatorContext


class EgressPreflightOperator:
    def __init__(self, *, context=None, aws_call=None):
        self.context = context if context is not None else OperatorContext(aws_call=aws_call)
        self.ACCOUNT = "418638389566"
        self.REGION = "ap-southeast-1"
        self.PROFILE = "fitfinity-test"
        self.VPC = "vpc-0b55320bb1a054441"
        self.FOUNDATION = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fit"
            "finity-test-foundation/6b51b020-b65f-11f1-82ee-0a2a8f1e9b2d"
        )
        self.COGNITO = (
            "arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fit"
            "finity-test-cognito/776045f0-b66b-11f1-92b4-06ffd526f669"
        )
        self.AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
        self.APP_ROUTES = {
            "rtb-09f050cad93faea2c": "subnet-0a6ea67e00f370997",
            "rtb-046a15665b5999a5a": "subnet-0fcdf32ab544f1207",
        }
        self.ALLOWED = {
            ("sts", "get-caller-identity"),
            ("freetier", "get-account-plan-state"),
            ("cloudformation", "describe-stacks"),
            ("ec2", "describe-vpcs"),
            ("ec2", "describe-subnets"),
            ("ec2", "describe-route-tables"),
            ("ec2", "describe-internet-gateways"),
            ("ec2", "describe-nat-gateways"),
            ("ec2", "describe-vpc-endpoints"),
            ("ec2", "describe-instances"),
            ("ec2", "describe-images"),
            ("ec2", "describe-instance-type-offerings"),
            ("ec2", "describe-instance-types"),
            ("ec2", "describe-security-groups"),
            ("ec2", "describe-network-acls"),
            ("ssm", "get-parameter"),
            ("pricing", "get-products"),
        }
        if context is None:
            self.context.report.update(
                {
                    "account": self.ACCOUNT,
                    "region": self.REGION,
                    "vpc": self.VPC,
                    "read_only": True,
                    "preflight_passed": False,
                    "egress_deployed": False,
                    "app_deployed": False,
                }
            )

    def note(self, s):
        print(s, flush=True)

    def require(self, ok, message):
        if not ok:
            raise RuntimeError(message)

    def aws(self, service, operation, *args, region=None):
        if region is None:
            region = self.REGION
        self.require((service, operation) in self.ALLOWED, "Operation outside read-only allowlist")
        if service == "ssm":
            self.require(
                args == ("--name", self.AMI_PARAMETER),
                "Only the public Amazon Linux AMI parameter may be read",
            )
        if self.context.aws_call is not None:
            return self.context.aws_call(service, operation, *args, region=region)
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
            raise RuntimeError(service + " " + operation + ": " + p.stderr.strip())
        return json.loads(p.stdout) if p.stdout.strip() else {}

    def rate(self, service, filters, unit):
        response = self.aws(
            "pricing",
            "get-products",
            "--service-code",
            service,
            "--filters",
            json.dumps(
                [
                    {"Type": "TERM_MATCH", "Field": k, "Value": v}
                    for k, v in {"location": "Asia Pacific (Singapore)", **filters}.items()
                ]
            ),
            region="us-east-1",
        )
        found = []
        for raw in response.get("PriceList", []):
            item = json.loads(raw) if isinstance(raw, str) else raw
            for term in item.get("terms", {}).get("OnDemand", {}).values():
                for d in term.get("priceDimensions", {}).values():
                    if (
                        d.get("unit") == unit
                        and d.get("beginRange") == "0"
                        and d.get("endRange") == "Inf"
                        and Decimal(d.get("pricePerUnit", {}).get("USD", "0")) > 0
                    ):
                        found.append(
                            {
                                "sku": item["product"]["sku"],
                                "usd": d["pricePerUnit"]["USD"],
                                "unit": unit,
                                "description": d["description"],
                                "effective": term.get("effectiveDate"),
                            }
                        )
        self.require(
            len(found) == 1,
            "Current price missing/ambiguous for " + json.dumps(filters) + "; no estimate accepted",
        )
        return found[0]

    def main(self):
        self.note("Fitfinity AWS — outbound network preflight and current price review (READ ONLY)")
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
        who = self.aws("sts", "get-caller-identity")
        self.require(
            who.get("Account") == self.ACCOUNT
            and who.get("Arn") == f"arn:aws:iam::{self.ACCOUNT}:user/fitfinity-deployer",
            "Expected test IAM identity was not verified",
        )
        self.context.report["plan"] = self.aws(
            "freetier", "get-account-plan-state", region="us-east-1"
        )
        self.require(
            self.context.report["plan"].get("accountPlanStatus") == "ACTIVE"
            and self.context.report["plan"].get("accountPlanType") == "FREE",
            "Expected ACTIVE FREE account; review plan change first",
        )
        for key, arn in [("foundation", self.FOUNDATION), ("cognito", self.COGNITO)]:
            s = self.aws("cloudformation", "describe-stacks", "--stack-name", arn)["Stacks"][0]
            self.require(
                s["StackId"] == arn and s["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
                "Expected completed " + key + " stack",
            )
            self.context.report[key] = {
                "stack_id": arn,
                "status": s["StackStatus"],
                "outputs": s.get("Outputs", []),
            }
        v = self.aws("ec2", "describe-vpcs", "--vpc-ids", self.VPC)["Vpcs"]
        self.require(
            len(v) == 1
            and v[0]["CidrBlock"] == "10.84.0.0/16"
            and v[0].get("IsDefault") is False
            and v[0]["State"] == "available",
            "VPC identity/configuration differs",
        )
        vf = "Name=vpc-id,Values=" + self.VPC
        subnets = self.aws("ec2", "describe-subnets", "--filters", vf)["Subnets"]
        self.context.report["subnets"] = subnets
        self.require(
            set(self.APP_ROUTES.values()) <= {s["SubnetId"] for s in subnets}, "App subnet missing"
        )
        candidate = ipaddress.ip_network("10.84.0.0/24")
        self.require(
            not any(candidate.overlaps(ipaddress.ip_network(s["CidrBlock"])) for s in subnets),
            "Proposed NAT public-subnet CIDR already occupied; review required",
        )
        self.require(
            all(not s.get("MapPublicIpOnLaunch") for s in subnets),
            "Unexpected public-IP assignment in existing private subnets",
        )
        routes = self.aws("ec2", "describe-route-tables", "--filters", vf)["RouteTables"]
        self.context.report["route_tables"] = routes
        for rid, sid in self.APP_ROUTES.items():
            matches = [r for r in routes if r["RouteTableId"] == rid]
            self.require(
                len(matches) == 1
                and any(a.get("SubnetId") == sid for a in matches[0].get("Associations", [])),
                "App route association differs",
            )
        for r in routes:
            self.require(
                all(
                    x.get("GatewayId") == "local"
                    and x.get("DestinationCidrBlock") == "10.84.0.0/16"
                    and x.get("State") == "active"
                    for x in r.get("Routes", [])
                ),
                "Existing routes are no longer local-only; review before adding egress",
            )
        for key, op, collection, flt in [
            (
                "internet_gateways",
                "describe-internet-gateways",
                "InternetGateways",
                "Name=attachment.vpc-id,Values=" + self.VPC,
            ),
            ("nat_gateways", "describe-nat-gateways", "NatGateways", vf),
            ("endpoints", "describe-vpc-endpoints", "VpcEndpoints", vf),
        ]:
            filter_option = "--filter" if op == "describe-nat-gateways" else "--filters"
            items = self.aws("ec2", op, filter_option, flt)[collection]
            self.context.report[key] = items
            self.require(
                not [x for x in items if x.get("State") not in {"deleted", "failed"}],
                "Existing " + key + " need review; do not duplicate networking",
            )
        reservations = self.aws("ec2", "describe-instances", "--filters", vf)["Reservations"]
        instances = [
            i
            for r in reservations
            for i in r["Instances"]
            if i.get("State", {}).get("Name") != "terminated"
        ]
        self.context.report["instances"] = instances
        self.require(not instances, "Existing EC2 instances need review")
        self.context.report["security_groups"] = self.aws(
            "ec2", "describe-security-groups", "--filters", vf
        )["SecurityGroups"]
        self.context.report["network_acls"] = self.aws(
            "ec2", "describe-network-acls", "--filters", vf
        )["NetworkAcls"]
        # Preserve ACL evidence; the later concrete deployment must check its packet-path rules.
        self.note("Existing foundation routes are local-only; no active egress resources found.")
        ami = self.aws("ssm", "get-parameter", "--name", self.AMI_PARAMETER)["Parameter"]["Value"]
        images = self.aws("ec2", "describe-images", "--image-ids", ami, "--owners", "amazon")[
            "Images"
        ]
        self.require(len(images) == 1, "Public AMI did not resolve to an Amazon-owned image")
        image = images[0]
        self.require(
            image["ImageId"] == ami
            and image.get("Architecture") == "arm64"
            and image.get("State") == "available"
            and image.get("RootDeviceType") == "ebs"
            and image.get("VirtualizationType") == "hvm",
            "AMI configuration differs",
        )
        self.context.report["ami_candidate"] = {
            k: image.get(k)
            for k in [
                "ImageId",
                "Name",
                "OwnerId",
                "Architecture",
                "CreationDate",
                "RootDeviceName",
                "BlockDeviceMappings",
            ]
        }
        volumes = [
            b["Ebs"]["VolumeSize"]
            for b in image.get("BlockDeviceMappings", [])
            if b.get("DeviceName") == image["RootDeviceName"] and "Ebs" in b
        ]
        self.require(len(volumes) == 1, "AMI root volume size is ambiguous")
        disk = max(8, volumes[0])
        self.context.report["candidate_root_gib"] = disk
        offerings = self.aws(
            "ec2",
            "describe-instance-type-offerings",
            "--location-type",
            "availability-zone",
            "--filters",
            "Name=instance-type,Values=t4g.nano,t4g.micro",
            "Name=location,Values=ap-southeast-1a",
        )["InstanceTypeOfferings"]
        self.context.report["offerings"] = offerings
        self.require(
            {"t4g.nano", "t4g.micro"} <= {x["InstanceType"] for x in offerings},
            "Candidate instance types not both offered in ap-southeast-1a",
        )
        self.context.report["instance_types"] = self.aws(
            "ec2", "describe-instance-types", "--instance-types", "t4g.nano", "t4g.micro"
        )["InstanceTypes"]
        self.note("Reading current Singapore compute, gp3 and public IPv4 prices...")
        prices = {}
        self.context.report["prices"] = prices
        base = {
            "productFamily": "Compute Instance",
            "operatingSystem": "Linux",
            "tenancy": "Shared",
            "preInstalledSw": "NA",
            "capacitystatus": "Used",
        }
        for size in ["t4g.nano", "t4g.micro"]:
            prices[size] = self.rate("AmazonEC2", {**base, "instanceType": size}, "Hrs")
        prices["gp3"] = self.rate(
            "AmazonEC2", {"productFamily": "Storage", "volumeApiName": "gp3"}, "GB-Mo"
        )
        prices["public_ipv4"] = self.rate(
            "AmazonVPC", {"usagetype": "APS1-PublicIPv4:InUseAddress"}, "Hrs"
        )
        self.context.report["monthly_base_usd"] = {}
        for size in ["t4g.nano", "t4g.micro"]:
            monthly = 730 * (
                Decimal(prices[size]["usd"]) + Decimal(prices["public_ipv4"]["usd"])
            ) + disk * Decimal(prices["gp3"]["usd"])
            self.context.report["monthly_base_usd"][size] = str(monthly)
            self.note(
                f"{size} + one public IPv4 + {disk} GiB gp3: US${monthly:.2f}/month "
                "at 730 hours, before exclusions."
            )
        self.context.report["excludes"] = (
            "Taxes/FX, transfer including cross-AZ, CloudWatch/management"
            " usage, snapshots, additional storage/IOPS/throughput and op"
            "erating labour. Existing foundation/app costs are separate. "
            "Standard CPU credits proposed; exhaustion can throttle throu"
            "ghput. Not a spend cap."
        )
        self.note(self.context.report["excludes"])
        self.context.report["proposal"] = {
            "availability_zone": "ap-southeast-1a",
            "public_subnet_cidr": str(candidate),
            "instance_candidate": "t4g.nano",
            "comparison": "t4g.micro",
            "os": (
                "Amazon Linux 2023 arm64 (public parameter resolved in receip"
                "t; pin exact AMI during template preparation)"
            ),
            "design": (
                "One NAT instance/EIP in a dedicated public subnet; private a"
                "pp routes through its ENI; database routes remain local-only"
                "."
            ),
            "required_controls": [
                "No inbound SSH/public administration",
                "SSM management with least-privilege role",
                "IMDSv2",
                "Encrypted gp3",
                "Standard CPU credits",
                "Source/destination check disabled only on NAT ENI",
                (
                    "Forwarding limited to app/migration "
                    "subnet HTTPS with established return traffic"
                ),
                "Persistent firewall and forwarding configuration",
                ("Health/patch/replacement runbook and private-runtime probe before acceptance"),
            ],
            "limitations": [
                "Single instance/AZ is an egress failure point; no high-availability claim",
                "AMI is an ordinary OS image: NAT setup and patching must be implemented",
                (
                    "Instance offerings do not guarantee capacity, Free-plan elig"
                    "ibility or available quota"
                ),
                (
                    "PrivateLink-only design has not established JWKS and future "
                    "external-service reachability"
                ),
            ],
        }
        self.context.report["preflight_passed"] = True
        self.note(
            "PREFLIGHT PASSED — read-only network and pricing evidence co"
            "llected. Upload the receipt for the concrete deployment prev"
            "iew."
        )
        self.note(
            "No cloud resources created, routes changed, secrets retrieved or application deployed."
        )

    def save(self):
        self.context.report["checked_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        directory = Path.home() / "Downloads"
        directory.mkdir(exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix="Fitfinity_AWS_Egress_Preflight_", suffix=".json", dir=directory
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
            self.save()
            raise SystemExit(1) from None
        self.save()
