"""Additive search/fetch compatibility over explicitly injected item services.

Inert by default: no resolver factory, store, auth, listener or descriptor/index.
The owner must compose the real incumbent ReadService methods and qualification
policy. Synthetic callback assertions do not establish production qualification.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import inspect
import json

from .bounded_item_v1 import (
    COMPLETE_ITEM_SCHEMA, ITEM_ID_SCHEMA_PATTERN, ITEM_REFERENCE_SCHEMA,
    EvidenceResponseRefused, canonical_item_url, evidence_wire, item_reference,
)
from .contracts import ContractViolation

COMPATIBILITY_CONTRACT = 'research.read.mcp.search_fetch.v1'
COMPATIBILITY_TOOL_NAMES = ('search', 'fetch')
MAX_COMPATIBILITY_WIRE_BYTES = 128 * 1024
SEARCH_DEFAULT_LIMIT = 8
SEARCH_MAX_LIMIT = 20
INPUT_SCHEMAS = {
    'search': {'type': 'object', 'additionalProperties': False, 'required': ['query'],
               'properties': {'query': {'type': 'string', 'minLength': 1, 'maxLength': 200}}},
    'fetch': {'type': 'object', 'additionalProperties': False, 'required': ['id'],
              'properties': {'id': {'type': 'string', 'pattern': ITEM_ID_SCHEMA_PATTERN}}},
}
OUTPUT_SCHEMAS = {
    'search': {'type': 'object', 'additionalProperties': False, 'required': ['results'],
               'properties': {'results': {'type': 'array', 'maxItems': SEARCH_MAX_LIMIT,
                                          'items': deepcopy(ITEM_REFERENCE_SCHEMA)}}},
    'fetch': deepcopy(COMPLETE_ITEM_SCHEMA),
}


def _refuse(code='INTERNAL_ERROR'):
    raise ContractViolation(code) from None


def validate_arguments(name, arguments):
    if name not in COMPATIBILITY_TOOL_NAMES:
        _refuse('TOOL_NOT_AVAILABLE')
    if type(arguments) is not dict or set(arguments) != ({'query'} if name == 'search' else {'id'}):
        _refuse('INVALID_REQUEST')
    value = arguments['query' if name == 'search' else 'id']
    if name == 'search':
        if type(value) is not str or not value.strip() or not 1 <= len(value) <= 200:
            _refuse('INVALID_REQUEST')
        try:
            value.encode('utf-8', errors='strict')
        except UnicodeError:
            _refuse('INVALID_REQUEST')
    else:
        try:
            canonical_item_url(value)
        except EvidenceResponseRefused:
            _refuse('INVALID_REQUEST')
    return dict(arguments)


def grant_is_current(entitlement, now):
    """Same owner's current grant shape; no grant/identity authority is created."""
    return (type(now) is int
            and type(getattr(entitlement, 'content_classes', None)) is frozenset
            and 'evidence_passage' in entitlement.content_classes
            and type(getattr(entitlement, 'quote_limit_chars', None)) is int
            and entitlement.quote_limit_chars > 0
            and type(getattr(entitlement, 'expires_at', None)) is int
            and entitlement.expires_at > now)


def _search_data(value, limit):
    # This state is an injected SERVICE seam, not a new public/readiness receipt.
    if type(value) is not dict or set(value) != {'state', 'results'}:
        _refuse()
    if value['state'] in {'UNAVAILABLE', 'STALE'}:
        _refuse('SOURCE_UNAVAILABLE')
    if value['state'] != 'QUALIFIED' or type(value['results']) is not list or len(value['results']) > limit:
        _refuse()
    try:
        rows = [item_reference(row) for row in value['results']]
    except EvidenceResponseRefused:
        _refuse()
    if len({row['id'] for row in rows}) != len(rows):
        _refuse()
    return {'results': rows}


def validate_output(name, data, *, quote_limit_chars):
    if name == 'search':
        if type(data) is not dict or set(data) != {'results'}:
            _refuse()
        return _search_data({'state': 'QUALIFIED', 'results': data['results']}, SEARCH_MAX_LIMIT)
    if name != 'fetch':
        _refuse('TOOL_NOT_AVAILABLE')
    try:
        # Preserve the entire literal item; a smaller current quote cannot trim it.
        raw = evidence_wire(data, data.get('id') if type(data) is dict else None, 1000)
        if type(quote_limit_chars) is not int or quote_limit_chars <= 0 or len(data['text']) > quote_limit_chars:
            _refuse('NOT_ENTITLED')
        evidence_wire(data, data['id'], quote_limit_chars)
        return json.loads(raw)
    except EvidenceResponseRefused:
        _refuse()


@dataclass(frozen=True)
class CompatibilityPortV1:
    """Owner-supplied awaitable service seam; never a second corpus/resolver.

    search_items(caller_context, query, limit) returns exactly state/results.
    QUALIFIED must mean the actual current admitted search completed; STALE or
    UNAVAILABLE must refuse, including empty results. resolve_item(caller_context,
    item_id) returns the shared complete-item DTO or a closed ContractViolation.
    Actual service/descriptor/generation integration remains with its incumbent
    owner and must be qualified before this optional port is installed.
    """
    search_items: Callable
    resolve_item: Callable
    context_type: type
    result_limit: int = SEARCH_DEFAULT_LIMIT

    def __post_init__(self):
        if (not callable(self.search_items) or not callable(self.resolve_item)
                or not isinstance(self.context_type, type) or not issubclass(self.context_type, Mapping)
                or type(self.result_limit) is not int or not 1 <= self.result_limit <= SEARCH_MAX_LIMIT):
            raise ValueError('COMPATIBILITY_COMPOSITION_REFUSED')

    async def __call__(self, name, arguments, context, *, quote_limit_chars):
        args = validate_arguments(name, arguments)
        if (type(context) is not self.context_type or getattr(context, 'surface', None) != 'mcp'
                or getattr(context, 'entitlement', None) != 'pro'
                or type(getattr(context, 'scopes', None)) is not frozenset
                or 'find_evidence' not in context.scopes
                or type(quote_limit_chars) is not int or quote_limit_chars <= 0):
            _refuse('NOT_ENTITLED')
        pending = (self.search_items(caller_context=context, query=args['query'], limit=self.result_limit)
                   if name == 'search' else self.resolve_item(caller_context=context, item_id=args['id']))
        if not inspect.isawaitable(pending):
            _refuse()
        value = await pending
        if name == 'search':
            return _search_data(value, self.result_limit)
        try:
            # Resolver output must identify the exact item requested by this call.
            evidence_wire(value, args['id'], quote_limit_chars)
        except EvidenceResponseRefused:
            _refuse()
        return validate_output(name, value, quote_limit_chars=quote_limit_chars)
