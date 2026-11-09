"""Compact immutable research delivery: selected tables, paired diagnostics, provenance."""
import csv, hashlib, itertools, json, random, statistics, sys
from pathlib import Path
import study_v7 as s

def paired_interval(rows, seed=20261009):
    groups={}
    for r in rows:groups.setdefault(r['entry'][:7],[]).append(float(r['lift']))
    xs=list(groups.values());rng=random.Random(seed);draws=[]
    if not xs:return None
    for _ in range(10000):
        values=[v for g in rng.choices(xs,k=len(xs)) for v in g]
        draws.append(statistics.mean(values))
    draws.sort();score=sum(sum(g) for g in xs)
    exact=[sum(sign*sum(g) for sign,g in zip(signs,xs)) for signs in itertools.product([-1,1],repeat=len(xs))]
    return dict(months=len(xs),events=sum(len(g) for g in xs),changed=sum(abs(v)>1e-9 for g in xs for v in g),
                mean=statistics.mean([v for g in xs for v in g]),bootstrap95=[draws[250],draws[9749]],
                signflip_one_sided=sum(x>=score-1e-12 for x in exact)/len(exact),
                qualification='Retrospective, unadjusted descriptive entry-month resampling; not independent acceptance.')

def run(root):
    root=Path(root);out=root/'delivery'
    if out.exists():raise ValueError('delivery exists')
    out.mkdir();result=json.loads((root/'run1/results.json').read_text());grid=result['grid'];ts=result['rows']
    main=[];plans=['fixed2','slow_p0.25','guard_p0.25','guard_p0.5','reentry_break2_w13_p0.25']
    for plan in plans:
        by={(r['phase'],r['fee']):r for r in grid if r['label']=='3H_1H_pivot' and r['sample']=='native' and r['plan']==plan}
        a,b,z=by['prior',5],by['year',5],by['year',15]
        main.append(dict(plan=plan,n=b['resolved'],win=b['win'],mean=b['mean'],cum=b['cum'],mdd=b['mdd'],median=b['median'],
          prior_n=a['resolved'],prior_mean=a.get('mean'),prior_without_best=a.get('without_best'),stress15_mean=z.get('mean'),stress15_win=z.get('win'),without_best=b.get('without_best')))
    s.old.write_csv(out/'full10_comparison.csv',main)
    retry=[r for r in grid if r['label']=='3H_1H_pivot' and r['sample']=='native' and r['phase']=='year' and r['fee']==5 and ('reentry_' in r['plan'] or r['plan']=='guard_p0.25')]
    s.old.write_csv(out/'reentry_comparison.csv',retry)
    selected=[r for r in ts if r['label']=='3H_1H_pivot' and r['sample']=='native' and r['fee']==5 and r['phase']=='year']
    maps={p:{r['entry_ET']:r for r in selected if r['plan']==p} for p in plans}
    ledger=[]
    for key,base in maps['guard_p0.25'].items():
        row=dict(entry=key,guard_exit=base['exit_ET'],reason=base['reason'],status=base['status'])
        for p in plans:row[p]=maps[p][key].get('net_pct')
        ledger.append(row)
    s.old.write_csv(out/'trade_ledger.csv',ledger)
    pair=list(csv.DictReader((root/'validation/paired_guard.csv').open()))
    paired=paired_interval([r for r in pair if r['label']=='3H_1H_pivot' and float(r['fraction'])==.25 and r['phase']=='year'])
    time=list(csv.DictReader((root/'validation/time_controls.csv').open()))
    s.old.write_csv(out/'time_controls.csv',time)
    time_next=list(csv.DictReader((root/'validation/time_nextopen.csv').open()))
    s.old.write_csv(out/'time_nextopen.csv',time_next)
    timer_trades=list(csv.DictReader((root/'validation/time_nextopen_trades.csv').open()))
    timer52={r['entry_ET']:r for r in timer_trades if float(r['horizon'])==52 and r['phase']=='year' and r['status']=='resolved'}
    timed_pairs=[dict(entry=k,lift=float(timer52[k]['net_pct'])-r['net_pct']) for k,r in maps['guard_p0.25'].items() if k in timer52]
    timer_paired=paired_interval(timed_pairs)
    transfers=[{k:r.get(k) for k in ['label','plan','phase','candidates','resolved','status_counts','mean','win','cum','mdd']} for r in grid
               if r['sample']=='native' and r['fee']==5 and r['plan'] in ['slow_p0.25','guard_p0.25']]
    s.old.write_csv(out/'broader_entry_audit.csv',transfers)
    reentries=[{k:r.get(k) for k in ['entry_ET','plan','status','first_net','reentry_ET','reentry_quantity','additional_gain','net_pct','exit_ET']}
               for r in selected if r.get('reentered') and 'p0.25' in r['plan']]
    s.old.write_csv(out/'reentry_trades.csv',reentries)
    evidence=dict(phase='v7 exit audit and one-reentry test',window=['2025-10-09','2026-10-08'],prior=['2024-12-16','2025-10-08'],
        current_data_are_not_unseen=True,source_sha256=hashlib.sha256((root/'inputs/rth_original.json').read_bytes()).hexdigest(),
        common65_reproduced=True,original_cohort_size=8,restored_native_cohort_size=10,
        restored_entries=['2025-11-05T10:30:00-05:00','2026-02-02T09:30:00-05:00'],
        main_plan_definitions=18,time_control_definitions=14,next_open_time_definitions=7,guard_paired=paired,timer52_paired=timer_paired,
        actual_validation=json.loads((root/'validation/proof.json').read_text()),
        no_live_trades=True,no_production_changes=True,no_overnight_feed_used=True,
        independent_quotes_and_tick_execution_unverified=True)
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2))
    manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir() if p.is_file()}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    print('MAIN',json.dumps(main))
    print('PAIRED',json.dumps(paired))
    print('TIMER_PAIRED',json.dumps(timer_paired))
    print('DELIVERY',json.dumps(manifest))

if __name__=='__main__':run(sys.argv[1])