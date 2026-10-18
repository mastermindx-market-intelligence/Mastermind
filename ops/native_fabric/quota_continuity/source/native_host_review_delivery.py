"""Fixed source-bound native review inspector delivery through incumbent owners.

SOURCE-ONLY integration candidate. No transport implementation, provider launch,
lease/broker operation, source export, lifecycle transition or settlement.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

import artifact_delivery as delivery

SCHEMA = 'mastermind.native_host_review_inspection.v1'
RUN_ID = 'native-host-review-22f77378-01a0e0c7'
ROOT_ID = '01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311'
SUPPORT = '3df14e1a295570df7519adec21acf65eba6dccee80b5ab9c1e6a68a570dfb4c9'
INSPECTOR_SHA = 'afedcb6a13407ba75cea91109d720c522f8986763dca820acb06611cce33227a'
LOG_SHA = '8d2263486b863398f108ad83432974fc26240c9a2ae5862eb44dc56571c692fb'
PACKET_SHA = '898779496051a23123473d58c6c9f599ed4a541898d5a051029583e3da153d49'
MARKER_SHA = 'ff7b5bc29d6d2a72a7aa660af75176a2d9b65e12a05005fa5db1f5236c4c6d44'
POLICY_SHA = '489b803867dda091f8b9cd46b62917f0b33b1d5602602e7681729ce0a060ae13'
STDOUT_SHA = hashlib.sha256(b'REMOTE_CLEANUP_UNPROVEN OSError\n').hexdigest()
PACKET_PATH = Path('/Volumes/Mastermind/evidence/mastermind-os-frontier-company-convergence-20260925-sol-001/native-astra-01a0e0c7/native-host-review-22f77378-packet.txt')
REQUEST = dict(schema=SCHEMA, action='inspect', run_id=RUN_ID, root_id=ROOT_ID,
               host='ubuntu2', support_digest=SUPPORT)
MAX_RESPONSE = 16384
HEX = re.compile(r'[0-9a-f]{64}\Z')
CODE_NAMES = ('remote_sub_exec.py','lane_runtime.py','native_remote.py')
SIGNATURES = {'packet_read_text_utf8','ordinary_prompt_is_single_argument',
              'conditional_native_override_present','owned_process_called_with_command',
              'popen_called_with_command','minimax_is_not_native_override'}
LIMITS = ['Not an atomic cross-file snapshot',
          'Current metadata is not historical execution attestation',
          'Static source fingerprints do not attest running process source',
          'Marker PID presence or absence does not prove original child identity',
          'Argument size alone does not prove the historical exception errno',
          'No census of descendants or other potentially surviving processes',
          'No settlement eligibility, lease clearance, acceptance, retry or release decision']
FALSE_FLAGS = {'execution_replayed','effect_state_changed','settlement_eligible','accepted'}
BASE_KEYS = {'schema','run_id','root_id','host','support_digest','original_lease_id',
             'action','status','observations','limits'} | FALSE_FLAGS


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _strict_json(raw):
    value = delivery.reader.strict_json(raw)
    def finite(item):
        if type(item) is float:
            _require(math.isfinite(item), 'nonfinite_json')
        elif type(item) is list:
            for child in item:finite(child)
        elif type(item) is dict:
            for child in item.values():finite(child)
    finite(value)
    return value


def request_for(run_id=RUN_ID, root_id=ROOT_ID):
    _require(type(run_id) is str and type(root_id) is str
             and (run_id, root_id) == (RUN_ID, ROOT_ID), 'inspection_scope_not_admitted')
    return REQUEST.copy()


def validate_request(request):
    _require(type(request) is dict and request == REQUEST
             and all(type(v) is str for v in request.values()), 'inspection_request_mismatch')


def qualify(request):
    """Current read intent and exact retained evidence, without a settlement gate."""
    validate_request(request)
    paths = dict(log=delivery.HERE/'state/remote_sub'/(RUN_ID+'.log'), packet=PACKET_PATH,
                 stdout=delivery.HERE/'lanes'/(RUN_ID+'.remote.stdout'),
                 registry=delivery.HERE/'hosts.json',
                 inspector=delivery.HERE/'native_host_review_reconcile.py',
                 delivery_source=Path(__file__).absolute())
    raw = {key:delivery.local_file(path, 1048576) for key,path in paths.items()}
    expected = dict(log=LOG_SHA, packet=PACKET_SHA, stdout=STDOUT_SHA, inspector=INSPECTOR_SHA)
    _require(all(delivery.digest(raw[key]) == digest for key,digest in expected.items()),
             'original_inspection_sources_changed')
    _require(len(raw['packet']) == 201147 and len(raw['stdout']) == 32, 'original_source_size')
    pattern = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='
               +re.escape(RUN_ID)+r' host=ubuntu2\] (.*)')
    events=[]
    for line in raw['log'].decode('utf-8').splitlines():
        match=re.fullmatch(pattern,line)
        _require(match is not None, 'original_log_scope')
        events.append(match.group(1))
    expected_events = {
        'SUPPORT_VERSION_READY ':f'SUPPORT_VERSION_READY digest={SUPPORT} policy={POLICY_SHA}',
        'LAUNCH_ATTEMPT ':'LAUNCH_ATTEMPT attempt=1',
        'REMOTE_DONE ':'REMOTE_DONE rc=76',
        'REMOTE_EFFECT_UNKNOWN ':'REMOTE_EFFECT_UNKNOWN worker_rc=76 same_run_reconciliation_required=1',
        'DONE ':'DONE rc=76 signal=effect_unknown reason=remote_cleanup_unproven',
        'LEASE_PRESERVED ':'LEASE_PRESERVED effect_unknown=1 lease=b17b0ca31f28'}
    _require(all([event for event in events if event.startswith(prefix)] == [expected]
                 for prefix,expected in expected_events.items()), 'original_support_or_effect_join')
    registry=_strict_json(raw['registry'])
    entry=registry.get('ubuntu2') if type(registry) is dict else None
    _require(type(entry) is dict and type(entry.get('ssh_alias')) is str
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',entry['ssh_alias']) is not None,
             'original_host_alias_unavailable')
    _require(all(delivery.local_file(path,1048576) == raw[key] for key,path in paths.items()),
             'inspection_source_snapshot_changed')
    return dict(ssh_alias=entry['ssh_alias'], evidence_sha256={key:delivery.digest(value) for key,value in raw.items()},
                support_digest=SUPPORT, inspector_sha256=INSPECTOR_SHA,
                authority='current fixed-operation bounded observation; not historical execution or settlement attestation')


def code_for_request(request, *, expected_hash):
    validate_request(request)
    _require(type(expected_hash) is str and expected_hash == INSPECTOR_SHA,
             'inspection_source_head_binding')
    source=delivery.local_file(delivery.HERE/'native_host_review_reconcile.py',65536)
    _require(delivery.digest(source) == INSPECTOR_SHA, 'inspection_embedded_source_changed')
    # Dataclass annotations require a registered module. Nothing from the caller
    # chooses this module, its source, filename, request, or paths.
    return ('import sys,json,hashlib,types\n'
            'source='+repr(source)+'\n'
            'assert hashlib.sha256(source).hexdigest()=='+repr(INSPECTOR_SHA)+'\n'
            'module=types.ModuleType("_fixed_native_review_inspector")\n'
            'module.__file__="native_host_review_reconcile.py"\n'
            'sys.modules[module.__name__]=module\n'
            'exec(compile(source,module.__file__,"exec"),module.__dict__)\n'
            'raw=sys.stdin.buffer.read(8193)\n'
            'assert len(raw)<=8192\n'
            'request=module.strict_json(raw)\n'
            'assert request=='+repr(REQUEST)+'\n'
            'report=module.host_inspect(request)\n'
            'canonical=lambda value:json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()\n'
            'wrapped={"schema":'+repr(SCHEMA)+',"request_sha256":hashlib.sha256(canonical(request)).hexdigest(),'
            '"source_sha256":'+repr(INSPECTOR_SHA)+',"report":report}\n'
            'print(canonical(wrapped).decode())\n')


def _int(value, low=0, high=2**64-1):
    return type(value) is int and low<=value<=high


def _hash(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _file(value, *, size=None, mode=None):
    _require(type(value) is dict and set(value)=={'device','inode','uid','mode','bytes','mtime_ns'}
             and all(_int(v) for v in value.values()) and value['uid']==1000
             and value['mode']<=0o7777 and not value['mode'] & 0o022
             and (size is None or value['bytes']==size) and (mode is None or value['mode']==mode),
             'inspection_file_shape')


def _failure(row, *, pid=False):
    if type(row) is not dict:
        return False
    if row.get('status')=='absent':
        expected=dict(status='absent',reason='missing_at_observation')
        if pid:
            expected.update(observed_pid_present=False,original_child_identity_proven=False)
        _require(row == expected and all(type(row[k]) is type(v) for k,v in expected.items()),
                 'inspection_absence_shape')
        return True
    if row.get('status')=='unavailable':
        reason=row.get('reason')
        if reason=='filesystem_error':
            _require(set(row)=={'status','reason','errno'}
                     and (row['errno'] is None or _int(row['errno'],1,65535)), 'inspection_failure_errno')
        else:
            _require(set(row)=={'status','reason'} and reason in (
                     {'validation_failed','validated_marker_required'} if pid else {'validation_failed'}),
                     'inspection_failure_shape')
        return True
    return False


def _timestamp(value):
    _require(type(value) is str and len(value)<=40, 'inspection_timestamp_shape')
    try:
        timestamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        _require(timestamp.tzinfo is not None,'inspection_timestamp_timezone')
        return timestamp.astimezone(timezone.utc)
    except (ValueError,OverflowError):
        raise ValueError('inspection_timestamp_shape') from None


def _kernel(row):
    _require(set(row)=={'status','host','system','machine','release','page_size',
             'filesystem_encoding','uid','boot_id','historical_kernel_identity_proven'}
             and row['host']=='ubuntu2' and row['system']=='Linux' and row['machine']=='x86_64'
             and _int(row['uid']) and row['uid']==1000 and _int(row['page_size']) and row['page_size']==4096
             and type(row['release']) is str and re.fullmatch(r'[A-Za-z0-9_.+-]{1,120}',row['release'])
             and type(row['filesystem_encoding']) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,40}',row['filesystem_encoding'])
             and type(row['boot_id']) is str and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',row['boot_id'])
             and row['historical_kernel_identity_proven'] is False, 'inspection_kernel_shape')


def _support(row):
    _require(set(row)=={'status','manifest_file','manifest_sha256','digest','verified_source_sha256',
             'verified_code_files','full_release_code_verified','release_links_verified',
             'signatures','ast_sha256','execution_path_attested'} and row['digest']==SUPPORT
             and _hash(row['manifest_sha256']) and type(row['verified_code_files']) is int
             and row['verified_code_files']==3 and row['full_release_code_verified'] is False
             and row['release_links_verified'] is False and row['execution_path_attested'] is False,
             'inspection_support_shape')
    _file(row['manifest_file'],mode=0o444)
    for key in ('verified_source_sha256','ast_sha256'):
        _require(type(row[key]) is dict and set(row[key])==set(CODE_NAMES)
                 and all(_hash(v) for v in row[key].values()), 'inspection_source_hash_shape')
    _require(type(row['signatures']) is dict and set(row['signatures'])==SIGNATURES
             and all(type(v) is bool for v in row['signatures'].values()), 'inspection_signature_shape')


def _packet(row):
    _require(set(row)=={'status','file','sha256','decoded_utf8_argument_bytes_including_nul',
             'linux_max_single_argument_bytes','single_argument_exceeds_limit','historical_exec_errno_proven'}
             and row['sha256']==PACKET_SHA and _int(row['decoded_utf8_argument_bytes_including_nul'],1,201148)
             and type(row['linux_max_single_argument_bytes']) is int
             and row['linux_max_single_argument_bytes']==131072
             and type(row['single_argument_exceeds_limit']) is bool
             and row['single_argument_exceeds_limit']==(row['decoded_utf8_argument_bytes_including_nul']>131072)
             and row['historical_exec_errno_proven'] is False,'inspection_packet_shape')
    _file(row['file'],size=201147)


def _marker(row):
    _require(set(row)=={'status','file','sha256','pid','started_at','held_at','source_sha256',
             'root_identity_proven','lease_identity_proven','original_child_identity_proven'}
             and row['sha256']==MARKER_SHA and type(row['pid']) is int and row['pid']==2553528
             and row['source_sha256'] is None and all(row[k] is False for k in (
                 'root_identity_proven','lease_identity_proven','original_child_identity_proven')),
             'inspection_marker_shape')
    _file(row['file'],size=647)
    _require(row['file']['device']==66307 and row['file']['inode']==24547401,'inspection_marker_inode')
    _require(_timestamp(row['started_at'])==_timestamp('2026-10-11T05:47:53.290Z')
             and _timestamp(row['held_at'])==_timestamp('2026-10-11T05:47:53.297Z'),'inspection_marker_time')


def _returncode(row):
    _require(set(row)=={'status','file','sha256','returncode','accepted'}
             and type(row['returncode']) is int and row['returncode']==76 and row['accepted'] is False
             and row['sha256']==delivery.digest(b'76\n'),'inspection_returncode_shape')
    _file(row['file'],size=3)


def _stdout(row):
    _require(set(row)=={'status','file','sha256','fixed_cleanup_diagnostic_matches','content_returned',
             'provider_output_read','accepted'} and row['sha256']==STDOUT_SHA
             and row['fixed_cleanup_diagnostic_matches'] is True and all(row[k] is False
             for k in ('content_returned','provider_output_read','accepted')),'inspection_stdout_shape')
    _file(row['file'],size=32)


def _pid(row, marker):
    _require(set(row)=={'status','observed_pid_present','pid','uid','state','start_ticks',
             'original_child_identity_proven','useful_progress_proven','argv_read','environ_read'}
             and row['observed_pid_present'] is True and type(row['pid']) is int
             and row['pid']==marker.get('pid') and type(row['uid']) is int and row['uid']==1000
             and type(row['state']) is str and row['state'] in set('RSDZTtXxKWPI')
             and _int(row['start_ticks']) and all(row[k] is False for k in (
             'original_child_identity_proven','useful_progress_proven','argv_read','environ_read')),
             'inspection_pid_shape')


def _artifacts(row):
    _require(set(row)=={'status','artifacts','absence_is_only_current_observation'}
             and row['absence_is_only_current_observation'] is True and type(row['artifacts']) is dict
             and set(row['artifacts'])=={'process.jsonl','usage.json'},'inspection_artifact_shape')
    for artifact in row['artifacts'].values():
        if _failure(artifact):continue
        _require(type(artifact) is dict and set(artifact)=={'status','file','content_read','accepted'}
                 and artifact['status']=='observed' and artifact['content_read'] is False
                 and artifact['accepted'] is False,'inspection_artifact_presence_shape')
        _file(artifact['file'])


def validate_response(raw,request):
    validate_request(request)
    _require(type(raw) is bytes and len(raw)<=MAX_RESPONSE,'inspection_response_limit')
    value=_strict_json(raw)
    _require(type(value) is dict and set(value)=={'schema','request_sha256','source_sha256','report'}
             and value['schema']==SCHEMA and value['request_sha256']==delivery.digest(canonical(request))
             and value['source_sha256']==INSPECTOR_SHA,'inspection_response_binding')
    report=value['report']
    _require(type(report) is dict and BASE_KEYS<=set(report)
             and not set(report)-BASE_KEYS-{'reason','errno','request_stopped'}
             and all(report[key]==request[key] and type(report[key]) is str for key in REQUEST)
             and report['original_lease_id']=='b17b0ca31f28' and type(report['original_lease_id']) is str
             and report['status'] in ('observed','unavailable') and report['limits']==LIMITS
             and all(report[k] is False for k in FALSE_FLAGS),'inspection_report_shape')
    if 'reason' in report:
        _require(report['reason'] in {'os_permission_denied','filesystem_unavailable',
                 'final_custody_check_failed','fixed_host_surface_unavailable'},'inspection_report_reason')
    if 'errno' in report:
        _require(report['errno'] is None or _int(report['errno'],1,65535),'inspection_report_errno')
    if 'request_stopped' in report:
        _require(report['request_stopped'] is True and report['status']=='unavailable'
                 and 'reason' in report,'inspection_stop_shape')
    if 'reason' in report or 'errno' in report:
        _require(report.get('request_stopped') is True,'inspection_failure_stop_binding')
    obs=report['observations'];fields={'kernel','support','packet','marker','returncode','stdout','pid','artifacts'}
    _require(type(obs) is dict and not set(obs)-fields,'inspection_observation_fields')
    validators={'kernel':_kernel,'support':_support,'packet':_packet,'marker':_marker,
                'returncode':_returncode,'stdout':_stdout,'artifacts':_artifacts}
    for name,row in obs.items():
        if _failure(row,pid=name=='pid'):continue
        _require(type(row) is dict and row.get('status')=='observed','inspection_observation_shape')
        if name=='pid':
            _require(obs.get('marker',{}).get('status')=='observed','inspection_pid_marker_binding')
            _pid(row,obs['marker'])
        else:validators[name](row)
    if obs.get('packet',{}).get('status')=='observed':
        _require(obs.get('kernel',{}).get('status')=='observed'
                 and obs['kernel']['filesystem_encoding']=='utf-8','inspection_packet_kernel_binding')
    if obs.get('pid',{}).get('status') in ('observed','absent'):
        _require(obs.get('marker',{}).get('status')=='observed','inspection_pid_marker_binding')
    if set(obs)-{'kernel'}:
        _require(obs.get('kernel',{}).get('status')=='observed','inspection_kernel_stage')
    if set(obs)-{'kernel','support'}:
        _require(obs.get('support',{}).get('status')=='observed','inspection_support_stage')
    ready=(set(obs)==fields and all(obs[name]['status']=='observed' for name in fields-{'pid'})
           and obs['pid']['status'] in ('observed','absent')
           and all(v['status'] in ('observed','absent') for v in obs['artifacts'].get('artifacts',{}).values()))
    _require((report['status']=='observed') == (ready and report.get('request_stopped') is not True),
             'inspection_overall_contradiction')
    return report


def inspect_run(request,destination):
    evidence=qualify(request)
    chain=delivery.reserve_destination(destination)
    receipt=dict(schema='mastermind.native_host_review_inspection_receipt.v1',request=request,
                 evidence=evidence,state='INSPECTION_PENDING',files=[],report=None,
                 execution_replayed=False,outcome_accepted=False,effect_state_changed=False,
                 settlement_eligible=False,read_transport_state='MAY_START_AFTER_THIS_INTENT')
    def unchanged():
        try:
            _require(qualify(request)==evidence,'inspection_sources_changed')
        except (OSError,ValueError,TypeError,KeyError,RecursionError):
            receipt['report']=None;receipt['state']='UNAVAILABLE'
            raise
    try:
        delivery.write_exclusive(chain.fd,'request.json',canonical(receipt))
        try:
            unchanged();chain.verify();receipt['read_transport_state']='ATTEMPTED_UNCONFIRMED'
            raw=delivery.transport(evidence['ssh_alias'],request,observer_source_hash=INSPECTOR_SHA)
            receipt['read_transport_state']='RESPONSE_RECEIVED'
            report=validate_response(raw,request);unchanged();chain.verify();receipt['report']=report
            receipt['state']='OBSERVED' if report['status']=='observed' else 'UNAVAILABLE'
        except (OSError,ValueError,TypeError,KeyError,RecursionError,delivery.subprocess.SubprocessError):
            receipt['state']='UNAVAILABLE';receipt['report']=None
        receipt['observed_at_epoch']=time.time()
        delivery.publish_receipt(chain,receipt,{'paths':[]},verify_source=unchanged)
        return receipt
    finally:chain.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id');parser.add_argument('--root',required=True)
    parser.add_argument('--destination',required=True);args=parser.parse_args(argv)
    try:
        receipt=inspect_run(request_for(args.run_id,args.root),args.destination)
        print(canonical(receipt).decode());return 0 if receipt['state']=='OBSERVED' else 76
    except (OSError,ValueError,TypeError,KeyError,RecursionError,delivery.subprocess.SubprocessError):
        print('{"state":"REFUSED","reason":"original_host_inspection_unconfirmed"}');return 75


if __name__=='__main__':
    raise SystemExit(main())
