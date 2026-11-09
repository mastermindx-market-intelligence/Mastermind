"""Closed DATA compiler for the canonical paid sealed-input analysis surface.

Compiler output grants nothing. The actual Control peer, Runtime pin, current
Capacity claim and paid lease owner must independently authorize consumption.
READ/RESEARCH describe analysis of supplied text; no file/web acquisition tool
is exposed. Provider inference transport is separate from model tool authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

PROFILE_ID = 'fabric.paid.glm.sealed-input.v1'
ADAPTER_ID = 'canonical-paid-fabric'
EXECUTION_SURFACE = 'glm-model-only'
ATTESTATION_SCHEMA = 'mastermind.executive_paid_model_launch_attestation/v1'
POLICY = {
    'schema': 'mastermind.paid_model_only_policy/v1',
    'profile_id': PROFILE_ID,
    'input_policy': 'sealed-supplied-text-only',
    'model_tools': [], 'functions': [], 'mcp_servers': [], 'hooks': [],
    'plugins': [], 'subagents': [], 'filesystem_tools': [], 'network_tools': [],
    'provider_transport': 'incumbent-lease-bound-glm-shim',
    'request_keys': ['input', 'max_output_tokens', 'model', 'stream'],
    'max_output_tokens': 8192, 'stream': False,
}
MAX_INPUT_BYTES = 1024 * 1024
MAX_SCHEMA_BYTES = 256 * 1024
MODELS = frozenset({'glm-5.3', 'glm-5.3-flash'})
_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')


class PaidModelContractRefused(ValueError):
    pass


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PaidModelContractRefused('paid_model_contract_invalid') from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def compile_request(payload):
    """Validate inert exact input and return bytes; never read a supplied path."""
    try:
        if (type(payload) is not dict or not {
                'binding', 'physical_binding_sha256', 'launch_spec',
                'validation_commands', 'paid_route', 'paid_input'} <= set(payload)
                or set(payload) - {'binding', 'physical_binding_sha256', 'launch_spec',
                'validation_commands', 'paid_route', 'paid_input', 'control_start',
                'start_request_sha256', 'control_recovery', 'paid_physical_binding', 'paid_source_config', 'paid_account', 'paid_quota_class'}
                or type(payload['physical_binding_sha256']) is not str
                or not _DIGEST.fullmatch(payload['physical_binding_sha256'])):
            raise ValueError
        binding = payload['binding']
        if (type(binding) is not dict or set(binding) != {
                'root_id', 'job_id', 'attempt_id', 'effective_grant_digest', 'commission_sha256'}
                or any(type(binding[k]) is not str or not _ID.fullmatch(binding[k])
                       for k in ('root_id', 'job_id', 'attempt_id'))
                or any(type(binding[k]) is not str or not _DIGEST.fullmatch(binding[k])
                       for k in ('effective_grant_digest', 'commission_sha256'))):
            raise ValueError
        spec, route, supplied = (payload[k] for k in ('launch_spec', 'paid_route', 'paid_input'))
        if (type(spec) is not dict or type(route) is not dict or type(supplied) is not dict
                or set(route) != {'provider', 'host_ref', 'model', 'parent_job_id'}
                or set(supplied) != {'prompt', 'result_schema'}
                or route['provider'] != 'glm' or route['model'] not in MODELS
                or type(route['host_ref']) is not str or not _ID.fullmatch(route['host_ref'])
                or (route['parent_job_id'] is None and binding['job_id'] != binding['root_id'])
                or (route['parent_job_id'] is not None and (
                    type(route['parent_job_id']) is not str
                    or not _ID.fullmatch(route['parent_job_id'])))
                or type(spec.get('timeout_seconds')) not in (int, float)
                or not math.isfinite(spec['timeout_seconds'])
                or not 0 < spec['timeout_seconds'] <= 7200
                or spec.get('model') != route['model']
                or spec.get('job_id') != binding['job_id']
                or spec.get('run_id') != binding['attempt_id']
                or spec.get('effective_grant_digest') != binding['effective_grant_digest']
                or supplied['prompt'] != spec.get('prompt')
                or type(supplied['prompt']) is not str or not supplied['prompt']
                or '\x00' in supplied['prompt']
                or len(supplied['prompt'].encode('utf-8')) > MAX_INPUT_BYTES
                or type(supplied['result_schema']) is not dict
                or not supplied['result_schema']
                or len(canonical(supplied['result_schema'])) > MAX_SCHEMA_BYTES):
            raise ValueError
        authorities = spec.get('authorities')
        # Adapted from the returned paid-read policy leaf's exact plural grant
        # check. No scalar authority compatibility or prompt-derived grant.
        if (type(authorities) is not list or any(type(v) is not str for v in authorities)
                or len(authorities) != len(set(authorities))
                or set(authorities) not in ({'READ'}, {'READ', 'RESEARCH'})
                or spec.get('authority') is not None
                or spec.get('allowed_artifact_paths') not in ([], ())
                or payload.get('validation_commands') != []):
            raise ValueError
        body = {'model': route['model'], 'input': supplied['prompt']
                + '\n\nRESULT_SCHEMA_JSON:\n'
                + canonical(supplied['result_schema']).decode('utf-8'),
                'stream': False, 'max_output_tokens': 8192}
        raw = canonical(body)
        if len(body['input'].encode('utf-8')) > MAX_INPUT_BYTES or len(raw) > 2 * 1024 * 1024:
            raise ValueError
        return raw
    except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        raise PaidModelContractRefused('paid_model_contract_refused') from None


def descriptor(payload):
    body = compile_request(payload)
    return {
        'schema': 'mastermind.paid_model_execution_descriptor/v1',
        'profile_id': PROFILE_ID, 'execution_surface': EXECUTION_SURFACE,
        'policy_sha256': digest(POLICY),
        'request_body_sha256': hashlib.sha256(body).hexdigest(),
        'result_schema_sha256': digest(payload['paid_input']['result_schema']),
        'prompt_sha256': hashlib.sha256(payload['paid_input']['prompt'].encode()).hexdigest(),
        'binding': dict(payload['binding']), 'paid_route': dict(payload['paid_route']),
        'physical_binding_sha256': payload['physical_binding_sha256'],
    }


PAID_REGISTRY_NAMESPACE='/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/hosts.json'


def paid_host_reference(registry_key,transport_alias):
    """Stable identity DATA; never host proof, capacity or independence."""
    import re
    if any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',v) is None
           for v in (registry_key,transport_alias)):
        raise PaidModelContractRefused('paid_model_contract_refused')
    return 'host-'+digest(dict(schema='mastermind.canonical_paid_host_reference/v1',
        registry_namespace=PAID_REGISTRY_NAMESPACE,registry_key=registry_key,
        transport_alias=transport_alias))
