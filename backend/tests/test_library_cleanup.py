"""Durable cleanup tests advance only the worker clock; storage and DB remain real."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app import library_cleanup
from app.api import exercise_library
from app.auth.errors import AuthError
from app.models.media import LibrarySaveIntent, MediaAsset, MediaDeletion
from tests.test_exercise_library_api import attach_store, commit, media_input, reserve, upload
from tests.test_media_storage import PNG
from tests.test_staff_api import api as api

pytestmark = pytest.mark.database


def prepared(api, media_store, domain_db):
    store = attach_store(api, media_store)
    key, response = reserve(api, upload=media_input())
    assert response.status_code == 200
    upload(api, key)
    with domain_db.transaction() as session:
        row = session.scalar(select(LibrarySaveIntent))
        return (
            store,
            row.upload_until,
            exercise_library.evidence(session.get(MediaAsset, row.upload_id)),
            key,
        )


def test_abandoned_upload_is_not_deleted_before_signed_deadline(
    api, media_store, domain_db, monkeypatch
):
    store, deadline, item, key = prepared(api, media_store, domain_db)
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline - timedelta(seconds=1))
    assert library_cleanup.run_once(domain_db, store, item.bucket) is False
    assert store.verified_bytes(item) == PNG
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(seconds=1))
    assert library_cleanup.run_once(domain_db, store, item.bucket) is True
    assert store.head(item) is None
    assert commit(api, key).status_code == 409
    with domain_db.transaction() as session:
        assert session.scalar(select(LibrarySaveIntent)).state == "expired"
        assert session.scalar(select(MediaAsset)).status == "deleted"
        row = session.scalar(select(MediaDeletion))
        assert row.status == "done" and row.attempts == 1


def test_live_media_survives_cleanup_and_foreign_bucket_is_untouched(
    api, media_store, domain_db, monkeypatch
):
    store, deadline, item, key = prepared(api, media_store, domain_db)
    assert library_cleanup.expire_uploads(domain_db, "different-test-bucket") == 0
    assert commit(api, key).status_code == 200
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(days=1))
    assert library_cleanup.run_once(domain_db, store, item.bucket) is False
    assert store.verified_bytes(item) == PNG


def test_lost_delete_response_retains_work_and_reconciles_same_key(
    api, media_store, domain_db, monkeypatch
):
    store, deadline, item, _ = prepared(api, media_store, domain_db)
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(seconds=1))
    actual_delete = store.delete

    def lost_response(evidence):
        actual_delete(evidence)
        raise AuthError("MEDIA_UNAVAILABLE", "Injected response loss", 503)

    monkeypatch.setattr(store, "delete", lost_response)
    with pytest.raises(AuthError):
        library_cleanup.run_once(domain_db, store, item.bucket)
    assert store.head(item) is None
    with domain_db.transaction() as session:
        row = session.scalar(select(MediaDeletion))
        assert row.status == "pending" and row.attempts == 1
    assert library_cleanup.run_once(domain_db, store, item.bucket) is False
    monkeypatch.setattr(store, "delete", actual_delete)
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(minutes=2))
    assert library_cleanup.run_once(domain_db, store, item.bucket) is True
    with domain_db.transaction() as session:
        row = session.scalar(select(MediaDeletion))
        assert row.status == "done" and row.attempts == 2


def test_dead_worker_lease_can_be_reclaimed_but_old_worker_cannot_finish(
    api, media_store, domain_db, monkeypatch
):
    store, deadline, item, _ = prepared(api, media_store, domain_db)
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(seconds=1))
    assert library_cleanup.expire_uploads(domain_db, item.bucket) == 1
    old = library_cleanup.claim(domain_db, item.bucket)
    assert old is not None
    assert library_cleanup.claim(domain_db, item.bucket) is None
    monkeypatch.setattr(library_cleanup, "clock", lambda _: deadline + timedelta(minutes=3))
    new = library_cleanup.claim(domain_db, item.bucket)
    assert new[0] == old[0] and new[1] > old[1]
    assert library_cleanup.finish(domain_db, old[0], old[1], True) is False
    store.delete(new[2])
    assert library_cleanup.finish(domain_db, new[0], new[1], True) is True
