"""Bind an unchanged release to its original owned pre-upgrade backup."""

import hashlib
import re
import subprocess

from operator_checks import require
from release_observation import digest


def source_fingerprint(source):
    """Hash every tracked input except explicit documentation and orchestration owners."""
    require(re.fullmatch(r"[a-f0-9]{40}", source or ""), "Exact transition source required")
    rows = subprocess.check_output(["git", "ls-tree", "-rz", "--full-tree", source]).split(b"\0")
    retained = []
    for row in rows:
        if not row:
            continue
        path = row.split(b"\t", 1)[1].decode()
        excluded = (
            path.startswith(("docs/", ".agents/", ".github/workflows/"))
            or path in {"AGENTS.md", "NORTH_STAR.md", "PROGRESS.md"}
            or path
            in {
                "backend/scripts/verify-infrastructure.py",
                "scripts/verify-infrastructure.mjs",
                "scripts/verify-ci-groups.mjs",
                "scripts/verify-quality.mjs",
                "scripts/verify-quality.test.mjs",
            }
            or (path.startswith("backend/infrastructure/") and path.endswith(".py"))
        )
        if not excluded:
            retained.append(row)
    require(retained, "Transition input inventory is empty")
    return hashlib.sha256(b"\0".join(sorted(retained))).hexdigest()


def prepare_transition(maintenance, baseline, source):
    """Retain original backup identity and prove ancestor release inputs are unchanged."""
    previous = maintenance.get("identity", {}).get("source_sha")
    require(previous != source, "A transition requires distinct release sources")
    original = source_fingerprint(previous)
    current = source_fingerprint(source)
    require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", previous, source],
            capture_output=True,
            check=False,
        ).returncode
        == 0
        and original == current,
        "Backup transition requires ancestor source and unchanged application/migration inputs",
    )
    require(
        re.fullmatch(r"[a-f0-9]{64}", maintenance.get("runtime_sha256", "")),
        "Original paused runtime fingerprint required",
    )
    return {
        "from_source": previous,
        "to_source": source,
        "inputs_sha256": current,
        "maintenance_sha256": digest(maintenance),
        "baseline_catalog_sha256": digest(baseline),
    }
