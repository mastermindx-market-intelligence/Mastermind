import json
from pathlib import Path

from integrations.executive_mcp.coo import COO_SERVER_VERSION, COO_TOOL_NAMES


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "integrations" / "claude_executive_plugin"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
SKILL = PLUGIN / "skills" / "executive-orchestration" / "SKILL.md"
COMMAND = PLUGIN / "commands" / "executive-context.md"
README = PLUGIN / "README.md"


EXPECTED_COO_TOOLS = (
    "executive_mandate",
    "executive_state",
    "executive_inbox",
    "executive_fabric",
    "submit_principal_intent",
    "principal_intent_status",
)


def test_manifest_is_minimal_private_executive_plugin():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "name",
        "version",
        "description",
        "author",
        "repository",
        "keywords",
    }
    assert manifest["name"] == "mastermind-executive"
    assert manifest["version"] == "0.2.0"
    assert manifest["author"] == {"name": "MastermindX"}
    assert manifest["repository"] == (
        "https://github.com/mastermindx-market-intelligence/Mastermind"
    )
    assert "mcpServers" not in manifest
    assert "hooks" not in manifest


def test_p2_does_not_create_second_mcp_or_hook_carrier():
    assert not (PLUGIN / ".mcp.json").exists()
    assert not (PLUGIN / "hooks").exists()
    readme = README.read_text(encoding="utf-8")
    assert "without** a plugin-owned `.mcp.json`" in readme
    assert "#955" in readme
    assert "DRAFT/HOLD" in readme
    assert "cannot install, authenticate or select" in readme


def test_package_tracks_exact_current_role_correct_coo_contract():
    assert COO_SERVER_VERSION == "1.0.0"
    assert COO_TOOL_NAMES == EXPECTED_COO_TOOLS
    readme = README.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    command = COMMAND.read_text(encoding="utf-8")
    assert "server version `1.0.0`" in readme
    for tool in EXPECTED_COO_TOOLS:
        assert f"`{tool}`" in readme
        assert f"`{tool}`" in skill or f"`{tool}`" in command
    assert "This package never uses `submit_ceo_intent`." in readme
    assert "Never call `submit_ceo_intent` from the COO seat." in skill
    assert "fall back to CEO mutation" in command


def test_skill_preserves_broad_coo_judgment_without_ambient_authority():
    text = SKILL.read_text(encoding="utf-8")
    assert "broad delegated COO principal" in text
    assert "Organizational\njudgment and technical authority remain separate" in text
    assert "Do not ask Sol/Chairman to choose among ordinary reversible" in text
    assert "A blocker freezes its lane first, not the entire mission." in text
    assert "source release, merge or deployment" in text


def test_skill_has_exact_bounded_action_and_reconciliation_sequence():
    text = SKILL.read_text(encoding="utf-8")
    assert "`executive_mandate` permits a new COO effect" in text
    assert "the COO owns the applicable turn" in text
    assert "stable operation key" in text
    assert "contains no provider/account/host/Worker/session selection" in text
    assert "accepted receipt proves request admission, not Worker START" in text
    assert "do not\n  submit again" in text
    assert "`principal_intent_status` with the original `request_ref`" in text
    assert "does not create an H4 governed orchestration root" in text


def test_context_command_is_read_only_and_effect_honest():
    text = COMMAND.read_text(encoding="utf-8")
    assert "mastermind-executive" in text
    assert "`executive_mandate`" in text
    assert "`executive_state`" in text
    assert "`executive_inbox`" in text
    assert "`executive_fabric`" in text
    assert "`principal_intent_status` only when reconciling" in text
    assert "must not call `submit_principal_intent`" in text
    assert "admission is not START" in text
    assert "delivery is not ACK" in text
    assert "CI is not acceptance" in text
    assert "fall back to CEO mutation" in text


def test_plugin_contains_no_secret_or_client_registration_material():
    texts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (MANIFEST, SKILL, COMMAND, README)
    ).lower()
    for forbidden in (
        "sk-ant-",
        "bearer eyj",
        "refresh_token",
        "client_secret",
        "api_key=",
        "auth_token=",
    ):
        assert forbidden not in texts
    assert "public_auth0_client_id" not in texts
    assert "8774" not in texts


def test_readme_keeps_install_auth_and_surface_proofs_separate():
    text = README.read_text(encoding="utf-8")
    assert "source package\ntherefore cannot install, authenticate or select" in text
    assert "Claude Desktop Executive connector availability remains **UNPROVEN**" in text
    assert "one surface's success is not inherited by another" in text
    assert "plugin installation on any Claude surface" in text
    assert "OAuth/client enrollment" in text
    assert "exact native principal/profile admission" in text
    assert "H4 governed fan-out" in text


def test_readme_tracks_current_carriers_without_claiming_their_runtime_acceptance():
    text = README.read_text(encoding="utf-8")
    for dependency in ("#962", "#955", "#676", "#600", "#919", "#992", "#660", "#1236", "#1240"):
        assert dependency in text
    assert "#955" in text and "DRAFT/HOLD" in text
    assert "Historical issue/PR text is evidence, not current runtime authority" in text


def test_plugin_files_never_claim_role_correct_source_as_live_native_authority():
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in (README, SKILL, COMMAND)
    )
    assert "P2 source does **not** prove:" in text
    assert "This source package does not prove:" in text
    assert "cannot install, authenticate or select" in text
    assert "If it is\nmissing, unauthenticated or exposes the wrong schema" in text
    assert "PRODUCTION INERT" in text
