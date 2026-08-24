"""Expected domain errors for execution-plane API mapping."""

from __future__ import annotations


class ExecutionDomainError(RuntimeError):
    """Base class for an expected execution control-plane failure."""


class ExecutionNotFoundError(ExecutionDomainError):
    """Raised when a requested execution record does not exist."""


class LifecycleConflictError(ExecutionDomainError):
    """Raised for an illegal lifecycle mutation or terminal record."""


class ApprovalDeniedError(ExecutionDomainError):
    """Raised when deny-by-default approval checks do not pass."""


class UnknownManifestError(ExecutionDomainError):
    """Raised when a work order names an untrusted manifest identity."""


class ManifestIntegrityError(ExecutionDomainError):
    """Raised when a persisted identity differs from its trusted definition."""


class CatalogReadinessLimitError(ExecutionDomainError):
    """Raised when the bounded public worker snapshot cannot be represented."""


class ManifestParameterError(ExecutionDomainError):
    """Raised when a caller supplies an unsupported manifest parameter."""


class RepositoryWritePolicyError(ExecutionDomainError):
    """Raised when a caller asks for forbidden Phase 1 repository writes."""


class OwnershipConflictError(ExecutionDomainError):
    """Raised when a worker does not own the active execution lease."""


class MalformedEvidenceError(ExecutionDomainError):
    """Raised when persisted compact evidence fails its strict contract."""
