"""Runtime helpers for accessing the active extension bundle."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import FastAPI

from .interfaces import ExtensionBundle
from .loader import load_extension_bundle

LOGGER = logging.getLogger(__name__)


class _BundleCache:
    """Simple cache holder for the loaded extension bundle."""

    __slots__ = ("bundle",)

    def __init__(self) -> None:
        self.bundle: ExtensionBundle | None = None


_CACHE = _BundleCache()


def get_extension_bundle() -> ExtensionBundle:
    """Return the cached :class:`ExtensionBundle`, loading it if necessary."""

    if _CACHE.bundle is None:
        _CACHE.bundle = load_extension_bundle()
    return _CACHE.bundle


def initialize_extensions(app: FastAPI) -> ExtensionBundle:
    """Load extensions and attach startup hooks to ``app``."""

    bundle = get_extension_bundle()
    if bundle.descriptors:
        LOGGER.info(
            "Loaded %s extensions: %s",
            len(bundle.descriptors),
            ", ".join(descriptor.name for descriptor in bundle.descriptors),
        )
    bundle.attach(app)
    return bundle


def reload_extensions(*, modules: Sequence[str] | None = None) -> ExtensionBundle:
    """Force a reload of the extension bundle (for tests)."""

    _CACHE.bundle = load_extension_bundle(modules=modules)
    return _CACHE.bundle


def set_extension_bundle(bundle: ExtensionBundle | None) -> ExtensionBundle | None:
    """Override the cached bundle. Intended for testing."""

    previous = _CACHE.bundle
    _CACHE.bundle = bundle
    return previous
