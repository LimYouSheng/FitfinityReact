"""Durable authentication orchestration; external calls never hold a DB transaction."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.auth.errors import AuthError, busy, expired
from app.auth.security import TokenVault, csrf_token, handle_hash, new_handle, validate_password
from app.models.authentication import AuthAccount, AuthFlow, AuthSession
from app.models.people import StaffIdentity, StaffUser, Trainer

FLOW_SECONDS = 300


@dataclass
class AuthResult:
    body: dict
    session_handle: str | None = field(default=None, repr=False)
    flow_handle: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None


class AuthService:
    def __init__(self, database, settings, provider, verifier, clock=None):
        self.db, self.settings, self.provider, self.verifier = (
            database,
            settings,
            provider,
            verifier,
        )
        self.vault = TokenVault(settings.auth_encryption_keys)
        self.clock = clock or (lambda: datetime.now(UTC))

    def _account(self, session, user_id):
        session.execute(insert(AuthAccount).values(user_id=user_id).on_conflict_do_nothing())
        return session.scalar(
            select(AuthAccount).where(AuthAccount.user_id == user_id).with_for_update()
        )

    def _invalidate(self, session, account, finish_pending=False):
        account.epoch += 1
        if finish_pending:
            account.pending_id = account.pending_until = None
        session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == account.user_id)
            .values(
                closed_at=self.clock(),
                access_cipher=None,
                revoke_pending=True,
                refresh_lease_id=None,
                refresh_lease_until=None,
            )
        )

    def _prepare(self, user_id):
        # An abandoned external password operation revokes old authority before unblocking.
        with self.db.transaction() as session:
            account = self._account(session, user_id)
            if account.pending_until and account.pending_until <= self.clock():
                self._invalidate(session, account, finish_pending=True)

    def _active(self, session, user_id):
        user = session.get(StaffUser, user_id)
        if not user or user.status != "active" or user.role not in {"owner", "admin", "trainer"}:
            raise expired()
        trainer_id = None
        if user.role == "trainer":
            trainer = session.scalar(select(Trainer).where(Trainer.user_id == user.id))
            if not trainer or trainer.status != "active":
                raise expired()
            trainer_id = str(trainer.id)
        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "trainerId": trainer_id,
        }

    def _usable(self, session, account, record):
        if record is None:
            raise expired()
        self._active(session, record.user_id)
        if account.pending_id:
            raise busy()
        if account.epoch != record.epoch or record.expires_at <= self.clock():
            raise expired()
        if isinstance(record, AuthSession) and record.closed_at:
            raise expired()

    def _start(self, email, kind):
        with self.db.transaction() as session:
            user = session.scalar(select(StaffUser).where(StaffUser.email == email.strip().lower()))
            if not user:
                raise AuthError()
            user_id = user.id
        self._prepare(user_id)
        with self.db.transaction() as session:
            account = self._account(session, user_id)
            self._active(session, user_id)
            if account.pending_id:
                raise busy()
            identity = session.scalar(
                select(StaffIdentity).where(
                    StaffIdentity.user_id == user_id,
                    StaffIdentity.issuer == self.settings.cognito_issuer,
                )
            )
            if not identity or identity.status != "active" or not identity.provider_username:
                raise AuthError()
            recent = session.scalar(
                select(func.count())
                .select_from(AuthFlow)
                .where(
                    AuthFlow.user_id == user_id,
                    AuthFlow.created_at > self.clock() - timedelta(minutes=10),
                )
            )
            if recent >= 10:
                raise AuthError("AUTH_RATE_LIMITED", "Too many attempts. Try again later.", 429)
            handle = new_handle()
            flow = AuthFlow(
                handle_hash=handle_hash(handle),
                user_id=user_id,
                epoch=account.epoch,
                kind=kind,
                step="starting",
                username=identity.provider_username,
                expires_at=self.clock() + timedelta(seconds=FLOW_SECONDS),
            )
            session.add(flow)
            session.flush()
        return handle, flow

    def _end_flow(self, flow_id):
        with self.db.transaction() as session:
            session.execute(
                update(AuthFlow)
                .where(AuthFlow.id == flow_id)
                .values(step="ended", provider_state=None)
            )

    def _claim_flow(self, handle, kind):
        digest = handle_hash(handle)
        with self.db.transaction() as session:
            user_id = session.scalar(select(AuthFlow.user_id).where(AuthFlow.handle_hash == digest))
            if not user_id:
                raise expired()
        self._prepare(user_id)
        with self.db.transaction() as session:
            account = self._account(session, user_id)
            flow = session.scalar(
                select(AuthFlow).where(AuthFlow.handle_hash == digest).with_for_update()
            )
            self._usable(session, account, flow)
            if flow.kind != kind or flow.step in {"ended", "starting"} or flow.attempts >= 6:
                raise expired()
            if flow.step == "processing":
                raise busy()
            step = flow.step
            flow.step, flow.attempts = "processing", flow.attempts + 1
            session.flush()
        return flow, step

    def _flow_failure(self, flow, step, error):
        with self.db.transaction() as session:
            account = self._account(session, flow.user_id)
            current = session.get(AuthFlow, flow.id)
            retryable = isinstance(error, AuthError) and error.code in {
                "INVALID_CODE",
                "PASSWORD_POLICY",
                "AUTH_RATE_LIMITED",
            }
            if current is not None and current.step == "processing":
                current.step = (
                    step
                    if retryable and current.attempts < 6 and account.epoch == flow.epoch
                    else "ended"
                )
                if current.step == "ended":
                    current.provider_state = None

    def _credentials(self, access):
        claims = self.verifier.verify(access)
        remote = self.provider.user(
            access
        )  # Cognito revocation/disable checks, beyond JWT signature.
        attributes = {item["Name"]: item["Value"] for item in remote.get("UserAttributes", [])}
        if (
            attributes.get("sub") != claims["sub"]
            or attributes.get("email_verified") != "true"
            or remote.get("Username") != claims["username"]
            or "SOFTWARE_TOKEN_MFA" not in remote.get("UserMFASettingList", [])
        ):
            raise AuthError()
        return claims

    def _advance(self, flow, reply, mfa_complete=False):
        if "AuthenticationResult" in reply:
            if not mfa_complete:
                raise AuthError(
                    "MFA_REQUIRED", "Staff sign-in requires an authenticator code.", 403
                )
            tokens = reply["AuthenticationResult"]
            access, refresh = tokens.get("AccessToken"), tokens.get("RefreshToken")
            if not refresh:
                raise AuthError()
            claims = self._credentials(access)
            handle = new_handle()
            with self.db.transaction() as session:
                account = self._account(session, flow.user_id)
                current = session.scalar(
                    select(AuthFlow).where(AuthFlow.id == flow.id).with_for_update()
                )
                self._usable(session, account, current)
                if (
                    current.step != "processing"
                    or claims["auth_time"] < int(flow.created_at.timestamp()) - 30
                ):
                    raise expired()
                identity = session.scalar(
                    select(StaffIdentity).where(
                        StaffIdentity.user_id == flow.user_id,
                        StaffIdentity.issuer == claims["iss"],
                        StaffIdentity.subject == claims["sub"],
                    )
                )
                if (
                    not identity
                    or identity.status != "active"
                    or flow.username != claims["username"]
                ):
                    raise AuthError()
                digest = handle_hash(handle)
                authenticated = datetime.fromtimestamp(claims["auth_time"], UTC)
                expires_at = authenticated + timedelta(hours=self.settings.auth_session_hours)
                record = AuthSession(
                    handle_hash=digest,
                    user_id=flow.user_id,
                    identity_id=identity.id,
                    epoch=account.epoch,
                    authenticated_at=authenticated,
                    expires_at=expires_at,
                    access_expires_at=datetime.fromtimestamp(claims["exp"], UTC),
                    access_cipher=self.vault.seal(access, f"{digest}:access"),
                    refresh_cipher=self.vault.seal(refresh, f"{digest}:refresh"),
                )
                session.add(record)
                current.step, current.provider_state = "ended", None
                user = self._active(session, flow.user_id)
            return AuthResult(
                {
                    "user": user,
                    "csrfToken": csrf_token(handle),
                    "expiresAt": expires_at.isoformat(),
                },
                session_handle=handle,
                expires_at=expires_at,
            )
        step = reply.get("ChallengeName")
        if step not in {"NEW_PASSWORD_REQUIRED", "SOFTWARE_TOKEN_MFA", "MFA_SETUP"}:
            raise AuthError()
        state = reply.get("Session")
        body = {"challenge": step, "expiresAt": flow.expires_at.isoformat()}
        if step == "NEW_PASSWORD_REQUIRED":
            # Provisioning owns required verified email, not this challenge endpoint.
            required = reply.get("ChallengeParameters", {}).get("requiredAttributes", "[]")
            try:
                complete = (
                    isinstance(required, str)
                    and len(required) <= 1024
                    and json.loads(required) == []
                )
            except ValueError:
                complete = False
            if not complete:
                raise AuthError(
                    "ACCOUNT_SETUP_REQUIRED", "Ask the owner to finish account setup.", 403
                )
        if step == "MFA_SETUP":
            associated = self.provider.associate(state)
            state = associated.get("Session")
            secret = associated.get("SecretCode")
            if not isinstance(secret, str) or not 16 <= len(secret) <= 256:
                raise AuthError()
            body["secretCode"] = secret
        encrypted = self.vault.seal(state, f"{flow.handle_hash}:challenge")
        with self.db.transaction() as session:
            account = self._account(session, flow.user_id)
            current = session.scalar(
                select(AuthFlow).where(AuthFlow.id == flow.id).with_for_update()
            )
            self._usable(session, account, current)
            if current.step not in {"starting", "processing"}:
                raise expired()
            current.step, current.provider_state = step, encrypted
        return AuthResult(body)

    def sign_in(self, email, password):
        try:
            handle, flow = self._start(email, "sign_in")
        except AuthError as error:
            if error.code == "SESSION_EXPIRED":
                raise AuthError() from None
            raise
        try:
            result = self._advance(flow, self.provider.begin(flow.username, password))
            result.flow_handle, result.expires_at = handle, flow.expires_at
            return result
        except Exception:
            self._end_flow(flow.id)
            raise

    def challenge(self, handle, code=None, new_password=None):
        flow, step = self._claim_flow(handle, "sign_in")
        try:
            state = self.vault.open(flow.provider_state, f"{flow.handle_hash}:challenge")
            if step == "NEW_PASSWORD_REQUIRED":
                answer = validate_password(new_password)
            else:
                if (
                    not isinstance(code, str)
                    or len(code) != 6
                    or not code.isascii()
                    or not code.isdigit()
                ):
                    raise AuthError("INVALID_CODE", "Enter the six-digit authenticator code.", 422)
                answer = code
            if step == "MFA_SETUP":
                state = self.provider.verify_totp(state, code)
            reply = self.provider.answer(flow.username, step, state, answer)
            return self._advance(
                flow, reply, mfa_complete=step in {"SOFTWARE_TOKEN_MFA", "MFA_SETUP"}
            )
        except Exception as error:
            self._flow_failure(flow, step, error)
            raise

    def _session(self, handle):
        digest = handle_hash(handle)
        with self.db.transaction() as session:
            user_id = session.scalar(
                select(AuthSession.user_id).where(AuthSession.handle_hash == digest)
            )
            if not user_id:
                raise expired()
        self._prepare(user_id)
        with self.db.transaction() as session:
            account = self._account(session, user_id)
            record = session.scalar(select(AuthSession).where(AuthSession.handle_hash == digest))
            self._usable(session, account, record)
            return record

    def principal(self, handle):
        record = self._session(handle)
        if record.access_expires_at <= self.clock():
            raise AuthError("TOKEN_EXPIRED", "Refresh your session to continue.")
        try:
            claims = self._credentials(
                self.vault.open(record.access_cipher, f"{record.handle_hash}:access")
            )
        except AuthError as error:
            if error.status in {400, 401, 403}:
                self.sign_out(handle)
                raise expired() from None
            raise
        with self.db.transaction() as session:
            account = self._account(session, record.user_id)
            current = session.get(AuthSession, record.id)
            self._usable(session, account, current)
            identity = session.get(StaffIdentity, current.identity_id)
            if (
                not identity
                or identity.status != "active"
                or identity.user_id != current.user_id
                or identity.issuer != claims["iss"]
                or identity.subject != claims["sub"]
                or int(current.authenticated_at.timestamp()) != claims["auth_time"]
            ):
                raise expired()
            user = self._active(session, current.user_id)
        return user, record

    def bootstrap(self, handle):
        # No principal, health data or provider tokens. The cookie-bound token permits
        # refresh after a reload; /me still verifies provider authority before UI access.
        record = self._session(handle)
        with self.db.transaction() as session:
            identity = session.get(StaffIdentity, record.identity_id)
            if not identity or identity.status != "active" or identity.user_id != record.user_id:
                raise expired()
        return AuthResult(
            {"csrfToken": csrf_token(handle), "expiresAt": record.expires_at.isoformat()}
        )

    def me(self, handle):
        user, record = self.principal(handle)
        return AuthResult(
            {
                "user": user,
                "csrfToken": csrf_token(handle),
                "expiresAt": record.expires_at.isoformat(),
                "accessExpiresAt": record.access_expires_at.isoformat(),
            }
        )

    def refresh(self, handle):
        record = self._session(handle)
        lease = uuid4()
        abandoned = False
        with self.db.transaction() as session:
            account = self._account(session, record.user_id)
            current = session.scalar(
                select(AuthSession).where(AuthSession.id == record.id).with_for_update()
            )
            self._usable(session, account, current)
            if current.refresh_lease_id:
                if current.refresh_lease_until > self.clock():
                    raise busy()
                current.closed_at, current.access_cipher, current.revoke_pending = (
                    self.clock(),
                    None,
                    True,
                )
                abandoned = True
            else:
                current.refresh_lease_id, current.refresh_lease_until = (
                    lease,
                    self.clock() + timedelta(seconds=20),
                )
                refresh = self.vault.open(current.refresh_cipher, f"{current.handle_hash}:refresh")
        if abandoned:
            raise expired()
        try:
            tokens = self.provider.refresh(refresh)["AuthenticationResult"]
            access, rotated = tokens.get("AccessToken"), tokens.get("RefreshToken")
            claims = self._credentials(access)
            if (
                not rotated
                or rotated == refresh
                or claims["auth_time"] != int(record.authenticated_at.timestamp())
            ):
                raise expired()
            with self.db.transaction() as session:
                account = self._account(session, record.user_id)
                current = session.scalar(
                    select(AuthSession).where(AuthSession.id == record.id).with_for_update()
                )
                self._usable(session, account, current)
                identity = session.get(StaffIdentity, current.identity_id)
                if (
                    not identity
                    or identity.status != "active"
                    or current.refresh_lease_id != lease
                    or current.refresh_lease_until <= self.clock()
                    or identity.subject != claims["sub"]
                    or identity.issuer != claims["iss"]
                ):
                    raise expired()
                current.access_cipher = self.vault.seal(access, f"{current.handle_hash}:access")
                current.refresh_cipher = self.vault.seal(rotated, f"{current.handle_hash}:refresh")
                current.access_expires_at = datetime.fromtimestamp(claims["exp"], UTC)
                current.refresh_lease_id = current.refresh_lease_until = None
            return AuthResult(
                {
                    "refreshed": True,
                    "accessExpiresAt": current.access_expires_at.isoformat(),
                    "expiresAt": record.expires_at.isoformat(),
                }
            )
        except Exception:
            with self.db.transaction() as session:
                self._account(session, record.user_id)
                current = session.get(AuthSession, record.id)
                if current.refresh_lease_id == lease:
                    current.closed_at, current.access_cipher, current.revoke_pending = (
                        self.clock(),
                        None,
                        True,
                    )
                    current.refresh_lease_id = current.refresh_lease_until = None
            raise

    def sign_out(self, handle, everywhere=False):
        if everywhere:
            self.principal(handle)
        digest = handle_hash(handle)
        with self.db.transaction() as session:
            user_id = session.scalar(
                select(AuthSession.user_id).where(AuthSession.handle_hash == digest)
            )
        if user_id:
            with self.db.transaction() as session:
                account = self._account(session, user_id)
                if everywhere:
                    current = session.scalar(
                        select(AuthSession).where(AuthSession.handle_hash == digest)
                    )
                    self._usable(session, account, current)
                    self._invalidate(session, account)
                else:
                    session.execute(
                        update(AuthSession)
                        .where(AuthSession.handle_hash == digest)
                        .values(
                            closed_at=self.clock(),
                            access_cipher=None,
                            revoke_pending=True,
                            refresh_lease_id=None,
                            refresh_lease_until=None,
                        )
                    )
            self.drain_revocations(user_id=user_id)
        return AuthResult({"signedOut": True})

    def _block_password_operation(self, user_id, epoch, session_id=None):
        operation = uuid4()
        with self.db.transaction() as session:
            account = self._account(session, user_id)
            self._active(session, user_id)
            if account.pending_id:
                raise busy()
            if account.epoch != epoch:
                raise expired()
            if session_id:
                self._usable(session, account, session.get(AuthSession, session_id))
            account.pending_id, account.pending_until = (
                operation,
                self.clock() + timedelta(seconds=30),
            )
        return operation

    def _finish_password_operation(self, user_id, operation, error=None):
        with self.db.transaction() as session:
            account = self._account(session, user_id)
            if account.pending_id != operation:
                raise expired()
            if error is None:
                self._invalidate(session, account, finish_pending=True)
            elif isinstance(error, AuthError) and error.status in {400, 401, 403, 422, 429}:
                account.pending_id = account.pending_until = None
            # Ambiguous upstream failure stays blocked; _prepare revokes before recovery.

    def change_password(self, handle, current, proposed):
        validate_password(proposed)
        if proposed == current:
            raise AuthError("PASSWORD_UNCHANGED", "Choose a different new password.", 422)
        _, record = self.principal(handle)
        operation = self._block_password_operation(record.user_id, record.epoch, record.id)
        try:
            self.provider.change_password(
                self.vault.open(record.access_cipher, f"{record.handle_hash}:access"),
                current,
                proposed,
            )
        except Exception as error:
            self._finish_password_operation(record.user_id, operation, error)
            raise
        self._finish_password_operation(record.user_id, operation)
        self.drain_revocations(user_id=record.user_id)
        return AuthResult({"passwordChanged": True, "signedOut": True})

    def forgot_password(self, email):
        # Identical body and cookie shape for unregistered/inactive/unmapped staff.
        handle = new_handle()
        result = AuthResult(
            {"message": "If the account is eligible, a recovery code will be emailed."},
            flow_handle=handle,
            expires_at=self.clock() + timedelta(seconds=FLOW_SECONDS),
        )
        try:
            handle, flow = self._start(email, "recovery")
        except AuthError:
            return result
        result.flow_handle = handle
        try:
            self.provider.forgot(flow.username)
            with self.db.transaction() as session:
                account = self._account(session, flow.user_id)
                current = session.get(AuthFlow, flow.id)
                self._usable(session, account, current)
                current.step = "recovery"
        except Exception:
            self._end_flow(flow.id)
            # Do not expose eligibility or recovery delivery details.
        return result

    def reset_password(self, handle, code, password):
        validate_password(password)
        flow, step = self._claim_flow(handle, "recovery")
        operation = None
        try:
            operation = self._block_password_operation(flow.user_id, flow.epoch)
            self.provider.reset(flow.username, code, password)
        except Exception as error:
            if operation:
                self._finish_password_operation(flow.user_id, operation, error)
            self._flow_failure(flow, step, error)
            raise
        self._finish_password_operation(flow.user_id, operation)
        self._end_flow(flow.id)
        self.drain_revocations(user_id=flow.user_id)
        return AuthResult({"passwordReset": True, "signedOut": True})

    def drain_revocations(self, user_id=None, limit=20):
        with self.db.transaction() as session:
            query = select(AuthSession).where(
                AuthSession.revoke_pending.is_(True), AuthSession.refresh_cipher.is_not(None)
            )
            if user_id:
                query = query.where(AuthSession.user_id == user_id)
            records = list(session.scalars(query.order_by(AuthSession.created_at).limit(limit)))
        completed = 0
        for record in records:
            try:
                token = self.vault.open(record.refresh_cipher, f"{record.handle_hash}:refresh")
                self.provider.revoke(token)
            except AuthError:
                continue
            with self.db.transaction() as session:
                # Closing sessions never reopen. Parallel drains can safely revoke the same token.
                changed = session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.id == record.id,
                        AuthSession.refresh_cipher == record.refresh_cipher,
                        AuthSession.closed_at.is_not(None),
                    )
                    .values(refresh_cipher=None, revoke_pending=False)
                )
                completed += changed.rowcount
        return completed
