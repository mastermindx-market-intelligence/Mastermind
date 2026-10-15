"""Bounded current-parent observations through the incumbent read transport.
No worker launch, result publication, lease mutation or terminal acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import artifact_delivery as delivery
import artifact_reader as reader

SCHEMA = 'mastermind.fabric_run_observation_request.v1'
SCOPES = {'mm-os-mac-release-review-20261010-01a104e6': {'root': '01a104e6-58f8-76d3-8d99-1302a1cca072', 'host': 'ubuntu1', 'support_digest': '8df7ac415890db623dc24ab9d00a18d0df49dcd9c7a453d43e51014dbff7c499', 'packet_path': '/Volumes/Mastermind/evidence/mastermind-os-noir-product-convergence-20261003-astra-001/production-continuation-20261010/macos-release-review-packet.txt', 'log_sha256': 'ec80f718d72a546a7ad8336baebd216831546ccad742c56295d651e96c208372', 'packet_sha256': '5386102be7859c07235727ca88c471c64c49251cad8547a0adc5118d74ab107a'}, 'native-host-review-22f77378-01a0e0c7': {'root': '01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311', 'host': 'ubuntu2', 'support_digest': '3df14e1a295570df7519adec21acf65eba6dccee80b5ab9c1e6a68a570dfb4c9', 'packet_path': '/Volumes/Mastermind/evidence/mastermind-os-frontier-company-convergence-20260925-sol-001/native-astra-01a0e0c7/native-host-review-22f77378-packet.txt', 'log_sha256': '8d2263486b863398f108ad83432974fc26240c9a2ae5862eb44dc56571c692fb', 'packet_sha256': '898779496051a23123473d58c6c9f599ed4a541898d5a051029583e3da153d49'}}
RESERVED_RUN = 'gmi-w3b-clock-patch-20261010-astra-001'
SCOPES[RESERVED_RUN] = {
    'root': 'theme-fabric-e2e-20261008-sol-001', 'host': 'ubuntu3',
    'support_digest': None,
    'packet_path': '/Users/chriswong/agent-evidence/theme-fabric-e2e-20261008-sol-001/astra-takeover-20261010/w3b-clock-patch-packet.md',
    'packet_sha256': 'ed2b937818040fd2dd72d0d3b04871ff11594e762d27ef53f2f37d9cd186be42',
    'log_sha256': 'a7d47a10bd148ae59e2e577874310f6f0bd0ef2f412a674aa934de5e38afa034',
}
SCOPES['b-f08-alert-race-review-01a128b7-v1'] = {
    'root': '01a128b7-bd2b-7a91-891d-39d38f74ad55', 'host': 'ubuntu3',
    'support_digest': 'afb81a34429f67fcad0f1981ac9014968bde4641cf9f8457a3fc43738ce55a57',
    'packet_path': '/Volumes/Mastermind/evidence/marketontology-fabric-repair-01a128b7/marketontology-consumer/alerts-race-review-packet.txt',
    'packet_sha256': '2554057d5a3f97c2d6b26550846940f6867c9d6842d24558a6700b578ea06431',
    'log_sha256': '525d90fab29639c22a3da36d4c91a80e591b7ebab93b3c9d45e1ed93bb754bf0',
}

# Original parent authorizes one same-run observation after lost controller handle.
# Existing strict reader, no PID probe, no stdout content or lifecycle mutation.
SCOPES['fabric-b-mode-durability-build-01a11e90-v1'] = {'root': '01a11e90-4b5d-7f53-b966-8aaaad38701f', 'host': 'ubuntu0', 'support_digest': '526e8b8ef73cd67e22b7520ed91dfd1d78f4f3de6ec8fc9a38cc5a8302166759', 'packet_path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/fabric-b-mode-durability-build-01a11e90-v1.packet.ihuz9ljt', 'packet_sha256': '72c65d446ae054f3ca1bea6b9674f14138d8b2282d1c6b0b86624d615571eab3', 'log_sha256': '667bfcc6cc59e547f64328d7ef35d57a677b966d0c3699a645e93d5cd266ac5b'}
# One original assigning parent requested this active-run metadata diagnostic.
# Bind the retained launch prefix; later controller polls may append to it.
ACTIVE_RUN = 'mm-os-incident-issuer-custody-preflight-20261013-01a104e6'
SCOPES[ACTIVE_RUN] = {'root': '01a104e6-58f8-76d3-8d99-1302a1cca072', 'parent': '01a104e6-58f8-76d3-8d99-1302a1cca072', 'host': 'ubuntu2', 'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114', 'packet_path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/mm-os-incident-issuer-custody-preflight-20261013-01a104e6.packet.16qpaved', 'packet_sha256': '7c9ec569638e276a47bb311a748b5bdcb3b905e253f031c74bd91676c3078e61', 'log_prefix_bytes': 1693, 'log_prefix_sha256': 'cb5b9ec957b240025a62b5e090967909fb18df00ea65dab58076a51143a9a9dd'}
LIMITS = ['Not an atomic cross-file snapshot', 'Support hashes do not attest a running process',
          'PID presence does not prove original child identity or progress',
          'No lifecycle, acceptance, retry, cancellation, or release decision']


SUPPORT_METADATA_RUN = 'b-f08-alert-race-review-01a128b7-v1'
SUPPORT_METADATA_LIMITS = [
    'Directory metadata only; no file content read',
    'Release content and hashes are not verified; no content identity is proven',
    'Not an atomic directory snapshot',
    'Does not grant strict Reader admission',
    'No lifecycle, acceptance, retry, cancellation, or release decision',
]
SUPPORT_METADATA_MAX_COMPONENTS = 16


class ObservationScopeNotAdmitted(ValueError):
    """A closed historical scope refusal, before destination or transport."""


def request_for(run_id, root, *, support_metadata_only=False):
    scope = SCOPES.get(run_id)
    if scope is None or root != scope['root']:
        raise ObservationScopeNotAdmitted('observation_scope_not_admitted')
    if type(support_metadata_only) is not bool or (support_metadata_only and run_id != SUPPORT_METADATA_RUN):
        raise ValueError('support_metadata_scope_not_admitted')
    request = dict(schema=SCHEMA, run_id=run_id, root=root, host=scope['host'],
                   support_digest=scope['support_digest'], observe_pid=False)
    if run_id == ACTIVE_RUN:
        request['parent'] = scope['parent']
    if support_metadata_only:
        request['support_metadata_only'] = True
    return request


def validate_request(request):
    if (type(request) is not dict or type(request.get('run_id')) is not str
            or type(request.get('root')) is not str or request.get('observe_pid') is not False
            or request != request_for(request.get('run_id'), request.get('root'),
                                      support_metadata_only=request.get('support_metadata_only',False))):
        raise ValueError('observation_request_mismatch')


def qualify_bytes(request, scope, raw):
    """No I/O: retain immutable launch identity while permitting later polls.

    This is provenance from the original parent's retained packet and launch,
    not caller authentication, progress or permission to retry the operation.
    """
    if delivery.digest(raw['packet']) != scope['packet_sha256']:
        raise ValueError('original_observation_sources_changed')
    stable = dict(raw)
    if request['run_id'] == ACTIVE_RUN:
        size = scope['log_prefix_bytes']
        launch = raw['log'][:size]
        if len(launch) != size or delivery.digest(launch) != scope['log_prefix_sha256']:
            raise ValueError('original_launch_prefix_changed')
        first, body = raw['packet'].split(b'\n', 1)
        if not first.startswith(b'FABRIC_ARTIFACT_REQUEST_V1 '):
            raise ValueError('original_packet_header_missing')
        header = reader.strict_json(first.split(b' ', 1)[1])
        if (type(header) is not dict or any(header.get(k) != request[k]
                for k in ('root','parent','run_id','support_digest'))):
            raise ValueError('original_packet_identity_mismatch')
        if header.get('body_sha256') != delivery.digest(body):
            raise ValueError('original_packet_body_mismatch')
        # Stable evidence identity deliberately hashes the prefix, not a growing log.
        stable['log'] = launch
    elif delivery.digest(raw['log']) != scope['log_sha256']:
        raise ValueError('original_observation_sources_changed')
    prefix = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='
              + re.escape(request['run_id']) + ' host=' + re.escape(request['host']) + r'\] (.*)')
    events = [match.group(1) for line in raw['log'].decode().splitlines()
              if (match := re.fullmatch(prefix,line))]
    if request['run_id'] == ACTIVE_RUN:
        for line in raw['log'].decode().splitlines():
            if not re.fullmatch(prefix, line):
                raise ValueError('original_log_identity_or_line_invalid')
        if not raw['log'].endswith(b'\n'):
            raise ValueError('original_log_incomplete')
    versions = [event for event in events if event.startswith('SUPPORT_VERSION_READY ')]
    if request['run_id'] == RESERVED_RUN:
        # This exact reservation predates a recorded support/launch edge. Read
        # only its fixed metadata paths; never infer nonexecution or retry rights.
        if events != ['RUN_RESERVED explicit=1', 'LEASE_WAIT pool=minimax wait=3600',
                      'LEASE_OK pool=minimax']:
            raise ValueError('original_reservation_unconfirmed')
    elif (len(versions)!=1 or 'digest='+request['support_digest']+' ' not in versions[0]
            or [event for event in events if event.startswith('LAUNCH_ATTEMPT ')] != ['LAUNCH_ATTEMPT attempt=1']):
        raise ValueError('original_launch_support_unconfirmed')
    if request['run_id'] == ACTIVE_RUN:
        if ([e for e in events if e.startswith('RUN_RESERVED ')] != ['RUN_RESERVED explicit=1']
                or len([e for e in events if e.startswith('LAUNCH ')]) != 1):
            raise ValueError('original_launch_repeated')
    return stable


def qualify(request, *, observed_log=None):
    validate_request(request)
    scope = SCOPES[request['run_id']]
    paths = {'log': delivery.HERE/'state/remote_sub'/(request['run_id']+'.log'),
             'packet': Path(scope['packet_path']), 'registry': delivery.HERE/'hosts.json',
             'observer': delivery.HERE/'run_observation.py'}
    raw = {key:delivery.local_file(path, 1048576) for key,path in paths.items()}
    stable = qualify_bytes(request, scope, raw)

    registry=reader.strict_json(raw['registry']);entry=registry.get(request['host']) if type(registry) is dict else None
    if (type(entry) is not dict or type(entry.get('ssh_alias')) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',entry['ssh_alias'])):
        raise ValueError('original_host_alias_unavailable')
    after = {key:delivery.local_file(path,1048576) for key,path in paths.items()}
    if qualify_bytes(request, scope, after) != stable:
        raise ValueError('observation_sources_changed')
    if request['run_id'] == ACTIVE_RUN:
        if (not after['log'].startswith(raw['log'])
                or observed_log and not raw['log'].startswith(observed_log[-1])):
            raise ValueError('original_log_rewritten')
        if observed_log is not None:
            observed_log[:] = [after['log']]
    return dict(ssh_alias=entry['ssh_alias'],evidence_sha256={key:delivery.digest(value) for key,value in stable.items()},
                log_binding=('launch_prefix_1693_bytes' if request['run_id']==ACTIVE_RUN else 'complete_log'),
                authority='current original-parent bounded observation request; not historical execution attestation')


def code_for_request(request, *, expected_hash):
    validate_request(request)
    raw=delivery.local_file(delivery.HERE/'run_observation.py',65536)
    if (type(expected_hash) is not str or not re.fullmatch(r'[0-9a-f]{64}',expected_hash)
            or delivery.digest(raw)!=expected_hash):
        raise ValueError('observation_embedded_source_mismatch')
    source=raw.decode()
    # Fixed helper only. No caller-provided code/path/PID/host is evaluated.
    observation_call = (
        'ns["support_metadata"](req["run_id"],req["support_digest"])'
        if request.get('support_metadata_only') is True else
        'ns["observe_reserved"](req["run_id"])'
        if request['run_id'] == RESERVED_RUN else
        'ns["observe"](req["run_id"],req["support_digest"],observe_pid=False)'
    )
    return ('import sys,json,hashlib\nns={"__name__":"_fabric_observation"}\n'
            'exec('+repr(source)+',ns)\n'
            'raw=sys.stdin.buffer.read(8193)\n'
            'assert len(raw)<=8192\n'
            'req=ns["strict_json"](raw)\n'
            'assert req=='+repr(request)+'\n'
            'report='+observation_call+'\n'
            'print(json.dumps({"schema":req["schema"],"request_sha256":hashlib.sha256(json.dumps(req,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"report":report},sort_keys=True,separators=(",",":")))\n')


def _integer(value):
    return type(value) is int and 0<=value<=2**63-1


def _file(value):
    return (type(value) is dict and set(value)=={'device','inode','uid','mode','bytes','mtime_ns'}
            and all(_integer(v) for v in value.values()) and value['mode']<=0o7777)


def _failure(value):
    if type(value) is not dict:
        return False
    if value.get('status') == 'absent':
        return value == {'status': 'absent', 'reason': 'missing_at_observation'}
    return (set(value) <= {'status','reason','errno'}
            and value.get('status') == 'unavailable'
            and type(value.get('reason')) is str
            and re.fullmatch(r'[a-z_]{1,80}',value['reason']) is not None
            and ('errno' not in value or value['errno'] is None or
                 type(value['errno']) is int and 0<value['errno']<=65535))


def _support_metadata_response(report, request):
    fields={'schema','run_id','expected_support_digest','account_uid','status','verdict',
            'metadata_only','content_read','component','expected','observed','failures','reason','errno',
            'account_home','components','limits'}
    if (type(report) is not dict or set(report)!=fields
            or report['schema']!='mastermind.support_directory_metadata.v1'
            or report['run_id']!=request['run_id']
            or report['expected_support_digest']!=request['support_digest']
            or not _integer(report['account_uid']) or report['metadata_only'] is not True
            or report['content_read'] is not False or report['limits']!=SUPPORT_METADATA_LIMITS):
        raise ValueError('support_metadata_report_shape')
    rows=report['components'];home=report['account_home']
    if type(rows) is not list or len(rows)>SUPPORT_METADATA_MAX_COMPONENTS:
        raise ValueError('support_metadata_components')
    if home is None:
        if rows or any(report[k] is not None for k in ('component','expected','observed')):
            raise ValueError('support_metadata_component')
    else:
        if (type(home) is not str or len(home)>256 or not home.startswith('/')
                or home=='/' or '..' in Path(home).parts or str(Path(home))!=home
                or len(Path(home).parts)+4>SUPPORT_METADATA_MAX_COMPONENTS or not rows):
            raise ValueError('support_metadata_home')
        # Home is remote account metadata, not locally attested identity. Require
        # every role/path to be the same contiguous fixed chain derived from it.
        parts=Path(home).parts
        expected_chain=[('filesystem_root','/')]
        path=Path('/')
        for index,part in enumerate(parts[1:],1):
            path=path/part
            expected_chain.append(('account_home' if index==len(parts)-1
                                   else 'account_home_ancestor',str(path)))
        for name,role in (('lanes','lanes'),('support-releases','support-releases'),
                          (request['support_digest'],'release'),('ext','release-ext')):
            path=path/name
            expected_chain.append((role,str(path)))
        if len(rows)>len(expected_chain):
            raise ValueError('support_metadata_components')
        for index,row in enumerate(rows):
            if type(row) is not dict or set(row)!={'component','expected','observed','failures'}:
                raise ValueError('support_metadata_component')
            role,path=expected_chain[index]
            if row['component']!={'role':role,'path':path}:
                raise ValueError('support_metadata_component')
            expected=dict(directory=True,uids=([report['account_uid']] if role=='account_home'
                                              else sorted({0,report['account_uid']})),
                          forbidden_mode_bits=0o022)
            if (type(row['expected']) is not dict or row['expected']!=expected
                    or row['expected'].get('directory') is not True):
                raise ValueError('support_metadata_invariant')
            observed=row['observed'];failures=[]
            if observed is not None:
                if (type(observed) is not dict
                        or set(observed)!={'kind','device','inode','uid','mode','bytes','mtime_ns'}
                        or observed['kind'] not in {'directory','symlink','other'}
                        or not _file({k:v for k,v in observed.items() if k!='kind'})):
                    raise ValueError('support_metadata_observed')
                if observed['kind']!='directory':failures.append('type')
                if observed['uid'] not in expected['uids']:failures.append('uid')
                if observed['mode'] & 0o022:failures.append('mode')
            if row['failures']!=failures or (index<len(rows)-1 and (observed is None or failures)):
                raise ValueError('support_metadata_chain_contradiction')
        last=rows[-1]
        if any(report[k]!=last[k] for k in ('component','expected','observed')):
            raise ValueError('support_metadata_component')
    failures=rows[-1]['failures'] if rows else []
    if report['status']=='observed':
        if (not rows or report['observed'] is None or report['failures']!=failures
                or report['reason'] is not None or report['errno'] is not None
                or report['verdict']!=('INVARIANT_FAILED' if failures else 'CHAIN_VALID')
                or (not failures and len(rows)!=len(expected_chain))):
            raise ValueError('support_metadata_contradiction')
    elif report['status']=='unavailable':
        if (report['verdict']!='UNAVAILABLE' or report['failures']!=[]
                or report['reason'] not in {'os_permission_denied','filesystem_unavailable','directory_changed',
                                           'invalid_account_home','account_home_unavailable'}
                or (report['errno'] is not None and not (type(report['errno']) is int and 0<report['errno']<=65535))
                or (report['reason']=='os_permission_denied' and report['errno'] not in (1,13))
                or (report['reason']=='filesystem_unavailable' and (report['errno'] is None or report['errno'] in (1,13)))
                or (report['reason'] not in {'os_permission_denied','filesystem_unavailable'} and report['errno'] is not None)
                or (home is None and report['reason'] not in {'invalid_account_home','account_home_unavailable'})
                or (home is not None and report['reason'] in {'invalid_account_home','account_home_unavailable'})
                or (failures and report['reason']!='directory_changed')):
            raise ValueError('support_metadata_unavailable')
    else:raise ValueError('support_metadata_status')
    return report


def validate_response(raw,request):
    validate_request(request)
    if len(raw)>16384:raise ValueError('observation_response_limit')
    value=reader.strict_json(raw)
    if (type(value) is not dict or set(value)!={'schema','request_sha256','report'}
            or value['schema']!=SCHEMA or value['request_sha256']!=delivery.digest(reader.canonical(request))):
        raise ValueError('observation_response_binding')
    report=value['report']
    if request.get('support_metadata_only') is True:
        return _support_metadata_response(report,request)
    if (type(report) is not dict or not {'schema','run_id','expected_support_digest','status','observations','limits'}<=set(report)
            or set(report)-{'schema','run_id','expected_support_digest','status','observations','limits','reason','errno','request_stopped','observed_at'}
            or report['schema']!='mastermind.run_observation.v1' or report['run_id']!=request['run_id']
            or report['expected_support_digest']!=request['support_digest']
            or report['status'] not in ('observed','unavailable') or report['limits']!=LIMITS):
        raise ValueError('observation_report_shape')
    if 'reason' in report and (type(report['reason']) is not str or not re.fullmatch(r'[a-z_]{1,80}',report['reason'])):
        raise ValueError('observation_reason_shape')
    if 'errno' in report and not (report['errno'] is None or type(report['errno']) is int and 0<report['errno']<=65535):
        raise ValueError('observation_errno_shape')
    if 'request_stopped' in report and report['request_stopped'] is not True:raise ValueError('observation_stop_shape')
    if 'observed_at' in report:
        from run_observation import timestamp
        timestamp(report['observed_at'])
    observations=report['observations']
    if type(observations) is not dict or set(observations)-{'support','marker','returncode','stdout','process_receipt'}:
        raise ValueError('observation_fields')
    for name,row in observations.items():
        if _failure(row):continue
        if type(row) is not dict or row.get('status')!='observed':raise ValueError('observation_field_shape')
        if name=='support':
            if (set(row)!={'status','digest','verified_code_files','verification','running_process_source_identity_proven','release_links_verified'}
                    or row['digest']!=request['support_digest'] or type(row['verified_code_files']) is not int
                    or row['verified_code_files'] not in ((30,) if request['run_id']==ACTIVE_RUN else (21,23,24))
                    or row['verification']!='manifest_and_fixed_code_hashes'
                    or row['running_process_source_identity_proven'] is not False or row['release_links_verified'] is not False):
                raise ValueError('observation_support_shape')
            continue
        if not _file(row.get('file')):raise ValueError('observation_file_shape')
        if name=='marker':
            if (set(row)-{'reconciliation_hold'}!={'status','file','marker_sha256','pid','started_at','elapsed_since_marker_seconds','source_sha256','process_generation_proven','root_identity_proven'}
                    or not _integer(row['pid']) or not 0<row['pid']<2**31
                    or not re.fullmatch(r'[0-9a-f]{64}',str(row['marker_sha256']))
                    or row['source_sha256'] is not None and not re.fullmatch(r'[0-9a-f]{64}',str(row['source_sha256']))
                    or type(row['elapsed_since_marker_seconds']) not in (int,float) or not 0<=row['elapsed_since_marker_seconds']<1e12
                    or row['process_generation_proven'] is not False or row['root_identity_proven'] is not False):
                raise ValueError('observation_marker_shape')
            from run_observation import timestamp
            started=timestamp(row['started_at'])
            if 'reconciliation_hold' in row:
                hold=row['reconciliation_hold']
                if (type(hold) is not dict or set(hold)!={'schema','reason','held_at','original_lease_key_matches'}
                        or hold['schema']!='mastermind.local_lane_reconciliation_hold.v1'
                        or hold['reason']!='worker_cleanup_unproven' or hold['original_lease_key_matches'] is not True
                        or not started <= timestamp(hold['held_at']) <= timestamp(report.get('observed_at'))):
                    raise ValueError('observation_hold_shape')
        elif name=='returncode':
            if (set(row)!={'status','file','returncode','terminal_acceptance_proven'} or type(row['returncode']) is not int
                    or not 0<=row['returncode']<=255 or row['terminal_acceptance_proven'] is not False):
                raise ValueError('observation_rc_shape')
        elif name=='stdout':
            if (set(row)!={'status','file','content_read','useful_progress_proven'}
                    or row['content_read'] is not False or row['useful_progress_proven'] is not False):
                raise ValueError('observation_stdout_shape')
        elif name=='process_receipt':
            if (set(row)!={'status','file','records','last_record','receipt_sha256','original_child_identity_proven','accepted'}
                    or type(row['records']) is not int or not 1<=row['records']<=64
                    or not re.fullmatch(r'[0-9a-f]{64}',str(row['receipt_sha256']))
                    or row['original_child_identity_proven'] is not False or row['accepted'] is not False):
                raise ValueError('observation_process_shape')
            record=row['last_record'];keys={'pid','started_at','ended_at','returncode','timed_out','stdout_truncated','stderr_truncated','stdout_bytes','stderr_bytes','recorded_cleanup'}
            if (type(record) is not dict or set(record)!=keys or not _integer(record['pid']) or not 0<record['pid']<2**31
                    or type(record['returncode']) is not int or not -255<=record['returncode']<=255
                    or any(type(record[k]) is not bool for k in ('timed_out','stdout_truncated','stderr_truncated'))
                    or any(not _integer(record[k]) for k in ('stdout_bytes','stderr_bytes'))
                    or type(record['recorded_cleanup']) is not dict
                    or set(record['recorded_cleanup'])-{'identity_verified','stdout_capture_complete','stderr_capture_complete','stdin_delivery_complete'}
                    or any(type(v) is not bool for v in record['recorded_cleanup'].values())):
                raise ValueError('observation_process_record_shape')
            from run_observation import timestamp
            if timestamp(record['ended_at'])<timestamp(record['started_at']):raise ValueError('observation_process_time')
    if report['status']=='observed' and (set(observations)!={'support','marker','returncode','stdout','process_receipt'}
            or observations['support']['status']!='observed' or any(v['status']=='unavailable' for v in observations.values())
            or 'request_stopped' in report):
        raise ValueError('observation_overall_contradiction')
    return report


def observe(request,destination):
    observed_log=[]
    evidence=qualify(request,observed_log=observed_log)
    chain=delivery.reserve_destination(destination)
    receipt=dict(schema='mastermind.fabric_run_observation_receipt.v1',request=request,evidence=evidence,
                 state='OBSERVATION_PENDING',files=[],report=None,execution_replayed=False,outcome_accepted=False,
                 effect_state_changed=False,read_transport_state='MAY_START_AFTER_THIS_INTENT')
    def unchanged():
        if qualify(request,observed_log=observed_log)!=evidence:raise ValueError('observation_sources_changed')
    try:
        delivery.write_exclusive(chain.fd,'request.json',reader.canonical(receipt))
        try:
            unchanged();chain.verify();receipt['read_transport_state']='ATTEMPTED_UNCONFIRMED'
            raw=delivery.transport(evidence['ssh_alias'],request,
                                   observer_source_hash=evidence['evidence_sha256']['observer'])
            receipt['read_transport_state']='RESPONSE_RECEIVED'
            report=validate_response(raw,request);unchanged();chain.verify();receipt['report']=report
            if request.get('support_metadata_only') is True:
                receipt['state']=('OBSERVED' if report['verdict']=='CHAIN_VALID' else
                                  'INVARIANT_FAILED' if report['verdict']=='INVARIANT_FAILED' else 'UNAVAILABLE')
            else:
                receipt['state']='OBSERVED' if report['status']=='observed' else 'UNAVAILABLE'
        except (OSError,ValueError,TypeError,KeyError,RecursionError,subprocess.SubprocessError):
            receipt['state']='UNAVAILABLE';receipt['report']=None
        receipt['observed_at_epoch']=time.time()
        delivery.publish_receipt(chain,receipt,{'paths':[]},verify_source=unchanged)
        return receipt
    finally:chain.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_id');p.add_argument('--root',required=True);p.add_argument('--destination',required=True);p.add_argument('--support-metadata-only',action='store_true');args=p.parse_args(argv)
    try:
        receipt=observe(request_for(args.run_id,args.root,support_metadata_only=args.support_metadata_only),args.destination)
        print(reader.canonical(receipt).decode());return 0 if receipt['state']=='OBSERVED' else 76
    except ObservationScopeNotAdmitted:
        print('{"state":"REFUSED","reason":"observation_scope_not_admitted"}');return 75
    except (OSError,ValueError,TypeError,KeyError,RecursionError,subprocess.SubprocessError):
        print('{"state":"REFUSED","reason":"original_run_observation_unconfirmed"}');return 75
