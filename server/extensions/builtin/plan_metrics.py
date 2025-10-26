"""Builtin plan observer that updates task analytics metrics."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry
from server.observability.metrics import record_task_analytics_metrics

LOGGER = logging.getLogger(__name__)


class PlanMetricsObserver:
    """Emit Prometheus gauges whenever the plan is broadcast."""

    async def on_plan_broadcast(
        self,
        *,
        version: int | None,
        plan: Mapping[str, Any] | None,
        delta: Mapping[str, Any] | None,
        analytics: Any | None,
    ) -> None:
        # NOTE: ``broadcast_plan`` delivers keyword arguments for the broadcasted
        # version, plan, and delta.  They are currently unused by this observer,
        # but we accept them explicitly to remain signature-compatible with the
        # extension contract and avoid unexpected keyword errors when new call
        # sites use named arguments.
        _ = (version, plan, delta)
        if analytics is None:
            return
        updated = record_task_analytics_metrics(analytics=analytics)
        if not updated:
            LOGGER.debug(
                "Plan metrics observer skipped analytics update because metrics "
                "are disabled or unavailable."
            )


def register(registry: ExtensionRegistry) -> None:
    """Register the builtin plan metrics observer."""

    registry.register_extension(
        ExtensionDescriptor(
            name="builtin.plan_metrics",
            capabilities=("metrics", "plan_observer"),
            version="1.0.0",
            description="Updates task analytics Prometheus gauges on plan broadcasts.",
            config={"requires_metrics": True},
        )
    )
    registry.append_contract_note(
        "Plan metrics observer emits Prometheus gauges when SWITCHBOARD_ENABLE_METRICS=1."
    )
    registry.register_plan_observer(PlanMetricsObserver())


register_extension = register
