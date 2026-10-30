"""Source-only paired policy evaluation over predeclared, as-of opportunities.

No price fetch, strategy selection, quote inference, train/test tuning, or
market-data admission occurs here. Both policies must be evaluated on the SAME
opportunity and reference clock by an independently qualified source owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import math
from typing import Any

import numpy as np
import pandas as pd

STATUSES = frozenset({"RESOLVED", "NO_ENTRY", "CENSORED", "UNAVAILABLE"})
OPP_COLUMNS = frozenset({
    "opportunity_id", "symbol", "episode_id", "session_date", "decision_utc",
    "bar_known_at_utc", "leader_known_at_utc", "leader_asof_session",
    "regime_known_at_utc", "input_sha256", "eligible", "signal", "split",
})
OUT_COLUMNS = frozenset({
    "opportunity_id", "policy", "status", "net_r", "outcome_end_utc",
    "outcome_known_at_utc", "common_policy_clock_utc",
    "common_episode_end_utc", "common_risk_unit_sha256", "common_cost_model_sha256",
})
SPLITS = ("DEVELOPMENT", "CALIBRATION", "HOLDOUT")


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class PairedProtocol:
    candidate: str
    baseline: str = "leader_reference"
    registered_at_utc: str | None = None
    analysis_asof_utc: str | None = None
    embargo_calendar_days: int = 9
    block_sessions: int = 20
    bootstrap_draws: int = 1000
    seed: int = 193

    def __post_init__(self):
        if not self.candidate or not self.baseline or self.candidate == self.baseline:
            raise ValueError("two distinct frozen policy identities required")
        if self.embargo_calendar_days < 0 or self.block_sessions < 2:
            raise ValueError("invalid chronological embargo/bootstrap block")
        if not 10 <= self.bootstrap_draws <= 20_000 or not 0 <= self.seed < 2**32:
            raise ValueError("invalid deterministic bootstrap configuration")
        if self.registered_at_utc is not None:
            _clock(self.registered_at_utc)
        if self.analysis_asof_utc is not None:
            _clock(self.analysis_asof_utc)


def _clock(value: Any) -> pd.Timestamp:
    if not isinstance(value, (str, pd.Timestamp)) or pd.isna(value):
        raise ValueError("missing clock")
    try:
        raw = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid timestamp") from exc
    if raw.tzinfo is None or raw.utcoffset() is None:
        raise ValueError("timezone-qualified UTC instant required, not naive/display epoch")
    return raw.tz_convert("UTC")


def _day(value: Any) -> date:
    if not isinstance(value, (str, date)):
        raise ValueError("session date must be YYYY-MM-DD")
    try:
        out = date.fromisoformat(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid session date") from exc
    if type(out) is not date:
        raise ValueError("date without clock required")
    return out


def _amount(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("boolean cannot be an outcome")
    if isinstance(value, (int, float, np.integer, np.floating)):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("nonfinite net outcome")
        return float(value)
    if pd.isna(value):
        return None
    raise ValueError("net_r requires a finite numeric or null")


def _prepared_opportunities(frame: pd.DataFrame) -> pd.DataFrame:
    if OPP_COLUMNS - set(frame.columns):
        raise ValueError(f"missing opportunities columns {sorted(OPP_COLUMNS - set(frame.columns))}")
    if frame.empty:
        raise ValueError("predeclared population is empty")
    a = frame.copy()
    if a.opportunity_id.isna().any() or not a.opportunity_id.map(
            lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise ValueError("stable nonempty opportunity IDs required")
    if a.opportunity_id.duplicated().any():
        raise ValueError("duplicate opportunity ID")
    if a[["symbol", "episode_id", "input_sha256"]].isna().any().any():
        raise ValueError("missing issuer, episode, or input identity")
    if not a.symbol.map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise ValueError("invalid issuer")
    if not a.episode_id.map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise ValueError("invalid episode")
    if a.duplicated(["symbol", "episode_id"]).any():
        raise ValueError("multiple opportunities from a single episode")
    if not a.input_sha256.map(lambda x: isinstance(x, str) and len(x) == 64 and
                               all(c in "0123456789abcdef" for c in x)).all():
        raise ValueError("source payload must carry its 64-char lowercase hash")
    for col in ("eligible", "signal"):
        if not a[col].map(lambda x: type(x) in (bool, np.bool_)).all():
            raise ValueError(f"{col} must be genuine bool, not imputed or string")
    if not a.split.isin(SPLITS).all():
        raise ValueError("unknown split")
    for col in ("decision_utc", "bar_known_at_utc", "leader_known_at_utc", "regime_known_at_utc"):
        a[col] = a[col].map(_clock)
    a["session_date"] = a.session_date.map(_day)
    a["leader_asof_session"] = a.leader_asof_session.map(_day)
    if (a["leader_asof_session"] >= a["session_date"]).any():
        raise ValueError("daily leader context must come from a prior session")
    for col in ("bar_known_at_utc", "leader_known_at_utc", "regime_known_at_utc"):
        if (a[col] > a["decision_utc"]).any():
            raise ValueError("future feature or late source receipt")
    et_day = a.decision_utc.dt.tz_convert("America/New_York").dt.date
    if (et_day != a.session_date).any():
        raise ValueError("decision/session ET date mismatch")
    a = a.sort_values(["decision_utc", "opportunity_id"]).reset_index(drop=True)
    # A calendar block cannot straddle two chronological partitions: every
    # issuer's opportunity on the same session must be assigned together.
    if (a.groupby("session_date")["split"].nunique() > 1).any():
        raise ValueError("same calendar session divided across chronological splits")
    # Chronological partitions must be monotonic. No row-level random split.
    rank = a.split.map({name: i for i, name in enumerate(SPLITS)})
    if (rank.diff().fillna(0) < 0).any():
        raise ValueError("interleaved chronological splits")
    return a


def _prepared_outcomes(frame: pd.DataFrame, ids: set[str], policies: set[str],
                       decisions: dict[str, pd.Timestamp]) -> pd.DataFrame:
    if OUT_COLUMNS - set(frame.columns):
        raise ValueError(f"missing outcome columns {sorted(OUT_COLUMNS - set(frame.columns))}")
    a = frame.copy()
    expected = {(i, p) for i in ids for p in policies}
    actual = set(zip(a.opportunity_id, a.policy))
    if actual != expected or a.duplicated(["opportunity_id", "policy"]).any():
        raise ValueError("full identical opportunity denominator required for each policy")
    if not a.status.isin(STATUSES).all():
        raise ValueError("unrecognized outcome state")
    resolved = []
    paired_protocol: dict[str, tuple[Any, ...]] = {}
    for row in a.itertuples(index=False):
        if (not _sha(row.common_risk_unit_sha256) or
                not _sha(row.common_cost_model_sha256)):
            raise ValueError("frozen common risk/cost digests required")
        clock = _clock(row.common_policy_clock_utc)
        terminal = _clock(row.common_episode_end_utc)
        if clock != decisions[row.opportunity_id] or terminal <= clock:
            raise ValueError("common policy decision or episode terminal clock invalid")
        pair_contract = (clock, terminal, row.common_risk_unit_sha256,
                         row.common_cost_model_sha256)
        prior_contract = paired_protocol.setdefault(row.opportunity_id, pair_contract)
        if prior_contract != pair_contract:
            raise ValueError("candidate/reference policy clocks, horizon, cost and risk must match")
        net = _amount(row.net_r)
        end = None if pd.isna(row.outcome_end_utc) else _clock(row.outcome_end_utc)
        known = None if pd.isna(row.outcome_known_at_utc) else _clock(row.outcome_known_at_utc)
        if end is not None and end > terminal:
            raise ValueError("reported outcome extends beyond the common episode horizon")
        if row.status == "RESOLVED":
            if net is None or end is None or known is None:
                raise ValueError("resolved outcome requires return and label clocks")
            if end <= decisions[row.opportunity_id] or known < end:
                raise ValueError("outcome clock is earlier than source decision/label end")
        else:
            if net is not None:
                raise ValueError("no-entry/censored/unavailable must carry null, not zero")
            if row.status == "NO_ENTRY" and (end is not None or known is not None):
                raise ValueError("NO_ENTRY cannot have a fabricated future outcome")
            if row.status == "CENSORED" and end is None:
                raise ValueError("censoring boundary required")
            if known is not None and end is None:
                raise ValueError("known outcome without its event boundary")
            if end is not None and end <= decisions[row.opportunity_id]:
                raise ValueError("invalid censoring boundary")
            if end is not None and known is not None and known < end:
                raise ValueError("outcome known before observed end")
        resolved.append((end, known))
    a["_end"] = [x[0] for x in resolved]
    a["_known"] = [x[1] for x in resolved]
    a["_r"] = [_amount(x) for x in a.net_r]
    a.loc[a.status == "NO_ENTRY", "_r"] = 0.0
    return a


def _cluster_interval(rows: pd.DataFrame, config: PairedProtocol) -> dict[str, Any]:
    dates = sorted(rows.session_date.unique())
    n = len(dates)
    if n < 2 * config.block_sessions:
        return {"lower": None, "upper": None, "reason": "INSUFFICIENT_DATE_CLUSTERS",
                "date_clusters": n, "required": 2 * config.block_sessions}
    values = [rows.loc[rows.session_date == d, "delta_r"].to_numpy(dtype=float) for d in dates]
    rng = np.random.default_rng(config.seed)
    boot = []
    last_start = n - config.block_sessions
    for _ in range(config.bootstrap_draws):
        draw = []
        while len(draw) < n:
            start = int(rng.integers(0, last_start + 1))
            draw.extend(range(start, start + config.block_sessions))
        sample = np.concatenate([values[i] for i in draw[:n]])
        boot.append(float(sample.mean()))
    lower, upper = np.quantile(np.array(boot, dtype=float), [.025, .975])
    return {"lower": float(lower), "upper": float(upper), "reason": None,
            "date_clusters": n, "required": 2 * config.block_sessions}


def evaluate_paired(opportunities: pd.DataFrame, outcomes: pd.DataFrame,
                    protocol: PairedProtocol) -> dict[str, Any]:
    """Compare two policies over every ex-ante eligible common opportunity.

    A policy that explicitly skips an eligible opportunity contributes zero R.
    Unavailable/censored outcomes remain null and *remove both arms from the
    supported paired mean*, while remaining in coverage/selection denominators.
    Confidence intervals are date-cluster resampling of fully observed pairs,
    not proof of source rights, point-in-time truth or execution quality.
    """
    o = _prepared_opportunities(opportunities)
    policies = {protocol.candidate, protocol.baseline}
    a = _prepared_outcomes(outcomes, set(o.opportunity_id), policies,
                           dict(zip(o.opportunity_id, o.decision_utc)))
    if protocol.analysis_asof_utc is not None:
        asof = _clock(protocol.analysis_asof_utc)
        if (o.decision_utc > asof).any():
            raise ValueError("future decision relative to analysis cutoff")
        if any(t is not None and t > asof for t in a["_known"]):
            raise ValueError("unobserved outcome relative to analysis cutoff")
    wide = a.set_index(["opportunity_id", "policy"])
    details = []
    development_bound = None
    for row in o.itertuples(index=False):
        c = wide.loc[(row.opportunity_id, protocol.candidate)]
        b = wide.loc[(row.opportunity_id, protocol.baseline)]
        if not row.eligible and (c.status == "RESOLVED" or b.status == "RESOLVED"):
            raise ValueError("cannot trade an ineligible episode")
        if not row.signal and c.status == "RESOLVED":
            raise ValueError("candidate trade issued with no as-of signal")
        if row.split != "HOLDOUT":
            for x in (c, b):
                if pd.notna(x["_end"]) and (development_bound is None or x["_end"] > development_bound):
                    development_bound = x["_end"]
        supported = row.eligible and c.status in {"RESOLVED", "NO_ENTRY"} and b.status in {"RESOLVED", "NO_ENTRY"}
        details.append({"opportunity_id": row.opportunity_id, "symbol": row.symbol,
                        "session_date": row.session_date.isoformat(), "split": row.split,
                        "eligible": row.eligible, "signal": row.signal,
                        "candidate_status": c.status, "baseline_status": b.status,
                        "candidate_r": float(c["_r"]) if pd.notna(c["_r"]) else None,
                        "baseline_r": float(b["_r"]) if pd.notna(b["_r"]) else None,
                        "paired_supported": bool(supported),
                        "delta_r": float(c["_r"] - b["_r"]) if supported else None})
    df = pd.DataFrame(details)
    held = o[o.split == "HOLDOUT"]
    holdout_start = held.decision_utc.min() if not held.empty else None
    if holdout_start is not None and development_bound is not None:
        if development_bound >= holdout_start - pd.Timedelta(days=protocol.embargo_calendar_days):
            raise ValueError("development label overlaps holdout embargo: purge before comparison")
    if not held.empty and protocol.registered_at_utc is not None:
        if _clock(protocol.registered_at_utc) >= holdout_start:
            raise ValueError("holdout registration postdates first decision")
    report: dict[str, Any] = {}
    for split in SPLITS:
        cohort = df[(df.split == split) & df.eligible]
        paired = cohort.loc[cohort.paired_supported].copy()
        result = {"eligible": len(cohort), "paired_supported": len(paired),
                  "unpaired_or_censored": len(cohort) - len(paired),
                  "signal_count": int(cohort.signal.sum()),
                  "candidate_nonentries": int((cohort.candidate_status == "NO_ENTRY").sum()),
                  "baseline_nonentries": int((cohort.baseline_status == "NO_ENTRY").sum()),
                  "candidate_censored": int((cohort.candidate_status == "CENSORED").sum()),
                  "baseline_censored": int((cohort.baseline_status == "CENSORED").sum()),
                  "distinct_symbols": int(cohort.symbol.nunique()),
                  "distinct_sessions": int(cohort.session_date.nunique()),
                  "paired_mean_incremental_r": None,
                  "paired_median_incremental_r": None,
                  "date_block_bootstrap": None}
        if len(paired):
            result["paired_mean_incremental_r"] = float(paired.delta_r.mean())
            result["paired_median_incremental_r"] = float(paired.delta_r.median())
            result["date_block_bootstrap"] = _cluster_interval(paired, protocol)
        report[split] = result
    return {"schema": "rs_leader_paired_policy_research.v1",
            "candidate": protocol.candidate, "baseline": protocol.baseline,
            "source_admission": "NOT_ATTESTED_BY_THIS_EVALUATOR",
            "empirical_strategy_edge_verdict": "NOT_ESTABLISHED",
            "holdout_status": ("ABSENT" if held.empty else
                               "REGISTRATION_NOT_PROVED" if protocol.registered_at_utc is None else
                               "REGISTRATION_DECLARED_NOT_INDEPENDENTLY_ATTESTED"),
            "denominator": {"all_predeclared": len(df), "eligible": int(df.eligible.sum()),
                            "ineligible": int((~df.eligible).sum())},
            "splits": report, "paired_opportunities": details}
