# Executive OS Phase 1G — Multi-Provider Agent Fabric Master Design

**Program:** Mastermind Executive OS / Agent OS  
**Program name:** Multi-Provider Agent Fabric  
**Status:** master architecture and commissioning baseline; **DESIGN ONLY — NO PRODUCTION ARMING**  
**Design date:** 2026-08-15  
**Repository base:** `mastermindx-market-intelligence/Mastermind@3823a2bb000946dc6d318ec1ba6f163d67046884`  
**Strategic objective:** `EXECUTIVE_OS` — durable CEO→COO→worker execution with resource-aware routing, persistence, verification, and failover  

---

## 0. Executive decision

Mastermind will build one durable, quota-aware, multi-provider agent execution fabric underneath the existing Executive OS.

The organization will use expensive frontier capacity primarily for executive reasoning, project leadership, architecture, difficult repair, and independent review. High-volume implementation will preferentially use larger or economically cheaper coding pools such as dedicated Codex Max accounts, GLM, Qwen, Cursor, and Grok Build, subject to capability, quality, plan terms, and live capacity.

This is **not** a second autonomous-agent framework beside Executive OS. Executive OS SQLite remains the only authority for Job, Attempt, Worker, capacity assignment, process/session identity, checkpoint, result, review, and lifecycle events. Agent OS remains the cross-session knowledge plane in Macro `agentos/`. The Improvement Agenda remains the sole canonical company priority queue.

The operating model is:

```text
Chairman Chris
      ↓
ChatGPT Business workspace / Sol CEO seat
      ↓ bounded objective
Executive OS durable parent Job
      ↓
Fable / Opus / Sol-class project leader
      ↓ bounded plan and child-job proposal
Executive OS authority + policy validation
      ↓
Capacity Router
      ↓
provider + account + pool + model + worker slot + execution runtime
      ↓
Codex / Qwen / GLM / Cursor / Grok / Claude worker Attempt
      ↓
checkpoint + result + validation + independent review
      ↓
project leader aggregation or bounded repair
      ↓
Executive Inbox exception only when bounds or authority require it
```

The project leader orchestrates. It does not remain alive as a costly polling daemon and does not brute-force all implementation itself.

---

## 1. Source law and architecture boundary

This design is subordinate to, in order:

1. `research/MASTERMIND_CHARTER_V2.md`;
2. `config/strategic_state.yml`;
3. `config/authority_map.yml`;
4. the accepted parent Job / CEO directive;
5. `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`;
6. current code and verified evidence.

The following existing laws remain binding:

- **Charter P2:** missing, stale, or contradicted information shrinks capability; it never expands it.
- **Charter P3/P8:** new routing authority and provider integrations earn authority in shadow before live use.
- **Charter P7:** one source of truth per concept.
- **Charter P10:** deployment and real-host verification are part of completion.
- **One lifecycle authority:** no sidecar job database, queue, lease service, router ledger, or tmux-owned lifecycle.
- **Agent OS is knowledge only:** no dispatch, scheduling, liveness, quota gating, or priority ranking in Macro `agentos/`.
- **Improvement Agenda owns priority:** placement ranks eligible execution capacity; it never decides what the company should do next.
- **Labels confer no authority:** model, role, skill, seat, provider, impact, and priority labels do not grant capabilities.
- **Production MCP writes remain unavailable** until their separately reviewed identity and principal gates pass.

---

## 2. Current and planned capacity topology

The present constraint is that ChatGPT and Claude frontier subscriptions are too valuable and too quickly exhausted when used simultaneously as project leaders and implementation labor.

The capacity fabric must represent these as separate resource families:

| Surface | Account/pool boundary | Claimable by worker router? | Default organizational use |
|---|---|---:|---|
| ChatGPT Business workspace | current Business account and Workspace Agents agentic pool | **No** | Sol CEO seat, workspace-level orchestration, executive interaction |
| Dedicated Codex Max accounts | multiple separate personal accounts, each on the operator-described 20× Max entitlement | **Yes** | code implementation, hard repair, architecture/review where justified |
| Claude | each independently authenticated subscription account/pool | Yes, reserve-constrained | Fable/Opus leadership, architecture, hard review, difficult repair |
| Grok Build | xAI/SuperGrok weekly pool; separate from Cursor | Yes | implementation and research-heavy coding |
| Cursor Ultra | Cursor monthly pools; separate from Grok Build | Yes | everyday senior implementation and review |
| Z.AI GLM Max | planned purchase; rolling 5-hour and 7-day horizons | Yes after adapter acceptance | primary high-volume implementation, secondary technical lead after evaluation |
| Alibaba Token Plan Team Edition | planned purchase; assigned-seat monthly Credits pool and optional shared pack | `operator_assisted` until terms are resolved | Qwen/GLM/other implementation inside permitted tools |

### 2.1 ChatGPT Business is not a Codex worker pool

OpenAI documents that Codex and Workspace Agents share agentic usage **when they use the same ChatGPT plan/account**. That does not imply sharing across the user's separate accounts. The current topology intentionally separates them:

```text
ChatGPT Business account
  capacity domain: executive_workspace
  worker_claimable: false
  purpose: Sol + Workspace Agents

Codex Max account 01
  capacity domain: worker_execution
  worker_claimable: true
  provider home: dedicated
  quota state: independent

Codex Max account 02..N
  same contract, independently metered and authenticated
```

The exact number of dedicated Codex accounts is operator-managed inventory, not guessed in source. Every account becomes a distinct `provider_account`, `capacity_pool`, credential reference, and worker slot. A Codex limit on one account must not mark any other Codex account—or the Business workspace account—limited.

### 2.2 Provider terms are routing constraints

Provider plan details are volatile. Exact limits, model allowlists, reset times, and terms are runtime observations/configuration rather than hard-coded architectural truths.

Two current restrictions are load-bearing:

1. Z.AI Coding Plan benefits are restricted to officially supported tools/products; a private SDK or unsupported backend must not consume that subscription.
2. Alibaba Token Plan Team Edition currently describes interactive use through compatible programming/agent tools and prohibits automated scripts or application backends. Until written provider clarification or a separately reviewed interpretation exists, Team Edition is `operator_assisted`, not `autonomous_allowed`. Fully autonomous Qwen execution may use a lawful pay-as-you-go/API entitlement instead.

The router enforces these compliance modes rather than treating purchased credentials as universal execution authority.

---

## 3. Master design laws

### L1 — Executive SQLite remains the only lifecycle authority

Every durable Job, Attempt, Worker slot, capacity assignment, session identity, checkpoint, result, review, and placement receipt lives in the existing Executive runtime schema and immutable event stream.

### L2 — Capacity placement is deterministic policy, not an LLM judgment

A model may propose an agent profile and constraints. It may not select raw credentials, silently change reserve policy, or invent remaining quota. Candidate filtering and ranking are deterministic and receipt-producing.

### L3 — Priority and placement are different

The Improvement Agenda and accepted directives determine which work matters. The Capacity Router only determines where an already-eligible Job can run.

### L4 — Model, role, skill, authority, account, and runtime are separate dimensions

```text
Agent instance
= model
+ agent profile
+ skill bundle
+ Job context
+ authority receipt
+ capacity pool
+ worker slot
+ execution runtime
```

No monolithic `Fable-CTO-account-3` identity becomes governance truth.

### L5 — Same model/different pool is the first failover preference

On pool exhaustion, the router first tries the same logical worker/model through another lawful account or entitlement. Only then may it move to an equivalent model family, a peer intelligence class, or an explicitly permitted lower class.

### L6 — No silent intelligence downgrade

A Job declares an intelligence floor and whether degradation is permitted. Architecture, security, high-impact review, and CEO work default to `degrade_allowed=false`.

### L7 — Frontier reserve is explicit

ChatGPT workspace and Claude pools may carry reserve floors for executive exceptions, architecture, independent review, and rescue. The ChatGPT Business seat is not worker-claimable at all. Ordinary worker placement cannot consume protected capacity without an allowed override.

### L8 — Unknown capacity is not zero and not infinite

Capacity observations carry confidence: `exact`, `provider_reported`, `estimated`, `failure_inferred`, or `unknown`. Unknown capacity can be used under conservative concurrency and reserve rules, but never represented as a fabricated percentage.

### L9 — All governing horizons must be healthy

One entitlement can have multiple simultaneous limits: rolling five-hour, weekly, monthly, concurrency, credits, or provider risk controls. A candidate is runnable only when every required governing horizon is eligible.

### L10 — A provider/account switch creates a new Attempt

The same Attempt never migrates between credentials or providers. The prior Attempt becomes terminal or LOST/RATE_LIMITED, its workspace is sealed, a handoff/checkpoint is persisted, and a fresh Attempt starts in a fresh workspace.

### L11 — Structured protocols outrank pane scraping

JSON/JSONL, ACP, SDK streams, stable exit codes, and provider session IDs are preferred. tmux is a persistent PTY/runtime and operator-observation layer, not lifecycle truth and not the primary parser when a structured interface exists.

### L12 — No generic model-facing terminal control

Models do not receive arbitrary `tmux send-keys`, shell, credential selection, or session-name tools. They request typed child Jobs. Trusted adapters issue bounded low-level commands after authority and placement.

### L13 — One writer per worktree

Every write-capable child Job receives a separate exact-SHA worktree. Provider-native subagents may fan out read-only analysis inside one Attempt, but parallel writing becomes Executive child Jobs with independent worktrees and leases.

### L14 — Leaders are ephemeral

A persistent deterministic orchestration cycle observes canonical state. Fable/Opus/Sol-class leaders are invoked only for planning, aggregation, repair, or escalation transitions. Their chat context is not company state.

### L15 — Independent review is first-class

Material work requires a review Job. At minimum the reviewer must have a different `worker_id`; policy may require a different account or provider where capacity permits.

### L16 — Skills confer competence, never authority

A Fable orchestration skill, CTO skill, design skill, or worker skill changes instructions and tools within the already-granted envelope. It cannot grant WRITE_BRANCH, RUN_TESTS, network, merge, deployment, credentials, or broader paths.

### L17 — Credentials never enter public state

SQLite and events store opaque credential references, account labels, and non-secret metadata only. Token values, OAuth state, browser cookies, provider homes, and secret-bearing command lines remain outside public projections and are redacted from logs.

### L18 — Provider terms are a routing gate

Every account and pool has a compliance mode. A pool marked `operator_assisted` or `supported_cli_only` is refused for placements that violate that mode even when capacity is available.

### L19 — Every placement is explainable

The selected candidate and every rejection are persisted in a bounded placement receipt tied to the Job/Attempt and policy version.

### L20 — Shadow before authority

New telemetry sources, pool classifiers, routing policies, adapters, failover, and orchestration loops run against fixtures and shadow recommendations before live dispatch.

---

## 4. Target architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                       CEO / MCP surface                      │
│  Business Workspace Agents read state and submit bounded     │
│  intent; no raw worker credentials or generic terminal tools │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     Executive OS runtime                     │
│ Jobs · Attempts · Workers · Events · authority · worktrees  │
│ parent/child trees · reviews · checkpoints · results          │
└───────────────┬───────────────────────────┬──────────────────┘
                │                           │
                ▼                           ▼
┌──────────────────────────┐   ┌───────────────────────────────┐
│ deterministic COO cycle  │   │ Capacity Registry + Router    │
│ plan / collect / review  │   │ accounts / pools / horizons   │
│ repair / aggregate       │   │ observations / reserves       │
└───────────────┬──────────┘   │ deterministic placement       │
                │              │ placement receipts            │
                └──────────────────┬────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                      Worker-slot broker                      │
│ typed launch · heartbeat · checkpoint · input · interrupt    │
│ collect · cancel · reconcile · whole-slot absence proof       │
└───────────────┬─────────────────┬─────────────────┬──────────┘
                ▼                 ▼                 ▼
       Structured process        ACP               PTY/tmux
       Codex / Claude /          Grok               fallback,
       GLM / Qwen / Cursor                           attach/debug
                │                 │                 │
                └─────────────────┴─────────────────┘
                                   ▼
                         isolated exact-SHA worktree
```

---

## 5. Canonical data model

The exact schema migration numbers must follow Phase 1F-B. The concepts below are additive extensions of the existing runtime, not a parallel store.

### 5.1 `provider_accounts`

Represents one purchased or configured provider identity.

```text
account_id                 stable non-secret identifier
provider                   openai | anthropic | xai | cursor | zai | alibaba | ...
plan_name                  descriptive plan identity
account_label              operator-readable non-secret label
capacity_domain            executive_workspace | worker_execution | cloud_worker
worker_claimable           boolean
licensed_principal         assigned subscriber/seat label
credential_ref             opaque protected reference, never secret bytes
compliance_mode            autonomous_allowed | supported_cli_only |
                           operator_assisted | api_only | disabled
status                     ONLINE | DRAINING | OFFLINE | AUTH_FAILED | ERROR
metadata_json              non-secret plan/region/tool facts
created_at / updated_at
```

### 5.2 `capacity_pools`

Represents one separately consumed entitlement bucket.

```text
pool_id
account_id
provider
entitlement_kind           subscription | credits | api_budget | bonus | shared_pack
model_allowlist_json
execution_backends_json
routing_rank
reserve_class
reserve_floor
max_concurrency
status
metadata_json
```

Examples:

```text
chatgpt-business.workspace-agentic     # non-claimable executive seat
codex-max-01.agentic-20x                # claimable worker pool
codex-max-02.agentic-20x                # independent claimable worker pool
anthropic-main.subscription
xai-heavy-01.supergrok-weekly
cursor-ultra-01.first-party
cursor-ultra-01.api-agents
zai-max-01.coding-plan
alibaba-team-01.monthly-seat-credits
alibaba-team.shared-pack-01
```

### 5.3 `capacity_horizons`

Represents one governing meter within a pool.

```text
pool_id + horizon_id
meter_kind                 calls | prompts | credits | currency | tokens |
                           compute_units | concurrency | opaque
limit_value
consumed_value
remaining_value
remaining_ratio
window_started_at
reset_at
status                     AVAILABLE | RESERVED | SOFT_LIMIT | RATE_LIMITED |
                           CONCURRENCY_LIMITED | AUTH_FAILED | POLICY_DISABLED |
                           OFFLINE | UNKNOWN
confidence                 exact | provider_reported | estimated |
                           failure_inferred | unknown
source                     dashboard | cli | plugin | headers | error | operator | estimate
observed_at
```

### 5.4 `capacity_observations`

Append-only evidence used to update pool/horizon projections.

```text
observation_id
pool_id / horizon_id
observation_type
value_json
source
confidence
job_id / attempt_id
reset_hint
observed_at
```

An observation never contains credential values or raw unsanitized provider text.

### 5.5 Worker slots

The existing `workers` and `worker_quota_classes` remain the execution-capacity registry. They gain or reference:

```text
account_id
pool_id
slot_id
execution_runtime
adapter_id
provider_home_ref
max_parallel_attempts
health / last probe
```

A worker slot is a real isolation boundary, not an abstract model name.

For dedicated Codex accounts, the initial mapping is one worker slot per account:

```text
_mastermind_codex_01 → CODEX_HOME_01 → codex-max-01.agentic-20x
_mastermind_codex_02 → CODEX_HOME_02 → codex-max-02.agentic-20x
...
```

This preserves independent credentials and prevents a whole-UID cleanup for one account from killing another account's process.

### 5.6 `placement_receipts`

```text
placement_id
job_id
attempt_id
policy_version
candidate_set_sha256
selected_worker_id
selected_pool_id
selected_model_alias
selected_runtime
compatibility_tier
ranking_tuple_json
rejections_json
created_at
```

### 5.7 `session_handles`

```text
attempt_id
runtime_kind               process | acp | tmux | cloud
provider_session_id
pid / pgid / process_start_identity / boot_id
runtime_session_name
transcript_path
transcript_cursor
status
metadata_json
```

This augments, not replaces, the existing Attempt process identity.

### 5.8 Provider-neutral handoff

`mastermind.agent_handoff.v1` is a persisted artifact referenced by the Attempt:

```text
job_id
source_attempt_id
objective
acceptance_criteria
base_sha
checkpoint_ref / patch_digest
branch
completed_steps
current_state
changed_files
commands_run
test_results
artifacts
open_questions
known_failures
next_actions
provider_session_reference
agent_profile
skill_bundle_digest
context_digest
created_at
```

Hidden reasoning is neither required nor copied. The next worker receives explicit state, repository changes, acceptance criteria, and bounded evidence.

---

## 6. Agent profiles and skill bundles

### 6.1 Machine-readable profiles

A later wave adds `config/agent_profiles.yml` with profiles such as:

```text
executive_orchestrator
project_lead.engineering
project_lead.design
project_lead.marketing
systems_architect
implementation.senior
implementation.fast
research.deep
research.scout
qa.engineer
independent_reviewer
```

Each profile declares competence requirements, not authority:

```text
profile class
intelligence floor
required capabilities
preferred model aliases
allowed fallback policy
allowed child profiles
maximum fan-out/depth
review policy
skill bundle defaults
```

### 6.2 Model aliases

The catalog uses stable capability aliases rather than volatile provider version strings:

```text
frontier.orchestrator
frontier.engineering
senior.engineering
standard.engineering
fast.engineering
research.deep
research.fast
```

Provider adapters resolve aliases to currently allowed exact model IDs under reviewed configuration.

### 6.3 Canonical skills

Skills live once and are exported to provider-specific layouts:

```text
skills/fable-orchestration/
skills/mastermind-architecture/
skills/bounded-delegation/
skills/python-implementation/
skills/adversarial-review/
skills/product-design/
skills/marketing-strategy/
```

Every skill carries a manifest, `SKILL.md`, compatible profiles/models, required tools, forbidden authorities, evaluation fixtures, and version/digest.

The Fable-derived skill is an experimental methodology bundle. It must be evaluated separately on Opus, Sol, GLM, Qwen, and other leaders; no model is declared “Fable-like” by prompt alone.

---

## 7. Deterministic placement policy

### 7.1 Job placement request

A Job requests a logical execution shape:

```text
agent_profile
intelligence_floor
required_capabilities
preferred_model_aliases
fallback_policy
degrade_allowed
reserve_override_class
provider allow/deny constraints
cost class
context affinity
```

A Job does not normally request a raw account or secret.

### 7.2 Eligibility filters

A candidate is removed when any of the following holds:

- worker slot not ONLINE/AVAILABLE;
- `worker_claimable=false` (therefore the ChatGPT Business workspace seat is never selected);
- account compliance mode incompatible with the requested automation;
- provider/model/backend not allowed by the Job;
- missing required capabilities;
- authority or path scope cannot be honored;
- any hard governing horizon is RATE_LIMITED, AUTH_FAILED, POLICY_DISABLED, OFFLINE, or stale beyond policy;
- concurrency limit reached;
- intelligence floor not met;
- frontier reserve would be breached without an allowed override;
- continuation requires state the adapter cannot lawfully import;
- review-independence rule would be violated.

### 7.3 Compatibility tiers

```text
T0 CONTINUE
same provider session + same worker + healthy pool

T1 EXACT_POOL_FAILOVER
same exact model/profile, different lawful account or pool

T2 FAMILY_PEER
same provider/model family and intelligence class

T3 CROSS_PROVIDER_PEER
different provider, same profile and intelligence class

T4 EXPLICIT_DEGRADE
lower intelligence class only when degrade_allowed=true

T5 ESCALATE
no eligible candidate; return to leader/inbox
```

For Codex, T1 means moving from `codex-max-01` to another healthy dedicated Codex Max account—not to ChatGPT Business.

### 7.4 Ranking tuple

After filtering, candidates are ordered lexicographically by:

```text
compatibility tier
compliance mode
intelligence-floor satisfaction
reserve-floor impact
hard capacity health
continuation/context affinity
task-class evaluation score
remaining-capacity confidence
remaining ratio or conservative load proxy
active concurrency
marginal cost class
latency class
stable pool_id / worker_id tie-break
```

The first candidate is atomically claimed through the existing lease/fence path. A race restarts placement against fresh state.

---

## 8. Failure, checkpoint, and failover

### 8.1 Typed failure vocabulary

Adapters normalize provider/runtime failures to:

```text
RATE_LIMITED
CONCURRENCY_LIMITED
AUTH_FAILED
POLICY_REFUSED
TRANSIENT_PROVIDER_ERROR
MODEL_REFUSAL
CONTEXT_EXHAUSTED
WORKER_CRASH
SESSION_LOST
VALIDATION_FAILED
USER_INPUT_REQUIRED
CANCELLED
UNKNOWN
```

Only quota/capacity failures cool capacity horizons. A bad test result must not mark an account exhausted.

### 8.2 Failover transaction

```text
active Attempt
→ receive typed failure or supervisor loss
→ persist final structured event and latest checkpoint
→ terminate/reconcile runtime and prove child absence
→ seal workspace
→ persist provider-neutral handoff (or degraded supervisor-built handoff)
→ terminalize Attempt
→ update capacity observation/horizon if applicable
→ requeue same Job within attempt limit
→ deterministic placement on fresh state
→ create fresh workspace and fresh Attempt
→ apply checkpoint/patch/handoff
→ run validation and continue
```

No two Attempts are current for one Job. No two worker slots own the same worktree.

### 8.3 Anti-thrashing laws

- hard-limited pools cannot be retried before reset unless a new provider-reported observation clears them;
- a failed pool receives a cooldown/failure penalty;
- the router cannot bounce immediately between two equivalent failing pools indefinitely;
- Job attempt limits and root-tree repair limits remain binding;
- a provider switch is visible in the placement receipt;
- unresolved handoff or workspace integrity failure escalates rather than improvises.

---

## 9. Execution runtimes and adapters

### 9.1 Common adapter contract

```text
probe()
prepare(LaunchSpec)
start()
read_events(cursor)
send_input(TypedInput)
checkpoint()
interrupt()
collect()
cancel()
reconcile()
```

Adapter output is normalized to common events:

```text
SESSION_STARTED
ASSISTANT_MESSAGE
TOOL_STARTED
TOOL_FINISHED
FILE_CHANGED
CHECKPOINT
USAGE_OBSERVATION
APPROVAL_REQUIRED
RATE_LIMITED
AUTH_FAILED
RESULT
SESSION_ENDED
```

### 9.2 Structured process runtime

Preferred for Codex, Claude Code/GLM, Qwen Code, and Cursor CLI when their non-interactive structured modes are sufficient.

Properties:

- process identity and stdout/stderr paths remain durable;
- JSON/JSONL is parsed incrementally;
- fixed wall-clock, turn, tool, and output bounds are supervisor-owned;
- provider session IDs are persisted;
- resume is allowed only through typed adapter methods.

### 9.3 ACP runtime

Preferred first-class runtime for Grok Build where ACP provides stable JSON-RPC session control and incremental updates.

### 9.4 tmux runtime

Use for genuine interactive/PTY requirements, provider defects, long-running steerable sessions, and operator attachment.

Rules:

- one tmux server/session namespace per worker isolation principal;
- session name derived from Attempt identity;
- no session without a durable current Attempt and lease;
- transcript continuously copied to a bounded file/event stream;
- `capture-pane` is diagnostic evidence, not completion truth;
- arbitrary tmux commands are never exposed through MCP or authored by a worker model;
- restart adoption validates worker UID, tmux server identity, session name, pane PID, process start identity, and worktree before rotating the Attempt fence.

### 9.5 Cloud runtime

A later adapter may support Grok Bot, Cursor Cloud Agents, or other remote workers. GitHub branch/PR state is a handoff surface, not a replacement lifecycle database.

---

## 10. Provider adapter plan

### ChatGPT Business workspace

- remains the Sol/workspace-agent executive surface;
- is registered as non-claimable `executive_workspace` capacity;
- is never selected for ordinary child implementation;
- may later expose bounded capacity awareness to the CEO seat without becoming a worker credential.

### Dedicated Codex Max accounts

- retain the native structured process approach and secure supervisor pattern;
- provision one dedicated OS worker principal and `CODEX_HOME` per account initially;
- treat each 20× Max account as an independent pool/horizon set;
- exact-model failover rotates among these accounts first;
- no account shares credential state, provider home, whole-UID sweeps, or quota status;
- account count is operator inventory and can grow without schema changes.

### Anthropic / Claude

- reuse structured Claude Code/SDK output where reliable;
- generalize current key-rotor cooling evidence into provider-independent capacity observations;
- default use: leader, architecture, hard review, repair;
- ordinary worker placement requires reserve policy clearance.

### Z.AI / GLM Max

- use an officially supported tool path such as Claude Code configured to the Z.AI endpoint;
- do not use a private unsupported SDK with the Coding Plan entitlement;
- model rolling five-hour and seven-day horizons independently;
- begin with one dedicated subscriber/worker slot and conservative concurrency;
- first planned new high-volume worker after fixture acceptance.

### Alibaba / Qwen

- Qwen Code headless JSON/stream-JSON is the preferred technical adapter;
- Token Plan Team Edition account begins `operator_assisted` due current plan language;
- autonomous canaries use a lawful API/PAYG entitlement or wait for provider clarification;
- monthly seat Credits and shared packs are separate pools/horizons;
- one assigned seat/key maps to its licensed principal and is never shared across people.

### xAI / Grok Build

- represent Grok Build as an xAI weekly pool separate from Cursor but shared with other SuperGrok product usage;
- prefer ACP or streaming JSON;
- normalize provider session and usage events rather than scraping a TUI.

### Cursor Ultra

- use Cursor CLI print mode with stream-JSON and resumable session IDs;
- represent first-party/model and API-agent allowances as separately observed pools where the account surface distinguishes them;
- keep one conservative worker slot until measured concurrency and allowance behavior are proven.

---

## 11. Provider-native subagents

Provider-native subagents are useful for read-only research, bounded analysis, and parallel searches inside one Attempt.

They do not replace Executive child Jobs for parallel writing. In particular, Qwen fork subagents currently share the parent working directory and do not automatically feed their result back into the parent. Writing fan-out therefore uses Executive child Jobs and separate worktrees.

A project leader may propose child profiles; only Executive OS creates, validates, routes, leases, and aggregates those children.

---

## 12. Security and isolation

The current Phase 1C-A whole-UID cleanup is valid only for one exclusive worker identity. Multi-provider concurrency therefore requires one dedicated principal per concurrent worker slot, for example:

```text
_mastermind_codex_01
_mastermind_codex_02
_mastermind_glm_01
_mastermind_qwen_01
_mastermind_cursor_01
_mastermind_grok_01
```

Each slot has:

- a dedicated provider home and credential boundary;
- a dedicated broker socket;
- one active Attempt unless separately accepted otherwise;
- independent process/session reconciliation;
- access only to its assigned worktree and run directory;
- no direct DB, control service, unrelated credentials, other provider homes, merge, deploy, or production state authority.

No provider adapter may weaken the current allowed capability set (`READ`, `RESEARCH`, `WRITE_BRANCH`, `RUN_TESTS`) or bypass `ExecutiveAuthorityPolicy`.

---

## 13. Acceptance proof for the architecture

The central canary is one parent Job with provider failover:

```text
Parent JOB
  ↓
Attempt 1 on low-cost/high-capacity worker pool
  ↓ injected or real typed RATE_LIMITED
checkpoint + handoff + sealed workspace
  ↓
Attempt 2 on exact-model/different-pool if available,
otherwise same-class peer provider
  ↓ completion + supervisor validation
  ↓
independent review Job on different worker
  ↓
parent aggregation
```

The proof passes only if:

- exactly one parent Job exists;
- Attempts name actual account, pool, model, adapter, and worker slot;
- ChatGPT Business is absent from the worker candidate set;
- no two writers touch one live worktree;
- the first workspace becomes inaccessible to its old worker;
- checkpoint/handoff survives provider/account change;
- the second worker does not repeat completed work unnecessarily;
- capacity cooling is durable and pool-specific;
- placement receipts explain every selection and rejection;
- credentials never appear in SQLite, events, logs, artifacts, or MCP output;
- parent completion is refused until required independent review approves;
- restart reconstructs the same state.

---

## 14. Explicit non-goals for this design PR

This PR does not:

- change the Executive runtime schema;
- add a live provider credential;
- install or authenticate GLM, Qwen, Cursor, Grok, Claude, or another Codex account;
- add production dispatch or MCP write authority;
- create a second queue or router service;
- run tmux under the existing single Codex worker UID;
- arm automatic provider failover;
- allow a model to choose credentials or raw terminal commands;
- modify Phase 1C-A host state;
- supersede the Phase 1F orchestration contract.

The implementation sequence and individual merge gates are defined in `research/EXECUTIVE_OS_PHASE1G_MASTERPLAN_AND_WAVES.md`.