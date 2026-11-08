"""Fixed installed-source/credential/current-purpose acquisition.

The root owner receives this new source request only from its genuine Control
socket peer. The old SERVICE v3 protocol/defaults have no evaluation meaning.
No paths, principal facts, callback verifier or clock come from public requests.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
from common import memory_evaluation_contract as c
from common import memory_native_wire as w
from control_plane import protected_memory_profile as profiles
from control_plane import memory_native_issuer as issuer

CONFIG_SCHEMA = 'mastermind.protected_memory_evaluation_config.v1'
SLOTS = {f'memory-model-{i:02}': Path('/Library/Application Support/MastermindExecutive/credentials') / f'memory-model-{i:02}.json' for i in range(1, 4)}

def control_document():
    owner = issuer.describe_control_owner()
    raw = profiles._read_config()
    if hashlib.sha256(raw).hexdigest() != owner['configuration_sha256']: c.fail()
    return profiles._json(raw), owner

def configured(document):
    value = document.get('memory_evaluation')
    w.exact(value, 'schema armed coo_config coo_source work_ref profiles source_protocol')
    if (value['schema'] != CONFIG_SCHEMA or value['armed'] is not True
            or value['source_protocol'] != 'memory.e0.evaluation_issuer.v1'): c.fail()
    c.text(value['work_ref'], 256)
    for k in ('coo_config', 'coo_source'):
        if type(value[k]) is not str or not Path(value[k]).is_absolute() or '..' in Path(value[k]).parts: c.fail()
    rows = value['profiles']
    if type(rows) is not list or not 1 <= len(rows) <= 3: c.fail()
    seen = []
    for row in rows:
        w.exact(row, 'id profile credential_binding_ref credential_document_sha256')
        w.token(row['id']); c.refs(row['credential_binding_ref']); w.digest(row['credential_document_sha256'])
        profile_document(row['profile']); seen.append(row['id'])
    if len(set(seen)) != len(seen): c.fail()
    return value

def profile_document(value):
    if type(value) is not dict or value.get('credential_slot') not in SLOTS: c.fail()
    # Reuse ALL incumbent origin/model/policy/worker/account constraints. Only
    # this new, installed optional table admits the two further fixed slots.
    copy = dict(value, credential_slot='memory-model-01')
    profiles.validate_profile_document(copy)
    return json.loads(w.canonical(value))

def installed(runtime):
    from control_plane.executive_runtime import Runtime, JobStatus
    from ops.executive_os.coo_principal_host import CooInstalledSource
    if type(runtime) is not Runtime or os.geteuid() != 450: c.fail()
    document, owner = control_document(); config = configured(document)
    if document.get('runtime_root') != str(runtime.store.root): c.fail()
    source = CooInstalledSource.from_path(config['coo_config'], config['coo_source'], expected_uid=450)
    row, principal, authority = source.snapshot(config['work_ref'])
    grant = c.delegation(row.get('memory_evaluation_delegation'))
    now = runtime.store.now_ms()
    root = runtime.jobs.get_job(grant['root_job_id'])
    if (row.get('authority_version') != 3 or row['enabled'] is not True or grant['enabled'] is not True
            or grant['principal_binding_digest'] != principal.principal_binding_digest
            or not grant['not_before_ms'] <= now < grant['expires_at_ms']
            or root is None or root.root_job_id != root.job_id or root.status is not JobStatus.RUNNING): c.fail()
    from control_plane.executive_authority import ExecutiveAuthorityPolicy
    ExecutiveAuthorityPolicy.load().authorize(['READ'], worktree=root.worktree, allowed_write_paths=[], validation_commands=[])
    return source, row, grant, config, owner

def same(runtime, previous):
    current = installed(runtime)
    if current[1:] != previous[1:]: c.fail()
    return current

def model_observation(runtime, profile_id):
    context = installed(runtime)
    rows = [r for r in context[3]['profiles'] if r['id'] == profile_id]
    if len(rows) != 1: c.fail()
    row = rows[0]; selected = profile_document(row['profile'])
    credential = credential_observation(selected)
    if credential['document_sha256'] != row['credential_document_sha256']: c.fail()
    same(runtime, context)
    return dict(profile_id=profile_id, profile=selected, credential_binding_ref=row['credential_binding_ref'],
        credential_document_sha256=credential['document_sha256'], credential_metadata=credential['metadata'])

def credential_observation(selected):
    """Actual fixed private object, not account text, inode or path as actor ID.

    Hash/metadata remain in protected custody. Canonical actor identity comes
    ONLY from the independently authenticated assessor's admitted mapping.
    """
    from control_plane.codex_provider_realm import _native_open
    with _native_open(SLOTS[selected['credential_slot']]) as (fd, info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 450
                or stat.S_IMODE(info.st_mode) != 0o440 or info.st_nlink != 1 or not 1 <= info.st_size <= 8192): c.fail()
        raw = os.read(fd, info.st_size + 1)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != info.st_size or identity(info) != identity(os.fstat(fd)): c.fail()
    value = profiles._json(raw)
    w.exact(value, 'schema account_ref api_key')
    if (value['schema'] != 'mastermind.protected_memory_model_credential.v1'
            or value['account_ref'] != selected['account_ref']): c.fail()
    c.text(value['api_key'], 4096)
    return {'document_sha256': hashlib.sha256(raw).hexdigest(), 'metadata': list(identity(info))}

def make_request(grant, action='read_evaluation_basis', *, subject=None, assignment=None, input_sha256=None, pair_sha256=None):
    return c.request(dict(schema=c.REQUEST, action=action, delegation=grant, subject=subject,
        assignment=assignment, input_sha256=input_sha256, pair_sha256=pair_sha256))

def exchange(runtime, request):
    before = installed(runtime)
    if request['delegation'] != before[2]: c.fail()
    result = issuer._send({'schema': issuer.SCHEMA, 'operation': 'evaluation_source', 'request': c.request(request)})
    w.exact(result, 'schema state response')
    if result['schema'] != issuer.SCHEMA or result['state'] != 'EVALUATION_SOURCE_CURRENT': c.fail()
    response = c.response(result['response'], request)
    same(runtime, before)
    now = runtime.store.now_ms()
    if not response['not_before_ms'] <= now < response['expires_at_ms']: c.fail()
    return response

def root_exchange(request, connection):
    """Only called from the incumbent privileged socket's Control-peer branch."""
    from control_plane import protected_memory_peer as peer
    from control_plane import executive_memory_issuer as root
    observed = peer.observe_control_owner(connection)
    enrolled = root._enrollment(observed)
    document = profiles._json(enrolled[0]); config = configured(document)
    request = c.request(request)
    from ops.executive_os.coo_principal_host import CooInstalledSource
    source = CooInstalledSource.from_path(config['coo_config'], config['coo_source'], expected_uid=0)
    row, fact, _ = source.snapshot(config['work_ref'])
    grant = c.delegation(row.get('memory_evaluation_delegation'))
    import time
    if (row['enabled'] is not True or grant['enabled'] is not True or request['delegation'] != grant
            or grant['principal_binding_digest'] != fact.principal_binding_digest
            or not grant['not_before_ms'] <= int(time.time()*1000) < grant['expires_at_ms']
            or grant['source_audience']['service_key_fingerprint'] != enrolled[1]): c.fail()
    raw = w.canonical(request)
    framed = root._exchange(len(raw).to_bytes(4, 'big') + raw)
    response = c.response(w._unframe(framed, 262144), request)
    if (source.snapshot(config['work_ref'])[0] != row or peer.observe_control_owner(connection) != observed
            or root._enrollment(observed) != enrolled): c.fail()
    return response
