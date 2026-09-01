# CCL-A2 — Owner-Preserving Chairman Cognition Source Composer

**Operation:** `mastermind-chairman-cognition-source-composer-20260830-sol-001`  
**Parent:** `mastermind-chairman-cognition-loop-20260830-sol-001`  
**Current base:** complete CCL-A1 R3 decision contract  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Capability until protected:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## Observable mission

Given an already-produced `mastermind.ceo_boot_packet.v1`, one explicit Chairman-directive
receipt, canonical revision attestations for Mastermind and Agent OS, optional receipts from existing
owners, one delegation envelope and candidate strategic options, deterministically produce and
evaluate one complete `mastermind.chairman_cognition_input.v1`.

A2 does not crawl systems, invent CURRENT facts, create a second Steward, strategy store, lifecycle,
queue, authority plane or execution path.

## User and machine capability

Before A2, the protected A1 core can adjudicate a closed decision document but no owner-preserving
adapter composes that document from the existing CEO boot packet and explicit current-source
receipts.

After A2 protection, a trusted caller can assemble one A1-compatible source bundle while preserving:

- the exact owner of each fact;
- revision, observation time, state and load-bearing status;
- all six current Strategic State constraints;
- exact Strategic State, option-classification and Chairman-envelope content bindings;
- stale, conflict, unknown and degraded behavior;
- `execution_authority_granted=false` throughout.

This is still a pure source-composition capability. It does not make Chairman cognition live.

## Existing-owner composition

```text
existing CEO boot packet
  strategic-state summary + local Mastermind revision
  Agent OS brief + local Macro revision
+ protected-Mastermind revision attestation
+ canonical-Agent-OS revision attestation
+ explicit Chairman directive
+ explicit GitHub / Executive / Capacity / Runtime / Wake / Steward receipts
+ content-bound delegation envelope and classified options
-> owner-attributed A1 input
-> A1 deterministic frontier and preflight
```

A1 remains the controlling grammar and policy core. A2 does not duplicate its constraint selectors,
authority decisions, Pareto logic, effect law or carrier law.

## Exact four-path scope

1. `control_plane/chairman_cognition_sources.py`
2. `scripts/chairman_cognition_compose.py`
3. `tests/test_chairman_cognition_sources.py`
4. `docs/superpowers/plans/2026-08-30-chairman-cognition-source-composer-a2.md`

No A1 source file, Executive lifecycle, Agent OS owner, CEO boot-packet owner, Steward, GitHub,
Linear, Slack, RuntimeBinding, Wake, Capacity, provider, credential or production path is modified.

## Complete R2/R3 compatibility contract

### Strategic State

The composed input names:

```text
strategic_constraints_source_ref = STRATEGIC_STATE:config/strategic_state.yml
```

The composer derives exactly one load-bearing Strategic State receipt from the boot packet and the
protected-Mastermind revision attestation. The normalized constraint map must contain **all six current constraints**:

```text
autonomous_production_deploy
autonomous_live_capital_execution
duplicate_control_planes
marketing_org_expansion_before_distribution_proof
new_feature_expansion
unbounded_autonomous_strategic_modification
```

A2 imports the required set from A1 rather than maintaining a second policy list. It binds the exact
normalized map through:

```text
constraints-sha256:<sha256(canonical normalized constraint map)>
```

The full strategic-state projection remains separately content-addressed for provenance.

`STRATEGIC_STATE:config/strategic_state.yml` is CURRENT only when the boot packet reports canonical
`master`, its full SHA matches the protected-Mastermind attestation and that attestation is CURRENT.
An unresolved or noncanonical checkout is UNKNOWN at source derivation and causes A1 to reject the
entire decision because the root Strategic State source is not CURRENT. A mismatched local `master`
is CONFLICT and is rejected for the same reason. A2 never launders either state into an option-local
refusal packet.

### Option classification

Every option must supply A1's closed fields:

```text
classification_source_ref
change_classes
 affected_departments
```

The cited canonical receipt must carry:

```text
classification-sha256:<sha256(canonical exact option subject)>
```

The exact subject includes option ID, action, affected-scope references, repositories, paths,
duplicate-control-plane flag, change classes and affected departments. Title, prose and benefit/cost
estimates do not grant classification authority. A token cannot be transplanted to another option.

A2 passes owner-produced classification evidence through; it does not infer class from title or
silently manufacture a canonical owner. A1 validates the binding and owner eligibility.

### Chairman delegation envelope

Every non-null envelope must already be bound through at least one cited current load-bearing
Chairman-directive receipt:

```text
envelope-sha256:<sha256(canonical complete delegation envelope)>
```

The canonical payload covers schema and envelope ID, the complete authority-source set, mode,
actions, reversibility, repository/path/scope/carrier limits, budget, active-child ceiling,
exact-carrier rule and expiry. A caller-mutated envelope cannot retain an unrelated current Chairman
receipt and become accepted.

A2 preserves the supplied receipt and envelope; A1 validates the exact binding. The pure composer
**does not authenticate** Chairman identity by itself.

### Exact source actions

Existing-carrier `SOURCE_BRANCH_WRITE` and `SOURCE_MERGE` options must name an exact
`expected_head_sha`. A2 does not guess it or weaken A1's refusal behavior.

## Canonical revision attestations

A local checkout name or SHA is provenance, not proof that it matches current canonical source. The
bundle therefore requires two dedicated, closed, load-bearing full-SHA attestations:

```text
GITHUB:Mastermind:protected-master
AGENT_OS:canonical-revision
```

The caller cannot rewrite those owner identities. Matching revision propagates the attestation's
CURRENT, STALE, CONFLICT or UNKNOWN state. Local/canonical mismatch becomes CONFLICT.

This pure composer **does not authenticate** GitHub, Agent OS, Chairman identity or acquisition path
merely because JSON uses an owner label. CURRENT is operationally meaningful only when a separately
accepted **trusted source adapter** supplies owner payload and attestation together. A
**model-authored or arbitrary local JSON** bundle remains fixture/evidence input. It grants no
technical identity, organizational authority or reusable effect token.

## Agent OS brief

A2 performs wire-shape and degradation validation only. It does not re-rank work or become another
Agent OS implementation.

`AGENT_OS:ceo_brief` is CURRENT only when the complete `ceo_brief.v1` owner shape is structurally
valid, timestamps are valid, degradation/warning lists are empty, the local Macro SHA matches the
canonical Agent OS attestation and that attestation is CURRENT. Missing, malformed or degraded input
is UNKNOWN. A valid brief on a mismatched Macro revision is CONFLICT.

Derived Strategic State and Agent OS observations use the latest load-bearing input time, preventing
a newer attestation from being backdated into an older company snapshot.

## Failure behavior

- missing/wrong boot-packet schema -> opaque invalid source bundle;
- missing Strategic State or any current constraint -> fail closed;
- missing/non-full-SHA/non-load-bearing canonical attestation -> fail closed;
- unresolved/noncanonical Strategic State revision -> derive UNKNOWN, then A1 rejects the whole decision;
- local/canonical Strategic State disagreement -> derive CONFLICT, then A1 rejects the whole decision;
- malformed/degraded Agent OS brief -> UNKNOWN and dependent options are refused;
- reserved owner injection or duplicate source reference -> refused;
- missing or mismatched `constraints-sha256`, `classification-sha256` or `envelope-sha256` -> A1 rejection;
- source branch or merge without expected head -> A1 refusal;
- duplicate JSON key at any nesting level -> opaque CLI refusal;
- future-dated evidence -> A1 rejection;
- CLI invalid input -> fixed `INVALID_SOURCE_BUNDLE`, exit 2, no input leakage.

## Proof ruler

The focused source-composer suite must prove:

- deterministic composition without mutating input documents;
- exact root Strategic State reference and complete six-constraint map;
- exact Strategic State constraint binding;
- exact option-subject classification and mutation refusal;
- exact Chairman-envelope binding and mutation refusal;
- expected-head source-action compatibility;
- non-current Strategic State inputs fail the complete A1 decision closed;
- Agent OS and additional non-root stale/unknown/conflict states remain option-local;
- malformed brief cannot become CURRENT;
- latest-observation semantics;
- strict recursive duplicate-key rejection;
- static no-I/O/no-runtime/no-connector import fence;
- valid and opaque-invalid CLI journeys;
- `execution_authority_granted=false` in both composition and A1 packet.

Repository test and security analysis are implementation evidence. Final source acceptance is one
accountable Sol exact-head review under the Chairman's current streamlined release ruling; a
redundant external-auditor ceremony is not a blocking gate for this production-inert vertical.

## Non-goals

A2 does not call Agent OS, GitHub, Slack, Linear, Executive OS, Capacity, RuntimeBinding, Wake,
Steward or a model. It does not create a Job, select a worker, write durable memory, deploy, trade or
grant execution authority. It does not make A3, A4, A5 or A6 live.

## Completion and next action

A2 is complete when one exact current-base PR contains only the four paths above, the focused and
repository suites are green, the source contract is directly reviewed, and the expected-head merge
is read back from protected `master`.

After protection, CCL-A3 composes one real current-source bundle with materially different options,
including `PORTFOLIO_HOLD`, and executes one supervised reversible canary only through an existing
effect owner after owner-local revalidation.
