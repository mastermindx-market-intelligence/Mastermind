# Independent Fabric source audit: parent adjudication

## Scope and actual result

A separate admitted Fabric worker audited the source-level Executive intent -> admission -> cycle -> Fabric -> result -> return boundaries at Mastermind `bb85b429f2ffffd38408080ce4df7d6378c34100`. It did not audit the new planning documents, run the product, change source, install software, or qualify a production principal.

| Receipt field | Observed value |
|---|---|
| Run | `autonomy-exec-seam-audit-20261030-01` |
| Root | `meta-ceo-autonomy-census-20261030` |
| Parent | `web-autonomy-research-principal-20261030` |
| Terminal status | `TERMINAL`, `rc=0`, `signal=ok`, `root_verified=true`, `controller_return=RECORDED` |
| Retained response | 20,811 bytes |
| Response SHA-256 | `8ac5d68c2c0fb537abb809bae213b4079edf531bf1d713cfab7b3fe27bf89169` |
| Digest meaning | Exact complete adapter response; not a cryptographic attestation of source, model identity or artifact correctness |
| Native route evidence | Retained controller log selected GLM Flash and a remote Linux host; this is selection evidence, not independently attested served-model identity |
| Retry | `retry_allowed=false`; no replacement or replay |

The worker reported read-only `git show`/`git grep` access to the exact commit in an existing full clone. That access report is worker testimony. The parent independently opened the most consequential source locations in its own exact-pin checkout and checked them before incorporation.

**Disposition: consumed as a useful advisory source map; NOT accepted wholesale.** The raw report contains overbroad claims corrected below. The adapter's raw-report acceptance is deliberately left `NOT_ACCEPTED`; the pack does not present an unqualified independent approval. The worker is terminal, no reciprocal watcher was armed, and no repair/replacement child is pending. The parent resolved the answer-changing claims by reading the original source. This is not a source-code approval, production acceptance or independent review of the newly authored pack.

## Findings retained after source checks

### One admission sink is not execution

`control_plane/ceo_intent.py` contains validation and the `submit_intent` sink, with existing request identity/idempotency and strict-v2 provenance. Its admission receipt is not a dispatch receipt. `control_plane/executive_ceo_ingress.py` adds closed frame, trusted principal and host-provider gates. The selected client must use its actual schema and policy; a generic role string or native run label does not establish eligibility.

**Implication:** The first Office witness must prove the actual route from interpreted direction to the intended admitted Job/Attempt. A queued Job is not enough.

### COO execution needs its real installed composition

The inspected `executive_service.py` methods `_run_coo_cycle_once`, `_dispatch_cycle_job_exact` and `_coo_tick_loop` are separate from source admission. `executive_coo_cycle.py:run_once` sequences bounded plan/work/review/repair/handoff operations through existing owners. `executive_autonomy.py` validates receipt/policy/readiness evidence; source inspection does not establish an installed arm.

**Implication:** Qualify the current installed release, route, binding and readiness through their actual owners. Do not build a new dispatcher or rerun old acceptance commands from a document.

### Fabric terminal proof is more specific than a generic status

`AttendedFabricWorkerAdapter` verifies the current claim, pinned physical binding and original launch identity. Terminal process/descendant absence is not established by an ordinary terminal status alone. The source includes a distinct `prepare_fabric_cleanup` path that obtains and validates two authenticated owner readbacks and retains their exact matching package.

**Implication:** The consumer test should use the actual result/cleanup/assignment proof required by the chosen adapter. Neither a local PID check nor a model's “done” text can stand in for the remote owner.

### One canonical paid adapter has a deliberately narrow grant

The inspected `CanonicalPaidFabricWorkerAdapter._resolve` checks its exact installed binding, provider/profile and claim. It refuses write paths and validation commands and admits only its READ / READ+RESEARCH sealed-analysis grant.

**Implication:** Do not send a code-writing mission through this specific profile merely because a separate native Fabric worker can write. Select an actually admitted suitable route through the existing owner. This is not a global restriction on every paid Fabric worker.

### Result, review and return are distinct

The existing orchestration-result validator binds role and execution identity. Runtime review independence and supervisor retention/sealing are separate checks. `executive_terminal_return.py` and `executive_dialogue_observation.py` project original returns through their existing identities and phases.

**Implication:** A valid result or return projection does not automatically prove that the original principal consumed the disposition. The installed acceptance witness must observe that consumption separately.

## Corrections to the worker's broader assertions

| Raw-report assertion | Parent source check | Accepted bounded conclusion |
|---|---|---|
| Fabric `presence()` always returns UNKNOWN | `executive_fabric_adapter.py` returns LIVE for correctly bound STARTING/RUNNING/CANCELLING observations; terminal/error paths remain UNKNOWN | Generic terminal presence does not prove absence. Valid live presence is implemented. |
| Completion while generic presence is UNKNOWN is necessarily invalid | Source provides separate authenticated cleanup and retained terminal proof paths | Judge completion by the actual owner-specific required evidence, not the generic presence method alone. |
| Executive MCP has exactly five tools | `integrations/executive_mcp/server.py` has multiple profile builders, including web CEO v2/v3 and sessions; current discovered connector exposes additional session actions | The five-tool description is not a current universal surface census. Inspect the actual selected profile. |
| Paid Fabric cannot do code changes | The read/research ceiling is enforced inside the specific canonical paid sealed-analysis adapter | Do not generalize that profile to every native/paid Fabric avenue. |
| Only one mission can run across the organization | The inspected locks govern the particular service/serialized-worker dispatch binding | Scope the concurrency limitation to that binding; broader organizational capacity requires its own evidence. |
| Wake is globally unarmed and unwired; one parent path is the only live route | The cited Wake documentation includes historical PR-1/PR-2 state. Current source also contains route/descriptor/binding checks and native Wake adapters. No installed global Wake census was performed. | The selected Wake route needs actual installed proof. Source/history cannot establish a universal live outage or exclusive live path. |
| Source and tests establish a current test pass | The audit read source and test locations; it did not execute the test suites | Treat the result as source inspection, not fresh test qualification. |
| Generic dispatch restrictions show every v1 intent is universally undispatchable | The inspected control-service path is intentionally restricted; other exact owner/profile paths must be assessed separately | Use the actual intended schema/service path; do not turn a local restriction into a company-wide absence claim. |

These corrections are material. They prevent unnecessary platform rewrites, incorrect blocker claims and a false belief that a successful independent worker report is itself acceptance.

## Minimal source reading for the receiving runtime integrator

All references below are immutable at the same pin. Read the named functions and their immediate tests/imports, not every large file by default.

- [ceo_intent.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/ceo_intent.py): `validate_intent`, `submit_intent` and idempotent replay checks.
- [executive_ceo_ingress.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_ceo_ingress.py): closed schemas, `handle_frame`, `_require_v2_admission`.
- [executive_service.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_service.py): `_dispatch_cycle_job_exact`, `_run_coo_cycle_once`, `_coo_tick_loop`, `_project_terminal_return`.
- [executive_coo_cycle.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_coo_cycle.py): `run_once` and finite-control/review sequencing.
- [executive_fabric_adapter.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_fabric_adapter.py): `presence`, `absence_verified`, `terminate`, `prepare_fabric_cleanup`, `_resolve`.
- [executive_fabric_composition.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_fabric_composition.py): installed physical binding validation.
- [executive_paid_fabric_adapter.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_paid_fabric_adapter.py): `_resolve`, `collect_result`; [paid supervisor](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_paid_supervisor.py): exact owned terminal evidence.
- [executive_orchestration_result.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_orchestration_result.py): `validate_envelope`; [terminal return](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/executive_terminal_return.py): original-result projection.
- [Executive MCP server](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/integrations/executive_mcp/server.py): actual profile builders rather than a historical global tool count.
- [Wake dispatcher](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bb85b429f2ffffd38408080ce4df7d6378c34100/control_plane/wake_dispatcher.py) and `integrations/executive_wake/`: qualify only the actual selected route and installed composition.

## Revised test recommendations

Use isolated tests for admission identity, out-of-order/duplicate callbacks, result mismatches, wrong profile and review independence. Use an actual authorized useful mission for installed proof; do not create dummy production Jobs solely to test an available tool. Exercise the chosen adapter's real cleanup/result evidence, not a blanket inference from UNKNOWN. Verify original-parent consumption after projection. Qualify the selected Wake route independently of the COO tick loop.

The separate audit improved the source map and revealed where generic descriptions could mislead delivery. Its raw output is retained by the original Fabric owner under the receipt above; this public document contains the adjudicated conclusions and necessary provenance, not the worker's host paths or an unfiltered transcript.
