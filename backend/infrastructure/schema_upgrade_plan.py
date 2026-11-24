"""Prepare a private populated-upgrade review; never bootstrap, invoke or deploy resources."""

import hashlib
import json
from pathlib import Path

from deployment_profile import identities
from operator_checks import require
from private_job_template import render, validate_binding
from release_image_validation import validate_image as validate_published_image
from release_readiness import migration_chain


def prepare(binding, *, profile, source_sha, migrations=None, now=None):
    """Bind a forward-only revision range to exact checked-out migration files and image."""
    target = identities(profile)
    validate_binding(
        binding,
        profile=profile,
        now=now,
        extra_patterns={
            "operation_id": r"[0-9a-f]{32}",
            "from_revision": r"[0-9]{8}_[0-9]{4}",
            "to_revision": r"[0-9]{8}_[0-9]{4}",
        },
    )
    require(binding["source_sha"] == source_sha, "Upgrade source differs from checkout")
    chain = migration_chain(
        migrations or Path(__file__).resolve().parents[1] / "migrations/versions"
    )
    revisions = [row["revision"] for row in chain]
    require(
        binding["to_revision"] == revisions[-1] and binding["from_revision"] in revisions[:-1],
        "Require a known populated start and the exact current migration head",
    )
    template = render(binding, profile=profile, kind="upgrade")
    template_hash = hashlib.sha256(
        json.dumps(template, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "decision": "HOLD",
        "profile_sha256": target["profile_sha256"],
        "binding": dict(binding),
        "template": template,
        "template_sha256": template_hash,
        "migration_chain": chain,
        "invoke_payload": {
            "operation": "upgrade-existing",
            "operation_id": binding["operation_id"],
        },
        "required_evidence": [
            "Exact main source, reviewed image scan and current profile; no artifact substitution",
            "Fresh private catalog with observed start revision, migration identity and grants",
            "Reviewed backup/recovery evidence and maintenance before any database write",
            "Private VPC/subnet/security-group/secret ownership and separately scoped upgrade IAM",
            "Exact owned temporary worker with no public trigger; invoke only the reviewed intent",
            "Verify final schema and runtime access; retain uncertain results without blind replay",
            "Explicit owned-resource cleanup and separately reviewed staff rollout; no downgrade",
        ],
    }


def validate_image(review, receipt, call, *, profile, source_sha, now, migrations=None):
    """Recompute the upgrade review and verify every migration against the published image."""
    checked = prepare(
        review["binding"], profile=profile, source_sha=source_sha, now=now, migrations=migrations
    )
    require(review == checked, "Upgrade review changed; regenerate and review")
    validate_published_image(
        receipt,
        checked["binding"],
        call,
        now,
        profile=profile,
        required_files={
            **{
                "backend/migrations/versions/" + row["file"]: row["sha256"]
                for row in checked["migration_chain"]
            },
            **{
                "backend/app/" + name: hashlib.sha256(
                    (Path(__file__).resolve().parents[1] / "app" / name).read_bytes()
                ).hexdigest()
                for name in (
                    "release_upgrade.py",
                    "release_upgrade_service.py",
                    "runtime_grants.py",
                    "runtime-grants.json",
                )
            },
        },
    )


def main():
    """Write an offline review bundle from explicit metadata; do not contact AWS."""
    import argparse

    from deployment_profile import load

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    result = prepare(
        json.loads(args.bindings.read_text()),
        profile=load(args.profile),
        source_sha=args.source_sha,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Private upgrade review prepared; execution remains HOLD")


if __name__ == "__main__":
    main()
