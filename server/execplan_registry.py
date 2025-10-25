"""Helpers for persisting and presenting ExecPlan registry metadata."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from email.utils import format_datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ExecPlan, ExecPlanRegistry
from .schema import (
    ExecPlanEntry,
    ExecPlanLifecycle,
    ExecPlanOwner,
    ExecPlanRegistryIndex,
    ExecPlanRegistrySource,
)
from .time_utils import utcnow

DEFAULT_REGISTRY_ID = "switchboard-default"
DEFAULT_SCHEMA_VERSION = 1

__all__ = ["build_registry_index", "ensure_registry", "load_plans"]


def _as_utc(value: dt.datetime) -> dt.datetime:
    """Return ``value`` as a timezone-aware UTC datetime."""

    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _normalize_timestamp(value: dt.datetime) -> dt.datetime:
    """Return a naive UTC datetime suitable for serialization."""

    if value.tzinfo is None:
        return value
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)


def _optional_owners(
    raw: list[dict[str, Any]] | None,
) -> list[ExecPlanOwner] | None:
    """Normalize optional owner payloads into ``ExecPlanOwner`` models."""

    if not raw:
        return None
    return [ExecPlanOwner(**owner) for owner in raw]


def _optional_lifecycle(plan: ExecPlan) -> ExecPlanLifecycle | None:
    """Return lifecycle metadata for ``plan`` when at least one field exists."""

    lifecycle_fields = (
        plan.lifecycle_created_at,
        plan.lifecycle_updated_at,
        plan.lifecycle_target_completion,
    )
    if not any(lifecycle_fields):
        return None
    return ExecPlanLifecycle(
        created_at=plan.lifecycle_created_at,
        updated_at=plan.lifecycle_updated_at,
        target_completion=plan.lifecycle_target_completion,
    )


def _optional_list(value: list[Any] | None) -> list[Any] | None:
    """Return ``value`` when truthy, otherwise ``None`` for clean JSON output."""

    if not value:
        return None
    return value


def _optional_dict(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return ``value`` when truthy, otherwise ``None`` for clean JSON output."""

    if not value:
        return None
    return value


def _plan_timestamp(plan: ExecPlan) -> Iterable[dt.datetime]:
    """Yield timestamp candidates that should influence ``generated_at``."""

    for candidate in (
        plan.updated_at,
        plan.lifecycle_updated_at,
        plan.lifecycle_created_at,
        plan.created_at,
    ):
        if candidate:
            yield _normalize_timestamp(candidate)


async def ensure_registry(session: AsyncSession) -> ExecPlanRegistry:
    """Return the singleton ExecPlan registry, creating it if needed."""

    stmt = select(ExecPlanRegistry).order_by(ExecPlanRegistry.id).limit(1)
    registry = (await session.execute(stmt)).scalar_one_or_none()
    if registry is None:
        registry = ExecPlanRegistry(
            registry_id=DEFAULT_REGISTRY_ID,
            schema_version=DEFAULT_SCHEMA_VERSION,
            generated_at=utcnow().replace(tzinfo=None),
        )
        session.add(registry)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            registry = (await session.execute(stmt)).scalar_one()
    return registry


async def load_plans(session: AsyncSession) -> list[ExecPlan]:
    """Return ExecPlan rows ordered for deterministic registry serialization."""

    rows = await session.execute(select(ExecPlan).order_by(ExecPlan.plan_id))
    return list(rows.scalars().all())


def _latest_generated_at(
    registry: ExecPlanRegistry, plans: Iterable[ExecPlan]
) -> dt.datetime:
    """Return the most recent timestamp across the registry and provided plans."""

    candidates: list[dt.datetime] = []
    if registry.generated_at:
        candidates.append(_normalize_timestamp(registry.generated_at))
    for plan in plans:
        candidates.extend(_plan_timestamp(plan))
    if not candidates:
        return utcnow()
    latest = max(candidates)
    return _as_utc(latest)


def _compute_etag(payload: dict[str, Any]) -> str:
    """Return a weak ETag derived from a canonical JSON representation."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f'W/"{digest[:32]}"'


def _http_date(timestamp: dt.datetime) -> str:
    """Return an HTTP-date string suitable for ``Last-Modified`` headers."""

    return format_datetime(_as_utc(timestamp), usegmt=True)


async def build_registry_index(
    session: AsyncSession, *, source_url: str
) -> tuple[dict[str, Any], str, dt.datetime, str]:
    """Return the serialized ExecPlan index and related caching metadata."""

    registry = await ensure_registry(session)
    # TODO(P3, 5d) - Cache the serialized registry when inputs are unchanged to
    # reduce database load.
    plans = await load_plans(session)
    generated_at = _latest_generated_at(registry, plans)

    entry_models = [
        ExecPlanEntry(
            plan_id=plan.plan_id,
            title=plan.title,
            summary=plan.summary,
            status=plan.status,
            lifecycle=_optional_lifecycle(plan),
            owners=_optional_owners(plan.owners),
            tags=_optional_list(plan.tags),
            scope=_optional_dict(plan.scope),
            links=_optional_dict(plan.links) or {},
            metrics=_optional_dict(plan.metrics),
            changelog_token=plan.changelog_token,
            extensions=_optional_list(plan.extensions),
        )
        for plan in plans
    ]

    index_model = ExecPlanRegistryIndex(
        version=registry.schema_version or DEFAULT_SCHEMA_VERSION,
        registry_id=registry.registry_id or DEFAULT_REGISTRY_ID,
        generated_at=generated_at,
        source=ExecPlanRegistrySource(url=registry.source_url or source_url),
        plans=entry_models,
        extensions=_optional_list(registry.extensions),
    )

    payload = index_model.model_dump(mode="json", exclude_none=True)
    payload.setdefault("source", {})
    payload["source"]["url"] = source_url

    digest_input = deepcopy(payload)
    source_section = digest_input.get("source")
    if source_section and "etag" in source_section:
        source_section.pop("etag")
    etag = _compute_etag(digest_input)
    payload["source"]["etag"] = etag

    registry.generated_at = generated_at.replace(tzinfo=None)
    registry.source_url = payload["source"].get("url")
    registry.source_etag = etag
    if registry.schema_version is None:
        registry.schema_version = DEFAULT_SCHEMA_VERSION
    if not registry.registry_id:
        registry.registry_id = DEFAULT_REGISTRY_ID
    await session.flush()

    return payload, etag, generated_at, _http_date(generated_at)
