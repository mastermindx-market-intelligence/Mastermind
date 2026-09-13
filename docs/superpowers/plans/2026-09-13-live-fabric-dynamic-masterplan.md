# Live Fabric Dynamic Workspace Implementation Masterplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for the admitted implementation slice. Read the companion specification and current protected Mastermind procedure before source work. The work packages below are not receiver assignments or runtime START receipts.

**Goal:** Build a real, remotely accessible CEO-and-agent operating workspace that displays actual dialogue, dynamic delegation, routing and waiting relationships, and supports exact safe interaction while the company continues operating with the UI closed.

**Architecture:** Extend existing Executive, Operator Harness, Company Dialogue, Model Router/Capacity, Steward and Business-auth owners. An isolated React frontend and later Tauri client consume qualified projections and send finite admitted commands; neither becomes another runtime or transcript system.

**Tech Stack:** Existing Python/Starlette integration and authentication; React/TypeScript/Vite; React Flow; TanStack Query/Virtual; a small Zustand presentation store; Vitest/Testing Library/Playwright; Tauri for the native shell. Existing reverse-proxy/private-network owners supply deployment transport.

**Spec:** `docs/superpowers/specs/2026-09-13-live-fabric-dynamic-orchestration-addendum.md`, read with the original `2026-09-13-mastermind-live-fabric-design.md` where not narrowly superseded.

**Source basis:** Mastermind `f087f9cf90a8fc7a81273c2576eefa6d06b54d9e`; source carrier PR #595. This is a program-level implementation masterplan plus first-slice contract, not a claim that every downstream provider-specific executable plan or source lease is complete.

## Global constraints

- Existing Executive OS remains lifecycle/admission/event/effect/retry authority.
- Existing Agent OS remains organizational memory; no new workstream or CEO memory database.
- Preserve the singular current-operator query; enumerate work through the existing plural observation owner.
- No arbitrary existing App Server adoption, provider-home scan, transcript scrape or account switch.
- Provider-visible response content, transport delivery and accepted company action are distinct.
- No provider turn is started by a read or spectator subscription.
- Current source, capability, budget and exact-session rules govern effects; a mockup or plan grants none.
- Reconcile effect uncertainty through the same operation/owner; never retry through another host or provider.
- Every delivered capability includes real input, a real visible consumer, negative proof and explicit limitations.
- Synthetic previews, source tests, CI, merge, installation, production proof and acceptance remain separately recorded.
- The complete target includes real dialogue and remote interaction, not a permanent read-only dashboard.

## 1. Delivery structure and accountable continuation

Sol is accountable for this program's architecture, sequencing, review and exact next action. Domain ownership below names the existing implementation boundary, not evidence a particular worker session is currently active. Before source START, resolve the actual carrier, receiver, writable paths, source version, approved effect scope and continuation path. Missing placement is reported as placement debt, never a fictional executing owner.

A task may have several implementation steps but a release must create one useful capability. Dependency setup, schema parsing, test fixtures and style tokens are folded into the release that needs them. They are not separate shipped milestones.

The expanded outcome is delivered in this order:

| Package | Useful result | Key prerequisite |
|---|---|---|
| D1 | One real mission room with genuine managed-session dialogue, topology and evidence | Correct source origin; qualified managed provider observer; authorized read projection |
| D2 | Dynamic child creation and result-return choreography visible from real admission | Existing child-work/capacity/return owners and allowed concurrency |
| D3 | Hosted remote viewer from a non-local network | Existing application authentication and fixed private upstream service path |
| D4 | One exact operator message from the hosted workspace, with effect reconciliation | Current command/admission owner; action-time principal and target validation |
| D5 | Route inspection, dry-run comparison and reviewed future-policy changes | Existing ModelRouter/Capacity/source policy ownership |
| D6 | Durable CEO conversation and research-to-principal delivery journey | Exact CEO responsibility binding; qualified research and principal lanes |
| D7 | Parent recovery and approved continuation with UI closed | Existing Wake/continuity and real stale-effect fencing |
| D8 | Signed Mac client using the same hosted backend | D3/D4 contract plus independent native-client qualification |
| D9 | Rich operator tools and bounded team/routine/instruction editing | Individually admitted provider and canonical-owner capabilities |
| D10 | Sustained useful multi-provider/multi-host operation | Accepted lower-level journeys and a bounded live campaign |

D3 may run in parallel with D2 after D1's read contract is stable. D5's non-mutating route viewer may advance independently of D4's action gate. Figma and deterministic frontend development are not blocked by a provider-account ceremony, but neither closes a live milestone. Mac packaging does not gate useful web delivery. An unsupported optional provider does not block the first qualified provider lane.

## 2. Source map: reuse, extend, and do not touch incidentally

| Existing source or carrier | Required use | Boundary |
|---|---|---|
| `control_plane/operator_harness_contract.py` | Actual identity, EventCursor and NormalizedEvent semantics | No second generic session/event schema; rich-interface changes need its owner |
| `control_plane/codex_operator_adapter.py` | First managed observer candidate | Do not start an extra provider process for viewing; preserve private realm/profile |
| `control_plane/operator_harness_orchestrator.py` | Existing operation/receipt path | UI reads cannot claim, acknowledge or complete work |
| `control_plane/executive_operator_supervisor.py` / `executive_worker_broker.py` | Current admitted execution and parent-owned control | Do not add a frontend-specific supervisor |
| `control_plane/model_router.py` / `config/executive_worker_routes.json` | Logical route, suitability, exclusions and reason codes | A pure route is not an atomic capacity reservation |
| `integrations/slack_agent_dialogue/engine_v2.py` and `company_dialogue_runtime_binding.py` | Company semantic messages and binding applicability | Do not derive consumption from ordinary chat prose |
| `integrations/slack_agent_dialogue/executive_terminal_return_projector.py` | Existing canonical terminal-return projection | Do not create a second return injector |
| `integrations/mastermind_steward_app/app.py` / `server.py` / `projection.py` | Existing authenticated read/application owner | A new browser resource contract needs review; preserve current MCP surface |
| `integrations/business_mcp_auth/` | Existing principal/resource/scope validation | No separate Live auth/token database |
| `scripts/chairman_control_room.py` / `control_plane/chairman_control_room.py` | Incumbent local UI/composition/cache and navigation | No public exposure of legacy loopback API; preserve Today and source validity |
| #508 family | Plural recorded mission/descendant read | Release/installation are distinct; missing detail fields cannot be invented |
| #546/C3 family | Optional enrolled browser census | Local observation scope is not control or full transcript entitlement |
| Existing Web-Sol / RuntimeBinding / Wake carriers | Exact ChatGPT Web research and current office target | No newest-tab selection or API-run relabeling |

Proposed new frontend root: `ui/live-fabric/`. Proposed narrow Python display helpers: `control_plane/live_fabric_projection.py` and `integrations/mastermind_steward_app/live_views.py`. These are intended locations, not existing modules or source reservations. Run a fresh exact path/rename/branch/worktree/process census before implementation; integrate through the actual owning source carrier rather than racing another session.

The screenshot's missing local runtime path is an origin/configuration investigation, not a database-creation task. Resolve the intended installed runtime service, source identity and authorized read endpoint. A different checkout containing no database is not repaired by creating empty lifecycle state. Record the selected authority instance, observed service generation and allowed scope without publishing private filesystem details.

## 3. First-slice contracts: what frontend and owner implementations agree on

These are proposed **presentation interfaces**, not new canonical registries or currently installed endpoints. IDs and lifecycle values come from their existing owners. Their wire encoding is fixed only after the current source owner verifies exact allowed fields and client authorization.

### Display boundary

```ts
// Proposed types in ui/live-fabric/src/contracts/display.ts.
// Source-qualified views, never executable grants or new lifecycle records.
export type ItemClass =
  | 'message'
  | 'tool_activity'
  | 'visible_plan'
  | 'system_receipt'
  | 'advisory_summary';

export type ContentState = 'partial' | 'complete' | 'redacted' | 'unavailable';
export type Coverage = 'complete_in_scope' | 'partial' | 'unavailable';

export interface SourceRef {
  owner: string;
  ref: string;
  revision: string | null;
}

export interface DisplayItem {
  key: string;                 // owner + session/generation + item/block identity
  source: SourceRef;
  scopeRef: string;
  attemptRef: string | null;
  turnRef: string | null;
  parentItemRef: string | null;
  senderRef: string | null;
  recipientRef: string | null;  // null if source does not establish a recipient
  itemClass: ItemClass;
  contentState: ContentState;
  text: string | null;         // qualified safe display text; never arbitrary payload
  observedAt: string;
}

export interface MissionSnapshot {
  scopeRef: string;
  publicationRef: string;
  coverage: Coverage;
  items: readonly DisplayItem[];
  sourceRefs: readonly SourceRef[];
  // Topology/obligation/route sections retain their accepted source DTOs.
  // The owning integration fixes those exact adapters before the D1 source plan.
}
```

Keep null recipient, unavailable content and partial coverage meaningful. A title or natural-language mention cannot fill these fields. Do not lexically order opaque revision strings. A completed item wins over its own partial buffer only under the same source identity/generation; an unrelated final-looking item cannot replace it.

The production transport has three independent operations: read an authorized mission snapshot; subscribe to that mission's qualified updates; and obtain/read an owner-native action receipt. Mutating preparation/execution is added in D4. Do not ship a generic proxy that lets the browser invoke every MCP tool.

### Proposed UI composition

```text
ui/live-fabric/src/
  app/Workspace.tsx                 shell, mission selection and layout
  contracts/display.ts             source-qualified display types only
  transport/liveReadClient.ts      bounded existing-owner read/stream adapter
  state/presentationStore.ts       selection, panels, graph positions, replay mode
  dialogue/DialoguePane.tsx        safe, virtualized content and source classes
  dialogue/itemProjection.ts      partial/completed source-item reconciliation
  topology/MissionCanvas.tsx      graph/list selection and explicit edge semantics
  topology/layout.ts              bounded structural layout, not runtime inference
  obligations/WaitInspector.tsx    actual obligation and target/recovery detail
  evidence/EvidenceDrawer.tsx      exact artifact/source/version links
  router/RouteInspector.tsx        existing RoutingDecision and claim readback
  ceo/CeoWorkspace.tsx             later office conversation and delegation cards
  actions/ActionTray.tsx           later preflight/receipt view; no local dispatch rules
```

Do not introduce all later files as empty scaffolding in D1. Create each with its first real consumer. The shared package manifest, TypeScript/Vite/test configuration and build-asset integration belong to D1's UI delivery, with its own review and exact dependency lock.

## 4. D1 — authentic mission room and dialogue

**Mission:** See one authentic managed session's actual emitted content next to its mission, recorded descendants, event receipts and exact evidence.

**Source/effect envelope:** Read-only observer and frontend work. A real-provider canary is a separately admitted small test operation through the existing owner. The GUI never starts that provider while opening a view.

**Files:** Create the display projection/helper and first frontend files above; extend only the current provider/application owners' permitted seams. Tests: `tests/test_live_fabric_projection.py`, `tests/test_live_fabric_read_views.py`, and `ui/live-fabric/src/dialogue/itemProjection.test.ts`, `ui/live-fabric/tests/mission-room.spec.ts`. These names are planned source paths.

**Interfaces:** Consume exact `NormalizedEvent`, `EventCursor`, plural mission read and already-qualified visible item content. Produce the bounded authenticated MissionSnapshot and safe frontend rendering. The adapter owner must freeze the actual provider event-to-content mapping from real version-qualified fixtures; accepting an arbitrary `payload_redacted` dictionary is forbidden.

- [ ] Establish the installed source origin and exact managed test session; prove that reading it causes zero provider starts/resumes/turns and does not consume the primary adapter's control stream.
- [ ] Capture only authorized, non-sensitive actual event/item fixtures with immutable source/version evidence. Include a parent response, a tool activity item, a completed item replacing partial content, and an unknown event type.
- [ ] Write RED tests for wrong Attempt/generation, unavailable body, unjoined recipient, stale scope response, completed-block preservation and unknown event refusal. For each, retain a working positive fixture.
- [ ] Implement the smallest owner-side safe projection. Enforce byte/row limits and authorization before serialization; missing source does not become an empty successful list.
- [ ] Build the graph/list and DialoguePane together. Selecting a source item selects its actual node or reports an unjoined observation. Use the same underlying snapshot for both views.
- [ ] Add integrated HTTP tests with the real authentication middleware: valid principal/scope, wrong scope, revoked principal during await, denied fields, bounded output, and zero mutating owner calls.
- [ ] Run actual browser tests for keyboard selection, partial/completed rendering, scroll stability, reconnect, narrow width and degraded source. A missing browser must fail the required-browser campaign, not skip to a green acceptance.
- [ ] Install the accepted candidate through the existing deployment owner and inspect the real admitted canary mission from the actual browser. Verify content against the source receipt and preserve the scope/coverage shown.

A concrete proposed UI regression test, not a claim it has been implemented:

```ts
import { expect, test } from 'vitest';
import { reconcileItem } from './itemProjection';
import type { DisplayItem } from '../contracts/display';

const partial: DisplayItem = {
  key: 'sample-owner:sample-attempt:g1:item-1:block-1',
  source: { owner: 'sample-owner', ref: 'item-1:block-1', revision: '1' },
  scopeRef: 'sample-mission', attemptRef: 'sample-attempt', turnRef: 'sample-turn',
  parentItemRef: null, senderRef: 'sample-worker', recipientRef: null,
  itemClass: 'message', contentState: 'partial', text: 'First draft',
  observedAt: '2026-09-13T12:00:00Z'
};

test('source-accepted completion replaces rather than appends partial text', () => {
  const completed = { ...partial, contentState: 'complete' as const,
    text: 'Corrected final response', source: { ...partial.source, revision: '2' } };
  const result = reconcileItem(partial, completed, 'same-source-newer');
  expect(result.text).toBe('Corrected final response');
  expect(result.contentState).toBe('complete');
});

test('late older observation cannot reopen a completed item', () => {
  const completed = { ...partial, contentState: 'complete' as const,
    text: 'Final response', source: { ...partial.source, revision: '2' } };
  expect(reconcileItem(completed, partial, 'same-source-older')).toEqual(completed);
});
```

Proposed pure signature: `reconcileItem(current: DisplayItem, incoming: DisplayItem, order: 'same-source-newer' | 'same-source-older' | 'duplicate'): DisplayItem`. The order argument is supplied only after transport/owner identity and revision qualification. This helper cannot decide cross-source authority, authorization or generation validity. Its tests are necessary UI regression proof, not a security proof of the qualifier.

**Acceptance:** Real response text, real source links, real recorded topology and explicit unknowns in one useful mission room. No fabricated running count, transcript, owner or production status. **Not sufficient:** a fixture demo, a health ping, a new endpoint with no source, or a source merge.

**Return to Sol:** Source identity wrong, unsupported provider history/stream contract, content rights unclear, source custody contested, or required content not projected. Return the exact finite owner extension needed; preserve disjoint UI progress and do not make a second reader.

## 5. D2 — spawn, fan-out and return as a visible workflow

**Mission:** A parent delegates bounded work; the user sees proposed children become admitted and then observed sessions, sees their real messages/results, and sees which parent consumed each return.

**Existing seams:** Executive child-work admission, current broker/supervisor, provider native-subordinate observations, Company Dialogue terminal-return projection and Wake. UI additions are source relation/obligation views, not another spawn engine.

- [ ] Choose a small currently lawful parent/child canary. Declare exact depth, concurrency, spend and workspace limits in its existing admission, not in frontend settings.
- [ ] Test proposed/admitted/materialized/observed distinctions and at-most-once semantic child admission under duplicate requests. A delivered commission with no pickup stays unconsumed.
- [ ] Add exact native-helper lineage to the display where the adapter actually supplies it. A helper without a join remains unjoined; it does not become a fake Job.
- [ ] Test parallel read-only helpers first where allowed. Concurrent source writers require independently owned workspaces and the current runtime/source policy's actual permission.
- [ ] Drive one child return through its existing projector, exact parent obligation, consumption and next permitted edge. Read the resulting canonical evidence in the mission room.
- [ ] Test child failure, duplicate return, parent generation change and late output after a child was stopped. No prior child result may satisfy a different successor by name.

**Acceptance:** One real parent-to-child-to-parent loop and the source-supported topology visible as it changes. Native helpers and independently admitted workers remain distinguishable. The sample prototype's larger swarm is not claimed live from this small canary.

## 6. D3 — hosted read access from outside the local network

**Mission:** Chris signs in from a non-local network and sees the same qualified mission without port forwarding a privileged local dashboard.

**Files/owners:** Existing authenticated application/Business auth, deployment reverse proxy, private host transport and service discovery. New finite resource views belong in the existing application integration, not a generic Node/MCP proxy. Packaging uses the frontend built by D1.

- [ ] Resolve the real VPS/deployment target, current proxy/issuer and allowed private upstream service. Do not assume host names, public ports or credentials from old chats.
- [ ] Bind the gateway to fixed approved owner services; reuse current principal/resource/scope verification. Define browser session establishment, renewal and revocation through the existing auth owner.
- [ ] Publish only the finite read surface and static assets behind HTTPS. Strip untrusted identity headers; deny arbitrary upstream URLs, paths and tool invocation.
- [ ] Test wrong user/scope, direct unauthenticated origin access, cross-origin requests, old cache after logout, stream revocation, upstream outage and opaque private identifier leakage.
- [ ] Exercise an actual off-LAN browser journey, record the public service/build identity and prove that UI access did not move, copy or create the authoritative runtime database.

**Acceptance:** The real remote read journey works and degraded-origin behavior is honest. A working Tailscale-only route proves private enrolled-device access, not public browser access without a network client. A tunnel alone is not user authorization.

## 7. D4 — one exact remote operator message

**Mission:** From the hosted UI, send one authorized message to a verified operator at its supported turn boundary and see the actual admission, delivery and response receipts.

**Existing seams:** Current authenticated action owner, Executive operation intent, exact RuntimeBinding, supported provider steer/begin-turn/message semantics and same-operation reconciliation. New UI code is `actions/ActionTray.tsx` and an exact-command client; no generic terminal API.

- [ ] Freeze one supported provider action with its real preflight and effect class. A status question that starts a model turn is an action, not a GET.
- [ ] Test principal, target, payload, policy and obligation preimage validation, including a changed binding after preflight.
- [ ] Prove semantic single-consumption for one obligation even when two browsers use different request keys. Repeated identical transport requests return the same owner result; changed payload conflicts.
- [ ] Exercise normal success, refused action, lost reply after possible provider acceptance, client restart and restored receipt lookup. Disable automatic retries and cross-host/provider fallback for uncertainty.
- [ ] Verify that ordinary in-envelope action does not require redundant Chairman ceremonies, while new privilege/budget/irreversible scope still invokes the existing appropriate approval.

**Acceptance:** One real exact-target interaction from the external network, with no duplicate effect in the exercised negative cases. Do not claim every provider or bulk command is supported. Later interrupt/stop/cancel/pause-admission controls get their own target semantics and proofs.

## 8. D5 — a useful, honest router console

**Mission:** Understand actual placement and compare a prospective change before it affects future work.

**Interfaces:** Use `ModelRouter.route(WorkRequest(...))`, `RoutingDecision.to_dict()` and the separately qualified Capacity/Executive claim. Existing fields include `suitability_tiers`, `reason_codes`, `excluded_worker_ids`, policy/profile digests and cognition-route information. Do not make up absent historical per-candidate scores.

- [ ] Render a source-qualified recorded decision and its separate concrete claim/binding. Missing route evidence is not regenerated under today's policy and presented as history.
- [ ] Add a pure simulation path using an explicit policy revision and bounded request. Test zero Job, reservation, session, Wake and provider effects.
- [ ] Compare original/proposed suitability and exclusions with identical request inputs. Hold unrelated variables constant so the policy-change explanation is meaningful.
- [ ] Add a reviewed policy-diff workflow through the existing source/configuration owner. Validate the expected preimage, scope and current policy before applying.
- [ ] Prove new admissions use the accepted new revision while in-flight Attempts remain pinned. Rollback is a new reviewed policy transition, not editing historical receipts.

**Acceptance:** An actual route can be explained, a hypothetical change stays hypothetical, and one separately admitted future-policy update is visible through exact readback. “Best model” without capability/budget/capacity evidence fails the journey.

## 9. D6 — CEO office and research-to-Fable program delivery

**Mission:** The Chairman speaks to one durable CEO responsibility and watches it commission research, adjudicate the result and route a justified principal build without manual prompt carriage.

**Scope:** Provider-neutral office presentation and exact current role binding. No final CEO model is selected by this plan. The existing cognition/budget default remains until a separate accepted change qualifies a successor implementation.

- [ ] Bind the office UI to the existing logical Meta-CEO responsibility and its exact current surface. A new chat title is not a new office or binding.
- [ ] Package progressive-disclosure context from current procedure, Agent OS and source/evidence owners. Keep the complete corpus outside the CEO's default prompt; admit referenced detail on demand.
- [ ] Qualify candidate CEO implementations against the same authority, tool, source, recovery and useful-outcome rubric. Record requested versus served model and per-surface limitations.
- [ ] Exercise one approved research commission. ChatGPT Web Pro is used only when its exact Web-Sol session/mode path is proven; an API alternative is labeled and budgeted as a distinct route.
- [ ] Require an immutable research artifact with sources, decisions, open risks and exact build acceptance. The designated integrator consumes it before principal implementation begins.
- [ ] Where ambiguity genuinely justifies it, route to Fable with the accepted artifact and bounded source/workspace plan. Otherwise use a less-scarce capable route. Show the actual child graph and returned artifacts, not a separate Fable queue.
- [ ] Return independent review and production proof to the appropriate parent; record the final ruling and durable next action.

**Acceptance:** The demonstrated chain is Chairman → exact CEO office → qualified research → adjudicated artifact → principal/bounded workers → evidence → parent acceptance. No actor claims another model's hidden reasoning, web mode, permissions or independent review.

## 10. D7 — the UI can close and the program still advances

**Mission:** Approved work survives a closed GUI, unavailable reasoning session and controlled transport interruption without Chris becoming the message bus.

- [ ] Use existing deterministic obligation/return mechanisms; successful progress must not depend on the model remembering to post a Slack status.
- [ ] Close every viewer during a real child return and prove exact parent wake, consumption and explicit next edge through the existing owners.
- [ ] Make the current parent reasoning target unavailable in a disposable approved scenario. Preserve its logical responsibility and unresolved work.
- [ ] Reconcile outstanding effects and demonstrate actual old-writer fencing at the workspace/provider/executor sinks before transfer. Lease expiry alone is not sufficient.
- [ ] Bind a qualified successor and prove that a late old target cannot issue a conflicting action or write. An uncertain effect remains isolated on its original operation.
- [ ] Confirm a child STOP does not stop siblings, and parent-active/no-successor re-enters the accountable responsibility without letting an old watcher originate new work.

**Acceptance:** Useful work advances through one real recovered parent loop with the viewer closed. A changed owner label or delivery acknowledgement is not recovery. A dead session must not be the only possible issuer of its own release receipt; use the existing accepted recovery policy or deliver its finite missing primitive through its owner.

## 11. D8–D10 — native parity, rich tools and sustained operation

### D8: Native Mac client

Share the web UI and API. Add only a narrow native adapter, signing/notarization, secure session storage through the existing credential owner, exact deep links, notifications and approved multi-window behavior. Test WKWebView content policy, client currentness, origin/IPC separation, token revocation, sleep/wake, update rollback and remote access. Chrome qualification does not transfer automatically. Closing/updating the client does not restart Executive services or migrate their database.

### D9: Rich tools and editable organization

Add browser/terminal/files/diffs individually through proven adapters. Viewing terminal output is not permission to inject input. Rich artifacts are isolated from the privileged origin. Team edits, routines and instruction proposals write through their existing owners, with exact preimages, review, rollback and current-attempt pinning. Routine timezone/missed-run/overlap semantics stay in the existing scheduler. Never create a second team, prompt or routine database in the frontend.

### D10: Sustained live qualification

First an approved short canary, then a proposed 24-hour interval, then a proposed 72-hour interval only after acceptance. These intervals are not scheduled or executed by this records work. Include authentic useful tasks, GUI absence, a worker crash, parent succession, source outage, capacity exhaustion, a changed binding and uncertain-action reconciliation.

Measure useful accepted outcomes, manual relay/account-selection events, result-to-consumption latency, false-currentness, lost/duplicate returns, action duplication, source coverage, resource overhead, cost evidence and recovery correctness. Distinguish measured figures from estimates and keep secrets/raw unrelated transcripts out of analytics.

## 12. Integration, review and release discipline

Each implementation PR names its one useful result, exact source paths, actual receiver/custody, dependent contracts, allowed effects, negative controls, production evidence and return condition. Development fixtures and the Figma scenario must use one shared set of identities/counts/content classes so design drift is detectable.

For each code task: write the failure discriminator, run RED against the unmodified behavior, implement the minimal scoped change, run GREEN and regressions, record the exact candidate, and review it against user intent. Source tests that pass by disabling the real feature are invalid; retain a positive authentic path. New frontend tooling does not authorize changes to the repository-wide CI or dependency owners without a scoped integration.

The first code plan must freeze the source-qualified topology and obligation DTO adapters that remain source-owner-specific in Section 3. That is a finite discovery/contract step, not permission to fabricate fields. It may proceed on disjoint UI code using marked fixtures while the real owner mapping is reviewed. D1 acceptance still requires the real producer.

No new default worker, account, host, privileged service, production installation, public network exposure or database migration is authorized by this masterplan. The source/architecture carrier remains #595. Current #508/#546 and adjacent owners are dependencies, not inherited workers.

## 13. Current pass and exact continuation

This pass supplies the expanded system design, implementation masterplan and event-driven visual storyboard. It does not claim source implementation, passing product tests, live session streaming or an external deployment. The original 72-case matrix remains required/unexecuted; its relevant cases are reused rather than replaced by a new test authority.

Next, build the revised Figma mission-room choreography in the existing file from the storyboard: CEO intake, research route, actual-message display classes, principal handoff, child appearance, waits, returns and consumption. Then lock the first source-qualified D1 executable plan against that exact interaction contract. Do not substitute another static card gallery or repeat a conceptual approval loop.
