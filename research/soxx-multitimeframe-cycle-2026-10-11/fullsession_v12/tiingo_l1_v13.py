"""Pure consumer of *existing* Macro Data OS Tiingo BOATS research-view rows.

This module NEVER reads credentials, files, the Tiingo API, or starts a collector.
Caller supplies rows from the canonical source/receipt-verified L1 reader.
A qualified BOATS OHLC bar is NOT a quote fill or point-in-time backtest.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime,timedelta,time,timezone,date
from zoneinfo import ZoneInfo
import math,re
from fullsession import Bar,_aware,classify_session,trade_date,ET,UTC

SCHEMA="mastermind.tiingo.research_views.v2"
SHA=re.compile(r"^[0-9a-f]{64}$")
FALSE_FLAGS=("source_rights_admitted","pit_backtest_eligible",
             "canonical_price_basis_admitted","is_nbbo","executable_price_proven")

def _volume(row):
    value=row.get("vendor_volume")
    available=row.get("volume_available")
    if type(available) is not bool or available != (value is not None):
        raise ValueError("volume availability/provenance mismatch")
    if value is None:return None
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError("invalid vendor volume")
    if value<0 or value>=2**53 or int(value)!=value:
        raise ValueError("imprecise, noninteger or unsafe share volume")
    return int(value)

def l1_to_bars(rows,*,symbol,expected_sha,receipt_id,observed_before_utc,
               minutes=1,basis="raw"):
    """No cross-receipt or mixed-vintage normalization, no inferred quote data."""
    if not isinstance(rows,list) or not rows:raise ValueError("empty L1 research view")
    if not isinstance(symbol,str) or symbol!=symbol.upper() or not symbol:
        raise ValueError("explicit uppercase ticker required")
    if not (isinstance(expected_sha,str) and SHA.fullmatch(expected_sha)
            and isinstance(receipt_id,str) and SHA.fullmatch(receipt_id)):
        raise ValueError("receipt and source digest required")
    if basis!="raw":raise ValueError("Tiingo BOATS archive split basis unverified")
    if minutes not in (1,5,15,30,60):raise ValueError("invalid source grain")
    cutoff=_aware(observed_before_utc)
    capture=None;bars=[];stamps=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError("invalid L1 row")
        if (row.get("source_vendor")!="tiingo" or
            row.get("dataset_source")!="boats-bars" or
            row.get("source_view_schema")!=SCHEMA):
            raise ValueError("not a receipt-verified Tiingo BOATS historical L1 row")
        if row.get("source_sha256")!=expected_sha or row.get("source_receipt_id")!=receipt_id:
            raise ValueError("mixed source body/receipt: do not splice historical vintages")
        if (row.get("venue")!="BOATS" or row.get("venue_scope")!="single_ats"
            or row.get("session")!="overnight"):
            raise ValueError("wrong venue or market session")
        if any(row.get(flag) is not False for flag in FALSE_FLAGS):
            raise ValueError("unreviewed PIT, rights, source or fill promotion")
        if row.get("vendor_historical_availability")!="UNVERIFIED":
            raise ValueError("unexpected source historical-availability claim")
        if row.get("ticker_vendor","").upper()!=symbol:
            raise ValueError("symbol/receipt identity mismatch")
        if row.get("requested_resample_frequency")!=f"{minutes}min":
            raise ValueError("vendor requested grain disagrees with research grain")
        observed=_aware(row["source_observed_at_utc"])
        if observed>cutoff:raise ValueError("source observed after requested capture cutoff")
        if capture is None:capture=observed
        elif capture!=observed:raise ValueError("mixed capture vintages")
        at=_aware(row["bar_at_vendor"])
        if row.get("source_date_label")!=str(row["bar_at_vendor"])[:10]:
            raise ValueError("vendor date label inconsistent with source timestamp")
        if at in stamps:raise ValueError("duplicate vendor bar start")
        stamps.add(at)
        b=Bar(symbol,at,minutes,row["vendor_open"],row["vendor_high"],
              row["vendor_low"],row["vendor_close"],_volume(row),"tiingo-boats","raw")
        if classify_session(b.utc)!="overnight":
            raise ValueError("source row outside eligible BOATS session")
        bars.append(b)
    bars.sort(key=lambda b:b.utc)
    for old,new in zip(bars,bars[1:]):
        if new.utc<old.end:raise ValueError("overlapping vendor bar")
    return bars,dict(
        source_sha256=expected_sha,receipt_id=receipt_id,
        vendor="tiingo",venue="BOATS",venue_scope="single_ats",
        first_observed_at=capture.isoformat(),rows=len(bars),
        pit_backtest_eligible=False,historical_quote_fills_proven=False,
        redistribution_approved=False,full_24h_session_proven=False,
        normalized_output_kind="RETROSPECTIVE_BAR_ONLY")

def audit_overnight_nights(bars,*,night_starts_et):
    """8-hour night denominator; *not* 24h coverage, calendar or actual fill proof."""
    if not isinstance(night_starts_et,(tuple,list)) or not night_starts_et:
        raise ValueError("specific nights required")
    dates=[]
    for value in night_starts_et:
        if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
            raise ValueError("ET night date required")
        d=date.fromisoformat(value)
        if d in dates:raise ValueError("duplicate overnight date")
        dates.append(d)
    if any(b.minutes!=1 or b.source!="tiingo-boats" for b in bars):
        raise ValueError("overnight minute input only")
    out=[]
    for d in sorted(dates):
        start=datetime.combine(d,time(20,0),ET).astimezone(UTC)
        end=datetime.combine(d+timedelta(days=1),time(4,0),ET).astimezone(UTC)
        expected=int((end-start).total_seconds()//60)
        if expected<=0:raise ValueError("invalid overnight clock")
        qualified={b.utc for b in bars if start<=b.utc<end}
        expected_starts={start+timedelta(minutes=i) for i in range(expected)}
        unknown=qualified-expected_starts
        if unknown:raise ValueError("off-minute source timestamp")
        missing=expected_starts-qualified
        out.append(dict(night_start_et=d.isoformat(),observed_minutes=len(qualified),
            expected_minutes=expected,missing_minutes=len(missing),
            complete_overnight=not missing and len(qualified)==expected,
            complete_24h_proven=False,marketable_quote_replay_proven=False))
    return out

def resample_complete_30m(bars):
    """Completeness-gated 1m->30m BOATS bars, never forward-fills missing minutes."""
    if any(b.minutes!=1 or b.source!="tiingo-boats" or b.basis!="raw" for b in bars):
        raise ValueError("only raw Tiingo minute BOATS input accepted")
    if len({b.symbol for b in bars})>1:raise ValueError("mixed instruments")
    grouped=defaultdict(list)
    for b in bars:
        if b.utc.second or b.utc.microsecond:raise ValueError("unaligned minute")
        if classify_session(b.utc)!="overnight":raise ValueError("daytime source")
        epoch=int(b.utc.timestamp())
        slot=datetime.fromtimestamp(epoch//1800*1800,tz=UTC)
        grouped[slot].append(b)
    completed=[];partial=0
    for start,chunk in sorted(grouped.items()):
        xs=sorted(chunk,key=lambda x:x.utc)
        expected={start+timedelta(minutes=i) for i in range(30)}
        got={x.utc for x in xs}
        if len(xs)!=30 or got!=expected:
            partial+=1
            continue
        if len({trade_date(x.utc) for x in xs})!=1:
            raise ValueError("bucket crosses trade date")
        vol=sum(x.volume for x in xs) if all(x.volume is not None for x in xs) else None
        completed.append(Bar(xs[0].symbol,start,30,xs[0].open,
          max(x.high for x in xs),min(x.low for x in xs),xs[-1].close,
          vol,"tiingo-boats","raw"))
    return completed,dict(observed_one_minute_bars=len(bars),
        source_buckets=len(grouped),complete_30m=len(completed),
        skipped_partial_30m=partial,synthetic_candles_created=0,
        full_24h_session_proven=False)