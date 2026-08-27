# Mastermind Worker Presence & Dialogue Gateway

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** CHAIRMAN APPROVED DESIGN CANDIDATE / RECORDS ONLY. This document creates no Executive Job, Attempt, Worker, Slack app installation, Slack credential, MCP credential, Wake delivery, provider process, runtime service, or production authority by itself.  
**Operation key:** `worker-presence-dialogue-wp0-20260827-sol-001`  
**Protected Mastermind / Skillpack basis:** `8affa1c0403f4400825371bea0257f360a4814f2`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1.  
**Current organizational owners extended, not replaced:** Executive OS; `WS:CHAIRMAN-CONTROL-ROOM` / Active-Session Dialogue; `WS:EXECUTIVE-CAPACITY-FABRIC`; Executive Wake Fabric; Agent OS.  
**Predecessor architecture:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md` / Mastermind #172; Codex-Sol conformance accepted in #173.

---

## 1. Outcome

Mastermind-X should feel like an actual AI company in Slack without making Slack another scheduler, identity database, lifecycle plane, or source of authority.

The Chairman and Sol should be able to see which governed executive surface or worker is speaking, follow its progress, answer a bounded decision request, and observe the final result in a coherent Slack conversation. Codex, Fable/Claude, and later heterogeneous Executive workers should all use the same company-dialogue capability even when their provider, host, runtime, or paid account differs.

The end state is:

```text
Chairman / Sol
      |
      v
Slack workspace
      |
      v
one Mastermind Agent Relay / Slack app principal
      |
      v
one worker-aware dialogue gateway
      |
      v
trusted Executive / runtime identity binding
      |
      +--> Codex-Sol reasoning surface
      +--> Fable / Claude COO surface
      +--> Executive Worker W-...
      +--> later GLM/Grok/Qwen/local worker adapters
```

Slack presents useful logical actors such as `Mastermind · Sol/Codex`, `Mastermind · Fable`, or `Mastermind · Worker W-7A29`, while the underlying Slack bot principal remains one application principal and the canonical runtime identity remains Executive Job/Attempt/Worker truth.

### 1.1 Chairman job

See the company working without manually carrying messages between sessions, without needing one paid Slack member per machine worker, and without learning which provider account, Mac, native thread, or subprocess happens to embody a worker.

### 1.2 Sol job

Use Slack as a human-readable communication and attention surface while retaining Executive OS as runtime authority, Agent OS as durable organizational memory, GitHub as implementation/evidence truth, and Wake Fabric as continuation authority.

### 1.3 Worker job

A governed worker can read only its bound company-dialogue context and emit only the bounded message classes its current execution grant permits. It never receives the Slack bot token and cannot claim a different Job, Attempt, Worker, executive seat, workstream, or Slack presentation identity by writing those strings in model output.

### 1.4 Machine job

Project one canonical Executive/runtime actor into Slack, validate every dialogue frame against its immutable commission/session/Attempt context, preserve bounded history and correction semantics, and fail closed on stale, ambiguous, unbound, or effect-unknown states.

---

## 2. Current capability ledger at architecture freeze

| Capability | Current state | Evidence / boundary |
|---|---|---|
| Codex as bounded Sol technical reasoning surface | `BUILT_NOT_PROVEN` as a full live operating path | #173 mechanically proves identity/authority composition; no new Wake/provider/Slack arming |
| ASD A0/A1 contract + storeless dialogue engine | `BUILT_NOT_PROVEN` / development-unarmed | accepted hermetic core; production A2/A3 remain gated |
| Production Agent Relay Slack app | `NOT_BUILT` / not production-proven | ASD-A2 remains TODO under `WS:CHAIRMAN-CONTROL-ROOM` |
| Generic Slack-to-worker receiver | `DARK_OR_DISCONNECTED` | current Agent OS discovery says no proven canonical receiver; Slack membership/delivery is not Worker claim |
| Executive heterogeneous worker routing | `PARTIAL` | Capacity Fabric H0/P0/CF2-I/HF1/PF1/MH1 gates remain |
| Exact MCP execution-capability policy | `BUILT_NOT_PROVEN` for reviewed profiles | existing `ExecutionCapabilityRegistry` / `McpServerGrant` supports exact server identity, version, enabled tools and schema digest; policy is production-unarmed |
| Worker-aware MCP company-dialogue gateway | `NOT_BUILT` | this design owns the extension |
| Dynamic worker presentation in Slack | `NOT_BUILT` | optional presentation layer; must not become identity authority |

Architecture/docs merge changes only the last two rows to `SPEC_ONLY`. It does not make them built or live.

---

## 3. Canonical ownership — unchanged

| Fact | Canonical owner |
|---|---|
| Job / Attempt / Worker / Event lifecycle, claim, retry, reconciliation | Executive OS |
| Executive seat and effective authority | Executive OS + accepted Chairman/Sol provenance/grant law |
| Organizational workstreams, decisions, discoveries, handoffs | Agent OS |
| Code / PR / CI / merge / implementation evidence | GitHub |
| Provider/account capacity and placement eligibility | existing Provider Control + Model Router + Capacity Fabric contracts |
| Native provider start/resume/result | approved Worker Harness adapter |
| Wake obligation / delivery / ACK / source resolution | Executive Wake Fabric |
| Slack delivery, thread history and visible conversation | Slack / Agent Relay transport |
| Worker dialogue validation and Slack projection | existing Agent Relay service extended by this design |
| Portfolio projection | Linear |

**Slack principal is never Executive Worker identity.**  
**MCP server identity is never Executive Worker identity.**  
**Provider/model/account identity is never Executive authority.**  
**Agent OS never mints runtime Worker identity.**

---

## 4. No-rebuild boundaries

This program MUST NOT create any of the following:

- a second Job/Attempt/Worker/Event lifecycle;
- a Slack task queue or dispatch database;
- a worker-identity registry parallel to Executive OS;
- a mutable Slack inbox/cursor/replay database;
- a per-provider or per-host worker scheduler;
- a new Agent OS runtime router;
- one Slack app or OAuth token per ephemeral worker;
- one MCP gateway per provider;
- one dialogue daemon per worker;
- a new Wake obligation or session registry;
- a generic secret-management service;
- model-authored authority, worker identity, Slack username, channel scope, or grant fields.

The implementation extends existing Executive capability profiles and the existing Agent Relay / ASD package. If either seam proves insufficient, the worker returns to Sol with the falsifier rather than inventing a parallel plane.

---

## 5. Architecture

### 5.1 One real Slack app principal, many logical actors

The production transport target is one least-privilege Mastermind Agent Relay Slack app. The app may project different logical actors in message content and, after a separately reviewed scope expansion, through Slack-supported app username/icon customization.

The logical actor is always clearly app-managed. Presentation names MUST use a reserved Mastermind prefix, for example:

```text
Mastermind · Sol/Codex
Mastermind · Fable
Mastermind · Worker W-7A29
Mastermind · Research W-93C1
```

Presentation MUST NOT impersonate the Chairman, a human Slack member, or a personal ChatGPT/Claude account. Personal ChatGPT1/2/3 and Claude user principals remain communication/fallback endpoints under existing law; they are not reused as generic worker identities.

### 5.2 Baseline presentation before `chat:write.customize`

The first live proof does not depend on custom app impersonation/customization scope. The baseline can render the trusted actor label in the message body while every message is visibly posted by the normal Mastermind Relay app.

Only after baseline Relay production proof may a bounded follow-up request Slack's `chat:write.customize` capability. If used, the exact display name/icon is derived from trusted actor context, never model text. The underlying Slack bot user ID remains unchanged.

Slack's current Agent Sessions APIs may later improve status/title/stop UX, but they are optional product presentation. Agent Sessions MUST NOT become the canonical Mastermind session or lifecycle identity.

### 5.3 One worker-aware dialogue gateway

Codex and later worker harnesses receive a small Mastermind company-dialogue MCP interface, not a generic Slack MCP.

Expected worker tools are conceptually:

```text
mastermind_company.read_thread
mastermind_company.ack
mastermind_company.progress
mastermind_company.blocked
mastermind_company.request_decision
mastermind_company.result
```

Executive/Sol-side tools are conceptually:

```text
mastermind_company.ruling
mastermind_company.continue
mastermind_company.stop
```

No generic `slack.post_message`, arbitrary channel search, channel creation, member lookup, unbounded history read, or caller-selected username tool is part of the worker profile.

### 5.4 Reuse the existing Executive MCP capability authority

`control_plane.executive_agent_capabilities.ExecutionCapabilityRegistry` and `McpServerGrant` already provide the correct reviewed seam for exact MCP server identity, version, transport, enabled tools, approval mode and tool-schema digest. This program extends that existing policy rather than creating another MCP permission registry.

A future reviewed profile may name one exact capability such as `mastermind-company-dialogue-v1` and one exact App Server configuration name. The Job/claim path binds the profile/policy digest under existing law. The worker process must be attested against that reviewed profile before the tool is considered available.

Secret values remain outside the capability JSON and outside Job/Attempt/Event/Agent OS/Slack records.

### 5.5 Gateway authentication is subordinate to the runtime grant

The gateway may use Codex-supported MCP OAuth or bearer-token mechanics only through an accepted secret-owning runtime seam. The secret value must never be model-visible, persisted in a Job payload, included in Slack, or written into the capability policy.

The gateway MUST NOT trust caller-supplied `job_id`, `attempt_id`, `worker_id`, executive seat, workstream, channel, Slack display name, or authority class. A successful transport authentication is necessary but not sufficient: the server must resolve a trusted actor binding established by the existing Executive/runtime launch path.

If implementation archaeology finds no existing secret-owning mechanism capable of binding an MCP session to the exact current Attempt/session without creating a new generic credential service, WP-2 stops at a production-inert contract/profile proof and returns that missing seam to Sol. It must not silently solve the gap with a long-lived shared worker token.

---

## 6. Dialogue identity contract

### 6.1 Preserve ASD v1

`mastermind.agent_dialogue.v1` remains accepted for the current Sol/Fable active-session contract. WP-1 MUST NOT mutate old v1 receipts into a new meaning or make historical Slack messages satisfy Worker identity.

### 6.2 Add a versioned worker-aware envelope in the same package/service

The preferred evolution is `mastermind.agent_dialogue.v2` inside the existing `integrations/slack_agent_dialogue` package and Agent Relay service.

V2 retains the existing bounded message families, immutable commission reference, bounded evidence references, semantic fingerprinting, secret-shaped-value rejection, reply lineage, edit/delete reconciliation and storeless history laws. It replaces the closed v1 `seat_ref` assumption with a typed trusted `actor_ref`.

Conceptual closed actor shapes:

```json
{
  "kind": "executive_surface",
  "seat": "ceo",
  "reasoning_surface": "codex"
}
```

or

```json
{
  "kind": "worker_attempt",
  "job_id": "...",
  "attempt_id": "...",
  "worker_id": "..."
}
```

The exact identifiers and formats must reuse current Executive Runtime ID formats; WP-1 may not invent a second ID namespace merely for Slack.

`reasoning_surface` is communication/execution evidence only. It never widens the executive seat. Provider account, host and native provider thread are not required in the semantic actor identity and should remain runtime evidence unless a concrete proof need demands an allowlisted non-authoritative projection.

### 6.3 Trusted injection, not model authorship

For a worker-origin message, the worker supplies only the bounded semantic body appropriate to the tool call. The gateway injects:

- schema/version;
- message key;
- exact work/commission/session context;
- `actor_ref`;
- reply binding;
- applicability identity;
- created timestamp;
- semantic fingerprint;
- Slack target/thread identity.

The worker cannot select another actor by putting IDs in prose.

### 6.4 Applicable context

V2 must be able to bind conversation to the current immutable work context without requiring every worker to own a PR. `applies_to` therefore needs a typed form that can represent both existing repository/head/PR evidence and a current Executive Job/Attempt scope.

This is a dialogue join only, not new lifecycle state. The authoritative Job/Attempt state continues to come from Executive OS; GitHub remains the authority for PR/head evidence.

---

## 7. Message and authority semantics

Worker-origin message classes remain bounded:

- `ACK` — confirms the already-active commissioned context was received;
- `PROGRESS` — descriptive progress only;
- `BLOCKED` — work cannot safely continue and names the required authority boundary;
- `DECISION_REQUEST` — requests a bounded Sol/Chairman ruling with explicit options/impact;
- `RESULT` — returns the bounded result and evidence references.

Sol-origin message classes remain bounded:

- `RULING` — adjudicates a specific decision request under accepted authority law;
- `CONTINUE` — continues inside the existing scope without widening authority;
- `STOP` — halts the dialogue/work continuation path;
- existing amendment semantics remain available where lawful.

No Slack message automatically creates a Job, retries an Attempt, changes a Worker, merges/deploys code, modifies production, or changes Agent OS state.

---

## 8. End-to-end flows

### 8.1 Codex-Sol active-session proof

```text
accepted bounded Sol technical continuation
  -> current Codex runtime binding
  -> reviewed App Server capability profile includes company-dialogue MCP
  -> Codex calls mastermind_company.ack
  -> gateway resolves trusted executive_surface actor
  -> Agent Relay posts into the exact bound Slack thread
  -> Sol reads visible ACK/progress/decision request
  -> Sol issues bounded ruling through accepted Relay path
  -> Codex continues via Wake/native continuation owner
  -> Codex emits RESULT
```

Slack does not originate or own the Codex continuation. Wake PR3 remains the continuation owner.

### 8.2 Executive Worker proof

```text
Executive Job already exists
  -> Executive OS claims exact Worker for exact Attempt
  -> approved Worker Harness launches with reviewed MCP capability profile
  -> worker calls mastermind_company.progress/result
  -> gateway derives job/attempt/worker actor from trusted runtime binding
  -> Relay posts visible logical Worker identity
  -> result remains canonical in Executive/GitHub/Agent OS according to its owning layer
```

### 8.3 Decision request

```text
worker_attempt
  -> DECISION_REQUEST in bound thread
  -> Slack delivery proves transport only
  -> Sol reviews request + canonical evidence
  -> RULING references exact request
  -> gateway validates scope/authority
  -> worker consumes ruling through its bound dialogue context
```

A Slack ruling does not self-apply architecture or production mutation. Where accepted source law requires a canonical decision record, the canonical reference is recorded in the owning repository/Agent OS before the worker can treat it as authority.

---

## 9. Failure and correction behavior

The gateway fails closed on:

- unknown or expired runtime actor binding;
- Job/Attempt/Worker mismatch;
- actor binding not active for the bound conversation;
- changed commission/session context;
- unreviewed MCP server/tool schema digest;
- missing required capability profile;
- caller-supplied identity or Slack target fields;
- stale or incomplete bounded Slack history;
- message-key fingerprint conflict;
- edited/deleted message without complete creation evidence;
- authorization refusal;
- Slack transport timeout/effect uncertainty;
- unknown Slack send result;
- duplicate semantic key with changed payload;
- secret-shaped content;
- tool call outside the actor's allowed message classes;
- request to read/post outside the bound thread/channel;
- provider/MCP disconnect after an effect may have begun.

For an ambiguous Slack write, use existing ASD effect-unknown semantics and reconcile the same message key/thread/transport before any resend. Never auto-failover to a personal Slack account or a second app.

For an ambiguous provider/runtime effect, Executive/Wake reconciliation remains authoritative; the Slack gateway cannot reassign or retry the underlying work.

---

## 10. Privacy and secret boundaries

The following may never appear in dialogue frames, Slack text, Agent OS records, GitHub receipts, model-visible configuration, or capability policy JSON:

- Slack bot tokens or app-level tokens;
- MCP OAuth access/refresh tokens;
- bearer token values;
- ChatGPT/Codex/Claude cookies or auth files;
- provider account email/PII not already approved for a separate owner;
- private host addresses or credentials;
- raw Keychain/secret-store contents;
- unrestricted native session handles where only a digest/opaque binding is required.

Logs/receipts may expose only allowlisted non-secret identifiers and digests needed to prove the actor/thread/tool binding.

---

## 11. Product presentation

The Slack experience should optimize for company legibility, not for pretending every ephemeral process is a human Slack member.

Recommended visible composition:

```text
Mastermind · Sol/Codex     [APP]
Architecture review complete. One decision is required...

Mastermind · Worker W-7A29 [APP]
PROGRESS — store adapter integrated; production proof remains.

Mastermind · Fable          [APP]
DECISION REQUEST — two lawful sequencing options...
```

Messages should carry compact status plus links/refs to GitHub/Agent OS evidence rather than dumping raw traces. Worker IDs may be shortened for display only; the machine frame carries exact canonical IDs.

The Control Room may later project read-only worker-conversation attention only after its existing ASD/CCR prerequisites are accepted. It does not become a send path or stored inbox.

---

## 12. Dependency and collision law

This program deliberately crosses existing owners and therefore must respect their gates:

- **Wake #174:** owns native Codex/Claude wake/resume. WP work may not edit Wake implementation paths or use Slack delivery as substitute Wake proof.
- **ASD-A2/A3:** owns first production Agent Relay app/thread proof. WP-1/WP-2 may remain production-inert in parallel; WP-3 cannot claim live Slack proof before the accepted Relay production prerequisite exists.
- **CF2/HF1/PF1:** own heterogeneous Worker placement and provider-neutral harness. WP-4 can prove one current eligible Worker when the accepted execution seam exists; WP-5 provider-neutral fan-out waits for HF1/PF1.
- **MH1:** owns authenticated multi-host execution. WP-6 multi-host worker dialogue waits for MH1; the dialogue gateway itself does not create remote execution transport.
- **C1/B2/C2 Personal-Pro:** remain independent CEO ingress/state-write gates. This program does not use MCP/Slack dialogue to bypass them.

If a newer accepted source law changes any of these boundaries before an implementation carrier is released, Sol re-reconciles and amends the plan rather than asking the worker to reconcile authority ad hoc.

---

## 13. Bounded wave architecture

### WP-0 — architecture/source-law freeze

**Mission:** make this identity/transport/no-rebuild architecture durable without arming runtime capability.

Completion is records-only. No production proof is owed.

### WP-1 — worker-aware Agent Relay contract

**Mission:** add deterministic `agent_dialogue.v2` actor/applicability semantics and presentation derivation inside the existing ASD package/service, with v1 compatibility and no network/credential arming.

Required proof includes discriminating tests for identity spoofing, worker/Attempt mismatch, actor laundering through prose, v1 compatibility, message conflict/edit/delete behavior, secret rejection, and zero new persistence.

### WP-2 — custom Mastermind MCP facade + Executive capability profile

**Mission:** expose only the bounded company-dialogue tool surface through one exact MCP server contract and bind it through the existing `ExecutionCapabilityRegistry` / `McpServerGrant` policy seam.

WP-2 remains production-inert unless the existing secret-owning runtime seam can safely establish exact actor binding. No long-lived shared worker credential is permitted as a shortcut.

### WP-3 — one real Codex-Sol -> MCP -> Relay -> Slack conversation

**Gate:** accepted production Agent Relay prerequisite plus exact current Codex runtime/capability preflight.

**Mission:** one harmless bound Codex-Sol conversation emits ACK, PROGRESS, one DECISION_REQUEST, consumes one Sol RULING, continues, then emits RESULT through the real Slack app without Slack originating work or authority.

Baseline proof does not require `chat:write.customize`.

### WP-4 — one real Executive Worker identity projection

**Gate:** a lawful current Worker Harness/Executive Attempt path.

**Mission:** an already-claimed Worker automatically receives the company-dialogue capability and reports ACK -> PROGRESS -> RESULT with exact Job/Attempt/Worker identity injected by trusted runtime context.

### WP-5 — provider-neutral worker proof

**Gate:** HF1 + PF1 acceptance or superseding provider-neutral harness law.

**Mission:** at least two different provider adapters use the same dialogue contract and gateway without provider-specific Slack/MCP lifecycle code.

### WP-6 — multi-host proof

**Gate:** MH1.

**Mission:** workers on separate authenticated execution hosts use the same company-dialogue gateway while credentials remain host/runtime-local and one Executive Runtime remains canonical.

### WP-7 — read-only Control Room projection

**Gate:** existing CCR/ASD product prerequisites plus stable live worker-dialogue receipts.

**Mission:** project worker/executive conversation attention into the Control Room without creating a stored inbox, send path, or lifecycle authority.

---

## 14. Acceptance standard

The long-form program is complete only when all of the following are true:

1. **Truth:** Slack actor labels are mechanically joined to exact Executive/runtime identity; no model/user prose can mint or change identity.
2. **Authority:** Slack/MCP/provider identity cannot create or widen Job/Attempt/Worker/seat/effective grant authority.
3. **Transport:** one real Agent Relay app carries bounded dialogue with reconciliation-safe effect semantics.
4. **Product:** the Chairman/Sol can distinguish Sol/Fable/workers, follow progress and answer a real decision request without copy/paste.
5. **Execution:** at least one real Executive Worker and one Codex-Sol continuation have proven the path.
6. **Provider neutrality:** after HF1/PF1, a non-Codex worker uses the same contract without a provider-specific relay/gateway.
7. **Multi-host:** after MH1, a worker on another physical host uses the same canonical identity/transport path.
8. **Learning:** operational metrics can describe delivery latency, decision-request latency, malformed/refused dialogue, and transport reliability without creating market/trading authority.
9. **No rebuild:** zero new lifecycle DB, Slack queue, worker registry, Wake registry, replay ledger, generic secret service, or per-worker Slack app.

Green CI or a Slack message alone is not final acceptance.

---

## 15. Explicitly rejected alternatives

### One Slack user/app per ephemeral worker

Rejected. It creates credential/app sprawl, weakens identity reconciliation, and falsely suggests Slack membership is Worker identity.

### Reuse ChatGPT1/2/3 or Claude personal principals as generic workers

Rejected. Those are communication identities. The same paid subscriptions may supply worker capacity, but Executive OS must claim the concrete Worker/realm.

### Generic Slack MCP exposed to workers

Rejected. Workers receive only company-dialogue tools bound to one context; arbitrary Slack access is unnecessary authority.

### Slack-origin worker dispatch

Rejected. Slack cannot become a second task queue. Jobs originate through accepted Executive admission/routing paths.

### New Worker Presence database

Rejected. Executive OS already owns Worker/Attempt truth; Slack presence is a derived projection.

### Per-provider dialogue gateways

Rejected. One Agent Relay/gateway contract serves all approved providers.

---

## 16. Architecture-freeze rulings

The following are binding for implementation unless a later explicit Sol/Chairman source-law amendment supersedes them:

1. One Mastermind Slack app principal, not one app/token per worker.
2. Logical Slack actor presentation is a projection of trusted runtime identity, never its source.
3. Executive OS remains the sole runtime Worker identity/lifecycle owner.
4. Agent OS remains organizational memory and does not mint runtime workers.
5. Existing Agent Relay/ASD is extended; no second dialogue plane is created.
6. Existing `ExecutionCapabilityRegistry` / `McpServerGrant` is extended; no second MCP capability registry is created.
7. Workers receive bounded company-dialogue MCP tools, not generic Slack tools.
8. Slack never originates a Job, Worker claim, retry, provider failover, Wake obligation, or production mutation.
9. ASD v1 remains valid; worker-awareness lands as a versioned compatible evolution.
10. Production-inert WP-1/WP-2 may proceed independently of Wake/ASD live gates only while their changed paths remain disjoint.
11. WP-3 waits for the real Agent Relay production prerequisite and initially proves normal app presentation before optional custom username/avatar scope.
12. Any lack of a safe exact Attempt/session authentication seam is a return-to-Sol falsifier, not permission to mint a shared long-lived worker token.

---

## 17. Exact next action after written-spec approval

After the Chairman reviews this checked-in spec, Sol creates separate implementation plans for WP-1 and WP-2, re-pins current protected Mastermind and relevant open carriers, and releases them as disjoint bounded implementation waves. Wake #174, ASD-A2/A3 production work, CF2/HF1/PF1, and Personal-Pro C1/B2/C2 remain independently owned and may continue in parallel only where current paths/authority are disjoint.
