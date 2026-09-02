# Operation Assurance A2 — Bounded Gather/Source-Compiler Seam Design

**Status:** `NARROW CONTROLLING DESIGN / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`
**Date:** 2026-09-01
**Owner:** Fable principal, operation `mastermind-operation-assurance-full-production-20260901-fable-003`, under the standing Chairman completion commission; Sol retains release acceptance.
**Protected reconciliation at drafting:** `mastermindx-market-intelligence/Mastermind@21a721427743fdae6d513eeb0f993ebd1c327a81` (contains protected OLS-F0 `f0ea4847…` and OLS-A1 `c6af57d1…`; later reconciliations are pinned in the release PR's body)
**Carrier:** the fable-003 child carrier in #agent-dispatch

This design satisfies the Executive Steward reconciliation's OLS-A2 predecessor gate 3: it is the
"separately accepted bounded gather/source-compiler seam" record. It authorizes no implementation
by itself; the A2 implementation wave starts only after this record is protected.

## 1. Narrow precedence

This design wins on: the A2 seam boundary, the first-vertical owner-adapter set, the frozen first
target operation, and the A2 file plan. For every other subject the existing protected stack wins:
the 2026-08-31 wire-release finalization, the immutable-report clarification, the model-fidelity
amendment, the trusted-input clarification, the controlling execution overlay, the Executive
Steward reconciliation (whose §5–§8 gates and prohibitions this design implements, not amends),
the SCF and observability reconciliations, and the parent law/design/plan.

## 2. Seam composition (implements the protected Steward-reconciliation §6 pipeline)

```text
existing canonical owner adapters
-> immutable owner-native facts and source receipts
-> bounded gather/source-compiler seam
-> closed mastermind.operation_assurance_model.v1 bundle with provenance receipts
-> protected OLS-A1 checker (unchanged; never side-reads)
-> immutable mastermind.operation_assurance_report.v1
```

Two modules, one CLI, strict separation:

- `control_plane/operation_assurance_sources.py` — the ONLY module with read I/O. It gathers
  owner-native facts from an explicitly named owner surface at an explicitly pinned revision and
  emits an immutable plain-data source bundle (`mastermind.operation_assurance_source_bundle.v1`,
  the schema already frozen and parsed by the protected A1/A2-S0 contract family). Read-only:
  no network beyond the named owner read, no write, no cache, no persistence, no retry loops.
- `control_plane/operation_assurance_compiler.py` — pure (stdlib-only, zero I/O). Compiles one
  source bundle into one closed `mastermind.operation_assurance_model.v1` plus per-element
  `source_refs`, deterministically. Same purity law as the protected A1 modules.
- `scripts/operation_assurance_compile.py` — bounded CLI: gather (or accept a bundle on
  stdin/file), compile, emit the model bundle to stdout; deterministic exits per the A1 pattern
  (0 valid output, 2 invalid input/refusal, 3 internal refusal).

## 3. First owner adapter (frozen): AGENT_OS

The first vertical implements exactly ONE owner adapter: **Agent OS records** — the machine-schema
files under the Macro repository's `agentos/` tree (`agentos.workstream.v1`,
`agentos.handoff.v1`), read at ONE pinned git revision.

Why this owner first: real owner-native data exists today; records are git-revisioned, giving
exact provenance for free; the read is trivially bounded and side-effect free; and the accepted
CCL-A2 source-composer already demonstrates the accepted receipt shape for an `AGENT_OS`
content-bound attestation. Frontmatter in these records is validated machine schema
(`scripts/agentos.py validate` in the owning repository), not prose — compiling it does not
violate the no-prose-parsing law; the record BODY (human truth) is never parsed.

Receipt law per fact (implements Steward-reconciliation §7, mirroring the accepted CCL-A2
attestation fields): `source_owner="AGENT_OS"`, source repository + pinned commit SHA, record
path, record schema name, content digest (sha256 of the record bytes), `observed_at`, coverage
statement (which record families were read; truncation explicit), and conflict/correction state.
Missing or unreadable records become explicit `SOURCE_MISSING` / `SOURCE_PARTIAL` facts — never
healthy defaults.

Adapters explicitly NOT in this vertical (each `NOT_BUILT`, stated in the bundle coverage):
Executive OS runtime (Job/Attempt/Worker/Event), Wake/dialogue, RuntimeBinding, Capacity,
SCF/GitHub (whose packets OLS must never counterfeit per the SCF reconciliation), Runtime
Observability. Each later adapter is its own bounded acceptance.

## 4. First target operation (frozen)

The first real compiled operation is the **`WS:OPERATION-ASSURANCE` workstream itself**: its wave
DAG as recorded in `agentos/workstreams/WS-OPERATION-ASSURANCE.md` at the pinned revision.

Mapping (deterministic, closed):
- each wave → a model state-bearing unit: `todo`/`in_progress`/`awaiting_ci`/`done`/`dropped`
  statuses map to a closed marking vocabulary;
- `depends_on` edges → gating transitions (a wave may start only when its dependencies are done);
- `next_action` on a non-terminal wave → a declared obligation owned by the workstream owner seat;
- a schema-valid `wait` object → a typed external gate/intentional wait (never silent inactivity);
- workstream `status` → the operation's declared terminal/ongoing classification.

The compiled model is checked by the protected A1 engine for exactly its existing property set
(option-to-complete, proper completion, universal progress, starvation under declared fairness,
etc.). Expected honest outcome for a live workstream: `EXTERNALLY_GATED` or `INTENTIONAL_WAIT`
progress dispositions where waits are declared, `NO_PROGRESS` findings where a non-terminal wave
carries neither a dependency, a wait, nor a next action — that last case is the real
organizational black-hole class this vertical makes detectable.

## 5. Trust ceiling (unchanged, restated as binding on A2)

A compiled bundle is `PROVENANCE_CLOSED_UNATTESTED / AUTHOR_DECLARED_ONLY` at most. Gathering
with correct receipts does NOT mint `CURRENT_SOURCE_ATTESTED`, `SOURCE_CONTRACT_VALIDATED`, or
`RUNTIME_REPLAY_CONFIRMED`; those require separately accepted attestation capabilities that remain
`NOT_BUILT`. The compiler cannot self-upgrade; the A1 checker's caps apply unchanged.

## 6. No-rebuild boundary (implements Steward-reconciliation §8)

The seam must not: create a parallel federated reader, source graph, cache, store, scheduler, or
second Steward; copy Steward dataclasses; side-read owners from the A1 checker; parse Slack/PR
prose; elect sources by recency; persist gathered facts anywhere; or import
`chairman_cognition_sources` (its receipt SHAPE is the accepted pattern; its schema family and
consumer are a different program).

## 7. Required failure states (subset of the program's §13 vocabulary)

`INVALID_SOURCE_BUNDLE`, `SOURCE_MISSING`, `SOURCE_PARTIAL`, `SOURCE_TRUNCATED`, `SOURCE_STALE`,
`SOURCE_CONFLICTED`, `SOURCE_SUPERSEDED`, `SOURCE_ATTESTATION_UNAVAILABLE`, `INPUT_TOO_LARGE`,
`DUPLICATE_KEY`, `UNRESOLVED_REFERENCE`, `UNSUPPORTED_SEMANTICS` — each fails closed with the
canonical owner named and never degrades to an apparently healthy compilation.

## 8. Implementation wave boundary

One branch, one PR, TDD-first, changed paths exactly: the two `control_plane/` modules, one
`scripts/` CLI, fixtures/tests under `tests/`, and nothing else. Release ceiling after protection:
`BUILT_NOT_PROVEN / OFFLINE_SOURCE_COMPILER / REPORT_ONLY / PRODUCTION_INERT`. The implementation
must prove one real end-to-end run: gather `WS:OPERATION-ASSURANCE` at a pinned revision →
compile → protected A1 CLI → immutable report, with byte receipts in the PR body.
