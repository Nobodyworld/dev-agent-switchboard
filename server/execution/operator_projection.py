"""Bounded, redacted read models for the validation broker dashboard."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql.elements import ColumnElement

from server.models import (
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
    GitHubValidationRequest,
    WorkerRoutingProfile,
)
from server.time_utils import utcnow_naive

from .enums import ExecutionRunStatus, ReuseDecision, WorkerStatus

MAX_OPERATOR_LIMIT = 100
MAX_OPERATOR_OFFSET = 10_000
MAX_OPERATOR_WINDOW_DAYS = 365
SHA256_HEX_LENGTH = 64


class OperatorProjectionModel(BaseModel):
    """Strict base for browser-safe operator projections."""

    model_config = ConfigDict(extra="forbid")


class OperatorWindowOut(OperatorProjectionModel):
    """Inclusive UTC window applied to persisted record timestamps."""

    days: int = Field(ge=1, le=MAX_OPERATOR_WINDOW_DAYS)
    starts_at: dt.datetime
    ends_at: dt.datetime


class OperatorRequestMetricsOut(OperatorProjectionModel):
    total: int = Field(ge=0)


class OperatorWorkOrderMetricsOut(OperatorProjectionModel):
    total: int = Field(ge=0)
    by_status: dict[str, int]


class OperatorRunMetricsOut(OperatorProjectionModel):
    total: int = Field(ge=0)
    by_status: dict[str, int]
    fresh_successful: int = Field(ge=0)
    reused_successful: int = Field(ge=0)
    unavailable_exact_reuse: int = Field(ge=0)


class AvoidedWorkMetricsOut(OperatorProjectionModel):
    deterministic_executions_avoided: int = Field(ge=0)
    reference_seconds_avoided: float = Field(ge=0)
    comparison_units_avoided: int = Field(ge=0)
    reuse_rate: float = Field(ge=0, le=1)


class OperatorPublicationMetricsOut(OperatorProjectionModel):
    current: int = Field(ge=0)
    stale: int = Field(ge=0)


class OperatorWorkerMetricsOut(OperatorProjectionModel):
    total: int = Field(ge=0)
    active: int = Field(ge=0)
    stale: int = Field(ge=0)
    capacity_constrained: int = Field(ge=0)


class ExecutionOperatorOverviewOut(OperatorProjectionModel):
    window: OperatorWindowOut
    requests: OperatorRequestMetricsOut
    work_orders: OperatorWorkOrderMetricsOut
    runs: OperatorRunMetricsOut
    avoided_work: AvoidedWorkMetricsOut
    publications: OperatorPublicationMetricsOut
    workers: OperatorWorkerMetricsOut


class RoutingProfileSummaryOut(OperatorProjectionModel):
    enabled: bool
    estimated_cost_units_per_run: int = Field(ge=0)
    quota_capacity_units: int = Field(ge=0)
    quota_remaining_units: int = Field(ge=0)
    quota_reset_at: dt.datetime | None
    routing_priority: int = Field(ge=0)
    revision: int = Field(ge=1)
    updated_at: dt.datetime


class ExecutionWorkerSummaryOut(OperatorProjectionModel):
    worker_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    operating_system: str = Field(min_length=1, max_length=64)
    architecture: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=32)
    activity_state: Literal["active", "stale", "capacity_constrained", "unavailable"]
    active_run_count: int = Field(ge=0)
    max_concurrency: int = Field(ge=1)
    last_heartbeat_at: dt.datetime
    last_checkout_poll_at: dt.datetime | None
    profile: RoutingProfileSummaryOut | None


class ExecutionWorkerPageOut(OperatorProjectionModel):
    items: list[ExecutionWorkerSummaryOut]
    limit: int = Field(ge=1, le=MAX_OPERATOR_LIMIT)
    offset: int = Field(ge=0, le=MAX_OPERATOR_OFFSET)
    total: int = Field(ge=0)


class ExecutionHistoryItemOut(OperatorProjectionModel):
    request_id: int = Field(ge=1)
    repository_full_name: str = Field(min_length=3, max_length=255)
    pull_request_number: int = Field(ge=1)
    tested_head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest_name: str = Field(min_length=1, max_length=128)
    manifest_version: str = Field(min_length=1, max_length=64)
    work_order_id: int = Field(ge=1)
    work_order_status: str = Field(min_length=1, max_length=32)
    routing_policy: str = Field(min_length=1, max_length=32)
    preferred_executor: str | None = Field(default=None, max_length=128)
    maximum_cost_units: int | None = Field(default=None, ge=0)
    required_quota_units: int = Field(ge=0)
    run_id: int | None = Field(default=None, ge=1)
    run_status: str | None = Field(default=None, max_length=32)
    selected_worker_id: str | None = Field(default=None, max_length=128)
    estimated_cost_units: int | None = Field(default=None, ge=0)
    reuse_decision: str | None = Field(default=None, max_length=32)
    reused_from_run_id: int | None = Field(default=None, ge=1)
    run_duration_seconds: float | None = Field(default=None, ge=0)
    evidence_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    publication_state: str = Field(min_length=1, max_length=32)
    publication_decision: str = Field(min_length=1, max_length=16)
    created_at: dt.datetime
    updated_at: dt.datetime


class ExecutionHistoryPageOut(OperatorProjectionModel):
    items: list[ExecutionHistoryItemOut]
    limit: int = Field(ge=1, le=MAX_OPERATOR_LIMIT)
    offset: int = Field(ge=0, le=MAX_OPERATOR_OFFSET)
    total: int = Field(ge=0)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _utc_naive(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(dt.UTC).replace(tzinfo=None)


def _fresh(value: dt.datetime | None, *, now: dt.datetime, seconds: int) -> bool:
    return value is not None and _utc_naive(value) >= now - dt.timedelta(
        seconds=seconds
    )


class ExecutionOperatorProjection:
    """Build stable operator views without exposing executable or sensitive data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(
        self,
        *,
        window_days: int,
        heartbeat_freshness_seconds: int,
        active_poll_freshness_seconds: int,
        now: dt.datetime | None = None,
    ) -> ExecutionOperatorOverviewOut:
        now = _utc_naive(now or utcnow_naive())
        starts_at = now - dt.timedelta(days=window_days)

        request_total = int(
            await self._session.scalar(
                select(func.count(GitHubValidationRequest.id)).where(
                    GitHubValidationRequest.created_at >= starts_at
                )
            )
            or 0
        )
        work_order_counts = await self._grouped_counts(
            ExecutionWorkOrder.status,
            ExecutionWorkOrder.created_at >= starts_at,
        )
        run_counts = await self._grouped_counts(
            ExecutionRun.status,
            ExecutionRun.created_at >= starts_at,
        )
        reuse_rows = (
            await self._session.execute(
                select(
                    ExecutionRun.reuse_decision,
                    ExecutionRun.status,
                    ExecutionRun.route_estimated_cost_units,
                    ExecutionRun.reused_from_run_id,
                ).where(ExecutionRun.created_at >= starts_at)
            )
        ).all()
        fresh = sum(
            status == ExecutionRunStatus.SUCCEEDED and decision == ReuseDecision.FRESH
            for decision, status, _cost, _source in reuse_rows
        )
        reused_rows = [
            row
            for row in reuse_rows
            if row.status == ExecutionRunStatus.SUCCEEDED
            and row.reuse_decision == ReuseDecision.REUSED
        ]
        reused = len(reused_rows)
        unavailable = sum(
            decision == ReuseDecision.UNAVAILABLE
            for decision, _status, _cost, _source in reuse_rows
        )
        source_ids = {
            row.reused_from_run_id for row in reused_rows if row.reused_from_run_id
        }
        source_durations: dict[int, float] = {}
        if source_ids:
            source_runs = (
                await self._session.execute(
                    select(
                        ExecutionRun.id,
                        ExecutionRun.started_at,
                        ExecutionRun.finished_at,
                    ).where(ExecutionRun.id.in_(source_ids))
                )
            ).all()
            source_durations = {
                run_id: max(0.0, (finished - started).total_seconds())
                for run_id, started, finished in source_runs
                if started is not None and finished is not None and finished >= started
            }
        seconds_avoided = sum(
            source_durations.get(row.reused_from_run_id, 0.0) for row in reused_rows
        )
        units_avoided = sum(
            row.route_estimated_cost_units
            for row in reused_rows
            if row.route_estimated_cost_units is not None
        )

        publication_counts = await self._grouped_counts(
            GitHubValidationRequest.publication_state,
            GitHubValidationRequest.created_at >= starts_at,
        )
        worker_rows = (
            await self._session.execute(
                select(
                    ExecutionWorker.status,
                    ExecutionWorker.active_run_count,
                    ExecutionWorker.max_concurrency,
                    ExecutionWorker.last_heartbeat_at,
                    ExecutionWorker.last_checkout_poll_at,
                )
            )
        ).all()
        worker_states = [
            _worker_activity_state(
                status=status,
                active_run_count=active_runs,
                max_concurrency=max_concurrency,
                last_heartbeat_at=heartbeat,
                last_checkout_poll_at=poll,
                now=now,
                heartbeat_freshness_seconds=heartbeat_freshness_seconds,
                active_poll_freshness_seconds=active_poll_freshness_seconds,
            )
            for status, active_runs, max_concurrency, heartbeat, poll in worker_rows
        ]
        denominator = fresh + reused
        return ExecutionOperatorOverviewOut(
            window=OperatorWindowOut(
                days=window_days,
                starts_at=starts_at.replace(tzinfo=dt.UTC),
                ends_at=now.replace(tzinfo=dt.UTC),
            ),
            requests=OperatorRequestMetricsOut(total=request_total),
            work_orders=OperatorWorkOrderMetricsOut(
                total=sum(work_order_counts.values()), by_status=work_order_counts
            ),
            runs=OperatorRunMetricsOut(
                total=sum(run_counts.values()),
                by_status=run_counts,
                fresh_successful=fresh,
                reused_successful=reused,
                unavailable_exact_reuse=unavailable,
            ),
            avoided_work=AvoidedWorkMetricsOut(
                deterministic_executions_avoided=reused,
                reference_seconds_avoided=seconds_avoided,
                comparison_units_avoided=units_avoided,
                reuse_rate=(reused / denominator if denominator else 0.0),
            ),
            publications=OperatorPublicationMetricsOut(
                current=publication_counts.get("published_current", 0),
                stale=publication_counts.get("published_stale", 0),
            ),
            workers=OperatorWorkerMetricsOut(
                total=len(worker_states),
                active=worker_states.count("active"),
                stale=worker_states.count("stale"),
                capacity_constrained=worker_states.count("capacity_constrained"),
            ),
        )

    async def list_workers(
        self,
        *,
        limit: int,
        offset: int,
        heartbeat_freshness_seconds: int,
        active_poll_freshness_seconds: int,
        now: dt.datetime | None = None,
    ) -> ExecutionWorkerPageOut:
        now = _utc_naive(now or utcnow_naive())
        total = int(
            await self._session.scalar(select(func.count(ExecutionWorker.id))) or 0
        )
        rows = (
            await self._session.execute(
                select(ExecutionWorker, WorkerRoutingProfile)
                .outerjoin(
                    WorkerRoutingProfile,
                    WorkerRoutingProfile.worker_id == ExecutionWorker.worker_id,
                )
                .order_by(ExecutionWorker.worker_id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        items = []
        for worker, profile in rows:
            profile_out = None
            if profile is not None:
                profile_out = RoutingProfileSummaryOut.model_validate(
                    {
                        "enabled": profile.enabled,
                        "estimated_cost_units_per_run": (
                            profile.estimated_cost_units_per_run
                        ),
                        "quota_capacity_units": profile.quota_capacity_units,
                        "quota_remaining_units": profile.quota_remaining_units,
                        "quota_reset_at": profile.quota_reset_at,
                        "routing_priority": profile.routing_priority,
                        "revision": profile.revision,
                        "updated_at": profile.updated_at,
                    }
                )
            items.append(
                ExecutionWorkerSummaryOut(
                    worker_id=worker.worker_id,
                    display_name=worker.display_name,
                    operating_system=worker.operating_system,
                    architecture=worker.architecture,
                    status=_enum_value(worker.status),
                    activity_state=_worker_activity_state(
                        status=worker.status,
                        active_run_count=worker.active_run_count,
                        max_concurrency=worker.max_concurrency,
                        last_heartbeat_at=worker.last_heartbeat_at,
                        last_checkout_poll_at=worker.last_checkout_poll_at,
                        now=now,
                        heartbeat_freshness_seconds=heartbeat_freshness_seconds,
                        active_poll_freshness_seconds=active_poll_freshness_seconds,
                    ),
                    active_run_count=worker.active_run_count,
                    max_concurrency=worker.max_concurrency,
                    last_heartbeat_at=worker.last_heartbeat_at,
                    last_checkout_poll_at=worker.last_checkout_poll_at,
                    profile=profile_out,
                )
            )
        return ExecutionWorkerPageOut(
            items=items, limit=limit, offset=offset, total=total
        )

    async def list_history(  # noqa: PLR0913
        self,
        *,
        limit: int,
        offset: int,
        repository_full_name: str | None = None,
        pull_request_number: int | None = None,
        work_order_status: str | None = None,
        run_status: str | None = None,
        reuse_decision: str | None = None,
        routing_policy: str | None = None,
        publication_state: str | None = None,
        created_after: dt.datetime | None = None,
        created_before: dt.datetime | None = None,
    ) -> ExecutionHistoryPageOut:
        latest_run = aliased(ExecutionRun)
        latest_run_id = (
            select(func.max(ExecutionRun.id))
            .where(ExecutionRun.work_order_id == ExecutionWorkOrder.id)
            .correlate(ExecutionWorkOrder)
            .scalar_subquery()
        )
        statement = (
            select(GitHubValidationRequest, ExecutionWorkOrder, latest_run)
            .join(
                ExecutionWorkOrder,
                ExecutionWorkOrder.id == GitHubValidationRequest.work_order_id,
            )
            .outerjoin(latest_run, latest_run.id == latest_run_id)
        )
        statement = self._history_filters(
            statement,
            latest_run=latest_run,
            repository_full_name=repository_full_name,
            pull_request_number=pull_request_number,
            work_order_status=work_order_status,
            run_status=run_status,
            reuse_decision=reuse_decision,
            routing_policy=routing_policy,
            publication_state=publication_state,
            created_after=created_after,
            created_before=created_before,
        )
        count_statement = select(func.count(GitHubValidationRequest.id)).join(
            ExecutionWorkOrder,
            ExecutionWorkOrder.id == GitHubValidationRequest.work_order_id,
        )
        if reuse_decision is not None or run_status is not None:
            count_statement = count_statement.outerjoin(
                latest_run, latest_run.id == latest_run_id
            )
        count_statement = self._history_filters(
            count_statement,
            latest_run=latest_run,
            repository_full_name=repository_full_name,
            pull_request_number=pull_request_number,
            work_order_status=work_order_status,
            run_status=run_status,
            reuse_decision=reuse_decision,
            routing_policy=routing_policy,
            publication_state=publication_state,
            created_after=created_after,
            created_before=created_before,
        )
        total = int(await self._session.scalar(count_statement) or 0)
        rows = (
            await self._session.execute(
                statement.order_by(
                    GitHubValidationRequest.created_at.desc(),
                    GitHubValidationRequest.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return ExecutionHistoryPageOut(
            items=[_history_item(request, order, run) for request, order, run in rows],
            limit=limit,
            offset=offset,
            total=total,
        )

    async def _grouped_counts(
        self, column: InstrumentedAttribute[Any], predicate: ColumnElement[bool]
    ) -> dict[str, int]:
        rows = (
            await self._session.execute(
                select(column, func.count()).where(predicate).group_by(column)
            )
        ).all()
        return {_enum_value(value): int(count) for value, count in rows}

    @staticmethod
    def _history_filters(  # noqa: PLR0913
        statement: Select[Any],
        *,
        latest_run: Any,
        repository_full_name: str | None,
        pull_request_number: int | None,
        work_order_status: str | None,
        run_status: str | None,
        reuse_decision: str | None,
        routing_policy: str | None,
        publication_state: str | None,
        created_after: dt.datetime | None,
        created_before: dt.datetime | None,
    ) -> Select[Any]:
        if repository_full_name is not None:
            statement = statement.where(
                GitHubValidationRequest.repository_full_name == repository_full_name
            )
        if pull_request_number is not None:
            statement = statement.where(
                GitHubValidationRequest.pull_request_number == pull_request_number
            )
        if work_order_status is not None:
            statement = statement.where(ExecutionWorkOrder.status == work_order_status)
        if run_status is not None:
            statement = statement.where(latest_run.status == run_status)
        if reuse_decision is not None:
            statement = statement.where(latest_run.reuse_decision == reuse_decision)
        if routing_policy is not None:
            statement = statement.where(
                ExecutionWorkOrder.routing_policy == routing_policy
            )
        if publication_state is not None:
            statement = statement.where(
                GitHubValidationRequest.publication_state == publication_state
            )
        if created_after is not None:
            statement = statement.where(
                GitHubValidationRequest.created_at >= _utc_naive(created_after)
            )
        if created_before is not None:
            statement = statement.where(
                GitHubValidationRequest.created_at <= _utc_naive(created_before)
            )
        return statement


def _worker_activity_state(  # noqa: PLR0913
    *,
    status: WorkerStatus,
    active_run_count: int,
    max_concurrency: int,
    last_heartbeat_at: dt.datetime,
    last_checkout_poll_at: dt.datetime | None,
    now: dt.datetime,
    heartbeat_freshness_seconds: int,
    active_poll_freshness_seconds: int,
) -> Literal["active", "stale", "capacity_constrained", "unavailable"]:
    if status != WorkerStatus.ONLINE:
        return "unavailable"
    if active_run_count >= max_concurrency:
        return "capacity_constrained"
    if not _fresh(
        last_heartbeat_at, now=now, seconds=heartbeat_freshness_seconds
    ) or not _fresh(
        last_checkout_poll_at, now=now, seconds=active_poll_freshness_seconds
    ):
        return "stale"
    return "active"


def _history_item(
    request: GitHubValidationRequest,
    order: ExecutionWorkOrder,
    run: ExecutionRun | None,
) -> ExecutionHistoryItemOut:
    fingerprint = None
    duration = None
    if run is not None:
        if isinstance(run.evidence_metadata, dict):
            candidate = run.evidence_metadata.get("fingerprint")
            if isinstance(candidate, str) and len(candidate) == SHA256_HEX_LENGTH:
                fingerprint = candidate
        if run.started_at is not None and run.finished_at is not None:
            duration = max(0.0, (run.finished_at - run.started_at).total_seconds())
    return ExecutionHistoryItemOut(
        request_id=request.id,
        repository_full_name=request.repository_full_name,
        pull_request_number=request.pull_request_number,
        tested_head_sha=request.head_sha,
        manifest_name=request.manifest_name,
        manifest_version=request.manifest_version,
        work_order_id=order.id,
        work_order_status=_enum_value(order.status),
        routing_policy=_enum_value(order.routing_policy),
        preferred_executor=order.preferred_executor,
        maximum_cost_units=order.maximum_cost_units,
        required_quota_units=order.required_quota_units,
        run_id=run.id if run is not None else None,
        run_status=_enum_value(run.status) if run is not None else None,
        selected_worker_id=run.worker_id if run is not None else None,
        estimated_cost_units=(
            run.route_estimated_cost_units if run is not None else None
        ),
        reuse_decision=_enum_value(run.reuse_decision) if run is not None else None,
        reused_from_run_id=run.reused_from_run_id if run is not None else None,
        run_duration_seconds=duration,
        evidence_fingerprint=fingerprint,
        publication_state=request.publication_state,
        publication_decision=request.publication_decision,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


__all__ = [
    "MAX_OPERATOR_LIMIT",
    "MAX_OPERATOR_OFFSET",
    "MAX_OPERATOR_WINDOW_DAYS",
    "ExecutionHistoryPageOut",
    "ExecutionOperatorOverviewOut",
    "ExecutionOperatorProjection",
    "ExecutionWorkerPageOut",
]
