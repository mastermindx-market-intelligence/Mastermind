# Operation Assurance A2 — Bounded Gather/Source-Compiler Seam Design

**Status:** `NARROW CONTROLLING DESIGN / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`
**Date:** 2026-09-01 (repaired 2026-09-02 per Sol review `5086088649` on PR #339)
**Owner:** Fable principal, operation `mastermind-operation-assurance-full-production-20260901-fable-003`, under the standing Chairman completion commission (COO operator authority).
**Protected reconciliation at repair:** `mastermindx-market-intelligence/Mastermind@9ed1a2020246348118a0c83e4207284c5bd51d60` (contains protected OLS-F0 `f0ea4847…` and OLS-A1 `c6af57d1…`; the release PR body pins the exact current base)
**Carrier:** the fable-003 child carrier in #agent-dispatch

This design satisfies the Executive Steward reconciliation's OLS-A2 predecessor gate 3: it is the
"separately accepted bounded gather/source-compiler seam" record. It authorizes no implementation
by itself; the A2 implementation wave starts only after this record is protected.

## 1. Narrow precedence

This design wins on: the A2 seam boundary, the first-vertical owner-adapter set, the frozen first
target operation, the supported-property subset, and the A2 file plan. For every other subject the
existing protected stack wins: the 2026-08-31 wire-release finalization, the immutable-report
clarification, the model-fidelity amendment, the trusted-input clarification, the controlling
execution overlay, the Executive Steward reconciliation (whose §5–§8 gates and prohibitions this
design implements, not amends), the SCF and observability reconciliations, and the parent
law/design/plan.

## 2. Seam composition (implements the protected Steward-reconciliation §6 pipeline, in full)

```text
AGENT_OS gather adapter (sole I/O)
-> immutable owner-native facts and content-bound source receipts (invocation-local plain data)
-> existing Executive Steward pure composition (mastermind.executive_steward.result.v1)
-> pure OLS source compiler (consumes the Steward result + the exact facts the Steward accepted)
-> closed mastermind.operation_assurance_model.v1 with per-element source_refs
-> protected OLS-A1 checker (unchanged; never side-reads)
-> immutable mastermind.operation_assurance_report.v1
```

The mandatory Steward step is real, not decorative: the seam presents every gathered WORKSTREAM
fact (`agentos.workstream.v1` — exactly one `ResponsibilityFact` per `WS:<KEY>` identity, with
`source_owner=AGENT_OS`, the only owner the real API admits for that family) to the EXISTING
`control_plane/executive_steward.py` snapshot composition. Handoff records (`agentos.handoff.v1`)
are NEVER presented to the Steward — the real API has no lawful home for them, and presenting them
as duplicate `WS:`-keyed facts would force `ambiguous_responsibility_join` refusals; they are
gathered as evidence-only facts that feed coverage, supersession, and receipt context alongside
the Steward result. The compiler consumes
(a) the Steward result for identity grouping, currentness/degradation classification, and
source-failure semantics, and (b) the exact owner-native wave/dependency fields of only those
records the Steward composition accepted. The compiler performs ZERO identity resolution,
deduplication, conflict election, or source normalization of its own — the Steward is the only
identity/source normalizer, and it is reused, never copied, subclassed, or reimplemented.

Modules, one CLI, strict separation:

- `control_plane/operation_assurance_sources.py` — the ONLY module with read I/O. It gathers
  owner-native facts from the named owner surface at one explicitly pinned revision and emits the
  invocation-local source-facts structure defined in Section 3. Read-only: no network beyond the
  named owner read, no write, no cache, no persistence, no retry loops.
- `control_plane/operation_assurance_compiler.py` — pure (stdlib-only, zero I/O). Feeds the facts
  through the existing Steward composition, then compiles the accepted facts into one closed
  `mastermind.operation_assurance_model.v1` with per-element `source_refs`, deterministically.
- `scripts/operation_assurance_compile.py` — bounded CLI: gather (or accept the source-facts
  structure on stdin/file), compile, emit the model bundle to stdout; deterministic exits per the
  A1 pattern (0 valid output, 2 invalid input/refusal, 3 internal refusal).

## 3. Source-facts wire — defined BY THIS DESIGN, invocation-local, non-persistent

No protected source-bundle or predecessor "A2-S0" wire exists in the repository today; this
design DEFINES the wire and the implementation wave freezes it by executable test. It is named
`mastermind.operation_assurance_source_facts.v1` and is strictly **invocation-local and
non-persistent**: it exists only as the in-process value (or the caller-owned stdin/stdout bytes)
of one compile invocation. No module may write it to any file, store, cache, or database; there is
no source store, no "latest bundle" location, and no new truth owner. Re-gathering always produces
a fresh structure at a fresh pinned revision.

Per-fact fields (closed): `source_owner` (exactly `"AGENT_OS"` in this vertical), source
repository, `revision` (the full 40-hex commit SHA — abbreviated SHAs are refused), record path,
record schema name, `content_digest` (sha256 of the record bytes), `observed_at` (see the
single-cutoff rule), the validated frontmatter payload, per-family `coverage` (which record
families were read; truncation explicit), and `conflict`/`supersession` state.

## 4. First owner adapter (frozen): AGENT_OS

The first vertical implements exactly ONE owner adapter: **Agent OS records** — the machine-schema
files under the Macro repository's `agentos/` tree (`agentos.workstream.v1`,
`agentos.handoff.v1`), read at ONE pinned full-SHA git revision.

Why this owner first: real owner-native data exists today; records are git-revisioned, giving
exact provenance; the read is trivially bounded and side-effect free; the accepted CCL-A2
source-composer demonstrates the accepted receipt shape for an `AGENT_OS` content-bound
attestation; and the Steward's own `SourceOwner.AGENT_OS` fact family is the designed home for
exactly this owner. Frontmatter in these records is validated machine schema (`scripts/agentos.py
validate` in the owning repository), not prose — the record BODY (human truth) is never parsed.

Owner-seat derivation (closed grammar, not prose interpretation): the workstream `owner` field is
a schema-noted accountable-seat string; the adapter derives the Steward `Seat` enum value by
matching the closed token grammar `\((CHAIRMAN|CEO|COO|WORKER) seat\)` (case-insensitive on the
token) against that string. Exactly one match is required; zero or multiple matches make the
record an explicit `SOURCE_PARTIAL` fact — the seat is never guessed from free prose.

Freshness derivation (closed, and deliberately humble): the AGENT_OS adapter ALWAYS emits
`Freshness.UNKNOWN` for every fact — never `CURRENT` — because no accepted attestation capability
exists that could establish semantic currentness from Agent-OS-only evidence. The existing Steward
composition then mechanically raises its non-current/degraded issues for every fact, so every
compiled model carries explicit non-current applicability by construction; nothing downstream can
launder schema validity into currentness.

Attestation and time law:
- the pinned `revision` MUST be the full canonical SHA of the Agent OS repository commit actually
  read; the adapter records how it resolved that revision;
- ONE `observed_at` cutoff covers the entire gather — per-file observation drift is refused;
- a missing, unreadable, or truncated record becomes an explicit `SOURCE_MISSING` /
  `SOURCE_PARTIAL` / `SOURCE_TRUNCATED` fact — never a healthy default;
- records disagreeing on the same identity at one revision become `SOURCE_CONFLICTED`;
- corrections are immutable and append-only: a later revision SUPERSEDES an earlier gather by
  producing a NEW source-facts structure and a NEW compiled model/report; nothing is rewritten;
- Agent-OS-only evidence can never yield whole-operation currentness: compiled applicability is
  capped at the authored/declared tier, and no compilation output can produce
  `REPORT_ONLY_PROCEED` (the value does not exist in the protected wire).

Adapters explicitly NOT in this vertical (each `NOT_BUILT`, stated in coverage): Executive OS
runtime (Job/Attempt/Worker/Event), Wake/dialogue, RuntimeBinding, Capacity, SCF/GitHub (whose
packets OLS must never counterfeit per the SCF reconciliation), Runtime Observability. Each later
adapter is its own bounded acceptance.

## 5. First target operation (frozen) and honest construction semantics

The first real compiled operation is the **`WS:OPERATION-ASSURANCE` workstream itself**: its wave
DAG as recorded in `agentos/workstreams/WS-OPERATION-ASSURANCE.md` at the pinned revision.

Mapping (deterministic, closed, compiler-authored and disclosed as such):
- each wave → a model state-bearing unit; wave `status` values map to a closed marking vocabulary;
- `depends_on` edges → gating transitions (a wave may start only when its dependencies are done);
- `next_action` on a non-terminal wave → a declared obligation owned by the workstream owner seat;
- a schema-valid `wait` object → a typed external gate / intentional wait;
- workstream `status` → the operation's declared terminal/ongoing classification.

**A static workstream snapshot does not author lifecycle, fairness, retry/effect, or runtime
semantics.** Every transition the compiler constructs from this mapping is compiler-template
behavior grounded in exact record fields (its `source_refs` name the record path, revision, and
digest); it is disclosed in the model's assumptions as compiled construction, never presented as
owner-attested runtime fact or current operational proof.

**Supported property subset (frozen, exact):** `OPTION_TO_COMPLETE`, `PROPER_COMPLETION`,
`NO_DEAD_REQUIRED_TRANSITION`, `TERMINAL_ABSORPTION`, `GATE_WAIT_RETURN_VALIDITY`,
`UNIVERSAL_PROGRESS`.
**Unsupported in this vertical (each an explicit load-bearing model gap in every compiled
model):** starvation-under-declared-fairness and fairness realizability (a snapshot authors no
scheduler/fairness assumptions), recurring-progress validity (unless a wave declares a recurring
wait), retry/effect-unknown semantics, and runtime lifecycle conformance.

**Proof ceiling (loud, binding, and MECHANIZED):** the compiler MUST emit
`abstraction_contract.kind = "SOUND_OVERAPPROXIMATION"` in every compiled model and MUST NOT emit
`"DECLARED_EXACT"`; the protected A1 fence (`_fidelity_proof_eligible` in the checker, duplicated
in the report validator) then mechanically forecloses proof — an enforced input contract, not a
promise about builder behavior. Every report from this vertical is therefore capped at
`UNSAFE_COUNTEREXAMPLE` / `BOUNDED_NO_COUNTEREXAMPLE` / `INCONCLUSIVE_MODEL_GAP`. This vertical
DETECTS organizational black holes (a `NO_PROGRESS` wave with no dependency, wait, or next action
yields a real witness); it never mints `PROVEN_WITHIN_FINITE_MODEL` for a live workstream.

## 6. Hostile fixture (frozen): the CURRENT stale revision

The hostile stale/coverage-incomplete fixture is pinned to the exact Agent OS (Macro repository)
revision `a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4`, whose `WS:OPERATION-ASSURANCE` record's
durable `next_action` still names predecessor-era state (the fable-002 wave) while the fable-003
operation is active. The implementation MUST use that exact full-SHA revision as the negative
fixture — expected outcome (mechanical under the Section 4 freshness rule): every fact carries
`Freshness.UNKNOWN`, the Steward result carries its degraded/non-current issues, and the compiled
model's applicability is explicitly non-current — never a healthy compile presented as current. The positive end-to-end proof MUST use a later corrected, schema-valid pinned revision
(landed through the Agent OS owner's own lawful process — not mutated by this repair). Schema
validity is never laundered into semantic currentness.

Collision review (reconciliation §5 gate 6, discharged): the fable-002/003 census and branch-diff
review found no newer owner supplying a compiled operation-assurance model contract; the CCL-A2
Chairman-cognition composer is a different schema family and consumer
(`chairman_cognition_input`, not `operation_assurance_model`) and is cited here only as
receipt-shape precedent.

## 7. Trust ceiling (unchanged, restated as binding on A2)

A compiled model is `PROVENANCE_CLOSED_UNATTESTED / AUTHOR_DECLARED_ONLY` at most. Gathering with
correct receipts does NOT mint `CURRENT_SOURCE_ATTESTED`, `SOURCE_CONTRACT_VALIDATED`, or
`RUNTIME_REPLAY_CONFIRMED`; those require separately accepted attestation capabilities that remain
`NOT_BUILT`. The compiler cannot self-upgrade; the A1 checker's caps apply unchanged.

## 8. No-rebuild boundary (implements Steward-reconciliation §8)

The seam must not: create a parallel federated reader, source graph, cache, store, scheduler, or
second Steward; copy or reimplement Steward dataclasses or identity logic; side-read owners from
the A1 checker; parse Slack/PR prose; elect sources by recency; persist gathered facts anywhere;
or import `chairman_cognition_sources` (its receipt SHAPE is the accepted pattern; its schema
family and consumer are a different program).

## 9. Required failure states (subset of the program's §13 vocabulary)

`INVALID_SOURCE_BUNDLE`, `SOURCE_MISSING`, `SOURCE_PARTIAL`, `SOURCE_TRUNCATED`, `SOURCE_STALE`,
`SOURCE_CONFLICTED`, `SOURCE_SUPERSEDED`, `SOURCE_ATTESTATION_UNAVAILABLE`, `INPUT_TOO_LARGE`,
`DUPLICATE_KEY`, `UNRESOLVED_REFERENCE`, `UNSUPPORTED_SEMANTICS` — each fails closed with the
canonical owner named and never degrades to an apparently healthy compilation.

## 10. Implementation wave boundary

One branch, one PR, TDD-first, changed paths exactly: the two `control_plane/` modules, one
`scripts/` CLI, fixtures/tests under `tests/`, and nothing else. Release ceiling after protection:
`BUILT_NOT_PROVEN / OFFLINE_SOURCE_COMPILER / REPORT_ONLY / PRODUCTION_INERT`. The implementation
must prove one real end-to-end run — hostile fixture (Section 6 stale revision → explicit
inapplicability) AND positive case (later corrected revision → gather → Steward composition →
compile → protected A1 CLI → immutable report) — with byte receipts in the PR body.
