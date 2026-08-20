# Executive OS Pro Sol Slack ingress — CEO admission readiness amendment

**Date:** 2026-08-20  
**Linear:** `MAS-48`  
**Status:** records-only architecture amendment.  
**Precedence:** highest for service/readiness/arming semantics.

## 0. Blocking discovery

The current production Executive control service is not merely a neutral database process with an optional worker attached.

Current `scripts/executive_os_phase1c.py::_service_from_config(...)` constructs the service with:

```text
service_state = AWAITING_CANARY
```

and current `ExecutiveControlService._dispatch_request(...)` allows only `status`, `health`, and `activate-canary` until service state becomes `READY`. Raw `submit-ceo-intent` and all other mutations are refused while `AWAITING_CANARY`.

Current formal Phase 1C-A host acceptance also validates a provider-readiness receipt and refuses when it is missing/stale/invalid. That provider-readiness path is presently blocked by the Codex workspace/auth entitlement problem.

Therefore a Slack ingress merely attached to current `READY` semantics would **not** solve the Chairman's original problem: Pro-Sol writeback would still be indirectly hostage to Codex execution authentication.

## 1. Executive ruling: separate admission readiness from execution readiness

The Executive OS keeps **one process, one runtime, one authority plane**, but it must represent two different capabilities honestly:

1. **CEO admission readiness** — may a bounded high-level CEO request be validated and committed as one canonical QUEUED Job, with no worker execution?
2. **worker execution readiness** — may the supervisor/broker/provider path launch and run that Job?

These are not the same capability and must not share one all-or-nothing readiness gate.

MAS-48 may make CEO admission live while Codex worker execution remains unavailable, provided every boundary below is proven.

This does **not** declare Phase 1C-A worker acceptance passed. It explicitly preserves `CODEX_EXECUTION_REQUIRED=false` for the MAS-48 canary.

## 2. Service-state boundary

Do not weaken or reinterpret existing generic `service_state` semantics for the Operator socket.

Existing Operator behavior remains:

```text
AWAITING_CANARY -> generic mutations blocked
READY           -> reviewed existing command surface available
QUARANTINED     -> mutating path blocked/fail closed
```

The dedicated `CeoIngress` listener gets a separate, narrower host-owned gate:

```text
ceo_ingress_armed = false | true
```

or an equivalently explicit typed readiness object.

Rules:

- default is false / absent = unavailable;
- request/model/Slack content cannot set or widen it;
- `CeoIngress` submit/status require `ceo_ingress_armed=true`;
- ingress is allowed only when generic service state is `AWAITING_CANARY` or `READY`;
- ingress is refused when service state is `QUARANTINED` or any unknown/future unsafe state;
- setting ingress ready does not set generic service state to READY;
- it does not set `supervisor.require_complete_launch_attestation`, register workers, start the broker, load provider credentials, dispatch Jobs, or claim worker readiness;
- Operator socket still refuses raw CEO-intent and generic mutations in `AWAITING_CANARY` exactly as before.

PR-A may model this gate as an injected immutable constructor/policy object for hermetic proof. Production arming and receipt validation belong to PR-C.

## 3. Why bounded CEO admission is independently safe/useful

The existing canonical `control_plane.ceo_intent.submit_intent(...)` path is already structurally submission-only:

- validates a typed CEO intent;
- calls existing `Runtime.jobs.create_job(...)`;
- persists one `JOB_CREATED` event under the existing unique `command_id` law;
- returns `dispatched=false`;
- imports no supervisor/broker/provider execution module;
- does not claim or lease an Attempt.

The dedicated CEO-ingress handler must terminate at this seam.

Therefore the new capability unlocked under admission readiness is exactly:

```text
trusted high-level CEO request
    -> one canonical QUEUED Job
    -> canonical receipt/readback
```

not worker launch.

An existing/manual operator command elsewhere in the estate may later choose to execute eligible queued work; MAS-48 does not widen, automate, or call that path.

## 4. Current control-process startup can be composed without worker execution

The present service startup already opens the Executive runtime and constructs a supervisor while `AWAITING_CANARY`; startup reconciliation is intentionally skipped until READY. `WorkerBrokerClient` construction names a worker-broker socket but does not itself prove provider readiness or launch a worker.

PR-C may therefore compose the **control daemon + CeoIngress** while leaving the worker LaunchDaemon/provider path stopped/unready, subject to its own exact host proof.

Do not solve the problem by starting the Codex worker anyway or by manufacturing a provider-readiness receipt.

## 5. CEO-ingress readiness receipt — production requirement

Before PR-C may arm production ingress, a root/operator-controlled acceptance step must mint and validate a non-secret receipt, recommended schema:

```text
mastermind.executive_ceo_ingress_readiness/v1
```

It binds at minimum:

- exact installed Mastermind release SHA/tree/manifest;
- exact Executive runtime/database identity and health;
- exact control process UID and release/config binding;
- exact dedicated `_mastermind_slack` UID/GID;
- exact `CeoIngress` socket path/owner/group/mode;
- exact accepted ingress protocol/schema version;
- exact trusted Mastermind grounding source;
- exact trusted fresh Macro/Agent-OS grounding source and observed SHA;
- explicit `generic_service_state` observed at proof time;
- explicit `worker_execution_ready` observation;
- explicit `worker_execution_required=false` for ingress readiness;
- proof the Slack principal cannot reach Operator socket/generic dispatcher;
- proof no worker/process is launched by submit/status canaries;
- receipt creation timestamp + exact release/config digests.

No credential/token values enter this receipt.

A changed release, config, socket identity, principal identity, grounding-source binding, or admission protocol invalidates the receipt and forces requalification.

The exact cryptographic/file binding method is PR-C security design; do not invent it casually in PR-A.

## 6. Startup / deployment mode

PR-C's target production topology while Codex remains `AUTH_MISSING` is:

```text
Executive control LaunchDaemon      RUNNING
    generic service state           AWAITING_CANARY (worker execution not accepted)
    Operator generic mutations      BLOCKED by existing law
    CeoIngress readiness            ARMED by separate accepted receipt
    CeoIngress submit/status        AVAILABLE

Codex worker LaunchDaemon           STOPPED / UNREADY
provider readiness                  AUTH_MISSING / not claimed green
worker dispatch                     NOT USED
```

If later worker/provider acceptance succeeds, the same control service may progress to generic `READY` under its existing process. CEO ingress does not need a separate lifecycle database or migration when execution becomes available.

## 7. Quarantine and failure law

A worker-side execution failure must not be hidden merely because CEO admission is independent.

Rules:

- `QUARANTINED` blocks both generic mutations and CEO ingress until operator reconciliation;
- Executive SQLite integrity/foreign-key failure blocks ingress;
- stale/invalid ingress-readiness receipt blocks ingress;
- trusted grounding failure blocks submit; narrowly read-only Slack-intent status may be either blocked with ingress or retained only if a separate review proves safe—V1 default is block with ingress readiness;
- loss of Slack transport does not change Executive service state;
- loss of worker provider readiness does not by itself revoke an already-qualified CEO admission capability, because worker execution is not used by it;
- any code change that makes CEO submission create/claim/dispatch an Attempt invalidates this architecture and must fail tests.

## 8. PR-A requirements created by this ruling

PR-A remains production-unarmed but must prove the state separation in hermetic tests.

Required:

1. ingress gate defaults unavailable;
2. ingress submit/status refused when gate false;
3. with gate true + service `AWAITING_CANARY`, bounded submit/status work while generic Operator mutations remain refused exactly as before;
4. with gate true + service `READY`, ingress still uses the same narrow two-schema surface;
5. `QUARANTINED` blocks ingress;
6. ingress submit produces one QUEUED Job and zero Attempts / worker calls;
7. test supervisor/broker fakes may raise on every start/dispatch operation and valid CEO admission must still pass;
8. no provider credential/readiness input is required by the PR-A pure/local admission proof;
9. no existing test asserting generic AWAITING_CANARY behavior is weakened or deleted;
10. no change to current provider-readiness/Phase 1C-A acceptance claim is made.

## 9. PR-C acceptance consequence

The first real MAS-48 production canary must prove both positive and negative capability at the same time:

**Positive:**

- control daemon is live;
- accepted CEO-ingress readiness receipt is current;
- Pro Sol request creates/reconciles one canonical QUEUED Job;
- Slack user-visible ACK and MCP readback agree.

**Negative:**

- worker provider remains honestly `AUTH_MISSING` if still unresolved;
- worker LaunchDaemon remains stopped/unready;
- no Attempt is created/claimed/launched;
- generic Operator mutations remain unavailable if generic service state is still AWAITING_CANARY;
- no credential mutation occurred;
- `CODEX_EXECUTION_REQUIRED=false` and `WORKER_EXECUTION_OCCURRED=false` are explicit proof fields.

This is the product outcome: CEO cognition/communication works independently of executor entitlement, without pretending execution works.

## 10. No-rebuild / no-bypass boundary

This amendment does not authorize:

- a second Executive service/runtime/database;
- changing generic service state to READY without existing worker acceptance;
- faking or weakening provider-readiness receipts;
- loading/copying Personal Codex credentials;
- direct Slack-daemon SQLite access;
- worker execution from the CEO-ingress handler;
- an autonomous scheduler consuming admitted Jobs;
- treating a QUEUED Job as completed work;
- bypassing QUARANTINED state.

The split is capability-specific readiness inside the existing canonical control plane, not a parallel control plane.
