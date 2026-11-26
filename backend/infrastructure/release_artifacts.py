"""Collect authenticated workflow artifacts before acquiring rollout credentials."""

import json
import re
import time

from hosting_frontend import source_check
from operator_checks import require
from release_evidence import validate
from release_observation import digest
from schema_probe_artifacts import fetch


def collect(repo, destination, runs, *, source, profile, database, schema_action, clock=time.time):
    """Bind successful manual-main producers to the clean checkout and inspect their contents."""
    runs = dict(runs)
    upgrade_source = runs.pop("upgrade_source", source)
    require(
        isinstance(upgrade_source, str) and re.fullmatch(r"[a-f0-9]{40}", upgrade_source),
        "Exact upgrade producer source required",
    )
    require(
        upgrade_source == source or schema_action == "upgrade", "Upgrade source without upgrade"
    )
    fresh_run = None
    if "fresh_catalog" in runs:
        fresh_run = runs.pop("fresh_catalog")
        require(
            isinstance(fresh_run, str) and re.fullmatch(r"[1-9][0-9]*", fresh_run),
            "Exact catalog confirmation run required",
        )
    expected = {"frontend", "image", "catalog"}
    require(schema_action in {"unchanged", "upgrade"}, "Explicit schema action required")
    if schema_action == "upgrade":
        expected.add("upgrade")
    require(
        set(runs) == expected
        and all(
            isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value)
            for value in runs.values()
        ),
        "Exact producer run IDs required",
    )
    require(
        not destination.exists()
        and not destination.is_symlink()
        and destination.absolute() == destination.resolve()
        and not destination.resolve().is_relative_to(repo.resolve()),
        "Use a new artifact directory outside the checkout",
    )
    verified_source = source_check(repo, source)
    destination.mkdir(parents=True, mode=0o700)
    for kind in sorted(expected):
        fetch(
            "review" if kind == "frontend" else kind,
            runs[kind],
            destination / kind,
            upgrade_source if kind == "upgrade" else source,
            profile=profile,
        )
    if fresh_run:
        fetch("catalog", fresh_run, destination / "fresh_catalog", source, profile=profile)
    require(source_check(repo, source) == verified_source, "Checkout changed during retrieval")

    def read(name):
        path = destination / name
        require(path.is_file() and not path.is_symlink(), "Missing or redirected artifact receipt")
        return json.loads(path.read_text())

    require(
        not any(path.is_symlink() for path in destination.rglob("*")),
        "Redirected downloaded artifact refused",
    )
    frontend = read("frontend/release-readiness.json")
    image = read("image/fitfinity-image-candidate.json")
    probe = read("catalog/schema-probe-receipt.json")
    upgrade = read("upgrade/schema-upgrade-receipt.json") if schema_action == "upgrade" else None
    fresh_probe = read("fresh_catalog/schema-probe-receipt.json") if fresh_run else None
    result = validate(
        frontend,
        destination / "frontend/release-frontend/dist-api-test",
        image,
        upgrade,
        probe,
        repo=repo,
        source_inventory=verified_source,
        profile=profile,
        database=database,
        schema_action=schema_action,
        now=clock(),
        fresh_probe=fresh_probe,
        upgrade_source=upgrade_source,
    )
    result["producer_runs"] = dict(runs)
    if fresh_run:
        confirmation = {
            "run": fresh_run,
            "observed_at": fresh_probe["receipt"]["catalog"]["observed_at"],
            "evidence_sha256": digest(result),
        }
        (destination / "catalog-confirmation.json").write_text(json.dumps(confirmation) + "\n")
    return result
