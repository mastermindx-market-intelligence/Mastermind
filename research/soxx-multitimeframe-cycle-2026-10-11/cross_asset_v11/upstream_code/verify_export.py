"""Verify frozen outputs and export compact reproducible evidence. No data fetch."""
import base64,csv,hashlib,io,json,statistics,sys,zipfile
from pathlib import Path
import frozen_audit as a

def run(root):
    root=Path(root);out=root/'delivery';out.mkdir(exist_ok=False)
    allres={sym:json.loads((root/sym/'results.json').read_text()) for sym in ['SOXX','SMH','QQQ']}
    ctx=a.context_from_source(root/'inputs/rth_original.json');raw=ctx['raw']
    zero=a.shifted_bars(raw,180,ctx['closes'],0)
    keys=['start','end','open','high','low','close','volume','complete','firstidx','lastidx']
    assert len(zero)==len(ctx['high'][180])
    for x,y in zip(zero,ctx['high'][180]):assert all(x[k]==y[k] for k in keys)
    prefix_cases=prefix_bars=0
    for offset in [0,60,120]:
        full=a.shifted_bars(raw,180,ctx['closes'],offset)
        lookup={(x['start'],x['end']):x for x in full}
        for cut in [300,1000,2000,3200]:
            prefix_cases+=1
            short=a.shifted_bars(raw[:cut],180,ctx['closes'],offset)
            for x in short:
                if not x['complete']:continue
                y=lookup[x['start'],x['end']]
                assert all(x[k]==y[k] for k in keys);prefix_bars+=1
    oldroot=Path('/Users/mini4/.local/share/mastermind-review-artifacts/SOXX_EXIT_VALIDATION_20261009_v7')
    old=list(csv.DictReader((oldroot/'delivery/full10_comparison.csv').open()))
    baseline_checks=0
    for row in old:
        if row['plan'] not in ['fixed2','slow_p0.25','guard_p0.25','guard_p0.5']:continue
        now=next(r for r in allres['SOXX']['summary'] if r['variant']=='frozen' and r['phase']=='year' and r['plan']==row['plan'])
        for key in ['mean','win','cum','mdd']:
            assert abs(float(row[key])-now[key])<1e-10;baseline_checks+=1
    fields=['symbol','variant','plan','phase','candidates','resolved','mean','win','median','cum','mdd','without_best']
    def write(name,rows):
        a.v7.old.write_csv(out/name,rows)
    write('SOXX_timing_risk.csv',[{k:r.get(k) for k in fields} for r in allres['SOXX']['summary']])
    write('peer_transfer.csv',[{k:r.get(k) for k in fields} for sym in ['SMH','QQQ'] for r in allres[sym]['summary']])
    for source,name in [('entry_fills/summary.csv','entry_fill_stress.csv'),('intrabar/summary.csv','intrabar_drawdown.csv')]:
        rows=list(csv.DictReader((root/source).open()))
        write(name,[{k:r.get(k) for k in ['plan','bps','route','order','phase','candidates','resolved','mean','win','cum','mdd']} for r in rows])
    write('session_gaps.csv',[dict(symbol=sym,**g) for sym in allres for g in allres[sym]['audit']['gaps']])
    write('entry_timing_ledger.csv',[{k:t.get(k) for k in ['variant','plan','phase','origin_entry_ET','entry_ET','exit_ET','status','net_pct','reason']} for t in allres['SOXX']['trades'] if t['phase']=='year' and t['variant'] in ['frozen','delay_1bar','delay_2bars'] and t['plan']=='guard_p0.25'])
    ret={};entrydays={};dependence={}
    import math
    for sym in allres:
        path=root/'inputs'/('rth_original.json' if sym=='SOXX' else sym+'_60m.json')
        rs=a.n.b.load_rth(path)[0]
        ret[sym]={r['start']:math.log(r['close']/r['open']) for r in rs if r['day']>=a.n.b.YEAR_START}
        entrydays[sym]={t['entry_ET'][:10] for t in allres[sym]['trades'] if t['phase']=='year' and t['variant']=='frozen' and t['plan']=='guard_p0.25'}
    for sym in ['SMH','QQQ']:
        ix=sorted(ret['SOXX'].keys()&ret[sym].keys())
        dependence[sym]=dict(matched_bars=len(ix),open_to_close_return_correlation=statistics.correlation([ret['SOXX'][i] for i in ix],[ret[sym][i] for i in ix]),shared_entry_days=len(entrydays['SOXX']&entrydays[sym]),own_entry_days=len(entrydays[sym]))
    proof=json.loads((root/'intrabar/proof.json').read_text())
    evidence=dict(study='v8 frozen strategy robustness; no optimized winner selected',window=[a.n.b.YEAR_START,a.n.b.YEAR_END],
      raw_sources={sym:d['source_sha256'] for sym,d in allres.items()},
      source_audits={sym:{k:v for k,v in d['audit'].items() if k!='gaps'} for sym,d in allres.items()},
      remote_checks=dict(zero_anchor_bars=len(zero),prefix_cases=prefix_cases,prefix_complete_bars=prefix_bars,baseline_metric_matches=baseline_checks,independent_execution=proof),
      code_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['frozen_audit.py','intrabar_audit.py','fill_stress.py']},
      dependence=dependence,retrospective=True,source_calendar='Vendor tradingPeriods; selected early-close dates checked against NYSE. Not an independent complete calendar proof.',
      no_overnight_data=True,session_gaps_not_imputed=True,full_prior_portfolio_unresolved=True)
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2))
    manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir() if p.is_file()}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    zpath=root/'delivery.zip'
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(out.iterdir()):z.write(p,p.name)
    encoded=base64.b64encode(zpath.read_bytes()).decode();(root/'delivery.b64').write_text(encoded)
    print('VERIFICATION',json.dumps(evidence['remote_checks']))
    print('TRANSFER',json.dumps(dict(zip_bytes=zpath.stat().st_size,base64_bytes=len(encoded),sha256=hashlib.sha256(zpath.read_bytes()).hexdigest())))
if __name__=='__main__':run(sys.argv[1])