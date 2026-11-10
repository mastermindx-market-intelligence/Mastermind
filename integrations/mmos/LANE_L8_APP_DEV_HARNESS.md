# Lane L8 — native window and its dev environment (was: agent test environment)

Lead: glm-5.3 (T3). Branch `t3/mmos-v2-l8`. Trunk: `origin/feat/mmos-v1-integration-t3`.
Evidence: `~/.mastermind/mmos_evidence/l8-20261110/`.

**Re-scoped by the principal 2026-11-10** (delivered with D0's return; basis
`integrations/mmos/PROGRAM_PLAN_V3.md` @ `46621f5ad`): Paperclip is the product shell; the Mac
app becomes a thin native window that opens a local address and holds no product logic. Dropped
from the old scope: fixture failure injection, proof-page extension, the standalone browser path
(L9 owns the dev instance), the cold-agent acceptance test (L9's), and the APP_DEV_HARNESS runbook
(replaced by a skill ≤100 lines). The old LOCAL_OPERATOR_CONTRACT discrepancy is closed — the
contract landed on trunk with the same refresh.

## Re-scoped outcome (return when 1–4 pass)

1. Land slice A (launcher, dev bundle identity `com.mastermind.os.dev`) and D0 (dev log). D0 landed.
2. Shell mode: `MM_SHELL_URL` at launch → main window loads that address, no sign-in gate;
   unset = today's behaviour byte-identical. Accept only `http://127.0.0.1[:port]` /
   `http://localhost[:port]`; refuse anything else with a logged reason. Zero IPC for the loaded
   origin. Tests for accept and refuse.
3. Page verbs that work on whatever page the window shows: navigate, read page text or
   accessibility tree, click, type, read console errors and failed requests, window-scoped capture.
4. Proof: dev bundle in shell mode against a self-served local page (L9's launcher not on trunk
   yet); one window-scoped capture + dev log excerpt. Default instance `:3100` — load and capture
   only, no clicks, no typing.
5. `skills/mmos-app-dev/SKILL.md` ≤100 lines; links to L9's module skill, does not duplicate it.

## Slices

| Slice | What | Model / shape | State |
|---|---|---|---|
| R1 | Reuse scan: Rust→JS return path **without IPC**, WKWebView snapshot, socket listener choice | glm-5.3 + gemini-4-argon, two investigators | R1a (glm-5.3) **accepted** — hash verified, 92 lines, all claims sourced; R1b (argon) failed twice on a provider transport bug (missing thought_signature), rerouted to deepseek-v4-pro (R1c) with the sharpened no-IPC question |
| A | `tools/mmos_dev.py` up/down/status, dev root, npm-dep handling | deepseek-v4.1-flash, diff+test | **landed** `2902c33f6` → lane `9eb0f4368`; lead re-ran pytest: 30 passed, 0 failed; py_compile clean. A2 will add `up --url` (dev bundle in shell mode) once S1 lands |
| D0 | `dev_log.rs` JSONL logger + redaction | deepseek-v4.1-flash, diff+test | **landed** `0319f54b5` → lane; lead re-ran `cargo test dev_log`: 3 passed, 0 failed |
| C | Page verbs via `install.ts`/`proof.tsx` + fixture failure injection | deepseek-v4.1-flash | **cancelled** (re-scope: surface dropped; verbs move to a native-injected bootstrap that works on any page) |
| S1 | Shell mode: `parse_shell_url` + env-gated startup branch + refusal logging + no-remote-IPC guarantee + `tauri.conf.dev.json` overlay + minimal injected page bootstrap | deepseek-v4.1-flash, diff+test; then grok-4.7 attack pass on the diff | launching |
| S2 | Full page-verb set + result transport (after R1 verdict + S1 landing; replaces S1's minimal bootstrap) | deepseek-v4.1-flash, diff+test | queued |
| A2 | Launcher `up --url <addr>`: build + launch dev bundle in shell mode, background, pid discipline | deepseek-v4.1-flash, diff+test | queued (after A returns) |
| S3 | `skills/mmos-app-dev/SKILL.md` | written last, from what works | queued |
| Proof | Item 4 evidence under `l8-20261110/shell-proof/` | lead-held (desktop law) | queued |

## Frozen decisions (carried + new)

- Dev root `~/.mastermind/mmos_dev/` (env `MMOS_DEV_ROOT` overrides for tests): never
  `/Library/Application Support/MastermindExecutive`, never `<checkout>/data/control_plane/`
  (the Executive per-checkout default = L1's scratch root, `control_plane/executive_runtime.py:324`),
  never `/tmp`.
- Dev identity: `tauri.conf.dev.json` as a **merge overlay** (`productName` "Mastermind OS Dev",
  `identifier` `com.mastermind.os.dev`; deep-link scheme also `.dev` if the base carries one).
- Shell URL gate: scheme exactly `http`; host exactly `127.0.0.1` or `localhost`
  (case-insensitive); port free (explicit or default) — the boundary is loopback+cleartext-local,
  not the number. Refuse https, `0.0.0.0`, `[::1]`, other hosts, `file:`, unparseable, userinfo —
  refusal reason never embeds the raw input (userinfo could carry a secret).
- No IPC for the shell origin: Tauri 2 grants remote origins nothing unless a capability has a
  `remote` key; navigate the existing `main` window and a test asserts no `capabilities/*.json`
  contains `remote`.
- Page bootstrap is injected by the native side (`initialization_script`), not app frontend code:
  in shell mode the loaded page is not ours and has no `MastermindAppControl`. S1 buffers verb
  results on `window.__mmShell` until the transport lands (R1 question 3, now harder: no IPC).
- CRITICAL-row surface (shell mode + remote-control): files listed under `CRITICAL FOR RC REVIEW`
  in the lane return; S1's diff gets a grok-4.7 attack pass (reproducing command per finding).
- Desktop law unchanged: one GUI-driving child at a time, background launch, webview-only
  captures, no image to a vision model unless it is that webview render, no GLM GUI children,
  20-minute box. Proof driving is lead-held.

## FLEET

| Model | Launched | Accepted | Rejected | Cancelled |
|---|---|---|---|---|
| deepseek-v4.1-flash | 3 (A, D0, C) | 2 (A: 30/0, D0: 3/0) | 0 | 1 (C, re-scope) |
| glm-5.3 | 1 (R1a) | 1 (R1a) | 0 | 0 |
| gemini-4-argon | 2 (R1b ×2) | 0 | 0 (provider transport bug both times, not a finding) | 0 |
| deepseek-v4-pro | 1 (R1c) | pending | 0 | 0 |

R1a load-bearing facts (verified): tauri lock **2.11.6**; `eval_with_callback` added **2.12.0** (crates.io max stable 2.12.5 — refresh reachable); WKWebView snapshot donor = mcp-server-tauri `macos.rs` (MIT; `with_webview` → objc2-web-kit 0.3.2 takeSnapshot → block2 RcBlock → mpsc; all crates already in our lock via wry); screen-capture donors (tauri-pilot cgwindow, connector xcap, Victauri) **rejected by law**; UDS listener = std-thread `std::os::unix::net`, no tokio feature churn; tauri-plugin-log 2.10.1 viable but D0's serde_json appender already landed — adopt only if rotation/file-target needs emerge. R1a's invoke-reply return path serves the app's own page only; the shell page needs zero IPC → R1c's question.

## Notes

- `build.rs` requires `MM_SOURCE_REVISION`/`MM_BUILD_IDENTITY` at compile time (D0 finding).
- Trunk refresh `46621f5ad` brought `PROGRAM_PLAN_V3.md` and `LOCAL_OPERATOR_CONTRACT.md`.
- Old DONE_WHEN 6 (cold-agent) transferred to L9 per PROGRAM_PLAN_V3 §5.
