"""Security regressions for trusted executable worker manifests."""

from __future__ import annotations

from dataclasses import replace
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

from server.app import app
from server.execution.registry import TrustedStep, get_trusted_manifest


def test_worker_smoke_digest_binds_fixed_executable_fields() -> None:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    assert manifest.execution_steps

    first = manifest.execution_steps[0]
    changed_step = replace(first, argv=("python", "-VV"))
    changed_manifest = replace(
        manifest,
        execution_steps=(changed_step, *manifest.execution_steps[1:]),
        fixed_step_metadata=[
            changed_step.safe_metadata(),
            *[step.safe_metadata() for step in manifest.execution_steps[1:]],
        ],
    )

    assert changed_manifest.digest != manifest.digest


def test_worker_smoke_steps_are_fixed_read_only_and_shellless() -> None:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None

    assert [step.id for step in manifest.execution_steps] == [
        "python-version",
        "git-head",
    ]
    assert all(isinstance(step.argv, tuple) for step in manifest.execution_steps)
    assert manifest.execution_steps[0].argv == ("python", "--version")
    assert manifest.execution_steps[1].argv == ("git", "rev-parse", "HEAD")
    assert manifest.repository_write_policy.value == "read_only"


def test_trusted_step_rejects_escaping_working_directory() -> None:
    with pytest.raises(ValueError, match="working directory"):
        TrustedStep(
            id="escape",
            title="Escape",
            argv=("python", "--version"),
            required=True,
            timeout_seconds=10,
            working_directory="../outside",
        )


@pytest.mark.asyncio
async def test_manifest_api_never_exposes_executable_fields() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/execution/manifests/worker-smoke/1")

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    serialized = str(payload).lower()
    assert payload["name"] == "worker-smoke"
    assert "argv" not in serialized
    assert "executable" not in serialized
    assert "shell" not in serialized
    assert payload["fixed_step_metadata"] == [
        {
            "id": "python-version",
            "required": True,
            "timeout_seconds": 60,
            "output_summary_limit": 4096,
        },
        {
            "id": "git-head",
            "required": True,
            "timeout_seconds": 60,
            "output_summary_limit": 4096,
        },
    ]


def test_validate_switchboard_remains_metadata_only() -> None:
    manifest = get_trusted_manifest("validate-switchboard", "1")
    assert manifest is not None
    assert manifest.execution_steps == ()
