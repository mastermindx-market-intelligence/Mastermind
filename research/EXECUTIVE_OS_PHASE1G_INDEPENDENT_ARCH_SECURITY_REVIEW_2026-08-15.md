# Executive OS Phase 1G — Independent Fresh-Context Architecture & Security Review

**Reviewer role:** independent fresh-context architecture / security / distributed-systems review. Did not author any Phase 1G document.
**Review date:** 2026-08-15
**Target:** PR #66 — Executive OS Phase 1G: Agent Fabric + Workspace CEO autonomy design
**PR head verified:** `d64349f22327474ec2d862aa8a36bf97a507cc70`
**Design branch:** `codex/executive-agent-fabric-masterplan-20260815` → resolves to the same commit; head had not moved at review time.
**Merge base / master:** `3823a2bb000946dc6d318ec1ba6f163d67046884`
**Verdict:** **BLOCK**

---

## 0. Method and evidence classes

All repository claims below were verified against the checked-out PR head, not against the PR description or document summaries. External product claims were checked against current primary vendor documentation on the review date.

Evidence classes used throughout:

- **[REPO]** — source-law or code fact verified in this repository at the stated commit.
- **[EXT]** — verified against current primary vendor documentation.
- **[INF]** — architecture inference by this reviewer.
- **[UNRES]** — unresolved assumption; not safe to make load-bearing.

### 0.1 What the design gets right

This is a strong design and the review should not obscure that. Specifically:

- The three-stage attention pipeline with `final_route = max(mandatory_floor, semantic_promotion, policy_promotion)` and **no** `semantic_demotion` term (amendment E2/E4) is a correct and elegant solution to the LLM-suppression problem. I attempted to construct a demotion path through compression (E7), deferral (E6), triage outage (E5), and recursion (E19) and could not find one **at the design level**.
- Separating wake path (trigger API) from state/action path (MCP) is correct, and C10's insistence that they fail independently is right.
- The activation generation/fence plus the additive activation **claim** (F4/E9/§7) correctly distinguishes duplicate *writes* from duplicate *cognition burn*. Most designs miss the second.
- E10 (technical completion ≠ strategic closure) and E13–E15 (immutable commission artifact, two-phase publication, GitHub as provenance not queue) are the right decompositions.
- G0-A is **satisfied as a factual matter [REPO]**: the diff against merge-base is 8 added files, 5,217 insertions, all under `research/`, all markdown. Zero code, schema, config, credential, scheduler, or MCP changes. Confirmed by `git diff --name-status 3823a2bb d64349f2`.

The blocking findings below are not about the attention pipeline. They are about **the authority substrate the pipeline is asserted to sit on, which does not currently exist**, and about **a transport identity assumption that current primary evidence contradicts rather than merely leaves open**.

---

## 1. BLOCKING findings

### B1 — `chairman_required` and "delegated CEO authority" have no canonical definition, and Phase 1G is the phase that was supposed to create it

**Severity:** BLOCKER
**Affects:** Amendment §3.2 (Chairman-required floor), §9 (Chairman authorization gateway), E11; Autonomy track C8, C9, §5.2 R3_CHAIRMAN, invariant 14; Master design §1 source-law list.

**Repository evidence [REPO]:**

- `config/authority_map.yml` contains **zero occurrences** of `chairman`, `ceo`, or `coo` (verified by grep over all 570 lines).
- The A0–A7 ladder terminates at **`A7 FABLE_HUMAN` — "Irreversible or cross-book change; requires Fable/human approval."** There is no Chairman level and no CEO level.
- `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md` §2 states directly: *"The executive hierarchy (Chairman Chris → CEO Sol → COO Fable → workers) exists **in prose only**: `AGENTS.md`/`CLAUDE.md` § 'Executive contract'. Nothing machine-reads seat occupancy today."*
- The same section prescribes the remedy and its trigger: *"**Smallest canonical representation, for a LATER phase (proposed, not built):** a `seats:` block inside `config/authority_map.yml` … with an explicit `authority: none` marker. **Implement only when something must machine-read seat occupancy (the CEO-wake mechanism above 1F-C is the first plausible consumer).**"*

**Failure scenario:** Phase 1G *is* the CEO-wake mechanism — precisely the consumer Phase 1F named. Phase 1G references `authority_map.yml` exactly twice in 5,217 lines: once in a precedence list, once as *"other decisions reserved by Charter or `authority_map.yml`"*. It never commissions the `seats:` block or any CEO authority-ceiling definition. It uses "delegated CEO authority" as a load-bearing boundary seven times.

Consequently, at X3-A the implementer must decide what `hard_floor = chairman_required` means with no canonical source. Whatever they write becomes, by default, the definition of Chairman-reserved authority — authored by an implementation session rather than by the Chairman. Phase 1F anticipated exactly this drift: *"do NOT create a seat registry casually. The failure mode is drift: a `seats.yml` quietly becomes an authority surface."*

**Violated invariant:** Amendment §3.2 "No model self-declares new Chairman authority categories" and E20 "labels confer no authority." Both are unenforceable without a canonical, versioned, Chairman-ratified authority definition. The *deterministic* half of the deterministic/semantic split is undefined at its most security-critical boundary.

**Already prevented by current design?** No. The design asserts the floor is deterministic; it does not define, locate, or commission the policy object that would make it so.

**Required correction:** Add a commission (naturally X3-A-0 or an authority-map amendment wave) that produces, before any attention-floor fixture work is accepted:
1. the `seats:` block in `config/authority_map.yml` in the minimal form Phase 1F prescribed, with `authority: none`;
2. an explicit, versioned, conformance-tested enumeration of Chairman-reserved decision categories and CEO delegated ceilings, in `authority_map.yml` (the already-reviewed, test-asserted governance file), **not** in a new file;
3. an explicit ruling on B3/Phase-1F §6 Q3.

**Gate:** **Before G0.** This is not deferrable to a later wave, because every downstream artifact (X3-A floor fixtures, X5 write census, X7 promotion gates) is specified relative to a boundary that does not yet exist.

---

### B2 — the "sole canonical company priority queue" is a derived, advisory, non-mutable artifact; committing a CEO priority mutation to it is not possible

**Severity:** BLOCKER
**Affects:** Master design §1 and L3; Autonomy track C9, §7.3, invariant 15; Amendment E10, §10.

**Design claims:** Master design §1 — *"The Improvement Agenda remains the sole canonical company priority queue."* Autonomy track C9 — *"Sol submits a typed agenda/project operation and Executive OS validates and commits the priority mutation through the existing canonical priority source."* Invariant 15 — *"autonomous discoveries become projects only through the Improvement Agenda/accepted strategic-state authority; no shadow priority queue exists."*

**Repository evidence [REPO]:** `brain/improvement_agenda.py` (79 KB) declares itself in its own module docstring:

- a **fusion engine over accountability artifacts** — calibration deltas, journal lesson clusters, shadow-vs-live gaps, benchmark-ledger gaps, validation-run verdicts, experiment maturities, cost_guard spend, armory/deploy-lag, distill drift;
- it **regenerates**: `agenda.write()` builds and persists `data/agenda/<date>.json` + `AGENDA.md`. The only persistence entrypoint in the module is `write()`. There is no insert, upsert, or mutate API;
- it is explicitly *"display/advisory **ONLY**: it NEVER trades, NEVER flips a flag, NEVER mutates a seat. It ranks and writes"*;
- its `owner` vocabulary is `{self-tunable, opus-session, fable-review}` — no CEO/Sol owner;
- its scope is trading-model self-audit, not Executive OS project priority.

And `config/strategic_state.yml` [REPO] declares `authority: advisory_and_orientation_only`, states *"It is not a control plane, a scheduler, or a job queue, and no runtime behavior keys off it,"* and names four *separate* owners: *"control_plane/ owns job governance, config/authority_map.yml owns the A0-A7 authority ladder, config/agents.yml owns seats and model routing, brain/improvement_agenda.py owns the ranked work queue."*

**Failure scenario:** Sol, under X6, detects a capability gap and emits `AGENDA_CHANGE_SUBMITTED`. Executive OS attempts to "commit the priority mutation through the existing canonical priority source." There is no such write path. The implementer has exactly three options, and all three are architecture failures:

1. write into `data/agenda/<date>.json` — **erased on the next `agenda.write()` rebuild**; the CEO's priority decision silently evaporates;
2. amend `config/strategic_state.yml` — but it is `advisory_and_orientation_only` with `no runtime behavior keys off it`, so the mutation is inert and cannot gate execution;
3. create a new durable executive-priority store — **which is precisely the "shadow priority queue" invariant 15 forbids, the "second control plane" `strategic_state.yml` marks `duplicate_control_planes: prohibited`, and the Charter P7 violation the design cites as binding.**

**Violated invariant:** Charter P7 (one source of truth per concept); `strategic_state.yml constraints.duplicate_control_planes: prohibited`; Autonomy track invariant 15; Master design L3.

**Additional defect:** the design repeatedly writes the compound *"Improvement Agenda / accepted strategic state"* as though it were one authority. Source law defines them as two artifacts with different owners, different scopes, and different regeneration semantics. Treating them as interchangeable is itself a P7 ambiguity — when they disagree about company priority, the design provides no precedence rule.

**Already prevented by current design?** No. The design assumes a mutable canonical priority authority exists. It does not.

**Required correction:** Before G0, the design must state explicitly which artifact is the canonical *mutable* executive-priority authority, and either (a) demonstrate an existing governed write path into it, or (b) commission its creation as a first-class, reviewed, Charter-P7-adjudicated change to a *named existing* store — with an explicit ruling that this is not a second control plane, and a conformance test enforcing it. Until then C9, §7.3, E10, §10, and invariant 15 are unimplementable as written.

**Gate:** **Before G0** for the adjudication and precedence ruling. Implementation may follow at X3-B/X5.

---

### B3 — Phase 1F §6 open questions marked "do not build past these" are unreferenced and at least four are built past

**Severity:** BLOCKER
**Affects:** Amendment §3.1 (mandatory CEO floor), E17; Master design L15; G0 acceptance index §1 precedence claim.

**Repository evidence [REPO]:** `EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md` §6 is titled *"Open questions requiring a CEO ruling (do not build past these)"* and lists six. Grep across all eight Phase 1G documents returns **zero** references to Phase 1F §6, "open question", or "CEO ruling."

Four are load-bearing for Phase 1G:

| 1F §6 | Question | How Phase 1G builds past it |
|---|---|---|
| Q1 | `authority_map.yml` `coo_cycle_policy` bounds/ceilings acceptable? | Amendment §3.1 makes *"bounded COO repair/attempt/review ceilings exhausted"* a **mandatory CEO floor trigger**. The floor's first listed trigger depends on ceilings that have not been ruled on. |
| Q3 | Seat registry: defer, or order it earlier? | See B1. Phase 1G is the named trigger and does not answer. |
| Q4 | Is different-`worker_id` sufficient for independence, or must it be different `provider`/`account_label`? | Master design L15 and Amendment E17 adopt "different `worker_id` minimum; provider/account **where capacity permits**" — resolving an open question by fiat, as a soft preference. |
| Q6 | Review-independence starvation: escalate, or may the CEO waive independence? | Unaddressed, and **made worse** by the new E17 dissent reviewer (see H5). |

**Violated invariant:** G0 acceptance index §1: *"Nothing here overrides the higher source law: … Phase 1F contract."* An explicit "do not build past these" is higher source law, and the design builds past it silently.

**Already prevented by current design?** No — the design does not acknowledge the questions exist.

**Required correction:** The G0 acceptance index must add a gate item requiring each Phase 1F §6 question to be either (a) Chairman/CEO-ruled and recorded, or (b) explicitly shown non-load-bearing for Phase 1G. Q1, Q3, Q4, Q6 must be ruled before G0; Q2 and Q5 are 1F-internal and can be marked non-blocking for 1G.

**Gate:** **Before G0.**

---

### B4 — Secure MCP Tunnel caller identity is more likely REFUTED than UNKNOWN, and the design's fallback is a single uncommissioned sentence

**Severity:** BLOCKER
**Affects:** Autonomy track §9.3, §4.5, invariant 5; Amendment §8.3 (`CHAIRMAN_DIRECT`), E12; G0-C rows 15–18, 21, 23; masterplan G10; Workspace CEO evidence register §4.

**External evidence [EXT]** — current OpenAI Secure MCP Tunnel documentation:

- *"tunnel-client authenticates to the OpenAI tunnel control plane; supported OpenAI products use the OpenAI-hosted tunnel endpoint."*
- *"**Tunnel permissions are organization-level, not project-level.**"*
- The tunnel identity is a **`tunnel_id` plus a Platform runtime API key** (`CONTROL_PLANE_TUNNEL_ID` / `CONTROL_PLANE_API_KEY`).
- One tunnel serves **ChatGPT, Codex, the Responses API, and AgentKit** — *"The same tunnel-backed MCP server can power ChatGPT connectors, Codex sessions, and Responses API."*
- No documented mechanism propagates a per-caller workspace/app/agent/user principal to the private MCP server. Identity is asserted at the *tunnel*, not per request.

**Failure scenario [INF]:** The gateway receives an MCP JSON-RPC call over the tunnel. On current evidence it cannot distinguish among:

1. the autonomous Sol Workspace Agent under a live activation;
2. Chris in an ordinary interactive ChatGPT session;
3. **any Codex session anywhere in the same Platform organization** that attaches the tunnel;
4. **any Responses API call** made with that tunnel configured.

All four present identically as "the tunnel." The design's own law is that authority must derive from trusted transport identity and *never* from model-supplied correlation fields (§4.4: *"The server derives caller authority from trusted transport/platform identity and canonical policy — **not** from these model-supplied correlation fields"*). If transport identity is org-uniform, then **there is no authority differentiation available at all**, and:

- §4.5 interactive-session ratification cannot distinguish an interactive session from an autonomous one;
- §8.3 `CHAIRMAN_DIRECT` cannot be ratified, because the transport cannot prove the interactive principal is the Chairman rather than any org principal;
- X5 production write arming is not merely *gated* — it is **architecturally unreachable through this transport** without an additional authorization layer;
- the activation fence degrades from a security boundary to a correctness boundary. It still prevents *stale* and *duplicate* writes (which is real value), but it cannot prevent an *unauthorized org principal* from claiming an activation and issuing CEO writes, because the fence's inputs are exactly the model-supplied fields the design says confer no authority.

**Violated invariant:** Autonomy track invariant 5 ("production writes prove authorized Workspace/App caller identity from trusted evidence"); PR #64 R6 caller-identity gate; masterplan G10.

**Already prevented by current design?** **Partially, and in the right direction.** §9.3 does say *"If the transport cannot convey trustworthy caller identity to the local gateway, production writes remain blocked and a separate auth layer must be designed."* That is the correct fail-closed posture and it is why this is a BLOCKER rather than a catastrophe.

But the design treats this as a binary unknown to be resolved by an X0 canary, when current primary evidence already indicates the likely answer is negative. The consequence is a **plan-shaped defect**: X5, X6, X7, G10, and the entire production-write half of the program are sequenced behind a capability that probably does not exist, and the alternative ("a separate auth layer") is one sentence — not commissioned, not scoped, not gated, not in the wave plan, not in the dependency graph.

**Required correction:**
1. Reclassify the tunnel identity assumption from `STILL_UNKNOWN` to `LIKELY_REFUTED — pending X0-A canary`, and record the org-level-permission and multi-surface-reachability facts in the Workspace CEO evidence register §4.
2. Commission the fallback **now**, as a named design item (e.g. X1-B "gateway-level authorization layer"): an application-layer authenticator the gateway can verify independently of the tunnel — for example a per-principal bearer secret injected into the published Workspace Agent's MCP connector configuration and never present in model-visible context, with replay resistance, rotation, and an explicit threat model for what an interactive org principal can and cannot obtain.
3. Add an X0-A row: *"can any non-Sol org principal (Codex session, Responses API call, interactive ChatGPT) reach the same tunnel and invoke the same MCP surface?"* Expected result REFUTED-or-PROVED materially changes X5.

**Gate:** Reclassification and commissioning of the fallback: **before G0.** The auth layer itself: before X5/production arming.

---

## 2. HIGH findings

### H1 — `tunnel-client` is not a pure transport: it embeds Harpoon, an MCP server with configurable HTTP egress into the private network

**Severity:** HIGH · **Affects:** Autonomy track §9.1–§9.2, infrastructure design §13 threat model.

**[EXT]** Current OpenAI documentation: *"tunnel-client includes an embedded MCP server, **Harpoon**, that exposes configured HTTP targets by label and lets callers invoke them through the tunnel with bounded request/response limits."* OpenAI is explicit that it is not a general-purpose proxy — targets and methods are customer-configured — but it *is* a customer-configurable egress path from OpenAI-side callers into the private network, shipped inside the same binary.

The design asserts *"The tunnel client is transport. It is not a scheduler, queue, database, authority source, or worker"* and grants it least privilege. That characterization is incomplete: as shipped, tunnel-client is transport **plus a latent bounded HTTP proxy**. Nothing in the design forbids Harpoon targets, and the threat model does not mention it.

**Failure scenario:** an operator configuring the tunnel for the Executive MCP gateway also registers a convenience Harpoon target (a health endpoint, an internal API). That target is now invocable from any OpenAI-side caller that reaches the tunnel — inheriting B4's identity ambiguity, and bypassing the Executive MCP gateway's entire typed-operation and authority surface.

**Required correction:** Add to the infrastructure design §13 threat model and to the X1-A acceptance criteria an explicit invariant: **the Mastermind tunnel profile registers zero Harpoon targets**, verified in the acceptance receipt, with drift detection on the tunnel profile. Add the tunnel-client profile to the config-integrity/inventory-digest regime (infrastructure §3.2).
**Gate:** before X1-A live spike.

### H2 — provider-side conversation concurrency on `conversation_key` is unmodeled; `Idempotency-Key` does not cover it

**Severity:** HIGH · **Affects:** Autonomy track §4.1, §4.2; amendment §7.

**[EXT]** The trigger API's `Idempotency-Key` dedupes *the same trigger event*: *"Requests to the same API trigger with the same key return the original accepted outcome instead of adding a second trigger event to the queue."* `conversation_key` is a separate, caller-defined field for *"continuing the same agent conversation across multiple trigger events."* There is no documented concurrency control on a conversation.

**[REPO/design]** §4.2 recommends *"one key per durable executive/project scope rather than one immortal company-wide thread."*

**Failure scenario [INF]:** Activation A (superseded after a reasoning escalation, §5.3) and successor activation B share a project-scoped `conversation_key`. Two *distinct* trigger events with *distinct* idempotency keys land in the *same* conversation. Idempotency does not apply — they are different events. The activation claim prevents B and a duplicate-of-B from both becoming current cognition owners, but it does not prevent A's superseded reasoning from being **in-context for B**. Worse, if A is still generating, provider-side interleaving in a single conversation is undefined.

The design's fence correctly stops A from *writing*. It does not stop A from *contaminating B's reasoning context* — and B's output is authoritative. This is a subtle authority-widening path: superseded executive reasoning re-enters a live activation as apparently-canonical conversation history.

**Required correction:** Add to X3-A: (a) conversation-key rotation is **mandatory** on supersession, escalation, and drain — not merely "may be rotated when context becomes stale"; (b) an invariant that at most one non-terminal activation may be bound to a given `conversation_key`; (c) an X0-A row measuring provider behavior under two concurrent triggers sharing one `conversation_key`.
**Gate:** X3-A design; X0-A evidence row before X6.

### H3 — the trigger credential is a user-shared principal, not a service identity; CEO wake has an undeclared human-account dependency

**Severity:** HIGH · **Affects:** Autonomy track §10 (trigger dispatcher/secret boundary), C1, §11.1; G0-C row 4.

**[EXT]** Workspace Agent access tokens are provisioned from `Admin > Access tokens` with the Workspace Agents scope, and explicitly *"Do not use an OpenAI Platform API key."* Error semantics: `403 Forbidden` — *"The token is valid but does not have permission to trigger the requested workspace agent"*; the cookbook's remediation is *"Share the agent with the caller or use a token from an allowed user"*, and its failure row reads *"Token from unshared user."*

The token therefore carries a **user principal**, and the agent must be *shared with* that user. Sol's wake path depends on a specific human account's continued existence, entitlement, and share relationship to the published agent.

**Failure scenario:** the account whose token drives the dispatcher is deprovisioned, loses the Workspace Agents scope, or the agent's sharing audience is narrowed during an unrelated admin change. Every autonomous CEO wake begins returning `403`. Under §11.1 this is an authentication refusal → retry/backoff → cooldown. The organization goes quiet, and the failure looks like a transient provider problem rather than an identity-lifecycle event.

**Required correction:** (a) model the trigger principal explicitly in the credential-boundary section as a *user-scoped* credential with a named owning account and a share dependency on the published agent; (b) add `403` as a **distinct non-retryable class** requiring operator attention, separate from `401` and `429`; (c) add G0-C rows for token lifetime, rotation, revocation, and agent-share-audience drift; (d) add share-audience change to the C14 config-drift invalidation list.
**Gate:** X0-A evidence; dispatcher design at X3-A.

### H4 — `suspended` is the machine-visible signature of approval-blocking, but C11 declares run status advisory, leaving no non-advisory detector

**Severity:** HIGH · **Affects:** Autonomy track C11, §11.2, §4 state machine; amendment §16.

**[EXT]** The beta run-status endpoint reports `suspended` = *"The agent is waiting for an external action or tool"*; terminal statuses are `completed` and `failed`, with `error.code` ∈ {`dispatch_failed`, `run_failed`}.

**[REPO/design]** §11.2 lists *"app write confirmation blocks unattended completion"* as a failure to handle. C11 declares beta telemetry advisory and says the loop must be correct without it.

**Failure scenario:** an approval prompt blocks Sol mid-activation. The run sits `suspended`. Because run status is advisory-only, Executive OS has no signal at all — it waits out `activation_deadline` and lands in `EXPIRED_UNRESOLVED`. For the entire deadline window the activation holds the single-owner claim for its scope (E9), so **no other CEO cognition can proceed on that scope**, and under §4.3 overlapping-scope serialization the blockage propagates. A single mis-set approval toggle silently freezes an executive scope for one full deadline period, repeatedly, with no distinguishing telemetry.

The design is *correct* not to make canonical completion depend on run status. But "advisory" has been over-applied: telemetry may safely be used to **shorten a failure path** without ever being used to **declare success**. Those are different privileges.

**Required correction:** Permit run status to serve as a *negative/diagnostic* signal only — a `suspended` observation may raise an operator/Inbox exception and may shorten claim reconciliation, but may never produce `COMPLETED`. State this asymmetry explicitly in C11 (it currently reads as a blanket prohibition). Add an X0-A row for approval-driven `suspended` behavior, and add a first-class `APPROVAL_BLOCKED` diagnostic to §11.2.
**Gate:** X3-A design; before X5 arming.

### H5 — E17 dissent review reintroduces Phase 1F §6 Q6 independence starvation, and degrades silently

**Severity:** HIGH · **Affects:** Amendment E17, §11.2; Master design L15; Phase 1F §6 Q6.

E17 requires a read-only independent critic for policy-selected high-impact actions, and says *"Where capacity permits, the dissent reviewer should differ by worker/provider/account from the primary reasoning route."* "Where capacity permits" is a **silent-degradation clause** on a security control.

**Failure scenario:** on the actual near-term host (infrastructure §14 sequences a *single* Codex slot first, adding accounts one at a time), capacity frequently does not permit. The critic then runs on the same provider/account — and for the highest-value case, plausibly the same model family as Sol. A same-model critic is substantially correlated with the primary reasoning route and will systematically miss the same class of error, while producing a `CLEAR` verdict that satisfies the gate and creates *documentary evidence of independent review that was not independent*. That is worse than no critic, because it launders the decision.

This is exactly Phase 1F §6 Q6, which recommended *"escalate; no waiver vocabulary in v1"* — and E17 effectively adopts the opposite default without ruling on it.

**Required correction:** Make the degradation explicit and fail-closed: if the policy-required independence class is unavailable, the outcome is a typed `dissent_unavailable` disposition that either defers the action or escalates to Chairman attention — never a `CLEAR`. Add a `critic_independence_class` field to the dissent result so a same-account critique is never recorded as independent. Adjudicate against 1F §6 Q6 (B3).
**Gate:** before G0 for the fail-closed rule (it is a one-line invariant); implementation at X2/X5.

---

## 3. MEDIUM findings

**M1 — Charter principles are generalized from a trading constitution to agent orchestration without saying so.** [REPO] `MASTERMIND_CHARTER_V2.md` is a *trading* constitution: P2 is "Wrong data shrinks, never flips" about allocation authority and direction; P3 is the signal-promotion ladder; P8 is shadow-earned autonomy for seats/signals/books/levers. Master design §1 restates these as governing routing authority, provider integrations, and lifecycle. The generalizations are reasonable and in the right spirit, but they are **[INF] architecture inference presented as [REPO] source law**. Related: the Charter's authority line names *Fable* as program owner, and A7 is `FABLE_HUMAN` — yet Phase 1G places Fable **below** Sol as COO. This role inversion needs an explicit Chairman ruling, not silent adoption. *Correction:* label the generalizations as inference, or amend the Charter to state agent-orchestration applicability. *Gate:* before G0 (cheap; it is a labeling and one ruling).

**M2 — "Sol" collides with an existing model identifier.** [REPO] In `config/agents.yml`, `sol` is a *model* (`gpt-5.6-sol`) to which **all five** reasoning roles resolve, including `fable`. Phase 1G uses "Sol" as the CEO *seat*. Phase 1F §2 already flagged this exact over-claim as a docs-only correction owed to `AGENTS.md`. Doing seat-registry work (B1) on top of an unresolved name collision is how label-derived authority gets in. *Correction:* disambiguate seat-name vs model-id before the `seats:` block lands. *Gate:* with B1.

**M3 — `dispatch_failed` vs `run_failed` is not mapped to retry policy.** [EXT] These are materially different: `dispatch_failed` means the run never started (retry is safe); `run_failed` means the agent ran and failed (retry risks duplicate cognition and, if the agent partially committed, duplicate effect). §11.1 treats trigger failures generically. The activation claim covers this incidentally via expiry/reconciliation, but the mapping should be explicit rather than emergent. *Gate:* X3-A.

**M4 — the executive-attention case store is scheduler-adjacent, and its non-queue status is asserted rather than enforced.** Amendment §5 defines a relation with `status: OPEN|DEFERRED|ACTIVATED|RESOLVED|SUPERSEDED`, `revisit_at`, reopen-on-expiry semantics, and a strategic heartbeat that periodically re-evaluates it. Functionally that is a durable prioritized work store with a timer. The design says *"This is **not a second work queue**"* — but says it by declaration. Given `duplicate_control_planes: prohibited` [REPO] is a standing constraint, declaration is not enough. *Correction:* add an explicit invariant that **nothing dispatches from attention state** (attention state may only produce CEO activations via the Wake Router, never Jobs, never placements), plus a conformance test. *Gate:* X3-A.

**M5 — three distinct credential trust domains are treated as one "secret boundary."** [EXT] The Workspace Agent trigger uses a `api.chatgpt.com` **Workspace Agent access token** (user-scoped, ChatGPT admin-issued, explicitly *not* a Platform key). The tunnel uses a **Platform** `tunnel_id` + runtime API key under **organization-level** permissions, and best practice separates the daemon's Read+Use key from a manager's Read+Manage key. §10 models these as one undifferentiated "trigger credential / tunnel runtime credential." *Correction:* model three domains with separate rotation, revocation, and blast-radius statements; adopt the Use/Manage key split explicitly. *Gate:* X0-A / X1-A.

---

## 4. LOW / NONBLOCKING

- **L1** — The Workspace CEO evidence register §1 correctly captures the Help-Center-vs-developer-reference discrepancy (I verified both surfaces; **the discrepancy is real and accurately characterized**), but omits the beta terminal-status set, the `suspended` state, `error.code` values, and the `403/404/409` semantics. Add for completeness.
- **L2** — The xAI Grok Build ACP/headless claim was not independently re-verified in this review. It is correctly non-load-bearing (C2, E3, invariant 20), so this is nonblocking; re-verify at W9.
- **L3** — G0-C row 11 can be partially resolved now: the live trigger request body contains only `input` and `conversation_key` [EXT], with no model or reasoning-effort field. Option A ("dynamic effort externally selectable") is therefore already effectively refuted for the documented endpoint, leaving Option B (separate published routes) as the only viable path to R2_PRO. The register can state this affirmatively rather than leaving it fully open.
- **L4** — Master design §2.1's claim that Codex and Workspace Agents share agentic usage only *within* the same plan/account is asserted from OpenAI documentation but is the kind of plan-terms fact the design itself marks volatile (§2.2). It is correctly handled as runtime configuration; flagging only so it is re-checked at W6 rather than inherited.

---

## 5. Attacks attempted that the design withstood

Recording these so a later session does not redo them, and so the BLOCK is not misread as a rejection of the attention architecture.

| Attack | Result |
|---|---|
| Semantic demotion of a hard floor via direct assessment | **Held.** E2's `max()` has no demotion term; §6 router checks `hard_floor` before consulting semantics. |
| Demotion via compression — bury a critical event behind an earlier routine disposition | **Held.** E7 requires severity-monotonic coalescing and full source-event lineage; a stronger event promotes or supersedes. |
| Demotion via deferral — park a material case indefinitely | **Held.** E6 requires expiry/revisit, strategic-review inclusion, and reopen-on-contradictory-evidence; §5.2 explicitly forbids an indefinite shelf. |
| Demotion via triage outage / malformed / stale / low-confidence output | **Held.** E5 fails upward to CEO for material cases. |
| Triage recursion — triage job's own lifecycle events create new triage cases | **Held.** E19 explicitly excludes them. |
| Assessor emits instruction-shaped `recommended_next_action` that executes | **Held.** §4.2 forbids execution of the text; E16 makes it evidence. |
| Stale Sol conversation issues a late second directive | **Held at design level.** §4.4 activation fence with generation + terminal-state checks. (Transport caveat: B4.) |
| Duplicate trigger delivery causes duplicate expensive cognition | **Held.** §7 activation claim; acceptance explicitly measures duplicate *runs*, not only duplicate writes. |
| Free-form Slack text becomes approval | **Held.** E12; `Discuss` ≠ `Approve`; delivery failure leaves request PENDING. |
| Stale Slack click approves a superseded commission | **Held.** §9.4 supersedes rather than applying approval to different bytes. |
| Editing the commission file after directive acceptance mutates the accepted project | **Held.** E14/§8.2 pin `commit_sha` + blob/content digest; HEAD substitution forbidden. |
| Artifact published, directive submission lost | **Held.** E15 two-phase; orphan artifact is inert; idempotent recovery. |
| `Job COMPLETED` silently closes the strategic objective | **Held.** E10/§10 invariant. |
| GitHub PR state used as work queue | **Held.** E14; master design §9.5 restates for cloud runtimes. |
| One account's rate limit contaminates sibling accounts / the executive seat | **Held.** Infrastructure §6.4, §12; `worker_claimable=false` on ChatGPT Business is enforced at the eligibility filter, not by convention. |
| Model selects credentials or raw tmux argv | **Held.** L12, L17, infrastructure §8.3, §13. |
| Cross-project conflict via different `root_scope_id` | **Held as design intent.** F9/§12 `affected_scope_keys` with fail-closed to one owner when independence is not establishable. Adequacy depends on X3-A's actual key derivation, which does not exist yet — re-attack at X3-A. |

---

## 6. Required explicit determinations

| Question | Answer | Evidence |
|---|---|---|
| More than one **lifecycle authority**? | **NO** | L1 and Autonomy track invariant 1 keep Job/Attempt/activation state in Executive SQLite. §17 forbids sidecar attention DB, semantic queue, and Grok-owned store. X3-B explicitly forbids a sidecar. |
| More than one **production scheduler**? | **NO** *(with M4 caveat)* | C13 and invariant 2 make Executive OS the sole production schedule owner; Workspace Agent built-in schedules are excluded from production. Caveat: the attention-case store's `revisit_at` + heartbeat is scheduler-adjacent and its non-queue status is asserted, not enforced (M4). |
| More than one **company-priority authority**? | **YES** | The design names a compound *"Improvement Agenda / accepted strategic state"* authority. [REPO] source law defines these as two separate artifacts with different owners (`strategic_state.yml` header), both marked advisory, with no precedence rule between them and no mutation path into either (B2). |
| Hidden **semantic-model suppression authority**? | **NO** | E2/E4 monotonic `max()`; §6 router consults `hard_floor` before semantics; §3.1 states the assessor is not asked whether hard floors should disappear; X7 requires zero hard-floor demotion as a zero-tolerance metric. This is the design's strongest element and survived every attack in §5. |
| **Chairman-authorization bypass**? | **UNRESOLVED** | The Slack/typed-action/supersession design (E11, E12, §9) is sound. But `chairman_required` has no canonical definition (B1) and the transport cannot currently distinguish the Chairman from any org principal (B4). The gateway is well-designed around a boundary that is not yet defined or provable. |
| **Stale/duplicate CEO-write path**? | **NO at design level; UNRESOLVED at transport level** | §4.4 fence + §7 claim + §4.6 atomic completion + idempotency are correct against staleness, duplication, and crashed claimants. However, per B4, the fence's inputs are model-supplied correlation fields whose *authority* depends on a transport identity that may not exist — so the fence is currently a correctness control, not an access control. |
| Route to **autonomous constitutional self-modification**? | **UNRESOLVED** | C8, §7.2, §17, and X7 ("keep constitutional/governance/security files outside autonomous write authority") state the prohibition clearly and repeatedly. But there is no machine-readable protected-path set, no enumerated constitutional file list, and — per B1 — no canonical definition of the authority boundary being protected. The prohibition is prose enforced against an undefined boundary. |

---

## 7. Verdict

# BLOCK

Phase 1G's executive-attention architecture is, in my assessment, correct on the hardest problem it set out to solve: a probabilistic model cannot suppress mandatory executive attention, and I could not construct a path that makes it possible. The activation/claim/fence model is sound. The commissioning and provenance design is sound. G0-A is factually satisfied.

The design is blocked not on what it built, but on **what it assumed already existed**.

Three of the four blockers share one root cause: **Phase 1G specifies an authority architecture against a canonical authority substrate that the repository does not contain.** `authority_map.yml` has no CEO, no Chairman, no seats. The Improvement Agenda is a regenerated advisory artifact with no mutation API. `strategic_state.yml` is advisory-only by its own declaration. Phase 1F saw this coming, named Phase 1G as the phase that would have to fix it, and marked six questions "do not build past these" — and Phase 1G does not cite them once. The fourth blocker is different in kind: the production-write half of the program is sequenced behind a transport identity capability that current primary vendor evidence suggests does not exist, with an uncommissioned one-sentence fallback.

None of this is unrecoverable, and none of it requires redesigning the attention pipeline. B1, B2, and B3 are adjudication and commissioning work, not architecture rework. B4 requires committing to an authorization design that the program will almost certainly need regardless.

---

## 8. Exact handoff to the architecture-authoring session

Do not merge PR #66. Do not weaken any gate. Do not begin X1/X2/X3 fixture work that assumes a CEO-authority boundary, a mutable priority authority, or tunnel-borne caller identity.

**Adjudicate before G0 can be re-reviewed:**

1. **B1 — authority substrate.** Commission the `seats:` block in `config/authority_map.yml` per Phase 1F §2's prescribed minimal form (`authority: none`), **plus** a versioned, conformance-tested enumeration of Chairman-reserved decision categories and CEO delegated ceilings. In `authority_map.yml`, not a new file. Everything referencing "delegated CEO authority" or `chairman_required` must cite it.
2. **B2 — priority authority.** Rule which artifact is the canonical *mutable* executive-priority authority. State the precedence rule between the Improvement Agenda and accepted strategic state. Either demonstrate an existing governed write path or commission its creation with an explicit Charter-P7 / `duplicate_control_planes` adjudication and a conformance test. Rewrite C9, §7.3, E10, §10, and invariant 15 against the answer.
3. **B3 — Phase 1F §6.** Rule Q1, Q3, Q4, Q6. Record the rulings. Add a G0 index gate item requiring every prior-phase open question to be ruled or shown non-load-bearing.
4. **B4 — transport identity.** Reclassify to `LIKELY_REFUTED — pending X0-A`. Record the org-level-permission and multi-surface-reachability facts in the evidence register §4. Commission the gateway-level authorization layer as a named, scoped, gated design item. Add the "can any non-Sol org principal reach this tunnel" X0-A row.
5. **H5 — dissent independence.** Adopt the fail-closed rule now (one invariant): unavailable independence class yields `dissent_unavailable` → defer or Chairman attention, never `CLEAR`.
6. **M1/M2 — naming and lineage.** Rule on the Fable-A7-vs-COO inversion. Disambiguate the Sol seat/model collision before any seat-registry work.

**Fold into the next design revision (not G0-blocking):** H1 Harpoon prohibition + drift detection; H2 conversation-key rotation invariant; H3 trigger-principal lifecycle and `403` class; H4 the advisory-telemetry asymmetry (`suspended` may shorten failure, never declare success); M3 error-code retry mapping; M4 attention-store non-dispatch invariant + test; M5 three credential trust domains; L1/L3 register updates.

**Re-review scope after adjudication:** the four blockers, H5's invariant, and a fresh attack on X3-A's `affected_scope_keys` derivation once it exists — that is the one design-intent item in §5 whose adequacy could not be assessed because the mechanism is not yet specified.
