"""Source-only guard for the Chairman's attended CEO Web review waiver.

This does not claim a protected merge, live Project setting, native skill install,
a real reviewer child, or a signed GitHub/Executive machine admission.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/SESSION_LOCAL_REVIEW_POLICY.md"


def policy() -> str:
    return POLICY.read_text(encoding="utf-8")


def test_attended_web_waiver_is_all_three_tiers_without_host_dependency():
    s = policy()
    required = (
        "Attended CEO Web FAST / STANDARD / CRITICAL",
        "Zero blanket independent technical reviewers",
        "zero additional formal non-author approvals",
        "Do not wait for #2018 or a signed host deployment",
        "Native/automatic CRITICAL requires one distinct read-only technical reviewer",
        "SELF_REVIEWED",
        "proportionate security and real-path proof",
    )
    for anchor in required:
        assert anchor in s, anchor
    for obsolete in (
        "FAST / ordinary STANDARD only AFTER",
        "Before #2018 is protected",
        "CRITICAL's two technical perspectives must show two distinct child",
        "a CRITICAL source subagent runs and returns locally",
    ):
        assert obsolete not in s, obsolete


def test_machine_review_and_actual_native_release_stay_distinct():
    s = policy()
    for anchor in (
        "signed AUTOMATIC GitHub/Executive",
        "OFF unless separately authorized",
        "separate",
        "native GitHub/CODEOWNERS",
        "mandatory hosted CI",
        "Never self-approve",
        "HOLD",
        "original",
        "explicit permission denial",
        "separate START",
        "Actual GitHub native requirements reject author self-approval",
    ):
        assert anchor in s, anchor


def test_optional_review_availability_is_not_a_default_delegation():
    s = policy()
    table = s.split("## Session-local review avenues", 1)[1].split(
        "## Receipt, adversarial protocol and limits", 1
    )[0]
    assert "FAST, STANDARD and CRITICAL" in table
    for surface in (
        "ChatGPT Web, ordinary session",
        "ChatGPT Web, Pro session",
        "Codex native",
        "Claude native",
        "Subagent Fabric",
    ):
        assert surface in table
    assert "when distinct scrutiny is genuinely owed" in table
    assert "when a separate technical review is actually required" in s.lower()
    assert "A CRITICAL label alone creates no two-child requirement" in table


def test_protected_release_cannot_pretend_to_be_project_installation():
    s = policy()
    status = next(line for line in s.splitlines() if line.startswith("**Status:**"))
    assert "#2030" in status and "protected-merged" in status
    assert "68e3b816c95930f6996dbcc10403a6ad694e6889" in status
    assert "SOURCE CANDIDATE" not in status
    assert "does not install ChatGPT Project settings" in s
    assert "Distinguish source, installed instructions" in s
    assert "Normal automated release" in s


def test_signed_machine_risk_status_separates_merged_waiver_from_unverified_install():
    risk = (ROOT / "docs/REVIEW_RISK_POLICY.md").read_text(encoding="utf-8")
    status = next(line for line in risk.splitlines() if line.startswith("**Status:**"))
    assert "#1989" in status and "#2030" in status
    assert "protected-merged" in status
    assert "source candidate" not in status.lower()
    assert "ChatGPT Project settings" in status and "NOT_PROVEN" in status
    assert "AUTOMATIC" in status and "OFF" in status
    for term in ("FAST", "STANDARD", "CRITICAL", "CODEOWNERS"):
        assert term in risk


def test_native_critical_review_covers_full_canonical_risk_signals():
    signals = ("auth/security/permissions", "source authority", "review/release automation",
               "privileged CI", "financial execution", "irreversible data", "exactly-once")
    for file in ("AGENTS.md", "CLAUDE.md", "docs/DELIVERY_WORKFLOW.md",
                 "docs/REVIEW_RISK_POLICY.md", "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md",
                 "docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md", "docs/SESSION_LOCAL_REVIEW_POLICY.md"):
        source = " ".join((ROOT / file).read_text(encoding="utf-8").split())
        assert "CRITICAL row" in source, file
        for signal in signals:
            assert signal in source, (file, signal)
    source = policy()
    assert "CRITICAL classification by itself does **not** require one or two native children" not in source
    assert "Native/automatic CRITICAL requires one distinct read-only technical reviewer" in source
    assert "the attended CEO-Web all-tier waiver remains" in source
    assert "Do not add a second reviewer, another account or a new review carrier by habit" in source
    kernel = (ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md").read_text(encoding="utf-8")
    assert "Native CRITICAL keeps actual distinct review; Web 5A applies" in kernel


def test_historical_web_rationale_cannot_reinstate_a_current_scope_limit():
    source = (ROOT / "docs/REVIEW_RISK_POLICY.md").read_text(encoding="utf-8")
    historical = source.split("## Historical accepted #2030 rationale:", 1)[1]
    assert "source candidate" not in historical
    assert "Only attended-Web review handoffs are waived by this policy" not in historical
    normalized = " ".join(historical.split())
    assert "historical Web-only scope is superseded for native/automatic work" in normalized
    assert "current proportionate-qualification section above" in normalized
    assert "attended Web all-tier waiver remains" in normalized
    assert "default OFF" in historical
