"""Fixed Memory SSH exchange inside the EXISTING privileged broker.

No endpoint/argv/key/path is selected by a request. Root key confinement and
Control process qualification are independent of Linux's current enrolled
service+recipient/source grant. No installation or runtime grant is issued here.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time

from common import memory_native_wire as wire
from control_plane import protected_memory_peer as peer

SCHEMA = 'mastermind.protected_memory_issuer_exchange.v1'
CONFIG = Path('/Library/Application Support/MastermindExecutive/config/control.json')
KEY = Path('/var/db/mastermind-executive/memory-issuer/id_ed25519')
PUBLIC = KEY.with_suffix('.pub')
KNOWN_HOSTS = Path('/var/db/mastermind-executive/memory-issuer/known_hosts')
REMOTE_COMMAND = '/opt/macro-api/.venv/bin/python -I -B /opt/macro/scripts/market_memory_e0_native_issuer.py'

class IssuerExchangeUnknown(ValueError):
    def __init__(self): super().__init__('memory_issuer_original_exchange_unknown')

def fail(): raise peer.ProtectedMemoryRefused()

def validate_transport_document(value):
    """Pure closed config shape; never enrollment or current source permission."""
    if type(value) is not dict:fail()
    if value.get('schema')=='mastermind.fixed_memory_issuer_transport.v1':
        wire.exact(value,'schema protocol service_key_fingerprint known_hosts_sha256')
        if value['protocol']!='memory.e0.native_issuer.v2':fail()
    elif value.get('schema')=='mastermind.fixed_memory_issuer_transport.v2':
        wire.exact(value,'schema protocol service_key_fingerprint known_hosts_sha256 transport_profile')
        if (value['protocol']!='memory.e0.native_issuer.v3'
                or value['transport_profile']!='memory.e0.protected_m2_service_ssh.v2'):fail()
    else:fail()
    wire.fingerprint(value['service_key_fingerprint']);wire.digest(value['known_hosts_sha256'])
    return json.loads(wire.canonical(value))

def _read(path, maximum, *, private=False):
    from control_plane.codex_provider_realm import _native_open
    with _native_open(path) as (fd, info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_mode & (0o077 if private else 0o022)
                or not 1 <= info.st_size <= maximum): fail()
        raw = bytearray()
        while len(raw) <= info.st_size:
            part = os.read(fd, min(65536, info.st_size+1-len(raw)))
            if not part: break
            raw.extend(part)
        current = os.fstat(fd)
        identity = lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(raw) != info.st_size or identity(info) != identity(current): fail()
    return bytes(raw)

def _enrollment(observed):
    if os.geteuid() != 0: fail()
    raw = _read(CONFIG, 4194304)
    if hashlib.sha256(raw).hexdigest() != observed['configuration_sha256']: fail()
    # Config is installed owner DATA, not a supplied auth flag. Remote native
    # sshd/protected-helper proof and current recipient grant remain Linux-owned.
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value: fail()
            value[key] = item
        return value
    document = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: fail())
    value = validate_transport_document(document.get('memory_native_issuer'))
    public = _read(PUBLIC, 4096).decode('ascii').split()
    if len(public) not in (2,3) or public[0] != 'ssh-ed25519': fail()
    try: keyblob = base64.b64decode(public[1], validate=True)
    except ValueError: fail()
    fingerprint = 'SHA256:'+base64.b64encode(hashlib.sha256(keyblob).digest()).decode().rstrip('=')
    if fingerprint != value['service_key_fingerprint']: fail()
    known = _read(KNOWN_HOSTS, 65536)
    if hashlib.sha256(known).hexdigest() != value['known_hosts_sha256']: fail()
    # Inspect private metadata only; never export/read the SSH secret into JSON.
    from control_plane.codex_provider_realm import _native_open
    with _native_open(KEY) as (_, info):
        if (info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600): fail()
        keyidentity = (info.st_dev,info.st_ino,info.st_mode,info.st_mtime_ns,info.st_ctime_ns)
    _read(Path('/usr/bin/ssh'), 16777216)
    return raw, fingerprint, known, keyidentity

def _exchange(frame):
    # Fixed forced-command-only separately enrolled identity. Do not use the
    # principal deploy key, SSH config/agent, user env or forwarding fallback.
    argv = ['/usr/bin/ssh','-F','/dev/null','-T','-o','BatchMode=yes',
        '-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','StrictHostKeyChecking=yes',
        '-o','UpdateHostKeys=no','-o','ClearAllForwardings=yes','-o','ForwardAgent=no',
        '-o','SendEnv=-*','-o','ControlMaster=no','-o','ControlPath=none','-o','ControlPersist=no',
        '-o','ForwardX11=no','-o','PermitLocalCommand=no','-o','RequestTTY=no',
        '-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','ProxyCommand=none',
        '-o','UserKnownHostsFile='+str(KNOWN_HOSTS),'-i',str(KEY),
        'root@146.190.142.17', REMOTE_COMMAND]
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, close_fds=True, env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','LANG':'C'})
    # A disconnected/timeout exchange is UNKNOWN. We neither kill/release nor
    # retry the original source operation. Output is bounded before retention.
    deadline = time.monotonic()+120
    try:
        output = bytearray()
        pending = memoryview(frame)
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE, 'input')
            selector.register(proc.stdout, selectors.EVENT_READ, 'output')
            complete = False
            while not complete:
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise IssuerExchangeUnknown()
                ready = selector.select(remaining)
                if not ready: raise IssuerExchangeUnknown()
                for selected, _ in ready:
                    if selected.data == 'input':
                        written = os.write(proc.stdin.fileno(), pending)
                        if written <= 0: raise IssuerExchangeUnknown()
                        pending = pending[written:]
                        if not pending:
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        part = os.read(proc.stdout.fileno(), min(65536,262149-len(output)))
                        if not part:
                            complete = True
                            break
                        output.extend(part)
                        if len(output) > 262148: raise IssuerExchangeUnknown()
            if pending: raise IssuerExchangeUnknown()
        if proc.wait(timeout=max(0.001,deadline-time.monotonic())) != 0: raise IssuerExchangeUnknown()
        return bytes(output)
    except Exception:
        raise IssuerExchangeUnknown() from None
    finally:
        # Closing local pipes never means cancellation or absence of effect.
        if proc.stdin is not None and not proc.stdin.closed: proc.stdin.close()
        if proc.stdout is not None: proc.stdout.close()

def _protocol(enrollment):
    from control_plane.protected_memory_profile import _json
    return validate_transport_document(_json(enrollment[0])['memory_native_issuer'])['protocol']

def qualify_before_economic(admitted):
    """Real read-only v3 exchange; no capability/cache/row/count is issued."""
    prepare,_=peer.require_protected_memory_intent(admitted)
    state=peer._ISSUED[admitted]
    observed=peer.observe_control_owner(state.connection)
    before=_enrollment(observed)
    if _protocol(before)!='memory.e0.native_issuer.v3':fail()
    request=wire.validate_request(dict(prepare,schema='research_factory.market_memory_e0_native_issuer_request.v3',
        action='qualify_current_case'))
    response=wire.decode_response(_exchange(wire.encode_request(request)),request=request)
    if (response.get('status')!='CURRENT_CASE_QUALIFIED'
            or response['issuer']['broker_service_fingerprint']!=before[1]):fail()
    peer.require_protected_memory_intent(admitted)
    if peer.observe_control_owner(state.connection)!=observed or _enrollment(observed)!=before:fail()

def handle_memory_exchange(raw, connection):
    """Fixed branch, called with the real accepted socket by privileged owner."""
    try:
        observed = peer.observe_control_owner(connection)
        if type(raw) is not dict or raw.get('schema') != SCHEMA: fail()
        if raw.get('operation') == 'describe':
            wire.exact(raw, 'schema operation')
            return {'schema':SCHEMA,'state':'OWNER_CURRENT','owner':observed}
        if raw.get('operation') == 'evaluation_source':
            wire.exact(raw, 'schema operation request')
            from control_plane.protected_memory_evaluation_source import root_exchange
            return {'schema':SCHEMA, 'state':'EVALUATION_SOURCE_CURRENT',
                'response':root_exchange(raw['request'], connection)}
        if raw.get('operation') == 'evaluation_economic':
            wire.exact(raw, 'schema operation projection request evaluation_context')
            admitted = peer.accept_protected_memory_intent(raw['projection'], connection)
            from control_plane import protected_memory_economic_owner as economic
            receipt = economic.execute(admitted, raw['request'], evaluation_context=raw['evaluation_context'])
            return {'schema':SCHEMA, 'state':'ECONOMIC_OBSERVED', 'receipt':receipt}
        if raw.get('operation') == 'qualify_transport':
            wire.exact(raw, 'schema operation projection')
            admitted = peer.accept_protected_memory_intent(raw['projection'], connection)
            peer.require_protected_memory_intent(admitted)
            before = _enrollment(observed)
            from control_plane.protected_memory_economic_owner import qualify_helper_source
            qualify_helper_source()
            if peer.observe_control_owner(connection)!=observed or _enrollment(observed)!=before: fail()
            return {'schema':SCHEMA,'state':'TRANSPORT_CONFIGURED','protocol':_protocol(before)}
        if raw.get('operation')=='completed_result':
            wire.exact(raw,'schema operation material')
            from control_plane.protected_memory_result_access import authorize_completed_read
            return {'schema':SCHEMA,'state':'COMPLETED_READ_CURRENT',
                'receipt':authorize_completed_read(connection,raw['material'])}
        if raw.get('operation') == 'economic':
            wire.exact(raw, 'schema operation projection request')
            admitted = peer.accept_protected_memory_intent(raw['projection'], connection)
            from control_plane import protected_memory_economic_owner as economic
            receipt = economic.execute(admitted, raw['request'])
            return {'schema':SCHEMA,'state':'ECONOMIC_OBSERVED','receipt':receipt}
        wire.exact(raw, 'schema operation projection request')
        if raw['operation'] != 'exchange': fail()
        admitted = peer.accept_protected_memory_intent(raw['projection'], connection)
        prepare, _ = peer.require_protected_memory_intent(admitted)
        request = wire.validate_request(raw['request'])
        if (request['schema'] not in ('research_factory.market_memory_e0_native_issuer_request.v2','research_factory.market_memory_e0_native_issuer_request.v3')
                or request['operation_id'] != prepare['operation_id'] or request['intent'] != prepare['intent']): fail()
        if request['action'] == 'prepare_case':
            # Source reservation is downstream of REAL incumbent paid capacity,
            # account, root/operator allowance and current child lease admission.
            from control_plane import protected_memory_economic_owner as economic
            receipt = economic.execute(admitted, {'action':'current', 'arguments':{}})
            if receipt['phase'] != 'RESERVED': fail()
        before = _enrollment(observed)
        if _protocol(before)!='memory.e0.native_issuer.'+request['schema'][-2:]:fail()
        result = _exchange(wire.encode_request(request))
        response = wire.decode_response(result, request=request)
        if peer.observe_control_owner(connection) != observed or _enrollment(observed) != before: fail()
        peer.require_protected_memory_intent(admitted)
        if 'issuer' in response and response['issuer']['broker_service_fingerprint'] != before[1]: fail()
        return {'schema':SCHEMA,'state':'EXCHANGED','response':response}
    except IssuerExchangeUnknown:
        return {'schema':SCHEMA,'state':'ORIGINAL_EXCHANGE_UNKNOWN'}
    except Exception:
        return {'schema':SCHEMA,'state':'REFUSED'}
