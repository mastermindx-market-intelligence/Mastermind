# Web Fabric autonomy through the existing execution owners

Status: source implementation in progress; this document does not attest installation or production acceptance.
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
- **GitHub review decisions:** exact repository, PR, expected full head and a review-ID baseline; bounded complete pagination and current-head binding. Report new approved, changes-requested or dismissed review evidence. A review event does not prove reviewer independence, required approval count or release authority.
- **Named service health:** existing read-only endpoint/tool allowlist, semantic health state, no arbitrary caller URL, headers, credentials or command. Ignore volatile request nonces and timestamps. Permission/auth failures terminate observation without retry.

The result is one of material event, timeout, cancellation or unavailable source. It preserves identity and source digest and explicitly grants no retry, release or native-parent-wake authority. Cancellation ends only this finite observer; it does not cancel siblings, revoke leases, mutate Jobs or re-open terminal work.

Network sampling is deterministic and bounded; a sleeping process is not a model polling loop. A material result returns to the same admitted worker, which must fresh-read the authoritative source before any separately authorized effect. Source text, CI logs and API responses remain untrusted evidence, never instructions.

## Practical autonomous workflow

1. The Web principal reads the current compatible bootstrap once, recovers the source plan and exact effects, and discovers the actually exposed Fabric contract.
2. It partitions ready work by independent inputs and source custody. Dispatch ready siblings promptly within admitted budget, provider/host capacity and review capacity. There is no arbitrary one-worker serial default and no assumption that an advertised ceiling grants all slots.
3. Each commission includes the complete bounded outcome, exact source and expected head, owned paths, available capabilities, finite wait/repair limits, falsifier, verification, retained return and stop condition. A tool schema without `max_turns` must not receive invented parameters.
4. A worker observes deterministically, then acts only inside its original grant. For CI healing, inspect the exact failing current-head run, make a bounded repair, run focused checks and return evidence. Green selected runs, skipped checks and actual required-policy success remain distinct.
5. A review worker returns findings; it does not impersonate a formal non-author GitHub approver. Applicable required formal review and protected release controls remain with their owners.
6. The principal reads the complete retained result, verifies proportionate evidence and records acceptance using the exact effective/accept run ID. It advances each useful return without waiting for unrelated siblings.
7. If the foreground session ends, original operation and effect identities remain recoverable through existing source/Agent OS records and the original result path. A resume must reconcile them before creating another effect. No detached chat daemon is implied.

An existing execution plan may sequence steps through accepted predecessor result manifests. At the current schema, a completed work result releases a dependency without a built-in conditional material-event predicate. A downstream worker must therefore revalidate semantic disposition and no-op or return blocked when appropriate. Do not encode quiescent timeout as fabricated failure, or claim that generic dependencies suppress every non-material launch.

Dependency manifests establish predecessor identity and readiness, not automatic transfer of the predecessor's report into a worker prompt. The current ordinary supervisor prompt does not project arbitrary predecessor result bytes. A whole bounded worker already holds its observed evidence. A separate sealed-input triage step must receive that evidence through its existing verified immutable commission/input owner; manifest presence alone is not proof of consumption.

## Replay, identity and failure rules

| Boundary | Required behavior |
|---|---|
| Duplicate exact CI material observation | One existing Wake obligation/command; return the immutable canonical record, including across Runtime reopen. |
| Tampered decision, digest or binding | Reject before a write. A wrapper is not a way to bless inconsistent evidence. |
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

A real admitted Fabric canary must load the exact candidate implementation, execute a finite observer, continue its bounded task, return retained evidence and be consumed by the principal. That is proof of the attended worker workflow only.

The production durable path additionally requires a qualified capable route, real installed/armed Executive consumer, admission/START, exact returned source evidence, post-restart reconciliation and parent/COO consumption. The existing #1893 protected original administrator-result hold blocks the dependent activation lane. Do not read the denied result through another carrier, restart services or imply this source change resolves that hold.

Original scope remains open until account rollout and the production consumer proof are actually satisfied. Record built, tested, published, installed and proven states separately in the source plan and Agent OS.

## Primary research

Anthropic's current public design separates [deterministic lifecycle hooks](https://code.claude.com/docs/en/hooks), [scheduled/session tasks](https://code.claude.com/docs/en/scheduled-tasks) and [subagent execution](https://code.claude.com/docs/en/sub-agents). That separation informs this design: a trigger carries evidence to an existing execution owner; it is not a new authority or persistence mechanism. These external product capabilities do not grant capabilities to ChatGPT Web or Mastermind.
