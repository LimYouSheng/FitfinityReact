"""Actual original-byte failures and permission changes cannot partially restore recordings."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.api.exercise_library import evidence
from app.models.media import MediaAsset
from app.models.people import StaffUser
from app.models.session_mutations import SessionMutationUndo
from tests.test_session_media_api import commit, publish, reserve
from tests.test_session_media_api import recording as recording
from tests.test_session_undo_api import latest, undo, undo_review
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


@pytest.mark.parametrize("failure", ["missing_bytes", "actor_deactivated"])
def test_original_media_and_current_actor_are_required_at_compensation(
    api, graph, domain_db, recording, monkeypatch, failure
):
    store, item, _ = recording
    _, saved = publish(api, graph, item)
    key, _, response = reserve(api, graph, item, remove=True)
    assert response.status_code == 200
    assert commit(api, key).status_code == 200
    mutation = latest(domain_db)
    viewed = undo_review(api, mutation)
    asset_id = UUID(saved["media"]["id"])
    with domain_db.transaction() as session:
        checked = evidence(session.get(MediaAsset, asset_id))
    if failure == "missing_bytes":
        store.delete(checked)
    else:
        original = store.verified_bytes

        def revoke(lease):
            data = original(lease)
            with domain_db.transaction() as session:
                session.get(StaffUser, graph["owner_id"]).status = "inactive"
            return data

        monkeypatch.setattr(store, "verified_bytes", revoke)
    result = undo(api, mutation, viewed)
    assert result.status_code == (409 if failure == "missing_bytes" else 401), result.text
    with domain_db.transaction() as session:
        asset = session.get(MediaAsset, asset_id)
        assert asset.session_id is None and asset.expires_at.isoformat() == saved["media"][
            "expiresAt"
        ].replace("Z", "+00:00")
        assert session.scalar(select(func.count()).select_from(SessionMutationUndo)) == 0
