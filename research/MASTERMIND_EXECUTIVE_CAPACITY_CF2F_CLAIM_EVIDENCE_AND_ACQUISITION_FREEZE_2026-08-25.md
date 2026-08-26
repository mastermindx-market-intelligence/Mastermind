# Executive Capacity Fabric CF2-F — acquisition, claim-evidence and replay source law

**Date:** 2026-08-25
**Owner:** Sol, AI CEO
**Chairman:** Chris
**Status:** **SOL SOURCE-LAW FREEZE / RECORDS-ONLY CARRIER. No runtime, worker, login, route or service is changed by this document.**
**Protected Mastermind basis:** `eff2033c639cb25f8b4a2a4e5f90e1a4a6002138`
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1, loaded atomically from that exact protected commit.
**Accepted CF1 candidate:** `fc12904f59a5758817aa2c76ffaa40bb1ebcbf8e`
**Accepted CF1 squash merge:** `dcdd939c45b23abce5ba04f95e330ac914a3904b`
**Organizational parent:** `WS:EXECUTIVE-CAPACITY-FABRIC`
**Integration parent:** `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md`

---

## 0. Observable outcome and ruling

The Chairman should be able to give one bounded outcome without choosing among three Codex
Personal Pro accounts or watching their quota state. Executive OS must choose one already-lawful
worker deterministically from fresh, secret-free Provider Control evidence, atomically record why
that worker was chosen, and return the same historical decision on replay without re-reading or
re-ranking current provider state.

CF2-F freezes that law. It makes one correction to the earlier preferred acquisition family:

> A single subprocess under the Executive control principal is not a lawful concrete producer for
> the three Personal Pro realms. Each realm is intentionally owned by a distinct UID and mode-0700
> provider home. The accepted repair is a distributed **read**, not shared credential access:
> each existing worker-broker principal observes only its own realm through Macro-owned code;
> Macro-owned code validates and aggregates those secret-free fragments into the one accepted
> `mastermind.provider_capacity.v1` projection; Executive consumes the final projection and owns
> only placement/lifecycle evidence.

This ruling does not accept or install that path. The records-only result is `SPEC_ONLY`. CF2-I
remains held until its acquisition subcarriers are implemented, independently reviewed and proven
on the installed three-principal host.

---

## 1. Current canonical capability ledger

| Capability | State | Exact meaning |
|---|---|---|
| Macro CF1 strict projection and no-write CLI | `BUILT_NOT_PROVEN` in the Autonomy V1 product | Accepted and squash-merged; producer contract is real, but no installed Executive consumer exists. |
| CF1 semantic content at merge | `BUILT_NOT_PROVEN` | Candidate and squash delta have stable patch ID `eece33a635bcb536a93146b19f74339f080115dc`; all twelve CF1-owned blobs are byte-identical. |
| Three Personal Pro realm definitions | `BUILT_NOT_PROVEN` | Protected Mastermind defines isolated principals/homes/readiness ceremonies; merge is not host installation, authentication or service proof. |
| Current installed all-three acquisition path | `DARK_OR_DISCONNECTED` | No lawful principal can currently observe all three private realms and emit one complete CF1 snapshot. |
| Distributed fragment producer/aggregator | `NOT_BUILT` | Required Macro-owned follow-on frozen below. |
| Per-realm broker capacity-read operation | `NOT_BUILT` | Required additive read operation on the existing worker-broker boundary. |
| Three worker-broker service composition | `NOT_BUILT` | Current protected readiness realms do not start or fan out three worker services. |
| Typed `JOB_CLAIMED.capacity_evidence` | `NOT_BUILT` | Existing event/transaction is sufficient; the exact extension is frozen below. |
| Capacity-aware claim ranking | `NOT_BUILT` | Must remain after all existing route/authority/capability/identity filters. |
| Cursor and Grok source/auth archaeology | may proceed in parallel | It does not touch this carrier. Executable adapters remain gated by RF1/HF1. |

No row above is upgraded by this records-only source law.

---

## 2. Estate reconciliation and concrete blocker

### 2.1 CF1 is a single-process producer today

Accepted Macro CF1 calls the Codex owner once. `capacity_account_observations()` enumerates
`CODEX_ACCOUNT_HOMES`, assigns the stable `codex_account`, `codex_account_2`, and
`codex_account_3` identities by configured position, and checks only `auth.json` file metadata.
The normalizer then joins those observations with existing Provider Control health, cooling,
budget and outcome owners before emitting one complete twelve-slot snapshot.

The implementation never opens auth bytes. That property remains frozen.

### 2.2 Mastermind intentionally prevents one principal seeing every realm

Protected Mastermind defines:

```text
codex-pro-01 -> _mastermind_codex_01 (UID/GID 454) -> mode-0700 provider home
codex-pro-02 -> _mastermind_codex_02 (UID/GID 455) -> mode-0700 provider home
codex-pro-03 -> _mastermind_codex_03 (UID/GID 456) -> mode-0700 provider home
```

The principals have distinct one-member groups. `_mastermind_exec` UID 450 is not a member. The
worker broker refuses unexpected supplementary groups. Therefore:

- `_mastermind_exec` cannot traverse the three homes;
- one worker principal cannot inspect another worker's home;
- running the existing full CF1 CLI independently under each principal incorrectly maps every
  single `CODEX_HOME` to `codex_account`, creating identity collisions;
- `provider-slot-status.py` is useful readiness proof but has no health/cooling/quota horizon
  evidence and is not the CF1 capacity source.

The current installed host is older still: the protected three-principal source is not itself
proof that those users, homes, brokers or an exact accepted release are installed and running.

### 2.3 Exact current-code receipts

At the pinned bases:

- Macro `engine/provider_capacity.py:646-763` performs one source-owner observation pass and emits
  the complete inventory;
- Macro `engine/codex_provider.py:92-120` assigns capability IDs by configured home order, while
  `:152-239` returns only secret-free orthogonal presence/enablement/executable observations;
- Mastermind `ops/executive_os/provider_worker_slots.py:80-115` freezes the distinct Personal Pro
  principals and homes;
- Mastermind `ops/executive_os/bootstrap-host.sh:343-424,446-462` enforces distinct groups and
  mode-0700 roots/homes;
- Mastermind `control_plane/executive_worker_broker.py:1285-1298` refuses unexpected supplementary
  groups;
- Mastermind `control_plane/executive_runtime.py:2907-3033` supplies the immutable additive quota
  registration seam;
- Mastermind `control_plane/executive_runtime.py:8724-8776` performs command replay before candidate
  selection;
- Mastermind `control_plane/executive_runtime.py:8904-8964` applies current hard filters and stable
  route rank;
- Mastermind `control_plane/executive_runtime.py:8967-9116` seals the unchanged placement, quota
  hold, Attempt, Job transition and `JOB_CLAIMED` event in one transaction;
- Mastermind `control_plane/executive_orchestration_principal.py:221-263` keeps the placement object
  closed to exactly six fields;
- Mastermind `control_plane/executive_runtime.py:2286-2329` persists canonical event payload JSON in
  the existing `events.payload_json` column.

Phase 1F-C schema-v4 landed through Mastermind PR #116 at merge
`db0bac5fe3f72348262d42c8bd26b836bda9f61d`; no current installed-runtime proof is inferred from
that merge.

### 2.4 Rejected shortcuts

CF2 implementation must not:

- run provider-capacity code as root or the Chairman's interactive account;
- add a shared credential group, supplementary worker groups, ACLs or weaker home modes;
- copy, link, export or centrally cache `auth.json` or provider-native tokens;
- infer logical account identity from path, browser seat, array order or account label;
- run three full CF1 snapshots and merge them inside Executive;
- import Macro's private `_build_snapshot_from_observations` test seam;
- reimplement CF1 normalization or canonical hashing in Mastermind;
- add a bridge daemon merely to cross the principal boundary.

These shortcuts either weaken the accepted realm boundary or create a second producer/truth plane.

---

## 3. Frozen acquisition architecture

The accepted implementation target is:

```text
AttemptRegistry command replay lookup
        |
        | no historical claim found
        v
read-only Executive preflight produces lawful available candidates
        |
        v
Macro acquisition-begin executable (control principal; no provider state)
        |
        | closed request envelope, bounded lifetime
        v
existing worker broker for each candidate realm (peer-UID authenticated)
        |
        | fixed idle-only capacity-observe operation for candidate realms only
        v
Macro fragment executable under that worker's existing UID/environment
        |
        | one closed secret-free normalized slot fragment
        v
Executive control gathers fragments without interpreting provider evidence
        |
        v
Macro acquisition-finalize executable (strict stdin; no provider credentials)
        |
        | one complete validated mastermind.provider_capacity.v1 document
        v
Mastermind independent strict consumer
        |
        v
immutable slot-to-quota join -> deterministic capacity ranking
        |
        v
existing atomic JOB_CLAIMED event + unchanged placement snapshot
```

Macro remains the only normalization/canonical-hash producer. Mastermind owns transport,
candidate eligibility, deterministic selection and lifecycle. The worker broker is extended; it
is not replaced and no provider-specific broker is added.

### 3.1 Implementation carrier sequence

CF2-I is implemented through three bounded subcarriers, never one cross-repository merge bomb:

1. **CF2-I-A / Macro distributed producer:** public acquisition-envelope, fragment and finalize
   entrypoints plus strict schemas/golden vectors; no provider calls, no persistence, no
   Mastermind changes.
2. **CF2-I-B / Mastermind acquisition transport:** one closed idle-only read operation on the
   existing worker-broker protocol, exact per-realm immutable capability binding, three broker
   service composition and strict Macro executable invocation; no claim ranking yet.
3. **CF2-I-C / Mastermind claim integration:** independent strict final-snapshot consumer,
   capacity join/ranking, atomic event evidence, replay/conflict law and the real three-seat
   canary; no provider adapter or schema migration.

Each subcarrier receives an independent review and exact-head hosted proof. Failure of an earlier
subcarrier holds later ones without authorizing another acquisition design.

---

## 4. Macro-owned distributed producer protocol

The exact field names may be implemented only as frozen here. All JSON is canonical UTF-8 with
sorted keys, compact separators, no NaN/Infinity and no trailing bytes. In every digest below,
`canonical(x)` means those exact bytes and `sha256` means lowercase hexadecimal SHA-256 over those
bytes.

### 4.1 Acquisition envelope

Closed schema `mastermind.provider_capacity.acquisition_request.v1`:

```json
{
  "schema": "mastermind.provider_capacity.acquisition_request.v1",
  "request_id": "<32-lower-hex>",
  "snapshot_generated_at": "2026-08-26T01:45:00Z",
  "expires_at": "2026-08-26T01:45:30Z",
  "host_ref": "local-unbound",
  "required_capability_ids": ["codex_account_2", "codex_account_3"],
  "producer": {},
  "producer_audit": {},
  "request_digest": "<64-lower-hex>"
}
```

Rules:

- the Macro begin executable owns `request_id`, both times, producer identity and digest;
- `expires_at` is exactly 30 seconds after `snapshot_generated_at`; the numeric future-clock
  tolerance is 2 seconds at begin, worker, finalizer and claim commit;
- first single-host V1 may use accepted `local-unbound` only because every broker and Executive
  control socket is on the same attested host; it is not a remote address;
- `required_capability_ids` is the sorted, unique set of capability IDs joined to the current
  preflight hard-eligible candidate set; it contains one to three members drawn only from
  `codex_account`, `codex_account_2`, and `codex_account_3`;
- only trusted Executive preflight may supply that derived subset; no Job, caller, prompt, model or
  Slack payload may author it, and Macro rejects any identity outside the fixed inventory;
- `request_digest = sha256(canonical(request_without_request_digest))`; the excluded field is
  exactly `request_digest` and no other field is omitted;
- canonical envelope size is at most 4 KiB.

### 4.2 Immutable realm-to-capability join

The installed root-owned worker configuration freezes exactly:

```text
codex-pro-01 -> codex_account
codex-pro-02 -> codex_account_2
codex-pro-03 -> codex_account_3
```

The worker broker supplies only its own immutable configured capability ID to the Macro fragment
executable. Macro validates that identity against the envelope and its reviewed inventory. Neither
control nor a model may choose or rewrite the mapping at request time.

This is a cross-system join, not a second provider identity registry. Macro remains owner of
`capability_id`; Mastermind remains owner of worker/slot/principal identity.

### 4.3 Slot fragment

Closed schema `mastermind.provider_capacity.fragment.v1`:

```json
{
  "schema": "mastermind.provider_capacity.fragment.v1",
  "request_digest": "<64-lower-hex>",
  "host_ref": "local-unbound",
  "capability_id": "codex_account_2",
  "producer": {},
  "producer_audit": {},
  "slot": {},
  "degraded": [],
  "observed_at": "2026-08-26T01:45:00Z",
  "fragment_hash": "<64-lower-hex>"
}
```

`slot` is the exact complete closed CF1 slot object for that capability. `degraded` contains only
producer-global rows required to interpret that fragment and rows scoped to that capability. The
fragment producer:

- executes under the worker's existing UID and exact allowlisted environment;
- may observe only its configured provider home and already-owned local Provider Control sources;
- never performs a provider/network call;
- never opens or serializes auth contents;
- never returns a path, UID, username, browser-seat label, email, account/provider-native ID,
  token, cookie, secret-ref name, raw stderr or exception text;
- fails with one closed refusal code rather than a partial structurally valid fragment;
- evaluates projection-time presence, enablement and all freshness against the envelope's exact
  `snapshot_generated_at`; `observed_at` is only the bounded fragment-completion receipt and must
  lie between `snapshot_generated_at` and `expires_at` plus the 2-second clock tolerance;
- sets `fragment_hash = sha256(canonical(fragment_without_fragment_hash))`; the excluded field is
  exactly `fragment_hash` and no other field is omitted;
- emits at most 32 KiB and exits within 5 seconds.

There must be exactly one fragment for every requested capability ID and no other fragment. Every
fragment binds the same request digest, producer implementation/version, repository commit and
material-source digest. Mixed releases, duplicate capability IDs, missing requested fragments,
unexpected fragments, stale observations or different `host_ref` values refuse. Non-requested
inventory slots never block this acquisition.

### 4.4 Finalization

The Macro finalize executable receives one canonical object on stdin containing the envelope and
the fragments. It accepts at most 256 KiB, reads no provider home and receives no secret-bearing
environment. It independently:

1. validates every closed schema/hash/time/source binding;
2. requires exactly one fragment for each requested Codex capability and none for non-requested
   capabilities;
3. preserves the complete accepted twelve-slot CF1 inventory;
4. emits explicit unknown/degraded rows for inventory slots without a lawful observation source;
5. sets the final document `generated_at` exactly equal to the envelope's
   `snapshot_generated_at`, and uses that same instant for every projection-time normalization and
   freshness calculation;
6. computes the final semantic `snapshot_hash` under the accepted CF1 law;
7. emits exactly one strict `mastermind.provider_capacity.v1` document of at most 256 KiB;
8. writes no file/database/cache and exits within 5 seconds.

The aggregation/finalization entrypoint must be public and reviewed in Macro. Mastermind may call
the executable; it may not import the implementation or build the snapshot itself.

---

## 5. Mastermind acquisition port and worker-broker operation

Mastermind defines one internal `ProviderCapacitySource`-equivalent port whose only successful
return is a fully validated immutable `mastermind.provider_capacity.v1` value plus canonical bytes.
The production implementation is the fixed distributed Macro executable path above. Tests may use
an inert fake implementing the same closed return; production config may not select arbitrary
commands, modules or URLs.

### 5.1 Fixed subprocess law

Every Macro invocation uses:

- an absolute root-owned installed release path pinned to exact accepted commit/material digest;
- fixed executable and argv, direct execution, never a shell;
- empty stdin except the finalizer's bounded canonical document;
- fixed root-owned working directory;
- `-I -S -B` where Python entrypoints permit;
- a newly constructed allowlisted environment containing no inherited auth/token/cookie/Keychain,
  clipboard, proxy, Git credential or interactive-login variables;
- bounded stdout captured in memory, stderr discarded or mapped to a closed refusal code;
- closed timeout and process-group cleanup;
- no fallback executable, PATH search, floating checkout or user-writable code.

### 5.2 Existing broker extension only

The worker operation is `capacity-observe/v1`. It is:

- read-only and valid only while that exact worker/quota has no held Attempt/provider process;
- authorized by the existing control-to-worker peer UID and exact installed service configuration;
- bound to one envelope digest and the broker's immutable capability ID;
- unable to accept a home path, executable path, capability ID or arbitrary environment from
  control;
- limited to a 4 KiB request and 32 KiB response;
- complete within 8 seconds including subprocess cleanup;
- non-retriable through another worker under the same request after an ambiguous response.

Only brokers represented in `required_capability_ids` are contacted. A worker already holding an
Attempt is absent from the preflight candidate set, so its idle-only broker refusal cannot block a
second child from using another available realm. The finalizer still emits the full twelve-slot
inventory, with explicit unknown/degraded evidence for every non-requested slot.

If a requested broker response is uncertain, the entire capacity acquisition is refused and no Job is
claimed. A later claim command may start a new acquisition only after canonical command replay
proves the prior command did not commit.

### 5.3 Three broker services are composition, not three runtimes

The three Personal Pro worker services may each run the existing worker-broker implementation
under their own reviewed UID, socket and provider home. They do not receive separate Executive
databases, queues, schedulers, retry state or control services. One `_mastermind_exec` control
runtime remains lifecycle authority.

---

## 6. Capacity-slot to Executive-quota join

The join lives as one closed nested object in existing immutable quota-registration metadata:

```json
{
  "capacity_join": {
    "schema": "mastermind.executive_capacity_join/v1",
    "host_ref": "local-unbound",
    "capability_id": "codex_account_2",
    "provider_capacity_schema": "mastermind.provider_capacity.v1"
  }
}
```

Rules:

- the nested object has exactly those four keys;
- `register_quota_class()` existing byte-equivalent reconciliation makes the join immutable;
- exactly one registered `(worker_id, quota_class)` maps to one `(host_ref, capability_id)`;
- duplicate joins, missing joins, provider mismatch or drift refuse before ranking;
- the join does not contain a provider home, UID, account email/name, OAuth seat, token, host
  address or provider-native session identity;
- `local-unbound` is lawful only for this explicitly same-host local V1 canary;
- MH1 must replace it with a reviewed authenticated host binding before remote placement.

No new table or placement field is authorized.

---

## 7. Deterministic claim sequence and capacity policy

For command-bound orchestration claims the order is frozen as a two-phase operation. No broker,
socket, subprocess or other external acquisition may occur while `BEGIN IMMEDIATE` holds the
Executive lifecycle writer lock.

**Read-only preflight and acquisition, outside the write transaction:**

1. validate the bounded command target;
2. perform a read-only `command_id` lookup; if historical `JOB_CLAIMED` exists, validate and return
   it with zero acquisition;
3. in a short read transaction, validate Job state, attempt limits, authority, orchestration
   lineage and requeue chain;
4. collect currently AVAILABLE/unheld quota rows and apply every existing quarantine, requested
   worker/quota, route, execution-profile, capability-policy, provider/model/effort/cost, identity
   and required-capability filter;
5. validate the immutable capacity joins, derive the sorted unique one-to-three requested
   capability IDs and compute `preflight_candidate_digest` over canonical candidate semantic rows;
6. close the read transaction; if no lawful candidate remains, return no claim with zero
   acquisition;
7. acquire one strict grounded distributed capacity snapshot for only that requested subset,
   entirely outside any SQLite write transaction.

**Atomic recheck and commit, inside the existing write transaction:**

8. open the existing `BEGIN IMMEDIATE` transaction and re-check `command_id` first; if another
   writer committed it, discard the fresh acquisition and return the one persisted Attempt and
   evidence;
9. reload and revalidate the Job semantic target, state, attempt/requeue/authority law, every
   hard-filter input, current AVAILABLE/unheld candidate rows, immutable joins, routing/policy
   identity and snapshot freshness;
10. recompute the candidate semantic rows and require byte equality of
    `preflight_candidate_digest`; any drift returns `CAPACITY_PREFLIGHT_CONFLICT` with no mutation
    and no external I/O under the lock;
11. validate the final snapshot, evaluate only the unchanged hard-eligible candidate rows and rank
    deterministically;
12. derive the claim/lease timestamp now, after acquisition, then atomically hold quota, create the
    Attempt, transition the Job and append `JOB_CLAIMED.capacity_evidence` while leaving the closed
    placement bytes/digest unchanged;
13. commit and return the Attempt.

`preflight_candidate_digest = sha256(canonical(preflight_object))`. The closed
`mastermind.executive_capacity_preflight/v1` object has exactly `schema_version`,
`command_target`, `job`, `policy` and `candidates`:

- `command_target` has exactly `command_id`, `job_id`, `requested_worker_id`,
  `requested_quota_class`, `lease_owner` and `lease_seconds`, normalized exactly as existing replay
  law does;
- `job` has exactly `job_id`, `status`, `version`, `attempt_count`, `attempt_limit`,
  `available_at_ms`, `current_attempt_id`, `orchestration_role`, `authority_policy_hash`,
  `constraints_digest`, `requested_authorities_digest`, `allowed_write_paths_digest`,
  `validation_commands_digest`, `orchestration_lineage_digest`, `requeue_chain_digest` and
  `effective_grant_digest`; every `*_digest` is SHA-256 over the existing normalized canonical value
  or the canonical validated rows it names;
- `policy` has exactly `coo_cycle_policy_digest`, `model_route_policy_digest`,
  `capability_policy_digest` and `capacity_policy_digest`;
- `candidates` is sorted by `(worker_id, quota_class)` and each row has exactly `worker_id`,
  `quota_class`, `quota_status`, `quota_version`, `held_attempt_id`, `fence_counter`, `provider`,
  `model`, `effort`, `cost_class`, `capabilities_digest`, `quota_metadata_digest`,
  `worker_provider`, `worker_account_label`, `identity_status`, `capacity_join` and `route_rank`.

The object contains only candidates that passed the existing hard filters. Nulls remain JSON null;
sets are sorted unique arrays; policy/constraint/capability/metadata objects are validated before
hashing. The object is kept only in process memory until a successful claim, then only its digest
is included in the acquisition receipt. Any future hard-filter input not represented by this
closed object is a source-law change, not an implementation liberty.

Drift does not trigger an automatic reacquisition loop or failover inside the invocation. A later
invocation of the same command may try again only after replay proves no canonical claim exists.
Concurrent same-command callers may duplicate read-only acquisition, but only one transaction may
commit; the loser must reconcile the winner and create no second Attempt/Event/provider turn.

Capacity cannot make an ineligible candidate eligible and cannot change Model Router suitability.

### 7.1 First Codex-only policy

The policy is deterministic and model-free.

Hard capacity exclusions:

- missing/duplicate/drifting join;
- snapshot ungrounded, expired, oversized, invalid or producer material mismatch;
- `present=false` or `present=null`;
- `enabled=false` or `enabled=null`;
- fresh health `unavailable`;
- `cooling.active=true` with current trusted evidence;
- fresh known exhaustion for the relevant five-hour/weekly horizon;
- slot/provider/capability identity mismatch.

Unknown/stale evidence is not free capacity:

- unknown/stale health remains eligible only with an explicit penalty when readiness and presence
  are independently true;
- `cooling.active=null` remains eligible only with an explicit cooling-unknown penalty; it never
  proves that cooling is clear;
- unknown/stale quota remains eligible only with an explicit penalty for the bounded routine
  canary, because CF1 currently reports honest unknowns for Codex allocation;
- fresh known healthy non-exhausted evidence outranks unknown/stale evidence;
- headroom comparisons are allowed only for the same Codex provider and the fixed
  `provider_allocation` five-hour/weekly horizons;
- stable `(worker_id, quota_class)` ordering breaks genuine ties.

For each horizon, a fresh finite quantitative row is one whose `freshness=fresh`, whose evidence is
`provider_reported` or `estimated`, and which contains either finite `used_percent` or a finite
positive `limit` plus finite `remaining`. Headroom percent is `100-used_percent` when present,
otherwise `100*remaining/limit`; disagreement or a value outside `[0,100]` refuses the candidate.
The multi-horizon bottleneck is the minimum known headroom across the five-hour and weekly rows.
For comparison it is converted from the canonical JSON decimal text to integer basis points using
decimal round-half-even. No known row means a null bottleneck, never 100 percent.

Eligible candidates sort lexicographically by this exact lowest-wins tuple:

```text
(
  cooling_rank,                 # false=0, null=1; true is excluded
  health_rank,                  # fresh available=0, fresh degraded=1, unknown/stale=2
  quota_coverage_rank,          # both horizons quantitative=0, one=1, none=2
  quota_evidence_rank,          # all known reported=0, mixed=1, all known estimated=2, none=3
  headroom_unknown_rank,        # numeric bottleneck=0, null=1
  negative_bottleneck_basis_points,  # greater known bottleneck wins
  worker_id,
  quota_class
)
```

Fresh health `unavailable`, known cooling active and fresh known exhaustion are excluded before the
tuple. `quota_evidence_rank=mixed` means the known horizon rows contain both provider-reported and
estimated evidence. Stale rows are unknown for ranking. Stable identifiers are used only after all
capacity dimensions genuinely tie.

The exact policy object whose canonical bytes are hashed is:

```json
{"cooling_unknown":"eligible_penalized","hard_exclusions":["join_invalid","snapshot_invalid","present_false_or_unknown","enabled_false_or_unknown","fresh_health_unavailable","cooling_active","fresh_quota_exhausted","slot_identity_mismatch"],"headroom_rounding":"decimal_round_half_even_basis_points","quota_horizons":["five_hour","weekly"],"quota_metric":"provider_allocation","rank_tuple":["cooling_rank","health_rank","quota_coverage_rank","quota_evidence_rank","headroom_unknown_rank","negative_bottleneck_basis_points","worker_id","quota_class"],"schema":"capacity-placement.v1","stale_evidence":"unknown","unknown_quota":"eligible_without_positive_headroom"}
```

`capacity_policy_digest = sha256(canonical(policy_object))`. No LLM interprets provider evidence,
chooses a worker or waives independence.

---

## 8. Closed `JOB_CLAIMED.capacity_evidence`

The existing v4 placement snapshot remains exactly six keys and byte-for-byte unchanged. Capacity
evidence is one nested object in the existing `JOB_CLAIMED` payload.

Closed schema `mastermind.executive_capacity_evidence/v1` has exactly:

```text
schema_version
capacity_snapshot_hash
capacity_snapshot_generated_at
producer_identity
producer_audit
capacity_policy_version
capacity_policy_digest
selected_slot
selected_slot_digest
selected_degraded_rows
candidate_decisions
acquisition_receipt
```

Semantics:

- `producer_identity` is the exact closed CF1 `producer` object;
- `producer_audit` is the exact closed CF1 `audit` object;
- `selected_slot` is the complete exact secret-free CF1 slot used for the decision;
- `selected_slot_digest` is SHA-256 over its canonical bytes;
- `selected_degraded_rows` contains only producer-global and selected-slot rows;
- `candidate_decisions` is deterministically ordered and contains only candidates already lawful
  under Executive/Router hard filters;
- `acquisition_receipt` is the exact closed object below and binds the preflight, requested subset,
  envelope digest, ordered fragments, installed Macro release/material identity and completion
  time without paths or principal names.

Each candidate decision has exactly:

```text
host_ref
capability_id
worker_id
quota_class
slot_evidence
slot_digest
degraded_rows
disposition
reason_codes
rank_vector
```

`slot_evidence` is the complete canonical secret-free CF1 slot for that candidate.
`slot_digest = sha256(canonical(slot_evidence))`. `degraded_rows` contains every producer-global and
candidate-scoped row needed to interpret that slot. Persisting full evidence for all one-to-three
capacity-evaluated candidates makes the historical choice independently explainable without a
mutable provider lookup. `selected_slot`, `selected_slot_digest` and `selected_degraded_rows` must
be byte-equal to the corresponding fields in the one selected candidate row.

`disposition` is `selected | eligible | excluded`. Excluded here means capacity-excluded after all
other hard filters; unauthorized or otherwise ineligible workers never enter this list.

`rank_vector` is either null for a hard-excluded candidate or an exact object with these eight
keys: `cooling_rank`, `health_rank`, `quota_coverage_rank`, `quota_evidence_rank`,
`headroom_unknown_rank`, `negative_bottleneck_basis_points`, `worker_id`, `quota_class`. Its values
must reproduce the tuple in Section 7.1 exactly.

The closed candidate reason vocabulary is:

```text
CAPACITY_JOIN_MISSING
CAPACITY_JOIN_AMBIGUOUS
CAPACITY_JOIN_DRIFT
CAPACITY_SLOT_IDENTITY_MISMATCH
CAPACITY_PRESENT_FALSE
CAPACITY_PRESENT_UNKNOWN
CAPACITY_ENABLED_FALSE
CAPACITY_ENABLED_UNKNOWN
CAPACITY_HEALTH_AVAILABLE
CAPACITY_HEALTH_DEGRADED
CAPACITY_HEALTH_UNKNOWN
CAPACITY_HEALTH_STALE
CAPACITY_HEALTH_UNAVAILABLE
CAPACITY_COOLING_CLEAR
CAPACITY_COOLING_UNKNOWN
CAPACITY_COOLING_ACTIVE
CAPACITY_QUOTA_COMPLETE
CAPACITY_QUOTA_PARTIAL
CAPACITY_QUOTA_UNKNOWN
CAPACITY_QUOTA_REPORTED
CAPACITY_QUOTA_ESTIMATED
CAPACITY_QUOTA_MIXED
CAPACITY_QUOTA_STALE
CAPACITY_QUOTA_EXHAUSTED
CAPACITY_SELECTED
CAPACITY_ELIGIBLE_LOWER_RANK
CAPACITY_STABLE_TIE_BREAK
```

Reason lists are sorted, unique and contain only facts applicable to the row.

Closed `acquisition_receipt` schema `mastermind.executive_capacity_acquisition_receipt/v1` has
exactly:

```json
{
  "schema_version": "mastermind.executive_capacity_acquisition_receipt/v1",
  "preflight_candidate_digest": "<64-lower-hex>",
  "request_digest": "<64-lower-hex>",
  "requested_capability_ids": ["codex_account_2", "codex_account_3"],
  "fragment_receipts": [
    {"capability_id": "codex_account_2", "fragment_hash": "<64-lower-hex>"},
    {"capability_id": "codex_account_3", "fragment_hash": "<64-lower-hex>"}
  ],
  "macro_release_commit": "<40-lower-hex>",
  "producer_material_source_digest": "<64-lower-hex>",
  "completed_at": "2026-08-26T01:45:04Z"
}
```

The two lists are sorted by capability ID. They contain the same one-to-three identities exactly.
The material digest equals the final CF1 producer audit; the installed release commit equals the
attested Macro executable release; `completed_at` is UTC, is not before `snapshot_generated_at`,
and is not after `expires_at` plus the 2-second clock tolerance. Any extra key, duplicate, mismatch
or bound violation refuses before mutation.

Bounds:

- at most 3 candidate decisions in the Codex-only first vertical;
- at most 16 reason codes per candidate, each at most 64 ASCII characters;
- at most 32 degradation rows per candidate;
- canonical `capacity_evidence` at most 64 KiB;
- complete canonical `JOB_CLAIMED` payload at most 128 KiB;
- any bound violation refuses before quota hold/Attempt creation.

No token, cookie, auth path, secret ref, email, username, hostname, IP, UID, browser-seat label,
provider-native account/session ID, raw provider output or exception text is permitted.

---

## 9. Replay, conflict, timeout and correction law

### 9.1 Replay before acquisition

The first operation is a read-only `command_id` event lookup before acquisition, followed by the
same lookup as the first operation inside the eventual write transaction. When either lookup finds
the event:

- validate the historical event target and closed capacity evidence;
- return the persisted historical Attempt/outcome;
- perform zero broker calls, zero Macro subprocesses, zero provider/home observations and zero
  ranking;
- never compare the historical evidence to current capacity state.

### 9.2 Semantic conflict

Production callers do not supply capacity evidence. If a lower-level test/internal API supports
an expected evidence argument, only canonical byte equality to the persisted object reconciles.
Changed normalized snapshot, policy, selected slot, candidate list, worker/quota, request target,
lease semantics or snapshot time under the same command conflicts.

### 9.3 Ambiguous effects

- timeout before the atomic claim commits produces no Attempt and no Job transition;
- timeout after commit is `EFFECT_UNKNOWN`; replay the same command through the same carrier;
- a committed historical event returns the same Attempt and performs zero second acquisition;
- absent canonical event permits a new acquisition for the same command only after current Job
  state still proves the claim never committed;
- never fail over the ambiguous request to another worker/provider/host.

### 9.4 Corrections

Later provider observations create future snapshots only. They never rewrite historical
`JOB_CLAIMED` evidence, placement, Attempt or result. Provider failure after an Attempt begins is
first reconciled through the existing Attempt/effect law; it does not authorize immediate blind
cross-account retry.

---

## 10. Schema and no-rebuild boundaries

CF2-F proves the existing event payload is sufficient. CF2 implementation must add zero:

- SQLite schema version, migration or column;
- provider/account/quota/cooling/health table;
- event type or placement snapshot field;
- capacity snapshot cache/file/database;
- Executive provider normalizer or semantic hash implementation;
- worker queue, scheduler, lifecycle, retry ledger or Executive Runtime;
- provider-specific broker/service;
- long-lived bridge daemon;
- root/interactive credential observer;
- direct Macro Python import or raw Macro ledger parser;
- live quota/model/provider state in Model Router policy;
- automatic retry/failover after ambiguous provider effect.

The existing `events.payload_json`, existing atomic `JOB_CLAIMED`, existing immutable quota metadata
and existing worker-broker transport are the only Mastermind persistence/transport surfaces used.

---

## 11. Test and mutation matrix

### CF2-I-A / Macro producer

Require tests that:

- reject missing/extra keys, invalid hashes/times, NaN/Infinity, duplicate identities and trailing
  stdout;
- prove explicit capability binding maps the three isolated realms exactly and never by path/order;
- reject mixed commit/material digests and altered request envelopes;
- prove one-, two- and three-ID requested subsets; a non-requested busy realm cannot block the
  available subset and the final inventory remains twelve slots with explicit unknowns;
- preserve twelve-slot inventory with explicit unknown/degraded rows for unavailable fragments;
- keep `generated_at` nonsemantic while source observations/material identity remain semantic;
- prove fragment/finalizer output redlines all credential/path/PII classes;
- prove zero provider calls and zero writes;
- prove fixed bounds and golden canonical vectors.

Mutation kills must include swapping codex account 2/3 identities, dropping a fragment, treating
unknown as false/free, accepting mixed producer commits and allowing a path in a fragment.

### CF2-I-B / Mastermind acquisition

Require tests that:

- fixed absolute argv uses no shell/PATH/user checkout and inherits no sensitive environment;
- each broker can request only its own immutable capability ID/home;
- wrong peer UID, supplementary group, worker-busy state, unexpected capability, oversized output,
  timeout, nonzero exit or malformed fragment refuses;
- three service instances share one Executive Runtime/database and have distinct sockets/Uids/homes;
- zero auth bytes are opened by Executive or returned across broker;
- ambiguous broker response causes no claim and no cross-worker retry;
- installed release/material identity is attested.

### CF2-I-C / claim integration

Require tests that:

- command replay occurs before acquisition and invokes the source zero times;
- a capacity source blocked longer than SQLite's five-second busy timeout does not hold the
  lifecycle writer lock and does not delay an unrelated Job/Event/Attempt writer;
- every existing hard filter runs before capacity ranking;
- missing/duplicate/drifting join refuses;
- false/null presence or enablement, fresh unavailable health, active cooling and fresh exhaustion
  exclude exactly as frozen;
- unknown/stale penalties never become free/unlimited headroom;
- ranking and reason codes are stable under input order changes;
- golden vectors independently recompute request, fragment, preflight, policy, slot, snapshot and
  acquisition-receipt digests plus the exact multi-horizon rank decision;
- every capacity-evaluated candidate persists its complete canonical slot/degradation/rank evidence
  and independently explains the selected/lower/excluded disposition;
- capacity evidence bounds/privacy validators reject before mutation;
- one transaction commits quota hold, Attempt, Job transition, unchanged placement and exact
  capacity evidence together—or none;
- a concurrent race creates exactly one Attempt;
- concurrent same-command callers may duplicate read-only acquisition but the losing write
  transaction reconciles the winner and creates no second Attempt/Event/provider turn;
- preflight/transaction candidate or policy drift returns `CAPACITY_PREFLIGHT_CONFLICT`, performs no
  mutation and never reacquires while the writer lock is held;
- changed same-command evidence conflicts while exact replay returns history without acquisition;
- later correction leaves historical evidence unchanged;
- exact pre-CF2 v4 placement canonical bytes/digest and normalized SQLite schema digest do not
  change.

---

## 12. Real production proof owed by CF2-I

The final CF2-I canary must use an exact accepted installed release and prove:

1. all three Personal Pro realms have separate sanitized readiness and inference-canary receipts;
2. all three worker brokers run under the correct distinct principals with one canonical Executive
   Runtime;
3. three immutable worker/quota joins bind the exact Codex capability IDs;
4. one complete grounded fresh `mastermind.provider_capacity.v1` snapshot is obtained through the
   distributed Macro producer path without root/shared credential access;
5. one harmless Chairman-authorized Executive Job chooses deterministically among the three
   already-eligible seats and persists exact capacity evidence atomically;
6. one real worker execution reaches a terminal result;
7. replay of the same command performs zero second acquisition/provider turn/Attempt;
8. a future observation change does not alter the historical claim;
9. disarm/rearm and recovery preserve one lifecycle and no hidden provider process;
10. secret/PII scans and before/after write receipts remain clean.

The proof packet names exact release, Mastermind/Macro commits, process principals in sanitized
form, snapshot/policy/slot/event digests, Job/Attempt/command identities, terminal result and every
degraded/null field. It never publishes auth material or account identity.

---

## 13. Cursor and Grok boundary

Cursor and Grok are parallel V1.x provider verticals under the accepted Autonomy V1 closure:

- read-only official auth/session/capability research may continue now;
- neither receives a Codex home, capacity identity or provider-specific broker;
- Cursor subscription-browser OAuth is not assumed exportable or silently renewable; supported
  service-account/API/cloud-agent paths must remain distinct from human login;
- Grok/xAI API-key inference remains distinct from Grok Build's supported OIDC/device/enterprise
  auth-provider path;
- executable integration waits for RF1 provider-neutral suitability and HF1 common harness law;
- their implementation cannot modify this Codex-only CF2 first vertical or hold its acceptance.

---

## 14. Acceptance, stop and continuation

This CF2-F records-only carrier passes only when an independent reviewer proves:

1. protected Mastermind and compatible Skillpack were pinned exactly;
2. accepted CF1 candidate/merge and current #149 integration freeze are named;
3. the current single-principal acquisition falsifier is preserved honestly;
4. the distributed read path preserves mode-0700/principal isolation and one Macro producer;
5. exact acquisition, fragment, join, evidence, bounds, privacy, time, null, correction and replay
   laws are closed;
6. existing `JOB_CLAIMED` is sufficient and placement/schema remain unchanged;
7. implementation is split into bounded Macro producer, Mastermind transport and Mastermind claim
   carriers with exact proof gates;
8. Cursor/Grok research remains parallel while executable adapters remain RF1/HF1-gated.

Merge makes this source law `SPEC_ONLY`. It does not install services, authenticate accounts,
enable routing, place work, spawn sessions, grant MCP/plugins, deploy to a VPS or arm autonomy.

After PASS/merge, the exact next action is CF2-I-A: implement the Macro-owned distributed
fragment/finalize producer as one no-write independently useful carrier. CF2-I-B remains held until
that exact contract is accepted. Personal Pro readiness may continue on its separate host carrier,
and Cursor/Grok source research may continue on disjoint read-only carriers.

Stop and return to Sol if implementation proves the existing broker cannot carry the bounded read,
the final projection cannot remain Macro-owned, the closed event payload cannot fit the evidence,
or any proposed repair requires shared/root credential observation, another service family, another
database/event/lifecycle, schema v5 or changed placement identity.
