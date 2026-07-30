"""Bounded errors for the server-side GitHub validation adapter."""

from __future__ import annotations


class GitHubAdapterError(RuntimeError):
    """Base error whose message is always one bounded reason code."""


class GitHubRequestNotFoundError(GitHubAdapterError):
    """Raised when an adapter request does not exist."""


class GitHubRepositoryNotAllowedError(GitHubAdapterError):
    """Raised before remote resolution for a repository outside the allowlist."""


class GitHubManifestError(GitHubAdapterError):
    """Raised when the requested trusted manifest identity does not exist."""


class GitHubTransportError(GitHubAdapterError):
    """Raised for a redacted deterministic outbound transport failure."""


class GitHubRateLimitedError(GitHubTransportError):
    """Raised when GitHub refuses an operation because of rate limiting."""


class GitHubAmbiguousWriteError(GitHubTransportError):
    """Raised when a comment create may have reached GitHub."""


class GitHubTerminalEvidenceRequiredError(GitHubAdapterError):
    """Raised when publication has no suitable terminal compact evidence."""


__all__ = [
    "GitHubAdapterError",
    "GitHubAmbiguousWriteError",
    "GitHubManifestError",
    "GitHubRateLimitedError",
    "GitHubRepositoryNotAllowedError",
    "GitHubRequestNotFoundError",
    "GitHubTerminalEvidenceRequiredError",
    "GitHubTransportError",
]
