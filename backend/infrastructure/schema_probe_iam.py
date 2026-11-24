"""Own the temporary probe runtime's permission ceiling."""

from deployment_profile import DEVELOPER, identities
from operator_checks import require

_TARGET = identities(DEVELOPER)
ACCOUNT, REGION = _TARGET["account"], _TARGET["region"]

NAME = _TARGET["probe_name"]
RUNTIME_ROLE = NAME + "-runtime"
BOUNDARY = f"arn:aws:iam::{ACCOUNT}:policy/{NAME}-runtime-boundary"


def runtime_policy(secret_arn, *, profile=DEVELOPER, purpose="probe"):
    """Limit runtime access to its exact migration secret, logs and managed ENIs."""
    target = identities(profile)
    require(purpose in {"probe", "upgrade"}, "Unknown private job purpose")
    account, region = target["account"], target["region"]
    name = target["probe_name" if purpose == "probe" else "upgrade_name"]
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
