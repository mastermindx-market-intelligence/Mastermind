# Capacity Fabric router: current upgrade and acceptance frontier

Parent: Mastermind #983 / WS:EXECUTIVE-CAPACITY-FABRIC.
Operation: capacity-router-resilience-20261109-c4.
Procedure pin: protected master ff6d5ab67c3535056d69f603fac0d95c058baad8,
Skillpack 1.0.1. Actual master later observed at 3652d8907df1738de551dd3032b42aa2a2acb482;
that disjoint Hermes GitHub-plugin advance preserved applicable procedure bytes.
Date: 2026-11-09.

## Mission and acceptance

Make the shared M2 routing edge reliable under concurrent Hermes, DeepSeek Harness
and T3 traffic, with truthful health, bounded overload and deterministic recovery.

DONE_WHEN: affected regressions pass; the normal protected release path admits the
source; the installed generation exposes the new behavior; all three consumers
retain their endpoint/model contracts and complete real-path acceptance.
Source qualification, merge, installed generation and consumer acceptance are
separate. MISSION_COMPLETE: false. Current capability: BUILT_NOT_PROVEN_LIVE.

This is an extension of the existing unified router and its owners. It creates no
quota registry, credential store, queue, admission owner or Executive lifecycle.

## Current source and custody

- Original dependency PR #2367, branch fabric-router-codex-oauth-dsh, carries
  dc59c41e97b263a784997a7e0fbe610e304a4dc3. Its tree is
  3d1c015d98b1440d874970108056b58827a2f334.
- Scoped router PR #2369, branch sol/web-capacity-router-resilience-20261109-c4,
  remains a nine-file extension stacked on that original dependency.
- Combined source 01e5c7f302cd9da3922d6296c245de1a68db3830 incorporated the dependency
  repair. This revision adds selection explanations, fixed latency bins and the
  current release procedure to that combined source.
- Registered router qualification workspace:
  /Volumes/Mastermind/agent-workspaces/web/capacity-router-resilience-20261109-c4.
- Registered parent repair workspace:
  /Volumes/Mastermind/agent-workspaces/web/capacity-router-parent-ci-repair-20261109-c4.
  Its local qualification commit 7d778687a41d93e054985eafd1c0291f7f857588 has the
  exact same tree as published dc59c41e. No second parent PR was created.
- Registered Macro fixture workspace:
  /Volumes/Mastermind/agent-workspaces/macro/web/capacity-router-paired-macro-proof-20261109-c4.
  It stays at f38c5b9ea25ea598094a309f0edf48e2722408be, with no Macro source changes.
- The occupied /Users/chriswong/Mastermind checkout and original live release are
  not this operation's editing surface. Preserve other active source/runtime effects.

GitHub owns publication and immutable source evidence. The current assigned session
owns routine recovery; an archived author/chat is not an approval or execution seat.
All source mutations so far have matching readback; no unreconciled source effect
is being moved to another carrier.

## Task tree

| Step | Capability | Current evidence and remaining acceptance |
|---|---|---|
| UR1 | Inspect actual source and live bindings | Exact original generation, route/catalogue and consumer configuration observed |
| UR2 | Local intelligent selection and recovery | Exact models/priority, normalized pressure, soft weighted rendezvous, ceilings and circuit regressions pass |
| UR3 | Request/stream lifecycle | Bounded ingress, terminal-only success, cancellation cleanup and one-send regressions pass |
| UR4 | Explain routing and health | Same-selector trace, local counters, latency EWMA and fixed bins qualified; production observations still owed |
| UR5 | Publish qualified owned source | Ready scoped #2369; original dependency repaired in #2367; hosted required CI remains binding |
| UR6 | Protected release and consumer proof | Not accepted: protected source, safe cutover and actual Hermes/DSH/T3 turns remain owed |
| UR7 | Physical-account capacity composition | Existing APPLICATION owner needs the actual streaming transport and attested physical-account join |
| UR8 | Capability-aware model policy | Reuse owner tri-state/model/transport capability declarations and evaluated substitutions |
| UR9 | Measured adaptive selection | Collect representative evidence and shadow evaluation; automatic weight changes remain off |
| UR10 | Fairness and operations | Existing caller/queue owner supplies fairness; existing service/consumer owners supply drain and real fault proof |

UR7–UR10 are explicit program obligations, not claims of implemented global capacity
or authorization to create parallel owners.

## Implemented behavior

1. Exact model constraints and lowest eligible priority tier remain controlling.
   Within a tier, normalized local in-flight pressure precedes soft weighted
   rendezvous affinity; otherwise the existing weighted random choice applies.
   Zero weight drains a route. No learned model/quality substitution is enabled.
2. Process, route and explicitly declared local group ceilings bound concurrent
   work. The process slot is acquired before body upload and asynchronous auth
   preflight. Defaults are 32 concurrent requests, 30-second body upload deadline,
   1,800-second total admitted deadline, eight-MiB request, 16-MiB response and
   one-MiB unfinished SSE frame.
3. Circuit recovery admits one half-open probe, uses bounded exponential backoff
   and positive jitter, honors provider Retry-After floors, and fences stale
   completions by generation.
4. HTTP headers are not success. Stream/nonstream paths require valid completion;
   truncated EOF, error events, malformed 200s, limits and deadlines fail visibly.
   Cleanup handles disconnect before iteration and midstream, closes upstream and
   releases local permits, with bounded shielded cleanup.
5. Each incoming inference has one upstream send. No redirect, transport retry,
   account rotation or refresh-and-resend follows a possible effect.
6. Tool-only block indexing and Responses tool argument identity are repaired.
   Count-token routing uses an Anthropic-capable transport only.
7. OAuth inference reads the incumbent owner and respects DEAD, unknown exhaustion,
   known quota holds and tokens expiring within 30 seconds. The gateway performs
   no OAuth refresh POST. Owner refresh refusals do not invent quota resets or
   open a circuit. A later request adopts the owner's new token.
8. Observed 429 benches use the existing lock/store and atomic replacement, stamp
   last_status_at, preserve stronger/longer holds, and cannot let an older async
   persistence result shorten a newer local cooldown.
9. Safe route/model/request trace headers and local counters are available. The
   same selector now explains hard exclusions, priority and pressure reductions
   and the actual tie-break without another RNG draw or a reservation.

The retained explicit refresh helper is outside gateway recovery. File locking
does not establish exactly-once remote OAuth refresh after a crash. Overloading
DEAD to mark uncertainty was rejected because the incumbent interprets it as
revoked and may prune it. No new auth status or uncertainty ledger was introduced.

## Diagnostics contract

One bounded historical selection is retained, with sequence and monotonic age.
It contains configured route IDs, counts and fixed enums, never raw model/alias,
caller/session/account identifiers, prompts, credentials or hashes of them.
Alias candidate position/count is numeric. The same exclusion predicate drives
selection and local permit acquisition.

The local selector sees the gateway's preflight-filtered input. Owner-excluded
route counts refer to the current candidate; they are separate from local circuit
and capacity exclusions. An empty input can produce FABRIC_MODEL_UNKNOWN locally
while the actual request returns an owner refusal. Both facts remain distinguishable.
A local permit is not provider admission or send proof; fresh owner reads can still
refuse before inference. Selection-not-run counters never relabel an older choice.

Metric cardinality is bounded by configured routes, fixed outcomes and fixed
latency metrics. Status reads do not rerun selection, draw randomness, read owner
credentials or reserve slots. Latency bins are noncumulative, with inclusive upper
bounds and a final overflow bin. They measure successful completions from local
admission reservation, including upload and preflight. Missing first-content
observations are not zero; failed and cancelled work has separate counters.
These observations do not activate adaptive weights or model substitutions.

## Qualification evidence

- All 107 affected cases pass in scratch Python 3.12.14 and on the actual installed
  M2 dependency set: Python 3.14.7, FastAPI 0.162.2, Starlette 1.10.0, httpx 0.28.1.
  Native process 33306 exited 0; git diff --check passed. The live venv was unchanged.
  The original 33 cases remain included.
- The eleven new diagnostic cases cover disjoint exclusions, priority/pressure and
  affinity, unchanged singleton/random draw counts, alias fallback, fixed cardinality,
  privacy, owner refusal despite empty selector input, status-read purity, preselection
  refusal preserving an older trace, invalid latency samples and success-only bins.
- Earlier combined 01e5c7 passed all 96 resilience cases in native process 64384 and
  the unchanged D8 HEAD source guard in process 64431.
- The actual paired Fabric composition passed all 15 cases in native process 78436:
  tracked Mastermind 01e5c7 plus exact CI Macro fixture f38c5b9ea25ea598094a309f0edf48e2722408be.
  A disposable archive inside the registered SSD workspace loaded the real source
  owners and a local synthetic provider response. No real provider was called.
  Router-only diagnostics do not modify those paired source fixture inputs.
- Distinct reasoning reviews found concrete lifecycle, owner-boundary and telemetry
  pitfalls. Root repaired and self-checked them with focused regressions. This is not
  an authenticated GitHub APPROVED review or release permission.
- Exact new HEAD source guard and hosted CI must be consumed after publication.
  Do not infer protected acceptance from the focused suite.

The original parent repair has separate proof in CAPACITY_ROUTER_PARENT_CI_REPAIR.md:
96 policy/historical-composition cases passed with three pre-existing optional SDK
skips; eight actual APPLICATION transition cases passed; 168 Capacity/Unix transport
cases passed; 241 exact identity/mutation cases passed; original D8 and four dispatcher
cases passed. The parent preserves sealed policy/profile bytes, moves additive helpers
to the existing gateway, mounts the exact query-free Capacity GET transport and
requalifies only unchanged protected source/site fingerprints. It removes 3,924
accidental npm installation files while preserving manifests, locks and application
changes. #2367 now has 56 changed files. No general scanner exemption or historical
provider release repin was used.

## Observed live generation and consumers

The unchanged live service is ai.mastermind.fabric-router on 127.0.0.1:8313.
SOURCE.json identifies source a58c34f1d935ee06e5ef45e77aa5705185398d77 and generation
80141f9373320f8d8f337c8475551bc40665a9676aa0c9776685bee281609035.
Its immutable WorkingDirectory is the release directory of that generation.

Read-only observations showed 14 routes and 45 catalogue entries. Candidate settings
loaded the real environment/table read-only: local max 32, zero shared groups, no
migration required to boot. This is not discovered provider quota.

Hermes model-routes, T3 Capacity Fabric (claudeAgent, 33 configured models), and DSH
desktop/acp/mmx-acp bind the existing Anthropic Messages edge at 8313. Those are
configuration observations, not completed consumer turns on this candidate.

No service restart, provider inference, route-table write, live credential write,
consumer-setting change or runtime generation selection was performed by this task.
The incumbent model_exclusivity_guard.py and route configuration remain untouched.

## Initial safe cutover and rollback

Sanitized loaded-job readback: gui user job, PID 13492 at observation, one worker,
KeepAlive.SuccessfulExit=false, RunAtLoad=true, ThrottleInterval=30, no explicit plist
ExitTimeOut, loaded exit timeout five seconds. The loaded WorkingDirectory and port
listener matched the original generation. Reverify PID/start identity before action.

Installed Uvicorn 0.54.0 handles the first SIGTERM by closing the listener, shutting
down keepalive connections and waiting for active responses/tasks, then lifespan.
Its graceful timeout defaults to None and service.py does not override it. The old
application has no drain endpoint, in-flight count or total request deadline.
SSE keepalives or a partial upload can make its drain unbounded. SIGHUP is not a
single-worker reload mechanism. A launchd stop/bootout can impose its own short kill
budget. A quiet interval and health check do not prove quiescence.

Conditional release sequence through the existing service/consumer owners:

1. Obtain the actual protected merge receipt for this operation; stage that exact
   immutable generation and verify its source/dependencies. Record previous
   generation and service definition as rollback inputs.
2. Establish an effective hold on new submissions across all legitimate consumers,
   including automated retries/background workers. Allow original requests to finish.
3. Reconfirm the original worker identity, send one direct SIGTERM, and observe its
   actual graceful completion. Do not stop/bootout/kickstart it while it drains.
   A stuck request requires original-owner reconciliation, never blind cancellation
   followed by resubmission.
4. Keep ingress held. Reconcile any idle old-generation KeepAlive replacement,
   unload the old definition, verify absence, and select/bootstrap the accepted
   immutable generation. Reconcile any ambiguous control reply on the same carrier.
5. Verify generation, health, authorized status and catalogue. Complete bounded real
   Hermes, DSH and T3 turns, tool/stream behavior and cancellation proof through
   existing owners before restoring ordinary traffic.

Rollback uses the same hold/drain/reconcile sequence and the recorded previous
immutable generation/definition. Never restore stale shared-auth, cooldown or quota
snapshots: changing code does not undo a provider outcome.

This is a prepared operating procedure, not proof that ingress hold exists or that
a runtime action is authorized/admitted. The first safe deployment remains unperformed.

## Remaining owner contracts

Workspace Capacity explicitly declares NONE_PREVIEW_ONLY and admission_authorized=False.
Displayed headroom, preview eligibility and queued waiters cannot grant inference.

The existing APPLICATION Broker performs atomic admission under its lock and SQLite
transaction. GoLeaseGateway owns original selection, begin, immutable prepare,
recovery and settlement. Its qualified contract is nonstream /v1/chat/completions
with registered Go/Bailian HTTP and native CLI transports. It must be extended for
the actual 8313 Anthropic/Responses streaming wire before consuming it here; a fake
nonstream request or direct replacement ledger would bypass its commitments.

True configured aliases share canonical provider/account lease counts. Explicit
quota_scope joins cooldown/recovery probes, but does not by itself prove ordinary
cross-product concurrency consolidation. H3/account-owner attestation must supply
the physical-account join; provider/model names or credential hashes cannot.

Reuse the existing picker's tri-state/model-specific capabilities: required support
must be explicitly true. Fairness needs authenticated caller identity plus the
existing queue/budget owner; caller-supplied consumer labels cannot grant priority.

Required joined proof includes one atomic winner for one shared slot, every required
quota window, missing/stale/conflicting evidence remaining unknown, binding rotation
between selection and admission refusing stale work, retained ambiguous sends across
restart, exact model/capability preservation and original settlement after disconnect.
Local cleanup does not prove release of an unresolved provider-side account lease.

## Release gates and exact next actions

- Consume original #2367 required CI run 42589473107 and the current #2369 exact-head
  checks. Repair real source failures on their original carriers, without duplicate
  runs, empty pushes or moving a denied/unknown effect.
- The GitHub integration's branch-protection read returned 403 Resource not accessible.
  Its exact enforcement remains UNKNOWN, not waived and not an invented approval
  requirement. Do not retry that read through another tool/account/endpoint.
  Public branch metadata confirms protected master and required test; missing actual
  enforcement evidence blocks the dependent auto-merge request.
- The Executive read surface returned backend_unavailable before sending requests.
  That is a transport/control availability fact, not a security denial or a started
  worker. The separate restricted control.json PermissionError remains fenced.
- Never merge #2369 into its unprotected feature base. After #2367 is protected-accepted,
  integrate only the owned nine-file delta with the actual protected source and retarget
  #2369 to master. Preserve old-policy and dependency-tree removals; qualify material
  integration and use the actual protected queue, never direct/self/admin merge.
- Before runtime action, discover and verify the existing ingress hold/service custody.
  Preserve live requests and shared owners. Protected merge alone does not prove a
  safe cutover or completed consumer acceptance.

DO_NOT_REDO: accepted source investigations and unchanged paired proof; new source
does not require another blanket independent review. Reuse exact-input evidence.
Do not recreate the parent branch, restore accidental dependencies, repin sealed
provider commitments, overload DEAD, enable automatic learned weights from fixtures,
multiply Uvicorn workers or infer provider quota from local counters.
