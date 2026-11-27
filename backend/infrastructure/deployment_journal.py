"""Retain immutable operation receipts in a private target-owned S3 bucket."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from deployment_profile import load
from operator_checks import require

MAX_BYTES = 4 * 1024 * 1024


class MissingJournalObject(RuntimeError):
    """Identify an absent object without treating denied access as absence."""


def bucket_name(profile):
    """Derive a bounded journal bucket from the reviewed deployment target."""
    name = f"{profile['resource_prefix']}-journal-{profile['account']}-{profile['region']}"
    require(len(name) <= 63, "Journal bucket name exceeds provider limit")
    return name


def access(profile, *, write):
    """Return exact object permissions for an operator and its permissions boundary."""
    return {
        "Effect": "Allow",
        "Action": ["s3:GetObject"] + (["s3:PutObject"] if write else []),
        "Resource": [
            f"arn:aws:s3:::{bucket_name(profile)}/{prefix}/*" for prefix in ("runs", "releases")
        ],
    }


def template(profile):
    """Prepare retained private storage without changing IAM or creating network resources."""
    name = bucket_name(profile)
    arn = f"arn:aws:s3:::{name}"
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Resources": {
            "Journal": {
                "Type": "AWS::S3::Bucket",
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
                "Properties": {
                    "BucketName": name,
                    "PublicAccessBlockConfiguration": {
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    },
                    "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
                    "VersioningConfiguration": {"Status": "Enabled"},
                    "BucketEncryption": {
                        "ServerSideEncryptionConfiguration": [
                            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                        ]
                    },
                    "LifecycleConfiguration": {
                        "Rules": [
                            {
                                "Id": "AbortIncompleteUploads",
                                "Status": "Enabled",
                                "Prefix": "",
                                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                            }
                        ]
                    },
                },
            },
            "JournalPolicy": {
                "Type": "AWS::S3::BucketPolicy",
                "Properties": {
                    "Bucket": {"Ref": "Journal"},
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Deny",
                                "Principal": "*",
                                "Action": "s3:*",
                                "Resource": [arn, arn + "/*"],
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            },
                            {
                                "Effect": "Deny",
                                "Principal": "*",
                                "Action": "s3:PutObject",
                                "Resource": [arn + "/runs/*", arn + "/releases/*/events/*"],
                                "Condition": {"Null": {"s3:if-none-match": "true"}},
                            },
                            {
                                "Effect": "Deny",
                                "Principal": "*",
                                "Action": "s3:PutObject",
                                "Resource": arn + "/releases/*/current.json",
                                "Condition": {
                                    "Null": {"s3:if-none-match": "true", "s3:if-match": "true"}
                                },
                            },
                        ],
                    },
                },
            },
        },
    }


def aws(profile, operation, values, body=None, *, metadata=False):
    """Make one bounded journal request without retries or provider error disclosure."""
    require(operation in {"put-object", "get-object"}, "Unknown journal operation")
    require(
        not any(k.startswith("AWS_ENDPOINT_URL") for k in os.environ), "Endpoint override refused"
    )
    with tempfile.TemporaryDirectory(prefix="fitfinity-journal-") as directory:
        path = Path(directory) / "object.json"
        args = [
            "aws",
            "s3api",
            operation,
            "--region",
            profile["region"],
            "--cli-input-json",
            json.dumps(values),
            "--output",
            "json",
            "--no-cli-pager",
        ]
        if body is not None:
            require(len(body) <= MAX_BYTES, "Journal receipt too large")
            path.write_bytes(body)
            args += ["--body", str(path)]
        else:
            args.append(str(path))
        result = subprocess.run(
            args, capture_output=True, env={**os.environ, "AWS_MAX_ATTEMPTS": "1"}
        )
        if result.returncode and operation == "get-object":
            error = result.stderr.decode("utf-8", errors="replace")
            if re.search(
                r"An error occurred \(NoSuchKey\) when calling the GetObject operation:", error
            ):
                raise MissingJournalObject("Journal object does not exist")
        require(
            result.returncode == 0,
            "Journal request failed; inspect retained local intent, do not replay",
        )
        if body is None:
            require(path.stat().st_size <= MAX_BYTES, "Journal receipt too large")
            payload = path.read_bytes()
            return (payload, json.loads(result.stdout)) if metadata else payload
        return json.loads(result.stdout)


def run_key(run, attempt, name):
    """Bind journal locations to exact producer runs without arbitrary path selection."""
    require(re.fullmatch(r"[1-9][0-9]*", str(run)), "Exact journal run required")
    require(re.fullmatch(r"[1-9][0-9]*", str(attempt)), "Exact journal attempt required")
    require(
        name
        in {
            "maintenance-receipt.json",
            "rollout-receipt.json",
            "schema-upgrade-receipt.json",
            "schema-probe-receipt.json",
        },
        "Unknown journal receipt",
    )
    return f"runs/{run}/{attempt}/{name}/"


class RemoteJournal:
    """Write immutable sequenced events; a failed acknowledgement blocks further effects."""

    def __init__(self, profile, context, name, call=None):
        self.profile, self.context = profile, dict(context)
        self.prefix = run_key(context["run_id"], context["attempt"], name)
        self.call = call or (lambda op, values, body=None: aws(profile, op, values, body))
        self.sequence, self.previous = 0, None
        self.uncertain = False
        require(context["repository"] == profile["github_repository"], "Foreign journal repository")
        require(
            re.fullmatch(r"[a-f0-9]{40}", context["source_sha"]), "Exact journal source required"
        )

    def save(self, receipt):
        """Persist the next event before allowing the caller's cloud mutation."""
        require(
            not self.uncertain, "Journal acknowledgement uncertain; reconcile before continuing"
        )
        event = {
            "schema_version": 1,
            "context": self.context,
            "sequence": self.sequence,
            "previous_sha256": self.previous,
            "receipt": receipt,
        }
        body = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
        require(len(body) <= MAX_BYTES, "Journal receipt too large")
        self.uncertain = True
        self.call(
            "put-object",
            {
                "Bucket": bucket_name(self.profile),
                "ExpectedBucketOwner": self.profile["account"],
                "Key": self.prefix + f"{self.sequence:08d}.json",
                "IfNoneMatch": "*",
                "ServerSideEncryption": "AES256",
                "ContentType": "application/json",
            },
            body,
        )
        self.previous = hashlib.sha256(body).hexdigest()
        self.sequence += 1
        self.uncertain = False


def configured(name):
    """Enable durable receipts only for an explicit, exact target bucket binding."""
    selected = os.getenv("FITFINITY_JOURNAL_BUCKET", "")
    if not selected:
        return None
    profile = load(os.environ["DEPLOYMENT_PROFILE"])
    require(selected == bucket_name(profile), "Journal bucket differs from reviewed target")
    return RemoteJournal(
        profile,
        {
            "repository": os.environ["GITHUB_REPOSITORY"],
            "run_id": os.environ["GITHUB_RUN_ID"],
            "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "source_sha": os.environ["GITHUB_SHA"],
            "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
        },
        name,
    )


def read_event(profile, *, run, attempt, name, sequence, context, previous_sha256, call=None):
    """Read an exact retained event and verify producer, position and hash-chain linkage."""
    require(type(sequence) is int and 0 <= sequence < 100000000, "Invalid journal sequence")
    reader = call or (lambda op, values: aws(profile, op, values))
    body = reader(
        "get-object",
        {
            "Bucket": bucket_name(profile),
            "ExpectedBucketOwner": profile["account"],
            "Key": run_key(run, attempt, name) + f"{sequence:08d}.json",
        },
    )
    require(isinstance(body, bytes) and len(body) <= MAX_BYTES, "Invalid journal bytes")
    event = json.loads(body)
    require(
        event.get("schema_version") == 1
        and event.get("context") == context
        and event.get("sequence") == sequence
        and event.get("previous_sha256") == previous_sha256,
        "Journal producer or chain differs",
    )
    return event, hashlib.sha256(body).hexdigest()


def release_store(profile):
    """Build conditional object access for the target's release records."""
    common = {"Bucket": bucket_name(profile), "ExpectedBucketOwner": profile["account"]}

    def read(key):
        body, response = aws(profile, "get-object", {**common, "Key": key}, metadata=True)
        return json.loads(body), response.get("ETag")

    def write(key, body, *, if_match=None, if_none_match=None):
        require((if_match is None) != (if_none_match is None), "One write condition required")
        condition = {"IfMatch": if_match} if if_match else {"IfNoneMatch": if_none_match}
        response = aws(
            profile,
            "put-object",
            {
                **common,
                "Key": key,
                **condition,
                "ServerSideEncryption": "AES256",
                "ContentType": "application/json",
            },
            body,
        )
        return response.get("ETag")

    return read, write
