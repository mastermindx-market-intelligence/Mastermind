"""Operator-scoped read-only V3 evidence routes; no capture or provider execution."""
from __future__ import annotations

from pathlib import Path
import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app import auth
from portfolio import decision_snapshot as snapshots
from portfolio.decision_snapshot_contracts import SECTION_IDS, MAX_SECTION_RESPONSE_BYTES, MAX_SNAPSHOT_BYTES

router = APIRouter()
_STATIC = Path(__file__).resolve().parent / 'static'
_HEADERS = {'Cache-Control': 'no-store, private', 'Vary': 'Authorization, Cookie',
            'X-Content-Type-Options': 'nosniff'}
_QUERY_KEYS = frozenset({'book', 'snapshot_id', 'section', 'offset', 'limit'})
_ID = re.compile(r'sha256:[0-9a-f]{64}\Z')
_NUMBER = re.compile(r'(?:0|[1-9][0-9]{0,7})\Z')


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({'error': code}, status_code=status, headers=_HEADERS)


def _parameters(request: Request) -> dict:
    pairs = list(request.query_params.multi_items())
    if len(pairs) > len(_QUERY_KEYS) or len({key for key, _ in pairs}) != len(pairs):
        raise ValueError('duplicate or excessive query fields')
    if any(key not in _QUERY_KEYS for key, _ in pairs):
        raise ValueError('unknown query field')
    values = dict(pairs)
    snapshot_id = values.get('snapshot_id')
    section = values.get('section')
    if snapshot_id is not None and _ID.fullmatch(snapshot_id) is None:
        raise ValueError('invalid snapshot identity')
    if section is not None and section not in SECTION_IDS:
        raise ValueError('invalid section')
    offset_raw = values.get('offset', '0'); limit_raw = values.get('limit', '50')
    if not _NUMBER.fullmatch(offset_raw) or not _NUMBER.fullmatch(limit_raw):
        raise ValueError('invalid integer')
    offset, limit = int(offset_raw), int(limit_raw)
    if not 1 <= limit <= 100 or (section is None and offset != 0):
        raise ValueError('invalid page')
    return {'book': values.get('book', 'autonomous'), 'snapshot_id': snapshot_id,
            'section_id': section, 'offset': offset, 'limit': limit}


@router.get('/api/decision-snapshot')
def evidence_api(request: Request) -> JSONResponse:
    # The response-cache owner separately excludes this endpoint. A dependency
    # inside the route alone cannot protect a middleware-level shared cache hit.
    if auth.serve_only():
        return _error('snapshot_operator_surface_disabled', 403)
    try:
        auth.assert_authoritative_auth_configured()
    except auth.AuthorizationMisconfigured:
        return _error('operator_auth_unavailable', 503)
    if not auth.is_operator_authorized(request):
        return _error('operator_authorization_required', 401)
    try:
        parameters = _parameters(request)
    except ValueError:
        return _error('invalid_snapshot_request', 400)
    if parameters['book'] != 'autonomous':
        return _error('unsupported_snapshot_book', 404)
    try:
        result = snapshots.read_projection(**parameters)
    except snapshots.SnapshotNotFound:
        return _error('snapshot_not_found', 404)
    except snapshots.SnapshotCorrupt:
        return _error('snapshot_corrupt', 409)
    except snapshots.SnapshotInvalidRequest:
        return _error('invalid_snapshot_request', 400)
    except (snapshots.DecisionSnapshotError, OSError):
        return _error('snapshot_read_unavailable', 503)
    response = JSONResponse(result, headers=_HEADERS)
    maximum = MAX_SECTION_RESPONSE_BYTES if parameters['section_id'] is not None else MAX_SNAPSHOT_BYTES
    if len(response.body) > maximum:
        return _error('snapshot_response_too_large', 400)
    return response


@router.get('/decision-evidence', include_in_schema=False)
def evidence_page() -> FileResponse:
    # Source-only shell is public; protected data is never embedded in HTML.
    headers = {**_HEADERS, 'Referrer-Policy': 'no-referrer',
               'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}
    return FileResponse(_STATIC / 'decision-evidence.html', media_type='text/html', headers=headers)


@router.get('/decision-evidence.js', include_in_schema=False)
def evidence_script() -> FileResponse:
    return FileResponse(_STATIC / 'decision-evidence.js', media_type='text/javascript', headers=_HEADERS)


@router.get('/decision-evidence.css', include_in_schema=False)
def evidence_styles() -> FileResponse:
    return FileResponse(_STATIC / 'decision-evidence.css', media_type='text/css', headers=_HEADERS)
