from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/SOL_WATCHER_ACCOUNT_HARDENING.md"


def test_three_account_runbook_is_account_local_and_receipted() -> None:
    assert RUNBOOK.exists(), "account hardening runbook must be checked in"
    text = " ".join(RUNBOOK.read_text(encoding="utf-8").split())

    required_phrases = (
        "account-local-only mutation",
        "account/surface identity",
        "export time",
        "protected Skillpack SHA",
        "active watcher count",
        "changed or disabled watcher IDs",
        "unresolved action-authority conflicts",
        "one authoritative action",
        "two observer accounts",
        "canonical action-target transfer",
        "never elect by recency",
        "passing prompt audit does not prove runtime consumption",
        '"audit_kind": "SOL_WATCHER"',
        '"audit_kind": "NON_WATCHER"',
        "aggregate:<stable-scope-id>",
        "ACTION_AUTHORITATIVE requires one exact Slack carrier",
        "one rotating Codex OAuth slot",
        "does not identify or authorize all three ChatGPT web accounts",
        "Audit each exact web account's native Tasks/Automations store",
        "Codex availability is not a watcher-store prerequisite",
        "native task ID must be present and unique",
        "enabled state must be a JSON boolean",
        "Duplicate native task IDs",
        "invalid_export_tasks",
        "non-authoritative watcher",
    )
    for phrase in required_phrases:
        assert phrase in text, f"missing account hardening law: {phrase}"


def test_runbook_requires_canonical_render_replace_readback() -> None:
    text = " ".join(RUNBOOK.read_text(encoding="utf-8").split())
    required_phrases = (
        "render_watcher_prompt",
        "MMX_SOL_WATCHER_V1",
        "MMX_SOL_WATCHER_BODY_V1",
        "replace the complete native task prompt",
        "Read the task back immediately",
        "byte-for-byte",
        "CANONICAL_PROMPT_MISMATCH",
        "Natural-language polarity is not a validity boundary",
        "Do not patch prose",
        "python3 -m scripts.audit_sol_watchers",
        "EFFECT_UNKNOWN",
        "Do not repeat the modification on another account",
        "do not cross-account retry or fail over",
        "canonical prompt digest",
    )
    for phrase in required_phrases:
        assert phrase in text, f"missing renderer/readback ceremony: {phrase}"
