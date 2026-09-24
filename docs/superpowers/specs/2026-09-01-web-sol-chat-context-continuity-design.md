# Web-Sol Chat Context Continuity — Detailed Design

**Date:** 2026-09-01  
**Chairman operation:** `web-sol-chat-context-continuity-20260901-chairman-001`  
**CR-F0 operation:** `web-sol-chat-context-continuity-cr-f0-20260901-sol-001`  
**Owner:** Sol, AI CEO  
**Existing workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Linear projection:** `MAS-198`  
**Protected source at freeze:** `187490f3d5676adf7a249d69afacedd00b3efcec`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**Release state:** `RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT`.

CR-F0 defines product, authority, contracts, failure behavior, and proof. It performs no browser or runtime mutation. **No browser/runtime implementation is authorized by CR-F0.**

## 1. Problem statement

Long-running ChatGPT Pro conversations eventually become unusable, intentionally retired, or too uncertain to remain the current reasoning surface. The current Chairman recovery workflow—open a new chat in the same Project and ask it to continue a named predecessor—demonstrates a useful provider affordance but is manual and not an authority protocol.

The product must preserve one logical Sol responsibility while rotating the disposable provider conversation underneath it. It must work even when the predecessor transcript cannot be loaded, must never equate a title with identity, and must prevent a revived predecessor from regaining authority.

## 2. Outcome and non-outcomes

### 2.1 Outcome

```text
stable logical responsibility
  + exact current RuntimeBinding
  + sufficient canonical continuation
  + ROTATION_REQUIRED
        |
        v
one exact same-profile / same-Project successor
        |
one deterministic continuation bootstrap
        |
exact surface verification + accepted semantic readiness
        |
CAS/ABA-safe RuntimeBinding succession
        |
stale predecessor fenced + navigation projected
        |
same logical Sol completes the next governed action
```

### 2.2 Non-outcomes

This is not:

- generic browser automation;
- transcript replication;
- a session database;
- title-based continuation;
- a model-output scraper;
- a retry/failover system;
- a second Executive lifecycle;
- an OpenClaw substitute;
- automatic usage-limit evasion;
- proof that current Web-Sol is installed or production-ready.

## 3. Current capability ledger

| Capability | Current state at design freeze |
|---|---|
| exact Web-Sol `INSPECT` / `FOREGROUND` source | `BUILT_NOT_PROVEN / PRODUCTION_NOT_INSTALLED` |
| R1 lifecycle reconstitution | `BUILT_NOT_PROVEN`, PR #306 open with bounded repair |
| T1 transport hardening | `BUILT_NOT_PROVEN`, PR #308 open with bounded repair |
| generic provider error probe | source exists |
| exact context-exhaustion classification | `NOT_BUILT` |
| successor creation | `NOT_BUILT` |
| bounded bootstrap submission | `NOT_BUILT` |
| exact successor verification | `NOT_BUILT` |
| ChatGPT Web semantic ACK | not production-proven |
| ChatGPT RuntimeBinding writer/succession | `SPEC_ONLY / NOT BUILT` |
| autonomous context rollover | `NOT_BUILT` |
| one real Sol rotation | `NOT_BUILT` |

The design does not collapse these states into “Web-Sol is live.”

## 4. Source precedence and collision reconciliation

Authority order:

1. Chairman operation `web-sol-chat-context-continuity-20260901-chairman-001`.
2. Protected source and same-SHA Skillpack.
3. `EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md`, especially CNM-C1.
4. `EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`.
5. Accepted path-specific Web-Sol amendments and protected S0/S1/F1/F2 source.
6. Current exact heads of open R1 PR #306 and T1 PR #308, after their own review/repair gates.

PR #306 owns service-worker/browser reconstitution. PR #308 owns native transport hardening. CR-F0 is path-disjoint records work. CR-P1 may not rewrite either implementation path from stale master; it must consume their accepted protected descendants or declare explicit ancestry.

## 5. Identity model

### 5.1 THE SOL IDENTITY IS NOT THE CHAT CONVERSATION

Stable fields:

- `responsibility_ref`;
- program/workstream identity;
- logical `session_alias`;
- accepted organizational authority;
- unresolved reciprocal dialogue edge, if any.

Rotating fields:

- ChatGPT conversation;
- provider conversation id / native handle;
- RuntimeBinding generation;
- conversation URL;
- browser tab/window coordinate.

The exact successor continues the same responsibility. It is not a replacement CEO.

### 5.2 TITLE IS NOT IDENTITY

Title is advisory only. It cannot select a predecessor, successor, account, profile, Project, or RuntimeBinding. Duplicate titles and renamed titles must not change authority. **Project/predecessor chat history is advisory only.**

Exact URL/fingerprint/provider handles are runtime coordinates and evidence inputs. They are not durable organizational identity.

### 5.3 Provider identity minting

The provider may not expose a durable successor conversation id until the first message is submitted. CR-P1 must determine this empirically. The contract must represent these as distinct evidence stages even when the provider UI fuses them:

```text
SUCCESSOR_CREATION_NOT_ATTEMPTED
SUCCESSOR_CREATION_REQUESTED
SUCCESSOR_IDENTITY_OBSERVED
BOOTSTRAP_SUBMISSION_REQUESTED
BOOTSTRAP_DELIVERED
EFFECT_UNKNOWN
```

A blank tab, title, URL lacking a conversation id, or newest-tab ordering is not a successor identity receipt.

## 6. Owner architecture

Normative owner statements:

- **Executive OS owns Job / Attempt / Worker / Event lifecycle and CEO admission**.
- **Agent OS owns durable continuation, decisions, discoveries and handoffs**.
- **SessionTargetRegistry / RuntimeBinding owns the logical target and rotating exact runtime binding**.
- **surface_bindings remains navigation-only**.
- **Web-Sol is the closed browser actuator**.
- **GitHub owns implementation and immutable evidence**.

Additional boundaries:

- Capacity/managed-seat ownership resolves eligible account/profile/Project before Web-Sol is invoked.
- Company Dialogue / Agent Relay / Wake / accepted continuation ownership provides semantic pickup/start/source-resolution truth.
- Web-Sol reports browser-side receipts only; it never grants organizational authority.
- Linear may project accepted status but never outruns GitHub or Agent OS.

Forbidden duplicate systems:

- **no Chat session registry**;
- **no transcript memory database**;
- **no second RuntimeBinding store**;
- no second lifecycle;
- **no rollover queue**;
- **no retry ledger**;
- **no browser-tab authority plane**;
- no Web-Sol memory database;
- no title lookup authority;
- no newest-tab election;
- no hidden failover graph.

## 7. Rotation classifier

### 7.1 Closed states

```text
SESSION_HEALTHY
ROTATION_SUSPECTED
ROTATION_REQUIRED
AUTH_REQUIRED
PROVIDER_TRANSIENT
SURFACE_UNUSABLE
UNKNOWN
```

### 7.2 Closed reasons

```text
MANUAL_RETIREMENT
CONTEXT_LIMIT_SUSPECTED
REPEATED_TERMINAL_GENERATION_FAILURE
SURFACE_UNUSABLE
UNKNOWN
```

### 7.3 Truth boundary

**Thinking failed != context exhausted**.

Stable DOM/test-id metadata may support a precise provider condition only when independently falsified. Generic error presentation is not sufficient. **Never export raw provider error text.** Closed observations may include booleans, closed enums, bounded timestamps, and opaque fingerprints only.

**If exact context exhaustion cannot be proven, preserve suspicion or surface-unusable uncertainty.** The orchestration owner may still decide `ROTATION_REQUIRED` when the exact bound surface cannot continue safely; the recorded reason must remain no more precise than evidence permits.

### 7.4 Example decision matrix

| Browser facts | Permitted classification |
|---|---|
| exact surface responsive, composer usable, no terminal condition | `SESSION_HEALTHY` |
| generic provider error shown once | `ROTATION_SUSPECTED` or `PROVIDER_TRANSIENT` |
| auth wall | `AUTH_REQUIRED` |
| exact surface cannot be interacted with safely and repeated recovery fails | `SURFACE_UNUSABLE` or policy-approved `ROTATION_REQUIRED` |
| explicit supported context-limit state | `ROTATION_REQUIRED / CONTEXT_LIMIT_SUSPECTED` unless provider semantics prove stronger wording |
| contradictory/missing evidence | `UNKNOWN` |

## 8. Closed action contract

The current v1 action protocol remains exactly:

```text
INSPECT
FOREGROUND
```

A new protocol version, capability digest, and deployment artifact may expose only:

```text
CREATE_SUCCESSOR
DELIVER_CONTINUATION_BOOTSTRAP
VERIFY_SUCCESSOR
```

Forbidden public primitives:

```text
CLICK
TYPE
SEND_TEXT
NAVIGATE_URL
EXECUTE_JS
QUERY_SELECTOR
READ_TRANSCRIPT
READ_MODEL_OUTPUT
COPY_CHAT
SELECT_ACCOUNT
```

### 8.1 Initial provider scope

Accepted predecessor URL form:

```text
/g/g-p-<project>/c/<conversation>
```

Required invariants:

- successor is created in the **same approved managed-browser profile**;
- successor is in the **same ChatGPT Project**;
- successor has a **different new conversation identity**;
- non-Project predecessor returns `NON_PROJECT_CONVERSATION_UNSUPPORTED`;
- **No caller-selected project/account/profile URL.**

Profile/account/Project are derived from the exact predecessor binding and accepted managed-seat owner. Web-Sol does not accept a free-form URL or profile selector.

### 8.2 Conceptual request envelope

The final schema is frozen in CR-P1, but every mutating request must bind:

```text
schema/version
operation_key
responsibility_ref
session_alias
binding_id
expected_binding_generation
predecessor_provider_handle / opaque fingerprint
expected_profile identity
expected_Project identity
closed rotation reason
issued_at / expires_at
nonce
capability digest
```

The caller does not provide arbitrary DOM selectors, account IDs, browser instructions, or message text.

### 8.3 Conceptual receipt envelope

Receipts are secret-free and closed:

```text
request identity fields
closed status
effect_state = NONE | APPLIED | EFFECT_UNKNOWN
predecessor fingerprint
successor fingerprint/provider handle when proven
same_profile = true|false|unknown
same_project = true|false|unknown
different_conversation = true|false|unknown
observed_at
protocol/capability identity
```

No transcript, output text, cookie, storage, credential, raw DOM, or arbitrary URL is exported.

## 9. Continuation bootstrap

**Do not submit arbitrary model/user text through Web-Sol.** The bootstrap is deterministically rendered from validated canonical references.

Required text shape:

```text
SOL CONTINUATION

Logical responsibility:
<responsibility_ref>

Reason:
<closed reason>

Predecessor:
<opaque predecessor reference/fingerprint>

Current continuation record:
<Agent OS continuation/handoff ref>

Current protected source:
<protected SHA / Skillpack identity>

Instruction:
Recover current canonical state using COLD_START.
Project/predecessor chat history is advisory only.
Do not restart completed work.
Recover any open reciprocal worker dialogue before creating replacement work.
Continue the same logical responsibility only after current binding/effect gates are satisfied.
```

**Predecessor title is advisory only.** Prefer the continuation reference over embedding long prose. A **bounded continuation manifest** is allowed only when the new chat cannot read the durable reference. Its canonical copy/reference belongs in Agent OS, not Web-Sol.

The renderer must reject missing/malformed/stale responsibility, source pin, continuation reference, predecessor binding, and unresolved effect status. It must enforce size and character bounds and produce byte-stable output for the same accepted inputs.

## 10. Exact state machine

### 1. ROTATION REQUEST

Input: exact current binding, closed reason, current authority, operation key.  
Output: accepted `ROTATION_REQUIRED` or typed refusal.  
No browser mutation.

### 2. EFFECT FENCE

Read current operation/effect state. **EFFECT_UNKNOWN blocks modifying continuation.** Read-only reconciliation remains allowed.

### 3. DURABLE CONTINUATION

Resolve accepted Agent OS continuation/handoff and current protected source. A dead predecessor is not required to emit a final summary.

### 4. EXACT TARGET RESOLUTION

Resolve current managed profile/account eligibility, exact Project, exact predecessor native handle/fingerprint, `responsibility_ref`, `session_alias`, binding id, and generation. Multiple candidates fail closed.

### 5. CREATE ONE SUCCESSOR

Perform one provider creation effect. Verify same profile/Project and distinct identity when observable. Lost post-effect receipt produces `EFFECT_UNKNOWN`. **Never blindly create another successor**.

### 6. DELIVER BOOTSTRAP

Submit one deterministic bootstrap through the closed action. Lost post-submit receipt produces `EFFECT_UNKNOWN`. **Never blindly submit the bootstrap twice**.

### 7. VERIFY SURFACE

Prove exact successor identity, same profile, same Project, responsiveness, and absence of a conflicting candidate. Browser verification is not semantic pickup.

### 8. SEMANTIC READINESS

**visible generated text is not PICKUP_ACK or START**. **semantic readiness must reuse an accepted Agent Relay / Company Dialogue / continuation ACK owner**. If no production-proven path exists, return the dependency and do not transfer authority.

### 9. RUNTIMEBINDING SUCCESSION

The existing writer compares expected generation and predecessor coordinate, then advances exactly one generation to the verified successor. It preserves logical identity and fences the old generation. Must be CAS/ABA-safe.

### 10. NAVIGATION UPDATE

Project the successor URL through existing `surface_bindings` only. If this projection fails after the canonical swap, **authority remains with the successor**, report **navigation degraded/stale**, and **Do not roll authority backward merely to make navigation agree**.

### 11. POST-CUTOVER INSPECT

Use exact inspection to prove successor health and stale-predecessor refusal at the current generation.

### 12. CONTINUE

The successor executes current `COLD_START`, reconstructs canonical state, recovers open reciprocal dialogue, and performs the next observable governed action without restarting completed work.

## 11. Effect semantics

| Operation boundary | No-effect proof | Ambiguous effect | Rule |
|---|---|---|---|
| create request refused before actuation | yes | no | bounded same-operation retry may be eligible |
| provider may have created successor; response lost | no | yes | reconcile exact Project/profile; **Never blindly create another successor** |
| bootstrap refused before submission | yes | no | bounded same-operation retry may be eligible |
| bootstrap may have submitted; response lost | no | yes | reconcile; **Never blindly submit the bootstrap twice** |
| semantic ACK absent | no authority effect | n/a | remain pending; do not scrape output |
| RuntimeBinding CAS rejects | yes | no | re-read canonical state |
| RuntimeBinding response lost after possible commit | no | yes | reconcile canonical generation before another write |
| navigation write fails after swap | authority already committed | navigation-only failure | successor remains authoritative |

There is no other-tab, other-account, newest-conversation, OpenClaw, or sister-session failover.

## 12. RuntimeBinding succession contract

Expected transition:

```text
generation N = exact predecessor
generation N+1 = exact successor
preserve the same session_alias and responsibility_ref
fence predecessor generation N
```

Required writer behavior:

- discover the existing canonical writer and persistence source before implementation;
- compare binding id, generation N, alias, responsibility, reasoning surface, provider handle, and exact target evidence in one accepted transaction boundary;
- accept only N -> N+1;
- refuse missing/malformed evidence, multiple successors, changed root responsibility, wrong profile/Project, duplicate N+1, stale N-1, or incompatible surface;
- persist enough canonical evidence to reconcile a lost response without a second store;
- remain **CAS/ABA-safe**;
- ensure **stale predecessor remains non-authoritative even if it later becomes responsive**;
- require fresh current-resolution before the next modifying action.

The dataclass in `control_plane/session_targets.py`, read-only projection in `control_plane/runtime_binding_projection.py`, and storeless resolver in `control_plane/sol_action_target.py` are not themselves a general ChatGPT writer. CR-B1 must locate the accepted owner rather than invent one.

## 13. Semantic readiness contract

The following states remain distinct:

```text
SUCCESSOR_SURFACE_CREATED
BOOTSTRAP_MAYBE_DELIVERED
BOOTSTRAP_DELIVERED
SUCCESSOR_SURFACE_RESPONSIVE
SEMANTIC_READINESS_PENDING
PICKUP_ACK_ACCEPTED
START_ACCEPTED
RUNTIMEBINDING_SUCCESSION_COMMITTED
NAVIGATION_CURRENT
NAVIGATION_DEGRADED
```

A model can visibly answer while organizational pickup is absent. A plugin call can be queued while not executing. A RuntimeBinding can lawfully advance while local navigation is stale. The UI and records must report each fact separately.

## 14. Provider continuation falsifier

Run in a **disposable/non-sensitive ChatGPT Project** with harmless synthetic markers. Record exact profile, Project, predecessor and successor coordinates without secrets.

Required experiments:

1. new Project chat instructed to continue an exact predecessor title;
2. **duplicate predecessor titles**;
3. **renamed predecessor title**;
4. an **exact predecessor reference/URL** where UI/API behavior permits;
5. request a **synthetic fact that existed ONLY in the predecessor**;
6. same instruction outside the Project to determine whether **Project membership is essential**;
7. Project history disabled/unavailable where configurable;
8. creation without first submission, if the UI permits;
9. lost/obscured URL observation around first submission;
10. service-worker/native interruption during provider identity minting.

Questions answered:

- Does the successor receive full transcript, summaries, selected Project history, recent context, or nothing?
- Are duplicate/renamed titles reliable?
- Is title text semantically interpreted rather than resolved exactly?
- When does a durable conversation id appear?
- Are creation and first message one provider effect?
- Can exact same-Project membership be verified without transcript access?

Evidence may improve bootstrap UX. It may not establish authority from history/title.

## 15. Required failure matrix

CR-P1/CR-B1/CR-D1 must falsify at least:

- **wrong ChatGPT Project**;
- **wrong managed profile/account**;
- **two candidate new conversations**;
- provider creates a conversation but receipt is lost;
- bootstrap may have submitted but receipt is lost;
- successor never becomes responsive;
- **successor responds visibly but semantic ACK is absent**;
- predecessor still has an active generation;
- predecessor has `EFFECT_UNKNOWN`;
- **RuntimeBinding generation race / ABA**;
- navigation binding update fails after cutover;
- **extension service worker restarts during rotation**;
- **native transport disconnects during each effect boundary**;
- auth wall;
- provider transient;
- generic “Thinking failed” without context-limit proof;
- **predecessor already totally dead before checkpoint**;
- **ChatGPT Project history unavailable**;
- **Agent OS continuation record unavailable/stale**;
- **stale predecessor later becomes responsive again**.

The last case is mandatory: after generation succession the resurrected predecessor remains stale, may observe/reconcile only under current authority, and cannot originate a modifying action.

## 16. Security and privacy

ZERO:

- transcript scraping;
- `READ_MODEL_OUTPUT` or output export as company memory;
- cookie/storage/clipboard/proxy/fingerprint/credential reads;
- arbitrary DOM export;
- arbitrary text input;
- generic click/type/send/navigation/JavaScript/selectors;
- caller-controlled account/profile/Project;
- account switching;
- title/newest-tab authority;
- second lifecycle/session registry/memory/retry system;
- silent OpenClaw fallback;
- API Meta-CEO substitution;
- usage-limit evasion;
- secret-bearing receipts.

Every log/receipt is bounded, closed, and secret-free.

## 17. Release decomposition

### CR-F0 — source law

Records only. Defines this design and executable source-contract test. No runtime capability.

### CR-P1 — exact successor + bootstrap

One exact Project-bound provider capability, no RuntimeBinding transfer. Requires accepted R1/T1 base and provider falsifier evidence.

### CR-B1 — RuntimeBinding succession

Integrates accepted semantic readiness and canonical writer. Proves generation N/N+1, fencing, and no ABA.

### CR-D1 — disposable canary

Synthetic end-to-end rotation, including next bounded action, with **Zero Chairman click/type/message shuttling**.

### CR-PROD1 — real approved rotation

One approved real Project Sol rotation and observable continuation. **Do not call the program PROVEN_LIVE before CR-PROD1.**

Each is one independently useful capability per PR with RED/GREEN, exact-head CI/security, independent review, and applicable browser/production proof.

## 18. Observability

Secret-free receipts must make these distinctions observable:

- requested vs admitted vs browser-submitted;
- definite no-effect vs applied vs `EFFECT_UNKNOWN`;
- successor candidate vs exact verified successor;
- surface-responsive vs semantic-ready;
- binding-current vs navigation-current;
- predecessor visible vs predecessor authoritative;
- source merged vs installed vs canary-proven vs production-proven.

Raw error text, transcript, output text, and private profile material are excluded.

## 19. Product acceptance

A real approved bound MastermindX Project Sol is made rotation-required. Without the Chairman opening a chat or carrying a message:

1. exactly one correct successor appears in the exact profile/Project;
2. exactly one bootstrap effect is reconciled;
3. successor reconstructs protected source and Agent OS state;
4. completed work is not restarted;
5. open worker dialogue is recovered;
6. semantic readiness is accepted through the current owner;
7. RuntimeBinding advances exactly N -> N+1;
8. predecessor N is fenced;
9. exact Web-Sol health follows the successor;
10. successor completes the next governed action;
11. resurrected predecessor cannot complete that action;
12. injected ambiguity produces no duplicate successor or bootstrap.

Anything less remains `BUILT_NOT_PROVEN` or `PARTIAL`.

## 20. Stop conditions

Return to Sol/Chairman only for:

- irreconcilable current-law contradiction;
- provider behavior that cannot create/verify an exact same-Project successor without generic browser authority;
- canonical RuntimeBinding writer or semantic ACK owner genuinely absent, requiring an architecture ruling;
- production install/admin/credential action;
- irreconcilable modifying `EFFECT_UNKNOWN`.

Routine account/profile/chat choice is derived from the current exact binding, not delegated to the Chairman.
