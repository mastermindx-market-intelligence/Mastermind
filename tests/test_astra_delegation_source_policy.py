import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"
ASTRA_PROFILE = ROOT / "ops" / "codex_fabric" / "mastermind-astra.config.toml"
L2_SOL_PROFILE = ROOT / "ops" / "codex_fabric" / "agents" / "l2-sol-ceo.toml"


def _astra_section() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    marker = "### Astra project-delivery economics"
    assert text.count(marker) == 1
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_astra_is_principal_and_external_fabric_is_default_execution_path():
    section = _astra_section()
    required = (
        "principal, not the default worker",
        "existing five-tool Executive MCP",
        "external Fabric first",
        "final acceptance",
        "l2_sol_ceo",
        "SUSTAINED_ORCHESTRATION",
        "Generic native Codex worker agents remain explicit bounded fallback",
        "GLM or Grok",
        "another Sol/Astra",
        "Luna and Terra are not normal",
    )
    for phrase in required:
        assert phrase in section


def test_astra_policy_preserves_physical_routing_and_effect_boundaries():
    section = _astra_section()
    required = (
        "Capacity chooses provider/account/host placement",
        "never replay full worker transcripts",
        "EFFECT_UNKNOWN",
        "same operation identity",
        "no provider or internal-agent failover",
        "exact current RuntimeBinding",
    )
    for phrase in required:
        assert phrase in section


def test_named_astra_parent_profile_exposes_only_one_native_l2_sol_ceo_lane():
    profile = tomllib.loads(ASTRA_PROFILE.read_text(encoding="utf-8"))
    assert profile["model"] == "gpt-6-astra"
    assert profile["model_reasoning_effort"] == "high"
    agents = profile["agents"]
    assert agents["enabled"] is True
    assert agents["max_concurrent_threads_per_session"] == 1
    assert agents["default_subagent_model"] == "gpt-5.6-sol"
    assert agents["default_subagent_reasoning_effort"] == "high"
    l2 = agents["l2_sol_ceo"]
    assert l2["config_file"] == "agents/l2-sol-ceo.toml"
    assert "sustained orchestration" in l2["description"].lower()
    serialized = ASTRA_PROFILE.read_text(encoding="utf-8")
    assert "gpt-5.6-luna" not in serialized
    assert "gpt-5.6-terra" not in serialized


def test_l2_sol_ceo_is_narrow_nonrecursive_executive_role():
    profile = tomllib.loads(L2_SOL_PROFILE.read_text(encoding="utf-8"))
    assert profile["name"] == "l2_sol_ceo"
    assert profile["model"] == "gpt-5.6-sol"
    assert profile["model_reasoning_effort"] == "high"
    assert profile["agents"]["enabled"] is False
    instructions = profile["developer_instructions"]
    for phrase in (
        "bounded Level-2 executive",
        "External Fabric",
        "SUSTAINED_ORCHESTRATION",
        "Do not perform routine implementation",
        "Do not spawn native child agents",
        "Capacity chooses provider/account/host placement",
    ):
        assert phrase in instructions


def test_repository_codex_config_remains_separate_worker_attestation_layer():
    config = CODEX_CONFIG.read_text(encoding="utf-8")
    assert "enabled = true" in config
    assert "max_concurrent_threads_per_session = 3" in config
    assert 'default_subagent_model = "gpt-5.6-terra"' in config
    assert 'default_subagent_reasoning_effort = "medium"' in config
    assert "gpt-6-astra" not in config


def test_astra_policy_consumes_current_role_adaptive_delegation_contract():
    section = _astra_section()
    required = (
        "docs/sol_skills/ACTIVE_EXECUTION.md",
        "docs/sol_skills/WEB_CEO_DELEGATION.md",
        "CONCENTRATED_JUDGMENT",
        "SUSTAINED_ORCHESTRATION",
        "Either principal may",
        "retain productive work",
        "sole no-delta/finalization owner",
        "never grants",
    )
    for phrase in required:
        assert phrase in section

RUNBOOK = ROOT / "docs" / "runbooks" / "codex-astra-fabric-delegation.md"


def test_astra_policy_names_canonical_external_fabric_delegation_phrase():
    section = _astra_section()
    assert "External Fabric delegation" in section
    assert "submit_ceo_intent" in section


def test_runbook_records_real_client_auth_and_dcr_effect_unknown_boundaries():
    text = RUNBOOK.read_text(encoding="utf-8")
    required = (
        "Codex CLI 0.154.0 or newer",
        "mastermind-executive",
        "http_headers_helper",
        "macOS Keychain",
        "codex mcp login",
        "resource identity mismatch",
        "DCR_EFFECT_UNKNOWN",
        "must not retry",
        "must not delete the pending registration marker",
        "--reconcile-client-id",
        "--reconcile-attempt-ref",
        "--reconcile-client-name",
        "pre-fingerprint",
        "mcp_servers.mastermind-executive.http_headers_helper",
        "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/bin/python3.14",
        "working directory",
        "Mastermind Codex Astra",
        "offline_access",
        "must not request `openid`",
    )
    for phrase in required:
        assert phrase in text


def test_runbook_preserves_exact_parent_and_capacity_ownership():
    text = RUNBOOK.read_text(encoding="utf-8")
    required = (
        "exact current RuntimeBinding",
        "process generation",
        "provider-native handle",
        "manually opened arbitrary Codex tab",
        "Capacity owns provider/account/host placement",
        "alibaba-token-plan-personal.codex-responses",
        "BUILT_NOT_PROVEN",
        "autonomous_allowed=false",
        "effect_unknown",
        "same request_ref",
        "l2_sol_ceo",
        "$CODEX_HOME/agents/l2-sol-ceo.toml",
        "native multi-agent concurrency at one",
    )
    for phrase in required:
        assert phrase in text


def test_astra_policy_contains_no_direct_provider_spawn_or_physical_assignment_commands():
    section = _astra_section()
    forbidden = (
        "pool run",
        "spawn_minimax",
        "spawn_glm",
        "provider_home=",
        "account_number=",
    )
    for token in forbidden:
        assert token not in section


def test_attended_astra_profile_does_not_claim_executive_parent_cutover():
    section = _astra_section()
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for phrase in (
        "does not itself change the Executive `frontier.orchestrator` alias",
        "provider/binary-attestation owner",
        "profile presence alone is not production cutover evidence",
    ):
        assert phrase in section
    for phrase in (
        "Current Executive-parent compatibility hold",
        "Codex **0.147.0**",
        "did **not** expose `gpt-6-astra`",
        "frontier.orchestrator",
        "served-model canary",
    ):
        assert phrase in runbook
