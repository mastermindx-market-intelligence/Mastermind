"""Preserve this completed offline research phase without modifying prior archives."""
from pathlib import Path
import ast,hashlib,json,shutil,zipfile
root=Path('/private/tmp/soxx_exit_reentry_20261009_v7')
dest=Path('/Users/mini4/.local/share/mastermind-review-artifacts/SOXX_EXIT_VALIDATION_20261009_v7')
archive=dest.with_suffix('.zip')
assert not dest.exists() and not archive.exists(),'reconcile existing archive before replay'
expected={'reentry_core.py':'c19e569b97e4564e7312bfe832ae7859e741025cace16e6607b0024cd2b36a79','study_v7.py':'267b587b1bbc64a79613de6876c4deecd701c12c819af03bf2cc13e4f73f4303','validate_v7.py':'ef3950e15a7030c6d56cc701f9b64271660b1d8f582fec328a44be0385513730','time_nextopen.py':'01deb0243d83b7f88e56678215dd91d562fecff7c08deeb5bdd9276aa5163812','export_v7.py':'da8a5165d09ea1142ef971129534f4cd70023dc550bc239616ccb0949969e6af'}
for name,want in expected.items():assert hashlib.sha256(ast.dump(ast.parse((root/name).read_text())).encode()).hexdigest()==want
for name,info in json.loads((root/'delivery/MANIFEST.json').read_text()).items():
 assert hashlib.sha256((root/'delivery'/name).read_bytes()).hexdigest()==info['sha256']
shutil.copytree(root,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
checkpoint={'mission':'SOXX granular-exit validation, full native-entry restoration, and one bounded re-entry after early protection',
 'protected_sha':'326c8469a21d7f50fc9ecb1848196bf1c6e66685',
 'scope':'Offline research artifacts only; no trading, authentication, production, GitHub changes or background service',
 'completed':['Reproduced common eight-entry baseline','Restored all ten main-rule entries using actual-exit path audit','Three bounded re-entry definitions at two windows and two partial sizes','Broader entry-family and unresolved-path audit','Time exits with close versus next-open execution','Truncated-path validation and selected-data export'],
 'main_native_entries':10,'prior_entries':5,'source_sha256':'ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720',
 'main_plan_definitions':18,'period_summaries':432,'simulation_rows':6862,'time_controls':14,'next_open_time_controls':7,
 'main_finding':'Quarter-sale early guard: full10 mean4.184740715%, win70%, recorded MDD-4.664002136%; eight-entry5.30%/-2.51% is subset only.',
 'reentry_finding':'Only two triggered main re-entry legs, both lost; do not add this automatic re-entry to frozen candidate.',
 'timer_finding':'52 observed RTH hours plus next-open exit averaged4.335935162% on same10; paired advantage0.151194446pp is not established; simple holding-time explanation remains viable.',
 'broader_audit':'Any-HTF13 episodes/12 resolved; ungated45/41 resolved. Whole-stream cum/MDD omitted where any outcome is unobserved or right-censored.',
 'statistical_qualification':'Already-inspected data; no independent forward or 24h proof; three guard improvements among10 events in9 entry-month clusters.',
 'verification':{'local_unit_tests_passed':21,'local_test_surface':'conversation container; AST equality to executed remote new modules, not a remote unittest receipt','remote_truncated_path_replays':269,'remote_reentry_budget_cases':4,'local_summary_arithmetic_checks':20,'new_module_AST_parity':expected},
 'all_started_research_processes_completed':True,'pending_effects':[],
 'DO_NOT_REDO':'Preserve original v6 and v7 data/results. Do not rank former eight-entry result as full10. Do not rerun completed frozen grids without relevant data/rule invalidator. Do not count reused configurations as independent trades.',
 'next_action':'Validate supplied longer subhourly/BOATS history and compare the frozen guard+slow and guard+52h timed exits with matched horizons. Fresh independent observations required before edge acceptance.',
 'remaining_obligations':['BOATS/full-session history not supplied','Independent market-price and actual spread/tick proof absent','Statistical superiority not established'],
 'actual_stop_reason':'Bounded requested continuation audit and replay completed; broader research mission remains unproven, not a daemon.',
 'mode_evidence':'User mode not independently attested; no runtime or model quota claim',
 'artifact_owner':str(dest),'no_background_execution':True}
(dest/'CHECKPOINT.json').write_text(json.dumps(checkpoint,indent=2))
(dest/'README.md').write_text('# SOXX exit validation v7\n\nComplete remote research snapshot. Inputs and full replay outputs included.\n\nStart with CHECKPOINT.json and delivery/full10_comparison.csv. Main result uses all ten original entries, not the earlier future-window-filtered eight. The same inspected history is not fresh out-of-sample evidence. No automatic trading integration exists.\n\nReproduction into a NEW workspace: keep Python modules in one directory with inputs/, run study_v7.py inputs run1, then validate_v7.py inputs ., time_nextopen.py ., and export_v7.py . . Refuse existing output names; never overwrite this sealed source. The conversation package contains detailed rerun instructions and 21 locally executed tests.\n')
manifest={str(p.relative_to(dest)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(dest.rglob('*')) if p.is_file()}
(dest/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
for name,info in manifest.items():assert hashlib.sha256((dest/name).read_bytes()).hexdigest()==info['sha256']
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(dest.rglob('*')):
  if p.is_file():z.write(p,p.relative_to(dest))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
receipt=dict(archive=str(archive),directory=str(dest),bytes=archive.stat().st_size,files=len(manifest)+1,
 archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),checkpoint_sha256=hashlib.sha256((dest/'CHECKPOINT.json').read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((dest/'MANIFEST.json').read_bytes()).hexdigest())
print(json.dumps(receipt,indent=2))