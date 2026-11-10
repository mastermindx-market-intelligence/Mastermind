"""Tests for ``control_plane/child_execution_contracts.py`` — MMOS V1 WO-02.

The shared child execution contracts for the Mastermind/Hermes routing
boundary: the ``ChildRoutingPolicy`` port with canonical long class names,
the classification record, ``ChildExecutionRequest.v1``, ``ExecutionBinding.v1``,
``RoutePreview.v1`` and the decision/event schema.

File choice (WO-02 acceptance, resolved OQ-12 2026-11-08): a NEW test file
``tests/test_child_execution_contracts.py`` rather than an extension of
``tests/test_executive_model_router.py`` — the contracts module is shared
law, not ModelRouter behaviour, and deserves its own pinned contract.

Sections:
* the 23 WO-00 (Hermes ``mmx-router`` plugin) cases re-expressed in pytest
  style, numbered 1..23 exactly as in the plugin's ``test_child_routing_policy.py``
  (cases 12–15 are one parametrized test = 4 collected items);
* canonical-vocabulary and contract tests for every record, incl. JSON
  round-trips;
* a PARITY test importing the live Hermes plugin module by path via
  importlib (skipped cleanly when the file is absent) and asserting
  identical ``(resolved, downgraded, witness_problem)`` on all 23 cases.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from control_plane import child_execution_contracts as contracts
from control_plane.child_execution_contracts import (
    C0_MECHANICAL,
    C1_ROUTINE_BOUNDED,
    C2_COMPLEX_BOUNDED,
    C3_FRONTIER_JUDGMENT,
    REVIEW_LANE,
    CANONICAL_ROUTE_OPTIONS,
    CapabilityRequest,
    ChildExecutionRequest,
    ChildRoutingPolicy,
    DecisionEvent,
    ExecutionBinding,
    ExecutionProfile,
    POLICY_REVISION,
    PREVIEW_AUTHORITY,
    RoutePreview,
    RoutingDecision,
    TaskClassification,
    canonical_task_complexity,
    witness_disposition_of,
)

WITNESS = "witness: cross-repo contract conflict between OMH chains and fabric pools, unresolved"

#: The plugin-era raw config shape (short ``C0``..``C3`` spellings under the
#: ``task_class`` key, provider/model rows present).  The port must accept it
#: unchanged; the parity test feeds this SAME dict to both implementations.
HERMES_OPTIONS = {
    "mechanical": {"name": "mechanical", "task_class": "C0", "description": "C0 sweeps.",
                   "provider": "byteplus-coding", "model": "deepseek-v4-1-flash-261017"},
    "routine": {"name": "routine", "task_class": "C1", "description": "C1 bounded.",
                "provider": "byteplus-coding", "model": "deepseek-v4.1-flash"},
    "hard": {"name": "hard", "task_class": "C2", "description": "C2 workhorse.",
             "provider": "zai", "model": "glm-5.3-flash"},
    "frontier": {"name": "frontier", "task_class": "C3", "description": "C3 gated.",
                 "provider": "zai", "model": "glm-5.3",
                 "requires_witness": True, "downgrade_to": "hard",
                 "fallback_providers": ["zai-fabric", "anthropic"]},
    "review": {"name": "review", "task_class": "reviewer", "description": "Reviewer.",
               "provider": "zai", "model": "glm-5.3"},
}


def ev(requested, goal="", context="", options=None, min_chars=24):
    return ChildRoutingPolicy(min_chars).evaluate(
        requested, goal, context,
        options if options is not None else CANONICAL_ROUTE_OPTIONS)


def lonely_options():
    options = {name: dict(entry) for name, entry in CANONICAL_ROUTE_OPTIONS.items()}
    options["frontier"]["downgrade_to"] = "nonexistent"
    return options


def lonely_hermes_options():
    options = {name: dict(entry) for name, entry in HERMES_OPTIONS.items()}
    options["frontier"]["downgrade_to"] = "nonexistent"
    return options


# =============================================================================
# The 23 WO-00 cases, re-expressed in pytest style (numbering as in the plugin)
# =============================================================================

# --- the five adversarial witness cases ---------------------------------------

def test_case_01_all_inflation_witness_rejected_downgrades_to_hard():
    d = ev("frontier", context="witness: this is a very urgent and important large production task")
    assert d.resolved == "hard" and d.downgraded
    assert d.witness_problem == "witness contains only impact/inflation words, no concrete evidence"


def test_case_02_short_witness_rejected_with_exact_char_count():
    d = ev("frontier", context="witness: " + "y" * 12)  # 12-char content
    assert d.resolved == "hard"
    assert d.witness_problem == "witness is 12 chars (< 24)"


def test_case_03_23_char_boundary_content_rejected():
    d = ev("frontier", context="witness: " + "z" * 23)  # pin the low side of 24
    assert d.witness_problem == "witness is 23 chars (< 24)"
    assert d.resolved == "hard"


def test_case_04_24_char_concrete_witness_accepted():
    d = ev("frontier", context="witness: " + "ab" * 12)  # exactly 24 chars, concrete tokens
    assert d.resolved == "frontier" and not d.downgraded
    assert d.witness_problem == ""
    assert d.task_complexity == C3_FRONTIER_JUDGMENT


def test_case_05_witness_only_in_context_accepted():
    d = ev("frontier", goal="redesign the fabric pool scheduler", context=WITNESS)
    assert d.resolved == "frontier" and not d.downgraded
    assert "fabric pools" in d.witness


def test_case_06_mid_line_witness_not_matched():
    d = ev("frontier", goal="the task said witness: " + "concrete evidence naming the unresolved tradeoff here")
    assert d.resolved == "hard"
    assert d.witness_problem == "no 'witness:' line in the task"


# --- the newline-join regression (past bug: space join hid the ^ anchor) ------

def test_case_07_newline_join_keeps_context_leading_witness_anchored():
    d = ev("frontier", goal="refactor the routing audit tables", context=WITNESS + "\nextra line")
    assert d.resolved == "frontier"
    assert d.witness.startswith("cross-repo contract")


def test_case_08_witness_at_end_of_goal_still_anchored_with_context_present():
    d = ev("frontier", goal="refactor the routing audit tables\n" + WITNESS, context="more context text")
    assert d.resolved == "frontier"
    assert d.witness.startswith("cross-repo contract")


# --- the rest of the law ------------------------------------------------------

def test_case_09_no_witness_downgrades_to_declared_c2_target():
    d = ev("frontier", goal="important production refactor")
    assert d.resolved == "hard" and d.downgraded
    assert d.task_complexity == C2_COMPLEX_BOUNDED  # the explicit downgrade lane
    assert d.reason.startswith("downgraded frontier->hard: ")


def test_case_10_bare_not_witnesses_phrase_rejected():
    d = ev("frontier", context="witness: frontier quota is unused")
    assert "bare inflation word" in (d.witness_problem or "")


def test_case_11_no_lawful_downgrade_target_refused():
    d = ev("frontier", goal="x", options=lonely_options())
    assert d.resolved == "" and d.task_complexity == ""
    assert "needs a concrete witness" in d.reason


@pytest.mark.parametrize("opt", ["mechanical", "routine", "hard", "review"])
def test_cases_12_to_15_non_witness_classes_resolve_without_witness(opt):
    d = ev(opt, goal="anything important production urgent")
    assert d.resolved == opt
    assert d.witness_problem is None
    assert not d.downgraded


def test_case_16_resolved_is_a_class_name_never_provider_or_model():
    d = ev("frontier", goal="x\n" + WITNESS)
    assert d.resolved in CANONICAL_ROUTE_OPTIONS
    assert d.resolved not in ("zai", "glm-5.3", "zai-fabric")


def test_case_17_unknown_option_refused_cleanly():
    d = ev("opus", goal="x")
    assert d.resolved == ""
    assert "not a configured route" in d.reason


def test_case_18_decision_carries_task_complexity_and_policy_revision():
    d = ev("hard", goal="debug the pool")
    assert d.task_complexity == C2_COMPLEX_BOUNDED
    assert d.policy_revision == POLICY_REVISION


def test_case_19_witness_min_chars_override_enforced():
    d = ChildRoutingPolicy(40).evaluate("frontier", "", "witness: " + "ab" * 12, CANONICAL_ROUTE_OPTIONS)
    assert d.resolved == "hard"
    assert d.witness_problem == "witness is 24 chars (< 40)"


def test_case_20_bullet_prefixed_witness_accepted():
    d = ev("frontier", goal="- witness: multi-file race with two conflicting owners over shared cache")
    assert d.resolved == "frontier"
    assert d.witness.startswith("multi-file race")


def test_case_21_inflation_words_verbatim_22_entries():
    assert len(contracts._INFLATION_WORDS) == 22
    assert contracts._INFLATION_WORDS >= {"important", "production", "critical", "urgent",
                                          "decomposed", "quota", "extremely"}


def test_case_22_glue_words_verbatim_39_entries():
    assert len(contracts._GLUE_WORDS) == 39
    assert contracts._GLUE_WORDS >= {"this", "the", "must", "mission", "program", "project"}


def test_case_23_options_dict_never_mutated():
    snapshot = repr(CANONICAL_ROUTE_OPTIONS["frontier"])
    ev("frontier", goal="x", context="witness: " + "q" * 30)
    assert repr(CANONICAL_ROUTE_OPTIONS["frontier"]) == snapshot


# =============================================================================
# Canonical vocabulary and the port's contract with the plugin config shape
# =============================================================================

def test_canonical_vocabulary_uses_long_names_at_the_boundary():
    assert contracts.CANONICAL_TASK_COMPLEXITIES == (
        C0_MECHANICAL, C1_ROUTINE_BOUNDED, C2_COMPLEX_BOUNDED, C3_FRONTIER_JUDGMENT)
    assert contracts.DISPLAY_SHORTHAND[C3_FRONTIER_JUDGMENT] == "C3"
    for spelling in ("C2", "c2", "C2_COMPLEX_BOUNDED", "c2_complex_bounded"):
        assert canonical_task_complexity(spelling) == C2_COMPLEX_BOUNDED
    assert canonical_task_complexity("reviewer") == REVIEW_LANE
    assert canonical_task_complexity("") == ""
    assert canonical_task_complexity("C9_UNHEARD_OF") == "C9_UNHEARD_OF"  # forward-compat passthrough


def test_canonical_options_declare_the_c2_downgrade_lane():
    frontier = CANONICAL_ROUTE_OPTIONS["frontier"]
    assert frontier["requires_witness"] is True
    target = frontier["downgrade_to"]
    assert target in CANONICAL_ROUTE_OPTIONS
    assert (CANONICAL_ROUTE_OPTIONS[target]["task_complexity"]
            == contracts.FRONTIER_DOWNGRADE_COMPLEXITY == C2_COMPLEX_BOUNDED)


def test_port_accepts_the_plugin_shaped_options_unchanged():
    d = ChildRoutingPolicy().evaluate("frontier", "x\n" + WITNESS, "", HERMES_OPTIONS)
    assert d.resolved == "frontier"
    assert d.task_complexity == C3_FRONTIER_JUDGMENT
    assert d.witness_problem == ""
    d2 = ChildRoutingPolicy().evaluate("frontier", "important refactor", "", HERMES_OPTIONS)
    assert d2.resolved == "hard" and d2.task_complexity == C2_COMPLEX_BOUNDED


def test_module_is_pure_stdlib():
    tree = ast.parse(Path(contracts.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert imported
    assert not (imported - set(sys.stdlib_module_names)), "shared contracts must stay stdlib-pure"


# =============================================================================
# Classification record (Rev 4 §S3.A l.181–186)
# =============================================================================

def test_classification_record_keeps_five_dimensions_separate():
    record = TaskClassification(
        task_kind="code", task_complexity=C2_COMPLEX_BOUNDED,
        execution_risk="elevated", business_impact="high",
        execution_profile=ExecutionProfile(
            native_tools=("terminal", "filesystem:workspace"),
            cpu_cores=2, memory_gib=4.0, scratch_gib=1.0))
    assert record.problems() == ()


def test_classification_flags_c3_without_witness_regardless_of_impact():
    record = TaskClassification(
        task_kind="code", task_complexity=C3_FRONTIER_JUDGMENT,
        execution_risk="critical", business_impact="critical", frontier_witness="")
    problems = record.problems()
    assert problems
    assert "frontier witness gate" in problems[0]
    assert "business impact is never a witness" in problems[0]


def test_classification_accepts_shorthand_and_normalizes():
    record = TaskClassification(task_kind="research", task_complexity="c3")
    assert record.task_complexity == C3_FRONTIER_JUDGMENT
    assert "frontier witness gate" in record.problems()[0]


def test_classification_round_trip():
    record = TaskClassification(
        task_kind="code", task_complexity="C1",
        execution_profile={"native_tools": ["terminal"], "cpu_cores": 1})
    restored = TaskClassification.from_dict(json.loads(json.dumps(record.to_dict())))
    assert restored == record
    assert restored.execution_profile.native_tools == ("terminal",)


# =============================================================================
# ChildExecutionRequest.v1 — idempotency, digest, validation, round trip
# =============================================================================

def _sample_request(**overrides):
    kwargs = dict(
        root_ref="root-1",
        immediate_parent_run_ref="parent-7",
        logical_child_key="child-a",
        operation_key="op-42",
        task_kind="code",
        requested_complexity=C3_FRONTIER_JUDGMENT,
        frontier_witness="cross-repo contract conflict between OMH chains and fabric pools, unresolved",
        routing_decision=ev("frontier", goal="x\n" + WITNESS),
        brief_ref="briefs/42",
        brief_digest="a" * 64,
        required_capabilities=(CapabilityRequest("terminal", True, "runs pytest"),),
        harness_preference="pytest",
        scope_ref="scopes/9",
        scope_digest="b" * 64,
        budget_grant_ref="grants/5",
        preview_id="pv-1",
        notes="free-text for the reviewer",
    )
    kwargs.update(overrides)
    return ChildExecutionRequest(**kwargs)


def test_request_idempotency_key_is_root_parent_child():
    request = _sample_request()
    assert request.idempotency_key() == ("root-1", "parent-7", "child-a")


def test_request_digest_is_deterministic_sha256_and_notes_are_not_identity():
    a = _sample_request()
    b = _sample_request(notes="a completely different note")
    c = _sample_request(logical_child_key="child-b")
    d = _sample_request(operation_key="op-43")  # same key, different content
    assert len(a.request_digest) == 64
    int(a.request_digest, 16)  # lowercase hex
    assert a.request_digest == b.request_digest  # notes never participate
    assert a.request_digest != c.request_digest
    assert a.request_digest != d.request_digest
    assert a.is_idempotent_retry(b)
    assert not a.is_idempotency_conflict(b)
    assert not a.is_idempotency_conflict(c)  # different key: a different request, not a conflict
    assert not a.is_idempotent_retry(c)
    assert a.is_idempotency_conflict(d)  # same key, different digest: conflict, never a re-run
    assert not a.is_idempotent_retry(d)


def test_request_validates_required_fields():
    with pytest.raises(ValueError, match="root_ref"):
        _sample_request(root_ref="")
    with pytest.raises(ValueError, match="immediate_parent_run_ref"):
        _sample_request(immediate_parent_run_ref=" ")
    with pytest.raises(ValueError, match="logical_child_key"):
        _sample_request(logical_child_key="")
    with pytest.raises(ValueError, match="requested_complexity"):
        _sample_request(requested_complexity="C4_MIDDLING")
    with pytest.raises(ValueError, match="requested_complexity"):
        _sample_request(requested_complexity="")
    with pytest.raises(ValueError, match="fallback_mode"):
        _sample_request(fallback_mode="always_local")
    with pytest.raises(ValueError, match="brief_digest"):
        _sample_request(brief_digest="deadbeef")


def test_request_rejects_embedded_policy_revision_drift():
    stale = RoutingDecision(
        requested="frontier", resolved="frontier", task_complexity=C3_FRONTIER_JUDGMENT,
        downgraded=False, witness_problem="", reason="", witness="w" * 30,
        policy_revision="0.9.0")
    with pytest.raises(ValueError, match="policy revision drift"):
        _sample_request(routing_decision=stale)


def test_request_round_trip_through_json():
    request = _sample_request()
    payload = json.loads(json.dumps(request.to_dict()))
    assert payload["schema"] == "ChildExecutionRequest.v1"
    assert payload["request_digest"] == request.request_digest
    restored = ChildExecutionRequest.from_dict(payload)
    assert restored == request
    assert restored.request_digest == request.request_digest


def test_request_from_dict_rejects_tampered_content():
    payload = _sample_request().to_dict()
    payload["operation_key"] = "different-op"  # content changed, digest unchanged
    with pytest.raises(ValueError, match="request_digest mismatch"):
        ChildExecutionRequest.from_dict(payload)


# =============================================================================
# ExecutionBinding.v1
# =============================================================================

def _sample_binding(**overrides):
    kwargs = dict(
        root_run_ref="root-1", immediate_parent_run_ref="parent-7",
        logical_child_key="child-a", request_digest=_sample_request().request_digest,
        effective_complexity=C2_COMPLEX_BOUNDED,
        original_root_orchestrator_ref="principal-1", task_kind="code",
        job_ref="jobs/77", attempt_ref="attempts/9",
        decision_ref="decisions/4", scope_digest="b" * 64,
        budget_grant_ref="grants/5", adapter_id="canonical-paid-fabric",
        model_ref="models/glm-5.3", provider_ref="providers/zai",
        pool_ref="pools/zai-main",
        shared_quota_resource_refs=("quota/zai-main", "quota/anthropic-shared"),
        host_id="m1-studio", worker_id="workers/12", host_boot_id="boot-2026-11-08",
        assignment_generation=3, fence_counter=7, lease_expiry="2026-11-08T12:30:00Z",
    )
    kwargs.update(overrides)
    return ExecutionBinding(**kwargs)


def test_binding_binds_only_the_admitted_request():
    request = _sample_request()
    assert _sample_binding().binds_request(request)
    assert not _sample_binding(request_digest="c" * 64).binds_request(request)
    assert not _sample_binding(logical_child_key="child-z").binds_request(request)
    assert _sample_binding().child_identity() == ("root-1", "parent-7", "child-a")


def test_binding_validation():
    with pytest.raises(ValueError, match="request_digest"):
        _sample_binding(request_digest="not-hex")
    with pytest.raises(ValueError, match="effective_complexity"):
        _sample_binding(effective_complexity="ultra")
    with pytest.raises(ValueError, match="fence_counter"):
        _sample_binding(fence_counter=-1)


def test_binding_round_trip_through_json():
    binding = _sample_binding()
    payload = json.loads(json.dumps(binding.to_dict()))
    assert payload["schema"] == "ExecutionBinding.v1"
    assert ExecutionBinding.from_dict(payload) == binding


# =============================================================================
# RoutePreview.v1 — fixed authority, distinct identities, enums, round trip
# =============================================================================

def _sample_preview(**overrides):
    kwargs = dict(
        preview_id="pv-1", requested_complexity=C3_FRONTIER_JUDGMENT,
        effective_complexity=C2_COMPLEX_BOUNDED, witness_disposition="downgraded",
        request_digest="d" * 64, registry_revision="rev-9",
        suitability_tiers=("hard", "routine"),
        candidate_reason_codes=("witness_gate",),
        observation_refs=("obs/1",), observed_at="2026-11-08T12:00:00Z",
        expires_at="2026-11-08T12:05:00Z",
        capacity_knowledge="configured_only", rank_basis="suitability_only",
        decision_id="dec-1", attempt_ref="att-1",
    )
    kwargs.update(overrides)
    return RoutePreview(**kwargs)


def test_preview_authority_is_a_fixed_constant_and_never_armed():
    preview = _sample_preview()
    assert preview.authority == "NONE_SOURCE_PREVIEW_ONLY" == PREVIEW_AUTHORITY
    assert preview.production_armed is False
    with pytest.raises(TypeError):  # non-init field: no caller can ever set it
        RoutePreview(preview_id="pv", requested_complexity=C1_ROUTINE_BOUNDED,
                     effective_complexity=C1_ROUTINE_BOUNDED,
                     witness_disposition="not_required", authority="SHARED_FABRIC")


def test_preview_from_dict_rejects_foreign_authority_or_armed_previews():
    payload = _sample_preview().to_dict()
    payload["authority"] = "SHARED_FABRIC"
    with pytest.raises(ValueError, match="authority"):
        RoutePreview.from_dict(payload)
    payload = _sample_preview().to_dict()
    payload["production_armed"] = True
    with pytest.raises(ValueError, match="never production-armed"):
        RoutePreview.from_dict(payload)


def test_preview_keeps_decision_and_attempt_identities_distinct():
    with pytest.raises(ValueError, match="distinct identities"):
        _sample_preview(preview_id="same", decision_id="same")
    with pytest.raises(ValueError, match="distinct identities"):
        _sample_preview(preview_id="same", attempt_ref="same")
    with pytest.raises(ValueError, match="distinct identities"):
        _sample_preview(decision_id="same", attempt_ref="same")


def test_preview_enum_and_complexity_validation():
    with pytest.raises(ValueError, match="capacity_knowledge"):
        _sample_preview(capacity_knowledge="omniscient")
    with pytest.raises(ValueError, match="rank_basis"):
        _sample_preview(rank_basis="vibes")
    with pytest.raises(ValueError, match="witness_disposition"):
        _sample_preview(witness_disposition="generous")
    with pytest.raises(ValueError, match="requested_complexity"):
        _sample_preview(requested_complexity="legendary")
    assert _sample_preview(requested_complexity="C3").requested_complexity == C3_FRONTIER_JUDGMENT


def test_preview_capacity_knowledge_and_rank_basis_vocabularies():
    assert contracts.CAPACITY_KNOWLEDGE == ("observed", "configured_only", "unknown")
    assert contracts.RANK_BASIS == ("suitability_only", "observed_headroom", "bounded_unknown")


def test_witness_disposition_of_covers_all_four_dispositions():
    assert witness_disposition_of(ev("hard", "anything")) == "not_required"
    assert witness_disposition_of(ev("frontier", goal="x\n" + WITNESS)) == "accepted"
    assert witness_disposition_of(ev("frontier", goal="important production refactor")) == "downgraded"
    assert witness_disposition_of(ev("frontier", goal="x", options=lonely_options())) == "insufficient"


def test_preview_composition_from_a_downgraded_decision():
    decision = ev("frontier", goal="important production refactor")
    preview = _sample_preview(
        effective_complexity=decision.task_complexity,
        witness_disposition=witness_disposition_of(decision),
        decision_id="dec-2")
    assert preview.effective_complexity == C2_COMPLEX_BOUNDED
    assert preview.witness_disposition == "downgraded"
    assert preview.authority == PREVIEW_AUTHORITY


def test_preview_round_trip_through_json():
    preview = _sample_preview()
    payload = json.loads(json.dumps(preview.to_dict()))
    assert payload["schema"] == "RoutePreview.v1"
    assert payload["authority"] == "NONE_SOURCE_PREVIEW_ONLY"
    assert payload["production_armed"] is False
    assert RoutePreview.from_dict(payload) == preview


# =============================================================================
# DecisionEvent.v1 — the one shared decision/event (JSONL) schema
# =============================================================================

def _sample_event(**overrides):
    decision = ev("frontier", goal="important production refactor")
    kwargs = dict(
        event_id="evt-1", event_kind="request_classified",
        occurred_at="2026-11-08T12:00:00Z",
        root_run_ref="root-1", immediate_parent_run_ref="parent-7",
        logical_child_key="child-a", preview_id="pv-1", decision_id="dec-1",
        attempt_ref="att-1", fence_counter=3, request_digest="c" * 64,
        task_kind="code", requested_complexity=C3_FRONTIER_JUDGMENT,
        effective_complexity=C2_COMPLEX_BOUNDED, downgraded=True,
        witness_problem=decision.witness_problem, reason=decision.reason,
        witness=decision.witness, routing_decision=decision,
    )
    kwargs.update(overrides)
    return DecisionEvent(**kwargs)


def test_decision_event_carries_all_correlation_identities():
    event = _sample_event()
    assert event.event_id == "evt-1"
    assert (event.root_run_ref, event.immediate_parent_run_ref, event.logical_child_key) == \
        ("root-1", "parent-7", "child-a")
    assert (event.preview_id, event.decision_id, event.attempt_ref) == ("pv-1", "dec-1", "att-1")
    assert event.fence_counter == 3


def test_decision_event_validates_kind_and_fields():
    with pytest.raises(ValueError, match="event_kind"):
        _sample_event(event_kind="child_promoted_itself")
    with pytest.raises(ValueError, match="event_id"):
        _sample_event(event_id="")
    with pytest.raises(ValueError, match="request_digest"):
        _sample_event(request_digest="short")


def test_decision_event_jsonl_round_trip():
    event = _sample_event()
    line = event.to_json_line()
    assert "\n" not in line
    restored = DecisionEvent.from_json_line(line)
    assert restored == event
    assert restored.to_json_line() == line


# =============================================================================
# RoutingDecision plugin-era alias compatibility
# =============================================================================

def test_routing_decision_from_dict_accepts_plugin_era_aliases():
    payload = {"requested": "frontier", "resolved": "hard", "task_class": "C2",
               "downgraded": True,
               "witness_problem": "no 'witness:' line in the task",
               "reason": "downgraded frontier->hard: no 'witness:' line in the task",
               "witness": "", "policy_version": "1.0.0"}
    decision = RoutingDecision.from_dict(payload)
    assert decision.task_complexity == C2_COMPLEX_BOUNDED
    assert decision.policy_revision == POLICY_REVISION
    with pytest.raises(ValueError, match="disagree"):
        RoutingDecision.from_dict(dict(payload, task_complexity=C3_FRONTIER_JUDGMENT))


def test_routing_decision_round_trip_through_json():
    decision = ev("hard", goal="debug the pool")
    restored = RoutingDecision.from_dict(json.loads(json.dumps(decision.to_dict())))
    assert restored == decision


# =============================================================================
# PARITY: the live Hermes mmx-router plugin vs this repo port, all 23 cases
# =============================================================================

_DEFAULT_HERMES_POLICY_PATH = Path(
    "/Users/chriswong/.hermes/profiles/engineering/plugins/mmx-router/child_routing_policy.py")


@pytest.fixture(scope="session")
def hermes_policy_module():
    path = Path(os.environ.get("MMX_ROUTER_POLICY_PATH", str(_DEFAULT_HERMES_POLICY_PATH)))
    if not path.is_file():
        pytest.skip(f"Hermes mmx-router policy module not found at {path}")
    spec = importlib.util.spec_from_file_location(
        "hermes_child_routing_policy_parity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses needs cls.__module__ resolvable
    spec.loader.exec_module(module)
    return module


#: The 20 evaluate-based cases (plugin cases 1–20; 12–15 share one shape).
PARITY_CASES = [
    pytest.param("frontier", "", "witness: this is a very urgent and important large production task",
                 None, 24, id="p01-all-inflation-rejected"),
    pytest.param("frontier", "", "witness: " + "y" * 12, None, 24, id="p02-short-witness-12"),
    pytest.param("frontier", "", "witness: " + "z" * 23, None, 24, id="p03-boundary-23-chars"),
    pytest.param("frontier", "", "witness: " + "ab" * 12, None, 24, id="p04-24-char-concrete-accepted"),
    pytest.param("frontier", "redesign the fabric pool scheduler", WITNESS, None, 24,
                 id="p05-witness-in-context"),
    pytest.param("frontier", "the task said witness: concrete evidence naming the unresolved tradeoff here",
                 "", None, 24, id="p06-mid-line-not-matched"),
    pytest.param("frontier", "refactor the routing audit tables", WITNESS + "\nextra line",
                 None, 24, id="p07-newline-join-context-leading"),
    pytest.param("frontier", "refactor the routing audit tables\n" + WITNESS, "more context text",
                 None, 24, id="p08-witness-end-of-goal"),
    pytest.param("frontier", "important production refactor", "", None, 24,
                 id="p09-no-witness-downgrades"),
    pytest.param("frontier", "", "witness: frontier quota is unused", None, 24,
                 id="p10-bare-inflation-phrase"),
    pytest.param("frontier", "x", "", "lonely", 24, id="p11-no-lawful-target-refused"),
    pytest.param("mechanical", "anything important production urgent", "", None, 24,
                 id="p12-mechanical-no-witness"),
    pytest.param("routine", "anything important production urgent", "", None, 24,
                 id="p13-routine-no-witness"),
    pytest.param("hard", "anything important production urgent", "", None, 24,
                 id="p14-hard-no-witness"),
    pytest.param("review", "anything important production urgent", "", None, 24,
                 id="p15-review-no-witness"),
    pytest.param("frontier", "x\n" + WITNESS, "", None, 24, id="p16-decision-not-placement"),
    pytest.param("opus", "x", "", None, 24, id="p17-unknown-option-refused"),
    pytest.param("hard", "debug the pool", "", None, 24, id="p18-task-class-and-revision"),
    pytest.param("frontier", "", "witness: " + "ab" * 12, None, 40, id="p19-min-chars-override"),
    pytest.param("frontier", "- witness: multi-file race with two conflicting owners over shared cache",
                 "", None, 24, id="p20-bullet-prefixed-witness"),
]


@pytest.mark.parametrize("requested,goal,context,options_key,min_chars", PARITY_CASES)
def test_parity_hermes_plugin_identical_decisions(
        requested, goal, context, options_key, min_chars, hermes_policy_module):
    """Cases 1–20: same inputs (the plugin-shaped options dict, verbatim) into
    BOTH implementations -> identical resolved class, downgrade flag,
    witness problem, reason, and canonical class."""
    options = lonely_hermes_options() if options_key == "lonely" else HERMES_OPTIONS
    hermes = hermes_policy_module.ChildRoutingPolicy(min_chars).evaluate(
        requested, goal, context, options)
    port = ChildRoutingPolicy(min_chars).evaluate(requested, goal, context, options)
    assert hermes.resolved == port.resolved
    assert hermes.downgraded == port.downgraded
    assert hermes.witness_problem == port.witness_problem
    assert hermes.reason == port.reason
    assert canonical_task_complexity(hermes.task_class) == port.task_complexity


def test_parity_word_lists_verbatim(hermes_policy_module):
    """Cases 21–22: the inflation/glue vocabularies are ported verbatim."""
    assert hermes_policy_module.NOT_WITNESSES == contracts.NOT_WITNESSES
    assert hermes_policy_module._INFLATION_WORDS == contracts._INFLATION_WORDS
    assert hermes_policy_module._GLUE_WORDS == contracts._GLUE_WORDS


def test_parity_options_never_mutated_on_either_side(hermes_policy_module):
    """Case 23: neither implementation mutates the caller's options dict."""
    options = {name: dict(entry) for name, entry in HERMES_OPTIONS.items()}
    snapshot = repr(options)
    hermes_policy_module.ChildRoutingPolicy().evaluate(
        "frontier", "x", "witness: " + "q" * 30, options)
    ChildRoutingPolicy().evaluate("frontier", "x", "witness: " + "q" * 30, options)
    assert repr(options) == snapshot


def test_parity_policy_revision_and_witness_floor_agree(hermes_policy_module):
    assert hermes_policy_module.POLICY_VERSION == POLICY_REVISION
    assert hermes_policy_module.DEFAULT_WITNESS_MIN == contracts.DEFAULT_WITNESS_MIN


def test_parity_witness_helpers_identical(hermes_policy_module):
    for text in ("", "witness: x", "goal text\nwitness: " + "ab" * 12,
                 "no witness here at all", "- witness: indented content"):
        assert hermes_policy_module.find_witness(text) == contracts.find_witness(text)
    for witness, minimum in (("", 24), ("short", 24), ("w" * 24, 24),
                             ("important production task", 24),
                             ("concrete multi-file race evidence", 24),
                             ("frontier quota is unused", 24)):
        assert (hermes_policy_module.witness_problems(witness, minimum)
                == contracts.witness_problems(witness, minimum))
