"""Synthetic SES and real PostgreSQL evidence; never deliver mail to a real recipient."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.email_delivery import dispatch_one, enqueue
from app.email_dispatch import signing_key, verify_request
from app.email_provider import DeliveryFailure, SesEmail
from app.email_templates import render
from app.models.email_delivery import EmailDelivery


def queued(db):
    with db.transaction() as session:
        session.info["transactional_email_enabled"] = True
        return enqueue(
            session,
            "welcome:one",
            "client_welcome",
            "one@example.test",
            {"name": "One", "trainer": "Trainer"},
        )


@pytest.mark.database
def test_intent_is_atomic_deduplicated_and_immutable(domain_db):
    first = queued(domain_db)
    assert queued(domain_db) == first
    with pytest.raises(DBAPIError), domain_db.transaction() as session:
        session.get(EmailDelivery, first).recipient = "redirected@example.test"
    with pytest.raises(ValueError), domain_db.transaction() as session:
        session.info["transactional_email_enabled"] = True
        enqueue(
            session,
            "welcome:rollback",
            "client_welcome",
            "two@example.test",
            {"name": "Two", "trainer": "Trainer"},
        )
        raise ValueError("business write failed")
    with domain_db.transaction() as session:
        assert len(session.scalars(select(EmailDelivery)).all()) == 1
        assert session.get(EmailDelivery, first).state == "pending"


@pytest.mark.database
def test_disabled_capture_does_not_queue_old_events(domain_db):
    with domain_db.transaction() as session:
        assert (
            enqueue(
                session,
                "disabled",
                "client_welcome",
                "one@example.test",
                {"name": "One", "trainer": "T"},
            )
            is None
        )
        assert session.scalar(select(EmailDelivery)) is None


@pytest.mark.database
def test_provider_acceptance_is_saved_once_and_not_delivery(domain_db):
    identity = queued(domain_db)

    class Provider:
        calls = 0

        def send(self, recipient, content, delivery_id):
            self.calls += 1
            assert delivery_id == identity and recipient == "one@example.test"
            return "ses-accepted-id"

    provider = Provider()
    assert dispatch_one(domain_db, provider)["state"] == "accepted"
    assert dispatch_one(domain_db, provider) is None
    assert provider.calls == 1
    with domain_db.transaction() as session:
        row = session.get(EmailDelivery, identity)
        assert row.provider_id == "ses-accepted-id"
        assert row.attempts == 1


@pytest.mark.database
def test_uncertain_send_and_expired_lease_are_never_resent(domain_db):
    identity = queued(domain_db)

    class Provider:
        calls = 0

        def send(self, *args):
            self.calls += 1
            raise DeliveryFailure("unknown", "transport")

    provider = Provider()
    assert dispatch_one(domain_db, provider)["state"] == "unknown"
    assert dispatch_one(domain_db, provider) is None
    assert provider.calls == 1
    with domain_db.transaction() as session:
        row = session.get(EmailDelivery, identity)
        row.state, row.lease_id = "sending", uuid4()
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert dispatch_one(domain_db, provider) is None
    assert provider.calls == 1


@pytest.mark.database
def test_explicit_throttling_retries_boundedly(domain_db):
    identity = queued(domain_db)

    class Provider:
        def send(self, *args):
            raise DeliveryFailure("retry", "ses_throttled")

    now = datetime.now(UTC)
    for attempt in range(5):
        result = dispatch_one(domain_db, Provider(), now=now + timedelta(hours=attempt))
        assert result["state"] == ("failed" if attempt == 4 else "pending")
    assert dispatch_one(domain_db, Provider(), now=now + timedelta(days=1)) is None
    with domain_db.transaction() as session:
        assert session.get(EmailDelivery, identity).attempts == 5


def test_plain_templates_exclude_private_fields_and_credentials():
    value = render(
        "client_welcome",
        {"name": "One", "trainer": "T", "health_notes": "PRIVATE", "password": "SECRET"},
    )
    assert "No app login is needed" in value.text
    assert "PRIVATE" not in value.text and "SECRET" not in value.text
    credit = render(
        "session_complete",
        {
            "name": "One",
            "package": "12 sessions",
            "used": 1,
            "total": 12,
            "start": "2026-11-28",
            "end": "2027-02-25",
        },
    )
    assert "Sessions remaining: 11" in credit.text and "2027-02-25" in credit.text
    with pytest.raises(ValueError):
        render("unknown", {"name": "One"})


def test_ses_uses_one_recipient_and_truthful_error_categories():
    class Client:
        failure = None

        def send_email(self, **request):
            assert request["Destination"] == {"ToAddresses": ["one@example.test"]}
            assert request["Content"]["Simple"]["Body"]["Text"]["Charset"] == "UTF-8"
            if self.failure:
                raise self.failure
            return {"MessageId": "accepted"}

    client = Client()
    provider = SesEmail("ap-southeast-1", "sender@example.test", client=client)
    content = render("trainer_termination", {"name": "One"})
    assert provider.send("one@example.test", content, uuid4()) == "accepted"
    client.failure = ReadTimeoutError(endpoint_url="https://example.test")
    with pytest.raises(DeliveryFailure) as caught:
        provider.send("one@example.test", content, uuid4())
    assert caught.value.state == "unknown"
    client.failure = ClientError(
        {"Error": {"Code": "MessageRejected"}, "ResponseMetadata": {"HTTPStatusCode": 400}},
        "SendEmail",
    )
    with pytest.raises(DeliveryFailure) as caught:
        provider.send("one@example.test", content, uuid4())
    assert caught.value.state == "failed"


def test_dispatch_signature_rejects_wrong_key_body_expiry_and_purpose(monkeypatch):
    key = b"k" * 32
    client = Mock()
    client.get_secret_value.return_value = {"SecretString": json.dumps({"dispatch_key": key.hex()})}
    monkeypatch.setattr("app.email_dispatch.boto3.client", lambda *args, **kwargs: client)
    settings = SimpleNamespace(aws_region="ap-southeast-1", email_dispatch_secret_arn="test-secret")
    assert signing_key(settings) == key
    client.get_secret_value.assert_called_once_with(
        SecretId="test-secret", VersionStage="AWSCURRENT"
    )
    client.close.assert_called_once_with()
    body = json.dumps({"at": 1000, "id": str(uuid4())}).encode()
    signature = hmac.new(key, b"fitfinity.email.dispatch.v1\n" + body, hashlib.sha256).hexdigest()
    assert verify_request(body, signature, key, now=1000)
    assert not verify_request(body, signature, b"x" * 32, now=1000)
    assert not verify_request(body + b" ", signature, key, now=1000)
    assert not verify_request(body, signature, key, now=1061)
    assert not verify_request(body, "0" * 64, key, now=1000)
