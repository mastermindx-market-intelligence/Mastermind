"""Closed historical post-failure evidence, never settlement or a process probe.

The existing reader supplies metadata from fixed original-run paths. A prior
observation's absence is not a final absence. Original completion records are
reported as recorded; missing child-generation/capture provenance is not rebuilt.
"""
from __future__ import annotations
import hashlib
import json
import re

SCHEMA = 'mastermind.fabric_post_failure_observation.v1'
SUPPORT = '6cdf2f96fb780ef08e8bac21c55cc91418bbfe080252f18479c7bfb70cff5a80'
MACRO_ROOT = '01a14c38-2baf-76c2-9475-b1f0a370ab17'
MACRO_PARENT = '01a1aaa4-2a02-7c52-958d-9adcf70c23a1'
SCOPES = {
 'macro-native-publisher-routing-20261105-01a1aaa4': {
  'root': MACRO_ROOT, 'parent': MACRO_PARENT, 'host': 'ubuntu3',
  'lease_id': '9b1b9a1dd376', 'account': 'chairman-max-3',
  'names': ['routing.patch', 'ROUTING.md'],
  'prior_receipt_sha256': '21d1f86bd7f74905b45b4c458473fb3417a15c79cb266323f30be5205381b131'},
 'macro-native-publisher-main-workflows-20261105-01a1aaa4': {
  'root': MACRO_ROOT, 'parent': MACRO_PARENT, 'host': 'ubuntu3',
  'lease_id': '0019506a1dd4', 'account': 'chairman-max-2',
  'names': ['main-workflows.patch', 'MAIN-WORKFLOWS.md'],
  'prior_receipt_sha256': None},
 'mmos-compound-edge-3dda-01a19fff-v1': {
  'root': '01a15741-5e68-7803-8eb4-ccac74a6c04b',
  'parent': '01a19fff-121a-7643-bb9e-13f6e6d460cc', 'host': 'ubuntu3',
  'lease_id': '992ec0f01737', 'account': None,
  'names': ['edge-repair.patch'], 'prior_receipt_sha256': None},
}
HEX = re.compile(r'[0-9a-f]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')


def canonical(value):
 return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def scope_for(run):
 if type(run) is not str or run not in SCOPES:
  raise ValueError('post_failure_scope_not_admitted')
 return SCOPES[run]


def validate_artifact_binding(run, artifact):
 scope_for(run)
 if type(artifact) is not dict or set(artifact) != {'packet_sha256', 'support_files'}:
  raise ValueError('original_artifact_binding_missing')
 if type(artifact['packet_sha256']) is not str or not HEX.fullmatch(artifact['packet_sha256']):
  raise ValueError('original_packet_digest_invalid')
 files = artifact['support_files']
 if (type(files) is not dict or len(files) != 37
     or any(type(k) is not str or type(v) is not str or not HEX.fullmatch(v) for k,v in files.items())
     or hashlib.sha256(canonical({'schema': 'remote-support-code.v1', 'files': files})).hexdigest() != SUPPORT):
  raise ValueError('original_support_manifest_mismatch')


def validate_contract(run, artifact):
 scope = scope_for(run)
 if type(artifact) is not dict or set(artifact) != {'packet_sha256', 'contract', 'support_files'}:
  raise ValueError('original_artifact_binding_missing')
 validate_artifact_binding(run, {k:artifact[k] for k in ('packet_sha256','support_files')})
 contract = artifact['contract']
 if (type(contract) is not dict or set(contract) !=
     {'schema', 'run_id', 'root', 'parent', 'support_digest', 'names', 'body_sha256'}
     or contract['schema'] != 'mastermind.fabric_artifact_production.v1'
     or contract['run_id'] != run or contract['support_digest'] != SUPPORT
     or any(contract[k] != scope[k] for k in ('root', 'parent', 'names'))
     or type(contract['body_sha256']) is not str or not HEX.fullmatch(contract['body_sha256'])):
  raise ValueError('original_contract_mismatch')


def validate_request(request):
 keys = {'schema', 'run_id', 'root', 'parent', 'host', 'support_digest', 'artifact',
         'launch_binding_sha256', 'terminal_log_sha256', 'prior_receipt_sha256',
         'request_record_sha256', 'request_launch_sha256', 'invocation_id'}
 if type(request) is not dict or set(request) != keys or request['schema'] != SCHEMA:
  raise ValueError('post_failure_request_shape')
 scope = scope_for(request['run_id'])
 if (any(request[k] != scope[k] for k in ('root', 'parent', 'host'))
     or request['support_digest'] != SUPPORT
     or request['prior_receipt_sha256'] != scope['prior_receipt_sha256']):
  raise ValueError('original_incident_binding_unqualified')
 if type(request['invocation_id']) is not str or re.fullmatch('[0-9a-f]{32}',request['invocation_id']) is None:
  raise ValueError('post_failure_invocation_invalid')
 for key in ('launch_binding_sha256', 'terminal_log_sha256', 'request_record_sha256','request_launch_sha256'):
  if type(request[key]) is not str or not HEX.fullmatch(request[key]):
   raise ValueError('post_failure_source_digest_invalid')
 validate_artifact_binding(request['run_id'], request['artifact'])
 return scope


def _int(value, low=0):
 return type(value) is int and low <= value <= 2**63-1


def project_report(request, original):
 """Project only bounded facts, without forwarding errors/streams or attesting code.

 The existing reader requalifies the actual original remote packet and support.
 This phase performs no PID census. Even an authentic old completion record has
 no child start-ticks/boot field in the original producer's closed receipt shape.
 """
 validate_request(request)
 if (type(original) is not dict or original.get('schema') != 'mastermind.run_observation.v1'
     or original.get('run_id') != request['run_id']
     or original.get('expected_support_digest') != SUPPORT
     or original.get('status') not in ('observed', 'unavailable')
     or type(original.get('observations')) is not dict):
  raise ValueError('post_failure_original_report_binding')
 obs = original['observations']
 if set(obs) - {'support', 'marker', 'returncode', 'stdout', 'process_receipt'}:
  raise ValueError('post_failure_unrequested_observation')
 def present(name):
  row = obs.get(name)
  return type(row) is dict and row.get('status') == 'observed'
 support = obs.get('support', {})
 verified = (present('support') and support.get('digest') == SUPPORT
             and type(support.get('verified_code_files')) is int and support.get('verified_code_files') == 37
             and support.get('running_process_source_identity_proven') is False)
 marker = obs.get('marker', {})
 hold = marker.get('reconciliation_hold') if present('marker') else None
 held = (type(hold) is dict and hold.get('schema') == 'mastermind.local_lane_reconciliation_hold.v1'
         and hold.get('reason') == 'worker_cleanup_unproven'
         and hold.get('original_lease_key_matches') is True)
 rc = obs.get('returncode', {}).get('returncode') if present('returncode') else None
 if rc is not None and (not _int(rc) or rc > 255): raise ValueError('post_failure_returncode_type')
 process = obs.get('process_receipt', {})
 last = process.get('last_record') if present('process_receipt') else None
 recorded = None
 if last is not None:
  if type(last) is not dict or not _int(last.get('pid'), 1) or type(last.get('recorded_cleanup')) is not dict:
   raise ValueError('post_failure_record_shape')
  if type(process.get('receipt_sha256')) is not str or not HEX.fullmatch(process['receipt_sha256']):
   raise ValueError('original_record_digest_missing')
  cleanup = last['recorded_cleanup']
  if any(type(v) is not bool for v in cleanup.values()):
   raise ValueError('post_failure_capture_flag_type')
  recorded = {'child_pid': last['pid'],
              'recorded_cleanup': {k: cleanup.get(k) for k in
               ('identity_verified', 'stdout_capture_complete', 'stderr_capture_complete', 'stdin_delivery_complete')},
              'source_of_claim': 'original_receipt_record_only',
              'recorded_pgid':last.get('recorded_pgid'), 'recorded_sid':last.get('recorded_sid'),
              'original_record_sha256':process['receipt_sha256']}
 permission=original.get('reason')=='os_permission_denied'
 reasons = ['ORIGINAL_METADATA_PERMISSION_REFUSED'] if permission else []
 if not verified: reasons.append('ORIGINAL_SUPPORT_UNQUALIFIED')
 if not held: reasons.append('ORIGINAL_HOLD_UNQUALIFIED')
 if rc != 76: reasons.append('ORIGINAL_TERMINAL_76_UNQUALIFIED')
 if last is None: reasons.append('FINAL_ORIGINAL_PROCESS_RECEIPT_NOT_OBSERVED')
 else: reasons.append('ORIGINAL_COMPLETION_RECORD_OBSERVED_NOT_SETTLEMENT')
 reasons += ['ORIGINAL_HOLD_HOST_LEASE_NOT_PROVEN', 'ORIGINAL_CHILD_START_GENERATION_NOT_PROVEN', 'ORIGINAL_BOOT_IDENTITY_NOT_PROVEN',
             'CAPTURE_COMPLETENESS_NOT_RECONSTRUCTED', 'ARTIFACT_EXPORT_REMAINS_HELD']
 return {'schema': SCHEMA, 'run_id': request['run_id'], 'state': 'UNKNOWN',
         'reason_codes': reasons, 'original_support_observed': verified,
         'original_hold_observed': held, 'original_hold_binding_proven':False,
         'outer_returncode_observed': rc,
         'final_process_receipt_observed': last is not None, 'recorded_completion': recorded,
         'earlier_absence_is_not_final_absence': True, 'permission_refusal_observed':permission,
         'pid_probe_performed': False, 'stream_content_read': False,
         'execution_replayed': False, 'effect_state_changed': False,
         'lease_released': False, 'export_authorized': False, 'outcome_accepted': False,
         'original_report_sha256': hashlib.sha256(canonical(original)).hexdigest()}


def original_packet(base, reader, request):
 """Read the ACTUAL retained packet. Never re-encode a missing original packet."""
 raw, _ = reader.read(('lanes','tmp',request['run_id']+'.txt'),2*1024*1024)
 if hashlib.sha256(raw).hexdigest() != request['artifact']['packet_sha256']:
  raise ValueError('original_remote_packet_unqualified')
 line, sep, body = raw.partition(b'\n')
 prefix=b'FABRIC_ARTIFACT_REQUEST_V1 '
 if not sep or not line.startswith(prefix) or len(line)>65536:
  raise ValueError('original_remote_contract_unqualified')
 contract=base['strict_json'](line[len(prefix):])
 artifact=dict(request['artifact'],contract=contract)
 validate_contract(request['run_id'],artifact)
 if hashlib.sha256(body).hexdigest()!=contract['body_sha256']:
  raise ValueError('original_remote_body_unqualified')
 return artifact


def observe_metadata(base, request, artifact):
 """Reuse the existing reader, with a same-hash final-record metadata view.

 No missing record is recreated. These PID/PGID/SID values remain recorded
 claims, not generation/boot identity or authority to census/terminate a child.
 """
 original=base['observe'](request['run_id'],request['support_digest'],observe_pid=False,artifact=artifact)
 row=original.get('observations',{}).get('process_receipt',{})
 if original.get('status')!='observed' or row.get('status')!='observed':return original
 try:
  import os,pwd
  uid=os.getuid();home=pwd.getpwuid(uid).pw_dir
  with base['Reader'](home,uid) as source:
   raw,_=source.read(('lanes','ext','lanes',request['run_id']+'.process.jsonl'),65536)
   if hashlib.sha256(raw).hexdigest()!=row.get('receipt_sha256'):
    raise ValueError('original_process_record_changed')
   record=base['strict_json'](raw.splitlines()[-1])
   if (record.get('schema')!='mastermind.local_owned_process_receipt.v1'
       or record.get('label')!=request['run_id'] or record.get('pid')!=row['last_record']['pid']):
    raise ValueError('original_process_record_binding')
   cleanup=record.get('cleanup',{})
   pgid=record.get('pgid');sid=cleanup.get('session_id')
   if (pgid is not None and (not _int(pgid,1) or pgid>2**31-1)
       or sid is not None and (not _int(sid,1) or sid>2**31-1)):
    raise ValueError('original_process_record_identity_shape')
   source.verify()
  row['last_record'].update(recorded_pgid=pgid,recorded_sid=sid,original_record_sha256=row['receipt_sha256'])
 except (OSError,ValueError,KeyError,IndexError,TypeError) as exc:
  original['status']='unavailable';original['request_stopped']=True
  original['reason']=('os_permission_denied' if isinstance(exc,OSError) and exc.errno in (1,13) else 'original_process_record_unqualified')
  original['observations']['process_receipt']={'status':'unavailable','reason':'original_process_record_unqualified'}
 return original


def _private_read_one(files, path, remaining, expected_private):
    """Phase-local composition of incumbent bounds/codec on one checked FD.

    Only snapshot_artifact invokes this; no endpoint or request parameter selects
    it. Its caller already resolved the original packet-declared file name.
    The canonical reader and every historical helper stay byte-exact.
    """
    os, stat = files["os"], files["stat"]
    validate_path, identity = files["validate_path"], files["identity"]
    MAX_FILE = files["MAX_FILE"]
    import base64
    directory, name = validate_path(path)
    fds = []
    try:
        tmp = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(tmp)
        parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=tmp)
        fds.append(parent)
        before_parent = os.fstat(parent)
        if before_parent.st_uid != os.getuid() or before_parent.st_mode & 0o022:
            raise ValueError("directory_owner_or_mode")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o002:
            raise ValueError("file_owner_mode_or_type")
        if (identity(before) != expected_private
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
            raise ValueError("private_snapshot_custody")
        if before.st_size > MAX_FILE or before.st_size > remaining:
            raise ValueError("size_limit")
        chunks = []
        budget = min(MAX_FILE, remaining) + 1
        while budget:
            chunk = os.read(fd, min(budget, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            budget -= len(chunk)
        raw = b"".join(chunks)
        after_parent = os.stat(directory, dir_fd=tmp, follow_symlinks=False)
        if (identity(before) != identity(os.fstat(fd))
                or identity(before) != identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                or identity(before_parent) != identity(after_parent)
                or len(raw) != before.st_size):
            raise ValueError("changed_during_read")
        return {"path": path, "status": "RETRIEVED", "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "data_base64": base64.b64encode(raw).decode(),
                "observed_file": {"device": before.st_dev, "inode": before.st_ino,
                                  "mtime_ns": before.st_mtime_ns, "uid": before.st_uid,
                                  "mode": stat.S_IMODE(before.st_mode)}}
    except FileNotFoundError:
        return {"path": path, "status": "NOT_FOUND", "reason": "missing_at_read"}
    except (OSError, ValueError) as exc:
        return {"path": path, "status": "UNAVAILABLE",
                "reason": str(exc) if isinstance(exc, ValueError) else "filesystem_refused"}
    finally:
        for fd in reversed(fds):
            os.close(fd)


def snapshot_artifact(files, path, remaining):
 """Phase-local stricter composition; canonical byte reader stays unchanged.

 Hold the private single-link inode before/after its one stable content read.
 No second content read, chmod, rename, cleanup, alternative path or retry.
 """
 os=files['os'];stat=files['stat'];fds=[]
 try:
  directory,name=files['validate_path'](path)
  tmp=os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fds.append(tmp)
  parent=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=tmp);fds.append(parent)
  parent_before=os.fstat(parent)
  if parent_before.st_uid!=os.getuid() or stat.S_IMODE(parent_before.st_mode)!=0o700:
   raise ValueError('private_snapshot_custody')
  fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);fds.append(fd)
  before=os.fstat(fd)
  if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
      or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1):
   raise ValueError('private_snapshot_custody')
  item=_private_read_one(files,path,remaining,files['identity'](before))
  if item.get('status')!='RETRIEVED':return item
  meta=item.get('observed_file',{})
  if (files['identity'](before)!=files['identity'](os.fstat(fd))
      or files['identity'](before)!=files['identity'](os.stat(name,dir_fd=parent,follow_symlinks=False))
      or files['identity'](parent_before)!=files['identity'](os.stat(directory,dir_fd=tmp,follow_symlinks=False))
      or (meta.get('device'),meta.get('inode'),meta.get('uid'),meta.get('mode'))!=
         (before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode))):
   raise ValueError('changed_during_read')
  item['observed_file']['links']=1
  return item
 except FileNotFoundError:
  return {'path':path,'status':'NOT_FOUND','reason':'missing_at_read'}
 except (OSError,ValueError) as exc:
  return {'path':path,'status':'UNAVAILABLE','reason':('permission_refused' if isinstance(exc,OSError) and exc.errno in (1,13) else 'private_snapshot_custody')}
 finally:
  for fd in reversed(fds):os.close(fd)


def observe_original(base, files, request):
 """Same fixed reader, no PID probe/stream content. Snapshots remain unsettled."""
 validate_request(request)
 import os, pwd
 uid=os.getuid();home=pwd.getpwuid(uid).pw_dir
 with base['Reader'](home,uid) as source:
  artifact=original_packet(base,source,request)
  source.verify()
 original=observe_metadata(base,request,artifact)
 projection=project_report(request,original)
 # A stable byte snapshot is not worker completion, even if every file exists.
 # Paths come ONLY from the hash-bound ACTUAL packet, never request argv.
 scope={k:artifact['contract'][k] for k in ('root','parent','run_id')}
 directory='/tmp/fabric-'+hashlib.sha256(canonical(scope)).hexdigest()[:40]
 entries=[];remaining=files['MAX_TOTAL']
 if (projection['original_support_observed'] and original.get('status')=='observed'
     and not original.get('request_stopped') and 'directory_diagnostic' not in original):
  for name in artifact['contract']['names']:
   item=snapshot_artifact(files,directory+'/'+name,remaining)
   remaining-=item.get('bytes',0);entries.append(item)
   if item.get('status')=='UNAVAILABLE':break  # No onward alternate/denied read.
 if not entries:
  entries=[{'path':directory+'/'+artifact['contract']['names'][0],
            'status':'UNAVAILABLE','reason':'original_metadata_unqualified'}]
 return {'report':projection,'files':entries,'original_contract':artifact['contract'],
         'snapshot_state':'PARTIAL_UNSETTLED','source_adoption_allowed':False}
