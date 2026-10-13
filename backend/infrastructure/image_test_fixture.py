"""Temporary image bytes and contracts for offline runtime tests only."""

import copy
import hashlib
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def image_fixture(source, pinned_contract):
    """Snapshot test inputs once; never rewrite the historical deployment contract.

    A current checkout is not the previously published image. Tests exercise the
    canonical loader/runtime against this separate, immutable-at-capture manifest.
    Later file changes must still fail the runtime's real SHA-256 comparisons.
    """
    contract = copy.deepcopy(pinned_contract)
    # Explicit candidate-only schema extension. Never update the deployed contract;
    # its six-revision/table binding must reject this sixteen-revision image.
    assert contract["revisions"][-1] == "20260924_0006"
    revision = "20261013_0007"
    migration = "migrations/versions/20261013_0007_package_saves.py"
    contract["files"][migration] = hashlib.sha256((source / migration).read_bytes()).hexdigest()
    contract["files"]["app/api/packages.py"] = hashlib.sha256(
        (source / "app/api/packages.py").read_bytes()
    ).hexdigest()
    contract["revisions"] = [*contract["revisions"], revision]
    contract["tables"]["package_save_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0008_trainer_approvals.py",
        "app/api/trainer_approvals.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0008")
    contract["tables"]["trainer_approval_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0009_client_details.py",
        "app/api/client_details.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0009")
    contract["tables"]["client_detail_receipts"] = ["SELECT", "INSERT"]
    migration = "migrations/versions/20261013_0010_optional_contacts.py"
    contract["files"][migration] = hashlib.sha256((source / migration).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0010")
    migration = "migrations/versions/20261013_0011_client_notes.py"
    contract["files"][migration] = hashlib.sha256((source / migration).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0011")
    contract["tables"]["client_note_receipts"] = ["SELECT", "INSERT"]
    contract["tables"]["client_note_access"] = ["SELECT", "INSERT"]
    migration = "migrations/versions/20261013_0012_trainer_rates.py"
    contract["files"][migration] = hashlib.sha256((source / migration).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0012")
    contract["tables"]["trainer_rate_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0013_verified_email.py",
        "app/api/email_changes.py",
        "app/models/email_changes.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0013")
    contract["tables"]["staff_email_changes"] = ["SELECT", "INSERT", "UPDATE"]
    for relative in (
        "migrations/versions/20261013_0014_trainer_details.py",
        "app/api/trainer_details.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0014")
    contract["tables"]["trainer_detail_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0015_client_creation.py",
        "app/api/client_creation.py",
        "app/api/client_matching.py",
        "app/purchase_schedule.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0015")
    contract["tables"]["client_create_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0016_trainer_reactivation.py",
        "app/api/trainer_reactivation.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0016")
    contract["tables"]["trainer_reactivation_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0017_content_saves.py",
        "app/api/content.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0017")
    contract["tables"]["content_save_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0018_message_reads.py",
        "app/api/messages.py",
        "app/api/message_schemas.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0018")
    contract["tables"]["message_read_receipts"] = ["SELECT", "INSERT"]
    with TemporaryDirectory(prefix="fitfinity-offline-image-") as directory:
        root = Path(directory)
        files = set(contract["files"]) | {"app/certificates/ap-southeast-1-bundle.pem"}
        for relative in sorted(files):
            data = (source / relative).read_bytes()
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            if relative in contract["files"]:
                contract["files"][relative] = hashlib.sha256(data).hexdigest()
        yield root, contract
