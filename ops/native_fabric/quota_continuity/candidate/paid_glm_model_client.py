"""One model-only request over the incumbent controller shim transport.

This trusted program exposes no model tool/function, shell, filesystem, MCP,
hook, plugin or delegation API. It reads only its sealed request and short-lived
capability inputs. The same controller-side gateway independently authenticates
the canonical body and current paid lease before credential/provider access.
No retry, provider credential, URL selection or alternative transport exists.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import stat
import sys
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

URL = 'http://127.0.0.1:4141/v1/responses'
MAX_BODY = 2 * 1024 * 1024
MAX_CAPSULE = 32768
MAX_RESPONSE = 2 * 1024 * 1024
MODELS = frozenset({'glm-5.3', 'glm-5.3-flash'})


class ModelOnlyRefused(ValueError):
    pass


def _pairs(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            raise ModelOnlyRefused('closed_json_refused')
        value[k] = v
    return value


def _constant(_):
    raise ModelOnlyRefused('closed_json_refused')


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ModelOnlyRefused('closed_json_refused') from None


def parse(raw):
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                            parse_constant=_constant)
        canonical(result)
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ModelOnlyRefused('closed_json_refused') from None


def private_input(path, limit):
    """Read one original input descriptor; do not follow a replacement link."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 1 <= before.st_size <= limit):
            raise ModelOnlyRefused('private_input_refused')
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        visible = os.lstat(path)
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode,
                    s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if (len(raw) != before.st_size or identity(before) != identity(after)
                or identity(after) != identity(visible)):
            raise ModelOnlyRefused('private_input_changed')
        return bytes(raw)
    finally:
        os.close(fd)


def validate_body(raw, model):
    body = parse(raw)
    if (type(body) is not dict
            or set(body) != {'model', 'input', 'stream', 'max_output_tokens'}
            or type(model) is not str or model not in MODELS or body['model'] != model
            or type(body['input']) is not str or not body['input']
            or body['stream'] is not False or type(body['max_output_tokens']) is not int
            or body['max_output_tokens'] != 8192 or canonical(body) != raw):
        raise ModelOnlyRefused('model_only_body_refused')
    return body


def result_bytes(raw):
    """Return the actual response text only; never execute a returned tool call."""
    response = parse(raw)
    if (type(response) is not dict or response.get('status') != 'completed'
            or response.get('error') is not None
            or response.get('incomplete_details') is not None
            or type(response.get('output')) is not list or len(response['output']) != 1):
        raise ModelOnlyRefused('model_only_response_refused')
    message = response['output'][0]
    if (type(message) is not dict or message.get('type') != 'message'
            or message.get('role') != 'assistant' or message.get('status') != 'completed'
            or type(message.get('content')) is not list or len(message['content']) != 1):
        raise ModelOnlyRefused('model_only_response_refused')
    part = message['content'][0]
    if (type(part) is not dict or part.get('type') != 'output_text'
            or type(part.get('text')) is not str or not part['text']):
        raise ModelOnlyRefused('model_only_response_refused')
    text = part['text'].encode('utf-8')
    if len(text) > MAX_RESPONSE:
        raise ModelOnlyRefused('model_only_response_refused')
    # Parsing the role envelope/schema and retaining these exact bytes belong
    # to the existing qualified result owner. This is never a completion seal.
    parse(text)
    return text


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def execute(body_raw, capsule_raw, model):
    validate_body(body_raw, model)
    capsule = parse(capsule_raw)
    if type(capsule) is not dict:
        raise ModelOnlyRefused('canonical_capsule_refused')
    token = capsule.get('token')
    expiry = capsule.get('expires_at')
    if (type(token) is not str or not token.startswith('v2.') or len(token) > 16384
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
            or capsule.get('model') != model
            or any(type(capsule.get(k)) is not str
                   or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', capsule[k]) is None
                   for k in ('run_id', 'host'))
            or type(expiry) not in (int, float) or not time.time() + 1 < expiry <= time.time() + 7500):
        raise ModelOnlyRefused('canonical_capsule_refused')
    request = Request(URL, data=body_raw, method='POST', headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token,
        'User-Agent': 'mastermind-canonical-paid-model/1',
        'X-MM-Worker-Model': model, 'X-MM-Run-Id': capsule['run_id'],
        'X-MM-Host': capsule['host'],
    })
    # Disable ambient proxy settings and redirects; the signed capability can
    # reach only the existing lane-loopback controller transport. One POST.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=min(7000, expiry - time.time())) as response:
        if response.status != 200:
            raise ModelOnlyRefused('model_only_transport_refused')
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ModelOnlyRefused('model_only_response_refused')
    return result_bytes(raw)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) != 3:
            raise ModelOnlyRefused('model_only_arguments_refused')
        body = private_input(Path(args[0]), MAX_BODY)
        capsule = private_input(Path(args[1]), MAX_CAPSULE)
        result = execute(body, capsule, args[2])
        sys.stdout.buffer.write(result)
        return 0
    except Exception:
        # Original owner retains process/transport failure; no partial response,
        # capability, input path, exception message or provider prose escapes.
        print('CANONICAL_PAID_MODEL_ONLY_UNAVAILABLE', file=sys.stderr)
        return 78


if __name__ == '__main__':
    raise SystemExit(main())
