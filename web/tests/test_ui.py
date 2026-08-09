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
EXPECTED_PUBLICATION_DIALOGS = 2

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

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "web.tests.ui_test_app:app",
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

        task_script = """async () => {
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
                                }"""
        task_ids = page.evaluate(task_script)

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


def _post_json(page, url: str, payload: dict | None = None) -> dict:
    return page.evaluate(
        """async ({ url, payload }) => {
            const options = { method: 'POST' };
            if (payload !== null) {
                options.headers = { 'Content-Type': 'application/json' };
                options.body = JSON.stringify(payload);
            }
            const response = await fetch(url, options);
            const body = await response.json();
            if (!response.ok) {
                const detail = JSON.stringify(body);
                throw new Error(`${url}: ${response.status} ${detail}`);
            }
            return body;
        }""",
        {"url": url, "payload": payload},
    )


def _put_json(page, url: str, payload: dict) -> dict:
    return page.evaluate(
        """async ({ url, payload }) => {
            const response = await fetch(url, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const body = await response.json();
            if (!response.ok) {
                const detail = JSON.stringify(body);
                throw new Error(`${url}: ${response.status} ${detail}`);
            }
            return body;
        }""",
        {"url": url, "payload": payload},
    )


def test_validation_broker_operator_workflow_is_accessible_and_responsive(  # noqa: PLR0915
    app_server: str,
    browser: object,
) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    console_errors: list[str] = []
    page.on(
        "console",
        lambda message: (
            console_errors.append(message.text)
            if message.type == "error" and "status of 409" not in message.text
            else None
        ),
    )
    try:
        page.goto(f"{app_server}/", wait_until="domcontentloaded")
        expect(page.locator("h1")).to_have_text("Switchboard")
        expect(page.locator("#validation-broker-heading")).to_have_text(
            "Validation Broker"
        )
        expect(page.locator("#validation-broker")).to_be_visible()
        page.wait_for_function(
            "() => document.querySelector('#brokerStatus')?.textContent"
            ".includes('refreshed')"
        )
        page.evaluate(
            "() => localStorage.setItem('switchboardAdminToken', 'ui-admin-sentinel')"
        )
        page.click("#refreshBroker")
        page.wait_for_function(
            "() => document.querySelector('#brokerStatus')?.textContent"
            ".includes('refreshed')"
        )
        assert "ui-admin-sentinel" not in page.locator("body").inner_text()
        assert "ui-admin-sentinel" not in page.locator("body").inner_html()

        worker_base = {
            "display_name": "Synthetic local worker",
            "operating_system": "linux",
            "architecture": "x86_64",
            "python_version": "3.11.14",
            "node_version": None,
            "docker_available": False,
            "browsers": [],
            "gpu_available": False,
            "unity_available": False,
            "desktop_available": False,
            "capabilities": {},
            "max_concurrency": 1,
            "network_policy_capability": "worker_restricted",
            "repository_write_capability": False,
            "status": "online",
        }
        _post_json(
            page,
            "/api/execution/workers",
            {
                **worker_base,
                "worker_id": "ui-worker-cheap",
                "display_name": "Local small",
                "browsers": ["chromium"],
                "capabilities": {
                    "internal_marker": "not-for-operator-ui",
                },
            },
        )
        _post_json(
            page,
            "/api/execution/workers",
            {
                **worker_base,
                "worker_id": "ui-worker-expensive",
                "display_name": "Local large",
            },
        )
        _post_json(
            page,
            "/api/execution/workers",
            {
                **worker_base,
                "worker_id": "ui-worker-new",
                "display_name": "Local reserve",
            },
        )
        for worker_id, cost in (("ui-worker-cheap", 3), ("ui-worker-expensive", 9)):
            _post_json(
                page,
                "/api/execution/routing-profiles",
                {
                    "schema_version": 1,
                    "worker_id": worker_id,
                    "enabled": True,
                    "estimated_cost_units_per_run": cost,
                    "quota_capacity_units": 20,
                    "quota_remaining_units": 20,
                    "quota_reset_at": (
                        "2026-08-10T12:00:00Z"
                        if worker_id == "ui-worker-cheap"
                        else None
                    ),
                    "routing_priority": 0,
                },
            )
            _post_json(page, "/api/execution/checkout", {"worker_id": worker_id})
        _post_json(page, "/api/execution/checkout", {"worker_id": "ui-worker-new"})

        page.click("#refreshBroker")
        page.wait_for_selector('[data-worker-id="ui-worker-cheap"]')
        expect(page.locator("#brokerWorkers")).to_contain_text("Local small")
        expect(page.locator("#brokerWorkers")).to_contain_text("3")
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "online"
        )
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "active"
        )
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "linux / x86_64"
        )
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "0 active / 1 maximum"
        )
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "Last heartbeat"
        )
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "Last checkout poll"
        )
        expect(page.locator('[data-worker-id="ui-worker-cheap"]')).to_contain_text(
            "enabled"
        )
        cheap_worker_card = page.locator('[data-worker-id="ui-worker-cheap"]')
        expect(cheap_worker_card).to_contain_text("Python")
        expect(cheap_worker_card).to_contain_text("3.11.14")
        expect(cheap_worker_card).to_contain_text("Node")
        expect(cheap_worker_card).to_contain_text("Not reported")
        expect(cheap_worker_card).to_contain_text("Docker")
        expect(cheap_worker_card).to_contain_text("Unavailable")
        expect(cheap_worker_card).to_contain_text("Browsers")
        expect(cheap_worker_card).to_contain_text("chromium")
        expect(cheap_worker_card).to_contain_text("GPU")
        expect(cheap_worker_card).to_contain_text("Unity")
        expect(cheap_worker_card).to_contain_text("Desktop automation")
        expect(cheap_worker_card).to_contain_text("worker restricted")
        expect(cheap_worker_card).to_contain_text("Repository writes")
        expect(cheap_worker_card).to_contain_text("Disabled")
        expect(cheap_worker_card).to_contain_text("Quota reset")
        expect(cheap_worker_card).to_contain_text("2026")
        expensive_worker_card = page.locator('[data-worker-id="ui-worker-expensive"]')
        expect(expensive_worker_card).to_contain_text("Quota reset")
        expect(expensive_worker_card).to_contain_text("Not scheduled")
        assert "internal_marker" not in page.locator("#brokerWorkers").inner_text()
        assert "not-for-operator-ui" not in page.locator("#brokerWorkers").inner_text()

        page.select_option("#profileWorker", "ui-worker-new")
        page.fill("#profileCost", "12")
        page.fill("#profilePriority", "2")
        page.fill("#profileCapacity", "20")
        page.fill("#profileRemaining", "15")
        page.click('#routingProfileForm button[type="submit"]')
        expect(page.locator("#profileStatus")).to_contain_text("revision 1")
        page.fill("#profileRemaining", "14")
        page.once("dialog", lambda dialog: dialog.accept())
        page.click("#resetProfileQuota")
        expect(page.locator("#profileStatus")).to_contain_text("Editing revision 2")
        expect(page.locator("#profileRemaining")).to_have_value("14")

        page.click('[data-profile-edit="ui-worker-cheap"]')
        expect(page.locator("#profileRevision")).to_have_value("1")
        page.fill("#profileCost", "4")
        page.click('#routingProfileForm button[type="submit"]')
        expect(page.locator("#profileStatus")).to_contain_text("revision 2")

        _put_json(
            page,
            "/api/execution/routing-profiles/ui-worker-cheap",
            {
                "expected_revision": 2,
                "enabled": True,
                "estimated_cost_units_per_run": 3,
                "quota_capacity_units": 20,
                "quota_remaining_units": 20,
                "quota_reset_at": None,
                "routing_priority": 0,
            },
        )
        page.fill("#profileCost", "5")
        page.click('#routingProfileForm button[type="submit"]')
        expect(page.locator("#profileStatus")).to_contain_text("conflicted")
        expect(page.locator("#profileRevision")).to_have_value("3")

        page.fill("#validationRepository", "missing-owner")
        page.fill("#validationPullRequest", "0")
        page.fill("#validationCostCeiling", "-1")
        page.fill("#validationQuotaUnits", "-1")
        assert not page.locator("#validationRequestForm").evaluate(
            "form => form.checkValidity()"
        )
        assert page.locator("#validationReusePolicy option").evaluate_all(
            "options => options.map(option => option.value)"
        ) == ["never", "allow_exact", "require_exact"]
        assert page.locator("#validationRoutingPolicy option").evaluate_all(
            "options => options.map(option => option.value)"
        ) == ["first_available", "cheapest_capable"]

        page.fill("#validationRepository", "Nobodyworld/dev-agent-switchboard")
        page.fill("#validationPullRequest", "137")
        page.fill("#validationCostCeiling", "")
        page.select_option("#validationReusePolicy", "never")
        page.select_option("#validationRoutingPolicy", "cheapest_capable")
        page.fill("#validationQuotaUnits", "1")
        page.click('#validationRequestForm button[type="submit"]')
        page.wait_for_function(
            "() => document.querySelector('#brokerRequestDetail')?.textContent"
            ".includes('7d3a91c')"
        )
        request_detail = page.locator("#brokerRequestDetail")
        expect(request_detail).to_contain_text("pending approval")
        expect(
            request_detail.locator("dt", has_text="Repository").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_have_text("Nobodyworld/dev-agent-switchboard")
        expect(
            request_detail.locator("dt", has_text="Pull request").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_have_text("#137")
        expect(
            request_detail.locator("dt", has_text="Reuse policy").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_contain_text("never")
        expect(
            request_detail.locator("dt", has_text="Routing policy").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_contain_text("cheapest capable")
        page.click('[data-request-action="approve-queue"]')
        page.wait_for_function(
            "() => document.querySelector('#brokerRequestDetail')?.textContent"
            ".includes('queued')"
        )
        expect(page.locator("#brokerRequestDetail")).to_contain_text("ui-worker-cheap")
        expect(page.locator("#brokerRequestDetail")).to_contain_text("routing selected")
        expect(page.locator("#brokerRequestDetail")).to_contain_text(
            "Eligible candidates"
        )
        expect(page.locator("#brokerRequestDetail")).to_contain_text("Not applied")
        first_request_id = page.evaluate(
            "() => Number(document.querySelector('[data-history-request]')"
            "?.dataset.historyRequest)"
        )
        fresh = _post_json(page, f"/__test__/complete/{first_request_id}")
        assert fresh["reuse_decision"] == "fresh"
        page.click("#refreshRequest")
        page.wait_for_function(
            "() => document.querySelector('#brokerRequestDetail')?.textContent"
            ".includes('succeeded')"
        )
        fresh_detail = page.locator("#brokerRequestDetail")
        expect(fresh_detail).to_contain_text("1 required / 1 reserved")
        expect(fresh_detail).to_contain_text("consumed")
        expect(fresh_detail).to_contain_text("Measured duration")
        expect(fresh_detail).to_contain_text("7 s")
        expect(fresh_detail).to_contain_text("Cleanup")
        expect(fresh_detail).to_contain_text("succeeded")
        expect(
            fresh_detail.locator("dt", has_text="Reuse decision").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_contain_text("fresh")

        dialogs: list[str] = []

        def accept_dialog(dialog) -> None:
            dialogs.append(dialog.message)
            dialog.accept()

        page.on("dialog", accept_dialog)
        page.click('[data-request-action="publish"]')
        page.wait_for_function(
            "() => document.querySelector('#brokerRequestDetail')?.textContent"
            ".includes('published current')"
        )
        expect(page.locator("#brokerRequestDetail")).to_contain_text("current")

        page.select_option("#validationReusePolicy", "allow_exact")
        page.click('#validationRequestForm button[type="submit"]')
        page.wait_for_function(
            "() => document.querySelectorAll('[data-history-request]').length === 2"
        )
        page.click('[data-request-action="approve-queue"]')
        second_request_id = page.evaluate(
            "() => Number(document.querySelector('[data-history-request]')"
            "?.dataset.historyRequest)"
        )
        assert second_request_id != first_request_id
        reused = _post_json(page, f"/__test__/complete/{second_request_id}")
        assert reused["reuse_decision"] == "reused"
        _post_json(page, f"/__test__/github/head/{'c' * 40}")
        page.click("#refreshRequest")
        page.wait_for_function(
            "() => !document.querySelector('[data-request-action=publish]')?.disabled"
        )
        reused_detail = page.locator("#brokerRequestDetail")
        expect(reused_detail).to_contain_text("reused")
        expect(reused_detail).to_contain_text(f"#{fresh['run_id']}")
        expect(reused_detail).to_contain_text(fresh["evidence_fingerprint"])
        expect(reused_detail).to_contain_text("Executed steps")
        expect(reused_detail).to_contain_text("0")
        expect(
            reused_detail.locator("dt", has_text="Reuse policy").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_contain_text("allow exact")
        expect(
            reused_detail.locator("dt", has_text="Reuse decision").locator(
                "xpath=following-sibling::dd[1]"
            )
        ).to_contain_text("reused")
        page.click('[data-request-action="publish"]')
        page.wait_for_function(
            "() => document.querySelector('#brokerRequestDetail')?.textContent"
            ".includes('published stale')"
        )
        assert len(dialogs) == EXPECTED_PUBLICATION_DIALOGS

        page.click("#refreshBroker")
        page.wait_for_function(
            "() => document.querySelector('#brokerHistory')?.textContent"
            ".includes('reused')"
        )
        expect(page.locator("#brokerHistory")).to_contain_text("fresh")
        expect(page.locator("#brokerHistory")).to_contain_text("reused")
        expect(page.locator("#brokerHistory")).to_contain_text("published current")
        expect(page.locator("#brokerHistory")).to_contain_text("published stale")
        expect(page.locator("#brokerMetrics")).to_contain_text(
            "Deterministic executions avoided"
        )
        expect(page.locator("#brokerMetrics")).to_contain_text(
            "Reference execution time avoided"
        )
        expect(
            page.locator("#brokerMetrics .broker-metric").first.locator("dd")
        ).to_have_text("1")

        page.select_option("#historyReuseDecision", "reused")
        page.click('#brokerHistoryFilters button[type="submit"]')
        page.wait_for_function(
            "() => document.querySelectorAll('#brokerHistory tbody tr').length === 1"
        )
        expect(page.locator("#brokerHistory")).to_contain_text("reused")

        page.locator("#validationRepository").focus()
        page.keyboard.press("Tab")
        assert (
            page.evaluate("() => document.activeElement?.id") == "validationPullRequest"
        )
        expect(page.locator('[data-request-action="approve-queue"]')).to_be_disabled()
        assert "pending" in (
            page.locator('[data-request-action="approve-queue"]').get_attribute("title")
            or ""
        )

        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator("#validation-broker")).to_be_visible()
        overflow_script = """() => ({
                contained: document.documentElement.scrollWidth <= window.innerWidth,
                offenders: [...document.querySelectorAll('body *')]
                    .filter(
                        (node) => node.getBoundingClientRect().right
                            > window.innerWidth + 1
                    )
                    .slice(0, 10)
                    .map((node) => ({
                        tag: node.tagName,
                        id: node.id,
                        className: String(node.className),
                        right: node.getBoundingClientRect().right,
                    })),
            })"""
        overflow = page.evaluate(overflow_script)
        assert overflow["contained"], overflow["offenders"]
        assert "ui-admin-sentinel" not in page.url
        assert all("ui-admin-sentinel" not in message for message in console_errors)
        page.evaluate(
            "() => document.querySelectorAll('.toast.is-visible')"
            ".forEach((toast) => toast.click())"
        )
        expect(page.locator(".toast.is-visible")).to_have_count(0)
        assert console_errors == []
    finally:
        page.close()
