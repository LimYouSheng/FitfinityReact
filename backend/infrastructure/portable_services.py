"""Prepare portable identity, object storage and image-publication access templates."""

import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

from deployment_profile import identities, template_rules
from operator_checks import require


def policy(statements):
    """Construct a versioned policy with explicit statements."""
    return {"Version": "2012-10-17", "Statement": statements}


def trust(profile):
    """Bind OIDC access to the selected repository and protected environment."""
    target = identities(profile)
    return policy(
        [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Principal": {
                    "Federated": (
                        f"arn:aws:iam::{target['account']}:"
                        "oidc-provider/token.actions.githubusercontent.com"
                    )
                },
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": target["oidc_subject"],
                    }
                },
            }
        ]
    )


def identity(profile, *, session_hours, staff_portal_url):
    """Retain the reviewed Cognito security policy while rebinding region and naming."""
    target = identities(profile)
    require(type(session_hours) is int and 1 <= session_hours <= 168, "Review session lifetime")
    if staff_portal_url:
        parsed = urlsplit(staff_portal_url)
        require(
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and not any(char in staff_portal_url for char in '*<>"\\\r\n'),
            "Exact HTTPS staff portal URL required",
        )
    template = json.loads(Path(__file__).with_name("cognito.json").read_text())
    template["Description"] = "Portable staff Cognito pool; required MFA and fixed role policy"
    template["Rules"] = template_rules(profile)
    template["Parameters"]["SessionHours"]["Default"] = session_hours
    template["Parameters"]["StaffPortalUrl"]["Default"] = staff_portal_url
    template["Resources"]["StaffPool"]["Properties"]["UserPoolName"] = (
        target["resource_prefix"] + "-staff"
    )
    template["Metadata"] = {"FitfinityProfile": target["profile_sha256"]}
    return template


def storage(profile, *, browser_origin):
    """Render retained private media and immutable image storage with target-only access."""
    target = identities(profile)
    parsed = urlsplit(browser_origin)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and not any(char in browser_origin for char in '*<>"\\\r\n'),
        "Exact HTTPS browser origin required",
    )
    account, region, prefix = target["account"], target["region"], target["resource_prefix"]
    bucket = f"{prefix}-media-{account}-{region}"
    require(len(bucket) <= 63, "Media bucket name exceeds provider limit")
    tags = [
        {"Key": "Application", "Value": "Fitfinity"},
        {"Key": "Environment", "Value": target["environment_tag"]},
    ]
    functions = [target["runtime_function"], target["probe_name"], prefix + "-migration"]
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Rules": template_rules(profile),
        "Description": "Portable immutable images and private retained session media",
        "Metadata": {"FitfinityProfile": target["profile_sha256"]},
        "Resources": {
            "Images": {
                "Type": "AWS::ECR::Repository",
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
                "Properties": {
                    "RepositoryName": target["image_repository"],
                    "ImageTagMutability": "IMMUTABLE",
                    "EncryptionConfiguration": {"EncryptionType": "AES256"},
                    "ImageScanningConfiguration": {"ScanOnPush": True},
                    "Tags": tags + [{"Key": "ManagedBy", "Value": prefix + "-image-uploader"}],
                    "RepositoryPolicyText": policy(
                        [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "lambda.amazonaws.com"},
                                "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                                "Condition": {
                                    "ArnLike": {
                                        "aws:SourceArn": [
                                            f"arn:aws:lambda:{region}:{account}:function:{name}"
                                            for name in functions
                                        ]
                                    }
                                },
                            }
                        ]
                    ),
                },
            },
            "Media": {
                "Type": "AWS::S3::Bucket",
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
                "Properties": {
                    "BucketName": bucket,
                    "Tags": tags,
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
                    "CorsConfiguration": {
                        "CorsRules": [
                            {
                                "AllowedOrigins": [browser_origin],
                                "AllowedMethods": ["GET", "PUT", "HEAD"],
                                "AllowedHeaders": ["*"],
                                "ExposeHeaders": ["ETag", "x-amz-checksum-sha256"],
                                "MaxAge": 300,
                            }
                        ]
                    },
                },
            },
            "MediaPolicy": {
                "Type": "AWS::S3::BucketPolicy",
                "Properties": {
                    "Bucket": {"Ref": "Media"},
                    "PolicyDocument": policy(
                        [
                            {
                                "Effect": "Deny",
                                "Principal": "*",
                                "Action": "s3:*",
                                "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        ]
                    ),
                },
            },
        },
        "Outputs": {
            "MediaBucket": {"Value": {"Ref": "Media"}},
            "ImageRepository": {"Value": {"Ref": "Images"}},
            "ImageRepositoryUri": {"Value": {"Fn::GetAtt": ["Images", "RepositoryUri"]}},
        },
    }


def image_access(profile):
    """Grant only image publication/scan access, never deployment or secret retrieval."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    repository = f"arn:aws:ecr:{region}:{account}:repository/{target['image_repository']}"
    condition = {"StringEquals": {"aws:RequestedRegion": region}}
    document = policy(
        [
            {
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken", "ecr:GetRegistryScanningConfiguration"],
                "Resource": "*",
                "Condition": condition,
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:DescribeRepositories",
                    "ecr:ListTagsForResource",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:PutImage",
                    "ecr:StartImageScan",
                    "ecr:DescribeImageScanFindings",
                ],
                "Resource": repository,
                "Condition": condition,
            },
        ]
    )
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Rules": template_rules(profile),
        "Metadata": {"FitfinityProfile": target["profile_sha256"]},
        "Resources": {
            "ImageBoundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": target["image_role"] + "-boundary",
                    "PolicyDocument": document,
                },
            },
            "ImageRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": target["image_role"],
                    "MaxSessionDuration": 3600,
                    "AssumeRolePolicyDocument": trust(profile),
                    "PermissionsBoundary": {"Ref": "ImageBoundary"},
                    "Policies": [
                        {"PolicyName": "PublishReviewedImage", "PolicyDocument": deepcopy(document)}
                    ],
                },
            },
        },
        "Outputs": {"ImageRoleArn": {"Value": {"Fn::GetAtt": ["ImageRole", "Arn"]}}},
    }
