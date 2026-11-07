# MastermindX lightning CI architecture and execution plan

Date: 2026-11-06 America/Vancouver.
Program: existing Mastermind #917 / #1607, Macro #6351, WS:CI-MERGE-CONTROL-PLANE.
Implementation operation: ci-lightning-architecture-20261107-c2.
Procedure: Mastermind protected master 615146aac6a1b0c0933bc9b815517a2fd285ed4a,
Skillpack mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap 1.
This is a detailed CI extension of P3.O3 / Phase 4 of the existing
[delivery-turnaround task tree](superpowers/plans/2026-11-02-delivery-turnaround-execution.md).
It introduces no new workstream, queue, scheduler, runtime or acceptance owner.

## Outcome and completion criterion

Make ordinary engineering feedback feel immediate while completing full consequential
validation quickly and predictably across Mastermind, macro and mastermind-terminal.
Optimize final source revision to required green, and separately eligible revision to
protected merge. Preserve the exact selected tests, meaningful integration checks,
source identity, current trust boundaries and original product outcomes.

An implementation is complete only after its existing workflow consumes it, a
representative natural cohort demonstrates the target by risk class, required failure
cases remain red, and its source/evidence/rollback are recoverable. A cache hit,
local test, isolated runner canary, green workflow or plan is evidence at its own layer.

## Verified starting point

Read-only source observations at intake:

| Repository | Default revision | Current implementation |
|---|---|---|
| Mastermind | 615146aac6a1b0c0933bc9b815517a2fd285ed4a | Trusted scope -> fast/smoke or six canonical pytest shards -> required test; merge-group scope from merged #2129; same-SHA postmerge reuse and existing ci-profile consumer |
| macro | 72c249a2e1967d1ec6dcf6179a7a8728f3305e44 | Existing semantic ci-plan -> selected ci-pack -> ci-gate; incumbent merge-on-green, proof freshness and adaptive admission |
| mastermind-terminal | dd49fa9bd4746d283bfc12581153463629de2b4e | Three stable required contexts; 12 PR browser shards; merged #1320 avoids duplicate merge-group browser matrix; merged #1324 scopes responsive verification |

The [latest native measurements](https://github.com/mastermindx-market-intelligence/Mastermind/issues/917#issuecomment-6702164981)
report Mastermind merge-group-created to required-green STANDARD/smoke n=8
p50 1m53.5s / nearest-rank p95 3m10s; FULL n=6 p50 40m47.5s / p95 43m57s.
STANDARD merge-group-created to merge p95 was 29m44s, so a fast check is not
necessarily a fast release. These selected cohorts are not a causal speedup experiment.

The [Terminal full PR cohort](https://github.com/mastermindx-market-intelligence/Mastermind/issues/917#issuecomment-6700311570)
has n=4, workflow-created to complete-green p50 57m22s / p95 58m42s.
The previously recorded ubuntu0 desktop-1 canary was 16m06s versus hosted 54m41s
for one shard, not a full-suite or general fleet result.

Macro's [FIF split proposal](https://github.com/mastermindx-market-intelligence/macro/pull/10788)
records one pack at 69 minutes while its siblings finished in 10-33 minutes.
Its stale calibration weight was 1,630 seconds. We must not confuse calibrated
model weights with observed wall time. Current proof-refresh scarcity and frequent
check-definition invalidation are independent contributors.

## Architecture decision

Extend the existing GitHub Actions owners with a common contract, not a common
replacement orchestrator. Keep repo-specific suites and required-check names.
Treat every run as five separable costs: admission/queue, acquisition/setup,
selected execution critical path, aggregation, and integration/release wait.

1. **Trusted affected-work planner.** Compute changed paths from exact Git identities.
   Use protected policy, explicit dependency closure and conservative invalidators.
   Missing, renamed, dynamic, ambiguous or incomplete dependency evidence goes full.
   Review risk and sufficient test scope remain separate decisions.
2. **Small deterministic tasks.** Split expensive semantic families at natural test
   boundaries, keep stable ownership and prove exact selected coverage once.
   Balance using current measured durations; preserve serial affinity where required.
3. **Cheap hot execution.** Restore locked dependency caches, avoid repeated installation,
   compile production browser assets once per tested candidate where semantics permit,
   and reuse that immutable build across browser shards. Do not ship test flags.
4. **Bounded parallelism.** Choose shard count and per-shard workers together, accounting
   for total slots, memory, databases, ports and queue demand. More fan-out can be slower.
   Use ephemeral isolated runners only through the already qualified runner owner.
5. **Trustworthy reuse.** Begin with immutable dependency/build reuse. A reusable test
   result must bind exact task inputs and transitive dependencies, runtime/toolchain,
   platform, lockfiles, command, trusted policy, environment inputs and artifact digest.
   Untrusted candidate writes cannot supply trusted qualification. Unknown means miss.
6. **Stable aggregate.** Each existing required context reports for every admitted event.
   It validates planner identity, complete coverage, expected shard outcomes and result
   provenance. Cancellation, omission, wrong source, partial results and unqualified
   cache hits cannot turn it green.
7. **Existing release owners.** Preserve native queues and Macro merge-on-green.
   Reduce unnecessary invalidation at its existing owner, while retaining actual
   integrated-candidate proof. Never add a second lease, retry or verdict store.
8. **Existing measurement consumer.** Extend ci-profile/semantic timing artifacts.
   Measure failure/timeout/supersession as well as successful latency, by class and
   phase. Report queue delay separately only where the native timestamp semantics
   actually establish it; a job start offset also includes dependencies.

## Target service levels (proposals, not achieved results)

| Work class | Required-green p50 | Required-green p95 | Qualification |
|---|---:|---:|---|
| Documentation/inert records | <=90 seconds | <=3 minutes | Positive trusted allowlist; no executable/config/consumed-data escape |
| Ordinary bounded code | <=3 minutes | <=5 minutes | Relevant unit/contracts plus affected integration/browser paths |
| Broad shared UI/backend changes | <=6 minutes | <=10 minutes | Complete affected dependency closure; all necessary responsive/security journeys |
| CI/security/authority/full invalidators | <=10 minutes | <=15 minutes | Full canonical assurance, no expanded exclusions |
| Eligible source to protected merge | <=10 minutes | <=20 minutes | Measured independently of source authoring age and required-green |

These are staged goals. Queue capacity and current 41/57-minute full paths make
the full target unproven. Publish observed p50/p95, sample size, risk distribution,
hardware, selection and failures; use at least 30 successive eligible observations
per populated class before a general claim. Small cohorts remain labeled small.

## Preserve and integrate the last few days' work

| Existing change | Intake disposition | Next useful action |
|---|---|---|
| Mastermind #2044 six-shard rebalance, #2129 scoped merge groups, #1570 reuse, #2000/fast-ship profiler | Already merged according to recovered source/history | Consume; do not rebuild these owners |
| Mastermind #2065 four xdist workers per shard | Open b3fdd6ada45a48b940666380938862e558170477; conflicted/review held in latest checkpoint | Reconcile actual live writer; compose current source in original carrier; qualify worker-death and exact completion guard; measure full run |
| Macro #10735 control-plane family split | Open dbd83c93d5b50f18e11057bd19844336859edc92 | Preserve original split and current repairs; resolve only proven current failure/integration |
| Macro #10788 FIF three-way split | Open 8e7a1de816e246cb8a96031284483576769bdc46 | Compose with the chosen worker design and prove selected-test conservation |
| Macro #10658 / #10738 FIF parallelism | Overlapping existing lanes | Reconcile exact owners/diffs; one resulting source implementation |
| Macro #10752 narrowed-pack compaction | Open 4ddd347bb74a1a04d3f608cae698c203b30effbf | Preserve baseline checks and selected work; measure slots saved versus critical path |
| Macro #10770 adaptive proof cap | Merged in latest checkpoint | Observe actual mature-run capacity decisions; no guessed cap increase |
| Macro #10764 manifest-scoped freshness / #10745 replay environment | Existing source lanes with inherited-red/freshness dependencies | Retain trusted definition identity and accurate base comparison; integrate without repeated global churn |
| Macro #10656 authored/refresh admission and #10674 continuation | Existing control-plane work; #10674 original operation26751 uncertain | Preserve uncertain effect and live source; this plan does not replay or replace it |
| Terminal #1320 native browser dedup / #1324 scoped QA | Merged | Preserve current integrated contracts |
| Terminal #1297 trusted docs scope | Open 6a7137dc41e189a1cbd2437469be8764aa5b9dd5 | Compose with current responsive selector; prove natural docs PR latency |
| Terminal #1306 optional isolated e2e lane | Open a709b18c3bd25e3aaa264fe3236dbda3155733c9 | Qualify trust/isolation and complete matrix before activation; no implicit host install |
| Terminal #1223 18-browser-shard redistribution | Draft e34862900a09bfbcf124397ffe0db02a4f509a49; unpublished candidate and uncertain create-commit | Reconcile original effect; do not create replacement source or replay publication |

## Ordered execution tree

These IDs extend the existing Phase 4 CI work, and are editorial source nodes only.

| ID | Deliverable | Dependency | Acceptance |
|---|---|---|---|
| P4.L1 | Reconciled architecture, current cohort, source/collision map | Current source and #917 evidence | Exact citations and separate observed/forecast/held states |
| P4.L2 | Finish existing parallelism/pack/fast-scope implementations | Original custody and current source | No duplicate PR; actual exact-head coverage and runtime measurements |
| P4.L3 | Terminal browser build/setup critical-path slice | Current workflow/config and no overlapping writer | Same user journeys against immutable candidate; focused failures stay red; real hosted canary |
| P4.L4 | Remove hot Mastermind test/setup overhead | Current measured heavy modules; L2 compatibility | No cached security outcomes; unchanged assertions; Linux proof |
| P4.L5 | Macro duration calibration and split/compact reconciliation | Existing logical-job owner and L2 | Every selected job exactly once, current weight evidence, bounded maximum pack duration |
| P4.L6 | Trusted task-result reuse pilot in incumbent planner | Input contract + deterministic hermetic task | Shadow equivalence first; tamper/environment/dependency changes miss; no false green |
| P4.L7 | Qualified runner economics and execution capacity | Full isolation/trust/capacity canary | Whole-matrix benefit, no starvation of Fabric, rollback through same owner |
| P4.L8 | Natural-cohort acceptance and closed migration | Previous slices | SLO distribution, unchanged coverage, failure/freshness behavior, recoverable rollback |

Execute source-disjoint ready work now. No new CI run merely to produce activity;
use natural candidate validation and actual changed-source canaries where needed.
No merge, approval, runner activation or publication of held operations is inferred
from this plan. Source edits and qualified ordinary PR publication are in scope.

## Initial continuation

Architecture/planning and non-overlapping source investigation are assigned to the
current session. Native child advice is C3 architecture judgment only. Routine
bounded source labor uses admitted paid Fabric where useful, with one original root,
true parent, stable child ID and retained result; principal direct work requires a
recorded whole-cycle reason. No post-turn execution is promised without real START
and a supported return path.

Next: inspect the current Terminal browser lifecycle and open overlapping PRs, select
one independently useful unowned slice, implement and run focused discriminating
checks, then publish its exact source and update this plan with evidence.
