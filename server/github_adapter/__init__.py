"""Server-owned outbound GitHub exact-pull-request validation adapter."""

from .service import (
    GitHubAdapterDependencies,
    GitHubAdapterService,
    GitHubRequestStatus,
)
from .transport import GitHubTransport

__all__ = [
    "GitHubAdapterDependencies",
    "GitHubAdapterService",
    "GitHubRequestStatus",
    "GitHubTransport",
]
