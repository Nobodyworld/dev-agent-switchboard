"""Interfaces shared by Switchboard extensions and runtime instrumentation."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI

if TYPE_CHECKING:  # pragma: no cover - typing imports for documentation clarity
    from server.domain import (
        Agent,
        CheckoutResult,
        CompletionResult,
        HeartbeatResult,
        TaskRecord,
    )
else:  # pragma: no cover - runtime fallbacks keep optional dependencies optional
    Agent = Any
    CheckoutResult = Any
    CompletionResult = Any
    HeartbeatResult = Any
    TaskRecord = Any


EXTENSION_API_VERSION = "2025.1"

TaskEventCoroutine = Awaitable[None]
TaskEventCallable = Callable[..., TaskEventCoroutine | None]
StartupHook = Callable[[FastAPI], Awaitable[None] | None]


@dataclass(frozen=True)
class ExtensionContract:
    """Versioned contract describing the current extension surface area."""

    api_version: str = EXTENSION_API_VERSION
    notes: tuple[str, ...] = ()


class SupportsTaskEvents(Protocol):
    """Protocol implemented by task lifecycle hooks."""

    async def on_checkout(
        self, *, agent: Agent, result: CheckoutResult
    ) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_complete(
        self, *, agent_id: str, result: CompletionResult
    ) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_heartbeat(
        self, *, agent_id: str, result: HeartbeatResult
    ) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_abandon(
        self, *, agent_id: str, result: HeartbeatResult
    ) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_task_created(
        self, *, task: TaskRecord
    ) -> None:  # pragma: no cover - protocol definition
        ...

    async def on_task_updated(
        self, *, task: TaskRecord
    ) -> None:  # pragma: no cover - protocol definition
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
    contract: ExtensionContract = field(default_factory=ExtensionContract)

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
            async def runner(
                h: StartupHook = hook,
            ) -> None:  # pragma: no cover - async closure
                outcome = h(app)
                if inspect.isawaitable(outcome):
                    await outcome

            app.add_event_handler("startup", runner)


class ExtensionLoadError(RuntimeError):
    """Raised when an extension fails to load or register."""


class ExtensionRegistry:
    """Registry exposed to extensions during startup."""

    def __init__(self, contract: ExtensionContract | None = None) -> None:
        self._task_hooks: list[object] = []
        self._startup_hooks: list[StartupHook] = []
        self._descriptors: list[ExtensionDescriptor] = []
        self._contract = contract or ExtensionContract()

    def register_task_hook(self, hook: object) -> None:
        """Register a hook object for task lifecycle notifications."""

        self._task_hooks.append(hook)

    def register_startup_hook(self, hook: StartupHook) -> None:
        """Register a callable executed during FastAPI startup."""

        self._startup_hooks.append(hook)

    def register_extension(self, descriptor: ExtensionDescriptor) -> None:
        """Expose extension metadata for discovery endpoints."""

        self._descriptors.append(descriptor)

    def set_contract(self, *, api_version: str | None = None, notes: tuple[str, ...] | None = None) -> None:
        """Adjust the declared contract metadata for downstream consumers."""

        if api_version is None and notes is None:
            return
        self._contract = ExtensionContract(
            api_version=api_version or self._contract.api_version,
            notes=notes if notes is not None else self._contract.notes,
        )

    def append_contract_note(self, note: str) -> None:
        """Append a compatibility note to the extension contract."""

        self._contract = ExtensionContract(
            api_version=self._contract.api_version,
            notes=self._contract.notes + (note,),
        )

    def freeze(self) -> ExtensionBundle:
        """Return an immutable snapshot of registered hooks."""

        return ExtensionBundle(
            task_hooks=tuple(self._task_hooks),
            startup_hooks=tuple(self._startup_hooks),
            descriptors=tuple(self._descriptors),
            contract=self._contract,
        )
