"""Deterministic eligibility and scoring for trusted local workers."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cmp_to_key
from typing import Any

from server.models import (
    ExecutionWorker,
    WorkerRoutingProfile,
)

from .capabilities import match_worker_capabilities
from .enums import NetworkPolicy, RoutingPolicy, WorkerStatus

ROUTING_SCHEMA_VERSION = 1
MAX_ROUTING_INTEGER = 2_147_483_647


@dataclass(frozen=True, slots=True)
class RoutingCandidate:
    """One fully eligible worker with authoritative operator profile state."""

    worker: ExecutionWorker
    profile: WorkerRoutingProfile | None

    @property
    def quota_headroom(self) -> int:
        """Return quota remaining after the prospective reservation."""

        return self.profile.quota_remaining_units if self.profile is not None else 0


@dataclass(frozen=True, slots=True)
class RoutingEvaluationRequest:
    """Complete pure input shared by checkout, assessment, and readiness."""

    repository_full_name: str
    routing_policy: RoutingPolicy
    preferred_executor: str | None
    maximum_cost_units: int | None
    required_quota_units: int
    manifest_requirements: Mapping[str, Any]
    requested_requirements: Mapping[str, Any]
    network_policy: NetworkPolicy


@dataclass(frozen=True, slots=True)
class RoutingEligibility:
    """Fail-closed eligibility outcome for one worker and work order."""

    worker: ExecutionWorker
    profile: WorkerRoutingProfile | None
    candidate: RoutingCandidate | None
    reasons: tuple[str, ...]


def evaluate_routing_candidate(  # noqa: PLR0912,PLR0913
    worker: ExecutionWorker,
    profile: WorkerRoutingProfile | None,
    *,
    request: RoutingEvaluationRequest,
    now: dt.datetime,
    heartbeat_freshness_seconds: int,
    active_poll_freshness_seconds: int,
) -> RoutingEligibility:
    """Evaluate every routed-worker safety and policy requirement."""

    reasons: list[str] = []
    repository_full_names = worker.repository_full_names or [
        "Nobodyworld/dev-agent-switchboard"
    ]
    if request.repository_full_name not in repository_full_names:
        reasons.append("worker_repository_unavailable")
    if request.preferred_executor is not None and (
        worker.worker_id != request.preferred_executor
    ):
        reasons.append("preferred_executor_mismatch")
    if request.routing_policy == RoutingPolicy.CHEAPEST_CAPABLE:
        if profile is None:
            reasons.append("routing_profile_missing")
        elif not _valid_profile(profile):
            reasons.append("routing_profile_invalid")
        elif not profile.enabled:
            reasons.append("routing_profile_disabled")

    if worker.status != WorkerStatus.ONLINE:
        reasons.append("worker_not_available")
    if worker.active_run_count >= worker.max_concurrency:
        reasons.append("worker_concurrency_limit")
    if not _fresh(
        worker.last_heartbeat_at,
        now=now,
        freshness_seconds=heartbeat_freshness_seconds,
    ):
        reasons.append("worker_heartbeat_stale")
    if not _fresh(
        worker.last_checkout_poll_at,
        now=now,
        freshness_seconds=active_poll_freshness_seconds,
    ):
        reasons.append("worker_checkout_poll_stale")

    capability_match = match_worker_capabilities(
        worker,
        manifest_requirements=request.manifest_requirements,
        requested_requirements=request.requested_requirements,
        network_policy=request.network_policy,
    )
    reasons.extend(capability_match.reasons)

    if (
        request.routing_policy == RoutingPolicy.CHEAPEST_CAPABLE
        and profile is not None
        and _valid_profile(profile)
    ):
        if (
            request.maximum_cost_units is not None
            and profile.estimated_cost_units_per_run > request.maximum_cost_units
        ):
            reasons.append("routing_cost_ceiling_exceeded")
        if profile.quota_remaining_units < request.required_quota_units:
            reasons.append("routing_quota_insufficient")

    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        return RoutingEligibility(worker, profile, None, unique_reasons)
    return RoutingEligibility(worker, profile, RoutingCandidate(worker, profile), ())


def rank_routing_candidates(
    candidates: list[RoutingCandidate], *, required_quota_units: int
) -> list[RoutingCandidate]:
    """Return candidates in the exact locked deterministic score order."""

    def compare(first: RoutingCandidate, second: RoutingCandidate) -> int:
        first_profile = first.profile
        second_profile = second.profile
        if first_profile is None or second_profile is None:
            raise ValueError("ranked routing candidates require profiles")
        if (
            first_profile.estimated_cost_units_per_run
            != second_profile.estimated_cost_units_per_run
        ):
            return (
                -1
                if (
                    first_profile.estimated_cost_units_per_run
                    < second_profile.estimated_cost_units_per_run
                )
                else 1
            )

        first_headroom = first_profile.quota_remaining_units - required_quota_units
        second_headroom = second_profile.quota_remaining_units - required_quota_units
        if first_headroom != second_headroom:
            return -1 if first_headroom > second_headroom else 1

        first_load = first.worker.active_run_count * second.worker.max_concurrency
        second_load = second.worker.active_run_count * first.worker.max_concurrency
        if first_load != second_load:
            return -1 if first_load < second_load else 1

        if first_profile.routing_priority != second_profile.routing_priority:
            return (
                -1
                if (first_profile.routing_priority < second_profile.routing_priority)
                else 1
            )
        if first.worker.worker_id == second.worker.worker_id:
            return 0
        return -1 if first.worker.worker_id < second.worker.worker_id else 1

    return sorted(candidates, key=cmp_to_key(compare))


def unavailable_route_reason(mismatch_reasons: list[str], *, explicit_pin: bool) -> str:
    """Collapse detailed eligibility failures into one bounded route reason."""

    if explicit_pin:
        return "preferred_executor_unavailable"
    precedence = (
        "worker_repository_unavailable",
        "routing_profile_missing",
        "routing_profile_invalid",
        "routing_profile_disabled",
        "worker_heartbeat_stale",
        "worker_checkout_poll_stale",
        "worker_not_available",
        "worker_concurrency_limit",
        "routing_cost_ceiling_exceeded",
        "routing_quota_insufficient",
    )
    for reason in precedence:
        if reason in mismatch_reasons:
            return reason
    return "no_capable_workers"


def _valid_profile(profile: WorkerRoutingProfile) -> bool:
    values = (
        profile.estimated_cost_units_per_run,
        profile.quota_capacity_units,
        profile.quota_remaining_units,
        profile.routing_priority,
        profile.revision,
    )
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        return False
    return (
        profile.schema_version == ROUTING_SCHEMA_VERSION
        and 0 <= profile.estimated_cost_units_per_run <= MAX_ROUTING_INTEGER
        and 0 <= profile.quota_capacity_units <= MAX_ROUTING_INTEGER
        and 0 <= profile.quota_remaining_units <= profile.quota_capacity_units
        and 0 <= profile.routing_priority <= MAX_ROUTING_INTEGER
        and 1 <= profile.revision <= MAX_ROUTING_INTEGER
    )


def _fresh(
    value: dt.datetime | None,
    *,
    now: dt.datetime,
    freshness_seconds: int,
) -> bool:
    if value is None or freshness_seconds <= 0:
        return False
    normalized_value = _utc_naive(value)
    normalized_now = _utc_naive(now)
    return normalized_value >= normalized_now - dt.timedelta(seconds=freshness_seconds)


def _utc_naive(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(dt.UTC).replace(tzinfo=None)


__all__ = [
    "MAX_ROUTING_INTEGER",
    "ROUTING_SCHEMA_VERSION",
    "RoutingCandidate",
    "RoutingEligibility",
    "RoutingEvaluationRequest",
    "evaluate_routing_candidate",
    "rank_routing_candidates",
    "unavailable_route_reason",
]
