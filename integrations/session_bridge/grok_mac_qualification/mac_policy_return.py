"""Original mac-policy result recovery; read-only incumbent collector extension.

Never launch, acknowledge, publish canonical results, settle or release a lease.
An old controller may still be alive. Output is current retained evidence only.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

RUN = 'fabric-grok-mac-policy-build-01a11e90-v1'
ROOT = '01a11e90-4b5d-7f53-b966-8aaaad38701f'
HOST = 'ubuntu1'
SUPPORT = '06915d0288c7ad9a24ce736eaff34a43b47fb4af4a208ab816d62fd7a010389a'
LOG_SHA = '841531bffe647486f34eeaf8c8b166742fd3992f2db8a53504095d86b6664162'
PACKET = Path('/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/grok-mac-qualification-20261012/POLICY_PACKET.txt')
PACKET_SHA = 'c400c40d72ccf91b04d057a5b1e24db62b3dc2258b948071cc874f0d2ce278f5'
SCHEMA = 'mastermind.mac_policy_original_return.v1'
MAX_FILE = 262144
MAX_RESPONSE = 1800000
PATHS = {'rc': ('lanes_'+RUN+'.rc',),
         'terminal': ('lanes', RUN+'.native-terminal.json'),
         'process': ('lanes', RUN+'.process.jsonl'),
         'stdout': ('lanes_'+RUN+'.stdout',)}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def request_for(run, root):
    if run != RUN or root != ROOT:
        raise ValueError('original_mac_policy_scope_mismatch')
    return dict(schema=SCHEMA, run_id=RUN, root=ROOT, parent=ROOT, host=HOST,
                support_digest=SUPPORT, log_sha256=LOG_SHA, packet_sha256=PACKET_SHA)

def verify_request(request):
    if type(request) is not dict or request != request_for(RUN, ROOT):
        raise ValueError('original_mac_policy_request_mismatch')

def read_current(request):
    """Fixed remote files under held directory descriptors; no arbitrary paths."""
    import run_observation as ob
    verify_request(request)
    uid = os.getuid()
    home = ob.pwd.getpwuid(uid).pw_dir
    with ob.Reader(home, uid) as reader:
        base = ('lanes', 'support-releases', SUPPORT)
        manifest_raw, _ = reader.read((*base, 'RELEASE.json'), 65536, mode=0o444)
        manifest = ob.strict_json(manifest_raw)
        if type(manifest) is not dict: raise ValueError('original_support_manifest_shape')
        files = manifest.get('files')
        if (manifest.get('schema') != 'remote-support-code.v1'
                or manifest.get('digest') != SUPPORT or type(files) is not dict
                or not 1 <= len(files) <= 40
                or digest(canonical(dict(schema=manifest['schema'], files=files))) != SUPPORT):
            raise ValueError('original_support_manifest_mismatch')
        total = 0
        for name, expected in sorted(files.items()):
            if (not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', name)
                    or not re.fullmatch(r'[a-f0-9]{64}', expected)):
                raise ValueError('original_support_filename_or_digest')
            code, _ = reader.read((*base, 'ext', name), min(2*MAX_FILE, 16*MAX_FILE-total), mode=0o555)
            total += len(code)
            if digest(code) != expected:
                raise ValueError('original_support_code_changed')
        if reader.read((*base, 'RELEASE.json'), 65536, mode=0o444)[0] != manifest_raw:
            raise ValueError('original_support_manifest_changed')
        # Verify the one immutable link which routes receipts into stable ext.
        parent_depth, edge_depth = len(reader.fds), len(reader.edges)
        try:
            for part in (*base, 'ext'):
                reader.descend(part)
            expected_link = str(Path(home)/'lanes/ext/lanes')
            link_identity = ob.identity(os.stat('lanes',dir_fd=reader.fds[-1],follow_symlinks=False))
            link_parent_identity = ob.directory_identity(os.fstat(reader.fds[-1]))
            if os.readlink('lanes', dir_fd=reader.fds[-1]) != expected_link:
                raise ValueError('original_support_receipt_link_changed')
            reader.verify()
        finally:
            for fd in reversed(reader.fds[parent_depth:]): os.close(fd)
            del reader.fds[parent_depth:]; del reader.edges[edge_depth:]
        reader.descend('lanes'); reader.descend('ext')
        held = {}
        for role, path in PATHS.items():
            held[role] = reader.read(path, 16 if role == 'rc' else MAX_FILE)
        for role, path in reversed(list(PATHS.items())):
            current = reader.read(path, 16 if role == 'rc' else MAX_FILE)
            if (current[0] != held[role][0]
                    or ob.identity(current[1]) != ob.identity(held[role][1])):
                raise ValueError('original_result_changed_during_read')
        reader.verify()
        with ob.Reader(home,uid) as links:
            if links.read((*base,'RELEASE.json'),65536,mode=0o444)[0] != manifest_raw:
                raise ValueError('original_support_manifest_changed')
            for part in (*base,'ext'): links.descend(part)
            if (ob.directory_identity(os.fstat(links.fds[-1])) != link_parent_identity
                    or ob.identity(os.stat('lanes',dir_fd=links.fds[-1],follow_symlinks=False)) != link_identity
                    or os.readlink('lanes',dir_fd=links.fds[-1]) != expected_link):
                raise ValueError('original_support_receipt_link_changed')
            links.verify()
    return dict(schema=SCHEMA, request_sha256=digest(canonical(request)),
                support_files=files,
                files={k: dict(bytes=len(v[0]), sha256=digest(v[0]),
                               content_b64=base64.b64encode(v[0]).decode()) for k,v in held.items()})

def source_bytes():
    import artifact_delivery as delivery
    import run_observation as ob
    import artifact_production as production
    return {name: delivery.local_file(path, 1048576) for name,path in
            dict(module=Path(__file__), observer=Path(ob.__file__), producer=Path(production.__file__)).items()}

def qualify(request):
    import artifact_delivery as delivery
    verify_request(request)
    log = delivery.local_file(delivery.HERE/'state/remote_sub'/(RUN+'.log'))
    if digest(log) != LOG_SHA or digest(delivery.local_file(PACKET)) != PACKET_SHA:
        raise ValueError('original_local_evidence_changed')
    registry_raw = delivery.local_file(delivery.HERE/'hosts.json')
    registry = delivery.reader.strict_json(registry_raw)
    entry = registry[HOST]
    alias = entry['ssh_alias']
    if (alias != 'ubuntu1' or entry.get('platform') != 'linux'
            or entry.get('hostnames') != ['mastermind-pc']
            or 'lanes' not in entry.get('roles',[]) or 'grok' not in entry.get('allowed_modes',[])):
        raise ValueError('original_host_alias_invalid')
    return dict(ssh_alias=alias,registry_sha256=digest(registry_raw), sources={k:digest(v) for k,v in source_bytes().items()},
                log_sha256=LOG_SHA, packet_sha256=PACKET_SHA)

def code_for_request(request, *, expected_hashes):
    verify_request(request)
    raw = source_bytes()
    if {k:digest(v) for k,v in raw.items()} != expected_hashes:
        raise ValueError('original_read_source_changed')
    return ("import sys,types,json\n"
            "ob=types.ModuleType('run_observation');sys.modules[ob.__name__]=ob\n"
            "exec("+repr(raw['observer'].decode())+",ob.__dict__)\n"
            "ns={'__name__':'_mac_policy_read'}\n"
            "exec("+repr(raw['module'].decode())+",ns)\n"
            "raw=sys.stdin.buffer.read(8193)\n"
            "if len(raw)>8192: raise ValueError('request_limit')\n"
            "req=ob.strict_json(raw)\n"
            "if req!="+repr(request)+": raise ValueError('request_mismatch')\n"
            "try: response=ns['read_current'](req)\n"
            "except (OSError,ValueError,TypeError,KeyError) as exc:\n"
            " response={'schema':ns['SCHEMA'],'request_sha256':ns['digest'](ns['canonical'](req)),"
            "'state':'UNAVAILABLE','reason':ns['safe_reason'](exc),'errno':getattr(exc,'errno',None)}\n"
            "print(ns['canonical'](response).decode())\n")

def safe_reason(exc):
    if isinstance(exc,PermissionError): return 'filesystem_permission_refused'
    if isinstance(exc,FileNotFoundError): return 'missing_at_read'
    if isinstance(exc,ValueError) and re.fullmatch(r'[a-z_]{1,100}',str(exc)):
        return str(exc)
    return type(exc).__name__

def validate_response(raw, request):
    import artifact_delivery as delivery
    import artifact_production as production
    from lane_runtime import cleanup_receipt_is_proven
    verify_request(request)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('response_limit')
    value = delivery.reader.strict_json(raw)
    if (type(value) is dict and value.get('state') == 'UNAVAILABLE'
            and value.get('schema') == SCHEMA and value.get('request_sha256') == digest(canonical(request))
            and type(value.get('reason')) is str and re.fullmatch(r'[A-Za-z_]{1,100}',value['reason'])):
        raise ValueError('remote_'+value['reason'])
    if (type(value) is not dict or set(value) != {'schema','request_sha256','files','support_files'}
            or value['schema'] != SCHEMA or value['request_sha256'] != digest(canonical(request))
            or type(value['files']) is not dict or set(value['files']) != set(PATHS)
            or digest(canonical(dict(schema='remote-support-code.v1',files=value['support_files']))) != SUPPORT):
        raise ValueError('response_binding')
    files = {}
    for role, item in value['files'].items():
        if type(item) is not dict or set(item) != {'bytes','sha256','content_b64'} or type(item['bytes']) is not int:
            raise ValueError('file_shape')
        if not 0 <= item['bytes'] <= (16 if role=='rc' else MAX_FILE):
            raise ValueError('file_limit')
        data = base64.b64decode(item['content_b64'], validate=True)
        if len(data) != item['bytes'] or digest(data) != item['sha256']:
            raise ValueError('file_integrity')
        files[role] = data
    if files['rc'] != b'0\n':
        raise ValueError('original_worker_nonzero_or_nonterminal')
    terminal = delivery.reader.strict_json(files['terminal'])
    process = delivery.reader.strict_json(files['process'])
    if type(terminal) is not dict or type(process) is not dict:
        raise ValueError('original_receipt_shape')
    if type(terminal.get('output_binding')) is not dict or type(terminal.get('launch_timing')) is not dict:
        raise ValueError('original_binding_shape')
    producer = delivery.local_file(Path(production.__file__))
    packet = delivery.local_file(PACKET)
    if (value['support_files'].get('artifact_production.py') != digest(producer)
            or digest(packet) != PACKET_SHA):
        raise ValueError('original_packet_encoder_unproven')
    original_contract = production.parse_packet(production.encode_packet(packet.decode(),
        root=ROOT,parent=ROOT,run_id=RUN,support_digest=SUPPORT,
        names=['unified.patch','bootstrap_host_policy.py','test_host_policy.py']))
    if terminal.get('output_binding',{}).get('contract') != original_contract:
        raise ValueError('original_packet_contract_mismatch')
    cleanup = process.get('cleanup') or {}
    if (terminal.get('schema') != 'mastermind.native.remote-terminal.v1'
            or any(terminal.get(k) != v for k,v in dict(run_id=RUN,root=ROOT,host=HOST,mode='grok',model='grok-4.6').items())
            or terminal.get('started') is not True or type(terminal.get('returncode')) is not int or terminal['returncode'] != 0
            or terminal.get('cleanup_proven') is not True or terminal.get('output_complete') is not True
            or terminal.get('launch_timing',{}).get('support_digest') != SUPPORT
            or process.get('schema') != 'mastermind.local_owned_process_receipt.v1'
            or process.get('label') != RUN or type(process.get('returncode')) is not int or process['returncode'] != 0
            or process.get('timed_out') is not False or process.get('runtime_failure_code') is not None
            or type(terminal.get('capture')) is not dict
            or set(terminal['capture']) != {'stdout_bytes','stderr_bytes','stdout_truncated','stderr_truncated'}
            or terminal['capture'].get('stdout_truncated') is not False
            or terminal['capture'].get('stderr_truncated') is not False
            or terminal.get('cleanup') != process.get('cleanup')
            or not cleanup_receipt_is_proven(cleanup)
            or type(cleanup.get('residual_count')) is not int or cleanup['residual_count'] != 0
            or cleanup.get('error_code') is not None
            or any(cleanup.get(stem+'_complete') is not True or cleanup.get(stem+'_error') is not None
                   for stem in ('stdin_delivery','stdout_capture','stderr_capture'))
            or any(type(process.get(k)) is not type(v) or process.get(k) != v for k,v in terminal.get('capture',{}).items())):
        raise ValueError('original_terminal_or_cleanup_unqualified')
    binding_request = dict(run_id=RUN,root=ROOT,parent=ROOT,host=HOST,
                           stdout_sha256=digest(files['stdout']),paths=[])
    delivery.qualify_grok_output(binding_request,terminal,process,files['stdout'])
    lease = delivery.retained_lease(terminal.get('lease_id'),include_pool=True)
    if lease is None or any(lease[k] != v for k,v in dict(orchestrator_id=ROOT,host=HOST,pool='grok',account=terminal.get('account'),model='grok-4.6').items()):
        raise ValueError('original_lease_binding_mismatch')
    return files, dict(lease_id=lease['id'], observed_lease_state=lease['state'],
                       stdout_sha256=digest(files['stdout']))

def recover(run, root, destination):
    import artifact_delivery as delivery
    request = request_for(run,root)
    evidence = qualify(request)
    chain = delivery.reserve_destination(Path(destination))
    receipt = dict(schema=SCHEMA,request=request,evidence=evidence,state='READ_INTENT',
                   execution_replayed=False,effect_state_changed=False,outcome_accepted=False,
                   original_controller_inactive_proven=False,files=[])
    created = {}
    try:
        delivery.write_exclusive(chain.fd,'request.json',canonical(receipt))
        try:
            raw = delivery.transport(evidence['ssh_alias'],request,current_sources_sha256=evidence['sources'])
            files,binding = validate_response(raw,request)
            if qualify(request) != evidence:
                raise ValueError('original_local_evidence_changed')
            for role,data in files.items():
                chain.verify();created[role] = delivery.write_exclusive(chain.fd,role+'.bin',data)
            receipt.update(state='RETAINED_ORIGINAL_RESULT',binding=binding,
                           files=[dict(path=k,local_name=k+'.bin',bytes=len(v),sha256=digest(v)) for k,v in files.items()])
            delivery.verify_delivered(chain,receipt['files'])
        except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError) as exc:
            receipt.update(state='UNAVAILABLE',reason=safe_reason(exc),errno=getattr(exc,'errno',None))
        def unchanged():
            if qualify(request) != evidence: raise ValueError('original_local_evidence_changed')
            for role,identity in created.items():
                if delivery.inode(os.stat(role+'.bin',dir_fd=chain.fd,follow_symlinks=False)) != identity:
                    raise ValueError('delivered_inode_changed')
        delivery.publish_receipt(chain,receipt,{'paths':list(PATHS)},
            verify_source=unchanged if receipt['state']=='RETAINED_ORIGINAL_RESULT' else None)
        return receipt
    finally:
        chain.close()
