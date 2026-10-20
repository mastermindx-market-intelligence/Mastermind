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
