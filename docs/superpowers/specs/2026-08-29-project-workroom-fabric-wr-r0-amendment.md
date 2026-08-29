# Project Workroom Fabric — WR-R0 Current-Platform Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / CHAIRMAN-AUTHORIZED / RECORDS_ONLY`  
**Parent operation:** `mastermind-project-workroom-fabric-20260829-sol-001`  
**WR-R0 operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Parent carrier:** Mastermind PR #240 / `sol/project-workroom-fabric-20260829`  
**Protected source basis:** `mastermindx-market-intelligence/Mastermind@dfd69451dce5e186ce05f65446023fbe21f07a58`  
**Research carrier:** `sol/project-workroom-wr-r0-20260829`  
**Linear:** MAS-231 / MAS-233

This amendment records current primary-source Slack/Linear API and real-workspace falsification discovered after the parent architecture and rollout plan were written. For the exact V1 surface, visibility, permission and concurrency questions below, this amendment wins over generic or more ambitious wording in:

- `docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md`;
- `docs/superpowers/plans/2026-08-29-project-workroom-fabric-rollout.md`.

All other Chairman outcome, source ownership, identity, no-rebuild, dialogue, Linear, Steward, multi-agent, failure, cutover and completion laws remain unchanged.

This amendment creates no Slack/Linear/app/credential/runtime/host/Agent OS/Executive effect.

---

## 1. V1 Workrooms are public-internal only

The parent design allowed both `PUBLIC_INTERNAL` and `PRIVATE_RESTRICTED` as initial visibility values. WR-R0 narrows the first production vertical:

```text
V1 supported Workroom visibility = PUBLIC_INTERNAL
PRIVATE_RESTRICTED                = DEFERRED
```

A dedicated bot can create and manage public channels with a substantially narrower surface than private-channel lifecycle and membership management. Private Workrooms require additional private-channel read/write/topic/invite permissions, exact app membership, member/audience policy and stronger proof that Linear unfurls, Canvas/List access and linked evidence cannot expose restricted information.

The first Workroom pilot must therefore use Projects whose collaboration/evidence can lawfully appear in a public internal company channel. No projector may silently downgrade a requested private Workroom to public.

Private Workrooms require a later, independently reviewed promotion proving at least:

```text
groups:read
groups:write
groups:write.topic
groups:write.invites
exact app membership
exact human membership policy
private Canvas/List/bookmark access behavior
Linear unfurl and synchronized-thread audience safety
removal/archive/reopen behavior
```

The static policy may retain the closed `PRIVATE_RESTRICTED` vocabulary for future refusal/planning, but V1 apply must emit `visibility_refused` for it.

---

## 2. Home Canvas is static charter, not the dynamic current-state surface

The parent design proposed a Home Canvas with a generated present-tense snapshot. WR-R0 found that Slack's public Canvas methods support creation, section lookup/edit and access control, but do not expose a documented atomic revision/`If-Match` conditional write contract suitable for continuously replacing authoritative current-state content under optimistic concurrency.

The V1 ruling is:

```text
Home Canvas = projector-owned static Project charter and navigation
Control Room = dynamic source-attributed current truth
Radar List   = bounded current selected-work projection when Lists are enabled
```

The Home Canvas may contain:

- Project mission/outcome;
- exact `WS:<KEY>` and Linear Project/Initiative links;
- stable Sol Project Steward responsibility description;
- stable architecture/no-rebuild/audience law;
- repository/runbook/Control Room/Radar/Working Notes links;
- an explicit banner that Canvas content is navigation/charter, not runtime/completion truth.

It must not continuously render:

- current Worker/Attempt/runtime;
- current turn owner;
- current blocker/attention;
- current proof state;
- dynamic next action.

Those remain Control Room/Steward facts and, where useful, Radar rows.

### 2.1 Static Canvas drift law

The Workroom Projector owns the complete static charter Canvas it creates. Before any explicit charter update it must:

1. read exact file metadata through the accepted Slack file/Canvas path;
2. verify expected Canvas ID, owner/app attribution and observed update timestamp/hash inputs;
3. use exact managed section lookup and require one unique match;
4. refuse on manual/remote movement since the approved plan;
5. apply one bounded edit;
6. read back metadata and managed section identity;
7. rerun the same desired charter and require no further edit.

Because the platform lacks a documented atomic content precondition, a remote edit detected between plan and action is a hard `remote_changed` refusal. V1 does not attempt high-frequency Canvas synchronization.

### 2.2 Working Notes remain separate and noncanonical

A separate human-editable Working Notes Canvas may be linked. The projector does not manage its content after creation/access setup. Its title and first section must state that it is noncanonical scratch material.

---

## 3. Radar List is app-owned, channel-read-only and not a task manager

Slack Lists have a public API for List creation/schema/items/access on paid plans when the feature is enabled. The V1 Radar contract is:

```text
owner                  = Mastermind Workroom Projector app
channel access         = read
ordinary human editing = not relied upon for managed fields
slack todo_mode        = false
purpose                = source-separated Project projection
```

The Radar retains separate fields for plan, runtime, proof, logical owner, turn owner, attention, source freshness, exceptions and next action. There is no single authoritative `Status`, assignee, due date or task-completion checkbox.

The projector may manage exact app-owned rows only after complete item readback and an observation hash. Remote/manual movement produces `remote_changed`; it does not use last-writer-wins.

### 3.1 List access and channel presence

The public API documents channel access grants and file/list permalinks, but WR-R0 found no documented API to attach a List as a native channel tab. V1 therefore uses:

```text
slackLists.access.set(channel, permission=read)
files.info(list_id) -> permalink
bookmarks.add(channel, Radar permalink)
```

A native List tab may be added manually later as a presentation convenience, but cannot be a V1 acceptance dependency or automated claim until an exact supported method exists.

### 3.2 Lists are feature-gated

If the real workspace/app canary proves Lists unavailable under the current plan or app policy:

- emit `SURFACE_CAPABILITY_UNAVAILABLE`;
- keep Control Room as the dynamic operating surface;
- proceed with core channel + static Home + exact threads + bookmarks only if the accepted pilot still satisfies its reduced completion law;
- do not fake Radar state in Canvas or messages.

---

## 4. Channel tabs and bookmark folders are not V1 automation contracts

Slack's UI supports channel tabs for Canvases, Lists, Workflows, messages, links/files and folders. WR-R0 found no documented general public API that lets the projector create/reorder arbitrary native channel tabs, nor a documented method to create bookmark folders.

V1 automation is limited to supported objects and flat bounded bookmarks:

```text
Linear Project
Control Room
Home Canvas
Radar List permalink when enabled
Working Notes Canvas
primary GitHub/evidence landing
```

The number of managed bookmarks remains bounded. Native tab/folder customization may be performed manually without creating authority, but it is not required for production acceptance and cannot be used as the only locator for a managed surface.

---

## 5. Workflows are optional/deferred, not a core Workroom dependency

Slack custom functions and event/link/external triggers are platform-supported for Slack-hosted apps on paid plans, subject to deployment and workspace-admin restrictions. Their real MastermindX enablement and least-privilege boundary remain unproven.

Therefore:

```text
core V1 = channel + marker/purpose + bookmarks + static Home + exact threads
optional V1 = app-owned read-only Radar List when enabled
later optional = structured Workflow intake after separate app/admin canary
```

WR-WF remains in the program plan, but it is not a prerequisite for WR-P1 if the accepted pilot provides equivalent bounded structured intake through the exact operation/Linear/Control Room path. No `MARK_COMPLETE`, `RETRY`, `ASSIGN_WORKER`, `MERGE` or `DEPLOY` Workflow is ever allowed.

Custom channel templates are rejected as a dependency because Slack temporarily disabled creating/editing custom templates on August 20, 2026. Direct deterministic provisioning remains controlling even if the template feature later returns.

---

## 6. Dedicated Workroom Projector V1 scope set

The dedicated Workroom Projector is not the Agent Relay and receives no semantic dialogue, message-history or arbitrary posting authority.

The exact V1 bot-scope candidate frozen for implementation tests is:

```text
bookmarks:read
bookmarks:write
canvases:read
canvases:write
channels:manage
channels:read
channels:write.topic
files:read
lists:read
lists:write
```

This is a candidate contract until the isolated app qualification/canary proves the real Slack manifest and method behavior. Any Slack-required scope not in this set returns to Sol before app creation or secret enrollment.

Explicitly absent in V1 include:

```text
admin.*
app_mentions:read
channels:history
channels:join
channels:write.invites
chat:write
chat:write.public
commands
connections:write
groups:history
groups:read
groups:write
groups:write.invites
groups:write.topic
incoming-webhook
links:read
links:write
triggers:read
triggers:write
users:read
```

If Lists are not enabled for the accepted core, `lists:read` and `lists:write` are removed rather than granted speculatively. If a later Workflow promotion occurs, trigger/function scopes are reviewed on that separate carrier.

### 6.1 Workroom Projector fixed method families

The first client contract may allow only the WR-R0 accepted fixed methods required for:

```text
auth.test
conversations.list
conversations.info
conversations.create
conversations.rename
conversations.archive
conversations.setTopic
conversations.setPurpose
canvases.create
canvases.sections.lookup
canvases.edit
canvases.access.set
files.info
bookmarks.list
bookmarks.add
bookmarks.edit
bookmarks.remove
```

When Lists are enabled, the separate optional method family is:

```text
slackLists.create
slackLists.update
slackLists.items.list
slackLists.items.create
slackLists.items.update
slackLists.items.delete
slackLists.access.set
slackLists.access.delete
```

No generic arbitrary Slack method/path is accepted. HTTP redirect, ambient proxy, unexpected origin, oversized/non-JSON/duplicate-key response, wrong workspace/app/object or POST ambiguity fails closed under the parent effect-unknown law.

---

## 7. Current workspace findings

The read-only acting-principal census found ten visible MastermindX channels, including:

```text
#agent-dispatch       public legacy global dialogue transport
#ceo-control-room     private Chairman/Sol command surface
#mastermind-exec-ops  private transition coordination surface
#sol-runtime          private runtime projection/transport surface
#build-events         public selected visibility surface
#company-intelligence public cross-program discovery surface
#social               public channel with an existing Canvas tab
```

No exact managed Workroom marker or accepted Project Workroom was found.

The workspace contains multiple ChatGPT, Claude, Cursor, Grok and Mastermind app identities. This confirms that channel membership and Slack principal identity are collaboration/transport facts only; they cannot elect the Project Steward, current Worker or action-authoritative Sol.

Current Agent Relay source remains exact single-channel configuration for `#agent-dispatch` (`C0BSBM78V1N`) with bot scopes:

```text
channels:history
chat:write
```

That app is not widened for Workroom presentation. Multi-workroom dialogue remains a later current-owner evolution after its independent release/enrollment/live-canary gates.

The current Workroom Projector state is:

```text
app identity      NOT_BUILT
credential        NOT_BUILT
host apply client NOT_BUILT
canary            NOT_BUILT
managed Workrooms 0 observed
```

---

## 8. Linear integration V1 correction

Linear's official Project Slack Channel feature can automatically create a public channel for every new Project, add Project members and configure Project updates. V1 keeps this global setting disabled.

Project Workroom eligibility remains the exact static policy + normalized Agent OS/Linear join. The official integration may later bind selected existing Workrooms and project updates only after readback and audience review.

Linear's contextual `@Linear`/Linear Agent issue creation is a human convenience. Autonomous Mastermind mutation must use exact Project/Issue IDs and current projector law; contextual inference from channel content cannot select a Project.

Bidirectional Slack/Linear synchronized discussions remain selected human collaboration only after OSC-C1/MAS-189 promotion. Raw Agent Dialogue protocol is never synchronized into Linear.

---

## 9. Required changes to rollout interpretation

Apply these corrections to the parent rollout plan:

- WR-R0 must output the exact public-only/core/optional/deferred capability sets and current non-secret workspace census.
- WR-P0 V1 policy may select only `PUBLIC_INTERNAL`; `PRIVATE_RESTRICTED` is a typed refusal/deferred class.
- WR-A0 core client excludes Canvas dynamic-current-state and all Workflow/private-channel/message methods.
- WR-A1 app manifest starts from the exact candidate scope set in §6 and removes optional scopes not proven necessary.
- WR-C0 creates one public inert canary channel only.
- WR-SURF1 proves static Home Canvas and optional app-owned channel-read-only Radar; Control Room remains dynamic truth.
- WR-D0/WR-D1 remain separate Agent Relay/AD-DLG2 work and receive no Workroom Projector scope.
- WR-WF is optional/deferred and cannot block the first three-Project pilot unless Sol later rules structured Slack Workflow intake necessary for that pilot.
- WR-P1 Project selection must satisfy public-internal audience safety.
- private Workrooms require a future distinct promotion wave.

---

## 10. No other change

The parent architecture remains controlling for:

- one canonical owner per fact;
- deterministic Workroom/operation identity and exact joins;
- one logical Sol Project Steward with exact current action authority;
- multi-operator operation isolation and collision fences;
- one current Agent Relay/dialogue owner;
- one current Linear projector/OSC-C1 owner;
- Steward/Control Room composition;
- effect-unknown, outage, stale-worker and wrong-carrier failure law;
- existing-carrier preservation;
- staged pilot/stress/fleet/full-fabric proof;
- no duplicate project/lifecycle/task/memory/queue/session/retry/control plane.

This amendment makes no capability live. Current state remains `SPEC_ONLY / RECORDS_ONLY`.