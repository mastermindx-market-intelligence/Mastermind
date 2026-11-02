"""Validate a private launch capsule; the gateway authenticates its bearer."""
import json
import math
import os
import re
import stat

ERROR = 'worker capsule refused'
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
TOKEN = re.compile(r'v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')
ENDPOINT = re.compile(r'http://127\.0\.0\.1:([0-9]{1,5})')
HEX = re.compile(r'[0-9a-f]{64}')
SCOPE = frozenset(('root','lease_id','account','run_id','host','model'))
SOURCES = frozenset(('go_shim.py','go_lease_capability.py','go_lease_gateway.py'))
CAPSULE_KEYS = SCOPE | {'schema','token','endpoint','expires_at','source_sha256'}
HEALTH_KEYS = SCOPE | {'ok','worker_capabilities','source_sha256','expires_at'}


class CapsuleError(ValueError):
    pass


def _require(condition):
    if not condition:
        raise CapsuleError(ERROR)


def _number(value):
    _require(type(value) in (int,float) and math.isfinite(value))


def _pairs(items):
    result = {}
    for key,value in items:
        _require(key not in result)
        result[key] = value
    return result


def _constant(value):
    raise CapsuleError(ERROR)


def load_capsule(path, *, expected, now):
    try:
        _number(now);_require(now >= 0)
        _require(isinstance(expected,dict) and set(expected)==SCOPE)
        fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                     and stat.S_IMODE(before.st_mode)==0o600 and 0<before.st_size<=8192)
            chunks=[];size=0
            while size<8193:
                chunk=os.read(fd,8193-size)
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
            after=os.fstat(fd)
            _require(size==before.st_size and
                     (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                     (after.st_size,after.st_mtime_ns,after.st_ctime_ns))
        finally:os.close(fd)
        value=json.loads(b''.join(chunks).decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant)
        _require(isinstance(value,dict) and set(value)==CAPSULE_KEYS)
        _require(value['schema']=='mastermind.go.worker-launch.v1')
        token=value['token'];_require(isinstance(token,str) and len(token)<=4096 and TOKEN.fullmatch(token))
        endpoint=value['endpoint'];_require(isinstance(endpoint,str))
        match=ENDPOINT.fullmatch(endpoint);_require(match and 1<=int(match.group(1))<=65535)
        for field in SCOPE:
            item=value[field]
            _require(isinstance(item,str) and IDENT.fullmatch(item) and item==expected[field])
        sources=value['source_sha256'];_require(isinstance(sources,dict) and set(sources)==SOURCES)
        for digest in sources.values():_require(isinstance(digest,str) and HEX.fullmatch(digest))
        _number(value['expires_at']);_require(value['expires_at']>now)
        return value
    except Exception:
        raise CapsuleError(ERROR) from None


def validate_health(capsule, health):
    try:
        _require(isinstance(health,dict) and set(health)==HEALTH_KEYS)
        _require(health['ok'] is True and health['worker_capabilities']=='lease-v1')
        for field in SCOPE:_require(health[field]==capsule[field])
        _require(health['source_sha256']==capsule['source_sha256'])
        _number(health['expires_at']);_require(health['expires_at']==capsule['expires_at'])
    except Exception:
        raise CapsuleError(ERROR) from None
