"""Typed library commands; bytes and signed URLs never enter durable response snapshots."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from app.api.schemas import Contract

Category = Literal["Full Body", "Upper Body", "Core", "Lower Body", "Single Leg", "Cardio"]
CATEGORIES = ["Full Body", "Upper Body", "Core", "Lower Body", "Single Leg", "Cardio"]


class OriginalLibraryAction(Contract):
    """No replacement fields are accepted after the original command is reserved."""


class LibraryMedia(Contract):
    id: UUID
    name: str
    type: str
    size: int


class LibraryExercise(Contract):
    id: UUID
    name: str
    category: str
    description: str
    status: Literal["active", "inactive"]
    version: int
    createdAt: datetime
    updatedAt: datetime
    media: LibraryMedia | None


class Catalogue(Contract):
    items: list[LibraryExercise]
    categories: list[str] = Field(default_factory=lambda: list(CATEGORIES))


class UploadEvidence(Contract):
    name: StrictStr = Field(min_length=1, max_length=255)
    type: Literal[
        "image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm", "video/quicktime"
    ]
    size: StrictInt = Field(gt=0, le=50 * 1024 * 1024)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class SaveLibrary(Contract):
    id: UUID | None = None
    expectedVersion: StrictInt | None = Field(default=None, gt=0)
    name: StrictStr = Field(min_length=1, max_length=180)
    category: Category
    description: StrictStr = Field(default="", max_length=2000)
    status: Literal["active", "inactive"]
    removeMedia: StrictBool = False
    upload: UploadEvidence | None = None

    @model_validator(mode="after")
    def reviewed(self):
        if (self.id is None) != (self.expectedVersion is None):
            raise ValueError("Existing records require their reviewed version")
        self.name = " ".join(self.name.split())
        self.description = self.description.strip()
        if not self.name or self.name.lower() in {"custom exercise", "__custom__"}:
            raise ValueError("Choose a unique exercise name")
        if self.upload and self.removeMedia:
            raise ValueError("Choose either replacement or removal")
        return self


class LibraryIntentView(Contract):
    key: UUID
    state: Literal["pending", "completed", "expired"]
    uploadUntil: datetime
    result: LibraryExercise | None


class UploadLease(Contract):
    url: str
    headers: dict[str, str]


class ReadLease(Contract):
    url: str
    sha256: str
    size: int
    type: str
    version: int


class MediaReadCheck(Contract):
    valid: Literal[True]
