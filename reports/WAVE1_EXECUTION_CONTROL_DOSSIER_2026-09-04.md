# WAVE 1 EXECUTION-CONTROL DOSSIER

```yaml
operation_key: portfolio-wave1-execution-control-20260903-sol-001
parent_freeze: MMX-PORTFOLIO-FREEZE-20260903-001
producer: Claude CEO session (claude-fable-5), branch claude/ceo-project-completion-ddd6bf
observation_window_utc: 2026-09-04T10:45:12Z – 2026-09-04T11:05Z
effect: NONE  # zero writes to Slack, Linear, GitHub carriers, Agent OS, or production
sources: gh (identity chriswong6031-creator), Slack MCP read-only, Linear MCP read-only,
  anonymous production browser, git ls-remote, local read-only checkout census
evidence_bundle: session scratchpad evidence/ (PINS.md, carrier_summary.md, slack_*.md,
  linear_projections.md, public_surfaces.md, open-PR + changed-file censuses, agentos WS files)
```

## 0. Fresh pins (vs freeze pins)

| Repo | Freeze pin | Observed 2026-09-04T10:45Z | Moved |
|---|---|---|---|
| Mastermind master (protected) | 3055b499 | **cc03ea32**9148a44b048b65a4649481d637980dd3 | yes |
| macro main | ce976afa | **fdaf4091**0809de8da38e91c4696abfa22d2199e0 | yes |
| terminal master | fadd8b82 | fadd8b82f03ecaabe8a86d693da89f27be096d9f | no |

Executive OS runtime: **BLOCKED_EXECUTIVE_RUNTIME** — no runtime database on host (searched Mastermind checkout; only `data/bot.db` = trading bot), executive.control launchd job not bootstrapped. All `EXECUTIVE_PLACEMENT` fields remain unprovable; nothing in this dossier infers admission or capacity. Restoration is operator work.

Procedure-file drift note: freeze §1.1 lists `AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` and `EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md` as same-SHA loaded files at 3055b499; neither filename exists in the cc03ea32 tree (`docs/sol_skills/` now holds 9 files: BOOTSTRAP_KERNEL, CLOSEOUT, COLD_START, COMMISSION_WAVE, INDEX, RECONCILE_STATE, REVIEW_RETURN, WATCHER_ACTION_LOOP, WORKER_AVENUE_ROUTING). Any packet citing those two files must re-derive the law from the current pin.

## 1. Carrier table — one row per §9.1 operation

Legend: state names use the freeze's vocabulary. "Next lawful edge" is a recommendation to Sol, not an action taken.

### 1. Prophet D5 authenticated proof — `prophet-d5-authenticated-browser-production-proof-20260903-sol-003`
- **Carrier:** macro issue #6797 (OPEN) + Slack `C0BSBM78V1N/1788454392.789159` + Codex task `01a06966-799f-7720-b093-32b13f203af8` — singular, no sibling found.
- **State:** `PRE_START / CHAIRMAN_LOGIN_REQUIRED / STICKY_OWNER / BLOCKED_AUTH`. Exact thread shows PICKUP_ACK → WATCH_ARMED (Class-M/60m) → CHAIRMAN_LOGIN_REQUIRED → PROGRESS ("control surface recovered; site_full still absent", receipt 1788487287.239349). Effect NONE.
- **Post-freeze movement:** PROGRESS edge only; worker claimed the already-open China-dashboard tab; Settings>Account still signed out.
- **Collision:** none. **Dependency:** Chairman login (site_full) only; D5 does not block B2-0.
- **Next lawful edge:** Chairman signs into the already-open trusted normal production tab; then same-carrier Sol posts `CONTINUE prophet-d5-authenticated-browser-production-proof-20260903-sol-003`; same task STARTs. *(This is the §13.2 action — it needs Chris personally; no automation may do it.)*
- **Capability:** proves authenticated machine path (site_full envelope retrieval); trust-critical, unlocks nothing by itself.
- **Side observation for owners:** the worker reported one automated click on the public "Sign in" control on china_stocks.html produced no URL change/auth dialog/popup. Unverified against a human click path — flagged as a possible public login-UI defect worth an owner look, NOT acted on.

### 2. Breathing C2-A — `breathing-c2-closepass-host-lane-repair-20260829-sol-001`
- **Carrier:** Slack `C0BSBM78V1N/1788248718.881509`; CTO-FORGE task `01a04bdf-7a7b-7f63-9abd-9a7c13e944c0`; branch `claude/breathing-c2a-host-lane-repair-20260901` in worktree `/Users/chriswong/Documents/Cluade/macro-main/.claude/worktrees/breathing-c2a-host-lane-repair-20260901`.
- **State:** `STARTED / PARKED / STICKY_OWNER`. Latest canonical edge = SOL RULING/PARK: same native task lawfully owns Chairman-priority W3C (`w3c-runtime-composition-r0-20260901-forge-001`); C2-A mutation must not resume while W3C holds the modifying turn. Preserved local effect: exactly 2 unstaged paths (`scripts/close_pass_host_runner.py`, `tests/test_close_pass_host_runner.py`, +152/−9) at HEAD f30a9f6d. Effect local-only, bounded, known.
- **Collision:** the runtime-surface collision with W3C is the parking cause; no repo-path collision.
- **Next lawful edge:** W3C release/reconciliation, then explicit Breathing-Sol `CONTINUE` on this same carrier. Not placeable while Executive runtime is absent and W3C is unreleased.
- **Capability:** infrastructure (close-pass host lane repair); feeds Breathing natural-session acceptance (D-16), which feeds board freshness (T).

### 3. Options C0 — macro PR #6604
- **State:** OPEN / DRAFT / HOLD-FOR-SOL at head `7cc1b336`; 4 records files (DEC/handoff/config/mastermind_programs.yml/masterplan); checks green at head; mergeable UNKNOWN (GitHub recompute); updated 2026-09-03T05:17Z. Matches freeze: registry blob (`config/mastermind_programs.yml`) copied older than current main ⇒ `CURRENT_BASE_REQUIRED` on that one artifact.
- **Collision:** none of its 4 paths appear in any other open PR.
- **Next lawful edge:** same-PR surgical reconciliation of the registry blob to then-current main, fresh exact-head checks, Sol review. No replacement C0 PR.
- **Capability:** program-control record; gates AD-1T2 (MAS-196) and MAS-86 placement. Status-only itself — correctly held below product spine.

### 4. Eval OS A1 — macro PR #6651 (+ release op `eval-os-a1-release-visual-proof-20260830-sol-001`, records PR #6689)
- **State:** OPEN / DRAFT / HOLD at exact head `036d5bc0` (unchanged); MERGEABLE/CLEAN; 13 files; checks green at head; `BUILT_NOT_PROVEN / PRODUCTION_INERT`. Release op remains `WAITING_CAPACITY / needs_placement` (no lawful receiver found in fresh Slack searches per MAS-194 09-03/09-04 entries; Executive runtime absent ⇒ `BLOCKED_CAPACITY`).
- **Banked current-base obligations (from MAS-194, 09-02→09-03):** any current-base reconciliation must preserve the merged CI-manifest authorities of #6767/#6773/#6741/#6771/#6780/#6786/#6791/#6795/#6796/#6808/#6812/#6721 in `.github/ci/legacy-jobs.yml`, plus A1's own `tests/test_admin_intelligence_os_ui.py`, and #6767's staleness reader-plane behavior in `admin/intelligence_os.py`.
- **Collision:** `.github/ci/legacy-jobs.yml` co-edited by held PRs #6625 and #6832 (different regions asserted, not proven). **Linear drift:** MAS-194 status chip says "In Progress" while its own body says WAITING_CAPACITY — status field is a stale projection; body + GitHub govern.
- **Next lawful edge:** place the SAME release operation (13-path census → dark/light × EN/ZH × 1440/390 authenticated proof → exact-head CI → independent review). No rebase-for-aesthetics while mergeable=CLEAN.
- **Capability:** evidence maturity visible to CEO (P-14/journey step 7).

### 5. Terminal account/entitlement stack — #444 → #445 → #446
- **State:** all OPEN, non-draft; #444 BEHIND, #445/#446 BLOCKED; **required check `Terminal typecheck + tests` = FAILURE on all three**; heads a28adb32 / 0b804381 / 1f4a075f; updated 09-01→09-03. Matches freeze rank 5.
- **Collision (in-stack + neighbors):** the three PRs share entitlement/settings paths by design (stacked); #435 also touches `OnboardingSheet.tsx` shared with #445/#446 — order-sensitive; Terminal PR #502 touches `terminal/lib/watchlistsFixtureDb.ts` (future Wave-2B watchlist territory, not this stack).
- **Next lawful edge:** reconcile in exact order #444→#445→#446 on current protected master; make the required check green at exact heads; owner-switch/stale-last-good/browser proof. No parallel entitlement reader.
- **Capability:** account identity/entitlement semantics for activation (C-04/C-05).

### 6. Billing D7 safety — Terminal PR #435
- **State:** OPEN, BEHIND, required check FAILURE, head d6eb13f2; 6 files (onboarding/billing receipt). Matches freeze rank 6.
- **Collision:** `OnboardingSheet.tsx` shared with #445/#446 (and #446's prefs work) — adjudicate with the stack, no sibling onboarding rewrite.
- **Next lawful edge:** same-PR defect adjudication + current-base proof preserving the fail-closed receipt/date contract.
- **Capability:** money-surface safety (C-08); explicitly not activation completion.

### 7. Terminal quote-demand continuity — PR #429
- **State:** OPEN, BEHIND, required check FAILURE, head 7b30fc8a; 7 files (quote route/demand). Matches freeze rank 7.
- **Collision:** `TerminalShell.tsx` also edited by #444/#445/#446 — coordinate ordering with the stack.
- **Next lawful edge:** same-carrier current-base/test repair + production identity proof.
- **Capability:** prevents shell/live-data regressions (guards journey step 4/5 surfaces).

### 8. Prophet post-D5 records — macro PR #6801
- **State:** OPEN / DRAFT at head 9b033640 (branch `sol/prophet-post-d5-critical-path-reset-20260903`), 3 records files, checks green, updated 09-03T17:12Z — i.e. it was refreshed the same day as the freeze; whether its text now reflects the CURRENT D5 hot state (control-surface-recovered PROGRESS edge of 09-04) was not verified line-by-line here.
- **Next lawful edge:** verify/amend the SAME three-file PR against the D5 thread's latest receipts; records only; then Sol review.
- **Capability:** durable-truth repair (status-only; correctly ranked below product).

### 9. Market Memory M0D
- **State:** `BUILT_NOT_PROVEN`, natural-proof lane; no forced rerun observed; no new carrier found in open-PR census (memory recharter records PR #6528 remains draft/records).
- **Next lawful edge:** await natural proof window; record first causal failure if it occurs. No action needed from Wave 1.

### 10. Stock Identity sustained program — `SI-FABLE-COO-PROGRAM-20260828`
- **State:** active sustained ownership; WS-STOCK-IDENTITY shows W0–W2 done, W3+ todo; records PR #6672 (W3A recovery restart) draft. No competing carrier.
- **Next lawful edge:** existing Sol/owner continuation only; outside Wave 1 authority.

### 11. Rates F0 / durable status — merged macro PR #6543
- **State:** #6543 MERGED 2026-08-28T03:02Z (GitHub truth: F0 done). **`WS-RATES-INFLATION-COMMAND.md` on current main still reads `status: awaiting_ci` — STALE_PROJECTION persists** (freeze contradiction #10 not yet repaired).
- **Next lawful edge:** records-only workstream reconciliation after collision check; F1/F3 remain NOT_BUILT and gated behind fresh admission.

### 12. Flow Observatory W7 — macro PR #6815 — **POST-FREEZE STATE CHANGE**
- **State:** **MERGED** (updated 2026-09-04T08:00:15Z), 15 files incl. `config/growth_events.yml`, `app/main.py`, `templates/flow_velocity.html.j2`, tests, W7 evidence shots. `WS-FLOW-OBSERVATORY-V2.md` now reads `status: done` — Agent OS and GitHub AGREE (freeze contradiction #11 resolved by events).
- **Consequence:** the freeze-time constraint "no `growth_events.yml`/`/api/collect` edits while #6815 unresolved" is **released**; growth-vocabulary path is unblocked for future activation work (C-02→C-03). Production proof of W7 remains whatever its own dossier claims — merge is not proof.
- **Next lawful edge:** none owed on this carrier; downstream activation children may now census these paths fresh.

## 2. New/changed carriers detected since the freeze (not in §9)

| Carrier | What it is | Wave-plan impact |
|---|---|---|
| macro PR **#6831** (`claude/market-os-msft-security-truth-20260904`, draft, upd 09-04T10:34Z) | `engine/security_state.py` + golden **MSFT** fixtures + contract/view-model tests | **Wave 2A (`market-os-b1b-non-aapl-security-state`) is de-facto in flight on another carrier; reference issuer operationally = MSFT.** Wave-2A planning row must bind to THIS carrier, not mint a sibling. |
| macro PR **#6825** (Agent OS records, upd 09-04T10:14Z) | "Record MSFT owner-composition frontier / IMPLEMENTATION STARTED" + discovery `DSC-MARKET-OS-IDENTITY-PRIMITIVES-EXIST-COMPOSITION-MISSING` | Same — durable record of the above. |
| macro PR **#6832** (prophet cockpit p0b zero-FOUC, draft) | HK/Canada first-frame canonical fix; touches `.github/ci/legacy-jobs.yml` | No collision with B2-0 evidence-contract paths; adds to the hot shared CI-manifest zone. |
| Market Ontology F-lanes #6820/#6826/#6828/#6829/#6830/#6833 (all draft, 09-04) | Parallel F01/F04/F10/F13 architecture/records lanes | None touch acquisition-surface or Prophet-evidence paths (verified in changed-file census). |

## 3. Collision census for the two Wave-1 modifying children (action-time)

- Packet B paths (`templates/index.html`, `site/index.html`, `scripts/build_vector.py`, `site/start.html`, `site/stocks/index.html`, `config/growth_events.yml`): **zero hits** across all 77 open macro PRs' changed files (736 rows). Clean lane. `config/growth_events.yml` released by #6815 merge but still out of Packet B scope.
- Packet C paths (Prophet evidence/disposition contract + tests): only Prophet-adjacent open PR is #6832 (site/mockups/CI-manifest; no engine/prophet evidence paths). Clean lane pending exact-path enumeration at START.
- Shared caution: `.github/ci/legacy-jobs.yml` is additively co-edited by #6625 and #6832 and carries the banked manifest authorities listed under carrier 4 — any Wave-1 child adding tests must edit it additively and re-verify no textual conflict at PR time.

## 4. Public-surface regression observation (anonymous, 2026-09-04)

See `public_surfaces.md` for full capture. Deterministic highlights:
- Homepage "PROPHET · TODAY" card carries **Jul 21** content; "REAL CALLS · 2-WEEK DELAYED" carries **BOARD OF AUG 14** (21 days). P-01 defect live.
- Stocks index: coverage sentence now says **1,955** dossiers (freeze saw 1,564; other surfaces claimed 2,700+/1,600+) — denominator drift is ACTIVE; its "AT THE CLOSE" strip is **2026-08-31** (3 sessions stale) with em-dash index values.
- US board `us_stocks.html`: **Data through 2026-09-03** — fresh; P-03 confirmed.
- `start.html`: current WHAT-CHANGED entries; consistent regime labels; no stale-wrapper observed.

## 5. Contradiction list (system vs system, with governing source)

1. Linear MAS-194 status chip "In Progress" vs its own body + Slack ("WAITING_CAPACITY, no receiver") → GitHub/Slack govern; chip is stale projection.
2. Agent OS WS-RATES `awaiting_ci` vs merged #6543 → GitHub governs; records repair owed (freeze already ruled this; still unrepaired).
3. Freeze §9 "#6815 OPEN/conflicted" vs GitHub MERGED → events superseded the freeze row; Wave-1A item "same-carrier conflict repair" is DONE by the existing owner (as the freeze prescribed).
4. Freeze planning row "Wave 2A reserved, not dispatched" vs live #6831/#6825 MSFT implementation → carrier-singularity law: the LIVE carrier wins; planning row must be re-pointed, not duplicated.
5. Freeze §1.1 procedure-file list vs cc03ea32 tree (two law files absent) → current protected pin governs; cite current files only.
6. Homepage/stocks-index freshness & counts vs US board (§4) → canonical product surfaces govern; acquisition projection is the defect (Packet B's charter, confirmed).

## 6. Recommendations returned to Sol (no edges posted by this orchestrator)

| Carrier | Recommendation |
|---|---|
| D5 #6797 | **CONTINUE** — needs the §13.2 Chairman login first; everything else is armed and sticky |
| Breathing C2-A | **HOLD** (parked correctly) until W3C release; then CONTINUE same carrier |
| Options C0 #6604 | **REPAIR** (registry blob current-base) then REVIEW |
| Eval A1 #6651 | **REVIEW/PLACE** the existing release op; do not rebase while CLEAN |
| Terminal #444→#445→#446 | **REPAIR** in order (required check red) |
| Terminal #435 | **REPAIR** same-PR (money-safety contract preserved) |
| Terminal #429 | **REPAIR** same-PR |
| Prophet records #6801 | **REPAIR/verify** against 09-04 hot state, records-only |
| M0D | **HOLD** (natural time) |
| Stock Identity | **CONTINUE** existing program (no Wave-1 action) |
| Rates durable status | **REPAIR** records-only (still stale) |
| Flow W7 #6815 | **CLOSED by merge** — remove from stuck queue; production proof tracked by its own dossier |

**Stop condition met:** this dossier is returned to Sol and the orchestration role terminates with it; no scheduler, watcher, queue, or portfolio control plane remains alive from this packet.
