"""Strict API contracts for the manual GitHub exact-PR adapter."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.execution.catalog import validate_repository_full_name
from server.execution.enums import ReusePolicy, RoutingPolicy
from server.execution.routing import MAX_ROUTING_INTEGER

from .service import GitHubRequestStatus


class GitHubAdapterInput(BaseModel):
    """Reject every caller field not explicitly owned by the manual workflow."""

    model_config = ConfigDict(extra="forbid")


class GitHubManifestReferenceIn(GitHubAdapterInput):
    """Identity-only trusted manifest reference with no caller parameters."""

    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(min_length=1, max_length=64)


class GitHubValidationCreateIn(GitHubAdapterInput):
    """The only caller-controlled fields for exact-PR validation."""

    repository_full_name: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    pull_request_number: int = Field(ge=1, le=2_147_483_647)
    manifest: GitHubManifestReferenceIn
    reuse_policy: ReusePolicy = ReusePolicy.NEVER
    routing_policy: RoutingPolicy = RoutingPolicy.FIRST_AVAILABLE
    maximum_cost_units: int | None = Field(
        default=None, strict=True, ge=0, le=MAX_ROUTING_INTEGER
    )
    required_quota_units: int = Field(
        default=0, strict=True, ge=0, le=MAX_ROUTING_INTEGER
    )
    preferred_executor: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("repository_full_name")
    @classmethod
    def validate_repository_identity(cls, value: str) -> str:
        return validate_repository_full_name(value)


class GitHubValidationRequestOut(BaseModel):
    """Bounded adapter provenance and linked lifecycle without remote bodies."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    request_id: int
    schema_version: Literal[1]
    github_host: str = Field(min_length=1, max_length=255)
    repository_full_name: str = Field(min_length=3, max_length=255)
    repository_id: int = Field(ge=1)
    repository_node_id: str = Field(min_length=1, max_length=128)
    pull_request_number: int = Field(ge=1)
    pull_request_id: int = Field(ge=1)
    pull_request_node_id: str = Field(min_length=1, max_length=128)
    pull_request_state: Literal["open", "closed"]
    pull_request_draft: bool
    pull_request_merged: bool
    tested_head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest_name: str = Field(min_length=1, max_length=128)
    manifest_version: str = Field(min_length=1, max_length=64)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operator_id: str = Field(min_length=1, max_length=128)
    work_order_id: int = Field(ge=1)
    work_order_status: str = Field(min_length=1, max_length=32)
    reuse_policy: ReusePolicy
    routing_policy: RoutingPolicy
    maximum_cost_units: int | None = Field(default=None, ge=0)
    required_quota_units: int = Field(ge=0)
    preferred_executor: str | None = Field(default=None, max_length=128)
    terminal_run_id: int | None = Field(default=None, ge=1)
    terminal_run_status: str | None = Field(default=None, max_length=32)
    evidence_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    managed_comment_id: int | None = Field(default=None, ge=1)
    publication_state: Literal[
        "not_published",
        "published_current",
        "published_stale",
        "retryable_failure",
        "failed",
    ]
    publication_decision: Literal["not_evaluated", "current", "stale"]
    publication_head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    transport_reason: str | None = Field(default=None, max_length=64)
    publication_reason: str | None = Field(default=None, max_length=64)
    created_at: dt.datetime
    updated_at: dt.datetime
    last_resolved_at: dt.datetime
    last_publication_attempt_at: dt.datetime | None
    published_at: dt.datetime | None

    @classmethod
    def from_status(cls, status: GitHubRequestStatus) -> GitHubValidationRequestOut:
        """Validate a service snapshot at the final response boundary."""

        return cls.model_validate(status)


__all__ = [
    "GitHubManifestReferenceIn",
    "GitHubValidationCreateIn",
    "GitHubValidationRequestOut",
]
