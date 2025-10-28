"""Interfaces shared by Switchboard extensions and runtime instrumentation."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI

from .contracts import PlanBroadcastContext, TaskHookContext

if TYPE_CHECKING:  # pragma: no cover - typing imports for documentation clarity
    from server.domain import (
        Agent,
        CheckoutResult,
        CompletionResult,
        HeartbeatResult,
        TaskRecord,
    )
    from server.extensions.observability import (
        ObservabilityHook,
        ObservabilityRegistration,
    )
    from server.observability.telemetry import TelemetryState
else:  # pragma: no cover - runtime fallbacks keep optional dependencies optional
    Agent = Any
    CheckoutResult = Any
    CompletionResult = Any
    HeartbeatResult = Any
    TaskRecord = Any
    ObservabilityHook = Callable[..., Any]
    ObservabilityRegistration = Any  # type: ignore[assignment]
    TelemetryState = Any  # type: ignore[assignment]


EXTENSION_API_VERSION = "2025.3"

TaskEventCoroutine = Awaitable[None]
TaskEventCallable = Callable[..., TaskEventCoroutine | None]
StartupHook = Callable[[FastAPI], Awaitable[None] | None]
PlanEventCoroutine = Awaitable[None]
PlanEventCallable = Callable[..., PlanEventCoroutine | None]
ObservabilityHookResult = ObservabilityRegistration | None


def _accepts_context(callback: Any) -> bool:
    """Return ``True`` if ``callback`` declares a ``context`` keyword."""

    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):  # pragma: no cover - C extensions
        return False
    for parameter in signature.parameters.values():
        if parameter.name != "context":
            continue
        if parameter.kind in (
            parameter.POSITIONAL_OR_KEYWORD,
            parameter.KEYWORD_ONLY,
        ):
            return True
    return False


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


class SupportsPlanEvents(Protocol):
    """Protocol implemented by plan broadcast observers."""

    async def on_plan_broadcast(
        self,
        *,
        version: int | None,
        plan: Mapping[str, Any] | None,
        delta: Mapping[str, Any] | None,
        analytics: Any | None,
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
class ObservabilityHookRegistration:
    """Metadata describing an extension-provided observability hook."""

    extension: str
    callback: ObservabilityHook
    description: str | None = None
    capabilities: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtensionBundle:
    """Frozen set of runtime hooks registered by extensions."""

    task_hooks: tuple[object, ...] = ()
    startup_hooks: tuple[StartupHook, ...] = ()
    plan_observers: tuple[object, ...] = ()
    descriptors: tuple[ExtensionDescriptor, ...] = ()
    contract: ExtensionContract = field(default_factory=ExtensionContract)
    observability_hooks: tuple[ObservabilityHookRegistration, ...] = ()

    async def emit(self, event: str, **payload: Any) -> None:
        """Invoke ``event`` across registered task hooks."""

        if not self.task_hooks:
            return
        context = TaskHookContext(event=event, payload=dict(payload))
        for hook in self.task_hooks:
            callback = getattr(hook, event, None)
            if callback is None:
                continue
            kwargs = dict(payload)
            if _accepts_context(callback):
                kwargs["context"] = context
            result = callback(**kwargs)
            if inspect.isawaitable(result):
                await result

    async def emit_plan_event(self, event: str, **payload: Any) -> None:
        """Invoke ``event`` across registered plan observers."""

        if not self.plan_observers:
            return
        context = PlanBroadcastContext(
            version=payload.get("version"),
            plan=payload.get("plan"),
            delta=payload.get("delta"),
            analytics=payload.get("analytics"),
        )
        for observer in self.plan_observers:
            callback = getattr(observer, event, None)
            if callback is None:
                continue
            kwargs = dict(payload)
            if _accepts_context(callback):
                kwargs["context"] = context
            result = callback(**kwargs)
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
        self._plan_observers: list[object] = []
        self._descriptors: list[ExtensionDescriptor] = []
        self._observability_hooks: list[ObservabilityHookRegistration] = []
        self._contract = contract or ExtensionContract()

    def register_task_hook(self, hook: object) -> None:
        """Register a hook object for task lifecycle notifications."""

        self._task_hooks.append(hook)

    def register_startup_hook(self, hook: StartupHook) -> None:
        """Register a callable executed during FastAPI startup."""

        self._startup_hooks.append(hook)

    def register_plan_observer(self, observer: object) -> None:
        """Register an observer notified after plan broadcasts."""

        self._plan_observers.append(observer)

    def register_extension(self, descriptor: ExtensionDescriptor) -> None:
        """Expose extension metadata for discovery endpoints."""

        self._descriptors.append(descriptor)

    def register_observability_hook(
        self,
        extension: str,
        callback: ObservabilityHook,
        *,
        description: str | None = None,
        capabilities: tuple[str, ...] = (),
        outputs: tuple[str, ...] = (),
    ) -> None:
        """Register a telemetry hook executed during instrumentation bootstrap."""

        self._observability_hooks.append(
            ObservabilityHookRegistration(
                extension=extension,
                callback=callback,
                description=description,
                capabilities=capabilities,
                outputs=outputs,
            )
        )

    def set_contract(
        self,
        *,
        api_version: str | None = None,
        notes: tuple[str, ...] | None = None,
    ) -> None:
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
            notes=(*self._contract.notes, note),
        )

    def freeze(self) -> ExtensionBundle:
        """Return an immutable snapshot of registered hooks."""

        return ExtensionBundle(
            task_hooks=tuple(self._task_hooks),
            startup_hooks=tuple(self._startup_hooks),
            plan_observers=tuple(self._plan_observers),
            descriptors=tuple(self._descriptors),
            contract=self._contract,
            observability_hooks=tuple(self._observability_hooks),
        )
