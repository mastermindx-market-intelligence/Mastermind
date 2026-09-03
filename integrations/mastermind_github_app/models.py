"""Closed models and owner ports for bounded exact GitHub branch repairs."""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Mapping, Protocol, Sequence


RESULT_SCHEMA = "mastermind.github_exact_repair_tool_result.v1"
RECEIPT_SCHEMA = "mastermind.github_exact_branch_repair_receipt.v1"
REQUIRED_SCOPE = "mastermind.github.exact_branch_repair"


class ToolStatus(str, Enum):
    OK = "OK"
    BLOCKED = "BLOCKED"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


class EffectState(str, Enum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class PatchEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


class IssueCode(str, Enum):
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    PRODUCTION_DISARMED = "PRODUCTION_DISARMED"
    AUTHENTICATION_REFUSED = "AUTHENTICATION_REFUSED"
    SCOPE_REFUSED = "SCOPE_REFUSED"
    ORGANIZATIONAL_AUTHORITY_REFUSED = "ORGANIZATIONAL_AUTHORITY_REFUSED"
    ACTION_TARGET_UNRESOLVED = "ACTION_TARGET_UNRESOLVED"
    OPERATION_NOT_FOUND = "OPERATION_NOT_FOUND"
    OPERATION_CARRIER_CONFLICT = "OPERATION_CARRIER_CONFLICT"
    CARRIER_WRITER_CONFLICT = "CARRIER_WRITER_CONFLICT"
    PATCH_TARGET_NOT_OWNED = "PATCH_TARGET_NOT_OWNED"
    PROTECTED_BRANCH_REFUSED = "PROTECTED_BRANCH_REFUSED"
    BRANCH_HEAD_MOVED = "BRANCH_HEAD_MOVED"
    BLOB_OID_MOVED = "BLOB_OID_MOVED"
    SOURCE_TRUNCATED_OR_UNAVAILABLE = "SOURCE_TRUNCATED_OR_UNAVAILABLE"
    SOURCE_KIND_REFUSED = "SOURCE_KIND_REFUSED"
    PATCH_SCHEMA_INVALID = "PATCH_SCHEMA_INVALID"
    PATCH_LIMIT_EXCEEDED = "PATCH_LIMIT_EXCEEDED"
    PATCH_CONTEXT_MISMATCH = "PATCH_CONTEXT_MISMATCH"
    PATCH_NO_EFFECT = "PATCH_NO_EFFECT"
    PATCH_SECRET_SHAPE_REFUSED = "PATCH_SECRET_SHAPE_REFUSED"
    PREPARED_TOKEN_INVALID = "PREPARED_TOKEN_INVALID"
    PREPARED_ACTION_EXPIRED = "PREPARED_ACTION_EXPIRED"
    APP_GENERATION_MISMATCH = "APP_GENERATION_MISMATCH"
    PRECONDITION_CHANGED = "PRECONDITION_CHANGED"
    PRIOR_EFFECT_UNKNOWN = "PRIOR_EFFECT_UNKNOWN"
    NATIVE_REQUEST_REFUSED = "NATIVE_REQUEST_REFUSED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    INTERNAL_CONTRACT_ERROR = "INTERNAL_CONTRACT_ERROR"


@dataclasses.dataclass(frozen=True)
class AuthenticatedPrincipal:
    principal_digest: str
    scopes: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ResolvedPatchTarget:
    """Server-owned exact operation/carrier/writer target facts.

    The model never supplies this object. An accepted semantic owner resolves it
    from the stable operation key and authenticated principal immediately before
    preparation/commit/reconciliation.
    """

    operation_key: str
    repository: str
    branch: str
    pull_request_number: int | None
    protected_branches: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    carrier_digest: str
    writer_digest: str
    authority_digest: str
    source_digest: str
    patch_eligibility: PatchEligibility
    issues: tuple[IssueCode, ...] = ()


@dataclasses.dataclass(frozen=True)
class GithubBlob:
    path: str
    oid: str
    content: str
    object_kind: str = "REGULAR_FILE"
    encoding: str = "utf-8"
    truncated: bool = False


@dataclasses.dataclass(frozen=True)
class CommitFile:
    path: str
    expected_blob_oid: str
    content: str = dataclasses.field(repr=False)
    after_sha256: str


@dataclasses.dataclass(frozen=True)
class NativeCommitResult:
    request_sent: bool
    commit_oid: str | None
    definite_no_effect: bool


@dataclasses.dataclass(frozen=True)
class EffectObservation:
    state: EffectState
    commit_oid: str | None
    branch_head_oid: str | None
    complete: bool


@dataclasses.dataclass(frozen=True)
class AppConfig:
    app_id: str
    app_generation: str
    schema_digest: str
    policy_id: str
    production_armed: bool = False
    required_scope: str = REQUIRED_SCOPE
    token_ttl_seconds: int = 300


@dataclasses.dataclass(frozen=True)
class ToolEnvelope:
    tool: str
    status: ToolStatus
    observed_at: int
    capability_generation: str
    data: Mapping[str, object]
    issues: tuple[IssueCode, ...] = ()

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RESULT_SCHEMA,
            "tool": self.tool,
            "status": self.status.value,
            "observed_at": self.observed_at,
            "capability_generation": self.capability_generation,
            "data": dict(self.data),
            "issues": [issue.value for issue in self.issues],
        }


class PrincipalProvider(Protocol):
    async def current_principal(self) -> AuthenticatedPrincipal:
        """Return the already-authenticated resource principal."""


class PatchAuthorityResolver(Protocol):
    async def resolve_patch_target(
        self,
        operation_key: str,
        principal_digest: str,
    ) -> ResolvedPatchTarget:
        """Resolve the exact current operation/carrier/writer-owned target."""


class GithubPatchPort(Protocol):
    async def read_branch_head(self, target: ResolvedPatchTarget) -> str:
        """Read the exact current branch head OID."""

    async def read_blob(
        self,
        target: ResolvedPatchTarget,
        head_oid: str,
        path: str,
    ) -> GithubBlob:
        """Read one complete exact regular-file blob at the supplied head."""

    async def commit_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        files: Sequence[CommitFile],
    ) -> NativeCommitResult:
        """Issue at most one expected-head native branch commit."""

    async def reconcile_branch_patch(
        self,
        target: ResolvedPatchTarget,
        expected_head_oid: str,
        operation_key: str,
        effect_digest: str,
        expected_after_sha256: Mapping[str, str],
    ) -> EffectObservation:
        """Read canonical GitHub evidence without resubmitting."""


class Clock(Protocol):
    def now(self) -> int:
        """Return integer UTC epoch seconds from the owner process."""


class NativeCommitError(RuntimeError):
    """Stable GitHub-port error without provider payload reflection."""

    def __init__(self, *, effect_possible: bool) -> None:
        self.effect_possible = effect_possible
        super().__init__("native_commit_error")


__all__ = [
    "RESULT_SCHEMA",
    "RECEIPT_SCHEMA",
    "REQUIRED_SCOPE",
    "AppConfig",
    "AuthenticatedPrincipal",
    "Clock",
    "CommitFile",
    "EffectObservation",
    "EffectState",
    "GithubBlob",
    "GithubPatchPort",
    "IssueCode",
    "NativeCommitError",
    "NativeCommitResult",
    "PatchAuthorityResolver",
    "PatchEligibility",
    "PrincipalProvider",
    "ResolvedPatchTarget",
    "ToolEnvelope",
    "ToolStatus",
]
