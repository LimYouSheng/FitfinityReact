"""Opaque browser handles and authenticated encryption with row/purpose binding."""

import base64
import hashlib
import hmac
import re
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.auth.errors import AuthError, expired

HANDLE = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def new_handle():
    return secrets.token_urlsafe(32)


def handle_hash(value):
    if not isinstance(value, str) or not HANDLE.fullmatch(value):
        raise expired()
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def csrf_token(handle):
    handle_hash(handle)
    return hmac.new(handle.encode("ascii"), b"fitfinity-csrf-v1", hashlib.sha256).hexdigest()


def require_csrf(handle, supplied):
    if (
        not isinstance(supplied, str)
        or not re.fullmatch(r"[0-9a-f]{64}", supplied)
        or not hmac.compare_digest(csrf_token(handle), supplied)
    ):
        raise AuthError("CSRF_REJECTED", "Request verification failed.", 403)


def validate_password(value):
    # Cognito ChangePassword and ConfirmForgotPassword require the non-whitespace pattern.
    if not isinstance(value, str) or not 15 <= len(value) <= 128 or any(c.isspace() for c in value):
        raise AuthError(
            "PASSWORD_POLICY", "Use 15–128 characters without spaces or other whitespace.", 422
        )
    return value


class TokenVault:
    def __init__(self, keys):
        self._keys = [
            AESGCM(base64.b64decode(key.get_secret_value(), altchars=b"-_", validate=True))
            for key in keys
        ]

    def seal(self, value, context):
        if not isinstance(value, str) or not value or len(value) > 16384:
            raise AuthError()
        nonce = secrets.token_bytes(12)
        return b"\x01" + nonce + self._keys[0].encrypt(nonce, value.encode(), context.encode())

    def open(self, value, context):
        if not isinstance(value, bytes) or not 30 <= len(value) <= 65536 or value[0] != 1:
            raise expired()
        for key in self._keys:
            try:
                return key.decrypt(value[1:13], value[13:], context.encode()).decode()
            except (InvalidTag, UnicodeDecodeError):
                continue
        raise expired()
