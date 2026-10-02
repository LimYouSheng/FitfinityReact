"""Application composition. Health and staff identity; domain APIs belong to later milestones."""

from contextlib import asynccontextmanager

from alembic.runtime.migration import MigrationContext
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.openapi import configure_openapi
from app.api.routes import router as staff_router
from app.api.schemas import ERROR_RESPONSES, Live, Ready
from app.api.staff import router as access_router
from app.auth.cognito import Cognito
from app.auth.errors import AuthError
from app.auth.invitations import CognitoInvitations
from app.auth.jwt import AccessVerifier
from app.auth.middleware import AuthRequestMiddleware
from app.auth.routes import router as auth_router
from app.auth.service import AuthService
from app.config import Settings, load_settings
from app.database import Database
from app.migrations import expected_revisions
from app.observability import RequestContextMiddleware, configure_logging, error_response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logger = configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = Database(settings)
        app.state.expected_revisions = expected_revisions()
        if settings.auth_enabled:
            app.state.invitations = CognitoInvitations(settings)
            provider = Cognito(settings)
            app.state.auth = AuthService(
                app.state.database, settings, provider, AccessVerifier(settings)
            )
        logger.info("application_started")
        try:
            yield
        finally:
            if settings.auth_enabled:
                app.state.auth.provider.close()
                app.state.invitations.close()
            app.state.database.close()
            logger.info("application_stopped")

    app = FastAPI(
        title="Fitfinity API",
        version="0.2.0",
        responses=ERROR_RESPONSES,
        lifespan=lifespan,
        root_path=settings.root_path,
        docs_url="/docs" if settings.environment == "local" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment == "local" else None,
    )
    app.state.auth_settings = settings
    if settings.auth_enabled:
        app.include_router(auth_router)
        app.include_router(staff_router)
        app.include_router(access_router)
        app.add_middleware(AuthRequestMiddleware, settings=settings)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.auth_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestContextMiddleware, logger=logger)

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError):
        # An old request can finish after another tab has replaced the session.
        # Only explicit successful auth transitions may mutate the cookie.
        return error_response(exc.code, exc.message, exc.status, request.state.request_id)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        conflict = isinstance(exc, (IntegrityError, StaleDataError))
        return error_response(
            "state_conflict" if conflict else "service_unavailable",
            "Record changed or is read-only. Refresh and review it."
            if conflict
            else "Service is temporarily unavailable. Retry using the same request key.",
            409 if conflict else 503,
            request.state.request_id,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        messages = {
            404: ("not_found", "The requested resource was not found."),
            405: ("method_not_allowed", "This method is not allowed."),
        }
        code, message = messages.get(exc.status_code, ("request_rejected", "Request rejected."))
        response = error_response(code, message, exc.status_code, request.state.request_id)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        return error_response(
            "validation_error", "Request validation failed.", 422, request.state.request_id
        )

    @app.get("/health/live", tags=["health"], response_model=Live, operation_id="healthLive")
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"], response_model=Ready, operation_id="healthReady")
    def ready(request: Request):
        if settings.environment in {"staging", "production"} and not settings.auth_enabled:
            return error_response(
                "not_ready", "Service is not ready.", 503, request.state.request_id
            )
        try:
            with request.app.state.database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                actual = set(MigrationContext.configure(connection).get_current_heads())
                if actual != request.app.state.expected_revisions:
                    return error_response(
                        "not_ready", "Service is not ready.", 503, request.state.request_id
                    )
        except SQLAlchemyError as exc:
            logger.warning(
                "database_unavailable",
                extra={
                    "request_id": request.state.request_id,
                    "error_type": type(exc).__name__,
                },
            )
            return error_response(
                "not_ready", "Service is not ready.", 503, request.state.request_id
            )
        return {"status": "ready"}

    configure_openapi(app, settings)
    return app
