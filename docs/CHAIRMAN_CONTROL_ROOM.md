# Chairman Control Room P0 — local operator guide

**Status:** IMPLEMENTATION IN PROGRESS — this branch is the FABLE-00 runtime claim
and implementation carrier for `WS:CHAIRMAN-CONTROL-ROOM` (Linear MAS-113).
Nothing documented here is proven until the consolidated HOLD-FOR-SOL packet
returns to Sol and passes adversarial review against the accepted architecture.

## Authority

- Accepted architecture freeze + FABLE-00 commission:
  `research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_P0_ARCHITECTURE_AND_FABLE00_COMMISSION_2026-08-21.md`
  (Mastermind PR #108, merge `fd88ad761b477a84a95bf514a02d932012f211a5`).
- Agent OS records (Macro): `DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED`,
  `WS:CHAIRMAN-CONTROL-ROOM`, handoff `CHAIRMAN-CONTROL-ROOM-2026-08-22-sol-architecture`
  (Macro PR #6216, merge `442bbe179646a91e0830be347c23353af766600a`).

## Exact pickup state (recorded 2026-08-22T06:03Z)

- Mastermind protected `master`: `fd88ad761b477a84a95bf514a02d932012f211a5`
  (identical to the accepted #108 architecture merge — no drift between
  acceptance and pickup).
- Macro `main`: `5ad347240a1a744746e01a472f80d6698e73b413`.
- Sol Skillpack: `docs/sol_skills/INDEX.md` loaded from the same Mastermind
  commit; `skillpack_version 1.0.0`, `minimum_bootstrap_major 1` — compatible.
- Collision check at pickup: no existing CCR branch/PR in either repository;
  open Mastermind #109 (MAS-108 B1) and Macro #6208 / #6182 own their surfaces
  and are not touched by this program; no open PR touches
  `scripts/build_project_active_build_map.py`.

## Build hygiene notes (verified)

- This repository tracks BOTH `.github/PULL_REQUEST_TEMPLATE.md` and
  `.github/pull_request_template.md` (`git ls-files` shows the two casings with
  different contents), so on a case-insensitive filesystem one of them
  permanently reports as modified in `git status`. Never stage with
  `git add -A`/`-u` in a CCR worktree; stage explicit paths only.
- Concurrent-claim anomaly, 2026-08-22 ~06:08Z (reconciled): an unattributed
  edit briefly appeared in this worktree claiming a second "current FABLE-00
  session" had found this branch "unpushed" and adopted it, then vanished.
  Verified against GitHub at the time: branch head `f8dc90c` was already
  pushed, PR #110's body was never edited, exactly one worktree exists on this
  branch, and no competing CCR branch/PR exists. The original FABLE-00 session
  (owner of `f8dc90c`/PR #110) remains the single principal builder; the
  anomaly is escalated to Sol in the PR #110 thread. Any genuinely live
  duplicate FABLE-00 dispatch must reconcile through Sol, not adopt this
  branch.

## What P0 is

A private, loopback-only, read-only local product on the Chairman's M3 Ultra that
composes existing canonical truth — Executive OS attention/runtime, Agent OS
organizational state, and the Macro `project_active_builds.v1` GitHub projection —
and adds a navigation-only local surface-binding address book so the Chairman can
one-click reopen the exact bound Sol / Fable / worker / PR surface.

P0 never dispatches, wakes, messages, types prompts, decides completion, ranks the
roadmap, or creates work. Deleting the local binding file removes Open buttons and
changes no canonical fact.

## Planned surfaces (per the accepted freeze §8.1)

```text
control_plane/chairman_control_room.py       # pure read-only compositor
integrations/chairman_surfaces/              # provider navigation adapters
scripts/chairman_control_room.py             # local CLI / ephemeral loopback server
app/static/chairman_control/                 # private-local UI assets
tests/                                       # dedicated CCR tests
```

Launch/run instructions land here when the implementation exists.
