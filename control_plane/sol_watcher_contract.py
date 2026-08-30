"""Deterministic contract checks for temporary Sol watcher prompts.

This module is validation-only. It owns no watcher, task store, lifecycle,
action target, transport, retry, cursor, provider session, or persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable, Mapping


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
_CARRIER_RE = re.compile(r"^slack:[CGD][A-Z0-9]+/\d{10}\.\d{6}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_EDGE_RE = re.compile(r"^(?:NONE|\d{10}\.\d{6}|[A-Za-z0-9][A-Za-z0-9._:/-]{1,255})$")


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
    OBSERVER_MODIFICATION_FORBIDDEN = "OBSERVER_MODIFICATION_FORBIDDEN"
    INVALID_TASK = "INVALID_TASK"


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
    audit: PromptAudit | None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "enabled": self.enabled,
            "evaluated": self.evaluated,
            "audit": self.audit.to_dict() if self.audit else None,
        }


@dataclass(frozen=True)
class AuditReport:
    valid: bool
    total_tasks: int
    enabled_tasks: int
    valid_enabled_tasks: int
    invalid_enabled_tasks: int
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

_NOTIFICATION_ONLY_PATTERNS = (
    re.compile(r"\bsol action required\b", re.IGNORECASE),
    re.compile(r"\bwait(?:ing)? for sol\b", re.IGNORECASE),
    re.compile(r"\bstand by for sol(?:'s)? ruling\b", re.IGNORECASE),
)


def _finding(
    code: FindingCode,
    message: str,
    *,
    field: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ContractFinding:
    return ContractFinding(code=code, message=message, field=field, severity=severity)


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
    if carrier and not _CARRIER_RE.fullmatch(carrier):
        findings.append(
            _finding(
                FindingCode.INVALID_CARRIER,
                "carrier must be slack:<channel-id>/<10-digit-ts.6-digit-fraction>",
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
        if any(pattern.search(body) for pattern in _NOTIFICATION_ONLY_PATTERNS):
            findings.append(
                _finding(
                    FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK,
                    "action-authoritative watcher cannot terminate by waiting for the Sol role it already represents",
                )
            )

    if role is WatcherRole.OBSERVER_ONLY:
        positive_phrases = (
            "post the actual same-carrier sol edge",
            "issue a sol ruling",
            "send sol continue",
            "merge the pull request",
        )
        for phrase in positive_phrases:
            if phrase in folded and f"do not {phrase}" not in folded:
                findings.append(
                    _finding(
                        FindingCode.OBSERVER_MODIFICATION_FORBIDDEN,
                        "observer-only watcher cannot claim child modification authority",
                    )
                )
                break

    findings_tuple = tuple(findings)
    return PromptAudit(
        valid=not any(finding.severity is Severity.ERROR for finding in findings_tuple),
        role=role,
        operation_key=operation_key,
        carrier=carrier,
        latest_handled_edge=latest_handled_edge,
        findings=findings_tuple,
    )


def audit_tasks(tasks: Iterable[Mapping[str, Any]]) -> AuditReport:
    """Audit an account-local task export without contacting or mutating a task store."""

    results: list[TaskAudit] = []
    for index, raw in enumerate(tasks):
        task_id = str(raw.get("id") or raw.get("task_id") or f"task-{index}")
        title = str(raw.get("title") or "")
        enabled = bool(raw.get("is_enabled", raw.get("enabled", False)))
        if not enabled:
            results.append(
                TaskAudit(
                    task_id=task_id,
                    title=title,
                    enabled=False,
                    evaluated=False,
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
                audit=audit,
            )
        )

    enabled_results = [result for result in results if result.enabled]
    valid_count = sum(bool(result.audit and result.audit.valid) for result in enabled_results)
    invalid_count = len(enabled_results) - valid_count
    return AuditReport(
        valid=invalid_count == 0,
        total_tasks=len(results),
        enabled_tasks=len(enabled_results),
        valid_enabled_tasks=valid_count,
        invalid_enabled_tasks=invalid_count,
        tasks=tuple(results),
    )
