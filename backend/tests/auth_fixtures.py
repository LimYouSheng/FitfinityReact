"""Real signed JWTs and a deterministic provider; no AWS calls, credentials or mail."""

import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.cognito import Cognito
from app.auth.jwt import AccessVerifier
from app.auth.security import new_handle
from app.auth.service import AuthService
from app.config import Settings
from app.models.people import StaffIdentity


@pytest.fixture
def auth_settings(settings):
    return Settings(
        **{
            **settings.model_dump(),
            "auth_enabled": True,
            "cognito_pool_id": "ap-southeast-1_TestPool",
            "cognito_client_id": "testclient123",
            "cognito_client_secret": "unit_test_client_secret_value",
            "auth_encryption_keys": [base64.urlsafe_b64encode(bytes(range(32))).decode()],
            "auth_origins": ["https://staff.example"],
            "auth_cookie_secure": True,
        }
    )


@pytest.fixture(scope="session")
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="test-key-one", alg="RS256", use="sig")
    return key, public


@pytest.fixture
def signed(auth_settings, rsa_keys):
    def make(claims=None, header=None, algorithm="RS256", key=None):
        now = int(time.time())
        values = {
            "iss": auth_settings.cognito_issuer,
            "sub": "identity-subject-one",
            "client_id": auth_settings.cognito_client_id,
            "token_use": "access",
            "username": "provider-username-one",
            "scope": "aws.cognito.signin.user.admin",
            "exp": now + 300,
            "iat": now,
            "auth_time": now,
        }
        values.update(claims or {})
        values = {k: v for k, v in values.items() if v is not None}
        return jwt.encode(
            values,
            key or rsa_keys[0],
            algorithm=algorithm,
            headers={"kid": "test-key-one", **(header or {})},
        )

    return make


@pytest.fixture
def verifier(auth_settings, rsa_keys):
    return AccessVerifier(auth_settings, fetch=lambda _: {"keys": [rsa_keys[1]]})


class FakeCognito:
    def __init__(self, signed):
        self.signed = signed
        self.calls = []
        self.errors = {}
        self.begin_step = "SOFTWARE_TOKEN_MFA"
        self.claims = {}
        self.user_changes = {}
        self.auth_time = int(time.time())
        self.db = None
        self.before_refresh = None

    def _call(self, name):
        # Assert the real SQLAlchemy pool is released before each external provider step.
        if self.db:
            assert self.no_connection_held()
        self.calls.append(name)
        if name in self.errors:
            raise self.errors[name]

    def tokens(self):
        return {
            "AuthenticationResult": {
                "AccessToken": self.signed({"auth_time": self.auth_time, **self.claims}),
                "RefreshToken": new_handle(),
                "TokenType": "Bearer",
                "ExpiresIn": 300,
            }
        }

    def begin(self, username, password):
        self._call("begin")
        if self.begin_step == "tokens":
            return self.tokens()
        return {"ChallengeName": self.begin_step, "Session": "opaque-provider-session-value"}

    def answer(self, username, step, state, answer):
        self._call("answer")
        if step == "NEW_PASSWORD_REQUIRED":
            return {"ChallengeName": "MFA_SETUP", "Session": "opaque-provider-setup-value"}
        return self.tokens()

    def associate(self, state):
        self._call("associate")
        return {
            "Session": "opaque-provider-associated-value",
            "SecretCode": "ABCDEFGHIJKLMNOP234567",
        }

    def verify_totp(self, state, code):
        self._call("verify_totp")
        return "opaque-provider-verified-value"

    def user(self, access):
        self._call("user")
        return {
            "Username": "provider-username-one",
            "UserMFASettingList": ["SOFTWARE_TOKEN_MFA"],
            "UserAttributes": [
                {"Name": "sub", "Value": "identity-subject-one"},
                {"Name": "email_verified", "Value": "true"},
            ],
            **self.user_changes,
        }

    def refresh(self, refresh):
        self._call("refresh")
        if self.before_refresh:
            self.before_refresh()
        return self.tokens()

    def revoke(self, refresh):
        self._call("revoke")
        return {}

    def change_password(self, access, current, proposed):
        self._call("change_password")

    def forgot(self, username):
        self._call("forgot")

    def reset(self, username, code, password):
        self._call("reset")

    def close(self):
        pass


@pytest.fixture
def fake_cognito(signed):
    return FakeCognito(signed)


@pytest.fixture
def sdk(auth_settings):
    provider = Cognito(auth_settings)
    yield provider
    provider.close()


@pytest.fixture
def auth_service(domain_db, graph, auth_settings, fake_cognito, verifier):
    with domain_db.transaction() as session:
        session.add(
            StaffIdentity(
                user_id=graph["owner_id"],
                issuer=auth_settings.cognito_issuer,
                subject="identity-subject-one",
                provider_username="provider-username-one",
            )
        )
    from threading import local

    from sqlalchemy import event

    held = local()

    def checkout(*_):
        held.count = getattr(held, "count", 0) + 1

    def checkin(*_):
        held.count -= 1

    event.listen(domain_db.engine, "checkout", checkout)
    event.listen(domain_db.engine, "checkin", checkin)
    fake_cognito.no_connection_held = lambda: getattr(held, "count", 0) == 0
    fake_cognito.db = domain_db
    return AuthService(domain_db, auth_settings, fake_cognito, verifier)


@pytest.fixture
def login(auth_service, graph):
    from app.models.people import StaffUser

    with auth_service.db.transaction() as session:
        email = session.get(StaffUser, graph["owner_id"]).email

    def run():
        result = auth_service.sign_in(email, "initial-password-value")
        return auth_service.challenge(result.flow_handle, code="123456")

    return run
