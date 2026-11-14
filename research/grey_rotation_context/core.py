"""Read-only grey-dot rotation context; no event creation or decision authority.

Consumes existing producers. Unknown timestamps, cohort coverage and share-class
choices remain unknown. No oscillator, portfolio policy or persistent store lives here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Integral
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

AUTHORITY = {"may_rank": False, "may_size": False, "may_trade": False,
             "may_change_entry_gate": False}


class ContractError(ValueError):
    """An input identity or clock cannot support this computation."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def instant(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ContractError("an explicit timezone-aware availability instant is required")
    return t.tz_convert("UTC")


def session(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is not None or t != t.normalize():
        raise ContractError("an unambiguous economic-session date is required")
    return t


def calendar_index(values: Sequence) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(values)
    if (idx.empty or idx.hasnans or idx.tz is not None or not idx.is_unique
            or not idx.is_monotonic_increasing or not (idx == idx.normalize()).all()):
        raise ContractError("supply the producer's ordered unique exchange-session calendar")
    return idx


def numerical(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)) or value is None:
        return None
    try:
        x = float(value)
    except (ValueError, TypeError):
        return None
    return x if math.isfinite(x) else None


@dataclass(frozen=True)
class SeriesInput:
    name: str
    values: pd.Series
    receipt_sha256: str
    available_at: pd.Series | None = None

    def validate(self) -> None:
        if len(self.receipt_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.receipt_sha256):
            raise ContractError("source receipt must be bound by a SHA256")
        calendar_index(self.values.index)
        if self.available_at is not None and not self.available_at.index.equals(self.values.index):
            raise ContractError("availability must refer to the same economic observations")


def index_context(source: SeriesInput, sessions: Sequence, origin: str, decision_at: str,
                  *, lag: int = 1, allow_assumed_availability: bool = False) -> dict:
    """Separate implied-risk level, mean trend, acceleration and peak retreat.

    Defaults to one exchange-session lag. Missing observations are never filled.
    Per-row publication times are checked against THIS decision, including all
    lookback inputs. A historical lag assumption is disclosed, not called PIT proof.
    """
    source.validate()
    if source.name not in ("VIX", "VVIX"):
        raise ContractError("VIX or actual options-implied VVIX required; no proxy substitution")
    if not isinstance(lag, int) or isinstance(lag, bool) or lag < 1:
        raise ContractError("at least one completed-session lag is required")
    idx, t, clock = calendar_index(sessions), session(origin), instant(decision_at)
    if t not in idx or clock.date() < t.date():
        raise ContractError("origin/calendar/decision mismatch")
    j = int(idx.get_loc(t)) - lag
    if j < 0:
        return {"status": "UNAVAILABLE", "reason": "no lagged session", "name": source.name,
                "authority": dict(AUTHORITY)}
    used = idx[max(0, j-252):j+1]
    raw = pd.to_numeric(source.values.reindex(used), errors="coerce")
    x = raw.where(np.isfinite(raw) & (raw > 0))
    basis = "publication_checked"
    if source.available_at is None:
        if not allow_assumed_availability:
            return {"status": "UNAVAILABLE", "reason": "publication time absent", "name": source.name,
                    "authority": dict(AUTHORITY)}
        basis = "previous_session_assumption_not_historical_vintage_proof"
    else:
        times = source.available_at.reindex(used)
        known = []
        for value in times:
            try:
                known.append(instant(value) <= clock)
            except (TypeError, ValueError):
                known.append(False)
        x = x.where(np.asarray(known))

    def mean_at(window: int, offset: int = 0) -> float | None:
        z = x.iloc[max(0, len(x)-window-offset):len(x)-offset if offset else None]
        return float(z.mean()) if len(z) == window and z.notna().all() else None

    latest = numerical(x.iloc[-1])
    m5, m20, old20, older20 = mean_at(5), mean_at(20), mean_at(20, 5), mean_at(20, 10)
    ratio = lambda a, b: math.log(a/b) if a is not None and b is not None else None
    slope, old_slope = ratio(m20, old20), ratio(old20, older20)
    prior = x.iloc[-253:-1]
    rank = (float((prior <= latest).mean()) if latest is not None and len(prior) == 252
            and prior.notna().all() else None)
    recent = x.iloc[-10:]
    peak = float(recent.max()) if len(recent) == 10 and recent.notna().all() else None
    peak_age = None
    if peak is not None:
        last_peak = int(np.flatnonzero(recent.to_numpy() == peak)[-1])
        peak_age = 9-last_peak
    return {"status": "OBSERVED" if latest is not None else "UNAVAILABLE", "name": source.name,
            "origin": str(t.date()), "source_session": str(used[-1].date()), "lag_sessions": lag,
            "source_receipt_sha256": source.receipt_sha256, "availability_basis": basis,
            "latest": latest, "mean5": m5, "mean20": m20, "prior252_percentile": rank,
            "log_level_over_mean20": ratio(latest, m20), "log_mean5_over_mean20": ratio(m5, m20),
            "mean20_log_change5": slope,
            "mean20_log_acceleration5": slope-old_slope if slope is not None and old_slope is not None else None,
            "log_retreat_from_peak10": ratio(peak, latest), "peak_age_sessions10": peak_age,
            "missing_or_unavailable_lookback": int(x.isna().sum()), "authority": dict(AUTHORITY)}


def event_context(event: Mapping[str, Any], *, expected_identity: Mapping[str, Any],
                  source_observed_at: str, decision_at: str, decision_session: str,
                  signal_close_at: str | None = None) -> dict:
    """Read an existing G0 EntryEvent; never infer known_ts from its chart label.

    This does not create, deduplicate or repair canonical events. A settled bare
    side-channel dot can remain unqualified for historical timing when its true
    known timestamp is absent. The original event is never mutated.
    """
    now, seen, day = instant(decision_at), instant(source_observed_at), session(decision_session)
    if seen > now:
        raise ContractError("source artifact was observed after the decision")
    if now.date() < day.date():
        raise ContractError("decision precedes economic session")
    identity = event.get("source_identity")
    keys = ("source_hash", "signal_era", "detector_spec_hash")
    if (not isinstance(identity, Mapping) or any(not expected_identity.get(k) for k in keys)
            or any(identity.get(k) != expected_identity[k] for k in keys)):
        raise ContractError("unbound detector/source/era identity")
    if event.get("family") != "grey_dot" or event.get("detector_id") != "G0_GREY_DOT@1":
        raise ContractError("a canonical G0 grey event is required, not a similarly named trigger")
    if not event.get("event_id") or not event.get("ticker"):
        raise ContractError("event identity missing")
    out = {"event_id": event["event_id"], "ticker": event["ticker"],
           "source_identity": dict(identity), "chart_label": event.get("signal_ts"),
           "signal_known_session": event.get("signal_known_ts"),
           "bar_state": event.get("bar_state"), "authority": dict(AUTHORITY)}
    known = event.get("signal_known_ts")
    if known is None:
        return {**out, "status": "TIMING_UNQUALIFIED", "reason": "known_ts absent; chart label is not a substitute"}
    if session(known) > day:
        raise ContractError("signal was not known by the economic decision session")
    if (event.get("field_origin") or {}).get("signal_known_ts") == "artifact_absent":
        raise ContractError("non-null known time contradicts its absent-field provenance")
    if event.get("final") is True:
        if signal_close_at is None and session(known) == day:
            return {**out, "status": "CLOSE_TIME_UNQUALIFIED", "reason": "same-day finality needs the exchange close instant"}
        if signal_close_at is not None:
            close_clock = instant(signal_close_at)
            if (close_clock.tz_convert("America/New_York").date() != session(known).date()
                    or close_clock > now or close_clock > seen):
                raise ContractError("final signal precedes its supplied exchange close")
    if event.get("pre_channel_reconstruction"):
        return {**out, "status": "BACKCAST_ONLY", "reason": "not original historical emission"}
    if event.get("final") is not True:
        return {**out, "status": "PROVISIONAL", "reason": "keep in separate observation cohort"}
    return {**out, "status": "RECORDED_CONTEXT", "reason": "recorded known date and source observation; not execution proof"}


def cohort_snapshot(rows: Sequence[Mapping[str, Any]], *, origin: str, decision_at: str,
                    focal_issuer: str | None = None, representative: Mapping[str, str] | None = None,
                    allow_reconstructed_membership: bool = False, minimum_peers: int = 5) -> dict:
    """Consume member states, not an oscillator; report the full roster denominator.

    All rows belong to one explicitly declared group/vintage. Duplicate share
    classes require the incumbent owner's representative rule. Missing members
    remain in n_expected, and focal-issuer exclusion removes every share class.
    No alphabetical placeholder is promoted into a production identity rule.
    """
    t, clock = session(origin), instant(decision_at)
    if minimum_peers < 1 or clock.date() < t.date():
        raise ContractError("invalid minimum/calendar")
    groups = {(r.get("group_id"), r.get("membership_vintage")) for r in rows}
    if len(groups) != 1 or any(not k for k in next(iter(groups), (None, None))):
        raise ContractError("one source-bound group and membership vintage required")
    grouped: dict[str, list[Mapping]] = {}
    assumed = False
    for r in rows:
        if not r.get("issuer_id") or not r.get("ticker"):
            raise ContractError("canonical issuer identity required")
        if r["issuer_id"] == focal_issuer:
            continue
        start = session(r["start_session"])
        end = session(r["end_session"]) if r.get("end_session") is not None else None
        if end is not None and end <= start:
            raise ContractError("invalid membership interval")
        if not (start <= t and (end is None or t < end)):
            continue
        stamp = r.get("membership_available_at")
        if stamp is None:
            if not allow_reconstructed_membership:
                raise ContractError("historical membership knowability absent")
            assumed = True
        elif instant(stamp) > clock:
            raise ContractError("membership was learned after this decision")
        grouped.setdefault(r["issuer_id"], []).append(r)
    states, absent, unresolved = {}, [], []
    for issuer, choices in grouped.items():
        tickers = [r["ticker"] for r in choices]
        if len(set(tickers)) != len(tickers):
            raise ContractError("duplicate member observations")
        if len(choices) > 1:
            pick = (representative or {}).get(issuer)
            if pick not in tickers:
                unresolved.append(issuer)
                continue
            r = next(r for r in choices if r["ticker"] == pick)
        else:
            r = choices[0]
        valid = (isinstance(r.get("has_close"), (bool, np.bool_)) and bool(r["has_close"])
                 and r.get("observation_session") == str(t.date()))
        if valid:
            try:
                valid = instant(r.get("available_at")) <= clock
            except (ValueError, TypeError):
                valid = False
        d = numerical(r.get("d_known")) if valid else None
        if d is not None and not 0 <= d <= 100:
            raise ContractError("StochRSI D must be on its native 0..100 scale")
        if d is None or not isinstance(r.get("n_bars_known"), Integral) or isinstance(r.get("n_bars_known"), bool) or r["n_bars_known"] < 90:
            absent.append(issuer)
            states[issuer] = None
        else:
            dot = r.get("dot_recent5")
            if dot is not None and not isinstance(dot, (bool, np.bool_)):
                raise ContractError("dot state must be boolean or unknown")
            states[issuer] = {"below20": d < 20, "dot_recent5": bool(dot) if dot is not None else None, "ticker": r["ticker"]}
    n = len(grouped)
    defined = [v for v in states.values() if v is not None]
    dot_defined = [v for v in defined if v["dot_recent5"] is not None]
    return {"status": "SHARE_CLASS_UNRESOLVED" if unresolved else "THIN" if len(defined) < minimum_peers else "CONTEXT_ONLY",
            "group_id": next(iter(groups))[0], "membership_vintage": next(iter(groups))[1],
            "origin": str(t.date()), "focal_issuer_excluded": focal_issuer,
            "membership_basis": "reconstructed_not_original_vintage" if assumed else "availability_checked",
            "n_expected": n, "n_defined": len(defined), "n_missing_or_unresolved": n-len(defined),
            "n_dot_defined": len(dot_defined), "coverage": len(defined)/n if n else None,
            "floor_share": sum(v["below20"] for v in defined)/len(defined) if defined else None,
            "dot_share5": sum(v["dot_recent5"] for v in dot_defined)/len(dot_defined) if dot_defined else None,
            "unresolved_issuers": sorted(unresolved), "missing_issuers": sorted(absent),
            "issuer_states": states, "authority": dict(AUTHORITY)}


def paired_breadth_change(before: Mapping, after: Mapping) -> dict:
    """Separate real changes among paired issuers from membership/coverage changes."""
    if before.get("group_id") != after.get("group_id"):
        raise ContractError("cannot compare unrelated groups")
    if session(before["origin"]) >= session(after["origin"]):
        raise ContractError("breadth comparison must move forward in time")
    if before.get("focal_issuer_excluded") != after.get("focal_issuer_excluded"):
        raise ContractError("focal-issuer exclusion changed")
    a, b = before["issuer_states"], after["issuer_states"]
    shared = sorted(k for k in a.keys() & b.keys() if a[k] is not None and b[k] is not None)
    n = len(shared)
    old = sum(a[k]["below20"] for k in shared)/n if n else None
    new = sum(b[k]["below20"] for k in shared)/n if n else None
    return {"common_defined_issuers": n, "paired_floor_change": new-old if n else None,
            "raw_floor_change": after["floor_share"]-before["floor_share"]
            if before["floor_share"] is not None and after["floor_share"] is not None else None,
            "roster_or_definition_changed": set(a) != set(b) or
            any((a.get(k) is None) != (b.get(k) is None) for k in a.keys() | b.keys()),
            "membership_vintage_changed": before.get("membership_vintage") != after.get("membership_vintage"),
            "authority": dict(AUTHORITY)}


def recovery_context(group_log_returns: pd.Series, market_log_returns: pd.Series,
                     rival_log_returns: pd.Series, *, window: int = 5, beta_window: int = 126) -> pd.DataFrame:
    """Trailing absolute/relative recovery; beta fit excludes the evaluated window.

    Inputs must be aligned causal total-return histories. No missing row is
    carried. Rival selection is the caller's frozen hypothesis, not a fitted
    strongest inverse partner. This is descriptive, not predicted sector alpha.
    """
    idx = calendar_index(group_log_returns.index)
    if not market_log_returns.index.equals(idx) or not rival_log_returns.index.equals(idx):
        raise ContractError("group/market/rival must use identical session clocks")
    if window < 1 or beta_window < 20:
        raise ContractError("invalid lookback")
    g, m, r = [pd.to_numeric(x, errors="coerce").where(lambda z: np.isfinite(z))
               for x in (group_log_returns, market_log_returns, rival_log_returns)]
    cov = g.rolling(beta_window).cov(m).shift(window)
    var = m.rolling(beta_window).var().shift(window)
    beta = cov / var.where(var > 1e-14)
    gs, ms, rs = [x.rolling(window).sum() for x in (g, m, r)]
    out = pd.DataFrame({"group_log_move": gs, "market_log_move": ms, "rival_log_move": rs,
                        "relative_to_rival": gs-rs, "pre_window_market_beta": beta,
                        "market_adjusted_move": gs-beta*ms}, index=idx)
    out["both_falling"] = ((gs < 0) & (rs < 0)).astype("boolean")
    out["relative_gain_without_absolute_gain"] = ((gs-rs > 0) & (gs <= 0)).astype("boolean")
    out.loc[gs.isna() | rs.isna(), ["both_falling", "relative_gain_without_absolute_gain"]] = None
    return out


def attach_context(incumbent: Mapping, context: Mapping) -> dict:
    """Pure opt-in research sidecar; never changes incumbent decisions or scores."""
    if "grey_rotation_research" in incumbent:
        raise ContractError("existing context must be reconciled, not overwritten")
    allowed = {"event", "market", "cohort", "relative_recovery", "personality_coverage", "lineage", "limitations"}
    if set(context)-allowed:
        raise ContractError("only named evidence lanes allowed; no fused probability, score or action")
    out = copy.deepcopy(dict(incumbent))
    payload = copy.deepcopy(dict(context))
    payload["authority"] = dict(AUTHORITY)
    payload["status"] = "RESEARCH_ONLY"
    out["grey_rotation_research"] = payload
    return out
