"""Read-only resource, scan and cost checks with explicit inputs."""

import datetime as dt
import json
import re
from decimal import Decimal

from operator_checks import one, require


def stack_template(row, *, aws):
    actual = aws(
        "cloudformation",
        "get-template",
        "--stack-name",
        row["StackId"],
        "--template-stage",
        "Original",
    )["TemplateBody"]
    return json.loads(actual) if isinstance(actual, str) else actual


def network(
    *,
    account,
    admin_arn,
    app_sg,
    db_sg,
    foundation,
    host,
    migration_sg,
    subnet_a,
    subnet_b,
    vpc,
    aws,
    report,
):
    stack = one(
        aws("cloudformation", "describe-stacks", "--stack-name", foundation)["Stacks"],
        "Foundation missing",
    )
    require(
        stack["StackId"] == foundation
        and stack["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"},
        "Foundation state differs",
    )
    require(
        stack.get("EnableTerminationProtection") is True,
        "Foundation termination protection differs",
    )
    outputs = {x["OutputKey"]: x["OutputValue"] for x in stack["Outputs"]}
    expected = {
        "Vpc": vpc,
        "DatabaseEndpoint": host,
        "DatabasePort": "5432",
        "AdminSecretArn": admin_arn,
        "ApplicationSecurityGroup": app_sg,
        "MigrationSecurityGroup": migration_sg,
        "DatabaseSecurityGroup": db_sg,
        "AppSubnetA": subnet_a,
        "AppSubnetB": subnet_b,
    }
    require(all(outputs.get(k) == v for k, v in expected.items()), "Foundation references changed")
    database = one(
        aws("rds", "describe-db-instances", "--db-instance-identifier", "fitfinity-test-db")[
            "DBInstances"
        ],
        "RDS identity ambiguous",
    )
    expected_db = {
        "DBInstanceStatus": "available",
        "Engine": "postgres",
        "DBInstanceClass": "db.t4g.micro",
        "DBName": "fitfinity",
        "MasterUsername": "fitfinity_admin",
        "PubliclyAccessible": False,
        "StorageEncrypted": True,
        "DeletionProtection": True,
        "MultiAZ": False,
        "StorageType": "gp3",
    }
    require(all(database.get(k) == v for k, v in expected_db.items()), "RDS settings differ")
    require(
        database.get("EngineVersion", "").startswith("17.")
        and database["DBSubnetGroup"]["VpcId"] == vpc,
        "RDS version/VPC differs",
    )
    require(
        database["Endpoint"]["Address"] == host and database["Endpoint"]["Port"] == 5432,
        "RDS endpoint differs",
    )
    require(
        database.get("MasterUserSecret", {}).get("SecretArn") == admin_arn
        and database["MasterUserSecret"].get("SecretStatus") == "active",
        "RDS administrator secret differs",
    )
    require(
        database.get("VpcSecurityGroups") == [{"VpcSecurityGroupId": db_sg, "Status": "active"}],
        "RDS security groups differ",
    )
    require(
        20 <= database["AllocatedStorage"] <= 30
        and database["MaxAllocatedStorage"] == 30
        and database["BackupRetentionPeriod"] >= 1,
        "RDS storage/backups changed",
    )
    parameter = one(database["DBParameterGroups"], "RDS parameter groups differ")
    require(parameter["ParameterApplyStatus"] == "in-sync", "RDS parameters not applied")
    parameters = aws(
        "rds",
        "describe-db-parameters",
        "--db-parameter-group-name",
        parameter["DBParameterGroupName"],
    )["Parameters"]
    require(
        any(
            x.get("ParameterName") == "rds.force_ssl" and x.get("ParameterValue") == "1"
            for x in parameters
        ),
        "RDS forced TLS differs",
    )
    report["database_tls_policy"] = {
        "source": "rds_parameter_group",
        "parameter_group": parameter["DBParameterGroupName"],
        "apply_status": parameter["ParameterApplyStatus"],
        "rds_force_ssl": "1",
    }
    groups = aws(
        "ec2",
        "describe-security-groups",
        "--group-ids",
        app_sg,
        migration_sg,
        db_sg,
    )["SecurityGroups"]
    require(
        {g["GroupId"] for g in groups} == {app_sg, migration_sg, db_sg},
        "Security groups missing",
    )
    for group in groups:
        require(
            group["VpcId"] == vpc and group["OwnerId"] == account,
            "Security group ownership differs",
        )
        if group["GroupId"] == db_sg:
            peers = set()
            for rule in group.get("IpPermissions", []):
                require(
                    rule.get("IpProtocol") == "tcp"
                    and rule.get("FromPort") == rule.get("ToPort") == 5432
                    and not any(
                        rule.get(key) for key in ["IpRanges", "Ipv6Ranges", "PrefixListIds"]
                    ),
                    "Unexpected database ingress",
                )
                peers.update(x["GroupId"] for x in rule.get("UserIdGroupPairs", []))
            require(peers == {app_sg, migration_sg}, "Database sources differ")
        else:
            require(
                not group.get("IpPermissions"),
                "Application/migration ingress unexpectedly open",
            )
            rules = group.get("IpPermissionsEgress", [])
            require(len(rules) == 2, "Application/migration egress differs")
            require(
                {rule.get("FromPort") for rule in rules} == {443, 5432},
                "Application/migration egress ports differ",
            )
            for rule in rules:
                port = rule.get("FromPort")
                require(
                    rule.get("IpProtocol") == "tcp"
                    and port == rule.get("ToPort")
                    and port in {443, 5432},
                    "Unexpected outbound ports",
                )
                require(
                    not rule.get("Ipv6Ranges") and not rule.get("PrefixListIds"),
                    "Unexpected outbound destination",
                )
                if port == 443:
                    require(
                        [x["CidrIp"] for x in rule.get("IpRanges", [])] == ["0.0.0.0/0"]
                        and not rule.get("UserIdGroupPairs"),
                        "HTTPS route differs",
                    )
                else:
                    require(
                        [x["GroupId"] for x in rule.get("UserIdGroupPairs", [])] == [db_sg]
                        and not rule.get("IpRanges"),
                        "Database egress differs",
                    )
    subnets = aws("ec2", "describe-subnets", "--subnet-ids", subnet_a, subnet_b)["Subnets"]
    require(
        {x["SubnetId"] for x in subnets} == {subnet_a, subnet_b}
        and all(x["VpcId"] == vpc and not x["MapPublicIpOnLaunch"] for x in subnets),
        "Private subnets differ",
    )
    for subnet in [subnet_a, subnet_b]:
        route = one(
            aws(
                "ec2",
                "describe-route-tables",
                "--filters",
                "Name=association.subnet-id,Values=" + subnet,
            )["RouteTables"],
            "Private route table missing",
        )
        default = one(
            [x for x in route["Routes"] if x.get("DestinationCidrBlock") == "0.0.0.0/0"],
            "Private NAT route missing",
        )
        require(
            default.get("NetworkInterfaceId") == "eni-0189d693bfad0c7fa"
            and default.get("State") == "active",
            "Private NAT route changed",
        )
    reservations = aws("ec2", "describe-instances", "--instance-ids", "i-0fc0373d803ed17ec")[
        "Reservations"
    ]
    instance = one([i for r in reservations for i in r["Instances"]], "NAT instance ambiguous")
    require(
        instance["State"]["Name"] == "running"
        and instance["InstanceType"] == "t4g.micro"
        and instance["VpcId"] == vpc
        and instance.get("PublicIpAddress") == "52.77.93.192",
        "Existing NAT state changed",
    )
    volumes = aws(
        "ec2",
        "describe-volumes",
        "--volume-ids",
        *[x["Ebs"]["VolumeId"] for x in instance["BlockDeviceMappings"]],
    )["Volumes"]
    require(
        len(volumes) == 1 and volumes[0]["VolumeType"] == "gp3" and volumes[0]["Encrypted"] is True,
        "NAT volume differs",
    )
    report["database_configuration"] = {
        k: database[k]
        for k in [
            "EngineVersion",
            "AllocatedStorage",
            "DBInstanceClass",
            "PubliclyAccessible",
            "StorageEncrypted",
        ]
    }
    return database["AllocatedStorage"], volumes[0]["Size"]


def scan(*, account, digest, expiry, aws, report):
    now = dt.datetime.now(dt.UTC)
    require(now < expiry, "Approved test exception expired; review the image before deployment")
    response = aws(
        "ecr",
        "describe-image-scan-findings",
        "--registry-id",
        account,
        "--repository-name",
        "fitfinity-test-api",
        "--image-id",
        "imageDigest=" + digest,
    )
    require(
        response.get("registryId") == account
        and response.get("repositoryName") == "fitfinity-test-api"
        and response.get("imageId", {}).get("imageDigest") == digest,
        "ECR image identity differs",
    )
    require(
        not response.get("nextToken")
        and not response.get("NextToken")
        and response.get("imageScanStatus", {}).get("status") == "COMPLETE",
        "ECR scan incomplete",
    )
    findings = response["imageScanFindings"]
    completed = dt.datetime.fromisoformat(findings["imageScanCompletedAt"].replace("Z", "+00:00"))
    require(
        dt.timedelta(minutes=-5) <= now - completed <= dt.timedelta(hours=24),
        (
            "Image scan is older than 24 hours; refresh the scan and review it befo"
            "re running this step"
        ),
    )
    accepted = {
        "CVE-2026-85091": ("HIGH", "zlib", "1.3.dfsg+really1.3.1-1"),
        "CVE-2026-82560": ("HIGH", "perl", "5.40.1-6+deb13u1"),
        "CVE-2026-86805": ("MEDIUM", "glibc", "2.41-12+deb13u4"),
        "CVE-2026-95818": ("LOW", "glibc", "2.41-12+deb13u4"),
    }
    require(not findings.get("enhancedFindings"), "Scan type changed")
    observed = {}
    for item in findings.get("findings", []):
        attributes = {x["key"]: x["value"] for x in item.get("attributes", [])}
        require(item["name"] not in observed, "Duplicate scan finding")
        observed[item["name"]] = (
            item["severity"],
            attributes.get("package_name"),
            attributes.get("package_version"),
        )
    require(observed == accepted, "Scan findings changed; review required before deployment")
    report["scan"] = {
        "completed": completed.isoformat(),
        "findings": observed,
        "exception": "FITFINITY-TEST-2026-09-25-ZLIB",
        "expires": expiry.isoformat(),
    }


def price(service, filters, unit, *, aws):
    result = aws(
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
    rows = []
    for raw in result.get("PriceList", []):
        product = json.loads(raw) if isinstance(raw, str) else raw
        for term in product.get("terms", {}).get("OnDemand", {}).values():
            for dimension in term.get("priceDimensions", {}).values():
                if (
                    dimension.get("unit") == unit
                    and dimension.get("beginRange") == "0"
                    and dimension.get("endRange") == "Inf"
                    and Decimal(dimension.get("pricePerUnit", {}).get("USD", "0")) > 0
                ):
                    rows.append(
                        {
                            "sku": product["product"]["sku"],
                            "usd": dimension["pricePerUnit"]["USD"],
                            "unit": unit,
                            "description": dimension["description"],
                            "effective": term.get("effectiveDate"),
                        }
                    )
    return one(rows, f"Current {service} price missing/ambiguous; no stale price fallback")


def costs(db_gib, nat_gib, *, authentication=False, report, note, price_lookup):
    db = {"databaseEngine": "PostgreSQL", "deploymentOption": "Single-AZ"}
    rates = {
        "database_compute": price_lookup(
            "AmazonRDS",
            {**db, "instanceType": "db.t4g.micro", "productFamily": "Database Instance"},
            "Hrs",
        ),
        "database_storage": price_lookup(
            "AmazonRDS",
            {**db, "productFamily": "Database Storage", "volumeType": "General Purpose-GP3"},
            "GB-Mo",
        ),
        "nat_compute": price_lookup(
            "AmazonEC2",
            {
                "productFamily": "Compute Instance",
                "operatingSystem": "Linux",
                "tenancy": "Shared",
                "preInstalledSw": "NA",
                "capacitystatus": "Used",
                "instanceType": "t4g.micro",
            },
            "Hrs",
        ),
        "nat_storage": price_lookup(
            "AmazonEC2", {"productFamily": "Storage", "volumeApiName": "gp3"}, "GB-Mo"
        ),
        "ipv4": price_lookup("AmazonVPC", {"usagetype": "APS1-PublicIPv4:InUseAddress"}, "Hrs"),
        "secret": price_lookup(
            "AWSSecretsManager", {"usagetype": "APS1-AWSSecretsManager-Secret"}, "Secrets"
        ),
    }

    def value(key):
        return Decimal(rates[key]["usd"])

    existing = (
        730 * (value("database_compute") + value("nat_compute") + value("ipv4"))
        + db_gib * value("database_storage")
        + nat_gib * value("nat_storage")
        + value("secret")
    )
    added = 2 * value("secret")
    report["prices"] = rates
    report["monthly_base_usd"] = {
        "existing": str(existing),
        "two_database_secrets": str(added),
        "after_this_step": str(existing + added),
        "later_auth_secret": str(value("secret")),
        "hours": 730,
        "db_gib": db_gib,
        "nat_gib": nat_gib,
    }
    if authentication:
        report["monthly_base_usd"].update(
            before_this_step=str(existing + added),
            authentication_secret=str(value("secret")),
            after_this_step=str(existing + added + value("secret")),
        )
        del report["monthly_base_usd"]["later_auth_secret"]
        note(
            f"Existing base: US${existing + added:.2f}/month. Authentication secret: "
            f"+US${value('secret'):.2f}/month. After this step: "
            f"US${existing + added + value('secret'):.2f}/month (730-hour estimate)."
        )
        note(
            "Temporary Lambda/logs, secret API calls, ECR, transfer, backups/overages, "
            "later app services, tax and FX are extra. Not billed spend or a cap."
        )
        return
    note(
        f"Foundation/NAT/admin-secret base: US${existing:.2f}/month. "
        f"Two database secrets: +US${added:.2f}/month. "
        f"After this step: US${existing + added:.2f}/month."
    )
    note(
        "730-hour estimate; includes the existing RDS administrator secret. Aut"
        "hentication secret is a later additional resource."
    )
    note(
        "Temporary Lambda, logs, secret API calls, ECR, transfer, backups/overa"
        "ges, tax and FX are extra. Not billed spend or a cap."
    )


def secret_metadata(arn, name, *, tags, aws):
    value = aws("secretsmanager", "describe-secret", "--secret-id", arn)
    require(
        value.get("ARN") == arn
        and value.get("Name") == name
        and not value.get("DeletedDate")
        and not value.get("RotationEnabled"),
        "Secret identity/rotation differs",
    )
    require(
        value.get("KmsKeyId") in {None, "alias/aws/secretsmanager"},
        "Secret encryption key differs",
    )
    tags = {x["Key"]: x["Value"] for x in value.get("Tags", [])}
    require(all(tags.get(k) == v for k, v in tags.items()), "Secret ownership differs")
    require(
        sum("AWSCURRENT" in stages for stages in value.get("VersionIdsToStages", {}).values()) == 1,
        "Secret current version differs",
    )
    policy = aws("secretsmanager", "get-resource-policy", "--secret-id", arn)
    require(not policy.get("ResourcePolicy"), "Secret has an unexpected resource policy")


def credentials(row, *, account, region, report, review_secret):
    outputs = {x["OutputKey"]: x["OutputValue"] for x in row["Outputs"]}
    result = {}
    for logical, suffix in [
        ("ApplicationDatabaseSecret", "app"),
        ("MigrationDatabaseSecret", "migration"),
    ]:
        arn = outputs[logical + "Arn"]
        require(
            re.fullmatch(
                rf"arn:aws:secretsmanager:{region}:{account}:secret:fitfinity/test/database/{suffix}-[A-Za-z0-9]{{6}}",
                arn,
            ),
            "Secret ARN differs",
        )
        review_secret(arn, "fitfinity/test/database/" + suffix)
        result[suffix] = arn
    report["database_secret_arns"] = result
    return result
