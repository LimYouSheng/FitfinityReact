"""Test-only real HTTP application. Isolated PostgreSQL; only Cognito is substituted.

Not copied into the runtime image. No test/reset routes or authorization overrides.
"""

import base64
import json
import os
import secrets
import time
from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import date, timedelta
from datetime import time as clock_time
from pathlib import Path
from uuid import uuid4

import jwt
import psycopg
import uvicorn
from alembic import command
from cryptography.hazmat.primitives.asymmetric import rsa
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app.auth.errors import AuthError
from app.auth.jwt import AccessVerifier
from app.auth.service import AuthService
from app.config import Settings
from app.database import Database
from app.main import create_app
from app.migrations import expected_revisions, migration_config
from app.models.communications import Message, MessageReceipt
from app.models.people import Client, StaffIdentity, StaffUser, Trainer, TrainerAvailability
from app.models.training import PackageTemplate, PackageTemplateRevision, PurchasePreference
from app.persistence import add_client, add_purchase
from tests.domain_fixtures import person, purchase_parts
from tests.test_package_reactivation_review import freeze

PASSWORD = "browser-test-password-only"


class BrowserIdentityProvider:
    """Local signed tokens, validated by the production verifier with a test JWKS."""

    def __init__(self, settings, allowed_users):
        self.settings = settings
        self.allowed_users = allowed_users
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.public.update(kid="browser-test-key", alg="RS256", use="sig")
        self.refreshes = {}

    def begin(self, username, password):
        if password != PASSWORD or username not in self.allowed_users:
            raise AuthError("AUTH_FAILED", "Invalid test identity.")
        return {"ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": username}

    def answer(self, username, step, state, answer):
        if step != "SOFTWARE_TOKEN_MFA" or state != username or answer != "123456":
            raise AuthError("AUTH_FAILED", "Invalid test challenge.")
        return self.tokens(username)

    def tokens(self, username, auth_time=None):
        now = int(time.time())
        claims = {
            "iss": self.settings.cognito_issuer,
            "sub": f"browser-{username}",
            "username": username,
            "client_id": self.settings.cognito_client_id,
            "token_use": "access",
            "scope": "aws.cognito.signin.user.admin",
            "iat": now,
            "auth_time": auth_time if auth_time is not None else now,
            "exp": now + 300,
        }
        refresh = secrets.token_urlsafe(32)
        self.refreshes[refresh] = (username, claims["auth_time"])
        return {
            "AuthenticationResult": {
                "AccessToken": jwt.encode(
                    claims, self.key, algorithm="RS256", headers={"kid": "browser-test-key"}
                ),
                "RefreshToken": refresh,
                "TokenType": "Bearer",
                "ExpiresIn": 300,
            }
        }

    def user(self, access):
        claims = jwt.decode(
            access, self.key.public_key(), algorithms=["RS256"], issuer=self.settings.cognito_issuer
        )
        return {
            "Username": claims["username"],
            "UserMFASettingList": ["SOFTWARE_TOKEN_MFA"],
            "UserAttributes": [
                {"Name": "sub", "Value": claims["sub"]},
                {"Name": "email_verified", "Value": "true"},
            ],
        }

    def refresh(self, refresh):
        return self.tokens(*self.refreshes[refresh])

    def revoke(self, refresh):
        self.refreshes.pop(refresh, None)

    def close(self):
        self.refreshes.clear()


class BrowserInvitations:
    """Keep Cognito provisioning and delivery entirely inside this test process."""

    def __init__(self):
        self.remote = {}
        self.sent = set()

    def check_configuration(self):
        """Use the already validated test settings without external discovery."""

    def ensure(self, user_id, name, email):
        """Return one synthetic provider identity for the real persisted staff account."""
        if not email.endswith("@example.test"):
            raise ValueError("Only synthetic browser-test invitation addresses are allowed")
        return self.remote.setdefault(
            user_id,
            {
                "subject": str(user_id),
                "username": str(user_id),
                "status": "FORCE_CHANGE_PASSWORD",
            },
        )

    def send(self, user_id, email):
        """Record one local delivery and fail if the application repeats the effect."""
        if (
            user_id not in self.remote
            or user_id in self.sent
            or not email.endswith("@example.test")
        ):
            raise ValueError("Unexpected or repeated test invitation")
        self.sent.add(user_id)
        return True

    def close(self):
        self.remote.clear()
        self.sent.clear()


def seed(db, settings):
    with db.transaction() as session:
        users = {
            role: StaffUser(name=f"Browser {role.title()}", email=f"{role}@example.test", role=role)
            for role in ("owner", "admin", "trainer")
        }
        session.add_all(users.values())
        session.flush()
        for role, user in users.items():
            session.add(
                StaffIdentity(
                    user_id=user.id,
                    issuer=settings.cognito_issuer,
                    subject=f"browser-{role}",
                    provider_username=role,
                )
            )
        trainer = Trainer(
            user_id=users["trainer"].id,
            name="Browser Trainer",
            email="trainer@example.test",
            birthday=date(1985, 1, 1),
            phone_country_code="+65",
            phone_number="91234569",
            gender="Other",
            trainer_type="Strength",
            peak_rate_cents=8000,
            off_peak_rate_cents=5500,
        )
        session.add(trainer)
        session.flush()
        client = add_client(
            session,
            Client(kind="individual", name="Browser Client", trainer_id=trainer.id),
            [person("Browser Client")],
        )
        template = PackageTemplate()
        session.add(template)
        session.flush()
        session.add(
            PackageTemplateRevision(
                template_id=template.id,
                revision=1,
                name="Two sessions",
                total_sessions=2,
                validity_days=90,
                actor_id=users["owner"].id,
                actor_name=users["owner"].name,
            )
        )
        session.flush()
        # Dates derive from the server's business clock; assertions use returned evidence.
        start = session.scalar(
            text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date")
        ) + timedelta(days=7)
        other_trainer = Trainer(
            name="Other Trainer",
            email="other-trainer@example.test",
            birthday=date(1986, 1, 1),
            phone_country_code="+65",
            phone_number="91234669",
            gender="Other",
            trainer_type="Strength",
            peak_rate_cents=8000,
            off_peak_rate_cents=5500,
        )
        session.add(other_trainer)
        session.flush()
        other_person = person("Other Client")
        other_person.email = "other-client@example.test"
        other_person.phone_number = "91234667"
        other_client = add_client(
            session,
            Client(kind="individual", name="Other Client", trainer_id=other_trainer.id),
            [other_person],
        )
        for seeded_client, seeded_trainer in [(client, trainer), (other_client, other_trainer)]:
            graph = {
                "client_id": seeded_client.id,
                "trainer_id": seeded_trainer.id,
                "template_id": template.id,
            }
            purchase, slots, preferences, bookings = purchase_parts(graph, start, stage="current")
            add_purchase(session, purchase, slots, preferences, bookings, expected_client_version=1)

        # Distinct real accounts isolate authentication rate budgets between scenarios.
        # Production rate limits remain intact; each fresh-context check still signs in via UI.
        scopes = (
            "contacts",
            "assessments",
            "lifecycle",
            "weekly",
            "assignment",
            "package",
            "renewal",
            "messages",
            "staff",
            "content",
            "retry",
            "create",
            "admincreate",
            "onboarding",
            "interrupted",
            "catalogue",
        )
        allowed_users = {"owner", "admin", "trainer"}
        cohort_owners = {}
        for project in ("desktop-chromium", "phone", "tablet"):
            for scope in scopes:
                for role in ("owner", "admin"):
                    alias = f"{project}-{scope}-{role}"
                    user = StaffUser(
                        name=f"{scope} {role}", email=f"{alias}@example.test", role=role
                    )
                    session.add(user)
                    session.flush()
                    session.add(
                        StaffIdentity(
                            user_id=user.id,
                            issuer=settings.cognito_issuer,
                            subject=f"browser-{alias}",
                            provider_username=alias,
                        )
                    )
                    allowed_users.add(alias)
                    if role == "owner":
                        cohort_owners[(project, scope)] = user.id

        # Dedicated project/workflow aggregates keep independent browser writers isolated.
        for project in ("desktop-chromium", "phone", "tablet"):
            for purpose in (
                "contacts",
                "assessments",
                "lifecycle",
                "weekly",
                "assignment",
                "package",
                "renewal",
                "messages",
                "staff",
                "assignmentcover",
                "staffcover",
                "onboardingcover",
                "availability",
            ):
                label = f"{project} {purpose}"
                cohort_trainer = Trainer(
                    name=label + " Trainer",
                    email=f"{project}-{purpose}-trainer@example.test",
                    birthday=date(1985, 1, 1),
                    phone_country_code="+65",
                    phone_number="91234569",
                    gender="Other",
                    trainer_type="Strength",
                    peak_rate_cents=8000,
                    off_peak_rate_cents=5500,
                )
                if purpose == "availability":
                    alias = f"{project}-availability"
                    allowed_users.add(alias)
                    account = StaffUser(name=label, email=f"{alias}@example.test", role="trainer")
                    session.add(account)
                    session.flush()
                    session.add(
                        StaffIdentity(
                            user_id=account.id,
                            issuer=settings.cognito_issuer,
                            subject=f"browser-{alias}",
                            provider_username=alias,
                        )
                    )
                    cohort_trainer.user_id = account.id
                    cohort_trainer.email = account.email
                session.add(cohort_trainer)
                session.flush()
                for weekday in range(7):
                    session.add(
                        TrainerAvailability(
                            trainer_id=cohort_trainer.id,
                            weekday=weekday,
                            starts_at=clock_time(8),
                            ends_at=clock_time(20),
                        )
                    )
                cohort_person = person(label)
                cohort_person.email = f"{project}-{purpose}-client@example.test"
                cohort_client = add_client(
                    session,
                    Client(kind="individual", name=label, trainer_id=cohort_trainer.id),
                    [cohort_person],
                )
                if purpose.endswith("cover"):
                    continue
                graph = {
                    "client_id": cohort_client.id,
                    "trainer_id": cohort_trainer.id,
                    "template_id": template.id,
                }
                purchase, slots, preferences, bookings = purchase_parts(
                    graph, start, stage="current"
                )
                if purpose == "renewal":
                    preferences.append(
                        PurchasePreference(
                            weekday=start.weekday(),
                            starts_at=clock_time(9),
                            ends_at=clock_time(12),
                        )
                    )
                add_purchase(
                    session, purchase, slots, preferences, bookings, expected_client_version=1
                )
                if purpose == "package":
                    freeze(session, {"owner_id": users["owner"].id}, purchase)
                if purpose == "messages":
                    notice = Message(
                        kind="renewal",
                        title=label + " renewal",
                        body="Two sessions remain",
                        client_id=cohort_client.id,
                        purchase_id=purchase.id,
                        actor_id=users["owner"].id,
                        actor_name=users["owner"].name,
                    )
                    session.add(notice)
                    session.flush()
                    session.add(
                        MessageReceipt(
                            message_id=notice.id, user_id=cohort_owners[(project, purpose)]
                        )
                    )

        return allowed_users


class WorkerApplications:
    """Dispatch test workers to separate real applications/databases, never shared catalogues."""

    def __init__(self, health, factory):
        self.health, self.factory, self.workers = health, factory, {}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.health(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        key = headers.get(b"x-fitfinity-browser-worker", b"")
        if not key and scope.get("path") == "/health/ready":
            await self.health(scope, receive, send)
            return
        if not key.isdigit() or len(key) > 3 or int(key) > 255:
            await JSONResponse({"error": "A bounded test worker identity is required"}, 400)(
                scope, receive, send
            )
            return
        key = int(key)
        if key not in self.workers:
            if len(self.workers) >= 64:
                await JSONResponse({"error": "Test worker capacity exceeded"}, 503)(
                    scope, receive, send
                )
                return
            # No await while allocating: concurrent first requests cannot create two databases.
            self.workers[key] = self.factory()
        await self.workers[key](scope, receive, send)


@contextmanager
def browser_app(control):
    """Own one migrated database, real application and local Cognito substitutes."""
    name = "fitfinity_test_browser_" + uuid4().hex
    dsn = control.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    db = None
    try:
        settings = Settings(
            _env_file=None,
            environment="test",
            log_level="WARNING",
            database_url=control.set(database=name).render_as_string(hide_password=False),
            auth_enabled=True,
            staff_invitations_enabled=True,
            staff_portal_url="https://staff.example.test/",
            cognito_pool_id="ap-southeast-1_BrowserTest",
            cognito_client_id="browsertest123",
            cognito_client_secret="browser_test_client_secret_value",
            auth_encryption_keys=[base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()],
            auth_cookie_secure=False,
            auth_origins=["http://127.0.0.1:4180", "https://staff.example.test"],
            allowed_hosts=["127.0.0.1", "localhost"],
        )
        engine = create_engine(settings.database_url.get_secret_value())
        try:
            with engine.connect() as connection:
                config = migration_config()
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        finally:
            engine.dispose()
        db = Database(settings)
        allowed_users = seed(db, settings)
        provider = BrowserIdentityProvider(settings, allowed_users)
        app = create_app(settings)

        app.state.database = db
        app.state.expected_revisions = expected_revisions()
        app.state.auth = AuthService(
            db,
            settings,
            provider,
            AccessVerifier(settings, fetch=lambda _: {"keys": [provider.public]}),
        )
        app.state.invitations = BrowserInvitations()

        @asynccontextmanager
        async def lifespan(app):
            # Resources belong to the surrounding context, including worker apps.
            yield

        app.router.lifespan_context = lifespan
        site = Path(os.environ.get("FITFINITY_BROWSER_SITE", "/browser-site"))
        app.mount("/", StaticFiles(directory=site, html=True), name="browser-site")
        try:
            yield app
        finally:
            provider.close()
            app.state.invitations.close()
    finally:
        if db:
            db.close()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def main():
    control = make_url(os.environ["FITFINITY_TEST_DATABASE_URL"])
    if (
        control.drivername != "postgresql+psycopg"
        or control.database != "fitfinity_test"
        or control.host != "test-db"
        or control.username != "fitfinity_test"
        or control.port not in (None, 5432)
        or control.query
    ):
        raise ValueError("Only the isolated fitfinity_test Docker control database is allowed")
    if os.environ.get("FITFINITY_ENVIRONMENT") != "test":
        raise ValueError("Browser harness requires explicit test environment")
    with ExitStack() as resources:

        def factory():
            return resources.enter_context(browser_app(control))

        applications = WorkerApplications(factory(), factory)
        uvicorn.run(applications, host="0.0.0.0", port=4180, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
