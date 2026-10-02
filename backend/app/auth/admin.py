"""Explicit operator commands: read-only provider audit, identity linking and cleanup."""

import argparse
import hmac
from datetime import timedelta
from uuid import UUID

import boto3
from botocore.config import Config
from sqlalchemy import delete, select, update

from app.auth.cognito import Cognito
from app.auth.jwt import AccessVerifier
from app.auth.service import AuthService
from app.config import load_settings
from app.database import Database
from app.models.authentication import AuthAccount, AuthFlow, AuthSession
from app.models.people import StaffIdentity, StaffUser


def check_configuration(settings, client):
    pool = client.describe_user_pool(UserPoolId=settings.cognito_pool_id)["UserPool"]
    app = client.describe_user_pool_client(
        UserPoolId=settings.cognito_pool_id, ClientId=settings.cognito_client_id
    )["UserPoolClient"]
    mfa = client.get_user_pool_mfa_config(UserPoolId=settings.cognito_pool_id)
    policy = pool.get("Policies", {}).get("PasswordPolicy", {})
    checks = {
        "required authenticator MFA": mfa.get("MfaConfiguration") == "ON"
        and mfa.get("SoftwareTokenMfaConfiguration", {}).get("Enabled") is True,
        "no remembered-device bypass": not pool.get("DeviceConfiguration"),
        "password minimum": policy.get("MinimumLength") == 15,
        "no character composition requirements": all(
            policy.get(key) is False
            for key in ["RequireUppercase", "RequireLowercase", "RequireNumbers", "RequireSymbols"]
        ),
        "invitation-only staff pool": pool.get("AdminCreateUserConfig", {}).get(
            "AllowAdminCreateUserOnly"
        )
        is True,
        "email username": pool.get("UsernameAttributes") == ["email"]
        and pool.get("UsernameConfiguration", {}).get("CaseSensitive") is False,
        "email recovery": pool.get("AccountRecoverySetting", {}).get("RecoveryMechanisms")
        == [{"Name": "verified_email", "Priority": 1}],
        "confidential app client": isinstance(app.get("ClientSecret"), str)
        and hmac.compare_digest(
            app["ClientSecret"], settings.cognito_client_secret.get_secret_value()
        ),
        "password auth only": set(app.get("ExplicitAuthFlows", [])) == {"ALLOW_USER_PASSWORD_AUTH"},
        "token revocation": app.get("EnableTokenRevocation") is True,
        "refresh rotation": app.get("RefreshTokenRotation")
        == {"Feature": "ENABLED", "RetryGracePeriodSeconds": 0},
        "short access tokens": app.get("AccessTokenValidity") == 5
        and app.get("TokenValidityUnits", {}).get("AccessToken") == "minutes",
        "refresh lifetime": app.get("RefreshTokenValidity") == settings.auth_session_hours
        and app.get("TokenValidityUnits", {}).get("RefreshToken") == "hours",
        "five-minute challenges": app.get("AuthSessionValidity") == 5,
        "generic Cognito errors": app.get("PreventUserExistenceErrors") == "ENABLED",
        # Cognito requires app-client write permission for required email.
        # Provider tokens remain server-side; staff authorization uses issuer/sub.
        "limited writable attributes": sorted(app.get("WriteAttributes") or [])
        == ["email", "name"],
        "verify email changes": pool.get("UserAttributeUpdateSettings", {}).get(
            "AttributesRequireVerificationBeforeUpdate"
        )
        == ["email"],
        "rotation-capable tier": pool.get("UserPoolTier") == "ESSENTIALS",
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ValueError("Cognito configuration mismatch: " + "; ".join(failed))
    return len(checks)


def link_identity(database, settings, remote, subject, *, staff_id=None, owner_name=None):
    attributes = {item["Name"]: item["Value"] for item in remote.get("UserAttributes", [])}
    if (
        remote.get("Enabled") is not True
        or remote.get("UserStatus") not in {"CONFIRMED", "FORCE_CHANGE_PASSWORD"}
        or not isinstance(remote.get("Username"), str)
        or not 1 <= len(remote["Username"]) <= 128
        or attributes.get("sub") != subject
        or attributes.get("email_verified") != "true"
        or not attributes.get("email")
    ):
        raise ValueError("Use an enabled Cognito account with verified email and the exact subject")
    if bool(staff_id) == bool(owner_name):
        raise ValueError("Choose an existing staff ID or an explicit first-owner bootstrap")
    with database.transaction() as session:
        if owner_name:
            # One bootstrap across competing operator invocations; no runtime admin endpoint.
            from sqlalchemy import text

            session.execute(text("SELECT pg_advisory_xact_lock(714622153)"))
            if session.scalar(select(StaffUser.id).where(StaffUser.role == "owner")):
                raise ValueError("An owner already exists; use explicit staff linking")
            if not owner_name.strip() or len(owner_name) > 200:
                raise ValueError("Use a valid owner name")
            user = StaffUser(
                name=owner_name.strip(), email=attributes["email"].strip().lower(), role="owner"
            )
            session.add(user)
            session.flush()
        else:
            user = session.get(StaffUser, staff_id, with_for_update=True)
            if (
                not user
                or user.status != "active"
                or user.email != attributes["email"].strip().lower()
            ):
                raise ValueError("The explicit active staff record must match the verified email")
        identity = session.scalar(
            select(StaffIdentity).where(
                StaffIdentity.issuer == settings.cognito_issuer, StaffIdentity.subject == subject
            )
        )
        if identity:
            if (
                identity.status != "active"
                or identity.user_id != user.id
                or identity.provider_username
                not in {
                    None,
                    remote["Username"],
                }
            ):
                raise ValueError("That identity is already linked to another staff record")
            identity.provider_username = remote["Username"]
        else:
            session.add(
                StaffIdentity(
                    user_id=user.id,
                    issuer=settings.cognito_issuer,
                    subject=subject,
                    provider_username=remote["Username"],
                )
            )
        return str(user.id)


def maintain(service):
    now = service.clock()
    with service.db.transaction() as session:
        users = list(
            session.scalars(select(AuthAccount.user_id).where(AuthAccount.pending_until <= now))
        )
    for user_id in users:
        service._prepare(user_id)
    with service.db.transaction() as session:
        session.execute(
            update(AuthSession)
            .where(AuthSession.expires_at <= now, AuthSession.closed_at.is_(None))
            .values(
                closed_at=now,
                access_cipher=None,
                revoke_pending=True,
                refresh_lease_id=None,
                refresh_lease_until=None,
            )
        )
    revoked = service.drain_revocations(limit=100)
    with service.db.transaction() as session:
        flows = session.execute(
            delete(AuthFlow).where(AuthFlow.expires_at < now - timedelta(days=1))
        ).rowcount
        sessions = session.execute(
            delete(AuthSession).where(
                AuthSession.closed_at < now - timedelta(days=7),
                AuthSession.refresh_cipher.is_(None),
            )
        ).rowcount
    return {
        "providerRevocationsCompleted": revoked,
        "expiredFlowsRemoved": flows,
        "closedSessionsRemoved": sessions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check-config", "link", "bootstrap-owner", "maintain"])
    parser.add_argument("--subject")
    parser.add_argument("--staff-id", type=UUID)
    parser.add_argument("--owner-name")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.auth_enabled:
        raise SystemExit("Configure authentication explicitly before using this command.")
    database = Database(settings)
    provider = None
    admin = None
    try:
        if args.action == "maintain":
            provider = Cognito(settings)
            print(maintain(AuthService(database, settings, provider, AccessVerifier(settings))))
        else:
            admin = boto3.client(
                "cognito-idp",
                region_name="ap-southeast-1",
                config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1}),
            )
            count = check_configuration(settings, admin)
            if args.action == "check-config":
                print(f"PASS — {count} Cognito configuration checks; no provider changes.")
            else:
                if (
                    not args.subject
                    or (args.action == "link" and not args.staff_id)
                    or (args.action == "bootstrap-owner" and not args.owner_name)
                ):
                    raise ValueError(
                        "Supply the exact subject and the selected staff ID or owner name"
                    )
                remote = admin.admin_get_user(
                    UserPoolId=settings.cognito_pool_id, Username=args.subject
                )
                identity = link_identity(
                    database,
                    settings,
                    remote,
                    args.subject,
                    staff_id=args.staff_id if args.action == "link" else None,
                    owner_name=args.owner_name if args.action == "bootstrap-owner" else None,
                )
                print("Identity linked to staff ID " + identity)
    except Exception as error:
        # SDK exceptions can echo sensitive parameter values. Keep operator output allowlisted.
        raise SystemExit("Authentication administration failed: " + type(error).__name__) from None
    finally:
        if admin:
            admin.close()
        if provider:
            provider.close()
        database.close()


if __name__ == "__main__":
    main()
