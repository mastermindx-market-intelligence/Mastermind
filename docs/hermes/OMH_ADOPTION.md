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

### O1 — Pinned pure core and canonical proposal adapter (source implemented)
Create `integrations/hermes_omh/` and the unique canonical test module `tests/test_hermes_omh.py`. Vendor `src/plugin_bundle/omh/dag_core.py`, its MIT license and provenance. Build `prepare_execution_plan(nodes, *, policies, root_job_id, plan_attempt_id)` with up to eight OMH definition nodes (the donor NODE_FIELDS, not persisted run/status records). Policy is explicitly supplied per node; no guessed authorities, provider, model, principal, root or retry allowance. The output is source/planning data, never an admission receipt. Preserve all dependencies through stable topological ordering. Require supplied write scope to remain within each policy and refuse unordered overlapping writes.

Test first: independent lanes + downstream verification; unknown/duplicate/cyclic/forward references; 0/9 nodes; malformed strings/containers; bool-as-int; deep and oversized JSON; directory/case/Unicode scope overlap; traversal/globs/absolute paths; no inferred placement; identity separation; input immutability; zero filesystem/network/process/store effects in the pure path. Verify using the incumbent canonical plan validator rather than a copied schema.

### O2 — Operator consumer and qualification (source implemented; release evidence pending)
Provide a bounded stdin/file CLI under `python -m integrations.hermes_omh`, exact documented example, safe value-free refusal diagnostics, tests for CLI input/output and the original Executive parser. New source paths only; do not edit active #2134/#2147/H24 runtime or memory work. Run affected incumbent plan and Hermes delegation tests.

### O3 — Release and installed consumer proof (depends O2)
Self-check exact diff, run required CI, use normal protected publication/release controls without self-approval or manual self-merge. Any live Hermes registration requires separately qualified native profile/session binding and release; do not remove allowlists or change service configuration to manufacture a canary. Preserve original effect uncertainty and writers.

## Broader adoption remains open

Memory intelligence must land through the existing Agent OS/native MemoryProvider packet in #2159, not a second OMH store. Curated skill selection, evidence rendering and optional code intelligence remain subsequent selectively integrated capabilities; this first topology slice does not claim those outcomes. Native session/role enrollment and production acceptance remain independently evidenced.

## Execution ownership

Principal retains architecture and source integration. One paid Fabric leaf may implement the frozen O1/O2 package; economical AUTO placement, C2 bounded engineering, no Fable required. Direct principal source work is limited to integration/adjudication or a recorded lower-overhead/capability exception. The fresh attended operation root is the operation ID above; these labels are correlation, not Runtime identity/authentication. No duplicate worker, queue or watcher.

## Implementation adjudication

The original paid child `hermes-omh-adoption-20261106-c3-core-01` was retained as `REQUEST_REFUSED_BEFORE_LAUNCH / EXECUTION_NOT_ELIGIBLE`, controller31674 exited75, no worker START or result. Same-run replay is forbidden. It was not resubmitted or moved to another carrier. Direct source work continued in the original managed parent workspace under `NO_ELIGIBLE_PRE_EFFECT_WORKER`; no worker authored the implementation.

CI inspection found the main gate discovers only `tests/**/test_*.py`, while the existing Hermes-specific workflow does not cover a new package. The source-only scope therefore includes the one new canonical test path above, rather than a new workflow or silently uncollected tests. Existing production/source owners remain untouched.

Initial TDD proof failed on the missing adapter. The first implementation passed89 cases. A second red run exposed five Windows-ambiguous scope paths and argparse's raw argument echo; these are repaired with explicit path exclusions and value-free parser diagnostics. The expanded suite passed99 cases, including1,536 generated DAG/input-order combinations inside one test. These are local source checks, not native role installation or model-performance evidence.

## Source qualification receipt

- Combined command: `python3 -m pytest -q -o addopts='' tests/test_hermes_omh.py tests/test_executive_plan_schema_versions.py integrations/hermes_delegate/tests/test_delegate.py` -> **141 passed, 9 subtests passed**, exit0.
- Actual CLI example emitted a three-step canonical proposal; the original parser accepted it and its plan SHA-256 was `6e83ce32433558c5a8ee9aa0d34929d6878116ea72ac6d8d51d8a3142d2447f5`. Both admission/dispatch flags were false.
- `python3 -m compileall -q integrations/hermes_omh` and `git diff --check` passed. No provider call or live Hermes profile was used.
- Protected master observed at `ad6275a9c4d237bce75e52d0d6a8f41264b4ded5`; governing skillpack/review/delivery files, original plan parser, its imported acceptance/redaction code and canonical CI discovery/runner files were unchanged relative to the retained source pin. No ancestry-only rebase was performed.
- Structured author self-review checked dependency preservation, lexical policy containment versus conservative conflict folding, malformed/unbounded input, evidence labels, copied-source licensing and CI discovery. This is `SELF_REVIEWED`, not an independent review or formal GitHub approval.
- An incidental Git auto-maintenance warning reported denied access to another workspace index; the requested source read and compatibility comparison completed. No GC/repack, foreign index or permission repair was attempted.

Current source state: **BUILT_NOT_PROVEN live**. Source publication, hosted checks, protected release, and future native registration/admission remain distinct. Broader memory/skills adoption remains on the existing programme, not marked complete by this receipt.
