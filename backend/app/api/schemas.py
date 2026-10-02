"""Public shapes. Health answers appear only in scoped assessment responses."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)


class ErrorDetail(Contract):
    code: str
    message: str
    requestId: str


class ErrorEnvelope(Contract):
    error: ErrorDetail


ERROR_RESPONSES = {
    status: {"model": ErrorEnvelope, "description": description}
    for status, description in {
        400: "Ambiguous or invalid request",
        401: "Session or access credentials expired",
        403: "Operation, origin or CSRF denied",
        404: "Resource unavailable for this account",
        405: "Method unavailable",
        409: "State, version or idempotency conflict; review before retrying",
        413: "Request exceeds the body limit",
        415: "JSON is required",
        422: "Invalid input; answer and credential values are never echoed",
        429: "Rate limit reached",
        500: "Request failed safely",
        503: "Dependency unavailable",
    }.items()
}


class Live(Contract):
    status: Literal["alive"]


class Ready(Contract):
    status: Literal["ready"]


class Staff(Contract):
    id: UUID
    name: str
    email: str
    role: Literal["owner", "admin", "trainer"]
    trainerId: UUID | None


class SignedIn(Contract):
    user: Staff
    csrfToken: str
    expiresAt: datetime


class SessionInfo(SignedIn):
    accessExpiresAt: datetime


class SessionBootstrap(Contract):
    csrfToken: str
    expiresAt: datetime


class AuthChallenge(Contract):
    challenge: Literal["NEW_PASSWORD_REQUIRED", "SOFTWARE_TOKEN_MFA", "MFA_SETUP"]
    expiresAt: datetime
    secretCode: str | None = None


class SignedOut(Contract):
    signedOut: Literal[True]


class PasswordChanged(Contract):
    passwordChanged: Literal[True]
    signedOut: Literal[True]


class RecoveryStarted(Contract):
    message: str


class PasswordReset(Contract):
    passwordReset: Literal[True]
    signedOut: Literal[True]


class PasswordPolicy(Contract):
    minimumLength: Literal[15]
    maximumLength: Literal[128]
    spacesAllowed: Literal[False]
    requiresCharacterMix: Literal[False]
    scheduledRotation: Literal[False]


class MFAPolicy(Contract):
    required: Literal[True]
    method: Literal["totp"]


class AuthPolicy(Contract):
    password: PasswordPolicy
    mfa: MFAPolicy
    recovery: Literal["verified_email"]


class ServerClock(Contract):
    serverAt: datetime
    businessDate: date
    timeZone: Literal["Asia/Singapore"]


class ClientSummary(Contract):
    id: UUID
    version: int
    name: str
    kind: Literal["individual", "couple"]
    status: Literal["active", "inactive"]
    trainer_id: UUID


class PersonSummary(Contract):
    id: UUID
    version: int
    position: int
    name: str
    birthday: date


class ClientDetail(ClientSummary):
    people: list[PersonSummary]


class TrainerSummary(Contract):
    id: UUID
    version: int
    name: str
    status: Literal["active", "inactive"]


class SessionSummary(Contract):
    id: UUID
    version: int
    client_id: UUID
    purchase_id: UUID
    trainer_id: UUID
    training_date: date
    starts_at: time
    ends_at: time
    status: Literal["scheduled", "planned", "completed", "cancelled"]


class Page[T](Contract):
    items: list[T]
    limit: int
    offset: int
    hasMore: bool


Answers = dict[str, StrictStr | StrictInt | StrictFloat]


class NewAssessment(Contract):
    formId: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    formVersion: int = Field(gt=0, strict=True)
    expectedPersonVersion: int = Field(gt=0, strict=True)
    answers: Answers
    event: Literal["draft", "completed"] = "completed"


class SaveAssessment(Contract):
    expectedVersion: int = Field(gt=0, strict=True)
    answers: Answers
    event: Literal["draft", "completed", "correction", "voided"]
    reason: str | None = Field(default=None, min_length=1, max_length=2000)


class AssessmentRevision(Contract):
    id: UUID
    assessment_id: UUID
    revision: int
    previous_revision: int | None
    form_id: str
    form_version: int
    status: Literal["draft", "completed", "voided"]
    event: Literal["draft", "completed", "correction", "voided"]
    assessment_date: date
    assessor_id: UUID
    assessor_name: str
    client_name: str
    client_birthday: date
    answers: Answers
    actor_id: UUID
    actor_name: str
    reason: str | None
    created_at: datetime


class FormDefinition(Contract):
    form_id: str
    version: int
    title: str
    source_filename: str
    source_sha256: str
    layout_release: str
    layout_sha256: str
    definition: dict


class Refreshed(Contract):
    refreshed: Literal[True]
    accessExpiresAt: datetime
    expiresAt: datetime


class DirectoryPerson(PersonSummary):
    email: str
    phone_country_code: str
    phone_number: str
    gender: str
    emergency_name: str
    emergency_relationship: str
    emergency_country_code: str
    emergency_number: str


class DirectorySlot(Contract):
    id: UUID
    weekday: int
    starts_at: time
    ends_at: time


class DirectoryPurchase(Contract):
    id: UUID
    version: int
    template_id: UUID
    template_revision: int
    name: str
    total_sessions: int
    validity_days: int
    sessions_per_week: int
    free_gym: bool
    start_date: date
    end_date: date
    purchased_trainer_id: UUID
    trainer_name: str
    trainer_id: UUID
    status: Literal["active", "inactive"]
    stage: Literal["queued", "current", "archived"]
    used: int
    schedule: list[DirectorySlot]


class DirectoryClient(ClientSummary):
    gender_preference: str
    remarks: str
    people: list[DirectoryPerson]
    purchases: list[DirectoryPurchase]


class OperationalTrainer(TrainerSummary):
    email: str
    phone_country_code: str
    phone_number: str
    birthday: date
    gender: str
    trainer_type: str
    qualifications: str
    public_profile: bool
    approve_availability: bool
    approve_session_time: bool
    approve_session_trainer: bool
    approve_weekly_schedule: bool
    availability: list[DirectorySlot]


class DirectoryTrainer(OperationalTrainer):
    peak_rate_cents: int
    off_peak_rate_cents: int


class DirectoryPackage(Contract):
    id: UUID
    version: int
    revision: int
    status: Literal["active", "inactive"]
    name: str
    total_sessions: int
    validity_days: int


class DirectorySnapshot(ServerClock):
    schemaVersion: Literal[1]
    viewerId: UUID
    clients: list[DirectoryClient]
    trainers: list[DirectoryTrainer | OperationalTrainer]
    packages: list[DirectoryPackage]


class SessionClient(Contract):
    session_id: UUID
    client_id: UUID
    name: str
    kind: Literal["individual", "couple"]
    person_names: list[str]
