"""brain/liquidity_transmission.py — THE sole Mastermind reader for the Global Liquidity
Transmission (GLT) producer (W-LIQ.2, Mastermind issue #119).

Reads ONLY ``vendor/macro/site/liquiditydata/global_liquidity_transmission.json``
(schema ``global_liquidity_transmission.v1``), produced by Macro W-LIQ.1.  No other
Mastermind module may open that file; every consumer goes through this module.  Nothing
here imports Macro engine code, and nothing here recomputes or falls back to a locally
derived state — the producer's frozen handoff forbids both ("Neither consumer may
recompute or fall back").

Fail-soft everywhere: absent / malformed / wrong-schema / stale / garbled-mode →
empty / advisory / inert.  This module never raises into a build.

PUBLIC API
----------
* ``context()``              — full artifact dict; ``{}`` unless present AND valid AND
                               fresh (never a partially-trusted state).  The file read is
                               cached; the freshness verdict is NOT (see CACHING below).
* ``market_plane()``         — compact dict for the ``liquidity_transmission`` market_view
                               plane; truthful provenance even when absent/stale.
* ``target(symbol)``         — ``{}`` in this wave (see CONTRACT SCOPE below).
* ``opportunities(limit=…)`` — ``[]`` in this wave (see CONTRACT SCOPE below).
* ``audit_row()``            — perception/runlog row: status, both clocks, age, state,
                               coverage, confidence, current authority mode.
* ``decision_signals(symbol)`` — the typed decision chokepoint; inert in this wave for
                               EVERY mode (see AUTHORITY LADDER).
* ``glt_mode()``             — the current authority mode.
* ``_reset_context_cache()`` — explicit cache reset for tests.

CONTRACT SCOPE (why target()/opportunities() are empty)
-------------------------------------------------------
The producer publishes ``meta.contract_scope = 'state_quality_freshness_only'`` and
``meta.authority = 'measurement_only'``, with ``meta.forbidden_authority`` listing
trade / allocation / alert / dispatch / transmission_curve / repricing_gap.  Per-symbol
targets and an opportunity ranking are later-wave fields that DO NOT EXIST in v1.  They
return empty here and are never synthesised from current state — manufacturing them from
``state`` would invent authority the producer explicitly withholds.

CLOCK LAW (the load-bearing part)
---------------------------------
Evidence availability is NOT when the file was written.  The producer names its own
adapter seam and this reader honours exactly that naming:

    freshness.clocks.adapter_observed_at_field -> 'evidence_available_at'
    freshness.clocks.adapter_known_at_field    -> 'first_known_at'

* ``evidence_available_at`` is the conservative all-evidence availability boundary — "no
  earlier than the latest availability of every field copied into state.event_reference".
  It is the ONLY clock freshness/age is measured from.
* ``release_at`` is a documented alias of it; ``monetary_release_at`` is the monetary-only
  release and is explicitly NOT the evidence boundary.
* ``first_known_at`` is the known clock (PIT/audit), never a freshness input.
* ``meta.generated_at``, ``latest_component_observed_at`` and the file's mtime are NEVER
  evidence availability.  Using any of them would let a wrapper rewritten today launder
  weeks-old component evidence into a "current" reading.

The artifact's own ``freshness.status`` was computed when the file was written, so it goes
stale on the shelf and can never on its own certify freshness.  It is applied only in the
fail-closed direction: a producer that declares itself not-fresh is not fresh here either,
whatever the age arithmetic says.

If the artifact declares adapter clock field names other than the two pinned above, the
seam has moved: that is a contract change, and the read goes inert rather than silently
following a redirected clock.

VOCABULARIES (two closed sets, never interchangeable)
------------------------------------------------------
* direction — ``expanding`` | ``flat`` | ``contracting`` | ``unknown``
* quality   — ``easing`` | ``tightening`` | ``mixed`` | ``unknown``

Their only shared member is ``unknown``.  No value from one set is ever emitted in a field
belonging to the other, and neither is ever translated into the market_view risk
vocabulary (risk_off/neutral/risk_on) — see ``market_plane()``.

MAGNITUDE (two separate numbers, each with its own unit)
---------------------------------------------------------
``magnitude`` is the raw ``state.monetary_impulse`` in ``weekly_change_in_expanding_z_score``
units and is NOT standardized.  ``magnitude_z`` is its prior-only causal expanding-z
standardization, and is the only one a downstream z-threshold may ever gate on.  Both are
emitted only alongside their own unit strings; neither is ever surfaced as a bare number.

MISSING IS NOT ZERO
-------------------
``credit_impulse_global = null`` means insufficient comparable PIT coverage.  Nulls are
preserved as ``None`` and never coerced to 0.0.

CACHING
-------
The process cache holds the file read and its structural validation — never a freshness
verdict.  Caching the verdict would freeze both status and age for the life of the
process, so a long-running consumer that loaded a fresh artifact would keep reporting it
fresh at its load-time age forever.  That is the same "stale reads as current" failure as
a laundered wrapper, arriving through the cache, so the clock is re-judged on every call.

AUTHORITY LADDER
----------------
``off -> shadow -> display -> candidacy -> context -> vote`` (monotone; each rung is a
superset of the prior).  ``MASTERMIND_GLT_MODE`` selects it; absent → ``shadow`` (this
wave's default), present-but-unrecognized/garbled → ``off``.  Unknown input never
escalates.

In W-LIQ.2 every rung is behaviourally inert: ``decision_signals()`` returns the same
inert record for ``vote`` as for ``off``, because the producer's contract scope carries no
decision-bearing fields to act on.  The ladder exists so later waves add authority at a
typed chokepoint instead of through ad-hoc raw reads.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
# Follow the intake/_neural_web_context convention: _V = repo_root / "vendor" / "macro".
_V = _ROOT / "vendor" / "macro"
_ARTIFACT_PATH = _V / "site" / "liquiditydata" / "global_liquidity_transmission.json"

# The producer contract this reader is pinned to.
_EXPECTED_SCHEMA = "global_liquidity_transmission.v1"
_EXPECTED_CONTRACT_SCOPE = "state_quality_freshness_only"
_EXPECTED_AUTHORITY = "measurement_only"

# The producer-declared adapter clock seam (freshness.clocks.*).  Pinned: a differently
# named seam is a contract change, not a redirect to follow.
_OBSERVED_AT_FIELD = "evidence_available_at"
_KNOWN_AT_FIELD = "first_known_at"

# Clocks that are NEVER evidence availability.  Listed so the prohibition is greppable and
# testable, not merely documented.
_NON_EVIDENCE_CLOCKS: frozenset[str] = frozenset({
    "generated_at",                   # when the wrapper was written
    "monetary_release_at",            # the monetary-only release, not the all-evidence boundary
    "latest_component_observed_at",   # newest component reference date, not availability
    "state_asof",                     # the economic/state grid date, not availability
})

# Staleness horizon in CALENDAR days, measured from evidence_available_at.  The producer is
# weekly (W-FRI); one cycle plus a weekend and a release-lag day is the conservative bound.
_STALE_DAYS = 10

# The two closed vocabularies.  A value outside its own set degrades to 'unknown' — it is
# never repaired by borrowing from the other set.
_DIRECTION_VOCAB: frozenset[str] = frozenset({"expanding", "flat", "contracting", "unknown"})
_QUALITY_VOCAB: frozenset[str] = frozenset({"easing", "tightening", "mixed", "unknown"})
_UNKNOWN = "unknown"

# Monotone authority ladder.  Ordinal only — values exist for threshold (>=) comparisons.
_MODE_ORDER: dict[str, int] = {
    "off": 0,
    "shadow": 1,
    "display": 2,
    "candidacy": 3,
    "context": 4,
    "vote": 5,
}
# W-LIQ.2 default: shadow.  Every rung is inert this wave (see module docstring).
_MODE_DEFAULT = "shadow"
_MODE_ENV = "MASTERMIND_GLT_MODE"

# Status tokens for the audit/plane surface.
_ST_PRESENT = "present"
_ST_ABSENT = "absent"
_ST_STALE = "stale"
_ST_INVALID = "invalid"

# --------------------------------------------------------------------------- #
# process-level cache — reset via _reset_context_cache() for tests
# --------------------------------------------------------------------------- #
# Caches the FILE READ and its structural validation only — never a freshness verdict.
_SNAP_CACHE: dict[str, Any] | None = None


def _reset_context_cache() -> None:
    """Invalidate the per-process read cache.  Tests MUST call this around fixtures."""
    global _SNAP_CACHE
    _SNAP_CACHE = None


# --------------------------------------------------------------------------- #
# authority ladder
# --------------------------------------------------------------------------- #

def glt_mode() -> str:
    """Return the GLT authority mode from ``MASTERMIND_GLT_MODE`` (default 'shadow').

    Absent → the wave default ('shadow').  Present but empty/unrecognized → 'off': a
    garbled value must never ESCALATE authority, and must not silently inherit the
    default either.
    """
    try:
        raw = os.environ.get(_MODE_ENV)
        if raw is None:
            return _MODE_DEFAULT
        raw = raw.strip().lower()
        return raw if raw in _MODE_ORDER else "off"
    except Exception:  # noqa: BLE001 — fail-soft: never raise
        return "off"


def _mode_ge(mode: str, threshold: str) -> bool:
    """True iff ``mode`` is at or above ``threshold``.  Unknown resolves to 'off' (rank 0)."""
    return _MODE_ORDER.get(mode, 0) >= _MODE_ORDER.get(threshold, 0)


# --------------------------------------------------------------------------- #
# clocks
# --------------------------------------------------------------------------- #

def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse a producer clock string to an aware UTC datetime; None when unparseable.

    Accepts date-only ('2026-08-28', the producer's conservative_date_only precision) and
    ISO-8601 with 'Z' or an explicit offset.  A naive timestamp is read as UTC.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:  # noqa: BLE001
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_days(value: Any, now: Optional[datetime] = None) -> Optional[float]:
    """Calendar-day age of a producer clock.  None when unparseable.  Negative = future."""
    dt = _parse_ts(value)
    if dt is None:
        return None
    ref = now or datetime.now(timezone.utc)
    return (ref - dt).total_seconds() / 86400.0


def _as_float(value: Any) -> Optional[float]:
    """Coerce to float, preserving None.  Never turns a null into 0.0 (missing != zero)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except Exception:  # noqa: BLE001
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf are not readings
        return None
    return out


def _vocab(value: Any, vocab: frozenset[str]) -> str:
    """Map a producer token into its OWN closed vocabulary; anything else → 'unknown'."""
    if isinstance(value, str) and value.strip().lower() in vocab:
        return value.strip().lower()
    return _UNKNOWN


# --------------------------------------------------------------------------- #
# load + validate
# --------------------------------------------------------------------------- #

# Sentinel distinguishing "nothing was read" from "something was read that parsed to null".
_UNREADABLE = object()


def _load_raw() -> Any:
    """Read and JSON-parse the artifact.

    Returns the parsed document, or ``_UNREADABLE`` when the file is missing/unreadable/
    unparseable.  The sentinel matters: a document that parses to ``null`` is a file that
    EXISTS and is not a producer document (status 'invalid'), which is a different fact
    from no file at all (status 'absent'), and the runlog should be able to tell them apart.
    """
    try:
        if not _ARTIFACT_PATH.exists():
            return _UNREADABLE
        return json.loads(_ARTIFACT_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("liquidity_transmission: read failed (%s)", e)
        return _UNREADABLE


def _validate_contract(raw: Any) -> tuple[bool, str]:
    """Return (valid, reason) for the STRUCTURAL contract — no freshness judgement here.

    Fail-closed on every check: an unexpected schema, a widened authority claim, or a
    redirected adapter clock seam all mean the producer contract this reader was written
    against no longer holds.
    """
    if not isinstance(raw, dict):
        return False, "not a dict"
    meta = raw.get("meta")
    if not isinstance(meta, dict):
        return False, "meta absent"
    if meta.get("schema") != _EXPECTED_SCHEMA:
        return False, f"wrong schema {meta.get('schema')!r}"
    if meta.get("contract_scope") != _EXPECTED_CONTRACT_SCOPE:
        return False, f"unexpected contract_scope {meta.get('contract_scope')!r}"
    if meta.get("authority") != _EXPECTED_AUTHORITY:
        return False, f"unexpected authority {meta.get('authority')!r}"
    for block in ("state", "quality", "freshness"):
        if not isinstance(raw.get(block), dict):
            return False, f"{block} block absent or not a dict"
    clocks = raw["freshness"].get("clocks")
    if not isinstance(clocks, dict):
        return False, "freshness.clocks absent"
    # The producer names its own adapter seam; a different naming is a contract change.
    if clocks.get("adapter_observed_at_field") != _OBSERVED_AT_FIELD:
        return False, (
            f"adapter_observed_at_field moved: "
            f"{clocks.get('adapter_observed_at_field')!r} != {_OBSERVED_AT_FIELD!r}"
        )
    if clocks.get("adapter_known_at_field") != _KNOWN_AT_FIELD:
        return False, (
            f"adapter_known_at_field moved: "
            f"{clocks.get('adapter_known_at_field')!r} != {_KNOWN_AT_FIELD!r}"
        )
    if not clocks.get(_OBSERVED_AT_FIELD):
        return False, f"{_OBSERVED_AT_FIELD} absent"
    return True, "ok"


def _observed_date(value: Any) -> Optional[str]:
    """The evidence clock's calendar DATE (YYYY-MM-DD), or None.

    The producer stamps ``release_clock_precision = 'conservative_date_only'``: the clock is
    honest to the day, not the second.  Consumers whose calendar arithmetic is date-based
    (market_view's trading-day counter among them) must be handed this, never the full ISO
    string -- an unparsed timestamp there reads as unknown-age and pins the plane stale
    forever, which is fail-closed but false.
    """
    dt = _parse_ts(value)
    return dt.date().isoformat() if dt is not None else None


def _freshness_verdict(raw: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """Judge freshness from the evidence clock ALONE (plus the producer's own fail-closed status).

    Returns {observed_at, observed_date, known_at, age_days, stale, future_dated, reason}.  Fail-closed:
    an unparseable clock, a future-dated evidence boundary, an evidence clock that
    postdates the known clock, or a producer that declares itself not-fresh are all stale.
    """
    clocks = (raw.get("freshness") or {}).get("clocks") or {}
    observed_at = clocks.get(_OBSERVED_AT_FIELD)
    known_at = clocks.get(_KNOWN_AT_FIELD)
    age = _age_days(observed_at, now=now)

    reason = "ok"
    stale = False
    if age is None:
        stale, reason = True, f"{_OBSERVED_AT_FIELD} unparseable: {observed_at!r}"
    elif age < 0:
        stale, reason = True, f"future-dated {_OBSERVED_AT_FIELD}={observed_at}"
    elif age > _STALE_DAYS:
        stale, reason = True, f"age {age:.2f}d > {_STALE_DAYS}d from {_OBSERVED_AT_FIELD}"

    # Evidence cannot become available AFTER the producer first knew it.  A wrapper that
    # claims otherwise is asserting a clock it could not have observed.
    obs_dt, known_dt = _parse_ts(observed_at), _parse_ts(known_at)
    if not stale and obs_dt is not None and known_dt is not None and obs_dt > known_dt:
        stale, reason = True, (
            f"{_OBSERVED_AT_FIELD}={observed_at} postdates {_KNOWN_AT_FIELD}={known_at}"
        )

    # The producer's own status is applied one-way only: it can condemn, never certify.
    producer_status = (raw.get("freshness") or {}).get("status")
    if not stale and producer_status != "fresh":
        stale, reason = True, f"producer freshness.status={producer_status!r}"

    return {
        "observed_at": observed_at if isinstance(observed_at, str) else None,
        "observed_date": _observed_date(observed_at),
        "known_at": known_at if isinstance(known_at, str) else None,
        "age_days": round(age, 4) if age is not None else None,
        "stale": bool(stale),
        "future_dated": bool(age is not None and age < 0),
        "stale_after_days": _STALE_DAYS,
        "reason": reason,
    }


def _provenance(raw: dict[str, Any]) -> dict[str, Any]:
    """Exact source/version/clock provenance, copied from the producer without derivation."""
    meta = raw.get("meta") or {}
    clocks = (raw.get("freshness") or {}).get("clocks") or {}
    return {
        "artifact_path": _artifact_path_label(),
        "schema": meta.get("schema"),
        "producer_version": meta.get("producer_version"),
        "model_version": meta.get("model_version"),
        "data_version": meta.get("data_version"),
        "source_snapshot_hash": meta.get("source_snapshot_hash"),
        "config_hash": meta.get("config_hash"),
        "contract_scope": meta.get("contract_scope"),
        "authority": meta.get("authority"),
        "forbidden_authority": list(meta.get("forbidden_authority") or []),
        "frequency": meta.get("frequency"),
        "owner": meta.get("owner"),
        "clocks": {
            # The two adapter clocks, named exactly as the producer names them …
            "observed_at_field": _OBSERVED_AT_FIELD,
            "observed_at": clocks.get(_OBSERVED_AT_FIELD),
            "known_at_field": _KNOWN_AT_FIELD,
            "known_at": clocks.get(_KNOWN_AT_FIELD),
            "release_clock_precision": clocks.get("release_clock_precision"),
            "evidence_available_at_law": clocks.get("evidence_available_at_law"),
            # … and the clocks that are explicitly NOT evidence availability, carried for
            # audit visibility so a reader can see what was rejected, never used for age.
            "not_evidence_availability": {
                "generated_at": meta.get("generated_at"),
                "monetary_release_at": clocks.get("monetary_release_at"),
                "latest_component_observed_at": clocks.get("latest_component_observed_at"),
                "state_asof": clocks.get("state_asof"),
            },
        },
    }


def _artifact_path_label() -> str:
    """A stable, repo-relative label for the artifact — absolute when it lies elsewhere.

    ``vendor/macro`` is a symlink, so the artifact does not have to resolve under the repo
    root; ``Path.relative_to`` RAISES in that case, and an exception here would be caught
    upstream and reported as an ABSENT artifact even though the file was present and valid.
    """
    try:
        return str(_ARTIFACT_PATH.relative_to(_ROOT))
    except Exception:  # noqa: BLE001 — outside the root is legitimate, not an error
        return str(_ARTIFACT_PATH)


def _snapshot(now: Optional[datetime] = None) -> dict[str, Any]:
    """Internal structured read: status + provenance + clocks, WHATEVER the freshness.

    Unlike ``context()`` (which withholds a stale/invalid artifact entirely), this keeps
    truthful provenance for the shadow plane and the audit row, so an absent or stale
    producer is reported as absent or stale WITH its identity rather than as silence.
    """
    global _SNAP_CACHE
    try:
        # Only the READ and the structural validation are cached -- never the freshness
        # verdict.  Caching the verdict would freeze both the status and the age for the
        # life of the process: a long-running consumer that loaded a fresh artifact would
        # go on reporting it fresh, at its load-time age, indefinitely.  That is the
        # headline "stale artifact appears current" attack arriving through the cache
        # instead of through the wrapper, so the clock is re-judged on every call.
        cached = _SNAP_CACHE
        if cached is None:
            raw = _load_raw()
            if raw is _UNREADABLE:
                cached = {"status": _ST_ABSENT, "reason": "artifact absent or unreadable",
                          "raw": None, "provenance": None}
            else:
                valid, reason = _validate_contract(raw)
                if not valid:
                    # provenance is only trustworthy once the contract validates
                    cached = {"status": _ST_INVALID, "reason": reason, "raw": None,
                              "provenance": None}
                else:
                    cached = {"status": None, "reason": None, "raw": raw,
                              "provenance": _provenance(raw)}
            _SNAP_CACHE = cached

        if cached["raw"] is None:                     # absent / invalid — no clock to judge
            return {**cached, "freshness": None}
        fresh = _freshness_verdict(cached["raw"], now=now)
        return {
            "status": _ST_STALE if fresh["stale"] else _ST_PRESENT,
            "reason": fresh["reason"],
            "raw": cached["raw"],
            "provenance": cached["provenance"],
            "freshness": fresh,
        }
    except Exception as e:  # noqa: BLE001 — fail-soft: never raise into a build
        log.warning("liquidity_transmission: unexpected error reading artifact (%s)", e)
        return {"status": _ST_ABSENT, "reason": f"reader error: {e}", "raw": None,
                "provenance": None, "freshness": None}


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #

def context() -> dict[str, Any]:
    """Return the full producer artifact dict, or ``{}``.

    ``{}`` whenever the artifact is absent, malformed, wrong-schema, contract-moved, or
    stale — a partially-trusted state is never handed out.  Cached for the process
    lifetime; call ``_reset_context_cache()`` to force a re-read.
    """
    try:
        # Deliberately NOT memoised on the freshness verdict: _snapshot() re-judges the
        # clock on every call (the file read behind it IS cached), so a document that ages
        # out mid-process stops being handed out instead of persisting as once-fresh.
        snap = _snapshot()
        if snap["status"] != _ST_PRESENT or not isinstance(snap.get("raw"), dict):
            log.debug("liquidity_transmission: context withheld (%s: %s)",
                      snap["status"], snap.get("reason"))
            return {}
        return snap["raw"]
    except Exception as e:  # noqa: BLE001
        log.warning("liquidity_transmission: unexpected error loading context (%s)", e)
        return {}


def _empty_plane(status: str, reason: str, provenance: Any = None,
                 freshness: Any = None) -> dict[str, Any]:
    """The inert plane payload: identity and status only, no readings."""
    return {
        "status": status,
        "reason": reason,
        "mode": glt_mode(),
        "authority": "shadow_advisory_inert",
        "direction_label": _UNKNOWN,
        "direction_vocabulary": "direction_label_enum",
        "quality": _UNKNOWN,
        "quality_vocabulary": "quality_enum",
        "magnitude": None,
        "magnitude_unit": None,
        "magnitude_z": None,
        "magnitude_z_unit": None,
        "coverage": None,
        "confidence": None,
        "confidence_kind": None,
        "breadth": None,
        "credit_impulse_global": None,
        "state_asof": None,
        "observed_at": (freshness or {}).get("observed_at") if isinstance(freshness, dict) else None,
        "observed_date": (freshness or {}).get("observed_date") if isinstance(freshness, dict) else None,
        "known_at": (freshness or {}).get("known_at") if isinstance(freshness, dict) else None,
        "age_days": (freshness or {}).get("age_days") if isinstance(freshness, dict) else None,
        "stale": True,
        "provenance": provenance,
        "signs_posture": False,
        "decision_effect": "none",
    }


def market_plane() -> dict[str, Any]:
    """Return the compact ``liquidity_transmission`` market_view plane payload.

    ADVISORY / SHADOW / INERT.  It carries the producer's own vocabularies and both
    magnitudes with their own unit strings; it never translates either into the
    market_view risk vocabulary (risk_off/neutral/risk_on) and never emits a bare
    magnitude.  Absent / invalid / stale → an inert payload that still names what it
    failed to read.
    """
    try:
        snap = _snapshot()
        if snap["status"] != _ST_PRESENT:
            return _empty_plane(snap["status"], str(snap.get("reason") or ""),
                                snap.get("provenance"), snap.get("freshness"))
        raw = snap["raw"]
        state = raw.get("state") or {}
        quality = raw.get("quality") or {}
        freshness = raw.get("freshness") or {}
        er = state.get("event_reference") or {}
        conf = quality.get("confidence") or {}

        return {
            "status": _ST_PRESENT,
            "reason": "ok",
            "mode": glt_mode(),
            "authority": "shadow_advisory_inert",
            # direction vocabulary — never quality words, never risk words
            "direction_label": _vocab(state.get("label"), _DIRECTION_VOCAB),
            "direction_vocabulary": "direction_label_enum",
            "direction_sign": int(er["direction"]) if isinstance(er.get("direction"), int) else None,
            # quality vocabulary — never direction words
            "quality": _vocab(er.get("quality"), _QUALITY_VOCAB),
            "quality_vocabulary": "quality_enum",
            "quality_status": quality.get("status"),
            # two magnitudes, each inseparable from its unit
            "magnitude": _as_float(er.get("magnitude")),
            "magnitude_unit": er.get("magnitude_unit"),
            "magnitude_z": _as_float(er.get("magnitude_z")),
            "magnitude_z_unit": er.get("magnitude_z_unit"),
            "magnitude_semantics": er.get("magnitude_semantics"),
            # coverage / data-lineage confidence (NOT a predictive probability)
            "coverage": _as_float(er.get("coverage")),
            "confidence": _as_float(conf.get("value")),
            "confidence_kind": conf.get("kind"),
            "breadth": _as_float(state.get("liquidity_breadth")),
            "monetary_coverage_ratio": _as_float(freshness.get("monetary_coverage_ratio")),
            "funding_coverage_ratio": _as_float(freshness.get("funding_coverage_ratio")),
            # null means insufficient comparable PIT coverage — never zero
            "credit_impulse_global": _as_float(state.get("credit_impulse_global")),
            "state_family": er.get("state_family"),
            "state_asof": state.get("asof"),
            "observed_at": snap["freshness"]["observed_at"],
            "observed_date": snap["freshness"]["observed_date"],
            "known_at": snap["freshness"]["known_at"],
            "age_days": snap["freshness"]["age_days"],
            "stale": False,
            "provenance": snap["provenance"],
            # structural guarantees, asserted on the payload itself
            "signs_posture": False,
            "decision_effect": "none",
        }
    except Exception as e:  # noqa: BLE001 — fail-soft: never raise into a build
        log.debug("liquidity_transmission: market_plane failed (%s)", e)
        return _empty_plane(_ST_ABSENT, f"market_plane error: {e}")


def target(symbol: str) -> dict[str, Any]:
    """Return ``{}`` — the v1 producer publishes no per-symbol targets.

    Its ``contract_scope`` is ``state_quality_freshness_only`` and
    ``meta.forbidden_authority`` includes allocation and trade.  A target is a later-wave
    field; deriving one from current state would fabricate authority the producer
    withholds, so this returns empty in every mode.
    """
    try:
        _ = str(symbol)
    except Exception:  # noqa: BLE001
        pass
    return {}


def opportunities(limit: int = 10) -> list[dict[str, Any]]:
    """Return ``[]`` — the v1 producer publishes no opportunity ranking.

    ``meta.forbidden_authority`` includes ``repricing_gap`` and ``transmission_curve``;
    ranking is exactly what this wave must not invent.  Empty in every mode.
    """
    try:
        _ = int(limit)
    except Exception:  # noqa: BLE001
        pass
    return []


def _inert_signals(mode: str, reason: str) -> dict[str, Any]:
    """The inert decision record — everything None/False, with the reason it is inert."""
    return {
        "candidacy": None,
        "tilt": None,
        "size_multiplier": None,
        "vote": None,
        "inert": True,
        "mode": mode,
        "reason": reason,
    }


def decision_signals(symbol: str) -> dict[str, Any]:
    """Return TYPED decision signals for ``symbol`` — inert for EVERY mode in W-LIQ.2.

    This is the chokepoint later waves widen.  Today the producer's contract scope carries
    no decision-bearing field, so escalating the ladder — even to ``vote`` — cannot change
    the result: the record is inert whether the mode is ``off`` or ``vote``.  The mode is
    reported so the runlog can see what was requested versus what was granted.
    """
    mode = glt_mode()
    try:
        _ = str(symbol)
        if not _mode_ge(mode, "shadow"):
            return _inert_signals(mode, "mode off")
        # Ladder rungs above shadow exist for later waves; the v1 contract scope grants
        # none of them any field to act on, so every rung resolves inert here.
        return _inert_signals(mode, f"contract_scope={_EXPECTED_CONTRACT_SCOPE}")
    except Exception:  # noqa: BLE001 — fail-soft: never raise
        return _inert_signals("off", "decision_signals error")


def audit_row() -> dict[str, Any]:
    """Return the perception/runlog row.  Flag-independent — always runs.

    ``status``: 'present' | 'absent' | 'stale' | 'invalid'.  Both clocks are reported
    separately so a runlog reader can see evidence availability and first-known apart from
    each other, and apart from the wrapper's ``generated_at``.
    """
    try:
        snap = _snapshot()
        fresh = snap.get("freshness") or {}
        prov = snap.get("provenance") or {}
        row: dict[str, Any] = {
            "status": snap["status"],
            "reason": snap.get("reason"),
            "mode": glt_mode(),
            "observed_at": fresh.get("observed_at"),
            "observed_date": fresh.get("observed_date"),
            "known_at": fresh.get("known_at"),
            "age_days": fresh.get("age_days"),
            "stale_after_days": _STALE_DAYS,
            "schema": prov.get("schema"),
            "producer_version": prov.get("producer_version"),
            "model_version": prov.get("model_version"),
            "data_version": prov.get("data_version"),
            "source_snapshot_hash": prov.get("source_snapshot_hash"),
            "state_label": None,
            "quality": None,
            "coverage": None,
            "confidence": None,
            "signs_posture": False,
            "decision_effect": "none",
        }
        raw = snap.get("raw")
        if snap["status"] == _ST_PRESENT and isinstance(raw, dict):
            state = raw.get("state") or {}
            er = state.get("event_reference") or {}
            conf = (raw.get("quality") or {}).get("confidence") or {}
            row["state_label"] = _vocab(state.get("label"), _DIRECTION_VOCAB)
            row["quality"] = _vocab(er.get("quality"), _QUALITY_VOCAB)
            row["coverage"] = _as_float(er.get("coverage"))
            row["confidence"] = _as_float(conf.get("value"))
        return row
    except Exception:  # noqa: BLE001
        return {
            "status": _ST_ABSENT, "reason": "audit_row error", "mode": "off",
            "observed_at": None, "observed_date": None, "known_at": None, "age_days": None,
            "stale_after_days": _STALE_DAYS, "schema": None, "producer_version": None,
            "model_version": None, "data_version": None, "source_snapshot_hash": None,
            "state_label": None, "quality": None, "coverage": None, "confidence": None,
            "signs_posture": False, "decision_effect": "none",
        }
