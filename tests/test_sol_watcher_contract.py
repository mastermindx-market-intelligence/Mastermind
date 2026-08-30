from __future__ import annotations

import pytest

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


def _parent_prompt() -> str:
    return """MMX_SOL_WATCHER_V1
WATCHER_ROLE: PARENT_ORCHESTRATOR
OPERATION_KEY: eval-os-program-parent-20260830-sol-001
CARRIER: aggregate:eval-os-program
LATEST_HANDLED_EDGE: NONE
ACTION_REQUIRED_EVENTS: PARENT_TRANSITION
ACTION_REQUIRED_OUTCOME: PARENT_EDGE_ONLY_NO_CHILD_RACE
SISTER_SOL_POLICY: NEVER_ACT_ON_DEDICATED_CHILD_RETURN

On every run, re-pin the CURRENT protected Mastermind Skillpack.
Fresh-read every exact carrier needed to prove a parent transition before reporting.
Act only on parent state and never post a dedicated child semantic edge.
No blind retry or cross-carrier failover is permitted.
Never infer Executive Job/Attempt/Worker/Event lifecycle from Slack delivery.
Terminal STOP for a child remains owned by that child's exact action-authoritative Sol surface.
"""


def _triage_prompt() -> str:
    return """MMX_SOL_WATCHER_V1
WATCHER_ROLE: TRIAGE_ONLY
OPERATION_KEY: mastermind-session-triage-20260830-sol-001
CARRIER: aggregate:mastermind-session-triage
LATEST_HANDLED_EDGE: NONE
ACTION_REQUIRED_EVENTS: UNCONSUMED_RETURN
ACTION_REQUIRED_OUTCOME: RECONCILE_OR_REPORT_NO_DUPLICATE
SISTER_SOL_POLICY: NEVER_ELECT_BY_RECENCY

On every run, re-pin the CURRENT protected Mastermind Skillpack.
Fresh-read each exact carrier selected by the bounded triage delta before reporting.
Reconcile or report the unconsumed return without posting a child semantic edge or electing a Sol target.
No blind retry or cross-carrier failover is permitted.
Never infer Executive Job/Attempt/Worker/Event lifecycle from Slack delivery.
Terminal STOP remains owned by the exact child action-authoritative Sol surface.
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


def test_negated_self_deadlock_examples_are_allowed() -> None:
    prompt = _authoritative_prompt(
        body_suffix=(
            "Do not return 'Sol action required'. Never wait for Sol or stand by for Sol's ruling; "
            "this exact action-authoritative watcher is the Sol re-entry surface."
        )
    )
    assert FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK not in _codes(prompt)


def test_positive_wait_later_on_a_mixed_negation_line_is_rejected() -> None:
    prompt = _authoritative_prompt(
        body_suffix=(
            "Do not narrate routine progress; when RESULT arrives, wait for Sol and notify the Chairman."
        )
    )
    assert FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK in _codes(prompt)


@pytest.mark.parametrize(
    "instruction",
    (
        "When RESULT arrives, await Sol.",
        "When RESULT arrives, defer to Sol.",
        "When RESULT arrives, escalate to Sol.",
        "When RESULT arrives, pause for Sol.",
    ),
)
def test_action_authoritative_self_deferral_synonyms_are_rejected(instruction: str) -> None:
    assert FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK in _codes(
        _authoritative_prompt(body_suffix=instruction)
    )


def test_observer_cannot_claim_child_modification_authority() -> None:
    prompt = _observer_prompt().replace(
        "ACTION_REQUIRED_OUTCOME: OBSERVE_ONLY_NO_MODIFY",
        "ACTION_REQUIRED_OUTCOME: SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
    )
    assert FindingCode.ROLE_CONTRACT_MISMATCH in _codes(prompt)


def test_non_authoritative_positive_modification_instructions_are_rejected() -> None:
    cases = (
        _observer_prompt() + "\nWhen RESULT arrives, reply with CONTINUE and merge the pull request.\n",
        _parent_prompt() + "\nWhen a child returns, post SOL STOP and commission a successor.\n",
        _triage_prompt() + "\nWhen an unconsumed result appears, issue REQUEST_REPAIR and retry it.\n",
    )
    for prompt in cases:
        assert FindingCode.NON_AUTHORITATIVE_MODIFICATION_FORBIDDEN in _codes(prompt)


def test_non_authoritative_negated_modification_examples_are_allowed() -> None:
    prompt = _observer_prompt() + (
        "\nNever issue a Sol ruling, never send Sol CONTINUE, and do not merge the pull request.\n"
    )
    assert FindingCode.NON_AUTHORITATIVE_MODIFICATION_FORBIDDEN not in _codes(prompt)


def test_missing_required_header_field_fails_closed() -> None:
    prompt = _authoritative_prompt().replace("WATCHER_ROLE: ACTION_AUTHORITATIVE\n", "")
    assert FindingCode.MISSING_FIELD in _codes(prompt)


def test_malformed_slack_carrier_fails_closed() -> None:
    prompt = _authoritative_prompt().replace(
        "CARRIER: slack:C0BSBM78V1N/1788053475.603929",
        "CARRIER: newest-visible-chat",
    )
    assert FindingCode.INVALID_CARRIER in _codes(prompt)


def test_triage_may_use_closed_aggregate_scope() -> None:
    audit = validate_watcher_prompt(_triage_prompt())
    assert audit.valid is True
    assert audit.role is WatcherRole.TRIAGE_ONLY
    assert audit.carrier == "aggregate:mastermind-session-triage"


def test_action_authoritative_watcher_requires_exact_slack_carrier() -> None:
    prompt = _authoritative_prompt().replace(
        "CARRIER: slack:C0BSBM78V1N/1788053475.603929",
        "CARRIER: aggregate:ff-fif-program",
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


@pytest.mark.parametrize(
    ("original", "contradiction", "expected"),
    (
        (
            "On every run, re-pin the CURRENT protected Mastermind Skillpack before modifying action.",
            "On every run, do not re-pin the CURRENT protected Mastermind Skillpack before modifying action.",
            FindingCode.MISSING_CURRENT_REPIN,
        ),
        (
            "Fresh-read the exact carrier after the latest local evidence-producing action.",
            "Do not fresh-read the exact carrier after the latest local evidence-producing action.",
            FindingCode.MISSING_CARRIER_FRESHNESS,
        ),
        (
            "For BLOCKED, DECISION_REQUEST, or RESULT, post the actual same-carrier Sol edge before reporting.",
            "For BLOCKED, DECISION_REQUEST, or RESULT, do not post the actual same-carrier Sol edge before reporting.",
            FindingCode.MISSING_SAME_CARRIER_ACTION,
        ),
        (
            "If action cannot lawfully occur, return a typed blocker naming the real boundary.",
            "If action cannot lawfully occur, do not return a typed blocker naming the real boundary.",
            FindingCode.MISSING_TYPED_BLOCKER,
        ),
        (
            "Send terminal STOP before disarming the child watcher source.",
            "Do not send terminal STOP before disarming the child watcher source.",
            FindingCode.MISSING_TERMINAL_STOP_ORDER,
        ),
        (
            "Never infer Executive Job/Attempt/Worker/Event lifecycle from Slack delivery.",
            "Infer Executive Job/Attempt/Worker/Event lifecycle from Slack delivery.",
            FindingCode.MISSING_LIFECYCLE_BOUNDARY,
        ),
    ),
)
def test_negated_required_laws_do_not_satisfy_contract(
    original: str, contradiction: str, expected: FindingCode
) -> None:
    prompt = _authoritative_prompt().replace(original, contradiction)
    assert expected in _codes(prompt)


def test_audit_tasks_reports_invalid_enabled_and_ignores_disabled() -> None:
    tasks = [
        {"id": "good", "title": "Good action loop", "is_enabled": True, "prompt": _authoritative_prompt()},
        {"id": "bad", "title": "Notification only", "is_enabled": True, "prompt": _authoritative_prompt(body_suffix="Return Sol action required and wait for Sol.")},
        {"id": "disabled-old", "title": "Historical invalid watcher", "is_enabled": False, "prompt": "wait for Sol"},
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
    assert FindingCode.NOTIFICATION_ONLY_SELF_DEADLOCK in {finding.code for finding in by_id["bad"].audit.findings}


def test_audit_tasks_skips_declared_non_watcher_tasks() -> None:
    report = audit_tasks([
        {"id": "ordinary-reminder", "title": "Ordinary non-watcher automation", "is_enabled": True, "audit_kind": "NON_WATCHER", "prompt": "remind the Chairman about a meeting"},
        {"id": "watcher", "title": "Triage watcher", "is_enabled": True, "audit_kind": "SOL_WATCHER", "prompt": _triage_prompt()},
    ])
    assert report.total_tasks == 2
    assert report.enabled_tasks == 1
    assert report.valid_enabled_tasks == 1
    assert report.invalid_enabled_tasks == 0
    by_id = {task.task_id: task for task in report.tasks}
    assert by_id["ordinary-reminder"].evaluated is False
    assert by_id["ordinary-reminder"].audit_kind == "NON_WATCHER"


def test_unknown_audit_kind_fails_closed_even_when_task_is_disabled() -> None:
    report = audit_tasks([
        {"id": "ambiguous", "title": "Ambiguous wrapper", "is_enabled": False, "audit_kind": "MAYBE_WATCHER", "prompt": ""}
    ])
    assert report.valid is False
    assert report.invalid_classification_tasks == 1
    assert report.tasks[0].evaluated is True
    assert report.tasks[0].audit is not None
    assert FindingCode.INVALID_TASK in {finding.code for finding in report.tasks[0].audit.findings}


def test_enabled_flag_must_be_a_json_boolean() -> None:
    report = audit_tasks([
        {"id": "typed-wrong", "title": "Wrong enabled type", "is_enabled": "false", "prompt": _authoritative_prompt()}
    ])
    assert report.valid is False
    assert report.invalid_export_tasks == 1
    assert report.tasks[0].audit is not None
    assert FindingCode.INVALID_ENABLED_FLAG in {finding.code for finding in report.tasks[0].audit.findings}


def test_duplicate_native_task_ids_fail_closed_even_when_disabled() -> None:
    report = audit_tasks([
        {"id": "same-id", "title": "First", "is_enabled": False, "audit_kind": "NON_WATCHER", "prompt": ""},
        {"id": "same-id", "title": "Second", "is_enabled": False, "audit_kind": "NON_WATCHER", "prompt": ""},
    ])
    assert report.valid is False
    assert report.duplicate_task_ids == ("same-id",)
    for task in report.tasks:
        assert task.audit is not None
        assert FindingCode.DUPLICATE_TASK_ID in {finding.code for finding in task.audit.findings}


def test_missing_native_task_id_fails_closed() -> None:
    report = audit_tasks([
        {"title": "Missing id", "is_enabled": False, "audit_kind": "NON_WATCHER", "prompt": ""}
    ])
    assert report.valid is False
    assert report.invalid_export_tasks == 1
    assert report.tasks[0].audit is not None
    assert FindingCode.INVALID_TASK_ID in {finding.code for finding in report.tasks[0].audit.findings}


def test_cli_emits_valid_json_and_zero_for_clean_export(tmp_path, capsys) -> None:
    from scripts.audit_sol_watchers import main
    source = tmp_path / "tasks.json"
    source.write_text(__import__("json").dumps({"tasks": [{"id": "good", "title": "Good", "is_enabled": True, "prompt": _authoritative_prompt()}]}), encoding="utf-8")
    assert main([str(source)]) == 0
    output = __import__("json").loads(capsys.readouterr().out)
    assert output["schema"] == "mastermind.sol_watcher_audit.v1"
    assert output["valid"] is True
    assert output["summary"]["invalid_enabled_tasks"] == 0


def test_cli_returns_one_for_invalid_enabled_watcher(tmp_path, capsys) -> None:
    from scripts.audit_sol_watchers import main
    source = tmp_path / "tasks.json"
    source.write_text(__import__("json").dumps([{"id": "bad", "title": "Bad", "is_enabled": True, "prompt": "wait for Sol"}]), encoding="utf-8")
    assert main([str(source)]) == 1
    output = __import__("json").loads(capsys.readouterr().out)
    assert output["valid"] is False
    assert output["summary"]["invalid_enabled_tasks"] == 1


def test_cli_returns_two_for_malformed_input(tmp_path, capsys) -> None:
    from scripts.audit_sol_watchers import main
    source = tmp_path / "tasks.json"
    source.write_text("{not-json", encoding="utf-8")
    assert main([str(source)]) == 2
    error = __import__("json").loads(capsys.readouterr().err)
    assert error["schema"] == "mastermind.sol_watcher_audit_error.v1"
    assert error["error"] == "INVALID_INPUT"
