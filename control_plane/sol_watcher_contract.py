"""Deterministic contract checks for temporary Sol watcher prompts.

This module is validation-only. It owns no watcher, task store, lifecycle,
action target, transport, retry, cursor, provider session, or persistence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable, Mapping, Pattern


DISCRIMINATOR = "MMX_SOL_WATCHER_V1"
_REQUIRED_FIELDS = (
    "WATCHER_ROLE",
    "OPERATION_KEY",
    "CARRIER",
    "LATEST_HANDLED_EDGE",
    "ACTION_REQUIRED_EVENTS",
    "ACTION_REQUIRED_OUTCOME",
    "SISTER_SOL_POLICY",
)
_SLACK_CARRIER_RE = re.compile(r"^slack:[CGD][A-Z0-9]+/\d{10}\.\d{6}$")
_AGGREGATE_CARRIER_RE = re.compile(r"^aggregate:[a-z0-9][a-z0-9._/-]{2,127}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_EDGE_RE = re.compile(r"^(?:NONE|\d{10}\.\d{6}|[A-Za-z0-9][A-Za-z0-9._:/-]{1,255})$")
_AUDIT_KINDS = frozenset({"SOL_WATCHER", "NON_WATCHER"})


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


_ROLE_CONTRACTS: dict[WatcherRole, tuple[frozenset[str], str, str]] = {
    WatcherRole.ACTION_AUTHORITATIVE: (
        frozenset({"BLOCKED", "DECISION_REQUEST", "RESULT"}),
        "SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
        "OBSERVE_ONLY_UNLESS_EXACT_ACTION_TARGET",
    ),
    WatcherRole.OBSERVER_ONLY: (
        frozenset({"NONE"}),
        "OBSERVE_ONLY_NO_MODIFY",
        "NEVER_ACT_WITHOUT_CANONICAL_TRANSFER",
    ),
    WatcherRole.PARENT_ORCHESTRATOR: (
        frozenset({"PARENT_TRANSITION"}),
        "PARENT_EDGE_ONLY_NO_CHILD_RACE",
        "NEVER_ACT_ON_DEDICATED_CHILD_RETURN",
    ),
    WatcherRole.TRIAGE_ONLY: (
        frozenset({"UNCONSUMED_RETURN"}),
        "RECONCILE_OR_REPORT_NO_DUPLICATE",
        "NEVER_ELECT_BY_RECENCY",
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
        r"\b(?:post|send|issue|write|emit|reply with|respond with)\s+"
        r"(?:an?\s+)?(?:sol\s+)?(?:continue|ruling|request[_ -]?repair|stop)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:merge|release)\s+(?:the\s+)?(?:pull request|pr|carrier|branch)\b", re.IGNORECASE),
    re.compile(r"\b(?:enable|arm)\s+auto-merge\b", re.IGNORECASE),
    re.compile(r"\b(?:retry|resubmit|requeue|fail\s*over)\b", re.IGNORECASE),
    re.compile(r"\b(?:commission|start)\s+(?:a\s+)?successor\b", re.IGNORECASE),
)
_REJECTION_MARKERS = (
    "do not",
    "don't",
    "never",
    "must not",
    "cannot",
    "can't",
    "forbidden",
    "reject",
    "rejected",
    "invalid",
    "anti-pattern",
    "antipattern",
    "failure",
    "fails",
)
_CLAUSE_BOUNDARY_RE = re.compile(r"[;.!?]|\b(?:but|however|instead|whereas)\b", re.IGNORECASE)
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


def _parse_prompt(prompt: str) -> tuple[dict[str, str], str, list[ContractFinding]]:
    findings: list[ContractFinding] = []
    if not isinstance(prompt, str):
        return {}, "", [_finding(FindingCode.INVALID_TASK, "prompt must be a string", field="prompt")]

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
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
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

    body = "\n".join(lines[body_start:])
    return headers, body, findings


def _normalized_events(raw: str) -> frozenset[str]:
    values = {part.strip().upper() for part in raw.split(",") if part.strip()}
    return frozenset(values)


def _clause_containing(text: str, start: int, end: int) -> str:
    previous_end = 0
    next_start = len(text)
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text):
        if boundary.end() <= start:
            previous_end = boundary.end()
            continue
        if boundary.start() >= end:
            next_start = boundary.start()
            break
    return text[previous_end:next_start].strip()


def _contains_positive_phrase(text: str, patterns: tuple[Pattern[str], ...]) -> bool:
    for raw_line in text.splitlines():
        normalized = " ".join(raw_line.casefold().split())
        if not normalized:
            continue
        for pattern in patterns:
            for match in pattern.finditer(normalized):
                clause = _clause_containing(normalized, match.start(), match.end())
                if any(marker in clause for marker in _REJECTION_MARKERS):
                    continue
                return True
    return False


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


def validate_watcher_prompt(prompt: str) -> PromptAudit:
    """Validate one prompt without executing or mutating anything."""

    headers, body, findings = _parse_prompt(prompt)

    for field in _REQUIRED_FIELDS:
        if not headers.get(field):
            findings.append(
                _finding(FindingCode.MISSING_FIELD, f"missing required watcher field {field}", field=field)
            )

    role: WatcherRole | None = None
    raw_role = headers.get("WATCHER_ROLE")
    if raw_role:
        try:
            role = WatcherRole(raw_role)
        except ValueError:
            findings.append(
                _finding(FindingCode.UNKNOWN_ROLE, f"unknown watcher role {raw_role!r}", field="WATCHER_ROLE")
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
        expected_events, expected_outcome, expected_policy = _ROLE_CONTRACTS[role]
        observed_events = _normalized_events(headers.get("ACTION_REQUIRED_EVENTS", ""))
        observed_outcome = headers.get("ACTION_REQUIRED_OUTCOME", "")
        observed_policy = headers.get("SISTER_SOL_POLICY", "")
        if (
            observed_events != expected_events
            or observed_outcome != expected_outcome
            or observed_policy != expected_policy
        ):
            findings.append(
                _finding(
                    FindingCode.ROLE_CONTRACT_MISMATCH,
                    (
                        f"{role.value} requires events={','.join(sorted(expected_events))}, "
                        f"outcome={expected_outcome}, sister_policy={expected_policy}"
                    ),
                    field="WATCHER_ROLE",
                )
            )

    folded = " ".join(body.casefold().split())
    if not re.search(r"\b(?:re-pin|repin|fresh-pin)\b", folded) or "current protected" not in folded:
        findings.append(
            _finding(
                FindingCode.MISSING_CURRENT_REPIN,
                "prompt must re-pin the CURRENT protected Skillpack before modifying action",
            )
        )
    if "fresh-read" not in folded or not ("exact carrier" in folded or "exact thread" in folded):
        findings.append(
            _finding(
                FindingCode.MISSING_CARRIER_FRESHNESS,
                "prompt must fresh-read the exact carrier/thread before substantive output",
            )
        )
    if not ("no blind retry" in folded or "never blind-retry" in folded):
        findings.append(
            _finding(
                FindingCode.MISSING_NO_BLIND_RETRY,
                "prompt must explicitly forbid blind retry",
            )
        )
    if not ("executive job" in folded and "lifecycle" in folded and "slack" in folded):
        findings.append(
            _finding(
                FindingCode.MISSING_LIFECYCLE_BOUNDARY,
                "prompt must preserve Executive lifecycle ownership and refuse Slack lifecycle inference",
            )
        )

    if role is WatcherRole.ACTION_AUTHORITATIVE:
        if not ("same-carrier" in folded and "sol edge" in folded):
            findings.append(
                _finding(
                    FindingCode.MISSING_SAME_CARRIER_ACTION,
                    "action-authoritative watcher must post the actual same-carrier Sol edge",
                )
            )
        if "typed blocker" not in folded:
            findings.append(
                _finding(
                    FindingCode.MISSING_TYPED_BLOCKER,
                    "action-authoritative watcher must return a typed blocker when action cannot occur",
                )
            )
        if not ("terminal stop" in folded and ("before disarm" in folded or "before disabling" in folded)):
            findings.append(
                _finding(
                    FindingCode.MISSING_TERMINAL_STOP_ORDER,
                    "terminal STOP must precede child watcher disarm",
                )
            )
        if _contains_positive_phrase(body, _NOTIFICATION_ONLY_PATTERNS):
            findings.append(
                _finding(
                    FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK,
                    "action-authoritative watcher cannot terminate by waiting for the Sol role it already represents",
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
                "non-authoritative watcher cannot claim child modification, retry, release, or successor authority",
            )
        )

    findings_tuple = tuple(findings)
    return PromptAudit(
        valid=not any(finding.severity is Severity.ERROR for finding in findings_tuple),
        role=role,
        operation_key=operation_key,
        carrier=carrier,
        latest_handled_edge=latest_handled_edge,
        findings=findings_tuple,
    )


def _extract_task_id(raw: Mapping[str, Any], index: int) -> tuple[str, list[ContractFinding]]:
    findings: list[ContractFinding] = []
    has_id = "id" in raw
    has_task_id = "task_id" in raw
    if not has_id and not has_task_id:
        return f"invalid-task-{index}", [
            _finding(FindingCode.INVALID_TASK_ID, "task export must contain id or task_id", field="id")
        ]
    primary = raw.get("id") if has_id else raw.get("task_id")
    secondary = raw.get("task_id") if has_id and has_task_id else primary
    if not isinstance(primary, str) or not primary.strip():
        findings.append(
            _finding(FindingCode.INVALID_TASK_ID, "native task id must be a non-empty string", field="id")
        )
        task_id = f"invalid-task-{index}"
    else:
        task_id = primary.strip()
    if has_id and has_task_id and primary != secondary:
        findings.append(
            _finding(FindingCode.INVALID_TASK_ID, "id and task_id disagree", field="id")
        )
    return task_id, findings


def _extract_enabled(raw: Mapping[str, Any]) -> tuple[bool, list[ContractFinding]]:
    findings: list[ContractFinding] = []
    has_is_enabled = "is_enabled" in raw
    has_enabled = "enabled" in raw
    if not has_is_enabled and not has_enabled:
        return False, [
            _finding(
                FindingCode.INVALID_ENABLED_FLAG,
                "task export must contain a JSON boolean is_enabled or enabled field",
                field="is_enabled",
            )
        ]
    primary = raw.get("is_enabled") if has_is_enabled else raw.get("enabled")
    secondary = raw.get("enabled") if has_is_enabled and has_enabled else primary
    if not isinstance(primary, bool):
        findings.append(
            _finding(
                FindingCode.INVALID_ENABLED_FLAG,
                "enabled state must be a JSON boolean, not a string or number",
                field="is_enabled",
            )
        )
        enabled = False
    else:
        enabled = primary
    if has_is_enabled and has_enabled and primary != secondary:
        findings.append(
            _finding(
                FindingCode.INVALID_ENABLED_FLAG,
                "is_enabled and enabled disagree",
                field="is_enabled",
            )
        )
    return enabled, findings


def audit_tasks(tasks: Iterable[Mapping[str, Any]]) -> AuditReport:
    """Audit an account-local task export without contacting or mutating a task store."""

    materialized = list(tasks)
    candidate_ids: list[str] = []
    for index, raw in enumerate(materialized):
        if not isinstance(raw, Mapping):
            continue
        task_id, id_findings = _extract_task_id(raw, index)
        if not id_findings:
            candidate_ids.append(task_id)
    duplicate_task_ids = tuple(
        sorted(task_id for task_id, count in Counter(candidate_ids).items() if count > 1)
    )
    duplicate_set = set(duplicate_task_ids)

    results: list[TaskAudit] = []
    for index, raw in enumerate(materialized):
        if not isinstance(raw, Mapping):
            audit = _audit_from_findings(
                [_finding(FindingCode.INVALID_TASK, "every task must be a JSON object", field="task")]
            )
            results.append(
                TaskAudit(
                    task_id=f"invalid-task-{index}",
                    title="",
                    enabled=False,
                    evaluated=True,
                    audit_kind="INVALID",
                    audit=audit,
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
                _finding(FindingCode.INVALID_TASK, "audit_kind must be a string", field="audit_kind")
            )
        else:
            audit_kind = raw_audit_kind.strip().upper()
        if audit_kind not in _AUDIT_KINDS:
            wrapper_findings.append(
                _finding(FindingCode.INVALID_TASK, f"unknown audit_kind {audit_kind!r}", field="audit_kind")
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

        audit = validate_watcher_prompt(raw.get("prompt", ""))
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
                finding.code is FindingCode.INVALID_TASK and finding.field == "audit_kind"
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
