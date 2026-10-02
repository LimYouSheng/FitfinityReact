"""Verify Cognito access tokens against bounded, issuer-owned rotating RSA keys."""

import json
import threading
import time
import urllib.request
from datetime import UTC, datetime

import jwt

from app.auth.errors import AuthError, unavailable


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("JWKS redirects are not allowed")


def download_keys(url):
    try:
        with urllib.request.build_opener(NoRedirect).open(url, timeout=3) as response:
            body = response.read(131073)
            if response.status != 200 or len(body) > 131072:
                raise ValueError("Invalid key response")
        return json.loads(body)
    except Exception:
        raise unavailable() from None


class AccessVerifier:
    def __init__(self, settings, fetch=download_keys):
        self.issuer = settings.cognito_issuer
        self.client_id = settings.cognito_client_id
        self.fetch = fetch
        self._keys = {}
        self._loaded = float("-inf")
        self._attempted = float("-inf")
        self._lock = threading.Lock()

    def _key(self, kid):
        with self._lock:
            now = time.monotonic()
            fresh = now - self._loaded < 300
            if fresh and kid in self._keys:
                return self._keys[kid]
            if now - self._attempted < 5:
                if not fresh:
                    raise unavailable()
                raise AuthError()
            self._attempted = now
            data = self.fetch(self.issuer + "/.well-known/jwks.json")
            try:
                records = data["keys"]
                if not isinstance(records, list) or not 1 <= len(records) <= 8:
                    raise ValueError()
                keys = {}
                for item in records:
                    if (item.get("kty"), item.get("alg"), item.get("use")) != (
                        "RSA",
                        "RS256",
                        "sig",
                    ):
                        raise ValueError()
                    key_id = item["kid"]
                    if not isinstance(key_id, str) or not 1 <= len(key_id) <= 200 or key_id in keys:
                        raise ValueError()
                    key = jwt.PyJWK.from_dict(item).key
                    if key.key_size < 2048:
                        raise ValueError()
                    keys[key_id] = key
            except (KeyError, TypeError, ValueError, jwt.PyJWTError):
                raise unavailable() from None
            self._keys, self._loaded = keys, now
            if kid not in keys:
                raise AuthError()
            return keys[kid]

    def verify(self, token):
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise AuthError()
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256"
                or header.get("crit")
                or not isinstance(kid, str)
                or not 1 <= len(kid) <= 200
            ):
                raise AuthError()
            claims = jwt.decode(
                token,
                self._key(kid),
                algorithms=["RS256"],
                issuer=self.issuer,
                options={
                    "verify_aud": False,
                    "require": [
                        "exp",
                        "iat",
                        "auth_time",
                        "iss",
                        "sub",
                        "client_id",
                        "token_use",
                        "username",
                        "scope",
                    ],
                },
            )
            if claims["token_use"] != "access" or claims["client_id"] != self.client_id:
                raise AuthError()
            for field in ("exp", "iat", "auth_time"):
                if type(claims[field]) is not int:
                    raise AuthError()
            now = datetime.now(UTC).timestamp()
            if (
                not claims["auth_time"] <= claims["iat"] < claims["exp"]
                or claims["auth_time"] > now
                or claims["exp"] - claims["iat"] > 600
            ):
                raise AuthError()
            for field in ("sub", "username", "scope"):
                if (
                    not isinstance(claims[field], str)
                    or not claims[field]
                    or len(claims[field]) > 2048
                ):
                    raise AuthError()
            if "aws.cognito.signin.user.admin" not in claims["scope"].split():
                raise AuthError()
            return claims
        except jwt.PyJWTError:
            raise AuthError() from None
