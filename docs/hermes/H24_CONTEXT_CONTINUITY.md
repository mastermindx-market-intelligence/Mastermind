# H24-09 — Native context and original-result continuity

**Source-only delivery.** This packet provides closed owner-return constructors,
an immutable manifest, a validator and a pure original-result recovery projection. It does not restore a
live session, admit work, change a native context, consume a result or activate a
service. The existing host and Runtime owners remain the only acquisition and
effect boundaries.

- Packet/branch: `H24-09` / `sol/h24-09-continuity-20261106`.
- Immutable implementation base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437`.
- Continuation procedure pin: protected `master@609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1`,
  `mastermind.sol_skillpack.v1`, skillpack `1.0.1`, bootstrap major `1`.
- Scope: the new `checkpoint_projection.py`, its new
  `test_h24_checkpoint_projection.py` and this document only.
- Concurrent Chairman placement is the assignment. No H24-01/H24-06 wave seal is
  required for this disjoint source packet. C31 and the existing Y7 audit remain
  separate owners. PR #2120 and C29–C34 receive no source changes from this branch.

## Useful capability and limit

A Secretary or Meta-CEO host can retain compact context identifying one original
request, then compare newly acquired owner facts to that context. The output
selects the exact original result reference, pending/uncertain original request,
historical evidence or a refusal. All outcomes have `can_write=False` and
`can_resume_execution=False`.

The host can recover a retained answer through the incumbent read route even
after gateway restart or writer cleanup. A summary cannot recover an absent
answer, prove a grant, select a replacement Attempt, recreate a prompt or adopt
another session. Model context compaction and Executive acceptance are independent.

## Grounded owner comparison

All Mastermind links in this section name the immutable implementation base.
Upstream is the pin declared in
[`integrations/hermes_runtime/constants.py`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_runtime/constants.py):
`NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

| Existing owner | Observed contract | H24-09 use |
| --- | --- | --- |
| [Hermes `gateway/session_authority.py`](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/gateway/session_authority.py) | Native profile/session, instance, authority epoch, runtime revision and execution generation; startup calls `begin_runtime_epoch` and native admission recovery. | Preserve original identity. A later gateway epoch is not a new request. Optional current target observations must be internally consistent. |
| [Hermes `hermes_state_worker_context.py`](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/hermes_state_worker_context.py) | Constructor context and sidecars remain inside the worker receipt transaction; identity/lineage remain reserved. | Reference owner-produced context metadata only. Do not call the context mutation functions or copy their prompt/session rows. |
| [Hermes `agent/context_compressor.py`](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/agent/context_compressor.py) | Model summary/context handling, stale-held-history checks, archive watermarks and partial-summary refusal. | Track an optional owner checkpoint reference and compaction generation. Never treat model summary output as an admission or accepted result. |
| [Hermes `tools/checkpoint_manager.py`](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/tools/checkpoint_manager.py) | Filesystem snapshots/rollback in a shared shadow Git store. | Not conversation recovery; not imported, invoked or duplicated. |
| [Native continuation projection](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/native_continuation.py) | Immutable original request/binding, source/root evidence, derived operation/read/submission identifiers. Hermes direct-root request events have no Attempt; native continuation requests require their original Attempt. | Validate the original identifier derivations and preserve this distinction. No new Job/Attempt identity. |
| [Hermes SessionBridge result](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/session_bridge/hermes_native.py) | Closed original request/result envelope; the public result always says `parent_consumed=False`. | Retain a digest/reference, never the raw answer. That boolean alone maps to consumption `UNKNOWN`, not a positive consumption or nonconsumption proof. |
| [Native original-reply reader](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/session_bridge/native_read.py) | Authenticated original request/message join, owner-validated semantic fingerprint, text/next-step, committed reply; operation-key echo only when that selector was used. | Use the existing read reference and message fingerprint. Changing lookup form must not change result identity. A PROGRESS reply is not a Job completion or parent-consumption receipt. |
| [Runtime original return](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/session_bridge/runtime_return.py) | `read_hermes` reads original admission/result without live target discovery or a submit guard, then rechecks original event/commit/principal. `_read_request` retains committed provenance after writer cleanup. | The existing `read_ref` remains the only recovery selector. Retained reads gain no new writer/target/lease requirement. |
| [Installed SessionBridge](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/session_bridge/installed.py) | Dispatches original result reads by the stored request schema. | Host-owned acquisition seam; H24-09 registers no tool or alternate reader. |
| [Runtime bounded read receipt](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/executive_runtime.py) | `RuntimeReadObservationReceipt` is valid only after close/finalization. `source_identity` is request-scoped; `before/after` are same-connection `data_version` samples. | Require finalized `SAME` samples. Never use these values as a stable store identity, global event cursor or clock across requests. |
| [Native dialogue consumer](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_secretary/native_dialogue_consumer.py) | Reuses `NativeReplyWriter`; an existing canonical reply avoids a second model call/send. Its result does not prove parent consumption. | The incumbent return writer retains delivery/deduplication ownership. The projection cannot invoke it. |
| [Team integration contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/docs/GROK_SECRETARY_TEAM_INTEGRATION.md) | Result availability, delivery, consumption and acceptance are separate; source fixtures and a disarmed host are not production proof. | Keep separate recorded facts and explicit unavailable metadata. |

Upstream Git blob receipts: session authority
`3bc6c596c77c495c1cf318495a84319c211dd523`; worker context
`e59b9dd2233d5931f91690823dfc84a5185630e6`; context compressor
`de049abd7d8927179d65f79dea8ac0ff00194052`; filesystem checkpoint manager
`140cace15fb8a61061c3c10de7b874363643621f`.

## Closed schemas and trust boundary

The owner-return construction paths are implemented in the same pure module:

```python
# Inputs are supplied by the authenticated incumbent host, after its owner reads.
owner_facts = project_hermes_owner_facts(
    metadata, original_result=qualified_hermes_result,
    runtime_receipt=finalized_runtime_receipt_dict)
manifest = build_checkpoint_from_hermes_returns(
    metadata, original_result=qualified_hermes_result,
    runtime_receipt=finalized_runtime_receipt_dict)

native_facts = project_native_owner_facts(
    native_metadata, original_result=qualified_native_reply,
    runtime_receipt=finalized_runtime_receipt_dict,
    request_message_key=original_request_message_key)
native_manifest = build_checkpoint_from_native_returns(
    native_metadata, original_result=qualified_native_reply,
    runtime_receipt=finalized_runtime_receipt_dict,
    request_message_key=original_request_message_key)
```

These constructors calculate the construction checksum and derive only the
fields supplied by the particular owner return. They never repair a retained
manifest or bypass `validate_checkpoint`. The lower-level API remains available
for an already normalized full owner export:

```python
manifest = build_checkpoint(owner_facts, summary_limit_bytes=512,
                            context_budget_bytes=16 * 1024)
validated = validate_checkpoint(manifest.canonical_json,
                                expected_sha256=owner_retained_digest)
decision = project_recovery(validated, expected_sha256=owner_retained_digest,
                            before=owner_before, after=owner_after, now=host_now)
document = decision.as_dict()
```

`CheckpointManifest` contains immutable canonical JSON bytes. `RecoveryProjection`
is a frozen value. Returned dictionaries are detached copies. There is no callback,
reader, transport constructor, clock read, cache, lock, queue, restore method,
database connection or write method in the implementation.

### Host metadata: `mastermind.hermes_checkpoint_metadata.v1`

Both constructors take a closed dictionary with exactly `schema`, `native`,
`runtime`, `original`, `authority`, `source`, `context`, `parent`, `observation`.
This is a construction input, not a new stored record, permission, service or
public endpoint. The host first authenticates and validates its full existing
owner returns. The constructors validate only the consumed subset and joins.

| Input | Exact source and treatment |
| --- | --- |
| `native`, `runtime`, `authority`, `source`, `context` | Same closed groups as the facts schema below; supplied independently by the respective owners. A public answer does not supply these groups. |
| Hermes `original` | The facts `original` group excluding `commit_status`, `admission_id`, `admission_sequence`, `admission_epoch`, `admission_generation`, `admission_status`. The constructor fills those six fields from the qualified return, and checks target, operation, read/request references, request revision and native-input digest against the supplied original metadata. |
| Native-continuation `original` | The complete facts `original` group. Original Job/Attempt and Runtime commitment remain independently required. Hermes admission fields must all be null. A committed reply does not substitute for Runtime commitment. |
| `parent` | Null for unavailable parent evidence, or exactly `parent_request_ref`, `parent_terminal_ref`, `parent_terminal_sha256`, `consumption_status`, `consumption_ref`, `executive_acceptance`, `acceptance_ref`. Null yields `UNKNOWN` consumption and `NOT_OBSERVED` acceptance, not a negative receipt. |
| `observation` | Exactly `finalized`, `read_state`, `omitted_count`, `observed_at`, `valid_until`, `write_uncertainty`. Actual physical finalization must be supplied by the host; it is not inferred from receipt state. |
| `runtime_receipt` argument | The existing `RuntimeReadObservationReceipt.to_dict()` shape: `schema`, `state`, `source_identity`, `before`, `after`. The constructor maps these to the corresponding facts fields. No receipt or generation is synthesized. |
| Native `request_message_key` argument | The canonical original causal request-message key from the existing resolver; it must match `in_reply_to`. It is not selected from returned text. |

The immutable request revision is the original **Event** digest. It must not be
replaced with the input or request-payload digest. The public Hermes result joins
that revision directly. The native reply wire envelope does not include it; its
host must retain the original Runtime evidence separately.

#### Return mapping and digest domains

| Owner return | Construction result |
| --- | --- |
| Hermes `OBSERVED`, terminal admission, `answer is not None`, boolean `successful` | `RETAINED`; `result_ref` is the existing `read_ref`; digest is SHA-256 of the canonical complete public-result envelope; outcome is SUCCESS or FAILED. Empty answers and failed answers remain retained evidence. |
| Hermes queued/started admission without answer | `PENDING`; preserve original admission and read/request references. |
| Hermes terminal admission without answer | `UNAVAILABLE`; terminal metadata does not reconstruct a missing answer. |
| Hermes unknown admission or absent native result | `UNKNOWN`; recovery reconciles the original request. |
| Hermes `EFFECT_UNKNOWN` | Preserve Runtime commitment and force `write_uncertainty=EFFECT_UNKNOWN`; metadata cannot clear the native uncertainty. |
| Hermes `REFUSED`, `UNAVAILABLE`, `NOT_SUBMITTED` | Preserve the independently returned commit marker; missing native admission yields original reconciliation. Never infer permission to resubmit. |
| Native committed original PROGRESS reply | `RETAINED`; `result_ref` is the existing `read_ref`; `result_sha256` is the existing canonical message `fingerprint`; outcome remains UNKNOWN. Keep Runtime status and parent facts separate. |

The native digest intentionally uses the semantic fingerprint already checked by
`NativeReplyReader`. The optional `operation_key` echo and transport `primary_ts`
do not enter that digest domain. Reacquiring the same reply by operation key and
then read reference therefore yields identical facts. The consumed wire subset
does not contain enough information to independently revalidate the full message
fingerprint; the authenticated incumbent reader remains responsible for that.

Hermes input is bounded to its existing 23 KiB canonical public envelope; native
reply input to its existing 16 KiB envelope. Unicode and permitted line breaks
are accepted at the transient text edge. Answer, completed text, next-step text
and free-form admission outcome are dropped before manifest construction. These
limits are separate from the complete checkpoint budget. An unknown wire schema,
extra field, contradictory flag, wrong original join or oversized envelope fails
with a closed error code. No generic `reply_unavailable` error is converted into
evidence that a request or result does not exist.

#### Principal relationship limit

This version consumes exact Executive-principal fingerprints. The existing
[`read_matches_original`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/installed_principal_read_binding.py)
owner also supports an explicitly installed READ/SEND policy pair whose policy
IDs differ. That pairing is not represented in this checkpoint facts schema.
Such a fingerprint mismatch therefore remains refused even when the incumbent
reader could authorize it. Do not erase policy IDs, hash only the subject, copy
the original fingerprint over the current one, or infer a pair from a successful
read. Supporting that additional projection variant requires an owner-qualified
relationship export preserving both identities. The exact-principal path is
implemented; no general policy-pair compatibility is claimed.

### Owner facts: `mastermind.hermes_checkpoint_owner_facts.v1`

This is a **normalized consumed subset**, not a claim to validate the entire
Workspace, Runtime or native response. An authenticated incumbent composition
must first validate its real owner responses and exact joins, then supply this
closed metadata export. The pure validator cannot authenticate a caller's JSON.
It must not be exposed as a public endpoint accepting model-supplied authority.

| Group | Required fields and meaning |
| --- | --- |
| `native` | `role`; SHA-256 fingerprints of profile, session and native principal; optional current instance fingerprint, `authority_epoch`, `revision`, `execution_generation`. Current-target fields are either all known or all null. Original scope fingerprints remain required. |
| `runtime` | Original `root_id`, `root_job_id`, `work_ref`; original `job_id`, `attempt_id`, `parent_job_id`; current `root_status` and `attempt_status`. Direct Hermes root requests use explicit `NOT_APPLICABLE` with null job/Attempt/parent fields; native continuation requires its original job/Attempt. `UNAVAILABLE` never means absent. |
| `original` | Request kind, original caller fingerprint, target/operation/request/read references, request revision and binding/input digests; native submission/input digest where applicable; commit status and optional original native admission ID/sequence/epoch/generation/status. Native input digest and request input digest are different incumbent domains and are kept separate. |
| `authority` | Current caller fingerprint, existing owner authority generation or null, current `read_permitted`, and separate execution `approval_status` (`CURRENT`, `REVOKED`, `UNAVAILABLE`). An unavailable generation must not be replaced with a caller counter. |
| `source` | Exact repository, immutable 40-hex ref, repository-relative source path and SHA-256. This identifies the owner-qualified commission/input source. Original request/binding digests additionally preserve the original executable binding. |
| `context` | Optional owner message-checkpoint reference/digest and optional compaction generation. These are references, not messages or a copy of the model context. |
| `return` | Result availability/reference/digest/outcome; original parent request reference; optional terminal-return reference/digest; separate consumption status/receipt; separate Executive acceptance/receipt. A pending result cannot also claim terminal return or consumption. |
| `observation` | Runtime receipt schema/state, request-scoped source identity and its sample pair, successful finalization, currentness/omission facts, host observation/expiry times and original-write uncertainty. |
| `snapshot_sha256` | SHA-256 of canonical owner-facts JSON excluding this field. Detects mixed/torn bytes; it is not a signature or grant. |

Fingerprint normalization is host-owned and field-qualified: hash canonical JSON
of `{"field": <owner-field-name>, "value": <owner-value>}` using the same
normalization for original and current facts. Do not expose raw profile paths,
native principal identities, prompt bodies or result text. Reference strings are
bounded opaque tokens, not URLs, executable instructions or paths to dereference.

The manifest schema is `mastermind.hermes_checkpoint_projection.v1`, with exactly
`schema`, `facts`, `summary`, `omissions`. Its expected digest must come from the
existing owner retaining the artifact, not from an untrusted document alongside
its self-computed digest. No new persistence location or checkpoint store is defined.

The validator rejects unknown/missing fields, duplicate JSON keys, noncanonical
byte encoding, malformed digests, partial reference pairs, integer/boolean
coercions, inconsistent native targets, wrong parent joins and contradictory
result/consumption claims. It rejects custom objects and bounded-depth violations.

### Context and budgets

The summary is mechanically generated from closed result, consumption and
acceptance enums. It never accepts arbitrary prose to redact. Truncating this
summary preserves the entire identity/evidence tuple and records exact omitted
bytes. Zero summary bytes is supported. The default is 512 bytes; maximum 1,024.

Facts are bounded at 24 KiB, the complete manifest at 16 KiB, nesting at eight
levels and inspected nodes at 512. A smaller caller context budget is enforced
against the complete canonical bytes. If the required tuple cannot fit, the
whole manifest is refused; no partial identity snapshot is emitted. Generated
summary and exported metadata are ASCII, so the byte budget is exact. Raw Unicode
prompts/answers are not part of this schema; their owner references/digests survive.

Omissions always identify raw prompt, transcript, raw result, secrets, filesystem
snapshot and execution authority as excluded. Optional unavailable metadata is
listed separately. No claim of full event history is made.

## Authoritative recovery algorithm and owner seam

The **host performs acquisition**; this module only evaluates the supplied facts.

1. Read and validate the retained manifest against its owner-retained digest.
   Use its original `read_ref` as a lookup hint. Do not replay any prompt or derive
   a new target from the summary.
2. Through the original installed SessionBridge/Runtime carrier, reauthorize READ
   for the exact original caller and retrieve the immutable request, commit,
   original native admission/result, root/work/Attempt and current root status.
   For Hermes, the incumbent `read_hermes`/native `read_original` path owns this.
   A live native target or surviving writer lease is not required for an already
   committed retained result. Optional target observations must be qualified.
3. Complete owner reads and their physical close/finalization before exporting
   any facts. Recheck caller, source, request/binding, authority generation,
   parent/result references and original-write uncertainty after acquisition.
   Supply both fresh evidence snapshots to the projection. Missing or inaccessible
   evidence stays unavailable; it never becomes proof of nonexecution.
4. Require finalized `SAME` Runtime samples and complete current source facts.
   Different fresh reads legitimately have different request-scoped
   `source_identity` values and incomparable counters. When the same namespace is
   supplied twice, sample values must agree. Persistent identity comes from
   original request/binding/source digests and canonical root/work/Attempt joins.
   These checks do not establish continuous exclusion after the last sample.
5. Reconcile any original submit uncertainty on that original carrier. A summary,
   transport failure or missing active row cannot clear a committed or uncertain
   effect. This module has no retry or reconciliation writer.
6. Recover only the exact retained result reference or return the typed
   pending/evidence/refusal decision below. A separate host read must still use
   its incumbent admission/currentness fences. The projection is not a reusable
   read capability and cannot send, consume, accept or resume execution.

There is no new store-incarnation counter here. If physical source replacement,
rollback, revoked identity or another ABA cannot be resolved by the existing
owner's binding/admission/currentness evidence, that owner must withhold qualified
facts. Equal hashes and request-local counters cannot prove otherwise.

### Operator recovery map

| Situation | Projection | Exact permitted next boundary |
| --- | --- | --- |
| Original terminal result retained, including after a clean gateway restart | `RECOVER_ORIGINAL_RESULT` | Existing original-result READ using the unchanged `read_ref`; no session restoration claim. |
| New epoch/instance with same profile/session/principal and original admission | Original result read remains possible | Preserve the original admission epoch. A known stale current epoch or inconsistent epoch/instance pair is refused. |
| Writer cleanup; no current native target observation | Original retained read remains possible; restart status is null/unknown | Read original provenance. Do not discover/adopt another session to fill the gap. |
| Original result pending | `AWAIT_ORIGINAL_RESULT` | Observe the original request through its existing owner/return path. No polling loop or replacement job is created here. |
| Submit response ambiguous, admission unknown/missing, or commit unproven | `RECONCILE_ORIGINAL` | Incumbent same-request reconciliation/read. No `submit`, resend, fresh Job or fallback session. |
| Child complete; parent not consumed | `RECOVER_ORIGINAL_RESULT` with separate consumption | Existing parent-return owner retains delivery/consumption. Completion alone cannot accept or resend. |
| Parent consumption independently proved | `ALREADY_CONSUMED` | Retain original evidence; no new ACK, send or result consumption. Executive acceptance remains separate. |
| Execution approval revoked/unavailable, READ still authorized | `EVIDENCE_ONLY` | Preserve supplied historical references; no execution continuation selector. |
| READ revoked/unavailable | `REFUSED` | No original/result references escape that evaluation. Reauthorize only through the current owner. |
| Root or Attempt canceled/cancel requested | `EVIDENCE_ONLY` | Retain terminal evidence; no reactivation or execution continuation. |
| Retained result inaccessible/expired | `EVIDENCE_ONLY` / `RETAINED_RESULT_UNAVAILABLE` | Preserve known checkpoint/terminal evidence. The answer cannot be reconstructed from context. |
| Foreign profile/principal/session, wrong parent/Attempt, changed original binding/request/result, stale authority, invalid digest, partial/unfinalized snapshot | `REFUSED` | Obtain qualified original owner evidence; do not repair identity by selecting “latest.” |
| Duplicate notification or parallel evaluations | Same deterministic projection for identical evidence | Multiple read observations are harmless; no local winner, reservation, lock, dedupe ledger or exactly-once execution claim. |
| Context compacted or summary truncated | Context metadata changes; original request and acceptance do not | Use the existing native context owner. No transcript restore or acceptance effect. |

## Required integration owners and unavailable metadata

**C31 owns native gateway/startup and current native selection.** Its unchanged
source seams are
[`native_gateway_entry.py`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_runtime/native_gateway_entry.py)
and
[`native_session_control.py`](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_runtime/native_session_control.py).
The incumbent SessionBridge/Runtime owners linked above own original request,
commit, native result, retained parent return and authenticated current reads.
The existing `NativeReplyWriter`/Dialogue/Wake owner retains any actual delivery;
Agent OS retains organizational continuity. H24-09 supplies no new writer for any
of these facts.

The pure construction path now consumes the real Hermes public result, native
original-reply result and Runtime receipt shapes. The full H24-09 envelope is
not an installed/public owner endpoint. The authenticated host must still supply
the remaining owner facts and retain this artifact through an existing permitted
artifact/checkpoint home. If a required
authority generation or finalized read receipt is not exported, withhold recovery;
do not create a counter or assert availability from this source fixture.

This packet has not acquired live metadata from the disarmed roles. In particular,
the following remain unavailable here: live instance/epoch/revision/generation;
enrolled native session/admission; current principal READ/approval generation;
finalized Runtime observation; native message-checkpoint/compaction watermark;
accessible retained terminal answer; positive parent consumption; and Executive
acceptance. The schema represents optional gaps explicitly and refuses recovery
when required current evidence is missing. `attempt_id=None` on a proven direct
Hermes root request is **not applicable**, not an invented missing child.

No provider, credential, native `state.db`, upstream source, installed SessionBridge
file, wake ledger or production conversation was used or changed by the tests.
There is no install, activation, merge, approval, serving or restored-session proof.

## Acceptance fixtures and verification

The fixture file holds clean restart, compaction and parent/child cases in source.
It covers stale epoch/foreign profile, pending results, ambiguous submit, invalid
digest/partial snapshot, summary truncation, full-context budget refusal, wrong
parent, completed-but-unconsumed child, revocation, duplicate delivery, concurrent
evaluation of one original request, canceled root and retained terminal evidence.
It additionally checks original Attempt applicability, source/authority ABA,
request-local observation semantics, admission/result regression, unknown metadata,
secret/transcript exclusion, immutable copies and contradictory states.

The contract test exercises the incumbent `_request_key`,
`_hermes_operation_key`, `public_result` and `validate_public_result` functions.
Construction fixtures also use the real `RuntimeReadObservationReceipt` and
`NativeReplyReader`, with an in-memory transport that admits only `read_thread`.
They prove operation-key/read-reference equivalence, correct semantic digest use,
Unicode/empty/failed answer handling, missing authority and physical finalization,
original joins, preserved uncertainty, and independent parent evidence. They do
not open a socket, write a native reply or create a Runtime/native database.
The production module imports no Runtime implementation. An AST test verifies its
closed standard-library dependency set and absent write surface. Repeated
evaluation runs with filesystem, socket, process and SQLite entry points blocked.
The parallel fixture performs 24 evaluations on four threads and verifies that
every result names the same original request without changing inputs.

Commands, run from the isolated branch root with Python 3.12:

```bash
python -B -m unittest integrations.hermes_secretary.tests.test_h24_checkpoint_projection -q
python -B -m unittest integrations.hermes_secretary.tests.test_h24_checkpoint_projection -q
python -B -m unittest integrations.hermes_secretary.tests.test_native_dialogue_consumer -q
git diff --cached --check
```

Continuation source-fixture results with Python 3.12.14:

| Command | Result |
| --- | --- |
| First H24 unittest command above | 107 tests, 1.881 seconds, `OK`, exit 0. |
| Second H24 unittest command above | 107 tests, 1.948 seconds, `OK`, exit 0. |
| Incumbent native-dialogue unittest command above | 22 tests, 0.064 seconds, `OK`, exit 0. |

The initial source head `bd7f3288ea8ae98227233ea354f3f0e312c3f825` had 75 H24
cases (two passing runs) and 22 passing native-dialogue cases. This continuation
adds 32 focused owner-return composition and contract cases; the accepted original
fixtures remain in place.

The second H24 run is an intentional no-write repeat. This source-only proof
does not exercise a live gateway restart, real parent conversation, provider,
service installation or production restore. Exact terminal counts/results and
the owned diff checksum are recorded in the parent checkpoint for the published
head; no CI/production result is inferred from these source fixtures.

The initial delivery's attempted combined adjacent-suite command also included
`integrations.hermes_runtime.tests.test_native_session_control`; collection of
that existing module was unavailable because this Python environment has no
`pytest`. No dependency was installed. The incumbent native-dialogue suite is
run separately; the new H24 contract test imports and exercises the real
SessionBridge functions without requiring pytest.

The exact attempted command was:

```bash
python -B -m unittest integrations.hermes_secretary.tests.test_native_dialogue_consumer integrations.hermes_runtime.tests.test_native_session_control -q
```

It exited 1 with `ModuleNotFoundError: No module named 'pytest'`; unittest
reported 23 tests including one loader error. That existing native-session-control
suite is not claimed as validated. No hosted CI run or production proof is claimed.

## Continuation and parent consumption

The Chairman's continuation retains the same H24-09 source branch, original base
and three-file ownership. The added implementation closes the manual construction
gap: both real owner return shapes now have explicit pure fact and manifest
constructors. No endpoint, session owner, result store or acquisition loop is added.
Direct implementation retained the existing builder for the cross-owner contract
judgment and lower whole-cycle overhead. An optional native reasoning collaborator
provided contract advice only; it performed no code, test, provider or external
write labor, and its return was consumed with ACCEPTED/STOP.

The parent [PR #2120](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120)
was observed merged at `28a894186eb56654ab4e833eb11a183d2eed46ae`. Its former
comparison branch `sol/web-meta-ceo-secretary-native-parent-20261106-c18-01`
returned GitHub `NOT_FOUND`. Comparing the initial H24-09 head with protected
`609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1` still includes 98 inherited foundation
commits beyond this packet, because the histories differ. The immutable
`b54cb10e4abdd3766c62d4088f6a576ecfe80437`-to-H24-09-head comparison remains the
authoritative three-file delivery. No replacement integration branch or broad
master-targeting PR was created to disguise that history.

The receiving integration action is to consume the three owned paths and supply
authenticated metadata from the unchanged C31, SessionBridge/Runtime and parent
owners above. Retention belongs to an existing permitted artifact home. The
exact-principal projection is built and source-tested; installed policy-pair
projection, missing live owner metadata, host registration, service activation and
production/browser proof remain outside this packet's permitted source surface.
