"""Loopback-only executable UI harness. Synthetic state; not a production API.

Run from package root: python -m backend.server
No authentication substitute, broker endpoint, persistent state or provider call.
"""
from pathlib import Path
from urllib.parse import urlsplit
import json
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from backend.preflight import ContractError, Plan, evaluate, verify_preview
from backend.fixtures import NOW, SAMPLE_PLAN, CASES, context

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title='Trading Lab preflight integration harness', version='0.1.0')


@app.middleware('http')
async def boundary(request: Request, call_next):
    # This is loopback transport protection for a fixture harness, not user auth.
    host = request.headers.get('host', '').split(':')[0].lower()
    if host not in ('localhost', '127.0.0.1', 'testserver'):
        return JSONResponse({'error': 'LOOPBACK_ONLY'}, status_code=403)
    origin = request.headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.netloc != request.headers.get('host'):
                return JSONResponse({'error': 'CROSS_ORIGIN_REFUSED'}, status_code=403)
        except ValueError:
            return JSONResponse({'error': 'CROSS_ORIGIN_REFUSED'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get('/')
def index():
    return FileResponse(ROOT/'web'/'index.html')


@app.get('/api/demo')
def demo():
    return {'synthetic': True, 'live_data': False, 'ai_connected': False,
            'clock': NOW.isoformat(), 'sample_plan': SAMPLE_PLAN, 'cases': CASES,
            'note': 'Frozen fixture clock. No account writes or real orders.'}


async def payload(request):
    if request.headers.get('content-type', '').split(';')[0] != 'application/json':
        raise ContractError('Use application/json.')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32768:
            raise ContractError('Request exceeds the 32 KiB limit.')
    try:
        def reject_constant(x):
            raise ValueError(x)
        def unique_pairs(pairs):
            obj = {}
            for k, v in pairs:
                if k in obj:
                    raise ValueError('duplicate JSON key')
                obj[k] = v
            return obj
        data = json.loads(body, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise ContractError('Invalid strict JSON.') from exc
    if not isinstance(data, dict) or set(data) - {'plan', 'case', 'previous'}:
        raise ContractError('Unknown request fields.')
    if data.get('case', 'current') not in CASES or not isinstance(data.get('plan'), dict):
        raise ContractError('A known demonstration case and plan are required.')
    return data


@app.post('/api/preflight')
async def preflight(request: Request):
    try:
        data = await payload(request)
        p = Plan.from_payload(data['plan'])
        c = context(data.get('case', 'current'))
        out = evaluate(p, c, now=NOW)
        out.update(synthetic=True, ai_connected=False, live_data=False)
        if 'previous' in data:
            if not isinstance(data['previous'], dict):
                raise ContractError('Previous preview must be an object.')
            out['previous_still_current'] = verify_preview(data['previous'], p, c, now=NOW)
        return out
    except (ContractError, ValueError, TypeError, KeyError) as exc:
        return JSONResponse({'error': 'INVALID_INPUT', 'detail': str(exc), 'execution_authority': False}, status_code=422)


@app.post('/api/execute')
def no_execution():
    return JSONResponse({'error': 'EXECUTION_NOT_IMPLEMENTED', 'order_submitted': False,
                         'detail': 'This harness only prepares decisions. It does not place or persist orders.'}, status_code=501)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765, access_log=False, proxy_headers=False)
