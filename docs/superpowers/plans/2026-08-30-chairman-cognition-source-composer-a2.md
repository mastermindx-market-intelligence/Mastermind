# CCL-A2 — Owner-Preserving Chairman Cognition Source Composer

**Operation:** `mastermind-chairman-cognition-source-composer-20260830-sol-001`  
**Parent:** `mastermind-chairman-cognition-loop-20260830-sol-001`  
**Stack base:** CCL-A1 exact head `1927f82f8a30893b379a2a2e2b5b10abd625fccb`  
**Protected source law:** `Mastermind@620263090fb9f272f763e420ba103b0ff8dc5f31`  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Capability state until accepted:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## Observable mission

Given a real `mastermind.ceo_boot_packet.v1`, one explicit current Chairman-directive receipt,
explicit canonical revision attestations for the Mastermind and Agent OS sources, optional receipts
from existing owners, a delegation envelope and candidate strategic options, deterministically
produce and evaluate one `mastermind.chairman_cognition_input.v1` without crawling systems,
inventing CURRENT facts, or creating a second Steward, strategy store, lifecycle, queue or authority
plane.

## Why this is the next vertical

CCL-A1 can adjudicate a closed decision document but does not assemble one from Mastermind's current
read projections. A2 closes that gap while preserving existing source owners:

```text
existing CEO boot packet
  strategic-state summary + local Mastermind revision
  Agent OS brief + local Macro revision
+ current protected-Mastermind revision attestation
+ current canonical-Agent-OS revision attestation
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

### Canonical revision attestations

A local checkout name or SHA is provenance, not proof that it matches the current canonical source.
The bundle therefore requires two dedicated, closed and load-bearing full-SHA attestations:

```text
GITHUB:Mastermind:protected-master
AGENT_OS:canonical-revision
```

The caller cannot rewrite their owner or source identity. A1 validates that their observation times
do not postdate the decision snapshot. An attestation may be `CURRENT`, `STALE`, `CONFLICT` or
`UNKNOWN`; the derived source preserves that state when its SHA matches the boot packet.

A derived Strategic State or Agent OS receipt is not observed before its newest load-bearing input.
Its `observed_at` is therefore the later of the boot/brief observation and the canonical revision
attestation observation. This prevents a later attestation from being backdated into an earlier
company-state snapshot.

### Strategic state

A2 uses the strategic-state summary already embedded by the canonical CEO boot packet. Missing or
wrong-schema strategic state fails composition because the company cannot reason against an invented
objective set. The normalized strategic summary is content-addressed.

`STRATEGIC_STATE:config/strategic_state.yml` is CURRENT only when all are true:

- the boot packet reports a full Mastermind checkout SHA;
- the checkout branch is canonical `master`;
- the checkout SHA exactly matches the protected-Mastermind attestation;
- the attestation itself is CURRENT.

An unresolved or feature/unaccepted checkout is UNKNOWN. A full local `master` SHA that disagrees
with protected Mastermind is CONFLICT. Therefore a stale local checkout named `master` cannot be
laundered into current company strategy.

### Agent OS

A2 does not parse workstream prose or rank work. It converts the embedded `ceo_brief.v1` into one
Agent OS receipt. The exact brief payload is content-addressed.

`AGENT_OS:ceo_brief` is CURRENT only when all are true:

- the brief schema is exact;
- structured `inputs.degraded` and `warnings` lists are present and empty;
- the boot packet reports a full Macro checkout SHA;
- the checkout SHA matches the canonical Agent OS revision attestation;
- the attestation itself is CURRENT.

Missing, wrong-schema or degraded input becomes UNKNOWN. A valid brief whose local Macro revision
disagrees with the canonical attestation becomes CONFLICT rather than healthy/current.

### Other owners

GitHub, Executive OS, Capacity, RuntimeBinding, Wake, Steward, observability and operation-assurance
facts enter only as explicit A1 receipts. Additional receipts may not impersonate Chairman,
Strategic State or Agent OS, whose dedicated paths prevent duplicate canonical sources. The
additional-receipt cap preserves A1's total 128-receipt bound after the five dedicated receipts.

## Failure behavior

- missing/wrong CEO boot-packet schema -> invalid source bundle;
- missing/wrong strategic state or load-bearing constraints -> fail closed;
- missing, non-load-bearing or non-full-SHA canonical attestation -> fail closed;
- unresolved or noncanonical Mastermind revision -> UNKNOWN strategic receipt;
- local Mastermind/canonical SHA disagreement -> CONFLICT;
- unresolved Macro revision -> UNKNOWN Agent OS receipt;
- local Macro/canonical SHA disagreement -> CONFLICT;
- missing/degraded/wrong-schema Agent OS brief -> UNKNOWN receipt;
- invalid or non-UTC observation time -> fail closed;
- reserved owner injected through additional receipts -> refused;
- duplicate source reference -> refused;
- future-dated, malformed or unknown A1 receipt -> A1 refusal/error;
- CLI invalid input -> fixed opaque `INVALID_SOURCE_BUNDLE`, exit 2, no input leakage.

## Proof

- deterministic repeated composition and digests;
- owner documents are not mutated;
- current strategic and Agent OS sources compose as CURRENT only from structured evidence plus
  matching canonical revision attestations;
- stale local `master` and Macro checkouts produce CONFLICT rather than false CURRENT;
- unresolved/degraded sources remain UNKNOWN and block dependent options;
- stale/unknown/conflicting attestations propagate truthfully;
- attestations are closed, load-bearing and full-SHA only;
- derived observation time is the latest load-bearing input and future evidence is rejected;
- static import fence proves the pure composer imports no filesystem, subprocess, network,
  connector, Executive runtime, Capacity or Agent OS implementation owner;
- reserved-owner and duplicate-reference hostile cases fail closed;
- direct CLI valid and invalid journeys;
- full CCL-A1 behavior remains green on the stacked head;
- hosted repository and security checks on the exact head.

## Non-goals

A2 does not call Agent OS, GitHub, Slack, Linear, Executive OS, Capacity, RuntimeBinding, Wake,
Steward or a model. It does not create a Job, select a worker, write durable memory, merge, deploy,
trade, or grant execution authority. The existing CEO boot packet and future accepted Steward/owner
adapters remain the gather paths. Supplying a revision attestation is an explicit current-source
input, not a network lookup performed by this pure module.

## Stop condition

One exact stacked PR head with four changed paths, focused and full repository proof, and independent
review. After A2 is accepted, CCL-A3 must run one real source bundle containing materially different
strategic options—including `PORTFOLIO_HOLD`—and complete one supervised reversible canary through an
existing effect owner.
