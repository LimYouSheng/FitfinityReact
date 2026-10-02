"""Portable validation plus real PostgreSQL integrity/atomicity regression tests."""

import hashlib
import math
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.people import Client
from app.persistence import PersistenceConflict, require_transaction, reviewed, signature_evidence


@pytest.mark.parametrize(
    "strokes",
    [
        None,
        [],
        [[]],
        [[{"x": 0, "y": 0}]],
        [[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}]],
        [[{"x": 0, "y": 0}, {"x": 25, "y": 0}, {"x": math.nan, "y": 5}]],
        [[{"x": 0, "y": 0}, {"x": 25, "y": 0}, {"x": 601, "y": 5}]],
        [[{"x": True, "y": 0}, {"x": 25, "y": 0}, {"x": 35, "y": 5}]],
        [[{"x": 0, "y": 0}]] * 101,
        [[{"x": index % 600, "y": 10} for index in range(10001)]],
        [[{"x": 10**400, "y": 0}, {"x": 25, "y": 0}, {"x": 35, "y": 5}]],
    ],
)
def test_signature_rejects_invalid_or_oversized_evidence(strokes):
    with pytest.raises(ValueError):
        signature_evidence(strokes)


def test_signature_encoding_keeps_drawn_evidence_and_stable_digest():
    drawn = [[{"x": 1, "y": 2}, {"x": 20, "y": 5}, {"x": 40, "y": 30}]]
    payload, digest = signature_evidence(drawn)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert payload == b'[[{"x":1,"y":2},{"x":20,"y":5},{"x":40,"y":30}]]'


def test_persistence_rejects_implicit_transaction_and_missing_review():
    with Session() as session:
        with pytest.raises(RuntimeError, match="explicit"):
            require_transaction(session)
        with session.begin():
            require_transaction(session)
            with pytest.raises(PersistenceConflict, match="positive"):
                reviewed(session, Client, uuid4(), 0)
            with pytest.raises(PersistenceConflict, match="positive"):
                reviewed(session, Client, uuid4(), True)
