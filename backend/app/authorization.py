"""Stored role/assignment policy shared by HTTP services; callers cannot supply authority."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, or_, select, true
from sqlalchemy.orm import Session

from app.auth.errors import AuthError
from app.models.people import Client, Trainer
from app.models.training import AssignmentChange, AssignmentEvent, PackagePurchase, TrainingSession


def unavailable():
    return AuthError("not_found", "The requested resource was not found.", 404)


def conflict():
    return AuthError(
        "state_conflict", "Record changed or is read-only. Refresh and review it.", 409
    )


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    name: str
    role: str
    trainer_id: UUID | None

    @property
    def manages_operations(self):
        return self.role in {"owner", "admin"}

    def operations(self):
        if not self.manages_operations:
            raise AuthError("forbidden", "This action requires operational access.", 403)

    def owner(self):
        if self.role != "owner":
            raise AuthError("forbidden", "This action is available to the owner.", 403)


def client_scope(principal: Principal):
    if principal.manages_operations:
        return true()
    return or_(
        Client.trainer_id == principal.trainer_id,
        exists().where(
            PackagePurchase.client_id == Client.id,
            PackagePurchase.trainer_id == principal.trainer_id,
        ),
        exists().where(
            AssignmentEvent.client_id == Client.id,
            or_(
                AssignmentEvent.old_trainer_id == principal.trainer_id,
                AssignmentEvent.new_trainer_id == principal.trainer_id,
            ),
        ),
    )


def client_record(session: Session, principal: Principal, identity: UUID, *, write=False):
    record = session.scalar(
        select(Client)
        .where(Client.id == identity, client_scope(principal))
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise unavailable()
    if write and record.status != "active":
        raise conflict()
    return record


def trainer_record(session: Session, principal: Principal, identity: UUID, *, write=False):
    if not principal.manages_operations and principal.trainer_id != identity:
        raise unavailable()
    record = session.scalar(
        select(Trainer)
        .where(Trainer.id == identity)
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise unavailable()
    if write and record.status != "active":
        raise conflict()
    return record


def session_scope(principal: Principal):
    if principal.manages_operations:
        return true()
    return or_(
        TrainingSession.trainer_id == principal.trainer_id,
        exists().where(
            Client.id == TrainingSession.client_id, Client.trainer_id == principal.trainer_id
        ),
        exists().where(
            PackagePurchase.id == TrainingSession.purchase_id,
            PackagePurchase.purchased_trainer_id == principal.trainer_id,
        ),
        exists().where(
            AssignmentChange.session_id == TrainingSession.id,
            or_(
                AssignmentChange.old_trainer_id == principal.trainer_id,
                AssignmentChange.new_trainer_id == principal.trainer_id,
            ),
        ),
    )


def session_record(session: Session, principal: Principal, identity: UUID, *, write=False):
    found = session.get(TrainingSession, identity)
    if found is None:
        raise unavailable()
    # Match lifecycle writers' client -> purchase -> session lock order. Session access
    # must not depend on permission to open the full client profile.
    client = session.scalar(
        select(Client)
        .where(Client.id == found.client_id)
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    purchase = session.scalar(
        select(PackagePurchase)
        .where(PackagePurchase.id == found.purchase_id)
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    record = session.scalar(
        select(TrainingSession)
        .where(TrainingSession.id == identity, session_scope(principal))
        .with_for_update(read=not write)
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise unavailable()
    if write:
        if not principal.manages_operations and record.trainer_id != principal.trainer_id:
            raise unavailable()
        if (
            client.status != "active"
            or purchase.status != "active"
            or record.status in {"completed", "cancelled"}
        ):
            raise conflict()
    return record


def client_write(session: Session, principal: Principal, identity: UUID, *, coaching=False):
    """Owner/Admin manage general data; the current trainer may write coaching data only."""
    if not coaching:
        principal.operations()
    record = client_record(session, principal, identity, write=True)
    if not principal.manages_operations and principal.trainer_id != record.trainer_id:
        raise unavailable()
    return record
