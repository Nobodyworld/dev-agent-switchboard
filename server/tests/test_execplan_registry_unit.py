import pytest
import sqlalchemy as sa

from server.db import AsyncSessionLocal
from server.execplan_registry import (
    DEFAULT_REGISTRY_ID,
    DEFAULT_SCHEMA_VERSION,
    ensure_registry,
)
from server.models import ExecPlanRegistry
from server.time_utils import utcnow

MIN_EXPECTED_EXECUTE_CALLS = 2


@pytest.mark.asyncio
async def test_ensure_registry_creates_singleton() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(ExecPlanRegistry))
        await session.commit()

    async with AsyncSessionLocal() as session:
        registry = await ensure_registry(session)
        assert registry.registry_id == DEFAULT_REGISTRY_ID
        assert registry.schema_version == DEFAULT_SCHEMA_VERSION
        await session.commit()

    async with AsyncSessionLocal() as session:
        registry = await ensure_registry(session)
        assert registry.registry_id == DEFAULT_REGISTRY_ID


@pytest.mark.asyncio
async def test_ensure_registry_handles_integrity_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(ExecPlanRegistry))
        await session.commit()

    async with AsyncSessionLocal() as session:
        original_execute = session.execute
        original_flush = session.flush
        state = {"execute_calls": 0, "flush_calls": 0}

        async def fake_execute(statement, *args, **kwargs):
            state["execute_calls"] += 1
            if state["execute_calls"] == 1:
                class _Result:
                    def scalar_one_or_none(self) -> None:
                        return None

                return _Result()
            return await original_execute(statement, *args, **kwargs)

        async def fake_flush(*args, **kwargs):
            if state["flush_calls"] == 0:
                state["flush_calls"] += 1
                async with AsyncSessionLocal() as other:
                    other.add(
                        ExecPlanRegistry(
                            registry_id=DEFAULT_REGISTRY_ID,
                            schema_version=DEFAULT_SCHEMA_VERSION,
                            generated_at=utcnow().replace(tzinfo=None),
                        )
                    )
                    await other.commit()
                raise sa.exc.IntegrityError("insert", {}, Exception("duplicate"))
            return await original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "execute", fake_execute)
        monkeypatch.setattr(session, "flush", fake_flush)

        registry = await ensure_registry(session)
        assert registry.registry_id == DEFAULT_REGISTRY_ID
        assert state["execute_calls"] >= MIN_EXPECTED_EXECUTE_CALLS
        assert state["flush_calls"] == 1

    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(ExecPlanRegistry))
        await session.commit()
