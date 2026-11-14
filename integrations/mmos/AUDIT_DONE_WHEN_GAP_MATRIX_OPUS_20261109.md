# Distinct program gap audit — DONE_WHEN rows 1–7 at `70dabba15` (Director J, Opus READ_ONLY)

Reviewer: Claude Opus 5.5, READ_ONLY on the capacity_fabric path (distinct from the GLM-5.3 lane authors and the Fable
integrator). Ran at this head: 54 lane-touched python files → 2087 passed / 10 skipped / 1 strict xfail; 133 further files
(every `claim_job` caller, session-bridge, pins, executive_mcp, GitHub readers) → 4819 passed; `tsc` green; full vitest
427 files / 7097 passed / 6 load timeouts (pass in isolation); cargo 284 passed / 8 ignored. Live read-only: T3 desktop
:3773 listening; Executive MCP :8731 and :8748 not listening.

**Bottom line:** no DONE_WHEN row is PROVEN_INSTALLED. The installed app (`~/Applications/Mastermind OS.app`, rev
`3652d89`) and the installed Executive (release `dd45d11…`) are master builds without lane code or the V1 stack.

## Matrix (status per sub-claim)

| Row | PROVEN_BY_TEST / LIVE_NARROW | MISSING / CONTRADICTED | Most important missing piece → lane |
|---|---|---|---|
| 1 Team roster + persistent bot conversation | roster producer (test); bot conversation (#2180 live, narrow); no production fixtures | roster in installed app; typed continuity SOURCE_ONLY | build from pushed head, install, receipt, open Team → I (after B2 pin policy) |
| 2 One admitted coding handoff | idempotent admission; `claim_job` sole authority | no `t3-native` route row in `config/executive_worker_routes.json` (join unreachable); no original-requester carriage; Hermes ingress (WO-19 not executed, :8731 dead, mmx-mastermind disabled); namespace CONTRADICTED (constant `T3_REQUEST_NAMESPACE`) | v1.2 requester block + route row (enabled=false) → C2 / publication |
| 3 Exactly one T3 thread + harness, visible in OS | adapter launch/read/result live-narrow; exactly-one projection (test + synthetic live demo) | not visible in OS (bridge hunks not applied → now Workspace route, G2); streaming/changes/tests/PR; duplicate-launcher detection only (master #2372 adds a second T3 launcher `t3_web_client.py`); deep link unknown | A3 rework → G2 route → D |
| 4 Crash-safe original execution | single-process cold restart (test); canary S1/S2/S4 live-narrow (S3 stubbed namespace) | audit #1–#7 open at this head (cross-process double launch, namespace attestation, lost reply, exact-run interrupt, spec round-trip, executive.sqlite3 guard name-only, patch Layer.build) | A3 rework + canary re-run with a real second OAuth client |
| 5 Authoritative return | projection + idempotent delivery (test) | live Secretary delivery SOURCE_ONLY; not wired at `complete_attempt`; no GitHub lifecycle reader; requester carriage; UI CONTRADICTED (`ResultReturnCard` orphan with own `accepted: boolean`) | C2 wiring + reader; D3 contract unify |
| 6 Usable UI from 34 boards | components (test) | installed; ~16/34 boards mapped; three null-fed surfaces; Fleet attempt block | D (after A3/C2/G2) then install via I |
| 7 Negative matrix, CI, merge, receipts, rollback | 6/20 rows (test); receipt + rollback tools (test, fake bundles); one live receipt of the wrong generation | current-head CI (now dispatched on 6d5b2f737); protected merge; marker SOURCE_ONLY (now applied at 6d5b2f737) | push + green CI → build/install/receipt → Hermes publication |

## Top 10 risks (reviewer's order)
1. Nothing pushed/installed (single point of loss) — *addressed: pushed as `feat/mmos-v1-integration-t3`, CI dispatched.*
2. Prior-audit blockers open; canary "DONE" ran on the un-reworked adapter (S3 stubbed) — A3 in flight.
3. Idempotency identity wrong end-to-end (constant namespace at claim; live port cannot attest; upstream T3 may have dropped the launch retry key per master `docs/T3_WEB_COLLABORATION.md`).
4. #2329 r5 guard bypassable (`P=po; L=ol; $P$L run …`, `python3 -c "'po'+'ol …'"`, `exec(bytes.fromhex(…))`, `echo <b64> | base64 -d | sh`); CRITICAL; r5 lives on this branch not on #2329 — C3 in flight.
5. Master moved 10 commits (#2372 second T3 client; #2344 sign-in) — Director M merging.
6. Row 2 has no live path (route, requester, WO-19, :8731, plugin, reader behind Control release).
7. Duplicated machinery: two return contracts (F vs D) → D3; three new `ps` readers beside `executive_process_identity`/`darwin_process_image`; TeamLink schema two owners; three T3 ports.
8. State-store hazards: per-checkout adapter state path orphaned on Executive upgrade; README line 48 (fixed); `WorkspaceLeaseStore` unguarded + WAL.
9. Gateway `code_sha` pin (`2bd378ed…` vs hermes-agent HEAD `ba4ddf99`) will hard-refuse native session + roster after the next gateway update → B2.
10. Reviews/proofs owed: CRITICAL pin moves (now reviewed ACCEPT), #2329, #2311 r2, #2313 delta, #2353, #2356; six-shard CI (dispatched); vitest flakes; handoff §3 "THREE arg rows" for DSH contradicted by live refusal (repo's two rows are right — Hermes should correct the handoff text).

## Hard-constraint check (scope `git diff ff6d5ab67..HEAD`, 202 files)
- User-home paths in committed JSON/stdout artifacts (quota preview, wo19 inventory/dryrun, canary receipt) — *redacted to `~` by the integrator.* No token/secret patterns.
- Two new SQLite stores vs handoff §2 "no new database": `t3_adapter_state.sqlite3` (integrator ruling: required — the Executive file's whole-file schema digest is pinned and bricks on foreign tables; recorded in the adapter audit) and `WorkspaceLeaseStore` (unguarded — to fix).
- #2177 overlap: reviewer could not reproduce via `gh pr view` (404 for its login) — the C/E review reproduced it via `refs/pull/2177/head` = `70a6cf453` (0 conflicts, no overlap). `executive_worker_routes.json` was edited by the pre-lane WO-18 stack (`81f0ef90`), not by a lane.
- Not found: new listener/queue/registry; production fixtures; `executive.sqlite3` DDL (digest `7692d62b…` unchanged); edits to #2351/#2182/#2186/#2342 files; repo writes to `~/.hermes`.

## Test union before publishing
The 54 lane-touched files + the 133 `claim_job`/session-bridge/pin/executive_mcp/GitHub-reader files (regenerate:
`{ grep -rl claim_job tests/; ls tests/test_session_bridge*.py tests/test_next_mounted_identity_pins.py tests/test_executive_reviewed_site_identity_tokens.py tests/test_company_consultation_identity_review.py tests/test_executive_mcp*.py tests/test_github_pr_lifecycle.py tests/test_github_review_result_reader.py tests/test_mastermind_os*.py tests/test_hermes_primary_session_return.py; } | sort -u`),
after the master merge also `git diff --name-only ff6d5ab67 origin/master -- tests/`; frontend typecheck + vitest + both
vite builds + browser-proof + adapter.test; cargo; and the six-shard CI matrix on the exact pushed head.

## Integrator disposition (Fable)
P1 items pushed/dispatched; A3, C3 (guard r6 + namespace), C2 (requester v1.2 + return wiring + GitHub reader), G2
(fleet read route), B2 (code-pin policy), D3 (one return contract), M (master merge) in flight. Remaining integrator
items: `WorkspaceLeaseStore` executive.sqlite3 guard; `t3-native` route row decision (file carries #2177 hunks at
lines 4 and 56 — publication-time, with Hermes); adapter state path under the Executive data directory (A3 note #15).
