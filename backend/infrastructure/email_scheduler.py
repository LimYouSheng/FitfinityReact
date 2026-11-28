"""Render an opt-in signed dispatcher; this module makes no AWS calls."""

import json
import re

HANDLER = """import boto3,hashlib,hmac,json,os,time,uuid
from botocore.config import Config

def handler(event, context):
    secrets=boto3.client("secretsmanager",config=Config(connect_timeout=2,read_timeout=5,retries={"total_max_attempts":1}))
    try:
        key=json.loads(secrets.get_secret_value(SecretId=os.environ["DISPATCH_SECRET"])["SecretString"])["dispatch_key"]
    finally:
        secrets.close()
    body=json.dumps({"at":int(time.time()),"id":str(uuid.uuid4())},separators=(",",":"))
    signature=hmac.new(bytes.fromhex(key),b"fitfinity.email.dispatch.v1\\n"+body.encode(),hashlib.sha256).hexdigest()
    request={"httpMethod":"POST","path":"/internal/email-dispatch","resource":"/{proxy+}",
      "headers":{"host":"127.0.0.1","content-type":"application/json","x-fitfinity-email-signature":signature},
      "requestContext":{"requestId":str(uuid.uuid4()),"identity":{"sourceIp":"127.0.0.1"},"stage":"internal"},
      "body":body,"isBase64Encoded":False}
    # An Invoke timeout may mean SES was already reached; never retry here.
    client=boto3.client("lambda",config=Config(connect_timeout=2,read_timeout=40,retries={"total_max_attempts":1}))
    try:
        response=client.invoke(FunctionName=os.environ["API_FUNCTION"],InvocationType="RequestResponse",Payload=json.dumps(request).encode())
        payload=response["Payload"]
        try:
            result=json.loads(payload.read())
        finally:
            payload.close()
        if response.get("FunctionError") or result.get("statusCode")!=200:
            raise RuntimeError("Email dispatch did not return a verified success")
        return {"dispatched":True}
    finally:
        client.close()
"""


def template(account, region, prefix, function_arn, secret_arn, secret_prefix):
    """Bind scheduler privileges to one function alias and one dedicated signing secret."""
    if not re.fullmatch(r"[0-9]{12}", account) or not re.fullmatch(r"[a-z][a-z0-9-]{2,40}", prefix):
        raise ValueError("Invalid deployment identity")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-[1-9]", region):
        raise ValueError("Invalid AWS region")
    if not re.fullmatch(
        rf"arn:aws:lambda:{region}:{account}:function:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+", function_arn
    ):
        raise ValueError("Use the exact application alias ARN")
    if not re.fullmatch(
        r"[a-z][a-z0-9-]{0,24}/[a-z][a-z0-9-]{0,24}", secret_prefix
    ) or not re.fullmatch(
        rf"arn:aws:secretsmanager:{region}:{account}:secret:{re.escape(secret_prefix)}/email-dispatch-[A-Za-z0-9]{{6}}",
        secret_arn,
    ):
        raise ValueError("Use the target's dedicated email dispatch secret")
    name = prefix + "-email-dispatch"
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": function_arn},
            {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": secret_arn},
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/{name}:*",
            },
        ],
    }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Resources": {
            "Logs": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {"LogGroupName": f"/aws/lambda/{name}", "RetentionInDays": 7},
            },
            "Boundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {"PolicyDocument": policy},
            },
            "Role": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "PermissionsBoundary": {"Ref": "Boundary"},
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
                    "Policies": [{"PolicyName": "EmailDispatch", "PolicyDocument": policy}],
                },
            },
            "Worker": {
                "Type": "AWS::Lambda::Function",
                "DependsOn": "Logs",
                "Properties": {
                    "FunctionName": name,
                    "Runtime": "python3.12",
                    "Handler": "index.handler",
                    "Timeout": 50,
                    "ReservedConcurrentExecutions": 1,
                    "Role": {"Fn::GetAtt": ["Role", "Arn"]},
                    "Environment": {
                        "Variables": {"DISPATCH_SECRET": secret_arn, "API_FUNCTION": function_arn}
                    },
                    "Code": {"ZipFile": HANDLER},
                },
            },
            "Schedule": {
                "Type": "AWS::Events::Rule",
                "Properties": {
                    "ScheduleExpression": "rate(1 minute)",
                    "State": "DISABLED",
                    "Targets": [
                        {
                            "Id": "Dispatch",
                            "Arn": {"Fn::GetAtt": ["Worker", "Arn"]},
                            "RetryPolicy": {"MaximumRetryAttempts": 0},
                        }
                    ],
                },
            },
            "Invoke": {
                "Type": "AWS::Lambda::Permission",
                "Properties": {
                    "Action": "lambda:InvokeFunction",
                    "FunctionName": {"Ref": "Worker"},
                    "Principal": "events.amazonaws.com",
                    "SourceArn": {"Fn::GetAtt": ["Schedule", "Arn"]},
                    "SourceAccount": account,
                },
            },
        },
        "Outputs": {
            "ScheduleName": {"Value": {"Ref": "Schedule"}},
            "Worker": {"Value": {"Ref": "Worker"}},
        },
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("account", "region", "prefix", "function-arn", "secret-arn", "secret-prefix"):
        parser.add_argument("--" + name, required=True)
    print(json.dumps(template(**vars(parser.parse_args())), indent=2))
