from contextlib import contextmanager

from starlette.testclient import TestClient

from server.app import app
from server.middleware import get_current_rate_limit_middleware
from server.settings import (
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_TRUSTED_ENV,
    RATE_LIMIT_WINDOW_ENV,
    reload_rate_limit_settings,
)


def _configure_limit(monkeypatch, *, requests: int, window: int, trusted: str = "") -> None:
    monkeypatch.setenv(RATE_LIMIT_REQUESTS_ENV, str(requests))
    monkeypatch.setenv(RATE_LIMIT_WINDOW_ENV, str(window))
    if trusted:
        monkeypatch.setenv(RATE_LIMIT_TRUSTED_ENV, trusted)
    else:
        monkeypatch.delenv(RATE_LIMIT_TRUSTED_ENV, raising=False)
    reload_rate_limit_settings()


@contextmanager
def _client_with_reset():
    with TestClient(app) as client:
        middleware = get_current_rate_limit_middleware()
        assert middleware is not None, "Rate limit middleware should be initialized"
        middleware.reset()
        yield client


def test_rate_limit_enforced(monkeypatch):
    _configure_limit(monkeypatch, requests=2, window=60)
    with _client_with_reset() as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        response = client.get("/health")
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"


def test_rate_limit_trusted_bypass(monkeypatch):
    _configure_limit(monkeypatch, requests=1, window=60, trusted="testclient")
    with _client_with_reset() as client:
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200
