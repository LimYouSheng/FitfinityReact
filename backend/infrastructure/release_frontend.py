"""Upload immutable frontend objects with durable intent and read-only recovery."""

import re
import time
from copy import deepcopy

from deployment_profile import identities
from hosting_frontend import inventory, manifest_hash
from operator_checks import require


def transfer(review, folder, profile, call, persist, *, prior=None, inspect=False, clock=time.time):
    """Verify owned storage and record each conditional write before calling S3."""
    target = identities(profile)
    require(
        set(review)
        == {"source_sha", "profile_sha256", "manifest_sha256", "stack_arn", "expires_at"}
        and re.fullmatch(r"[a-f0-9]{40}", review["source_sha"])
        and review["profile_sha256"] == target["profile_sha256"]
        and type(review["expires_at"]) is int,
        "Exact frontend review required",
    )
    stack_prefix = (
        f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
        + target["hosting_stack"]
        + "/"
    )
    require(
        re.fullmatch(re.escape(stack_prefix) + r"[a-f0-9-]+", review["stack_arn"]),
        "Frontend stack target differs",
    )
    files = inventory(folder)
    require(manifest_hash(files) == review["manifest_sha256"], "Frontend artifact changed")
    identity = dict(review)
    state = deepcopy(prior) if prior is not None else {"identity": identity, "objects": {}}
    require(state.get("identity") == identity, "Original frontend receipt required")
    require(set(state.get("objects", {})) <= set(files), "Unexpected frontend receipt object")
    caller = call("sts", "get-caller-identity", {})
    require(
        caller.get("Account") == target["account"]
        and re.fullmatch(
            f"arn:aws:sts::{target['account']}:assumed-role/"
            + re.escape(target["hosting_role"])
            + r"/[^/]+",
            caller.get("Arn", ""),
        ),
        "Exact frontend operator role required",
    )
    stacks = call("cloudformation", "describe-stacks", {"StackName": review["stack_arn"]})["Stacks"]
    require(
        len(stacks) == 1
        and stacks[0].get("StackId") == review["stack_arn"]
        and stacks[0].get("StackStatus")
        in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}
        and not stacks[0].get("ParentId"),
        "Stable owned frontend stack required",
    )
    resource = call(
        "cloudformation",
        "describe-stack-resource",
        {
            "StackName": review["stack_arn"],
            "LogicalResourceId": "FrontendBucket",
        },
    )["StackResourceDetail"]
    bucket = resource.get("PhysicalResourceId", "")
    require(
        resource.get("StackId") == review["stack_arn"]
        and resource.get("LogicalResourceId") == "FrontendBucket"
        and resource.get("ResourceType") == "AWS::S3::Bucket"
        and resource.get("ResourceStatus") in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
        and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket),
        "Owned frontend bucket required",
    )
    require(state.get("bucket", bucket) == bucket, "Frontend bucket changed during recovery")
    state["bucket"] = bucket
    prefix = f"releases/{review['source_sha']}/{review['manifest_sha256']}"
    for name, row in files.items():
        args = {
            "Bucket": bucket,
            "Key": prefix + "/" + name,
            "ExpectedBucketOwner": target["account"],
        }
        existing = call("s3api", "head-object", {**args, "ChecksumMode": "ENABLED"})
        if existing is None:
            require(not inspect, "Frontend object absent; inspection never uploads")
            require(
                name not in state["objects"],
                "Original upload is unresolved; inspect before recovery",
            )
            require(0 < review["expires_at"] - clock() <= 3600, "Frontend review expired")
            require(inventory(folder) == files, "Frontend changed before upload")
            state["objects"][name] = "submitted"
            state["state"] = "uploading"
            persist(deepcopy(state))
            require(0 < review["expires_at"] - clock() <= 3600, "Frontend review expired")
            call(
                "s3api",
                "put-object",
                {
                    **args,
                    "Body": (folder / name).read_bytes(),
                    "IfNoneMatch": "*",
                    "ContentType": row["content_type"],
                    "CacheControl": row["cache_control"],
                    "ChecksumSHA256": row["checksum"],
                    "ServerSideEncryption": "AES256",
                },
            )
            existing = call("s3api", "head-object", {**args, "ChecksumMode": "ENABLED"})
        require(
            isinstance(existing, dict)
            and existing.get("ContentLength") == row["bytes"]
            and existing.get("ChecksumSHA256") == row["checksum"]
            and existing.get("ContentType") == row["content_type"]
            and existing.get("CacheControl") == row["cache_control"]
            and existing.get("ServerSideEncryption") == "AES256",
            "Frontend object differs; overwrite refused",
        )
        state["objects"][name] = "verified"
        persist(deepcopy(state))
    state["state"] = "verified"
    persist(deepcopy(state))
    return state
