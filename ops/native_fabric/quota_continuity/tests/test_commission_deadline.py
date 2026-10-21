"""Offline deadline proofs through the actual Bash and owned-process runtime.

Each transport/broker executable is an inert, finite fixture. No live config,
provider, account or SSH session is used. Source copies remain byte-identical;
the fixture supplies host metadata and never permits a model task to execute.
"""
from __future__ import annotations

import hashlib
import fcntl
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]
import commission_deadline as deadline


def write(path, source, executable=False):
    path.write_text(textwrap.dedent(source).lstrip(), encoding='utf-8')
    path.chmod(0o700 if executable else 0o600)


def write_native_plain_request(directory, run_id, payload,
                               root_id='offline-root', parent_id='offline-parent'):
    """Use the native exclusive writer and the adapter's original record schemas."""
    import provider_outcome
    request = directory / (run_id + '.request.json')
    launch = directory / (run_id + '.request-launch.json')
    packet_sha = hashlib.sha256(payload).hexdigest()
    provider_outcome.write_new(request, {
        'schema': 'mastermind.fabric_request_artifact.v1',
        'run_id': run_id, 'root_id': root_id, 'parent_run_id': parent_id,
        'task_class': 'domain_orchestration', 'cwd': '~',
        'packet': run_id + '.request.packet', 'packet_sha256': packet_sha,
        'packet_bytes': len(payload), 'created_at': 1,
        'automatic_background_execution': False,
    })
    provider_outcome.write_new(launch, {
        'schema': 'mastermind.fabric_request_launch.v1',
        'run_id': run_id, 'root_id': root_id, 'parent_run_id': parent_id,
        'state': 'LAUNCH_ATTEMPT_RESERVED', 'created_at': 1,
        'packet_sha256': packet_sha,
        'request_sha256': hashlib.sha256(request.read_bytes()).hexdigest(),
    })
    return request, launch


FIXTURE = r'''
import hashlib, json, os, re, sys, time
from pathlib import Path
root = Path(os.environ['DEADLINE_FIXTURE_ROOT'])
name = Path(sys.argv[0]).name
case = os.environ['DEADLINE_FIXTURE_CASE']
args = sys.argv[1:]
def record(stage, **extra):
    row = dict(stage=stage, monotonic_ns=time.monotonic_ns(), pid=os.getpid(),
               origin_deadline_ns=os.environ.get('POOL_COMMISSION_DEADLINE_NS'), **extra)
    with (root/'events.jsonl').open('a') as stream:
        stream.write(json.dumps(row, sort_keys=True)+'\n')
    return row
def count(stage):
    if not (root/'events.jsonl').exists(): return 0
    return sum(json.loads(line)['stage']==stage for line in (root/'events.jsonl').read_text().splitlines())
if name == 'broker':
    operation = args[0]
    if operation == 'acquire':
        wait = float(args[args.index('--wait')+1])
        wire_deadline = args[args.index('--deadline-ns')+1] if '--deadline-ns' in args else None
        record('acquire', requested_wait_seconds=wait, wire_deadline_ns=wire_deadline,
               inherited_remaining_seconds=os.environ.get('POOL_COMMISSION_REMAINING_SECONDS'))
        if case == 'deny':
            time.sleep(min(wait, float(os.environ['POOL_COMMISSION_REMAINING_SECONDS'])+2))
            record('broker_denied')
            raise SystemExit(75)
        time.sleep(float(os.environ.get('DEADLINE_FIXTURE_BROKER_DELAY', '0')))
        print('LEASE=0123456789ab ACCOUNT=fixture-account')
        record('granted')
        raise SystemExit(0)
    if operation in ('release','heartbeat'):
        record(operation)
        raise SystemExit(0)
elif name == 'ssh':
    command = args[-1]
    if 'mastermind.transport_observation' in command:
        # Inert stand-in for the fixed remote readback: the selected host's
        # uploaded packet and published RELEASE manifest are represented by the
        # local fixture packet and the support manifest this controller wrote.
        head = re.match(r"python3 - '([^']+)' '([a-f0-9]{64})' '([a-f0-9]{64})'", command)
        run, support, policy = head.group(1), head.group(2), head.group(3)
        observations = list((root/'ext/state/remote_sub').glob(run+'.transport-observation.*'))
        if len(observations) != 1: raise SystemExit('observation_custody_missing')
        observed = observations[0]
        info = observed.stat()
        record('transport_read', observation_path=str(observed),
               observation_mode=info.st_mode & 0o777,
               observation_inode=info.st_ino)
        if case == 'transport_observation_replaced':
            saved = observed.with_name(observed.name+'.saved')
            observed.rename(saved)
            observed.symlink_to(saved)
        packet = (root/'packet.txt').read_bytes()
        manifest = json.loads((root/'ext/state/remote_sub'/(run+'.support.json')).read_text())
        files = manifest.get('files') if isinstance(manifest, dict) and 'files' in manifest else manifest
        observation = {'schema': 'mastermind.transport_observation.v1', 'run_id': run,
                       'packet_bytes': len(packet),
                       'packet_sha256': hashlib.sha256(packet).hexdigest(),
                       'support_digest': support, 'policy_sha256': policy,
                       'files': files}
        if case == 'transport_mutated_packet':
            observation['packet_bytes'] = len(packet) + 1
            observation['packet_sha256'] = 'f'*64
        print(json.dumps(observation, sort_keys=True, separators=(',', ':')))
        raise SystemExit(0)
    if 'nohup env ' in command:
        child = re.search(r"REMOTE_SUB_CHILD_TIMEOUT='([0-9]+)'", command)
        budget = re.search(r"REMOTE_SUB_COMMISSION_BUDGET_SECONDS='([0-9]+)'", command)
        record('launch', child_timeout=int(child.group(1)) if child else None,
               remote_budget=int(budget.group(1)) if budget else None,
               origin_clock_forwarded='POOL_COMMISSION_DEADLINE_NS' in command)
        if case == 'retry_ambiguous':
            raise SystemExit(0 if count('launch')==1 else 255)
        if case == 'admission_expiry': raise SystemExit(0)
        if case == 'launch_timeout': time.sleep(10); raise SystemExit(0)
        raise SystemExit(0)
    if '__REMOTE_SUB_PENDING__' in command:
        record('poll'); print('0' if case == 'plain_ok' else '75'); raise SystemExit(0)
    if 'tail -c 4096' in command:
        record('admission_read')
        if case == 'admission_expiry': time.sleep(10)
        print('REMOTE_SUB_ADMISSION_REFUSED {"reasons":["active_lane_limit_reached"]}')
        raise SystemExit(0)
    if 'support_bundle.py' in command:
        record('support_publish')
        manifests = list((root/'ext/state/remote_sub').glob('*.support.json'))
        if len(manifests) != 1: raise SystemExit('fixture_manifest_missing')
        files = json.loads(manifests[0].read_text())
        digest = hashlib.sha256(json.dumps({'schema':'remote-support-code.v1','files':files},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        # Match the incumbent publisher's physical path-line contract. These
        # deadline cases still use their explicitly inert readback above; the
        # separate physical-owner suite executes the real strict readback body.
        print(root/'physical-owner'/'support-releases'/digest/'ext')
        raise SystemExit(0)
    if 'mkdir -p ~/lanes/tmp ' in command:
        record('setup')
        if case == 'slow_setup': time.sleep(10)
        raise SystemExit(0)
    if 'mkdir ' in command:
        record('support_mkdir'); raise SystemExit(0)
    if command.startswith('test -f '):
        record('settlement_read'); raise SystemExit(1)
    if command.startswith('rm -f '):
        record('remote_cleanup'); raise SystemExit(0)
elif name == 'scp':
    record('scp')
    if case == 'slow_scp': time.sleep(10)
    if case == 'retry_ambiguous' and count('scp')==1: time.sleep(1.2)
    raise SystemExit(0)
elif name == 'rsync':
    if args == ['--version']:
        print('rsync  version 3.2.7  protocol version 31');raise SystemExit(0)
    record('collect')
    Path(args[-1]).write_text('REMOTE_SUB_ADMISSION_REFUSED {"reasons":["active_lane_limit_reached"]}\n')
    raise SystemExit(0)
elif name == 'ledger':
    record('ledger'); raise SystemExit(0)
record('forbidden', command=name)
raise SystemExit(125)
'''


PYTHON_FIXTURE = r'''
"""Use the real process census wherever the platform supports it.

Only this sandbox's qualified virtual-PID mismatch gets an observation adapter
from actual POSIX identity syscalls. Never return a canned empty/proven census.
Production Popen, timeout, signals, reaping and receipt code remain unchanged.
The finite inert fixtures do not spawn independent descendants.
"""
import os, runpy, sys
from pathlib import Path
sys.path.insert(0,str(Path(os.environ['DEADLINE_FIXTURE_ROOT'])/'ext'))
import lane_runtime
def census(argv, *, timeout):
    if not (0 < os.getpid() < 2048):
        raise lane_runtime.ProcessCensusError('fixture_pid_namespace_out_of_bounds')
    if argv not in (['/bin/ps','-axo','pid=,pgid=,stat='], ['/bin/ps','-axo','pid=,stat=']):
        if len(argv)!=5 or argv[:3]!=['/bin/ps','-o','pid=,stat='] or argv[3]!='-p':
            raise lane_runtime.ProcessCensusError('fixture_census_argv_unknown')
        wanted=int(argv[4])
    else:
        wanted=None
    rows=[]
    for pid in range(1,2048) if wanted is None else [wanted]:
        try:
            pgid=os.getpgid(pid)
            os.getsid(pid)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise lane_runtime.ProcessCensusError('fixture_census_permission') from exc
        state='R'
        try:
            observed=os.waitid(os.P_PID,pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        except ChildProcessError:
            observed=None
        if observed is not None and observed.si_pid==pid:
            state='Z'
        rows.append(f'{pid} {pgid} {state}' if argv[2]=='pid=,pgid=,stat=' else f'{pid} {state}')
    if not rows:
        raise lane_runtime.ProcessCensusError('fixture_census_empty')
    return tuple(rows)
def needs_virtual_census():
    # This simulator intermittently makes ps succeed in the host namespace.
    # Choose by the stable, exact namespace mismatch; an occasional successful
    # ps call cannot qualify that host-domain census for virtual process IDs.
    # macOS and ordinary Linux keep the incumbent census entirely unchanged.
    if not sys.platform.startswith('linux'):
        return False
    try:
        raw=Path('/proc/self/stat').read_text()
        actual_pid=int(raw.split(' ',1)[0])
        fields=raw.rsplit(') ',1)[1].split()
        actual_pgid=int(fields[2])
    except (OSError,ValueError,IndexError):
        return False
    if actual_pid==os.getpid() and actual_pgid==os.getpgid(0):
        return False
    if (not 0<os.getpid()<2048 or actual_pid==os.getpid()
            or actual_pgid==os.getpgid(0)
            or not hasattr(os,'waitid') or not hasattr(os,'WNOWAIT')):
        raise lane_runtime.ProcessCensusError('fixture_virtual_namespace_unqualified')
    return True
if needs_virtual_census():
    lane_runtime._run_ps_lines=census
args=sys.argv[1:]
if args[0]=='-c':
    sys.argv=['-c',*args[2:]]
    exec(compile(args[1],'<fixture -c>','exec'),{'__name__':'__main__'})
elif args[0]=='-':
    sys.argv=args
    exec(compile(sys.stdin.read(),'<fixture stdin>','exec'),{'__name__':'__main__'})
else:
    sys.argv=args
    runpy.run_path(args[0],run_name='__main__')
'''


class DeadlineValues(unittest.TestCase):
    def test_canonical_origin_and_narrowing_never_extend(self):
        self.assertEqual(deadline.read_deadline_ns({}), None)
        self.assertEqual(deadline.read_deadline_ns({deadline.DEADLINE_ENV:'123456789'}),123456789)
        self.assertEqual(deadline.narrow_deadline_ns(9_000_000_000,20,now_ns=1_000_000_000),9_000_000_000)
        self.assertEqual(deadline.narrow_deadline_ns(9_000_000_000,2,now_ns=1_000_000_000),3_000_000_000)
        self.assertEqual(deadline.remaining_seconds(1_234_567_890,now_ns=1_000_000_000),0.23456789)

    def test_invalid_clock_and_duration_inputs_fail_closed(self):
        for value in ('', '0', '01', '+1', ' 1', '1.0', True, 1.0, -1, 2**63):
            with self.subTest(value=value), self.assertRaises(deadline.CommissionDeadlineInvalid):
                deadline.validate_deadline_ns(value)
        for value in (-1, math.inf, math.nan, True, '1', 7201):
            with self.subTest(value=value), self.assertRaises(deadline.CommissionDeadlineInvalid):
                deadline.narrow_deadline_ns(None,value,now_ns=1_000_000_000)

    def test_exact_expiry_and_minimum_are_not_rounded_up(self):
        for now in (1_000_000_000,1_000_000_001):
            with self.assertRaises(deadline.CommissionDeadlineExpired):
                deadline.require_remaining(1_000_000_000,now_ns=now)
        with self.assertRaises(deadline.CommissionDeadlineExpired):
            deadline.require_remaining(999_999_999,minimum_seconds=1,now_ns=0)
        self.assertEqual(deadline.require_remaining(1_000_000_000,minimum_seconds=1,now_ns=0),1)


class ControllerDeadline(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='commission-',
            dir=os.environ.get('NATIVE_ROLLOUT_TEST_ROOT',str(ROOT/'tests')))
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.ext=self.root/'ext'; self.bin=self.root/'bin'; self.tmp=self.root/'tmp'
        for path in (self.ext,self.bin,self.tmp): path.mkdir(mode=0o700)
        for folder in (ROOT/'source',ROOT/'candidate'):
            for path in folder.iterdir():
                if path.is_file() and not path.is_symlink():
                    shutil.copyfile(path,self.ext/path.name)
        self.copied={name:hashlib.sha256((self.ext/name).read_bytes()).hexdigest()
                     for name in ('remote_sub.sh','remote_sub_helpers.py','commission_deadline.py','lane_runtime.py')}
        for name in ('remote_sub.sh','remote_sub_helpers.py','commission_deadline.py'):
            self.assertEqual(self.copied[name],hashlib.sha256((ROOT/'candidate'/name).read_bytes()).hexdigest())
        (self.ext/'hosts.json').write_text(json.dumps({'fixture':{
            'ssh_alias':'inert-transport','cores':2,'max_active':1,'load_gate':1,
            'roles':['lanes'],'allowed_modes':['minimax','glm','qwen'],
            'min_free_gb':0,'checkout_reserve_gb':0}}))
        policy=self.root/'orch/fabric'; policy.mkdir(parents=True)
        (policy/'pools.yaml').write_text('{}\n')
        # The support manifest hashes these exact files but transport fixtures
        # never execute the uploaded support or read a real remote filesystem.
        (self.ext/'yes').write_text('#!/bin/sh\nexit 125\n')
        self.packet=self.root/'packet.txt';self.packet.write_text('INERT TEST: no model task may start.\n')
        for name in ('ssh','scp','rsync','broker','ledger','claude','codex','curl','node'):
            write(self.bin/name,'#!'+sys.executable+'\n'+FIXTURE,executable=True)
        write(self.bin/'fixture-python','#!'+sys.executable+'\n'+PYTHON_FIXTURE,executable=True)

    def run_controller(self,case,budget=4,broker_delay=0,mode='minimax',model='fixture-model',
                       allow_prelease_refusal=False):
        origin=time.monotonic_ns()+int(budget*1_000_000_000)
        env={'PATH':str(self.bin)+':/usr/bin:/bin','LANG':'C','LC_ALL':'C',
             'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','TMPDIR':str(self.tmp),
             'DEADLINE_FIXTURE_ROOT':str(self.root),'DEADLINE_FIXTURE_CASE':case,
             'DEADLINE_FIXTURE_BROKER_DELAY':str(broker_delay),
             'REMOTE_SUB_MAX_SECS':str(int(budget)),'REMOTE_SUB_POLL_SECS':'1',
             'REMOTE_SUB_ADMISSION_RETRY_SECS':'1','REMOTE_SUB_ADMISSION_WAIT_SECS':'10',
             'REMOTE_SUB_PYTHON':str(self.bin/'fixture-python'),'REMOTE_SUB_BROKER_CMD':str(self.bin/'broker'),
             'REMOTE_SUB_LEDGER_CMD':str(self.bin/'ledger'),'REMOTE_SUB_SSH_CMD':str(self.bin/'ssh'),
             'REMOTE_SUB_SCP_CMD':str(self.bin/'scp'),'REMOTE_SUB_RSYNC_CMD':str(self.bin/'rsync'),
             'POOL_ORCHESTRATOR_ID':'offline-root','POOL_PARENT_RUN_ID':'offline-parent',
             'POOL_TASK_CLASS':'domain_orchestration',
             'POOL_TASK_COMPLEXITY':'C0_MECHANICAL',
             'POOL_COMMISSION_REMAINING_SECONDS':str(int(budget)),
             'POOL_COMMISSION_DEADLINE_NS':str(origin)}
        command=['/bin/bash',str(self.ext/'remote_sub.sh'),'fixture',mode,str(self.packet),'~',
                 model,'--run-id','offline-'+case]
        started=time.monotonic()
        proc=subprocess.Popen(command,cwd=self.root,env=env,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:
            stdout,stderr=proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM)
            try: stdout,stderr=proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);stdout,stderr=proc.communicate(timeout=3)
            self.fail('Independent harness, not the original owner, timed out: '+stderr)
        event_path=self.root/'events.jsonl'
        if not allow_prelease_refusal:
            self.assertTrue(event_path.exists(),stderr)
        events=[json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
        self.assertNotIn('forbidden',[row['stage'] for row in events],stderr)
        receipt=self.ext/'state/remote_sub'/('offline-'+case+'.controller-process.jsonl')
        receipts=[json.loads(line) for line in receipt.read_text().splitlines()] if receipt.exists() else []
        return dict(returncode=proc.returncode,stdout=stdout,stderr=stderr,events=events,
                    elapsed=time.monotonic()-started,budget=budget,origin=origin,receipts=receipts)

    def test_real_bash_passes_origin_and_bounds_capacity_wait(self):
        result=self.run_controller('deny')
        self.assertEqual(result['returncode'],75,result['stderr'])
        acquire=next(row for row in result['events'] if row['stage']=='acquire')
        self.assertEqual(acquire['wire_deadline_ns'],str(result['origin']))
        self.assertEqual(acquire['origin_deadline_ns'],str(result['origin']))
        self.assertLessEqual(acquire['requested_wait_seconds'],result['budget'])
        self.assertLessEqual(result['elapsed'],result['budget']+0.5,result)
        self.assertEqual([row['stage'] for row in result['events']],['acquire','broker_denied'])
        self.assertIn('LEASE_REFUSED rc=75',result['stderr'])

    def test_owned_setup_expiry_releases_only_unlaunched_provider_lease(self):
        result=self.run_controller('slow_setup',budget=3)
        self.check_prelaunch_expiry(result,'commission-setup')
        self.assertNotIn('scp',[row['stage'] for row in result['events']])

    def test_owned_support_transfer_expiry_never_launches_worker(self):
        result=self.run_controller('slow_scp',budget=3)
        self.check_prelaunch_expiry(result,'commission-packet-upload')

    def check_prelaunch_expiry(self,result,label):
        self.assertEqual(result['returncode'],75,result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertIn('granted',stages);self.assertIn('release',stages);self.assertNotIn('launch',stages)
        self.assertLess(result['elapsed'],result['budget']+2,result)
        receipt=next(row for row in result['receipts'] if row['label']==label)
        self.assertTrue(receipt['timed_out'])
        self.assertTrue(receipt['cleanup']['census_proven'])
        self.assertEqual(receipt['cleanup']['residual_count'],0)

    def test_each_actual_launch_recomputes_duration_and_keeps_ambiguous_lease(self):
        result=self.run_controller('retry_ambiguous',budget=12,broker_delay=1)
        self.assertEqual(result['returncode'],255,result['stderr'])
        launches=[row for row in result['events'] if row['stage']=='launch']
        self.assertEqual(len(launches),2,result['stderr'])
        self.assertLess(launches[0]['child_timeout'],10)
        self.assertLess(launches[1]['child_timeout'],launches[0]['child_timeout'])
        for row in launches:
            self.assertEqual(row['remote_budget'],row['child_timeout'])
            self.assertFalse(row['origin_clock_forwarded'])
            self.assertLess(row['monotonic_ns'],result['origin'])
        self.assertNotIn('release',[row['stage'] for row in result['events']])
        self.assertIn('LEASE_PRESERVED effect_unknown=1',result['stderr'])

    def test_expired_admission_retry_keeps_terminal_and_collects_after_deadline(self):
        # Leave room for real prelaunch preparation; the finite 10-second
        # admission-read stall still exceeds the entire original budget.
        result=self.run_controller('admission_expiry',budget=8)
        self.assertEqual(result['returncode'],75,result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertEqual(stages.count('launch'),1,result['stderr'])
        self.assertIn('collect',stages);self.assertIn('release',stages)
        collection=next(row for row in result['events'] if row['stage']=='collect')
        self.assertGreaterEqual(collection['monotonic_ns'],result['origin'])
        self.assertIn('REMOTE_DONE rc=75',result['stderr'])
        self.assertNotIn('EFFECT_UNKNOWN timeout',result['stderr'])

    def tracked_log_events(self,run_id):
        """Classify the real controller log exactly as the collector does."""
        import remote_sub_helpers
        log_path=self.ext/'state/remote_sub'/(run_id+'.log')
        prefix=re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='
                          +re.escape(run_id)+r' host=fixture\] (.*)')
        events=[prefix.fullmatch(line).group(1)
                for line in log_path.read_text().splitlines()
                if prefix.fullmatch(line)]
        return remote_sub_helpers._tracked_events(events),log_path

    def test_plain_prelaunch_evidence_is_verified_and_ordered_before_launch(self):
        # An actual qwen plain controller run through the real Bash: the
        # transport readback, the verified receipt and the fsynced binding all
        # appear in strict order in the per-run log before the launch event.
        result=self.run_controller('plain_ok',budget=8,mode='qwen',model='qwen3.8-flash')
        self.assertEqual(result['returncode'],0,result['stderr'])
        tracked,log_path=self.tracked_log_events('offline-plain_ok')
        self.assertEqual([name for name,_ in tracked],
                         ['RUN_RESERVED','LEASE_OK','SUPPORT_VERSION_READY',
                          'TRANSPORT_VERIFIED','LAUNCH_BINDING','LAUNCH',
                          'LAUNCH_ATTEMPT'])
        order=[name for name,_ in tracked]
        self.assertLess(order.index('TRANSPORT_VERIFIED'),order.index('LAUNCH_BINDING'))
        self.assertLess(order.index('LAUNCH_BINDING'),order.index('LAUNCH'))
        packet_sha=hashlib.sha256((self.root/'packet.txt').read_bytes()).hexdigest()
        retained=self.ext/'state/remote_sub'/'offline-plain_ok.request.packet'
        self.assertEqual(hashlib.sha256(retained.read_bytes()).hexdigest(),packet_sha)
        transport_line=next(event for name,event in tracked if name=='TRANSPORT_VERIFIED')
        self.assertTrue(transport_line.startswith('TRANSPORT_VERIFIED packet='+packet_sha
                         + ' support='),transport_line)
        receipt=json.loads((self.ext/'state/remote_sub'
                            /'offline-plain_ok.transport-verified.json').read_text())
        self.assertEqual(receipt['schema'],'mastermind.transport_verification.v1')
        self.assertEqual(receipt['packet_sha256'],packet_sha)
        self.assertEqual(receipt['phase'],'PRE_LAUNCH')
        binding_line=next(event for name,event in tracked if name=='LAUNCH_BINDING')
        binding=json.loads(binding_line[len('LAUNCH_BINDING '):])
        self.assertEqual(binding['schema'],'mastermind.fabric_plain_launch_binding.v1')
        self.assertEqual(binding['transport']['packet_sha256'],packet_sha)
        self.assertEqual(binding['packet_sha256'],packet_sha)
        self.assertEqual(binding['acquire_response_sha256'],
                         receipt['acquire_response_sha256'])
        # The real shell event stream proves the actual ordering: the readback
        # and receipt happened before the only launch.
        stages=[row['stage'] for row in result['events']]
        self.assertEqual(stages.count('launch'),1,result['stderr'])
        self.assertLess(stages.index('transport_read'),stages.index('launch'))

    def test_plain_wrapper_retained_packet_reuses_exact_private_source(self):
        # fabric_task.py has already durably retained this path before invoking
        # the real native Bash controller. Retention must not re-create it.
        retained=self.ext/'state/remote_sub'/'offline-plain_ok.request.packet'
        retained.parent.mkdir(parents=True)
        retained.write_bytes(self.packet.read_bytes())
        retained.chmod(0o600)
        write_native_plain_request(retained.parent, 'offline-plain_ok', retained.read_bytes())
        self.packet=retained
        before=retained.stat()
        digest=hashlib.sha256(retained.read_bytes()).hexdigest()
        result=self.run_controller('plain_ok',budget=8,mode='qwen',model='qwen3.8-flash')
        self.assertEqual(result['returncode'],0,result['stderr'])
        after=retained.stat()
        self.assertEqual((before.st_dev,before.st_ino,before.st_mtime_ns),
                         (after.st_dev,after.st_ino,after.st_mtime_ns))
        self.assertEqual(hashlib.sha256(retained.read_bytes()).hexdigest(),digest)
        stages=[row['stage'] for row in result['events']]
        self.assertEqual(stages.count('acquire'),1)
        self.assertEqual(stages.count('launch'),1)
        self.assertLess(stages.index('transport_read'),stages.index('launch'))
        observation=next(row for row in result['events'] if row['stage']=='transport_read')
        self.assertEqual(Path(observation['observation_path']).parent,retained.parent)
        self.assertEqual(observation['observation_mode'],0o600)
        self.assertFalse(list(retained.parent.glob('offline-plain_ok.transport-observation.*')))
        receipt=json.loads((retained.parent/'offline-plain_ok.transport-verified.json').read_text())
        self.assertEqual(receipt['packet_sha256'],digest)

    def test_same_path_without_original_reservations_refuses_before_acquisition(self):
        retained=self.ext/'state/remote_sub'/'offline-plain_ok.request.packet'
        retained.parent.mkdir(parents=True)
        retained.write_bytes(self.packet.read_bytes())
        retained.chmod(0o600)
        self.packet=retained
        before=(retained.read_bytes(),retained.stat().st_ino,retained.stat().st_mtime_ns)
        result=self.run_controller('plain_ok',budget=8,mode='qwen',model='qwen3.8-flash',
                                   allow_prelease_refusal=True)
        self.assertEqual(result['returncode'],78,result['stderr'])
        self.assertIn('PLAIN_PACKET_RETENTION_REFUSED',result['stderr'])
        self.assertEqual(result['events'],[])
        self.assertEqual(before,(retained.read_bytes(),retained.stat().st_ino,retained.stat().st_mtime_ns))

    def test_replaced_transport_observation_refuses_before_worker_launch(self):
        result=self.run_controller('transport_observation_replaced',budget=8,
                                   mode='qwen',model='qwen3.8-flash')
        self.assertEqual(result['returncode'],78,result['stderr'])
        self.assertIn('TRANSPORT_VERIFICATION_REFUSED',result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertIn('transport_read',stages)
        self.assertNotIn('launch',stages)
        self.assertFalse((self.ext/'state/remote_sub'
                          /'offline-transport_observation_replaced.transport-verified.json').exists())

    def test_mutated_remote_packet_refuses_launch_and_binding(self):
        result=self.run_controller('transport_mutated_packet',budget=8,
                                   mode='qwen',model='qwen3.8-flash')
        self.assertEqual(result['returncode'],78,result['stderr'])
        self.assertIn('TRANSPORT_VERIFICATION_REFUSED',result['stderr'])
        stages=[row['stage'] for row in result['events']]
        self.assertIn('transport_read',stages)
        self.assertNotIn('launch',stages)
        tracked,_=self.tracked_log_events('offline-transport_mutated_packet')
        self.assertNotIn('TRANSPORT_VERIFIED',[name for name,_ in tracked])
        self.assertNotIn('LAUNCH_BINDING',[name for name,_ in tracked])
        self.assertFalse((self.ext/'state/remote_sub'
                          /'offline-transport_mutated_packet.transport-verified.json').exists())


REMOTE_FIXTURE = r'''
import json, os, sys, time
from pathlib import Path
import remote_sub_exec as remote
root=Path(os.environ['DEADLINE_FIXTURE_ROOT'])
original_acquire=remote.LaneLease.acquire
def acquire(cls,*args,**kwargs):
    kwargs.update(load1=0.0,cpu_count=2,max_active=1)
    (root/'before-acquire.json').write_text(json.dumps({'monotonic_ns':time.monotonic_ns()}))
    return original_acquire(*args,**kwargs)
remote.LaneLease.acquire=classmethod(acquire)
original_workspace=remote._new_macro_workspace
def workspace(*args,**kwargs):
    result=original_workspace(*args,**kwargs)
    time.sleep(float(os.environ.get('DEADLINE_FIXTURE_PREPARE_DELAY','0')))
    return result
remote._new_macro_workspace=workspace
original_process=remote.run_owned_process
def process(command,**kwargs):
    (root/'before-worker.json').write_text(json.dumps({
        'timeout':kwargs['timeout'],'monotonic_ns':time.monotonic_ns(),
        'origin_clock_in_worker_env':'POOL_COMMISSION_DEADLINE_NS' in kwargs['env'],
        'commission_envelope_in_worker_env':'REMOTE_SUB_COMMISSION_BUDGET_SECONDS' in kwargs['env']}))
    return original_process(command,**kwargs)
remote.run_owned_process=process
raise SystemExit(remote.main(sys.argv))
'''


class RemoteDeadline(unittest.TestCase):
    setUp=ControllerDeadline.setUp

    def remote(self,budget,prepare_delay=0,lock_delay=0):
        write(self.ext/'fixture-remote.py',REMOTE_FIXTURE)
        (self.ext/'yes').chmod(0o700)
        (self.ext/'lanes').mkdir(exist_ok=True)
        # The positive control is an inert local process: no CLI or provider.
        write(self.ext/'sub.sh','#!/bin/bash\nprintf "INERT COMPLETE\\n"\n',executable=True)
        active=self.ext/'active';active.mkdir(exist_ok=True)
        env={'PATH':str(self.bin)+':/usr/bin:/bin','LANG':'C','LC_ALL':'C',
             'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','TMPDIR':str(self.tmp),
             'DEADLINE_FIXTURE_ROOT':str(self.root),
             'DEADLINE_FIXTURE_PREPARE_DELAY':str(prepare_delay),
             'REMOTE_SUB_CHILD_TIMEOUT':'20','REMOTE_SUB_COMMISSION_BUDGET_SECONDS':str(budget),
             # Deliberately unrelated origin-domain value must not be compared
             # on this host, nor enter the eventual worker environment.
             'POOL_COMMISSION_DEADLINE_NS':'1',
             'LANE_MAX_ACTIVE':'1','LANE_MAX_LOAD_RATIO':'1.5',
             'POOL_TASK_COMPLEXITY':'C0_MECHANICAL'}
        command=[str(self.bin/'fixture-python'),str(self.ext/'fixture-remote.py'),
                 'offline-remote-deadline','minimax',str(self.packet),str(self.root),'fixture-model']
        lock=(active/'.admission.lock').open('w')
        proc=None
        started=time.monotonic()
        try:
            if lock_delay: fcntl.flock(lock,fcntl.LOCK_EX)
            proc=subprocess.Popen(command,cwd=self.root,env=env,stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            if lock_delay:
                until=time.monotonic()+2
                while not (self.root/'before-acquire.json').exists() and time.monotonic()<until:
                    if proc.poll() is not None: break
                    time.sleep(0.01)
                self.assertTrue((self.root/'before-acquire.json').exists(),'Real executor never entered admission')
                time.sleep(lock_delay)
                fcntl.flock(lock,fcntl.LOCK_UN)
            stdout,stderr=proc.communicate(timeout=10)
        finally:
            fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try: proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.communicate(timeout=2)
        return proc.returncode,stdout,stderr,time.monotonic()-started

    def test_original_physical_admission_lock_consumes_received_budget(self):
        rc,out,err,elapsed=self.remote(1,lock_delay=1.1)
        self.assertEqual(rc,75,err)
        self.assertIn('before_worker=1 stage=admission',err)
        self.assertFalse((self.root/'before-worker.json').exists())
        self.assertFalse((self.ext/'active/offline-remote-deadline').exists())
        self.assertLess(elapsed,4)

    def test_final_preworker_gate_deducts_elapsed_remote_preparation(self):
        rc,out,err,elapsed=self.remote(1,prepare_delay=1.1)
        self.assertEqual(rc,75,err)
        self.assertIn('before_worker=1 stage=launch',err)
        self.assertFalse((self.root/'before-worker.json').exists())
        self.assertFalse((self.ext/'active/offline-remote-deadline').exists())
        self.assertLess(elapsed,4)

    def test_inert_positive_control_receives_only_remaining_remote_duration(self):
        rc,out,err,elapsed=self.remote(3,prepare_delay=0.2)
        self.assertEqual(rc,0,err)
        self.assertEqual(out,'INERT COMPLETE\n')
        launch=json.loads((self.root/'before-worker.json').read_text())
        self.assertGreater(launch['timeout'],0)
        self.assertLess(launch['timeout'],2.85)
        self.assertFalse(launch['origin_clock_in_worker_env'])
        self.assertFalse(launch['commission_envelope_in_worker_env'])
        receipt=json.loads((self.ext/'lanes/offline-remote-deadline.process.jsonl').read_text().splitlines()[-1])
        self.assertTrue(receipt['cleanup']['census_proven'])
        self.assertEqual(receipt['cleanup']['residual_count'],0)


class FullCliDeadline(unittest.TestCase):
    def test_frozen_original_real_cli_case_passes_with_exact_followup_sources(self):
        """Reuse the frozen failing test without rewriting production or red evidence."""
        original_path=ROOT/'tests/fixtures/original_commission_deadline_20261018.py.txt'
        self.assertEqual(hashlib.sha256(original_path.read_bytes()).hexdigest(),
                         '47cdfd98e9f59adf446365e230bf9bc263e3ecbeaddaaef451870f28b2c2b20b')
        spec=importlib.util.spec_from_file_location('frozen_original_deadline',original_path,
            loader=SourceFileLoader('frozen_original_deadline',str(original_path)))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        with tempfile.TemporaryDirectory(prefix='full-cli-',dir=ROOT/'tests') as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            names=(*original.SOURCE_SHA256,'remote_sub_helpers.py','commission_deadline.py',
                   'lane_runtime.py','quota_circuit.py','lease_broker.py')
            for name in names:
                origin=ROOT/'candidate'/name
                if not origin.exists(): origin=ROOT/'source'/name
                shutil.copyfile(origin,source/name)
            original.HERE=root;original.SOURCE=source
            original.SOURCE_SHA256={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in names}
            # Only the existing test interpreter seam changes to supply this
            # sandbox's real namespace census. CLI/request/Bash code is exact.
            def launch(command,**kwargs):
                fixture_root=Path(kwargs['env']['DEADLINE_FIXTURE_ROOT'])
                adapter=fixture_root/'bin/fixture-python'
                write(adapter,'#!'+sys.executable+'\n'+PYTHON_FIXTURE,executable=True)
                kwargs['env']['REMOTE_SUB_PYTHON']=str(adapter)
                proc=subprocess.Popen([str(adapter),*command[2:]],**kwargs)
                communicate=proc.communicate
                def communicate_and_retain(*args,**opts):
                    result=communicate(*args,**opts)
                    stages={}
                    for path in (fixture_root/'ext/state/remote_sub').glob('*.json*'):
                        if path.is_file() and path.stat().st_size<=65536:
                            stages[path.name]=path.read_text()
                    (ROOT/'tests/last-full-cli-request-stages.json').write_text(json.dumps(stages,indent=2)+'\n')
                    return result
                proc.communicate=communicate_and_retain
                return proc
            original.subprocess=SimpleNamespace(Popen=launch,TimeoutExpired=subprocess.TimeoutExpired,
                                                DEVNULL=subprocess.DEVNULL,PIPE=subprocess.PIPE)
            case=original.OriginalDeadline('test_original_budget_bounds_real_cli_broker_wait_before_task_start')
            try:
                case.test_original_budget_bounds_real_cli_broker_wait_before_task_start()
            finally:
                if (root/'last-run.json').exists():
                    shutil.copyfile(root/'last-run.json',ROOT/'tests/last-full-cli-attempt.json')
                if (root/'last-controller.stderr').exists():
                    shutil.copyfile(root/'last-controller.stderr',ROOT/'tests/last-full-cli-attempt.stderr')
            evidence=json.loads((root/'last-run.json').read_text())
            self.assertEqual(evidence['transport_or_task_invocation_count'],0)
            self.assertFalse(evidence['launch_log_present'])
            self.assertEqual(evidence['continuation_finished']['reason'],'commission_time_exhausted')
            (ROOT/'tests/last-full-cli-green.json').write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
            (ROOT/'tests/last-full-cli-green.stderr').write_text((root/'last-controller.stderr').read_text())


if __name__=='__main__':
    unittest.main(verbosity=2)



class PlainPacketRetention(unittest.TestCase):
    """Exercise the candidate's actual retention block without a live controller."""

    def test_same_path_private_custody_and_exclusive_destination_matrix(self):
        source=(ROOT/'candidate/remote_sub.sh').read_text()
        marker="<<'PY_RETAIN_PLAIN_PACKET'\n"
        self.assertEqual(source.count(marker),1)
        block=source.split(marker,1)[1].split('\nPY_RETAIN_PLAIN_PACKET',1)[0]
        cases={
            'fresh_private':True,
            'fresh_public_source':True,
            'same_private':True,
            'same_public_refused':False,
            'same_hardlink_refused':False,
            'same_symlink_refused':False,
            'different_existing_equal_refused':False,
            'different_existing_foreign_refused':False,
            'destination_symlink_refused':False,
            'empty_source_refused':False,
            'oversized_source_refused':False,
            'same_inode_replacement_refused':False,
            'same_content_change_refused':False,
        }
        payload=b'INERT packet-retention fixture; no worker task\n'
        with tempfile.TemporaryDirectory(prefix='plain-retain-') as temporary:
            for case,expected_success in cases.items():
                with self.subTest(case=case):
                    directory=Path(temporary)/case
                    directory.mkdir()
                    incoming=directory/'source.packet'
                    retained=directory/'run.request.packet'
                    incoming.write_bytes(payload)
                    incoming.chmod(0o600)
                    if case.startswith('same_'):
                        incoming.unlink()
                        incoming=retained
                        incoming.write_bytes(payload)
                        incoming.chmod(0o600)
                        write_native_plain_request(directory, 'run', payload)
                    if case=='fresh_public_source':
                        incoming.chmod(0o644)
                    elif case=='same_public_refused':
                        incoming.chmod(0o644)
                    elif case=='same_hardlink_refused':
                        os.link(incoming,directory/'another-link')
                    elif case=='same_symlink_refused':
                        incoming.rename(directory/'actual.packet')
                        incoming.symlink_to(directory/'actual.packet')
                    elif case=='different_existing_equal_refused':
                        retained.write_bytes(payload)
                        retained.chmod(0o600)
                    elif case=='different_existing_foreign_refused':
                        retained.write_bytes(b'another retained packet\n')
                        retained.chmod(0o600)
                    elif case=='destination_symlink_refused':
                        retained.symlink_to(incoming)
                    elif case=='empty_source_refused':
                        incoming.write_bytes(b'')
                    elif case=='oversized_source_refused':
                        incoming.write_bytes(b'x'*(2*1024*1024+1))
                    code=block
                    faulted=case in ('same_inode_replacement_refused','same_content_change_refused')
                    if faulted:
                        # Deterministic adversarial mutation after the real source
                        # read. Product code remains byte-identical otherwise.
                        point='finally:\n    os.close(fd)\n'
                        self.assertEqual(code.count(point),1)
                        if case=='same_inode_replacement_refused':
                            fault="os.rename(source,source+'.saved'); open(source,'wb').write(data); os.chmod(source,0o600)\n"
                        else:
                            fault="with open(source,'wb') as changed: changed.write(b'changed after source read')\n"
                        code=code.replace(point,point+fault,1)
                    def inventory():
                        return {p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),
                                        p.stat().st_ino,p.stat().st_mtime_ns)
                                for p in directory.iterdir() if p.is_file()}
                    before=inventory()
                    result=subprocess.run([sys.executable,'-c',code,str(incoming),str(retained)],
                                          stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10,
                                          env={**os.environ, 'POOL_ORCHESTRATOR_ID':'offline-root',
                                               'POOL_PARENT_RUN_ID':'offline-parent'})
                    self.assertEqual(result.returncode==0,expected_success,result.stderr)
                    if not faulted and (not expected_success or case=='same_private'):
                        self.assertEqual(inventory(),before)
                    if expected_success:
                        self.assertEqual(retained.read_bytes(),payload)
                        self.assertEqual(retained.stat().st_mode & 0o777,0o600)
                    elif case=='same_inode_replacement_refused':
                        self.assertIn('PLAIN_PACKET_RETENTION_CHANGED',result.stderr)
                    elif case=='same_content_change_refused':
                        self.assertIn('PLAIN_PACKET_RETENTION_',result.stderr)


    def test_same_path_original_reservation_falsifiers(self):
        source=(ROOT/'candidate/remote_sub.sh').read_text()
        marker="<<'PY_RETAIN_PLAIN_PACKET'\n"
        self.assertEqual(source.count(marker),1)
        block=source.split(marker,1)[1].split('\nPY_RETAIN_PLAIN_PACKET',1)[0]
        cases=(
            'root_missing','root_empty','root_malformed',
            'parent_missing','parent_empty','parent_malformed',
            'request_root','launch_root','request_parent','launch_parent',
            'request_run','launch_run','packet_name','packet_size','packet_digest',
            'launch_packet_digest','request_digest','launch_state','request_schema','launch_schema',
            'request_missing','launch_missing','request_public','launch_public',
            'request_hardlink','launch_hardlink','request_symlink','launch_symlink',
            'request_duplicate','launch_duplicate','boolean_packet_size',
            'request_swap_during_read','launch_mutation_during_read',
            'request_swap_after_launch','launch_swap_after_packet',
        )
        with tempfile.TemporaryDirectory(prefix='plain-provenance-') as temporary:
            for case in cases:
                with self.subTest(case=case):
                    directory=Path(temporary)/case
                    directory.mkdir(mode=0o700)
                    payload=b'x' if case=='boolean_packet_size' else b'INERT original packet\n'
                    packet=directory/'run.request.packet'
                    packet.write_bytes(payload);packet.chmod(0o600)
                    env={**os.environ,'POOL_ORCHESTRATOR_ID':'offline-root','POOL_PARENT_RUN_ID':'offline-parent'}
                    root_id,parent_id='offline-root','offline-parent'
                    for prefix,key in (('root','POOL_ORCHESTRATOR_ID'),('parent','POOL_PARENT_RUN_ID')):
                        value=None if case==prefix+'_missing' else '' if case==prefix+'_empty' else 'bad/id' if case==prefix+'_malformed' else env[key]
                        if value is None: env.pop(key,None)
                        else: env[key]=value
                        if prefix=='root': root_id=value
                        else: parent_id=value
                    request,launch=write_native_plain_request(directory,'run',payload,root_id,parent_id)
                    request_row=json.loads(request.read_bytes())
                    launch_row=json.loads(launch.read_bytes())
                    request_changes={
                        'request_root':('root_id','other-root'),
                        'request_parent':('parent_run_id','other-parent'),
                        'request_run':('run_id','other-run'),
                        'packet_name':('packet','other.request.packet'),
                        'packet_size':('packet_bytes',len(payload)+1),
                        'boolean_packet_size':('packet_bytes',True),
                        'packet_digest':('packet_sha256','f'*64),
                        'request_schema':('schema','unknown'),
                    }
                    launch_changes={
                        'launch_root':('root_id','other-root'),
                        'launch_parent':('parent_run_id','other-parent'),
                        'launch_run':('run_id','other-run'),
                        'launch_packet_digest':('packet_sha256','f'*64),
                        'request_digest':('request_sha256','f'*64),
                        'launch_state':('state','COMPLETE'),
                        'launch_schema':('schema','unknown'),
                    }
                    if case in request_changes:
                        key,value=request_changes[case];request_row[key]=value
                    request_raw=(json.dumps(request_row,sort_keys=True)+'\n').encode()
                    if case=='request_duplicate':
                        request_raw=b'{"root_id":"ambiguous",'+request_raw[1:]
                    request.write_bytes(request_raw)
                    launch_row['request_sha256']=hashlib.sha256(request_raw).hexdigest()
                    if case in launch_changes:
                        key,value=launch_changes[case];launch_row[key]=value
                    launch_raw=(json.dumps(launch_row,sort_keys=True)+'\n').encode()
                    if case=='launch_duplicate':
                        launch_raw=b'{"request_sha256":"ambiguous",'+launch_raw[1:]
                    launch.write_bytes(launch_raw)
                    for prefix,path in (('request',request),('launch',launch)):
                        if case==prefix+'_missing': path.unlink()
                        elif case==prefix+'_public': path.chmod(0o644)
                        elif case==prefix+'_hardlink': os.link(path,path.with_name(path.name+'.link'))
                        elif case==prefix+'_symlink':
                            saved=path.with_name(path.name+'.saved')
                            path.rename(saved);path.symlink_to(saved)
                    code=block
                    race='_during_read' in case or '_after_' in case
                    if case in ('request_swap_during_read','launch_mutation_during_read'):
                        point='            contents = os.read(descriptor, 32769)\n'
                        self.assertEqual(code.count(point),1)
                        if case=='request_swap_during_read':
                            fault="            if filename.endswith('.request.json'):\n                os.rename(path,path+'.saved'); open(path,'wb').write(contents); os.chmod(path,0o600)\n"
                        else:
                            fault="            if filename.endswith('.request-launch.json'):\n                with open(path,'wb') as changed: changed.write(b' '*len(contents))\n"
                        code=code.replace(point,point+fault,1)
                    elif case=='request_swap_after_launch':
                        point="    launch, _ = read_original_json(run_id + '.request-launch.json')\n"
                        self.assertEqual(code.count(point),1)
                        fault="    path=os.path.join(directory,run_id+'.request.json'); os.rename(path,path+'.saved'); open(path,'wb').write(request_bytes); os.chmod(path,0o600)\n"
                        code=code.replace(point,point+fault,1)
                    elif case=='launch_swap_after_packet':
                        point='    after = os.fstat(check)\n'
                        self.assertEqual(code.count(point),1)
                        fault="    path=os.path.join(directory,run_id+'.request-launch.json'); raw=open(path,'rb').read(); os.rename(path,path+'.saved'); open(path,'wb').write(raw); os.chmod(path,0o600)\n"
                        code=code.replace(point,point+fault,1)
                    def inventory():
                        return {p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),
                                        p.stat().st_ino,p.stat().st_mtime_ns)
                                for p in directory.iterdir() if p.is_file()}
                    before=inventory()
                    result=subprocess.run([sys.executable,'-c',code,str(packet),str(packet)],
                                          env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10)
                    self.assertNotEqual(result.returncode,0,result.stdout)
                    if race:
                        self.assertIn('PRE_RETAINED_REQUEST_SOURCE_CHANGED',result.stderr)
                    else:
                        self.assertEqual(inventory(),before)
