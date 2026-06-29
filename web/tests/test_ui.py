from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Error as PlaywrightError, expect, sync_playwright
except ImportError:  # pragma: no cover - handled by skip
    pytest.skip(
        "playwright is required for UI tests",
        allow_module_level=True,
    )


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


def _launch_browser_or_skip(playwright) -> object:
    try:
        return playwright.chromium.launch(headless=True)
    except PlaywrightError as exc:
        missing_browser = "Executable doesn't exist" in str(exc)
        strict = os.getenv("SWITCHBOARD_STRICT_PLAYWRIGHT") == "1"
        if missing_browser and strict:
            pytest.fail(
                "Playwright Chromium is missing while strict UI validation is enabled. "
                "Run 'python -m playwright install chromium'."
            )
        if missing_browser:
            pytest.skip(
                "Playwright browsers are not installed; run 'playwright install'."
            )
        raise


@pytest.fixture(scope="function")
def app_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str, None, None]:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    runtime_root = tmp_path_factory.mktemp("ui-runtime")
    db_path = runtime_root / "switchboard.db"
    storage_root = runtime_root / "storage"

    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{existing}" if existing else str(ROOT)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    env["STORAGE_ROOT"] = str(storage_root)
    env["FILES_ROOT"] = str(storage_root / "files")

    process = subprocess.Popen(  # - test harness launches local uvicorn
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
        stderr = ""
        if process.stderr is not None:
            with contextlib.suppress(Exception):
                stderr = process.stderr.read().decode("utf-8", errors="replace")
        process.terminate()
        with contextlib.suppress(ProcessLookupError):
            process.wait(timeout=5)
        if stderr.strip():
            raise RuntimeError(
                f"Timed out waiting for UI server: {stderr.strip()}"
            ) from None
        raise

    yield base_url

    process.terminate()
    with contextlib.suppress(ProcessLookupError):
        process.wait(timeout=10)


@pytest.fixture(scope="function")
def browser() -> Generator[object, None, None]:
    with sync_playwright() as p:
        launched = _launch_browser_or_skip(p)
        try:
            yield launched
        finally:
            launched.close()


def test_task_lifecycle_with_feedback(  # noqa: PLR0915
    app_server: str,
    browser: object,
) -> None:
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
        expect(page.locator(".toast")).to_contain_text("Request POST /api/tasks failed")

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
            "() => {"
            "const meta = document.querySelector('#planMeta');"
            "return !!meta && !meta.classList.contains('hidden');"
            "}"
        )
        expect(page.locator("#planVersion")).not_to_have_text("—")
        expect(page.locator("#planUpdated")).not_to_have_text("—")

        page.wait_for_function(
            "() => document.querySelector('#analyticsSummary') && "
            "document.querySelector('#analyticsSummary').textContent."
            "includes('2 tasks')"
        )
        expect(page.locator("#analyticsCards")).to_contain_text("Ready")

        dep_chip = page.locator('tr:has-text("Task B") .tooltip-chip').first
        expect(dep_chip).to_be_visible()
        tooltip = dep_chip.get_attribute("data-tooltip")
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
            page.remove_listener("dialog", handle_dialog)

        assert any("Mark task" in msg for msg in dialog_messages)
        assert any("Delete task" in msg for msg in dialog_messages)

        expect(page.locator('tr:has-text("Task A")')).to_be_visible()

        page.click("#toggleDiagnostics")
        page.wait_for_selector("#diagnosticsPanel:not(.hidden)")
        page.wait_for_selector("#diagnosticsPackages tr")
        expect(page.locator("#diagnosticsPackages")).to_contain_text("fastapi")
        summary = page.locator("#diagnosticsSummary")
        expect(summary).not_to_have_text("Diagnostics have not been loaded yet.")
    finally:
        page.close()


def test_two_agent_dependency_flow_updates_dashboard(
    app_server: str,
    browser: object,
) -> None:
    page = browser.new_page()
    try:
        page.goto(f"{app_server}/", wait_until="domcontentloaded")
        page.wait_for_selector("#tasks")

        task_ids = page.evaluate("""async () => {
                                        const jsonHeaders = {
                                            'Content-Type': 'application/json',
                                        };
                                        const postJson = async (url, payload) => {
                                            const response = await fetch(url, {
                                                method: 'POST',
                                                headers: jsonHeaders,
                                                body: JSON.stringify(payload),
                                            });
                                            if (!response.ok) {
                                                const msg =
                                                    `${url} failed with ` +
                                                    `${response.status}`;
                                                throw new Error(
                                                    msg
                                                );
                                            }
                                            return response.json();
                                        };

                                        await postJson('/api/agents', {
                                            agent_name: 'agent-one',
                                        });
                                        await postJson('/api/agents', {
                                            agent_name: 'agent-two',
                                        });

                                        const taskA = await postJson('/api/tasks', {
                                            title: 'Task A',
                                            description: 'Ready root task',
                                            depends_on: [],
                                        });
                                        const taskB = await postJson('/api/tasks', {
                                            title: 'Task B',
                                            description: 'Unlocks after Task A',
                                            depends_on: [taskA.id],
                                        });

                                        return { taskAId: taskA.id, taskBId: taskB.id };
                                }""")

        page.wait_for_selector('tr:has-text("Task A")')
        page.wait_for_selector('tr:has-text("Task B")')
        page.wait_for_function(
            "() => {"
            "const summary = document.querySelector('#analyticsSummary');"
            "return !!summary && summary.textContent.includes('1 blocked');"
            "}"
        )
        initial_version = page.locator("#planVersion").inner_text()

        results = page.evaluate(
            """async ({ taskAId }) => {
                                        const post = async (url, body = undefined) => {
                                            const options = { method: 'POST' };
                                            if (body !== undefined) {
                                                options.headers = {
                                                    'Content-Type': 'application/json',
                                                };
                                                options.body = JSON.stringify(body);
                                            }
                                            const response = await fetch(url, options);
                                            if (!response.ok) {
                                                const msg =
                                                    `${url} failed with ` +
                                                    `${response.status}`;
                                                throw new Error(
                                                    msg
                                                );
                                            }
                                            return response.json();
                                        };

                                        const firstCheckout = await post(
                                            '/api/tasks/checkout?agent_id=agent-one'
                                        );
                                        const blockedCheckout = await post(
                                            '/api/tasks/checkout?agent_id=agent-two'
                                        );
                                        const heartbeat = await post(
                                            `/api/tasks/${taskAId}/heartbeat?agent_id=agent-one`
                                        );
                                        const completion = await post(
                                            `/api/tasks/${taskAId}/complete?agent_id=agent-one`,
                                            {
                                            notes: 'Task A finished',
                                            }
                                        );
                                        const secondCheckout = await post(
                                            '/api/tasks/checkout?agent_id=agent-two'
                                        );

                                        return {
                                            firstCheckout,
                                            blockedCheckout,
                                            heartbeat,
                                            completion,
                                            secondCheckout,
                                        };
                                }""",
            task_ids,
        )

        assert results["firstCheckout"]["task"]["id"] == task_ids["taskAId"]
        assert results["blockedCheckout"]["task"] is None
        assert results["blockedCheckout"]["reason"] == "no_available_tasks"
        assert results["heartbeat"] == {"ok": True}
        assert results["completion"]["ok"] is True
        assert results["secondCheckout"]["task"]["id"] == task_ids["taskBId"]

        task_a_row = page.locator("tbody tr").filter(
            has=page.locator(f'td:text-is("{task_ids["taskAId"]}")')
        )
        task_b_row = page.locator("tbody tr").filter(
            has=page.locator(f'td:text-is("{task_ids["taskBId"]}")')
        )

        expect(task_a_row).to_contain_text("completed")
        expect(task_b_row).to_contain_text("in progress")
        expect(page.locator("#analyticsSummary")).to_contain_text("0 blocked")
        expect(page.locator("#analyticsCards")).to_contain_text("Completed")
        expect(page.locator("#analyticsCards")).to_contain_text("In progress")
        expect(page.locator("#planVersion")).not_to_have_text(initial_version)
    finally:
        page.close()
