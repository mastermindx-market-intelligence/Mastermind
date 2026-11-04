# Fabric capacity and orchestration upgrade: execution record

Operation: `fabric-capacity-orchestration-upgrade-20261005-sol-001`.
Chairman intent recorded at the 2026-10-05 checkpoint: upgrade native Codex/Claude orchestration, cheaper-worker
utilization, multi-level hierarchy, concurrency and future-quota-aware routing.
Historical protected procedure/source pin: `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`;
skillpack 1.0.1 / bootstrap major 1. Actual selected model/mode was unverified at that checkpoint.
This record is evidence and continuation, not a second task queue or authority.

The observations and test receipts below describe the original 2026-10-05
checkpoint unless explicitly updated. They do not establish the current installed
native generation, provider balances, #1228 disposition or qualification of the
later integrated source tree. Current work continues on the original #1248
operation and PR under the assigned receiver, preserving actual writer, lease,
access and effect constraints.

## DONE_WHEN

Qualified Codex and Claude principals can submit through the existing fabric,
use bounded domain coordination and independent workers on more than one eligible
provider, return reviewed results to the exact parent, and recover/cancel without
orphaned effects. Account/model/shared quota, request-rate, host, review and root
budgets are all respected. Measured accepted throughput and whole-closure cost
improve against a recorded baseline. Source, installed and all-account proof are
separate; the overall mission is not complete at this checkpoint.

## Census and ownership

- Executive owns Jobs/Attempts, admission and conserved descendants. Agent OS in
  Macro owns durable workstream continuity. GitHub owns source/review/evidence.
  Capacity/Shared AI Provider Control own resource identity and quota placement.
- The local `pool` wrapper uses an incumbent file-locked SQLite broker in the
  native Meta-CEO kit. Its configured caps are not authoritative live balances.
- Native broker source SHA-256 at census:
  `ff6fe4b949d6be7d985370d4629c407b5f6fe9ad638170224a55aa902d85d364`.
  Account/model admission was present; model-aware planning was absent. The plan
  also exposed a TTL hint without distinguishing it from actual future capacity.
- Source `config/subscription_provider_profiles.v1.json` keeps external provider
  activation gated. Local installed wrappers do not establish that the governed
  Executive path is armed, nor that subscription terms permit unattended work.
- GLM configured example: three accounts, each total cap 10, full-model cap 5,
  Flash cap 20. MiniMax configured example: one account cap 7. Alibaba configured
  example: three account entries with cap 7. Their real enrollment, shared-bucket
  independence, remaining balance and present usage were not verified. Never sum
  these examples into a claim of available fleet capacity.

## Implemented source in this operation

`control_plane/model_router.py` gains an optional strict `TaskFit` on the existing
router: C0/C1/C2/C3, independent business impact/topology and bounded C3 witness.
Legacy wire output stays unchanged. Consequential routine work remains on worker
tiers; real critical execution risk remains a lead/adjudication gate. C2 consumes
the existing stronger reviewed worker set without falsifying execution risk.
All classified worker constraints retain discrete fit facts in routing reasons.
No provider alias is armed and no new routing service is introduced.

The existing Phase 1B `route` and `create-job` commands consume the same fit.
Preview remains free of Runtime creation. Calibrated consequential build jobs set
the existing review gate; review jobs do not recursively create another review
requirement. Partial classification is rejected rather than silently ignored.

**Current native-integration boundary:** Executive TaskFit/Phase1B uses short
`C0`–`C3` tokens; the observed native consumer requires `C0_MECHANICAL`,
`C1_ROUTINE_BOUNDED`, `C2_COMPLEX_BOUNDED` and `C3_FRONTIER_JUDGMENT`.
[Finding6187002077](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1248#issuecomment-6187002077)
remains unresolved until an actual producer-consumer handoff is identified,
implemented and qualified. Routing reason codes and an unused conversion helper
do not prove that handoff. TaskFit source tests and native model-planning fixture
tests do not establish end-to-end native classification, installation or program
acceptance.

`ops/native_fabric/patches/lease_broker_model_planning.patch` repairs the incumbent
broker's advisory model planning. Its manifest and inert exact-source fixture
allow reproducible review without modifying the installed kit. The patch offers
an account/model intersection, preserves legacy pool-only calls and explicitly
marks quota and future capacity as unproven. It changes no live lease store,
provider setting, admission/lifecycle function or wrapper.

The program amendment remains on [#1247's existing carrier](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1247):
`docs/EXECUTIVE_FABRIC_CAPACITY_ORCHESTRATION_AMENDMENT.md` and its single
addendum pointer, under [#600 ruling6626757718](https://github.com/mastermindx-market-intelligence/Mastermind/issues/600#issuecomment-6626757718).
This #1248 retains the distinct TaskFit, Phase1B and native model-planning
implementation; it adds no competing Section 12. Proposed amendment text becomes
governing source only through protected acceptance and is consumed from the same
verified pin.

## Verification checkpoint

Synthetic, provider-free source tests:

```text
python3 -m pytest --noconftest -o addopts='' -q \
  tests/test_native_pool_model_planning_patch.py \
  tests/test_model_router_task_fit.py tests/test_executive_model_router.py
147 passed in 1.18s
```

The original router had no TaskFit and failed the new test import. Core routing
then passed while five native CLI cases failed; after CLI integration the routing
family passed. The final checkpoint above includes actual temporary Runtime
review-gate tests and patched native SQLite/CLI tests. Counts overlap; do not add
these successive runs. No live provider, worker, deployment or parent-return
canary was run by this operation.

### Broader normal-fixture verification

The six directly relevant suites pass with the repository's normal conftest:
`227 passed in 1.85s`. This includes task-fit, native model planning, existing
model routing, Chat cognition economics, worker-avenue law and the existing
capacity-economics bridge. The initial normal-conftest run had five test-only
failures because shared fixtures pre-populate the pytest temporary directory.
The side-effect assertions now use a dedicated absent CLI root and still require
that it remain absent. No production change was needed for that correction.
The 147-test set is a subset of this run, not additional independent coverage.

Before the original publication, protected master was fetched and remained the same pinned
`5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`. No governing/source drift was present.

## Current source integration (2026-11-04)

The original carrier is composed with protected
`cb8fa9132770b1967d585e323dd72b145c580601`. The router retains the complete
protected responsibility normalization, canonical digest/wire handling, coordinate
admission refusal, attended/frontier selection and first-lawful-tier guards.
Optional TaskFit is appended after responsibility_intent, preserving existing
positional callers. Removing only the reviewed TaskFit additions exactly
reconstructs the protected router. Phase1B, native patch, manifest and inert
fixture retain their original implementation bytes; the competing addendum
insertion is removed.

Native PID49998 completed exit 0 on Python 3.14.7: **309 tests passed, 0
failures/errors/skips**, JUnit 13.769s, across TaskFit, executive responsibility,
ModelRouter, attended routing, Chat cognition and native model-planning suites.
The new cases discriminate combined wire omission/digests, positional role
compatibility, coordinate-refusal despite task topology, all five C2 elevated
bands and tier ordering, critical/frontier/cognition guards, and legacy versus
explicit CLI review behavior. This is a current source test receipt, not a native
provider or installation result.

Tested router SHA256:
`614e9b167b8eb2f8eec2dc272836c76207b82a789f7c01eac0039851dec08446`.
TaskFit test SHA256:
`ea60a0ab39f3b06031c83eaa9b0ca1c166a5a8ad75767071511e9f29b5842b8d`.
All 13 observed input hashes and the prepared tree matched before/after that run.
The subsequent README/report qualifications change no tested code, test, patch,
manifest or fixture bytes; no further test run is claimed for those prose edits.
Current exact-head hosted checks and applicable protected review/release remain
required. Source publication and the full original program outcome are distinct.

## Incumbents: reuse, do not fork

| Existing carrier | Ownership / next qualification |
| --- | --- |
| Mastermind #600 | Existing integration, ready-frontier and native-return program; follow its canonical owner/ruling, not a historical session name as approver. |
| Mastermind #1041, observed head `b3816bb75fa328ec6df1f92a77e8377016efdc8e` | Closed-unmerged historical V1.x candidate, neither a rollout dependency nor a source to restore. Audit comment5976714813 identified schema conflict, an extra charge ledger, live depth change and serialized dispatch. Do not restore that implementation or transfer its held effects. |
| Mastermind #981 and #1013 | Native Codex principal/child role and attended orchestration bundle. Source installation and exact-parent proof remain distinct. |
| Mastermind #955 | Authenticated Claude Executive client edge; preserve existing auth/enrollment gates. |
| Mastermind #1217 | Universal Studio/Paper/fabric client projection; avoid a competing MCP projector. |
| Mastermind #1228 | Existing native policy-deployment owner. At the recorded census, held for reproduced migration, cross-session cooldown and hook-verification defects in review5408319347/comment5984558903. Current source/install status is not established by this report; reconcile actual writer, access and effects. No hot-editing provider homes or alternate installer here. |
| Mastermind #1143 | Live interconnect launch/return acceptance. Last owner observation is queue-only with configuration-generation disagreement; do not toggle/replay an arm. |
| Mastermind #947 | MiniMax route seam; this operation does not edit its policy or existing router-test file. |
| Macro #7103 / #7116 | Subscription catalog and existing multi-window quota economics. #7116 already intersects shared/model/short/weekly/monthly/concurrency budgets and measures cost per accepted output. Its unpublished two-file repair, denied publication and CI base gates must be reconciled by the incumbent; no alternate host/transport or replacement quota engine here. |
| Macro #8255 / #8311 | Reset economics and ordered real provider observations. Do not predict reset gifts or duplicate their ledger/normalizer. |

These are census observations, not assertions that each carrier is accepted,
installed or still at the same head. Recheck affected source at integration time.

## Capacity calculation and placement contract

For one eligible account/model, a concurrency ceiling is the minimum of remaining
account slots and remaining model slots, then further constrained by existing
pool fairness, host slots, root budget and reviewer capacity. Sum only genuinely
independent account contributions; full/Flash maxima on one account are not
additive. Outstanding reservations and active use must be disjoint. Parents and
children sharing the same subscription both count.

The existing quota owner then intersects all applicable budget windows using the
same model/task cohort's measured cost, including failed/repair/review work and
unsettled reservations. Remaining raw tokens, credits, requests and agent slots
are not interchangeable. A preview never reserves them. Existing claim-time
owners must atomically revalidate all shared resources; no principal may treat a
cached `grant_now` as permission to dispatch that many jobs.

A reset date is a recheck point, not guaranteed refill. Actual newer complete
provider observations may reveal an unscheduled refill; stale replies cannot
reverse that evidence. Shared subscriptions across hosts must be counted once by
verified resource identity. Quota exhaustion, concurrency saturation, unknown
telemetry, authentication/permission denial and uncertain effects are different
states with different recovery actions.

Historical public product evidence, retrieved 2026-10-05:

- Alibaba Token Plan Personal documentation, updated 2026-09-28, states monthly
  credits and removal of the weekly quota on 2026-09-22; Pro advertises 6-8 agents.
  It separately restricts use to interactive coding/agent tools and subscriber
  use. Product policy is not proof of the enrolled account's tier or balance.
  https://www.alibabacloud.com/help/en/model-studio/token-plan-personal-overview
- MiniMax Token Plan advertises concurrency ranges by subscription tier, including
  6-7 for Ultra. Its API rate-limit documentation separately lists RPM/TPM by
  model/interface. Do not substitute an API RPM number for agent concurrency.
  https://platform.minimax.io/subscribe
  https://platform.minimax.io/docs/guides/rate-limits
- GLM per-model values above are observed local configuration, not independently
  verified account entitlements. No cap increase is justified by this census.

## Native embedding and hierarchy release sequence

1. Accept the disjoint task-fit and model-planning repairs with exact-head tests,
   applicable exact-head review, required hosted checks and protected release
   requirements. Preserve all incumbent work.
2. Reconcile #1228's current source/installation disposition and actual original
   writer, access and effect constraints before its installer consumes accepted
   policy. The three recorded findings and prior M2 observations are historical
   evidence, not current-head or all-profile installation proof.
   Qualify Codex #981/#1013 and Claude #955 through #1143's existing launch/return
   acceptance; publishing a profile is not installation, trust or active selection.
3. Preserve the accepted Runtime/COO contract: default V1 remains, and an
   explicitly selected v5 plan uses the existing conserved budget of up to 16
   descendants under one original root. Preserve existing accounting, schema
   ownership, admission, cleanup and parent-return controls. #1041 is closed
   unmerged and is not a release dependency; do not restore its conflicting
   hierarchy or charge ledger. Planning topology, native harness nesting and
   admitted Job depth remain distinct. This selects or installs no native depth.
4. Reconcile #7103/#7116's original source/custody/denial/CI gates. Feed accepted,
   authenticated quota observations and cost cohorts into the existing capacity
   path, not a new pool-side quota ledger. Keep interactive-only products outside
   an unattended backend unless an appropriate entitled product is qualified.
5. Use the existing native pool installation owner to apply the exact hash-bound
   planning repair. Prove wrapper forwarding and actual account/model contention;
   never overwrite a moved broker or an active writer's unreviewed changes.
6. Run one admitted bounded project through each qualified native parent, with
   two eligible worker providers, a domain coordinator only where the selected
   accepted plan and actual admission permit, independent review, one repair and
   exact-parent consumption. Test
   stale/unknown quota, exhausted shared bucket, cancellation, interruption,
   root-budget exhaustion and orphan cleanup. Compare accepted work per scarce
   model budget and wall time against the baseline before increasing load.

## Historical post-publication boundary reconciliation

Candidate fab47ba8 was published as Mastermind PR#1248. A fresh incumbent-comment
read materially corrected the initial dependency plan: #1041 is a historical
V1.x proposal with a should-close-unmerged disposition, not the next release to
activate. #1228 has three reproduced source defects and an unresolved native
profile/source-access gate. These comments are evidence of incumbent disposition,
not protected new law or authority to close/edit their branches. This records
correction changes no runtime, classification, quota or native broker bytes.

Historical source baseline reported by the #1228 owner at that boundary: depth1,
fanout8, total reserved
children16. One fully reviewed item reserves9 slots; two reviewed items plus a
planner require19. Raising a YAML integer alone is invalid under the exact-value
loader and is not the authorized fix. Separate planning topology, native harness
nesting, actual Job depth and shared provider quotas. Retain the four optional
planning shapes rather than imposing a mandatory management chain. This
calculation records the earlier baseline; it is not the admission formula for
the currently accepted selected-plan v5 contract described above.

A separate disposable before/after discriminator used the actual original and
patched broker plus the same synthetic three-account configuration. Original
pool planning advertised30 slots while actual full-model admissions stopped at15;
model-aware candidate planning advertised15 and the unchanged admission path also
stopped at15. This confirms the concrete planning defect without touching a live
lease store or invoking a provider. Read-only inspection of the installed `pool`
wrapper shows `plan` forwards all arguments to the existing broker, so the new
flags do not require a competing wrapper. This is static forwarding evidence,
not a selected-client or production canary.

One exact-head review was requested through the existing Codex GitHub route:
comment5984828074. Response5984828564 asks the submitting account to create/link
Codex with GitHub. No review, worker START or reviewer findings were returned.
The request's explicit stop-on-unavailable condition applies; no alternate
account/model/transport or second review worker was used. Independent source
acceptance remains open. CI for fab47ba8 was running at this boundary; queued or
running checks are not failure and not acceptance.

## Compact frontier / DO_NOT_REDO

At the original checkpoint, this operation had not installed the broker patch,
called a provider, submitted a Job, changed authentication or armed runtime. Its
recorded native before-hash is historical evidence; this report does not reobserve
current installation. Source recovery continues on the original managed operation
and PR. The integrated TaskFit/Phase1B source requires current exact-head
qualification; native mapping, installation and original program acceptance
remain separately unproven. The original Codex request remains terminal at its
account-linking response, with no reviewer START or findings. A currently
authorized native-session review is a separate source-review avenue, not a retry,
impersonation or completion claim for that Codex request.

DO_NOT_REDO: do not recreate #7116 quota economics or its denied publication,
#1041's conflicting hierarchy/ledger, native MCP, account registry, reset ledger
or #1228 installer. Do not repeat the incumbent native-profile/fleet/source
refusals through another carrier. Do not re-run prior M2 prompt/guard proofs as
if they establish fleet adoption. Do not submit another Codex review until the
same account-linking gate is actually resolved.

Next: publish and read back the original-carrier integrated source and its
current regression evidence, then satisfy hosted checks and applicable protected
review/release controls. Keep #600's original program outcome and #1247's
amendment ownership intact. Native rollout separately requires reconciliation of
actual incumbent installation constraints, the classification handoff, supported
observed quota input, and admitted native launch/reviewed-return proof. The full
program remains incomplete.
