# Mastermind Chairman Control Room P0 — architecture freeze + FABLE-00 commission

**Date:** 2026-08-21  
**Author/owner:** Sol, AI CEO  
**Chairman outcome:** remove Chris from manual session discovery, routing, and tab-to-project memory without creating another lifecycle/control plane.  
**Status:** **SOL ARCHITECTURE FREEZE / RECORDS ONLY. NO RUNTIME, UI, BROWSER, CREDENTIAL, EXECUTIVE, AGENT OS, SLACK, LINEAR, OR PRODUCTION STATE IS CHANGED BY THIS FILE.**  
**Mastermind pickup authority:** protected `master` `013cff6e84e738494b2aa502b9d04fbef920fff8`  
**Macro archaeology observation:** `main` observed at `fefdd4430e5cc4fb45fa58452f6b35cf3adf2cb3`; builders MUST re-read current Macro `main` at pickup.  
**Existing semantic parent:** `project-active-build-control` in Macro `config/mastermind_programs.yml`.  
**Proposed Agent OS workstream after this freeze is accepted:** `WS:CHAIRMAN-CONTROL-ROOM`; do not create an approximate parent or edit `WS:AGENT-OS` merely to make the portfolio neat.

---

## 0. Executive ruling

Mastermind has an organizational legibility failure before it has a scaling failure.

The Chairman currently has multiple Personal-Pro Sol conversations across three ChatGPT accounts and many concurrent Claude/Fable, Codex, Cursor, Grok/AionUI and other worker surfaces. Canonical lower-level identity exists in Git, Agent OS and Executive OS, but the human still has to remember which visible conversation belongs to which program and where a worker is supposed to return. The Chairman has therefore become the company's manual session registry, service discovery layer, wake scheduler and handoff bus.

That is the product defect P0 fixes.

The architecture is:

```text
canonical authorities
  Executive OS runtime/attention
  Agent OS organizational state
  GitHub implementation/build state
  project-active-build-control cross-repo projection
        |
        v
mastermind.chairman_control_room.v1
READ-ONLY COMPOSER
        |
        +--> local navigation-only surface bindings
        |      (address book, never lifecycle truth)
        |
        v
LOCAL LOOPBACK CHAIRMAN CONTROL ROOM
        |
        +--> Open Sol
        +--> Open Fable
        +--> Open Worker
        +--> Open PR / Agent OS / Linear when exact
```

P0 **does not dispatch, wake, message, type prompts, decide completion, rank the roadmap, allocate compute, or create work.** It makes the organization legible and navigable.

This program extends the existing `project-active-build-control` coordination purpose. It does **not** create a new global `session-os`, task database, work queue, lifecycle registry, liveness authority or second Executive service.

---

## 1. User job and 10/10 P0 end state

### Primary persona

Chairman Chris.

### User job

From one screen, answer without memory or tab hunting:

1. What are the real active programs/workstreams?
2. Who/what currently requires attention?
3. Which exact Sol/Fable/worker surface is associated with this work?
4. What real Git/PR/runtime evidence exists?
5. Can I open the correct cognition or evidence surface with one click?

### P0 success experience

The Chairman may minimize or close all AI application windows, open one local Control Room, select a real active workstream, and recover:

```text
program/workstream
canonical organizational status + next action
canonical executive attention owner, when one exists
runtime Job/Attempt/Worker evidence, when one exists
open/recent GitHub implementation evidence
preferred local Sol/Fable/worker surfaces
explicit UNBOUND / DEGRADED / UNKNOWN states
```

The Chairman can then invoke `Open Sol`, `Open Fable`, `Open Worker`, or `Open PR` without searching through application windows.

### Explicit P0 non-promise

P0 does **not** guarantee that an opened AI surface is currently thinking, owns a lease, saw a message, or remains the canonical execution runtime. A surface binding is a navigation address only. Canonical runtime and organizational facts continue to come from their existing owners.

---

## 2. Current capability ledger

| Capability | State at architecture freeze | Binding observation |
|---|---|---|
| Agent OS workstreams/decisions/discoveries/handoffs | `PROVEN_LIVE` organizational substrate | `scripts/agentos.py`, `ceo_brief.v1`, current Agent OS adoption receipts |
| Agent OS CEO rollup | `PROVEN_LIVE` | existing goal is one generated CEO page rather than hand reconstruction |
| Executive Runtime Job/Attempt/Worker/Event authority | `PROVEN_LIVE` substrate / current-host proof remains separate | `control_plane/executive_runtime.py`; SQLite is sole lifecycle authority |
| Executive Inbox attention projection | `BUILT_NOT_PROVEN` as CCR production input until P0 real-host proof | `mastermind.executive_inbox.v2`; read-only, no durable inbox state |
| CEO boot packet / Agent OS read bridge | `BUILT_NOT_PROVEN` as CCR production input until P0 real-host proof | `mastermind.ceo_boot_packet.v1`; read-only Macro bridge |
| CEO-intent workstream provenance | `BUILT_NOT_PROVEN` as production Personal-Pro path; schema exists on merged code | optional `workstream` pointer persists in typed CEO intent provenance |
| Project Active Build Control | `PROVEN_LIVE` advisory architecture; live-read behavior must be re-proven in P0 | existing `project_active_builds.v1` compiler across Macro/Terminal/Mastermind |
| ChatGPT1/2/3 cross-service seat identity | `PARTIAL` | MAS-99; never infer a missing mapping from a name |
| Claude native/deep-link navigation | `NOT_BUILT` in Mastermind; provider capability documented | provider deep links / resumable session ids must be live-probed locally |
| Cursor native thread navigation | `NOT_BUILT` in Mastermind; provider capability documented | provider thread resume must be live-probed locally |
| Codex native thread navigation | `NOT_BUILT` in CCR; Operator Harness already has durable native session concepts | App Server `thread/resume` must be live-probed locally |
| ChatGPT Personal-Pro exact conversation navigation | `NOT_BUILT` | P0 must prove named-profile + exact-chat-URL behavior on the real Mac |
| Chairman Control Room compositor/UI | `NOT_BUILT` | this document is the freeze, not implementation |
| Automated return routing / CEO wake | `NOT_BUILT` / explicitly outside P0 | later architecture only after P0 addressability proof |
| Multi-host load balancing | `NOT_BUILT` / outside P0 | later after closed-loop beta exists |

Do not average these into one vague percent-complete status.

---

## 3. Existing systems P0 MUST reuse

### 3.1 Executive attention

Use `control_plane.executive_inbox` as the owner of executive-attention projection.

It already:

* reads typed Runtime registries rather than raw SQL;
* opens the Executive store read-only;
* emits Chairman/CEO/COO target classes;
* carries `job_id`, `workstream`, status, reason, evidence and existing next actions;
* creates no database/table/queue/scheduler/lease/liveness store;
* treats degraded inputs visibly.

**CCR may filter/render this projection. CCR may not independently decide that Chris, Sol or Fable needs attention.**

### 3.2 Agent OS organizational state

Use the existing `control_plane.ceo_boot_packet` → Macro `scripts/agentos.py brief --json --no-remember` read path where sufficient.

Use current Agent OS direct records only when the existing bridge does not expose the minimum exact field P0 needs. If a bridge extension is necessary, extend one existing read projection; do not add an Agent OS clone or local RAG store.

`owner` in Agent OS remains an accountable seat, not a GUI session id. Do not reinterpret it.

### 3.3 GitHub active-build state

Reuse Macro `scripts/build_project_active_build_map.py` / `project_active_builds.v1`.

Do not reimplement its repository list, PR dependency parser, protected-path classification or collision logic in Mastermind.

The existing script has a `--dry-run` no-write path. FABLE-00 may add one tiny machine-consumer-friendly **JSON-only stdout/read seam** if needed, with the same compiler and zero new persistence. The existing generated JSON/Markdown files retain their current purpose.

### 3.4 Executive → Agent OS join

Existing CEO intent supports an optional `workstream` pointer and records it in typed provenance while writing only the Executive runtime.

CCR may use that exact provenance to associate a canonical Executive Job with an Agent OS workstream when present.

Missing `workstream` is `UNKNOWN/UNBOUND`, never an invitation to fuzzy-match an objective/title.

### 3.5 Existing worker session models

Executive Operator Harness already models Attempt → HarnessSessionEpoch → ProcessGeneration → Turn and provider-native session identity.

For headless workers under Executive OS, use the canonical runtime/session identity that already exists. Do not create a second `session_id` authority merely for the UI.

Macro's Claude fleet/hook system remains the existing session execution plane for current Claude Code work. CCR observes/navigates it; it does not replace it.

---

## 4. Identity model — do not blur these concepts

P0 freezes these as separate dimensions:

```text
PROGRAM / WORKSTREAM
  durable organizational identity; Agent OS / semantic registry

SEAT
  chairman / ceo / coo / worker account/persona identity

RUNTIME JOB / ATTEMPT / WORKER / HARNESS SESSION
  Executive OS execution identity where applicable

PROVIDER NATIVE CONVERSATION / THREAD
  Claude/Cursor/Codex/etc provider identity

SURFACE BINDING
  local navigation address that tells this Mac how to reopen/focus something

GUI WINDOW / BROWSER TAB
  ephemeral current presentation instance
```

A tab is not a session. A session is not a workstream. A workstream is not a Job. A Slack user is not a live model. A Linear assignee is not a runtime claim.

### P0 does NOT invent a canonical `cognition_id`

Current browser-hosted ChatGPT CEO conversations do not have a reviewed Mastermind runtime identity plane. P0 therefore does not mint one.

Instead, P0 stores a **preferred navigation binding** for a canonical work reference + role/seat. This is operator navigation preference, not organizational ownership or runtime liveness.

---

## 5. Navigation-only surface binding contract

### 5.1 Local home

Default target on macOS:

```text
~/Library/Application Support/Mastermind/control-room/surface_bindings.json
```

Mode target: `0600`. Parent directory private to the user.

This file is **not tracked in Git**, not synchronized through Agent OS, not posted to Slack/Linear, not embedded in Executive SQLite, and contains no credentials/cookies/tokens/prompts/chat text.

### 5.2 Contract

Proposed schema:

```json
{
  "schema": "mastermind.surface_bindings.v1",
  "bindings": [
    {
      "work_ref": "WS:EXAMPLE",
      "role": "ceo",
      "seat_ref": "chatgpt1",
      "provider": "chatgpt",
      "locator_kind": "chatgpt_url",
      "locator": {
        "browser_profile": "chatgpt1",
        "url": "https://chatgpt.com/..."
      },
      "observed_at": "<UTC timestamp>",
      "last_verified_at": "<UTC timestamp or null>"
    }
  ]
}
```

Allowed fields may be tightened by implementation. Do not widen them casually.

### 5.3 Forbidden semantics

The binding store MUST NOT contain or author:

* Job/Attempt/Worker status;
* workstream status;
* priority/rank;
* next action;
* completion state;
* queue position;
* lease/claim;
* authority or permission grant;
* executive attention target;
* result verdict;
* provider credential/session token;
* raw prompt/chat transcript.

If deleting the binding file changes any canonical program/runtime/attention fact, the architecture has failed.

### 5.4 Binding confidence

Closed P0 navigation confidence vocabulary:

```text
VERIFIED_OPENABLE
BOUND_UNVERIFIED
UNBOUND
STALE
UNSUPPORTED
```

These are **surface-navigation states only**. Never map them onto work/runtime lifecycle.

---

## 6. Provider locator architecture

P0 uses provider-native stable identifiers/deep links before GUI automation.

### 6.1 ChatGPT Personal Pro / Sol

P0 target:

```text
seat_ref + deterministic browser profile + exact observed private chat URL
```

Because the Chairman operates three separate Pro accounts, do not depend on ChatGPT's in-product account switcher as the addressing model. P0 should prove one deterministic browser profile per approved Sol seat.

Open behavior:

1. select the exact allowlisted seat/browser profile;
2. fresh-enumerate that profile's current tabs;
3. if the exact bound URL is open, focus that tab;
4. otherwise open the exact bound URL in that profile;
5. verify the resulting origin/profile and deterministic URL behavior;
6. never persist browser/CDP target ids as durable locators.

The exact observed ChatGPT URL is private local navigation data. Never commit it or print it into CI logs.

**P0 may focus/open only. It may not send a prompt, click composer actions, choose tools, or trigger a model turn.** Automated CEO wake is a later wave.

OpenClaw is an admissible P0 actuator because it supports named profiles and deterministic tab enumeration/focus/open. It is transport/presentation only. If the locally installed version disagrees with researched documentation, the live version wins and the discrepancy returns to Sol.

### 6.2 Claude/Fable

Prefer, in order:

1. provider-native Claude Code session id for code sessions;
2. Claude official chat/code deep link for desktop/web conversations;
3. exact provider URL if supported;
4. macOS window fallback only when no native address is proven.

Do not use window title as canonical session identity.

### 6.3 Cursor

Prefer provider-native Agent/CLI thread id and supported resume/load operation.

The Control Room may launch/resume the exact thread through an allowlisted server-built command. The browser must never supply arbitrary argv/executable/path.

### 6.4 Codex

Prefer the existing provider-native thread/session identity associated with the current Operator Harness/App Server path. Current App Server semantics support thread resume/read/list; builders must verify the installed exact version before relying on a remembered behavior.

Do not create a UI-only Codex session id when Executive OHF already owns the session identity.

### 6.5 Grok / AionUI

P0 is fail-closed:

* use an exact provider/native conversation/session id or documented local API/deep-link if live inspection proves one;
* otherwise expose `UNSUPPORTED` or a clearly labeled macOS-window fallback;
* never block P0 on AionUI parity;
* never infer work ownership from a Grok/AionUI window title.

### 6.6 macOS fallback

Native URL/deep link or provider resume command outranks Accessibility automation.

If a fallback must focus an app/window:

* exact bundle/app allowlist;
* explicit local macOS Automation/Accessibility permission;
* no free-form AppleScript from UI input;
* no lifecycle inference from process/window presence;
* absence becomes `UNBOUND/STALE`, not Job failure.

---

## 7. `mastermind.chairman_control_room.v1`

The compositor is a deterministic read-only projection.

Conceptual shape:

```json
{
  "schema": "mastermind.chairman_control_room.v1",
  "generated_at": "...Z",
  "sources": {
    "mastermind_sha": "...",
    "macro_sha": "...",
    "executive_inbox_schema": "mastermind.executive_inbox.v2",
    "agent_os_brief_schema": "ceo_brief.v1",
    "active_builds_schema": "project_active_builds.v1"
  },
  "degraded": [],
  "attention": {
    "chairman": [],
    "ceo": [],
    "coo": []
  },
  "work": [],
  "unbound_surfaces": []
}
```

Exact field contract is frozen by FABLE-00 implementation tests before merge. P0 should remain compact rather than copying whole upstream documents.

### `work[]` card semantics

A card may include only source-owned/proven facts such as:

* exact Agent OS workstream/program key + title/status/next action;
* exact runtime Job/Attempt/Worker ids/status where joined by accepted identity;
* exact GitHub PR/branch state from `project_active_builds.v1`;
* exact attention items from Executive Inbox;
* exact navigation bindings + binding confidence;
* explicit disagreements/degraded/unknown joins.

CCR MUST NOT derive a synthetic overall lifecycle status by averaging these layers.

### Attention UI law

`NEEDS YOU` = canonical `target=chairman` attention only.

`SOL NEEDS ATTENTION` = canonical `target=ceo` items.

`COO/OPS` = canonical `target=coo` items, normally collapsed from the Chairman's primary view.

A local missing surface may make an item harder to navigate; it must not promote or demote attention altitude.

---

## 8. Local Control Room process

### 8.1 Home

Implementation belongs primarily in `mastermindx-market-intelligence/Mastermind` because this repository owns Executive Runtime/Inbox and already owns the read-only Agent OS boot bridge.

Expected new bounded surface (names may change only with a written reason):

```text
control_plane/chairman_control_room.py       # pure compositor
integrations/chairman_surfaces/              # provider navigation adapters
scripts/chairman_control_room.py             # local CLI / ephemeral loopback server
app/static/chairman_control/ or equivalent   # dedicated private-local UI assets
```

Do **not** mount this into the public/serve-only Mastermind web product in P0.

Macro may receive one small consumer seam in `scripts/build_project_active_build_map.py` if needed for machine-readable no-write live JSON.

### 8.2 Runtime shape

P0 is an **ephemeral local presentation process**, not a launchd/system service and not Executive OS runtime.

* bind loopback only (`127.0.0.1` / `::1` where supported);
* reject public/non-loopback bind;
* no background scheduler;
* no durable event loop/lifecycle state;
* state recomputed on page refresh/poll from canonical readers;
* `open` actions affect presentation only.

### 8.3 Security

* no arbitrary URL open;
* host/origin allowlist per locator kind;
* no arbitrary executable/argv from browser;
* no shell strings built from caller input;
* no raw file path browsing endpoint;
* no secrets/chat contents in JSON or logs;
* CSRF/local action nonce for POST open/bind mutations;
* GET/state generation performs zero canonical writes;
* local binding mutation writes only the navigation cache atomically with restrictive permissions;
* malformed/unknown locator kind refuses closed;
* all subprocesses bounded by timeout and output-size ceilings.

---

## 9. P0 binding workflow

Current sessions are already fragmented, so P0 needs a transition mechanism rather than pretending bindings exist.

### Discovery

The UI may discover **candidate surfaces** from provider/native enumerators:

* ChatGPT: current tabs in each allowlisted named browser profile;
* Claude Code: provider/native session listing for the relevant checkout;
* Claude Desktop/web: currently discoverable conversation/deep-link identity if available;
* Cursor: provider thread/session listing;
* Codex: App Server/native thread listing;
* AionUI: only an exact supported local enumeration if proven.

Candidate discovery confers zero ownership.

### Explicit bind

For pre-existing GUI conversations, a human may select `Bind this surface to WS:X / role Y` once. The local mapping is navigation preference only.

The UI may offer a fuzzy/title suggestion to reduce clicking, but **the suggestion is never persisted without explicit confirmation**, and the suggestion can never create a workstream/session identity or lifecycle claim.

### New sessions after P0

Later launcher flows should create the surface from the Control Room and record the returned provider-native locator automatically. That is the migration away from today's manual bindings.

---

## 10. Failure states

P0 explicitly renders at least:

* Agent OS unreadable/malformed → named `DEGRADED`, no invented portfolio;
* Executive DB absent/unreadable → named `DEGRADED`, no false zero-runtime claim;
* GitHub/`gh` unavailable/rate-limited → stale/unknown active-build evidence, no lifecycle inference;
* ambiguous workstream ↔ Job relation → `UNBOUND`, never title-match;
* surface binding file absent → all navigation unbound, canonical state unaffected;
* duplicate bindings for one role/work ref → visible conflict, no automatic winner unless an explicit deterministic local preference rule exists;
* ChatGPT wrong profile/not logged in → surface open fails visibly; never retry through another seat/profile;
* private chat URL now redirects to login/not-found → `STALE`, no account failover;
* provider session/thread not found → `STALE`, never mint a replacement session silently;
* native app unavailable → visible open failure; program remains whatever canonical owners say;
* malformed locator / disallowed host / untrusted argv → refusal;
* one source advances while another is stale → preserve disagreement; do not majority-vote;
* browser/OpenClaw unavailable → navigation degraded only; no Executive/Agent OS mutation.

---

## 11. P0 exact acceptance matrix

FABLE-00 may not call P0 complete until all applicable rows are proven on the Chairman's **real M3 Ultra operating environment**, not only fixtures.

### Product / real-data proof

1. Control Room displays at least **three real currently active organizational work items/workstreams** from canonical sources; builders choose the exact three at proof time from then-current state rather than hardcoding this document's examples.
2. Each card identifies exact source ownership and never invents a unified lifecycle status.
3. At least one card carries a real Executive Job/Attempt/Worker join if such a current canonical joined Job exists; if none exists, that absence is shown honestly and is not fabricated for proof.
4. At least one real open/recent PR is linked from the existing active-build projection.
5. Chairman-targeted and CEO-targeted attention render distinctly from Executive Inbox.

### ChatGPT / Sol proof

6. Configure/prove deterministic browser profile separation for at least two Personal-Pro seats and target all three when the real environment supports it.
7. Bind one real Sol conversation per tested seat using its exact observed private URL.
8. With the target tab already open, `Open Sol` focuses the exact tab in the correct profile.
9. Close that target tab: `Open Sol` reopens the exact conversation in the correct profile without searching another account.
10. Restart the browser/control actuator: binding still opens the exact conversation from the persisted profile+URL rather than a stale tab id.
11. Wrong-profile, login-redirect and not-found probes fail visibly; never cross-seat failover.
12. Zero prompt/message is sent in every P0 ChatGPT proof.

### Fable / worker proof

13. One real Fable/Claude surface opens deterministically using a provider-native session/deep-link where available.
14. One real Cursor **or** Codex worker session resumes/opens using its provider-native thread/session identity.
15. Unsupported AionUI/Grok behavior is truthfully labeled rather than blocking or faking parity.

### No-duplicate-system proof

16. Delete/rename the local binding cache: canonical program/runtime/attention semantic output remains identical except for navigation binding availability.
17. Composer/UI creates zero Executive jobs/attempts/events/workers and writes zero Agent OS/GitHub/Linear/Slack state.
18. No new SQLite DB/table, queue, scheduler, retry ledger, session-liveness DB, task store, replay cursor or second Agent OS registry exists.
19. Existing Executive and Agent OS direct inputs remain the owners of their facts.

### Determinism / failure / security proof

20. Same frozen canonical inputs + same binding file semantics produce byte-identical semantic output excluding declared clock-only fields.
21. Unknown/malformed locator kinds and disallowed URL origins are rejected.
22. Browser cannot inject arbitrary command argv/path/shell.
23. Missing/unreadable canonical inputs render named degraded states, not empty-green company state.
24. A source disagreement is shown, not automatically repaired by the UI.
25. Local cache permissions/atomic-write behavior are verified.

### UX proof

26. Real browser proof at desktop and narrow/mobile-ish widths for the Control Room itself.
27. From page load, the Chairman can reach any tested Sol/Fable/worker/PR surface without consulting Slack, Linear, Finder, app switcher or memory.
28. P0 restart proof: stop/restart the local Control Room process and recover the same organization/navigation bindings without any application tab being canonical state.

---

## 12. No-rebuild / explicit non-goals

FABLE-00 MUST NOT absorb:

* MAS-48 B1/C1/B2/C2 or S0-R1;
* automated ChatGPT prompt submission / CEO wake;
* Slack command transport or `#ceo-control-room`;
* `#agent-dispatch` or generic worker delivery;
* a new Agent OS work/task/session database;
* an Executive SQLite schema migration solely for Control Room navigation;
* worker scheduling/placement changes;
* provider credential/account mutation;
* multi-host SSH/load balancing/CPU telemetry;
* OpenClaw autonomous reasoning agent/Qwen watcher;
* tmux orchestration authority;
* replacing Claude/Cursor/Codex desktop apps;
* finishing MAS-95 Linear Chairman views;
* absorbing the open Linear portfolio-projector PR;
* public/VPS deployment of the Control Room;
* inferred completion/priority/attention based on GUI text;
* a generic browser remote-control product.

P0 solves **addressability and legibility**. Automation comes later.

---

## 13. Post-P0 evolution — frozen direction, not commissioned

### P1 — launcher + automatic binding

New Sol/Fable/worker surfaces launched from Control Room return their native locator and are auto-bound to the initiating canonical work reference. Existing apps remain usable.

### P2 — structured return routing

Worker result routes canonically to COO/Fable; COO result routes to CEO/Sol; only typed authority/attention escalates to Chairman. Extend existing Executive/Agent OS/hook planes; do not create a mailbox DB.

### P3 — CEO activation actuator

Executive OS attention/wake authority decides that Sol must run. A bounded browser actuator receives an exact activation containing a target seat/work reference, resolves the already-bound ChatGPT surface, focuses/opens it, verifies context, and submits only the reviewed activation payload. OpenClaw/Qwen may assist presentation recovery but does not decide work.

### P4 — headless-by-default workers

Codex/Claude/Cursor workers increasingly run through provider-native headless session adapters under the existing Executive/Claude fleet lifecycle models. Desktop apps become optional specialist/debug surfaces.

### P5 — multi-host capacity

Only after a closed-loop beta exists: host agents report capacity and Executive placement chooses M3/M4/M1/PC/Mac-mini workers. SSH/private networking are transport, never lifecycle authority.

---

# FABLE-00 PRINCIPAL-BUILDER COMMISSION

## 14. Observable mission

**Deliver one real local Chairman Control Room P0 on the Chairman's Mac that composes existing canonical organizational/runtime/build truth with navigation-only surface bindings, and proves one-click reopening of real Sol, Fable and worker surfaces without creating another lifecycle/control plane.**

## 15. Why it matters

The Chairman currently performs manual service discovery and return routing across dozens of AI conversations. That cognitive/administrative burden is the immediate company bottleneck. P0 returns the Chairman to ideas, strategy and rulings by making the existing organization recoverable from one screen.

## 16. Authority and precedence

At pickup, re-read current source truth. Do not trust the SHAs in this historical receipt as current implementation state.

Precedence:

1. Chairman's current outcome and Mastermind-X operating doctrine.
2. Current protected Mastermind `docs/sol_skills/INDEX.md` + required skill at one exact commit.
3. This accepted architecture freeze for CCR P0.
4. Current Executive Runtime / Inbox / CEO boot-packet source in Mastermind.
5. Current Macro `config/mastermind_programs.yml`, Agent OS records/schema and project-active-build compiler.
6. Current provider primary documentation + **installed local version live probes**.
7. Linear/Slack/project/chat history as projection/advisory evidence only.

If a newer accepted source contradicts this record, stop the affected surface and return the exact contradiction to Sol. Do not mechanically merge the laws.

## 17. Verified pickup facts to re-check

Architecture author observed:

* Mastermind protected `master` = `013cff6e84e738494b2aa502b9d04fbef920fff8`;
* Macro `main` = `fefdd4430e5cc4fb45fa58452f6b35cf3adf2cb3` at archaeology time;
* open Mastermind #106 owns B1 Executive hot-state/Slack read-plane surfaces — do not collide;
* open Macro #6208 owns MAS-48 Agent OS reconciliation files — do not collide;
* open Macro #6182 owns Linear portfolio projection/compiler surfaces — do not absorb;
* no open PR was found touching `scripts/build_project_active_build_map.py` at final architecture collision check;
* existing public Mastermind app is a portfolio product; CCR P0 is private-local and must not be mounted there by convenience.

Re-check all of these immediately before changing files.

## 18. Scope / repositories

### Primary repository: `mastermindx-market-intelligence/Mastermind`

Expected implementation domains:

```text
control_plane/chairman_control_room.py
integrations/chairman_surfaces/**
scripts/chairman_control_room.py
private/local Control Room static assets
tests dedicated to CCR
operator/local run documentation
```

### Secondary repository: `mastermindx-market-intelligence/macro`

Only if required:

```text
scripts/build_project_active_build_map.py
its dedicated tests
new Agent OS CCR records after architecture/workstream ownership is lawfully established
```

Do not edit current MAS-48 records, `WS:AGENT-OS`, generated portfolio projection work, or unrelated product code merely to make joins convenient.

## 19. Complete user journey

1. Chairman starts local Control Room using one bounded command/app launcher.
2. UI builds fresh read-only composite state.
3. Top surface shows canonical Chairman attention, then Sol attention, then active work cards.
4. A work card names its exact Agent OS/GitHub/Executive evidence and visible unknowns.
5. The card shows verified/bound/unbound navigation surfaces for Sol/Fable/workers.
6. `Open Sol` focuses or opens the exact Personal-Pro conversation in the exact seat profile.
7. `Open Fable` opens the exact Claude/Fable surface through native identity/deep link where possible.
8. `Open Worker` resumes/opens exact provider-native worker session for the proven provider.
9. PR/Agent OS/Linear evidence links open normally when exact.
10. Restart/closed-tab/missing-provider/degraded-source cases behave according to this freeze.
11. No canonical state changes merely because the Chairman looked at or navigated the organization.

## 20. Method

Deterministic:

* source joining;
* schema validation;
* attention altitude preservation;
* URL/provider allowlists;
* active-build compilation;
* native-id resume/open adapter commands;
* cache validation/atomic write;
* degraded/disagreement projection.

Human-confirmed:

* initial binding of a pre-existing ambiguous GUI conversation to a work reference/role.

Statistical/model-generated:

* optional UI-only fuzzy suggestions of candidate surface → workstream, if useful.
* suggestion grants zero authority and cannot persist without explicit confirmation.

No model decides attention, lifecycle, completion, priority, authority or work ownership in P0.

## 21. Ordered implementation sequence

### Wave A — source contract + pure compositor

* re-read current authorities and collision surfaces;
* freeze exact `mastermind.chairman_control_room.v1` + `mastermind.surface_bindings.v1` schemas in code/tests;
* consume Executive Inbox + CEO boot packet without raw-SQL/AgentOS-parser duplication;
* consume existing active-build compiler through a no-write machine seam; add the smallest Macro seam only if required;
* prove deterministic/degraded/disagreement/no-write behavior.

**Stop A if joining requires a new canonical identity/lifecycle field. Return to Sol rather than inventing it.**

### Wave B — provider surface adapters

Implement exact allowlisted adapters separately:

* ChatGPT named-profile exact-URL focus/open;
* Claude native/deep-link resume/open;
* Cursor thread resume/open;
* Codex thread resume/open;
* optional AionUI exact-supported adapter or explicit UNSUPPORTED.

Before coding each adapter, inspect the installed binary/app/version and run a disposable zero-message live probe. Keep a capability matrix with `PROVEN`, `PARTIAL`, `UNSUPPORTED`, `NOT_INSTALLED`.

### Wave C — private-local UI + binding flow

* local loopback-only ephemeral server;
* compact Chairman-first information architecture;
* candidate discovery + explicit bind/unbind;
* one-click open actions;
* no prompt sending;
* security/refusal tests.

Use existing Mastermind visual language where useful, but do not bolt this into the public portfolio route.

### Wave D — real operating proof

On the Chairman's real Mac:

* bind/test three real work items;
* prove ChatGPT multi-seat navigation with closed-tab + browser-restart cases;
* prove Fable exact open;
* prove Cursor or Codex native worker resume;
* prove deletion of bindings does not alter canonical state;
* capture browser/UI proof at relevant breakpoints;
* run full scoped + regression tests and mutation/falsifier probes;
* produce exact continuation handoff.

## 22. Acceptance tests

Implement discriminating tests for every P0 matrix row in §11. Minimum high-value mutation/falsifier set:

* mutate local binding to include lifecycle status → contract rejects;
* change workstream title to resemble another → no join occurs;
* remove CEO provenance workstream → runtime card becomes unbound rather than fuzzy-joined;
* disallowed ChatGPT host → open refuses;
* change browser profile from seat A to B → seat/profile invariant catches it in live proof;
* stale browser target id → open still succeeds by fresh tab enumeration or fails visibly; target id is never authority;
* arbitrary argv injected into Cursor/Codex locator → refuses;
* delete binding file → canonical semantic projection remains unchanged;
* force Executive read failure → named degraded, not zero jobs;
* force Agent OS read failure → named degraded, not zero workstreams;
* force active-build live fetch failure → stale/unknown build evidence, no work completion change;
* duplicate competing surface bindings → visible conflict, no silent arbitrary winner.

## 23. Production proof standard

Green CI is insufficient.

FABLE-00 owes:

* exact local command used to launch CCR;
* exact Mastermind/Macro SHAs consumed;
* real source receipts and any degraded state;
* redacted screenshots of the Control Room;
* real `Open Sol`, `Open Fable`, and `Open Worker` proofs;
* exact provider-native identifiers **redacted where they are private** while proving equality locally;
* evidence of zero messages sent by navigation tests;
* file/database before/after receipts proving no canonical mutation;
* browser restart / app restart behavior;
* local binding-cache permission/atomicity receipt;
* CI/test/mutation results;
* discovered platform limitations and the exact consequence.

Do not commit private conversation URLs, local usernames/paths that reveal sensitive information, provider session tokens or browser profile data containing secrets.

## 24. Stop condition

Stop when **CCR-P0 is production-proven on the Chairman's real Mac and one held/review-ready implementation packet exists for Sol**.

Do not start automatic wake, typed prompt submission, worker return routing, multi-host capacity or MAS-48 transport work.

Return to Sol with:

```text
VERDICT
exact Mastermind/Macro base + heads
PRs
changed-file census
schema hashes/contracts
capability matrix per provider
real three-work-item proof
ChatGPT seat/profile/closed-tab/restart proof
Claude/Fable proof
Cursor/Codex worker proof
canonical no-write proof
security/mutation results
browser screenshots/locations
all degraded/unsupported surfaces
new conflicts/discoveries
one exact recommended P1 or blocker
```

---

## 25. Research receipts used for this freeze

Repository evidence:

* Mastermind `control_plane/executive_runtime.py`
* Mastermind `control_plane/executive_inbox.py`
* Mastermind `control_plane/ceo_boot_packet.py`
* Mastermind `control_plane/ceo_intent.py`
* Macro `config/mastermind_programs.yml`
* Macro `scripts/build_project_active_build_map.py`
* Macro `scripts/agentos.py`
* Macro Agent OS schemas / `WS-AGENT-OS`
* Macro `.claude/settings.json` and return guard
* Macro `.cursor/hooks.json` / `.codex/hooks.json`

Current platform primary/reference research consulted before local falsification:

* OpenAI Help — ChatGPT multiple account switching / Project behavior
* OpenAI Codex App Server documentation — thread read/list/resume
* Anthropic Claude Code session continuation/resume documentation
* Anthropic Claude app URL-scheme / deep-link documentation
* Cursor Agent CLI / thread resume documentation
* OpenClaw browser profile/tab-control documentation
* Apple macOS Automation/Accessibility and URL/application opening documentation

Primary documentation establishes a candidate capability. **The installed version and the Chairman's real environment remain the P0 truth for every load-bearing locator.**
