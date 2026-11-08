"""Keep signed dollar P&L readable in the actual served Portfolio Desk.

Repository CI already installs app/mastermind_os's JSDOM dependency. Execute
all inline page scripts against fixture-only read responses; no ledger action,
account, network, or browser is used.
"""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const [source, packageRoot, locale, input] = process.argv.slice(1);
const {JSDOM, VirtualConsole} = createRequire(path.join(packageRoot, 'package.json'))('jsdom');
const problems = [];
const console = new VirtualConsole();
console.on('jsdomError', error => {
  // JSDOM has no layout engine and does not implement all production CSS.
  if (error.type !== 'css parsing') problems.push(String(error));
});
const dom = new JSDOM(fs.readFileSync(source, 'utf8'), {
  url: 'https://portfolio-fixture.invalid/portfolio_desk',
  runScripts: 'outside-only', virtualConsole: console,
});
const w = dom.window, doc = w.document;
const payloads = JSON.parse(input);
const calls = [];
let refresh;
w.setInterval = (callback, interval) => {
  assert.equal(interval, 60000);
  refresh = callback;
  return 1;
};
w.fetch = async (url, options) => {
  assert.equal(url, '/api/pfolio/positions');
  assert.equal(options.method, undefined, 'Only existing GET reads may occur');
  assert.equal(options.credentials, 'same-origin');
  calls.push(url);
  assert.ok(payloads.length, 'No unexpected extra read');
  return {ok: true, json: async () => payloads.shift()};
};
const format = w.Number.prototype.toLocaleString;
w.Number.prototype.toLocaleString = function(requestedLocale, options) {
  assert.equal(requestedLocale, undefined, 'Keep the existing user-default locale policy');
  return format.call(this, locale, options);
};
const get = selector => {
  const element = doc.querySelector(selector);
  assert.ok(element, `Missing rendered element: ${selector}`);
  return element;
};
const snapshot = () => ({
  day: get('#strip-day-pnl').textContent,
  total: get('#strip-total-pnl').textContent,
  position: get('#pos-tbody tr[data-id] td:nth-child(6)').textContent,
  value: get('#strip-value').textContent,
  shares: get('#pos-tbody tr[data-id] td:nth-child(2)').textContent,
  last: get('#pos-tbody tr[data-id] td:nth-child(4)').textContent,
  dayPct: get('#pos-tbody tr[data-id] td:nth-child(5)').textContent,
  pnlPct: get('#pos-tbody tr[data-id] td:nth-child(7)').textContent,
});
(async () => {
  for (const script of doc.querySelectorAll('script:not([src])')) w.eval(script.textContent);
  await new Promise(setImmediate);
  const states = [snapshot()];
  while (payloads.length) {
    refresh();
    await new Promise(setImmediate);
    states.push(snapshot());
  }
  assert.deepEqual(problems, []);
  process.stdout.write(JSON.stringify({states, requests: calls.length}));
})().catch(error => { process.stderr.write(error.stack); process.exitCode = 1; })
  .finally(() => w.close());
"""


def _payload(value, *, omit=False):
    position = {
        "id": "fixture", "ticker": "FIXTURE", "shares": 10.125,
        "entry_price": 125, "last": 100, "market_value": 1012.5,
        "day_change_pct": -2.5, "pnl_pct": -20,
    }
    payload = {"ok": True, "total_value": 1012.5, "positions": [position]}
    if not omit:
        payload.update(day_pnl=value, total_pnl_usd=value)
        position["pnl_usd"] = value
    return payload


def _render(payloads, locale):
    result = subprocess.run(
        ["node", "-e", SCRIPT, str(ROOT / "app/static/portfolio.html"),
         str(ROOT / "app/mastermind_os"), locale, json.dumps(payloads)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


CASES = [
    pytest.param((-1234.56, "-$1,234.56", "-$1.234,56", False), id="negative"),
    pytest.param((-0.01, "-$0.01", "-$0,01", False), id="negative-cent"),
    pytest.param((-0.004, "-$0.00", "-$0,00", False), id="negative-below-cent"),
    pytest.param((-12.3456, "-$12.35", "-$12,35", False), id="negative-rounded"),
    pytest.param(("-1234.56", "-$1,234.56", "-$1.234,56", False), id="negative-string"),
    pytest.param((1234.56, "+$1,234.56", "+$1.234,56", False), id="positive"),
    pytest.param((0, "+$0.00", "+$0,00", False), id="zero"),
    pytest.param(("0", "+$0.00", "+$0,00", False), id="zero-string"),
    pytest.param((None, "—", "—", False), id="null"),
    pytest.param((None, "—", "—", True), id="missing"),
    pytest.param(("not-a-number", "—", "—", False), id="invalid"),
    pytest.param(("", "—", "—", False), id="empty"),
    pytest.param(("NaN", "—", "—", False), id="nan"),
    pytest.param(("Infinity", "—", "—", False), id="positive-infinity"),
    pytest.param(("-Infinity", "—", "—", False), id="negative-infinity"),
]


@pytest.fixture(scope="module", params=["en-US", "de-DE"])
def locale(request):
    return request.param


@pytest.fixture(scope="module", params=CASES)
def displayed(request, locale):
    value, en, de, omit = request.param
    result = _render([_payload(value, omit=omit)], locale)
    assert result["requests"] == 1
    return result["states"][0], en if locale == "en-US" else de


@pytest.mark.parametrize("caller", ["day", "total", "position"])
def test_all_signed_dollar_callers_preserve_value_sign(displayed, caller):
    state, expected = displayed
    assert state[caller] == expected


def test_refresh_changes_sign_without_changing_other_columns(locale):
    result = _render([_payload(-1234.56), _payload(1234.56), _payload(0), _payload(None)], locale)
    expected = ["-$1,234.56", "+$1,234.56", "+$0.00", "—"] if locale == "en-US" else [
        "-$1.234,56", "+$1.234,56", "+$0,00", "—"]
    assert result["requests"] == 4
    for state, amount in zip(result["states"], expected):
        for caller in ("day", "total", "position"):
            assert state[caller] == amount
        assert state["value"] == ("$1,012.50" if locale == "en-US" else "$1.012,50")
        assert state["shares"] == ("10.125" if locale == "en-US" else "10,125")
        assert state["last"] == "$100.00"
        assert state["dayPct"] == "-2.50%"
        assert state["pnlPct"] == "-20.00%"


def test_actual_totals_producer_loss_reaches_page(locale):
    from app.pfolio import _portfolio_totals

    payload = _payload(-250)
    position = payload["positions"][0]
    position.update(shares=10, market_value=1000, last=100, day_change_pct=-20)
    payload.update(_portfolio_totals(payload["positions"]))
    assert payload["day_pnl"] == payload["total_pnl_usd"] == -250
    state = _render([payload], locale)["states"][0]
    expected = "-$250.00" if locale == "en-US" else "-$250,00"
    assert (state["day"], state["total"], state["position"]) == (expected,) * 3
