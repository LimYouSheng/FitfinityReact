"""Private immutable object IO; callers own database authority and transaction boundaries."""

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.auth.errors import AuthError

MAX_LIBRARY_BYTES = 50 * 1024 * 1024
MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm", "video/quicktime"}
)


def configured_storage(settings):
    """Production uses the workload identity and AWS endpoint; test endpoints are injected."""
    if not settings.media_enabled:
        return None
    return MediaStorage(
        boto3.client(
            "s3",
            region_name="ap-southeast-1",
            config=Config(signature_version="s3v4", retries={"total_max_attempts": 1}),
        )
    )


def unavailable():
    return AuthError(
        "MEDIA_UNAVAILABLE",
        "Media storage is unavailable. Check the original save before retrying.",
        503,
    )


def invalid():
    return AuthError(
        "MEDIA_INVALID", "The stored attachment does not match the reviewed file.", 422
    )


@dataclass(frozen=True)
class ObjectEvidence:
    bucket: str
    key: str
    content_type: str
    size: int
    sha256: str

    @property
    def checksum(self):
        return base64.b64encode(bytes.fromhex(self.sha256)).decode("ascii")


def media_header(data, content_type):
    """Reject active documents and mislabeled payloads before making immutable media visible."""
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33 and data[12:16] == b"IHDR"
    if content_type == "image/webp":
        return len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type in {"video/mp4", "video/quicktime"}:
        return len(data) >= 16 and data[4:8] == b"ftyp"
    if content_type == "video/webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    return False


class MediaStorage:
    """No bucket creation, public ACLs, automatic mutation retries or application-local storage."""

    def __init__(self, client, signing_client=None):
        self.client = client
        self.signing_client = signing_client or client

    def close(self):
        self.client.close()
        if self.signing_client is not self.client:
            self.signing_client.close()

    def upload(self, evidence, lifetime, *, deadline=None):
        """Bind a short-lived conditional upload to reviewed length, type and exact checksum."""
        if (
            not 1 <= lifetime <= 300
            or not 0 < evidence.size <= MAX_LIBRARY_BYTES
            or evidence.content_type not in MEDIA_TYPES
        ):
            raise invalid()
        try:
            url = self.signing_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": evidence.bucket,
                    "Key": evidence.key,
                    "ContentType": evidence.content_type,
                    "ContentLength": evidence.size,
                    "ChecksumSHA256": evidence.checksum,
                    "IfNoneMatch": "*",
                },
                ExpiresIn=lifetime,
            )
        except (BotoCoreError, ClientError):
            raise unavailable() from None
        if deadline is not None:
            # Validate the actual signed timestamp, even if signing paused after DB review.
            query = parse_qs(urlsplit(url).query)
            signed = datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            expires = signed + timedelta(seconds=int(query["X-Amz-Expires"][0]))
            if expires > deadline:
                raise AuthError(
                    "upload_expired", "The upload window expired. Review a new save.", 409
                )
        # The browser derives Content-Length from its Blob; script cannot set that header.
        return {
            "url": url,
            "headers": {
                "Content-Type": evidence.content_type,
                "x-amz-checksum-sha256": evidence.checksum,
                "If-None-Match": "*",
            },
        }

    def head(self, evidence):
        """Distinguish a missing original upload from an ambiguous storage failure."""
        try:
            value = self.client.head_object(Bucket=evidence.bucket, Key=evidence.key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise unavailable() from None
        except BotoCoreError:
            raise unavailable() from None
        if (
            value.get("ContentLength") != evidence.size
            or value.get("ContentType") != evidence.content_type
        ):
            raise invalid()
        return value

    def verified_bytes(self, evidence):
        """Bound reads and independently verify uploaded bytes before DB commit."""
        if not 0 < evidence.size <= MAX_LIBRARY_BYTES or evidence.content_type not in MEDIA_TYPES:
            raise invalid()
        stream = None
        try:
            value = self.client.get_object(Bucket=evidence.bucket, Key=evidence.key)
            stream = value["Body"]
            if (
                value.get("ContentLength") != evidence.size
                or value.get("ContentType") != evidence.content_type
            ):
                raise invalid()
            data, digest = bytearray(), hashlib.sha256()
            while chunk := stream.read(min(65536, evidence.size - len(data) + 1)):
                if len(data) + len(chunk) > evidence.size:
                    raise invalid()
                data.extend(chunk)
                digest.update(chunk)
            if (
                len(data) != evidence.size
                or digest.hexdigest() != evidence.sha256
                or not media_header(data, evidence.content_type)
            ):
                raise invalid()
            return bytes(data)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                raise AuthError(
                    "MEDIA_MISSING", "The original upload is not stored yet.", 409
                ) from None
            raise unavailable() from None
        except BotoCoreError:
            raise unavailable() from None
        finally:
            if stream is not None:
                stream.close()

    def download(self, evidence, lifetime):
        """Issue a private lease only after the caller has rechecked current scope and expiry."""
        if not 1 <= lifetime <= 300:
            raise invalid()
        if self.head(evidence) is None:
            raise AuthError("MEDIA_MISSING", "This attachment is unavailable.", 404)
        try:
            return self.signing_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": evidence.bucket,
                    "Key": evidence.key,
                    "ResponseContentType": evidence.content_type,
                    "ResponseCacheControl": "private, no-store",
                },
                ExpiresIn=lifetime,
            )
        except (BotoCoreError, ClientError):
            raise unavailable() from None

    def delete(self, evidence):
        """Idempotently delete one immutable key after upload leases and live/Undo holds expire."""
        try:
            self.client.delete_object(Bucket=evidence.bucket, Key=evidence.key)
        except (BotoCoreError, ClientError):
            raise unavailable() from None
