from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs" / "EXECUTIVE_BROWSER_ACTUATION_LAW.md"
DESIGN = ROOT / "docs" / "superpowers" / "specs" / "2026-09-04-web-sol-browser-actuation-fabric-design.md"
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-09-04-web-sol-browser-actuation-fabric.md"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing BRA source record: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_bra_source_records_exist_and_remain_production_inert():
    for path in (LAW, DESIGN, PLAN):
        text = _text(path)
        assert "PRODUCTION_INERT" in text
        assert "WS:CHAIRMAN-CONTROL-ROOM" in text


def test_bra_preserves_canonical_authority_and_no_duplicate_control_plane():
    law = _text(LAW)
    required = (
        "Executive OS owns Job / Attempt / Worker / Event lifecycle",
        "RuntimeBinding / SessionTarget owners determine exact actionable runtime targets",
        "Agent OS owns durable organizational workstreams",
        "Secure MCP Tunnel, when used, is transport only",
        "second lifecycle",
        "browser-session authority",
    )
    for phrase in required:
        assert phrase in law


def test_bra_keeps_chatgpt_semantics_out_of_generic_browser_tools():
    law = _text(LAW)
    assert "mastermind.web_sol_surface_action.v1" in law
    assert "INSPECT | FOREGROUND" in law
    assert "mastermind.browser_actuation.v1" in law
    assert "mastermind.web_sol_semantic_action.v2+" in law
    assert "A generic browser primitive is never authority-equivalent to a semantic Web-Sol action." in law
    assert "Generic browser actuation must not be used to smuggle ChatGPT prompt submission" in law


def test_bra_effect_unknown_is_sticky_and_non_retryable():
    law = _text(LAW)
    assert "EFFECT_UNKNOWN" in law
    assert "blocks blind retry" in law
    assert "blocks target/session/account failover" in law
    assert "permits read-only reconciliation only" in law


def test_bra_refuses_ui_heuristic_target_selection():
    law = _text(LAW)
    for phrase in (
        "newest or most recently active tab",
        "browser/window order",
        "title similarity",
        "visible model output",
        "model-selected account/profile/project",
    ):
        assert phrase in law


def test_bra_secret_boundary_forbids_browser_credential_extraction():
    law = _text(LAW)
    for phrase in (
        "cookies or storage values",
        "auth/session/OAuth tokens",
        "password-manager values",
        "raw browser profile contents",
        "private provider network payloads",
        "bulk ChatGPT transcripts/model outputs",
    ):
        assert phrase in law


def test_bra_managed_chairman_seats_remain_p0b_gated():
    law = _text(LAW)
    plan = _text(PLAN)
    assert "CHAIRMAN_MANAGED_BROWSER_SEAT" in law
    assert "existing P0B/MAS-115 program independently proves" in law
    assert "BRA-M1" in plan
    assert "P0B must first establish" in plan


def test_bra_remote_transport_is_not_runtime_identity():
    law = _text(LAW)
    design = _text(DESIGN)
    assert "Tunnel identity" in law
    assert "must never elect or replace RuntimeBinding" in law
    assert "Correlation IDs may appear in diagnostic receipts as transport evidence but never as company identity." in design


def test_bra_first_modifying_proof_is_disposable_not_chairman_chatgpt():
    plan = _text(PLAN)
    assert "BRA-A1" in plan
    assert "exact disposable browser" in plan
    assert "No Chairman seat. No ChatGPT prompt submission." in plan


def test_bra_records_reject_super_mcp_and_remote_desktop_rebuild():
    design = _text(DESIGN)
    assert "Mastermind-hosted generic remote-desktop relay" in design
    assert "central browser-session database" in design
    assert "super-MCP combining Executive, browser, filesystem and shell powers" in design
    assert "generic `execute_javascript`/raw-CDP model tools" in design
