# Native Hermes request and tool observations

## Original owner and receiving path

The native gateway retains bounded request-content, offered-schema, tool-callback
and result-commit observations in the original admission's terminal result. The
selected Hermes revision is `1c0cd667746d3395fe9e1b6c74f8f85952486f18`.
The existing held-release source closure, admission, pending result, terminal
codec and authenticated `read_original` remain the owners. There is no new
queue, session, memory store, credential, transport, retry or EVAL publication.

1. Native `SessionAuthority._stamp_claim` stamps the original live claim.
2. The qualified ingress wrapper establishes the existing admission-local
   `ContextVar`. Native executor/thread-context helpers propagate it.
3. The original request builder calls its module-global pre-request hook.
   The wrapper invokes that hook once, then digests the content and tools.
4. The original `_dispatch_authorized_once` still runs all scope, plugin,
   pruned-argument and guardrail gates. Its wrapped callback records actual entry.
5. The original `_commit_tool_result` still appends and flushes the native
   tool result. Its wrapper observes the return without retaining the body.
6. Native ingress creates `pending_results[admission_id]`. The wrapper seals
   and attaches metadata to this original outer record before claim retirement.
7. Native preparation, redaction, compaction and codecs retain that metadata.
   The existing original-result reader projects it after the original joins.

Installation occurs once after exact profile/source qualification and before
native main starts. The original API-start callback binds the actual authority
before opening the private listener. Tools-list invocation does not install it.
A stale source, module origin, function-global binding or duplicate installation
refuses startup before wrappers are mutated.

## Versioned evidence

Outer result key: `mastermind_request_observation`.

Current schema: `mastermind.hermes_request_observation/v2`. Historical v1
remains readable in its exact original form; no empty v2 tool facts are invented.

### Request content and offered schemas

Each request observation selects the presence-sensitive `messages`, `input`,
`system` and `instructions` fields after the pre-request hook. The declared
content stage remains `assembled_content_after_pre_request_hooks`.
Strict JSON is detached and hashed with UTF-8, sorted object keys, no
insignificant spaces, no ASCII escaping and no nonfinite numbers.
`json_sorted_keys_utf8_no_spaces_v1` names this representation; it is neither
RFC8785 nor a provider wire digest. Whitespace and Unicode are preserved.

The content record contains its SHA-256, encoded byte count, selected field names
and bounded original request/turn/count identifiers. Physical agent session
labels may differ from the authoritative logical session.

V2 adds `tools` with status `absent`, `observed`, or `unavailable` plus a
closed reason. An observed value contains its JSON kind, complete-value digest,
byte count and canonicalization. Missing, null and an empty array are distinct.
Unsupported or oversized tools do not erase valid content evidence.
`tools_stage` is `assembled_tools_after_pre_request_hooks`. This is the exact
aggregate value at that seam, not a registry digest or per-tool EVAL mapping.
Later execution middleware can alter or synthesize a request.

Raw prompts, schemas, headers, credentials, outputs, reasoning and arbitrary
request metadata are never retained. Both `provider_dispatch_proven` and
`model_identity_verified` remain literal false. Content coverage remains
`assembly_hooks_only`, or `no_assembly_observation` if none was retained.
Neither claims complete native path coverage or absence of model calls.

### Tool execution and commit returns

Separate `executions` and `commits` arrays belong to the same transient scope
and outer result. Each retained record gets a shared, increasing observer-local
`sequence`. It is not a provider ID or durable command identity.

Identity admits only present, valid `agent_session_id`, `turn_id`,
`api_request_id`, `task_id`, `tool_call_id` and `tool_name` labels.
Missing labels remain missing. Invalid selected fields are named without their
values. No raw native ref, argument, return body or exception text is retained.

An execution record is created inside the supplied callback, after the original
native gates. State is `entered`, `returned` or `raised`. An `entered`
record at sealing means no terminal observation was retained; it does not prove
a worker remains running. The donor's `dispatched` flag is set before some
refusals and is deliberately not treated as callback-entry evidence.

A commit starts as `pending`. Its qualified original three-element tuple return
becomes `commit_tuple_returned`; None becomes `commit_none_returned`; an
exception becomes `raised`; any other shape is `unrecognized_return`.
These are literal return facts, not proof of durable persistence. The pinned
flush helper treats any value other than False as success, but the persistence
owner returns None when persistence is disabled or the session DB is absent.
Thus even a normal tuple can follow a no-op persistence call. A None return or
exception also cannot prove that no write or external effect occurred.
Typed `blocked`, `is_error` and `reported_effect_disposition` are native
reports. The latter is null, `none` or `unknown`; sequential blocked
commits may legitimately carry null. Handler return, non-error classification
and durable result are separate from proof of an external effect.

Sealing correlates only a unique complete six-label tuple in both arrays, with
execution sequence preceding commit sequence and no relevant coverage gap or
adopted-agent-object change. Duplicate identities, incomplete labels, invalid
order and missing callbacks remain explicit and unjoined. Tool-count/byte
overflow or observer failure prevents a positive join. The reader independently
checks all structurally verifiable correlation claims.

A unique match associates an observed attempt, not the callback's literal
returned result: native timeout synthesis or transformation may intervene.
Dispatch and commit use different native ref objects; concurrent commit order
need not match callback completion order. A callback updates its own captured
record, never a lookup by tool-call ID.

Middleware can synthesize a result without callback entry. Some native skipped
or invalid-argument results bypass the commit hook. Thus `tool_coverage` is
always `native_callback_and_result_commit_hooks_only`; empty arrays prove no
absence. Existing `mmx_delegate` alone owns its selected-child effect semantics.

## Source custody, races and budgets

The held source verifies the seven complete upstream files in
`native_request_observation.SOURCE_SHA256`. Module origins, original function
globals/source filenames and sync/async signatures are qualified before
wrapping. The bound authority must match the selected profile, instance, epoch,
runner and single-profile descriptor.

Each contribution checks source lifetime, original live session object, claim
stamp, executing generation, drain/retirement and actual adopted agent identity.
Native stored-generation reads occur outside the event-stream lock. Final
currentness and append use event-stream lock followed by scope lock, matching
the original owner. Sealing closes the scope before retention; late copied
contexts cannot change it or contribute to a successor. Native outcomes and
exceptions are never replaced by optional observation failures.

Content/schema work is bounded at 4 MiB encoded bytes, 65,536 visited nodes,
depth64 and exact supported JSON types. At most eight request observations and
sixteen records of each tool kind share a 16 KiB metadata ceiling. Identifiers
are at most256 UTF-8 bytes with control characters rejected.

Reservation uses the same default-spaced, non-ASCII-escaped JSON encoder as
final validation, including quote/backslash expansion. The envelope reserves
4 KiB; each tool record reserves another256 bytes for bounded terminal and
correlation updates. A failed reservation appends nothing and preserves explicit
request/tool/shared-byte overflow flags. A defensive final-size fallback marks
lost coverage rather than silently discarding the entire evidence document.

The observer never creates a missing pending result or overwrites an existing
outer observation key. An agent's same-named inner field is not promoted.
No event observer, extra publication or lifecycle owner changes delivery.

## Authenticated historical read

The existing `read_original` first joins principal, role/profile, session,
submission, input digest and exact original admission. Scope role/session/
admission/epoch/generation must match that receipt. The retained instance is
historical and is not replaced by today's serving process.

Validation bounds containers before traversal and text before UTF-8 encoding,
reconstructs only closed admitted fields, enforces unique ordered observer
sequences and the 16 KiB ceiling, and preserves detached output. Historical
v1 retains its original eight-record overflow invariant. V2 distinguishes count
and byte loss and checks its explicit correlation/coverage relationships.

Malformed, unknown, mismatched or oversized metadata produces only
`request_observation_error: INVALID_RETAINED_OBSERVATION`. The original
answer, outcome, success behavior and terminal metadata remain readable.
Queued, started, unknown or missing original admissions emit no terminal
evidence. Explicit admission lookup must match the requested admission ID
before stored result access.

The serving gateway's `implementation_sha` describes the current reader.
Neither the reviewed-file digest nor that current release is substituted for
historical per-admission process attestation. Digest syntax and owner binding
are validated; raw content is unavailable for recomputation.

## Qualification and remaining acceptance

Complete unmodified MIT donor snapshots, exact source/blob/digest provenance
and the original license are retained as .py.source data. They are materialized
at original module paths before actual body execution. The new tests run the
actual request builder, tool middleware/dispatch/commit bodies, complete native
registry, registered selected-child handler, native thread-context copier,
original ingress/preparation/redaction/codecs and authenticated original reader.

Plugin-policy, heartbeat, provider/Executive transport, environment and storage
edges are explicitly doubled. Tests distinguish all native refusal gates,
middleware synthesis, actual callback exceptions, failed flush, concurrent
completion, duplicate/missing IDs, late workers, shared overflow, secret omission
and malformed optional metadata. Historical v1 reader checks remain intact.
The earlier accepted socket tests are not repeated in the restricted local lane.

These are source/composition tests. They do not establish installed service,
actual provider request, successful account login, model weights, held-out
improvement or full teammate acceptance. The original C26 host-access issue
remains separate. No EVAL draft or validity receipt is manufactured from these
partial observations; complete genuine runtime facts must reach the existing
finalizer, ArtifactStore and memory-grounding scorer.
