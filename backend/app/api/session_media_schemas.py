"""Recording commands bind the reviewed session and immutable original file."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from app.api.schemas import Contract


class RecordingUpload(Contract):
    name: StrictStr = Field(min_length=1, max_length=255)
    type: Literal["video/mp4", "video/webm", "video/quicktime"]
    size: StrictInt = Field(gt=0, le=10 * 1024 * 1024)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class SaveRecording(Contract):
    sessionId: UUID
    exerciseId: UUID
    expected: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    remove: StrictBool
    upload: RecordingUpload | None = None
    duration: StrictInt | None = Field(default=None, ge=1, le=60)
    source: Literal["recorded", "attached"] = "attached"
    caption: StrictStr = Field(default="", max_length=10000)
    processingStatus: Literal["complete", "deferred"] = "deferred"
    audioIncluded: StrictBool | None = None

    @model_validator(mode="after")
    def action(self):
        if self.remove != (self.upload is None):
            raise ValueError("Choose replacement or removal")
        return self


class RecordingMedia(Contract):
    id: UUID
    name: str
    type: str
    size: int
    attachedAt: datetime
    expiresAt: datetime


class RecordingReview(Contract):
    sessionId: UUID
    exerciseId: UUID
    version: int
    expected: str
    media: RecordingMedia | None


class RecordingSaved(Contract):
    sessionId: UUID
    exerciseId: UUID
    version: int
    savedAt: datetime
    media: RecordingMedia | None


class RecordingIntent(Contract):
    key: UUID
    state: Literal["pending", "completed", "expired"]
    uploadUntil: datetime
    result: RecordingSaved | None
