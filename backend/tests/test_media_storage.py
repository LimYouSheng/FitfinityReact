"""Exercise signatures, actual object bytes and immutable storage failure boundaries."""

import base64
import hashlib
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
import pytest
from botocore.exceptions import ClientError

from app.auth.errors import AuthError
from app.media_storage import ObjectEvidence

# A complete one-pixel PNG, not an arbitrary string with a trusted MIME label.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMwaPj/HwAFQgKv8Qz/1QAAAABJRU5ErkJggg=="
)


def evidence(bucket, data=PNG, content_type="image/png"):
    return ObjectEvidence(
        bucket, uuid4().hex, content_type, len(data), hashlib.sha256(data).hexdigest()
    )


def put(store, item, data=PNG):
    lease = store.upload(item, 60)
    with httpx2.Client(trust_env=False) as client:
        return client.put(lease["url"], headers=lease["headers"], content=data)


def test_signed_upload_and_private_read_preserve_exact_bytes(media_store):
    store, bucket = media_store
    item = evidence(bucket)
    assert store.head(item) is None
    lease = store.upload(item, 60)
    query = parse_qs(urlsplit(lease["url"]).query)
    assert set(query["X-Amz-SignedHeaders"][0].split(";")) == {
        "host",
        "content-length",
        "content-type",
        "if-none-match",
        "x-amz-checksum-sha256",
    }
    assert query["X-Amz-Expires"] == ["60"]
    assert put(store, item).status_code == 200
    assert store.verified_bytes(item) == PNG
    with httpx2.Client(trust_env=False) as client:
        result = client.get(store.download(item, 60))
        assert result.status_code == 200
        assert result.content == PNG
        assert result.headers["cache-control"] == "private, no-store"
        assert client.get(lease["url"].split("?", 1)[0]).status_code == 403
    store.delete(item)
    store.delete(item)
    assert store.head(item) is None


def test_original_upload_cannot_be_overwritten(media_store):
    store, bucket = media_store
    item = evidence(bucket)
    assert put(store, item).status_code == 200
    assert put(store, item).status_code == 412
    assert store.verified_bytes(item) == PNG


def test_browser_upload_preflight_allows_only_the_isolated_portal_origin(media_store):
    store, bucket = media_store
    url = store.upload(evidence(bucket), 60)["url"]
    with httpx2.Client(trust_env=False) as client:
        headers = {
            "Origin": "http://127.0.0.1:4180",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": (
                "content-type,if-none-match,x-amz-checksum-sha256,x-fitfinity-browser-worker"
            ),
        }
        result = client.options(url, headers=headers)
        assert result.status_code == 200, result.text
        assert result.headers.get("access-control-allow-origin") == "http://127.0.0.1:4180"
        assert "PUT" in result.headers["access-control-allow-methods"]
        foreign = client.options(url, headers={**headers, "Origin": "https://foreign.example.test"})
        assert foreign.headers.get("access-control-allow-origin") is None


@pytest.mark.parametrize("change", ["bytes", "length", "type", "condition"])
def test_signed_upload_rejects_changed_review(media_store, change):
    store, bucket = media_store
    item = evidence(bucket)
    lease = store.upload(item, 60)
    body = PNG
    if change == "bytes":
        body = b"X" * len(PNG)
    elif change == "length":
        body = PNG + b"X"
    elif change == "type":
        lease["headers"]["Content-Type"] = "text/html"
    else:
        del lease["headers"]["If-None-Match"]
    with httpx2.Client(trust_env=False) as client:
        result = client.put(lease["url"], headers=lease["headers"], content=body)
    assert result.status_code in {400, 403}
    assert store.head(item) is None


@pytest.mark.parametrize("change", ["hash", "length", "type", "active_document"])
def test_commit_independently_checks_stored_evidence(media_store, change):
    store, bucket = media_store
    body = b"<script>alert(1)</script>" if change == "active_document" else PNG
    item = evidence(bucket, body)
    # Direct SDK write represents corrupted/incorrect metadata or an untrusted producer.
    store.client.put_object(Bucket=bucket, Key=item.key, Body=body, ContentType=item.content_type)
    if change == "hash":
        item = replace(item, sha256="0" * 64)
    elif change == "length":
        item = replace(item, size=item.size + 1)
    elif change == "type":
        item = replace(item, content_type="image/jpeg")
    with pytest.raises(AuthError) as failure:
        store.verified_bytes(item)
    assert failure.value.status == 422


def test_missing_bytes_and_storage_failure_are_distinct(media_store):
    store, bucket = media_store
    item = evidence(bucket)
    with pytest.raises(AuthError) as failure:
        store.verified_bytes(item)
    assert failure.value.status == 409
    with pytest.raises(AuthError) as failure:
        store.download(item, 60)
    assert failure.value.status == 404
    # A real missing bucket is a storage configuration failure, not a missing upload.
    absent = replace(item, bucket="fitfinity-test-" + uuid4().hex)
    with pytest.raises(ClientError):
        store.client.list_objects_v2(Bucket=absent.bucket)
    with pytest.raises(AuthError) as failure:
        store.verified_bytes(absent)
    assert failure.value.status == 503
