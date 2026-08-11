# ruff: noqa: PLR2004
"""Focused configuration and transport coverage for the GitHub adapter."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from server.application.configuration_service import ConfigurationService
from server.github_adapter.errors import (
    GitHubAmbiguousWriteError,
    GitHubRateLimitedError,
    GitHubTransportError,
)
from server.github_adapter.transport import (
    MAX_GITHUB_COLLECTION_ITEMS,
    MAX_GITHUB_COMMENT_PAGES,
    MAX_GITHUB_LAST_PAGE,
    MAX_GITHUB_LINK_HEADER_LENGTH,
    MAX_GITHUB_RESPONSE_BYTES,
    GitHubActorIdentity,
    GitHubTransport,
)
from server.settings import (
    DEFAULT_GITHUB_API_URL,
    GitHubConfigurationError,
    GitHubSettings,
    get_github_settings,
)

REPOSITORY = "Nobodyworld/dev-agent-switchboard"
HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
TOKEN = "offline-transport-secret-placeholder"  # noqa: S105
CREDENTIAL_ACTOR = GitHubActorIdentity(actor_id=700, node_id="U_credential")
MANAGED_MARKER = "<!-- switchboard-validation:v1:" + "c" * 64 + " -->"


@pytest.fixture(autouse=True)
def _clear_github_settings_cache() -> None:
    get_github_settings.cache_clear()
    yield
    get_github_settings.cache_clear()


def _settings(
    *, api_url: str = DEFAULT_GITHUB_API_URL, token: str = TOKEN
) -> GitHubSettings:
    return GitHubSettings(
        api_url=api_url,
        operator_id="transport-test",
        token=token,
    )


def _repository_payload(
    *,
    full_name: str = REPOSITORY,
    repository_id: int = 100,
    node_id: str = "R_repo",
) -> dict[str, object]:
    return {
        "id": repository_id,
        "node_id": node_id,
        "full_name": full_name,
    }


def _pull_payload(
    *,
    state: str = "open",
    draft: bool = False,
    merged: bool = False,
    head_sha: str | None = HEAD_SHA,
    head_repository: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": 200,
        "node_id": "PR_node",
        "number": 125,
        "state": state,
        "draft": draft,
        "merged": merged,
        "base": {
            "ref": "main",
            "sha": BASE_SHA,
            "repo": _repository_payload(),
        },
        "head": {
            "ref": "feature/one",
            "sha": head_sha,
            "repo": (
                _repository_payload() if head_repository is None else head_repository
            ),
        },
    }


def _actor_payload(
    *,
    actor_id: int = CREDENTIAL_ACTOR.actor_id,
    node_id: str = CREDENTIAL_ACTOR.node_id,
    response_sentinel: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": actor_id,
        "node_id": node_id,
        "login": "credential-actor",
    }
    if response_sentinel is not None:
        payload["bio"] = response_sentinel
    return payload


def _comment_payload(
    comment_id: int,
    body: str,
    *,
    actor_id: int = CREDENTIAL_ACTOR.actor_id,
    actor_node_id: str = CREDENTIAL_ACTOR.node_id,
    pull_request_number: int = 125,
) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": body,
        "issue_url": (
            "https://api.github.com/repos/Nobodyworld/"
            f"dev-agent-switchboard/issues/{pull_request_number}"
        ),
        "user": _actor_payload(actor_id=actor_id, node_id=actor_node_id),
    }


def _json_response(
    payload: object,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response_headers = {"content-type": "application/json"}
    if headers:
        response_headers.update(headers)
    return httpx.Response(status, json=payload, headers=response_headers)


def _resolver_transport(
    pull_payload: dict[str, object],
    *,
    repository_payload: dict[str, object] | None = None,
    observed: list[httpx.Request] | None = None,
) -> GitHubTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if observed is not None:
            observed.append(request)
        if request.url.path.endswith("/repos/Nobodyworld/dev-agent-switchboard"):
            return _json_response(repository_payload or _repository_payload())
        if request.url.path.endswith(
            "/repos/Nobodyworld/dev-agent-switchboard/pulls/125"
        ):
            return _json_response(pull_payload)
        raise AssertionError(f"unexpected fixed route: {request.url}")

    return GitHubTransport(_settings(), transport=httpx.MockTransport(handler))


def test_missing_token_fails_with_bounded_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SWITCHBOARD_GITHUB_TOKEN", raising=False)

    with pytest.raises(
        GitHubConfigurationError, match=r"^github_token_not_configured$"
    ):
        get_github_settings()


def test_token_is_absent_from_repr_and_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "sensitive-header-test-placeholder"
    monkeypatch.setenv("SWITCHBOARD_GITHUB_TOKEN", sentinel)
    settings = get_github_settings()

    assert sentinel not in repr(settings)
    assert "token=" not in repr(settings)

    monkeypatch.setenv("SWITCHBOARD_GITHUB_API_URL", "http://api.github.com")
    get_github_settings.cache_clear()
    with pytest.raises(GitHubConfigurationError) as caught:
        get_github_settings()
    assert str(caught.value) == "github_api_url_must_be_https"
    assert sentinel not in str(caught.value)


def test_token_is_absent_from_operator_configuration_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "sensitive-snapshot-test-placeholder"
    monkeypatch.setenv("SWITCHBOARD_GITHUB_TOKEN", sentinel)

    snapshot = ConfigurationService().snapshot()

    assert sentinel not in repr(snapshot)
    assert all(item.name != "SWITCHBOARD_GITHUB_TOKEN" for item in snapshot.environment)


@pytest.mark.parametrize(
    "api_url",
    [
        "http://api.github.com",
        "https://operator@api.github.com",
        "https://api.github.com?next=https://example.test",
        "https://api.github.com/#fragment",
        "https://api.github.com:invalid",
        "https://api.github.com/%2e%2e",
        "https://api.github.com\\@example.test",
    ],
)
def test_invalid_or_unsafe_api_bases_are_rejected(
    monkeypatch: pytest.MonkeyPatch, api_url: str
) -> None:
    monkeypatch.setenv("SWITCHBOARD_GITHUB_TOKEN", TOKEN)
    monkeypatch.setenv("SWITCHBOARD_GITHUB_API_URL", api_url)

    with pytest.raises(GitHubConfigurationError):
        get_github_settings()


def test_enterprise_api_base_is_normalized_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_GITHUB_TOKEN", TOKEN)
    monkeypatch.setenv("SWITCHBOARD_GITHUB_API_URL", "https://GitHub.Example/api/v3/")
    monkeypatch.setenv("SWITCHBOARD_OPERATOR_ID", "operator:test")

    settings = get_github_settings()

    assert settings.api_url == "https://github.example/api/v3"
    assert settings.host == "github.example"
    assert settings.operator_id == "operator:test"


@pytest.mark.asyncio
async def test_fixed_routes_ignore_untrusted_returned_urls_and_encode_identity() -> (
    None
):
    observed: list[httpx.Request] = []
    repository = _repository_payload()
    repository["url"] = "https://attacker.example/repository"
    pull = _pull_payload()
    pull["diff_url"] = "https://attacker.example/payload"
    transport = _resolver_transport(
        pull, repository_payload=repository, observed=observed
    )

    resolved = await transport.resolve_pull_request(REPOSITORY, 125)

    assert resolved.head_sha == HEAD_SHA
    assert [request.url.path for request in observed] == [
        "/repos/Nobodyworld/dev-agent-switchboard",
        "/repos/Nobodyworld/dev-agent-switchboard/pulls/125",
    ]
    assert {request.url.host for request in observed} == {"api.github.com"}
    assert all(
        request.headers["authorization"] == f"Bearer {TOKEN}" for request in observed
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repository_full_name",
    ("./repository", "../repository", "owner/.", "owner/.."),
)
async def test_fixed_routes_reject_exact_dot_segments_before_transport(
    repository_full_name: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("invalid repository identity reached transport")

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubTransportError, match=r"^github_transport_failed$"):
        await transport.resolve_pull_request(repository_full_name, 125)
    assert requests == []


@pytest.mark.asyncio
async def test_actor_and_persisted_comment_reads_use_fixed_authoritative_routes() -> (
    None
):
    observed: list[httpx.Request] = []
    response_sentinel = "discarded-actor-response-body"

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.path == "/user":
            return _json_response(_actor_payload(response_sentinel=response_sentinel))
        if request.url.path.endswith(
            "/repos/Nobodyworld/dev-agent-switchboard/issues/comments/55"
        ):
            return _json_response(_comment_payload(55, f"{MANAGED_MARKER}\nmanaged"))
        raise AssertionError(f"unexpected fixed route: {request.url}")

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    actor = await transport.resolve_authenticated_actor()
    comment = await transport.get_comment(REPOSITORY, 55)

    assert actor == CREDENTIAL_ACTOR
    assert response_sentinel not in repr(actor)
    assert comment.author == CREDENTIAL_ACTOR
    assert comment.repository_full_name == REPOSITORY
    assert comment.pull_request_number == 125
    assert [request.url.path for request in observed] == [
        "/user",
        "/repos/Nobodyworld/dev-agent-switchboard/issues/comments/55",
    ]
    assert all(request.url.host == "api.github.com" for request in observed)


@pytest.mark.asyncio
async def test_actor_resolution_failure_is_bounded_and_redacted() -> None:
    response_sentinel = "untrusted-actor-response-sentinel"

    def handler(_request: httpx.Request) -> httpx.Response:
        return _json_response({"id": 700, "bio": response_sentinel})

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(
        GitHubTransportError,
        match=r"^github_actor_resolution_failed$",
    ) as captured:
        await transport.resolve_authenticated_actor()

    assert TOKEN not in str(captured.value)
    assert response_sentinel not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"id": 56}),
        lambda payload: payload.update(
            {
                "issue_url": (
                    "https://attacker.example/repos/Nobodyworld/"
                    "dev-agent-switchboard/issues/125"
                )
            }
        ),
        lambda payload: payload.update(
            {
                "issue_url": (
                    "https://api.github.com/repos/Nobodyworld/"
                    "dev-agent-switchboard/issues/125?follow=1"
                )
            }
        ),
        lambda payload: payload.update({"user": {"id": 700}}),
    ],
)
async def test_persisted_comment_identity_and_association_are_strict(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    payload = _comment_payload(55, f"{MANAGED_MARKER}\nmanaged")
    mutate(payload)

    def handler(_request: httpx.Request) -> httpx.Response:
        return _json_response(payload)

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubTransportError):
        await transport.get_comment(REPOSITORY, 55)


@pytest.mark.asyncio
async def test_owned_comment_after_first_100_is_found_on_last_page() -> None:
    observed_pages: list[str] = []
    oldest_page = [
        _comment_payload(
            index,
            f"ordinary user comment {index}",
            actor_id=701,
            actor_node_id="U_user",
        )
        for index in range(1, 101)
    ]
    newest_page = [_comment_payload(101, f"{MANAGED_MARKER}\nmanaged")]
    last_url = (
        "https://api.github.com/repos/Nobodyworld/dev-agent-switchboard/"
        "issues/125/comments?per_page=100&page=2"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed_pages.append(request.url.params["page"])
        if request.url.params["page"] == "1":
            return _json_response(
                oldest_page,
                headers={"link": f'<{last_url}>; rel="last"'},
            )
        if request.url.params["page"] == "2":
            return _json_response(newest_page)
        raise AssertionError(f"unexpected page: {request.url}")

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    listing = await transport.list_comments(REPOSITORY, 125)

    assert observed_pages == ["1", "2"]
    assert listing.complete is True
    assert len(listing.comments) == 101
    assert listing.comments[0].comment_id == 101
    assert listing.comments[0].author == CREDENTIAL_ACTOR
    assert listing.comments[0].body.startswith(MANAGED_MARKER)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "last_url",
    [
        (
            "https://attacker.example/repos/Nobodyworld/dev-agent-switchboard/"
            "issues/125/comments?per_page=100&page=2"
        ),
        (
            "https://api.github.com/repos/Nobodyworld/other/"
            "issues/125/comments?per_page=100&page=2"
        ),
        (
            "https://api.github.com/repos/Nobodyworld/dev-agent-switchboard/"
            "issues/125/comments?per_page=100&page="
            f"{MAX_GITHUB_LAST_PAGE + 1}"
        ),
    ],
)
async def test_comment_recovery_rejects_untrusted_or_unbounded_last_links(
    last_url: str,
) -> None:
    observed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(str(request.url))
        return _json_response(
            [],
            headers={"link": f'<{last_url}>; rel="last"'},
        )

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubTransportError, match=r"^github_pagination_invalid$"):
        await transport.list_comments(REPOSITORY, 125)

    assert len(observed) == 1
    assert observed[0].startswith(
        "https://api.github.com/repos/Nobodyworld/dev-agent-switchboard/"
    )


@pytest.mark.asyncio
async def test_comment_recovery_inspects_only_last_and_preceding_pages() -> None:
    observed_pages: list[str] = []
    last_url = (
        "https://api.github.com/repos/Nobodyworld/dev-agent-switchboard/"
        "issues/125/comments?per_page=100&page=4"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        observed_pages.append(page)
        headers = {"link": f'<{last_url}>; rel="last"'} if page == "1" else None
        return _json_response(
            [_comment_payload(int(page), f"page {page}")],
            headers=headers,
        )

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    listing = await transport.list_comments(REPOSITORY, 125)

    assert observed_pages == ["1", "4", "3"]
    assert MAX_GITHUB_COMMENT_PAGES == 2
    assert listing.complete is False
    assert [comment.comment_id for comment in listing.comments] == [4, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "link",
    [
        "not-a-link-header",
        (
            "<https://api.github.com/repos/Nobodyworld/dev-agent-switchboard/"
            'issues/125/comments?per_page=100&page=2>; rel="unknown"'
        ),
        (
            "<https://api.github.com/repos/Nobodyworld/dev-agent-switchboard/"
            'issues/125/comments?per_page=100&page=2&extra=1>; rel="last"'
        ),
        "x" * (MAX_GITHUB_LINK_HEADER_LENGTH + 1),
    ],
)
async def test_malformed_or_oversized_link_metadata_is_rejected(link: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _json_response([], headers={"link": link})

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubTransportError, match=r"^github_pagination_invalid$"):
        await transport.list_comments(REPOSITORY, 125)


def test_unexpected_response_origin_is_rejected() -> None:
    transport = GitHubTransport(_settings())

    with pytest.raises(GitHubTransportError, match=r"^github_unexpected_host$"):
        transport._validate_response_origin(
            httpx.URL("https://attacker.example/repos/owner/repository")
        )


@pytest.mark.asyncio
async def test_redirect_is_rejected_without_following_location() -> None:
    observed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(str(request.url))
        return httpx.Response(
            302,
            headers={
                "location": "https://attacker.example/redirected",
                "content-type": "application/json",
            },
            content=b"{}",
        )

    transport = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubTransportError, match=r"^github_redirect_rejected$"):
        await transport.resolve_pull_request(REPOSITORY, 125)
    assert len(observed) == 1
    assert "attacker.example" not in observed[0]


@pytest.mark.asyncio
async def test_response_bytes_and_collection_sizes_are_bounded() -> None:
    oversized = b"{" + b'"padding":"' + b"x" * MAX_GITHUB_RESPONSE_BYTES + b'"}'

    def oversized_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=oversized, headers={"content-type": "application/json"}
        )

    transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(oversized_handler)
    )
    with pytest.raises(GitHubTransportError, match=r"^github_response_too_large$"):
        await transport.resolve_pull_request(REPOSITORY, 125)

    def comments_handler(_request: httpx.Request) -> httpx.Response:
        return _json_response(
            [
                {"id": index + 1, "body": "bounded"}
                for index in range(MAX_GITHUB_COLLECTION_ITEMS + 1)
            ]
        )

    comments_transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(comments_handler)
    )
    with pytest.raises(GitHubTransportError, match=r"^github_response_too_large$"):
        await comments_transport.list_comments(REPOSITORY, 125)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("id"),
        lambda payload: payload.update({"unexpected": "field"}),
        lambda payload: payload.update({"number": 126}),
        lambda payload: payload.update({"state": "unknown"}),
        lambda payload: payload.update({"head": None}),
        lambda payload: payload.update(
            {
                "head": {
                    "ref": "feature",
                    "sha": "A" * 40,
                    "repo": _repository_payload(),
                }
            }
        ),
    ],
)
async def test_malformed_missing_unknown_and_invalid_pr_fields_are_rejected(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    payload = _pull_payload()
    mutate(payload)
    transport = _resolver_transport(payload)

    with pytest.raises(GitHubTransportError):
        await transport.resolve_pull_request(REPOSITORY, 125)


@pytest.mark.asyncio
async def test_oversized_decoded_string_and_wrong_content_type_are_rejected() -> None:
    repository = _repository_payload()
    repository["full_name"] = "x" * 70_000
    transport = _resolver_transport(_pull_payload(), repository_payload=repository)
    with pytest.raises(GitHubTransportError, match=r"^github_response_too_large$"):
        await transport.resolve_pull_request(REPOSITORY, 125)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{}", headers={"content-type": "text/html"})

    wrong_type = GitHubTransport(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubTransportError, match=r"^github_transport_failed$"):
        await wrong_type.resolve_pull_request(REPOSITORY, 125)


@pytest.mark.asyncio
async def test_safe_reads_retry_but_comment_creation_never_blindly_retries() -> None:
    attempts = 0

    def read_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path.endswith("/repos/Nobodyworld/dev-agent-switchboard"):
            attempts += 1
            if attempts < 3:
                return _json_response({}, status=503)
            return _json_response(_repository_payload())
        return _json_response(_pull_payload())

    transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(read_handler)
    )
    assert (await transport.resolve_pull_request(REPOSITORY, 125)).head_sha == HEAD_SHA
    assert attempts == 3

    create_attempts = 0

    def create_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal create_attempts
        create_attempts += 1
        return _json_response({}, status=503)

    create_transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(create_handler)
    )
    with pytest.raises(GitHubAmbiguousWriteError, match=r"^github_publication_failed$"):
        await create_transport.create_comment(
            REPOSITORY, 125, "<!-- switchboard-validation:v1:" + "c" * 64 + " -->"
        )
    assert create_attempts == 1


@pytest.mark.asyncio
async def test_rate_limits_are_distinguished_from_other_forbidden_responses() -> None:
    def rate_limited(_request: httpx.Request) -> httpx.Response:
        return _json_response(
            {"message": "remote response must not escape"},
            status=403,
            headers={"x-ratelimit-remaining": "0"},
        )

    transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(rate_limited)
    )
    with pytest.raises(GitHubRateLimitedError, match=r"^github_rate_limited$"):
        await transport.resolve_pull_request(REPOSITORY, 125)

    def forbidden(_request: httpx.Request) -> httpx.Response:
        return _json_response({"message": f"do not reveal {TOKEN}"}, status=403)

    forbidden_transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(forbidden)
    )
    with pytest.raises(GitHubTransportError) as caught:
        await forbidden_transport.resolve_pull_request(REPOSITORY, 125)
    assert str(caught.value) == "github_transport_failed"
    assert TOKEN not in str(caught.value)
    assert "do not reveal" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "draft", "merged"),
    [
        ("open", False, False),
        ("open", True, False),
        ("closed", False, False),
        ("closed", False, True),
    ],
)
async def test_open_draft_closed_and_merged_states_are_resolved(
    state: str, draft: bool, merged: bool
) -> None:
    transport = _resolver_transport(
        _pull_payload(state=state, draft=draft, merged=merged)
    )

    resolved = await transport.resolve_pull_request(REPOSITORY, 125)

    assert (resolved.state, resolved.draft, resolved.merged) == (
        state,
        draft,
        merged,
    )
    assert resolved.repository_id == 100
    assert resolved.pull_request_id == 200
    assert resolved.head_sha == HEAD_SHA


@pytest.mark.asyncio
async def test_fork_identity_is_retained_and_deleted_head_fails_closed() -> None:
    fork = _repository_payload(
        full_name="fork-owner/dev-agent-switchboard",
        repository_id=101,
        node_id="R_fork",
    )
    fork_transport = _resolver_transport(_pull_payload(head_repository=fork))
    fork_result = await fork_transport.resolve_pull_request(REPOSITORY, 125)
    assert fork_result.head_repository_full_name == ("fork-owner/dev-agent-switchboard")
    assert fork_result.head_repository_id == 101

    deleted_payload = _pull_payload()
    assert isinstance(deleted_payload["head"], dict)
    deleted_payload["head"]["repo"] = None
    deleted_transport = _resolver_transport(deleted_payload)
    with pytest.raises(GitHubTransportError, match=r"^github_head_unavailable$"):
        await deleted_transport.resolve_pull_request(REPOSITORY, 125)
    deleted_result = await deleted_transport.resolve_pull_request(
        REPOSITORY, 125, require_head=False
    )
    assert deleted_result.head_sha is None
    assert deleted_result.head_repository_full_name is None


@pytest.mark.asyncio
async def test_missing_repository_and_pr_have_bounded_reasons() -> None:
    def missing_repository(_request: httpx.Request) -> httpx.Response:
        return _json_response({"message": "not found"}, status=404)

    transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(missing_repository)
    )
    with pytest.raises(GitHubTransportError, match=r"^github_repository_not_found$"):
        await transport.resolve_pull_request(REPOSITORY, 125)

    def missing_pr(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/Nobodyworld/dev-agent-switchboard"):
            return _json_response(_repository_payload())
        return _json_response({"message": "not found"}, status=404)

    pr_transport = GitHubTransport(
        _settings(), transport=httpx.MockTransport(missing_pr)
    )
    with pytest.raises(GitHubTransportError, match=r"^github_pr_not_found$"):
        await pr_transport.resolve_pull_request(REPOSITORY, 125)


def test_no_secret_or_response_body_is_present_in_serialized_errors() -> None:
    error = GitHubTransportError("github_transport_failed")
    serialized = json.dumps({"detail": str(error)})

    assert TOKEN not in serialized
    assert "authorization" not in serialized.lower()
    assert "response" not in serialized.lower()
