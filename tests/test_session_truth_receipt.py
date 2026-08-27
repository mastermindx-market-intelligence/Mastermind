from __future__ import annotations

import copy

import pytest

try:
    from control_plane.session_truth import (
        build_receipt,
        compute_admission,
        render_receipt,
        semantic_projection,
    )
except ModuleNotFoundError as exc:
    if exc.name != "control_plane.session_truth":
        raise

    def _missing(*_args, **_kwargs):
        raise NotImplementedError("session_truth receipt assembly not implemented")

    build_receipt = _missing
    compute_admission = _missing
    render_receipt = _missing
    semantic_projection = _missing


MASTER = "mastermindx-market-intelligence/Mastermind"
SHA_A = "a" * 40
SHA_B = "b" * 40
NOW = "2026-08-27T08:00:00Z"


def healthy_inputs() -> dict:
    return {
        "schema": "mastermind.session_truth_inputs.v1",
        "scope": {
            "workstreams": ["WS:TARGET"],
            "linear": [],
            "repositories": [MASTER],
            "operation_key": None,
            "requires_executive": False,
        },
        "skillpack": {
            "repository": MASTER,
            "sha": SHA_A,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.0",
            "minimum_bootstrap_major": 1,
            "available": True,
        },
        "agentos": {
            "available": True,
            "source_sha": SHA_B,
            "state": {
                "schema": "agent_os_state.v1",
                "generated_at": NOW,
                "workstreams": [],
                "warnings": [],
            },
            "contexts": [],
            "warnings": [],
        },
        "github": {
            "available": True,
            "observed_at": NOW,
            "pull_requests": [],
        },
        "linear": {
            "available": True,
            "observed_at": NOW,
            "issues": [],
        },
        "slack": {
            "available": True,
            "observed_at": NOW,
            "channels": [],
            "messages": [],
        },
        "executive": {
            "available": True,
            "observed_at": NOW,
            "fresh": True,
            "do_not_submit": False,
            "grounding_sha": SHA_A,
            "operations": [],
        },
        "identities": {
            "available": True,
            "observed_at": NOW,
            "bindings": [],
        },
    }


def finding(code: str, severity: str) -> dict:
    return {
        "code": code,
        "severity": severity,
        "canonical_owner": "owner",
        "subject": "subject",
        "source_a": None,
        "source_b": None,
        "repair_owner": "repair",
        "modification_consequence": "test",
        "details": {},
    }


@pytest.mark.parametrize(
    ("findings", "requires_exec", "expected", "safe"),
    [
        ([finding("ACTOR_ROLE_COLLISION", "FATAL")], False, "MODIFICATION_REFUSED", False),
        ([finding("RUNTIME_STATE_UNAVAILABLE", "BLOCKING")], True, "DIALOGUE_ONLY", False),
        ([finding("UNKNOWN_SEAT_IDENTITY", "WARNING")], False, "GROUNDING_PARTIAL", True),
        ([finding("BUILD_VISIBILITY_STALE", "INFO")], False, "GROUNDING_COMPLETE", True),
        ([], False, "GROUNDING_COMPLETE", True),
    ],
)
def test_admission_precedence(findings, requires_exec, expected, safe):
    doc = healthy_inputs()
    doc["scope"]["requires_executive"] = requires_exec
    admission = compute_admission(doc, findings)
    assert admission["mode"] == expected
    assert admission["modification_safe"] is safe


@pytest.mark.parametrize(
    ("source", "scope_change"),
    [
        ("skillpack", None),
        ("agentos", None),
        ("github", None),
        ("linear", "linear"),
        ("executive", "executive"),
    ],
)
def test_required_source_unavailable_for_scope_is_dialogue_only(source, scope_change):
    doc = healthy_inputs()
    if scope_change == "linear":
        doc["scope"]["linear"] = ["MAS-10"]
    if scope_change == "executive":
        doc["scope"]["requires_executive"] = True
    unavailable = {"available": False, "reason": f"{source.upper()}_UNAVAILABLE"}
    if source == "skillpack":
        unavailable["sha"] = SHA_A
    doc[source] = unavailable

    admission = compute_admission(doc, [])
    assert admission["mode"] == "DIALOGUE_ONLY"
    assert admission["modification_safe"] is False
    assert source in admission["required_sources_unavailable"]


@pytest.mark.parametrize("source", ["slack", "identities"])
def test_optional_source_unavailable_is_partial(source):
    doc = healthy_inputs()
    doc[source] = {"available": False, "reason": f"{source.upper()}_UNAVAILABLE"}
    admission = compute_admission(doc, [])
    assert admission["mode"] == "GROUNDING_PARTIAL"
    assert admission["modification_safe"] is True
    assert source in admission["optional_sources_unavailable"]


def test_envelope_clock_does_not_change_semantic_hash():
    inputs = healthy_inputs()
    one = build_receipt(
        inputs,
        observed_started_at="2026-08-27T05:00:00Z",
        observed_ended_at="2026-08-27T05:00:01Z",
    )
    two = build_receipt(
        inputs,
        observed_started_at="2026-08-27T05:10:00Z",
        observed_ended_at="2026-08-27T05:10:01Z",
    )
    assert one["semantic_hash"] == two["semantic_hash"]
    assert semantic_projection(one) == semantic_projection(two)
    assert one["observation"] != two["observation"]


def test_source_revision_change_changes_semantic_hash():
    one_inputs = healthy_inputs()
    two_inputs = healthy_inputs()
    two_inputs["github"]["observed_at"] = "2026-08-27T08:01:00Z"
    one = build_receipt(one_inputs, observed_started_at=NOW, observed_ended_at=NOW)
    two = build_receipt(two_inputs, observed_started_at=NOW, observed_ended_at=NOW)
    assert one["semantic_hash"] != two["semantic_hash"]


def test_semantic_projection_excludes_only_envelope_and_hash():
    receipt = build_receipt(healthy_inputs(), observed_started_at=NOW, observed_ended_at=NOW)
    projection = semantic_projection(receipt)
    assert set(projection) == set(receipt) - {"observation", "semantic_hash"}
    assert "scope" in projection
    assert "skillpack" in projection
    assert "observations" in projection
    assert "findings" in projection
    assert "admission" in projection


def test_build_receipt_detects_warning_and_does_not_mutate_input():
    inputs = healthy_inputs()
    inputs["agentos"]["state"]["direct_state_hash"] = "sha256:" + "1" * 64
    inputs["agentos"]["state"]["generated_state_hash"] = "sha256:" + "2" * 64
    before = copy.deepcopy(inputs)

    receipt = build_receipt(inputs, observed_started_at=NOW, observed_ended_at=NOW)

    assert inputs == before
    assert receipt["schema"] == "mastermind.session_truth_receipt.v1"
    assert [item["code"] for item in receipt["findings"]] == [
        "DIRECT_GENERATED_STATE_DIVERGENCE"
    ]
    assert receipt["admission"]["mode"] == "GROUNDING_PARTIAL"


def test_render_receipt_is_deterministic_bounded_summary():
    receipt = build_receipt(healthy_inputs(), observed_started_at=NOW, observed_ended_at=NOW)
    rendered = render_receipt(receipt)
    assert rendered == render_receipt(receipt)
    assert rendered.startswith("Session Truth Receipt\n")
    assert "mode: GROUNDING_COMPLETE" in rendered
    assert f"semantic_hash: {receipt['semantic_hash']}" in rendered
    assert "modification_safe: true" in rendered
    assert f"source.skillpack: available=true sha={SHA_A}" in rendered
    assert f"source.agentos: available=true source_sha={SHA_B}" in rendered
    assert f"source.github: available=true observed_at={NOW}" in rendered
    assert "findings: total=0 FATAL=0 BLOCKING=0 WARNING=0 INFO=0" in rendered
    assert "executed=true" not in rendered


def test_render_unavailable_source_never_looks_healthy():
    inputs = healthy_inputs()
    inputs["slack"] = {"available": False, "reason": "SLACK_READ_UNAVAILABLE"}
    receipt = build_receipt(inputs, observed_started_at=NOW, observed_ended_at=NOW)
    rendered = render_receipt(receipt)
    assert "mode: GROUNDING_PARTIAL" in rendered
    assert "source.slack: available=false reason=SLACK_READ_UNAVAILABLE" in rendered
    assert "source.slack: available=true" not in rendered


def test_render_has_one_line_per_finding():
    inputs = healthy_inputs()
    inputs["agentos"]["state"]["direct_state_hash"] = "sha256:" + "1" * 64
    inputs["agentos"]["state"]["generated_state_hash"] = "sha256:" + "2" * 64
    receipt = build_receipt(inputs, observed_started_at=NOW, observed_ended_at=NOW)
    rendered = render_receipt(receipt)
    finding_lines = [line for line in rendered.splitlines() if line.startswith("finding: ")]
    assert len(finding_lines) == len(receipt["findings"]) == 1
    assert "WARNING DIRECT_GENERATED_STATE_DIVERGENCE" in finding_lines[0]
