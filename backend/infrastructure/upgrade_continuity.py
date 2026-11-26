"""Preserve completed migration and maintenance ownership across compatible sources."""

import re
import subprocess

from backup_transition import source_fingerprint
from deployment_profile import fingerprint
from operator_checks import require
from release_observation import digest


def compatible(previous, current):
    """Require ancestor source and identical application, migration and schema inputs."""
    require(re.fullmatch(r"[a-f0-9]{40}", previous or ""), "Exact previous source required")
    original = source_fingerprint(previous)
    require(original == source_fingerprint(current), "Completed migration inputs changed")
    require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", previous, current],
            capture_output=True,
            check=False,
        ).returncode
        == 0,
        "Completed migration source is not an ancestor",
    )
    return original


def evidence(upgrade, source, profile):
    """Bind an authenticated upgrade receipt to its original maintenance marker."""
    previous = upgrade["result"]["source_sha"]
    inputs = compatible(previous, source) if previous != source else None
    maintenance = upgrade.get("readiness", {}).get("maintenance_identity")
    if maintenance is None:
        require(previous == source, "Original maintenance identity required for continuation")
        return None
    target = fingerprint(profile)
    require(
        maintenance.get("profile_sha256") == target
        and re.fullmatch(r"[a-f0-9]{32}", maintenance.get("operation_id", ""))
        and re.fullmatch(r"[a-f0-9]{40}", maintenance.get("source_sha", ""))
        and re.fullmatch(r"[a-f0-9]{64}", maintenance.get("review_sha256", "")),
        "Original maintenance identity differs",
    )
    if maintenance["source_sha"] != previous:
        transition = upgrade.get("backup_transition", {})
        retained = compatible(maintenance["source_sha"], previous)
        require(
            transition.get("from_source") == maintenance["source_sha"]
            and transition.get("to_source") == previous
            and transition.get("inputs_sha256") == retained
            and re.fullmatch(r"[a-f0-9]{64}", transition.get("maintenance_sha256", ""))
            and re.fullmatch(r"[a-f0-9]{64}", transition.get("baseline_catalog_sha256", "")),
            "Original backup continuation differs",
        )
    return {
        "upgrade_source": previous,
        "source_sha": source,
        "profile_sha256": target,
        "upgrade_receipt_sha256": digest(upgrade),
        "inputs_sha256": inputs,
        "maintenance_marker": ":".join(
            (maintenance["operation_id"], maintenance["source_sha"], target)
        ),
    }


def bind_marker(review, collected):
    """Require authenticated upgrade evidence for a marker from a previous source."""
    marker = review["maintenance_marker"]
    parts = marker.split(":")
    require(len(parts) == 3, "Invalid maintenance marker")
    proof = collected.get("upgrade_continuity")
    if parts[1] != review["source_sha"] or proof is not None:
        require(
            isinstance(proof, dict)
            and proof.get("maintenance_marker") == marker
            and proof.get("source_sha") == review["source_sha"]
            and proof.get("profile_sha256") == review["profile_sha256"]
            and collected.get("schema_action") == "upgrade",
            "Original maintenance marker requires authenticated upgrade continuity",
        )
