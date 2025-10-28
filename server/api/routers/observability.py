"""Observability and health routes."""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse

from server.api.dependencies import SessionDependency, require_admin_token
from server.observability import (
    build_liveness_payload,
    build_readiness_payload,
    collect_observability_health,
    collect_observability_overview,
    describe_task_metrics,
    get_telemetry_report,
)
from server.schema import (
    HealthEnvelopeOut,
    HealthStatus,
    MetricsCatalogOut,
    ObservabilityHealthOut,
    ObservabilityOverviewOut,
    TelemetryReportOut,
)

router = APIRouter()


def _app_version(request: Request) -> str:
    return getattr(request.app, "version", "0.0.0")


@router.get("/health/live", response_model=HealthStatus)
async def health_live(request: Request) -> dict[str, object]:
    return build_liveness_payload(version=_app_version(request))


@router.get("/health/ready", response_model=HealthStatus)
async def health_ready(
    request: Request,
    session: SessionDependency,
):
    payload = await build_readiness_payload(session, version=_app_version(request))
    if not payload["ok"]:
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "OK"


@router.get(
    "/api/health",
    response_model=HealthEnvelopeOut,
    dependencies=[Depends(require_admin_token)],
)
async def read_combined_health(
    request: Request,
    session: SessionDependency,
) -> JSONResponse:
    liveness = build_liveness_payload(version=_app_version(request))
    readiness = await build_readiness_payload(session, version=_app_version(request))
    ok = bool(liveness.get("ok") and readiness.get("ok"))
    envelope = HealthEnvelopeOut(ok=ok, liveness=liveness, readiness=readiness)
    status = HTTPStatus.OK if ok else HTTPStatus.SERVICE_UNAVAILABLE
    if ok:
        return envelope
    return JSONResponse(status_code=status, content=jsonable_encoder(envelope))


@router.get(
    "/api/observability/health",
    response_model=ObservabilityHealthOut,
    dependencies=[Depends(require_admin_token)],
)
async def read_observability_health(
    request: Request,
    session: SessionDependency,
) -> ObservabilityHealthOut:
    payload = await collect_observability_health(session, version=_app_version(request))
    return payload


@router.get(
    "/api/observability/overview",
    response_model=ObservabilityOverviewOut,
    dependencies=[Depends(require_admin_token)],
)
async def read_observability_overview(
    request: Request,
    session: SessionDependency,
) -> dict[str, object]:
    overview = await collect_observability_overview(
        session,
        app_version=_app_version(request),
    )
    return overview.as_payload()


@router.get(
    "/api/observability/telemetry",
    response_model=TelemetryReportOut,
    dependencies=[Depends(require_admin_token)],
)
async def read_observability_telemetry(request: Request) -> TelemetryReportOut:
    report = get_telemetry_report(app_version=_app_version(request))
    return TelemetryReportOut.model_validate(report)


@router.get(
    "/api/observability/metrics",
    response_model=MetricsCatalogOut,
    dependencies=[Depends(require_admin_token)],
)
async def read_observability_metrics() -> MetricsCatalogOut:
    catalog = describe_task_metrics()
    generated_at = datetime.now(timezone.utc)
    payload = {"generated_at": generated_at, **catalog}
    if isinstance(catalog.get("last_updated_at"), datetime):
        payload["last_updated_at"] = catalog["last_updated_at"]
    return MetricsCatalogOut.model_validate(payload)
