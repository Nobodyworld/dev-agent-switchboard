"""Configuration and diagnostics API routes."""

from __future__ import annotations

import sys

from fastapi import APIRouter, Request

from server.api.dependencies import SessionDependency
from server.api.utils import system_state_to_out
from server.application import ConfigurationService, build_system_state_service
from server.extensions import ExtensionBundle, get_extension_bundle
from server.observability import collect_diagnostics as _collect_diagnostics_impl
from server.schema import (
    AdminSettingsOut,
    ConfigurationResponse,
    DatabaseSettingsOut,
    DiagnosticsPackageOut,
    DiagnosticsReportOut,
    EnvironmentVariableOut,
    ExecutionRoutingSettingsOut,
    ExtensionDescriptorOut,
    ExtensionSettingsOut,
    LeaseSettingsOut,
    RateLimitSettingsOut,
    RuntimeInfoOut,
    SettingsResponse,
    StorageInfoOut,
)
from server.settings import SettingsBundle, get_settings_bundle

router = APIRouter()


def _app_version(request: Request) -> str:
    return getattr(request.app, "version", "0.0.0")


def _resolve_collect_diagnostics():
    module = sys.modules.get("server.app")
    if module is not None and hasattr(module, "collect_diagnostics"):
        return module.collect_diagnostics
    return _collect_diagnostics_impl


def _build_settings_response(
    settings_bundle: SettingsBundle | None = None,
    extension_bundle: ExtensionBundle | None = None,
) -> SettingsResponse:
    bundle = settings_bundle or get_settings_bundle()
    extension_runtime = extension_bundle or get_extension_bundle()
    rate_settings = bundle.rate_limit
    lease_settings = bundle.lease
    extension_settings = bundle.extensions
    routing_settings = bundle.routing
    return SettingsResponse(
        rate_limit=RateLimitSettingsOut(
            requests=rate_settings.requests,
            window_seconds=rate_settings.window_seconds,
            trusted_bypass=sorted(rate_settings.trusted_bypass),
            trusted_proxies=sorted(rate_settings.trusted_proxies),
            enabled=rate_settings.enabled,
        ),
        lease=LeaseSettingsOut(duration_seconds=lease_settings.duration_seconds),
        execution_routing=ExecutionRoutingSettingsOut(
            heartbeat_freshness_seconds=(routing_settings.heartbeat_freshness_seconds),
            active_poll_freshness_seconds=(
                routing_settings.active_poll_freshness_seconds
            ),
        ),
        extensions=ExtensionSettingsOut(
            modules=list(extension_settings.modules),
            builtin_enabled=extension_settings.enable_builtin,
            registered=[
                ExtensionDescriptorOut(
                    name=descriptor.name,
                    capabilities=list(descriptor.capabilities),
                    version=descriptor.version,
                    description=descriptor.description,
                    config=descriptor.config,
                )
                for descriptor in extension_runtime.descriptors
            ],
            contract_version=extension_runtime.contract.api_version,
            contract_notes=list(extension_runtime.contract.notes),
        ),
    )


@router.get("/api/settings", response_model=SettingsResponse)
async def read_settings() -> SettingsResponse:
    return _build_settings_response()


@router.get("/api/configuration", response_model=ConfigurationResponse)
async def read_configuration(request: Request) -> ConfigurationResponse:
    service = ConfigurationService(version=_app_version(request))
    snapshot = service.snapshot()
    settings_response = _build_settings_response(
        snapshot.settings, snapshot.extension_bundle
    )
    runtime_info = RuntimeInfoOut(**snapshot.runtime.model_dump())
    storage = snapshot.storage
    storage_out = StorageInfoOut(
        root=str(storage.root),
        exists=storage.exists,
        writable=storage.writable,
        total_bytes=storage.total_bytes,
        free_bytes=storage.free_bytes,
    )
    environment = [
        EnvironmentVariableOut(name=entry.name, value=entry.value, source=entry.source)
        for entry in snapshot.environment
    ]
    database = snapshot.database
    database_out = DatabaseSettingsOut(
        url=database.url,
        driver=database.driver,
        configured_via_env=database.configured_via_env,
        engine_options=dict(database.engine_options),
    )
    admin_out = AdminSettingsOut(configured=snapshot.admin.configured)
    return ConfigurationResponse(
        settings=settings_response,
        admin=admin_out,
        storage=storage_out,
        database=database_out,
        runtime=runtime_info,
        environment=environment,
        warnings=list(snapshot.warnings),
    )


@router.get("/api/diagnostics", response_model=DiagnosticsReportOut)
async def read_diagnostics(
    request: Request,
    session: SessionDependency,
) -> DiagnosticsReportOut:
    state_service = build_system_state_service(session)
    system_state = await state_service.get_state()
    collect = _resolve_collect_diagnostics()
    report = collect(
        app_version=_app_version(request),
        system_state=system_state,
    )
    settings_response = _build_settings_response(
        report.settings_bundle, report.extension_bundle
    )
    runtime_info = RuntimeInfoOut(**report.runtime.model_dump())
    packages = [
        DiagnosticsPackageOut(
            name=package.name,
            installed=package.installed_version,
            required=package.required_version,
            status=package.status,
            homepage=package.homepage,
            summary=package.summary,
        )
        for package in report.packages
    ]
    system_state_out = None
    if system_state is not None:
        system_state_out = system_state_to_out(system_state)
    return DiagnosticsReportOut(
        python_version=report.python_version,
        implementation=report.implementation,
        platform=report.platform,
        executable=report.executable,
        runtime=runtime_info,
        packages=packages,
        settings=settings_response,
        system_state=system_state_out,
        features=dict(report.features),
        warnings=list(report.warnings),
        generated_at=report.generated_at,
    )
