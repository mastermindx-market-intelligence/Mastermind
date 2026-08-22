# Chairman Control Room P0 — local operator guide

## Status

**P0A RELEASED 2026-08-22** as a partial product. Immutable receipts:
Mastermind PR #110 → merge `90db9baf5bcc` (exact head `98c8834`), Macro PR
#6225 → merge `5603972754e5` (the `--json-stdout` seam
`/api/refresh-builds` and the live-builds override path depend on), Sol
partial-release review 5000790561.

`WS:CHAIRMAN-CONTROL-ROOM` / Linear MAS-113 remains **PARTIAL / nonterminal**:
Open on the installed ChatGPT seats refuses as `unsupported_surface` — see
the managed-environment law below. P0B (MAS-115, a vendor-supported
attach/open contract first) is a SEPARATE, unresolved program — not
absorbed here.

This branch — Mastermind PR #113 — is H0 hardening on top of the
already-released P0A runtime above (cached single-flight state composition,
token-gated read APIs, host-fit compose timeout), plus an H1 repair closing
three bounded blockers from Sol review 5000983751: a truthful token
contract, a composition-generation fix for a stale-background-overwrite
race, and this document.

Agent OS records for this release: Macro PR #6230 is a PENDING records
carrier (open, not yet merged) — cite it as pending, not canonical.

## Authority

- Accepted architecture freeze + FABLE-00 commission:
  `research/MASTERMIND_CHAIRMAN_CONTROL_ROOM_P0_ARCHITECTURE_AND_FABLE00_COMMISSION_2026-08-21.md`
  (Mastermind PR #108, merge `fd88ad761b477a84a95bf514a02d932012f211a5`).
- Agent OS records (Macro): `DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED`,
  `WS:CHAIRMAN-CONTROL-ROOM`, handoff `CHAIRMAN-CONTROL-ROOM-2026-08-22-sol-architecture`
  (Macro PR #6216, merge `442bbe179646a91e0830be347c23353af766600a`).
- P0A release receipts: Mastermind PR #110 → merge `90db9baf5bcc` (exact
  head `98c8834`); Macro PR #6225 → merge `5603972754e5`; Sol
  partial-release review 5000790561.
- H0/H1 hardening carrier: Mastermind PR #113 (this branch).

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

## What P0A is

A private, loopback-only, read-only local product on the Chairman's M3 Ultra that
composes existing canonical truth — Executive OS attention/runtime, Agent OS
organizational state, and the Macro `project_active_builds.v1` GitHub projection —
and adds a navigation-only local surface-binding address book so the Chairman can
one-click reopen the exact bound Sol / Fable / worker / PR surface.

P0A never dispatches, wakes, messages, types prompts, decides completion, ranks the
roadmap, or creates work. Deleting the local binding file removes Open buttons and
changes no canonical fact.

## Running it

```text
python3 scripts/chairman_control_room.py [--port 8787] [--macro-root PATH] \
    [--bindings-path PATH] [--repo-root PATH] [--compose-timeout 240] \
    [--state-ttl 120] [--open]
python3 scripts/chairman_control_room.py --check
```

- Binds 127.0.0.1 only; there is no host flag. `--check` builds one document
  + capability census, prints a compact summary (no URLs/session ids), and
  always exits 0 — it is the operator smoke command, not a correctness
  gate, and it always uses the shared gather library's own 60s
  `ceo_boot_packet.DEFAULT_TIMEOUT`, never `--compose-timeout`.
- `--macro-root` MUST point at a maintained, CURRENT full Macro checkout —
  the `/Users/chriswong/Documents/Cluade/macro-main` shape — never a stale
  or scratch session worktree (e.g. a `.claude/worktrees/...` tree). A
  stale checkout silently starves `/api/refresh-builds` and the
  live-builds override path of the `--json-stdout` seam and any
  GitHub-projection freshness the composition depends on. Resolution order
  unchanged: flag → `MASTERMIND_MACRO_ROOT` → sibling `Macro Dashboard` →
  `vendor/macro`.
- `--compose-timeout` (default 240s) bounds every cache-populating
  composition — startup pre-compose and every background/explicit
  recompose. `--state-ttl` (default 120s) is the cache max-age before a
  stale `GET /api/state` kicks a background recompose. See "Operational
  model (H0)" below.

## Operational model (H0)

- Startup pre-composes the `/api/state` document ONCE, synchronously,
  before the server accepts any request — measured ~65s on the Chairman's
  M3 Ultra, bounded by `--compose-timeout` (default 240s). Startup is NOT
  yet "instant"; that startup-latency/Agent-OS-performance cost is a known,
  deliberately unabsorbed follow-up (Sol MAJOR FOLLOW-UP — not part of
  this branch).
- Every `GET /api/state` after that is served from the process-memory
  cache (~1ms) — it never recomposes per request.
- A stale cache (age past `--state-ttl`) triggers at most ONE background
  recompose thread (single-flight); the triggering request, and every
  concurrent request, still returns the last good cached doc promptly —
  none of them block on the fresh composition.
- A failed background refresh keeps the last good doc and records a
  static `state_refresh_error` string in the envelope; a later successful
  refresh clears it. `composed_at` and `refresh_in_flight` are also
  surfaced in the envelope and the UI.
- **Composition generations (H1 repair, Sol review 5000983751 Blocker
  2):** every composition attempt — startup, background, or an explicit
  "Refresh builds from GitHub" (`POST /api/refresh-builds`) — reserves a
  monotonic generation number before composing. An explicit recompose
  supersedes any older in-flight background composition: if the older one
  finishes after the explicit one has already published, its result (and
  any failure it hit) is discarded entirely — never published, never
  recorded as an error — instead of racing to overwrite the newer explicit
  doc. A newer background composition is unaffected by this rule and still
  publishes normally.
- EVERYTHING above is process memory only: a restart forgets the state
  cache, the live-builds document, and the process's `X-CCR-Token` alike.
  There is no durable cursor, store, or generation counter — the
  reservation counters above reset to zero on every process start.

## Security model & threat boundary

- Loopback-only bind (`127.0.0.1`, no `--host` flag; the process asserts at
  startup that the bound socket is loopback).
- Host-header allowlist (`127.0.0.1` / `localhost`, matching port) — a
  DNS-rebinding defense.
- `Content-Security-Policy` + `X-Content-Type-Options: nosniff` on every
  response.
- **`X-CCR-Token` is a per-process browser-origin capability nonce — a
  cross-site/CSRF defense for the local UI, NOT local-process
  authentication (H1 repair, Sol review 5000983751 Blocker 1).** `GET /`
  is itself unauthenticated and is what DELIVERS the nonce to the browser
  (`_serve_index` substitutes it into the served HTML) — so any same-user
  local process can fetch `/` and extract the token exactly the way the
  browser does. That adversary — another process running as the same
  local user — is deliberately OUTSIDE this nonce's threat boundary; no
  mechanism in this process defends against it. What the nonce DOES
  guarantee: a simple cross-site request from a browser (an `<img>`/
  `<form>` POST from another origin, or a `fetch` from a malicious page)
  cannot set a custom header, so it can never carry a valid
  `X-CCR-Token`; and because this server implements no CORS/preflight
  response at all, a browser can never be granted cross-origin permission
  to attach the header or read the response either way. Mutating (`POST`)
  requests and the two read `GET`s that expose full org state
  (`/api/state`, `/api/discover`) require the token; when a browser also
  supplies an `Origin` header, it must match the server's own origin
  exactly. Tokenless or wrong-origin API requests are rejected fast —
  BEFORE any composition/discovery work runs.
- Static assets are served from a closed, explicit `{name: (path, mime)}`
  map — a request path is only ever used as a dict lookup key, never
  concatenated into a filesystem path, so path traversal has no code path
  to reach.
- `POST /api/open` accepts only a `binding_id` — never a URL, argv, path,
  or profile from the browser; the actual navigation argv is built entirely
  server-side by `integrations.chairman_surfaces`.
- The only disk write anywhere in this process is the atomic, `0600`
  surface-bindings save, reached from `POST /api/bind`, `POST /api/unbind`,
  and one `last_verified_at` write-back from a successful `POST /api/open`
  — the SAME file, the SAME atomic writer.
- Composition latency is dominated by Macro's `agentos.py brief` — measured
  60-95s+ on this host's blobless clone (this replaces the stale "~2.5s"
  guidance this document previously carried), which is exactly why
  composition was moved off the request path in H0.

## Degradations honesty

- The composed `mastermind.chairman_control_room.v1` document carries a
  `degraded` list naming its own source failures — nothing is hidden.
- Run from a repo root without the Executive OS runtime DB, the 3 named
  runtime-DB degradations are EXPECTED and are surfaced as such, not
  treated as a bug.

## Bindings, managed environments, and verification semantics

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
