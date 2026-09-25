"""Static source contracts for Paper design carrier discovery and fallback.

These tests prove procedural/source alignment only. They do not prove live Paper,
Studio Direct publication, Desktop Commander connectivity, or visual acceptance.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/sol_skills/INDEX.md"
SKILL = ROOT / "skills/paper-design-workflow/SKILL.md"
CONNECTION = ROOT / "skills/paper-design-workflow/references/connection.md"
INTEGRATION = ROOT / "docs/PAPER_DESIGN_INTEGRATION.md"


def norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_index_mandates_same_pin_paper_domain_skill():
    text = norm(INDEX)
    assert "skills/paper-design-workflow/SKILL.md" in text
    assert "Mandatory domain companion" in text
    assert "same pinned repository commit" in text
    assert "generic Studio filesystem/process tools do not prove Paper unavailable" in text
    assert "Remote Desktop Commander" in text


def test_skill_discovers_exact_paper_family_before_negative_claim():
    text = norm(SKILL)
    for phrase in (
        "Select the Paper carrier before declaring a blocker",
        "paper_inspect",
        "paper_catalog",
        "paper_read",
        "paper_edit",
        "generic Studio `read_file` / `start_process` actions says nothing",
        "absence alone does not make Paper unavailable",
        "Desktop Commander is a real guarded-bridge fallback",
    ):
        assert phrase in text


def test_fallback_uses_current_protected_runtime_pin_not_folder_guessing():
    text = norm(CONNECTION)
    for phrase in (
        "integrations/studio_direct_mcp/private_service.py",
        "PAPER_RUNTIME_REL",
        "PAPER_RUNTIME_SCHEMA",
        "PAPER_BRIDGE_SHA256",
        "Never choose a runtime by directory recency",
        "RUNTIME.json",
        "source/bridge.py",
        "python_source",
        "run the bridge",
    ):
        assert phrase in text


def test_cross_carrier_write_failover_is_forbidden():
    skill = norm(SKILL)
    connection = norm(CONNECTION)
    for phrase in (
        "explicit safety, permission",
        "Once a Paper edit is dispatched",
        "EFFECT_UNKNOWN",
        "never replay",
    ):
        assert phrase in skill
    for phrase in (
        "pre-dispatch technical absence",
        "explicit safety/permission denial never does",
        "logical mutation remains on that carrier",
        "do not replay through Desktop Commander",
    ):
        assert phrase in connection


def test_preview_artifact_cannot_substitute_for_unprobed_paper_effect():
    skill = norm(SKILL)
    integration = norm(INTEGRATION)
    assert "standalone HTML preview" in skill
    assert "not completion" in skill
    assert "NOT_APPLIED_TO_PAPER" in skill
    assert "cannot replace the required Paper effect" in integration
    assert "while either lawful Paper route remains unprobed" in integration


def test_integration_declares_one_adapter_two_clients_not_two_gateways():
    text = norm(INTEGRATION)
    assert "same guarded bridge" in text
    assert "bounded fallback" in text
    assert "not a second gateway, auth plane, or write authority" in text
    assert "publication/surface drift" in text
