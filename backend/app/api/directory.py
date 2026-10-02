"""Bounded, authorized read projections for the canonical staff directory screens."""

from collections import defaultdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.api.schemas import DirectoryPackage, DirectorySnapshot
from app.auth.errors import AuthError
from app.models.people import Client, ClientPerson, Trainer, TrainerAvailability
from app.models.training import (
    CreditDebit,
    PackagePurchase,
    PackageTemplate,
    PackageTemplateRevision,
    PurchaseScheduleSlot,
)

# A complete snapshot fits the agreed 200–300 clients/5–10 trainers. Never truncate it.
# Replace this contract with server pagination before increasing these explicit bounds.
MAX_RECORDS = 2000


def bounded(session, statement, maximum=MAX_RECORDS):
    rows = session.scalars(statement.limit(maximum + 1)).all()
    if len(rows) > maximum:
        raise AuthError("directory_capacity", "The directory could not be loaded completely.", 503)
    return rows


def fields(record):
    return {column.key: getattr(record, column.key) for column in record.__table__.columns}


def snapshot(session, principal):
    client_query = select(Client).order_by(Client.id)
    trainer_query = select(Trainer).order_by(Trainer.id)
    if not principal.manages_operations:
        # Full profiles require the current permanent relationship. Session cover is separate.
        client_query = client_query.where(Client.trainer_id == principal.trainer_id)
        trainer_query = trainer_query.where(Trainer.id == principal.trainer_id)
    clients = bounded(session, client_query.with_for_update(read=True))
    trainers = bounded(session, trainer_query.with_for_update(read=True))
    client_ids, trainer_ids = [c.id for c in clients], [t.id for t in trainers]
    people = defaultdict(list)
    for person in bounded(
        session,
        select(ClientPerson)
        .where(ClientPerson.client_id.in_(client_ids))
        .order_by(ClientPerson.client_id, ClientPerson.position),
        MAX_RECORDS * 2,
    ):
        people[person.client_id].append(fields(person))
    purchases = bounded(
        session,
        select(PackagePurchase)
        .where(PackagePurchase.client_id.in_(client_ids))
        .order_by(PackagePurchase.start_date, PackagePurchase.id)
        .with_for_update(read=True),
    )
    purchase_ids = [p.id for p in purchases]
    slots = defaultdict(list)
    for slot in bounded(
        session,
        select(PurchaseScheduleSlot)
        .where(PurchaseScheduleSlot.purchase_id.in_(purchase_ids))
        .order_by(PurchaseScheduleSlot.weekday),
        MAX_RECORDS * 7,
    ):
        slots[slot.purchase_id].append(fields(slot))
    used = dict(
        session.execute(
            select(CreditDebit.purchase_id, func.count(CreditDebit.id))
            .where(CreditDebit.purchase_id.in_(purchase_ids))
            .group_by(CreditDebit.purchase_id)
        ).all()
    )
    purchase_trainers = dict(
        session.execute(
            select(Trainer.id, Trainer.name).where(
                Trainer.id.in_([p.trainer_id for p in purchases])
            )
        ).all()
    )
    by_client = defaultdict(list)
    for purchase in purchases:
        by_client[purchase.client_id].append(
            {
                **fields(purchase),
                "used": used.get(purchase.id, 0),
                "trainer_name": purchase_trainers[purchase.trainer_id],
                "schedule": slots[purchase.id],
            }
        )
    availability = defaultdict(list)
    for slot in bounded(
        session,
        select(TrainerAvailability)
        .where(TrainerAvailability.trainer_id.in_(trainer_ids))
        .order_by(TrainerAvailability.weekday, TrainerAvailability.starts_at),
        MAX_RECORDS * 7,
    ):
        availability[slot.trainer_id].append(fields(slot))
    packages = []
    if principal.manages_operations:
        templates = bounded(
            session, select(PackageTemplate).order_by(PackageTemplate.id).with_for_update(read=True)
        )
        # Template lifecycle version and immutable terms revision are separate counters.
        latest = (
            select(
                PackageTemplateRevision.template_id,
                func.max(PackageTemplateRevision.revision).label("revision"),
            )
            .where(PackageTemplateRevision.template_id.in_([t.id for t in templates]))
            .group_by(PackageTemplateRevision.template_id)
            .subquery()
        )
        revisions = {
            row.template_id: row
            for row in session.scalars(
                select(PackageTemplateRevision).join(
                    latest,
                    (PackageTemplateRevision.template_id == latest.c.template_id)
                    & (PackageTemplateRevision.revision == latest.c.revision),
                )
            )
        }
        for template in templates:
            revision = revisions.get(template.id)
            if revision is None:
                raise AuthError("directory_incomplete", "Package details are unavailable.", 503)
            packages.append(
                DirectoryPackage(
                    id=template.id,
                    version=template.version,
                    revision=revision.revision,
                    status=template.status,
                    name=revision.name,
                    total_sessions=revision.total_sessions,
                    validity_days=revision.validity_days,
                )
            )
    # Validate through explicit allowlists; ORM fields such as health_notes never escape.
    from app.api.schemas import (
        DirectoryClient,
        DirectoryPerson,
        DirectoryPurchase,
        DirectorySlot,
        DirectoryTrainer,
        OperationalTrainer,
    )

    def project(model, value):
        return model.model_validate({key: value[key] for key in model.model_fields})

    projected_clients = []
    for client in clients:
        client_people = [project(DirectoryPerson, p) for p in people[client.id]]
        if len(client_people) != (2 if client.kind == "couple" else 1):
            raise AuthError("directory_incomplete", "Client details are unavailable.", 503)
        client_purchases = [
            project(
                DirectoryPurchase,
                {**p, "schedule": [project(DirectorySlot, slot) for slot in p["schedule"]]},
            )
            for p in by_client[client.id]
        ]
        projected_clients.append(
            project(
                DirectoryClient,
                {**fields(client), "people": client_people, "purchases": client_purchases},
            )
        )
    projected_trainers = [
        project(
            OperationalTrainer if principal.role == "admin" else DirectoryTrainer,
            {**fields(t), "availability": [project(DirectorySlot, s) for s in availability[t.id]]},
        )
        for t in trainers
    ]
    now = datetime.now(UTC)
    return DirectorySnapshot(
        schemaVersion=1,
        viewerId=principal.user_id,
        serverAt=now,
        businessDate=now.astimezone(ZoneInfo("Asia/Singapore")).date(),
        timeZone="Asia/Singapore",
        clients=projected_clients,
        trainers=projected_trainers,
        packages=packages,
    )
