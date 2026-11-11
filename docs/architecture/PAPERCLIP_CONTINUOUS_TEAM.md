# Mastermind OS: Paperclip management, Hermes execution

Status: **engineering integration implemented in source; installed runtime cutover not performed**.

Chairman assignment: 9 November 2026, continuation of Mastermind #2373 and its comment 6754900984. Work is owned by `mmos-paperclip-control-integration-20261109-c4` on `sol/web-mmos-paperclip-control-integration-20261109-c4`. The governing procedure remains pinned to `494d095813dad415938800fa0e4d2719497738fa`; source construction starts from `5257967eb23d10418dc2326bb7a7b31f7e6a5915`.

This is an implementation amendment to the existing Mastermind OS programme, not a new operating system, task registry or bot fleet. See the [phase plan](../plans/2026-11-09-paperclip-continuous-team-integration.md), [existing OS masterplan](../../research/mastermind_os_estate_audit_2026-10-21/MASTERPLAN.md), and the [company design](../design/MASTERMIND_OS_ALWAYS_ON_COMPANY_WORKSPACE.md).

The current assignment changes the earlier **presentation-only** Paperclip recommendation: Paperclip is now the intended company/work management owner. It does not replace the Hermes agent engine, Executive admission, Capacity placement, Agent OS continuity, GitHub source custody or source-system permissions. Tests, canaries and live-result demonstrations are explicitly deferred for this engineering pass. That waiver is not a production-acceptance statement or a repository-protection bypass.

## 1. The product and ownership decision

**Mastermind OS is the product. Paperclip is its company-management donor and service. Hermes remains the bot runtime.** The user should not operate three loosely connected applications or create a new bot each time a new company view opens.

Target responsibilities:

| Capability | Intended authority | What changes |
| --- | --- | --- |
| Company, reporting relationships and company work views | Paperclip | Replace the bespoke company-management presentation and duplicated business roster. Preserve source company/agent IDs and join them to existing runtime profiles. |
| Business goals, project coordination, issue hierarchy and work status | Paperclip | Use the existing company/project/issue records, not a mirrored task database. Map an existing OS `work_ref` when one already exists. GitHub plans/evidence and Executive Jobs/Attempts remain their own records. |
| Routine definitions, business wake policy and run history | Paperclip after explicit wake-owner cutover | Transfer each business schedule once. Fence the previous trigger owner before enabling the successor. Reading a routine is not activating it. |
| Agent execution, session history, durable memory, skills and tool permissions | Hermes | Retain the enrolled profile, native session database, existing memory and actual tool/provider configuration. Do not clone or bootstrap another twelve agents. |
| Admission, execution grants, Job/Attempt/effect ownership and cancellation | Existing Executive owners | Paperclip coordination must enter the real existing admission path before unattended execution is enabled. A UI ownership label is not that binding. |
| Physical accounts, model pools, usage-window limits and placement | Capacity Fabric | Reuse the actual selected account/model binding; Paperclip cost displays are observations, not authority to spend or an independent account router. |
| Original goal, plan adoption, pending work and original-parent acceptance | Agent OS and existing project/continuity owners | Consume the existing continuity interfaces. An issue marked done does not replace original-parent acceptance. |
| Source code, PR/review/merge/release evidence | GitHub and current publisher | A Paperclip status or run ending does not merge or deploy code. Preserve normal release controls. |
| Source-document access, edits, comments and sharing | Actual source-system owner | Do not infer read/edit/share permissions from company membership or a connected human account. |

A *runtime process supervisor* and a *business work scheduler* are different things. Do not delete `integrations/hermes_runtime/supervisor.py`, its service lifecycle or profile-isolation machinery simply because Paperclip takes over business work coordination. Those components keep the actual Hermes process and identity safe. Likewise, `integrations/hermes_leadership/continuity.py` is not a competing company board: its original-goal and pending-work responsibilities remain necessary.

Existing native leadership tools in `integrations/hermes_leadership/native.py` and organization views in `organization.py` are adaptation seams. Their company-facing projections can consume the Paperclip-owned company/work information; their installed registration and source custody must not be reset. No runtime/leadership source file is removed by this contribution.

## 2. Connected source architecture

Implemented path:

```text
Mastermind OS / Team
    ├─ overview, people, goals, projects, work and task discussion
    ├─ routines, run/revision history, artifacts and activity
    └─ existing-agent / Hermes migration inspector
            │
            ▼
Existing MissionHost.company contract
    ├─ web: existing acquisition bearer + fixed Workspace routes
    └─ macOS: existing NativeAuth + fixed Tauri commands
            │
            ▼
Existing audited Workspace app and outer Executive path fence
    ├─ current Workspace principal and membership
    ├─ sealed operator company + source-principal binding
    └─ request-scoped PaperclipWorkspace service
            │
            ▼
One configured existing Paperclip instance and company
    ├─ native source records and source ACLs
    └─ one bounded optional backlog-create command
```

There is no new local company database, snapshot replication job, webhook listener, retry queue, dispatcher, auth session, browser poller or daemon. The service reads the existing source on explicit page selection/refresh. Optional backlog creation uses Paperclip's native create idempotency key and the OS's existing durable pending-pointer store.

The intended execution connection is **not claimed implemented by the above diagram**:

```text
Paperclip work / routine wake
    → existing, properly bound admission and placement owners
    → qualified existing Hermes runtime interface
    → retained issue execution context
    → original task / room result receipt
    → original-parent acceptance
```

The source inspector identifies these execution bindings as requirements. Merely installing the upstream `hermes_gateway` adapter would not establish Mastermind's Executive/Capacity admission or result consumption. No fabricated admission endpoint or second dispatcher is introduced to hide that gap.

## 3. Donor qualification and exact interfaces

The implementation API pin is Paperclip `d69631b01b9c658f80bf8bed389863dce82643e1`, package generation `2026.1106.0`. It is the revision reported by the existing integration investigation, not the later presentation-research pin `ad440d4e91339e2206ab58640d50fcbb6f61b83c`.

Inspected primary source at the implementation pin:

- [Issue API](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/issues.ts): company-scoped list, status/project filters, bounded limit/offset, `sortField=updated`, issue reads and original comments.
- [Issue validators](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/packages/shared/src/validators/issue.ts): native issue-create `idempotencyKey`; comments have different wake/interrupt implications and are not exposed as writes here.
- [Agent API](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/agents.ts) and [agent validators](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/packages/shared/src/validators/agent.ts): current agents, configuration/revision views and update contracts. The general adapter/configuration PATCH does not provide an expected-revision compare-and-swap field.
- [Routine API](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/routines.ts) and [types](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/packages/shared/src/types/routine.ts): definitions, runs and revisions. Raw restored webhook secret material is not projected into OS history.
- [Artifacts API](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/artifacts.ts) and [types](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/packages/shared/src/types/artifact.ts): bounded cursor envelope, nested issue/project/creator summaries and source links. No arbitrary preview URL proxy is created.
- [Activity API](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/activity.ts): latest bounded company activity. This is not advertised as complete history.
- [Health route](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/server/src/routes/health.ts): observed full `commit` value. Write capability is offered only when it matches the qualified source revision.
- [Hermes adapter](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/packages/adapters/hermes/README.md) and [gateway executor](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/packages/adapters/hermes/src/gateway/server/execute.ts): existing-service HTTP/SSE transport, session-key strategy and per-run idempotency headers.

No donor code or assets have been copied into the product. The small integration modules are original adapters over the pinned public API. Actual upstream package adoption must retain its required license notices and existing dependency/security controls.

## 4. Hermes: preserve identity, separate project contexts

The existing private Mastermind native bridge uses `hermes-gateway-v1`. The official Paperclip `hermes_gateway` adapter uses an **HTTP/SSE API server**. Pointing the HTTP adapter at the private native socket or dashboard URL is not a protocol conversion.

The upstream package is `@paperclipai/hermes-paperclip-adapter`; the older separate gateway package is a compatibility shim, not a reason to install a second runtime. For a persistent enrolled bot, adopt its existing supported HTTP/SSE service rather than using `hermes_local` to spawn a fresh CLI process on each heartbeat. The previously inspected local adapter's execution flags are not silently adopted by this integration.

Session policy:

1. Keep the original supervisor conversation for direct Chairman steering and original result returns.
2. Use issue-scoped retained execution contexts for distinct work items. A persistent identity is not one unbounded transcript shared by every project.
3. Preserve company, agent, profile, source issue, OS work reference, original parent, execution attempt and return references. These are joins across existing owners, not a new identity store.
4. Consume the native/T3/continuity changes on #2345/#2374/#2375 through their actual interfaces when eligible. Do not fork their session, streaming, stop or pending-operation mechanisms.

The migration inspector reads one source-visible existing agent and prepares its target relationship. It displays the current adapter/status, retained profile and supervisor references, target `hermes_gateway`, issue context strategy and outstanding owner bindings. Its state is `PREPARED_NOT_APPLIED`; it has no Apply endpoint, no token fields and no bot-creation action.

### Why an adapter change is not a blind PATCH

At the pinned upstream revision, the general agent PATCH has no general expected-revision/CAS argument. Do not invent `If-Match`, `expectedConfigRevision` or a preflight hash and then claim concurrency was enforced. The inspector's observed digest is diagnostic only.

A future source/configuration migration must reconcile the actual existing configuration writer and active runs/effects before one authorized mutation. Keep the agent paused and its heartbeat disabled during configuration adoption; retain the exact existing agent/company ID. Do not copy private credentials into comments or config examples. The gateway executor expects a resolved `apiKey`/`token` string; an arbitrary environment placeholder or secret-reference object is not assumed to work unless the real upstream secret owner resolves it.

The upstream adapter's `Idempotency-Key` is a run identity. It is not evidence of business-task exactly-once execution across future heartbeat runs. The original work/attempt/effect owners remain necessary.

## 5. Implemented source surface and permissions

### Fixed transport

`GET /workspace/company/current` accepts a closed view selection. `POST /workspace/company/command` accepts only `create_backlog`. Both remain inside the existing audited Workspace authenticator, current membership gate, outer path fence and installed policy. Native and web clients use their existing acquisition token owners.

Paperclip's private source credential stays in the host. The browser/native webview receives no bearer, adapterConfig, environment, secret bundle, raw runtime logs or arbitrary activity detail. Sensitive source text is not copied into a new cache. Allowed text is projected through bounded fields and rendered as text, not arbitrary source HTML.

Each request binds to one configured origin, one company and one actual Workspace subject/client. HTTPS is required except for explicitly configured numeric-loopback access. Redirects and inherited HTTP proxy variables are refused. A local trusted source requires an explicit operator binding; being signed into any Workspace account is not enough.

Source reads and writes recheck current identity, permission, expiry, installation binding and credential continuity. Binding or credential changes revoke the in-flight result; an uncertain write remains uncertain. Reference joins are exposed only for records that the source actually allowed this principal to read. A global configuration roster is not broadcast to every signed-in client.

### Views

The new Team route includes Overview, People, Work, Projects, Goals, Routines, Artifacts and Activity. Task, routine and runtime drilldowns retain their original source IDs. Task detail also reads original work products and bounded run summaries, including source output links and original run/workspace references; it excludes raw result JSON, private logs and tool output. The work view provides list/board presentation and source filtering; it does not implement a cosmetic drag-to-complete transition. Routine history is source history, not a new scheduler. Artifact cards show qualified source metadata and source/task links, not invented previews.

The route is lazy-loaded as its own bundle. It uses the existing Atelier/light tokens, responsive grids, visible focus and ordinary labeled controls. English/Chinese copy is provided. These source affordances are not a claim of browser/macOS/accessibility acceptance.

### Backlog creation

The optional command creates an **unassigned backlog item** in the existing company/project. It does not set an agent, provider, account, model, wake, resume, interrupt or schedule flag. Existing upstream business automations remain their source owner's concern; the command does not claim to globally suppress them.

Enabling requires all of:
- Current Workspace principal membership and an explicit source credential grant.
- Operator-selected `work_owner=paperclip` and `create_backlog_enabled=true`.
- The bound principal's `create_backlog=true`.
- The observed upstream commit exactly matching the qualified revision.
- A matching current binding revision and revalidated project access when supplied.
- A reserved original-request pointer before the UI dispatches its single call.

These flags are not set on any installed service by this contribution.

### Original-effect recovery

The existing `mastermind-os-pending-v1` IndexedDB store receives a closed `project_source_write` variant. It retains only original request ID, company ID and principal scope; it never stores a task body or credential. No second pending store or retry ledger is introduced.

The source mutation uses Paperclip's native issue-create idempotency key. Its original description marker supports bounded **discovery**, not proof. If the source supplies the same native idempotency key and a unique matching issue, the original receipt can be confirmed. Otherwise the UI retains `EFFECT_UNKNOWN` and offers source candidate inspection. A missing result, matching title or editable marker cannot clear the request or authorize a resend.

**Known adoption gap:** the inspected public issue API does not establish a generally available authoritative read endpoint for every native create-idempotency receipt. Therefore some lost-response cases remain held for the original source owner to reconcile; the adapter does not invent a new ledger, clear the pointer manually or replay the request to discover its result. This is documented rather than disguised as full recovery acceptance.

## 6. Installed configuration and source-to-runtime joins

The optional block is attached to the **existing sealed** `workspace` configuration in `ops/executive_os/executive_mcp_entry.py`. Its loader is the incumbent `current_projection_loader`; config/policy changes revoke the binding rather than silently changing the destination during an action.

See [the inert example](../../integrations/paperclip_control/workspace-binding.example.json). It intentionally has no principal grants or runtime/project references and leaves authoring off. Replace the origin with the existing reachable Paperclip instance and reconcile the dated company ID before adoption. `127.0.0.1` means the Workspace service host, not the user's browser or another Mac. Use an existing authorized private route/tunnel when the services are on different hosts; do not open a new public service or add an anonymous proxy.

Add only existing references:

```json
{
  "access": [{
    "subject_digest": "EXISTING_WORKSPACE_SUBJECT_SHA256",
    "client_ref": "existing-workspace-client",
    "credential_env": "EXISTING_PAPERCLIP_CREDENTIAL_ENV",
    "local_operator": false,
    "create_backlog": false
  }],
  "hermes_bindings": [{
    "agent_id": "EXISTING_PAPERCLIP_AGENT_UUID",
    "profile_ref": "existing-hermes-profile",
    "supervisor_session_ref": "existing-supervisor-session",
    "gateway_ref": "existing-qualified-gateway-reference"
  }],
  "project_bindings": [{
    "project_id": "EXISTING_PAPERCLIP_PROJECT_UUID",
    "work_ref": "WS:EXISTING-PROJECT"
  }]
}
```

This fragment contains placeholders and is not an installable grant. The complete example contains the required schema and owner fields. The source validator rejects malformed/ambiguous bindings, duplicate profile adoption and principals outside the existing Workspace policy. Source credentials must already belong to the selected principal or explicitly authorized local operator. Do not turn a shared admin token into implicit authority for unrelated users.

The prior integration report at #2375 head `336062e39625b4231553fd725af01931fa5df87c` observed company `a5f907fc-c4b1-478c-a1b1-1748d32206dd` and paused Meta-CEO `4e45902f-a976-4e68-b5be-139076e2d461`. They are **dated adoption references**, not a current runtime census, enrollment permission or activation proof.

## 7. Replacement sequence without a second control plane

**A. Bind management reads.** Reconcile the installed source revision/company and current principal. Bind the existing source credential and optional existing profile/project references. Deploy the connected source through the normal release owner. Leave work/wake switches at legacy and authoring disabled while ownership is unresolved. This step creates no bot or schedule.

**B. Transfer company/work management.** Decide the exact authoritative Paperclip records and existing OS/GitHub/Agent OS joins. Preserve parent/plan/source identity and preexisting work. Disable the matching legacy business authoring path before enabling the Paperclip path. Do not dual-write work states to two authoritative stores. This source contribution provides optional unassigned backlog creation, not blanket issue/agent administration.

**C. Adopt Hermes execution.** Reconcile the actual writer, active runs, private native attachment and HTTP/SSE service. Bind the existing profile and original supervisor session. Configure issue-scoped work contexts through the qualified donor adapter and the actual Executive/Capacity consumer path. Retain memory/tool/provider custody. Keep activation off until that source/configuration path is real; a prepared diagram or package name does not complete it.

**D. Transfer business wakes/routines.** Move one exact legacy trigger to its Paperclip successor, retaining timezone, overlap policy, missed-run handling, budget/admission context and original return. Fence the old trigger before enabling the new one. A daemon/process-health supervisor can remain; a competing business scheduler cannot. Do not infer that Paperclip's monthly cost field replaces five-hour, weekly or monthly capacity limits.

**E. Join outcomes and operator attention.** Return actual outputs to the original task/project room and original parent. Keep delivery, source result, task review, repository release and outcome acceptance distinct. Reuse existing T3/Hermes streaming, steer/stop and continuity interfaces. The present Team route exposes source data; it does not replace the full donor Code workspace or create a second chat surface.

Tests/canaries/live-result work remains deferred in this pass as assigned. The sequence describes architecture and necessary owner changes, not a request for a new human ceremony. Actual repository/security/custody controls still apply, and installed acceptance must be reported separately whenever it is later performed.

## 8. Implementation map

| Source | Responsibility |
| --- | --- |
| `integrations/paperclip_control/contract.py` | Closed source selections, command shape, projection allowlists, source IDs and bounds |
| `integrations/paperclip_control/client.py` | One bounded configured transport; no redirects, proxy inheritance or automatic retries |
| `integrations/paperclip_control/installed.py` | Existing policy/principal/config binding, no secret copying or new auth registry |
| `integrations/paperclip_control/service.py` | Company composition, source-visible reference joins, limited backlog creation and original receipt inspection |
| `integrations/paperclip_control/runtime_migration.py` | Existing-agent/Hermes replacement preparation without live mutation |
| `integrations/mastermind_workspace_app/paperclip_http.py` | Two fixed existing-Workspace authenticated endpoints |
| `integrations/mastermind_workspace_app/app.py` | Optional binding, inner routes and literal path/method fence |
| `integrations/executive_mcp/server.py` | Existing audited outer route/fence classification |
| `ops/executive_os/executive_mcp_entry.py` | Existing sealed installation factory composition |
| `app/mastermind_os/src/company/contract.ts` | Typed response validation and selection-bound client contracts |
| `app/mastermind_os/src/company/transport.ts` | Existing MissionHost/auth-generation composition |
| `app/mastermind_os/src/company/pending.ts` | Original pointer grammar, without private draft storage |
| `app/mastermind_os/src/company/CompanyWorkspace.tsx` | Team route, explicit reads, bounded authoring and retained-effect recovery |
| `app/mastermind_os/src/company/CompanyViews.tsx` | Connected company/work/people/project/routine/artifact views |
| `app/mastermind_os/src/company/TaskOutputs.tsx`, `SourceLink.tsx` | Original source outputs/run summaries and constrained source navigation |
| `app/mastermind_os/src/company/RuntimeIntegrationView.tsx` | Retain/replace and actual-source agent migration inspector |
| `app/mastermind_os/src/company/company.css` | Existing theme tokens and responsive route styling |
| `app/mastermind_os/src/host.ts`, `web-auth.ts` | Native/web transport mounted in existing owners |
| `app/mastermind_os/src/orchestration/indexeddb-pending-pointer-store.ts` | One closed original-source variant in the existing store |
| `app/mastermind_os/src/App.tsx` | Primary Team navigation, lazy route and existing-project navigation checks |
| `app/mastermind_os/src-tauri/src/auth/paperclip.rs`, `auth.rs`, `main.rs` | Fixed native commands and existing bearer release fence |

## 9. Engineering verification and limits

Source verification recorded during construction: TypeScript source compilation succeeds; Vite production bundling succeeds; Python source syntax parsing succeeds; the new Rust module parses/formats with rustfmt. The Team view is emitted as a separate lazy bundle. Existing application bundle-size and mixed dynamic/static import warnings remain; this contribution does not claim to solve unrelated startup performance.

No unit/integration suites, hosted-check success, canary, browser interaction, Rust type build, installed service cutover, live agent dispatch or model result is claimed. No installed credentials/configuration were read out or modified. No agent/schedule was activated. The UI's configured owner values are not runtime ownership evidence.

Remaining concrete integration: actual installed company credential/network binding; the existing Hermes HTTP/SSE-versus-private-native boundary; Executive/Capacity admission into Paperclip-originated work; guarded owner-led adapter configuration adoption; one-at-a-time business wake transfer; authoritative readback for uncertain source-create receipts; full T3/room/result/original-parent consumption; complete source actions and runtime acceptance when resumed. Unsaved backlog draft text is currently view-local; only an issued original request pointer is durable. Do not describe it as cross-restart draft synchronization.
