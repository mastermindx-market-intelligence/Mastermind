# Executive OS Phase 1F-C — final independent post-P1B design review

**Date:** 2026-08-20

**Reviewer role:** independent architecture/security reviewer

**Runtime design baseline:** OHF P1B squash merge
`4f672b8f6b950010534390001f4a17ed232e0390`

**Commission delivery base:** Mastermind `origin/master`
`a790fb56c1c557197927dee9a76356a47188191b`

**Reviewed commission:**
`research/EXECUTIVE_OS_PHASE1FC_CEO_POLICY_AND_IMPLEMENTATION_COMMISSION_2026-08-20.md`

**Exact reviewed commission identity:**

- SHA-256:
  `ff141dadcf5e9972cfc307e844c4bd998cb268d3adf8b7e4cfa20b793f201812`
- length: `2,320` lines / `148,589` bytes
- Markdown fence markers: `28`
- worktree state at review: `HEAD == origin/master ==`
  `a790fb56c1c557197927dee9a76356a47188191b`; only the commission and this
  commissioned review artifact differed from that base
- review mode: read-only for the commission, runtime, provider, host,
  credentials, and databases; the only authorized write was this review artifact

## STATUS

**PASS FOR INERT IMPLEMENTATION ONLY.**

Severity adjudication on the exact bytes above:

| Severity | Open findings |
|---|---:|
| P0 | 0 |
| P1 | 0 |
| P2 | 0 |

The commission is internally coherent and implementable on the exact merged OHF
P1B/schema-v3 baseline. It authorizes a separately bounded, unarmed Phase 1F-C
implementation after this PASS is recorded. It does not prove that the code,
schema-v4 migration, deterministic acceptance, provider substrate, host, planner,
production dispatch boundary, or live vertical exists.

No implementation, merge, installation, migration, provider call, credential
operation, host mutation, service activation, production dispatch, or arming is
authorized or claimed by this review. Every operational gate remains pending.

## Supersession and review-history reconciliation

This final review supersedes every earlier PASS, HOLD, NO-SHIP, partial audit,
and intermediate commission-hash verdict previously recorded in this artifact or
its review process.

The earlier design initially appeared sufficient, but that verdict was withdrawn
after independent cross-review exposed two source-law defects: it required an
execution-principal snapshot before an OHF Attempt entered `RUNNING`, although
frozen P1B TX-3 enters `RUNNING` before TX-4 can observe and compare launch facts;
and it described rollback as a source revert without separating the post-v4
forward-fix boundary. Subsequent exact-byte reviews also found and closed missing
typed principal sources, terminal-generation qualification, lossless raw-result
transport, provider lifecycle cardinality, literal legacy-content projection,
TX-9 detached continuation, quota-continuity, and worker-wide quarantine details.

The final commission SHA-256 above is the sole current source-law candidate. Any
older commission hash, line count, historical PASS, or HOLD is evidence of the
review process only and grants no authority. The historical review prose does not
override or supplement the final commission.

## Final architecture and security adjudication

### 1. Frozen TX-3/TX-4 order and typed launch principal — PASS

The final law preserves P1B's transaction order:

```text
TX-3 binds native session/process identity and sets Attempt RUNNING
-> execution-principal pair may still be NULL and work remains forbidden
-> supervisor authors typed OS-principal/UID/provider-home observation
-> Runtime-owned TX-4 independently derives compare_launch
-> ALLOW + principal pair + generation admission commit atomically
```

`ObservedHarnessAttestation` is not widened. The supervisor observation supplies
the facts it does not contain: OS principal name, numeric effective UID, exact
process identity, provider-session/generation identity, and a fresh symlink-safe
dedicated-provider-home identity. `account_label`, provider, worker, and quota are
joined only inside Runtime from the immutable claim-time placement snapshot.

On `ALLOW`, the existing TX-4 transaction atomically commits the ordinary launch
decision, stable Attempt principal pair, and exact-generation
`ORCHESTRATION_WORK_ADMITTED` Event. On `REFUSE`, comparison error, forged input,
or mismatch, no principal/admission evidence is created; cleanup and fenced
adverse termination remain legal. Crash-before, crash-after, replay, and successor
generation behavior are explicitly closed.

### 2. Stable Attempt identity versus per-generation evidence — PASS

The stable `mastermind.execution_principal_snapshot/v1` excludes generation,
session, attestation-time, and process-instance facts. Every lawful OHF generation
separately binds its process/session identity, observed attestation, raw principal
observation, placement, effective grant, and stable principal digest in its own
admission Event. A successor generation cannot inherit a predecessor's admission.

The deterministic/runtime independence floor is different immutable completing-
Attempt `worker_id` values. Live acceptance additionally requires different
accepted OS principals/UIDs, provider homes, and account labels. Mutable terminal-
time Worker rows and worker prose are never identity evidence.

### 3. Lossless raw role-result transport and work closure — PASS

The final commission does not overload P1B's bounded/redacted
`CandidateResult.summary`. It defines a separate optional typed observation and a
single fixed `thread/turns/list` raw-page primitive with:

- one reserved request path and one-shot in-memory consumption;
- a `64 MiB` per-frame limit;
- at most `128` pages, `128 MiB` cumulative bytes, and one `120 s` monotonic
  deadline;
- exact descending cursor progression and native turn correlation;
- strict phased-agent-message versus sole-unphased-message cohorts;
- direct-text or ordered text-block reconstruction, with byte equality when both
  representations exist;
- an `8 MiB` canonical orchestration-result envelope ceiling; and
- duplicate-key, invalid UTF-8, malformed JSON, noncanonical JSON, unknown-field,
  identity/lineage, artifact-digest, and sensitive-content refusal.

The ordinary App Server response, notification, error, stderr, and P1B paths stay
redacted. Raw response bytes cannot enter logs, exceptions, notifications,
receipts, or Events. The complete accepted canonical envelope is stored losslessly
inside one immutable `ORCHESTRATION_ROLE_RESULT_SEALED` Event before provider
shutdown.

The unique seal is the derived `work_closed` predicate. After it commits, all
TX-2, TX-5, checkpoint, collection/publication, TX-10/TX-11, successor-generation,
and replacement-epoch work paths refuse. Event-first seal replay performs zero
provider calls. A raw read racing an already committed seal persists nothing.
Only bounded heartbeat/lease-CAS authority needed for cleanup, shutdown,
validation, and terminalization remains.

### 4. Provider lifecycle cardinality and recovery — PASS

The non-configurable ceilings are coherent and direct-Runtime enforced:

```text
MAX_ORCHESTRATION_EPOCHS_PER_ATTEMPT = 1
MAX_ORCHESTRATION_TX5_PER_GENERATION = 1
MAX_ORCHESTRATION_TX5_PER_ATTEMPT = 2
```

Only E1 can be allocated. Same-OperationId pre-dispatch replay reconciles the
same durable epoch/TurnRef without another provider call; a different operation
cannot create E2 or a second same-generation turn.

The sole second turn is a freshly TX-4-admitted same-epoch G2 after the exact G1
pre-candidate process-loss predicate: one matching TX-5 INTENT+APPLIED pair, no
`EFFECT_UNKNOWN`, no checkpoint, candidate, seal, or competing result, G1
`PROVEN_DEAD`, provider writer `RELEASED`, epoch still `CURRENT`, and independent
P1B `resume_safe`/TX-10/TX-11 proof. A G1 candidate of any quality, ambiguity,
live/non-released writer, new epoch, failed recovery, invalid G2 result, G3, or
third turn ends adversely. No model prose, retry wrapper, supervisor flag, or
Attempt budget can widen these limits.

### 5. Terminal evidence and no-fallback law — PASS

Live work must name the current, unended, greatest Executive-writer generation.
After lawful TX-6/TX-8 shutdown, validation and completion use immutable terminal
evidence rather than pretending a historical admission remains work authority.
The qualifying sealed generation must remain the greatest tuple ever allocated,
all writers/current epochs must be absent, required supervisor receipts must bind
the seal, and no later epoch, generation, turn, candidate, or result may exist.

If G2 or another later generation exists, G1 evidence can never be substituted,
even when the later generation refused or failed. `SEALED_WORKER` uses its
equivalent immutable supervisor collection/result, launch/principal, process-death,
grant, validation, and no-competing-result evidence; it does not borrow the OHF
raw-observation protocol.

### 6. Additive schema v4 and exact legacy preservation — PASS

OHF P1B remains the owner of schema v3. Phase 1F-C adds exactly eight nullable Job
columns and six paired Attempt columns. Role-null v1-v3 rows remain null,
cycle-ineligible, and byte/behavior compatible. No historical role, lineage,
grant, placement, principal, admission, or result evidence is inferred or
backfilled.

The closed `mastermind.executive_legacy_content_projection/v1` freezes the literal
v3 columns and primary keys for all eight projected tables, including the
`sqlite_sequence(name,seq)` AUTOINCREMENT state and the exact v1-v3 migration
vector. Every cell preserves its SQLite storage class and exact value. Preflight,
in-transaction, post-migration, completion, backup, and drill proofs all use the
same canonical projection and require exact digest equality.

### 7. Offline migration, rollback, and forward-fix boundary — PASS

Normal v4 startup may create a fresh v4 store or open an exact v4 store without a
barrier. It must inspect and refuse an existing v1-v3 database without WAL mode,
sidecar creation, schema mutation, or auto-migration.

The only populated-store transition is the explicit offline exact-v3-to-v4 path:

1. acquire the existing owner-controlled service/restore lock under the invoking
   control principal and persist the private durable upgrade barrier;
2. prove service stop and no Runtime/supervisor/harness/backup/SQLite writer;
3. checkpoint the quiesced WAL and verify exact v3;
4. take, verify, and read-only drill the v3 backup;
5. persist the closed preflight receipt;
6. revalidate it and run one `BEGIN EXCLUSIVE` migration transaction;
7. prove integrity, normalized fresh-v4 schema parity, and exact legacy-content
   equality before commit; and
8. while the barrier remains, verify v4, take and drill the immediate v4 backup,
   persist completion, and only then make writers eligible.

Failure before commit must roll back and reproduce exact v3 or quarantine.
Anything after an authoritative v4 commit is forward-fix only: no v3 binary,
downgrade, v3 restore over the v4 authority store, deletion of evidence, or
source revert that makes installed code v3-only is permitted.

### 8. TX-9 detached same-Job requeue and canonical quota continuity — PASS

TX-9 itself remains byte- and behavior-semantically unchanged. The narrow v4
branch applies only to a Phase 1F-C orchestration Job whose exact current OHF
Attempt was restore-invalidated. It proves the immutable TX-9 Event, LOST/lease-
null Attempt and Job, abandoned epochs, no Executive writer, remaining Attempt
budget, and the exact invalidated quota state.

Before requeue, the quota must be `ERROR`, unheld, and timestamp-aligned with the
TX-9 Event, and no later Event by `event_id` may name that exact worker/quota. The
scoped Event cutoff covers shipped event-bearing quota transitions without
letting an unrelated fleet Event block recovery.

The requeue Event persists a canonical
`mastermind.tx9_invalidated_quota_snapshot/v1` containing exact worker, quota,
status, holder, fence counter, row version, and update timestamp plus its digest.
The requeue transaction does not mutate the old quota, Attempt, epoch,
generation, or provider-session evidence. The later claim rederives the full TX-9
and requeue chain and matches that quota snapshot field-for-field. Therefore
`ERROR -> AVAILABLE -> ERROR`, release, intervening claim/terminal release,
fence/version/update drift, and flip-back cannot masquerade as uninterrupted
quarantine.

The test law includes the required positive control: a later Event naming the
exact invalidated worker/quota refuses, while an unrelated worker/quota Event does
not. Two-connection quota/requeue/claim races serialize through the same SQLite
write boundary before Attempt creation or provider contact.

### 9. Permanent Phase 1F-C worker-wide TX-9 quarantine — PASS

Every direct claim for every non-null Phase 1F-C orchestration role derives all
workers named by immutable `OHF_RESTORE_INVALIDATED` history. Event and immutable
Attempt worker identities must both exist and match; malformed or mismatched
identity refuses the orchestration claim.

Every quota class of every quarantined worker is excluded before ordinary
capacity routing, regardless of current status, `QUOTA_RELEASED`, alternate
quota, mutable metadata, target Job, or provider prose. A detached continuation
may select only a different, accepted, non-quarantined worker with independently
available matching capacity. A nominally different candidate worker with its own
TX-9 history is also excluded. All derivation, snapshot comparison, routing, and
claim writes occur in one transaction before an Attempt, dispatch marker,
process launch, or provider call.

V1 defines no typed process-absence or slot/host-reset receipt, so this Phase
1F-C quarantine is permanent. Generic role-null P1B TX-9 continuation and a
future reviewed reset receipt are explicitly outside the commission. The new
claim fence does not relax, repair, or reinterpret ordinary role-null P1B.

### 10. COO state machine, authority, lineage, and aggregation — PASS

The final law retains the strict v1/v2 CEO-intent boundary, exact policy home and
nine-field policy block, depth-one Runtime gate, bounded logical fan-out and
reservation arithmetic, immutable revision lineage, binary review verdicts,
different-worker review floor, exact-ID dispatch, deterministic command replay,
closed adverse precedence, and real fresh aggregation Attempt.

The cycle is one explicit run-once bookkeeping command. It performs at most one
top-level mutation class, never scans or falls back to another Job during
dispatch, calls no model in-process, creates no scheduler/daemon/lease store, and
cannot synthesize worker completion. Root completion remains an ordinary fenced
worker `complete_job`/`JOB_COMPLETED` transaction after all aggregation refusals
pass.

## Implementation authorization and required proof

This PASS opens only the commission's separate inert implementation lane. The
builder must implement the exact source law without expanding its surface and
must produce all deterministic acceptance evidence named by the commission,
including:

- exact v4 fresh/migrated schema and legacy-content equality;
- direct Runtime bypass and command-collision refusals;
- typed principal, TX-4 atomicity, crash, replay, and successor-generation tests;
- complete raw-result transport, containment, secret/canonical refusal, and
  lossless multi-block round trips;
- E1/TX-5/G1-to-G2 cardinality and provider-before-gate refusal tests;
- work-closed, TX-6/TX-8, greatest-generation, and no-fallback terminal tests;
- exact TX-9 detached requeue, canonical quota snapshot/digest, exact-worker/
  quota Event cutoff, unrelated-Event positive control, flip-back continuity,
  global cross-Job/all-quota worker quarantine, malformed identity, candidate-
  with-own-TX-9, two-connection race, and post-claim replay tests;
- exact-version read-only backup/drill, exclusive migration, rollback-to-exact-v3,
  post-commit barrier/quarantine, and forward-fix tests; and
- focused/full CI, independent implementation review, and truthful delivery
  receipts.

Green deterministic tests will prove only the inert implementation. They cannot
be called provider readiness, Phase 1C-A PASS, production dispatch acceptance,
or Phase 1F-C live acceptance.

## Operational gates — all pending

The following remain mandatory and unpassed at this review point:

- **G0:** merge all intended source and acceptance code, freeze one clean exact
  `origin/master` release SHA, and prove ancestry from P1B and this PASS.
- **G1:** exact-SHA install with services stopped; company-bound provider readiness;
  Git handoff Gate B; formal Phase 1C-A acceptance; and completed v3-to-v4
  preflight, migration, backup/drill, legacy-equality, TX-9, quota-continuity, and
  global-worker-quarantine evidence.
- **G2:** accepted builder/reviewer capacity with distinct worker IDs, OS
  principals/UIDs, provider homes, and account labels; neither worker may have
  TX-9 history under the v1 no-reset rule.
- **G3:** independently accepted Fable/COO planner principal and one authenticated
  bounded planning receipt.
- **G4:** separately reviewed post-Phase-1C-A production exact-ID dispatch service.
- **G5:** the complete Sol-to-COO-to-worker-to-independent-review-to-fresh-
  aggregation-to-readback live receipt.
- **G6:** the complete adverse live proof, including independence VOID,
  repair/stale-approval, exhaustion, exact dispatch containment, and TX-9
  quarantine behavior.
- **G7:** independent live-packet adjudication; `production_armed` remains false
  until a later explicit Chairman/CEO operating-envelope decision.

No merge, deployment, health result, fixture run, provider-readiness receipt, or
Phase 1C-A result may be substituted for any later gate.

## Final verdict

**Commission SHA-256
`ff141dadcf5e9972cfc307e844c4bd998cb268d3adf8b7e4cfa20b793f201812`:
PASS FOR INERT IMPLEMENTATION ONLY. P0=0, P1=0, P2=0.**

Every prior design blocker is closed in source law. Implementation and all
operational/live gates remain pending. This review makes no provider, host,
migration, deployment, live-planner, production-dispatch, live-vertical, or
production-arming claim.

## Deviations

- No commission byte was edited during this review update.
- No implementation/config/runtime/provider/credential/service/host/database/
  deployment state was changed.
- The only durable write was this explicitly commissioned independent review
  artifact.
