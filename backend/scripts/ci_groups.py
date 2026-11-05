"""Collect the full inventory, then execute one complete-file domain partition."""

import json
import os
from pathlib import Path

EXPECTED = 1431
GROUPS = json.loads(Path(__file__).with_name("test-groups.json").read_text())


def partition(inventory, group, files):
    """Reject stale ownership, duplicate identities and incomplete discovery."""
    assigned = [name for names in GROUPS.values() for name in names]
    if len(set(assigned)) != len(assigned) or set(assigned) != set(files):
        raise ValueError("Every backend test file must have exactly one group")
    if group not in GROUPS or len(inventory) != EXPECTED or len(set(inventory)) != EXPECTED:
        raise ValueError("Invalid group or incomplete backend inventory")
    if {node.split("::")[0] for node in inventory} != set(files):
        raise ValueError("Collected files differ from assigned files")
    return [node for node in inventory if node.split("::")[0] in GROUPS[group]]


def pytest_collection_modifyitems(session, config, items):
    inventory = [item.nodeid for item in items]
    group = os.environ["FITFINITY_TEST_GROUP"]
    selected = set(partition(inventory, group, [str(p) for p in Path("tests").glob("test_*.py")]))
    session.ci_receipt = {
        "group": group,
        "identity": {
            key: os.environ.get(key)
            for key in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
        },
        "inventory": inventory,
        "selected": sorted(selected),
        "reports": [],
    }
    retained = [item for item in items if item.nodeid in selected]
    config.hook.pytest_deselected(items=[item for item in items if item.nodeid not in selected])
    items[:] = retained


def pytest_runtest_logreport(report):
    # A receipt includes setup/call/teardown: teardown errors cannot become green.
    REPORTS.append({"id": report.nodeid, "phase": report.when, "outcome": report.outcome})


REPORTS = []


def pytest_sessionfinish(session, exitstatus):
    receipt = getattr(session, "ci_receipt", {})
    receipt.update(exitstatus=int(exitstatus), reports=REPORTS)
    # Docker tmpfs disappears at exit. Persist through container logs before cleanup.
    print("\nFITFINITY_BACKEND_RECEIPT=" + json.dumps(receipt), flush=True)
