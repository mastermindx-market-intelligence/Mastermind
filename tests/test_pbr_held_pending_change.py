"""A queued change for a HELD lot must be shown on that lot's Positions row.

The failure shape (MASTERPLAN §10.2): a book still holds MU while the accepted decision has
already queued a full target book that EXCLUDES it. ``/api/trades`` projects that queue truthfully
(``app/web.py::_pending_target_projection``); the Positions table used to keep rendering the
stale book verdict ("HOLDING"), so the primary holdings view contradicted the accepted
decision. ``_heldPendingChange`` is the pure projection the verdict cell now reads.

These tests execute the real shipped helper source in a Node ``vm`` — source-string presence
alone is not proof of behavior — and bind it to the actual ``/api/trades`` route output so the
API and the renderer cannot drift apart. No network, no live data: everything is synthetic.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "app" / "static" / "index.html"
HTML = HTML_PATH.read_text()

BEGIN_MARKER = "// PBR-HELD-PENDING-CHANGE:BEGIN"
END_MARKER = "// PBR-HELD-PENDING-CHANGE:END"

NEXT_OPEN = "2026-10-23T09:30:00-04:00"

requires_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is required to execute the shipped dashboard helper",
)


# ── shipped-source extraction ─────────────────────────────────────────────────


def _helper_source() -> str:
    """The helper exactly as shipped, between its marker lines."""
    start = HTML.index(BEGIN_MARKER)
    end = HTML.index(END_MARKER) + len(END_MARKER)
    return HTML[start:end]


def _render_positions_source() -> str:
    start = HTML.index("function renderPositions() {")
    tail = HTML.index("\nfunction ", start + 1)
    return HTML[start:tail]


# ── 1. static wiring ───────────────────────────────────────────────────────────


def test_helper_is_wrapped_by_exactly_one_marker_pair_immediately_above_render_positions():
    assert HTML.count(BEGIN_MARKER) == 1
    assert HTML.count(END_MARKER) == 1
    assert "function _heldPendingChange(ticker, trades) {" in HTML

    between = HTML[HTML.index(END_MARKER) + len(END_MARKER):HTML.index("function renderPositions()")]
    assert between.strip() == "", "helper must sit immediately above renderPositions()"
    assert HTML.index(BEGIN_MARKER) < HTML.index(END_MARKER)


def test_render_positions_reads_the_helper_and_emits_the_queued_change_attribute():
    source = _render_positions_source()
    assert "_heldPendingChange(p.ticker, _trades)" in source
    # Only held lots consult the queue; an unfilled pending row is a different, already-truthful view.
    assert "p.pending ? null : _heldPendingChange(p.ticker, _trades)" in source
    assert 'qAttr = \' data-queued-change="\' + qc.kind + \'"\';' in source
    # Presentation only: the helper must never rewrite the book's own verdict field.
    assert "p.verdict =" not in source
    assert "p.verdict=" not in source


@pytest.mark.parametrize(
    ("key", "en", "zh"),
    [
        ("pos.q_exit", "EXIT QUEUED", "已排队卖出"),
        ("pos.q_trim", "TRIM QUEUED", "已排队减仓"),
        ("pos.q_add", "ADD QUEUED", "已排队加仓"),
        ("pos.q_unclassified", "CHANGE QUEUED", "已排队调整"),
    ],
)
def test_queued_change_labels_are_localized(key: str, en: str, zh: str):
    match = re.search(r"'" + re.escape(key) + r"':\s*\{([^}]*)\}", HTML)
    assert match, f"missing i18n key {key}"
    body = match.group(1)
    assert "en:" in body and "zh:" in body, f"{key} must carry both languages"
    assert f"en: '{en}'" in body
    assert f"zh: '{zh}'" in body


def test_queued_change_chip_uses_existing_classes_and_one_new_muted_rule():
    source = _render_positions_source()
    # All four chip classes already exist; no new colours are introduced.
    for css_class in ("exit_pending", "trim", "add", "hold"):
        assert f".mm-verdict-chip.{css_class}" in HTML
    assert "{ exit: 'exit_pending', trim: 'trim', add: 'add', unclassified: 'hold' }" in source

    assert HTML.count(".mm-q-when {") == 1
    assert (
        ".mm-q-when { display:block; margin-top:2px; font-size:11px; line-height:1.25; "
        "color:var(--muted); font-weight:500; white-space:normal; }"
    ) in HTML
    # The timing line sits inside the same verdict cell, under the chip.
    assert "'<span class=\"mm-q-when\">'" in source
    assert "t('pend.fills_at_lbl') + ' ' + fmtDate(qc.fillAfter)" in source
    assert "t('pend.awaiting_lbl')" in source


# ── node harness ───────────────────────────────────────────────────────────────

NODE_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const context = vm.createContext({});
vm.runInContext(source, context, {filename: "_heldPendingChange.js"});
const helper = context._heldPendingChange;
if (typeof helper !== "function") throw new Error("helper is not defined in the vm context");

const results = cases.map(function(c) {
  const out = {name: c.name};
  try {
    if (c.tradesLiteral === "undefined") {
      const r = helper(c.ticker, undefined);
      out.result = r === undefined ? "__undefined__" : r;
    } else if (c.tradesLiteral === "null") {
      const r = helper(c.ticker, null);
      out.result = r === undefined ? "__undefined__" : r;
    } else {
      const trades = c.trades;
      const before = JSON.stringify(trades);
      const r = helper(c.ticker, trades);
      out.result = r === undefined ? "__undefined__" : r;
      // Purity: presentation must never rewrite the data object it was handed.
      out.mutated = JSON.stringify(trades) !== before;
    }
  } catch (error) {
    out.error = String((error && error.message) || error);
  }
  return out;
});
console.log(JSON.stringify(results));
"""


def _run_helper(tmp_path, cases):
    node = shutil.which("node")
    assert node is not None, "node is required to execute the shipped dashboard helper"
    source_path = tmp_path / "held_pending_change.js"
    source_path.write_text(_helper_source(), encoding="utf-8")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases), encoding="utf-8")

    completed = subprocess.run(
        [node, "-e", NODE_HARNESS, str(source_path), str(cases_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return {entry["name"]: entry for entry in json.loads(completed.stdout)}


def _queued(rows, **target_fields):
    """A full /api/trades-shaped payload carrying one queued target book."""
    target = {"portfolio": "autonomous", "status": "queued", "rows": rows}
    target.update(target_fields)
    return {"pending_target": target}


# ── 3./4./5. helper contract in node ───────────────────────────────────────────


@requires_node
def test_only_a_queued_target_produces_a_change(tmp_path):
    exit_rows = [{"ticker": "MU", "action": "exit", "target_weight": 0.0, "status": "queued"}]
    results = _run_helper(
        tmp_path,
        [
            {"name": "invalid", "ticker": "MU", "trades": {"pending_target": {
                "status": "invalid", "rows": exit_rows}}},
            {"name": "unavailable", "ticker": "MU", "trades": {"pending_target": {
                "status": "unavailable", "rows": exit_rows}}},
            {"name": "none", "ticker": "MU", "trades": {"pending_target": {
                "status": "none", "rows": exit_rows}}},
            {"name": "queued_upper", "ticker": "MU", "trades": {"pending_target": {
                "status": "QUEUED", "rows": exit_rows}}},
            {"name": "no_status", "ticker": "MU", "trades": {"pending_target": {"rows": exit_rows}}},
            {"name": "pending_target_missing", "ticker": "MU", "trades": {}},
            {"name": "pending_target_null", "ticker": "MU",
             "trades": {"pending_target": None}},
            {"name": "pending_target_scalar", "ticker": "MU",
             "trades": {"pending_target": "queued"}},
            {"name": "no_rows", "ticker": "MU",
             "trades": {"pending_target": {"status": "queued"}}},
            {"name": "empty_rows", "ticker": "MU", "trades": {"pending_target": {
                "status": "queued", "rows": []}}},
            {"name": "trades_null", "ticker": "MU", "tradesLiteral": "null"},
            {"name": "trades_undefined", "ticker": "MU", "tradesLiteral": "undefined"},
            {"name": "ticker_empty", "ticker": "", "trades": {"pending_target": {
                "status": "queued", "rows": exit_rows}}},
            {"name": "control_queued", "ticker": "MU", "trades": {"pending_target": {
                "status": "queued", "rows": exit_rows}}},
        ],
    )

    for name in ("invalid", "unavailable", "none", "no_status", "pending_target_missing",
                 "pending_target_null", "pending_target_scalar", "no_rows", "empty_rows",
                 "trades_null", "trades_undefined", "ticker_empty"):
        assert "error" not in results[name], f"{name} raised: {results[name].get('error')}"
        assert results[name]["result"] is None, f"{name} must not present a queued change"

    control = results["control_queued"]
    assert control["result"]["kind"] == "exit"
    assert control["mutated"] is False
    # Status matching is case-insensitive, exactly like the rest of this file's verdicts.
    assert results["queued_upper"]["result"]["kind"] == "exit"


@requires_node
def test_kind_mapping_is_classified_and_case_insensitive(tmp_path):
    def row(action):
        return [{"ticker": "MU", "action": action, "target_weight": 0.0, "status": "queued"}]

    cases = [
        {"name": "exit", "ticker": "MU", "trades": _queued(row("exit"))},
        {"name": "exit_upper", "ticker": "MU", "trades": _queued(row("EXIT"))},
        {"name": "trim", "ticker": "MU", "trades": _queued(row("trim"))},
        {"name": "add", "ticker": "MU", "trades": _queued(row("add"))},
        {"name": "comparison_unavailable", "ticker": "MU",
         "trades": _queued(row("comparison_unavailable"))},
        {"name": "unpriceable", "ticker": "MU", "trades": _queued(row("unpriceable"))},
        {"name": "hold", "ticker": "MU", "trades": _queued(row("hold"))},
        {"name": "blocked", "ticker": "MU", "trades": _queued(row("blocked"))},
        {"name": "buy", "ticker": "MU", "trades": _queued(row("buy"))},
        {"name": "filtered", "ticker": "MU", "trades": _queued(row("filtered"))},
        {"name": "unknown", "ticker": "MU", "trades": _queued(row("reduce_to_zero"))},
        {"name": "ticker_case", "ticker": "mu", "trades": _queued(row("exit"))},
        {"name": "ticker_case_row", "ticker": "MU",
         "trades": _queued([{"ticker": "mu", "action": "exit", "target_weight": 0.0}])},
        {"name": "other_ticker", "ticker": "XOM", "trades": _queued(row("exit"))},
        {"name": "first_match_wins", "ticker": "MU", "trades": _queued([
            {"ticker": "XOM", "action": "trim", "target_weight": 0.1},
            {"ticker": "MU", "action": "exit", "target_weight": 0.0},
        ])},
    ]
    results = _run_helper(tmp_path, cases)

    assert results["exit"]["result"]["kind"] == "exit"
    assert results["exit_upper"]["result"]["kind"] == "exit"
    assert results["trim"]["result"]["kind"] == "trim"
    assert results["add"]["result"]["kind"] == "add"
    # A target queued for a held name with no classified direction never guesses one.
    for name in ("comparison_unavailable", "unpriceable"):
        assert results[name]["result"]["kind"] == "unclassified"
        assert results[name]["result"]["action"] == name
    for name in ("hold", "blocked", "buy", "filtered", "unknown", "other_ticker"):
        assert results[name]["result"] is None, f"{name} is not a change to a held lot"
    assert results["ticker_case"]["result"]["kind"] == "exit"
    assert results["ticker_case_row"]["result"]["kind"] == "exit"
    assert results["first_match_wins"]["result"]["action"] == "exit"


@requires_node
def test_row_fields_fall_back_to_the_target_and_the_helper_is_pure(tmp_path):
    trades = _queued([
        {"ticker": "MU", "action": "exit", "target_weight": 0.0, "status": "queued"},
        {"ticker": "XOM", "action": "trim", "target_weight": 0.12,
         "current_weight": 0.2, "fill_after": "2026-10-23T09:30:00-04:00",
         "queued_at": "2026-10-22T19:00:00+00:00"},
    ], fill_after="2026-10-23T09:30:00-04:00", queued_at="2026-10-22T20:05:11+00:00")
    results = _run_helper(
        tmp_path,
        [{"name": "fallback", "ticker": "MU", "trades": trades}],
    )

    entry = results["fallback"]
    assert "error" not in entry, entry.get("error")
    assert entry["mutated"] is False, "the helper must not rewrite the trades it was handed"
    assert entry["result"] == {
        "kind": "exit",
        "action": "exit",
        "targetWeight": 0.0,
        "currentWeight": None,
        "fillAfter": "2026-10-23T09:30:00-04:00",
        "queuedAt": "2026-10-22T20:05:11+00:00",
    }

    # Row values win; absent/invalid numerics normalize to null rather than leaking NaN.
    results = _run_helper(
        tmp_path,
        [
            {"name": "row_wins", "ticker": "XOM", "trades": trades},
            {"name": "bad_numbers", "ticker": "CVX", "trades": _queued([
                {"ticker": "CVX", "action": "trim", "target_weight": "0.1",
                 "current_weight": None}], fill_after="   ", queued_at="")},
        ],
    )
    assert results["row_wins"]["result"] == {
        "kind": "trim",
        "action": "trim",
        "targetWeight": 0.12,
        "currentWeight": 0.2,
        "fillAfter": "2026-10-23T09:30:00-04:00",
        "queuedAt": "2026-10-22T19:00:00+00:00",
    }
    assert results["bad_numbers"]["result"] == {
        "kind": "trim",
        "action": "trim",
        "targetWeight": None,
        "currentWeight": None,
        "fillAfter": None,
        "queuedAt": None,
    }


# ── 2. the API projection and the renderer must agree ──────────────────────────


@pytest.fixture
def trades_env(monkeypatch):
    """Local, deterministic /api/trades fixture in the failure shape: MU held, MU excluded by the
    queued target. All quantities are synthetic round numbers (this repository is public)."""
    from app import web
    from portfolio import market_calendar, paper_account, position_log, trade_history

    state: dict = {
        "account": {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 700000.0,
            "positions": {
                "MU": {"shares": 30.0, "avg_cost": 1000.0},
                "XOM": {"shares": 900.0, "avg_cost": 150.0},
            },
        },
        "prices": {"MU": 900.0, "XOM": 180.0},
        "target": None,
        "target_exists": False,
        "legacy": [],
    }
    monkeypatch.setattr(web, "_account_tickers", lambda portfolio_id=None: list(
        state["account"]["positions"]
    ))
    monkeypatch.setattr(web, "_live_prices", lambda tickers, refresh=None: dict(state["prices"]))
    monkeypatch.setattr(web, "_attach_security_names", lambda rows: None)
    monkeypatch.setattr(
        trade_history, "history", lambda prices, portfolio_id=None, account_state=None: []
    )
    monkeypatch.setattr(position_log, "open_positions", lambda portfolio_id=None: [])
    monkeypatch.setattr(position_log, "closed_positions", lambda portfolio_id=None: [])
    monkeypatch.setattr(
        paper_account, "load_pending", lambda portfolio_id=None: list(state["legacy"])
    )
    monkeypatch.setattr(
        paper_account, "load_pending_target", lambda portfolio_id=None: state["target"]
    )
    monkeypatch.setattr(
        paper_account, "pending_target_file_exists",
        lambda portfolio_id=None: bool(state["target_exists"]),
    )
    monkeypatch.setattr(
        paper_account, "_load_account_file",
        lambda portfolio_id=None, strict=False: state["account"],
    )
    monkeypatch.setattr(
        paper_account, "_transaction_path",
        lambda portfolio_id=None: type("NoWal", (), {"exists": lambda self: False})(),
    )
    monkeypatch.setattr(market_calendar, "status", lambda: {
        "open": False,
        "asof_et": "2026-10-22T16:05:11-04:00",
        "next_open": NEXT_OPEN,
        "next_open_day": "2026-10-23",
    })
    return state


def _current_xom_weight() -> float:
    """XOM's live weight, rounded to 4dp — the target that makes it a carry, not a trade."""
    nav = 700000.0 + 30.0 * 900.0 + 900.0 * 180.0
    return round((900.0 * 180.0) / nav, 4)


@requires_node
def test_queued_mu_exit_is_a_pending_change_while_mu_is_still_held(tmp_path, trades_env):
    from app import web

    trades_env["target"] = {
        "schema_version": "pending_target.v2",
        "engine_version": "us_brain_v2",
        "portfolio_id": "autonomous",
        # The accepted full target book excludes MU and pins XOM at its own current weight.
        "target": {"XOM": _current_xom_weight()},
        "asof": "2026-10-22",
        "queued_at": "2026-10-22T20:05:11+00:00",
    }
    trades_env["target_exists"] = True

    response = web.api_trades("autonomous")
    assert response.status_code == 200
    data = json.loads(response.body)

    target = data["pending_target"]
    assert target["status"] == "queued"
    assert target["fill_after"] == NEXT_OPEN
    actions = {row["ticker"]: row["action"] for row in target["rows"]}
    assert actions == {"MU": "exit", "XOM": "hold"}, actions

    # The renderer must read exactly this payload, not a re-derived or reshaped copy.
    results = _run_helper(tmp_path, [
        {"name": "MU", "ticker": "MU", "trades": data},
        {"name": "XOM", "ticker": "XOM", "trades": data},
        {"name": "AAPL", "ticker": "AAPL", "trades": data},
    ])

    mu = results["MU"]
    assert "error" not in mu, mu.get("error")
    assert mu["mutated"] is False
    assert mu["result"]["kind"] == "exit"
    assert mu["result"]["fillAfter"] == NEXT_OPEN
    assert mu["result"]["queuedAt"] == "2026-10-22T20:05:11+00:00"
    assert mu["result"]["targetWeight"] == 0.0
    assert mu["result"]["currentWeight"] is not None

    # XOM is carried inside the no-trade band and AAPL is not in the book at all: neither is a
    # pending change, so both keep today's rendering untouched.
    assert results["XOM"]["result"] is None
    assert results["AAPL"]["result"] is None


@requires_node
def test_without_a_queue_every_held_row_keeps_its_current_rendering(tmp_path, trades_env):
    from app import web

    trades_env["target"] = None
    trades_env["target_exists"] = False

    data = json.loads(web.api_trades("autonomous").body)

    assert data["pending_target"]["status"] == "none"
    assert data["pending_target"]["rows"] == []

    # No queue means no queued change: every held row renders exactly as it does today.
    results = _run_helper(tmp_path, [
        {"name": "MU", "ticker": "MU", "trades": data},
        {"name": "XOM", "ticker": "XOM", "trades": data},
    ])
    assert results["MU"]["result"] is None
    assert results["XOM"]["result"] is None