# Unified Capacity Fabric router: resilience and intelligent selection

Parent: Mastermind #983 / WS:EXECUTIVE-CAPACITY-FABRIC.
Operation: capacity-router-resilience-20261109-c4.
Procedure: protected master ff6d5ab67c3535056d69f603fac0d95c058baad8, Skillpack 1.0.1.
Source input: a58c34f1d935ee06e5ef45e77aa5705185398d77 (PR #2367).
This is a scoped extension of the installed unified router, not a replacement allocator,
quota registry, credential store, queue or Executive runtime.

## Outcome and acceptance

Make the shared M2 routing edge reliable under concurrent Hermes, DeepSeek Harness
and T3 traffic, with truthful health, bounded overload and deterministic recovery.
DONE_WHEN: the qualified source passes affected regressions; the normal protected
release path admits it; the installed generation exposes the new behavior; all
three consumers retain their existing endpoint/model contracts and real-path proof.
Source qualification, merge, installed generation and consumer acceptance are separate.

## Recovered live facts

The M2 launchd service ai.mastermind.fabric-router listens on 127.0.0.1:8313.
Its SOURCE.json identifies a58c34f1 and generation
80141f9373320f8d8f337c8475551bc40665a9676aa0c9776685bee281609035.
Read-only health/status/catalog requests succeeded: 14 routes and 45 catalog entries.
The shared source checkout is clean at that commit; no edits are made there.
This operation uses the canonical mmx-workspace isolated branch, not the #2367 writer.
Existing #2338 backend integration, #2351 OS projection, #2366 Anthropic gateway and
#2182 unresolved publication retain their distinct scopes and effects.

## Task tree

| Task | Work | Acceptance | Dependency |
|---|---|---|---|
| UR1 | Verify installed source, current routing and failure behavior | Exact generation, endpoint observations, concrete source findings | None |
| UR2 | Extend existing RouteState selection and circuit control | Tier/weight/affinity contract, load bounds, one half-open probe, provider retry timing, concurrency regressions | UR1 |
| UR3 | Unify request settlement and streaming cleanup | Success only after completion; cancellation/transport/protocol failure closes resources; no invisible replay | UR2 |
| UR4 | Make route health and decisions inspectable | Monotonic cooldowns, in-flight/circuit/counters/latency, bounded safe reason codes; no credentials or prompts | UR2–3 |
| UR5 | Qualify and publish one owned diff | Existing and new adversarial tests, exact-head diff, Ready source PR with dependency/holds preserved | UR2–4 |
| UR6 | Protected release and installed consumer acceptance | Exact approved release, graceful installation, Hermes/DSH/T3 real-path evidence | UR5 and upstream release |

## Concrete source findings to repair

- /statusz uses wall-clock time against monotonic cooldown values.
- Several forwarding paths declare success at HTTP headers before stream completion.
- Anthropic passthrough closes upstream only on normal completion, not cancellation.
- Selection has no local in-flight pressure or bounded half-open recovery.
- OpenAI and Responses streaming paths can emit successful terminal frames at EOF
  without verifying the provider's actual completion.
- OAuth Responses forwarding retries across accounts after 5xx, contrary to the
  documented no-replay-after-possible-effect boundary.
- Refresh helper constructs its client from an out-of-scope variable.

All findings require focused reproductions before their repairs are claimed.

## Design constraints and reuse decision

Keep hard admission, quotas and account identity with their incumbent owners.
The router may limit its own process concurrency and health probes; these are local
bulkheads, not claims of remaining five-hour/weekly/monthly provider allowance.
Preserve exact-model constraints and current priority tiers. Affinity cannot override
an unavailable or saturated route. Measure latency before enabling any adaptive weight changes; a future bounded
latency tie-breaker must follow eligibility and evaluated quality. Never promote
an unknown lower-quality model.

Reuse httpx/FastAPI and the current route/state/service interfaces. LiteLLM/Envoy
patterns inform this extension; importing a second gateway would duplicate live
credential and policy owners. Atomic shared-account quota integration remains with
the existing Capacity/Executive lanes, not a guessed quota ledger here.

No new paid provider, credential import, default model change, provider-limit bypass,
duplicate watcher, or request replay is authorized by this plan.

## Execution ownership

Principal retains this coupled source/stream-lifecycle repair: PRINCIPAL_JUDGMENT
and LOWER_TOTAL_OVERHEAD while freezing the exact-effect boundary. A separate native
reasoning reviewer covers architecture and adversarial analysis, not routine labor.
WHY NOT FABLE: the bounded router extension has a concrete source and test surface;
it does not need another principal or a cross-program handoff.

## Evidence and release frontier

Initial workspace creation was NOT_APPLIED / INVALID_ARGUMENT because the canonical
source object was not yet serviceable. A read of that exact commit materialized it;
the same owner then acquired the same operation successfully. No source effect was
replayed or moved. Implementation, tests, publication and installation are pending.

## Verified implementation milestone

The scoped candidate now implements local load-aware selection, explicit group/global
bulkheads, bounded half-open probes, generation fencing, Retry-After handling,
terminal-only success accounting, cancellation-safe response ownership, bounded SSE
framing, one-send OAuth inference, and tool-call translation repairs. The original
33 tests plus 43 new regression cases passed in the scratch Python 3.12 runner and
on M2 Python 3.14.7 (76/76, native process 88815 exit 0). The live router's isolated
runtime venv contains no pytest; its dependencies were not altered. The M2 test run
used the already provisioned /opt/homebrew/bin/python3 runner.

Adversarial source review found account cooldown overwrite, refresh clearing quota
holds, tool-only block indexing and false non-stream 200 success. Those four findings
were repaired and exercised by the 76-case set. Bounded refresh lock/deadline and
atomic auth-store write improvements are the next safe source phase; no live
credentials, consumer settings, service, provider or release selection changed.

## Current qualified candidate — 2026-11-09 00:18 America/Vancouver

UR1–UR4 are implemented and qualified in this isolated source operation.
UR5 is published as Ready PR #2369, scoped against the original #2367 source.
UR6 remains unaccepted; the live source is still
a58c34f1. The parent DONE_WHEN is not met.

### Final behavior and proof

- 91 affected tests pass in scratch (Python 3.12.14) and in the actual M2
  router runtime (Python 3.14.7, FastAPI 0.162.2, Starlette 1.10.0, httpx 0.28.1).
  The latter uses existing pytest dependencies appended after the live venv;
  no live dependency or running service was changed. Native process 29943
  completed with exit 0. Original 33 tests remain passing.
- Tests cover bounded concurrent admission, weighted pressure and affinity,
  explicit group ceilings, single half-open probes, stale generation fencing,
  provider Retry-After, EOF/error/keepalive/size failures, disconnect before and
  during iteration, response cleanup, exact one inference send, tool argument
  identity, owner holds and atomic account benches.
- The distinct reasoning review found tool-only index, malformed success,
  owner-hold and post-await deadline races. Repairs are covered by focused
  regressions. The last bench regression overlaps two sends and delays both
  persistence returns; an earlier completion cannot shorten the newer
  7,200-second local hold. This is technical reasoning evidence, not a native
  GitHub APPROVED review.
- The production request path performs no OAuth refresh POST. Known-expiring
  accounts are excluded before inference; eligible alternatives can be chosen
  before send. If all usable accounts require rotation, the response is
  FABRIC_OAUTH_OWNER_REFRESH_REQUIRED with no invented reset or circuit penalty.
  A subsequent request reads the auth owner's rotated token.
- This supersedes the earlier preflight-refresh implementation milestone.
  An uncertain rotating-token outcome has no suitable incumbent owner fence;
  overloading DEAD was rejected because Hermes treats it as revoked and may
  prune manual DEAD rows after 24 hours. No new auth ledger/status is added.
  The retained explicit helper remains outside gateway recovery and cannot
  claim exactly-once remote refresh.
- Observed 429 benches use the existing lock/store, atomic replacement,
  last_status_at merge timestamp, non-shortening reset and stronger-hold
  preservation. Local post-await reconciliation includes the newest local value.

### Consumer and deployment observations

- Hermes model-routes plugin constructs an Anthropic Messages route to
  127.0.0.1:8313 using the current catalogue and internal token reference.
- T3 capacity_fabric is enabled with driver claudeAgent, the same endpoint and
  33 configured model entries. It retains its existing provider home.
- DSH desktop, acp and mmx-acp profile patches contain the same endpoint and
  anthropic-messages protocol.
- Read-only OAuth eligibility metadata: 5 owner rows, 3 eligible access tokens,
  2 quota-held rows, 0 known-expiring and 0 owner-dead rows at observation.
  This is a snapshot, not a quota guarantee.
- Installed SOURCE.json remains generation
  80141f9373320f8d8f337c8475551bc40665a9676aa0c9776685bee281609035,
  source a58c34f1d935ee06e5ef45e77aa5705185398d77. No service restart,
  provider request, credential mutation, route-table write or consumer-setting
  change was performed by this operation.

The candidate also loaded the real M2 router environment and route table in a
read-only process: 14 routes, 45 catalogue entries, local maximum 32 and zero
configured shared groups. Existing route configuration needs no migration to boot.

These are binding/configuration observations and offline qualification, not
proof of a completed real consumer turn on the new candidate.

### Concrete release dependency

PR #2367 is still open at a58c34f1 and targets protected master ff6d5ab6.
GitHub reports 23 commits, 3,973 changed files and 816,847 additions; its
inherited history includes other active integration surfaces and bundled
node_modules. The router tests do not qualify that entire inherited diff.
This operation must remain a scoped stacked diff against #2367 until its
upstream source/release dependency is reconciled. Do not auto-merge into the
unprotected feature branch or deploy this branch head.

The assigned capacity mission retains recovery responsibility: inspect the
original dependency carriers and active custody, qualify/repair their actual
source scope on those carriers, then use the protected merge queue. Retarget
this scoped PR after its source dependency is protected-accepted, obtain actual
required checks/holds, install the exact accepted release through the incumbent
launchd generation mechanism, and prove real Hermes/DSH/T3 turns and cancellation.
No archived author/chat is a required recipient.

### Next intelligence work within existing owners

| Step | Capability | Required acceptance |
|---|---|---|
| UR7 | Physical-account capacity composition | Existing owner provides fresh account identity, quota window/reset and atomic admission; aliases cannot multiply one account's allowance |
| UR8 | Capability-aware model policy | Explicit task/context/tool requirements; evaluated model quality and allowed substitution; exact model requests remain exact |
| UR9 | Measured adaptive selection | Representative latency/error/load samples, shadow comparison and bounded changes after hard eligibility; no learned policy enabled from mock tests |
| UR10 | Fairness and operations | Existing queue owner supplies caller fairness and budgets; existing deployment owner supplies graceful drain/restart/rollback and real consumer fault proof |

UR7–UR10 are explicit unimplemented program obligations, not claims of delivered
capacity, new controllers or authorization to infer provider limits. They extend
the same parent #983; no second quota/auth/queue/workstream registry is created.


## Request-body admission and predecessor recovery — 2026-11-09

A further fault reproduction showed that partial uploads held body buffers before
the process concurrency slot. Admission now reserves the same global slot before
the first body read, with a separate 30-second configurable body deadline inside
the total request deadline. Timeout, task cancellation, ASGI disconnect and deeply
nested invalid JSON release local resources without an upstream send or circuit
penalty. The existing size limit remains eight MiB.

The affected suite is now **96 passing tests** in scratch Python 3.12.14 and the
exact installed M2 dependency set (native process 7010, Python 3.14.7 / FastAPI
0.162.2 / Starlette 1.10.0 / httpx 0.28.1, exit 0). The new upload regressions
reproduced the missing admission/cancellation boundary before repair.

Hosted CI at source 08917fc4 (run 42585309236) independently reproduces the
predecessor's immutable provider APPLICATION lineage failure. It is not green.
The source repair is being qualified under operation
capacity-router-parent-ci-repair-20261109-c4 in its own registered workspace;
the six temporary predecessor files have been verified there and restored out
of this scoped router workspace. Original #2367 remains the publication carrier.

Qualified predecessor repairs so far preserve the exact protected policy/profile
bytes, move additive Anthropic helpers into the existing gateway, and register
the exact query-free Capacity GET path in the existing transport. Focused proof:
96 passed / 3 existing SDK-dependent skips for policy and historical composition,
8 actual APPLICATION transition cases passed, and 168 capacity/transport cases
passed including Unix authentication and expiry. These do not qualify the entire
predecessor or authorize runtime installation.

The predecessor also accidentally tracks 3,924 dependency files in two existing
npm installation directories. Both manifests and lockfiles match protected source;
the source-only repair will remove those tracked trees while preserving the
declared npm-ci installation and other app-control changes. Source/site review
fingerprints are being requalified only where the original protected functions,
literal values and negative controls remain exact. No scanner-wide exemption,
identity/default change, provider release repin, or protected gate bypass is
part of this work.

Protected master advanced from the procedure pin to 3652d890 through the disjoint
Hermes GitHub-plugin change. Applicable procedure bytes are unchanged; the source
qualification above still states its exact input and runtime. The original live
router and consumer configuration remain unchanged by this operation.


## Original predecessor repaired and composed

Original #2367 now carries dc59c41e97b263a784997a7e0fbe610e304a4dc3.
Its tree 3d1c015d98b1440d874970108056b58827a2f334 matches the native qualified
repair tree exactly. The PR has 56 changed files after removing the 3,924
accidental dependency files; all declared manifests/locks and application
changes remain. Its source repair, tests and custody are recorded in
docs/CAPACITY_ROUTER_PARENT_CI_REPAIR.md and the original PR body.

This scoped branch composes that original repair with the already qualified nine
router files. This is a material dependency repair: it restores immutable provider
commitments, fixes the Unix transport path and removes the accidental dependency
installations. It is not an ancestry-only refresh or another publication carrier.
Combined-source qualification and protected release still apply.

The exact original D8 HEAD guard passed on native repair commit 7d778687,
as did four dispatcher tests. Ordinary discovery skipped the eleven paired
cross-repository tests; their explicit required CI step remains owed. Do not
reinterpret those skips as a paired consumer proof.

### Existing-owner integration findings for UR7–UR10

The Workspace Capacity view is explicitly NONE_PREVIEW_ONLY and requires
admission_authorized=False. Its displayed headroom, preview eligibility and
queued waiters must never grant an inference slot.

The existing APPLICATION Broker owns atomic admission under its file lock and
SQLite transaction. GoLeaseGateway mediates original selection, begin, immutable
prepare, recovery and settlement. Its current admitted contract is nonstream
/v1/chat/completions with registered Go/Bailian HTTP and native CLI transports;
that is not an admitted raw Anthropic/Responses streaming contract for 8313.
Extend that owner contract and its recipe/capability bindings before using it
for this edge. Never fake a nonstream request or directly create another ledger.

Actual configured pool aliases already share the canonical provider/account
lease count. Explicit shared quota_scope also joins cooldown and recovery-probe
holds, but the inspected ordinary account count remains provider/account-local.
Matching scope strings alone do not prove a shared cross-product concurrency
budget. H3/account-owner attestation must supply that physical-account join;
provider/model names and credential hashes are not substitutes.

The existing picker has tri-state, model-specific capability semantics: a required
capability must be explicitly true. Reuse its owner declarations and transport
needs, without creating another editable model table. Caller fairness likewise
needs an authenticated owner identity and the existing queue/budget controls;
a caller-supplied consumer label cannot authorize priority.

Acceptance for those phases includes one atomic winner for one shared slot,
retained uncertain effects across restart/rotation, every required quota window,
stale/missing/conflicting evidence as unknown, exact-model/capability preservation,
and original owner settlement after streaming disconnect. Local resource cleanup
does not establish release of an unresolved provider-side account lease.

Safe routing-side follow-up can make the same selection code's exclusions and
tie-breaks inspectable and measure a shadow policy without additional provider
calls. Adaptive production weights require representative evidence and evaluated
model quality; synthetic tests cannot enable them.
