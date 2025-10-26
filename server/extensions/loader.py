"""Extension loading utilities for Switchboard."""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Iterable, Sequence

from .interfaces import ExtensionBundle, ExtensionLoadError, ExtensionRegistry

LOGGER = logging.getLogger(__name__)
EXTENSION_ENV = "SWITCHBOARD_EXTENSIONS"
ENABLE_BUILTIN_ENV = "SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS"


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _normalize_modules(raw: Iterable[str]) -> tuple[str, ...]:
    modules: list[str] = []
    for entry in raw:
        candidate = entry.strip()
        if candidate:
            modules.append(candidate)
    return tuple(dict.fromkeys(modules))


def load_extension_bundle(
    *,
    modules: Sequence[str] | None = None,
    enable_builtin: bool | None = None,
) -> ExtensionBundle:
    """Return an :class:`ExtensionBundle` derived from the configured modules."""

    registry = ExtensionRegistry()

    include_builtin = enable_builtin
    if include_builtin is None:
        include_builtin = _truthy(os.getenv(ENABLE_BUILTIN_ENV), default=True)

    if include_builtin:
        try:
            from .builtin import task_metrics, webhook_notifier

            task_metrics.register(registry)
            webhook_notifier.register(registry)
        except Exception:  # pragma: no cover - builtin registration should succeed
            LOGGER.exception("Failed to register builtin extensions")

    configured_modules: tuple[str, ...]
    if modules is not None:
        configured_modules = tuple(modules)
    else:
        raw = os.getenv(EXTENSION_ENV, "")
        configured_modules = _normalize_modules(raw.split(",")) if raw else ()

    for module_path in configured_modules:
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:  # pragma: no cover - import failure logged for operators
            LOGGER.warning("Unable to import extension module %s: %s", module_path, exc)
            continue

        registrar = getattr(module, "register_extension", None) or getattr(
            module, "register", None
        )
        if registrar is None:
            LOGGER.warning(
                "Extension module %s does not expose register_extension()", module_path
            )
            continue

        try:
            registrar(registry)
        except ExtensionLoadError:
            raise
        except Exception:  # pragma: no cover - plugin failure surfaces to logs
            LOGGER.exception(
                "Extension %s failed during registration and was skipped", module_path
            )
            continue

    return registry.freeze()
