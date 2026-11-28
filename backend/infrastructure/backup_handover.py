"""Review an explicit forward migration using an existing drained backup."""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from operator_checks import require
from release_observation import digest
from release_readiness import migration_chain


def chain_at(source):
    """Parse tracked migration blobs without importing or executing their code."""
    require(re.fullmatch(r"[a-f0-9]{40}", source or ""), "Exact handover source required")
    root = "backend/migrations/versions/"
    rows = subprocess.check_output(["git", "ls-tree", "-rz", source, "--", root]).split(b"\0")
    with tempfile.TemporaryDirectory(prefix="fitfinity-handover-") as folder:
        for row in filter(None, rows):
            metadata, path = row.split(b"\t", 1)
            mode, kind, blob = metadata.split()
            name = path.decode().removeprefix(root)
            require(
                mode == b"100644" and kind == b"blob" and "/" not in name,
                "Migration inventory contains redirected or executable files",
            )
            if name.endswith(".py"):
                Path(folder, name).write_bytes(
                    subprocess.check_output(["git", "cat-file", "blob", blob.decode()])
                )
        return migration_chain(Path(folder))


def migration_evidence(previous, current, revision):
    """Require an ancestor and an unchanged applied chain with only forward additions."""
    before, after = chain_at(previous), chain_at(current)
    require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", previous, current],
            capture_output=True,
            check=False,
        ).returncode
        == 0,
        "Backup source is not an ancestor",
    )
    require(
        before[-1]["revision"] == revision
        and len(after) > len(before)
        and after[: len(before)] == before,
        "Handover requires unchanged applied migrations and a forward extension",
    )
    for path in ("backend/infrastructure/read-schema.sql",):
        blobs = [
            subprocess.check_output(["git", "rev-parse", f"{source}:{path}"], text=True).strip()
            for source in (previous, current)
        ]
        require(blobs[0] == blobs[1], "Baseline catalog contract changed")
    return {
        "from_revision": revision,
        "to_revision": after[-1]["revision"],
        "applied_chain_sha256": digest(before),
        "target_chain_sha256": digest(after),
    }


def proposal(maintenance, baseline, source):
    """Produce exact metadata for explicit review; never transfer resource ownership."""
    from backup_transition import source_fingerprint

    previous = maintenance["identity"]["source_sha"]
    revisions = baseline.get("alembic_revisions")
    require(
        isinstance(revisions, list) and len(revisions) == 1,
        "Original populated catalog revision required",
    )
    require(
        maintenance.get("state") == "snapshot_ready"
        and maintenance.get("snapshot_requested") is True,
        "Verified original backup required",
    )
    return {
        "schema_version": 1,
        "from_source": previous,
        "to_source": source,
        "from_inputs_sha256": source_fingerprint(previous),
        "to_inputs_sha256": source_fingerprint(source),
        "maintenance_sha256": digest(maintenance),
        "baseline_catalog_sha256": digest(baseline),
        **migration_evidence(previous, source, revisions[0]),
    }


def validate(proof, previous, current):
    """Recompute source and migration bindings when consuming a completed handover."""
    from backup_transition import source_fingerprint

    require(
        isinstance(proof, dict)
        and proof.get("schema_version") == 1
        and proof.get("from_source") == previous
        and proof.get("to_source") == current,
        "Reviewed backup handover source differs",
    )
    expected = {
        "schema_version": 1,
        "from_source": previous,
        "to_source": current,
        "from_inputs_sha256": source_fingerprint(previous),
        "to_inputs_sha256": source_fingerprint(current),
        "maintenance_sha256": proof.get("maintenance_sha256"),
        "baseline_catalog_sha256": proof.get("baseline_catalog_sha256"),
        **migration_evidence(previous, current, proof.get("from_revision")),
    }
    require(
        proof == expected
        and all(
            re.fullmatch(r"[a-f0-9]{64}", proof.get(key, ""))
            for key in ("maintenance_sha256", "baseline_catalog_sha256")
        ),
        "Reviewed backup handover evidence differs",
    )
    return proof["to_inputs_sha256"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maintenance", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            proposal(
                json.loads(args.maintenance.read_text()),
                json.loads(args.baseline.read_text()),
                args.source,
            ),
            indent=2,
        )
    )
