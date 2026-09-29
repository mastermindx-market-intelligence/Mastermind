# Pro-led coordination consumer — implemented isolated vertical

Operation: `mastermind-pro-led-project-delivery-20260929-sol-001` / #1056.
State: **BUILT_NOT_PROVEN / no production admission or model qualification**.

## Ownership correction

The current Chairman directed this Web principal to build the enhancement directly.
The request for the busy base builders to schedule this enhancement was withdrawn.
Their source, release and installation responsibilities remain untouched. This source
is additive implementation in the existing registered #1056 workspace, not another
principal, worker commission, runtime, queue, memory store or compiler.

## Implemented path

Existing Macro Agent OS `compile-context` output
→ source-bound briefing through the existing Chairman Cognition CLI
→ a model's explicit candidate (model invocation remains outside this component)
→ project/revision/return/evidence checks plus the original cognition evaluator
→ a non-authoritative result for semantic review and current owner revalidation.

The code lives in `control_plane/chairman_coordination.py` and extends the existing
`scripts/chairman_cognition.py` entrypoint. The original evaluator and context compiler
are imported/consumed, not rewritten. Without the new flags, CLI output is unchanged.
The new schemas are transient input/output contracts for this consumer, not durable
records, authority grants or new lifecycle states.

## Briefing API

`render_coordination_brief(document, *, context, context_bundle, bundle_source_ref)`
accepts the existing `mastermind.chairman_cognition_input.v1`, the scoped context,
and an already-compiled `context_bundle.v1`. The context must bind the exact project,
intent, accepted plan and source revisions. An AGENT_OS source receipt binds the
whole bundle as `sha256:<canonical-JSON digest>`; the context cites that same revision.
The canonical JSON convention is the existing `wake_events.canonical_json_bytes`.
An upstream `source_records_digest` is separately preserved with its actual
`sha256:` prefix; it is not interchangeable with this whole-envelope digest.

The renderer retains the entire compiler output: sections, citations, wait evidence,
excluded records, budget omissions, degradation, source identity and timestamps.
It does not retrieve, summarize, rank, refresh or write any memory. A wrong project,
changed bundle, missing required source or stale source binding refuses the brief.
A degraded compiled bundle cannot be presented as COMPLETE. An explicitly partial
context can be rendered for reasoning about the gap, but its review cannot authorize
a normal modifying continuation.

The fixed instruction describes Pro as the product/design/research/planning/synthesis
principal; native delivery advances the accepted slice in parallel. Evidence text is
serialized separately from the fixed instruction. This separation is not a claim of
perfect prompt-injection defense. It does not turn quoted instructions into authority.

No option or decision is preselected. The template binds immutable context identities
but leaves option, decision, rationale and next step to model judgment. The renderer
refuses payloads above 512 KiB rather than silently truncating; this is an implementation
byte limit, not a claim about the model's actual context window or token allowance.

## Candidate-review API

`evaluate_coordination_candidate(document, *, context, candidate)` first calls the
unchanged `chairman_cognition.evaluate_document`. Additional checks can only hold
that result, never upgrade an option refused by the existing owner.

The candidate carries an option ID, project, intent/plan revisions, context/policy
input digests, proposal label, exact target reference, consumed-return claims,
evidence references, rationale and next step. CONTINUE, REQUEST_REPAIR, ASK_PRINCIPAL,
PROPOSE_ACCEPTANCE and WAIT are explanatory proposal labels, not runtime commands.

Checks include exact project and option scope; source identities/owners/currentness;
accepted-plan and Chairman-intent changes; target changes; required returns missing
from the candidate; evidence outside the context; undeclared or missing acceptance
proof; permission holds; unresolved effects; and original policy eligibility.
WAIT cannot conceal a modifying option. A proposed acceptance remains a proposal.
Read-only investigation may remain available with visible effect/permission cautions;
that does not permit it to retry or affect the held operation.

Every result contains `execution_authority_granted:false`, `acceptance_granted:false`,
`requires_semantic_review:true`, and `next_effect_requires_owner_revalidation:true`.
Both briefing and review are deterministic and perform no I/O. No free-text rationale
or next-step instruction is echoed in the review result.

## Trust boundary — essential

The source adapter must acquire the context, policy, receipts and accepted plan from
their existing owners. Consistent caller JSON and matching hashes do not authenticate
any of them. A model may not author its own authority envelope or claim that its list
of consumed references proves it actually read/understood the source.

This component checks structural consistency, not whether a conclusion is intelligent,
a cited test proves success, or an instruction matches the chosen action semantically.
A dishonest model could select a read-only option and write deployment prose. The
review still grants zero execution authority and explicitly requires semantic review.
Actual runtime capability restrictions and current owner checks must remain in force.
Nothing here submits BEGIN_TURN, wakes a Web chat, chooses an account, creates a Job,
changes the initial plan seal, or changes the production acceptance owner.

## Executable examples

All checked-in example inputs are FICTIONAL qualification fixtures, not live grants.

```bash
python3 scripts/chairman_cognition.py \
  tests/fixtures/chairman_coordination/example_policy.json \
  --coordination-brief tests/fixtures/chairman_coordination/example_brief_request.json \
  --pretty

python3 scripts/chairman_cognition.py \
  tests/fixtures/chairman_coordination/example_policy.json \
  --coordination-review tests/fixtures/chairman_coordination/example_review_request.json \
  --pretty
```

The three modes are mutually exclusive. One input may use stdin, never both. Malformed
or oversized supplemental JSON returns the existing closed INVALID_INPUT error without
echoing raw content. Exit zero means evaluation succeeded, not that execution is allowed.

## Verification and remaining boundary

Tests cover the existing CLI, prompt/candidate round trip, cross-project and stale
revisions, missing consumption, partial context, changed target, denied delegation,
unknown effects, acceptance proposals, false role claims, malformed scalar/container
values, duplicate JSON, input/output bounds, deterministic reconstruction and no I/O.
The exact pinned Macro compiler was also executed on isolated fixture records, with
explicit fixture repo/date adapters; its output was consumed unchanged. This is source
compatibility proof, not a live project-memory or native-provider canary.

No base-builder task is required to continue developing this component. This Web
principal retains its implementation. Existing admitted model/transport and durable
return adapters remain the later integration boundary, after source review and release;
no new immediate assignment to the busy base team is made here.


## Complete native-result consumer — implemented follow-through

`evaluate_coordination_return(document, *, context, observation, candidate_result,
expected_turn, expected_provider_session_id, expected_provider_native_turn_id)` consumes
existing `RawRoleResultObservation`, `CandidateResult` and `TurnRef` types. It never
creates or changes their wire format, runtime status or completion seal.

The current native adapters shorten ordinary candidate summaries to4,000 characters.
For this consumer that summary is navigation only: it is never parsed or treated as
complete model output. The complete canonical JSON is parsed with the existing raw
result validator, binding attempt, session epoch, process generation, exact turn,
provider session/native turn, and the artifact digest previously collected by the
adapter. Altered bytes/digests, false job-completion permission, dictionaries posing
as owner instances and excessive content fail closed. Native canonical-result digest
and coordination-candidate digest are distinct because each retains its owner's
canonicalization convention; neither is silently substituted for the other.

The result is passed through the existing candidate review without altering the
source-bound context or overriding the policy verdict. Returned evidence retains
exact native provenance and `summary_used:false`, but not the private result text.
The input limit128KiB is local to this consumer, not a provider context-window claim.

The CLI also supports --coordination-return with an explicitly supplied observation,
collected candidate, expected turn/target and context. Deserializing that document
is not trusted acquisition or permission; every output still grants zero authority.

```bash
python3 scripts/chairman_cognition.py \
  tests/fixtures/chairman_coordination/example_policy.json \
  --coordination-return tests/fixtures/chairman_coordination/example_return_request.json
```

Existing provider roles and structured-output profiles are not changed or armed.
In particular, a fixed plan/work role must not be secretly replaced by this candidate
schema. This source consumes the existing complete-observation contract; qualified
model generation, current Runtime binding and an authorized dispatcher remain distinct.
No shortened summary can stand in for a missing full result. Tests construct the real
observation types with explicit fixtures; they do not assert a real model ran.
