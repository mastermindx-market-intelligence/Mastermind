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

DirectoryChain = delivery.DirectoryChain
HERE = Path(__file__).resolve().parent
SCHEMA = 'mastermind.original_delivery_read.v1'
PLAIN_SCHEMA = 'mastermind.original_plain_result_contract.v1'
PLAIN_SCOPES = {'fabric-manifest-framing-review-01a11e90-v1': {'root': '01a11e90-4b5d-7f53-b966-8aaaad38701f',
                                                'parent': '01a11e90-4b5d-7f53-b966-8aaaad38701f',
                                                'host': 'mb',
                                                'packet_path': '/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/fabric-start-publication-20261012-fb76f8a5c8c5e179/integrations/session_bridge/artifact_manifest_framing/REVIEW_PACKET.txt',
                                                'packet_sha256': 'e7fb39a83f6e7456fe976c83f88f95602e2164bb00acfdf36f7aaade7e272f88',
                                                'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114',
                                                'destination': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/fabric-manifest-framing-review-01a11e90-v1-collection-v1'},
 'mm-os-incident-custody-direct-review-20261013-01a104e6': {'root': '01a104e6-58f8-76d3-8d99-1302a1cca072',
                                                            'parent': '01a104e6-58f8-76d3-8d99-1302a1cca072',
                                                            'host': 'ubuntu1',
                                                            'packet_path': '/Volumes/Mastermind/evidence/mastermind-os-noir-product-convergence-20261003-astra-001/production-continuation-20261010/issuer-custody-repair-20261013/direct-preventive-review-packet.md',
                                                            'packet_sha256': 'dc3bfd8aaf0358c160c7290def2b3d3c6ef45893e1042620346e8ee7070d588c',
                                                            'support_digest': '4014714eb8865585f11b2a0120975479c10f0567cad968c5a57e5101f8c8f114',
                                                            'destination': '/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/original-parent-host-selection-20261013/mm-os-incident-custody-direct-review-20261013-01a104e6-collection-v1'},
 'rf-archive-order-review-01a1333c-v1': {'root': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                         'parent': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                         'host': 'mb',
                                         'mode': 'qwen',
                                         'requested_model': 'qwen3.8-max',
                                         'packet_path': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/runtime-release/physical-qualification/archive-order-repair-v1/ARCHIVE_ORDER_REVIEW_PACKET.txt',
                                         'packet_sha256': '30fb451ed25f680d0dddebfeca1a38abb1b923a031af564758f6b820a456a854',
                                         'support_digest': '8cf4ee40a6b81a2cae2b23e51affb55595292541b8f3e3fcf0627216b31d9ed5',
                                         'source_pins': {'log': 'e765bb98af7a421ddf4c170e03672eef4363ef5d3bc32ab721e634c6734cd33c',
                                                         'support': 'edc233071cb0d6a800dfba97e1a2a904a0a4ec54554ba473ac551611e8182fdd'},
                                         'destination': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/retained-returns/rf-archive-order-review-01a1333c-v1-collection-v1'},
 'rf-mountinfo-review-01a1333c-v1': {'root': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                     'parent': '01a1333c-a475-7052-95a8-72a88eb8c17b',
                                     'host': 'ubuntu1',
                                     'mode': 'qwen',
                                     'requested_model': 'qwen3.8-max',
                                     'packet_path': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/containment-acceptance/workloads/MOUNTINFO_INDEPENDENT_REVIEW_PACKET_V1.txt',
                                     'packet_sha256': 'd10873588448ba479ffca205e928239290f5d6e9348994d9d1acdd4897e63728',
                                     'support_digest': '69e494d29888c63cfee97ce19f7ed6afb7cf24a145ee9dc019e737e853f81a9b',
                                     'source_pins': {'log': 'a45d165e074694c10d59dbd4729759c607eb05d09d369e6a977d545c989f2193',
                                                     'support': 'ff2d51c0a2b95a96ef2543b8e1d53d88e7706c6398f1b1fcbc09b44270f310fe'},
                                     'destination': '/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c/retained-returns/rf-mountinfo-review-01a1333c-v1-collection-v1'}}
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
            or value['mode'] != plain.get('mode', 'minimax') or value['artifact_names'] != []
            or value['requested_model'] != plain.get('requested_model', 'MiniMax-M3')
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
        if (plain is not None and name in plain.get('source_pins', {})
                and item['sha256'] != plain['source_pins'][name]):
            raise ValueError('plain_original_source_pin_changed')
        if sha(data) != item['sha256']:
            raise ValueError('original_source_changed')
        source[name] = data
    manifest = reader.strict_json(source['support'])
    if (type(manifest) is not dict or not manifest
            or any(type(k) is not str or type(v) is not str or not HEX.fullmatch(v)
                   for k,v in manifest.items())):
        raise ValueError('original_support_mismatch')
    original_validator = None
    if plain is None or plain.get('mode') == 'qwen':
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
    if plain is not None and plain.get('mode', 'minimax') == 'minimax':
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
    remote_scopes = {key: {field: scope[field] for field in (
        'root', 'parent', 'host', 'packet_sha256', 'support_digest')}
        for key, scope in PLAIN_SCOPES.items()}
    code+='PLAIN_SCHEMA='+repr(PLAIN_SCHEMA)+'\nPLAIN_SCOPES='+repr(remote_scopes)+'\n'
    code+='SCHEMA='+repr(SCHEMA)+'\nMAX_STDOUT='+str(MAX_STDOUT)+'\nIDENT=re.compile('+repr(IDENT.pattern)+')\nHEX=re.compile('+repr(HEX.pattern)+')\n'
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
    if request['contract'].get('schema') == PLAIN_SCHEMA:
        plain = PLAIN_SCOPES.get(request['run_id'])
        if (plain is None or row['artifacts']
                or mode != plain.get('mode', 'minimax')):
            raise ValueError('plain_artifact_conflict')
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


class LocalBindingRefused(ValueError):
    """A local-only validation failure before destination reservation/transport."""


def collect(path,*,run_id,root,parent,destination):
    try:
        value,binding_raw,source,contract,alias,registry,original_validator=load_binding(path,run_id=run_id,root=root,parent=parent)
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
        raise LocalBindingRefused(str(error)) from error
    if run_id in PLAIN_SCOPES and str(destination)!=PLAIN_SCOPES[run_id]['destination']:
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
        if run_id in PLAIN_SCOPES:
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
    require_caller(root)
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
    chunks=receipt['stdout_chunks']
    if (not isinstance(chunks,list) or not 1<=len(chunks)<=32
            or chunks!=[f'stdout.{i:03d}' for i in range(len(chunks))]):raise ValueError('collection_chunks_invalid')
    if plain is not None:
        files=receipt.get('files')
        names=['binding.json',*chunks,'process.json','returncode.txt']
        if (receipt.get('host')!=plain['host'] or receipt.get('mode')!=plain.get('mode', 'minimax')
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
                        'host':plain['host'],'mode':plain.get('mode', 'minimax'),
                        'requested_model':plain.get('requested_model', 'MiniMax-M3'),
                        'cwd':'~','artifact_names':[]}.items())
                    or type(binding.get('sources')) is not dict
                    or binding['sources'].get('packet')!={'path':plain['packet_path'],'sha256':plain['packet_sha256']}):
                raise ValueError('plain_collection_binding_invalid')
            for name, digest in plain.get('source_pins', {}).items():
                filename = run_id + ('.log' if name == 'log' else '.support.json')
                if binding['sources'].get(name) != {
                        'path': str(HERE/'state/remote_sub'/filename), 'sha256': digest}:
                    raise ValueError('plain_collection_source_pin_changed')
        stdout=b''.join(delivery.read_local_at(chain,name,reader.MAX_FILE) for name in chunks)
        if len(stdout)!=receipt['stdout_bytes'] or sha(stdout)!=receipt['stdout_sha256']:
            raise ValueError('collection_stdout_integrity')
        chain.verify();return stdout


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    for name in ('root','parent'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--binding');parser.add_argument('--destination')
    parser.add_argument('--collection');parser.add_argument('--receipt-sha256')
    args=parser.parse_args(argv)
    try:
        if args.collection:
            if args.binding or args.destination or not args.receipt_sha256:raise ValueError('collection_arguments')
            sys.stdout.buffer.write(read_collection(args.collection,expected_sha256=args.receipt_sha256,
                run_id=args.run_id,root=args.root,parent=args.parent));return 0
        if not args.binding or not args.destination or args.receipt_sha256:raise ValueError('collection_arguments')
        receipt=collect(args.binding,run_id=args.run_id,root=args.root,parent=args.parent,destination=args.destination)
        print(canonical(receipt).decode());return 0 if receipt['state']=='COMPLETE' else 76
    except LocalBindingRefused as error:
        allowed={'directory_owner_or_mode','directory_chain_changed','directory_path_invalid',
                 'original_native_root_required'}
        reason=str(error) if str(error) in allowed else 'original_binding_unconfirmed'
        print(canonical({'state':'REFUSED','reason':reason,
            'failure_phase':'original_local_binding','remote_read_started':False,
            'destination_reserved':False,'retry_authorized':False,
            'worker_terminal_proof':False,'delivery_verified':False}).decode())
        return 75
    except OriginalDeliveryRefused as error:
        print(canonical({'state':'REFUSED','reason':error.reason,
            'failure_phase':'original_remote_read','retry_authorized':False,
            'worker_terminal_proof':False,'delivery_verified':False}).decode())
        return 75
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        print('{"state":"REFUSED","reason":"original_delivery_unconfirmed","retry_authorized":false}')
        return 75


if __name__=='__main__':raise SystemExit(main())
