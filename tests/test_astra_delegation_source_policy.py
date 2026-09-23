from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"


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
        "Native Codex agents are explicit bounded fallback",
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


def test_native_codex_fanout_is_disabled_by_default_and_frontier_only_when_opted_in():
    config = CODEX_CONFIG.read_text(encoding="utf-8")
    assert 'enabled = false' in config
    assert 'max_concurrent_threads_per_session = 1' in config
    assert 'default_subagent_model = "gpt-5.6-sol"' in config
    assert 'default_subagent_reasoning_effort = "high"' in config
    assert 'gpt-5.6-luna' not in config
    assert 'gpt-5.6-terra' not in config


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
