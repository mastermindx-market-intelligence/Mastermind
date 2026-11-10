# Lane L8 — agent test environment (app dev harness)

Lead: glm-5.3 (T3). Branch `t3/mmos-v2-l8`. Commissioned by the principal (Fable), 2026-11-10.
Trunk: `origin/feat/mmos-v1-integration-t3`. Evidence: `~/.mastermind/mmos_evidence/l8-20261110/`.

## Split (wave 1, 2026-11-10) — seam redraw declared

Incumbent read froze the split: `src/agent-control/` already implements the whole in-page half
(inspect / act / navigate / check, stable refs, one-shot observation frames, secret filter;
`control.ts` 359 lines) and `main.tsx:46` mounts `installAppControl` in the production entry.
Original seam (c) "in-page half" therefore shrinks to a thin verb adapter; the real build work
moves to the Rust socket half, the launcher, and logging. The principal's seams are otherwise kept.

| Slice | What | Shape / model | Wave |
|---|---|---|---|
| R1 | Reuse scan: DOM control+inspect of Tauri 2 webview on macOS, file logging, webview-only shot | two investigators: `glm-5.3` + `gemini-4-argon`, raw findings files | 1 |
| A | `app/mastermind_os/tools/mmos_dev.py` — `up --fixture` / `down` / `status`, fake-proc tests | diff+test: `deepseek-v4.1-flash` | 1 |
| D0 | Rust dev-log module + redaction (bearer-absence test) | diff+test: `deepseek-v4.1-flash` | 1 |
| B | Unix-socket control channel, Rust half: feature gate, eval→agent-control bridge, IPC return, release-exclusion test | writer-attacker: writer + `grok-4.7` attacks (reproducing command per finding) | 2 (after R1) |
| C | Verb adapter: snapshot / click / type / wait-for / logs / shot → existing agent-control tools | diff+test | 2 |
| D1 | Wire dev_log into real request/auth/native-failure paths (dev build only) | diff+test | 2 |
| E | Browser path: serve existing browser-proof pages, document DOM driving | diff+test | 2 |
| F | Runbook `integrations/mmos/APP_DEV_HARNESS.md` + `skills/mmos-app-dev/SKILL.md` | written last, from what actually works | 3 |
| G | Cold-agent acceptance: fresh `deepseek-v4.1-flash`, runbook path only, fixture mode | fresh child, evidence under `l8-20261110/cold-agent/` | 3 |

## Frozen decisions

- Dev root: `~/.mastermind/mmos_dev/` — never `/Library/Application Support/MastermindExecutive`
  (production, read-only for every agent), never `<checkout>/data/control_plane/` (the Executive's
  per-checkout default = L1's scratch root: `control_plane/executive_runtime.py:323-324`), never `/tmp`.
- Dev app identity: bundle id `com.mastermind.os.dev`, productName `Mastermind OS Dev`
  (separate tauri config), window title carries DEV. Cannot be mistaken for the installed app.
- Control socket: `<dev root>/control.sock`, mode 0600, JSON-lines protocol; compiled only under
  cargo feature `dev-control` (Cargo.toml has no `[features]` section today — one is added);
  a test proves the release build does not contain the listener.
- Dev log: `<dev root>/app.log`, JSONL. Records: requests (method/path/status/error_code),
  auth state transitions, native command failures. Redaction module with a bearer-absence test
  (feed a bearer through the logger; assert no `Bearer `, no `eyJ`, no subject value in the file).
  On by default in dev; release recommendation goes in the lane return, not switched on silently.
- Fixture mode = one fixture system: the existing browser-proof pages + `browser-proof-command-fixture.ts`
  + `vite.browser-proof.config.ts`. Browser front (vite serve) ships now; the dev Tauri front serves
  the same pages as its frontendDist once slice B lands. No second fixture system.
- `up` without `--fixture` (real dev Executive) returns a typed `NOT_IMPLEMENTED_YET` until lane L4
  lands its local operator contract; nothing in this lane waits on L4.
- Desktop law (from the brief and L4's ledger): one GUI-driving child at a time; dev app launched
  in background (`open -g` or equivalent); no global clicks/keystrokes; captures of the dev app's
  own webview only, never the screen; no image to a vision model unless it is that webview render;
  no GUI work to a GLM child; 20-minute GUI time box.

## Open / discrepancies

- Brief stated L4's first landed commit is `integrations/mmos/LOCAL_OPERATOR_CONTRACT.md` on trunk —
  verified false (absent from trunk, L4 branch and worktree; only old evidence files
  `docs/evidence/2026-10-13-mmos-fabric-discovery/M2_LOCAL_OPERATOR_20261017.*` match). Lane builds
  against the fixture transport per the brief's own provision. Reported to principal in lane return.
- Cold-agent run against the real dev Executive (second half of DONE_WHEN 6) deferred until L4 lands.
