"""Approved general-note access never grants access to assessment forms."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.models.api import ClientNoteAccess, ClientNoteReceipt
from app.models.people import ClientPerson
from tests.test_staff_api import api as api
from tests.test_staff_api import trainer_login

pytestmark = pytest.mark.database


def url(graph):
    return f"/api/clients/{graph['client_id']}/notes"


def save(api, graph, patch, version=None, key=None):
    if version is None:
        version = next(
            c["version"]
            for c in api.get("/api/directory").json()["clients"]
            if c["id"] == str(graph["client_id"])
        )
    return api.post(
        url(graph),
        json={"expectedVersion": version, "patch": patch},
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_read_write_and_receipt_persist_without_copying_notes_into_evidence(api, domain_db, graph):
    with domain_db.transaction() as session:
        session.scalar(select(ClientPerson)).health_notes = "Original limitation"
    assert api.get(url(graph)).json()["healthNotes"] == "Original limitation"
    version = api.get(url(graph)).json()["version"]
    key = uuid4()
    saved = save(api, graph, {"healthNotes": "Updated limitation", "remarks": "Coaching"}, key=key)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"id": str(graph["client_id"]), "version": version + 1}
    current = api.get(url(graph)).json()
    assert current["healthNotes"] == "Updated limitation" and current["remarks"] == "Coaching"
    assert save(api, graph, {"remarks": "Later"}, version=version + 1).status_code == 200
    assert (
        save(
            api,
            graph,
            {"healthNotes": "Updated limitation", "remarks": "Coaching"},
            version=version,
            key=key,
        ).json()
        == saved.json()
    )
    assert api.get(f"/api/client-note-saves/{key}").json() == saved.json()
    assert save(api, graph, {"remarks": "Changed"}, key=key).status_code == 409
    assert save(api, graph, {"remarks": "Stale"}, version=version).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(ClientPerson)).health_notes == "Updated limitation"
        receipt = session.scalar(
            select(ClientNoteReceipt).where(ClientNoteReceipt.request_key == key)
        )
        assert receipt.result == saved.json()
        assert len(session.scalars(select(ClientNoteAccess)).all()) == 7
    assert "Updated limitation" not in api.get("/api/directory").text


def test_assigned_trainer_can_edit_general_notes_but_not_assessment_forms(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    assert api.get(url(graph)).status_code == 200
    assert save(api, graph, {"healthNotes": "General guidance"}).status_code == 200
    assert api.get("/api/assessment-forms").status_code == 403
    with domain_db.transaction() as session:
        person_id = session.scalar(select(ClientPerson.id))
    assert api.get(f"/api/people/{person_id}/assessments").status_code == 403


def test_unknown_or_historical_client_never_discloses_notes(
    api, domain_db, graph, auth_settings, auth_service, fake_cognito
):
    trainer_login(api, domain_db, graph, auth_settings, auth_service, fake_cognito)
    missing = api.get(f"/api/clients/{uuid4()}/notes")
    assert missing.status_code == 404
    # Current assignment alone is the policy; an old purchase does not grant it.
    from app.api.client_notes import record
    from app.auth.errors import AuthError
    from app.authorization import Principal

    with domain_db.transaction() as session:
        with pytest.raises(AuthError) as error:
            record(
                session,
                Principal(graph["user_id"], "Trainer", "trainer", uuid4()),
                graph["client_id"],
            )
        assert error.value.status == 404


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"healthNotes": None},
        {"remarks": None},
        {"healthNotes": 7},
        {"assessments": {}},
        {"actor": "owner"},
        {"trainerId": "forged"},
        {"healthNotes": "x" * 10001},
    ],
)
def test_note_allowlist_rejects_invalid_and_assessment_fields(api, graph, patch):
    assert save(api, graph, patch).status_code == 422


def test_clearing_notes_is_durable_and_contact_edits_do_not_restore_old_summary(api, graph):
    from tests.test_client_details import payload
    from tests.test_client_details import save as contact_save

    assert save(api, graph, {"healthNotes": ""}).status_code == 200
    assert contact_save(api, graph, payload(api, graph)).status_code == 200
    assert api.get(url(graph)).json()["healthNotes"] == ""


def test_notes_access_and_receipts_are_immutable_and_prevent_downgrade(
    api, domain_db, graph, migrate
):
    assert save(api, graph, {"remarks": "Saved"}).status_code == 200
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientNoteReceipt)))
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.delete(session.scalar(select(ClientNoteAccess)))
    with pytest.raises(DBAPIError, match="populated attribution downgrade refused"):
        migrate("downgrade", "20261013_0010")
    assert api.get(url(graph)).json()["remarks"] == "Saved"


def test_direct_note_transaction_commits_with_current_actor(domain_db, graph):
    from app.api.client_notes import SaveNotes
    from app.api.client_notes import save as save_notes
    from app.authorization import Principal
    from app.models.people import Client

    with domain_db.transaction() as session:
        saved = save_notes(
            session,
            Principal(graph["owner_id"], "Owner", "owner", None),
            graph["client_id"],
            uuid4(),
            SaveNotes(
                expectedVersion=session.get(Client, graph["client_id"]).version,
                patch={"remarks": "Direct"},
            ),
        )
        assert saved.version > 1


def test_parallel_note_retry_has_one_receipt_and_rechecks_current_assignment(api, domain_db, graph):
    from concurrent.futures import ThreadPoolExecutor

    from app.api import client_notes as commands
    from app.auth.errors import AuthError
    from app.authorization import Principal

    principal = Principal(graph["user_id"], "Trainer", "trainer", graph["trainer_id"])
    body = commands.SaveNotes(
        expectedVersion=api.get(url(graph)).json()["version"], patch={"remarks": "Concurrent"}
    )
    key = uuid4()

    def submit(_):
        with domain_db.transaction() as session:
            return commands.save(session, principal, graph["client_id"], key, body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    with domain_db.transaction() as session:
        assert len(session.scalars(select(ClientNoteReceipt)).all()) == 1
        with pytest.raises(AuthError) as denied:
            commands.reconcile(
                session, Principal(principal.user_id, "Trainer", "trainer", uuid4()), key
            )
        assert denied.value.status == 404
        with pytest.raises(AuthError) as denied:
            commands.reconcile(session, Principal(graph["owner_id"], "Owner", "owner", None), key)
        assert denied.value.status == 404


@pytest.mark.parametrize("couple", [False, True])
def test_person_note_edits_sync_summary_without_overwriting_unchanged_shared_notes(
    api, domain_db, graph, couple
):
    from app.models.people import Client
    from tests.test_client_details import payload
    from tests.test_client_details import save as save_contacts

    if couple:
        with domain_db.transaction() as session:
            first = session.scalar(select(ClientPerson))
            values = {
                c.key: getattr(first, c.key)
                for c in first.__table__.columns
                if c.key not in {"id", "created_at", "updated_at", "version"}
            }
            session.add(ClientPerson(**{**values, "position": 2, "name": "Second Client"}))
            session.get(Client, graph["client_id"]).kind = "couple"
    body = payload(api, graph)
    body["people"][0]["healthNotes"] = "Person guidance"
    assert save_contacts(api, graph, body).status_code == 200
    notes = api.get(url(graph)).json()
    assert "Person guidance" in notes["healthNotes"]
    assert save(api, graph, {"healthNotes": "Shared guidance"}).status_code == 200
    notes = api.get(url(graph)).json()
    body = payload(api, graph)
    for person, note in zip(body["people"], notes["people"], strict=True):
        person["healthNotes"] = note["healthNotes"]
    body["people"][0]["name"] = "Renamed client"
    assert save_contacts(api, graph, body).status_code == 200
    assert api.get(url(graph)).json()["healthNotes"] == "Shared guidance"
