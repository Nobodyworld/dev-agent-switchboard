"""Extension loading API for Switchboard."""

from __future__ import annotations

from .contracts import PlanBroadcastContext, TaskHookContext
from .interfaces import (
    EXTENSION_API_VERSION,
    ExtensionBundle,
    ExtensionDescriptor,
    ExtensionLoadError,
    ExtensionRegistry,
    ObservabilityHookRegistration,
)
from .loader import load_extension_bundle
from .observability import (
    ObservabilityHook,
    ObservabilityRegistration,
    ObservabilitySnapshot,
    get_observability_registrations,
    record_observability_registration,
    reset_observability_registrations,
)
from .runtime import (
    get_extension_bundle,
    initialize_extensions,
    reload_extensions,
    set_extension_bundle,
)

__all__ = [
    "EXTENSION_API_VERSION",
    "ExtensionBundle",
    "ExtensionDescriptor",
    "ExtensionLoadError",
    "ExtensionRegistry",
    "ObservabilityHook",
    "ObservabilityHookRegistration",
    "ObservabilityRegistration",
    "ObservabilitySnapshot",
    "PlanBroadcastContext",
    "TaskHookContext",
    "get_extension_bundle",
    "get_observability_registrations",
    "initialize_extensions",
    "load_extension_bundle",
    "record_observability_registration",
    "reload_extensions",
    "reset_observability_registrations",
    "set_extension_bundle",
]
