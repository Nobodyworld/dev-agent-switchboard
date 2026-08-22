"""Reviewed workload blueprints compiled into the trusted execution surfaces.

This module is deliberately data-only: it does not read files, open a network
connection, or import the registry or catalog.  The catalog imports its safe
repository mappings, while the registry supplies its already-defined concrete
types to the compiler after import.  That keeps the reviewed source boundary
acyclic and prevents a runtime profile document from becoming executable.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_STEP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_ENVIRONMENT_KEY = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
_EXECUTABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_ARTIFACT_KIND = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SAFE_MEDIA_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+/-]{1,127}$")
_SAFE_EXCLUSION = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")

PROFILE_SCHEMA_VERSION = 1
MAX_PROFILE_TIMEOUT_SECONDS = 14_400
MAX_STEP_TIMEOUT_SECONDS = 3_600
MAX_OUTPUT_SUMMARY_BYTES = 65_536
MAX_ARTIFACT_COUNT = 128
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_RETENTION_DAYS = 3_650
MAX_RESULT_RECORDS = 10_000_000
MAX_RESULT_BYTES = 2 * 1_024 * 1_024
DEFAULT_RESULT_BYTES = 1_048_576
PUBLIC_WORKLOAD_REPOSITORIES = frozenset(
    {
        "Nobodyworld/dev-agent-switchboard",
        "Nobodyworld/app-accounting-modular",
        "Nobodyworld/dev-logger-zscripts",
        "Nobodyworld/app-industry-resilience",
    }
)
_ALLOWED_INHERITED_ENVIRONMENT_KEYS = frozenset(
    {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP"}
)
_ALLOWED_FIXED_ENVIRONMENT_KEYS = frozenset(
    {
        "PIP_DISABLE_PIP_VERSION_CHECK",
        "PIP_NO_INPUT",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUTF8",
    }
)
_PARSER_KINDS = frozenset(
    {
        "pytest",
        "coverage",
        "pytest-coverage",
        "security-audit",
        "dependency-audit",
        "dependency-health",
        "critical-coverage",
        "quality-summary-v1",
        "secret-scan",
    }
)
_RESULT_FIELDS_BY_PARSER = {
    "coverage": frozenset({"coverage"}),
    "dependency-audit": frozenset({"audit"}),
    "dependency-health": frozenset({"audit"}),
    "pytest": frozenset({"tests"}),
    "pytest-coverage": frozenset({"coverage", "tests"}),
    "quality-summary-v1": frozenset(
        {"coverage-threshold", "diagnostics", "operations", "profile", "status"}
    ),
    "secret-scan": frozenset({"audit"}),
}
_RESULT_FAILURES_BY_PARSER = {
    "dependency-audit": frozenset({"dependency-vulnerability"}),
    "dependency-health": frozenset({"dependency-health"}),
    "pytest": frozenset({"test-failure"}),
    "pytest-coverage": frozenset({"coverage-threshold", "test-failure"}),
    "quality-summary-v1": frozenset(
        {"coverage-threshold", "quality-operation-failure"}
    ),
    "secret-scan": frozenset({"baseline-validation"}),
}
_SHELL_EXECUTABLES = frozenset(
    {
        "bash",
        "cmd",
        "cmd.exe",
        "command",
        "fish",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "zsh",
    }
)
_SHELL_ARGUMENTS = frozenset({"-c", "/c", "-command", "-encodedcommand"})


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _exact_mapping_keys(
    value: Mapping[str, object], expected: set[str], kind: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"profile {kind} fields are invalid")


def _string_tuple(value: object, *, kind: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError(f"profile {kind} must be a string sequence")
    return tuple(value)


def _validate_relative_path(value: str, *, kind: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\\" in value
        or "\x00" in value
        or value.startswith(("/", "//"))
        or ":" in value
    ):
        raise ValueError(f"{kind} must be a bounded relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{kind} must not contain traversal or dot segments")
    return value


def _validate_fixed_argv(argv: tuple[str, ...]) -> None:
    if (
        not isinstance(argv, tuple)
        or not argv
        or any(not isinstance(item, str) or not item or "\x00" in item for item in argv)
    ):
        raise ValueError("profile step argv must be a non-empty fixed tuple")
    executable = argv[0]
    if (
        not _EXECUTABLE.fullmatch(executable)
        or executable.lower() in _SHELL_EXECUTABLES
    ):
        raise ValueError("profile step executable is unsafe or shell-shaped")
    if any(item.casefold() in _SHELL_ARGUMENTS for item in argv[1:]):
        raise ValueError("profile step shell invocation is not allowed")
    if any(
        item.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", item) is not None
        for item in argv
    ):
        raise ValueError("profile step argv must not contain absolute paths")
    path_arguments = (
        item.split("=", maxsplit=1)[-1].replace("\\", "/") for item in argv[1:]
    )
    if any(
        candidate in {".", ".."}
        or any(segment in {".", ".."} for segment in candidate.split("/"))
        for candidate in path_arguments
        if "/" in candidate or candidate in {".", ".."}
    ):
        raise ValueError("profile step argv must not contain traversal or dot segments")


def _validate_environment(environment: tuple[tuple[str, str], ...]) -> None:
    keys = [item[0] for item in environment]
    if len(keys) != len(set(keys)):
        raise ValueError("profile step environment keys must be unique")
    for key, value in environment:
        if (
            not isinstance(key, str)
            or not _ENVIRONMENT_KEY.fullmatch(key)
            or key not in _ALLOWED_FIXED_ENVIRONMENT_KEYS
        ):
            raise ValueError("profile step environment key is unsupported")
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 256
            or "\x00" in value
            or "\n" in value
            or "\r" in value
            or "${" in value
            or "%" in value
        ):
            raise ValueError("profile step environment value is invalid")


def _validate_capabilities(requirements: Mapping[str, Any]) -> None:
    allowed = {
        "git_available",
        "node",
        "operating_system",
        "pnpm",
        "python",
        "repository_write",
    }
    if set(requirements) - allowed:
        raise ValueError("profile capability requirement is not readiness-enforceable")
    operating_system = requirements.get("operating_system")
    if (
        not isinstance(operating_system, (tuple, list))
        or not operating_system
        or not all(item in {"linux", "windows"} for item in operating_system)
    ):
        raise ValueError("profile operating-system capability is invalid")
    for runtime in ("python", "node", "pnpm"):
        if runtime not in requirements:
            continue
        value = requirements[runtime]
        if not isinstance(value, Mapping) or set(value) not in ({"minimum"}, {"exact"}):
            raise ValueError("profile runtime capability is invalid")
        version = value.get("minimum", value.get("exact"))
        if not isinstance(version, str) or not re.fullmatch(
            r"\d+(?:\.\d+){1,2}", version
        ):
            raise ValueError("profile runtime capability version is invalid")
    if requirements.get("git_available") is not True:
        raise ValueError("profile must require Git availability")
    if requirements.get("repository_write") is not False:
        raise ValueError("profile must prohibit repository writes")


@dataclass(frozen=True, slots=True)
class ArtifactDeclaration:
    """One reviewed bounded checkout artifact declaration."""

    kind: str
    relative_path: str
    media_type: str
    redaction_state: str = "none"
    required: bool = True
    maximum_bytes: int = MAX_ARTIFACT_BYTES

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ArtifactDeclaration:
        _exact_mapping_keys(
            value,
            {
                "kind",
                "relative_path",
                "media_type",
                "redaction_state",
                "required",
                "maximum_bytes",
            },
            "artifact declaration",
        )
        return cls(**value)  # type: ignore[arg-type]

    def __post_init__(self) -> None:
        if not _SAFE_ARTIFACT_KIND.fullmatch(self.kind):
            raise ValueError("profile artifact kind is invalid")
        _validate_relative_path(self.relative_path, kind="profile artifact path")
        if not _SAFE_MEDIA_TYPE.fullmatch(self.media_type):
            raise ValueError("profile artifact media type is invalid")
        if self.redaction_state not in {"none", "redacted"}:
            raise ValueError("profile artifact redaction state is invalid")
        if (
            not isinstance(self.required, bool)
            or not 1 <= self.maximum_bytes <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError("profile artifact bounds are invalid")

    def identity_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "maximum_bytes": self.maximum_bytes,
            "media_type": self.media_type,
            "redaction_state": self.redaction_state,
            "relative_path": self.relative_path,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class ResultContract:
    """Closed parser and outcome contract for one fixed reviewed step."""

    parser_kind: str | None
    source: str = "stdout"
    source_path: str | None = None
    minimum_coverage_percent: int | None = None
    minimum_test_count: int | None = None
    maximum_parsed_records: int = 100_000
    maximum_parsed_bytes: int = DEFAULT_RESULT_BYTES
    required_summary_fields: tuple[str, ...] = ()
    failure_conditions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ResultContract:
        _exact_mapping_keys(
            value,
            {
                "parser_kind",
                "source",
                "source_path",
                "minimum_coverage_percent",
                "minimum_test_count",
                "maximum_parsed_records",
                "maximum_parsed_bytes",
                "required_summary_fields",
                "failure_conditions",
            },
            "result contract",
        )
        return cls(
            parser_kind=value["parser_kind"]
            if isinstance(value["parser_kind"], str)
            else None,
            source=value["source"] if isinstance(value["source"], str) else "",
            source_path=(
                value["source_path"] if isinstance(value["source_path"], str) else None
            ),
            minimum_coverage_percent=value["minimum_coverage_percent"],  # type: ignore[arg-type]
            minimum_test_count=value["minimum_test_count"],  # type: ignore[arg-type]
            maximum_parsed_records=value["maximum_parsed_records"],  # type: ignore[arg-type]
            maximum_parsed_bytes=value["maximum_parsed_bytes"],  # type: ignore[arg-type]
            required_summary_fields=_string_tuple(
                value["required_summary_fields"], kind="result summary fields"
            ),
            failure_conditions=_string_tuple(
                value["failure_conditions"], kind="result failure conditions"
            ),
        )

    def __post_init__(self) -> None:
        self._validate_source()
        self._validate_numeric_limits()
        self._validate_declared_fields()
        self._validate_parser_rules()

    def _validate_source(self) -> None:
        if self.parser_kind not in _PARSER_KINDS | {None}:
            raise ValueError("profile result parser kind is unsupported")
        if self.source not in {"stdout", "artifact"}:
            raise ValueError("profile result source is unsupported")
        if self.source == "artifact":
            if self.source_path is None:
                raise ValueError("artifact result source requires a declared path")
            _validate_relative_path(self.source_path, kind="profile result source path")
        elif self.source_path is not None:
            raise ValueError("stdout result source must not declare an artifact path")

    def _validate_numeric_limits(self) -> None:
        if (
            self.minimum_coverage_percent is not None
            and not 0 <= self.minimum_coverage_percent <= 100
        ):
            raise ValueError("profile coverage threshold is invalid")
        if (
            self.minimum_test_count is not None
            and not 0 <= self.minimum_test_count <= MAX_RESULT_RECORDS
        ):
            raise ValueError("profile test-count rule is invalid")
        if not 1 <= self.maximum_parsed_records <= MAX_RESULT_RECORDS:
            raise ValueError("profile parsed-record limit is invalid")
        if not 1 <= self.maximum_parsed_bytes <= MAX_RESULT_BYTES:
            raise ValueError("profile parsed-byte limit is invalid")

    def _validate_declared_fields(self) -> None:
        if len(set(self.required_summary_fields)) != len(
            self.required_summary_fields
        ) or any(
            not _SAFE_EXCLUSION.fullmatch(value)
            for value in self.required_summary_fields
        ):
            raise ValueError("profile result summary fields are invalid")
        if len(set(self.failure_conditions)) != len(self.failure_conditions) or any(
            not _SAFE_EXCLUSION.fullmatch(value) for value in self.failure_conditions
        ):
            raise ValueError("profile result failure conditions are invalid")

    def _validate_parser_rules(self) -> None:
        if self.parser_kind is None:
            return
        if self.parser_kind == "quality-summary-v1":
            if (
                self.source != "artifact"
                or self.source_path != "reports/quality-summary.json"
            ):
                raise ValueError("quality result source is unsupported")
        elif self.source != "stdout" or self.source_path is not None:
            raise ValueError("profile result source is unsupported")
        if not set(self.required_summary_fields).issubset(
            _RESULT_FIELDS_BY_PARSER.get(self.parser_kind, frozenset())
        ):
            raise ValueError("profile result summary fields are unsupported")
        if not set(self.failure_conditions).issubset(
            _RESULT_FAILURES_BY_PARSER.get(self.parser_kind, frozenset())
        ):
            raise ValueError("profile result failure conditions are unsupported")
        if (
            "coverage-threshold" in self.failure_conditions
            and self.minimum_coverage_percent is None
        ):
            raise ValueError("profile coverage failure condition requires a threshold")
        if self.minimum_coverage_percent is not None and self.parser_kind not in {
            "coverage",
            "pytest-coverage",
            "quality-summary-v1",
        }:
            raise ValueError("profile result coverage parser is unsupported")
        if self.minimum_test_count is not None and self.parser_kind not in {
            "pytest",
            "pytest-coverage",
        }:
            raise ValueError("profile result test parser is unsupported")

    def identity_payload(self) -> dict[str, object]:
        return {
            "failure_conditions": list(self.failure_conditions),
            "maximum_parsed_bytes": self.maximum_parsed_bytes,
            "maximum_parsed_records": self.maximum_parsed_records,
            "minimum_coverage_percent": self.minimum_coverage_percent,
            "minimum_test_count": self.minimum_test_count,
            "parser_kind": self.parser_kind,
            "required_summary_fields": list(self.required_summary_fields),
            "source": self.source,
            "source_path": self.source_path,
        }


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Explicit finite limits that a compatible worker can enforce."""

    maximum_artifact_count: int
    maximum_artifact_bytes: int
    maximum_total_artifact_bytes: int
    retention_days: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ResourceLimits:
        _exact_mapping_keys(
            value,
            {
                "maximum_artifact_count",
                "maximum_artifact_bytes",
                "maximum_total_artifact_bytes",
                "retention_days",
            },
            "resource limits",
        )
        return cls(**value)  # type: ignore[arg-type]

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_artifact_count <= MAX_ARTIFACT_COUNT:
            raise ValueError("profile artifact-count limit is invalid")
        if not 1 <= self.maximum_artifact_bytes <= MAX_ARTIFACT_BYTES:
            raise ValueError("profile per-artifact limit is invalid")
        if not (
            self.maximum_artifact_bytes
            <= self.maximum_total_artifact_bytes
            <= MAX_TOTAL_ARTIFACT_BYTES
        ):
            raise ValueError("profile total-artifact limit is invalid")
        if not 1 <= self.retention_days <= MAX_RETENTION_DAYS:
            raise ValueError("profile retention limit is invalid")

    def identity_payload(self) -> dict[str, int]:
        return {
            "maximum_artifact_bytes": self.maximum_artifact_bytes,
            "maximum_artifact_count": self.maximum_artifact_count,
            "maximum_total_artifact_bytes": self.maximum_total_artifact_bytes,
            "retention_days": self.retention_days,
        }


@dataclass(frozen=True, slots=True)
class WorkloadStep:
    """A shell-free, source-controlled fixed argv step."""

    id: str
    title: str
    argv: tuple[str, ...]
    required: bool
    timeout_seconds: int
    output_summary_limit: int = 4096
    working_directory: str = "."
    environment: tuple[tuple[str, str], ...] = ()
    result_contract: ResultContract | None = None
    artifacts: tuple[ArtifactDeclaration, ...] = ()
    diagnostic_only: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> WorkloadStep:
        _exact_mapping_keys(
            value,
            {
                "id",
                "title",
                "argv",
                "required",
                "timeout_seconds",
                "output_summary_limit",
                "working_directory",
                "environment",
                "result_contract",
                "artifacts",
                "diagnostic_only",
            },
            "step",
        )
        raw_environment = value["environment"]
        if not isinstance(raw_environment, (tuple, list)):
            raise ValueError("profile step environment is invalid")
        environment: list[tuple[str, str]] = []
        for item in raw_environment:
            if (
                not isinstance(item, (tuple, list))
                or len(item) != 2
                or not all(isinstance(part, str) for part in item)
            ):
                raise ValueError("profile step environment is invalid")
            environment.append((item[0], item[1]))
        raw_artifacts = value["artifacts"]
        if not isinstance(raw_artifacts, (tuple, list)) or not all(
            isinstance(item, Mapping) for item in raw_artifacts
        ):
            raise ValueError("profile step artifacts are invalid")
        raw_contract = value["result_contract"]
        if raw_contract is not None and not isinstance(raw_contract, Mapping):
            raise ValueError("profile step result contract is invalid")
        return cls(
            id=value["id"],  # type: ignore[arg-type]
            title=value["title"],  # type: ignore[arg-type]
            argv=_string_tuple(value["argv"], kind="step argv"),
            required=value["required"],  # type: ignore[arg-type]
            timeout_seconds=value["timeout_seconds"],  # type: ignore[arg-type]
            output_summary_limit=value["output_summary_limit"],  # type: ignore[arg-type]
            working_directory=value["working_directory"],  # type: ignore[arg-type]
            environment=tuple(environment),
            result_contract=(
                ResultContract.from_mapping(raw_contract)
                if isinstance(raw_contract, Mapping)
                else None
            ),
            artifacts=tuple(
                ArtifactDeclaration.from_mapping(item) for item in raw_artifacts
            ),
            diagnostic_only=value["diagnostic_only"],  # type: ignore[arg-type]
        )

    def __post_init__(self) -> None:
        if not _STEP_ID.fullmatch(self.id) or not self.title or len(self.title) > 160:
            raise ValueError("profile step identity is invalid")
        _validate_fixed_argv(self.argv)
        if not isinstance(self.required, bool) or self.required == self.diagnostic_only:
            raise ValueError("profile step required/diagnostic policy is invalid")
        if not 1 <= self.timeout_seconds <= MAX_STEP_TIMEOUT_SECONDS:
            raise ValueError("profile step timeout is invalid")
        if not 1 <= self.output_summary_limit <= MAX_OUTPUT_SUMMARY_BYTES:
            raise ValueError("profile step output bound is invalid")
        if self.working_directory != ".":
            _validate_relative_path(
                self.working_directory, kind="profile working directory"
            )
        _validate_environment(self.environment)
        if len({artifact.relative_path for artifact in self.artifacts}) != len(
            self.artifacts
        ):
            raise ValueError("profile step artifact paths must be unique")
        if (
            self.result_contract is not None
            and self.result_contract.parser_kind is None
        ):
            raise ValueError("profile result contract must select a fixed parser")
        if (
            self.result_contract is not None
            and self.result_contract.source == "artifact"
            and self.result_contract.source_path
            not in {artifact.relative_path for artifact in self.artifacts}
        ):
            raise ValueError("profile result source must be a declared artifact")

    def identity_payload(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "artifacts": [artifact.identity_payload() for artifact in self.artifacts],
            "diagnostic_only": self.diagnostic_only,
            "environment": [list(item) for item in self.environment],
            "id": self.id,
            "output_summary_limit": self.output_summary_limit,
            "required": self.required,
            "result_contract": (
                self.result_contract.identity_payload()
                if self.result_contract is not None
                else None
            ),
            "timeout_seconds": self.timeout_seconds,
            "working_directory": self.working_directory,
        }


@dataclass(frozen=True, slots=True)
class WorkloadProfile:
    """One reviewed profile with separate execution and display contracts."""

    repository_full_name: str
    display_name: str
    description: str
    documentation_reference: str
    manifest_name: str
    manifest_version: str
    required_capabilities: Mapping[str, Any]
    environment_policy: Mapping[str, tuple[str, ...]]
    network_policy: str
    repository_write_policy: str
    timeout_seconds: int
    resource_limits: ResourceLimits
    result_affecting_input_paths: tuple[str, ...]
    deterministic_exclusions: tuple[str, ...]
    steps: tuple[WorkloadStep, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> WorkloadProfile:
        _exact_mapping_keys(
            value,
            {
                "repository_full_name",
                "display_name",
                "description",
                "documentation_reference",
                "manifest_name",
                "manifest_version",
                "required_capabilities",
                "environment_policy",
                "network_policy",
                "repository_write_policy",
                "timeout_seconds",
                "resource_limits",
                "result_affecting_input_paths",
                "deterministic_exclusions",
                "steps",
            },
            "definition",
        )
        capabilities = value["required_capabilities"]
        policy = value["environment_policy"]
        limits = value["resource_limits"]
        raw_steps = value["steps"]
        if not isinstance(capabilities, Mapping):
            raise ValueError("profile capabilities are invalid")
        if not isinstance(policy, Mapping):
            raise ValueError("profile environment policy is invalid")
        if not isinstance(limits, Mapping):
            raise ValueError("profile resource limits are invalid")
        if not isinstance(raw_steps, (tuple, list)) or not all(
            isinstance(step, Mapping) for step in raw_steps
        ):
            raise ValueError("profile steps are invalid")
        _exact_mapping_keys(
            policy,
            {"allowed_inherited_keys", "redact_keys"},
            "environment policy",
        )
        return cls(
            repository_full_name=value["repository_full_name"],  # type: ignore[arg-type]
            display_name=value["display_name"],  # type: ignore[arg-type]
            description=value["description"],  # type: ignore[arg-type]
            documentation_reference=value["documentation_reference"],  # type: ignore[arg-type]
            manifest_name=value["manifest_name"],  # type: ignore[arg-type]
            manifest_version=value["manifest_version"],  # type: ignore[arg-type]
            required_capabilities=dict(capabilities),
            environment_policy={
                "allowed_inherited_keys": _string_tuple(
                    policy["allowed_inherited_keys"], kind="inherited environment keys"
                ),
                "redact_keys": _string_tuple(
                    policy["redact_keys"], kind="redacted environment keys"
                ),
            },
            network_policy=value["network_policy"],  # type: ignore[arg-type]
            repository_write_policy=value["repository_write_policy"],  # type: ignore[arg-type]
            timeout_seconds=value["timeout_seconds"],  # type: ignore[arg-type]
            resource_limits=ResourceLimits.from_mapping(limits),
            result_affecting_input_paths=_string_tuple(
                value["result_affecting_input_paths"],
                kind="result-affecting inputs",
            ),
            deterministic_exclusions=_string_tuple(
                value["deterministic_exclusions"], kind="deterministic exclusions"
            ),
            steps=tuple(WorkloadStep.from_mapping(step) for step in raw_steps),
        )

    def __post_init__(self) -> None:  # noqa: PLR0912 - the profile boundary is explicit
        if (
            not _REPOSITORY.fullmatch(self.repository_full_name)
            or any(part in {".", ".."} for part in self.repository_full_name.split("/"))
            or self.repository_full_name not in PUBLIC_WORKLOAD_REPOSITORIES
        ):
            raise ValueError("profile repository is not public and reviewed")
        if not _IDENTITY.fullmatch(self.manifest_name) or not _VERSION.fullmatch(
            self.manifest_version
        ):
            raise ValueError("profile manifest identity is invalid")
        if not self.display_name or len(self.display_name) > 120:
            raise ValueError("profile display name is invalid")
        if not self.description or len(self.description) > 500:
            raise ValueError("profile description is invalid")
        _validate_relative_path(
            self.documentation_reference, kind="profile documentation reference"
        )
        if not self.documentation_reference.startswith(
            "docs/"
        ) or not self.documentation_reference.endswith(".md"):
            raise ValueError("profile documentation reference is invalid")
        _validate_capabilities(self.required_capabilities)
        inherited = self.environment_policy.get("allowed_inherited_keys")
        redacted = self.environment_policy.get("redact_keys")
        if set(self.environment_policy) != {"allowed_inherited_keys", "redact_keys"}:
            raise ValueError("profile environment policy fields are invalid")
        if (
            not isinstance(inherited, tuple)
            or not inherited
            or len(set(inherited)) != len(inherited)
            or not set(inherited).issubset(_ALLOWED_INHERITED_ENVIRONMENT_KEYS)
        ):
            raise ValueError("profile inherited environment policy is unsupported")
        if (
            not isinstance(redacted, tuple)
            or not redacted
            or len(set(redacted)) != len(redacted)
            or any(not _ENVIRONMENT_KEY.fullmatch(key) for key in redacted)
        ):
            raise ValueError("profile redaction policy is invalid")
        if self.network_policy not in {"disabled", "worker_restricted"}:
            raise ValueError("profile network policy is unsupported")
        if self.repository_write_policy != "read_only":
            raise ValueError("profile repository write policy is unsupported")
        if not 1 <= self.timeout_seconds <= MAX_PROFILE_TIMEOUT_SECONDS:
            raise ValueError("profile timeout is invalid")
        if not self.result_affecting_input_paths:
            raise ValueError("profile result-affecting inputs are required")
        paths = list(self.result_affecting_input_paths)
        if len(paths) != len(set(paths)):
            raise ValueError("profile result-affecting inputs must be unique")
        for path in paths:
            _validate_relative_path(path, kind="profile result-affecting input")
        if len(self.steps) == 0 or len(self.steps) > 64:
            raise ValueError("profile step count is invalid")
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("profile step IDs must be unique")
        artifact_paths = [
            artifact.relative_path for step in self.steps for artifact in step.artifacts
        ]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("profile artifact paths must be unique")
        if len(artifact_paths) > self.resource_limits.maximum_artifact_count:
            raise ValueError("profile artifact declarations exceed the fixed limit")
        if len(set(self.deterministic_exclusions)) != len(
            self.deterministic_exclusions
        ) or any(
            not _SAFE_EXCLUSION.fullmatch(value)
            for value in self.deterministic_exclusions
        ):
            raise ValueError("profile deterministic exclusions are invalid")

    @property
    def manifest_identity(self) -> tuple[str, str]:
        return (self.manifest_name, self.manifest_version)

    def identity_payload(self) -> dict[str, object]:
        """Return every execution-relevant value, excluding display wording."""

        return {
            "environment_policy": {
                key: list(value)
                for key, value in sorted(self.environment_policy.items())
            },
            "manifest": {"name": self.manifest_name, "version": self.manifest_version},
            "network_policy": self.network_policy,
            "repository_full_name": self.repository_full_name,
            "repository_write_policy": self.repository_write_policy,
            "required_capabilities": dict(self.required_capabilities),
            "resource_limits": self.resource_limits.identity_payload(),
            "result_affecting_input_paths": list(self.result_affecting_input_paths),
            "schema_version": PROFILE_SCHEMA_VERSION,
            "steps": [step.identity_payload() for step in self.steps],
            "timeout_seconds": self.timeout_seconds,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.identity_payload()).encode("utf-8")
        ).hexdigest()

    def safe_catalog_mapping(self) -> dict[str, object]:
        """Return display-only repository metadata for the public catalog."""

        return {
            "default_manifest": {
                "name": self.manifest_name,
                "version": self.manifest_version,
            },
            "description": self.description,
            "display_name": self.display_name,
            "documentation_reference": self.documentation_reference,
            "full_name": self.repository_full_name,
            "manifests": [
                {"name": self.manifest_name, "version": self.manifest_version}
            ],
            "support_status": "developer_preview",
        }

    def safe_validation_summary(self, manifest_digest: str) -> dict[str, str]:
        return {
            "manifest": f"{self.manifest_name}@{self.manifest_version}",
            "manifest_digest": manifest_digest,
            "repository": self.repository_full_name,
        }


_BASE_ENVIRONMENT_POLICY = {
    "allowed_inherited_keys": (
        "PATH",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
    ),
    "redact_keys": (
        "SWITCHBOARD_ADMIN_TOKEN",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
    ),
}
_FIXED_ENVIRONMENT = (
    ("PIP_DISABLE_PIP_VERSION_CHECK", "1"),
    ("PIP_NO_INPUT", "1"),
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONUTF8", "1"),
)
_DEFAULT_LIMITS = ResourceLimits(
    maximum_artifact_count=32,
    maximum_artifact_bytes=16 * 1024 * 1024,
    maximum_total_artifact_bytes=128 * 1024 * 1024,
    retention_days=14,
)


_ZSCRIPTS_PROFILE = WorkloadProfile(
    repository_full_name="Nobodyworld/dev-logger-zscripts",
    display_name="Dev Logger Zscripts",
    description=(
        "Reviewed deterministic quality validation for the public Zscripts repository."
    ),
    documentation_reference="docs/operations/trusted-workload-onboarding.md",
    manifest_name="validate-zscripts",
    manifest_version="1",
    required_capabilities={
        "git_available": True,
        "node": {"minimum": "24.12.0"},
        "operating_system": ["linux", "windows"],
        "pnpm": {"exact": "10.18.1"},
        "python": {"minimum": "3.11"},
        "repository_write": False,
    },
    environment_policy=_BASE_ENVIRONMENT_POLICY,
    network_policy="worker_restricted",
    repository_write_policy="read_only",
    timeout_seconds=7_200,
    resource_limits=_DEFAULT_LIMITS,
    result_affecting_input_paths=(
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "scripts/quality_gate.py",
        "workspace-ui/package.json",
        "workspace-ui/pnpm-lock.yaml",
    ),
    deterministic_exclusions=(
        "gpu-ml-workloads",
        "live-external-dogfood",
        "publication",
        "semantic-release-review",
    ),
    steps=(
        WorkloadStep(
            id="quality-gate",
            title="Run reviewed quality gate",
            argv=("python", "scripts/quality_gate.py", "quality"),
            required=True,
            timeout_seconds=3_600,
            output_summary_limit=16_384,
            environment=_FIXED_ENVIRONMENT,
            result_contract=ResultContract(
                parser_kind="quality-summary-v1",
                source="artifact",
                source_path="reports/quality-summary.json",
                minimum_coverage_percent=85,
                maximum_parsed_bytes=2 * 1_024 * 1_024,
                required_summary_fields=(
                    "coverage-threshold",
                    "diagnostics",
                    "operations",
                    "profile",
                    "status",
                ),
                failure_conditions=("coverage-threshold", "quality-operation-failure"),
            ),
            artifacts=(
                ArtifactDeclaration(
                    "quality-summary",
                    "reports/quality-summary.json",
                    "application/json",
                ),
                ArtifactDeclaration(
                    "coverage-json", "reports/coverage.json", "application/json"
                ),
                ArtifactDeclaration(
                    "diagnostics-json", "reports/diagnostics.json", "application/json"
                ),
            ),
        ),
    ),
)


_INDUSTRY_PROFILE = WorkloadProfile(
    repository_full_name="Nobodyworld/app-industry-resilience",
    display_name="Industry Resilience",
    description=(
        "Reviewed deterministic Python quality validation for Industry Resilience."
    ),
    documentation_reference="docs/operations/trusted-workload-onboarding.md",
    manifest_name="validate-industry-resilience",
    manifest_version="1",
    required_capabilities={
        "git_available": True,
        "operating_system": ["linux", "windows"],
        "python": {"minimum": "3.13"},
        "repository_write": False,
    },
    environment_policy=_BASE_ENVIRONMENT_POLICY,
    network_policy="worker_restricted",
    repository_write_policy="read_only",
    timeout_seconds=10_800,
    resource_limits=_DEFAULT_LIMITS,
    result_affecting_input_paths=(
        ".github/workflows/ci.yml",
        "Makefile",
        "config/.secrets.baseline",
        "requirements-dev.txt",
        "requirements.txt",
        "src/scripts/benchmark_metrics.py",
    ),
    deterministic_exclusions=(
        "docker-acceptance",
        "edge-acceptance",
        "live-provider-refresh",
        "playwright-acceptance",
        "publication",
        "screen-reader-acceptance",
        "source-scan",
    ),
    steps=(
        WorkloadStep(
            id="python-version",
            title="Record Python version",
            argv=("python", "--version"),
            required=True,
            timeout_seconds=60,
            environment=_FIXED_ENVIRONMENT,
        ),
        WorkloadStep(
            id="dependency-health",
            title="Validate installed dependency consistency",
            argv=("python", "-m", "pip", "check"),
            required=True,
            timeout_seconds=300,
            environment=_FIXED_ENVIRONMENT,
            result_contract=ResultContract(
                parser_kind="dependency-health",
                required_summary_fields=("audit",),
                failure_conditions=("dependency-health",),
            ),
        ),
        WorkloadStep(
            id="format",
            title="Check Black formatting",
            argv=("python", "-m", "black", "--check", "app.py", "src", "tests"),
            required=True,
            timeout_seconds=900,
            environment=_FIXED_ENVIRONMENT,
        ),
        WorkloadStep(
            id="lint",
            title="Run Ruff checks",
            argv=("python", "-m", "ruff", "check", "app.py", "src", "tests"),
            required=True,
            timeout_seconds=900,
            environment=_FIXED_ENVIRONMENT,
        ),
        WorkloadStep(
            id="typecheck",
            title="Run Mypy checks",
            argv=("python", "-m", "mypy", "src"),
            required=True,
            timeout_seconds=1_200,
            environment=_FIXED_ENVIRONMENT,
        ),
        WorkloadStep(
            id="runtime-coverage",
            title="Run runtime coverage with required threshold",
            argv=(
                "python",
                "-m",
                "pytest",
                "--cov=src/adapters",
                "--cov=src/agents",
                "--cov=src/application",
                "--cov=src/core",
                "--cov=src/extensions",
                "--cov=src/infrastructure",
                "--cov=src/interfaces/api",
                "--cov=src/interfaces/streamlit",
                "--cov-report=term-missing",
                "--cov-report=xml:build/reports/runtime-coverage.xml",
                "--cov-report=json:build/reports/runtime-coverage.json",
                "--cov-fail-under=85",
            ),
            required=True,
            timeout_seconds=2_400,
            output_summary_limit=16_384,
            environment=_FIXED_ENVIRONMENT,
            result_contract=ResultContract(
                parser_kind="pytest-coverage",
                minimum_coverage_percent=85,
                minimum_test_count=1,
                required_summary_fields=("coverage", "tests"),
                failure_conditions=("coverage-threshold", "test-failure"),
            ),
            artifacts=(
                ArtifactDeclaration(
                    "coverage-xml",
                    "build/reports/runtime-coverage.xml",
                    "application/xml",
                ),
                ArtifactDeclaration(
                    "coverage-json",
                    "build/reports/runtime-coverage.json",
                    "application/json",
                ),
            ),
        ),
        WorkloadStep(
            id="full-src-coverage",
            title="Record informational full source coverage",
            argv=(
                "python",
                "-m",
                "pytest",
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-report=xml:build/reports/full-src-coverage.xml",
                "--cov-report=json:build/reports/full-src-coverage.json",
            ),
            required=False,
            diagnostic_only=True,
            timeout_seconds=2_400,
            output_summary_limit=16_384,
            environment=_FIXED_ENVIRONMENT,
            result_contract=ResultContract(
                parser_kind="pytest-coverage",
                minimum_test_count=1,
                required_summary_fields=("coverage", "tests"),
                failure_conditions=("test-failure",),
            ),
            artifacts=(
                ArtifactDeclaration(
                    "coverage-xml",
                    "build/reports/full-src-coverage.xml",
                    "application/xml",
                ),
                ArtifactDeclaration(
                    "coverage-json",
                    "build/reports/full-src-coverage.json",
                    "application/json",
                ),
            ),
        ),
        WorkloadStep(
            id="benchmark",
            title="Check benchmark metrics",
            argv=("python", "src/scripts/benchmark_metrics.py", "--check"),
            required=True,
            timeout_seconds=900,
            environment=_FIXED_ENVIRONMENT,
        ),
        WorkloadStep(
            id="dependency-audit",
            title="Audit reviewed runtime and development dependencies",
            argv=(
                "python",
                "-m",
                "pip_audit",
                "-r",
                "requirements.txt",
                "-r",
                "requirements-dev.txt",
                "--format",
                "json",
                "--output",
                "build/reports/pip-audit.json",
            ),
            required=True,
            timeout_seconds=1_200,
            environment=_FIXED_ENVIRONMENT,
            result_contract=ResultContract(
                parser_kind="dependency-audit",
                required_summary_fields=("audit",),
                failure_conditions=("dependency-vulnerability",),
            ),
            artifacts=(
                ArtifactDeclaration(
                    "audit-json", "build/reports/pip-audit.json", "application/json"
                ),
            ),
        ),
        WorkloadStep(
            id="secret-scan",
            title="Validate the detect-secrets baseline without a source scan",
            argv=(
                "python",
                "-m",
                "detect_secrets.pre_commit_hook",
                "--baseline",
                "config/.secrets.baseline",
            ),
            required=True,
            timeout_seconds=900,
            environment=_FIXED_ENVIRONMENT,
            result_contract=ResultContract(
                parser_kind="secret-scan",
                required_summary_fields=("audit",),
                failure_conditions=("baseline-validation",),
            ),
        ),
    ),
)

_WORKLOAD_PROFILES = tuple(
    sorted(
        (_ZSCRIPTS_PROFILE, _INDUSTRY_PROFILE),
        key=lambda profile: profile.repository_full_name,
    )
)


def iter_workload_profiles() -> tuple[WorkloadProfile, ...]:
    """Return the fixed source-controlled external workload profiles."""

    return _WORKLOAD_PROFILES


def validate_workload_profiles(
    profiles: Iterable[WorkloadProfile] = _WORKLOAD_PROFILES,
) -> tuple[WorkloadProfile, ...]:
    """Validate profile identity uniqueness and return canonical source order."""

    definitions = tuple(
        sorted(profiles, key=lambda profile: profile.repository_full_name)
    )
    repository_names = [
        profile.repository_full_name.casefold() for profile in definitions
    ]
    if len(repository_names) != len(set(repository_names)):
        raise ValueError(
            "profile repository identities must be unique without case collisions"
        )
    manifest_identities = [profile.manifest_identity for profile in definitions]
    if len(manifest_identities) != len(set(manifest_identities)):
        raise ValueError("profile manifest identities must be unique")
    if len(definitions) != 2:
        raise ValueError("exactly two reviewed external workload profiles are required")
    return definitions


def profile_catalog_mappings() -> tuple[dict[str, object], ...]:
    """Return safe source mappings consumed by :mod:`server.execution.catalog`."""

    return tuple(
        profile.safe_catalog_mapping() for profile in validate_workload_profiles()
    )


def _profile_manifest_arguments(profile: WorkloadProfile) -> dict[str, object]:
    """Construct non-executable manifest arguments for a supplied typed compiler."""

    artifact_declarations = [
        artifact.identity_payload()
        for step in profile.steps
        for artifact in step.artifacts
    ]
    result_contract = {
        "resource_limits": profile.resource_limits.identity_payload(),
        "schema_version": PROFILE_SCHEMA_VERSION,
        "steps": [
            {
                "id": step.id,
                "result_contract": step.result_contract.identity_payload(),
            }
            for step in profile.steps
            if step.result_contract is not None
        ],
    }
    return {
        "artifact_declarations": artifact_declarations,
        "description": profile.description,
        "environment_policy": {
            key: list(value)
            for key, value in sorted(profile.environment_policy.items())
        },
        "registry_source": "server/execution/workload_profiles.py",
        "required_capabilities": dict(profile.required_capabilities),
        # The existing dependency-lock identity is deliberately reused for every
        # reviewed result-affecting file.  Its name is historical; the worker
        # hashes each declared relative file before exact evidence reuse.
        "dependency_lock_paths": profile.result_affecting_input_paths,
        "result_contract": result_contract,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "timeout_seconds": profile.timeout_seconds,
        "version": profile.manifest_version,
        "name": profile.manifest_name,
    }


def compile_trusted_manifests(
    *,
    manifest_factory: Callable[..., Any],
    step_factory: Callable[..., Any],
    artifact_factory: Callable[..., Any],
    network_policy_factory: Callable[[str], Any],
    repository_write_policy_factory: Callable[[str], Any],
) -> tuple[Any, ...]:
    """Compile only the two reviewed profiles into registry manifest objects.

    Callers inject concrete registry constructors after they exist.  This module
    therefore cannot pull the registry into catalog import initialization.
    """

    compiled: list[Any] = []
    for profile in validate_workload_profiles():
        steps = tuple(
            step_factory(
                id=step.id,
                title=step.title,
                argv=step.argv,
                required=step.required,
                timeout_seconds=step.timeout_seconds,
                output_summary_limit=step.output_summary_limit,
                working_directory=step.working_directory,
                environment=step.environment,
                diagnostic_only=step.diagnostic_only,
                parser_kind=(
                    step.result_contract.parser_kind
                    if step.result_contract is not None
                    else None
                ),
                artifacts=tuple(
                    artifact_factory(
                        kind=artifact.kind,
                        relative_path=artifact.relative_path,
                        media_type=artifact.media_type,
                        redaction_state=artifact.redaction_state,
                    )
                    for artifact in step.artifacts
                ),
            )
            for step in profile.steps
        )
        arguments = _profile_manifest_arguments(profile)
        compiled.append(
            manifest_factory(
                **arguments,
                fixed_step_metadata=[step.safe_metadata() for step in steps],
                execution_steps=steps,
                network_policy=network_policy_factory(profile.network_policy),
                repository_write_policy=repository_write_policy_factory(
                    profile.repository_write_policy
                ),
            )
        )
    return tuple(compiled)


def profile_serialization(profile: WorkloadProfile) -> str:
    """Return deterministic execution-identity serialization for audit tests."""

    return _canonical_json(profile.identity_payload())


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_ARTIFACT_COUNT",
    "MAX_OUTPUT_SUMMARY_BYTES",
    "MAX_PROFILE_TIMEOUT_SECONDS",
    "MAX_RESULT_BYTES",
    "MAX_RESULT_RECORDS",
    "MAX_RETENTION_DAYS",
    "MAX_STEP_TIMEOUT_SECONDS",
    "MAX_TOTAL_ARTIFACT_BYTES",
    "PROFILE_SCHEMA_VERSION",
    "PUBLIC_WORKLOAD_REPOSITORIES",
    "ArtifactDeclaration",
    "ResourceLimits",
    "ResultContract",
    "WorkloadProfile",
    "WorkloadStep",
    "compile_trusted_manifests",
    "iter_workload_profiles",
    "profile_catalog_mappings",
    "profile_serialization",
    "validate_workload_profiles",
]
