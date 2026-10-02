"""Private probe templates and size checks; no AWS operations."""

import hashlib
import json

from operator_checks import require


def probe_template(
    arns,
    *,
    source=None,
    account,
    admin_arn,
    app_sg,
    image,
    migration_sg,
    region,
    root,
    subnet_a,
    subnet_b,
    check_sizes,
):
    source = source if source is not None else (root / "test-db-bootstrap.py").read_bytes()
    require(len(source) <= 32768, "Bootstrap source exceeds invocation transport limit")
    source_sha256 = hashlib.sha256(source).hexdigest()
    # Source travels in the private Invoke payload. Only this small pinned loader
    # lives in ImageConfig, so code growth cannot inflate configuration updates.
    command = ["python", "-c", (root / "test-db-loader.py").read_text(), source_sha256]
    image_config = {"Command": command, "EntryPoint": [], "WorkingDirectory": "/app"}
    require(len(json.dumps(image_config).encode()) <= 4096, "Bootstrap ImageConfig exceeds 4 KiB")
    resources = {}
    eni = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses",
    ]
    for prefix, mode, subnet, group in [
        ("Setup", "setup", subnet_a, migration_sg),
        ("Application", "app-probe", subnet_b, app_sg),
    ]:
        name = "fitfinity-test-db-" + ("setup" if prefix == "Setup" else "app-probe")
        function_arn = f"arn:aws:lambda:{region}:{account}:function:{name}"
        log_name = "/aws/lambda/" + name
        access = (
            [arns["app"]]
            if prefix == "Application"
            else [admin_arn, arns["app"], arns["migration"]]
        )
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["secretsmanager:GetSecretValue"],
                    "Resource": access,
                    "Condition": {"StringEquals": {"secretsmanager:VersionStage": "AWSCURRENT"}},
                },
                {
                    "Effect": "Allow",
                    "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                    "Resource": f"arn:aws:logs:{region}:{account}:log-group:{log_name}:*",
                },
                {"Effect": "Allow", "Action": eni, "Resource": "*"},
                {
                    "Effect": "Deny",
                    "Action": eni + ["ec2:DetachNetworkInterface"],
                    "Resource": "*",
                    "Condition": {"ArnEquals": {"lambda:SourceFunctionArn": function_arn}},
                },
            ],
        }
        resources[prefix + "Logs"] = {
            "Type": "AWS::Logs::LogGroup",
            "Properties": {"LogGroupName": log_name, "RetentionInDays": 1},
        }
        resources[prefix + "Role"] = {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "Policies": [
                    {"PolicyName": "FitfinityDatabaseBootstrap", "PolicyDocument": policy}
                ],
            },
        }
        variables = {
            "FITFINITY_DB_ACCESS_MODE": mode,
            "FITFINITY_APP_DB_SECRET_ARN": arns["app"],
            "AWS_LWA_PASS_THROUGH_PATH": "/events",
            "AWS_LWA_PORT": "8080",
            "AWS_LWA_READINESS_CHECK_PATH": "/health/live",
            "AWS_LWA_READINESS_CHECK_HEALTHY_STATUS": "200",
        }
        if prefix == "Setup":
            variables["FITFINITY_MIGRATION_DB_SECRET_ARN"] = arns["migration"]
        require(
            len(json.dumps(variables).encode()) <= 4096,
            "Bootstrap environment exceeds 4 KiB",
        )
        resources[prefix + "Function"] = {
            "Type": "AWS::Lambda::Function",
            "DependsOn": [prefix + "Logs"],
            "Properties": {
                "FunctionName": name,
                "PackageType": "Image",
                "Code": {"ImageUri": image},
                "Architectures": ["x86_64"],
                "ImageConfig": image_config,
                "Role": {"Fn::GetAtt": [prefix + "Role", "Arn"]},
                "Timeout": 120,
                "MemorySize": 256,
                "VpcConfig": {
                    "SubnetIds": [subnet],
                    "SecurityGroupIds": [group],
                    "Ipv6AllowedForDualStack": False,
                },
                "Environment": {"Variables": variables},
            },
        }
    for prefix in ["Setup", "Application"]:
        check_sizes(resources[prefix + "Function"]["Properties"])
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": (
            "Temporary private Fitfinity database setup and real-login permission v"
            "erification. No URL or API."
        ),
        "Resources": resources,
    }


def configuration_sizes(properties, *, account):
    # Estimate the entire API body, not just individual Lambda quota fields.
    # Reserve 1 KiB for provider-added defaults/serialization. Actual generated
    # role names cannot exceed IAM's 64-character role-name limit.
    request = {
        key: properties[key]
        for key in [
            "FunctionName",
            "ImageConfig",
            "Timeout",
            "MemorySize",
            "VpcConfig",
            "Environment",
        ]
    }
    request["Role"] = f"arn:aws:iam::{account}:role/" + "r" * 64
    request_bytes = len(json.dumps(request).encode())
    image_bytes = len(json.dumps(properties["ImageConfig"]).encode())
    environment_bytes = len(json.dumps(properties["Environment"]["Variables"]).encode())
    require(image_bytes <= 4096, "Bootstrap ImageConfig exceeds 4 KiB")
    require(environment_bytes <= 4096, "Bootstrap environment exceeds 4 KiB")
    require(request_bytes + 1024 < 5120, "Combined Lambda configuration exceeds request budget")
    return {
        "image_config": image_bytes,
        "environment": environment_bytes,
        "limit_each": 4096,
        "modeled_update_request": request_bytes,
        "provider_allowance": 1024,
        "update_request_limit": 5120,
    }
