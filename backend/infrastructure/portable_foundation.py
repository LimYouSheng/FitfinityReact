"""Render new-environment foundations; never update or adopt an existing database."""

import ipaddress
import re

from deployment_profile import identities, template_rules
from operator_checks import require


def ref(name):
    """Reference a resource in the same reviewed template."""
    return {"Ref": name}


def attr(name, key):
    """Reference a resource attribute without external discovery assumptions."""
    return {"Fn::GetAtt": [name, key]}


def prepare(profile, options):
    """Require explicit capacity, retention and egress choices before rendering a new stack."""
    target = identities(profile)
    require(
        set(options)
        == {
            "vpc_cidr",
            "engine_version",
            "database_class",
            "storage_gib",
            "max_storage_gib",
            "multi_az",
            "backup_days",
            "egress",
        },
        "Exact foundation options required",
    )
    network = ipaddress.ip_network(options["vpc_cidr"], strict=True)
    require(
        network.version == 4
        and network.prefixlen == 16
        and any(
            network.subnet_of(ipaddress.ip_network(cidr))
            for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        ),
        "A private non-overlapping /16 must be reviewed",
    )
    require(
        re.fullmatch(r"17\.[0-9]{1,2}", options["engine_version"] or ""),
        "Review a PostgreSQL 17 minor version",
    )
    require(
        re.fullmatch(r"db\.[a-z][a-z0-9]*\.[a-z0-9]+", options["database_class"] or ""),
        "Review an RDS instance class",
    )
    require(
        type(options["storage_gib"]) is int
        and type(options["max_storage_gib"]) is int
        and 20 <= options["storage_gib"] <= options["max_storage_gib"] <= 65536,
        "Review database storage limits",
    )
    require(type(options["multi_az"]) is bool, "Explicit Multi-AZ choice required")
    require(
        type(options["backup_days"]) is int and 1 <= options["backup_days"] <= 35,
        "Review account-supported backup retention",
    )
    require(options["egress"] in {"none", "nat-per-az"}, "Explicit reviewed egress choice required")
    prefix = target["resource_prefix"]
    tags = [
        {"Key": "Application", "Value": "Fitfinity"},
        {"Key": "Environment", "Value": target["environment_tag"]},
        {"Key": "FitfinityProfile", "Value": target["profile_sha256"]},
    ]
    resources = {}

    def resource(name, kind, properties, *, retained=False):
        resources[name] = {"Type": "AWS::" + kind, "Properties": properties}
        if retained:
            resources[name].update(DeletionPolicy="Retain", UpdateReplacePolicy="Retain")

    def subnet(name, offset, zone):
        resource(
            name,
            "EC2::Subnet",
            {
                "VpcId": ref("Vpc"),
                "CidrBlock": str(list(network.subnets(new_prefix=24))[offset]),
                "AvailabilityZone": {"Fn::Select": [zone, {"Fn::GetAZs": ""}]},
                "MapPublicIpOnLaunch": False,
                "Tags": tags,
            },
        )
        resource(name + "Routes", "EC2::RouteTable", {"VpcId": ref("Vpc"), "Tags": tags})
        resource(
            name + "RouteAssociation",
            "EC2::SubnetRouteTableAssociation",
            {"SubnetId": ref(name), "RouteTableId": ref(name + "Routes")},
        )

    resource(
        "Vpc",
        "EC2::VPC",
        {
            "CidrBlock": str(network),
            "EnableDnsSupport": True,
            "EnableDnsHostnames": True,
            "Tags": tags,
        },
    )
    for zone, suffix in enumerate(("A", "B")):
        subnet("DatabaseSubnet" + suffix, 16 + zone, zone)
        subnet("AppSubnet" + suffix, 32 + zone, zone)
    resource(
        "DatabaseSecurityGroup",
        "EC2::SecurityGroup",
        {
            "VpcId": ref("Vpc"),
            "GroupDescription": "Restricted PostgreSQL ingress only",
            "SecurityGroupEgress": [
                {"IpProtocol": "tcp", "FromPort": 9, "ToPort": 9, "CidrIp": "127.0.0.1/32"}
            ],
            "Tags": tags,
        },
    )
    for name in ("ApplicationSecurityGroup", "MigrationSecurityGroup"):
        resource(
            name,
            "EC2::SecurityGroup",
            {
                "VpcId": ref("Vpc"),
                "GroupDescription": name,
                "SecurityGroupEgress": [
                    {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"},
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 5432,
                        "ToPort": 5432,
                        "DestinationSecurityGroupId": attr("DatabaseSecurityGroup", "GroupId"),
                    },
                ],
                "Tags": tags,
            },
        )
        resource(
            name + "DatabaseAccess",
            "EC2::SecurityGroupIngress",
            {
                "GroupId": attr("DatabaseSecurityGroup", "GroupId"),
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "SourceSecurityGroupId": attr(name, "GroupId"),
            },
        )
    if options["egress"] == "nat-per-az":
        resource("InternetGateway", "EC2::InternetGateway", {"Tags": tags})
        resource(
            "GatewayAttachment",
            "EC2::VPCGatewayAttachment",
            {"VpcId": ref("Vpc"), "InternetGatewayId": ref("InternetGateway")},
        )
        for zone, suffix in enumerate(("A", "B")):
            subnet("EgressSubnet" + suffix, zone, zone)
            resource(
                "EgressDefault" + suffix,
                "EC2::Route",
                {
                    "RouteTableId": ref("EgressSubnet" + suffix + "Routes"),
                    "DestinationCidrBlock": "0.0.0.0/0",
                    "GatewayId": ref("InternetGateway"),
                },
            )
            resources["EgressDefault" + suffix]["DependsOn"] = "GatewayAttachment"
            resource("EgressAddress" + suffix, "EC2::EIP", {"Domain": "vpc", "Tags": tags})
            resource(
                "Nat" + suffix,
                "EC2::NatGateway",
                {
                    "SubnetId": ref("EgressSubnet" + suffix),
                    "AllocationId": attr("EgressAddress" + suffix, "AllocationId"),
                    "Tags": tags,
                },
            )
            resources["Nat" + suffix]["DependsOn"] = "GatewayAttachment"
            resource(
                "AppDefault" + suffix,
                "EC2::Route",
                {
                    "RouteTableId": ref("AppSubnet" + suffix + "Routes"),
                    "DestinationCidrBlock": "0.0.0.0/0",
                    "NatGatewayId": ref("Nat" + suffix),
                },
            )
    resource(
        "DatabaseSubnetGroup",
        "RDS::DBSubnetGroup",
        {
            "DBSubnetGroupDescription": "Private database subnets in two selected-region AZs",
            "SubnetIds": [ref("DatabaseSubnetA"), ref("DatabaseSubnetB")],
            "Tags": tags,
        },
    )
    resource(
        "DatabaseParameters",
        "RDS::DBParameterGroup",
        {
            "Description": "PostgreSQL TLS and statement privacy",
            "Family": "postgres17",
            "Parameters": {
                "rds.force_ssl": "1",
                "log_statement": "none",
                "log_min_duration_statement": "-1",
                "log_min_error_statement": "panic",
            },
            "Tags": tags,
        },
    )
    database = {
        "DBInstanceIdentifier": target["database"],
        "Engine": "postgres",
        "EngineVersion": options["engine_version"],
        "DBInstanceClass": options["database_class"],
        "EngineLifecycleSupport": "open-source-rds-extended-support-disabled",
        "DBName": "fitfinity",
        "MasterUsername": "fitfinity_admin",
        "ManageMasterUserPassword": True,
        "AllocatedStorage": str(options["storage_gib"]),
        "MaxAllocatedStorage": options["max_storage_gib"],
        "StorageType": "gp3",
        "StorageEncrypted": True,
        "PubliclyAccessible": False,
        "MultiAZ": options["multi_az"],
        "DBSubnetGroupName": ref("DatabaseSubnetGroup"),
        "DBParameterGroupName": ref("DatabaseParameters"),
        "VPCSecurityGroups": [attr("DatabaseSecurityGroup", "GroupId")],
        "Port": "5432",
        "BackupRetentionPeriod": options["backup_days"],
        "CopyTagsToSnapshot": True,
        "DeletionProtection": True,
        "DeleteAutomatedBackups": False,
        "AutoMinorVersionUpgrade": True,
        "AllowMajorVersionUpgrade": False,
        "MonitoringInterval": 0,
        "EnablePerformanceInsights": False,
        "Tags": tags,
    }
    if not options["multi_az"]:
        database["AvailabilityZone"] = {"Fn::Select": [0, {"Fn::GetAZs": ""}]}
    resource("Database", "RDS::DBInstance", database, retained=True)
    outputs = {
        name: {"Value": ref(name)}
        for name in (
            "Vpc",
            "AppSubnetA",
            "AppSubnetB",
            "ApplicationSecurityGroup",
            "MigrationSecurityGroup",
        )
    }
    outputs.update(
        {
            "DatabaseEndpoint": {"Value": attr("Database", "Endpoint.Address")},
            "DatabaseIdentifier": {"Value": ref("Database")},
            "AdminSecretArn": {"Value": attr("Database", "MasterUserSecret.SecretArn")},
        }
    )
    return {
        "decision": "HOLD",
        "profile_sha256": target["profile_sha256"],
        "mode": "new-environment-only",
        "stack_name": prefix + "-foundation",
        "template": {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Description": "Portable private PostgreSQL foundation",
            "Rules": template_rules(profile),
            "Metadata": {"FitfinityProfile": target["profile_sha256"]},
            "Resources": resources,
            "Outputs": outputs,
        },
        "required_before_execution": [
            "Verify caller account/region, at least two AZs and instance/engine availability",
            "Review CIDR overlap, quotas, NAT/storage/Multi-AZ cost and backup eligibility",
            "Refuse existing stack/database adoption or any replacement; separate migration plan",
            "No application/provider acceptance until actual network/TLS and restore checks",
        ],
    }
