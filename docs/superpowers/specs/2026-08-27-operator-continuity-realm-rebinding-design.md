# Mastermind Operator Continuity & Realm Rebinding

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** **CHAIRMAN APPROVED / ARCHITECTURE FREEZE. RECORDS ONLY.** The Chairman approved the architecture in the governing Sol conversation on 2026-08-27 and directed Sol to continue end to end through planning, integration, proof and closeout. This document creates no Executive Job, Attempt, Worker, provider login, Slack app installation, Wake delivery, remote host connection, account failover, or production authority by itself.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Protected Mastermind / Skillpack basis:** `af43f356f4f7f34cb3514d1d1099b50444af8487`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1.  
**Observed Macro main during freeze:** `47439bf4180846af6eb4336a107c1935806399c2`.  
**Existing owners extended, never replaced:** Executive OS; Operator Harness; `WS:EXECUTIVE-CAPACITY-FABRIC`; Shared AI Provider Control; Model Router; Executive Wake Fabric; `WS:CHAIRMAN-CONTROL-ROOM` / Worker Presence & Dialogue; Agent OS; GitHub.

---

## 1. Outcome

Mastermind-X must be able to treat the company's paid Claude and Codex subscriptions as governed execution capacity without binding organizational continuity to one provider account, one native app, one Mac, one terminal process, or one provider-native conversation.

A sustained Fable/COO responsibility must survive exhaustion of the current Claude account. A sustained Codex-Sol technical responsibility must likewise survive replacement of the current Codex runtime. The Chairman and Sol should continue interacting with the same logical company entity and Slack conversation while Executive OS safely terminates or reconciles the prior Attempt, selects a lawful replacement realm, creates a fresh provider-native session when the account/host changes, hydrates exact continuation context, and resumes work.

The architecture preserves native Claude/Codex applications as premium **cockpits** while moving machine-operable execution underneath programmatic provider surfaces:

- Claude Code CLI / supported Agent SDK/session surfaces for Claude execution;
- Codex App Server for sustained Codex sessions;
- `codex exec` remains valid for sealed one-shot Codex workers;
- native desktop applications remain useful for human inspection/manual intervention but are not required for autonomous continuity;
- one canonical Executive Runtime remains the lifecycle authority across all hosts.

### 1.1 Chairman job

Give Sol/Fable a company outcome once. Do not manually watch quota, choose Claude1 versus Claude5, move prompts between apps, remember which Mac hosts which operator, or re-create context after one subscription is exhausted.

### 1.2 Sol job

Retain company/product/architecture authority and final acceptance while delegating runtime continuity to the existing Executive control plane. Sol must be able to see that `Fable` moved from one realm to another without treating the new provider account as a new COO.

### 1.3 Fable/operator job

Hold sustained responsibility across multiple Executive Attempts and provider-native sessions. A provider/account/host change may replace the current runtime embodiment but must not silently change mission, authority, accepted decisions, workstream, Slack conversation, or GitHub work product.

### 1.4 Machine job

Separate logical responsibility from physical execution; detect or consume provider-capacity evidence; reconcile the current Attempt; select only an already-lawful replacement realm; build a deterministic continuation capsule from canonical sources; launch and attest a new provider-native session; bind the new Attempt; project the new runtime to Wake/Slack/Control Room; and refuse cross-realm failover whenever the prior modifying effect is uncertain.

---

## 2. Canonical ownership remains unchanged

| Fact | Canonical owner |
|---|---|
| Job / Attempt / Worker / Event lifecycle, terminal state, retry/requeue, effect reconciliation | Executive OS |
| Session epoch / process generation / provider session / turn operation evidence inside an Attempt | existing Operator Harness + Executive Runtime |
| Provider/account presence, health, cooling, quota evidence | Shared AI Provider Control in Macro |
| Quality / execution-shape suitability | existing Model Router |
| Final placement among already-eligible Worker realms | Executive OS + Capacity Fabric claim evidence |
| Native Claude/Codex start/resume/turn/result mechanics | approved provider adapter behind the existing Worker/Operator Harness |
| Wake obligation / delivery / ACK / source resolution | existing Executive Wake Fabric |
| Slack conversation, visible dialogue and transport evidence | existing Agent Relay / Slack transport |
| Organizational workstreams, decisions, discoveries, handoffs | Agent OS |
| Code, branch, PR, CI, merge, implementation evidence | GitHub |
| Chairman operating view / navigation | Chairman Control Room |
| Optional host/device actuator or conversational shell | subordinate integration only; never a canonical owner |

OpenClaw, a Claude background supervisor, Codex App Server, a native desktop app, tmux, a Slack account or a physical Mac may provide execution/session evidence. None becomes a second lifecycle, scheduler, identity registry, retry ledger or company memory plane.

---

## 3. Capability ledger at freeze

| Capability | State | Freeze finding |
|---|---|---|
| Executive Job/Attempt/Worker lifecycle | `BUILT_NOT_PROVEN` for the complete autonomous outcome | Runtime already supports terminal `RATE_LIMITED`/`FAILED`/`LOST`, requeue, new claim, exact Attempt lineage and immutable terminal Attempts. |
| Rich Operator Harness session/process/turn state | `BUILT_NOT_PROVEN` / production-unarmed | Existing session epochs, process generations, provider session identity, start/resume/turn intents, effect-unknown and reconciliation are the canonical foundation. |
| Provider-neutral sealed-worker adapter | `PARTIAL` | `WorkerExecutionAdapter` exists but still carries Codex-owned types; HF1 remains the accepted generalization owner. |
| Capacity projection | `BUILT_NOT_PROVEN` / predecessor-gated | Macro `mastermind.provider_capacity.v1` already enumerates Claude subscription slots and Codex account slots, but CF2-I placement is not yet released. |
| Real multi-account placement | `NOT_BUILT` | CF2-H0 -> P0 -> CF2-I remains the gate. |
| First real non-Codex Executive provider | `NOT_BUILT` | PF1 names Claude as the preferred first vertical after RF1/HF1. |
| Claude same-session Wake | `NOT_BUILT` / host-capability gated | Existing Wake PR #174 is the sole current transport carrier; it may prove or truthfully refuse exact Claude transport. |
| Codex native Wake | `BUILT_NOT_PROVEN` candidate on open #174 | Still under review/production proof; not an ownership seam for placement. |
| Worker-aware Slack dialogue | `BUILT_NOT_PROVEN` candidate on open #178 | Storeless dialogue V2 only; no lifecycle or capacity ownership. |
| Cross-account Fable continuity | `NOT_BUILT` | This source law freezes how existing owners compose to supply it. |
| Authenticated multi-host worker transport | `NOT_BUILT` | Existing MH1 remains the owner. |
| Executive Steward continuity product | `SPEC_ONLY` | Steward consumes canonical projections; it must not become scheduler/routing authority. |
| Native-app GUI failover as canonical mechanism | `REJECTED_BY_DESIGN` | Apps are cockpits; supported programmatic harnesses are the autonomous substrate. |

---

## 4. Identity model

Never collapse these layers:

```text
CHAIRMAN / EXECUTIVE AUTHORITY
  -> executive seat: chairman | ceo | coo
  -> accepted commission / root Job

LOGICAL RESPONSIBILITY
  -> root_job_id
  -> target_seat
  -> accepted logical session_alias / company presentation
  -> operation_key / immutable commission context

EXECUTION
  -> Job
  -> Attempt
  -> Worker
  -> quota class / placement snapshot
  -> provider realm/account
  -> host_ref
  -> harness kind
  -> session epoch
  -> process generation
  -> provider_session_id / native thread

TRANSPORT / PRESENTATION
  -> Wake RuntimeBinding projection
  -> Slack channel/thread
  -> Mastermind logical actor label
```

A provider account is replaceable capacity. A native provider session is runtime evidence. Neither is organizational identity.

### 4.1 Stable across cross-realm rollover

The following remain the same unless separately amended through their canonical owner:

- Chairman/Sol outcome and accepted commission;
- root Job / parent responsibility;
- target executive seat;
- operation key;
- workstream and accepted architecture/decisions;
- branch/PR/work-product lineage when safe continuation retains it;
- Slack dialogue parent/thread identity;
- human-visible company presentation such as `Mastermind · Fable`.

### 4.2 Changes across cross-realm rollover

At minimum:

- old Attempt terminates;
- a new Attempt is created after lawful requeue;
- Worker may change;
- provider account/realm changes;
- host may change;
- provider-native session/thread changes;
- runtime binding changes;
- execution principal / placement evidence binds to the new Attempt.

---

## 5. Attempt-boundary law

The existing Operator Harness `ATTEMPT_BOUNDARY_MATRIX` remains controlling.

### 5.1 Same-Attempt operations

A provider-native process may be replaced inside the same Attempt only when the exact current execution realm remains stable and the existing Operator Harness recovery law proves it safe. Examples include safe process crash recovery, graceful process replacement, same-realm context rotation or same-session resurrection.

### 5.2 New-Attempt operations

Any of the following requires a **new Attempt**:

- Worker/placement change;
- provider change;
- account/auth-home change;
- requested model change;
- harness-kind or harness-binary change;
- host change when it changes the accepted execution principal/placement;
- workspace/base/authority/sandbox/network policy change.

Therefore `Claude realm 05 -> Claude realm 02` is never modeled as the same provider-native session or same Attempt.

### 5.3 Effect-unknown law

If the prior modifying effect may have occurred but no authoritative result exists:

```text
EFFECT_UNKNOWN
-> retain current Attempt/carrier identity
-> reconcile that exact operation
-> do not select another provider/account/host
```

Only after the prior Attempt is canonically safe to terminalize/requeue may a new Attempt claim another realm.

---

## 6. Two distinct continuity mechanisms

### 6.1 Same-realm resurrection

Purpose: restart/resume the exact current provider session without changing the placement.

Examples:

- Codex App Server thread reconnect/resume;
- Claude Code exact-session resume when supported and proven;
- Claude background-session supervisor respawn on the same authenticated realm when the installed-version proof satisfies exact identity and writer-safety requirements.

Owner:

```text
Operator Harness same-Attempt recovery
+ provider adapter
+ Wake delivery/attention
```

Wake may address the exact current binding. Wake never chooses another realm.

### 6.2 Cross-realm rollover

Purpose: continue the same Job after the current realm becomes unusable or intentionally drained.

Canonical sequence:

```text
current provider failure / planned drain
-> reconcile current modifying effect
-> terminalize old Attempt truthfully
-> preserve accepted checkpoint/result evidence
-> requeue the same Job under existing attempt-limit law
-> Model Router filters lawful quality/execution class
-> Capacity Fabric ranks eligible fresh capacity
-> Executive OS claims a new Worker/realm
-> build deterministic continuation capsule
-> start fresh provider-native session
-> attest new execution principal / placement
-> target session ACKs the exact continuation capsule
-> new RuntimeBinding projection becomes current
-> same company Slack thread projects rebound
-> work continues
```

Cross-realm continuity is not a Wake retry and not a Slack handoff.

---

## 7. Continuation capsule

The provider-native new session must not depend on the previous Claude/Codex conversation being exportable, and must not depend on this ChatGPT conversation.

Create a derived versioned launch artifact:

```text
mastermind.operator_continuation.v1
```

### 7.1 Required closed fields

The implementation plan must preserve at minimum:

```text
schema
capsule_id
root_job_id
job_id
source_attempt_id
target_attempt_id
operation_key
target_seat
session_alias
effective_grant_digest
source_authority_refs[]
agentos_refs[]
github_state
prior_attempt_receipt
checkpoint
slack_dialogue_ref
accepted_ruling_refs[]
next_action
known_unknowns[]
generated_at
source_revisions
```

`capsule_id` is a digest over the canonical closed representation excluding no semantic field except the digest field itself.

### 7.2 Source ownership

The capsule is generated from existing canonical owners:

- Executive OS for Job/Attempt/Worker/authority/checkpoint state;
- Agent OS for durable decisions/discoveries/handoff references;
- GitHub for repository/branch/PR/head truth;
- bounded Agent Relay/Slack history only for dialogue/ruling transport evidence that is already applicable to the commission.

### 7.3 No new memory store

The continuation capsule is a launch artifact / receipt. It is not a mutable memory database, replay cursor, inbox, queue, planner state or second Agent OS.

A human-readable/model-generated summary may accompany the deterministic packet, but it is descriptive only and has zero authority to override exact fields or source refs.

### 7.4 Target ACK

A new provider-native session must ACK at least:

```text
target_attempt_id
capsule_id
observed provider_session_id
```

ACK proves the newly bound runtime consumed the continuation packet. It is not proof the work is complete.

---

## 8. RuntimeBinding projection

Wake currently models `RuntimeBinding` as runtime-only and deliberately defers persistence. This program must not solve continuity by creating a new runtime-binding table.

The current binding should be derived from accepted Executive/Operator Harness state. Conceptually:

```text
session_alias        <- accepted logical target for the root/seat
binding_id           <- opaque stable identity for the current Executive session epoch / binding life
binding_generation   <- current accepted process-generation / binding generation
native_handle        <- current provider_session_id / native thread handle
account_label        <- placement/account label from accepted claim/principal evidence
reasoning_surface    <- provider adapter class such as claude | codex
```

The exact deterministic binding-id derivation/persistence seam must reuse existing Executive events/session-epoch identity and remain ABA-safe. If current runtime structures cannot satisfy this without a new table, implementation returns to Sol rather than creating one.

Wake, Control Room, Agent Relay and Steward consume this projection; they do not own it.

---

## 9. Claude runtime architecture

### 9.1 Autonomous substrate

Use provider-supported machine surfaces:

- Claude Code CLI session controls;
- supported Claude Agent SDK/session primitives where useful;
- provider-native structured output/streaming;
- exact permission/MCP/tool policy through the accepted Executive capability boundary.

Native Claude desktop/macOS application remains a cockpit/manual surface. GUI automation is not the foundation for production failover.

### 9.2 Same-realm capability detection

The Claude adapter may use installed-version capability detection for exact session discovery, resurrection and bounded nudge ingress. Current official Claude Code documentation includes explicit session resume, Agent View/background session controls and one per-user supervisor. Research-preview capabilities may be used only when action-time host proof validates their contract; absence does not authorize a custom replacement session manager.

### 9.3 Realm isolation is a hard predecessor

Five Claude subscriptions are only five usable realms when the installed hosts prove account/auth isolation.

On macOS, do not assume multiple `CLAUDE_CONFIG_DIR` directories automatically isolate Keychain-backed credentials. A current upstream issue reports credential collision across multiple config directories on macOS. The program therefore requires an explicit realm-isolation falsifier before production routing.

Accepted mechanisms may include:

- separate physical hosts;
- separate OS principals / Keychains;
- separately provisioned long-lived subscription tokens used only by a host-local secret-owning process;
- another provider-supported mechanism proven to isolate simultaneous accounts.

Rejected mechanisms include:

- a shared global login presented as multiple realms;
- token swapping in a model-visible shell;
- copying credentials between hosts;
- account selection by Slack username;
- assuming config-directory names establish authentication identity.

### 9.4 Realm proof

Before a realm is routable, prove secret-free:

```text
realm identity -> expected provider/account observation
realm-specific auth state
no cross-account refresh/logout collision under concurrency
quota/cooling evidence maps to the same realm
restart does not silently change realm
host_ref and execution principal remain consistent
```

Raw account PII, cookies, auth files and token values never enter Executive/Agent OS/GitHub/Slack records.

---

## 10. Codex runtime architecture

Use two distinct Codex modes:

```text
sustained Codex-Sol / operator responsibility
  -> Codex App Server

bounded sealed worker
  -> existing codex exec --json adapter
```

App Server's thread lifecycle is provider-native session state, not company lifecycle. Thread IDs remain runtime evidence under the existing Operator Harness / RuntimeBinding boundary.

The native Codex app remains a cockpit/client. Autonomous Mastermind continuity must not require GUI automation between multiple app windows.

---

## 11. Slack continuity

The Worker Presence architecture remains controlling.

Human-visible identity should remain the logical company actor:

```text
Mastermind · Fable
Mastermind · Codex-Sol
Mastermind · Worker W-...
```

Provider accounts such as `Claude5` are transitional/manual communication identities, not the eventual routing target.

The same Slack parent/thread stays bound to the immutable commission/session context across new Attempts. On successful rollover, Agent Relay may project a non-authoritative system event derived from canonical runtime truth, for example:

```text
Fable runtime rebound
old Attempt: ATT-...
new Attempt: ATT-...
previous realm: claude-pro-05
current realm: claude-pro-02
continuation capsule: <digest>
state: ACKNOWLEDGED / RUNNING
```

The message does not cause the rollover. Slack delivery remains transport evidence only.

A Slack send timeout/effect-unknown uses existing Agent Relay reconciliation and may never cause provider/account failover.

---

## 12. Executive Steward

The Executive Steward is a product/operational-intelligence layer over existing canonical systems.

It may:

- show the current logical responsibility and runtime embodiment;
- surface capacity risk, draining, blocked reconciliation and replacement readiness;
- identify the exact canonical blocker preventing continuation;
- raise material Sol/Chairman attention;
- navigate to the relevant Slack thread, PR, workstream or runtime evidence;
- invoke only separately approved bounded Mastermind controls.

It may not:

- create or own Job/Attempt/Worker lifecycle;
- choose provider/account capacity itself;
- reclassify `EFFECT_UNKNOWN`;
- retry a modifying operation;
- invent a continuation packet from chat memory;
- treat an OpenClaw/Slack/native-app session as company identity.

A future Steward UI may show:

```text
Fable / Market Ontology
status: RUNNING
attempt: ATT-...
runtime: claude-pro-05 @ host-ref-A
capacity: low

then later

runtime: claude-pro-02 @ host-ref-B
continuity: ACKNOWLEDGED
```

---

## 13. OpenClaw boundary

OpenClaw is optional and subordinate.

Permitted future uses include:

- Executive Steward conversational shell;
- read-only Claude/Codex session discovery;
- host/device availability observation;
- one bounded, authenticated host-local actuator behind a Mastermind-approved adapter;
- optional user navigation/status convenience.

OpenClaw must not become:

- Job/Attempt/Worker lifecycle authority;
- provider/account capacity owner;
- provider-selection/failover policy;
- canonical Slack commission/thread owner;
- canonical transcript or continuation-memory owner;
- retry/effect-unknown authority;
- another scheduler or remote queue.

If OpenClaw is removed, canonical Executive continuity must remain recoverable from Mastermind's existing authorities.

---

## 14. Multi-host architecture

Keep one canonical Executive Runtime on the control host. Additional machines are worker hosts.

```text
                 CANONICAL EXECUTIVE OS
                      control host
                          |
                authenticated MH1 transport
           +--------------+--------------+
           |              |              |
           v              v              v
        M1 host         M2 host         PC host
      host broker      host broker      host broker
      local creds      local creds      local creds
      Claude/Codex     Claude/Codex     Codex/local
```

Provider credentials remain local to the host/realm. Remote placement carries an authorized Attempt to a host-local broker; it does not copy provider credentials to the control host.

A second machine adds local execution capacity, account isolation and parallel worktree/test/browser resources. It does not increase Anthropic/OpenAI server-side model inference CPU.

Remote timeout/disconnect after a modifying operation begins is `EFFECT_UNKNOWN`; reconcile the same Attempt/host/operation before any cross-host replacement.

---

## 15. Failure-state matrix

| Condition | Required behavior |
|---|---|
| Realm known exhausted before claim | Exclude it from lawful candidates; no Attempt starts there. |
| Realm capacity unknown/stale | Never treat as unlimited/free. Use accepted Capacity Fabric null/freshness semantics. |
| 429/quota after a non-modifying turn with exact terminal observation | Terminalize truthfully, preserve checkpoint, requeue if attempt law permits. |
| 429/transport loss after modifying effect may have occurred | `EFFECT_UNKNOWN`; no cross-realm rollover until reconciled. |
| Provider-native session process died but same realm/session is proven recoverable | Operator Harness same-Attempt recovery may resume it. |
| Provider/session identity cannot be proven | Refuse; do not start a fresh session while claiming same-session continuation. |
| Multiple candidate Claude sessions match | Refuse as ambiguous. |
| Target realm auth identity differs from placement evidence | Refuse and mark/degrade that realm through its existing owners. |
| Continuation capsule source revision changed materially before launch | Refuse/rebuild against current canonical truth. |
| New session ACK names wrong capsule or Attempt | Refuse work admission. |
| Slack rebound message fails ambiguously | Reconcile Slack message only; runtime continuity remains authoritative elsewhere. |
| OpenClaw node unavailable | Degrade optional actuator/shell; never lose canonical lifecycle/continuity truth. |
| Remote host disconnect ambiguous | Same-host/Attempt reconciliation first; no automatic host failover. |

---

## 16. No-rebuild boundaries

This program MUST NOT create:

- a new operator/session database;
- another Job/Attempt/Worker/Event lifecycle;
- a provider-specific broker/queue per vendor;
- a Slack task queue or persistent worker inbox;
- an OpenClaw-owned Mastermind session/task registry;
- one retry/failover ledger per provider;
- a new memory/RAG store merely to carry continuation;
- a second capacity router;
- a second Wake/session identity plane;
- a credential synchronization service between hosts;
- GUI/RPA as the required production path for Claude/Codex continuity.

If an existing seam proves insufficient, the wave returns to Sol with the exact falsifier.

---

## 17. Ordered implementation program

The architecture is one outcome but implementation is split into independently reviewable capabilities.

### OCR-0 — records/source-law freeze

This document plus Chairman approval and detailed implementation plans. Records only.

### OCR-1 — Claude realm-isolation falsifier

Prove how the real five Claude subscriptions can operate concurrently as independent realms on the available host topology without exposing secrets or creating credential synchronization.

No Executive routing or production provider call beyond the bounded host/auth falsifier may be armed by this wave.

### OCR-2 — Capacity/Router/Harness predecessors

Respect the existing `WS:EXECUTIVE-CAPACITY-FABRIC` order:

```text
CF2-H0
-> independent CF2-P0
-> CF2-I
-> RF1
-> HF1
-> PF1 Claude vertical
```

Do not reopen CF1/CF2-F or start a replacement Capacity Fabric.

### OCR-3 — deterministic continuation capsule + derived RuntimeBinding

Implement the provider-neutral continuation artifact and runtime binding projection without new lifecycle storage. This may proceed only on paths not owned by active Wake #174 / Worker Presence #178; any needed collision waits for those carriers to settle.

### OCR-4 — one-realm Claude operator proof

Through PF1/HF1, prove one real bounded Executive child Job using the provider-neutral Operator Harness contract and one exact Claude realm.

### OCR-5 — local cross-account rollover

Prove a safe `claude-pro-A -> claude-pro-B` rollover on the same Job through two Attempts and a fresh provider session, including continuation ACK and negative `EFFECT_UNKNOWN` proof.

### OCR-6 — Slack + Steward continuity projection

After Worker Presence/Agent Relay production predecessors, keep the same Slack thread/logical actor across Attempt replacement and expose read-only Control Room/Steward runtime continuity status.

### OCR-7 — multi-host continuation

After MH1 and local rollover acceptance, prove one authenticated host-A -> host-B rollover with local-only credentials and exact effect reconciliation.

### OCR-8 — full pool acceptance

Arm the reviewed Claude/Codex pool only after the complete real canary and adverse canaries pass.

---

## 18. Production acceptance

The program is not complete because adapters compile or CI is green.

Required positive production canary:

```text
one Sol commission
-> one Fable logical responsibility / root Job
-> first Claude realm claimed
-> real work + same Slack conversation
-> first realm intentionally drains or reaches accepted capacity boundary
-> old Attempt reconciled and terminal
-> same Job requeued
-> second realm claimed
-> fresh Claude session starts
-> exact continuation capsule ACK
-> same logical Slack actor/thread projects rebound
-> real work continues
-> material result returns
-> GitHub + Agent OS closeout
-> Control Room/Steward shows accepted terminal state
```

Required adverse canary:

```text
modifying provider turn loses definitive outcome
-> EFFECT_UNKNOWN
-> zero cross-provider/account/host failover
-> same operation reconciled
```

Additional acceptance requires:

- exact account/realm isolation proof for every routable Claude subscription;
- no credential values in model/GitHub/Slack/Agent OS/Executive receipts;
- no duplicate lifecycle/session/capacity/retry/memory plane;
- cross-host proof before any second physical host is generally routable;
- real Slack/Control Room proof at the final product layer when owed.

---

## 19. Primary-source research basis

Architecture research reviewed on 2026-08-27 included:

- Claude Code CLI/session documentation: `https://code.claude.com/docs/en/cli-usage`, `https://code.claude.com/docs/en/sessions`;
- Claude Code Agent View/background session supervisor: `https://code.claude.com/docs/en/agent-view`;
- Claude authentication/subscription token guidance: `https://code.claude.com/docs/en/authentication`;
- Claude subscription + Agent SDK usage: Anthropic support article `Use the Claude Agent SDK with your Claude plan`;
- Claude statusline usage payload: `https://code.claude.com/docs/en/statusline`;
- upstream macOS multi-config Keychain collision report: `anthropics/claude-code#70697` (evidence to falsify on installed hosts; not accepted as universal fact without host proof);
- OpenAI Codex harness/App Server architecture: `https://openai.com/index/unlocking-the-codex-harness/`;
- OpenAI Codex orchestration / Symphony discussion: `https://openai.com/index/open-source-codex-orchestration-symphony/`;
- OpenClaw ACP/session/node documentation for optional subordinate integration.

Primary-source documentation guides provider mechanics; Mastermind's accepted repository source law remains the authority for company lifecycle/ownership.

---

## 20. Supersession / compatibility

This design **extends** and narrows ambiguity in `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`. It does not replace that document.

It specifically freezes:

1. native apps as cockpits rather than autonomous failover authority;
2. same-realm resurrection versus cross-realm rollover as distinct mechanisms;
3. provider/account/host change as a new-Attempt boundary;
4. deterministic continuation capsule instead of conversation transplantation;
5. RuntimeBinding as an Executive-derived projection, not a new database;
6. the five Claude subscriptions as routable only after real account-isolation proof;
7. OpenClaw as optional/subordinate rather than lifecycle/routing owner;
8. Slack logical actor/thread continuity across runtime replacement;
9. Steward as read/control product over canonical owners, not a scheduler.

Wake #174, Worker Presence #178 and current Capacity Fabric waves retain their frozen scopes. This design may not be used to widen those existing carriers retroactively.
