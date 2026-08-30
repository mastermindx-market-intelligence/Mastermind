# CCL-A2 — Owner-Preserving Chairman Cognition Source Composer

**Operation:** `mastermind-chairman-cognition-source-composer-20260830-sol-001`  
**Parent:** `mastermind-chairman-cognition-loop-20260830-sol-001`  
**Stack base:** CCL-A1 exact head `1927f82f8a30893b379a2a2e2b5b10abd625fccb`  
**Protected source law:** `Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31`  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Capability state until accepted:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## Observable mission

Given a real `mastermind.ceo_boot_packet.v1`, one explicit current Chairman-directive receipt,
optional source receipts from existing owners, a delegation envelope and candidate strategic
options, deterministically produce and evaluate one
`mastermind.chairman_cognition_input.v1` without crawling systems, inventing CURRENT facts, or
creating a second Steward, strategy store, lifecycle, queue or authority plane.

## Why this is the next vertical

CCL-A1 can adjudicate a closed decision document but does not assemble one from Mastermind's current
read projections. A2 closes that gap while preserving existing source owners:

```text
existing CEO boot packet
  strategic-state summary + exact Mastermind revision
  Agent OS brief + exact Macro revision
+ explicit current Chairman directive
+ explicit GitHub / Executive / Capacity / Runtime / Wake / Steward receipts
+ delegation envelope and options
-> owner-attributed A1 input
-> A1 strategic frontier and preflight
```

A2 does not wait for corrected Executive Steward to become production-live. It can consume a Steward
receipt later, but it is useful immediately with the existing CEO boot packet and explicit evidence
receipts. Missing runtime owners remain absent or UNKNOWN and cannot authorize a modifying option.

## Exact four-path scope

1. `control_plane/chairman_cognition_sources.py`
2. `scripts/chairman_cognition_compose.py`
3. `tests/test_chairman_cognition_sources.py`
4. `docs/superpowers/plans/2026-08-30-chairman-cognition-source-composer-a2.md`

A2 changes no CCL-A1 file, Executive lifecycle, Agent OS, CEO boot-packet owner, Steward, GitHub,
Linear, Slack, RuntimeBinding, Wake, Capacity, provider, credential or production path.

## Source semantics

### Chairman directive

The wrapper forces owner `CHAIRMAN_DIRECTIVE`; caller prose cannot select another owner. The receipt
must be explicitly load-bearing. A1 still verifies current state, observation time and delegation
envelope linkage.

### Strategic state

A2 uses the strategic-state summary already embedded by the canonical CEO boot packet. Missing or
wrong-schema strategic state fails composition because the company cannot reason against an invented
objective set. The normalized strategic summary is content-addressed. CURRENT additionally requires
a full Mastermind SHA from the canonical `master` checkout; feature/unaccepted or unresolved
checkouts remain `UNKNOWN` rather than laundering local strategy into company truth.

### Agent OS

A2 does not parse workstream prose or rank work. It converts the embedded `ceo_brief.v1` into one
Agent OS receipt. The receipt becomes CURRENT only when the brief schema is exact, the Macro revision
is a full SHA, and the brief's structured `inputs.degraded` and `warnings` lists are empty. The exact
brief payload is content-addressed in the receipt revision. Missing, mismatched or degraded input
becomes UNKNOWN.

### Other owners

GitHub, Executive OS, Capacity, RuntimeBinding, Wake, Steward, observability and operation-assurance
facts enter only as explicit A1 receipts. Additional receipts may not impersonate Chairman,
Strategic State or Agent OS, whose dedicated paths prevent duplicate canonical sources.

## Failure behavior

- missing/wrong CEO boot-packet schema -> invalid source bundle;
- missing/wrong strategic state or load-bearing constraints -> fail closed;
- unresolved or noncanonical Mastermind revision -> UNKNOWN strategic receipt;
- unresolved Macro revision -> UNKNOWN Agent OS receipt;
- missing/degraded/wrong-schema Agent OS brief -> UNKNOWN receipt;
- reserved owner injected through additional receipts -> refused;
- duplicate source reference -> refused;
- future-dated, malformed or unknown A1 receipt -> A1 refusal/error;
- CLI invalid input -> fixed opaque `INVALID_SOURCE_BUNDLE`, exit 2, no input leakage.

## Proof

- deterministic repeated composition and digests;
- owner documents are not mutated;
- current strategic and Agent OS sources compose as CURRENT only from structured evidence;
- unresolved/degraded sources remain UNKNOWN and block dependent options;
- reserved-owner and duplicate-reference hostile cases fail closed;
- direct CLI valid and invalid journeys;
- full CCL-A1 behavior remains green on the stacked head;
- hosted repository and security checks on the exact head.

## Non-goals

A2 does not call Agent OS, GitHub, Slack, Linear, Executive OS, Capacity, RuntimeBinding, Wake,
Steward or a model. It does not create a Job, select a worker, write durable memory, merge, deploy,
trade, or grant execution authority. The existing CEO boot packet and future accepted Steward/owner
adapters remain the gather paths.

## Stop condition

One exact stacked PR head with four changed paths, focused and full repository proof, and independent
review. After A2 is accepted, CCL-A3 must run one real source bundle containing materially different
strategic options—including `PORTFOLIO_HOLD`—and complete one supervised reversible canary through an
existing effect owner.
