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
    )
    for phrase in required_phrases:
        assert phrase in text, f"missing account hardening law: {phrase}"
