# Project Workroom Fabric — WR-R0 Adversarial Review

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Operation:** `mastermind-project-workroom-wr-r0-20260829-sol-001`  
**Parent architecture:** Mastermind PR #240 / `mastermind-project-workroom-fabric-20260829-sol-001`  
**Research carrier:** Mastermind PR #242 / `sol/project-workroom-wr-r0-20260829`  
**Capability state:** `RESEARCH / RECORDS ONLY / ZERO MUTATION`

This review attempts to falsify the Project Workroom V1 against current Slack/Linear documentation, the real MastermindX estate and Mastermind authority boundaries. For Canvas creation order, effect handling and cleanup, this review supersedes the earlier generic access wording in the platform census. The controlling source law is the current #240 WR-R0 amendment.

No app, credential, channel, Canvas, List, bookmark, Workflow, Linear object, Agent OS record, Executive Job, runtime or host service was created or modified by this review.

---

## 1. Public-internal V1 is the only accepted first visibility

### Evidence

Public channel lifecycle can use a narrow dedicated bot scope set. Private Workrooms require additional private-channel read/write/topic/invite scopes, exact app membership, human audience authority and private Canvas/List/unfurl correction proof.

### Ruling

```text
PUBLIC_INTERNAL    = supported V1 class
PRIVATE_RESTRICTED = typed deferred/refused class
```

A requested private Workroom is never silently created as public.

---

## 2. Existing-channel adoption cannot be inferred or automated

### Evidence

The projector needs exact bot membership to manage an existing target. The current desired scope deliberately omits `channels:join`, invite and message authority. Name similarity does not establish a Workroom binding.

### Ruling

Existing-channel adoption requires all of:

```text
one exact valid MMX-WR1 marker
exact expected workroom_ref and WS:<KEY>
complete authoritative marker census
exact projector bot already a member
app-owned or accepted-prior-projector managed surfaces
explicit ADOPT_EXISTING plan
no duplicate or conflicting object
```

Otherwise return a typed refusal such as:

```text
WORKROOM_ACTOR_NOT_MEMBER
WORKROOM_FOREIGN_OWNER
WORKROOM_MARKER_INVALID
DUPLICATE_WORKROOM
```

Do not add `channels:join`, invitation or membership-management scopes merely to make adoption convenient.

---

## 3. Finding: attached-first Home Canvas creates an unsafe remote effect

### Evidence

Slack documents that `canvases.create(channel_id=...)` automatically adds the Canvas to the channel with `write` permission. Slack also documents `canvas_not_found` as a typical error when `canvases.access.set` attempts to change access for a channel Canvas.

Therefore this sequence is unsafe as a production default:

```text
create attached/write-exposed Canvas
-> attempt downgrade
-> on failure create standalone fallback
```

The first step has already created a remote object. A failed downgrade does not erase that effect. Blind fallback creates a second Canvas and leaves the first write-exposed or access-unproven. Automatic deletion is not safe compensation because `canvases.delete` is irreversible and can itself return an ambiguous or partial-effect error.

### Ruling

Production Home creation is standalone-first:

```text
create standalone app-owned Canvas with no channel_id
-> exact canvas_id/ownership/metadata readback
-> set exact Workroom channel access to read
-> prove accepted exact access/readback condition
-> files.info permalink
-> exact bookmark
-> idempotent rerun/noop
```

A standalone Canvas is usable only after the dedicated app canary proves the paid-plan/workspace path. If unavailable:

```text
HOME_CANVAS_UNAVAILABLE
SURFACE_CAPABILITY_UNAVAILABLE
```

Remove Home from an explicitly accepted reduced pilot or stop the pilot. Do not fall back to attached write exposure.

Channel-tabbed creation is canary-only until a separately admitted disposable canary proves:

```text
create exact channel Canvas
-> exact ID/readback
-> downgrade channel access to read
-> exact access/readback
-> app ownership/metadata
-> idempotent rerun
-> accepted cleanup or historical-preservation disposition
```

### Effect and cleanup law

```text
ambiguous create
  -> EFFECT_UNKNOWN
  -> no second create

create applied + access failed
  -> EFFECT_APPLIED / CANVAS_ACCESS_UNSAFE
  -> no second create or automatic fallback

create applied + access unproven
  -> EFFECT_APPLIED / CANVAS_ACCESS_UNPROVEN
  -> no second create

standalone unsupported
  -> HOME_CANVAS_UNAVAILABLE
  -> no attached fallback
```

Unsafe/unproven objects remain bound to their exact `canvas_id` for reconciliation. `canvases.delete` is permitted only for an exact disposable canary or separate accepted cleanup operation. It is never automatic rollback. Ambiguous deletion is `EFFECT_UNKNOWN` and forbids replacement creation until reconciled.

### Required hostile tests

```text
channel_id create treated as read-only at birth
access failure triggers standalone fallback
ambiguous create is retried
write-exposed Canvas is bound as Home
missing access readback becomes success
free-plan standalone refusal triggers attached create
automatic delete rollback
ambiguous delete permits replacement
```

---

## 4. Finding: Slack surface writes lack a uniform atomic conditional-update contract

### Risk

Channel, Canvas, List and bookmark APIs do not expose one uniform server-side `If-Match` precondition. Two local projector invocations can race between final read and write.

### Ruling

Every live apply acquires one existing-host-style one-shot exclusive/advisory lock before the final read-plan-write-readback sequence.

The lock:

- contains no desired state;
- contains no lifecycle, queue, retry, cursor or project record;
- is not a distributed registry;
- is released on process exit/finally;
- refuses concurrent apply;
- never authorizes retry after `EFFECT_UNKNOWN`.

The exact path/owner/mode/timeout is frozen only at WR-A1 against the then-current accepted host/credential architecture. Server-side remote movement still produces `remote_changed`; the local lock owns no Slack truth.

---

## 5. Finding: Radar safety depends on read-only channel access and app ownership

### Risk

A Slack List with ordinary human write access becomes a second task/project board. Manual drag/drop or checkbox changes could be mistaken for execution or completion.

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

## 6. Finding: connected channel census cannot prove authoritative absence

### Risk

The current Slack connector returned channels visible to its acting principal. That is useful evidence but not an admin-complete or dedicated-bot-complete public-channel inventory.

### Ruling

The committed fixture sets:

```text
complete_for_public_channel_absence_proof = false
public_absence_proof_allowed              = false
mutation_allowed                          = false
```

WR-P0 must refuse authoritative `would_create_channel` or zero-marker conclusions on this incomplete snapshot. Future apply uses the dedicated Projector's complete paginated `conversations.list` read.

---

## 7. Finding: the existing inert channel is not an accepted canary

### Evidence

Exact readback proves:

```text
workspace_id = T0BRD2AQXQV
channel_id   = C0BTQ71QEA0
name         = canary-project-workroom-20260829
public       = true
archived     = false
topic        = ""
purpose      = ""
history      = creator-join event only
```

### Ruling

```text
effect_state  = APPLIED
product_state = INERT / UNMANAGED / NOT A WORKROOM
```

No retry, replacement, implicit adoption, marker, archive, delete, app invite, Canvas/List/bookmark or Workroom binding is authorized. A future WR-C0 operation must bind to this exact channel ID and explicitly choose preservation, gated adoption or gated archival.

---

## 8. Finding: Linear's automatic Project-channel feature is too broad

### Evidence

Linear can automatically create a public Slack channel for each new Project, add Project members and configure Project updates.

### Risk

Global enablement bypasses Workroom eligibility, audience review, exact marker identity and the rule that only selected sustained material Projects receive Workrooms.

### Ruling

Keep global automatic Project-channel creation disabled. Later selected integration may attach exact existing Workrooms and Project updates only after exact readback and audience review. Raw Agent Dialogue is never synchronized into Linear.

---

## 9. Finding: Slack principals and membership are not runtime or authority identity

The workspace contains several ChatGPT, Claude, Cursor, Grok and Mastermind app identities. One Slack identity may represent several native sessions; several sessions may share a Slack identity.

Therefore:

```text
Slack user/channel membership != Worker assignment
Slack delivery                 != target consumption
Slack START                    != Executive Attempt running
Slack RESULT                   != completion
```

Current runtime and action-authoritative Sol identity remain exact Executive/RuntimeBinding/dialogue facts.

---

## 10. Finding: navigation resources must be exact observed values

Fresh direct Linear readback rejected the first resource fixture's six URL values: Project IDs matched, but URLs did not equal the values returned by the exact live Project objects.

### Ruling

The repaired fixture consumes exact Project-object URLs and binds each to the exact Project ID/source ref. It does not reconstruct slugs from names, IDs or earlier URLs.

Exact observation hash:

```text
4464bdf459e3d795aaca6305baad016ecbbf03511d58704ea9748eb75aaef18a
```

The digest reuses:

```python
scripts.linear_portfolio_plan.canonical_bytes
```

which is sorted compact UTF-8 JSON plus one trailing newline. A second digest definition is forbidden. Stale/reconstructed URL acceptance, Project-ID-only URL trust and omitted trailing-newline bytes are hostile regressions.

No Workroom-safe Control Room URL is canonically published. Private provider/chat bindings and guessed URLs remain forbidden.

---

## 11. Least-privilege scope review

Candidate core plus optional Radar scopes:

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

`channels:write.topic` remains intentionally absent because Slack's public-channel topic/purpose methods accept the already-required `channels:manage` bot scope.

Lists scopes are removed if Lists are not part of the accepted production surface. `canvases.delete` uses the existing `canvases:write` scope but is method-allowed only for disposable canary or separately accepted cleanup.

Agent Relay remains dialogue-only and receives no channel/Canvas/List/bookmark/projector scope.

---

## 12. Final V1 recommendation

Proceed only through this reduced, fail-closed product:

```text
PUBLIC_INTERNAL projector-created Workroom
+ exact managed marker/purpose
+ bounded flat bookmarks
+ standalone-first app-owned channel-read-only static Home when proven
+ optional app-owned channel-read-only Radar when proven
+ exact Agent Relay operation threads after independent gates
+ selected Linear links/updates after existing projector/MAS-189 gates
+ Control Room as dynamic present-tense truth
```

Deferred or refused:

```text
private Workrooms
attached-first/write-exposed Home
implicit adoption/join
native List-tab dependence
bookmark-folder automation
custom templates
Workflow intake as core
broad Linear automatic channel creation
raw dialogue synchronization
```

Capability remains:

```text
WR-R0 research                     RESEARCH / RECORDS_ONLY
Workroom Projector app/credential  NOT BUILT
accepted Canvas/List canary        NOT BUILT
WR-P0 and every live wave          NOT BUILT
real Project Workroom              NOT BUILT
```
