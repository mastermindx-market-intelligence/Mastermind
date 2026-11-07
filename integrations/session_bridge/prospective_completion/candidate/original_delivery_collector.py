"""Delivery only for an original ordinary Fabric artifact producer.

No launch, lease, retry, controller takeover, ledger or acceptance effects.
The original root commissions recovery. Native environment/packet fields are
caller correlation and retained evidence, never authentication or a new grant.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

import artifact_delivery as delivery
import artifact_reader as reader
import artifact_production as production
from remote_sub_exec import validate_completion_binding

DirectoryChain = delivery.DirectoryChain
HERE = Path(__file__).resolve().parent
SCHEMA = 'mastermind.original_delivery_read.v1'
PLAIN_SCHEMA = 'mastermind.original_plain_result_contract.v1'
PLAIN_SCOPES = {'fabric-manifest-framing-review-01a11e90-v1': {'root': '01a11e90-4b5d-7f53-b966-8aaaad38701f', 'parent': '01a11e90-4b5d-7f53-b966-8aaaad38701f', 'host': 'mb', 'packet_path': '/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/fabric-start-publication-20261012-fb76f8a5c8c5e179/integrations/session_bridge/artifact_manifest_framing/REVIEW_PACKET.txt', 'packet_sha256': 'e7fb39a83f6e7456fe976c83f88f95602e2164bb00acfdf36f7aaade7e272f88', 'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114', 'destination': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/fabric-manifest-framing-review-01a11e90-v1-collection-v1'}, 'mm-os-incident-custody-direct-review-20261013-01a104e6': {'root': '01a104e6-58f8-76d3-8d99-1302a1cca072', 'parent': '01a104e6-58f8-76d3-8d99-1302a1cca072', 'host': 'ubuntu1', 'packet_path': '/Volumes/Mastermind/evidence/mastermind-os-noir-product-convergence-20261003-astra-001/production-continuation-20261010/issuer-custody-repair-20261013/direct-preventive-review-packet.md', 'packet_sha256': 'dc3bfd8aaf0358c160c7290def2b3d3c6ef45893e1042620346e8ee7070d588c', 'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114', 'destination': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/mm-os-incident-custody-direct-review-20261013-01a104e6-collection-v1'}}
BINDING_SCHEMA = 'mastermind.original_delivery_binding.v1'
RECEIPT_SCHEMA = 'mastermind.original_delivery_receipt.v1'
MAX_STDOUT = 8 * 1024 * 1024
MAX_RESPONSE = 14 * 1024 * 1024
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
HEX = re.compile(r'[a-f0-9]{64}\Z')


class OriginalDeliveryRefused(ValueError):
    """Sanitized original read refusal; never an invitation to retry."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def reject_failure_envelope(row, request, schema):
    if type(row) is not dict or row.get('state') != 'UNAVAILABLE':
        return
    allowed = {'read_request_invalid','read_contract_invalid','directory_owner_or_mode',
        'directory_chain_changed','original_file_owner_mode_type_or_size',
        'original_file_changed','original_rc_invalid','original_artifact_unavailable',
        'filesystem_refused'}
    if (set(row) != {'schema','request_sha256','state','files','artifacts','reason'}
            or row['schema'] != schema or row['request_sha256'] != sha(canonical(request))
            or row['files'] != {} or row['artifacts'] != []
            or type(row['reason']) is not str or row['reason'] not in allowed):
        raise ValueError('collection_failure_envelope_invalid')
    raise OriginalDeliveryRefused(row['reason'])


def canonical(value):
    return reader.canonical(value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require_caller(root):
    # Actual invoking root must be independently verified by its original
    # owner. This check prevents an accidental child/new-root substitution; it
    # does not turn mutable environment labels into authenticated authority.
    if (not IDENT.fullmatch(root) or os.environ.get('CODEX_THREAD_ID') != root
            or os.environ.get('POOL_ORCHESTRATOR_ID', root) != root):
        raise ValueError('original_native_root_required')


def load_binding(path, *, run_id, root, parent):
    require_caller(root)
    raw = delivery.local_file(Path(path), 65536)
    value = reader.strict_json(raw)
    fields = {'schema','run_id','root','parent','host','mode','requested_model',
              'cwd','artifact_names','sources'}
    if (type(value) is not dict or set(value) != fields or value['schema'] != BINDING_SCHEMA
            or any(value[k] != v for k,v in {'run_id':run_id,'root':root,'parent':parent}.items())
            or any(type(value[k]) is not str or not IDENT.fullmatch(value[k])
                   for k in ('run_id','root','parent','host','requested_model'))
            or value['mode'] not in production.ORDINARY_MODES | {'minimax'} or value['cwd'] != '~'
            or type(value['sources']) is not dict or set(value['sources']) != {'packet','log','support'}):
        raise ValueError('original_binding_invalid')
    plain = PLAIN_SCOPES.get(run_id)
    if (value['mode'] == 'minimax' or plain is not None) and (plain is None
            or value['mode'] != 'minimax' or value['artifact_names'] != []
            or value['requested_model'] != 'MiniMax-M3'
            or any(value[k] != plain[k] for k in ('root','parent','host'))):
        raise ValueError('plain_original_scope_unqualified')
    source = {}
    for name, item in value['sources'].items():
        if (type(item) is not dict or set(item) != {'path','sha256'}
                or type(item['sha256']) is not str or not HEX.fullmatch(item['sha256'])):
            raise ValueError('original_source_pin_invalid')
        p = Path(item['path'])
        if name == 'packet' and plain is not None:
            allowed_path = str(p) == plain['packet_path'] and item['sha256'] == plain['packet_sha256']
        else:
            allowed_path = (p.parent == HERE/'state/remote_sub' and
                ((name == 'packet' and re.fullmatch(re.escape(run_id)+r'\.packet\.[A-Za-z0-9_]+',p.name)) or
                 (name != 'packet' and p.name == run_id + ('.log' if name=='log' else '.support.json'))))
        if not allowed_path:
            raise ValueError('original_source_path_invalid')
        data = delivery.local_file(p, 2 * 1024 * 1024)
        if sha(data) != item['sha256']:
            raise ValueError('original_source_changed')
        source[name] = data
    manifest = reader.strict_json(source['support'])
    if (type(manifest) is not dict or not manifest
            or any(type(k) is not str or type(v) is not str or not HEX.fullmatch(v)
                   for k,v in manifest.items())):
        raise ValueError('original_support_mismatch')
    original_validator = None
    if plain is None:
        original_validator = delivery.original_validator_context(manifest)
    validator = original_validator if original_validator is not None else production
    contract = validator.parse_packet(source['packet'].decode('utf-8'))
    if plain is not None:
        if contract is not None:
            raise ValueError('plain_original_artifact_contract_conflict')
        contract = dict(schema=PLAIN_SCHEMA, run_id=run_id, root=root, parent=parent,
            names=[], packet_sha256=plain['packet_sha256'], support_digest=plain['support_digest'])
    if contract is None:
        # Old plaintext packets have no producer-bound root/parent/digest.
        # Do not manufacture that missing provenance from this new binding.
        raise ValueError('original_producer_contract_unavailable')
    if (any(contract[k] != value[k] for k in ('run_id','root','parent'))
            or contract['names'] != value['artifact_names']):
        raise ValueError('original_packet_scope_mismatch')
    if sha(canonical({'schema':'remote-support-code.v1','files':manifest})) != contract['support_digest']:
        raise ValueError('original_support_mismatch')
    # Ordinary runs use the explicitly bound, full-hash-qualified validator.
    # Preserve the incumbent plaintext scope's installed-source check unchanged.
    if plain is not None:
        for name in ('artifact_production.py','artifact_reader.py'):
            if manifest.get(name) != sha(delivery.local_file(HERE/name, 128*1024)):
                raise ValueError('original_producer_validator_changed')
    prefix = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=' + re.escape(run_id)
              + r' host=' + re.escape(value['host']) + r'\] (.*)')
    events=[]
    for line in source['log'].decode('utf-8').splitlines():
        match = re.fullmatch(prefix,line)
        if match: events.append(match[1])
        elif '[remote_sub id=' in line: raise ValueError('original_log_scope_mismatch')
    launches=[e for e in events if e.startswith('LAUNCH ')]
    support=[e for e in events if e.startswith('SUPPORT_VERSION_READY ')]
    if (launches != [f'LAUNCH stdout=lanes_{run_id}.stdout rc_file=ext/lanes_{run_id}.rc cwd=~']
            or [e for e in events if e.startswith('LAUNCH_ATTEMPT ')] != ['LAUNCH_ATTEMPT attempt=1']
            or len(support)!=1 or not re.fullmatch('SUPPORT_VERSION_READY digest='+contract['support_digest']+r' policy=[a-f0-9]{64}',support[0])
            or [e for e in events if e.startswith('LEASE_OK ')] != ['LEASE_OK pool='+{'glm':'glm','qwen':'bailian','minimax':'minimax'}[value['mode']]]):
        raise ValueError('original_launch_evidence_unqualified')
    delivery.assert_capsule_family(run_id)
    registry_raw=delivery.local_file(HERE/'hosts.json')
    registry=reader.strict_json(registry_raw)
    host=registry.get(value['host']) if type(registry) is dict else None
    if (type(host) is not dict or value['mode'] not in host.get('allowed_modes',[])
            or type(host.get('ssh_alias')) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',host['ssh_alias'])):
        raise ValueError('original_host_registry_unavailable')
    return value, raw, source, contract, host['ssh_alias'], registry_raw, original_validator


def remote_read(request, *, home=None):
    """Fixed read-only paths. home is an inert-test seam, never in the request."""
    if (type(request) is not dict or set(request) != {'schema','run_id','root','parent','host','contract'}
            or request['schema'] != SCHEMA
            or any(type(request[k]) is not str or not IDENT.fullmatch(request[k])
                   for k in ('run_id','root','parent','host'))):
        raise ValueError('read_request_invalid')
    contract=request['contract']
    if type(contract) is dict and contract.get('schema') == 'mastermind.prospective_completion.v1':
        return prospective_remote_read(request)
    plain = contract.get('schema') == PLAIN_SCHEMA if type(contract) is dict else False
    if request['run_id'] in PLAIN_SCOPES and not plain:
        raise ValueError('read_contract_invalid')
    if plain:
        expected = PLAIN_SCOPES.get(rid := request['run_id'])
        if (expected is None or any(request[k] != expected[k] for k in ('root','parent','host'))
                or contract != dict(schema=PLAIN_SCHEMA, run_id=rid, root=expected['root'],
                    parent=expected['parent'], names=[], packet_sha256=expected['packet_sha256'],
                    support_digest=expected['support_digest'])):
            raise ValueError('read_contract_invalid')
    # Local original source qualification validates the full contract. Recheck
    # path-bearing fields here before deriving exact artifact names remotely.
    if not plain and (type(contract) is not dict or set(contract) != {'schema','run_id','root','parent','names','body_sha256','support_digest'}
            or contract['schema'] != 'mastermind.fabric_artifact_production.v1'
            or any(contract[k]!=request[k] for k in ('run_id','root','parent'))
            or type(contract['names']) is not list or not 1<=len(contract['names'])<=8
            or len(set(contract['names']))!=len(contract['names'])
            or any(type(n) is not str or not reader.COMPONENT.fullmatch(n) or n in {'request.json','receipt.json'} for n in contract['names'])
            or any(type(contract[k]) is not str or not HEX.fullmatch(contract[k]) for k in ('body_sha256','support_digest'))):
        raise ValueError('read_contract_invalid')
    root=Path(home if home is not None else pwd.getpwuid(os.geteuid()).pw_dir)
    rid=request['run_id']; held=[]
    def read(chain,name,limit):
        chain.verify()
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        held.append((chain,name,fd,None))
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                or before.st_nlink!=1 or before.st_mode&0o022 or not 0<before.st_size<=limit):
            raise ValueError('original_file_owner_mode_type_or_size')
        data=b''
        while len(data)<=limit:
            part=os.read(fd,min(65536,limit+1-len(data)))
            if not part:break
            data+=part
        ident=reader.identity(before)
        held[-1]=(chain,name,fd,ident)
        if len(data)!=before.st_size:raise ValueError('original_file_changed')
        return {'bytes':len(data),'sha256':sha(data),'data_base64':base64.b64encode(data).decode()}
    def verify():
        for chain,name,fd,ident in held:
            chain.verify()
            if ident is None or ident!=reader.identity(os.fstat(fd)) or ident!=reader.identity(os.stat(name,dir_fd=chain.fd,follow_symlinks=False)):
                raise ValueError('original_file_changed')
    result={'schema':SCHEMA,'request_sha256':sha(canonical(request)),'state':'PENDING','files':{},'artifacts':[]}
    packet_dir = None
    try:
        if plain:
            packet_dir = DirectoryChain(root/'lanes/tmp')
            packet = read(packet_dir, rid+'.txt', 2*1024*1024)
            if packet['sha256'] != contract['packet_sha256']:
                raise ValueError('read_contract_invalid')
            verify()
        with DirectoryChain(root/'lanes/ext') as ext:
            try: rc=read(ext,'lanes_'+rid+'.rc',32)
            except FileNotFoundError:
                ext.verify();return result
            rcraw=base64.b64decode(rc['data_base64'],validate=True)
            if not re.fullmatch(rb'(0|[1-9][0-9]{0,2})\n?',rcraw) or int(rcraw)>255:
                raise ValueError('original_rc_invalid')
            result['files']['rc']=rc
            if int(rcraw)!=0:
                verify();result['state']='NONZERO';return result
            with DirectoryChain(root/'lanes/ext/lanes') as lanes:
                result['files']['process']=read(lanes,rid+'.process.jsonl',65536)
                result['files']['stdout']=read(ext,'lanes_'+rid+'.stdout',MAX_STDOUT)
                scope={k:request[k] for k in ('root','parent','run_id')}
                directory='/tmp/fabric-'+sha(canonical(scope))[:40]
                remaining=reader.MAX_TOTAL
                for name in contract['names']:
                    item=reader.read_one(directory+'/'+name,remaining)
                    if item.get('status')!='RETRIEVED':raise ValueError('original_artifact_unavailable')
                    remaining-=item['bytes'];result['artifacts'].append(item)
                verify();result['state']='READ';return result
    finally:
        for _chain,_name,fd,_ident in reversed(held):os.close(fd)
        if packet_dir is not None:packet_dir.close()


def remote_envelope(request):
    try:
        return remote_read(request)
    except (OSError, ValueError, TypeError, KeyError) as error:
        reason = str(error) if isinstance(error, ValueError) else 'filesystem_refused'
        allowed = {'read_request_invalid','read_contract_invalid','directory_owner_or_mode',
            'directory_chain_changed','original_file_owner_mode_type_or_size',
            'original_file_changed','original_rc_invalid','original_artifact_unavailable'}
        return {'schema':SCHEMA,'request_sha256':sha(canonical(request)),
            'state':'UNAVAILABLE','files':{},'artifacts':[],
            'reason':reason if reason in allowed else 'filesystem_refused'}


def code_for_request(request):
    # Fixed reviewed code, not caller-selected commands/paths/imports. The same
    # incumbent bounded SSH reader transports it; no remote write or probe.
    source=delivery.local_file(HERE/'artifact_reader.py',65536).decode()
    code='import base64, hashlib, json, os, pwd, re, stat, sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
    code+="_reader_ns={'__name__':'fixed_original_artifact_reader'}\nexec("+repr(source)+",_reader_ns)\nreader=SimpleNamespace(**_reader_ns)\n"
    code+='PLAIN_SCHEMA='+repr(PLAIN_SCHEMA)+'\nPLAIN_SCOPES='+repr(PLAIN_SCOPES)+'\n'
    code+='SCHEMA='+repr(SCHEMA)+'\nMAX_STDOUT='+str(MAX_STDOUT)+'\nIDENT=re.compile('+repr(IDENT.pattern)+')\nHEX=re.compile('+repr(HEX.pattern)+')\n'
    from remote_sub_exec import validate_completion_binding
    code+=inspect.getsource(validate_completion_binding)+'\n'+inspect.getsource(prospective_remote_read)+'\n'
    code+=inspect.getsource(delivery.DirectoryChain)+'\n'+inspect.getsource(canonical)+'\n'+inspect.getsource(sha)+'\n'+inspect.getsource(remote_read)+'\n'+inspect.getsource(remote_envelope)
    code+="\ntry:\n raw=sys.stdin.buffer.read(65537)\n if len(raw)>65536:raise ValueError('request_limit')\n request=reader.strict_json(raw)\n result=remote_envelope(request)\n sys.stdout.buffer.write(canonical(result))\nexcept (OSError,ValueError,TypeError,KeyError):\n raise SystemExit(76)\n"
    return code


def validate_response(raw,request,mode,*,original_validator=None):
    if len(raw)>MAX_RESPONSE:raise ValueError('collection_response_limit')
    row=reader.strict_json(raw)
    reject_failure_envelope(row, request, SCHEMA)
    if (type(row) is not dict or set(row)!={'schema','request_sha256','state','files','artifacts'}
            or row['schema']!=SCHEMA or row['request_sha256']!=sha(canonical(request))
            or type(row['files']) is not dict or type(row['artifacts']) is not list):
        raise ValueError('collection_response_invalid')
    if row['state']=='PENDING' and row['files']=={} and row['artifacts']==[]:
        return None
    if row['state']!='READ' or set(row['files'])!={'rc','process','stdout'}:
        raise ValueError('original_terminal_delivery_unqualified')
    blobs={}
    for name,limit in [('rc',32),('process',65536),('stdout',MAX_STDOUT)]:
        item=row['files'][name]
        if type(item) is not dict or set(item)!={'bytes','sha256','data_base64'}:
            raise ValueError('collection_file_invalid')
        data=base64.b64decode(item['data_base64'],validate=True)
        if type(item['bytes']) is not int or not 0<len(data)<=limit or len(data)!=item['bytes'] or sha(data)!=item['sha256']:
            raise ValueError('collection_file_integrity')
        blobs[name]=data
    if blobs['rc'] not in (b'0',b'0\n'):raise ValueError('collection_rc_mismatch')
    if request['contract'].get('schema') == 'mastermind.prospective_completion.v1':
        if row['artifacts']:raise ValueError('completion_artifact_conflict')
        return validate_prospective_process(blobs,request)
    if request['contract'].get('schema') == PLAIN_SCHEMA:
        if row['artifacts'] or mode != 'minimax':raise ValueError('plain_artifact_conflict')
        delivery.validate_capsule_process(blobs['process'],blobs['stdout'],request['run_id'])
        process=reader.strict_json(blobs['process'])
        if process.get('stdout_sha256') != sha(blobs['stdout']) or 'artifact_production' in process:
            raise ValueError('plain_capture_digest_mismatch')
        return blobs,[],None
    manifest=delivery.validate_ordinary_producer(request,blobs['stdout'],blobs['process'],
        original_validator=original_validator)
    validator=original_validator if original_validator is not None else production
    process=reader.strict_json(blobs['process'])
    if (process['artifact_production']['contract']!=request['contract']
            or process['artifact_production']['mode']!=mode):raise ValueError('original_completion_scope_mismatch')
    artrequest={'schema':reader.SCHEMA,**{k:request[k] for k in ('root','parent','run_id','host')},
                'stdout_sha256':sha(blobs['stdout']),'paths':validator.paths(request['contract'])}
    artresponse={'schema':reader.SCHEMA,'request_sha256':sha(canonical(artrequest)),'files':row['artifacts']}
    artifacts=delivery.validate_response(canonical(artresponse),artrequest)
    if len(artifacts)!=len(manifest['files']):raise ValueError('original_artifact_count')
    for (meta,data), advertised in zip(artifacts,manifest['files']):
        if data is None or any(meta[k]!=advertised[k] for k in ('path','bytes','sha256')):
            raise ValueError('original_artifact_manifest_mismatch')
    return blobs,artifacts,manifest


def collect(path,*,run_id,root,parent,destination):
    value,binding_raw,source,contract,alias,registry,original_validator=load_binding(path,run_id=run_id,root=root,parent=parent)
    if value['mode']=='minimax' and str(destination)!=PLAIN_SCOPES[run_id]['destination']:
        raise ValueError('plain_original_destination_changed')
    request={'schema':SCHEMA,**{k:value[k] for k in ('run_id','root','parent','host')},'contract':contract}
    # Reserve before transport. Existing path refuses, so a crashed publication
    # cannot silently repeat the remote observation using that destination.
    with delivery.reserve_destination(destination) as chain:
        delivery.write_exclusive(chain.fd,'read-request.json',canonical(request))
        try:
            response=delivery.transport(alias,request)
        except (OSError,ValueError) as error:
            allowed={'transport_timeout','transport_output_limit','transport_unavailable'}
            reason=str(error) if str(error) in allowed else 'transport_refused'
            delivery.write_exclusive(chain.fd,'transport-failure.json',canonical(
                {'state':'UNAVAILABLE','reason':reason,'retry_authorized':False}))
            raise
        if len(response)>MAX_RESPONSE:raise ValueError('collection_response_limit')
        # Retain the exact untrusted response even when qualification refuses.
        # These new evidence files are never copied over an original run file.
        for index,offset in enumerate(range(0,len(response),reader.MAX_FILE)):
            delivery.write_exclusive(chain.fd,f'read-response.{index:03d}',response[offset:offset+reader.MAX_FILE])
        verified=validate_response(response,request,value['mode'],original_validator=original_validator)
        def verify_source():
            current=load_binding(path,run_id=run_id,root=root,parent=parent)
            if current[1:4]!=(binding_raw,source,contract) or current[5]!=registry:
                raise ValueError('original_source_changed_during_collection')
        verify_source()
        receipt={'schema':RECEIPT_SCHEMA,**{k:value[k] for k in ('run_id','root','parent','host','mode')},
            'binding_sha256':sha(binding_raw),'request_sha256':sha(canonical(request)),
            'response_sha256':sha(response),'state':'PENDING' if verified is None else 'COMPLETE',
            'delivery_verified':verified is not None,'worker_terminal_proof':verified is not None,
            'lease_settlement':'UNKNOWN','controller_state':'UNKNOWN','acceptance':'NOT_RECORDED',
            'original_operation_mutated':False,'files':[],'stdout_chunks':[], 'artifacts':[]}
        if value['mode']=='minimax':
            receipt['plain_provenance']={
                'scope':'retained_packet_and_process_capture_at_collection',
                'producer_root_authenticated':False,
                'producer_packet_consumption_attested':False,
                'served_model_and_historical_physical_host_authenticated':False}
        def save(name,data):
            delivery.write_exclusive(chain.fd,name,data)
            receipt['files'].append({'local_name':name,'bytes':len(data),'sha256':sha(data)})
        save('binding.json',binding_raw)
        if verified is not None:
            blobs,artifacts,manifest=verified
            for index,offset in enumerate(range(0,len(blobs['stdout']),reader.MAX_FILE)):
                name=f'stdout.{index:03d}';save(name,blobs['stdout'][offset:offset+reader.MAX_FILE]);receipt['stdout_chunks'].append(name)
            receipt['stdout_sha256']=sha(blobs['stdout']);receipt['stdout_bytes']=len(blobs['stdout'])
            save('process.json',blobs['process']);save('returncode.txt',blobs['rc'])
            for index,(meta,data) in enumerate(artifacts):
                name=f'artifact.{index:02d}';save(name,data)
                receipt['artifacts'].append({**meta,'local_name':name})
            receipt['artifact_manifest']=manifest
        delivery.publish_receipt(chain,receipt,{'paths':[]},verify_source=verify_source)
        # publish_receipt invalidates its own created inode on a failed guard.
        if receipt['state']=='UNAVAILABLE':raise ValueError('collection_publication_unconfirmed')
        return receipt


def read_collection(path,*,expected_sha256,run_id,root,parent):
    plain = PLAIN_SCOPES.get(run_id)
    if plain is not None and (str(path) != str(Path(plain['destination'])/'receipt.json')
            or root != plain['root'] or parent != plain['parent']):
        raise ValueError('plain_collection_scope_mismatch')
    raw=delivery.local_file(Path(path),65536)
    if sha(raw)!=expected_sha256:raise ValueError('collection_receipt_changed')
    receipt=reader.strict_json(raw)
    if (receipt.get('schema')!=RECEIPT_SCHEMA or receipt.get('state')!='COMPLETE'
            or receipt.get('delivery_verified') is not True or receipt.get('worker_terminal_proof') is not True
            or any(receipt.get(k)!=v for k,v in {'root':root,'parent':parent,'run_id':run_id}.items())
            or receipt.get('original_operation_mutated') is not False):
        raise ValueError('collection_not_verified')
    if receipt.get('completion_contract') == 'mastermind.prospective_completion.v1':
        completion_caller(root,parent)
        with CompletionDirectory(completion_path(run_id)) as context:
            context.claim()
            complete=reader.strict_json(context.read('collection-complete.json'))
            if complete != {'destination':str(Path(path).parent),'receipt_sha256':expected_sha256}:
                raise ValueError('completion_consumption_unconfirmed')
    else:require_caller(root)
    chunks=receipt['stdout_chunks']
    if (not isinstance(chunks,list) or not 1<=len(chunks)<=32
            or chunks!=[f'stdout.{i:03d}' for i in range(len(chunks))]):raise ValueError('collection_chunks_invalid')
    if plain is not None:
        files=receipt.get('files')
        names=['binding.json',*chunks,'process.json','returncode.txt']
        if (receipt.get('host')!=plain['host'] or receipt.get('mode')!='minimax'
                or receipt.get('artifacts')!=[] or receipt.get('artifact_manifest') is not None
                or type(files) is not list or len(files)!=len(names)
                or any(type(item) is not dict or set(item)!={'local_name','bytes','sha256'}
                    or item['local_name']!=name or type(item['bytes']) is not int
                    or not 0<item['bytes']<=reader.MAX_FILE or type(item['sha256']) is not str
                    or not HEX.fullmatch(item['sha256']) for item,name in zip(files,names))):
            raise ValueError('plain_collection_files_or_scope_invalid')
    with delivery.DirectoryChain(Path(path).parent) as chain:
        delivery.verify_delivered(chain,receipt['files'])
        if plain is not None:
            binding_raw=delivery.read_local_at(chain,'binding.json',65536)
            binding=reader.strict_json(binding_raw)
            if (sha(binding_raw)!=receipt.get('binding_sha256') or type(binding) is not dict
                    or any(binding.get(k)!=v for k,v in {
                        'schema':BINDING_SCHEMA,'run_id':run_id,'root':root,'parent':parent,
                        'host':plain['host'],'mode':'minimax','requested_model':'MiniMax-M3',
                        'cwd':'~','artifact_names':[]}.items())
                    or type(binding.get('sources')) is not dict
                    or binding['sources'].get('packet')!={'path':plain['packet_path'],'sha256':plain['packet_sha256']}):
                raise ValueError('plain_collection_binding_invalid')
        stdout=b''.join(delivery.read_local_at(chain,name,reader.MAX_FILE) for name in chunks)
        if len(stdout)!=receipt['stdout_bytes'] or sha(stdout)!=receipt['stdout_sha256']:
            raise ValueError('collection_stdout_integrity')
        chain.verify();return stdout


class CompletionDirectory:
    """Private original-run evidence and its existing controller custody fence."""
    def __init__(self, path):
        self.path = Path(path)
        self.chain = delivery.DirectoryChain(self.path)
        self.fd = os.dup(self.chain.fd)
        self.lock = None
        self.identity = (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino)
        try: self.verify()
        except BaseException: self.close(); raise

    def verify(self):
        self.chain.verify()
        a, b = os.fstat(self.fd), self.path.lstat()
        if (not stat.S_ISDIR(b.st_mode) or a.st_uid != os.getuid() or stat.S_IMODE(a.st_mode) != 0o700
                or self.identity != (a.st_dev, a.st_ino) or self.identity != (b.st_dev, b.st_ino)):
            raise ValueError('completion_directory_changed')
        if self.lock is not None:
            a, b = os.fstat(self.lock), os.stat('custody.lock', dir_fd=self.fd, follow_symlinks=False)
            if ((a.st_dev,a.st_ino) != (b.st_dev,b.st_ino) or not stat.S_ISREG(a.st_mode)
                    or a.st_uid != os.getuid() or a.st_nlink != 1 or stat.S_IMODE(a.st_mode) != 0o600):
                raise ValueError('completion_custody_changed')

    def claim(self, create=False):
        import fcntl
        self.lock = os.open('custody.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
            | (os.O_CREAT | os.O_EXCL if create else 0), 0o600, dir_fd=self.fd)
        self.verify()
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.verify()

    def read(self, name, limit=2*1024*1024):
        self.verify()
        info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('completion_evidence_file')
        return delivery.read_local_at(self, name, limit)

    def write(self, name, data):
        self.verify();delivery.write_exclusive(self.fd,name,data);self.verify()
        if self.read(name) != data:raise ValueError('completion_publication_unconfirmed')

    def close(self):
        for name in ('lock','fd'):
            fd=getattr(self,name,None)
            if fd is not None:os.close(fd);setattr(self,name,None)
        if getattr(self,'chain',None) is not None:self.chain.close();self.chain=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def completion_path(run):
    if not IDENT.fullmatch(run):raise ValueError('completion_run_invalid')
    return HERE/'state/remote_sub'/(run+'.completion')


def completion_caller(root,parent):
    # Explicit native-parent correlation is necessary, never a replacement for
    # the original resource grant. No environment substitution for old runs.
    if (type(root) is not str or type(parent) is not str or not IDENT.fullmatch(root) or not IDENT.fullmatch(parent)
            or os.environ.get('CODEX_THREAD_ID') != parent
            or os.environ.get('POOL_ORCHESTRATOR_ID',root) != root):
        raise ValueError('completion_original_parent_required')


def completion_sources():
    return {name:sha(delivery.local_file(HERE/name,2*1024*1024)) for name in
        ('fabric_task.py','remote_sub.sh','original_delivery_collector.py','artifact_delivery.py','artifact_reader.py','remote_sub_exec.py')}


def begin_completion(run,root,parent,route,packet,cwd,support_digest):
    import time,uuid
    completion_caller(root,parent)
    if not isinstance(packet,bytes) or not 0<len(packet)<=2*1024*1024:raise ValueError('completion_packet_bound')
    if cwd != '~' or route['MODE'] not in ('glm','qwen','minimax') or route['HOST']=='m2':
        raise ValueError('completion_route_unsupported')
    for old in (HERE/'state/remote_sub'/(run+'.log'), HERE/'lanes'/(run+'.remote.stdout')):
        if os.path.lexists(old):raise ValueError('completion_existing_run_not_adopted')
    path=completion_path(run);os.mkdir(path,0o700)
    parent_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(parent_fd)
    finally:os.close(parent_fd)
    store=CompletionDirectory(path)
    try:
        store.claim(create=True)
        lock=os.fstat(store.lock)
        origin={'schema':'mastermind.completion_origin.v1','run_id':run,'root':root,'parent':parent,
            'host':route['HOST'],'mode':route['MODE'],'model':route['MODEL'],'cwd':cwd,
            'packet_sha256':sha(packet),'support_digest':support_digest,
            'hosts_sha256':sha(delivery.local_file(HERE/'hosts.json')), 'local_sources':completion_sources(),
            'controller':{'pid':os.getpid(),'generation':uuid.uuid4().hex,'started_at':int(time.time()),
                'lock_device':lock.st_dev,'lock_inode':lock.st_ino}}
        store.write('packet.txt',packet)
        store.write('origin.json',canonical(origin))
        return store
    except BaseException:store.close();raise


def seal_completion(path,run,root,parent,host,mode,model,account,lease,support,max_secs,child_secs,ttl,controller_pid,custody_fd):
    import time
    from remote_sub_exec import validate_completion_binding
    if Path(path) != completion_path(run):raise ValueError('completion_context_path')
    with CompletionDirectory(path) as store:
        store.lock=os.dup(int(custody_fd))
        store.verify()
        import fcntl
        fcntl.flock(store.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        origin=reader.strict_json(store.read('origin.json'))
        completion_caller(root,parent)
        if origin['local_sources'] != completion_sources() or origin['hosts_sha256'] != sha(delivery.local_file(HERE/'hosts.json')):
            raise ValueError('completion_launch_source_changed')
        expected={'schema':'mastermind.completion_origin.v1','run_id':run,'root':root,'parent':parent,
            'host':host,'mode':mode,'model':model,'cwd':'~','support_digest':support}
        if any(origin.get(k)!=v for k,v in expected.items()) or str(origin['controller']['pid'])!=controller_pid:
            raise ValueError('completion_origin_changed')
        if sha(store.read('packet.txt'))!=origin['packet_sha256']:raise ValueError('completion_packet_changed')
        lock=os.stat('custody.lock',dir_fd=store.fd,follow_symlinks=False)
        if (lock.st_dev,lock.st_ino)!=(origin['controller']['lock_device'],origin['controller']['lock_inode']):
            raise ValueError('completion_controller_changed')
        # The original adapter holds this inode across the whole controller.
        deadline=origin['controller']['started_at']+int(max_secs)
        binding=dict(origin,schema='mastermind.prospective_completion.v1',lease_id=lease,account=account,
            controller_deadline=deadline,worker_deadline=min(deadline,int(time.time())+int(child_secs)),
            lease_ttl_requested=int(ttl))
        validate_completion_binding(binding)
        if binding['worker_deadline']<=time.time():raise ValueError('completion_deadline_expired')
        support_raw=delivery.local_file(HERE/'state/remote_sub'/(run+'.support.json'))
        if sha(canonical({'schema':'remote-support-code.v1','files':reader.strict_json(support_raw)}))!=support:
            raise ValueError('completion_support_changed')
        store.write('support.json',support_raw)
        store.write('launch.json',canonical(binding))
        return path+'/launch.json'


def prospective_remote_read(request):
    # Uses the SAME fixed artifact reader and its private /tmp/fabric-* rules.
    # No home-directory probe, chmod, transport alternative or legacy adoption.
    binding=validate_completion_binding(request.get('contract'))
    if (set(request)!={'schema','run_id','root','parent','host','contract'} or request['schema']!=SCHEMA
            or any(request[k]!=binding[k] for k in ('run_id','root','parent','host'))):
        raise ValueError('read_request_invalid')
    scope={k:binding[k] for k in ('root','parent','run_id')}
    directory='/tmp/fabric-'+sha(canonical(scope))[:40]
    def read(name):
        item=reader.read_one(directory+'/'+name,reader.MAX_FILE)
        if item.get('status')!='RETRIEVED':raise ValueError('original_artifact_unavailable')
        return {k:item[k] for k in ('bytes','sha256','data_base64')}
    original=read('binding.json')
    if base64.b64decode(original['data_base64'],validate=True)!=canonical(binding):
        raise ValueError('read_contract_invalid')
    first=read('terminal.json')
    result={'schema':SCHEMA,'request_sha256':sha(canonical(request)),'state':'READ',
        'files':{'rc':read('returncode.txt'),'process':read('process.json'),'stdout':read('stdout.txt')},'artifacts':[]}
    marker=reader.strict_json(base64.b64decode(first['data_base64'],validate=True))
    names={'rc':'returncode.txt','process':'process.json','stdout':'stdout.txt'}
    if (type(marker) is not dict or set(marker)!={'schema','binding_sha256','files'}
            or marker['schema']!='mastermind.prospective_terminal.v1'
            or marker['binding_sha256']!=sha(canonical(binding)) or set(marker['files'])!=set(names.values())):
        raise ValueError('read_contract_invalid')
    for short,name in names.items():
        if marker['files'][name]!={k:result['files'][short][k] for k in ('bytes','sha256')}:
            raise ValueError('original_file_changed')
    if read('terminal.json')!=first or read('binding.json')!=original:raise ValueError('original_file_changed')
    return result


def validate_prospective_process(blobs,request):
    from remote_sub_exec import validate_completion_binding
    from datetime import datetime
    b=validate_completion_binding(request['contract'])
    process=reader.strict_json(blobs['process'])
    delivery.validate_capsule_process(blobs['process'],blobs['stdout'],b['run_id'])
    evidence=process.get('prospective_completion')
    if evidence!={'binding':b,'stdout_sha256':sha(blobs['stdout']),'stdout_bytes':len(blobs['stdout'])}:
        raise ValueError('completion_producer_binding_mismatch')
    started=datetime.fromisoformat(process['started_at'].replace('Z','+00:00')).timestamp()
    ended=datetime.fromisoformat(process['ended_at'].replace('Z','+00:00')).timestamp()
    if not b['controller']['started_at']<=started<=ended<=b['controller_deadline']:
        raise ValueError('completion_process_deadline')
    return blobs,[],None


def collect_prospective(run,root,parent,destination):
    from remote_sub_exec import validate_completion_binding
    completion_caller(root,parent)
    with CompletionDirectory(completion_path(run)) as store:
        store.claim()  # Fails while original controller OR another collector owns it.
        origin_raw=store.read('origin.json');origin=reader.strict_json(origin_raw)
        raw=store.read('launch.json');binding=validate_completion_binding(reader.strict_json(raw))
        if any(binding[k]!=v for k,v in {'run_id':run,'root':root,'parent':parent}.items()):
            raise ValueError('completion_foreign_run')
        expected=dict(binding,schema='mastermind.completion_origin.v1')
        for k in ('lease_id','account','controller_deadline','worker_deadline','lease_ttl_requested'):expected.pop(k)
        if origin!=expected or sha(store.read('packet.txt'))!=binding['packet_sha256']:
            raise ValueError('completion_original_source_changed')
        c=binding['controller'];lock=os.fstat(store.lock)
        if (lock.st_dev,lock.st_ino)!=(c['lock_device'],c['lock_inode']):raise ValueError('completion_lock_replaced')
        support_raw=store.read('support.json')
        if sha(canonical({'schema':'remote-support-code.v1','files':reader.strict_json(support_raw)}))!=binding['support_digest']:
            raise ValueError('completion_support_changed')
        if completion_sources()!=binding['local_sources']:raise ValueError('completion_local_source_changed')
        registry_raw=delivery.local_file(HERE/'hosts.json')
        if sha(registry_raw)!=binding['hosts_sha256']:raise ValueError('completion_host_source_changed')
        host=reader.strict_json(registry_raw).get(binding['host'])
        if (not isinstance(host,dict) or binding['mode'] not in host.get('allowed_modes',[])
                or type(host.get('ssh_alias')) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',host['ssh_alias'])):
            raise ValueError('completion_host_changed')
        request={'schema':SCHEMA,**{k:binding[k] for k in ('root','parent','run_id','host')},'contract':binding}
        def unchanged():
            completion_caller(root,parent);store.verify()
            if store.read('launch.json')!=raw or store.read('origin.json')!=origin_raw or sha(store.read('packet.txt'))!=binding['packet_sha256']:
                raise ValueError('completion_source_changed')
            if delivery.local_file(HERE/'hosts.json')!=registry_raw or store.read('support.json')!=support_raw or completion_sources()!=binding['local_sources']:
                raise ValueError('completion_dependency_changed')
        # Irreversible evidence of this read attempt precedes any transport.
        # On lost response/publication it is NEVER cleared for another attempt.
        store.write('collection-intent.json',canonical({'request':request,'destination':str(destination)}))
        with delivery.reserve_destination(Path(destination)) as chain:
            unchanged();response=delivery.transport(host['ssh_alias'],request)
            delivery.write_exclusive(chain.fd,'untrusted-response.json',response)
            blobs,_,_=validate_response(response,request,binding['mode'])
            unchanged()
            receipt={'schema':RECEIPT_SCHEMA,'state':'COMPLETE','root':root,'parent':parent,'run_id':run,
                'host':binding['host'],'mode':binding['mode'],'binding_sha256':sha(raw),
                'delivery_verified':True,'worker_terminal_proof':True,'original_operation_mutated':False,
                'lease_settlement':'UNCHANGED_REQUIRES_EXISTING_OWNER','acceptance':'NOT_RECORDED','files':[],
                'completion_contract':'mastermind.prospective_completion.v1',
                'stdout_chunks':['stdout.000'],'stdout_bytes':len(blobs['stdout']),'stdout_sha256':sha(blobs['stdout']),
                'artifacts':[],'artifact_manifest':None}
            for name,data in [('binding.json',raw),('stdout.000',blobs['stdout']),('process.json',blobs['process']),('returncode.txt',blobs['rc'])]:
                delivery.write_exclusive(chain.fd,name,data)
                receipt['files'].append({'local_name':name,'bytes':len(data),'sha256':sha(data)})
            delivery.publish_receipt(chain,receipt,{'paths':[]},verify_source=unchanged)
            if receipt['state']!='COMPLETE':raise ValueError('completion_publication_unconfirmed')
            store.write('collection-complete.json',canonical({'destination':str(destination),'receipt_sha256':sha(delivery.read_local_at(chain,'receipt.json',65536))}))
            return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    for name in ('root','parent'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--prospective',action='store_true')
    parser.add_argument('--seal-completion',nargs=15)
    parser.add_argument('--binding');parser.add_argument('--destination')
    parser.add_argument('--collection');parser.add_argument('--receipt-sha256')
    args=parser.parse_args(argv)
    try:
        if args.seal_completion:
            if (args.seal_completion[1:4] != [args.run_id,args.root,args.parent]
                    or args.prospective or args.binding or args.destination or args.collection or args.receipt_sha256):
                raise ValueError('completion_seal_arguments')
            print(seal_completion(*args.seal_completion));return 0
        if args.prospective:
            if args.binding or args.collection or not args.destination:raise ValueError('completion_arguments')
            print(canonical(collect_prospective(args.run_id,args.root,args.parent,args.destination)).decode());return 0
        if args.collection:
            if args.binding or args.destination or not args.receipt_sha256:raise ValueError('collection_arguments')
            sys.stdout.buffer.write(read_collection(args.collection,expected_sha256=args.receipt_sha256,
                run_id=args.run_id,root=args.root,parent=args.parent));return 0
        if not args.binding or not args.destination or args.receipt_sha256:raise ValueError('collection_arguments')
        receipt=collect(args.binding,run_id=args.run_id,root=args.root,parent=args.parent,destination=args.destination)
        print(canonical(receipt).decode());return 0 if receipt['state']=='COMPLETE' else 76
    except OriginalDeliveryRefused as error:
        print(canonical({'state':'REFUSED','reason':error.reason,
            'failure_phase':'original_remote_read','retry_authorized':False,
            'worker_terminal_proof':False,'delivery_verified':False}).decode())
        return 75
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        print('{"state":"REFUSED","reason":"original_delivery_unconfirmed","retry_authorized":false}')
        return 75


if __name__=='__main__':raise SystemExit(main())
