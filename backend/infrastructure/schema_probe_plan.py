"""Offline private catalog-probe template; does not create, invoke or delete AWS resources."""

import argparse
import hashlib
import json
from pathlib import Path

from deployment_profile import DEVELOPER, identities, load
from operator_checks import require
from private_job_template import render, validate_binding


def prepare(binding, *, now=None, profile=DEVELOPER):
    validate_binding(
        binding, now=now, profile=profile, extra_patterns={"sql_sha256": r"[0-9a-f]{64}"}
    )
    template = render(binding, profile=profile, kind="probe")
    return {
        "decision": "HOLD",
        "template": template,
        "invoke_payload": {"operation": "observe-schema"},
        "required_evidence": [
            "Account-plan eligibility, cost and explicit create/invoke/delete authority",
            "Review secret KMS key; any required customer-key decrypt grant must be exact",
            "Verify subnet/VPC/security-group/secret identities and private connectivity",
            "Scanned image/source/SQL bindings; reviewed operator IAM; no hosting-role broadening",
            "Inspect function bindings and no public triggers before synchronous invocation",
            "Retain receipt; delete only the probe stack; verify cleanup; expiry is not cleanup",
        ],
    }


def prepare_review(binding, source_sha, sql, *, now=None, profile=DEVELOPER):
    """Bind the offline probe review to the checked-out source and packaged SQL."""
    require(binding.get("source_sha") == source_sha, "Probe source differs from checkout")
    require(
        binding.get("sql_sha256") == hashlib.sha256(sql).hexdigest(),
        "Probe SQL differs from packaged catalog query",
    )
    plan = prepare(binding, now=now, profile=profile)
    template_bytes = json.dumps(plan["template"], sort_keys=True, separators=(",", ":")).encode()
    return {
        **plan,
        "profile": dict(profile),
        "profile_sha256": identities(profile)["profile_sha256"],
        "bindings": dict(binding),
        "source_sha": source_sha,
        "sql_sha256": binding["sql_sha256"],
        "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
        "expires_at": binding["expires_at"],
        "image_attestation": "Not verified; review exact published image and scan receipt",
    }


def write_review(review, output):
    """Write a new immutable review directory with the exact probe request bytes."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "review.json").write_text(json.dumps(review, indent=2))
    (output / "template.json").write_text(
        json.dumps(review["template"], sort_keys=True, separators=(",", ":"))
    )
    (output / "invoke.json").write_text(json.dumps(review["invoke_payload"], separators=(",", ":")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--profile", type=Path, default=Path(__file__).with_name("targets") / "developer.json"
    )
    args = parser.parse_args()
    review = prepare_review(
        json.loads(args.bindings.read_text()),
        args.source_sha,
        Path(__file__).with_name("read-schema.sql").read_bytes(),
        profile=load(args.profile),
    )
    write_review(review, args.output)
