# Executive estate visibility and checkpoint history implementation plan

> Execute under the existing #600 / #987 owners. This is a partial source return,
> not an accepted estate implementation or permission to retry a blocked action.

**Goal:** Orchestrators can understand the managed estate and changes across continuations.
**Architecture:** Read existing Executive, Agent OS, RuntimeBinding and GitHub owners;
create no replacement lifecycle, registry, Event database, scheduler or retry plane.
**Tech stack:** Existing Python/Fabric v2 read contracts; bounded JSON exports.
**Spec:** Commission and owner map below; unresolved integration remains with incumbents.
**Operation:** executive-estate-visibility-history-20260926-sol-001.
**Protected source/procedure:** 763ec8f920177fdf48b18df1b8e37b61ab482ef0.

## Commission and owner map
The Chairman requested immediate orchestrator visibility of all active sessions,
each parent's subworkers, company-wide work in progress, and meaningful history.
Executive Runtime owns Jobs/Attempts/Workers/Events. Agent OS owns organizational
knowledge and continuation. GitHub owns code/PR evidence. RuntimeBinding and
SessionTarget own exact physical identity; account labels are not stable identity.
Jobs and Attempts are NOT a census of native ChatGPT/Claude sessions.
The existing MissionWorkspace/Control Room consumers should supply organizational
and code-context joins; do not create a second project or task inventory.

Preserve #1001/P1-R1 custody and the STOP in #600 comment 5846091614, including
its donor evidence. Preserve #979/#995 installed-reader/service recovery custody.
The existing singular Steward query stays singular; plural observation is separate.

## Implemented independent slice
- [x] Write and observe failing tests for one-root checkpoint comparison.
- [x] Implement compare_fabric_snapshots in control_plane/fabric_checkpoint_changes.py.
- [x] Implement scripts/fabric_checkpoint_changes.py over authorized JSON exports.
- [x] Test actual Fabric v2 projector shape, identity, missingness, bounds and no I/O effects.
- [x] Run history plus two existing Fabric owner suites: 137 passed, exit 0.
- [x] Attempt full repository pytest: collection stopped on missing local module jwt.
- [ ] Independent exact-head review and hosted CI acceptance.
- [ ] Incumbent-controlled installation / authenticated machine-consumer proof.

This slice reports NET differences between TWO snapshots of ONE root. It is not
complete Event replay, a native-session census, or the requested estate endpoint.
Changes identify recorded status/Attempt/Worker references. Missing observations
are not termination; execution COMPLETED is not product acceptance. Comparison
refuses different roots/sources, unknown/conflicting generations and invalid input.
Input hashes identify canonical JSON content, not authentication or file signatures.
No current-state acquisition, scheduler, source write or provider action occurs.

## Blocked estate slice and preserved evidence
- [ ] Multi-root estate assembly, owner read adapter and global visibility endpoint.
- [ ] Native-session enrollment/coverage and exact physical-binding succession.
- [ ] Agent OS/Git context joins, Mastermind OS view and all-account live proof.
The platform blocked the estate-assembly append before dispatch. Readback proved
only preliminary helpers existed. The append was NOT retried or rerouted.
The helpers and 27 deliberately red estate acceptance tests were preserved under
/Volumes/Mastermind/evidence/executive-estate-visibility-history-20260926-sol-001/blocked-estate-frontier/.
They are not part of the shippable history slice or its passing-test count.
Do not delegate, replay or disguise the blocked action to bypass this boundary.

## Review focus and acceptance gates
1. Stale/partial observations must not imply an idle, finished, or empty company.
2. Source/account rotation must not silently rebind or duplicate running work.
3. History must distinguish net checkpoint change from missed intermediate events.
4. Private payloads, credentials and arbitrary source text must not become output or commands.
5. Response and acquisition limits must be explicit rather than silently dropping estate members.

## Full-history follow-through (not implemented)
Add bounded ordered history at the existing Runtime Event owner. Verify its global
ordering key before specifying a cursor: per-aggregate sequence and SQLite
observation counters are NOT interchangeable with a global history sequence.
Use source/epoch-qualified cursors, a fixed window watermark, explicit retention
and gap states, and existing Agent OS checkpoint ownership. No new Event store.
Claude3 -> Claude5 preserves responsibility/work references but requires an explicit
new physical binding and reconciliation of outstanding effects; opening an account
or comparing snapshots does not transfer authority or custody.

## Cumulative continuation checkpoint
FINALIZATION_CLASSIFICATION: CHECKPOINTED_CONTINUATION
MISSION_COMPLETE: false
HISTORY_SLICE: BUILT_NOT_PROVEN (source/CLI verification; not installed)
ESTATE_ASSEMBLY: NOT_IMPLEMENTED_PLATFORM_BLOCK

Before: no dedicated net-comparison helper for these two Fabric exports.
After: an authorized consumer can compare one root's exported checkpoints using
`python3.12 -m scripts.fabric_checkpoint_changes --before old.json --after new.json`.
Exit 0 means complete net comparison, 2 partial/unavailable, 1 invalid export.
This command does not acquire current Runtime state or open a provider session.

Verified: 137 tests passed in 8.98 seconds, exit 0, across the new 43-case suite,
existing Fabric v2 semantics and existing bounded Fabric owner tests.
Full-repository check: `python3.12 -B -m pytest -q --maxfail=1` stopped during
collection at tests/mastermind_window_reader/test_mission_association.py because
the local environment lacks the `jwt` module. The full suite is NOT green/proven.
No dependency, service, provider, installed profile, account or lifecycle was changed.

Source SHA-256 receipts:
- control_plane/fabric_checkpoint_changes.py: fdc126673b3f2b9343a7f769d0e36cedd5de6e5c300a0534de7a823e16194e3c
- scripts/fabric_checkpoint_changes.py: 55aef37360ccdc9d2660381cc458c10e4389430bf0843ea19dbeedcd84afbdc5
- tests/test_fabric_checkpoint_changes.py: 04420b02db04e281c1581615bf52055599741bb30c813166fc48184c9c64e8b5

Evidence home: /Volumes/Mastermind/evidence/executive-estate-visibility-history-20260926-sol-001/.
Test receipts: history-and-owner-tests.txt and full-repository-check.txt.
Blocked-frontier hashes: helpers 42812c18d109c9896f6d3b7e61a2c7358d4fe429f0804fb999293ff71a05166a;
red estate tests 0be7c365d7c4e2e4a77f0681ef337b97b3d3c52716eec6024547eea8cc0480dd.
Source revision/publication is pinned by cumulative #600 comment 5846145892.

Next primary action: the incumbent #600 integration principal reviews the exact
history-only source revision and hosted CI; production integration requires its
normal authenticated owner/installation acceptance. The blocked estate action
remains closed absent a legitimate change in platform authorization/status.
Do not redo bootstrap archaeology, reopen #979/#995 custody, or interpret this
handoff as a directive to retry the blocked write through a different actor.
No child was dispatched, no watcher was armed, and no native consumption ACK is
claimed for the informational #600 coordination receipt. Existing parent work and
watchers are unchanged. Agent OS/Linear live projections remain unmodified.
