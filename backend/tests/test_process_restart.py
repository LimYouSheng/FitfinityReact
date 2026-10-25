"""Actual HTTP worker death/restart against the same disposable PostgreSQL database."""

import multiprocessing
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from uuid import uuid4

import httpx2 as httpx
import pytest
import uvicorn
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.auth.service import AuthService
from app.config import Settings
from app.main import create_app
from app.models.api import ContentSaveReceipt
from app.models.media import ContentEntry

pytestmark = pytest.mark.database


def serve(settings, provider, verifier, channel, listener, interrupt):
    """Only this disposable child receives the deterministic pre-commit crash hook."""
    provider.db = None
    app = create_app(settings)
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            application.state.auth.provider.close()
            application.state.auth = AuthService(
                application.state.database, settings, provider, verifier
            )
            yield

    app.router.lifespan_context = lifespan
    if interrupt:

        def flushed(session, _):
            if any(isinstance(row, ContentSaveReceipt) for row in session.new):
                channel.send("uncommitted")
                channel.recv()  # Parent kills this child; no commit or test-only HTTP route.

        event.listen(Session, "after_flush", flushed)

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            channel.send(("ready", os.getpid()))

    Server(uvicorn.Config(app, log_level="warning", access_log=False)).run(sockets=[listener])


@contextmanager
def worker(settings, provider, verifier, listener, *, interrupt=False):
    """Fork only the test worker; parent owns the database and listening socket."""
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe()
    process = context.Process(
        target=serve, args=(settings, provider, verifier, child, listener, interrupt)
    )
    process.start()
    child.close()
    try:
        assert parent.poll(10), "HTTP worker failed to start"
        ready, pid = parent.recv()
        assert ready == "ready" and pid == process.pid
        yield process, parent
    finally:
        if process.is_alive():
            process.kill()
        process.join(10)
        assert not process.is_alive()
        parent.close()
        process.close()


@pytest.mark.parametrize("crash", ["after_commit", "before_commit"])
def test_worker_restart_preserves_committed_receipts_and_rolls_back_interrupted_write(
    domain_db, auth_settings, fake_cognito, verifier, login, graph, crash
):
    signed = login()
    # Dispose parent connections before forking; children open their own bounded pools.
    domain_db.close()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        settings = Settings(
            **{
                **auth_settings.model_dump(),
                "database_url": domain_db.engine.url.render_as_string(hide_password=False),
                "auth_cookie_secure": False,
                "auth_origins": [origin],
                "allowed_hosts": ["127.0.0.1"],
            }
        )
        key = str(uuid4())
        payload = {
            "draft": {
                "key": "restart/proof",
                "title": "Restart proof",
                "body": "Durable",
                "status": "draft",
            }
        }
        headers = {
            "Origin": origin,
            "X-CSRF-Token": signed.body["csrfToken"],
            "Idempotency-Key": key,
            "Connection": "close",
        }
        cookies = {settings.session_cookie: signed.session_handle}
        with worker(
            settings,
            fake_cognito,
            verifier,
            listener,
            interrupt=crash == "before_commit",
        ) as (process, channel):
            first_pid = process.pid
            with httpx.Client(
                base_url=origin, headers=headers, cookies=cookies, timeout=10
            ) as client:
                assert client.get("/me").status_code == 200
                if crash == "after_commit":
                    response = client.post("/api/content", json=payload)
                    assert response.status_code == 200, response.text
                    committed = response.json()
                else:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        pending = executor.submit(client.post, "/api/content", json=payload)
                        assert channel.poll(10), "write did not reach the uncommitted barrier"
                        assert channel.recv() == "uncommitted"
                        with domain_db.transaction() as session:
                            assert (
                                session.scalar(select(func.count()).select_from(ContentEntry)) == 0
                            )
                            assert (
                                session.scalar(select(func.count()).select_from(ContentSaveReceipt))
                                == 0
                            )
                        process.kill()
                        with pytest.raises(httpx.RemoteProtocolError):
                            pending.result(timeout=10)
        domain_db.close()
        with worker(settings, fake_cognito, verifier, listener) as (process, _):
            assert process.pid != first_pid
            with httpx.Client(
                base_url=origin, headers=headers, cookies=cookies, timeout=10
            ) as client:
                # The same server-side cookie/session survives a new application process.
                assert client.get("/me").json()["user"]["id"] == str(graph["owner_id"])
                recovery = client.get(f"/api/content-saves/{key}")
                if crash == "after_commit":
                    assert recovery.status_code == 200
                    assert recovery.json() == committed
                else:
                    assert recovery.status_code == 404
                    assert client.get("/api/content").json() == []
                response = client.post("/api/content", json=payload)
                assert response.status_code == 200, response.text
                if crash == "after_commit":
                    assert response.json() == committed
                assert client.post("/api/content", json=payload).json() == response.json()
                assert client.get("/api/content").json() == [response.json()]
        with domain_db.transaction() as session:
            assert session.scalar(select(func.count()).select_from(ContentEntry)) == 1
            assert session.scalar(select(func.count()).select_from(ContentSaveReceipt)) == 1
