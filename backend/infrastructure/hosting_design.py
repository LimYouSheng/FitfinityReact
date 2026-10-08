"""First same-origin test deployment. Application and bootstrap code are unchanged."""

import json
import re

import private_runtime_preflight as pf

REVISION = "2026-10-08-test-hosting-1"
MARKER = "Fitfinity_AWS_Test_Login_2026-10-06"
ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
EDGE_REGION = "us-east-1"
ADAPTATION_BASE = "e6b4a13b003ade5e7ee49032d5ca3fe95b1d28a9"  # Adaptation checkpoint only.
IMAGE = pf.binding.URI + "@" + pf.binding.DIGEST
FUNCTION = "fitfinity-test-staff-api"
STACKS = {
    "edge": ("fitfinity-test-login-edge", EDGE_REGION),
    "app": ("fitfinity-test-login", REGION),
}
CACHE_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
ORIGIN_FORWARD = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
API_PATHS = ["auth/*", "api/*", "me", "health/*"]
OWNER_RECEIPT_SHA256 = "4704e2b08a53919047cfe7d51c93ee837dfed25c9f9a31e5f8eb74887621b589"


def ref(name):
    return {"Ref": name}


def attr(name, key):
    return {"Fn::GetAtt": [name, key]}


def sub(value):
    return {"Fn::Sub": value}


def resource(kind, properties, **extra):
    return {"Type": "AWS::" + kind, "Properties": properties, **extra}


def visibility(name):
    # WAF sampled requests can include credentials. Metrics only; no request logging.
    return {"CloudWatchMetricsEnabled": True, "SampledRequestsEnabled": False, "MetricName": name}


def waf(scope):
    name = "fitfinity-test-login-" + scope.lower()
    return resource(
        "WAFv2::WebACL",
        {
            "Name": name,
            "Scope": scope,
            "DefaultAction": {"Allow": {}},
            "VisibilityConfig": visibility(name),
            "Rules": [
                {
                    "Name": "RequestRate",
                    "Priority": 0,
                    "Action": {"Block": {}},
                    "Statement": {
                        "RateBasedStatement": {
                            "AggregateKeyType": "IP",
                            "Limit": 2000,
                            "EvaluationWindowSec": 300,
                        }
                    },
                    "VisibilityConfig": visibility(name + "-rate"),
                },
                {
                    "Name": "KnownBadInputs",
                    "Priority": 1,
                    "OverrideAction": {"None": {}},
                    "Statement": {
                        "ManagedRuleGroupStatement": {
                            "VendorName": "AWS",
                            "Name": "AWSManagedRulesKnownBadInputsRuleSet",
                        }
                    },
                    "VisibilityConfig": visibility(name + "-inputs"),
                },
            ],
        },
    )


def edge_template():
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Fitfinity TEST login CloudFront WAF. No application data in this region.",
        "Resources": {"EdgeAcl": waf("CLOUDFRONT")},
        "Outputs": {"WebAclArn": {"Value": attr("EdgeAcl", "Arn")}},
    }


def runtime_policy():
    app_secret = (
        "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fi"
        "tfinity/test/database/app-cqKagk"
    )
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"],
                "Resource": [app_secret, pf.deploy.CONFIG["auth_secret"]],
                "Condition": {"StringEquals": {"secretsmanager:VersionStage": "AWSCURRENT"}},
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/lambda/{FUNCTION}:*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateNetworkInterface",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeSubnets",
                    "ec2:DeleteNetworkInterface",
                    "ec2:AssignPrivateIpAddresses",
                    "ec2:UnassignPrivateIpAddresses",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Deny",
                "Action": [
                    "ec2:CreateNetworkInterface",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeSubnets",
                    "ec2:DeleteNetworkInterface",
                    "ec2:AssignPrivateIpAddresses",
                    "ec2:UnassignPrivateIpAddresses",
                    "ec2:DetachNetworkInterface",
                ],
                "Resource": "*",
                "Condition": {
                    "ArnEquals": {
                        "lambda:SourceFunctionArn": (
                            f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION}"
                        )
                    }
                },
            },
        ],
    }


def app_template(frontend_prefix, edge_arn):
    pf.require(
        re.fullmatch(r"releases/[a-f0-9]{40}/[a-f0-9]{64}", frontend_prefix),
        "Invalid frontend release prefix",
    )
    pf.require(
        re.fullmatch(
            (
                "arn:aws:wafv2:us-east-1:418638389566:global/webacl/fitfinity"
                "-test-login-cloudfront/[a-f0-9-]{36}"
            ),
            edge_arn,
        ),
        "Invalid edge ACL identity",
    )
    api_domain = sub("${Api}.execute-api.ap-southeast-1.amazonaws.com")
    headers = {
        "ContentTypeOptions": {"Override": True},
        "FrameOptions": {"FrameOption": "DENY", "Override": True},
        "ReferrerPolicy": {"ReferrerPolicy": "no-referrer", "Override": True},
        "StrictTransportSecurity": {"AccessControlMaxAgeSec": 31536000, "Override": True},
    }
    static = {
        "TargetOriginId": "frontend",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": ["GET", "HEAD"],
        "CachedMethods": ["GET", "HEAD"],
        "CachePolicyId": ref("StaticCache"),
        "Compress": True,
        "ResponseHeadersPolicyId": ref("ResponseHeaders"),
    }
    api = {
        "TargetOriginId": "api",
        "ViewerProtocolPolicy": "https-only",
        "AllowedMethods": ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"],
        "CachedMethods": ["GET", "HEAD"],
        "CachePolicyId": CACHE_DISABLED,
        "OriginRequestPolicyId": ORIGIN_FORWARD,
        "Compress": False,
        "ResponseHeadersPolicyId": ref("ResponseHeaders"),
    }
    env = {
        "FITFINITY_CONFIG_SOURCE": "aws-secrets-manager",
        "FITFINITY_ENVIRONMENT": "staging",
        "FITFINITY_AWS_ACCOUNT_ID": ACCOUNT,
        "FITFINITY_DATABASE_SECRET_ARN": runtime_policy()["Statement"][0]["Resource"][0],
        "FITFINITY_AUTH_SECRET_ARN": pf.deploy.CONFIG["auth_secret"],
        "FITFINITY_DB_HOST": "fitfinity-test-db.c1ak66620gza.ap-southeast-1.rds.amazonaws.com",
        "FITFINITY_DB_NAME": "fitfinity",
        "FITFINITY_AUTH_ENABLED": "true",
        "FITFINITY_COGNITO_POOL_ID": "ap-southeast-1_La0Y3MXCj",
        "FITFINITY_COGNITO_CLIENT_ID": "2jj6r722g5591u5kf2b812pkgm",
        "FITFINITY_ALLOWED_HOSTS": sub(
            '["127.0.0.1","${Api}.execute-api.ap-southeast-1.amazonaws.com"]'
        ),
        "FITFINITY_AUTH_ORIGINS": sub('["https://${Distribution.DomainName}"]'),
        "FITFINITY_AUTH_COOKIE_SECURE": "true",
        "FITFINITY_STAFF_INVITATIONS_ENABLED": "false",
        "FITFINITY_DB_POOL_SIZE": "1",
        "FITFINITY_DB_POOL_RECYCLE_SECONDS": "60",
        "AWS_LWA_PORT": "8080",
        "AWS_LWA_READINESS_CHECK_PATH": "/health/live",
        "AWS_LWA_READINESS_CHECK_HEALTHY_STATUS": "200",
    }
    resources = {
        "FrontendBucket": resource(
            "S3::Bucket",
            {
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
                "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                    ]
                },
                "VersioningConfiguration": {"Status": "Enabled"},
            },
            DeletionPolicy="Retain",
            UpdateReplacePolicy="Retain",
        ),
        "OriginAccess": resource(
            "CloudFront::OriginAccessControl",
            {
                "OriginAccessControlConfig": {
                    "Name": "fitfinity-test-login-s3",
                    "OriginAccessControlOriginType": "s3",
                    "SigningBehavior": "always",
                    "SigningProtocol": "sigv4",
                }
            },
        ),
        "StaticCache": resource(
            "CloudFront::CachePolicy",
            {
                "CachePolicyConfig": {
                    "Name": "fitfinity-test-login-static",
                    "MinTTL": 0,
                    "DefaultTTL": 0,
                    "MaxTTL": 31536000,
                    "ParametersInCacheKeyAndForwardedToOrigin": {
                        "EnableAcceptEncodingGzip": True,
                        "EnableAcceptEncodingBrotli": True,
                        "CookiesConfig": {"CookieBehavior": "none"},
                        "HeadersConfig": {"HeaderBehavior": "none"},
                        "QueryStringsConfig": {"QueryStringBehavior": "none"},
                    },
                }
            },
        ),
        "ResponseHeaders": resource(
            "CloudFront::ResponseHeadersPolicy",
            {
                "ResponseHeadersPolicyConfig": {
                    "Name": "fitfinity-test-login-security",
                    "SecurityHeadersConfig": headers,
                }
            },
        ),
        "Api": resource(
            "ApiGateway::RestApi",
            {
                "Name": "fitfinity-test-staff-api",
                "EndpointConfiguration": {"Types": ["REGIONAL"]},
                "DisableExecuteApiEndpoint": False,
            },
        ),
        "Distribution": resource(
            "CloudFront::Distribution",
            {
                "DistributionConfig": {
                    "Comment": "Fitfinity TEST staff login " + frontend_prefix.split("/")[1],
                    "Enabled": True,
                    "DefaultRootObject": "index.html",
                    "HttpVersion": "http2",
                    "IPV6Enabled": True,
                    "PriceClass": "PriceClass_All",
                    "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
                    "WebACLId": edge_arn,
                    "Origins": [
                        {
                            "Id": "frontend",
                            "DomainName": attr("FrontendBucket", "RegionalDomainName"),
                            "OriginPath": "/" + frontend_prefix,
                            "OriginAccessControlId": ref("OriginAccess"),
                            "S3OriginConfig": {"OriginAccessIdentity": ""},
                        },
                        {
                            "Id": "api",
                            "DomainName": api_domain,
                            "OriginPath": "/test",
                            "CustomOriginConfig": {
                                "HTTPSPort": 443,
                                "OriginProtocolPolicy": "https-only",
                                "OriginSSLProtocols": ["TLSv1.2"],
                                "OriginReadTimeout": 30,
                                "OriginKeepaliveTimeout": 5,
                            },
                        },
                    ],
                    "DefaultCacheBehavior": static,
                    "CacheBehaviors": [{"PathPattern": path, **api} for path in API_PATHS],
                    "CustomErrorResponses": [
                        {"ErrorCode": code, "ErrorCachingMinTTL": 0}
                        for code in [400, 403, 404, 405, 414, 416, 500, 501, 502, 503, 504]
                    ],
                }
            },
        ),
        "BucketPolicy": resource(
            "S3::BucketPolicy",
            {
                "Bucket": ref("FrontendBucket"),
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "cloudfront.amazonaws.com"},
                            "Action": "s3:GetObject",
                            "Resource": sub("${FrontendBucket.Arn}/*"),
                            "Condition": {
                                "StringEquals": {
                                    "AWS:SourceArn": sub(
                                        "arn:aws:cloudfront::418638389566:"
                                        "distribution/${Distribution}"
                                    )
                                }
                            },
                        },
                        {
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:*",
                            "Resource": [
                                attr("FrontendBucket", "Arn"),
                                sub("${FrontendBucket.Arn}/*"),
                            ],
                            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                        },
                    ],
                },
            },
        ),
        "ApiLogs": resource(
            "Logs::LogGroup", {"LogGroupName": "/aws/lambda/" + FUNCTION, "RetentionInDays": 7}
        ),
        "ApiRole": resource(
            "IAM::Role",
            {
                "RoleName": "fitfinity-test-hosting-api",
                "PermissionsBoundary": (
                    "arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary"
                ),
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
                    {"PolicyName": "FitfinityTestLogin", "PolicyDocument": runtime_policy()}
                ],
            },
        ),
        "ApiFunction": resource(
            "Lambda::Function",
            {
                "FunctionName": FUNCTION,
                "PackageType": "Image",
                "Code": {"ImageUri": IMAGE},
                "Architectures": ["x86_64"],
                "MemorySize": 512,
                "Timeout": 25,
                "ReservedConcurrentExecutions": 2,
                "Role": attr("ApiRole", "Arn"),
                "VpcConfig": {
                    "SubnetIds": [],
                    "SecurityGroupIds": ["sg-09bcb69b70968f702"],
                    "Ipv6AllowedForDualStack": False,
                },
                "Environment": {"Variables": env},
            },
            DependsOn=["ApiLogs"],
        ),
        "ApiVersion": resource(
            "Lambda::Version",
            {"FunctionName": ref("ApiFunction"), "Description": frontend_prefix.split("/")[1]},
        ),
        "ApiAlias": resource(
            "Lambda::Alias",
            {
                "Name": "first-test",
                "FunctionName": ref("ApiFunction"),
                "FunctionVersion": attr("ApiVersion", "Version"),
            },
        ),
        "ProxyResource": resource(
            "ApiGateway::Resource",
            {
                "RestApiId": ref("Api"),
                "ParentId": attr("Api", "RootResourceId"),
                "PathPart": "{proxy+}",
            },
        ),
        "ProxyMethod": resource(
            "ApiGateway::Method",
            {
                "RestApiId": ref("Api"),
                "ResourceId": ref("ProxyResource"),
                "HttpMethod": "ANY",
                "AuthorizationType": "NONE",
                "Integration": {
                    "Type": "AWS_PROXY",
                    "IntegrationHttpMethod": "POST",
                    "TimeoutInMillis": 29000,
                    "Uri": sub(
                        "arn:aws:apigateway:ap-southeast-1:lambda:path/2015-03-31/fun"
                        "ctions/${ApiAlias}/invocations"
                    ),
                },
            },
        ),
        "GatewayPermission": resource(
            "Lambda::Permission",
            {
                "Action": "lambda:InvokeFunction",
                "FunctionName": ref("ApiAlias"),
                "Principal": "apigateway.amazonaws.com",
                "SourceAccount": ACCOUNT,
                "SourceArn": sub("arn:aws:execute-api:ap-southeast-1:418638389566:${Api}/test/*/*"),
            },
        ),
        "ApiDeployment": resource(
            "ApiGateway::Deployment", {"RestApiId": ref("Api")}, DependsOn=["ProxyMethod"]
        ),
        "ApiStage": resource(
            "ApiGateway::Stage",
            {
                "RestApiId": ref("Api"),
                "DeploymentId": ref("ApiDeployment"),
                "StageName": "test",
                "CacheClusterEnabled": False,
                "TracingEnabled": False,
                "MethodSettings": [
                    {
                        "ResourcePath": "/*",
                        "HttpMethod": "*",
                        "CachingEnabled": False,
                        "DataTraceEnabled": False,
                        "LoggingLevel": "OFF",
                        "MetricsEnabled": True,
                        "ThrottlingBurstLimit": 10,
                        "ThrottlingRateLimit": 5,
                    }
                ],
            },
        ),
        "RegionalAcl": waf("REGIONAL"),
        "ApiWaf": resource(
            "WAFv2::WebACLAssociation",
            {
                "WebACLArn": attr("RegionalAcl", "Arn"),
                "ResourceArn": sub(
                    "arn:aws:apigateway:ap-southeast-1::/restapis/${Api}/stages/test"
                ),
            },
            DependsOn=["ApiStage"],
        ),
        "ApiErrors": resource(
            "CloudWatch::Alarm",
            {
                "AlarmName": "fitfinity-test-login-api-errors",
                "AlarmDescription": (
                    "Fitfinity test API errors; no notification recipient configured."
                ),
                "Namespace": "AWS/Lambda",
                "MetricName": "Errors",
                "Dimensions": [{"Name": "FunctionName", "Value": ref("ApiFunction")}],
                "Statistic": "Sum",
                "Period": 60,
                "EvaluationPeriods": 1,
                "Threshold": 1,
                "ComparisonOperator": "GreaterThanOrEqualToThreshold",
                "TreatMissingData": "notBreaching",
            },
        ),
    }
    resources["Distribution"]["Properties"]["Tags"] = [
        {"Key": key, "Value": value}
        for key, value in {
            "Application": "Fitfinity",
            "Environment": "test",
            "Purpose": "first-login-v1",
        }.items()
    ]
    # Resolve the accepted second subnet from the canonical database owner, not a duplicate guess.
    from authentication_secrets import AuthenticationSecretOperator
    from operator_context import OperatorContext

    resources["ApiFunction"]["Properties"]["VpcConfig"]["SubnetIds"] = [
        AuthenticationSecretOperator(context=OperatorContext()).db.SUBNET_A,
        AuthenticationSecretOperator(context=OperatorContext()).db.SUBNET_B,
    ]
    outputs = {
        "FrontendDomain": attr("Distribution", "DomainName"),
        "DistributionId": ref("Distribution"),
        "FrontendBucket": ref("FrontendBucket"),
        "ApiId": ref("Api"),
        "FunctionName": ref("ApiFunction"),
        "FunctionVersion": attr("ApiVersion", "Version"),
        "FunctionAlias": ref("ApiAlias"),
        "RuntimeRole": ref("ApiRole"),
        "RegionalWebAclArn": attr("RegionalAcl", "Arn"),
    }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": (
            "Fitfinity first TEST authentication release. No Owner bootstrap or migrations."
        ),
        "Resources": resources,
        "Outputs": {k: {"Value": v} for k, v in outputs.items()},
    }


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
