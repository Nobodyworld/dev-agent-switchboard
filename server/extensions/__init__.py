"""Extension loading API for Switchboard."""

from __future__ import annotations

from .interfaces import (
    EXTENSION_API_VERSION,
    ExtensionBundle,
    ExtensionDescriptor,
    ExtensionLoadError,
    ExtensionRegistry,
)
from .loader import load_extension_bundle
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
    "get_extension_bundle",
    "initialize_extensions",
    "load_extension_bundle",
    "reload_extensions",
    "set_extension_bundle",
]
