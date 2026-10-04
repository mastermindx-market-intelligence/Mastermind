# Fabric capacity and orchestration upgrade: execution record

Operation: `fabric-capacity-orchestration-upgrade-20261005-sol-001`.
Current Chairman intent: upgrade native Codex/Claude orchestration, cheaper-worker
utilization, multi-level hierarchy, concurrency and future-quota-aware routing.
Protected procedure/source pin: `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`;
skillpack 1.0.1 / bootstrap major 1. Actual selected model/mode is unverified.
This record is evidence and continuation, not a second task queue or authority.

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

`ops/native_fabric/patches/lease_broker_model_planning.patch` repairs the incumbent
broker's advisory model planning. Its manifest and inert exact-source fixture
allow reproducible review without modifying the installed kit. The patch offers
an account/model intersection, preserves legacy pool-only calls and explicitly
marks quota and future capacity as unproven. It changes no live lease store,
provider setting, admission/lifecycle function or wrapper.

Section 12 of `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md` is the proposed
protected-law update: useful native principal capacity, fresh per-child fit,
conserved hierarchical budgets, multidimensional headroom, current observations,
quality-adjusted economics and separate production qualification. It becomes
protected law only through normal acceptance; this branch does not self-arm it.

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

Before publication, protected master was fetched and remained the same pinned
`5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`. No governing/source drift was present.

## Incumbents: reuse, do not fork

| Existing carrier | Ownership / next qualification |
| --- | --- |
| Mastermind #600 | Existing Fable integration umbrella and ready-frontier/native-return program. |
| Mastermind #1041, observed head `b3816bb75fa328ec6df1f92a77e8377016efdc8e` | Historical V1.x hierarchy candidate, NOT an approved release dependency. Fable/Opus audit comment5976714813 recommends closing unmerged: schema conflict, extra charge ledger, live depth change and serialized dispatch. Preserve incumbent disposition; do not merge wholesale or transfer custody. |
| Mastermind #981 and #1013 | Native Codex principal/child role and attended orchestration bundle. Source installation and exact-parent proof remain distinct. |
| Mastermind #955 | Authenticated Claude Executive client edge; preserve existing auth/enrollment gates. |
| Mastermind #1217 | Universal Studio/Paper/fabric client projection; avoid a competing MCP projector. |
| Mastermind #1228 | Existing native policy-deployment owner, currently held for reproduced migration, cross-session cooldown and hook-verification defects in review5408319347/comment5984558903. Repairs and source-custody refusals remain with the incumbent. No hot-editing provider homes or alternate installer here. |
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

Current public product evidence, retrieved 2026-10-05:

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
   independent review and required hosted checks. Preserve all incumbent work.
2. Have #1228's incumbent repair its three reproduced defects and reconcile its
   original action/custody gates before its installer consumes accepted policy.
   Preserve observed M2 settings as prior evidence, not all-profile runtime proof.
   Qualify Codex #981/#1013 and Claude #955 through #1143's existing launch/return
   acceptance; publishing a profile is not installation, trust or active selection.
3. Preserve the current depth-one Runtime/COO baseline and close the real V1
   capacity/worker-transport parallelism gap first. Do NOT release #1041 wholesale:
   its incumbent Fable/Opus disposition recommends closure unmerged. A later
   bounded hierarchy extension must be explicitly reconciled through the same
   Runtime/COO/Capacity owners, use the existing accounting rather than a second
   charge ledger, preserve schema ownership and prove conservation/cleanup.
   Desired multi-level planning labels are not already-admitted Job depth.
4. Reconcile #7103/#7116's original source/custody/denial/CI gates. Feed accepted,
   authenticated quota observations and cost cohorts into the existing capacity
   path, not a new pool-side quota ledger. Keep interactive-only products outside
   an unattended backend unless an appropriate entitled product is qualified.
5. Use the existing native pool installation owner to apply the exact hash-bound
   planning repair. Prove wrapper forwarding and actual account/model contention;
   never overwrite a moved broker or an active writer's unreviewed changes.
6. Run one admitted bounded project through each qualified native parent, with
   two eligible worker providers, a domain coordinator only if installed depth
   permits, independent review, one repair and exact-parent consumption. Test
   stale/unknown quota, exhausted shared bucket, cancellation, interruption,
   root-budget exhaustion and orphan cleanup. Compare accepted work per scarce
   model budget and wall time against the baseline before increasing load.

## Post-publication boundary reconciliation

Candidate fab47ba8 was published as Mastermind PR#1248. A fresh incumbent-comment
read materially corrected the initial dependency plan: #1041 is a historical
V1.x proposal with a should-close-unmerged disposition, not the next release to
activate. #1228 has three reproduced source defects and an unresolved native
profile/source-access gate. These comments are evidence of incumbent disposition,
not protected new law or authority to close/edit their branches. This records
correction changes no runtime, classification, quota or native broker bytes.

Existing source baseline (per the #1228 owner): depth1, fanout8, total reserved
children16. One fully reviewed item reserves9 slots; two reviewed items plus a
planner require19. Raising a YAML integer alone is invalid under the exact-value
loader and is not the authorized fix. Separate planning topology, native harness
nesting, actual Job depth and shared provider quotas. Retain the four optional
planning shapes rather than imposing a mandatory management chain.

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

The operation retains its managed workspace/branch. Source implementation/tests,
the inert patch artifact and proposed law are published on PR#1248. The native
broker remains at the before hash; no installation, provider call, Job submission,
authentication change or runtime arm occurred. The review request is terminal at
the account-linking gate, not active computation. The documentation correction
must be committed/read back on the same PR; no code-test rerun is claimed for a
docs-only update.

DO_NOT_REDO: do not recreate #7116 quota economics or its denied publication,
#1041's conflicting hierarchy/ledger, native MCP, account registry, reset ledger
or #1228 installer. Do not repeat the incumbent native-profile/fleet/source
refusals through another carrier. Do not re-run prior M2 prompt/guard proofs as
if they establish fleet adoption. Do not submit another Codex review until the
same account-linking gate is actually resolved.

Next: publish the corrected same-PR records, reconcile required checks and make
the integration delta available to the existing #600 owner. Acceptance then needs
an authorized independent review on the exact final candidate. Runtime rollout
separately requires incumbent fixes, supported observed quota input and admitted
native launch/reviewed-return proof. The full Chairman mission remains incomplete.
