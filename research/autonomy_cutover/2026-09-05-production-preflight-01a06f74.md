# AD-CUTOVER production preflight — evidence-only hold

**Run:** `sol-autonomy-production-preflight-20260905-01a06f74`

**Machine-readable companion:** [preflight JSON](2026-09-05-production-preflight-01a06f74.json), with observation timestamps, exact source hashes, host probe commands and null-valued measurements.

**Prepared against:** Mastermind `46a24a1a4083b74bbde8876100a8ca1f720589a9`

**Verdict:** `HOLD / NOT_STARTED / NO_PROMOTION`
**Scope:** an evidence-only acceptance contract. It creates no runtime authority, store, reducer, provider action, deployment, Agent OS update, or portfolio-status update.

## Acceptance source and boundary

The current Chairman assignment to SOL-AUTONOMY-PRODUCTION specifies the 17 numbered adverse cases below, including provider-neutral return as case 5. The contemporaneous SOL-AUTONOMY-INTEGRATOR assignment lists standalone stale Sol and does not list provider-neutral return. Final portfolio acceptance preserves their **union of 18 named obligations**: the Production 17 plus the supplemental standalone stale-Sol refusal case. The JSON maps exact requirement text to each case and fingerprints both assignments with SHA-256. Neither assignment replaces or weakens the other. The existing acceptance fabric is recorded in the [AD-CUTOVER acceptance-fabric comment](https://github.com/mastermindx-market-intelligence/Mastermind/pull/212#issuecomment-5480487230): cutover is per work class, progresses from `MANUAL` through `SHADOW`, `CANARY`, `SMALL_FLEET`, and `PRODUCTION_FLEET`, and is accepted only from existing source-attributed evidence. It does not authorize a start, provider arm, fleet launch, database, or new truth owner.

The comment's stage labels are preserved here as the acceptance sequence:

```text
MANUAL
  -> SHADOW
  -> CANARY (2–3 responsibilities)
  -> SMALL_FLEET (5–10 independent roots; at least two truly independent realms)
  -> PRODUCTION_FLEET (20–30+ concurrent, event-complete responsibilities)
```

This report is not the reducer described by the acceptance comment. A report may eventually derive from existing Executive OS, RuntimeBinding/Operator Harness, Agent Dialogue/Wake, Capacity, Steward/Control Room, GitHub, and Agent OS evidence. The runtime already owns many input producers, but this operation has no accepted interval exports from them. Every acceptance measurement below therefore remains unknown; this report does not claim the producers are unbuilt.

## Current source versus production truth

The following merge commits are source receipts, not a fleet or runtime proof:

| predecessor | merged PR / merge commit | truthful interpretation |
| --- | --- | --- |
| AD-RET1-R2 terminal RESULT producer | [#406](https://github.com/mastermindx-market-intelligence/Mastermind/pull/406) / `b3f01bbc9ec00594ff936adcec79aaceb513ad56` | protected implementation evidence only |
| W3C runtime composition | [#357](https://github.com/mastermindx-market-intelligence/Mastermind/pull/357) / `b28023f92458ba186937afa1e619f3b4464e149f` | protected implementation evidence only |
| C2-R1A atomic placement commitment | [#415](https://github.com/mastermindx-market-intelligence/Mastermind/pull/415) / `0a5b070624e03d011887adf8ca213733946b6332` | protected implementation evidence only |
| Control Room phase A | [#326](https://github.com/mastermindx-market-intelligence/Mastermind/pull/326) / `b5baa9ed1a38bae5e6821e297f6757fabb7f33a2` | protected implementation evidence only |
| AD-RETRY1 atomic retry decision | [#321](https://github.com/mastermindx-market-intelligence/Mastermind/pull/321) / `7191702e3b0104525b6b26cd30ddb53d89a8a663` | `BUILT_NOT_PROVEN / PRODUCTION_INERT`; no retry/provider/RuntimeBinding activation implied |

The Stage-B v6.1 document retains its records-only `SPEC_ONLY` header. C2-R1A is now implemented in protected source; MAT-S1, Stage-B1 and C2-R1B remain absent at the audited SHA. Overall capability is `PARTIAL / PRODUCTION_NOT_PROVEN`. The current DAG is:

```text
C2-R1A -> MAT-S1 -> { Stage-B1, C2-R1B } -> multi-root reuse canary
```

`MAT-S1` owns materialization of the alias-scoped role-null carrier and the canonical current-writer read. `Stage-B1` is the first-root child; `C2-R1B` is later-root reuse only. Transfer and succession are later, separate work: current v6.1 explicitly says `succession_supported_now: false`. The [MAT-S1 issue #430](https://github.com/mastermindx-market-intelligence/Mastermind/issues/430) comments [5539579073](https://github.com/mastermindx-market-intelligence/Mastermind/issues/430#issuecomment-5539579073) and [5539830435](https://github.com/mastermindx-market-intelligence/Mastermind/issues/430#issuecomment-5539830435) identify protection of `CAP-S1` [#350](https://github.com/mastermindx-market-intelligence/Mastermind/pull/350) as MAT-S1's remaining source predecessor in that pre-start review; a source START still requires fresh protected-source, path, host and effect reconciliation. This report is no commission or START. No duplicate writer, substitute fixture, or alternate source gate is lawful.

AD-RET2 remains a separate gap. [MAS-214](https://linear.app/mastermindx/issue/MAS-214) is Todo and calls for sustained `PROGRESS`, `BLOCKED`, and `DECISION_REQUEST` production projection. The live ORION milestone of 2026-09-03 says #406 is terminal and does not commission AD-RET2. No accepted sustained-yield canary was recovered; terminal RESULT source protection cannot satisfy that gate.

## Bounded host preflight observations

These are observations bounded to the named probes and dates; they are not host-wide absence claims.

| probe | observation | interpretation |
| --- | --- | --- |
| Executive tool fixture | old `7191702e` / `7794929` fixture lacked the required database | no usable acceptance evidence from that fixture |
| `launchctl` system control and `codex-pro-01`, `codex-pro-02`, `codex-pro-03` | service absent (`113`) | named service absence only; no installation or host-wide inference |
| installed releases | control `a6fde004`; Pro releases `e4e44867` | installed-source identifiers, not live service proof |
| `control.json` | `PermissionDenied` | configuration could not be accepted as a current runtime receipt |
| `GET localhost:8787/api/state` | `403` | endpoint access result only; not a Control Room health or fleet-state result |

This preflight did not obtain a complete current canonical input set for an acceptance run. `OperationAssurance` [#362](https://github.com/mastermindx-market-intelligence/Mastermind/pull/362) is occupied; this operation must not replace it or claim its function. A fixture, a caller-provided pass summary, a protected merge, a green check, a Slack delivery, `PICKUP_ACK`, or `START` is not a substitute for source-attributed runtime evidence.

## Measurement contract: null before SHADOW

For this operation every numeric measurement is **unknown**. There is no denominator, so all hard-zero counters are **unknown**, not zero. The 17 cases below are **`NOT_RUN_THIS_OPERATION`**. The Production assignment explicitly numbers 17; the older acceptance comment groups the retry pair. The Integrator assignment adds the standalone stale-Sol obligation described below. This scorecard separates safe and unsafe retry and explicitly includes effect-unknown failover. Continuation and completion remain stage gates, not substitutes for case 17.

SHADOW is read-only. It compares proposed identity, target, placement, retry, queue, and Control Room outcomes against canonical operator/runtime outcomes. Before any canary, it must freeze source-derived numeric `p50`, `p95`, and `max` budgets for:

- `request_admission_to_claim`;
- `claim_to_provider_start`;
- `provider_terminal_to_company_return`;
- `company_return_to_sol_target`;
- `sol_action_to_worker_continuation`; and
- `eligible_capacity_wait`.

It must also freeze the fairness budget and its population/denominator before CANARY. Neither latency nor fairness numbers may be invented in this report or relaxed after observing a canary. All 18 named obligations in the reconciled union require source-attributed execution evidence before final portfolio acceptance.

No previously accepted stage receipt was recovered; the operational posture for this task remains manual and unpromoted. SHADOW may collect evidence only after its applicable readiness gates clear. Advancement from SHADOW to CANARY requires a declared denominator, source references, frozen budgets, zero measured hard-invariant violations, and no unresolved systematic misclassification.

## Measurement preregistration: planning accepted, execution unarmed

The Autonomy Integration CEO accepted the following **planning and measurement protocol floors** under the current Chairman portfolio assignment. This is not numerical SLO acceptance, a runtime START, a stage promotion, or evidence that measurement has begun. The companion JSON separates these protocol values from still-null observed metrics and latency budgets.

Before measurement, freeze named work-class/provider/realm/resource strata, independence criteria, actual canonical endpoint and clock fields, contribution per root, and all data-quality states: completed, active, right-censored, missing, invalid and failed. Retain every eligible start in its denominator. Report raw nearest-rank quantiles, pooled and root-weighted results, each root's contribution, and uncertainty; repeated turns are not independent roots. A completed-only p95/max cannot pass while unresolved or censored observations could breach its budget. Unqualified sparse strata cannot disappear into a pooled result.

The accepted planning floor is 100 completed observations for each applicable edge in each qualified stratum, covering at least 20 distinct roots for that edge, plus at least 20 distinct eligible-wait episodes. These are coverage floors, not claims of high-confidence tail estimation. The six endpoint contracts must distinguish actual provider start from queueing, company return from transport ACK, and return delivery at the current Sol target from an older binding-creation timestamp. Capacity wait ends at lawful placement, never merely at a `WAITING_CAPACITY` label.

Fairness is measured across a whole frozen epoch, with candidate/allocation/policy receipts. The planning limit is at most three unexplained bypasses among roots with comparable priority/weight, capability/resource requirements and eligible-realm set. Report global oldest eligible age as well as comparable-class age. Preserve age across same-root retry/backoff; pause only verified, predeclared ineligibility. The literal capacity-wait maximum remains unfrozen. This tests the existing policy and does not commission a scheduler change.

The numeric budget formula remains **proposed only**: p50 at 1.25 times the measured p50; p95 at 1.5 times the measured p95; maximum at the greater of the measured maximum and twice the measured p95. Use nearest-rank empirical quantiles and seconds rounded upward to 0.001 second, retaining raw data. Sol must adjudicate the resulting literal stratum budgets and product fitness after SHADOW and before CANARY. A slow baseline cannot qualify itself through the formula. Ordinary and predeclared adverse-recovery limits must be frozen separately; all fault observations remain in invariant and recovery denominators.

The accepted production protocol floor is at least 24 continuous hours **in addition to** event completeness and separately frozen natural-time obligations. A predeclared substantive overlap window must contain N >= 20 roots performing real cohort work; an instantaneous peak is insufficient. At least `ceil(N/3)`, with a minimum of seven distinct cohort roots, must complete Worker → Sol → Worker continuation; at least two distinct roots must terminally complete. Freeze the overlap window, realm taxonomy and valid terminal types before the interval; fixtures and cleanup-only cancellations do not count. The reconciled 18 obligations and zero routine Chairman carriage remain required.

**Staging separation accepted by the Integrator:** read-only SHADOW cannot manufacture the provider/return/continuation events it measures. The existing acceptance source requires frozen budgets before CANARY. The accepted route is observation of genuinely analogous, independently authorized MANUAL owner operations through existing read interfaces, with SHADOW producing no launch or command effect. Setup/operator activity stays in its declared ledger outside the later acceptance interval. This does not create a new stage or permit an autonomous experiment to be renamed calibration. Exact manual event authority and source equivalence must be reconciled first; missing edges remain unqualified. Historical cases require frozen work-class/provider/resource/source equivalence, exact lineage, trustworthy clocks/endpoints and censor parity; otherwise they remain contextual only. If no such event source is lawful, return `WAITING_DEPENDENCY / MANUAL_EVENT_AUTHORITY_ABSENT` for that exact missing operation authority before measurement. The staging design is settled; endpoint/overlap freeze and actual operation readiness remain owed.

## Event-complete promotion gates

### CANARY — two or three responsibilities

Each real responsibility must traverse one source-attributed vertical:

```text
request -> one root -> one child -> lawful placement -> exact current worker
-> provider turn -> harness semantic return -> canonical dialogue -> Wake
-> exact Sol target -> Sol action -> exact worker continuation or truthful terminal
-> Control Room / Linear projection
```

The canary must include one read-only/research responsibility and one isolated code responsibility. At least one must prove a real Worker → Sol → Worker continuation with no routine Chairman Slack/session intervention, and at least one must reach a truthful terminal outcome. A preliminary single-operation retry proof remains distinct from this 2–3-responsibility CANARY stage.

### SMALL_FLEET — five to ten independent roots

Require five to ten concurrently active independent roots and at least two **truly independent** lawful realms. Aliases sharing quota, host, process, or effective provider boundary count as one realm. The interval must demonstrate fairness against the frozen population, visible `WAITING_CAPACITY` rather than Chairman account selection, one safe typed retry, and one unsafe/effect-unknown case held without blind failover.

### PRODUCTION_FLEET — twenty to thirty or more concurrent responsibilities

Acceptance is event-complete, not a short cosmetic soak. The interval cannot close until 20–30+ concurrent logical responsibilities span multiple lawful realms; every active responsibility crosses at least one real provider/harness semantic boundary; a meaningful production subset completes Worker → Sol → Worker continuation; and multiple responsibilities complete terminally through the real path. Frozen p50/p95/max and fairness budgets must be met, every required adverse case must have an exact receipt, and routine Chairman Slack/session/account/watch intervention must remain absent.

## Seventeen required cases

All case rows are `NOT_RUN_THIS_OPERATION`; every hard-zero count and every latency/fairness observation is `UNKNOWN` until SHADOW establishes its denominator.

| # | stable case ID | case | required safe outcome |
| --- | --- | --- | --- |
| 1 | `AD-CUTOVER-DUPLICATE_INGRESS` | duplicate ingress | same request yields one root; changed envelope conflicts, with zero second root |
| 2 | `AD-CUTOVER-SISTER_SOL_RACE` | sister-Sol race | one current action target; other surface is observer/refusal |
| 3 | `AD-CUTOVER-LOST_PROVIDER_LAUNCH_RESPONSE` | lost provider launch response | reconcile the same Attempt/provider; zero alternate-realm resend |
| 4 | `AD-CUTOVER-STALE_WORKER_AFTER_REBOUND` | stale Worker after rebound | former Attempt/provider refuses; current Attempt alone acts |
| 5 | `AD-CUTOVER-PROVIDER_NEUTRAL_RETURN` | provider-neutral return | two actually proven worker/provider classes project semantic return without etiquette assumptions |
| 6 | `AD-CUTOVER-DEAD_UNAVAILABLE_SOL_TRANSFER` | dead/unavailable Sol transfer | unavailable target holds visibly; sanctioned transfer must prove prior target plus binding-generation CAS, one valid replacement, deterministic replay and former-target refusal |
| 7 | `AD-CUTOVER-SLACK_OUTAGE` | Slack outage | safe Executive work continues; needed semantic boundary holds and recovers exactly once |
| 8 | `AD-CUTOVER-SAFE_RETRY` | safe retry | currently sanctioned `TX9_DETACHED` pre-effect case requeues exactly once; identical concurrent retry/restart replay stays deterministic and a stale root cannot overwrite it |
| 9 | `AD-CUTOVER-UNSAFE_RETRY` | unsafe retry | unsafe/generic/semantic failure refuses requeue with a source-attributed outcome |
| 10 | `AD-CUTOVER-CAPACITY_SATURATION` | capacity saturation | visible `WAITING_CAPACITY`; independent eligible root progresses; Chairman does not choose an account |
| 11 | `AD-CUTOVER-PARENT_ACTIVE_NO_SUCCESSOR` | parent active with no successor | explicit `Needs Sol`/parent-orphaned condition, not silent stall |
| 12 | `AD-CUTOVER-STALE_CHAIRMAN_ACTION_CAS` | stale Chairman action | `STALE_VIEW / REFRESH_REQUIRED`; zero effect |
| 13 | `AD-CUTOVER-CONTROL_HOST_RESTART_AMBIGUOUS_RESPONSE` | control-host restart or ambiguous command response | reconcile accepted receipt; conflict stays conflict and unknown stays held |
| 14 | `AD-CUTOVER-STALE_PROVIDER_SURFACE` | stale provider surface | superseded native task is non-actionable and absent from normal resume/needs-worker actions |
| 15 | `AD-CUTOVER-ATTENTION_BROKEN_LIFECYCLE_HEALTHY` | attention failure with healthy lifecycle | `ATTENTION_BROKEN`, not failed/lost lifecycle |
| 16 | `AD-CUTOVER-CONFLICTING_STEWARD_IDENTITY` | conflicting source identity | unknown/refused with source set; no selected owner |
| 17 | `AD-CUTOVER-EFFECT_UNKNOWN_FAILOVER_ATTEMPT` | effect-unknown failover attempt | refuse alternate-carrier/provider resend while preserving the exact operation, Attempt and unresolved effect |

Case 8 includes four explicit subcases: identical command replay after restart, stale-root versus identical concurrent retry, stale expectation/current-Attempt conflict, and intervening invalidated Worker/quota reuse. The refusal cases must produce zero requeue and preserve any accepted concurrent receipt. Case 8 requires the current Runtime-owned classifier and commit path; a pure classifier output alone is insufficient. The audited integrated COO path allows only its closed TX9_DETACHED evidence. Cases 9 and 17 are separate negative cases. Case 6 remains an acceptance blocker until the canonical transfer primitive exists and is exercised: a visible hold alone cannot satisfy transfer acceptance. This report does not authorize a transfer or weaken the prerequisite.

### Supplemental stale-Sol authority exercise

`AD-CUTOVER-STALE_SOL_REFUSAL` maps directly to **stale Sol** in the Integrator assignment's REQUIRED ADVERSE MATRIX. The Production assignment also requires AD-SOL **former-target refusal** and hard-zero **stale writes**. It is `NOT_RUN_THIS_OPERATION`, with unknown observations and no receipts. This standalone case supplements the exact Production 17, bringing the required union to 18 named obligations.

Exercise a formerly valid Sol target after its action authority or RuntimeBinding generation has been superseded. A new stale command must refuse with zero effect, while only the exact current target may act. Replay of an already accepted command must return its existing receipt without a second effect. Capture the exact root, unresolved CEO child, current Attempt, prior and current target/binding identities and generations, immediate precommit CAS, and action/refusal/replay receipts. This is a separate stale-authority exercise from the simultaneous sister-Sol race and unavailable-target transfer; a result from either cannot silently stand in for it.

## Hard invariants and acceptance record

For a stage that has a real denominator, the following counters must be exactly zero: duplicate admitted roots; duplicate child operations; simultaneous authoritative Workers or Sols; sanctioned stale-worker or stale-Sol writes; blind resend/failover after `EFFECT_UNKNOWN`; unsafe automatic retry; permanently lost return after recovery; actionable stale provider surface; false routine `Needs Chris`; routine Chairman provider/account/session choice, Slack shuttle, or tab wake; hidden starvation of a continuously eligible root; and action accepted against stale Control Room state.

An identity, authority, stale-write, or blind-retry violation demotes the affected work class: stop autonomous launch for that class, preserve current effects, reconcile the same operations, and return to the preceding accepted stage. A transport-only degradation with intact Executive truth is not by itself a lifecycle failure.

The eventual immutable report must contain protected source identity, exact root/child/Attempt/Worker/RuntimeBinding/dialogue/Wake refs, realm independence basis, denominator, hard-zero counters, frozen budgets plus measured p50/p95/max, fairness observations, retry/effect decisions, deliberate fault injections, Chairman-touch ledger, projection consistency, gaps, and `PASS | HOLD | ROLLBACK` with a falsifier. It is derived evidence only and cannot become a runtime consumer, lifecycle store, scheduler, or promotion authority.

## Recoverable next step

The existing Autonomy Integration CEO owns the next lawful assembly: collect the existing owner receipts for host readiness, capacity, `MAT-S1`, and Stage B; verify that their source gates and current writers remain exact; then run one exact harmless canary if and only if that complete evidence package supports it. Do not update `MAS-158` or `MAS-219` to done, create a new Agent OS record, reuse the Secretary-retirement 30-case/R0–R5/80% wake criteria, or infer a fleet from source protection.

## References

- [AD-CUTOVER acceptance fabric, Mastermind #212 comment 5480487230](https://github.com/mastermindx-market-intelligence/Mastermind/pull/212#issuecomment-5480487230)
- [Stage-B durable target-transfer v6.1 design](../../docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md)
- [Stage-B v6.1 implementation DAG](../../docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md)
- [MAT-S1 #430](https://github.com/mastermindx-market-intelligence/Mastermind/issues/430), [comment 5539579073](https://github.com/mastermindx-market-intelligence/Mastermind/issues/430#issuecomment-5539579073), and [comment 5539830435](https://github.com/mastermindx-market-intelligence/Mastermind/issues/430#issuecomment-5539830435)
- [CAP-S1 #350](https://github.com/mastermindx-market-intelligence/Mastermind/pull/350), [OperationAssurance #362](https://github.com/mastermindx-market-intelligence/Mastermind/pull/362), [AD-RET1-R2 #406](https://github.com/mastermindx-market-intelligence/Mastermind/pull/406), [W3C #357](https://github.com/mastermindx-market-intelligence/Mastermind/pull/357), [C2-R1A #415](https://github.com/mastermindx-market-intelligence/Mastermind/pull/415), and [Control Room #326](https://github.com/mastermindx-market-intelligence/Mastermind/pull/326)
