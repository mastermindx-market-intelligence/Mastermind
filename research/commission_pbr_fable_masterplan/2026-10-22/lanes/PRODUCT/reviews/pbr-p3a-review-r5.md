# Independent review: PR #1707 (L-P3a held pending change)

- reviewer lane: `pbr-p3a-review-r5`, host ubuntu1, model glm-5.3-flash, class review C2 (ECONOMIC_POLICY allowed, tier leaf-labor), LEASE_OK pool=glm, REMOTE_DONE rc=0 at 2026-10-22T08:38Z
- builder lane: `pbr-p3a-held-pending-r3` (MiniMax-M3, ubuntu2). Builder and reviewer are different lanes and model families.
- reviewed identity: PR #1707 head `faee0e32` on base `d31aade9`, applied as uncommitted edits in a fresh origin/master checkout
- tier deviation: the commissioned review tier was glm-5.3 or qwen3.8-max. glm-5.3 at C2 was refused by ECONOMIC_POLICY (rc=78, not retried) and qwen3.8-max returned HTTP 429 on rounds r1, r3 and r4. The lane was moved to glm-5.3-flash at r5.

## Reviewer narrative (verbatim)

Review complete. All evidence gathered; here is my assessment as the independent reviewer.

## Review summary

**Scope (1)** — `git status --short`: `M app/static/index.html`, `?? tests/test_pbr_held_pending_change.py`, `?? review_evidence/pbr/` (which `--untracked-files=all` resolves to exactly `review_evidence/pbr/p3a-held-pending/README.md`), plus the ignored `_pbr_review/`. The other `review_evidence/` trees (`provider_realms/`, `session_truth/`) are already tracked (`git ls-files`). The README contains tickers, chip labels, pixel measurements and off-repo evidence paths + sha256 only — no quantities, cash, NAV or credentials. **PASS.**

**Helper contract (2)** — walked every branch of `_heldPendingChange` (`app/static/index.html:4725-4778`) against BUILD_PACKET §1: null cases (non-object `trades`/`pending_target`, non-`queued` status via case-insensitive `String(...).toLowerCase()`, empty ticker, `rows` without numeric `length`, no matching row) all return `null`; kind mapping is exactly exit/trim/add → classified, `comparison_unavailable`/`unpriceable` → `unclassified`, `default: return null`; returns a fresh 6-field object; `fillAfter`/`queuedAt` fall back row → target through a trimming `strOrNull`; `finiteOrNull` requires `typeof === 'number' && isFinite` (NaN/Infinity/numeric-strings → `null`, matching "<finite number or null>"). ES5 only (no `=>`/`let`/`const`/template literals in the block); references only standard builtins (`String`, `isFinite`) — proven by the tests running it in a bare `vm.createContext({})`. No input mutation. **PASS.**

**Wiring (3)** — `app/static/index.html:4830` calls it only via `p.pending ? null : _heldPendingChange(p.ticker, _trades)`. Null path: `qAttr=''` and `verdictCell` is byte-identical to the removed line, so row markup is unchanged. Non-null: only the verdict `<td>` is replaced and `data-queued-change="<kind>"` (fixed whitelist) is added to the `<tr>`; shares/entry/current/P&L/weight/sleeve/held/thesis strings are untouched; `p.verdict` is only read (`:4804`), never written. **PASS.**

**Truth (4)** — `exit` → `exit_pending` chip "EXIT QUEUED" + "at open <fmtDate>"; `unpriceable`/`comparison_unavailable` → grey `hold` chip "CHANGE QUEUED", never a guessed direction; `invalid`/`unavailable`/`none` → `null` → stale verdict, unchanged; nothing claims a fill — the row still shows live marks/P&L and the "QUEUED … at open" phrasing matches the existing Pending Orders vocabulary (`:5044`). Verified against `_pending_target_projection` (`app/web.py:2001`): held + target 0 → `exit`/`sell`, missing price → `unpriceable`, weights unavailable → `comparison_unavailable`, one row per ticker. **PASS.**

**EN/ZH (5)** — all four keys at `:3449-3452` with `en`+`zh`; ZH `已排队卖出/已排队减仓/已排队加仓/已排队调整` matches `pos.v_exit_pending` (`已排队卖出`) and `pend.*` tone. `t()` (`:3586`) falls back en → key. **PASS.**

**Design (6)** — one new rule, `var(--muted)` only, existing chip classes only (`add`/`hold`/`trim`/`exit_pending` at `:344-348`), no hover-only info, no new accents. The `white-space:normal; line-height:1.25` repair is the approved deviation, with rationale in the CSS comment. From CSS: the wrapping line's min-content is the 10-char date token (~60px), smaller than the chip; "EXIT QUEUED" chips already render in this same table via pending rows' `pos.v_exit_pending`, so the Verdict column's binding width is unchanged — consistent with the measured 325px = baseline. **PASS.**

**Tests (7)** — exact line: `54 passed in 1.53s`. `-rs` on the new file: `12 passed`, no skips — node is present (`/home/longr/.local/bin/node`), so the vm tests ran. The agreement test genuinely calls `web.api_trades("autonomous")`, asserts the projection (`MU: exit`, `XOM: hold`), and feeds the parsed JSON into the marker-extracted helper in node. If `renderPositions` stopped calling the helper, the static assertion `"_heldPendingChange(p.ticker, _trades)" in source` fails; if the helper returned `'exit'` for `invalid`, `test_only_a_queued_target_produces_a_change` fails. No vacuous assertions found. One real weakness listed below.

**Other (8)** — XSS: `qWhen` (API-derived date) is `esc()`-wrapped; chip text and `qc.kind` are constants; no unescaped API string reaches markup. A throw can't blank the table (`innerHTML` assigned after the loop; every helper access is guarded). `_trades` null → helper null → fail-closed stale render.

```
RETURN pbr-p3a-review
VERDICT: PASS
tests: 54 passed in 1.53s; node tests ran: yes
findings:
1. [MINOR] tests/test_pbr_held_pending_change.py:68 — renderPositions wiring is guarded only by source-string assertions; a regression that computes `qc` but discards it (verdict cell never swapped) would pass all behavioral node tests — acceptable at C2 given house style (test_portfolio_dashboard_ui.py is string-based); non-blocking stronger fix: a DOM-level harness that executes renderPositions
2. [NIT] app/static/index.html:4836 — "at open <date>" uses fmtDate (ISO, slices to 10 chars) while the Held column uses fmtDateShort (M/D/YY); this deliberately mirrors the existing Pending Orders convention at index.html:5044, so no change required
3. [NIT] app/static/index.html:4740 — duplicate tickers in pending_target.rows would resolve to the first match; _pending_target_projection (app/web.py:2213-2260) emits exactly one row per ticker so this cannot occur today; no change required
checklist: 1=ok 2=ok 3=ok 4=ok 5=ok 6=ok 7=ok 8=ok
```
