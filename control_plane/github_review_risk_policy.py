"""Advisory risk tier for a source-verified GitHub PR diff.

This is a deterministic policy input to the *existing* release and review
owners, NOT a merge, reviewer, approval, CI, worker or admission authority.
Facts must be collected from an authenticated current-head GitHub read, never
from PR description, author-controlled labels or agent self-attestation.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum

SCHEMA = "mastermind.github_review_risk_assessment.v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_MAX_PATHS = 256
_MAX_METRIC = 10_000_000
_FAST_MAX_LINES = 200
_FAST_MAX_FILES = 8
_MAX_TEST_DELETIONS = 50

# A small line count must never bypass trust-boundary / source-law review.
_CRITICAL_PREFIXES = (
    ".github/",
    "docs/sol_skills/",
    "ops/executive_os/",
    "control_plane/github_review_",
    "integrations/github_review_",
    "scripts/deploy_",
    "scripts/release_",
    "security/",
)
_CRITICAL_EXACT = frozenset({
    "AGENTS.md",
    "CLAUDE.md",
    "CODEOWNERS",
    "SECURITY.md",
    "config/authority_map.yml",
    "control_plane/executive_runtime.py",
    "control_plane/github_release_assessment.py",
    "docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md",
    "docs/CEO_PROJECT_PLAN_CONTINUITY.md",
    "docs/DELIVERY_WORKFLOW.md",
    "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md",
    "docs/REVIEW_RISK_POLICY.md",
    "docs/GITHUB_REVIEW_INGRESS.md",
})
_CRITICAL_SEGMENTS = frozenset({
    "auth", "authentication", "authorization", "oauth", "security", "secrets",
    "secret", "credential", "credentials", "permission", "permissions",
    "privilege", "privileges", "token", "tokens", "crypto", "encryption",
    "order_execution", "trade_execution", "trade_sizing", "payments",
    "payment", "billing",
})
_STANDARD_PREFIXES = (
    "control_plane/", "integrations/", "migrations/", "db/migrations/",
    "database/migrations/", "brain/", "trading/", "finance/", "engine/risk_",
)
_STANDARD_EXACT = frozenset({
    "pyproject.toml", "requirements.txt", "package.json",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
})
_STANDARD_SEGMENTS = frozenset({
    "schema", "schemas", "migration", "migrations", "reconciliation",
    "risk", "position", "positions", "portfolio", "signal", "signals",
    "prophet", "settlement", "webhook", "runtime", "publication",
})
_CRITICAL_HINTS = frozenset({
    "trust_boundary", "secrets", "auth", "privileged_ci", "deployment",
    "review_policy", "financial_execution", "irreversible",
})
_STANDARD_HINTS = frozenset({
    "user_behavior", "data_contract", "cross_service", "schema",
    "complex_refactor",
})
_ALL_HINTS = _CRITICAL_HINTS | _STANDARD_HINTS
_DOC_EXTENSIONS = (".md", ".rst", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".gif")
_TEST_PREFIXES = ("tests/", "test/", "__tests__/")


class RiskPolicyInputError(ValueError):
    """The source snapshot is malformed; never treat it as a FAST receipt."""


class ReviewTier(str, Enum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    CRITICAL = "CRITICAL"
    HOLD = "HOLD"


@dataclasses.dataclass(frozen=True)
class ReviewChangeFacts:
    repository: str
    pull_number: int
    head_sha: str
    changed_paths: tuple[str, ...]
    additions: int
    deletions: int
    # Only the trusted GitHub reader/diff validator can set this true.
    complete_source_verified: bool
    # Hints may only elevate risk and must come from a trusted policy owner.
    risk_hints: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ReviewRiskAssessment:
    schema: str
    tier: ReviewTier
    minimum_independent_assessments: int
    minimum_formal_non_author_approvals: int
    reasons: tuple[str, ...]

    @property
    def fast_lane_candidate(self) -> bool:
        """Not authority to merge: CI, live holds and native rules still apply."""
        return self.tier is ReviewTier.FAST


def _validate(facts: ReviewChangeFacts) -> None:
    if type(facts) is not ReviewChangeFacts:
        raise RiskPolicyInputError("expected exact ReviewChangeFacts")
    if type(facts.repository) is not str or _REPO.fullmatch(facts.repository) is None:
        raise RiskPolicyInputError("invalid repository")
    if type(facts.pull_number) is not int or facts.pull_number <= 0:
        raise RiskPolicyInputError("invalid pull number")
    if type(facts.head_sha) is not str or _SHA40.fullmatch(facts.head_sha) is None:
        raise RiskPolicyInputError("head_sha must be a lowercase full Git SHA")
    if type(facts.changed_paths) is not tuple or len(facts.changed_paths) > _MAX_PATHS:
        raise RiskPolicyInputError("changed_paths must be a bounded tuple")
    seen: set[str] = set()
    for path in facts.changed_paths:
        if type(path) is not str or not (1 <= len(path) <= 512):
            raise RiskPolicyInputError("invalid changed path")
        if path.startswith("/") or "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
            raise RiskPolicyInputError("unsafe changed path")
        if any(segment in {"", ".", ".."} for segment in path.split("/")):
            raise RiskPolicyInputError("noncanonical changed path")
        if path.lower() in seen:
            raise RiskPolicyInputError("duplicate or case-conflicting changed path")
        seen.add(path.lower())
    for name in ("additions", "deletions"):
        value = getattr(facts, name)
        if type(value) is not int or not 0 <= value <= _MAX_METRIC:
            raise RiskPolicyInputError(f"{name} must be a bounded nonnegative integer")
    if type(facts.complete_source_verified) is not bool:
        raise RiskPolicyInputError("complete_source_verified must be a boolean")
    if type(facts.risk_hints) is not tuple or any(
        type(hint) is not str or hint not in _ALL_HINTS for hint in facts.risk_hints
    ):
        raise RiskPolicyInputError("risk_hints must be exact known escalation-only values")
    if len(set(facts.risk_hints)) != len(facts.risk_hints):
        raise RiskPolicyInputError("duplicate risk hints")


def _result(tier: ReviewTier, *reasons: str) -> ReviewRiskAssessment:
    review_counts = {
        ReviewTier.FAST: (0, 0),
        ReviewTier.STANDARD: (1, 1),
        ReviewTier.CRITICAL: (2, 1),
        ReviewTier.HOLD: (0, 0),
    }
    assessments, approvals = review_counts[tier]
    return ReviewRiskAssessment(
        schema=SCHEMA,
        tier=tier,
        minimum_independent_assessments=assessments,
        minimum_formal_non_author_approvals=approvals,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _is_critical_path(path: str) -> bool:
    lower = path.lower()
    if lower in {p.lower() for p in _CRITICAL_EXACT}:
        return True
    if any(lower.startswith(prefix) for prefix in _CRITICAL_PREFIXES):
        return True
    # A directory or filename component that names a privileged boundary.
    parts = lower.replace(".", "_").replace("-", "_").split("/")
    return any(part in _CRITICAL_SEGMENTS for part in parts)


def _is_standard_path(path: str) -> bool:
    lower = path.lower()
    if lower in _STANDARD_EXACT or lower.endswith((".sql", ".lock")):
        return True
    if any(lower.startswith(prefix) for prefix in _STANDARD_PREFIXES):
        return True
    parts = lower.replace(".", "_").replace("-", "_").split("/")
    return any(part in _STANDARD_SEGMENTS for part in parts)


def _is_test_path(path: str) -> bool:
    lower = path.lower()
    return lower.startswith(_TEST_PREFIXES) or "/__tests__/" in lower or lower.endswith((".test.ts", ".test.tsx", ".spec.js", ".spec.ts"))


def assess_review_risk(facts: ReviewChangeFacts) -> ReviewRiskAssessment:
    """Choose the smallest review burden justified by verified source evidence.

    This function neither runs/requests a review nor grants a release exemption.
    Missing source evidence is HOLD, not a low-risk assumption.
    """
    _validate(facts)
    if not facts.complete_source_verified or not facts.changed_paths:
        return _result(ReviewTier.HOLD, "CURRENT_COMPLETE_DIFF_NOT_PROVEN")
    critical = [path for path in facts.changed_paths if _is_critical_path(path)]
    if critical or any(h in _CRITICAL_HINTS for h in facts.risk_hints):
        return _result(ReviewTier.CRITICAL, "TRUST_OR_AUTHORITY_BOUNDARY")
    standard = [path for path in facts.changed_paths if _is_standard_path(path)]
    if standard or any(h in _STANDARD_HINTS for h in facts.risk_hints):
        return _result(ReviewTier.STANDARD, "CONSEQUENTIAL_OR_COMPLEX_CHANGE")
    total = facts.additions + facts.deletions
    if total > _FAST_MAX_LINES or len(facts.changed_paths) > _FAST_MAX_FILES:
        return _result(ReviewTier.STANDARD, "SCOPE_EXCEEDS_FAST_LIMIT")
    if all(_is_test_path(p) for p in facts.changed_paths) and facts.deletions > _MAX_TEST_DELETIONS:
        return _result(ReviewTier.STANDARD, "SUBSTANTIAL_TEST_REMOVAL")
    if all(p.lower().endswith(_DOC_EXTENSIONS) for p in facts.changed_paths):
        return _result(ReviewTier.FAST, "ROUTINE_DOCUMENTATION_OR_ASSETS")
    return _result(ReviewTier.FAST, "BOUNDED_ROUTINE_CHANGE")
