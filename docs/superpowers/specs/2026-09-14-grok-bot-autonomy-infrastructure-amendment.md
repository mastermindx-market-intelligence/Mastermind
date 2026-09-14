# Grok Operations Infrastructure Amendment — Wake, Consultation, Helpers, and Runtime Proof

**Date:** 2026-09-14  
**Owner:** Sol, for Chairman Chris  
**Operation:** `grok-bot-autonomy-design-20260914-sol-001`  
**State:** `ARCHITECTURE_CANDIDATE / SPEC_ONLY / PRODUCTION_INERT`  
**Carrier:** existing Mastermind PR #624 / `sol/grok-bot-autonomy-design-20260914`  
**Procedure pin:** protected Mastermind `af9fce32861f9c1496b85a580e3569712170d92b`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1
**Organizational read pin:** Macro `e0e3fda2fa2a44d8d64c3f0a52b9d56c1de3653b`

## 1. Precedence and purpose

This amendment hardens and narrows `docs/superpowers/specs/2026-09-14-grok-bot-autonomy-foreman-design.md` against the current protected implementation. Where the earlier design describes a generic future candidate-return path, this amendment wins: protected W6-C1 now supplies the bounded Company Consultation contract and Company MCP producer facet. No Grok-specific callback store, sixth Executive tool, generic webhook-action API, alternate queue, new identity registry, or second result plane is permitted.

The Chairman-approved outcome remains:

> Mastermind should gain one always-available Grok operational teammate that can receive a real bounded obligation, inspect current company evidence, coordinate permitted economical help, and return an evidence-bound answer to the correct current parent without requiring Chris to move messages or choose worker accounts.

The Bot is not the CEO, lifecycle authority, ranked agenda, scheduler, provider router, durable memory, production deployer, or acceptance owner. It may later become an action-authoritative operational principal for closed decision classes under the existing Web CEO autonomous-delivery law; provider availability and a role prompt do not grant that authority.

## 2. Current capability ledger

| Capability | Current state | Evidence / limit |
| --- | --- | --- |
| Web-independent operational continuation law | `SPEC_ONLY / SOURCE_PROTECTED` | `docs/EXECUTIVE_WEB_CEO_AUTONOMOUS_DELIVERY_AMENDMENT.md` on protected source defines strategic, operational, and deterministic loops; it does not install the journey. |
| Company peer-consultation grammar | `BUILT_NOT_PROVEN / PRODUCTION_INERT` | W6-C1 protected at `f4730cc...`: `common/agent_dialogue_consultation_contract.py` and `integrations/mastermind_company_mcp/consultation.py`. |
| Consultation runtime receipts | `BUILT_NOT_PROVEN / UNMERGED / RELEASE_BLOCKED` | PR #615 exact head `97634130...` is green but fails review `5196352060`: protected-v1 breakage, unusable real Codex ingress, unjoined Wake/provider effects, contradictory `EFFECT_UNKNOWN`, and unsafe answer availability/consumption. Downstream code must not bind to it. |
| Executive read/app edge | `BUILT_NOT_PROVEN` | #599 is merged; its own receipt leaves intended installation and real client acceptance pending. It remains separate from Company Consultation. |
| Grok wake transport | `NOT_BUILT` | `grok-computer` is named in `control_plane/wake_transport.py` but `transport_implemented=false`; all checked-in targets remain disabled and global production is false. |
| Grok reasoning-surface identity | `NOT_BUILT` | `control_plane/session_targets.py` has no `grok-bot` reasoning surface. Existing `chatgpt-sol` targets using `grok-computer` are not a lawful substitute. |
| Remote Company Consultation app for Grok | `NOT_BUILT` | W6-C1 is hermetic/provider-free and has no installed authenticated remote composition. |
| Grok Bot product/account | `DARK_OR_DISCONNECTED` from Mastermind | Chris reports Grok Bot ready. This establishes human intent and likely product availability, not a Mastermind account, RuntimeBinding, connector, routine, or run receipt. |
| Economical helper fleet | `PARTIAL` | Existing Studio observations and provider-realm candidates prove bounded experiments only. Eligibility remains provider/account/plan/client/mode/data/budget specific. |
| End-to-end Grok autonomy | `SPEC_ONLY` | No real `Wake -> Grok -> consultation answer -> requester consumption` proof exists. |

## 3. Architecture freeze

### 3.1 One Bot, two task modes

Create exactly one initial Bot named **Grok Operations**.

- **Sentinel mode** diagnoses one material exception or returned-work obligation.
- **Foreman mode** requests and evaluates one bounded helper consultation inside the current admitted parent.

These are prompt/task modes, not separate principals, queues, budgets, RuntimeBindings, or Bots. A second Bot is held until measured workload proves a stable separate role. All Bots under one Cursor user share the same cloud computer, files, browser sessions, and logins, so splitting roles would not create credential isolation.

### 3.2 Two integration seams, one existing organization

```text
Existing Executive / Dialogue / Wake facts
                    |
                    v
      persisted Wake obligation and exact route
                    |
                    v
      Grok routine webhook transport adapter
                    |
          HTTP 200 = accepted/start only
                    |
                    v
          Grok Operations Bot turn
                    |
       current canonical reads as permitted
                    |
                    v
      Company Consultation MCP (four tools)
                    |
                    v
   W6-C consultation runtime / dialogue carrier
                    |
                    v
 current requester consumes answer and decides
```

The **inbound seam** is canonical Wake. The **outbound seam** is canonical Company Consultation. They remain separate because provider acceptance and returned company evidence are different facts. Neither seam owns the other, and neither becomes a new lifecycle. Consultation semantic receipts may project the exact Wake/provider evidence, but they may not independently mint dispatch, native-acceptance, retry, or effect-unknown truth.

### 3.3 Canonical owners remain unchanged

| Fact or action | Owner |
| --- | --- |
| Job / Attempt / Worker / Event lifecycle | Executive OS |
| Current admitted authority and operational grant | existing delegation/runtime owners |
| Exact logical target | SessionTargetRegistry |
| Exact rotating provider destination | RuntimeBinding |
| Attention obligation, delivery attempt, and `EFFECT_UNKNOWN` | existing Wake ledger/dispatcher |
| Peer question/answer grammar and budgets | Company Consultation contract |
| Consultation receipt lineage and requester consumption | W6-C runtime/Company Dialogue owner |
| Provider/account/plan/model/client eligibility | Capacity / Model Router / provider owner |
| Durable decisions/discoveries/handoffs | Agent OS |
| Implementation and proof | GitHub |
| Chairman-facing explanation | existing Control Room / Steward projection |
| Grok workspace files, memories, and routine history | disposable provider working context only |

## 4. Exact inbound Wake design

### 4.1 New reasoning surface and target

Do not repurpose a `chatgpt-sol` target. Add a closed `grok-bot` reasoning surface through the current SessionTarget owner and a disabled logical target such as:

```json
{
  "session_alias": "EXECUTIVE-COO-GROK-A",
  "target_seat": "coo",
  "reasoning_surface": "grok-bot",
  "wake_transport": "grok-computer",
  "allowed_transports": ["grok-computer"],
  "workstream": "executive",
  "target_enabled": false
}
```

The checked-in registry remains production-disarmed. Root-job overlays bind a real admitted Grok Worker/Attempt to this logical alias at runtime. The Bot name is presentation; the Worker/Attempt plus RuntimeBinding is the company identity.

### 4.2 RuntimeBinding and secret separation

The RuntimeBinding carries:

- logical session alias;
- opaque `binding_id` and generation;
- opaque native handle naming one installed webhook-routine target generation;
- non-secret account label where accepted;
- reasoning surface `grok-bot`.

It must not contain the webhook URL, bearer key, browser cookie, Cursor account credential, Company MCP token, or private host address. An existing secret owner resolves the opaque native handle to the current webhook URL/key at call time. Rotation creates a new target generation; it does not rewrite historical delivery receipts.

### 4.3 Wake adapter behavior

Add one provider adapter parallel to `CodexAppServerWakeDispatcher`, not another dispatcher or scheduler. It receives the existing `WakeNudge` and performs at most one provider POST.

The provider payload contains only bounded opaque correlation material:

```json
{
  "schema": "mastermind.grok_bot_wake.v1",
  "nudge_id": "NUDGE-...",
  "binding_id": "bind-...",
  "binding_generation": 1,
  "obligation_ids": ["WAKE-..."],
  "attempt_command_ids": ["WAKE-...:..."],
  "company_consultation_server": "mastermind-company-consultation-mcp"
}
```

No objective prose, source content, secret, credential, provider account, URL, native session token, worktree path, customer data, or approval text crosses the webhook.

Provider semantics:

- known failure before POST -> typed `TARGET_UNAVAILABLE` or `FAILED`;
- non-200 response -> definite no-run outcome according to the provider contract;
- HTTP 200 -> `ACCEPTED`, not `DELIVERED`, consumed, answered, or complete;
- timeout/connection loss after submission may have begun -> `WakeEffectUnknownError` and same-operation reconciliation only;
- no automatic retry, alternate Bot, account, host, webhook, Slack message, or provider failover;
- run-history/request-ID observation may reduce uncertainty but cannot manufacture target consumption.

Because the provider offers acceptance rather than an exact target ACK, initial Grok Wake receipts cannot claim `DELIVERED`. Recipient consumption is proved later by W6-C native/input and consultation receipts.

## 5. Exact outbound Company Consultation design

### 5.1 Reuse the protected four-tool facet

Grok receives only:

- `company.peers`
- `company.consult`
- `company.reply`
- `company.consultation`

The protected limits remain: one answer, at most four evidence reads, zero forward hops, bounded payloads, opaque peer refs, exact artifact revisions, no provider/session/account fields, and no authority-bearing action vocabulary. Grok does not receive `submit_ceo_intent` through this connection.

### 5.2 Version the external reasoning surface honestly

Protected v1 admits only its current closed surfaces and is immutable: every previously accepted/rejected frame and fingerprint must remain byte-for-byte stable. After C0 protects the consultation schema table, add `grok-bot` only in the **next unused lawful schema version**; do not assume that `v2` remains available, and do not label Grok as Codex or Claude. The new version must keep actor refs as real Worker/Attempt identities and require exact current RuntimeBinding correlation.

W6-C2 may project INTENT, dispatch, recipient, answer, and requester-consumption semantics only when each effect-bearing fact is causally derived from the exact canonical Wake attempt and typed provider observation. Downstream Grok work begins only after the current W6-C2 owner closes review `5196352060` and protects the actual interface. This amendment does not copy its draft runtime or effect reducer into a Grok module.

### 5.3 Authenticated remote composition

Expose Company Consultation as a separate authenticated Streamable HTTP app using the existing Business OAuth resource-server, audit, service-user, sealed-source, and Secure MCP Tunnel patterns. Do not widen the five-tool Executive app.

The remote app must:

- expose exactly the four Company Consultation tools;
- require a distinct exact scope such as `mastermind.company.consultation` under the existing policy owner;
- authenticate a dedicated least-privilege principal for the intended Grok account;
- reuse the existing W6-C runtime and peer resolver;
- own no database, result store, retry loop, Job lifecycle, provider client, or conversation memory;
- bind one accepted source release and server generation;
- emit bounded auth/audit facts without raw subject, token, Bot name, question, answer, or provider output;
- refuse startup if the runtime, source, policy, peer resolver, or W6-C generation is unavailable or mismatched.

Grok custom MCP must reach a public HTTPS URL; tunneling is reachability only and does not weaken OAuth or organizational authorization. Actual Grok Bot custom-MCP visibility, OAuth linking, tool inventory, and invocation must be proven on the intended account before the connection is called usable.

## 6. Context and operating method

A webhook nudge contains no work prose. On wake, Grok must use the Company Consultation/current-read surfaces to recover one exact current obligation and its bounded context. Required context includes:

- actual parent/root and accepted mission;
- current action-authoritative parent;
- applicable decision class and prohibited classes;
- exact question or attention obligation;
- source/artifact revisions and evidence refs;
- freshness, missing inputs, and corrections;
- response budget and expiry;
- what counts as useful completion;
- required return action.

The Bot may not scan Slack, GitHub, or the filesystem broadly to invent a mission. If the exact obligation cannot be resolved, it returns/refuses through the current consultation path rather than searching for unrelated work.

## 7. Helper and subagent design

Grok never receives GLM, MiniMax, Alibaba, xAI API, Codex, or Studio credentials merely to orchestrate helpers. It calls `company.consult` with an opaque peer selected by the existing resolver after current suitability, capacity, account/plan/client/mode, data-rights, and budget checks.

Initial helper law:

- one active helper;
- one answer;
- zero forwarding/nested helpers;
- at most four evidence reads;
- no source write or persistent independent deliverable inside a consultation;
- exact artifacts only;
- a bad answer can be corrected only through the contract's current correction semantics and parent budget;
- source-modifying, long-lived, independently reviewable, or separately effectful work becomes an Executive child Job instead;
- no fallback from an included subscription route to paid API inference without the accepted economic exception.

Grok evaluates the helper answer against the frozen acceptance contract. Model/provider exit success is not acceptance. The requester/current parent remains responsible for consuming the answer and deciding whether to continue, repair, park, or escalate.

## 8. Security and account posture

### 8.1 Account boundary

Use one dedicated Cursor user for the Grok Operations workload when credential isolation from other Bots is required. Multiple Bots under one user share the computer and logins and therefore are not isolation. The first rollout uses one Bot only.

### 8.2 Default Bot posture

- one clear profile: Grok Operations;
- local execution disabled unless a later separate canary requires it;
- no browser login to production-admin or personal accounts;
- no raw SSH, Mac control, generic shell, cloud-provider console, billing console, password manager, or source-write connector;
- no Slack plugin initially; if later connected, remember it acts as the connected user rather than a distinct company principal;
- no public Bot share link;
- no secrets, internal URLs, customer data, or credentials in the Bot description, skill, routine instruction, conversation, or shared files;
- Auto Review is defense-in-depth only, not organizational authority or complete side-effect enforcement.

### 8.3 Secret custody

Keep these domains separate:

1. Grok routine webhook URL/key;
2. Company Consultation OAuth client/access/refresh material;
3. Secure MCP Tunnel runtime/admin material;
4. provider/helper credentials owned by their existing providers;
5. any optional future OpenClaw/local-actuation credentials.

No secret is copied into GitHub, Slack, Agent OS, Bot memory, webhook JSON, RuntimeBinding, or acceptance receipts. Revocation of a company tool grant does not prove a remote Bot run stopped; it prevents the next company effect and leaves provider computation/billing status explicit.

### 8.4 Network ceiling

Self-serve Grok/Cursor controls do not establish a Mastermind destination allowlist. Compensate at the server boundary: one public HTTPS endpoint, exact OAuth audience/scope, closed tool inventory, bounded bodies, no redirects, no arbitrary URL fetch, and zero source/production authority. A tunnel alone is not a security boundary.

## 9. Product and Control Room projection

The Chairman should see one Grok Operations responsibility card, not provider chatter. Compose from existing facts:

- logical target alias and `grok-bot` reasoning surface;
- sanitized RuntimeBinding ID/generation and source freshness;
- capability/profile/server generation;
- routine state: configured, active, paused, unknown;
- latest Wake state: requested, accepted, definitely not started, or `EFFECT_UNKNOWN`;
- consultation state: intent, recipient accepted/consumed, answer available, requester consumed, work accepted;
- current budget/usage observation and whether overflow is disabled/unknown;
- exact blocker and decision owner;
- evidence links.

Do not display raw webhook URLs/keys, OAuth material, private host coordinates, full question/answer, model chain-of-thought, or inferred liveness. The card is a projection over Wake, W6-C, RuntimeBinding, Capacity, and GitHub—not a Grok status database.

## 10. Failure and correction behavior

| Failure or ambiguity | Required result |
| --- | --- |
| Webhook target/key unavailable before submission | definite target unavailable; no provider run claimed |
| Provider returns non-200 | definite no-run result under the current documented contract |
| HTTP 200 | provider accepted/start only; await consultation receipts |
| Post-submit timeout/lost reply | `EFFECT_UNKNOWN`; same nudge/target reconciliation, no resend |
| Bot routine paused or usage exhausted | preserve obligation in Wake/Executive; independent work continues |
| Company MCP unavailable | Bot cannot return company evidence; no Slack/GitHub workaround |
| Wrong/old binding generation | refuse as stale target; no target substitution |
| Duplicate same semantic question | idempotent existing consultation/result |
| Same identity with changed semantic payload | conflict/refusal, not a second operation |
| Late answer after correction/revocation | retain as historical evidence; cannot alter current acceptance |
| Helper/provider unavailable | affected consultation remains unavailable; no unapproved paid fallback |
| Bot workspace reset | reconstruct from current source and binding; no company state loss |
| Grok memory disagrees with source | source wins; memory is corrected or ignored |
| Empty Prophet/signal result | distinguish valid no-signal output from missing run/input/publication using the owning product contract |
| Strategic/Chairman-reserved decision | durable pending obligation to the correct owner; Grok must not decide it |

## 11. Deployment topology

```text
Mastermind host / existing Executive services
  ├─ Executive Runtime + Wake ledger
  ├─ W6-C consultation runtime and Company Dialogue carrier
  ├─ authenticated Company Consultation HTTP app
  ├─ existing OAuth / audit / service supervision
  └─ outbound Grok routine client
          |
          | HTTPS POST + bearer key, opaque nudge only
          v
Cursor cloud / dedicated Grok user
  └─ Grok Operations Bot
       ├─ webhook routine
       ├─ durable role description / skill
       └─ authenticated custom Company Consultation MCP
          |
          | HTTPS Streamable MCP + OAuth
          v
Mastermind Company Consultation app
```

The Bot cloud computer is optional working context. No local Mastermind source checkout is required for the first canary. OpenClaw and #188 remain optional later local/host actuation and are not dependencies of the cloud-only Grok loop.

## 12. Implementation waves and dependencies

1. **C0 — W6-C runtime acceptance:** repair #615 on its existing carrier and protect one canonical Wake/effect/result interface. Required closure includes protected-schema compatibility, real current-writer composition, exact Wake/provider causality, one effect reducer, authoritative RuntimeBinding evidence, exact available-to-consumed answer identity, and atomic answer/consumption budgets.
2. **G1a — provider-free Grok Wake adapter:** may proceed in parallel because it depends only on the already-protected generic Wake contract. It must remain unregistered, unarmed, network-free, and incapable of claiming delivery or target consumption.
3. **G1b — bounded HTTP client:** may follow G1a with injected transport/secret seams and no checked-in target, credential, routine, or production registration.
4. **C1 — external reasoning-surface version:** after C0, add `grok-bot` to the next unused consultation schema version with exact compatibility tests.
5. **G2 — Grok target/registry composition:** bind the adapter only after C0/C1, keep the transport descriptor false and target disabled.
6. **G3 — remote Company Consultation app:** authenticated four-tool HTTP composition using existing auth/audit/service owners; no CEO app change.
7. **G4 — capability and installation package:** sealed profile, dedicated service/tunnel config, Bot description/skill/routine artifacts, and secret-free attestation.
8. **G5 — account setup and read-only qualification:** one dedicated Bot, connector/tool inventory, OAuth, usage/overflow inspection, routine saved but inactive until negative tests pass.
9. **G6 — real return canary:** exact Wake -> HTTP 200 -> exact recipient consumption -> exact answer availability -> matching requester consumption, plus duplicate/stale/late/effect-unknown failures.
10. **G7 — one economical helper:** current Router/Capacity selects one qualified peer; validate answer and one bounded correction if naturally required.
11. **G8 — event-driven operational responsibility:** enable one narrow event/routine after proof; no timer/polling storm.
12. **G9 — delegated operational continuation:** grant only closed repair/continue/park classes under #612 after identity/effect proof.
13. **G10 — Control Room and ROI promotion:** expose truthful state; scale only after measured accepted value and no authority defects.

Each wave must be independently useful, separately reviewed, and separately proven. Source merge, install, provider acceptance, answer arrival, parent consumption, production proof, and final Sol acceptance remain distinct.

## 13. Acceptance ruler

The first complete useful capability is:

```text
real admitted returned-work obligation
-> exact Grok RuntimeBinding and Wake route
-> one webhook POST accepted by intended routine
-> Grok resolves current bounded context
-> Grok produces a valid Company Consultation answer
-> W6-C records recipient consumption and answer availability
-> current requester consumes it
-> visible/machine next action is correct
-> Grok can be unavailable afterward without losing company state
```

Required negative proofs: pre-submit unavailable, non-200, post-submit `EFFECT_UNKNOWN`, late-result reconciliation, duplicate delivery, changed payload conflict, wrong binding generation, revoked grant, expired question, foreign requester/recipient/binding, same-message-key changed answer, available/consumed fingerprint mismatch, concurrent answer race, stale/late/corrected answer history, exhausted one-answer budget, Company MCP unavailable, Bot paused, included usage exhausted, and helper invalid output.

ROI is accepted useful outcomes per scarce principal/human effort. Measure existing telemetry/evidence owners for human interventions, parent-consumption latency, first-pass acceptance, repairs, false escalations, missed actionable obligations, Grok usage basis, helper usage/cost, duplicate effects, and authority violations. Do not infer per-run savings from an account-wide usage meter when concurrent work exists.

## 14. Holds and no-rebuild rules

- Do not modify or activate #188 from this carrier. Reconcile its current head/body/install facts on its own carrier before any optional local-actuation use.
- Do not widen the five-tool Executive app with Company Consultation.
- Do not create a Grok callback database, provider router, account store, event queue, retry loop, memory plane, or Control Room source of truth.
- Do not claim `grok-computer` implemented until source, install, real provider call, negative cases, and production proof are separately satisfied.
- Do not treat a webhook 200, routine run record, Bot message, custom-MCP tool visibility, process exit, Slack post, or PR merge as company completion.
- Do not assign a helper/provider from prompt text. Existing placement owners select the least-scarce lawful route.
- Do not enable on-demand usage or purchased-credit overflow from this design. Action-time budget authority remains separate.
- Do not require Grok or Workspace Agents for deterministic transitions or direct bounded worker tasks.

## 15. Exact next action

The next implementation dependency is **C0: repair #615 on its existing carrier and close exact review `5196352060`**. The protected interface must preserve old schemas, reuse the canonical Wake/current-writer path, authenticate exact provider evidence, expose one coherent effect reducer, and enforce exact/atomic answer availability and consumption.

In parallel, only the provider-free Grok Wake dispatcher and bounded HTTP client may advance because they depend solely on the already-protected generic Wake protocol. They remain unregistered, unarmed and incapable of target or completion claims. Contract versioning, target/registry composition, remote Company Consultation composition, account/Bot setup and every canary remain held until C0. After C0, allocate `grok-bot` to the next unused schema version and continue the gated sequence.

## 16. Primary external references observed 2026-09-14

- Grok Bot plans and non-stacking grants: https://cursor.com/help/grok-bot/plans
- Grok Bot routines/webhook semantics: https://cursor.com/help/grok-bot/routines
- Shared cloud computer and minimal roster: https://docs.x.ai/grok-bot/overview and https://docs.x.ai/grok-bot/bots
- Security and per-user/Bot boundaries: https://docs.x.ai/grok-bot/security-faq
- Skills/routines trust guidance: https://docs.x.ai/grok-bot/skills-routines-and-automations
- Custom MCP public reachability and auth: https://docs.x.ai/grok/connectors/custom-mcp-tunneling and https://docs.x.ai/grok/connectors

These public contracts are time-sensitive capability evidence, not Mastermind entitlement, current account configuration, run proof, or authority.
