# Executive OS Phase 1G — Agent Fabric Masterplan and Wave Plan

**Program:** Multi-Provider Agent Fabric  
**Status:** commissioned; Wave 0 design branch active; production behavior unchanged  
**Program base:** `3823a2bb000946dc6d318ec1ba6f163d67046884`  
**Design branch:** `codex/executive-agent-fabric-masterplan-20260815`  
**Master design:** `research/EXECUTIVE_OS_PHASE1G_AGENT_FABRIC_MASTER_DESIGN.md`  
**Primary strategic objective:** `EXECUTIVE_OS`  

---

## 0. Program outcome

Build a durable execution fabric that lets Mastermind use:

- ChatGPT Business Workspace Agents as the protected CEO/workspace surface;
- multiple separate Codex Max accounts as independent high-capacity coding pools;
- Claude as scarce Fable/Opus leadership, architecture, difficult repair, and review capacity;
- Grok Build and Cursor Ultra as independent implementation pools;
- Z.AI GLM Max as a planned high-volume worker pool;
- Alibaba/Qwen as a planned worker pool under a compliance-gated integration;
- future providers without redesigning the lifecycle authority.

The end state is a bounded hierarchy:

```text
CEO objective
→ project leader plan
→ Executive child Jobs
→ deterministic account/pool placement
→ isolated worker Attempts
→ checkpoint/failover
→ independent review
→ bounded repair
→ aggregation or executive exception
```

Frontier agents lead and review. Worker pools implement. Executive OS owns truth.

---

## 1. Current baseline

### Already shipped

- durable SQLite Worker / QuotaClass / Job / Attempt / Event runtime;
- atomic claim, lease, heartbeat, fencing, checkpoint, completion, rate-limit, LOST, requeue, and cancellation semantics;
- secure exact-SHA Codex worker path and macOS supervisor architecture;
- Executive Inbox read projection;
- Phase 1F hierarchical orchestration design;
- bounded CEO-intent bridge;
- bounded ChatGPT Executive MCP gateway in READONLY/FIXTURE modes.

### Not yet shipped

- successful final Phase 1C-A native-host acceptance at the latest reviewed SHA;
- Phase 1F-B parent/child Job schema and independent-review enforcement;
- provider-account and capacity-pool registry;
- provider quota telemetry and confidence model;
- deterministic placement receipts and shadow router;
- multiple isolated Codex account workers;
- GLM, Qwen, Cursor, and Grok Build adapters;
- provider-neutral handoff and automatic account/provider failover;
- generic session runtime and tmux fallback;
- machine-readable agent/skill catalog;
- Phase 1F-C bounded project-leader cycle;
- production MCP writes, dispatch, or CEO wake relay.

---

## 2. Program gates

No later wave may waive an earlier gate implicitly.

### G0 — Architecture baseline

Pass condition:

- master design and wave plan merged;
- independent architecture review finds no duplicate control plane, authority widening, secret path, priority inversion, or migration collision;
- no production behavior changed.

### G1 — Phase 1C-A real-host PASS

Pass condition:

- exact latest merge SHA installed;
- one fresh formal native-host acceptance passes;
- success, interruption/reconciliation, workspace seal, and absence receipts are valid;
- services return to the intended post-acceptance state.

Design and hermetic fixture work may proceed before G1. No new live provider worker may arm before G1.

### G2 — Phase 1F-B hierarchy/review PASS

Pass condition:

- parent/root/depth Job structure exists;
- parent claim with children is refused;
- aggregation before terminal children/review approval is refused;
- review independence is enforced;
- escalation fields and Inbox kinds ship;
- migration from the current populated schema is proven.

The first Phase 1G schema migration is based on the schema version produced by 1F-B.

### G3 — Capacity schema and inventory PASS

Pass condition:

- provider accounts, pools, horizons, observations, and placement receipts live in the existing Executive database;
- ChatGPT Business is represented as `worker_claimable=false`;
- each dedicated Codex Max account is an independent account/pool identity;
- no credential values enter database/events/projections;
- backup/restore and migration proofs pass.

### G4 — Shadow telemetry PASS

Pass condition:

- provider observations can be ingested without affecting dispatch;
- stale, absent, contradictory, and malformed telemetry degrade visibly;
- provider-specific limits update only the correct account/pool/horizon;
- exact, provider-reported, estimated, failure-inferred, and unknown confidence classes are distinguishable.

### G5 — Shadow router PASS

Pass condition:

- router recommendations are deterministic from canonical state;
- every rejection and selection is explainable;
- same-model/different-account ranks first;
- ChatGPT Business never appears as a claimable candidate;
- reserve and compliance rules are enforced;
- shadow recommendations cannot affect live claims.

### G6 — First multi-account live worker PASS

Pass condition:

- at least two dedicated Codex Max accounts run under different worker principals and provider homes;
- quota/rate-limit state is independent;
- cancelling or sweeping one cannot affect the other;
- exact-model account failover succeeds in a controlled canary.

### G7 — New-provider worker PASS

Pass condition:

- GLM or Qwen worker executes through a supported and contract-compliant tool path;
- adapter emits the common event/result contract;
- credentials, provider home, process tree, and worktree are isolated;
- failure classification and capacity observation are correct;
- a different-provider independent review approves the result.

### G8 — Cross-provider failover PASS

Pass condition:

- typed rate limit terminates the first Attempt honestly;
- checkpoint/handoff is durable;
- fresh placement starts a new Attempt on a peer provider;
- old workspace is sealed;
- work is completed without duplicate current ownership;
- restart reconstructs the same state.

### G9 — Hierarchical orchestration PASS

Pass condition:

- one parent objective is planned by an ephemeral leader;
- bounded child Jobs are validated and created;
- children route through the capacity fabric;
- independent reviews and bounded repair run;
- parent aggregates only when runtime refusals permit it;
- bounds produce an Inbox exception rather than uncontrolled fan-out.

### G10 — Production ChatGPT control PASS

Pass condition:

- trusted ChatGPT Business caller identity is bound from transport/platform evidence;
- a least-privilege MCP principal can reach only the reviewed control operations;
- production submission/dispatch tools are separately reviewed and schema-pinned;
- no generic shell, credential, tmux, merge, deploy, or service-control path is exposed.

---

## 3. Wave dependency graph

```text
W0 Master design
 |
 +--> W1 Phase 1C-A acceptance closure -------------------------+
 |                                                              |
 +--> W2 Phase 1F-B hierarchy/review -----------------------+    |
                                                            |    |
W3 Capacity schema/inventory <------------------------------+----+
 |
W4 Capacity observations and provider probes (shadow)
 |
W5 Deterministic placement router (shadow)
 |
W6 Dedicated Codex multi-account worker fleet
 |
+--> W7 GLM worker adapter
|    W8 Qwen worker adapter / compliance-gated entitlement
|    W9 Grok Build + Cursor adapters
|        |
+--------+
         |
W10 Provider-neutral checkpoint/handoff and automatic failover
 |
W11 Structured session control + tmux fallback
 |
W12 Agent profiles, model aliases, skills, and evals
 |
W13 Phase 1F-C bounded leader orchestration
 |
W14 Production MCP control arm and CEO wake relay
```

W7–W9 can be developed in parallel after W5, but live arming remains serial per provider until its acceptance proof passes.

---

## 4. Wave plans

## W0 — Master architecture and commissioning baseline

**Purpose:** freeze the design laws and prevent implementation drift.

**Deliverables**

- `EXECUTIVE_OS_PHASE1G_AGENT_FABRIC_MASTER_DESIGN.md`;
- this masterplan;
- architecture decision table;
- threat/failure model;
- first implementation commissions;
- independent review findings and adjudications.

**No runtime files change.**

**Acceptance**

- branch based on exact `origin/master`;
- docs agree with Phase 1F and current authority map;
- separate ChatGPT Business and dedicated Codex accounts are explicitly modeled;
- design states which facts remain unverified/operationally supplied;
- merge as a documentation-only PR after independent review.

---

## W1 — Phase 1C-A final native-host acceptance

**Owner:** current Phase 1C-A lane; do not fold into Phase 1G code.

**Purpose:** prove the existing secure supervisor before multiplying workers.

**Work**

- install exact latest reviewed SHA;
- run UID-separated preflight;
- spend one formal acceptance;
- archive receipts;
- if failure occurs, repair only the observed boundary and rerun under the established single-acceptance discipline.

**Exit**

- Phase 1C-A is formally PASS, or Phase 1G live activation remains blocked.

---

## W2 — Phase 1F-B hierarchical Job and review runtime

**Purpose:** provide the durable project-tree substrate the fabric will route.

**Implementation**

- migrate Job schema with `parent_job_id`, `root_job_id`, `depth`, `owner_seat`, `escalation_target`, `business_impact`, `review_required`, `reviews_job_id`;
- add result verdict vocabulary;
- add parent/container claim refusal;
- add aggregation/review refusals;
- add review independence checks;
- add Inbox exception kinds and tree compression.

**Tests**

- populated migration and idempotency;
- cycle prevention and immutable parentage;
- review-of-review refusal;
- independence starvation and bounded escalation;
- no behavior change for childless Phase 1B Jobs.

---

## W3 — Capacity schema and account inventory

**Purpose:** make every provider account and separately metered entitlement first-class without routing on it yet.

**Implementation**

Add to the existing runtime:

```text
provider_accounts
capacity_pools
capacity_horizons
capacity_observations
placement_receipts
worker-slot pool references
```

Add a strict machine-readable inventory, likely:

```text
config/provider_accounts.yml
config/placement_policy.yml
```

Configuration stores only identifiers and protected credential references—never secrets.

**Required initial inventory shapes**

```text
chatgpt-business
  capacity_domain: executive_workspace
  worker_claimable: false

codex-max-01..N
  capacity_domain: worker_execution
  worker_claimable: true
  plan: operator-described 20x Max
  independent pool and provider home

claude-* / xai-heavy-* / cursor-ultra-*
  explicit account and pool identities

zai-max-01 / alibaba-team-01
  disabled or fixture until purchased/configured
```

**Acceptance**

- no credential material in fixture or projection;
- pool uniqueness and account foreign keys enforced;
- ChatGPT Business candidate exclusion structurally tested;
- multi-Codex-account independence tested;
- backup/restore preserves all new rows and events.

---

## W4 — Capacity observations and provider probes, shadow only

**Purpose:** observe capacity without changing dispatch.

**Implementation**

- provider-independent observation ingestion;
- projection from observations to current horizons;
- stale/contradictory/malformed handling;
- adapters/probes for existing Codex/Claude evidence first;
- GLM usage plugin/probe fixture;
- Qwen/Alibaba credit fixture;
- Cursor and Grok fixture parsers;
- Executive read projection for capacity state.

**Rules**

- raw provider text is sanitized before persistence;
- failures update only the named pool/horizon;
- unknown remains unknown;
- an `ok` event cannot clear a weekly hard limit unless provider rules or reset evidence permit it;
- probe failure never aborts unrelated Job execution.

**Acceptance**

- mutation tests for cross-account contamination;
- stale telemetry cannot steer the router;
- failure-inferred cooling has a named reset source;
- ChatGPT Business usage can be visible to the CEO but remains non-claimable.

---

## W5 — Deterministic placement router, shadow only

**Purpose:** replace “first matching quota class” with explainable ranked placement, initially without dispatch authority.

**Implementation**

- logical placement request on Jobs;
- eligibility filters;
- compatibility tiers T0–T5;
- lexicographic ranking tuple;
- frontier reserve and compliance gates;
- placement receipt generation;
- shadow comparison against current dispatcher.

**Acceptance scenarios**

1. Codex Max account 01 limited → account 02 selected;
2. one Codex account auth-failed → only that account removed;
3. ChatGPT Business healthy → still refused as worker;
4. same-model peer outranks cross-provider peer;
5. lower intelligence candidate refused when `degrade_allowed=false`;
6. unknown-capacity candidate remains eligible only under conservative policy;
7. material review requires independent worker/account/provider according to policy;
8. byte-identical canonical state yields byte-identical recommendation.

**Exit**

- shadow receipts collected on representative Job fixtures;
- no live claim path imports the router yet.

---

## W6 — Dedicated Codex multi-account worker fleet

**Purpose:** deliver immediate capacity scaling using already owned independent Codex accounts before depending on new purchases.

**Implementation**

- generalize the current Codex-specific worker config into an indexed worker-slot model;
- one macOS service identity, `CODEX_HOME`, config, socket, log root, and broker state per account;
- root-owned inventory maps slot → account → pool → exact binary/adapter;
- control service selects a typed slot from the router receipt;
- per-slot whole-UID sweep and absence proof;
- one active Attempt per slot initially;
- account-specific capacity observations and rate-limit cooling.

**Security law**

A Codex account credential/home is readable only by its dedicated worker principal. No shared worker UID, no shared `CODEX_HOME`, no account rotation by environment mutation inside a live process.

**Acceptance**

- two-account canary minimum;
- both can run independent harmless Jobs;
- one forced RATE_LIMITED event leaves the other AVAILABLE;
- cancellation/sweep of slot 01 cannot signal slot 02;
- same Job requeues from slot 01 to slot 02 as a fresh Attempt;
- ChatGPT Business remains untouched.

---

## W7 — GLM Max worker adapter

**Purpose:** add the first planned high-volume non-frontier worker pool.

**Implementation**

- officially supported Claude Code/ZCode path to Z.AI;
- dedicated provider home and worker principal;
- structured stream parser;
- five-hour and weekly horizons;
- usage-query integration where supported;
- GLM model aliases and capability declarations;
- common checkpoint/result/failure contract.

**Acceptance**

- fixture proof before purchase/auth;
- live harmless Job after G1 and plan setup;
- provider limit fixture cools correct horizon;
- no unsupported direct Coding Plan SDK;
- independent Codex or Claude review.

---

## W8 — Qwen/Alibaba worker adapter

**Purpose:** add Qwen implementation capacity without violating plan terms.

**Tracks**

- **W8A:** Qwen Code adapter against fixture or lawful PAYG/API entitlement;
- **W8B:** Team Plan entitlement assessment and written provider clarification;
- **W8C:** Team Plan remains `operator_assisted` unless W8B authorizes autonomous use.

**Implementation**

- Qwen Code headless stream-JSON;
- hooks/session events;
- assigned-seat and shared-pack pool modeling;
- monthly Credits observations;
- skills and named subagent compatibility;
- provider-native subagents restricted to read-only fan-out unless one writer owns the Attempt.

**Acceptance**

- autonomous routing refuses `operator_assisted` Team pool;
- PAYG/API entitlement can be independently enabled if configured;
- monthly credits and shared pack do not contaminate another seat;
- independent provider review.

---

## W9 — Grok Build and Cursor adapters

**W9A Grok Build**

- ACP or streaming JSON first;
- separate xAI weekly pool;
- explicit acknowledgement that other SuperGrok products may consume the same pool;
- provider session and rate-limit classification.

**W9B Cursor Ultra**

- Cursor CLI stream-JSON and resume IDs;
- separate monthly pool observations where the provider surface supports them;
- conservative concurrency until proven;
- no inference that Grok Build and Cursor share one allowance.

**Acceptance**

- each adapter passes common contract tests;
- each has a dedicated worker slot and credential boundary;
- each can be independently cooled and drained;
- provider-diverse review can be commissioned.

---

## W10 — Provider-neutral handoff and automatic failover

**Purpose:** survive account/provider limits without losing project state.

**Implementation**

- `mastermind.agent_handoff.v1`;
- checkpoint commit/patch and digest;
- supervisor-built degraded handoff after abrupt death;
- Attempt terminalization and workspace seal;
- fresh Attempt/workspace restore;
- anti-thrashing/cooldown policy;
- exact-account, family-peer, cross-provider-peer, and explicit-degrade fallback.

**Acceptance**

- exact Codex account failover;
- Codex→GLM or GLM→Codex controlled failover;
- no repeated completed steps beyond the declared handoff tolerance;
- no stale worker retains workspace access;
- restart-safe recovery.

---

## W11 — Structured session control and tmux fallback

**Purpose:** support interactive CLIs and operator attach without making tmux the control plane.

**Implementation**

```text
SessionRuntime
  ProcessRuntime
  AcpRuntime
  TmuxRuntime
  later CloudRuntime
```

Tmux operations remain internal typed primitives:

```text
create
status
send_typed_input
read_events
checkpoint
interrupt
terminate
adopt
```

**Acceptance**

- no raw tmux MCP tool;
- session identity bound to current Attempt lease/fence;
- stale session cannot be adopted;
- pane output cannot alone declare success;
- transcript is bounded, sanitized, cursor-addressable, and available through structured Job reads;
- process/runtime restart reconstructs session state honestly.

---

## W12 — Agent profiles, model aliases, skills, and evaluations

**Purpose:** make leadership and specialization composable rather than hard-coded to provider names.

**Implementation**

- `config/agent_profiles.yml`;
- model capability aliases;
- skill manifests and provider exporters;
- Fable-orchestration skill experiment;
- task-class evaluation ledger;
- profile→candidate constraints;
- independent review quality gates.

**Evaluation axes**

- decomposition completeness;
- dependency/collision rate;
- first-pass validation;
- review approval;
- repair rounds;
- frontier token/session burn;
- cross-provider handoff success;
- human escalation rate.

**Acceptance**

- skills cannot widen authority;
- model/profile/skill/account remain distinct in receipts;
- a skill is promoted only on measured task classes;
- provider-specific formats are compiled from one canonical source.

---

## W13 — Phase 1F-C bounded project-leader orchestration

**Purpose:** make high-intelligence leaders manage teams rather than implement everything.

**Implementation**

- deterministic run-once COO cycle;
- planning child;
- plan schema and validation;
- bounded child creation;
- subtree-scoped dispatch through Capacity Router;
- independent review creation;
- bounded repair;
- parent aggregation;
- exception projection.

**Leader invocation policy**

Leaders are invoked only when a canonical state transition needs reasoning:

```text
plan missing
results need aggregation
review rejected
repair plan required
scope/authority exception
```

They are not persistent pollers.

**Acceptance**

- one real bounded project tree;
- worker implementation predominantly uses claimable worker pools;
- protected Business workspace is not consumed as implementation capacity;
- leader token/session usage is recorded separately from worker usage;
- fan-out, depth, repair, and review ceilings hold under mutation.

---

## W14 — Production MCP control and CEO wake relay

**Purpose:** allow ChatGPT Business Workspace Agents to operate Executive OS by exception.

**Implementation requires a new commission.**

Potential reviewed tools:

```text
submit_production_ceo_intent
request_dispatch
executive_capacity
executive_project
acknowledge_ceo_wake
```

No tool exposes shell, raw tmux, credentials, merge, deploy, or arbitrary argv.

**Acceptance**

- trusted workspace/app identity binding;
- least-privilege local principal;
- schema snapshot and adversarial mutation tests;
- one bounded real canary;
- automatic wake only for explicit canonical exception kinds.

---

## 5. First implementation commissions

After this design PR is reviewed, issue these in order.

### Commission A — 1F-B build

Use the existing Phase 1F contract verbatim as source law. Do not mix capacity schema into the same PR.

### Commission B — Phase 1G capacity schema and inventory

Build W3 only. No router and no provider process launch.

Required evidence:

- migration on a populated runtime;
- ChatGPT Business non-claimable invariant;
- independent Codex account pool fixtures;
- secret census;
- backup/restore;
- independent review.

### Commission C — Capacity observation core

Build W4 core plus Codex/Claude fixture adapters only. No dispatch effects.

### Commission D — Shadow placement router

Build W5. It emits receipts and recommendations but cannot claim Jobs.

### Commission E — Codex multi-account worker slots

Build W6 after G1 and W5. This is the first live capacity expansion because the accounts already exist and preserve model continuity.

### Commission F — GLM fixture adapter

Build W7 fixture path in parallel with E. Live arm follows plan purchase and provider-auth acceptance.

---

## 6. Program-level test matrix

Every implementation PR must select from this matrix and add mutation tests proving the changed invariant is observable.

### Lifecycle

- atomic claim and one current Attempt per Job;
- lease/fence/token stale-owner rejection;
- restart adoption or honest LOST;
- terminal Attempt immutability;
- workspace seal and absence proof.

### Capacity

- account isolation;
- horizon isolation;
- stale/unknown telemetry;
- reset behavior;
- reserve enforcement;
- concurrency enforcement;
- compliance mode enforcement;
- no ChatGPT Business worker claim.

### Placement

- deterministic candidate set and rank;
- same-model/different-account preference;
- no silent downgrade;
- independent reviewer selection;
- race and retry behavior;
- complete rejection receipt.

### Adapter

- structured event parsing;
- secret redaction;
- typed rate limit/auth/concurrency errors;
- bounded output/transcript;
- provider session identity;
- cancel/reconcile;
- malformed provider output fail-closed.

### Failover

- checkpoint durability;
- handoff completeness/degradation;
- fresh workspace;
- no concurrent writers;
- cooldown/anti-thrashing;
- attempt limit;
- restart reconstruction.

### Orchestration

- bounded fan-out/depth/repair;
- child authority/path/cost shrink-only;
- review independence;
- aggregation refusals;
- exception escalation;
- idempotent command IDs.

### Security

- credentials absent from state/logs/artifacts;
- dedicated provider homes;
- cross-worker read denial;
- no generic shell/tmux path;
- no authority increase through profile/skill/provider labels;
- no production MCP write before identity gate.

---

## 7. Operational procurement sequence

1. Inventory all existing dedicated Codex Max accounts and assign stable non-secret account labels. Do not record credentials in Git.
2. Complete the two-account Codex worker-slot proof before buying capacity solely to solve an orchestration defect.
3. Purchase/configure GLM Max as the first planned new autonomous worker entitlement, using an officially supported tool path.
4. Start Alibaba Team at a measured tier only after its automation/compliance mode is resolved; use a lawful PAYG/API entitlement for autonomous Qwen canaries when needed.
5. Add Cursor and Grok telemetry/adapters without assuming their pools are shared.
6. Change provider rankings only from completed Mastermind task evidence, not model marketing claims.

---

## 8. Program metrics

Track by task class, model alias, provider, account, pool, profile, and skill bundle:

```text
accepted results per quota unit / credit / account window
first-pass validation rate
independent-review approval rate
repair rounds
rate-limit interruptions
handoff success
duplicate-work after failover
frontier leader calls per completed project
worker-to-leader usage ratio
human intervention rate
escalation rate
wall-clock completion
```

The key economic measure is not cheapest tokens. It is:

> completed, independently accepted project outcomes per unit of scarce frontier capacity.

---

## 9. Stop conditions

The program pauses and escalates if any wave discovers:

- a second lifecycle authority is required;
- provider terms prohibit the intended execution mode;
- credentials cannot be isolated per worker slot;
- rate-limit state cannot be attributed to a specific pool with adequate confidence;
- cross-provider handoff repeatedly loses or corrupts work;
- lower-cost workers cause enough repair/review burn to consume more frontier capacity than they save;
- tmux/session control requires a generic remote shell surface;
- Phase 1C-A isolation cannot safely support the required worker count;
- a migration conflicts with Phase 1F or corrupts existing state.

The response is a recorded CEO/Chairman decision or a redesigned wave—not a silent workaround.