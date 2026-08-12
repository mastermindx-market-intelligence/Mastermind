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

PHASE1B_ALLOWED = frozenset({"READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"})
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
