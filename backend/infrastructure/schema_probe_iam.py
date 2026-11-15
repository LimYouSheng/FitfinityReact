"""Own the temporary probe runtime's permission ceiling."""

from deployment_profile import DEVELOPER, identities

_TARGET = identities(DEVELOPER)
ACCOUNT, REGION = _TARGET["account"], _TARGET["region"]

NAME = "fitfinity-test-schema-observe"
RUNTIME_ROLE = NAME + "-runtime"
BOUNDARY = f"arn:aws:iam::{ACCOUNT}:policy/{NAME}-runtime-boundary"


def runtime_policy(secret_arn, *, profile=DEVELOPER):
    """Limit runtime access to its exact migration secret, logs and managed ENIs."""
    target = identities(profile)
    account, region, name = target["account"], target["region"], target["probe_name"]
    function = f"arn:aws:lambda:{region}:{account}:function:{name}"
    logs = f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/{name}"
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
