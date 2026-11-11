"""Fixed metadata-only economic branch of the incumbent privileged owner.

Root already qualifies the current installed Control connection. One bounded
root-owned helper then runs the EXISTING OperatorOwner/Broker as UID501, against
their existing namespace. No private source, credential or result bytes cross
that boundary. A root/Runtime claim alone never substitutes for its real grant.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from common import memory_native_wire as wire
from control_plane import protected_memory_peer as peer

HELPER = Path(__file__).resolve().parents[1] / 'scripts/protected_memory_economic_helper.py'
OWNER = Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')
SCHEMA = 'mastermind.protected_memory_economic_request.v1'
ACTIONS = frozenset({'acquire', 'current', 'bind_input', 'consume', 'heartbeat', 'settle'})


def fail(): raise peer.ProtectedMemoryRefused()


def qualify_helper_source():
    from control_plane.paid_fabric_backend import _root_source
    root = HELPER.parents[1]
    from control_plane.protected_memory_profile import _json
    manifest = _json(_root_source(root / '.executive-release-manifest.json'))
    if manifest.get('commit_sha') != root.name: fail()
    entries = {r['path']: r for r in manifest['entries']}
    profile_name='ops/native_fabric/provider_plans/memory118/profile.json'
    names = ['scripts/protected_memory_economic_helper.py',profile_name]
    names += ['ops/native_fabric/provider_plans/memory118/native_owner/' + n for n in (
        'fabric_operator_contract.py', 'fabric_operator_owner.py', 'fabric_memory_view.py',
        'protected_memory_economic.py', 'lease_broker.py', 'artifact_delivery.py',
        'fabric_task.py', 'provider_outcome.py', 'run_observation_delivery.py')]
    names += ['ops/native_fabric/quota_continuity/candidate/' + n for n in ('pool_ledger.py','pick.py')]
    names += ['ops/native_fabric/quota_continuity/source/'+n for n in ('model_tier.py','fabric_policy_snapshot.py')]
    retained={}
    for name in names:
        raw = _root_source(root / name); entry = entries.get(name)
        if (type(entry) is not dict or entry.get('sha256') != hashlib.sha256(raw).hexdigest()
                or entry.get('size') != len(raw)): fail()
        retained[name]=raw
    # Source correspondence only: a coherent source manifest cannot pair a
    # smaller historical helper with the current preserving native profile.
    # Use the SAME checked bytes; no second path read or selection/grant claim.
    profile=_json(retained[profile_name])
    if type(profile) is not dict or type(profile.get('files')) is not dict:fail()
    for name in ('lease_broker.py','fabric_task.py'):
        source_name='ops/native_fabric/provider_plans/memory118/native_owner/'+name
        if profile['files'].get('ext/'+name)!=hashlib.sha256(retained[source_name]).hexdigest():fail()
    _root_source(Path(sys.executable).resolve(strict=True))


def _call_helper(payload):
    if os.geteuid() != 0: fail()
    qualify_helper_source()
    raw = wire.canonical(payload)
    if len(raw) > 16384: fail()
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    proc = None
    try:
        # The inherited FD has a kernel root creator; an ordinary501 caller
        # cannot forge it. No root/key/general-command capability is delegated.
        proc = subprocess.Popen([str(Path(sys.executable).resolve(strict=True)), '-I', '-B',
            str(HELPER), str(child.fileno())], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, pass_fds=(child.fileno(),),
            close_fds=True, user=501, group=20, extra_groups=[],
            env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'})
        child.close(); parent.settimeout(35)
        parent.sendall(len(raw).to_bytes(4, 'big') + raw); parent.shutdown(socket.SHUT_WR)
        result = bytearray()
        while len(result) <= 16388:
            part = parent.recv(min(4096, 16389 - len(result)))
            if not part: break
            result.extend(part)
        if len(result) < 5 or int.from_bytes(result[:4], 'big') != len(result)-4: fail()
        value = wire.parse(bytes(result[4:]), 16384)
        if proc.wait(timeout=2) != 0: fail()
        wire.exact(value, 'schema receipt')
        if value['schema'] != SCHEMA: fail()
        return value['receipt']
    except Exception:
        # An interrupted acquire/consume/accounting call is original UNKNOWN.
        # No kill, release, refund, second helper or alternate route is tried.
        from control_plane.executive_memory_issuer import IssuerExchangeUnknown
        raise IssuerExchangeUnknown() from None
    finally:
        parent.close(); child.close()


def _material(projection, observed, *, evaluation_profile_id=None):
    from control_plane import executive_memory_issuer as issuer
    from control_plane import protected_memory_profile as profile
    raw = issuer._read(issuer.CONFIG, 4194304)
    if hashlib.sha256(raw).hexdigest() != observed['configuration_sha256']: fail()
    document = profile._json(raw)
    value = document.get('protected_memory_execution')
    if evaluation_profile_id is not None:
        from control_plane.protected_memory_evaluation_source import configured, profile_document
        rows = [row for row in configured(document)['profiles'] if row['id'] == evaluation_profile_id]
        if len(rows) != 1: fail()
        value = profile_document(rows[0]['profile'])
    wire.exact(value, 'schema profile_id policy_sha256 worker_id quota_class provider model account_ref api_origin credential_slot')
    if (value['schema'] != profile.SCHEMA or value['profile_id'] != profile.PROFILE
            or value['provider'] != 'glm' or value['model'] not in ('glm-5.3','glm-5.3-flash')
            or value['policy_sha256'] != hashlib.sha256(profile.canonical(profile.POLICY)).hexdigest()): fail()
    wire.token(value['account_ref'])
    locator = projection['native_source_locator']
    selector = dict(root=locator['root_id'], parent=locator['operator_run_id'], run_id=locator['child_run_id'],
        pre_input_sha256=hashlib.sha256(peer.canonical(projection)).hexdigest(),
        profile_sha256=hashlib.sha256(profile.canonical(value)).hexdigest())
    route = dict(account=value['account_ref'], model=value['model'], host=socket.gethostname().split()[0])
    return raw, selector, route


def execute(admitted, request, *, evaluation_context=None):
    """Called only with a nominal current root-issued Control intent."""
    from control_plane import executive_memory_issuer as issuer
    peer.require_protected_memory_intent(admitted)
    state = peer._ISSUED[admitted]
    projection = json.loads(state.original)
    observed = peer.observe_control_owner(state.connection)
    if evaluation_context is not None:
        from control_plane import protected_memory_evaluation_source as evaluation_source
        wire.exact(evaluation_context, 'profile_id source_request')
        evaluation_source.root_exchange(evaluation_context['source_request'], state.connection)
    profile_id = None if evaluation_context is None else evaluation_context['profile_id']
    before, selector, route = _material(projection, observed, evaluation_profile_id=profile_id)
    wire.exact(request, 'action arguments')
    if type(request['action']) is not str or request['action'] not in ACTIONS: fail()
    action = request['action']; arguments = request['arguments']
    if action in ('current', 'heartbeat') and arguments != {}: fail()
    delegation=None
    if action=='acquire':
        wire.exact(arguments,'delegation')
        delegation=arguments['delegation'];wire.exact(delegation,'token task_class task_complexity model')
        # Do not call the helper/reserve a row/count/lease before genuine
        # current Linux service/recipient/source-purpose qualification.
        if evaluation_context is None:
            issuer.qualify_before_economic(admitted)
    if action == 'bind_input': wire.exact(arguments, 'input_sha256 input_bytes body_sha256')
    if action == 'consume':
        wire.exact(arguments, 'attempt_id process_ref_sha256')
        if arguments['attempt_id'] != projection['runtime_admission']['attempt_id']: fail()
    if action == 'settle': wire.exact(arguments, 'rc result_sha256 result_bytes')
    actual_peer=peer.capture_peer_identity(state.connection)
    if actual_peer.euid!=450:fail()
    result = _call_helper({'schema':SCHEMA, 'action':action, 'selector':selector,
        'route':route, 'arguments':{} if action=='acquire' else arguments,
        'controller_pid':actual_peer.pid,'delegation':delegation})
    peer.require_protected_memory_intent(admitted)
    if peer.observe_control_owner(state.connection) != observed or _material(projection, observed, evaluation_profile_id=profile_id)[0] != before: fail()
    if evaluation_context is not None:
        evaluation_source.root_exchange(evaluation_context['source_request'], state.connection)
    wire.exact(result, 'schema root parent run_id pre_input_sha256 profile_sha256 lease_id phase retry_authorized')
    if (result['schema'] != 'mastermind.protected_memory_economic_receipt.v1'
            or any(result[k] != v for k,v in selector.items()) or result['retry_authorized'] is not False
            or result['phase'] not in ('ADMITTED','RESERVED','BOUND','CONSUMED','SETTLING','SETTLED')): fail()
    wire.token(result['lease_id'])
    return result
