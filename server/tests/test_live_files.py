from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from server.app import app
from server.settings import (
    reload_admin_token,
    reload_max_live_file_bytes,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


HTTP_OK = 200
HTTP_NOT_MODIFIED = 304
HTTP_UNAUTHORIZED = 401
HTTP_CONTENT_TOO_LARGE = 413


def build_scope(
    path: str, headers: Iterable[tuple[str, str]] = ()
) -> dict[str, object]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "client": ("test", 0),
        "server": ("testserver", 80),
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
        "app": app,
    }


async def call_live(
    path: str, headers: Iterable[tuple[str, str]] = ()
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    scope = build_scope(f"/live/{path}", headers=headers)
    body_sent = False

    async def receive() -> dict[str, object]:
        nonlocal body_sent
        if body_sent:
            return {"type": "http.disconnect"}
        body_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        events.append(message)

    await app(scope, receive, send)
    return events


def collect_response(
    events: list[dict[str, object]],
) -> tuple[int, dict[str, str], bytes]:
    status = events[0]["status"]
    headers = {
        key.decode().lower(): value.decode() for key, value in events[0]["headers"]
    }
    body = b"".join(event.get("body", b"") for event in events[1:])
    return status, headers, body


@pytest.mark.anyio
async def test_live_file_includes_sha256_etag(files_root: Path):
    path = "tests/etag.txt"
    content = b"etag-me"
    expected_sha = hashlib.sha256(content).hexdigest()

    full_path = files_root / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with full_path.open("wb") as handle:
        handle.write(content)

    events = await call_live(path)
    status, headers, body = collect_response(events)

    assert status == HTTP_OK
    assert "etag" in headers, "ETag header should be present on live file responses"
    assert headers["etag"].strip('"') == expected_sha
    assert body == content


@pytest.mark.anyio
async def test_live_file_returns_304_on_matching_if_none_match(files_root: Path):
    path = "tests/if-none-match.txt"
    content = b"conditional"
    expected_sha = hashlib.sha256(content).hexdigest()

    full_path = files_root / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with full_path.open("wb") as handle:
        handle.write(content)

    preflight = await call_live(path)
    _, headers, _ = collect_response(preflight)
    etag = headers.get("etag", f'"{expected_sha}"')

    events = await call_live(path, headers=[("if-none-match", etag)])
    status, headers, body = collect_response(events)

    assert status == HTTP_NOT_MODIFIED
    assert headers.get("etag") == etag
    assert body == b""

    mismatch_events = await call_live(path, headers=[("if-none-match", '"bogus"')])
    mismatch_status, mismatch_headers, mismatch_body = collect_response(mismatch_events)

    assert mismatch_status == HTTP_OK
    assert mismatch_headers.get("etag") == etag
    assert mismatch_body == content


@pytest.mark.anyio
async def test_live_file_write_requires_configured_admin_token(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "test-admin-token")
    reload_admin_token()
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            missing = await client.put(
                "/api/files/tests/protected.txt",
                content=b"blocked",
            )
            assert missing.status_code == HTTP_UNAUTHORIZED

            invalid = await client.put(
                "/api/files/tests/protected.txt",
                content=b"blocked",
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert invalid.status_code == HTTP_UNAUTHORIZED

            authorized = await client.put(
                "/api/files/tests/protected.txt",
                content=b"allowed",
                headers={"Authorization": "Bearer test-admin-token"},
            )
            assert authorized.status_code == HTTP_OK
            assert authorized.json()["ok"] is True
    finally:
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()


@pytest.mark.anyio
async def test_live_file_write_remains_open_without_configured_token():
    reload_admin_token()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/files/tests/unprotected.txt",
            content=b"allowed",
        )

    assert response.status_code == HTTP_OK
    assert response.json()["ok"] is True


@pytest.mark.anyio
async def test_live_file_write_rejects_body_over_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
    files_root: Path,
):
    monkeypatch.setenv("SWITCHBOARD_MAX_LIVE_FILE_BYTES", "4")
    reload_max_live_file_bytes()
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.put(
                "/api/files/tests/oversized.txt",
                content=b"12345",
            )
        assert response.status_code == HTTP_CONTENT_TOO_LARGE
        assert not (files_root / "tests" / "oversized.txt").exists()
    finally:
        monkeypatch.delenv("SWITCHBOARD_MAX_LIVE_FILE_BYTES", raising=False)
        reload_max_live_file_bytes()
