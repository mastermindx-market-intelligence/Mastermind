from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-08-31-agent-operator-capability-convergence-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-08-31-agent-operator-capability-pack-attestation.md"
AMENDMENT = ROOT / "docs/superpowers/specs/2026-09-01-agent-operator-capability-convergence-owner-amendment.md"


def _read(path: Path) -> str:
    payload = path.read_bytes()
    assert payload
    assert b"\x00" not in payload
    assert payload.endswith(b"\n")
    return payload.decode("utf-8")


def test_records_are_present_and_explicitly_production_inert() -> None:
    texts = [_read(path) for path in (SPEC, PLAN, AMENDMENT)]
    for text in texts:
        assert "PRODUCTION INERT" in text
        assert "Executive OS" in text
        assert "ExecutionCapabilityRegistry" in text
        assert "EFFECT_UNKNOWN" in text
        assert "TODO" not in text
        assert "TBD" not in text


def test_amendment_has_narrow_precedence_over_the_original_records() -> None:
    amendment = _read(AMENDMENT)
    assert "where it conflicts, supersedes" in amendment
    assert SPEC.name in amendment
    assert PLAN.name in amendment
    assert "The original product outcome" in amendment
    assert "This amendment" in amendment


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

    assert "`CAP-S1` does **not** require HF1" in amendment
    assert "Provider-neutral materialization and any non-Codex parity still require HF1" in amendment
    assert "rather than merging an unused digest library alone" in amendment

    assert "CapabilityIdentity.skill_content_digest" in plan
    assert "ObservedCapabilityIdentity.skill_content_digest" in plan
    assert "same skill name + changed SKILL.md -> REFUSE" in plan
    assert "No `grok_broker`" in plan
    assert "Do not create `claude_broker.py`" in plan


def test_practice_and_execution_capability_identity_remain_distinct() -> None:
    amendment = _read(AMENDMENT)
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
    amendment = _read(AMENDMENT)
    assert "It does not make any package generation attested" in amendment
    assert "custom Skill digest enforced" in amendment
    assert "provider materializer built" in amendment
    assert "browser available" in amendment
    assert "non-Codex worker routable" in amendment
    assert "practice adapter live" in amendment
