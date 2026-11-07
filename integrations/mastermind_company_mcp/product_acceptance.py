"""Closed, separately granted acceptance selector over the existing Company socket.

The worker supplies only the prerequisite selector. This contract issues no
grant and contains no principal identity, source path, digest or ruling input.
"""
from __future__ import annotations

import hashlib
import json
import re

from common.company_consultation_host_contract import (
    HostFrameError, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
    decode_json_frame, encode_json_frame,
)
from integrations.mastermind_company_mcp.schemas import (
    ERROR_CODES as DIALOGUE_ERRORS, GatewayError, validate_tool_arguments,
)

CONFIG_NAME = 'mastermind-product-acceptance'
SERVER_IDENTITY = 'mastermind-product-acceptance-mcp'
SERVER_VERSION = '1.0.0'
REQUEST_SCHEMA = 'mastermind.product_acceptance_host_request.v1'
RESULT_SCHEMA = 'mastermind.product_acceptance_mcp_result.v1'
TOOL_NAME = 'request_decision'
INPUT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['purpose', 'subject_job_id'],
    'properties': {
        'purpose': {'type': 'string', 'enum': ['PRODUCT_ACCEPTANCE']},
        'subject_job_id': {'type': 'string', 'minLength': 1, 'maxLength': 128,
                           'pattern': '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'},
    },
}
TOOL_DESCRIPTION = ('Request a product ruling for one independently reviewed prerequisite '
                    'in your existing commission, or read its original qualified receipt. '
                    'The host derives the request. Repeating the selector never resends it.')
ANNOTATIONS = {'readOnlyHint': False, 'destructiveHint': False,
               'idempotentHint': True, 'openWorldHint': False}
TOOL_SCHEMA_DIGEST = hashlib.sha256(json.dumps([{
    'name': TOOL_NAME, 'input_schema': INPUT_SCHEMA,
    'annotations': ANNOTATIONS, 'output_schema': None,
}], sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
ERROR_CODES = DIALOGUE_ERRORS | {'ACCESS_REFUSED', 'UNAVAILABLE', 'EFFECT_UNKNOWN', 'CONFLICT'}


def validate_arguments(arguments):
    try:
        value = validate_tool_arguments(TOOL_NAME, arguments, allow_product_acceptance=True)
    except GatewayError:
        raise HostFrameError() from None
    if set(value) != {'purpose', 'subject_job_id'} or value['purpose'] != 'PRODUCT_ACCEPTANCE':
        raise HostFrameError()
    return value


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
        raise ValueError('invalid product acceptance error')
    return {'schema': RESULT_SCHEMA, 'tool': TOOL_NAME, 'ok': error is None,
        'server_identity': SERVER_IDENTITY, 'server_version': SERVER_VERSION,
        'data': data if error is None else None,
        'error': None if error is None else {'code': error, 'message': error}}


def from_dialogue(result):
    value = envelope(data=result['data'])
    value.update(ok=result['ok'], error=result['error'])
    return validated_response(encode_json_frame(value, limit=MAX_RESPONSE_BYTES))


def validated_response(frame):
    value = decode_json_frame(frame, limit=MAX_RESPONSE_BYTES)
    if (set(value) != set(envelope()) or type(value['ok']) is not bool
            or value['schema'] != RESULT_SCHEMA or value['tool'] != TOOL_NAME
            or value['server_identity'] != SERVER_IDENTITY
            or value['server_version'] != SERVER_VERSION):
        raise HostFrameError()
    if value['ok']:
        if value['error'] is not None or type(value['data']) is not dict:
            raise HostFrameError()
    else:
        error = value['error']
        if (type(error) is not dict or set(error) not in (
                {'code', 'message'}, {'code', 'message', 'detail_code'})
                or error['code'] not in ERROR_CODES or error['message'] != error['code']
                or ('detail_code' in error and (type(error['detail_code']) is not str
                    or re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', error['detail_code']) is None))
                or (value['data'] is not None and type(value['data']) is not dict)):
            raise HostFrameError()
    return value
