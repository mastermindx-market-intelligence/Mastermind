# Risk-tiered PR review — lower friction without removing real safeguards

**Status:** Proposed source policy for Chairman directive 2026-11-02. Not an installed GitHub rule or an approval/merge bypass. It becomes operative only after protected acceptance, alignment with source-law/instruction consumers and host enrollment. This document has no separate source of runtime authority.

**Owner:** Existing GitHub release workflow + `control_plane/github_release_assessment.py` (approval adjudication), Executive/Fabric (admission and independent results), and native branch rules/merge queue (enforcement). The pure `control_plane/github_review_risk_policy.py` only supplies a reproducible advisory risk tier. No new webhook, queue, reviewer registry, auth store, code owner, worker budget, retry process or release engine.

## Default: stop requiring a second person or agent for small ordinary work

Independent review is **not** a default prerequisite for every minor edit, every commit, every child build, every test update or every PR head. Qualify the *coherent change* once, at its source-verified exact revision, and apply the **smallest justified external review requirement**. The author still self-checks the diff, runs focused tests and required hosted CI, preserves honest evidence and must not approve or merge their own protected change.

| Tier | Source signals | Independent technical assessments | New non-author formal approvals required by **this policy** | Handling |
| --- | --- | ---: | ---: | --- |
| **FAST** | Verified current diff; only ordinary docs/assets/tests, or routine code up to 200 changed lines and 8 files; no sensitive paths or escalation signal | **0** | **0** | Self-check + focused tests + required CI. Let existing authorized sweeper/native queue progress; no mandatory Fabric request or Dot ACK |
| **STANDARD** | Meaningful runtime/contract/data logic; medium refactor; dependencies, schema or risk-adjacent code; or over FAST size threshold | **1** | **1** | One suitably qualified independent review of the coherent candidate, not one review per commit or file |
| **CRITICAL** | Auth, security, permissions, secrets, authority/source-law, review/merge automation, privileged CI, release/deployment, trade or financial execution, irreversible state changes | **2** | **1** | Two independent technical perspectives (different model family/provider when justified), at least one genuine non-author formal approval, targeted security/behavior tests |
| **HOLD** | Complete exact-head source not proven, changed-path coverage missing, inconsistent metadata, identity/effect uncertainty | **Not inferred** | **Not inferred** | Reconcile the source or effect through its incumbent owner. No auto-exemption, duplicate reviews, merge or safety fallback |

The counts above are **additional policy demands**, not permission to reduce a higher native GitHub ruleset, CODEOWNERS, release hold or separately accepted security review. A technical Fabric `PASS` or GitHub `COMMENT` does not become `APPROVED`. If a native rule requires an approval even on FAST, that native rule governs until its legitimate owner amends it. Never silently admin-bypass. The merge actor must remain authorized and independent from the source author under applicable protected law.

## Risk classification evidence and adversarial rules

The owner supplies complete changed filenames, additions/deletions and a verified exact current GitHub PR head. Diff coverage must include renames/deletions, not only visible excerpts. Agent PR descriptions, labels, comments, Markdown risk declarations, branch names and model claims **cannot lower** the tier. Allowed trusted source-owner hints can only escalate. Invalid paths, case aliases, stale heads, partial pagination or unverified files produce HOLD, not FAST. Small one-line edits to auth, release controls or protected rules remain CRITICAL.

Deterministic path patterns are conservative, not exhaustive semantic proof. Existing CI security scans, test suites and source-code ownership constraints remain. Before a FAST release, the responsible builder must confirm that the diff really is reversible/routine and does not covertly alter a trust boundary, product decision, money/trading operation, external interface, migration or production data. Any actual contradictory evidence escalates the tier; lack of certainty means HOLD. The pure classifier cannot inspect code semantics and **must not be connected directly to a privileged auto-merge endpoint as an authorization oracle**.

A review is requested **only** when its tier or an explicit eligible human request warrants it. Manual `independent-review` requests still use existing signed GitHub ingress and its source/identity controls. For a *new* review, preserve original builder/reviewer separation and one PR-head/scope operation: never spawn a new Fabric, Slack Dot or Cursor reviewer just because the first is queued, unconsumed, declined, uncertain or already reviewed. A changed head invalidates only review evidence that no longer covers the changed source; whether a formal approval remains valid follows GitHub's actual branch rules. Do not fabricate exact-head reviewer coverage.

## How this avoids administrative stalls

1. **Batch logically related tiny changes into a coherent PR**, not one PR per line or test fixture. Do not batch unrelated owners/sensitive paths just to avoid review.
2. **One review per substantive candidate**, not a mandatory separate worker review on every implementation subtask, tiny repair, test pass, comment, reviewer request or generated file. No duplicate worker work for the same head/scope.
3. **Do not require an Astra/Opus/Pro review for ordinary code.** FAST needs none. STANDARD uses the least-scarce qualified independent reviewer (economical GLM/MiniMax/Grok lanes where admitted). CRITICAL uses qualified diversified judgment where its assurance needs it; model variety without true independence is not evidence.
4. **Parallelize CI and review** for STANDARD/CRITICAL when candidate is stable, and keep subsequent unrelated source work moving. CI green is a merge gate, not a human attention lock. No busywork observers.
5. **Use post-merge sampling**, provisionally 5–10% of source-verified FAST PRs, to discover classifier misses without stalling every merge. Sampled findings flow to the existing issue/defect owner, not a new reviewer state machine. Measure escapes and expand risk rules only on actual evidence.
6. **Preserve protected deployment gates.** Significant production changes still require service-path acceptance; routine source-only changes do not trigger irrelevant deployment review or reboot.

## Rollout / proof (not satisfied by a source PR)

- Pass unit tests including sensitive one-line changes, incomplete source, forged hints, duplicate paths and elevated test deletions.
- Run read-only classification over a real mixed recent-PR cohort from Mastermind, Macro and Terminal. Manually adjudicate false FAST classifications; report proportion of eligible changes and reviewer time saved only from observed receipts.
- Reconcile source-law wording in `docs/sol_skills/ACTIVE_EXECUTION.md`, `docs/CEO_PROJECT_PLAN_CONTINUITY.md`, `AGENTS.md`, `CLAUDE.md` and native consumers without overwriting in-flight compaction PR #1967. Do not claim acceptance from this document alone.
- Integrate this policy into existing PR #1977 GitHub/Executive ingress **after** its source writer and effects are reconciled. The repo-policy auto-coverage mode must be held default OFF for FAST until the installed consumer provably skips them. No cross-carrier replay of existing review intent.
- Verify actual GitHub rulesets / branch protection with administrative readback for each repo. A 403 on the branch-protection endpoint means UNKNOWN, not zero. Update a rule only by its authorized admin owner after a separate compatible source release; never use bypass to test.
- Obtain independent policy-security review of this review-bypass-sensitive change, protected merge/CI, installed instruction and host proof, signed ingress canary with verified FAST skip, STANDARD review, CRITICAL handling, and downstream merge/rollback behavior. Production `PROVEN_LIVE` only after those receipts.
