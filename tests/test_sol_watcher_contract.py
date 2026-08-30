from __future__ import annotations

from control_plane.sol_watcher_contract import (
    FindingCode,
    WatcherRole,
    audit_tasks,
    validate_watcher_prompt,
)


def _authoritative_prompt(*, body_suffix: str = "", sister_policy: str | None = None) -> str:
    policy = sister_policy or "OBSERVE_ONLY_UNLESS_EXACT_ACTION_TARGET"
    return f"""MMX_SOL_WATCHER_V1
WATCHER_ROLE: ACTION_AUTHORITATIVE
OPERATION_KEY: ff-fif-fable-principal-restart-20260829-sol-001
CARRIER: slack:C0BSBM78V1N/1788053475.603929
LATEST_HANDLED_EDGE: 1788070813.223189
ACTION_REQUIRED_EVENTS: BLOCKED,DECISION_REQUEST,RESULT
ACTION_REQUIRED_OUTCOME: SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER
SISTER_SOL_POLICY: {policy}

On every run, re-pin the CURRENT protected Mastermind Skillpack before modifying action.
Fresh-read the exact carrier after the latest local evidence-producing action.
For BLOCKED, DECISION_REQUEST, or RESULT, post the actual same-carrier Sol edge before reporting.
If action cannot lawfully occur, return a typed blocker naming the real boundary.
No blind retry or cross-carrier failover is permitted.
Never infer Executive Job/Attempt/Worker/Event lifecycle from Slack delivery.
Send terminal STOP before disarming the child watcher source.
{body_suffix}
"""


def _observer_prompt() -> str:
    return """MMX_SOL_WATCHER_V1
WATCHER_ROLE: OBSERVER_ONLY
OPERATION_KEY: ff-fif-fable-principal-restart-20260829-sol-001
CARRIER: slack:C0BSBM78V1N/1788053475.603929
LATEST_HANDLED_EDGE: 1788070813.223189
ACTION_REQUIRED_EVENTS: NONE
ACTION_REQUIRED_OUTCOME: OBSERVE_ONLY_NO_MODIFY
SISTER_SOL_POLICY: NEVER_ACT_WITHOUT_CANONICAL_TRANSFER

On every run, re-pin the CURRENT protected Mastermind Skillpack.
Fresh-read the exact carrier before reporting any material delta.
Observe only; do not post a child CONTINUE, RULING, REQUEST_REPAIR, STOP, merge, retry, or successor commission.
No blind retry or cross-carrier failover is permitted.
Never infer Executive Job/Attempt/Worker/Event lifecycle from Slack delivery.
A terminal STOP is consumed as transport evidence only; this observer never disarms another account's watcher.
"""


def _codes(prompt: str) -> set[FindingCode]:
    return {finding.code for finding in validate_watcher_prompt(prompt).findings}


def test_valid_action_authoritative_prompt_passes() -> None:
    audit = validate_watcher_prompt(_authoritative_prompt())

    assert audit.valid is True
    assert audit.role is WatcherRole.ACTION_AUTHORITATIVE
    assert audit.operation_key == "ff-fif-fable-principal-restart-20260829-sol-001"
    assert audit.carrier == "slack:C0BSBM78V1N/1788053475.603929"
    assert audit.findings == ()


def test_ff_fif_notification_only_self_deadlock_is_rejected() -> None:
    prompt = _authoritative_prompt(
        body_suffix=(
            'When Fable returns RESULT, notify the Chairman that "Sol action required", '
            "stand by for Sol's ruling, and wait for Sol."
        )
    )

    assert FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK in _codes(prompt)


def test_observer_cannot_claim_child_modification_authority() -> None:
    prompt = _observer_prompt().replace(
        "ACTION_REQUIRED_OUTCOME: OBSERVE_ONLY_NO_MODIFY",
        "ACTION_REQUIRED_OUTCOME: SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
    )

    assert FindingCode.ROLE_CONTRACT_MISMATCH in _codes(prompt)


def test_missing_required_header_field_fails_closed() -> None:
    prompt = _authoritative_prompt().replace("WATCHER_ROLE: ACTION_AUTHORITATIVE\n", "")

    assert FindingCode.MISSING_FIELD in _codes(prompt)


def test_malformed_slack_carrier_fails_closed() -> None:
    prompt = _authoritative_prompt().replace(
        "CARRIER: slack:C0BSBM78V1N/1788053475.603929",
        "CARRIER: newest-visible-chat",
    )

    assert FindingCode.INVALID_CARRIER in _codes(prompt)


def test_action_authoritative_sister_sol_policy_is_closed() -> None:
    prompt = _authoritative_prompt(sister_policy="ANY_SOL_MAY_ACT")

    assert FindingCode.ROLE_CONTRACT_MISMATCH in _codes(prompt)


def test_missing_freshness_or_repin_law_is_rejected() -> None:
    prompt = _authoritative_prompt().replace("Fresh-read the exact carrier", "Read the carrier")
    prompt = prompt.replace("CURRENT protected", "protected")

    codes = _codes(prompt)
    assert FindingCode.MISSING_CURRENT_REPIN in codes
    assert FindingCode.MISSING_CARRIER_FRESHNESS in codes


def test_audit_tasks_reports_invalid_enabled_and_ignores_disabled() -> None:
    tasks = [
        {
            "id": "good",
            "title": "Good action loop",
            "is_enabled": True,
            "prompt": _authoritative_prompt(),
        },
        {
            "id": "bad",
            "title": "Notification only",
            "is_enabled": True,
            "prompt": _authoritative_prompt(body_suffix="Return Sol action required and wait for Sol."),
        },
        {
            "id": "disabled-old",
            "title": "Historical invalid watcher",
            "is_enabled": False,
            "prompt": "wait for Sol",
        },
    ]

    report = audit_tasks(tasks)

    assert report.total_tasks == 3
    assert report.enabled_tasks == 2
    assert report.valid_enabled_tasks == 1
    assert report.invalid_enabled_tasks == 1
    assert report.valid is False
    by_id = {task.task_id: task for task in report.tasks}
    assert by_id["disabled-old"].evaluated is False
    assert by_id["bad"].audit is not None
    assert FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK in {
        finding.code for finding in by_id["bad"].audit.findings
    }
