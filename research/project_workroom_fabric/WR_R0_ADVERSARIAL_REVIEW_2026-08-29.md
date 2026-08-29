# WR-R0 Adversarial Review — Least Privilege, Ownership and Concurrency Corrections

**Date:** 2026-08-29  
**Reviewer:** Sol, AI CEO  
**Operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Reviewed carrier:** Mastermind PR #242  
**Parent architecture:** Mastermind PR #240  
**Status:** `PASS WITH CORRECTIONS APPLIED / RECORDS_ONLY`

This review treats the initial WR-R0 research as a candidate rather than authority and tests whether its proposed Slack scopes, object ownership and update semantics remain safe under the Project Workroom constitution.

The corrections below are incorporated into:

- the parent WR-R0 platform amendment on #240;
- `slack_surface_contract_snapshot_2026-08-29.json` on #242.

The original capability census remains useful platform archaeology. For exact scope, adoption, access and apply-lock questions, this review and the updated machine-readable contract win.

---

## 1. Finding: `channels:write.topic` was redundant

### Candidate

The initial scope proposal contained both:

```text
channels:manage
channels:write.topic
```

### Evidence

Slack documents `channels:manage` as a bot scope for public channel create/rename/archive and accepts it for `conversations.setTopic` and `conversations.setPurpose`. Because the Workroom Projector already requires `channels:manage`, adding `channels:write.topic` does not unlock a necessary separate V1 capability.

### Ruling

Remove `channels:write.topic` from the candidate manifest and explicitly forbid it in V1 unless a later exact platform change proves `channels:manage` insufficient.

Resulting public-channel scopes:

```text
channels:manage
channels:read
```

This is a least-privilege reduction, not a feature loss.

---

## 2. Finding: public visibility does not prove bot membership or management authority

### Risk

A bot with `channels:read` may see public channels it cannot lawfully manage. A channel name or marker visible to the app is not enough to authorize Canvas/List/bookmark/topic mutation.

### Ruling

The normal V1 path is projector-created channels. Creation establishes the projector bot's managed channel relation.

Existing-channel adoption is explicit and requires:

```text
exact valid marker
exact expected workroom_ref and WS:<KEY>
one complete authoritative snapshot
projector bot is_member == true or equivalent exact membership fact
managed Home/Radar objects are projector-app-owned
plan explicitly says ADOPT_EXISTING
zero duplicate marker/channel
```

Otherwise refuse:

```text
WORKROOM_ACTOR_NOT_MEMBER
WORKROOM_FOREIGN_OWNER
WORKROOM_MARKER_INVALID
DUPLICATE_WORKROOM
```

Do not add `channels:join`, invitation or membership-management scopes merely to make adoption convenient.

---

## 3. Finding: channel-tabbed Home Canvas may initially expose write access

### Evidence

Slack documents that `canvases.create(channel_id=...)` can automatically add a Canvas to the channel tab with write permission. Slack also documents `canvases.access.set(access_level=read|write|owner)` for channel/user entities.

### Risk

A projector-owned static Home Canvas cannot be safely managed if ordinary channel members retain write access. Manual edits would create continuous drift and blur charter authority.

### Ruling

The canary must prove one of these exact safe paths:

```text
A. create with channel_id
   -> set channel access to read
   -> read back exact access

B. if A cannot be proven:
   create standalone app-owned Canvas
   -> set exact Workroom channel access to read
   -> expose by bookmark/permalink
```

A write-exposed Home Canvas is refused. A native tab is presentation only and not required if it cannot meet read-only access.

Working Notes, when enabled, is a separate human-editable noncanonical Canvas and is optional.

---

## 4. Finding: Slack surface writes lack a uniform atomic conditional-update contract

### Risk

Channel/Canvas/List/bookmark APIs do not expose one uniform server-side `If-Match` precondition. Two local projector invocations could race between final read and write even if each individually performs optimistic reread.

### Ruling

Every live apply must acquire one one-shot existing-host-style exclusive/advisory lock before the final read-plan-write-readback sequence.

The lock:

- contains no desired state;
- contains no lifecycle, queue, retry, cursor or project record;
- is not a distributed registry;
- is released on process exit/finally;
- refuses concurrent apply;
- never authorizes retry after `EFFECT_UNKNOWN`.

The exact path/owner/mode/timeout is frozen only at WR-A1 against the current accepted host/credential architecture.

Server-side remote movement still produces `remote_changed`; the local lock is not treated as ownership of Slack truth.

---

## 5. Finding: Radar safety depends on read-only channel access and app ownership

### Risk

A Slack List with ordinary human write access would become a second task/project board. Manual drag/drop or checkbox changes could be mistaken for execution or completion.

### Ruling

The Radar List is:

```text
app-owned
channel access = read
todo_mode = false
managed under one-shot apply lock
separate plan/runtime/proof/turn/attention fields
no single status or canonical completion
```

If the real Lists/app canary cannot establish these exact properties, remove Lists scopes and proceed without Radar. Do not reconstruct dynamic status in Canvas or messages.

---

## 6. Finding: current connected-channel census cannot prove authoritative absence

### Risk

The current Slack connector returned the channels visible to its acting principal. That is useful estate evidence but not necessarily a complete public-channel inventory for a future dedicated bot or admin actor.

### Ruling

The committed fixture sets:

```text
complete_for_public_channel_absence_proof = false
```

WR-P0 must refuse `would_create` or authoritative zero-marker conclusions on an incomplete snapshot. The dedicated Workroom Projector's own paginated `conversations.list` read is the future apply-time source for complete public-channel marker census.

---

## 7. Finding: optional Slack features must shrink permissions when absent

### Risk

Keeping `lists:*` or future `triggers:*` permissions “for later” would violate least privilege and make app review ambiguous.

### Ruling

The final app manifest is generated/frozen only after canary capability selection:

```text
Lists disabled/unavailable -> remove lists:read and lists:write
Workflow deferred          -> no triggers scopes and no Workflow functions
private deferred           -> no groups:* scopes
```

Any later feature promotion gets a new exact operation, app-manifest review, credential/installation scope confirmation and adverse canary.

---

## 8. Finding: Workroom Projector and Agent Relay must remain separate principals

### Risk

Adding channel/Canvas/List/bookmark management to Agent Relay would create a Slack superbot whose semantic dialogue token could restructure the workspace.

### Ruling

```text
Workroom Projector = presentation/provisioning only
Agent Relay        = exact dialogue only
Official Linear    = selected human updates/unfurls only
```

The Workroom Projector has no `chat:write`, history, join/invite, command, webhook, private-channel, trigger, user-read, Executive or provider authority. Agent Relay receives no Workroom presentation scopes.

---

## 9. Corrected candidate V1 scope set

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

If Radar/Lists are not proven, remove the two `lists:*` scopes.

Explicitly absent:

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

---

## 10. Review verdict

**PASS WITH CORRECTIONS APPLIED.**

The corrected V1 remains feasible and stronger:

- public-internal projector-created Workrooms;
- exact marker and app membership/ownership;
- static read-only Home Canvas with safe fallback;
- optional app-owned read-only Radar;
- one-shot apply lock plus exact readback;
- no redundant topic scope;
- no automatic channel join/adoption;
- optional features remove scopes when unavailable;
- Workroom Projector and Agent Relay stay separate.

Capability remains `SPEC_ONLY / RESEARCH`. This review does not approve app creation, credential enrollment, channel mutation, WR-P0 code, Agent Relay widening or production use. Those retain the rollout plan's exact subsequent gates.
