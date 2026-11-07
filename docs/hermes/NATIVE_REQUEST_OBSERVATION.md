# Native Hermes request observations

## Capability and receiving path

The native gateway now retains a bounded observation of request content at the
original admission's terminal-result boundary. It uses the selected Hermes
revision `1c0cd667746d3395fe9e1b6c74f8f85952486f18` and the existing held-release
source closure. It adds no session, queue, dispatch, memory store, credential,
provider call, viewer, event subscriber, retry, or EVAL publication.

The actual path is:

1. `SessionAuthority._stamp_claim` stamps the original live claim.
2. `_execute_claimed` invokes `execute_finite_admission`, which imports the
   original `gateway.session_ingress.execute_admission` at call time.
3. The qualified wrapper establishes one admission-local `ContextVar` scope.
4. Native ingress calls the existing message handler. The native
   `_run_in_executor_with_context` carries that scope into the turn executor.
5. `agent.turn_api_request.build_api_request` calls its module-global
   `_fire_pre_api_request_hook`. The wrapper invokes that original function
   exactly once, then digests the selected content fields.
6. Native ingress creates its own outer `pending_results[admission_id]` record.
   The wrapper seals the observation and attaches metadata to that original
   record before `_execute_claimed` clears the executing generation.
7. The native `prepare_result`, `compact_result`, `encode_result`, and
   `load_result` retain the outer metadata with the original result. Ordinary
   redaction and native failure/interruption semantics remain in force.

The gateway entry installs the two wrappers once after exact profile/source
selection and before native main starts the gateway. The original API-start
callback binds the actual `SessionAuthority` instance before opening the
private control listener. The tools-list invocation does not install them.

## Meaning of the observation

Outer result key: `mastermind_request_observation`.

Schema: `mastermind.hermes_request_observation/v1`.

Stage: `assembled_content_after_pre_request_hooks`.

Each observed attempt selects the presence-sensitive `messages`, `input`,
`system`, and `instructions` fields. It detaches only strict JSON values and
hashes their UTF-8 JSON representation with sorted object keys, no insignificant
spaces, no ASCII escaping, and no nonfinite numbers. This is the explicitly
named `json_sorted_keys_utf8_no_spaces_v1` representation, not an RFC8785 claim
or a wire-payload digest. String normalization and whitespace are preserved;
missing, null, and empty fields remain different.

The retained event contains its digest, encoded byte count, selected field
names, canonicalization identifier, and bounded original request/turn/count
identifiers. The scope contains the role, logical session, admission, authority
epoch, execution generation, and instance. The actual adopted agent's physical
session label is optional and may differ from the logical session.

The outer document always declares:

```json
{
  "coverage": "assembly_hooks_only",
  "provider_dispatch_proven": false,
  "model_identity_verified": false
}
```

When there are no retained observations, coverage is
`no_assembly_observation`. That is not proof of zero model calls. The native
pre-request helper can contain plugin exceptions, later execution middleware
can modify or short-circuit the request, and other native paths can bypass this
assembly seam. Requested provider/model labels, serving-model identity,
provider delivery, complete context inclusion, memory efficacy, and EVAL
validity are not inferred.

Raw prompts, output, tool schemas, headers, credentials, reasoning, provider
labels, and arbitrary request metadata are not retained by this observer. A
digest is produced before later request mutation and does not change with it.

## Custody and bounded retention

The held source verifies the six complete upstream files listed in
`native_request_observation.SOURCE_SHA256`. Module origins, original function
globals/source filenames and async/sync signatures are checked before any
wrapping. Existing bindings and changed source refuse startup. The actual
authority must match the selected profile, instance, epoch, runner, and
single-profile descriptor.

The scope checks the original live session object, executing generation,
complete claim stamp, role/source lifetime, drain/retirement state, and actual
adopted agent identity. It calls the native stored-generation checker before
and after hashing. Storage reads occur outside the stream lock. The final
ownership check and event append use the native `event_stream.lock`, followed
by the scope lock, matching the claim/adoption/retirement owner. Sealing and
attachment use the same ordering.

Content work is bounded at 4MiB encoded bytes, 65,536 visited nodes, depth64,
and strict supported value types. At most eight attempt observations and
16KiB of final metadata are retained. Identifiers are at most256 UTF-8 bytes;
invalid labels are omitted with named invalid-field markers. Errors have a
fixed vocabulary. Overflow is explicit. Content limit or instrumentation
failure does not replace the original native outcome.

The observer never creates a missing pending result or overwrites an existing
outer observation field. An agent's same-named inner result field cannot become
the outer gateway observation. Sealing prevents a cancelled executor's copied
context from adding late evidence or contaminating a successor claim. Native
exceptions and cancellation propagate unchanged through the ingress wrapper.
No `SessionEvents.observers` registration or extra publication changes delivery
acceptance.

## Verification and remaining consumer work

The tests include complete, unmodified MIT upstream files and a five-line
executor-method excerpt, with exact revision/blob/digest provenance and license
notice in `integrations/hermes_runtime/tests/fixtures/request_observation`.
They execute selected original AST bodies, with explicit edge doubles for
viewer/transport/storage/environment services. The request builder, admission,
claim-owner ordering, finite wrapper, context-copy executor, compaction,
redaction traversal, and stored-result codec bodies are actual donor code.

Meaningful checks cover middleware/hook mutations, Unicode and presence
semantics, exact-once original calls, retained result round-trips, original
failure flags, cancellation with a surviving real executor, successor-claim
isolation, interleaved admissions, stale ownership, an adoption race during
hashing, unsupported JSON and content bounds, overflow, source mutation and
authority qualification before a listener effect.

These are source/composition tests. They do not establish an installed service,
actual provider request, full host permissions, model identity, held-out
performance, or learning acceptance. The original C26 host-access issue remains
separate.

## Authenticated original-result projection

The existing role-qualified private request `read_original` now returns
`request_observation` beside the original answer and terminal metadata. Its
status is `observed`, `missing`, or `invalid`. Only `observed` carries a
`document`; missing or invalid metadata does not hide a valid native answer,
alter success/failure, create an admission, or authorize replay. Unsettled
admissions expose no terminal observation.

The reader takes the document only from the outer saved result. Agent-generated
same-named inner fields are ignored. It first qualifies the original principal,
profile, session, submission, input digest and requested admission. It then
joins the document's role, session, admission, stored authority epoch and
execution generation to that original receipt. A missing generation cannot be
manufactured. Historical reads compare historical identities, so a new owner's
epoch cannot erase a retained observation. The instance label is bounded reported
metadata: the admission row supplies no independent instance-identity join.

The projection accepts exactly the producer's bounded fields, content digest
representation, field ordering, error vocabulary and observation counts. Unknown
fields, malformed identifiers, contradictory coverage, oversized data and true
provider/model proof flags invalidate only the observation. Raw prompt content,
unselected error text and arbitrary metadata cannot pass through this projection.
A returned document is detached from owner storage.

Source qualification includes a test that failed before this change because
`read_original` dropped the outer evidence. The positive path executes the
pinned upstream admission/assembly/compaction/codec bodies, retains the result
in SQLite, and reads it through the original reader before and after a simulated
owner restart. Native row lookup and environment edges are explicit doubles.
Separate real AF_UNIX tests cover both Secretary and Meta role contracts and
ensure a newer admission cannot replace the requested original result. These
tests prove the composition, not an installed service or actual provider call.

EVAL still must join genuine admissions, original outcomes, exact source facts
and real held-out judgments. This projection creates no EVAL record, learning
acceptance or validity receipt. The original C26 access hold and other activation
boundaries remain separate.
