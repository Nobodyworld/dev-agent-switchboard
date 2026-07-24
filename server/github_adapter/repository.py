"""Persistence operations for GitHub adapter identity and publication state."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models import GitHubValidationRequest


class GitHubAdapterRepository:
    """Store one idempotent adapter record per immutable GitHub request."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, values: dict[str, Any]) -> GitHubValidationRequest:
        """Insert and flush one adapter request without committing it."""

        request = GitHubValidationRequest(**values)
        self.session.add(request)
        await self.session.flush()
        return request

    async def get(
        self, request_id: int, *, refresh: bool = False
    ) -> GitHubValidationRequest | None:
        """Return an adapter request, optionally bypassing cached ORM state."""

        if refresh:
            result = await self.session.execute(
                select(GitHubValidationRequest)
                .where(GitHubValidationRequest.id == request_id)
                .execution_options(populate_existing=True)
            )
            return result.scalar_one_or_none()
        return await self.session.get(GitHubValidationRequest, request_id)

    async def get_by_idempotency_key(
        self, idempotency_key: str, *, refresh: bool = False
    ) -> GitHubValidationRequest | None:
        """Return the immutable request bound to one deterministic key."""

        statement = select(GitHubValidationRequest).where(
            GitHubValidationRequest.idempotency_key == idempotency_key
        )
        if refresh:
            statement = statement.execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def flush(self) -> None:
        """Flush bounded lifecycle mutations into the current transaction."""

        await self.session.flush()


__all__ = ["GitHubAdapterRepository"]
