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
