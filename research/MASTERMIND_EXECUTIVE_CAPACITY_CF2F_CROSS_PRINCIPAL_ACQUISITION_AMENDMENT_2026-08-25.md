# CF2-F Cross-Principal Acquisition Amendment

**Date:** 2026-08-25  
**Owner:** Sol, AI CEO  
**Amends:** `research/MASTERMIND_EXECUTIVE_CAPACITY_CF2F_CLAIM_EVIDENCE_AND_ACQUISITION_FREEZE_2026-08-25.md`  
**Protected Mastermind basis:** `eff2033c639cb25f8b4a2a4e5f90e1a4a6002138`  
**Status:** SOURCE-LAW CORRECTION / RECORDS ONLY

---

## 0. Why this amendment exists

After CF1 closeout, a concurrent duplicate records carrier exposed one material fact that the first CF2-F draft had not fully reconciled:

- the three Personal-Pro Codex worker homes are intentionally owned by three distinct worker principals and mode `0700`;
- `_mastermind_exec` is **not** a member of those three worker groups;
- the accepted three-realm implementation explicitly treats adding those groups to the control principal as a safety failure.

Therefore the first CF2-F draft's simple wording — “the control service runs the Macro capacity CLI” — is **not sufficient as the authority model** if it is interpreted to mean the control principal may inspect every private provider home.

This amendment preserves the accepted isolation and supersedes only that assumption. The claim-evidence schema, schema-v4 no-widening law, deterministic capacity policy and replay law remain controlling unless explicitly changed below.

---

## 1. Binding correction

> **Executive control may never gain direct read/traverse authority over the three isolated Personal-Pro provider homes merely to obtain capacity evidence.**

CF2-I must use a two-owner observation join:

```text
Macro Provider Control
  shared secret-free capacity evidence
  (quota / cooling / health / historical outcome / source identity)
              |
              v
       provider_capacity.v1
              |
              +----------------------+ 
                                     |
private worker broker               |
  exact worker UID                  |
  own provider home only            |
  fixed capacity-observe operation  |
              |                      |
              +----------+-----------+
                         v
              Executive hard eligibility
              + capacity ranking
                         |
                         v
                one atomic JOB_CLAIMED
```

Neither side takes ownership from the other:

- Macro remains provider-capacity truth owner.
- Executive/worker-broker evidence remains execution-realm/readiness truth.
- The join is claim-time evidence only; it is not a new provider store.

---

## 2. Worker-local private-realm observation

The existing `ExecutiveWorkerBroker` is the accepted principal boundary to reuse:

- it runs under the dedicated worker UID;
- its Unix socket accepts only the configured Executive control UID via kernel peer credentials;
- it has a closed operation allowlist and no generic shell endpoint;
- it already supports fixed, bounded, non-provider operations such as `autonomy-canary`;
- it refuses work when its dedicated-UID / autonomy / process-state invariants are not satisfied.

CF2-I may add exactly one fixed read-only operation:

```text
capacity-observe
```

It is **not** a command runner. The request carries no path, argv, environment variable name, account identifier, provider-home override, script name, prompt or model-authored field.

### 2.1 Operation admission

`capacity-observe` is accepted only when:

- the peer UID is the exact configured Executive control UID;
- the broker is the exact configured worker UID/GID and approved supplementary-group vector;
- current autonomy authority is valid when the production broker is armed;
- no provider turn / validation / OHF operation is active or starting;
- the worker config identifies exactly one reviewed provider realm and one fixed capacity account label;
- the observation implementation is part of the installed exact-SHA Mastermind release.

The operation performs no provider call and creates no provider session.

### 2.2 Fixed three-seat mapping

For the first V1 Codex proof, the reviewed host catalog binds:

```text
codex-pro-01 -> codex_account
codex-pro-02 -> codex_account_2
codex-pro-03 -> codex_account_3
```

The mapping belongs in trusted host/provider-slot configuration or its existing reviewed catalog, never in a Job/prompt/request. A caller cannot ask broker 01 to report broker 02's account.

### 2.3 Worker observation schema

Closed conceptual response:

```json
{
  "schema_version": "mastermind.executive_worker_capacity_observation/v1",
  "worker_id": "codex-pro-01",
  "provider": "codex",
  "account_label": "codex_account",
  "observed_at": "<UTC>",
  "worker_uid": 454,
  "provider_home_metadata_valid": true,
  "credential_present": true,
  "credential_metadata_valid": true,
  "codex_binary_attested": true,
  "broker_generation_ready": true,
  "observation_digest": "<64hex>"
}
```

The exact implementation may use the already-reviewed credential **metadata** identity/lstat helpers. It must never open, parse, copy, hash or return credential bytes.

The observation contains no provider-home path, auth path, token/cookie, email/account PII, provider session ID, raw exception or arbitrary filesystem metadata.

`credential_present=true` means the fixed auth object exists with the reviewed file type/ownership/mode boundary. It is not a claim that the provider would accept a new call; provider-readiness/G7 admission remains a separate gate.

`broker_generation_ready=true` means only that the exact broker/principal is in a state where this fixed observation was lawfully issued. It is not a Job execution receipt.

### 2.4 No readiness duplication

CF2 does **not** create a second readiness receipt or reimplement G7/provider-readiness promotion.

Production capacity placement requires the existing host/provider-readiness/arming gates to have admitted these worker realms. `capacity-observe` adds only fresh private-realm evidence required because Provider Control intentionally cannot traverse the isolated home.

---

## 3. Macro Provider Control acquisition remains separate

The accepted CF1 snapshot continues to supply the shared secret-free capacity evidence.

However, a production implementation must not execute CF1 from an arbitrary/user-writable Macro checkout. The CF1 producer identity already distinguishes semantic material-source bytes from repository audit provenance; CF2 must preserve that property at runtime.

### 3.1 Preflight gate — `CF2-P0`

Before CF2-I writes production acquisition code, run one **read-only host census** and freeze the existing provider-control source path:

1. identify the actual Macro Provider Control code root used on the Executive host;
2. identify the actual `METABOLISM_STATE_ROOT` / key-ledger and usage-ledger owner/path used for current Codex quota/cooling telemetry;
3. inspect owner/group/mode/ACL/symlink boundaries without reading credential values;
4. determine whether an existing Macro-owned local process/API can already emit the accepted CF1 projection;
5. if no such process exists, determine whether the exact accepted CF1 producer can be installed as a root-owned immutable dependency and read **only** the already-secret-free Provider Control telemetry without granting `_mastermind_exec` access to provider homes or a broader sensitive state tree;
6. record the exact executable/process principal and source/state paths used by the chosen acquisition implementation.

This census is read-only. It creates no service, changes no mode/group, copies no credential, and does not arm production.

### 3.2 Allowed acquisition outcomes

CF2-P0 must end in exactly one of:

```text
EXISTING_MACRO_PROJECTION_PATH_ACCEPTED
IMMUTABLE_CF1_BUNDLE_PATH_ACCEPTED
NO_SAFE_CF1_ACQUISITION_PATH
```

#### Existing Macro projection path

Prefer an already-operating Macro-owned local producer/process if it can emit strict `mastermind.provider_capacity.v1` from canonical Provider Control state with bounded authenticated/local transport and no new lifecycle authority.

#### Immutable CF1 bundle path

If no existing process owns the projection, CF2-I may provision the accepted Macro CF1 producer as an **immutable release dependency**, not a floating Python import:

- exact reviewed Macro commit/material-source identity;
- root-owned, non-group/other-writable installed bytes;
- fixed executable and source root from root-owned config;
- no caller-supplied path/argv;
- read access only to the exact secret-free Provider Control telemetry files required by CF1;
- no read/traverse authority to any Personal-Pro provider home;
- no copied/mirrored mutable quota database inside Executive OS;
- no long-lived capacity daemon/cache/scheduler.

If the existing telemetry root is broader or contains sensitive data such that safe narrow read access cannot be established without creating a new copy/cache or weakening unrelated permissions, this outcome **fails** and returns to Sol.

#### No safe path

`NO_SAFE_CF1_ACQUISITION_PATH` blocks CF2-I. It does not authorize widening Pro-home groups, running a root daemon by convenience, moving Provider Control truth into Executive SQLite, or reimplementing quota state from scratch.

---

## 4. How the two evidence planes join

For each otherwise Executive-eligible Codex candidate, CF2-I joins:

1. exactly one CF1 slot by `(provider, account_label)`; and
2. exactly one current worker-broker observation by `(worker_id, provider, account_label)`.

### 4.1 Presence rule under isolation

The original CF2-F hard rule `present != true => refuse` is corrected for the isolated Pro realm.

For Codex Personal-Pro worker slots only:

- `CF1 present == true` and worker observation valid/present -> coherent;
- `CF1 present == false` -> **refuse**, even if worker observation says present; this is contradictory observed evidence requiring reconciliation;
- `CF1 present == null` + worker observation valid/present -> the worker's private-realm observation resolves **Executive execution eligibility only**; the CF1 field remains historically `null` and is not rewritten to true;
- `CF1 present == null` + missing/invalid worker observation -> refuse;
- worker observation false/invalid -> refuse regardless of CF1 presence.

This does not let Executive rewrite Macro Provider Control truth. It lets the correct private principal establish the execution fact that Macro cannot lawfully observe across the `0700` boundary.

### 4.2 Enablement / cooling / quota / health

- provider enablement remains CF1/Provider Control evidence and must be observed true for automatic placement;
- `cooling.active=true` or `null` remains a hard capacity refusal;
- fresh reported/exact exhaustion remains a refusal;
- health unavailable remains a refusal;
- stale/unknown quota remains unknown and provides no positive headroom advantage;
- worker observation cannot override CF1 cooling, quota, health or provider enablement.

---

## 5. Claim evidence correction

`mastermind.executive_capacity_evidence/v1` must preserve both evidence owners.

Each candidate row should carry a compact closed `decision_evidence` sufficient to reconstruct every capacity decision without later mutable lookup:

```json
{
  "provider_slot": {
    "slot_digest": "<64hex>",
    "present": null,
    "enabled": true,
    "health_state": "unknown",
    "health_freshness": "unknown",
    "cooling_active": false,
    "cooling_evidence": "exact",
    "quota_summary_digest": "<64hex>",
    "quota_coverage": "none",
    "quota_evidence_class": "none",
    "bottleneck_headroom_percent": null
  },
  "worker_realm": {
    "observation_digest": "<64hex>",
    "credential_present": true,
    "credential_metadata_valid": true,
    "codex_binary_attested": true,
    "broker_generation_ready": true
  }
}
```

This compact evidence is deterministic and derived from the full strict source slot + worker observation. The selected row may additionally carry the full canonical secret-free CF1 slot as already frozen by the parent source law.

Refused candidates therefore remain historically auditable without persisting all provider snapshots or reading current state later.

The total `capacity_evidence` 64-KiB ceiling remains. No truncation is allowed.

---

## 6. Replay / race law with worker observations

For a new command-bound claim:

1. read existing `command_id`; persisted claim -> return it, no CF1 acquisition and no broker observation;
2. acquire one fresh CF1 projection through the accepted CF2-P0 path;
3. query `capacity-observe` only for otherwise Executive-eligible worker candidates;
4. enter the existing claim transaction;
5. re-check `command_id` and current Executive candidate state;
6. ensure CF1 snapshot and worker observations remain within their accepted freshness budgets;
7. rank and append `JOB_CLAIMED.capacity_evidence` atomically.

If another writer won the same command, discard newly acquired observations and return persisted evidence. Never re-contact a provider merely because the claim raced.

Worker-broker observation is read-only and may be repeated **before any claim commits** if it expires. After claim commit, historical evidence is immutable.

---

## 7. New implementation falsifiers

CF2-I must additionally prove:

- `_mastermind_exec` cannot traverse/read any Pro provider home;
- adding control to any Pro primary group causes acceptance failure;
- `capacity-observe` from a wrong peer UID refuses;
- payload fields beyond the closed empty/fixed request refuse;
- one broker cannot select/report another account label or provider-home path;
- credential bytes cannot reach the broker response even under hostile filename/content fixtures;
- a worker observation cannot override CF1 false presence, cooling, exhaustion, health unavailable or disabled state;
- CF1 null presence + valid private worker observation remains explicitly null in persisted provider evidence while permitting Executive eligibility;
- missing/expired broker observation prevents placement;
- command replay performs zero CF1 acquisition and zero worker-broker observations;
- the chosen CF2-P0 source path uses exact immutable code identity and no user-writable producer bytes;
- the chosen shared telemetry read surface contains no provider credential files/values;
- there is still no new capacity cache/store/daemon/scheduler or schema-v5 migration.

---

## 8. Sequencing correction

The next implementation sequence is now:

```text
CF2-F source-law acceptance
    -> CF2-P0 read-only host acquisition census
        -> safe acquisition path accepted
            -> CF2-I implementation
            -> real 3-Codex multi-account canary
```

CF2-P0 is a probe/gate, not a long-form new program. It should be executed immediately and returned to Sol as one evidence packet.

Browser/DevServer F0/B1, Personal-Pro ingress, ASD and other disjoint Autonomy V1 lanes continue in parallel.

---

## 9. Stop condition

This amendment is complete when independent review agrees that it preserves the accepted Pro-realm isolation while giving CF2-I one lawful claim-time evidence join and one bounded preflight for the remaining host-specific source path.

Do not merge CF2-F if review finds that `capacity-observe` would require generic commands, credential-byte access, cross-worker home access or a second readiness/control plane.
