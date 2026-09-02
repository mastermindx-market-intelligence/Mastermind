"""Deterministic contract checks for temporary Sol watcher prompts.

This module is validation-only. It owns no watcher, task store, lifecycle,
action target, transport, retry, cursor, provider session, or persistence.
Managed watcher prompts use a closed, canonically rendered body document;
legacy free-prose bodies remain readable only for migration/audit compatibility.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable, Mapping, Pattern


DISCRIMINATOR = "MMX_SOL_WATCHER_V1"
BODY_DISCRIMINATOR = "MMX_SOL_WATCHER_BODY_V1"
ACCOUNT_EXPORT_SCHEMA = "mastermind.sol_watcher_account_export.v1"

_REQUIRED_FIELDS = (
    "WATCHER_ROLE",
    "OPERATION_KEY",
    "CARRIER",
    "LATEST_HANDLED_EDGE",
    "ACTION_REQUIRED_EVENTS",
    "ACTION_REQUIRED_OUTCOME",
    "SISTER_SOL_POLICY",
)
_ALLOWED_HEADER_FIELDS = frozenset(_REQUIRED_FIELDS)
_SLACK_CARRIER_RE = re.compile(r"^slack:[CGD][A-Z0-9]+/\d{10}\.\d{6}$")
_AGGREGATE_CARRIER_RE = re.compile(r"^aggregate:[a-z0-9][a-z0-9._/-]{2,127}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_EDGE_RE = re.compile(r"^(?:NONE|\d{10}\.\d{6}|[A-Za-z0-9][A-Za-z0-9._:/-]{1,255})$")
_AUDIT_KINDS = frozenset({"SOL_WATCHER", "NON_WATCHER"})

_BODY_SECTIONS = ("ROLE", "SOURCE_LAW", "AUTHORITY")
_BODY_KEYS: dict[str, tuple[str, ...]] = {
    "ROLE": ("ROLE", "EVENTS", "OUTCOME", "RESPONSIBILITY"),
    "SOURCE_LAW": (
        "CURRENT_PROTECTED_REPIN",
        "EXACT_CARRIER_FRESH_READ",
        "NONTERMINAL_RETURN_STATE",
        "SLACK_EXECUTIVE_LIFECYCLE_INFERENCE",
        "BLIND_RETRY",
        "CROSS_CARRIER_FAILOVER",
        "TERMINAL_STOP_BEFORE_DISARM",
    ),
    "AUTHORITY": ("ALLOWED", "FORBIDDEN"),
}


class WatcherRole(str, Enum):
    ACTION_AUTHORITATIVE = "ACTION_AUTHORITATIVE"
    OBSERVER_ONLY = "OBSERVER_ONLY"
    PARENT_ORCHESTRATOR = "PARENT_ORCHESTRATOR"
    TRIAGE_ONLY = "TRIAGE_ONLY"


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class FindingCode(str, Enum):
    MISSING_DISCRIMINATOR = "MISSING_DISCRIMINATOR"
    MISSING_FIELD = "MISSING_FIELD"
    DUPLICATE_FIELD = "DUPLICATE_FIELD"
    UNKNOWN_HEADER_FIELD = "UNKNOWN_HEADER_FIELD"
    INVALID_HEADER_LINE = "INVALID_HEADER_LINE"
    UNKNOWN_ROLE = "UNKNOWN_ROLE"
    INVALID_OPERATION_KEY = "INVALID_OPERATION_KEY"
    INVALID_CARRIER = "INVALID_CARRIER"
    INVALID_HANDLED_EDGE = "INVALID_HANDLED_EDGE"
    ROLE_CONTRACT_MISMATCH = "ROLE_CONTRACT_MISMATCH"
    MISSING_CURRENT_REPIN = "MISSING_CURRENT_REPIN"
    MISSING_CARRIER_FRESHNESS = "MISSING_CARRIER_FRESHNESS"
    MISSING_SAME_CARRIER_ACTION = "MISSING_SAME_CARRIER_ACTION"
    MISSING_TYPED_BLOCKER = "MISSING_TYPED_BLOCKER"
    MISSING_NO_BLIND_RETRY = "MISSING_NO_BLIND_RETRY"
    MISSING_LIFECYCLE_BOUNDARY = "MISSING_LIFECYCLE_BOUNDARY"
    MISSING_TERMINAL_STOP_ORDER = "MISSING_TERMINAL_STOP_ORDER"
    NOTIFICATION_ONLY_SELF_DEADLOCK = "NOTIFICATION_ONLY_SELF_DEADLOCK"
    NON_AUTHORITATIVE_MODIFICATION_FORBIDDEN = "NON_AUTHORITATIVE_MODIFICATION_FORBIDDEN"
    MISSING_BODY_DISCRIMINATOR = "MISSING_BODY_DISCRIMINATOR"
    MISSING_BODY_SECTION = "MISSING_BODY_SECTION"
    DUPLICATE_BODY_SECTION = "DUPLICATE_BODY_SECTION"
    UNKNOWN_BODY_SECTION = "UNKNOWN_BODY_SECTION"
    INVALID_BODY_LINE = "INVALID_BODY_LINE"
    UNKNOWN_BODY_KEY = "UNKNOWN_BODY_KEY"
    DUPLICATE_BODY_KEY = "DUPLICATE_BODY_KEY"
    BODY_CONTRACT_MISMATCH = "BODY_CONTRACT_MISMATCH"
    NONCANONICAL_MANAGED_BODY = "NONCANONICAL_MANAGED_BODY"
    INVALID_TASK = "INVALID_TASK"
    INVALID_TASK_ID = "INVALID_TASK_ID"
    INVALID_ENABLED_FLAG = "INVALID_ENABLED_FLAG"
    DUPLICATE_TASK_ID = "DUPLICATE_TASK_ID"


@dataclass(frozen=True)
class ContractFinding:
    code: FindingCode
    message: str
    severity: Severity = Severity.ERROR
    field: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True)
class PromptAudit:
    valid: bool
    role: WatcherRole | None
    operation_key: str | None
    carrier: str | None
    latest_handled_edge: str | None
    findings: tuple[ContractFinding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "role": self.role.value if self.role else None,
            "operation_key": self.operation_key,
            "carrier": self.carrier,
            "latest_handled_edge": self.latest_handled_edge,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class TaskAudit:
    task_id: str
    title: str
    enabled: bool
    evaluated: bool
    audit_kind: str
    audit: PromptAudit | None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "enabled": self.enabled,
            "evaluated": self.evaluated,
            "audit_kind": self.audit_kind,
            "audit": self.audit.to_dict() if self.audit else None,
        }


@dataclass(frozen=True)
class AuditReport:
    valid: bool
    total_tasks: int
    enabled_tasks: int
    valid_enabled_tasks: int
    invalid_enabled_tasks: int
    invalid_classification_tasks: int
    invalid_export_tasks: int
    duplicate_task_ids: tuple[str, ...]
    tasks: tuple[TaskAudit, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "mastermind.sol_watcher_audit.v1",
            "valid": self.valid,
            "summary": {
                "total_tasks": self.total_tasks,
                "enabled_tasks": self.enabled_tasks,
                "valid_enabled_tasks": self.valid_enabled_tasks,
                "invalid_enabled_tasks": self.invalid_enabled_tasks,
                "invalid_classification_tasks": self.invalid_classification_tasks,
                "invalid_export_tasks": self.invalid_export_tasks,
                "duplicate_task_ids": list(self.duplicate_task_ids),
            },
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class _RoleContract:
    events: frozenset[str]
    outcome: str
    sister_policy: str
    responsibility: str
    allowed: tuple[str, ...]
    forbidden: tuple[str, ...]


_NON_AUTHORITATIVE_FORBIDDEN = (
    "CHILD_CONTINUE",
    "CHILD_RULING",
    "CHILD_REQUEST_REPAIR",
    "CHILD_STOP",
    "DISARM_OTHER_WATCHER",
    "MERGE",
    "RELEASE",
    "RETRY",
    "RESUBMIT",
    "REQUEUE",
    "FAILOVER",
    "SUCCESSOR",
)

_ROLE_CONTRACTS: dict[WatcherRole, _RoleContract] = {
    WatcherRole.ACTION_AUTHORITATIVE: _RoleContract(
        events=frozenset({"BLOCKED", "DECISION_REQUEST", "RESULT"}),
        outcome="SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
        sister_policy="OBSERVE_ONLY_UNLESS_EXACT_ACTION_TARGET",
        responsibility="ACT_NOW",
        allowed=("SAME_CARRIER_SOL_EDGE", "TYPED_BLOCKER", "TERMINAL_STOP"),
        forbidden=(
            "WAIT_FOR_SOL",
            "NOTIFICATION_ONLY",
            "BLIND_RETRY",
            "CROSS_CARRIER_FAILOVER",
        ),
    ),
    WatcherRole.OBSERVER_ONLY: _RoleContract(
        events=frozenset({"NONE"}),
        outcome="OBSERVE_ONLY_NO_MODIFY",
        sister_policy="NEVER_ACT_WITHOUT_CANONICAL_TRANSFER",
        responsibility="NO_CHILD_ACTION",
        allowed=("OBSERVE", "REPORT_DELTA"),
        forbidden=_NON_AUTHORITATIVE_FORBIDDEN,
    ),
    WatcherRole.PARENT_ORCHESTRATOR: _RoleContract(
        events=frozenset({"PARENT_TRANSITION"}),
        outcome="PARENT_EDGE_ONLY_NO_CHILD_RACE",
        sister_policy="NEVER_ACT_ON_DEDICATED_CHILD_RETURN",
        responsibility="NO_CHILD_ACTION",
        allowed=("PARENT_EDGE", "REPORT_DELTA"),
        forbidden=_NON_AUTHORITATIVE_FORBIDDEN,
    ),
    WatcherRole.TRIAGE_ONLY: _RoleContract(
        events=frozenset({"UNCONSUMED_RETURN"}),
        outcome="RECONCILE_OR_REPORT_NO_DUPLICATE",
        sister_policy="NEVER_ELECT_BY_RECENCY",
        responsibility="NO_CHILD_ACTION",
        allowed=("READ_ONLY_RECONCILIATION", "REPORT_BLOCKER"),
        forbidden=_NON_AUTHORITATIVE_FORBIDDEN,
    ),
}


_NOTIFICATION_ONLY_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bsol action required\b", re.IGNORECASE),
    re.compile(r"\bwait(?:ing)? for sol\b", re.IGNORECASE),
    re.compile(r"\bstand by for sol(?:'s)? ruling\b", re.IGNORECASE),
    re.compile(r"\bawait(?:ing)? sol\b", re.IGNORECASE),
    re.compile(r"\bdefer(?:red|ring)? to sol\b", re.IGNORECASE),
    re.compile(r"\bescalate(?:d|s|ing)? to sol\b", re.IGNORECASE),
    re.compile(r"\bpause(?:d|s|ing)? for sol\b", re.IGNORECASE),
)
_NON_AUTHORITATIVE_MODIFICATION_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"\b(?:post(?:s|ed|ing)?|send(?:s|ing)?|sent|issue(?:s|d|ing)?|"
        r"write(?:s|written|ing)?|emit(?:s|ted|ting)?|reply with|respond with)\s+"
        r"(?:(?:an?|the)\s+)?(?:(?:actual|same-carrier|child)\s+)*"
        r"(?:sol\s+)?(?:continue|ruling|request[_ -]?repair|stop)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:merge|release)(?:s|d|ing)?\s+"
        r"(?:the\s+)?(?:pull request|pr|carrier|branch|#\d+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:enable|arm)(?:s|ed|ing)?\s+auto-merge\b", re.IGNORECASE),
    re.compile(r"\b(?:retry|resubmit|requeue|fail\s*over)(?:s|ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\b(?:commission|start)(?:s|ed|ing)?\s+(?:a\s+)?successor\b", re.IGNORECASE),
    re.compile(
        r"(?:^|\b(?:then|please|now)\s+|\bgo ahead and\s+)merge\b"
        r"(?:\s+(?:it|this|now|#\d+|the\s+(?:pr|pull request|carrier|branch)))?"
        r"(?:\s*$|\s*[,;.!?])",
        re.IGNORECASE,
    ),
)
_CURRENT_REPIN_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"\b(?:re-pin|repin|fresh-pin)\b[^,;.!?]{0,180}\bcurrent protected\b",
        re.IGNORECASE,
    ),
)
_CARRIER_FRESHNESS_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"\bfresh-read\b[^,;.!?]{0,180}\bexact (?:carrier|thread)\b",
        re.IGNORECASE,
    ),
)
_SAME_CARRIER_ACTION_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"\b(?:post(?:s|ed|ing)?|send(?:s|ing)?|sent|issue(?:s|d|ing)?|"
        r"write(?:s|written|ing)?|emit(?:s|ted|ting)?)\s+"
        r"(?:the\s+)?(?:actual\s+)?same-carrier\s+sol\s+edge\b",
        re.IGNORECASE,
    ),
)
_TYPED_BLOCKER_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"\b(?:return(?:s|ed|ing)?|report(?:s|ed|ing)?|emit(?:s|ted|ting)?|"
        r"post(?:s|ed|ing)?|send(?:s|ing)?|sent)\s+(?:a\s+)?typed blocker\b",
        re.IGNORECASE,
    ),
)
_TERMINAL_STOP_ORDER_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(
        r"\b(?:send|post|issue|write|emit)(?:s|ed|ing)?\s+(?:the\s+)?terminal stop\b"
        r"[^,;.!?]{0,180}\bbefore\b[^,;.!?]{0,100}\b(?:disarm|disable)(?:s|d|ing)?\b",
        re.IGNORECASE,
    ),
)
_LIFECYCLE_INFERENCE_RE = re.compile(r"\binfer(?:ring|red|s)?\b", re.IGNORECASE)
_ACTION_START = (
    r"(?:do\s+not|don't|never|must\s+not|cannot|can't|if|when|wait|await|defer|"
    r"escalate|pause|post|send|issue|write|emit|reply|respond|merge|release|"
    r"enable|arm|retry|resubmit|requeue|fail|commission|start|infer|re-pin|repin|"
    r"fresh-read|return|report)"
)
_CLAUSE_BOUNDARY_RE = re.compile(
    rf"[;.!?]+|,(?!\s*(?:unless|except)\b)\s*|"
    rf"\b(?:then|but|however|instead|whereas)\b|"
    rf"\band\s+(?={_ACTION_START}\b)",
    re.IGNORECASE,
)
_NEGATOR_RE = re.compile(r"\b(?:do not|don't|never|must not|cannot|can't|no)\b", re.IGNORECASE)
_SCOPE_REVERSER_RE = re.compile(
    r"\b(?:forbid(?:s|den|ding)?|prohibit(?:s|ed|ing)?|reject(?:s|ed|ing)?|"
    r"prevent(?:s|ed|ing)?|disallow(?:s|ed|ing)?|ban(?:s|ned|ning)?|"
    r"fail(?:s|ed|ing)?\s+to|refuse(?:s|d|ing)?\s+to|decline(?:s|d|ing)?\s+to|"
    r"avoid(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
_REQUIRED_EXCEPTION_RE = re.compile(
    r"\b(?:unless|except(?:\s+when)?|optional(?:ly)?|may\s+(?:skip|omit)|"
    r"need\s+not|no\s+need\s+to|not\s+(?:required|necessary|mandatory)|only\s+if)\b",
    re.IGNORECASE,
)
_MARKDOWN_TRANSLATION = str.maketrans("", "", "`*~")
_EXPORT_FINDING_CODES = frozenset(
    {
        FindingCode.INVALID_TASK,
        FindingCode.INVALID_TASK_ID,
        FindingCode.INVALID_ENABLED_FLAG,
        FindingCode.DUPLICATE_TASK_ID,
    }
)


def _finding(
    code: FindingCode,
    message: str,
    *,
    field: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ContractFinding:
    return ContractFinding(code=code, message=message, field=field, severity=severity)


def _audit_from_findings(findings: Iterable[ContractFinding]) -> PromptAudit:
    frozen = tuple(findings)
    return PromptAudit(
        valid=not any(finding.severity is Severity.ERROR for finding in frozen),
        role=None,
        operation_key=None,
        carrier=None,
        latest_handled_edge=None,
        findings=frozen,
    )


def _with_finding(audit: PromptAudit, finding: ContractFinding) -> PromptAudit:
    findings = audit.findings + (finding,)
    return PromptAudit(
        valid=False,
        role=audit.role,
        operation_key=audit.operation_key,
        carrier=audit.carrier,
        latest_handled_edge=audit.latest_handled_edge,
        findings=findings,
    )


def _coerce_role(role: WatcherRole | str) -> WatcherRole:
    if isinstance(role, WatcherRole):
        return role
    return WatcherRole(str(role))


def _event_text(events: frozenset[str]) -> str:
    return ",".join(sorted(events))


def _managed_body_values(role: WatcherRole) -> dict[str, dict[str, str]]:
    contract = _ROLE_CONTRACTS[role]
    return {
        "ROLE": {
            "ROLE": role.value,
            "EVENTS": _event_text(contract.events),
            "OUTCOME": contract.outcome,
            "RESPONSIBILITY": contract.responsibility,
        },
        "SOURCE_LAW": {
            "CURRENT_PROTECTED_REPIN": "REQUIRED",
            "EXACT_CARRIER_FRESH_READ": "REQUIRED",
            "NONTERMINAL_RETURN_STATE": "OPEN",
            "SLACK_EXECUTIVE_LIFECYCLE_INFERENCE": "FORBIDDEN",
            "BLIND_RETRY": "FORBIDDEN",
            "CROSS_CARRIER_FAILOVER": "FORBIDDEN",
            "TERMINAL_STOP_BEFORE_DISARM": "REQUIRED",
        },
        "AUTHORITY": {
            "ALLOWED": ",".join(contract.allowed),
            "FORBIDDEN": ",".join(contract.forbidden),
        },
    }


def render_watcher_body(role: WatcherRole | str) -> str:
    """Render the one canonical managed body for a watcher role."""

    resolved = _coerce_role(role)
    values = _managed_body_values(resolved)
    lines = [BODY_DISCRIMINATOR]
    for section in _BODY_SECTIONS:
        lines.append(f"[{section}]")
        for key in _BODY_KEYS[section]:
            lines.append(f"{key}: {values[section][key]}")
        lines.append(f"[/{section}]")
    return "\n".join(lines)


def render_watcher_prompt(
    *,
    role: WatcherRole | str,
    operation_key: str,
    carrier: str,
    latest_handled_edge: str = "NONE",
) -> str:
    """Render an exact-header/exact-body managed watcher prompt."""

    resolved = _coerce_role(role)
    if not _OPERATION_RE.fullmatch(operation_key):
        raise ValueError("operation_key is invalid")
    if not _carrier_is_valid_for_role(carrier, resolved):
        raise ValueError("carrier is invalid for role")
    if not _EDGE_RE.fullmatch(latest_handled_edge):
        raise ValueError("latest_handled_edge is invalid")
    contract = _ROLE_CONTRACTS[resolved]
    header = "\n".join(
        (
            DISCRIMINATOR,
            f"WATCHER_ROLE: {resolved.value}",
            f"OPERATION_KEY: {operation_key}",
            f"CARRIER: {carrier}",
            f"LATEST_HANDLED_EDGE: {latest_handled_edge}",
            f"ACTION_REQUIRED_EVENTS: {_event_text(contract.events)}",
            f"ACTION_REQUIRED_OUTCOME: {contract.outcome}",
            f"SISTER_SOL_POLICY: {contract.sister_policy}",
        )
    )
    return f"{header}\n\n{render_watcher_body(resolved)}"


def _parse_prompt(prompt: str) -> tuple[dict[str, str], str, list[ContractFinding]]:
    findings: list[ContractFinding] = []
    if not isinstance(prompt, str):
        return {}, "", [
            _finding(FindingCode.INVALID_TASK, "prompt must be a string", field="prompt")
        ]

    lines = prompt.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].lstrip("\ufeff") != DISCRIMINATOR:
        findings.append(
            _finding(
                FindingCode.MISSING_DISCRIMINATOR,
                f"first line must be exactly {DISCRIMINATOR}",
            )
        )

    headers: dict[str, str] = {}
    body_start = len(lines)
    for index, line in enumerate(lines[1:], start=1):
        if not line.strip():
            body_start = index + 1
            break
        if ":" not in line:
            findings.append(
                _finding(
                    FindingCode.INVALID_HEADER_LINE,
                    "every watcher header line must be one allowed KEY: value field",
                    field=f"line_{index + 1}",
                )
            )
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
        if key not in _ALLOWED_HEADER_FIELDS:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN_HEADER_FIELD,
                    f"unknown watcher header field {key!r}",
                    field=key or f"line_{index + 1}",
                )
            )
            continue
        if key in headers:
            findings.append(
                _finding(
                    FindingCode.DUPLICATE_FIELD,
                    f"duplicate watcher header {key}",
                    field=key,
                )
            )
            continue
        headers[key] = value

    body = "\n".join(lines[body_start:]).rstrip("\n")
    return headers, body, findings


def _parse_managed_body(
    body: str,
) -> tuple[dict[str, dict[str, str]], list[ContractFinding]]:
    findings: list[ContractFinding] = []
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0] != BODY_DISCRIMINATOR:
        return {}, [
            _finding(
                FindingCode.MISSING_BODY_DISCRIMINATOR,
                f"managed body must start with {BODY_DISCRIMINATOR}",
            )
        ]

    sections: dict[str, dict[str, str]] = {}
    order: list[str] = []
    current: str | None = None
    for index, raw_line in enumerate(lines[1:], start=2):
        line = raw_line.strip()
        if not line:
            findings.append(
                _finding(
                    FindingCode.INVALID_BODY_LINE,
                    "managed body cannot contain blank lines",
                    field=f"body_line_{index}",
                )
            )
            continue
        if line.startswith("[/") and line.endswith("]"):
            name = line[2:-1]
            if current != name:
                findings.append(
                    _finding(
                        FindingCode.INVALID_BODY_LINE,
                        "managed body section close is mismatched",
                        field=f"body_line_{index}",
                    )
                )
            current = None
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            if name not in _BODY_SECTIONS:
                findings.append(
                    _finding(
                        FindingCode.UNKNOWN_BODY_SECTION,
                        f"unknown managed body section {name!r}",
                        field=name,
                    )
                )
                current = None
                continue
            if name in sections:
                findings.append(
                    _finding(
                        FindingCode.DUPLICATE_BODY_SECTION,
                        f"duplicate managed body section {name}",
                        field=name,
                    )
                )
                current = name
                continue
            sections[name] = {}
            order.append(name)
            current = name
            continue
        if current is None or ":" not in line:
            findings.append(
                _finding(
                    FindingCode.INVALID_BODY_LINE,
                    "managed body lines must be inside a named section and use KEY: value",
                    field=f"body_line_{index}",
                )
            )
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
        if key not in _BODY_KEYS[current]:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN_BODY_KEY,
                    f"unknown key {key!r} in {current}",
                    field=f"{current}.{key}",
                )
            )
            continue
        if key in sections[current]:
            findings.append(
                _finding(
                    FindingCode.DUPLICATE_BODY_KEY,
                    f"duplicate key {key} in {current}",
                    field=f"{current}.{key}",
                )
            )
            continue
        sections[current][key] = value

    if current is not None:
        findings.append(
            _finding(
                FindingCode.INVALID_BODY_LINE,
                f"managed body section {current} is not closed",
                field=current,
            )
        )
    for section in _BODY_SECTIONS:
        if section not in sections:
            findings.append(
                _finding(
                    FindingCode.MISSING_BODY_SECTION,
                    f"missing managed body section {section}",
                    field=section,
                )
            )
    if order != [section for section in _BODY_SECTIONS if section in sections]:
        findings.append(
            _finding(
                FindingCode.NONCANONICAL_MANAGED_BODY,
                "managed body sections are not in canonical order",
            )
        )
    return sections, findings


def _validate_managed_body(body: str, role: WatcherRole | None) -> list[ContractFinding]:
    sections, findings = _parse_managed_body(body)
    if role is None:
        return findings
    expected = _managed_body_values(role)
    for section in _BODY_SECTIONS:
        observed = sections.get(section)
        if observed is None:
            continue
        expected_keys = set(_BODY_KEYS[section])
        missing = sorted(expected_keys - set(observed))
        if missing:
            findings.append(
                _finding(
                    FindingCode.BODY_CONTRACT_MISMATCH,
                    f"{section} is missing required keys: {','.join(missing)}",
                    field=section,
                )
            )
        for key in _BODY_KEYS[section]:
            if key in observed and observed[key] != expected[section][key]:
                findings.append(
                    _finding(
                        FindingCode.BODY_CONTRACT_MISMATCH,
                        f"{section}.{key} does not match the closed {role.value} contract",
                        field=f"{section}.{key}",
                    )
                )
    if body != render_watcher_body(role):
        findings.append(
            _finding(
                FindingCode.NONCANONICAL_MANAGED_BODY,
                "managed body must equal the canonical role renderer byte-for-byte",
            )
        )
    return findings


def _normalized_events(raw: str) -> frozenset[str]:
    return frozenset(part.strip().upper() for part in raw.split(",") if part.strip())


def _scan_line(raw_line: str) -> str:
    return " ".join(raw_line.casefold().translate(_MARKDOWN_TRANSLATION).split())


def _scan_clauses(text: str) -> Iterable[str]:
    for raw_line in text.splitlines():
        normalized = _scan_line(raw_line)
        if not normalized:
            continue
        start = 0
        for boundary in _CLAUSE_BOUNDARY_RE.finditer(normalized):
            clause = normalized[start : boundary.start()].strip()
            if clause:
                yield clause
            start = boundary.end()
        clause = normalized[start:].strip()
        if clause:
            yield clause


def _match_polarity(clause: str, start: int) -> str:
    prefix = clause[:start]
    negators = list(_NEGATOR_RE.finditer(prefix))
    if not negators:
        return "POSITIVE"
    closest = negators[-1]
    governed_prefix = prefix[closest.end() :]
    if _SCOPE_REVERSER_RE.search(governed_prefix):
        return "REVERSED"
    return "NEGATED"


def _phrase_polarities(
    text: str, patterns: tuple[Pattern[str], ...]
) -> tuple[bool, bool, bool, bool]:
    positive = False
    negated = False
    reversed_scope = False
    excepted = False
    for clause in _scan_clauses(text):
        for pattern in patterns:
            for match in pattern.finditer(clause):
                if _REQUIRED_EXCEPTION_RE.search(clause):
                    excepted = True
                polarity = _match_polarity(clause, match.start())
                if polarity == "NEGATED":
                    negated = True
                elif polarity == "REVERSED":
                    reversed_scope = True
                else:
                    positive = True
    return positive, negated, reversed_scope, excepted


def _contains_positive_phrase(text: str, patterns: tuple[Pattern[str], ...]) -> bool:
    positive, _negated, reversed_scope, _excepted = _phrase_polarities(text, patterns)
    return positive or reversed_scope


def _contains_required_positive_phrase(
    text: str, patterns: tuple[Pattern[str], ...]
) -> bool:
    positive, negated, reversed_scope, excepted = _phrase_polarities(text, patterns)
    return positive and not negated and not reversed_scope and not excepted


def _contains_no_blind_retry(text: str) -> bool:
    saw = False
    occurrence = re.compile(r"\b(?:blind[- ]retry|retry\s+blindly)\b", re.IGNORECASE)
    accepted = (
        re.compile(r"^no\s+blind[- ]retry\b.*\b(?:permitted|allowed)\b", re.IGNORECASE),
        re.compile(
            r"^blind[- ]retry\s+(?:is\s+)?(?:forbidden|prohibited|disallowed|not\s+permitted|not\s+allowed)\b",
            re.IGNORECASE,
        ),
        re.compile(r"^(?:never|do\s+not|don't|must\s+not)\s+retry\s+blindly\b", re.IGNORECASE),
    )
    rejected_double_negative = re.compile(
        r"\b(?:do\s+not|never)\s+(?:forbid|reject|prevent|disallow)\b|"
        r"\bno\s+blind[- ]retry\s+prohibition\b",
        re.IGNORECASE,
    )
    for clause in _scan_clauses(text):
        if not occurrence.search(clause):
            continue
        if _REQUIRED_EXCEPTION_RE.search(clause) or rejected_double_negative.search(clause):
            return False
        if not any(pattern.search(clause) for pattern in accepted):
            return False
        saw = True
    return saw


def _contains_lifecycle_refusal(text: str) -> bool:
    saw = False
    for clause in _scan_clauses(text):
        if not (
            _LIFECYCLE_INFERENCE_RE.search(clause)
            and "executive" in clause
            and "lifecycle" in clause
            and "slack" in clause
        ):
            continue
        if _REQUIRED_EXCEPTION_RE.search(clause):
            return False
        for match in _LIFECYCLE_INFERENCE_RE.finditer(clause):
            if _match_polarity(clause, match.start()) != "NEGATED":
                return False
            saw = True
    return saw


def _carrier_is_valid_for_role(carrier: str, role: WatcherRole | None) -> bool:
    if _SLACK_CARRIER_RE.fullmatch(carrier):
        return True
    if not _AGGREGATE_CARRIER_RE.fullmatch(carrier):
        return False
    return role in {
        WatcherRole.OBSERVER_ONLY,
        WatcherRole.PARENT_ORCHESTRATOR,
        WatcherRole.TRIAGE_ONLY,
    }


def _validate_legacy_body(body: str, role: WatcherRole | None) -> list[ContractFinding]:
    findings: list[ContractFinding] = []
    if not _contains_required_positive_phrase(body, _CURRENT_REPIN_PATTERNS):
        findings.append(
            _finding(
                FindingCode.MISSING_CURRENT_REPIN,
                "prompt must positively require re-pinning the CURRENT protected Skillpack",
            )
        )
    if not _contains_required_positive_phrase(body, _CARRIER_FRESHNESS_PATTERNS):
        findings.append(
            _finding(
                FindingCode.MISSING_CARRIER_FRESHNESS,
                "prompt must positively require a fresh-read of the exact carrier/thread",
            )
        )
    if not _contains_no_blind_retry(body):
        findings.append(
            _finding(
                FindingCode.MISSING_NO_BLIND_RETRY,
                "prompt must explicitly forbid blind retry",
            )
        )
    if not _contains_lifecycle_refusal(body):
        findings.append(
            _finding(
                FindingCode.MISSING_LIFECYCLE_BOUNDARY,
                "prompt must explicitly refuse inferring Executive lifecycle from Slack delivery",
            )
        )
    if role is WatcherRole.ACTION_AUTHORITATIVE:
        if not _contains_required_positive_phrase(body, _SAME_CARRIER_ACTION_PATTERNS):
            findings.append(
                _finding(
                    FindingCode.MISSING_SAME_CARRIER_ACTION,
                    "action-authoritative watcher must positively require the same-carrier Sol edge",
                )
            )
        if not _contains_required_positive_phrase(body, _TYPED_BLOCKER_PATTERNS):
            findings.append(
                _finding(
                    FindingCode.MISSING_TYPED_BLOCKER,
                    "action-authoritative watcher must positively require a typed blocker",
                )
            )
        if not _contains_required_positive_phrase(body, _TERMINAL_STOP_ORDER_PATTERNS):
            findings.append(
                _finding(
                    FindingCode.MISSING_TERMINAL_STOP_ORDER,
                    "terminal STOP must be positively ordered before child watcher disarm",
                )
            )
        if _contains_positive_phrase(body, _NOTIFICATION_ONLY_PATTERNS):
            findings.append(
                _finding(
                    FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK,
                    "action-authoritative watcher cannot wait for the Sol role it already represents",
                )
            )
    if role in {
        WatcherRole.OBSERVER_ONLY,
        WatcherRole.PARENT_ORCHESTRATOR,
        WatcherRole.TRIAGE_ONLY,
    } and _contains_positive_phrase(body, _NON_AUTHORITATIVE_MODIFICATION_PATTERNS):
        findings.append(
            _finding(
                FindingCode.NON_AUTHORITATIVE_MODIFICATION_FORBIDDEN,
                "non-authoritative watcher cannot claim modification, retry, release, or successor authority",
            )
        )
    return findings


def validate_watcher_prompt(prompt: str) -> PromptAudit:
    """Validate one prompt without executing or mutating anything."""

    headers, body, findings = _parse_prompt(prompt)
    for field in _REQUIRED_FIELDS:
        if not headers.get(field):
            findings.append(
                _finding(
                    FindingCode.MISSING_FIELD,
                    f"missing required watcher field {field}",
                    field=field,
                )
            )

    role: WatcherRole | None = None
    raw_role = headers.get("WATCHER_ROLE")
    if raw_role:
        try:
            role = WatcherRole(raw_role)
        except ValueError:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN_ROLE,
                    f"unknown watcher role {raw_role!r}",
                    field="WATCHER_ROLE",
                )
            )

    operation_key = headers.get("OPERATION_KEY")
    if operation_key and not _OPERATION_RE.fullmatch(operation_key):
        findings.append(
            _finding(
                FindingCode.INVALID_OPERATION_KEY,
                "operation key must be a stable non-whitespace identifier",
                field="OPERATION_KEY",
            )
        )

    carrier = headers.get("CARRIER")
    if carrier and not _carrier_is_valid_for_role(carrier, role):
        findings.append(
            _finding(
                FindingCode.INVALID_CARRIER,
                (
                    "ACTION_AUTHORITATIVE requires slack:<channel-id>/<parent-ts>; "
                    "observer, parent and triage roles may instead use aggregate:<stable-scope-id>"
                ),
                field="CARRIER",
            )
        )

    latest_handled_edge = headers.get("LATEST_HANDLED_EDGE")
    if latest_handled_edge and not _EDGE_RE.fullmatch(latest_handled_edge):
        findings.append(
            _finding(
                FindingCode.INVALID_HANDLED_EDGE,
                "latest handled edge must be NONE, a Slack timestamp, or a stable semantic-edge identifier",
                field="LATEST_HANDLED_EDGE",
            )
        )

    if role is not None:
        expected = _ROLE_CONTRACTS[role]
        observed_events = _normalized_events(headers.get("ACTION_REQUIRED_EVENTS", ""))
        if (
            observed_events != expected.events
            or headers.get("ACTION_REQUIRED_OUTCOME", "") != expected.outcome
            or headers.get("SISTER_SOL_POLICY", "") != expected.sister_policy
        ):
            findings.append(
                _finding(
                    FindingCode.ROLE_CONTRACT_MISMATCH,
                    (
                        f"{role.value} requires events={_event_text(expected.events)}, "
                        f"outcome={expected.outcome}, sister_policy={expected.sister_policy}"
                    ),
                    field="WATCHER_ROLE",
                )
            )

    if body.startswith(BODY_DISCRIMINATOR):
        findings.extend(_validate_managed_body(body, role))
    else:
        findings.extend(_validate_legacy_body(body, role))

    frozen = tuple(findings)
    return PromptAudit(
        valid=not any(finding.severity is Severity.ERROR for finding in frozen),
        role=role,
        operation_key=operation_key,
        carrier=carrier,
        latest_handled_edge=latest_handled_edge,
        findings=frozen,
    )


def _normalize_task_id(value: Any, *, field: str) -> tuple[str | None, ContractFinding | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _finding(
            FindingCode.INVALID_TASK_ID,
            f"{field} must be a non-empty string",
            field=field,
        )
    return value.strip(), None


def _extract_task_id(raw: Mapping[str, Any], index: int) -> tuple[str, list[ContractFinding]]:
    findings: list[ContractFinding] = []
    has_id = "id" in raw
    has_task_id = "task_id" in raw
    if not has_id and not has_task_id:
        return f"invalid-task-{index}", [
            _finding(
                FindingCode.INVALID_TASK_ID,
                "task export must contain id or task_id",
                field="id",
            )
        ]

    normalized_id: str | None = None
    normalized_task_id: str | None = None
    if has_id:
        normalized_id, finding = _normalize_task_id(raw.get("id"), field="id")
        if finding:
            findings.append(finding)
    if has_task_id:
        normalized_task_id, finding = _normalize_task_id(
            raw.get("task_id"), field="task_id"
        )
        if finding:
            findings.append(finding)
    if (
        normalized_id is not None
        and normalized_task_id is not None
        and normalized_id != normalized_task_id
    ):
        findings.append(
            _finding(
                FindingCode.INVALID_TASK_ID,
                "id and task_id disagree after normalization",
                field="id",
            )
        )
    return normalized_id or normalized_task_id or f"invalid-task-{index}", findings


def _extract_enabled(raw: Mapping[str, Any]) -> tuple[bool, list[ContractFinding]]:
    findings: list[ContractFinding] = []
    fields = [field for field in ("is_enabled", "enabled") if field in raw]
    if not fields:
        return False, [
            _finding(
                FindingCode.INVALID_ENABLED_FLAG,
                "task export must contain a JSON boolean is_enabled or enabled field",
                field="is_enabled",
            )
        ]
    normalized: dict[str, bool] = {}
    for field in fields:
        value = raw.get(field)
        if not isinstance(value, bool):
            findings.append(
                _finding(
                    FindingCode.INVALID_ENABLED_FLAG,
                    f"{field} must be a JSON boolean, not a string or number",
                    field=field,
                )
            )
        else:
            normalized[field] = value
    if (
        "is_enabled" in normalized
        and "enabled" in normalized
        and normalized["is_enabled"] != normalized["enabled"]
    ):
        findings.append(
            _finding(
                FindingCode.INVALID_ENABLED_FLAG,
                "is_enabled and enabled disagree",
                field="is_enabled",
            )
        )
    return normalized.get("is_enabled", normalized.get("enabled", False)), findings


def canonical_account_export(
    tasks: Iterable[Mapping[str, Any]],
) -> dict[str, object]:
    """Return a stable, secret-neutral account-export candidate for read/write replay."""

    canonical: list[dict[str, object]] = []
    for index, raw in enumerate(tasks):
        if not isinstance(raw, Mapping):
            raise ValueError("every task must be a mapping")
        task_id, id_findings = _extract_task_id(raw, index)
        enabled, enabled_findings = _extract_enabled(raw)
        if id_findings or enabled_findings:
            raise ValueError("task identity and enabled state must already be valid")
        audit_kind = raw.get("audit_kind", "SOL_WATCHER")
        if not isinstance(audit_kind, str) or audit_kind.strip().upper() not in _AUDIT_KINDS:
            raise ValueError("audit_kind is invalid")
        prompt = raw.get("prompt", "")
        if not isinstance(prompt, str):
            raise ValueError("prompt must be a string")
        canonical.append(
            {
                "id": task_id,
                "task_id": task_id,
                "title": str(raw.get("title") or ""),
                "is_enabled": enabled,
                "audit_kind": audit_kind.strip().upper(),
                "prompt": prompt,
            }
        )
    canonical.sort(key=lambda item: (str(item["id"]), str(item["title"])))
    return {
        "payload_kind": "ACCOUNT_EXPORT",
        "schema": ACCOUNT_EXPORT_SCHEMA,
        "tasks": canonical,
    }


def audit_tasks(
    tasks: Iterable[Mapping[str, Any]],
    *,
    require_managed_body: bool = False,
) -> AuditReport:
    """Audit an account-local task export without contacting or mutating a task store."""

    materialized = list(tasks)
    candidate_ids: list[str] = []
    for index, raw in enumerate(materialized):
        if not isinstance(raw, Mapping):
            continue
        task_id, _findings = _extract_task_id(raw, index)
        if not task_id.startswith("invalid-task-"):
            candidate_ids.append(task_id)

    duplicate_task_ids = tuple(
        sorted(task_id for task_id, count in Counter(candidate_ids).items() if count > 1)
    )
    duplicate_set = set(duplicate_task_ids)
    results: list[TaskAudit] = []

    for index, raw in enumerate(materialized):
        if not isinstance(raw, Mapping):
            results.append(
                TaskAudit(
                    task_id=f"invalid-task-{index}",
                    title="",
                    enabled=False,
                    evaluated=True,
                    audit_kind="INVALID",
                    audit=_audit_from_findings(
                        [
                            _finding(
                                FindingCode.INVALID_TASK,
                                "every task must be a JSON object",
                                field="task",
                            )
                        ]
                    ),
                )
            )
            continue

        task_id, wrapper_findings = _extract_task_id(raw, index)
        enabled, enabled_findings = _extract_enabled(raw)
        wrapper_findings.extend(enabled_findings)
        title = str(raw.get("title") or "")
        raw_audit_kind = raw.get("audit_kind", "SOL_WATCHER")
        if not isinstance(raw_audit_kind, str):
            audit_kind = "INVALID"
            wrapper_findings.append(
                _finding(
                    FindingCode.INVALID_TASK,
                    "audit_kind must be a string",
                    field="audit_kind",
                )
            )
        else:
            audit_kind = raw_audit_kind.strip().upper()
        if audit_kind not in _AUDIT_KINDS:
            wrapper_findings.append(
                _finding(
                    FindingCode.INVALID_TASK,
                    f"unknown audit_kind {audit_kind!r}",
                    field="audit_kind",
                )
            )
        if task_id in duplicate_set:
            wrapper_findings.append(
                _finding(
                    FindingCode.DUPLICATE_TASK_ID,
                    f"duplicate native task id {task_id!r}",
                    field="id",
                )
            )

        if wrapper_findings:
            results.append(
                TaskAudit(
                    task_id=task_id,
                    title=title,
                    enabled=enabled,
                    evaluated=True,
                    audit_kind=audit_kind,
                    audit=_audit_from_findings(wrapper_findings),
                )
            )
            continue

        if not enabled or audit_kind == "NON_WATCHER":
            results.append(
                TaskAudit(
                    task_id=task_id,
                    title=title,
                    enabled=enabled,
                    evaluated=False,
                    audit_kind=audit_kind,
                    audit=None,
                )
            )
            continue

        prompt = raw.get("prompt", "")
        audit = validate_watcher_prompt(prompt)
        _headers, body, _findings = _parse_prompt(prompt)
        if require_managed_body and not body.startswith(BODY_DISCRIMINATOR):
            audit = _with_finding(
                audit,
                _finding(
                    FindingCode.NONCANONICAL_MANAGED_BODY,
                    "managed account exports require the canonical structured watcher body",
                    field="prompt",
                ),
            )
        results.append(
            TaskAudit(
                task_id=task_id,
                title=title,
                enabled=True,
                evaluated=True,
                audit_kind=audit_kind,
                audit=audit,
            )
        )

    enabled_results = [
        result
        for result in results
        if result.enabled and result.audit_kind == "SOL_WATCHER"
    ]
    valid_count = sum(bool(result.audit and result.audit.valid) for result in enabled_results)
    invalid_count = len(enabled_results) - valid_count
    invalid_classification_count = sum(
        bool(
            result.audit
            and any(
                finding.code is FindingCode.INVALID_TASK
                and finding.field == "audit_kind"
                for finding in result.audit.findings
            )
        )
        for result in results
    )
    invalid_export_count = sum(
        bool(
            result.audit
            and any(finding.code in _EXPORT_FINDING_CODES for finding in result.audit.findings)
        )
        for result in results
    )
    return AuditReport(
        valid=(
            invalid_count == 0
            and invalid_classification_count == 0
            and invalid_export_count == 0
        ),
        total_tasks=len(results),
        enabled_tasks=len(enabled_results),
        valid_enabled_tasks=valid_count,
        invalid_enabled_tasks=invalid_count,
        invalid_classification_tasks=invalid_classification_count,
        invalid_export_tasks=invalid_export_count,
        duplicate_task_ids=duplicate_task_ids,
        tasks=tuple(results),
    )
