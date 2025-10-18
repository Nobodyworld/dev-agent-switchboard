from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

from server.app import app
from server.file_store import FILES_ROOT as CONFIGURED_FILES_ROOT

STATIC_ROOT = Path(__file__).resolve().parents[2] / "web" / "static"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

FILES_ROOT = Path(CONFIGURED_FILES_ROOT)
# TODO - Use TemporaryDirectory fixtures so tests never touch shared filesystem state between runs.


@pytest.fixture(autouse=True)
def clean_filesystem():
    """Ensure the live file store is empty before and after each test."""
    if FILES_ROOT.exists():
        shutil.rmtree(FILES_ROOT)
    FILES_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        if FILES_ROOT.exists():
            shutil.rmtree(FILES_ROOT)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def build_scope(path: str, headers: Iterable[Tuple[str, str]] = ()) -> Dict:
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


async def call_live(path: str, headers: Iterable[Tuple[str, str]] = ()) -> List[Dict]:
    events: List[Dict] = []
    scope = build_scope(f"/live/{path}", headers=headers)
    body_sent = False

    async def receive() -> Dict:
        nonlocal body_sent
        if body_sent:
            return {"type": "http.disconnect"}
        body_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Dict) -> None:
        events.append(message)

    await app(scope, receive, send)
    return events


def collect_response(events: List[Dict]) -> Tuple[int, Dict[str, str], bytes]:
    status = events[0]["status"]
    headers = {
        key.decode().lower(): value.decode() for key, value in events[0]["headers"]
    }
    body = b"".join(event.get("body", b"") for event in events[1:])
    return status, headers, body


@pytest.mark.anyio
async def test_live_file_includes_sha256_etag():
    path = "tests/etag.txt"
    content = b"etag-me"
    expected_sha = hashlib.sha256(content).hexdigest()

    full_path = FILES_ROOT / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with full_path.open("wb") as handle:
        handle.write(content)

    events = await call_live(path)
    status, headers, body = collect_response(events)

    assert status == 200
    assert "etag" in headers, "ETag header should be present on live file responses"
    assert headers["etag"].strip('"') == expected_sha
    assert body == content


@pytest.mark.anyio
async def test_live_file_returns_304_on_matching_if_none_match():
    path = "tests/if-none-match.txt"
    content = b"conditional"
    expected_sha = hashlib.sha256(content).hexdigest()

    full_path = FILES_ROOT / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with full_path.open("wb") as handle:
        handle.write(content)

    preflight = await call_live(path)
    _, headers, _ = collect_response(preflight)
    etag = headers.get("etag", f'"{expected_sha}"')

    events = await call_live(path, headers=[("if-none-match", etag)])
    status, headers, body = collect_response(events)

    assert status == 304
    assert headers.get("etag") == etag
    assert body == b""

    mismatch_events = await call_live(path, headers=[("if-none-match", '"bogus"')])
    mismatch_status, mismatch_headers, mismatch_body = collect_response(mismatch_events)

    assert mismatch_status == 200
    assert mismatch_headers.get("etag") == etag
    assert mismatch_body == content
