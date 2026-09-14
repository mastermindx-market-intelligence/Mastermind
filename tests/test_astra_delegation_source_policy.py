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
        "Internal Codex agents are fallback",
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


def test_internal_codex_fallback_remains_bounded_terra_medium_three_threads():
    config = CODEX_CONFIG.read_text(encoding="utf-8")
    assert 'max_concurrent_threads_per_session = 3' in config
    assert 'default_subagent_model = "gpt-5.6-terra"' in config
    assert 'default_subagent_reasoning_effort = "medium"' in config
