# Mastermind Living Atlas

## Experience architecture and engineering plan

**Prepared:** 9 November 2026, America/Vancouver  
**Status:** proposed architecture; concept and motion study authored; production integration not started by this commission.  
**Source baseline:** Mastermind protected master at **85179e35ce1fd3ddc00e85df5745fee4d5288068**.  
**Programme alignment:** extend the existing Team / Projects / Code / Fleet experience and WS:EXECUTIVE-ECOSYSTEM-COMPLETION. This is a proposed experience specification, not a new runtime, admission grant, registry or accepted organizational ruling.

## 1. The decision

Build **Living Atlas**: a navigable, gently dimensional landscape of projects connected by fine threads. Small articulated robotic creatures, called **weavers** in this proposal, inhabit it. They travel, dock, inspect, build, wait and return results. The world has the movement and visual care of a game, with the clarity and evidence of an operating interface.

Use **2.5D art and animation on one PixiJS canvas**, surrounded by the existing React application. Keep project names, search, inspectors, navigation, permissions and the accessible activity explorer in HTML. Ship a production-qualified WebGL implementation first; qualify WebGPU separately against the actual package and browser matrix.

The key separation is:

> Existing owners establish what happened. A disposable presentation layer decides how to show it.

No model calls, streamed video, general physics simulation or continuous force layout are required to animate the world. Real observations arrive at their natural frequency. The browser interpolates motion locally.

The first implementation should be one excellent, fully connected project story: a persistent bot, a T3 coding lead, two actual helper executions, one repository, a browser action, a file change, a continuing terminal process, a failed check, a correction and a separately evidenced result. Estate scale follows that complete slice.

### The user-facing promise

Someone unfamiliar with the engineering should quickly see:

1. What the company is trying to accomplish.
2. Which team is working on each project.
3. Who is leading and which helpers belong to that execution.
4. What is happening now, including concurrent work.
5. What needs attention and why.
6. What has actually been delivered or verified.

Complete visibility of every machine and file action is a coverage objective, not a current capability claim.

## 2. What the current estate already provides

This investigation inspected source and current PR metadata. It did not establish that every path below is installed or live.

| Existing evidence | What it establishes | Design consequence |
|---|---|---|
| app/mastermind_os/package.json at the source baseline | Existing React / Vite / TypeScript application with a Tauri host; no Pixi/Three dependency in this manifest | Add a lazy scene package inside the current app |
| Existing Team/T3/Hermes plan, particularly sections 5 and 18 | Team, Projects, Code and Fleet composition; native T3, Hermes, Teamlink and Capacity ownership already have defined places | Atlas is an alternate view of these objects and routes |
| OrganizationWorkspace.tsx | Source-linked advisory organization; live enrollment not observed; full_fleet is false | Charter seats cannot become live creatures without actual session/enrollment evidence |
| fabric/catalog-contract.ts | Explicit source scope, availability and coverage; catalog limit 32 | Whole-estate claims require qualified paging and coverage |
| fabric/mission-interiors.ts | Lineage qualification, duplicate/cycle handling, a 256-row display cap and documented 500-child decoded-source bound | Reuse lineage rules; distinguish grouping from source omission |
| T3_WEB_COLLABORATION.md and session_bridge/t3_web_client.py | Existing native T3 MCP/CLI direction, cursor reads and preserved native identities | Consume T3's owner instead of creating another coding-session service |
| PR #2356 | T3 adapter lane merged into the integration branch; recorded narrow native adapter proof | Native adapter proof is not global admission or deployed estate completeness |
| PR #2338 | Open draft integration candidate at inspection | Coordinate future source work with its incumbent writer |
| Executive MCP read in this session | backend_unavailable | No live Executive census obtained; do not fabricate a live scene |

The current design distinguishes a persistent Hermes profile, Bot Chat, an ordinary Hermes session, an ACP coding session, a T3 thread, an Executive job and an attempt. Atlas must preserve those distinctions.

Sources are linked in section 20. Refresh material interfaces and ownership narrowly before implementation.

## 3. Art direction: a living project landscape

### Chosen composition

Use low, sculpted project islands on an ink-dark or warm-light surface. Give them a consistent miniature material language: ceramic or stone-like planes, brushed graphite, soft contact shadows, crisp labels and restrained warm metal accents. Fine curved threads connect meaningful relationships.

The generated concept study explores the darker direction. Production should independently compose the existing Noir and Atelier themes rather than mechanically invert colors.

Most of the world remains quiet. Purposeful motion attracts the eye because it is surrounded by space. A little parallax and occlusion gives depth; a free-flying camera is unnecessary.

The visual identity should be original. Existing software and games are references for animation craft, spatial memory and rendering techniques, not sources of copied branding or proprietary assets.

| Direction | Strength | Weakness | Decision |
|---|---|---|---|
| Pure constellation or spiderweb | Beautiful relationships and travel | Anonymous nodes, dense edge crossings, unstable layouts | Borrow threads and motion |
| Connected project islands | Stable places, recognizable objectives, nested detail | Needs strong art direction to avoid floating-card appearance | Adopt as the foundation |
| Literal office or city | Immediately familiar | Desks often fail to explain work; walking becomes decorative | Borrow spatial principles only |
| Fully navigable 3D world | Strong spectacle and physical depth | More occlusion, camera/picking complexity, asset work and GPU cost | Keep as a comparative experiment |

### Creature design

The agent body is a small polished robotic form with eight fine articulated limbs, clear orientation and a persistent identity mark. It may be charming, but should avoid exaggerated faces, costumes and constant speech bubbles.

A lead gets a distinctive emblem or frame. Worker size expresses display emphasis or selection, not model intelligence, organizational worth or provider prestige.

Create an original kit:

- One reusable body rig with a few controlled silhouettes.
- Persistent identity marks independent of provider/model.
- Start, move, inspect, build, wait, blocked, return and settled poses.
- A neutral non-spider silhouette option if usability research finds the spider form uncomfortable.
- Baked material and shadow assets for rich appearance at low runtime cost.

An artist or motion designer should own the character sheet, silhouettes, contact poses and timing. Coding alone will not reliably produce the desired finish.

## 4. Geography and semantic zoom

Projects are the primary places. Tool categories are local destinations inside a project. A single global Browser room would mix unrelated missions and obscure purpose.

| Scale | Visible meaning | Representation |
|---|---|---|
| Estate | Projects, leadership, grouped work, major handoffs and attention needs | Approximately 5–12 prominent regions in the opening composition |
| Project | Objectives, teams, sessions, major repos and dependencies | Stable island with team anchors |
| Session | Execution lineage, simultaneous processes and tool targets | Session creature with process satellites |
| Action/artifact | Exact source, file/diff, command result, browser target or receipt | Existing inspector, Code workspace or evidence view |

The opening count is an art and comprehension constraint, not a system limit. Large portfolios use grouping, search and navigation.

### Identity model

Keep persistent teammate, organizational role, project/mission, session/thread, job, attempt, tool/process, resource and artifact as distinct entities.

A bot with four active sessions has one persistent home identity and four identifiable execution bodies. A session running a command while browsing has one body and two concurrent activity markers. It must not race between them in a way that implies sequential execution.

Organizational reporting and execution parentage are different edges. Cross-source joins require explicit mappings or owner-emitted correlations. Similar names, timestamps and descriptions are insufficient.

Projects and repositories are not one-to-one. Use local resource portals referring to canonical repository identity, with exact workspace, branch and observed head available on selection. Do not duplicate the repository in the data model because two projects display it. Do not collapse unrelated worktrees because their file paths match.

The Fleet lens adds observed host/environment badges and constraints to the same world. It does not rearrange project geography. Host placement and project purpose are separate dimensions.

## 5. A precise animation language

| Meaning | Motion/pose | Minimum evidence |
|---|---|---|
| Session requested | Outlined marker | Request observed |
| Session running | Creature present and working | Actual started/running observation |
| Child requested | Pending outline | Original delegation/request |
| Child starts | Creature emerges; parent tether emphasized | Qualified child start and parent relation |
| Reading | Scan across stationary document | Structured read observation |
| Editing | Stitch/build gesture | Observed write/edit; provisional until confirmed |
| File changed | Artifact detail settles | Owner change receipt or qualified postimage/diff |
| File moved/renamed | Named document transfers between endpoints | Confirmed source/destination effect |
| Browser use | Dock at window/portal | Exact context/tab action observation |
| Command running | Workbench activates; process marker remains | Original process/command start |
| Command complete | Workbench settles into result | Matching terminal result |
| Message sent | Capsule starts transfer | Send receipt |
| Message consumed | Receiver state changes | Separate consumption/ack evidence where supported |
| Waiting | Settled pose; short reason | Owner wait state |
| Failed check | One restrained cue; durable marker | Matching failed result |
| PR ready, merged, deployed, accepted | Distinct artifact milestones | Each milestone's own evidence |
| Telemetry lost | Outline at last known location | Source freshness/availability failure |

A command containing a move instruction does not prove a file moved. A generic tool success may not prove the intended user-visible outcome. Hidden reasoning is not a telemetry source. “Preparing a response” should reflect observable state, without claiming to visualize private thoughts.

### Motion craft

Initial artistic timing ranges:

- Departure anticipation: 60–100 ms.
- Local travel: 400–1,200 ms.
- Docking/landing: 80–180 ms.
- Explicit camera navigation: 350–700 ms.
- Working-pose variation: subtle and infrequent.

These are presentation durations, not real work-duration measurements.

Use distance-based gait phase so feet do not slide when velocity changes. A two-segment leg solve or small authored rig is sufficient. Jumps use a spline, vertical arc and shadow separation. Soft body response gives a satisfying arrival. General rigid-body or cloth simulation adds little meaning.

Routine messages move capsules; they do not make the whole leader cross the world. Show detailed relationship lines on selection. Keep the underlying topology calm.

### Motion arbitration

Current facts outrank cinematic continuity:

1. Cancellation, failure, unknown effects and lost source interrupt incompatible poses.
2. A new attempt invalidates obsolete motions from the prior attempt.
3. A short completed operation can appear as a retrospective trace.
4. Repeated reads/edits coalesce into counts and time intervals.
5. Reconnect collapses obsolete choreography to current state.
6. Animation callbacks never change operational state.

Set a maximum presentation lag as well as a record cap. Start with a target below one second for ordinary live explanation. Facts and urgent state indicators update immediately. Shorten travel when it would contradict them.

## 6. Navigation and everyday use

Atlas is an alternate view reachable from existing Team and Projects. Avoid another competing company home.

Core actions: find a project/teammate/session; focus a project; follow a selected team; show attention needs; inspect an artifact; open the exact source conversation or coding workspace; choose Full/Calm/Off motion; pause display.

The default camera is stable. Explicit navigation moves it smoothly. Follow-team and cinematic presentation modes are opt-in. The camera must not pull users away from a failure they are reading.

The inspector leads with purpose:

> **Make Portfolio reliable**  
> Terminal · Engineering lead · two active helpers  
> Now: running navigation checks  
> Last verified milestone: route guard updated  
> Waiting on: browser verification

Repository, workspace, branch, head, process and source IDs remain available beneath the readable summary. Reuse permission-aware Open session, Open changes and Open PR paths.

Dragging changes presentation layout only. Reassigning or stopping real work is a separate explicit action through the existing owner.

### Attention budget

One followed story receives full cinematic detail. Two or three nearby important events can receive secondary emphasis. Background work uses grouped motion. These are proposed design constraints to validate.

Movement intensity is not a productivity score. Tool calls, tokens and child counts can grow without progress. Prioritize milestones, resolved blockers, outcome state and observation age.

## 7. Integration architecture

1. Existing Hermes, T3, Executive/Fabric, GitHub and fleet sources provide permitted observations.
2. Existing authenticated host/bridge paths qualify principal, project, source scope and freshness.
3. Thin adapters produce a display-safe projection.
4. An ephemeral reducer keeps current view state coherent and computes aggregates.
5. A presentation planner chooses meaningful transitions.
6. Pixi draws the world; React/HTML renders navigation and inspectors.

No second event bus, scheduler, credential store, bot registry, memory service, runtime or lifecycle database is introduced.

| Concern | Owner retained | Atlas responsibility |
|---|---|---|
| Navigation/access | Mastermind OS and authenticated host | Preserve permitted objects and exact selection |
| Organization/continuity | Agent OS and current role/work contracts | Render sourced relationships |
| Persistent bots/sessions | Hermes profile/gateway | Show observed presence, tools and conversation links |
| Coding threads, workspace, PTY, Git, browser | T3/native owners | Project activity and open source surfaces |
| Admission, attempts, claims, parentage | Executive OS | Consume established lifecycle and lineage |
| Model/account/host placement | Capacity Fabric/router | Show qualified assignment; do not choose placement |
| Cross-app dialogue | Teamlink / Session Bridge | Show observed message/result returns |
| PR/checks/merge/release | GitHub/release owners | Render separately proven milestones |
| Retained history | Existing source retention owners | Offer supported historical views |

### Proposed frontend boundaries

The following paths are proposed, not existing source claims:

~~~text
app/mastermind_os/src/living-atlas/
  AtlasWorkspace.tsx
  read-port.ts
  scene-contract.ts
  scene-reducer.ts
  source-coverage.ts
  identity-joins.ts
  presentation-plan.ts
  layout/
  renderer/
  accessibility/
  inspector/
  fixtures/
~~~

Integrate through existing host.ts, projection/selection, fabric, organization, session-estate, resources and qualified T3/Hermes adapters. Preserve the active Team/Code writer. Freeze actual interface names in the first engineering slice.

Reuse current typed subscriptions/RPC and source cursors. A host projection may combine sources for an authorized selection, but becomes no new authority. Polling-only sources retain their supported bounded polling and visible observation age.

Prefer one shared authenticated subscription set for the mounted application scope over one connection per creature or panel. Reconnection restores reads and never resubmits commands.

## 8. Event, identity and coverage contracts

This proposed normalized shape adapts existing types; it is not a new canonical runtime schema:

~~~typescript
type SceneObservation = {
  source: {
    owner: string;
    instanceRef: string;
    epoch: string;
    eventId: string;
    cursor: string | null;
    sequence: string | null;
  };
  observedAt: string;
  occurredAt: string | null;
  relatesTo: {
    botRef?: string;
    roleRef?: string;
    projectRef?: string;
    missionRef?: string;
    sessionRef?: string;
    nativeThreadRef?: string;
    jobRef?: string;
    attemptRef?: string;
    parentAttemptRef?: string;
    toolSpanRef?: string;
    resourceRef?: string;
    artifactRef?: string;
  };
  kind: string;
  state: string | null;
  evidenceRef: string | null;
  causedBy: string[];
  disclosure: "summary" | "detail";
  display: {
    verb: string;
    targetLabel: string | null;
    outcome: string | null;
  };
};
~~~

Namespace event IDs by source instance and epoch. Preserve distinct retry attempts and process restarts. Use source-local ordering; cross-machine clocks do not establish total causal order.

Every source snapshot also needs:

- Scope and authorization generation.
- Observation time and source-specific freshness policy.
- Complete / partial / unavailable / unknown coverage.
- Returned count.
- Available/omitted counts only when known.
- Continuation/paging capability.
- Source revision and compatible cursor boundary.

**Aggregation and omission look different.** “48 sessions grouped” means 48 records were observed. “More sessions not loaded” means records are missing. Unknown counts remain unknown.

A missing row in a capped response does not mean stopped. Stale does not become idle. Deletion needs evidence or a documented source-replacement rule.

### Snapshot and stream consistency

Establish a safe snapshot-plus-cursor boundary, or use the owner's equivalent resume contract. Where snapshot/subscription ordering can lose events, use a supported overlap/reconciliation strategy. Timestamp alone is insufficient.

Track source epochs and authorization changes. Clear prohibited data and restore the correct selection. Preserve explicit gaps. Bound deduplication state to the retained cursor window.

For multiple sources, retain source-local cursors and a projection revision. That revision describes the view; it does not claim atomic observation of all sources.

### Tool/resource coverage

Prefer structured tool/process events and existing receipts. Do not install blanket filesystem watchers, session-directory scrapers, packet capture or screen streaming merely to create motion.

If a source cannot observe a file, tab or command, show its supported activity level. Expand an existing owner's instrumentation only for a named user journey.

Repository references include stable repo identity and checkout context. Browser references include context/tab/navigation identity. Process references include start or boot generation so recycled PIDs cannot inherit old results.

## 9. Time and bounded presentation

Keep source time, observation time, presentation time and browser frame time distinct. Source time records when the owner says the event occurred; observation time supports freshness; presentation/frame time controls explanatory motion.

The presentation clock may be briefly buffered. The inspector does not wait for a creature to arrive.

~~~text
SceneFrame = project(
  qualified state,
  selected observations,
  presentation time,
  viewport,
  layout version,
  choreography version,
  deterministic seed
)
~~~

Use analytical paths and deterministic seeds. Avoid an endless physics integration whose state is difficult to reconstruct.

On bursts, facts precede decoration. Coalesce redundant scans and poses. Preserve failures, parent changes, attempts and terminal milestones in owner history. If the client cannot keep up, replace its projection from a qualified snapshot and expose the gap.

The presentation schedule is bounded, disposable UI state. It is not a durable job/retry queue.

## 10. Replay and recorded activity

Replay depends on retained evidence. Current snapshots alone do not automatically form a reconstructible historical world.

| Source capability | Permitted experience |
|---|---|
| Current state only | Current atlas with observation age |
| Retained events without reconstructible state | Recorded activity timeline with gaps |
| Snapshot plus complete event boundary | State replay in the qualified interval |
| Missing historical relationships | Unresolved relationships, not guessed lineage |

Use the same reducer with a qualified starting state and source cursor boundaries. Version layout/choreography where reproducibility matters. Animation changes must not alter facts.

Display replay timestamp and speed. Separate live operational controls from historical inspection. Returning live reads the current snapshot rather than animating all missed events.

Later features can include a two-minute project recap, a selected team's journey and before/after correction comparison. Assemble summaries from existing milestones and evidence. Optional model narration is a separate bounded summary request, never part of the frame loop.

Full-estate historical replay remains conditional until retention and reconstruction tests pass.

## 11. Rendering technology and reuse

| Layer | Choice | Reason |
|---|---|---|
| Shell/inspectors | Existing React/HTML | Preserve navigation, auth and accessibility |
| World | PixiJS with qualified WebGL backend | Sprites, meshes, batching, scene graph and local animation |
| Characters | Reusable rigs/sprites and procedural gait | Rich motion without full physics |
| Complex detail illustration | Optional Rive after measurement | Designer-authored animation where useful |
| Projection/layout | Client state plus bounded worker when justified | Keep burst processing away from interaction |
| Transport/history | Existing owners | Avoid duplicate infrastructure |

Pixi's current guide recommends WebGL for production and labels WebGPU experimental. Pin the package and verify actual behavior. Do not promise automatic Canvas fallback from an untested version. The HTML explorer is the functional fallback.

Three.js / React Three Fiber is a credible alternative if a comparative prototype demonstrates better comprehension and preference within the same budgets. Phaser is credible if the experience becomes a playable simulation needing game systems. Neither belongs alongside Pixi by default.

Rive has shared offscreen rendering, but many updated instances still need measurement. Avoid one WebGL canvas per bot.

### Original-source precedents

**Gource** shows contributors working on an animated repository tree. Borrow the readable actor/directory/change relationship; it is not a drop-in live web estate renderer.

**AgentMove** maps coding activity into animated zones with a PixiJS frontend. Its README states MIT licensing. It is a useful event-to-character pattern donor; its performance claims were not independently benchmarked here.

Check exact donor files/licenses before reuse. Do not import its hook installers, watchers or permission system wholesale when Mastermind already has owners for those functions.

### Asset production

Author a small original kit: project bases, a few resource props, one creature family, outcome markers and restrained effects. A 3D authoring tool can bake orthographic views, material shading and contact shadows into texture atlases. Compose runtime depth from those layers.

Avoid unique large textures for every project. Recolor/recombine shared assets. Track dimensions, compressed transfer size, decoded texture cost, ownership and license/source in the asset manifest.

## 12. Performance plan

These are initial qualification targets, not measured production capabilities.

### Representative fixture

- 1,000 active session summaries across 30 project regions.
- 10,000 historical summaries navigable through paging, not all histories resident.
- Up to 120 visible actors, with at most 40 fully articulated rigs.
- Up to 40 persistent labels and 200 connection segments.
- Normalized records exclude raw transcripts and terminal output.
- Desktop viewport around 1440 × 900 CSS pixels; initial DPR cap 1.5.
- 100 normalized observations/second sustained and 1,000/second for a ten-second burst.
- Separate typical estate, worst-case text and repeated-error fixtures.

Renderer capacity and source coverage are separate. A synthetic 1,000-session fixture does not prove live sources expose 1,000 sessions.

| Metric | Proposed gate |
|---|---|
| Desktop | Target 60 Hz; report frame-time distribution and missed frames |
| Reduced quality | Stable 30 Hz where 60 Hz does not hold |
| Main-thread animation bookkeeping | p95 under 2 ms/frame |
| Shell input | p95 under 100 ms; no material regression against the same busy shell without Atlas |
| Incremental route code | Initial target under 750 KiB compressed; measure selected build |
| Initial art | Under 3 MiB compressed target; later assets lazy-loaded |
| Incremental JS/worker memory | At or below 128 MiB target on the specified fixture |
| GPU resources | Conservative allocation-ledger target at or below 96 MiB, not exact driver-memory reporting |
| Hidden/unmounted | No continuous world rendering; deliberate source ownership and disposal |
| Repeated navigation | No accumulating contexts, workers, textures, listeners or subscriptions |
| Long session | One-hour soak with stable allocation counts and bounded presentation backlog |

Download size differs from decoded texture cost. One 2048 × 2048 RGBA8 texture uses 16 MiB before mipmaps. A 1440 × 900 target at DPR 1.5 uses about 11.1 MiB for one RGBA8 color buffer. Additional targets and anti-aliasing add cost.

If the first prototype misses budgets, reduce visible detail, texture dimensions and effects before reducing factual fidelity.

### Implementation rules

1. Load renderer/art only on Atlas.
2. Keep per-frame transforms outside React state.
3. Reuse sprites, geometry, textures and motion objects.
4. Keep stable layout anchors; recalculate only on material topology/viewport change.
5. Avoid per-agent blur/glow/masks and constantly rebuilt complex paths.
6. Update text on meaningful changes, not every frame.
7. Do not forward token streams into the world.
8. Generate motion locally: no per-frame network traffic.
9. Profile culling; its CPU cost can outweigh its benefit.
10. Stop settled/hidden rendering while scheduling necessary freshness changes.
11. Limit browser thumbnails to explicit selected views.
12. Test M2 under ordinary load, a second Mac, a lower-power laptop, relevant Chromium/Safari versions and Tauri WebView.

Use a worker for burst reduction/layout when profiling justifies it. Keep rendering on the main thread initially. OffscreenCanvas rendering is a later measured option with input, accessibility and support costs.

## 13. Fault isolation and disclosure

One renderer instance belongs to one mounted view. Bound startup/recovery, use abortable asset loading, slice event work and dispose resources explicitly. Allow at most one automatic context recovery before switching to the HTML fallback; user-triggered retry remains available.

A React error boundary does not isolate GPU failures or CPU starvation. Test context loss, worker failure, missing assets, source floods and visibility changes.

The ordinary Team/Projects view must work even if Atlas never initializes.

Same login does not imply identical source disclosure rights. Filter and allowlist fields before they reach the scene, worker, local search or replay buffer.

Default payloads use typed verbs, controlled labels and opaque resource references. Exclude credentials, full URL query strings, raw terminal output, private browser content and full transcripts. Detail is fetched through the existing authorized owner.

Clear data on access revocation, auth generation or scope changes. Do not leak hidden project names/counts through aggregates. A future presentation mode can redact already permitted data; it grants no new access.

## 14. Accessibility and comprehension

Full, Calm and Off modes preserve equivalent information. Motion Off replaces travel with stable relations and state changes. Respect reduced-motion preferences. Provide pause/stop/hide or update-frequency controls for moving and auto-updating content.

Maintain a real HTML explorer, not just a canvas description. Support keyboard search/selection, visible focus and exact source navigation. Screen readers receive selected milestones rather than every tool event.

Use text/shape as well as color. Avoid flashing failure effects. Sound defaults off. Label paused display explicitly. Stop run and Pause display are different controls.

### Usability gate

Show representative scenarios to 8–12 people unfamiliar with the engineering, without a tutorial. Target at least 80% correct answers on project, leader, helpers, current activity, blockers and whether the outcome is PR-ready, merged, deployed or product-verified.

Measure response time, wrong inferences, motion discomfort and preference. This is a practical design gate, not a statistically certain claim.

Compare the same tasks with the current list view. Atlas should improve situational understanding or make comparable understanding substantially more approachable and engaging.

## 15. Build sequence

All packages below are **proposed**, not dispatched, queued or running.

| Slice | Output | Dependencies | Acceptance |
|---|---|---|---|
| A. Source qualification | Read ports, identity/coverage map, safe fixtures, writer reconciliation | Current integration revision and connected source reads | Known work represented or explicitly outside/unknown scope |
| B. Art/motion slice | Original creature, one project, browser/files/terminal behavior | A's frozen semantics; artist and graphics owner | Beautiful and correctly interpreted without tutorial |
| C. Live project | Real bot → T3 lead → helpers → tools → result | A+B and source access | Exact IDs/receipts, concurrency, failure and return verified |
| D. Estate scale | Grouping, semantic zoom, hierarchy, search and coverage | C | Large fixture clear; omission differs from aggregation |
| E. History/recovery | Recorded activity, qualified replay, reconnect/degraded states | A's history contracts and C | No invented continuity or false completion |
| F. Release proof | Device matrix, accessibility, shell isolation, rollout/rollback | C–E and art refinement | Real consumer journey and measured budgets pass |

### Parallel ownership

One existing integration lead owns contracts and the final user journey. Use disjoint lanes:

- Experience/art: composition, silhouettes, theme assets and motion grammar.
- Graphics: renderer, rigs, paths, camera, lifetimes and adaptive quality.
- Source/projection: identity joins, coverage, streams and safe fixtures.
- App experience: shell integration, inspector, keyboard explorer and source navigation.
- Qualification: factual, failure, performance and comprehension proof.

Avoid relay-only management layers. Route bounded work through qualified existing execution paths. This project does not create another routing plan.

### A1 — Read contract and fixtures

**Inputs:** pinned paths, actual schemas, active integration branch/owner.  
**Output:** normalized projection with lineage, availability, coverage and history capabilities; sanitized fixtures.  
**Held:** runtime ownership changes and new telemetry infrastructure.  
**Pass:** duplicate names, missing parents, partial pages, stale snapshots and auth changes cannot fabricate joins.

### B1 — One-project animation kit

**Inputs:** event-to-motion table, original art direction and A1.  
**Output:** reusable rig, three resource props, movement/work/wait/failure/return behavior and quality levels.  
**Held:** credentials, whole-estate layout and a second renderer.  
**Pass:** motion-off remains comprehensible; outcomes never precede evidence.

### C1 — Existing-owner live adapter

**Inputs:** qualified host/T3/Hermes/Fabric reads, exact selection and A1.  
**Output:** one connected project scene and native deep links.  
**Held:** dispatch, retry, account/provider changes, merge or deployment authority.  
**Pass:** a real execution is traceable from original source to scene and back to evidence.

### D1 — Estate composition

**Inputs:** C1 and qualified paging.  
**Output:** stable project anchors, aggregation, semantic zoom, search and typed relationship lenses.  
**Held:** guessed roster/totals and filesystem-wide scans.  
**Pass:** grouped records and missing source records are visibly distinct.

### E1 — Recorded activity and replay

**Inputs:** retention/reconstruction contracts and epoch/cursor fixtures.  
**Output:** historical activity; state replay only within qualified intervals.  
**Held:** a new history store or guessed causal order.  
**Pass:** restart, retention loss and reconnect preserve visible gaps.

### F1 — Release proof

**Inputs:** exact candidate, actual devices, source coverage and original journey.  
**Output:** measured rendering/shell/memory results, accessibility proof, original result return, rollout and rollback.  
**Pass:** users understand and inspect real work without disrupting the OS.

### Planning estimate

Allow approximately **16–27 person-weeks** across art, graphics, source integration, app experience and qualification. A small coordinated team could plausibly produce the first strong slice in **2–3 calendar weeks** and a hardened estate experience in **6–10 weeks**, depending on source readiness.

These are estimates, not delivery promises. AI workers can accelerate bounded code and fixtures; they do not remove source gaps, art iteration, live proof or usability work. Re-estimate after the measured first slice.

## 16. Hard falsifiers

Fail the release if:

1. An active session beyond the first source page disappears while the UI claims full coverage.
2. Same-named sessions merge or a retry inherits the wrong attempt's result.
3. A queued child looks running, denied write looks saved, or uncertain move looks completed.
4. A stale actor appears to keep working with current certainty.
5. A burst leaves obsolete action poses after failure/completion.
6. Replay conceals missing snapshots, source restarts or retention gaps.
7. Private source data reaches scene/search/worker/history payloads before filtering.
8. Repeated navigation accumulates contexts, subscriptions, workers or textures.
9. Canvas FPS is good while shell input stalls.
10. Context/asset failures crash the shared shell.
11. Users enjoy the animation but cannot distinguish busy, waiting, unobserved and finished.
12. The world cannot open the original session, artifact or evidence.

Also cover independent processes surviving a parent turn, simultaneous tools, multi-host clock skew, duplicate/out-of-order delivery, permission revocation and unknown effects.

## 17. Rollout

1. Clearly labeled simulated art/motion route.
2. One internal read-only project through existing feature controls.
3. Real user-journey proof against original sources.
4. A few projects/source combinations with visible coverage.
5. Larger estate and device qualification.
6. Normal optional Team/Projects view.

Rollback returns to the existing list/office/project experience and disposes the renderer. It does not cancel jobs or change routing. Future operational controls remain consumers of existing command capabilities.

## 18. Deliverables from this commission

- This architecture and build specification.
- A generated art-direction concept image, explicitly illustrative.
- A self-contained interactive motion study with a simulated 38-second story.

The study demonstrates moving helpers, concurrent stations, failure/correction, distinct result milestones, display pause, calm motion, a lost-feed state and project selection.

Its lightweight Canvas2D illustrations make the vocabulary inspectable. It is not the production Pixi implementation, a live connection, a stress benchmark or production acceptance proof. It launches no real work.

Validation completed for this study: JavaScript syntax, fourteen state/control checks across desktop and narrow-screen fixtures, and visual inspection of native canvas rasters. Browser startup was unavailable in this environment, so browser layout, browser-specific rendering and target-device performance remain unverified. The implementation qualification above must establish those properties on the real application.

## 19. Recommended first implementation action

Attach this proposed experience to the current Team/T3/Hermes programme. Freeze A1 against the incumbent integration revision and build B1/C1 as one end-to-end project slice.

Start with a truthful, beautiful story. Then scale its semantics and art system across the estate.

## 20. Sources

Internal source links are immutable unless explicitly a PR. Public documentation was inspected on 9 November 2026. Budgets, estimates and product decisions above are proposals.

### Mastermind

1. [Application manifest](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/app/mastermind_os/package.json).
2. [Team/T3/Hermes/Capacity plan](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/docs/plans/2026-11-08-mmos-team-delivery-integration.md).
3. [OrganizationWorkspace](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/app/mastermind_os/src/organization/OrganizationWorkspace.tsx).
4. [Fabric catalog](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/app/mastermind_os/src/fabric/catalog-contract.ts).
5. [Mission interiors](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/app/mastermind_os/src/fabric/mission-interiors.ts).
6. [T3 Web collaboration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/docs/T3_WEB_COLLABORATION.md).
7. [T3 CLI client](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/integrations/session_bridge/t3_web_client.py).
8. [T3 adapter PR #2356](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2356), observed merged into the integration branch.
9. [Integration PR #2338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2338), observed open/draft.
10. [Reuse-first engineering](https://github.com/mastermindx-market-intelligence/Mastermind/blob/85179e35ce1fd3ddc00e85df5745fee4d5288068/docs/REUSE_FIRST_ENGINEERING.md).

### Public primary references

11. [PixiJS renderers](https://pixijs.com/8.x/guides/components/renderers).
12. [PixiJS performance](https://pixijs.com/8.x/guides/concepts/performance-tips).
13. [React Three Fiber scaling](https://r3f.docs.pmnd.rs/advanced/scaling-performance).
14. [Rive rendering tradeoffs](https://rive.app/docs/runtimes/web/canvas-vs-webgl).
15. [Gource](https://gource.io/).
16. [AgentMove](https://github.com/FoothillSolutions/agent-move).
17. [T3 outside agents](https://github.com/pingdotgg/t3code/blob/main/docs/user/outside-agents.md).
18. [W3C moving and updating content](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html).

### Evidence limits

No live Executive census was available through this session's reader. Installed T3/Hermes versions and whole-fleet telemetry were not independently requalified here. PR proof descriptions were inspected as recorded evidence, not rerun. The source baseline is a point-in-time reference, not a guarantee about later merges/deployments.
