# Mastermind Claude Capability Hardening — Build Handoffs

Protected starting reference: `mastermindx-market-intelligence/Mastermind` protected `master`. Re-pin current protected master before modifying work.

Universal rule for every packet below: extend existing Executive OS / Agent OS / ExecutionCapabilityRegistry / Capacity / Dialogue / Browser / Studio owners. Do not create a Claude-specific lifecycle, queue, retry plane, identity database, session registry, capability authority, watcher database, or provider-placement system.

---

## HANDOFF 1 — Rich Claude Principal Capability Profile

### Outcome
Create the first production-candidate **rich Claude principal/orchestrator capability profile**, distinct from sealed Claude workers, so an admitted Claude COO/CEO session can actually receive reviewed Executive, delegation, source, design, browser and company-context capabilities.

### Existing owners to reuse
- `ExecutionCapabilityRegistry`
- `control_plane/claude_mcp_client_projection.py`
- existing COO principal mandate/host admission
- existing source/workspace and Capacity owners
- existing sealed Claude profiles remain unchanged

### Build
Add a reviewed profile conceptually equivalent to `principal.claude.coo.rich.v1`.

It should reference exact capability packages rather than ambient Claude/user-home configuration. Initial admitted capability families should be composed incrementally:
- Executive COO surface;
- Agent OS / company context;
- Company Dialogue;
- governed source/GitHub actions;
- Subagent Fabric;
- Studio/Paper;
- governed browser resource.

Project the profile through the existing Claude MCP/client projection for CLI, Agent SDK and other qualified Claude surfaces.

Require observed tool-catalog/schema attestation before launch where supported. Unexpected ambient MCP/plugin/skill/hook capability must not silently widen authority.

### Critical separation
Do **not** weaken:
`sealed.worker.claude.*.no-extensions.v1`

Rich principals and sealed implementation workers are different security products.

### DONE WHEN
A real admitted Claude principal launches under an exact reviewed profile, observes exactly the expected capability generation, can perform a harmless read across multiple admitted owners, and refuses on capability/schema/profile drift.

No production claim from config existence or tests alone.

---

## HANDOFF 2 — Claude Capability Mirror / Provider Projection

### Outcome
Prevent Claude from permanently falling behind ChatGPT/Codex capabilities.

Build a deterministic provider-projection and parity validation layer around the existing canonical capability owners.

### Architecture
Canonical capability definition:
`ExecutionCapabilityRegistry / capability package owner`

Provider projections:
- ChatGPT
- Codex
- Claude Code
- Claude Agent SDK
- later Grok/GLM/etc.

Provider packaging is not authority.

### Build
Create a versioned parity manifest/compiler or equivalent existing-owner extension that can answer:

1. What canonical capability generation exists?
2. Which provider projections are expected?
3. Which provider projection generation is currently shipped?
4. Are tool schemas, capability identities and required package digests equivalent where parity is claimed?
5. Is a difference intentional and explicitly classified?

For Claude, consume the existing `claude_mcp_client_projection.py`; do not invent another MCP projection engine.

Add CI that fails when a capability explicitly declared Claude-supported changes without updating/requalifying the Claude projection.

### Hardening
Do not blindly auto-add newly introduced tools to Claude. New capabilities must remain opt-in through reviewed profiles.

“Parity” means capability-equivalent under the same authority ceiling, not identical provider configuration.

### DONE WHEN
A change to a shared capability generation either:
- produces a valid updated Claude projection with tests, or
- deliberately records Claude as unsupported/deferred,

and stale silent Claude projections are CI-detectable.

---

## HANDOFF 3 — Mastermind Executive for Claude: Current-Backend Parity

### Outcome
Bring `integrations/claude_executive_plugin` forward from the old P1 package to the current accepted Executive/COO backend generation.

### Current gap
Protected source still has the Claude plugin at version `0.1.0` and its README says:

`P1 SOURCE PACKAGE / PRODUCTION INERT / EXECUTIVE MUTATION UNAVAILABLE`

But later protected backend work now includes COO principal mandate, request identity, host composition/admission and static COO Executive routes.

Do not rebuild those backend features.

### Build
Census the current ChatGPT/Web-CEO Executive v3 app and the current accepted COO backend.

Update the Claude package to expose the **role-correct COO capability**, not a copied Web CEO tool set.

Expected package work:
- updated plugin manifest/version;
- updated Executive orchestration Skill;
- current context/recovery command;
- reviewed MCP declaration/projection if current Claude surface qualification allows it;
- role-correct COO action surface;
- optional session hook only where it supplies an already-accepted binding fact;
- exact schema/profile generation tests.

### Critical authority rule
Do **not** give Claude COO `submit_ceo_intent` merely because ChatGPT CEO has it.

CEO and COO remain different principals/policies. Use the existing COO admission path.

Do not claim exact Claude-conversation isolation unless the existing session-binding falsifier is actually satisfied.

### DONE WHEN
A fresh Claude principal can:
1. recover current Executive/Fabric state;
2. perform one harmless role-correct COO action through the existing Executive owner;
3. consume/read the resulting canonical state;
4. reject CEO-only actions and sibling/invalid principal/profile cases.

Source merge, installation, authentication and live canary are separate required proofs.

---

## HANDOFF 4 — Claude ↔ Subagent Fabric

### Outcome
Allow a rich Claude orchestrator to delegate bounded work to the existing Mastermind workforce and consume results without provider/account micromanagement.

### Existing substrate
Reuse:
- Executive Job / Attempt / Worker lifecycle;
- CooCycle / OperatorHarnessOrchestrator;
- Model Router;
- Capacity Fabric;
- remote/native worker adapters;
- result/review/repair/aggregation owners.

Do not create `claude_subagent_queue`.

### Claude-facing capability
Expose a compact principal workflow conceptually equivalent to:

`fabric_capabilities`
`fabric_delegate`
`fabric_children`
`fabric_result`
`fabric_continue`

The exact names should follow the existing Executive/Fabric public contract rather than force a new API if equivalent operations already exist.

### Hardening
Claude chooses outcome/capability/quality constraints. Capacity/Router chooses provider/account/host.

Provider-native Claude subagents may remain useful for ephemeral cognition, but independently reviewable or durable Mastermind work must return through the existing governed child-work mechanism.

Ensure:
- exact parent/root association;
- no duplicate child after ambiguous dispatch;
- independent review path;
- parent result consumption;
- parallel ready work where dependencies permit;
- no head-of-line wait on unrelated children.

### DONE WHEN
One real Claude principal delegates at least two path-disjoint child outcomes to eligible non-identical worker lanes, continues useful principal work, receives both canonical results, handles one review/repair path, and consumes the accepted result without Chairman provider/account/session selection.

---

## HANDOFF 5 — Claude CI / PR / Release Continuation

### Outcome
Stop Claude orchestrators from spending 30–50 minutes synchronously waiting for GitHub CI.

### Existing law
Reuse the existing GitHub/release owner and current CI-observer design:

**one observer per exact candidate**, bounded polling, material-change return, stale-head rejection.

The observer reads status only.

### Build
Give Claude principals a workflow that:

1. publishes or identifies the exact candidate head;
2. arms/reuses the existing observer for that exact head;
3. records the return route;
4. immediately continues path-disjoint authorized work;
5. consumes PASS/FAIL only when materially returned;
6. on FAIL, reads the exact failure and repairs;
7. on a new head, invalidates the old observation and binds observation to the successor candidate.

### Hardening
Do not make Claude itself sit in a `gh pr checks --watch` loop.

Do not create a Claude CI daemon or watcher DB.

CI observer cannot:
- merge;
- deploy;
- change leases;
- silently rerun;
- bypass required checks.

PASS means release prerequisite satisfied for that candidate, not product acceptance.

### DONE WHEN
A representative Claude orchestrator submits a PR candidate, hands CI observation off, performs another useful independent phase while CI runs, then receives the correct exact-head result and either advances the release gate or repairs a real failure without duplicate observer/candidate work.

---

## HANDOFF 6 — Claude Agent OS + Company Dialogue

### Outcome
Give Claude principals durable organizational context and reciprocal company communication without building a Claude-specific memory/message system.

### Existing owners
- Agent OS: workstreams, decisions, discoveries, handoffs
- Agent Relay / Company Dialogue: validated dialogue
- Slack: transport
- Executive Wake Fabric: wake obligations
- RuntimeBinding / SessionTargetRegistry: exact continuation targets

### Build
Surface a Claude-capable workflow for:
- recover current workstream/mission context;
- read relevant decisions/discoveries/handoffs;
- write authorized Agent OS decision/discovery/handoff deltas;
- send validated Company Dialogue frames;
- read the bound dialogue/thread return;
- participate in CONTINUE / RESULT / STOP reciprocal flow.

Use the existing company-dialogue MCP/Relay route wherever available.

### Hardening
Slack prose is not work authority.

Do not create:
- Claude inbox database;
- Claude thread registry;
- Claude wake scheduler;
- one watcher daemon per conversation;
- provider-session identifiers in Slack.

A validated commission-bound dialogue frame may trigger existing Wake; arbitrary messages may not.

### DONE WHEN
One Claude principal participates in a complete:
principal → worker/other principal → return → continuation → terminal STOP
dialogue using the same Executive/Agent OS identity and one existing dialogue carrier, with zero Chairman message shuttling and zero duplicate wake/job/session effects.

---

## HANDOFF 7 — Claude Governed Browser / Visual QA

### Outcome
Give rich Claude principals and appropriately admitted workers browser-based product proof using the existing Worker Browser Resource Fabric.

### Existing substrate
Protected source already contains:
- `playwright-worker-browser-b1`;
- browser snapshot/screenshot/navigation/form/console/network/tab tools;
- browser resource ownership;
- native Claude operator consumer code/candidate tests.

The production capability policy does not yet establish full native Claude rich-operator admission.

### Build
Add the browser resource only to reviewed Claude profiles that require it.

Bind:
- exact workspace/source identity;
- exact browser resource generation;
- approved origins/egress;
- browser tool schema;
- lifecycle/cleanup ownership.

Start with the existing bounded local-review model before widening internet/production-site scope.

Use Studio Direct separately for desktop-native interaction. Do not collapse browser and fleet/Desktop authority.

### Hardening
Do not use:
- Chairman browser cookies/profile;
- arbitrary `claude --chrome`;
- ambient user browser session;
- unrestricted network access

as substitutes for Browser Resource Fabric.

Visual proof should include screenshot plus bounded console/network evidence when appropriate.

### DONE WHEN
A real admitted Claude path opens a product from the exact permitted workspace/devserver, inspects relevant breakpoints, captures visual evidence, reads bounded console/network state, and releases the exact browser resource without gaining ambient user-browser authority.