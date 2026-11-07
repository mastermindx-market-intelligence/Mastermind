"""Contract checks for project-level governance; not proof of installed behavior."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "skills/mastermind-fabric-orchestration/references"

def test_meta_ceo_preserves_project_quality_and_real_acceptance():
    policy = (ROLES / "meta-ceo.md").read_text()
    for required in ("accountable outcome owner", "Do not shadow-implement",
                     "final independent product acceptance", "NOT_ACCEPTED",
                     "original Chairman requirements", "actual chart behavior"):
        assert required in policy

def test_program_ceo_owns_domain_review_and_return():
    policy = (ROLES / "program-ceo.md").read_text()
    for required in ("defined domain outcome", "reviewers independently",
                     "one integrated domain result", "author does not self-certify"):
        assert required in policy

def test_operator_does_not_confuse_execution_with_accepted_product():
    policy = (ROLES / "operator.md").read_text()
    for required in ("UNVERIFIED", "accepted_by label", "exact artifact revisions",
                     "real-path", "original product thesis"):
        assert required in policy


def test_future_project_default_covers_full_quality_chain():
    policy = (ROOT / "skills/mastermind-fabric-orchestration/SKILL.md").read_text()
    for contract in ("every newly assigned Mastermind project", "Macro Dashboard", "Terminal", "consequential multi-domain product",
                     "not split ordinary implementation", "original-intent falsifiers",
                     "independence", "NOT_ACCEPTED", "Small reversible tasks",
                     "future-session loading"):
        assert contract in policy

def test_installed_global_provider_policy_inherits_project_quality_floor(tmp_path):
    from test_operator_first_policy import load_installer, seed_home
    module, _, guard = load_installer(tmp_path)
    home = tmp_path / "home"
    seed_home(home)
    assert module.apply_policy(home, guard_source=guard)["state"] == "READY"
    for doc in (home / ".codex/AGENTS.md", home / ".claude/CLAUDE.md"):
        text = doc.read_text()
        assert text.count("every newly assigned Mastermind project") == 1
        assert "not split ordinary implementation" in text
        assert "original-intent falsifiers" in text
        assert "NOT_ACCEPTED" in text


def test_fable_proven_artifact_ownership_and_review_methods_are_in_operator_role():
    policy = (ROLES / "operator.md").read_text()
    for required in ("exclusive artifact ownership", "not attractive topic names",
                     "Freeze the interface", "nullability", "actual search coverage",
                     "counts delivered acceptance obligations", "one worktree/writer",
                     "independent review", "integration parent's product acceptance"):
        assert required in policy
