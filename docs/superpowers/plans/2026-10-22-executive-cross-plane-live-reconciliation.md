# Executive OS ↔ GitHub ↔ Linear: Live Reconciliation Release Plan

**As of:** 2026-10-22 (fresh authenticated census around 19:34 UTC)  
**Owning organizational lane:** existing `WS:AGENT-OS`, with `WS:CHAIRMAN-CONTROL-ROOM` as read-only product consumer  
**Existing Linear parents:** [MAS-6](https://linear.app/mastermindx/issue/MAS-6), [MAS-27](https://linear.app/mastermindx/issue/MAS-27), [MAS-64](https://linear.app/mastermindx/issue/MAS-64), [MAS-66](https://linear.app/mastermindx/issue/MAS-66)  
**Source basis:** protected [Mastermind master](https://github.com/mastermindx-market-intelligence/Mastermind/commit/05f4765cdded00b86620b546b04e2dd339f82f72) `05f4765cdded00b86620b546b04e2dd339f82f72`, compatible Sol Skillpack `mastermind.sol_skillpack.v1` v1.0.1/bootstrap 1; Macro [main](https://github.com/mastermindx-market-intelligence/macro/commit/753f9b92287e32ee1c6b4b76b38ab153719b9e0a) `753f9b92287e32ee1c6b4b76b38ab153719b9e0a`.  
**Type:** census, design/implementation extension and gated release DAG; **not** a new program, projector, event service or independent authority. An unmerged plan is not protected acceptance.

## Mission and completion ruler

**Human job:** the Chairman opens Executive OS and sees a coherent, source-attributed, current company picture: which exact workstream is being implemented, PR/review/CI state, Linear projection, Executive Job/Attempt/Worker state, discrepancies, last observations, owner of the next action, and direct navigation to the authoritative source. An item never falsely turns Done merely because a contributing/architecture PR merged.

**Machine job:** reuse existing canonical APIs, authenticated native integrations and deterministic Session Truth to acquire exact identities and current owner observations, classify conflicts, and project **read-only** reliable cockpit cards. Separately, and only after its own app-actor/authority gates, apply authorized Agent OS desired-state changes to selected Linear **Project** fields via the existing P0/P1 projector.

**10/10 is not a PR merge.** It requires: authenticated live source reads with bounded freshness and coverage; reliable exact WS/MAS/repository/PR/operation links; typed disagreement visible on signed-in Executive OS; lost-event recovery and honest staleness; deterministic no-effect tests and hostile cases; one authorized Linear app actor and confined idempotent live project canary; independent reviews and source releases; signed-in desktop/mobile product proof; observable monitoring and recoverable failure.

## Canonical ownership and hard exclusions

| Fact | Only canonical owner | Executive UI/Linear behavior |
|---|---|---|
| Workstream, decision, handoff, completion proof law | Agent OS | Explicit exact-key join and projection; never infer from titles |
| Branch, PR, CI, review, merge, source implementation | GitHub | Read live; native Linear GitHub integration remains the only native PR/diff/review feed |
| Job, Attempt, Worker, admission, START, retry and execution effects | Executive Runtime | Read-only projection; queued/Slack-delivered never shown as executing |
| Selected portfolio and issue navigation | Linear | Semantic project projection only; may disagree with owners |
| Slack transport, notifications, dialogue | Slack | Visibility; not lifecycle or GitHub/Linear reconciliation authority |
| Reconciliation finding and context pack | Existing Session Truth / Context Fabric | Derived evidence, not a persisted source-of-truth plane |

**Do not build** a second PR mirror, GitHub webhook datastore, Linear diff object registry, sync cursor DB, retry queue, lifecycle state machine, identity registry, authority service or new workstream. No staff browser cookie/personal API key as projector credential. No silent provider/host/carrier failover, blind-effect replay, GitHub automation bypass or inferred cross-system identity. Slack Linear app [MAS-103](https://linear.app/mastermindx/issue/MAS-103) is intentionally deferred due workspace app capacity; **not** a blocker and not a reason to build a replacement bot.

## Evidence-backed current census

| Lane | State at observation | Owner/ref | Exact next constraint |
|---|---|---|---|
| Native Linear↔GitHub linkage | `PROVEN_LIVE`, **selective**; some sampled diffs have `linkedIssues: []` | [MAS-67](https://linear.app/mastermindx/issue/MAS-67) | Never infer links from title/branch; preserve native PR feed |
| PR/WS/MAS relationship validation | Report-only calibration accepted; corpus 92 real + 47 hostile | [MAS-28](https://linear.app/mastermindx/issue/MAS-28), Macro PR #8407 merged | No duplicate validator; use explicit completion semantics |
| Agent OS → Linear P0 | `BUILT_NOT_PROVEN` as live projection; deterministic zero-network compiler merged | [MAS-65](https://linear.app/mastermindx/issue/MAS-65), [Macro #6634](https://github.com/mastermindx-market-intelligence/macro/pull/6634), `scripts/linear_portfolio_plan.py` | Reuse canonical desired-state output, never recompile differently in Executive |
| P1 offline project diff | Existing [Macro PR #9919](https://github.com/mastermindx-market-intelligence/macro/pull/9919), **open DRAFT**, head `b033cd0a219bb725a79ce11e0af43a3d9e41aa31`; exact-head `fences`/ `ci` Actions runs SUCCESS; zero formal reviews observed | Same PR, 3 changed paths | Existing writer must obtain independent review, current-base release and acceptance; **do not duplicate or merge it here** |
| P1 data canary | Two scoped reads: 2 invalid managed blocks; 83 omitted/unbound; effects=0; separate 59-project census reported no P1 markers | PR #9919 body/source receipts | Do not reinterpret absent partial sample as missing/created projects; managed-block enrollment requires own gate |
| Credential host foundation | `BUILT_NOT_PROVEN`, protected source from MAS-188 | [MAS-188](https://linear.app/mastermindx/issue/MAS-188), Mastermind #218 merged | Does not create app/secret or grant Linear writes |
| macOS projector host repair | [Mastermind #1670](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1670), open DRAFT, head `56177dd0985ace59ee9dcfe1e9a71aa185d4ac2b` | Existing 3-file source carrier | Review/release and verify fresh-inode-only group normalization; no credential mutation until accepted |
| Dedicated Linear app actor | `NOT_BUILT` / exact external admin gate | [MAS-64](https://linear.app/mastermindx/issue/MAS-64) | One workspace-owned OAuth `actor=app`, verified scopes/team, protected host enrollment and isolated canary |
| P1 live adapter/apply | `NOT_BUILT` for authenticated project apply, despite offline preflight source candidate | [MAS-66](https://linear.app/mastermindx/issue/MAS-66) | Hold live mutation until MAS-64; optimistic re-read and idempotent one-project proof |
| Session Truth R1 | Accepted protected **source** for deterministic read-only receipts and findings | [MAS-177](https://linear.app/mastermindx/issue/MAS-177), Mastermind #170 merged; `control_plane/session_truth*.py` | Installed live owner adapters, freshness and cockpit consumer still need proof |
| Live acquisition / Context Fabric | Source present on protected master; CF PRs #1205/#1207/#1211/#1215 still open DRAFT / old heads | `session_truth_live_acquire.py`, `context_resolver.py`; [#1215](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1215) | Reconcile installed/current files and incumbent custody before touching any of their paths |
| Executive/Control Room | `PARTIAL`, not currently complete | `chairman_control_room.py`, `scripts/chairman_control_room.py`, [MAS-113](https://linear.app/mastermindx/issue/MAS-113), [MAS-218](https://linear.app/mastermindx/issue/MAS-218) | Current installed version, real signed-in path, source coverage and exact link needs proof |
| Installed Executive observation | 25 Jobs (3 QUEUED, 0 RUNNING); 33 Attempts (21 COMPLETED, 11 LOST, 1 FAILED); 1 Worker AVAILABLE at observed read | Existing Executive State read-only API | Job counts reflect Runtime only, not separate Fabric child/active browser session |
| Source freshness | Executive host Mastermind `80f384b8f58b7ca46422d9783aa5c0613c7bf4b2`, Macro `88804ed7079700c598bb8e04aa64307d1335402d`; remote SHA pins above newer | Executive State receipt | Active-build snapshot approximately **616h old**, open/merged PR windows TRUNCATED: must show stale/coverage-loss, not live green |
| Current Linear portfolio | **7 initiatives; 66 Projects including archived (59 In Progress, seven Completed); 64 one-to-one memberships; 2 unassigned; 0 multi-parent** | Two-page authenticated Projects reads both excluding and including archived projects, plus Initiatives read, matched using Project UUID, not display `P-MAS-*` ID | Unassigned: `WS:WATCHLIST-PORTFOLIO-CEO` and `Mastermind-X Linear OS`. Older 65/63 snapshot is historical; current active-only view is 59/57 |
| Chairman Linear views | Only currently read shared view: `Build Event Projection`; [MAS-95](https://linear.app/mastermindx/issue/MAS-95) Todo | Authenticated `list_custom_views`; existing view | Do not claim eight views configured; separate optional navigation delivery |
| GitHub→Slack build feed | Done/selected material events, visibility-only | [MAS-104](https://linear.app/mastermindx/issue/MAS-104) | Not a release, source-read or execution substitute |

**Direct M2 installed-file falsifier (read-only device inspection 2026-10-22 19:42 UTC):** The exact Executive-installed Macro source bundle at `/Library/Application Support/MastermindExecutive/macro-sources/88804ed7079700c598bb8e04aa64307d1335402d` contains `data/governance/active_builds.json` with `generated_at=2026-09-27T04:00:56.761089+00:00` and `data/governance/project_active_builds.json` with `collected_at=2026-08-11T13:24:20.082810+00:00`. Both files have filesystem modification time September 27 and are old observations inside the installed bundle. This corroborates the Executive's 616h staleness warning and additionally proves that the Project active-build file is older still. Reading the files did **not** refresh either one; no service, auth, source or process mutation occurred. R2 must inspect both consumers and prove a new source read from a qualifying installed runtime, not merely update one timestamp or copy the old bundle.

**Current disagreement:** MAS-66 leading description reports no P1 adapter/dry-run yet, whereas fresh GitHub #9919 contains an *unmerged source-only* offline diff candidate. This is a projection age/scope discrepancy, **not** proof that the real authenticated P1 apply exists. Historical 65-project counts in MAS-95 must not replace the fresh 59-project census. The Executive cached active-build feed is too stale/capped to prove current GitHub state. An inclusive live `includeArchived=true` inventory proves 66 total projects (59 In Progress, seven Completed), whereas active-only reads return 59; these populations must not be conflated.

## Implementation shape (extend existing owners only)

```text
Native GitHub + Linear integration ─── PR, review, CI, issue-link objects (already live)
GitHub canonical API  ─────────────┐
Agent OS direct records ────────────┤
Linear authenticated read ──────────┤  current injected read-only owner ports
Executive Runtime read API ────────┤  → existing strict snapshot normalizers
Slack optional transport read ──────┘  → existing Session Truth exact-scope/finding engine
                                          → Executive read-only workstream cards
                                          → existing Chairman Control Room / Context Pack

Agent OS source → existing linear_portfolio_plan.v1 (P0)
                → existing P1 offline diff (#9919, pending release)
                → dedicated verified MAS-64 app actor only
                → MAS-66 guarded project-only optimistic re-read/apply
                → authoritative post-read / receipt / idempotent noop
```

Each card carries exact `WS:<key>`, authored MAS/project bindings, canonical repo/PR/head, operation key if actually known, source owner and clock, remote GitHub CI/review/merge facts, Linear status, proof/acceptance relation, Executive Job state from Runtime only, typed findings with repair owner, and `UNKNOWN`/`STALE`/`TRUNCATED`/unavailable flags. No synthetic overall lifecycle. Unrelated PRs never join on title similarity. A missing `linkedIssues` is a visible missing relation, **not** permission to auto-link.

**Refresh semantics:** a native event/notification may *invalidate* an already selected card, but the new answer must come from a direct canonical owner re-read, never from event body as truth. Use existing approved service/refresh endpoints and scheduler/Runtime owner; do **not** create another worker, webhook daemon, persistent cursor or race-prone poller. Inspect the existing Control Room `/api/refresh-builds` process-memory path before modifications. If native push is not qualified, expose authenticated manual Refresh and an explicitly time-bounded existing-owner periodic re-read. On 429/transport outage/capped GitHub window, degrade by named source, preserve last-good as historical, never display green/current by default. The source clock must accompany each card and status transition.

## Frozen release DAG and acceptance evidence

### R0 — Baseline, ownership and collision fences (this census)

- [x] Resolve protected Skillpack SHA and live repo/source identities.
- [x] Inspect native Linear-GitHub, P0/P1, MAS-64/CRED0, R1/Context Fabric, Executive/CCR and selected current PRs.
- [x] Reconcile current Linear Projects/Initiatives using UUIDs.
- [ ] Reconcile any incumbent writer/effect before subsequent source mutation; preserve exact worker/PR carriers.
- [ ] Establish live installed Control Room build/hash, signed-in user-path and current data acquisition probe.

**Gate:** one evidence ledger showing source, timestamp, identity, coverage, freshness, owner and next lawful effect.

### R1 — Read-only Executive cockpit card consumer (parallel to app-actor gate)

- [ ] Finish the already submitted Fabric child **`exec-linear-gh-view-20261022-01`**, root `exec-linear-gh-20261022`, controller PID `14172`; preserve same run and root, **do not resubmit while active/unknown**. Its launch attempt is evidenced but START/worker return was unverified at this census.
- [ ] Consume existing Session Truth and typed findings, *not* raw unbounded GitHub/Linear blobs.
- [ ] Add stable exact-key card rendering and bounded diff, sources, clocks, coverage and conflicts.
- [ ] Prove false-green, missing issue links, mixed case/invalid ID, stale GitHub, stale Linear, unavailable owner, missing proof, merged contributing PR, queued-not-running, order invariance and no effects.
- [ ] Independent review and draft-source/CI/readback proof. Do not claim a live cockpit from pure tests.

**Owners:** Mastermind source worker/custody; Executive read-only product consumer. **Reserved paths:** worker's proposed `control_plane/executive_cross_plane_view.py` and `tests/test_executive_cross_plane_view.py`; no competing implementation in those paths.

### R2 — Current-source acquisition, coverage and installed Executive freshness

- [ ] Qualify `session_truth_live_acquire.py` injected adapters against authenticated actual owners at exact scope; compare open CF #1215 paths with protected source before any release movement.
- [ ] Replace reliance on stale/truncated `project_active_builds.v1` when making current UI claims: use an existing bounded refresh or a direct canonical read; publish refresh origin, GitHub pagination/cap and timestamp in view.
- [ ] Diagnose Control Room's live `/api/refresh-builds` source reader and source-pin mismatch; consume [Mastermind #1736](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1736) installed successor-config preparation without stealing its installer ownership.
- [ ] Exercise two-source invalidation/out-of-order observations, timeouts, 429s, loss of optional Slack, remote GitHub update and restart with explicit `STALE`/unavailable output.
- [ ] Prove installed runtime uses the new reviewed files and source SHAs; no unauthorized production deploy.

**Gate:** after controlled refresh, targeted cards show actual current GitHub head/CI, the exact Linear issue and authoritative Executive state, with demonstrably bounded staleness.

### R3 — Preserve and qualify existing P1 offline planner

- [ ] Incumbent owner handles [Macro #9919](https://github.com/mastermindx-market-intelligence/macro/pull/9919) independent review and latest-base merge/release through its **existing branch**, not a replacement.
- [ ] Verify negative marker cases, WS→immutable project UUID binding, full vs partial snapshot, 85 active desired WS vs 59 observed projects, 16 excluded, no invented creates, duplicate/archived IDs, field hash preimages, manual-description preservation, `effects=0`.
- [ ] Advance only the accepted offline slice; P1 live status remains held. Current-head CI green is necessary but not reviewer/production acceptance.
- [ ] Keep native Linear issue auto-Done associations out of contributing/documentation PRs; enforce explicit completion semantics with existing MAS-28 checks and project proof law.

### R4 — One dedicated app actor (the exact external administrator gate)

- [ ] Admin inspects existing Linear app inventory for one matching `Mastermind Portfolio Projector`; create/reconcile exactly one workspace-owned OAuth `actor=app` identity with `read,write`, scoped to `MastermindX` as currently contracted.
- [ ] Preserve the **already proven M2 host PREPARED** effect from the existing 2026-10-21 exact-root metadata/CLI receipt: root/config are root:wheel 0750, no `projector.json` or `oauth-client-secret`; **do not rerun prepare, chmod or chgrp**. [Mastermind #1670](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1670) is only the still-DRAFT permanent source repair for fresh-inode group inheritance. Enroll later solely via accepted MAS-188 native hidden-TTY root-owned credential path.
- [ ] Reconcile the separate **Linear Project `Paused` status gap** from the accepted source/canary record. This requires authorized workspace status configuration or a separately reviewed explicit semantic mapping; do not silently map canonical `parked` to `In Progress`. Read back actor/client identity, scope, team and host metadata without exposing secret content; then run isolated app-attributed create/read/update/noop/conflict/cleanup canary with explicit cleanup/effect proof.
- [ ] **No ChatGPT/employee key, copied cookie, Slack secret, GitHub secret, ad hoc HTTP bridge or actor impersonation.**

**Stop:** if workspace-admin app provisioning/credential ceremony is unavailable, this lane remains **EXACT_HUMAN_GATE**. It never holds R1/R2 read-only work.

### R5 — MAS-66 bounded semantic project apply

- [ ] Implement the *existing* P1 actor-bound remote read/diff/apply contract over P0 and reviewed R3 planner, not an independent compiler.
- [ ] Strict project allowlist/authored mapping, optimistic remote preimage re-read and compare-and-swap; one selected project's exact permitted fields and managed block only; no issue comments/archives/bulk auto-create.
- [ ] Serialize one modifying operation per target with same-carrier effect/readback. Recover unknown effects before retry and prove identical input gives zero-op; protect unrelated manual fields and non-managed blocks.
- [ ] Compare remote post-read to expected output; emit exact receipt, conflict/refusal and partial-failure case. Verify 0 false completion/lease mutation across hostile controls.
- [ ] Only after canary acceptance propose gated expansion across explicitly mapped projects; never infer authority from PR merge.

### R6 — Live event/freshness and product integration

- [ ] Wire read-only R1/R2 cards into existing Executive Control Room/Steward; include source status, direct repo/PR/Linear links, *last verified* evidence and manual refresh.
- [ ] Leverage qualified existing push/invalidation when available; otherwise approved existing-owner bounded refresh (no new daemon) with source-as-of. Target **p95 <=60s** for qualified native event→fresh card and **<=15m** lost-event convergence after accepted scheduler integration. These are *targets to measure*, not claims of current performance.
- [ ] Explicit stale threshold and transport/backoff policies; replay 24h owner-event traces with duplicates, reordering, missing pages, links absent and delayed CI. Exactly one joined card per explicit identity, no  false-green.
- [ ] Signed-in Chairman journey: click a workstream → view exact GitHub candidate/CI/review → see Linear projection and any drift → inspect Executive Job truth → navigate owner/action; verify desktop and responsive mobile. Capture real screenshot/network/source/readback receipts, not synthetic fixture proof.

### R7 — Adoption, calibration and closeout

- [ ] Audit sample of active + completed + unresolved projects against current GitHub/Linear/Agent OS and Executive owner; calculate false-completion, unknown-link, freshness and missingness rates with exact denominator, no `0/0` victory.
- [ ] Keep correction flow owner-specific: repair Linear projection only when it disagrees with Agent OS/GitHub, repair Agent OS only under its own writer, and repair Runtime only via its own accepted admission; never majority-vote.
- [ ] Confirm service restart/no secrets/no duplicate state, independent review, source CI, installed SHA, 24h liveness and production signed-in walkthrough.
- [ ] Update appropriate Agent OS continuity/evidence and existing Linear parent projections after accepted proof. Explicitly leave failed/unknown lanes incomplete.

## Testing and roll-forward/rollback matrix

1. **Truth invariants:** a merged contributing PR with failing or missing product proof is never Done; a `QUEUED` Job is never running; a Slack event never creates an Executive attempt; source status controls its own domain.
2. **Identity:** immutable Linear UUID vs `P-MAS-*` display ID, WS/MAS case and uniqueness, explicit authored relations, parent-child, missing native `linkedIssues`, duplicate/head drift and malformed source refusal.
3. **Completeness:** pagination required; capped/truncated partial feeds show explicit `COVERAGE_INCOMPLETE` and cannot positively assert no open PR. A 59-project portfolio observation does not automatically map to 85 canonical active WS.
4. **Temporal:** source revision+as-of, stale installed snapshot, delayed/duplicate webhook, forced 429, partial Linear outage, remote head moving during read; preserve last-good only with historical label.
5. **Mutation:** no P1 live write without MAS-64; single-project CAS, zero-op repeat, conflict fail-close, partial failure and post-read, app revocation, refused/unknown effect no alternate carrier.
6. **Acceptance:** separate hermetic tests, independent review, merged source, installed service, current-owner read, UI browser proof, controlled actor canary and later live use. Each has its own receipt.
7. **Rollback:** R1/R2 consumer is read-only/feature-gated; switch existing UI back to old read-only view if malformed while exposing stale notices. For R5, no blind reverse-write: reconcile exact Linear target/current value and restore only through the same accepted project/actor operation.

## Execution inventory and immediate next actions

**First unblocked delivery:** finish **R1** on the already admitted/attempted Fabric carrier; consume its exact result and publish one independent-reviewed source candidate for the existing Executive Control Room. In parallel, use existing read-only Studio/Executive/GitHub inspection to establish why active builds are approximately 616h old and what the installed refresh endpoint actually observes, without colliding with #1736/Control Room release owners.

**Second unblocked delivery:** existing Macro #9919 writer/reviewer owns review/current-base release of offline P1. Do not duplicate the offline planner or wrongly wait for MAS-64 to do pure read-only review.

**Real human ceremony:** MAS-64 has no verified callable app-management path in the current connected Linear tool contract. The workspace administrator must provision/reconcile the single actor and use the protected credential enrollment procedure; only then may R5 live-project mutation run.

**Non-goals:** Slack Linear app installation (explicitly deferred), auto-issue closure by PR merge, unrelated company-project refactoring, replacement Context Fabric PRs, duplicated Worker/Executive ingress, direct production deployment and background execution claims without an observed durable operator.

## Evidence/custody references for a successor

- Protected source & procedure pin: `Mastermind@05f4765cdded00b86620b546b04e2dd339f82f72`, Skillpack 1.0.1/bootstrap 1. Source/authored procedures, not this chat, control.
- Macro `main@753f9b92287e32ee1c6b4b76b38ab153719b9e0a` at observation; newer movement requires material-source comparison, not global replay.
- Existing Fabric child `exec-linear-gh-view-20261022-01`, root `exec-linear-gh-20261022`, PID `14172`: launch attempted; START/return/effects unverified at this checkpoint. **No duplicate request.**
- Existing conflicting/reserved source surfaces: Macro #9919 `scripts/linear_projector_p1_offline.py`/tests/CI manifest; Mastermind #1670 `ops/linear_projector/host_enrollment.py`/tests; Mastermind #1205/#1207/#1211/#1215 Context Fabric paths; Mastermind #1736 Executive installer config paths. Recover current writer/effects before any change to these.
- No code, live actor, installed Executive refresh, deployment or user-path proof is conferred by this plan. Source PR and tests must be read back independently.
