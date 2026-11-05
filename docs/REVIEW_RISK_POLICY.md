# Risk-tiered PR review — lower friction without removing real safeguards

**Status:** The #1989 baseline and #2030 Chairman-directed attended-Web all-tier waiver / safe CI-risk composition are protected-merged (#2030 merge `68e3b816c95930f6996dbcc10403a6ad694e6889`). ChatGPT Project settings save/readback and fresh-session behavior remain NOT_PROVEN; the distinct signed AUTOMATIC review host remains OFF unless separately enabled. This source grants no GitHub rule, approval, merge bypass or independent runtime authority.

**Owner:** Existing GitHub release workflow + `control_plane/github_release_assessment.py` (approval adjudication), Executive/Fabric (admission and independent results), and native branch rules/merge queue (enforcement). The pure `control_plane/github_review_risk_policy.py` only supplies a reproducible advisory risk tier. No new webhook, queue, reviewer registry, auth store, code owner, worker budget, retry process or release engine.

## One proportionate qualification across assigned sessions

Ordinary reversible FAST/STANDARD source changes use session self-check, affected tests
and normal protected release automation, with **zero** independent technical reviews
and **zero** additional formal approvals. Consequential native/automated changes mean the full CRITICAL row below:
auth/security/permissions, source authority, review/release automation, privileged CI, financial execution, irreversible data and exactly-once. They need **one** distinct native/Fabric technical review. Review finding repairs only for the affected delta, without a second
release operator. The attended CEO-Web all-tier self-review waiver remains: a tier label
alone does not require an independent reviewer there. Preserve stronger tests and required
real-path proof for stronger consequences.

| Tier | Source signals | Automatic technical assessments | Additional formal approvals | Handling |
| --- | --- | ---: | ---: | --- |
| **FAST** | Verified passive guides/evidence only; executable changes excluded | **0** | **0** | Static CI eligibility; no automatic review Job |
| **STANDARD** | Ordinary application/UI/backend/test code and reversible contracts | **0** | **0** | Affected checks and executable smoke; no automatic review Job |
| **CRITICAL** | Auth/security/permissions, source authority, review/release automation, privileged CI, financial execution or irreversible state | **1** | **0** | One distinct technical assessment for native/automatic work; stronger correctness/security proof |
| **HOLD** | Incomplete or inconsistent source, identity or effect uncertainty | Not inferred | Not inferred | Reconcile the original source/effect; never auto-exempt |

The source classifier stays conservative; this change lowers review counts, not risk
classification or CI coverage. Counts are internal assurance only. Actual GitHub rulesets,
CODEOWNERS, required CI, explicit release/security holds and original effect controls
remain independently binding. Obtain formal authenticated non-author GitHub `APPROVED`
only when an actual enforced rule or specific hold requires it; a technical Fabric PASS
is not that event. The assigned session may request release of its own qualified change
through the existing protected automation. No blanket non-author arming ceremony remains.
Never self-approve, impersonate independence or use an admin/protected-rule bypass.

The signed AUTOMATIC host stays OFF until separately enabled. This source change does not
install a host or alter branch protection. Source-verified FAST and STANDARD skip the
existing review ingress before Job creation; CRITICAL remains eligible for its one review.
Authenticated explicit manual review retains its original path. No author assertion,
label, branch name or prose can lower a tier or forge a zero-count critical assessment.

## Exact-head source verification and pre-admission disposition

The additional pure `control_plane/github_review_risk_source.py` requires an **existing authenticated installation-scoped GitHub reader** to supply one current PR identity, every bounded changed-file page, and a second identical current PR read. `integrations/github_review_risk_reader.py` now supplies a narrow concrete adapter backed by the incumbent `GitHubReviewAPI`'s existing installation-token-scoped read transport; no second client, key, webhook or GitHub endpoint owner is introduced. Its read-only hermetic suite verifies whole-source-to-dispatch outcomes and refused malformed identities. The incumbent #1977 host must still install and call this read seam after signed webhook authority and before Executive admission. It refuses incomplete pagination, inconsistent totals, changed heads/base, forks, drafts, missing code patches, and missing original paths for renames. Deleted files escalate the risk tier; renamed files are assessed at both their old and new paths. These inputs are **not** permission or a GitHub credential source by themselves.

The pure `control_plane/github_review_risk_dispatch.py` is the integration seam: verified signed AUTOMATIC origin + FAST/STANDARD => `SKIP_NO_REVIEW_NEEDED` **before Executive creates a review Job**; authenticated AUTOMATIC CRITICAL => original review ingress only if the optional host is independently enabled; incomplete source => HOLD. Tier labels preserve substantive consequence/risk classification. Every assessment and positive dispatch advice is now tied to **repository, PR number, and exact 40-character head SHA**, with a mandatory matching signed-event identity and a **fresh current GitHub App PR read after the full census**. Head movement after classification, cross-PR reuse, missing current source, draft/fork drift or mismatched head => HOLD, never skip. The `advise_current_pr_review` helper performs source census, final current read and dispatch as one bounded read-only path; the signed host/authority must supply the arguments, never the PR author. An authenticated explicit manual review intent retains the original permission-gated path even if the source would ordinarily be FAST. This preflight is not connected to #1977's live host yet. Its binding must reuse the existing `GitHubReviewAPI` installation, source reader, signed receiver, Runtime ledger, and original exact command identity, not add a second review scheduler.

## Risk classification evidence and adversarial rules

The owner supplies complete changed filenames, additions/deletions and a verified exact current GitHub PR head. Diff coverage must include renames/deletions, not only visible excerpts. Agent PR descriptions, labels, comments, Markdown risk declarations, branch names and model claims **cannot lower** the tier. Allowed trusted source-owner hints can only escalate. Invalid paths, case aliases, stale heads, partial pagination or unverified files produce HOLD, not FAST. Small one-line edits to auth, release controls or protected rules remain CRITICAL. Ordinary backend/frontend/test changes are at least STANDARD even for tiny patches, because the accepted #2016 CI scope maps FAST to static-only mode and STANDARD to executable smoke. This CI decision is separate from the no-mandatory-review policy for attended CEO Web work. Privileged paths and risk exclusions still elevate.

Deterministic path patterns are conservative, not exhaustive semantic proof. A file ending in `.md` does not itself qualify as passive evidence; canonical operator/source-law documents in `docs/sol_*`, `docs/session_*`, `docs/executive_*`, `docs/agent_*`, `docs/github_*`, `docs/review_*`, installable `skills/` and `plugins/`, and test/CI control paths are CRITICAL. Unknown operational documentation remains STANDARD unless it qualifies under the bounded ordinary source rule; canonical governance and installable instructions remain CRITICAL. Read-only user guides and verified visual evidence retain FAST eligibility. Existing CI security scans, test suites and source-code ownership constraints remain. Before a FAST release, the responsible builder must confirm that the diff really is reversible/routine and does not covertly alter a trust boundary, product decision, money/trading operation, external interface, migration or production data. Any actual contradictory evidence escalates the tier; lack of certainty means HOLD. The pure classifier cannot establish code semantics: path and size heuristics can misclassify risk, so sample defects, escalate contradictory evidence and never infer production acceptance from FAST. It **must not be connected directly to a privileged auto-merge endpoint as an authorization oracle**.

**Evidence-aware scope budget:** Authenticated per-file stats distinguish executable changes from accompanying screenshots, documentation and verification logs. Executable tests are **not inert supporting evidence** and never qualify for static-only FAST, even if they add one line. Pytest/CI enforcement and installable agent skills remain protected even for one-line edits. Large test removal over the separate 50-deletion budget is STANDARD. Ordinary bounded UI/code and tests remain at least STANDARD, not CRITICAL merely because a PR carries large inert proof artifacts. The source collector requires complete pagination and matching additions/deletions, and its file metrics must cover every current and renamed prior path. Missing metrics revert to conservative aggregate counting. File deletions and high-risk security/source-law paths still escalate even when surrounded by evidence. This is not an author-controlled `skip-review` label or a semantic safety guarantee.

An attended CEO Web session requests a review **only** for an explicit eligible manual request or a separately binding native/security approval requirement; risk tier alone never requires an attendee to create a reviewer operation. The distinct, default-OFF signed AUTOMATIC host may admit CRITICAL reviews under its own authenticated policy if separately activated. Manual `independent-review` requests retain the existing signed GitHub ingress and source/identity controls. For a *new* review, preserve original builder/reviewer separation and one PR-head/scope operation: never spawn a new Fabric, Slack Dot or Cursor reviewer just because the first is queued, unconsumed, declined, uncertain or already reviewed. A changed head invalidates only review evidence that no longer covers the changed source; whether a formal approval remains valid follows GitHub's actual branch rules. Do not fabricate exact-head reviewer coverage.

## How this avoids administrative stalls

1. **Batch logically related tiny changes into a coherent PR**, not one PR per line or test fixture. Do not batch unrelated owners/sensitive paths just to avoid review.
2. **No universal independent reviewer in attended CEO Web.** The automatic machine host remains OFF; if expressly enabled, signed CRITICAL may use its existing one-Job path. Explicit manual review is optional and one-operation-only; never duplicate reviewer work.
3. **Do not require an Astra/Opus/Fabric review to ship CEO Web code.** FAST needs focused tests, STANDARD integration proof, CRITICAL targeted security and production-path proof. When explicit expert review is independently authorized, use the original least-scarce capable avenue.
4. **Parallelize required CI and other useful work**; an unsatisfied check blocks merge, not the whole CEO session. Never fabricate an independent reviewer as a default prerequisite.
5. **Use post-merge sampling**, provisionally 5–10% of source-verified FAST PRs, to discover classifier misses without stalling every merge. Sampled findings flow to the existing issue/defect owner, not a new reviewer state machine. Measure escapes and expand risk rules only on actual evidence.
6. **Preserve protected deployment gates.** Significant production changes still require service-path acceptance; routine source-only changes do not trigger irrelevant deployment review or reboot.

## Rollout / proof (not satisfied by a source PR)

- Pass unit tests including sensitive one-line changes, incomplete source, forged hints, duplicate paths and elevated test deletions.
- Run read-only classification over a real mixed recent-PR cohort from Mastermind, Macro and Terminal. Manually adjudicate false FAST classifications; report proportion of eligible changes and reviewer time saved only from observed receipts.
- Reconcile source-law wording in `docs/sol_skills/ACTIVE_EXECUTION.md`, `docs/CEO_PROJECT_PLAN_CONTINUITY.md`, `AGENTS.md`, `CLAUDE.md` and native consumers without overwriting in-flight compaction PR #1967. Do not claim acceptance from this document alone.
- Keep the existing GitHub/Executive **automatic review host OFF** for this no-mandatory-review policy. Its unfinished Executive socket binding is not a prerequisite for eliminating reviewer handoffs. If a separately authorized administrator later enables manual/optional review ingress, integrate this policy into original #1977 and prove signed FAST skip, STANDARD skip, CRITICAL existing authorized machine review admission, explicit MANUAL routing and HOLD refusal before arming. No denied-handler replay or second ingress.
- Verify actual GitHub rulesets / branch protection with administrative readback for each repo. A 403 on the branch-protection endpoint means UNKNOWN, not zero. Update a rule only by its authorized admin owner after a separate compatible source release; never use bypass to test.
- Prove the no-review release path with protected CI, native rule readback, approved instructions loaded in real CEO sessions and one genuine PR reaching protected merge without a fabricated reviewer. The automatic-review host remains OFF, so it owes **no production webhook canary** for this waiver. If optional ingress is separately activated later, it must first prove signed FAST/STANDARD => zero Jobs, CRITICAL => one existing authorized Job when admitted, HOLD refusal, manual ingress and rollback. Never claim optional review-host production proof from source tests.


## Historical accepted #2030 rationale: attended-Web waiver and #2016 CI

A prior 20-PR path-only sample showed that the legacy FAST classifier excluded
most executable source. That motivated removing blanket attended-Web reviewer
handoffs across **all** tiers rather than using FAST as a false exemption.
The accepted #2016 CI qualifier consumes the same risk tiers: FAST selects
static-only checks; STANDARD preserves executable smoke tests. That historical
baseline restricts FAST to verified passive files and keeps even tiny
ordinary code and test changes at least STANDARD, preserving stronger CRITICAL
trust-boundary classification. The signed automatic review host is separate
and default OFF. The historical Web-only scope is superseded for native/automatic
work by the current proportionate-qualification section above. The attended Web
all-tier waiver remains; source verification, CI, release controls, holds and
production proof remain.
The original path sample was diagnostic, not a measured production KPI.

There is no universal reviewer handoff after each patch, commit, fix, test,
or CEO task. Review occurs only on an explicit authorized request or actually binding native requirement.
The signed #1977 consumer is optional infrastructure, not a required
reviewer or release dependency; leave its automatic policy OFF. A future opt-in
must use its original authorized writer and signed canaries, never the
previously denied Executive handler edit. Source text does not change live
ChatGPT Projects: an authorized editor must save the accepted compact kernel
and verify each intended account in a fresh session.
