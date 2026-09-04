# CCL-A2 - Owner-Preserving Chairman Cognition Source Composer

**Operation:** `mastermind-chairman-cognition-source-composer-20260830-sol-001`  
**R4 repair:** `mastermind-chairman-cognition-source-composer-r4-content-identity-20260901-sol-001`  
**R5 repair:** `chairman-cognition-agentos-advisory-warning-currentness-repair-20260903-sol-001`  
**Parent:** `mastermind-chairman-cognition-loop-20260830-sol-001`  
**Current base:** protected CCL-A1 R3 decision contract  
**Cognition route:** `CHAT_PRO_DEFAULT`  
**Capability until protected:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## Observable mission

Given an already-produced `mastermind.ceo_boot_packet.v1`, one explicit Chairman-directive
receipt, content-bound canonical attestations for Mastermind and Agent OS, optional receipts from
existing owners, one delegation envelope and candidate strategic options, deterministically produce
and evaluate one complete `mastermind.chairman_cognition_input.v1`.

A2 does not crawl systems, invent CURRENT facts, create a second Steward, strategy store, lifecycle,
queue, retrieval plane, authority plane or execution path.

## User and machine capability

Before A2, protected A1 can adjudicate a closed decision document but no owner-preserving adapter
composes it from the existing CEO boot packet and explicit current-source receipts.

After A2 protection, a trusted caller can assemble one A1-compatible source bundle while preserving:

- the exact owner of each fact;
- repository revision, content identity, observation time, state and load-bearing status;
- all six current Strategic State constraints;
- exact Strategic State, option-classification and Chairman-envelope content bindings;
- mandatory Strategic State and Agent OS dependence for every modifying option;
- stale, conflict, unknown, degraded and correction behavior;
- `execution_authority_granted=false` throughout.

This is still pure source composition. It does not make Chairman cognition, executive learning,
worker dispatch or production autonomy live.

## Existing-owner composition

```text
existing CEO boot packet
  Strategic State projection + local Mastermind revision
  Agent OS brief + local Macro revision
+ protected Mastermind revision + exact strategic-state blob + projection digest
+ canonical Agent OS revision + owner-produced source-record digest + brief digest
+ explicit Chairman directive
+ explicit GitHub / Executive / Capacity / Runtime / Wake / Steward receipts
+ content-bound delegation envelope and classified options
-> owner-attributed A1 input
-> A1 deterministic frontier and preflight
```

A1 remains the only grammar, constraint, authority, carrier, effect and Pareto adjudicator. A2 does
not duplicate those laws.

## Exact four-path scope

1. `control_plane/chairman_cognition_sources.py`
2. `scripts/chairman_cognition_compose.py`
3. `tests/test_chairman_cognition_sources.py`
4. `docs/superpowers/plans/2026-08-30-chairman-cognition-source-composer-a2.md`

No A1 source file, Executive lifecycle, Agent OS owner, CEO boot-packet owner, Steward, GitHub,
Linear, Slack, RuntimeBinding, Wake, Capacity, provider, credential or production path is modified.

### R5 advisory-warning correction scope

The R5 repair changes only:

1. `control_plane/chairman_cognition_sources.py`;
2. `tests/test_chairman_cognition_agentos_warning_currentness.py`;
3. this accepted A2 plan.

It does not reopen A1, the owner wire, the CEO boot-packet producer, the original A2 CLI, or any
runtime/effect surface. It introduces no warning allowlist or message classifier: every valid warning
string remains advisory evidence, while malformed warning structure still fails closed.

## Complete A1 compatibility contract

### Strategic State root

The composed input names:

```text
strategic_constraints_source_ref = STRATEGIC_STATE:config/strategic_state.yml
```

The normalized map must contain all six current constraints imported from A1:

```text
autonomous_production_deploy
autonomous_live_capital_execution
duplicate_control_planes
marketing_org_expansion_before_distribution_proof
new_feature_expansion
unbounded_autonomous_strategic_modification
```

The derived Strategic State receipt binds:

```text
constraints-sha256:<canonical normalized constraint digest>
payload-sha256:<canonical supplied Strategic State projection digest>
blob:<exact config/strategic_state.yml Git blob SHA>
git:<protected Mastermind commit SHA>
```

`STRATEGIC_STATE:config/strategic_state.yml` is CURRENT only when all of the following agree:

1. the boot packet reports branch `master` and a full local Mastermind SHA;
2. the local SHA equals the protected-Mastermind attestation revision;
3. the attestation itself is CURRENT;
4. `source_blob_sha` is a resolved full Git blob SHA;
5. `payload_digest` equals the digest recomputed from the supplied Strategic State projection.

A mutated local payload with unchanged repository SHAs is `CONFLICT`. Missing or `UNRESOLVED`
content identity is `UNKNOWN`. A noncanonical checkout is `UNKNOWN`. A local/canonical revision
mismatch is `CONFLICT`. Because Strategic State is A1's root source, anything other than CURRENT
fails the complete decision closed.

### Agent OS root for modifying options

The dedicated Agent OS attestation carries:

```text
revision: <canonical Macro commit SHA>
source_records_digest: <agentos.source_records_digest.v1 value>
payload_digest: <sha256 of exact supplied ceo_brief.v1 payload>
```

The source-record digest is produced by Agent OS; A2 does not recompute the record walk, parse the
Agent OS store or own a second digest. A separately accepted trusted source adapter must acquire the
brief, canonical revision and owner-produced identity together.

`AGENT_OS:ceo_brief` is CURRENT only when:

1. the complete `ceo_brief.v1` wire shape and timestamps are valid;
2. `inputs.degraded` is a valid empty string list;
3. `readiness.degraded` is a valid empty string list and every included readiness record is valid;
4. `warnings` is a valid string list; its entries may be nonempty advisory evidence and remain in the exact payload digest without independently blocking CURRENT;
5. local Macro SHA equals the canonical Agent OS revision;
6. the attestation is CURRENT;
7. `source_records_digest` is resolved and syntactically valid;
8. `payload_digest` equals the digest recomputed from the exact supplied brief.

A mutated brief, including any warning-set change, with unchanged repository SHA and source-record
digest is `CONFLICT`. Missing or `UNRESOLVED` owner identity is `UNKNOWN`. Malformed wire shape,
malformed warnings, nonempty `inputs.degraded`, or nonempty `readiness.degraded` is `UNKNOWN` and
cannot be promoted by an otherwise-current revision receipt. Valid advisory warnings do not by
themselves change CURRENT and remain fully content-bound evidence.

### Mandatory option owner binding

Every option whose action is in A1's canonical `MODIFYING_ACTIONS` set must cite both:

```text
STRATEGIC_STATE:config/strategic_state.yml
AGENT_OS:ceo_brief
```

A2 validates citation presence; it never silently injects refs. Omission fails closed before the
option can rely on an unrelated current receipt. Read-only options are not forced to cite Agent OS
unless their own evidence contract requires it.

### Option classification

Every option supplies A1's closed classification fields. The cited eligible source must carry:

```text
classification-sha256:<sha256(canonical exact option subject)>
```

The subject includes option ID, action, scope refs, repositories, paths, duplicate-control-plane
flag, change classes and affected departments. A token cannot be transplanted to another option.
A2 passes classification evidence through; A1 owns eligibility and binding validation.

### Chairman delegation envelope

Every non-null envelope must already be content-bound through at least one cited current
load-bearing Chairman-directive receipt:

```text
envelope-sha256:<sha256(canonical complete delegation envelope)>
```

The payload includes every authority, action, reversibility, repository/path/scope/carrier, budget,
child, exact-carrier and expiry field. A2 preserves the evidence; A1 validates it. A2 does not
authenticate Chairman identity merely because JSON uses that label.

### Exact source actions

Existing-carrier `SOURCE_BRANCH_WRITE` and `SOURCE_MERGE` options must name an exact
`expected_head_sha`. A2 does not guess it or weaken A1's mechanical refusal precedence.

## Attestation grammar

The two dedicated attestations are closed documents.

Mastermind:

```yaml
revision: <40 lowercase hex>
state: CURRENT | STALE | CONFLICT | UNKNOWN
load_bearing: true
observed_at: <UTC ISO-8601>
source_blob_sha: <40 lowercase hex> | UNRESOLVED
payload_digest: sha256:<64 lowercase hex> | UNRESOLVED
```

Agent OS:

```yaml
revision: <40 lowercase hex>
state: CURRENT | STALE | CONFLICT | UNKNOWN
load_bearing: true
observed_at: <UTC ISO-8601>
source_records_digest: sha256:<64 lowercase hex> | UNRESOLVED
payload_digest: sha256:<64 lowercase hex> | UNRESOLVED
```

Unknown fields, malformed identities, non-load-bearing attestations or abbreviated revisions are
refused. The extra identity fields remain composer-local metadata; A1 receives only its unchanged
closed `SourceReceipt` grammar plus the identity-bearing derived receipts.

This pure composer does not authenticate GitHub, Agent OS, Chairman identity or acquisition path.
CURRENT is operationally meaningful only when a separately accepted **trusted source adapter**
acquires the owner payload and attestation together. A **model-authored or arbitrary local JSON**
bundle remains fixture/evidence input and grants no technical identity, organizational authority or
reusable effect token.

## Time, null and correction behavior

- derived receipts use the latest load-bearing owner/attestation observation time;
- evidence later than the bundle `as_of` is rejected by A1;
- content mismatch is `CONFLICT`, never silently refreshed;
- missing content identity is `UNKNOWN`, never inferred from matching branch names;
- valid advisory warnings are preserved in the exact brief payload and digest without independently degrading currentness;
- changing, removing, or adding a warning without a matching payload attestation is `CONFLICT`;
- a correction produces a new payload/identity pair and therefore a new composed-input digest;
- no historical memory, receipt or successful procedure authorizes replay of an effect.

## Failure behavior

- missing/wrong boot-packet schema -> opaque invalid source bundle;
- missing Strategic State or any current constraint -> fail closed;
- missing, malformed, abbreviated or non-load-bearing attestation -> fail closed;
- mutated Strategic State with unchanged revision identity -> CONFLICT and root refusal;
- mutated Agent OS brief with unchanged revision/record identity -> CONFLICT and option refusal;
- unresolved content identity -> UNKNOWN;
- malformed Agent OS brief or malformed warning wire -> UNKNOWN;
- nonempty `inputs.degraded` or `readiness.degraded` -> UNKNOWN;
- valid nonempty advisory Agent OS warnings alone -> preserve CURRENT eligibility;
- modifying option omitting Strategic State or Agent OS -> refused;
- reserved owner injection or duplicate source reference -> refused;
- missing/mismatched constraints, classification or envelope binding -> A1 rejection;
- source branch or merge without expected head -> A1 refusal;
- duplicate JSON key at any nesting level -> opaque CLI refusal;
- future-dated evidence -> A1 rejection;
- CLI invalid input -> fixed `INVALID_SOURCE_BUNDLE`, exit 2, no input leakage.

## Proof ruler

The focused suite must prove:

- deterministic composition without input mutation;
- all six Strategic State constraints and exact root reference;
- exact strategic payload/blob/revision identity;
- mutated local strategic payload cannot be CURRENT;
- exact Agent OS brief/source-record/revision identity;
- valid nonempty advisory Agent OS warnings preserve CURRENT;
- unavailable inputs remain UNKNOWN;
- degraded readiness remains UNKNOWN;
- malformed warning wire remains UNKNOWN;
- warning mutation after attestation is CONFLICT;
- mutated local brief cannot be CURRENT;
- missing/unresolved identities remain UNKNOWN;
- malformed identity fields and unknown attestation fields are refused;
- every modifying option must cite both canonical owner roots;
- read-only behavior is not over-constrained;
- exact option classification and mutation refusal;
- exact Chairman-envelope binding and mutation refusal;
- expected-head source-action compatibility;
- stale/unknown/conflict/degraded/future-dated behavior;
- recursive duplicate-key rejection and opaque errors;
- no I/O, runtime, connector or owner import;
- `execution_authority_granted=false` in both composition and A1 packet.

Repository tests and security analysis are implementation evidence. Final source acceptance remains an
accountable exact-head Sol review and expected-head merge. Green CI, merge and source protection do
not constitute a live Chairman workflow.

## No-rebuild boundaries

A2 has **no second Agent OS parser**, source crawler, digest store, RAG/CXI plane, memory database,
strategy store, authority registry, lifecycle, queue, worker router or effect owner. It consumes the
existing CEO boot packet, owner-produced identity and protected A1 contract.

## Completion and next action

The R5 correction is complete when one exact current-base PR contains only the three repair paths,
focused and neighboring suites are green, the correction receives independent exact-head review,
and the expected-head merge is read back from protected `master`. It does not reopen the original A2
acceptance or claim a live Chairman workflow.

After protection, CCL-A3 may compose one real current-source bundle with materially different
options, including `PORTFOLIO_HOLD`, but no effect may begin until the prospective Outcome Learning
prediction/assumption receipt is sealed. Any effect must use an existing effect owner and owner-local
revalidation. A2 itself never executes.
