import asyncio
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.application import build_task_service
from server.db import AsyncSessionLocal
from server.domain import Agent
from server.extensions import (
    ExtensionBundle,
    loader as extension_loader,
    set_extension_bundle,
)
from server.extensions.builtin import task_metrics, webhook_notifier
from server.extensions.interfaces import (
    ExtensionDescriptor,
    ExtensionLoadError,
    ExtensionRegistry,
)
from server.extensions.loader import load_extension_bundle
from server.settings import reload_extension_settings


class RecordingHook:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    async def on_task_created(self, *, task) -> None:
        self.events.append(("created", task.id))

    async def on_checkout(self, *, agent, result) -> None:
        self.events.append(("checkout", result.reason or "ok"))

    async def on_complete(self, *, agent_id, result) -> None:
        self.events.append(("complete", result.ok))

    async def on_task_updated(self, *, task) -> None:
        self.events.append(("updated", task.title))


def test_task_service_emits_extension_events():
    hook = RecordingHook()
    original = set_extension_bundle(
        ExtensionBundle(task_hooks=(hook,), startup_hooks=(), descriptors=())
    )
    async def scenario() -> None:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            created = await service.create_task(title="sample", description="", depends_on=())
            await session.commit()
            checkout = await service.checkout(Agent(agent_id="observer"))
            assert checkout.task is not None
            await service.complete("observer", checkout.task.id)
            await service.update_task(created.id, title="updated", description=None)

    try:
        asyncio.run(scenario())
    finally:
        set_extension_bundle(original)
    assert hook.events[0][0] == "created"
    assert any(event[0] == "checkout" for event in hook.events)
    assert any(event == ("complete", True) for event in hook.events)
    assert any(event[0] == "updated" for event in hook.events)


@pytest.mark.skipif(task_metrics.Counter is None, reason="prometheus_client not installed")
def test_builtin_metrics_hook_increments_counters(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS", "1")
    reload_extension_settings()
    metrics_hook = task_metrics.TaskMetricsHook()
    checkout_counter = task_metrics._CHECKOUT_COUNTER
    completion_counter = task_metrics._COMPLETION_COUNTER
    assert checkout_counter is not None
    assert completion_counter is not None
    before_checkout = {
        sample.labels.get("outcome"): sample.value
        for metric in checkout_counter.collect()
        for sample in metric.samples
        if not sample.name.endswith("_created")
    }
    before_complete = {
        sample.labels.get("outcome"): sample.value
        for metric in completion_counter.collect()
        for sample in metric.samples
        if not sample.name.endswith("_created")
    }
    asyncio.run(
        metrics_hook.on_checkout(
            agent=Agent(agent_id="x"),
            result=SimpleNamespace(task=object(), reason=None),
        )
    )
    asyncio.run(
        metrics_hook.on_complete(
            agent_id="x", result=SimpleNamespace(ok=True)
        )
    )
    after_checkout = {
        sample.labels.get("outcome"): sample.value
        for metric in checkout_counter.collect()
        for sample in metric.samples
        if not sample.name.endswith("_created")
    }
    after_complete = {
        sample.labels.get("outcome"): sample.value
        for metric in completion_counter.collect()
        for sample in metric.samples
        if not sample.name.endswith("_created")
    }
    assert (
        after_checkout.get("granted", 0.0)
        - before_checkout.get("granted", 0.0)
    ) == pytest.approx(1.0)
    assert (
        after_complete.get("completed", 0.0)
        - before_complete.get("completed", 0.0)
    ) == pytest.approx(1.0)
    reload_extension_settings()


def test_webhook_notifier_registers_and_emits(monkeypatch):
    events: list[dict[str, Any]] = []

    class DummyClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):  # pragma: no cover - trivial context manager
            return self

        async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
            return False

        async def post(self, url, json=None, headers=None):
            events.append({"url": url, "json": json, "headers": headers})

    monkeypatch.setenv(webhook_notifier.URL_ENV, "https://example.test/hook")
    monkeypatch.setenv(webhook_notifier.EVENTS_ENV, "on_complete")
    monkeypatch.setenv("SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS", "1")
    monkeypatch.setattr(webhook_notifier.httpx, "AsyncClient", DummyClient)

    registry = ExtensionRegistry()
    webhook_notifier.register(registry)
    bundle = registry.freeze()

    assert any(
        descriptor.name == "builtin.webhook_notifier" for descriptor in bundle.descriptors
    )
    assert any("Webhook notifier" in note for note in bundle.contract.notes)

    hook = next((hook for hook in bundle.task_hooks if isinstance(hook, webhook_notifier.WebhookNotifier)), None)
    assert hook is not None

    asyncio.run(
        hook.on_complete(
            agent_id="agent-1",
            result=SimpleNamespace(ok=True, task=SimpleNamespace(id=5)),
        )
    )

    assert events
    payload = events[0]["json"]
    assert payload["event"] == "on_complete"
    assert payload["data"]["task_id"] == 5


def test_webhook_notifier_rejects_invalid_timeout(monkeypatch):
    monkeypatch.setenv(webhook_notifier.URL_ENV, "https://example.test/hook")
    monkeypatch.setenv(webhook_notifier.TIMEOUT_ENV, "invalid")

    registry = ExtensionRegistry()
    with pytest.raises(ExtensionLoadError):
        webhook_notifier.register(registry)


def test_load_extension_bundle_skips_missing_modules(monkeypatch, caplog):
    monkeypatch.setenv("SWITCHBOARD_EXTENSIONS", "does.not.exist")
    caplog.set_level("WARNING")
    bundle = load_extension_bundle()
    assert any("Unable to import extension module" in record.message for record in caplog.records)
    assert any(descriptor.name == "builtin.task_metrics" for descriptor in bundle.descriptors)


def test_extension_bundle_startup_hooks_execute():
    invoked = {}

    async def hook(app: FastAPI) -> None:
        invoked["app"] = app.title

    bundle = ExtensionBundle(task_hooks=(), startup_hooks=(hook,), descriptors=())
    app = FastAPI()
    bundle.attach(app)
    with TestClient(app):
        pass
    assert invoked["app"] == app.title


def test_truthy_helper_parses_variants():
    assert extension_loader._truthy("TRUE") is True  # type: ignore[attr-defined]
    assert extension_loader._truthy("off") is False  # type: ignore[attr-defined]
    assert extension_loader._truthy(None, default=True) is True  # type: ignore[attr-defined]


def test_normalize_modules_deduplicates_and_strips():
    result = extension_loader._normalize_modules(  # type: ignore[attr-defined]
        ["  alpha ", "beta", "alpha", ""]
    )
    assert result == ("alpha", "beta")


def test_load_extension_bundle_with_explicit_modules(monkeypatch):
    module_name = "ext.sample"

    def register_extension(registry):
        registry.register_extension(ExtensionDescriptor(name=module_name))
        registry.register_startup_hook(lambda app: None)

    module = ModuleType(module_name)
    module.register_extension = register_extension
    monkeypatch.setitem(sys.modules, module_name, module)
    bundle = load_extension_bundle(
        modules=(module_name,),
        enable_builtin=False,
    )
    assert any(descriptor.name == module_name for descriptor in bundle.descriptors)


def test_load_extension_bundle_warns_without_registrar(monkeypatch, caplog):
    module_name = "ext.missing"
    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)
    caplog.set_level("WARNING")
    bundle = load_extension_bundle(modules=(module_name,), enable_builtin=False)
    assert not bundle.descriptors
    assert any("does not expose register_extension" in record.message for record in caplog.records)


def test_load_extension_bundle_propagates_extension_errors(monkeypatch):
    module_name = "ext.error"

    def register_extension(registry):
        raise ExtensionLoadError("boom")

    module = ModuleType(module_name)
    module.register_extension = register_extension
    monkeypatch.setitem(sys.modules, module_name, module)
    with pytest.raises(ExtensionLoadError):
        load_extension_bundle(modules=(module_name,), enable_builtin=False)


def test_load_extension_bundle_skips_generic_failures(monkeypatch, caplog):
    module_name = "ext.generic"

    def register_extension(registry):
        raise RuntimeError("explode")

    module = ModuleType(module_name)
    module.register_extension = register_extension
    monkeypatch.setitem(sys.modules, module_name, module)
    caplog.set_level("ERROR")
    bundle = load_extension_bundle(modules=(module_name,), enable_builtin=False)
    assert not any(descriptor.name == module_name for descriptor in bundle.descriptors)
    assert any("failed during registration" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_extension_bundle_emit_handles_missing_callbacks():
    bundle = ExtensionBundle(task_hooks=(object(),))
    await bundle.emit("nonexistent", payload="value")


@pytest.mark.asyncio
async def test_extension_bundle_emit_awaits_coroutines():
    calls: list[str] = []

    class Hook:
        async def on_event(self, payload: str) -> None:
            calls.append(payload)

    bundle = ExtensionBundle(task_hooks=(Hook(),))
    await bundle.emit("on_event", payload="value")
    assert calls == ["value"]
