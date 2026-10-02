"""Validated environment or mounted-secret configuration; no bundled production secrets."""

import base64
import os
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.managed_secrets import ConfigurationError, DatabasePurpose, managed_values


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FITFINITY_", extra="forbid", hide_input_in_errors=True
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    database_url: SecretStr
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "api"]
    root_path: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    db_pool_size: int = Field(default=1, ge=1, le=10)
    db_pool_timeout_seconds: int = Field(default=5, ge=1, le=30)
    db_pool_recycle_seconds: int = Field(default=60, ge=10, le=300)
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    db_statement_timeout_ms: int = Field(default=5000, ge=100, le=30000)

    auth_enabled: bool = False
    cognito_pool_id: str = ""
    cognito_client_id: str = ""
    cognito_client_secret: SecretStr | None = Field(default=None, repr=False)
    auth_encryption_keys: list[SecretStr] = Field(default_factory=list, repr=False)
    auth_origins: list[str] = []
    auth_cookie_secure: bool = True
    staff_invitations_enabled: bool = False
    staff_portal_url: str = ""
    auth_session_hours: int = Field(default=8, ge=1, le=168)

    @property
    def cognito_issuer(self):
        return f"https://cognito-idp.ap-southeast-1.amazonaws.com/{self.cognito_pool_id}"

    @property
    def session_cookie(self):
        return "__Host-fitfinity-session" if self.auth_cookie_secure else "fitfinity-session-local"

    @property
    def flow_cookie(self):
        return "__Host-fitfinity-flow" if self.auth_cookie_secure else "fitfinity-flow-local"

    @model_validator(mode="after")
    def validate_deployment(self):
        try:
            url = make_url(self.database_url.get_secret_value())
        except Exception:
            raise ValueError("A valid PostgreSQL connection URL is required") from None
        if url.drivername != "postgresql+psycopg" or not url.database or not url.username:
            raise ValueError("Use a named PostgreSQL database and postgresql+psycopg driver")
        if not self.allowed_hosts or any(
            not host or "/" in host or ":" in host for host in self.allowed_hosts
        ):
            raise ValueError("Configure nonempty host names without schemes or ports")
        if self.root_path and (
            not self.root_path.startswith("/")
            or self.root_path.endswith("/")
            or any(char in self.root_path for char in "?#\r\n")
        ):
            raise ValueError("root_path must be empty or a path such as /staff-api")
        if self.environment in {"staging", "production"}:
            if url.query.get("sslmode") != "verify-full":
                raise ValueError("Staging/production database TLS must use sslmode=verify-full")
            if "allowed_hosts" not in self.model_fields_set or any(
                "*" in host for host in self.allowed_hosts
            ):
                raise ValueError("Staging/production requires explicit allowed hosts")
        if self.auth_enabled:
            if not re.fullmatch(r"ap-southeast-1_[A-Za-z0-9]{1,64}", self.cognito_pool_id):
                raise ValueError("Configure the Singapore staff Cognito pool")
            if not re.fullmatch(r"[A-Za-z0-9]{1,128}", self.cognito_client_id):
                raise ValueError("Configure the staff Cognito app client")
            if not self.cognito_client_secret or not re.fullmatch(
                r"[A-Za-z0-9_+]{24,64}", self.cognito_client_secret.get_secret_value()
            ):
                raise ValueError("A confidential Cognito app client is required")
            if not 1 <= len(self.auth_encryption_keys) <= 3:
                raise ValueError("Configure one to three authentication encryption keys")
            for key in self.auth_encryption_keys:
                try:
                    decoded = base64.b64decode(
                        key.get_secret_value(), altchars=b"-_", validate=True
                    )
                except Exception:
                    raise ValueError("Authentication keys must encode 32 random bytes") from None
                if len(decoded) != 32:
                    raise ValueError("Authentication keys must encode 32 random bytes")
            if not self.auth_origins:
                raise ValueError("Authentication requires exact trusted browser origins")
            for origin in self.auth_origins:
                parsed = urlsplit(origin)
                local = self.environment in {"local", "test"} and parsed.hostname in {
                    "localhost",
                    "127.0.0.1",
                    "testserver",
                }
                if (
                    parsed.scheme not in {"https", "http"}
                    or (parsed.scheme != "https" and not local)
                    or not parsed.netloc
                    or parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                    or "*" in origin
                ):
                    raise ValueError("Configure exact HTTPS origins without paths or wildcards")
            if not self.auth_cookie_secure and self.environment not in {"local", "test"}:
                raise ValueError("Deployed authentication cookies must be Secure")
        if self.staff_invitations_enabled:
            portal = urlsplit(self.staff_portal_url)
            origin = f"{portal.scheme}://{portal.netloc}"
            if (
                not self.auth_enabled
                or portal.scheme != "https"
                or origin not in self.auth_origins
                or portal.query
                or portal.fragment
                or portal.username
                or portal.password
                or any(c in self.staff_portal_url for c in '<>"\\\r\n')
            ):
                raise ValueError("Invitations require the trusted HTTPS staff portal URL")
        return self


def load_settings(*, purpose: DatabasePurpose = "runtime") -> Settings:
    """Resolve once at startup; explicit AWS mode never falls back to local credentials."""
    values = managed_values(purpose)
    if purpose == "migration":
        values["staff_invitations_enabled"] = False
    try:
        return Settings(**values, _secrets_dir=os.getenv("FITFINITY_SECRETS_DIR"))
    except Exception:
        # Do not expose Pydantic input dictionaries containing provider secret material.
        if values:
            raise ConfigurationError("Managed deployment settings are invalid") from None
        raise
