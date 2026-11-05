"""Original-parent, read-only post-failure metadata phase for three held incidents.

No apply/export/settle verb. Native lineage and retained hashes are correlation,
not authentication, admission, retrospective code attestation, or lease authority.
The original parent must execute under its actual existing tool/host grants.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import sqlite3
import subprocess

import artifact_delivery as delivery
import artifact_reader as reader
import fabric_task
import post_failure_observation as model

PRIOR = {
 'macro-native-publisher-routing-20261105-01a1aaa4': Path('/Volumes/Mastermind/evidence/release-delivery-controller-20261105-01a1aa50/routing-worker-ordinary-observation/receipt.json'),
}
MAX_BYTES = 2 * 1024 * 1024


def native_lineage(expected_parent, root):
 """Read actual native session metadata from fixed local storage, not argv IDs."""
 current = os.environ.get('CODEX_THREAD_ID')
 if (current != expected_parent or os.environ.get('POOL_ORCHESTRATOR_ID', root) != root):
  raise ValueError('original_actual_native_parent_required')
 start = Path.home() / '.codex/sessions'
 seen, records = set(), []
 for _ in range(16):
  if current in seen or not model.IDENT.fullmatch(current):
   raise ValueError('native_ancestor_cycle_or_invalid')
  seen.add(current)
  matches = list(start.glob('**/*-' + current + '.jsonl'))
  if len(matches) != 1:
   raise ValueError('actual_native_session_metadata_unavailable')
  path = matches[0]
  with delivery.DirectoryChain(path.parent) as chain:
   # Read only the bounded first session_meta record, never a transcript.
   chain.verify()
   fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=chain.fd)
   try:
    before = os.fstat(fd)
    import stat
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
        or before.st_nlink != 1 or before.st_mode & 0o022):
     raise ValueError('native_session_custody_unqualified')
    raw = b''
    while b'\n' not in raw and len(raw) <= 65536:
     part = os.read(fd, 1)
     if not part: break
     raw += part
    if b'\n' not in raw or len(raw.split(b'\n', 1)[0]) > 65536:
     raise ValueError('native_session_meta_invalid')
    after = os.fstat(fd)
    path_after=os.stat(path.name,dir_fd=chain.fd,follow_symlinks=False)
    identity=lambda x:(x.st_dev,x.st_ino,x.st_uid,x.st_nlink,x.st_mode)
    if identity(before)!=identity(after) or identity(before)!=identity(path_after):
     raise ValueError('native_session_identity_changed')
    os.lseek(fd,0,os.SEEK_SET);repeat=b''
    while b'\n' not in repeat and len(repeat)<=65536:
     part=os.read(fd,1)
     if not part:break
     repeat+=part
    if repeat!=raw:raise ValueError('native_session_meta_changed')
    event = reader.strict_json(raw.split(b'\n', 1)[0])
    chain.verify()
   finally:
    os.close(fd)
  meta = event.get('payload') if type(event) is dict and event.get('type') == 'session_meta' else None
  if type(meta) is not dict or meta.get('id') != current:
   raise ValueError('native_session_meta_identity_mismatch')
  records.append({'id': current, 'parent_thread_id': meta.get('parent_thread_id'),
                  'session_meta_sha256': hashlib.sha256(raw.split(b'\n', 1)[0]).hexdigest()})
  if current == root:
   return records
  current = meta.get('parent_thread_id')
  if type(current) is not str:
   raise ValueError('native_original_root_not_in_ancestry')
 raise ValueError('native_ancestry_limit')


def snapshot(run, *, invocation_id):
 scope=model.scope_for(run)
 ancestry=native_lineage(scope['parent'],scope['root'])
 here=delivery.HERE;state=here/'state/remote_sub'
 request_raw=delivery.local_file(state/(run+'.request.json'),32768)
 launch_raw=delivery.local_file(state/(run+'.request-launch.json'),32768)
 recorded=reader.strict_json(request_raw);launch=reader.strict_json(launch_raw)
 if (type(recorded) is not dict or recorded.get('schema')!='mastermind.fabric_request_artifact.v1'
     or recorded.get('run_id')!=run or recorded.get('root_id')!=scope['root']
     or recorded.get('parent_run_id')!=scope['parent'] or recorded.get('packet')!=run+'.request.packet'
     or type(recorded.get('packet_sha256')) is not str or not model.HEX.fullmatch(recorded['packet_sha256'])):
  raise ValueError('original_native_request_record_unqualified')
 if (type(launch) is not dict or launch.get('schema')!='mastermind.fabric_request_launch.v1'
     or launch.get('run_id')!=run or launch.get('root_id')!=scope['root']
     or launch.get('parent_run_id')!=scope['parent'] or launch.get('state')!='LAUNCH_ATTEMPT_RESERVED'
     or launch.get('packet_sha256')!=recorded['packet_sha256']
     or launch.get('request_sha256')!=delivery.digest(request_raw)):
  raise ValueError('original_native_launch_record_unqualified')
 log_path=state/(run+'.log');log=delivery.local_file(log_path,fabric_task.MAX_LOG_BYTES)
 lineage=fabric_task._active_lineage_projection(run,log)['controller_lineage']
 if (lineage.get('state')!='RECORDED_PRE_LAUNCH' or lineage.get('root_id')!=scope['root']
     or lineage.get('parent_run_id')!=scope['parent']):
  raise ValueError('original_launch_prefix_unqualified')
 pattern=re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='+re.escape(run)+r' host=ubuntu3\] (.*)\n')
 lines=log.decode('utf-8').splitlines(keepends=True);events=[]
 for line in lines:
  match=pattern.fullmatch(line)
  if not match:raise ValueError('original_terminal_log_shape')
  events.append(match[1])
 bindings=[reader.strict_json(x[len('LAUNCH_BINDING '):]) for x in events if x.startswith('LAUNCH_BINDING ')]
 if (len(bindings)!=1 or [x for x in events if x.startswith('LAUNCH_ATTEMPT ')]!=['LAUNCH_ATTEMPT attempt=1']
     or [x for x in events if x.startswith('REMOTE_DONE ')]!=['REMOTE_DONE rc=76']
     or [x for x in events if x.startswith('DONE ')]!=['DONE rc=76 signal=effect_unknown reason=remote_cleanup_unproven']
     or [x for x in events if x.startswith('LEASE_PRESERVED ')]!=['LEASE_PRESERVED effect_unknown=1 lease='+scope['lease_id']]):
  raise ValueError('exact_original_cleanup_failure_not_retained')
 binding=bindings[0]
 if (any(binding.get(k)!=scope[k] for k in ('root','parent','host','lease_id'))
     or scope['account'] is not None and binding.get('account')!=scope['account']
     or binding.get('run_id')!=run or binding.get('support_digest')!=model.SUPPORT):
  raise ValueError('original_terminal_launch_binding_mismatch')
 manifest_raw=delivery.local_file(state/(run+'.support.json'),MAX_BYTES)
 files=reader.strict_json(manifest_raw)
 artifact={'packet_sha256':binding['packet_sha256'],'support_files':files}
 model.validate_artifact_binding(run,artifact)
 # A prior qualified observation is an additional immutable cross-check where
 # it actually exists. Its pre-failure absences never become current facts.
 prior_raw=None
 if scope['prior_receipt_sha256'] is not None:
  prior_raw=_read_witness(PRIOR[run])
  if delivery.digest(prior_raw)!=scope['prior_receipt_sha256']:
   raise ValueError('original_observation_witness_changed')
  prior=reader.strict_json(prior_raw);req=prior.get('request',{})
  if (prior.get('schema')!='mastermind.fabric_run_observation_receipt.v1'
      or prior.get('state')!='OBSERVED' or prior.get('effect_state_changed') is not False
      or prior.get('execution_replayed') is not False or prior.get('outcome_accepted') is not False
      or req.get('run_id')!=run or any(req.get(k)!=scope[k] for k in ('root','parent','host'))
      or {k:req.get('artifact',{}).get(k) for k in artifact}!=artifact):
   raise ValueError('original_observation_witness_unqualified')
  model.validate_contract(run,req['artifact'])
  prefix=''.join(lines[:events.index('LAUNCH_ATTEMPT attempt=1')+1]).encode()
  old=prior.get('evidence',{}).get('evidence_sha256',{})
  if old.get('log')!=delivery.digest(prefix) or old.get('support')!=delivery.digest(manifest_raw):
   raise ValueError('original_contemporaneous_launch_support_changed')
 lease=delivery.retained_lease(scope['lease_id'],include_pool=True)
 if (lease is None or any(lease.get(k)!=v for k,v in {'id':scope['lease_id'],
     'orchestrator_id':scope['root'],'host':scope['host'],'account':binding['account'],
     'model':binding['requested_model'],'pool':binding['pool']}.items())):
  raise ValueError('original_retained_lease_binding_mismatch')
 registry_raw=delivery.local_file(here/'hosts.json',MAX_BYTES);registry=reader.strict_json(registry_raw)
 host=registry.get(scope['host'],{});alias=host.get('ssh_alias')
 if (type(alias) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',alias)
     or binding['mode'] not in host.get('allowed_modes',[])
     or prior_raw is not None and reader.strict_json(prior_raw).get('evidence',{}).get('ssh_alias')!=alias):
  raise ValueError('original_host_transport_binding_changed')
 request={'schema':model.SCHEMA,'run_id':run,'root':scope['root'],'parent':scope['parent'],
  'host':scope['host'],'support_digest':model.SUPPORT,'artifact':artifact,
  'launch_binding_sha256':delivery.digest(reader.canonical(binding)),
  'terminal_log_sha256':delivery.digest(log),'prior_receipt_sha256':scope['prior_receipt_sha256'],
  'request_record_sha256':delivery.digest(request_raw),'request_launch_sha256':delivery.digest(launch_raw),
  'invocation_id':invocation_id}
 model.validate_request(request)
 sources={name:delivery.digest(delivery.local_file(here/name,65536)) for name in
          ('run_observation.py','post_failure_observation.py','artifact_reader.py')}
 proof={'ssh_alias':alias,'source_sha256':sources,'native_ancestry':ancestry,
  'local_evidence_sha256':{'terminal_log':delivery.digest(log),'support':delivery.digest(manifest_raw),
   'registry':delivery.digest(registry_raw),'request':delivery.digest(request_raw),'launch':delivery.digest(launch_raw),
   'prior_receipt':None if prior_raw is None else delivery.digest(prior_raw)},
  'authority':'Original-parent/retained-source correlation; not authentication/admission or retrospective execution attestation'}
 if (delivery.local_file(log_path,fabric_task.MAX_LOG_BYTES)!=log
     or delivery.local_file(state/(run+'.request.json'),32768)!=request_raw
     or delivery.local_file(state/(run+'.request-launch.json'),32768)!=launch_raw
     or delivery.local_file(state/(run+'.support.json'),MAX_BYTES)!=manifest_raw
     or prior_raw is not None and _read_witness(PRIOR[run])!=prior_raw):
  raise ValueError('post_failure_sources_changed')
 return request,proof


def _read_witness(path):
 with delivery.DirectoryChain(path.parent) as chain:
  return delivery.read_local_at(chain, path.name, MAX_BYTES)


def qualify(request):
 model.validate_request(request)
 current, proof = snapshot(request['run_id'],invocation_id=request['invocation_id'])
 if request != current: raise ValueError('post_failure_request_changed')
 return proof


def code_for_request(request, *, expected_sources):
 proof = qualify(request)
 if expected_sources != proof['source_sha256']:
  raise ValueError('post_failure_observer_source_changed')
 source_bytes = {name:delivery.local_file(delivery.HERE/name,65536) for name in expected_sources}
 if set(source_bytes) != {'run_observation.py','post_failure_observation.py','artifact_reader.py'}:
  raise ValueError('post_failure_code_scope')
 if (any(delivery.digest(raw)!=expected_sources[name] for name,raw in source_bytes.items())
     or expected_sources['artifact_reader.py']!=delivery._ORIGINAL_READER_SHA256):
  raise ValueError('post_failure_exact_code_bytes_changed')
 # Keep these EXACT checked byte strings; no later path reread constructs code.
 sources={name:raw.decode() for name,raw in source_bytes.items()}
 return ('import sys,json,hashlib\nbase={"__name__":"_original_metadata_reader"}\n'
  'exec('+repr(sources['run_observation.py'])+',base)\n'
  'phase={"__name__":"_post_failure_projection"}\n'
  'exec('+repr(sources['post_failure_observation.py'])+',phase)\n'
  'files={"__name__":"_fixed_artifact_reader"}\n'
  'exec('+repr(sources['artifact_reader.py'])+',files)\n'
  'raw=sys.stdin.buffer.read(8193)\nassert len(raw)<=8192\n'
  'req=base["strict_json"](raw)\nassert req=='+repr(request)+'\n'
  'report=phase["observe_original"](base,files,req)\n'
  'print(json.dumps({"schema":req["schema"],"request_sha256":hashlib.sha256(phase["canonical"](req)).hexdigest(),"report":report},sort_keys=True,separators=(",",":")))\n')


def validate_response(raw, request):
 model.validate_request(request)
 if len(raw)>reader.MAX_RESPONSE: raise ValueError('post_failure_response_limit')
 value = reader.strict_json(raw)
 if (type(value) is not dict or set(value) != {'schema','request_sha256','report'}
     or value['schema'] != model.SCHEMA
     or value['request_sha256'] != delivery.digest(reader.canonical(request))):
  raise ValueError('post_failure_response_binding')
 bundle=value['report']
 if (type(bundle) is not dict or set(bundle)!={'report','files','original_contract','snapshot_state','source_adoption_allowed'}
     or bundle['snapshot_state']!='PARTIAL_UNSETTLED' or bundle['source_adoption_allowed'] is not False):
  raise ValueError('post_failure_snapshot_shape')
 model.validate_contract(request['run_id'],dict(request['artifact'],contract=bundle['original_contract']))
 report=bundle['report']
 expected = {'schema','run_id','state','reason_codes','original_support_observed',
  'original_hold_observed','original_hold_binding_proven','outer_returncode_observed','final_process_receipt_observed',
  'recorded_completion','earlier_absence_is_not_final_absence','permission_refusal_observed','pid_probe_performed',
  'stream_content_read','execution_replayed','effect_state_changed','lease_released',
  'export_authorized','outcome_accepted','original_report_sha256'}
 if type(report) is not dict or set(report) != expected or report['schema'] != model.SCHEMA or report['run_id'] != request['run_id'] or report['state'] != 'UNKNOWN':
  raise ValueError('post_failure_response_shape')
 for key in ('pid_probe_performed','stream_content_read','execution_replayed','effect_state_changed','lease_released','export_authorized','outcome_accepted','original_hold_binding_proven'):
  if report[key] is not False: raise ValueError('post_failure_authority_injection')
 for key in ('original_support_observed','original_hold_observed','final_process_receipt_observed','permission_refusal_observed'):
  if type(report[key]) is not bool: raise ValueError('post_failure_observation_type')
 if report['earlier_absence_is_not_final_absence'] is not True:
  raise ValueError('post_failure_prior_absence_promotion')
 if type(report['original_report_sha256']) is not str or not model.HEX.fullmatch(report['original_report_sha256']):
  raise ValueError('post_failure_report_digest')
 # Recompute the finite projection shape with the model's validator below.
 allowed = {'ORIGINAL_METADATA_PERMISSION_REFUSED','ORIGINAL_SUPPORT_UNQUALIFIED','ORIGINAL_HOLD_UNQUALIFIED','ORIGINAL_TERMINAL_76_UNQUALIFIED',
  'FINAL_ORIGINAL_PROCESS_RECEIPT_NOT_OBSERVED','ORIGINAL_COMPLETION_RECORD_OBSERVED_NOT_SETTLEMENT',
  'ORIGINAL_HOLD_HOST_LEASE_NOT_PROVEN','ORIGINAL_CHILD_START_GENERATION_NOT_PROVEN','ORIGINAL_BOOT_IDENTITY_NOT_PROVEN',
  'CAPTURE_COMPLETENESS_NOT_RECONSTRUCTED','ARTIFACT_EXPORT_REMAINS_HELD'}
 if (type(report['reason_codes']) is not list or not report['reason_codes']
     or any(type(x) is not str or x not in allowed for x in report['reason_codes'])
     or len(set(report['reason_codes'])) != len(report['reason_codes'])):
  raise ValueError('post_failure_reason_code_shape')
 if report['outer_returncode_observed'] is not None and (type(report['outer_returncode_observed']) is not int or not 0<=report['outer_returncode_observed']<=255):
  raise ValueError('post_failure_returncode_shape')
 record=report['recorded_completion']
 if record is not None:
  if (type(record) is not dict or set(record) != {'child_pid','recorded_cleanup','source_of_claim','recorded_pgid','recorded_sid','original_record_sha256'}
      or not model._int(record['child_pid'],1) or record['child_pid']>2**31-1
      or record['source_of_claim'] != 'original_receipt_record_only'
      or type(record['recorded_cleanup']) is not dict
      or set(record['recorded_cleanup']) != {'identity_verified','stdout_capture_complete','stderr_capture_complete','stdin_delivery_complete'}
      or any(x is not None and type(x) is not bool for x in record['recorded_cleanup'].values())):
   raise ValueError('post_failure_record_projection_shape')
  for key in ('recorded_pgid','recorded_sid'):
   if record[key] is not None and (not model._int(record[key],1) or record[key]>2**31-1):
    raise ValueError('post_failure_record_projection_identity')
  if type(record['original_record_sha256']) is not str or not model.HEX.fullmatch(record['original_record_sha256']):
   raise ValueError('post_failure_original_record_digest')
 if report['final_process_receipt_observed'] != (record is not None):
  raise ValueError('post_failure_record_projection_mismatch')
 entries=bundle['files'];contract=bundle['original_contract']
 scope={k:contract[k] for k in ('root','parent','run_id')}
 directory='/tmp/fabric-'+hashlib.sha256(reader.canonical(scope)).hexdigest()[:40]
 paths=[directory+'/'+name for name in contract['names']]
 if type(entries) is not list or len(entries)>len(paths):raise ValueError('post_failure_files_shape')
 normalized=[];remaining=reader.MAX_TOTAL
 import base64
 stopped=False
 for index,item in enumerate(entries):
  if stopped or type(item) is not dict or item.get('path')!=paths[index]:
   raise ValueError('post_failure_file_scope')
  status=item.get('status')
  if status=='RETRIEVED':
   if set(item)!={'path','status','bytes','sha256','data_base64','observed_file'}:
    raise ValueError('post_failure_file_fields')
   if (type(item['bytes']) is not int or not 0<=item['bytes']<=min(reader.MAX_FILE,remaining)
       or type(item['sha256']) is not str or not model.HEX.fullmatch(item['sha256'])
       or type(item['data_base64']) is not str):
    raise ValueError('post_failure_file_limit')
   try:data=base64.b64decode(item['data_base64'],validate=True)
   except (ValueError,TypeError):raise ValueError('post_failure_file_encoding') from None
   meta=item['observed_file']
   if (type(meta) is not dict or set(meta)!={'device','inode','mtime_ns','uid','mode','links'}
       or any(type(x) is not int or x<0 for x in meta.values())
       or meta['mode']!=0o600 or meta['links']!=1
       or len(data)!=item['bytes'] or delivery.digest(data)!=item['sha256']):
    raise ValueError('post_failure_file_snapshot_unqualified')
   remaining-=len(data)
   normalized.append(dict(item,local_name='unsettled-'+contract['names'][index]))
  elif status in ('NOT_FOUND','UNAVAILABLE'):
   if (set(item)!={'path','status','reason'} or type(item['reason']) is not str
       or item['reason'] not in {'missing_at_read','directory_owner_or_mode','file_owner_mode_or_type',
        'size_limit','changed_during_read','filesystem_refused','permission_refused','private_snapshot_custody','original_metadata_unqualified'}):
    raise ValueError('post_failure_file_diagnostic_shape')
   normalized.append(item);stopped=status=='UNAVAILABLE'
  else:raise ValueError('post_failure_file_status')
 if len(entries)<len(paths) and not stopped:raise ValueError('post_failure_partial_response_unexplained')
 return {'report':report,'files':normalized,'snapshot_state':'PARTIAL_UNSETTLED','source_adoption_allowed':False}


def observe(request, destination):
 proof=qualify(request)
 chain=delivery.reserve_destination(destination)
 receipt={'schema':model.SCHEMA,'request':request,'evidence':proof,'state':'OBSERVATION_PENDING',
  'files':[],'report':None,'execution_replayed':False,'effect_state_changed':False,
  'outcome_accepted':False,'source_adoption_allowed':False,'retry_authorized':False,
  'read_transport_state':'NOT_ATTEMPTED'}
 def unchanged():
  if qualify(request)!=proof:raise ValueError('post_failure_sources_changed')
 try:
  delivery.write_exclusive(chain.fd,'request.json',reader.canonical(receipt))
  try:
   unchanged();chain.verify();receipt['read_transport_state']='ATTEMPTED_UNCONFIRMED'
   raw=delivery.transport(proof['ssh_alias'],request,current_sources_sha256=proof['source_sha256'])
   receipt['read_transport_state']='RESPONSE_RECEIVED'
   validated=validate_response(raw,request);receipt['report']=validated['report']
   import base64
   for item in validated['files']:
    item=dict(item)
    if item['status']=='RETRIEVED':
     data=base64.b64decode(item.pop('data_base64'),validate=True)
     delivery.write_exclusive(chain.fd,item['local_name'],data)
     item['status']='RETAINED_UNSETTLED';item['snapshot_only']=True
     item['source_adoption_allowed']=False
    receipt['files'].append(item)
   unchanged();chain.verify();receipt['state']='PARTIAL_UNSETTLED'
   receipt['local_preservation_created']=True
  except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,sqlite3.Error,subprocess.SubprocessError) as exc:
   receipt['state']='UNAVAILABLE';receipt['diagnostic_code']=('LOCAL_OS_PERMISSION_REFUSED' if isinstance(exc,OSError) and exc.errno in (1,13) else 'POST_FAILURE_READ_UNCONFIRMED')
  receipt['observed_at_epoch']=time.time()
  # One publication attempt. Never republish after an ambiguous publication.
  delivery.publish_receipt(chain,receipt,{'paths':[]},verify_source=unchanged)
  return receipt
 finally:
  chain.close()


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('run_id');parser.add_argument('--root',required=True)
 parser.add_argument('--destination',required=True)
 args=parser.parse_args(argv)
 import secrets
 try:
  scope=model.scope_for(args.run_id)
  if args.root != scope['root']:raise ValueError('original_root_mismatch')
  request,_=snapshot(args.run_id,invocation_id=secrets.token_hex(16))
  result=observe(request,Path(args.destination))
 except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,sqlite3.Error,subprocess.SubprocessError) as exc:
  print(reader.canonical({'schema':model.SCHEMA,'state':'UNAVAILABLE','diagnostic_code':('LOCAL_OS_PERMISSION_REFUSED' if isinstance(exc,OSError) and exc.errno in (1,13) else 'POST_FAILURE_SOURCE_UNQUALIFIED'),'retry_authorized':False,'effect_state_changed':False}).decode())
  return 75
 print(reader.canonical(result).decode())
 return 0


if __name__ == '__main__':
 raise SystemExit(main())
