"""Services for assembling rich configuration snapshots."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from server.db import DATABASE_URL, ENGINE_OPTIONS, FILES_ROOT, STORAGE_ROOT
from server.extensions import ExtensionBundle, get_extension_bundle
from server.observability.runtime import RuntimeSnapshot, get_runtime_snapshot
from server.settings import SettingsBundle, get_admin_token, get_settings_bundle

LOW_STORAGE_THRESHOLD_BYTES = 256 * 1024 * 1024  # 256 MiB


@dataclass(frozen=True)
class AdminSettingsSnapshot:
    """Representation of administrative authentication configuration."""

    configured: bool


@dataclass(frozen=True)
class StorageSnapshot:
    """Description of the live file storage root and its health."""

    root: Path
    exists: bool
    writable: bool
    total_bytes: int | None
    free_bytes: int | None


@dataclass(frozen=True)
class DatabaseSnapshot:
    """Database connection metadata with credentials removed."""

    url: str
    driver: str | None
    configured_via_env: bool
    engine_options: Mapping[str, object]


@dataclass(frozen=True)
class EnvironmentVariableSnapshot:
    """Sanitised environment variable surfaced for diagnostics."""

    name: str
    value: str
    source: str


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """Aggregated configuration data used by API, CLI, and UI surfaces."""

    settings: SettingsBundle
    extension_bundle: ExtensionBundle
    runtime: RuntimeSnapshot
    admin: AdminSettingsSnapshot
    storage: StorageSnapshot
    database: DatabaseSnapshot
    environment: tuple[EnvironmentVariableSnapshot, ...]
    warnings: tuple[str, ...]


class ConfigurationService:
    """Build comprehensive runtime configuration snapshots."""

    SAFE_ENVIRONMENT_VARIABLES: tuple[str, ...] = (
        "SWITCHBOARD_ENVIRONMENT",
        "SWITCHBOARD_COMMIT_SHA",
        "SWITCHBOARD_RATE_LIMIT_REQUESTS",
        "SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS",
        "SWITCHBOARD_RATE_LIMIT_TRUSTED_BYPASS",
        "SWITCHBOARD_RATE_LIMIT_TRUSTED_PROXIES",
        "SWITCHBOARD_LEASE_SECONDS",
        "SWITCHBOARD_EXTENSIONS",
        "SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS",
        "SWITCHBOARD_MAX_LIVE_FILE_BYTES",
        "FILES_ROOT",
        "STORAGE_ROOT",
    )

    def __init__(self, *, version: str | None = None) -> None:
        self._version = version

    def snapshot(self) -> ConfigurationSnapshot:
        """Return the current configuration snapshot."""

        settings = get_settings_bundle()
        extension_bundle = get_extension_bundle()
        runtime = get_runtime_snapshot(version=self._version)
        admin = AdminSettingsSnapshot(configured=get_admin_token() is not None)
        storage, storage_warnings = self._collect_storage()
        database = self._collect_database()
        environment = self._collect_environment(storage.root)
        warnings = tuple(storage_warnings)
        return ConfigurationSnapshot(
            settings=settings,
            extension_bundle=extension_bundle,
            runtime=runtime,
            admin=admin,
            storage=storage,
            database=database,
            environment=environment,
            warnings=warnings,
        )

    def _collect_storage(self) -> tuple[StorageSnapshot, list[str]]:
        root = Path(FILES_ROOT)
        warnings: list[str] = []
        exists = self._path_exists(root)
        if not exists:
            warnings.append(
                "Failed to inspect live file storage root; "
                "permission denied or path invalid."
            )

        writable = self._is_writable(root if exists else root.parent)

        total_bytes: int | None = None
        free_bytes: int | None = None
        disk_target = root if exists else root.parent
        try:
            usage = shutil.disk_usage(disk_target)
        except (FileNotFoundError, PermissionError, OSError):
            usage = None
            warnings.append(
                "Unable to determine live file storage disk usage; "
                "check filesystem permissions and mounts."
            )
        if usage is not None:
            total_bytes = int(usage.total)
            free_bytes = int(usage.free)

        if not exists:
            warnings.append(
                "Live file storage root does not exist; "
                "it will be created on demand by uploads."
            )
        if not exists and not writable:
            warnings.append(
                "Live file storage root is missing and its parent directory "
                "is not writable; uploads cannot create it automatically."
            )
        if exists and not writable:
            warnings.append(
                "Live file storage root is not writable; "
                "uploads will fail until permissions are corrected."
            )
        if (
            free_bytes is not None
            and free_bytes < LOW_STORAGE_THRESHOLD_BYTES
            and exists
            and writable
        ):
            warnings.append(
                "Live file storage free space is below 256 MiB; "
                "consider increasing disk capacity."
            )

        snapshot = StorageSnapshot(
            root=root,
            exists=exists,
            writable=writable,
            total_bytes=total_bytes,
            free_bytes=free_bytes,
        )
        return snapshot, warnings

    @staticmethod
    def _path_exists(path: Path) -> bool:
        try:
            return path.exists()
        except OSError:
            return False

    @staticmethod
    def _is_writable(path: Path) -> bool:
        try:
            return os.access(path, os.W_OK | os.X_OK)
        except OSError:
            return False

    def _collect_database(self) -> DatabaseSnapshot:
        raw_url = DATABASE_URL
        configured_via_env = bool(os.getenv("DATABASE_URL"))
        masked_url = raw_url
        driver: str | None = None
        try:
            parsed = make_url(raw_url)
        except ArgumentError:
            parsed = None
        if parsed is not None:
            driver = parsed.drivername
            masked_url = parsed.render_as_string(hide_password=True)
        elif ":" in raw_url:
            driver = raw_url.split(":", 1)[0]

        # TODO(P2, 1d) - Capture pool utilization metrics once observability
        # exposes them.
        options: dict[str, object] = {
            key: ENGINE_OPTIONS[key] for key in sorted(ENGINE_OPTIONS)
        }
        return DatabaseSnapshot(
            url=masked_url,
            driver=driver,
            configured_via_env=configured_via_env,
            engine_options=options,
        )

    def _collect_environment(
        self, storage_root: Path
    ) -> tuple[EnvironmentVariableSnapshot, ...]:
        entries: list[EnvironmentVariableSnapshot] = []
        seen: set[str] = set()
        for name in self.SAFE_ENVIRONMENT_VARIABLES:
            raw = os.getenv(name)
            if raw is None:
                continue
            value = self._truncate(raw.strip())
            if not value:
                continue
            entries.append(
                EnvironmentVariableSnapshot(
                    name=name,
                    value=value,
                    source="environment",
                )
            )
            seen.add(name)

        if "FILES_ROOT" not in seen:
            entries.append(
                EnvironmentVariableSnapshot(
                    name="FILES_ROOT",
                    value=str(storage_root),
                    source="derived",
                )
            )
        if "STORAGE_ROOT" not in seen:
            entries.append(
                EnvironmentVariableSnapshot(
                    name="STORAGE_ROOT",
                    value=str(STORAGE_ROOT),
                    source="derived",
                )
            )

        entries.sort(key=lambda entry: entry.name)
        return tuple(entries)

    @staticmethod
    def _truncate(value: str, *, limit: int = 512) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 1] + "…"


__all__ = [
    "AdminSettingsSnapshot",
    "ConfigurationService",
    "ConfigurationSnapshot",
    "DatabaseSnapshot",
    "EnvironmentVariableSnapshot",
    "StorageSnapshot",
]
