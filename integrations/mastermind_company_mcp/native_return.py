"""Closed, separately granted native return facet. No runtime or SDK effects."""
from __future__ import annotations

import hashlib
import json
import re

from common.company_consultation_host_contract import (
    HostFrameError, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, decode_json_frame, encode_json_frame,
)
from integrations.session_bridge.native_reply import validate_native_reply_arguments

CONFIG_NAME = 'mastermind-native-return'
SERVER_IDENTITY = 'mastermind-native-return-mcp'
SERVER_VERSION = '1.0.0'
REQUEST_SCHEMA = 'mastermind.native_return_host_request.v1'
RESULT_SCHEMA = 'mastermind.native_return_mcp_result.v1'
TOOL_NAME = 'native.reply'
INPUT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['operation_key', 'in_reply_to', 'text', 'next_step'],
    'properties': {
        'operation_key': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$'},
        'in_reply_to': {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$'},
        'text': {'type': 'string', 'minLength': 1, 'maxLength': 700},
        'next_step': {'type': 'string', 'minLength': 1, 'maxLength': 700},
    },
}
TOOL_DESCRIPTION = 'Reply once to the consumed original executive continuation on its bound carrier; does not claim parent consumption.'
ANNOTATIONS = {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}
TOOL_SCHEMA_DIGEST = hashlib.sha256(json.dumps([{
    'name': TOOL_NAME, 'input_schema': INPUT_SCHEMA,
    'annotations': ANNOTATIONS, 'output_schema': None,
}], sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
ERROR_CODES = frozenset({'INVALID_REQUEST', 'ACCESS_REFUSED', 'UNAVAILABLE', 'EFFECT_UNKNOWN', 'CONFLICT'})


def validate_arguments(arguments):
    return validate_native_reply_arguments(arguments)


def encode_request(tool, arguments):
    if tool != TOOL_NAME:
        raise HostFrameError()
    return encode_json_frame({'schema': REQUEST_SCHEMA, 'tool': tool,
        'arguments': validate_arguments(arguments)}, limit=MAX_REQUEST_BYTES)


def decode_request(frame):
    value = decode_json_frame(frame, limit=MAX_REQUEST_BYTES)
    if (set(value) != {'schema', 'tool', 'arguments'} or value['schema'] != REQUEST_SCHEMA
            or value['tool'] != TOOL_NAME):
        raise HostFrameError()
    return value['tool'], validate_arguments(value['arguments'])


def envelope(*, data=None, error=None):
    if error is not None and error not in ERROR_CODES:
        raise ValueError('invalid native return error')
    return {'schema': RESULT_SCHEMA, 'tool': TOOL_NAME, 'ok': error is None,
        'server_identity': SERVER_IDENTITY, 'server_version': SERVER_VERSION,
        'data': data if error is None else None,
        'error': None if error is None else {'code': error, 'message': error}}


def validated_response(frame):
    value = decode_json_frame(frame, limit=MAX_RESPONSE_BYTES)
    if (type(value.get('ok')) is not bool or set(value) != set(envelope())
            or value.get('schema') != RESULT_SCHEMA or value.get('tool') != TOOL_NAME
            or value.get('server_identity') != SERVER_IDENTITY or value.get('server_version') != SERVER_VERSION):
        raise HostFrameError()
    if value['ok']:
        data = value['data']
        if (value['error'] is not None or type(data) is not dict
                or set(data) != {'reply_committed', 'action', 'message_key', 'fingerprint',
                                 'thread_ts', 'in_reply_to', 'parent_consumed'}
                or data['reply_committed'] is not True or data['parent_consumed'] is not False
                or data['action'] not in {'POSTED', 'RECOVERED', 'DUPLICATE'}):
            raise HostFrameError()
        for name, pattern in (
            ('message_key', r'asd-native-reply-[0-9a-f]{40}'),
            ('fingerprint', r'[0-9a-f]{64}'), ('thread_ts', r'[0-9]{10}\.[0-9]{6}'),
            ('in_reply_to', r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}'),
        ):
            if type(data[name]) is not str or re.fullmatch(pattern, data[name]) is None:
                raise HostFrameError()
    elif (type(value['error']) is not dict or value['error'].get('code') not in ERROR_CODES
          or value != envelope(error=value['error']['code'])):
        raise HostFrameError()
    return value
