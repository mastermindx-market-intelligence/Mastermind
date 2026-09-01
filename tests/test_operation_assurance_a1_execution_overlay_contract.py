from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs" / "OPERATION_LIVENESS_SOUNDNESS_LAW.md"
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-liveness-soundness-design.md"
)
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-operation-assurance-core.md"
)
OVERLAY = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-assurance-a1-controlling-execution-overlay.md"
)

CONTROLLING_A1_SOURCES = (
    "docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md",
    "docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md",
    "docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md",
    "docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md",
)


def _raw(path: Path) -> str:
    assert path.is_file(), f"missing OLS source artifact: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _text(path: Path) -> str:
    return " ".join(_raw(path).split())


def test_overlay_closes_the_plan_precedence_gap() -> None:
    text = _text(OVERLAY)
    for marker in (
        "CONTROLLING EXECUTION OVERLAY",
        "mastermind-operation-liveness-soundness-20260830-sol-001",
        "2026-08-30-operation-assurance-core.md",
        "2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md",
        "2026-08-30-operation-assurance-immutable-report-projection-clarification.md",
        "Where this overlay conflicts with the parent law, design, or implementation plan, this overlay wins",
    ):
        assert marker in text


def test_parent_entrypoints_reverse_link_to_controlling_a1_contract_near_top() -> None:
    for path in (LAW, DESIGN, PLAN):
        prefix = " ".join("\n".join(_raw(path).splitlines()[:100]).split())
        assert "CONTROLLING OLS-A1 IMPLEMENTATION NOTICE" in prefix
        positions = []
        for source in CONTROLLING_A1_SOURCES:
            assert source in prefix, f"{path.relative_to(ROOT)} missing {source}"
            positions.append(prefix.index(source))
        assert positions == sorted(positions), (
            f"{path.relative_to(ROOT)} lists controlling A1 sources out of precedence order"
        )
        assert "historical drafting residue" in prefix
        assert "do not implement" in prefix.lower()


def test_a1_model_wire_requires_the_corrected_fidelity_contract() -> None:
    text = _text(OVERLAY)
    for marker in (
        "abstraction_contract is required",
        "DECLARED_EXACT",
        "SOUND_OVERAPPROXIMATION",
        "TRACE_BACKED_UNDERAPPROXIMATION",
        "HEURISTIC_ABSTRACTION",
        "UNKNOWN_FIDELITY",
        "release_transition_ids",
        "owned_persistent_obligation_ids",
        "owned_persistent_resource_ids",
        "affects_property_ids",
        "affects_transition_ids",
        "affects_variable_ids",
    ):
        assert marker in text

    assert "NONE fairness is represented by absence" in text
    assert "STRONG fairness is rejected in OLS-A1" in text


def test_immutable_report_keeps_model_analysis_and_applicability_orthogonal() -> None:
    text = _text(OVERLAY)
    for verdict in (
        "UNSAFE_COUNTEREXAMPLE",
        "PROVEN_WITHIN_FINITE_MODEL",
        "BOUNDED_NO_COUNTEREXAMPLE",
        "INCONCLUSIVE_MODEL_GAP",
    ):
        assert verdict in text

    assert "model_analysis_verdict has exactly four values" in text
    assert "source_applicability_at_generation" in text
    assert "MODEL_STALE_OR_INVALID is a current derived status, not a model-analysis verdict" in text
    assert "current_projection_verdict is withdrawn from the immutable report" in text
    assert "the ambiguous bare source_applicability field is withdrawn" in text


def test_a1_never_claims_current_status_or_operational_proceed() -> None:
    text = _text(OVERLAY)
    assert "OLS-A1 never emits mastermind.operation_assurance_status.v1" in text
    assert "OLS-A1 never emits REPORT_ONLY_PROCEED" in text
    assert "AUTHOR_DECLARED_ONLY" in text
    assert "REPORT_ONLY_NO_RECOMMENDATION" in text
    assert "REPORT_ONLY_RECONCILE" in text


def test_gap_relevance_and_counterexample_realizability_control_certainty() -> None:
    text = _text(OVERLAY)
    for marker in (
        "DECLARED_MODEL_ONLY",
        "SOURCE_CONTRACT_VALIDATED",
        "RUNTIME_REPLAY_CONFIRMED",
        "POTENTIALLY_SPURIOUS",
        "INVALIDATED",
        "trace/property-specific relevance",
        "an unrelated non-load-bearing gap does not hide a definite witness",
        "a relevant load-bearing gap weakens witness certainty",
    ):
        assert marker in text

    assert "telemetry alone cannot create RUNTIME_REPLAY_CONFIRMED" in text


def test_corrected_fixture_expectations_are_frozen() -> None:
    text = _text(OVERLAY)
    for fixture in (
        "safe_finite.json",
        "effect_unknown_failover.json",
        "stale_projection.json",
        "chairman_external_gate.json",
        "capacity_valid_wait.json",
    ):
        assert fixture in text

    assert "PROVEN_WITHIN_FINITE_MODEL + AUTHOR_DECLARED_ONLY + REPORT_ONLY_NO_RECOMMENDATION" in text
    assert "UNSAFE_COUNTEREXAMPLE + DECLARED_MODEL_ONLY + REPORT_ONLY_REPAIR" in text
    assert "preserves the model-analysis result while setting generation-time applicability to STALE or CONFLICTED" in text


def test_overlay_preserves_the_pure_report_only_no_rebuild_boundary() -> None:
    text = _text(OVERLAY)
    assert "standard-library-only" in text
    assert "zero network, socket, subprocess, telemetry, filesystem-write, SQLite, runtime, or source-owner I/O" in text
    assert "No Executive OS, Agent OS, Wake, RuntimeBinding, Capacity, Steward, Control Room, watcher, retry, or Runtime Observability mutation" in text
    assert "all reachable cyclic SCCs" in text
    assert "descriptive gate prose alone never legalizes a dead state" in text


def test_fair_lasso_search_uses_a_closed_walk_product() -> None:
    text = _text(OVERLAY)
    assert "fairness-valid closed walk" in text
    assert "may combine multiple simple cycles" in text
    assert "seen-or-disabled fairness mask" in text
    assert "shortest fair violating lasso" in text


def test_report_identity_is_non_circular_and_deterministic() -> None:
    text = _text(OVERLAY)
    assert "report_hash is computed from the canonical report body excluding report_id and report_hash" in text
    assert "report_id is oar_ plus the first 24 hexadecimal characters of report_hash" in text
    assert "duration_ms is excluded from the OLS-A1 canonical report" in text
    assert "deterministic work counts" in text


def test_structural_refusal_and_semantic_gate_gap_are_distinct() -> None:
    text = _text(OVERLAY)
    assert "a missing required gate field is parser refusal" in text
    assert "a syntactically complete gate without a realizable release or terminal assessment boundary is EXTERNAL_GATE_INCOMPLETE" in text


def test_redundant_assumption_references_must_agree() -> None:
    text = _text(OVERLAY)
    assert "transition fairness_ref and fairness assumption transition_ids must agree exactly" in text
    assert "transition external_assumption_ref and environment assumption transition_ids must agree exactly" in text
    assert "duplicate effects for the same state variable are rejected" in text
