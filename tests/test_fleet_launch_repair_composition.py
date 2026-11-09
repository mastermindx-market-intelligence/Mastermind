"""Fleet launch repair over the observed sequence42 source; public code only.

The selected 8404cb15 generation is reconstructed from the protected composers.
Its RELEASE.json here is an inert source descriptor, not an installed receipt.
Composed members run in a child interpreter so no sibling test's import of an
older lane_runtime/support_bundle can satisfy them.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
from ops.native_fabric.provider_plans import compose
from test_current40_terminal_diagnostic_composition import source40
from test_current116_maintenance_guard_composition import current_source
from test_terminal_memory_successor_composition import terminal_source

GENERATION='8404cb15c5322690a8b805140e9f987710881e8ac020f2eee4f6cafa41fdee03'
PREDECESSOR='terminal116-protected-memory-support-status'
PROFILE='terminal119-fleet-launch-repair'
CHANGED={'ext/fabric_task.py','ext/lease_broker.py','ext/remote_sub.sh','ext/support_bundle.py'}
OLD_SUPPORT='afbfa147cf44083e9e47e916c50b3368737f6730a270af8e974793f4bf507822'


def sha(raw):return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope='module')
def selected119(terminal_source,tmp_path_factory):
    target=tmp_path_factory.mktemp('fleet-selected119')/'code'
    compose.compose(terminal_source,target,profile_name=PREDECESSOR)
    files=json.loads((target/'FILES.json').read_text())
    profile=json.loads((compose.HERE/'fleet_launch_repair/profile.json').read_text())
    assert files==profile['base_files'] and len(files)==119
    assert profile['base_selection']['generation']==GENERATION
    (target/'RELEASE.json').write_text(json.dumps({'digest':GENERATION,'files':files,
        'fixture_premise':'SOURCE_ONLY descriptor, not installed evidence'}))
    return target


@pytest.fixture(scope='module')
def repaired(selected119,tmp_path_factory):
    target=tmp_path_factory.mktemp('fleet-repaired119')/'code'
    result=compose.compose(selected119,target,profile_name=PROFILE)
    assert result['files']==119
    assert result['publication_performed'] is result['selection_performed'] is False
    return target


def run_ext(repaired,tmp_path,code,*args):
    proc=subprocess.run([sys.executable,'-c','import sys;sys.path.insert(0,sys.argv[1]);'+code,
                         str(repaired/'ext'),*map(str,args)],
                        capture_output=True,text=True,cwd=tmp_path,timeout=120)
    assert proc.returncode==0,proc.stderr
    return json.loads(proc.stdout)


def test_repair_changes_exactly_four_reviewed_members(selected119,repaired):
    profile=json.loads((compose.HERE/'fleet_launch_repair/profile.json').read_text())
    base=json.loads((selected119/'FILES.json').read_text())
    files=json.loads((repaired/'FILES.json').read_text())
    assert files==profile['files'] and set(files)==set(base)
    assert {k for k in files if files[k]!=base[k]}==CHANGED
    for relative,wanted in files.items():
        assert sha((repaired/relative).read_bytes())==wanted
        if relative not in CHANGED:
            assert (repaired/relative).read_bytes()==(selected119/relative).read_bytes()
    assert not (repaired/'RELEASE.json').exists() and not (repaired/'CURRENT.json').exists()
    provenance=json.loads((compose.HERE/'fleet_launch_repair/provenance.json').read_text())
    assert sorted(CHANGED)==provenance['changed_target_members']
    assert provenance['prospective_predecessor']==profile['base_selection']
    assert provenance['actual_current_or_publication_claim'] is False


def test_profiles_refuse_each_others_base(terminal_source,selected119,tmp_path):
    with pytest.raises(ValueError,match='selected native base changed'):
        compose.compose(terminal_source,tmp_path/'a',profile_name=PROFILE)
    with pytest.raises(ValueError,match='selected native base changed'):
        compose.compose(selected119,tmp_path/'b',profile_name=PREDECESSOR)
    assert not (tmp_path/'a').exists() and not (tmp_path/'b').exists()


def test_support_status_reader_pins_repaired_support_bundle(repaired):
    raw=(repaired/'ext/fabric_task.py').read_text()
    pins=re.findall(r"'support_bundle\.py': '([0-9a-f]{64})'",raw)
    assert pins==[sha((repaired/'ext/support_bundle.py').read_bytes())]
    assert OLD_SUPPORT not in raw


CLASSIFY=r'''
import hashlib, json, os, stat
from pathlib import Path
import support_bundle as sb
work = Path(sys.argv[2]).resolve()
RUN, T = "fleet-r1", "2026-11-01T00:00:00Z"
# Key sets observed on triage0-3 retained records (2026-11-09 census).
ADMISSION = {"active_count": 0, "allowed": True, "cpu_count": 8, "json_locked_count": 0,
             "legacy_count": 0, "load1": 0.5, "load_ratio_limit": 1.5, "max_active": 4,
             "reasons": [], "stale_reaped": []}
MINT = {"census_proven": True, "started_at": "2026-11-01T00:00:00.123Z",
        "ended_at": "2026-11-01T00:00:01.456Z", "residual_count": 0, "returncode": 1,
        "stderr_bytes": 55}
PROOF = {"executor_staging_without_git": ["lanes/x"], "lane_branch_present": False,
         "lane_workspace_dirs": [], "mint": MINT, "process": False, "worktree_registered": False}
def sha(raw): return hashlib.sha256(raw).hexdigest()
def lease(run=RUN):
    return {"schema": "mastermind.local_lane_lease.v1", "key": run, "label": run,
            "host": "triage0", "pid": 4242, "started_at": T, "source_sha256": None,
            "admission": dict(ADMISSION), "reconcile_unreleased": True}
def hold(run=RUN):
    return {"schema": "mastermind.local_lane_reconciliation_hold.v1", "key": run,
            "host": "triage0", "held_at": T, "reason": "sparse_workspace_effect_unknown",
            "original_lease": lease(run)}
def seat(active, marker_raw, run=RUN, **change):
    value = {"schema": "mastermind.seat_hold_settlement.v1", "run_id": run, "host": "triage0",
             "hold": hold(run), "marker_sha256": sha(marker_raw),
             "proof": json.loads(json.dumps(PROOF)),
             "remote_rc": 76, "remote_signal": "FABRIC_SPARSE_MINT_UNVERIFIED",
             "worker_started": False, "settled_at": T, "settled_by": "seat", "note": "n",
             "lease_released": {"lease": "0123456789ab", "ok": True,
                                "via": "lease_broker.py release"},
             "marker_moved_to": str(active / ("." + run + ".held-marker.json"))}
    value.update(change)
    return value
def sparse(**change):
    value = {"schema": "mastermind.original_host_sparse_hold_settlement.v1", "run_id": RUN,
             "action": "original_host_sparse_hold_settlement", "state": "removal_authorized",
             "host": "triage2", "created_at": T, "broker_provenance": "lease_broker.py release",
             "marker_sha256": "a" * 64, "mint_receipt_sha256": "b" * 64, "mint_session": 7,
             "original_pid": 99, "provider_lease_id": "0123456789ab",
             "provider_lease_state": "released", "mint_cleanup_census_proven": True,
             "mint_cleanup_residual_count": 0}
    value.update({k: True for k in sb._SPARSE_VERIFIED})
    value.update(change)
    return value
def physical(kind, **change):
    value = {"schema": "mastermind.original_lane_physical_cleanup_settlement.v1",
             "run_id": RUN, "kind": kind, "host": "triage3", "evidence": "e",
             "original_marker_device": 1, "original_marker_inode": 2,
             "original_marker_sha256": "c" * 64,
             "original_task_state": "EFFECT_UNKNOWN_PRESERVED_NOT_REPLAYED"}
    if kind == "preprovider_mint_failed_verified_cleanup":
        value.update(original_marker=hold(), mint_helper_git_blob="d" * 40,
                     mint_receipt_sha256="e" * 64, provider_effect_claimed=False,
                     worker_started_proven=False)
    else:
        value.update(original_marker=lease(), kernel_boot_epoch=2000,
                     receipt_observed_utc=T, external_task_effects_resolved=False,
                     provider_result_accepted=False, worker_may_have_performed_effects=True)
    if kind == "rebooted_worker_physical_cleanup_only":
        value.update(kernel_boot_id="0f0f0f0f-1111-2222-3333-444455556666",
                     original_started_epoch=1000)
    if kind == "orphaned_worker_physical_cleanup_only":
        value.update(no_matching_processes=True, no_processes_with_cwd_under_lanes=True,
                     original_worker_pid_confirmed_dead=True, results_retained_paths=["r"])
    value.update(change)
    return value
def put(path, value, mode=0o600):
    path.write_bytes(value if type(value) is bytes else json.dumps(value).encode())
    os.chmod(path, mode)
    return path
results = {}
def case(name, build):
    active = work / name / "active"
    active.mkdir(parents=True)
    probe = build(active)
    results[name] = sb._is_retained_settlement_metadata(probe)
def held_pair(active, run=RUN, mode=0o600, **change):
    raw = json.dumps(hold(run)).encode()
    marker = put(active / ("." + run + ".held-marker.json"), raw)
    put(active / ("." + run + ".seat-settlement.json"), seat(active, raw, run, **change), mode)
    return marker
case("seat", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m")))
case("seat_minimal", lambda a: put(a / ".fleet-r1.seat-settlement.json",
     {k: v for k, v in seat(a, b"m").items() if k not in ("lease_released", "marker_moved_to")}))
case("seat_donor_proof", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m", proof={
     "donor_base_type_now": "tree", "lane_branch_present": False, "lane_workspace_dirs": [],
     "mint": {k: v for k, v in MINT.items() if k != "started_at"}, "original_pid_alive": False,
     "process": False, "worktree_registered": False})))
case("held_marker", lambda a: held_pair(a))
def held_symlinked_root(a):
    alias = a.parent / "alias"
    alias.symlink_to(a, target_is_directory=True)
    return held_pair(a, marker_moved_to=str(alias / (".fleet-r1.held-marker.json")))
case("held_marker_symlinked_root", held_symlinked_root)
for kind in sorted(sb._PHYSICAL_KINDS):
    case("physical_" + kind, lambda a, kind=kind: put(
        a / ".fleet-r1.physical-cleanup-settlement.json", physical(kind)))
case("sparse", lambda a: put(a / ".fleet-r1.sparse-settlement.json", sparse()))
# Each mutation below must stay a blocking active entry.
case("seat_group_writable", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m"), 0o664))
case("seat_run_mismatch", lambda a: put(a / ".other-run.seat-settlement.json", seat(a, b"m")))
case("seat_worker_started", lambda a: put(a / ".fleet-r1.seat-settlement.json",
     seat(a, b"m", worker_started=True)))
case("seat_extra_key", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m", extra=1)))
case("seat_wrong_rc", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m", remote_rc=0)))
def proof_case(name, **change):
    case(name, lambda a: put(a / ".fleet-r1.seat-settlement.json",
                             seat(a, b"m", proof=dict(PROOF, **change))))
proof_case("seat_proof_extra_key", pid_alive=False)
proof_case("seat_proof_workspace_present", lane_workspace_dirs=["lanes/fleet-r1"])
proof_case("seat_proof_pid_alive", original_pid_alive=True)
proof_case("seat_proof_branch_present", lane_branch_present=True)
proof_case("seat_proof_mint_residual", mint=dict(MINT, residual_count=1))
proof_case("seat_proof_mint_unproven", mint=dict(MINT, census_proven=False))
proof_case("seat_proof_mint_extra_key", mint=dict(MINT, worker_pid=7))
case("seat_proof_missing_workspace", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m",
     proof={k: v for k, v in PROOF.items() if k != "lane_workspace_dirs"})))
case("seat_admission_extra_key", lambda a: put(a / ".fleet-r1.seat-settlement.json", seat(a, b"m",
     hold=dict(hold(), original_lease=dict(lease(), admission=dict(ADMISSION, override=True))))))
case("seat_duplicate_key", lambda a: put(a / ".fleet-r1.seat-settlement.json",
     json.dumps(seat(a, b"m"))[:-1].encode() + b', "run_id": "fleet-r1"}'))
def seat_symlink(a):
    real = put(a.parent / "real.json", seat(a, b"m"))
    link = a / ".fleet-r1.seat-settlement.json"
    link.symlink_to(real)
    return link
case("seat_symlink", seat_symlink)
case("held_marker_unpaired", lambda a: put(a / ".fleet-r1.held-marker.json", hold()))
case("held_marker_hash_mismatch", lambda a: held_pair(a, marker_sha256="f" * 64))
case("held_marker_moved_elsewhere", lambda a: held_pair(a, marker_moved_to=str(a / "x.json")))
case("held_marker_relative_path", lambda a: held_pair(a, marker_moved_to=".fleet-r1.held-marker.json"))
def held_other_dir(a):
    (a.parent / "other").mkdir()
    return held_pair(a, marker_moved_to=str(a.parent / "other" / ".fleet-r1.held-marker.json"))
case("held_marker_other_dir", held_other_dir)
case("held_marker_seat_group_writable", lambda a: held_pair(a, mode=0o664))
case("sparse_residual", lambda a: put(a / ".fleet-r1.sparse-settlement.json",
     sparse(mint_cleanup_residual_count=1)))
case("sparse_unverified", lambda a: put(a / ".fleet-r1.sparse-settlement.json",
     sparse(verified_no_live_original_pid=False)))
case("physical_effect_cleared", lambda a: put(a / ".fleet-r1.physical-cleanup-settlement.json",
     physical("orphaned_worker_physical_cleanup_only", original_task_state="RESOLVED")))
case("physical_started_after_boot", lambda a: put(a / ".fleet-r1.physical-cleanup-settlement.json",
     physical("rebooted_worker_physical_cleanup_only", original_started_epoch=3000)))
case("physical_unknown_kind", lambda a: put(a / ".fleet-r1.physical-cleanup-settlement.json",
     dict(physical("orphaned_worker_physical_cleanup_only"), kind="other")))
case("unknown_settlement_kind", lambda a: put(a / ".fleet-r1.other-settlement.json", seat(a, b"m")))
case("arbitrary_dotfile", lambda a: put(a / ".fleet-r1.json", seat(a, b"m")))
case("preexec_run_mismatch", lambda a: put(a / ".fleet-r1.preexec-settlement.json", {"run_id": "x"}))
# ensure_policy: retained-only active refreshes; a lane marker or bad record refuses.
def stable(name, build):
    root = work / ("policy-" + name)
    (root / "ext/active").mkdir(parents=True)
    (root / "orch/fabric").mkdir(parents=True)
    put(root / "orch/fabric/pools.yaml", b"old: 1\n", 0o640)
    source = put(root / "new-pools.yaml", b"new: 2\n")
    build((root / "ext").resolve() / "active")
    try:
        outcome = sb.ensure_policy(source, root / "ext", sha(b"new: 2\n"))
    except ValueError as exc:
        outcome = str(exc)
    target = root / "orch/fabric/pools.yaml"
    names = sorted(p.name for p in (root / "ext/active").iterdir())
    results["policy_" + name] = [outcome, target.read_bytes().decode(),
                                 oct(stat.S_IMODE(target.stat().st_mode)), names]
def retained_fleet(a):
    put(a / ".fleet-r1.seat-settlement.json",
        {k: v for k, v in seat(a, b"m").items() if k != "marker_moved_to"})
    held_pair(a, "fleet-r2")
    put(a / ".fleet-r3.sparse-settlement.json", dict(sparse(), run_id="fleet-r3"))
    put(a / ".fleet-r4.physical-cleanup-settlement.json",
        dict(physical("orphaned_worker_physical_cleanup_only"), run_id="fleet-r4",
             original_marker=lease("fleet-r4")))
stable("retained_only", retained_fleet)
stable("live_lane", lambda a: (retained_fleet(a), put(a / "fleet-r9.json", lease("fleet-r9"))))
stable("bad_record", lambda a: (retained_fleet(a),
       put(a / ".fleet-r5.seat-settlement.json", seat(a, b"m", run_id="fleet-r5"), 0o664)))
print(json.dumps(results))
'''

RETAINED={'seat','seat_minimal','seat_donor_proof','held_marker','held_marker_symlinked_root','sparse',
          'physical_orphaned_worker_physical_cleanup_only',
          'physical_preprovider_mint_failed_verified_cleanup','physical_rebooted_worker_physical_cleanup_only'}


def test_retained_settlements_are_metadata_and_everything_else_blocks(repaired,tmp_path):
    results=run_ext(repaired,tmp_path,CLASSIFY,tmp_path/'work')
    classified={k:v for k,v in results.items() if not k.startswith('policy_')}
    assert {k for k,v in classified.items() if v is True}==RETAINED
    assert all(v is False for k,v in classified.items() if k not in RETAINED)
    assert len(classified)==len(RETAINED)+30


def test_idle_refresh_accepts_only_retained_metadata_and_keeps_every_record(repaired,tmp_path):
    results=run_ext(repaired,tmp_path,CLASSIFY,tmp_path/'work')
    retained=['.admission.lock','.fleet-r1.seat-settlement.json','.fleet-r2.held-marker.json',
              '.fleet-r2.seat-settlement.json','.fleet-r3.sparse-settlement.json',
              '.fleet-r4.physical-cleanup-settlement.json']
    assert results['policy_retained_only']==['POLICY_REFRESHED_IDLE','new: 2\n','0o640',retained]
    assert results['policy_live_lane']==['SUPPORT_POLICY_STALE_ACTIVE_REFUSED','old: 1\n','0o640',
                                         sorted(retained+['fleet-r9.json'])]
    assert results['policy_bad_record']==['SUPPORT_POLICY_STALE_ACTIVE_REFUSED','old: 1\n','0o640',
                                          sorted(retained+['.fleet-r5.seat-settlement.json'])]


BROKER=r'''
import json
from datetime import date, datetime, timedelta, timezone
import lease_broker as lb
aware = datetime(2026, 11, 9, 11, 30, tzinfo=timezone(timedelta(hours=8)))
snapshot = {"parked_until": lb._json_safe_time(aware),
            "usage": lb._json_safe_time({"day": date(2026, 11, 9), "w": [aware], "n": 3}),
            "keyed": lb._json_safe_time({date(2026, 11, 9): 3, aware: {"n": 1}}),
            "naive": lb._json_safe_time(datetime(2026, 11, 9, 3, 30)),
            "none": lb._json_safe_time(None), "text": lb._json_safe_time("2026-11-09")}
lines = [lb.AcquireResult(ok=False, reason="host_account_unavailable",
                          detail="host_account_mode_not_admitted").line(),
         lb.AcquireResult(ok=False, reason="pool_busy").line()]
print(json.dumps({"snapshot": json.loads(json.dumps(snapshot)), "lines": lines}))
'''


def test_status_snapshot_serializes_yaml_timestamps_and_refusal_names_detail(repaired,tmp_path):
    results=run_ext(repaired,tmp_path,BROKER)
    assert results['snapshot']=={'parked_until':'2026-11-09T03:30:00Z',
        'usage':{'day':'2026-11-09','w':['2026-11-09T03:30:00Z'],'n':3},
        'keyed':{'2026-11-09':3,'2026-11-09T03:30:00Z':{'n':1}},
        'naive':'2026-11-09T03:30:00','none':None,'text':'2026-11-09'}
    assert results['lines']==['WAIT reason=host_account_unavailable detail=host_account_mode_not_admitted',
                              'WAIT reason=pool_busy']
    source=(repaired/'ext/lease_broker.py').read_text()
    assert '"parked_until": _json_safe_time(acct.get("parked_until"))' in source
    assert 'else "unclassified")' in source


@pytest.mark.parametrize('broker_output,expected',[
    ('WAIT reason=host_account_unavailable detail=host_account_mode_not_admitted\n',
     ' reason=host_account_unavailable detail=host_account_mode_not_admitted'),
    ('WAIT reason=pool_busy\n',' reason=pool_busy'),
    ('WAIT reason=$(touch${IFS}x) detail=Free-Text\n',''),
    ('WAIT reason='+'a'*65+' detail=ok_1\n',' detail=ok_1'),
    ('noise\nWAIT reason=first reason=second\n',' reason=first'),
    ('detail=early\nWAIT reason=pool_busy detail=x_1\nWAIT reason=z detail=y\n',
     ' reason=pool_busy detail=x_1'),
    ('WAIT reason=pool_busy\ndetail=next_line\n',' reason=pool_busy'),
    ('noise detail=orphan\n',''),
    ('',''),
])
def test_launch_log_echoes_only_closed_refusal_tokens(repaired,tmp_path,broker_output,expected):
    script=(repaired/'ext/remote_sub.sh').read_text()
    function=re.search(r'^lease_refusal_detail\(\) \{\n.*?^\}\n',script,re.S|re.M).group(0)
    assert script.count('log "LEASE_REFUSED rc=$RC$(lease_refusal_detail)"')==2
    output=tmp_path/'lease.out';output.write_text(broker_output)
    proc=subprocess.run(['bash','-c',function+'printf "LEASE_REFUSED rc=75%s" "$(lease_refusal_detail)"'],
                        env={'LEASE_OUTPUT_FILE':str(output),'PATH':'/usr/bin:/bin'},
                        capture_output=True,text=True,cwd=tmp_path,timeout=30)
    assert proc.returncode==0 and proc.stdout=='LEASE_REFUSED rc=75'+expected
    assert not (tmp_path/'x').exists()
