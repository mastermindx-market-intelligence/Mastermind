# Selective Oh My Hermes integration

Operation: `hermes-omh-adoption-20261106-c3`. Parent: Hermes teammate evolution, Mastermind PR #2159; assessment comment 6698869434. Current Chairman direction authorizes implementation of the selective-adoption recommendation, not a wholesale plugin install.

Protected source/procedure: `b0a280be474ae67e7681f68dc0dfe3af2aea1626`. Donor: `rlaope/oh-my-hermes@5ead1032360edadd4b3a749f234f3830324de3b2` (v4.0.6). Existing Hermes source pin remains `1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

## Design and alternatives

Reuse the donor's pure, standard-library DAG algorithms unchanged behind a strict Mastermind proposal boundary. Translate graph definitions into the existing `mastermind.execution_plan/v4` contract and validate with `control_plane.executive_orchestration_result._validate_plan`. Executive OS alone admits plans and creates Jobs/Attempts; Fabric alone selects workers/providers. A prepared plan is never an admitted or running plan.

Rejected alternatives: installing all OMH hooks/tools/memory would conflict with existing owners; rebuilding topology from scratch would discard useful MIT source and tests; adopting OMH's persisted DAG runner would introduce duplicate lifecycle/retry state.

The donor core ignores unknown references unless the caller checks them, deduplicates IDs, and compares write scopes literally. Our boundary must reject duplicate/unknown/self/cyclic dependencies before calling it, bound the input, and compare safe relative write scopes conservatively (directory ancestry, case/Unicode aliases). It imports no OMH runtime, memory provider, dispatcher, credentials or installer. No automatic recovery/re-offer or provider fallback is adopted.

## Useful first journey and acceptance

A Hermes/operator graph definition plus separately supplied host planning policy becomes a deterministic canonical plan proposal, dependency layers, unweighted critical path and bottleneck explanation. Malformed graphs, over-budget graphs, unsafe scopes, parallel overlapping writers, authority-bearing extra fields and policy widening refuse without partial output. The CLI can consume a bounded JSON document and emit this proposal without loading a live Hermes profile or touching runtime state.

`DONE_WHEN` for the first source slice: exact pinned donor bytes and MIT notice retained; strict adapter; actual canonical validator consumer; operator CLI; positive and negative tests; readback of published source and current CI. This does not complete live Hermes rollout or the larger teammate programme.

## Implementation task tree

### O1 — Pinned pure core and canonical proposal adapter (ready)
Create `integrations/hermes_omh/` only. Vendor `src/plugin_bundle/omh/dag_core.py`, its MIT license and provenance. Build `prepare_execution_plan(nodes, *, policies, root_job_id, plan_attempt_id)` with up to eight OMH definition nodes (the donor NODE_FIELDS, not persisted run/status records). Policy is explicitly supplied per node; no guessed authorities, provider, model, principal, root or retry allowance. The output is source/planning data, never an admission receipt. Preserve all dependencies through stable topological ordering. Require supplied write scope to remain within each policy and refuse unordered overlapping writes.

Test first: independent lanes + downstream verification; unknown/duplicate/cyclic/forward references; 0/9 nodes; malformed strings/containers; bool-as-int; deep and oversized JSON; directory/case/Unicode scope overlap; traversal/globs/absolute paths; no inferred placement; identity separation; input immutability; zero filesystem/network/process/store effects in the pure path. Verify using the incumbent canonical plan validator rather than a copied schema.

### O2 — Operator consumer and qualification (depends O1)
Provide a bounded stdin/file CLI under `python -m integrations.hermes_omh`, exact documented example, safe value-free refusal diagnostics, tests for CLI input/output and the original Executive parser. New source paths only; do not edit active #2134/#2147/H24 runtime or memory work. Run affected incumbent plan and Hermes delegation tests.

### O3 — Release and installed consumer proof (depends O2)
Self-check exact diff, run required CI, use normal protected publication/release controls without self-approval or manual self-merge. Any live Hermes registration requires separately qualified native profile/session binding and release; do not remove allowlists or change service configuration to manufacture a canary. Preserve original effect uncertainty and writers.

## Broader adoption remains open

Memory intelligence must land through the existing Agent OS/native MemoryProvider packet in #2159, not a second OMH store. Curated skill selection, evidence rendering and optional code intelligence remain subsequent selectively integrated capabilities; this first topology slice does not claim those outcomes. Native session/role enrollment and production acceptance remain independently evidenced.

## Execution ownership

Principal retains architecture and source integration. One paid Fabric leaf may implement the frozen O1/O2 package; economical AUTO placement, C2 bounded engineering, no Fable required. Direct principal source work is limited to integration/adjudication or a recorded lower-overhead/capability exception. The fresh attended operation root is the operation ID above; these labels are correlation, not Runtime identity/authentication. No duplicate worker, queue or watcher.
