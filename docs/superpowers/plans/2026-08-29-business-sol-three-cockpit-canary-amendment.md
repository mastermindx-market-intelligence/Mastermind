# Business Sol Three-Cockpit Canary Amendment

**Program:** Business Sol Surface Convergence  
**Carrier:** Mastermind PR #236 / `business-sol-surface-convergence-plan-20260829`  
**Capability:** `SPEC_ONLY / RECORDS_ONLY`  
**Chairman ruling date:** 2026-08-29

## Chairman intent

Mastermind currently has three CEO cockpits. The Chairman explicitly authorizes **one** cockpit to move into ChatGPT Business when useful while the other two remain available. This changes the rollout topology from an all-or-nothing account cutover to one reversible shadow canary plus two retained controls.

This amendment changes neither organizational authority nor the existing Business Sol system architecture. It authorizes bounded planning and later admin execution for one cockpit only after the gates below. It does not itself join a workspace, merge data, cancel a Pro subscription, install a plugin, register an app, authenticate a user, create an Executive Job, bind a runtime, or make Business Sol production-live.

## Current official workspace contract

Current official OpenAI Business documentation distinguishes two materially different actions:

1. **Keep Personal and Business workspaces separate.** The same account may join Business, retain its Personal workspace and switch between them.
2. **Merge Personal into Business.** Personal chats and GPTs move into Business, the Personal workspace is deleted, the merge is permanent, plugins and custom instructions do not migrate, and Business data export is unavailable.

Current sources to re-verify immediately before any account action:

- `https://help.openai.com/en/articles/8542115` — ChatGPT Business General FAQ
- `https://help.openai.com/en/articles/8801890` — managing workspace lifecycle and migration
- `https://help.openai.com/en/articles/8542216` — Business members, seats and roles

If those contracts materially change, stop with `PLATFORM_CONTRACT_CHANGED` before account mutation.

## Frozen ruling — reversible workspace canary first

The first Business cockpit action is **join-and-keep-separate**, not personal-workspace merge.

```text
three current CEO cockpits
  ├── two Personal/Pro control cockpits retained unchanged
  └── one selected cockpit joins Business
          ├── Personal workspace remains intact
          ├── Business workspace is a separate switchable environment
          └── Business side begins SHADOW / read-only / non-authoritative
```

A later Personal-to-Business merge is a separate irreversible Chairman gate. It is not implied by joining, switching workspaces, plugin import, OAuth linking, MCP success, canary success or Business-first preference.

## Canary identity and selection

Wave identity:

```text
BSC-SHADOW1 — one-cockpit Business workspace canary
```

The selected cockpit is the least continuity-sensitive of the three at action time. Selection requires an exact current census proving:

- no active effect-bearing child is bound to that cockpit;
- no exact-session-required continuation depends on that Personal workspace;
- no unclosed watcher-enabled dialogue would be abandoned;
- important chat/project continuity is recoverable from canonical GitHub, Agent OS, Linear and Slack sources rather than hidden chat history alone;
- the other two cockpits remain accessible as independent control/fallback surfaces.

Do not choose by account nickname, browser recency, newest tab or convenience. If all three carry current exact-session obligations, the canary waits; do not silently migrate an active cockpit.

The selection and workspace join are routine rollout operations after these predicates are proven. They do not require the Chairman to choose among numbered accounts again unless two candidates remain materially non-equivalent or a billing/ownership decision is genuinely human-only.

## Ordered canary stages

### Stage 0 — preflight and recoverability receipt

Before joining Business, record a secret-free receipt containing:

- selected cockpit/account reference;
- current Personal workspace still present;
- active-operation and watcher census;
- Business workspace owner and intended standard/Premium ChatGPT seat type;
- two retained control cockpits;
- explicit `personal_workspace_merge=false`;
- rollback path = switch back to retained Personal workspace.

No chat export claim is permitted. Business workspace export is unavailable, so durable company truth must already live in canonical repositories and systems.

### Stage 1 — workspace join and switch proof

The chosen account may join the approved Mastermind Business workspace and **keep its Personal workspace separate**.

Required proof:

- profile switcher shows both distinct workspaces;
- Personal chats/projects remain accessible on the Personal side;
- Business workspace opens under the intended seat and role;
- switching Personal -> Business -> Personal succeeds;
- no personal merge prompt was accepted;
- no Pro cancellation or subscription change is inferred from workspace access;
- zero plugin/app/OAuth/Executive mutation.

Success state:

```text
BSC-SHADOW1 / WORKSPACE_SWITCH_PROVEN / DATA_UNMIGRATED
```

### Stage 2 — native Business capability census

Use the Business side only for bounded platform research and exact capability discovery:

- workspace GitHub/plugin import availability;
- custom app/developer-mode availability;
- app authentication/linking controls;
- workspace sharing/project behavior;
- host metadata behavior through HC0 when its server exists;
- memory/custom-instruction behavior without relying on it as canonical company truth.

No retrieved platform UI or workspace role grants Mastermind authority. Record unavailable/ambiguous states exactly.

### Stage 3 — skills-only package canary

After BSC-P1 is protected on current Mastermind source, import or inspect the exact reviewed skills-only marketplace/package commit in the Business canary.

This proves only package visibility/invocation. It does not bind Steward/Executive apps, authenticate the Chairman or grant write authority.

### Stage 4 — authenticated read canary

After BSC-A1, BSC-S1 and the protected Steward owner are ready, authenticate the one Business cockpit and execute the bounded Steward read canary.

Require exact principal/resource/scope validation, source-attributed results, failure-state proof and zero Executive mutation.

### Stage 5 — harmless admission canary

Only after BSC-E1 and its existing Executive/CeoIngress owners are accepted may the Business cockpit submit the already-frozen harmless admission canary. A successful `QUEUED` receipt remains distinct from dispatch, execution and completion.

### Stage 6 — dual-run and cutover evidence

Run Business shadow/control comparison against the two retained Pro cockpits. Required evidence includes:

- correct current-source bootstrap;
- no authority divergence;
- no lost exact-session continuation;
- no Chairman message shuttling required for the Business path;
- safe degradation and switch-back;
- material product benefit over the retained controls.

Only after this stage may Sol recommend Business-first use for one cockpit.

## Irreversible merge gate

Personal-to-Business workspace merge remains **forbidden** until a separate Chairman decision after all of the following:

- Business-first dual-run is accepted;
- critical Personal chats/projects have durable canonical substitutes or explicit retention treatment;
- plugin and custom-instruction loss is understood and accepted;
- organization ownership/access-loss consequences are accepted;
- no required data export is assumed;
- rollback is no longer required for the selected cockpit;
- the other two cockpits remain sufficient emergency controls;
- exact migration UI and current official contract are re-read at action time.

The merge gate must use the words:

```text
CHAIRMAN AUTHORIZES IRREVERSIBLE PERSONAL-TO-BUSINESS MERGE
```

A generic “continue,” “move one cockpit,” “Business is ready,” or successful canary is insufficient for that irreversible step.

## Failure and rollback behavior

Before any personal merge, rollback is simply:

```text
stop Business canary actions
→ switch the selected account back to its retained Personal workspace
→ preserve Business evidence as non-authoritative receipts
→ leave the other two cockpits unchanged
```

Stop and return to Sol on:

- only one workspace visible after a keep-separate choice;
- Personal history/project access loss;
- wrong seat type or role;
- forced migration/merge flow;
- inability to identify the intended Business workspace exactly;
- Business workspace deactivation or ownership ambiguity;
- unexpected plugin/custom-instruction deletion before an authorized merge;
- account/session collision with an active exact-operation binding;
- any effect uncertainty around workspace merge or subscription cancellation.

Never retry an ambiguous merge or subscription mutation. Never move a second cockpit merely because the first canary fails.

## Program-DAG effect

This amendment inserts one early reversible pilot lane without changing existing build dependencies:

```text
BSC-F0 protected
  ├── BSC-P1 package source
  ├── BSC-A1 auth foundation
  └── BSC-SHADOW1 Stage 0-2 workspace canary (keep Personal separate)

P1 + A1 + Steward/Executive app readiness
  → BSC-SHADOW1 Stage 3-5
  → BSC-D1 dual run with two retained Pro controls
  → BSC-CUTOVER decision
  → optional separately authorized irreversible personal merge
```

BSC-SHADOW1 does not replace HC0, U1, C1, C2, D1, RB1/RB2 or CUTOVER. It supplies a real Business surface earlier while preserving two live control cockpits and a reversible switch-back path.

## Completion boundary

This records amendment is complete when protected and reflected in Agent OS/Linear. It creates no account or product capability by itself.

The bounded canary is `PROVEN_LIVE` only after one chosen cockpit shows both Personal and Business workspaces, performs a successful round-trip switch and returns to Personal with no data migration or access loss. Every later stage has its own proof law.