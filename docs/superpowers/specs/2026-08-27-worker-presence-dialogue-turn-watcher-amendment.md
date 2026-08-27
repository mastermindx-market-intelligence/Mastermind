# Mastermind Worker Presence & Dialogue Gateway — Stateless Turn-Watcher Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** CHAIRMAN-APPROVED DESIGN AMENDMENT / WRITTEN-SPEC REVIEW PENDING / RECORDS ONLY. This document creates no Executive Job, Attempt, Worker, Wake delivery, Slack app installation, provider process, runtime service, watcher daemon, scheduler, queue, cursor database, session registry, credential, or production authority by itself.  
**Parent operation key:** `worker-presence-dialogue-wp0-20260827-sol-001`  
**Carrier:** existing branch `sol/worker-presence-dialogue-wp0-20260827`; no second WP-0 carrier.  
**Parent spec:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-gateway-design.md` at parent head `e6c35378845ee526f68843b17258c9115db4ef2a`.  
**Protected Mastermind / Skillpack basis:** `8affa1c0403f4400825371bea0257f360a4814f2`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1.  
**Chairman-approved amendment outcome:** after one Sol↔Claude/Fable commission is bound to one Slack thread, neither side should require Chairman intervention merely to notice the other side returned. The thread should deterministically trigger the correct executive/session continuation, while Slack remains transport rather than lifecycle authority.

---

## 0. Supersession and precedence

This amendment extends the parent WP-0 architecture; it does not replace it.

The parent spec remains controlling for worker identity, Agent Relay, company-dialogue MCP, Slack presentation, Executive capability profiles, privacy, provider neutrality, multi-host evolution and no-rebuild boundaries.

This amendment has higher precedence only for the following parent-spec topics:

1. whether an already-bound, already-commissioned dialogue turn may become a Wake source;
2. how Sol↔COO turn ownership is derived;
3. how a sleeping exact reasoning surface is resumed after the other side posts a valid turn;
4. how the first commission message can trigger the already-bound COO session without becoming generic Slack dispatch;
5. how restart/reconnect recovers pending dialogue turns without a watcher/cursor database;
6. the bounded implementation-wave sequence required to prove the zero-manual-wake loop.

The parent ruling “Slack never originates a Wake obligation” is narrowed to:

> **Raw Slack delivery, arbitrary Slack prose, channel membership and caller-selected session claims never originate Wake. A fully validated, commission-bound `mastermind.agent_dialogue` frame may deterministically produce an `AgentDialogueAttention` source fact. Executive Wake Fabric may then mint one route-independent Wake obligation from that source fact. Slack still does not originate a Job, Worker claim, authority grant, retry, provider failover or production mutation.**

All other parent architecture-freeze rulings remain unchanged.

---

## 1. Outcome and acceptance experience

The capability exists to remove one specific Chairman burden:

```text
Sol commissions an already-selected Fable/Claude COO session
        -> one bound Slack thread
        -> COO ACKs, reads the full thread and works
        -> COO posts DECISION_REQUEST / BLOCKED / RESULT
        -> Sol is automatically brought back to that exact bounded responsibility
        -> Sol reviews canonical GitHub / Agent OS / Executive evidence
        -> Sol posts RULING / CONTINUE / STOP
        -> the same bound COO reasoning surface is automatically resumed
        -> COO reads the full thread, continues or stops, and returns again
        -> repeat until terminal
```

The acceptance canary is intentionally strict:

```text
Chris performs the initial authorization and then touches nothing.

Sol -> Claude/Fable -> Sol -> same Claude/Fable -> Sol

one operation key
one Slack thread
one canonical commission
zero duplicate Jobs
zero duplicate provider sessions
zero duplicate Wake obligations for the same turn
zero watcher/cursor/inbox databases
zero manual wake
```

A green unit test, Slack message, successful provider delivery or GitHub PR alone does not satisfy this outcome.

---

## 2. Canonical ownership — unchanged

| Fact | Canonical owner |
|---|---|
| Job / Attempt / Worker / Event lifecycle | Executive OS |
| Executive attention projected from runtime/Agent OS | existing Executive Inbox / accepted owners |
| Organizational commission/workstream/decision/handoff | Agent OS + declared repository source law |
| Code / PR / CI / implementation evidence | GitHub |
| Dialogue frame validation, thread history and Slack transport | existing Agent Relay / ASD package |
| **Dialogue turn classification** | new deterministic, storeless function inside existing Agent Relay / ASD package |
| Wake obligation / routing / delivery / acknowledgement / source resolution | Executive Wake Fabric |
| Logical session target / seat / reasoning surface / transport policy | existing `SessionTargetRegistry` |
| Rotating native provider destination | existing runtime-only `RuntimeBinding` |
| Provider-native same-session resume | approved Wake/Worker Harness adapter |

No watcher component may own work status, completion, retries, provider selection, authority, current worker identity or durable session liveness.

---

## 3. No new watcher control plane

The user-visible behavior is “this handoff has a watcher.” The implementation is **not** one process/task/database per handoff.

There is one existing Agent Relay service. It gains one bounded dialogue-observer loop and one pure turn-classifier. At runtime it may hold an ephemeral in-memory set of currently eligible thread locators for efficiency, but that set is never authoritative and is never persisted.

Forbidden implementations include:

- one cron/automation per Slack handoff as the canonical system;
- one daemon per COO/worker/session;
- a watcher table, pending-turn table, last-seen cursor table or inbox database;
- a second Wake registry;
- a session-alias registry parallel to `SessionTargetRegistry`;
- a provider thread/session database;
- a Slack-owned work queue;
- a generic GitHub/Slack notification router that implicitly creates work;
- blind retry/failover when a Wake/provider/Slack effect is unknown.

Restart must lose only caches, not semantic truth.

---

## 4. Commission and thread admission

The watcher applies only to one already-authorized operation. It is not generic `#agent-dispatch` pickup.

Before the first actionable turn, the exact thread must validate all of:

1. one eligible top-level parent in the reviewed Slack channel;
2. exact stable `operation_key`;
3. exact immutable `commission_ref` (`repository`, `commit`, `path`, `content_sha256`) or an equivalent already-accepted immutable commission identity;
4. exact `work_ref` / workstream identity where applicable;
5. accountable target seat(s);
6. an already-lawful session-routing basis resolvable by existing Wake policy:
   - canonical `root_job_id` binding when one exists;
   - otherwise reviewed workstream→seat binding;
   - otherwise only the existing seat default when the operation law explicitly permits that fallback;
7. exact allowed Slack sender/app identities and dialogue schema version;
8. complete bounded thread history sufficient to prove there is no conflicting parent or semantic fork.

A Slack message may contain a human-readable session label, but `SessionTargetRegistry.resolve(... claimed_session_alias=...)` already ignores caller-claimed aliases. This amendment preserves that law. The watcher never routes from free-form Slack text.

If the user expects a particular sister Sol/COO session and the existing root/workstream/seat routing law cannot resolve it uniquely, the result is `DIALOGUE_WAKE_TARGET_UNBOUND`; the system does not guess, use the newest browser tab, or create a new session.

Native handles, account credentials and provider thread/session IDs remain outside Slack and Git.

---

## 5. Initial dispatch handshake

The first commission message must be self-contained enough that the target session can safely enter the loop without depending on hidden comments or prior chat memory.

For a Slack-dispatched Claude/Fable session, the initial envelope must require, in this order:

```text
BEFORE DOING ANY WORK:
1. reply in this exact Slack thread with `ACK <operation_key>`;
2. read the entire existing Slack thread;
3. do not begin execution until both ACK and thread-read are complete;
4. keep all later DECISION_REQUEST / BLOCKED / RESULT and Sol replies in this same thread;
5. after posting a nonterminal return, enter the approved wait/watch path instead of silently abandoning the carrier.
```

The machine contract does not infer compliance merely because an ACK string exists. A real provider/session receipt or later target acknowledgement remains separately required where the underlying Wake/runtime law requires it.

The top-level commission can trigger `WAKE_COO` only when the commission already exists canonically and the exact COO routing basis is already bound. It may not find/assign a new worker, choose a provider, or mint a new Job. Absent bound recipient => `NO_ACTION / TARGET_UNBOUND`, never generic Slack dispatch.

---

## 6. Stateless dialogue-turn classifier

The classifier consumes one completely validated parent plus bounded ordered valid dialogue frames. It performs no network call, no write and no provider operation.

Its closed output vocabulary is:

```text
NO_ACTION
WAKE_CEO
WAKE_COO
WAKE_COO_TERMINAL
TERMINAL
REFUSE
```

### 6.1 COO/Fable-origin turns

| Latest valid semantic turn | Classifier result |
|---|---|
| valid initial commission, exact COO target bound, no COO ACK yet | `WAKE_COO` |
| `ACK` | `NO_ACTION` |
| `PROGRESS` with `requires_response=false` | `NO_ACTION` |
| `BLOCKED` | `WAKE_CEO` |
| `DECISION_REQUEST` | `WAKE_CEO` |
| `RESULT` | `WAKE_CEO` |

A future message type cannot implicitly inherit wake behavior. Unknown types refuse until source law is amended.

### 6.2 Sol-origin turns

| Latest valid semantic turn | Classifier result |
|---|---|
| `RULING` replying to the current COO request | `WAKE_COO` |
| `CONTINUE` | `WAKE_COO` |
| `AMENDMENT_AVAILABLE` with required canonical ref | `WAKE_COO` |
| `STOP`, with no later COO consumption receipt | `WAKE_COO_TERMINAL` |
| `STOP`, followed by exact COO `ACK`/terminal receipt for that stop | `TERMINAL` |

### 6.3 Lineage law

Slack timestamp order alone is not semantic turn ownership.

Every actionable reply must satisfy existing reply/message-key lineage and commission applicability rules. If two valid frames create competing semantic leaves for the same unresolved request, the classifier returns `REFUSE / DIALOGUE_FORKED` rather than choosing the newest timestamp.

Edits/deletes never rewrite already-consumed turns. Correction uses a new semantic message key under existing ASD law.

---

## 7. Derived Agent-Dialogue Attention fact

A classifier result requiring Wake is reduced to one deterministic source fact before Wake is invoked.

Conceptual contract:

```text
mastermind.agent_dialogue_attention.v1
```

Required semantic fields are limited to:

- source dialogue schema/version;
- exact canonical `message_key`;
- exact immutable commission fingerprint;
- exact `operation_key`;
- target seat (`ceo` or `coo`);
- closed attention kind `dialogue_turn_pending`;
- canonical workstream / root-job correlation when already present;
- non-authoritative evidence refs needed to reread the exact Slack thread.

The attention identity MUST NOT include:

- Slack event delivery ID;
- Slack retry count;
- provider/model/account;
- native session handle;
- current RuntimeBinding generation;
- arbitrary message prose;
- timestamp except as non-identity evidence;
- caller-claimed session alias.

The same valid dialogue turn observed five times or rediscovered after restart produces the same semantic attention identity.

This attention fact is derived, not persisted in a new store. Slack remains the owner of thread history; the existing dialogue contract remains owner of message semantic identity.

---

## 8. Wake composition

The Wake Fabric gains one reviewed source family conceptually equivalent to:

```text
SourceKind.AGENT_DIALOGUE_ATTENTION
WakeKind.DIALOGUE_TURN_PENDING
```

Exact enum/string syntax is frozen by the implementation plan after current #174 head/merge reconciliation, but the semantic law is fixed here.

The Wake obligation identity is route-independent. It is derived from the deterministic attention source identity and wake kind, not from Slack delivery retries or provider/session routing.

Routing then follows **existing `SessionTargetRegistry` precedence**:

```text
root_job_id binding, when supplied and valid
    -> exact seat binding
else reviewed workstream binding
    -> exact seat binding
else permitted seat default
```

Caller-provided Slack session labels are ignored. If an explicitly supplied root/workstream routing identity is malformed or unbound, Wake refuses rather than falling through.

The resulting current `RuntimeBinding` supplies provider-native destination identity. Binding rotation changes delivery destination identity, not the dialogue attention fact or Wake obligation identity.

No Slack/turn-watcher module imports provider SDKs or calls Claude/Codex/ChatGPT directly.

---

## 9. Hot path versus cold path

### 9.1 Hot already-active COO path

If the target Claude/Fable process is still alive and already using the accepted Agent Dialogue client, it may call the existing bounded `wait_for_reply` behavior after posting a nonterminal return:

```text
COO posts DECISION_REQUEST / RESULT
    -> waits on the exact bound thread
    -> Sol reply appears
    -> same process validates reply
    -> continues immediately
```

No Wake delivery is necessary while the exact session is already actively waiting.

The Relay observer may still derive the same attention fact for Sol; duplicate observation remains identity-stable.

### 9.2 Cold/sleeping target path

If the target is not actively waiting:

```text
valid opposite-side dialogue turn
    -> AgentDialogueAttention
    -> Wake obligation
    -> existing SessionTarget / RuntimeBinding
    -> provider-native Wake transport
    -> exact bound reasoning surface resumes
    -> rereads the complete thread + canonical company state
    -> continues only inside existing authority
```

Wake may not create a substitute provider conversation when exact same-session continuation is required by that transport's law.

### 9.3 CEO target behavior

`WAKE_CEO` means wake the **canonical CEO target resolved by existing Wake routing**, not “pick any ChatGPT account.”

If the bound CEO target is currently `codex`, Wake may use the approved Codex transport once production law permits it. If it is a ChatGPT/managed-browser target whose transport is not implemented/armed, the turn remains pending/unavailable; the watcher may not silently switch to another CEO target.

This preserves accountability across multiple sister Sol sessions while refusing title/tab/name similarity as routing authority.

---

## 10. Observer loop and restart recovery

The existing Agent Relay service owns one background observation loop after the production dialogue prerequisite permits it. This is an extension of the same service, not a second daemon.

The first implementation SHOULD use the least-authority transport already supported by the accepted Agent Relay app. A bounded Web API polling implementation is acceptable for the first proof if it requires no new Slack credential class/scope and meets latency/rate limits. Socket Mode or another event stream is a later optimization only if separately justified; it is not required merely to make the architecture work.

### 10.1 No persistent cursor

The observer may cache eligible thread locators and latest validated frames in memory. Those caches disappear on restart.

On service boot/reconnect:

```text
CONNECTED
-> RECONCILING
-> bounded channel history traversal
-> identify eligible watcher-enabled commission parents
-> read bounded complete thread history for each
-> recompute turn classifier
-> derive the same attention identities
-> READY
```

The reviewed implementation plan must freeze numerical history/time/page bounds from actual `#agent-dispatch` volume. The bounds must be large enough to cover the declared maximum watcher-enabled commission lifetime. If complete traversal cannot be proven within those bounds, the service remains `RECONCILIATION_INCOMPLETE`; it does not skip old pending turns or create a cursor DB.

### 10.2 No per-thread task lifecycle

A watcher-enabled thread is eligible because its validated parent/commission says so and remains within its reviewed nonterminal dialogue semantics. There is no durable `watching=true`, lease, heartbeat or task row.

---

## 11. Dialogue ACK versus Wake TARGET_ACKNOWLEDGED

These are separate facts.

```text
Slack `ACK <operation_key>` / agent_dialogue ACK
    = dialogue/admission testimony that the target session claims the bounded commission context

Wake `TARGET_ACKNOWLEDGED`
    = canonical Wake lifecycle fact that the exact runtime-bound target consumed a delivered Wake
```

Slack ACK cannot satisfy Wake acknowledgement. Provider delivery cannot satisfy Wake acknowledgement. A model-generated sentence cannot satisfy Wake acknowledgement.

The separately approved Wake ACK-ingress architecture remains the owner of target-consumption proof. A future exact session may consume the thread and submit a bounded Wake ACK only through the reviewed trusted host/runtime ingress. Until that exists, a dialogue can proceed on the hot active-session path but end-to-end cold Wake remains `PARTIAL`.

---

## 12. Idempotency, ambiguity and loop prevention

### 12.1 Duplicate observation

Same dialogue `message_key` + same semantic fingerprint + same commission => same attention source => same Wake obligation.

Repeated Slack events, polling passes or service restarts do not mint another logical Wake.

### 12.2 Changed semantic payload

Same semantic key + changed fingerprint => existing ASD conflict/refusal. No Wake is minted from the conflicted frame.

### 12.3 Wake effect unknown

If provider delivery may have begun but the Wake client loses the response:

```text
EFFECT_UNKNOWN
-> preserve the same Wake obligation / delivery carrier
-> reconcile existing Wake delivery state
-> never mint a fresh dialogue key
-> never choose another session/provider
```

### 12.4 Slack write effect unknown

Existing ASD message-key/history reconciliation remains controlling. No GitHub-comment or personal-account failover is added.

### 12.5 Self-loop

Agent Relay ignores/refuses its own non-dialogue transport echoes. One Sol `RULING` does not wake Sol again; one COO `RESULT` does not wake COO again. Target direction comes only from the closed classifier table.

### 12.6 Stale applicability

If the frame applies to an immutable head/commission/root identity that is now invalid under the accepted dialogue contract, classify `REFUSE`, not Wake. The target session may be manually inspected by Sol only after canonical reconciliation; the watcher does not repair source law.

---

## 13. Security and privacy

The watcher never requires or stores:

- provider native handles in Slack/Git;
- Slack bot/app token values;
- ChatGPT/Claude/Codex credentials or cookies;
- browser target IDs;
- arbitrary model prompts as Wake identity;
- private provider/account PII;
- raw GitHub diffs/logs in Slack frames;
- a list of local running apps/windows as session truth.

Thread locators, operation keys, commission hashes, canonical Job/Attempt IDs and stable logical session aliases may appear only where their owning contracts already allow them and only as non-secret identity/evidence. Native `RuntimeBinding` destination details remain runtime-local.

A target/model cannot author target seat, routing workstream, root binding, RuntimeBinding generation, Wake transport, effective grant or source-resolution status through Slack prose.

---

## 14. Collision and dependency law

### Wake PR #174

#174 remains the sole native Wake transport carrier. This amendment does not edit #174-owned provider-transport files while #174 is open. Turn classification and Agent-Dialogue Attention can be implemented production-inert in the existing ASD package first. The Relay→Wake adapter that needs closed Wake source vocabulary waits for #174 acceptance/merge or an exact disjoint-path reconciliation approved by Sol.

### ASD-A2/A3

ASD-A2 remains the first production Agent Relay app/service proof. The turn-watcher may not claim real Slack observation before A2 is accepted. A3 remains the real active-session dialogue proof. The first bilateral watcher canary may compose with or immediately follow A3, but must not make A2/A3 look accepted merely because watcher code exists.

### Executive routing / CF2

Root-job routing uses existing Executive/Wake bindings only when the underlying Job exists. This amendment does not create Jobs to make routing convenient. Pre-Executive manual commissions may use only existing reviewed workstream/seat routing where unambiguous; otherwise cold Wake is unavailable.

### ChatGPT browser / managed-seat actuation

No GUI automation is introduced here. If an exact sister Sol web conversation is not reachable by an accepted Wake transport, the watcher returns target unavailable rather than using browser-tab title matching or undocumented prompt injection.

### WP-1/WP-2

Worker-aware dialogue v2 and the company-dialogue MCP facade remain useful independent prerequisites. Their trusted actor/context injection is reused by the watcher; no watcher-specific identity schema is added.

---

## 15. Bounded implementation waves inside the existing WP program

These are sub-waves of the existing WP-0 carrier/program. They do not create a new workstream or competing architecture.

### WP-TW1 — deterministic thread-turn classifier

**Mission:** inside the existing `integrations/slack_agent_dialogue` package, implement pure deterministic parent/thread validation, turn classification and `AgentDialogueAttention` projection with zero network and zero persistence.

**Required discriminators:**

- initial bound commission => `WAKE_COO` only when recipient routing is already lawful;
- ACK/ordinary PROGRESS => no CEO wake;
- BLOCKED/DECISION_REQUEST/RESULT => CEO wake;
- RULING/CONTINUE/AMENDMENT_AVAILABLE => COO wake;
- STOP => one terminal COO wake then terminal after exact consumption receipt;
- duplicate Slack delivery/restart => same attention identity;
- same message key changed payload => refusal;
- two semantic leaves => refusal;
- wrong sender/channel/commission/work/head => refusal;
- caller-claimed session alias cannot alter target;
- edits/deletes cannot rewrite consumed turn;
- no new file/db/cache authority.

### WP-TW2 — existing Agent Relay observer + Wake adapter

**Gates:** WP-TW1 accepted; current ASD service collision census; #174 transport/source-law reconciliation; production remains disarmed until its own gates permit.

**Mission:** extend the existing Agent Relay service with one bounded background observer/reconciliation loop and adapt exact `AgentDialogueAttention` to existing Wake Fabric. No provider imports inside Slack code. No new daemon, queue, cursor, scheduler or session registry.

**Required proof:** restart reconstruction, bounded history completeness, duplicate event suppression by identity rather than mutable cursor, exact root/workstream/seat routing, unbound target refusal, Wake effect-unknown same-carrier reconciliation, and no self-loop.

### WP-TW3 — bilateral no-Chairman wake canary

**Gates:** production Agent Relay accepted, appropriate Wake transport(s) live enough for the chosen CEO/COO targets, and any required target Wake ACK law stated truthfully.

**Mission:** execute one real bounded handoff where Chris performs no wake/copy/paste after initial authorization:

```text
Sol commission
-> same bound Claude/Fable session ACK + full-thread read
-> work
-> RESULT or DECISION_REQUEST
-> automatic Sol continuation/review
-> Sol RULING / CONTINUE
-> automatic resume of the same Claude/Fable session
-> repair/continue
-> final RESULT
-> Sol final review + STOP
```

Proof must include one Relay restart/reconciliation during the sequence, no duplicate provider session, no duplicate Wake obligation, no duplicate Job/Attempt, and zero watcher persistence.

### WP-TW4 — broader worker/provider adoption

Only after WP-TW3: extend the same classifier/Wake bridge to worker-aware WP-4/WP-5 provider-neutral actors. No provider-specific watcher is allowed.

---

## 16. Capability ledger after this amendment

Before implementation:

- Worker Presence / Dialogue Gateway architecture: `SPEC_ONLY` on this unmerged records carrier.
- ASD A0/A1 storeless dialogue core: existing `BUILT_NOT_PROVEN / DEVELOPMENT_UNARMED`.
- Production Agent Relay: `NOT_BUILT / PRE-FLIGHT GATED` until A2 proof.
- Stateless dialogue turn classifier: `NOT_BUILT`.
- AgentDialogueAttention→Wake bridge: `NOT_BUILT`.
- Codex/Claude provider-native Wake: whatever exact #174 current truth earns; not upgraded by this document.
- Target Wake ACK ingress: `NOT_BUILT` until its separate accepted wave.
- Zero-manual-wake bilateral Sol↔Fable loop: `NOT_BUILT` until WP-TW3 real proof.

Records/spec merge must never be called the capability working.

---

## 17. Acceptance standard for the Chairman problem

This amendment is complete only when the real system demonstrates all of:

1. one canonical commission and one Slack thread;
2. initial COO admission requires ACK + full-thread read before work;
3. a valid COO return wakes/re-enters the owning Sol responsibility without Chairman action;
4. Sol rereads canonical GitHub/Agent OS/Executive evidence before consequential review/action;
5. Sol's RULING/CONTINUE wakes the same bound COO reasoning surface without Chairman action;
6. session/provider destination changes cannot change executive authority or dialogue identity;
7. duplicate/replayed Slack observations cannot create duplicate logical Wake;
8. Relay restart loses no pending turn and uses no persistent cursor/inbox;
9. unbound/ambiguous target refuses instead of selecting another ChatGPT/Claude session;
10. STOP reaches the target once and becomes terminal rather than creating a ping-pong loop;
11. Slack ACK, Wake delivery and Wake TARGET_ACKNOWLEDGED remain separate facts;
12. no new lifecycle, worker registry, watcher registry, Wake registry, queue, scheduler, retry plane or session database exists;
13. Chris performs zero intermediate wake/copy/paste actions in the canary.

---

## 18. Exact next action after written-spec approval

After the Chairman reviews this checked-in amendment:

1. keep the same WP-0 branch/carrier and reconcile any sister-session movement;
2. use `superpowers:writing-plans` to write a bounded WP-TW1 implementation plan first;
3. plan WP-TW2 separately because its Wake dependency must reconcile #174's accepted final source/transport law;
4. keep WP-TW1 production-inert and disjoint from #174/ASD-A2 so it may proceed immediately after planning;
5. do not create a new workstream, second WP architecture PR, generic Slack watcher service or per-thread automation fleet;
6. after WP-TW1 is accepted, release WP-TW2 only when its exact Wake/Agent Relay dependency gates permit;
7. reserve WP-TW3 as the real no-Chairman acceptance proof, not a synthetic fixture.

The first implementation change after written-spec approval is therefore **the pure stateless classifier/attention contract, not a background daemon and not provider Wake code**.
