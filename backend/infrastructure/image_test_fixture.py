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
    # its six-revision/table binding must reject the current candidate image.
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
    for relative in (
        "migrations/versions/20261013_0019_renewal_dismissal.py",
        "app/api/renewal_dismissal.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0019")
    contract["tables"]["renewal_dismissals"] = ["SELECT", "INSERT"]
    contract["tables"]["renewal_dismissal_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0020_client_deactivation.py",
        "app/api/client_deactivation.py",
        "app/api/client_reactivation.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0020")
    contract["tables"]["client_deactivation_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0021_client_reactivation.py",
        "app/api/client_reactivation_save.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0021")
    contract["tables"]["client_reactivation_receipts"] = ["SELECT", "INSERT"]
    relative = "migrations/versions/20261013_0022_open_sessions.py"
    contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0022")
    for relative in (
        "migrations/versions/20261013_0023_request_cancellation.py",
        "app/api/request_cancellation.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0023")
    contract["tables"]["request_cancellation_receipts"] = ["SELECT", "INSERT"]
    relative = "migrations/versions/20261013_0024_postponement_requests.py"
    contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0024")
    for relative in (
        "migrations/versions/20261013_0025_trainer_availability.py",
        "app/api/trainer_availability.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0025")
    contract["tables"]["trainer_availability_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0026_client_renewal.py",
        "app/api/client_renewal.py",
        "app/api/client_renewal_save.py",
        "app/api/purchase_creation.py",
        "app/api/purchase_activation.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0026")
    contract["tables"]["client_renewal_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0027_package_reactivation.py",
        "app/api/package_reactivation_save.py",
        "app/api/staff_provisioning.py",
        "app/api/trainer_creation.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0027")
    contract["tables"]["package_reactivation_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0028_client_assignment.py",
        "app/api/client_assignment.py",
        "app/api/client_assignment_save.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0028")
    contract["tables"]["client_assignment_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0029_trainer_deactivation.py",
        "app/api/trainer_deactivation.py",
        "app/api/trainer_deactivation_save.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0029")
    contract["tables"]["trainer_deactivation_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261013_0030_client_weekly_schedule.py",
        "app/api/client_weekly_schedule.py",
        "app/api/client_weekly_schedule_save.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261013_0030")
    contract["tables"]["client_weekly_schedule_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261023_0031_session_numbering.py",
        "app/session_numbering.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0031")
    for relative in (
        "migrations/versions/20261023_0032_session_bookings.py",
        "app/api/session_booking_review.py",
        "app/api/session_booking_save.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0032")
    contract["tables"]["session_booking_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261023_0033_session_postponements.py",
        "app/api/session_postponement.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0033")
    contract["tables"]["session_postponement_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261023_0034_request_resolution.py",
        "app/api/request_resolution.py",
        "app/api/request_application.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0034")
    contract["tables"]["request_resolution_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261023_0035_session_changes.py",
        "app/api/session_changes.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0035")
    contract["tables"]["session_change_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261023_0036_session_plans.py",
        "app/api/session_plans.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0036")
    contract["tables"]["session_plan_receipts"] = ["SELECT", "INSERT"]
    contract["tables"]["exercise_plan_details"] = ["SELECT", "INSERT", "UPDATE", "DELETE"]
    for relative in ("app/api/session_reads.py", "app/api/session_read_schemas.py"):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    for relative in (
        "migrations/versions/20261023_0037_session_outcomes.py",
        "app/api/session_outcomes.py",
        "app/api/session_progress.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261023_0037")
    contract["tables"]["session_outcome_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261024_0038_session_summaries.py",
        "app/api/session_summaries.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0038")
    contract["tables"]["session_summary_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261024_0039_session_acknowledgements.py",
        "app/api/session_acknowledgements.py",
        "app/api/session_reports.py",
        "app/api/remuneration.py",
        "app/api/remuneration_schemas.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0039")
    contract["tables"]["session_acknowledgement_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261024_0040_session_handoffs.py",
        "app/api/session_handoffs.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0040")
    contract["tables"]["session_handoff_receipts"] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261024_0041_library_intents.py",
        "app/api/exercise_library.py",
        "app/api/library_schemas.py",
        "app/api/library_routes.py",
        "app/media_storage.py",
        "app/library_cleanup.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0041")
    contract["tables"]["library_save_intents"] = ["SELECT", "INSERT", "UPDATE"]
    migration = "migrations/versions/20261024_0042_email_corrections.py"
    contract["files"][migration] = hashlib.sha256((source / migration).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0042")
    for relative in (
        "migrations/versions/20261024_0043_package_archives.py",
        "app/api/package_action_review.py",
        "app/api/package_action_save.py",
        "app/api/package_action_undo.py",
        "app/api/package_action_routes.py",
        "app/api/package_action_schemas.py",
        "app/models/package_actions.py",
        "app/session_media_cleanup.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0043")
    for table in (
        "package_archived_media",
        "package_action_requests",
        "session_identities",
        "session_archives",
        "package_action_receipts",
        "package_deletion_undos",
    ):
        contract["tables"][table] = ["SELECT", "INSERT"]
    for relative in (
        "migrations/versions/20261024_0044_session_recordings.py",
        "app/api/session_media.py",
        "app/api/session_media_routes.py",
        "app/api/session_media_schemas.py",
        "app/models/session_media.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0044")
    contract["tables"]["session_media_intents"] = ["SELECT", "INSERT", "UPDATE"]
    for relative in (
        "migrations/versions/20261024_0045_session_undo.py",
        "app/models/session_mutations.py",
        "app/api/session_mutation_journal.py",
        "app/api/session_undo_review.py",
        "app/api/session_undo_save.py",
        "app/api/session_undo_routes.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["revisions"].append("20261024_0045")
    for table in (
        "session_mutations",
        "session_mutation_undos",
        "mutation_scopes",
        "mutation_training_sessions",
        "mutation_clients",
        "mutation_package_purchases",
        "mutation_purchase_schedule_slots",
        "mutation_trainers",
        "mutation_staff_users",
        "mutation_exercise_plan_items",
        "mutation_exercise_plan_details",
        "mutation_exercise_results",
        "mutation_media_assets",
        "mutation_change_requests",
    ):
        contract["tables"][table] = ["SELECT", "INSERT"]
    contract["revisions"].append("20261025_0046")
    for relative in (
        "migrations/versions/20261025_0046_session_attribution.py",
        "app/models/session_attribution.py",
        "app/api/session_attribution.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    contract["tables"]["session_trainer_attributions"] = ["SELECT", "INSERT", "UPDATE"]
    contract["tables"]["session_trainer_assignment_history"] = ["SELECT", "INSERT"]
    # Candidate-only Admin/independent-purchase extension; deployed bindings remain pinned.
    contract["revisions"].extend(
        [
            "20261031_0047",
            "20261031_0048",
            "20261031_0049",
            "20261031_0050",
            "20261031_0051",
            "20261101_0052",
        ]
    )
    for relative in (
        "migrations/versions/20261031_0047_concurrent_purchases.py",
        "migrations/versions/20261031_0048_admin_management.py",
        "migrations/versions/20261031_0049_no_report_approval.py",
        "migrations/versions/20261031_0050_concurrent_purchase_guard.py",
        "migrations/versions/20261031_0051_admin_requests.py",
        "migrations/versions/20261101_0052_share_approval_policy.py",
        "app/api/admin_management.py",
        "app/api/admin_requests.py",
        "app/api/admin_review.py",
        "app/api/admin_supervision.py",
        "app/api/library_approval.py",
        "app/api/renewal_policy.py",
        "app/api/report_sharing.py",
        "app/api/session_undo_approval.py",
        "app/models/admin_management.py",
        "app/models/admin_requests.py",
    ):
        contract["files"][relative] = hashlib.sha256((source / relative).read_bytes()).hexdigest()
    for table in ("admin_approval_requirements", "admin_operation_requests"):
        contract["tables"][table] = ["SELECT", "INSERT", "UPDATE"]
    for table in ("admin_management_receipts", "admin_operation_decisions"):
        contract["tables"][table] = ["SELECT", "INSERT"]
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
