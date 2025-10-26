from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import app
from server.domain import SystemState
from server.extensions import ExtensionBundle
from server.extensions.interfaces import ExtensionContract, ExtensionDescriptor
from server.observability import diagnostics
from server.observability.diagnostics import (
    DiagnosticsReport,
    PackageStatus,
    clear_required_versions_cache,
)
from server.observability.runtime import RuntimeSnapshot
from server.settings import (
    ExtensionSettings,
    LeaseSettings,
    RateLimitSettings,
    SettingsBundle,
)

HTTP_OK = 200
EXPECTED_PID = 999
EXPECTED_STATE_VERSION = 7


def _make_settings_bundle() -> SettingsBundle:
    return SettingsBundle(
        rate_limit=RateLimitSettings(
            requests=25,
            window_seconds=10,
            trusted_bypass=frozenset(),
            trusted_proxies=frozenset(),
        ),
        lease=LeaseSettings(duration_seconds=120),
        extensions=ExtensionSettings(modules=("alpha.plugin",), enable_builtin=True),
    )


def test_collect_diagnostics_reports_package_status(monkeypatch):
    fake_settings = _make_settings_bundle()
    fake_extension_bundle = ExtensionBundle(descriptors=())
    fake_runtime = RuntimeSnapshot(
        started_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
        uptime_seconds=42.0,
        pid=1234,
    )

    monkeypatch.setattr(diagnostics, "get_settings_bundle", lambda: fake_settings)
    monkeypatch.setattr(
        diagnostics,
        "get_extension_bundle",
        lambda: fake_extension_bundle,
    )
    def fake_snapshot(*_args, **_kwargs):
        return fake_runtime

    monkeypatch.setattr(diagnostics, "get_runtime_snapshot", fake_snapshot)
    monkeypatch.setattr(diagnostics, "PACKAGES_OF_INTEREST", ("alpha", "beta"))
    monkeypatch.setattr(
        diagnostics,
        "_load_required_versions",
        lambda: {"alpha": "1.0"},
    )

    def fake_package_info(name: str) -> tuple[str | None, str | None, str | None]:
        if name == "alpha":
            return "1.0", "https://example.test/alpha", "Alpha runtime"
        if name == "beta":
            return None, None, None
        raise AssertionError(f"unexpected package lookup: {name}")

    monkeypatch.setattr(diagnostics, "_package_info", fake_package_info)

    report = diagnostics.collect_diagnostics(app_version="test")

    assert report.python_version
    assert report.runtime is fake_runtime
    assert report.settings_bundle is fake_settings
    assert report.extension_bundle is fake_extension_bundle
    assert report.features["rate_limit_enabled"] is True
    assert report.features["extensions_registered"] is False

    packages = {pkg.name: pkg for pkg in report.packages}
    assert packages["alpha"].status == "ok"
    assert packages["beta"].status == "missing"
    assert any("beta" in warning for warning in report.warnings)


def test_load_required_versions_cache(monkeypatch):
    clear_required_versions_cache()
    calls: dict[str, int] = {"read": 0}

    def fake_exists(self: Path) -> bool:
        _ = self
        return True

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        _ = self
        _ = encoding
        calls["read"] += 1
        return "alpha==1.0\n"

    monkeypatch.setattr(diagnostics.Path, "exists", fake_exists)
    monkeypatch.setattr(diagnostics.Path, "read_text", fake_read_text)

    first = diagnostics._load_required_versions()
    second = diagnostics._load_required_versions()
    assert first == {"alpha": "1.0"}
    assert second == first
    assert calls["read"] == 1

    clear_required_versions_cache()
    diagnostics._load_required_versions()
    expected_reads_after_clear = 2
    assert calls["read"] == expected_reads_after_clear


def test_read_diagnostics_endpoint_shapes_payload(monkeypatch):
    generated_at = dt.datetime.now(tz=dt.timezone.utc)
    fake_settings = _make_settings_bundle()
    fake_extension_bundle = ExtensionBundle(
        descriptors=(
            ExtensionDescriptor(
                name="demo",
                capabilities=("hooks",),
                version="0.1.0",
                description="demo extension",
                config={"enabled": True},
            ),
        ),
        contract=ExtensionContract(api_version="2025.2", notes=("beta",)),
    )
    fake_runtime = RuntimeSnapshot(
        started_at=generated_at,
        uptime_seconds=5.0,
        pid=999,
        version="app-version",
    )
    fake_system_state = SystemState(
        maintenance_mode=False,
        message="",
        updated_at=generated_at,
        version=7,
    )
    fake_report = DiagnosticsReport(
        python_version="3.11.9",
        implementation="CPython",
        platform="test-platform",
        executable="/usr/bin/python",
        runtime=fake_runtime,
        packages=(
            PackageStatus(
                name="alpha",
                installed_version="1.0",
                required_version="1.0",
                status="ok",
            ),
        ),
        settings_bundle=fake_settings,
        extension_bundle=fake_extension_bundle,
        system_state=fake_system_state,
        features={"rate_limit_enabled": True},
        warnings=("demo warning",),
        generated_at=generated_at,
    )

    captured: dict[str, object] = {}

    def fake_collect(*, app_version: str | None, system_state: SystemState | None):
        captured["app_version"] = app_version
        captured["system_state"] = system_state
        return fake_report

    monkeypatch.setattr("server.app.collect_diagnostics", fake_collect)

    with TestClient(app) as client:
        response = client.get("/api/diagnostics")

    assert response.status_code == HTTP_OK
    payload = response.json()

    assert captured["app_version"] == app.version
    assert isinstance(captured["system_state"], SystemState)
    assert payload["python_version"] == "3.11.9"
    assert payload["implementation"] == "CPython"
    assert payload["runtime"]["pid"] == EXPECTED_PID
    rate_limit = payload["settings"]["rate_limit"]
    assert rate_limit["requests"] == fake_settings.rate_limit.requests
    assert isinstance(payload["system_state"]["version"], int)
    assert payload["packages"][0]["name"] == "alpha"
    assert payload["warnings"] == ["demo warning"]
    assert payload["features"]["rate_limit_enabled"] is True
    assert payload["settings"]["extensions"]["contract_version"] == "2025.2"
    assert payload["settings"]["extensions"]["contract_notes"] == ["beta"]
