from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _codex_config() -> dict:
    return tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))


def _codex_policy_section() -> str:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    start = text.index("### Codex frontier orchestration economics")
    end = text.index("\n### Reciprocal dialogue and watcher invariant", start)
    return text[start:end]


def test_frontier_codex_defaults_to_astra_and_native_fallback_to_sol() -> None:
    config = _codex_config()
    assert config["model"] == "gpt-6-astra"
    assert config["model_reasoning_effort"] == "xhigh"
    assert config["review_model"] == "gpt-6-sol"

    agents = config["agents"]
    assert agents["enabled"] is True
    assert agents["max_concurrent_threads_per_session"] == 3
    assert agents["default_subagent_model"] == "gpt-6-sol"
    assert agents["default_subagent_reasoning_effort"] == "high"
    assert "terra" not in agents["default_subagent_model"].lower()
    assert "luna" not in agents["default_subagent_model"].lower()


def test_codex_policy_is_fabric_first_without_creating_a_second_control_plane() -> None:
    section = _codex_policy_section()

    required = (
        "project-local default is **GPT-6 Astra**",
        "prefer the **existing Executive Fabric** over Codex-native subagents",
        "`submit_ceo_intent` ingress",
        "sub-orchestrator is a duty, not a",
        "existing `plan`, `work`, `review`",
        "GLM/Grok first for routine sub-orchestration",
        "already admitted, eligible, and capable",
        "Model Router and",
        "Capacity owner chooses the concrete provider/account/host",
        "Sol or an additional Astra",
        "Luna/Terra are exceptional compatibility/fallback lanes",
        "never self-arms a",
        "disabled or unproven provider lane",
        "pre-effect fallback only",
        "`EFFECT_UNKNOWN`",
        "not a replay of full worker transcripts",
    )
    for phrase in required:
        assert phrase in section

    assert section.index("GLM/Grok first") < section.index("Sol or an additional Astra")
    assert section.index("Sol or an additional Astra") < section.index("Luna/Terra")


def test_codex_policy_keeps_physical_placement_out_of_ceo_intent() -> None:
    section = _codex_policy_section()

    assert "must not inject a provider, model, account, credential home, endpoint, host, or worker" in section
    assert "never silently switch to a native subagent, another provider, or a new operation key" in section
    assert "another queue, scheduler," in section
    assert "retry plane, or state store" in section

    # Direct provider-spawn shortcuts would create a competing placement/control path.
    for forbidden in ("spawn_glm", "spawn_grok", "pool run", "provider_home="):
        assert forbidden not in section
