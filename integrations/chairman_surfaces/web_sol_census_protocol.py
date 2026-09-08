"""Closed, lossless profile census values; no I/O, transport or retained state."""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone

from . import web_sol_protocol as legacy

REQUEST_SCHEMA = 'mastermind.web_sol_census_request.v1'
RECEIPT_SCHEMA = 'mastermind.web_sol_census_receipt.v1'
TABLE_SCHEMA = 'mastermind.web_sol_census_table.v1'
LOCAL_SCHEMA = 'mastermind.web_sol_local_census.v1'
MAX_ROWS = 128
MAX_PAYLOAD_BYTES = 61440
TOTAL_SECONDS = 10
IDENTITY_FIELDS = ('adapter_instance_id', 'operation_key', 'nonce')
HEADER_FIELDS = ('schema', 'scope', 'adapter_instance_id', 'started_at', 'completed_at',
                 'duration_ms', 'inventory_coverage', 'consistency', 'reason',
                 'initial_tab_count', 'final_tab_count', 'excluded_private_count',
                 'omitted_tab_count', 'unobserved_added_count', 'unique_conversation_count',
                 'duplicate_tab_count', 'probed_tab_count', 'generation_cue_count',
                 'unknown_cue_count', 'probe_coverage')
ROW_FIELDS = ('slot', 'conversation_fingerprint', 'identity_evidence', 'document_binding',
              'status', 'generation_cue', 'selected_in_window', 'discarded', 'frozen',
              'visibility', 'auth_required', 'provider_error_present', 'duplicate_count',
              'duplicate_cue_disagreement', 'observed_at', 'selected_model',
              'selected_effort', 'served_model', 'model_evidence')
STATUSES = frozenset({'COLLECTED', 'COLLECTOR_UNAVAILABLE', 'READ_DEADLINE_EXCEEDED',
                      'RESULT_TOO_LARGE', 'INVALID_OBSERVATION'})
ROW_STATUSES = frozenset({'OBSERVED', 'DISCARDED', 'FROZEN', 'LOADING', 'NAVIGATING',
    'NOT_A_CONVERSATION', 'INVALID_TAB', 'OUT_OF_SCOPE', 'PROBE_UNAVAILABLE',
    'PROBE_TIMEOUT', 'INVALID_PROBE', 'TARGET_CHANGED', 'LOOKUP_UNAVAILABLE',
    'SWEEP_DEADLINE', 'PROBE_SLOTS_EXHAUSTED'})
REASONS = frozenset({'NONE', 'ADAPTER_UNCONFIGURED', 'QUERY_UNAVAILABLE',
    'INVALID_INVENTORY', 'INVALID_TAB', 'TAB_LIMIT', 'INVENTORY_LIMIT',
    'INVENTORY_CHANGED', 'FINAL_QUERY_UNAVAILABLE'})


def _require(condition):
    if not condition:
        raise legacy.WebSolProtocolError('invalid_census_value')


def _keys(value, fields):
    _require(type(value) is dict and set(value) == set(fields))


def _integer(value, maximum=9007199254740991):
    return type(value) is int and 0 <= value <= maximum


def _hex(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _timestamp(value):
    _require(type(value) is str and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z', value) is not None)
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise legacy.WebSolProtocolError('invalid_census_value') from None


def _identity(value):
    _require(_hex(value['adapter_instance_id']))
    for field, low, high in [('operation_key', 1, 256), ('nonce', 16, 128)]:
        v = value[field]
        _require(type(v) is str and low <= len(v) <= high and not any(c.isspace() for c in v))


def validate_census_request(value):
    _keys(value, ('schema', *IDENTITY_FIELDS, 'issued_at', 'expires_at'))
    _require(value['schema'] == REQUEST_SCHEMA)
    _identity(value)
    issued, expires = _timestamp(value['issued_at']), _timestamp(value['expires_at'])
    _require(0 < (expires-issued).total_seconds() <= TOTAL_SECONDS)
    return copy.deepcopy(value)


def validate_census_window(value, *, now=None):
    value = validate_census_request(value)
    now = datetime.now(timezone.utc) if now is None else now
    _require(isinstance(now, datetime) and now.tzinfo is not None)
    _require(_timestamp(value['expires_at']) > now)
    _require((_timestamp(value['issued_at'])-now).total_seconds() <= 5)
    return value


def _validate_snapshot(value):
    _keys(value, (*HEADER_FIELDS, 'rows'))
    _require(value['schema'] == LOCAL_SCHEMA and value['scope'] == 'CURRENT_PROFILE_NORMAL_CHATGPT_TABS')
    _require(_hex(value['adapter_instance_id']))
    _require(_timestamp(value['completed_at']) >= _timestamp(value['started_at']))
    _require(_integer(value['duration_ms'], 10000))
    _require(value['inventory_coverage'] in ('UNAVAILABLE', 'PARTIAL', 'COMPLETE_IN_SCOPE'))
    _require(value['consistency'] in ('UNKNOWN', 'CHANGED', 'STABLE_AT_BOUNDARIES'))
    _require(type(value['reason']) is str and value['reason'] in REASONS)
    for field in ('initial_tab_count', 'final_tab_count', 'unobserved_added_count'):
        _require(value[field] is None or _integer(value[field], 4096))
    for field in ('excluded_private_count', 'omitted_tab_count', 'unique_conversation_count',
                  'duplicate_tab_count', 'probed_tab_count', 'generation_cue_count', 'unknown_cue_count'):
        _require(_integer(value[field]))
    rows = value['rows']
    _require(type(rows) is list and len(rows) <= MAX_ROWS)
    groups, cues = {}, {}
    for index, row in enumerate(rows):
        _keys(row, ROW_FIELDS)
        _require(type(row['slot']) is int and row['slot'] == index+1)
        fp = row['conversation_fingerprint']
        _require(fp is None or _hex(fp))
        _require(row['identity_evidence'] in ('UNVERIFIED', 'BROWSER_LOCATOR', 'LOCATOR_AND_V1_PROBE'))
        _require(row['document_binding'] == 'UNVERIFIED' and row['model_evidence'] == 'UNVERIFIED')
        _require(all(row[k] is None for k in ('selected_model', 'selected_effort', 'served_model')))
        _require(type(row['status']) is str and row['status'] in ROW_STATUSES)
        _require(row['generation_cue'] in ('UNKNOWN', 'PRESENT', 'NOT_OBSERVED'))
        _require(row['visibility'] in ('UNKNOWN', 'VISIBLE', 'HIDDEN'))
        for field in ('selected_in_window', 'discarded', 'frozen', 'auth_required', 'provider_error_present'):
            _require(row[field] is None or type(row[field]) is bool)
        _require(type(row['duplicate_cue_disagreement']) is bool)
        _require(_integer(row['duplicate_count'], MAX_ROWS) and row['duplicate_count'] >= 1)
        if row['observed_at'] is not None: _timestamp(row['observed_at'])
        if row['status'] == 'OBSERVED':
            _require(fp is not None and row['observed_at'] is not None and
                     row['identity_evidence'] == 'LOCATOR_AND_V1_PROBE')
        else:
            _require(row['generation_cue'] == 'UNKNOWN' and row['observed_at'] is None)
        if fp:
            groups[fp] = groups.get(fp, 0)+1
            if row['generation_cue'] != 'UNKNOWN': cues.setdefault(fp, set()).add(row['generation_cue'])
    for row in rows:
        fp = row['conversation_fingerprint']
        _require(row['duplicate_count'] == groups.get(fp, 1))
        _require(row['duplicate_cue_disagreement'] == (len(cues.get(fp, ())) > 1))
    probed = sum(r['status'] == 'OBSERVED' for r in rows)
    expected = {'unique_conversation_count': len(groups),
                'duplicate_tab_count': sum(n-1 for n in groups.values()),
                'probed_tab_count': probed,
                'generation_cue_count': sum(r['generation_cue'] == 'PRESENT' for r in rows),
                'unknown_cue_count': sum(r['generation_cue'] == 'UNKNOWN' for r in rows)}
    _require(all(value[k] == v for k,v in expected.items()))
    initial = value['initial_tab_count']
    if initial is None: _require(not rows)
    else:
        _require(len(rows) == min(initial, MAX_ROWS))
        _require(value['omitted_tab_count'] == max(initial-MAX_ROWS, 0))
    _require(value['probe_coverage'] == ('NONE' if not probed else
             'COMPLETE_IN_SCOPE' if probed == initial else 'PARTIAL'))
    if value['inventory_coverage'] == 'COMPLETE_IN_SCOPE':
        _require(initial is not None and value['omitted_tab_count'] == 0)
    final, added = value['final_tab_count'], value['unobserved_added_count']
    coverage, consistency, reason = (value[k] for k in ('inventory_coverage', 'consistency', 'reason'))
    # These relationships preserve the collector's distinct partial outcomes;
    # a closed table must not turn unknown inventory into measured success.
    _require(reason != 'ADAPTER_UNCONFIGURED')
    if final is None:
        _require(consistency == 'UNKNOWN' and added is None)
    else:
        _require(initial is not None and added is not None and added <= final)
        _require(consistency in ('STABLE_AT_BOUNDARIES', 'CHANGED'))
    if consistency == 'STABLE_AT_BOUNDARIES':
        _require(final == initial and added == 0)
    if consistency == 'CHANGED': _require(coverage == 'PARTIAL')
    if coverage == 'COMPLETE_IN_SCOPE':
        _require(consistency == 'STABLE_AT_BOUNDARIES' and reason == 'NONE')
    if initial is None:
        _require(final is None and reason in ('QUERY_UNAVAILABLE', 'INVALID_INVENTORY', 'INVENTORY_LIMIT'))
    else:
        _require(reason in ('NONE', 'INVALID_TAB', 'TAB_LIMIT', 'INVENTORY_CHANGED', 'FINAL_QUERY_UNAVAILABLE'))
    if reason == 'QUERY_UNAVAILABLE':
        _require(initial is None and coverage == 'UNAVAILABLE' and
                 value['excluded_private_count'] == 0 and value['omitted_tab_count'] == 0)
    elif reason == 'INVALID_INVENTORY':
        _require(initial is None and coverage == 'UNAVAILABLE')
    elif reason == 'INVENTORY_LIMIT':
        _require(initial is None and coverage == 'PARTIAL' and
                 value['excluded_private_count'] == 0 and value['omitted_tab_count'] > 4096)
    elif reason == 'NONE':
        _require(coverage == 'COMPLETE_IN_SCOPE')
    else:
        _require(coverage == 'PARTIAL')
        if reason == 'TAB_LIMIT': _require(value['omitted_tab_count'] > 0)
        else: _require(value['omitted_tab_count'] == 0)
        if reason == 'INVALID_TAB': _require(consistency != 'STABLE_AT_BOUNDARIES')
        if reason == 'INVENTORY_CHANGED': _require(consistency == 'CHANGED')
        if reason == 'FINAL_QUERY_UNAVAILABLE': _require(final is None)
    return value


def encode_snapshot(value):
    value = _validate_snapshot(value)
    return {'schema': TABLE_SCHEMA, 'header': [copy.deepcopy(value[k]) for k in HEADER_FIELDS],
            'rows': [[copy.deepcopy(row[k]) for k in ROW_FIELDS] for row in value['rows']]}


def decode_snapshot(value):
    _keys(value, ('schema', 'header', 'rows'))
    _require(value['schema'] == TABLE_SCHEMA and type(value['header']) is list and
             len(value['header']) == len(HEADER_FIELDS))
    _require(type(value['rows']) is list and len(value['rows']) <= MAX_ROWS and
             all(type(r) is list and len(r) == len(ROW_FIELDS) for r in value['rows']))
    snapshot = dict(zip(HEADER_FIELDS, value['header'], strict=True))
    snapshot['rows'] = [dict(zip(ROW_FIELDS, row, strict=True)) for row in value['rows']]
    return copy.deepcopy(_validate_snapshot(snapshot))


def validate_census_receipt(value):
    _keys(value, ('schema', *IDENTITY_FIELDS, 'status', 'snapshot'))
    _require(value['schema'] == RECEIPT_SCHEMA)
    _identity(value)
    _require(type(value['status']) is str and value['status'] in STATUSES)
    if value['status'] == 'COLLECTED':
        snapshot = decode_snapshot(value['snapshot'])
        _require(snapshot['adapter_instance_id'] == value['adapter_instance_id'])
    else: _require(value['snapshot'] is None)
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError):
        raise legacy.WebSolProtocolError('invalid_census_value') from None
    _require(len(payload) <= MAX_PAYLOAD_BYTES)
    return copy.deepcopy(value)
