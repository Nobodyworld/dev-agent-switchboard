"""Agent registration routes."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.dependencies import (
    OptionalSessionDependency,
    OptionalTaskServiceDependency,
    resolve_task_service,
)
from server.application import TaskService
from server.domain import Agent
from server.schema import AgentIn, AgentRegistrationResponse

router = APIRouter()


def _require_session(
    session: OptionalSessionDependency | AsyncSession | None,
) -> AsyncSession:
    if isinstance(session, AsyncSession):
        return session
    raise RuntimeError("AsyncSession is required for agent operations")


@router.post("/api/agents", response_model=AgentRegistrationResponse)
async def register_agent(
    agent: AgentIn,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> AgentRegistrationResponse:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    await resolved.ensure_agent(Agent(agent_id=agent.agent_name))
    await db_session.commit()
    return AgentRegistrationResponse(ok=True, agent_id=agent.agent_name)
