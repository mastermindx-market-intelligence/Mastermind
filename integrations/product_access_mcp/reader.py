"""Stateless projections of existing public product owners. No user session access."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from .contracts import (ENDPOINTS, SCHEMA, HttpObservation, count, finite, revision,
                        strict_json, symbols_checked, time_observation, utc_now)

CHECKS = frozenset({"site", "overlay", "risk_state", "china_risk_state", "quotes", "basket_pulse",
                    "flow_pulse", "release_publications", "orchestrator", "breadth", "terminal_data", "prophet_live"})
COUNTS = ("n", "fresh", "requested", "resolved", "symbols", "n_names", "n_tickers", "with_bars")
PULSE_KEYS = {"schema", "projection", "snapshot_id", "generated_at", "source_owner", "source_view",
              "state", "coverage", "items", "errors"}
ITEM_KEYS = {"symbol", "price", "change_abs", "change_pct", "currency", "session", "freshness",
             "observed_at", "received_at", "published_at", "regular_session_date", "revision"}
COVERAGE_KEYS = {"requested", "resolved", "live", "delayed", "stale", "missing"}


def _health(value: dict, now: datetime) -> dict:
    if set(value) != {"status", "commit", "checkout"} or value["status"] != "ok":
        raise ValueError("health_contract_changed")
    process, checkout = revision(value["commit"]), revision(value["checkout"])
    drift = None
    if process and checkout:
        if process == checkout:
            drift = False
        elif not (process.startswith(checkout) or checkout.startswith(process)):
            drift = True
        # A matching abbreviation and a longer revision cannot prove identity or drift.
    return {"reported_status": "ok", "process_revision": process, "checkout_revision": checkout,
            "checkout_drift": drift, "exact_deployment_verified": False}


def _status(value: dict, now: datetime) -> dict:
    if not {"status", "commit", "checks"} <= value.keys() or type(value["checks"]) is not dict:
        raise ValueError("status_contract_changed")
    if len(value["checks"]) > 64:
        raise ValueError("status_checks_unbounded")
    checks = {}
    for name, source in value["checks"].items():
        if name not in CHECKS:
            continue
        if type(source) is not dict:
            source = {"status": "invalid"}
        stamp = next((source[k] for k in ("built", "as_of", "commit_time") if k in source), None)
        state = "unavailable" if "error" in source else source.get("status", "observed")
        if state not in {"missing", "unavailable", "invalid", "ok", "observed", "stale", "partial"}:
            state = "unknown"
        checks[name] = {"state": state, "source_time": time_observation(stamp, now),
                        "file_age_minutes": finite(source.get("age_min"), nonnegative=True),
                        "commit": revision(source.get("commit")),
                        "counts": {k: count(source.get(k)) for k in COUNTS}}
    return {"reported_status": "ok" if value["status"] == "ok" else "unknown",
            "process_revision": revision(value["commit"]), "checks": checks,
            "omitted_check_count": len(value["checks"]) - len(checks),
            "freshness_policy": "unknown; source timestamps and file age are observations, not currentness proof"}


def _pulse(value: dict, now: datetime, symbols: tuple[str, ...]) -> dict:
    if (set(value) != PULSE_KEYS or value["schema"] != "intelligence_hub.market_pulse.v1"
            or value["projection"] != "intelligence_hub.market_pulse"
            or value["source_owner"] != "terminal-market-data" or value["source_view"] != "regular"
            or revision(value["snapshot_id"], 16, 16) is None):
        raise ValueError("quote_contract_changed")
    coverage, items, errors, state = (value[k] for k in ("coverage", "items", "errors", "state"))
    if (type(coverage) is not dict or set(coverage) != COVERAGE_KEYS
            or any(count(coverage[k]) is None for k in COVERAGE_KEYS)
            or type(items) is not list or type(errors) is not list
            or len(items) > len(symbols) or len(errors) > len(symbols)
            or type(state) is not dict or set(state) != {"availability", "freshness", "session", "coverage"}):
        raise ValueError("invalid_coverage")
    if (coverage["requested"] != len(symbols) or coverage["resolved"] != len(items)
            or coverage["missing"] != len(errors) or len(items) + len(errors) != len(symbols)
            or sum(coverage[k] for k in ("live", "delayed", "stale")) != len(items)
            or state["coverage"] != ("partial" if errors else "complete")
            or state["availability"] != ("available" if items else "unavailable")
            or state["freshness"] not in {"live", "delayed", "stale"}
            or state["session"] not in {"regular", "closed", "mixed"}):
        raise ValueError("inconsistent_coverage")
    projected = []
    seen: set[str] = set()
    fresh_counts = {k: 0 for k in ("live", "delayed", "stale")}
    generated = time_observation(value["generated_at"], now)
    for row in items:
        if type(row) is not dict or set(row) != ITEM_KEYS:
            raise ValueError("unexpected_quote_fields")
        symbol = row["symbol"]
        if type(symbol) is not str or symbol not in symbols or symbol in seen:
            raise ValueError("unexpected_symbol")
        seen.add(symbol)
        price = finite(row["price"])
        if (price is None or price <= 0 or row["freshness"] not in fresh_counts
                or row["session"] not in {"regular", "closed"}
                or revision(row["revision"], 16, 16) is None):
            raise ValueError("invalid_quote")
        for key in ("change_abs", "change_pct"):
            if row[key] is not None and finite(row[key]) is None:
                raise ValueError("invalid_quote_number")
        currency = row["currency"]
        if currency is not None and (type(currency) is not str or len(currency) != 3 or not currency.isascii()
                                     or not currency.isalpha() or not currency.isupper()):
            raise ValueError("invalid_currency")
        day = row["regular_session_date"]
        if day is not None:
            if type(day) is not str or len(day) != 10:
                raise ValueError("invalid_session_date")
            datetime.strptime(day, "%Y-%m-%d")
        fresh_counts[row["freshness"]] += 1
        times = {k: time_observation(row[k], now) for k in ("observed_at", "received_at", "published_at")}
        projected.append({"symbol": symbol, "price": price, "change_abs": row["change_abs"],
                          "change_pct": row["change_pct"], "currency": currency, "session": row["session"],
                          "owner_freshness": row["freshness"], "regular_session_date": day,
                          "revision": row["revision"], **times,
                          "timestamp_qualified": all(x["status"] == "observed" for x in
                                                     (generated, times["observed_at"], times["published_at"]))})
    for row in errors:
        if (type(row) is not dict or set(row) != {"symbol", "code"}
                or type(row["symbol"]) is not str or row["symbol"] not in symbols
                or row["symbol"] in seen or row["code"] != "quote_unavailable"):
            raise ValueError("invalid_quote_error")
        seen.add(row["symbol"])
    if seen != set(symbols) or any(coverage[k] != fresh_counts[k] for k in fresh_counts):
        raise ValueError("inconsistent_items")
    expected_freshness = "stale" if fresh_counts["stale"] or not items else "delayed" if fresh_counts["delayed"] else "live"
    sessions = {r["session"] for r in items}
    expected_session = next(iter(sessions)) if len(sessions) == 1 else "mixed"
    if state["freshness"] != expected_freshness or state["session"] != expected_session:
        raise ValueError("inconsistent_state")
    return {"snapshot_id": value["snapshot_id"], "generated_at": generated,
            "owner_state": dict(state), "coverage": dict(coverage), "items": projected,
            "errors": [dict(r) for r in errors], "source_view": "regular"}


class ProductReader:
    """Trusted transport port gets only fixed endpoint identifiers, never MCP identity."""

    def __init__(self, *, transport: object, now: Callable[[], datetime]):
        if not callable(getattr(transport, "read", None)) or not callable(now):
            raise TypeError("explicit public transport and observation clock required")
        self._transport, self._now = transport, now

    async def _observe(self, endpoint: str, symbols: tuple[str, ...] = ()) -> dict[str, Any]:
        try:
            response = await self._transport.read(endpoint, symbols=symbols)
        except Exception:
            response = HttpObservation(status=None, error="backend_unavailable")
        now = utc_now(self._now())
        result: dict[str, Any] = {"endpoint": endpoint, "url": ENDPOINTS[endpoint],
            "source_owner": "terminal-market-data" if endpoint == "market_pulse" else "macro-api",
            "environment": "production", "access_class": "public", "observed_at": now.isoformat(),
            "http_status": None, "sha256": None, "state": "unavailable", "data": None}
        if not isinstance(response, HttpObservation):
            result["state"] = "invalid"
            return result
        result["http_status"] = response.status if type(response.status) is int and 100 <= response.status <= 599 else None
        if response.status in (401, 403):
            result["state"] = "unauthorized"
            return result
        if response.status == 404:
            result["state"] = "missing"
            return result
        if response.error or response.status != 200:
            return result
        try:
            if not isinstance(response.content_type, str) or response.content_type.split(";")[0].strip().lower() != "application/json":
                raise ValueError("invalid_content_type")
            value = strict_json(response.body)
            data = _pulse(value, now, symbols) if endpoint == "market_pulse" else _health(value, now) if endpoint == "health" else _status(value, now)
            result.update(data=data, state="observed", sha256=hashlib.sha256(response.body).hexdigest())
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            result["state"] = "invalid"
        return result

    @staticmethod
    def _envelope(tool: str, observations: list[dict]) -> dict:
        return {"schema": SCHEMA, "tool": tool, "observations": observations,
                "limitations": ["public observations only; not a product-user session",
                                "source-reported freshness is not recomputed or guaranteed current",
                                "exact deployment and preview revisions are not verified"]}

    async def diagnostics(self) -> dict:
        # Serial fixed reads avoid an extra fanout policy or alternate retry owner.
        return self._envelope("product_diagnostics", [await self._observe("health"), await self._observe("status")])

    async def market_pulse(self, symbols: object) -> dict:
        selected = symbols_checked(symbols)
        return self._envelope("product_market_pulse", [await self._observe("market_pulse", selected)])
