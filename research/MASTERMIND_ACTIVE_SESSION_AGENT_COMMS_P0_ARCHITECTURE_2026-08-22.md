# Mastermind Active-Session Agent Communications P0 — architecture freeze

**Date:** 2026-08-22  
**Author/owner:** Sol, AI CEO  
**Chairman outcome:** remove Chris from the live Sol↔Fable message relay during an already-active program without creating a Slack task system, pretending Slack wakes models, or weakening Executive OS authority.  
**Status:** **SOL ARCHITECTURE FREEZE / RECORDS ONLY. THIS FILE DOES NOT INSTALL, AUTHENTICATE, MESSAGE, WAKE, DISPATCH, CLAIM, OR COMPLETE ANY SESSION OR JOB.**  
**Protected Mastermind pickup:** `fd88ad761b477a84a95bf514a02d932012f211a5`  
**Macro observation at archaeology:** moving `main`; implementation must re-read current head at pickup.  
**Existing architectural parents:** Macro `MAS-9` Slack transport program and `DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY`.  
**Proposed organizational identity after acceptance:** `WS:ACTIVE-AGENT-COMMS`; do not mint it before this freeze is accepted.

---

## 0. Executive ruling

Mastermind has discovered a distinct communication problem that the earlier generic Slack bus design blurred with dispatch and wake:

> Sol and Fable are already active on the same bounded program, but Chris must copy Fable's decision requests/results into Sol and copy Sol's rulings back into Fable.

That is **active-session communication**, not generic dispatch.

P0 therefore freezes this narrower product:

```text
existing Sol commission thread in #agent-dispatch
        |
        +--> active Fable posts ACK / PROGRESS / DECISION_REQUEST / BLOCKED / RESULT
        |
        +--> active Sol posts RULING / AMENDMENT / CONTINUE / STOP
        |
        +--> both sides cite exact GitHub / Agent OS / Executive evidence
```

Slack remains transport and human-visible conversation. It owns no task, claim, lease, completion, retry, queue, authority, or runtime-delivery state.

The P0 transport is the **official Slack remote MCP connection used by active Claude/Fable sessions**, authenticated as one persistent least-privilege Slack transport principal that can access only `#agent-dispatch`. The persistent Slack principal identifies the transport account only. Every Fable/Claude runtime remains ephemeral and is represented inside the protocol by a non-authoritative, privacy-preserving provider session reference.

P0 explicitly rejects a bespoke Slack daemon, Socket Mode bridge, bot lifecycle database, durable seat inbox, and automatic wake. If the reviewed Slack MCP guest-principal canary fails, P0 stops and returns to Sol. It does not silently fail over to a bot CLI or Executive Relay.

---

## 1. User job and 10/10 end state

### Primary persona

Chairman Chris, operating many simultaneous Sol CEO and Fable/worker sessions.

### User job

For an already-active program, Chris should not carry the substance of routine CEO↔COO coordination between applications.

### 10/10 P0 experience

1. Sol posts or identifies one exact bounded commission thread in `#agent-dispatch`.
2. Chris starts the intended Fable session once and supplies the existing commission/thread reference as part of the launch packet.
3. Fable acknowledges the mission directly in the thread.
4. When a material fork appears, Fable posts a structured `DECISION_REQUEST` with evidence, bounded options, and its recommendation.
5. The accountable Sol session reads the exact thread and posts a structured ruling.
6. Fable reads that ruling, continues the same active work, and later posts `RESULT`, `BLOCKED`, or `PR_READY` with exact evidence links.
7. GitHub, Agent OS, Executive OS, and Linear remain responsible for their existing facts; Slack closes none of them.
8. Chris performs zero copy/paste of the substantive messages between Sol and Fable after the one-time Fable launch.

### Explicit P0 non-promise

P0 does not wake, resume, prompt, or prove visibility to an inactive ChatGPT, Claude, Codex, Cursor, or other provider runtime. A Slack mention or delivered message is not a runtime acknowledgement.

---

## 2. Current capability ledger at freeze

| Capability | State | Evidence / boundary |
|---|---|---|
| `#agent-dispatch` channel and Sol-authored bounded commissions | `PROVEN_LIVE` transport | Existing channel and messages distinguish `DELIVERED` from `ACKED`/execution. |
| Personal-Pro Sol Slack read/write | `PROVEN_LIVE` for current ChatGPT seats | Existing ChatGPT1/2/3 Slack members and messages. |
| Fable/Claude Slack principal in workspace | `NOT_BUILT` | Current channel members are Chris + ChatGPT1/2/3; no Fable/Claude principal. |
| Active Fable native session identity/resume | `PROVEN_LIVE` substrate | CCR P0/#110 real-Mac Fable resume proof; not communication authority. |
| Active Fable→Sol direct Slack return | `NOT_BUILT` | GitHub PR comments and Chris relay remain the practical paths. |
| Sol→Fable direct Slack ruling consumption | `NOT_BUILT` | No Fable Slack connection or protocol skill exists. |
| Generic Slack dispatch / session bootstrap / progress-result bus | `SPEC_ONLY` and architecture-held | MAS-29/30/31; old durable inbox/store design rejected. |
| Automatic CEO/COO wake | `NOT_BUILT` / held | Separate Wake/Phase-1G architecture. |
| Executive Slack command path | `PARTIAL` and separately gated | MAS-48 R0/B1/C1/B2/C2; excluded from this P0. |
| Chairman Control Room navigation | `BUILT_NOT_PROVEN` / held on #110 | Zero-message navigation substrate only; excluded from this P0 implementation. |

Do not average these states into a generic “Slack integration percentage.”

---

## 3. Collision and ownership ruling

### 3.1 Linear Stack Workflow lane

The separate Linear Stack session owns report-only Agent OS→Linear projection, native Linear/GitHub workflow configuration, and low-noise `#build-events` visibility. It does not own protected command channels or active agent communication. Active-agent communication must not edit MAS-65 projector files, Linear app-actor code, or `#build-events` integration configuration.

### 3.2 MAS-48 Executive Relay

MAS-48 owns CEO request/state transport into Executive OS. Active-agent communication must not import or call `ceo_intent`, `CeoIngress`, `SOL_STATE`, Executive SQLite, the Executive Relay, or `#ceo-control-room` command semantics.

### 3.3 Chairman Control Room P0

CCR P0 owns read-only composition and navigation. It explicitly sends zero prompts/messages. This P0 may cite provider/session bindings as transport evidence but does not edit #110 or add communication state to `mastermind.surface_bindings.v1`.

### 3.4 MAS-29/30/31

This freeze **supersedes only the assumption that active-session communication must wait for generic dispatch/wake**. MAS-29/30/31 remain held for inactive-session delivery, bootstrap projection, runtime-visible claims, wake, and generic lifecycle integration. No old durable Slack store/inbox wording is revived.

---

## 4. Identity model

P0 keeps these identities separate:

```text
WORK_REF
  exact Agent OS organizational identity, normally WS:<KEY>

COMMISSION THREAD
  Slack channel_id + top-level thread_ts; transport address, not lifecycle identity

TRANSPORT PRINCIPAL
  one persistent Slack account restricted to #agent-dispatch; transport provenance only

PROVIDER SESSION
  the actual active Claude/Fable runtime; ephemeral and provider-owned

SESSION_REF
  privacy-preserving protocol reference derived from provider + native session identity;
  not a new canonical session registry

MESSAGE_KEY / MESSAGE_ID
  one logical communication item and its deterministic protocol identity

CANONICAL EVIDENCE
  GitHub PR/SHA, Agent OS record, Executive Job/Event, or other owning-system receipt
```

A Slack user is not Fable authority. A `session_ref` is not a claim/lease. A mention is not wake. A `RESULT` message is testimony until its canonical evidence is reviewed.

### 4.1 Persistent transport principal

P0 uses one dedicated Slack transport account, proposed display name `Fable Relay`, configured as a single-channel guest or equivalent workspace-restricted user with access only to `#agent-dispatch`.

It is intentionally persistent so every temporary Fable session does not require a paid Slack identity. It carries no organizational authority and may be shared by sequential or concurrent active Fable sessions; the protocol's `session_ref` and exact thread provide the runtime provenance.

The account must not join:

- `#ceo-control-room`;
- future `#sol-runtime`;
- `#build-events`;
- `#company-intelligence`;
- private DMs or unrelated channels.

### 4.2 Session privacy

The raw Claude/CLI provider session identifier remains local. The protocol derives:

```text
session_ref = <provider>-<lowercase 16-byte/32-hex digest>
```

No transcript, prompt text, provider token, cookie, credential, local filesystem path, email, browser profile, or raw native session ID enters Slack.

---

## 5. Transport architecture

### 5.1 Chosen P0 carrier

The Fable side uses the official Slack remote MCP endpoint configured at project scope in the execution repository. OAuth is completed interactively for the dedicated transport principal. No OAuth token or Slack credential is committed.

The Sol side uses the existing approved ChatGPT Slack connector under the accountable ChatGPT seat.

### 5.2 Why not a custom bot/daemon first

A daemon would add process lifecycle, credentials, reconnect behavior, Socket Mode event handling, retry semantics, and likely a new pending-message representation before the product question has been proven. Active sessions already have a synchronous tool surface. P0 uses that narrower surface first.

### 5.3 One carrier / no failover

A communication item created through the Slack MCP carrier remains bound to that carrier/thread. A timeout or uncertain send is reconciled by reading the exact thread for the same deterministic `message_id`. It is never blindly reposted through GitHub comments, another Slack account, or Executive Relay.

If the official remote MCP endpoint, guest authorization, channel restriction, exact text preservation, or read-after-write behavior fails the canary, status is `BLOCKED_PLATFORM_CAPABILITY`. Do not add a hidden bot fallback in the same wave.

---

## 6. Protocol: `mastermind.active_agent_comms.v1`

Every machine-parseable message has exactly this framed shape:

```text
MMX/ACTIVE_AGENT_COMMS_V1
<one canonical single-line JSON object>
```

A platform-added attribution trailer may appear only after the two-line canonical payload and only when it matches a separately validated transport grammar. The trailer is non-authoritative and excluded from message identity/fingerprint material. Unknown trailing content refuses machine parsing.

### 6.1 Closed message kinds

Fable/worker-originating:

- `SESSION_ACK`
- `PROGRESS`
- `DECISION_REQUEST`
- `BLOCKED`
- `RESULT`
- `PR_READY`

Sol-originating:

- `RULING`
- `AMENDMENT`
- `CONTINUE`
- `STOP`

`CANARY` is permitted only in a clearly labeled zero-authority test thread.

### 6.2 Common fields

The canonical object contains only reviewed high-level fields:

- `schema` = `mastermind.active_agent_comms.v1`
- `kind`
- `message_key`
- `message_id`
- `fingerprint`
- `work_ref`
- `session_ref`
- `sender_role` (`ceo|coo|worker|reviewer`)
- `target_seat_ref` (`chatgpt1|chatgpt2|chatgpt3|fable-relay|none`)
- `created_at`
- `summary`
- `in_reply_to` (`message_id|null`)
- `evidence_refs` (bounded HTTPS references)
- `payload` (kind-specific closed object)

Unknown fields refuse. Whole framed body target ceiling is 3,500 UTF-8 bytes.

### 6.3 Identity and conflict law

`message_id` is derived deterministically from protocol namespace + `work_ref` + `session_ref` + `kind` + `message_key`.

`fingerprint` is derived from canonical normalized semantics excluding only `fingerprint` itself.

- same `message_id` + same fingerprint = duplicate/reconciliation of one communication item;
- same `message_id` + changed fingerprint = `MESSAGE_CONFLICT`, never a second item;
- changed communication = new explicit `message_key`.

Slack message/event/timestamp IDs are transport evidence, not logical message identity.

### 6.4 Kind-specific requirements

`DECISION_REQUEST` requires:

- one decision question;
- two to five bounded options;
- Fable's recommendation and why;
- whether work is blocked pending the ruling;
- the smallest safe reversible action, if any, that may continue independently.

No material decision silently defaults from Sol silence.

`RULING` requires:

- `in_reply_to` naming the exact `DECISION_REQUEST`;
- disposition `ANSWER|CONTINUE|AMEND|HOLD|STOP`;
- concise rationale;
- exact allowed next action and non-goals.

`RESULT` / `PR_READY` require exact evidence references. They do not claim merge, production proof, Agent OS closeout, Linear completion, or Executive terminality unless the owning source itself proves it.

---

## 7. Thread and conversation law

1. Every program communication loop begins from one top-level bounded commission thread in exact `#agent-dispatch` channel `C0BSBM78V1N` for the current workspace.
2. Fable messages for that mission are replies in that exact thread.
3. Sol rulings are replies in the same thread.
4. The project skill/config may identify the channel and approved Sol user mappings, but never credentials.
5. No routine DMs, group DMs, one-channel-per-workstream, or cross-posting.
6. A thread can carry transport conversation but never becomes the canonical handoff or workstream record.
7. Material accepted rulings and discoveries are copied into their lawful durable owners during normal PR/Agent OS closeout—not through an automatic Slack lifecycle importer in P0.

---

## 8. Authority and security boundaries

The transport principal and model may never author:

- Executive actor/authority lists;
- Job/Attempt/Worker state;
- branch/worktree/argv/credential fields for Executive admission;
- merge/deploy/service-control approval;
- Chairman approval/decision commit;
- a lifecycle status, lease, ownership claim, or completion verdict merely from Slack;
- Slack app/token/OAuth material;
- unrestricted destination channel/user IDs;
- raw private evidence or secrets.

P0 implementation must fail closed on at least:

- wrong channel or missing thread;
- unknown kind/role/seat;
- invalid work/session/message identity;
- unknown keys;
- oversize body;
- malformed JSON/UTF-8;
- unknown trailer;
- disallowed/credential-bearing URL;
- duplicate ID with changed payload;
- target seat not in approved mapping;
- missing kind-specific fields;
- MCP unavailable/not authenticated;
- transport response uncertain;
- message absent or altered on exact readback.

Slack source identity and payload role are evidence only; neither grants authority.

---

## 9. Product workflow

### 9.1 Commission

Sol creates the bounded commission through existing human/session procedures. It includes:

- exact work_ref;
- exact Slack channel/thread;
- accountable Sol seat;
- exact authority packet and stop condition.

This initial launch may still be conveyed to Fable by Chris in P0. Removing the launch step is later dispatch/wake work.

### 9.2 Active work

Fable loads the repository's `agent-comms` skill, derives a privacy-safe session_ref, validates the existing commission thread, and posts `SESSION_ACK`.

### 9.3 Mid-run fork

Fable posts `DECISION_REQUEST` only when the fork is material to product/architecture/authority/scope, not for routine implementation choices inside the frozen commission.

### 9.4 Sol response

The accountable Sol session reads the exact thread, validates message identity/evidence, resolves the decision against canonical sources, and posts one ruling.

### 9.5 Return

Fable posts `PR_READY`, `RESULT`, or `BLOCKED`; GitHub and Agent OS still carry the durable evidence/continuation. Sol reviews under `REVIEW_RETURN.md`.

---

## 10. P0 implementation surfaces

After this architecture merges, the first implementation wave may touch only:

### Mastermind

- protected Sol Skillpack procedure for reading/responding to active-agent comms;
- deterministic protocol contract/test vectors if Mastermind owns the shared contract;
- no Executive runtime/Slack Executive package/CCR UI change.

### Macro representative Fable execution repository

- project-scoped remote MCP declaration with no secret;
- `.claude/skills/agent-comms/**` procedure;
- deterministic stdlib protocol builder/parser + tests;
- optional non-secret allowlist/config for current workspace/channel/ChatGPT seats;
- Agent OS records and continuation.

No `.github/workflows/**`, production daemon, launchd, Slack SDK dependency, Socket Mode, network call in ordinary tests, or credentials are authorized merely to prove the protocol.

---

## 11. Acceptance matrix

P0 is accepted only when all applicable rows have real receipts:

1. Current Mastermind/Macro heads and open collisions re-read before implementation.
2. Protocol builder emits byte-deterministic canonical payloads.
3. Parser accepts exact two-line payload and rejects unknown trailer/keys/kinds.
4. Every message-kind required-field mutation is killed by a discriminating test.
5. Message ID/fingerprint duplicate and conflict laws are proven.
6. Raw provider session ID never appears in generated body/log/error.
7. Credential/token/path/email-shaped values are refused or redacted.
8. Destination is fixed to the approved `#agent-dispatch` channel/thread.
9. Dedicated Slack transport principal is created/restricted to the one channel.
10. Official Slack remote MCP OAuth succeeds for that principal on the real Mac.
11. Fable project MCP connection exposes the required read-thread/send-reply operations.
12. Exact inert `CANARY` post appears once in the intended thread.
13. Exact readback is byte-equivalent over the canonical payload span.
14. Duplicate send reconciliation creates no second logical item.
15. Edited/altered message fails validation rather than being silently accepted.
16. One real active Fable session posts `SESSION_ACK`.
17. The same Fable session posts a real `DECISION_REQUEST` or bounded canary equivalent.
18. The accountable Personal-Pro Sol seat reads it without Chris copying its contents.
19. Sol posts a `RULING` in the same thread.
20. The same active Fable session reads and acknowledges the ruling.
21. Fable continues and posts a real `PR_READY`/`RESULT` evidence reference.
22. Sol verifies the cited GitHub evidence independently.
23. Slack delivery is never reported as runtime wake, execution, or completion.
24. No Executive Job/Event, Agent OS workstream state, Linear issue, PR, or deployment changes merely from a Slack message.
25. No new DB/table/queue/inbox/cursor/store exists.
26. The transport principal cannot access protected Executive/visibility/intelligence channels.
27. Disconnect/re-auth produces visible unavailable state; no blind resend/failover.
28. Fresh Sol and Fable sessions can recover procedure from protected/current Git without this chat.
29. Exact-head CI is green for every implementation PR.
30. Durable closeout records the production result and exact next action.

Rows 9–21 are production proof, not satisfiable by fixture tests or a docs merge.

---

## 12. Sequence and stop conditions

### F0 — this architecture

One records-only Mastermind architecture PR. Merge proves only that the product/authority design is accepted.

### A0 — Agent OS establishment

Create the exact `WS:ACTIVE-AGENT-COMMS` decision/workstream/handoff in Macro after F0 acceptance. Do not mint a Linear issue first.

### P0-A — deterministic protocol + procedures

Implement the Sol/Fable skills and pure protocol builder/parser with zero live Slack mutation. Return one held implementation packet.

### S0 — platform/principal canary

Chairman/admin creates the dedicated one-channel Slack transport principal and performs one OAuth connection to the official Slack remote MCP. Run only inert protocol canaries.

### P0-B — real closed-loop canary

One active Fable session and one accountable Sol session execute the real ACK→DECISION_REQUEST→RULING→PR_READY loop on a harmless bounded mission.

### Closeout

Record what is proven live, what remains held, and whether the next wave is:

- rollout to additional execution repositories;
- CCR read-only “waiting on Sol / return available” projection;
- or a separately frozen wake/bootstrap program.

### Hard stop

Do not implement inactive-session dispatch, automatic prompt delivery, Wake, Executive admission, a bot/daemon fallback, a durable Slack inbox, lifecycle persistence, or CCR communication state in P0.

---

## 13. Fable principal-builder commission after acceptance

### Observable mission

A real active Fable session and a real Personal-Pro Sol session complete one evidence-bound Slack thread loop—ACK, decision request, ruling, and PR-ready return—without Chris relaying the message contents and without any new lifecycle store or wake claim.

### Why it matters

This removes the highest-frequency biological message-bus work while preserving the high-quality Sol executive control loop the Chairman has observed to outperform autonomous end-to-end COO execution.

### Authority precedence

1. Chairman's current outcome and this accepted freeze.
2. Current protected Sol Skillpack.
3. Macro Slack transport/Agent OS decisions.
4. Current GitHub implementation evidence.
5. Linear only as projection.

If a newer accepted source changes Slack/MCP/Executive/CCR ownership during the wave, stop and return to Sol rather than merge-resolving the authority conflict.

### Exact scope

One primary protocol/procedure implementation, one representative Macro Fable workflow, and only the smallest protected Skillpack addition required for Sol. No generic bus.

### Required return

Exact pickup/final SHAs, PRs and changed-file census; protocol test vectors; no-secret/no-store/import/network proofs; Slack principal/channel scope receipt; MCP OAuth/tool census; exact canary thread/message IDs; canonical payload readback; real Fable/Sol loop transcript references; CI; conflicts; explicit non-goals remaining unstarted.

### Stop

Stop at one proven active-session loop and return to Sol. Do not begin wake, inactive delivery, CCR projection, or repository-wide rollout.

---

This is the architecture: **active sessions communicate through one least-privilege Slack thread and a deterministic non-authoritative protocol; canonical systems continue to own every durable fact.**
