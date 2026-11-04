"""Tests for ``control_plane.executive_cross_plane_view``.

These tests build **real** Session Truth receipts through the existing producer
(``session_truth.build_receipt``) and consume them through the new cockpit
consumer.  Nothing here hand-writes a finding: every typed finding and every
repair owner asserted below was computed by ``session_truth_rules`` from the
normalized observations, which is exactly the property this delivery has to
prove — the cockpit reads the rules engine, it does not re-run or re-word it.

Key sets and forbidden key names are written out **literally** in this file
rather than imported from the module under test: an assertion that reads its
expected value from the code it is checking cannot fail.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from control_plane import executive_cross_plane_view as view
from control_plane.session_truth import build_receipt
from control_plane.session_truth_contract import (
    SessionTruthContractError,
    canonical_json,
    semantic_hash,
)

MASTER = "mastermindx-market-intelligence/Mastermind"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
NOW = "2026-08-27T08:00:00Z"
LATER = "2026-08-27T09:00:00Z"
SKILLPACK_SHA = "0ffe0b01f4fa8be64350f5764b80711b2066f990"
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64

# --- literal shapes, deliberately not read from the module under test ---
LITERAL_CARD_KEYS = {
    "workstream", "identities", "github", "linear", "findings", "finding_counts",
}
LITERAL_IDENTITIES_KEYS = {
    "linear_issue_ids", "repositories", "pull_requests", "operation_keys",
}
LITERAL_PR_CARD_KEYS = {
    "repository", "number", "delivery", "pickup_head_sha", "proof",
    "linked_linear_issue_id", "operation_key", "wave", "portfolio_mode", "authority",
}
LITERAL_ISSUE_CARD_KEYS = {
    "issue_id", "status", "workstream", "parent_id", "projection_revision",
    "declared_completion", "completion_proven", "updated_at", "github_relations",
    "execution",
} - {"completion_proven"}
LITERAL_GITHUB_BLOCK_KEYS = {
    "available", "observed_at", "freshness", "reason", "pull_requests",
}
LITERAL_LINEAR_BLOCK_KEYS = {
    "available", "observed_at", "freshness", "reason", "issues",
}
LITERAL_CAPABILITY_KEYS = {"read_only", "effect"}

#: No key anywhere in the document may assert execution liveness.  Linear status
#: and Slack delivery are a projection and a transport, never a running Job.
FORBIDDEN_EXECUTION_KEYS = {
    "running", "in_progress", "executing", "active", "alive", "working",
    "job_is_active", "lifecycle", "job_state", "execution_state", "liveness",
}


def _all_keys(node) -> set[str]:
    """Every mapping key anywhere in a nested structure."""

    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _all_keys(item)
    return keys


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def _pr(
    number: int = 170,
    *,
    state: str = "open",
    ci: str = "success",
    workstream: str | None = "WS:TARGET",
    linear: str | None = "MAS-6",
    completion: str | None = "merge-is-done",
    proof_state: str | None = "open",
    operation_key: str | None = "op-cockpit-001",
    wave: str | None = "R1",
    draft: bool = True,
    merge_sha: str | None = None,
    pickup_head_sha: str | None = SHA_B,
) -> dict:
    """A closed-shape GitHub PR record (session_truth_snapshots grammar)."""

    return {
        "repository": MASTER,
        "number": number,
        "state": state,
        "draft": draft,
        "head_sha": SHA_B,
        "base_sha": SHA_A,
        "merge_sha": merge_sha,
        "ci": ci,
        "workstream": workstream,
        "linear": linear,
        "portfolio_mode": "implementation",
        "wave": wave,
        "authority": "implementation",
        "completion": completion,
        "proof_state": proof_state,
        "operation_key": operation_key,
        "pickup_head_sha": pickup_head_sha,
    }


def _issue(
    issue_id: str = "MAS-6",
    *,
    status: str = "In Progress",
    workstream: str | None = "WS:TARGET",
    parent_id: str | None = None,
    projection_revision: int | None = 7,
    relation: str = "program_gate",
    number: int = 170,
    completion: str | None = "implementation",
) -> dict:
    """A closed-shape Linear issue record."""

    return {
        "id": issue_id,
        "status": status,
        "parent_id": parent_id,
        "workstream": workstream,
        "completion": completion,
        "projection_revision": projection_revision,
        "github_relations": [
            {"repository": MASTER, "number": number, "relation": relation}
        ],
        "updated_at": "2026-08-27T07:30:00Z",
    }


def _agentos(*, projection_revision: int = 7, pr_state: str = "open") -> dict:
    return {
        "available": True,
        "source_sha": SHA_A,
        "state": {
            "schema": "mastermind.agent_os_state.v1",
            "source_records_digest": DIGEST_A,
            "workstreams": [
                {
                    "key": "TARGET",
                    "updated": "2026-08-27",
                    # session_truth_rules reads the direct revision from the
                    # workstream row, not from the state envelope.
                    "projection_revision": projection_revision,
                    "prs": [{"number": 170, "state": pr_state}],
                }
            ],
        },
        "contexts": [
            {
                "schema": "mastermind.agent_os_context.v1",
                "target": {"workstream": "WS:TARGET"},
                "sections": [],
                "source_records_digest": DIGEST_B,
            }
        ],
    }


def _slack(*, operation_key: str = "op-slack-001", acked: bool = False) -> dict:
    return {
        "available": True,
        "observed_at": NOW,
        "channels": [{"channel_id": "C1", "member_ids": ["U1"]}],
        "messages": [
            {
                "channel_id": "C1",
                "ts": "100.1",
                "thread_ts": None,
                "sender_id": "U1",
                "operation_key": operation_key,
                "payload_hash": "sha256:" + "3" * 64,
                "transport": "DELIVERY_ONLY",
                "message_class": "READ_ONLY_COMMISSION",
                "target_principal_id": "U1",
                "delivered": True,
                "acked": acked,
                "receiver_eligible": True,
                "ack_required": True,
                "created_at": NOW,
                "source_law_sha": SHA_C,
                "freeze_at": None,
            }
        ],
    }


def _inputs(
    *,
    scope: dict | None = None,
    github: dict | None = None,
    linear: dict | None = None,
    agentos: dict | None = None,
    slack: dict | None = None,
    executive: dict | None = None,
    identities: dict | None = None,
) -> dict:
    """One complete Session Truth input envelope for the MAS-6 first vertical."""

    return {
        "schema": "mastermind.session_truth_inputs.v1",
        "scope": scope
        or {
            "workstreams": ["WS:TARGET"],
            "linear": ["MAS-6"],
            "repositories": [MASTER],
            "operation_key": None,
            "requires_executive": False,
        },
        "skillpack": {
            "available": True,
            "sha": SKILLPACK_SHA,
            "repository": MASTER,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.1",
            "minimum_bootstrap_major": 1,
        },
        "agentos": agentos if agentos is not None else _agentos(),
        "github": github
        if github is not None
        else {"available": True, "observed_at": NOW, "pull_requests": [_pr()]},
        "linear": linear
        if linear is not None
        else {"available": True, "observed_at": NOW, "issues": [_issue()]},
        # Readable, empty, and therefore silent: an unreadable optional plane
        # would alone force GROUNDING_PARTIAL and mask the scenario under test.
        "slack": slack
        if slack is not None
        else {"available": True, "observed_at": NOW, "channels": [], "messages": []},
        "executive": executive
        if executive is not None
        else {
            "available": True,
            "observed_at": NOW,
            "fresh": True,
            "grounding_sha": SKILLPACK_SHA,
            "operations": [],
        },
        "identities": identities
        if identities is not None
        else {"available": True, "observed_at": NOW, "bindings": []},
    }


def _receipt(inputs: dict | None = None) -> dict:
    return build_receipt(
        inputs if inputs is not None else _inputs(),
        observed_started_at=NOW,
        observed_ended_at=LATER,
    )


def _receipt_with_findings() -> dict:
    """A receipt whose rules engine actually emitted findings, for tamper tests."""

    return _receipt(
        _inputs(
            agentos=_agentos(projection_revision=9),
            linear={"available": True, "observed_at": NOW, "issues": [_issue()]},
        )
    )


def _card(document: dict, workstream: str = "WS:TARGET") -> dict:
    matches = [row for row in document["cards"] if row["workstream"] == workstream]
    assert len(matches) == 1, f"expected exactly one {workstream} card, got {len(matches)}"
    return matches[0]


def _codes(card: dict) -> set[str]:
    return {finding["code"] for finding in card["findings"]}


def _unattributed_codes(document: dict) -> set[str]:
    return {finding["code"] for finding in document["unattributed_findings"]}


def _finding(receipt: dict, code: str) -> dict:
    matches = [row for row in receipt["findings"] if row["code"] == code]
    assert matches, f"{code} was not produced by the rules engine"
    return matches[0]


# ---------------------------------------------------------------------------
# first vertical: healthy relation on MAS-6 exact identity
# ---------------------------------------------------------------------------

def test_healthy_relation_renders_exact_mas6_identity():
    receipt = _receipt()
    document = view.build_cross_plane_view(receipt)

    assert document["schema"] == view.SCHEMA
    assert document["state"] == "CONSUMED"
    assert receipt["admission"]["mode"] == "GROUNDING_COMPLETE"
    assert receipt["findings"] == []
    assert document["digest_check"]["state"] == "VERIFIED"

    card = _card(document)
    assert set(card) == LITERAL_CARD_KEYS
    assert set(card["identities"]) == LITERAL_IDENTITIES_KEYS
    assert card["workstream"] == "WS:TARGET"
    assert card["identities"]["linear_issue_ids"] == ["MAS-6"]
    assert card["identities"]["repositories"] == [MASTER]
    assert card["identities"]["pull_requests"] == [{"repository": MASTER, "number": 170}]
    assert card["identities"]["operation_keys"] == ["op-cockpit-001"]

    issue = card["linear"]["issues"][0]
    assert issue["issue_id"] == "MAS-6"
    assert issue["status"] == "In Progress"
    assert issue["github_relations"] == [
        {"repository": MASTER, "number": 170, "relation": "program_gate"}
    ]


def test_view_is_traceable_to_the_exact_receipt():
    receipt = _receipt()
    document = view.build_cross_plane_view(receipt)

    assert document["source_receipt"]["schema"] == receipt["schema"]
    assert document["source_receipt"]["semantic_hash"] == receipt["semantic_hash"]
    assert document["source_receipt"]["observation"] == {
        "started_at": NOW,
        "ended_at": LATER,
    }
    assert document["admission"] == receipt["admission"]


# ---------------------------------------------------------------------------
# false green: merged + green CI is NOT proof
# ---------------------------------------------------------------------------

def test_false_green_keeps_delivery_and_proof_separate():
    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [
                    _pr(state="merged", ci="success", completion="acceptance-required",
                        proof_state="open", draft=False, merge_sha=SHA_C)
                ],
            },
            agentos=_agentos(pr_state="merged"),
        )
    )
    # The blocking verdict comes from the existing rules engine, not from here.
    rule_finding = _finding(receipt, "GITHUB_MERGE_WITH_PROOF_OPEN")
    assert rule_finding["severity"] == "BLOCKING"

    card = _card(view.build_cross_plane_view(receipt))
    pull_request = card["github"]["pull_requests"][0]

    # Delivery and proof are separate blocks: the card can be read as merged and
    # green while still visibly not proven.
    assert pull_request["delivery"]["state"] == "merged"
    assert pull_request["delivery"]["ci"] == "success"
    assert pull_request["proof"]["declared_completion"] == "acceptance-required"
    assert pull_request["proof"]["proof_state"] == "open"

    finding = next(
        row for row in card["findings"] if row["code"] == "GITHUB_MERGE_WITH_PROOF_OPEN"
    )
    assert finding["severity"] == "BLOCKING"
    assert finding["canonical_owner"] == "declared_completion_owner"
    assert finding["repair_owner"] == "linear"
    assert finding["subject"] == f"{MASTER}#170"


def test_card_never_asserts_a_completion_verdict_of_its_own():
    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [
                    _pr(state="merged", ci="success", completion="merge-is-done",
                        proof_state="complete", draft=False, merge_sha=SHA_C)
                ],
            },
            agentos=_agentos(pr_state="merged"),
        )
    )
    document = view.build_cross_plane_view(receipt)
    card = _card(document)
    pull_request = card["github"]["pull_requests"][0]

    # Expected key sets are literal (above), so a new key fails this assertion
    # even when the module also declares it in its own constant.
    assert set(card) == LITERAL_CARD_KEYS
    assert set(card["identities"]) == LITERAL_IDENTITIES_KEYS
    assert set(card["github"]) == LITERAL_GITHUB_BLOCK_KEYS
    assert set(card["linear"]) == LITERAL_LINEAR_BLOCK_KEYS
    assert set(pull_request) == LITERAL_PR_CARD_KEYS
    assert set(pull_request["delivery"]) == {
        "state", "ci", "draft", "base_sha", "head_sha", "merge_sha"
    }
    assert set(pull_request["proof"]) == {"declared_completion", "proof_state"}

    # And no key anywhere in the document may name a completion verdict.
    assert not (_all_keys(document) & {
        "done", "complete", "completed", "green", "healthy", "verdict",
        "proof_verdict", "is_done", "finished",
    })


def test_no_health_verdict_is_invented_next_to_a_refused_receipt():
    """A refusal must never sit beside a self-issued all-clear."""

    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                # Two open carriers in one wave: MULTIPLE_ACTIVE_CARRIERS is FATAL.
                "pull_requests": [_pr(170), _pr(171)],
            },
            linear={"available": True, "observed_at": NOW, "issues": [_issue()]},
        )
    )
    assert receipt["admission"]["mode"] == "MODIFICATION_REFUSED"
    assert any(row["code"] == "MULTIPLE_ACTIVE_CARRIERS" for row in receipt["findings"])

    document = view.build_cross_plane_view(receipt)

    # The refusal is passed through intact, and this module adds no verdict of
    # its own: capability says what it can attest (read-only, no effect) and
    # nothing more.
    assert document["admission"]["mode"] == "MODIFICATION_REFUSED"
    assert document["admission"]["modification_safe"] is False
    assert set(document["capability"]) == LITERAL_CAPABILITY_KEYS
    assert document["capability"] == {"read_only": True, "effect": "NONE"}


# ---------------------------------------------------------------------------
# missing link
# ---------------------------------------------------------------------------

def test_missing_linear_link_is_typed_and_never_silently_dropped():
    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                # The carrier declares no Linear binding at all.
                "pull_requests": [_pr(linear=None)],
            },
            linear={
                "available": True,
                "observed_at": NOW,
                # Linear was genuinely read, and MAS-6 is genuinely absent.
                "issues": [_issue("MAS-99", relation="program_gate")],
            },
        )
    )
    assert "MISSING_LINEAR_PROJECTION" in {row["code"] for row in receipt["findings"]}

    document = view.build_cross_plane_view(receipt)
    # MAS-6 was read as absent, so no card may claim to carry it...
    card = _card(document)
    assert "MAS-6" not in card["identities"]["linear_issue_ids"]
    # ...and the finding is still surfaced, in the unattributed bucket.
    assert "MISSING_LINEAR_PROJECTION" in _unattributed_codes(document)
    assert any(
        fact["target_field"] == "cards.findings" for fact in document["unknowns"]
    )


def test_pr_bound_to_an_unreadable_linear_is_not_called_a_binding_conflict():
    receipt = _receipt(
        _inputs(linear={"available": False, "reason": "LINEAR_READ_PATH_UNAVAILABLE"})
    )
    codes = {finding["code"] for finding in receipt["findings"]}
    # An unreadable Linear cannot testify that the bound issue is absent.
    assert "PR_BINDING_CONFLICT" not in codes
    assert "MISSING_LINEAR_PROJECTION" not in codes

    card = _card(view.build_cross_plane_view(receipt))
    # The carrier is still rendered, with the link visible as declared-but-unverified.
    assert card["identities"]["pull_requests"] == [{"repository": MASTER, "number": 170}]
    assert card["github"]["pull_requests"][0]["linked_linear_issue_id"] == "MAS-6"


# ---------------------------------------------------------------------------
# stale owner
# ---------------------------------------------------------------------------

def test_stale_linear_projection_names_the_repair_owner_and_keeps_evidence():
    receipt = _receipt(
        _inputs(
            agentos=_agentos(projection_revision=9),
            linear={"available": True, "observed_at": NOW, "issues": [_issue()]},
        )
    )
    rule_finding = _finding(receipt, "STALE_LINEAR_PROJECTION")

    card = _card(view.build_cross_plane_view(receipt))
    finding = next(
        row for row in card["findings"] if row["code"] == "STALE_LINEAR_PROJECTION"
    )
    assert finding["severity"] == "WARNING"
    assert finding["canonical_owner"] == "agentos"
    assert finding["repair_owner"] == "linear"
    assert finding["subject"] == "MAS-6"
    # The rules engine's own evidence rides along verbatim: both divergent
    # revisions stay readable instead of being reduced to the status word.
    assert finding["source_a"] == rule_finding["source_a"]
    assert finding["source_b"] == rule_finding["source_b"]
    assert finding["source_a"]["agentos_projection_revision"] == 9
    assert finding["source_b"]["linear_projection_revision"] == 7


def test_completion_owner_evidence_unknown_keeps_its_distinguishing_detail():
    receipt = _receipt(
        _inputs(
            linear={
                "available": True,
                "observed_at": NOW,
                # Done, with an exact reciprocal completion owner whose proof
                # state is unclassified.
                "issues": [_issue("MAS-6", status="Done")],
            },
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [_pr(linear="MAS-6", proof_state=None)],
            },
        )
    )
    rule_finding = next(
        row
        for row in receipt["findings"]
        if row["code"] == "COMPLETION_OWNER_EVIDENCE_UNKNOWN"
    )
    card = _card(view.build_cross_plane_view(receipt))
    finding = next(
        row for row in card["findings"]
        if row["code"] == "COMPLETION_OWNER_EVIDENCE_UNKNOWN"
    )
    # details.reason separates two failure modes; dropping it would collapse them.
    assert finding["details"]["reason"] == rule_finding["details"]["reason"]
    assert finding["source_a"] == rule_finding["source_a"]
    assert finding["source_b"] == rule_finding["source_b"]


def test_freshness_is_relative_to_caller_evidence_never_assumed():
    receipt = _receipt()

    # No evaluation window supplied: freshness is undetermined, never "fresh".
    document = view.build_cross_plane_view(receipt)
    card = _card(document)
    assert card["github"]["freshness"] == "UNKNOWN"
    assert card["linear"]["freshness"] == "UNKNOWN"

    fresh = view.build_cross_plane_view(
        receipt, evaluated_at=LATER, stale_after_seconds=3600
    )
    assert _card(fresh)["github"]["freshness"] == "CURRENT"
    assert _card(fresh)["linear"]["freshness"] == "CURRENT"

    stale = view.build_cross_plane_view(
        receipt, evaluated_at="2026-08-29T08:00:00Z", stale_after_seconds=3600
    )
    assert _card(stale)["github"]["freshness"] == "STALE"
    assert _card(stale)["linear"]["freshness"] == "STALE"
    assert stale["state"] == "DEGRADED"
    assert any(fact["missingness_class"] == "DEGRADED" for fact in stale["unknowns"])


@pytest.mark.parametrize("bad", ["soon", -1, True, [3600]])
def test_stale_after_seconds_must_be_a_non_negative_number(bad):
    with pytest.raises(SessionTruthContractError):
        view.build_cross_plane_view(_receipt(), stale_after_seconds=bad)


# ---------------------------------------------------------------------------
# unavailable sources, on every plane
# ---------------------------------------------------------------------------

def test_unavailable_projected_source_is_named_never_rendered_as_empty():
    receipt = _receipt(
        _inputs(linear={"available": False, "reason": "LINEAR_READ_PATH_UNAVAILABLE"})
    )
    document = view.build_cross_plane_view(receipt)
    card = _card(document)

    assert document["state"] == "DEGRADED"
    assert card["linear"]["available"] is False
    assert card["linear"]["freshness"] == "UNAVAILABLE"
    assert card["linear"]["reason"] == "LINEAR_READ_PATH_UNAVAILABLE"
    assert card["linear"]["issues"] == []

    entry = next(row for row in document["unavailable_sources"] if row["source"] == "linear")
    assert entry["reason"] == "LINEAR_READ_PATH_UNAVAILABLE"
    assert "not testimony" in entry["omission_effect"]

    # The GitHub half of the card is still fully readable.
    assert card["github"]["available"] is True
    assert card["github"]["pull_requests"][0]["number"] == 170


def test_unavailable_non_projected_plane_keeps_its_owner_reason():
    receipt = _receipt(
        _inputs(agentos={"available": False, "reason": "MACRO_BOOT_PACKET_PATH_UNAVAILABLE"})
    )
    document = view.build_cross_plane_view(receipt)

    entry = next(
        row for row in document["unavailable_sources"] if row["source"] == "agentos"
    )
    # The owner reason is preserved, not replaced by a viewer excuse.
    assert entry["reason"] == "MACRO_BOOT_PACKET_PATH_UNAVAILABLE"
    # And it is NOT simultaneously reported as merely "not projected by us".
    assert not any(
        fact["producer_owner"] == "agentos"
        and "not projected by this cockpit consumer" in fact["reason"]
        for fact in document["unknowns"]
    )


def test_available_unprojected_plane_is_named_as_a_viewer_choice():
    document = view.build_cross_plane_view(_receipt())
    excluded = {
        fact["producer_owner"]
        for fact in document["unknowns"]
        if "not projected by this cockpit consumer" in fact["reason"]
    }
    assert {"agentos", "slack", "executive", "identities"} <= excluded


# ---------------------------------------------------------------------------
# malformed rows are counted, never silently dropped
# ---------------------------------------------------------------------------

def test_untypable_carrier_row_is_counted_not_vanished():
    receipt = _receipt()
    tampered = copy.deepcopy(receipt)
    tampered["observations"]["github"]["pull_requests"].append(
        dict(_pr(172), number="172")  # a string is not an exact PR identity
    )
    document = view.build_cross_plane_view(tampered)

    # The bad row is absent, but the omission is named rather than silent, so the
    # card can never be mistaken for a source that reported nothing.
    assert [row["number"] for row in _card(document)["github"]["pull_requests"]] == [170]
    assert any(
        fact["target_field"] == "observations.github.pull_requests"
        and "1 carrier row(s)" in fact["reason"]
        for fact in document["unknowns"]
    )
    assert document["state"] == "DEGRADED"


@pytest.mark.parametrize(
    "relations",
    [
        [{"repository": MASTER, "number": None, "relation": "program_gate"}],
        ["not-an-object"],
    ],
)
def test_benign_relation_rows_still_render_the_card(relations):
    receipt = _receipt()
    tampered = copy.deepcopy(receipt)
    tampered["observations"]["linear"]["issues"][0]["github_relations"] = relations
    document = view.build_cross_plane_view(tampered)
    assert [card["workstream"] for card in document["cards"]] == ["WS:TARGET"]


def test_an_unhashable_relation_row_degrades_typed_instead_of_crashing():
    """The shared selector assumes normalizer-typed rows; a tampered receipt must
    degrade a typed refusal rather than propagate its TypeError out of the cockpit."""

    receipt = _receipt()
    tampered = copy.deepcopy(receipt)
    tampered["observations"]["linear"]["issues"][0]["github_relations"] = [
        {"repository": MASTER, "number": [1, 2], "relation": "program_gate"}
    ]

    document = view.build_cross_plane_view(tampered)
    assert document["state"] == "DEGRADED"
    assert document["cards"] == []
    assert any("closure" in fact["reason"] for fact in document["unknowns"])
    # Nothing is dropped: every finding is still reported.
    assert document["finding_counts"] == {
        severity: sum(1 for row in receipt["findings"] if row["severity"] == severity)
        for severity in ("FATAL", "BLOCKING", "WARNING", "INFO")
    }

    # strict raises this module's typed error, never the selector's raw TypeError.
    with pytest.raises(SessionTruthContractError):
        view.build_cross_plane_view(tampered, strict=True)


# ---------------------------------------------------------------------------
# execution liveness is never asserted, including from Slack
# ---------------------------------------------------------------------------

def test_linear_and_slack_never_yield_a_running_job():
    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET"],
                "linear": ["MAS-6"],
                "repositories": [MASTER],
                "operation_key": "op-slack-001",
                "requires_executive": False,
            },
            slack=_slack(),
            linear={"available": True, "observed_at": NOW,
                    "issues": [_issue(status="In Progress")]},
        )
    )
    # Slack is genuinely exercised here: a delivered, unacked runnable message.
    assert "SLACK_TRANSPORT_WITHOUT_ACK" in {row["code"] for row in receipt["findings"]}

    document = view.build_cross_plane_view(receipt)
    card = _card(document)

    assert document["execution"]["state"] == "NOT_PROJECTED"
    issue = card["linear"]["issues"][0]
    assert issue["status"] == "In Progress"
    assert set(issue) == LITERAL_ISSUE_CARD_KEYS
    # ...but the card still refuses to claim anything is executing.
    assert issue["execution"] == {
        "state": "NOT_PROJECTED",
        "reason": issue["execution"]["reason"],
    }
    assert issue["execution"]["state"] == "NOT_PROJECTED"

    # No key anywhere in the rendered document may assert liveness.
    assert not (_all_keys(document) & FORBIDDEN_EXECUTION_KEYS)
    # And the Slack finding is surfaced, never quietly turned into a running job.
    assert "SLACK_TRANSPORT_WITHOUT_ACK" in _unattributed_codes(document)


def test_slack_delivery_is_not_execution_liveness_even_when_acked():
    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET"],
                "linear": ["MAS-6"],
                "repositories": [MASTER],
                "operation_key": "op-slack-001",
                "requires_executive": False,
            },
            slack=_slack(acked=True),
        )
    )
    document = view.build_cross_plane_view(receipt)
    assert not (_all_keys(document) & FORBIDDEN_EXECUTION_KEYS)
    assert document["execution"]["state"] == "NOT_PROJECTED"


# ---------------------------------------------------------------------------
# multi-carrier and parent/child subject forms
# ---------------------------------------------------------------------------

def test_multiple_active_carriers_subject_reaches_its_workstream_card():
    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [_pr(170, wave="R1"), _pr(171, wave="R1")],
            },
            linear={"available": True, "observed_at": NOW, "issues": [_issue()]},
        )
    )
    rule_finding = _finding(receipt, "MULTIPLE_ACTIVE_CARRIERS")
    assert rule_finding["subject"] == "WS:TARGET#R1"

    card = _card(view.build_cross_plane_view(receipt))
    # The "WS:<KEY>#<wave>" subject form is resolved to its workstream card.
    assert "MULTIPLE_ACTIVE_CARRIERS" in _codes(card)


def test_parent_child_divergence_subject_reaches_both_issue_cards():
    receipt = _receipt(
        _inputs(
            linear={
                "available": True,
                "observed_at": NOW,
                "issues": [
                    _issue("MAS-7", status="Done", workstream="WS:TARGET"),
                    _issue("MAS-6", status="In Progress", workstream="WS:TARGET",
                           parent_id="MAS-7"),
                ],
            },
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [_pr(linear=None)],
            },
        )
    )
    rule_finding = _finding(receipt, "LINEAR_PARENT_CHILD_DIVERGENCE")
    assert rule_finding["subject"] == "MAS-7->MAS-6"

    # Regression: the "A->B" subject form used to raise TypeError here, which a
    # real receipt from the real rules engine triggers on any parent/child drift.
    document = view.build_cross_plane_view(receipt)
    card = _card(document)
    assert "LINEAR_PARENT_CHILD_DIVERGENCE" in _codes(card)


# ---------------------------------------------------------------------------
# deterministic ordering
# ---------------------------------------------------------------------------

def test_output_is_byte_identical_across_repeated_renders():
    receipt = _receipt()
    first = view.build_cross_plane_view(receipt)
    second = view.build_cross_plane_view(receipt)
    assert semantic_hash(first) == semantic_hash(second)
    assert canonical_json(first) == canonical_json(second)


def test_card_and_row_order_is_independent_of_source_row_order():
    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [
                    _pr(170, linear="MAS-6"),
                    _pr(169, linear="MAS-6"),
                    _pr(171, linear="MAS-6"),
                ],
            },
            linear={
                "available": True,
                "observed_at": NOW,
                "issues": [_issue("MAS-7", number=170), _issue("MAS-6", number=170)],
            },
        )
    )
    document = view.build_cross_plane_view(receipt)
    card = _card(document)

    assert [row["number"] for row in card["github"]["pull_requests"]] == [169, 170, 171]
    assert [row["issue_id"] for row in card["linear"]["issues"]] == ["MAS-6", "MAS-7"]

    # Reverse the receipt's own row order: the view's ordering must not move.
    shuffled = copy.deepcopy(receipt)
    shuffled["observations"]["github"]["pull_requests"].reverse()
    shuffled["observations"]["linear"]["issues"].reverse()
    shuffled_card = _card(view.build_cross_plane_view(shuffled))
    assert shuffled_card["github"]["pull_requests"] == card["github"]["pull_requests"]
    assert shuffled_card["linear"]["issues"] == card["linear"]["issues"]


def test_multiple_workstreams_render_in_sorted_order_with_distinct_identities():
    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET", "WS:ALPHA"],
                "linear": ["MAS-6"],
                "repositories": [MASTER],
                "operation_key": None,
                "requires_executive": False,
            },
            agentos={
                "available": True,
                "source_sha": SHA_A,
                "state": {
                    "schema": "mastermind.agent_os_state.v1",
                    "source_records_digest": DIGEST_A,
                    "workstreams": [
                        {"key": "TARGET", "updated": "2026-08-27", "prs": []},
                        {"key": "ALPHA", "updated": "2026-08-27", "prs": []},
                    ],
                },
                "contexts": [],
            },
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [
                    _pr(171, workstream="WS:ALPHA", linear="MAS-6"),
                    _pr(170, workstream="WS:TARGET", linear="MAS-6"),
                ],
            },
            linear={"available": True, "observed_at": NOW,
                    "issues": [_issue("MAS-6", workstream="WS:TARGET")]},
        )
    )
    document = view.build_cross_plane_view(receipt)

    assert [card["workstream"] for card in document["cards"]] == ["WS:ALPHA", "WS:TARGET"]
    assert [row["number"] for row in _card(document, "WS:ALPHA")["github"]["pull_requests"]] == [171]
    assert [row["number"] for row in _card(document, "WS:TARGET")["github"]["pull_requests"]] == [170]


def test_single_workstream_does_not_claim_an_unbound_operation_carrier():
    """Cardinality one is not an owner edge, even for an exact selected operation."""

    identity_number = 181
    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET"],
                "linear": [],
                "repositories": [MASTER],
                "operation_key": "op-unbound-001",
                "requires_executive": False,
            },
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [
                    _pr(
                        identity_number, workstream=None, linear=None,
                        operation_key="op-unbound-001",
                    )
                ],
            },
            linear={"available": True, "observed_at": NOW, "issues": []},
        )
    )
    document = view.build_cross_plane_view(receipt)
    card = _card(document)

    assert card["github"]["pull_requests"] == []
    assert card["identities"]["pull_requests"] == []
    assert document["state"] == "DEGRADED"
    assert any(
        fact["target_field"] == "cards.github.pull_requests"
        and f"{MASTER}#{identity_number}" in fact["reason"]
        and "no verified Agent OS owner registry entry" in fact["reason"]
        for fact in document["unknowns"]
    )


def test_single_workstream_does_not_claim_an_unbound_seeded_linear_issue():
    """A seeded MAS issue ID may be in scope yet own no WS without an authored link."""

    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET"],
                "linear": ["MAS-7"],
                "repositories": [MASTER],
                "operation_key": None,
                "requires_executive": False,
            },
            github={"available": True, "observed_at": NOW, "pull_requests": []},
            linear={
                "available": True,
                "observed_at": NOW,
                "issues": [_issue("MAS-7", workstream=None, number=181)],
            },
        )
    )
    document = view.build_cross_plane_view(receipt)
    card = _card(document)

    assert card["linear"]["issues"] == []
    assert card["identities"]["linear_issue_ids"] == []
    assert document["state"] == "DEGRADED"
    assert any(
        fact["target_field"] == "cards.linear.issues"
        and "MAS-7:" in fact["reason"]
        and "no verified Agent OS owner registry entry" in fact["reason"]
        for fact in document["unknowns"]
    )


def test_exact_relation_selected_orphan_pr_cannot_mint_a_workstream_card():
    """A self-declared WS key in closure is context, not Agent OS ownership."""
    receipt = _receipt(
        _inputs(
            github={
                "available": True, "observed_at": NOW,
                "pull_requests": [
                    _pr(170, workstream="WS:TARGET", linear="MAS-6"),
                    _pr(999, workstream="WS:BOGUS", linear="MAS-6",
                        operation_key="op-orphan-999"),
                ],
            },
            linear={"available": True, "observed_at": NOW,
                    "issues": [_issue("MAS-6", workstream="WS:TARGET")]},
        )
    )
    assert "ORPHAN_GITHUB_CARRIER" in {row["code"] for row in receipt["findings"]}
    document = view.build_cross_plane_view(receipt)

    assert [card["workstream"] for card in document["cards"]] == ["WS:TARGET"]
    assert [row["number"] for row in _card(document)["github"]["pull_requests"]] == [170]
    assert document["state"] == "DEGRADED"
    assert "ORPHAN_GITHUB_CARRIER" in _unattributed_codes(document)
    assert any(
        fact["target_field"] == "cards.github.pull_requests"
        and f"{MASTER}#999" in fact["reason"]
        and "no verified Agent OS owner registry entry" in fact["reason"]
        for fact in document["unknowns"]
    )


def test_exact_seeded_orphan_linear_issue_cannot_mint_a_workstream_card():
    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET"], "linear": ["MAS-7"],
                "repositories": [MASTER], "operation_key": None,
                "requires_executive": False,
            },
            github={"available": True, "observed_at": NOW, "pull_requests": []},
            linear={"available": True, "observed_at": NOW,
                    "issues": [_issue("MAS-7", workstream="WS:BOGUS", number=999)]},
        )
    )
    assert "ORPHAN_LINEAR_ISSUE" in {row["code"] for row in receipt["findings"]}
    document = view.build_cross_plane_view(receipt)

    assert [card["workstream"] for card in document["cards"]] == ["WS:TARGET"]
    assert _card(document)["linear"]["issues"] == []
    assert document["state"] == "DEGRADED"
    assert "ORPHAN_LINEAR_ISSUE" in _unattributed_codes(document)
    assert any(
        fact["target_field"] == "cards.linear.issues"
        and "MAS-7:" in fact["reason"]
        and "no verified Agent OS owner registry entry" in fact["reason"]
        for fact in document["unknowns"]
    )


def test_known_carrier_workstream_cannot_override_a_conflicting_agentos_pr_owner():
    """GitHub metadata cannot reassign a PR when Agent OS authors another owner."""
    agentos = _agentos()
    agentos["state"]["workstreams"].append(
        {"key": "OTHER", "updated": "2026-08-27", "prs": []}
    )
    receipt = _receipt(
        _inputs(
            scope={
                "workstreams": ["WS:TARGET"], "linear": ["MAS-6"],
                "repositories": [MASTER], "operation_key": None,
                "requires_executive": False,
            },
            agentos=agentos,
            github={"available": True, "observed_at": NOW,
                    "pull_requests": [_pr(170, workstream="WS:OTHER", linear="MAS-6")]},
            linear={"available": True, "observed_at": NOW,
                    "issues": [_issue("MAS-6", workstream="WS:TARGET")]},
        )
    )
    document = view.build_cross_plane_view(receipt)

    assert document["state"] == "DEGRADED"
    assert all(
        not row["github"]["pull_requests"] for row in document["cards"]
    )
    assert any(
        fact["target_field"] == "cards.github.pull_requests"
        and f"{MASTER}#170" in fact["reason"]
        and "conflicts with the exact Agent OS PR ownership record" in fact["reason"]
        for fact in document["unknowns"]
    )


def test_findings_are_ordered_by_severity_then_code_then_subject():
    receipt = _receipt(
        _inputs(
            github={"available": True, "observed_at": NOW,
                    "pull_requests": [_pr(170), _pr(171)]},
            linear={"available": True, "observed_at": NOW, "issues": [_issue()]},
        )
    )
    order = {"FATAL": 0, "BLOCKING": 1, "WARNING": 2, "INFO": 3}
    for card in view.build_cross_plane_view(receipt)["cards"]:
        keys = [
            (order[row["severity"]], row["code"], row["subject"]) for row in card["findings"]
        ]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# no effect
# ---------------------------------------------------------------------------

def test_building_the_view_does_not_mutate_the_receipt():
    receipt = _receipt()
    before = copy.deepcopy(receipt)
    document = view.build_cross_plane_view(receipt, evaluated_at=LATER,
                                           stale_after_seconds=3600)
    assert receipt == before
    assert document["source_receipt"]["semantic_hash"] == receipt["semantic_hash"]
    assert document["capability"] == {"read_only": True, "effect": "NONE"}


def test_reading_a_receipt_artifact_writes_nothing(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(_receipt()), encoding="utf-8")

    before = sorted(os.listdir(tmp_path))
    document = view.read_cross_plane_view(
        path, evaluated_at=LATER, stale_after_seconds=3600
    )
    assert sorted(os.listdir(tmp_path)) == before
    assert _card(document)["identities"]["linear_issue_ids"] == ["MAS-6"]


# ---------------------------------------------------------------------------
# malformed / foreign receipts degrade rather than crash
# ---------------------------------------------------------------------------

def test_foreign_schema_is_rejected_not_rendered():
    receipt = _receipt()
    receipt["schema"] = "mastermind.some_other_receipt.v9"

    document = view.build_cross_plane_view(receipt)
    assert document["state"] == "REJECTED"
    assert document["cards"] == []
    assert document["admission"] is None
    assert document["unknowns"][0]["missingness_class"] == "DEGRADED"

    with pytest.raises(SessionTruthContractError):
        view.build_cross_plane_view(receipt, strict=True)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r.pop("observations"), id="missing-observations"),
        pytest.param(lambda r: r.pop("semantic_hash"), id="missing-digest"),
        pytest.param(lambda r: r["observations"].pop("linear"), id="missing-plane"),
        pytest.param(lambda r: r.pop("admission"), id="missing-admission"),
        pytest.param(lambda r: r.pop("scope"), id="missing-scope"),
        pytest.param(lambda r: r.__setitem__("semantic_hash", "not-a-digest"),
                     id="bad-digest"),
        pytest.param(lambda r: r.__setitem__("unexpected", 1), id="unknown-key"),
        pytest.param(lambda r: r["findings"][0].pop("repair_owner"),
                     id="finding-missing-repair-owner"),
    ],
)
def test_truncated_or_tampered_receipts_are_rejected(mutate):
    receipt = _receipt_with_findings()
    mutate(receipt)
    document = view.build_cross_plane_view(receipt)
    assert document["state"] == "REJECTED"
    assert document["cards"] == []


@pytest.mark.parametrize(
    "field,foreign",
    [
        ("workstreams", "WS:TARGET"),
        ("workstreams", ["WS:TARGET", "invalid"]),
        ("linear", "MAS-6"),
        ("repositories", MASTER),
        ("operation_key", []),
        ("requires_executive", "false"),
    ],
)
def test_foreign_receipt_scope_fails_the_authoritative_shape_gate(field, foreign):
    receipt = _receipt()
    receipt["scope"][field] = foreign
    document = view.build_cross_plane_view(receipt)
    assert document["state"] == "REJECTED"
    assert document["cards"] == []
    with pytest.raises(SessionTruthContractError, match="scope"):
        view.build_cross_plane_view(receipt, strict=True)


def test_foreign_receipt_scope_rejects_undeclared_fields():
    receipt = _receipt()
    receipt["scope"]["extra_actor"] = "source_bypass"
    assert view.build_cross_plane_view(receipt)["state"] == "REJECTED"
    with pytest.raises(SessionTruthContractError, match="scope"):
        view.build_cross_plane_view(receipt, strict=True)


def test_finding_with_an_invalid_severity_is_rejected():
    receipt = _receipt()
    receipt["findings"].append(
        {"code": "X", "severity": "CATASTROPHIC", "subject": "s", "repair_owner": "x",
         "canonical_owner": "x", "modification_consequence": "x"}
    )
    assert view.build_cross_plane_view(receipt)["state"] == "REJECTED"


def test_content_that_no_longer_hashes_to_its_digest_is_flagged_not_trusted():
    receipt = _receipt_with_findings()
    tampered = copy.deepcopy(receipt)
    # Downgrade a warning's severity in place, leaving the stored digest stale.
    tampered["findings"][0]["severity"] = "INFO"

    document = view.build_cross_plane_view(tampered)
    assert document["digest_check"]["state"] == "MISMATCH"
    assert document["digest_check"]["stored"] == receipt["semantic_hash"]
    assert document["digest_check"]["recomputed"] != receipt["semantic_hash"]
    assert document["state"] == "DEGRADED"
    assert any(fact["target_field"] == "semantic_hash" for fact in document["unknowns"])


def test_unreadable_or_non_json_artifact_degrades_to_rejected(tmp_path):
    missing = view.read_cross_plane_view(tmp_path / "absent.json")
    assert missing["state"] == "REJECTED"
    assert missing["cards"] == []

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert view.read_cross_plane_view(broken)["state"] == "REJECTED"

    # strict must raise the module's own typed error, not an OSError.
    with pytest.raises(SessionTruthContractError):
        view.read_cross_plane_view(broken, strict=True)
    with pytest.raises(SessionTruthContractError):
        view.read_cross_plane_view(tmp_path / "absent.json", strict=True)


def test_strict_raises_rather_than_degrading_on_an_unclosable_scope():
    receipt = _receipt()
    unclosable = copy.deepcopy(receipt)
    unclosable["scope"] = {
        "workstreams": [], "linear": [], "repositories": [MASTER],
        "operation_key": None, "requires_executive": False,
    }

    document = view.build_cross_plane_view(unclosable)
    assert document["state"] == "DEGRADED"
    assert document["cards"] == []
    # Findings are still surfaced rather than dropped on this path.
    assert document["finding_counts"] == {
        severity: sum(1 for row in receipt["findings"] if row["severity"] == severity)
        for severity in ("FATAL", "BLOCKING", "WARNING", "INFO")
    }
    assert len(document["unattributed_findings"]) == len(receipt["findings"])

    with pytest.raises(SessionTruthContractError):
        view.build_cross_plane_view(unclosable, strict=True)


def test_evaluated_at_must_be_offset_aware():
    with pytest.raises(SessionTruthContractError):
        view.build_cross_plane_view(_receipt(), evaluated_at="2026-08-27T08:00:00")


# ---------------------------------------------------------------------------
# the closure is the rules engine's, not a second one
# ---------------------------------------------------------------------------

def test_scope_closure_is_delegated_to_the_rules_engine_own_selector(monkeypatch):
    receipt = _receipt()
    captured: list[dict] = []
    real = view.select_session_truth_scope

    def spy(inputs):
        captured.append(copy.deepcopy(dict(inputs)))
        return real(inputs)

    monkeypatch.setattr(view, "select_session_truth_scope", spy)
    document = view.build_cross_plane_view(receipt)

    assert len(captured) == 1
    forwarded = captured[0]
    # The receipt's own scope and every plane are forwarded verbatim: this view
    # does not narrow, widen or re-derive the closure.
    assert forwarded["scope"] == receipt["scope"]
    for plane in ("agentos", "github", "linear", "slack", "executive", "identities"):
        assert forwarded[plane] == receipt["observations"][plane]
    # And the cards really are that selector's answer.
    assert [card["workstream"] for card in document["cards"]] == sorted(
        real(
            {"scope": receipt["scope"],
             **{name: receipt["observations"][name]
                for name in ("agentos", "github", "linear", "slack", "executive",
                             "identities")}}
        ).workstreams
    )


def test_unselected_repositories_are_fenced_out_of_the_cards():
    receipt = _receipt(
        _inputs(
            github={
                "available": True,
                "observed_at": NOW,
                "pull_requests": [
                    _pr(170),
                    # Same workstream, different repository: outside the requested fence.
                    dict(_pr(171), repository="someone-else/Other-Repo"),
                ],
            },
        )
    )
    card = _card(view.build_cross_plane_view(receipt))
    assert [row["number"] for row in card["github"]["pull_requests"]] == [170]
    assert "someone-else/Other-Repo" not in card["identities"]["repositories"]


# ---------------------------------------------------------------------------
# house drift guards
# ---------------------------------------------------------------------------

def test_missingness_vocabulary_matches_the_house_precedent():
    """The closed vocabulary is copied from fabric_job_view; prove it has not drifted."""

    fabric_job_view = pytest.importorskip("control_plane.fabric_job_view")
    assert view.MISSINGNESS_CLASSES == fabric_job_view.MISSINGNESS_CLASSES


def test_severity_vocabulary_is_the_contract_registry_not_a_local_list():
    from control_plane.session_truth_contract import FINDING_SEVERITIES

    counts = view.build_cross_plane_view(_receipt())["finding_counts"]
    assert set(counts) == set(FINDING_SEVERITIES)