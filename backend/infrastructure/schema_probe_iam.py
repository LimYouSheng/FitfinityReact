"""Own the temporary probe runtime's permission ceiling."""

from release_image import ACCOUNT, REGION

NAME = "fitfinity-test-schema-observe"
RUNTIME_ROLE = NAME + "-runtime"
BOUNDARY = f"arn:aws:iam::{ACCOUNT}:policy/{NAME}-runtime-boundary"


def runtime_policy(secret_arn):
    """Limit runtime access to its exact migration secret, logs and managed ENIs."""
    function = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{NAME}"
    logs = f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/lambda/{NAME}"
    eni = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSubnets",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses",
    ]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": secret_arn,
                "Condition": {"StringEquals": {"secretsmanager:VersionStage": "AWSCURRENT"}},
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": logs + ":*",
            },
            {"Effect": "Allow", "Action": eni, "Resource": "*"},
            {
                "Effect": "Deny",
                "Action": eni + ["ec2:DetachNetworkInterface"],
                "Resource": "*",
                "Condition": {"ArnEquals": {"lambda:SourceFunctionArn": function}},
            },
        ],
    }
