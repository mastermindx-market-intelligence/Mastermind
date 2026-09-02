"""Frozen, SDK-free contract for the six Secretary grounding reads.

This module contains data shapes and validation only. It deliberately imports
neither an MCP SDK nor any canonical owner, transport, provider, browser, host,
or persistence implementation.
"""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any
SERVER_NAME = 'mastermind-secretary-grounding'
SERVER_IDENTITY = 'mastermind-secretary-grounding-mcp'
SERVER_VERSION = '1.0.0'
RESULT_SCHEMA = 'mastermind.secretary_grounding_mcp_result.v1'
MAX_REQUEST_BYTES = 8 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RESPONSIBILITY_REF_CHARS = 160
MAX_FACTS = 64
MAX_SOURCES_PER_FACT = 8
MAX_REASON_CODES = 16
ERROR_CODES = frozenset({'INVALID_REQUEST', 'STEWARD_UNAVAILABLE', 'GROUNDING_REFUSED', 'RESPONSE_REFUSED', 'INTERNAL_ERROR'})
GROUNDING_STATES = frozenset({'FACTS', 'UNKNOWN', 'DEGRADED', 'REFUSED'})
FRESHNESS_STATES = frozenset({'FRESH', 'STALE', 'UNKNOWN'})
GROUNDING_REASON_CODES = frozenset({'AMBIGUOUS_JOIN', 'DENIED', 'DEPENDENCY_UNAVAILABLE', 'EFFECT_UNKNOWN', 'NO_SOURCE', 'POLICY_REFUSAL', 'RESPONSIBILITY_UNKNOWN', 'RUNTIME_UNKNOWN', 'STALE_SOURCE', 'STEWARD_DEGRADED', 'SURFACE_UNKNOWN'})
SOURCE_NAMESPACE_BY_OWNER = MappingProxyType({'agent_os': ('WS', 'DEC', 'DSC'), 'executive_os': ('JOB', 'ATTEMPT', 'WORKER', 'EVENT', 'EXEC'), 'runtime_binding': ('RUNTIME',), 'executive_inbox': ('EIA',), 'capacity': ('CAPACITY',), 'wake': ('WAKE',), 'agent_dialogue': ('DIALOGUE',), 'surface_binding': ('SURFACE',), 'surface_bindings': ('SURFACE',), 'provider_control': ('POLICY',), 'unknown': ('UNKNOWN',)})
SOURCE_OWNERS = frozenset(SOURCE_NAMESPACE_BY_OWNER)
_CANONICAL_CREDENTIAL_PREFIX = '(?:sb_secret_|sb_publishable_|sbp_|sk-ant-|sk-|github_pat_|ghp_|gho_|ghs_|xox[abeprs]-|xapp-|eyJ|AKIA|ASIA|ABIA|ACCA)'
_CANONICAL_CREDENTIAL_FENCE = f'(?!{_CANONICAL_CREDENTIAL_PREFIX})(?![A-Za-z0-9._-]*[._-]{_CANONICAL_CREDENTIAL_PREFIX})'
_CREDENTIAL_ANY_GUARD = f'(?!.*(?:^|[^A-Za-z0-9]){_CANONICAL_CREDENTIAL_PREFIX})'
_ABSOLUTE_END = r'(?![\s\S])'
_RESPONSIBILITY_REF_PATTERN = f'^responsibility:{_CANONICAL_CREDENTIAL_FENCE}[a-z0-9][a-z0-9._-]{{0,144}}{_ABSOLUTE_END}'
_RESPONSIBILITY_REF_RE = re.compile(rf'\Aresponsibility:{_CANONICAL_CREDENTIAL_FENCE}[a-z0-9][a-z0-9._-]{{0,144}}\Z')
_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f]')
_EMAIL_PATTERN = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
_URL_PATTERN = '://'
_PRIVATE_PATH_PATTERN = r'(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Za-z]:\\)'
_SECRET_LABEL_PATTERN = r'\b(?:[Bb]earer|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]|[Tt]oken|[Ss]ecret|[Pp]assword)\s*[:=]'
_PRIVATE_LOCATOR_KEY_PATTERN = '(?:[Pp]rovider(?:_session)?|[Nn]ative_(?:session|handle)|[Aa]ccount(?:_id)?|[Bb]rowser_profile|[Pp]rofile_id|[Hh]ost|[Cc]hannel|[Tt]hread|[Cc]oordinates|[Pp]id|[Pp]gid|[Aa]ction|[Tt]arget)'
_PRIVATE_LOCATOR_PATTERN = rf'\b{_PRIVATE_LOCATOR_KEY_PATTERN}\s*[:=]\s*\S+'
_EMAIL_RE = re.compile(_EMAIL_PATTERN)
_URL_RE = re.compile(_URL_PATTERN)
_PRIVATE_PATH_RE = re.compile(_PRIVATE_PATH_PATTERN)
_SECRET_RE = re.compile(f'(?:^|[^A-Za-z0-9]){_CANONICAL_CREDENTIAL_PREFIX}|-----BEGIN [A-Z ]*PRIVATE KEY-----|{_SECRET_LABEL_PATTERN}')
_PRIVATE_LOCATOR_RE = re.compile(_PRIVATE_LOCATOR_PATTERN)
_HEX_SECRET_RE = re.compile(r'\b[A-Fa-f0-9]{32,}\b')
_HIGH_ENTROPY_RE = re.compile(r'\b(?=[A-Za-z0-9]{32,}\b)(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]+\b')
_PUBLIC_TEXT_PATTERN = rf'^(?=\S(?:.*\S)?$)(?!.*[\x00-\x1f\x7f])(?!.*{_URL_PATTERN})(?!.*{_EMAIL_PATTERN})(?!.*{_PRIVATE_PATH_PATTERN}){_CREDENTIAL_ANY_GUARD}(?!.*{_SECRET_LABEL_PATTERN})(?!.*-----BEGIN [A-Z ]*PRIVATE KEY-----)(?!.*{_PRIVATE_LOCATOR_PATTERN})(?!.*\b[A-Fa-f0-9]{{32,}}\b)(?!.*\b(?=[A-Za-z0-9]{{32,}}\b)(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]+\b).+{_ABSOLUTE_END}'
_PUBLIC_TOKEN_PATTERN = f'^{_CREDENTIAL_ANY_GUARD}[A-Za-z0-9][A-Za-z0-9._-]{{0,95}}{_ABSOLUTE_END}'
_PUBLIC_TOKEN_RE = re.compile(_PUBLIC_TOKEN_PATTERN)
_SAFE_REF_TOKEN = '[A-Za-z0-9][A-Za-z0-9._-]{0,223}'
_SAFE_RECEIPT_TOKEN = '[A-Za-z0-9][A-Za-z0-9._-]{0,223}'
_UUID_PATTERN = '[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[1-5][0-9A-Fa-f]{3}-[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}'

def _guarded_pattern(body: str) -> str:
    return f'^{_CREDENTIAL_ANY_GUARD}{body}{_ABSOLUTE_END}'
_WORK_ID_PATTERN = _guarded_pattern(f'WS:{_SAFE_REF_TOKEN}')
_ATTENTION_ID_PATTERN = _guarded_pattern(f'(?:(?:EVENT|EXEC|WAKE|DIALOGUE):{_SAFE_REF_TOKEN}|[A-Za-z][A-Za-z0-9._-]{{0,223}})')
_JOB_ID_PATTERN = _guarded_pattern(f'JOB-{_SAFE_REF_TOKEN}')
_ATTEMPT_ID_PATTERN = _guarded_pattern(f'ATT-{_SAFE_REF_TOKEN}')
_WORKER_ID_PATTERN = _guarded_pattern('[A-Za-z][A-Za-z0-9._-]{0,223}')
_BINDING_ID_PATTERN = _guarded_pattern('[A-Za-z][A-Za-z0-9._-]{0,223}')
_SURFACE_ID_PATTERN = _guarded_pattern(f'(?:SURFACE:{_SAFE_REF_TOKEN}|{_UUID_PATTERN})')
_PUBLIC_REFERENCE_PATTERN = _guarded_pattern(f'(?:(?:WS|DEC|DSC|JOB|ATTEMPT|WORKER|EVENT|EXEC|RUNTIME|CAPACITY|WAKE|DIALOGUE|SURFACE|POLICY):{_SAFE_REF_TOKEN}|JOB-{_SAFE_REF_TOKEN}|ATT-{_SAFE_REF_TOKEN}|{_UUID_PATTERN}|[A-Za-z][A-Za-z0-9._-]{{0,223}})')
# One producer vocabulary per owner. Every accepted source_ref form is built
# from these tables, so the advertised grammar and the runtime validator cannot
# drift apart. Frozen namespaces are the reviewed public identity vocabulary;
# receipt bodies are the producer-native provenance vocabulary. The two are
# advertised separately and are never conflated.
_NATIVE_SOURCE_BODY_BY_OWNER = {
    'agent_os': rf'(?:agentos/workstreams/(?!.*(?:/\.\.?/|/\.\.?$))[A-Za-z0-9][A-Za-z0-9._/-]{{0,220}})',
    'executive_os': rf'executive-(?:runtime|event|job|attempt|worker):{_SAFE_RECEIPT_TOKEN}',
    'runtime_binding': rf'runtime-binding:{_SAFE_RECEIPT_TOKEN}',
    'executive_inbox': rf'executive-inbox:{_SAFE_RECEIPT_TOKEN}',
    'capacity': rf'capacity:{_SAFE_RECEIPT_TOKEN}',
    'wake': rf'wake:{_SAFE_RECEIPT_TOKEN}',
    'agent_dialogue': rf'agent-dialogue:{_SAFE_RECEIPT_TOKEN}',
    'surface_binding': None,
    'surface_bindings': rf'surface-binding:(?:{_UUID_PATTERN}|{_SAFE_RECEIPT_TOKEN})',
    'provider_control': None,
    'unknown': None,
}

def _owner_source_pattern(owner: str) -> str:
    """Accept the frozen namespace vocabulary and this owner's native receipts."""
    alternatives = [f'(?:{"|".join(SOURCE_NAMESPACE_BY_OWNER[owner])}):{_SAFE_REF_TOKEN}']
    native = _NATIVE_SOURCE_BODY_BY_OWNER[owner]
    if native is not None:
        alternatives.append(native)
    return _guarded_pattern(f'(?:{"|".join(alternatives)})')
_SOURCE_REF_PATTERN_BY_OWNER = MappingProxyType({owner: _owner_source_pattern(owner) for owner in SOURCE_NAMESPACE_BY_OWNER})
_SOURCE_REF_RE_BY_OWNER = MappingProxyType({owner: re.compile(pattern) for owner, pattern in _SOURCE_REF_PATTERN_BY_OWNER.items()})
_LEAP_YEAR = '(?:[0-9]{2}(?:0[48]|[2468][048]|[13579][26])|(?:0[48]|[2468][048]|[13579][26])00)'
_TIMESTAMP_PATTERN = f'^(?!0000-)(?:[0-9]{{4}}-(?:(?:01|03|05|07|08|10|12)-(?:0[1-9]|[12][0-9]|3[01])|(?:04|06|09|11)-(?:0[1-9]|[12][0-9]|30)|02-(?:0[1-9]|1[0-9]|2[0-8]))|{_LEAP_YEAR}-02-29)T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z{_ABSOLUTE_END}'
_TIMESTAMP_RE = re.compile(_TIMESTAMP_PATTERN)

class GatewayError(RuntimeError):
    """One fixed Secretary gateway refusal."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError('unknown Secretary gateway error code')
        super().__init__(code)
        self.code = code

def _string(*, max_length: int, pattern: str | None=None) -> dict[str, Any]:
    value: dict[str, Any] = {'type': 'string', 'maxLength': max_length}
    if pattern is None:
        value['minLength'] = 1
    else:
        value['pattern'] = pattern
    return value

def _object(properties: Mapping[str, Any], *, required: tuple[str, ...]=()) -> dict[str, Any]:
    value: dict[str, Any] = {'type': 'object', 'properties': dict(properties), 'additionalProperties': False}
    if required:
        value['required'] = list(required)
    return value

def _normalize_public_text(value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or value != value.strip() or _CONTROL_RE.search(value) or _EMAIL_RE.search(value) or _URL_RE.search(value) or _PRIVATE_PATH_RE.search(value) or _SECRET_RE.search(value) or _PRIVATE_LOCATOR_RE.search(value) or _HEX_SECRET_RE.search(value) or _HIGH_ENTROPY_RE.search(value):
        raise GatewayError('RESPONSE_REFUSED')
    return value

def _normalize_pattern(value: Any, maximum: int, pattern: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or value != value.strip() or _CONTROL_RE.search(value) or (re.fullmatch(pattern, value) is None):
        raise GatewayError('RESPONSE_REFUSED')
    return value

@dataclasses.dataclass(frozen=True)
class _PublicFactContract:
    """One reviewed public predicate and its only representable value language."""
    predicate: str
    value_kind: str
    enum_values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    reference_namespaces: tuple[str, ...] = ()
    corroborating_owners: tuple[str, ...] = ()
    pattern: str | None = None
    enum_aliases: tuple[tuple[str, str], ...] = ()

    @property
    def value_schema(self) -> dict[str, Any]:
        if self.value_kind == 'enum':
            return {'type': 'string', 'enum': list(self.enum_values)}
        if self.value_kind == 'boolean':
            return {'type': 'boolean'}
        if self.value_kind == 'integer':
            return {'type': 'integer', 'minimum': self.minimum, 'maximum': self.maximum}
        if self.value_kind == 'text':
            return _string(max_length=int(self.max_length or 1), pattern=_PUBLIC_TEXT_PATTERN)
        if self.value_kind in {'token', 'reference'}:
            return _string(max_length=int(self.max_length or 256), pattern=str(self.pattern or _PUBLIC_TOKEN_PATTERN))
        raise RuntimeError('unsupported public fact contract')

    def normalize(self, value: Any) -> str | int | bool:
        if self.value_kind == 'enum':
            if isinstance(value, str):
                if value in self.enum_values:
                    return value
                for alias, canonical in self.enum_aliases:
                    if value == alias:
                        return canonical
        elif self.value_kind == 'boolean':
            if isinstance(value, bool):
                return value
        elif self.value_kind == 'integer':
            if isinstance(value, int) and (not isinstance(value, bool)) and (self.minimum is not None) and (self.maximum is not None) and (self.minimum <= value <= self.maximum):
                return value
        elif self.value_kind == 'text':
            return _normalize_public_text(value, int(self.max_length or 0))
        elif self.value_kind in {'token', 'reference'}:
            return _normalize_pattern(value, int(self.max_length or 256), str(self.pattern or _PUBLIC_TOKEN_PATTERN))
        raise GatewayError('RESPONSE_REFUSED')
_AGENT_OS = ('agent_os',)
_ATTENTION_OWNERS = ('executive_inbox', 'wake', 'executive_os', 'agent_dialogue', 'agent_os')
_EXECUTIVE_OS = ('executive_os',)
_RUNTIME_BINDING = ('runtime_binding',)
_CAPACITY = ('capacity',)
_BLOCKER_OWNERS = ('agent_os', 'executive_os', 'executive_inbox', 'wake', 'runtime_binding', 'capacity', 'surface_binding', 'surface_bindings', 'provider_control')
_SURFACE_OWNERS = ('surface_binding', 'surface_bindings')
_FACT_CONTRACT_ROWS = (_PublicFactContract('responsibility.identity', 'reference', max_length=256, reference_namespaces=('WS',), corroborating_owners=_AGENT_OS, pattern=_WORK_ID_PATTERN), _PublicFactContract('responsibility.title', 'text', max_length=160, corroborating_owners=_AGENT_OS), _PublicFactContract('responsibility.accountable_seat', 'enum', ('CHAIRMAN', 'CEO', 'COO', 'WORKER'), corroborating_owners=_AGENT_OS, enum_aliases=(('chairman', 'CHAIRMAN'), ('ceo', 'CEO'), ('coo', 'COO'), ('worker', 'WORKER'))), _PublicFactContract('responsibility.objective', 'text', max_length=480, corroborating_owners=_AGENT_OS), _PublicFactContract('responsibility.next_action', 'text', max_length=480, corroborating_owners=_AGENT_OS), _PublicFactContract('responsibility.state', 'token', max_length=96, corroborating_owners=_AGENT_OS, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('responsibility.priority', 'integer', minimum=0, maximum=100, corroborating_owners=_AGENT_OS), _PublicFactContract('responsibility.requires_attention', 'boolean', corroborating_owners=_ATTENTION_OWNERS), _PublicFactContract('attention.ref', 'reference', max_length=256, corroborating_owners=_ATTENTION_OWNERS, pattern=_ATTENTION_ID_PATTERN), _PublicFactContract('attention.target_seat', 'enum', ('CHAIRMAN', 'CEO', 'COO', 'WORKER'), corroborating_owners=_ATTENTION_OWNERS, enum_aliases=(('chairman', 'CHAIRMAN'), ('ceo', 'CEO'), ('coo', 'COO'), ('worker', 'WORKER'), ('SOL', 'CEO'))), _PublicFactContract('attention.kind', 'token', max_length=96, corroborating_owners=_ATTENTION_OWNERS, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('attention.reason', 'text', max_length=320, corroborating_owners=_ATTENTION_OWNERS), _PublicFactContract('attention.requested_action', 'text', max_length=320, corroborating_owners=_ATTENTION_OWNERS), _PublicFactContract('attention.state', 'enum', ('CHAIRMAN_REQUIRED', 'COO_REQUIRED', 'EXTERNAL_REQUIRED', 'NONE', 'SOL_REQUIRED', 'UNKNOWN'), corroborating_owners=_ATTENTION_OWNERS), _PublicFactContract('runtime.job_ref', 'reference', max_length=256, reference_namespaces=('JOB',), corroborating_owners=_EXECUTIVE_OS, pattern=_JOB_ID_PATTERN), _PublicFactContract('runtime.attempt_ref', 'reference', max_length=256, reference_namespaces=('ATTEMPT',), corroborating_owners=_EXECUTIVE_OS, pattern=_ATTEMPT_ID_PATTERN), _PublicFactContract('runtime.worker_ref', 'reference', max_length=256, reference_namespaces=('WORKER',), corroborating_owners=_EXECUTIVE_OS, pattern=_WORKER_ID_PATTERN), _PublicFactContract('runtime.binding_ref', 'reference', max_length=256, reference_namespaces=('RUNTIME',), corroborating_owners=_RUNTIME_BINDING, pattern=_BINDING_ID_PATTERN), _PublicFactContract('runtime.state', 'token', max_length=96, corroborating_owners=_EXECUTIVE_OS, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('runtime.effect_state', 'enum', ('NONE', 'APPLIED', 'EFFECT_UNKNOWN'), corroborating_owners=_EXECUTIVE_OS, enum_aliases=(('none', 'NONE'), ('applied', 'APPLIED'), ('effect_unknown', 'EFFECT_UNKNOWN'))), _PublicFactContract('runtime.continuation', 'token', max_length=96, corroborating_owners=_RUNTIME_BINDING, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('runtime.capacity_state', 'enum', ('AVAILABLE', 'DEGRADED', 'UNKNOWN'), corroborating_owners=_CAPACITY, enum_aliases=(('available', 'AVAILABLE'), ('degraded', 'DEGRADED'), ('unknown', 'UNKNOWN'))), _PublicFactContract('runtime.age_seconds', 'integer', minimum=0, maximum=31536000, corroborating_owners=('executive_os', 'runtime_binding')), _PublicFactContract('blocker.kind', 'token', max_length=96, corroborating_owners=_BLOCKER_OWNERS, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('blocker.present', 'boolean', corroborating_owners=_BLOCKER_OWNERS), _PublicFactContract('blocker.explanation', 'text', max_length=480, corroborating_owners=_BLOCKER_OWNERS), _PublicFactContract('blocker.dependency_ref', 'reference', max_length=256, corroborating_owners=_BLOCKER_OWNERS, pattern=_PUBLIC_REFERENCE_PATTERN), _PublicFactContract('blocker.action_ref', 'reference', max_length=256, corroborating_owners=_BLOCKER_OWNERS, pattern=_PUBLIC_REFERENCE_PATTERN), _PublicFactContract('surface.ref', 'reference', max_length=256, reference_namespaces=('SURFACE',), corroborating_owners=_SURFACE_OWNERS, pattern=_SURFACE_ID_PATTERN), _PublicFactContract('surface.locator_kind', 'token', max_length=96, corroborating_owners=_SURFACE_OWNERS, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('surface.review_state', 'enum', ('APPROVED', 'PENDING', 'REJECTED', 'UNKNOWN'), corroborating_owners=_SURFACE_OWNERS, enum_aliases=(('approved', 'APPROVED'), ('pending', 'PENDING'), ('rejected', 'REJECTED'), ('unknown', 'UNKNOWN'))), _PublicFactContract('surface.health', 'token', max_length=96, corroborating_owners=_SURFACE_OWNERS, pattern=_PUBLIC_TOKEN_PATTERN), _PublicFactContract('surface.repair_required', 'boolean', corroborating_owners=_SURFACE_OWNERS), _PublicFactContract('surface.observation_age_seconds', 'integer', minimum=0, maximum=31536000, corroborating_owners=_SURFACE_OWNERS))
PUBLIC_FACT_CONTRACTS = MappingProxyType({contract.predicate: contract for contract in _FACT_CONTRACT_ROWS})
_PUBLIC_FACTS_BY_PREDICATE = PUBLIC_FACT_CONTRACTS
_PREDICATE_ORDER = {predicate: index for index, predicate in enumerate(PUBLIC_FACT_CONTRACTS)}
TOOL_REQUIRED_PREDICATES = MappingProxyType({'list_responsibilities': frozenset({'responsibility.identity', 'responsibility.title', 'responsibility.state', 'responsibility.next_action'}), 'get_responsibility': frozenset({'responsibility.identity', 'responsibility.title', 'responsibility.objective', 'responsibility.next_action', 'responsibility.state'}), 'get_attention': frozenset({'attention.ref', 'attention.reason', 'attention.requested_action', 'attention.state'}), 'get_current_runtime': frozenset({'runtime.job_ref', 'runtime.attempt_ref', 'runtime.worker_ref', 'runtime.binding_ref', 'runtime.state', 'runtime.effect_state'}), 'explain_blocker': frozenset({'blocker.present', 'blocker.kind', 'blocker.explanation'}), 'resolve_surface': frozenset({'surface.ref', 'surface.locator_kind', 'surface.review_state', 'surface.health'})})
_RESPONSIBILITY_REF_SCHEMA = _string(max_length=MAX_RESPONSIBILITY_REF_CHARS, pattern=_RESPONSIBILITY_REF_PATTERN)
_OBSERVED_AT_SCHEMA = {'oneOf': [{'type': 'null'}, _string(max_length=20, pattern=_TIMESTAMP_PATTERN)]}
_SOURCE_SCHEMA = _object({'owner': {'type': 'string', 'enum': sorted(SOURCE_OWNERS)}, 'source_ref': _string(max_length=256, pattern=rf'^[^\x00-\x20\x7f]{{1,256}}{_ABSOLUTE_END}'), 'observed_at': _OBSERVED_AT_SCHEMA}, required=('owner', 'source_ref', 'observed_at'))
_SOURCE_SCHEMA['allOf'] = [{'oneOf': [{'properties': {'owner': {'const': owner}, 'source_ref': _string(max_length=256, pattern=pattern)}} for owner, pattern in _SOURCE_REF_PATTERN_BY_OWNER.items()]}]
_FACT_SCHEMA = _object({'subject_ref': _RESPONSIBILITY_REF_SCHEMA, 'predicate': {'type': 'string', 'enum': list(PUBLIC_FACT_CONTRACTS)}, 'value': {'anyOf': [{'type': 'boolean'}, {'type': 'integer', 'minimum': 0, 'maximum': 31536000}, {'type': 'string'}]}, 'freshness': {'type': 'string', 'enum': sorted(FRESHNESS_STATES)}, 'sources': {'type': 'array', 'minItems': 1, 'maxItems': MAX_SOURCES_PER_FACT, 'items': _SOURCE_SCHEMA}}, required=('subject_ref', 'predicate', 'value', 'freshness', 'sources'))
_FACT_SCHEMA['allOf'] = [{'oneOf': [{'properties': {'predicate': {'const': contract.predicate}, 'value': contract.value_schema, 'sources': {'contains': {'properties': {'owner': {'enum': list(contract.corroborating_owners)}}}, 'minContains': 1}}} for contract in _FACT_CONTRACT_ROWS]}]
_RESULT_DATA_SCHEMA = _object({'state': {'type': 'string', 'enum': sorted(GROUNDING_STATES)}, 'facts': {'type': 'array', 'maxItems': MAX_FACTS, 'items': _FACT_SCHEMA}, 'reason_codes': {'type': 'array', 'maxItems': MAX_REASON_CODES, 'uniqueItems': True, 'items': {'type': 'string', 'enum': sorted(GROUNDING_REASON_CODES)}}}, required=('state', 'facts', 'reason_codes'))
_RESULT_DATA_SCHEMA['allOf'] = [{'oneOf': [{'properties': {'state': {'const': 'FACTS'}, 'facts': {'type': 'array', 'minItems': 1, 'maxItems': MAX_FACTS, 'items': {'type': 'object', 'properties': {'freshness': {'const': 'FRESH'}}, 'required': ['freshness']}}, 'reason_codes': {'type': 'array', 'maxItems': 0}}}, {'properties': {'state': {'const': 'UNKNOWN'}, 'facts': {'type': 'array', 'maxItems': 0}, 'reason_codes': {'type': 'array', 'minItems': 1, 'maxItems': MAX_REASON_CODES}}}, {'properties': {'state': {'const': 'DEGRADED'}, 'reason_codes': {'type': 'array', 'minItems': 1, 'maxItems': MAX_REASON_CODES}}}, {'properties': {'state': {'const': 'REFUSED'}, 'facts': {'type': 'array', 'maxItems': 0}, 'reason_codes': {'type': 'array', 'minItems': 1, 'maxItems': MAX_REASON_CODES}}}]}]
_ERROR_DETAIL_SCHEMA = {'oneOf': [_object({'code': {'const': code}, 'message': {'const': code}}, required=('code', 'message')) for code in sorted(ERROR_CODES)]}

def _facts_contains(predicate: str) -> dict[str, Any]:
    return {'contains': {'properties': {'predicate': {'const': predicate}}, 'required': ['predicate']}, 'minContains': 1}

def _result_data_schema_for(tool_name: str) -> dict[str, Any]:
    schema = copy.deepcopy(_RESULT_DATA_SCHEMA)
    required = sorted(TOOL_REQUIRED_PREDICATES.get(tool_name, ()))
    if required:
        schema['allOf'][0]['oneOf'][0]['properties']['facts']['allOf'] = [_facts_contains(predicate) for predicate in required]
    return schema

def _output_schema(tool_name: str) -> dict[str, Any]:
    value = _object({'schema': {'const': RESULT_SCHEMA}, 'tool': {'const': tool_name}, 'ok': {'type': 'boolean'}, 'server_version': {'const': SERVER_VERSION}, 'data': {'oneOf': [{'type': 'null'}, _result_data_schema_for(tool_name)]}, 'error': {'oneOf': [{'type': 'null'}, copy.deepcopy(_ERROR_DETAIL_SCHEMA)]}}, required=('schema', 'tool', 'ok', 'server_version', 'data', 'error'))
    value['allOf'] = [{'oneOf': [{'properties': {'ok': {'const': True}, 'data': {'type': 'object'}, 'error': {'type': 'null'}}}, {'properties': {'ok': {'const': False}, 'data': {'type': 'null'}, 'error': {'type': 'object'}}}]}]
    return value

@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """One immutable reviewed Secretary read tool."""
    name: str
    description: str
    requires_responsibility_ref: bool
    read_only: bool = True

    @property
    def input_schema(self) -> dict[str, Any]:
        if self.requires_responsibility_ref:
            return _object({'responsibility_ref': copy.deepcopy(_RESPONSIBILITY_REF_SCHEMA)}, required=('responsibility_ref',))
        return _object({})

    @property
    def output_schema(self) -> dict[str, Any]:
        return _output_schema(self.name)

    @property
    def annotations(self) -> dict[str, Any]:
        return {'title': self.name, 'readOnlyHint': self.read_only, 'destructiveHint': False, 'idempotentHint': self.read_only, 'openWorldHint': False}
_TOOL_ROWS = (('list_responsibilities', 'List source-attributed responsibility grounding from the injected Steward read port.', False), ('get_responsibility', 'Read one exact responsibility reference without heuristic identity resolution.', True), ('get_attention', 'Read source-attributed attention facts without selecting a person, role, or transport.', False), ('get_current_runtime', 'Read current runtime facts for one exact responsibility reference.', True), ('explain_blocker', 'Read source-attributed company, runtime, and surface blocker facts for one responsibility.', True), ('resolve_surface', 'Read exact reviewed surface resolution and health without performing any action.', True))
TOOL_SPECS: tuple[ToolSpec, ...] = tuple((ToolSpec(*row) for row in _TOOL_ROWS))
_TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}

def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise GatewayError('INVALID_REQUEST')
            result[key] = _jsonable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        raise GatewayError('INVALID_REQUEST')
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if dataclasses.is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    raise GatewayError('INVALID_REQUEST')

def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(_jsonable(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except GatewayError:
        raise
    except (TypeError, ValueError, RecursionError):
        raise GatewayError('INVALID_REQUEST') from None

def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    assert_contract_integrity()
    if not isinstance(tool_name, str):
        raise GatewayError('INVALID_REQUEST')
    spec = _TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        raise GatewayError('INVALID_REQUEST')
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise GatewayError('INVALID_REQUEST')
    try:
        raw = dict(arguments)
    except Exception:
        raise GatewayError('INVALID_REQUEST') from None
    allowed = set(spec.input_schema['properties'])
    required = set(spec.input_schema.get('required', ()))
    if set(raw) != required or not set(raw) <= allowed:
        raise GatewayError('INVALID_REQUEST')
    if not raw:
        return {}
    responsibility_ref = raw.get('responsibility_ref')
    if not isinstance(responsibility_ref, str) or _RESPONSIBILITY_REF_RE.fullmatch(responsibility_ref) is None:
        raise GatewayError('INVALID_REQUEST')
    if len(canonical_json({'arguments': raw})) > MAX_REQUEST_BYTES:
        raise GatewayError('INVALID_REQUEST')
    return {'responsibility_ref': responsibility_ref}

def _validated_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        raise GatewayError('RESPONSE_REFUSED')
    try:
        parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise GatewayError('RESPONSE_REFUSED') from None
    return value

def _validated_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {'owner', 'source_ref', 'observed_at'}:
        raise GatewayError('RESPONSE_REFUSED')
    owner = value['owner']
    source_ref = value['source_ref']
    if not isinstance(owner, str) or owner not in SOURCE_OWNERS:
        raise GatewayError('RESPONSE_REFUSED')
    if not isinstance(source_ref, str) or not 1 <= len(source_ref) <= 256 or source_ref != source_ref.strip() or _CONTROL_RE.search(source_ref) or (_SOURCE_REF_RE_BY_OWNER[owner].fullmatch(source_ref) is None):
        raise GatewayError('RESPONSE_REFUSED')
    observed_at = _validated_timestamp(value['observed_at'])
    return {'owner': owner, 'source_ref': source_ref, 'observed_at': observed_at}

def _validated_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {'subject_ref', 'predicate', 'value', 'freshness', 'sources'}:
        raise GatewayError('RESPONSE_REFUSED')
    subject_ref = value['subject_ref']
    predicate = value['predicate']
    freshness = value['freshness']
    sources = value['sources']
    if not isinstance(subject_ref, str) or _RESPONSIBILITY_REF_RE.fullmatch(subject_ref) is None or (not isinstance(predicate, str)) or (predicate not in PUBLIC_FACT_CONTRACTS) or (not isinstance(freshness, str)) or (freshness not in FRESHNESS_STATES) or (not isinstance(sources, (list, tuple))) or (not 1 <= len(sources) <= MAX_SOURCES_PER_FACT):
        raise GatewayError('RESPONSE_REFUSED')
    contract = PUBLIC_FACT_CONTRACTS[predicate]
    normalized_sources = sorted((_validated_source(source) for source in sources), key=lambda row: (row['owner'], row['source_ref'], row['observed_at'] or ''))
    normalized_value = contract.normalize(value['value'])
    if contract.corroborating_owners and (not any((source['owner'] in contract.corroborating_owners for source in normalized_sources))):
        raise GatewayError('RESPONSE_REFUSED')
    return {'subject_ref': subject_ref, 'predicate': predicate, 'value': normalized_value, 'freshness': freshness, 'sources': normalized_sources}

_EXECUTIVE_RUNTIME_PREDICATES = ('runtime.job_ref', 'runtime.attempt_ref', 'runtime.worker_ref', 'runtime.state', 'runtime.effect_state')
_BINDING_RUNTIME_PREDICATES = ('runtime.binding_ref', 'runtime.continuation')

def _common_receipt(rows: dict[str, dict[str, Any]], predicates: tuple[str, ...], owners: tuple[str, ...]) -> str | None:
    """Return the single receipt shared by every present fact, else refuse."""
    receipt_sets: list[set[str]] = []
    for predicate in predicates:
        row = rows.get(predicate)
        if row is None:
            continue
        refs = {source['source_ref'] for source in row['sources'] if source['owner'] in owners}
        if not refs:
            raise GatewayError('RESPONSE_REFUSED')
        receipt_sets.append(refs)
    if not receipt_sets:
        return None
    common = set.intersection(*receipt_sets)
    if len(common) != 1:
        raise GatewayError('RESPONSE_REFUSED')
    return next(iter(common))

def _receipt_attempt_identity(receipt: str) -> str | None:
    _, _, tail = receipt.partition(':')
    return tail if tail.startswith('ATT-') else None

def _validate_runtime_receipt_join(rows: dict[str, dict[str, Any]]) -> None:
    """Selected runtime facts may not borrow authority across unrelated receipts."""
    executive = _common_receipt(rows, _EXECUTIVE_RUNTIME_PREDICATES, _EXECUTIVE_OS)
    _common_receipt(rows, _BINDING_RUNTIME_PREDICATES, _RUNTIME_BINDING)
    attempt = rows.get('runtime.attempt_ref')
    if executive is None or attempt is None:
        return
    carried = _receipt_attempt_identity(executive)
    if carried is not None and carried != str(attempt['value']):
        raise GatewayError('RESPONSE_REFUSED')

def _surface_receipt_matches(surface_ref: str, receipt: str) -> bool:
    return receipt == surface_ref or receipt == f'surface-binding:{surface_ref}'

def _validate_cross_fact_law(state: str, facts: list[dict[str, Any]], reason_codes: list[str]) -> None:
    seen: set[tuple[str, str]] = set()
    subject_by_identity: dict[str, str] = {}
    by_subject: dict[str, dict[str, dict[str, Any]]] = {}
    for fact in facts:
        key = (fact['subject_ref'], fact['predicate'])
        if key in seen:
            raise GatewayError('RESPONSE_REFUSED')
        seen.add(key)
        by_subject.setdefault(fact['subject_ref'], {})[fact['predicate']] = fact
        if fact['predicate'] == 'responsibility.identity':
            identity = str(fact['value'])
            previous = subject_by_identity.get(identity)
            if previous is not None and previous != fact['subject_ref']:
                raise GatewayError('RESPONSE_REFUSED')
            subject_by_identity[identity] = fact['subject_ref']
    selected_predicates = {'runtime.job_ref', 'runtime.attempt_ref', 'runtime.worker_ref', 'runtime.binding_ref', 'surface.ref'}
    selected = any((fact['predicate'] in selected_predicates for fact in facts))
    unsafe_reasons = {'AMBIGUOUS_JOIN', 'EFFECT_UNKNOWN', 'RUNTIME_UNKNOWN', 'STALE_SOURCE', 'SURFACE_UNKNOWN'}
    if selected and (state != 'FACTS' or unsafe_reasons.intersection(reason_codes)):
        raise GatewayError('RESPONSE_REFUSED')
    for rows in by_subject.values():
        selected_runtime = any((predicate in rows for predicate in ('runtime.job_ref', 'runtime.attempt_ref', 'runtime.worker_ref', 'runtime.binding_ref')))
        effect = rows.get('runtime.effect_state')
        if selected_runtime and effect is not None and (str(effect['value']).lower() == 'effect_unknown'):
            raise GatewayError('RESPONSE_REFUSED')
        if selected_runtime:
            _validate_runtime_receipt_join(rows)
        surface = rows.get('surface.ref')
        if surface is None:
            continue
        locator = rows.get('surface.locator_kind')
        review = rows.get('surface.review_state')
        health = rows.get('surface.health')
        if locator is None or review is None or health is None or (str(review['value']).lower() != 'approved') or any((row['freshness'] != 'FRESH' for row in (surface, locator, review, health))):
            raise GatewayError('RESPONSE_REFUSED')
        binding_sets: list[set[str]] = []
        for row in (surface, locator, review, health):
            refs = {source['source_ref'] for source in row['sources'] if source['owner'] in _SURFACE_OWNERS}
            if not refs:
                raise GatewayError('RESPONSE_REFUSED')
            binding_sets.append(refs)
        common = set.intersection(*binding_sets)
        if len(common) != 1:
            raise GatewayError('RESPONSE_REFUSED')
        receipt = next(iter(common))
        if not _surface_receipt_matches(str(surface['value']), receipt):
            raise GatewayError('RESPONSE_REFUSED')

_SUBJECT_SCOPED_TOOLS = ('get_responsibility', 'get_current_runtime', 'explain_blocker', 'resolve_surface')

def _validate_tool_contract(tool_name: str | None, responsibility_ref: str | None, state: str, facts: list[dict[str, Any]]) -> None:
    """Enforce the frozen per-tool field set and the exact requested subject."""
    if tool_name is None:
        return
    required = TOOL_REQUIRED_PREDICATES.get(tool_name)
    if required is None:
        raise GatewayError('RESPONSE_REFUSED')
    scoped = tool_name in _SUBJECT_SCOPED_TOOLS
    subjects = {fact['subject_ref'] for fact in facts}
    if scoped and responsibility_ref is not None and any((subject != responsibility_ref for subject in subjects)):
        raise GatewayError('RESPONSE_REFUSED')
    if state != 'FACTS':
        return
    if scoped and len(subjects) != 1:
        raise GatewayError('RESPONSE_REFUSED')
    present: dict[str, set[str]] = {}
    for fact in facts:
        present.setdefault(fact['subject_ref'], set()).add(fact['predicate'])
    for predicates in present.values():
        if not required <= predicates:
            raise GatewayError('RESPONSE_REFUSED')

def validate_result_data(value: Any, *, tool_name: str | None=None, responsibility_ref: str | None=None) -> dict[str, Any]:
    """Validate the complete typed Steward return without inference or repair."""
    if not isinstance(value, Mapping) or set(value) != {'state', 'facts', 'reason_codes'}:
        raise GatewayError('RESPONSE_REFUSED')
    state = value['state']
    facts = value['facts']
    reason_codes = value['reason_codes']
    if not isinstance(state, str) or state not in GROUNDING_STATES or (not isinstance(facts, (list, tuple))) or (len(facts) > MAX_FACTS) or (not isinstance(reason_codes, (list, tuple))) or (len(reason_codes) > MAX_REASON_CODES):
        raise GatewayError('RESPONSE_REFUSED')
    if any((not isinstance(code, str) or code not in GROUNDING_REASON_CODES for code in reason_codes)):
        raise GatewayError('RESPONSE_REFUSED')
    if len(reason_codes) != len(set(reason_codes)):
        raise GatewayError('RESPONSE_REFUSED')
    normalized_facts = [_validated_fact(fact) for fact in facts]
    normalized_reasons = sorted(reason_codes)
    if state == 'FACTS' and (not normalized_facts or normalized_reasons or any((fact['freshness'] != 'FRESH' for fact in normalized_facts))):
        raise GatewayError('RESPONSE_REFUSED')
    if state in {'UNKNOWN', 'REFUSED'} and (normalized_facts or not normalized_reasons):
        raise GatewayError('RESPONSE_REFUSED')
    if state == 'DEGRADED' and (not normalized_reasons):
        raise GatewayError('RESPONSE_REFUSED')
    _validate_cross_fact_law(state, normalized_facts, normalized_reasons)
    _validate_tool_contract(tool_name, responsibility_ref, state, normalized_facts)
    normalized_facts.sort(key=lambda fact: (fact['subject_ref'], _PREDICATE_ORDER[fact['predicate']], canonical_json(fact['value'])))
    return {'state': state, 'facts': normalized_facts, 'reason_codes': normalized_reasons}

def result_envelope(tool_name: str, *, data: Any, responsibility_ref: str | None=None) -> dict[str, Any]:
    if tool_name not in _TOOLS_BY_NAME:
        raise GatewayError('RESPONSE_REFUSED')
    normalized = validate_result_data(data, tool_name=tool_name, responsibility_ref=responsibility_ref)
    envelope = {'schema': RESULT_SCHEMA, 'tool': tool_name, 'ok': True, 'server_version': SERVER_VERSION, 'data': normalized, 'error': None}
    try:
        if len(canonical_json(envelope)) > MAX_RESPONSE_BYTES:
            raise GatewayError('RESPONSE_REFUSED')
    except GatewayError:
        raise GatewayError('RESPONSE_REFUSED') from None
    return envelope

def error_envelope(tool_name: str, code: str) -> dict[str, Any]:
    if code not in ERROR_CODES:
        code = 'INTERNAL_ERROR'
    return {'schema': RESULT_SCHEMA, 'tool': tool_name if isinstance(tool_name, str) and tool_name in _TOOLS_BY_NAME else 'unknown', 'ok': False, 'server_version': SERVER_VERSION, 'data': None, 'error': {'code': code, 'message': code}}

def schema_snapshot() -> dict[str, Any]:
    return {'server_name': SERVER_NAME, 'server_identity': SERVER_IDENTITY, 'server_version': SERVER_VERSION, 'result_schema': RESULT_SCHEMA, 'errors': sorted(ERROR_CODES), 'grounding_reason_codes': sorted(GROUNDING_REASON_CODES), 'source_namespaces': {owner: list(namespaces) for owner, namespaces in SOURCE_NAMESPACE_BY_OWNER.items()}, 'public_fact_contracts': [{'predicate': contract.predicate, 'value_kind': contract.value_kind, 'enum_values': list(contract.enum_values), 'minimum': contract.minimum, 'maximum': contract.maximum, 'max_length': contract.max_length, 'reference_namespaces': list(contract.reference_namespaces), 'corroborating_owners': list(contract.corroborating_owners), 'pattern': contract.pattern, 'enum_aliases': [list(pair) for pair in contract.enum_aliases]} for contract in _FACT_CONTRACT_ROWS], 'tool_required_predicates': {tool: sorted(predicates) for tool, predicates in TOOL_REQUIRED_PREDICATES.items()}, 'limits': {'request_bytes': MAX_REQUEST_BYTES, 'response_bytes': MAX_RESPONSE_BYTES, 'facts': MAX_FACTS, 'sources_per_fact': MAX_SOURCES_PER_FACT, 'reason_codes': MAX_REASON_CODES}, 'tools': [{'name': spec.name, 'description': spec.description, 'input_schema': copy.deepcopy(spec.input_schema), 'output_schema': copy.deepcopy(spec.output_schema), 'annotations': copy.deepcopy(spec.annotations), 'read_only': spec.read_only} for spec in TOOL_SPECS]}

def schema_snapshot_sha256() -> str:
    return hashlib.sha256(canonical_json(schema_snapshot())).hexdigest()

def tool_schema_snapshot() -> list[dict[str, Any]]:
    return [{'annotations': copy.deepcopy(spec.annotations), 'input_schema': copy.deepcopy(spec.input_schema), 'name': spec.name, 'output_schema': copy.deepcopy(spec.output_schema)} for spec in sorted(TOOL_SPECS, key=lambda item: item.name)]

def tool_schema_digest() -> str:
    return hashlib.sha256(canonical_json(tool_schema_snapshot())).hexdigest()
SCHEMA_SNAPSHOT_SHA256 = 'e73601400350540e5949f76a8d5f68012e3e3cf09bd980f775ebe7ce2f9afe5c'
TOOL_SCHEMA_DIGEST = 'beed9214a33ad6a5cbe61c08c392ad134d80e70ff39c13dc6351dc652a5d86ee'

def assert_contract_integrity() -> None:
    if schema_snapshot_sha256() != SCHEMA_SNAPSHOT_SHA256 or tool_schema_digest() != TOOL_SCHEMA_DIGEST:
        raise GatewayError('INTERNAL_ERROR')
__all__ = ['ERROR_CODES', 'FRESHNESS_STATES', 'GROUNDING_REASON_CODES', 'GROUNDING_STATES', 'GatewayError', 'MAX_FACTS', 'MAX_REQUEST_BYTES', 'MAX_RESPONSE_BYTES', 'MAX_SOURCES_PER_FACT', 'PUBLIC_FACT_CONTRACTS', 'RESULT_SCHEMA', 'SCHEMA_SNAPSHOT_SHA256', 'SERVER_IDENTITY', 'SERVER_NAME', 'SERVER_VERSION', 'SOURCE_NAMESPACE_BY_OWNER', 'SOURCE_OWNERS', 'TOOL_REQUIRED_PREDICATES', 'TOOL_SCHEMA_DIGEST', 'TOOL_SPECS', 'ToolSpec', 'assert_contract_integrity', 'canonical_json', 'error_envelope', 'result_envelope', 'schema_snapshot', 'schema_snapshot_sha256', 'tool_schema_digest', 'tool_schema_snapshot', 'validate_result_data', 'validate_tool_arguments']
