# Mastermind-X Executive Capacity Fabric CF2-F

**Date:** 2026-08-25  
**Owner:** Sol, AI CEO  
**Status:** SOL SOURCE-LAW FREEZE / RECORDS ONLY  
**Organizational parent:** `WS:EXECUTIVE-CAPACITY-FABRIC`  
**Wave identity:** `WS:EXECUTIVE-CAPACITY-FABRIC::CF2-F — Freeze Executive claim-time capacity evidence and acquisition`  
**Protected Mastermind basis:** `eff2033c639cb25f8b4a2a4e5f90e1a4a6002138`  
**Protected Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1, loaded atomically from that exact commit.  
**Accepted CF1 implementation:** Macro PR #6297, exact reviewed head `fc12904f59a5758817aa2c76ffaa40bb1ebcbf8e`, merge `dcdd939c45b23abce5ba04f95e330ac914a3904b`.  
**Current Macro truth inspected:** current `main` includes the accepted CF1 producer; no post-CF1 modification of `engine/provider_capacity.py` was found before this freeze.  
**Completion law:** this records-only wave is complete when this source law is independently reviewed and merged. It does **not** make Executive placement capacity-aware and does not prove a production worker claim.

---

## 0. Observable mission and CEO ruling

Freeze the smallest lawful seam by which the existing Executive OS can acquire one fresh, strict, secret-free `mastermind.provider_capacity.v1` snapshot and atomically record the exact capacity decision inside the existing `JOB_CLAIMED` receipt **without changing schema v4 placement identity, creating another event/store, importing floating Macro internals, or allowing callers/models to author capacity evidence**.

The ruling is:

> **CF2-F uses one bounded read-only local acquisition subprocess and one closed nested `capacity_evidence` object in the already-canonical `JOB_CLAIMED` payload.**

No daemon, provider database, capacity cache, second allocation ledger, schema v5, widened placement snapshot or provider-specific scheduler is authorized.

CF2-I is the separate implementation wave. It may begin only after this freeze is accepted.

---

## 1. Why this matters

CF1 made provider capacity truthful and machine-readable, but Executive OS still ignores it when choosing among eligible worker accounts. The current schema-v4 runtime already owns the correct atomic claim transaction and already records routing evidence in `JOB_CLAIMED`. The remaining gap is therefore not a new scheduler; it is a deterministic join and evidence seam:

```text
Macro Provider Control truth
    -> mastermind.provider_capacity.v1
    -> strict bounded acquisition
    -> existing Executive hard eligibility
    -> deterministic capacity rank/exclusion
    -> same existing atomic claim
       + unchanged placement_snapshot_json/digest
       + JOB_CLAIMED.capacity_evidence
```

This unlocks the Chairman job: give the company work once and let the system use available subscription capacity without manually choosing among the three Codex accounts or interpreting quota dashboards.

---

## 2. Authority and no-rebuild precedence

Descending authority for CF2-F:

1. Current protected Sol Skillpack at the exact basis above.
2. `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md` — Autonomy V1 integration/finish-line law.
3. `research/EXECUTIVE_OS_PHASE1FC_CEO_POLICY_AND_IMPLEMENTATION_COMMISSION_2026-08-20.md` and landed schema-v4 runtime — Executive lifecycle/claim/placement authority.
4. `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_PLACEMENT_AMENDMENT_2026-08-22.md` — capacity evidence must live alongside, never inside, the closed placement object.
5. `research/MASTERMIND_EXECUTIVE_CAPACITY_FABRIC_F0_ARCHITECTURE_2026-08-22.md` and its semantic/null amendments — provider-capacity ownership and contract law.
6. Macro `mastermind.provider_capacity.v1` producer accepted in PR #6297.

Canonical ownership remains:

- Executive OS: Job / Attempt / Worker / Event lifecycle and atomic claim.
- Macro Shared AI Provider Control: provider/account presence, enablement, health, cooling, quota evidence and correction.
- Model Router: task/model suitability; Capacity Fabric may not redefine it.
- Agent OS: durable organizational workstream state.
- GitHub: implementation/evidence truth.

A newer material source-law collision returns to Sol. High-churn unrelated repo movement does not automatically invalidate this freeze.

---

## 3. Verified landed implementation constraints

### 3.1 Schema v4 placement is closed

`control_plane/executive_orchestration_principal.py` freezes `mastermind.executive_placement_snapshot/v1` as exactly:

```text
schema_version
worker_id
quota_class
provider
account_label
observed_at_ms
```

The JSON/digest pair is persisted on the Attempt and protected by schema-v4 pair/immutability triggers. CF2-F must not add capacity fields to it.

### 3.2 `JOB_CLAIMED` is already the correct atomic evidence owner

Current `AttemptRegistry.claim_job` selects a current AVAILABLE worker/quota row, inserts the Attempt, updates the Job and appends `JOB_CLAIMED` inside one transaction. Its payload already records routing policy/profile/capability identity and, for orchestration claims, effective-grant and placement digests.

The capacity extension therefore belongs in this same payload.

### 3.3 Replay already has a canonical command identity

Command-bound COO dispatch looks up an existing Event by `command_id` and returns/reconciles the already-bound Attempt. CF2-I must preserve and strengthen this ordering: a replayed command never reacquires provider capacity and never reruns selection.

### 3.4 CF1 producer is deliberately read-only

Macro `scripts/build_provider_capacity.py` emits strict JSON to stdout, makes no provider call, persists no capacity state, and returns bounded opaque refusal text on stderr. The underlying contract independently distinguishes semantic `snapshot_hash`/`material_source_digest` from whole-repository audit commit identity.

---

## 4. Acquisition seam freeze — `MacroCapacityAcquirer/v1`

CF2-I must implement one trusted local acquisition helper inside Mastermind. It is a read-only resource adapter, not a daemon and not lifecycle authority.

### 4.1 Fixed operation

The helper may invoke exactly one reviewed producer operation conceptually equivalent to:

```text
<absolute reviewed Python executable>
<absolute reviewed Macro root>/scripts/build_provider_capacity.py
```

with **no caller/model-supplied arguments** and without `--pretty`.

The relative producer script path is frozen. The executable path and Macro checkout root are host/operator configuration owned by the installed Executive release, not fields in a Job, prompt, Slack message or model-produced plan.

The helper must:

- resolve configured paths as canonical absolute paths;
- refuse symlink/path-escape surprises at the trusted boundary;
- use an explicit executable path rather than PATH lookup;
- set stdin to null;
- set `PYTHONDONTWRITEBYTECODE=1` and avoid source-tree writes;
- use a minimal environment sufficient for the reviewed Macro runtime;
- capture stdout/stderr separately;
- impose a hard wall-clock timeout;
- kill/reap only the acquisition process it owns on timeout;
- never forward raw stderr/private exception text into Executive Events, model-visible results or Slack.

### 4.2 Bounds

V1 source-law bounds:

```text
acquisition timeout:        10 seconds
maximum stdout:             256 KiB
maximum stderr retained:    4 KiB internally, never persisted verbatim
maximum snapshot age at claim commit: 30 seconds
future-clock tolerance:     2 seconds
```

If the producer needs larger output or longer execution later, that is a source-law change, not a silent implementation increase.

### 4.3 Strict acceptance

Acquisition succeeds only if all are true:

- process exits `0` within the timeout;
- stdout is one UTF-8 JSON document within the byte ceiling;
- exact top-level schema is `mastermind.provider_capacity.v1`;
- producer repository/program/implementation identity is exactly the accepted contract family;
- `producer.implementation_version >= 1` and all closed v1 fields validate;
- canonical `snapshot_hash` recomputes exactly;
- `audit.material_sources_match_commit == true`;
- the snapshot `generated_at` is not beyond the future tolerance and is no older than 30 seconds at the eventual claim commit;
- slots/degraded rows are canonical, bounded and secret-free under the accepted v1 validator.

A failure produces one bounded internal refusal code and **no claim mutation**.

### 4.4 Refusal vocabulary

Closed acquisition refusal codes for V1:

```text
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
```

Raw subprocess stderr, Python exception text, filesystem paths and provider responses are not receipt fields.

### 4.5 No cache/store in V1

Every **new logical claim command** acquires a fresh snapshot. There is no capacity cache table, file, daemon, cursor or refresh scheduler in Executive OS.

A command replay is the exception: persisted `JOB_CLAIMED` evidence is authoritative and no acquisition is performed.

---

## 5. V1 slot-to-Executive binding law

CF1 currently publishes each supported slot with:

```text
provider
account_label == capability_id
host_ref == local-unbound
```

Current Executive Worker identity separately carries canonical `provider` and `account_label`.

For the first single-host CF2-I canary, the binding is therefore deliberately minimal:

```text
capacity slot.provider      == Executive Worker.provider
capacity slot.account_label == Executive Worker.account_label
```

Rules:

- exactly one slot must match an otherwise Executive-eligible worker;
- zero matches => capacity candidate refusal;
- more than one match => ambiguity refusal;
- the matched `capability_id` and `host_ref` are recorded as evidence but do not widen placement identity;
- `capability_id` never becomes a second Worker ID;
- `host_ref=local-unbound` is accepted only for the single-host V1 proof and grants no remote-execution meaning;
- a future producer that can yield more than one host-bound slot for the same provider/account identity requires the later reviewed host/binding law; V1 refuses ambiguity rather than guessing.

This keeps CF2-I independent of MH1. It does not claim multi-host placement.

---

## 6. Capacity may rank only after existing hard eligibility

Capacity selection never decides whether a model/provider is suitable for the work.

CF2-I must first preserve every existing Executive hard filter, including at minimum:

- Job state / availability / attempt limit;
- parent-child/review/repair/orchestration law;
- authority/effective-grant law;
- quarantine and review independence;
- Worker/quota `AVAILABLE` state and no held Attempt;
- identity `ONLINE` state;
- route/model/profile/provider/effort/cost/capability policy compatibility;
- explicitly excluded workers;
- quota-class compatibility.

Only the resulting candidate set enters Capacity Fabric ranking.

A lower-suitability model/provider may never beat a higher lawful tier because it has more quota. RF1 remains the later prerequisite before heterogeneous provider aliases share equivalence tiers.

---

## 7. Capacity candidate eligibility and ranking — `capacity-placement.v1`

The first policy is deterministic and intentionally small.

### 7.1 Hard capacity refusals

An otherwise Executive-eligible candidate is removed from capacity ranking when any is true:

```text
no exact capacity slot binding
ambiguous capacity slot binding
present != true
enabled != true
cooling.active == true
cooling.active == null
health.state == unavailable
a fresh exact/provider_reported quota horizon proves exhaustion
```

A fresh quota horizon proves exhaustion when either:

```text
remaining == 0 with a known positive limit
or
used_percent >= 100
```

Stale quota never proves current exhaustion by itself; active cooling or another fresh observation must do so.

### 7.2 Health ranking

After hard refusals:

```text
health available  -> rank 0
health degraded   -> rank 1
health unknown    -> rank 2
```

A stale health reading is treated as unknown for ranking. Capacity does not invent health from last outcome.

### 7.3 Quota evidence ranking

Only fresh finite quantitative quota evidence contributes positive headroom information.

For each candidate:

- use the set of fresh `provider_allocation` horizons with either a valid `used_percent` or known positive `limit` + `remaining`;
- derive horizon headroom percent mechanically;
- the candidate's `bottleneck_headroom_percent` is the minimum known headroom across those horizons;
- unknown/stale horizons contribute no numeric headroom and are never converted to 100%;
- exact/provider-reported quantitative evidence outranks estimated evidence;
- partial quantitative coverage outranks no quantitative evidence only within the same health class;
- no quantitative evidence remains a lawful fallback when other hard availability facts are good, but receives **no headroom advantage**.

Conceptual rank components:

```text
health_rank
quota_coverage_rank       # complete / partial / none
quota_evidence_rank       # exact-or-provider-reported / estimated / none
negative bottleneck_headroom_percent when known
stable worker_id
stable quota_class
```

Stable lexical Worker/quota ordering is the final tie-break only. Unknown quota therefore cannot masquerade as free capacity; it simply yields no positive capacity score.

### 7.4 Reliability / cost boundary

`last_outcome`, billing mode and cost remain descriptive/audit inputs in CF2-I V1 unless an already-accepted routing/cost law consumes them. CF2-I must not invent a new economic or quality optimizer while closing the capacity seam.

---

## 8. Atomic claim evidence — `mastermind.executive_capacity_evidence/v1`

`JOB_CLAIMED.payload` gains exactly one optional nested key for capacity-aware orchestration claims:

```text
capacity_evidence
```

Legacy/non-capacity claims preserve existing payload behavior.

Closed conceptual shape:

```json
{
  "schema_version": "mastermind.executive_capacity_evidence/v1",
  "source": {
    "schema": "mastermind.provider_capacity.v1",
    "snapshot_hash": "<64hex>",
    "generated_at": "<UTC>",
    "producer_implementation_version": 1,
    "producer_material_source_digest": "<64hex>",
    "audit_repository_commit": "<40hex>"
  },
  "policy": {
    "version": "capacity-placement.v1",
    "digest": "<64hex>"
  },
  "selected": {
    "capability_id": "codex_account_2",
    "provider": "codex",
    "account_label": "codex_account_2",
    "host_ref": "local-unbound",
    "slot_digest": "<64hex>",
    "slot_evidence": {},
    "rank": {
      "health_rank": 2,
      "quota_coverage_rank": 2,
      "quota_evidence_rank": 2,
      "bottleneck_headroom_percent": null
    },
    "reason_codes": []
  },
  "candidates": []
}
```

`slot_evidence` is the complete canonical secret-free selected slot from the acquired snapshot. This makes historical selection evidence interpretable without a mutable provider lookup. It must hash to `slot_digest`.

### 8.1 Candidate decision rows

Each capacity-considered candidate contributes one bounded row:

```json
{
  "worker_id": "worker-1",
  "quota_class": "default",
  "capability_id": "codex_account",
  "slot_digest": "<64hex-or-null>",
  "decision": "SELECTED",
  "reason_codes": [],
  "rank": {}
}
```

`decision`:

```text
SELECTED
ELIGIBLE_LOWER_RANK
REFUSED
```

Candidate rows are sorted deterministically by `(worker_id, quota_class)` and are capped at 64. Exactly one row is `SELECTED` in a successful capacity-aware claim.

### 8.2 Reason code vocabulary

Closed V1 candidate reasons:

```text
CAPACITY_SLOT_MISSING
CAPACITY_SLOT_AMBIGUOUS
CAPACITY_PRESENT_FALSE
CAPACITY_PRESENT_UNKNOWN
CAPACITY_DISABLED
CAPACITY_ENABLEMENT_UNKNOWN
CAPACITY_COOLING_ACTIVE
CAPACITY_COOLING_UNKNOWN
CAPACITY_HEALTH_UNAVAILABLE
CAPACITY_HEALTH_AVAILABLE
CAPACITY_HEALTH_DEGRADED
CAPACITY_HEALTH_UNKNOWN
CAPACITY_REPORTED_EXHAUSTED
CAPACITY_QUOTA_COMPLETE
CAPACITY_QUOTA_PARTIAL
CAPACITY_QUOTA_REPORTED
CAPACITY_QUOTA_ESTIMATED
CAPACITY_QUOTA_UNKNOWN
CAPACITY_STABLE_TIE_BREAK
```

Reason lists are sorted/unique. They describe deterministic facts/decisions only.

### 8.3 Size bound

Canonical `capacity_evidence` bytes must not exceed **64 KiB**. Exceeding the bound refuses the claim before mutation. Do not silently truncate candidate evidence.

---

## 9. Replay, race, TOCTOU and correction law

### Replay

For a command-bound orchestration claim:

1. perform a read-only lookup for existing `command_id` **before acquisition**;
2. existing canonical `JOB_CLAIMED` => reconcile the same Attempt/evidence; do not reacquire;
3. no existing command => acquire one fresh capacity snapshot;
4. enter the existing atomic claim transaction;
5. re-check `command_id` inside the transaction to close the race;
6. if another writer committed the same command, discard the fresh acquisition and return the persisted result;
7. otherwise re-check Executive candidate state, ensure snapshot freshness still meets the 30-second bound, rank, claim and append evidence atomically.

Same command + changed semantic target remains a conflict under existing law.

### Provider state movement during the claim

Provider state can change after the point-in-time snapshot. That does not rewrite historical evidence. The claim receipt records exactly what was observed and used.

If the acquisition is already older than the freshness limit before commit, reacquire once only as part of the same not-yet-started logical operation. After a claim commits, never reacquire or revise its evidence.

### Correction

A later correction in Macro creates a later `provider_capacity.v1` snapshot. It affects future claims only. It never rewrites:

- historical placement snapshot;
- historical `JOB_CLAIMED.capacity_evidence`;
- historical selected slot evidence;
- historical policy digest.

---

## 10. Failure visibility without a new event plane

Acquisition/capacity failure must not be hidden as a generic successful no-op.

For the COO orchestration path, CF2-I may add one bounded reason to the **existing** COO block receipt vocabulary:

```text
capacity_unavailable
```

The existing block evidence may contain only a safe refusal code from Section 4.4 or a bounded candidate refusal summary. This is an extension of the existing block event path, not a new event/store.

No `JOB_CLAIMED` event is written when capacity acquisition fails or every candidate is refused.

If implementation proves the existing block receipt cannot carry this safely, stop for Sol rather than creating another lifecycle/event.

---

## 11. Security and privacy law

Neither acquisition nor claim evidence may contain:

- API keys, OAuth/token/cookie values;
- credential references that reveal private secret names;
- raw auth-file contents or provider-home bytes;
- email, billing name, provider account ID or user PII;
- private hostname, IP, serial number or endpoint credentials;
- provider-native session handles;
- raw stderr/exception/provider response bodies;
- arbitrary caller/model-supplied file paths or argv.

The caller/model does not author:

- the snapshot;
- capacity timestamps;
- producer identity;
- slot identity;
- rank values;
- policy digest;
- reason codes;
- selected Worker/quota class after eligibility/ranking;
- `capacity_evidence` bytes.

All are derived by trusted deterministic code.

---

## 12. Deterministic vs model-generated method

All CF2-F/CF2-I outputs are deterministic first-party code.

Models may propose/decompose work upstream. They have zero authority over capacity observation, candidate eligibility, quota interpretation, ranking, claim evidence, replay, Worker selection or exhaustion classification.

No LLM scoring is permitted in Capacity Fabric V1.

---

## 13. Ordered CF2-I implementation sequence

After this source law is accepted, one bounded CF2-I operator should proceed in this order:

1. Add strict Mastermind consumer types/validator for `mastermind.provider_capacity.v1`; do not import Macro Python.
2. Add `MacroCapacityAcquirer/v1` with timeout/size/path/error redlines and no writes.
3. Add pure deterministic capacity binding/ranking functions and mutation tests.
4. Add pure `mastermind.executive_capacity_evidence/v1` builder/validator and policy digest.
5. Integrate replay-before-acquisition and transaction-time freshness into the existing command-bound claim path.
6. Extend `JOB_CLAIMED` with `capacity_evidence` while keeping placement JSON/digest byte-for-byte unchanged.
7. Add existing COO block-path `capacity_unavailable` visibility if needed by the real cycle consumer.
8. Prove exact replay/race behavior and zero duplicate Attempt/Event.
9. Run fixture canaries with three Codex-shaped workers/slots.
10. After the three real Personal-Pro Codex realms are live and G7 permits the production canary, prove one real same-provider/multi-account selection on the armed Executive path.

CF2-I stops there. RF1/HF1/provider expansion remain separate.

---

## 14. Acceptance tests and falsifiers for CF2-I

The implementation is not accepted without discriminating tests for at least:

### Acquisition

- correct CF1 stdout accepted;
- nonzero exit refused;
- timeout refused and owned process reaped;
- oversize stdout refused;
- malformed/noncanonical JSON refused;
- wrong schema/producer refused;
- invalid snapshot hash refused;
- `material_sources_match_commit=false` refused;
- stale/future snapshot refused;
- raw stderr/private exception never propagates;
- caller cannot choose Macro path, script, argv, generated time or snapshot.

### Null/evidence law

- unknown quota is never converted to zero/unlimited/100% headroom;
- stale quota contributes no fresh numeric advantage;
- estimated evidence ranks below provider-reported/exact within equivalent coverage;
- active/unknown cooling refuses;
- present/enablement false or unknown refuses;
- health unavailable refuses; degraded/unknown remain explicit lower ranks;
- fresh reported exhaustion refuses.

### Binding/ranking

- exact provider/account match binds one slot;
- missing/duplicate match refuses;
- shuffling input candidate/snapshot order does not alter output;
- known higher bottleneck headroom wins only after existing hard suitability/authority filters;
- stable tie-break is deterministic;
- capacity cannot select an Executive-ineligible/quarantined/excluded worker.

### Atomicity/replay

- `placement_snapshot_json` schema and digest remain unchanged;
- successful claim contains exactly one validated `capacity_evidence` object;
- capacity evidence is under the byte ceiling and not truncated;
- same command replay performs zero acquisition and returns persisted Attempt/evidence;
- concurrent same-command attempts produce one canonical claim;
- command semantic-target drift still conflicts;
- acquisition failure creates zero Attempt/JOB_CLAIMED and uses only the existing block path;
- provider state changing after commit cannot rewrite historical evidence.

### No-rebuild

- schema remains v4;
- zero new capacity/provider lifecycle tables;
- zero new capacity daemon/service/scheduler;
- zero new claim/allocation event type;
- zero Macro provider-ledger imports into Mastermind;
- zero provider credential reads from the capacity consumer.

---

## 15. Real production proof owed by CF2-I

Green tests/CI are not enough.

The first production proof must show, on the real installed Executive host:

1. the three intended Codex Personal-Pro Worker realms are separately ready;
2. one bounded orchestration child has at least two otherwise-lawful Codex account candidates;
3. a fresh real CF1 snapshot is acquired through the accepted read-only seam;
4. capacity rank chooses one candidate deterministically;
5. the same atomic claim persists unchanged placement identity plus exact `capacity_evidence`;
6. the selected Worker actually executes the bounded child through the real provider path;
7. replay/reconciliation shows no duplicate Attempt/provider turn;
8. the evidence explains the choice even if quota is unknown and the final tie-break is stable;
9. no Chairman manual account selection is required.

Only then may CF2-I be called `PROVEN_LIVE` for same-provider/multi-account placement.

---

## 16. Explicit non-goals

CF2-F and CF2-I do not include:

- RF1 heterogeneous provider equivalence tiers;
- HF1 provider-neutral broker generalization;
- Claude/Cursor/Grok/OpenRouter/GLM/Z.AI/Alibaba integration;
- multi-host/VPS transport;
- worker Browser/DevServer Resource Fabric;
- Slack Agent Relay/ASD;
- Personal-Pro CEO write transport;
- Control Room redesign;
- dynamic MCP/plugin installation;
- market/trading/model signal authority.

These continue on their own carriers.

---

## 17. Stop condition and continuation handoff

### CF2-F stop

Stop after this records-only source law is independently reviewed and accepted. Do not begin implementation in the same carrier.

### Required return to Sol

Return:

- exact source-law PR/head;
- any finding that the landed v4 `JOB_CLAIMED` payload cannot safely carry the bounded nested evidence;
- any proof that the read-only subprocess cannot be made secret-safe/no-write without a daemon/store;
- any collision with newer Executive claim/replay law.

### On PASS

Commission one fresh CF2-I implementation carrier whose observable mission is:

> **A command-bound Executive COO claim consumes one fresh strict Macro capacity snapshot, ranks only already-lawful candidates, atomically receipts the exact decision in `JOB_CLAIMED`, and proves a real multi-Codex-account canary without changing schema v4 placement or creating another control plane.**

CF2-I must stop before RF1/HF1/provider expansion.
