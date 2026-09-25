"""Static source contracts for Paper design carrier discovery and fallback.

These tests prove procedural/source alignment only. They do not prove live Paper,
Studio Direct publication, Desktop Commander connectivity, or visual acceptance.
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/sol_skills/INDEX.md"
SKILL = ROOT / "skills/paper-design-workflow/SKILL.md"
CONNECTION = ROOT / "skills/paper-design-workflow/references/connection.md"
INTEGRATION = ROOT / "docs/PAPER_DESIGN_INTEGRATION.md"
PRIVATE_SERVICE = ROOT / "integrations/studio_direct_mcp/private_service.py"


def norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_index_mandates_same_pin_paper_domain_skill():
    text = norm(INDEX)
    assert "skills/paper-design-workflow/SKILL.md" in text
    assert "Mandatory domain companion" in text
    assert "same pinned repository commit" in text
    assert "generic Studio filesystem/process tools do not prove Paper unavailable" in text
    assert "Remote Desktop Commander" in text
    assert "Studio Direct absence or degradation grants **no** Desktop Commander authority" in text
    assert "independently authorizes that exact host carrier" in text


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
        "Desktop Commander is a real guarded-bridge alternative, never authority by fallback",
        "INDEPENDENT_RDC_AUTHORIZATION",
        "Tool absence is not proof that a denied permission may be recovered elsewhere",
    ):
        assert phrase in text


def test_fallback_uses_current_protected_runtime_pin_not_folder_guessing():
    text = norm(CONNECTION)
    source = PRIVATE_SERVICE.read_text(encoding="utf-8")
    for phrase in (
        "integrations/studio_direct_mcp/private_service.py",
        "_verify_paper_runtime()",
        "PAPER_RUNTIME_REL",
        "PAPER_RUNTIME_SCHEMA",
        "PAPER_BRIDGE_SHA256",
        "Never choose a runtime by directory recency",
        "schema == PAPER_RUNTIME_SCHEMA",
        "generation == Path(PAPER_RUNTIME_REL).name",
        'source_sha256 == {"bridge.py": PAPER_BRIDGE_SHA256}',
        "network_install_performed is false",
        "production_acceptance is false",
        "RUNTIME/venv/bin/python",
        "python_source",
        "staging provenance only",
    ):
        assert phrase in text
    for name in ("PAPER_RUNTIME_REL", "PAPER_RUNTIME_SCHEMA", "PAPER_BRIDGE_SHA256", "_verify_paper_runtime"):
        assert name in source


def test_carrier_decision_matrix_blocks_permission_bypass_and_unknown_effect():
    raw = CONNECTION.read_text(encoding="utf-8")
    block = raw.split("<!-- PAPER_CARRIER_DECISION_V1_START -->", 1)[1].split(
        "<!-- PAPER_CARRIER_DECISION_V1_END -->", 1
    )[0]
    payload = re.search(r"```json\s*(\{.*\})\s*```", block, re.S)
    assert payload, "missing machine-readable carrier decision matrix"
    policy = json.loads(payload.group(1))
    assert policy["schema"] == "mastermind.paper_carrier_decision.v1"
    cases = {
        (row["studio_state"], row["rdc_independently_authorized"], row["effect_state"]): row["decision"]
        for row in policy["cases"]
    }
    assert cases[("PAPER_ACTION_AVAILABLE", False, "NONE")] == "USE_STUDIO"
    assert cases[("ACTION_ABSENT_OR_UNSERVICEABLE", True, "NONE")] == "RDC_ELIGIBLE_PRE_EFFECT"
    assert cases[("ACTION_ABSENT_OR_UNSERVICEABLE", False, "NONE")] == "BLOCK_EXACT_CARRIER_GATE"
    assert cases[("EXPLICIT_DENIAL", True, "NONE")] == "BLOCK_NO_FALLBACK"
    assert cases[("ANY", True, "EFFECT_UNKNOWN")] == "BLOCK_RECONCILE_ORIGINAL_CARRIER"


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
        "Technical absence does not grant that authorization",
        "explicit safety/permission denial",
        "logical mutation remains on that carrier",
        "do not replay through Desktop Commander",
    ):
        assert phrase in connection
    assert "current live Chairman intent/delegated authority or accepted canonical placement" in connection
    assert "Studio Direct absence never grants authority" in connection


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
    assert "direct-host client of the **same guarded bridge**" in text
    assert "Studio Direct absence grants it no authority" in text
    assert "not a second gateway, auth plane, write authority, or permission fallback" in text
    assert "publication/surface drift" in text
