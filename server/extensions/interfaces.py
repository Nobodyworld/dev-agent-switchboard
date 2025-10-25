"""Interfaces shared by Switchboard extensions and runtime instrumentation."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from fastapi import FastAPI

if True:  # pragma: no cover - typing imports for documentation clarity
    try:
        from server.domain import (
            Agent,
            CheckoutResult,
            CompletionResult,
            HeartbeatResult,
            TaskRecord,
        )
    except Exception:  # pragma: no cover - import-time guards for optional typing
        Agent = Any  # type: ignore[assignment]
        CheckoutResult = Any  # type: ignore[assignment]
        CompletionResult = Any  # type: ignore[assignment]
        HeartbeatResult = Any  # type: ignore[assignment]
        TaskRecord = Any  # type: ignore[assignment]


TaskEventCoroutine = Awaitable[None]
TaskEventCallable = Callable[..., TaskEventCoroutine | None]
StartupHook = Callable[[FastAPI], Awaitable[None] | None]


class SupportsTaskEvents(Protocol):
    """Protocol implemented by task lifecycle hooks."""

    async def on_checkout(self, *, agent: Agent, result: CheckoutResult) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_complete(self, *, agent_id: str, result: CompletionResult) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_heartbeat(self, *, agent_id: str, result: HeartbeatResult) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_abandon(self, *, agent_id: str, result: HeartbeatResult) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_task_created(self, *, task: TaskRecord) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_task_updated(self, *, task: TaskRecord) -> None:  # pragma: no cover - protocol definition
        ...


@dataclass(frozen=True)
class ExtensionDescriptor:
    """Metadata describing an extension for operator discovery."""

    name: str
    capabilities: tuple[str, ...] = ()
    version: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExtensionBundle:
    """Frozen set of runtime hooks registered by extensions."""

    task_hooks: tuple[object, ...] = ()
    startup_hooks: tuple[StartupHook, ...] = ()
    descriptors: tuple[ExtensionDescriptor, ...] = ()

    async def emit(self, event: str, **payload: Any) -> None:
        """Invoke ``event`` across registered task hooks."""

        if not self.task_hooks:
            return
        for hook in self.task_hooks:
            callback = getattr(hook, event, None)
            if callback is None:
                continue
            result = callback(**payload)
            if inspect.isawaitable(result):
                await result

    def attach(self, app: FastAPI) -> None:
        """Register startup hooks on ``app`` and return immediately."""

        for hook in self.startup_hooks:
            async def runner(h: StartupHook = hook) -> None:  # pragma: no cover - async closure
                outcome = h(app)
                if inspect.isawaitable(outcome):
                    await outcome

            app.add_event_handler("startup", runner)


class ExtensionLoadError(RuntimeError):
    """Raised when an extension fails to load or register."""


class ExtensionRegistry:
    """Registry exposed to extensions during startup."""

    def __init__(self) -> None:
        self._task_hooks: list[object] = []
        self._startup_hooks: list[StartupHook] = []
        self._descriptors: list[ExtensionDescriptor] = []

    def register_task_hook(self, hook: object) -> None:
        """Register a hook object for task lifecycle notifications."""

        self._task_hooks.append(hook)

    def register_startup_hook(self, hook: StartupHook) -> None:
        """Register a callable executed during FastAPI startup."""

        self._startup_hooks.append(hook)

    def register_extension(self, descriptor: ExtensionDescriptor) -> None:
        """Expose extension metadata for discovery endpoints."""

        self._descriptors.append(descriptor)

    def freeze(self) -> ExtensionBundle:
        """Return an immutable snapshot of registered hooks."""

        return ExtensionBundle(
            task_hooks=tuple(self._task_hooks),
            startup_hooks=tuple(self._startup_hooks),
            descriptors=tuple(self._descriptors),
        )
