"""Same-run artifact reads owned by fabric_task/remote_sub; no worker lifecycle."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shlex
import sqlite3
import stat
import subprocess
import sys
import time

import artifact_reader as reader

HERE = Path(__file__).resolve().parent
DESTINATION_ROOT = Path("/Volumes/Mastermind/evidence")
CAPSULE_SOURCE_FILES = {'declaration': {'path': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/capsule-path-correction-20261011/CURRENT_PARENT_DECLARATION.json',
                 'sha256': '1a01c365cba51e636c764af148e02d7ee0da4a356b546c3a5f7d1d26247353ce'},
 'log': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/paper-01a1101f-im08-im09-contract-repair-r2.log',
         'sha256': '6d52f4e8381fe9658345daa5cc51ee89b986a66c256527b9dbbc1f22a4d16f30'},
 'manifest': {'path': '/Volumes/Mastermind/evidence/paper-waves-20261006-01a1101f/im08-im09-contract-repair-r2/work/INPUT_MANIFEST.json',
              'sha256': '61718b268b85afe04d977480946825efe96905ff109be54e131b19f0f5df5b19'},
 'packet': {'path': '/Volumes/Mastermind/evidence/paper-waves-20261006-01a1101f/im08-im09-contract-repair-r2/packet.md',
            'sha256': '93d07465d957f55b3e46fe41b5306ec832eda797ff567bf324fb4596cd5d5a9c'},
 'process': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/paper-01a1101f-im08-im09-contract-repair-r2.process.jsonl',
             'sha256': 'c5ce64c0a2d521629ecb0b9c330425ea9eec04aa5e9b8052dc43e9b371805fb0'},
 'stdout': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/lanes/paper-01a1101f-im08-im09-contract-repair-r2.remote.stdout',
            'sha256': 'a8800c6883b74faaa78accb475c83d0abdabdb617549d65768276f4be52764ba'}}


BRIDGE_SOURCE_FILES = {'declaration': {'path': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/paper-bridge-recovery-20261011/CURRENT_PARENT_DECLARATION.json',
                 'sha256': 'b0f5fd0acdfdaac533a897c9c704a695d6dd26b07185eeae712ecafd05580b2c'},
 'log': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/paper-01a1101f-intl-owner-bridge-build-r1.log',
         'sha256': '99adb751c39e9bb4c2e3cf8b45a8898da4ae2ddf2408a8dd6f364c35bd160157'},
 'manifest': {'path': '/Volumes/Mastermind/evidence/paper-waves-20261006-01a1101f/intl-owner-bridge-r1/INPUT_HASHES.json',
              'sha256': '4542ebad98b604947aa1472b6ebc240712496b09cebe7d6eafdd25b8396cd134'},
 'packet': {'path': '/Volumes/Mastermind/evidence/paper-waves-20261006-01a1101f/intl-owner-bridge-r1/WORKER.md',
            'sha256': '64c2f63f59eb666c37d666c205146abed9c0f20a806c5e63499dd95d739eafeb'},
 'process': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub/paper-01a1101f-intl-owner-bridge-build-r1.process.jsonl',
             'sha256': 'e79fec04b57fed48b09858de8423e1bf235c96f858a438ef5b746f5f00423026'},
 'stdout': {'path': '/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/lanes/paper-01a1101f-intl-owner-bridge-build-r1.remote.stdout',
            'sha256': '7d9ec40d6dfbc2dc29fd3e99ba27e737ce9166ef650f8945bf9c74ffedf59070'}}


def validate_capsule_process(raw, stdout, run_id):
    row = reader.strict_json(raw)
    if (type(row) is not dict or row.get('schema')!='mastermind.local_owned_process_receipt.v1'
            or row.get('label')!=run_id or type(row.get('returncode')) is not int
            or row['returncode']!=0 or row.get('timed_out') is not False
            or type(row.get('pid')) is not int or row['pid']<=0
            or type(row.get('pgid')) is not int or row['pgid']!=row['pid']
            or type(row.get('stdout_bytes')) is not int or row['stdout_bytes']!=len(stdout)
            or type(row.get('stderr_bytes')) is not int or row['stderr_bytes']<0
            or row.get('stdout_truncated') is not False or row.get('stderr_truncated') is not False
            or 'runtime_failure_code' not in row or row['runtime_failure_code'] is not None):
        raise ValueError('ordinary_process_unqualified')
    try:
        start=datetime.fromisoformat(row['started_at'].replace('Z','+00:00'))
        end=datetime.fromisoformat(row['ended_at'].replace('Z','+00:00'))
        if start.tzinfo is None or end.tzinfo is None or end<start:
            raise ValueError('process_time_invalid')
    except (KeyError,AttributeError,TypeError) as exc:
        raise ValueError('process_time_invalid') from exc
    cleanup=row.get('cleanup')
    if (type(cleanup) is not dict or cleanup.get('identity_verified') is not True
            or cleanup.get('census_proven') is not True
            or type(cleanup.get('residual_count')) is not int or cleanup['residual_count']!=0
            or cleanup.get('status') not in ('not_needed','terminated')
            or 'error_code' not in cleanup or cleanup['error_code'] is not None):
        raise ValueError('ordinary_cleanup_unproven')
    if 'session_id' in cleanup or cleanup['status']=='terminated':
        if type(cleanup.get('session_id')) is not int or cleanup['session_id']!=row['pgid']:
            raise ValueError('ordinary_cleanup_identity')
    for stem in ('stdin_delivery','stdout_capture','stderr_capture'):
        if (cleanup.get(stem+'_complete') is not True or stem+'_error' not in cleanup
                or cleanup[stem+'_error'] is not None):
            raise ValueError('ordinary_capture_unproven')


def assert_capsule_family(run_id):
    suffixes = ('native-terminal.json','go-run.json','go-worker.json','go-transport.json',
                'go-ssh.jsonl','go-terminal-read.jsonl','go-worker.raw.log')
    with DirectoryChain(HERE/'state/remote_sub') as chain:
        for suffix in suffixes:
            try:os.stat(run_id+'.'+suffix,dir_fd=chain.fd,follow_symlinks=False)
            except FileNotFoundError:continue
            raise ValueError('mixed_capsule_settlement_family')
        chain.verify()


def qualify_capsule(request):
    """Join source-admitted CURRENT read intent; no historical lease seal claim."""
    import fabric_task
    reader.validate_capsule_request(request)
    rid=request['run_id']
    bridge = rid == reader.BRIDGE_INTENT['run_id']
    source_files = BRIDGE_SOURCE_FILES if bridge else CAPSULE_SOURCE_FILES
    mode = 'minimax' if bridge else 'glm'
    area = 'account_home_exact_file' if bridge else 'capsule_root'
    assert_capsule_family(rid)
    raw={name:local_file(Path(item['path'])) for name,item in source_files.items()}
    if set(raw)!={'declaration','packet','manifest','log','process','stdout'}:
        raise ValueError('capsule_binding_source_incomplete')
    if any(digest(raw[name])!=item['sha256'] for name,item in source_files.items()):
        raise ValueError('capsule_binding_source_changed')
    if (digest(raw['declaration'])!=request['declaration_sha256']
            or digest(raw['stdout'])!=request['stdout_sha256']):
        raise ValueError('capsule_declaration_or_stdout_mismatch')
    declaration=reader.strict_json(raw['declaration'])
    if (type(declaration) is not dict or any(declaration.get(key)!=request[key]
            for key in ('run_id','root','parent','host','cwd'))
            or declaration.get('allowed_names')!=request['names']
            or declaration.get('source_thread')!=request['root']
            or declaration.get('area')!=area
            or (bridge and declaration.get('expected_sizes')!=request['expected_sizes'])
            or declaration.get('declaration_kind')!='CURRENT_BOUNDED_READ_INTENT'
            or declaration.get('historical_packet_manifest_lease_seal')!='NOT_RETAINED'
            or declaration.get('output_hash_seal')!='NOT_RETAINED'
            or declaration.get('live_effect_authorized_by_this_record_alone') is not False):
        raise ValueError('capsule_declaration_scope_mismatch')
    # The hashes above pin actual retained bytes. These semantic checks also
    # expose the original host/cwd/one-launch settlement join to reviewers.
    prefix=(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='+re.escape(rid)
            +' host='+re.escape(request['host'])+r'\] (.*)')
    events=[]
    for line in raw['log'].decode('utf-8').splitlines():
        match=re.fullmatch(prefix,line)
        if match:events.append(match.group(1))
    launch=f"LAUNCH stdout=lanes_{rid}.stdout rc_file=ext/lanes_{rid}.rc cwd={request['cwd']}"
    if ([e for e in events if e.startswith('LAUNCH ')]!=[launch]
            or [e for e in events if e.startswith('LAUNCH_ATTEMPT ')]!=['LAUNCH_ATTEMPT attempt=1']
            or [e for e in events if e.startswith('REMOTE_DONE ')]!=['REMOTE_DONE rc=0']
            or [e for e in events if e.startswith('DONE ')]!=['DONE rc=0 signal=ok']):
        raise ValueError('capsule_original_launch_or_settlement_mismatch')
    validate_capsule_process(raw['process'],raw['stdout'],rid)
    try:status=fabric_task.inspect_run(rid)
    except fabric_task.FabricTaskError as exc:
        raise ValueError('incumbent_status_unavailable') from exc
    if (status['state']!='TERMINAL' or type(status['rc']) is not int or status['rc']!=0
            or status['signal']!='ok' or status['result_available'] is not True
            or status.get('root_id')!=request['root'] or status.get('parent_run_id')!=request['parent']
            or status.get('acceptance_state') not in ('ACCEPTED','NOT_ACCEPTED')):
        raise ValueError('capsule_strict_run_projection_unqualified')
    registry=local_file(HERE/'hosts.json')
    registry_value=reader.strict_json(registry)
    if type(registry_value) is not dict:
        raise ValueError('capsule_receiver_registry_shape')
    entry=registry_value.get(request['host'])
    if (type(entry) is not dict or mode not in entry.get('allowed_modes',[])
            or type(entry.get('ssh_alias')) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',entry['ssh_alias'])):
        raise ValueError('capsule_receiver_registry_mismatch')
    if any(local_file(Path(item['path']))!=raw[name] for name,item in source_files.items()):
        raise ValueError('capsule_provenance_changed_during_qualification')
    assert_capsule_family(rid)
    return {'evidence_sha256':{name:digest(value) for name,value in raw.items()},
            'registry_sha256':digest(registry),'ssh_alias':entry['ssh_alias'],
            'settlement_family':'ordinary_'+mode,'original_projection':status,
            'lease_id':None,'account':None,'historical_joint_seal':'NOT_RETAINED',
            'authority':'source-admitted current task-owner intent; not producer attestation'}


def validate_capsule_response(raw, request):
    reader.validate_capsule_request(request)
    if len(raw)>reader.MAX_RESPONSE:raise ValueError('response_limit')
    value=reader.strict_json(raw)
    if (type(value) is not dict or value.get('schema')!=reader.CAPSULE_SCHEMA
            or value.get('request_sha256')!=digest(reader.canonical(request))):
        raise ValueError('capsule_response_identity')
    legacy={'paths':reader.capsule_paths(request)}
    converted=dict(value,schema=reader.SCHEMA,request_sha256=digest(reader.canonical(legacy)))
    return validate_response(reader.canonical(converted),legacy)


def export_capsule(request, destination):
    evidence=qualify_capsule(request)
    paths={'paths':reader.capsule_paths(request)}
    chain=reserve_destination(destination)
    receipt={'schema':'mastermind.fabric_capsule_current_export.v1','request':request,
             'evidence':evidence,'destination':str(destination),'state':'READ_PENDING','files':[],
             'historical_worker_bytes_attested':False,'execution_replayed':False,'outcome_accepted':False,
             'read_transport_state':'MAY_START_AFTER_THIS_INTENT',
             'provenance':'Current bytes under the source-admitted task-owner capsule intent; no completion-time hash, historical lease/account binding, or joint packet seal.'}
    def unchanged():
        if qualify_capsule(request)!=evidence:raise ValueError('capsule_source_changed')
    try:
        write_exclusive(chain.fd,'request.json',reader.canonical(receipt))
        try:
            unchanged();chain.verify()
            receipt['read_transport_state']='ATTEMPTED_UNCONFIRMED'
            raw=transport(evidence['ssh_alias'],request)
            receipt['read_transport_state']='RESPONSE_RECEIVED'
            files=validate_capsule_response(raw,request)
            unchanged();chain.verify()
            for item,data in files:
                entry=dict(item)
                if data is not None:
                    name=item['path'].rsplit('/',1)[1]
                    write_exclusive(chain.fd,name,data);entry['local_name']=name
                receipt['files'].append(entry)
                verify_delivered(chain,receipt['files'])
            receipt['state']='COMPLETE' if all(i['status']=='RETRIEVED' for i in receipt['files']) else 'PARTIAL'
        except (OSError,ValueError,TypeError,KeyError,RecursionError,subprocess.SubprocessError,sqlite3.Error):
            unavailable(receipt,paths)
        receipt['observed_at_epoch']=time.time()
        # Keep provenance revalidation inside the held-inode publication scope,
        # so a changed original carrier cannot leave a COMPLETE receipt.
        verify_source=unchanged if receipt['state'] in ('COMPLETE','PARTIAL') else None
        publish_receipt(chain,receipt,paths,verify_source=verify_source)
        return receipt
    finally:chain.close()


def validate_capsule_diagnosis(raw, envelope):
    if len(raw) > 4096:
        raise ValueError('diagnosis_response_limit')
    value = reader.strict_json(raw)
    if (type(value) is not dict or set(value) != {'schema', 'request_sha256', 'result'}
            or value['schema'] != reader.CAPSULE_DIAG_SCHEMA
            or value['request_sha256'] != digest(reader.canonical(envelope))):
        raise ValueError('diagnosis_response_identity')
    result = value['result']
    keys = {'operation', 'status', 'checked_components', 'failure',
            'artifact_files_opened', 'artifact_bytes_read'}
    if (type(result) is not dict or set(result) != keys
            or result['operation'] != 'capsule_directory_diagnosis'
            or result['status'] not in ('SAFE_CHAIN', 'UNSAFE_CHAIN', 'UNAVAILABLE')
            or type(result['checked_components']) is not int
            or not 0 <= result['checked_components'] <= 256
            or any(type(result[k]) is not int or result[k] != 0
                   for k in ('artifact_files_opened', 'artifact_bytes_read'))):
        raise ValueError('diagnosis_result_shape')
    failure = result['failure']
    if result['status'] == 'SAFE_CHAIN':
        if (failure is not None or result['checked_components'] <
                len(envelope['request']['cwd'].split('/')[1:]) + 1):
            raise ValueError('diagnosis_safe_shape')
        return result
    if (type(failure) is not dict
            or set(failure) != {'component_index', 'role', 'reason', 'owner_relation', 'mode', 'errno'}
            or failure['role'] not in ('home_ancestor', 'lanes', 'artifacts', 'project', 'run', 'work', 'request', 'home', 'root')
            or failure['owner_relation'] not in (None, 'root', 'current', 'other')
            or (failure['mode'] is not None and
                (type(failure['mode']) is not str or not re.fullmatch(r'[0-7]{4}', failure['mode'])))
            or (failure['component_index'] is not None and
                (type(failure['component_index']) is not int or not 0 <= failure['component_index'] <= 255))
            or (failure['errno'] is not None and
                (type(failure['errno']) is not int or not 1 <= failure['errno'] <= 65535))):
        raise ValueError('diagnosis_failure_shape')
    if result['status'] == 'UNSAFE_CHAIN':
        if (failure['reason'] not in ('not_directory', 'foreign_owner', 'group_or_world_writable')
                or failure['component_index'] is None
                or result['checked_components'] != failure['component_index'] + 1
                or failure['role'] not in ('home_ancestor', 'lanes', 'artifacts', 'project', 'run', 'work')
                or failure['owner_relation'] is None or failure['mode'] is None
                or failure['errno'] is not None):
            raise ValueError('diagnosis_rule_failure_shape')
        minimum_index = {'home_ancestor': 0, 'lanes': 0, 'artifacts': 1, 'project': 2, 'run': 3, 'work': 4}
        if (failure['component_index'] < minimum_index[failure['role']]
                or (failure['reason'] == 'foreign_owner' and failure['owner_relation'] != 'other')
                or (failure['reason'] == 'group_or_world_writable' and
                    (failure['owner_relation'] not in ('root', 'current') or not int(failure['mode'], 8) & 0o022))):
            raise ValueError('diagnosis_rule_failure_contradiction')
    elif failure['reason'] not in ('invalid_request', 'home_shape_invalid', 'filesystem_refused', 'changed_during_diagnosis'):
        raise ValueError('diagnosis_unavailable_reason')
    return result


def diagnose_capsule(request, destination):
    evidence = qualify_capsule(request)
    envelope = {'schema': reader.CAPSULE_DIAG_SCHEMA, 'request': request}
    chain = reserve_destination(destination)
    receipt = {'schema': 'mastermind.fabric_capsule_directory_diagnosis_receipt.v1',
               'request': envelope, 'evidence': evidence, 'destination': str(destination),
               'state': 'DIAGNOSIS_PENDING', 'files': [], 'diagnosis': None,
               'artifact_files_opened': 0, 'artifact_bytes_read': 0,
               'execution_replayed': False, 'outcome_accepted': False,
               'read_transport_state': 'MAY_START_AFTER_THIS_INTENT'}
    def unchanged():
        if qualify_capsule(request) != evidence:
            raise ValueError('capsule_diagnosis_source_changed')
    try:
        write_exclusive(chain.fd, 'request.json', reader.canonical(receipt))
        try:
            unchanged(); chain.verify()
            receipt['read_transport_state'] = 'ATTEMPTED_UNCONFIRMED'
            raw = transport(evidence['ssh_alias'], envelope)
            receipt['read_transport_state'] = 'RESPONSE_RECEIVED'
            result = validate_capsule_diagnosis(raw, envelope)
            unchanged(); chain.verify()
            receipt['diagnosis'] = result
            receipt['state'] = 'DIAGNOSED' if result['status'] in ('SAFE_CHAIN', 'UNSAFE_CHAIN') else 'UNAVAILABLE'
        except (OSError, ValueError, TypeError, KeyError, RecursionError, subprocess.SubprocessError, sqlite3.Error):
            receipt['state'] = 'UNAVAILABLE'
            receipt['diagnosis'] = None
        receipt['observed_at_epoch'] = time.time()
        publish_receipt(chain, receipt, {'paths': []}, verify_source=unchanged)
        return receipt
    finally:
        chain.close()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def local_file(path, limit=1048576):
    with DirectoryChain(path.parent) as chain:
        return read_local_at(chain, path.name, limit)


def read_local_at(chain, name, limit):
    chain.verify()
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=chain.fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_mode & 0o002 or before.st_size > limit):
            raise ValueError("local_evidence_owner_mode_type_or_size")
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        if (len(data) != before.st_size or len(data) > limit
                or reader.identity(before) != reader.identity(os.fstat(fd))
                or reader.identity(before) != reader.identity(os.stat(name, dir_fd=chain.fd, follow_symlinks=False))):
            raise ValueError("local_evidence_changed")
        chain.verify()
        return data
    finally:
        os.close(fd)


class LeaseSnapshotLock:
    """Bounded shared read under the incumbent broker writer's existing lock."""
    def __init__(self, chain, seconds=4):
        self.chain=chain;self.seconds=seconds;self.fd=None;self.identity=None
    def __enter__(self):
        import fcntl
        self.fd=os.open('leases.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.chain.fd)
        try:
            st=os.fstat(self.fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode & 0o022:
                raise ValueError('lease_lock_metadata')
            deadline=time.monotonic()+self.seconds
            while True:
                try:fcntl.flock(self.fd,fcntl.LOCK_SH|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise ValueError('lease_snapshot_busy')
                    time.sleep(.01)
            self.chain.verify()
            seen=os.stat('leases.lock',dir_fd=self.chain.fd,follow_symlinks=False)
            if (seen.st_dev,seen.st_ino)!=(st.st_dev,st.st_ino):
                raise ValueError('lease_lock_changed')
            self.identity=(st.st_dev,st.st_ino)
            return self
        except BaseException:
            os.close(self.fd);self.fd=None;raise
    def __exit__(self,*_):
        import fcntl
        try:
            self.chain.verify()
            seen=os.stat('leases.lock',dir_fd=self.chain.fd,follow_symlinks=False)
            current=os.fstat(self.fd)
            if (seen.st_dev,seen.st_ino)!=self.identity or (current.st_dev,current.st_ino)!=self.identity:
                raise ValueError('lease_lock_changed')
        finally:
            fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd);self.fd=None


def _retained_broker_row(query, parameters, *, here=None):
    # A bounded snapshot under the existing broker lock; refuse an active WAL rather than
    # following SQLite sidecar paths or opening an unverified pathname.
    with DirectoryChain((HERE if here is None else Path(here)) / "broker") as chain, LeaseSnapshotLock(chain):
        def no_wal():
            for suffix in ("-wal", "-journal"):
                try:
                    os.stat("leases.sqlite" + suffix, dir_fd=chain.fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise ValueError("lease_snapshot_has_live_sidecar")
        no_wal()
        raw = read_local_at(chain, "leases.sqlite", 16777216)
        no_wal()
        if (raw[:16] != b"SQLite format 3\x00" or len(raw) < 100
                or raw[18] not in (1, 2) or raw[19] not in (1, 2)):
            raise ValueError("lease_snapshot_header")
        # deserialize cannot consume WAL-mode headers. With no WAL, the verified
        # main file is complete; only the private in-memory copy uses rollback mode.
        snapshot = raw[:18] + b"\x01\x01" + raw[20:]
        with sqlite3.connect(":memory:") as db:
            db.deserialize(snapshot)
            db.execute("PRAGMA query_only=ON")
            db.row_factory = sqlite3.Row
            row = db.execute(query, parameters).fetchone()
        no_wal()
        if read_local_at(chain, "leases.sqlite", 16777216) != raw:
            raise ValueError("lease_snapshot_changed")
        no_wal()
        chain.verify()
        return row


def retained_lease(lease_id, *, include_pool=False):
    columns = "id,orchestrator_id,host,account,model,state" + (",pool" if include_pool else "")
    return _retained_broker_row("SELECT " + columns + " FROM leases WHERE id=?", (lease_id,))


def go_cleanup(value, *, captured=False):
    from lane_runtime import cleanup_receipt_is_proven
    if (not isinstance(value, dict) or not cleanup_receipt_is_proven(value)
            or type(value.get("residual_count")) is not int or value["residual_count"] != 0
            or value.get("error_code") is not None):
        return False
    for stem in ("stdin_delivery", "stdout_capture", "stderr_capture"):
        if (captured or stem + "_complete" in value) and value.get(stem + "_complete") is not True:
            return False
        if value.get(stem + "_error") is not None:
            return False
    return True


def json_minimum_bytes(value):
    """Conservative JSON source bound, not original serialization attestation.

    JSON strings require these UTF-8 bytes (or longer escapes); containers
    require their punctuation. Numbers deliberately contribute only one byte,
    because distinct numeric spellings may deserialize to the same value.
    """
    if isinstance(value, str):
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    if value is None:
        return 4
    if type(value) is bool:
        return 4 if value else 5
    if type(value) in {int, float}:
        return 1
    if isinstance(value, list):
        return 2 + max(0, len(value) - 1) + sum(json_minimum_bytes(v) for v in value)
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return (2 + max(0, len(value) - 1)
                + sum(json_minimum_bytes(k) + 1 + json_minimum_bytes(v) for k, v in value.items()))
    raise ValueError("non_json_terminal")


def qualify_go(request, raw):
    from go_remote_run import worker_settled, transport_settled
    from go_remote_transport import SCOPE, IDENT
    from lane_runtime import cleanup_receipt_is_proven
    from lease_broker import _this_host
    run, worker, transport_receipt, process, terminal_read = (
        reader.strict_json(raw[name]) for name in ("go_run", "go_worker", "go_transport", "go_ssh", "go_terminal_read"))
    if (not isinstance(run, dict) or set(run) != set(SCOPE) | {
            "schema", "launched", "worker_returncode", "settled", "status", "helper_cleanup", "gateway_instance_id", "error_class"}
            or run.get("schema") != "mastermind.go.remote-run.v1"
            or any(not isinstance(run[k], str) or not IDENT.fullmatch(run[k]) for k in SCOPE)
            or any(run[k] != request[q] for k, q in (("run_id", "run_id"), ("root", "root"), ("host", "host")))
            or run.get("launched") is not True or run.get("settled") is not True
            or type(run.get("worker_returncode")) is not int or run["worker_returncode"] != 0
            or run.get("status") != "COMPLETE" or run.get("error_class") is not None
            or not isinstance(run.get("gateway_instance_id"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", run["gateway_instance_id"])
            or not isinstance(run.get("helper_cleanup"), dict)
            or not go_cleanup(run["helper_cleanup"])):
        raise ValueError("go_run_unqualified")
    worker_settled(worker, run)
    if worker["started"] is not True or worker["returncode"] != 0 or not go_cleanup(worker["cleanup"], captured=True):
        raise ValueError("go_worker_unsuccessful")
    pid = run["helper_cleanup"].get("session_id")
    if type(pid) is not int or pid <= 0 or not isinstance(transport_receipt, dict):
        raise ValueError("go_transport_identity")
    transport_settled(transport_receipt, run, pid, True)
    if (type(transport_receipt.get("helper_pid")) is not int
            or transport_receipt.get("ready_published") is not True
            or type(transport_receipt.get("ssh_pid")) is not int or transport_receipt["ssh_pid"] <= 0
            or type(transport_receipt.get("remote_port")) is not int or not 1024 <= transport_receipt["remote_port"] <= 65535
            or type(transport_receipt.get("duration_s")) not in {int, float}
            or not 0 <= transport_receipt["duration_s"] <= 86400 or not math.isfinite(transport_receipt["duration_s"])
            or not go_cleanup(transport_receipt.get("local_cleanup"))
            or type(transport_receipt["local_cleanup"].get("session_id")) is not int
            or transport_receipt["local_cleanup"]["session_id"] != transport_receipt["ssh_pid"]
            or type(transport_receipt.get("ssh_returncode")) is not int or transport_receipt["ssh_returncode"] != 0
            or transport_receipt.get("error_class") is not None
            or transport_receipt.get("remote_error_phase") is not None):
        raise ValueError("go_transport_incomplete")
    for value, label in ((process, request["run_id"] + "-worker-ssh"), (terminal_read, request["run_id"] + "-terminal")):
        if (not isinstance(value, dict) or value.get("schema") != "mastermind.local_owned_process_receipt.v1"
                or value.get("label") != label or type(value.get("returncode")) is not int or value["returncode"] != 0
                or value.get("timed_out") is not False or value.get("runtime_failure_code") is not None
                or value.get("stdout_truncated") is not False or value.get("stderr_truncated") is not False
                or type(value.get("stdout_bytes")) is not int or value["stdout_bytes"] <= 0
                or type(value.get("stderr_bytes")) is not int or value["stderr_bytes"] < 0
                or not go_cleanup(value.get("cleanup"), captured=True)):
            raise ValueError("go_process_unqualified")
    if (process["stdout_bytes"] != len(raw["stdout"]) or raw["go_raw"] != raw["stdout"]
            or worker["cleanup"] != process["cleanup"]
            or not json_minimum_bytes(worker) <= terminal_read["stdout_bytes"] <= 16384):
        raise ValueError("go_capture_conflict")
    lease = retained_lease(run["lease_id"], include_pool=True)
    if lease is None or any(lease[k] != expected for k, expected in {
            "orchestrator_id": request["root"], "host": _this_host(), "pool": "go",
            "account": run["account"], "model": run["model"], "state": "released"}.items()):
        raise ValueError("go_controller_lease_mismatch")
    return {"lease_id": lease["id"], "mode": "go-codex", "broker_host": lease["host"]}


def assert_settlement_family(request, go):
    opposing = (["native-terminal.json", "process.jsonl"] if go else
                ["go-run.json", "go-worker.json", "go-transport.json", "go-ssh.jsonl", "go-terminal-read.jsonl", "go-worker.raw.log"])
    with DirectoryChain(HERE / "state/remote_sub") as chain:
        for suffix in opposing:
            try:
                os.stat(request["run_id"] + "." + suffix, dir_fd=chain.fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError("mixed_settlement_families")
        chain.verify()


def qualify(request):
    import fabric_task
    reader.validate_request(request)
    rid = request["run_id"]
    # Check our source paths before the incumbent status projection reads them.
    base = HERE / "state/remote_sub"
    paths = {"stdout": HERE / "lanes" / f"{rid}.remote.stdout", "log": base / f"{rid}.log"}
    raw = {name: local_file(path) for name, path in paths.items()}
    # Only newly opted-in ordinary GLM runs carry executor-written completion
    # evidence. Never infer eligibility for an old stdout-only run or capsule.
    ordinary_path = base / f"{rid}.process.jsonl"
    if ordinary_path.exists():
        ordinary_raw = local_file(ordinary_path)
        ordinary = reader.strict_json(ordinary_raw)
        if isinstance(ordinary, dict) and 'artifact_production' in ordinary:
            # An ordinary producer cannot override an incomplete or uncertain
            # opposing settlement, even if its receipt file never arrived.
            log_text = raw["log"].decode("utf-8")
            if any(marker in log_text for marker in ("GO_SETTLED", "GO_EFFECT_UNKNOWN")):
                raise ValueError("mixed_settlement_families")
            return qualify_glm_producer(request, raw, paths, ordinary_path, ordinary_raw)
    go_marker = "GO_SETTLED receipt=" + rid + ".go-run.json"
    log_text = raw["log"].decode("utf-8")
    prefix = (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=" + re.escape(rid)
              + " host=" + re.escape(request["host"]) + r"\] ")
    markers = sum(line == go_marker or re.fullmatch(prefix + re.escape(go_marker), line) is not None
                  for line in log_text.splitlines())
    if markers > 1 or "GO_EFFECT_UNKNOWN" in log_text:
        raise ValueError("go_settlement_conflict")
    go = markers == 1
    assert_settlement_family(request, go)
    if go:
        suffixes = {"go_run": "go-run.json", "go_worker": "go-worker.json", "go_transport": "go-transport.json",
                    "go_ssh": "go-ssh.jsonl", "go_terminal_read": "go-terminal-read.jsonl", "go_raw": "go-worker.raw.log"}
    else:
        suffixes = {"terminal": "native-terminal.json", "process": "process.jsonl"}
    for name, suffix in suffixes.items():
        paths[name] = base / f"{rid}.{suffix}"
        raw[name] = local_file(paths[name])
    try:
        status = fabric_task.inspect_run(rid)
    except fabric_task.FabricTaskError as exc:
        raise ValueError("incumbent_status_unavailable") from exc
    if (status["state"] != "TERMINAL" or type(status["rc"]) is not int or status["rc"] != 0
            or status["signal"] != "ok" or status["result_available"] is not True
            or status.get("acceptance_state") not in {"ACCEPTED", "NOT_ACCEPTED"}
            or status.get("root_id") != request["root"]
            or status.get("parent_run_id") != request["parent"]):
        raise ValueError("run_not_qualified")
    if any(local_file(path) != raw[name] for name, path in paths.items()):
        raise ValueError("evidence_changed_during_projection")
    if digest(raw["stdout"]) != request["stdout_sha256"]:
        raise ValueError("stdout_digest_mismatch")
    text = raw["stdout"].decode("utf-8")
    artifact_manifest = None
    if any(line.startswith("FABRIC_ARTIFACTS_V1 ") for line in text.splitlines()):
        import artifact_production
        artifact_manifest = artifact_production.manifest_from_stdout(
            text, root=request["root"], parent=request["parent"], run_id=rid, host=request["host"])
        advertised = {item["path"] for item in artifact_manifest["files"]}
        if any(path not in advertised for path in request["paths"]):
            raise ValueError("artifact_not_in_producer_manifest")
    else:
        tokens = {token[1:-1] if len(token) >= 2 and token[0] in "\"'`" and token[-1] == token[0] else token
                  for token in text.split()}
        if any(path not in tokens for path in request["paths"]):
            raise ValueError("artifact_not_named_in_retained_result")
    if go:
        binding = qualify_go(request, raw)
    else:
        binding = qualify_native(request, raw)
    registry = local_file(HERE / "hosts.json")
    registry_value = reader.strict_json(registry)
    if not isinstance(registry_value, dict):
        raise ValueError("registry_shape")
    entry = registry_value.get(request["host"])
    if not isinstance(entry, dict) or binding["mode"] not in entry.get("allowed_modes", []):
        raise ValueError("receiver_registry_mismatch")
    alias = entry.get("ssh_alias")
    if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", alias):
        raise ValueError("receiver_alias_invalid")
    result = {"evidence_sha256": {name: digest(value) for name, value in raw.items()},
              "registry_sha256": digest(registry), "ssh_alias": alias, "lease_id": binding["lease_id"]}
    if go:
        result.update(settlement_family="go", broker_host=binding["broker_host"])
    if artifact_manifest is not None:
        result["artifact_manifest"] = artifact_manifest
    if any(local_file(path) != raw[name] for name, path in paths.items()):
        raise ValueError("evidence_changed_during_qualification")
    assert_settlement_family(request, go)
    return result


_ORIGINAL_PRODUCER_PATH = Path('/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/artifact_production.c0f17c3e.before.py')
_ORIGINAL_PRODUCER_SHA256 = 'c0f17c3e489c83bdb369d6c1ea9adc2757f4732f515cbc76e230fe154a61f67e'
_PREVIOUS_PRODUCER_PATH = _ORIGINAL_PRODUCER_PATH.with_name('artifact_production.e126d643.before.py')
_PREVIOUS_PRODUCER_SHA256 = 'e126d6432135725a7a7846cbe9f9749305dfe9dd7cfe37037fc413a1136248bf'
_CURRENT_PRODUCER_SHA256 = '0be15bd5d3304a65673576fd30386bcc977c02ed8ee28313a4cb1ed454f8c409'
_ORIGINAL_READER_SHA256 = 'e2b08b7967df0e4193ba668cf6f72225429138a9361322c42db6ec84150e3469'


def _original_validator_source(producer_sha=_ORIGINAL_PRODUCER_SHA256):
    """Secure fixed-file checks precede every historical validation operation."""
    if producer_sha == _ORIGINAL_PRODUCER_SHA256:
        path = _ORIGINAL_PRODUCER_PATH
    elif producer_sha == _PREVIOUS_PRODUCER_SHA256:
        path = _PREVIOUS_PRODUCER_PATH
    else:
        raise ValueError('original_producer_validator_changed')
    raw = local_file(path, 128 * 1024)
    if digest(raw) != producer_sha:
        raise ValueError('original_producer_validator_changed')
    if digest(local_file(HERE / 'artifact_reader.py', 128 * 1024)) != _ORIGINAL_READER_SHA256:
        raise ValueError('original_producer_validator_changed')
    return raw


class _OriginalValidatorContext:
    """Fixed reviewed validator, bound to one exact support manifest digest.

    No caller module, source path or source code is accepted. Each operation
    rereads fixed secure files and executes only the full-hash-qualified source
    in a fresh private namespace. The installed producer/imports are untouched.
    """
    __slots__ = ('_support_digest', '_producer_sha')

    def __setattr__(self, name, value):
        raise AttributeError('original validator context is immutable')

    def _namespace(self):
        source = _original_validator_source(self._producer_sha)
        namespace = {'__name__': 'fixed_original_producer_validator'}
        exec(compile(source, 'fixed_producer_' + self._producer_sha, 'exec'), namespace)
        return namespace

    def _bind(self, contract):
        if contract['support_digest'] != self._support_digest:
            raise ValueError('original_support_mismatch')
        return contract

    def parse_packet(self, text):
        contract = self._namespace()['parse_packet'](text)
        return None if contract is None else self._bind(contract)

    def validate_contract(self, value):
        return self._bind(self._namespace()['validate_contract'](value))

    def paths(self, contract):
        namespace = self._namespace()
        return namespace['paths'](self._bind(namespace['validate_contract'](contract)))

    def manifest_from_stdout(self, text, **scope):
        return self._namespace()['manifest_from_stdout'](text, **scope)


def original_validator_context(manifest):
    """Select only three exact reviewed producer generations.

    The matching installed e126 or 0be uses the existing default validator. After
    0be adoption, e126 and c0 use their own fixed source and support-bound context.
    Unknown or drifted current versions cannot be reclassified as e126 history.
    """
    if (type(manifest) is not dict or not manifest
            or any(type(k) is not str or type(v) is not str
                   or re.fullmatch(r'[0-9a-f]{64}', v) is None for k, v in manifest.items())
            or manifest.get('artifact_reader.py') != _ORIGINAL_READER_SHA256
            or digest(local_file(HERE / 'artifact_reader.py', 128 * 1024)) != _ORIGINAL_READER_SHA256):
        raise ValueError('original_producer_validator_changed')
    producer_sha = manifest.get('artifact_production.py')
    if producer_sha in (_PREVIOUS_PRODUCER_SHA256, _CURRENT_PRODUCER_SHA256):
        installed_sha = digest(local_file(HERE / 'artifact_production.py', 128 * 1024))
        if installed_sha == producer_sha:
            return None
        if not (producer_sha == _PREVIOUS_PRODUCER_SHA256
                and installed_sha == _CURRENT_PRODUCER_SHA256):
            raise ValueError('original_producer_validator_changed')
    elif producer_sha != _ORIGINAL_PRODUCER_SHA256:
        raise ValueError('original_producer_validator_changed')
    _original_validator_source(producer_sha)
    context = object.__new__(_OriginalValidatorContext)
    object.__setattr__(context, '_producer_sha', producer_sha)
    object.__setattr__(context, '_support_digest', digest(reader.canonical(
        {'schema': 'remote-support-code.v1', 'files': manifest})))
    return context


def validate_ordinary_producer(request, stdout, process_raw, *, original_validator=None):
    """Pure producer proof; no controller terminal flag or lease settlement."""
    import artifact_production
    if original_validator is not None:
        if type(original_validator) is not _OriginalValidatorContext:
            raise ValueError('original_validator_context_invalid')
        artifact_production = original_validator
        ordinary_modes = {'glm', 'qwen'}
    else:
        ordinary_modes = artifact_production.ORDINARY_MODES
    rid = request['run_id']
    validate_capsule_process(process_raw, stdout, rid)
    completion = reader.strict_json(process_raw)['artifact_production']
    if (type(completion) is not dict or set(completion) != {
            'schema', 'mode', 'contract', 'manifest', 'stdout_sha256'}
            or completion['schema'] != 'mastermind.fabric_artifact_completion.v1'
            or completion['mode'] not in ordinary_modes
            or completion['stdout_sha256'] != digest(stdout)
            or request.get('stdout_sha256', digest(stdout)) != digest(stdout)):
        raise ValueError('glm_producer_completion_unqualified')
    contract = artifact_production.validate_contract(completion['contract'])
    if any(contract[k] != request[k] for k in ('run_id', 'root', 'parent')):
        raise ValueError('glm_producer_contract_scope')
    manifest = artifact_production.manifest_from_stdout(stdout.decode('utf-8'),
        root=request['root'], parent=request['parent'], run_id=rid, host=request['host'])
    if (manifest != completion['manifest']
            or manifest['request_sha256'] != digest(reader.canonical(contract))
            or [item['path'] for item in manifest['files']] != artifact_production.paths(contract)
            or any(path not in artifact_production.paths(contract) for path in request.get('paths', artifact_production.paths(contract)))):
        raise ValueError('glm_producer_manifest_mismatch')
    return manifest


def qualify_glm_producer(request, raw, paths, process_path, process_raw):
    import fabric_task
    import artifact_production
    rid = request['run_id']
    assert_capsule_family(rid)
    raw = dict(raw, process=process_raw)
    paths = dict(paths, process=process_path)
    manifest = validate_ordinary_producer(request, raw['stdout'], process_raw)
    completion = reader.strict_json(process_raw)['artifact_production']
    prefix = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=' + re.escape(rid)
              + ' host=' + re.escape(request['host']) + r'\] (.*)')
    events = [m.group(1) for line in raw['log'].decode('utf-8').splitlines()
              if (m := re.fullmatch(prefix, line))]
    remote_done = [e for e in events if e.startswith('REMOTE_DONE ')]
    done = [e for e in events if e.startswith('DONE ')]
    if (not any(e.startswith(f'LAUNCH stdout=lanes_{rid}.stdout rc_file=ext/lanes_{rid}.rc cwd=') for e in events)
            or not remote_done or remote_done[-1] != 'REMOTE_DONE rc=0'
            or done != ['DONE rc=0 signal=ok']):
        raise ValueError('glm_producer_controller_host_mismatch')
    status = fabric_task.inspect_run(rid)
    if (status['state'] != 'TERMINAL' or type(status['rc']) is not int or status['rc'] != 0
            or status['signal'] != 'ok' or status['result_available'] is not True
            or status.get('root_id') != request['root'] or status.get('parent_run_id') != request['parent']
            or status.get('acceptance_state') not in ('ACCEPTED', 'NOT_ACCEPTED')):
        raise ValueError('glm_producer_terminal_unqualified')
    registry = local_file(HERE / 'hosts.json')
    registry_value = reader.strict_json(registry)
    entry = registry_value.get(request['host']) if type(registry_value) is dict else None
    if (type(entry) is not dict or completion['mode'] not in entry.get('allowed_modes', [])
            or type(entry.get('ssh_alias')) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', entry['ssh_alias'])):
        raise ValueError('glm_producer_receiver_registry_mismatch')
    if any(local_file(path) != raw[name] for name, path in paths.items()):
        raise ValueError('glm_producer_evidence_changed')
    assert_capsule_family(rid)
    return dict(evidence_sha256={name: digest(value) for name, value in raw.items()},
        registry_sha256=digest(registry), ssh_alias=entry['ssh_alias'], lease_id=None,
        settlement_family='ordinary_' + completion['mode'] + '_producer', producer_contract_verified=True,
        artifact_manifest=manifest)



def qualify_grok_output(request, terminal, process, stdout):
    """Only a contemporaneous original producer binding admits transformed text."""
    import artifact_production
    b=terminal.get('output_binding')
    keys={'schema','algorithm','root','parent','run_id','host','lease_id','account','support_digest',
          'mode','model','raw_bytes','raw_sha256','normalized_bytes','normalized_sha256','contract','manifest'}
    if (type(b) is not dict or set(b)!=keys or b['schema']!='mastermind.grok_normalized_output.v1'
            or b['algorithm']!='grok_plaintext_and_usage_v1' or b['mode']!='grok' or b['model']!='grok-4.6'
            or any(b[k]!=request[k] for k in ('root','parent','run_id','host'))
            or any(b[k]!=terminal.get(k) for k in ('root','run_id','host','lease_id','account','mode','model'))
            or b['support_digest']!=(terminal.get('launch_timing') or {}).get('support_digest')
            or type(b['raw_bytes']) is not int or b['raw_bytes']!=process.get('stdout_bytes')
            or type(b['raw_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',b['raw_sha256'])
            or b['raw_sha256']!=process.get('stdout_sha256')
            or type(b['normalized_bytes']) is not int or b['normalized_bytes']!=len(stdout)
            or b['normalized_sha256']!=digest(stdout) or request['stdout_sha256']!=digest(stdout)):
        raise ValueError('grok_normalized_output_unqualified')
    contract=artifact_production.validate_contract(b['contract'])
    if any(contract[k]!=b[k] for k in ('root','parent','run_id','support_digest')):
        raise ValueError('grok_normalized_contract_scope')
    manifest=artifact_production.manifest_from_stdout(stdout.decode('utf-8'),
        root=request['root'],parent=request['parent'],run_id=request['run_id'],host=request['host'])
    if (manifest!=b['manifest'] or manifest['request_sha256']!=digest(reader.canonical(contract))
            or [f['path'] for f in manifest['files']]!=artifact_production.paths(contract)
            or any(p not in artifact_production.paths(contract) for p in request['paths'])):
        raise ValueError('grok_normalized_manifest_mismatch')
    return b['raw_bytes']


def qualify_native(request, raw):
    rid = request["run_id"]
    terminal, process = reader.strict_json(raw["terminal"]), reader.strict_json(raw["process"])
    if (not isinstance(terminal, dict) or not isinstance(process, dict)
            or terminal.get("schema") != "mastermind.native.remote-terminal.v1"
            or process.get("schema") != "mastermind.local_owned_process_receipt.v1"):
        raise ValueError("receipt_shape")
    for key, expected in (("run_id", rid), ("root", request["root"]), ("host", request["host"])):
        if terminal.get(key) != expected:
            raise ValueError("receiver_identity_mismatch")
    expected_capture_bytes = len(raw["stdout"])
    if 'output_binding' in terminal:
        expected_capture_bytes = qualify_grok_output(request, terminal, process, raw['stdout'])
    capture = terminal.get("capture")
    if (not isinstance(capture, dict) or set(capture) != {"stdout_bytes", "stderr_bytes", "stdout_truncated", "stderr_truncated"}
            or type(capture["stdout_bytes"]) is not int or capture["stdout_bytes"] != expected_capture_bytes
            or type(capture["stderr_bytes"]) is not int or capture["stderr_bytes"] < 0
            or capture["stdout_truncated"] is not False or capture["stderr_truncated"] is not False
            or any(type(process.get(key)) is not type(value) or process.get(key) != value for key, value in capture.items())
            or terminal.get("cleanup") != process.get("cleanup")):
        raise ValueError("capture_or_cleanup_conflict")
    from lane_runtime import cleanup_receipt_is_proven
    if (terminal.get("started") is not True or type(terminal.get("returncode")) is not int
            or terminal["returncode"] != 0 or terminal.get("output_complete") is not True
            or terminal.get("cleanup_proven") is not True
            or not cleanup_receipt_is_proven(terminal.get("cleanup") or {})
            or process.get("label") != rid or type(process.get("returncode")) is not int
            or process["returncode"] != 0 or process.get("timed_out") is not False
            or not cleanup_receipt_is_proven(process.get("cleanup") or {})
            or process.get("stdout_truncated") is not False
            or process.get("stdout_bytes") != expected_capture_bytes):
        raise ValueError("settlement_unqualified")
    lease = retained_lease(terminal.get("lease_id"))
    if lease is None or any(lease[key] != expected for key, expected in {
        "orchestrator_id": request["root"], "host": request["host"],
        "account": terminal.get("account"), "model": terminal.get("model"), "state": "released",
    }.items()):
        raise ValueError("lease_identity_or_settlement_mismatch")
    return {"lease_id": lease["id"], "mode": terminal.get("mode")}


def transport(alias, request, *, observer_source_hash=None, current_sources_sha256=None):
    # Fixed code, fixed interpreter, validated registry alias; paths travel in stdin.
    response_limit = reader.MAX_RESPONSE
    if type(request) is dict and request.get("schema") == "mastermind.original_operator_stdout_read.v1":
        import operator_stdout_delivery
        code = operator_stdout_delivery.code_for_request(request)
        response_limit = operator_stdout_delivery.MAX_RESPONSE
    elif type(request) is dict and request.get("schema") == "mastermind.original_delivery_read.v1":
        import original_delivery_collector
        code = original_delivery_collector.code_for_request(request)
        response_limit = original_delivery_collector.MAX_RESPONSE
    elif type(request) is dict and request.get("schema") == "mastermind.mac_policy_original_return.v1":
        import mac_policy_return
        code = mac_policy_return.code_for_request(request, expected_hashes=current_sources_sha256)
        response_limit = mac_policy_return.MAX_RESPONSE
    elif type(request) is dict and request.get("schema") == "mastermind.original_result_current_read_request.v1":
        import original_result_read
        code = original_result_read.code_for_request(request, expected_hashes=current_sources_sha256)
        response_limit = original_result_read.MAX_RESPONSE
    elif type(request) is dict and request.get("schema") == "mastermind.native_host_review_source_read.v1":
        if digest(local_file(HERE / "native_host_review_source_delivery.py", 65536)) != '3ec53fa0be3c69c28e265a1bb5b1cab3cc0ee3f6f6c03b93908d6c2685f2e902':
            raise ValueError("native_source_delivery_head_changed")
        import native_host_review_source_delivery
        code = native_host_review_source_delivery.code_for_request(request, expected_hash=observer_source_hash)
        response_limit = native_host_review_source_delivery.MAX_RESPONSE
    elif type(request) is dict and request.get("schema") == "mastermind.native_host_review_inspection.v1":
        import native_host_review_delivery
        code = native_host_review_delivery.code_for_request(request, expected_hash=observer_source_hash)
        response_limit = native_host_review_delivery.MAX_RESPONSE
    elif type(request) is dict and request.get("schema") == "mastermind.fabric_run_observation_request.v1":
        import run_observation_delivery
        code = run_observation_delivery.code_for_request(request, expected_hash=observer_source_hash)
    else:
        code = local_file(HERE / "artifact_reader.py", 65536).decode("utf-8")
    command = "python3 -I -S -c " + shlex.quote(code)
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", alias, command]
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as proc:
        try:
            proc.stdin.write(reader.canonical(request))
            proc.stdin.close()
            chunks, total = [], 0
            deadline = time.monotonic() + 30
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError("transport_timeout")
                    chunk = os.read(proc.stdout.fileno(), min(65536, response_limit + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > response_limit:
                        raise ValueError("transport_output_limit")
            if proc.wait(timeout=max(0.01, deadline-time.monotonic())) != 0:
                raise ValueError("transport_unavailable")
            return b"".join(chunks)
        finally:
            if proc.poll() is None:
                # This is solely our new read transport, never the settled worker/controller.
                proc.kill()
                proc.wait()


def validate_response(raw, request):
    if len(raw) > reader.MAX_RESPONSE:
        raise ValueError("response_limit")
    response = reader.strict_json(raw)
    if (not isinstance(response, dict) or set(response) != {"schema", "request_sha256", "files"}
            or response["schema"] != reader.SCHEMA
            or response["request_sha256"] != digest(reader.canonical(request))
            or not isinstance(response["files"], list)
            or len(response["files"]) != len(request["paths"])):
        raise ValueError("response_identity_or_shape")
    total, result = 0, []
    for path, item in zip(request["paths"], response["files"]):
        if not isinstance(item, dict) or item.get("path") != path:
            raise ValueError("response_path_mismatch")
        if item.get("status") == "RETRIEVED":
            if set(item) != {"path", "status", "bytes", "sha256", "data_base64", "observed_file"}:
                raise ValueError("response_file_shape")
            data = base64.b64decode(item["data_base64"], validate=True)
            if (type(item["bytes"]) is not int or item["bytes"] != len(data)
                    or len(data) > reader.MAX_FILE or digest(data) != item["sha256"]):
                raise ValueError("response_file_integrity")
            observed = item["observed_file"]
            if (not isinstance(observed, dict) or set(observed) != {"device", "inode", "mtime_ns", "uid", "mode"}
                    or any(type(v) is not int or v < 0 for v in observed.values())):
                raise ValueError("response_metadata")
            total += len(data)
            if total > reader.MAX_TOTAL:
                raise ValueError("response_total_limit")
            result.append(({k: v for k, v in item.items() if k != "data_base64"}, data))
        elif (set(item) == {"path", "status", "reason"}
              and item.get("status") in {"NOT_FOUND", "UNAVAILABLE"}
              and item.get("reason") in {"missing_at_read", "directory_owner_or_mode", "file_owner_mode_or_type",
                  "size_limit", "changed_during_read", "filesystem_refused"}):
            result.append((item, None))
        else:
            raise ValueError("response_status_invalid")
    return result


class DirectoryChain:
    """Hold and revalidate every directory edge without following symlinks."""
    def __init__(self, path):
        self.fds = []
        self.parts = []
        try:
            path = Path(path)
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("directory_path_invalid")
            self.fds.append(os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            for component in path.parts[1:]:
                self.append(component)
            self.verify()
        except BaseException:
            self.close()
            raise

    @property
    def fd(self):
        return self.fds[-1]

    def append(self, name):
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        self.fds.append(fd)
        self.parts.append(name)

    def verify(self):
        for i, fd in enumerate(self.fds):
            held = os.fstat(fd)
            if not stat.S_ISDIR(held.st_mode) or held.st_uid not in {0, os.getuid()} or held.st_mode & 0o022:
                raise ValueError("directory_owner_or_mode")
            if i:
                visible = os.stat(self.parts[i-1], dir_fd=self.fds[i-1], follow_symlinks=False)
                if ((visible.st_dev, visible.st_ino, visible.st_mode, visible.st_uid)
                        != (held.st_dev, held.st_ino, held.st_mode, held.st_uid)):
                    raise ValueError("directory_chain_changed")

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def reserve_destination(destination):
    path = Path(destination)
    if not path.is_absolute() or ".." in path.parts or path == DESTINATION_ROOT or not path.is_relative_to(DESTINATION_ROOT):
        raise ValueError("destination_outside_approved_evidence_root")
    chain = DirectoryChain(path.parent)
    try:
        os.mkdir(path.name, 0o700, dir_fd=chain.fd)  # Fresh leaf only.
        os.fsync(chain.fd)
        chain.append(path.name)
        chain.verify()
        return chain
    except BaseException:
        chain.close()
        raise


def write_exclusive(fd, name, data):
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(handle, "wb") as stream:
        if stream.write(data) != len(data):
            raise OSError("short_local_write")
        stream.flush()
        os.fsync(stream.fileno())
        created = (os.fstat(stream.fileno()).st_dev, os.fstat(stream.fileno()).st_ino)
    os.fsync(fd)
    return created


def verify_delivered(chain, files):
    chain.verify()
    for entry in files:
        if entry.get("local_name"):
            raw = read_local_at(chain, entry["local_name"], reader.MAX_FILE)
            if len(raw) != entry["bytes"] or digest(raw) != entry["sha256"]:
                raise ValueError("delivered_file_integrity")


def unavailable(receipt, request):
    receipt["state"] = "UNAVAILABLE"
    for flag in ("delivery_verified", "worker_terminal_proof"):
        if flag in receipt:
            receipt[flag] = False
    if "requested_content_constraints_matched" in receipt:
        receipt["requested_content_constraints_matched"] = False
    if "advertised_manifest_matched" in receipt:
        receipt["advertised_manifest_matched"] = False
        receipt["provenance"] = "A scoped manifest was advertised; complete artifact delivery and integrity are unconfirmed."
    # Earlier writes are no longer attested after a publication/path failure.
    receipt["files"] = [{"path": p, "status": "UNAVAILABLE", "reason": "read_or_delivery_unconfirmed"}
                        for p in request["paths"]]


def inode(info):
    return info.st_dev, info.st_ino


def publish_receipt(chain, receipt, request, *, verify_source=None):
    fd = chain.fd
    pending = ".receipt.pending.json"
    handle = None
    owned = False
    published = False
    try:
        raw = reader.canonical(receipt)
        created = write_exclusive(fd, pending, raw)
        # Keep the actual created inode open through publication AND failure
        # finalization. Never delete or reopen a pathname to invalidate it.
        handle = os.open(pending, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        own = inode(os.fstat(handle))
        if own != created:
            raise ValueError("receipt_stage_substituted")
        owned = True
        if read_local_at(chain, pending, 65536) != raw:
            raise ValueError("receipt_stage_integrity")
        verify_delivered(chain, receipt["files"])
        if verify_source is not None:
            verify_source()
        os.link(pending, "receipt.json", src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        published = True
        os.fsync(fd)
        if (inode(os.stat("receipt.json", dir_fd=fd, follow_symlinks=False)) != own
                or inode(os.stat(pending, dir_fd=fd, follow_symlinks=False)) != own):
            raise ValueError("receipt_inode_changed")
        verify_delivered(chain, receipt["files"])
        if read_local_at(chain, "receipt.json", 65536) != raw:
            raise ValueError("receipt_integrity")
        if verify_source is not None:
            verify_source()
            verify_delivered(chain, receipt["files"])
            # The callback can fail or race with replacement/corruption of
            # either link. Validate our published receipt after it returns,
            # as well as validating the delivered output files above.
            if (inode(os.stat("receipt.json", dir_fd=fd, follow_symlinks=False)) != own
                    or inode(os.stat(pending, dir_fd=fd, follow_symlinks=False)) != own):
                raise ValueError("receipt_inode_changed")
            if read_local_at(chain, "receipt.json", 65536) != raw:
                raise ValueError("receipt_integrity")
        # Retain the staging link as evidence. Removing it by pathname could
        # destroy a replacement installed after our last identity observation.
    except Exception:
        # Every ordinary failure inside this publication boundary invalidates
        # the inode we created, including malformed provenance projections.
        # Restricting this to filesystem/value failures can leave COMPLETE
        # visible when a callback raises TypeError, KeyError, or another error.
        unavailable(receipt, request)
        if owned:
            # Truncate first, so a later failed write cannot leave our old valid
            # COMPLETE record. This affects only the inode created by us.
            os.ftruncate(handle, 0)
            os.lseek(handle, 0, os.SEEK_SET)
            remaining = reader.canonical(receipt)
            while remaining:
                count = os.write(handle, remaining)
                if count <= 0:
                    raise OSError("failure_receipt_short_write")
                remaining = remaining[count:]
            os.fsync(handle)
        if not published:
            try:
                write_exclusive(fd, "receipt.json", reader.canonical(receipt))
            except FileExistsError:
                pass  # Foreign collision: preserve it and refuse.
        raise ValueError("local_publication_unconfirmed")
    finally:
        if handle is not None:
            os.close(handle)


def failure_diagnostic(exc):
    # Fixed categories only: exception text may contain private paths or data.
    known={'lease_snapshot_has_live_sidecar','lease_snapshot_changed','lease_snapshot_busy',
           'lease_lock_metadata','lease_lock_changed','capture_or_cleanup_conflict',
           'settlement_unqualified','lease_identity_or_settlement_mismatch',
           'grok_normalized_output_unqualified','directory_owner_or_mode',
           'destination_outside_approved_evidence_root','local_publication_unconfirmed'}
    if isinstance(exc, PermissionError):
        return 'permission_denied'
    return str(exc) if isinstance(exc,ValueError) and str(exc) in known else 'unclassified_local_failure'


def failure_phase(exc, phase):
    exc.fabric_delivery_phase=phase
    return exc


def export(request, destination):
    reader.validate_request(request)
    if any(p.rsplit("/", 1)[1] in {"request.json", "receipt.json"} for p in request["paths"]):
        raise ValueError("reserved_output_name")
    try:
        evidence = qualify(request)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error) as exc:
        raise failure_phase(exc, 'qualification')
    try:
        chain = reserve_destination(destination)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error) as exc:
        raise failure_phase(exc, 'destination_reservation')
    fd = chain.fd
    receipt = {"schema": "mastermind.fabric_artifact_export.v1", "request": request,
               "evidence": evidence, "destination": str(destination), "state": "READ_PENDING",
               "files": [], "historical_worker_bytes_attested": False,
               "read_transport_state": "MAY_START_AFTER_THIS_INTENT",
               "provenance": "Current receiver bytes at paths named by the retained result; no original artifact hash was sealed.",
               "execution_replayed": False, "outcome_accepted": False}
    if "artifact_manifest" in evidence:
        receipt["advertised_manifest_matched"] = False
        receipt["provenance"] = "A scoped manifest was advertised; complete artifact delivery and integrity are unconfirmed."
    try:
        write_exclusive(fd, "request.json", reader.canonical(receipt))
        chain.verify()
        try:
            receipt["read_transport_state"] = "ATTEMPTED_UNCONFIRMED"
            raw = transport(evidence["ssh_alias"], request)
            receipt["read_transport_state"] = "RESPONSE_RECEIVED"
            files = validate_response(raw, request)
            if "artifact_manifest" in evidence:
                declared = {item["path"]: item for item in evidence["artifact_manifest"]["files"]}
                if any(data is not None and (item["bytes"] != declared[item["path"]]["bytes"]
                        or item["sha256"] != declared[item["path"]]["sha256"]) for item, data in files):
                    raise ValueError("artifact_changed_since_completion")
            if qualify(request) != evidence:
                raise ValueError("source_changed_during_read")
            chain.verify()
            for item, data in files:
                entry = dict(item)
                if data is not None:
                    name = item["path"].rsplit("/", 1)[1]
                    if name in {"request.json", "receipt.json"}:
                        raise ValueError("reserved_output_name")
                    write_exclusive(fd, name, data)
                    entry["local_name"] = name
                receipt["files"].append(entry)
                verify_delivered(chain, receipt["files"])
            receipt["state"] = "COMPLETE" if all(i["status"] == "RETRIEVED" for i in receipt["files"]) else "PARTIAL"
            if ("artifact_manifest" in evidence and receipt["state"] == "COMPLETE"
                    and set(request["paths"]) == set(declared)):
                receipt["advertised_manifest_matched"] = True
                receipt["provenance"] = "All advertised files were retained and their bytes match the scoped manifest in this result; producer verification and parent acceptance remain separate."
        except (OSError, ValueError, TypeError, KeyError, RecursionError, subprocess.SubprocessError, sqlite3.Error) as exc:
            receipt['failure_phase']='transport_or_validation'
            receipt['failure_diagnostic']=failure_diagnostic(exc)
            unavailable(receipt, request)
        receipt["observed_at_epoch"] = time.time()
        def verify_source():
            if qualify(request) != evidence:
                raise ValueError("source_changed_during_publication")
        publish_receipt(chain, receipt, request, verify_source=(
            verify_source if evidence.get("settlement_family") in {"ordinary_glm_producer", "ordinary_qwen_producer"} else None))
        return receipt
    finally:
        chain.close()


def main():
    if sys.argv[1:2] == ["--mac-policy-return"]:
        import mac_policy_return
        p = argparse.ArgumentParser(description="Original mac-policy retained evidence only")
        p.add_argument("run_id"); p.add_argument("--root", required=True)
        p.add_argument("--destination", required=True)
        args = p.parse_args(sys.argv[2:])
        try:
            receipt = mac_policy_return.recover(args.run_id, args.root, args.destination)
            print(reader.canonical(receipt).decode())
            return 0 if receipt['state'] == 'RETAINED_ORIGINAL_RESULT' else 76
        except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error):
            print('{"state":"REFUSED","reason":"original_mac_policy_recovery_unconfirmed"}')
            return 75
    if sys.argv[1:2] == ["--current-output"]:
        import original_result_delivery
        return original_result_delivery.main(sys.argv[2:])
    if sys.argv[1:2] == ["--observe-run"]:
        import run_observation_delivery
        return run_observation_delivery.main(sys.argv[2:])
    if sys.argv[1:2] == ['--capsule-diagnose']:
        p = argparse.ArgumentParser(description='Exact capsule directory metadata diagnosis only')
        p.add_argument('run_id'); p.add_argument('--destination', required=True)
        args = p.parse_args(sys.argv[2:])
        try:
            receipt = diagnose_capsule(reader.capsule_request(args.run_id), args.destination)
            print(reader.canonical(receipt).decode())
            return 0 if receipt['state'] == 'DIAGNOSED' else 76
        except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error):
            print('{"state":"REFUSED","reason":"capsule_diagnosis_unconfirmed"}')
            return 75
    if sys.argv[1:2]==['--capsule-current']:
        p=argparse.ArgumentParser(description='Exact source-admitted current capsule outputs only')
        p.add_argument('run_id');p.add_argument('--destination',required=True)
        args=p.parse_args(sys.argv[2:])
        try:
            if args.run_id == "rf-codegen-contracts-impl-01a1333c-v1":
                import operator_stdout_delivery
                receipt = operator_stdout_delivery.collect(args.run_id, args.destination)
            elif args.run_id in ("rf-static-checks-01a1333c-v1", "rf-fixed-smoke-runsc-01a1333c-v1", "rf-fixed-smoke-runsc-01a1333c-v2", "rf-fixed-smoke-runsc-01a1333c-v3"):
                import current_failed_artifact_evidence
                receipt = current_failed_artifact_evidence.export(args.run_id, args.destination)
            else:
                receipt=export_capsule(reader.capsule_request(args.run_id),args.destination)
            print(reader.canonical(receipt).decode())
            return 0 if receipt['state']=='COMPLETE' else 76
        except (OSError,ValueError,TypeError,KeyError,RecursionError,sqlite3.Error):
            print('{"state":"REFUSED","reason":"capsule_current_intent_or_delivery_unconfirmed"}')
            return 75
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id")
    for name in ("root", "parent", "host", "stdout-sha256", "destination"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--path", action="append", required=True)
    args = p.parse_args()
    request = {"schema": reader.SCHEMA, "run_id": args.run_id, "root": args.root,
               "parent": args.parent, "host": args.host, "stdout_sha256": args.stdout_sha256, "paths": args.path}
    try:
        receipt = export(request, args.destination)
        print(reader.canonical(receipt).decode())
        return 0 if receipt["state"] == "COMPLETE" else 76
    except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error) as exc:
        phase=getattr(exc,'fabric_delivery_phase','validation_or_publication')
        print(json.dumps({'state':'REFUSED','reason':'artifact_export_precondition_or_local_delivery_failed',
                          'failure_phase':phase,'diagnostic':failure_diagnostic(exc)}))
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
