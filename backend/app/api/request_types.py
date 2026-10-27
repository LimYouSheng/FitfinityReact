"""Shared HTTP request annotations; independent of route registration."""

from typing import Annotated
from uuid import UUID

from fastapi import Header

RequestKey = Annotated[
    UUID,
    Header(
        alias="Idempotency-Key",
        description="New UUID per save; retain the key and identical body for retries.",
    ),
]
