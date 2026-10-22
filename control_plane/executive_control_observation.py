"""Closed nonsecret Control observation; data only, never a peer or grant."""
from __future__ import annotations

import hashlib
import json
import re
import stat

from ops.executive_os.capacity_broker_topology import CONTROL_UID

SCHEMA = 'mastermind.control_observation/v1'
MAX_BYTES = 8192
CONFIG_MAX_BYTES = 4194304
CONTROL_PATH = '/Library/Application Support/MastermindExecutive/config/control.json'
OBSERVATION_PATH = '/Library/Application Support/MastermindExecutive/config/control-observation.json'
TRANSACTION_PATH = '/Library/Application Support/MastermindExecutive/config/autonomy-transaction.lock'
FIELDS = frozenset({'schema', 'source_release_sha', 'control_sha256', 'control_identity',
                    'control_uid', 'python_runtime_provenance_digest', 'control_acl_absent'})


class ControlObservationError(ValueError):
    pass


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ControlObservationError('duplicate_observation_key')
        value[key] = item
    return value


def _reject_constant(value):
    raise ControlObservationError('nonfinite_observation')


def _json(raw, maximum, *, ascii_only):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ControlObservationError('observation_size')
    try:
        value = json.loads(raw.decode('ascii' if ascii_only else 'utf-8'),
                           object_pairs_hook=_pairs, parse_constant=_reject_constant)
        json.dumps(value, allow_nan=False, ensure_ascii=False).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ControlObservationError('observation_json') from exc
    if type(value) is not dict:
        raise ControlObservationError('observation_object')
    return value


def _hex(value, length):
    return (type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}', value)
            is not None and set(value) != {'0'})


def object_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def validate_identity(value):
    if (type(value) not in (tuple, list) or len(value) != 9
            or any(type(v) is not int or not 0 <= v < 2**64 for v in value)):
        raise ControlObservationError('control_identity_shape')
    dev, ino, mode, uid, gid, links, size, mtime, ctime = value
    if (ino < 1 or not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o440
            or uid != 0 or gid != CONTROL_UID or links != 1
            or not 0 < size <= CONFIG_MAX_BYTES):
        raise ControlObservationError('control_identity_untrusted')
    return tuple(value)


def parse_observation(raw):
    value = _json(raw, MAX_BYTES, ascii_only=True)
    if (set(value) != FIELDS or value['schema'] != SCHEMA
            or type(value['control_uid']) is not int or value['control_uid'] != CONTROL_UID
            or value['control_acl_absent'] is not True
            or not _hex(value['source_release_sha'], 40)
            or not _hex(value['control_sha256'], 64)
            or not _hex(value['python_runtime_provenance_digest'], 64)):
        raise ControlObservationError('observation_schema')
    validate_identity(value['control_identity'])
    return value


def encode_observation(control_bytes, identity, expected_sha):
    """Pure projection; the root publisher must supply actual trusted reads."""
    document = _json(control_bytes, CONFIG_MAX_BYTES, ascii_only=False)
    identity = validate_identity(identity)
    if (identity[6] != len(control_bytes)
            or document.get('schema_version') != 'mastermind.executive_control_config/v1'
            or not _hex(expected_sha, 40) or document.get('proof_base_sha') != expected_sha
            or type(document.get('control_uid')) is not int or document['control_uid'] != CONTROL_UID):
        raise ControlObservationError('control_source_mismatch')
    value = dict(schema=SCHEMA, source_release_sha=expected_sha,
                 control_sha256=hashlib.sha256(control_bytes).hexdigest(),
                 control_identity=list(identity), control_uid=CONTROL_UID,
                 python_runtime_provenance_digest=document.get('python_runtime_provenance_digest'),
                 control_acl_absent=True)
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n').encode('ascii')
    parse_observation(raw)
    return raw
