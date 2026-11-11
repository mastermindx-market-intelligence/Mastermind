# T3 long-horizon readiness — 2026-11-10

## Decision and current responsibility

T3 has a substantial working native foundation, but the full Fable-led project
journey is **PARTIAL**, not production accepted. Reuse the existing project,
hierarchy, continuity and Teamlink implementations; the remaining job is to
complete their admitted consumer paths and prove installation and recovery.

This is a readiness assessment and bounded repair under the existing
`WS:ORCHESTRATOR-PROJECT-CONTINUITY` programme. The parent task tree remains
[ESTATE_GRAPH_INTEGRATION_PLAN.md at #2424](https://github.com/mastermindx-market-intelligence/Mastermind/blob/95762fc3700598a7be1a12b8c6c1995753071eed/docs/ESTATE_GRAPH_INTEGRATION_PLAN.md).
No new project registry, queue, scheduler, agent identity or plan store is added.

Current commission: assess and organize the T3 harness for Fable-led long-horizon
projects, visible step execution, nested suborchestrators, original-parent return,
and communication with the Chairman and the Paperclip/Hermes team. DONE_WHEN
remains the complete installed success and interruption/recovery journey.

Procedure: protected Mastermind `76cca6bf0d4f54c1c4a732726a16c70dbe8ed679`, compatible Skillpack 1.0.1.
Bounded repair operation: `t3-visible-task-tools-20261110-c4`.
Source contribution is based on #2367 `f6c794d228c9ffa0d9d95c508aea61d99a85d63e`;
the original router branch, native release and active writers remain intact.
Principal direct repair rationale: LOWER_TOTAL_OVERHEAD for one configuration
seam and its regression proof. Separate reasoning leads assessed donor semantics,
T3 runtime evidence and cross-estate ownership; no Fabric execution is claimed.

## Confirmed and repaired task-visibility defect

Actual Fable `claude-fable-5.2:free` initialization in installed T3 0.1.7,
Claude Agent SDK 0.3.284 / CLI 2.1.319, exposed neither TaskCreate/Get/Update/List
nor TodoWrite. Both inspected native init records omitted them. The enabled
provider environment and provider-home settings lacked the task-tool opt-in.

The installed T3 runtime already translates TaskCreate/Update/List and TodoWrite
to plan progress. Its frontend already consumes `plan.updated` and `todo_list`.
The missing producer was therefore tool availability, not an absent planner UI.

The registration owner now emits `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` for routed
Claude-driver models and reports `task_tools_not_enabled` when that owned setting
is absent or disabled. Refresh can restore the setting without changing model
selection, routing, depth, concurrency, Experimental Agent Teams or credentials.

The setting was installed in the three currently enabled provider homes:
`fabric-unified-router`, `fabric-anthropic-oauth`, `fabric-experiential`.
Exact preimages, backups and postimage readback establish the only semantic change
as that one environment key. Existing 24/5 native concurrency/depth settings were
preserved; those values are not Executive admission grants. T3's live application
settings, running sessions, router services and default model were not changed.
This is next-session configuration; existing sessions were not force-reloaded.
A later bounded log observation found fresh native initialization in an existing
Fable root and a delegated GLM child with all four Task tools present.

### Discriminating evidence

- Sixteen focused registration tests pass on M2 Python 3.14.7, including new and
  gateway model IDs, missing/disabled opt-in repair, idempotence and preservation
  of existing provider-home capacity.
- Five actual installed-CLI fixture cases pass. macOS sandbox-exec permits only
  loopback networking and the HTTP fixture supplies deterministic responses.
  There is no real model inference or paid provider call.
- Default-search baseline omits the four Task tools; environment and settings
  opt-ins expose all four in the native init catalogue.
- With tool search disabled equally in a separate A/B pair, all four appear in
  the repaired model-request tool definitions and remain absent in the baseline.
  Default deferred tool search remains unchanged in production.
- Live post-install adoption was observed without creating a new session: an
  existing delegated GLM child initialized at 10:44:48.476Z with 180 tools and a
  Fable root initialized at 10:50:31.928Z with 182 tools. Both used the existing
  `capacity_fabric` provider and exposed TaskCreate/Get/List/Update.
- Configured, initialized, model-used and visually rendered are separate evidence.
  A bounded scan found no later Task tool invocation in those two logs. A real
  task-progression and resume journey remains owed.

Exact evidence: [2026-11-10-t3-task-tool-visibility.json](evidence/2026-11-10-t3-task-tool-visibility.json).
Reproducible offline runtime proof: [qualify_t3_task_tools.py](../scripts/qualify_t3_task_tools.py).

## Existing plugins and second installed repair

A read of the same Fable initialization at 10:50:31.928Z, observed at
11:00:31.135776Z, shows substantial integration already loaded:

| Native MCP server | Observed condition |
| --- | --- |
| paper, desktop-commander, studio-direct, t3-code | Connected at Fable initialization |
| mmx-browser | Failed at that initialization; known protocol defect subsequently repaired and actual configured Claude MCP health check reports Connected |
| mastermind-executive | Needs authentication; installed endpoint is also backed by the wrong role profile for the loaded COO plugin |
| linear-server | Needs authentication; ordinary native OAuth availability boundary, not a demonstrated source defect |

Loaded plugins include `mastermind-executive` 0.2.0,
`mastermind-workforce` 0.1.0-candidate.g61e97693f4bb.skills-only,
and the agents-md, telemetry, privacy and plugin-authoring Claude plugins.
A skills-only workforce package is not an admitted execution capability.

### Browser transport repair reused from protected #2401

The installed `~/.t3/mcp/mmx-browser/server.js` matched the exact broken
preimage already qualified in merged #2401. Its response writer omitted
`jsonrpc: "2.0"`. Reused the protected
`scripts/t3_computer_use_setup.py::qualified_browser_server` and existing
`apply_plan` receipt/backup owner for **only that file operation**. No new
browser implementation, MCP entry, native tool, skill or credential was added.

Preview digest `528c431c40247253af1c2b8ac13ff30ed901c569ddcf20862e6222b0706d43cf`
was bound to the exact server, runtime descriptor and source helper. The
operation saved the preimage, checked it immediately before atomic replacement,
and read back the exact accepted successor. Node syntax validation passed.
The runtime descriptor stayed byte-identical.

- Before: `854c8397ea5b3547a1faa93e5af27eb071eefc64e9d4f2279695994414727faf`
- After: `325366ad6a64c6e28204727ffa36344c34a3e5bc418047e55e87467dd950fdd9`
- Existing-owner receipt:
  `~/.t3/backups/computer-use/install-a5qewv79/receipt.json`
- Receipt SHA-256:
  `c206bd275f46fdee1121ff7dcb774abaa9df7aa7529d11e10b9dde2b65b7ec90`

After installation, the existing Claude CLI's `mcp get mmx-browser` in the exact
`fabric-unified-router` provider home reported **Connected**. This is actual
configured client/transport acceptance. No model run, page action or agent
restart was performed. The immutable installer receipt correctly retains its
original `INSTALLED_NOT_CONSUMER_PROVEN` state; this later CLI health proof does
not assert fresh T3 model consumption or browser-page acceptance.

All #2401 profile identity, original tab, page-permission and uncertain-input
boundaries remain intact. This repair must not be replayed.

### Role-correct Executive enrollment is still required

The three provider homes point to `http://127.0.0.1:8444/mcp`. The existing
adapter and upstream listeners are present, but the installed upstream profile
is `web_ceo_v3`. The loaded Executive plugin describes a separately enrolled
`/mcp/coo` surface and forbids CEO fallback. Therefore clearing an auth cache or
logging into the present endpoint would not qualify a Fable COO.

The next permitted implementation uses the existing Executive/native integration
carrier to reconcile the intended role/resource, native requester authority and
tool catalogue, then enroll the correct endpoint under its existing custody.
No CEO credential was copied, no profile changed, and no new authority granted.
A historical README reference to #955 could not be refreshed and is not treated
as a current verified hold.

The Linear URL is the ordinary `https://mcp.linear.app/mcp`, and the exact
provider's `claude mcp get linear-server` confirms Needs authentication.
The existing `claude mcp login linear-server` control is available. No login,
cache deletion or credential copying was performed. Linear is a projection and
does not belong on the critical path for T3 task execution and parent return.

## Capability map and current source owners

| Capability | Evidence and owner | Readiness |
| --- | --- | --- |
| Fable/Capacity native sessions | Actual installed Fable init; #2367 Capacity registration | Live native initialization observed; later streaming scoped to those sessions |
| Visible task steps | Existing runtime/UI; this task-tool repair and installed configuration | Repaired and adopted by live Fable/GLM initialization; actual task use/visual proof pending |
| COO → domain lead → worker | Merged #2394 hierarchy and #2414 real native continuation canary | Native path partially proven; broader governed acceptance separate |
| Company-governed nested admission | #2424 existing Executive hierarchy: depth 3, at most 16 retained descendants, narrowed grants and conserved ancestor accounting | Source implemented; actual native T3 scope/settlement not qualified |
| Original mission and scope through steering/compaction | #2375 `336062e39625b4231553fd725af01931fa5df87c` and #2424 | Source and isolated API proof; selected installed model journey pending |
| Company/team visibility | #2395/#2421/#2424 Team and company projections | Implemented composition; real enrolled consumers pending |
| Original return and requester ACK | #2414/#2415/#2424 | API-principal ACK is distinct from native parent consumption |
| Paperclip/Hermes ↔ T3 communication | #2419 Teamlink plugin; #2403 credential cutover; original MAS-4 | Implemented source; live original acceptance remains unrun |
| Strict native lifecycle controls | Merged #2416; current installed CLI still exposes old commands | Built, not installed/proven on inspected app |
| Browser/computer tools | Merged #2401; exact browser writer repaired here and configured Claude MCP health reports Connected | Transport restored; native T3 page/host permission proof remains separate |
| Unattended remote T3 entry | Inspected T3 Connect/LAN off, background service absent | Not enabled; foreground sessions remain usable |

These time-scoped findings do not transfer a writer, clear a release hold, revive
an interrupted session or authorize a replay. #2427 already repairs the stale
10-versus-11 archive assertion; do not duplicate it. #2338 remains the original
Draft integration/release carrier.

## Product architecture to complete

Give a project one persistent accountable coordinator and a clear overview:
original outcome, current step, next dependency-ready work, active domain leads,
returned results awaiting integration, blockers and evidence. Keep two relations
separate: the accountable-parent tree and the task-dependency graph. A dependency
does not assign another manager.

Use the existing T3 native task list for current-session progress, the existing
GitHub/Agent OS plan for original mission and accepted scope, Executive for actual
admitted jobs/attempts/grants/effects, and Paperclip for company/project/issue
coordination. Teamlink carries authenticated discussion and returns. Compose these
owners in the existing project/Team views; do not import another task database.

A domain lead should receive outcome, exact input revisions, owned paths,
constraints and acceptance; it should integrate its own children's results before
reporting upward. Preserve actual root, immediate parent, descendant settlement and
budget. Settings or a skill do not enlarge Runtime grants.

The Chairman-facing update should answer what changed, what evidence proves it,
what remains blocked and what happens next. Delivered, awakened, started, result
returned, parent consumed and accepted remain distinct states. The original project
conversation is the return destination; a late result must not attach to whichever
session happens to be newest.

## Final observed execution frontier

The original contribution is [PR #2431](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2431),
targeting the existing #2367 router branch. #2367 remains open at its recorded
head with its existing auto-merge configuration. No release hold or other writer
was altered. The task-tool repair is installed with live native adoption; the existing #2401
browser protocol repair is also installed with a successful configured-client
health check. Whole harness acceptance remains incomplete.

The connected Chrome surface reached the actual T3 listener at
`http://127.0.0.1:3773`. The rendered page requires a trusted pairing credential
and states that the environment is desktop-managed. No explicitly issued pairing
credential was available in this session. No credential was extracted, no new
pairing was created, and no visible plan acceptance is claimed.

Two read-only Executive ownership projections timed out. A subsequent canonical
`executive_state` receipt at 10:56:42.309722Z returned server 1.5.0,
`backend_unavailable`: the Executive reader is unavailable in the installed
backend. This is a reader/transport boundary, not a security denial and not proof
that submission or execution is unavailable. It leaves current owner and
admission state unqualified; it does not justify duplicating or taking over an
original native operation.

A bounded same-log metadata observation shows actual live native work through
10:57Z, including compaction, background task lifecycle and streaming. These
events do not prove that the estate integration's source writer is running, nor
do they prove task-plan progress. #2424 was refreshed at the same exact head and
still names the project-help consumer and original callback binding as current
owned work. Its installed cutover, credential and original-operation fences
remain in effect.

The next consumer proof is one admitted original T3 task/progress journey
through a trusted native surface. Then finish the current #2424 help/callback
implementation and perform its original installed return/recovery canary.
Do not replay this configuration install, the 16 passing tests or the five-case
CLI qualification absent a relevant change. No new watcher, background runner
or future execution commitment was created.

## Remaining acceptance, through existing carriers

1. **Task consumer:** one fresh owned T3 session creates a visible plan, advances
   at least two steps, and resumes with matching task identity. This can proceed
   without restarting existing sessions once the actual native launch is admitted.
2. **Installed native lifecycle:** use #2416's original package/install path,
   reconcile live writers and qualify real scope enforcement and descendant
   quiescence. Keep #2424's explicit refusal until the owning implementation exists.
3. **Role, help and ancestry:** qualify the intended COO endpoint rather than the
   currently installed Web CEO profile; finish #2424's current project-help consumer and retain
   original native callback/MCP binding through actual App/Control admission.
   A visible colleague or API credential is not native-origin proof.
4. **Teamlink:** finish #2403/#2404 original installation/credential boundary,
   then run #2419's original MAS-4 Meta→COO→return and COO-origin question,
   with actual model consumption and the same original conversation.
5. **Integrated recovery:** Fable coordinates two domains, one domain launches a
   worker, parents consume and integrate results, and a controlled reconnect
   preserves mission, pending work, exact effects and next action without replay.
6. **Acceptance and rollout:** prove the authenticated T3/Mastermind OS user view,
   persist evidence to the existing task tree and Agent OS handoff, then close
   only the outcomes actually accepted.

## Donor findings and adoption decision

Current official Claude Code supports nested subagents by default to three
layers, with different foreground/background return semantics in headless/SDK
operation. Agent Teams is a separate experimental topology with resume/nesting
limits; it should not become Mastermind's durable lifecycle owner.

Current Claude task tools are model-dependent unless explicitly enabled. Built-in
tools can be deferred by ToolSearch, so absence from the initial wire schemas is
not absence from the initialized catalogue. The repaired opt-in supplies the
existing T3 task consumer without a new orchestration plugin.

References:
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/agent-teams
- https://code.claude.com/docs/en/tools-reference#task-tool-availability
- https://code.claude.com/docs/en/agent-sdk/tool-search
- https://code.claude.com/docs/en/env-vars
