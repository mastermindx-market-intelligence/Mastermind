"""Per-TRADE reasoning for the daily decision log — why each add / trim / exit happened.

THE GAP THIS CLOSES
-------------------
Every free-form Brain book (``autonomous``, ``etf``, ``china``, ``hk``) submits a COMPLETE target
book once a day. The desk then rebalances the paper account to those weights, so the actual trades
are an IMPLICIT diff: a name whose weight rose was bought, a name omitted was sold in full. The
decision log recorded the book-level ``summary``, an optional free-text ``sold_note``, and a
per-HOLDING ``rationale`` (why we own it) — but nothing per TRADE. So the log could say "we own
600519.SS because …" and never say "we bought 1,900 more shares today because …", and an EXIT left
no trace at all beyond one optional sentence covering every sell at once. Reading the log, you can
see WHAT changed but not WHY it changed.

WHAT THIS MODULE PROVIDES
-------------------------
  * ``TRADES_SCHEMA_PROPERTY`` / ``TOOL_HINT`` — the shared ``trades`` input-schema fragment and the
    tool-description text, so all four ``submit_book`` tools ask for the same thing in the same
    shape (and a fifth book can adopt it without a new contract).
  * ``normalize(raw)`` — defensive cleaning of what the Brain submitted.
  * ``reconcile(stated, executed, ...)`` — the load-bearing one. It emits ONE row per trade that
    ACTUALLY EXECUTED, derived from the fill diff, and joins the Brain's stated reason onto it.

WHY RECONCILE AGAINST THE FILLS, NOT THE NARRATIVE (the load-bearing invariant)
------------------------------------------------------------------------------
If the log simply stored what the Brain *said* it did, it would inherit the failure it exists to
fix: an unmentioned sell stays invisible, and a claimed trade that never filled reads as real. So
the row set is driven by ``executed`` (the real before/after share diff from ``bot/settle.py``
``_diff_trades``) and the Brain's prose is joined ON to it. A trade the Brain did not explain is
still logged, carrying ``explained: False`` — the absence becomes VISIBLE and gradable instead of
silently absent. We never fabricate a reason for it.

The ``action`` is likewise DERIVED, not taken on trust: a buy in a name we did not hold is a
``new_buy``, a buy in a name we held is an ``add``, a sell that leaves nothing is an ``exit``, a
sell that leaves a position is a ``trim``. The Brain can mislabel its own intent; the fills cannot.

FAIL-SOFT: every public function returns a usable default ([] / {}) on malformed input and NEVER
raises — this decorates the decision log and must never block a book from publishing.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Actions the Brain may DECLARE. The persisted `action` is derived from the fills (see `reconcile`);
# a declared action is kept alongside as `stated_action` so a mismatch is auditable rather than lost.
ACTIONS = ("new_buy", "add", "trim", "exit", "hold")

_MAX_REASON_CHARS = 1200          # generous: this is the field the operator actually reads
_MAX_ROWS = 60                    # a book never trades this many names in a day; bounds a bad emit


# --------------------------------------------------------------------------- #
# the shared tool contract
# --------------------------------------------------------------------------- #

TRADES_SCHEMA_PROPERTY: dict[str, Any] = {
    "type": "array",
    "description": (
        "REQUIRED WHEN YOU CHANGE THE BOOK. One entry for EVERY position you are opening, adding "
        "to, trimming, or exiting today versus the book you are currently holding — including every "
        "name you are dropping (a name you omit from `holdings` is SOLD IN FULL). This is the "
        "operator-facing record of WHY the book moved today; the per-holding `rationale` says why "
        "you own a name, this says why you TRADED it now."
    ),
    "items": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "action": {"type": "string", "enum": list(ACTIONS),
                       "description": "new_buy = open a position you did not hold; add = increase an "
                                      "existing one; trim = reduce but keep; exit = sell in full"},
            "reason": {
                "type": "string",
                "description": (
                    "The specific, falsifiable reason you are making THIS trade TODAY — 2-5 "
                    "sentences. Name the concrete thing that CHANGED and made you act now (a "
                    "print, a price level reclaimed or lost, a policy move, a sector rotating, a "
                    "thesis milestone hit or missed). Say what you expect to happen next and what "
                    "would prove you wrong. Do NOT write generic filler like 'rebalancing', "
                    "'taking profits', 'risk management', or 'reducing exposure' — those describe "
                    "the mechanics, not the reason. If you are EXITING, state whether the thesis "
                    "broke, the thesis completed, or you were wrong — those are different outcomes "
                    "and you are graded on telling them apart."
                ),
            },
            "thesis_change": {
                "type": "string",
                "description": "Optional: what you now believe that you did not believe yesterday. "
                               "Leave empty when the thesis is unchanged and only size moved.",
            },
        },
        "required": ["ticker", "action", "reason"],
    },
}

# Appended to each book's submit_book tool description so the requirement is stated where the Brain
# reads it, not only in the JSON schema.
TOOL_HINT = (
    " TRADE REASONING (required whenever today's book differs from what you currently hold): pass "
    "`trades` — one entry per position you open, add to, trim, or EXIT, each with a specific reason "
    "for acting TODAY. Every name you drop from `holdings` is sold in full and needs an exit reason. "
    "This is what the operator reads to understand the day's decisions; a book that moves without "
    "trade reasons is logged as UNEXPLAINED."
)


# --------------------------------------------------------------------------- #
# shared seat doctrine — appended to each free-form book's daily prompt
# --------------------------------------------------------------------------- #

# Two rules that apply to EVERY book that trades by submitting a complete target book, kept here so
# the four seats state them identically. (The China seat additionally carries book-specific sizing
# and cash doctrine inline in bot/china.py.)
#
# Rule 1 exists because these books express a sell as an OMISSION from `holdings`, which makes it
# far too easy to drop a name for a reason that belongs to a screen rather than to the position —
# the in-house boards are DISCOVERY surfaces, they are volatile, and a working trade frequently
# stops being surfaced precisely because it is no longer a fresh setup.
# Rule 2 exists because an omission also leaves no written trace: without a per-trade reason, a full
# exit is indistinguishable in the log from a name that was never considered.
BOOK_DOCTRINE_BLOCK = """
## Decision discipline

**Sell for a reason that belongs to the position.** Exit when the thesis breaks, when your
invalidation level trades, when the thesis has played out, or when the capital has a clearly better
use. A name disappearing from one of the in-house boards or screens is NOT a sell signal — those are
discovery tools, they are volatile, they are still being improved, and a name commonly stops being
surfaced precisely because the trade is already working. If a name you hold is no longer surfaced,
judge it on its own chart and thesis before you act. Never sell a winner merely because the desk
stopped mentioning it.

**Explain every trade.** Pass `trades` to submit_book: one entry for each name you open, add to,
trim, or exit, naming the specific thing that CHANGED and made you act today. Any name you omit from
`holdings` is sold in full and needs an exit reason. This is the record the operator reads to
understand the day — "rebalancing", "trimming risk", and "taking profits" explain nothing. Say what
you now believe that you did not believe yesterday, and whether an exit means the thesis broke, the
thesis completed, or you were wrong.
""".strip()


# --------------------------------------------------------------------------- #
# normalization
# --------------------------------------------------------------------------- #

def _clean_str(v: Any, cap: int) -> str:
    if not isinstance(v, str):
        return ""
    return v.strip()[:cap]


def normalize(raw: Any) -> list[dict]:
    """Clean the Brain-submitted ``trades`` array into stable rows. Never raises.

    Drops rows without a ticker or without a reason (a reasonless row carries no information and
    would otherwise dilute the `explained` coverage metric). Deduped by ticker, first row wins.
    """
    out: list[dict] = []
    try:
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        for row in raw[:_MAX_ROWS]:
            if not isinstance(row, dict):
                continue
            t = _clean_str(row.get("ticker"), 16).upper()
            reason = _clean_str(row.get("reason"), _MAX_REASON_CHARS)
            if not t or t in seen or not reason:
                continue
            action = _clean_str(row.get("action"), 16).lower()
            seen.add(t)
            rec = {"ticker": t, "reason": reason,
                   "stated_action": action if action in ACTIONS else None}
            tc = _clean_str(row.get("thesis_change"), _MAX_REASON_CHARS)
            if tc:
                rec["thesis_change"] = tc
            out.append(rec)
        return out
    except Exception as e:  # noqa: BLE001 — decorative; never raise into a book publish
        log.debug("trade_rationale.normalize failed (%s)", e)
        return []


# --------------------------------------------------------------------------- #
# reconciliation against the real fills
# --------------------------------------------------------------------------- #

def _derive_action(side: str, ticker: str, prior_held: set[str], still_held: set[str]) -> str:
    """Classify a filled trade from the position transition. `side` is 'buy' or 'sell'."""
    if side == "buy":
        return "add" if ticker in prior_held else "new_buy"
    return "trim" if ticker in still_held else "exit"


def reconcile(stated: Any, executed: Any, *,
              prior_positions: Any = None,
              target_holdings: Any = None) -> list[dict]:
    """Join the Brain's stated trade reasons onto the trades that ACTUALLY filled.

    Args:
      stated:           the raw ``trades`` array from the submission (normalized here).
      executed:         the real fill rows from ``bot/settle._diff_trades`` —
                        ``[{ticker, side, shares, price, value}, ...]``.
      prior_positions:  tickers held BEFORE today's rebalance (dict keyed by ticker, or an
                        iterable of tickers). Distinguishes ``new_buy`` from ``add``.
      target_holdings:  today's submitted holdings (list of dicts with ``ticker``, or an iterable
                        of tickers). Distinguishes ``trim`` from ``exit``.

    Returns one row per executed trade::

        {ticker, action, side, shares, price, value, reason, stated_action, explained,
         thesis_change?, action_mismatch?}

    ``explained`` is False when the Brain traded a name it gave no reason for — logged, not hidden.
    Returns [] on malformed input; never raises.
    """
    try:
        by_ticker = {r["ticker"]: r for r in normalize(stated)}
        prior_held = _ticker_set(prior_positions)
        still_held = _ticker_set(target_holdings)

        rows: list[dict] = []
        for ex in (executed if isinstance(executed, list) else []):
            if not isinstance(ex, dict):
                continue
            t = _clean_str(ex.get("ticker"), 16).upper()
            if not t:
                continue
            side = _clean_str(ex.get("side"), 8).lower()
            if side not in ("buy", "sell"):
                continue
            action = _derive_action(side, t, prior_held, still_held)
            said = by_ticker.get(t) or {}
            row: dict[str, Any] = {
                "ticker": t,
                "action": action,
                "side": side,
                "shares": ex.get("shares"),
                "price": ex.get("price"),
                "value": ex.get("value"),
                "reason": said.get("reason") or None,
                "stated_action": said.get("stated_action"),
                "explained": bool(said.get("reason")),
            }
            if said.get("thesis_change"):
                row["thesis_change"] = said["thesis_change"]
            # The Brain's own label vs what the fills say it did. Surfaced (not corrected silently)
            # because a book that thinks it trimmed while it exited is a real reasoning failure.
            if said.get("stated_action") and said["stated_action"] != action:
                row["action_mismatch"] = True
            rows.append(row)
        return rows
    except Exception as e:  # noqa: BLE001 — decorative; never raise into a book publish
        log.debug("trade_rationale.reconcile failed (%s)", e)
        return []


def _ticker_set(src: Any) -> set[str]:
    """Coerce positions/holdings — dict keyed by ticker, list of dicts, or list of strings — to a
    set of upper-case tickers. Never raises; unknown shapes degrade to an empty set."""
    out: set[str] = set()
    try:
        if isinstance(src, dict):
            return {str(k).upper().strip() for k in src if k}
        for item in (src or []):
            if isinstance(item, dict):
                t = item.get("ticker")
            else:
                t = item
            if t:
                out.add(str(t).upper().strip())
    except Exception:  # noqa: BLE001
        return out
    return out


def coverage(rows: Any) -> dict:
    """Summarize explanation coverage for a reconciled row set: how much of today's turnover the
    Brain actually justified. Cheap enough to store on every decision-log entry, and it makes an
    unexplained book a VISIBLE metric the loop can grade rather than a silent gap. Never raises."""
    try:
        rs = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
        n = len(rs)
        if not n:
            return {"n_trades": 0, "n_explained": 0, "pct_explained": None, "unexplained": []}
        explained = [r for r in rs if r.get("explained")]
        return {
            "n_trades": n,
            "n_explained": len(explained),
            "pct_explained": round(100.0 * len(explained) / n, 1),
            "unexplained": sorted({r.get("ticker") for r in rs
                                   if not r.get("explained") and r.get("ticker")}),
        }
    except Exception:  # noqa: BLE001
        return {"n_trades": 0, "n_explained": 0, "pct_explained": None, "unexplained": []}
