from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-08-31-agent-operator-capability-convergence-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-08-31-agent-operator-capability-pack-attestation.md"
AMENDMENT = ROOT / "docs/superpowers/specs/2026-09-01-agent-operator-capability-convergence-owner-amendment.md"
CLOSURE = ROOT / "docs/superpowers/specs/2026-09-01-agent-operator-effective-skill-closure-amendment.md"
EXPOSURE = ROOT / "docs/superpowers/specs/2026-09-01-agent-operator-skill-set-exposure-amendment.md"
OPERATOR_SKILLS = {
    name: ROOT / f"plugins/mastermind-operator/skills/{name}/SKILL.md"
    for name in (
        "escalate-decision",
        "finish-operation",
        "receive-commission",
        "return-progress",
    )
}
DIALOGUE_REFERENCE = ROOT / "plugins/mastermind-operator/references/dialogue-boundary.md"


def _read(path: Path) -> str:
    payload = path.read_bytes()
    assert payload
    assert b"\x00" not in payload
    assert payload.endswith(b"\n")
    return payload.decode("utf-8")


def _prose(path: Path) -> str:
    """Normalize Markdown wrapping without weakening exact semantic phrases."""

    return " ".join(_read(path).split())


def test_records_are_present_and_explicitly_production_inert() -> None:
    records = {path: _read(path) for path in (SPEC, PLAN, AMENDMENT)}
    for text in records.values():
        assert "PRODUCTION INERT" in text
        assert "TODO" not in text
        assert "TBD" not in text

    assert "Executive OS" in records[SPEC]
    assert "ExecutionCapabilityRegistry" in records[AMENDMENT]
    assert "EFFECT_UNKNOWN" in records[PLAN]

    for path in (CLOSURE, EXPOSURE):
        text = _read(path)
        assert "PRODUCTION_INERT" in text
        assert "TODO" not in text
        assert "TBD" not in text

    assert "ExecutionCapabilityRegistry" in _read(CLOSURE)


def test_amendments_have_narrow_precedence_over_the_original_records() -> None:
    amendment = _read(AMENDMENT)
    closure = _read(CLOSURE)
    exposure = _read(EXPOSURE)

    assert "where it conflicts, supersedes" in amendment
    assert SPEC.name in amendment
    assert PLAN.name in amendment
    assert "The original product outcome" in amendment
    assert "This amendment" in amendment

    assert "where it conflicts, supersedes" in closure
    assert SPEC.name in closure
    assert PLAN.name in closure
    assert AMENDMENT.name in closure
    assert "existing-owner ruling" in closure

    assert "where it conflicts, supersedes" in exposure
    for path in (SPEC, PLAN, AMENDMENT, CLOSURE):
        assert path.name in exposure
    assert "All existing-owner" in exposure


def test_existing_capability_and_practice_owners_are_not_duplicated() -> None:
    amendment = _read(AMENDMENT)
    required = (
        "Sol Capability Fabric",
        "Professional Practice Fabric",
        "BSC-P1",
        "BSC-U1",
        "Operator Harness",
        "Worker Browser / DevServer Resource Fabric",
        "Capacity Fabric / Model Router / MH1",
        "Agent OS",
        "GitHub",
    )
    for phrase in required:
        assert phrase in amendment

    assert "#313 is an amendment/substrate, not a new company program" in amendment
    assert "a new Agent OS workstream" in amendment
    assert "a new capability owner" in amendment
    assert "A fresh Sol may retain `CAP-S1`" in amendment


def test_stale_bsc_f2_label_is_not_treated_as_an_executable_carrier() -> None:
    amendment = _read(AMENDMENT)
    assert "There is no current protected/open implementation carrier discovered" in amendment
    assert "is not an executable dependency reference" in amendment
    assert "PACKAGE_GENERATION_OWNER_UNRESOLVED" in amendment
    assert "The exact future wave name is not frozen by #313" in amendment
    assert "current Business Sol / Sol Capability Fabric" in amendment


def test_first_vertical_and_hf1_boundary_are_precise() -> None:
    amendment = _read(AMENDMENT)
    plan = _read(PLAN)
    exposure = _read(EXPOSURE)

    assert "`CAP-S1` does **not** require HF1" in amendment
    assert "Provider-neutral materialization and any non-Codex parity still require HF1" in amendment
    assert "rather than merging an unused digest library alone" in amendment

    assert "CapabilityIdentity.skill_content_digest" in plan
    assert "ObservedCapabilityIdentity.skill_content_digest" in plan
    assert "same skill name + changed SKILL.md -> REFUSE" in plan
    assert "No `grok_broker`" in plan
    assert "Do not create `claude_broker.py`" in plan

    assert "HF1 remains required before heterogeneous providers" in exposure
    assert "first Codex rich-operator proof" in exposure


def test_effective_skill_closure_includes_required_package_reference() -> None:
    closure = _read(CLOSURE)
    closure_prose = _prose(CLOSURE)
    dialogue_reference = _read(DIALOGUE_REFERENCE)

    for skill_path in OPERATOR_SKILLS.values():
        assert "../../references/dialogue-boundary.md" in _read(skill_path)
    assert "Distinct states remain distinct" in dialogue_reference

    assert "mastermind.effective_skill_closure/v1" in closure
    assert '"entrypoint_path": "skills/receive-commission/SKILL.md"' in closure
    assert '"relative_path": "references/dialogue-boundary.md"' in closure
    assert "skills/receive-commission/SKILL.md\nreferences/dialogue-boundary.md" in closure
    assert "effective Skill closure, not merely" in closure_prose
    assert (
        "Skill closure identity and package generation identity are related but not collapsed"
        in closure_prose
    )
    assert "A regex/link crawler cannot prove" in closure_prose
    assert "Name-only observation cannot satisfy a requested digest" in closure_prose
    assert "same name + changed required shared reference" in closure_prose
    assert "same closure + changed unrelated sibling Skill" in closure_prose
    assert "per-Skill effective-closure mapping" in closure_prose


def test_first_codex_profile_requires_the_exact_exposed_four_skill_set() -> None:
    exposure = _read(EXPOSURE)

    for name in OPERATOR_SKILLS:
        assert name in exposure
        assert f"mastermind-operator.{name}.v1" in exposure

    assert "loads and requires the complete four-Skill" in exposure
    assert "operator.appserver.readonly.mastermind-operator.v1" in exposure
    assert "one requested typed identity" in exposure
    assert "exactly one observed typed identity" in exposure
    assert "multiple same-name observations, even when one matches" in exposure
    assert "unexpected fifth custom Skill" in exposure
    assert "skills/extraRoots/set" in exposure
    assert "plugins/mastermind-operator/skills" in exposure
    assert "one-Skill profile is lawful only" in exposure
    assert "require all four exact `mastermind-operator` effective Skill closures" in exposure


def test_practice_and_execution_capability_identity_remain_distinct() -> None:
    amendment = _prose(AMENDMENT)
    assert "Practice source and executable capability source remain distinct identities" in amendment
    assert "A capability digest proves exact bytes loaded" in amendment
    assert "it does not prove the model applied the professional method correctly" in amendment
    assert "PPF's real evaluation still decides that" in amendment


def test_browser_and_desktop_access_remain_explicit_resources() -> None:
    spec = _read(SPEC)
    amendment = _read(AMENDMENT)
    combined = spec + "\n" + amendment

    assert "Any governed Attempt whose job requires browser proof" in combined
    assert "Browser capability is not ambient desktop authority" in amendment
    assert "Worker Browser B1 remains the local-review owner" in amendment
    assert "Chairman's browser profile" in amendment
    assert "GUI mutex belongs to Worker/resource capacity and MH1" in amendment


def test_records_do_not_claim_runtime_or_product_completion() -> None:
    amendment = _prose(AMENDMENT)
    closure = _prose(CLOSURE)
    exposure = _prose(EXPOSURE)
    assert "It does not make any package generation attested" in amendment
    assert "custom Skill digest enforced" in amendment
    assert "provider materializer built" in amendment
    assert "browser available" in amendment
    assert "non-Codex worker routable" in amendment
    assert "practice adapter live" in amendment
    assert "does not attest a live package generation" in closure
    assert "Codex vertical `PROVEN_LIVE`" in closure
    assert "does not load or prove the Skill set" in exposure
