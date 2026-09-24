import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "integrations" / "claude_executive_plugin"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
SKILL = PLUGIN / "skills" / "executive-orchestration" / "SKILL.md"
COMMAND = PLUGIN / "commands" / "executive-context.md"
README = PLUGIN / "README.md"


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
    assert manifest["version"] == "0.1.0"
    assert manifest["author"] == {"name": "MastermindX"}
    assert manifest["repository"] == (
        "https://github.com/mastermindx-market-intelligence/Mastermind"
    )
    assert "mcpServers" not in manifest
    assert "hooks" not in manifest


def test_p1_does_not_create_a_second_mcp_or_hook_carrier():
    assert not (PLUGIN / ".mcp.json").exists()
    assert not (PLUGIN / "hooks").exists()
    readme = README.read_text(encoding="utf-8")
    assert "existing user-scope MCP registration: mastermind-executive" in readme
    assert "plugin-owned" in readme and ".mcp.json" in readme
    assert "without hooks in P1" in readme
    assert "#955" in readme


def test_skill_preserves_broad_coo_autonomy_without_claiming_technical_authority():
    text = SKILL.read_text(encoding="utf-8")
    assert "broad delegated COO principal" in text
    assert "ordinary reversible judgment belongs to the COO principal" in text
    assert "Do not ask Sol/Chairman to choose among ordinary reversible" in text
    assert "Do not confuse broad organizational judgment with ambient technical authority." in text
    assert "When the canonical mission says the COO owes the turn, decide and continue" in text
    assert "When CEO or Chairman owes the turn, do not answer that seat." in text
    assert "do not micromanage it" in text
    assert "A blocker freezes its lane first, not the entire mission." in text


def test_skill_refuses_legacy_ceo_mutation_from_coo_seat():
    text = SKILL.read_text(encoding="utf-8")
    assert "legacy Executive profile exposes a CEO-specific modifying tool" in text
    assert "do not use it from the COO seat" in text
    assert "role-correct COO action surface is a later gated capability" in text
    assert "submit_ceo_intent" not in text


def test_context_command_is_read_only_and_effect_honest():
    text = COMMAND.read_text(encoding="utf-8")
    assert "mastermind-executive" in text
    assert "read-only Executive/Workspace/Fabric operations" in text
    assert "Do not invoke any CEO-specific modifying operation" in text
    assert "admission is not START" in text
    assert "delivery is not ACK" in text
    assert "CI is not acceptance" in text
    assert "Do not ask for credentials" in text


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


def test_readme_freezes_future_bundle_gates_and_source_dependencies():
    text = README.read_text(encoding="utf-8")
    assert "static COO Executive MCP profile exists" in text
    assert "COO action scope rather than the CEO submit scope" in text
    assert "bundled-plugin OAuth works on the exact deployed Claude Code CLI" in text
    assert "no CEO or ambient modifying surface leaked into the plugin" in text
    for dependency in ("#957", "#960", "#961", "#955", "#676", "#804"):
        assert dependency in text


def test_no_executable_component_claims_current_coo_mutation():
    executable_instructions = (
        SKILL.read_text(encoding="utf-8")
        + "\n"
        + COMMAND.read_text(encoding="utf-8")
    )
    for forbidden in (
        "submit_principal_intent",
        "mastermind.executive.coo.act",
        "AUTONOMOUS_SOURCE_RELEASE_WITH_GATES",
    ):
        assert forbidden not in executable_instructions
