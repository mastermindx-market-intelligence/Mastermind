# Project Workroom Fabric — WR-R0 Current-Platform Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `SPEC_ONLY / CHAIRMAN-AUTHORIZED / RECORDS_ONLY`  
**Parent operation:** `mastermind-project-workroom-fabric-20260829-sol-001`  
**WR-R0 operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Parent carrier:** Mastermind PR #240 / `sol/project-workroom-fabric-20260829`  
**Protected source basis:** `mastermindx-market-intelligence/Mastermind@dfd69451dce5e186ce05f65446023fbe21f07a58`  
**Research carrier:** Mastermind PR #242 / `sol/project-workroom-wr-r0-20260829`  
**Linear:** MAS-231 / MAS-233

This amendment records current primary-source Slack/Linear API and real-workspace falsification discovered after the parent architecture and rollout plan were written. For the exact V1 surface, visibility, permission, actor-membership and concurrency questions below, this amendment wins over generic or more ambitious wording in:

- `docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md`;
- `docs/superpowers/plans/2026-08-29-project-workroom-fabric-rollout.md`.

All other Chairman outcome, source ownership, identity, no-rebuild, dialogue, Linear, Steward, multi-agent, failure, cutover and completion laws remain unchanged.

This amendment creates no Slack/Linear/app/credential/runtime/host/Agent OS/Executive effect.

---

## 1. V1 Workrooms are public-internal only

The first production vertical is narrowed to:

```text
V1 supported Workroom visibility = PUBLIC_INTERNAL
PRIVATE_RESTRICTED                = DEFERRED
```

Public Workrooms allow a materially narrower dedicated bot than private-channel lifecycle and membership management. Private Workrooms require additional private-channel read/write/topic/invite permissions, exact app membership, exact human audience policy, safe private Canvas/List sharing and proof that Linear unfurls or synchronized discussion cannot expose restricted information.

The first Workroom pilot must therefore use Projects whose collaboration and linked evidence can lawfully appear in a public internal company channel. No projector may silently downgrade a requested private Workroom to public.

A later private-Workroom promotion must independently prove at least:

```text
groups:read
groups:write
groups:write.topic
groups:write.invites
exact app membership
exact human membership authority and correction law
private Canvas/List/bookmark access behavior
Linear unfurl and synchronized-thread audience safety
removal/archive/reopen behavior
```

The static policy may retain `PRIVATE_RESTRICTED` as a closed future/deferred value, but V1 apply emits `visibility_refused` for it.

---

## 2. Projector-created channels only; no implicit adoption or join

The Workroom Projector may create a new public Workroom through the reviewed plan and then manage that exact app-created channel. It does not receive `channels:join`, invite or public-message authority.

An existing public channel may be recognized as a managed Workroom only when all of the following are true:

- one exact valid `MMX-WR1` marker binds the expected `workroom_ref` and `WS:<KEY>`;
- the current dedicated Workroom Projector bot/app identity is already a member;
- the expected managed Home/Radar/bookmark objects are app-owned or exactly attributable to the accepted prior projector identity;
- no duplicate channel/marker exists;
- the complete current snapshot is authoritative for absence/uniqueness;
- the plan explicitly says `ADOPT_EXISTING` rather than inferring adoption from name or title.

Otherwise apply refuses with a typed result such as:

```text
WORKROOM_ACTOR_NOT_MEMBER
WORKROOM_FOREIGN_OWNER
WORKROOM_MARKER_INVALID
DUPLICATE_WORKROOM
```

V1 does not join an existing channel automatically and does not add `channels:join` merely to make adoption convenient. A true existing-channel adoption needs a separate human/admin membership act or later exact promotion.

Channel name remains presentation only. The marker and immutable Slack channel ID are the projection locator.

---

## 3. Home Canvas is static charter, not dynamic current truth

Slack supports Canvas creation, section lookup/edit and access control, but does not expose a documented atomic content revision/`If-Match` write contract suitable for continuously replacing current-state claims under optimistic concurrency.

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
- an explicit banner that Canvas content is charter/navigation, not runtime or completion truth.

It must not continuously render current Worker/Attempt/runtime, current turn owner, blocker/attention, proof state or dynamic next action. Those remain Steward/Control Room facts and, when supported, Radar rows.

### 3.1 Channel access must be read-only

`canvases.create(channel_id=...)` may add the created Canvas to the channel with write access. The Workroom Projector must immediately attempt to set the Workroom channel's Canvas access to `read` through the accepted `canvases.access.set` path and read back the exact access result.

If the real app canary proves that a channel-tabbed Canvas cannot be downgraded safely to channel-read access, V1 must instead:

1. create a standalone app-owned Canvas without channel attachment;
2. grant the exact Workroom channel `read` access;
3. add a bookmark to the Canvas permalink;
4. refuse a write-exposed Home Canvas rather than lowering the ownership boundary.

A manually added native tab may be presentation convenience only. Static Home ownership does not depend on a tab.

### 3.2 Static Canvas drift law

The Workroom Projector owns the complete static charter Canvas it creates. Before an explicit charter update it must:

1. acquire the one-shot Workroom apply lock described in §6;
2. read exact file/Canvas metadata and expected app ownership;
3. verify observed update timestamp/hash inputs from the approved plan;
4. look up the exact managed section and require one unique match;
5. refuse on manual/remote movement since planning;
6. apply one bounded edit;
7. read back exact metadata/section identity/access;
8. rerun the same desired charter and require no further edit.

A remote edit detected between plan and action is `remote_changed`. V1 does not attempt high-frequency Canvas synchronization or last-writer-wins.

### 3.3 Working Notes are optional and noncanonical

A separate human-editable Working Notes Canvas may be created only if the real plan/API canary supports the required access behavior. It must be clearly labeled noncanonical scratch material. The projector does not manage its content after creation/access setup.

Working Notes are optional and never a core Workroom acceptance dependency.

---

## 4. Radar List is app-owned, channel-read-only and not a task manager

Slack Lists have a public API for creation/schema/items/access on paid plans when enabled. The V1 Radar contract is:

```text
owner                  = Mastermind Workroom Projector app
channel access         = read
ordinary human editing = not relied upon for managed fields
slack todo_mode        = false
purpose                = source-separated Project projection
```

The Radar retains separate plan, runtime, proof, logical-owner, turn-owner, attention, freshness, exception and next-action fields. There is no single authoritative `Status`, assignee, due date or completion checkbox.

The projector manages exact app-owned rows only after complete item readback and an observation hash. Because Slack does not document an atomic item `If-Match` precondition, V1 relies on both:

- Workroom channel read-only List access, so ordinary humans do not mutate managed rows;
- the one-shot Workroom apply lock, so two local projector actions cannot race.

Any unexpected remote/app movement still produces `remote_changed`; no last-writer-wins or blind retry is permitted.

### 4.1 List access and channel presence

The public API documents channel access grants and file/List permalinks but no public method to attach a List as a native channel tab. V1 uses:

```text
slackLists.access.set(channel, access_level=read)
files.info(list_id) -> permalink
bookmarks.add(channel, Radar permalink)
```

A native List tab may be added manually later as presentation convenience, but is neither canonical nor an automated acceptance gate.

### 4.2 Lists are feature-gated

If the real app canary proves Lists unavailable under the current plan or workspace policy:

- emit `SURFACE_CAPABILITY_UNAVAILABLE`;
- remove `lists:read` and `lists:write` from the app manifest rather than retaining speculative scope;
- keep Control Room as dynamic truth;
- proceed with core channel + static Home + exact threads + bookmarks only if the accepted pilot's reduced completion law still passes;
- do not fake Radar in Canvas or messages.

---

## 5. Tabs, bookmark folders, Workflows and templates

### 5.1 Tabs and folders

Slack's UI supports channel tabs for Canvases, Lists, Workflows, messages, links/files and folders. No general documented public API was found to create/reorder arbitrary native tabs, and no documented method was found to create bookmark folders.

V1 automates only supported objects and a flat bounded bookmark set:

```text
Linear Project
Control Room
Home Canvas when not already a safe native tab
Radar List permalink when enabled
Working Notes Canvas when enabled
primary GitHub/evidence landing
```

Manual tab/folder customization never establishes identity, authority or completion and cannot be the only locator for a managed surface.

### 5.2 Workflows are optional/deferred

Slack custom functions and event/link/external triggers are platform-supported for Slack-hosted apps on paid plans, subject to deployment and workspace-admin restrictions. MastermindX enablement and least-privilege behavior remain unproven.

Therefore:

```text
core V1 = channel + marker/purpose + bookmarks + static read-only Home + exact threads
optional V1 = app-owned read-only Radar List when enabled
later optional = structured Workflow intake after separate app/admin canary
```

WR-WF is not a prerequisite for WR-P1 unless Sol later rules it necessary for the pilot. No Workflow may implement `MARK_COMPLETE`, `RETRY`, `ASSIGN_WORKER`, `MERGE` or `DEPLOY`.

### 5.3 Custom channel templates are not a dependency

Slack temporarily disabled creating/editing custom channel templates on August 20, 2026. Direct deterministic provisioning remains controlling even if templates later return.

---

## 6. One-shot Workroom apply lock; no new state plane

Slack channel, Canvas, List and bookmark APIs do not provide a uniform atomic conditional-write contract. To prevent two local projector invocations from racing, every apply operation must acquire one existing-host-style advisory/exclusive lock for the exact Workroom Projector apply surface before its final read-plan-write-readback sequence.

The lock:

- contains no lifecycle, queue, retry, cursor, project state or desired state;
- is not a durable registry;
- is scoped to the projector/apply host and released on exit;
- refuses concurrent apply rather than waiting indefinitely or starting another worker;
- does not make Slack state authoritative;
- does not authorize a retry after effect uncertainty.

The exact host path/owner/mode/timeout comes from the current accepted host/credential architecture at WR-A1, not from this records document. A need for a database, daemon queue or distributed lock returns to Sol as an architecture mismatch.

The apply sequence remains:

```text
acquire one-shot local lock
-> complete exact read
-> verify plan/source/actor/object/app ownership
-> compare observation hash
-> one bounded write
-> exact readback
-> release lock
```

Any ambiguous POST response remains `EFFECT_UNKNOWN`; the same target is read back before any further action, and there is no alternate channel/app/worker failover.

---

## 7. Dedicated Workroom Projector V1 scope and method set

The Workroom Projector is not the Agent Relay and receives no semantic dialogue, message-history, join/invite, private-channel or arbitrary posting authority.

### 7.1 Candidate bot scopes

Core plus optional Radar candidate:

```text
bookmarks:read
bookmarks:write
canvases:read
canvases:write
channels:manage
channels:read
files:read
lists:read
lists:write
```

`channels:write.topic` is deliberately omitted. The already-required bot `channels:manage` scope is accepted by Slack's public-channel topic/purpose methods; duplicating a second topic-write scope would not be least privilege.

If Lists are not enabled for the accepted core, remove `lists:read` and `lists:write` before app creation/qualification. Any newly required scope outside this set returns to Sol before app creation or secret enrollment.

Explicitly absent in V1 include:

```text
admin.*
app_mentions:read
channels:history
channels:join
channels:write.invites
channels:write.topic
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

### 7.2 Fixed method family

The first client may allow only:

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

When Lists are enabled, the optional family is:

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

No generic arbitrary Slack method/path is accepted. HTTP redirect, ambient proxy, unexpected origin, oversized/non-JSON/duplicate-key response, wrong workspace/app/object or POST ambiguity fails closed under parent effect-unknown law.

### 7.3 Membership and ownership readback

The client/plan must verify `is_member` or an equivalent exact bot-membership fact for every existing managed target before a management write. It also verifies app/file ownership for Home/Radar surfaces. A merely public/visible channel is not sufficient.

---

## 8. Current workspace findings

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

No exact managed Workroom marker or accepted Project Workroom was found. The census is acting-principal-visible, not a complete app/admin public-channel absence proof. WR-P0 must refuse absence/create decisions on an incomplete snapshot.

The workspace contains multiple ChatGPT, Claude, Cursor, Grok and Mastermind app identities. Channel membership and Slack principal identity remain collaboration/transport facts only; they cannot elect the Project Steward, current Worker or action-authoritative Sol.

Current Agent Relay source remains single-channel configuration for `#agent-dispatch` (`C0BSBM78V1N`) with bot scopes:

```text
channels:history
chat:write
```

That app is not widened for Workroom presentation. Multi-workroom dialogue remains a later current-owner evolution after independent release/enrollment/live-canary gates.

Current Workroom Projector state:

```text
app identity      NOT_BUILT
credential        NOT_BUILT
host apply client NOT_BUILT
canary            NOT_BUILT
managed Workrooms 0 observed
```

---

## 9. Linear integration V1 correction

Linear's official Project Slack Channel feature can automatically create a public channel for every new Project, add Project members and configure updates. V1 keeps global automatic creation disabled.

Workroom eligibility remains exact static policy + normalized Agent OS/Linear identity. The official integration may later bind selected existing Workrooms and Project updates only after exact readback and audience review.

Contextual `@Linear`/Linear Agent issue creation is a human convenience. Autonomous Mastermind mutation uses exact Project/Issue IDs and current projector law; channel context or title similarity cannot select a Project.

Bidirectional Slack/Linear synchronized discussion remains selected human collaboration only after OSC-C1/MAS-189 promotion. Raw Agent Dialogue is never synchronized into Linear.

---

## 10. Required rollout interpretation

Apply these corrections to the parent rollout plan:

- WR-R0 outputs exact public-only/core/optional/deferred capability sets, candidate scopes and current non-secret workspace census.
- WR-P0 V1 policy permits apply only for `PUBLIC_INTERNAL`; `PRIVATE_RESTRICTED` is a typed deferred/refused class.
- WR-P0 snapshots include app membership and managed-object ownership evidence; incomplete snapshots refuse create/absence claims.
- WR-A0 excludes dynamic Canvas status and all Workflow/private/message/history/join/invite methods.
- WR-A1 manifest begins from §7 and removes optional scopes not proven necessary; it adds a one-shot apply lock using existing host patterns only.
- WR-C0 creates one new public inert canary channel; it does not adopt `#new-channel` or another existing room.
- WR-SURF1 proves static channel-read-only Home and optional app-owned/channel-read-only Radar; Control Room remains dynamic truth.
- WR-D0/WR-D1 remain separate Agent Relay/AD-DLG2 work and receive no Workroom Projector scope.
- WR-WF is optional/deferred and cannot block the first pilot absent a later Sol ruling.
- WR-P1 selections must satisfy public-internal audience safety.
- private Workrooms require a future distinct promotion wave.

---

## 11. No other change

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