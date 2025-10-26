"""Builtin webhook notifier extension for Switchboard."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from server.extensions.interfaces import (
    ExtensionDescriptor,
    ExtensionLoadError,
    ExtensionRegistry,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_EVENTS: tuple[str, ...] = (
    "on_task_created",
    "on_task_updated",
    "on_checkout",
    "on_complete",
    "on_heartbeat",
    "on_abandon",
)
URL_ENV = "SWITCHBOARD_WEBHOOK_URL"
EVENTS_ENV = "SWITCHBOARD_WEBHOOK_EVENTS"
HEADERS_ENV = "SWITCHBOARD_WEBHOOK_HEADERS"
TIMEOUT_ENV = "SWITCHBOARD_WEBHOOK_TIMEOUT"


@dataclass
class WebhookNotifier:
    """Task lifecycle hook that emits structured webhook payloads."""

    url: str
    events: tuple[str, ...]
    headers: Mapping[str, str]
    timeout: float

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(self.url, json=payload, headers=self.headers)
        except Exception:  # pragma: no cover - surfaced via logging
            LOGGER.warning("Webhook delivery failed", exc_info=True)

    async def _dispatch(self, event: str, payload: Mapping[str, Any]) -> None:
        if event not in self.events:
            return
        envelope = {"event": event, "data": dict(payload)}
        await self._send(envelope)

    async def on_task_created(self, *, task: Any) -> None:
        await self._dispatch(
            "on_task_created",
            {
                "task_id": getattr(task, "id", None),
                "title": getattr(task, "title", None),
                "status": getattr(getattr(task, "status", None), "name", None),
            },
        )

    async def on_task_updated(self, *, task: Any) -> None:
        await self._dispatch(
            "on_task_updated",
            {
                "task_id": getattr(task, "id", None),
                "title": getattr(task, "title", None),
                "status": getattr(getattr(task, "status", None), "name", None),
            },
        )

    async def on_checkout(self, *, agent: Any, result: Any) -> None:
        await self._dispatch(
            "on_checkout",
            {
                "agent_id": getattr(agent, "agent_id", None),
                "task_id": getattr(getattr(result, "task", None), "id", None),
                "reason": getattr(result, "reason", None),
            },
        )

    async def on_complete(self, *, agent_id: str, result: Any) -> None:
        await self._dispatch(
            "on_complete",
            {
                "agent_id": agent_id,
                "ok": getattr(result, "ok", None),
                "task_id": getattr(getattr(result, "task", None), "id", None),
            },
        )

    async def on_heartbeat(self, *, agent_id: str, result: Any) -> None:
        await self._dispatch(
            "on_heartbeat",
            {
                "agent_id": agent_id,
                "ok": getattr(result, "ok", None),
                "task_id": getattr(result, "task_id", None),
            },
        )

    async def on_abandon(self, *, agent_id: str, result: Any) -> None:
        await self._dispatch(
            "on_abandon",
            {
                "agent_id": agent_id,
                "task_id": getattr(result, "task_id", None),
            },
        )


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_events(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_EVENTS
    events: list[str] = []
    for piece in raw.split(","):
        name = piece.strip()
        if name:
            events.append(name)
    valid = [event for event in events if event in DEFAULT_EVENTS]
    return tuple(valid or DEFAULT_EVENTS)


def _parse_headers(raw: str | None) -> Mapping[str, str]:
    headers: dict[str, str] = {}
    if not raw:
        return headers
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            return {str(key): str(value) for key, value in decoded.items()}
    except json.JSONDecodeError:
        pass
    for piece in raw.split(","):
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def register(registry: ExtensionRegistry) -> None:
    """Register the webhook notifier extension when configured."""

    url = os.getenv(URL_ENV)
    events = _parse_events(os.getenv(EVENTS_ENV))
    headers = _parse_headers(os.getenv(HEADERS_ENV))
    timeout_raw = os.getenv(TIMEOUT_ENV, "5.0")
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:  # pragma: no cover - configuration error
        raise ExtensionLoadError(f"Invalid timeout {timeout_raw!r}") from exc

    registry.register_extension(
        ExtensionDescriptor(
            name="builtin.webhook_notifier",
            capabilities=("webhook", "notifications"),
            version="1.0.0",
            description="Emits webhook callbacks for task lifecycle events.",
            config={
                "enabled": bool(url),
                "events": list(events),
                "timeout": timeout,
            },
        )
    )

    registry.append_contract_note(
        "Webhook notifier publishes task lifecycle updates when "
        "SWITCHBOARD_WEBHOOK_URL is set."
    )

    if not url:
        LOGGER.info("Webhook notifier disabled; set %s to enable", URL_ENV)
        return

    if not _truthy(os.getenv("SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS", "1")):
        LOGGER.info("Builtin extensions disabled; webhook notifier skipped")
        return

    formatted_events = ", ".join(events)
    LOGGER.info(
        "Registering webhook notifier for %s with events %s",
        url,
        formatted_events,
    )
    registry.register_task_hook(
        WebhookNotifier(url=url, events=events, headers=headers, timeout=timeout)
    )


register_extension = register
