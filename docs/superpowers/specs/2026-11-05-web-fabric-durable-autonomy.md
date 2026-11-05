# Web Fabric autonomy through the existing execution owners

Status: timer, finite observer and CI-Wake source implemented and qualified; installation, real-worker and all-account acceptance remain open.
Governing source: Mastermind `b9e4c72c101d1f5a4ef6c86e51e8eb1fdc89cf8c`.
Delivery carrier: [Mastermind #2066](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2066).
Operation: `web-fabric-durable-autonomy-20261105-c3`.

## Outcome

A Web principal can commission independent ready work concurrently, give a capable Fabric worker an entire bounded wait / inspect / repair / verify / return assignment, and consume each result as it becomes useful. Waiting for CI, a review decision, a timer, or a named service transition should not require one model turn per sample or another user message per ordinary authorized action.

A persistent record and an executing consumer are different deliverables. Preserve the existing Executive Job/Attempt owner, Fabric admission/capacity owner, Wake event ledger, source/CI owner and Agent OS continuity. No new queue, cron service, generic callback runner, browser control loop, lifecycle database or permission broker is introduced.

## Ownership and execution paths

| Path | Producer and consumer | Lifetime and evidence |
|---|---|---|
| Attended Web to capable Fabric worker | Existing `fabric_request`, original stable root and immediate parent; worker executes a complete bounded commission | Existing admitted worker/controller lifetime. Retained terminal result plus parent verification/acceptance. No native Web wake or process restart promise. |
| Finite deterministic watch | `ops.fabric_launch.finite_watch` runs inside that worker; its typed result returns control to the same worker | At most the admitted finite timeout/sample budget. No model call per sample, own daemon, renewal or independent action. |
| Exact CI observation to Wake | Existing candidate observer/continuation produces a validated obligation; a trusted host join writes through `WakeLedgerRepository` | Idempotent durable obligation in existing Runtime events. Runtime reopen can retain the obligation; persistence alone does not prove delivery or dispatch. |
| Existing autonomous Executive plan | Existing strict root, execution plan, COO ready frontier and supervisor admit each capable dependent Job | Only an actually installed, armed and qualified route can make this autonomous. Source tests do not attest live service readiness. |

The installed attended adapter currently reports `native_parent_wake=false`, `background_execution=false` and generation-local controller tracking with `restart_persistent=false`. Those fields must remain truthful. A successful independently executing worker proves its bounded task path, not an always-running ChatGPT conversation.

The existing Executive service is the restart-capable consumer owner. Its startup reconciliation, COO tick, ready frontier, dependency manifests and exact dispatch remain authoritative. Bare `WAKE_REQUESTED` does not authorize creating a root, selecting a provider, retrying a Job, granting write access or dispatching a repair.

The current protected paid background route is sealed-input analysis, with no general file, web, tool, hook or subagent capability. The attended MiniMax composition has a foreground-only condition. Neither limitation may be erased by labeling a task a watcher. Use the currently admitted tool-capable attended route for executable finite observers; a background tool-capable route needs its own existing capability qualification and release process.

## Finite observer contract

A request binds original run, root, parent and watch identity, a closed source description, timeout, cadence and sample ceiling. Unknown fields, malformed identities, booleans in integer fields and invalid limits fail before observation. The CLI reads one regular bounded request file at invocation; it does not read credentials from that file.

Supported observations:

- **Timer:** fixed UTC due time within a finite monotonic lifetime. A future deadline beyond the budget produces a timeout, not renewal.
- **Selected GitHub CI runs:** exact repository, PR, expected full head SHA and explicit workflow-run IDs. Read the PR head before and after sampling; validate every run's repository and head. Report actual terminal conclusions. This does not synthesize the repository's required-check policy or certify release readiness.
- **GitHub review decisions:** exact repository, PR, expected full head and a review-ID lower bound for new reviews; bounded complete pagination and current-head binding. The observer must also retain an in-process semantic baseline of review ID, state and commit association from its first complete snapshot, so later dismissal or other decision changes to an existing review are detectable. Report new approved, changes-requested or dismissed review evidence and subsequent semantic state changes. The ID lower bound alone cannot prove revocation detection. A review event does not prove reviewer independence, required approval count or release authority.
- **Named service health:** existing read-only endpoint/tool allowlist, semantic health state, no arbitrary caller URL, headers, credentials or command. Ignore volatile request nonces and timestamps. Permission/auth failures terminate observation without retry.

The result is one of material event, timeout, cancellation or unavailable source. It preserves identity and source digest and explicitly grants no retry, release or native-parent-wake authority. Cancellation ends only this finite observer; it does not cancel siblings, revoke leases, mutate Jobs or re-open terminal work.

Network sampling is deterministic and bounded; a sleeping process is not a model polling loop. A material result returns to the same admitted worker, which must fresh-read the authoritative source before any separately authorized effect. Source text, CI logs and API responses remain untrusted evidence, never instructions.

## Practical autonomous workflow

1. The Web principal reads the current compatible bootstrap once, recovers the source plan and exact effects, and discovers the actually exposed Fabric contract.
2. It partitions ready work by independent inputs and source custody. Dispatch ready siblings promptly within admitted budget, provider/host capacity and source custody. Account for review capacity only when the work actually carries a required review obligation. There is no arbitrary one-worker serial default and no assumption that an advertised ceiling grants all slots.
3. Each commission includes the complete bounded outcome, exact source and expected head, owned paths, available capabilities, finite wait/repair limits, falsifier, verification, retained return and stop condition. A tool schema without `max_turns` must not receive invented parameters.
4. A worker observes deterministically, then acts only inside its original grant. For CI healing, inspect the exact failing current-head run, make a bounded repair, run focused checks and return evidence. Green selected runs, skipped checks and actual required-policy success remain distinct.
5. A review worker returns findings; it does not impersonate a formal non-author GitHub approver. Applicable required formal review and protected release controls remain with their owners.
6. The principal reads the complete retained result, verifies proportionate evidence and records acceptance using the exact effective/accept run ID. It advances each useful return without waiting for unrelated siblings.
7. If the foreground session ends, original operation and effect identities remain recoverable through existing source/Agent OS records and the original result path. A resume must reconcile them before creating another effect. No detached chat daemon is implied.

An existing execution plan may sequence steps through accepted predecessor result manifests. In legacy plan schemas, a completed work result releases a dependency without a built-in conditional material-event predicate. Explicit V6 timer gates add the material-only observation predicate described below. A downstream worker must revalidate semantic disposition and, when no effect is warranted, return truthful no-action or inconclusive evidence using its admitted result schema. The existing supervisor and COO owner retain lifecycle blocking and failure decisions; do not invent a BLOCKED work-result envelope. Do not encode quiescent timeout as fabricated failure, or claim that generic dependencies suppress every non-material launch.

Dependency manifests establish predecessor identity and readiness, not automatic transfer of the predecessor's report into a worker prompt. The current ordinary supervisor prompt does not project arbitrary predecessor result bytes. A whole bounded worker already holds its observed evidence. A separate sealed-input triage step must receive that evidence through its existing verified immutable commission/input owner; manifest presence alone is not proof of consumption.

## Replay, identity and failure rules

The private Wake persistence join accepts only the trusted host owner's
continuation object. It reconstructs binding fields to check projection
consistency; it cannot independently authenticate the original root, account or
grant. The existing host must establish that provenance before calling it. It
is not exposed as a model-writable endpoint. A coherently different binding is
not inherently invalid on a fresh ledger; after the first canonical write, the
existing ledger rejects conflicting correlation and preserves the original row.
Receipt flags describe what this call performed, not the current delivery or
acknowledgement state of an older obligation.

| Boundary | Required behavior |
|---|---|
| Duplicate exact CI material observation | One existing Wake obligation/command; return the immutable canonical record, including across Runtime reopen. |
| Tampered decision, digest or internally inconsistent binding | Reject before a write. Canonical self-consistency does not authenticate the caller or independently prove original root/grant provenance. |
| Source head moves during observation | Return stale/unavailable evidence; no repair, approval or release claim for the old head. |
| Process interruption after an effect | Reconcile the same operation/carrier. Never infer absence, blindly replay or switch accounts. |
| Gateway restart | Re-read the original retained task/result through its owner; do not reconstruct authority from lost in-memory handles. |
| Runtime restart | Existing reconciliation and finisher custody apply. `requeue_lost=False` is not permission to repeat interrupted effects. |
| Permission denial | End that action. Do not rephrase, change provider/account or install a substitute route. |
| Budget exhausted or timeout | Return a truthful bounded result. No self-renewal or root-budget reset. |
| STOP/cancel | Stop the exact child/observer; preserve siblings and unresolved effects. |

## Source and account delivery

The source skill lives beside the existing low-level `use-subagent-fabric` contract in `integrations/studio_direct_mcp/fabric_plugin_source`. The new orchestration skill references existing ownership and explains useful fanout, complete commissions, deterministic waits and retained-result consumption. It is account-neutral.

For each existing Web account plugin, preserve the exact app/MCP identity, presentation, permissions and audience. Add skills through the plugin's supported source/update owner using its observed release ID. Source package creation, account release publication, installed skill loading, worker execution and parent consumption each need their own evidence. A C3 success does not attest C1, C2, C4, business or admin profiles.

The shared Project kernel remains under the active parity repair in #2064; the browser session attention watcher remains under #2063. This implementation must not overwrite those live writers. Additive guidance in existing source owners can land independently; compose actual Project changes against the accepted kernel and its byte limit after custody is reconciled.

## Proof and rollout

Focused tests must distinguish malformed/stale evidence, duplicate material events, Runtime reopen, cancellation, finite exhaustion, changed CI heads, partial pagination, unavailable/auth-failed sources and secret-free errors. Pure imports must not start work or write state.

A real admitted Fabric canary must load the exact candidate implementation, execute a finite observer, continue its bounded task, return retained evidence and be consumed by the principal. The concrete canary uses an actual UTC timer due three seconds later with real monotonic time, and gates focused validation on its TIMER_DUE result inside the same admitted worker. A separate authorized single current-PR CI sample reports its actual outcome; it cannot substitute selected-run completion for required-policy success. A synthetic clock/unit test alone is not this proof. No production test writes or fabricated failures are needed. That is proof of the attended worker workflow only.

The production durable path additionally requires a qualified capable route, real installed/armed Executive consumer, admission/START, exact returned source evidence, post-restart reconciliation and parent/COO consumption. The existing #1893 protected original administrator-result hold blocks the dependent activation lane. Do not read the denied result through another carrier, restart services or imply this source change resolves that hold.

Original scope remains open until account rollout and the production consumer proof are actually satisfied. Record built, tested, published, installed and proven states separately in the source plan and Agent OS.

## Primary research

Anthropic's current public design separates [deterministic lifecycle hooks](https://code.claude.com/docs/en/hooks), [scheduled/session tasks](https://code.claude.com/docs/en/scheduled-tasks) and [subagent execution](https://code.claude.com/docs/en/sub-agents). That separation informs this design: a trigger carries evidence to an existing execution owner; it is not a new authority or persistence mechanism. These external product capabilities do not grant capabilities to ChatGPT Web or Mastermind.

## Durable observation gate inside the existing COO

The finite helper is useful for short attended waits, but occupies its provider
lease while pending. The long-wait requirement therefore needs a second source
slice inside the incumbent Runtime/COO owner, not another process or queue.
The first slice is a timer-gated, already-admitted leaf step. External CI/review/
service acquisition remains separately unqualified until a trusted source owner
and bounded reader are composed; a timer implementation must not advertise those
sources as installed.

### Versioned contracts and source authority

Add explicit `mastermind.execution_plan/v6` using the V3 leaf topology plus a
required `observation_gate` field on every step (null or a closed object). Preserve
V3/V4/V5 defaults and their producer pins. V6 has at most eight steps, backward
prerequisites and exact provider-realm/quota-class placement; its first form adds
no nested coordination or manual-model selection. A V3-bound producer cannot
return V6 or retrofit an admitted plan.

The first closed gate is `mastermind.coo_observation_gate/v1` with exactly:
`schema_version`, `source={kind:"timer",due_at_ms:int}`, `deadline_at_ms:int`,
`max_samples:1`, `min_interval_ms:0`, `sample_timeout_ms:0`,
`max_api_calls:0` and `max_response_bytes:0`. Exact integers reject booleans,
floats, unknown keys, nonfinite values and duplicate JSON members. Require
`due_at_ms < deadline_at_ms`, an unexpired acquisition deadline and bounded canonical
bytes. An already-due timer is allowed; delayed admission never moves its due time.
Do not reserve authority by accepting unimplemented source variants.

The existing service composes the trusted host. A private observation-host protocol
provides source scope/current-binding checks and a future bounded-reader seam;
a type, hash or scope object does not authenticate its caller. Runtime independently
revalidates the canonical root, sealed planner result, producer binding, plan digest,
persisted READ authority and current Executive authority policy, workstream and
finite-control fences. Persist the effective acquisition deadline bounded by the requested deadline,
the trusted host maximum horizon and an existing finite-control expiry when present.
Ordinary roots do not need a fabricated finite arm or expiry. Missing or disarmed composition refuses before mutation.

Use the existing `COO_PLAN_ADMITTED` event with a new
`mastermind.coo_plan_admission/v4`. Each reservation adds `observation`, null or
an admission binding the root, plan Attempt/digest/step, root creation event,
authority-policy hash, trusted source reference/digest, original admission time,
gate spec and complete gate digest. All fields except the spec derive from
canonical Runtime or trusted host state. Replay retains the first admission time.
Reserve normal work/review/repair allowances, but defer a step with prerequisites
**or a non-null gate** without creating its work Job.

### One transaction and a real downstream consumer

`JobRegistry.advance_cycle_observation(root_job_id, plan_step_id,
observation_host=...)` uses the existing store and deterministic command IDs.
Before due time it returns pending with zero writes, claims, sleeps or network/
model calls. At due time one transaction rechecks admission, root cancellation,
authority, host binding and absolute acquisition deadline, then commits one material
timer record. A material record committed in time remains historical evidence after
that acquisition deadline; downstream execution still obeys its current root gates. At/after deadline it records expiry and cannot satisfy the gate.

A closed observation record binds the root, plan Attempt/digest/step, gate digest,
sample index, authoritative start/finish times, disposition, exact timer snapshot
and canonical snapshot/evidence digests. Timer sample index is one, reservation
command and previous snapshot are null. Only MATERIAL satisfies the gate.
The snapshot is exactly `{kind:"timer",due_at_ms,observed_at_ms}`; Runtime's clock
supplies observed time. Cancellation, stale authority and expiry never manufacture
material evidence. Runtime reopen preserves the original deadline and record.
An uncertain commit reconciles its original command, never a new event identity.
Historical readback and exact duplicate reconciliation remain available after
authority drift; fresh effects do not rewrite admitted hashes to conceal drift.

Use `mastermind.work_dependency_manifest/v3` for V6, retaining existing accepted
revision fields and adding `observation=null | {gate_digest,event_id,evidence_digest}`.
Derive this binding only from the exact committed material record. Both dependency
projection and `create_cycle_work` rederive it through the existing root-open and
reserved-child admission checks; a caller-supplied digest or Wake ID cannot admit
work. A gate-only deferred step must follow the same materialization path.

The Runtime observation-input reader joins actual child creation, current Attempt,
exact dependency manifest and original evidence event. The supervisor adds those
bounded retained bytes to the worker prompt as
`mastermind.coo_observation_input/v1`, labeled evidence data. Old jobs receive no
suffix. A manifest hash alone is not consumption, and timer evidence does not
grant new effects.

### Existing tick composition and honest waiting

The existing `ExecutiveControlService._coo_tick_loop` remains the only periodic
driver. An additive `ServiceConfig.coo_observations_armed=False` and existing
READY/autonomy/current-host/custody gates control timer composition. Installed
configuration and the original #1893 activation hold remain unchanged.

The COO preserves uncertain-dispatch reconciliation first and independent ready
siblings. Advance at most one due observation per turn; never sleep inside the
COO lock. Preserve exact/live/READ frontier fences when other work is active.
The no-living-child/missing-step path must recognize legitimate pending gates
instead of aggregating early or durably blocking the root. A terminal unsatisfied
gate remains explicit while independent authorized work may continue.

The focused proof must exercise sealed plans and real inert owner boundaries:
zero work Job/Attempt/provider start while pending; independent sibling progress;
one evidence record then one reserved Job and ordinary dispatch; reopen before due
and between evidence and Job creation; no premature root block; cancellation and
expiry; missing READ/current-policy drift or missing/disarmed host; exact replay
versus conflicting evidence; wrong-root/step/Attempt refusal; actual prompt bytes;
unchanged legacy schemas and all existing capacity/review/release gates.
These source proofs are not installed-service or unattended production acceptance.

## Implemented scheduling and network qualification

Missing observation-host composition after an in-time material record is temporary: retain the original event/reservation and resume the same work once the original host returns. A proven pre-claim review-capacity miss permits only disjoint READ-gate progress; uncertain/active review effects retain reconciliation priority. The existing service selector rotates after a positive timer-wait outcome using its current previous-root hint, requalifying all candidates and preserving live/unknown ownership. No new durable cursor or queue is added.

The finite helper accepts optional `review_baseline` rows `{id,state,commit,login}` alongside `after_review_id`, so an owner can detect an existing approval dismissed before the first sample. IDs are exact positive integers; conflicting duplicates refuse. CI binds the workflow execution repository, permits a different fork head repository, and retains `run_attempt`. All sequential GitHub calls and fixed MCP body reads share an absolute deadline; late results are discarded and cancellation wins. Streamed GitHub overflow kills/reaps only the exact read child. Positive Studio ping and official documentation-search shapes are required for READY. Errors retain bounded classification and no response/credential text.

The implementation plan records exact source-test receipts, the CI reading-budget correction and the still-open production/account gates.

## Resource limits and Web fan-out qualification

The real canary validates functional timer/continuation behavior and exposes a
separate budget-evidence limit. Its report says approximately 25 provider turns
against behavioral guidance of 12. That report does not define an equality among
tool calls, native CLI turns, provider requests, tokens or billed cost.

Protected native source already has request-level turn-limit plumbing:
`ops/native_fabric/quota_continuity/candidate/fabric_task.py` validates and retains
`max_turns`, forwards `POOL_REQUEST_MAX_TURNS`, and restricts a bounded request to
supported GLM/MiniMax routes. `remote_sub_helpers.py` carries the value.
`sub.sh::_claude_worker_profile` clamps it to the smaller profile/request bound;
the ordinary MiniMax branch and `glm_bound_claude.make_command` pass the effective
value to `claude --max-turns`. The visual-helper branch instead fixes 60, so it
must be qualified or excluded before claiming a caller's ceiling across profiles.

The currently exposed Web `fabric_request` schema has no `max_turns` field.
Neither prose in a work packet nor an advertised capability expands that schema.
The ordinary retained process receipt does not prove the effective numeric argv;
the inspected provider projection reads native `num_turns` internally but does
not retain it as a returned field. A support digest proves source identity, not
the completed canary's effective turn count or requested ceiling.

Future exposure belongs to existing owners: a strictly typed optional facade
field forwarded unchanged to native admission, plus a credential-free projection
of requested ceiling, effective ceiling, exact support/profile and native
`num_turns` when supplied. Preserve actual unsupported-route refusal. #2063
currently owns facade files; this mission does not shadow-edit that writer.
No new budget ledger, watchdog, detached cancellation process or queue is needed.

This gap does not block finite observers or the durable observation feature.
Ready fan-out remains subject to actual capacity/admission and conserved root
reservations; observation deadlines, sample/call/byte budgets and the existing
bounded process owner apply independently. Do not sell a behavioral suggestion as
a hard spend/turn limit, multiply allowances by child/account, or retroactively
claim a missing execution/usage receipt. A commission requiring an unavailable
hard ceiling must use a qualified owner path or refuse that requirement.

C3 judgment references the same protected pin
`b9e4c72c101d1f5a4ef6c86e51e8eb1fdc89cf8c`; source lookup and reasoning were
performed without native labor substitution, runtime probes or facade edits.
