"""Prepare/apply a reviewed pre-backup retirement from CloudShell; never delete resources."""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from deployment_journal import release_store
from deployment_profile import load
from operator_checks import require
from operator_errors import PROVIDER_ERRORS, OperatorFailure, safe_reason
from release_record import ReleaseRecord, identity
from release_recovery import claim_key
from release_retirement import apply, digest, prepare
from retirement_observation import archived_contract, observe


def github(path):
    """Read public repository metadata over the fixed GitHub API; fail closed on rate limits."""
    request = urllib.request.Request(
        "https://api.github.com/" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "fitfinity-retirement-review",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        require(len(data) <= 4 * 1024 * 1024, "GitHub recovery response too large")
        return json.loads(data)
    except urllib.error.HTTPError as error:
        require(False, f"GitHub recovery read failed: HTTP {error.code}; no writes authorized")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--mode", choices=("prepare", "apply"), required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    os.umask(0o077)
    profile = load(args.profile)
    read, write = release_store(profile)
    successor = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(
        subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                "HEAD",
                "--",
                "backend/infrastructure",
                "package.json",
                "package-lock.json",
            ],
            check=False,
        ).returncode
        == 0,
        "Recovery source or dependency files have local changes",
    )
    import boto3
    from botocore.config import Config

    session = boto3.Session(region_name=profile["region"])
    config = Config(
        retries={"total_max_attempts": 1},
        connect_timeout=10,
        read_timeout=30,
        ignore_configured_endpoint_urls=True,
    )
    clients = {}
    allowed = {
        ("sts", "get_caller_identity"),
        ("lambda", "get_function"),
        ("lambda", "get_function_concurrency"),
        ("rds", "describe_db_instances"),
        ("cloudformation", "describe_stacks"),
        ("cloudformation", "get_template"),
    }

    def aws(service, operation, values):
        require((service, operation) in allowed, "Recovery provider mutation refused")
        if service not in clients:
            clients[service] = session.client(service, config=config)
        try:
            return getattr(clients[service], operation)(**values)
        except Exception as error:
            response = getattr(error, "response", {})
            detail = response.get("Error", {}) if isinstance(response, dict) else {}
            code = detail.get("Code") if isinstance(detail, dict) else None
            safe_code = (
                code
                if isinstance(code, str) and code in PROVIDER_ERRORS
                else "UnknownProviderError"
            )
            raise OperatorFailure(
                f"Recovery AWS {service}/{operation} failed; code={safe_code}"
            ) from None

    def observed(record, next_source):
        return observe(record, profile, next_source, github, aws, archived_contract)

    def claim():
        return read(claim_key(profile))

    if args.mode == "prepare":
        require(args.sha256 is None, "Digest is only used for apply")
        owner, etag = claim()
        require(
            owner.get("schema_version") == 1
            and owner["identity"] == identity(profile, owner["identity"]["source_sha"]),
            "Target claim differs",
        )
        record = ReleaseRecord(profile, owner["identity"]["source_sha"], read, write)
        record.refresh()
        plan = prepare(
            record.value,
            profile,
            successor,
            observed(record.value, successor),
            etag,
            record.etag,
            time.time(),
        )
        require(claim()[1] == etag, "Claim changed during preparation")
        require(
            read(record.prefix + "current.json")[1] == record.etag,
            "Release changed during preparation",
        )
        with args.review.open("x") as stream:
            json.dump(plan, stream, indent=2)
        print(
            json.dumps(
                {
                    "state": "prepared_only",
                    "review": str(args.review),
                    "sha256": digest(plan),
                    "successor_source": successor,
                    "expires_at": plan["expires_at"],
                    "application_changed": False,
                },
                indent=2,
            )
        )
    else:
        plan = json.loads(args.review.read_text())
        require(plan["successor_source"] == successor, "Checkout differs from reviewed successor")
        record = ReleaseRecord(profile, plan["identity"]["source_sha"], read, write)
        result = apply(
            record, profile, plan, args.sha256, claim, observed, time.time(), clock=time.time
        )
        print(
            json.dumps(
                {
                    **result,
                    "application_changed": False,
                    "claim_transferred": False,
                    "history_preserved": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + safe_reason(error))
        print("Read the original journal before retrying; an acknowledgement may be uncertain.")
        raise SystemExit(1) from None
