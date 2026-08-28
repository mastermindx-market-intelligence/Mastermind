# Session Truth R1 — Owner Record Identity & Required-Source Amendment

**Date:** 2026-08-28  
**Owner:** Sol, AI CEO  
**Existing carrier:** Mastermind PR #170 / `sol/session-truth-r1-20260827`  
**Repair operation key:** `session-truth-r1-owner-record-identity-repair-20260828-sol-001`  
**Authority:** narrow amendment to the accepted Cross-Plane Reconciliation design and R1 plan. It governs only the exact R1 defects below. It does not authorize R2-R7, mutation, a second truth store, a new Agent OS parser, or a new runtime.

## 1. Problem statement

The current R1 consumer attempts to derive stable Agent OS semantic identity by deleting a named list of acquisition-clock fields from `agent_os_state.v1` and `context_bundle.v1`. That is structurally unsafe:

- additional `--now`-derived values and host/worktree census values remain inside the hashed subtrees;
- every new Macro field enters the downstream hash by default;
- unchanged direct Agent OS records can therefore produce different Session Truth semantic hashes;
- a downstream denylist makes Mastermind re-own Agent OS field semantics and loses the race whenever the owner evolves.

R1 also has four exact deterministic defects:

- a PR can positively declare a Linear binding while Linear is unavailable and admission can become modification-safe;
- canonical JSON/parsing accepts non-finite numbers or untyped invalid map keys;
- Slack ACK-without-Executive-state can fire without positive evidence that the scoped operation owes Executive state;
- one Agent OS bare PR number can be joined across multiple repositories.

## 2. Owner-produced direct-record content identity

Agent OS remains the parser/schema owner. Macro must produce a **content identity of the direct authored records**, not a semantic classification of its generated/derived state fields.

### 2.1 Contract

The preferred additive owner contract is:

```text
agent_os_state.v1.source_records_digest
context_bundle.v1.source_records_digest
```

Each value is:

```text
sha256:<64 lowercase hex>
```

If current consumers prove that either V1 document is a closed object whose additive field would be incompatible, the Macro carrier must stop and return a versioning decision request; it may not silently add the field or unilaterally bump every consumer. A separately accepted `v2` migration is then required. Compatibility must be proven, not assumed.

Optional audit metadata may include a bounded `source_record_count`; it is not part of Session Truth identity unless the owner contract explicitly freezes it.

### 2.2 Digest input

The digest is computed by Macro over the exact direct Agent OS source records that the canonical parser reads for that output:

```text
sort by repository-relative source path
for each source: path UTF-8 bytes + NUL + SHA-256(exact file bytes)
canonical compact JSON envelope with closed schema/version
SHA-256 over the canonical envelope
```

For `agent_os_state.v1`, the source set is the direct record set used to build the state. For `context_bundle.v1`, the source set is the complete deterministic candidate source set for the exact target/sections **before acquisition-clock, expiry, staleness or host-census filtering**. Direct record bytes include validated frontmatter and Markdown body; any authored byte change changes the digest. Generated state, generated Markdown, git dates, current clock, stale-day arithmetic, claim liveness, worktree census, active-build age, provider/runtime observations and auxiliary join results are excluded.

This is intentionally a conservative **content identity**, not a claim that whitespace-equivalent files are semantically identical. A formatting-only authored change may move the digest; unchanged authored records may never move because the observation clock or host changed.

### 2.3 Fail-closed producer tests

Macro must prove:

1. same direct records at different `--now` values and different worktree/census fixtures -> identical digest;
2. any byte change to any included direct record -> different digest;
3. adding/removing/renaming an included source path -> different digest;
4. changing only generated state / git-derived dates / stale warnings / live worktrees -> unchanged digest;
5. context expiry crossing with unchanged source records -> unchanged digest;
6. deterministic output on repeated runs;
7. no network and no source writes;
8. a source file read by the canonical parser but omitted from the digest source-set test -> RED.

The last test is the completeness fence. Do not maintain a field-by-field downstream allowlist or volatile denylist.

## 3. Session Truth consumer behavior

### 3.1 Positive projection

When valid owner digests are present, R1 semantic projection uses:

```text
Agent OS source_sha
state schema + source_records_digest
for each context: schema + exact target + requested sections + source_records_digest
```

The full raw owner observations remain in the immutable receipt for diagnosis; only the semantic-hash projection is reduced. Source repository SHA and requested scope remain covered elsewhere in the receipt.

### 3.2 Missing digest

The current named-list stripping path may remain as a legacy **display/fallback observation only**. It cannot authorize modification.

When Agent OS is required by the requested scope and a valid owner digest is absent, emit a typed blocking finding:

```text
AGENTOS_RECORD_IDENTITY_UNAVAILABLE
```

and make `modification_safe=false`. When Agent OS is optional, preserve the observation as partial/degraded. Do not call a clock-coupled fallback stable merely because two nearby runs happened to match.

### 3.3 Migration sequence

1. #170 may implement digest validation/preference, the missing-digest blocker and all other Mastermind-side repairs on its existing carrier.
2. The Macro digest producer is a separate Agent OS carrier and new operation key, sequenced **after Macro #6182** because both touch `scripts/agentos.py` / Agent OS proof layout.
3. #170's frozen real current-estate Task 7 proof runs only after the Macro owner digest is available on the canonical read root.
4. R1 remains `BUILT_NOT_PROVEN` until two real observations at distinct acquisition clocks produce identical semantic projection/hash from unchanged direct records.

## 4. Required Linear evidence

`linear` is a required source when either:

- `scope.linear` names one or more exact Linear identities; or
- the normalized in-scope GitHub observation is available and any scoped pull request positively declares a non-null Linear binding.

Therefore:

```text
scope.linear=[]
+ GitHub available
+ scoped PR.linear=MAS-###
+ Linear unavailable
→ required_sources_unavailable includes linear
→ DIALOGUE_ONLY / modification_safe=false
```

A genuinely optional Linear source with no scope identity and no positive GitHub binding remains optional/degraded. Unavailable Linear never becomes an empty issue index or negative testimony.

## 5. Strict canonical JSON and snapshot parsing

- `canonical_json` uses `allow_nan=False` and converts serializer failures into `SessionTruthContractError`.
- snapshot loaders and `_decode_leading_json` reject `NaN`, `Infinity` and `-Infinity` through `parse_constant`.
- Agent OS interior values are recursively bounded to JSON-compatible string-keyed mappings/lists/scalars before hashing/rendering; invalid keys or values fail through the typed R1 error path, not an uncaught traceback.
- No coercion to null/string/zero is allowed.

## 6. Slack ACK versus Executive state

`SLACK_ACK_WITHOUT_EXECUTIVE_STATE` may fire only when all are true:

```text
scope.requires_executive is True
executive.available is True
message.acked is True
message.ack_required is True
exact non-empty operation_key is absent from Executive observations
```

If Executive is required but unavailable, the existing required-source/admission path blocks safely. If `scope.requires_executive` is false, a lawful active-session/read-only transport ACK creates no Executive-state finding. R1 does not invent per-operation Executive ownership; mixed-operation typing belongs to a later separately versioned snapshot contract.

## 7. Repository-qualified PR identity

R1 must never bind an Agent OS bare PR number across multiple repositories.

- When the requested scope contains exactly one repository, the scoped repository may qualify a bare Agent OS PR number.
- With multiple repositories in scope, an unqualified Agent OS PR citation is `AMBIGUOUS/UNBOUND`; it may emit a typed finding but must not join by number, title, workstream similarity or first match.
- Add the two-repository/same-number falsifier.
- A future repo-qualified Agent OS PR citation is an owner-side improvement, not a reason for R1 to guess today.

## 8. Ordinary carrier movement

R1 may conservatively block when an exact expected/prior-observed carrier head was explicitly part of the requested scope. It must not claim that every branch movement since original commission is inherently unauthorized. Preserve the current safe behavior only if its field is documented as an exact expected head; otherwise classify simple active-carrier advancement separately or leave it unknown. No model inference.

## 9. Exact carrier split and collision law

### Mastermind #170 repairs itself

Authorized R1 files remain the existing #170 modules/tests/fixtures plus this amendment. The repair includes:

- strict JSON/parsing;
- Linear required-source derivation;
- Executive-required ACK gate;
- repository-qualified/ambiguous PR join behavior;
- owner-digest validation/preference and missing-digest blocker;
- RED-first falsifiers and current-estate proof harness updates.

### Separate Macro carrier after #6182

The Macro carrier owns:

- digest computation and output on existing canonical CLI surfaces;
- compatibility/versioning proof;
- producer completeness and invariance tests;
- one Agent OS decision/discovery/handoff recording the contract.

It does not modify Linear, Executive, Slack, Wake, Capacity/OCR, or create a new store/artifact daemon.

### Held collisions

- Do not touch Macro `scripts/agentos.py` for the digest until #6182 is reconciled/accepted.
- Do not couple R1 to unaccepted WP-1/Wake fields.
- The active Codex/H0 canary remains reserved; this amendment authorizes no H0/host/capacity/OCR mutation.

## 10. Stop condition

R1 is accepted only when:

- every Mastermind-side defect above passes exact-head RED->GREEN tests and hosted review;
- the owner-produced direct-record digest is available from the canonical Macro read root;
- two unchanged real current-estate observations at meaningfully different acquisition clocks have byte-identical semantic projection/hash;
- a real authored Agent OS record change moves the digest/hash;
- required unavailable sources never read safe;
- zero source write/network fallback/duplicate store exists;
- Sol independently accepts the exact final head and receipt.

Merge alone does not release R2-R7, Project Recovery, Linear mutation, Agent Relay, Wake, capacity routing or production modification.