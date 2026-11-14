# What the picker lock does to conversations that already exist (PF-2 item 3)

Source: T3 tree `/Volumes/Mastermind/build-cache/pf-t3code`, branch `pf/face-mode`,
test commit `ffddeb52` (on top of release source `f5248ab2`). Lead's own reading and test;
corrected after the principal's census (RULING PF-2a, 09:50Z).

## The rule as built

The lock is one check in the server and the same check in the window.

- Server: `apps/server/src/orchestration-v2/Orchestrator.ts` (dispatch, just before
  planning) calls `resolveLockedInstanceMismatch`
  (`apps/server/src/orchestration-v2/ProviderInstanceLock.ts:39-51`). It refuses only when
  all of these hold: `teamMode` is on, the thread's project is in
  `lockedProviderProjectIds`, the command **names** an instance
  (`message.dispatch` with a model selection, `thread.model-selection.set`,
  `provider.switch`), and that instance differs from the thread's **current**
  `providerInstanceId`. Delegated children are not judged by the parent's lock.
  The refusal records no receipt, so the same command works again once the project is
  unlocked.
- Window: `apps/web/src/components/chat/composerInstanceLock.logic.ts:13-26` pins the
  picker to the thread's current instance (`runtime.providerInstanceId`, else its model
  selection), and offers nothing else.
- Settings are read on every dispatch and pushed to open windows (`settingsUpdated`), so
  the lock starts the moment the `presentation` key is written. No restart.

The lock pins a conversation to the instance it is on **now**. It has no idea which
teammate a conversation belongs to.

## Case 1: the Chairman's conversation on `capacity_fabric` (ruling 20)

Fact (principal's read-only census of the real team project, 09:50Z, 25 conversations):
Secretary was given a fresh primary conversation on its own instance on 12 Nov. The old
conversation on `capacity_fabric` is no longer Secretary's primary. It is the Chairman's
conversation, and under ruling 20 it is left exactly as it is.

Behaviour once the real project is locked:

- His turns keep working. The window sends every turn with the selected instance, which
  is pinned to the current one (`capacity_fabric`); that equals the conversation's
  instance, so the server lets it through. A turn that names no instance (MCP) also
  goes through.
- He can still change the model within `capacity_fabric`: the window keeps every model
  of the pinned instance (`applyComposerInstanceLock` filters instances, not models,
  `composerInstanceLock.logic.ts:32-60`), and the server allows a model change on the
  conversation's own instance (`allows a model change on the thread's own instance`,
  `ProviderInstanceLock.integration.test.ts`). Multi-model is off there.
- He cannot move it to another instance; the server answers "This conversation belongs
  to <capacity_fabric's display name>; other providers are not offered here."
- Proven by test: `keeps turns flowing in a conversation already on another instance`
  (`ProviderInstanceLock.integration.test.ts`, 7/7 pass).

Pinning this conversation to `capacity_fabric` is the correct outcome, not a defect.

## Case 2: older non-primary conversations

The other 11 non-primary conversations (census: 7 `capacity_fabric`, 2 `assurance`,
2 `design-lead`, 1 `secretary`) are each pinned to the instance they are on now; turns
and same-instance model changes keep working, moves are refused with the same message.
All 13 teammate primaries are on their own instance and match the roster.

Stuck case: a conversation whose instance has been removed or disabled in settings. The
window then offers nothing (`offers nothing when the locked instance is absent from the
catalog`, `composerInstanceLock.logic.test.ts`) and the server refuses a move. The
census found no such conversation today.

## Handling: lock as built

The lock goes on as built: no schema field, no change to
`resolveLockedInstanceMismatch`, no new T3 release for this.

Before switching it on, the principal runs the census (read-only; part (c) precondition):

```
/opt/homebrew/bin/python3.12 tools/mmos_team_server/lock_census.py tools/mmos_team_server/specs/team_roster.json
```

Expected: exit 0, `"onMissingInstance": []`, `"primaryMismatch": []`, `"ok": true`, and
`"conversations"` with `"byInstance"` matching the principal's count (25 on 14 Nov).
It opens the state database with its own `mode=ro` connection (never `immutable=1`,
which could read stale data while the server runs), reads settings.json and the roster
state file, and prints counts, conversation IDs and the database `"journalMode"` only.
The main database file is never written; on a WAL-mode database with the server running
the `-wal`/`-shm` files already exist and are the server's, and with the server stopped
sqlite may create them when the census opens its read-only connection. Rehearsed on PF
staging: exit 0, 3 conversations, `{"scout": 2, "writer": 1}`.

## Not built: a "way home"

An optional `presentation` map, conversation ID → home instance, letting a conversation
move onto its home instance while every other move stays refused (the teammate-primary
refusal unchanged). Trigger for building it: the census finds a conversation on a removed
or disabled instance, or a teammate primary off its roster instance. Until then it is not
needed.
