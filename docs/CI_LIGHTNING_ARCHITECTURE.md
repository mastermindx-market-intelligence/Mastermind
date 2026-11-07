# MastermindX lightning CI architecture and execution plan

Created: 2026-11-06 America/Vancouver. Execution checkpoint updated 2026-11-07 UTC.
Program: existing Mastermind #917 / #1607, Macro #6351, WS:CI-MERGE-CONTROL-PLANE.
Implementation operation: ci-lightning-architecture-20261107-c2.
Procedure: Mastermind protected master 615146aac6a1b0c0933bc9b815517a2fd285ed4a,
Skillpack mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap 1.
This is a detailed CI extension of P3.O3 / Phase 4 of the existing
[delivery-turnaround task tree](superpowers/plans/2026-11-02-delivery-turnaround-execution.md).
It introduces no new workstream, queue, scheduler, runtime or acceptance owner.

The final **Current execution checkpoint** section supersedes historical execution
statuses below. Baselines, earlier receipts and unachieved acceptance targets remain
explicitly distinguished.

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
The ubuntu0 desktop-1 canaries were 16m06s with one worker and 8m08s with
four workers ([four-worker run](https://github.com/mastermindx-market-intelligence/mastermind-terminal/actions/runs/42029519496)),
against an earlier hosted 54m41s comparison. These are one-shard observations,
not matched-source whole-suite or sustained fleet results.

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

The end state is seconds for inert changes and a few minutes for substantive changes.
A ten-minute broad/full path is an interim milestone; it does not close the final goal.

| Measurement | Interim p95 | Final p95 | Required meaning |
|---|---:|---:|---|
| First actionable static/contract failure | Establish baseline | <=60 seconds | Real failure surfaced to author; successful runs are not counted as failures |
| Verified docs/metadata required verdict | <=2 minutes | <=90 seconds | Trusted inert allowlist; no executable/config/consumed-data escape |
| Ordinary bounded source required verdict | <=5 minutes | <=3 minutes | Relevant unit/contracts and affected integration/browser paths |
| Broad/full canonical required verdict | <=10 minutes | <=5 minutes | Complete assigned assurance; no expanded exclusions or renamed scope |
| Queue delay on intended capacity | <=60 seconds | <=30 seconds | Native queue timestamps; dependency waiting separately classified |
| Aggregate after last dependency | <=10 seconds | <=10 seconds | Stable required context verifies completeness and provenance |
| Eligible source to protected merge | <=20 minutes | <=10 minutes | Includes integration candidate and queue wait; separate from authoring age |

These are engineering targets, not promises established by current hardware or suites.
The five-minute full target requires removing current indivisible work, not just
changing worker counts. Report cold and warm distributions separately, plus their
actual mix. Publish p50/p95, sample size, selected coverage, runner class, attempts,
failures and cancellations. At least 30 successive eligible observations per populated
class provide an initial operational cohort, not a statistical guarantee. Small
canaries retain their observed ranges and explicit sample counts. Do not choose only
green, fast or warm runs to manufacture acceptance.

A target is not met if test-step time falls but queueing increases the author's
end-to-end wait, total compute becomes unsustainable, or previously required work
silently disappears. A scope reduction is accepted only when the trusted dependency
contract proves that omitted work is irrelevant.

## Preserve and integrate the last few days' work

| Existing change | Intake disposition | Next useful action |
|---|---|---|
| Mastermind #2044 six-shard rebalance, #2129 scoped merge groups, #1570 reuse, #2000/fast-ship profiler | Already merged according to recovered source/history | Consume; do not rebuild these owners |
| Mastermind #2065 four xdist workers per shard | Open b3fdd6ada45a48b940666380938862e558170477; conflicted at intake; current recovery below | Reconcile actual live writer; compose current source in original carrier; qualify worker-death and exact completion guard; measure full run |
| Macro #10735 control-plane family split | Open dbd83c93d5b50f18e11057bd19844336859edc92 | Preserve original split and current repairs; resolve only proven current failure/integration |
| Macro #10788 FIF three-way split | Open 8e7a1de816e246cb8a96031284483576769bdc46 | Compose with the chosen worker design and prove selected-test conservation |
| Macro #10658 / #10738 FIF parallelism | Overlapping existing lanes | Reconcile exact owners/diffs; one resulting source implementation |
| Macro #10752 narrowed-pack compaction | Open 4ddd347bb74a1a04d3f608cae698c203b30effbf | Preserve baseline checks and selected work; measure slots saved versus critical path |
| Macro #10770 adaptive proof cap | Merged in latest checkpoint | Observe actual mature-run capacity decisions; no guessed cap increase |
| Macro #10764 manifest-scoped freshness / #10745 replay environment | Existing source lanes with inherited-red/freshness dependencies | #10755 board-cap repair is already merged; preserve #10674 hold, then #10745, then existing-owner refresh of #10735 |
| Macro #10656 authored/refresh admission and #10674 continuation | Existing control-plane work; #10674 original operation26751 uncertain | Preserve uncertain effect and live source; this plan does not replay or replace it |
| Terminal #1320 native browser dedup / #1324 scoped QA | Merged | Preserve current integrated contracts |
| Terminal #1297 trusted docs scope | Intake 6a7137dc; now integrated/published as 689757a5 on the same PR | Consume natural exact-head CI, then prove natural docs PR latency; release-rule read is currently denied |
| Terminal #1306 optional isolated e2e lane | Open a709b18c3bd25e3aaa264fe3236dbda3155733c9 | Qualify trust/isolation and complete matrix before activation; no implicit host install |
| Terminal #1223 weighted 7/5/5 + serial browser topology, trace and timing work | Draft e34862900a09bfbcf124397ffe0db02a4f509a49; unpublished candidate and uncertain create-commit | Reconcile original effect; preserve already-authored on-first-retry tracing, explicit zero-retry traces, per-attempt JSON timings and one-time Node unit discovery; do not reimplement or replay |

## Critical-path evidence and consequences

Direct native job inspection corroborates the existing cohort reports:

| Observed source/run | Component | Measured elapsed | Decision |
|---|---|---:|---|
| [Terminal 42302235414](https://github.com/mastermindx-market-intelligence/mastermind-terminal/actions/runs/42302235414), mobile 2 | Playwright test / whole job / npm ci | 3298 / 3345 / 17 seconds | Test execution is 98.6% of this job. Prioritize browser/runtime/fixture work over another dependency cache. |
| Same Terminal run | Unit job / current-checkout capture / Vitest | 1013 / 544 / 285 seconds | Capture and Vitest account for 81.8% of the unit job. Browser-shard tuning alone leaves a roughly 17-minute constraint. |
| [Mastermind serial run 42331481657](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42331481657), shard 0 | Whole job / pytest / native application custody | 2131 / 1437 / 373 seconds | The serial qualification prefix must be included in the graph, not hidden inside pytest averages. |
| Same Mastermind run, shards 2 / 3 | Pytest | 1655 / 1683 seconds | Broad serial execution is still expensive across several shards. |
| [Mastermind xdist candidate 42202096909](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42202096909), head b3fdd6ad | Shard 0 whole / pytest / custody / private HTTP compatibility | 1650 / 956 / 382 / 125 seconds | Four workers improve the pytest part, while qualification before pytest dominates the remaining tail. |
| Same xdist candidate, shard 2 | Whole / pytest | 1330 / 1226 seconds | The longest test granules still need work. Other shard jobs were 620-998 seconds. |

These different runs are observational comparisons with potentially different source
and load. They do not establish a controlled causal speedup.

For a workflow DAG, measure queue + setup + collection + the actual dependent
execution path + aggregation. Concurrent job durations are not added to estimate
latency; their sum is compute consumption. Conversely, a serial prefix and its
dependent shard cannot be treated as parallel.

### Amdahl and test granularity

The historical 788.9-second capacity-artifact module imposed a 13m09s constraint
while it remained one unchanged unit under xdist loadfile. The [xdist distribution
contract](https://pytest-xdist.readthedocs.io/en/stable/distribution.html) keeps all
tests in one file on one worker. The current execution slice has physically split
that module into twelve coherent files while preserving all 466 cases. This removes
that particular indivisible unit; it does not establish a five-minute full run.

Macro's old 1630-second FIF unit divided perfectly into three remains approximately
9m03s per sibling before setup. The observed 69-minute pack also shows that
calibration, nested execution or fixture behavior differs from that old estimate.

The next optimization must therefore do one of the following with evidence:
remove repeated deterministic fixture construction, shorten legitimate individual
test work, separate independent fixture-affinity groups, or place the same work on
qualified faster capacity. Increasing timeouts or deleting assertions is not an
optimization. Parallelism is bounded by:

`concurrent runs × jobs per run × workers per job`

Choose all three together. Reserve capacity for the existing merge/admission path
through its current owner. Do not create another reservation service.

## Repository implementation design

### Mastermind: remove repeated collection, long units and serial qualification

Existing source owners are `scripts/ci_pr_scope.py`,
`scripts/ci_parallel_shard.py`, `scripts/ci_pytest.py`,
`scripts/ci_pytest_timing.py`, `scripts/ci_xdist_guard.py` in #2065,
and `.github/workflows/ci.yml`. Keep the required `test` aggregate and the
accepted #2129 trusted merge-group scope.

1. Finish qualification in #2065's original source carrier. The nine independent
   source qualifications now run beside the six pytest jobs. Capacity tests are
   physically partitioned; the native custody pytest bundle uses four processes.
   Preserve current source, security checks and explicit release holds. The latest
   measured full run is red for a diagnosed test synchronization race, not accepted.
2. Qualify **four independent prepartitioned pytest processes inside each existing
   outer job**, using `ci_pytest.run_shards`. The current xdist workers each collect
   the same outer shard before distributing its tests. Partition whole modules
   before interpreter startup so each process collects its own subset. Keep six
   outer jobs and four actual child interpreters: do not nest four xdist workers
   inside each of four processes. Use an independently domain-separated inner
   partition, exact cover checks, private child diagnostic directories and complete
   terminal receipts. The detailed contract and failure cases are below.
3. Treat source qualification as a separate measured critical path. The published
   change removes it from pytest shard 0, but its own serial chain is still longer
   than five minutes. After the collection experiment, qualify independent native
   Actions qualification jobs only where their source/fixture inputs are separable.
   Deliberately advance the aggregate and exact postmerge job-set contract together.
4. Use the now-complete runtime timing inventory to select remaining expensive
   modules and setup/import work. Split coherent affinity groups, shorten redundant
   legitimate fixture work, or qualify faster capacity. A fixture-template cache
   was measured and rejected: it produced no whole-module speedup. Do not resurrect
   it, cache admission outcomes, or infer production Git-batching safety from it.
5. Recalibrate after collection and granularity changes. Compare fixed-budget native
   candidates before increasing the matrix. Include contention, queueing, cold
   setup and first-attempt success. Only then choose a measured combination of work
   reduction and additional qualified capacity that can satisfy the full target.

The accepted architecture decision is a staged experiment, not a forecast that
prepartitioning alone will reach five minutes. The prior native run reports
10,383.657 seconds of test service. At 24 equivalent processes and unchanged
service costs, perfect balancing alone still takes about 433 seconds before
collection/setup. Both wasted work and the remaining compute budget must change.

### Macro: smaller semantic units and less unnecessary reproof

Keep `scripts/ci_pr_scope.py`, `scripts/run_ci_pack.py`,
`scripts/ci_semantic_proof.py`, the existing `ci-plan -> ci-pack -> ci-gate`
workflow, and `scripts/merge_on_green.py` as the owners.

1. Reconcile the overlapping FIF worker proposals (#10658/#10738) and the
   three-way split (#10788) into one source progression. Apply #10735's independent
   control-plane family split and #10752's narrowed-plan compaction without
   losing baseline check identities or selected logical jobs.
2. Calibrate current logical-job and expensive constituent durations from real
   native artifacts. Investigate why FIF pack 0 took 69 minutes; do not tune a
   scheduler against the obsolete 1630-second estimate.
3. Split again at genuine independent or fixture-affinity boundaries whenever the
   longest group exceeds the required budget. Preserve ordered/serial state
   dependencies explicitly. The planner must assert every selected unit exactly
   once, including after compaction, fallback and empty/narrow changes.
4. Complete the existing manifest-scoped freshness and replay-environment work
   (#10764/#10745), so irrelevant changes do not invalidate unrelated proof.
   Definition, command, environment and dependency changes still invalidate it.
5. Complete #10656's existing authored/refresh admission programme through its
   original owner. Main admission remains OFF until its actual producer, consumer,
   fairness and cutover acceptance is established. #10674 operation26751 remains
   uncertain and is not retried or replaced by this plan.

Batch compatible check-definition changes for integration, then calibrate. Repeated
global definition changes followed by repeated proof refreshes waste the very
capacity the execution changes are intended to free.

### Terminal: complete existing topology, address capture, and qualify build reuse

Keep `scripts/ci_e2e_scope.py`, `terminal/playwright.config.ts`,
`terminal/e2e/globalSetup.ts` and the existing workflow/aggregate. Preserve
`Quote Hub tests`, `Terminal typecheck + tests`, and
`Ingest + signal-layer tests` as required contexts.

1. Reconcile #1223's original create-commit uncertainty before further publication
   of its unpublished composed candidate. Its trace policy, attempt reports,
   weighted 7/5/5-plus-serial topology and Node-test discovery repair are already
   authored. #1297's trusted docs lane must compose with the merged #1324 selector.
2. Measure individual slow tests, repeated navigation/warmup, retries and server
   compile time using the existing #1223 timing output. Use weights appropriate
   to runner class and worker count. Keep known serial Company Intelligence and
   other dependency chains intact until isolation is demonstrated.
3. Profile the unit job's 544-second capture separately from its 285-second Vitest
   execution. Preserve required evidence consumers and exact-source identity.
   Reuse same-candidate capture outputs across consumers where valid; only select
   fewer capture journeys after proving the impacted-journey contract.
4. Build one immutable browser-test artifact for a candidate and fan it out to
   shards **only after fixture-mode equivalence is qualified**. Current tests use
   `next dev`; their `ADMIN_DEV`, fixture identity/entitlement and runtime data
   behavior do not automatically survive `next build && next start`.
5. Treat test fixture build inputs as a distinct, nondeployable artifact class.
   Keep localhost binding, deterministic fixture data, explicit identity, no live
   credential/provider requirement, and production auth refusal tests. Do not
   widen production's development-only bypass to obtain a faster test. If safe
   production-build parity requires application changes, retain the dev-server
   lane until those are qualified.
6. Compare one controlled shard with identical tests/source under both runtime
   modes, then the complete selected matrix and required aggregate. Browser
   version, fixture/build digest and environment must travel with the artifact.
   Zero-retry evidence jobs retain their deliberate failure trace.
7. Expand #1306 only through its actual isolated runner trust and capacity owner.
   Measure the whole matrix under realistic concurrent demand; the 8m08s canary
   does not prove an 18-shard fleet will achieve that time.

[Playwright's trace guidance](https://playwright.dev/docs/trace-viewer) supports
on-first-retry CI traces. That recommendation is already embodied in #1223; it is
not a reason to author another trace change. Its [CI guidance](https://playwright.dev/docs/ci)
also makes worker count a resource/stability decision, not a universal maximum.

## Common evidence contract and reuse boundaries

This is an additive contract for existing planner/proof/timing artifacts. It does
not introduce a new daemon, registry, scheduler or authoritative database.

| Evidence component | Must bind or establish |
|---|---|
| Source and policy | Repository; PR or merge-candidate SHA; trusted planner/policy revision; verified diff base |
| Selected work | Required task/group identities; test/helper/config/data closure; serial affinity; expected partitions |
| Execution identity | Exact command; dependency locks; runtime/toolchain/browser; OS/architecture; material nonsecret environment inputs |
| Input/build artifact | Content digest; producer source and trusted provenance; fixture mode; compatible consumer; nondeployable test marking where applicable |
| Test outcome | Attempt and runner identity; complete collection/execution; success/failure/cancel state; coverage membership; completion evidence |
| Reuse validity | Matching relevant inputs; trust namespace; accepted freshness rule; policy eligibility; miss reason when unverifiable |
| Performance | Queue/setup/collection/execution/aggregate times; retries; cold/warm state; total compute; source class |

Artifact reuse accelerates a fresh test. Result reuse substitutes an already
qualified assertion and needs the stronger identity above. A passing PR proof is
not automatically proof of a different integrated merge candidate.

Use the accepted trusted merge-group selector and the current repository-specific
composition contract. GitHub's [merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
checks the candidate containing current base and preceding queued changes. Preserve
Terminal's accepted removal of duplicate browser fanout while accurately stating
what its merge-group checks establish; add only the specifically owed composition
proof, not the old blanket matrix by default.

Candidate code cannot select a weaker classifier for itself. Unknown dependencies,
renames, policy changes and incomplete analysis expand validation. Missing,
cancelled, wrong-source or unexpectedly skipped selected work cannot satisfy the
aggregate. A cache hit cannot override an observed failure.

Start result reuse with one deterministic, hermetic task in shadow mode: compare
its reuse decision with actual fresh execution before letting it satisfy an
existing required check. Invalidate on a test/helper/lock/config/runtime/environment
change, evidence tampering or trust mismatch. Preserve the existing broader-run
fallback and rollback at the same owner.

The prior [Vercel CI research](https://vercel.com/blog/introducing-vercel-ci)
provides a useful task-graph/cache/per-task-compute pattern. Its vendor performance
claims are not MastermindX measurements. Adopting a new external CI platform is not
required for this plan and is not authorized by an architecture analogy.

## Falsifiers, rollout and rollback

The strongest counterargument is that narrow selection or proof reuse can hide
dynamic dependencies or interactions between individually passing changes.
The architecture fails qualification if:

- A helper, fixture, lockfile, configuration or policy change incorrectly leaves
  affected work out of the plan or keeps a stale result eligible.
- A candidate changes its own classifier and thereby reduces its required work.
- A selected shard is absent/cancelled/duplicated and the aggregate still passes.
- Individually passing changes violate an owed integrated-candidate behavior.
- A full audit finds a selection false negative.
- Additional fanout improves an isolated test while worsening end-to-end p95 or
  completed delivery throughput under representative load.

Use focused negative tests for these failures, then existing full CI and the real
PR-to-integration path. Keep first-attempt pass rate and retries visible; do not
use retries, longer timeouts or exclusions to hide regressions.

Roll out one material execution dimension per interpretable canary. Preserve the
previous trusted planner/worker/runtime setting for source-level rollback. On
bad selection or invalid proof, fall back to the broader canonical run. On runner
or performance regression, restore the previous admitted execution topology.
Rollback does not replay an uncertain operation or resurrect a stale proof.

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

## Initial execution record (historical)

Architecture/planning and non-overlapping source investigation are assigned to the
current session. Native child advice is C3 architecture judgment only. Routine
bounded source labor uses admitted paid Fabric where useful, with one original root,
true parent, stable child ID and retained result; principal direct work requires a
recorded whole-cycle reason. No post-turn execution is promised without real START
and a supported return path.

Current execution: the existing Mastermind #2065 original workspace was
integrated with master 23c9b011e30a4acc6892a59d67a629f74b07a491 after confirming
clean tracked source, exact old head and no observed active handles/index locks.
Six actual test-source conflicts were reconciled. The canonical native stage
builder reproduced the composed 107-member manifest and source inventory
byte-for-byte (manifest 8a7e89dd92cd4c8252ac03188670985f9d76d498a8710a120b1a8a5adfa25cb7).
A new frozen remote-cwd predecessor test exposed one additional observer-preimage
composition mismatch. Its authentic historical observer bytes were restored in
the disposable fixture; the frozen expected digest remained unchanged.

**Published original-branch integration:** [433105846b4d9698d89cffbb54516f51069edacc](https://github.com/mastermindx-market-intelligence/Mastermind/commit/433105846b4d9698d89cffbb54516f51069edacc),
parents b3fdd6ad and 23c9b011, ordinary non-force push with exact GitHub readback.
The same PR now reports mergeable=true. The workflow difference against the
integrated base is still only the four-worker argument; #2129 scope is preserved.
This is principal integration (PRINCIPAL_JUDGMENT / CRITICAL_PATH_SHORTCUT).

**Qualification:** initial 13-file four-worker local batch completed with failures,
not a pass. One was the newly repaired frozen fixture. The other reported failures
were sparse-Git observation refusals; a traced representative returned Git exit0
with a sparse-index expansion warning on stderr. The same representative fails on
unchanged 615146aa source in the separate managed workspace. No warning was ignored
and no production guard was relaxed. The final repaired Go stage and native support
composition selection passed **71 tests, zero failures/errors/skips**, JUnit time
3.651 seconds on macOS Python3.14.7. This is focused local evidence, not full Linux
qualification.

The natural new-head required CI is [42340989000](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42340989000);
shadow CI is [42340989046](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42340989046).
Both were pending at source readback. The earlier green head is not reused to
claim qualification of this integration. No release request has been issued.

### Terminal original-branch integration

[Terminal #1297](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1297)
is now published at [10230a0bf622da83b6acd6c2d9bb2134e9593918](https://github.com/mastermindx-market-intelligence/mastermind-terminal/commit/10230a0bf622da83b6acd6c2d9bb2134e9593918),
parents 6a7137dc and protected dd49fa9b. The original clean workspace was first
reconciled to its bot-created remote merge, then the two selectors were composed.
Two explicit conflict sites and duplicate YAML needs/if/env keys were resolved;
five paths differ from the current protected source. Original #1223 and #1306
source/effects remain untouched.

The docs selector is an optional optimization: an invalid/failed selector runs
ordinary validation. The independent browser selector is mandatory for all events.
Only a successful, exact docs classification on an actual pull_request can excuse
the intentional unit/browser skips. The accepted merge_group browser skip remains.
The stable aggregate checks both selectors and required job outcomes, and explicitly
fails cancellation; missing, failed or unqualified skipped work cannot pass it.

Executed qualification: **207 Python tests passed in 18.98s**, including actual
aggregate-shell truth cases, existing scope/matrix contracts, recursive duplicate-key
checks and cancellation behavior; **10 TypeScript guard tests passed**. No timeout,
test exclusion or required context was weakened. The natural exact-head run is
[42342421881](https://github.com/mastermindx-market-intelligence/mastermind-terminal/actions/runs/42342421881).
Both selectors passed and all expected native jobs were admitted at readback.
Full browser qualification and actual docs-latency acceptance remain pending.

The connector's Terminal branch-protection read returned **403, Resource not
accessible by integration**. That action is stopped; no alternate-account/carrier
replay was attempted. The pre-integration formal review is not claimed as review
of this new source. No new queue or merge request was issued.

### Macro dependency correction

The old #10735 run's board-headroom failure was real at its tested source, but
[the existing #10755 repair](https://github.com/mastermindx-market-intelligence/macro/pull/10755)
already merged as d7843f7f on November 5. Current main c0f0597e has
DISPLAY_BOARD_CAP=640. Do not recreate the repair or describe 480 as current main.
The repair's historical cost estimates are not new VPS runtime qualification.

The source-linked order in
[#10735's owner disposition](https://github.com/mastermindx-market-intelligence/macro/pull/10735#issuecomment-6656361530)
therefore reduces to: preserve/reconcile the existing #10674 held source/effects;
qualify #10745's replay environment through its existing release owner; let the
incumbent update-branch/sweeper reprove #10735 on the resulting base. #10674 currently
remains merge-blocked; its old operation26751 uncertainty is not cleared by a newer
visible branch head. No duplicate cap repair, queue request or rerun is authorized
by finding a stale failure.

### Audit adjudication and next performance slice

Both paid audits returned terminal rc0 with root verified and complete response
bytes consumed. These are research returns, not formal GitHub approval or hosted
performance acceptance. Native C3 advice addressed prioritization and isolation
only; it performed no source mutation.

- **Mastermind audit:** ci-lightning-mastermind-hotspot-audit-20261107-c2-01,
  response SHA256 64b507a2109331a75b795148d361e4195ddebfb5eff41d912c3605907153e5a6.
  The pinned timing artifact directly confirms 788.9s for
  tests/test_capacity_host_artifacts.py. The worker reports 24,846 Git subprocesses
  in its local baseline and 8,584 after three combined proposals; local wall falls
  41.33s to 36.94s. Its approximately 300s hosted forecast assumes spawn latency
  fitted to the old timing and is **not a measured hosted result**. Both local
  variants retained 138 failures, so zero outcome divergence is not full assurance.
  The complete audit return was accepted by manual_result_review with the exact
  response digest above; that receipt does not accept the proposed source patch.
  Accept the diagnostic hypothesis and a fixture-only experiment. Defer both
  production batching proposals until their filesystem-change, path/object,
  malformed-output, refusal-order and tamper semantics have direct qualification.
- **Terminal audit:** ci-lightning-terminal-runtime-audit-20261107-c2-01,
  response SHA256 5693da53b5eba5e7337243586acea8c0bc0136b1f614bece787c776685a32837.
  Its dev-only auth and existing-writer map are useful. Its claim that a passing
  first-retry trace is removed is **rejected**: the
  [Playwright contract](https://playwright.dev/docs/api/class-testoptions#test-options-trace)
  records and keeps that retry. Its assertion that adding seven routes leaves
  every shard's total compile work unchanged is also unproved, especially for
  focused shards. Do not implement blanket warmup additions from this report.
  This return is not accepted as a complete correct performance recommendation.

Direct parent inspection fills part of the Terminal audit's missing evidence:
[mobile-2 job128182990557](https://github.com/mastermindx-market-intelligence/mastermind-terminal/actions/runs/42302235414/job/128182990557)
reports **14 warmup routes in 12s**, **368 passed /115 skipped in 55.0m**, and no
flaky/retry count. Slow files include news-flow-responsive (6.3m) and
options-companion (5.8m). This run does not support warmup as the dominant cost.
Its startup also executes Node-test diagnostics before the Playwright run; the
already-authored #1223 discovery repair remains material. The unit job's
current-checkout capture decision reports full-pr-proof despite zero drifted
files; preserving its assurance while reducing capture/setup remains a separate
design task. Do not claim unmeasured route or trace savings.

The fixture-only child and its parent experiment are now terminal; see the current
checkpoint below. Its principal-owned integration workspace remains at base
7fee845723c44dafe1e9e1159058ad9bd3f3e06b with no candidate published. The experiment
did not demonstrate a whole-module wall-time improvement. Production batching
remains deferred under the safety and measurement requirements above.

Posting a PR status comment was rejected by automatic approval review because
explicit permission to message others was absent. That comment is not retried or
repackaged. Source authoring and qualification continue independently. No source
merge, runner activation or product acceptance is claimed.


## Current execution checkpoint — 2026-11-07 UTC

### Published source, proof and release state

| Carrier | Exact source or evidence | Observed outcome and remaining gate |
| --- | --- | --- |
| [Mastermind #2065](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2065) | Current head **7a49a75341fbccf7cf3dc4898156718e21fcf38c**; capacity/qualification head `1b02680617008bd617a5d9be6da09a80b5a54cbf`; integrated native checkout `a91c52581a28434312013be584a03c767807df7d` | Original branch retained. Native [run 42353265679](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42353265679) completed **FAILURE** in about 25m30s: source qualification and five shards passed; shard 4 found the original-turn finalization race repaired in the newer source. Final-head [required CI 42355985590](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42355985590) and [shadow 42355985472](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42355985472) were observed pending. The 1b shadow was cancelled after superseding source. No queue or merge request issued. |
| [Terminal #1297](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1297) | `689757a5fecab76bac601efbef9178f8115ae01e`; [run 42344305342](https://github.com/mastermindx-market-intelligence/mastermind-terminal/actions/runs/42344305342) | **SUCCESS** across the full native matrix and required aggregate, approximately **64m13s**. This qualifies its scope composition, not fast CI. The integration's explicit 403 on branch-protection access blocks release-rule verification; no alternate carrier or queue request was used. |
| [Macro #10825](https://github.com/mastermindx-market-intelligence/macro/pull/10825) | Continuity seed `d49837ea333bfef114466139d410ee217ed1c999`; existing `WS-CI-MERGE-CONTROL-PLANE` | Agent OS validation passed and exact source readback matched. `ci-gate`, all three packs and main authority succeeded; the distinct merge-queue-pilot authority context failed. Macro branch-protection verification also returned an explicit 403. No label, queue, approval or merge was requested. |
| [Mastermind #2191](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2191) | This architecture carrier; previous checkpoint `e27af89163dbc1e255122b31501d733f167d5197` | Source-backed master plan, current evidence and staged execution contract. Its native required CI is red; job 128336049875 at the previous checkpoint confirms the same protected-base realm pin mismatch that #2065 repairs. Normal required checks and integration remain owed. |

The protected procedure pin `615146aac6a1b0c0933bc9b815517a2fd285ed4a` remains
compatible through current protected master `5199647e89166d163392905574097b2cfa16ca5b`.
The bounded comparison found no change in AGENTS, sol_skills, session review,
delivery workflow or active-execution law, or the owned CI/capacity/gateway paths.
The final protected ref was read again and still matched. No ancestry-only merge
was performed merely to move the source revision.

An explicit [Release HOLD on #2065](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2065#issuecomment-6704040875)
requires the gateway successor failure to be diagnosed/repaired and fresh native
proof. Its author was a read-only observer, not a replacement writer. The assigned
session retains recovery ownership. Passing that shard in the later run is useful
evidence, but does not by itself identify the earlier hidden exception or rescind
the hold. Preserve the hold until legitimately resolved; do not invent an approval.

### Source scheduling and exact qualification

Nine formerly serial matrix-zero qualifications now run as a separate **Source
qualification** job alongside six canonical pytest shards. Commands, source pins,
environment bindings and order were preserved when moved. The later native-custody
change adds four-process loadfile execution to its exact eleven pytest files.
Its 375-case unittest prefix, trusted fixture parent, one-controller JUnit result,
positive test count and zero-failure/error/skip assertion remain unchanged.

```mermaid
flowchart TD
    S["Trusted source scope"] -->|Full| Q["Source qualification"]
    S -->|Full| P["Six pytest shards"]
    S -->|Fast or smoke| F["Focused checks"]
    Q --> G["Required test gate"]
    P --> G
    F --> G
    G --> M["Existing merge queue"]
```

Full scope requires both heavy results successful and fast checks skipped.
Fast/smoke requires successful focused checks and both heavy results skipped.
Protected push and deliberate dispatch retain full qualification. Missing, failed,
cancelled, unknown and unexpected skip states remain red. Source qualification
has contents-read permission and a 30-minute cap; pytest retains its existing
Actions-read permission and 60-minute cap.

The postmerge reuse reader now verifies the actual **ten-job** full-run shape:
six shards, source qualification, scope, required gate and the exactly skipped
empty fast job. It retains exact source/clean checkout, native queue actor,
workflow/attempt, freshness, unique job/step identity and authenticated API checks.
Executed timestamps remain ordered; skipped-fast metadata is bounded to the run
despite GitHub's unusual skipped-job timestamp order. Missing evidence executes
pytest; source qualification remains mandatory even when pytest can be reused.
Native merge-group and postmerge acceptance of this optimization are still owed.

Focused graph/guard evidence: 736 tests passed, two old layout expectations were
corrected and both passed against the same source. This is 738 qualified cases
across the full run plus repair, not a single fabricated green invocation. Gate
tests cover wrong dependency states on PR, merge group, push and dispatch;
mutations reject omitted/conditional checks, serialized heavy dependencies,
additional Actions permission and false-success suppression.

Native source-qualification comparison:

| Measurement | Prior 91d / run 42348719795 | Capacity/qualification 1b / run 42353265679 |
| --- | ---: | ---: |
| 375-case native unittest prefix | 14.022s | 14.725s |
| Same eleven files / 277 native pytest cases | 451.33s, serial | **300.68s**, four-process loadfile |
| Native application custody step | 466s | **316s** |
| Whole source-qualification job | 817s | **684s** |

Both sets of 277 cases had zero errors, failures and skips. These are two actual
native observations, not a controlled cohort or a promised fourfold gain. The
remaining qualification chain includes 151 seconds of private HTTP compatibility,
48 seconds of closed transport and 45 seconds of Brain composition in the newer
run, besides source setup. Splitting that chain is a separate qualified change.

### Capacity module partition: published and natively consumed

Original module blob `b3341d2768bbc21c229bd25d86261cb9d05c3231` contained 167 test
functions and 466 parametrized cases. The candidate moves those functions into
twelve direct children of `tests/`: artifacts, crash replay, failure evidence,
precommit, publication, recovery, repository, retained views, rollback, source
admission, transitions and transport. Shared helpers stay in the original module.

All 167 function ASTs, decorators and parameter values are identical; all 39 helper
definitions are unchanged. Named helper imports preserve the external native
closure consumer. Tests using `__file__` retain the same directory depth; the
canonical-temp test and the V2 test it calls stay together. Darwin custody fixtures
are unchanged. There is no fixture cache or production capacity-code modification.

The complete source checkout discovered 2,284 modules with zero exclusions and
proved exact disjoint six-way membership. The later integrated checkout includes
additional current-base modules; its native selected inventory is 2,289 modules,
with 2,283 runtime summaries and six collection-gated modules. Source identity is
recorded for each measurement rather than treating these corpora as identical.

Paired partial Linux measurements preserve the exact 466-case inventory and outcomes:

| Execution | Wall time | Outcome |
| --- | ---: | --- |
| Original module, serial | 163.326s | 416 pass / 14 fail / 36 skip |
| Twelve modules, serial | 140.703s | Same outcome multiset |
| Twelve modules, four-process loadfile | **54.000s** | Same outcome multiset |

Failure IDs and messages match after normalizing only the exact source-root prefix.
Missing historical source/workflow, nonstandard temporary ancestry and supplementary
groups explain the partial snapshot refusals. These are local comparative results,
not an all-green hosted qualification or a hosted speed forecast.

Native run 42353265679 completed **all 466 capacity cases** across the twelve files.
The longest new capacity module reported **219.600 seconds**; the previous native
single-file unit reported **805.019 seconds**. The new family summed to 1,097.597
reported seconds versus 805.019 previously, so no reduction in total hosted work is
claimed. The split removes a large indivisible scheduling unit under variable load.
All case-start/completion counts match. The entire run remains red for the separate
follow-up-conversation race; this is evidence for this slice, not full acceptance.

The focused complete-host policy/fanin/diagnostic/guard/closure run had 472 passes
and 11 native-closure setup refusals caused by the Mac temporary ancestor's group.
No custody assertion was relaxed. The unchanged native-closure consumer separately
passed all 15 cases on Linux with a valid owned parent. These are distinct receipts.

### Concrete failures repaired or retained

**Original-turn finalization race.** Shard 4 of run 42353265679 failed strict event
equality in `test_signed_consumed_parent_second_turn_original_read_and_no_replay`.
The reply's completion future resolves at `RECORDED`; the [original dispatch](https://github.com/mastermindx-market-intelligence/Mastermind/blob/1b02680617008bd617a5d9be6da09a80b5a54cbf/control_plane/executive_service.py) then
performs ordinary finalization. Its legitimate `OHF_EPOCH_ABANDONED` and
`JOB_COMPLETED` events raced the test's snapshot. No new provider turn was observed.

The [fixture repair](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7a49a75341fbccf7cf3dc4898156718e21fcf38c/tests/test_fresh_conversation_turn.py) captures the original child dispatch task immediately after creation
and awaits it before the duplicate-event snapshot. Exact event-list equality,
same-result, original artifact export, one provider start, two turns and original
job/attempt counts are retained. A new controlled case pauses the real finalizer,
proves the duplicate is strictly read-only while finalization is pending, releases
the barrier, calls the real finalizer and verifies settled original/turn results.
Failure cleanup drains that original task before cancellation fallback.

All **13 follow-up cases passed** with four-process loadfile. The final cleanup
change additionally passed its focused case and a deliberate assertion-failure
probe: the original task completed without cancellation or dispatch error, with
exactly one abandonment and one completion event before teardown. The injected
case correctly failed; it is a failure-path qualification, not a claimed green test.
Production lifecycle and response behavior are unchanged.

**Gateway successor publication.** Prior 91d required run failed
`test_v2_receipt_can_be_next_exact_predecessor_without_rewriting_history`; its shadow
run 42348719763 succeeded. The same gateway module and production owner were
unchanged since the previous green candidate. The production wrapper correctly
hides post-marker errors behind `TransactionEffectUnknown`, retaining context.

The candidate adds bounded fixture-only diagnostics that rethrow the identical
exception: at most eight cause/context nodes, known-source function/line frames,
closed validated observation notes, cycle protection and a fixed fallback note.
It does not expose arbitrary exception payloads or modify production refusal.
Six focused diagnostic checks passed. All 24 existing gateway test function ASTs
remain unchanged; their parametrized native module's 60 cases passed in run
42353265679. An earlier Mac diagnostic passed the first two cases, including the
previous failure, then was deliberately interrupted; it was not a full green suite.

A narrow shared-repository-parent race during initial custody observation is a
source-supported hypothesis, not the proven earlier cause. The reader's later
prefix checks already tolerate ordinary child-entry changes. Do not weaken its
production identity/ACL checks or declare the Release HOLD cleared from a rerun.
Consume bounded context from any subsequent real failure and reproduce the actual
mechanism before a fixture-isolation repair is accepted.

**Explicit realm pin.** Accepted protected #1824 changed live realm blob
`eeea4c0fafc7e6df5c534c731cb6046bbe4d3f37` to
`a51e2bce8d9bb312107f975d503abd6541bd5000`. The integration fixture's single live
`REALM_PINS` entry was advanced deliberately; exact Git hash verification and
historical A/B preimages remain fixed. Current Brain composition passed 23 tests
against paired Macro `f0375acf4ba076718e7cb420ed28ab61fb0a4f26`; 16 commercial realm
tests passed. A different installed Codex-binary digest remained a real local
refusal; no host binary/configuration/assertion was altered. Native qualification
now passes this composition. Impact planning must model explicit source-pin edges.

The earlier CLI metadata repair changes only eleven parametrized IDs; the
131,073-byte input and assertions are unchanged. All 99 tests passed locally;
the old Linux E2BIG condition was reproduced and the shorter ID avoided it.

### Fixture experiment disposition

Paid child ci-lightning-mastermind-fixture-impl-20261107-c2-01 returned a complete
candidate and report, then terminated with rc 1 with provider_error/unrecognized_model
for MiniMax-M3. Root lineage was verified; this is not a successful worker return.
Response SHA256:
94aa09b2bdc28349cbda24c650d9785ba6bcb092a0a52d47f9042762f113f58b.
Patch SHA256:
de0b7c446b79e2d9292a6a4e2d5c4fa6b9a5706fc93e621c669adb4e4778c42e.
No retry or replacement dispatch was issued.

The parent independently checked the exact fixture candidate
db267ebbbc2d1c593fa16fc3b00c5bce5e1c85c244401527e8a33413d5913296.
All 167 existing test functions retain identical ASTs; the three new isolation,
pre-initialization and no-Git-on-copy checks pass. A private Linux parent was
verified against the actual custody guard before benchmarking:

| Run | Cases | Pass | Fail | Skip | Whole-module wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged source | 466 | 415 | 15 | 36 | 148.632s |
| Fixture candidate | 469 | 418 | 15 | 36 | 148.704s |

Failure IDs and messages are identical. The isolated snapshot lacks the workflow
file and historical Git object used by two tests; its nonstandard /tmp topology
and absent supplementary group account for the other failures. This is partial
environmental parity, not an all-green native qualification. Mac baselines also
exposed real custody refusals from temporary-directory groups and home-directory
ACLs. No production permission check or security assertion was relaxed.

**Disposition: do not publish this as an accepted performance optimization.**
Git subprocess reduction and a faster fixture microbenchmark did not produce a
demonstrated whole-module gain. No hosted speedup is claimed. The principal-owned
fixture integration worktree remains unchanged; the experiment does not authorize
production Git batching.

The separate paid preflight-DAG child
ci-lightning-mastermind-preflight-dag-20261107-c2-01 terminated at admission with
rc 75 / EXECUTION_NOT_ELIGIBLE and no qualified source return. It was not retried.
The principal performed the bounded integration in #2065's existing workspace,
using C3 architecture judgment and direct-source self-checks
(PRINCIPAL_JUDGMENT / CRITICAL_PATH_SHORTCUT / LOWER_TOTAL_OVERHEAD). No second
worker, source carrier, runtime route or approval identity was introduced.

### Full timing inventory and the next architecture constraint

Canonical-step logs from [run 42348719795](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42348719795)
at integrated `d31e7ade3d01efab0bb8cc6c50c62c0d6c8a6823` establish:

- **2,276 discovered modules, zero exclusions; 2,270 runtime timing summaries.**
- Every reported module has equal started and completed case counts.
- **10,383.656546 seconds** of setup/call/teardown service, excluding startup and collection.
- Eight supplementary H1 summaries are excluded from canonical workload accounting.

The six gaps are real tests behind module-level import gates: four
`mastermind_window_reader` browser files gate Playwright (two also JWT),
`test_acp_tool_observations.py` gates optional ACP, and `test_risk_prior.py` gates
`brain.risk_prior`, absent at that source. Quiet logs do not identify each failed
import. They have no runtime execution receipt; their import/capability-check cost
is included in collection. Do not call all 2,276 modules executed or assign them
zero collection cost.

| Outer shard | Runtime modules | Reported service | Startup/collection to first case | First case to last module summary | Whole canonical test step |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 402 | 1,393.230s | 196.331s | 438.029s | 638s |
| 1 | 357 | 1,803.163s | 263.354s | 534.525s | 800s |
| 2 | 349 | 1,858.675s | 250.181s | 805.743s | 1,059s |
| 3 | 374 | 1,762.026s | 181.828s | 472.641s | 658s |
| 4 | 379 | 1,658.507s | 258.462s | 441.831s | 704s |
| 5 | 409 | 1,908.055s | 272.184s | 493.272s | 770s |

The newer 1b native run still spent approximately **173–430 seconds before its
first canonical case** depending on shard. Its longest test step was 1,244 seconds;
`test_trend_persistence_walkforward.py` alone reported 553.047 seconds. Other source
and runner load differ, so a capacity-module gain cannot be reported as an overall
pack speedup. Filter logs at the exact canonical command boundary: H1 and the
canonical step can share a rounded API timestamp and otherwise be double-counted.

At unchanged observed service costs, 10,383.657 / 24 gives a conditional **432.65s**
perfect-balance execution floor before collection/setup. This is a planning bound,
not a hardware-independent law: reported elapsed service changes with contention.
A provisional 300-second budget might allot 30s queue, 30s setup, 30s collection,
200s selected execution and 10s aggregation. At that 200-second execution budget,
the old service sum would require about 52 equivalent concurrent processes under
ideal balancing, or roughly 54% less service work at 24. Neither is already
qualified. The next experiment keeps capacity fixed so the collection effect can
be measured before choosing the eventual work-reduction/capacity combination.

### Next implementation: partition before collection, inside existing owners

**Decision:** qualify independent prepartitioned pytest children before expanding
the Actions matrix. Extend `ci_pytest.run_shards`, the existing guard and fixed
diagnostics. Preserve six outer jobs, four actual child processes and the canonical
root conftest/whole-module semantics. Keep native custody's separate eleven-file
xdist lane unchanged during this experiment.

1. **Independent inner placement.** Preserve outer membership. Derive inner buckets
   from an explicit new hash domain or independent digest bits. Do not run the
   same `hash % 4` over a subset selected by `hash % 6`: parity would populate only
   two inner buckets. Prove deterministic complete disjoint cover at both levels,
   no empty-selected false success, stable unrelated placement and known pin rules.
2. **Private child outputs.** The current runner inherits one
   `MMX_CI_FIXED_DIAGNOSTICS_DIR` and fixed JSON leaf. Give each child an owned
   directory under the incumbent job root, preserving collision/foreign-file
   refusal and bounded output. Retain explicit supplementary-H1 phase identity.
   Reconcile all child evidence through the existing consumer, not a new registry.
3. **Complete execution proof.** Exit code zero alone is insufficient. Require
   collection/finish parity and a terminal receipt for each selected child. Detect
   import-time exit zero, killed/lost child, partial collection, missing completion,
   duplicate result, wrong source/child identity and controller interruption.
   Wait/reap every child on failure; no silent retry or fallback to a second effect.
4. **Fixture semantics.** Keep each whole module on one interpreter; preserve
   module/class/session scopes at the existing process boundary. Check inherited
   environment, cwd, import mode, subprocess resources, timeouts and cancellation.
   Do not add nested workers or relax admission/security tests to obtain parity.
5. **Same-budget native comparison.** Compare exact case/parameter/mark/skip
   multisets and failure behavior, then setup, first-case latency, execution tail,
   final required verdict and total compute on current integrated source. One
   interpretable candidate, no simultaneous matrix or runner-class expansion.
6. **Promotion/rollback.** Promote only with complete selected work and improved
   end-to-end latency without flake/capacity regression. Restore the incumbent
   xdist topology at the same owner if the qualification fails. This is source
   rollback, not a retry/queue/authority service.

### Remaining cross-repository execution order

| Ready or held lane | Next concrete action | Completion proof / blocker |
| --- | --- | --- |
| Mastermind source qualification | Consume the new exact-head required/shadow runs; repair only concrete failures; diagnose the held gateway cause using retained evidence | Six shards, all source qualifications, strict aggregate and owed native integration proof; Release HOLD remains binding |
| Mastermind collection | Implement the above four-child partition in existing owners, then native fixed-budget qualification | Exact case and terminal proof, failure injection, measured collection and final-gate reduction |
| Mastermind remaining work | After collection, split independent qualification and remaining long modules; recalibrate current weights | Advance current aggregate/postmerge shape deliberately; no unmeasured matrix expansion |
| Terminal scope | Preserve green #1297 and its full selector/fanin repair | Release-rule verification is blocked by explicit integration 403; no cross-carrier replay |
| Terminal performance | Reconcile #1223's original uncertain create-commit; then consume its already-authored weighted topology, Node discovery and attempt timing; profile capture/runtime separately | Do not duplicate/rehome the unpublished candidate. No global warmup or production-build parity is yet proven |
| Macro integration | Preserve **#10755 already merged (cap 640) + #10674 held → #10745 → #10735**; reconcile overlapping FIF/worker/compaction source under existing owners | Original #10674 operation26751 remains EFFECT_UNKNOWN; #10656 remains held and main admission OFF. Branch-rule verification 403 blocks this session's release path |
| Source continuity | Update this architecture and #10825's existing workstream pointer at material milestones | Readback and Agent OS validation; actual handoff only at a genuine continuity boundary |
| Program acceptance | Measure successive eligible natural cohorts per risk class and cold/warm mix | At least 30 initial observations/class, preserved failures/fallback/cancellation and original product journeys; all target p95 values remain unproved |

The release holds and access denials block their specific lanes, not source analysis
or authorized repairs elsewhere. No message, queued CI, successful job or source PR
is described as a durable autonomous execution owner. No source merge, runner
activation, five-minute acceptance or complete three-repository upgrade is claimed.
