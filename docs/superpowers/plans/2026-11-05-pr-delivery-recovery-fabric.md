# PR delivery recovery — bounded Fabric workers and protected releases

Status: active *source plan*, not installed automation or Executive admission.
Operation: `pr-delivery-recovery-20261105-sol-001`.
Owner: assigned Sol CEO; GitHub source and CI are authoritative. Protected Mastermind law pin: `cb390bfc5a4b85a59a1005bfd3824305a5a4bfee` (Skillpack v1.0.1, bootstrap major 1).
Observation: 2026-11-05 UTC; GitHub org search reported **1,482 open PRs**, **1,033 Draft**. This is a snapshot, not 1,033 completed changes.

## Outcome / DONE_WHEN

Sustain a *safe* GitHub-to-Fabric delivery loop that converts qualified, unfinished existing PRs into protected merged outcomes, without pushing risky drafts or claiming production deployment from green checks.

1. Machine-readable census across Mastermind, Macro and Terminal categorizes exact PR/head/author/Draft state, declared HOLD, active writer/worker, changed paths, local qualification, required checks, native review/CODEOWNERS, conflicts/base compatibility, and target consumer.
2. Bounded independent workers return source-linked findings and repairs under the **original PR/branch/effect carrier**. No duplicate PR, PR author, queue, authentication, Job/Attempt/Worker or reviewer registry. Actual admitted work and result consumption are separately receipted.
3. Readiness policy: `Draft` remains for incomplete or explicitly held changes; `Ready` is eligible only after evidence of stable candidate, affected tests and no binding Draft hold. CI *pending* alone is not a Draft hold. The existing `github_review_intent.py` refuses `review_requested` while Draft; never request before Ready and assume it replays.
4. Protected release uses **existing** per-repository policy: Macro's scheduled `merge-on-green` (opt-in, existing hold/semantic/release gates) and native GitHub queue/rules where actually enabled. No blanket arming, automatic un-draft of 1,033 PRs, forced merge, author self-approval, admin bypass or deploy. No new controller.
5. Exact merged SHA, native integrated checks and any owed live user path are recorded independently of PR Draft, CI, merge, or watcher status. Measure merged/closed-superseded/accepted outcomes and time-to-release, not PRs created.

## Canonical integration and active collisions

- `WS:CI-MERGE-CONTROL-PLANE`, Macro `.github/workflows/merge-on-green.yml` and `scripts/merge_on_green.py` own the existing Macro sweeper, rate/backpressure and merge safety.
- [Mastermind #2064](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2064) owns live review-risk/FAST-STANDARD policy, Project instructions and CI review-parity files. Do **not** shadow-edit them.
- [Mastermind #2066](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2066) owns the in-flight Web/Fabric durable orchestration, finite watcher and Wake continuation integration; preserve its child `web-fabric-autonomy-finite-repair-20261105-c3-02`. Do **not** duplicate or replace it.
- [Mastermind #2063](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2063) owns browser attention/watch paths. [Macro #10746](https://github.com/mastermindx-market-intelligence/macro/pull/10746) owns Macro source review-policy entrypoints. These are independent incumbents.
- Current GitHub login observed `MastermindX1`; login alone grants no alternate identity, reviewer independence, CI bypass or release authority. Source branches/holds remain with their real current owners.
- Executive reader reported `backend_unavailable` on 2026-11-05 UTC; do not infer Runtime admission or a daemon from GitHub/Fabric capability docs. The attended Fabric adapter returned `adapter_available=true`, but worker admission/START were UNPROBED.

## Phases and bounded tasks (editorial only; not Executive lifecycle state)

| ID | Objective / dependency | Actual completion evidence |
| --- | --- | --- |
| P0 | Freeze source/authority, audit candidate risk and collision; before worker launch | This plan and protected pin read back from GitHub, no active incumbent overwritten |
| P1.M | **Macro census worker**, read-only, excluding known explicit HOLDS and active writer effects | Exact-head 8–15 candidate PR table; separate qualified/CI-red/review/held/uncertain with source URLs and safest next owner action |
| P1.T | **Terminal census worker**, read-only, independent of Macro | Same; Terminal native rules and exact PR checks, no assumed Macro label |
| P1.S | **Mastermind census/integration worker**, read-only, distinct from #2064/#2066 owners | Same plus evidence of current Review/Draft ingress and already-installed webhook host vs SPEC_ONLY |
| P2 | Sol adjudicates worker returns; choose first eligible original-PR repair or metadata transition; source custody reviewed | One real original PR/head advanced with before/after evidence, no duplicate worker/effect |
| P3 | Extend **incumbent** GitHub/Executive ingress only if confirmed missing behavior and disjoint owner/custody; build tests | Webhook or scheduled native checks classify and return actionable state; conservative holds; original queue owns writes |
| P4 | Qualify existing protected merge route on a small, explicitly authorized pilot, no bulk arming | Real native rule/CI/review/hold readback, exact merged SHA and consumer proof when owed |
| P5 | Measure delivery throughput/backlog aging by repo, preserve existing owner recovery | Repeated real merged outcomes with no misclassified hold, accidental duplicate, or false release claim |

## Initial worker packet / budget

`ROUTE`: lowest-scarce admitted paid Fabric workers, AUTO model/pool selection; task class `census`, C1 or C2 on actual complexity. `WHY NOT FABLE`: frozen read-only repository/CI inventory and candidate classification require no principal architectural judgment. `FRONTIER_WITNESS`: none.

Parent operation/root `pr-delivery-recovery-20261105-sol-001`; children must preserve root and actual parent identity. Fabric handles are *not* Executive Job IDs. No provider/model/host pin, no inferred credentials or quota. Reserve review/repair capacity; start only as many independent workers as can actually be admitted. Their first task is read-only and may not mark Ready, relabel, request reviews, push, merge, deploy, spend or mutate any source/PR. If worker requires modifying GitHub access, it must return the exact change proposal for original-source custody/admission first.

## Draft classification contract

`INCOMPLETE` — missing source/test/consumer acceptance; name owner and repair.
`HELD` — explicit security/release/research/test/prod/stacked hold; do not transition.
`REVIEWABLE` — stable scoped candidate, local proof, no binding Draft hold; CI may be pending; Ready candidate only after current source/custody readback.
`CI_RED` — actual required check failure; exact run/logs; repair original carrier.
`REVIEW_BLOCKED` — actually mandated native/CODEOWNERS independent approval absent, or earlier Draft-only review request never admitted.
`INTEGRATION_BLOCKED` — real conflict/material base delta or required integrated gate missing, not just ancestry.
`UNKNOWN` — insufficient current-head source, lease, installed host or release-policy evidence; no optimistic release action.
`SUPERSEDED_CANDIDATE` — exact later merged equivalent proven; classify for independent owner disposition, no automatic closure.

Each candidate record must include `repo`, `PR`, `head_sha`, `updated_at`, `draft`, `classification`, `hold_quote/link`, `required_check_summary`, `formal_review_summary`, `writer/effect_uncertainty`, `next_owner_action`, and `evidence_urls`. Missing evidence stays UNKNOWN.

## Real-path acceptance / rollback

Initial source plan is safe even if Fabric or Executive is down. A PR alone is not an operating continuous-delivery system. Before activation, verify webhook/schedule installed, proven worker admission + result + parent consumption, safe rate/budget/backpressure, GitHub native rule checks, negative tests (held, draft, stale head, conflict, red CI, review revoked, API unavailable, interrupted effect), and one positive exact-head protected landing. If current checks refuse, leave source open or Draft with exact blocker, advance independent work, and never bypass safeguards.

This plan does not change production config, deploy, trigger arbitrary CI, create a new queue/app, or grant automatic permission to release held PRs.


## P2 implementation and end-to-end design refinement — 2026-11-05

Parent/root remains `pr-delivery-recovery-20261105-sol-001`. The continuation workspace operation is `pr-delivery-completion-20261105-sol-001`, not a replacement Runtime root. Source pickup: `f374289eb74587eaa755f5bc8e5a3252d00850e0`. The protected governing pin `cb390bfc5a4b85a59a1005bfd3824305a5a4bfee` remains compatible: the intervening comparison contains no governing-law change. Current outer Chairman direction requests complete implementation using the existing fleet and paid Fabric.

### Reconciled facts, not completion by implication

- Original readiness source #2074 is merged at `c3c1199893dae01ef40072add030b2d7afe13847`, 2026-11-05 07:14:56 UTC. It is an advisory source component, not an installed autonomous service.
- All three original `.macro-census-01`, `.terminal-census-01`, `.mastermind-census-01` runs returned terminal failure rc75 and no retained result. The original Macro controller records a 3,600-second MiniMax lease wait then LEASE_REFUSED. They remain original failed operations, not replaced workers. Missing root attestation and `retry_allowed=false` are preserved.
- A NEW bounded repair `.active-workstate-contract-02` has obtained its own lease and remote launch on Ubuntu3 via the incumbent AUTO router (controller78828). A launch is not accepted code. Its two owned patch paths are `control_plane/github_pr_lifecycle.py` and `tests/test_github_pr_draft_readiness.py`; no source push, PR metadata, merge or deployment is delegated.
- Executive V3's reader returned `backend_unavailable`, request not sent, at07:27Z. The existing #1893 protected administrator-result and #2066 activation boundaries are not cleared by this plan. The installed Studio fleet-status observer separately returned FLEET_STATUS_OWNER_RESULT_INVALID; this is not evidence the fleet is offline.
- The previously denied M1 `integrations/github_pr_draft_intake.py` write is not repeated, renamed, or routed to another host/tool. This continuation's source work is the independent active-workstate classifier repair and the existing plan. No intake implementation is claimed.

### Design decision: extend incumbent owners, not install a competing bot

A second GitHub App plus a second repair queue would compete with Executive admission, repeat reviews and lose original effect custody. A cron that simply marks green Drafts Ready would confuse green tests with scope completion and release permission. The selected approach is the existing authenticated GitHub ingress/reconciliation and Executive/Fabric owners, composed with the repository's established protected release path. These are architectural decisions of the assigned principal; installed configuration is separately evidenced.

The completion cycle has six evidence boundaries:

1. **Observe:** signed GitHub lifecycle/check events plus the existing bounded open-PR reconciliation. Validate signature and installation/repository identity; treat PR bodies, comments and logs as data. Use GitHub's existing delivery identity and Executive's command uniqueness; no second deduplication store. Missed events and reconciliation must converge on the same exact-head work identity.
2. **Qualify:** trusted owners supply current PR/head, actual source completeness, scoped test evidence, writer/effect state and explicit holds. An active *programme* does not mean a source writer is modifying the candidate. `source_writer_active` remains independent and fail-closed. CI pending or a required review can block release without automatically blocking Ready.
3. **Admit bounded work:** the existing router and capacity broker select eligible workers within original root, grant, host and budget. A reserved controller is not a worker. Capacity wait/refusal must be visible. Do not hold a reasoning worker merely to poll CI, duplicate a failed/uncertain commission or silently turn a new ID into a retry.
4. **Repair and return:** retain original PR/source custody and immutable head inputs. Workers return exact patch/artifact bytes plus actual tests, not an instruction to trust a success claim. Re-read changed source and integrate through the original authorized publisher. A moved head invalidates only affected evidence but never authorizes overwriting another writer.
5. **Release:** freshness/holds/checks/native approval rules are re-read immediately before one existing protected queue/controller action. The source author cannot bypass protection or self-approve. Macro's explicit controller opt-in is not interchangeable with native auto-merge. GitHub `merge_group` proves the integrated candidate, not merely the old PR head. Changes-requested, unavailable policy/API and unknown effects stop that release edge.
6. **Accept:** read the actual merged SHA, then verify installed/deployed consumer behavior when the change owes it. Source-only work must not restart unrelated services. Persist results under GitHub/Agent OS and return through the original carrier; do not call ARMED, queued, green or merged equivalent to product acceptance.

The standing runtime stays default-off/unclaimed until its current configuration, authenticated ingress, admitted START, retained result, parent consumption and original-operation recovery are proven. The useful unattended consumer belongs to Executive; the temporary ChatGPT observer is not its substitute.

### Bounded execution tasks

- [ ] **P2.A — correct active-workstate liveness.** Paid child `.active-workstate-contract-02` must first show a real failing regression for ACTIVE programme + no active source writer + exact qualified head + complete scope + no Draft hold. Remove only the inferred-writer condition; preserve all actual writer, unknown, source, head, effect and explicit-hold checks. Existing lifecycle closure must still KEEP_ACTIVE. Parent verifies returned bytes and both lifecycle/readiness suites before source publication.
- [ ] **P2.B — independent fixture generation.** A distinct bounded mechanical child may produce a table of negative/positive test vectors for readiness and release separation, using only frozen input contracts. It is a test-data task, not an independent approval, source writer, census retry or dispatcher. Its return must distinguish unexecuted vectors from executed tests.
- [ ] **P3 — host composition.** Respect the denied intake action. The actual missing allowed interface/host permission must be resolved by its legitimate owner before that same intake operation can proceed. #2066 keeps its active continuation source and installed-owner gates. Do not shadow-edit its paths or replay protected administrative reads.
- [ ] **P4 — real pilot.** After permitted host composition, process one authentic current PR event through the installed ingress, original Executive/Fabric admission, bounded useful worker result, parent consumption and protected release; verify exact merged SHA and owed consumer behavior. The #2074 merge proves only the source-release portion, not the worker/event chain.
- [ ] **P5 — safe breadth.** Increase parallel ready work only when actual broker/host admission and parent consumption keep pace. Count terminal useful repairs, protected merges and accepted consumers separately; report waiting/refused workers and held PR reasons without hiding them in a total 'running' count.

### Acceptance falsifiers

Tests and canaries must reject or defer: wrong installation/repository, forged payload, duplicated delivery, head drift during qualification, explicit Draft/release hold, incomplete scope, active/unknown writer, unknown prior effect, invalid or revoked approval, unavailable required-policy data, missing or red required integrated checks, stale CI proof, capacity refusal, interrupted publication and missing real consumer proof. Positive cases must show a still-ACTIVE programme can have a qualified Ready candidate while its genuine merge/deployment obligations remain open.

Use existing finite budgets and controls. No policy count, timeout, workflow cap or permission is raised solely to improve a dashboard number. Stop only the exact temporary child source after terminal adjudication; preserve aggregate seat/program attention and all independent work.

Primary platform references checked 2026-11-05: GitHub Docs `webhooks/using-webhooks/best-practices-for-using-webhooks`, `webhooks/using-webhooks/validating-webhook-deliveries`, `repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue`, and `actions/reference/workflows-and-actions/events-that-trigger-workflows`. The implementation must use the actually installed API/permission contract, not a documentation statement as an access grant.


### P2 verification milestone — actual paid returns and parent integration

The original repair child `.active-workstate-contract-02` returned TERMINAL/rc0 with verified original root/parent and a complete retained response (11,802 bytes), SHA-256 `99e0258c4692a9b4f3b2c8d429189402b940200cb53aef27e1d35b4a4882fee1`. Its exact two-file diff was consumed, not replaced by a second worker. Worker-reported tests were 3 failed/67 passed before the minimal source repair and 70 passed afterward in its isolated Ubuntu3 lane. No protected source, PR, release or deployment effect was delegated.

The parent independently reproduced **3 failed / 67 passed** against unchanged source blob `78cc0158a25ee2ebbb6c911cb29daace6566e53d`, then integrated the one-condition repair and additional fixture coverage in the managed Studio workspace. Actual command:
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -o addopts= --tb=short -q -p no:cacheprovider tests/test_github_pr_draft_readiness.py tests/test_github_pr_lifecycle.py`
Result: **97 passed in 6.28s**, process exit0; `git diff --check` passed. This parent run included the repository conftest; it was not the earlier M1 `--noconftest` fallback and is still targeted, not a full-repository test claim. The old lifecycle closure tests remain unchanged and passing. The repair child's original result was accepted through `fabric_accept` with `by=deterministic`, `verification_summary=deterministic_test_evidence`; canonical readback returned accepted=true. This is source-result acceptance, not a separate technical reviewer or formal GitHub approval.

The independent mechanical vector child `.readiness-safety-vectors-03` returned TERMINAL/rc0 with verified root/parent, 4,056 bytes, digest `994d8b1df460bb1a035fa10fa3b7e220fc450b512a9b419511c95cd67632462d`. It truthfully declared its vectors unexecuted. Parent review found three malformed raw PR-state values (lowercase closed/merged and null), which do not satisfy the typed enum contract. The raw fixture set is **NOT_ACCEPTED as executable evidence**. Parent integrated the intended typed cases and three explicit malformed-input rejection tests; all ran in the 97-test result above. No silent normalization, reviewer PASS, rerun or new child was invented.

P2.A source implementation/targeted verification is complete; hosted exact-head CI and protected release remain outstanding until their actual receipts. P2.B generation and parent disposition are complete, with raw fixture acceptance rejected and useful corrected coverage verified. Source publication does not fulfill P3/P4/P5.

A bounded nonprivileged Executive diagnostic found the C1 Personal launch-agent is running through the installed `tunnel-client`; it did not establish the receiving backend socket/configuration or clear the returned `backend_unavailable`. No service, tunnel, policy, socket, credential, administrator-result hold or configuration was changed. The remaining intake permission and installed Executive/ingress consumer proof are still real gates, not solved by this source repair.
