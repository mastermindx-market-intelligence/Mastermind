"""Strict DATA projection of actual paid owner observations.

No mint, process observation, source lookup or admission occurs here. The sole
shim backend supplies frames from its authenticated original controller; the
Runtime independently joins immutable claim/pin/commission evidence.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
from pathlib import Path
import re

from control_plane.paid_model_execution_contract import (
    ADAPTER_ID, ATTESTATION_SCHEMA, PROFILE_ID, EXECUTION_SURFACE,
    canonical, compile_request, descriptor, digest,
)
from control_plane.worker_execution_contract import BinaryAttestation

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_SOURCE_FIELDS = frozenset('schema_version worker_id provider host_ref model worker_uid worker_gid worker_user binary permission_profile_sha256 execution_profile_digest service_source_sha256 bridge_uid socket_path capture_root qualification capacity_capability_id'.split())
_PHYSICAL_FIELDS = (_SOURCE_FIELDS - {'capacity_capability_id'}) | {'worker_source_config_digest'}
_EMPTY = hashlib.sha256(b'').hexdigest()

_ENTRY_BINDING_FIELDS = frozenset(('schema_version host transport_alias worker_id account model '
    'boot_id source_config_sha256 release_manifest_sha256 registry_sha256 '
    'initializer_commitment_sha256 validator_sha256 readiness_source_sha256').split())


def provider_entry_descriptor(payload, *, sources_sha256, readiness_binding, config_identity):
    """Project owner-derived DATA; neither argument mints admission authority."""
    from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
    try:
        physical = require_paid_physical(payload)
        q = physical['qualification']
        c = q['initializer_commitment']
        if (c['bootstrap_python'] != c['launch_python']
                or c['startup']['profile'] != 'cpython-3.12-linux-root-prefix-nosite.v1'
                or type(sources_sha256) is not dict or set(sources_sha256) != entry.SOURCE_NAMES
                or any(type(h) is not str or not _SHA.fullmatch(h) for h in sources_sha256.values())
                or any(sources_sha256[n]!=q['qualifier_sources_sha256'][n] for n in entry.INITIALIZER_NAMES)
                or type(readiness_binding) is not dict or set(readiness_binding) != _ENTRY_BINDING_FIELDS
                or readiness_binding['schema_version']!='mastermind.paid_host_readiness_context/v1'):
            _refuse()
        expected = dict(host=q['registry_key'], transport_alias=q['transport_alias'],
            worker_id=physical['worker_id'], account=payload['paid_account'], model=physical['model'],
            boot_id=q['boot_id'], source_config_sha256=digest(payload['paid_source_config']),
            release_manifest_sha256=q['qualifier_source_manifest_sha256'],
            registry_sha256=q['registry_sha256'],
            initializer_commitment_sha256=q['initializer_commitment_sha256'])
        if any(readiness_binding.get(k) != v for k,v in expected.items()):_refuse()
        for key in ('validator_sha256', 'readiness_source_sha256'):
            if type(readiness_binding[key]) is not str or not _SHA.fullmatch(readiness_binding[key]):_refuse()
        return json.loads(canonical(dict(schema_version='mastermind.paid_provider_binding/v1',
            purpose=entry.PURPOSE, host_ref=q['registry_key'], transport_alias=q['transport_alias'],
            python_path=physical['binary']['path'], capture_root=physical['capture_root'],
            initializer_commitment=c, initializer_commitment_sha256=q['initializer_commitment_sha256'],
            config_identity=entry.validate_config_identity(config_identity,c),
            sources_sha256=sources_sha256, readiness_binding=readiness_binding,
            readiness_binding_sha256=digest(readiness_binding),
            physical_binding_sha256=payload['physical_binding_sha256'],
            run_id=payload['binding']['attempt_id'], account=payload['paid_account'],
            model=physical['model'], timeout_seconds=payload['launch_spec']['timeout_seconds'],
            body_sha256=descriptor(payload)['request_body_sha256'])))
    except (KeyError, TypeError, ValueError, OverflowError):_refuse()


class PaidWireRefused(ValueError):
    pass


def _refuse():
    raise PaidWireRefused('canonical_paid_owner_evidence_refused')


def require_paid_source(physical,source):
    """Pure source DATA consistency, without inventing a Job or LaunchSpec."""
    try:
        if (type(physical) is not dict or set(physical) != _PHYSICAL_FIELDS
                or type(source) is not dict or set(source) != _SOURCE_FIELDS
                or source['schema_version'] != 'mastermind.paid_worker_source/v1'
                or physical['schema_version'] != 'mastermind.paid_fabric_host_binding/v1'
                or physical['worker_source_config_digest'] != digest(source)
                or any(source[k] != physical[k] for k in _SOURCE_FIELDS - {
                    'schema_version', 'capacity_capability_id'})
                or source['provider'] != 'glm' or source['model'] not in {'glm-5.3','glm-5.3-flash'}):
            _refuse()
        for name in ('worker_id','host_ref','worker_user','capacity_capability_id'):
            if type(source[name]) is not str or not _ID.fullmatch(source[name]):
                _refuse()
        for name in ('permission_profile_sha256','execution_profile_digest','service_source_sha256'):
            if type(source[name]) is not str or not _SHA.fullmatch(source[name]):
                _refuse()
        for name in ('worker_uid','worker_gid','bridge_uid'):
            if type(source[name]) is not int or not 0 < source[name] < 2**31:
                _refuse()
        if source['bridge_uid'] != 501:
            _refuse()
        binary = source['binary']
        if type(binary) is not dict or set(binary) != {f.name for f in dataclasses.fields(BinaryAttestation)}:
            _refuse()
        if (type(binary['sha256']) is not str or not _SHA.fullmatch(binary['sha256'])
                or any(type(binary[k]) is not int or binary[k] < 0
                       for k in ('size','device','inode','mode','uid','gid','mtime_ns'))
                or not binary['size'] or not binary['mode'] & 0o111
                or type(binary['version']) is not str or not binary['version']
                or binary['team_identifier'] is not None):
            _refuse()
        for p in (binary['path'],binary['real_path'],source['socket_path'],source['capture_root']):
            if type(p) is not str or not Path(p).is_absolute() or '..' in Path(p).parts or '\x00' in p:
                _refuse()
        q=source['qualification']
        qfields={'registry_key','registry_sha256','transport_alias','host_env_path','host_env_sha256','boot_id',
                 'capture_identity','qualifier_source_manifest_sha256','qualifier_sources_sha256','probe_sha256'}
        preexec_fields={'initializer_commitment','initializer_commitment_sha256'}
        if type(q) is not dict or set(q) not in (qfields,qfields|preexec_fields):_refuse()
        has_preexec=set(q)==qfields|preexec_fields
        if has_preexec:
            from ops.native_fabric.quota_continuity.candidate.paid_initializer import validate_commitment
            commitment=validate_commitment(q['initializer_commitment'],host_ref=q['registry_key'],
                transport_alias=q['transport_alias'],python_path=binary['path'],capture_root=source['capture_root'])
            if (digest(commitment)!=q['initializer_commitment_sha256']
                    or commitment['host_env']['sha256']!=q['host_env_sha256']
                    or commitment['host_env']['path']!=q['host_env_path']
                    or commitment['launch_python']['real_path']!=binary['real_path']
                    or commitment['launch_python']['sha256']!=binary['sha256']
                    or (commitment['account']['uid'],commitment['account']['gid'],commitment['account']['user'])
                       !=(source['worker_uid'],source['worker_gid'],source['worker_user'])):_refuse()

        for key in ('registry_sha256','host_env_sha256','qualifier_source_manifest_sha256','probe_sha256'):
            if type(q[key]) is not str or not _SHA.fullmatch(q[key]):_refuse()
        for key in ('registry_key','transport_alias','boot_id'):
            if type(q[key]) is not str or not _ID.fullmatch(q[key]):_refuse()
        from control_plane.paid_model_execution_contract import paid_host_reference
        if source['host_ref']!=paid_host_reference(q['registry_key'],q['transport_alias']):_refuse()
        if q['host_env_path']!=str(Path(source['capture_root']).parent/'HOST_ENV.sh'):_refuse()
        ci=q['capture_identity']
        if (type(ci) is not dict or set(ci)!={'device','inode','mode','uid','gid'}
                or any(type(v) is not int or v<0 for v in ci.values())
                or ci['uid']!=source['worker_uid'] or ci['gid']!=source['worker_gid']
                or ci['mode'] & 0o022):_refuse()
        hashes=q['qualifier_sources_sha256']
        names={'host_pull.sh','host_pull_backend.py','host_pull_probe.template','paid_host_qualification.py','remote_sub.sh'}
        allowed_names=(names,)
        if has_preexec:
            names=names|{'paid_initializer.py'}
            current=names|{'paid_initializer_token_data.py','paid_initializer_nested_data.py'}
            allowed_names=(current,) if commitment['initialization_contract']=='paid-host-env-held-fd-token-data.v1' else (names,current)
        if (type(hashes) is not dict or set(hashes) not in allowed_names
                or any(type(v) is not str or not _SHA.fullmatch(v) for v in hashes.values())):_refuse()
        return json.loads(canonical(physical))
    except (KeyError,TypeError,ValueError,OverflowError):
        _refuse()


def require_paid_physical(payload):
    try:
        physical=require_paid_source(payload['paid_physical_binding'],payload['paid_source_config'])
        if (payload['physical_binding_sha256']!=digest(physical)
                or type(payload['paid_account']) is not str or not _ID.fullmatch(payload['paid_account'])):
            _refuse()
        spec, route = payload['launch_spec'], payload['paid_route']
        if (spec['worker_id'] != physical['worker_id']
                or spec['expected_worker_uid'] != physical['worker_uid']
                or spec['expected_worker_gid'] != physical['worker_gid']
                or spec['worker_user'] != physical['worker_user']
                or any(route[k] != physical[k] for k in ('provider','host_ref','model'))):
            _refuse()
        return physical
    except (KeyError,TypeError,ValueError,OverflowError):_refuse()


def paid_start_from_owned_launch(payload, frame, *, capsule, lease, controller, authority):
    """Project actual owner observations, then run the strict typed validator."""
    try:
        physical = require_paid_physical(payload)
        fields = frozenset('schema run_id model transport_host lease_id pid process_identity observed_user launch_nonce started_at python_path python_version source_manifest_sha256 request_body_sha256 capsule_binding_sha256 capture_contract capture_paths host_context'.split())
        initialized='initializer_commitment' in physical['qualification']
        if initialized:fields=fields|{'provider_entry'}
        if type(frame) is not dict or set(frame) != fields:
            _refuse()
        binding, route, spec = payload['binding'], payload['paid_route'], payload['launch_spec']
        if (frame['schema'] != 'mastermind.paid_model_owned_launch/v1'
                or frame['run_id'] != binding['attempt_id']
                or frame['model'] != route['model']
                or frame['transport_host'] != physical['qualification']['registry_key']
                or lease['host'] != physical['qualification']['registry_key']
                or frame['lease_id'] != lease['id'] or lease['account'] != payload['paid_account']
                or frame['capsule_binding_sha256'] != hashlib.sha256(json.dumps(capsule,
                    sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest()
                or frame['request_body_sha256'] != descriptor(payload)['request_body_sha256']):
            _refuse()
        image = frame['process_identity']
        image_fields = frozenset('start_identity pgid session_id effective_uid effective_gid real_uid real_gid parent_pid boot_id device inode mode uid gid size mtime_ns ctime_ns sha256'.split())
        if type(image) is not dict or set(image) != image_fields:
            _refuse()
        pid = frame['pid']
        if initialized:
            from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
            d=capsule['provider_entry']
            expected=provider_entry_descriptor(payload,sources_sha256=d['sources_sha256'],
                readiness_binding=d['readiness_binding'],config_identity=d['config_identity'])
            if d!=expected:_refuse()
            request=entry.request_from_capsule(capsule,capsule_raw=json.dumps(capsule,
                sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii'),
                timeout_seconds=1,entry_nonce=frame['launch_nonce'])
            entry.validate_ready(frame['provider_entry'],request,process_identity=image,pid=pid)
        if (type(pid) is not int or pid <= 0 or image['pgid'] != pid or image['session_id'] != pid
                or frame['observed_user'] != physical['worker_user']
                or any(image[k] != physical[v] for k,v in (
                    ('effective_uid','worker_uid'),('real_uid','worker_uid'),
                    ('effective_gid','worker_gid'),('real_gid','worker_gid')))):
            _refuse()
        q=physical['qualification']
        expected_context={key:q[key] for key in ('host_env_path','host_env_sha256','boot_id','capture_identity')}
        if type(frame['host_context']) is not dict or frame['host_context']!=expected_context:_refuse()
        if image['boot_id']!=q['boot_id']:_refuse()
        binary = physical['binary']
        if (frame['python_path'] != binary['path'] or frame['python_version'] != binary['version']
                or any(image[k] != binary[k] for k in (
                    'sha256','device','inode','mode','uid','gid','size','mtime_ns'))):
            _refuse()
        process = dict(pid=pid,pgid=pid,session_id=pid,
            start_identity=image['start_identity'],boot_id=image['boot_id'],
            observed_user=frame['observed_user'],launch_nonce=frame['launch_nonce'],
            **{k:image[k] for k in ('effective_uid','effective_gid','real_uid','real_gid')})
        lease_binding = dict(lease_id=lease['id'],orchestrator_id=lease['orchestrator_id'],
            pool=lease['pool'],account=lease['account'],host_ref=physical['host_ref'],model=lease['model'],
            controller_process=dict(pid=lease['pid'],start_identity=controller['process_start_identity'],
                                    boot_id=controller['boot_id']),
            runtime_fence_generation=authority.fence_generation,
            runtime_pin_version=authority.pin_version)
        evidence = dict(python_sha256=binary['sha256'],source_manifest_sha256=frame['source_manifest_sha256'],
            policy_sha256=descriptor(payload)['policy_sha256'],
            prompt_sha256=descriptor(payload)['prompt_sha256'],
            request_body_sha256=frame['request_body_sha256'],
            result_schema_sha256=descriptor(payload)['result_schema_sha256'],
            capsule_binding_sha256=frame['capsule_binding_sha256'],
            physical_binding_sha256=payload['physical_binding_sha256'],
            pin_identity_sha256=authority.pin_identity_sha256,
            capture_contract_sha256=digest(frame['capture_contract']),
            control_input_isolation_manifest_sha256=spec['isolation_manifest_sha256'])
        attestation = dict(schema_version=ATTESTATION_SCHEMA,profile_id=PROFILE_ID,
            adapter_id=ADAPTER_ID,execution_surface=EXECUTION_SURFACE,binding=binding,
            paid_route=route,worker_id=spec['worker_id'],quota_class=payload['paid_quota_class'],
            process_identity=process,lease_binding=lease_binding,evidence=evidence)
        from control_plane.paid_model_execution_principal import validate_paid_model_attestation
        attestation = validate_paid_model_attestation(attestation,
            expected_binding=binding,expected_route=route,expected_worker_id=spec['worker_id'],
            expected_quota_class=payload['paid_quota_class'],expected_process=process,
            expected_lease_binding=lease_binding,expected_evidence=evidence)
        # These are actual original owner capture paths. Control does not open
        # remote paths; collect reads the same owner's retained exact bytes.
        paths = frame['capture_paths']
        capture = Path(physical['capture_root'])/(binding['attempt_id']+'.paid')
        expected_paths=dict(stdout_path=str(capture/'stdout'),stderr_path=str(capture/'stderr'),
                            result_path=str(capture/'result.json'))
        if type(paths) is not dict or paths != expected_paths:
            _refuse()
        ref = dict(schema_version='mastermind.paid_model_process_ref/v1',
            run_id=binding['attempt_id'],worker_id=spec['worker_id'],host_ref=route['host_ref'],
            pid=pid,pgid=pid,session_id=pid,process_start_identity=image['start_identity'],
            boot_session_id=image['boot_id'],launch_nonce=frame['launch_nonce'],
            started_at=frame['started_at'],binary=binary,
            **paths,
            **{k:image[k] for k in ('effective_uid','effective_gid','real_uid','real_gid')})
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        return dict(adapter_id=ADAPTER_ID,binding=binding,
            request_sha256=start_request_sha256(payload),
            physical_binding_sha256=payload['physical_binding_sha256'],
            process_ref=ref,launch_attestation=attestation)
    except (KeyError,TypeError,ValueError,OverflowError):
        _refuse()


def validate_owned_terminal(frame, launch):
    try:
        if (type(frame) is not dict or set(frame) != {'schema','run_id','launch_sha256','terminal'}
                or frame['schema'] != 'mastermind.paid_model_owned_terminal/v1'
                or frame['run_id'] != launch['run_id']
                # Remote canonical ASCII includes escaped Unicode by contract.
                or frame['launch_sha256'] != hashlib.sha256(json.dumps(launch,
                    sort_keys=True,separators=(',',':'),ensure_ascii=True,
                    allow_nan=False).encode('ascii')).hexdigest()):
            _refuse()
        terminal = frame['terminal']
        required = frozenset('schema label pid pgid started_at ended_at returncode timed_out nice_requested nice_applied stdout_bytes stdout_sha256 stderr_bytes stderr_sha256 stdout_truncated stderr_truncated runtime_failure_code cleanup'.split())
        if (type(terminal) is not dict or set(terminal) != required
                or terminal['label'] != launch['run_id'] or terminal['pid'] != launch['pid']
                or terminal['pgid'] != launch['pid'] or terminal['started_at'] != launch['started_at']
                or type(terminal['returncode']) is not int or terminal['returncode'] != 0
                or terminal['timed_out'] is not False or terminal['stdout_truncated'] is not False
                or terminal['stderr_truncated'] is not False or terminal['runtime_failure_code'] is not None
                or terminal['stderr_bytes'] != 0 or terminal['stderr_sha256'] != _EMPTY
                or type(terminal['stdout_bytes']) is not int or not 0 < terminal['stdout_bytes'] <= 2*1024*1024
                or type(terminal['stdout_sha256']) is not str or not _SHA.fullmatch(terminal['stdout_sha256'])):
            _refuse()
        cleanup = terminal['cleanup']
        # The actual incumbent validator is included in the qualified owner
        # closure; importing it here performs no census or process mutation.
        from ops.native_fabric.quota_continuity.candidate.lane_runtime import cleanup_receipt_is_proven
        if (type(cleanup) is not dict or not cleanup_receipt_is_proven(cleanup)
                or cleanup.get('stdout_capture_complete') is not True
                or cleanup.get('stderr_capture_complete') is not True
                or cleanup.get('stdin_delivery_complete') is not True):
            _refuse()
        return json.loads(canonical(frame))
    except (KeyError,TypeError,ValueError,OverflowError):
        _refuse()


def paid_collection_from_owned_terminal(payload, start, owned_terminal, raw):
    terminal = owned_terminal['terminal']
    if (type(raw) is not bytes or len(raw) != terminal['stdout_bytes']
            or hashlib.sha256(raw).hexdigest() != terminal['stdout_sha256']):
        _refuse()
    try:
        text = raw.decode('utf-8',errors='strict')
        envelope = json.loads(text)
        if type(envelope) is not dict:
            _refuse()
        # Full canonical WorkerResult/role validation remains in Supervisor and
        # Runtime. This original owner preserves exact bytes without repair.
        result = dict(job_id=payload['binding']['job_id'],run_id=payload['binding']['attempt_id'],
            worker_id=payload['launch_spec']['worker_id'],status='SUCCEEDED',
            structured_output=envelope,artifact_manifest=[],git_manifest={},usage={},
            provider_session_id=None,exit_code=0,started_at=start['process_ref']['started_at'],
            finished_at=terminal['ended_at'],error=None)
        return dict(process_ref=start['process_ref'],result=result,
            stdout_sha256=terminal['stdout_sha256'],stderr_sha256=terminal['stderr_sha256'],
            result_sha256=terminal['stdout_sha256'])
    except (ValueError,TypeError,UnicodeError,KeyError):
        _refuse()


def validate_paid_start_wire(result,payload):
    """Control consumer joins its original sealed request, not supplied labels."""
    try:
        physical=require_paid_physical(payload)
        if (type(result) is not dict or set(result)!={'adapter_id','binding','request_sha256',
                'physical_binding_sha256','process_ref','launch_attestation'}
                or result['adapter_id']!=ADAPTER_ID or result['binding']!=payload['binding']
                or result['physical_binding_sha256']!=payload['physical_binding_sha256']):
            _refuse()
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        if result['request_sha256']!=start_request_sha256(payload):_refuse()
        from control_plane.worker_execution_contract import PaidModelProcessRef
        ref=PaidModelProcessRef.from_dict(result['process_ref'])
        data=ref.to_dict()
        expected_paths=Path(physical['capture_root'])/(payload['binding']['attempt_id']+'.paid')
        if (data['run_id']!=payload['binding']['attempt_id']
                or data['worker_id']!=physical['worker_id'] or data['host_ref']!=physical['host_ref']
                or data['binary']!=physical['binary']
                or data['stdout_path']!=str(expected_paths/'stdout')
                or data['stderr_path']!=str(expected_paths/'stderr')
                or data['result_path']!=str(expected_paths/'result.json')):_refuse()
        process=dict(pid=data['pid'],pgid=data['pgid'],session_id=data['session_id'],
            start_identity=data['process_start_identity'],boot_id=data['boot_session_id'],
            launch_nonce=data['launch_nonce'],observed_user=physical['worker_user'],
            **{k:data[k] for k in ('effective_uid','effective_gid','real_uid','real_gid')})
        att=result['launch_attestation']
        lease=att['lease_binding']
        if (lease['orchestrator_id']!=payload['binding']['root_id']
                or lease['account']!=payload['paid_account']
                or lease['host_ref']!=physical['host_ref'] or lease['model']!=physical['model']):_refuse()
        if 'control_start' in payload and (
                lease['runtime_fence_generation']!=payload['control_start']['fence_generation']
                or lease['runtime_pin_version']!=payload['control_start']['pin_version']):_refuse()
        expected=dict(att['evidence'])
        from control_plane.fabric_control_start import launch_identity
        expected.update(python_sha256=physical['binary']['sha256'],
            physical_binding_sha256=payload['physical_binding_sha256'],
            pin_identity_sha256=launch_identity(payload),
            control_input_isolation_manifest_sha256=payload['launch_spec']['isolation_manifest_sha256'],
            **{k:descriptor(payload)[k] for k in ('policy_sha256','prompt_sha256',
                                                  'request_body_sha256','result_schema_sha256')})
        from control_plane.paid_model_execution_principal import validate_paid_model_attestation
        valid=validate_paid_model_attestation(att,expected_binding=payload['binding'],
            expected_route=payload['paid_route'],expected_worker_id=physical['worker_id'],
            expected_quota_class=payload['paid_quota_class'],expected_process=process,
            expected_lease_binding=lease,expected_evidence=expected)
        return ref,valid
    except (ValueError,TypeError,KeyError,AttributeError):_refuse()
