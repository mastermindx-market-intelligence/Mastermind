# Grok Secretary → Mastermind MCP → OpenClaw — Architecture Amendment

**Date:** 2026-08-28  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Workstream:** existing `WS:CHAIRMAN-CONTROL-ROOM`  
**Operation key:** `grok-secretary-mastermind-mcp-openclaw-f0-20260828-sol-001`  
**Protected basis:** `Mastermind@97f85ce5b84030faf4d291f988a1c642fb15e80a`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY / PRODUCTION DISARMED.** This document creates no MCP listener, public endpoint, token, OAuth client, Grok connector, OpenClaw pairing, Mac permission, browser action, Wake delivery, provider call, Executive mutation, Slack message, service installation or production authority.

## 1. Authority and relationship to existing law

This is a narrow implementation-facing amendment to:

1. `docs/superpowers/specs/2026-08-27-mastermind-operating-surface-convergence-design.md`;
2. `docs/superpowers/plans/2026-08-27-mastermind-operating-surface-convergence-program.md`;
3. `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`;
4. `docs/superpowers/plans/2026-08-27-operator-continuity-ocr6-slack-steward-projection.md`;
5. `docs/EXECUTIVE_MCP.md` and the accepted Executive MCP security pattern;
6. the Worker Presence / company-dialogue MCP source law.

For the exact Grok Secretary, public MCP ingress and subordinate OpenClaw topics below, this amendment supplies the detailed boundary. It does **not** supersede canonical lifecycle, identity, capacity, Wake, Agent Relay, Control Room, Session Truth, surface-binding or Operator Continuity owners.

The protected operating-surface convergence ruling remains controlling:

- Executive OS owns Job / Attempt / Worker / Event lifecycle and CEO-intent admission;
- Agent OS owns durable organizational workstreams, decisions, discoveries and handoffs;
- strategic state and the Improvement Agenda retain their declared company-priority authority;
- GitHub owns implementation, review, CI and proof truth;
- Linear is selective human portfolio projection;
- Slack / Agent Relay is transport, dialogue and hot-state visibility;
- Shared AI Provider Control / Capacity Fabric owns provider/account capacity observations and lawful placement evidence;
- OHF/provider adapters own concrete execution after selection;
- Worker Presence and Wake retain attention, route, delivery, ACK and source-resolution authority;
- Control Room / Executive Steward remains a pure read/attention composition;
- OpenClaw remains optional, subordinate and removable.

There is no new `Mastermind-OS` database, scheduler, queue, actor registry, session registry, retry ledger, memory store, capacity router, Wake plane or device lifecycle.

## 2. Chairman outcome

Chris can speak to Grok Secretary at the company level instead of hunting through ChatGPT managed-browser seats, Claude Code sessions, Codex apps and Mac windows.

Representative requests:

```text
"Open the Sol session working on the China market dislocation."
"Which Fable responsibility returned and needs Sol?"
"Bring the exact Claude session for Market Ontology to the foreground."
"Open the Codex thread working on PR X."
"Explain why this responsibility is blocked."
"Nudge the exact current session."
```

The accepted system must:

1. resolve the logical responsibility from canonical Mastermind truth;
2. resolve the exact current runtime/session/surface without guessing from window titles or recency;
3. apply a server-owned policy decision;
4. prefer provider-native session/Wake mechanics where accepted;
5. use OpenClaw only as a bounded physical actuator when required;
6. verify the exact target/postcondition;
7. return a typed receipt without making transport success look like runtime ACK or task completion.

The 10/10 end-state is not “Grok can click a Mac.” It is:

> Chris asks for a company responsibility; Mastermind identifies the one lawful target; the correct provider-native or Mac surface is foregrounded, inspected or nudged; ambiguity and effect uncertainty fail closed; and all canonical company truth remains recoverable when Grok or OpenClaw is removed.

## 3. Final topology

```text
Chairman Chris
      |
      v
Grok Secretary / Grok Bot
      |
      | public authenticated Streamable HTTP MCP
      v
+--------------------------------------------------+
| Mastermind MCP platform                         |
|                                                  |
|  existing Executive MCP (unchanged v1 surface)  |
|  company-dialogue MCP (separate bounded surface)|
|  Secretary MCP (new bounded surface)            |
+-------------------------+------------------------+
                          |
            +-------------+------------------+
            |                                |
            v                                v
  Executive Steward /                  Actuation policy
  Session Truth / CCR                        |
  Executive + Agent OS                       +--> accepted native Wake/session path
  GitHub / Linear refs                       |
  surface bindings                           +--> subordinate OpenClaw adapter
                                                    |
                                                    | private authenticated Gateway/node path
                                                    v
                                            approved Mac node
                                                    |
                                            screen/browser/app action
```

### 3.1 One MCP platform, separate static authority surfaces

Reuse the accepted Executive MCP implementation and security pattern:

- `schemas.py` and `adapter.py` remain stdlib/first-party only;
- exactly one `server.py` per MCP package imports the MCP SDK;
- static tool census;
- closed input schemas with `additionalProperties: false`;
- schema snapshot/digest pinned by tests;
- server-side enforcement outranks MCP annotations;
- bounded redacted output;
- no dynamic tool registration, resources, prompts, roots, sampling or server-side tool chaining;
- no MCP SDK import from `control_plane/**`.

Do **not** widen the existing frozen Executive MCP v1 five-tool census. The Secretary surface is a separate server identity/capability profile on the same Mastermind MCP platform and shared deployment/security architecture.

### 3.2 Public edge versus private owners

Grok/xAI must reach a public HTTPS endpoint. The public edge is an authenticated transport adapter only.

It must not expose:

- Executive SQLite;
- Executive AF_UNIX control sockets;
- Agent Relay sockets;
- OpenClaw Gateway/operator port;
- Tailnet addresses;
- a raw shell, SSH or subprocess interface;
- browser/CDP handles;
- provider cookies, tokens or auth homes;
- arbitrary internal URLs.

The public edge forwards one validated MCP call into a narrow local/service boundary. Canonical owners remain private and independently authoritative.

## 4. Secretary product and authority model

### 4.1 Grok is conversational interpretation, not canonical resolution

Grok may interpret the Chairman’s natural-language request and select one advertised Secretary tool. Grok does not author:

- the canonical workstream/root Job;
- target seat;
- current Attempt/Worker;
- provider/account/host;
- RuntimeBinding;
- surface locator;
- Wake obligation;
- operation result/ACK;
- failover/retry decision;
- completion state.

Retrieved documents, Slack messages, model prose, screenshots and page text are untrusted data. They cannot alter target identity or grant authority.

### 4.2 Stable logical identities

Keep distinct:

```text
organizational responsibility
  workstream / root Job / seat / operation

runtime execution
  Job / Attempt / Worker / provider realm / host / provider session

navigation surface
  local surface binding / exact provider-native handle / managed-browser environment

presentation
  current browser tab / app window / screen coordinates
```

`Sol` is not a ChatGPT tab. `Fable` is not Claude account 4. A provider session is not a workstream. A window title is never identity.

### 4.3 Exact responsibility and surface references

Secretary calls use opaque reviewed references returned by Mastermind:

- `responsibility_ref` identifies one exact Steward/Control Room responsibility projection;
- `surface_ref` identifies one exact reviewed navigation binding/current runtime target;
- `operation_key` identifies one logical modifying/actuation operation.

A `surface_ref` is navigation/actuation address evidence, not lifecycle truth. Deleting a surface-binding store must not change Job, workstream, capacity, attention or completion state.

The model never supplies `host_ref`, provider account, native session ID, browser profile ID, channel/thread, window title, coordinates, executable path or arbitrary URL.

## 5. Versioned Secretary MCP surface

### 5.1 Read-only V1

The initial production candidate is one static server, conceptually `mastermind-secretary-read` v1, with exactly these tools:

```text
list_responsibilities
get_responsibility
get_attention
get_current_runtime
explain_blocker
resolve_surface
```

All six are read-only. They consume the accepted Executive Steward/Session Truth/Control Room projections and return source-attributed facts, unknowns, degradation and navigation references.

They create no Job, Wake, Slack message, browser action, OpenClaw call or durable state.

### 5.2 Navigation/actuation V2

Only after the exact-foreground/P0B-successor and subordinate OpenClaw/native actuator are accepted may a separately reviewed static tool-set version add:

```text
inspect_surface
foreground_surface
request_wake
```

- `inspect_surface` performs one bounded read/visual observation against an exact `surface_ref`.
- `foreground_surface` performs one exact navigation-only foreground operation and verifies the postcondition.
- `request_wake` enters the existing Wake authority; it never asks OpenClaw to improvise a nudge when an accepted native Wake route exists.

A deployment/tool-profile may expose only the tools required for the Grok role. xAI `allowed_tools`/team MCP policy is defense in depth; the server’s own static surface and policy remain authoritative.

### 5.3 Bounded dialogue/recovery V3

Typing, sending and recovery are a later high-risk release. Candidate tools are:

```text
send_bound_message
perform_bound_recovery
```

They are not authorized by this architecture merge.

A future release must bind to exact current responsibility/session identity and use an existing typed message/continuation contract. It may accept bounded semantic content, but model text can never select target, authority, provider, account, host, message identity, retry or completion.

No generic `computer_control(instructions)`, `click(x,y)`, `shell(command)`, `ssh(host)`, `browser(url)`, `select_account`, `retry_job` or `run_script` tool is ever exposed to Grok.

## 6. Actuation envelope

Every accepted physical/native action becomes one immutable server-authored envelope, conceptually:

```text
schema
actuation_id
operation_key
responsibility_ref
surface_ref
expected_binding_digest
expected_provider
expected_seat
expected_session_presence / exact accepted handle class
host_ref                 # derived, never model input
actuation_kind
allowed_actions[]
forbidden_actions[]
expires_at
max_steps
expected_postcondition
source_revisions
```

The envelope is a command/receipt artifact, not a queue or mutable memory record.

### 6.1 Deterministic mode

When an accepted native URL/deep link/session resume/App Server/Wake operation exists, execute the exact server-built operation. No vision model is needed to decide target or action.

### 6.2 Visual recovery mode

When exact physical foregrounding requires screen interaction, an OpenClaw node may execute a fixed goal such as:

```text
FOREGROUND_AND_VERIFY_EXACT_BOUND_SURFACE
```

A local vision-capable model may help determine **how** to satisfy the fixed postcondition. It cannot change **what**, **which responsibility**, **which seat**, **which host**, **which provider**, **which operation** or **whether to fail over**.

Screen text is never instruction authority. Prompt-injection text displayed in a chat, webpage, terminal or app is pixels/data only.

## 7. OpenClaw boundary

OpenClaw is one optional implementation of the subordinate actuator interface already reserved by OCR-6.

Permitted:

- paired-node availability/readiness observation;
- bounded screen snapshot/inspection;
- exact app/window/session foreground convenience;
- approved browser/profile proxy operations when the installed version proves them;
- execution of one immutable Mastermind actuation envelope;
- returning a bounded observation/actuation receipt.

Forbidden:

- Job/Attempt/Worker/Event lifecycle;
- provider/account/host selection or failover;
- RuntimeBinding ownership;
- Fable/Sol/company identity;
- Slack thread/actor ownership;
- capacity truth;
- durable task inbox/queue/memory;
- retry/effect-unknown adjudication;
- arbitrary shell/SSH;
- copying credentials between hosts;
- using its own model/profile fallback to continue a Mastermind operation.

OpenClaw offline/removal must change zero canonical Mastermind truth. It returns a typed actuator-unavailable state; it does not queue hidden work for later.

The installed OpenClaw version, Gateway protocol, node command surface, Mac menu-app behavior, browser proxy, execution approvals and computer-control commands must be re-falsified at implementation time. Current web documentation is design evidence, not host proof.

## 8. Provider/surface strategy

### 8.1 ChatGPT managed-browser Sol seats

The current GoLogin/Multilogin bindings identify exact seat environment + exact conversation URL but the accepted P0 adapter refuses unsupported vendor control of a running environment.

The required P0B/successor outcome is exact intended-seat and exact bound-conversation foreground proof:

```text
exact managed environment identity
+ exact private conversation URL
+ exact target Mac
→ foreground and verify that exact seat/conversation
```

No cross-seat fallback, guessed title, newest-tab heuristic, hidden credential exposure or Chairman window hunting.

OpenClaw computer control may be a candidate mechanism only after installed-host proof. It does not become the acceptance owner; the product outcome and exact-target proof law remain the ruler.

### 8.2 Claude Code / Fable

Prefer in order:

1. exact accepted Worker/Attempt/provider-native session identity;
2. accepted Claude native resume/Wake transport;
3. OpenClaw foreground/inspection of the native cockpit only as a bounded fallback/convenience.

OpenClaw does not choose a Claude account, infer returned work from an idle window, transplant a conversation or bypass Capacity Fabric/Operator Continuity.

### 8.3 Codex

Prefer current Operator Harness / Codex App Server thread/session identity and accepted native Wake mechanics. OpenClaw may foreground the Codex app/cockpit after Mastermind resolves the exact thread; it does not mint or select a substitute thread.

### 8.4 Other surfaces

Cursor/Grok/native apps follow the same law: exact provider-native address first, bounded physical foreground only when necessary, explicit `UNSUPPORTED`/`AMBIGUOUS` rather than heuristic ownership.

## 9. Network and authentication architecture

### 9.1 Supported external transport

The Grok-facing endpoint uses HTTPS Streamable HTTP MCP (SSE only if an accepted client/server combination requires it). xAI currently documents public remote MCP with `server_url`, optional Authorization token/headers and tool allowlisting, and its custom-connector flow requires public reachability.

Do not publish the existing Executive MCP stdio server or weaken its loopback/sealed boundary. Build/reuse one reviewed public MCP edge that can host separate static server identities behind exact authentication and policy.

### 9.2 Authentication

No unauthenticated production endpoint.

At implementation time select one provider-supported path proven in the actual Grok/Grok Bot surface:

- OAuth through the custom connector flow; or
- a dedicated scoped Authorization bearer/header installed through the supported team/connector policy.

The secret is generated/stored through the approved host/secret owner and never appears in Git, Slack, chat, argv, logs, screenshots, MCP output or model context. Authentication proves connector principal, not Chairman/CEO authority; tool policy and Mastermind source law still apply.

Grok Bot/team MCP policy and the ordinary Grok custom connector are distinct installation surfaces. The implementation preflight must identify which actual surface is used and prove its current tool allowlist/auth behavior rather than assuming parity.

### 9.3 Private OpenClaw transport

OpenClaw Gateway/node communication stays private and authenticated. No public route forwards arbitrary Gateway/node requests. The Mastermind adapter owns the exact allowlist and maps one accepted envelope to one node command sequence.

## 10. Idempotency, ambiguity and effect-unknown law

### Read calls

Read calls may retry only under the accepted transient/read bounds and must preserve source timestamps/freshness.

### Actuation calls

- one `operation_key` = one logical actuation;
- same key + same canonical fingerprint = duplicate reconciliation;
- same key + changed payload = conflict/refusal;
- timeout/cancel/disconnect after possible effect = `EFFECT_UNKNOWN`;
- `EFFECT_UNKNOWN` stays on the same target/carrier and is reconciled by exact postcondition/status observation;
- no cross-host/provider/account/surface failover;
- no blind resend of a possible message/send/click/submit operation.

Foregrounding may be retriable only when the operation is proven navigation-only/idempotent and the exact target remains current. Message send and any modifying UI action require stronger reconciliation.

## 11. Failure vocabulary

At minimum preserve typed outcomes such as:

```text
RESPONSIBILITY_NOT_FOUND
RESPONSIBILITY_AMBIGUOUS
SOURCE_UNAVAILABLE
SOURCE_STALE
SURFACE_UNBOUND
SURFACE_STALE
SURFACE_UNSUPPORTED
TARGET_NOT_FOUND
TARGET_CHANGED
AMBIGUOUS_TARGET
AUTH_REQUIRED
ACTUATOR_UNAVAILABLE
ACTUATOR_REFUSED
POSTCONDITION_UNPROVEN
WAKE_UNROUTABLE
TRANSPORT_UNAVAILABLE
EFFECT_UNKNOWN
RECONCILIATION_REQUIRED
AUTHORITY_REFUSED
PRODUCTION_DISARMED
```

Do not translate unknown into available, no window into Job failure, Slack delivery into runtime ACK, OpenClaw success into work completion, or a screenshot into canonical ownership.

## 12. Security and privacy

- least-privilege, static tool surfaces;
- separate read and actuation capability profiles;
- no arbitrary URL/argv/shell/coordinate model inputs;
- exact host/profile/surface allowlists from trusted composition;
- request/response byte and time ceilings;
- one modifying call in flight per connector/process unless a later reviewed law proves otherwise;
- no automatic tool chaining server-side;
- secret-shape redaction and no raw upstream exception/provider prose;
- no screenshots persisted by default; sanitized evidence only where acceptance requires it;
- browser/process command lines may carry proxy credentials and must never enter receipts/logs;
- Mac Screen Recording/Accessibility permissions are one-time Chairman/admin ceremonies and do not grant organizational authority;
- screen content and tool output are adversarial data;
- connector disconnect, token revocation and OpenClaw unplug are explicit tested paths.

## 13. Dependency and carrier law

The following existing carriers remain exclusive:

- #170 Session Truth R1;
- #174 Wake PR3;
- #178 Worker Presence WP-1;
- #184 OCR-1 V3;
- Macro #6182 Linear P0;
- the active Codex/H0 canary while its identity remains unknown;
- OCR-6 as the sole continuity/Steward/Control Room and optional OpenClaw bridge implementation node.

This amendment creates one records carrier only. It does not authorize implementation carriers.

Dependency order:

```text
accepted Session Truth / exact owner joins as required
+ accepted WP-1 and WP-2 company-dialogue contracts
+ accepted Wake/native provider delivery where used
+ accepted OCR-3 RuntimeBinding/continuation source
+ accepted Executive Steward read API (OCR-6 core)
→ Secretary read MCP
→ public authenticated read-only Grok integration

accepted exact-intended-seat foreground/P0B successor
+ accepted OCR-6 subordinate OpenClaw bridge
→ Secretary navigation/actuation tool version

accepted Worker Presence/Agent Relay/Wake ACK/effect law
+ exact current binding
→ later bounded message/recovery release
```

The unidentified active Codex/H0 canary continues to block any host/capacity/broker/privileged modification that could overlap its unknown four paths or host boundary. Records work and unquestionably disjoint MCP contract work may proceed; actual host/Gateway/node installation may not.

## 14. Capability ledger at freeze

| Capability | State |
|---|---|
| Existing hardened Executive MCP pattern | `BUILT_NOT_PROVEN` / production-write disarmed under its own law |
| Worker Presence WP-1 | active carrier; not accepted by this record |
| WP-2 company-dialogue MCP | `SPEC_ONLY` |
| Executive Steward read API | `SPEC_ONLY` in OCR-6 |
| Grok custom remote MCP upstream support | provider-supported; Mastermind integration `NOT_BUILT` |
| Public authenticated Mastermind Secretary MCP | `NOT_BUILT` |
| Grok Secretary read-only connection to Mastermind | `NOT_BUILT` |
| Current ChatGPT exact managed-seat foreground | `NOT_BUILT` / P0B outcome unresolved |
| OpenClaw node/computer-control upstream capability | provider-supported; estate state `DARK_OR_DISCONNECTED` until host proof |
| Mastermind subordinate OpenClaw adapter | `NOT_BUILT` |
| Exact ChatGPT/Claude/Codex surface foreground through Grok | `NOT_BUILT` |
| Bounded wake through Grok | `NOT_BUILT` end to end |
| Bounded message/recovery through Grok | `NOT_BUILT` |

No upstream documentation upgrades the Mastermind estate.

## 15. Acceptance ruler

### Read-only proof

From the actual Grok Secretary/Grok Bot surface, with the real authenticated connector:

- list current responsibilities from canonical projections;
- identify which exact item needs Chairman/Sol/COO;
- explain current runtime/blocker/degradation with source attribution;
- unknown/unavailable sources remain typed unknown;
- disconnecting Grok changes zero canonical truth.

### Exact foreground proof

- ChatGPT: exact intended managed-browser seat + exact bound conversation, no cross-seat fallback;
- Claude: exact current accepted provider-native session/cockpit;
- Codex: exact current App Server/thread/cockpit;
- wrong/stale/ambiguous target yields refusal and zero unintended interaction;
- no credential exposure;
- real desktop proof at relevant host/display state.

### Adverse proof

- malicious screen/page text cannot alter target/authority;
- OpenClaw offline returns `ACTUATOR_UNAVAILABLE`; Mastermind state remains intact;
- connector token revoked blocks access;
- target changes between resolution and action -> `TARGET_CHANGED`;
- multiple plausible windows -> `AMBIGUOUS_TARGET`;
- send/submit timeout after possible effect -> `EFFECT_UNKNOWN`, zero retry/failover;
- provider capacity unknown cannot select an account;
- Slack delivery cannot claim Wake ACK or execution;
- removing OpenClaw loses no Job, workstream, binding, dialogue or history.

### Chairman completion

Without reading `#agent-dispatch` or hunting among windows, Chris can ask Grok to explain and foreground the correct responsibility across the normal supported ChatGPT/Claude/Codex journeys. Later message/recovery completion requires its own accepted proof and cannot be inferred from foregrounding.

## 16. No-rebuild boundaries

Reject any implementation that creates or exposes:

- another Job/Attempt/Worker/Event plane;
- another workstream/decision/handoff store;
- another RuntimeBinding/session database;
- an OpenClaw task queue or Mastermind registry;
- a generic remote shell/SSH/computer-control MCP;
- a provider/account selector in Grok/OpenClaw;
- a Slack task queue;
- a hidden retry/failover ledger;
- an MCP dynamic plugin marketplace for company authority;
- a public Executive control socket;
- a credential synchronization service;
- a window-title/recency ownership heuristic;
- a model-authored canonical target or completion state.

## 17. Primary-source mechanics to re-check at implementation time

- xAI custom connectors: `https://docs.x.ai/grok/connectors`
- xAI custom MCP public reachability/tunneling: `https://docs.x.ai/grok/connectors/custom-mcp-tunneling`
- xAI remote MCP tool configuration/auth/tool allowlisting: `https://docs.x.ai/developers/tools/remote-mcp`
- xAI Grok Bot team MCP policy: `https://docs.x.ai/grok-bot/teams-and-enterprises`
- OpenClaw nodes/Gateway/node.invoke: `https://docs.openclaw.ai/nodes`
- OpenClaw node host/browser proxy/approvals: `https://docs.openclaw.ai/cli/node`
- OpenClaw xAI provider/Grok model path, only if a local visual agent is later used: `https://docs.openclaw.ai/providers/xai`

Provider documentation controls supported mechanics; this repository controls Mastermind authority and product acceptance.

## 18. Freeze verdict

The accepted architecture is:

> **One Mastermind MCP platform, one canonical company fabric, a read-only Grok Secretary first, and an optional bounded OpenClaw/native actuator only after exact responsibility and surface resolution.**

The next document supplies the bounded implementation program. This records carrier makes none of it live.
