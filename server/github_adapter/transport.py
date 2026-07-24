"""Fixed-route, bounded GitHub REST transport for exact-PR validation."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from server.settings import GitHubSettings

from .errors import (
    GitHubAmbiguousWriteError,
    GitHubRateLimitedError,
    GitHubTransportError,
)

MAX_GITHUB_RESPONSE_BYTES = 512 * 1024
MAX_GITHUB_STRING_LENGTH = 65_536
MAX_GITHUB_COLLECTION_ITEMS = 100
MAX_GITHUB_JSON_NODES = 20_000
MAX_GITHUB_NODE_ID_LENGTH = 128
MAX_MANAGED_COMMENT_BYTES = 12 * 1024
MAX_SAFE_GITHUB_ID = (1 << 63) - 1
MAX_SAFE_PULL_REQUEST_NUMBER = 2_147_483_647
SAFE_READ_ATTEMPTS = 3

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NODE_ID = re.compile(
    rf"^[A-Za-z0-9_=-]{{1,{MAX_GITHUB_NODE_ID_LENGTH}}}$"
)
_DISPLAY_TEXT = re.compile(r"^[^\x00-\x1f\x7f]{1,255}$")
_TRANSIENT_READ_STATUSES = frozenset({502, 503, 504})
_AMBIGUOUS_WRITE_STATUSES = frozenset({408, 425, 500, 502, 503, 504})

_REPOSITORY_FIELDS = frozenset(
    {
        "id",
        "node_id",
        "name",
        "full_name",
        "private",
        "owner",
        "html_url",
        "description",
        "fork",
        "url",
        "forks_url",
        "keys_url",
        "collaborators_url",
        "teams_url",
        "hooks_url",
        "issue_events_url",
        "events_url",
        "assignees_url",
        "branches_url",
        "tags_url",
        "blobs_url",
        "git_tags_url",
        "git_refs_url",
        "trees_url",
        "statuses_url",
        "languages_url",
        "stargazers_url",
        "contributors_url",
        "subscribers_url",
        "subscription_url",
        "commits_url",
        "git_commits_url",
        "comments_url",
        "issue_comment_url",
        "contents_url",
        "compare_url",
        "merges_url",
        "archive_url",
        "downloads_url",
        "issues_url",
        "pulls_url",
        "milestones_url",
        "notifications_url",
        "labels_url",
        "releases_url",
        "deployments_url",
        "created_at",
        "updated_at",
        "pushed_at",
        "git_url",
        "ssh_url",
        "clone_url",
        "svn_url",
        "homepage",
        "size",
        "stargazers_count",
        "watchers_count",
        "language",
        "has_issues",
        "has_projects",
        "has_downloads",
        "has_wiki",
        "has_pages",
        "has_discussions",
        "forks_count",
        "mirror_url",
        "archived",
        "disabled",
        "open_issues_count",
        "license",
        "allow_forking",
        "is_template",
        "web_commit_signoff_required",
        "topics",
        "visibility",
        "forks",
        "open_issues",
        "watchers",
        "default_branch",
        "temp_clone_token",
        "network_count",
        "subscribers_count",
        "permissions",
        "organization",
        "security_and_analysis",
        "custom_properties",
    }
)
_PULL_REQUEST_FIELDS = frozenset(
    {
        "url",
        "id",
        "node_id",
        "html_url",
        "diff_url",
        "patch_url",
        "issue_url",
        "number",
        "state",
        "locked",
        "title",
        "user",
        "body",
        "created_at",
        "updated_at",
        "closed_at",
        "merged_at",
        "merge_commit_sha",
        "assignee",
        "assignees",
        "requested_reviewers",
        "requested_teams",
        "labels",
        "milestone",
        "draft",
        "commits_url",
        "review_comments_url",
        "review_comment_url",
        "comments_url",
        "statuses_url",
        "head",
        "base",
        "_links",
        "author_association",
        "auto_merge",
        "active_lock_reason",
        "merged",
        "mergeable",
        "rebaseable",
        "mergeable_state",
        "merged_by",
        "comments",
        "review_comments",
        "maintainer_can_modify",
        "commits",
        "additions",
        "deletions",
        "changed_files",
    }
)
_PULL_REF_FIELDS = frozenset({"label", "ref", "sha", "user", "repo"})
_COMMENT_FIELDS = frozenset(
    {
        "url",
        "html_url",
        "issue_url",
        "id",
        "node_id",
        "user",
        "created_at",
        "updated_at",
        "author_association",
        "body",
        "reactions",
        "performed_via_github_app",
    }
)


@dataclass(frozen=True, slots=True)
class GitHubRepositoryIdentity:
    """Stable repository identity projected from bounded GitHub metadata."""

    full_name: str
    repository_id: int
    node_id: str


@dataclass(frozen=True, slots=True)
class ResolvedPullRequest:
    """Bounded GitHub PR provenance; remote display text remains non-executable."""

    repository_full_name: str
    repository_id: int
    repository_node_id: str
    pull_request_number: int
    pull_request_id: int
    pull_request_node_id: str
    state: str
    draft: bool
    merged: bool
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str | None
    head_repository_full_name: str | None
    head_repository_id: int | None


@dataclass(frozen=True, slots=True)
class GitHubComment:
    """The only remote comment fields retained by the adapter."""

    comment_id: int
    body: str


class GitHubTransport:
    """Perform only the five fixed GitHub operations required by issue #122."""

    def __init__(
        self,
        settings: GitHubSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._base_url = f"{settings.api_url.rstrip('/')}/"
        parsed = urlsplit(self._base_url)
        self._expected_origin = (
            parsed.scheme.lower(),
            parsed.hostname.lower() if parsed.hostname else "",
            parsed.port,
        )
        self._expected_path_prefix = parsed.path

    async def resolve_pull_request(
        self,
        repository_full_name: str,
        pull_request_number: int,
        *,
        require_head: bool = True,
    ) -> ResolvedPullRequest:
        """Resolve stable repository/PR identity and an optional exact head."""

        repository_path, owner, repository_name = _repository_route(
            repository_full_name
        )
        if not 1 <= pull_request_number <= MAX_SAFE_PULL_REQUEST_NUMBER:
            raise GitHubTransportError("github_transport_failed")
        repository_payload = await self._request_json(
            "GET",
            repository_path,
            safe_read=True,
            not_found_reason="github_repository_not_found",
        )
        repository = _decode_repository(repository_payload)
        pull_payload = await self._request_json(
            "GET",
            (
                f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}/"
                f"pulls/{pull_request_number}"
            ),
            safe_read=True,
            not_found_reason="github_pr_not_found",
        )
        return _decode_pull_request(
            pull_payload,
            repository=repository,
            requested_number=pull_request_number,
            require_head=require_head,
        )

    async def list_comments(
        self, repository_full_name: str, pull_request_number: int
    ) -> list[GitHubComment]:
        """List only the bounded first page of PR conversation comments."""

        _repository_path, owner, repository_name = _repository_route(
            repository_full_name
        )
        payload = await self._request_json(
            "GET",
            (
                f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}/"
                f"issues/{pull_request_number}/comments?per_page="
                f"{MAX_GITHUB_COLLECTION_ITEMS}&page=1"
            ),
            safe_read=True,
            not_found_reason="github_pr_not_found",
        )
        if not isinstance(payload, list) or len(payload) > MAX_GITHUB_COLLECTION_ITEMS:
            raise GitHubTransportError("github_transport_failed")
        return [_decode_comment(item) for item in payload]

    async def create_comment(
        self,
        repository_full_name: str,
        pull_request_number: int,
        body: str,
    ) -> GitHubComment:
        """Create one server-rendered managed PR comment without blind retry."""

        _validate_managed_body(body)
        _repository_path, owner, repository_name = _repository_route(
            repository_full_name
        )
        payload = await self._request_json(
            "POST",
            (
                f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}/"
                f"issues/{pull_request_number}/comments"
            ),
            json_body={"body": body},
            ambiguous_write=True,
        )
        return _decode_comment(payload)

    async def update_comment(
        self,
        repository_full_name: str,
        comment_id: int,
        body: str,
    ) -> GitHubComment:
        """Update one persisted or exact-marker-recovered managed comment."""

        _validate_managed_body(body)
        if not 1 <= comment_id <= MAX_SAFE_GITHUB_ID:
            raise GitHubTransportError("github_transport_failed")
        _repository_path, owner, repository_name = _repository_route(
            repository_full_name
        )
        payload = await self._request_json(
            "PATCH",
            (
                f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}/"
                f"issues/comments/{comment_id}"
            ),
            json_body={"body": body},
        )
        comment = _decode_comment(payload)
        if comment.comment_id != comment_id:
            raise GitHubTransportError("github_transport_failed")
        return comment

    async def _request_json(  # noqa: PLR0912, PLR0913
        self,
        method: str,
        route: str,
        *,
        safe_read: bool = False,
        not_found_reason: str = "github_transport_failed",
        json_body: dict[str, str] | None = None,
        ambiguous_write: bool = False,
    ) -> object:
        attempts = SAFE_READ_ATTEMPTS if safe_read else 1
        for attempt in range(attempts):
            try:
                response_status, response_headers, payload = await self._send(
                    method, route, json_body=json_body
                )
            except httpx.TransportError as error:
                if safe_read and attempt + 1 < attempts:
                    await asyncio.sleep(0.05 * (attempt + 1))
                    continue
                if ambiguous_write:
                    raise GitHubAmbiguousWriteError(
                        "github_publication_failed"
                    ) from error
                raise GitHubTransportError("github_transport_failed") from error

            if httpx.codes.is_redirect(response_status):
                raise GitHubTransportError("github_redirect_rejected")
            if _is_rate_limited(response_status, response_headers):
                raise GitHubRateLimitedError("github_rate_limited")
            if response_status == httpx.codes.NOT_FOUND:
                raise GitHubTransportError(not_found_reason)
            if response_status in _TRANSIENT_READ_STATUSES:
                if safe_read and attempt + 1 < attempts:
                    await asyncio.sleep(0.05 * (attempt + 1))
                    continue
                if ambiguous_write:
                    raise GitHubAmbiguousWriteError("github_publication_failed")
                raise GitHubTransportError("github_transport_failed")
            if ambiguous_write and response_status in _AMBIGUOUS_WRITE_STATUSES:
                raise GitHubAmbiguousWriteError("github_publication_failed")
            if not httpx.codes.is_success(response_status):
                raise GitHubTransportError("github_transport_failed")
            if not _is_json_content_type(response_headers.get("content-type", "")):
                raise GitHubTransportError("github_transport_failed")
            return _decode_json(payload)
        raise GitHubTransportError("github_transport_failed")  # pragma: no cover

    async def _send(
        self,
        method: str,
        route: str,
        *,
        json_body: dict[str, str] | None,
    ) -> tuple[int, httpx.Headers, bytes]:
        if (
            route.startswith(("/", "//"))
            or "\\" in route
            or urlsplit(route).scheme
            or ".." in route.split("/")
        ):
            raise GitHubTransportError("github_transport_failed")
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._settings.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "switchboard-validation-adapter/1",
        }
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
            trust_env=False,
        ) as client, client.stream(
            method,
            route,
            headers=headers,
            json=json_body,
        ) as response:
            self._validate_response_origin(response.request.url)
            collected = bytearray()
            async for chunk in response.aiter_bytes():
                collected.extend(chunk)
                if len(collected) > MAX_GITHUB_RESPONSE_BYTES:
                    raise GitHubTransportError("github_response_too_large")
            return response.status_code, response.headers, bytes(collected)

    def _validate_response_origin(self, url: httpx.URL) -> None:
        parsed = urlsplit(str(url))
        origin = (
            parsed.scheme.lower(),
            parsed.hostname.lower() if parsed.hostname else "",
            parsed.port,
        )
        if origin != self._expected_origin or not parsed.path.startswith(
            self._expected_path_prefix
        ):
            raise GitHubTransportError("github_unexpected_host")


def _repository_route(repository_full_name: str) -> tuple[str, str, str]:
    if not _REPOSITORY.fullmatch(repository_full_name):
        raise GitHubTransportError("github_transport_failed")
    owner, repository_name = repository_full_name.split("/", maxsplit=1)
    if owner in {".", ".."} or repository_name in {".", ".."}:
        raise GitHubTransportError("github_transport_failed")
    return (
        f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}",
        owner,
        repository_name,
    )


def _decode_json(payload: bytes) -> object:
    if not payload:
        raise GitHubTransportError("github_transport_failed")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubTransportError("github_transport_failed") from error
    _validate_json_limits(decoded)
    return decoded


def _validate_json_limits(value: object) -> None:
    nodes = 0

    def visit(nested: object) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_GITHUB_JSON_NODES:
            raise GitHubTransportError("github_response_too_large")
        if nested is None or isinstance(nested, (bool, int, float)):
            return
        if isinstance(nested, str):
            if len(nested) > MAX_GITHUB_STRING_LENGTH:
                raise GitHubTransportError("github_response_too_large")
            return
        if isinstance(nested, list):
            if len(nested) > MAX_GITHUB_COLLECTION_ITEMS:
                raise GitHubTransportError("github_response_too_large")
            for item in nested:
                visit(item)
            return
        if isinstance(nested, dict):
            if len(nested) > MAX_GITHUB_COLLECTION_ITEMS or not all(
                isinstance(key, str) and len(key) <= MAX_GITHUB_NODE_ID_LENGTH
                for key in nested
            ):
                raise GitHubTransportError("github_response_too_large")
            for item in nested.values():
                visit(item)
            return
        raise GitHubTransportError("github_transport_failed")

    visit(value)


def _strict_object(
    value: object,
    *,
    allowed: frozenset[str],
    required: frozenset[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GitHubTransportError("github_transport_failed")
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(allowed):
        raise GitHubTransportError("github_transport_failed")
    return value


def _safe_id(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_SAFE_GITHUB_ID
    ):
        raise GitHubTransportError("github_transport_failed")
    return value


def _safe_node_id(value: object) -> str:
    if not isinstance(value, str) or not _NODE_ID.fullmatch(value):
        raise GitHubTransportError("github_transport_failed")
    return value


def _safe_repository_name(value: object) -> str:
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise GitHubTransportError("github_transport_failed")
    return value


def _safe_display_text(value: object) -> str:
    if not isinstance(value, str) or not _DISPLAY_TEXT.fullmatch(value):
        raise GitHubTransportError("github_transport_failed")
    return value


def _safe_sha(value: object, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        if required:
            raise GitHubTransportError("github_head_unavailable")
        return None
    return value


def _decode_repository(value: object) -> GitHubRepositoryIdentity:
    payload = _strict_object(
        value,
        allowed=_REPOSITORY_FIELDS,
        required=frozenset({"id", "node_id", "full_name"}),
    )
    return GitHubRepositoryIdentity(
        full_name=_safe_repository_name(payload["full_name"]),
        repository_id=_safe_id(payload["id"]),
        node_id=_safe_node_id(payload["node_id"]),
    )


def _decode_ref(
    value: object,
    *,
    require_repository: bool,
    require_sha: bool,
) -> tuple[str, str | None, GitHubRepositoryIdentity | None]:
    if value is None and not require_repository and not require_sha:
        return "unavailable", None, None
    payload = _strict_object(
        value,
        allowed=_PULL_REF_FIELDS,
        required=frozenset({"ref", "sha", "repo"}),
    )
    repository_payload = payload["repo"]
    repository = (
        _decode_repository(repository_payload)
        if isinstance(repository_payload, dict)
        else None
    )
    if require_repository and repository is None:
        raise GitHubTransportError("github_head_unavailable")
    if repository is None:
        return _safe_display_text(payload["ref"]), None, None
    return (
        _safe_display_text(payload["ref"]),
        _safe_sha(payload["sha"], required=require_sha),
        repository,
    )


def _decode_pull_request(
    value: object,
    *,
    repository: GitHubRepositoryIdentity,
    requested_number: int,
    require_head: bool,
) -> ResolvedPullRequest:
    payload = _strict_object(
        value,
        allowed=_PULL_REQUEST_FIELDS,
        required=frozenset(
            {
                "id",
                "node_id",
                "number",
                "state",
                "draft",
                "merged",
                "base",
                "head",
            }
        ),
    )
    number = payload["number"]
    if number != requested_number:
        raise GitHubTransportError("github_transport_failed")
    state = payload["state"]
    if state not in {"open", "closed"}:
        raise GitHubTransportError("github_transport_failed")
    if not isinstance(payload["draft"], bool) or not isinstance(
        payload["merged"], bool
    ):
        raise GitHubTransportError("github_transport_failed")
    base_ref, base_sha, base_repository = _decode_ref(
        payload["base"], require_repository=True, require_sha=True
    )
    if (
        base_repository is None
        or base_repository.repository_id != repository.repository_id
        or base_repository.node_id != repository.node_id
    ):
        raise GitHubTransportError("github_transport_failed")
    head_ref, head_sha, head_repository = _decode_ref(
        payload["head"],
        require_repository=require_head,
        require_sha=require_head,
    )
    return ResolvedPullRequest(
        repository_full_name=repository.full_name,
        repository_id=repository.repository_id,
        repository_node_id=repository.node_id,
        pull_request_number=requested_number,
        pull_request_id=_safe_id(payload["id"]),
        pull_request_node_id=_safe_node_id(payload["node_id"]),
        state=state,
        draft=payload["draft"],
        merged=payload["merged"],
        base_ref=base_ref,
        base_sha=base_sha or "",  # require_sha=True guarantees a value
        head_ref=head_ref,
        head_sha=head_sha,
        head_repository_full_name=(
            head_repository.full_name if head_repository is not None else None
        ),
        head_repository_id=(
            head_repository.repository_id if head_repository is not None else None
        ),
    )


def _decode_comment(value: object) -> GitHubComment:
    payload = _strict_object(
        value,
        allowed=_COMMENT_FIELDS,
        required=frozenset({"id", "body"}),
    )
    body = payload["body"]
    if not isinstance(body, str) or len(body) > MAX_GITHUB_STRING_LENGTH:
        raise GitHubTransportError("github_transport_failed")
    return GitHubComment(comment_id=_safe_id(payload["id"]), body=body)


def _validate_managed_body(body: str) -> None:
    if (
        not isinstance(body, str)
        or not body
        or len(body.encode("utf-8")) > MAX_MANAGED_COMMENT_BYTES
        or "\x00" in body
    ):
        raise GitHubTransportError("github_publication_failed")


def _is_json_content_type(value: str) -> bool:
    return value.lower().split(";", maxsplit=1)[0].strip() in {
        "application/json",
        "application/vnd.github+json",
    }


def _is_rate_limited(status: int, headers: httpx.Headers) -> bool:
    if status == httpx.codes.TOO_MANY_REQUESTS:
        return True
    if status != httpx.codes.FORBIDDEN:
        return False
    return (
        headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in headers
    )


__all__ = [
    "MAX_GITHUB_COLLECTION_ITEMS",
    "MAX_GITHUB_RESPONSE_BYTES",
    "GitHubComment",
    "GitHubRepositoryIdentity",
    "GitHubTransport",
    "ResolvedPullRequest",
]
