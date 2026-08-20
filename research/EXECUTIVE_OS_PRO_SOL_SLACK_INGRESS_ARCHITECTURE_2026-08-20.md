# Executive OS — Pro Sol → Slack → Executive OS ingress architecture freeze

**Status:** ARCHITECTURE_FREEZE / RECORDS_ONLY  
**Date:** 2026-08-20  
**Implementation issue:** Linear `MAS-48`  
**Parent program:** Linear `MAS-9`  
**Pinned Mastermind baseline:** `18eb956a7dac0edca6870a39887a964b66c53d72`  
**Authority:** Sol CEO architecture; Chairman remains final authority.  
**Runtime implementation:** NOT IN THIS DOCUMENT / NOT IN THIS PR.

## 0. Executive ruling

The Chairman's immediate problem is not “build a generic Slack agent bus.” It is narrower and more valuable:

> A ChatGPT Personal Pro Sol session must be able to finish high-effort research, submit one bounded CEO request through an approved Slack write action, receive a deterministic acknowledgement, and read the exact resulting canonical Executive OS intent/job back through the existing read-only MCP — without requiring ChatGPT Business custom-MCP write access and without depending on the currently blocked Codex worker credential.

The long-term multi-seat Slack transport remains valid. It follows this proof; it does not precede it.

This architecture therefore freezes Slack as an **egress transport**, not a state authority. Mastermind Executive SQLite remains the sole Job/Attempt/Worker/Event lifecycle authority. Agent OS remains the organizational knowledge plane. Linear remains a selective portfolio projection. GitHub remains exact implementation/evidence truth.

No Slack queue, Slack database, durable seat-inbox database, task store, second scheduler, or second lifecycle state machine may be introduced by MAS-48.

## 1. Why this pivot exists

Current OpenAI product behavior makes the split explicit: Pro users can connect custom MCP with read/fetch permissions, while full custom MCP including write/modify actions is currently limited to Business and Enterprise/Edu. At the same time, ChatGPT apps can expose approved write actions. The architecture should use the strongest Pro cognition surface and an approved application transport rather than force the cognition seat to also be the privileged Executive mutation client.

Primary reference:
- OpenAI Help, “Developer mode and MCP apps in ChatGPT”: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt

The current Pro seat has already demonstrated installed Slack/GitHub/Linear access, and the Slack workspace contains `#ceo-control-room` and `#agent-dispatch`. MAS-48 uses only `#ceo-control-room`; generic seat routing is later.

## 2. Outcome and 10/10 end state

### User job

Sol does not stop being CEO because the chosen ChatGPT plan cannot call a custom write tool. Sol researches and adjudicates on Pro, then emits a small typed command to a familiar collaboration surface. No copy/paste into a terminal. No Chairman-mediated `auth.json` edits. No workspace-ID forcing. No end-of-session surprise where the result exists only in chat.

### Machine job

A separately authenticated Slack application receives the message, validates only transport facts, and submits a **high-level CEO request** to the existing Executive control service. The control service derives all privileged fields and sends the resulting canonical envelope through the already-built `control_plane.ceo_intent.submit_intent(...)` seam. Existing Executive SQLite commits exactly one Job plus its `JOB_CREATED` event.

### 10/10 proof

One real Pro Sol session produces all of the following for the same operation:

1. an original Slack message in `#ceo-control-room`;
2. a Slack bot ACK in the originating thread;
3. one canonical CEO intent id;
4. one canonical Executive Job id;
5. one existing `JOB_CREATED` durable event carrying CEO-intent provenance plus bounded Slack transport provenance;
6. zero duplicate Jobs after replay of the same Slack delivery;
7. a refusal, not another Job, when the same operation key is reused with changed payload;
8. successful readback through current read-only MCP `ceo_intent_status` and `executive_job`;
9. proof that the Slack local principal cannot invoke raw `submit-ceo-intent`, dispatch, shutdown, backup, service-control, or any other control command;
10. no Wake invocation, no new lifecycle store, and no dependence on Codex worker authentication.

## 3. Capability ledger at freeze

| Capability | State | Evidence / ruling |
|---|---|---|
| Personal Pro Sol research | `PROVEN_LIVE` | Chairman's active operating experience; plan choice driving this program. |
| Pro custom MCP read/fetch | `PROVEN_LIVE` | Current operating model and OpenAI plan documentation. |
| Pro custom MCP full write/modify | `REJECTED_BY_DESIGN` for this architecture | OpenAI currently limits full custom MCP to Business/Enterprise/Edu. |
| Installed ChatGPT Slack app access | `PROVEN_LIVE` | Workspace/channel/user discovery succeeded from the Pro seat. |
| Slack message write primitive from ChatGPT app | `BUILT_NOT_PROVEN` for MAS-48 | Tool exists and permission is configured; no MAS-48 production canary yet. |
| Executive SQLite Job/Event authority | `PROVEN_LIVE` | Existing Runtime and prior production acceptance receipts. |
| `mastermind.ceo_intent.v1` → one QUEUED Job | `BUILT_NOT_PROVEN` for Slack ingress | Merged first-party seam exists; Slack has not yet driven it in production. |
| MCP readback (`ceo_intent_status`, `executive_job`) | `BUILT_NOT_PROVEN` for Slack-created intent | Read tools exist; cross-transport proof not run. |
| Dedicated Slack backend app / Socket Mode daemon | `NOT_BUILT` | MAS-48 implementation scope. |
| Command-scoped Slack local principal | `NOT_BUILT` | Current control service authenticates peer UID but its command allowance is peer-wide. |
| Generic Slack seat dispatch bus | `SPEC_ONLY` / `BLOCKED` | MAS-29/30/31 wait for MAS-48 proof and fresh architecture review. |
| Wake Fabric as a foundation | `BROKEN` / `HOLD` | `DEC:EXECUTIVE-WAKE-B5E45BE-COO-ADJUDICATION`: NOT_ACCEPTED / NOT_ARMED. |
| Codex inference worker credential | `BROKEN` / `AUTH_MISSING` | Formal run failed `403 invalid_workspace_selected`; separate executor-auth program. |

## 4. Existing authority that MUST be reused

### 4.1 Executive runtime

`control_plane/executive_runtime.py` owns the durable Job/Attempt/Worker/Event lifecycle. Existing `events.command_id` uniqueness is the idempotency authority. MAS-48 does not add another dedupe table.

### 4.2 Canonical CEO intent

`control_plane/ceo_intent.py` is already explicitly an adapter, not a control plane. It validates one `mastermind.ceo_intent.v1`, lets existing authority policy adjudicate requested capabilities, calls the existing Job registry, and produces one QUEUED Job plus `JOB_CREATED` event. Submission is not dispatch.

The existing module also freezes two laws MAS-48 inherits unchanged:

- `actor` is provenance, never privilege;
- `workstream` is an Agent OS provenance pointer, never a write into Agent OS.

### 4.3 Existing model-safe request surface

`integrations/executive_mcp/schemas.py` already defines the correct high-level request vocabulary for a model-facing submitter:

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

The model cannot author actor, raw authorities, raw validation argv, grounding SHAs, worktree, branch, job id, status, dispatch state, constraints, authority level, schema, or canonical intent id. Those fields are derived by trusted code.

The Slack path MUST preserve these semantics. It may not create a richer, more permissive message schema.

### 4.4 Executive control service

`control_plane/executive_service.py` remains the only production process allowed to open and mutate the live runtime. The Slack daemon MUST NOT open Executive SQLite directly.

The current service authenticates AF_UNIX peers by UID, but a permitted peer can reach the command surface generally. That is insufficient for a network-facing Slack process.

## 5. Frozen V1 topology

```text
ChatGPT Personal Pro — Sol CEO
        |
        | approved Slack app write action
        v
Slack workspace T0BRD2AQXQV
#ceo-control-room C0BRDFZPLHK
        |
        | message.channels over Socket Mode
        v
_mastermind_slack daemon
(integrations/slack_executive)
        |
        | AF_UNIX, high-level request only
        | command = submit-ceo-request
        v
ExecutiveControlService (_mastermind_exec)
        |
        | trusted derivation / grounding / authority profile
        v
control_plane.ceo_intent.submit_intent
        |
        v
Executive SQLite
Job + JOB_CREATED + existing command-id uniqueness
        |
        +----------------------+
        |                      |
        v                      v
Slack thread ACK        read-only Executive MCP
                         ceo_intent_status/job
```

## 6. Why the AF_UNIX command is `submit-ceo-request`, not raw `submit-ceo-intent`

The raw canonical CEO-intent envelope contains fields a network-facing process must never be able to choose directly: requested authorities, validation argv, grounding, worktree, branch, actor and canonical intent id.

Therefore MAS-48 adds one narrow internal control command, provisionally named `submit-ceo-request`.

Its input is the existing high-level model-safe request plus bounded transport provenance. The control process itself derives the raw canonical intent and then invokes the existing `ceo_intent.submit_intent(...)`. This is an admission adapter into the existing mutation seam, not a second write path.

The Slack UID MUST be authorized only for this new command. It MUST be denied raw `submit-ceo-intent` and every other control-service command.

The existing MCP gateway continues using its currently reviewed public contract. Refactoring shared derivation must preserve its schema snapshot and byte-for-byte behavior for existing inputs.

## 7. Shared first-party request derivation

Do not copy MCP policy logic into a Slack package.

Create one transport-neutral first-party admission module under `control_plane/` (recommended name `control_plane/ceo_request.py`) that owns reusable normalized-request validation and privileged derivation semantics. The implementation may move/refactor existing functions from `integrations/executive_mcp/schemas.py` only if all frozen MCP behavior remains unchanged.

Required compatibility proof:

- current MCP `TOOL_SPECS` / schema snapshot unchanged unless a separately reviewed MCP contract migration is intentionally opened;
- same accepted MCP input yields the same existing MCP-derived canonical envelope/receipt as before refactor;
- same refused MCP input remains refused with the same public error category;
- `control_plane/` remains free of Slack SDK and MCP SDK imports.

Transport identity must be explicit. Existing MCP intent IDs use the MCP-specific domain/prefix and MUST NOT silently change. Slack requests use their own stable namespace (for example `slack-<digest>`) while preserving the same core law: the digest is from `operation_key` alone, never the whole payload. Cross-transport dedupe is NOT inferred automatically.

## 8. Slack wire contract

The first line is a hard discriminator:

```text
EXECOS/CEO_REQUEST_V1
```

The remainder is exactly one JSON object whose business fields mirror the existing MCP `submit_ceo_intent` input:

```json
{
  "operation_key": "stable-operation-key",
  "objective": "bounded outcome",
  "department": "executive-infrastructure",
  "priority": 0,
  "execution_profile": "research_only",
  "workstream": "WS:OPTIONAL-POINTER",
  "allowed_write_paths": [],
  "validation": {
    "pytest_targets": [],
    "compileall_paths": [],
    "git_diff_check": false
  },
  "attempt_limit": 2
}
```

Optional fields may be omitted; they MUST NOT be repaired from prose. Existing profile rules still apply. In particular `research_only` cannot smuggle write paths/validation, and `bounded_code_change` must satisfy the existing reviewed requirements.

### Wire bounds

- whole Slack message: maximum 4,500 UTF-8 bytes in V1;
- one discriminator line + one JSON object only;
- no Markdown interpretation;
- no YAML;
- no trailing instruction prose;
- unknown keys fail closed;
- control/surrogate characters fail closed;
- the inner business request must satisfy the existing CEO-request bounds, which remain no wider than upstream `ceo_intent`.

The tighter Slack byte ceiling is intentional: it stays below ChatGPT's current Slack text-element limit and forces long research to remain in its proper artifact/knowledge home rather than turning Slack into a document store.

## 9. Transport provenance

Transport evidence is required to prove the round trip but cannot affect executive authority and cannot create another store.

The existing `JOB_CREATED` CEO-intent provenance MAY be extended with one optional, bounded server-owned `transport` object. It is outside the model-authored intent fingerprint.

For Slack V1 it contains only:

```json
{
  "schema": "mastermind.slack_transport.v1",
  "team_id": "T...",
  "channel_id": "C...",
  "message_ts": "...",
  "thread_ts": "...",
  "sender_id": "U...",
  "slack_event_id": "Ev..."
}
```

Rules:

- exact key set and tight length/pattern bounds;
- values are provenance/evidence, never authority;
- no token, workspace secret, email address, display name, message body copy, or OAuth material;
- canonical intent fingerprint remains a fingerprint of the canonical intent, not Slack delivery metadata;
- a retry may carry a different Slack `event_id` only if it is provably a Slack redelivery of the same source message; the canonical operation/fingerprint law remains decisive;
- do not create a second durable `SLACK_RECEIVED` table merely to save these fields.

If adding optional transport provenance to the existing `JOB_CREATED` payload cannot be done compatibly with historical readback, STOP and return for architecture review. Do not fall back to a new database.

## 10. Slack app and network boundary

V1 uses **Socket Mode** so the Executive Mac makes an outbound WebSocket connection and exposes no public Slack webhook endpoint.

Slack primary references:
- Socket Mode/app token: https://docs.slack.dev/reference/scopes/connections.write/
- `message.channels`: https://docs.slack.dev/reference/events/message.channels
- `channels:history`: https://docs.slack.dev/reference/scopes/channels.history/
- `chat:write`: https://docs.slack.dev/reference/scopes/

Minimum intended Slack authorization for V1:

- app-level token: `connections:write`;
- bot OAuth: `channels:history` and `chat:write`;
- event subscription: `message.channels`;
- bot is invited only to `#ceo-control-room`;
- do NOT request `chat:write.public`;
- do NOT subscribe to private-channel/DM events in V1;
- if `#ceo-control-room` becomes private, V1 fails closed until a new scope/event review is completed.

Production config pins the workspace and channel IDs rather than trusting names:

- team: `T0BRD2AQXQV`;
- channel: `C0BRDFZPLHK`.

Allowed Sol transport identities are host configuration, not source constants. The current known ChatGPT Slack users are:

- ChatGPT1 `U0BRETDUAS2`;
- ChatGPT2 `U0BSB73JWNL`;
- ChatGPT3 `U0BR1GQH7SB`.

A sender allowlist proves who may use the transport. It does not grant Executive capability; the canonical request derivation plus `ExecutiveAuthorityPolicy` remain authoritative.

The Slack daemon must ignore its own bot messages and unsupported message subtypes so its ACK cannot recurse into a new request.

## 11. Process and credential boundary

The existing Executive installer pattern is binding: root is bootstrap only; runtime daemons use dedicated non-login identities.

MAS-48 introduces a dedicated non-login Slack transport account, recommended `_mastermind_slack`, with its own fixed UID/GID selected and collision-checked by the installer. Do not reuse root, `_mastermind_exec`, `_mastermind_worker`, the Chairman's interactive account, or a ChatGPT operator account.

The Slack process:

- cannot open the Executive SQLite path;
- cannot read worker/Codex credential homes;
- cannot write Agent OS, Linear, GitHub, or production application state;
- can connect outbound to Slack;
- can connect to the Executive AF_UNIX socket only through filesystem/peer policy needed for `submit-ceo-request`;
- receives no generic shell/exec command from Slack content;
- uses a pinned, reviewed Slack SDK/runtime dependency isolated from the stdlib-only Executive control process.

Slack `xapp-` and `xoxb-` credentials are host secrets. They MUST NOT be committed, included in launch plist source, emitted in logs/receipts, passed through CEO-request fields, or copied from the ChatGPT connector. Exact secret-file path/ownership and token-rotation procedure are a required security micro-freeze before production install; implementation must preserve dedicated-principal-only read access.

## 12. Command-scoped AF_UNIX authorization

Current `allowed_peer_uids` is insufficient because it answers “may this UID connect?” but not “which command may this UID invoke?”

MAS-48 must extend service authorization so policy is structurally command-scoped. Required semantics:

- existing trusted control identity retains its reviewed existing command set;
- Slack identity can invoke **only** `submit-ceo-request`;
- permission is checked before command body parsing/dispatch reaches any privileged handler;
- no request field may widen the peer's command allowance;
- authorization denial has a typed error distinct from malformed business input;
- unit tests enumerate every registered command and prove the Slack UID is denied all but the single allowed command;
- future commands default denied for the Slack UID.

Do not solve this by adding `_mastermind_slack` to a broad UID list and relying on the bridge code to “behave.”

## 13. Idempotency and correction law

The user-visible retry identity is `operation_key`.

- same Slack namespace + same `operation_key` + same normalized business payload → same canonical intent/Job, `duplicate=true`;
- same Slack namespace + same `operation_key` + changed normalized business payload → conflict/refusal, zero additional Job;
- Slack retry/event redelivery does not generate a new operation key;
- message edit does not mutate an accepted intent;
- a genuinely changed request requires a new operation key;
- ACK failure after Executive commit is a delivery failure, not a state rollback. Retry first reconciles/readbacks the already-committed intent, then retries ACK;
- cross-transport “same operation key” does not automatically mean same operation because MCP's existing identifier namespace is frozen. A future migration may explicitly unify namespaces; MAS-48 does not.

No blind retry of a modifying AF_UNIX call after an ambiguous timeout. Reconcile by canonical intent id/status first, matching the existing MCP law.

## 14. ACK contract

ACK is a transport receipt, not execution or completion.

First line:

```text
ACK | schema=EXECOS/CEO_REQUEST_V1 | operation=<key> | intent=<id> | job=<id> | accepted=<true|false> | duplicate=<true|false> | dispatched=false
```

A bounded second line may contain a typed refusal/error code. Do not echo the objective, secrets, raw exception text, or arbitrary upstream response bodies.

`accepted=true` means only that the existing CEO-intent seam committed/reconciled the canonical Job. It does not mean a worker ran. It does not close Linear, Agent OS, a PR, or a production capability.

## 15. Failure-state architecture

Every failure is explicit and fail-closed. Minimum vocabulary:

### Slack admission
- `unsupported_workspace`
- `unsupported_channel`
- `untrusted_sender`
- `unsupported_message_subtype`
- `malformed_envelope`
- `payload_too_large`
- `operation_conflict`

### Executive derivation/admission
- `grounding_unavailable`
- `grounding_changed`
- `invalid_input`
- `authority_refused`

### Local boundary
- `local_peer_denied`
- `command_not_allowed_for_peer`
- `backend_unavailable`
- `backend_refused`
- `timeout`

### Post-commit transport
- `ack_failed_after_commit`

No failure path invents success. No Slack timeout is interpreted as “probably queued.” No ACK success is interpreted as “running.”

## 16. Wake is explicitly excluded

Current durable COO ruling is `WAKE_CODE_HOLD / NOT_ACCEPTED / NOT_ARMED` after a proven admission bypass. MAS-48 MUST NOT import, call, persist through, arm, or claim production proof for Wake.

The fact that Wake also uses existing Executive events demonstrates a useful no-new-store pattern; it does not make Wake an accepted dependency.

`WS:<KEY>` remains an Agent OS provenance pointer. Do not translate it into Wake/session-target lower-snake identifiers.

## 17. Codex `AUTH_MISSING` is a separate execution concern

The spent Phase 1C-A formal attempt reached a real Codex turn and failed `403 invalid_workspace_selected`. That remains a worker/provider authentication problem. MAS-48 neither repairs nor bypasses it.

The Pro-Sol writeback proof succeeds when a CEO request is durably QUEUED and readable. It does not require Codex execution. This decouples CEO cognition/communication from executor entitlement.

No Personal credential copying, `auth.json` editing, forced workspace ID, operator credential reuse, or implicit reauthorization is permitted by this architecture.

## 18. Session-start preflight

Every Sol session expected to produce a durable handoff should front-load integrations before substantive research:

1. read Executive MCP state;
2. resolve Slack `#ceo-control-room`;
3. when relevant, verify Linear and GitHub connectivity with read-only calls;
4. surface any OAuth/reconnection requirement before substantive work;
5. do not mutate during preflight.

This cannot force provider OAuth dialogs to appear simultaneously; it does ensure all expected integrations are touched at the beginning rather than first discovered at the end.

For installed apps, app-specific ChatGPT permissions may remove ordinary per-action confirmation prompts, but exceptional provider/OAuth/risk checks remain platform-controlled and are not an Executive OS guarantee.

## 19. PR decomposition

MAS-48 is a program slice, not permission to ship one giant PR.

### PR-A — shared request law + command-scoped local admission

Observable capability: a fixture/local Slack-like peer can submit one high-level CEO request through AF_UNIX, and that peer is structurally unable to invoke every other command.

Includes:
- transport-neutral CEO-request normalization/derivation;
- Slack-specific intent namespace without changing MCP IDs;
- command-scoped peer authorization;
- optional bounded transport provenance in canonical `JOB_CREATED` provenance;
- tests proving MCP public schema/semantics are unchanged;
- no Slack SDK/network code.

Stop after hermetic E2E: high-level request → one Job → readback.

### PR-B — Slack Socket Mode adapter

Observable capability: fixture + non-production Slack app event reaches the PR-A local interface and produces the deterministic ACK payload.

Includes:
- `integrations/slack_executive/` adapter;
- pinned SDK dependency;
- exact team/channel/user allowlists from host config;
- message parser and ACK sender;
- reconnect/backoff and self-message/subtype filters;
- no installer/production credentials.

Stop after fixture and isolated Slack development-workspace proof.

### PR-C — production principal/install + one canary

Observable capability: the real Pro Sol seat posts one harmless `research_only` request in production `#ceo-control-room`; one canonical Job is created/reconciled; the bot ACKs; read-only MCP returns matching intent/job.

Includes:
- dedicated non-login principal;
- exact dependency/runtime pinning and provenance;
- secret-file ownership/rotation law;
- launchd/service configuration;
- rollback/uninstall path;
- one canary and production receipt.

No generic `#agent-dispatch`, no Wake, no worker execution.

## 20. Acceptance tests

At minimum:

1. exact valid `EXECOS/CEO_REQUEST_V1` `research_only` message succeeds;
2. unknown top-level/business key refuses;
3. message >4,500 UTF-8 bytes refuses;
4. wrong team refuses;
5. wrong channel refuses;
6. non-allowlisted sender refuses;
7. bot/self message does not recurse;
8. unsupported subtype/edit cannot mutate accepted state;
9. same operation/payload twice produces one Job;
10. same operation/changed payload refuses with one Job remaining;
11. ambiguous AF_UNIX response reconciles before any retry;
12. Slack UID can invoke `submit-ceo-request` only;
13. Slack UID is denied raw `submit-ceo-intent`;
14. Slack UID is denied every existing/future command by default;
15. raw authority/worktree/branch/argv/credential fields are impossible in Slack request;
16. MCP schema snapshot and existing derived IDs are unchanged;
17. transport provenance is bounded and does not enter canonical intent fingerprint;
18. no new SQLite table/database exists;
19. no Wake module is imported/called by the V1 path;
20. ACK says `dispatched=false`;
21. MCP readback agrees on intent id, fingerprint, Job id, status and grounding.

## 21. Production proof packet

The production canary packet must contain only non-secret evidence:

- exact Mastermind release SHA;
- exact integration release SHA;
- Slack workspace/channel/message/thread IDs;
- allowlisted sender ID;
- operation key;
- canonical intent id + fingerprint;
- canonical Job id + status;
- duplicate/dispatched flags;
- bounded authority receipt;
- MCP readback receipt;
- proof no second Job appeared after replay;
- proof Slack principal command-denial matrix passed on the installed release;
- Slack bot ACK message ID;
- explicit `WAKE_USED=false` and `CODEX_EXECUTION_REQUIRED=false`.

Do not store Slack tokens, OAuth responses, worker credentials, or full private conversation bodies in the packet.

## 22. No-rebuild / no-widen boundaries

The following require a new Sol/Fable architecture ruling before implementation:

- any new Executive lifecycle DB/table/queue/inbox;
- any Slack-to-Agent-OS direct write;
- any Slack-to-Linear completion authority;
- any Slack-to-GitHub automatic mutation in MAS-48;
- any direct Slack-triggered dispatch/execution;
- any use of Wake while its current HOLD stands;
- any change to MCP's existing public schema/intent-id semantics merely to support Slack;
- any grant of raw `submit-ceo-intent` to the Slack principal;
- any network listener exposed publicly for V1;
- any reuse of ChatGPT plugin OAuth tokens by the backend;
- any worker/provider credential in Slack transport state.

## 23. Exact next action

Commission **PR-A only** to a principal builder after PR #6071 is amended/re-reviewed or explicitly superseded on the conflicting implementation details.

PR-A's mission is not “build Slack.” Its mission is:

> Add a transport-neutral high-level CEO-request admission seam and command-scoped AF_UNIX peer authorization such that a hermetic Slack-like peer can create/reconcile exactly one existing Executive CEO-intent Job without being able to select raw authority fields or invoke any other control command, while preserving the existing MCP contract unchanged.

When PR-A returns, Sol performs adversarial review before PR-B is commissioned.
