"""Diagnostics helpers that aggregate runtime metadata for operators."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import platform
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

from server.domain import SystemState
from server.extensions import ExtensionBundle, get_extension_bundle
from server.observability.runtime import RuntimeSnapshot, get_runtime_snapshot
from server.settings import (
    SettingsBundle,
    get_admin_token,
    get_settings_bundle,
)

PACKAGES_OF_INTEREST: tuple[str, ...] = (
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "SQLAlchemy",
    "aiosqlite",
    "jinja2",
    "httpx",
    "python-json-logger",
    "prometheus-fastapi-instrumentator",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp",
    "opentelemetry-instrumentation-fastapi",
    "PyYAML",
    "python-multipart",
    "greenlet",
)


@dataclass(frozen=True)
class PackageStatus:
    """Information about an installed package and its expected version."""

    name: str
    installed_version: str | None
    required_version: str | None
    status: Literal["ok", "mismatch", "missing"]
    homepage: str | None = None
    summary: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "installed": self.installed_version,
            "required": self.required_version,
            "status": self.status,
        }
        if self.homepage:
            payload["homepage"] = self.homepage
        if self.summary:
            payload["summary"] = self.summary
        return payload


@dataclass(frozen=True)
class DiagnosticsReport:
    """Aggregated diagnostics snapshot used by the API and UI."""

    python_version: str
    implementation: str
    platform: str
    executable: str
    runtime: RuntimeSnapshot
    packages: tuple[PackageStatus, ...]
    settings_bundle: SettingsBundle
    extension_bundle: ExtensionBundle
    system_state: SystemState | None
    features: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the report."""

        return {
            "python_version": self.python_version,
            "implementation": self.implementation,
            "platform": self.platform,
            "executable": self.executable,
            "runtime": self.runtime.model_dump(),
            "packages": [package.as_dict() for package in self.packages],
            "features": dict(self.features),
            "warnings": list(self.warnings),
            "generated_at": self.generated_at.isoformat(),
        }


def collect_diagnostics(
    *, app_version: str | None = None, system_state: SystemState | None = None
) -> DiagnosticsReport:
    """Collect a diagnostics snapshot describing the current runtime state."""

    settings_bundle = get_settings_bundle()
    extension_bundle = get_extension_bundle()
    runtime = get_runtime_snapshot(version=app_version)

    required_versions = _load_required_versions()
    packages, warnings = _build_package_statuses(
        required_versions, PACKAGES_OF_INTEREST
    )

    features = _build_feature_flags(settings_bundle, extension_bundle, system_state)

    return DiagnosticsReport(
        python_version=platform.python_version(),
        implementation=platform.python_implementation(),
        platform=platform.platform(),
        executable=sys.executable,
        runtime=runtime,
        packages=packages,
        settings_bundle=settings_bundle,
        extension_bundle=extension_bundle,
        system_state=system_state,
        features=features,
        warnings=warnings,
    )


@lru_cache(maxsize=1)
def _load_required_versions() -> dict[str, str]:
    requirements_path = Path(__file__).resolve().parents[1] / "requirements.txt"
    versions: dict[str, str] = {}
    if not requirements_path.exists():
        return versions
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            continue
        package, version = line.split("==", 1)
        versions[package.strip()] = version.strip()
    return versions


def clear_required_versions_cache() -> None:
    """Reset the requirements version cache for testability."""

    _load_required_versions.cache_clear()


def _build_package_statuses(
    required_versions: dict[str, str], packages: Iterable[str]
) -> tuple[tuple[PackageStatus, ...], tuple[str, ...]]:
    statuses: list[PackageStatus] = []
    warnings: list[str] = []
    for name in packages:
        installed, homepage, summary = _package_info(name)
        required = required_versions.get(name)
        status = _resolve_status(installed, required)
        statuses.append(
            PackageStatus(
                name=name,
                installed_version=installed,
                required_version=required,
                status=status,
                homepage=homepage,
                summary=summary,
            )
        )
        if status == "missing":
            warnings.append(f"Package {name!r} is not installed.")
        elif status == "mismatch" and installed and required:
            warnings.append(
                f"Package {name!r} requires {required} but {installed} is installed."
            )
    statuses.sort(key=lambda item: item.name.lower())
    return tuple(statuses), tuple(warnings)


def _package_info(name: str) -> tuple[str | None, str | None, str | None]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return None, None, None
    metadata = cast(Message, distribution.metadata)
    homepage = metadata.get("Home-page")
    summary = metadata.get("Summary")
    return distribution.version, homepage, summary


def _resolve_status(
    installed: str | None, required: str | None
) -> Literal["ok", "mismatch", "missing"]:
    if installed is None:
        return "missing"
    if required and installed != required:
        return "mismatch"
    return "ok"


def _build_feature_flags(
    settings_bundle: SettingsBundle,
    extension_bundle: ExtensionBundle,
    system_state: SystemState | None,
) -> dict[str, Any]:
    rate_limit = settings_bundle.rate_limit
    lease = settings_bundle.lease
    features: dict[str, Any] = {
        "rate_limit_enabled": rate_limit.enabled,
        "rate_limit_window_seconds": rate_limit.window_seconds,
        "lease_duration_seconds": lease.duration_seconds,
        "extensions_registered": bool(extension_bundle.descriptors),
        "extension_modules": list(settings_bundle.extensions.modules),
        "builtin_extensions_enabled": settings_bundle.extensions.enable_builtin,
        "metrics_env_enabled": _truthy_env("SWITCHBOARD_ENABLE_METRICS"),
        "metrics_dependency_available": _module_available(
            "prometheus_fastapi_instrumentator"
        ),
        "tracing_env_enabled": _truthy_env("SWITCHBOARD_ENABLE_TRACING"),
        "tracing_dependency_available": _module_available(
            "opentelemetry.instrumentation.fastapi"
        ),
        "admin_token_configured": get_admin_token() is not None,
    }
    if system_state is not None:
        features["maintenance_mode"] = system_state.maintenance_mode
        features["system_state_version"] = system_state.version
    return features


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def _module_available(import_path: str) -> bool:
    try:
        return importlib.util.find_spec(import_path) is not None
    except (ImportError, AttributeError):
        return False
