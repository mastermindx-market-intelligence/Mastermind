"""Targeted, named mutation controls. This is not exhaustive mutation coverage."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parent
source=ROOT/'compiled/auctionContext.js'
original=source.read_text()
checks=[
 ('future_parent_leak','if (c.start < from || c.start + seconds > to)','if (c.start < from)','future_extremes_do_not_change_past_profile'),
 ('last_row_as_clock','const end = Math.floor(r.decisionAt / r.analysisSeconds) * r.analysisSeconds;',
  'const end = parentFeed && parentFeed.rows.length ? parentFeed.rows[parentFeed.rows.length-1].start + r.analysisSeconds : Math.floor(r.decisionAt / r.analysisSeconds) * r.analysisSeconds;',
  'missing_trailing_bars_not_silently_shifted'),
 ('ignore_venue','identityKeys.every(k => a[k] === b[k])',"identityKeys.every(k => k === 'venue' || a[k] === b[k])",'child_venue_mismatch_not_silently_mixed'),
 ('ignore_vintage','identityKeys.every(k => a[k] === b[k])',"identityKeys.every(k => k === 'vintage' || a[k] === b[k])",'child_vintage_mismatch_not_silently_mixed'),
 ('future_observation_leak','if (c.observedAt > r.decisionAt)','if (false)','late_observation_does_not_become_eligible'),
 ('silently_choose_conflicting_duplicate','if (old && !sameCandle(old, c))','if (false)','conflicting_selected_bars_refused'),
 ('initial_doji_neutral','let previous = null, sign = null;','let previous = null, sign = 0;','unclassified_initial_dojis_remain_unknown'),
 ('ignore_child_volume_mismatch','!equal(p.volume, volume)','false','parent_volume_reconciles_with_children'),
 ('unweighted_balance','balanceDeltaPct: 100 * (d / volume)',
  'balanceDeltaPct: dd.reduce((s,x,i)=>s+100*x/volumes[i],0)/dd.length','balance_uses_volume_not_average_percentages'),
 ('same_cutoff_bins_change_not_stale','s.construction.bins === r.bins','true','same_cutoff_different_bins_is_stale'),
 ('same_cutoff_knowledge_change_not_stale','s.evidenceMode === r.evidenceMode','true','same_cutoff_different_knowledge_mode_is_stale'),
 ('unsafe_normalization','latestDeltaPct: 100 * (dd[dd.length - 1] / latestVolume)',
  'latestDeltaPct: (100 * dd[dd.length - 1]) / latestVolume','normalized_delta_does_not_overflow'),
 ('nonfinite_profile_unchecked','if (!finiteProfile)','if (false)','nonfinite_profile_output_refused'),
 ('silently_clamped_small_fraction','r.valueAreaFraction >= 0.01','r.valueAreaFraction > 0','subminimum_value_area_refused')
]
results=[]
for name,before,after,expected in checks:
 assert original.count(before)==1,(name,original.count(before))
 folder=ROOT/'mutants'/name;folder.mkdir(parents=True,exist_ok=True)
 (folder/'auctionContext.js').write_text(original.replace(before,after))
 shutil.copyfile(ROOT/'compiled/terminal_analytics_pinned.js',folder/'terminal_analytics_pinned.js')
 reportpath=folder/'report.json'
 env={**os.environ,'TARGET_MODULE':str(folder/'auctionContext.js'),'REPORT_PATH':str(reportpath)}
 completed=subprocess.run(['node','test_context.cjs'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
 if not reportpath.exists():raise RuntimeError('Harness error, not a caught mutant: '+name+' '+completed.stderr)
 report=json.loads(reportpath.read_text());failed=[t['name']for t in report['tests']if t['status']=='FAIL']
 control=next(t for t in report['tests']if t['name']=='exact_existing_profile_source_blob')
 results.append({'name':name,'expected_assertion':expected,'caught_by_expected_assertion':expected in failed,
  'unchanged_source_control_passed':control['status']=='PASS','exit':completed.returncode,'failed_cases':failed})
assert source.read_text()==original
report={'status':'PASS'if all(x['caught_by_expected_assertion']and x['unchanged_source_control_passed']for x in results)else'FAIL',
 'mutants':len(results),'caught':sum(x['caught_by_expected_assertion']for x in results),'results':results,
 'scope':'14 selected forbidden-behavior mutations, not exhaustive code coverage or proof of alpha.',
 'base_compiled_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
(ROOT/'results/mutation_report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2));raise SystemExit(0 if report['status']=='PASS'else 1)
