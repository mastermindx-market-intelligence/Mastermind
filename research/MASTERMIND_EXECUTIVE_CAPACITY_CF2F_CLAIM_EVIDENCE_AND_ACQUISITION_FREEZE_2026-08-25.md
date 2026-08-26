# Executive Capacity Fabric CF2-F — acquisition, claim-evidence and replay source law

**Date:** 2026-08-25
**Owner:** Sol, AI CEO
**Chairman:** Chris
**Status:** **SOL SOURCE-LAW FREEZE / RECORDS-ONLY CARRIER. No runtime, worker, login, route or service is changed by this document.**
**Current protected Mastermind / Skillpack basis:** `cdfecc6f6b382862238c15fe1d5bd646eb62213c`
**Autonomy V1 architecture parent:** `eff2033c639cb25f8b4a2a4e5f90e1a4a6002138`
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1, loaded atomically from the current protected commit above.
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

> The unchanged strict Macro CF1 projection remains provider truth even when its isolated Codex
> `present` fields are honestly null. Executive acquires that projection from one exact grounded,
> root-owned Macro release without gaining provider-home access, asks each relevant existing worker
> broker for one bounded realm-local readiness observation, and joins the two evidence owners at
> claim time without rewriting either. Executive consumes provider capacity; it does not become a
> second provider normalizer.

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
| Central grounded CF1 acquisition path | `DARK_OR_DISCONNECTED` | A safe installed Macro producer/telemetry path must be proven by CF2-P0. |
| Per-realm broker `capacity-observe/v1` | `NOT_BUILT` | Required additive fixed read operation on the existing worker-broker boundary. |
| Three worker-broker service composition | `NOT_BUILT` | Current protected readiness realms do not start or fan out three worker services. |
| Typed `JOB_CLAIMED.capacity_evidence` | `NOT_BUILT` | Existing event/transaction is sufficient; the exact extension is frozen below. |
| Capacity-aware claim ranking | `NOT_BUILT` | Must remain after all existing route/authority/capability/identity filters. |
| Cursor and Grok source/auth archaeology | may proceed in parallel | It does not touch this carrier. Executable adapters remain gated by RF1/HF1. |

No row above is upgraded by this records-only source law.

---

## 2. Estate reconciliation and concrete blocker

### 2.1 CF1 already supports honest isolation-null evidence

Accepted Macro CF1 calls the Codex owner once. `capacity_account_observations()` enumerates the
producer-owned ordered `CODEX_ACCOUNT_HOMES` inventory, assigns the stable `codex_account`,
`codex_account_2`, and `codex_account_3` identities by that accepted order, and checks only
`auth.json` filesystem metadata. When the metadata check receives `PermissionError`/`OSError`, it
emits `present=null` plus the required scoped `SOURCE_UNREADABLE` and
`PROVIDER_PRESENCE_UNKNOWN` degradation instead of inventing false absence. The strict v1
validator accepts exactly that honest-null state.

The normalizer separately joins existing Provider Control health, cooling, budget and outcome
owners before emitting one complete twelve-slot snapshot. It never opens auth bytes. Those
properties remain frozen.

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

The lawful central producer configuration must list the exact three canonical Personal Pro homes
in Macro's accepted producer-owned order while `_mastermind_exec` retains zero traverse authority.
That fixed root-owned order is a Macro inventory input; Mastermind may never infer capability
identity from response position or provider-home path.

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
- add a Macro fragment/envelope/finalizer protocol when the accepted strict v1 null law already
  preserves the isolation boundary;
- import Macro's private `_build_snapshot_from_observations` test seam;
- reimplement CF1 normalization or canonical hashing in Mastermind;
- add a bridge daemon merely to cross the principal boundary;
- equate an Executive `account_label` with a Macro `capability_id`.

These shortcuts either weaken the accepted realm boundary or create a second producer/truth plane.

---

## 3. Frozen acquisition architecture

The accepted implementation target is:

~~~text
outer command replay lookup
        |
        | no historical claim found
        v
short read-only Executive hard-eligibility preflight
        |
        +------------------------------+
        |                              |
        v                              v
one unchanged strict CF1 snapshot      relevant existing worker brokers
under _mastermind_exec                 under each dedicated worker UID
        |                              |
        | provider capacity truth      | fixed capacity-observe/v1
        |                              | realm/readiness evidence only
        +---------------+--------------+
                        v
immutable (host_ref, capacity_capability_id) join
                        |
                        v
Mastermind strict consumer + deterministic capacity rank
                        |
                        v
BEGIN IMMEDIATE
  -> command/candidate/freshness recheck
  -> existing atomic JOB_CLAIMED event
  -> unchanged placement snapshot
~~~

Macro remains the only provider-capacity normalizer and semantic-hash producer. The existing worker
broker remains the private-principal readiness boundary. Mastermind owns the immutable join,
candidate eligibility, deterministic selection and lifecycle evidence. No side rewrites the other
side's historical facts.

The central CF1 process may know the fixed provider-home path strings through root-owned
configuration but receives no filesystem traverse/read authority to those homes. The worker broker
may inspect only metadata for its own fixed realm and never reads or returns credential bytes.

### 3.1 Implementation carrier sequence

The implementation sequence is bounded:

1. **CF2-P0 / read-only host census:** identify the actual Macro Provider Control producer/state
   roots, permission surfaces and installed Executive host topology; accept one safe source path or
   return `NO_SAFE_CF1_ACQUISITION_PATH`.
2. **CF2-I-A / grounded central acquisition:** add the strict Mastermind consumer and fixed
   acquisition of the unchanged CF1 projection from the accepted Macro path; no worker observation
   or claim ranking yet.
3. **CF2-I-B / worker-realm observation:** add one closed `capacity-observe/v1` operation to the
   existing broker and compose the three broker services with immutable capability bindings; no
   claim ranking yet.
4. **CF2-I-C / claim integration:** join the two evidence owners, rank already-lawful candidates,
   persist exact capacity evidence atomically and prove the real three-seat canary.

Each carrier receives independent exact-head review and hosted proof. Failure of an earlier gate
holds later work without authorizing another producer, daemon, credential group or lifecycle.

---

## 4. Unchanged Macro CF1 projection acquisition

### 4.1 CF2-P0 read-only host census

Before production acquisition code is commissioned, CF2-P0 must record without mutation:

1. the actual Macro Provider Control code/process root available to Executive;
2. the exact secret-free health/cooling/quota/outcome telemetry roots required by accepted CF1;
3. owner/group/mode/ACL/symlink boundaries without reading credential values;
4. whether an existing bounded Macro-owned process/API already emits strict
   `mastermind.provider_capacity.v1`;
5. whether the accepted CF1 code can instead run from a root-owned exact-commit grounded Git
   checkout under `_mastermind_exec` with only narrow telemetry access;
6. the fixed root-owned three-home inventory configuration and proof that `_mastermind_exec` cannot
   traverse any listed Personal Pro home;
7. the executable/process principal, exact release and source/state identity of the selected path.

The census makes no service, permission, group, file copy, login, provider call or production-arm
change. Its closed outcome is exactly one of:

~~~text
EXISTING_MACRO_PROJECTION_PATH_ACCEPTED
GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED
NO_SAFE_CF1_ACQUISITION_PATH
~~~

`NO_SAFE_CF1_ACQUISITION_PATH` holds CF2-I and returns to Sol. It does not authorize widening home
permissions, copying telemetry into Executive, running a root bridge or recreating CF1 logic.

`EXISTING_MACRO_PROJECTION_PATH_ACCEPTED` may be emitted only when that already-existing process/API
has a separately frozen exact local request/authentication/peer-principal/timeout/output/error and
release-identity contract satisfying Sections 4.2, 4.4 and 4.5. CF2-P0 discovery alone cannot invent
or infer that protocol. If an existing path is found without such a current source-law record, P0
pauses for that bounded follow-on freeze and CF2-I-A remains held; it must otherwise return
`NO_SAFE_CF1_ACQUISITION_PATH`. At this basis only the grounded-Git subprocess contract below is
closed by this record.

### 4.2 Allowed producer paths

An existing Macro-owned projection path is preferred only if it:

- emits the unchanged complete strict v1 projection;
- is bounded and locally authenticated;
- names exact producer/material/audit identity;
- reads canonical current Provider Control state;
- grants no new lifecycle or storage authority.

Otherwise CF2-I may install the accepted Macro CF1 merge
`dcdd939c45b23abce5ba04f95e330ac914a3904b` as a root-owned, non-group/other-writable, exact-commit
Git checkout. A copied source-only bundle is insufficient: accepted CF1 calls Git for
`repository_commit`, material blobs and `material_sources_match_commit`. The installed release must
retain the Git metadata and every material source required by the accepted receipt.

The selected path may read only the exact secret-free telemetry files accepted by CF2-P0. If that
requires access to a broader credential-bearing tree, the path refuses.

### 4.3 Fixed three-home producer inventory

Root-owned installed configuration supplies `CODEX_ACCOUNT_HOMES` as exactly three absolute
canonical Personal Pro home paths in Macro's accepted producer order:

~~~text
position 0 -> codex_account
position 1 -> codex_account_2
position 2 -> codex_account_3
~~~

This order belongs to the Macro producer contract. It is not a Mastermind runtime inference.
Mastermind never derives capability identity from path, position, response order, account label or
browser seat.

`_mastermind_exec` must remain outside all three worker groups and must fail to traverse/read each
home. The expected metadata outcome is therefore `present=null`, not false, for the isolated slots,
with exact scoped `SOURCE_UNREADABLE` and `PROVIDER_PRESENCE_UNKNOWN` rows. A false value means the
producer observed absence and cannot be overridden by worker evidence.

### 4.4 Fixed acquisition port

Mastermind defines one internal `ProviderCapacitySource`-equivalent port whose only successful
return is the strict immutable `mastermind.provider_capacity.v1` value plus canonical bytes.
Production configuration selects only the CF2-P0-accepted path. Tests may inject an inert fake
implementing the same closed return.

For the grounded Git path, the operation is conceptually:

~~~text
<absolute reviewed Python executable>
<absolute root-owned exact Macro Git checkout>/scripts/build_provider_capacity.py
~~~

with no caller/model-supplied arguments and without `--pretty`.

Every invocation:

- uses fixed absolute executable/source paths, direct execution and no shell/PATH lookup;
- uses a fixed root-owned working directory;
- sets stdin to null;
- uses a newly constructed allowlisted environment containing only required interpreter/runtime,
  fixed three-home inventory and accepted secret-free telemetry configuration;
- inherits no token, API key, cookie, Keychain, clipboard, proxy, Git credential or interactive
  login variable;
- captures stdout/stderr separately;
- accepts at most 256 KiB stdout and retains at most 4 KiB stderr internally;
- times out after 10 seconds and kills/reaps only its owned process group;
- never persists or forwards raw stderr, paths, exception text or provider responses;
- writes no file/database/cache and performs no provider/network call.

### 4.5 Canonical P0 and central-source configuration identity

The accepted P0 record is the exact canonical object
`mastermind.executive_capacity_p0_acceptance/v1` with exactly `schema_version`, `outcome`,
`source_kind`, `source_config_digest`, `macro_release_commit` and
`producer_material_source_digest`. `outcome` is one of the closed Section 4.1 values;
`source_kind` is `grounded_cf1_git_release` or `existing_macro_projection`; and the release/material
identities must equal the strict CF1 producer audit subsequently acquired. Its identity is
`p0_acceptance_digest = sha256(canonical(p0_record))`.

`source_config_digest = sha256(canonical(source_config))`, where the closed
`mastermind.executive_capacity_source_config/v1` object has exactly:

~~~text
schema_version
p0_source_kind
source_contract_id
source_release_commit
source_executable_identity_digest
source_entrypoint_identity_digest
source_working_directory_identity_digest
allowed_environment_names
inventory_config_digest
telemetry_config_digest
timeout_seconds
stdout_max_bytes
stderr_retained_max_bytes
no_shell
network_denied
write_denied
~~~

Digests are lower-case SHA-256 of the canonical root-owned installed object they name;
`allowed_environment_names` is a sorted unique string array; the fixed values are 10, 262144, 4096,
true, true and true for the final six fields. For the currently closed grounded path,
`source_contract_id=grounded_cf1_git_subprocess/v1`. An existing Macro projection requires its own
previously frozen contract identifier and exact protocol digest; it cannot reuse that identifier.
The accepted P0 record, source config and all referenced installed objects are root-owned,
non-group/other-writable and immutable for one acquisition. Receipts persist only their digests, not
paths, principals, home names or secret-bearing values.

Acquisition accepts only one UTF-8 JSON document with no trailing bytes and all accepted CF1 strict
v1 validation, including exact canonical snapshot hash,
`producer.material_source_digest`, `audit.repository_commit`, and
`audit.material_sources_match_commit=true`.

The acquired snapshot is valid for claim commit only while:

~~~text
snapshot.generated_at - 2 seconds <= trusted_current_utc
trusted_current_utc <= snapshot.generated_at + 32 seconds
~~~

The 30-second age budget plus 2-second clock tolerance is fixed. The same trusted current time is
used for post-acquisition claim/lease timestamping.

Closed acquisition refusal codes:

~~~text
CAPACITY_SOURCE_UNAVAILABLE
CAPACITY_SOURCE_TIMEOUT
CAPACITY_SOURCE_NONZERO_EXIT
CAPACITY_SOURCE_OVERSIZE
CAPACITY_SOURCE_INVALID_UTF8
CAPACITY_SOURCE_SCHEMA_INVALID
CAPACITY_SOURCE_HASH_INVALID
CAPACITY_SOURCE_UNGROUNDED
CAPACITY_SOURCE_STALE
CAPACITY_SOURCE_FUTURE
CAPACITY_SOURCE_INTERNAL
~~~

No acquisition cache, daemon, refresh scheduler or provider state copy is authorized.

---

## 5. Existing worker-broker realm observation

### 5.1 Fixed operation

The existing worker broker gains exactly one operation name:

~~~text
capacity-observe/v1
~~~

The request is the exact canonical object
`{"schema_version":"mastermind.executive_worker_capacity_observe_request/v1"}` and contains no path,
argv, environment variable, provider, capability, account, prompt, time or model-authored field.
The canonical request is at most 128 bytes.

Admission requires:

- exact configured Executive peer UID through kernel peer credentials;
- exact configured worker UID/GID and approved supplementary-group vector;
- valid current production autonomy authority when armed;
- no held Attempt/provider/validation/OHF process active or starting for that worker/quota;
- one immutable root-owned `(host_ref, capacity_capability_id)` binding;
- exact installed broker release and operation implementation.

The operation performs no provider call, creates no provider session and cannot execute an arbitrary
command.

### 5.2 Closed response

Canonical JSON is UTF-8, sorted-key, compact-separator, no NaN/Infinity and no trailing bytes.
The closed response has exactly:

~~~json
{
  "schema_version": "mastermind.executive_worker_capacity_observation/v1",
  "host_ref": "local-unbound",
  "capacity_capability_id": "codex_account_2",
  "realm_metadata_valid": true,
  "credential_present": true,
  "credential_metadata_valid": true,
  "provider_binary_attested": true,
  "broker_generation_ready": true,
  "source_config_digest": "<64-lower-hex>",
  "observed_at": "2026-08-26T01:45:00Z",
  "expires_at": "2026-08-26T01:45:15Z",
  "observation_digest": "<64-lower-hex>"
}
~~~

`expires_at` is exactly 15 seconds after `observed_at`.
`observation_digest = sha256(canonical(response_without_observation_digest))`; the excluded field is
exactly `observation_digest`.

`source_config_digest = sha256(canonical(worker_source_config))`, where the closed
`mastermind.executive_worker_capacity_source_config/v1` object has exactly:

~~~text
schema_version
host_ref
capacity_capability_id
broker_release_identity_digest
broker_operation_identity_digest
broker_generation
executive_peer_policy_digest
worker_realm_metadata_policy_digest
provider_binary_identity_digest
~~~

Every digest field is lowercase SHA-256 over the accepted root-owned canonical object it names;
`broker_generation` is the accepted nonnegative integer generation. The object contains no path,
UID, username, account label, provider-native identity or secret. Its digest must equal the expected
`worker_source_config_digest` in the immutable capacity join before the response is usable.

The operation:

- checks only the fixed own-realm directory/auth-object type, owner and mode metadata plus exact
  binary and broker generation/config identity;
- never opens, parses, copies, hashes or returns credential bytes;
- never returns a path, UID, username, Executive account label, browser seat, email, provider-native
  account/session ID, secret-ref name, raw exception or arbitrary filesystem metadata;
- emits at most 4 KiB and completes within 5 seconds;
- permits at most 2 seconds future clock skew;
- is valid at claim commit only when
  `observed_at - 2s <= trusted_current_utc <= expires_at + 2s`.

All five readiness booleans must be true. `credential_present=true` means only that the fixed auth
object exists with the reviewed metadata boundary; it does not claim provider acceptance or quota.
Existing G7/provider-readiness admission remains independently required and is not duplicated.

### 5.3 Refusal and ambiguity

Closed refusal codes:

~~~text
CAPACITY_OBSERVE_UNAUTHORIZED
CAPACITY_OBSERVE_WRONG_PRINCIPAL
CAPACITY_OBSERVE_GROUP_DRIFT
CAPACITY_OBSERVE_NOT_ARMED
CAPACITY_OBSERVE_BUSY
CAPACITY_OBSERVE_CONFIG_DRIFT
CAPACITY_OBSERVE_REALM_INVALID
CAPACITY_OBSERVE_CREDENTIAL_ABSENT
CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID
CAPACITY_OBSERVE_BINARY_UNATTESTED
CAPACITY_OBSERVE_GENERATION_UNREADY
CAPACITY_OBSERVE_TIMEOUT
CAPACITY_OBSERVE_OVERSIZE
CAPACITY_OBSERVE_SCHEMA_INVALID
CAPACITY_OBSERVE_DIGEST_INVALID
CAPACITY_OBSERVE_STALE
CAPACITY_OBSERVE_FUTURE
CAPACITY_OBSERVE_INTERNAL
~~~

Only brokers joined to the read-only preflight hard-eligible candidate set are contacted. A busy
non-candidate realm therefore cannot block another available seat. Missing, duplicate, invalid,
expired or ambiguous observation for any requested candidate refuses the whole claim invocation
before ranking or `JOB_CLAIMED`; no candidate decision or acquisition receipt is persisted. It is
never retried through another worker/broker under the same invocation. This conservative V1 law
keeps every successful receipt complete; per-candidate refusal would require a later frozen evidence
union and is not an implementation liberty.

A later invocation may observe again only after canonical command replay proves no claim committed.
After commit, historical observation/evidence is immutable.

### 5.4 Three brokers remain one runtime

The three Personal Pro services compose the same broker implementation under distinct reviewed
UIDs, sockets and homes. They receive no separate Executive database, queue, scheduler, retry
state, control service or lifecycle. One `_mastermind_exec` runtime remains authority.

---

## 6. Capacity capability to Executive-quota join

The join lives as one closed nested object in existing immutable quota-registration metadata:

```json
{
  "capacity_join": {
    "schema": "mastermind.executive_capacity_join/v1",
    "host_ref": "local-unbound",
    "capacity_capability_id": "codex_account_2",
    "provider_capacity_schema": "mastermind.provider_capacity.v1",
    "worker_source_config_digest": "<64-lower-hex>"
  }
}
```

Rules:

- the nested object has exactly those five keys;
- `register_quota_class()` existing byte-equivalent reconciliation makes the join immutable;
- exactly one registered `(worker_id, quota_class)` maps to one
  `(host_ref, capacity_capability_id)`;
- duplicate joins, missing joins, provider mismatch or drift refuse before ranking;
- each successful observation `source_config_digest` must equal the immutable join's
  `worker_source_config_digest`;
- the join does not contain a provider home, UID, account email/name, OAuth seat, token, host
  address or provider-native session identity;
- `local-unbound` is lawful only for this explicitly same-host local V1 canary;
- MH1 must replace it with a reviewed authenticated host binding before remote placement.

`capacity_capability_id` is the exact Macro CF1 capability identity. It is deliberately not named
or derived from Executive `account_label`; that existing field remains separate. No new table or
placement field is authorized.

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
5. validate the immutable capacity joins, derive the sorted unique one-to-three relevant
   `capacity_capability_id` values and compute `preflight_candidate_digest` over canonical
   candidate semantic rows;
6. close the read transaction; if no lawful candidate remains, return no claim with zero
   acquisition;
7. acquire one complete strict grounded CF1 snapshot, then call `capacity-observe/v1` exactly once
   for each relevant candidate broker, entirely outside any SQLite write transaction;
   any missing/duplicate/invalid/stale/ambiguous observation refuses the whole invocation here with
   no ranking, mutation or persisted candidate evidence;

**Atomic recheck and commit, inside the existing write transaction:**

8. open the existing `BEGIN IMMEDIATE` transaction and re-check `command_id` first; if another
   writer committed it, discard the fresh acquisition and return the one persisted Attempt and
   evidence;
9. reload and revalidate the Job semantic target, state, attempt/requeue/authority law, every
   hard-filter input, current AVAILABLE/unheld candidate rows, immutable joins, routing/policy
   identity, CF1 snapshot freshness and worker-observation freshness;
10. recompute the candidate semantic rows and require byte equality of
    `preflight_candidate_digest`; any drift returns `CAPACITY_PREFLIGHT_CONFLICT` with no mutation
    and no external I/O under the lock;
11. validate the final snapshot, evaluate only the unchanged hard-eligible candidate rows and rank
    deterministically;
12. derive one trusted current UTC time inside the transaction; require
    `snapshot.generated_at - 2s <= current_time <= snapshot.generated_at + 32s` and every
    `observation.observed_at - 2s <= current_time <= observation.expires_at + 2s`, then use that
    same time for the claim/lease timestamp and atomically hold quota, create the
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
- any false worker-realm readiness boolean; missing/duplicate/invalid/stale/ambiguous observations
  have already refused the whole acquisition before policy evaluation;
- `present=false`;
- `present=null` unless this is one of the three frozen Personal Pro isolation slots, the slot has
  the exact scoped `SOURCE_UNREADABLE` and `PROVIDER_PRESENCE_UNKNOWN` degradation, the central
  acquisition/config identity is attested and the matching worker observation is fully valid;
- `enabled=false` or `enabled=null`;
- fresh health `unavailable`;
- `cooling.active=true` with current trusted evidence;
- fresh known exhaustion for the relevant five-hour/weekly horizon;
- slot/provider/capability identity mismatch.

Worker evidence resolves Executive execution eligibility only. It never rewrites the persisted CF1
slot: an accepted isolation-null remains `present=null` historically. Worker evidence cannot
override CF1 disabled state, active cooling, known exhaustion or health unavailable.

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
`exact`, `provider_reported` or `estimated`, and which contains either finite `used_percent` or a finite
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
  quota_evidence_rank,          # all known exact/reported=0, mixed-with-estimated=1, all estimated=2, none=3
  headroom_unknown_rank,        # numeric bottleneck=0, null=1
  negative_bottleneck_basis_points,  # greater known bottleneck wins
  worker_id,
  quota_class
)
```

Fresh health `unavailable`, known cooling active and fresh known exhaustion are excluded before the
tuple. `quota_evidence_rank=mixed` means at least one known row is estimated and another is exact
or provider-reported. Exact and provider-reported rows share the highest evidence class. Stale rows
are unknown for ranking. Stable identifiers are used only after all
capacity dimensions genuinely tie.

The exact policy object whose canonical bytes are hashed is:

```json
{"cooling_unknown":"eligible_penalized","hard_exclusions":["join_invalid","snapshot_invalid","worker_observation_invalid","present_false","present_null_without_isolation_proof","enabled_false_or_unknown","fresh_health_unavailable","cooling_active","fresh_quota_exhausted","slot_identity_mismatch"],"headroom_rounding":"decimal_round_half_even_basis_points","isolation_null":"eligible_only_with_scoped_degradation_and_worker_proof","quota_evidence_highest":["exact","provider_reported"],"quota_horizons":["five_hour","weekly"],"quota_metric":"provider_allocation","rank_tuple":["cooling_rank","health_rank","quota_coverage_rank","quota_evidence_rank","headroom_unknown_rank","negative_bottleneck_basis_points","worker_id","quota_class"],"schema":"capacity-placement.v1","stale_evidence":"unknown","unknown_quota":"eligible_without_positive_headroom"}
```

`capacity_policy_digest = sha256(canonical(policy_object))` and the frozen v1 value is
`a50ac8345187354b778179d2744e0ba24c40b843c38241a7eacb90fe82ed3683`. No LLM interprets
provider evidence, chooses a worker or waives independence.

---

## 8. Closed `JOB_CLAIMED.capacity_evidence`

The existing v4 placement snapshot remains exactly six keys and byte-for-byte unchanged. Capacity
evidence is one nested object in the existing `JOB_CLAIMED` payload.

Closed schema `mastermind.executive_capacity_evidence/v1` has exactly:

~~~text
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
selected_worker_observation
candidate_decisions
acquisition_receipt
~~~

Semantics:

- `producer_identity` is the exact closed CF1 `producer` object;
- `producer_audit` is the exact closed CF1 `audit` object;
- `selected_slot` is the complete canonical secret-free CF1 slot used for the decision;
- `selected_slot_digest = sha256(canonical(selected_slot))`;
- `selected_degraded_rows` contains every producer-global and selected-slot scoped row needed to
  interpret that slot;
- `selected_worker_observation` is the complete canonical closed worker observation used for
  execution-realm eligibility;
- `candidate_decisions` is deterministically ordered and contains only candidates already lawful
  under Executive/Router hard filters;
- `acquisition_receipt` is the exact closed object below.

Each candidate decision has exactly:

~~~text
host_ref
capacity_capability_id
worker_id
quota_class
slot_evidence
slot_digest
degraded_rows
worker_observation
disposition
reason_codes
rank_vector
~~~

`slot_evidence` is the complete canonical CF1 slot. `slot_digest = sha256(canonical(slot_evidence))`.
`degraded_rows` includes all producer-global and candidate-scoped rows needed to interpret it.
`worker_observation` is the complete canonical secret-free
`mastermind.executive_worker_capacity_observation/v1` object.

Persisting full provider and realm evidence for all one-to-three capacity-evaluated candidates makes
the historical choice independently explainable without a mutable provider/worker lookup.
The top-level selected slot, digest, degradation and worker observation must be byte-equal to the
corresponding fields in the one selected row.

`disposition` is `selected | eligible | excluded`. Excluded here means capacity-excluded after all
other hard filters; unauthorized or otherwise ineligible workers never enter this list.

`rank_vector` is null for a hard-excluded candidate or an exact object with these eight keys:
`cooling_rank`, `health_rank`, `quota_coverage_rank`, `quota_evidence_rank`,
`headroom_unknown_rank`, `negative_bottleneck_basis_points`, `worker_id` and `quota_class`.
Its values must reproduce Section 7.1 exactly.

Closed candidate reason vocabulary:

~~~text
CAPACITY_JOIN_MISSING
CAPACITY_JOIN_AMBIGUOUS
CAPACITY_JOIN_DRIFT
CAPACITY_SLOT_IDENTITY_MISMATCH
CAPACITY_WORKER_REALM_READY
CAPACITY_WORKER_REALM_METADATA_INVALID
CAPACITY_WORKER_CREDENTIAL_ABSENT
CAPACITY_WORKER_CREDENTIAL_METADATA_INVALID
CAPACITY_WORKER_PROVIDER_BINARY_UNATTESTED
CAPACITY_WORKER_BROKER_GENERATION_UNREADY
CAPACITY_PRESENT_FALSE
CAPACITY_PRESENT_UNKNOWN
CAPACITY_PRESENT_ISOLATION_NULL_ACCEPTED
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
CAPACITY_QUOTA_EXACT
CAPACITY_QUOTA_REPORTED
CAPACITY_QUOTA_ESTIMATED
CAPACITY_QUOTA_MIXED
CAPACITY_QUOTA_STALE
CAPACITY_QUOTA_EXHAUSTED
CAPACITY_SELECTED
CAPACITY_ELIGIBLE_LOWER_RANK
CAPACITY_STABLE_TIE_BREAK
~~~

Reason lists are sorted, unique and contain only applicable deterministic facts. An accepted null
presence must carry both `CAPACITY_PRESENT_UNKNOWN` and
`CAPACITY_PRESENT_ISOLATION_NULL_ACCEPTED`; it never receives a synthetic true reason.

Closed `acquisition_receipt` schema
`mastermind.executive_capacity_acquisition_receipt/v1` has exactly:

~~~json
{
  "schema_version": "mastermind.executive_capacity_acquisition_receipt/v1",
  "preflight_candidate_digest": "<64-lower-hex>",
  "capacity_snapshot_hash": "<64-lower-hex>",
  "capacity_snapshot_generated_at": "2026-08-26T01:45:00Z",
  "p0_acceptance_digest": "<64-lower-hex>",
  "source_config_digest": "<64-lower-hex>",
  "acquisition_config_digest": "<64-lower-hex>",
  "macro_release_commit": "<40-lower-hex>",
  "producer_material_source_digest": "<64-lower-hex>",
  "worker_observation_receipts": [
    {
      "capacity_capability_id": "codex_account_2",
      "observation_digest": "<64-lower-hex>"
    },
    {
      "capacity_capability_id": "codex_account_3",
      "observation_digest": "<64-lower-hex>"
    }
  ],
  "completed_at": "2026-08-26T01:45:04Z"
}
~~~

The observation receipt list is sorted by `capacity_capability_id` and contains exactly the
one-to-three unchanged preflight candidates. It has no duplicate or unexpected identity.

Required identity equalities before mutation:

~~~text
receipt.capacity_snapshot_hash == capacity_evidence.capacity_snapshot_hash
receipt.capacity_snapshot_generated_at == capacity_evidence.capacity_snapshot_generated_at
receipt.p0_acceptance_digest == sha256(canonical(accepted_p0_record))
receipt.source_config_digest == accepted_p0_record.source_config_digest
receipt.source_config_digest == sha256(canonical(installed_source_config))
receipt.producer_material_source_digest == producer_identity.material_source_digest
receipt.macro_release_commit == producer_audit.repository_commit
accepted_p0_record.macro_release_commit == producer_audit.repository_commit
accepted_p0_record.producer_material_source_digest == producer_identity.material_source_digest
producer_audit.material_sources_match_commit == true
each receipt observation digest == its candidate worker_observation.observation_digest
each worker observation host/capability == the immutable candidate join
each worker observation source_config_digest == its join.worker_source_config_digest
runtime_acquisition_config.macro_release_commit == receipt.macro_release_commit
runtime_acquisition_config.producer_material_source_digest == receipt.producer_material_source_digest
runtime_acquisition_config.inventory_config_digest == installed_source_config.inventory_config_digest
runtime_acquisition_config.allowed_environment_names_digest == sha256(canonical(installed_source_config.allowed_environment_names))
runtime_acquisition_config.telemetry_config_digest == installed_source_config.telemetry_config_digest
receipt.acquisition_config_digest == sha256(canonical(runtime_acquisition_config))
~~~

`runtime_acquisition_config` is the closed
`mastermind.executive_capacity_acquisition_config/v1` object with exactly `schema_version`,
`p0_acceptance_digest`, `source_config_digest`, `macro_release_commit`,
`producer_material_source_digest`, `inventory_config_digest`,
`allowed_environment_names_digest`, `telemetry_config_digest` and `broker_bindings`.
`broker_bindings` is sorted by `(host_ref, capacity_capability_id)`, contains exactly the unchanged
preflight candidates and each row has exactly `host_ref`, `capacity_capability_id` and
`worker_source_config_digest`, byte-equal to the immutable capacity join.
`acquisition_config_digest = sha256(canonical(runtime_acquisition_config))` with no excluded field.

This accepted root-owned configuration identity thereby covers the exact P0 producer
operation/release, fixed three-home Macro inventory, allowed environment names, telemetry surface
identities and every contacted broker's immutable capability/config binding. A runtime observation
whose source digest differs from its binding returns `CAPACITY_OBSERVE_CONFIG_DRIFT` and refuses the
whole invocation. Receipts reveal no path,
principal/account name or secret. `completed_at` is UTC, not before snapshot generation or any
observation time, and not after the earliest applicable expiration plus the 2-second tolerance.

Bounds:

- at most 3 candidate decisions;
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
same lookup as the first operation inside the eventual write transaction.

**Outer replay hit:** validate the historical event target/evidence and return the persisted
Attempt/outcome with zero CF1 acquisition, broker observation, ranking or mutation. Never compare
historical evidence to current capacity state.

**Inner transactional race hit:** the losing caller may already have completed read-only CF1 and
broker acquisition outside the lock. It discards those fresh observations, validates and returns
the winner's persisted Attempt/evidence, and performs zero ranking, mutation, second Attempt/Event
or provider turn. A later replay invocation performs zero second acquisition.

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

### CF2-P0 / host census

Require read-only proof that:

- either an existing Macro producer or an exact root-owned grounded Git checkout can emit strict
  accepted CF1 v1;
- the installed checkout retains Git metadata and every accepted material source;
- the shared telemetry surface is narrow, secret-free, correction-current and readable without
  provider-home access;
- root-owned `CODEX_ACCOUNT_HOMES` contains exactly three canonical paths in accepted Macro order;
- `_mastermind_exec` cannot traverse/read any Personal Pro home and is not in any Pro group;
- the real central snapshot emits `present=null`, not false, for all three isolated slots plus every
  exact required scoped degradation;
- source path, owner/mode/ACL/symlink and no-write receipts are sanitized and complete.

Adding control to a Pro group, weakening a home mode, omitting/reordering a configured home, using a
source-only bundle or exposing credential-bearing telemetry must fail the gate.

### CF2-I-A / grounded central acquisition

Require tests that:

- fixed absolute argv uses no shell/PATH/user checkout and inherits no sensitive environment;
- stdout/stderr/time/process-group bounds are enforced and owned processes are reaped;
- wrong/ungrounded release, material mismatch, invalid hash/schema/UTF-8/trailing bytes, stale/future
  snapshot, oversize output and nonzero exit refuse;
- `producer.material_source_digest` and `audit.repository_commit` bind exactly to receipt fields and
  `material_sources_match_commit=true`;
- all twelve slots and every honest null/degradation are preserved byte-for-byte;
- no credential bytes/provider-home contents are opened, no provider/network call occurs and no
  file/database/cache is written.

### CF2-I-B / broker realm observation

Require tests that:

- the request is the one exact fixed object and rejects every extra/dynamic field;
- each broker reports only its immutable `capacity_capability_id` and own fixed realm;
- wrong peer UID, wrong broker UID/GID, supplementary-group drift, missing autonomy, held Attempt,
  active provider/process, config drift or another capability identity refuses;
- response closed keys, canonical digest, 4-KiB bound, five-second timeout, 15-second TTL and
  two-second skew are discriminated at boundaries;
- canonical worker source-config golden vectors bind each observation to the exact immutable join
  expected digest and reject every field/config/generation drift;
- swapping or changing one broker source-config digest and recomputing a valid observation self-hash
  still returns `CAPACITY_OBSERVE_CONFIG_DRIFT` with no ranking, quota hold, Attempt, Event,
  reacquisition loop or failover;
- credential absent/wrong owner/type/mode, binary drift or broker generation drift refuses;
- no path, UID, username, account label, browser identity, secret-ref, auth bytes or raw exception
  crosses the socket;
- three broker services share one Executive Runtime/database and use distinct sockets/principals/homes;
- a busy non-candidate broker is not contacted and cannot block an available candidate;
- one failed/ambiguous candidate plus one valid candidate refuses the whole V1 invocation before
  ranking, persists no `JOB_CLAIMED`/candidate/receipt evidence and performs no cross-worker retry.

### CF2-I-C / claim integration

Require tests that:

- an outer replay hit invokes zero CF1/broker acquisition;
- an inner same-command race may discard already-acquired reads but creates zero second
  Attempt/Event/provider turn and returns the winner;
- a capacity source blocked longer than SQLite's five-second busy timeout does not hold the
  lifecycle writer lock or delay an unrelated Job/Event/Attempt writer;
- every existing hard filter runs before capacity acquisition/ranking;
- missing/duplicate/drifting join refuses; any missing/duplicate/invalid/stale/ambiguous worker
  observation refuses the whole invocation before ranking or mutation;
- CF1 `present=false` always refuses;
- CF1 `present=null` is eligible only for the exact three isolation slots with scoped degradation,
  attested config and fully valid matching worker evidence, and remains null in persisted evidence;
- worker evidence never overrides disabled state, active cooling, fresh exhaustion or health
  unavailable;
- unknown/stale cooling, health and quota receive the exact penalties and never become free;
- fresh exact/provider-reported quota share the highest evidence class; estimated is lower;
- ranking/reasons are stable under input ordering;
- golden vectors independently recompute snapshot, worker observation, preflight, policy, slot,
  configuration and acquisition-receipt digests plus the multi-horizon rank;
- every evaluated candidate persists full canonical slot/degradation/worker/rank evidence;
- commit exactly at the freshness/skew boundary passes and one tick beyond refuses;
- one transaction commits quota hold, Attempt, Job transition, unchanged placement and exact
  capacity evidence together—or none;
- preflight/transaction candidate or policy drift returns `CAPACITY_PREFLIGHT_CONFLICT`, performs no
  mutation and never reacquires while the writer lock is held;
- exact replay returns history without acquisition; changed semantic target conflicts;
- later provider/realm correction leaves historical evidence unchanged;
- exact pre-CF2 v4 placement canonical bytes/digest and normalized SQLite schema digest do not
  change.

---

## 12. Real production proof owed by CF2-I

The final CF2-I canary must use exact accepted installed releases and prove:

1. all three Personal Pro realms have separate sanitized readiness and inference-canary receipts;
2. all three worker brokers run under the correct distinct principals with one canonical Executive
   Runtime;
3. three immutable worker/quota joins bind exact
   `(host_ref, capacity_capability_id)` identities without equating account labels;
4. one complete grounded fresh unchanged `mastermind.provider_capacity.v1` snapshot is emitted by
   the CF2-P0-accepted central Macro path while control cannot traverse any Pro home;
5. all three Codex slots preserve exact null presence/degradation from the isolation boundary;
6. fresh candidate-only worker observations establish current realm eligibility without reading
   credential bytes or blocking a parallel seat;
7. one harmless Chairman-authorized Executive Job chooses deterministically among the three
   already-eligible seats and persists full provider/realm decision evidence atomically;
8. the selected worker reaches a terminal result;
9. same-command replay performs zero second acquisition/provider turn/Attempt;
10. a later provider or realm observation change cannot alter the historical claim;
11. disarm/rearm/restart recovery preserves one lifecycle and no hidden provider process;
12. secret/PII scans and before/after write receipts remain clean.

The proof packet names exact Mastermind/Macro releases, sanitized principal/broker identities,
snapshot/policy/slot/observation/config/Event digests, Job/Attempt/command identities, terminal
result and every degraded/null field. It never publishes auth material, provider-home paths or
account identity.

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
3. the current control-principal acquisition falsifier and accepted CF1 isolation-null behavior are
   preserved honestly;
4. the central unchanged CF1 plus worker-local realm-evidence join preserves mode-0700 isolation,
   one Macro producer and one existing worker-broker family;
5. exact P0, acquisition, observation, join, evidence, bounds, privacy, time, null, correction and replay
   laws are closed;
6. existing `JOB_CLAIMED` is sufficient and placement/schema remain unchanged;
7. implementation is split into bounded P0, grounded central acquisition, broker observation and
   claim carriers with exact proof gates;
8. Cursor/Grok research remains parallel while executable adapters remain RF1/HF1-gated.

Merge makes this source law `SPEC_ONLY`. It does not install services, authenticate accounts,
enable routing, place work, spawn sessions, grant MCP/plugins, deploy to a VPS or arm autonomy.

After PASS/merge, the exact next action is CF2-P0: run the read-only host census and return one
closed safe-source outcome. Only an accepted source path releases CF2-I-A. Personal Pro readiness
may continue on its separate host carrier, and Cursor/Grok source research may continue on disjoint
records-only carriers.

Stop and return to Sol if no grounded Macro path can read only secret-free telemetry, the existing
broker cannot carry the bounded observation, the closed event payload cannot fit full evidence, or
any proposed repair requires shared/root credential observation, a new service family, another
database/event/lifecycle, schema v5 or changed placement identity.
