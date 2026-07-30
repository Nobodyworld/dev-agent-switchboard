"""Fixed-route, bounded GitHub REST transport for exact-PR validation."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

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
MAX_GITHUB_COMMENT_PAGES = 2
MAX_GITHUB_LAST_PAGE = 1_000_000
MAX_GITHUB_JSON_NODES = 20_000
MAX_GITHUB_LINK_HEADER_LENGTH = 4096
MAX_GITHUB_NODE_ID_LENGTH = 128
MAX_MANAGED_COMMENT_BYTES = 12 * 1024
MAX_SAFE_GITHUB_ID = (1 << 63) - 1
MAX_SAFE_PULL_REQUEST_NUMBER = 2_147_483_647
SAFE_READ_ATTEMPTS = 3

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NODE_ID = re.compile(rf"^[A-Za-z0-9_=-]{{1,{MAX_GITHUB_NODE_ID_LENGTH}}}$")
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
_USER_FIELDS = frozenset(
    {
        "login",
        "id",
        "node_id",
        "avatar_url",
        "gravatar_id",
        "url",
        "html_url",
        "followers_url",
        "following_url",
        "gists_url",
        "starred_url",
        "subscriptions_url",
        "organizations_url",
        "repos_url",
        "events_url",
        "received_events_url",
        "type",
        "user_view_type",
        "site_admin",
        "name",
        "company",
        "blog",
        "location",
        "email",
        "hireable",
        "bio",
        "twitter_username",
        "notification_email",
        "public_repos",
        "public_gists",
        "followers",
        "following",
        "created_at",
        "updated_at",
        "private_gists",
        "total_private_repos",
        "owned_private_repos",
        "disk_usage",
        "collaborators",
        "two_factor_authentication",
        "plan",
        "ldap_dn",
        "business_plus",
        "enterprise_managed_user",
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
class GitHubActorIdentity:
    """Stable, non-secret identity resolved for the configured credential."""

    actor_id: int
    node_id: str


@dataclass(frozen=True, slots=True)
class GitHubComment:
    """Bounded authoritative fields needed to prove managed-comment ownership."""

    comment_id: int
    body: str
    author: GitHubActorIdentity
    repository_full_name: str
    pull_request_number: int


@dataclass(frozen=True, slots=True)
class GitHubCommentListing:
    """Newest bounded recovery window plus whether it covers the full history."""

    comments: tuple[GitHubComment, ...]
    complete: bool


class GitHubTransport:
    """Perform only fixed, bounded GitHub operations required by issue #122."""

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
    ) -> GitHubCommentListing:
        """Inspect the newest page and at most one preceding recovery page."""

        collection_route = _comment_collection_route(
            repository_full_name, pull_request_number
        )
        first_payload, first_headers = await self._request_json_with_headers(
            "GET",
            (f"{collection_route}?per_page={MAX_GITHUB_COLLECTION_ITEMS}&page=1"),
            safe_read=True,
            not_found_reason="github_pr_not_found",
        )
        first_page = self._decode_comment_page(first_payload)
        last_page = self._last_comment_page(
            first_headers.get("link"), collection_route=collection_route
        )
        if last_page == 1:
            return GitHubCommentListing(comments=tuple(first_page), complete=True)

        newest_payload = await self._request_json(
            "GET",
            (
                f"{collection_route}?per_page="
                f"{MAX_GITHUB_COLLECTION_ITEMS}&page={last_page}"
            ),
            safe_read=True,
            not_found_reason="github_pr_not_found",
        )
        newest_page = self._decode_comment_page(newest_payload)
        if last_page == MAX_GITHUB_COMMENT_PAGES:
            return GitHubCommentListing(
                comments=(*newest_page, *first_page),
                complete=True,
            )

        preceding_payload = await self._request_json(
            "GET",
            (
                f"{collection_route}?per_page="
                f"{MAX_GITHUB_COLLECTION_ITEMS}&page={last_page - 1}"
            ),
            safe_read=True,
            not_found_reason="github_pr_not_found",
        )
        preceding_page = self._decode_comment_page(preceding_payload)
        return GitHubCommentListing(
            comments=(*newest_page, *preceding_page),
            complete=False,
        )

    async def resolve_authenticated_actor(self) -> GitHubActorIdentity:
        """Resolve the stable actor identity owned by the configured credential."""

        try:
            payload = await self._request_json(
                "GET",
                "user",
                safe_read=True,
            )
            return _decode_actor(payload)
        except GitHubRateLimitedError:
            raise
        except GitHubTransportError as error:
            raise GitHubTransportError("github_actor_resolution_failed") from error

    async def get_comment(
        self, repository_full_name: str, comment_id: int
    ) -> GitHubComment:
        """Retrieve one exact persisted comment through a fixed repository route."""

        if not 1 <= comment_id <= MAX_SAFE_GITHUB_ID:
            raise GitHubTransportError("github_transport_failed")
        _repository_path, owner, repository_name = _repository_route(
            repository_full_name
        )
        payload = await self._request_json(
            "GET",
            (
                f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}/"
                f"issues/comments/{comment_id}"
            ),
            safe_read=True,
            not_found_reason="github_comment_not_found",
        )
        comment = self._decode_comment(payload)
        if comment.comment_id != comment_id:
            raise GitHubTransportError("github_transport_failed")
        return comment

    async def create_comment(
        self,
        repository_full_name: str,
        pull_request_number: int,
        body: str,
    ) -> GitHubComment:
        """Create one server-rendered managed PR comment without blind retry."""

        _validate_managed_body(body)
        collection_route = _comment_collection_route(
            repository_full_name, pull_request_number
        )
        payload = await self._request_json(
            "POST",
            collection_route,
            json_body={"body": body},
            ambiguous_write=True,
        )
        return self._decode_comment(payload)

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
        comment = self._decode_comment(payload)
        if comment.comment_id != comment_id:
            raise GitHubTransportError("github_transport_failed")
        return comment

    def _decode_comment_page(self, payload: object) -> list[GitHubComment]:
        if not isinstance(payload, list) or len(payload) > MAX_GITHUB_COLLECTION_ITEMS:
            raise GitHubTransportError("github_transport_failed")
        return [self._decode_comment(item) for item in payload]

    def _decode_comment(self, payload: object) -> GitHubComment:
        return _decode_comment(
            payload,
            expected_origin=self._expected_origin,
            expected_path_prefix=self._expected_path_prefix,
        )

    def _last_comment_page(self, link: str | None, *, collection_route: str) -> int:
        if link is None:
            return 1
        expected_path = f"{self._expected_path_prefix.rstrip('/')}/{collection_route}"
        return _validated_last_page(
            _validated_last_link_url(link),
            expected_origin=self._expected_origin,
            expected_path=expected_path,
        )

    async def _request_json(  # noqa: PLR0913
        self,
        method: str,
        route: str,
        *,
        safe_read: bool = False,
        not_found_reason: str = "github_transport_failed",
        json_body: dict[str, str] | None = None,
        ambiguous_write: bool = False,
    ) -> object:
        payload, _headers = await self._request_json_with_headers(
            method,
            route,
            safe_read=safe_read,
            not_found_reason=not_found_reason,
            json_body=json_body,
            ambiguous_write=ambiguous_write,
        )
        return payload

    async def _request_json_with_headers(  # noqa: PLR0912, PLR0913
        self,
        method: str,
        route: str,
        *,
        safe_read: bool = False,
        not_found_reason: str = "github_transport_failed",
        json_body: dict[str, str] | None = None,
        ambiguous_write: bool = False,
    ) -> tuple[object, httpx.Headers]:
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
            return _decode_json(payload), response_headers
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
        async with (
            httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
                follow_redirects=False,
                transport=self._transport,
                trust_env=False,
            ) as client,
            client.stream(
                method,
                route,
                headers=headers,
                json=json_body,
            ) as response,
        ):
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


def _validated_last_link_url(link: str) -> str:
    if len(link) > MAX_GITHUB_LINK_HEADER_LENGTH:
        raise GitHubTransportError("github_pagination_invalid")
    last_urls: list[str] = []
    allowed_relations = {"first", "last", "next", "prev"}
    for item in link.split(","):
        match = re.fullmatch(
            r'\s*<([^<>"\x00-\x1f\x7f]+)>\s*;\s*rel="([a-z ]+)"\s*',
            item,
        )
        if match is None:
            raise GitHubTransportError("github_pagination_invalid")
        relations = set(match.group(2).split())
        if not relations or not relations.issubset(allowed_relations):
            raise GitHubTransportError("github_pagination_invalid")
        if "last" in relations:
            last_urls.append(match.group(1))
    if len(last_urls) != 1:
        raise GitHubTransportError("github_pagination_invalid")
    return last_urls[0]


def _validated_last_page(
    last_url: str,
    *,
    expected_origin: tuple[str, str, int | None],
    expected_path: str,
) -> int:
    try:
        parsed = urlsplit(last_url)
        origin = (
            parsed.scheme.lower(),
            parsed.hostname.lower() if parsed.hostname else "",
            parsed.port,
        )
    except ValueError as error:
        raise GitHubTransportError("github_pagination_invalid") from error
    if (
        origin != expected_origin
        or parsed.path != expected_path
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise GitHubTransportError("github_pagination_invalid")
    try:
        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=2,
        )
        page_values = query["page"]
        per_page_values = query["per_page"]
        page = int(page_values[0])
    except (KeyError, TypeError, ValueError) as error:
        raise GitHubTransportError("github_pagination_invalid") from error
    if (
        set(query) != {"page", "per_page"}
        or len(page_values) != 1
        or len(per_page_values) != 1
        or per_page_values[0] != str(MAX_GITHUB_COLLECTION_ITEMS)
        or str(page) != page_values[0]
        or not 1 <= page <= MAX_GITHUB_LAST_PAGE
    ):
        raise GitHubTransportError("github_pagination_invalid")
    return page


def _comment_collection_route(
    repository_full_name: str, pull_request_number: int
) -> str:
    _repository_path, owner, repository_name = _repository_route(repository_full_name)
    if not 1 <= pull_request_number <= MAX_SAFE_PULL_REQUEST_NUMBER:
        raise GitHubTransportError("github_transport_failed")
    return (
        f"repos/{quote(owner, safe='')}/{quote(repository_name, safe='')}/"
        f"issues/{pull_request_number}/comments"
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


def _decode_actor(value: object) -> GitHubActorIdentity:
    payload = _strict_object(
        value,
        allowed=_USER_FIELDS,
        required=frozenset({"id", "node_id"}),
    )
    return GitHubActorIdentity(
        actor_id=_safe_id(payload["id"]),
        node_id=_safe_node_id(payload["node_id"]),
    )


def _decode_comment(
    value: object,
    *,
    expected_origin: tuple[str, str, int | None],
    expected_path_prefix: str,
) -> GitHubComment:
    payload = _strict_object(
        value,
        allowed=_COMMENT_FIELDS,
        required=frozenset({"id", "body", "issue_url", "user"}),
    )
    body = payload["body"]
    if not isinstance(body, str) or len(body) > MAX_GITHUB_STRING_LENGTH:
        raise GitHubTransportError("github_transport_failed")
    repository_full_name, pull_request_number = _decode_issue_association(
        payload["issue_url"],
        expected_origin=expected_origin,
        expected_path_prefix=expected_path_prefix,
    )
    return GitHubComment(
        comment_id=_safe_id(payload["id"]),
        body=body,
        author=_decode_actor(payload["user"]),
        repository_full_name=repository_full_name,
        pull_request_number=pull_request_number,
    )


def _decode_issue_association(
    value: object,
    *,
    expected_origin: tuple[str, str, int | None],
    expected_path_prefix: str,
) -> tuple[str, int]:
    if not isinstance(value, str) or len(value) > MAX_GITHUB_STRING_LENGTH:
        raise GitHubTransportError("github_transport_failed")
    parsed = urlsplit(value)
    origin = (
        parsed.scheme.lower(),
        parsed.hostname.lower() if parsed.hostname else "",
        parsed.port,
    )
    route_prefix = f"{expected_path_prefix.rstrip('/')}/repos/"
    if (
        origin != expected_origin
        or not parsed.path.startswith(route_prefix)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GitHubTransportError("github_transport_failed")
    route_parts = parsed.path[len(route_prefix) :].split("/")
    match route_parts:
        case [owner_part, repository_part, "issues", number_part]:
            pass
        case _:
            raise GitHubTransportError("github_transport_failed")
    owner = unquote(owner_part)
    repository_name = unquote(repository_part)
    repository_full_name = f"{owner}/{repository_name}"
    try:
        pull_request_number = int(number_part)
    except ValueError as error:
        raise GitHubTransportError("github_transport_failed") from error
    if (
        not _REPOSITORY.fullmatch(repository_full_name)
        or quote(owner, safe="") != owner_part
        or quote(repository_name, safe="") != repository_part
        or str(pull_request_number) != number_part
        or not 1 <= pull_request_number <= MAX_SAFE_PULL_REQUEST_NUMBER
    ):
        raise GitHubTransportError("github_transport_failed")
    return repository_full_name, pull_request_number


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
    return headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers


__all__ = [
    "MAX_GITHUB_COLLECTION_ITEMS",
    "MAX_GITHUB_COMMENT_PAGES",
    "MAX_GITHUB_LAST_PAGE",
    "MAX_GITHUB_RESPONSE_BYTES",
    "GitHubActorIdentity",
    "GitHubComment",
    "GitHubCommentListing",
    "GitHubRepositoryIdentity",
    "GitHubTransport",
    "ResolvedPullRequest",
]
