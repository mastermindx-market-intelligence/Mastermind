#!/usr/bin/env python3
"""Read-only Mastermind research import of already-acquired BOATS + daytime history.

No network access, credentials, trading, production configuration or live vendor writes.
A bar contact/quote is not an executed order. No missing candle is forward-filled.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
import argparse,csv,hashlib,json,sys
from fullsession import (
    ET,Bar,normalize_alpaca,normalize_tiingo,normalize_terminal_display,
    stitch,aggregates,trade_date,coverage,provenance_summary,Quote)


def require_json(path):
    p=Path(path)
    if not p.is_file():raise ValueError(f'required input missing: {p.name}')
    data=p.read_bytes()
    return json.loads(data),hashlib.sha256(data).hexdigest()


def parse_day(payload, symbol, interval, basis, fmt):
    if fmt!='terminal':raise ValueError('only exact Terminal display-epoch daytime rows supported')
    rows=payload['bars'] if isinstance(payload,dict) and 'bars' in payload else payload
    return normalize_terminal_display(rows,symbol,interval,basis=basis,source='massive')


def parse_night(payload,symbol,interval,basis,fmt,evidence,tiingo_basis_attested=False):
    if evidence!='available':raise ValueError('night source provided but entitlement/coverage evidence is not available')
    if fmt=='alpaca':return normalize_alpaca(payload,symbol,interval,basis=basis)
    if fmt=='tiingo':
        if basis=='split' and not tiingo_basis_attested:
            raise ValueError('Tiingo historical split basis unverified; do not mislabel adjustment')
        return normalize_tiingo(payload,symbol,interval,basis=basis)
    if fmt=='terminal':
        rows=payload['bars'] if isinstance(payload,dict) and 'bars' in payload else payload
        if isinstance(payload,dict):
            if payload.get('source') not in ('alpaca-boats','tiingo-boats'):
                raise ValueError('Terminal payload does not establish licensed BOATS source')
            if payload.get('status')!='available':raise ValueError('Terminal overnight status not available')
            source=payload['source']
        else:raise ValueError('Terminal payload must include BOATS source and status evidence')
        return normalize_terminal_display(rows,symbol,interval,basis=basis,source=source,overnight_evidence='available')
    raise ValueError('unknown overnight input format')


def collect_quote_rows(payload,symbol):
    if not isinstance(payload,dict) or 'quotes' not in payload or not isinstance(payload['quotes'],dict):
        raise ValueError('expected archived Alpaca quotes envelope')
    arr=payload['quotes'].get(symbol,[])
    if not isinstance(arr,list):raise ValueError('bad quote list')
    out=[]
    for item in arr:
        out.append(Quote(symbol,datetime.fromisoformat(item['t'].replace('Z','+00:00')),
             float(item['bp']),float(item['ap']),int(item['bs']),int(item['as']),'alpaca-boats-historical'))
    return out


def expected_dates(args,observed):
    if args.calendar_file:
        c,_=require_json(args.calendar_file)
        if not isinstance(c,dict) or not isinstance(c.get('trading_days'),list):
            raise ValueError('calendar must supply explicit confirmed trading_days array')
        actual=[date.fromisoformat(d) for d in c['trading_days']]
        if not actual or len(actual)!=len(set(actual)):raise ValueError('empty or duplicate calendar dates')
        return sorted(actual),'declared_exchange_calendar'
    return sorted(observed),'observed_only_no_absent_date_inference'


def run(args):
    if args.symbol!=args.symbol.upper() or not args.symbol:raise ValueError('uppercase symbol required')
    if args.interval not in (5,15,30,60):raise ValueError('source grain must be 5/15/30/60 minutes')
    if args.basis not in ('split','raw'):raise ValueError('explicit adjustment basis required')
    if args.overnight_file is None and args.overnight_evidence=='available':
        raise ValueError('cannot claim available overnight history without a source artifact')
    day,day_sha=require_json(args.daytime_file)
    d=parse_day(day,args.symbol,args.interval,args.basis,args.daytime_format)
    source_hashes={'daytime':day_sha};n=[]
    if args.overnight_file:
        night,night_sha=require_json(args.overnight_file)
        n=parse_night(night,args.symbol,args.interval,args.basis,args.overnight_format,
            args.overnight_evidence,args.tiingo_basis_attested)
        source_hashes['overnight']=night_sha
    merged=stitch(d,n)
    indicators={120:aggregates(merged,120),180:aggregates(merged,180),240:aggregates(merged,240)}
    days=set(trade_date(x.utc) for x in merged)
    expected,calendar_type=expected_dates(args,days)
    complete_days=[];unverified=[]
    for dday in expected:
        start=datetime.combine(dday-timedelta(days=1),time(20,0),tzinfo=ET).astimezone(timezone.utc)
        # 24h cycle may contain non-trading days/holidays; calendar must be supplied externally.
        c=coverage(merged,start,args.interval,24*60//args.interval)
        if c['complete']:complete_days.append(dday.isoformat())
        else:unverified.append({'trade_date':dday.isoformat(),**c})
    # Counts only for complete, fully observed 24h trade dates. Never report
    # partial daytime bars as an accepted 24-hour indicator stream.
    complete_agg={}
    for tf,ag in indicators.items():
        complete_agg[str(tf)]=sum(a['complete'] and a['trade_date'] in complete_days for a in ag)
    qn=0
    if args.quotes_file:
        qp,qhash=require_json(args.quotes_file)
        q=collect_quote_rows(qp,args.symbol)
        qn=len(q);source_hashes['quotes']=qhash
    ready=bool(expected) and len(complete_days)==len(expected) and bool(n)
    report={
        'symbol':args.symbol,'source_timeframe_min':args.interval,
        'window_basis':args.basis,'overnight_evidence':args.overnight_evidence,
        'calendar_authority':calendar_type,
        'coverage':{'daytime_bars':len(d),'overnight_bars':len(n),'combined_bars':len(merged),
          'observed_trade_dates':len(days),'expected_trade_dates':len(expected),
          'complete_full_trading_days':len(complete_days),
          'unverified_day_count':len(unverified),'unverified_sample':unverified[:12]},
        'complete_aggregate_bars':complete_agg,
        'mixed_session_aggregates':{str(tf):sum(x['complete'] and x['mixed'] and x['trade_date'] in complete_days for x in ag) for tf,ag in indicators.items()},
        'full_session_research_ready':ready,
        'backtest_eligible_full_year':ready and calendar_type=='declared_exchange_calendar' and len(expected)>=180,
        'quote_execution_replay_ready':False,
        'historical_quote_rows':qn,'historical_quote_fills_claimed':0,
        'source_sha256':source_hashes,
        'limitations':['Historical Tiingo BOATS REST supplies bars, not past order book',
         'Alpaca or other licensed historical quote history required for quote marketability; no fills inferred',
         'True 20:00–04:00 market sessions and 04:00–20:00 daytime are disjoint, never forward-filled',
         'No calendar-based full-year eligibility without a verified exchange trading-day calendar',
         'Split adjustment parity must be independently verified before joint use',
         'Indicators and performance NOT calculated by this importer']}
    out=Path(args.out)
    if out.exists():raise ValueError('output already exists: never overwrite a prior research carrier')
    out.mkdir(parents=True)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    with (out/'normalized_bars.csv').open('w',newline='') as fp:
        w=csv.writer(fp);w.writerow(['symbol','timestamp_utc','trade_date','session_source','minutes','open','high','low','close','volume','basis'])
        for b in merged:
            w.writerow([b.symbol,b.utc.isoformat(),trade_date(b.utc),b.source,b.minutes,b.open,b.high,b.low,b.close,b.volume,b.basis])
    with (out/'aggregate_coverage.csv').open('w',newline='') as fp:
        w=csv.writer(fp);w.writerow(['tf_min','trade_date','utc_start','utc_end','complete','observed','expected','sessions','sources'])
        for tf,ag in indicators.items():
            for x in ag:
                w.writerow([tf,x['trade_date'],x['start'].isoformat(),x['end'].isoformat(),x['complete'],
                            x['observed'],x['expected'],'+'.join(x['sessions']),'+'.join(x['source_labels'])])
    return report


def build_parser():
    p=argparse.ArgumentParser(description='Read-only, fail-closed BOATS+Terminal bars research importer')
    p.add_argument('--symbol',required=True);p.add_argument('--daytime-file',required=True)
    p.add_argument('--daytime-format',choices=['terminal'],default='terminal')
    p.add_argument('--overnight-file');p.add_argument('--overnight-format',choices=['alpaca','tiingo','terminal'],default='alpaca')
    p.add_argument('--overnight-evidence',choices=['available','empty','not_configured','unavailable'],default='not_configured')
    p.add_argument('--quotes-file');p.add_argument('--interval',type=int,default=30)
    p.add_argument('--basis',choices=['raw','split'],required=True)
    p.add_argument('--tiingo-basis-attested',action='store_true')
    p.add_argument('--calendar-file');p.add_argument('--out',required=True)
    return p

if __name__=='__main__':
    try:
        out=run(build_parser().parse_args())
        print(json.dumps({'status':'research_ingestion_complete','symbol':out['symbol'],
            'full_session_research_ready':out['full_session_research_ready'],
            'backtest_eligible_full_year':out['backtest_eligible_full_year'],
            'coverage':out['coverage']},indent=2))
    except (ValueError,KeyError,TypeError,FileNotFoundError) as exc:
        print('IMPORT_REFUSED:',str(exc),file=sys.stderr)
        sys.exit(2)