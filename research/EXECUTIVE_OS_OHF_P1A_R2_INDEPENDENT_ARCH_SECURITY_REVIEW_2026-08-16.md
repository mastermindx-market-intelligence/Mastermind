# OHF-P1A-R2-IR — Independent re-review of remediated architecture

**Date:** 2026-08-16
**Commission:** OHF-P1A-R2-IR
**PR:** [#84](https://github.com/mastermindx-market-intelligence/Mastermind/pull/84)
**Architecture SHA reviewed:** `da746a90c93c168ba696944c9197e7699d05e959`
**This artifact does not review itself.**
**R1 review of `f3c1cdb7…` is historical evidence only and was not modified.**
**Author contracts were not edited in this pass.**
**Production / implementation / schema-migration / P1B / Phase 1F-C / merge authority:** none.

Final verdict: **REVISE_AND_REREVIEW**

R2 correctly replaced Attempt 1:1 session with CARDINALITY_B, deleted live App
Server adoption, split requested vs observed profile *as types*, preserved
honest gates, and stopped treating `ended_at` as writer release. That is real
progress. It is not a frozen architecture.

If P1B implemented `da746a90` literally, it would still have to invent:

- whether `attempts.provider_session_id` / pid fields may change across epochs
- who allocates epoch/generation IDs
- what fences two writers while `provider_session_id` is NULL
- where `OperationId` is durably deduplicated
- how requested capabilities, workspace, sandbox, binary, and served model are
  actually compared
- whether the adapter may assert Executive writer / resume-safe truth

Green CI does not close those.

---

## A. Review lineage

| Item | Value |
|---|---|
| PR | #84 open **draft**, `MERGEABLE` / `CLEAN`, not merged |
| Architecture SHA reviewed | `da746a90c93c168ba696944c9197e7699d05e959` |
| Base / current master | `37c34e2e83fe101cd7328bd74b5d33f46064239d` |
| R1 architecture | `f3c1cdb7d3b40103450cf3f845ac0648479585e7` |
| R1 review artifact | `3f1ee290ba147313d3bee3a1192e18b21313f88d` |
| CI `test` | SUCCESS |
| CodeQL + Analyze (actions/js/python) | SUCCESS |

Head matched the commissioned SHA. No silent head move.

Hidden #66/#72 dependency: none found. Draft-only citations remain names.

---

## B. R1 findings closure

| ID | Original class | R2 claimed | Independent result |
|---|---|---|---|
| R1 CARDINALITY_B vs retry | ARCH_BLOCKER | REMEDIATED | **PARTIALLY_CLOSED** — prose/matrix correct; Attempt field compatibility (H13/H14) unresolved |
| R2 writer realm | ARCH_BLOCKER | REMEDIATED | **PARTIALLY_CLOSED** — post-bind `(worker_id, provider_session_id)` is right; pre-bind NULL window is open (H15) |
| R3 process death ≠ writer | ARCH_BLOCKER | REMEDIATED | **CLOSED** for the four-fact model in constitution + `process_end_does_not_release_writer` |
| R4 live App Server adoption | ARCH_BLOCKER | REMEDIATED | **CLOSED** — `LIVE_APP_SERVER_ADOPTION = NOT_SUPPORTED`; old adopt-stdio law gone from author contracts |
| R5 profile seal | ARCH_BLOCKER | REMEDIATED | **PARTIALLY_CLOSED** — two types exist; comparator does not actually derive ALLOW (H18–H21) |
| R6 typed adapter | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED | **PARTIALLY_CLOSED** — dataclasses exist; ID ownership, optional Protocol, durable idempotency, comparator authority remain inventable |
| R7 restore | ARCH_BLOCKER | REMEDIATED | **PARTIALLY_CLOSED** — invalidate-on-restore + LOST is right; RELEASED→UNKNOWN destroys historical evidence (H25) |
| R8 account_label | PRODUCTION gate | GATE_PRESERVED | **CLOSED** as a gate (still unproven; correctly not faked) |
| R9 one source of truth | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED | **PARTIALLY_CLOSED** — synonym `native_session_id` gone; Attempt projections still a second truth vs write-once runtime |
| R10 helpers | WRITE_CANARY | GATE_PRESERVED | **CLOSED** as a gate |
| R11 exact binary | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED | **CLOSED** |
| R12 1F tradeoff | REQUIRED_BEFORE_P1A_MERGE | REMEDIATED | **CLOSED** (`V1_QUALITY_TRADEOFF_ACCEPTED`) |
| R13 residual plugins | WRITE_CANARY | GATE_PRESERVED | **CLOSED** as a gate |
| R14 postpone extras | postpone | REMEDIATED/POSTPONED | **CLOSED** |

No REGRESSED R1 item. Several claimed REMEDIATED items are only half-closed.

---

## C. Attempt definition

Accepted: one leased execution placement of a Job — one `(worker_id, quota_class)`
claim, one authority-policy hash, one workspace binding, one lease/fence
generation, one retry slot (`attempt_number` toward `attempt_limit`).

Merged runtime still increments `attempt_count` only in `claim_job`. Epoch
rotation in the typed matrix does not call claim. **Retry accounting is not
mutated by CARDINALITY_B as prose.** It *would* be mutated if P1B treated
rotation as a new Attempt, which R2 forbids.

Immutable after claim (merged): `attempt_id`, `job_id`, `attempt_number`,
`worker_id`, `quota_class`, `authority_policy_hash`, `started_at_ms`.

Merged `pid` / `provider_session_id` are **write-once** (`record_process`
refuses a second identity; `record_process_exit` refuses a changed session id).
That is the H13/H14 collision.

---

## D. Session cardinality

**CARDINALITY_B accepted as identity model? YES.**

- Attempt : SessionEpoch = 1:N sequential, at most one CURRENT
- SessionEpoch : ProcessGeneration = 1:N sequential
- native subordinate = not an epoch, not a Job, not review

Do **not** revert to 1:1. Close the compatibility and pre-bind holes instead.

---

## E. Existing Attempt-field compatibility

| Field | Sealed worker today | R2 rich-OHF claim | Independent verdict |
|---|---|---|---|
| `attempts.provider_session_id` | write-once canonical | “current-epoch projection” | **contradicts merged `record_process`** |
| `attempts.pid/pgid/start/boot` | write-once canonical | “current-generation projection” | **same contradiction** |

Required choice (R2 did not make a compatible one):

**A. LEGACY/SEALED-ONLY** for rich OHF: never rewrite these columns after first
sealed-style record; canonical OHF identity lives only on epoch/generation
rows. `adopt_attempt` today requires pid **or** `provider_session_id`; rich OHF
must keep a non-null legacy identity *or* amend `adopt_attempt` in a later
schema commission with an explicit discriminator.

**B. SAFE_MUTABLE_PROJECTION_WITH_DISCRIMINATOR:** change `record_process` /
`record_process_exit` / `adopt_attempt` only for Attempts that have epoch rows;
sealed Attempts remain write-once.

R2’s “same-txn projection” without a discriminator is **not C**. It is an
unresolved contradiction.

Independent required verdict: **A or B must be chosen in author R3. Current
text is neither.** Treat current “projection” as **REDESIGN**.

---

## F. Session epoch law

| Question | R2 text | Independent |
|---|---|---|
| epoch creation owner | implied Executive; `start_session` returns `SessionEpochRef` | **ambiguous** (H16) |
| epoch_number owner | monotonic; not named | **ambiguous** |
| provider_session_id binding | epoch column; adapter start_session creates provider session | **adapter-side-effect before durable bind** |
| current epoch | unique CURRENT index | ACCEPT as SQL |
| terminal | TERMINAL / Attempt terminalization | ACCEPT |
| abandon | ABANDONED; never reopen | ACCEPT; atomicity with writer-clear unspecified (H26) |
| cross-Attempt reuse | lifetime unique `(worker_id, provider_session_id)` | ACCEPT as fail-closed (H28 SAFE_CONSERVATIVE) |

---

## G. Pre-bind writer law

**What prevents duplicate generation/session creation while `provider_session_id` is NULL?**
Nothing durable in the proposed SQL. The unique writer index is:

```sql
WHERE executive_writer_held = 1 AND provider_session_id IS NOT NULL
```

SQLite therefore allows two held generations on the same CURRENT epoch with
NULL session ids. One CURRENT epoch does not imply one writer generation.
`OperationId` is not a table.

**Pre-bind fence key:** **missing.**

**Post-bind key:** `(worker_id, provider_session_id)` WHERE held=1 — correct.

**Both phases atomic?** No.

This is **ARCH_BLOCKER** (H15). A later unique `session_epoch_id WHERE
executive_writer_held=1` plus Executive-allocated generation before launch is
sufficient; do not require a `CREATING` epoch state unless that fence still
fails.

---

## H. Writer law

- realm after bind: `(worker_id, provider_session_id)` — ACCEPT
- Executive writer owner: generation `executive_writer_held` — ACCEPT
- provider states: HELD / RELEASED / UNKNOWN — ACCEPT
- process death: `ended_at` only; hold remains — ACCEPT (R3 CLOSED)
- abandon: clear Executive hold, do not invent RELEASED — ACCEPT
- fresh S2: new epoch, same Attempt — ACCEPT
- pre-bind: **unsafe**

---

## I. OperationId / idempotency

`OperationId` is a frozen dataclass. It is **not** a durable law.

Merged Executive already has `events.command_id TEXT NOT NULL UNIQUE` and
`find_event_by_command_id`. R2 never binds `OperationId.command_id` to that.

| Operation | Idempotency key in contract | Durable owner | Crash-after-side-effect |
|---|---|---|---|
| start_session | OperationId (notes) | **unspecified** | provider S1 can exist with no Executive row |
| start generation | mixed into start_session | unspecified | second process |
| bind provider session | none | unspecified | S1 lost or duplicated |
| begin_turn | OperationId on Protocol | unspecified | duplicate turn |
| resume_session | notes only; **not on Protocol** | unspecified | second writer |
| fork_session | notes; **not on Protocol** | unspecified | extra fork |
| send_input | **no OperationId**; still `idempotent=True` | none | duplicate steer |
| respond_to_approval | **no OperationId**; still `idempotent=True` | none | duplicate approval |

An in-memory adapter map is not sufficient. P1B would invent this. **H17
CONFIRMED_DEFECT.**

---

## J. Executive ID ownership

| ID | Who R2 Protocol implies | Required |
|---|---|---|
| session_epoch_id | adapter (`start_session` returns it, does not receive it) | **Executive** |
| epoch_number | adapter | **Executive** |
| process_generation_id | “supervisor already allocated” vs start_session launching | **ambiguous; must be Executive** |
| generation_number | unspecified | **Executive** |
| turn_id | adapter (`begin_turn` returns `TurnRef`) | **Executive** |

A provider adapter must not mint organizational IDs. Safer order: Executive
`BEGIN IMMEDIATE` allocates epoch+generation+writer+OperationId intent, then
adapter starts provider session against those refs, then Executive binds
`provider_session_id` and process identity.

---

## K. Requested profile

Fields on `RequestedExecutionProfile`: worker_id, provider, requested_model,
harness_kind, harness_binary_digest, harness_version, workspace, sandbox,
approval, network, capabilities (`CapabilityIdentity` tuples),
native_helper_policy, authority_policy_hash, allowed_write_paths, write_capable.

Seal: after claim, before process start. Attempt-immutable. **ACCEPT as type.**

---

## L. Observed attestation

`ObservedHarnessAttestation`: served_model optional; harness version/digest
optional; effective_skills/mcp/plugins as **plain name tuples**; sandbox;
approval; config digest; AuthRealmFact; workspace optional; unknown_fields.

Seal: after initialize, before first work turn. Unknown is supposed to stay
UNKNOWN. The comparator then **ALLOWs UNKNOWN served_model**. Contradiction.

---

## M. Launch comparator

`compare_launch` does **not** derive the decision from requested+observed alone.

Caller-supplied, defaulting to permissive:

- `unclassified=()`
- `missing_required=()`
- `forbidden_present=()`
- `workspace_match=True`
- `auth_realm_match=True`
- `config_drift=False`
- `lab_unclassified_policy=False`
- `supports_subagent_capability_ceiling=False`

It never compares:

- `requested.harness_binary_digest` vs `observed.harness_binary_digest`
- sandbox / approval / workspace identity fields
- capability digests
- `served_model is None`

| Question | Answer |
|---|---|
| Canonical comparator derives from typed data? | **NO** |
| Caller can force ALLOW? | **YES** — pass empty mismatch lists and default True matches |
| `served_model=None` | **ALLOW** (only truthy mismatch refuses) |
| harness digest mismatch | **not compared** |
| sandbox mismatch | **not compared** |
| approval mismatch | **not compared** |
| workspace mismatch | only if caller sets `workspace_match=False` |
| capability digest mismatch | **impossible** — observed side is names only |
| auth realm UNKNOWN | `auth_realm_match` defaults **True** |

R5/R6 are not closed.

---

## N. Capability precision

Requested: `CapabilityIdentity` (name + binary digest + optional content/schema/MCP).
Observed: `tuple[str, ...]`.

These are **not comparable at the claimed precision**. Names-only observation
cannot prove same skill content or tool schema. Either observe typed identities
where available, or freeze V1 comparison as name+requested-binary-digest only
and stop promising schema/content binding until observed.

---

## O. Adapter Protocol

Required methods have Protocol signatures. Optional methods mostly do **not**.

| Method | Signature frozen on Protocol? | OperationId on Protocol? |
|---|---|---|
| describe_capabilities | YES, but `-> Mapping[str, object]` | N/A |
| validate_requested_profile | YES | NO (pure) |
| start_session | YES | YES |
| begin_turn | YES | YES |
| read_events | YES | NO |
| interrupt_turn | YES | YES |
| collect_candidate_result | YES | NO |
| graceful_stop | YES | YES |
| cancel | YES | YES |
| reconcile | YES | NO |
| probe | **NO** | — |
| stage_operator_config | **NO** (types exist off-Protocol) | types exist |
| resume_session | **NO** | — |
| send_input | **NO** | **NO** |
| respond_to_approval | **NO** | **NO** |
| fork_session | **NO** | — |
| checkpoint | **NO** | — |

`METHOD_CONTRACTS` strings are not Python signatures. `describe_capabilities() -> Mapping[str, object]`
undercuts the typed-enough claim; it should return a frozen capability/support envelope.

---

## P. ReconcileReport authority

| Field | Should be | Actual |
|---|---|---|
| process_liveness | adapter observation | observation |
| process_identity_match | derived vs Executive identity | adapter boolean |
| provider_session_reachable | adapter observation | observation |
| provider_writer_state | adapter observation | observation |
| executive_writer_held | **Executive SQLite** | **adapter-returned** |
| workspace_identity_match | derived | adapter boolean |
| profile_or_config_drift | derived | adapter boolean |
| resume_safe | derived by `derive_resume_safety` | **adapter-returned standalone bool** |
| may_kill/resume/lost | forbidden | correctly rejected in `__post_init__` |

Adapter can assert `resume_safe=True` and `executive_writer_held=True`. That is
authority leakage. Supervisor must combine Executive rows + observations +
pure derive.

---

## Q. Process/controller topology

| Concept | Verdict |
|---|---|
| Attempt lease adoption | possible (`adopt_attempt`) |
| old App Server transport adoption | **NOT_SUPPORTED** |
| new ProcessGeneration | required after controller restart |
| provider session resume | optional; new generation only |

R4 CLOSED. Do not regress.

---

## R. Restore law

R2 Option A + Attempt LOST + do not invent RELEASED: **direction ACCEPT**.

`restore_invalidation()` rewrites snapshot `RELEASED` to current `UNKNOWN` in
the **same** `WriterFacts.provider_writer_state` field. That erases truthful
historical observation.

Required split:

- historical observation (immutable snapshot evidence, may be RELEASED)
- post-restore current knowledge (UNKNOWN until reconcile)
- Executive authority (held cleared; epochs abandoned; Attempt LOST)

---

## S. Schema-v3 readiness

**NOT_READY**

Still inventable: pre-bind writer unique, OperationId/command_id receipt,
legacy vs projection discriminator, epoch/generation allocation transaction,
abandon+rotate atomic group, restore historical vs current columns, event
cursor sequence scope.

Do not implement SCHEMA_VERSION 3.

---

## T. Atomic transaction matrix

R2 names “same-txn projection” in places and does **not** freeze these groups:

| Group | Required in one `BEGIN IMMEDIATE` | Specified? |
|---|---|---|
| create epoch + allocate generation + reserve pre-bind writer + OperationId intent | yes | **NO** |
| launch-intent receipt | yes | **NO** |
| bind provider_session_id + copy generation projection + immutable trigger | yes | partial (immutability only) |
| activate generation / attestation seal | yes | **NO** |
| graceful replacement: release gen1 hold + insert gen2 hold | yes | **NO** |
| abandon epoch + clear hold + (optional) create CURRENT S2 + pointer update | yes | **NO** |
| context rotate: TERMINAL old CURRENT + insert new CURRENT | yes (unique CURRENT) | SQL helps; service order unspecified |
| terminalize Attempt + clear holds without inventing RELEASED | yes | partial |
| restore invalidation | yes | helper only, not txn |

---

## U. Crash-window matrix

| Window | Durable state today | Safe retry | Duplicate risk |
|---|---|---|---|
| epoch inserted, process not launched | unspecified | unspecified | **high** if adapter retries start_session |
| generation reserved, process launched, identity not persisted | unspecified | terminate orphan | **orphan process** |
| provider created S1, id not stored | S1 exists at provider | **unknown** | **second S2** or lost S1 |
| session bound, attestation not sealed | unspecified | refuse work | work-before-ALLOW if comparator bypassed |
| attestation stored, first turn not started | unspecified | begin_turn + OperationId | if OperationId not durable, duplicate turn |
| begin_turn accepted, TurnRef not persisted | unspecified | unspecified | duplicate turn |
| graceful stop RELEASED, not persisted | process dead | may resume unsafely or double-stop | writer state lie |
| Executive hold cleared, epoch not yet ABANDONED | hold=0, still CURRENT | another writer can attach | **H26** |

---

## V. Sealed worker compatibility

`WorkerExecutionAdapter` + write-once `record_process` remain the sealed floor
**only if** rich OHF does not start rewriting those columns.

R2’s projection language would force a semantic change to sealed APIs.
**Sealed path is not proven unchanged.** Discriminator required.

---

## W. Phase 1F

Planning Attempt → children → release leader → later **new** aggregation
Attempt + fresh session + handoff: **ACCEPT**.

Context rotation inside planning Attempt = new epoch, **not** new Attempt:
**ACCEPT**.

`V1_QUALITY_TRADEOFF_ACCEPTED`: **ACCEPT**; later parity measurement required.
No parked hidden leader: **ACCEPT**.

---

## X. Preserved gates

- ACCOUNT_REALM_ATTESTATION_UNPROVEN (multi-account / production)
- residual Codex plugins (write-canary / production)
- native-helper ceiling (write-capable helpers)
- transitive orphan cleanup UNKNOWN
- host reboot UNKNOWN
- multi-host identity postponed
- `CODEX_HOME` not a SQLite worker column (slot can change home without new `worker_id`) — production/auth gate, not a reason to use `account_label`

Honest gates. Not architecture failure by themselves.

---

## Y. H13–H34

| H | Result | Evidence |
|---|---|---|
| H13 Attempt.provider_session_id vs write-once | **CONFIRMED_DEFECT** | `record_process` 2891–2892; schema §3.1 “projection” |
| H14 Attempt pid projection | **CONFIRMED_DEFECT** | same write-once; `adopt_attempt` requires pid or session |
| H15 pre-bind writer | **CONFIRMED_DEFECT** | unique index requires `provider_session_id IS NOT NULL` |
| H16 ID allocation | **CONFIRMED_DEFECT** | `start_session(...) -> SessionEpochRef` mints Executive IDs |
| H17 durable OperationId | **CONFIRMED_DEFECT** | type only; existing `events.command_id` unused |
| H18 caller-supplied verdicts | **CONFIRMED_DEFECT** | `compare_launch` kwargs default permissive |
| H19 capability precision | **CONFIRMED_DEFECT** | CapabilityIdentity vs `tuple[str]` |
| H20 served_model UNKNOWN | **CONFIRMED_DEFECT** | None → ALLOW |
| H21 binary/sandbox/approval/config | **CONFIRMED_DEFECT** | not compared |
| H22 auth_realm_match default True | **CONFIRMED_DEFECT** | defeats UNKNOWN / R8 |
| H23 optional Protocol signatures | **CONFIRMED_DEFECT** | missing on Protocol |
| H24 ReconcileReport Executive facts | **CONFIRMED_DEFECT** | `executive_writer_held`, `resume_safe` |
| H25 restore RELEASED→UNKNOWN | **CONFIRMED_DEFECT** | `restore_invalidation` |
| H26 atomic epoch/writer txns | **CONFIRMED_DEFECT** | indexes ≠ named BEGIN IMMEDIATE groups |
| H27 CREATING state | **NEEDS_AMENDMENT** | CURRENT+NULL is enough **iff** H15 fence exists |
| H28 lifetime session unique | **NOT_A_DEFECT** | SAFE_CONSERVATIVE fail-closed; opaque recycle refused |
| H29 worker_id stability | **PRODUCTION_GATE_ONLY** | PK + register refuse + provider not updated; CODEX_HOME unbound |
| H30 start_session width | **CONFIRMED_DEFECT** | one method creates session **and** may launch process |
| H31 generation.provider_session_id copy | **NEEDS_AMENDMENT** | projection OK; mismatch refuse not specified |
| H32 Attempt current pointers | **NEEDS_AMENDMENT** | too many currents if H13/H14 choose LEGACY_ONLY |
| H33 EventCursor sequence | **CONFIRMED_DEFECT** | last_sequence scope unspecified |
| H34 all methods idempotent | **CONFIRMED_DEFECT** | send_input/approval marked idempotent without OperationId |

---

## Z. Findings

### R2-1 — Attempt session/process columns cannot be OHF projections under current runtime
- **Class:** ARCH_BLOCKER
- **Severity:** high
- **Source:** schema §2/§3.1 vs `record_process` / `record_process_exit`
- **Failure:** CARDINALITY_B S1→S2 cannot update write-once Attempt fields; P1B either breaks sealed workers or cannot project
- **Remediation:** choose **LEGACY_ONLY** or **discriminator + explicit mutation APIs**; do not say “projection”

### R2-2 — No durable writer fence before `provider_session_id` exists
- **Class:** ARCH_BLOCKER
- **Severity:** high
- **Source:** `process_generations_one_executive_writer` partial unique
- **Failure:** timeout retry launches G1 and G2 both held with NULL session id
- **Remediation:** unique Executive writer per `session_epoch_id` (and/or durable OperationId intent) **before** provider bind

### R2-3 — Adapter Protocol mints Executive identities
- **Class:** ARCH_BLOCKER
- **Severity:** high
- **Source:** `OperatorHarnessAdapter.start_session` / `begin_turn`
- **Failure:** two controllers mint two epoch ids for one Attempt
- **Remediation:** Executive allocates epoch/generation/turn ids; adapter receives refs

### R2-4 — OperationId is not crash-safe
- **Class:** ARCH_BLOCKER
- **Severity:** high
- **Source:** contract `OperationId`; runtime `events.command_id` unused by OHF
- **Failure:** provider S1 created, controller dies, retry creates S2
- **Remediation:** bind OperationId to Executive `command_id` (or same-SQLite receipt); specify crash-after-side-effect

### R2-5 — Launch comparator is caller-verdict, not attestation
- **Class:** ARCH_BLOCKER
- **Severity:** high
- **Source:** `compare_launch`
- **Failure:** adapter passes empty mismatch lists → ALLOW; `served_model=None` ALLOW; digest/sandbox/workspace not compared
- **Remediation:** pure function of Requested+Observed; UNKNOWN served model REFUSE for V1 exact-model identity; default-deny matches

### R2-6 — ReconcileReport asserts Executive-owned truth
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Source:** `ReconcileReport.executive_writer_held`, `resume_safe`
- **Failure:** harness certifies its own resume
- **Remediation:** observations only; supervisor + `derive_resume_safety`

### R2-7 — Restore collapses historical RELEASED into UNKNOWN
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Source:** `restore_invalidation`
- **Remediation:** split historical observation vs post-restore current knowledge; still invalidate authority

### R2-8 — Optional methods and EventCursor not frozen
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Source:** Protocol vs METHOD_CONTRACTS; `EventCursor.last_sequence`
- **Remediation:** Protocol or extension Protocol with types; sequence scope; OperationId on state-changing optionals

### R2-9 — start_session combines session create and process launch
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Remediation:** split or define partial receipts for each side-effect

### R2-10 — Named transaction groups missing
- **Class:** SCHEMA_V3_GATE (also blocks claiming schema-ready)
- **Remediation:** §T groups in constitution/schema before any v3 implementation

---

## What may proceed

| Action | |
|---|---|
| Merge #84 as accepted architecture? | **NO** |
| Start P1B provider-neutral scaffolding? | **NO** |
| Start CodexOperatorAdapter? | **NO** |
| Implement schema v3? | **NO** |
| Start read-only Codex OHF canary? | **NO** |
| Start write-capable Codex OHF canary? | **NO** |
| Start Browser/DevServer Resource Fabric? | **NO** |
| Start Claude inert probe? | **YES** (evidence only; not OHF runtime) |
| Start Grok inert probe? | **YES** |
| Start Qwen inert probe? | **YES** |
| Production-arm Codex OHF? | **NO** |
| Start Phase 1F-C? | **NO** |

Author R3 may amend contracts on a new architecture SHA. Independent exact-head
re-review required. Do not mix repair into this review commit.

---

## Final verdict

**REVISE_AND_REREVIEW**

Smallest precise remediation set (do not reopen 1:1 cardinality):

1. **LEGACY_ONLY or explicit discriminator** for `attempts.provider_session_id` and pid fields.
2. **Pre-bind Executive writer unique on `session_epoch_id`** (plus durable OperationId intent).
3. **Executive allocates** epoch/generation/turn IDs before adapter side effects.
4. **Bind OperationId to Executive `command_id`** and specify crash-after-provider-side-effect.
5. **Pure launch comparator** from requested+observed; `served_model=None` REFUSE for V1; no default-True matches.
6. **ReconcileReport observational only**; restore splits historical vs current.

Direction remains compatible with Charter P7 and Phase 1F. `da746a90` is not
yet implementable without new lifecycle decisions.
