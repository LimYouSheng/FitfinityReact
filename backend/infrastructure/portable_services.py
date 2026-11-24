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


def media_bucket(target):
    """Bind media configuration to the target storage template's retained bucket."""
    name = f"{target['resource_prefix']}-media-{target['account']}-{target['region']}"
    require(len(name) <= 63, "Media bucket name exceeds provider limit")
    return name


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
    bucket = media_bucket(target)
    tags = [
        {"Key": "Application", "Value": "Fitfinity"},
        {"Key": "Environment", "Value": target["environment_tag"]},
    ]
    functions = [target["runtime_function"], target["probe_name"], target["upgrade_name"]]
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
                "Action": "ecr-public:GetAuthorizationToken",
                "Resource": "*",
                "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-1"}},
            },
            {
                "Effect": "Allow",
                "Action": "sts:GetServiceBearerToken",
                "Resource": "*",
                "Condition": {"StringEquals": {"sts:AWSServiceName": "ecr-public.amazonaws.com"}},
            },
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
    return access_template(profile, "Image", target["image_role"], "PublishReviewedImage", document)


def access_template(profile, kind, role_name, policy_name, document):
    """Keep each operator's trust and permission ceiling equal to its explicit policy."""
    target = identities(profile)
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Rules": template_rules(profile),
        "Metadata": {"FitfinityProfile": target["profile_sha256"]},
        "Resources": {
            kind + "Boundary": {
                "Type": "AWS::IAM::ManagedPolicy",
                "Properties": {
                    "ManagedPolicyName": role_name + "-boundary",
                    "PolicyDocument": document,
                },
            },
            kind + "Role": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": role_name,
                    "MaxSessionDuration": 3600,
                    "AssumeRolePolicyDocument": trust(profile),
                    "PermissionsBoundary": {"Ref": kind + "Boundary"},
                    "Policies": [{"PolicyName": policy_name, "PolicyDocument": deepcopy(document)}],
                },
            },
        },
        "Outputs": {kind + "RoleArn": {"Value": {"Fn::GetAtt": [kind + "Role", "Arn"]}}},
    }


def maintenance_access(profile):
    """Prepare a pause/snapshot operator without database credentials or image-write access."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    function = f"arn:aws:lambda:{region}:{account}:function:{target['runtime_function']}"
    database = f"arn:aws:rds:{region}:{account}:db:{target['database']}"
    snapshots = f"arn:aws:rds:{region}:{account}:snapshot:{target['resource_prefix']}-release-*"
    stack = f"arn:aws:cloudformation:{region}:{account}:stack/{target['hosting_stack']}/*"
    changes = f"arn:aws:cloudformation:{region}:{account}:changeSet/release-*/*"
    document = policy(
        [
            {"Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"},
            {
                "Effect": "Allow",
                "Action": [
                    "cloudformation:DescribeStacks",
                    "cloudformation:GetTemplate",
                    "cloudformation:ListStackResources",
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:ExecuteChangeSet",
                ],
                "Resource": [stack, changes],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "lambda:GetFunction",
                    "lambda:GetFunctionConcurrency",
                    "lambda:ListTags",
                    "lambda:PutFunctionConcurrency",
                ],
                "Resource": function,
            },
            {
                "Effect": "Allow",
                "Action": "lambda:TagResource",
                "Resource": function,
                "Condition": {
                    "ForAllValues:StringEquals": {
                        "aws:TagKeys": ["FitfinityMaintenance", "FitfinitySnapshot"]
                    }
                },
            },
            {"Effect": "Allow", "Action": "rds:DescribeDBInstances", "Resource": database},
            {
                "Effect": "Allow",
                "Action": ["rds:CreateDBSnapshot"],
                "Resource": [database, snapshots],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "rds:AddTagsToResource",
                    "rds:DescribeDBSnapshots",
                    "rds:ListTagsForResource",
                ],
                "Resource": snapshots,
            },
        ]
    )
    return access_template(
        profile, "Maintenance", target["maintenance_role"], "PauseAndSnapshot", document
    )
