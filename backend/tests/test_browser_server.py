"""The browser runner must refuse deployment databases before any connection."""

from unittest.mock import Mock

import pytest

from tests.browser_server import main


@pytest.mark.parametrize(
    ("environment", "url"),
    [
        ("production", "postgresql+psycopg://test:test@127.0.0.1/fitfinity_test"),
        ("local", "postgresql+psycopg://test:test@127.0.0.1/fitfinity_test"),
        ("test", "postgresql+psycopg://test:test@127.0.0.1/fitfinity_local"),
        ("test", "postgresql://test:test@127.0.0.1/fitfinity_test"),
        ("test", "postgresql+psycopg://fitfinity_test:test@production.example/fitfinity_test"),
        ("test", "postgresql+psycopg://fitfinity_test:test@127.0.0.1/fitfinity_test"),
        ("test", "postgresql+psycopg://production:test@test-db/fitfinity_test"),
        ("test", "postgresql+psycopg://fitfinity_test:test@test-db/fitfinity_test?host=other"),
    ],
)
def test_browser_harness_refuses_non_test_configuration_before_connect(
    monkeypatch, environment, url
):
    connection = Mock(side_effect=AssertionError("No database connection is allowed"))
    monkeypatch.setattr("tests.browser_server.psycopg.connect", connection)
    monkeypatch.setenv("FITFINITY_ENVIRONMENT", environment)
    monkeypatch.setenv("FITFINITY_TEST_DATABASE_URL", url)
    with pytest.raises(ValueError, match="(isolated fitfinity_test|explicit test environment)"):
        main()
    connection.assert_not_called()


def test_worker_requests_reuse_only_their_own_application():
    """Concurrent scenario catalogues must not share review versions or authentication state."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from tests.browser_server import WorkerApplications

    created = []

    def factory():
        records = []
        created.append(records)

        async def records_route(request):
            if request.method == "POST":
                records.append(await request.json())
            return JSONResponse(records)

        return Starlette(routes=[Route("/records", records_route, methods=["GET", "POST"])])

    with TestClient(WorkerApplications(factory(), factory)) as client:
        first = {"X-Fitfinity-Browser-Worker": "0"}
        other = {"X-Fitfinity-Browser-Worker": "1"}
        assert client.post("/records", headers=first, json={"id": "owned"}).json() == [
            {"id": "owned"}
        ]
        assert client.get("/records", headers=other).json() == []
        assert client.get("/records", headers=first).json() == [{"id": "owned"}]
        assert len(created) == 3


@pytest.mark.parametrize("worker", ["", "-1", "256", "1,2"])
def test_invalid_worker_never_allocates_an_application(worker):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from tests.browser_server import WorkerApplications

    factory = Mock(side_effect=AssertionError("Invalid scope must never allocate a database"))
    with TestClient(WorkerApplications(Starlette(), factory)) as client:
        assert (
            client.get("/api/directory", headers={"X-Fitfinity-Browser-Worker": worker}).status_code
            == 400
        )
    factory.assert_not_called()
