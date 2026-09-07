"""Reviewed operator guidance; never render untrusted exception values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperatorDiagnostic:
    reason: str
    guidance: str


_GUIDANCE = {
    "public_identity_rejected": (
        "Review the configured logical identity; public output must not contain "
        "private credential values or unsafe text."
    ),
    "preflight_probe_failed": (
        "A read-only probe could not complete. Review host access and the "
        "configured prerequisites before further execution."
    ),
    "runtime_parent_invalid": (
        "Choose a new runtime root under an existing regular local directory."
    ),
    "loopback_port_probe_failed": (
        "Check loopback availability and access before executing validation."
    ),
    "invalid_arguments": (
        "Review the command's documented arguments and output format."
    ),
    "invalid_configuration": (
        "Review the private configuration against the documented schema and limits."
    ),
    "admin_token_missing": (
        "Provide the existing operator credential in the process environment, "
        "then check readiness again."
    ),
    "python_version_unsupported": (
        "Select the supported Python runtime before checking readiness again."
    ),
    "strict_containment_unsupported": (
        "Use a host with supported process containment before executing validation."
    ),
    "git_probe_failed": (
        "Check that Git is available and the approved checkout can be inspected."
    ),
    "worker_capability_mismatch": (
        "Compare installed runtime versions with the selected trusted manifest "
        "requirements."
    ),
    "control_plane_source_invalid": (
        "Review the trusted Switchboard installation and its required internal "
        "modules before executing validation."
    ),
    "control_plane_source_reparse_ancestry": (
        "Use a trusted Switchboard installation without linked or reparse ancestry."
    ),
    "control_plane_target_overlap": (
        "Review the selected target checkout and trusted Switchboard source roots; "
        "distinct repositories require separate roots."
    ),
    "canonical_checkout_invalid": "Select an existing, regular, approved Git checkout.",
    "canonical_checkout_reparse_ancestry": (
        "Select a canonical checkout without linked or reparse ancestry."
    ),
    "source_head_mismatch": (
        "Review the approved checkout and exact requested commit; they must match."
    ),
    "source_checkout_dirty": (
        "Review the checkout changes and select a clean approved source "
        "before executing."
    ),
    "source_origin_invalid": (
        "Review the configured repository and the checkout GitHub origin."
    ),
    "source_origin_mismatch": (
        "Review the configured repository and the checkout GitHub origin; "
        "they must identify the same repository."
    ),
    "source_checkout_changed": (
        "Preserve the runtime and review the canonical source change before "
        "further execution."
    ),
    "runtime_root_already_exists": (
        "Preserve the existing runtime and choose a new absent runtime root."
    ),
    "runtime_root_invalid": (
        "Select a marker-owned runtime for inspection; "
        "preserve uncertain existing state."
    ),
    "runtime_path_budget_exceeded": (
        "Choose a shorter new runtime root within the documented platform limit."
    ),
    "runtime_parent_reparse_ancestry": (
        "Choose a new runtime root with existing non-linked parent ancestry."
    ),
    "runtime_source_overlap": (
        "Choose a new runtime root separate from the canonical checkout."
    ),
    "path_inspection_failed": (
        "Review access to the configured paths and their ancestry before execution."
    ),
    "loopback_port_occupied": (
        "Review the configured loopback port and select one that is "
        "currently available."
    ),
    "trusted_manifest_not_found": (
        "Select a reviewed manifest name and version from the existing "
        "workload catalog."
    ),
    "trusted_manifest_digest_mismatch": (
        "Review the expected digest against the selected reviewed manifest."
    ),
    "trusted_manifest_contract_unsupported": (
        "Select a supported reviewed read-only validation manifest."
    ),
    "manifest_timeout_exceeds_worker_budget": (
        "Review the configured work-order budget against the required manifest "
        "timeout; limits are not increased automatically."
    ),
    "manifest_step_timeout_exceeds_worker_budget": (
        "Review the configured work-order budget against every required step timeout."
    ),
    "terminal_timeout_below_manifest_budget": (
        "Review the terminal observation budget against the required manifest timeout."
    ),
    "fresh_approval_denied": (
        "Review the exact fresh work order and deliberately approve it "
        "only if intended."
    ),
    "reuse_approval_denied": (
        "Review the exact reuse work order and deliberately approve it separately "
        "if intended."
    ),
    "operator_interrupted": (
        "Inspect the retained runtime before deciding on any further execution."
    ),
    "runtime_ownership_lost": (
        "Preserve runtime and process state for operator diagnosis; "
        "do not repair ownership automatically."
    ),
    "runtime_report_invalid": (
        "Preserve the stored report; inspection does not repair or reverify "
        "historical evidence."
    ),
    "owned_process_cleanup_unproven": (
        "Preserve the runtime and review owned process state before further execution."
    ),
    "loopback_port_not_released": (
        "Preserve the runtime and review the configured port before further execution."
    ),
    "operator_output_failed": (
        "The output channel failed; inspect any retained runtime "
        "before further execution."
    ),
    "operator_lifecycle_failure": (
        "Review the bounded result and any retained runtime with the operator guide "
        "before further execution."
    ),
}


def operator_diagnostic(reason: object) -> OperatorDiagnostic:
    """Select fixed prose and codes; an unknown value is never echoed."""

    if isinstance(reason, str) and reason.startswith("invalid_configuration:"):
        key = "invalid_configuration"
    elif isinstance(reason, str) and reason in _GUIDANCE:
        key = reason
    else:
        key = "operator_lifecycle_failure"
    return OperatorDiagnostic(key, _GUIDANCE[key])
