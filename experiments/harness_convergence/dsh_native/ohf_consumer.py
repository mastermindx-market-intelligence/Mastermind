"""Private N0 observation intake into existing OHF. No runtime authority or I/O.

The native binding and host observation MUST come from the owning admitted
process/materialization boundary, not from this JSON document. This pure
experiment can validate their relationship; it does not authenticate origin.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import re
from typing import Any
from control_plane.operator_harness_contract import (
    ObservedCapabilityIdentity, ObservedHarnessAttestation, RequestedExecutionProfile,
    LaunchComparison, AuthRealmRequirement, compare_launch, first_work_turn_allowed,
)
from control_plane.operator_harness_wire import OperatorHarnessWireError
from scripts.agent_eval.privacy import assert_public_safe_evidence

UPSTREAM_COMMIT = '0d1f50007f9bca3f52b06e1c3074fa14d5fb0720'
MAX_BYTES = 65536
_EXTENSION_POLICY = 'N0_CLOSED_FIXTURE_NO_EXTERNAL_CAPABILITIES'
_DIGEST = re.compile(r'^sha256:[a-f0-9]{64}$')
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:@/\-]{0,191}$')

class NativeObservationError(OperatorHarnessWireError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

def _refuse(code: str) -> None:
    raise NativeObservationError(code)

@dataclasses.dataclass(frozen=True)
class NativeBinding:
    """Ephemeral, separately supplied owner expectation. Not a stored identity plane."""
    attempt_id: str
    worker_id: str
    process_generation_id: str
    native_session_id: str
    recipe_digest: str
    tools: tuple[tuple[str, str, str], ...]  # name, schema digest, implementation digest
    modules: tuple[tuple[str, str, str], ...]  # entry id, module specifier, module digest

    def __post_init__(self) -> None:
        if any(type(v) is not str or not _ID.fullmatch(v) for v in (self.attempt_id,self.worker_id,self.process_generation_id,self.native_session_id)):
            _refuse('OWNER_BINDING_INVALID')
        if type(self.recipe_digest) is not str or not _DIGEST.fullmatch(self.recipe_digest):
            _refuse('OWNER_BINDING_INVALID')
        # Frozen dataclasses alone would retain mutable nested aliases.
        for name, limit in [('tools',64),('modules',128)]:
            rows=getattr(self,name)
            if type(rows) is not tuple or not 1<=len(rows)<=limit or any(type(row) is not tuple or len(row)!=3 or any(type(v) is not str for v in row) for row in rows):
                _refuse('OWNER_BINDING_INVALID')
            if len({r[0] for r in rows})!=len(rows):_refuse('OWNER_BINDING_INVALID')
            for row in rows:
                if not _ID.fullmatch(row[0]) or not _DIGEST.fullmatch(row[2]):_refuse('OWNER_BINDING_INVALID')
                if name=='tools' and not _DIGEST.fullmatch(row[1]):_refuse('OWNER_BINDING_INVALID')

@dataclasses.dataclass(frozen=True)
class NativeComparison:
    launch: LaunchComparison
    comparator_allows: bool
    observation_digest: str
    evidence_scope: str = 'N0_SOURCE_CONFORMANCE'
    first_work_started: bool = False


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str,Any]={}
    for key,value in pairs:
        if key in result:_refuse('DUPLICATE_JSON_KEY')
        result[key]=value
    return result


def _validate_tree(value: Any) -> None:
    nodes=0
    def walk(v: Any, depth: int) -> None:
        nonlocal nodes
        nodes+=1
        if depth>32 or nodes>4096:_refuse('OBSERVATION_LIMIT')
        if v is None or type(v) is bool:return
        if type(v) is str:
            if len(v)>8192 or any(0xD800<=ord(c)<=0xDFFF for c in v):_refuse('OBSERVATION_LIMIT')
        elif type(v) is int:
            if abs(v)>2**53-1:_refuse('OBSERVATION_SHAPE')
        elif type(v) is list:
            if len(v)>128:_refuse('OBSERVATION_LIMIT')
            for item in v:walk(item,depth+1)
        elif type(v) is dict:
            if len(v)>128:_refuse('OBSERVATION_LIMIT')
            for key,item in v.items():
                if not re.fullmatch(r'[\x20-\x7e]{1,128}',key) or key in {'__proto__','prototype','constructor'}:_refuse('OBSERVATION_SHAPE')
                walk(item,depth+1)
        else:_refuse('OBSERVATION_SHAPE')
    walk(value,0)


def _shape(value: Any, keys: set[str]) -> None:
    if type(value) is not dict or set(value)!=keys:_refuse('OBSERVATION_SHAPE')

def _hash(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    return 'sha256:'+hashlib.sha256(raw).hexdigest()


def compareNativeObservation(
    payload: bytes, *, binding: NativeBinding, requested: RequestedExecutionProfile,
    host_observation: ObservedHarnessAttestation,
) -> NativeComparison:
    """Return existing gate evidence only. Never starts work or accepts an ALLOW field."""
    if type(payload) is not bytes or len(payload)>MAX_BYTES:_refuse('OBSERVATION_LIMIT')
    if type(binding) is not NativeBinding or type(requested) is not RequestedExecutionProfile or type(host_observation) is not ObservedHarnessAttestation:
        _refuse('OWNER_BINDING_INVALID')
    try:
        value=json.loads(payload.decode('utf-8'),object_pairs_hook=_pairs,
                         parse_constant=lambda _value:_refuse('OBSERVATION_SHAPE'))
        _validate_tree(value)
        assert_public_safe_evidence(value)
    except NativeObservationError:raise
    except Exception:raise NativeObservationError('OBSERVATION_INVALID') from None
    _shape(value,{'format','upstream_commit','binding','recipe_digest','extension_policy','presentation','model','tools','composition'})
    if value['format']!='dsh-native-observation/n0' or value['upstream_commit']!=UPSTREAM_COMMIT or value['extension_policy']!=_EXTENSION_POLICY or value['presentation']!='native':
        _refuse('OBSERVATION_PROFILE_MISMATCH')
    expected_binding={key:getattr(binding,key) for key in ['attempt_id','worker_id','process_generation_id','native_session_id']}
    if value['binding']!=expected_binding or value['recipe_digest']!=binding.recipe_digest:
        _refuse('OBSERVATION_IDENTITY_MISMATCH')
    # Required host unknowns must not be erased by replacing native inventories.
    required_unknowns={'served_model','harness_binary_digest','workspace','sandbox_state','approval_state','network_state','capabilities','effective_skills','effective_mcp','effective_plugins_or_apps'}
    if requested.expected_config_digest:
        required_unknowns.add('effective_config_digest')
    if requested.auth_realm_requirement is AuthRealmRequirement.VERIFIED_PROVIDER_ACCOUNT:
        required_unknowns.add('provider_account_id')
    if required_unknowns.intersection(host_observation.unknown_fields):_refuse('HOST_OBSERVATION_INCOMPLETE')
    if requested.worker_id!=binding.worker_id or host_observation.auth.worker_id!=binding.worker_id or host_observation.auth.provider!=requested.provider:
        _refuse('HOST_IDENTITY_MISMATCH')
    model=value['model'];_shape(model,{'provider','model','reasoning_effort','max_tokens'})
    if type(model['provider']) is not str or model['provider']!=requested.provider or type(model['model']) is not str or not _ID.fullmatch(model['model']):
        _refuse('MODEL_OBSERVATION_INVALID')
    if model['reasoning_effort'] is not None and (type(model['reasoning_effort']) is not str or not _ID.fullmatch(model['reasoning_effort'])):_refuse('MODEL_OBSERVATION_INVALID')
    if model['max_tokens'] is not None and (type(model['max_tokens']) is not int or not 0<model['max_tokens']<=2**53-1):_refuse('MODEL_OBSERVATION_INVALID')
    tools=value['tools'];composition=value['composition']
    if type(tools) is not list or len(tools)!=len(binding.tools) or len(tools)>64:_refuse('TOOL_CENSUS_MISMATCH')
    if type(composition) is not list or len(composition)!=len(binding.modules):_refuse('COMPOSITION_MISMATCH')
    capabilities=[]
    for row,expected in zip(tools,binding.tools):
        _shape(row,{'name','description','parameters','implementation_digest'})
        if type(row['name']) is not str or not _ID.fullmatch(row['name']) or row['name']=='run_code' or type(row['description']) is not str or type(row['parameters']) is not dict:_refuse('TOOL_SCHEMA_INVALID')
        schema_digest=_hash({k:row[k] for k in ['name','description','parameters']})
        if (row['name'],schema_digest,row['implementation_digest'])!=expected:_refuse('TOOL_IDENTITY_MISMATCH')
        capabilities.append(ObservedCapabilityIdentity(kind='tool',name=row['name'],tool_schema_digest=schema_digest))
    for row,expected in zip(composition,binding.modules):
        _shape(row,{'entry_id','module','module_digest'})
        if (row['entry_id'],row['module'],row['module_digest'])!=expected:_refuse('COMPOSITION_MISMATCH')
    # Empty extension inventories are authorized only for this exact separately
    # bound N0 fixture recipe, never inferred from absent wire fields. Non-empty
    # host observations cannot be overwritten to launder ambient extensions.
    if host_observation.capabilities or host_observation.effective_mcp or host_observation.effective_skills or host_observation.effective_plugins_or_apps:
        _refuse('HOST_EXTENSION_CONFLICT')
    # Backend-private configuration identity is measured from the admitted native
    # projection, not filled from an expected value or host-side config echo.
    # Binding/session IDs are deliberately excluded: configuration is not lifecycle.
    native_config_digest=_hash({k:value[k] for k in (
        'upstream_commit','recipe_digest','presentation','extension_policy',
        'model','tools','composition',
    )})
    observed=dataclasses.replace(host_observation,served_model=model['model'],capabilities=tuple(capabilities),
        effective_config_digest=native_config_digest,
        effective_skills=(),effective_mcp=(),effective_plugins_or_apps=())
    launch=compare_launch(requested,observed)
    return NativeComparison(launch=launch,comparator_allows=first_work_turn_allowed(launch.decision),observation_digest=_hash(value))
