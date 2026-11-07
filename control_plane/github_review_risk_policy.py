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
_FAST_MAX_LINES = 2400
_FAST_MAX_FILES = 40
_MAX_TEST_DELETIONS = 50

# A small line count must never bypass trust-boundary / source-law review.
_CRITICAL_PREFIXES = (
    ".github/",
    "docs/sol_skills/",
    "docs/sol_",
    "docs/session_",
    "docs/executive_",
    "docs/agent_",
    "docs/github_",
    "docs/review_",
    "docs/authority_",
    "ops/executive_os/",
    "control_plane/github_review_",
    "control_plane/executive_",
    "integrations/github_review_",
    "integrations/studio_direct_mcp/",
    "scripts/deploy_",
    "scripts/release_",
    "security/",
    "skills/",
    "plugins/",
    ".claude/",
    ".codex/",
    ".cursor/",
    "ci/",
    "tests/test_ci_",
    "tests/test_security_",
    "tests/test_auth_",
    "tests/test_review_",
    "tests/test_policy_",
    "config/unrun_test_waivers.yml",
    "config/ci_",
    "trading/",
    "payments/",
    "billing/",
    "migrations/",
    "db/migrations/",
    "database/migrations/",
    "finance/execution/",
)
_CRITICAL_EXACT = frozenset({
    "AGENTS.md",
    "CLAUDE.md",
    "pytest.ini",
    "tox.ini",
    "noxfile.py",
    "setup.cfg",
    "scripts/mastermind_workspace.py",
    "tests/conftest.py",
    "tests/pytest_plugins.py",
    "pyproject.toml",
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
    # Accepted #2018 constitutional/security pins. An apparently tiny diff in
    # any of these must stay CRITICAL even under the CEO Web review waiver.
    "control_plane/packet_gate.py",
    "control_plane/governance.py",
    "control_plane/strategic_state.py",
    "config/strategic_state.yml",
    "config/contracts.yml",
    "research/MASTERMIND_CHARTER_V2.md",
    "DOCTRINE.md",
})
_CRITICAL_SEGMENTS = frozenset({
    "auth", "authentication", "authorization", "oauth", "security", "secrets",
    "secret", "credential", "credentials", "permission", "permissions",
    "ci", "policy", "pytest",
    "privilege", "privileges", "token", "tokens", "crypto", "encryption",
    "order_execution", "trade_execution", "trade_sizing", "payments",
    "payment", "billing", "trading", "order", "orders", "broker",
    "execution", "deployment", "workflow", "policy_authority",
})
_STANDARD_PREFIXES = (
    # Reserved platform/integration and financial source is machine-elevated.
    # Ordinary executable/test source is also at least STANDARD so #2016's
    # CI qualifier retains its required smoke checks.
    "control_plane/", "integrations/", "finance/", "engine/risk_",
    "ops/", "config/",
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
    "session", "authority",
})
_CRITICAL_HINTS = frozenset({
    "trust_boundary", "secrets", "auth", "privileged_ci", "deployment",
    "review_policy", "financial_execution", "irreversible",
})
_STANDARD_HINTS = frozenset({
    "user_behavior", "data_contract", "cross_service", "schema",
    "complex_refactor", "destructive_change",
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
class ReviewFileStat:
    path: str
    additions: int
    deletions: int
    previous_path: str | None = None


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
    # Optional exact per-file metrics; the trusted source collector verifies
    # them against authenticated totals, so evidence-only files do not consume
    # the code-change budget. Without these metrics use conservative totals.
    file_metrics: tuple[ReviewFileStat, ...] = ()


@dataclasses.dataclass(frozen=True)
class ReviewRiskAssessment:
    schema: str
    repository: str
    pull_number: int
    head_sha: str
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
    if type(facts.file_metrics) is not tuple or len(facts.file_metrics) > _MAX_PATHS:
        raise RiskPolicyInputError("file_metrics must be a bounded tuple")
    metric_paths: set[str] = set()
    metric_covered_paths: set[str] = set()
    for entry in facts.file_metrics:
        if type(entry) is not ReviewFileStat or entry.path not in facts.changed_paths:
            raise RiskPolicyInputError("file metric identity not bound to changed paths")
        if entry.path.lower() in metric_paths:
            raise RiskPolicyInputError("duplicate file metric")
        metric_paths.add(entry.path.lower())
        metric_covered_paths.add(entry.path.lower())
        if entry.previous_path is not None:
            if (type(entry.previous_path) is not str
                or entry.previous_path not in facts.changed_paths
                or entry.previous_path.lower() in metric_covered_paths):
                raise RiskPolicyInputError("previous path not bound to changed paths")
            metric_covered_paths.add(entry.previous_path.lower())
        for name in ("additions", "deletions"):
            value = getattr(entry, name)
            if type(value) is not int or not 0 <= value <= _MAX_METRIC:
                raise RiskPolicyInputError("file metric must be bounded nonnegative integer")
    if facts.file_metrics and metric_covered_paths != seen:
        raise RiskPolicyInputError("file metrics omit source paths")
    if facts.file_metrics and (
        sum(f.additions for f in facts.file_metrics) != facts.additions
        or sum(f.deletions for f in facts.file_metrics) != facts.deletions
    ):
        raise RiskPolicyInputError("file metrics do not match authenticated aggregate")


def minimum_review_requirements(tier: ReviewTier) -> tuple[int, int]:
    """Internal assurance only; native repository requirements remain separate."""
    return {
        ReviewTier.FAST: (0, 0),
        ReviewTier.STANDARD: (0, 0),
        ReviewTier.CRITICAL: (1, 0),
        ReviewTier.HOLD: (0, 0),
    }[tier]


def _result(facts: ReviewChangeFacts, tier: ReviewTier, *reasons: str) -> ReviewRiskAssessment:
    # Ordinary changes self-check; consequential automatic/native work receives
    # one distinct technical assessment. Formal GitHub approvals arise only
    # from actual repository enforcement or a specific binding release hold.
    # This does not enable the default-OFF host or change attended-Web policy.
    assessments, approvals = minimum_review_requirements(tier)
    return ReviewRiskAssessment(
        schema=SCHEMA,
        repository=facts.repository,
        pull_number=facts.pull_number,
        head_sha=facts.head_sha,
        tier=tier,
        minimum_independent_assessments=assessments,
        minimum_formal_non_author_approvals=approvals,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _is_critical_path(path: str) -> bool:
    lower = path.lower()
    if lower in {p.lower() for p in _CRITICAL_EXACT}:
        return True
    if lower.rsplit("/", 1)[-1] in {
        "agents.md", "claude.md", "skill.md", "codeowners",
        "security.md", ".cursorrules", ".clinerules",
    }:
        return True
    if lower.endswith("/conftest.py") or lower.endswith("/pytest_plugins.py"):
        return True
    if any(lower.startswith(prefix) for prefix in _CRITICAL_PREFIXES):
        return True
    # A directory or filename component that names a privileged boundary.
    parts = set(part for part in re.split(r"[/_.-]+", lower) if part)
    return bool(parts & _CRITICAL_SEGMENTS)


def _is_standard_path(path: str) -> bool:
    lower = path.lower()
    if lower in _STANDARD_EXACT or lower.endswith((".sql", ".lock")):
        return True
    if any(lower.startswith(prefix) for prefix in _STANDARD_PREFIXES):
        return True
    parts = set(part for part in re.split(r"[/_.-]+", lower) if part)
    return bool(parts & _STANDARD_SEGMENTS)


def _is_test_path(path: str) -> bool:
    lower = path.lower()
    parts = lower.split("/")
    return (
        any(part in ("tests", "test", "__tests__", "e2e") for part in parts[:-1])
        or lower.endswith((".test.ts", ".test.tsx", ".test.js", ".test.jsx",
                           ".spec.js", ".spec.ts", ".spec.tsx"))
    )


# FAST is shared with the accepted #2016 CI qualifier: FAST selects static-only
# checks; STANDARD selects executable smoke checks. Even a tiny code/test diff
# must never use FAST to waive a smoke test. Attended CEO Web's no-review
# decision is separate from this signed machine/CI risk classification.


_SUPPORTING_PREFIXES = (
    "research/evidence/", "mockups/evidence/", "ux-evidence/",
    "terminal/docs/pr-crops/", "terminal/docs/verification/",
    "docs/verification/", "docs/screenshots/",
    "docs/evidence/", "docs/superpowers/plans/",
)
_INERT_DOC_EXACT = frozenset({
    "readme.md", "docs/readme.md", "docs/guide.md", "docs/user-guide.md",
})
_INERT_DOC_PREFIXES = (
    "docs/user/", "docs/guides/", "docs/faq/", "docs/tutorials/",
)
_VISUAL_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
    ".woff", ".woff2",
)
_INERT_TEXT_SUFFIXES = (".md", ".rst", ".txt")
_EVIDENCE_SUFFIXES = (".json", ".yml", ".yaml", ".log", ".csv", ".html")


def _is_supporting_change(path: str) -> bool:
    """Only known passive evidence, user guides and visual assets are exempt.

    Unknown operational Markdown is NOT silently a no-review document.
    Executable test sources are never supporting just because of a filename.
    """
    lower = path.lower()
    if _is_test_path(lower) or lower.startswith(("terminal/e2e/", "e2e/")):
        return False
    if lower in _INERT_DOC_EXACT:
        return True
    if any(lower.startswith(prefix) for prefix in _INERT_DOC_PREFIXES):
        return lower.endswith(_INERT_TEXT_SUFFIXES + _VISUAL_SUFFIXES)
    if any(lower.startswith(prefix) for prefix in _SUPPORTING_PREFIXES):
        return lower.endswith(_INERT_TEXT_SUFFIXES + _VISUAL_SUFFIXES + _EVIDENCE_SUFFIXES)
    return lower.endswith(_VISUAL_SUFFIXES)


def assess_review_risk(facts: ReviewChangeFacts) -> ReviewRiskAssessment:
    """Choose the smallest review burden justified by verified source evidence.

    This function neither runs/requests a review nor grants a release exemption.
    Missing source evidence is HOLD, not a low-risk assumption.
    """
    _validate(facts)
    if not facts.complete_source_verified or not facts.changed_paths:
        return _result(facts, ReviewTier.HOLD, "CURRENT_COMPLETE_DIFF_NOT_PROVEN")
    critical = [path for path in facts.changed_paths if _is_critical_path(path)]
    if critical or any(h in _CRITICAL_HINTS for h in facts.risk_hints):
        return _result(facts, ReviewTier.CRITICAL, "TRUST_OR_AUTHORITY_BOUNDARY")
    standard = [path for path in facts.changed_paths
                if not _is_supporting_change(path) and _is_standard_path(path)]
    if standard or any(h in _STANDARD_HINTS for h in facts.risk_hints):
        return _result(facts, ReviewTier.STANDARD, "CONSEQUENTIAL_OR_COMPLEX_CHANGE")
    if facts.file_metrics:
        test_deletions = sum(f.deletions for f in facts.file_metrics if _is_test_path(f.path))
        material = tuple(f for f in facts.file_metrics if not _is_supporting_change(f.path))
        total = sum(f.additions + f.deletions for f in material)
        material_count = len(material)
    else:
        test_deletions = facts.deletions if all(_is_test_path(p) for p in facts.changed_paths) else 0
        total = facts.additions + facts.deletions
        material_count = len(facts.changed_paths)
    if test_deletions > _MAX_TEST_DELETIONS:
        return _result(facts, ReviewTier.STANDARD, "SUBSTANTIAL_TEST_REMOVAL")
    if all(_is_supporting_change(p) for p in facts.changed_paths):
        return _result(facts, ReviewTier.FAST, "ROUTINE_DOCUMENTATION_TESTS_OR_EVIDENCE")
    if total > _FAST_MAX_LINES or material_count > _FAST_MAX_FILES:
        return _result(facts, ReviewTier.STANDARD, "SCOPE_EXCEEDS_FAST_LIMIT")
    # Under #2016, risk tier FAST also selects CI mode=fast (static-only).
    # Active code and tests stay STANDARD even when a Web CEO session needs no
    # additional independent reviewer; their smoke checks must remain enabled.
    return _result(facts, ReviewTier.STANDARD, "ACTIVE_SOURCE_REQUIRES_CI_SMOKE")
