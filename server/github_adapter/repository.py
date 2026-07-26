"""Persistence operations for GitHub adapter identity and publication state."""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
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

    async def acquire_publication_claim(
        self,
        request_id: int,
        *,
        token: str,
        claimed_at: dt.datetime,
        expires_at: dt.datetime,
    ) -> bool:
        """Atomically acquire and commit one cross-process publication lease."""

        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(GitHubValidationRequest)
                .where(
                    GitHubValidationRequest.id == request_id,
                    or_(
                        GitHubValidationRequest.publication_claim_token.is_(None),
                        GitHubValidationRequest.publication_claim_expires_at
                        <= claimed_at,
                    ),
                )
                .values(
                    publication_claim_token=token,
                    publication_claimed_at=claimed_at,
                    publication_claim_expires_at=expires_at,
                    last_publication_attempt_at=claimed_at,
                    publication_reason="github_publication_in_progress",
                )
            ),
        )
        acquired = result.rowcount == 1
        if acquired:
            await self.session.commit()
        else:
            await self.session.rollback()
        return acquired

    async def finalize_publication_claim(
        self,
        request_id: int,
        *,
        token: str,
        values: dict[str, Any],
    ) -> bool:
        """Conditionally persist a result and release only the matching lease."""

        forbidden = {
            "id",
            "publication_claim_token",
            "publication_claimed_at",
            "publication_claim_expires_at",
        }
        if forbidden.intersection(values):
            raise ValueError("invalid publication finalization fields")
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(GitHubValidationRequest)
                .where(
                    and_(
                        GitHubValidationRequest.id == request_id,
                        GitHubValidationRequest.publication_claim_token == token,
                    )
                )
                .values(
                    **values,
                    publication_claim_token=None,
                    publication_claimed_at=None,
                    publication_claim_expires_at=None,
                )
            ),
        )
        finalized = result.rowcount == 1
        if finalized:
            await self.session.commit()
        else:
            await self.session.rollback()
        return finalized

    async def renew_publication_claim(
        self,
        request_id: int,
        *,
        token: str,
        renewed_at: dt.datetime,
        expires_at: dt.datetime,
    ) -> bool:
        """Extend only a still-current, unexpired lease before a remote write."""

        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(GitHubValidationRequest)
                .where(
                    GitHubValidationRequest.id == request_id,
                    GitHubValidationRequest.publication_claim_token == token,
                    GitHubValidationRequest.publication_claim_expires_at > renewed_at,
                )
                .values(publication_claim_expires_at=expires_at)
            ),
        )
        renewed = result.rowcount == 1
        await self.session.commit()
        return renewed

    async def release_publication_claim(self, request_id: int, *, token: str) -> bool:
        """Release only the caller's still-current lease after local failure."""

        return await self.finalize_publication_claim(
            request_id,
            token=token,
            values={},
        )


__all__ = ["GitHubAdapterRepository"]
