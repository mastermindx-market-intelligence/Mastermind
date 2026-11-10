# T7 — the Team roster, live on the team T3 server

Date: 2026-11-10. Plain-English result of lane T7. Evidence:
`~/.mastermind/mmos_evidence/t7-20261110/` (LEDGER.md, REPORT.md, numbered
JSON, screenshots). Tool: `tools/mmos_team_server/team_roster.py` + spec
`tools/mmos_team_server/specs/team_roster.json`.

## What was set up

One T3 project "Team" (workspace root `~/.mastermind/t3-team/team-project`)
holding one pinned primary thread per teammate, titled `Name — role line`.
Two teammates, mirroring the installed Paperclip company (GET only):

| Teammate | Instance | Thread title | Charter source | Model |
|---|---|---|---|---|
| Assurance (qa) | `assurance` | Assurance — quality & security | `~/.hermes/profiles/assurance/SOUL.md` | glm-5.3 |
| Design Lead (designer) | `design-lead` | Design Lead — product design | `~/.hermes/profiles/design-lead/SOUL.md` | glm-5.3 |

Each teammate is a provider instance (`driver: claudeAgent`, own `homePath`,
`accentColor`, display name = teammate name, model list copied from the
`capacity_fabric` instance). Its home holds `CHARTER.md` (persona prose),
`CLAUDE.md` (long-term memory — proven: a fact written there survived a
server restart and came back in the same thread) and `tool-limits.json`
(passed via `--settings`): reads/searches allowed anywhere, writes allowed
only inside the home; Bash, subagents and NotebookEdit denied; writes to the
project workspace, /tmp and var-folders hard-denied. Proven live: both
teammates' Write to `/tmp` was refused verbatim ("File is in a directory
that is denied by your permission settings") and no file was created.

`team_roster.py apply` is idempotent (second run: no new thread, no file
rewrite, settings untouched) and never rewrites an existing `CLAUDE.md` —
memory belongs to the teammate (a first-draft rewrite bug here was caught by
a third apply and fixed with a regression test). Deep URLs per teammate in
`~/.mastermind/t3-team/run/team_urls.json` (0600, no credentials).

**Pinning has no server command or RPC**: the stock CLI offers no pin, and
pin is a web-client command (`thread.pin` over the client RPC; MCP
`t3_thread_organize` exists but only agents in threads can call it). Pinned
both threads through the headless browser (right-click row → "Pin thread"),
via `tools/mmos_team_server/roster_browser.js pin`.

**Settings reload: LIVE.** The server watches `settings.json` and reloads it
debounced while running (`apps/server/src/serverSettings.ts:1303-1311`,
cache invalidation `:937`); proven empirically — both provider instances
were added and immediately used for new threads with no restart.

## Adding a third teammate (exact commands)

1. Add a block to `tools/mmos_team_server/specs/team_roster.json`
   `teammates` (name, slug, role, role_line, distinct accent_color, instance,
   charter prose).
2. `python3 tools/mmos_team_server/team_roster.py apply tools/mmos_team_server/specs/team_roster.json`
   (works against the running server).
3. Pin the new thread once, from a paired browser profile:
   `node tools/mmos_team_server/roster_browser.js pin <profileDir> <threadUrl-from-team_urls.json> '<name>' <out.json> <shot.png>`

## The eight questions (running client, 1280×800, sidebar 239 px)

| # | Question | What was seen (DOM evidence) | Good enough |
|---|---|---|---|
| 1 | Pinned block reads as a roster at rest? | Two teammate rows at top with name+role titles, accent badges, above scratch rows; no drag-only boundary labels present, none needed | yes |
| 2 | `Name — role` legible at sidebar width? | Title box 199 px; both teammate titles ellipsize (`scrollWidth > clientWidth`) — role tail clips; full title remains in `aria-label`/tooltip | yes, with caveat |
| 3 | Accent badge renders? | `data-provider-accent-color="#e0b64d"`/`#3fb6a8` in each row; badge initials AS/DL, computed `rgb(224,182,77)`/`rgb(63,182,168)` | yes |
| 4 | Sidebar expanded by default on deep URL (fresh profile)? | Fresh paired profile, deep thread URL: sidebar 239 px wide, toggle button present | yes |
| 5 | Plain-question turn shows more than "ready"? | Turn ending in a text question: row status word stays "Done"/none, no "Input" chip | yes (as source predicted) |
| 6 | Carrier marker wraps readably? | `[pc-MAS-7-f3a1c2d4b5]` message: container 652 px, `scrollWidth == clientWidth`, no overflow | yes |
| 7 | "Done" clears after opening? | Assurance's mark absent after open; Design Lead's "Done" persisted across two headless opens 90 s apart — visit watermark (`Sidebar.logic.ts:697-707`) did not advance without dwell/scroll | partially |
| 8 | Snooze + failure shows "Woke"? | Snooze menu + presets live; snoozed thread leaves the list into a collapsed bottom "Snoozed" section, wake button inside; failure-wake not forced | observed only |

## Verdict

**fork needed for: nothing.** The stock client delivers the roster (list,
conversation, live status, badges). The only soft spot is title truncation at
the default sidebar width (full title is one hover away) and the "Done"
clear-on-visit nuance — neither justifies the fork on its own.

## Not verified

- Failure-wake ("Woke" + dismiss) — not forced, out of scope by instruction.
- "Done" clear latency in a real human session (dwell/scroll behaviour).
- Pairing token lifetime beyond: valid seconds after start, rejected ≥2 min.
- Multi-day stability, concurrent teammates under load, mobile client.
