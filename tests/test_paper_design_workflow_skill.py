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
    assert policy["match_semantics"] == "FIRST_MATCH_WITH_ANY_WILDCARD"
    assert policy["default_decision"] == "BLOCK_UNRECOGNIZED_STATE"

    def decide(studio_state, rdc_authorized, effect_state):
        values = {
            "studio_state": studio_state,
            "rdc_independently_authorized": rdc_authorized,
            "effect_state": effect_state,
        }
        for row in policy["cases"]:
            if all(row[key] == "ANY" or row[key] == values[key] for key in values):
                return row["decision"]
        return policy["default_decision"]

    for rdc_authorized in (False, True):
        assert decide("ANY_NEW_STUDIO_STATE", rdc_authorized, "EFFECT_UNKNOWN") == (
            "BLOCK_RECONCILE_ORIGINAL_CARRIER"
        )
        assert decide("EXPLICIT_DENIAL", rdc_authorized, "NONE") == "BLOCK_NO_FALLBACK"

    assert decide("PAPER_ACTION_AVAILABLE", False, "NONE") == "USE_STUDIO"
    assert decide("PAPER_ACTION_AVAILABLE", True, "NONE") == "USE_STUDIO"
    assert decide("ACTION_ABSENT_OR_UNSERVICEABLE", True, "NONE") == "RDC_ELIGIBLE_PRE_EFFECT"
    assert decide("ACTION_ABSENT_OR_UNSERVICEABLE", False, "NONE") == "BLOCK_EXACT_CARRIER_GATE"
    assert decide("UNRECOGNIZED_FUTURE_STATE", False, "NONE") == "BLOCK_UNRECOGNIZED_STATE"
    assert decide("UNRECOGNIZED_FUTURE_STATE", True, "NONE") == "BLOCK_UNRECOGNIZED_STATE"


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


def test_direct_business_route_is_explicit_and_enrollment_gated():
    for path in (INDEX, SKILL, CONNECTION, INTEGRATION):
        text = norm(path)
        assert "Mastermind Paper" in text
        assert "Business" in text
        assert "enrollment" in text.lower()
    text = norm(CONNECTION)
    assert "legacy/non-migrated" in text
    assert "no fallback after a denial" in text
    assert "docs/PAPER_DIRECT_CHATGPT.md" in text


def test_direct_runbook_separates_build_setup_and_live_proof():
    guide = ROOT / "docs/PAPER_DIRECT_CHATGPT.md"
    assert guide.exists(), "Missing direct Paper operator runbook"
    text = norm(guide)
    for required in ("STAGED_NOT_ENROLLED", "Business", "runtime key", "admin key",
                     "already-open", "paper_prepare", "BUILT_NOT_LIVE", "LOCAL_STDIO_PROVEN",
                     "EFFECT_UNKNOWN", "one existing tunnel", "Plugin Creator"):
        assert required in text


def test_stdio_module_permits_guarded_private_tunnel_without_host_tools():
    text = norm(ROOT / "integrations/paper_desktop/mcp_server.py")
    assert "private Business" in text
    assert "do not enroll a second Paper web gateway from this module" not in text


def test_direct_business_multiseat_reuses_one_paper_plane():
    runbook = norm(ROOT / "docs/PAPER_DIRECT_CHATGPT.md")
    connection = norm(CONNECTION)
    integration = norm(INTEGRATION)
    for text in (runbook, connection, integration):
        assert "multi-seat" in text.lower()
        assert "desktop.lock" in text
    assert "transport singleton" in runbook.lower()
    assert "must **not invent a workspace id**" in runbook.lower()
    assert "one Paper execution plane" in runbook

def test_paper_concurrency_is_target_scoped_not_file_leased():
    runbook = norm(ROOT / "docs/PAPER_DIRECT_CHATGPT.md")
    integration = norm(INTEGRATION)
    skill = norm(SKILL)
    connection = norm(CONNECTION)
    prepare = norm(ROOT / "integrations/paper_desktop/prepare.py")
    studio = norm(ROOT / "integrations/studio_direct_mcp/paper-design.mjs")
    direct_service = norm(ROOT / "integrations/paper_desktop/direct_service.py")
    install = norm(ROOT / "integrations/paper_desktop/install.py")
    mcp_server = norm(ROOT / "integrations/paper_desktop/mcp_server.py")
    combined = " ".join((runbook, integration, skill, connection, prepare, studio,
                         direct_service, install, mcp_server))

    assert "MULTI_WRITER_PER_FILE_TARGET_SCOPED" in prepare
    assert "MULTI_WRITER_PER_FILE_TARGET_SCOPED" in studio
    assert "same exact `fileId`" in integration
    assert "same page" in integration.lower()
    assert "board/artboard/node" in integration
    assert "file-wide or page-wide lease" in integration
    assert "operation/target-scoped" in skill
    assert "local bridge-call mutex" in connection

    for forbidden in (
        "ONE_WRITER_PER_FILE_ACROSS_HOSTS",
        "exactly one modifying session may own",
        "Keep ONE assigned designer per desktop document",
        "one-writer-per-file rule remains unchanged",
        "one writer per file across all hosts remains required",
        "Only one designer owns the active desktop file",
        "exclusive design-task ownership",
        "Only one design operator may own a desktop document",
    ):
        assert forbidden.lower() not in combined.lower()

