# H24-09 — Native context and original-result continuity

**Source-only delivery.** This packet provides a closed immutable manifest, a
validator and a pure original-result recovery projection. It does not restore a
live session, admit work, change a native context, consume a result or activate a
service. The existing host and Runtime owners remain the only acquisition and
effect boundaries.

- Packet/branch: `H24-09` / `sol/h24-09-continuity-20261106`.
- Immutable implementation base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437`.
- Procedure pin: protected `master@88a8b103a5a69e4b4e870a184655dde9fd5875c3`,
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

The public source functions are:

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

The normalized full H24-09 envelope is not yet an installed/public owner endpoint.
Its future host composition must supply owner-authenticated facts and retain this
artifact through an existing permitted artifact/checkpoint home. If a required
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

Recorded source-fixture results with Python 3.12.14:

| Command | Result |
| --- | --- |
| First H24 unittest command above | 75 tests, 1.364 seconds, `OK`, exit 0. |
| Second H24 unittest command above | 75 tests, 1.406 seconds, `OK`, exit 0. |
| Incumbent native-dialogue unittest command above | 22 tests, 0.042 seconds, `OK`, exit 0. |

The second H24 run is an intentional no-write repeat. This source-only proof
does not exercise a live gateway restart, real parent conversation, provider,
service installation or production restore. Exact terminal counts/results and
the owned diff checksum are recorded in the parent checkpoint for the published
head; no CI/production result is inferred from these source fixtures.

The attempted combined adjacent-suite command also included
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
