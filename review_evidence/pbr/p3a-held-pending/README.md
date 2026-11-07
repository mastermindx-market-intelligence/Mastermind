# PBR L-P3a — a queued change on a held lot is shown on its Positions row

Truth rule (MASTERPLAN §10.2): *a queued MU exit must show as a pending change while MU is
still held.* Before this change the Positions verdict cell kept the book's stale verdict
(`HOLDING`) while `/api/trades.pending_target` already carried the accepted queued exit, and
the Pending Orders block two panels lower said `SELL … at open`.

## What changed

- `app/static/index.html`: a pure ES5 helper `_heldPendingChange(ticker, trades)` (between the
  `PBR-HELD-PENDING-CHANGE` markers) reads only `/api/trades.pending_target`. When the target
  is `queued` and a row for a held ticker is `exit|trim|add` (or the unclassified
  `comparison_unavailable|unpriceable`), the verdict cell shows `EXIT|TRIM|ADD|CHANGE QUEUED`
  with the existing chip colours, plus a muted line "at open <fill_after date>" (or "awaiting
  settlement"), and the row gets `data-queued-change="<kind>"`. Shares, marks, P&L, weight,
  sleeve, held date and thesis are unchanged: nothing is filled until the next open.
- No server change and no new field. `hold`, `blocked`, `buy`, `filtered`, unknown actions and
  every non-`queued` status (`none`, `invalid`, `unavailable`) render exactly as before.
- Integration repair by the orchestrator: the timing line may wrap. A no-wrap line widened the
  Verdict column at 375 px and pushed the chip out of the table's scroll viewport (measured:
  scroll width 367 against a 317 px client width). With wrapping, the table measures 325 against
  317, the same as before the change.

## Tests (named suites, local venv, node present so the vm tests ran)

`tests/test_pbr_held_pending_change.py` (new: 12 tests) plus `tests/test_portfolio_dashboard_ui.py`
and `tests/test_brain_pending_truth.py`: **54 passed**. The new tests run the shipped helper in
a Node `vm` and bind it to the real `web.api_trades()` output (agreement: the API row is `MU exit`
→ the renderer returns `kind=exit`, `fillAfter == next_open`; `XOM hold` and the absent `AAPL`
both return null). Mutation checks: removing the `queued` status gate fails 1 test; running the
suite against the pre-change `index.html` fails 12 of 12.

## Local browser proof (serve-only on 127.0.0.1, captured books, read-only)

The repository is public and the dashboard sits behind a subscription tier, so the screenshots,
DOM dumps and API payloads stay out of git. They are in
`/Volumes/Mastermind/evidence/pbr/product-proof-p3a-held-pending-20261022T081553Z/`
(`SHA256SUMS` sha256 `05957365774a0a0b3f290450680717ff2c9c0076d304206bef0f04dd2bdabed0`, 11 files).
The book capture they render is `/Volumes/Mastermind/evidence/pbr/product-capture-20261022T073304Z/`
(MANIFEST sha256 `898d41f4…`).

| width | before (verdict cell, autonomous) | after |
|---|---|---|
| 1280 (headless Chrome dump + browser pane) | XOM, MSFT, MU, AAPL all `HOLDING` | MU `EXIT QUEUED` + "at open 2026-10-22", `data-queued-change="exit"`; XOM, MSFT, AAPL `HOLDING` |
| 375 (browser pane, emulated mobile, DPR 2) | MU `HOLDING` | MU `EXIT QUEUED` + "at open 2026-10-22", fully inside the viewport; the table's scroll width is unchanged |

At 1280 the Positions row now agrees with the Pending Orders block on the same page (`MU SELL …
at open 2026-10-22`). Headless Chrome's `--window-size=375` output is **not** valid phone proof:
it lays the page out wider than 375 px. The 375 evidence comes from the browser pane's viewport
emulation, where `document.scrollWidth == 375`.

## Production proof checklist (for the seat)

1. Confirm the deployed `app/static/index.html` blob equals this PR's merge blob (blob comparison,
   not `deploy_lag.json`).
2. On the autonomous book while `pending_target.status == "queued"`: each held ticker whose target
   row is `exit|trim|add` shows the matching `… QUEUED` chip and the "at open <date>" line, and the
   row carries `data-queued-change`. Every other held row is unchanged.
3. The same rows agree with the Pending Orders block and with `/api/trades.pending_target.rows`.
4. At 375 px the chip and the timing line are visible without horizontal scrolling.
5. The ZH toggle shows `已排队卖出 / 已排队减仓 / 已排队加仓 / 已排队调整` and `开盘 <date>`.
6. After the fill (`pending_target.status` leaves `queued`), the chip goes away and the row
   follows the book again; a sold-out lot drops out of Positions.
