"""Finite original operator stdout delivery, through the incumbent read owner.

No bearer renewal, worker replay, lease settlement or acceptance. The exact
original root commissioned this read; constants/env labels correlate that
commission and are not authentication. The native assigning parent is retained
from its separately verified commission, not invented from the operator grant.
"""
from __future__ import annotations
import base64
import hashlib
import inspect
import os
from pathlib import Path
import pwd
import re
import stat
import sqlite3

import artifact_delivery as delivery
import artifact_reader as reader
import original_delivery_collector as collector
from fabric_operator_owner import OperatorOwner

DirectoryChain = delivery.DirectoryChain
SCHEMA = 'mastermind.original_operator_stdout_read.v1'
RECEIPT_SCHEMA = 'mastermind.original_delivery_receipt.v1'
MAX_STDOUT = 8 * 1024 * 1024
MAX_RESPONSE = 14 * 1024 * 1024
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
HEX = re.compile(r'[a-f0-9]{64}\Z')
RUN_ID = 'rf-codegen-contracts-impl-01a1333c-v1'
ROOT = '01a1333c-a475-7052-95a8-72a88eb8c17b'
PARENT = '01a1333e-742d-7c80-8dbb-db42109f06ce'
HOST = 'ubuntu2'
EVIDENCE = Path('/Volumes/Mastermind/evidence/research-factory-codegen-20261012-01a1333c')
DESTINATION = EVIDENCE / 'original-contracts-collection-v1'
REQUEST = dict(schema=SCHEMA, run_id=RUN_ID, root=ROOT, parent=PARENT, host=HOST)
READER_SHA256 = 'e2b08b7967df0e4193ba668cf6f72225429138a9361322c42db6ec84150e3469'
SOURCES = {
    'packet': (RUN_ID + '.operator-packet.wy7OGS', 'd6038bc10d8f27ee50ad52b19f575719883bf8dd70ced1b16e608adb7d591132'),
    'log': (RUN_ID + '.log', '2785ae114deabfe8b23069acafc9563dfa230fed576229cadc875f75e805e9b8'),
    'support': (RUN_ID + '.support.json', '2d61ce4101de4a97d587ac97f09b32af48a8650e54d73aa0118f76dbb0e0cc84'),
}
COMMISSION = {
    'SAME_RUN_RECOVERY_REQUEST.md': '651a4fda6e0dbf98795a4435fd06873be4d0c3970d16828a5af36bace03f2b16',
    'contracts-science/native-identity.json': 'eb055f35bbfcaa234f29f58389fe5e261c954454b8ced807f9300fe1a8bf82b7',
}
EXPECTED_BINDING = dict(schema='mastermind.original_operator_launch_binding.v1',
    operator_run=RUN_ID, root=ROOT, lease_id='22997f469bee', pool='glm', model='glm-5.3',
    account='chairman-max-2', host=HOST,
    support_sha256='febbe42fe76bf9ac39db7f73f323473c3dd10ffd721e63c4f1e440c54af9b73f',
    packet_sha256=SOURCES['packet'][1], parent_binding='NOT_RECORDED_IN_OPERATOR_GRANT',
    current_authority=False, lease_settlement='UNKNOWN', children_settlement='UNKNOWN')


def canonical(value):
    return reader.canonical(value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def qualify(run_id):
    if run_id != RUN_ID:
        raise ValueError('original_operator_scope')
    delivery.assert_capsule_family(run_id)
    source = {}
    for key, (name, expected) in SOURCES.items():
        data = delivery.local_file(delivery.HERE / 'state/remote_sub' / name, 65536)
        if sha(data) != expected:
            raise ValueError('original_operator_source_changed')
        source[key] = data
    for name, expected in COMMISSION.items():
        if sha(delivery.local_file(EVIDENCE / name, 65536)) != expected:
            raise ValueError('original_operator_commission_changed')
    identity = reader.strict_json(delivery.local_file(EVIDENCE / 'contracts-science/native-identity.json', 65536))
    if (identity.get('original_root') != ROOT or identity.get('parent_thread_id') != ROOT
            or identity.get('immediate_parent') != PARENT):
        raise ValueError('original_operator_ancestry_mismatch')
    # This metadata is an independently checked commission, not an auth token.
    packet = source['packet'].decode('utf-8')
    if ROOT not in packet or PARENT not in packet:
        raise ValueError('original_operator_packet_scope')
    support = reader.strict_json(source['support'])
    if (type(support) is not dict or not support or any(type(k) is not str
            or type(v) is not str or not HEX.fullmatch(v) for k,v in support.items())
            or sha(canonical(dict(schema='remote-support-code.v1',files=support))) != EXPECTED_BINDING['support_sha256']):
        raise ValueError('original_operator_support_mismatch')
    binding = OperatorOwner(here=delivery.HERE).original_delivery_binding(run_id, root=ROOT)
    if binding != EXPECTED_BINDING:
        raise ValueError('original_operator_binding_changed')
    prefix = (r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id=' + re.escape(run_id)
              + ' host=' + HOST + r'\] (.*)')
    events = []
    for line in source['log'].decode('utf-8').splitlines():
        match = re.fullmatch(prefix, line)
        if match: events.append(match[1])
        elif '[remote_sub id=' in line: raise ValueError('original_operator_log_scope')
    for key, expected in {
        'LAUNCH_ATTEMPT ': ['LAUNCH_ATTEMPT attempt=1'],
        'LAUNCH ': [f'LAUNCH stdout=lanes_{run_id}.stdout rc_file=ext/lanes_{run_id}.rc cwd=~'],
        'LEASE_OK ': ['LEASE_OK pool=glm-frontier'],
    }.items():
        if [event for event in events if event.startswith(key)] != expected:
            raise ValueError('original_operator_launch_mismatch')
    supports = [event for event in events if event.startswith('SUPPORT_VERSION_READY ')]
    if (len(supports) != 1 or not re.fullmatch('SUPPORT_VERSION_READY digest='
            + EXPECTED_BINDING['support_sha256'] + r' policy=[a-f0-9]{64}', supports[0])
            or any(event.startswith(('DONE ', 'REMOTE_DONE ')) or 'EFFECT_UNKNOWN' in event for event in events)):
        raise ValueError('original_operator_original_state_changed')
    registry = delivery.local_file(delivery.HERE / 'hosts.json')
    host = reader.strict_json(registry).get(HOST)
    if (type(host) is not dict or 'glm' not in host.get('allowed_modes', [])
            or type(host.get('ssh_alias')) is not str
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', host['ssh_alias'])):
        raise ValueError('original_operator_receiver_unqualified')
    if sha(delivery.local_file(delivery.HERE / 'artifact_reader.py', 65536)) != READER_SHA256:
        raise ValueError('original_operator_reader_changed')
    return dict(binding=binding, source_hashes={k:v[1] for k,v in SOURCES.items()},
        commission_hashes=dict(COMMISSION), reader_sha256=READER_SHA256,
        registry_sha256=sha(registry), ssh_alias=host['ssh_alias'])


def remote_read(request, *, home=None):
    """Fixed read-only paths. home is an inert-test seam, never in the request."""
    if (type(request) is not dict or set(request) != {'schema','run_id','root','parent','host'}
            or request != REQUEST
            or any(type(request[k]) is not str or not IDENT.fullmatch(request[k])
                   for k in ('run_id','root','parent','host'))):
        raise ValueError('read_request_invalid')
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
    try:
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
                verify();result['state']='READ';return result
    finally:
        for _chain,_name,fd,_ident in reversed(held):os.close(fd)


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
    if request != REQUEST: raise ValueError('original_operator_scope')
    source=delivery.local_file(delivery.HERE/'artifact_reader.py',65536).decode()
    code='import base64, hashlib, json, os, pwd, re, stat, sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n'
    code+="_reader_ns={'__name__':'fixed_original_artifact_reader'}\nexec("+repr(source)+",_reader_ns)\nreader=SimpleNamespace(**_reader_ns)\n"
    code+='REQUEST='+repr(REQUEST)+'\n'
    code+='SCHEMA='+repr(SCHEMA)+'\nMAX_STDOUT='+str(MAX_STDOUT)+'\nIDENT=re.compile('+repr(IDENT.pattern)+')\nHEX=re.compile('+repr(HEX.pattern)+')\n'
    code+=inspect.getsource(delivery.DirectoryChain)+'\n'+inspect.getsource(canonical)+'\n'+inspect.getsource(sha)+'\n'+inspect.getsource(remote_read)+'\n'+inspect.getsource(remote_envelope)
    code+="\ntry:\n raw=sys.stdin.buffer.read(65537)\n if len(raw)>65536:raise ValueError('request_limit')\n request=reader.strict_json(raw)\n result=remote_envelope(request)\n sys.stdout.buffer.write(canonical(result))\nexcept (OSError,ValueError,TypeError,KeyError):\n raise SystemExit(76)\n"
    return code


def validate_response(raw):
    if len(raw) > MAX_RESPONSE:
        raise ValueError('operator_response_limit')
    row = reader.strict_json(raw)
    collector.reject_failure_envelope(row, REQUEST, SCHEMA)
    if (type(row) is not dict or set(row) != {'schema','request_sha256','state','files','artifacts'}
            or row['schema'] != SCHEMA or row['request_sha256'] != sha(canonical(REQUEST))
            or type(row['files']) is not dict or row['artifacts'] != []):
        raise ValueError('operator_response_invalid')
    if row['state'] == 'PENDING' and row['files'] == {}:
        return None
    if row['state'] != 'READ' or set(row['files']) != {'rc','process','stdout'}:
        raise ValueError('operator_terminal_delivery_unqualified')
    blobs = {}
    for name, limit in [('rc',32),('process',65536),('stdout',MAX_STDOUT)]:
        item = row['files'][name]
        if type(item) is not dict or set(item) != {'bytes','sha256','data_base64'}:
            raise ValueError('operator_file_invalid')
        data = base64.b64decode(item['data_base64'], validate=True)
        if (type(item['bytes']) is not int or not 0 < len(data) <= limit
                or len(data) != item['bytes'] or sha(data) != item['sha256']):
            raise ValueError('operator_file_integrity')
        blobs[name] = data
    if blobs['rc'] not in (b'0', b'0\n'):
        raise ValueError('operator_rc_mismatch')
    delivery.validate_capsule_process(blobs['process'], blobs['stdout'], RUN_ID)
    process = reader.strict_json(blobs['process'])
    if process.get('stdout_sha256') != sha(blobs['stdout']):
        raise ValueError('operator_capture_digest_mismatch')
    return blobs


def collect(run_id, destination):
    # Caller correlation does not replace the original owner's actual authority.
    if (os.environ.get('CODEX_THREAD_ID') != ROOT
            or os.environ.get('POOL_ORCHESTRATOR_ID') not in (None, '', ROOT)):
        raise ValueError('original_operator_root_required')
    if str(destination) != str(DESTINATION):
        raise ValueError('original_operator_destination_not_admitted')
    evidence = qualify(run_id)

    def unchanged():
        if qualify(run_id) != evidence:
            raise ValueError('original_operator_evidence_changed')

    # Single fixed fresh destination preserves an attempted read even if the
    # process exits before a receipt. No new pathname can retry that effect.
    with delivery.reserve_destination(destination) as chain:
        delivery.write_exclusive(chain.fd, 'read-request.json', canonical(REQUEST))
        receipt = dict(schema=RECEIPT_SCHEMA, profile='stdout_only_operator',
            run_id=RUN_ID, root=ROOT, parent=PARENT, host=HOST, mode='glm',
            evidence=evidence, request_sha256=sha(canonical(REQUEST)),
            state='UNAVAILABLE', delivery_verified=False, worker_terminal_proof=False,
            lease_settlement='UNKNOWN', children_settlement='UNKNOWN', controller_state='UNKNOWN',
            acceptance='NOT_RECORDED', original_operation_mutated=False,
            read_transport_state='MAY_START_AFTER_THIS_INTENT', files=[], stdout_chunks=[], artifacts=[])

        def save(name, data):
            delivery.write_exclusive(chain.fd, name, data)
            receipt['files'].append(dict(local_name=name, bytes=len(data), sha256=sha(data)))

        try:
            unchanged(); chain.verify()
            receipt['read_transport_state'] = 'ATTEMPTED_UNCONFIRMED'
            raw = delivery.transport(evidence['ssh_alias'], REQUEST)
            receipt['read_transport_state'] = 'RESPONSE_RECEIVED'
            if len(raw) > MAX_RESPONSE:
                raise ValueError('operator_response_limit')
            # Preserve the exact untrusted response before interpreting any state.
            for index, offset in enumerate(range(0, len(raw), reader.MAX_FILE)):
                save(f'read-response.{index:03d}', raw[offset:offset+reader.MAX_FILE])
            receipt['response_sha256'] = sha(raw)
            blobs = validate_response(raw)
            unchanged(); chain.verify()
            if blobs is None:
                receipt['state'] = 'PENDING'
            else:
                for index, offset in enumerate(range(0,len(blobs['stdout']),reader.MAX_FILE)):
                    name = f'stdout.{index:03d}'
                    save(name, blobs['stdout'][offset:offset+reader.MAX_FILE])
                    receipt['stdout_chunks'].append(name)
                receipt['stdout_sha256'] = sha(blobs['stdout'])
                receipt['stdout_bytes'] = len(blobs['stdout'])
                save('process.json', blobs['process']); save('returncode.txt', blobs['rc'])
                receipt.update(state='COMPLETE', delivery_verified=True, worker_terminal_proof=True)
        except collector.OriginalDeliveryRefused as error:
            receipt.update(state='UNAVAILABLE', delivery_verified=False, worker_terminal_proof=False,
                           reason=error.reason, failure_phase='original_remote_read', retry_authorized=False)
        except (OSError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error):
            receipt.update(state='UNAVAILABLE', delivery_verified=False, worker_terminal_proof=False,
                           reason='original_operator_delivery_unconfirmed', retry_authorized=False)
        delivery.publish_receipt(chain, receipt, {'paths':[]},
                                 verify_source=unchanged if receipt['state'] in ('COMPLETE','PENDING') else None)
        return receipt
