"""Data-only CF2-H0 source transport and closed runtime helpers.

The privileged host preparer accepts only two inert files from the operator:
an exact Git-object transport produced by this module and the pinned PyYAML
wheel.  No caller checkout, Git config, hooks, index, ignored files, or
credential material crosses the privilege boundary.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import csv
import errno
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import struct
import sys
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    from ops.executive_os.capacity_source_contract import (
        PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        PYYAML_RECORD_SHA256,
        PRODUCER_COMMIT,
        PRODUCER_MATERIAL_PATHS,
        PRODUCER_MATERIAL_SOURCE_DIGEST,
        PRODUCER_REPOSITORY,
        PRIOR_GENERATION_ARTIFACT_SHA256,
        PRIOR_GENERATION_DIGEST,
        RUNTIME_TREE_SHA256,
        SOURCE_REPAIR_INTENT_SCHEMA,
        SOURCE_REPAIR_RECEIPT_SCHEMA,
        SourceClosureEvidence,
        build_component_objects_v2,
        build_host_receipt_v2,
        build_source_config_v2,
        canonical_digest as source_contract_digest,
        validate_component_objects_v2,
        validate_host_receipt_v2,
        validate_source_config_v2,
        validate_source_repair_intent,
        validate_source_repair_receipt,
        validate_source_closure_evidence,
    )
except ModuleNotFoundError:  # pragma: no cover - direct Apple Python execution
    from capacity_source_contract import (  # type: ignore[no-redef]
        PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        PYYAML_RECORD_SHA256,
        PRODUCER_COMMIT,
        PRODUCER_MATERIAL_PATHS,
        PRODUCER_MATERIAL_SOURCE_DIGEST,
        PRODUCER_REPOSITORY,
        PRIOR_GENERATION_ARTIFACT_SHA256,
        PRIOR_GENERATION_DIGEST,
        RUNTIME_TREE_SHA256,
        SOURCE_REPAIR_INTENT_SCHEMA,
        SOURCE_REPAIR_RECEIPT_SCHEMA,
        SourceClosureEvidence,
        build_component_objects_v2,
        build_host_receipt_v2,
        build_source_config_v2,
        canonical_digest as source_contract_digest,
        validate_component_objects_v2,
        validate_host_receipt_v2,
        validate_source_config_v2,
        validate_source_repair_intent,
        validate_source_repair_receipt,
        validate_source_closure_evidence,
    )


TRANSPORT_SCHEMA = "mastermind.capacity_source_transport/v1"
TRANSPORT_SCHEMA_V2 = "mastermind.capacity_source_transport/v2"
RECOVERY_INTENT_SCHEMA = "mastermind.executive_capacity_h0_recovery_intent/v1"
RECOVERY_RECEIPT_SCHEMA = "mastermind.executive_capacity_h0_recovery/v1"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_ACCOUNT_RE = re.compile(r"^[a-z_][a-z0-9._-]{0,63}$")
_LAUNCHD_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MATERIAL_MODES = frozenset({"100644", "100755"})
_TRANSPORT_MEMBERS = frozenset({"manifest.json", "payload.pack"})
_WHEEL_PREFIXES = ("yaml/", "_yaml/", "pyyaml-6.0.3.dist-info/")
_APPROVED_SYSTEM_XATTRS = frozenset({b"com.apple.provenance"})
_APPROVED_TRAVERSAL_ANCESTOR_XATTRS = _APPROVED_SYSTEM_XATTRS | frozenset(
    {b"com.apple.rootless"}
)
_CLOSED_DIRECTORY_MODES = frozenset({0o555, 0o700})
_CLOSED_FILE_MODES = frozenset({0o400, 0o444, 0o500, 0o555})
_DARWIN_XATTR_LIST_MAX_BYTES = 64 * 1024
_DARWIN_XATTR_ERANGE_RETRIES = 3
_V2_MANIFEST_MAX_BYTES = 1024 * 1024
_V2_PACK_TYPES = frozenset({"commit", "tree", "blob", "tag"})
_V2_CONFIG = (
    b"[core]\n"
    b"\trepositoryformatversion = 0\n"
    b"\tfilemode = true\n"
    b"\tbare = false\n"
    b"\tlogallrefupdates = true\n"
    b"\thooksPath = /dev/null\n"
    b"\tfsmonitor = false\n"
    b"[extensions]\n"
    b"\tworktreeConfig = true\n"
    b"[pack]\n"
    b"\twriteReverseIndex = false\n"
)
_V2_WORKTREE_CONFIG = (
    b"[core]\n"
    b"\tsparseCheckout = true\n"
    b"\tsparseCheckoutCone = false\n"
)
_V2_SPARSE_CHECKOUT = b"".join(
    f"/{path}\n".encode("utf-8") for path in PRODUCER_MATERIAL_PATHS
)
_V2_ZIP32_ERROR = "TRANSPORT_V2_ZIP32_LIMIT_EXCEEDED"
_SOURCE_REPAIR_INTENT_NAME = "source-repair-intent.json"
_SOURCE_REPAIR_RECEIPT_NAME = "source-repair-receipt.json"
_ARCHIVED_SOURCE_NAME = "archived-source"
_ARCHIVED_GENERATION_NAME = "archived-generation"
_ALLOWED_BSD_FLAGS = 0
_TRAVERSAL_ANCESTOR_ALLOWED_FLAGS = (
    int(getattr(stat, "SF_NOUNLINK", 0x00100000))
    | int(getattr(stat, "SF_RESTRICTED", 0x00080000))
    | int(getattr(stat, "UF_HIDDEN", 0x00008000))
    if sys.platform == "darwin"
    else 0
)
_RELEASE_MANIFEST_SCHEMA = "mastermind.executive_release_manifest/v1"
_RELEASE_MANIFEST_NAME = ".executive-release-manifest.json"
_TRUSTED_E4_RELEASE_TREE = "ee1b95af3341a49151890cec1a6a31997f632aec"
_TRUSTED_E4_MANIFEST_SHA256 = (
    "ecb9a58eec12890126c291a451921ab0dd738baee765c61aae3a42fd74a31fc9"
)
_TRUSTED_E4_MANIFEST_SIZE = 190196
_TRUSTED_E4_MANIFEST_ENTRY_COUNT = 1122
_REPAIR_CARRIER_FILES = {
    ".repair-carrier-commit": 0o400,
    "ops/executive_os/repair-capacity-source-closure.sh": 0o500,
    "ops/executive_os/capacity_host_artifacts.py": 0o400,
    "ops/executive_os/capacity_source_contract.py": 0o400,
}


class CapacityHostArtifactError(ValueError):
    """Closed refusal for malformed or unsafe H0 artifacts."""


class SourceRepairIncomplete(RuntimeError):
    """The semantic commit may be visible and needs same-carrier reconciliation."""


class SourceRepairTransitionError(CapacityHostArtifactError):
    """The executable transition authority refused the observed position."""


class RenameDurability(str, Enum):
    """Typed outcome for one exclusive rename and both parent barriers."""

    RENAME_NOT_PERFORMED = "rename_not_performed"
    RENAME_VISIBLE_DURABLE = "rename_visible_durable"
    RENAME_VISIBLE_PARENT_DURABILITY_UNCERTAIN = (
        "rename_visible_parent_durability_uncertain"
    )


class SourceRepairRenameDurabilityUncertain(SourceRepairIncomplete):
    """An exclusive rename is visible but one parent barrier is uncertain."""

    outcome = RenameDurability.RENAME_VISIBLE_PARENT_DURABILITY_UNCERTAIN


class SourceRepairPhase(str, Enum):
    """Every unique durable position owned by the one repair intent."""

    INTENT_PREFIX = "intent_prefix"
    INTENT_DURABLE = "intent_durable"
    SOURCE_ARCHIVED = "source_archived"
    SOURCE_INSTALLED = "source_installed"
    GENERATION_ARCHIVED = "generation_archived"
    RECEIPT_PREFIX = "receipt_prefix"
    RECEIPT_DURABLE = "receipt_durable"
    GENERATION_PREFIX = "generation_prefix"
    COMMITTED = "committed"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_GENERATION_RESTORED = "rollback_generation_restored"
    ROLLED_BACK = "rolled_back"


class SourceRepairFailureLayout(str, Enum):
    """Exact semantic inventory below the intent-bound failure namespace."""

    NONE = "none"
    EMPTY = "empty"
    INSTALLED_SOURCE = "installed_source"
    STAGED_SOURCE = "staged_source"


class SourceRepairMode(str, Enum):
    REPAIR = "repair"
    VERIFY_ONLY = "verify-only"
    RECOVERY = "recovery"


class SourceRepairAction(str, Enum):
    PUBLISH_INTENT = "publish_intent"
    ADVANCE_SOURCE = "advance_source"
    ADVANCE_GENERATION = "advance_generation"
    ADVANCE_RECEIPT = "advance_receipt"
    COMMIT_GENERATION = "commit_generation"
    VERIFY_COMMITTED = "verify_committed"
    RECOVER_PRECOMMIT = "recover_precommit"
    REFUSE_ROLLED_BACK = "refuse_rolled_back"
    REFUSE_UNKNOWN = "refuse_unknown"


@dataclass(frozen=True)
class SourceRepairTransition:
    """One executable action and the complete durable states it may produce."""

    action: SourceRepairAction
    permitted_next_states: frozenset[
        tuple[SourceRepairPhase, SourceRepairFailureLayout]
    ]


def _source_repair_transition(
    action: SourceRepairAction,
    *next_states: tuple[SourceRepairPhase, SourceRepairFailureLayout],
) -> SourceRepairTransition:
    return SourceRepairTransition(action, frozenset(next_states))


_FORWARD_FAILURE_LAYOUT = SourceRepairFailureLayout.NONE
_ROLLBACK_NEXT_STATES = tuple(
    (phase, layout)
    for phase in (
        SourceRepairPhase.ROLLBACK_STARTED,
        SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
        SourceRepairPhase.ROLLED_BACK,
    )
    for layout in (
        SourceRepairFailureLayout.EMPTY,
        SourceRepairFailureLayout.INSTALLED_SOURCE,
        SourceRepairFailureLayout.STAGED_SOURCE,
    )
)
SOURCE_REPAIR_TRANSITIONS: Mapping[
    tuple[SourceRepairMode, SourceRepairPhase, SourceRepairFailureLayout],
    SourceRepairTransition,
] = {
    (SourceRepairMode.REPAIR, SourceRepairPhase.INTENT_PREFIX, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.PUBLISH_INTENT, (SourceRepairPhase.INTENT_DURABLE, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.INTENT_DURABLE, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.ADVANCE_SOURCE, (SourceRepairPhase.SOURCE_INSTALLED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.SOURCE_ARCHIVED, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.ADVANCE_SOURCE, (SourceRepairPhase.SOURCE_INSTALLED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.SOURCE_INSTALLED, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.ADVANCE_GENERATION, (SourceRepairPhase.GENERATION_ARCHIVED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.GENERATION_ARCHIVED, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.ADVANCE_RECEIPT, (SourceRepairPhase.RECEIPT_DURABLE, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.RECEIPT_PREFIX, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.ADVANCE_RECEIPT, (SourceRepairPhase.RECEIPT_DURABLE, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.RECEIPT_DURABLE, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.COMMIT_GENERATION, (SourceRepairPhase.GENERATION_PREFIX, _FORWARD_FAILURE_LAYOUT), (SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.GENERATION_PREFIX, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.COMMIT_GENERATION, (SourceRepairPhase.GENERATION_PREFIX, _FORWARD_FAILURE_LAYOUT), (SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.REPAIR, SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.VERIFY_COMMITTED, (SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.VERIFY_ONLY, SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.VERIFY_COMMITTED, (SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT)),
    (SourceRepairMode.RECOVERY, SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.VERIFY_COMMITTED, (SourceRepairPhase.COMMITTED, _FORWARD_FAILURE_LAYOUT)),
    **{
        (SourceRepairMode.RECOVERY, phase, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(
            SourceRepairAction.RECOVER_PRECOMMIT, *_ROLLBACK_NEXT_STATES
        )
        for phase in SourceRepairPhase
        if phase not in {
            SourceRepairPhase.COMMITTED,
            SourceRepairPhase.ROLLBACK_STARTED,
            SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
            SourceRepairPhase.ROLLED_BACK,
        }
    },
    **{
        (SourceRepairMode.VERIFY_ONLY, phase, _FORWARD_FAILURE_LAYOUT): _source_repair_transition(SourceRepairAction.REFUSE_UNKNOWN)
        for phase in SourceRepairPhase
        if phase not in {
            SourceRepairPhase.COMMITTED,
            SourceRepairPhase.ROLLBACK_STARTED,
            SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
            SourceRepairPhase.ROLLED_BACK,
        }
    },
    **{
        (mode, phase, layout): _source_repair_transition(
            SourceRepairAction.RECOVER_PRECOMMIT,
            *_ROLLBACK_NEXT_STATES,
        )
            if mode in {SourceRepairMode.REPAIR, SourceRepairMode.RECOVERY}
            and not (
                phase is SourceRepairPhase.ROLLED_BACK
                and layout is not SourceRepairFailureLayout.EMPTY
            )
            else _source_repair_transition(
                SourceRepairAction.REFUSE_ROLLED_BACK
                if mode in {SourceRepairMode.REPAIR, SourceRepairMode.RECOVERY}
                else SourceRepairAction.REFUSE_UNKNOWN
            )
        for mode in SourceRepairMode
        for phase in (
            SourceRepairPhase.ROLLBACK_STARTED,
            SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
            SourceRepairPhase.ROLLED_BACK,
        )
        for layout in (
            SourceRepairFailureLayout.EMPTY,
            SourceRepairFailureLayout.INSTALLED_SOURCE,
            SourceRepairFailureLayout.STAGED_SOURCE,
        )
    },
}


@dataclass(frozen=True)
class ObjectInventoryRow:
    oid: str
    object_type: str
    size: int

    def encoded(self) -> bytes:
        return f"{self.oid} {self.object_type} {self.size}\n".encode("ascii")


@dataclass(frozen=True)
class SourceRepairPosition:
    """One uniquely reconciled position inside the intent-derived archive."""

    intent_id: str
    intent_digest: str
    archived_source: bool
    archived_generation: bool
    receipt_digest: str | None
    phase: SourceRepairPhase
    intent_candidate: bool = False
    receipt_candidate: bool = False
    failure_namespace: str | None = None
    failure_layout: SourceRepairFailureLayout = SourceRepairFailureLayout.NONE


@dataclass
class SourceRepairParents:
    """Retained no-follow descriptors for every fixed transition parent."""

    source_path: Path
    source: int
    generation_path: Path
    generation: int
    staging_path: Path
    staging: int
    archive_path: Path
    archive: int
    device: int
    intent_archive_path: Path | None = None
    intent_archive: int | None = None
    guard_descriptors: tuple[int, ...] = ()
    guard_names: tuple[str, ...] = ()
    system_root: int | None = None
    system_root_state: tuple[int, ...] | None = None
    system_root_parent: int | None = None
    system_root_name: str | None = None
    capacity_sources: int | None = None
    locks: int | None = None
    relations: tuple[tuple[int, str, int], ...] = ()
    security_states: tuple[tuple[int, tuple[int, ...]], ...] = ()
    ancestor_states: tuple[tuple[int, tuple[int, ...]], ...] = ()
    ancestor_xattr_states: tuple[tuple[int, frozenset[bytes]], ...] = ()
    ancestor_expected_uid: int = 0
    ancestor_expected_gid: int = 0

    def revalidate(self) -> None:
        """Refuse descriptor or pathname-relation drift across the operation."""

        try:
            for descriptor, expected in self.ancestor_states:
                info = os.fstat(descriptor)
                if _descriptor_ancestor_state(info) != expected:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
                _require_source_repair_ancestor(
                    descriptor,
                    info,
                    expected_uid=self.ancestor_expected_uid,
                    expected_gid=self.ancestor_expected_gid,
                    expected_device=self.device,
                    reason="SOURCE_REPAIR_PARENT_DRIFT",
                )
            for descriptor, expected in self.ancestor_xattr_states:
                if _descriptor_extended_attribute_names(descriptor) != expected:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
            if (
                self.system_root is not None
                and self.system_root_state is not None
                and self.system_root_parent is not None
                and self.system_root_name is not None
            ):
                root_info = os.fstat(self.system_root)
                if _descriptor_directory_state(root_info) != self.system_root_state:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
                _require_secure_descriptor(
                    self.system_root,
                    root_info,
                    reason="SOURCE_REPAIR_PARENT_DRIFT",
                )
                observed_root = os.stat(
                    self.system_root_name,
                    dir_fd=self.system_root_parent,
                    follow_symlinks=False,
                )
                if _descriptor_directory_state(observed_root) != self.system_root_state:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
            for descriptor, expected in self.security_states:
                info = os.fstat(descriptor)
                if _descriptor_security_state(info) != expected:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
                _require_secure_descriptor(
                    descriptor, info, reason="SOURCE_REPAIR_PARENT_DRIFT"
                )
            for parent, name, child in self.relations:
                observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if _descriptor_security_state(observed) != _descriptor_security_state(
                    os.fstat(child)
                ):
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
            for index in range(1, len(self.guard_descriptors)):
                observed = os.stat(
                    self.guard_names[index],
                    dir_fd=self.guard_descriptors[index - 1],
                    follow_symlinks=False,
                )
                if (
                    observed.st_nlink < 1
                    or _descriptor_ancestor_state(observed)
                    != _descriptor_ancestor_state(
                    os.fstat(self.guard_descriptors[index])
                    )
                ):
                    raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT")
        except CapacityHostArtifactError:
            raise
        except OSError as exc:
            raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_DRIFT") from exc

    def close(self) -> None:
        descriptors = [self.source, self.generation, self.staging, self.archive]
        if self.intent_archive is not None:
            descriptors.append(self.intent_archive)
        for descriptor in (
            self.locks,
            self.capacity_sources,
            self.system_root,
            *reversed(self.guard_descriptors),
        ):
            if descriptor is not None and descriptor not in descriptors:
                descriptors.append(descriptor)
        first_error: OSError | None = None
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapacityHostArtifactError("NON_CANONICAL_JSON") from exc


def parse_launchctl_disabled(output: str, label: str) -> dict[str, str]:
    """Normalize the two exact disabled spellings emitted by supported macOS hosts."""

    if _LAUNCHD_LABEL_RE.fullmatch(label) is None or len(output.encode("utf-8")) > 256 * 1024:
        raise CapacityHostArtifactError("LAUNCHCTL_DISABLED_STATE_INVALID")
    matches: list[str] = []
    for line in output.splitlines():
        match = re.fullmatch(r'\s*"([^"\r\n]+)"\s*=>\s*(\S+)\s*', line)
        if match is not None and match.group(1) == label:
            matches.append(match.group(2))
    if len(matches) != 1 or matches[0] not in {"true", "disabled"}:
        raise CapacityHostArtifactError("LAUNCHCTL_DISABLED_STATE_INVALID")
    return {
        "label": label,
        "normalized_state": "disabled",
        "observed_state": matches[0],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes_exclusive(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CapacityHostArtifactError("SHORT_WRITE")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_descriptor(descriptor: int, maximum_bytes: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    output = bytearray()
    while True:
        chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - len(output)))
        if not chunk:
            return bytes(output)
        output.extend(chunk)
        if len(output) > maximum_bytes:
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_TOO_LARGE")


def _validate_canonical_file(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    expected_uid: int,
) -> None:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or info.st_nlink != 1
        or info.st_uid != expected_uid
        or stat.S_IMODE(info.st_mode) != mode
        or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
        or _extended_attribute_names(path) - _APPROVED_SYSTEM_XATTRS
        or path.read_bytes() != payload
    ):
        raise CapacityHostArtifactError("CANONICAL_FILE_INVALID")


def _publish_resumable_canonical_file(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    expected_uid: int,
) -> None:
    """Publish through a resumable prefix candidate, then fsync its directory."""

    candidate = path.with_name(f".{path.name}.candidate")
    if path.exists() or path.is_symlink():
        if candidate.exists() or candidate.is_symlink():
            raise CapacityHostArtifactError("CANONICAL_PUBLICATION_AMBIGUOUS")
        _validate_canonical_file(path, payload, mode=mode, expected_uid=expected_uid)
        return
    candidate_mode = mode | stat.S_IWUSR
    if candidate.exists() or candidate.is_symlink():
        candidate_info = candidate.lstat()
        if (
            not stat.S_ISREG(candidate_info.st_mode)
            or candidate.is_symlink()
            or candidate_info.st_nlink != 1
            or candidate_info.st_uid != expected_uid
            or stat.S_IMODE(candidate_info.st_mode) not in {mode, candidate_mode}
            or int(getattr(candidate_info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _extended_attribute_names(candidate) - _APPROVED_SYSTEM_XATTRS
        ):
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_METADATA_INVALID")
        candidate.chmod(candidate_mode)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(candidate, flags, candidate_mode)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or stat.S_IMODE(info.st_mode) != candidate_mode
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
        ):
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_METADATA_INVALID")
        existing = _read_descriptor(descriptor, len(payload))
        if not payload.startswith(existing):
            raise CapacityHostArtifactError("CANONICAL_CANDIDATE_PREFIX_INVALID")
        os.lseek(descriptor, 0, os.SEEK_END)
        view = memoryview(payload)[len(existing):]
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CapacityHostArtifactError("SHORT_WRITE")
            view = view[written:]
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if path.exists() or path.is_symlink():
        raise CapacityHostArtifactError("CANONICAL_PUBLICATION_AMBIGUOUS")
    candidate.rename(path)
    _fsync_directory(path.parent)
    _validate_canonical_file(path, payload, mode=mode, expected_uid=expected_uid)


def _canonical_transport_bytes(manifest: Mapping[str, Any], payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, body in (
            ("manifest.json", canonical_json(manifest)),
            ("payload.pack", payload),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o400) << 16
            archive.writestr(info, body)
    return output.getvalue()


def copy_closed_input(
    source: Path,
    destination: Path,
    *,
    operator_uid: int,
    expected_sha256: str,
    maximum_bytes: int = 65 * 1024 * 1024,
) -> dict[str, Any]:
    """Copy one operator file through a no-follow descriptor and bind its bytes."""

    if (
        isinstance(operator_uid, bool)
        or operator_uid < 1
        or _DIGEST_RE.fullmatch(expected_sha256) is None
        or maximum_bytes < 1
    ):
        raise CapacityHostArtifactError("CLOSED_INPUT_ARGUMENT_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(source, flags)
    output_descriptor: int | None = None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != operator_uid
            or stat.S_IMODE(info.st_mode) & 0o022
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or info.st_size > maximum_bytes
        ):
            raise CapacityHostArtifactError("CLOSED_INPUT_METADATA_INVALID")
        output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        output_descriptor = os.open(destination, output_flags, 0o400)
        if os.geteuid() == 0:
            os.fchown(output_descriptor, 0, 0)
        os.fchmod(output_descriptor, 0o400)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum_bytes:
                raise CapacityHostArtifactError("CLOSED_INPUT_TOO_LARGE")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(output_descriptor, view)
                if written <= 0:
                    raise CapacityHostArtifactError("SHORT_WRITE")
                view = view[written:]
        os.fsync(output_descriptor)
        observed = digest.hexdigest()
        if observed != expected_sha256 or size != info.st_size:
            raise CapacityHostArtifactError("CLOSED_INPUT_DIGEST_MISMATCH")
        return {"sha256": observed, "size": size}
    except Exception:
        if output_descriptor is not None:
            os.close(output_descriptor)
            output_descriptor = None
        destination.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)
        if output_descriptor is not None:
            os.close(output_descriptor)


def _extended_attribute_names(path: Path) -> frozenset[bytes]:
    """Inspect one object without following links, using macOS xattr(1) as fallback."""

    listxattr = getattr(os, "listxattr", None)
    if listxattr is not None:
        return frozenset(os.fsencode(name) for name in listxattr(path, follow_symlinks=False))
    if sys.platform != "darwin":
        raise CapacityHostArtifactError("RECOVERY_XATTR_INSPECTION_UNAVAILABLE")
    arguments = ["/usr/bin/xattr"]
    if path.is_symlink():
        arguments.append("-s")
    arguments.append(os.fspath(path))
    completed = subprocess.run(
        arguments,
        capture_output=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
        timeout=5,
    )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("RECOVERY_XATTR_INSPECTION_FAILED")
    return frozenset(name for name in completed.stdout.splitlines() if name)


def _descriptor_extended_attribute_names(descriptor: int) -> frozenset[bytes]:
    if sys.platform != "darwin":
        listxattr = getattr(os, "listxattr", None)
        if listxattr is None:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_UNAVAILABLE")
        try:
            return frozenset(os.fsencode(name) for name in listxattr(descriptor))
        except (OSError, TypeError, ValueError) as exc:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_FAILED") from exc
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        flistxattr = libc.flistxattr
    except (AttributeError, OSError) as exc:
        raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_UNAVAILABLE") from exc
    flistxattr.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int,
    ]
    flistxattr.restype = ctypes.c_ssize_t
    for _attempt in range(_DARWIN_XATTR_ERANGE_RETRIES):
        ctypes.set_errno(0)
        required = flistxattr(descriptor, None, 0, 0)
        if required < 0:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_FAILED")
        if required == 0:
            return frozenset()
        if required > _DARWIN_XATTR_LIST_MAX_BYTES:
            raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_TOO_LARGE")
        buffer = ctypes.create_string_buffer(required)
        ctypes.set_errno(0)
        observed = flistxattr(descriptor, buffer, required, 0)
        if observed < 0:
            if ctypes.get_errno() == errno.ERANGE:
                continue
            raise CapacityHostArtifactError("CLOSURE_XATTR_INSPECTION_FAILED")
        raw = buffer.raw[:observed]
        if observed > required or not raw.endswith(b"\0"):
            raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_INVALID")
        names = raw[:-1].split(b"\0")
        if (
            any(not name or len(name) > 127 for name in names)
            or len(set(names)) != len(names)
        ):
            raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_INVALID")
        return frozenset(names)
    raise CapacityHostArtifactError("CLOSURE_XATTR_LIST_UNSTABLE")


def _descriptor_has_extended_acl(descriptor: int) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        acl_get_fd_np = libc.acl_get_fd_np
        acl_get_entry = libc.acl_get_entry
        acl_free = libc.acl_free
    except (AttributeError, OSError) as exc:
        raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_UNAVAILABLE") from exc
    acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
    acl_get_fd_np.restype = ctypes.c_void_p
    acl_get_entry.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    acl_get_entry.restype = ctypes.c_int
    acl_free.argtypes = [ctypes.c_void_p]
    acl_free.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = acl_get_fd_np(descriptor, 0x00000100)
    if not acl:
        if ctypes.get_errno() == errno.ENOENT:
            return False
        raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_UNAVAILABLE")
    try:
        entry = ctypes.c_void_p()
        result = acl_get_entry(acl, 0, ctypes.byref(entry))
        if result == 0:
            return True
        if result == 1:
            return False
        raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_FAILED")
    finally:
        if acl_free(acl) != 0:
            raise CapacityHostArtifactError("CLOSURE_ACL_INSPECTION_FAILED")


def _descriptor_sha256(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _descriptor_directory_names(descriptor: int) -> list[str]:
    try:
        with os.scandir(descriptor) as entries:
            names = [entry.name for entry in entries]
    except OSError as exc:
        raise CapacityHostArtifactError("CLOSURE_DIRECTORY_UNREADABLE") from exc
    try:
        ordered_names = sorted(names, key=lambda name: name.encode("utf-8", "strict"))
    except UnicodeEncodeError as exc:
        raise CapacityHostArtifactError("CLOSURE_PATH_INVALID") from exc
    if any(name in {"", ".", ".."} or "/" in name for name in ordered_names):
        raise CapacityHostArtifactError("CLOSURE_PATH_INVALID")
    return ordered_names


def _descriptor_directory_state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_nlink,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        int(getattr(info, "st_flags", 0)),
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _descriptor_ancestor_state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        int(getattr(info, "st_flags", 0)),
    )


def _descriptor_regular_file_state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        int(getattr(info, "st_flags", 0)),
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _require_allowed_bsd_flags(
    info: os.stat_result, reason: str = "CLOSURE_FLAGS_INVALID"
) -> None:
    if int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS:
        raise CapacityHostArtifactError(reason)


def _descriptor_security_state(info: os.stat_result) -> tuple[int, ...]:
    """Identity and security metadata that a transition cannot legitimately alter."""

    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        int(getattr(info, "st_flags", 0)),
    )


def _require_secure_descriptor(
    descriptor: int,
    info: os.stat_result,
    *,
    reason: str,
    approved_xattrs: frozenset[bytes] = _APPROVED_SYSTEM_XATTRS,
) -> None:
    _require_allowed_bsd_flags(info, reason)
    if (
        _descriptor_extended_attribute_names(descriptor) - approved_xattrs
        or _descriptor_has_extended_acl(descriptor)
    ):
        raise CapacityHostArtifactError(reason)


def _require_source_repair_ancestor(
    descriptor: int,
    info: os.stat_result,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_device: int,
    reason: str,
) -> None:
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_nlink < 1
        or info.st_dev != expected_device
        or stat.S_IMODE(info.st_mode) & 0o022
        or int(getattr(info, "st_flags", 0))
        & ~_TRAVERSAL_ANCESTOR_ALLOWED_FLAGS
        or not (
            info.st_uid == 0
            or (info.st_uid == expected_uid and info.st_gid == expected_gid)
        )
    ):
        raise CapacityHostArtifactError(reason)
    if _descriptor_has_extended_acl(descriptor):
        raise CapacityHostArtifactError(reason)


def _source_repair_ancestor_xattrs(
    descriptor: int, *, reason: str
) -> frozenset[bytes]:
    observed = _descriptor_extended_attribute_names(descriptor)
    if observed - _APPROVED_TRAVERSAL_ANCESTOR_XATTRS:
        raise CapacityHostArtifactError(reason)
    return observed


def _descriptor_closed_tree_digest(
    root: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    approved_xattrs: frozenset[bytes] = frozenset({b"com.apple.provenance"}),
    root_mode_override: int | None = None,
    root_descriptor: int | None = None,
) -> str:
    """Hash one closed tree through no-follow descriptors and exact metadata rows."""

    if (
        isinstance(expected_uid, bool)
        or not isinstance(expected_uid, int)
        or expected_uid < 0
        or isinstance(expected_gid, bool)
        or not isinstance(expected_gid, int)
        or expected_gid < 0
        or not isinstance(approved_xattrs, frozenset)
        or any(not isinstance(name, bytes) for name in approved_xattrs)
        or not approved_xattrs.issubset(_APPROVED_SYSTEM_XATTRS)
    ):
        raise CapacityHostArtifactError("CLOSURE_ARGUMENT_INVALID")

    open_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    rows: list[dict[str, Any]] = []

    def visit(descriptor: int, relative: str) -> None:
        before = os.fstat(descriptor)
        _require_allowed_bsd_flags(before)
        if before.st_uid != expected_uid or before.st_gid != expected_gid:
            raise CapacityHostArtifactError("CLOSURE_OWNER_INVALID")
        if _descriptor_extended_attribute_names(descriptor) - approved_xattrs:
            raise CapacityHostArtifactError("CLOSURE_XATTR_INVALID")
        if _descriptor_has_extended_acl(descriptor):
            raise CapacityHostArtifactError("CLOSURE_ACL_INVALID")
        mode = stat.S_IMODE(before.st_mode)
        if stat.S_ISDIR(before.st_mode):
            if mode not in _CLOSED_DIRECTORY_MODES:
                raise CapacityHostArtifactError("CLOSURE_MODE_INVALID")
            row_mode = (
                root_mode_override
                if relative == "." and root_mode_override is not None
                else mode
            )
            rows.append(
                {
                    "path": relative,
                    "type": "directory",
                    "uid": before.st_uid,
                    "gid": before.st_gid,
                    "mode": f"{row_mode:04o}",
                    "nlink": before.st_nlink,
                    "flags": _ALLOWED_BSD_FLAGS,
                }
            )
            ordered_names = _descriptor_directory_names(descriptor)
            for name in ordered_names:
                child_relative = name if relative == "." else f"{relative}/{name}"
                try:
                    child_descriptor = os.open(
                        name, open_flags, dir_fd=descriptor
                    )
                except OSError as exc:
                    raise CapacityHostArtifactError("CLOSURE_TYPE_INVALID") from exc
                try:
                    visit(child_descriptor, child_relative)
                finally:
                    os.close(child_descriptor)
            after = os.fstat(descriptor)
            _require_allowed_bsd_flags(after)
            final_names = _descriptor_directory_names(descriptor)
            final = os.fstat(descriptor)
            if (
                _descriptor_directory_state(after)
                != _descriptor_directory_state(before)
                or final_names != ordered_names
                or _descriptor_directory_state(final)
                != _descriptor_directory_state(after)
            ):
                raise CapacityHostArtifactError("CLOSURE_DIRECTORY_DRIFT")
        elif stat.S_ISREG(before.st_mode):
            if before.st_nlink != 1:
                raise CapacityHostArtifactError("CLOSURE_LINK_INVALID")
            if mode not in _CLOSED_FILE_MODES:
                raise CapacityHostArtifactError("CLOSURE_MODE_INVALID")
            before_state = _descriptor_regular_file_state(before)
            digest = _descriptor_sha256(descriptor)
            after = os.fstat(descriptor)
            if _descriptor_regular_file_state(after) != before_state:
                raise CapacityHostArtifactError("CLOSURE_FILE_DRIFT")
            _require_secure_descriptor(
                descriptor,
                after,
                reason="CLOSURE_FILE_DRIFT",
                approved_xattrs=approved_xattrs,
            )
            rows.append(
                {
                    "path": relative,
                    "type": "file",
                    "uid": before.st_uid,
                    "gid": before.st_gid,
                    "mode": f"{mode:04o}",
                    "nlink": 1,
                    "flags": _ALLOWED_BSD_FLAGS,
                    "size": before.st_size,
                    "sha256": digest,
                }
            )
        else:
            raise CapacityHostArtifactError("CLOSURE_TYPE_INVALID")

    try:
        descriptor = (
            os.dup(root_descriptor)
            if root_descriptor is not None
            else os.open(root, open_flags)
        )
    except OSError as exc:
        raise CapacityHostArtifactError("CLOSURE_TYPE_INVALID") from exc
    try:
        visit(descriptor, ".")
    finally:
        os.close(descriptor)
    rows.sort(key=lambda row: row["path"].encode("utf-8"))
    return hashlib.sha256(canonical_json(rows)).hexdigest()


def closed_tree_digest(
    root: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    approved_xattrs: frozenset[bytes] = frozenset({b"com.apple.provenance"}),
    _root_descriptor: int | None = None,
) -> str:
    """Hash one closed tree through no-follow descriptors and exact metadata rows."""

    return _descriptor_closed_tree_digest(
        root,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        approved_xattrs=approved_xattrs,
        root_descriptor=_root_descriptor,
    )


def _old_generation_provenance() -> dict[str, Any]:
    return {
        "generation_digest": PRIOR_GENERATION_DIGEST,
        "preparer_source_commit": PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "topology_release_commit": PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "outcome": "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED",
        "generation_artifact_sha256": dict(PRIOR_GENERATION_ARTIFACT_SHA256),
    }


def build_source_repair_intent(**fixed_fields: Any) -> dict[str, Any]:
    """Build the sole canonical intent from caller-observed transition facts."""

    required = {
        "source_closure_repair_commit",
        "generation_repair_commit",
        "expected_uid",
        "expected_gid",
        "filesystem_device",
        "observed_old_source_tree_sha256",
        "candidate_transport_sha256",
        "candidate_transport_manifest_sha256",
        "candidate_object_count",
        "candidate_object_inventory_sha256",
        "candidate_source_tree_sha256",
    }
    if set(fixed_fields) != required:
        raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_ARGUMENTS_INVALID")
    identity: dict[str, Any] = {
        "schema_version": SOURCE_REPAIR_INTENT_SCHEMA,
        "operation": "side_by_side_non_promisor_rematerialization",
        "preparer_source_commit": PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "topology_release_commit": PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "source_closure_repair_commit": fixed_fields[
            "source_closure_repair_commit"
        ],
        "generation_repair_commit": fixed_fields["generation_repair_commit"],
        "source_release_commit": PRODUCER_COMMIT,
        "expected_uid": fixed_fields["expected_uid"],
        "expected_gid": fixed_fields["expected_gid"],
        "filesystem_device": fixed_fields["filesystem_device"],
        "producer_material_source_digest": PRODUCER_MATERIAL_SOURCE_DIGEST,
        "old_generation": _old_generation_provenance(),
        "observed_old_source_tree_sha256": fixed_fields[
            "observed_old_source_tree_sha256"
        ],
        "candidate_transport_sha256": fixed_fields["candidate_transport_sha256"],
        "candidate_transport_manifest_sha256": fixed_fields[
            "candidate_transport_manifest_sha256"
        ],
        "candidate_object_count": fixed_fields["candidate_object_count"],
        "candidate_object_inventory_sha256": fixed_fields[
            "candidate_object_inventory_sha256"
        ],
        "candidate_source_tree_sha256": fixed_fields[
            "candidate_source_tree_sha256"
        ],
        "service_state": "definitions_installed_labels_disabled_unloaded",
        "socket_state": "definitions_installed_nodes_absent",
        "credential_state": "not_read_copied_or_created",
        "worker_execution_state": "held",
        "cf2_i_state": "held",
    }
    value = {"intent_id": hashlib.sha256(canonical_json(identity)).hexdigest(), **identity}
    try:
        return validate_source_repair_intent(value)
    except ValueError as exc:
        raise CapacityHostArtifactError(str(exc)) from exc


def build_source_repair_receipt(**fixed_fields: Any) -> dict[str, Any]:
    """Build the forward-only receipt without a circular host-receipt edge."""

    required = {
        "intent",
        "archived_generation_tree_sha256",
        "new_source_config_digest",
        "new_component_manifest_digest",
    }
    if set(fixed_fields) != required:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RECEIPT_ARGUMENTS_INVALID")
    try:
        intent = validate_source_repair_intent(fixed_fields["intent"])
    except ValueError as exc:
        raise CapacityHostArtifactError(str(exc)) from exc
    value = {
        "schema_version": SOURCE_REPAIR_RECEIPT_SCHEMA,
        "outcome": "H0_SOURCE_CLOSURE_REPAIRED_NOT_P0_ACCEPTED",
        "intent_id": intent["intent_id"],
        "preparer_source_commit": PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "topology_release_commit": PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        "source_closure_repair_commit": intent["source_closure_repair_commit"],
        "generation_repair_commit": intent["generation_repair_commit"],
        "source_release_commit": PRODUCER_COMMIT,
        "expected_uid": intent["expected_uid"],
        "expected_gid": intent["expected_gid"],
        "filesystem_device": intent["filesystem_device"],
        "producer_material_source_digest": PRODUCER_MATERIAL_SOURCE_DIGEST,
        "prior_generation_digest": PRIOR_GENERATION_DIGEST,
        "archived_source_tree_sha256": intent["observed_old_source_tree_sha256"],
        "archived_generation_tree_sha256": fixed_fields[
            "archived_generation_tree_sha256"
        ],
        "installed_source_tree_sha256": intent["candidate_source_tree_sha256"],
        "installed_object_count": intent["candidate_object_count"],
        "installed_object_inventory_sha256": intent[
            "candidate_object_inventory_sha256"
        ],
        "new_source_config_digest": fixed_fields["new_source_config_digest"],
        "new_component_manifest_digest": fixed_fields[
            "new_component_manifest_digest"
        ],
        "service_state": "definitions_installed_labels_disabled_unloaded",
        "socket_state": "definitions_installed_nodes_absent",
        "credential_state": "not_read_copied_or_created",
        "worker_execution_state": "held",
        "cf2_i_state": "held",
    }
    try:
        return validate_source_repair_receipt(value, intent=intent)
    except ValueError as exc:
        raise CapacityHostArtifactError(str(exc)) from exc


def _open_source_repair_archive(
    archive: Path, *, expected_uid: int, expected_gid: int
) -> tuple[int, os.stat_result]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(archive, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_INVALID") from exc
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != 0o700
        or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
        or _descriptor_extended_attribute_names(descriptor) - _APPROVED_SYSTEM_XATTRS
        or _descriptor_has_extended_acl(descriptor)
    ):
        os.close(descriptor)
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_INVALID")
    return descriptor, info


def _read_source_repair_file(
    parent_descriptor: int,
    name: str,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_device: int,
    maximum_bytes: int = 1024 * 1024,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_FILE_INVALID") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or info.st_dev != expected_device
            or stat.S_IMODE(info.st_mode) != 0o400
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _descriptor_extended_attribute_names(descriptor)
            - _APPROVED_SYSTEM_XATTRS
            or _descriptor_has_extended_acl(descriptor)
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_FILE_INVALID")
        payload = _read_descriptor(descriptor, maximum_bytes)
        after = os.fstat(descriptor)
        if (
            after.st_dev != info.st_dev
            or after.st_ino != info.st_ino
            or after.st_size != info.st_size
            or after.st_mtime_ns != info.st_mtime_ns
            or after.st_ctime_ns != info.st_ctime_ns
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_FILE_DRIFT")
        return payload
    finally:
        os.close(descriptor)


def _read_source_repair_candidate_prefix(
    parent_descriptor: int,
    name: str,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_device: int,
    maximum_bytes: int = 1024 * 1024,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_INVALID") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or info.st_dev != expected_device
            or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _descriptor_extended_attribute_names(descriptor)
            - _APPROVED_SYSTEM_XATTRS
            or _descriptor_has_extended_acl(descriptor)
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_INVALID")
        return _read_descriptor(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)


def _rename_exclusive(
    source_parent: int,
    source_name: str,
    destination_parent: int,
    destination_name: str,
) -> None:
    """Descriptor-relative no-replace rename; never emulate with replace/copy/delete."""

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            rename = libc.renameatx_np
            flags = 0x00000004  # RENAME_EXCL
        else:
            rename = libc.renameat2
            flags = 0x00000001  # RENAME_NOREPLACE
    except (AttributeError, OSError) as exc:
        raise CapacityHostArtifactError("NO_REPLACE_RENAME_UNAVAILABLE") from exc
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    ctypes.set_errno(0)
    if rename(
        source_parent,
        os.fsencode(source_name),
        destination_parent,
        os.fsencode(destination_name),
        flags,
    ) != 0:
        observed_errno = ctypes.get_errno()
        if observed_errno == errno.EXDEV:
            reason = "SOURCE_REPAIR_DEVICE_MISMATCH"
        elif observed_errno in {errno.EEXIST, errno.ENOTEMPTY}:
            reason = "SOURCE_REPAIR_DESTINATION_EXISTS"
        else:
            reason = "SOURCE_REPAIR_RENAME_REFUSED"
        raise CapacityHostArtifactError(reason)


def _publish_source_repair_object(
    archive: Path,
    name: str,
    payload: bytes,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_device: int,
    publication_kind: str,
    crash_at: str | None = None,
    archive_descriptor: int | None = None,
) -> str:
    close_parent = archive_descriptor is None
    if archive_descriptor is None:
        parent, parent_info = _open_source_repair_archive(
            archive, expected_uid=expected_uid, expected_gid=expected_gid
        )
    else:
        parent = archive_descriptor
        parent_info = os.fstat(parent)
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != expected_uid
            or parent_info.st_gid != expected_gid
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_INVALID")
    candidate = f".{name}.candidate"
    try:
        if parent_info.st_dev != expected_device:
            raise CapacityHostArtifactError("SOURCE_REPAIR_DEVICE_MISMATCH")
        names = _descriptor_directory_names(parent)
        if name in names:
            if candidate in names:
                raise CapacityHostArtifactError("SOURCE_REPAIR_PUBLICATION_AMBIGUOUS")
            observed = _read_source_repair_file(
                parent,
                name,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_device=expected_device,
            )
            if observed != payload:
                raise CapacityHostArtifactError("SOURCE_REPAIR_PAYLOAD_MISMATCH")
            return hashlib.sha256(payload).hexdigest()
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        if candidate in names:
            inspect_flags = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            inspect_descriptor = os.open(candidate, inspect_flags, dir_fd=parent)
            try:
                candidate_info = os.fstat(inspect_descriptor)
                if (
                    not stat.S_ISREG(candidate_info.st_mode)
                    or candidate_info.st_nlink != 1
                    or candidate_info.st_uid != expected_uid
                    or candidate_info.st_gid != expected_gid
                    or candidate_info.st_dev != expected_device
                    or stat.S_IMODE(candidate_info.st_mode) not in {0o400, 0o600}
                    or int(getattr(candidate_info, "st_flags", 0))
                    != _ALLOWED_BSD_FLAGS
                ):
                    raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_INVALID")
                existing_prefix = _read_descriptor(inspect_descriptor, len(payload))
                if not payload.startswith(existing_prefix):
                    raise CapacityHostArtifactError(
                        "SOURCE_REPAIR_CANDIDATE_PREFIX_INVALID"
                    )
                os.fchmod(inspect_descriptor, 0o600)
            finally:
                os.close(inspect_descriptor)
        try:
            descriptor = os.open(candidate, flags, 0o600, dir_fd=parent)
        except OSError as exc:
            raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_INVALID") from exc
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != expected_uid
                or info.st_gid != expected_gid
                or info.st_dev != expected_device
                or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}
                or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_INVALID")
            if crash_at == f"after_candidate_create_{publication_kind}":
                raise SourceRepairIncomplete(crash_at)
            os.fchmod(descriptor, 0o600)
            existing = _read_descriptor(descriptor, len(payload))
            if not payload.startswith(existing):
                raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_PREFIX_INVALID")
            os.lseek(descriptor, 0, os.SEEK_END)
            view = memoryview(payload)[len(existing):]
            if (
                crash_at == f"after_candidate_partial_write_{publication_kind}"
                and view
            ):
                partial = max(1, len(view) // 2)
                written = os.write(descriptor, view[:partial])
                if written != partial:
                    raise CapacityHostArtifactError("SHORT_WRITE")
                raise SourceRepairIncomplete(crash_at)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise CapacityHostArtifactError("SHORT_WRITE")
                view = view[written:]
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
            if crash_at == f"after_candidate_file_fsync_{publication_kind}":
                raise SourceRepairIncomplete(crash_at)
        finally:
            os.close(descriptor)
        _rename_exclusive(parent, candidate, parent, name)
        if crash_at == f"after_candidate_rename_{publication_kind}":
            raise SourceRepairIncomplete(crash_at)
        if crash_at == f"before_parent_fsync_{publication_kind}":
            raise SourceRepairIncomplete(crash_at)
        try:
            os.fsync(parent)
        except OSError as exc:
            raise SourceRepairIncomplete(
                f"{publication_kind.upper()}_PARENT_DURABILITY_UNCERTAIN"
            ) from exc
        if crash_at == f"after_parent_fsync_{publication_kind}":
            raise SourceRepairIncomplete(crash_at)
        observed = _read_source_repair_file(
            parent,
            name,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_device=expected_device,
        )
        if observed != payload:
            raise CapacityHostArtifactError("SOURCE_REPAIR_PAYLOAD_MISMATCH")
        return hashlib.sha256(payload).hexdigest()
    finally:
        if close_parent:
            os.close(parent)


def publish_source_repair_intent(
    archive: Path,
    value: Mapping[str, Any],
    *,
    expected_uid: int,
    expected_gid: int,
    crash_at: str | None = None,
    archive_descriptor: int | None = None,
) -> str:
    try:
        intent = validate_source_repair_intent(value)
    except ValueError as exc:
        raise CapacityHostArtifactError(str(exc)) from exc
    if archive.name != f"source-closure-repair-{intent['intent_id']}":
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_ID_MISMATCH")
    return _publish_source_repair_object(
        archive,
        _SOURCE_REPAIR_INTENT_NAME,
        canonical_json(intent) + b"\n",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_device=intent["filesystem_device"],
        publication_kind="intent",
        crash_at=crash_at,
        archive_descriptor=archive_descriptor,
    )


def publish_source_repair_receipt(
    archive: Path,
    value: Mapping[str, Any],
    *,
    expected_uid: int,
    expected_gid: int,
    crash_at: str | None = None,
    archive_descriptor: int | None = None,
) -> str:
    position = reconcile_source_repair(
        archive,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_receipt=value,
    )
    parent, _ = _open_source_repair_archive(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    try:
        intent_bytes = _read_source_repair_file(
            parent,
            _SOURCE_REPAIR_INTENT_NAME,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_device=os.fstat(parent).st_dev,
        )
    finally:
        os.close(parent)
    intent = json.loads(intent_bytes)
    try:
        receipt = validate_source_repair_receipt(value, intent=intent)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CapacityHostArtifactError(str(exc)) from exc
    if position.receipt_digest is not None:
        expected = hashlib.sha256(canonical_json(receipt) + b"\n").hexdigest()
        if position.receipt_digest != expected:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RECEIPT_MISMATCH")
    return _publish_source_repair_object(
        archive,
        _SOURCE_REPAIR_RECEIPT_NAME,
        canonical_json(receipt) + b"\n",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_device=intent["filesystem_device"],
        publication_kind="receipt",
        crash_at=crash_at,
        archive_descriptor=archive_descriptor,
    )


def _validate_source_repair_failure_namespace(
    archive: Path,
    archive_descriptor: int,
    failure_name: str,
    *,
    intent: Mapping[str, Any],
    expected_uid: int,
    expected_gid: int,
) -> SourceRepairFailureLayout:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        failure_descriptor = os.open(
            failure_name, flags, dir_fd=archive_descriptor
        )
    except OSError as exc:
        raise CapacityHostArtifactError(
            "SOURCE_REPAIR_FAILURE_NAMESPACE_INVALID"
        ) from exc
    try:
        failure_info = os.fstat(failure_descriptor)
        if (
            not stat.S_ISDIR(failure_info.st_mode)
            or failure_info.st_uid != expected_uid
            or failure_info.st_gid != expected_gid
            or failure_info.st_dev != intent["filesystem_device"]
            or stat.S_IMODE(failure_info.st_mode) != 0o700
            or int(getattr(failure_info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _descriptor_extended_attribute_names(failure_descriptor)
            - _APPROVED_SYSTEM_XATTRS
            or _descriptor_has_extended_acl(failure_descriptor)
        ):
            raise CapacityHostArtifactError(
                "SOURCE_REPAIR_FAILURE_NAMESPACE_INVALID"
            )
        names = tuple(_descriptor_directory_names(failure_descriptor))
        layouts = {
            (): SourceRepairFailureLayout.EMPTY,
            ("installed-source",): SourceRepairFailureLayout.INSTALLED_SOURCE,
            ("staged-source",): SourceRepairFailureLayout.STAGED_SOURCE,
        }
        layout = layouts.get(names)
        if layout is None:
            raise CapacityHostArtifactError(
                "SOURCE_REPAIR_FAILURE_NAMESPACE_INVALID"
            )
        if layout is SourceRepairFailureLayout.EMPTY:
            return layout
        child_name = names[0]
        try:
            child_descriptor = os.open(
                child_name, flags, dir_fd=failure_descriptor
            )
        except OSError as exc:
            raise CapacityHostArtifactError(
                "SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID"
            ) from exc
        try:
            before = os.fstat(child_descriptor)
            expected_mode = 0o700 if expected_uid != 0 else 0o555
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != expected_uid
                or before.st_gid != expected_gid
                or before.st_dev != intent["filesystem_device"]
                or stat.S_IMODE(before.st_mode) != expected_mode
                or int(getattr(before, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
                or _descriptor_extended_attribute_names(child_descriptor)
                - _APPROVED_SYSTEM_XATTRS
                or _descriptor_has_extended_acl(child_descriptor)
            ):
                raise CapacityHostArtifactError(
                    "SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID"
                )
            child_path = archive / failure_name / child_name
            try:
                _manifest, evidence = _verify_installed_repair_source(
                    child_path,
                    PRODUCER_COMMIT,
                    parent_descriptor=failure_descriptor,
                )
            except (CapacityHostArtifactError, OSError) as exc:
                raise CapacityHostArtifactError(
                    "SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID"
                ) from exc
            observed_tree_digest = closed_tree_digest(
                child_path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            intent_bound_tree_digest = _descriptor_closed_tree_digest(
                child_path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                root_mode_override=0o555 if expected_uid != 0 else None,
            )
            after = os.fstat(child_descriptor)
            path_after = child_path.lstat()
            if (
                _descriptor_directory_state(after)
                != _descriptor_directory_state(before)
                or path_after.st_dev != before.st_dev
                or path_after.st_ino != before.st_ino
                or evidence.object_count != intent["candidate_object_count"]
                or evidence.object_inventory_sha256
                != intent["candidate_object_inventory_sha256"]
                or evidence.source_tree_sha256 != observed_tree_digest
                or intent_bound_tree_digest
                != intent["candidate_source_tree_sha256"]
            ):
                raise CapacityHostArtifactError(
                    "SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID"
                )
        finally:
            os.close(child_descriptor)
        final_failure_info = os.fstat(failure_descriptor)
        if (
            _descriptor_directory_state(final_failure_info)
            != _descriptor_directory_state(failure_info)
            or tuple(_descriptor_directory_names(failure_descriptor)) != names
        ):
            raise CapacityHostArtifactError(
                "SOURCE_REPAIR_FAILURE_NAMESPACE_INVALID"
            )
        return layout
    finally:
        os.close(failure_descriptor)


def reconcile_source_repair(
    archive: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_intent: Mapping[str, Any] | None = None,
    expected_receipt: Mapping[str, Any] | None = None,
) -> SourceRepairPosition:
    parent, parent_info = _open_source_repair_archive(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    try:
        names = set(_descriptor_directory_names(parent))
        intent_candidate_name = f".{_SOURCE_REPAIR_INTENT_NAME}.candidate"
        receipt_candidate_name = f".{_SOURCE_REPAIR_RECEIPT_NAME}.candidate"
        archive_intent_id = archive.name.removeprefix("source-closure-repair-")
        failure_name = f"failure-{archive_intent_id}"
        allowed = {
            _SOURCE_REPAIR_INTENT_NAME,
            intent_candidate_name,
            _ARCHIVED_SOURCE_NAME,
            _ARCHIVED_GENERATION_NAME,
            _SOURCE_REPAIR_RECEIPT_NAME,
            receipt_candidate_name,
            failure_name,
        }
        if (
            names - allowed
            or (_SOURCE_REPAIR_INTENT_NAME in names and intent_candidate_name in names)
            or (_SOURCE_REPAIR_RECEIPT_NAME in names and receipt_candidate_name in names)
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_INVENTORY_INVALID")
        if _SOURCE_REPAIR_INTENT_NAME not in names:
            if names != {intent_candidate_name} or expected_intent is None:
                raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INCOMPLETE")
            intent = validate_source_repair_intent(expected_intent)
            expected_payload = canonical_json(intent) + b"\n"
            observed_prefix = _read_source_repair_candidate_prefix(
                parent,
                intent_candidate_name,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_device=parent_info.st_dev,
            )
            if (
                not expected_payload.startswith(observed_prefix)
                or archive.name != f"source-closure-repair-{intent['intent_id']}"
                or parent_info.st_dev != intent["filesystem_device"]
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_PREFIX_INVALID")
            return SourceRepairPosition(
                intent_id=intent["intent_id"],
                intent_digest=hashlib.sha256(expected_payload).hexdigest(),
                archived_source=False,
                archived_generation=False,
                receipt_digest=None,
                phase=SourceRepairPhase.INTENT_PREFIX,
                intent_candidate=True,
            )
        intent_bytes = _read_source_repair_file(
            parent,
            _SOURCE_REPAIR_INTENT_NAME,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_device=parent_info.st_dev,
        )
        try:
            intent_raw = json.loads(intent_bytes)
            intent = validate_source_repair_intent(intent_raw)
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INVALID") from exc
        if (
            intent_bytes != canonical_json(intent) + b"\n"
            or archive.name != f"source-closure-repair-{intent['intent_id']}"
            or parent_info.st_dev != intent["filesystem_device"]
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INVALID")
        archived_source = _ARCHIVED_SOURCE_NAME in names
        archived_generation = _ARCHIVED_GENERATION_NAME in names
        if archived_generation and not archived_source:
            raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
        receipt_digest: str | None = None
        receipt_candidate = receipt_candidate_name in names
        if receipt_candidate:
            if not archived_source or not archived_generation:
                raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
            observed_prefix = _read_source_repair_candidate_prefix(
                parent,
                receipt_candidate_name,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_device=parent_info.st_dev,
            )
            if expected_receipt is not None:
                receipt_value = validate_source_repair_receipt(
                    expected_receipt, intent=intent
                )
                if not (canonical_json(receipt_value) + b"\n").startswith(
                    observed_prefix
                ):
                    raise CapacityHostArtifactError(
                        "SOURCE_REPAIR_CANDIDATE_PREFIX_INVALID"
                    )
        if _SOURCE_REPAIR_RECEIPT_NAME in names:
            if not archived_source or not archived_generation:
                raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
            receipt_bytes = _read_source_repair_file(
                parent,
                _SOURCE_REPAIR_RECEIPT_NAME,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_device=parent_info.st_dev,
            )
            try:
                receipt_raw = json.loads(receipt_bytes)
                receipt = validate_source_repair_receipt(receipt_raw, intent=intent)
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                raise CapacityHostArtifactError("SOURCE_REPAIR_RECEIPT_INVALID") from exc
            if receipt_bytes != canonical_json(receipt) + b"\n":
                raise CapacityHostArtifactError("SOURCE_REPAIR_RECEIPT_INVALID")
            receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
        if archived_source:
            digest = closed_tree_digest(
                archive / _ARCHIVED_SOURCE_NAME,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            if digest != intent["observed_old_source_tree_sha256"]:
                raise CapacityHostArtifactError("SOURCE_REPAIR_TREE_DIGEST_MISMATCH")
        if archived_generation:
            archived_generation_path = archive / _ARCHIVED_GENERATION_NAME
            _validate_prior_generation(
                archived_generation_path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            if receipt_digest is not None:
                digest = closed_tree_digest(
                    archived_generation_path,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                )
                if digest != receipt["archived_generation_tree_sha256"]:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_TREE_DIGEST_MISMATCH")
        failure_namespace: str | None = None
        failure_layout = SourceRepairFailureLayout.NONE
        if failure_name in names:
            failure_namespace = failure_name
            failure_layout = _validate_source_repair_failure_namespace(
                archive,
                parent,
                failure_name,
                intent=intent,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            if archived_generation and not archived_source:
                raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_POSITION_AMBIGUOUS")
            if archived_generation:
                phase = SourceRepairPhase.ROLLBACK_STARTED
            elif archived_source:
                phase = SourceRepairPhase.ROLLBACK_GENERATION_RESTORED
            else:
                phase = SourceRepairPhase.ROLLED_BACK
        elif receipt_candidate:
            phase = SourceRepairPhase.RECEIPT_PREFIX
        elif receipt_digest is not None:
            phase = SourceRepairPhase.RECEIPT_DURABLE
        elif archived_generation:
            phase = SourceRepairPhase.GENERATION_ARCHIVED
        elif archived_source:
            phase = SourceRepairPhase.SOURCE_ARCHIVED
        else:
            phase = SourceRepairPhase.INTENT_DURABLE
        return SourceRepairPosition(
            intent_id=intent["intent_id"],
            intent_digest=hashlib.sha256(intent_bytes).hexdigest(),
            archived_source=archived_source,
            archived_generation=archived_generation,
            receipt_digest=receipt_digest,
            phase=phase,
            receipt_candidate=receipt_candidate,
            failure_namespace=failure_namespace,
            failure_layout=failure_layout,
        )
    finally:
        os.close(parent)


def _classify_source_repair_position(
    *,
    archive_position: SourceRepairPosition,
    parents: SourceRepairParents,
    source_name: str,
    staged_source_name: str,
    generation_digest: str | None = None,
) -> SourceRepairPhase:
    """Pure structural classification; it performs no transition or durability work."""

    if archive_position.failure_namespace is not None:
        return archive_position.phase
    if archive_position.intent_candidate:
        return SourceRepairPhase.INTENT_PREFIX
    source_present = _descriptor_entry_info(parents.source, source_name) is not None
    staged_present = _descriptor_entry_info(parents.staging, staged_source_name) is not None
    if not archive_position.archived_source:
        if not source_present or not staged_present:
            raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
        return SourceRepairPhase.INTENT_DURABLE
    if not archive_position.archived_generation:
        if not source_present and staged_present:
            return SourceRepairPhase.SOURCE_ARCHIVED
        if source_present and not staged_present:
            return SourceRepairPhase.SOURCE_INSTALLED
        raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
    if not source_present or staged_present:
        raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
    if archive_position.receipt_candidate:
        return SourceRepairPhase.RECEIPT_PREFIX
    if archive_position.receipt_digest is None:
        return SourceRepairPhase.GENERATION_ARCHIVED
    if generation_digest is None:
        return SourceRepairPhase.RECEIPT_DURABLE
    hidden_present = _descriptor_entry_info(
        parents.generation, f".candidate-{generation_digest}"
    ) is not None
    visible_present = _descriptor_entry_info(
        parents.generation, generation_digest
    ) is not None
    if hidden_present and visible_present:
        raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
    if hidden_present:
        return SourceRepairPhase.GENERATION_PREFIX
    if visible_present:
        return SourceRepairPhase.COMMITTED
    return SourceRepairPhase.RECEIPT_DURABLE


def _source_repair_transition_for(
    mode: SourceRepairMode,
    phase: SourceRepairPhase,
    failure_layout: SourceRepairFailureLayout,
) -> SourceRepairTransition:
    key = (mode, phase, failure_layout)
    try:
        transition = SOURCE_REPAIR_TRANSITIONS[key]
    except KeyError as exc:
        raise SourceRepairTransitionError("SOURCE_REPAIR_TRANSITION_UNKNOWN") from exc
    if transition.action is SourceRepairAction.REFUSE_UNKNOWN:
        raise SourceRepairTransitionError("SOURCE_REPAIR_TRANSITION_REFUSED")
    return transition


def _source_repair_action(
    mode: SourceRepairMode,
    phase: SourceRepairPhase,
    failure_layout: SourceRepairFailureLayout,
) -> SourceRepairAction:
    return _source_repair_transition_for(mode, phase, failure_layout).action


def _require_permitted_next_state(
    transition: SourceRepairTransition,
    phase: SourceRepairPhase,
    failure_layout: SourceRepairFailureLayout,
) -> None:
    if (phase, failure_layout) not in transition.permitted_next_states:
        raise SourceRepairTransitionError("SOURCE_REPAIR_NEXT_STATE_REFUSED")


def _path_lexists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _open_source_repair_parents(
    system_root: Path, *, expected_uid: int, expected_gid: int
) -> SourceRepairParents:
    absolute = system_root.absolute()
    paths = {
        "source": absolute / "capacity-sources" / "macro",
        "generation": absolute / "capacity-generations",
        "staging": absolute / "capacity-staging",
        "archive": absolute / "capacity-archive",
    }
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptors: list[int] = []
    try:
        guard_descriptors = [os.open("/", directory_flags)]
        descriptors.extend(guard_descriptors)
        guard_names = ["/"]
        root_guard_info = os.fstat(guard_descriptors[0])
        ancestor_device = root_guard_info.st_dev
        _require_source_repair_ancestor(
            guard_descriptors[0],
            root_guard_info,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_device=ancestor_device,
            reason="SOURCE_REPAIR_PARENT_INVALID",
        )
        ancestor_states = [
            (guard_descriptors[0], _descriptor_ancestor_state(root_guard_info))
        ]
        ancestor_xattr_states = [
            (
                guard_descriptors[0],
                _source_repair_ancestor_xattrs(
                    guard_descriptors[0], reason="SOURCE_REPAIR_PARENT_INVALID"
                ),
            )
        ]
        for component in absolute.parent.parts[1:]:
            child = os.open(
                component, directory_flags, dir_fd=guard_descriptors[-1]
            )
            descriptors.append(child)
            guard_descriptors.append(child)
            guard_names.append(component)
            child_info = os.fstat(child)
            _require_source_repair_ancestor(
                child,
                child_info,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_device=ancestor_device,
                reason="SOURCE_REPAIR_PARENT_INVALID",
            )
            observed = os.stat(
                component,
                dir_fd=guard_descriptors[-2],
                follow_symlinks=False,
            )
            if (
                observed.st_nlink < 1
                or _descriptor_ancestor_state(observed)
                != _descriptor_ancestor_state(child_info)
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_INVALID")
            ancestor_states.append((child, _descriptor_ancestor_state(child_info)))
            ancestor_xattr_states.append(
                (
                    child,
                    _source_repair_ancestor_xattrs(
                        child, reason="SOURCE_REPAIR_PARENT_INVALID"
                    ),
                )
            )

        root_descriptor = os.open(
            absolute.name, directory_flags, dir_fd=guard_descriptors[-1]
        )
        descriptors.append(root_descriptor)
        root_info = os.fstat(root_descriptor)
        _require_source_repair_ancestor(
            root_descriptor,
            root_info,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_device=ancestor_device,
            reason="SOURCE_REPAIR_PARENT_INVALID",
        )
        _require_allowed_bsd_flags(root_info, "SOURCE_REPAIR_PARENT_INVALID")
        _require_secure_descriptor(
            root_descriptor,
            root_info,
            reason="SOURCE_REPAIR_PARENT_INVALID",
        )
        observed_root = os.stat(
            absolute.name,
            dir_fd=guard_descriptors[-1],
            follow_symlinks=False,
        )
        if _descriptor_ancestor_state(observed_root) != _descriptor_ancestor_state(
            root_info
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_INVALID")
        system_root_parent = guard_descriptors[-1]
        capacity_sources = os.open(
            "capacity-sources", directory_flags, dir_fd=root_descriptor
        )
        descriptors.append(capacity_sources)
        source_descriptor = os.open(
            "macro", directory_flags, dir_fd=capacity_sources
        )
        descriptors.append(source_descriptor)
        generation_descriptor = os.open(
            "capacity-generations", directory_flags, dir_fd=root_descriptor
        )
        descriptors.append(generation_descriptor)
        staging_descriptor = os.open(
            "capacity-staging", directory_flags, dir_fd=root_descriptor
        )
        descriptors.append(staging_descriptor)
        archive_descriptor = os.open(
            "capacity-archive", directory_flags, dir_fd=root_descriptor
        )
        descriptors.append(archive_descriptor)
        locks_descriptor = os.open("locks", directory_flags, dir_fd=root_descriptor)
        descriptors.append(locks_descriptor)

        secured = (
            (root_descriptor, 0o755),
            (capacity_sources, 0o755),
            (source_descriptor, 0o755),
            (generation_descriptor, 0o755),
            (staging_descriptor, 0o700),
            (archive_descriptor, 0o700),
            (locks_descriptor, 0o700),
        )
        for descriptor, expected_mode in secured:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != expected_uid
                or info.st_gid != expected_gid
                or stat.S_IMODE(info.st_mode) != expected_mode
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_INVALID")
            _require_secure_descriptor(
                descriptor, info, reason="SOURCE_REPAIR_PARENT_INVALID"
            )
        devices = {os.fstat(descriptor).st_dev for descriptor, _mode in secured}
        if len(devices) != 1:
            raise CapacityHostArtifactError("SOURCE_REPAIR_DEVICE_MISMATCH")
        parents = SourceRepairParents(
            source_path=paths["source"],
            source=source_descriptor,
            generation_path=paths["generation"],
            generation=generation_descriptor,
            staging_path=paths["staging"],
            staging=staging_descriptor,
            archive_path=paths["archive"],
            archive=archive_descriptor,
            device=next(iter(devices)),
            guard_descriptors=tuple(guard_descriptors),
            guard_names=tuple(guard_names),
            system_root=root_descriptor,
            system_root_state=_descriptor_directory_state(root_info),
            system_root_parent=system_root_parent,
            system_root_name=absolute.name,
            capacity_sources=capacity_sources,
            locks=locks_descriptor,
            relations=(
                (root_descriptor, "capacity-sources", capacity_sources),
                (capacity_sources, "macro", source_descriptor),
                (root_descriptor, "capacity-generations", generation_descriptor),
                (root_descriptor, "capacity-staging", staging_descriptor),
                (root_descriptor, "capacity-archive", archive_descriptor),
                (root_descriptor, "locks", locks_descriptor),
            ),
            security_states=tuple(
                (descriptor, _descriptor_security_state(os.fstat(descriptor)))
                for descriptor, _mode in secured
            ),
            ancestor_states=tuple(ancestor_states),
            ancestor_xattr_states=tuple(ancestor_xattr_states),
            ancestor_expected_uid=expected_uid,
            ancestor_expected_gid=expected_gid,
        )
        parents.revalidate()
        descriptors.clear()
        return parents
    except Exception:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                # An already-active open/validation error is authoritative.
                # Cleanup is best-effort across every descriptor and may not
                # mask that initial failure.
                pass
        raise


def _attach_source_repair_archive_parent(
    parents: SourceRepairParents,
    archive: Path,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    if archive.parent != parents.archive_path:
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_PARENT_INVALID")
    descriptor = os.open(
        archive.name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=parents.archive,
    )
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or info.st_dev != parents.device
            or stat.S_IMODE(info.st_mode) != 0o700
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _descriptor_extended_attribute_names(descriptor)
            - _APPROVED_SYSTEM_XATTRS
            or _descriptor_has_extended_acl(descriptor)
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_INVALID")
        if parents.intent_archive is not None:
            raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_ALREADY_ATTACHED")
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    parents.intent_archive_path = archive
    parents.intent_archive = descriptor


def _descriptor_entry_info(parent: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _require_descriptor_absent(parent: int, name: str) -> None:
    if _descriptor_entry_info(parent, name) is not None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_DESTINATION_EXISTS")


def _durable_source_repair_rename(
    *,
    source_parent: int,
    source_name: str,
    destination_parent: int,
    destination_name: str,
    move_name: str,
    crash_at: str | None,
) -> RenameDurability:
    if os.fstat(source_parent).st_dev != os.fstat(destination_parent).st_dev:
        raise CapacityHostArtifactError("SOURCE_REPAIR_DEVICE_MISMATCH")
    if _descriptor_entry_info(source_parent, source_name) is None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_SOURCE_ABSENT")
    _require_descriptor_absent(destination_parent, destination_name)
    _rename_exclusive(
        source_parent, source_name, destination_parent, destination_name
    )
    if crash_at == f"after_{move_name}_rename":
        raise SourceRepairRenameDurabilityUncertain(crash_at)
    try:
        if crash_at == f"fail_{move_name}_source_parent_fsync":
            raise OSError(errno.EIO, "injected source parent fsync failure")
        os.fsync(source_parent)
    except OSError as exc:
        raise SourceRepairRenameDurabilityUncertain(
            f"{move_name.upper()}_SOURCE_PARENT_DURABILITY_UNCERTAIN"
        ) from exc
    if crash_at == f"after_{move_name}_source_parent_fsync":
        raise SourceRepairRenameDurabilityUncertain(crash_at)
    try:
        if crash_at == f"fail_{move_name}_destination_parent_fsync":
            raise OSError(errno.EIO, "injected destination parent fsync failure")
        os.fsync(destination_parent)
    except OSError as exc:
        raise SourceRepairRenameDurabilityUncertain(
            f"{move_name.upper()}_DESTINATION_PARENT_DURABILITY_UNCERTAIN"
        ) from exc
    if crash_at == f"after_{move_name}_destination_parent_fsync":
        raise SourceRepairRenameDurabilityUncertain(crash_at)
    return RenameDurability.RENAME_VISIBLE_DURABLE


def _move_source_repair_tree(source: Path, destination: Path) -> None:
    source_parent = os.open(
        source.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    destination_parent = os.open(
        destination.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if os.fstat(source_parent).st_dev != os.fstat(destination_parent).st_dev:
            raise CapacityHostArtifactError("SOURCE_REPAIR_DEVICE_MISMATCH")
        _rename_exclusive(
            source_parent, source.name, destination_parent, destination.name
        )
        os.fsync(source_parent)
        if destination_parent != source_parent:
            os.fsync(destination_parent)
    finally:
        os.close(source_parent)
        os.close(destination_parent)


def _rename_final_generation(
    source: Path, destination: Path, *, parent_descriptor: int | None = None
) -> int:
    """Perform only the semantic commit rename and retain its parent descriptor."""

    if source.parent != destination.parent:
        raise CapacityHostArtifactError("SOURCE_REPAIR_GENERATION_PARENT_MISMATCH")
    owns_parent = parent_descriptor is None
    parent = (
        parent_descriptor
        if parent_descriptor is not None
        else os.open(
            source.parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    )
    try:
        _rename_exclusive(parent, source.name, parent, destination.name)
    except Exception:
        if owns_parent:
            os.close(parent)
        raise
    return parent


def _validate_prior_generation(
    path: Path, *, expected_uid: int, expected_gid: int
) -> str:
    if not path.is_dir() or path.is_symlink():
        raise CapacityHostArtifactError("PRIOR_GENERATION_INVALID")
    names = {item.name for item in path.iterdir()}
    if names != set(PRIOR_GENERATION_ARTIFACT_SHA256):
        raise CapacityHostArtifactError("PRIOR_GENERATION_INVALID")
    for name, digest in PRIOR_GENERATION_ARTIFACT_SHA256.items():
        candidate = path / name
        info = candidate.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or sha256_file(candidate) != digest
        ):
            raise CapacityHostArtifactError("PRIOR_GENERATION_INVALID")
    if sha256_file(path / "source-config.json") != PRIOR_GENERATION_DIGEST:
        raise CapacityHostArtifactError("PRIOR_GENERATION_INVALID")
    return closed_tree_digest(
        path, expected_uid=expected_uid, expected_gid=expected_gid
    )


def _load_complete_manifest(source_root: Path, expected_commit: str) -> dict[str, Any]:
    manifest_path = source_root / ".git" / "cf2-h0-transport-manifest.json"
    raw = json.loads(_read_small_nofollow(manifest_path, _V2_MANIFEST_MAX_BYTES))
    return validate_transport_manifest_v2(raw, expected_commit=expected_commit)


def _verify_installed_repair_source(
    source_root: Path,
    expected_commit: str,
    *,
    parent_descriptor: int | None = None,
) -> tuple[dict[str, Any], SourceClosureEvidence]:
    view = _RepositoryView(
        source_root,
        parent_descriptor=parent_descriptor,
        root_name=source_root.name,
    )
    try:
        descriptor = view.descriptors.get(".git/cf2-h0-transport-manifest.json")
        if descriptor is None:
            raise CapacityHostArtifactError("SOURCE_MANIFEST_MISMATCH")
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o444
        ):
            raise CapacityHostArtifactError("SOURCE_MANIFEST_MISMATCH")
        manifest = validate_transport_manifest_v2(
            json.loads(_read_descriptor(descriptor, _V2_MANIFEST_MAX_BYTES)),
            expected_commit=expected_commit,
        )
        evidence = verify_complete_repository(
            source_root, manifest, retained_view=view
        )
        view.revalidate()
        return manifest, evidence
    finally:
        view.close()


def _write_generation_payload(
    directory: Path,
    name: str,
    payload: bytes,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    target = directory / name
    if _path_lexists(target):
        info = target.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or stat.S_IMODE(info.st_mode) != 0o444
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or target.read_bytes() != payload
        ):
            raise CapacityHostArtifactError("GENERATION_CANDIDATE_INVALID")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o400)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CapacityHostArtifactError("SHORT_WRITE")
            view = view[written:]
        if os.geteuid() == 0:
            os.fchown(descriptor, expected_uid, expected_gid)
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _generation_values(
    *,
    evidence: SourceClosureEvidence,
    repair_commit: str,
    repair_receipt_digest: str,
    archived_generation: Path,
) -> tuple[str, dict[str, bytes]]:
    components = build_component_objects_v2(
        material_source_digest=PRODUCER_MATERIAL_SOURCE_DIGEST,
        pyyaml_record_sha256=PYYAML_RECORD_SHA256,
        runtime_tree_sha256=RUNTIME_TREE_SHA256,
        closure_evidence=evidence,
        source_closure_repair_commit=repair_commit,
    )
    source_config = build_source_config_v2(component_objects=components)
    preserved = {
        name: (archived_generation / name).read_bytes()
        for name in (
            "broker-topology.json",
            "rollback-contract.json",
            "rollback-drill-receipt.json",
        )
    }
    host_receipt = build_host_receipt_v2(
        source_config=source_config,
        component_objects=components,
        source_repair_receipt_digest=repair_receipt_digest,
        broker_topology_digest=hashlib.sha256(
            preserved["broker-topology.json"]
        ).hexdigest(),
        rollback_contract_digest=hashlib.sha256(
            preserved["rollback-contract.json"]
        ).hexdigest(),
        rollback_drill_receipt_digest=hashlib.sha256(
            preserved["rollback-drill-receipt.json"]
        ).hexdigest(),
    )
    digest = source_contract_digest(source_config)
    return digest, {
        "components.json": canonical_json(components),
        "source-config.json": canonical_json(source_config),
        "host-preparation-receipt.json": canonical_json(host_receipt),
        **preserved,
    }


def _verify_repaired_generation(
    generation: Path,
    *,
    expected_payloads: Mapping[str, bytes],
    expected_digest: str,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int = 0o555,
) -> None:
    info = generation.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or generation.is_symlink()
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != expected_mode
        or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
        or generation.name != expected_digest
        or {path.name for path in generation.iterdir()} != set(expected_payloads)
    ):
        raise CapacityHostArtifactError("REPAIRED_GENERATION_INVALID")
    for name, payload in expected_payloads.items():
        path = generation / name
        child = path.lstat()
        if (
            not stat.S_ISREG(child.st_mode)
            or child.st_nlink != 1
            or child.st_uid != expected_uid
            or child.st_gid != expected_gid
            or stat.S_IMODE(child.st_mode) != 0o444
            or int(getattr(child, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or path.read_bytes() != payload
        ):
            raise CapacityHostArtifactError("REPAIRED_GENERATION_INVALID")
    components = json.loads(expected_payloads["components.json"])
    config = json.loads(expected_payloads["source-config.json"])
    receipt = json.loads(expected_payloads["host-preparation-receipt.json"])
    validate_component_objects_v2(components)
    validate_source_config_v2(config, component_objects=components)
    validate_host_receipt_v2(receipt, source_config=config, component_objects=components)


def _build_repaired_generation_candidate(
    generation_root: Path,
    *,
    generation_parent_descriptor: int,
    generation_digest: str,
    payloads: Mapping[str, bytes],
    expected_uid: int,
    expected_gid: int,
    crash_at: str | None,
    test_adapter: bool,
) -> Path:
    hidden = generation_root / f".candidate-{generation_digest}"
    if _descriptor_entry_info(
        generation_parent_descriptor, hidden.name
    ) is None:
        os.mkdir(hidden.name, 0o700, dir_fd=generation_parent_descriptor)
        os.fsync(generation_parent_descriptor)
    info = hidden.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or hidden.is_symlink()
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) not in {0o700, 0o555}
        or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
    ):
        raise CapacityHostArtifactError("GENERATION_CANDIDATE_INVALID")
    if stat.S_IMODE(info.st_mode) == 0o700:
        for index, name in enumerate(sorted(payloads), start=1):
            _write_generation_payload(
                hidden,
                name,
                payloads[name],
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            if crash_at == f"after_generation_file_{index}_fsync":
                raise SourceRepairIncomplete(crash_at)
        _fsync_directory(hidden)
        if crash_at == "after_hidden_generation_directory_fsync":
            raise SourceRepairIncomplete(crash_at)
        hidden.chmod(0o700 if test_adapter else 0o555)
        _fsync_directory(hidden)
    _verify_repaired_generation(
        hidden,
        expected_payloads=payloads,
        expected_digest=f".candidate-{generation_digest}",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_mode=0o700 if test_adapter else 0o555,
    )
    return hidden


def _read_repair_intent_from_archive(
    archive: Path, *, expected_uid: int, expected_gid: int
) -> dict[str, Any]:
    parent, info = _open_source_repair_archive(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    try:
        payload = _read_source_repair_file(
            parent,
            _SOURCE_REPAIR_INTENT_NAME,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_device=info.st_dev,
        )
    finally:
        os.close(parent)
    try:
        value = json.loads(payload)
        intent = validate_source_repair_intent(value)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INVALID") from exc
    if payload != canonical_json(intent) + b"\n":
        raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INVALID")
    return intent


def _existing_repair_archive(
    archive_root: Path,
    *,
    repair_commit: str,
    transport_sha256: str | None,
    expected_uid: int,
    expected_gid: int,
) -> tuple[Path, dict[str, Any]] | None:
    candidates = [
        path
        for path in archive_root.iterdir()
        if path.name.startswith("source-closure-repair-")
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise CapacityHostArtifactError("SOURCE_REPAIR_MULTIPLE_INTENTS")
    intent = _read_repair_intent_from_archive(
        candidates[0], expected_uid=expected_uid, expected_gid=expected_gid
    )
    reconcile_source_repair(
        candidates[0], expected_uid=expected_uid, expected_gid=expected_gid
    )
    if (
        intent["source_closure_repair_commit"] != repair_commit
        or intent["generation_repair_commit"] != repair_commit
        or (
            transport_sha256 is not None
            and intent["candidate_transport_sha256"] != transport_sha256
        )
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_CARRIER_MISMATCH")
    return candidates[0], intent


def _source_repair_lock(
    lock_file: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    writable: bool,
    parent_descriptor: int | None = None,
) -> int:
    flags = (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(
            lock_file.name if parent_descriptor is not None else lock_file,
            flags,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_LOCK_INVALID") from exc
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != 0o600
        or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
        or _descriptor_extended_attribute_names(descriptor) - _APPROVED_SYSTEM_XATTRS
        or _descriptor_has_extended_acl(descriptor)
    ):
        os.close(descriptor)
        raise CapacityHostArtifactError("SOURCE_REPAIR_LOCK_INVALID")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(descriptor)
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            raise BlockingIOError("SOURCE_REPAIR_LOCK_HELD") from exc
        raise CapacityHostArtifactError("SOURCE_REPAIR_LOCK_INVALID") from exc
    return descriptor


def _resolve_source_repair_operator_uid(operator_user: str) -> int:
    completed = subprocess.run(
        ["/usr/bin/id", "-u", operator_user],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    try:
        output = completed.stdout.decode("ascii", "strict")
        value = int(output.removesuffix("\n"))
    except (UnicodeError, ValueError) as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_OPERATOR_INVALID") from exc
    if completed.returncode != 0 or output != f"{value}\n" or value <= 0:
        raise CapacityHostArtifactError("SOURCE_REPAIR_OPERATOR_INVALID")
    return value


def _read_directory_service_identity(
    record_kind: str, name: str, *, identity_field: str, expected: int
) -> None:
    completed = subprocess.run(
        [
            "/usr/bin/dscl",
            ".",
            "-read",
            f"/{record_kind}/{name}",
            identity_field,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    expected_line = f"{identity_field}: {expected}\n".encode("ascii")
    if completed.returncode != 0 or completed.stdout != expected_line:
        raise CapacityHostArtifactError("SOURCE_REPAIR_PRINCIPAL_INVALID")


def _verify_disabled_unloaded_label(label: str, disabled_output: str) -> None:
    parse_launchctl_disabled(disabled_output, label)
    completed = subprocess.run(
        ["/bin/launchctl", "print", f"system/{label}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    if completed.returncode == 0:
        raise CapacityHostArtifactError("SOURCE_REPAIR_SERVICE_STATE_INVALID")


def _release_object_state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        int(getattr(info, "st_flags", 0)),
        info.st_mtime_ns,
        info.st_ctime_ns,
        int(getattr(info, "st_birthtime_ns", 0)),
    )


def _open_release_symlink(parent: int, name: str) -> int:
    if sys.platform == "darwin":
        flags = os.O_RDONLY | 0x00200000  # O_SYMLINK
    else:
        flags = getattr(os, "O_PATH", os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    return os.open(name, flags, dir_fd=parent)


def _safe_release_link_target(relative: str, target: str) -> None:
    if not target or target.startswith("/") or "\x00" in target:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
    stack = list(PurePosixPath(relative).parent.parts)
    for part in PurePosixPath(target).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not stack:
                raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
            stack.pop()
        else:
            stack.append(part)


def _verify_inert_release_manifest(
    release: Path,
    *,
    expected_commit: str,
    expected_uid: int,
    expected_gid: int,
    parent_descriptor: int | None = None,
    retained_view: _RepositoryView | None = None,
) -> dict[str, Any]:
    """Verify an installed release strictly as inert descriptor-read data."""

    if (
        expected_commit != PRESERVED_TOPOLOGY_RELEASE_COMMIT
        or _COMMIT_RE.fullmatch(expected_commit) is None
        or release.name != expected_commit
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
    owns_view = retained_view is None
    view = retained_view
    try:
        if view is None:
            view = _RepositoryView(
                release,
                parent_descriptor=parent_descriptor,
                root_name=release.name,
                allow_symlinks=True,
            )
        elif (
            parent_descriptor is None
            or view.root_name != release.name
            or not view.allow_symlinks
            or _repository_snapshot_state(os.fstat(view.parent_descriptor))
            != _repository_snapshot_state(os.fstat(parent_descriptor))
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        root_before = os.fstat(view.root_descriptor)
        if (
            not stat.S_ISDIR(root_before.st_mode)
            or root_before.st_uid != expected_uid
            or root_before.st_gid != expected_gid
            or stat.S_IMODE(root_before.st_mode) != 0o755
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        _require_secure_descriptor(
            view.root_descriptor,
            root_before,
            reason="SOURCE_REPAIR_RELEASE_INVALID",
        )
        device = root_before.st_dev
        manifest_descriptor = view.descriptors.get(_RELEASE_MANIFEST_NAME)
        if manifest_descriptor is None:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        manifest_info = os.fstat(manifest_descriptor)
        if (
            not stat.S_ISREG(manifest_info.st_mode)
            or manifest_info.st_nlink != 1
            or manifest_info.st_dev != device
            or manifest_info.st_uid != expected_uid
            or manifest_info.st_gid != expected_gid
            or stat.S_IMODE(manifest_info.st_mode) != 0o444
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        _require_secure_descriptor(
            manifest_descriptor,
            manifest_info,
            reason="SOURCE_REPAIR_RELEASE_INVALID",
        )
        manifest_bytes = view.read_bytes(
            _RELEASE_MANIFEST_NAME,
            maximum_bytes=_TRUSTED_E4_MANIFEST_SIZE,
        )
        if (
            len(manifest_bytes) != _TRUSTED_E4_MANIFEST_SIZE
            or hashlib.sha256(manifest_bytes).hexdigest()
            != _TRUSTED_E4_MANIFEST_SHA256
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID") from exc
        if (
            not isinstance(manifest, Mapping)
            or set(manifest) != {"schema_version", "commit_sha", "tree_sha", "entries"}
            or manifest.get("schema_version") != _RELEASE_MANIFEST_SCHEMA
            or manifest.get("commit_sha") != expected_commit
            or manifest.get("tree_sha") != _TRUSTED_E4_RELEASE_TREE
            or not isinstance(manifest.get("entries"), list)
            or len(manifest["entries"]) != _TRUSTED_E4_MANIFEST_ENTRY_COUNT
            or manifest_bytes != canonical_json(manifest) + b"\n"
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")

        persisted_by_path: dict[str, Any] = {}
        for entry in manifest["entries"]:
            if not isinstance(entry, Mapping):
                raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
            path = entry.get("path")
            if (
                not isinstance(path, str)
                or not path
                or path in persisted_by_path
                or PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
            persisted_by_path[path] = dict(entry)

        observed_entries: list[dict[str, Any]] = []
        for relative, descriptor in view.descriptors.items():
            if relative in {".", _RELEASE_MANIFEST_NAME}:
                continue
            info = os.fstat(descriptor)
            if (
                info.st_dev != device
                or info.st_uid != expected_uid
                or info.st_gid != expected_gid
                or stat.S_IMODE(info.st_mode) & 0o022
                or (not stat.S_ISDIR(info.st_mode) and info.st_nlink != 1)
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
            _require_secure_descriptor(
                descriptor,
                info,
                reason="SOURCE_REPAIR_RELEASE_INVALID",
            )
            common = {
                "path": relative,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }
            if stat.S_ISDIR(info.st_mode):
                observed_entries.append({**common, "type": "directory"})
            elif stat.S_ISREG(info.st_mode):
                observed_entries.append(
                    {
                        **common,
                        "type": "file",
                        "size": info.st_size,
                        "sha256": view.sha256(relative),
                    }
                )
            elif stat.S_ISLNK(info.st_mode):
                target = view.readlink(relative)
                _safe_release_link_target(relative, target)
                observed_entries.append(
                    {**common, "type": "symlink", "target": target}
                )
            else:
                raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        observed_by_path = {entry["path"]: entry for entry in observed_entries}
        if persisted_by_path != observed_by_path:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID")
        view.revalidate()
        return dict(manifest)
    except (CapacityHostArtifactError, OSError) as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RELEASE_INVALID") from exc
    finally:
        if owns_view and view is not None:
            view.close()


@dataclass(frozen=True)
class _PreservedH0Views:
    """The one retained semantic evidence graph consumed by H0 verification."""

    runtime: "_RepositoryView"
    generation: "_RepositoryView"
    telemetry: "_RepositoryView"
    release: "_RepositoryView"
    rollback_archive: "_RepositoryView"
    topology: Mapping[Path, "_RepositoryView"]
    legacy: Mapping[Path, "_RepositoryView | None"]
    socket_parent: "_RepositoryView"
    socket_directory: "_RepositoryView | None"
    release_parent: "_RepositoryView | None" = None


def _verify_runtime_view(view: "_RepositoryView") -> None:
    """Authenticate the preserved runtime entirely through retained objects."""

    site_prefix = "lib/python3.12/site-packages/"
    record_relative = f"{site_prefix}pyyaml-6.0.3.dist-info/RECORD"
    record_descriptor = view.descriptors.get(record_relative)
    if record_descriptor is None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
    try:
        record_bytes = view.read_bytes(
            record_relative,
            maximum_bytes=os.fstat(record_descriptor).st_size,
        )
        rows = list(csv.reader(record_bytes.decode("utf-8").splitlines()))
    except (CapacityHostArtifactError, UnicodeError, csv.Error) as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID") from exc
    declared: dict[str, tuple[str, str]] = {}
    retained_hashes: dict[str, str] = {}

    def retained_sha256(relative: str) -> str:
        digest = retained_hashes.get(relative)
        if digest is None:
            digest = view.sha256(relative)
            retained_hashes[relative] = digest
        return digest

    for row in rows:
        if len(row) != 3 or row[0] in declared:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
        path = PurePosixPath(row[0])
        if (
            path.is_absolute()
            or ".." in path.parts
            or not any(row[0].startswith(prefix) for prefix in _WHEEL_PREFIXES)
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
        declared[row[0]] = (row[1], row[2])
    observed = {
        relative.removeprefix(site_prefix)
        for relative, descriptor in view.descriptors.items()
        if relative.startswith(site_prefix)
        and stat.S_ISREG(os.fstat(descriptor).st_mode)
    }
    if observed != set(declared):
        raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
    for relative, (encoded_hash, encoded_size) in declared.items():
        retained_relative = f"{site_prefix}{relative}"
        descriptor = view.descriptors.get(retained_relative)
        if descriptor is None:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
        if relative.endswith(".dist-info/RECORD") and not encoded_hash and not encoded_size:
            continue
        if not encoded_hash.startswith("sha256=") or not encoded_size.isdecimal():
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
        digest = base64.urlsafe_b64encode(
            bytes.fromhex(retained_sha256(retained_relative))
        ).rstrip(b"=").decode("ascii")
        if digest != encoded_hash.removeprefix("sha256=") or info.st_size != int(
            encoded_size
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
    forbidden = {f"{site_prefix}sitecustomize.py", f"{site_prefix}usercustomize.py"}
    if forbidden & set(view.descriptors) or any(
        relative.startswith(site_prefix) and relative.endswith(".pth")
        for relative in view.descriptors
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
    if retained_sha256(record_relative) != PYYAML_RECORD_SHA256:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")

    digest_rows: list[dict[str, Any]] = []
    for relative in sorted(view.descriptors, key=lambda value: value.encode("utf-8")):
        info = os.fstat(view.descriptors[relative])
        if stat.S_ISDIR(info.st_mode):
            digest_row: dict[str, Any] = {
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": info.st_nlink,
                "path": relative,
                "type": "directory",
            }
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            digest_row = {
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": 1,
                "path": relative,
                "sha256": retained_sha256(relative),
                "size": info.st_size,
                "type": "file",
            }
        else:
            raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
        digest_rows.append(digest_row)
    if hashlib.sha256(canonical_json(digest_rows)).hexdigest() != RUNTIME_TREE_SHA256:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RUNTIME_INVALID")
    view.revalidate()


def _verify_telemetry_view(view: "_RepositoryView") -> None:
    expected = {".", "data", "data/ai_costs", "data/metabolism"}
    if set(view.descriptors) != expected:
        raise CapacityHostArtifactError("SOURCE_REPAIR_TELEMETRY_INVALID")
    for relative in expected:
        info = os.fstat(view.descriptors[relative])
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o555
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_TELEMETRY_INVALID")
    view.revalidate()


def _verify_preserved_service_principal_state(labels: Sequence[str]) -> None:
    disabled = subprocess.run(
        ["/bin/launchctl", "print-disabled", "system"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    if disabled.returncode != 0:
        raise CapacityHostArtifactError("SOURCE_REPAIR_SERVICE_STATE_INVALID")
    disabled_text = disabled.stdout.decode("utf-8", "strict")
    for label in labels:
        _verify_disabled_unloaded_label(label, disabled_text)

    identities = (
        ("_mastermind_exec", 450, 450),
        ("_mastermind_codex_01", 454, 454),
        ("_mastermind_codex_02", 455, 455),
        ("_mastermind_codex_03", 456, 456),
    )
    for name, uid, gid in identities:
        _read_directory_service_identity(
            "Users", name, identity_field="UniqueID", expected=uid
        )
        _read_directory_service_identity(
            "Users", name, identity_field="PrimaryGroupID", expected=gid
        )
    for name, gid in (
        ("_mastermind_codex_01", 454),
        ("_mastermind_codex_02", 455),
        ("_mastermind_codex_03", 456),
    ):
        _read_directory_service_identity(
            "Groups", name, identity_field="PrimaryGroupID", expected=gid
        )
        membership = subprocess.run(
            ["/usr/bin/dsmemberutil", "checkmembership", "-U", name, "-G", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
        )
        if membership.returncode != 0 or membership.stdout != b"user is a member of the group\n":
            raise CapacityHostArtifactError("SOURCE_REPAIR_PRINCIPAL_INVALID")
        nonmembership = subprocess.run(
            [
                "/usr/sbin/dseditgroup",
                "-o",
                "checkmember",
                "-m",
                "_mastermind_exec",
                name,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=5,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
        )
        expected_nonmembership = (
            f"no _mastermind_exec is NOT a member of {name}\n".encode("ascii")
        )
        if nonmembership.returncode != 67 or nonmembership.stdout != expected_nonmembership:
            raise CapacityHostArtifactError("SOURCE_REPAIR_PRINCIPAL_INVALID")
    control_groups = subprocess.run(
        ["/usr/bin/id", "-G", "_mastermind_exec"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    try:
        control_gids = {int(value) for value in control_groups.stdout.split()}
    except ValueError as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_PRINCIPAL_INVALID") from exc
    if control_groups.returncode != 0 or control_gids & {454, 455, 456}:
        raise CapacityHostArtifactError("SOURCE_REPAIR_PRINCIPAL_INVALID")


def _verify_preserved_h0_invariants_body(
    system_root: Path,
    generation: Path,
    *,
    test_adapter: bool,
    parents: SourceRepairParents | None = None,
    retained_views: _PreservedH0Views | None = None,
) -> None:
    """Read only the fixed H0 roots and identity attributes; never provider homes."""

    if test_adapter:
        return
    if retained_views is None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_PRESERVED_EVIDENCE_INVALID")
    views = retained_views
    _verify_runtime_view(views.runtime)
    _verify_telemetry_view(views.telemetry)
    _verify_inert_release_manifest(
        system_root / "releases" / PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        expected_commit=PRESERVED_TOPOLOGY_RELEASE_COMMIT,
        expected_uid=0,
        expected_gid=0,
        parent_descriptor=(
            views.release_parent.root_descriptor
            if views.release_parent is not None
            else None
        ),
        retained_view=views.release,
    )

    try:
        topology = json.loads(
            views.generation.read_bytes(
                "broker-topology.json", maximum_bytes=1024 * 1024
            )
        )
        drill_bytes = views.generation.read_bytes(
            "rollback-drill-receipt.json", maximum_bytes=1024 * 1024
        )
        drill = json.loads(drill_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_PRESERVED_EVIDENCE_INVALID") from exc
    rows = topology.get("brokers")
    if not isinstance(rows, list) or len(rows) != 3:
        raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")
    if (
        drill.get("outcome") != "SHRINK_ONLY_ROLLBACK_PASS"
        or drill.get("moved_artifact_count") != 9
        or not isinstance(drill.get("artifacts"), list)
        or len(drill["artifacts"]) != 9
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_INVALID")
    drill_archive = Path(str(drill.get("archive_root")))
    if (
        drill_archive.parent != system_root / "capacity-archive"
        or not drill_archive.name.startswith("rollback-drill-")
        or views.rollback_archive.read_bytes(
            "rollback-receipt.json", maximum_bytes=1024 * 1024
        )
        != drill_bytes
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_INVALID")
    for artifact in drill["artifacts"]:
        if (
            not isinstance(artifact, Mapping)
            or set(artifact) != {"name", "sha256"}
            or "/" in str(artifact.get("name"))
            or _DIGEST_RE.fullmatch(str(artifact.get("sha256"))) is None
            or views.rollback_archive.sha256(str(artifact["name"]))
            != artifact["sha256"]
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_INVALID")
    observed_topology_paths: set[Path] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")
        for path_key, digest_key in (
            ("config_path", "config_sha256"),
            ("attestation_path", "attestation_sha256"),
            ("plist_path", "plist_sha256"),
        ):
            path = Path(str(row.get(path_key)))
            digest = str(row.get(digest_key))
            view = views.topology.get(path)
            if (
                not path.is_absolute()
                or path in observed_topology_paths
                or _DIGEST_RE.fullmatch(digest) is None
                or view is None
                or view.sha256(".") != digest
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")
            observed_topology_paths.add(path)
    if observed_topology_paths != set(views.topology):
        raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")

    labels = (
        "com.mastermind.executive.control",
        "com.mastermind.executive.worker.codex",
        "com.mastermind.executive.worker.codex-pro-01",
        "com.mastermind.executive.worker.codex-pro-02",
        "com.mastermind.executive.worker.codex-pro-03",
    )

    def legacy_view_digest(view: _RepositoryView | None) -> str:
        if view is None:
            return "absent"
        info = os.fstat(view.root_descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return "ambiguous"
        metadata = (
            f"{info.st_uid}:{info.st_gid}:{stat.S_IMODE(info.st_mode):o}:"
            f"{info.st_nlink}\n"
        ).encode("ascii")
        content_digest = f"{view.sha256('.')}\n".encode("ascii")
        return hashlib.sha256(metadata + content_digest).hexdigest()

    legacy_files = (
        system_root / "config" / "control.json",
        system_root / "config" / "worker-codex.json",
        Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist"),
        Path("/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"),
    )
    if set(views.legacy) != set(legacy_files):
        raise CapacityHostArtifactError("SOURCE_REPAIR_LEGACY_STATE_INVALID")
    legacy_lines = [
        f"{path}={legacy_view_digest(views.legacy[path])}\n" for path in legacy_files
    ]
    legacy_lines.extend(
        f"{label}:disabled=true:loaded=false\n" for label in labels[:2]
    )
    if hashlib.sha256("".join(legacy_lines).encode("utf-8")).hexdigest() != topology.get(
        "legacy_phase1c_state_digest"
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_LEGACY_STATE_INVALID")
    if views.socket_directory is None:
        if not views.socket_parent.is_absent("mastermind-executive"):
            raise CapacityHostArtifactError("SOURCE_REPAIR_SOCKET_STATE_INVALID")
    else:
        for slot_id in ("codex-pro-01", "codex-pro-02", "codex-pro-03"):
            if not views.socket_directory.is_absent(f"worker-{slot_id}.sock"):
                raise CapacityHostArtifactError("SOURCE_REPAIR_SOCKET_STATE_INVALID")

    for view in (
        views.runtime,
        views.generation,
        views.telemetry,
        views.release,
        views.rollback_archive,
        *views.topology.values(),
        *(view for view in views.legacy.values() if view is not None),
        views.socket_parent,
    ):
        view.revalidate()
    if views.release_parent is not None:
        views.release_parent.revalidate()
    if views.socket_directory is not None:
        views.socket_directory.revalidate()
    _verify_preserved_service_principal_state(labels)
    return


def _verify_preserved_h0_invariants(
    system_root: Path,
    generation: Path,
    *,
    test_adapter: bool,
    parents: SourceRepairParents | None = None,
) -> None:
    """Retain the complete preserved evidence graph around semantic verification."""

    if test_adapter:
        return
    if (
        parents is None
        or parents.system_root is None
        or parents.intent_archive is None
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_PARENT_INVALID")
    retained: list[_RepositoryView] = []

    def retain(view: _RepositoryView) -> _RepositoryView:
        retained.append(view)
        return view

    try:
        runtime_parent = retain(
            _RepositoryView(
                system_root / "capacity-runtimes",
                parent_descriptor=parents.system_root,
                root_name="capacity-runtimes",
                recursive=False,
            )
        )
        runtime = retain(
            _RepositoryView(
                system_root
                / "capacity-runtimes"
                / "cf1-pyyaml-6.0.3-cp312-arm64",
                parent_descriptor=runtime_parent.root_descriptor,
                root_name="cf1-pyyaml-6.0.3-cp312-arm64",
            )
        )
        generation_view = retain(
            _RepositoryView(
                generation,
                parent_descriptor=parents.intent_archive,
                root_name=generation.name,
            )
        )
        telemetry = retain(
            _RepositoryView(Path("/var/db/mastermind-provider-control"))
        )
        release_parent = retain(
            _RepositoryView(
                system_root / "releases",
                parent_descriptor=parents.system_root,
                root_name="releases",
                recursive=False,
            )
        )
        release = retain(
            _RepositoryView(
                system_root / "releases" / PRESERVED_TOPOLOGY_RELEASE_COMMIT,
                parent_descriptor=release_parent.root_descriptor,
                root_name=PRESERVED_TOPOLOGY_RELEASE_COMMIT,
                allow_symlinks=True,
            )
        )

        drill = json.loads(
            generation_view.read_bytes(
                "rollback-drill-receipt.json", maximum_bytes=1024 * 1024
            )
        )
        drill_archive = Path(str(drill.get("archive_root")))
        if (
            drill_archive.parent != parents.archive_path
            or not drill_archive.name.startswith("rollback-drill-")
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_INVALID")
        rollback_archive = retain(
            _RepositoryView(
                drill_archive,
                parent_descriptor=parents.archive,
                root_name=drill_archive.name,
            )
        )
        topology = json.loads(
            generation_view.read_bytes(
                "broker-topology.json", maximum_bytes=1024 * 1024
            )
        )
        rows = topology.get("brokers")
        if not isinstance(rows, list):
            raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")
        topology_views: dict[Path, _RepositoryView] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")
            for key in ("config_path", "attestation_path", "plist_path"):
                path = Path(str(row.get(key)))
                if not path.is_absolute() or path in topology_views:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_TOPOLOGY_INVALID")
                topology_views[path] = retain(_RepositoryView(path))

        config_parent = retain(
            _RepositoryView(
                system_root / "config",
                parent_descriptor=parents.system_root,
                root_name="config",
                recursive=False,
            )
        )
        launchd_parent = retain(
            _RepositoryView(Path("/Library/LaunchDaemons"), recursive=False)
        )
        legacy: dict[Path, _RepositoryView | None] = {}
        for parent_view, path in (
            (config_parent, system_root / "config" / "control.json"),
            (config_parent, system_root / "config" / "worker-codex.json"),
            (
                launchd_parent,
                Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist"),
            ),
            (
                launchd_parent,
                Path(
                    "/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist"
                ),
            ),
        ):
            if parent_view.contains(path.name):
                legacy[path] = retain(
                    _RepositoryView(
                        path,
                        parent_descriptor=parent_view.root_descriptor,
                        root_name=path.name,
                    )
                )
            elif parent_view.is_absent(path.name):
                legacy[path] = None
            else:  # pragma: no cover - contains/is_absent are exhaustive
                raise CapacityHostArtifactError("SOURCE_REPAIR_LEGACY_STATE_INVALID")

        socket_parent = retain(_RepositoryView(Path("/var/run"), recursive=False))
        socket_directory: _RepositoryView | None = None
        if socket_parent.contains("mastermind-executive"):
            socket_directory = retain(
                _RepositoryView(
                    Path("/var/run/mastermind-executive"),
                    parent_descriptor=socket_parent.root_descriptor,
                    root_name="mastermind-executive",
                    recursive=False,
                )
            )
        elif not socket_parent.is_absent("mastermind-executive"):
            raise CapacityHostArtifactError("SOURCE_REPAIR_SOCKET_STATE_INVALID")

        views = _PreservedH0Views(
            runtime=runtime,
            generation=generation_view,
            telemetry=telemetry,
            release=release,
            rollback_archive=rollback_archive,
            topology=topology_views,
            legacy=legacy,
            socket_parent=socket_parent,
            socket_directory=socket_directory,
            release_parent=release_parent,
        )
        parents.revalidate()
        _verify_preserved_h0_invariants_body(
            system_root,
            generation,
            test_adapter=False,
            parents=parents,
            retained_views=views,
        )
        parents.revalidate()
        for view in retained:
            view.revalidate()
        return
    except CapacityHostArtifactError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapacityHostArtifactError("SOURCE_REPAIR_PRESERVED_EVIDENCE_INVALID") from exc
    finally:
        for view in reversed(retained):
            view.close()


def _advance_source_repair_source_phase(
    *,
    parents: SourceRepairParents,
    archive: Path,
    source_root: Path,
    staged_source: Path,
    intent: Mapping[str, Any],
    expected_source_commit: str,
    expected_uid: int,
    expected_gid: int,
    test_adapter: bool,
    crash_at: str | None,
) -> SourceClosureEvidence:
    """Advance only INTENT_DURABLE through SOURCE_INSTALLED."""

    if parents.intent_archive is None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_NOT_ATTACHED")
    archived_source = archive / _ARCHIVED_SOURCE_NAME
    source_digest = (
        closed_tree_digest(
            source_root, expected_uid=expected_uid, expected_gid=expected_gid
        )
        if _path_lexists(source_root)
        else None
    )
    if source_digest == intent["observed_old_source_tree_sha256"]:
        if _path_lexists(archived_source):
            raise CapacityHostArtifactError("SOURCE_REPAIR_SOURCE_POSITION_INVALID")
        _durable_source_repair_rename(
            source_parent=parents.source,
            source_name=source_root.name,
            destination_parent=parents.intent_archive,
            destination_name=_ARCHIVED_SOURCE_NAME,
            move_name="old_source",
            crash_at=crash_at,
        )
        if crash_at == "after_old_source_move":
            raise SourceRepairIncomplete(crash_at)
        source_digest = None
    if source_digest is None:
        if not _path_lexists(staged_source):
            raise CapacityHostArtifactError("SOURCE_REPAIR_CANDIDATE_ABSENT")
        if test_adapter:
            staged_source.chmod(0o700)
        _durable_source_repair_rename(
            source_parent=parents.staging,
            source_name=staged_source.name,
            destination_parent=parents.source,
            destination_name=source_root.name,
            move_name="candidate_install",
            crash_at=crash_at,
        )
        if test_adapter:
            source_root.chmod(0o555)
        if crash_at == "after_candidate_install":
            raise SourceRepairIncomplete(crash_at)
    elif (
        _path_lexists(archived_source)
        and test_adapter
        and stat.S_IMODE(source_root.lstat().st_mode) != 0o555
    ):
        source_root.chmod(0o555)
    _manifest, evidence = _verify_installed_repair_source(
        source_root,
        expected_source_commit,
        parent_descriptor=parents.source,
    )
    if (
        evidence.source_tree_sha256 != intent["candidate_source_tree_sha256"]
        or evidence.object_count != intent["candidate_object_count"]
        or evidence.object_inventory_sha256
        != intent["candidate_object_inventory_sha256"]
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_SOURCE_DIGEST_MISMATCH")
    return evidence


def _advance_source_repair_generation_phase(
    *,
    system_root: Path,
    parents: SourceRepairParents,
    archive: Path,
    expected_uid: int,
    expected_gid: int,
    test_adapter: bool,
    crash_at: str | None,
) -> tuple[Path, str]:
    """Advance only SOURCE_INSTALLED through GENERATION_ARCHIVED."""

    if parents.intent_archive is None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_NOT_ATTACHED")
    archived_generation = archive / _ARCHIVED_GENERATION_NAME
    old_generation = parents.generation_path / PRIOR_GENERATION_DIGEST
    if _path_lexists(old_generation):
        if _path_lexists(archived_generation):
            raise CapacityHostArtifactError("SOURCE_REPAIR_GENERATION_POSITION_INVALID")
        _validate_prior_generation(
            old_generation,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        _durable_source_repair_rename(
            source_parent=parents.generation,
            source_name=old_generation.name,
            destination_parent=parents.intent_archive,
            destination_name=_ARCHIVED_GENERATION_NAME,
            move_name="old_generation",
            crash_at=crash_at,
        )
        if crash_at == "after_old_generation_move":
            raise SourceRepairIncomplete(crash_at)
    _validate_prior_generation(
        archived_generation,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    _verify_preserved_h0_invariants(
        system_root,
        archived_generation,
        test_adapter=test_adapter,
        parents=parents,
    )
    return archived_generation, closed_tree_digest(
        archived_generation, expected_uid=expected_uid, expected_gid=expected_gid
    )


def _advance_source_repair_receipt_phase(
    *,
    parents: SourceRepairParents,
    archive: Path,
    intent: Mapping[str, Any],
    evidence: SourceClosureEvidence,
    archived_generation_digest: str,
    expected_repair_commit: str,
    expected_uid: int,
    expected_gid: int,
    crash_at: str | None,
) -> str:
    """Advance only GENERATION_ARCHIVED through RECEIPT_DURABLE."""

    receipt = _expected_source_repair_receipt(
        intent=intent,
        evidence=evidence,
        archived_generation_digest=archived_generation_digest,
        expected_repair_commit=expected_repair_commit,
    )
    digest = publish_source_repair_receipt(
        archive,
        receipt,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        crash_at=crash_at,
        archive_descriptor=parents.intent_archive,
    )
    if crash_at == "after_repair_receipt_fsync":
        raise SourceRepairIncomplete(crash_at)
    return digest


def _expected_source_repair_receipt(
    *,
    intent: Mapping[str, Any],
    evidence: SourceClosureEvidence,
    archived_generation_digest: str,
    expected_repair_commit: str,
) -> dict[str, Any]:
    """Build the canonical receipt without publishing or mutating host state."""

    components = build_component_objects_v2(
        material_source_digest=PRODUCER_MATERIAL_SOURCE_DIGEST,
        pyyaml_record_sha256=PYYAML_RECORD_SHA256,
        runtime_tree_sha256=RUNTIME_TREE_SHA256,
        closure_evidence=evidence,
        source_closure_repair_commit=expected_repair_commit,
    )
    config = build_source_config_v2(component_objects=components)
    return build_source_repair_receipt(
        intent=intent,
        archived_generation_tree_sha256=archived_generation_digest,
        new_source_config_digest=source_contract_digest(config),
        new_component_manifest_digest=source_contract_digest(components),
    )


def _observe_source_repair_source(
    source_root: Path,
    *,
    intent: Mapping[str, Any],
    expected_source_commit: str,
    parent_descriptor: int | None = None,
) -> SourceClosureEvidence:
    """Read and bind the installed candidate to the durable intent."""

    _manifest, evidence = _verify_installed_repair_source(
        source_root,
        expected_source_commit,
        parent_descriptor=parent_descriptor,
    )
    if (
        evidence.source_tree_sha256 != intent["candidate_source_tree_sha256"]
        or evidence.object_count != intent["candidate_object_count"]
        or evidence.object_inventory_sha256
        != intent["candidate_object_inventory_sha256"]
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_SOURCE_DIGEST_MISMATCH")
    return evidence


def _observe_source_repair_archived_generation(
    *,
    system_root: Path,
    archive: Path,
    expected_uid: int,
    expected_gid: int,
    test_adapter: bool,
) -> tuple[Path, str]:
    """Read and validate the archived generation without advancing a phase."""

    archived_generation = archive / _ARCHIVED_GENERATION_NAME
    _validate_prior_generation(
        archived_generation,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    _verify_preserved_h0_invariants(
        system_root, archived_generation, test_adapter=test_adapter
    )
    return archived_generation, closed_tree_digest(
        archived_generation, expected_uid=expected_uid, expected_gid=expected_gid
    )


def _restore_digest_bound_precommit_state(
    *,
    archive: Path,
    source_root: Path,
    generation_root: Path,
    staged_source: Path,
    intent: Mapping[str, Any],
    expected_uid: int,
    expected_gid: int,
    test_adapter: bool,
    parents: SourceRepairParents,
    crash_at: str | None,
    transition: SourceRepairTransition,
) -> None:
    """Restore only a uniquely proven prior source/generation before commit."""

    archived_source = archive / _ARCHIVED_SOURCE_NAME
    archived_generation = archive / _ARCHIVED_GENERATION_NAME
    old_generation = generation_root / PRIOR_GENERATION_DIGEST
    intent_id = str(intent["intent_id"])
    failure_name = f"failure-{intent_id}"
    failure_namespace = archive / failure_name
    if parents.intent_archive is None:
        _attach_source_repair_archive_parent(
            parents,
            archive,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    if not _path_lexists(failure_namespace):
        initial_rollback_phase = (
            SourceRepairPhase.ROLLBACK_STARTED
            if _path_lexists(archived_generation)
            else (
                SourceRepairPhase.ROLLBACK_GENERATION_RESTORED
                if _path_lexists(archived_source)
                else SourceRepairPhase.ROLLED_BACK
            )
        )
        _require_permitted_next_state(
            transition,
            initial_rollback_phase,
            SourceRepairFailureLayout.EMPTY,
        )
        _require_descriptor_absent(parents.intent_archive, failure_name)
        os.mkdir(failure_name, 0o700, dir_fd=parents.intent_archive)
        try:
            os.fsync(parents.intent_archive)
        except OSError as exc:
            raise SourceRepairIncomplete(
                "FAILURE_NAMESPACE_PARENT_DURABILITY_UNCERTAIN"
            ) from exc
        if crash_at == "after_failure_namespace_parent_fsync":
            raise SourceRepairIncomplete(crash_at)
        created_position = reconcile_source_repair(
            archive, expected_uid=expected_uid, expected_gid=expected_gid
        )
        _require_permitted_next_state(
            transition, created_position.phase, created_position.failure_layout
        )
    failure_descriptor = os.open(
        failure_name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parents.intent_archive,
    )
    try:
        failure_info = os.fstat(failure_descriptor)
        if (
            failure_info.st_dev != parents.device
            or failure_info.st_uid != expected_uid
            or failure_info.st_gid != expected_gid
            or stat.S_IMODE(failure_info.st_mode) != 0o700
        ):
            raise CapacityHostArtifactError("SOURCE_REPAIR_FAILURE_NAMESPACE_INVALID")

        if _path_lexists(archived_source):
            if (
                closed_tree_digest(
                    archived_source,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                )
                != intent["observed_old_source_tree_sha256"]
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_DIGEST_MISMATCH")
            if _path_lexists(source_root) and _descriptor_entry_info(
                failure_descriptor, "installed-source"
            ) is None:
                _manifest, evidence = _verify_installed_repair_source(
                    source_root,
                    PRODUCER_COMMIT,
                    parent_descriptor=parents.source,
                )
                if evidence.source_tree_sha256 != intent["candidate_source_tree_sha256"]:
                    raise CapacityHostArtifactError(
                        "SOURCE_REPAIR_ROLLBACK_POSITION_AMBIGUOUS"
                    )
                _require_permitted_next_state(
                    transition,
                    SourceRepairPhase.ROLLBACK_STARTED,
                    SourceRepairFailureLayout.INSTALLED_SOURCE,
                )
                if test_adapter:
                    source_root.chmod(0o700)
                _durable_source_repair_rename(
                    source_parent=parents.source,
                    source_name=source_root.name,
                    destination_parent=failure_descriptor,
                    destination_name="installed-source",
                    move_name="rollback_installed",
                    crash_at=crash_at,
                )
                installed_position = reconcile_source_repair(
                    archive, expected_uid=expected_uid, expected_gid=expected_gid
                )
                _require_permitted_next_state(
                    transition,
                    installed_position.phase,
                    installed_position.failure_layout,
                )

        if _path_lexists(staged_source) and _descriptor_entry_info(
            failure_descriptor, "staged-source"
        ) is None:
            _manifest, evidence = _verify_installed_repair_source(
                staged_source,
                PRODUCER_COMMIT,
                parent_descriptor=parents.staging,
            )
            if evidence.source_tree_sha256 != intent["candidate_source_tree_sha256"]:
                raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_DIGEST_MISMATCH")
            _require_permitted_next_state(
                transition,
                SourceRepairPhase.ROLLBACK_STARTED,
                SourceRepairFailureLayout.STAGED_SOURCE,
            )
            if test_adapter:
                staged_source.chmod(0o700)
            _durable_source_repair_rename(
                source_parent=parents.staging,
                source_name=staged_source.name,
                destination_parent=failure_descriptor,
                destination_name="staged-source",
                move_name="rollback_staged",
                crash_at=crash_at,
            )
            staged_position = reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            _require_permitted_next_state(
                transition, staged_position.phase, staged_position.failure_layout
            )

        # Generation is restored before source so every durable rollback prefix
        # is structurally unique and replayable.
        if _path_lexists(archived_generation):
            _validate_prior_generation(
                archived_generation,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            if _path_lexists(old_generation):
                raise CapacityHostArtifactError(
                    "SOURCE_REPAIR_ROLLBACK_POSITION_AMBIGUOUS"
                )
            failure_layout = _validate_source_repair_failure_namespace(
                archive,
                parents.intent_archive,
                failure_name,
                intent=intent,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            _require_permitted_next_state(
                transition,
                SourceRepairPhase.ROLLBACK_GENERATION_RESTORED,
                failure_layout,
            )
            _durable_source_repair_rename(
                source_parent=parents.intent_archive,
                source_name=_ARCHIVED_GENERATION_NAME,
                destination_parent=parents.generation,
                destination_name=old_generation.name,
                move_name="rollback_generation",
                crash_at=crash_at,
            )
            generation_position = reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            _require_permitted_next_state(
                transition,
                generation_position.phase,
                generation_position.failure_layout,
            )

        if _path_lexists(archived_source):
            if _path_lexists(source_root):
                raise CapacityHostArtifactError(
                    "SOURCE_REPAIR_ROLLBACK_POSITION_AMBIGUOUS"
                )
            failure_layout = _validate_source_repair_failure_namespace(
                archive,
                parents.intent_archive,
                failure_name,
                intent=intent,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            _require_permitted_next_state(
                transition,
                SourceRepairPhase.ROLLED_BACK,
                failure_layout,
            )
            _durable_source_repair_rename(
                source_parent=parents.intent_archive,
                source_name=_ARCHIVED_SOURCE_NAME,
                destination_parent=parents.source,
                destination_name=source_root.name,
                move_name="rollback_source",
                crash_at=crash_at,
            )
            source_position = reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            _require_permitted_next_state(
                transition, source_position.phase, source_position.failure_layout
            )
    finally:
        os.close(failure_descriptor)

    restored_source = closed_tree_digest(
        source_root, expected_uid=expected_uid, expected_gid=expected_gid
    )
    if restored_source != intent["observed_old_source_tree_sha256"]:
        raise CapacityHostArtifactError("SOURCE_REPAIR_ROLLBACK_DIGEST_MISMATCH")
    _validate_prior_generation(
        old_generation, expected_uid=expected_uid, expected_gid=expected_gid
    )
    terminal_position = reconcile_source_repair(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    if (
        terminal_position.phase is not SourceRepairPhase.ROLLED_BACK
        or terminal_position.failure_layout
        not in {
            SourceRepairFailureLayout.INSTALLED_SOURCE,
            SourceRepairFailureLayout.STAGED_SOURCE,
        }
    ):
        raise CapacityHostArtifactError(
            "SOURCE_REPAIR_FAILURE_EVIDENCE_INVALID"
        )


def _verify_committed_source_repair(
    *,
    system_root: Path,
    parents: SourceRepairParents,
    expected_repair_commit: str,
    expected_source_commit: str,
    expected_uid: int,
    expected_gid: int,
    test_adapter: bool,
) -> str:
    """Structurally read-only verification of the one complete committed graph."""

    candidates = [
        path
        for path in parents.archive_path.iterdir()
        if path.name.startswith("source-closure-repair-")
    ]
    if len(candidates) != 1:
        raise CapacityHostArtifactError("SOURCE_REPAIR_COMMITTED_ARCHIVE_INVALID")
    archive = candidates[0]
    _attach_source_repair_archive_parent(
        parents,
        archive,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    position = reconcile_source_repair(
        archive,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    if (
        position.phase is not SourceRepairPhase.RECEIPT_DURABLE
        or not position.archived_source
        or not position.archived_generation
        or position.receipt_digest is None
        or position.intent_candidate
        or position.receipt_candidate
        or position.failure_namespace is not None
    ):
        _source_repair_action(
            SourceRepairMode.VERIFY_ONLY,
            position.phase,
            position.failure_layout,
        )
        raise CapacityHostArtifactError("SOURCE_REPAIR_COMMIT_INCOMPLETE")
    intent = _read_repair_intent_from_archive(
        archive, expected_uid=expected_uid, expected_gid=expected_gid
    )
    if (
        intent["source_closure_repair_commit"] != expected_repair_commit
        or intent["generation_repair_commit"] != expected_repair_commit
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_CARRIER_MISMATCH")

    source_root = parents.source_path / expected_source_commit
    _manifest, evidence = _verify_installed_repair_source(
        source_root,
        expected_source_commit,
        parent_descriptor=parents.source,
    )
    if (
        evidence.source_tree_sha256 != intent["candidate_source_tree_sha256"]
        or evidence.object_count != intent["candidate_object_count"]
        or evidence.object_inventory_sha256
        != intent["candidate_object_inventory_sha256"]
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_SOURCE_DIGEST_MISMATCH")
    archived_generation = archive / _ARCHIVED_GENERATION_NAME
    _validate_prior_generation(
        archived_generation,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    _verify_preserved_h0_invariants(
        system_root, archived_generation, test_adapter=test_adapter
    )
    components = build_component_objects_v2(
        material_source_digest=PRODUCER_MATERIAL_SOURCE_DIGEST,
        pyyaml_record_sha256=PYYAML_RECORD_SHA256,
        runtime_tree_sha256=RUNTIME_TREE_SHA256,
        closure_evidence=evidence,
        source_closure_repair_commit=expected_repair_commit,
    )
    config = build_source_config_v2(component_objects=components)
    expected_receipt = build_source_repair_receipt(
        intent=intent,
        archived_generation_tree_sha256=closed_tree_digest(
            archived_generation,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        ),
        new_source_config_digest=source_contract_digest(config),
        new_component_manifest_digest=source_contract_digest(components),
    )
    expected_receipt_digest = hashlib.sha256(
        canonical_json(expected_receipt) + b"\n"
    ).hexdigest()
    if position.receipt_digest != expected_receipt_digest:
        raise CapacityHostArtifactError("SOURCE_REPAIR_RECEIPT_MISMATCH")
    generation_digest, payloads = _generation_values(
        evidence=evidence,
        repair_commit=expected_repair_commit,
        repair_receipt_digest=expected_receipt_digest,
        archived_generation=archived_generation,
    )
    target_generation = parents.generation_path / generation_digest
    hidden_generation = f".candidate-{generation_digest}"
    if set(_descriptor_directory_names(parents.generation)) != {generation_digest}:
        raise CapacityHostArtifactError("SOURCE_REPAIR_COMMITTED_GENERATION_INVALID")
    if _descriptor_entry_info(parents.generation, hidden_generation) is not None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_COMMIT_INCOMPLETE")
    _verify_repaired_generation(
        target_generation,
        expected_payloads=payloads,
        expected_digest=generation_digest,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_mode=0o700 if test_adapter else 0o555,
    )
    if _descriptor_entry_info(parents.staging, f"source-candidate-{expected_repair_commit}") is not None:
        raise CapacityHostArtifactError("SOURCE_REPAIR_COMMIT_INCOMPLETE")
    if (
        _source_repair_action(
            SourceRepairMode.VERIFY_ONLY,
            SourceRepairPhase.COMMITTED,
            SourceRepairFailureLayout.NONE,
        )
        is not SourceRepairAction.VERIFY_COMMITTED
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_TRANSITION_REFUSED")
    return "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED"


def run_source_repair_host(
    *,
    mode: str,
    system_root: Path,
    lock_file: Path,
    expected_repair_commit: str,
    expected_source_commit: str,
    transport: Path | None,
    transport_sha256: str | None,
    operator_uid: int | None = None,
    operator_user: str | None = None,
    test_adapter: bool = False,
    crash_at: str | None = None,
) -> str:
    """Run one locked transition or one zero-write verification."""

    if (
        mode not in {"repair", "verify-only"}
        or _COMMIT_RE.fullmatch(expected_repair_commit) is None
        or _COMMIT_RE.fullmatch(expected_source_commit) is None
        or expected_source_commit != PRODUCER_COMMIT
        or (mode == "repair")
        != (transport is not None and transport_sha256 is not None)
        or (mode == "repair")
        != ((operator_uid is not None) ^ (operator_user is not None))
        or (operator_uid is not None and operator_uid <= 0)
        or (
            operator_user is not None
            and _LOCAL_ACCOUNT_RE.fullmatch(operator_user) is None
        )
        or (
            transport_sha256 is not None
            and _DIGEST_RE.fullmatch(transport_sha256) is None
        )
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_ARGUMENTS_INVALID")
    if test_adapter and (
        os.geteuid() == 0
        or system_root == Path("/Library/Application Support/MastermindExecutive")
    ):
        raise CapacityHostArtifactError("SOURCE_REPAIR_TEST_ADAPTER_INVALID")
    expected_uid = os.geteuid() if test_adapter else 0
    expected_gid = os.getegid() if test_adapter else 0
    lock_descriptor: int | None = None
    archive: Path | None = None
    intent: dict[str, Any] | None = None
    source_root: Path | None = None
    generation_root: Path | None = None
    staged_source: Path | None = None
    parents: SourceRepairParents | None = None
    semantic_commit_visible = False
    repair_effect_unknown = False
    authorized_precommit_recovery: tuple[
        SourceRepairPhase,
        SourceRepairFailureLayout,
        SourceRepairTransition,
    ] | None = None
    try:
        parents = _open_source_repair_parents(
            system_root, expected_uid=expected_uid, expected_gid=expected_gid
        )
        if lock_file.absolute() != (system_root.absolute() / "locks" / "cf2-h0.lock"):
            raise CapacityHostArtifactError("SOURCE_REPAIR_LOCK_INVALID")
        lock_descriptor = _source_repair_lock(
            lock_file,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            writable=mode == "repair",
            parent_descriptor=parents.locks,
        )
        parents.revalidate()
        if mode == "verify-only":
            outcome = _verify_committed_source_repair(
                system_root=system_root,
                parents=parents,
                expected_repair_commit=expected_repair_commit,
                expected_source_commit=expected_source_commit,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                test_adapter=test_adapter,
            )
            parents.revalidate()
            return outcome

        resolved_operator_uid = operator_uid
        if operator_user is not None:
            resolved_operator_uid = _resolve_source_repair_operator_uid(operator_user)
        source_parent = parents.source_path
        source_root = source_parent / expected_source_commit
        generation_root = parents.generation_path
        staging_root = parents.staging_path
        archive_root = parents.archive_path
        staged_transport = staging_root / f"source-transport-{expected_repair_commit}.zip"
        staged_source = staging_root / f"source-candidate-{expected_repair_commit}"
        raw_archives = [
            path
            for path in archive_root.iterdir()
            if path.name.startswith("source-closure-repair-")
        ]
        if len(raw_archives) > 1:
            raise CapacityHostArtifactError("SOURCE_REPAIR_MULTIPLE_INTENTS")
        if raw_archives and not (raw_archives[0] / _SOURCE_REPAIR_INTENT_NAME).exists():
            prefix_archive = raw_archives[0]
            if (
                transport_sha256 is None
                or not _path_lexists(staged_transport)
                or sha256_file(staged_transport) != transport_sha256
                or not _path_lexists(staged_source)
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INCOMPLETE")
            old_source_digest = closed_tree_digest(
                source_root, expected_uid=expected_uid, expected_gid=expected_gid
            )
            prior_generation_path = generation_root / PRIOR_GENERATION_DIGEST
            _validate_prior_generation(
                prior_generation_path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            manifest, evidence = _verify_installed_repair_source(
                staged_source,
                expected_source_commit,
                parent_descriptor=parents.staging,
            )
            prefix_intent = build_source_repair_intent(
                source_closure_repair_commit=expected_repair_commit,
                generation_repair_commit=expected_repair_commit,
                expected_uid=0,
                expected_gid=0,
                filesystem_device=parents.device,
                observed_old_source_tree_sha256=old_source_digest,
                candidate_transport_sha256=transport_sha256,
                candidate_transport_manifest_sha256=hashlib.sha256(
                    canonical_json(manifest)
                ).hexdigest(),
                candidate_object_count=evidence.object_count,
                candidate_object_inventory_sha256=evidence.object_inventory_sha256,
                candidate_source_tree_sha256=evidence.source_tree_sha256,
            )
            if prefix_archive.name != f"source-closure-repair-{prefix_intent['intent_id']}":
                raise CapacityHostArtifactError("SOURCE_REPAIR_ARCHIVE_ID_MISMATCH")
            _attach_source_repair_archive_parent(
                parents,
                prefix_archive,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            prefix_names = set(
                _descriptor_directory_names(parents.intent_archive)
            )
            intent_candidate_name = f".{_SOURCE_REPAIR_INTENT_NAME}.candidate"
            if prefix_names not in (set(), {intent_candidate_name}):
                raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_INCOMPLETE")
            if prefix_names:
                prefix_position = reconcile_source_repair(
                    prefix_archive,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    expected_intent=prefix_intent,
                )
                prefix_phase = prefix_position.phase
                prefix_layout = prefix_position.failure_layout
            else:
                prefix_phase = SourceRepairPhase.INTENT_PREFIX
                prefix_layout = SourceRepairFailureLayout.NONE
            prefix_transition = _source_repair_transition_for(
                SourceRepairMode.REPAIR,
                prefix_phase,
                prefix_layout,
            )
            if prefix_transition.action is not SourceRepairAction.PUBLISH_INTENT:
                raise CapacityHostArtifactError("SOURCE_REPAIR_TRANSITION_REFUSED")
            _require_permitted_next_state(
                prefix_transition,
                SourceRepairPhase.INTENT_DURABLE,
                SourceRepairFailureLayout.NONE,
            )
            publish_source_repair_intent(
                prefix_archive,
                prefix_intent,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                crash_at=crash_at,
                archive_descriptor=parents.intent_archive,
            )
            published_prefix = reconcile_source_repair(
                prefix_archive,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            _require_permitted_next_state(
                prefix_transition,
                published_prefix.phase,
                published_prefix.failure_layout,
            )
        existing = _existing_repair_archive(
            archive_root,
            repair_commit=expected_repair_commit,
            transport_sha256=transport_sha256,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        if existing is None:
            if mode != "repair" or transport is None or transport_sha256 is None:
                raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_ABSENT")
            old_source_digest = closed_tree_digest(
                source_root, expected_uid=expected_uid, expected_gid=expected_gid
            )
            prior_generation_path = generation_root / PRIOR_GENERATION_DIGEST
            _validate_prior_generation(
                prior_generation_path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            _verify_preserved_h0_invariants(
                system_root, prior_generation_path, test_adapter=test_adapter
            )
            if not _path_lexists(staged_transport):
                copy_closed_input(
                    transport,
                    staged_transport,
                    operator_uid=resolved_operator_uid,
                    expected_sha256=transport_sha256,
                    maximum_bytes=4 * 1024 * 1024 * 1024,
                )
                os.fsync(parents.staging)
            elif sha256_file(staged_transport) != transport_sha256:
                raise CapacityHostArtifactError("SOURCE_REPAIR_TRANSPORT_MISMATCH")
            if crash_at == "after_transport_fsync":
                raise SourceRepairIncomplete(crash_at)
            if not _path_lexists(staged_source):
                manifest = materialize_source_transport_v2(
                    staged_transport,
                    staged_source,
                    expected_commit=expected_source_commit,
                )
                os.fsync(parents.staging)
            else:
                manifest = _load_complete_manifest(staged_source, expected_source_commit)
            evidence = verify_complete_repository(staged_source, manifest)
            if crash_at == "after_candidate_verify":
                raise SourceRepairIncomplete(crash_at)
            intent = build_source_repair_intent(
                source_closure_repair_commit=expected_repair_commit,
                generation_repair_commit=expected_repair_commit,
                expected_uid=0,
                expected_gid=0,
                filesystem_device=parents.device,
                observed_old_source_tree_sha256=old_source_digest,
                candidate_transport_sha256=transport_sha256,
                candidate_transport_manifest_sha256=hashlib.sha256(
                    canonical_json(manifest)
                ).hexdigest(),
                candidate_object_count=evidence.object_count,
                candidate_object_inventory_sha256=evidence.object_inventory_sha256,
                candidate_source_tree_sha256=evidence.source_tree_sha256,
            )
            precommit_components = build_component_objects_v2(
                material_source_digest=PRODUCER_MATERIAL_SOURCE_DIGEST,
                pyyaml_record_sha256=PYYAML_RECORD_SHA256,
                runtime_tree_sha256=RUNTIME_TREE_SHA256,
                closure_evidence=evidence,
                source_closure_repair_commit=expected_repair_commit,
            )
            precommit_config = build_source_config_v2(
                component_objects=precommit_components
            )
            precommit_receipt = build_source_repair_receipt(
                intent=intent,
                archived_generation_tree_sha256=closed_tree_digest(
                    prior_generation_path,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                ),
                new_source_config_digest=source_contract_digest(precommit_config),
                new_component_manifest_digest=source_contract_digest(
                    precommit_components
                ),
            )
            precommit_generation_digest, _precommit_payloads = _generation_values(
                evidence=evidence,
                repair_commit=expected_repair_commit,
                repair_receipt_digest=hashlib.sha256(
                    canonical_json(precommit_receipt) + b"\n"
                ).hexdigest(),
                archived_generation=prior_generation_path,
            )
            _require_descriptor_absent(
                parents.generation, precommit_generation_digest
            )
            _require_descriptor_absent(
                parents.generation, f".candidate-{precommit_generation_digest}"
            )
            intent_transition = _source_repair_transition_for(
                SourceRepairMode.REPAIR,
                SourceRepairPhase.INTENT_PREFIX,
                SourceRepairFailureLayout.NONE,
            )
            if intent_transition.action is not SourceRepairAction.PUBLISH_INTENT:
                raise SourceRepairTransitionError("SOURCE_REPAIR_TRANSITION_REFUSED")
            _require_permitted_next_state(
                intent_transition,
                SourceRepairPhase.INTENT_DURABLE,
                SourceRepairFailureLayout.NONE,
            )
            archive = archive_root / f"source-closure-repair-{intent['intent_id']}"
            _require_descriptor_absent(parents.archive, archive.name)
            os.mkdir(archive.name, 0o700, dir_fd=parents.archive)
            if crash_at == "after_archive_create_intent":
                raise SourceRepairIncomplete(crash_at)
            try:
                if crash_at == "fail_archive_parent_fsync_intent":
                    raise OSError(errno.EIO, crash_at)
                os.fsync(parents.archive)
            except OSError as exc:
                raise SourceRepairIncomplete(
                    "INTENT_ARCHIVE_PARENT_DURABILITY_UNCERTAIN"
                ) from exc
            _attach_source_repair_archive_parent(
                parents,
                archive,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            for destination in (
                _ARCHIVED_SOURCE_NAME,
                _ARCHIVED_GENERATION_NAME,
                _SOURCE_REPAIR_INTENT_NAME,
                _SOURCE_REPAIR_RECEIPT_NAME,
            ):
                _require_descriptor_absent(parents.intent_archive, destination)
            publish_source_repair_intent(
                archive,
                intent,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                crash_at=crash_at,
                archive_descriptor=parents.intent_archive,
            )
            published_intent = reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            _require_permitted_next_state(
                intent_transition,
                published_intent.phase,
                published_intent.failure_layout,
            )
            if crash_at == "after_intent_fsync":
                raise SourceRepairIncomplete(crash_at)
        else:
            archive, intent = existing
            if parents.intent_archive is None:
                _attach_source_repair_archive_parent(
                    parents,
                    archive,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                )
        if archive is None or intent is None:
            raise CapacityHostArtifactError("SOURCE_REPAIR_INTENT_ABSENT")
        for _transition_count in range(8):
            # Recovery is fail-closed.  Each loop must earn a fresh grant from
            # one exact descriptor-bound classification; an earlier grant may
            # not survive an unclassified durable position.
            repair_effect_unknown = True
            authorized_precommit_recovery = None
            position = reconcile_source_repair(
                archive,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            generation_digest: str | None = None
            payloads: dict[str, bytes] | None = None
            evidence: SourceClosureEvidence | None = None
            archived_generation: Path | None = None
            archived_generation_digest: str | None = None
            current_phase = _classify_source_repair_position(
                archive_position=position,
                parents=parents,
                source_name=source_root.name,
                staged_source_name=staged_source.name,
            )
            if (
                current_phase is SourceRepairPhase.RECEIPT_DURABLE
                and position.receipt_digest is not None
            ):
                # The final generation digest depends on fallible semantic
                # observations below.  First establish, from the retained
                # generation-parent descriptor, whether a non-prefix child is
                # already visible.  From that point rollback is categorically
                # unsafe even when the later observations cannot identify or
                # verify that child.
                semantic_commit_visible = any(
                    not name.startswith(".")
                    for name in _descriptor_directory_names(parents.generation)
                )
                evidence = _observe_source_repair_source(
                    source_root,
                    intent=intent,
                    expected_source_commit=expected_source_commit,
                    parent_descriptor=parents.source,
                )
                archived_generation, archived_generation_digest = (
                    _observe_source_repair_archived_generation(
                        system_root=system_root,
                        archive=archive,
                        expected_uid=expected_uid,
                        expected_gid=expected_gid,
                        test_adapter=test_adapter,
                    )
                )
                expected_receipt = _expected_source_repair_receipt(
                    intent=intent,
                    evidence=evidence,
                    archived_generation_digest=archived_generation_digest,
                    expected_repair_commit=expected_repair_commit,
                )
                expected_receipt_digest = hashlib.sha256(
                    canonical_json(expected_receipt) + b"\n"
                ).hexdigest()
                if position.receipt_digest != expected_receipt_digest:
                    raise CapacityHostArtifactError("SOURCE_REPAIR_RECEIPT_MISMATCH")
                generation_digest, payloads = _generation_values(
                    evidence=evidence,
                    repair_commit=expected_repair_commit,
                    repair_receipt_digest=expected_receipt_digest,
                    archived_generation=archived_generation,
                )
                current_phase = _classify_source_repair_position(
                    archive_position=position,
                    parents=parents,
                    source_name=source_root.name,
                    staged_source_name=staged_source.name,
                    generation_digest=generation_digest,
                )
            repair_effect_unknown = False
            current_transition = _source_repair_transition_for(
                SourceRepairMode.REPAIR,
                current_phase,
                position.failure_layout,
            )
            current_action = current_transition.action
            recovery_transition = _source_repair_transition_for(
                SourceRepairMode.RECOVERY,
                current_phase,
                position.failure_layout,
            )
            if recovery_transition.action is SourceRepairAction.RECOVER_PRECOMMIT:
                if not recovery_transition.permitted_next_states:
                    raise SourceRepairTransitionError(
                        "SOURCE_REPAIR_NEXT_STATE_REFUSED"
                    )
                authorized_precommit_recovery = (
                    current_phase,
                    position.failure_layout,
                    recovery_transition,
                )
            elif recovery_transition.action is SourceRepairAction.VERIFY_COMMITTED:
                semantic_commit_visible = True
            elif recovery_transition.action is not SourceRepairAction.REFUSE_ROLLED_BACK:
                raise SourceRepairTransitionError(
                    "SOURCE_REPAIR_TRANSITION_REFUSED"
                )

            if current_action is SourceRepairAction.RECOVER_PRECOMMIT:
                if not current_transition.permitted_next_states:
                    raise SourceRepairTransitionError(
                        "SOURCE_REPAIR_NEXT_STATE_REFUSED"
                    )
                authorized_precommit_recovery = None
                _restore_digest_bound_precommit_state(
                    archive=archive,
                    source_root=source_root,
                    generation_root=generation_root,
                    staged_source=staged_source,
                    intent=intent,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    test_adapter=test_adapter,
                    parents=parents,
                    crash_at=crash_at,
                    transition=current_transition,
                )
                raise CapacityHostArtifactError("SOURCE_REPAIR_PRECOMMIT_RESTORED")
            if current_action is SourceRepairAction.REFUSE_ROLLED_BACK:
                raise CapacityHostArtifactError("SOURCE_REPAIR_PRECOMMIT_RESTORED")
            if current_action is SourceRepairAction.ADVANCE_SOURCE:
                _require_permitted_next_state(
                    current_transition,
                    SourceRepairPhase.SOURCE_INSTALLED,
                    SourceRepairFailureLayout.NONE,
                )
                _advance_source_repair_source_phase(
                    parents=parents,
                    archive=archive,
                    source_root=source_root,
                    staged_source=staged_source,
                    intent=intent,
                    expected_source_commit=expected_source_commit,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    test_adapter=test_adapter,
                    crash_at=crash_at,
                )
                next_position = reconcile_source_repair(
                    archive, expected_uid=expected_uid, expected_gid=expected_gid
                )
                next_phase = _classify_source_repair_position(
                    archive_position=next_position,
                    parents=parents,
                    source_name=source_root.name,
                    staged_source_name=staged_source.name,
                )
                _require_permitted_next_state(
                    current_transition, next_phase, next_position.failure_layout
                )
                continue
            if current_action is SourceRepairAction.ADVANCE_GENERATION:
                _require_permitted_next_state(
                    current_transition,
                    SourceRepairPhase.GENERATION_ARCHIVED,
                    SourceRepairFailureLayout.NONE,
                )
                _advance_source_repair_source_phase(
                    parents=parents,
                    archive=archive,
                    source_root=source_root,
                    staged_source=staged_source,
                    intent=intent,
                    expected_source_commit=expected_source_commit,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    test_adapter=test_adapter,
                    crash_at=crash_at,
                )
                _advance_source_repair_generation_phase(
                    system_root=system_root,
                    parents=parents,
                    archive=archive,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    test_adapter=test_adapter,
                    crash_at=crash_at,
                )
                next_position = reconcile_source_repair(
                    archive, expected_uid=expected_uid, expected_gid=expected_gid
                )
                next_phase = _classify_source_repair_position(
                    archive_position=next_position,
                    parents=parents,
                    source_name=source_root.name,
                    staged_source_name=staged_source.name,
                )
                _require_permitted_next_state(
                    current_transition, next_phase, next_position.failure_layout
                )
                continue
            if current_action is SourceRepairAction.ADVANCE_RECEIPT:
                _require_permitted_next_state(
                    current_transition,
                    SourceRepairPhase.RECEIPT_DURABLE,
                    SourceRepairFailureLayout.NONE,
                )
                evidence = _observe_source_repair_source(
                    source_root,
                    intent=intent,
                    expected_source_commit=expected_source_commit,
                    parent_descriptor=parents.source,
                )
                archived_generation, archived_generation_digest = (
                    _observe_source_repair_archived_generation(
                        system_root=system_root,
                        archive=archive,
                        expected_uid=expected_uid,
                        expected_gid=expected_gid,
                        test_adapter=test_adapter,
                    )
                )
                _advance_source_repair_receipt_phase(
                    parents=parents,
                    archive=archive,
                    intent=intent,
                    evidence=evidence,
                    archived_generation_digest=archived_generation_digest,
                    expected_repair_commit=expected_repair_commit,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    crash_at=crash_at,
                )
                next_position = reconcile_source_repair(
                    archive, expected_uid=expected_uid, expected_gid=expected_gid
                )
                next_phase = _classify_source_repair_position(
                    archive_position=next_position,
                    parents=parents,
                    source_name=source_root.name,
                    staged_source_name=staged_source.name,
                )
                _require_permitted_next_state(
                    current_transition, next_phase, next_position.failure_layout
                )
                continue
            if current_action not in {
                SourceRepairAction.COMMIT_GENERATION,
                SourceRepairAction.VERIFY_COMMITTED,
            }:
                raise SourceRepairTransitionError("SOURCE_REPAIR_TRANSITION_REFUSED")
            if (
                evidence is None
                or archived_generation is None
                or generation_digest is None
                or payloads is None
            ):
                raise CapacityHostArtifactError("SOURCE_REPAIR_POSITION_AMBIGUOUS")
            target_generation = generation_root / generation_digest
            if current_action is SourceRepairAction.VERIFY_COMMITTED:
                semantic_commit_visible = True
                _verify_repaired_generation(
                    target_generation,
                    expected_payloads=payloads,
                    expected_digest=generation_digest,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    expected_mode=0o700 if test_adapter else 0o555,
                )
                _require_permitted_next_state(
                    current_transition,
                    SourceRepairPhase.COMMITTED,
                    SourceRepairFailureLayout.NONE,
                )
                os.fsync(parents.generation)
                parents.revalidate()
                return "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"

            _require_permitted_next_state(
                current_transition,
                SourceRepairPhase.GENERATION_PREFIX,
                SourceRepairFailureLayout.NONE,
            )
            hidden_generation = _build_repaired_generation_candidate(
                generation_root,
                generation_parent_descriptor=parents.generation,
                generation_digest=generation_digest,
                payloads=payloads,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                crash_at=crash_at,
                test_adapter=test_adapter,
            )
            prefix_position = reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            prefix_phase = _classify_source_repair_position(
                archive_position=prefix_position,
                parents=parents,
                source_name=source_root.name,
                staged_source_name=staged_source.name,
                generation_digest=generation_digest,
            )
            _require_permitted_next_state(
                current_transition, prefix_phase, prefix_position.failure_layout
            )
            final_evidence = _observe_source_repair_source(
                source_root,
                intent=intent,
                expected_source_commit=expected_source_commit,
                parent_descriptor=parents.source,
            )
            if final_evidence != evidence:
                raise CapacityHostArtifactError("SOURCE_REPAIR_SOURCE_DRIFT")
            reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            _verify_preserved_h0_invariants(
                system_root,
                archived_generation,
                test_adapter=test_adapter,
                parents=parents,
            )
            if crash_at == "before_final_rename":
                raise SourceRepairIncomplete(crash_at)
            _require_permitted_next_state(
                current_transition,
                SourceRepairPhase.COMMITTED,
                SourceRepairFailureLayout.NONE,
            )
            generation_parent_descriptor = _rename_final_generation(
                hidden_generation,
                target_generation,
                parent_descriptor=parents.generation,
            )
            semantic_commit_visible = True
            try:
                if crash_at == "after_final_rename_before_parent_fsync":
                    raise SourceRepairIncomplete(crash_at)
                os.fsync(generation_parent_descriptor)
            finally:
                if generation_parent_descriptor != parents.generation:
                    os.close(generation_parent_descriptor)
            committed_position = reconcile_source_repair(
                archive, expected_uid=expected_uid, expected_gid=expected_gid
            )
            committed_phase = _classify_source_repair_position(
                archive_position=committed_position,
                parents=parents,
                source_name=source_root.name,
                staged_source_name=staged_source.name,
                generation_digest=generation_digest,
            )
            _require_permitted_next_state(
                current_transition,
                committed_phase,
                committed_position.failure_layout,
            )
            if crash_at == "after_parent_fsync_before_stdout":
                raise SourceRepairIncomplete(crash_at)
            parents.revalidate()
            return "H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED"
        raise CapacityHostArtifactError("SOURCE_REPAIR_TRANSITION_LOOP")
    finally:
        active_error = sys.exc_info()[1]
        try:
            if (
                isinstance(active_error, (CapacityHostArtifactError, OSError))
                and not isinstance(active_error, SourceRepairTransitionError)
                and mode == "repair"
                and not semantic_commit_visible
                and archive is not None
                and intent is not None
                and source_root is not None
                and generation_root is not None
                and staged_source is not None
                and _path_lexists(archive / _SOURCE_REPAIR_INTENT_NAME)
                and authorized_precommit_recovery is not None
            ):
                _recovery_phase, _recovery_layout, recovery_transition = (
                    authorized_precommit_recovery
                )
                authorized_precommit_recovery = None
                _restore_digest_bound_precommit_state(
                    archive=archive,
                    source_root=source_root,
                    generation_root=generation_root,
                    staged_source=staged_source,
                    intent=intent,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                    test_adapter=test_adapter,
                    parents=parents,
                    crash_at=crash_at,
                    transition=recovery_transition,
                )
        finally:
            cleanup_error: OSError | None = None
            if parents is not None:
                try:
                    parents.close()
                except OSError as exc:
                    cleanup_error = exc
            if lock_descriptor is not None:
                try:
                    fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
                except OSError as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
                try:
                    os.close(lock_descriptor)
                except OSError as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
            if cleanup_error is not None and active_error is None:
                if semantic_commit_visible:
                    raise SourceRepairIncomplete(
                        "POST_COMMIT_RECONCILIATION_REQUIRED"
                    ) from cleanup_error
                raise CapacityHostArtifactError(
                    "SOURCE_REPAIR_CLEANUP_INCOMPLETE"
                ) from cleanup_error
        if (
            (semantic_commit_visible or repair_effect_unknown)
            and isinstance(active_error, Exception)
            and not isinstance(active_error, SourceRepairIncomplete)
        ):
            raise SourceRepairIncomplete(
                "POST_COMMIT_RECONCILIATION_REQUIRED"
            ) from active_error


def verify_approved_xattrs(path: Path) -> dict[str, Any]:
    """Reject caller-controlled xattrs while tolerating macOS system provenance."""

    if not path.exists() and not path.is_symlink():
        raise CapacityHostArtifactError("XATTR_ROOT_ABSENT")
    paths = [path]
    if path.is_dir() and not path.is_symlink():
        paths.extend(
            sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix())
        )
    for candidate in paths:
        if _extended_attribute_names(candidate) - _APPROVED_SYSTEM_XATTRS:
            raise CapacityHostArtifactError("UNAPPROVED_EXTENDED_ATTRIBUTE")
    return {
        "approved_system_xattrs": ["com.apple.provenance"],
        "inspected_object_count": len(paths),
    }


def _closed_tree_digest(path: Path, *, expected_uid: int) -> str:
    paths = [path]
    if path.is_dir() and not path.is_symlink():
        paths.extend(
            sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix())
        )
    rows: list[dict[str, Any]] = []
    for candidate in paths:
        info = candidate.lstat()
        relative = "." if candidate == path else candidate.relative_to(path).as_posix()
        if (
            stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_uid
            or stat.S_IMODE(info.st_mode) & 0o022
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _extended_attribute_names(candidate) - _APPROVED_SYSTEM_XATTRS
        ):
            raise CapacityHostArtifactError("RECOVERY_OBJECT_INVALID")
        if stat.S_ISDIR(info.st_mode):
            row: dict[str, Any] = {
                "gid": info.st_gid,
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": info.st_nlink,
                "path": relative,
                "type": "directory",
                "uid": info.st_uid,
            }
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            row = {
                "gid": info.st_gid,
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": 1,
                "path": relative,
                "sha256": sha256_file(candidate),
                "size": info.st_size,
                "type": "file",
                "uid": info.st_uid,
            }
        else:
            raise CapacityHostArtifactError("RECOVERY_OBJECT_INVALID")
        rows.append(row)
    return hashlib.sha256(canonical_json(rows)).hexdigest()


def create_recovery_intent(
    archive: Path,
    sources: Sequence[Path],
    *,
    expected_uid: int,
) -> dict[str, Any]:
    if not sources or len(set(sources)) != len(sources):
        raise CapacityHostArtifactError("RECOVERY_SOURCE_INVENTORY_INVALID")
    info = archive.lstat()
    intent_path = archive / "recovery-intent.json"
    intent_candidate = archive / ".recovery-intent.json.candidate"
    archive_entries = set(archive.iterdir())
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != expected_uid
        or stat.S_IMODE(info.st_mode) & 0o022
        or archive_entries not in (set(), {intent_candidate})
    ):
        raise CapacityHostArtifactError("RECOVERY_ARCHIVE_INVALID")
    rows = []
    ordered_sources = sorted(sources, key=os.fspath)
    for index, source in enumerate(ordered_sources, start=1):
        if (
            not source.is_absolute()
            or archive in (source, *source.parents)
            or source in (archive, *archive.parents)
        ):
            raise CapacityHostArtifactError("RECOVERY_SOURCE_PATH_INVALID")
        rows.append(
            {
                "destination_name": f"{index}-{source.name}",
                "source_path": os.fspath(source),
                "tree_sha256": _closed_tree_digest(source, expected_uid=expected_uid),
            }
        )
    value = {"schema_version": RECOVERY_INTENT_SCHEMA, "targets": rows}
    _publish_resumable_canonical_file(
        intent_path,
        canonical_json(value) + b"\n",
        mode=0o400,
        expected_uid=expected_uid,
    )
    return value


def resume_recovery_archive(archive: Path, *, expected_uid: int) -> dict[str, Any]:
    intent_path = archive / "recovery-intent.json"
    try:
        intent_bytes = intent_path.read_bytes()
        intent = json.loads(intent_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapacityHostArtifactError("RECOVERY_INTENT_UNREADABLE") from exc
    if intent_bytes != canonical_json(intent) + b"\n" or set(intent) != {"schema_version", "targets"}:
        raise CapacityHostArtifactError("RECOVERY_INTENT_INVALID")
    targets = intent.get("targets")
    if intent.get("schema_version") != RECOVERY_INTENT_SCHEMA or not isinstance(targets, list) or not targets:
        raise CapacityHostArtifactError("RECOVERY_INTENT_INVALID")
    _validate_canonical_file(intent_path, intent_bytes, mode=0o400, expected_uid=expected_uid)
    expected_fields = {"destination_name", "source_path", "tree_sha256"}
    sources: set[Path] = set()
    destinations: set[Path] = set()
    for index, row in enumerate(targets, start=1):
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise CapacityHostArtifactError("RECOVERY_INTENT_ROW_INVALID")
        source = Path(str(row["source_path"]))
        destination = archive / str(row["destination_name"])
        if (
            not source.is_absolute()
            or destination.parent != archive
            or destination.name != f"{index}-{source.name}"
            or _DIGEST_RE.fullmatch(str(row["tree_sha256"])) is None
            or source in sources
            or destination in destinations
        ):
            raise CapacityHostArtifactError("RECOVERY_INTENT_ROW_INVALID")
        sources.add(source)
        destinations.add(destination)
    receipt_path = archive / "recovery-receipt.json"
    receipt_candidate = archive / ".recovery-receipt.json.candidate"
    expected_archive_entries = {intent_path, *destinations}
    observed_archive_entries = set(archive.iterdir())
    if receipt_path in observed_archive_entries:
        expected_archive_entries.add(receipt_path)
    if receipt_candidate in observed_archive_entries:
        expected_archive_entries.add(receipt_candidate)
    if observed_archive_entries - expected_archive_entries:
        raise CapacityHostArtifactError("RECOVERY_ARCHIVE_INVENTORY_INVALID")
    if receipt_path in observed_archive_entries and receipt_candidate in observed_archive_entries:
        raise CapacityHostArtifactError("RECOVERY_RECEIPT_POSITION_AMBIGUOUS")
    if receipt_path in observed_archive_entries or receipt_candidate in observed_archive_entries:
        for row in targets:
            source = Path(str(row["source_path"]))
            destination = archive / str(row["destination_name"])
            if source.exists() or source.is_symlink() or not destination.exists() or destination.is_symlink():
                raise CapacityHostArtifactError("RECOVERY_RECEIPT_POSITION_INVALID")

    for row in targets:
        source = Path(str(row["source_path"]))
        destination = archive / str(row["destination_name"])
        source_present = source.exists() or source.is_symlink()
        destination_present = destination.exists() or destination.is_symlink()
        if source_present == destination_present:
            raise CapacityHostArtifactError("RECOVERY_POSITION_AMBIGUOUS")
        current = source if source_present else destination
        if _closed_tree_digest(current, expected_uid=expected_uid) != row["tree_sha256"]:
            raise CapacityHostArtifactError("RECOVERY_TREE_DIGEST_MISMATCH")
        if source_present:
            source.rename(destination)
            _fsync_directory(source.parent)
            _fsync_directory(archive)
            if _closed_tree_digest(destination, expected_uid=expected_uid) != row["tree_sha256"]:
                raise CapacityHostArtifactError("RECOVERY_TREE_DIGEST_MISMATCH")
    receipt = {
        "schema_version": RECOVERY_RECEIPT_SCHEMA,
        "outcome": "INTERRUPTED_H0_PARTIAL_RECOVERED",
        "intent_sha256": hashlib.sha256(intent_bytes).hexdigest(),
        "recovered_target_count": len(targets),
        "recovered_targets": list(targets),
        "service_state": "labels_disabled_unloaded",
        "socket_state": "nodes_absent",
        "credential_state": "not_read_or_changed",
        "continuation": "same_carrier_preparation_resumed",
    }
    encoded = canonical_json(receipt) + b"\n"
    _publish_resumable_canonical_file(
        receipt_path,
        encoded,
        mode=0o400,
        expected_uid=expected_uid,
    )
    return receipt


def _git_environment() -> dict[str, str]:
    return {
        "HOME": "/var/empty",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_LOCAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_EXTERNAL_DIFF": "/usr/bin/false",
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CONFIG_COUNT": "6",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "core.attributesFile",
        "GIT_CONFIG_VALUE_2": "/dev/null",
        "GIT_CONFIG_KEY_3": "protocol.allow",
        "GIT_CONFIG_VALUE_3": "never",
        "GIT_CONFIG_KEY_4": "protocol.file.allow",
        "GIT_CONFIG_VALUE_4": "always",
        "GIT_CONFIG_KEY_5": "diff.external",
        "GIT_CONFIG_VALUE_5": "/usr/bin/false",
    }


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_OBJECT_TRANSPORT_REFUSED")
    return completed.stdout


def _material_rows(
    repository: Path,
    *,
    commit: str,
    material_paths: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_path in material_paths:
        candidate = PurePosixPath(raw_path)
        if (
            candidate.is_absolute()
            or not candidate.parts
            or ".." in candidate.parts
            or os.fspath(candidate) != raw_path
        ):
            raise CapacityHostArtifactError("MATERIAL_PATH_INVALID")
        output = _git(repository, "ls-tree", "-z", commit, "--", raw_path)
        values = output.rstrip(b"\0").split(b"\t", 1)
        if len(values) != 2 or values[1].decode("utf-8", "strict") != raw_path:
            raise CapacityHostArtifactError("MATERIAL_PATH_MISSING")
        header = values[0].decode("ascii", "strict").split()
        if len(header) != 3 or header[0] not in _MATERIAL_MODES or header[1] != "blob":
            raise CapacityHostArtifactError("MATERIAL_OBJECT_INVALID")
        object_id = header[2]
        if _OBJECT_RE.fullmatch(object_id) is None:
            raise CapacityHostArtifactError("MATERIAL_OBJECT_INVALID")
        payload = _git(repository, "cat-file", "blob", object_id)
        rows.append(
            {
                "path": raw_path,
                "mode": header[0],
                "git_blob": object_id,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        )
    if [row["path"] for row in rows] != sorted({row["path"] for row in rows}):
        raise CapacityHostArtifactError("MATERIAL_PATH_ORDER_INVALID")
    return rows


def build_source_transport(
    source_repository: Path,
    output: Path,
    *,
    commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    """Build one data-only ZIP containing a narrow Git pack and closed manifest."""

    if _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_INVALID")
    source = source_repository.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise CapacityHostArtifactError("OUTPUT_EXISTS")
    observed_commit = _git(source, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if observed_commit != commit:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    rows = _material_rows(source, commit=commit, material_paths=material_paths)

    graph_objects = _git(
        source,
        "rev-list",
        "--objects",
        "--filter=blob:none",
        "--no-object-names",
        "--max-count=1",
        commit,
    ).decode("ascii", "strict").splitlines()
    object_ids = sorted(set(graph_objects) | {str(row["git_blob"]) for row in rows})
    if not object_ids or any(_OBJECT_RE.fullmatch(value) is None for value in object_ids):
        raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
    payload = _git(
        source,
        "pack-objects",
        "--stdout",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    if not payload.startswith(b"PACK"):
        raise CapacityHostArtifactError("PACK_INVALID")
    manifest = {
        "schema_version": TRANSPORT_SCHEMA,
        "repository": "mastermindx-market-intelligence/macro",
        "commit": commit,
        "object_format": "sha1",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "material": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_bytes_exclusive(output, _canonical_transport_bytes(manifest, payload), 0o600)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return manifest


def validate_transport_manifest(
    value: Any,
    *,
    expected_commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "repository",
        "commit",
        "object_format",
        "payload_sha256",
        "material",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CapacityHostArtifactError("TRANSPORT_MANIFEST_FIELDS_INVALID")
    if (
        value.get("schema_version") != TRANSPORT_SCHEMA
        or value.get("repository") != "mastermindx-market-intelligence/macro"
        or value.get("commit") != expected_commit
        or value.get("object_format") != "sha1"
        or _DIGEST_RE.fullmatch(str(value.get("payload_sha256"))) is None
    ):
        raise CapacityHostArtifactError("TRANSPORT_MANIFEST_MISMATCH")
    rows = value.get("material")
    if not isinstance(rows, list) or [row.get("path") for row in rows if isinstance(row, Mapping)] != list(material_paths):
        raise CapacityHostArtifactError("TRANSPORT_MATERIAL_INVENTORY_INVALID")
    row_fields = {"path", "mode", "git_blob", "sha256", "size"}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != row_fields
            or row.get("mode") not in _MATERIAL_MODES
            or _OBJECT_RE.fullmatch(str(row.get("git_blob"))) is None
            or _DIGEST_RE.fullmatch(str(row.get("sha256"))) is None
            or isinstance(row.get("size"), bool)
            or not isinstance(row.get("size"), int)
            or row["size"] < 0
        ):
            raise CapacityHostArtifactError("TRANSPORT_MATERIAL_ROW_INVALID")
    return dict(value)


def extract_source_transport(
    archive_path: Path,
    destination: Path,
    *,
    expected_commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    """Validate and extract exactly manifest.json and payload.pack."""

    archive_info = archive_path.lstat()
    if (
        not stat.S_ISREG(archive_info.st_mode)
        or archive_info.st_nlink != 1
        or archive_info.st_size > 65 * 1024 * 1024
    ):
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_FILE_INVALID")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if {info.filename for info in infos} != _TRANSPORT_MEMBERS or len(infos) != 2:
                raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_INVENTORY_INVALID")
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    not stat.S_ISREG(mode)
                    or stat.S_IMODE(mode) != 0o400
                    or info.flag_bits & 0x1
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.file_size > 64 * 1024 * 1024
                    or info.compress_size != info.file_size
                ):
                    raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_MEMBER_INVALID")
            manifest_bytes = archive.read("manifest.json")
            manifest = validate_transport_manifest(
                json.loads(manifest_bytes),
                expected_commit=expected_commit,
                material_paths=material_paths,
            )
            payload = archive.read("payload.pack")
        if manifest_bytes != canonical_json(manifest):
            raise CapacityHostArtifactError("TRANSPORT_MANIFEST_NONCANONICAL")
        if hashlib.sha256(payload).hexdigest() != manifest["payload_sha256"]:
            raise CapacityHostArtifactError("TRANSPORT_PAYLOAD_DIGEST_MISMATCH")
        if archive_path.read_bytes() != _canonical_transport_bytes(manifest, payload):
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")
        for name, body in (
            ("manifest.json", canonical_json(manifest)),
            ("payload.pack", payload),
        ):
            target = destination / name
            _write_bytes_exclusive(target, body, 0o400)
        return manifest
    except Exception:
        for child in destination.iterdir():
            child.unlink(missing_ok=True)
        destination.rmdir()
        raise


def _run_git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    completed = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_MATERIALIZATION_REFUSED")
    return completed.stdout


def verify_materialized_source(
    source_root: Path,
    *,
    manifest: Mapping[str, Any],
) -> None:
    """Prove the checkout has only exact reviewed material blobs."""

    commit = str(manifest["commit"])
    if _run_git(source_root, "rev-parse", "HEAD").decode().strip() != commit:
        raise CapacityHostArtifactError("SOURCE_HEAD_MISMATCH")
    if _run_git(source_root, "branch", "--show-current").strip():
        raise CapacityHostArtifactError("SOURCE_HEAD_ATTACHED")
    if _run_git(source_root, "remote").strip():
        raise CapacityHostArtifactError("SOURCE_REMOTE_PRESENT")
    expected_paths = [str(row["path"]) for row in manifest["material"]]
    observed_paths = sorted(
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if ".git" not in path.relative_to(source_root).parts and path.is_file()
    )
    if observed_paths != expected_paths:
        raise CapacityHostArtifactError("SOURCE_WORKTREE_INVENTORY_MISMATCH")
    for row in manifest["material"]:
        path = source_root / str(row["path"])
        info = path.lstat()
        expected_modes = {0o755, 0o555} if row["mode"] == "100755" else {0o644, 0o444}
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) not in expected_modes
            or info.st_size != row["size"]
            or sha256_file(path) != row["sha256"]
        ):
            raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
        observed_blob = _run_git(source_root, "hash-object", "--no-filters", os.fspath(path)).decode().strip()
        tree_line = _run_git(source_root, "ls-tree", "-z", commit, "--", str(row["path"]))
        if observed_blob != row["git_blob"] or f" {row['git_blob']}\t".encode() not in tree_line:
            raise CapacityHostArtifactError("SOURCE_GIT_BLOB_MISMATCH")
    status = _run_git(source_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise CapacityHostArtifactError("SOURCE_WORKTREE_DIRTY")


def materialize_source_transport(
    archive_path: Path,
    source_root: Path,
    *,
    expected_commit: str,
    material_paths: Sequence[str],
) -> dict[str, Any]:
    """Create a fresh repository from the inert pack; never copy caller Git state."""

    transport = source_root.with_name(f".{source_root.name}.transport")
    if source_root.exists() or source_root.is_symlink() or transport.exists():
        raise CapacityHostArtifactError("SOURCE_DESTINATION_EXISTS")
    manifest = extract_source_transport(
        archive_path,
        transport,
        expected_commit=expected_commit,
        material_paths=material_paths,
    )
    try:
        source_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        _run_git(source_root, "init", "--quiet")
        _run_git(source_root, "config", "core.hooksPath", "/dev/null")
        _run_git(source_root, "config", "core.fsmonitor", "false")
        for hook in (source_root / ".git" / "hooks").iterdir():
            if not hook.is_file() or hook.is_symlink():
                raise CapacityHostArtifactError("SOURCE_DEFAULT_HOOK_INVENTORY_INVALID")
            hook.chmod(0o400)
        pack_output = _run_git(
            source_root,
            "index-pack",
            "--stdin",
            "--fix-thin",
            input_bytes=(transport / "payload.pack").read_bytes(),
        ).decode("ascii", "strict").strip()
        match = re.fullmatch(r"(?:pack\s+)?([0-9a-f]{40})", pack_output)
        if match is None:
            raise CapacityHostArtifactError("SOURCE_PACK_IDENTITY_INVALID")
        pack_base = source_root / ".git" / "objects" / "pack" / f"pack-{match.group(1)}"
        if not pack_base.with_suffix(".pack").is_file() or not pack_base.with_suffix(".idx").is_file():
            raise CapacityHostArtifactError("SOURCE_PACK_INSTALL_INVALID")
        pack_base.with_suffix(".promisor").write_bytes(b"")

        _run_git(source_root, "config", "extensions.partialClone", "cf2h0-offline")
        _run_git(source_root, "config", "extensions.worktreeConfig", "true")
        _run_git(source_root, "config", "--worktree", "core.sparseCheckout", "true")
        _run_git(source_root, "config", "--worktree", "core.sparseCheckoutCone", "false")
        sparse = source_root / ".git" / "info" / "sparse-checkout"
        sparse.write_text("".join(f"/{path}\n" for path in material_paths), encoding="utf-8")
        _run_git(source_root, "checkout", "--detach", expected_commit)
        for row in manifest["material"]:
            material_path = source_root / str(row["path"])
            descriptor = os.open(
                material_path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
            try:
                material_info = os.fstat(descriptor)
                if not stat.S_ISREG(material_info.st_mode) or material_info.st_nlink != 1:
                    raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
                os.fchmod(descriptor, 0o755 if row["mode"] == "100755" else 0o644)
            finally:
                os.close(descriptor)
        (source_root / ".git" / "cf2-h0-transport-manifest.json").write_bytes(
            canonical_json(manifest)
        )
        _run_git(source_root, "fsck", "--full", "--strict", "--no-progress")
        verify_materialized_source(source_root, manifest=manifest)
        return manifest
    except Exception:
        raise
    finally:
        for child in transport.iterdir():
            child.unlink(missing_ok=True)
        transport.rmdir()


def _inventory_digest(rows: Sequence[ObjectInventoryRow]) -> str:
    return hashlib.sha256(b"".join(row.encoded() for row in rows)).hexdigest()


def _source_common_git_directory(repository: Path) -> Path:
    raw = _git(repository, "rev-parse", "--git-common-dir").decode("utf-8", "strict").strip()
    if not raw or "\0" in raw or "\r" in raw or "\n" in raw:
        raise CapacityHostArtifactError("SOURCE_GIT_DIRECTORY_INVALID")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repository / candidate
    return candidate.resolve(strict=True)


def _path_lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _read_small_nofollow(path: Path, maximum_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        return _read_descriptor(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)


def _refuse_ambient_object_sources(repository: Path) -> None:
    """Refuse ambient object graph inputs that Git environment variables cannot erase."""

    git_dir = _source_common_git_directory(repository)
    alternates = git_dir / "objects" / "info" / "alternates"
    grafts = git_dir / "info" / "grafts"
    shallow = git_dir / "shallow"
    if any(_path_lstat(path) is not None for path in (alternates, grafts, shallow)):
        raise CapacityHostArtifactError("SOURCE_AMBIENT_OBJECT_STATE_PRESENT")
    replace = git_dir / "refs" / "replace"
    replace_info = _path_lstat(replace)
    if replace_info is not None:
        if not stat.S_ISDIR(replace_info.st_mode) or any(replace.iterdir()):
            raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
    packed_refs = git_dir / "packed-refs"
    if _path_lstat(packed_refs) is not None:
        if b"refs/replace/" in _read_small_nofollow(packed_refs, 16 * 1024 * 1024):
            raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
    pack_dir = git_dir / "objects" / "pack"
    if pack_dir.is_dir() and any(path.name.endswith(".promisor") for path in pack_dir.iterdir()):
        raise CapacityHostArtifactError("SOURCE_PROMISOR_STATE_PRESENT")
    config = git_dir / "config"
    if _path_lstat(config) is not None:
        lowered = _read_small_nofollow(config, 16 * 1024 * 1024).lower()
        if b"partialclone" in lowered or b"promisor" in lowered:
            raise CapacityHostArtifactError("SOURCE_PROMISOR_STATE_PRESENT")


def enumerate_reachable_objects(
    repository: Path, commit: str
) -> tuple[ObjectInventoryRow, ...]:
    """Return the exact semantic inventory reachable from one commit, or refuse missing state."""

    if _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_INVALID")
    source = repository.resolve(strict=True)
    _refuse_ambient_object_sources(source)
    observed_commit = _git(source, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if observed_commit != commit:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    raw_objects = _git(
        source,
        "rev-list",
        "--objects",
        "--no-object-names",
        "--missing=print",
        commit,
    ).decode("ascii", "strict").splitlines()
    if (
        not raw_objects
        or any(value.startswith("?") for value in raw_objects)
        or any(_OBJECT_RE.fullmatch(value) is None for value in raw_objects)
        or len(set(raw_objects)) != len(raw_objects)
    ):
        raise CapacityHostArtifactError("OBJECT_CLOSURE_MISSING")
    object_ids = sorted(raw_objects)
    checked = _git(
        source,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    if len(checked) != len(object_ids):
        raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
    rows: list[ObjectInventoryRow] = []
    for expected_oid, line in zip(object_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID") from exc
        if size < 0 or str(size) != fields[2]:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _write_complete_pack(
    repository: Path, rows: Sequence[ObjectInventoryRow], output: Path
) -> None:
    object_input = b"".join(f"{row.oid}\n".encode("ascii") for row in rows)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            completed = subprocess.run(
                [
                    "/usr/bin/git",
                    "--no-replace-objects",
                    "-C",
                    os.fspath(repository),
                    "pack-objects",
                    "--stdout",
                ],
                input=object_input,
                stdout=handle,
                stderr=subprocess.PIPE,
                check=False,
                env=_git_environment(),
            )
            handle.flush()
        if completed.returncode != 0:
            raise CapacityHostArtifactError("GIT_OBJECT_TRANSPORT_REFUSED")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_pack_file(path: Path, *, expected_count: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("PACK_INVALID") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size < 32:
            raise CapacityHostArtifactError("PACK_INVALID")
        header = os.read(descriptor, 12)
        if len(header) != 12 or header[:4] != b"PACK":
            raise CapacityHostArtifactError("PACK_INVALID")
        version, count = struct.unpack(">II", header[4:])
        if version not in {2, 3} or count != expected_count:
            raise CapacityHostArtifactError("PACK_OBJECT_INVENTORY_MISMATCH")
        content_size = before.st_size - 20
        os.lseek(descriptor, 0, os.SEEK_SET)
        digest = hashlib.sha1()
        remaining = content_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise CapacityHostArtifactError("PACK_INVALID")
            digest.update(chunk)
            remaining -= len(chunk)
        trailer = os.read(descriptor, 21)
        after = os.fstat(descriptor)
        if (
            len(trailer) != 20
            or trailer != digest.digest()
            or after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise CapacityHostArtifactError("PACK_TRAILER_INVALID")
    finally:
        os.close(descriptor)


def _zip_info(name: str, *, size: int = 0) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o400) << 16
    info.file_size = size
    return info


def _require_v2_zip32_size(size: int) -> None:
    # This is the exact preflight used by ZipFile.open(..., force_zip64=False).
    if size < 0 or size * 1.05 > zipfile.ZIP64_LIMIT:
        raise CapacityHostArtifactError(_V2_ZIP32_ERROR)


def _write_transport_v2_archive(
    output: Path, manifest: Mapping[str, Any], payload_path: Path
) -> None:
    payload_size = payload_path.stat().st_size
    manifest_bytes = canonical_json(manifest)
    _require_v2_zip32_size(len(manifest_bytes))
    _require_v2_zip32_size(payload_size)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w+b", closefd=False) as raw:
            try:
                with zipfile.ZipFile(
                    raw,
                    "w",
                    compression=zipfile.ZIP_STORED,
                    allowZip64=False,
                ) as archive:
                    archive.writestr(
                        _zip_info("manifest.json", size=len(manifest_bytes)),
                        manifest_bytes,
                    )
                    with payload_path.open("rb") as source, archive.open(
                        _zip_info("payload.pack", size=payload_size), "w"
                    ) as target:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
            except zipfile.LargeZipFile as exc:
                raise CapacityHostArtifactError(_V2_ZIP32_ERROR) from exc
            raw.flush()
        os.fsync(descriptor)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def build_source_transport_v2(
    source_repository: Path,
    output: Path,
    *,
    commit: str,
) -> dict[str, Any]:
    """Build the complete v2 pack with frozen CF1 projection and semantic closure identity."""

    if commit != PRODUCER_COMMIT or _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    if output.exists() or output.is_symlink():
        raise CapacityHostArtifactError("OUTPUT_EXISTS")
    source = source_repository.resolve(strict=True)
    rows = enumerate_reachable_objects(source, commit)
    material = _material_rows(
        source, commit=commit, material_paths=PRODUCER_MATERIAL_PATHS
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.payload-", dir=os.fspath(output.parent)
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        _write_complete_pack(source, rows, temporary)
        _validate_pack_file(temporary, expected_count=len(rows))
        manifest = {
            "schema_version": TRANSPORT_SCHEMA_V2,
            "repository": PRODUCER_REPOSITORY,
            "commit": commit,
            "object_format": "sha1",
            "closure_kind": "complete_reachable_commit_graph",
            "payload_sha256": sha256_file(temporary),
            "object_count": len(rows),
            "object_inventory_sha256": _inventory_digest(rows),
            "material": material,
        }
        _write_transport_v2_archive(output, manifest, temporary)
        return manifest
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def validate_transport_manifest_v2(
    value: Any, *, expected_commit: str
) -> dict[str, Any]:
    fields = {
        "schema_version",
        "repository",
        "commit",
        "object_format",
        "closure_kind",
        "payload_sha256",
        "object_count",
        "object_inventory_sha256",
        "material",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CapacityHostArtifactError("TRANSPORT_V2_MANIFEST_FIELDS_INVALID")
    count = value.get("object_count")
    if (
        expected_commit != PRODUCER_COMMIT
        or value.get("schema_version") != TRANSPORT_SCHEMA_V2
        or value.get("repository") != PRODUCER_REPOSITORY
        or value.get("commit") != expected_commit
        or value.get("object_format") != "sha1"
        or value.get("closure_kind") != "complete_reachable_commit_graph"
        or _DIGEST_RE.fullmatch(str(value.get("payload_sha256"))) is None
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 1
        or _DIGEST_RE.fullmatch(str(value.get("object_inventory_sha256"))) is None
    ):
        raise CapacityHostArtifactError("TRANSPORT_V2_MANIFEST_MISMATCH")
    rows = value.get("material")
    if (
        not isinstance(rows, list)
        or [row.get("path") for row in rows if isinstance(row, Mapping)]
        != list(PRODUCER_MATERIAL_PATHS)
    ):
        raise CapacityHostArtifactError("TRANSPORT_MATERIAL_INVENTORY_INVALID")
    row_fields = {"path", "mode", "git_blob", "sha256", "size"}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != row_fields
            or row.get("mode") not in _MATERIAL_MODES
            or _OBJECT_RE.fullmatch(str(row.get("git_blob"))) is None
            or _DIGEST_RE.fullmatch(str(row.get("sha256"))) is None
            or isinstance(row.get("size"), bool)
            or not isinstance(row.get("size"), int)
            or row["size"] < 0
        ):
            raise CapacityHostArtifactError("TRANSPORT_MATERIAL_ROW_INVALID")
    return dict(value)


def _validate_transport_v2_zip_layout(
    descriptor: int,
    infos: Sequence[zipfile.ZipInfo],
    *,
    manifest_bytes: bytes,
    payload_crc32: int,
) -> None:
    if [info.filename for info in infos] != ["manifest.json", "payload.pack"]:
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_INVENTORY_INVALID")
    crcs = (zlib.crc32(manifest_bytes) & 0xFFFFFFFF, payload_crc32)
    local_offset = 0
    central_records: list[bytes] = []
    for info, expected_crc in zip(infos, crcs):
        name = info.filename.encode("ascii")
        _require_v2_zip32_size(info.file_size)
        local_header = struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            0,
            zipfile.ZIP_STORED,
            0,
            33,
            expected_crc,
            info.file_size,
            info.file_size,
            len(name),
            0,
        ) + name
        if info.header_offset != local_offset or os.pread(
            descriptor, len(local_header), local_offset
        ) != local_header:
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")
        data_offset = local_offset + len(local_header)
        if info.filename == "manifest.json" and os.pread(
            descriptor, len(manifest_bytes), data_offset
        ) != manifest_bytes:
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")
        central_records.append(
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                (3 << 8) | 20,
                20,
                0,
                zipfile.ZIP_STORED,
                0,
                33,
                expected_crc,
                info.file_size,
                info.file_size,
                len(name),
                0,
                0,
                0,
                0,
                (stat.S_IFREG | 0o400) << 16,
                local_offset,
            )
            + name
        )
        local_offset = data_offset + info.file_size
    central = b"".join(central_records)
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(infos),
        len(infos),
        len(central),
        local_offset,
        0,
    )
    expected_tail = central + eocd
    before = os.fstat(descriptor)
    if (
        os.pread(descriptor, len(expected_tail), local_offset) != expected_tail
        or before.st_size != local_offset + len(expected_tail)
    ):
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_NONCANONICAL")


def _stream_zip_member(
    archive: zipfile.ZipFile, name: str, destination: Path
) -> tuple[str, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, 0o400)
    digest = hashlib.sha256()
    crc32 = 0
    try:
        with archive.open(name, "r") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                crc32 = zlib.crc32(chunk, crc32)
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise CapacityHostArtifactError("SHORT_WRITE")
                    view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return digest.hexdigest(), crc32 & 0xFFFFFFFF


def extract_source_transport_v2(
    archive_path: Path,
    destination: Path,
    *,
    expected_commit: str,
) -> dict[str, Any]:
    """Stream and validate the exact two-member complete transport."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    archive_descriptor = os.open(archive_path, flags)
    archive_info = os.fstat(archive_descriptor)
    if not stat.S_ISREG(archive_info.st_mode) or archive_info.st_nlink != 1 or (
        stat.S_IMODE(archive_info.st_mode) & 0o022
    ):
        os.close(archive_descriptor)
        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_FILE_INVALID")
    destination_created = False
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        destination_created = True
        with os.fdopen(os.dup(archive_descriptor), "rb") as raw:
            with zipfile.ZipFile(raw, "r") as archive:
                infos = archive.infolist()
                if [info.filename for info in infos] != ["manifest.json", "payload.pack"]:
                    raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_INVENTORY_INVALID")
                for info in infos:
                    mode = info.external_attr >> 16
                    if (
                        info.date_time != (1980, 1, 1, 0, 0, 0)
                        or info.create_system != 3
                        or not stat.S_ISREG(mode)
                        or stat.S_IMODE(mode) != 0o400
                        or info.flag_bits != 0
                        or info.compress_type != zipfile.ZIP_STORED
                        or info.compress_size != info.file_size
                        or info.extra != b""
                        or info.comment != b""
                    ):
                        raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_MEMBER_INVALID")
                    _require_v2_zip32_size(info.file_size)
                with archive.open("manifest.json", "r") as manifest_source:
                    manifest_bytes = manifest_source.read(_V2_MANIFEST_MAX_BYTES + 1)
                if len(manifest_bytes) > _V2_MANIFEST_MAX_BYTES:
                    raise CapacityHostArtifactError("TRANSPORT_MANIFEST_TOO_LARGE")
                manifest = validate_transport_manifest_v2(
                    json.loads(manifest_bytes), expected_commit=expected_commit
                )
                if manifest_bytes != canonical_json(manifest):
                    raise CapacityHostArtifactError("TRANSPORT_MANIFEST_NONCANONICAL")
                _write_bytes_exclusive(destination / "manifest.json", manifest_bytes, 0o400)
                observed_payload, payload_crc32 = _stream_zip_member(
                    archive, "payload.pack", destination / "payload.pack"
                )
                _validate_transport_v2_zip_layout(
                    archive_descriptor,
                    infos,
                    manifest_bytes=manifest_bytes,
                    payload_crc32=payload_crc32,
                )
        after = os.fstat(archive_descriptor)
        if _descriptor_directory_state(archive_info) != _descriptor_directory_state(after):
            raise CapacityHostArtifactError("TRANSPORT_ARCHIVE_FILE_INVALID")
        if observed_payload != manifest["payload_sha256"]:
            raise CapacityHostArtifactError("TRANSPORT_PAYLOAD_DIGEST_MISMATCH")
        _validate_pack_file(
            destination / "payload.pack", expected_count=manifest["object_count"]
        )
        return manifest
    except Exception:
        if destination_created and destination.exists():
            for child in destination.iterdir():
                child.unlink(missing_ok=True)
            destination.rmdir()
        raise
    finally:
        os.close(archive_descriptor)


def _run_git_file_input(repository: Path, input_path: Path, *arguments: str) -> bytes:
    with input_path.open("rb") as source:
        completed = subprocess.run(
            ["/usr/bin/git", "--no-replace-objects", "-C", os.fspath(repository), *arguments],
            stdin=source,
            capture_output=True,
            check=False,
            env=_git_environment(),
        )
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_MATERIALIZATION_REFUSED")
    return completed.stdout


def _normalize_complete_repository_modes(source_root: Path) -> None:
    executable_paths = {
        os.fspath(source_root / str(row))
        for row in PRODUCER_MATERIAL_PATHS
        if str(row).startswith("scripts/")
    }
    for current, directory_names, file_names in os.walk(
        source_root, topdown=False, followlinks=False
    ):
        current_path = Path(current)
        for name in file_names:
            path = current_path / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            path.chmod(0o555 if os.fspath(path) in executable_paths else 0o444)
        for name in directory_names:
            path = current_path / name
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            path.chmod(0o555)
    source_root.chmod(0o555)


def _read_verified_metadata_file(
    path: Path, *, expected_uid: int, expected_gid: int, maximum_bytes: int
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or stat.S_IMODE(info.st_mode) != 0o444
            or int(getattr(info, "st_flags", 0)) != _ALLOWED_BSD_FLAGS
            or _descriptor_extended_attribute_names(descriptor) - _APPROVED_SYSTEM_XATTRS
            or _descriptor_has_extended_acl(descriptor)
        ):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        return _read_descriptor(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)


def _refuse_optional_lock(path: Path) -> None:
    if _path_lstat(path.with_name(f"{path.name}.lock")) is not None:
        raise CapacityHostArtifactError("SOURCE_METADATA_LOCK_PRESENT")


def _repository_snapshot_state(info: os.stat_result) -> tuple[int, ...]:
    return _descriptor_directory_state(info) + (info.st_size,)


class _RepositoryView:
    """One retained graph and semantic read capability for preserved evidence."""

    _NATIVE_ROOT_ALIASES = {
        "var": "private/var",
        "tmp": "private/tmp",
    }

    def __init__(
        self,
        source_root: Path,
        *,
        parent_descriptor: int | None = None,
        root_name: str | None = None,
        allow_symlinks: bool = False,
        recursive: bool = True,
    ) -> None:
        absolute = source_root.absolute()
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        self.allow_symlinks = allow_symlinks
        self.recursive = recursive
        self.descriptors: dict[str, int] = {}
        self.states: dict[str, tuple[int, ...]] = {}
        self.xattr_states: dict[str, frozenset[bytes]] = {}
        self.directory_names: dict[str, tuple[str, ...]] = {}
        self.parents: dict[str, tuple[str, str]] = {}
        self.guard_descriptors: list[int] = []
        self.guard_names: list[str] = []
        self.guard_states: list[tuple[int, ...]] = []
        self.guard_xattr_states: list[frozenset[bytes]] = []
        self.guard_native_tmp: list[bool] = []
        self.alias_relations: list[
            tuple[int, str, int, tuple[int, ...], frozenset[bytes], str]
        ] = []
        self.parent_descriptor: int | None = None
        self.parent_state: tuple[int, ...] | None = None
        self.parent_xattr_state: frozenset[bytes] | None = None
        self.explicit_parent = parent_descriptor is not None
        try:
            if parent_descriptor is not None:
                self.parent_descriptor = os.dup(parent_descriptor)
                parent_info = os.fstat(self.parent_descriptor)
                if not stat.S_ISDIR(parent_info.st_mode):
                    raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
                parent_xattrs = _descriptor_extended_attribute_names(
                    self.parent_descriptor
                )
                _require_allowed_bsd_flags(parent_info, "SOURCE_METADATA_INVALID")
                if (
                    parent_xattrs - _APPROVED_SYSTEM_XATTRS
                    or _descriptor_has_extended_acl(self.parent_descriptor)
                ):
                    raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
                self.parent_state = _repository_snapshot_state(parent_info)
                self.parent_xattr_state = parent_xattrs
                actual_root_name = root_name if root_name is not None else absolute.name
            else:
                components = list(absolute.parts[1:])
                if not components:
                    raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
                root_guard = os.open("/", directory_flags)
                self._retain_guard(root_guard, "/", relation_parent=None)
                alias_target = self._NATIVE_ROOT_ALIASES.get(components[0])
                native_alias_name: str | None = None
                if alias_target is not None:
                    alias_info = os.stat(
                        components[0],
                        dir_fd=root_guard,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(alias_info.st_mode):
                        alias_descriptor = _open_release_symlink(
                            root_guard, components[0]
                        )
                        alias_state = _release_object_state(
                            os.fstat(alias_descriptor)
                        )
                        alias_xattrs = _descriptor_extended_attribute_names(
                            alias_descriptor
                        )
                        target = os.readlink(components[0], dir_fd=root_guard)
                        if (
                            target != alias_target
                            or alias_state
                            != _release_object_state(alias_info)
                            or alias_info.st_uid != 0
                            or stat.S_IMODE(alias_info.st_mode) & 0o022
                            or alias_info.st_nlink != 1
                            or int(getattr(alias_info, "st_flags", 0))
                            & ~_TRAVERSAL_ANCESTOR_ALLOWED_FLAGS
                            or alias_xattrs
                            - _APPROVED_TRAVERSAL_ANCESTOR_XATTRS
                            or _descriptor_has_extended_acl(alias_descriptor)
                        ):
                            os.close(alias_descriptor)
                            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
                        self.alias_relations.append(
                            (
                                root_guard,
                                components[0],
                                alias_descriptor,
                                alias_state,
                                alias_xattrs,
                                target,
                            )
                        )
                        native_alias_name = components[0]
                        components = [*PurePosixPath(target).parts, *components[1:]]
                actual_root_name = components[-1]
                for component_index, component in enumerate(components[:-1]):
                    observed = os.stat(
                        component,
                        dir_fd=self.guard_descriptors[-1],
                        follow_symlinks=False,
                    )
                    if not stat.S_ISDIR(observed.st_mode):
                        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
                    child = os.open(
                        component,
                        directory_flags,
                        dir_fd=self.guard_descriptors[-1],
                    )
                    self._retain_guard(
                        child,
                        component,
                        relation_parent=self.guard_descriptors[-1],
                        observed=observed,
                        native_tmp=(
                            native_alias_name == "tmp"
                            and component_index == 1
                            and component == "tmp"
                        ),
                    )
                self.parent_descriptor = os.dup(self.guard_descriptors[-1])

            if (
                not isinstance(actual_root_name, str)
                or not actual_root_name
                or actual_root_name in {".", ".."}
                or "/" in actual_root_name
            ):
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            self.root_name = actual_root_name
            relation_info = os.stat(
                self.root_name,
                dir_fd=self.parent_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISDIR(relation_info.st_mode):
                root_descriptor = os.open(
                    self.root_name,
                    directory_flags,
                    dir_fd=self.parent_descriptor,
                )
            elif allow_symlinks and stat.S_ISLNK(relation_info.st_mode):
                root_descriptor = _open_release_symlink(
                    self.parent_descriptor, self.root_name
                )
            else:
                root_descriptor = os.open(
                    self.root_name,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=self.parent_descriptor,
                )
            self.root_descriptor = root_descriptor
            self._retain(".", root_descriptor)
            self.root_relation_state = self.states["."]
            if _repository_snapshot_state(relation_info) != self.root_relation_state:
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        except Exception:
            self.close()
            raise

    def _retain_guard(
        self,
        descriptor: int,
        name: str,
        *,
        relation_parent: int | None,
        observed: os.stat_result | None = None,
        native_tmp: bool = False,
    ) -> None:
        info = os.fstat(descriptor)
        root_device = (
            info.st_dev
            if not self.guard_descriptors
            else os.fstat(self.guard_descriptors[0]).st_dev
        )
        self.guard_descriptors.append(descriptor)
        if native_tmp:
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_nlink < 1
                or info.st_dev != root_device
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o1777
                or int(getattr(info, "st_flags", 0))
                & ~_TRAVERSAL_ANCESTOR_ALLOWED_FLAGS
                or _descriptor_has_extended_acl(descriptor)
            ):
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        else:
            _require_source_repair_ancestor(
                descriptor,
                info,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
                expected_device=root_device,
                reason="SOURCE_METADATA_INVALID",
            )
        xattrs = _source_repair_ancestor_xattrs(
            descriptor, reason="SOURCE_METADATA_INVALID"
        )
        state = _descriptor_ancestor_state(info)
        if observed is not None and _descriptor_ancestor_state(observed) != state:
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self.guard_names.append(name)
        self.guard_states.append(state)
        self.guard_xattr_states.append(xattrs)
        self.guard_native_tmp.append(native_tmp)

    def _retain(self, relative: str, descriptor: int) -> None:
        self.descriptors[relative] = descriptor
        info = os.fstat(descriptor)
        if not (
            stat.S_ISDIR(info.st_mode)
            or stat.S_ISREG(info.st_mode)
            or (self.allow_symlinks and stat.S_ISLNK(info.st_mode))
        ):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        traversal_root = relative == "." and not self.recursive and stat.S_ISDIR(
            info.st_mode
        )
        if traversal_root:
            expected_device = (
                os.fstat(self.guard_descriptors[0]).st_dev
                if self.guard_descriptors
                else info.st_dev
            )
            _require_source_repair_ancestor(
                descriptor,
                info,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
                expected_device=expected_device,
                reason="SOURCE_METADATA_INVALID",
            )
            xattrs = _source_repair_ancestor_xattrs(
                descriptor, reason="SOURCE_METADATA_INVALID"
            )
        else:
            xattrs = _descriptor_extended_attribute_names(descriptor)
            _require_allowed_bsd_flags(info, "SOURCE_METADATA_INVALID")
            if (
                xattrs - _APPROVED_SYSTEM_XATTRS
                or _descriptor_has_extended_acl(descriptor)
            ):
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self.states[relative] = _repository_snapshot_state(info)
        self.xattr_states[relative] = xattrs
        if not stat.S_ISDIR(info.st_mode):
            return
        names = tuple(_descriptor_directory_names(descriptor))
        self.directory_names[relative] = names
        if not self.recursive:
            return
        for name in names:
            child = name if relative == "." else f"{relative}/{name}"
            child_info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not (
                stat.S_ISDIR(child_info.st_mode)
                or stat.S_ISREG(child_info.st_mode)
                or (self.allow_symlinks and stat.S_ISLNK(child_info.st_mode))
            ):
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
            if stat.S_ISLNK(child_info.st_mode):
                child_descriptor = _open_release_symlink(descriptor, name)
            else:
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                )
                if stat.S_ISDIR(child_info.st_mode):
                    flags |= getattr(os, "O_DIRECTORY", 0)
                else:
                    flags |= getattr(os, "O_NONBLOCK", 0)
                child_descriptor = os.open(name, flags, dir_fd=descriptor)
            self.parents[child] = (relative, name)
            self._retain(child, child_descriptor)
            if _repository_snapshot_state(child_info) != self.states[child]:
                raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")

    def _revalidate_parent_capability(self) -> None:
        if self.parent_descriptor is None:
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        if self.explicit_parent:
            parent_info = os.fstat(self.parent_descriptor)
            parent_xattrs = _descriptor_extended_attribute_names(
                self.parent_descriptor
            )
            if (
                self.parent_state is None
                or _repository_snapshot_state(parent_info) != self.parent_state
                or self.parent_xattr_state is None
                or parent_xattrs != self.parent_xattr_state
            ):
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
            _require_allowed_bsd_flags(parent_info, "SOURCE_VIEW_DRIFT")
            if _descriptor_has_extended_acl(self.parent_descriptor):
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        for index, descriptor in enumerate(self.guard_descriptors):
            info = os.fstat(descriptor)
            if (
                _descriptor_ancestor_state(info) != self.guard_states[index]
                or _descriptor_extended_attribute_names(descriptor)
                != self.guard_xattr_states[index]
            ):
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
            if self.guard_native_tmp[index]:
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or info.st_nlink < 1
                    or info.st_dev != os.fstat(self.guard_descriptors[0]).st_dev
                    or info.st_uid != 0
                    or info.st_gid != 0
                    or stat.S_IMODE(info.st_mode) != 0o1777
                    or int(getattr(info, "st_flags", 0))
                    & ~_TRAVERSAL_ANCESTOR_ALLOWED_FLAGS
                    or _descriptor_has_extended_acl(descriptor)
                ):
                    raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
            else:
                _require_source_repair_ancestor(
                    descriptor,
                    info,
                    expected_uid=os.geteuid(),
                    expected_gid=os.getegid(),
                    expected_device=os.fstat(self.guard_descriptors[0]).st_dev,
                    reason="SOURCE_VIEW_DRIFT",
                )
            if index:
                observed_guard = os.stat(
                    self.guard_names[index],
                    dir_fd=self.guard_descriptors[index - 1],
                    follow_symlinks=False,
                )
                if _descriptor_ancestor_state(observed_guard) != self.guard_states[index]:
                    raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        for parent, name, descriptor, state, xattrs, target in self.alias_relations:
            observed = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (
                _release_object_state(observed) != state
                or _release_object_state(os.fstat(descriptor)) != state
                or _descriptor_extended_attribute_names(descriptor) != xattrs
                or _descriptor_has_extended_acl(descriptor)
                or os.readlink(name, dir_fd=parent) != target
            ):
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")

    def _revalidate_object(self, relative: str, seen: set[str] | None = None) -> None:
        if seen is None:
            seen = set()
        if relative in seen:
            return
        seen.add(relative)
        descriptor = self.descriptors.get(relative)
        if descriptor is None:
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        info = os.fstat(descriptor)
        object_xattrs = _descriptor_extended_attribute_names(descriptor)
        if (
            _repository_snapshot_state(info) != self.states[relative]
            or object_xattrs != self.xattr_states[relative]
        ):
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        if relative == "." and not self.recursive and stat.S_ISDIR(info.st_mode):
            expected_device = (
                os.fstat(self.guard_descriptors[0]).st_dev
                if self.guard_descriptors
                else info.st_dev
            )
            _require_source_repair_ancestor(
                descriptor,
                info,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
                expected_device=expected_device,
                reason="SOURCE_VIEW_DRIFT",
            )
        else:
            _require_allowed_bsd_flags(info, "SOURCE_VIEW_DRIFT")
            if _descriptor_has_extended_acl(descriptor):
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        if relative in self.directory_names and tuple(
            _descriptor_directory_names(descriptor)
        ) != self.directory_names[relative]:
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
        relation = self.parents.get(relative)
        if relation is None:
            self._revalidate_parent_capability()
            observed = os.stat(
                self.root_name,
                dir_fd=self.parent_descriptor,
                follow_symlinks=False,
            )
            if _repository_snapshot_state(observed) != self.root_relation_state:
                raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")
            return
        parent, name = relation
        self._revalidate_object(parent, seen)
        observed = os.stat(
            name,
            dir_fd=self.descriptors[parent],
            follow_symlinks=False,
        )
        if _repository_snapshot_state(observed) != self.states[relative]:
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT")

    def read_bytes(self, relative: str, *, maximum_bytes: int) -> bytes:
        """Read one retained regular file and revalidate its complete relation."""

        if (
            isinstance(maximum_bytes, bool)
            or not isinstance(maximum_bytes, int)
            or maximum_bytes < 0
        ):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        descriptor = self.descriptors.get(relative)
        if descriptor is None or not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self._revalidate_object(relative)
        payload = _read_descriptor(descriptor, maximum_bytes)
        if len(payload) > maximum_bytes:
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self._revalidate_object(relative)
        return payload

    def sha256(self, relative: str) -> str:
        """Hash one retained regular file without reopening its pathname."""

        descriptor = self.descriptors.get(relative)
        if descriptor is None or not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self._revalidate_object(relative)
        digest = _descriptor_sha256(descriptor)
        self._revalidate_object(relative)
        return digest

    def readlink(self, relative: str) -> str:
        """Read one retained release symlink through its retained parent."""

        descriptor = self.descriptors.get(relative)
        relation = self.parents.get(relative)
        if (
            descriptor is None
            or relation is None
            or not stat.S_ISLNK(os.fstat(descriptor).st_mode)
        ):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        parent, name = relation
        self._revalidate_object(relative)
        target = os.readlink(name, dir_fd=self.descriptors[parent])
        self._revalidate_object(relative)
        return target

    def is_absent(self, name: str) -> bool:
        """Prove a simple child name absent through this retained directory root."""

        if (
            name in {"", ".", ".."}
            or "/" in name
            or "." not in self.directory_names
        ):
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self._revalidate_object(".")
        if name in self.directory_names["."]:
            return False
        try:
            os.stat(name, dir_fd=self.root_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            return False
        self._revalidate_object(".")
        return True

    def contains(self, name: str) -> bool:
        if name in {"", ".", ".."} or "/" in name:
            raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
        self._revalidate_object(".")
        return name in self.directory_names.get(".", ())

    def revalidate(self) -> None:
        try:
            self._revalidate_parent_capability()
            seen: set[str] = set()
            for relative in self.descriptors:
                self._revalidate_object(relative, seen)
        except CapacityHostArtifactError:
            raise
        except (OSError, UnicodeError) as exc:
            raise CapacityHostArtifactError("SOURCE_VIEW_DRIFT") from exc

    def close(self) -> None:
        for descriptor in getattr(self, "descriptors", {}).values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.descriptors = {}
        parent_descriptor = getattr(self, "parent_descriptor", None)
        if parent_descriptor is not None:
            try:
                os.close(parent_descriptor)
            except OSError:
                pass
        self.parent_descriptor = None
        for relation in reversed(getattr(self, "alias_relations", [])):
            try:
                os.close(relation[2])
            except OSError:
                pass
        self.alias_relations = []
        for descriptor in reversed(getattr(self, "guard_descriptors", [])):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.guard_descriptors = []


def verify_repair_carrier(
    carrier_root: Path,
    *,
    expected_commit: str,
    expected_uid: int,
    expected_gid: int,
) -> dict[str, Any]:
    """Authenticate the root-created executable carrier through retained FDs."""

    if (
        _COMMIT_RE.fullmatch(expected_commit) is None
        or expected_uid < 0
        or expected_gid < 0
    ):
        raise CapacityHostArtifactError("REPAIR_CARRIER_INVALID")
    view = _RepositoryView(carrier_root)
    try:
        expected_paths = {
            ".",
            ".repair-carrier-commit",
            "ops",
            "ops/executive_os",
            *_REPAIR_CARRIER_FILES.keys(),
        }
        if set(view.descriptors) != expected_paths:
            raise CapacityHostArtifactError("REPAIR_CARRIER_INVALID")
        for relative, descriptor in view.descriptors.items():
            info = os.fstat(descriptor)
            expected_mode = (
                0o700
                if stat.S_ISDIR(info.st_mode)
                else _REPAIR_CARRIER_FILES.get(relative)
            )
            if (
                info.st_uid != expected_uid
                or info.st_gid != expected_gid
                or expected_mode is None
                or stat.S_IMODE(info.st_mode) != expected_mode
                or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
                or _descriptor_extended_attribute_names(descriptor)
                - _APPROVED_SYSTEM_XATTRS
                or _descriptor_has_extended_acl(descriptor)
            ):
                raise CapacityHostArtifactError("REPAIR_CARRIER_INVALID")
            _require_allowed_bsd_flags(info, "REPAIR_CARRIER_INVALID")
        stamp = _read_descriptor(
            view.descriptors[".repair-carrier-commit"], 41
        )
        if stamp != f"{expected_commit}\n".encode("ascii"):
            raise CapacityHostArtifactError("REPAIR_CARRIER_INVALID")
        view.revalidate()
        return {
            "commit_sha": expected_commit,
            "verified_file_count": len(_REPAIR_CARRIER_FILES),
        }
    except CapacityHostArtifactError:
        raise
    except (OSError, UnicodeError) as exc:
        raise CapacityHostArtifactError("REPAIR_CARRIER_INVALID") from exc
    finally:
        view.close()


def _run_git_v2(
    view: _RepositoryView,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    view.revalidate()
    root_descriptor = view.root_descriptor

    def enter_retained_root() -> None:
        os.fchdir(root_descriptor)

    completed = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_git_environment(),
        pass_fds=(root_descriptor,),
        preexec_fn=enter_retained_root,
    )
    view.revalidate()
    if completed.returncode != 0:
        raise CapacityHostArtifactError("GIT_MATERIALIZATION_REFUSED")
    return completed.stdout


def _inspect_complete_repository_direct(
    source_root: Path, manifest: Mapping[str, Any], view: _RepositoryView
) -> tuple[str, str]:
    view.revalidate()
    root_info = os.fstat(view.root_descriptor)
    if not stat.S_ISDIR(root_info.st_mode):
        raise CapacityHostArtifactError("SOURCE_ROOT_INVALID")
    expected_uid = root_info.st_uid
    expected_gid = root_info.st_gid
    if any(PurePosixPath(relative).name.endswith(".lock") for relative in view.states):
        raise CapacityHostArtifactError("SOURCE_METADATA_LOCK_PRESENT")
    if view.directory_names.get(".git/hooks") != ():
        raise CapacityHostArtifactError("SOURCE_HOOK_PRESENT")
    if view.directory_names.get(".git/objects") != ("info", "pack"):
        raise CapacityHostArtifactError("SOURCE_OBJECT_NAMESPACE_INVALID")
    if view.directory_names.get(".git/objects/info") != ():
        raise CapacityHostArtifactError("SOURCE_OBJECT_NAMESPACE_INVALID")
    expected_info_names = ("exclude", "sparse-checkout")
    if view.directory_names.get(".git/info") != expected_info_names:
        raise CapacityHostArtifactError("SOURCE_METADATA_INVALID")
    git_dir = source_root / ".git"
    config = git_dir / "config"
    worktree_config = git_dir / "config.worktree"
    index = git_dir / "index"
    head = git_dir / "HEAD"
    stored_manifest = git_dir / "cf2-h0-transport-manifest.json"
    for path in (config, worktree_config, index, head, stored_manifest):
        _refuse_optional_lock(path)
    if _read_verified_metadata_file(
        config,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=64 * 1024,
    ) != _V2_CONFIG:
        raise CapacityHostArtifactError("SOURCE_CONFIG_INVALID")
    if _read_verified_metadata_file(
        worktree_config,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=64 * 1024,
    ) != _V2_WORKTREE_CONFIG:
        raise CapacityHostArtifactError("SOURCE_CONFIG_INVALID")
    if _read_verified_metadata_file(
        stored_manifest,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=_V2_MANIFEST_MAX_BYTES,
    ) != canonical_json(manifest):
        raise CapacityHostArtifactError("SOURCE_MANIFEST_MISMATCH")
    if _read_verified_metadata_file(
        git_dir / "info" / "sparse-checkout",
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        maximum_bytes=len(_V2_SPARSE_CHECKOUT),
    ) != _V2_SPARSE_CHECKOUT:
        raise CapacityHostArtifactError("SOURCE_SPARSE_CHECKOUT_INVALID")

    alternates = git_dir / "objects" / "info" / "alternates"
    shallow = git_dir / "shallow"
    grafts = git_dir / "info" / "grafts"
    packed_refs = git_dir / "packed-refs"
    for path in (alternates, shallow, grafts, packed_refs):
        _refuse_optional_lock(path)
    if _path_lstat(alternates) is not None:
        raise CapacityHostArtifactError("SOURCE_ALTERNATES_PRESENT")
    if _path_lstat(shallow) is not None:
        raise CapacityHostArtifactError("SOURCE_SHALLOW_PRESENT")
    if _path_lstat(grafts) is not None:
        graft_bytes = _read_verified_metadata_file(
            grafts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            maximum_bytes=16 * 1024 * 1024,
        )
        if any(line.strip() and not line.lstrip().startswith(b"#") for line in graft_bytes.splitlines()):
            raise CapacityHostArtifactError("SOURCE_GRAFT_PRESENT")
    if _path_lstat(packed_refs) is not None:
        packed_bytes = _read_verified_metadata_file(
            packed_refs,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            maximum_bytes=16 * 1024 * 1024,
        )
        if b"refs/replace/" in packed_bytes:
            raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
    replace_dir = git_dir / "refs" / "replace"
    replace_info = _path_lstat(replace_dir)
    if replace_info is not None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(replace_dir, flags)
        try:
            if _descriptor_directory_names(descriptor):
                raise CapacityHostArtifactError("SOURCE_REPLACEMENT_REF_PRESENT")
        finally:
            os.close(descriptor)

    pack_dir = git_dir / "objects" / "pack"
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        pack_descriptor = os.open(pack_dir, flags)
    except OSError as exc:
        raise CapacityHostArtifactError("SOURCE_PACK_INSTALL_INVALID") from exc
    try:
        pack_names = _descriptor_directory_names(pack_descriptor)
    finally:
        os.close(pack_descriptor)
    if any(name.endswith((".promisor", ".lock")) for name in pack_names):
        raise CapacityHostArtifactError("SOURCE_PROMISOR_OR_LOCK_PRESENT")
    packs = [name for name in pack_names if re.fullmatch(r"pack-[0-9a-f]{40}\.pack", name)]
    indexes = [name for name in pack_names if re.fullmatch(r"pack-[0-9a-f]{40}\.idx", name)]
    if (
        len(packs) != 1
        or len(indexes) != 1
        or packs[0][:-5] != indexes[0][:-4]
        or set(pack_names) != {packs[0], indexes[0]}
    ):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    pack_path = pack_dir / packs[0]
    index_path = pack_dir / indexes[0]
    _refuse_optional_lock(pack_path)
    _refuse_optional_lock(index_path)
    _validate_pack_file(pack_path, expected_count=int(manifest["object_count"]))
    view.revalidate()
    return (
        f".git/objects/pack/{packs[0]}",
        f".git/objects/pack/{indexes[0]}",
    )


def _pack_inventory(repository: Path, index_path: Path) -> tuple[ObjectInventoryRow, ...]:
    output = _run_git(repository, "verify-pack", "-v", os.fspath(index_path)).decode(
        "ascii", "strict"
    )
    object_ids: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or _OBJECT_RE.fullmatch(fields[0]) is None:
            continue
        if len(fields) < 3 or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        object_ids.append(fields[0])
    ordered_ids = sorted(object_ids)
    if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    checked = _run_git(
        repository,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(ordered_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    if len(checked) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    rows: list[ObjectInventoryRow] = []
    for expected_oid, line in zip(ordered_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID") from exc
        if size < 0:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _pack_inventory_v2(
    view: _RepositoryView, index_path: str
) -> tuple[ObjectInventoryRow, ...]:
    output = _run_git_v2(view, "verify-pack", "-v", index_path).decode(
        "ascii", "strict"
    )
    object_ids: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or _OBJECT_RE.fullmatch(fields[0]) is None:
            continue
        if len(fields) < 3 or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        object_ids.append(fields[0])
    ordered_ids = sorted(object_ids)
    if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    checked = _run_git_v2(
        view,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(ordered_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    rows: list[ObjectInventoryRow] = []
    if len(checked) != len(ordered_ids):
        raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
    for expected_oid, line in zip(ordered_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID") from exc
        if size < 0 or str(size) != fields[2]:
            raise CapacityHostArtifactError("SOURCE_PACK_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _enumerate_reachable_objects_v2(
    view: _RepositoryView, commit: str
) -> tuple[ObjectInventoryRow, ...]:
    if _COMMIT_RE.fullmatch(commit) is None:
        raise CapacityHostArtifactError("COMMIT_INVALID")
    observed = _run_git_v2(view, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if observed != commit:
        raise CapacityHostArtifactError("COMMIT_MISMATCH")
    raw_objects = _run_git_v2(
        view,
        "rev-list",
        "--objects",
        "--no-object-names",
        "--missing=print",
        commit,
    ).decode("ascii", "strict").splitlines()
    if (
        not raw_objects
        or any(value.startswith("?") for value in raw_objects)
        or any(_OBJECT_RE.fullmatch(value) is None for value in raw_objects)
        or len(set(raw_objects)) != len(raw_objects)
    ):
        raise CapacityHostArtifactError("OBJECT_CLOSURE_MISSING")
    object_ids = sorted(raw_objects)
    checked = _run_git_v2(
        view,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    ).decode("ascii", "strict").splitlines()
    if len(checked) != len(object_ids):
        raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
    rows: list[ObjectInventoryRow] = []
    for expected_oid, line in zip(object_ids, checked):
        fields = line.split(" ")
        if len(fields) != 3 or fields[0] != expected_oid or fields[1] not in _V2_PACK_TYPES:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        try:
            size = int(fields[2], 10)
        except ValueError as exc:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID") from exc
        if size < 0 or str(size) != fields[2]:
            raise CapacityHostArtifactError("OBJECT_INVENTORY_INVALID")
        rows.append(ObjectInventoryRow(expected_oid, fields[1], size))
    return tuple(rows)


def _observed_worktree_files_v2(view: _RepositoryView) -> list[str]:
    return sorted(
        (
            relative
            for relative, state in view.states.items()
            if relative != "."
            and not relative.startswith(".git/")
            and stat.S_ISREG(state[3])
        ),
        key=lambda value: value.encode("utf-8"),
    )


def _observed_worktree_files(source_root: Path) -> list[str]:
    output: list[str] = []
    for current, directory_names, file_names in os.walk(source_root, followlinks=False):
        if Path(current) == source_root and ".git" in directory_names:
            directory_names.remove(".git")
        relative_root = Path(current).relative_to(source_root)
        for name in file_names:
            relative = (relative_root / name).as_posix()
            output.append(relative)
    return sorted(output, key=lambda value: value.encode("utf-8"))


def verify_complete_repository(
    source_root: Path,
    manifest: Mapping[str, Any],
    *,
    retained_view: _RepositoryView | None = None,
) -> SourceClosureEvidence:
    """Descriptor-first proof of a direct, complete, sparse ordinary repository."""

    validated = validate_transport_manifest_v2(
        manifest, expected_commit=str(manifest.get("commit"))
    )
    owns_view = retained_view is None
    view = retained_view if retained_view is not None else _RepositoryView(source_root)
    try:
        root_info = os.fstat(view.root_descriptor)
        first_tree_digest = closed_tree_digest(
            source_root,
            expected_uid=root_info.st_uid,
            expected_gid=root_info.st_gid,
            _root_descriptor=view.root_descriptor,
        )
        view.revalidate()
        _pack_path, index_path = _inspect_complete_repository_direct(
            source_root, validated, view
        )
        commit = str(validated["commit"])
        if _run_git_v2(view, "rev-parse", "HEAD").decode().strip() != commit:
            raise CapacityHostArtifactError("SOURCE_HEAD_MISMATCH")
        if _run_git_v2(view, "branch", "--show-current").strip():
            raise CapacityHostArtifactError("SOURCE_HEAD_ATTACHED")
        if _run_git_v2(view, "remote").strip():
            raise CapacityHostArtifactError("SOURCE_REMOTE_PRESENT")
        _run_git_v2(view, "fsck", "--full", "--strict", "--no-progress")
        reachable = _enumerate_reachable_objects_v2(view, commit)
        packed = _pack_inventory_v2(view, index_path)
        if reachable != packed:
            raise CapacityHostArtifactError("SOURCE_PACK_OBJECT_SET_MISMATCH")
        if (
            len(reachable) != validated["object_count"]
            or _inventory_digest(reachable) != validated["object_inventory_sha256"]
        ):
            raise CapacityHostArtifactError("SOURCE_OBJECT_INVENTORY_MISMATCH")
        expected_paths = list(PRODUCER_MATERIAL_PATHS)
        if _observed_worktree_files_v2(view) != expected_paths:
            raise CapacityHostArtifactError("SOURCE_WORKTREE_INVENTORY_MISMATCH")
        for row in validated["material"]:
            relative = str(row["path"])
            descriptor = view.descriptors.get(relative)
            if descriptor is None:
                raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
            before = os.fstat(descriptor)
            expected_mode = 0o555 if row["mode"] == "100755" else 0o444
            observed_digest = _descriptor_sha256(descriptor)
            after = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != expected_mode
                or before.st_size != row["size"]
                or observed_digest != row["sha256"]
                or _repository_snapshot_state(before) != _repository_snapshot_state(after)
            ):
                raise CapacityHostArtifactError("SOURCE_WORKTREE_FILE_MISMATCH")
            observed_blob = _run_git_v2(
                view, "hash-object", "--no-filters", relative
            ).decode().strip()
            tree_line = _run_git_v2(
                view, "ls-tree", "-z", commit, "--", relative
            )
            if observed_blob != row["git_blob"] or (
                f" {row['git_blob']}\t".encode() not in tree_line
            ):
                raise CapacityHostArtifactError("SOURCE_GIT_BLOB_MISMATCH")
        if _run_git_v2(
            view, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            raise CapacityHostArtifactError("SOURCE_WORKTREE_DIRTY")
        final_tree_digest = closed_tree_digest(
            source_root,
            expected_uid=root_info.st_uid,
            expected_gid=root_info.st_gid,
            _root_descriptor=view.root_descriptor,
        )
        view.revalidate()
        if final_tree_digest != first_tree_digest:
            raise CapacityHostArtifactError("SOURCE_TREE_DRIFT")
        return validate_source_closure_evidence(
            SourceClosureEvidence(
                object_count=len(reachable),
                object_inventory_sha256=_inventory_digest(reachable),
                source_tree_sha256=final_tree_digest,
            )
        )
    finally:
        if owns_view:
            view.close()


def materialize_source_transport_v2(
    archive_path: Path,
    source_root: Path,
    *,
    expected_commit: str,
) -> dict[str, Any]:
    """Create one complete direct repository without inheriting operator Git state."""

    transport = source_root.with_name(f".{source_root.name}.transport-v2")
    if source_root.exists() or source_root.is_symlink() or transport.exists():
        raise CapacityHostArtifactError("SOURCE_DESTINATION_EXISTS")
    manifest = extract_source_transport_v2(
        archive_path, transport, expected_commit=expected_commit
    )
    try:
        source_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        _run_git(source_root, "init", "--quiet")
        hooks = source_root / ".git" / "hooks"
        for hook in hooks.iterdir():
            if not hook.is_file() or hook.is_symlink():
                raise CapacityHostArtifactError("SOURCE_DEFAULT_HOOK_INVENTORY_INVALID")
            hook.unlink()
        (source_root / ".git" / "config").write_bytes(_V2_CONFIG)
        (source_root / ".git" / "config.worktree").write_bytes(_V2_WORKTREE_CONFIG)
        pack_output = _run_git_file_input(
            source_root,
            transport / "payload.pack",
            "index-pack",
            "--stdin",
            "--fix-thin",
        ).decode("ascii", "strict").strip()
        match = re.fullmatch(r"(?:pack\s+)?([0-9a-f]{40})", pack_output)
        if match is None:
            raise CapacityHostArtifactError("SOURCE_PACK_IDENTITY_INVALID")
        pack_base = source_root / ".git" / "objects" / "pack" / f"pack-{match.group(1)}"
        if not pack_base.with_suffix(".pack").is_file() or not pack_base.with_suffix(".idx").is_file():
            raise CapacityHostArtifactError("SOURCE_PACK_INSTALL_INVALID")
        sparse = source_root / ".git" / "info" / "sparse-checkout"
        sparse.write_bytes(_V2_SPARSE_CHECKOUT)
        _run_git(source_root, "checkout", "--detach", expected_commit)
        (source_root / ".git" / "cf2-h0-transport-manifest.json").write_bytes(
            canonical_json(manifest)
        )
        _normalize_complete_repository_modes(source_root)
        verify_complete_repository(source_root, manifest)
        return manifest
    finally:
        if transport.exists():
            for child in transport.iterdir():
                child.unlink(missing_ok=True)
            transport.rmdir()


def _safe_wheel_member(info: zipfile.ZipInfo) -> PurePosixPath:
    candidate = PurePosixPath(info.filename)
    mode = info.external_attr >> 16
    if (
        candidate.is_absolute()
        or not candidate.parts
        or ".." in candidate.parts
        or "" in candidate.parts
        or not any(info.filename.startswith(prefix) for prefix in _WHEEL_PREFIXES)
    ):
        raise CapacityHostArtifactError("WHEEL_MEMBER_PATH_INVALID")
    kind = stat.S_IFMT(mode)
    if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise CapacityHostArtifactError("WHEEL_MEMBER_TYPE_INVALID")
    return candidate


def extract_pyyaml_wheel(wheel: Path, runtime_root: Path) -> Path:
    """Extract the pinned wheel with no pip, scripts, links, or archive modes."""

    site_packages = runtime_root / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with zipfile.ZipFile(wheel, "r") as archive:
        for info in archive.infolist():
            candidate = _safe_wheel_member(info)
            normalized = os.fspath(candidate)
            if normalized in seen:
                raise CapacityHostArtifactError("WHEEL_MEMBER_DUPLICATE")
            seen.add(normalized)
            target = site_packages.joinpath(*candidate.parts)
            if info.is_dir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
                continue
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            try:
                with archive.open(info, "r") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        os.write(descriptor, chunk)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    return site_packages


def verify_pyyaml_record(runtime_root: Path) -> str:
    site_packages = runtime_root / "lib" / "python3.12" / "site-packages"
    record = site_packages / "pyyaml-6.0.3.dist-info" / "RECORD"
    try:
        rows = list(csv.reader(record.read_text(encoding="utf-8").splitlines()))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CapacityHostArtifactError("PYYAML_RECORD_UNREADABLE") from exc
    declared: dict[str, tuple[str, str]] = {}
    for row in rows:
        if len(row) != 3 or row[0] in declared:
            raise CapacityHostArtifactError("PYYAML_RECORD_INVALID")
        path = PurePosixPath(row[0])
        if path.is_absolute() or ".." in path.parts or not any(row[0].startswith(prefix) for prefix in _WHEEL_PREFIXES):
            raise CapacityHostArtifactError("PYYAML_RECORD_PATH_INVALID")
        declared[row[0]] = (row[1], row[2])
    observed = {
        path.relative_to(site_packages).as_posix()
        for path in site_packages.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if observed != set(declared):
        raise CapacityHostArtifactError("PYYAML_RECORD_INVENTORY_MISMATCH")
    for relative, (encoded_hash, encoded_size) in declared.items():
        path = site_packages / relative
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CapacityHostArtifactError("PYYAML_RECORD_FILE_INVALID")
        if relative.endswith(".dist-info/RECORD") and not encoded_hash and not encoded_size:
            continue
        if not encoded_hash.startswith("sha256=") or not encoded_size.isdecimal():
            raise CapacityHostArtifactError("PYYAML_RECORD_HASH_INVALID")
        digest = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode("ascii")
        if digest != encoded_hash.removeprefix("sha256=") or info.st_size != int(encoded_size):
            raise CapacityHostArtifactError("PYYAML_RECORD_HASH_MISMATCH")
    for forbidden in ("sitecustomize.py", "usercustomize.py"):
        if (site_packages / forbidden).exists():
            raise CapacityHostArtifactError("RUNTIME_SITE_INJECTION_PRESENT")
    if any(site_packages.rglob("*.pth")):
        raise CapacityHostArtifactError("RUNTIME_PTH_PRESENT")
    return sha256_file(record)


def runtime_tree_digest(runtime_root: Path) -> str:
    rows: list[dict[str, Any]] = []
    paths = [runtime_root, *sorted(
        runtime_root.rglob("*"),
        key=lambda value: value.relative_to(runtime_root).as_posix(),
    )]
    for path in paths:
        info = path.lstat()
        relative = "." if path == runtime_root else path.relative_to(runtime_root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            raise CapacityHostArtifactError("RUNTIME_SYMLINK_PRESENT")
        if stat.S_ISDIR(info.st_mode):
            row: dict[str, Any] = {
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": info.st_nlink,
                "path": relative,
                "type": "directory",
            }
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            row = {
                "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                "nlink": 1,
                "path": relative,
                "sha256": sha256_file(path),
                "size": info.st_size,
                "type": "file",
            }
        else:
            raise CapacityHostArtifactError("RUNTIME_OBJECT_INVALID")
        rows.append(row)
    return hashlib.sha256(canonical_json(rows)).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or inspect inert CF2-H0 artifacts")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-source-transport")
    build.add_argument("--source-repository", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--commit", required=True)
    build.add_argument("--material-path", action="append", default=[])
    extract = commands.add_parser("extract-source-transport")
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--destination", type=Path, required=True)
    extract.add_argument("--commit", required=True)
    extract.add_argument("--material-path", action="append", default=[])
    materialize = commands.add_parser("materialize-source-transport")
    materialize.add_argument("--archive", type=Path, required=True)
    materialize.add_argument("--destination", type=Path, required=True)
    materialize.add_argument("--commit", required=True)
    materialize.add_argument("--material-path", action="append", default=[])
    verify_source = commands.add_parser("verify-materialized-source")
    verify_source.add_argument("--source-root", type=Path, required=True)
    verify_source.add_argument("--manifest", type=Path, required=True)
    verify_source.add_argument("--commit", required=True)
    verify_source.add_argument("--material-path", action="append", default=[])
    build_v2 = commands.add_parser("build-source-transport-v2")
    build_v2.add_argument("--source-repository", type=Path, required=True)
    build_v2.add_argument("--output", type=Path, required=True)
    build_v2.add_argument("--commit", required=True)
    extract_v2 = commands.add_parser("extract-source-transport-v2")
    extract_v2.add_argument("--archive", type=Path, required=True)
    extract_v2.add_argument("--destination", type=Path, required=True)
    extract_v2.add_argument("--commit", required=True)
    materialize_v2 = commands.add_parser("materialize-source-transport-v2")
    materialize_v2.add_argument("--archive", type=Path, required=True)
    materialize_v2.add_argument("--destination", type=Path, required=True)
    materialize_v2.add_argument("--commit", required=True)
    verify_complete = commands.add_parser("verify-complete-repository")
    verify_complete.add_argument("--source-root", type=Path, required=True)
    verify_complete.add_argument("--manifest", type=Path, required=True)
    verify_complete.add_argument("--commit", required=True)
    verify_carrier = commands.add_parser("verify-repair-carrier")
    verify_carrier.add_argument("--path", type=Path, required=True)
    verify_carrier.add_argument("--expected-commit", required=True)
    verify_carrier.add_argument("--expected-uid", type=int, required=True)
    verify_carrier.add_argument("--expected-gid", type=int, required=True)
    repair_host = commands.add_parser("source-repair-host")
    repair_host.add_argument("--mode", choices=("repair", "verify-only"), required=True)
    repair_host.add_argument("--system-root", type=Path, required=True)
    repair_host.add_argument("--lock-file", type=Path, required=True)
    repair_host.add_argument("--expected-repair-commit", required=True)
    repair_host.add_argument("--expected-source-commit", required=True)
    repair_host.add_argument("--operator-uid", type=int)
    repair_host.add_argument("--operator-user")
    repair_host.add_argument("--transport", type=Path)
    repair_host.add_argument("--transport-sha256")
    repair_host.add_argument("--test-adapter", action="store_true")
    wheel = commands.add_parser("extract-pyyaml-wheel")
    wheel.add_argument("--wheel", type=Path, required=True)
    wheel.add_argument("--runtime-root", type=Path, required=True)
    runtime = commands.add_parser("verify-runtime-tree")
    runtime.add_argument("--runtime-root", type=Path, required=True)
    closed = commands.add_parser("copy-closed-input")
    closed.add_argument("--source", type=Path, required=True)
    closed.add_argument("--destination", type=Path, required=True)
    closed.add_argument("--operator-uid", type=int, required=True)
    closed.add_argument("--expected-sha256", required=True)
    recovery_intent = commands.add_parser("create-recovery-intent")
    recovery_intent.add_argument("--archive", type=Path, required=True)
    recovery_intent.add_argument("--expected-uid", type=int, required=True)
    recovery_intent.add_argument("--source", type=Path, action="append", default=[])
    recovery_resume = commands.add_parser("resume-recovery-archive")
    recovery_resume.add_argument("--archive", type=Path, required=True)
    recovery_resume.add_argument("--expected-uid", type=int, required=True)
    approved_xattrs = commands.add_parser("verify-approved-xattrs")
    approved_xattrs.add_argument("--path", type=Path, required=True)
    launchctl_disabled = commands.add_parser("check-launchctl-disabled")
    launchctl_disabled.add_argument("--label", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build-source-transport":
            value: Any = build_source_transport(
                args.source_repository,
                args.output,
                commit=args.commit,
                material_paths=tuple(args.material_path),
            )
        elif args.command == "extract-source-transport":
            value = extract_source_transport(
                args.archive,
                args.destination,
                expected_commit=args.commit,
                material_paths=tuple(args.material_path),
            )
        elif args.command == "materialize-source-transport":
            value = materialize_source_transport(
                args.archive,
                args.destination,
                expected_commit=args.commit,
                material_paths=tuple(args.material_path),
            )
        elif args.command == "verify-materialized-source":
            manifest = validate_transport_manifest(
                json.loads(args.manifest.read_text(encoding="utf-8")),
                expected_commit=args.commit,
                material_paths=tuple(args.material_path),
            )
            verify_materialized_source(args.source_root, manifest=manifest)
            value = manifest
        elif args.command == "build-source-transport-v2":
            value = build_source_transport_v2(
                args.source_repository,
                args.output,
                commit=args.commit,
            )
        elif args.command == "extract-source-transport-v2":
            value = extract_source_transport_v2(
                args.archive,
                args.destination,
                expected_commit=args.commit,
            )
        elif args.command == "materialize-source-transport-v2":
            value = materialize_source_transport_v2(
                args.archive,
                args.destination,
                expected_commit=args.commit,
            )
        elif args.command == "verify-complete-repository":
            manifest = validate_transport_manifest_v2(
                json.loads(_read_small_nofollow(args.manifest, _V2_MANIFEST_MAX_BYTES)),
                expected_commit=args.commit,
            )
            evidence = verify_complete_repository(args.source_root, manifest)
            value = {
                "object_count": evidence.object_count,
                "object_inventory_sha256": evidence.object_inventory_sha256,
                "source_tree_sha256": evidence.source_tree_sha256,
            }
        elif args.command == "verify-repair-carrier":
            value = verify_repair_carrier(
                args.path,
                expected_commit=args.expected_commit,
                expected_uid=args.expected_uid,
                expected_gid=args.expected_gid,
            )
        elif args.command == "source-repair-host":
            value = run_source_repair_host(
                mode=args.mode,
                system_root=args.system_root,
                lock_file=args.lock_file,
                expected_repair_commit=args.expected_repair_commit,
                expected_source_commit=args.expected_source_commit,
                operator_uid=args.operator_uid,
                operator_user=args.operator_user,
                transport=args.transport,
                transport_sha256=args.transport_sha256,
                test_adapter=args.test_adapter,
                crash_at=os.environ.get("MMX_CAPACITY_REPAIR_CRASH_AT")
                if args.test_adapter
                else None,
            )
        elif args.command == "extract-pyyaml-wheel":
            value = {"site_packages": str(extract_pyyaml_wheel(args.wheel, args.runtime_root))}
        elif args.command == "verify-runtime-tree":
            value = {
                "pyyaml_record_sha256": verify_pyyaml_record(args.runtime_root),
                "runtime_tree_sha256": runtime_tree_digest(args.runtime_root),
            }
        elif args.command == "copy-closed-input":
            value = copy_closed_input(
                args.source,
                args.destination,
                operator_uid=args.operator_uid,
                expected_sha256=args.expected_sha256,
            )
        elif args.command == "create-recovery-intent":
            value = create_recovery_intent(
                args.archive,
                tuple(args.source),
                expected_uid=args.expected_uid,
            )
        elif args.command == "resume-recovery-archive":
            value = resume_recovery_archive(
                args.archive,
                expected_uid=args.expected_uid,
            )
        elif args.command == "verify-approved-xattrs":
            value = verify_approved_xattrs(args.path)
        else:
            value = parse_launchctl_disabled(sys.stdin.read(256 * 1024 + 1), args.label)
    except SourceRepairIncomplete:
        return 70
    except BlockingIOError:
        return 75
    except CapacityHostArtifactError as exc:
        reason = str(exc)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", reason) is None:
            reason = type(exc).__name__
        print(f"capacity host artifact refused: {reason}", file=sys.stderr)
        return 65
    except (OSError, UnicodeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"capacity host artifact refused: {type(exc).__name__}", file=sys.stderr)
        return 65
    sys.stdout.write(canonical_json(value).decode("utf-8") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
