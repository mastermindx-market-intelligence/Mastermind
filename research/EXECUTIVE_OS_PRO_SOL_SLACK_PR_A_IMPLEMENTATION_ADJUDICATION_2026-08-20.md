# Executive OS Pro Sol Slack ingress — MAS-75 PR-A implementation adjudication

**Date:** 2026-08-20  
**Linear:** `MAS-75` (child of `MAS-48`)  
**Status:** **RECORDS-ONLY / IMPLEMENTATION LAW. NO RUNTIME IS ARMED OR IMPLEMENTED BY THIS FILE.**  
**Delivery base:** Mastermind `a49ac647fff64d034cc965cf54ac48968d6c15be`  
**Parent architecture:** Mastermind PR #91, merged as `e61e48904302d0aae53baeab0e2681ee3fbec97d`  
**Authority:** Sol CEO implementation adjudication under the Chairman-approved Mastermind-X operating hierarchy.  

## 0. Purpose and precedence

PR #91 froze the product/system architecture for the first independently useful
Personal-Pro Sol writeback vertical:

```text
Pro Sol
  -> read-only Executive MCP preflight
  -> Slack #ceo-control-room
  -> dedicated Slack transport
  -> dedicated Executive CeoIngress AF_UNIX surface
  -> existing control_plane.ceo_intent.submit_intent
  -> one canonical QUEUED Job + JOB_CREATED
  -> Slack ACK + existing MCP readback
```

Subsequent source archaeology and adversarial implementation review closed several
lower-level questions that were intentionally left open in #91: the exact Slack
intent namespace, how the existing MCP normalization law is shared without
changing its contract, the exact grounding/replay ordering, how a second AF_UNIX
listener shares one Executive process/runtime/lock, and how timeout/shutdown
semantics avoid lying about a possibly committed SQLite mutation.

Those rulings initially lived in Linear because MAS-75 is the portfolio execution
record. That is not a sufficient canonical home: Linear is a projection, not the
source of architecture. This document makes the accepted PR-A implementation law
recoverable from the Mastermind repository itself.

For **MAS-75 / PR-A implementation mechanics**, this file is more specific than
PR #91 where it names an exact constant or closes an implementation ambiguity.
It does not replace #91's product/system architecture, widen authority, or modify
any durable/runtime state.

The later Phase 1F-C source-law records (#94/#95) remain separate authority for
their future strict `mastermind.ceo_intent.v2` + schema-v4 program. PR-A is
explicitly **v1-only** and may not preempt that future work.

If a Phase 1F-C runtime implementation lands before PR-A merges and changes
`control_plane/ceo_intent.py`, `control_plane/executive_runtime.py`, or overlapping
authority tests, the PR-A builder must STOP and return for semantic reconciliation.
Do not resolve that collision mechanically.

---

## 1. Observable PR-A capability

One hermetic local caller, shaped like the future Slack daemon but requiring no
Slack SDK or network, must be able to:

1. connect to a **dedicated** AF_UNIX `CeoIngress` listener;
2. authenticate as one exact configured local UID before request-body parsing;
3. submit one bounded high-level CEO request plus the grounding Sol observed;
4. have trusted Executive code normalize and derive all privileged v1 fields;
5. reconcile a prior accepted Slack intent before consulting current grounding;
6. for a new intent, independently observe current grounding, require equality,
   and re-observe immediately before the first canonical mutation;
7. call the existing `ceo_intent.submit_intent(...)` sink exactly as the durable
   mutation authority;
8. obtain one canonical receipt naming one QUEUED Job and `dispatched=false`;
9. query that same intent through a second, read-only, Slack-ID-only ingress frame;
10. do all of the above while generic service state is `AWAITING_CANARY`, with
    the existing generic Operator mutation surface still blocked and with zero
    worker/Attempt/provider execution.

This is a hermetic vertical. Production Slack transport and host arming remain
PR-B and PR-C respectively and are **not authorized by this document**.

---

## 2. One-system / no-rebuild boundaries

PR-A must preserve all of these:

- Executive SQLite remains the sole Job/Attempt/Worker/Event lifecycle authority.
- `control_plane.ceo_intent.submit_intent` remains the canonical v1 mutation sink.
- `events.command_id UNIQUE` remains the durable idempotency authority.
- No new SQLite table, database, queue, dedupe map, mutable request registry,
  grounding store, replay cursor, Slack inbox, seat inbox, scheduler, or lease is
  created.
- The raw `mastermind.ceo_intent.v1` envelope is internal Executive data, not a
  network-facing Slack contract.
- The Slack principal never connects to the broad Operator socket and never
  reaches its generic `_dispatch_request` command surface.
- No Wake import/call/persistence/repair/arming.
- No worker registration, Attempt creation/claim, broker/provider start, dispatch,
  Job completion, merge/deploy/service-control, or credential mutation.
- No Agent OS, Linear, GitHub, or Slack API mutation from PR-A runtime code.
- No production JSON/config schema, launchd plist, installer, UID/GID, secret,
  token, OAuth, or production socket-permission work.
- No MCP public tool/schema/ID migration merely to support Slack.
- No Slack transport metadata is added to canonical `JOB_CREATED` provenance in
  v1 merely for convenience. Transport evidence belongs to PR-B/PR-C proof.
- No `intent_kind`, `business_impact`, orchestration role, COO-cycle provenance,
  Phase 1F-C review/fan-out policy, or schema-v4 behavior enters the PR-A request.

### Strong default-no-edit surfaces

Unless implementation discovers a concrete blocking invariant and returns it to
Sol first, PR-A should not edit:

- `control_plane/ceo_intent.py`;
- `control_plane/executive_runtime.py`;
- production `scripts/executive_os_phase1c.py` config schema;
- `ops/executive_os/install.sh` or launchd/host acceptance code;
- `config/authority_map.yml`;
- Wake, worker, provider, broker, or Operator Harness modules;
- `.github/workflows/ci.yml` merely to wire new tests;
- `pyproject.toml` merely to package new `control_plane` modules.

The existing v1 sink/runtime are already sufficient for the capability.

---

## 3. Preferred bounded code surface and import graph

Exact class/function names remain builder-owned, but the preferred shape is:

```text
control_plane/ceo_request.py
    pure high-level CEO_REQUEST_V1 normalization + v1 derivation
    imports: stdlib + first-party control_plane.ceo_intent as needed
    MUST NOT import integrations.executive_mcp or Slack/MCP SDKs

control_plane/executive_ceo_ingress.py
    closed submit/status frame validation
    trusted-grounding/replay/admission logic
    dedicated response/error law
    imports ceo_request + ceo_intent + first-party runtime/authority types
    MUST NOT import executive_service (avoid circular authority/composition)

control_plane/executive_service.py
    owns platform AF_UNIX peer credential helper and service lifecycle
    thin dedicated ingress connection wrapper authenticates exact peer UID
    then delegates to an authenticated ingress protocol handler
    owns second-listener startup/close + ingress-handler drain set
    generic Operator handler/_dispatch_request stays unchanged

integrations/executive_mcp/schemas.py
    public MCP surface remains frozen
    may delegate submit normalization/derivation to ceo_request
    preserves all existing public names/re-exports/messages/schema bytes

integrations/executive_mcp/adapter.py
    only minimal wrapper/refactor needed to consume shared v1 derivation
    existing MCP behavior remains byte/semantic compatible
```

The platform-specific `_peer_uid` logic should remain owned by the existing
service/composition layer rather than being copied into the ingress module. A thin
`ExecutiveControlService` ingress callback may authenticate the socket using that
existing helper and then call an `handle_authenticated(...)`-shaped ingress
method. This keeps security logic shared without introducing
`executive_service <-> executive_ceo_ingress` imports.

New test files should preferably use the protected Executive naming prefix:

- `tests/test_executive_ceo_request.py`
- `tests/test_executive_ceo_ingress.py`

and may extend existing service/MCP tests where that proves compatibility better
than a parallel harness.

---

## 4. High-level CEO_REQUEST_V1 law

`control_plane.ceo_request` is a first-party **Python normalization/derivation
law**, not a new serialized public protocol.

The nested high-level request object has **no** `schema`, `version`, transport,
`intent_kind`, or other discriminator. Existing MCP continues to accept its exact
current no-schema input object; CeoIngress versions Slack through its outer frame.

### 4.1 Required/optional business fields

Required:

- `operation_key`
- `objective`
- `department`
- `priority`
- `execution_profile`

Optional:

- `workstream`
- `allowed_write_paths`
- `validation`
- `attempt_limit`

Nothing else is accepted.

Caller/model cannot author actor, canonical intent ID, schema, grounding target,
raw authorities, `authority_level`, raw argv, branch, worktree, Job ID/status,
provider/model/credential/account, arbitrary constraints, service control, or
execution state.

### 4.2 Exact current normalization semantics

Fingerprint compatibility depends on preserving current MCP behavior exactly:

- `operation_key`: validate exact supplied form; **no `.strip()` repair**;
  pattern `^[a-z0-9][a-z0-9-]{2,95}$`, maximum 96 characters.
- `objective`: validate type/control/surrogate bounds, then strip leading/trailing
  whitespace; empty-after-strip refuses.
- `department`: exact supplied form, no strip/case repair; current lowercase
  department pattern remains binding.
- `execution_profile`: exact supplied form; no case-fold or strip repair.
- `workstream`: exact supplied form; no strip/case repair.
- `allowed_write_paths`:
  - strip each item;
  - normalize repeated `/` and `.` segments according to current MCP law;
  - refuse absolute, `~`, `..`, backslash, Git-internal, or unsupported segments;
  - deduplicate and lexicographically sort normalized paths.
- `validation.pytest_targets` / `compileall_paths`:
  - apply the existing relative-path fence;
  - deduplicate and lexicographically sort;
  - remove empty lists from normalized validation.
- `validation.git_diff_check`:
  - must be a real bool;
  - `true` survives;
  - `false` is removed, so otherwise-empty validation normalizes to `{}`.
- omitted and all-empty validation are semantically identical.
- omitted and empty `allowed_write_paths` normalize to the same empty list.
- omitted `attempt_limit` becomes integer `2`.
- high-level attempt limit remains exactly `1..3`; bool is not an int.
- derived authorities are sorted.
- validation argv family ordering remains: pytest, compileall, then
  `git diff --check`.

### 4.3 Existing execution profiles

Exactly:

```text
research_only
  -> [READ, RESEARCH]
  -> allowed_write_paths must be empty
  -> validation must be empty

bounded_code_change
  -> [READ, RUN_TESTS, WRITE_BRANCH]
  -> requires >=1 allowed write path
  -> requires >=1 validation entry
```

No profile grows `OPEN_PR`, `PUSH_BRANCH`, `MERGE`, `DEPLOY`,
`SERVICE_CONTROL`, or `CROSS_REPO_PUBLISH`.

### 4.4 Shared internal errors versus MCP errors

`control_plane` must not import `integrations.executive_mcp.schemas.GatewayError`.
The first-party request module should own a small typed internal request error
(e.g. `CeoRequestError`) that distinguishes caller invalid input from an internal
policy/configuration defect.

The MCP wrapper maps those internal errors back onto its existing frozen public
`GatewayError` categories/messages. Existing accepted normalized outputs and
existing refused MCP error category/message remain compatible.

---

## 5. Trusted v1 derivation

For both MCP and Slack v1, trusted code derives:

- actor: exactly `ceo-sol` (CEO provenance, not transport identity);
- raw schema: existing `mastermind.ceo_intent.v1`;
- authority level: `A0`;
- branch: `codex/<canonical-intent-id>`;
- worktree: `<reviewed jobs workspace root>/<canonical-intent-id>`;
- requested authorities from the profile;
- validation argv from the reviewed validation recipe;
- attempt limit from normalized high-level request.

Use the existing reviewed jobs workspace root currently represented by
`ServiceConfig.proof_workspace_root`. The field retains a Phase-1C name, but
current service code documents that it is the general `jobs/workspaces` root.
Do not introduce a second CEO workspace root in PR-A.

The builder derives worktree under that root and then calls
`ceo_intent.submit_intent(..., workspace_root=the_same_root)` so the existing sink
independently re-fences the same path.

---

## 6. Exact transport-specific intent identities

Cross-transport dedupe is **not** inferred. MCP and Slack use separate namespaces
while preserving the same operation-key-only identity law.

### 6.1 Existing MCP identity — frozen byte-for-byte

```text
prefix: mcp-
domain bytes: b"mastermind.executive_mcp.operation_key.v1\x00"
digest: sha256(domain + operation_key UTF-8)
render: prefix + first 32 lowercase digest hex chars
```

### 6.2 Slack v1 identity — frozen here

```text
prefix: slack-
domain bytes: b"mastermind.executive_slack.operation_key.v1\x00"
digest: sha256(domain + normalized operation_key UTF-8)
render: prefix + first 32 lowercase digest hex chars
```

Payload, grounding, Slack event/message metadata, sender, channel, and timestamps
never enter the canonical intent ID.

Fixed literal vectors:

```text
operation: options-chain-browser-closure-001
MCP:   mcp-400560e76b2e72590f12d30f782bfc4d
Slack: slack-4e40f3d7656227ee9dcead6b00c9d5f2

operation: mas-75-pr-a-research-proof-001
MCP:   mcp-5c6f5256500080fc8f4f4ecceb9ff62a
Slack: slack-e824a09702dce2aeed46fb41d16711e6

operation: ceo-slack-canary-001
MCP:   mcp-1822467f893259d7322d9f0be5ee051c
Slack: slack-9ccec918320bf1518d89144be5a4ad42
```

At least one MCP and one Slack vector must be literal regression expectations,
not values computed by the function under test.

---

## 7. Dedicated ingress protocol

There is no generic `command/version/args` dispatcher on `CeoIngress`.

### 7.1 Submit frame

Exact top-level shape:

```json
{
  "schema": "mastermind.executive_ceo_ingress_submit.v1",
  "observed_grounding": {
    "mastermind_sha": "<40 lowercase hex>",
    "macro_sha": "<40 lowercase hex>",
    "boot_packet_schema": "mastermind.ceo_boot_packet.v1"
  },
  "request": {
    "operation_key": "...",
    "objective": "...",
    "department": "...",
    "priority": 0,
    "execution_profile": "research_only"
  }
}
```

The nested request accepts only the high-level fields in §4.

### 7.2 Status frame

Exact top-level shape:

```json
{
  "schema": "mastermind.executive_ceo_ingress_status.v1",
  "intent_id": "slack-<32 lowercase hex>"
}
```

Status ID validation is exactly:

```text
^slack-[0-9a-f]{32}$
```

It cannot enumerate Jobs/intents, read MCP intent IDs, or reach workers, service
control, backup, generic status, or other Operator data.

### 7.3 Wire bounds and framing

For PR-A hermetic ingress:

- request line maximum: 8,192 UTF-8 bytes including frame/newline budget;
- response line maximum: 32,768 UTF-8 bytes;
- one JSON frame per connection;
- frame must be newline-terminated;
- strict UTF-8, no replacement decoding;
- EOF before newline is an incomplete/refused frame even if the partial bytes
  would parse as valid JSON;
- close connection after one response;
- unknown top-level/nested keys refuse;
- untrusted peer UID refuses **before body read/parsing**.

The 8 KiB local ceiling comfortably contains the later frozen 4,500-byte Slack
source message plus the internal grounding/frame wrapper while staying far below
the broad Operator 64 KiB control request surface.

### 7.4 Response envelope

Reuse only the shape, not the generic dispatcher:

```json
{"ok": true, "result": {...}}
```

or

```json
{"ok": false, "error": {"code": "...", "message": "..."}}
```

The ingress owns a dedicated bounded sender using the 32 KiB ingress ceiling.
Do not blindly reuse generic `_send()`, whose configured response ceiling belongs
to the Operator service surface.

A successful canonical CEO receipt above the ingress bound is a protocol/backend
defect and must refuse; never truncate it.

---

## 8. Peer identity and second-listener composition

The Slack-like local principal is one exact configured/test UID for the dedicated
listener, not the generic `allowed_peer_uids` set.

- Obtain kernel local peer credentials using the service's existing platform
  helper.
- Missing/unreadable credentials -> `peer_credentials_unavailable`.
- Wrong UID -> `peer_denied`.
- Both refusals occur before request-body read/parser, grounding provider, or
  Runtime business access.

PR-A does not choose a production UID/GID or production filesystem permissions.
Those belong to PR-C.

### 8.1 One process / one runtime / one lock

The two sockets are transport separation, not a second control plane.

- one `ExecutiveControlService` instance;
- one Runtime opened by that service;
- one service lock/marker;
- one generic Operator listener;
- one optional dedicated CeoIngress listener;
- ingress receives the already-open exact Runtime object;
- ingress does not call `Runtime.at(...)` itself.

### 8.2 Atomic dual-listener startup

When ingress composition is absent, current service startup behavior must remain
unchanged.

When ingress is configured for PR-A hermetic proof, prefer a dual-listener startup
that constructs/binds both AF_UNIX servers before either is considered publicly
ready. `asyncio.start_unix_server(..., start_serving=False)` for the optional
dual-listener path (or an equivalently proven mechanism) is preferred:

1. acquire the existing one service lock;
2. open/health-check the Runtime once and compose the supervisor as today;
3. construct/bind Operator and CeoIngress listeners without serving;
4. validate the two paths/sockets are distinct and structurally correct;
5. only after both exist, begin serving both;
6. set service started state only after both are serving.

If either listener setup/start fails, close everything opened by the attempt,
unlink only service-owned non-launchd socket nodes, preserve existing dispatch
cleanup, release the one lock/marker, and re-raise. No half-live service.

Do not add production launchd socket names/config in PR-A.

---

## 9. Admission readiness versus worker execution readiness

Do not weaken or rename current generic Operator `service_state` semantics.

Current constructor startup states remain exactly:

```text
READY
AWAITING_CANARY
```

The running service can dynamically enter `QUARANTINED` after ambiguous worker
start or finish/seal failure. PR-A does not add `QUARANTINED` as a constructor
startup value.

CeoIngress has a separate host-owned/injected arming decision, default false.
For PR-A this may be a constructor/test policy only; production receipt-based
arming is PR-C.

Ingress proceeds only when:

```text
ceo_ingress_armed == true
AND current service state in {READY, AWAITING_CANARY}
```

Every other current/future state, including dynamic `QUARANTINED`, refuses.
Ingress arming never changes `_service_state`, clears quarantine, enables worker
execution, loads provider credentials, starts a broker, or sets generic service
state to READY.

Both dedicated submit and dedicated status follow this PR-A allowlist, preserving
the accepted #91 readiness law.

---

## 10. Trusted grounding interface

The dedicated ingress does not discover Git/Agent OS roots.

Inject an opaque first-party grounding provider whose business-facing operation
is conceptually:

```text
observe() -> {
  mastermind_sha,
  macro_sha,
  boot_packet_schema
}
```

Exact class/function name is builder-owned.

Rules:

- output contains only those three strings;
- both SHAs are exact 40 lowercase hex;
- schema is exact `mastermind.ceo_boot_packet.v1`;
- caller/request cannot supply/override the provider;
- no filesystem path, repository root, environment variable, Git argv, Agent OS
  text, strategy, handoff, or degraded prose enters this interface;
- malformed output/provider failure is `grounding_unavailable` with sanitized,
  bounded external text;
- `executive_ceo_ingress` does not import/call `ceo_boot_packet.build_packet`,
  `git_sha`, subprocess Git, Agent OS CLI, environment discovery, or filesystem
  root scanning;
- `ceo_request` receives an already-validated grounding object and does not
  discover/refresh it.

### 10.1 Product-side observed-grounding source

Later PR-B/session instructions mechanically copy only:

```text
executive_state.data.mastermind.sha      -> observed_grounding.mastermind_sha
executive_state.data.macro.sha           -> observed_grounding.macro_sha
executive_state.data.boot_packet_schema  -> observed_grounding.boot_packet_schema
```

Never copy roots, branches, `resolved_via`, runtime labels, degraded warnings,
strategic state, handoffs, or next actions.

Missing/malformed preflight identity means no new request is emitted under a
guessed current value.

---

## 11. Replay, status, grounding, and correction order

This order is load-bearing.

### 11.1 Exact status lookup

After exact Slack-ID validation:

1. derive `command_id = ceo_intent.command_id_for(intent_id)`;
2. use existing first-party
   `runtime.store.find_event_by_command_id(command_id)` for that one exact id;
3. if no event exists -> `not_found`;
4. if event exists -> call public `ceo_intent.resolve_intent(runtime, intent_id)`;
5. if resolution fails despite an event -> bounded `backend_refused`/integrity
   defect, never `not_found`, never silent repair.

This is existing RuntimeStore API use, not raw SQL/enumeration or a new status store.

### 11.2 Submit pre-reconciliation

For a submit frame:

1. validate outer frame and normalize high-level request;
2. derive the deterministic Slack intent ID;
3. construct the candidate v1 envelope/fingerprint using the request's
   `observed_grounding` claim **only for comparison**;
4. exact command-id lookup;
5. if a durable event exists, resolve it canonically **before any current
   grounding-provider call**:
   - corrupt/unresolvable event -> `backend_refused`;
   - durable fingerprint differs -> `operation_conflict`;
   - durable fingerprint matches -> the operation already committed. After that
     existence+fingerprint proof, call existing `ceo_intent.submit_intent` with
     the candidate envelope/workspace root to obtain the normal canonical
     duplicate receipt (`duplicate=true`). Existing command-id state makes this a
     reconciliation, not a new grounding-authorized creation.
6. only when no canonical event exists, call trusted grounding `observe()`;
7. require exact equality with `observed_grounding` -> else
   `grounding_mismatch`, zero Job;
8. derive/revalidate the canonical envelope from trusted grounding;
9. call the **same provider again immediately before first canonical submit**;
10. identity movement -> `grounding_changed`, zero Job;
11. call existing `ceo_intent.submit_intent(...)`.

### 11.3 Concurrent winner

If another caller commits between the initial absent lookup and submit:

- identical winner is reconciled by the existing v1 sink and returns
  `duplicate=true`;
- conflicting winner raises; repeat exact command-id lookup + canonical resolve
  and classify `operation_conflict` from durable fingerprint;
- if no event exists after a sink refusal, classify the actual typed error chain.

No advisory/durable dedupe structure is added.

### 11.4 Workspace/config continuity

Because the v1 fingerprint includes trusted-derived branch/worktree, replay
comparison assumes the reviewed jobs workspace/config binding is stable within a
bridge epoch. PR-C's production readiness receipt will bind the installed config
and invalidates on change. Do not add another durable business fingerprint/store
in PR-A to solve hypothetical host migrations.

---

## 12. Typed refusal/error law

Expected CeoIngress **server** error codes are the closed set:

```text
peer_credentials_unavailable
peer_denied
ingress_unavailable
unsupported_ingress_schema
request_too_large
response_too_large
invalid_json
invalid_input
invalid_intent_id
not_found
grounding_unavailable
grounding_mismatch
grounding_changed
operation_conflict
authority_refused
backend_unavailable
backend_refused
internal_error
```

The server does not export generic Operator `request_failed`, raw exception reprs,
tracebacks, local paths, environment values, tokens, Git stderr, or arbitrary
future codes.

Expected validation text may name the invalid field/value class. Unexpected
external/backend exceptions are sanitized/bounded; an unknown internal exception
may expose only a class label plus generic ingress failure text.

### 12.1 Authority classification

Do not make English-message matching canonical.

Current source preserves the useful cause chain:

```text
CeoIntentError
  caused by StateConflict
    caused by AuthorityDenied | AuthorityPolicyError
```

When no durable sibling event exists, traverse the typed cause chain to classify
`authority_refused`.

A non-authority StateConflict/refusal without accepted event is a bounded backend
refusal according to its actual type; never guess `operation_conflict` from text.

---

## 13. Modifying timeout and effect-unknown law

This is a critical correction to generic timeout vocabulary.

### 13.1 No cancellable server-side mutation timeout

Do **not** wrap a started canonical admission in:

```text
asyncio.wait_for(asyncio.to_thread(ceo_intent.submit_intent, ...))
asyncio.timeout(... around to_thread mutation ...)
```

or any equivalent that claims timeout cancelled the sync SQLite mutation.

Cancelling the awaiting coroutine does not safely cancel the underlying thread or
transaction. Returning server `timeout` could therefore be followed by a real
late commit, which would be a false cancellation claim.

The current raw Executive service is the correct precedent: it awaits
`asyncio.to_thread(ceo_intent.submit_intent, ...)` to terminal commit/refusal with
no internal mutation timeout.

Once canonical submit starts, PR-A server lets it reach a real terminal outcome.
Client disconnect or reply failure never rolls back canonical state.

### 13.2 Client/transport timeout

A later PR-B client may impose a response wait budget. That timeout means
**effect/response unknown**, not “submission cancelled.”

Required recovery:

1. stop modifying retries for the operation;
2. call dedicated status for its deterministic `slack-*` intent ID;
3. accepted receipt -> reconcile it;
4. true `not_found` -> a same-operation/same-payload resubmit may proceed only
   under normal current-grounding law;
5. status unavailable/ambiguous -> do not blindly resubmit.

`timeout` is therefore a later client/transport classification, not a PR-A server
claim that a started canonical mutation was cancelled.

---

## 14. Ingress shutdown-drain law

A second consequence follows from non-cancellable sync mutation.

Current `ExecutiveControlService.close()` waits its explicitly tracked worker
**dispatch** tasks, but `Server.close()/wait_closed()` alone does not prove every
already-created request-handler coroutine or `to_thread` mutation is terminal.

PR-A may not release the one Executive service lock while a started CeoIngress
admission is still live.

### 14.1 In-memory handler tracking

Track dedicated ingress handler tasks **in memory only** as process lifecycle,
not durable work authority.

- register the current CeoIngress handler task on entry;
- remove it in `finally` only after its admission/readback and response cleanup
  reaches the real terminal point;
- client disconnect does not remove it while canonical mutation runs.

### 14.2 Close ordering

`close()` in dual-listener mode:

1. stops both listeners first, preventing new connections;
2. preserves existing dispatch shutdown semantics;
3. waits every already-started CeoIngress handler to finish;
4. a handler whose sync `submit_intent` thread has started is **not cancelled at
   shutdown grace expiry**; cancellation does not cancel the thread, so fail
   closed by keeping shutdown/lock held until commit/refusal;
5. only after ingress handlers are terminal does socket cleanup and single
   service-lock/marker release complete.

A pre-mutation handler may be cancelled only when code structurally proves no
canonical mutation thread started. A simple “cancel all ingress handlers” rule is
not accepted.

No durable request registry/lease/table is created for this drain set.

PR-A need not redesign pre-existing generic Operator connection lifecycle unless
implementation proves that shared behavior makes the new ingress invariant
impossible. If so, STOP and return that concrete blocker.

---

## 15. MCP compatibility hard pins

Current MCP schema snapshot must remain exactly:

```text
546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232
```

Compatibility requires:

- same `TOOL_SPECS`/server version/schema snapshot bytes;
- same accepted submit input -> same normalized request and same v1 envelope;
- same MCP operation key -> same existing `mcp-*` ID;
- same refused input -> same public MCP error category/message;
- same derivation order/defaults/path normalization;
- no new public inner request schema;
- no production write mode added to EXEC-MCP-A.

### 15.1 Cross-transport golden fixture

Pure derivation fixture:

```text
operation_key: options-chain-browser-closure-001
objective: Implement the assigned bounded deliverable and return evidence.
department: executive-infrastructure
priority: 10
execution_profile: research_only
attempt_limit: omitted -> 2
mastermind_sha: 1111111111111111111111111111111111111111
macro_sha: 2222222222222222222222222222222222222222
boot_packet_schema: mastermind.ceo_boot_packet.v1
workspace_root: /tmp/mas75-workspaces
```

Expected MCP v1:

```text
intent_id: mcp-400560e76b2e72590f12d30f782bfc4d
canonical envelope length: 654 UTF-8 bytes
fingerprint: 2afba2ba02b4d2d7f3875cd2c13612f7d27fa44b7d9cd268f9f867542df6ccbe
```

Expected Slack v1:

```text
intent_id: slack-4e40f3d7656227ee9dcead6b00c9d5f2
canonical envelope length: 660 UTF-8 bytes
fingerprint: d35b07a3c259046ada8d849fc57575a2f2d7b44de5ede8d8db5e9f1a570666b8
```

The envelopes intentionally differ where transport identity propagates:
intent ID, derived branch, and derived worktree. Actor/objective/department/
priority/grounding/authority level/attempt limit/requested authorities are
otherwise identical.

Expected values are literal fixtures, never values generated by the new builder
under test.

---

## 16. CI and packaging law

Current Mastermind CI is discovery-first:

- `.github/workflows/ci.yml` runs `python scripts/ci_pytest.py`;
- every `tests/**/test_*.py` is discovered unless exactly excluded;
- `tests/test_executive_*` is a protected prefix that cannot be excluded;
- the CI harness rejects reintroducing a positive test-file allowlist.

Therefore PR-A does **not** edit `.github/workflows/ci.yml` merely to wire new
Executive tests and does not add a test exclusion/waiver.

`control_plane` is already packaged by current project configuration; new
first-party modules do not require a `pyproject.toml` package/dependency edit.

The accepted current source-law baseline's hosted repository test gate recorded:

```text
discovered=272 excluded=0 running=272
```

with source compile and shell validation green.

At builder pickup, record the then-current base SHA and its discovery plan.
Final PR head must discover/run every new PR-A test module with zero new
exclusions. Raw count differences caused by unrelated base movement must be
explained against the exact base rather than waved away.

---

## 17. Required adversarial proof matrix

A technically green PR is not accepted unless these families are proven.

### 17.1 Peer/protocol

- wrong UID -> `peer_denied` before parser/provider/Runtime business access;
- unavailable peer credentials -> fail before body read;
- ingress path same as Operator path -> constructor/composition refusal;
- wrong/non-AF_UNIX/non-listening/wrong-bound activated test socket -> refusal;
- malformed UTF-8/JSON -> zero Job;
- oversize request -> zero Job;
- missing newline / EOF partial frame -> zero Job;
- unknown schema / extra outer or nested keys -> zero Job;
- second frame on one connection is never processed;
- generic `_dispatch_request` monkeypatched to explode -> valid ingress still works.

### 17.2 Privilege/schema

Attempted caller fields `actor`, `requested_authorities`, raw argv, branch,
worktree, provider/model/credential/account, arbitrary constraints,
`intent_kind`, `business_impact`, orchestration role, or service-control refuse.

Status rejects MCP IDs, Job IDs, uppercase/short/long/random IDs before lookup.
Valid absent Slack ID returns true `not_found`.

### 17.3 Grounding/replay

- malformed observed grounding -> refuse before provider;
- trusted provider unavailable/malformed -> zero Job;
- observed != trusted -> `grounding_mismatch`, zero Job;
- trusted moves snapshot->precommit -> `grounding_changed`, zero Job;
- committed same fingerprint + later organizational grounding movement ->
  canonical duplicate/readback, no new Job, no current-grounding requirement;
- committed changed fingerprint -> `operation_conflict`;
- corrupted durable event is backend/integrity refusal, not `not_found`;
- concurrent identical winner -> exactly one Job, duplicate receipt;
- concurrent conflicting winner -> exactly one Job + `operation_conflict`.

### 17.4 Readiness/lifecycle

- ingress absent/unarmed -> current service behavior unchanged;
- armed + `AWAITING_CANARY` -> ingress works, generic Operator mutation still
  refuses exactly as current service law;
- armed + `READY` -> ingress works but surface does not widen;
- dynamic `QUARANTINED` -> ingress refuses;
- unknown/future service state -> ingress refuses;
- valid submit -> zero Attempt rows, zero workers, zero supervisor/broker/provider
  calls;
- listener startup partial failure -> all new listeners/resources roll back,
  lock/marker restartability proven;
- close twice is safe;
- normal ingress handler leaves no task-set residue.

### 17.5 Timeout/disconnect/drain

- pause canonical submit after sync thread invocation;
- disconnect/cancel client wait;
- release mutation -> it may still commit exactly once;
- status recovers canonical receipt;
- no second Job and no server claim that started mutation was cancelled;
- trigger service close while submit is paused -> listeners stop accepting, but
  close does not release service lock/marker until admission terminal;
- after terminal drain -> cleanup/lock release and fresh service restart succeeds.

### 17.6 Error containment

- downstream authority denial -> typed `authority_refused`, zero Job;
- fake secret/path in provider/backend exception -> not present in response;
- unexpected exception -> opaque bounded internal failure;
- successful receipt must report `dispatched=false`; a result claiming true is a
  backend contract defect, never presented as success.

### 17.7 Static/no-rebuild

- no new SQLite table/database/index/store for ingress;
- no Wake import/call;
- no Slack/MCP SDK import under `control_plane`;
- no production install/config/launchd/secret changes;
- `ceo_intent.py` / `executive_runtime.py` unchanged absent separate Sol ruling;
- MCP schema snapshot/vector/fingerprint hard pins unchanged;
- final full CI green on exact reviewed head with discovery plan.

---

## 18. Production proof and completion boundary

**No production proof is owed in PR-A.**

PR-A is complete only when the hermetic vertical is implemented, adversarially
reviewed by Sol against this file + PR #91, and merged without widening authority.

PR-A does not prove:

- Slack Socket Mode transport;
- Slack app scopes/tokens;
- dedicated `_mastermind_slack` production principal;
- production filesystem/socket permissions;
- host grounding-source binding;
- production CEO-ingress readiness receipt;
- Codex worker readiness;
- Phase 1C-A acceptance;
- Wake acceptance;
- generic `#agent-dispatch` runtime delivery;
- browser-agent wake/resume.

Those claims remain false/pending until separately proven.

---

## 19. Stop condition and continuation handoff

Stop PR-A after exactly one independently useful hermetic capability exists:

```text
bounded high-level CEO request
  -> dedicated local CeoIngress
  -> trusted v1 derivation + grounding/replay law
  -> existing ceo_intent sink
  -> one QUEUED Job/JOB_CREATED
  -> dedicated Slack-ID status readback
  -> zero worker execution
```

Do not absorb PR-B or PR-C because PR-A is green.

Return to Sol with:

- exact base/head SHA;
- changed files;
- focused + full CI and discovery-plan receipt;
- authorization/failure matrix;
- one-Job/zero-Attempt proof;
- duplicate/conflict/concurrent-race receipts;
- grounding mismatch/movement/replay proof;
- timeout/disconnect/shutdown-drain proof;
- MCP schema/vector/golden-fingerprint compatibility receipt;
- no-new-store/no-Wake/no-production-surface proof;
- readiness-state matrix;
- any architecture collision discovered.

Only after Sol accepts that PR may PR-B be commissioned.
