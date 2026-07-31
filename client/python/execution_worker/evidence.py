"""Worker-owned retained evidence storage, hashing, and verified retention."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from server.execution.evidence import (
    ArtifactRecord,
    EvidenceReuseIdentity,
    ExecutionEvidence,
    ReuseCandidate,
    compute_reuse_identity_hash,
    validate_relative_path,
)
from server.execution.registry import TrustedArtifact

_MARKER_NAME = "ownership.json"
_MARKER_SCHEMA_VERSION = 1
_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_RETENTION_DAYS = 3650


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _contains(child: Path, root: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or _contains(first, second) or _contains(second, first)


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse)


def _assert_no_reparse_ancestry(path: Path) -> None:
    absolute = _absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists() and not current.is_symlink():
            continue
        if _is_reparse(os.lstat(current)):
            raise ValueError(f"unsafe symlink or reparse-point path: {current}")


def _assert_regular_contained(path: Path, root: Path) -> os.stat_result:
    _assert_no_reparse_ancestry(path)
    if not _contains(path, root):
        raise ValueError("evidence artifact escaped its owned run directory")
    metadata = os.lstat(path)
    if _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("evidence artifact must be a regular non-reparse file")
    return metadata


def _safe_path(root: Path, relative_path: str) -> Path:
    normalized = validate_relative_path(relative_path)
    path = root.joinpath(*PurePosixPath(normalized).parts)
    if not _contains(path, root):
        raise ValueError("evidence path escaped its owned run directory")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def hash_declared_file(root: Path, relative_path: str) -> tuple[int, str]:
    """Hash one trusted relative regular file beneath a canonical root."""

    root = _absolute(root)
    _assert_no_reparse_ancestry(root)
    path = _safe_path(root, relative_path)
    before = _assert_regular_contained(path, root)
    digest = _sha256(path)
    after = _assert_regular_contained(path, root)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("declared file changed while being hashed")
    return after.st_size, digest


@dataclass(frozen=True, slots=True)
class EvidenceLimits:
    maximum_artifact_count: int
    maximum_artifact_bytes: int
    maximum_total_bytes: int


@dataclass(frozen=True, slots=True)
class PruneResult:
    removed_run_ids: tuple[int, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReuseVerificationResult:
    """Bounded local verification disposition without paths or artifact bytes."""

    verified: bool
    reason: str


@dataclass(slots=True)
class EvidenceStore:
    """One marker-bound evidence directory owned by one worker run."""

    root: Path
    run_directory: Path
    worker_id: str
    run_id: int
    created_at: dt.datetime
    retention_expires_at: dt.datetime
    limits: EvidenceLimits

    @property
    def marker(self) -> Path:
        return self.run_directory / _MARKER_NAME

    @property
    def logs(self) -> Path:
        return self.run_directory / "logs"

    @property
    def artifacts(self) -> Path:
        return self.run_directory / "artifacts"

    @property
    def result(self) -> Path:
        return self.run_directory / "result.json"

    def expected_marker(self) -> dict[str, object]:
        return {
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "retention_expires_at": self.retention_expires_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "run_id": self.run_id,
            "schema_version": _MARKER_SCHEMA_VERSION,
            "worker_id": self.worker_id,
        }

    def verify_ownership(self) -> None:
        if self.run_directory == self.root or not _contains(
            self.run_directory, self.root
        ):
            raise RuntimeError("refusing ambiguous evidence directory")
        _assert_no_reparse_ancestry(self.run_directory)
        metadata = os.lstat(self.marker)
        if _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("evidence ownership marker is not a regular file")
        try:
            marker = json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("evidence ownership marker is unreadable") from error
        if marker != self.expected_marker():
            raise RuntimeError("evidence ownership marker does not match this run")

    def finalize_artifacts(
        self,
        declarations: tuple[tuple[str, TrustedArtifact], ...],
    ) -> list[ArtifactRecord]:
        """Verify, bound, and stream-hash all trusted declared artifacts."""

        self.verify_ownership()
        if len(declarations) > self.limits.maximum_artifact_count:
            raise ValueError("maximum artifact count exceeded")
        if len({item.relative_path for _, item in declarations}) != len(declarations):
            raise ValueError("duplicate trusted artifact path")
        records: list[ArtifactRecord] = []
        total = 0
        for step_id, declaration in declarations:
            path = _safe_path(self.run_directory, declaration.relative_path)
            before = _assert_regular_contained(path, self.run_directory)
            size = before.st_size
            if size > self.limits.maximum_artifact_bytes:
                raise ValueError("maximum bytes per artifact exceeded")
            total += size
            if total > self.limits.maximum_total_bytes:
                raise ValueError("maximum total evidence bytes exceeded")
            digest = _sha256(path)
            after = _assert_regular_contained(path, self.run_directory)
            if (before.st_size, before.st_mtime_ns) != (
                after.st_size,
                after.st_mtime_ns,
            ):
                raise RuntimeError("artifact changed while being hashed")
            records.append(
                ArtifactRecord(
                    kind=declaration.kind,
                    relative_path=declaration.relative_path,
                    size_bytes=size,
                    sha256=digest,
                    media_type=declaration.media_type,
                    retention_expires_at=self.retention_expires_at,
                    redaction_state=declaration.redaction_state,
                    produced_by_step=step_id,
                )
            )
        return records

    def write_result(self, payload: dict[str, object]) -> None:
        """Write the bounded final local record after evidence validation."""

        self.verify_ownership()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > self.limits.maximum_artifact_bytes:
            raise ValueError("local result record exceeds per-artifact limit")
        self.result.write_text(encoded, encoding="utf-8")
        _assert_regular_contained(self.result, self.run_directory)


def create_evidence_store(  # noqa: PLR0913 - policy inputs remain explicit
    *,
    evidence_root: Path,
    worker_root: Path,
    repository_roots: tuple[Path, ...],
    worker_id: str,
    run_id: int,
    created_at: dt.datetime,
    retention_days: int,
    limits: EvidenceLimits,
) -> EvidenceStore:
    """Create one new unambiguous marked evidence directory."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("evidence creation time must be timezone-aware")
    if not worker_id or run_id < 1 or not 1 <= retention_days <= _MAX_RETENTION_DAYS:
        raise ValueError("invalid evidence ownership or retention policy")
    if (
        limits.maximum_artifact_count < 1
        or limits.maximum_artifact_bytes < 1
        or limits.maximum_total_bytes < limits.maximum_artifact_bytes
    ):
        raise ValueError("invalid evidence artifact limits")
    root = _absolute(evidence_root)
    source_root = _absolute(worker_root)
    _assert_no_reparse_ancestry(root)
    if _overlaps(root, source_root) or any(
        _overlaps(root, _absolute(repository)) for repository in repository_roots
    ):
        raise ValueError("evidence root must not overlap source or repository roots")
    root.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_ancestry(root)
    run_directory = root / f"run-{run_id}"
    if run_directory.exists() or run_directory.is_symlink():
        raise FileExistsError("evidence run directory already exists")
    run_directory.mkdir()
    (run_directory / "logs").mkdir()
    (run_directory / "artifacts").mkdir()
    created_utc = created_at.astimezone(dt.UTC)
    store = EvidenceStore(
        root=root,
        run_directory=run_directory,
        worker_id=worker_id,
        run_id=run_id,
        created_at=created_utc,
        retention_expires_at=created_utc + dt.timedelta(days=retention_days),
        limits=limits,
    )
    store.marker.write_text(
        json.dumps(store.expected_marker(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    store.verify_ownership()
    return store


def _read_stable_json(path: Path, root: Path, *, maximum_bytes: int) -> object:
    before = _assert_regular_contained(path, root)
    if before.st_size > maximum_bytes:
        raise ValueError("local JSON record exceeds configured bound")
    data = path.read_bytes()
    after = _assert_regular_contained(path, root)
    if (
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise RuntimeError("local JSON record changed while being read")
    return json.loads(data.decode("utf-8"))


def verify_reuse_candidate(  # noqa: PLR0911, PLR0912 - fail-closed reasons are explicit
    *,
    evidence_root: Path,
    worker_id: str,
    candidate: ReuseCandidate,
    now: dt.datetime,
    limits: EvidenceLimits,
) -> ReuseVerificationResult:
    """Reopen and verify one server-selected source beneath the local root."""

    if now.tzinfo is None or now.utcoffset() is None:
        return ReuseVerificationResult(False, "reuse_verification_time_invalid")
    if candidate.expected_source_worker_id != worker_id:
        return ReuseVerificationResult(False, "source_worker_mismatch")
    if candidate.retention_expires_at <= now.astimezone(dt.UTC):
        return ReuseVerificationResult(False, "source_evidence_expired")
    if len(candidate.artifacts) > limits.maximum_artifact_count:
        return ReuseVerificationResult(False, "source_artifact_count_oversized")
    root = _absolute(evidence_root)
    run_directory = root / f"run-{candidate.source_run_id}"
    try:
        _assert_no_reparse_ancestry(root)
        store = EvidenceStore(
            root=root,
            run_directory=run_directory,
            worker_id=worker_id,
            run_id=candidate.source_run_id,
            created_at=candidate.source_created_at,
            retention_expires_at=candidate.retention_expires_at,
            limits=limits,
        )
        store.verify_ownership()
    except FileNotFoundError:
        return ReuseVerificationResult(False, "source_evidence_missing")
    except (OSError, ValueError, RuntimeError):
        return ReuseVerificationResult(False, "source_marker_invalid")

    try:
        payload = _read_stable_json(
            store.result,
            store.run_directory,
            maximum_bytes=limits.maximum_artifact_bytes,
        )
        if not isinstance(payload, dict) or set(payload) != {
            "evidence",
            "result_summary",
            "reuse_identity",
            "reuse_identity_hash",
        }:
            return ReuseVerificationResult(False, "source_result_invalid")
        evidence = ExecutionEvidence.model_validate(payload["evidence"])
        identity = EvidenceReuseIdentity.model_validate(payload["reuse_identity"])
        identity_hash = payload["reuse_identity_hash"]
        provenance = evidence.reuse_provenance
        if (
            not isinstance(identity_hash, str)
            or identity != candidate.reuse_identity
            or identity_hash != candidate.reuse_identity_hash
            or identity_hash != compute_reuse_identity_hash(identity)
            or evidence.run_id != candidate.source_run_id
            or evidence.worker_id != worker_id
            or evidence.terminal_status != "succeeded"
            or evidence.fingerprint != candidate.expected_source_evidence_fingerprint
            or evidence.repository_full_name != identity.repository_full_name
            or evidence.tested_sha != identity.tested_sha
            or evidence.manifest_name != identity.manifest_name
            or evidence.manifest_version != identity.manifest_version
            or evidence.manifest_digest != identity.manifest_digest
            or evidence.environment.fingerprint
            != identity.worker_environment_fingerprint
            or evidence.dependency_lock_hashes != identity.dependency_lock_hashes
            or evidence.artifacts != candidate.artifacts
            or provenance is None
            or provenance.decision != "fresh"
            or provenance.reuse_identity_hash != identity_hash
        ):
            return ReuseVerificationResult(False, "source_result_identity_mismatch")
    except FileNotFoundError:
        return ReuseVerificationResult(False, "source_evidence_missing")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return ReuseVerificationResult(False, "source_result_invalid")
    except RuntimeError:
        return ReuseVerificationResult(False, "source_result_unstable")

    total = 0
    try:
        for record in candidate.artifacts:
            if record.retention_expires_at != candidate.retention_expires_at:
                return ReuseVerificationResult(False, "source_retention_mismatch")
            path = _safe_path(store.run_directory, record.relative_path)
            before = _assert_regular_contained(path, store.run_directory)
            if before.st_size != record.size_bytes:
                return ReuseVerificationResult(False, "source_artifact_size_mismatch")
            if before.st_size > limits.maximum_artifact_bytes:
                return ReuseVerificationResult(False, "source_artifact_oversized")
            total += before.st_size
            if total > limits.maximum_total_bytes:
                return ReuseVerificationResult(False, "source_artifacts_oversized")
            digest = _sha256(path)
            after = _assert_regular_contained(path, store.run_directory)
            if (
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                return ReuseVerificationResult(False, "source_artifact_unstable")
            if digest != record.sha256:
                return ReuseVerificationResult(False, "source_artifact_hash_mismatch")
        store.verify_ownership()
    except FileNotFoundError:
        return ReuseVerificationResult(False, "source_evidence_pruned")
    except (OSError, ValueError, RuntimeError):
        return ReuseVerificationResult(False, "source_artifact_unsafe")
    return ReuseVerificationResult(True, "exact_evidence_verified")


def _assert_tree_has_no_reparse(path: Path) -> None:
    for item in (path, *path.rglob("*")):
        if _is_reparse(os.lstat(item)):
            raise RuntimeError("refusing to prune evidence containing a reparse point")


def prune_expired_evidence(
    evidence_root: Path, *, worker_id: str, now: dt.datetime
) -> PruneResult:
    """Remove only expired marker-verified direct descendants owned by this worker."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("retention prune time must be timezone-aware")
    root = _absolute(evidence_root)
    if not root.exists():
        return PruneResult((), ())
    _assert_no_reparse_ancestry(root)
    removed: list[int] = []
    failures: list[str] = []
    for candidate in sorted(root.iterdir(), key=lambda item: item.name):
        try:
            metadata = os.lstat(candidate)
            if _is_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError("candidate is not a regular directory")
            if (
                candidate == root
                or candidate.parent != root
                or not _contains(candidate, root)
            ):
                raise RuntimeError("candidate is not a contained direct descendant")
            marker_path = candidate / _MARKER_NAME
            marker_metadata = os.lstat(marker_path)
            if _is_reparse(marker_metadata) or not stat.S_ISREG(
                marker_metadata.st_mode
            ):
                raise RuntimeError("candidate marker is not a regular file")
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if not isinstance(marker, dict) or set(marker) != {
                "created_at",
                "retention_expires_at",
                "run_id",
                "schema_version",
                "worker_id",
            }:
                raise RuntimeError("candidate marker shape is invalid")
            run_id = marker["run_id"]
            if (
                marker["schema_version"] != _MARKER_SCHEMA_VERSION
                or marker["worker_id"] != worker_id
                or not isinstance(run_id, int)
                or isinstance(run_id, bool)
                or run_id < 1
                or candidate.name != f"run-{run_id}"
            ):
                raise RuntimeError("candidate marker ownership is invalid")
            expires = dt.datetime.fromisoformat(
                str(marker["retention_expires_at"]).replace("Z", "+00:00")
            )
            if expires.tzinfo is None or expires > now.astimezone(dt.UTC):
                continue
            _assert_tree_has_no_reparse(candidate)
            shutil.rmtree(candidate)
            removed.append(run_id)
        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            RuntimeError,
        ) as error:
            failures.append(f"{candidate.name}:{type(error).__name__}")
    return PruneResult(tuple(removed), tuple(failures))


__all__ = [
    "EvidenceLimits",
    "EvidenceStore",
    "PruneResult",
    "ReuseVerificationResult",
    "create_evidence_store",
    "hash_declared_file",
    "prune_expired_evidence",
    "verify_reuse_candidate",
]
