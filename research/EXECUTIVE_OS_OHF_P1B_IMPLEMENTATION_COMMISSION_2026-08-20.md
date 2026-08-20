# Executive OS OHF-P1B Implementation Commission

**Commission:** OHF-P1B
**Authority:** Chairman Chris, delegated to the AI CEO for end-to-end execution on 2026-08-20
**Original accepted base:** merged `origin/master` commit `18eb956a7dac0edca6870a39887a964b66c53d72`
**Reconciled delivery base:** `49c363a8b95d368aab249eff75b4d371cdc59c6c` (provider-readiness PR #92)
**Contract:** `mastermind.operator_harness/v1` in `control_plane/operator_harness_contract.py`
**Status:** commissioned for implementation, review, merge, inert code deployment, and live deployment proof

## 1. CEO ruling

OHF-P1B implements the accepted OHF-P1A-R3.3 constitution as a real but
production-inert Executive OS execution substrate. It includes:

1. Executive schema v3 and the durable OHF identity/writer plane;
2. atomic Executive runtime APIs for TX-1 through TX-11, including offline
   restore invalidation;
3. provider-neutral orchestration against the frozen `OperatorHarnessAdapter`;
4. the first real `CodexOperatorAdapter`, unregistered and unrouted; and
5. fake-server proof plus one isolated, read-only laboratory canary if every
   isolation gate is satisfied.

This commission does not revise P1A, reopen its settled cardinality or
transaction law, or create a second control plane. Where the frozen law leaves
ordinary persistence mechanics unspecified, P1B may use private, versioned,
deterministic encodings and existing Event payloads without adding public
contract types.

## 2. Authority boundary

Executive SQLite remains the sole organizational lifecycle authority. The
adapter owns provider transport and returns typed observations. The supervisor
or subordinate orchestrator adjudicates them. Only the runtime mutates Jobs,
Attempts, session epochs, process generations, leases, fences, quota, or Events.

Provider completion is candidate evidence. It is never Executive Job
completion. An adapter may not allocate Executive identities, decide
`LaunchDecision`, certify writer safety, release quota, mark an Attempt `LOST`,
or complete a Job.

## 3. Required implementation

### 3.1 Schema v3

Extend the existing atomic migration chain with
`ohf_session_epochs_and_process_generations`:

- add only `attempts.execution_mode`,
  `attempts.requested_execution_profile_json`, and
  `attempts.requested_execution_profile_digest`;
- add `harness_session_epochs` and `process_generations` exactly within the
  accepted additive P1A schema;
- use the existing `events.command_id` plane for OperationId INTENTs and derived
  receipts; and
- enforce immutable modes/profiles/bindings, one current epoch, writer
  cardinality, provider-session realm uniqueness, complete process identity,
  and canonical parent projections at the database and service boundaries.

Historical `execution_mode IS NULL` means `SEALED_WORKER`. Rich OHF never writes
the legacy Attempt-level PID, process-start, boot, or provider-session fields.

### 3.2 TX-1 through TX-11

Implement every frozen transaction group inside the existing
`BEGIN IMMEDIATE` runtime boundary. State and its Event receipt commit together.
Replays reconcile through the existing unique Event command-id plane.

- TX-1 seals the requested profile before a provider call.
- TX-2 durably reserves the first epoch/generation and pre-bind writer before
  `start_session`.
- TX-3 immutably binds S1 and records G1 process identity.
- TX-4 seals observed attestation and derives `compare_launch`; turns remain
  forbidden until `ALLOW`.
- TX-5 allocates and persists the Executive `TurnRef` INTENT before
  `begin_turn`; ambiguous missing application remains `EFFECT_UNKNOWN`.
- TX-6 clears Executive writer authority only after confirmed graceful stop.
- TX-7 records hard process death without inferring either writer release.
- TX-8 abandons a poisoned epoch only after process absence is proved.
- TX-9 invalidates restored active OHF authority before service re-enable while
  preserving historical provider/process evidence.
- TX-10 reserves G2 on the already-bound S1 only after G1 is proven dead,
  provider writer state is `RELEASED`, and resume safety is derived true.
- TX-11 validates the exact typed resume target, binds G2 process identity, and
  appends APPLIED without creating an epoch, rebinding S1, or consuming another
  Attempt.

TX-2's pre-bind Event payload may truthfully carry a null provider session.
TX-5's Event payload may carry the frozen `TurnRef` fields. The frozen typed
`OperationIntentTarget` remains mandatory for TX-10/TX-11. Requested and
observed profile persistence uses compact sorted JSON with enum values and
SHA-256 as a private, versioned encoding.

### 3.3 Provider-neutral orchestration and Codex

Consume the frozen adapter protocols without widening them. Implement an
unregistered `CodexOperatorAdapter` with:

- exact Codex executable/version/digest observation;
- a dedicated `CODEX_HOME`, without copying, symlinking, or reading credential
  bytes;
- requested/observed separation for model, sandbox, approval, network,
  workspace, configuration, skills, MCP, plugins/apps, and auth realm;
- generation-scoped normalized events and cursors;
- strict process/session separation;
- graceful stop with honest provider-writer observation; and
- resume only through `ProviderSessionHandoff` for the already-bound S1.

The adapter must not steal a writer, delete locks, adopt old stdio, allocate
Executive IDs, import lifecycle mutation APIs, or directly complete Jobs.

## 4. Acceptance

Acceptance requires:

- fresh v3 creation and realistic v2-to-v3 atomic migration;
- legacy sealed-worker behavior unchanged;
- database-enforced identity, immutability, writer, and realm invariants;
- successful, refused, replayed, concurrent, and crash-window SQL tests for
  TX-1 through TX-11;
- TX-9 restore proof with truthful pre- and post-invalidation hashes;
- fake App Server end-to-end proof from profile seal through graceful stop;
- fail-closed tests for drift, conflict, missing/mismatched session,
  quota/rate-limit, process crash, ambiguous external effect, and restart;
- structural proof that no production configuration selects the adapter;
- an independent exact-head architecture/security review; and
- focused tests, full repository CI, CodeQL, `git diff --check`, and a clean
  scoped diff.

A read-only live canary is permitted only in a temporary runtime database,
temporary exact-SHA workspace, and dedicated laboratory Codex home. It must be
bounded, write-incapable, non-production, sanitized, and prove that no Executive
writer remains. Failure to meet an isolation gate cancels the canary; it does
not authorize a weaker or production-adjacent substitute.

## 5. Explicit non-goals and holds

P1B does not include:

- production worker registration, routing, enable flags, or service arming;
- a write-capable canary or production Job execution through OHF;
- Phase 1F-C, Browser/DevServer Resource Fabric, account/capacity pools, or
  another provider adapter;
- a new queue, scheduler, database, lease store, operation ledger, authority
  registry, MCP authority, or credential administrator;
- writer-steal, old-App-Server-stdio adoption, host-reboot safety claims,
  multi-host identity, or native helpers for write-capable profiles; or
- any claim that deployed code or a migrated schema makes OHF operational.

The surviving P1A gates continue to prohibit write-capable Codex use and
production activation until a later exact-head acceptance and explicit Chairman
authority.

## 6. Delivery and rollback law

The owning session carries this commission through commit, push, one ready pull
request, concluded-green CI, independent review, squash merge, exact merged-SHA
deployment through `scripts/deploy_from_git.sh`, and `/health` plus deployed-SHA
verification.

Code deployment is not production arming. The final receipt must report
separately: merged schema-v3 code, deployed schema-v3 code, authoritative
Executive database migration state, adapter implementation state, laboratory
canary state, routing/registration state, and production arming state.

Schema v3 is forward-fix after migration. A v2 binary must refuse a v3 database;
disabling OHF is not schema rollback. Before an authoritative database is first
opened by v3 code, its existing operational lane must quiesce the service, take
and drill a verified backup, and prove no active/unreconciled OHF writers. This
commission does not invent a new Executive-host rollout lane when none exists.
