from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _normalized(path: str) -> str:
    return " ".join(_read(path).split())


def test_release_compatibility_law_exists_and_separates_semantics_from_integration() -> None:
    spec_path = ROOT / (
        "docs/superpowers/specs/"
        "2026-09-02-autonomy-release-compatibility-review-reuse.md"
    )
    assert spec_path.exists(), "release-compatibility source law must exist"

    spec = _normalized(str(spec_path.relative_to(ROOT)))
    required = (
        "SEMANTIC_HEAD",
        "INTEGRATION_PROOF",
        "REVIEW_REUSE_ALLOWED",
        "FULL_REREVIEW_REQUIRED",
        "behind_by=0 is not a release property",
        "candidate-owned blobs are byte-identical",
        "governing source set is materially unchanged",
        "latest protected-base merge ref",
        "expected-head merge",
        "post-merge protected readback",
        "No branch join is permitted solely to refresh ancestry",
    )
    for phrase in required:
        assert phrase in spec, f"missing release-compatibility law: {phrase}"


def test_review_reuse_never_waives_material_change_or_live_proof() -> None:
    spec = _normalized(
        "docs/superpowers/specs/"
        "2026-09-02-autonomy-release-compatibility-review-reuse.md"
    )
    required_full_rereview_causes = (
        "candidate-owned blob changed",
        "governing source changed materially",
        "dependency closure intersects protected movement",
        "authority, identity, security, effect, retry, or persistence semantics changed",
        "production or live proof is owed",
        "unresolved blocking review",
    )
    for phrase in required_full_rereview_causes:
        assert phrase in spec, f"missing full-rereview trigger: {phrase}"

    forbidden_waivers = (
        "green CI grants merge authority",
        "path-disjoint means production-proven",
        "review reuse grants execution authority",
    )
    for phrase in forbidden_waivers:
        assert phrase in spec, f"missing explicit non-waiver: {phrase}"


def test_sol_review_and_reconciliation_skills_apply_the_same_rule() -> None:
    review = _normalized("docs/sol_skills/REVIEW_RETURN.md")
    reconcile = _normalized("docs/sol_skills/RECONCILE_STATE.md")

    review_required = (
        "Review reuse after protected-base movement",
        "semantic review and integration proof are separate receipts",
        "Do not invalidate an immutable semantic review merely because protected master advanced",
        "FULL_REREVIEW_REQUIRED",
        "REVIEW_REUSE_ALLOWED",
    )
    for phrase in review_required:
        assert phrase in review, f"missing REVIEW_RETURN acceleration law: {phrase}"

    reconcile_required = (
        "Path-disjoint protected movement",
        "Do not merge protected master into the carrier merely to make `behind_by=0`",
        "latest-base merge-ref proof",
        "material-source comparison",
        "semantic review may be reused",
    )
    for phrase in reconcile_required:
        assert phrase in reconcile, f"missing RECONCILE_STATE acceleration law: {phrase}"


def test_autonomy_completion_mode_freezes_the_real_golden_path() -> None:
    plan_path = ROOT / (
        "docs/superpowers/plans/"
        "2026-09-02-autonomy-completion-mode.md"
    )
    assert plan_path.exists(), "autonomy completion-mode plan must exist"

    plan = _normalized(str(plan_path.relative_to(ROOT)))
    required = (
        "NO_NEW_AUTONOMY_ARCHITECTURE",
        "W3C observation authority",
        "RET1 -> RESULT -> Wake -> ACK1 -> Sol continuation",
        "Capacity C1 -> Capacity C2 -> Stage B1",
        "Control Room over genuine live Executive Runtime truth",
        "MULTI_ROOT_ADVERSARIAL",
        "SMALL_FLEET",
        "SOAK_FLEET",
        "ROUTINE_CHAIRMAN_OPERATION_COUNT = 0",
        "Adjacent work may proceed only when it is path-disjoint",
        "one independently useful vertical at a time",
    )
    for phrase in required:
        assert phrase in plan, f"missing completion-mode law: {phrase}"


def test_completion_mode_rejects_false_progress_and_review_churn() -> None:
    plan = _normalized(
        "docs/superpowers/plans/2026-09-02-autonomy-completion-mode.md"
    )
    required = (
        "source protection is not production proof",
        "do not open a replacement carrier",
        "do not start an adjacent architecture wave merely because the golden path is waiting on CI",
        "current-base movement alone is not substantive work",
        "The next action must remove one named golden-path blocker",
    )
    for phrase in required:
        assert phrase in plan, f"missing anti-churn rule: {phrase}"


def test_native_merge_queue_owns_final_integrated_checks_without_prequeue_circular_gate() -> None:
    spec = _normalized('docs/superpowers/specs/2026-09-02-autonomy-release-compatibility-review-reuse.md')
    review = _normalized('docs/sol_skills/REVIEW_RETURN.md')
    reconcile = _normalized('docs/sol_skills/RECONCILE_STATE.md')
    delivery = _normalized('docs/DELIVERY_WORKFLOW.md')
    assert 'absence of prequeue check runs' in spec
    assert 'after queue entry' in spec
    assert 'before the actual merge' in spec
    assert 'merge_group' in review
    assert 'before queue admission' in reconcile
    assert 'do not require nonexistent prequeue merge-ref check runs' in reconcile
    assert 'do not add a manual synthetic PR merge-ref check requirement' in delivery
    assert 'If final integrated checks fail, the queue must not merge' in delivery
    assert 'review pass and queue entry is authorized' in delivery


def test_workspace_and_recovery_rules_never_demand_ancestry_only_branch_joins() -> None:
    delivery_source = _read('docs/DELIVERY_WORKFLOW.md')
    delivery = _normalized('docs/DELIVERY_WORKFLOW.md')
    assert 'git merge-base HEAD origin/master' in delivery_source
    assert 'git merge-base --is-ancestor origin/master HEAD' not in delivery_source
    assert 'do not block ordinary edits solely because the worktree is behind' in delivery
    assert 'material overlap or changed source law' in delivery
    assert 'Do not join/rebase merely to reset GitHub\'s `behind` count' in delivery
    assert 'actual path/semantic/dependency collisions require composition' in delivery
