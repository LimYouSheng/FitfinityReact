"""Verify exact published image, source-file bindings and fresh complete scan evidence."""

import re
from datetime import UTC, datetime

from deployment_profile import identities
from operator_checks import require
from release_image import scan_policy


def validate_image(receipt, binding, call, now, *, profile, required_files):
    """Require a matching publication receipt and fresh live scan without starting one."""
    require(
        isinstance(required_files, dict)
        and bool(required_files)
        and all(
            isinstance(path, str)
            and isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value)
            for path, value in required_files.items()
        ),
        "Exact required source-file hashes required",
    )
    target = identities(profile)
    account, region = target["account"], target["region"]
    uri = target["registry"] + "/" + target["image_repository"]
    require(
        receipt.get("profile_sha256") == target["profile_sha256"]
        and receipt.get("account") == account
        and receipt.get("region") == region
        and receipt.get("revision") == binding["source_sha"]
        and receipt.get("image_digest") == binding["image_digest"]
        and receipt.get("image_uri") == uri + "@" + binding["image_digest"]
        and all(
            receipt.get(key) is True
            for key in ("candidate_ready", "image_published", "scan_policy_passed")
        )
        and isinstance(receipt.get("source_files"), dict)
        and all(
            receipt["source_files"].get(path) == value for path, value in required_files.items()
        ),
        "Image publication receipt differs",
    )
    pages, tokens = [], set()
    arguments = {
        "repositoryName": target["image_repository"],
        "imageId": {"imageDigest": binding["image_digest"]},
    }
    while True:
        page = call("ecr", "describe-image-scan-findings", arguments)
        require(
            page.get("imageScanStatus", {}).get("status") == "COMPLETE", "Image scan is incomplete"
        )
        pages.append(page)
        token = page.get("nextToken")
        if not token:
            break
        require(token not in tokens and len(pages) < 100, "Invalid image scan pagination")
        tokens.add(token)
        arguments = {**arguments, "nextToken": token}
    scan_policy(pages, binding["image_digest"], datetime.fromtimestamp(now, UTC), profile=profile)
