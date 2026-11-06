# H24-03 — native attention and schedule boundary

**Source-only implementation; no activation or production-serving claim.**

This packet adds a deterministic, read-only projector from authenticated Hermes
occurrences and current owner evidence to at most one **proposed**, in-memory
canonical Wake obligation. Unchanged observations require no cognition. An
unknown original send stays with the existing reconciliation owner.

## Exact scope and provenance

- Packet: H24-03, Wave 1, bounded Hermes harness builder.
- Repository: `mastermindx-market-intelligence/Mastermind`.
- Immutable build base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437`.
- Branch: `sol/h24-03-attention-schedule-20261106`.
- Protected procedure pin: `32a354c3dd77751e206a80b2abc4e497efdbe5e6`,
  `mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`.
- Upstream: `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.
- Only owned additions: `integrations/hermes_secretary/native_attention_boundary.py`,
  `integrations/hermes_secretary/tests/test_h24_native_attention.py`, this document.

PR #2120, its integration branch, C29–C34 owners, original Wake writers, native
install/service files and `routines/jobs.json` are outside the write set. This
packet adds no release gate. Its completion scope is source, tests and a durable
parent receipt, not release or the parent programme's runtime acceptance.

## Grounded native/Wake comparison

| Existing source at its immutable pin | Consequence for this boundary |
|---|---|
| [Hermes hooks](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/gateway/hooks.py) | Lifecycle callbacks are profile scoped, but their ordinary context is not an authenticated Work/Runtime fact and does not supply the complete retained event identity required here. Hook text is never promoted into authority. |
| [Hermes native watchers](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/gateway/run_watchers.py) | Native housekeeping and stall observation already exist. H24 adds no watcher, loop, reconnect poll or daemon. |
| [Hermes scheduler](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/cron/scheduler.py) and [execution records](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/cron/executions.py) | Preserve the actual native job ID, execution ID and stored `scheduled_instant`. Do not derive a replacement from `next_run_at`, reception time, Slack text or a fresh UUID. |
| [Native occurrence semantics](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/cron/occurrences.py) | Normalize an aware instant to UTC; reject an ambiguous naive instant. The native owner already owns pending-slot recovery and schedule advancement. |
| [Native scheduler authority](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/cron/scheduler_authority.py) | Possible submission retains the original request/journal. Native unknown executions return reconciliation-required; H24 cannot retry, resume a paused job or recreate the occurrence. |
| [Existing Wake contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/docs/EXECUTIVE_WAKE_FABRIC.md) | `source_kind + source_ref + wake_kind` determine canonical Wake identity. Current session, transport, occurrence-observation time and reconnect generation never rekey it. |
| [Wake schema](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/wake_events.py), [persistence](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/wake_persist.py), [dispatch](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/wake_dispatcher.py), [reconciliation](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/wake_reconcile.py) | Reuse `parse_obligation` and `mint_obligation`. The existing Executive events and durable nudge owner retain atomic admission, delivery, acknowledgement and reconciliation. |

## Seven-routine route table — inert

All seven remain `installed=false`, `enabled=false`, `state=paused`, with local
delivery only in the unchanged catalog. The table is descriptive data; importing
the module registers or schedules nothing. Profile-clock expressions are retained
exactly, not recomputed by this module.

| Routine ID | Existing native schedule/trigger | H24 route when a future owner supplies qualified evidence |
|---|---|---|
| `slack-secretary-ping-scan` | `12,42 * * * *`, America/Cancun | Actual native occurrence -> current canonical `agent_dialogue_attention` -> proposed Wake; ordinary Slack text yields none. |
| `overnight-three-room-sweep` | `34 * * * *`, America/Cancun | Same canonical dialogue source boundary; duplicate attention coalesces across later observations. |
| `blocked-hold-listener` | Slack keyword `BLOCKED`; no cron expression | **Unsupported.** A keyword or authenticated payload flag cannot authorize attention. Requires a genuine authorized source adapter; never substitute cron. |
| `chatgpt-browser-session-watcher` | `5,35 * * * *`, America/Cancun | Current owner-qualified dialogue attention only. No browser actuation, session wake, tab selection or recovery attempt is implemented. |
| `codex-usage-reset-watcher` | `30m` native interval | No canonical Wake source in this catalog. Ineligible for a new H24 proposal; no account switching or credential operation. |
| `m2studio-browser-tab-sweep` | `40 2-23/3 * * *`, America/Cancun | No canonical Wake source in this catalog. Ineligible for a new H24 proposal; no tab operation. |
| `codex-continuity-audit` | `20 */2 * * *`, America/Cancun | Current canonical dialogue attention only. No drift-check execution or relaunch. The catalog's Denver summer/standard-time distinction remains explicit. |

Generic qualified lifecycle observations may carry existing Runtime
`review_required` or Inbox attention as well as Agent Dialogue attention. A named
routine remains constrained by its table row. H24 adds no new Wake source kind.

## Typed read-only API

`project_native_attention(notice, source=..., binding=..., now=...)` performs one
authentication callback and one bounded current-owner read. There is no default
adapter, credential lookup, model function, CLI, timer or automatic invocation.

The trusted host injects `AuthenticatedAttentionSource`:

1. `authenticate(notice)` verifies the actual native source and returns a
   `NativeObservation`, or refuses it. It cannot infer trust from
   `authenticated=True`, `owner_verified=True`, a Slack actor, message text or a
   caller-supplied source-reference string.
2. `read_current(observation)` reads the retained native occurrence, current
   role/session/source binding, Work/Runtime eligibility, canonical typed
   attention and original Wake effect evidence. A failed read is not absence.

The host-supplied expected `NativeBinding` freezes profile, role, original root,
session UUID, generation, exact Mastermind source revision, Hermes pin and profile
timezone. `BUILD_BASE` documents the build input; the active source revision must
be the real immutable host build, verified by the host, not a branch name or a
claim from the event. H24 checks equality and closed types; it does not implement
a competing authentication or source-attestation service.

`NativeOccurrence` retains its original binding, actual occurrence ID, event name,
exact positive native event sequence, timestamp and expiry. A cron occurrence
also retains the native job ID and aware scheduled instant. `cron:occurrence` is
this adapter's typed label for a retained execution row, **not** a claim that
upstream HookRegistry emits a cron hook with that name.

`CurrentAttention` separately carries the original canonical source-event
sequence and its current read watermark. For Runtime attention, the original
sequence must match the sequence encoded in `runtime:job:<JOB-ID>:<sequence>`.
Native and canonical streams are distinct. A newer watermark may cover a missed
older event; equality to the newest snapshot sequence is deliberately not required.
The existing source owner must verify the opaque Inbox/Dialogue reference's
correspondence to its exact original event.

The source read must be coherent and current, with known role qualification and
known Work **and** Runtime eligibility. Unknown eligibility refuses a proposal;
ineligible observations cannot produce a fingerprint that suppresses later
eligibility. No attention means no proposal. Snapshot freshness defaults to 300
seconds and checks both read age and expiry window; event expiry stays with the
original occurrence. There are no clock reads inside the projector.

## Identity, coalescing and recovery

Native identity and canonical attention identity are separate:

- Hook identity retains profile, original root/session/generation, original
  event ID and exact sequence. Snapshot recovery does not insert the new
  observing session into that identity.
- Cron slot identity is profile + native job ID + canonical UTC scheduled
  instant. The original execution ID remains on the occurrence even when a
  repeated observation refers to that same slot.
- Canonical Wake identity comes unchanged from incumbent `mint_obligation`.
  Later cron fires observing one unresolved source do not create new Wake IDs.

The semantic fingerprint covers validated canonical attention meaning and
correlation, excluding emission/observation times, evidence rendering, reconnect
metadata and native tick changes. Deduplication pairs native occurrence identity
with canonical source identity. The same occurrence/source claiming conflicting
meaning is refused; the same meaning on a later tick returns `NO_CHANGE`.

`SemanticEvidence` is optional prior evidence from the existing owner, not a
durable cursor, lease or send lock. H24 neither stores it nor advances any owner
watermark. A future consumer must not mark a proposal consumed merely because
it rendered a fingerprint: first hand it to incumbent canonical admission and
reconcile that outcome. If a read/projection is interrupted before admission,
discard the optimization hint and recover from canonical source/effect evidence.
Do not create a new store for this cache. Loss of a cache after restart cannot
erase an existing canonical effect.

Live-event observations from an old session generation fail. An authenticated
`SOURCE_SNAPSHOT` may carry an earlier original generation only when the current
owner independently returns the identical retained occurrence, under the current
qualified binding and original root. This is read recovery, not source-writer or
runtime-custody transfer. Expired events remain expired.

All civil-time decisions stay with native Hermes. Offset-equivalent timestamps
normalize to the same slot; repeated DST wall times with different UTC offsets
remain different slots. The boundary does not evaluate cron expressions or
recompute a missed event from local time.

## Effect contract and the one composition owner

**Composition responsibility: the incumbent Executive Wake source-admission owner
for the authenticated Hermes role.** It composes the existing native role host
and native event/cron readers with its current Work/Runtime source admission and
existing Wake persistence/dispatch/reconciliation. This names a capability owner,
not an invented live operator, new service or parallel scheduler. The receiving
parent assigns the actual eligible implementer within its existing owner paths;
H24 does not enter PR #2120 or C29–C34's exclusive write sets.

The contract distinguishes the following facts:

| Observation/result | Meaning |
|---|---|
| `PROPOSED` | One schema-valid, in-memory obligation. It is not a persisted `WAKE_REQUESTED`, dispatch, delivery, model turn or accepted runtime action. |
| `NO_CHANGE` | Unchanged qualified meaning or an original effect already admitted. No new cognition or submission. |
| `INELIGIBLE` | Current evidence supplies no qualifying attention or the routine has no Wake source. |
| `REJECTED` | Authentication, source/currentness, identity, expiry, eligibility knowledge or schema cannot be established. No automatic retry. |
| `RECONCILE_REQUIRED` | Native execution is unknown, or the original Wake effect may have been sent. Keep that original execution/occurrence/command. |

An **owner-proven `ABSENT`** effect read is required before any new proposal.
`REQUESTED`, `DELIVERED` and `RESOLVED` do not become fresh work after a restart.
`POSSIBLE_SEND` and `UNKNOWN` preserve the exact original effect even if the
observation came from a later cron fire, process generation or source build.
Native cron unknown returns its retained original execution for the native
`scheduler_authority.reconcile_pending` path; the boundary invokes none of it.

**At-least-once observation is not exactly-once execution.** Concurrent read-only
projections can both render the same canonical ID. The existing Wake owner must
fresh-read eligibility/currentness and atomically admit the original request and
durable nudge before any external effect. Its existing dispatcher guarantees
at-most-one provider submission per durable nudge identity. H24 cannot enforce a
distributed send lock and provides no retry counter, replacement occurrence or
effect-submission API. Both `new_cognition` and `new_submission` are always false.

### Remaining host-adapter prerequisites

These are downstream implementation/qualification facts, not H24 release gates:

1. Actual qualified `mmsecretary`/`mmmeta` role custody and current native
   session/generation/root/source binding through the incumbent host. A static
   fixture is not proof of that qualification.
2. A bounded authenticated hook adapter that joins callbacks to the native
   owner's retained original event ID/sequence. A plain HookRegistry context
   cannot satisfy this; unsupported contexts must remain rejected.
3. Native cron execution/slot reads and native unknown-effect reconciliation
   using the original owner. Never install a cron job or generate an execution
   ID merely to feed this projector.
4. Coherent current Work/Runtime eligibility and exact original Wake effect
   reads, plus the existing atomic persistence/dispatch owner for later effects.
   Missing or pruned effect evidence must not be called `ABSENT`.
5. After separately authorized role composition, a real event-to-source-to-Wake
   owner proof, including unknown send and restart. H24's static tests establish
   the boundary only; they do not establish production attention or serving.

## Validation and non-activation receipt

The test file contains a static native hook-context fixture, a static selected
cron execution-row fixture and an explicitly injected, no-network owner double.
The double authenticates only its exact fixture object. It is not an auth
implementation and cannot be installed as the host adapter.

Acceptance coverage includes duplicate and delayed events; reordered source
resolution; missed-event recovery with newer watermarks; original identity across
restart; explicit DST offsets and profile-zone representations; stale, foreign,
unqualified and unauthenticated observations; forged Slack `BLOCKED` payloads;
unchanged snapshots; one qualified proposed obligation; no retry/rekey after
possible or unknown sends; and 32 concurrent projections with one canonical ID.
Additional tests cover exact Runtime sequences, immutable source drift, malformed
schema, unavailable effect reads, ineligible-to-eligible transitions, all seven
catalog routes, sanitized adapter exceptions and absence of write/process paths.

Commands run from the repository root:

```sh
python3 -m unittest integrations.hermes_secretary.tests.test_h24_native_attention -v
PYTHONTZPATH='' python3 -m unittest discover -s integrations/hermes_secretary/tests -v
python3 -m compileall -q integrations/hermes_secretary/native_attention_boundary.py integrations/hermes_secretary/tests/test_h24_native_attention.py
git diff --check
```

Results at this source checkpoint: **48 focused tests passed**; **123 complete
secretary tests passed**, no failures/errors/skips; both compilation and whitespace
checks passed. Python is 3.12 in this test environment.

The first broad run with the OS timezone database exposed an existing catalog
fixture mismatch: OS IANA **2025b** falls Vancouver back to UTC-8, while the pinned
catalog expects **2026e** and UTC-7. The already-installed Python `tzdata` **2026.5**
contains IANA **2026e**. `PYTHONTZPATH=''` selects it for that test process only.
No package was installed, no system clock/configuration was changed and no catalog
or incumbent test was edited to obtain a pass. The new boundary does not calculate
recurrences, so its explicit-instant tests also pass with the OS database.

The owned diff contains only the three additions listed above. The unchanged
catalog SHA-256 is
`7a3b7242c1cc97e3868174d97311c7e62262f0e940db3ba098a4c43c10ee4841`.
No native profile/home, cron job, service, Runtime database, Wake ledger, Slack
transport or provider credential was opened for activation or modified. Tests use
existing temporary fixture resources; no production owner is instantiated by the
new module. Existing `install_into_hermes_home()` refusal remains unchanged.

The source commit message records the immutable base, exact owned-patch checksum
and final test receipts. The parent return carries that commit/head and remote
readback. Reproduce the owned diff checksum with:

```sh
git diff --binary --full-index --no-ext-diff b54cb10e4abdd3766c62d4088f6a576ecfe80437 HEAD -- \
  integrations/hermes_secretary/native_attention_boundary.py \
  integrations/hermes_secretary/tests/test_h24_native_attention.py \
  docs/hermes/H24_NATIVE_ATTENTION.md | sha256sum
```

H24-03's source outcome is complete once that exact branch/head is published and
read back. The parent harness integration and production qualification remain
separate, unclaimed work. No merge, self-approval, install or activation is part
of this packet.
