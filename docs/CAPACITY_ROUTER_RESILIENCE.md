# Capacity Fabric router: current upgrade and acceptance frontier

Parent: Mastermind #983 / WS:EXECUTIVE-CAPACITY-FABRIC.
Operation: capacity-router-resilience-20261109-c4.
Procedure pin: protected master 494d095813dad415938800fa0e4d2719497738fa,
Skillpack 1.0.1. This candidate consolidates current parent c83f8c67d2487a82d98c2ee8a8f75306f73e53a9
and scoped router 2008fd648b75c0cc9d1971c741ab27d72a4f950a on the original
release branch. Parent c83 includes repair e22c3313 and accepted protected source.
Hosted CI demonstrated that the Hermes manual-pool
change was an identity-catalogue dependency, despite initially appearing path-disjoint.
The exact two unchanged reason-limit tokens and whole-file postimage were requalified;
manual pool names still do not establish fleet executor authority.
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

- Release PR #2367 retains branch fabric-router-codex-oauth-dsh. The e22c3313
  repair incorporated accepted 494d0958 and qualified the Hermes identity records.
  Another writer then advanced the branch through a9e4b669 and 010a7200 to
  c83f8c67, preserving e22 and publishing the live per-model/fallback features.
  The earlier auto-merge request, enabled at 10:46:11 UTC for e22, was disarmed
  through its original native owner after this material head change. Process
  78380 confirmed the exact original request before acting and null autoMergeRequest
  and mergeQueueEntry afterward; it did not cancel another writer's CI.
- Scoped router PR #2369 was reconciled at 2008fd64 with no auto-merge request.
  Consolidation commit a59dd17b includes both that head and c83f8c67 as parents;
  64d68b57 removes a trailing blank line found during exact-source qualification.
  The original parent branch moved by expected-head CAS c83f8c67 to 64d68b57,
  followed by ref and PR readback. GitHub automatically marked #2369 merged into
  its feature base on that ancestry update at 11:05:33 UTC. That is source
  consolidation, **not protected release acceptance**. Only #2367's eventual
  protected master receipt can authorize installation of this combined source.
- Previous scoped head b2129832673930b5b4187e0677a67ba3acca18ca added the qualified
  selector explanations and fixed latency bins. This revision preserves those
  features while incorporating the material parent integration and its closed
  public-error literals. It does not revive the parent's former exception echo.
- Registered router qualification workspace:
  /Volumes/Mastermind/agent-workspaces/web/capacity-router-resilience-20261109-c4.
- Registered parent repair workspace:
  /Volumes/Mastermind/agent-workspaces/web/capacity-router-parent-ci-repair-20261109-c4.
  Its prepared index/worktree exactly matches integrated candidate tree 6c52dfd6.
  Local HEAD 7d778687 remains the earlier dc59c41e-equivalent qualification commit.
  The prepared merge is retained; no blind reset/abort or second parent PR is used.
- Registered Macro fixture workspace:
  /Volumes/Mastermind/agent-workspaces/macro/web/capacity-router-paired-macro-proof-20261109-c4.
  It stays at f38c5b9ea25ea598094a309f0edf48e2722408be, with no Macro source changes.
  Current paired proof archives exact CI fixture a82b310ebc1a3cd67547c5a2df6ef5c5fc54bb8c
  into a disposable child directory; synthetic configuration never touches the
  registered source checkout.
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
| UR5 | Publish qualified owned source | Consolidated #2367 preserves both reconciled source heads; GitHub closed #2369 by feature-branch ancestry; protected acceptance remains outstanding |
| UR6 | Protected release and consumer proof | Not accepted: protected source, safe cutover and actual Hermes/DSH/T3 turns remain owed |
| UR7 | Physical-account capacity composition | Existing GLM HTTP seam shares canonical account/model counts; raw streaming, runtime enrollment and cross-product physical-account joins remain owed |
| UR8 | Capability-aware model policy | Reuse owner tri-state/model/transport capability declarations and evaluated substitutions |
| UR9 | Measured adaptive selection | Collect representative evidence and shadow evaluation; automatic weight changes remain off |
| UR10 | Fairness and operations | Existing caller/queue owner supplies fairness; existing service/consumer owners supply drain and real fault proof |

UR7–UR10 are explicit program obligations, not claims of implemented global capacity
or authorization to create parallel owners.


## Live-policy integration and retry adjudication

The Chairman's current instruction assigns this session release leadership through
fully live acceptance. It does not require a separate release operator.

### Subsequent live consumer correction

During qualification the live owner advanced again to local commit
88bc2054c8393cdd080d3937b3267ee9f14be0d2, then installed generation
88bc2054c8393cdd080d3937b3267ee9f14be0d2-drain1. A bounded read of the occupied
checkout found that exact clean HEAD, with only wire.py and its tests changed
relative to c83f8c67. Its commit fixes an actual T3 input shape: inline system and
developer messages, plus empty user text blocks on OpenAI/Responses routes.
The two discriminating cases failed on the consolidated candidate before repair.
This revision preserves that consumer correction on both wires and adds closed
validation: unsupported or malformed inline context is refused, never silently
dropped. Unknown roles remain refused. **195 focused router cases now pass in
scratch**, including twenty cases for this material input contract.

The earlier c0c582b2 auto-merge request at 11:09:35 UTC was reconciled and disarmed
by process 18942 before this material repair; original-target readback confirmed
both autoMergeRequest and mergeQueueEntry null. Requalify and arm the new exact
head once. Prior protected acceptance has not occurred.

The live launchd observation at 11:10–11:12 UTC showed PID 9356, five runs and a
last terminating signal of SIGTERM. Its off-tree service patch uses SO_REUSEPORT
and a 25-second graceful shutdown ceiling. The candidate keeps its single-worker
bounded admission contract; concurrent replacement workers would not share its
local ceilings. The production service has not been signalled or reconfigured by
this session. Verify the incumbent shutdown/supervisor behavior and preserve
active requests before replacing it; the earlier unlimited-drain assumption no
longer describes that current live definition.

A bounded comparison of the newly selected f163d5 release with its predecessor
found router changes in gateway.py, routes.py and service.py. Immutable observed
SHA256 values are:

| Live source | SHA256 |
|---|---|
| gateway.py | a0f57eba36f6e4a300460469dcba870cb897bfb0c9b352b0a09933fa6aa8b3f5 |
| routes.py | 976ff3c7d6dfb2ab06f0bc14309e12bf067535572b13c36a4e0cec83ff5ae226 |
| service.py | 6b17006359b25c619634ce1983daee6855b16adea150e1c77d685cf497385869 |

The current candidate preserves live per-model priorities and weights, cross-provider
distribution, model labels and the OpenAI reasoning-effort override. Strict validation
rejects invalid, duplicate, non-finite, negative or unserved-model policy entries.
Provider tuning cannot overwrite messages, tools, model, stream or authentication.

The live source's retry list included HTTP 401/429/5xx and its OAuth code could
refresh/resend. Those behaviors conflict with preserving possible upstream effects:
zero client response bytes does not prove that an upstream did no work. This
integration retains safe failover and refuses replay after any HTTP response.
The service's HTTPX transport has no SDK/transport retries, redirects or environment
proxies; connection/pool-establishment exceptions are the only transport phases
eligible for the ladder. Connection-error fallback is disabled for every injected
transport: its exception name cannot prove that no request was sent. A real local
HTTPX transport test demonstrates one transmitted inference after a refused first
connection; a deliberately misclassified injected transport proves no replay.

Intermediate failures release the exact route/group/probe permit while retaining
the request's global slot. Selection re-evaluates current local eligibility and
records bounded prior-attempt exclusion counts. Every route is attempted once,
even across alias targets. A local PoolTimeout, credential failure or owner hold
does not poison provider-health circuits. Connect failures use the original circuit
generation fence. Final served/refused/failed/cancelled totals describe client
outcomes; route attempt failures and transport invocation counts remain separate.

Fresh focused tests cover these combined behaviors, including failure-after-send
non-replay for thirteen HTTP statuses and five ambiguous transport errors,
per-model drains and pressure, cross-provider distribution, public-to-wire tuning,
bounded exhaustion, global/group capacity across fallback, cancellation during
fallback admission, alias fallback and one total deadline. Final exact-head M2 and
hosted results belong to consolidated #2367; scratch results alone do not qualify installation.

## Implemented behavior

1. Exact model constraints and lowest eligible per-model priority remain controlling.
   Model priority and weight overrides preserve the current live routing table.
   Within a tier, normalized local in-flight pressure precedes weighted rendezvous
   affinity on one provider, or weighted random distribution across providers.
   Route weight zero drains every model and cannot be undone by a model override;
   model weight zero drains only that model. No learned substitution is enabled.
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
5. A bounded ladder may advance only after local pre-send admission refusal or a
   proven HTTPX connection/pool-establishment failure. No request bytes were sent
   in those transport phases. HTTP responses, write/read ambiguity, truncation,
   cancellation after send and any committed stream never trigger replay. One
   global reservation, request ID and absolute deadline cover every route attempt.
   The default maximum is eight distinct routes; the configuration range is 1–64.
   No redirect, 401 refresh-and-resend or post-effect account rotation occurs.
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
10. Public errors return registered constant reason literals or the fixed fallback.
    Matching-looking unregistered exception text cannot leak through model selection,
    OpenAI conversion, Responses conversion or aggregation error boundaries.

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

- The combined source passes **175 focused cases** in scratch Python 3.12
  (two dependency deprecation warnings). This retains the parent's new per-model
  distribution, parameter and label cases. Conflicting same-request HTTP retry
  assertions now prove terminal responses and later independent-request recovery.
  Exhaustion is tested using two credential refusals with zero network sends;
  injected connection exceptions cannot establish no-send evidence. The ordered
  route compatibility helper projects the same live selector and has a deterministic
  test draw; it adds no second admission path. Failed-attempt counters settle once
  per attempt, including terminal failures and exhausted preflight.
- Exact consolidated **64d68b5774a3b885ca1f26af78531f0eac0f89dc**, tree
  **db7112f6f3ee9d9e3324ef5451c7942c8d84d677**, passed **373 cases on M2**
  (process 92870, exit 0): the 175 router cases plus 198 identity/catalogue,
  negative-control and normal D8 HEAD cases. Four existing dependency/fixture
  warnings were reported. git diff --check passed; the canonical parent proof
  workspace was clean. The installed router, credentials and dependencies were
  not changed. Any later documentation-only clarification preserves this exact
  executable source proof; its own source identity is separately recorded on #2367.
- The earlier parent integration e22c3313 passed 198 exact-source identity,
  negative-control and normal D8 HEAD cases on M2 (process 10378). Its hosted CI
  was superseded by the substantive c83f8c67 update, not accepted for the new head.
  Exact consolidated-head M2 and required hosted results remain publication gates
  and are recorded with the current candidate on #2367.
- The published diagnostic source passed all 107 affected cases in scratch Python
  3.12.14 and on the actual installed
  M2 dependency set: Python 3.14.7, FastAPI 0.162.2, Starlette 1.10.0, httpx 0.28.1.
  Native process 33306 exited 0; git diff --check passed. The live venv was unchanged.
  The original 33 cases remain included.
- The eleven new diagnostic cases cover disjoint exclusions, priority/pressure and
  affinity, unchanged singleton/random draw counts, alias fallback, fixed cardinality,
  privacy, owner refusal despite empty selector input, status-read purity, preselection
  refusal preserving an older trace, invalid latency samples and success-only bins.
- The closed-error integration passes all 117 affected cases in scratch, including
  the parent's ten discriminating privacy regressions. Exact current native router
  and HEAD guard receipts belong to the scoped PR; do not promote the earlier 107
  result to this integrated candidate without its own run.
- Earlier combined 01e5c7 passed all 96 resilience cases in native process 64384 and
  the unchanged D8 HEAD source guard in process 64431. Published b2129832 passed the
  unchanged HEAD guard in process 41610.
- Current actual paired Fabric composition passed all 15 cases in native process 17707:
  Mastermind 307642d2 plus exact CI Macro fixture a82b310e. The four dispatcher and
  eleven paired cases in test_fabric_inference_composition.py include original owner
  admission, revocation, source refusal, usage honesty and no replay after ambiguous
  transport. Both modules resolve to the disposable actual owner. Fixture cleanup
  and unchanged Macro source were verified; no real provider was called.
  This supersedes the earlier 01e5c7/f38c5b9 receipt for changed owner inputs.
- Parent integration passed 230 precise identity cases, 25 Company/installed-wrapper
  cases, TypeScript checking and 77 focused frontend cases. Native auth passed 211
  cases with one existing ignored test in each refresh configuration (processes 6835
  and 11328), bound to immutable candidate 307642d2 after exact-tree verification.
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
changes. The integrated parent has 57 changed files against accepted dd45 source.
Its security regressions reproduced six failures before repair and passed all 43
parent router cases afterward. The two new Capacity/auth tests preserve accepted
primary and work flows while withdrawing stale reads. No general scanner exemption
or historical provider release repin was used.

## Observed live generation and consumers

The service is ai.mastermind.fabric-router on 127.0.0.1:8313. Its earlier observed
source was a58c34f1 / generation 80141f9373320f8d8f337c8475551bc40665a9676aa0c9776685bee281609035.
During release preparation it changed to f163d5f58e0053786a36aa17e4b60c4261baa1d2,
PID 95340, starting at 10:40 UTC. The loaded service definition and SOURCE.json
name that new generation. GitHub did not resolve its commit (422). SOURCE.json
contains only generation, path and source_commit; it does not identify a writer.
This session caused no such deployment or prior SIGKILL recorded by launchd.

Authenticated read-only health/status/catalogue checks of f163d5 returned 200:
18 routes, 49 catalogue entries, three friendly display labels, max_attempts 8.
The configured model-specific distribution and reasoning-effort override are inputs
to this integration. Configuration observations and existing live traffic do not
qualify this candidate or prove global provider headroom.

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
recovery and settlement. Its qualified APPLICATION HTTP contract is nonstream
/v1/chat/completions for registered Go, Bailian and GLM transports. Accepted GLM
HTTP supports fixed glm-5.3 and glm-5.3-flash text/tool requests through the existing
app4 capability, selected profile/account binding and canonical glm account/model
budget. It preserves reasoning_content for tool continuations and declares no
vision or streaming. The facade delegates to the original gateway and journal;
8313 enrollment, current grant and installed native generation remain unproven.

The actual 8313 Anthropic/Responses streaming wire needs an extension of that
owner's prepare, terminal, unknown-effect and release contract before integration.
A fake nonstream request or replacement ledger would bypass those commitments.
Prove the existing GLM HTTP/native shared-account cap first through the common
owner, then separately qualify cross-product physical-allowance consolidation.

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

- Consume exact consolidated #2367 checks. Earlier parent run 42589473107
  and scoped run 42592443374 remain bound to their original dc59c41e/b2129832 heads;
  pending or successful old checks do not qualify this material integration.
  Repair real failures on their original carriers, without duplicate runs, empty
  pushes or moving a denied/unknown effect.
- The denied administrative branch-protection read remains closed; no alternate
  account/tool/endpoint is used for that resource. Separate permitted reads establish
  protected master with required test from GitHub Actions app 15368, enforcement
  everyone, and native merge queue MQ_kwDOTotz3c4ABAiK. Candidate-specific preflight
  verified Ready, exact head/base, no blocking review/hold, resolved CodeQL threads,
  pending trusted checks and empty autoMergeRequest/mergeQueueEntry. Installed gh
  confirms the native --auto path keeps required checks and queue in force.
  The head-leased e22 request at 10:46:11 UTC was reconciled and disarmed after
  the material c83 head change. Qualify the consolidated candidate, read its
  actual queue/hold/check state and request native protected release once for
  that exact head. No --admin, direct merge or fabricated formal approval is used.
  Read the actual merge and integrated checks before protected acceptance.
- The Executive read surface returned backend_unavailable before sending requests.
  That is a transport/control availability fact, not a security denial or a started
  worker. The separate restricted control.json PermissionError remains fenced.
- #2369's automatic feature-base merge is not a release receipt. The consolidation
  preserves both source heads in #2367's history and publishes the complete upgrade
  to that original protected-release PR. Record #2369 as consolidated, with no
  protected acceptance or deployment claim. Preserve old-policy and dependency-tree removals; qualify the combined
  diff and use the actual protected queue, never direct/self/admin merge.
- Before runtime action, discover and verify the existing ingress hold/service custody.
  Hermes' existing global pause holds new cron, kanban and gateway turns, including
  CLI/TUI/Desktop turns, while running turns finish. Preserve any preexisting pause.
  It does not hold DSH or T3 submissions. Preserve live requests and shared owners. Protected merge alone
  does not prove a safe cutover or completed consumer acceptance.

DO_NOT_REDO: accepted source investigations and unchanged paired proof; new source
does not require another blanket independent review. Reuse exact-input evidence.
Do not recreate the parent branch, restore accidental dependencies, repin sealed
provider commitments, overload DEAD, enable automatic learned weights from fixtures,
multiply Uvicorn workers or infer provider quota from local counters.

## Terminal receipts for consumer correlation (2026-11-10)

The router emits one best-effort `FABRIC_TERMINAL` JSON record from its existing
idempotent request settlement boundary. The record uses schema
`fabric_terminal_v1` and the existing Uvicorn/launchd log sink. Only the router
logger is enabled at INFO; no new service, watcher, queue, credential store or
usage ledger is introduced. Failure to format or emit this observation cannot
change inference, retry decisions, cancellation or permit cleanup. A missing
receipt remains missing evidence.

| Fields | Meaning and limit |
| --- | --- |
| `request_id`, `process_id`, `settled_unix_ms`, `duration_ms` | Router request identity, process and terminal observation timing. |
| `gateway_source_sha256` | Cached SHA-256 of this gateway source file, or null if unreadable. It is not an attestation of the entire loaded release, dependencies or configuration. |
| `route_id`, `model`, `wire` | Final selected configured route and resolved model after any proven pre-send fallback. No account or credential fields are collected. |
| `operation`, `outcome`, `reason` | Messages versus count_tokens, existing served/failed/refused/cancelled outcome and a closed router reason or HTTP status. |
| `upstream_send_started` | Possible upstream transmission; not provider admission or settlement. |
| `response_id_sha256`, `response_id_state` | Router-produced client message ID digest; observed, unavailable, invalid or conflicting. |
| `upstream_response_id_sha256`, `upstream_response_id_state` | Separately observed protocol response identity, with the same states. HTTP, event, item and tool-call IDs are not substituted. |
| `usage` | Nullable input/output/cache-read/cache-creation counts reported upstream. Preserve the wire's cache inclusion semantics; do not add a fabricated total. |
| `usage_source`, `usage_state`, `usage_invalid_fields` | Upstream-reported versus unavailable; reported/partial/unavailable state and fixed names of fields with invalid reports. Reported does not assert complete field coverage or final provider metering. |
| `input_token_estimate` | Separate utility estimate for count_tokens, which does not become inference usage. |
| `cost_usd`, `cost_status` | Null and unknown; no inferred billing settlement. |

An identity digest is lowercase SHA-256 of the complete, unmodified UTF-8 ID,
bounded to 1–256 encoded bytes. IDs are never trimmed, normalized, truncated or
retained as raw receipt text. Invalid/unencodable values and conflicting IDs
make that semantic identity unavailable for a join; conflicting/invalid states
are sticky for the request. Translated client IDs are fixed from the router UUID
before the first emitted event and remain distinct across requests, including
when a Responses upstream ID arrives only in its terminal event. Direct
Anthropic bytes and tool-call/function-call IDs remain unchanged. A coalesced
SSE error cannot claim a downstream message ID from bytes that were not forwarded.

Usage merges latest cumulative observations rather than summing them. Explicit
integer zero is preserved; missing/null updates do not erase earlier values.
Booleans, strings, floats, negatives and values beyond the signed 64-bit count
range are not measurements. Invalid reports are flagged; retained earlier counts
remain partial. Failed/cancelled requests with observed usage are also partial.
HTTP error bodies and translated synthetic zero defaults are not usage evidence.

For real consumer acceptance, locally hash the actual completed Hermes Message ID
and require exactly one matching client-ID digest in the bounded receipt records.
Join that record to its router request, final route and reported usage, and retain
the native terminal task/usage evidence. Duplicate IDs, absent receipts or
conflicting identity cannot be resolved by approximate timestamps. This proves
consumer/router correlation; it does not prove an upstream provider's physical
account lease, billed cost or settlement. A served model response is not proof
that the assigned user task completed.

The exact source candidate before MCP compatibility composition passed all 212
affected offline cases on native Python 3.14.7 with the existing production
httpx/FastAPI/Uvicorn dependencies. The existing pure-Python pytest package was
borrowed from the user's Python 3.12 installation; no package or service was
installed or changed. The exact-source log is SHA-256
`a4c5989719ccaa671cba537e0e370deb65507994d672e2979b0890127a9073b5` and JUnit is
`4336d4687eb2e01603b4609c5a4e9910a8cf52e57ac3f269458ca7b4e63f76c5`, completed 2026-11-10T07:32:34.434122+00:00.
Earlier export qualification also passed the same 212 cases on Python 3.12.10;
these are the same cases, not additive totals. The final combined source qualification is recorded below; required-check and
consumer receipts remain separate.

Fresh inspection also found that the serving mcpfix1 source files had changed
under their existing directory label. Neither that label nor an on-disk hash
proves which bytes an existing process loaded. Preserve current service/writer
custody and reconcile legitimate MCP block compatibility before replacement.
Raw tool-argument logging and permissive malformed-argument coercion from that
live delta are not adopted by this terminal-receipt change. The original
hold/drain/reconcile sequence and live consumer acceptance remain required.

### Qualified MCP history composition

Both translated wires now normalize completed MCP call/result history through
existing ordinary tool-call and tool-result shapes. Exact call IDs, validated
function names and object inputs survive. An explicit legacy tool_name is accepted
only without a conflicting name; a server label never becomes a function name.
Inline assistant results move to their actual tool-result channel. Server metadata
and explicit is_error values remain in a deterministic JSON result envelope.
Parallel results may arrive in reverse call order. Visible text after an unresolved
call, duplicate/orphan IDs and incomplete exchanges refuse instead of being
reordered or completed with invented data.

The bounded mapping accepts text results. Unsupported rich results, active
mcp_servers/mcp_toolset configuration, unknown server execution and container state
refuse before translated inference. Direct Anthropic passthrough is unchanged.
Opaque assistant thinking/redacted_thinking follows the existing cross-provider
omission policy; the same blocks in other roles still refuse. Invalid roles,
content and tool collections cannot disappear through normalization. All five
response-side malformed-argument parsers retain strict JSON refusals without raw
argument logging or a fabricated _raw_arguments input object.

The protocol basis is the [MCP connector](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector),
[server-tool lifecycle](https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools)
and [tool-result handling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
contracts. This maps completed history and does not introduce a server-tool executor.

The final composition passes **295 affected offline cases** on the actual native
Python3.14.7 router dependency set, completed 2026-11-10T07:45:12.030370+00:00.
This includes the earlier212cases; totals are not added. Log SHA-256:
`f3575f1759fd9040edfcbbe0c53bd95b782ac409e93174d87f0d53b6589d4e99`; JUnit:
`d42b662e3d41b22e20f58f3daf5b83a9b6734b2c6538b62b39df83e59a9bf745`. Six changed Python files also pass whitespace checks.
The source qualification manifest is
`review_evidence/fabric_router/2026-11-10-paperclip-consumer-receipts.json`.
Protected checks, fresh installed-source/controller custody, safe cutover and real
consumer acceptance remain separate requirements. No live model call or runtime
change was made during this qualification.
