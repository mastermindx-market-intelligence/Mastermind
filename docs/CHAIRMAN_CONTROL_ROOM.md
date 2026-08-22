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

## Shipped surfaces (per the accepted freeze §8.1)

```text
control_plane/surface_bindings.py            # mastermind.surface_bindings.v1 store (0600 atomic)
control_plane/chairman_control_room.py       # mastermind.chairman_control_room.v1 pure compositor
integrations/chairman_surfaces/              # provider navigation adapters (zero-message)
scripts/chairman_control_room.py             # local CLI / ephemeral loopback server
app/static/chairman_control/                 # private-local UI (ink-and-brass, light+dark)
tests/test_surface_bindings.py               # + test_chairman_control_room.py,
                                             #   test_chairman_surfaces.py,
                                             #   test_chairman_control_room_server.py
```

## Running it

```text
python3 scripts/chairman_control_room.py [--port 8787] [--macro-root PATH] \
    [--bindings-path PATH] [--repo-root PATH] [--open]
```

- Binds 127.0.0.1 only; there is no host flag. `--check` prints a one-shot
  composition summary (no URLs/session ids) and exits.
- State recomposes fresh on every page load/poll. "Refresh builds from GitHub"
  invokes Macro's `build_project_active_build_map.py --json-stdout` seam
  (requires the seam to be merged at the macro root, and `gh` auth); the live
  document lives in process memory only and is forgotten on restart.
- The macro root resolves flag → `MASTERMIND_MACRO_ROOT` → sibling
  `Macro Dashboard` → `vendor/macro`. Composition latency is dominated by
  Macro's `agentos.py brief` (~2.5 s on a normal checkout; tens of seconds on
  a sparse/blobless scratch checkout — prefer a maintained full checkout).
- Bindings live at
  `~/Library/Application Support/Mastermind/control-room/surface_bindings.json`
  (mode 0600, parent 0700, atomic writes). Deleting the file removes Open
  buttons and changes no canonical fact.
- Terminal-launched resumes (claude/cursor-agent/codex) use the
  osascript → Terminal grant. ChatGPT never uses osascript/AppleScript/Chrome
  at all — see the managed-environment law below.
- **ChatGPT seats live in persistent GoLogin/Multilogin managed-browser
  environments, never a Chrome profile (Sol architecture correction,
  MAS-113, 2026-08-22 — supersedes the Chrome-profile law of review
  5000169412).** The `chatgpt` locator (`chatgpt_managed_env`) stores an
  exact local environment identity — a GoLogin `profile_id` or a Multilogin
  `folder_id` + `profile_id` — plus the exact conversation URL, and NEVER
  proxy, IP, fingerprint, cookie, credential, or token material
  (`control_plane.surface_bindings.FORBIDDEN_SEMANTIC_KEYS`). Every
  `chatgpt` open currently refuses with `unsupported_surface`: an
  investigation on the real machine plus a sweep of both vendors' official
  documentation (multilogin.com/help "API basics — key terms & concepts",
  "How to use headless mode", "Learn CLI commands", "Learn CLI command
  flags", "Start working with CLI"; gologin.com/docs quickstart + "Local
  Agent Browser CLI"; api.gologin.com/docs-json OpenAPI enumeration) found
  that neither vendor documents a surface that can open a URL in, focus, or
  attach automation to an environment that is already running as a
  GUI-started profile — refusing is the lawful outcome, not a bug to work
  around. Discovery (`GET /api/discover`) lists local environment
  identities read-only, ids only (a display name requires cloud
  authentication no session may perform). GoLogin's local store
  (`~/Library/Caches/GoLogin`) is under a standing operator no-delete veto
  and this product only ever `stat`s directory names inside it — it never
  writes there.
- `last_verified_at` / VERIFIED_OPENABLE advances ONLY on an open that
  proved the provider-native session actually exists (`claude_code`/`codex`,
  via their local session-store read). `chatgpt` can never advance this
  stamp in the current state (every open refuses); `claude_desktop`/
  `cursor_agent` opens are launch-ACK only and remain BOUND_UNVERIFIED —
  they never advance the stamp either.
