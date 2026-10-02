"""Verify provider credentials outside the transaction; recheck local authority inside it."""

from contextlib import contextmanager
from uuid import UUID

from fastapi import Request
from sqlalchemy import select

from app.auth.errors import expired
from app.auth.routes import _handle
from app.authorization import Principal
from app.models.authentication import AuthSession
from app.models.people import StaffIdentity, StaffUser, Trainer


@contextmanager
def authorized_transaction(request: Request):
    auth = request.app.state.auth
    handle = _handle(request, csrf=request.method == "POST")
    _, verified = auth.principal(handle)
    with auth.db.transaction() as session:
        # Identity/status writers lock their row before invalidating AuthAccount. Match that
        # order, then hold the account barrier through the business commit. No AWS calls here.
        user = session.scalar(
            select(StaffUser).where(StaffUser.id == verified.user_id).with_for_update(read=True)
        )
        trainer = None
        if user and user.role == "trainer":
            trainer = session.scalar(
                select(Trainer).where(Trainer.user_id == user.id).with_for_update(read=True)
            )
        identity = session.scalar(
            select(StaffIdentity)
            .where(StaffIdentity.id == verified.identity_id)
            .with_for_update(read=True)
        )
        account = auth._account(session, verified.user_id)
        current = session.scalar(
            select(AuthSession).where(AuthSession.id == verified.id).with_for_update(read=True)
        )
        auth._usable(session, account, current)
        if (
            not identity
            or identity.status != "active"
            or identity.user_id != user.id
            or current.identity_id != verified.identity_id
            or current.epoch != verified.epoch
            or current.access_expires_at <= auth.clock()
        ):
            raise expired()
        if user.role == "trainer" and (trainer is None or trainer.status != "active"):
            raise expired()
        principal = Principal(
            UUID(str(user.id)), user.name, user.role, trainer.id if trainer else None
        )
        yield session, principal
