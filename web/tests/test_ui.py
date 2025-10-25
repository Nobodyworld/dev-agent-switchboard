from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Error as PlaywrightError, expect, sync_playwright
except ImportError:  # pragma: no cover - handled by skip
    pytest.skip(
        "playwright is required for UI tests",
        allow_module_level=True,
    )  # type: ignore[arg-type]


HTTP_OK = 200
SERVER_WAIT_INTERVAL = 0.2

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(base_url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    health_url = f"{base_url}/health"
    while time.time() < deadline:
        try:
            with contextlib.closing(
                urllib.request.urlopen(health_url, timeout=1)  # noqa: S310
            ) as resp:
                if resp.status == HTTP_OK:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(SERVER_WAIT_INTERVAL)
    raise RuntimeError("Timed out waiting for UI server")


@pytest.fixture(scope="session")
def app_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    db_path = ROOT / "switchboard.db"
    if db_path.exists():
        db_path.unlink()
    storage_root = ROOT / "storage"
    if storage_root.exists():
        shutil.rmtree(storage_root)

    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{existing}" if existing else str(ROOT)

    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_server(base_url)
    except Exception:
        process.terminate()
        with contextlib.suppress(ProcessLookupError):
            process.wait(timeout=5)
        raise

    yield base_url

    process.terminate()
    with contextlib.suppress(ProcessLookupError):
        process.wait(timeout=10)


def test_task_lifecycle_with_feedback(app_server: str) -> None:  # noqa: PLR0915 - E2E smoke covers many interactions
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except PlaywrightError as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip(
                    "Playwright browsers are not installed; run 'playwright install'."
                )
            raise
        page = browser.new_page()
        try:
            page.goto(f"{app_server}/", wait_until="domcontentloaded")

            page.wait_for_selector("#tasks")

            def fail_once(route, _request):
                route.fulfill(status=500, body="intentional failure")
                page.unroute("**/api/tasks", fail_once)

            page.route("**/api/tasks", fail_once)

            page.fill('input[name="title"]', "Broken task")
            page.click('button:has-text("Add")')
            toast = page.wait_for_selector('.toast', timeout=5000)
            expect(toast).to_contain_text("Request POST /api/tasks failed")

            page.fill('input[name="title"]', "Task A")
            page.fill('textarea[name="description"]', "Root work")
            page.fill('input[name="depends_on"]', "")
            page.click('button:has-text("Add")')
            page.wait_for_selector('.toast:has-text("Task created successfully.")')
            page.wait_for_selector('tr:has-text("Task A")')

            page.fill('input[name="title"]', "Task B")
            page.fill('textarea[name="description"]', "")
            page.fill('input[name="depends_on"]', "1")
            page.click('button:has-text("Add")')
            page.wait_for_selector('.toast:has-text("Task created successfully.")')
            page.wait_for_selector('tr:has-text("Task B")')

            page.wait_for_function(
                "el => !el.classList.contains('hidden')",
                page.locator('#planMeta'),
            )
            expect(page.locator('#planVersion')).not_to_have_text('—')
            expect(page.locator('#planUpdated')).not_to_have_text('—')

            dep_chip = page.locator('tr:has-text("Task B") .tooltip-chip').first
            expect(dep_chip).to_be_visible()
            tooltip = dep_chip.get_attribute('data-tooltip')
            assert tooltip and "Task A (#1)" in tooltip

            dialog_messages = []

            def handle_dialog(dialog):
                dialog_messages.append(dialog.message)
                dialog.accept()

            page.on("dialog", handle_dialog)
            try:
                page.click('tr:has-text("Task B") [data-action="complete"]')
                page.wait_for_selector('.toast:has-text("Task #2 marked complete.")')

                page.click('tr:has-text("Task B") [data-action="delete"]')
                page.wait_for_selector('.toast:has-text("Task #2 deleted.")')
                page.wait_for_selector('tr:has-text("Task B")', state="detached")
            finally:
                page.off("dialog", handle_dialog)

            assert any("Mark task" in msg for msg in dialog_messages)
            assert any("Delete task" in msg for msg in dialog_messages)

            expect(page.locator('tr:has-text("Task A")')).to_be_visible()
        finally:
            browser.close()
