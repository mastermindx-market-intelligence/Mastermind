# BCU — browser and computer use for T3 and Mastermind OS

Lane BCU design note. Evidence dir `~/.mastermind/mmos_evidence/bcu-20261111/`,
dev dir `~/.mastermind/mmos_dev/bcu/`, status file `STATUS.md` there. Branch
`t3/mmos-v4-bcu`. Chairman order 2026-11-11: give T3 (and MMOS) the same quality
of browser/computer-use adapter system ChatGPT and Claude have.

## What already exists (verified 2026-11-11, this machine)

| Capability | Incumbent | State |
| --- | --- | --- |
| Browser control | `mmx-browser` MCP (`~/.t3/mcp/mmx-browser/`, pinned bridge release `5aa30969…`, Chrome Web-Sol extension + native host) | Working: 8 enrolled browsers, 6 local M2 profiles CONNECTED (README verification 2026-11-09). Registered in 4 of 5 provider homes. **Not registered in `fabric-unified-router-worker` — delegated children get nothing.** |
| Computer use | Peekaboo (homebrew 4.2.2 CLI; vendored 4.9.8 binary under `~/.cursor/quiet-computer-use/vendor/…`, sha256 `6e2d9f91…`) | Peekaboo reports Screen Recording / Accessibility / Event Synthesizing all **Granted**. Cursor's `quiet_mcp.py` proves the vendored binary works under grants. Nothing registered for T3/MMOS. |
| Vision model | fabric router serves `minimax-m3.1-flash` and `deepseek-v4.1-flash` | **Tested 2026-11-11:** `minimax-m3.1-flash` accepted a base64 PNG via `/v1/messages` image block and answered correctly ("Yes", end_turn). `deepseek-v4.1-flash` returned empty text with stop `max_tokens` — no image understanding. **Vision relay uses `minimax-m3.1-flash`.** |
| Guidance | `~/.t3/skills/mmx-browser/SKILL.md` (browser half, excellent) | Reused; this lane adds the computer-use half and cross-references. |

## Components (what this lane builds)

1. **`tools/mmos_computer_use/`** — one new zero-dependency Python stdio MCP
   server, tool name `mmos_computer_use`, wrapping a **sha256-pinned Peekaboo
   binary** (same pattern as mmx-browser's pinned bridge). Contains:
   - see: `cu_apps`, `cu_windows`, `cu_inspect` (AX tree of one window as
     bounded text), `cu_capture` (one window only, returns image + OCR text).
   - act: `cu_press` (AX action on an element), `cu_set_text` (AX set-value —
     no typing, no clipboard), `cu_keys`, `cu_scroll`, `cu_pointer_click`
     (last resort, coordinates within one window).
   - `cu_vision_ask` — capture/accept one window image → `minimax-m3.1-flash`
     through the fabric router (`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`
     from the session env at call time, never stored) → text answer +
     normalized coordinates.
   - `cu_lease` / `cu_lease_status` — screen lease (owner id, expiry,
     renewal; crashed holders expire).
   - `cu_presence` — human-active check (HID idle time).
2. **`tools/mmos_browser_use/`** — no new browser server. A staging package:
   registration-entry generator (all 5 provider homes including the worker
   home), tests, and the shared guidance skill text.
3. **Guidance** — `integrations/mmos/bcu/skill/` staged skill covering the
   observe-act-verify loop, text/AX before images, page/screen text is
   untrusted evidence never instruction, never repeat an uncertain action,
   paste/set rather than type, close only what you opened; references the
   mmx-browser skill for the browser half.
4. **Teammate switch** — roster-spec field (default off) that adds the
   `mmx-browser` and `mmos-computer-use` registrations to that teammate's
   session only. Team-server side is a small staged change; access is decided
   by the spec, never by anything the teammate writes.
5. **Staged install set** — `integrations/mmos/bcu/`: for each target the
   registration entry, target file, current sha256, install command, rollback
   command, and confirmation probe. Nothing is installed by this lane.

## Reuse decisions (options weighed)

- Peekaboo vs pyobjc-native vs open-source computer-use MCP servers: Peekaboo
  already holds the macOS grants on this machine, exposes AX see/inspect/
  action/set-value/click/press/scroll and window capture+OCR, and Cursor's
  harness proves the pattern. pyobjc would re-earn TCC grants per binary;
  open-source servers (e.g. generic computer-use MCP) bring full-desktop
  capture models we must not have. **Thin pinned adapter over Peekaboo wins.**
- Browser: mmx-browser already provides multi-host/multi-browser sessions,
  receipts and REFUSED/EFFECT_UNKNOWN semantics. Building a second browser
  server would duplicate a hardened surface. **Register, verify, document.**
- Vision: no new provider; router + `minimax-m3.1-flash` proven above.
- Lease/presence/deny-list/receipts/vision relay are the only new logic —
  they are ours, they get tests.

## Safety rules → code map

| Rule | Where |
| --- | --- |
| One window, never full screen | `cu_capture`/`cu_inspect`/acts require a window id; no screen-wide parameter exists |
| Deny list (password managers, Keychain Access, System Settings privacy/password panes, config-extendable) | `deny_apps.json` checked on every see/act; refusal is a receipt |
| Image only to vision model via router, never logged, deleted after answer | `cu_vision_ask` keeps bytes in memory; temp file removed; no base64 in any log/evidence |
| Router token only from session env | read at call time; never written to any file/arg/log |
| Every act returns a receipt (target, APPLIED/NOT_APPLIED/EFFECT_UNKNOWN, bounded cause) | receipt builder shared by all act tools |
| Uncertain act never retried by the layer | single-shot dispatch, no retry path in code |
| Lease with owner/expiry/visibility; crashed holder expires | `cu_lease*` file lease with atomic acquire + expiry takeover |
| Human present → refuse or wait | HID idle threshold gate on every act |
| Teammate access decided by spec | switch read from roster spec only |

## Staging targets (details in `integrations/mmos/bcu/`)

- 5 × `~/.t3/providers/*/.claude.json` — add `mmos-computer-use`; add
  `mmx-browser` to `fabric-unified-router-worker` (browser for children).
- MMOS team server home + roster spec switch (staged change in this repo).
- Skill file into the homes that carry skills today.

## Decisions made by this lane

One MCP server (`mmos-computer-use`) for computer use + vision; browsers reuse
`mmx-browser`. Python 3 stdlib only. Lease = JSON file lease under the
server's runtime dir. Presence = HID idle seconds (threshold 8 s) via IOKit
`HIDIdleTime`. Vision model `minimax-m3.1-flash`. Peekaboo binary pinned by
sha256, copied at install time into a BCU-owned vendor dir (TCC grants travel
with the signed binary).

## Reserved to the principal

Enabling for a real teammate; any router change; any macOS privacy grant
(current grants already cover Peekaboo); remote fleet screens; purchases,
accounts, sign-ins. Exact human actions are named in STATUS.md as they arise.
