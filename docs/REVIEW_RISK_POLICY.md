# Risk-tiered PR review — lower friction without removing real safeguards

**Status:** Proposed source policy for Chairman directive 2026-11-02. Not an installed GitHub rule or an approval/merge bypass. It becomes operative only after protected acceptance, alignment with source-law/instruction consumers and host enrollment. This document has no separate source of runtime authority.

**Owner:** Existing GitHub release workflow + `control_plane/github_release_assessment.py` (approval adjudication), Executive/Fabric (admission and independent results), and native branch rules/merge queue (enforcement). The pure `control_plane/github_review_risk_policy.py` only supplies a reproducible advisory risk tier. No new webhook, queue, reviewer registry, auth store, code owner, worker budget, retry process or release engine.

## Chairman's attended-Web waiver versus authenticated machine review

The assigned attended CEO Web session self-checks the exact diff, runs targeted
security/behavior tests and required CI, and completes the authorized native
release. **FAST, STANDARD and CRITICAL each impose zero blanket independent
reviewers or additional formal non-author approvals on attended CEO Web work.**
Use a real separate reviewer only when a binding native/CODEOWNERS/security hold
or a separately authorized explicit manual request actually requires one.
The tier still selects proportionate correctness, security and real-path proof.
No self-approval, self-merge, bypass, fabricated approval or release on red CI.

The same pure classifier is consumed by the separately authenticated, default-OFF
**signed AUTOMATIC GitHub/Executive machine review** ingress. The machine
cannot reliably infer attended CEO Web authorship from PR prose, labels or
paths. **Its STANDARD and CRITICAL review counts remain binding when that
machine consumer is legitimately enabled**; the attended waiver does not
rewrite or auto-skip an authenticated privileged machine's risk requirement.

| Tier | Source signals | Signed automatic assessments (when enabled) | Signed automatic approvals (advisory) | Attended-Web and machine handling |
| --- | --- | ---: | ---: | --- |
| **FAST** | Verified passive user guides, historical evidence and visual assets, no executable/test/config/privileged paths | **0** | **0** | Self-check and CI; signed machine may skip review Job for complete exact-head source |
| **STANDARD** | Ordinary executable code/test, application behavior and non-sensitive integration | **1** | **1** | Attended Web requires no blanket reviewer; signed machine retains original single review Job when enabled |
| **CRITICAL** | Auth, security, permissions, authority, CI/release automation, financial/trading execution and irreversible effects | **2** | **1** | Attended Web requires targeted security/real-path proof without a universal reviewer; signed machine keeps critical scrutiny |
| **HOLD** | Exact-head source unproven, partial pages, identity/effect uncertainty | **Not inferred** | **Not inferred** | Refuse an exemption or review job pending original-carrier reconciliation |

The signed machine columns are **not** new attended-session demands and never
replace actual native branch/CODEOWNERS approvals, security/release holds or
required CI. A real distinct-context native child can satisfy an independently
required *technical* review only when lawfully started/read back; an author's
second pass is SELF_REVIEWED, not that child. Neither supplies a formal GitHub
nonauthor `APPROVED`. The authorized release actor must not be the source author
where the protected owner requires independent release. The default-OFF machine
host is not a prerequisite to conducting attended CEO Web source work.

## Exact-head source verification and pre-admission disposition

The additional pure `control_plane/github_review_risk_source.py` requires an **existing authenticated installation-scoped GitHub reader** to supply one current PR identity, every bounded changed-file page, and a second identical current PR read. `integrations/github_review_risk_reader.py` now supplies a narrow concrete adapter backed by the incumbent `GitHubReviewAPI`'s existing installation-token-scoped read transport; no second client, key, webhook or GitHub endpoint owner is introduced. Its read-only hermetic suite verifies whole-source-to-dispatch outcomes and refused malformed identities. The incumbent #1977 host must still install and call this read seam after signed webhook authority and before Executive admission. It refuses incomplete pagination, inconsistent totals, changed heads/base, forks, drafts, missing code patches, and missing original paths for renames. Deleted files escalate the risk tier; renamed files are assessed at both their old and new paths. These inputs are **not** permission or a GitHub credential source by themselves.

The pure `control_plane/github_review_risk_dispatch.py` is the integration seam: verified signed AUTOMATIC origin + FAST => `SKIP_NO_REVIEW_NEEDED` **before Executive creates a review Job**; verified signed AUTOMATIC STANDARD/CRITICAL => `AUTO_REVIEW_ELIGIBLE` through the existing permitted ingress **only when that optional machine host is independently enabled**; incomplete source => HOLD. The attended CEO Web waiver is a separate author workflow, not a signed machine-skip token. Every assessment and positive dispatch advice is now tied to **repository, PR number, and exact 40-character head SHA**, with a mandatory matching signed-event identity and a **fresh current GitHub App PR read after the full census**. Head movement after classification, cross-PR reuse, missing current source, draft/fork drift or mismatched head => HOLD, never skip. The `advise_current_pr_review` helper performs source census, final current read and dispatch as one bounded read-only path; the signed host/authority must supply the arguments, never the PR author. An authenticated explicit manual review intent retains the original permission-gated path even if the source would ordinarily be FAST. This preflight is not connected to #1977's live host yet. Its binding must reuse the existing `GitHubReviewAPI` installation, source reader, signed receiver, Runtime ledger, and original exact command identity, not add a second review scheduler.

## Risk classification evidence and adversarial rules

The owner supplies complete changed filenames, additions/deletions and a verified exact current GitHub PR head. Diff coverage must include renames/deletions, not only visible excerpts. Agent PR descriptions, labels, comments, Markdown risk declarations, branch names and model claims **cannot lower** the tier. Allowed trusted source-owner hints can only escalate. Invalid paths, case aliases, stale heads, partial pagination or unverified files produce HOLD, not FAST. Small one-line edits to auth, release controls, charter/doctrine, strategic contracts, packet-gate, governance, or protected rules remain CRITICAL; they must not become automatic STANDARD skips merely because a path lacks the words `security` or `policy`.

Deterministic path patterns are conservative, not exhaustive semantic proof. A file ending in `.md` does not itself qualify as passive evidence; canonical operator/source-law documents in `docs/sol_*`, `docs/session_*`, `docs/executive_*`, `docs/agent_*`, `docs/github_*`, `docs/review_*`, installable `skills/` and `plugins/`, and test/CI control paths are CRITICAL. Unknown operational documentation remains STANDARD. Read-only user guides and verified visual evidence retain FAST eligibility. Existing CI security scans, test suites and source-code ownership constraints remain. Before a FAST release, the responsible builder must confirm that the diff really is reversible/routine and does not covertly alter a trust boundary, product decision, money/trading operation, external interface, migration or production data. Any actual contradictory evidence escalates the tier; lack of certainty means HOLD. The pure classifier cannot inspect code semantics and **must not be connected directly to a privileged auto-merge endpoint as an authorization oracle**.

**Evidence-aware scope budget:** Authenticated per-file stats distinguish executable changes from accompanying screenshots, documentation and verification logs. Executable tests, pytest/CI enforcement and installable agent skills are **not** considered inert supporting evidence: CI-policy tests, conftest, policy/configuration and skill instructions are protected even for one-line edits. Regular tests default to STANDARD until a separately trusted semantic qualification exists. A future semantically qualified UI/icon edit need not be escalated merely because its PR carries many large proof artifacts; the source collector requires complete pagination and matching additions/deletions, and its file metrics must cover every current and renamed prior path. Missing metrics revert to conservative aggregate counting. File deletions and high-risk security/source-law paths still escalate even when surrounded by evidence. This is not an author-controlled `skip-review` label or a semantic safety guarantee.

An attended CEO Web review is requested **only** when an actual native/security requirement or an explicit eligible manual request warrants it; risk tier alone creates no attended reviewer operation. The separate default-OFF signed machine may use its existing admitted risk-tier review path. Manual `independent-review` requests still use existing signed GitHub ingress and its source/identity controls. For a *new* review, preserve original builder/reviewer separation and one PR-head/scope operation: never spawn a new Fabric, Slack Dot or Cursor reviewer just because the first is queued, unconsumed, declined, uncertain or already reviewed. A changed head invalidates only review evidence that no longer covers the changed source; whether a formal approval remains valid follows GitHub's actual branch rules. Do not fabricate exact-head reviewer coverage.

## How this avoids administrative stalls

1. **Batch logically related tiny changes into a coherent PR**, not one PR per line or test fixture. Do not batch unrelated owners/sensitive paths just to avoid review.
2. **No universal independent reviewer in attended CEO Web.** FAST/STANDARD/CRITICAL do not create a default additional reviewer handoff, Dot ACK, Fabric commission or second top-level chat. Actual native/security gates remain.
3. **Do not require Astra/Opus/Fabric reviewers to ship ordinary attended source.** FAST retains static CI, STANDARD smoke/integration proof and CRITICAL targeted security/product proof. Manual expert review remains optional when explicitly authorized.
4. **Parallelize required CI and useful independent work** while holding real pending checks at the protected merge boundary. Never create duplicate review jobs, fictitious observers or CI exemptions.
5. **Use post-merge sampling**, provisionally 5–10% of source-verified FAST PRs, to discover classifier misses without stalling every merge. Sampled findings flow to the existing issue/defect owner, not a new reviewer state machine. Measure escapes and expand risk rules only on actual evidence.
6. **Preserve protected deployment gates.** Significant production changes still require service-path acceptance; routine source-only changes do not trigger irrelevant deployment review or reboot.

## Rollout / proof (not satisfied by a source PR)

- Pass unit tests including sensitive one-line changes, incomplete source, forged hints, duplicate paths and elevated test deletions.
- Run read-only classification over a real mixed recent-PR cohort from Mastermind, Macro and Terminal. Manually adjudicate false FAST classifications; report proportion of eligible changes and reviewer time saved only from observed receipts.
- Reconcile source-law wording in `docs/sol_skills/ACTIVE_EXECUTION.md`, `docs/CEO_PROJECT_PLAN_CONTINUITY.md`, `AGENTS.md`, `CLAUDE.md` and native consumers without overwriting in-flight compaction PR #1967. Do not claim acceptance from this document alone.
- #1977 signed host source is now protected-merged; use its existing installed ingress only after separate authorization and canaries, retaining default OFF and signed FAST skip versus signed STANDARD/CRITICAL admission. No additional host/queue or cross-carrier retry of refused review intent.
- Verify actual GitHub rulesets / branch protection with administrative readback for each repo. A 403 on the branch-protection endpoint means UNKNOWN, not zero. Update a rule only by its authorized admin owner after a separate compatible source release; never use bypass to test.
- Prove protected merge/CI, per-account installed instructions, and a genuine attended-Web release without blanket reviewer. Optional signed-machine activation, if separately authorized, requires FAST skip, STANDARD/CRITICAL admission, MANUAL unchanged, HOLD refusal and original-host rollback canaries. No machine activation or Project settings save is claimed by source-only tests.
