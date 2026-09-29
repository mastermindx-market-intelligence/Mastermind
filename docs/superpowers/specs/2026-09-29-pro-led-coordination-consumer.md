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


## Work-role integration and canonical Runtime acquisition

Implemented in `control_plane/chairman_coordination_work.py` under the same #1056
operation and #1059 source carrier. The Web principal retains implementation; no
new task is assigned to the base builders.

### Why this addition is necessary

A correctly typed raw observation does not mean an admitted native role permits a
standalone coordination-candidate final answer. Current orchestration roles return
their fixed result envelope; the interactive native supervisor remains plan-oriented
and read-only. It must not be silently widened by substituting another JSON schema.
The earlier complete-raw consumer remains a lower-level contract consumer, not proof
that a supported native generation path can produce that candidate directly.

This implementation instead treats one coordination judgment as an ordinary, already
admitted work task. The candidate is an ordinary artifact inside an exact write grant.
The final answer remains the existing work-result envelope, including the candidate
artifact path and SHA-256. No provider role, adapter, result schema or Runtime seal is
changed. This does not itself dispatch the task or activate a work-capable native profile.

### Outbound: exact current assignment

`read_coordination_work_request` consumes the existing bound Runtime instance and exact
root, Job and expected Attempt selectors. It reuses the installed source join's bounded
root observation and canonical creation-provenance validation. The root's recorded
workstream must equal the context project; a label or child-provided reference cannot
substitute. Unbound/invalid namespaces, truncated membership and changed selectors
refuse before producing a request.

The resulting Job and Attempt go to `render_coordination_work_request`. The original
pure effective-grant validator checks the same Job's preauthorized authority decision.
The Job must be the current running work role, on its exact Attempt/worker and accepted
plan lineage, with WRITE_BRANCH and the exact artifact path already granted. The
original work-result schema is returned byte-for-byte structurally unchanged.

The prompt contains the existing context briefing and explicit artifact instructions.
It tells the worker to propose a next step, not execute the proposed step. Source
admission, model/slot eligibility and all actual effect checks remain with the existing
owners. The returned request grants no authority and its read receipt does not promise
freshness after the sampled observation. The host must revalidate at actual dispatch.

### Inbound: one canonical result plus exact artifact bytes

`read_coordination_work_return` uses the existing bounded role-result reader with an
exact root/Job/Attempt/envelope-digest selector. It waits for the physical read scope
to close, then invokes the existing shared Fabric result projector. It does not copy
that validator, open SQLite directly, find a newest result, or retry another selector.
The canonical root workstream must match the coordination context, and the completed
result must be the work role without unresolved outer errors.

The supplied artifact path must occur exactly once in the canonical artifact manifest.
The supplied immutable bytes must match that artifact's SHA-256 and contain complete
canonical JSON within the consumer's bound. Artifact acquisition itself remains the
existing authorized artifact owner's responsibility; this module never opens a supplied
filesystem path. The complete candidate then passes through the original coordination
review, including the current accepted intent and plan checks.

The output records the canonical result selection, observation generation and artifact
identity. It still grants zero execution and zero acceptance authority. A completed
work task is not acceptance of the project, and structural checks are not a judgment
of the model's reasoning quality.

### Verified level

The integration tests create a real temporary Executive Runtime and pass ordinary
intent, plan, dispatch, result-seal and bounded-read operations through existing owners.
An end-to-end test binds an active work request, creates the proposed artifact under
the granted fixture path, completes the unchanged work result and recovers the exact
candidate. Model reasoning and native process observations are explicit fixtures; no
real provider is launched and no production Runtime is mutated.

Negative cases use separate read bindings. A binding invalidated by a failed selection
is not reset or weakened to keep a test running. The same production guard that closes
an invalid reader remains unchanged.


## Host supervisor composition — direct implementation follow-through

The optional `control_plane/chairman_coordination_host.py` now connects the previous
consumers to an actual ExecutiveSupervisor prompt/launch/completion path. The host
selects one already-admitted coordination work Job. It does not register a new
service, model role, queue, scheduler, operation identity or source authority.

`CoordinationWorkSupervisor` subclasses the existing supervisor and overrides only
its prompt hook. Original start, finish, heartbeat, validation, recovery, assignment
sealing and command-replay methods remain inherited unchanged. All other Jobs retain
their ordinary prompt. An exact selected Job with missing/unusable sources refuses
before the adapter starts instead of silently falling back to generic work.

The constructor requires the existing exact-target provider. A missing or foreign
selected target refuses before claiming work; ordinary capacity selection is not a
fallback for a task whose exact counterpart is required. The target is validated by
the existing Runtime owner and is never reissued or fabricated by this composition.
That same owner still performs its dispatch-time source/freshness/permission checks.

### Trusted source inputs

`CoordinationWorkSources` is a transient dataclass containing the already-owned
policy document, scoped context, compiled Agent OS bundle, bundle source reference,
artifact path and a current-source revalidator. It is neither a persistent memory
record nor an authentication token. The installed host must acquire these inputs
under its existing authorization, and must select the Job under the actual accepted
coordination assignment—not take these values from arbitrary caller text.

The revalidator follows the existing void-or-raise pattern: it returns exactly None
on a valid observation or raises. Booleans, strings and other nominal success tokens
are not accepted. Inputs are copied per call to prevent accidental mutation through
a shared provider cache. Snapshot copying is not authentication or ongoing freshness.

The original worker prompt/grant/result contract is preserved as the prefix. The
source-bound coordination task is appended only after current root, Attempt, effective
grant and source validation. The original supervisor persists the complete composed
prompt in its existing private recovery artifact; no second prompt store is created.
A task snapshot does not replace the effect owner's final dispatch fence.

### One bounded host step

`await supervisor.run_coordination_once(command_id=existing_command,
artifact_reader=existing_authorized_reader)` calls the inherited finite
`run_cycle_once` once, then collects a decision proposal. It returns the original
SupervisorReceipt or OrchestrationDispatchOutcome alongside a derived review or None.
No additional lifecycle/status model is introduced.

- An active duplicate returns the original active outcome with no second model run,
  source reasoning pass or result read.
- Completed replay reads the same accepted work result and artifact; it never
  re-plans, starts another worker, changes the command or creates another Attempt.
- Failed/cancelled/non-completed execution remains the original execution outcome,
  not a reviewed decision or a falsely accepted project.
- Source or artifact unavailability after work completion does not rewrite the
  canonical result as failed or restart the worker. Explicit same-command recovery
  can later read the original result once the owner dependency actually changes.
- A new Chairman intent observed after native completion holds the old candidate;
  it does not silently rewrite the proposal or execute its next step.

The helper invokes existing runtime effects only when explicitly called with an
already-admitted Job, command and current target/permission. Import and construction
start nothing. There is no automatic loop, background inference or polling.

### Complete return and artifact acquisition

`consume_coordination_completion` also supports a caller that already obtained an
ordinary SupervisorReceipt. Before asking for any artifact, it reads and validates
that exact canonical completed work result through the existing bounded Runtime and
Fabric owners. Only its declared single exact path/hash is sent to the installed
artifact reader, together with canonical Job/Attempt objects and a fixed byte ceiling.
The physical Runtime observation is closed before the artifact reader is invoked.

After acquisition, a second bounded observation revalidates the same result selector
and complete bytes through the previous work-return consumer. Namespace loss, target
change or source invalidation refuses without fallback/reacquisition loops. Neither
observation claims a write exclusion beyond its sampling interval. The installed
artifact reader remains responsible for safe physical read authorization and file
identity: this module intentionally does not open paths, URLs or arbitrary files.

The proposed next_step is not executed. Runtime work completion is not project
acceptance. Review output continues to require semantic judgment and current owner
admission; source hashes and test fixtures do not establish actual model intelligence.

### Qualification boundary

The new tests exercise the real supervisor and temporary canonical Runtime through
claim, launch, private recovery-prompt persistence, collection, assignment sealing,
completion, bounded artifact acquisition and decision review. The provider adapter
and model decision are explicitly fake. They do not start Claude, Codex, a Web Pro
turn or a production process. Fixture artifact readers are not installation recipes.

Required before live activation: accepted source/review/release, the actual host's
source and artifact acquisition bindings, an eligible current native profile and
permission envelope, one benign admitted model work task, and meaningful parent
consumption. The source does not substitute Extra High/native work for required Web
Pro reasoning or establish automatic control of an existing ChatGPT conversation.
