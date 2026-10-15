"""Offline comparison of TWO separately receipt-qualified BOATS source vintages.

Source truth, custody, rights, calendar and vendor request semantics remain
owned by the ORIGINAL Macro Data OS L0/L1 readers. This module only consumes
already verified original fullsession.Bar minute inputs, audits UTC timestamp
collisions and OHLCV equality, and emits COUNTS / truth flags. It neither
splices historical prices nor selects a winning vintage or builds indicators,
and it can never prove point-in-time availability, NBBO, execution or trading.
"""
from __future__ import annotations

from collections import Counter
import re
from typing import Sequence

from fullsession import Bar

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = ("open", "high", "low", "close", "volume")


def _indexed(bars: Sequence[Bar], *, source_name: str) -> dict:
    if not isinstance(bars, (list, tuple)):
        raise ValueError(f"{source_name} requires original Bar sequence")
    result = {}
    prev = None
    for b in bars:
        if not isinstance(b, Bar) or b.minutes != 1 or b.symbol != "SOXX":
            raise ValueError(f"{source_name} must contain original SOXX one-minute Bars")
        if b.source != "tiingo-boats" or b.basis != "raw":
            raise ValueError(f"{source_name} is not raw canonical Tiingo BOATS history")
        if b.utc.second or b.utc.microsecond:
            raise ValueError("source minute not aligned to original UTC minute")
        if prev is not None and b.utc <= prev:
            raise ValueError("unsorted or duplicate original source minute timestamps")
        prev = b.utc
        result[b.utc] = b
    return result


def audit_receipt_overlap(original: Sequence[Bar], candidate: Sequence[Bar], *,
                          original_raw_sha256: str,
                          candidate_raw_sha256: str) -> dict:
    """Classify source-vintage conflicts, without outputting market prices or rows.

    Both inputs MUST already have been separately authenticated via original
    read_research_view + tiingo_l1_v13.l1_to_bars. Digest arguments identify
    externally verified source receipts; digest *shape* is NOT authentication.
    A candidate with disjoint source minutes is a source discovery, not a fill.
    Equal overlapping prices are not provenance/PIT validation or permission to
    produce a mixed-vintage synthetic backtest.
    """
    for name, digest in (("original", original_raw_sha256),
                         ("candidate", candidate_raw_sha256)):
        if not isinstance(digest, str) or not _SHA.fullmatch(digest):
            raise ValueError(f"{name} raw source SHA256 must be canonical lowercase")
    if original_raw_sha256 == candidate_raw_sha256:
        raise ValueError("same source digest is not an independent receipt comparison")
    old = _indexed(original, source_name="original")
    new = _indexed(candidate, source_name="candidate")
    collision = sorted(set(old) & set(new))
    changed = Counter()
    identical = 0
    for ts in collision:
        a,b=old[ts],new[ts]
        bad = [f for f in _FIELDS if getattr(a,f)!=getattr(b,f)]
        if not bad:
            identical += 1
        else:
            changed.update(bad)
    failures = len(collision) - identical
    return {
        "schema": "mastermind.soxx.boats_receipt_vintage_overlap.v31",
        "status": ("QUARANTINE_CONFLICTING_HISTORICAL_VINTAGES" if failures
                   else ("SOURCE_TIME_OVERLAP_EXACT_NO_PRICE_CONFLICT" if collision
                         else "DISJOINT_ORIGINAL_SOURCE_TIMESTAMPS_NO_VINTAGE_COMPARISON")),
        "original_source_sha256": original_raw_sha256,
        "candidate_source_sha256": candidate_raw_sha256,
        "original_source_minute_rows": len(old),
        "candidate_source_minute_rows": len(new),
        "overlapping_original_UTC_minute_instants": len(collision),
        "overlapping_identical_OHLCV_rows": identical,
        "overlapping_conflicting_OHLCV_rows": failures,
        "overlap_conflicting_field_counts": dict(changed),
        "candidate_new_UTC_minute_instants": len(set(new) - set(old)),
        "original_only_UTC_minute_instants": len(set(old) - set(new)),
        "distinct_UTC_minute_instants": len(set(old) | set(new)),
        "source_price_rows_exported": 0,
        "source_price_values_exported": 0,
        "joined_price_series_constructed": False,
        "overlap_consistency_implies_point_in_time_qualified": False,
        "overlap_consistency_implies_quote_executable": False,
        "independent_strategy_validation_accepted": False,
        "note": "Original source receipt authority must be checked upstream; even matching vintages never prove tradable bid/ask or legal redistribution.",
    }
