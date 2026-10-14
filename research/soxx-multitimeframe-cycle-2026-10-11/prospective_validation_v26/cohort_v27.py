"""Frozen dual-checkpoint, full-denominator prospective SOXX accounting (V27).

Offline only. Consumes qualified DERIVED episode/return records, never requests vendor
data or constructs candles, broker orders, schedules, indicators or a new calendar.
Caller-supplied source claims are NOT authenticated by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import import_module
import re
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

_v26 = import_module(
    "research.soxx-multitimeframe-cycle-2026-10-11.prospective_validation_v26.utility"
)
PairedOutcome = _v26.PairedOutcome
_clock = _v26._clock

NY = ZoneInfo("America/New_York")
WINDOW_START = date(2026, 10, 14)
WINDOW_END = date(2027, 4, 13)
CHECKPOINTS = ("30m", "3h")
DELAYS_5M_BARS = (1, 2, 4)
ADVERSE_BPS = (0, 10, 25, 50, 100)
ARMS = tuple((cp, delay) for cp in CHECKPOINTS for delay in DELAYS_5M_BARS)
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class UpstreamSourceClaims:
    """Metadata claims to verify independently with the incumbent source owner.

    Neither hashes nor booleans here prove external coverage, rights, provenance,
    PIT vintage, executable quotes or complete parent-turn extraction.
    """
    protocol_committed_at: datetime
    incumbent_manifest_sha256: str
    incumbent_receipt_ref: str
    entry_universe_complete: bool
    warmup_complete: bool
    source_clock_qualified: bool
    vintage_adjustment_qualified: bool
    internal_research_rights_qualified: bool

    def __post_init__(self) -> None:
        committed = _clock(self.protocol_committed_at, "protocol_committed_at")
        object.__setattr__(self, "protocol_committed_at", committed)
        if committed >= datetime(2026, 10, 14, tzinfo=NY).astimezone(timezone.utc):
            raise ValueError("prospective protocol was not committed before first entry window")
        if not isinstance(self.incumbent_manifest_sha256, str) or not _HASH.fullmatch(
            self.incumbent_manifest_sha256
        ):
            raise ValueError("source manifest must have a canonical SHA256")
        if not isinstance(self.incumbent_receipt_ref, str) or not (
            0 < len(self.incumbent_receipt_ref.strip()) <= 512
            and self.incumbent_receipt_ref == self.incumbent_receipt_ref.strip()
        ):
            raise ValueError("incumbent source receipt reference is missing/invalid")
        for field in (
            "entry_universe_complete", "warmup_complete", "source_clock_qualified",
            "vintage_adjustment_qualified", "internal_research_rights_qualified",
        ):
            if type(getattr(self, field)) is not bool:
                raise ValueError("source qualification flags must be explicit booleans")

    @property
    def missing_gates(self) -> tuple[str, ...]:
        return tuple(name for name in (
            "entry_universe_complete", "warmup_complete", "source_clock_qualified",
            "vintage_adjustment_qualified", "internal_research_rights_qualified",
        ) if not getattr(self, name))


@dataclass(frozen=True)
class OriginalEpisode:
    """One upstream-sealed original entry; end is the matched baseline path end.

    outcome_known_at is the first instant complete paired baseline evidence became
    available. None must not be silently treated as a completed result.
    """
    episode: str
    symbol: str
    entry_at: datetime
    baseline_end_at: datetime
    outcome_known_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.episode, str) or not self.episode or self.episode.strip() != self.episode:
            raise ValueError("invalid episode identifier")
        if not isinstance(self.symbol, str) or not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("invalid symbol")
        entry = _clock(self.entry_at, "entry_at")
        end = _clock(self.baseline_end_at, "baseline_end_at")
        object.__setattr__(self, "entry_at", entry)
        object.__setattr__(self, "baseline_end_at", end)
        if end <= entry:
            raise ValueError("baseline horizon must finish after original entry")
        if not WINDOW_START <= entry.astimezone(NY).date() <= WINDOW_END:
            raise ValueError("original entry is outside the prospectively frozen ET window")
        if self.outcome_known_at is not None:
            known = _clock(self.outcome_known_at, "outcome_known_at")
            if known < end:
                raise ValueError("paired outcome evidence predates baseline completion")
            object.__setattr__(self, "outcome_known_at", known)


def evaluate_frozen_grid(
    source: UpstreamSourceClaims,
    original: Sequence[OriginalEpisode],
    policies: Mapping[tuple[str, int], Sequence[PairedOutcome]],
    *,
    evaluation_at: datetime,
) -> dict:
    """Use SAME original denominator for all 2 x 3 x 5 prescribed comparisons.

    Never select the better checkpoint/delay/cost. All cases stay descriptive;
    upstream evidence must be independently verified before interpreting any
    return as source-qualified, much less tradable or generalizable.
    """
    if not isinstance(source, UpstreamSourceClaims):
        raise ValueError("explicit source claims required")
    evaluation_at = _clock(evaluation_at, "evaluation_at")
    if evaluation_at < source.protocol_committed_at:
        raise ValueError("report cannot predate protocol publication")
    if source.missing_gates:
        return {
            "status": "WITHHELD_SOURCE_OR_UNIVERSE",
            "missing_gates": source.missing_gates,
            "cells": None,
            "source_claims_externally_authenticated": False,
            "live_trading_accepted": False,
        }

    episodes = list(original)
    if any(not isinstance(e, OriginalEpisode) for e in episodes):
        raise ValueError("original inventory must contain OriginalEpisode")
    ids = [e.episode for e in episodes]
    if len(ids) != len(set(ids)):
        raise ValueError("repeated original entry is not a new independent episode")
    if not episodes:
        return {
            "status": "NO_OBSERVED_PARENT_EPISODES",
            "original_episodes": 0,
            "cells": None,
            "source_claims_externally_authenticated": False,
            "live_trading_accepted": False,
        }
    if any(e.entry_at > evaluation_at for e in episodes):
        raise ValueError("future original entry cannot be scored as an observed episode")
    # The preregistered cutoff is FIXED. Interim source-quality checks are fine,
    # but interim realized strategy results must never become stopping signals.
    window_closed_at = datetime(2027, 4, 14, tzinfo=NY).astimezone(timezone.utc)
    if evaluation_at < window_closed_at:
        return {
            "status": "WITHHELD_WINDOW_OPEN", "original_episodes": len(ids),
            "cells": None, "source_claims_externally_authenticated": False,
            "live_trading_accepted": False,
        }
    # The original 52-RTH-hour exit horizon may extend far past Apr 13.
    # All original paths must finish, even when a fill remains unresolved.
    if any(e.baseline_end_at > evaluation_at for e in episodes):
        return {
            "status": "WITHHELD_UNFINISHED_HORIZON", "original_episodes": len(ids),
            "cells": None, "source_claims_externally_authenticated": False,
            "live_trading_accepted": False,
        }
    if set(policies) != set(ARMS):
        raise ValueError("all six frozen checkpoint/delay arms are mandatory")

    by_id = {e.episode: e for e in episodes}
    sorted_ids = sorted(ids)
    by_arm: dict[tuple[str, int], dict[str, PairedOutcome]] = {}
    baselines: dict[str, float] = {}

    for key in ARMS:
        rows = list(policies[key])
        if any(not isinstance(r, PairedOutcome) for r in rows):
            raise ValueError("arm contains an invalid paired-outcome record")
        members = [r.episode for r in rows]
        if len(members) != len(set(members)) or set(members) != set(sorted_ids):
            raise ValueError("missing, duplicated, or invented episodes in policy arm")
        by_arm[key] = {r.episode: r for r in rows}
        for r in rows:
            meta = by_id[r.episode]
            # An unknown discretionary sale can coexist with an already-known
            # baseline return. That known baseline must be mature and identical
            # across ALL arms; "UNRESOLVED" cannot launder future or conflicting
            # baseline information into a supposedly matched original cohort.
            if r.state != "UNRESOLVED" or r.baseline_pp is not None:
                if meta.outcome_known_at is None or meta.outcome_known_at > evaluation_at:
                    raise ValueError("known paired/baseline return has no mature owner evidence")
            if r.baseline_pp is not None:
                prev = baselines.setdefault(r.episode, r.baseline_pp)
                if prev != r.baseline_pp:
                    raise ValueError("different baseline return across matched arms")

    # No exchange-hour arithmetic or independent-trial fiction: these are the
    # actual upstream-reported exposure intervals, with overlap diagnoses only.
    overlaps = _v26.overlap_components(
        [(e.episode, e.entry_at, e.baseline_end_at) for e in episodes]
    )
    soxx_ids = sorted(e.episode for e in episodes if e.symbol.upper() == "SOXX")
    subsets = {"all_symbols": sorted_ids}
    if soxx_ids:
        subsets["SOXX_only"] = soxx_ids

    cells = {}
    for cp, delay in ARMS:
        for cohort_name, cohort_ids in subsets.items():
            ledger = [by_arm[(cp, delay)][id_] for id_ in cohort_ids]
            previous = None
            for bps in ADVERSE_BPS:
                # A partially covered uncertainty envelope raises (never drops
                # affected episodes or treats the uncertainty as no sale).
                result = _v26.summarize(
                    cohort_ids, ledger, extra_sell_slippage_bps=bps
                )
                current = result["mean_delta_pp"]
                if current is not None and previous is not None and current > previous + 1e-10:
                    raise AssertionError("adverse execution cost improved net return")
                previous = current
                cells[f"{cohort_name}:{cp}:d{delay}:bp{bps}"] = result

    return {
        "status": "STRUCTURAL_ECONOMICS_ONLY",
        "source_manifest_sha256": source.incumbent_manifest_sha256,
        "source_ref": source.incumbent_receipt_ref,
        "original_episodes": len(sorted_ids),
        "SOXX_original_episodes": len(soxx_ids),
        "primary_SOXX_evidence": "STRUCTURAL_ONLY" if soxx_ids else "NO_PRIMARY_EPISODES",
        "all_symbol_overlap_components": len(overlaps),
        "max_connected_exposure_episodes": max(map(len, overlaps)),
        "matched_denominator_all_arms": True,
        "cells": cells,
        "source_claims_externally_authenticated": False,
        "execution_marketability_proven": False,
        "inferential_confidence_claim": False,
        "live_trading_accepted": False,
        "note": "Caller-controlled claims are NOT independent source-owner proof; these are derived paired-accounting scenarios, not evidence of a profitable or executable policy.",
    }
