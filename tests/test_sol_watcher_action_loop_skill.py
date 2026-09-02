from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.sol_watcher_contract import (
    BODY_DISCRIMINATOR,
    FindingCode,
    WatcherRole,
    audit_tasks,
    canonical_account_export,
    render_watcher_body,
    render_watcher_prompt,
    validate_watcher_prompt,
)


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_watcher_action_loop_is_canonical_and_action_oriented() -> None:
    skill_path = ROOT / "docs/sol_skills/WATCHER_ACTION_LOOP.md"
    assert skill_path.exists(), "watcher action-loop law must be a canonical Sol skill"

    skill = skill_path.read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    index = _read("docs/sol_skills/INDEX.md")
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")

    assert "WATCHER_ACTION_LOOP.md" in index
    assert "WATCHER_ACTION_LOOP.md" in kernel

    required_skill_phrases = (
        "A Sol watcher is an action re-entry hook, not a notification service.",
        "DETECT -> RE-PIN -> ADJUDICATE -> ACT -> REPORT",
        "Do not stop at `Sol action required`",
        "post the actual Sol edge in the same lawful carrier",
        "Chairman-only boundary",
        "terminal return does not authorize a new independent wave",
        "never creates or mutates Executive Job/Attempt/Worker/Event state",
    )
    for phrase in required_skill_phrases:
        assert phrase in normalized_skill, f"missing watcher action-loop law: {phrase}"

    assert "notification-only watcher" in index
    assert "detect -> re-pin -> adjudicate -> act -> report" in kernel.lower()


def test_watcher_lifetime_survives_nonterminal_events_until_stop() -> None:
    skill = _read("docs/sol_skills/WATCHER_ACTION_LOOP.md")
    normalized = " ".join(skill.split())

    required_lifetime_phrases = (
        "ACK, WATCH_ARMED, START, and PROGRESS are nonterminal watcher events",
        "advance the consumed baseline and keep or re-arm the Sol watcher",
        "BLOCKED, DECISION_REQUEST, and RESULT are action-required watcher events",
        "Never disable Sol's continuation watcher before sending the worker's terminal STOP.",
        "ACK -> WATCH_ARMED -> START -> RESULT -> STOP",
        "Only after the terminal STOP edge is sent may Sol disarm its watcher for that child operation",
    )
    for phrase in required_lifetime_phrases:
        assert phrase in normalized, f"missing watcher lifetime invariant: {phrase}"


def test_temporary_sol_watchers_use_structured_role_contract() -> None:
    skill = _read("docs/sol_skills/WATCHER_ACTION_LOOP.md")
    normalized = " ".join(skill.split())

    required_contract_phrases = (
        "MMX_SOL_WATCHER_V1",
        "ACTION_AUTHORITATIVE",
        "OBSERVER_ONLY",
        "PARENT_ORCHESTRATOR",
        "TRIAGE_ONLY",
        "SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
        "NOTIFICATION_ONLY_SELF_DEADLOCK",
        "python3 scripts/audit_sol_watchers.py",
        "canonical action-target transfer",
        "never elect by recency",
        "aggregate:<stable-scope-id>",
        "ACTION_AUTHORITATIVE always requires an exact Slack carrier",
        "audit_kind: NON_WATCHER",
        "Every non-authoritative role",
        "retry, resubmit, requeue, fail over",
        "native task ID must be present and unique",
        "enabled state must be a JSON boolean",
        "Duplicate native task IDs",
        "invalid_export_tasks",
    )
    for phrase in required_contract_phrases:
        assert phrase in normalized, f"missing structured watcher contract law: {phrase}"


def _carrier_for(role: WatcherRole) -> str:
    if role is WatcherRole.ACTION_AUTHORITATIVE:
        return "slack:C0BSBM78V1N/1788308881.756489"
    return f"aggregate:test-{role.value.casefold().replace('_', '-')}"


@pytest.mark.parametrize("role", tuple(WatcherRole))
def test_managed_body_renderer_round_trips_canonically(role: WatcherRole) -> None:
    prompt = render_watcher_prompt(
        role=role,
        operation_key=f"watcher-closed-body-{role.value.casefold()}",
        carrier=_carrier_for(role),
        latest_handled_edge="NONE",
    )

    audit = validate_watcher_prompt(prompt)
    assert audit.valid is True
    assert audit.role is role
    assert audit.findings == ()
    assert prompt.count(BODY_DISCRIMINATOR) == 1
    body = prompt.split("\n\n", 1)[1]
    assert body == render_watcher_body(role)
    assert body.count("[ROLE]") == 1
    assert body.count("[SOURCE_LAW]") == 1
    assert body.count("[AUTHORITY]") == 1


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        (
            lambda body: body + "\n[EXTRA]\nVALUE: forbidden\n[/EXTRA]",
            FindingCode.UNKNOWN_BODY_SECTION,
        ),
        (
            lambda body: body + "\n[ROLE]\nROLE: OBSERVER_ONLY\n[/ROLE]",
            FindingCode.DUPLICATE_BODY_SECTION,
        ),
        (
            lambda body: body.replace(
                "ROLE: ACTION_AUTHORITATIVE",
                "ROLE: ACTION_AUTHORITATIVE\nUNREVIEWED_KEY: true",
            ),
            FindingCode.UNKNOWN_BODY_KEY,
        ),
        (
            lambda body: body.replace(
                "[SOURCE_LAW]",
                "[SOURCE_LAW_REMOVED]",
            ),
            FindingCode.MISSING_BODY_SECTION,
        ),
    ),
)
def test_managed_body_is_closed_world(
    mutation: object,
    expected: FindingCode,
) -> None:
    prompt = render_watcher_prompt(
        role=WatcherRole.ACTION_AUTHORITATIVE,
        operation_key="watcher-closed-body-negative",
        carrier="slack:C0BSBM78V1N/1788308881.756489",
        latest_handled_edge="NONE",
    )
    header, body = prompt.split("\n\n", 1)
    mutated = f"{header}\n\n{mutation(body)}"
    codes = {finding.code for finding in validate_watcher_prompt(mutated).findings}
    assert expected in codes


def test_managed_body_rejects_free_prose_even_when_it_looks_safe() -> None:
    prompt = render_watcher_prompt(
        role=WatcherRole.OBSERVER_ONLY,
        operation_key="watcher-closed-body-no-prose",
        carrier="aggregate:watcher-closed-body-no-prose",
        latest_handled_edge="NONE",
    )
    mutated = prompt + "\nNever issue a Sol ruling or merge the pull request."
    codes = {finding.code for finding in validate_watcher_prompt(mutated).findings}
    assert FindingCode.NONCANONICAL_MANAGED_BODY in codes


def test_managed_observer_cannot_gain_child_authority_by_editing_words() -> None:
    prompt = render_watcher_prompt(
        role=WatcherRole.OBSERVER_ONLY,
        operation_key="watcher-observer-authority-fence",
        carrier="aggregate:watcher-observer-authority-fence",
        latest_handled_edge="NONE",
    )
    mutated = prompt.replace(
        "ALLOWED: OBSERVE,REPORT_DELTA",
        "ALLOWED: OBSERVE,REPORT_DELTA,CHILD_CONTINUE",
    )
    codes = {finding.code for finding in validate_watcher_prompt(mutated).findings}
    assert FindingCode.BODY_CONTRACT_MISMATCH in codes


def test_canonical_account_export_is_byte_stable_and_managed() -> None:
    prompt = render_watcher_prompt(
        role=WatcherRole.ACTION_AUTHORITATIVE,
        operation_key="watcher-account-export-stable",
        carrier="slack:C0BSBM78V1N/1788308881.756489",
        latest_handled_edge="NONE",
    )
    tasks = [
        {
            "id": " watcher-1 ",
            "task_id": "watcher-1",
            "title": "Managed watcher",
            "is_enabled": True,
            "audit_kind": "SOL_WATCHER",
            "prompt": prompt,
        },
        {
            "id": "ordinary-1",
            "title": "Ordinary task",
            "is_enabled": False,
            "audit_kind": "NON_WATCHER",
            "prompt": "",
        },
    ]

    first = canonical_account_export(tasks)
    second = canonical_account_export(first["tasks"])
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert first["payload_kind"] == "ACCOUNT_EXPORT"
    assert first["schema"] == "mastermind.sol_watcher_account_export.v1"
    report = audit_tasks(first["tasks"], require_managed_body=True)
    assert report.valid is True


def test_managed_account_audit_rejects_legacy_free_prose_prompt() -> None:
    legacy_prompt = """MMX_SOL_WATCHER_V1
WATCHER_ROLE: TRIAGE_ONLY
OPERATION_KEY: legacy-triage
CARRIER: aggregate:legacy-triage
LATEST_HANDLED_EDGE: NONE
ACTION_REQUIRED_EVENTS: UNCONSUMED_RETURN
ACTION_REQUIRED_OUTCOME: RECONCILE_OR_REPORT_NO_DUPLICATE
SISTER_SOL_POLICY: NEVER_ELECT_BY_RECENCY

On every run, re-pin the CURRENT protected Mastermind Skillpack.
Fresh-read the exact carrier before reporting.
No blind retry is permitted.
Never infer Executive lifecycle from Slack delivery.
"""
    report = audit_tasks(
        [
            {
                "id": "legacy",
                "title": "Legacy prose watcher",
                "is_enabled": True,
                "audit_kind": "SOL_WATCHER",
                "prompt": legacy_prompt,
            }
        ],
        require_managed_body=True,
    )
    assert report.valid is False
    assert report.tasks[0].audit is not None
    assert FindingCode.NONCANONICAL_MANAGED_BODY in {
        finding.code for finding in report.tasks[0].audit.findings
    }
