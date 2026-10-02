"""Explicit Admin creation input; protected roles and trainer fields are never accepted."""

import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, StrictStr, field_validator, model_validator

from app.api.schemas import Contract


class NewAdmin(Contract):
    name: StrictStr = Field(min_length=1, max_length=200)
    email: StrictStr = Field(min_length=3, max_length=320)
    phone_country_code: StrictStr = Field(pattern=r"^\+[1-9][0-9]{0,2}$")
    phone_number: StrictStr = Field(min_length=6, max_length=32)
    birthday: date
    gender: Literal["Female", "Male", "Other", "Prefer not to say"]

    @field_validator("name", "email", "phone_number", mode="before")
    @classmethod
    def clean(cls, value):
        if not isinstance(value, str) or any(ord(char) < 32 for char in value):
            raise ValueError("Invalid contact value")
        return value.strip()

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email address")
        return value.lower()

    @field_validator("birthday", mode="before")
    @classmethod
    def birthday_text(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use an ISO birthday")
        return value

    @model_validator(mode="after")
    def contact(self):
        number = re.sub(r"\D", "", self.phone_number)
        if (
            not re.fullmatch(r"[0-9 ()-]+", self.phone_number)
            or len(number) < 6
            or len(self.phone_country_code[1:] + number) > 15
        ):
            raise ValueError("Invalid phone number")
        if self.birthday > datetime.now(ZoneInfo("Asia/Singapore")).date():
            raise ValueError("Birthday cannot be in the future")
        return self


class AdminCreated(Contract):
    id: UUID
    name: str
    email: str
    role: Literal["admin"]
    invitation: Literal["pending", "sending", "sent", "unknown"]
