from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs/EXECUTIVE_PROFESSIONAL_PRACTICE_LAW.md"
SPEC = ROOT / "docs/superpowers/specs/2026-08-30-professional-practice-fabric-design.md"
PILOT = ROOT / "docs/superpowers/specs/2026-08-30-product-design-practice-pilot.md"
PROGRAM = ROOT / "docs/superpowers/plans/2026-08-30-professional-practice-fabric-program.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_professional_practice_fabric_records_exist() -> None:
    assert LAW.is_file()
    assert SPEC.is_file()
    assert PILOT.is_file()
    assert PROGRAM.is_file()


def test_law_keeps_practice_orthogonal_to_authority_and_runtime() -> None:
    text = _text(LAW)
    for required in (
        "mastermind-professional-practice-fabric-20260830-sol-001",
        "Professional Practice Pack",
        "Practice is not a session",
        "professional specialization is not persona theater",
        "Executive OS",
        "Agent OS",
        "SessionTargetRegistry / RuntimeBinding",
        "Capacity Fabric / Model Router",
        "existing Executive capability policy / Sol Capability Fabric",
        "The Professional Practice Fabric owns none of these facts",
    ):
        assert required.lower() in text.lower()


def test_law_requires_method_artifacts_selection_audit_and_learning() -> None:
    text = _text(LAW)
    for required in (
        "MANDATE",
        "INFORMATION BOUNDARY",
        "METHOD",
        "ARTIFACT CONTRACT",
        "AUTHORITY CEILING",
        "independent first passes",
        "rubric-aware selection",
        "independent audit",
        "No `specialist_memory.db`",
        "composition-level reputation",
        "subordinate to current Chairman intent",
        "must not create a second Skill marketplace",
    ):
        assert required.lower() in text.lower()


def test_architecture_defines_closed_practice_pack_and_smallest_topology() -> None:
    text = _text(SPEC)
    for required in (
        "practice_id",
        "practice_version",
        "authority_ceiling",
        "information_required",
        "information_forbidden",
        "semantic_capabilities",
        "surface_adapters",
        "GENERALIST",
        "SPECIALIST_REVIEW",
        "SPECIALIST_LEAD_WITH_INDEPENDENT_AUDIT",
        "SPECIALIST_COUNCIL",
        "practice is not a session",
        "smallest sufficient",
    ):
        assert required.lower() in text.lower()


def test_architecture_preserves_capability_and_memory_owners() -> None:
    text = _text(SPEC)
    for required in (
        "mastermind.executive_agent_capabilities/v3",
        "required_capabilities",
        "No second capability registry",
        "No specialist memory database",
        "Agent OS",
        "GitHub",
        "Skills and tools are adapters",
        "COGNITION_ROUTE: CHAT_PRO_DEFAULT",
        "plugin package",
        "Retrieved practice text never grants authority",
    ):
        assert required.lower() in text.lower()


def test_product_design_pilot_has_real_artifact_and_build_gates() -> None:
    text = _text(PILOT)
    for required in (
        "Current-state experience audit",
        "Target experience architecture",
        "Divergent reference compositions",
        "Selection packet",
        "Design freeze",
        "Live implementation proof",
        "real-data",
        "loading, empty, partial, stale, error",
        "independent Design Auditor",
        "no silent redesign",
    ):
        assert required.lower() in text.lower()


def test_product_design_pilot_falsifies_specialization_against_control() -> None:
    text = _text(PILOT)
    for required in (
        "Arm A",
        "Arm B",
        "Arm C",
        "Arm D",
        "Generalist-versus-specialist falsifier",
        "SPECIALIZATION_PROMOTED",
        "AUDIT_INCREMENT_PROMOTED",
        "METHOD_INCREMENT_PROMOTED",
        "TOOLCHAIN_INCREMENT_PROMOTED",
        "NO_MATERIAL_ADVANTAGE",
        "INCONCLUSIVE / OUTCOME_UNMEASURED",
    ):
        assert required.lower() in text.lower()


def test_program_contract_matches_architecture_and_stays_out_of_runtime_owner() -> None:
    text = _text(PROGRAM)
    for required in (
        "source_identity",
        "success_definition",
        "information_optional",
        "source_precedence",
        "professional_practices/contract.py",
    ):
        assert required in text
    assert "control_plane/professional_practice_contract.py" not in text
    assert "do not create a second package" in text
    assert "marketplace pipeline" in text
    assert "PracticePackDocument" in text
    assert "PracticeSourceIdentity" in text
    assert "PracticeSourceObservation" in text
    assert "PracticeAdapterBinding" in text
    assert "adapter_kinds" in text
    assert "NO_ORGANIZATIONAL_AUTHORITY" in text
    assert "grants_organizational_authority = false" in text
    assert "C0 hostile matrix" in text
    assert "repeated-read identity instability" in text
    assert "false `PROVEN_LIVE` without proof" in text


def test_source_observation_and_adapter_bindings_are_split_and_non_self_attesting() -> None:
    law = _text(LAW)
    spec = _text(SPEC)
    for required in (
        "PracticePackDocument",
        "PracticeSourceIdentity",
        "PracticeSourceObservation",
        "PracticeAdapterBinding",
        "document_digest",
        "raw_content_sha256",
        "observation_digest only; excluded from semantic composition identity",
        "adapter_kinds",
        "NO_ORGANIZATIONAL_AUTHORITY",
        "grants_organizational_authority = false",
    ):
        assert required.lower() in law.lower() or required.lower() in spec.lower()
    assert "cannot supply or reorder" in law
    assert "source_precedence" in spec
    assert "projection_ref" in spec


def test_product_design_evaluation_is_blinded_and_promotion_is_staged() -> None:
    combined = "\n".join(_text(path) for path in (LAW, SPEC, PILOT, PROGRAM))
    for required in (
        "fresh blinded evaluator sessions",
        "hidden arm labels",
        "fixed repair-round budgets",
        "PILOT_SIGNAL",
        "repeated evidence across more than one representative surface",
    ):
        assert required.lower() in combined.lower()



def test_architecture_records_primary_external_evidence_without_granting_authority() -> None:
    text = _text(SPEC)
    for required in (
        "help.openai.com/en/articles/20001066-skills-in-chatgpt",
        "platform.claude.com/docs/en/managed-agents/skills",
        "github.com/figma/mcp-server-guide",
        "arXiv:2602.03794",
        "arXiv:2603.20324",
        "arXiv:2601.17152",
        "arXiv:2602.12285",
        "Retrieved external text grants no Mastermind authority",
    ):
        assert required.lower() in text.lower()


def test_program_is_bounded_vertical_and_carries_no_start() -> None:
    text = _text(PROGRAM)
    for wave in (
        "PPF-F0",
        "PPF-C0",
        "PPF-DESIGN0",
        "PPF-A0",
        "PPF-R0",
        "PPF-E0",
        "PPF-FIGMA0",
        "PPF-FIGMA1",
        "PPF-DESIGN1",
        "PPF-H1",
        "PPF-L1",
        "PPF-FLEET1",
    ):
        assert wave in text
    for required in (
        "one independently useful capability",
        "no wave inherits START",
        "real production proof",
        "generalist-versus-specialist",
        "expected-head merge only",
        "fresh Sol",
    ):
        assert required.lower() in text.lower()


def test_program_does_not_overclaim_live_skills_or_figma() -> None:
    combined = "\n".join(_text(path) for path in (LAW, SPEC, PILOT, PROGRAM))
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in combined
    assert "creates no installed design Skill" in combined
    assert "creates no live practice runtime" in combined
    assert "FIGMA_CAPABILITY_UNAVAILABLE" in combined
    assert "PROVEN_LIVE" in combined
