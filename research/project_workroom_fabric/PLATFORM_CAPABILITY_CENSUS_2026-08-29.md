# Project Workroom Fabric — Slack + Linear Platform Capability Census

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Parent architecture:** Mastermind PR #240 / `mastermind-project-workroom-fabric-20260829-sol-001`  
**Linear:** MAS-231 / MAS-233  
**Protected Mastermind source basis:** `dfd69451dce5e186ce05f65446023fbe21f07a58`  
**Architecture head used for research start:** `1cc6030012f764194e4487017b2a73f69d6f32ae`  
**Agent OS continuation head:** Macro `e0f03255fdafcc4f3316cebdd5dde89e4599c5e3`  
**Capability state:** `RESEARCH_COMPLETE / RECORDS_ONLY / ZERO MUTATION`

This census determines which current Slack and Linear capabilities may safely support the Project Workroom Fabric and which assumptions must fail closed or remain deferred. It combines official primary-source platform documentation, current protected Mastermind source, and a read-only acting-principal census of the real MastermindX Slack/Linear estate.

It does **not** install an app, request or read a token, change a permission, create a channel, mutate a Canvas/List/Workflow, create an Initiative, edit a Linear Project, modify Agent Relay, create an Executive Job or make any Workroom capability live.

---

## 1. Executive conclusion

The proposed Federated Project Workroom architecture is technically viable, but the strongest realistic first vertical is narrower than a feature-complete Slack project template.

The recommended V1 is:

```text
PUBLIC INTERNAL PROJECT WORKROOM

Slack public channel
  + exact managed topic/purpose marker
  + flat bounded bookmarks
  + projector-owned static Home Canvas
  + separate human-editable noncanonical Working Notes Canvas
  + optional app-owned, channel-read-only Radar List when Slack Lists are enabled
  + exact Agent Relay operation threads after current Relay/AD-DLG2 gates
  + Linear Project/selected-Issue links after current projector/MAS-189 gates
  + Control Room as the dynamic present-tense truth surface
```

Deferred from the first vertical:

```text
private Workrooms
native automated List-tab placement
automated bookmark-folder creation
custom channel templates
custom Workflow intake
high-frequency dynamic Canvas status
broad automatic Linear Project channel creation
raw Slack/Linear thread synchronization for Agent Dialogue
```

The most important architectural correction is that Slack Canvas is not a safe continuously synchronized current-state store. A static app-owned charter Canvas is viable; dynamic current truth should remain Control Room/Steward and, where supported, an app-owned read-only Radar List.

---

## 2. Sources and method

### 2.1 Primary platform sources

Slack method and feature references:

- [`auth.test`](https://docs.slack.dev/reference/methods/auth.test)
- [`conversations.list`](https://docs.slack.dev/reference/methods/conversations.list/)
- [`conversations.info`](https://docs.slack.dev/reference/methods/conversations.info/)
- [`conversations.create`](https://docs.slack.dev/reference/methods/conversations.create/)
- [`conversations.rename`](https://docs.slack.dev/reference/methods/conversations.rename/)
- [`conversations.archive`](https://docs.slack.dev/reference/methods/conversations.archive/)
- [`conversations.setTopic`](https://docs.slack.dev/reference/methods/conversations.setTopic/)
- [`conversations.setPurpose`](https://docs.slack.dev/reference/methods/conversations.setPurpose/)
- [`canvases.create`](https://docs.slack.dev/reference/methods/canvases.create/)
- [`canvases.edit`](https://docs.slack.dev/reference/methods/canvases.edit/)
- [`canvases.sections.lookup`](https://docs.slack.dev/reference/methods/canvases.sections.lookup/)
- [`canvases.access.set`](https://docs.slack.dev/reference/methods/canvases.access.set/)
- [`slackLists.create`](https://docs.slack.dev/reference/methods/slackLists.create/)
- [`slackLists.update`](https://docs.slack.dev/reference/methods/slackLists.update)
- [`slackLists.items.list`](https://docs.slack.dev/reference/methods/slackLists.items.list/)
- [`slackLists.items.create`](https://docs.slack.dev/reference/methods/slackLists.items.create/)
- [`slackLists.items.update`](https://docs.slack.dev/reference/methods/slackLists.items.update/)
- [`slackLists.items.delete`](https://docs.slack.dev/reference/methods/slackLists.items.delete/)
- [`slackLists.access.set`](https://docs.slack.dev/reference/methods/slackLists.access.set)
- [`slackLists.access.delete`](https://docs.slack.dev/reference/methods/slackLists.access.delete/)
- [`files.info`](https://docs.slack.dev/reference/methods/files.info/)
- [`bookmarks.list`](https://docs.slack.dev/reference/methods/bookmarks.list/)
- [`bookmarks.add`](https://docs.slack.dev/reference/methods/bookmarks.add/)
- [`bookmarks.edit`](https://docs.slack.dev/reference/methods/bookmarks.edit/)
- [`bookmarks.remove`](https://docs.slack.dev/reference/methods/bookmarks.remove/)
- [Slack app manifests](https://docs.slack.dev/reference/app-manifest/)
- [Slack event-trigger functions](https://docs.slack.dev/tools/deno-slack-sdk/guides/creating-event-triggers/)
- [Slack channel tabs](https://slack.com/help/articles/32562841868307-Add-and-manage-tabs-in-channels-and-direct-messages)
- [Slack custom channel templates](https://slack.com/help/articles/33777191777043-Create-and-share-custom-channel-templates)

Linear references:

- [Linear for Slack](https://linear.app/docs/slack)
- [Initiative and Project updates](https://linear.app/docs/initiative-and-project-updates)
- [Project Slack Channels release](https://linear.app/changelog/2026-05-21-project-slack-channels)

### 2.2 Current protected Mastermind sources

- `config/slack_agent_relay_app_manifest.yaml`
- `scripts/check_slack_agent_relay_app_manifest.py`
- `integrations/slack_agent_dialogue/slack_web_api.py`
- `research/AGENT_RELAY_SLACK_APP_ADMIN_CEREMONY_2026-08-27.md`
- protected Operating-Surface / project-management law #214
- protected autonomous-delegation operational-fluency law #227
- protected watcher resource/fresh-carrier law #205

### 2.3 Real estate reads

The acting-principal read-only census used current Slack connector channel inventory/member reads and current Linear Project/Issue readback. The Slack inventory is explicitly **not** an admin-complete workspace export; it is the set visible to the connected acting principal. No tool was used to create/edit/delete a Slack or Linear object.

---

## 3. Current MastermindX workspace census

### 3.1 Visible channels

| Channel ID | Name | Visibility | Current observed role |
|---|---|---|---|
| `C0BRAJUMGBD` | `#new-channel` | public | generic project-like channel, no managed marker |
| `C0BRD2B2L85` | `#all-mastermind-x` | public general | company announcements/general |
| `C0BRDFZPLHK` | `#ceo-control-room` | private | Chairman/Sol command and coordination surface |
| `C0BRET68EH4` | `#social` | public | social; existing Canvas tab observed |
| `C0BRFC9JXK8` | `#build-events` | public | selected build-event visibility surface |
| `C0BRH9VRUE6` | `#company-intelligence` | public | cross-program discovery/intelligence visibility |
| `C0BRUL9F2V7` | `#s0-sol-carrier-test` | private | historical/test surface |
| `C0BSBM78V1N` | `#agent-dispatch` | public | legacy global dialogue/dispatch transport; Files tab observed |
| `C0BSGABKBFY` | `#sol-runtime` | private | runtime/transport projection surface |
| `C0BTD5804QK` | `#mastermind-exec-ops` | private | temporary director/CTO coordination surface |

No channel carried the proposed exact `MMX-WR1` Workroom marker. No channel was accepted as a Project Workroom.

### 3.2 Actor topology

The visible estate includes:

- Chairman Chris;
- three ChatGPT/Sol seat identities;
- several Claude operator identities;
- Cursor identities;
- Grok Secretary;
- Mastermind Relay;
- Mastermind Executive in `#sol-runtime`;
- generic/admin identities.

This is useful collaboration topology but also confirms a core constitutional boundary:

```text
Slack channel membership != Project assignment
Slack user               != native reasoning session
Slack user               != Executive Worker
Slack user               != action-authoritative Sol
```

Several native sessions may share one Slack principal; one Slack principal may also carry several lawful distinct operations. Exact Executive Attempt/Worker/fence, RuntimeBinding and dialogue applicability must govern action.

### 3.3 Current Agent Relay

The protected manifest is intentionally minimal:

```text
name: Mastermind Agent Relay
bot:  Mastermind Relay
scopes:
  - channels:history
  - chat:write
Socket Mode: off
Events API: none
Interactivity: none
Webhooks: none
```

The current client is constructed with one exact `channel_id` and refuses all others. Enrollment/config is bound to public `#agent-dispatch` (`C0BSBM78V1N`).

Therefore:

```text
Agent Relay multi-workroom dialogue = NOT_BUILT
Workroom presentation provisioning = not an Agent Relay responsibility
```

The Relay must not receive channel-management, Canvas, List, bookmark or Workflow scopes.

---

## 4. Slack channel lifecycle capability

### 4.1 Public channels

A dedicated bot app can manage public Workroom channels through documented methods and scopes:

| Capability | Method | Candidate bot scope |
|---|---|---|
| enumerate current public channels | `conversations.list` | `channels:read` |
| read exact channel metadata | `conversations.info` | `channels:read` |
| create public channel | `conversations.create` | `channels:manage` |
| rename managed public channel | `conversations.rename` | `channels:manage` |
| archive managed public channel | `conversations.archive` | `channels:manage` |
| set marker/topic | `conversations.setTopic` | `channels:write.topic` |
| set stable purpose | `conversations.setPurpose` | `channels:write.topic` |

The core marker lives in topic/purpose, not channel name. Channel name is presentation only.

A complete public-channel read is required for duplicate marker detection. A partial/truncated snapshot must refuse planning/apply rather than infer absence.

### 4.2 Private channels

Private-channel lifecycle requires a materially wider and more audience-sensitive surface, including private-channel read/write/topic/invite scopes. The exact app and human membership state also becomes security-critical.

Result:

```text
PUBLIC_INTERNAL V1  = viable core
PRIVATE_RESTRICTED  = deferred separate promotion
```

No V1 projector may create a public fallback when a private Workroom was requested.

### 4.3 Invitations and membership

V1 does not automate human membership. Public-internal Workrooms rely on normal internal workspace access and deliberate human joining/notification patterns. Automatic member invites are not needed for the core Project identity or exact dialogue binding.

A future private promotion must define exact member-source authority, app membership and removal/correction semantics. Linear Project membership is not automatically Slack channel membership authority.

---

## 5. Canvas capability

### 5.1 Supported useful operations

Slack documents APIs for:

- creating a Canvas, including channel-associated creation;
- locating exact sections;
- bounded Canvas edits;
- setting Canvas access.

This supports:

- one projector-owned static Project Home/charter;
- one separately human-editable noncanonical Working Notes Canvas;
- exact links/bookmarks to each surface.

### 5.2 Concurrency limitation

The public Canvas APIs do not document an atomic content revision precondition comparable to an HTTP `If-Match` write contract. `canvases.sections.lookup` provides section identifiers, not a complete normalized content document suitable for a robust continuously updated optimistic-concurrency model.

Therefore the dynamic snapshot originally proposed for Home Canvas is rejected in V1.

Correct V1 use:

```text
Home Canvas     = stable charter/navigation, changed rarely and explicitly
Control Room    = dynamic source-attributed current truth
Radar List      = optional selected current-work projection
Working Notes   = human-editable noncanonical scratch
```

Before any explicit static Home update, the projector should use `files.info` metadata and unique managed-section lookup. Any unexpected `updated` movement or marker conflict refuses the update.

### 5.3 Access behavior

The projector should own the Home Canvas and grant channel access according to its exact role. Working Notes may grant channel write access, but its content is never managed or trusted by the projector after creation.

No Canvas text may establish runtime, completion, authority or current Worker identity.

---

## 6. Slack Lists capability

### 6.1 API viability

Slack's public Lists API supports:

- List creation and schema;
- List metadata updates;
- complete item enumeration;
- item create/update/delete;
- channel/user List access grants and removals.

The List is represented as a Slack file-like object; `files.info` supplies metadata and permalink.

### 6.2 Project Radar contract

The Radar should be app-owned and channel-readable:

```text
slackLists.access.set(channel, read)
todo_mode = false
```

`todo_mode=false` is important. The Radar is not a Slack task list and must not display task-specific completion/assignee/due-date semantics that agents could mistake for canonical execution.

Managed fields remain source-separated:

```text
plan_state
runtime_state
proof_state
logical_owner
turn_owner
attention_state
source_freshness
exception_codes
next_action
```

No single authoritative `Status` exists.

### 6.3 No documented native List-tab automation

Slack's UI supports adding Lists as channel tabs, but no public method was found to automate arbitrary List-tab attachment. The supported V1 composition is:

```text
channel read access to List
+ files.info permalink
+ channel bookmark to Radar
```

Manual native-tab addition may improve aesthetics but is neither canonical nor an automated acceptance gate.

### 6.4 Paid-plan/enablement gate

Slack Lists are a paid feature. The current acting-principal census did not establish exact workspace plan/Lists API enablement for a custom app.

The app canary must therefore prove Lists support before `lists:read`/`lists:write` are included in the production manifest. If unsupported, remove those scopes and run the first pilot with Control Room as dynamic truth rather than fabricating Radar elsewhere.

---

## 7. Bookmarks, tabs and folders

### 7.1 Bookmarks

The public API supports listing, adding, editing and removing channel bookmarks. This is a strong V1 navigation surface for:

- Linear Project;
- Control Room responsibility;
- Home Canvas;
- Radar List permalink if enabled;
- Working Notes Canvas;
- one primary GitHub/evidence landing.

The projector must identify its own bookmarks exactly and preserve human/unmanaged bookmarks.

### 7.2 Tabs

Slack's channel UI can host up to 15 tabs for Canvases, Lists, Workflows, messages, links/files and folders. No general documented API was found for arbitrary tab creation/reordering.

Tabs remain UI presentation. Supported objects and bookmarks are the automation contract.

### 7.3 Folders

The bookmark API accepts a `parent_id` for some link placement, but no supported method was found to create bookmark folders programmatically. Automated folder creation is not a V1 dependency.

Resources may instead be organized in the Home Canvas and a bounded flat bookmark set.

---

## 8. Workflow capability

Slack apps can define custom functions/workflows and event/link/external triggers on paid plans, subject to app deployment and workspace-admin restrictions. Trigger management uses additional permissions and creates another externally invoked input surface that needs its own admission and abuse controls.

Conclusion:

```text
Workflow intake is technically viable later
Workflow intake is not required for the first core Workroom pilot
```

The first Project Workroom can rely on exact Linear/Control Room/Agent Dialogue paths. WR-WF remains optional until a dedicated canary proves:

- plan and feature availability;
- custom app deployment policy;
- trigger/function scope boundaries;
- exact Workroom binding;
- no action-smuggling;
- no direct Executive/Linear/GitHub/Agent OS mutation;
- secret/audience safety.

There is never a Workflow action for `MARK_COMPLETE`, `RETRY`, `ASSIGN_WORKER`, `MERGE` or `DEPLOY`.

---

## 9. Custom channel templates

Slack's help center currently states that custom channel templates cannot be created or edited as of August 20, 2026.

The Workroom Fabric therefore uses deterministic direct provisioning rather than relying on templates. If templates later return, they may become a human convenience but not the canonical planner, identity or proof path.

---

## 10. Linear integration capability

### 10.1 Project Slack Channels

Linear supports Project Slack Channels and can:

- create a public channel for a Project;
- add Project members;
- add a bookmark to the Linear Project;
- post Project updates by default;
- expose a `slackChannelId` relation.

The automatic global mode is rejected for V1 because it bypasses exact Workroom eligibility and would create a public channel for every new Project.

The Workroom Projector—not Linear's global auto-create—owns selected channel provisioning. After exact readback, the official integration may attach Project updates to an already approved Workroom if the platform supports a safe existing-channel binding.

### 10.2 Slack issue actions and contextual Linear Agent

Linear can create/link/update issues from Slack and use channel/thread context. That is useful for humans but unacceptable as autonomous Project-selection authority.

Autonomous Mastermind writes require exact Project/Issue IDs and current app/projector law. No agent selects a Project because the Slack channel name or conversation sounds similar.

### 10.3 Synchronized threads and updates

Linear supports bidirectional synchronized issue discussions and cross-posted Initiative/Project updates. V1 rules:

- Project updates may be useful human projection after audience review;
- selected Issue discussion sync is allowed only after MAS-189/OSC-C1 promotion;
- raw Agent Dialogue protocol is never mirrored into Linear;
- synchronized comments/reactions never establish Executive lifecycle or completion;
- private Linear content must not be exposed to broader Slack audiences.

### 10.4 Existing Mastermind boundaries

MAS-103 remains a narrow `#build-events` visibility canary and explicitly disables global auto project channels and synced threads. MAS-64/MAS-66/MAS-189 remain the exclusive Project/Issue/update mutation path. WR-R0 does not supersede or execute them.

---

## 11. Dedicated Workroom Projector scope contract

### 11.1 Candidate V1 bot scopes

Core plus optional Radar candidate:

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

If the List canary fails or Lists are disabled, remove:

```text
lists:read
lists:write
```

The implementation must not silently retain optional scope.

### 11.2 Explicitly absent

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

This app cannot post arbitrary channel messages or read project dialogue. Agent Relay and official Linear updates remain separate principals.

### 11.3 Method allowlist

Core method family:

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

Optional Lists family after canary:

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

No generic method passthrough is accepted.

### 11.4 Transport security requirements

The client must copy the existing hardened Slack transport posture where applicable:

- fixed `https://slack.com/api/` origin;
- no ambient proxy;
- no redirects;
- closed method/path allowlist;
- bounded response bytes;
- JSON object/duplicate-key/NaN rejection;
- exact workspace/app/object validation;
- GET failure = unavailable;
- any ambiguous POST result = `EFFECT_UNKNOWN`;
- token absent from argv/environment/log/receipt/repr/error.

---

## 12. Workroom identity and marker implications

The exact Workroom marker remains the deterministic binding anchor, not the channel name.

The future planner must require a **complete** public-channel snapshot before deciding a marker is absent. It must classify:

```text
zero exact marker       -> missing / would_create
one exact marker        -> bound
multiple exact markers  -> DUPLICATE_WORKROOM
malformed marker        -> WORKROOM_MARKER_INVALID
wrong WS/workroom pair  -> conflict/refuse
```

Channel rename is presentation movement. Channel archive/reopen remains a separate lifecycle projection action and cannot occur while any active/effect-unknown operation or unresolved turn remains.

---

## 13. Current capability ledger after WR-R0

| Capability | State |
|---|---|
| public channel lifecycle API contract | `SPEC_ONLY / PRIMARY-SOURCE-QUALIFIED` |
| static Home Canvas contract | `SPEC_ONLY / PRIMARY-SOURCE-QUALIFIED` |
| Working Notes Canvas contract | `SPEC_ONLY / PRIMARY-SOURCE-QUALIFIED` |
| Radar List contract | `SPEC_ONLY / PLATFORM-SUPPORTED / WORKSPACE-UNPROVEN` |
| bookmarks/navigation contract | `SPEC_ONLY / PRIMARY-SOURCE-QUALIFIED` |
| native List tab automation | `NOT_BUILT / PUBLIC-API-NOT-FOUND` |
| bookmark folder automation | `NOT_BUILT / PUBLIC-API-NOT-FOUND` |
| Workflow app intake | `SPEC_ONLY / PLATFORM-SUPPORTED / WORKSPACE-UNPROVEN / OPTIONAL` |
| custom channel templates | `DARK_OR_DISCONNECTED / TEMPORARILY-UNAVAILABLE` |
| private Workrooms | `REJECTED_BY_DESIGN_FOR_V1 / DEFERRED` |
| dedicated Workroom Projector app | `NOT_BUILT` |
| Workroom Projector credential/client | `NOT_BUILT` |
| managed Workroom | `NOT_BUILT` |
| Agent Relay multi-workroom | `NOT_BUILT` |
| Linear Project/Issue Workroom join | `NOT_BUILT` |

Research does not advance any item to built or live.

---

## 14. Exact next implementation contract

After PR #240 protects and WR-R0 is independently accepted, WR-P0 is the first code wave.

WR-P0 should:

1. reuse `scripts.linear_portfolio_plan` and exact Agent OS Project identity;
2. define `mastermind.project_workroom_policy.v1` with stable policy only;
3. support V1 `PUBLIC_INTERNAL` apply eligibility and typed `PRIVATE_RESTRICTED` refusal;
4. derive deterministic `workroom_ref` from exact `WS:<KEY>`;
5. parse a complete normalized public Slack channel snapshot;
6. detect zero/one/multiple/malformed markers without fuzzy matching;
7. produce separate core/optional/deferred surface desired state;
8. never include worker/runtime/status/provider/session facts in static policy;
9. perform zero network call/write;
10. produce a deterministic current-estate shadow plan only after the Initiative/Project owner supplies accepted readback.

WR-A0 follows only after the WR-P0 plan schema and this method/scope contract are accepted.

---

## 15. Stop and no-rebuild ruling

WR-R0 found no need for another project database, Slack lifecycle store, channel registry, Canvas state store, List task system, Workflow queue, provider/session identity or synchronizer.

Do not:

- create a Slack superbot;
- widen Agent Relay scopes;
- grant Workroom Projector message/history/private/admin/trigger scopes preemptively;
- make Canvas dynamic truth;
- create a channel for every Linear Project;
- infer identity from titles/context;
- use Slack Lists as task completion;
- add another project-management plugin as canonical;
- install any app or credential before WR-A0/A1 security proof;
- claim paid Slack features are enabled until the exact app canary proves them.

The strongest feasible route remains the Federated Project Workroom Fabric with a narrow public-internal V1 and staged promotion.