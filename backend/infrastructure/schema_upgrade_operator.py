"""Run one protected upgrade step and retain durable intent before cloud mutations."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from deployment_profile import load
from operation_journal import Journal
from operator_checks import require
from schema_probe_operator import aws
from schema_upgrade_execution import execute


def archived_migrations(source, destination):
    """Read approved ancestor migration bytes without executing archived Python code."""
    require(re.fullmatch(r"[0-9a-f]{40}", source or ""), "Exact archived source required")
    subprocess.run(["git", "merge-base", "--is-ancestor", source, "HEAD"], check=True)
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", source, "backend/migrations/versions"], text=True
    ).splitlines()
    for name in names:
        require(
            re.fullmatch(r"backend/migrations/versions/[A-Za-z0-9_]+\.py", name),
            "Unexpected archived migration path",
        )
        (destination / Path(name).name).write_bytes(
            subprocess.check_output(["git", "show", source + ":" + name])
        )


def main():
    """Refuse non-main dispatch and preserve uncertain intent without a mutation retry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["create", "inspect", "invoke", "cleanup", "cleanup-check"], required=True
    )
    for name in ("profile", "review", "receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("image-receipt", "prior", "evidence"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--template-sha256", required=True)
    parser.add_argument("--stack-id")
    args = parser.parse_args()
    profile = load(args.profile)
    require(
        os.getenv("GITHUB_REPOSITORY") == profile["github_repository"]
        and os.getenv("GITHUB_REF") == "refs/heads/main"
        and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and os.getenv("GITHUB_WORKFLOW_REF")
        == profile["github_repository"]
        + "/.github/workflows/aws-schema-upgrade.yml@refs/heads/main",
        "Protected manual main upgrade workflow required",
    )
    source = os.environ["GITHUB_SHA"]
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == source,
        "Checkout source differs",
    )
    review = json.loads(args.review.read_text())
    recovery = args.mode in {"inspect", "cleanup", "cleanup-check"}
    if recovery:
        source = review["binding"]["source_sha"]
    journal = Journal(args.receipt)
    with tempfile.TemporaryDirectory(prefix="fitfinity-upgrade-source-") as directory:
        migrations = None
        if recovery:
            migrations = Path(directory)
            archived_migrations(source, migrations)
        try:
            execute(
                args.mode,
                review,
                args.template_sha256,
                source,
                json.loads(args.image_receipt.read_text()) if args.image_receipt else {},
                lambda service, operation, parameters: aws(
                    service, operation, parameters, profile=profile, purpose="upgrade"
                ),
                journal.save,
                profile=profile,
                stack_id=args.stack_id,
                evidence=json.loads(args.evidence.read_text()) if args.evidence else None,
                prior=json.loads(args.prior.read_text()) if args.prior else None,
                migrations=migrations,
            )
        except Exception:
            journal.save(
                {
                    **journal.value,
                    "error": "Step failed; inspect retained intent and owned resources "
                    "before recovery",
                }
            )
            raise RuntimeError("Upgrade step failed; inspect its retained receipt") from None
    print("Upgrade step receipt retained; staff rollout and live acceptance remain separate")


if __name__ == "__main__":
    main()
