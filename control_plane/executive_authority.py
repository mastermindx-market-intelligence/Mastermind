"""Fail-closed authority policy for Executive OS coding workers.

The portfolio A0-A7 ladder remains an effect classification.  Executive worker
capabilities are a separate, executable grant read from the same reviewed
``config/authority_map.yml`` source.  This module deliberately implements only
the Phase 1B grant surface; adding a capability to YAML alone cannot expand
runtime authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


_ROOT = Path(__file__).resolve().parent.parent
_POLICY_PATH = _ROOT / "config" / "authority_map.yml"

PHASE1B_ALLOWED = frozenset(
    {"READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS", "REQUEST_WORKER_LOGIN_CHECK"}
)
PHASE1B_REQUIRED_DENIES = frozenset(
    {
        "OPEN_PR",
        "MERGE",
        "DEPLOY",
        "SERVICE_CONTROL",
        "CAPITAL_EXECUTION",
        "BILLING",
        "CREDENTIAL_ADMIN",
        "PUSH_BRANCH",
        "CROSS_REPO_PUBLISH",
        "PAPER_STATE_MUTATION",
        "DATA_DELETE",
    }
)


class AuthorityPolicyError(RuntimeError):
    """The reviewed authority policy is absent, malformed, or unsafe."""


class AuthorityDenied(AuthorityPolicyError):
    """A requested effect is outside the Phase 1B worker grant."""


_POLICY_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_POLICY_VALUE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _parse_executive_policy(raw: bytes) -> dict[str, Any]:
    """Parse only the deliberately tiny Executive policy YAML subset.

    The always-on service must not inherit a mutable third-party Python package
    tree merely to read four scalar/list fields.  This strict parser accepts the
    checked-in block and the same plain mapping/list shape emitted by PyYAML in
    tests; every YAML feature outside that subset fails closed.
    """

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AuthorityPolicyError("Executive worker authority policy is unreadable") from exc
    if "\t" in text or "\x00" in text:
        raise AuthorityPolicyError("Executive worker authority policy is unreadable")
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.rstrip() == "executive_worker_policy:"
    ]
    if len(starts) != 1:
        raise AuthorityPolicyError("authority_map.yml has no unique executive_worker_policy mapping")
    block: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line and not line.startswith((" ", "#")):
            break
        if line.startswith("  "):
            block.append(line)
    result: dict[str, Any] = {}
    current_list: str | None = None
    in_scopes = False
    for raw_line in block:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line.startswith("  - ") and current_list is not None:
            value = stripped[2:]
            if _POLICY_KEY_RE.fullmatch(value) is None:
                raise AuthorityPolicyError("invalid executive_worker_policy shape")
            result[current_list].append(value)
            continue
        if raw_line.startswith("    ") and not raw_line.startswith("      "):
            if current_list is not None and stripped.startswith("- "):
                value = stripped[2:]
                if _POLICY_KEY_RE.fullmatch(value) is None:
                    raise AuthorityPolicyError("invalid executive_worker_policy shape")
                result[current_list].append(value)
                continue
            if in_scopes and ":" in stripped and not stripped.startswith("-"):
                key, value = (part.strip() for part in stripped.split(":", 1))
                if (
                    _POLICY_KEY_RE.fullmatch(key) is None
                    or _POLICY_VALUE_RE.fullmatch(value) is None
                    or key in result["scope_requirements"]
                ):
                    raise AuthorityPolicyError("invalid executive_worker_policy shape")
                result["scope_requirements"][key] = value
                continue
            raise AuthorityPolicyError("invalid executive_worker_policy shape")
        if not raw_line.startswith("  ") or raw_line.startswith("   ") or ":" not in stripped:
            raise AuthorityPolicyError("invalid executive_worker_policy shape")
        key, value = (part.strip() for part in stripped.split(":", 1))
        if key in result:
            raise AuthorityPolicyError("invalid executive_worker_policy shape")
        current_list = None
        in_scopes = False
        if key == "schema_version" and value:
            result[key] = value
        elif key in {"allowed_capabilities", "denied_capabilities"} and not value:
            result[key] = []
            current_list = key
        elif key == "scope_requirements" and not value:
            result[key] = {}
            in_scopes = True
        else:
            raise AuthorityPolicyError("invalid executive_worker_policy shape")
    required = {
        "schema_version",
        "allowed_capabilities",
        "denied_capabilities",
        "scope_requirements",
    }
    if set(result) != required:
        raise AuthorityPolicyError("invalid executive_worker_policy shape")
    return result


def _capabilities(values: Iterable[str] | str | None) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if values is not None and not isinstance(values, (list, tuple, set, frozenset)):
        raise AuthorityDenied("requested authorities must be a string or list")
    result = tuple(sorted({str(value).strip().upper() for value in (values or []) if str(value).strip()}))
    if not result:
        raise AuthorityDenied("at least one explicit worker authority is required")
    return result


def _relative_write_paths(values: Sequence[str] | None) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values or []:
        value = str(raw).strip().replace("\\", "/")
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or value in {".", "./"}:
            raise AuthorityDenied(f"unsafe assigned write path {raw!r}")
        result.append(str(path))
    return tuple(sorted(set(result)))


def _validation_commands(values: Sequence[Sequence[str]] | None) -> tuple[tuple[str, ...], ...]:
    commands: list[tuple[str, ...]] = []
    for raw in values or []:
        if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
            raise AuthorityDenied("validation commands must be argv lists, never shell strings")
        if not raw or any(not isinstance(item, str) or not item for item in raw):
            raise AuthorityDenied(
                "validation command argv must contain only non-empty strings"
            )
        argv = tuple(raw)
        commands.append(argv)
    return tuple(commands)


@dataclasses.dataclass(frozen=True)
class AuthorityDecision:
    requested: tuple[str, ...]
    policy_sha256: str
    policy_schema_version: int
    worktree: str | None
    allowed_write_paths: tuple[str, ...]
    validation_commands: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": list(self.requested),
            "policy_sha256": self.policy_sha256,
            "policy_schema_version": self.policy_schema_version,
            "worktree": self.worktree,
            "allowed_write_paths": list(self.allowed_write_paths),
            "validation_commands": [list(command) for command in self.validation_commands],
        }


@dataclasses.dataclass(frozen=True)
class ExecutiveAuthorityPolicy:
    path: Path
    sha256: str
    schema_version: int
    allowed: frozenset[str]
    denied: frozenset[str]
    scope_requirements: dict[str, str]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ExecutiveAuthorityPolicy":
        policy_path = Path(path).resolve() if path is not None else _POLICY_PATH
        try:
            raw = policy_path.read_bytes()
        except OSError as exc:
            raise AuthorityPolicyError(f"Executive worker authority policy is unavailable: {exc}") from exc
        section = _parse_executive_policy(raw)
        try:
            schema_version = int(section["schema_version"])
            allowed = frozenset(str(item).strip().upper() for item in section["allowed_capabilities"])
            denied = frozenset(str(item).strip().upper() for item in section["denied_capabilities"])
            scopes = {
                str(key).strip().upper(): str(value).strip()
                for key, value in dict(section["scope_requirements"]).items()
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthorityPolicyError(f"invalid executive_worker_policy shape: {exc}") from exc
        if schema_version != 1:
            raise AuthorityPolicyError(f"unsupported Executive worker policy schema {schema_version}")
        if allowed != PHASE1B_ALLOWED:
            raise AuthorityPolicyError(
                "Phase 1B authority allow-list drifted; code review is required before expansion"
            )
        if allowed & denied:
            raise AuthorityPolicyError("Executive worker policy cannot both allow and deny a capability")
        missing_denies = PHASE1B_REQUIRED_DENIES - denied
        if missing_denies:
            raise AuthorityPolicyError(
                f"Executive worker policy is missing mandatory denies: {sorted(missing_denies)}"
            )
        if scopes.get("WRITE_BRANCH") != "assigned_workspace_and_declared_paths":
            raise AuthorityPolicyError("WRITE_BRANCH must be workspace and path scoped")
        if scopes.get("RUN_TESTS") != "declared_argv_commands":
            raise AuthorityPolicyError("RUN_TESTS must be scoped to declared argv commands")
        if scopes.get("REQUEST_WORKER_LOGIN_CHECK") != "current_attempt_assigned_worker_slot":
            raise AuthorityPolicyError(
                "REQUEST_WORKER_LOGIN_CHECK must be scoped to the current-attempt assigned worker slot"
            )
        return cls(
            path=policy_path,
            sha256=hashlib.sha256(raw).hexdigest(),
            schema_version=schema_version,
            allowed=allowed,
            denied=denied,
            scope_requirements=scopes,
        )

    def authorize(
        self,
        requested: Iterable[str] | str | None,
        *,
        worktree: str | Path | None = None,
        allowed_write_paths: Sequence[str] | None = None,
        validation_commands: Sequence[Sequence[str]] | None = None,
    ) -> AuthorityDecision:
        capabilities = _capabilities(requested)
        unknown = set(capabilities) - self.allowed - self.denied
        forbidden = set(capabilities) & self.denied
        if unknown:
            raise AuthorityDenied(f"unknown Executive worker authorities: {sorted(unknown)}")
        if forbidden:
            raise AuthorityDenied(f"denied Executive worker authorities: {sorted(forbidden)}")
        if not set(capabilities).issubset(self.allowed):
            raise AuthorityDenied("requested Executive worker authority is not granted")

        resolved_worktree: str | None = None
        paths = _relative_write_paths(allowed_write_paths)
        commands = _validation_commands(validation_commands)
        if "WRITE_BRANCH" in capabilities:
            if worktree is None:
                raise AuthorityDenied("WRITE_BRANCH requires an assigned workspace")
            candidate = Path(worktree).expanduser()
            if not candidate.is_absolute():
                raise AuthorityDenied("assigned workspace must be an absolute path")
            resolved_worktree = str(candidate.resolve())
            if not paths:
                raise AuthorityDenied("WRITE_BRANCH requires at least one declared relative write path")
        elif paths:
            raise AuthorityDenied("declared write paths require WRITE_BRANCH authority")

        if "RUN_TESTS" in capabilities and not commands:
            raise AuthorityDenied("RUN_TESTS requires at least one declared argv command")
        if "RUN_TESTS" not in capabilities and commands:
            raise AuthorityDenied("declared validation commands require RUN_TESTS authority")

        return AuthorityDecision(
            requested=capabilities,
            policy_sha256=self.sha256,
            policy_schema_version=self.schema_version,
            worktree=resolved_worktree,
            allowed_write_paths=paths,
            validation_commands=commands,
        )


# Controller release policy is separate from the worker capability ladder above.
# These checks evaluate trusted owner inputs; they do not authenticate a JWT,
# qualify a running service, trust a file, enable production, sign, or dispatch.
# Product must obtain the principal from its verified gateway connection and
# the exact policy bytes from verify_production_trust before calling this API.
# A policy/record constructed in Python is not evidence of either provenance.
import enum as _enum
import os as _os
import weakref as _weakref


class ReleasePolicyState(str, _enum.Enum):
    UNCONFIGURED = "UNCONFIGURED"
    DISABLED = "DISABLED"
    CONFIGURED = "CONFIGURED"


class ReleaseAuthorityDenied(AuthorityDenied):
    """Closed controller refusal; never reflects credentials or rejected input."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_RELEASE_SECTION = "executive_release_controller_policy"
_RELEASE_LIST_FIELDS = frozenset({
    "subject_digests", "client_refs", "required_scopes", "actions",
    "target_refs", "installer_profile_digests", "source_policy_modes",
})
_RELEASE_INT_FIELDS = frozenset({"generation", "max_approval_lifetime_seconds"})
_RELEASE_TEXT_FIELDS = frozenset({
    "schema", "policy_id", "issuer_digest", "resource_digest",
    "confirmation_requirement",
})
_RELEASE_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_RELEASE_MAX_INT = (1 << 63) - 1


def _release_contract():
    # Keep the existing worker import graph unchanged. The installed C1 release
    # consumer uses Python 3.12 and loads its contract only when requested.
    from control_plane import executive_release_contract
    return executive_release_contract


def _release_refuse(code: str) -> None:
    raise ReleaseAuthorityDenied(code)


def _parse_release_controller_policy(raw: bytes):
    """Closed, plain YAML block; no aliases, tags, flow values or coercion.

    Other authority-map sections are left with their existing owners. A present
    malformed release section is never mistaken for an absent configuration.
    """
    if type(raw) is not bytes or not raw or len(raw) > _RELEASE_MAX_SOURCE_BYTES:
        _release_refuse("RELEASE_POLICY_INVALID")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _release_refuse("RELEASE_POLICY_INVALID")
    if any(char in text for char in ("\x00", "\t", "\ufeff")):
        _release_refuse("RELEASE_POLICY_INVALID")
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        _release_refuse("RELEASE_POLICY_INVALID")
    lines = text.split("\n")
    # Validate the entire root mapping before selecting an authority section.
    # Plain block keys have one spelling; quoted/complex keys, aliases, root
    # flow values and document boundaries cannot hide a second policy. Nested
    # contents of other ordinary sections remain their existing owners' data.
    root_keys: set[str] = set()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(" "):
            if not root_keys:
                _release_refuse("RELEASE_POLICY_INVALID")
            continue
        root = re.fullmatch(r"([a-z][a-z0-9_]*): *(?:#.*)?", line)
        if root is None or root.group(1) in root_keys:
            _release_refuse("RELEASE_POLICY_INVALID")
        root_keys.add(root.group(1))
    starts = [index for index, line in enumerate(lines)
              if re.match(r"^\s*['\"]?executive_release_controller_policy['\"]?\s*:", line)]
    if not starts:
        return None
    if len(starts) != 1 or lines[starts[0]].rstrip(" ") != _RELEASE_SECTION + ":":
        _release_refuse("RELEASE_POLICY_INVALID")
    values: dict[str, Any] = {}
    list_key: str | None = None
    for line in lines[starts[0] + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        if line.startswith("    - ") and list_key is not None:
            item = line[6:].rstrip(" ")
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", item) is None:
                _release_refuse("RELEASE_POLICY_INVALID")
            values[list_key].append(item)
            if len(values[list_key]) > 32:
                _release_refuse("RELEASE_POLICY_INVALID")
            continue
        match = re.fullmatch(r"  ([a-z_]+):(?: ([^\r\n]+))? *", line)
        if match is None:
            _release_refuse("RELEASE_POLICY_INVALID")
        key, value = match.groups()
        value = value.rstrip(" ") if value is not None else None
        if key in values:
            _release_refuse("RELEASE_POLICY_INVALID")
        list_key = None
        if key in _RELEASE_LIST_FIELDS and value is None:
            values[key] = []
            list_key = key
        elif key in _RELEASE_INT_FIELDS and value is not None:
            if re.fullmatch(r"[1-9][0-9]{0,18}", value) is None:
                _release_refuse("RELEASE_POLICY_INVALID")
            values[key] = int(value)
        elif key == "enabled" and value in ("true", "false"):
            values[key] = value == "true"
        elif key in _RELEASE_TEXT_FIELDS and value is not None:
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", value) is None:
                _release_refuse("RELEASE_POLICY_INVALID")
            values[key] = value
        else:
            _release_refuse("RELEASE_POLICY_INVALID")
    contract = _release_contract()
    try:
        return contract.validate_release_policy(values)
    except contract.ReleaseContractError:
        _release_refuse("RELEASE_POLICY_INVALID")


@dataclasses.dataclass(frozen=True)
class ReleaseControllerPolicy:
    """Exact policy snapshot, not proof of installed/root-owned provenance."""

    _raw: bytes = dataclasses.field(repr=False)

    def __post_init__(self):
        _parse_release_controller_policy(self._raw)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ReleaseControllerPolicy":
        return cls(raw)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ReleaseControllerPolicy":
        # No trust claim follows from opening this path. The production caller
        # supplies a currently verified installed source, never a model path.
        candidate = Path(path) if path is not None else _POLICY_PATH
        try:
            with candidate.open("rb") as source:
                raw = source.read(_RELEASE_MAX_SOURCE_BYTES + 1)
        except OSError:
            _release_refuse("RELEASE_POLICY_UNAVAILABLE")
        return cls.from_bytes(raw)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self._raw).hexdigest()

    @property
    def configuration_state(self) -> ReleasePolicyState:
        section = _parse_release_controller_policy(self._raw)
        if section is None:
            return ReleasePolicyState.UNCONFIGURED
        return ReleasePolicyState.CONFIGURED if section["enabled"] else ReleasePolicyState.DISABLED


class TrustedReleaseConfirmation:
    """In-process owner-issued surface confirmation, never a public payload."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("confirmation requires private trusted surface composition")


@dataclasses.dataclass(frozen=True)
class _ReleaseConfirmationState:
    principal_digest: str
    target_ref: str
    transition_digest: str
    authority_policy_hash: str
    evidence_digest: str
    expires_at_ms: int
    receiver_pid: int


# Product's trusted surface factory may use this private seam only after real
# confirmation. It is absent in production C1. Arbitrary code execution inside
# that same trusted process is outside this process-local provenance boundary.
_RELEASE_CONFIRMATION_CAPABILITY = object()
_RELEASE_CONFIRMATIONS = _weakref.WeakKeyDictionary()


def _bind_trusted_release_confirmation(owner_capability: object, *,
        principal_digest: str, target_ref: str, transition_digest: str,
        authority_policy_hash: str, evidence_digest: str,
        expires_at_ms: int) -> TrustedReleaseConfirmation:
    if owner_capability is not _RELEASE_CONFIRMATION_CAPABILITY:
        _release_refuse("RELEASE_CONFIRMATION_PROVENANCE_REQUIRED")
    for value in (principal_digest, target_ref, transition_digest,
                  authority_policy_hash, evidence_digest):
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            _release_refuse("RELEASE_CONFIRMATION_INVALID")
    if type(expires_at_ms) is not int or not 0 < expires_at_ms <= _RELEASE_MAX_INT:
        _release_refuse("RELEASE_CONFIRMATION_INVALID")
    result = object.__new__(TrustedReleaseConfirmation)
    _RELEASE_CONFIRMATIONS[result] = _ReleaseConfirmationState(
        principal_digest, target_ref, transition_digest, authority_policy_hash,
        evidence_digest, expires_at_ms, _os.getpid())
    return result


def release_principal_projection(principal):
    """Project an existing verified principal; never authenticate one here."""
    from integrations.business_mcp_auth.contracts import VerifiedPrincipal
    if type(principal) is not VerifiedPrincipal:
        _release_refuse("RELEASE_VERIFIED_PRINCIPAL_REQUIRED")
    if (type(principal.issuer) is not str or not principal.issuer
            or type(principal.resource) is not str or not principal.resource
            or len(principal.issuer) > 2048 or len(principal.resource) > 2048
            or type(principal.scopes) is not tuple):
        _release_refuse("RELEASE_PRINCIPAL_INVALID")
    if any(ord(char) < 32 or ord(char) == 127
           for char in principal.issuer + principal.resource):
        _release_refuse("RELEASE_PRINCIPAL_INVALID")
    try:
        issuer_bytes = principal.issuer.encode("utf-8", errors="strict")
        resource_bytes = principal.resource.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _release_refuse("RELEASE_PRINCIPAL_INVALID")
    issuer_digest = hashlib.sha256(issuer_bytes).hexdigest()
    if principal.issuer_digest != issuer_digest:
        _release_refuse("RELEASE_PRINCIPAL_INVALID")
    contract = _release_contract()
    try:
        return contract.validate_principal_projection({
            "policy_id": principal.policy_id, "issuer_digest": issuer_digest,
            "resource_digest": hashlib.sha256(resource_bytes).hexdigest(),
            "subject_digest": principal.subject_digest, "client_ref": principal.client_ref,
            "scopes": list(principal.scopes),
        })
    except contract.ReleaseContractError:
        _release_refuse("RELEASE_PRINCIPAL_INVALID")


def authorize_release_transition(principal, transition, installed_policy, *,
        target_ref: str, now_ms: int, confirmation=None):
    """Return a bounded controller grant from already trusted owner inputs.

    Signature verification, installed policy/provenance freshness, staged byte
    validation, connection qualification, and production arming stay with the
    existing Product owner. Call only after those checks, then independently
    recheck at seal/prepare/commit. This deterministic result creates no effect.
    """
    if type(installed_policy) is not ReleaseControllerPolicy:
        _release_refuse("RELEASE_INSTALLED_POLICY_REQUIRED")
    policy = _parse_release_controller_policy(installed_policy._raw)
    if policy is None:
        _release_refuse("RELEASE_POLICY_UNCONFIGURED")
    if not policy["enabled"]:
        _release_refuse("RELEASE_POLICY_DISABLED")
    if type(now_ms) is not int or not 0 <= now_ms <= _RELEASE_MAX_INT:
        _release_refuse("RELEASE_CLOCK_INVALID")
    projection = release_principal_projection(principal)
    if (type(principal.issued_at) is not int or type(principal.expires_at) is not int
            or not 0 <= principal.issued_at < principal.expires_at <= _RELEASE_MAX_INT // 1000):
        _release_refuse("RELEASE_PRINCIPAL_INVALID")
    if not principal.issued_at * 1000 <= now_ms < principal.expires_at * 1000:
        _release_refuse("RELEASE_PRINCIPAL_NOT_CURRENT")
    contract = _release_contract()
    if type(transition) is not contract.ReleaseRecord:
        _release_refuse("RELEASE_IMMUTABLE_TRANSITION_REQUIRED")
    try:
        effect = contract.validate_normalized_effect(transition)
    except contract.ReleaseContractError:
        _release_refuse("RELEASE_TRANSITION_INVALID")
    if (projection["policy_id"] != policy["policy_id"]
            or projection["issuer_digest"] != policy["issuer_digest"]
            or projection["resource_digest"] != policy["resource_digest"]
            or projection["subject_digest"] not in policy["subject_digests"]
            or projection["client_ref"] not in policy["client_refs"]
            or not set(policy["required_scopes"]).issubset(projection["scopes"])):
        _release_refuse("RELEASE_PRINCIPAL_NOT_AUTHORIZED")
    if (type(target_ref) is not str or target_ref not in policy["target_refs"]
            or effect["action"] not in policy["actions"]
            or effect["installer_profile_digest"] not in policy["installer_profile_digests"]
            or effect["source_policy_mode"] not in policy["source_policy_modes"]):
        _release_refuse("RELEASE_TRANSITION_NOT_AUTHORIZED")
    principal_digest = hashlib.sha256(contract.canonical_release_bytes(projection)).hexdigest()
    transition_digest = hashlib.sha256(contract.canonical_release_bytes(effect)).hexdigest()
    expiry = min(principal.expires_at * 1000,
                 now_ms + policy["max_approval_lifetime_seconds"] * 1000)
    if policy["confirmation_requirement"] == "required":
        if (type(confirmation) is not TrustedReleaseConfirmation
                or confirmation not in _RELEASE_CONFIRMATIONS):
            _release_refuse("RELEASE_CONFIRMATION_PROVENANCE_REQUIRED")
        state = _RELEASE_CONFIRMATIONS[confirmation]
        if (state.receiver_pid != _os.getpid()
                or state.principal_digest != principal_digest
                or state.target_ref != target_ref
                or state.transition_digest != transition_digest
                or state.authority_policy_hash != installed_policy.sha256):
            _release_refuse("RELEASE_CONFIRMATION_BINDING_MISMATCH")
        expiry = min(expiry, state.expires_at_ms)
        confirmation_digest = state.evidence_digest
    else:
        if confirmation is not None:
            _release_refuse("RELEASE_UNEXPECTED_CONFIRMATION")
        # Bind the exact installed delegation and selected subject/effect/target,
        # rather than a free-form caller assertion of delegated authority.
        confirmation_digest = hashlib.sha256(
            b"MMX_EXECUTIVE_RELEASE_DELEGATION_V1\0" + contract.canonical_release_bytes({
                "policy_id": policy["policy_id"], "policy_generation": policy["generation"],
                "confirmation_requirement": "delegated",
                "authority_policy_hash": installed_policy.sha256,
                "principal_digest": principal_digest, "target_ref": target_ref,
                "transition_digest": transition_digest,
            })).hexdigest()
    if expiry <= now_ms:
        _release_refuse("RELEASE_CONFIRMATION_EXPIRED")
    return contract.validate_release_grant({
        "schema": "mastermind.executive_release_grant/v1",
        "principal_digest": principal_digest,
        "authority_policy_hash": installed_policy.sha256,
        "policy_id": policy["policy_id"], "policy_generation": policy["generation"],
        "action": effect["action"], "target_ref": target_ref,
        "transition_digest": transition_digest,
        "installer_profile_digest": effect["installer_profile_digest"],
        "confirmation_requirement": policy["confirmation_requirement"],
        "confirmation_evidence_digest": confirmation_digest,
        "granted_at_ms": now_ms, "expires_at_ms": expiry,
    })
