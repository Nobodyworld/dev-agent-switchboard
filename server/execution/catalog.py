"""Strict source-controlled repository-to-manifest trust catalog."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .workload_profiles import profile_catalog_mappings

_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_IDENTITY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_MAX_DISPLAY_NAME = 120
_MAX_DESCRIPTION = 500
_MAX_MANIFESTS = 32
_MAX_DOCUMENTATION_REFERENCE_LENGTH = 255


def _exact_keys(value: Mapping[str, Any], expected: set[str], kind: str) -> None:
    if set(value) != expected:
        raise ValueError(f"trusted {kind} definition fields are invalid")


def validate_repository_full_name(value: str) -> str:
    """Return one canonical accepted repository identity or fail closed."""

    if not isinstance(value, str) or not _REPOSITORY_PATTERN.fullmatch(value):
        raise ValueError("repository full_name is invalid")
    owner, repository = value.split("/", maxsplit=1)
    if owner in {".", ".."} or repository in {".", ".."}:
        raise ValueError("repository full_name contains a dot segment")
    return value


@dataclass(frozen=True, slots=True, order=True)
class TrustedManifestReference:
    """One immutable manifest identity allowed for a repository."""

    name: str
    version: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TrustedManifestReference:
        _exact_keys(value, {"name", "version"}, "manifest reference")
        name = value["name"]
        version = value["version"]
        if not isinstance(name, str) or not isinstance(version, str):
            raise ValueError("trusted manifest reference values are invalid")
        return cls(name=name, version=version)

    def __post_init__(self) -> None:
        if not _IDENTITY_PATTERN.fullmatch(self.name) or not _VERSION_PATTERN.fullmatch(
            self.version
        ):
            raise ValueError("trusted manifest reference identity is invalid")

    def safe_metadata(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}


@dataclass(frozen=True, slots=True)
class TrustedRepository:
    """Reviewed repository metadata and its exact compatible manifests."""

    full_name: str
    display_name: str
    description: str
    support_status: str
    documentation_reference: str
    manifests: tuple[TrustedManifestReference, ...]
    default_manifest: TrustedManifestReference

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> TrustedRepository:
        _exact_keys(
            value,
            {
                "full_name",
                "display_name",
                "description",
                "support_status",
                "documentation_reference",
                "manifests",
                "default_manifest",
            },
            "repository",
        )
        manifests_value = value["manifests"]
        default_value = value["default_manifest"]
        if not isinstance(manifests_value, (tuple, list)):
            raise ValueError("trusted repository manifests are invalid")
        manifests = tuple(
            TrustedManifestReference.from_mapping(item)
            for item in manifests_value
            if isinstance(item, Mapping)
        )
        if len(manifests) != len(manifests_value):
            raise ValueError("trusted repository manifests are invalid")
        default_manifest = (
            TrustedManifestReference.from_mapping(default_value)
            if isinstance(default_value, Mapping)
            else None
        )
        if default_manifest is None:
            raise ValueError("trusted repository default manifest is invalid")
        full_name = value["full_name"]
        display_name = value["display_name"]
        description = value["description"]
        support_status = value["support_status"]
        documentation_reference = value["documentation_reference"]
        if not all(
            isinstance(item, str)
            for item in (
                full_name,
                display_name,
                description,
                support_status,
                documentation_reference,
            )
        ):
            raise ValueError("trusted repository metadata is invalid")
        return cls(
            full_name=full_name,
            display_name=display_name,
            description=description,
            support_status=support_status,
            documentation_reference=documentation_reference,
            manifests=manifests,
            default_manifest=default_manifest,
        )

    def __post_init__(self) -> None:
        validate_repository_full_name(self.full_name)
        if not (1 <= len(self.display_name) <= _MAX_DISPLAY_NAME):
            raise ValueError("trusted repository display_name is invalid")
        if not (1 <= len(self.description) <= _MAX_DESCRIPTION):
            raise ValueError("trusted repository description is invalid")
        if self.support_status != "developer_preview":
            raise ValueError("trusted repository support status is invalid")
        if (
            not self.documentation_reference.startswith("docs/")
            or not self.documentation_reference.endswith(".md")
            or len(self.documentation_reference) > _MAX_DOCUMENTATION_REFERENCE_LENGTH
            or ".." in self.documentation_reference.split("/")
        ):
            raise ValueError("trusted repository documentation reference is invalid")
        if not (1 <= len(self.manifests) <= _MAX_MANIFESTS):
            raise ValueError("trusted repository manifest count is invalid")
        if len(set(self.manifests)) != len(self.manifests):
            raise ValueError("trusted repository manifests must be unique")
        if self.default_manifest not in self.manifests:
            raise ValueError("trusted repository default manifest is not allowed")

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "display_name": self.display_name,
            "description": self.description,
            "support_status": self.support_status,
            "documentation_reference": self.documentation_reference,
            "manifests": [item.safe_metadata() for item in self.manifests],
            "default_manifest": self.default_manifest.safe_metadata(),
        }


_TRUSTED_REPOSITORIES = tuple(
    sorted(
        (
            TrustedRepository.from_mapping(
                {
                    "full_name": "Nobodyworld/dev-agent-switchboard",
                    "display_name": "Dev Agent Switchboard",
                    "description": (
                        "Switchboard control-plane and local-worker validation."
                    ),
                    "support_status": "developer_preview",
                    "documentation_reference": (
                        "docs/operations/validation-command-center.md"
                    ),
                    "manifests": (
                        {"name": "validate-switchboard", "version": "1"},
                        {"name": "worker-smoke", "version": "1"},
                    ),
                    "default_manifest": {
                        "name": "validate-switchboard",
                        "version": "1",
                    },
                }
            ),
            *(
                TrustedRepository.from_mapping(mapping)
                for mapping in profile_catalog_mappings()
            ),
            TrustedRepository.from_mapping(
                {
                    "full_name": "Nobodyworld/app-accounting-modular",
                    "display_name": "Modular Accounting",
                    "description": "Public modular-accounting Python quality contract.",
                    "support_status": "developer_preview",
                    "documentation_reference": (
                        "docs/operations/trusted-workload-onboarding.md"
                    ),
                    "manifests": (
                        {"name": "validate-accounting-modular", "version": "1"},
                    ),
                    "default_manifest": {
                        "name": "validate-accounting-modular",
                        "version": "1",
                    },
                }
            ),
        ),
        key=lambda item: item.full_name,
    )
)

TRUSTED_REPOSITORIES = frozenset(item.full_name for item in _TRUSTED_REPOSITORIES)
_PUBLIC_CATALOG_SIZE = 4


def validate_catalog(
    manifest_identities: Iterable[tuple[str, str]],
    repositories: Iterable[TrustedRepository] = _TRUSTED_REPOSITORIES,
) -> None:
    """Fail import when catalog entries are ambiguous or reference absent code."""

    is_public_catalog = repositories is _TRUSTED_REPOSITORIES
    identity_values = tuple(manifest_identities)
    identities = set(identity_values)
    if len(identities) != len(identity_values):
        raise ValueError("trusted manifest identities must be unique")
    definitions = tuple(repositories)
    names = [item.full_name.casefold() for item in definitions]
    if len(names) != len(set(names)):
        raise ValueError("trusted repository identities must be unique")
    if is_public_catalog and (
        len(definitions) != _PUBLIC_CATALOG_SIZE
        or {item.full_name for item in definitions} != TRUSTED_REPOSITORIES
    ):
        raise ValueError(
            "public trusted catalog must contain exactly four repositories"
        )
    for repository in definitions:
        if repository.default_manifest not in repository.manifests:
            raise ValueError("trusted repository default manifest is not allowed")
        for reference in repository.manifests:
            if (reference.name, reference.version) not in identities:
                raise ValueError("trusted repository references an unknown manifest")


def iter_trusted_repositories() -> tuple[TrustedRepository, ...]:
    return _TRUSTED_REPOSITORIES


def get_trusted_repository(full_name: str) -> TrustedRepository | None:
    return next(
        (item for item in _TRUSTED_REPOSITORIES if item.full_name == full_name), None
    )


def repository_allows_manifest(full_name: str, name: str, version: str) -> bool:
    repository = get_trusted_repository(full_name)
    return (
        repository is not None
        and TrustedManifestReference(name, version) in repository.manifests
    )


def trusted_catalog_digest() -> str:
    payload = [item.safe_metadata() for item in _TRUSTED_REPOSITORIES]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "TRUSTED_REPOSITORIES",
    "TrustedManifestReference",
    "TrustedRepository",
    "get_trusted_repository",
    "iter_trusted_repositories",
    "repository_allows_manifest",
    "trusted_catalog_digest",
    "validate_catalog",
    "validate_repository_full_name",
]
