# What the picker lock does to conversations that already exist (PF-2 item 3)

Source: T3 tree `/Volumes/Mastermind/build-cache/pf-t3code`, branch `pf/face-mode`,
test commit `ffddeb52` (on top of release source `f5248ab2`). Lead's own reading and test.

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

## Case 1: the Chairman's session in Secretary's old conversation (ruling 20)

Facts: the Chairman's runs 11–12 moved Secretary's conversation onto `capacity_fabric`
(deputy STATE, RF row). Ruling 20: it is his; never stopped or sent into.

Today's behaviour once the real project is locked:

- His turns keep working. The window sends every turn with the selected instance, which
  is pinned to the current one (`capacity_fabric`); that equals the thread's instance, so
  the server lets it through. A turn that names no instance (MCP) also goes through.
- What he sees change: the provider picker in that conversation offers only
  `capacity_fabric`, live, without a reload. Multi-model is off there.
- What he can no longer do: move that conversation to any other instance, including
  back to Secretary's own instance. The server answers "This conversation belongs to
  <capacity_fabric's display name>; other providers are not offered here."
- Proven by test: `keeps turns flowing in a conversation already on another instance`
  (`ProviderInstanceLock.integration.test.ts`, 7/7 pass): a thread created on a second
  instance in a locked project accepts a plain send and a send naming its own instance;
  a `provider.switch` back is refused with that message; the thread's instance is
  unchanged.

So his conversation does **not** start refusing his turns. The defect is the opposite
one: the lock freezes Secretary's conversation on the wrong instance, which is exactly
what ruling 20 says must not stay that way.

## Case 2: unbound older teammate conversations

Conversations in the team project that are not a teammate's primary conversation
(older ones from before the primary binding, or ones the window started).

- Each is pinned to whatever instance it is on now. Turns keep working; moves are
  refused with the same message.
- One trap: if a conversation's current instance is **removed or disabled** in
  settings, the window offers nothing (`offers nothing when the locked instance is absent
  from the catalog`, `composerInstanceLock.logic.test.ts`) and shows the provider as
  unavailable, and the server refuses a move to a working instance. Without the lock the
  person could pick another instance; with it the conversation is stuck, with only the
  "unavailable" notice. Whether any such conversation exists on the real root is a
  read-only census for the principal: `team_roster.py status` on the real spec lists
  every thread in the project with its instance (`list_threads`,
  `tools/mmos_team_server/team_roster.py:350`); compare each instance with the instance
  list in settings.

## Recommended handling (one)

**Add a "way home" to the lock, and nothing else.** A conversation that has a home
instance may always move onto its home instance; every other move stays refused.

- `presentation` gains an optional map, thread ID → home instance, written by the
  presentation writer from the roster's record of primary conversations (team_roster
  state). Absent map = today's behaviour exactly.
- Server: `resolveLockedInstanceMismatch` returns no mismatch when the requested
  instance is the thread's home instance. Window: the picker offers the current
  instance plus the home instance (when they differ), with a one-line notice: "This
  conversation belongs to Secretary. It is running on <current> now."
- Effect on case 1: his turns keep working on `capacity_fabric` (nothing refused, no
  warning needed); the one extra choice is Secretary's own instance. Moving it home is
  his act or the principal's after his run ends, never a lane's. After the move, the
  conversation is pinned home like every other teammate primary.
- Effect on case 2: unbound conversations have no home entry, so they behave as today.
  The principal can give a stuck one a home entry (a settings write through the same
  writer, with undo) instead of unlocking the whole project.
- What it does not do: it never lets a teammate primary conversation move anywhere
  except its own instance, so the server refusal for teammate primaries is not
  weakened. Teammates stay on their own instance (ruling 20).

Not chosen:
- Pin teammate primaries to their home instance outright: the window names the
  instance on every send, so his next turn in Secretary's conversation would be refused
  with no warning. Ruled out by PF-2.
- Unlock the project, move the conversation, relock: opens every conversation for that
  window and depends on his run ending first; usable once as a manual step, not a rule.

Size: one optional schema field, one line in the server rule, one in the window rule,
the notice, and tests (server integration and window logic). It needs a new T3 release
(same pack/install path as part (b)). It is the principal's call whether this goes in
before the real lock is switched on; until then the safe order is: switch the lock on
only after Secretary's conversation is back on Secretary's instance, or accept that it
stays on `capacity_fabric` until then.
