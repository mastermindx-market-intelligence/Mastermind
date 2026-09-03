"""Pure deterministic source-continuity contracts and verification.

This module performs no I/O, persistence, lifecycle mutation, watcher action,
Git operation, network request, release, merge, retry, or receiver transfer.
Its receipts are evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Mapping


RECEIPT_SCHEMA = "mastermind.source_continuity_receipt/v1"
REFUSAL_SCHEMA = "mastermind.source_continuity_refusal/v1"
RECEIPT_VERSION = "v1"
MAX_REMOTE_BLOB_BYTES = 10_000_000

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
)
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_VERIFIED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
_SAFE_BLOB_MODES = frozenset({"100644", "100755"})


class ReceiptKind(str, Enum):
    CHECKPOINT_VERIFIED = "CHECKPOINT_VERIFIED"
    REMOTE_COMPLETE_VERIFIED = "REMOTE_COMPLETE_VERIFIED"


class ExternalEffectState(str, Enum):
    NONE = "NONE"
    RECONCILED_NO_OPEN_EFFECT = "RECONCILED_NO_OPEN_EFFECT"
    OPEN_KNOWN_EFFECT = "OPEN_KNOWN_EFFECT"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class BranchEffectDependency(str, Enum):
    NONE = "NONE"
    SEPARABLE = "SEPARABLE"
    REQUIRED = "REQUIRED"
    UNKNOWN = "UNKNOWN"


class CollisionState(str, Enum):
    NONE = "NONE"
    DISJOINT = "DISJOINT"
    OVERLAP = "OVERLAP"
    INCOMPLETE = "INCOMPLETE"


class RefusalCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    REMOTE_IDENTITY_MISMATCH = "REMOTE_IDENTITY_MISMATCH"
    PR_NOT_OPEN = "PR_NOT_OPEN"
    PR_NOT_DRAFT_OR_HOLD = "PR_NOT_DRAFT_OR_HOLD"
    REMOTE_HEAD_EQUALS_PICKUP_BASE = "REMOTE_HEAD_EQUALS_PICKUP_BASE"
    REMOTE_CENSUS_INCOMPLETE = "REMOTE_CENSUS_INCOMPLETE"
    REMOTE_FACTS_INVALID = "REMOTE_FACTS_INVALID"
    PATH_OUTSIDE_OWNERSHIP = "PATH_OUTSIDE_OWNERSHIP"
    PATH_ENTRY_MISMATCH = "PATH_ENTRY_MISMATCH"
    UNSAFE_REMOTE_OBJECT = "UNSAFE_REMOTE_OBJECT"
    REMOTE_BLOB_TOO_LARGE = "REMOTE_BLOB_TOO_LARGE"
    LOCAL_FACTS_INVALID = "LOCAL_FACTS_INVALID"
    LOCAL_BRANCH_MISMATCH = "LOCAL_BRANCH_MISMATCH"
    REMOTE_HEAD_OBJECT_MISSING = "REMOTE_HEAD_OBJECT_MISSING"
    REMOTE_HEAD_NOT_ANCESTOR = "REMOTE_HEAD_NOT_ANCESTOR"
    OUT_OF_SCOPE_DIRT = "OUT_OF_SCOPE_DIRT"
    LOCAL_REMOTE_IDENTITY_MISMATCH = "LOCAL_REMOTE_IDENTITY_MISMATCH"
    UNPUSHED_COMMITS = "UNPUSHED_COMMITS"
    IN_SCOPE_DIRT = "IN_SCOPE_DIRT"
    EXTERNAL_EFFECT_INVALID = "EXTERNAL_EFFECT_INVALID"
    EXTERNAL_EFFECT_UNKNOWN = "EXTERNAL_EFFECT_UNKNOWN"
    BRANCH_EFFECT_REQUIRED = "BRANCH_EFFECT_REQUIRED"
    BRANCH_EFFECT_UNKNOWN = "BRANCH_EFFECT_UNKNOWN"
    AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
    LOCAL_PROBE_FAILED = "LOCAL_PROBE_FAILED"
    REMOTE_PROBE_FAILED = "REMOTE_PROBE_FAILED"
    REMOTE_PROOF_CHANGED = "REMOTE_PROOF_CHANGED"
    PROBE_INTERNAL_ERROR = "PROBE_INTERNAL_ERROR"


REFUSAL_MESSAGES: Mapping[RefusalCode, str] = {
    RefusalCode.INVALID_REQUEST: "input is invalid",
    RefusalCode.REMOTE_IDENTITY_MISMATCH: "remote identity does not match the request",
    RefusalCode.PR_NOT_OPEN: "target pull request is not open",
    RefusalCode.PR_NOT_DRAFT_OR_HOLD: "target pull request is not draft or hold",
    RefusalCode.REMOTE_HEAD_EQUALS_PICKUP_BASE: "remote head equals the pickup base",
    RefusalCode.REMOTE_CENSUS_INCOMPLETE: "remote proof census is incomplete",
    RefusalCode.REMOTE_FACTS_INVALID: "remote proof facts are invalid",
    RefusalCode.PATH_OUTSIDE_OWNERSHIP: "remote path is outside frozen ownership",
    RefusalCode.PATH_ENTRY_MISMATCH: "remote path entries do not match changed paths",
    RefusalCode.UNSAFE_REMOTE_OBJECT: "remote path object is unsafe",
    RefusalCode.REMOTE_BLOB_TOO_LARGE: "remote blob exceeds the fixed size limit",
    RefusalCode.LOCAL_FACTS_INVALID: "local proof facts are invalid",
    RefusalCode.LOCAL_BRANCH_MISMATCH: "local branch does not match the request",
    RefusalCode.REMOTE_HEAD_OBJECT_MISSING: "remote head object is absent locally",
    RefusalCode.REMOTE_HEAD_NOT_ANCESTOR: "remote head is not an ancestor of local head",
    RefusalCode.OUT_OF_SCOPE_DIRT: "local source contains out-of-scope dirt",
    RefusalCode.LOCAL_REMOTE_IDENTITY_MISMATCH: "local and remote source identities differ",
    RefusalCode.UNPUSHED_COMMITS: "local source contains unpushed commits",
    RefusalCode.IN_SCOPE_DIRT: "local source contains in-scope dirt",
    RefusalCode.EXTERNAL_EFFECT_INVALID: "external effect evidence is invalid",
    RefusalCode.EXTERNAL_EFFECT_UNKNOWN: "external effect state is unknown",
    RefusalCode.BRANCH_EFFECT_REQUIRED: "branch continuation requires an open external effect",
    RefusalCode.BRANCH_EFFECT_UNKNOWN: "branch effect dependency is unknown",
    RefusalCode.AUTH_UNAVAILABLE: "GitHub authentication is unavailable",
    RefusalCode.LOCAL_PROBE_FAILED: "local source probe failed",
    RefusalCode.REMOTE_PROBE_FAILED: "remote source probe failed",
    RefusalCode.REMOTE_PROOF_CHANGED: "remote proof changed during verification",
    RefusalCode.PROBE_INTERNAL_ERROR: "source continuity probe failed",
}


@dataclass(frozen=True)
class SourceContinuityRequest:
    receipt_kind: ReceiptKind
    operation_key: str
    repository: str
    pr_number: int
    branch: str
    base_ref: str
    pinned_base_sha: str
    owned_paths: tuple[str, ...]
    verified_at: str


@dataclass(frozen=True)
class LocalGitFacts:
    branch: str
    head_sha: str
    tree_sha: str
    remote_head_object_exists: bool
    remote_head_is_ancestor_of_local: bool
    unpushed_commit_count: int
    uncommitted_in_scope_count: int
    untracked_in_scope_count: int
    uncommitted_out_of_scope_count: int
    untracked_out_of_scope_count: int


@dataclass(frozen=True)
class RemotePathEntry:
    path: str
    mode: str
    object_type: str
    object_sha: str
    size: int


@dataclass(frozen=True)
class RemoteGitFacts:
    repository: str
    pr_number: int
    branch: str
    base_ref: str
    pr_open: bool
    pr_draft_or_hold: bool
    head_sha: str
    tree_sha: str
    merge_base_sha: str
    current_base_head_sha: str
    changed_paths: tuple[str, ...]
    path_entries: tuple[RemotePathEntry, ...]
    collision_state: CollisionState
    colliding_pr_numbers: tuple[int, ...]
    pagination_complete: bool


@dataclass(frozen=True)
class ExternalEffectEvidence:
    state: ExternalEffectState
    branch_dependency: BranchEffectDependency
    evidence_fingerprint: str


@dataclass(frozen=True)
class SourceContinuityRefusal:
    code: RefusalCode
    exit_code: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": REFUSAL_SCHEMA,
            "ok": False,
            "code": self.code.value,
            "message": REFUSAL_MESSAGES[self.code],
        }


@dataclass(frozen=True)
class SourceContinuityReceipt:
    operation_key: str
    repository: str
    pr_number: int
    branch: str
    base_ref: str
    pinned_base_sha: str
    remote_head_sha: str
    remote_tree_sha: str
    remote_merge_base_sha: str
    current_base_head_sha: str
    changed_paths: tuple[str, ...]
    owned_path_digest: str
    local_branch: str
    local_head_sha: str
    local_tree_sha: str
    remote_head_is_ancestor_of_local: bool
    local_equals_remote: bool
    unpushed_commit_count: int
    uncommitted_in_scope_count: int
    untracked_in_scope_count: int
    uncommitted_out_of_scope_count: int
    untracked_out_of_scope_count: int
    external_effect_state: ExternalEffectState
    branch_effect_dependency: BranchEffectDependency
    external_effect_evidence_fingerprint: str
    collision_state: CollisionState
    colliding_pr_numbers: tuple[int, ...]
    receipt_kind: ReceiptKind
    verified_at: str
    receipt_digest: str

    @property
    def authority_effect(self) -> str:
        return "NONE"

    @property
    def writer_release_authorized(self) -> bool:
        return False

    @property
    def merge_authorized(self) -> bool:
        return False

    @property
    def receiver_transfer_authorized(self) -> bool:
        return False

    def _payload_without_digest(self) -> dict[str, object]:
        return {
            "schema": RECEIPT_SCHEMA,
            "operation_key": self.operation_key,
            "repository": self.repository,
            "pr_number": self.pr_number,
            "branch": self.branch,
            "base_ref": self.base_ref,
            "pinned_base_sha": self.pinned_base_sha,
            "remote_head_sha": self.remote_head_sha,
            "remote_tree_sha": self.remote_tree_sha,
            "remote_merge_base_sha": self.remote_merge_base_sha,
            "current_base_head_sha": self.current_base_head_sha,
            "changed_paths": list(self.changed_paths),
            "owned_path_digest": self.owned_path_digest,
            "local_branch": self.local_branch,
            "local_head_sha": self.local_head_sha,
            "local_tree_sha": self.local_tree_sha,
            "remote_head_is_ancestor_of_local": self.remote_head_is_ancestor_of_local,
            "local_equals_remote": self.local_equals_remote,
            "unpushed_commit_count": self.unpushed_commit_count,
            "uncommitted_in_scope_count": self.uncommitted_in_scope_count,
            "untracked_in_scope_count": self.untracked_in_scope_count,
            "uncommitted_out_of_scope_count": self.uncommitted_out_of_scope_count,
            "untracked_out_of_scope_count": self.untracked_out_of_scope_count,
            "external_effect_state": self.external_effect_state.value,
            "branch_effect_dependency": self.branch_effect_dependency.value,
            "external_effect_evidence_fingerprint": self.external_effect_evidence_fingerprint,
            "collision_state": self.collision_state.value,
            "colliding_pr_numbers": list(self.colliding_pr_numbers),
            "receipt_kind": self.receipt_kind.value,
            "receipt_version": RECEIPT_VERSION,
            "verified_at": self.verified_at,
            "authority_effect": self.authority_effect,
            "writer_release_authorized": self.writer_release_authorized,
            "merge_authorized": self.merge_authorized,
            "receiver_transfer_authorized": self.receiver_transfer_authorized,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._payload_without_digest()
        payload["receipt_digest"] = self.receipt_digest
        return payload


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _refusal(code: RefusalCode, *, exit_code: int) -> SourceContinuityRefusal:
    return SourceContinuityRefusal(code=code, exit_code=exit_code)


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_safe_ref(value: object) -> bool:
    if not isinstance(value, str) or _REF_RE.fullmatch(value) is None:
        return False
    return not (
        value.startswith("/")
        or value.endswith("/")
        or value.endswith(".")
        or value.endswith(".lock")
        or ".." in value
        or "//" in value
        or "@{" in value
        or any(token in value for token in ("~", "^", ":", "?", "*", "[", "\\"))
    )


def _is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4096:
        return False
    if value.startswith("/") or "\\" in value or "//" in value or "\x00" in value:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        return False
    if parsed.parts and parsed.parts[0] == ".git":
        return False
    return str(parsed) == value


def _request_is_valid(request: SourceContinuityRequest) -> bool:
    if not isinstance(request, SourceContinuityRequest):
        return False
    if not isinstance(request.receipt_kind, ReceiptKind):
        return False
    if not isinstance(request.operation_key, str) or _OPERATION_RE.fullmatch(request.operation_key) is None:
        return False
    if not isinstance(request.repository, str) or _REPOSITORY_RE.fullmatch(request.repository) is None:
        return False
    if ".." in request.repository:
        return False
    if (
        not _is_nonnegative_int(request.pr_number)
        or request.pr_number == 0
        or request.pr_number > 2_147_483_647
    ):
        return False
    if not _is_safe_ref(request.branch) or not _is_safe_ref(request.base_ref):
        return False
    if not _is_sha(request.pinned_base_sha):
        return False
    if not isinstance(request.owned_paths, tuple) or not request.owned_paths:
        return False
    if len(request.owned_paths) > 1_000 or len(set(request.owned_paths)) != len(request.owned_paths):
        return False
    if not all(_is_safe_relative_path(path) for path in request.owned_paths):
        return False
    if not isinstance(request.verified_at, str) or _VERIFIED_AT_RE.fullmatch(request.verified_at) is None:
        return False
    try:
        parsed = datetime.fromisoformat(request.verified_at.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def request_is_valid(request: SourceContinuityRequest) -> bool:
    """Return whether a request is safe to use for local and remote probes."""
    return _request_is_valid(request)


def _local_facts_are_valid(local: LocalGitFacts) -> bool:
    return (
        isinstance(local, LocalGitFacts)
        and _is_sha(local.head_sha)
        and _is_sha(local.tree_sha)
        and type(local.remote_head_object_exists) is bool
        and type(local.remote_head_is_ancestor_of_local) is bool
        and _is_nonnegative_int(local.unpushed_commit_count)
        and _is_nonnegative_int(local.uncommitted_in_scope_count)
        and _is_nonnegative_int(local.untracked_in_scope_count)
        and _is_nonnegative_int(local.uncommitted_out_of_scope_count)
        and _is_nonnegative_int(local.untracked_out_of_scope_count)
    )


def _external_facts_are_valid(external: ExternalEffectEvidence) -> bool:
    if not isinstance(external, ExternalEffectEvidence):
        return False
    if not isinstance(external.state, ExternalEffectState):
        return False
    if not isinstance(external.branch_dependency, BranchEffectDependency):
        return False
    return (
        isinstance(external.evidence_fingerprint, str)
        and _FINGERPRINT_RE.fullmatch(external.evidence_fingerprint) is not None
    )


def _remote_identity_matches(
    request: SourceContinuityRequest, remote: RemoteGitFacts
) -> bool:
    return (
        remote.repository == request.repository
        and remote.pr_number == request.pr_number
        and remote.branch == request.branch
        and remote.base_ref == request.base_ref
    )


def _remote_facts_shape_is_valid(remote: RemoteGitFacts) -> bool:
    return (
        isinstance(remote, RemoteGitFacts)
        and isinstance(remote.repository, str)
        and _REPOSITORY_RE.fullmatch(remote.repository) is not None
        and ".." not in remote.repository
        and _is_nonnegative_int(remote.pr_number)
        and 0 < remote.pr_number <= 2_147_483_647
        and _is_safe_ref(remote.branch)
        and _is_safe_ref(remote.base_ref)
        and type(remote.pr_open) is bool
        and type(remote.pr_draft_or_hold) is bool
        and _is_sha(remote.head_sha)
        and _is_sha(remote.tree_sha)
        and _is_sha(remote.merge_base_sha)
        and _is_sha(remote.current_base_head_sha)
        and isinstance(remote.changed_paths, tuple)
        and isinstance(remote.path_entries, tuple)
        and isinstance(remote.collision_state, CollisionState)
        and isinstance(remote.colliding_pr_numbers, tuple)
        and type(remote.pagination_complete) is bool
        and all(
            _is_nonnegative_int(number) and number > 0
            for number in remote.colliding_pr_numbers
        )
        and (
            (
                remote.collision_state
                in {CollisionState.NONE, CollisionState.DISJOINT}
                and not remote.colliding_pr_numbers
            )
            or (
                remote.collision_state is CollisionState.OVERLAP
                and bool(remote.colliding_pr_numbers)
            )
            or remote.collision_state is CollisionState.INCOMPLETE
        )
    )


def _validate_remote_paths(
    request: SourceContinuityRequest, remote: RemoteGitFacts
) -> tuple[RefusalCode | None, tuple[RemotePathEntry, ...]]:
    changed = remote.changed_paths
    if not changed or len(changed) > 1_000 or len(set(changed)) != len(changed):
        return RefusalCode.REMOTE_FACTS_INVALID, ()
    if not all(_is_safe_relative_path(path) for path in changed):
        return RefusalCode.REMOTE_FACTS_INVALID, ()
    owned = frozenset(request.owned_paths)
    if any(path not in owned for path in changed):
        return RefusalCode.PATH_OUTSIDE_OWNERSHIP, ()

    entries_by_path: dict[str, RemotePathEntry] = {}
    for entry in remote.path_entries:
        if not isinstance(entry, RemotePathEntry) or not _is_safe_relative_path(entry.path):
            return RefusalCode.REMOTE_FACTS_INVALID, ()
        if entry.path in entries_by_path:
            return RefusalCode.PATH_ENTRY_MISMATCH, ()
        entries_by_path[entry.path] = entry
    if set(entries_by_path) != set(changed):
        return RefusalCode.PATH_ENTRY_MISMATCH, ()

    ordered = tuple(entries_by_path[path] for path in sorted(changed))
    for entry in ordered:
        if entry.mode not in _SAFE_BLOB_MODES or entry.object_type != "blob" or not _is_sha(entry.object_sha):
            return RefusalCode.UNSAFE_REMOTE_OBJECT, ()
        if not _is_nonnegative_int(entry.size):
            return RefusalCode.REMOTE_FACTS_INVALID, ()
        if entry.size > MAX_REMOTE_BLOB_BYTES:
            return RefusalCode.REMOTE_BLOB_TOO_LARGE, ()
    return None, ordered


def _owned_path_digest(entries: tuple[RemotePathEntry, ...]) -> str:
    projection = [
        {
            "path": entry.path,
            "mode": entry.mode,
            "object_type": entry.object_type,
            "object_sha": entry.object_sha,
            "size": entry.size,
        }
        for entry in entries
    ]
    return _digest(projection)


def _validate_effect(
    external: ExternalEffectEvidence,
) -> SourceContinuityRefusal | None:
    if external.state is ExternalEffectState.EFFECT_UNKNOWN:
        return _refusal(RefusalCode.EXTERNAL_EFFECT_UNKNOWN, exit_code=1)
    if external.branch_dependency is BranchEffectDependency.REQUIRED:
        return _refusal(RefusalCode.BRANCH_EFFECT_REQUIRED, exit_code=1)
    if external.branch_dependency is BranchEffectDependency.UNKNOWN:
        return _refusal(RefusalCode.BRANCH_EFFECT_UNKNOWN, exit_code=1)
    if (
        external.state is ExternalEffectState.OPEN_KNOWN_EFFECT
        and external.branch_dependency is not BranchEffectDependency.SEPARABLE
    ):
        return _refusal(RefusalCode.BRANCH_EFFECT_REQUIRED, exit_code=1)
    if (
        external.state
        in {ExternalEffectState.NONE, ExternalEffectState.RECONCILED_NO_OPEN_EFFECT}
        and external.branch_dependency is BranchEffectDependency.SEPARABLE
    ):
        return _refusal(RefusalCode.EXTERNAL_EFFECT_INVALID, exit_code=2)
    return None


def verify_source_continuity(
    request: SourceContinuityRequest,
    local: LocalGitFacts,
    remote: RemoteGitFacts,
    external: ExternalEffectEvidence,
) -> SourceContinuityReceipt | SourceContinuityRefusal:
    """Verify one immutable source checkpoint or remote-complete observation."""

    if not _request_is_valid(request):
        return _refusal(RefusalCode.INVALID_REQUEST, exit_code=2)
    if not _remote_facts_shape_is_valid(remote):
        return _refusal(RefusalCode.REMOTE_FACTS_INVALID, exit_code=2)
    if not _remote_identity_matches(request, remote):
        return _refusal(RefusalCode.REMOTE_IDENTITY_MISMATCH, exit_code=2)
    if not remote.pr_open:
        return _refusal(RefusalCode.PR_NOT_OPEN, exit_code=2)
    if not remote.pr_draft_or_hold:
        return _refusal(RefusalCode.PR_NOT_DRAFT_OR_HOLD, exit_code=2)
    if remote.head_sha == request.pinned_base_sha:
        return _refusal(RefusalCode.REMOTE_HEAD_EQUALS_PICKUP_BASE, exit_code=2)
    if not remote.pagination_complete or remote.collision_state is CollisionState.INCOMPLETE:
        return _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, exit_code=2)

    path_refusal, ordered_entries = _validate_remote_paths(request, remote)
    if path_refusal is not None:
        return _refusal(path_refusal, exit_code=2)

    if not isinstance(local, LocalGitFacts):
        return _refusal(RefusalCode.LOCAL_FACTS_INVALID, exit_code=2)
    if (
        not isinstance(local.branch, str)
        or not _is_safe_ref(local.branch)
        or local.branch != request.branch
    ):
        return _refusal(RefusalCode.LOCAL_BRANCH_MISMATCH, exit_code=1)
    if not _local_facts_are_valid(local):
        return _refusal(RefusalCode.LOCAL_FACTS_INVALID, exit_code=2)
    if not local.remote_head_object_exists:
        return _refusal(RefusalCode.REMOTE_HEAD_OBJECT_MISSING, exit_code=1)
    if not local.remote_head_is_ancestor_of_local:
        return _refusal(RefusalCode.REMOTE_HEAD_NOT_ANCESTOR, exit_code=1)
    if local.uncommitted_out_of_scope_count or local.untracked_out_of_scope_count:
        return _refusal(RefusalCode.OUT_OF_SCOPE_DIRT, exit_code=1)

    if not _external_facts_are_valid(external):
        return _refusal(RefusalCode.EXTERNAL_EFFECT_INVALID, exit_code=2)
    effect_refusal = _validate_effect(external)
    if effect_refusal is not None:
        return effect_refusal

    local_equals_remote = (
        local.head_sha == remote.head_sha and local.tree_sha == remote.tree_sha
    )
    if request.receipt_kind is ReceiptKind.REMOTE_COMPLETE_VERIFIED:
        if not local_equals_remote:
            return _refusal(
                RefusalCode.LOCAL_REMOTE_IDENTITY_MISMATCH, exit_code=1
            )
        if local.unpushed_commit_count:
            return _refusal(RefusalCode.UNPUSHED_COMMITS, exit_code=1)
        if local.uncommitted_in_scope_count or local.untracked_in_scope_count:
            return _refusal(RefusalCode.IN_SCOPE_DIRT, exit_code=1)

    receipt = SourceContinuityReceipt(
        operation_key=request.operation_key,
        repository=request.repository,
        pr_number=request.pr_number,
        branch=request.branch,
        base_ref=request.base_ref,
        pinned_base_sha=request.pinned_base_sha,
        remote_head_sha=remote.head_sha,
        remote_tree_sha=remote.tree_sha,
        remote_merge_base_sha=remote.merge_base_sha,
        current_base_head_sha=remote.current_base_head_sha,
        changed_paths=tuple(sorted(remote.changed_paths)),
        owned_path_digest=_owned_path_digest(ordered_entries),
        local_branch=local.branch,
        local_head_sha=local.head_sha,
        local_tree_sha=local.tree_sha,
        remote_head_is_ancestor_of_local=local.remote_head_is_ancestor_of_local,
        local_equals_remote=local_equals_remote,
        unpushed_commit_count=local.unpushed_commit_count,
        uncommitted_in_scope_count=local.uncommitted_in_scope_count,
        untracked_in_scope_count=local.untracked_in_scope_count,
        uncommitted_out_of_scope_count=local.uncommitted_out_of_scope_count,
        untracked_out_of_scope_count=local.untracked_out_of_scope_count,
        external_effect_state=external.state,
        branch_effect_dependency=external.branch_dependency,
        external_effect_evidence_fingerprint=external.evidence_fingerprint,
        collision_state=remote.collision_state,
        colliding_pr_numbers=tuple(sorted(set(remote.colliding_pr_numbers))),
        receipt_kind=request.receipt_kind,
        verified_at=request.verified_at,
        receipt_digest="",
    )
    digest = _digest(receipt._payload_without_digest())
    return SourceContinuityReceipt(
        **{
            **receipt.__dict__,
            "receipt_digest": digest,
        }
    )
