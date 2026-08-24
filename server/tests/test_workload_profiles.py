"""Focused offline conformance tests for source-controlled workload profiles."""

# ruff: noqa: PLR2004

from __future__ import annotations

import dataclasses
import json
import socket
from dataclasses import replace

import pytest
from scripts import dev

from server.execution import workload_profiles as profiles_module
from server.execution.catalog import iter_trusted_repositories, trusted_catalog_digest
from server.execution.registry import get_trusted_manifest
from server.execution.workload_profiles import (
    ArtifactDeclaration,
    ResourceLimits,
    ResultContract,
    WorkloadProfile,
    WorkloadStep,
    iter_workload_profiles,
    profile_serialization,
    validate_workload_profiles,
)

_LEGACY_DIGESTS = {
    "worker-smoke@1": (
        # pragma: allowlist nextline secret
        "63e645f19d8c60ae442e1800aaecc1a18a719d53f22ba8e85ec62bf745ed55d1"
    ),
    "validate-switchboard@1": (
        # pragma: allowlist nextline secret
        "10e99418e4e6f0e9f4a6e95fb5b9a267dab4eeac4671cf58533c8b9afe1fed98"
    ),
    "validate-accounting-modular@1": (
        # pragma: allowlist nextline secret
        "892f1269cdf2a6f4e0df4d86879e5dae980374d598faeadee77c2c32f33aa612"
    ),
}
# pragma: allowlist nextline secret
_CATALOG_DIGEST = "8303bcc8c577557adccc7c299fc2816744f1c7a3c5f0f5ac39146d49c9643115"
_NEW_MANIFEST_DIGESTS = {
    "validate-industry-resilience@1": (
        # pragma: allowlist nextline secret
        "dfda235a1dda46fd144341e0105a9093396770698bf2a11c737bc7cfa5547ac6"
    ),
    "validate-zscripts@1": (
        # pragma: allowlist nextline secret
        "c449d97cc63bb9c28c293e4798a116261fb01ece55cc92407dd4a8a330d3107e"
    ),
}


def _manifest(identity: str):
    name, version = identity.split("@", maxsplit=1)
    manifest = get_trusted_manifest(name, version)
    assert manifest is not None
    return manifest


def test_profiles_compile_deterministically_without_moving_legacy_identities() -> None:
    profiles = iter_workload_profiles()
    assert [profile.repository_full_name for profile in profiles] == [
        "Nobodyworld/app-industry-resilience",
        "Nobodyworld/dev-logger-zscripts",
    ]
    assert profile_serialization(profiles[0]) == profile_serialization(profiles[0])
    assert trusted_catalog_digest() == _CATALOG_DIGEST
    assert [repository.full_name for repository in iter_trusted_repositories()] == [
        "Nobodyworld/app-accounting-modular",
        "Nobodyworld/app-industry-resilience",
        "Nobodyworld/dev-agent-switchboard",
        "Nobodyworld/dev-logger-zscripts",
    ]

    for identity, digest in _LEGACY_DIGESTS.items():
        assert _manifest(identity).digest == digest
    for identity, digest in _NEW_MANIFEST_DIGESTS.items():
        assert _manifest(identity).digest == digest

    zscripts = _manifest("validate-zscripts@1")
    assert zscripts.dependency_lock_paths == (
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "scripts/quality_gate.py",
        "workspace-ui/package.json",
        "workspace-ui/pnpm-lock.yaml",
    )
    assert zscripts.execution_steps[0].parser_kind == "quality-summary-v1"
    assert zscripts.result_contract is not None
    industry = _manifest("validate-industry-resilience@1")
    assert len(industry.execution_steps) == 10
    assert industry.required_capabilities["python"] == {"minimum": "3.13"}


def test_display_metadata_does_not_change_identity_but_result_inputs_do() -> None:
    profile = iter_workload_profiles()[0]
    assert (
        replace(profile, description="A safe revised display sentence.").digest
        == profile.digest
    )
    assert (
        replace(
            profile,
            result_affecting_input_paths=(
                *profile.result_affecting_input_paths,
                "additional-reviewed-input.txt",
            ),
        ).digest
        != profile.digest
    )


def test_profile_mapping_and_construction_fail_closed() -> None:
    profile = iter_workload_profiles()[0]
    serialized = dataclasses.asdict(profile)
    with pytest.raises(ValueError, match="fields are invalid"):
        WorkloadProfile.from_mapping({**serialized, "unexpected": "nope"})
    assert WorkloadProfile.from_mapping(serialized).digest == profile.digest

    with pytest.raises(ValueError, match="shell"):
        WorkloadStep(
            id="shell",
            title="Unsafe shell",
            argv=("sh", "-c", "unsafe"),
            required=True,
            timeout_seconds=1,
        )
    with pytest.raises(ValueError, match="absolute"):
        WorkloadStep(
            id="absolute-path",
            title="Unsafe path",
            argv=("python", "C:/unsafe.py"),
            required=True,
            timeout_seconds=1,
        )
    with pytest.raises(ValueError, match="traversal"):
        WorkloadStep(
            id="traversal-path",
            title="Unsafe traversal",
            argv=("python", "../outside.py"),
            required=True,
            timeout_seconds=1,
        )
    with pytest.raises(ValueError, match="traversal"):
        WorkloadStep(
            id="attached-traversal-path",
            title="Unsafe attached traversal",
            argv=("python", "--output=../outside.json"),
            required=True,
            timeout_seconds=1,
        )
    with pytest.raises(ValueError, match="unsupported"):
        ResultContract(parser_kind="runtime-import")
    with pytest.raises(ValueError, match="source"):
        ResultContract(
            parser_kind="pytest",
            source="artifact",
            source_path="reports/results.json",
        )
    with pytest.raises(ValueError, match="coverage parser"):
        ResultContract(parser_kind="dependency-audit", minimum_coverage_percent=85)
    with pytest.raises(ValueError, match="declared artifact"):
        WorkloadStep(
            id="artifact-parser",
            title="Missing declared parser input",
            argv=("python", "tool.py"),
            required=True,
            timeout_seconds=1,
            result_contract=ResultContract(
                parser_kind="quality-summary-v1",
                source="artifact",
                source_path="reports/quality-summary.json",
            ),
        )
    with pytest.raises(ValueError, match="artifact paths"):
        replace(
            profile,
            steps=(
                replace(
                    profile.steps[0],
                    artifacts=(
                        ArtifactDeclaration(
                            "first", "reports/same.json", "application/json"
                        ),
                        ArtifactDeclaration(
                            "second", "reports/same.json", "application/json"
                        ),
                    ),
                ),
                *profile.steps[1:],
            ),
        )
    with pytest.raises(ValueError, match="result-affecting inputs"):
        replace(profile, result_affecting_input_paths=())
    with pytest.raises(ValueError, match="capability requirement"):
        replace(
            profile,
            required_capabilities={
                **profile.required_capabilities,
                "arbitrary-runtime-plugin": True,
            },
        )


def test_profile_primitives_reject_untrusted_values() -> None:
    for value, message in (
        ("", "bounded relative POSIX path"),
        ("reports/../outside.json", "traversal or dot segments"),
    ):
        with pytest.raises(ValueError, match=message):
            profiles_module._validate_relative_path(value, kind="test path")

    for argv, message in (
        ((), "non-empty fixed tuple"),
        (("python", "-c"), "shell invocation"),
    ):
        with pytest.raises(ValueError, match=message):
            profiles_module._validate_fixed_argv(argv)

    for environment, message in (
        (
            (("PIP_NO_INPUT", "1"), ("PIP_NO_INPUT", "0")),
            "keys must be unique",
        ),
        ((("UNREVIEWED_SETTING", "1"),), "key is unsupported"),
        ((("PIP_NO_INPUT", ""),), "value is invalid"),
    ):
        with pytest.raises(ValueError, match=message):
            profiles_module._validate_environment(environment)

    requirements = dict(iter_workload_profiles()[0].required_capabilities)
    invalid_capabilities = (
        ({**requirements, "operating_system": ("darwin",)}, "operating-system"),
        ({**requirements, "python": {}}, "runtime capability is invalid"),
        (
            {**requirements, "python": {"minimum": "v3"}},
            "runtime capability version is invalid",
        ),
        ({**requirements, "git_available": False}, "require Git availability"),
        (
            {**requirements, "repository_write": True},
            "prohibit repository writes",
        ),
    )
    for candidate, message in invalid_capabilities:
        with pytest.raises(ValueError, match=message):
            profiles_module._validate_capabilities(candidate)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"kind": "Invalid Kind"}, "artifact kind is invalid"),
        ({"media_type": "not a media type"}, "artifact media type is invalid"),
        ({"redaction_state": "scrubbed"}, "redaction state is invalid"),
        ({"maximum_bytes": 0}, "artifact bounds are invalid"),
    ),
)
def test_artifact_declaration_rejects_invalid_boundaries(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ArtifactDeclaration(
            kind=kwargs.get("kind", "report"),  # type: ignore[arg-type]
            relative_path="reports/output.json",
            media_type=kwargs.get("media_type", "application/json"),  # type: ignore[arg-type]
            redaction_state=kwargs.get("redaction_state", "none"),  # type: ignore[arg-type]
            maximum_bytes=kwargs.get("maximum_bytes", 1),  # type: ignore[arg-type]
        )


def test_result_contract_rejects_each_closed_validation_boundary() -> None:
    invalid_contracts = (
        (
            {"parser_kind": "pytest", "source": "file"},
            "result source is unsupported",
        ),
        (
            {"parser_kind": "pytest", "source": "artifact"},
            "requires a declared path",
        ),
        (
            {
                "parser_kind": "pytest",
                "source_path": "reports/results.json",
            },
            "must not declare an artifact path",
        ),
        (
            {"parser_kind": "coverage", "minimum_coverage_percent": 101},
            "coverage threshold is invalid",
        ),
        (
            {"parser_kind": "pytest", "minimum_test_count": -1},
            "test-count rule is invalid",
        ),
        (
            {"parser_kind": "pytest", "maximum_parsed_records": 0},
            "parsed-record limit is invalid",
        ),
        (
            {"parser_kind": "pytest", "maximum_parsed_bytes": 0},
            "parsed-byte limit is invalid",
        ),
        (
            {
                "parser_kind": "pytest",
                "required_summary_fields": ("tests", "tests"),
            },
            "summary fields are invalid",
        ),
        (
            {
                "parser_kind": "pytest",
                "failure_conditions": ("not a supported condition",),
            },
            "failure conditions are invalid",
        ),
        (
            {"parser_kind": "quality-summary-v1"},
            "quality result source is unsupported",
        ),
        (
            {"parser_kind": "pytest", "required_summary_fields": ("audit",)},
            "summary fields are unsupported",
        ),
        (
            {
                "parser_kind": "pytest",
                "failure_conditions": ("dependency-vulnerability",),
            },
            "failure conditions are unsupported",
        ),
        (
            {
                "parser_kind": "pytest-coverage",
                "failure_conditions": ("coverage-threshold",),
            },
            "requires a threshold",
        ),
        (
            {"parser_kind": "coverage", "minimum_test_count": 1},
            "test parser is unsupported",
        ),
    )
    for kwargs, message in invalid_contracts:
        with pytest.raises(ValueError, match=message):
            ResultContract(**kwargs)  # type: ignore[arg-type]

    contract = ResultContract(parser_kind=None)
    assert contract.parser_kind is None
    source_contract = next(
        step.result_contract
        for profile in iter_workload_profiles()
        for step in profile.steps
        if step.result_contract is not None
    )
    mapped_contract = dataclasses.asdict(source_contract)
    assert ResultContract.from_mapping(mapped_contract) == source_contract


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"maximum_artifact_count": 0}, "artifact-count limit is invalid"),
        ({"maximum_artifact_bytes": 0}, "per-artifact limit is invalid"),
        (
            {
                "maximum_artifact_bytes": 2,
                "maximum_total_artifact_bytes": 1,
            },
            "total-artifact limit is invalid",
        ),
        ({"retention_days": 0}, "retention limit is invalid"),
    ),
)
def test_resource_limits_reject_invalid_boundaries(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ResourceLimits(
            maximum_artifact_count=kwargs.get("maximum_artifact_count", 1),
            maximum_artifact_bytes=kwargs.get("maximum_artifact_bytes", 1),
            maximum_total_artifact_bytes=kwargs.get("maximum_total_artifact_bytes", 1),
            retention_days=kwargs.get("retention_days", 1),
        )

    profile = iter_workload_profiles()[0]
    assert ResourceLimits.from_mapping(dataclasses.asdict(profile.resource_limits)) == (
        profile.resource_limits
    )


def test_step_mapping_and_constructor_boundaries_fail_closed() -> None:
    step = iter_workload_profiles()[0].steps[0]
    for field, value, message in (
        ("environment", {"PIP_NO_INPUT": "1"}, "environment is invalid"),
        ("environment", (("PIP_NO_INPUT", 1),), "environment is invalid"),
        ("artifacts", (object(),), "artifacts are invalid"),
        ("result_contract", (), "result contract is invalid"),
    ):
        mapped = dataclasses.asdict(step)
        mapped[field] = value
        with pytest.raises(ValueError, match=message):
            WorkloadStep.from_mapping(mapped)

    assert WorkloadStep.from_mapping(dataclasses.asdict(step)) == step
    for replacement, message in (
        ({"id": "Invalid"}, "step identity is invalid"),
        (
            {"required": False, "diagnostic_only": False},
            "required/diagnostic policy is invalid",
        ),
        ({"timeout_seconds": 0}, "step timeout is invalid"),
        ({"output_summary_limit": 0}, "output bound is invalid"),
        ({"working_directory": "../outside"}, "working directory"),
        (
            {"result_contract": ResultContract(parser_kind=None)},
            "must select a fixed parser",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            replace(step, **replacement)


def test_profile_mapping_and_constructor_boundaries_fail_closed() -> None:
    profile = iter_workload_profiles()[0]
    for field, value, message in (
        ("required_capabilities", (), "capabilities are invalid"),
        ("environment_policy", (), "environment policy is invalid"),
        ("resource_limits", (), "resource limits are invalid"),
        ("steps", (object(),), "steps are invalid"),
    ):
        mapped = dataclasses.asdict(profile)
        mapped[field] = value
        with pytest.raises(ValueError, match=message):
            WorkloadProfile.from_mapping(mapped)

    invalid_replacements = (
        ({"manifest_name": "invalid/name"}, "manifest identity is invalid"),
        ({"display_name": ""}, "display name is invalid"),
        ({"description": ""}, "description is invalid"),
        (
            {"documentation_reference": "README.md"},
            "documentation reference is invalid",
        ),
        (
            {
                "environment_policy": {
                    "allowed_inherited_keys": profile.environment_policy[
                        "allowed_inherited_keys"
                    ]
                }
            },
            "environment policy fields are invalid",
        ),
        (
            {
                "environment_policy": {
                    "allowed_inherited_keys": (),
                    "redact_keys": profile.environment_policy["redact_keys"],
                }
            },
            "inherited environment policy is unsupported",
        ),
        (
            {
                "environment_policy": {
                    "allowed_inherited_keys": profile.environment_policy[
                        "allowed_inherited_keys"
                    ],
                    "redact_keys": (),
                }
            },
            "redaction policy is invalid",
        ),
        ({"network_policy": "unrestricted"}, "network policy is unsupported"),
        (
            {"repository_write_policy": "write"},
            "repository write policy is unsupported",
        ),
        ({"timeout_seconds": 0}, "profile timeout is invalid"),
        (
            {
                "result_affecting_input_paths": (
                    profile.result_affecting_input_paths[0],
                    profile.result_affecting_input_paths[0],
                )
            },
            "result-affecting inputs must be unique",
        ),
        ({"steps": ()}, "step count is invalid"),
        (
            {"steps": (profile.steps[0], profile.steps[0])},
            "step IDs must be unique",
        ),
        (
            {
                "resource_limits": replace(
                    profile.resource_limits, maximum_artifact_count=1
                )
            },
            "artifact declarations exceed the fixed limit",
        ),
        (
            {
                "deterministic_exclusions": (
                    profile.deterministic_exclusions[0],
                    profile.deterministic_exclusions[0],
                )
            },
            "deterministic exclusions are invalid",
        ),
    )
    for replacement, message in invalid_replacements:
        with pytest.raises(ValueError, match=message):
            replace(profile, **replacement)

    artifact_step = next(step for step in profile.steps if step.artifacts)
    duplicate_artifact_step = replace(artifact_step, id=f"{artifact_step.id}-copy")
    with pytest.raises(ValueError, match="artifact paths must be unique"):
        replace(profile, steps=(artifact_step, duplicate_artifact_step))


def test_profile_set_validation_defends_against_corrupted_instances() -> None:
    first, second = iter_workload_profiles()
    collision = replace(second)
    object.__setattr__(
        collision, "repository_full_name", first.repository_full_name.swapcase()
    )
    with pytest.raises(ValueError, match="repository identities must be unique"):
        validate_workload_profiles((first, collision))
    with pytest.raises(ValueError, match="exactly two reviewed external"):
        validate_workload_profiles((first,))


def test_profile_set_rejects_case_collisions_and_duplicate_manifests() -> None:
    first, second = iter_workload_profiles()
    with pytest.raises(ValueError, match="public and reviewed"):
        replace(
            second,
            repository_full_name=first.repository_full_name.swapcase(),
        )
    duplicate_manifest = replace(
        second,
        manifest_name=first.manifest_name,
        manifest_version=first.manifest_version,
    )
    with pytest.raises(ValueError, match="manifest identities"):
        validate_workload_profiles((first, duplicate_manifest))


def test_validate_workload_catalog_is_offline_safe_and_bounded(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("offline catalog validation must not execute or connect")

    monkeypatch.setattr(dev.subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    dev.main(["validate-workload-catalog"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"
    assert payload["repository_count"] == 4
    assert payload["catalog_digest"] == _CATALOG_DIGEST
    serialized = json.dumps(payload, sort_keys=True)
    assert "argv" not in serialized
    assert "environment" not in serialized
    assert "quality_gate.py" not in serialized


def test_validate_workload_catalog_fails_closed_without_echoing_bad_source(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid_profiles() -> tuple[object, ...]:
        raise ValueError("C:/private/path --unsafe-argv")

    monkeypatch.setattr(profiles_module, "validate_workload_profiles", invalid_profiles)
    with pytest.raises(SystemExit, match="1"):
        dev.main(["validate-workload-catalog"])
    assert capsys.readouterr().out == "workload catalog validation failed\n"
