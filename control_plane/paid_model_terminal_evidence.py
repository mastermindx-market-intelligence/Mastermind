"""Pure terminal-evidence validation for the canonical paid model-only lifecycle.

This module validates sealed worker-result evidence as DATA only.  It is a
self-contained standard-library validator: no I/O, no process inspection, no
provider, network, lease, config or live effects, and no imports from the
surrounding runtime (which may be unavailable where this runs).

Authority boundary
------------------
* This qualifies closed DATA and round-trips through the existing paid owner
  wire validators. It does not authenticate transport, current admission,
  immutable Capacity/Runtime claims, or the actual Control filesystem owner.
* The process reference must be the exact PaidModelProcessRef or its closed
  serialized shape. The full attestation is independently qualified upstream
  by the principal owner against the actual claim and original Runtime pin.
* Actual binary/process, host qualification, capture paths, complete delivery,
  and original terminal coordinates are required. No provider home, observed
  Git state, secret canary or UID sweep is invented for model-only execution.
* Control retention and remote owned-process cleanup remain distinct facts.
  This return is delivery evidence DATA, never review or product acceptance.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
from pathlib import PurePosixPath

from control_plane.worker_execution_contract import PaidModelProcessRef
from control_plane.paid_fabric_wire import (PaidWireRefused, require_paid_physical,
    validate_owned_terminal as validate_owned_paid_terminal)
import re

__all__ = ['PaidModelTerminalRefused', 'validate_paid_model_terminal_evidence']


class PaidModelTerminalRefused(ValueError):
    """Raised when paid model terminal evidence fails closed validation."""


SCHEMA_SEALED_EVIDENCE = 'mastermind.paid_model_sealed_worker_result_evidence/v1'
SCHEMA_OWNED_LAUNCH = 'mastermind.paid_model_owned_launch/v1'
SCHEMA_OWNED_TERMINAL = 'mastermind.paid_model_owned_terminal/v1'
SCHEMA_PROCESS_RECEIPT = 'mastermind.local_owned_process_receipt.v1'
SCHEMA_CAPTURE = 'mastermind.paid_model_capture_evidence/v1'
SCHEMA_CAPTURE_CONTRACT = 'mastermind.paid_model_capture/v1'
SCHEMA_COLLECTION = 'mastermind.executive_collection_evidence/v1'
SCHEMA_SEAL = 'mastermind.executive_assignment_seal/v1'
SCHEMA_CONTROL_RETENTION = 'mastermind.paid_model_control_retention/v1'
SCHEMA_GRANT = 'mastermind.executive_effective_grant/v1'
SCHEMA_ATTESTATION = 'mastermind.executive_paid_model_launch_attestation/v1'

MAX_STDOUT_BYTES = 1024 * 1024
MAX_ENVELOPE_BYTES = 1024 * 1024

_EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
_SHA256_RE = re.compile(r'[0-9a-f]{64}\Z')
_RUN_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_ALLOWED_AUTHORITIES = frozenset({'READ', 'RESEARCH'})
_CLEANUP_STATUS = frozenset({'not_needed', 'terminated'})

# Identity field naming differs between the process image/attestation names
# and the qualified process reference names; both spellings are evidenced by
# the owned producer sources.
_IDENTITY_ALIASES = {
    'start_identity': 'process_start_identity',
    'boot_id': 'boot_session_id',
}

TOP_KEYS = (
    'schema_version', 'launch_identity', 'owned_launch', 'owned_terminal',
    'capture', 'collection_receipt', 'collection_receipt_digest',
    'validation_receipts', 'validation_receipts_digest',
    'assignment_seal_receipt', 'assignment_seal_receipt_digest',
)
OWNED_LAUNCH_KEYS = (
    'schema', 'run_id', 'model', 'transport_host', 'lease_id', 'pid',
    'process_identity', 'observed_user', 'launch_nonce', 'started_at',
    'python_path', 'python_version', 'source_manifest_sha256',
    'request_body_sha256', 'capsule_binding_sha256', 'capture_contract', 'capture_paths', 'host_context',
)
OWNED_TERMINAL_KEYS = ('schema', 'run_id', 'launch_sha256', 'terminal')
TERMINAL_RECEIPT_KEYS = (
    'schema', 'label', 'pid', 'pgid', 'started_at', 'ended_at', 'returncode',
    'timed_out', 'nice_requested', 'nice_applied', 'stdout_bytes',
    'stdout_sha256', 'stderr_bytes', 'stderr_sha256', 'stdout_truncated',
    'stderr_truncated', 'runtime_failure_code', 'cleanup',
)
CAPTURE_KEYS = (
    'schema_version', 'stdout_utf8', 'stdout_sha256', 'stdout_bytes',
    'stderr_sha256', 'stderr_bytes',
)
COLLECTION_RECEIPT_KEYS = (
    'schema_version', 'collection', 'fabric_cleanup', 'effective_grant_digest',
)
COLLECTION_KEYS = (
    'process_ref', 'result', 'stdout_sha256', 'stderr_sha256', 'result_sha256',
)
RESULT_KEYS = (
    'job_id', 'run_id', 'worker_id', 'status', 'structured_output',
    'artifact_manifest', 'git_manifest', 'usage', 'provider_session_id',
    'exit_code', 'started_at', 'finished_at', 'error',
)
VALIDATION_KEYS = ('attempt_id', 'job_id', 'commands', 'effective_grant_digest')
SEAL_KEYS = ('schema_version', 'attempt_id', 'job_id', 'effective_grant_digest', 'control_seal')
CONTROL_SEAL_KEYS = ('schema_version', 'sealed_at', 'control_uid', 'paths', 'passed')
SEAL_PATH_KEYS = ('run', 'workspace')
SEAL_IDENTITY_KEYS = ('path', 'device', 'inode', 'mode', 'uid', 'gid', 'mtime_ns')
AFTER_MODE_BITS = 0o700


def _refuse(message):
    raise PaidModelTerminalRefused(message)


def _canonical_bytes(value, *, ensure_ascii, label):
    try:
        text = json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=ensure_ascii, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        _refuse(label + ' is not canonical JSON safe')
    try:
        return text.encode('ascii' if ensure_ascii else 'utf-8')
    except UnicodeEncodeError:
        _refuse(label + ' is not encodable canonical JSON text')


def _standard_digest(value, label):
    return hashlib.sha256(
        _canonical_bytes(value, ensure_ascii=False, label=label)).hexdigest()


def _owner_digest(value, label):
    """Digest in the owned producer's canonical form (ASCII, sorted keys)."""
    return hashlib.sha256(
        _canonical_bytes(value, ensure_ascii=True, label=label)).hexdigest()


def _canonical_equal(left, right, left_label, right_label):
    return _canonical_bytes(left, ensure_ascii=False, label=left_label) == \
        _canonical_bytes(right, ensure_ascii=False, label=right_label)


def _json_safe(value, path, _depth=0):
    if _depth > 64:
        _refuse("paid terminal JSON nesting refused")
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            _refuse(path + ' is not a finite JSON number')
        return
    if type(value) is str:
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            _refuse(path + ' is not valid UTF-8 text')
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _json_safe(item, path + '[]', _depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _refuse(path + ' has a non-string key')
            try:
                key.encode('utf-8')
            except UnicodeEncodeError:
                _refuse('paid terminal JSON key encoding refused')
            _json_safe(item, path + '.member', _depth + 1)
        return
    _refuse(path + ' is not a closed JSON-safe value')


def _exact_dict(value, label):
    if type(value) is not dict:
        _refuse(label + ' must be an exact closed dict (custom mapping refused)')
    return value


def _exact_keys(mapping, expected, label):
    present = set(mapping)
    wanted = set(expected)
    missing = sorted(wanted - present)
    unexpected = sorted(present - wanted)
    if missing or unexpected:
        _refuse(label + ' keys refused; missing=' + ','.join(missing)
                + ' unexpected=' + ','.join(unexpected))


def _require_keys(mapping, expected, label):
    missing = sorted(set(expected) - set(mapping))
    if missing:
        _refuse(label + ' missing required keys=' + ','.join(missing))


def _string_field(value, label):
    if type(value) is not str or not value:
        _refuse(label + ' must be a nonempty string')
    return value


def _sha256_field(value, label):
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _refuse(label + ' must be a lowercase 64-hex sha256 string')
    return value


def _int_field(value, label):
    if type(value) is not int:
        _refuse(label + ' must be an int (bool refused)')
    return value


def _bool_false(value, label):
    if value is not False:
        _refuse(label + ' must be exactly false')


def _bool_true(value, label):
    if value is not True:
        _refuse(label + ' must be exactly true')


def _none_field(value, label):
    if value is not None:
        _refuse(label + ' must be exactly null')


def _aware_datetime(value, label):
    _string_field(value, label)
    text = value
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        _refuse(label + ' is not a valid ISO-8601 timestamp')
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        _refuse(label + ' must be a timezone-aware ISO-8601 timestamp')
    return moment


def _match(expected, actual, label):
    """Exact comparison; bool/int and int/float confusions are refused."""
    if type(expected) is not type(actual) or expected != actual:
        _refuse(label + ' does not match the qualified expected value')


def _ref_bindings(expected_process_ref):
    try:
        if type(expected_process_ref) is PaidModelProcessRef:
            return expected_process_ref.to_dict()
        if type(expected_process_ref) is dict:
            return PaidModelProcessRef.from_dict(expected_process_ref).to_dict()
    except (TypeError, ValueError):
        pass
    _refuse('expected_process_ref must be an exact paid process reference')


def _ref_required(refmap, name, label):
    if name not in refmap:
        _refuse(label + ' unavailable: expected_process_ref lacks the ' + name
                + ' coordinate; caller qualification is required')
    return refmap[name]


def _ref_optional(refmap, name):
    return refmap.get(name)


def _attestation_view(attestation):
    _exact_keys(attestation, ('schema_version', 'profile_id', 'adapter_id',
        'execution_surface', 'binding', 'paid_route', 'worker_id', 'quota_class',
        'process_identity', 'lease_binding', 'evidence'), 'paid launch attestation')
    if (attestation['profile_id'] != 'fabric.paid.glm.sealed-input.v1'
            or attestation['adapter_id'] != 'canonical-paid-fabric'
            or attestation['execution_surface'] != 'glm-model-only'):
        _refuse('paid launch profile identity refused')
    view = {}
    for name in ('process_identity', 'paid_route', 'lease_binding', 'evidence'):
        part = _exact_dict(attestation[name], 'paid launch ' + name)
        view.update(part)
    return view


def _load_unique_json(text, label):
    def hook(items):
        result = {}
        for key, value in items:
            if key in result:
                _refuse(label + ' contains duplicate JSON object keys')
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=hook)
    except PaidModelTerminalRefused:
        raise
    except ValueError:
        _refuse(label + ' is not one complete JSON document')


def _validate_binding(expected_binding):
    binding = _exact_dict(expected_binding, 'expected_binding')
    _json_safe(binding, 'expected_binding')
    _exact_keys(binding, ('root_id', 'job_id', 'attempt_id', 'effective_grant_digest',
                          'commission_sha256'), 'expected_binding')
    for name in ('root_id', 'job_id', 'attempt_id'):
        value = _string_field(binding[name], 'expected_binding.' + name)
        if _RUN_ID_RE.fullmatch(value) is None:
            _refuse('expected binding identity refused')
    for name in ('effective_grant_digest', 'commission_sha256'):
        _sha256_field(binding[name], 'expected_binding.' + name)
    return binding, dict(binding)


def _validate_grant(expected_grant, binding, binding_values):
    grant = _exact_dict(expected_grant, 'expected_grant')
    _json_safe(grant, 'expected_grant')
    if grant.get('schema_version') != SCHEMA_GRANT:
        _refuse('expected_grant schema refused')
    _match(binding_values['job_id'],
           _string_field(grant.get('job_id'), 'expected_grant.job_id'),
           'expected_grant.job_id')
    _exact_keys(grant, ('schema_version', 'authorities', 'write_paths', 'validation_argv',
                         'policy_sha', 'job_id', 'role'), 'expected_grant')
    _sha256_field(grant['policy_sha'], 'expected_grant.policy_sha')
    if grant['role'] not in {'work', 'repair'}:
        _refuse('paid result role refused')
    authorities = grant.get('authorities')
    if type(authorities) is not list:
        _refuse('expected_grant.authorities must be a list')
    for item in authorities:
        _string_field(item, 'expected_grant.authorities entry')
    unique = set(authorities)
    if not unique <= _ALLOWED_AUTHORITIES or 'READ' not in unique or len(unique) != len(authorities):
        _refuse('expected_grant.authorities must be READ or READ+RESEARCH; '
                'other authorities including RUN_TESTS are refused')
    for name in ('validation_argv', 'write_paths'):
        items = grant.get(name)
        if type(items) is not list:
            _refuse('expected_grant.' + name + ' must be a list')
        if items != []:
            _refuse('paid grant forbids writes and validation commands')
    digest = _standard_digest(grant, 'expected_grant')
    _match(binding_values['effective_grant_digest'], digest,
           'expected_binding.effective_grant_digest')
    return digest


def _validate_launch_identity(launch_identity, binding,
                              expected_launch_identity_sha256):
    _sha256_field(expected_launch_identity_sha256, 'expected_launch_identity_sha256')
    identity = _exact_dict(launch_identity, 'launch_identity')
    _json_safe(identity, 'launch_identity')
    _exact_keys(identity, ('physical_binding_sha256', 'request'), 'launch_identity')
    physical_sha = _sha256_field(identity['physical_binding_sha256'], 'physical binding digest')
    request = _exact_dict(identity['request'], 'launch_identity.request')
    if request.get('binding') != binding or request.get('physical_binding_sha256') != physical_sha:
        _refuse('launch identity original binding differs')
    try:
        require_paid_physical(request)
    except PaidWireRefused:
        _refuse('paid physical source contract refused')
    physical = _exact_dict(request.get('paid_physical_binding'), 'paid physical binding')
    source = _exact_dict(request.get('paid_source_config'), 'paid source config')
    if _standard_digest(physical, 'paid physical binding') != physical_sha:
        _refuse('paid physical binding digest differs')
    if (_standard_digest(source, 'paid source config') != physical.get('worker_source_config_digest')
            or source.get('capture_root') != physical.get('capture_root')):
        _refuse('paid source config identity differs')
    root = source.get('capture_root')
    if (type(root) is not str or not root.startswith('/') or root == '/'
            or str(PurePosixPath(root)) != root or '..' in PurePosixPath(root).parts):
        _refuse('paid capture root refused')
    if _standard_digest(identity, 'launch_identity') != expected_launch_identity_sha256:
        _refuse('launch_identity digest differs from its original pin')


def _validate_owned_launch(owned_launch, attestation, att_view, refmap,
                           binding_values):
    launch = _exact_dict(owned_launch, 'owned_launch')
    _exact_keys(launch, OWNED_LAUNCH_KEYS, 'owned_launch')
    if launch.get('schema') != SCHEMA_OWNED_LAUNCH:
        _refuse('owned_launch schema refused')
    run_id = _string_field(launch.get('run_id'), 'owned_launch.run_id')
    if _RUN_ID_RE.fullmatch(run_id) is None:
        _refuse('owned_launch.run_id is not an owned run identifier')
    pid = _int_field(launch.get('pid'), 'owned_launch.pid')
    if pid <= 0:
        _refuse('owned_launch.pid must be positive')
    started_at = _aware_datetime(launch.get('started_at'),
                                 'owned_launch.started_at')
    nonce = _string_field(launch.get('launch_nonce'),
                          'owned_launch.launch_nonce')
    for name in ('source_manifest_sha256', 'request_body_sha256',
                 'capsule_binding_sha256'):
        _sha256_field(launch.get(name), 'owned_launch.' + name)
    _string_field(launch.get('model'), 'owned_launch.model')
    _string_field(launch.get('transport_host'), 'owned_launch.transport_host')
    _string_field(launch.get('lease_id'), 'owned_launch.lease_id')
    _string_field(launch.get('observed_user'), 'owned_launch.observed_user')
    _string_field(launch.get('python_path'), 'owned_launch.python_path')
    _string_field(launch.get('python_version'), 'owned_launch.python_version')

    # Cross-compare every field the qualified expectations actually carry.
    # Missing expectation fields stay a documented caller gap, never a dummy.
    for name in ('run_id', 'model', 'transport_host', 'lease_id', 'pid',
                 'observed_user', 'launch_nonce', 'started_at', 'python_path',
                 'python_version', 'source_manifest_sha256',
                 'request_body_sha256', 'capsule_binding_sha256',
                 'capture_contract'):
        expected = att_view.get(name)
        if expected is not None:
            _match(expected, launch[name], 'owned_launch.' + name)
    _match(_ref_required(refmap, 'run_id', 'owned_launch.run_id'),
           run_id, 'owned_launch.run_id')
    _match(_ref_required(refmap, 'pid', 'owned_launch.pid'), pid,
           'owned_launch.pid')
    _match(_ref_required(refmap, 'started_at', 'owned_launch.started_at'),
           launch['started_at'], 'owned_launch.started_at')
    for name in ('worker_id', 'model', 'lease_id', 'observed_user',
                 'launch_nonce', 'parent_pid', 'effective_uid', 'real_uid',
                 'effective_gid', 'real_gid'):
        expected = _ref_optional(refmap, name)
        if expected is not None and name in launch:
            _match(expected, launch[name], 'owned_launch.' + name)

    image = _exact_dict(launch.get('process_identity'),
                        'owned_launch.process_identity')
    _json_safe(image, 'owned_launch.process_identity')
    _exact_keys(image, ('start_identity', 'pgid', 'session_id', 'effective_uid', 'effective_gid',
        'real_uid', 'real_gid', 'parent_pid', 'boot_id', 'device', 'inode', 'mode', 'uid', 'gid',
        'size', 'mtime_ns', 'ctime_ns', 'sha256'), 'owned process image')
    for key in ('sha256', 'device', 'inode', 'mode', 'uid', 'gid', 'size', 'mtime_ns'):
        _match(refmap['binary'][key], image[key], 'owned process binary identity')
    _int_field(image['ctime_ns'], 'owned process image ctime')
    _match(refmap['binary']['path'], launch['python_path'], 'owned Python path')
    _match(refmap['binary']['version'], launch['python_version'], 'owned Python version')
    for name in ('parent_pid', 'pgid', 'session_id', 'effective_uid',
                 'real_uid', 'effective_gid', 'real_gid'):
        if name not in image:
            _refuse('owned_launch.process_identity missing actual observed '
                    'field ' + name)
        _int_field(image[name], 'owned_launch.process_identity.' + name)
    for name in ('pgid', 'session_id'):
        if image[name] != pid:
            _refuse('owned_launch.process_identity.' + name
                    + ' does not match the owned process coordinates')
    _match(_ref_required(refmap, 'pgid', 'owned_launch.process_identity.pgid'),
           image['pgid'], 'owned_launch.process_identity.pgid')
    _match(_ref_required(refmap, 'session_id',
                         'owned_launch.process_identity.session_id'),
           image['session_id'], 'owned_launch.process_identity.session_id')
    for name in ('effective_uid', 'real_uid', 'effective_gid', 'real_gid'):
        _match(_ref_required(refmap, name,
                             'owned_launch.process_identity.' + name),
               image[name], 'owned_launch.process_identity.' + name)
    for key, observed in image.items():
        ref_name = _IDENTITY_ALIASES.get(key, key)
        expected = refmap.get(ref_name)
        if expected is None:
            expected = att_view.get(key)
        if expected is not None:
            _match(expected, observed,
                   'owned_launch.process_identity.' + key)

    contract = _exact_dict(launch.get('capture_contract'),
                           'owned_launch.capture_contract')
    _json_safe(contract, 'owned_launch.capture_contract')
    _exact_keys(contract, ('schema', 'capture_limit_bytes', 'stdout_encoding', 'stderr_encoding',
                           'require_complete', 'require_cleanup'), 'capture contract')
    if contract.get('schema') != SCHEMA_CAPTURE_CONTRACT:
        _refuse('owned_launch.capture_contract schema refused')
    for flag in ('require_complete', 'require_cleanup'):
        if flag in contract:
            _bool_true(contract[flag],
                       'owned_launch.capture_contract.' + flag)
    for name in ('stdout_encoding', 'stderr_encoding'):
        if name in contract and contract[name] != 'utf-8':
            _refuse('owned_launch.capture_contract.' + name
                    + ' must be utf-8')
    limit = contract.get('capture_limit_bytes')
    if limit is not None:
        _int_field(limit, 'owned_launch.capture_contract.capture_limit_bytes')
        if limit <= 0 or limit > MAX_STDOUT_BYTES:
            _refuse('owned_launch.capture_contract.capture_limit_bytes is '
                    'outside the closed capture limit')
    return run_id, pid, started_at


def _validate_owned_terminal(owned_terminal, owned_launch, run_id, pid,
                             started_at, refmap, attempt_id):
    try:
        validate_owned_paid_terminal(owned_terminal, owned_launch)
    except PaidWireRefused:
        _refuse('actual paid owned terminal contract refused')
    terminal_wrap = _exact_dict(owned_terminal, 'owned_terminal')
    _exact_keys(terminal_wrap, OWNED_TERMINAL_KEYS, 'owned_terminal')
    if terminal_wrap.get('schema') != SCHEMA_OWNED_TERMINAL:
        _refuse('owned_terminal schema refused')
    _match(run_id, _string_field(terminal_wrap.get('run_id'),
                                 'owned_terminal.run_id'),
           'owned_terminal.run_id')
    _sha256_field(terminal_wrap.get('launch_sha256'),
                  'owned_terminal.launch_sha256')
    if terminal_wrap['launch_sha256'] != _owner_digest(owned_launch,
                                                       'owned_launch'):
        _refuse('owned_terminal.launch_sha256 does not match the owned '
                'launch record digest')

    receipt = _exact_dict(terminal_wrap.get('terminal'),
                          'owned_terminal.terminal')
    _json_safe(receipt, 'owned_terminal.terminal')
    # The actual lane receipt carries variable diagnostic fields; they are
    # preserved unchanged.  Every field the owner source defines is required.
    _require_keys(receipt, TERMINAL_RECEIPT_KEYS, 'owned_terminal.terminal')
    if receipt.get('schema') != SCHEMA_PROCESS_RECEIPT:
        _refuse('owned_terminal.terminal schema refused')
    label = _string_field(receipt.get('label'), 'owned_terminal.terminal.label')
    if label != attempt_id or label != run_id:
        _refuse('owned_terminal.terminal.label does not match the attempt '
                'run identity')
    receipt_pid = _int_field(receipt.get('pid'),
                             'owned_terminal.terminal.pid')
    receipt_pgid = _int_field(receipt.get('pgid'),
                              'owned_terminal.terminal.pgid')
    if receipt_pid != pid or receipt_pgid != pid:
        _refuse('owned_terminal.terminal process coordinates do not match '
                'the owned launch')
    _match(started_at,
           _aware_datetime(receipt.get('started_at'),
                           'owned_terminal.terminal.started_at'),
           'owned_terminal.terminal.started_at')
    _aware_datetime(receipt.get('ended_at'),
                    'owned_terminal.terminal.ended_at')
    returncode = _int_field(receipt.get('returncode'),
                            'owned_terminal.terminal.returncode')
    if returncode != 0:
        _refuse('owned_terminal.terminal.returncode must be zero')
    _bool_false(receipt.get('timed_out'),
                'owned_terminal.terminal.timed_out')
    _bool_false(receipt.get('stdout_truncated'),
                'owned_terminal.terminal.stdout_truncated')
    _bool_false(receipt.get('stderr_truncated'),
                'owned_terminal.terminal.stderr_truncated')
    _none_field(receipt.get('runtime_failure_code'),
                'owned_terminal.terminal.runtime_failure_code')
    stdout_bytes = _int_field(receipt.get('stdout_bytes'),
                              'owned_terminal.terminal.stdout_bytes')
    if stdout_bytes < 0:
        _refuse('owned_terminal.terminal.stdout_bytes must not be negative')
    stdout_sha256 = _sha256_field(receipt.get('stdout_sha256'),
                                  'owned_terminal.terminal.stdout_sha256')
    stderr_bytes = _int_field(receipt.get('stderr_bytes'),
                              'owned_terminal.terminal.stderr_bytes')
    if stderr_bytes != 0:
        _refuse('owned_terminal.terminal.stderr_bytes must be zero; paid '
                'runs retain no stderr contents')
    stderr_sha256 = _sha256_field(receipt.get('stderr_sha256'),
                                  'owned_terminal.terminal.stderr_sha256')
    if stderr_sha256 != _EMPTY_SHA256:
        _refuse('owned_terminal.terminal.stderr_sha256 must be the empty '
                'input digest')
    cleanup = _exact_dict(receipt.get('cleanup'),
                          'owned_terminal.terminal.cleanup')
    _json_safe(cleanup, 'owned_terminal.terminal.cleanup')
    _require_keys(cleanup,
                  ('census_proven', 'identity_verified', 'residual_count',
                   'status', 'session_id'),
                  'owned_terminal.terminal.cleanup')
    _bool_true(cleanup.get('census_proven'),
               'owned_terminal.terminal.cleanup.census_proven')
    _bool_true(cleanup.get('identity_verified'),
               'owned_terminal.terminal.cleanup.identity_verified')
    residual_count = cleanup.get('residual_count')
    if type(residual_count) is not int:
        _refuse('owned_terminal.terminal.cleanup.residual_count must be an '
                'exact int (bool refused)')
    if residual_count != 0:
        _refuse('owned_terminal.terminal.cleanup.residual_count must be '
                'exactly zero')
    if cleanup.get('status') not in _CLEANUP_STATUS:
        _refuse('owned_terminal.terminal.cleanup.status refused')
    _match(_ref_required(refmap, 'session_id',
                         'owned_terminal.terminal.cleanup.session_id'),
           cleanup.get('session_id'),
           'owned_terminal.terminal.cleanup.session_id')
    return stdout_bytes, stdout_sha256, stderr_bytes, stderr_sha256, cleanup


def _validate_capture(capture, contract_limit, terminal_stdout_bytes,
                      terminal_stdout_sha256, terminal_stderr_bytes,
                      terminal_stderr_sha256, expected_result_envelope):
    capture_data = _exact_dict(capture, 'capture')
    _exact_keys(capture_data, CAPTURE_KEYS, 'capture')
    if capture_data.get('schema_version') != SCHEMA_CAPTURE:
        _refuse('capture schema_version refused')
    stdout_text = capture_data.get('stdout_utf8')
    if type(stdout_text) is not str:
        _refuse('capture.stdout_utf8 must be a string')
    if '\x00' in stdout_text:
        _refuse('capture.stdout_utf8 contains a NUL character')
    try:
        stdout_raw = stdout_text.encode('utf-8')
    except UnicodeEncodeError:
        _refuse('capture.stdout_utf8 is not exactly encodable UTF-8 text')
    stdout_bytes = _int_field(capture_data.get('stdout_bytes'),
                              'capture.stdout_bytes')
    if len(stdout_raw) != stdout_bytes:
        _refuse('capture.stdout_bytes does not match the exact stdout byte '
                'length')
    if stdout_bytes > MAX_STDOUT_BYTES:
        _refuse('capture stdout exceeds the closed 1 MiB capture limit')
    if contract_limit is not None and stdout_bytes > contract_limit:
        _refuse('capture stdout exceeds the owned capture contract limit')
    stdout_sha256 = _sha256_field(capture_data.get('stdout_sha256'),
                                  'capture.stdout_sha256')
    if hashlib.sha256(stdout_raw).hexdigest() != stdout_sha256:
        _refuse('capture.stdout_sha256 does not match the exact stdout bytes')
    if stdout_bytes != terminal_stdout_bytes or \
            stdout_sha256 != terminal_stdout_sha256:
        _refuse('capture stdout evidence does not match the owned terminal '
                'receipt')
    stderr_bytes = _int_field(capture_data.get('stderr_bytes'),
                              'capture.stderr_bytes')
    if stderr_bytes != 0 or stderr_bytes != terminal_stderr_bytes:
        _refuse('capture.stderr_bytes must be zero and match the owned '
                'terminal receipt')
    stderr_sha256 = _sha256_field(capture_data.get('stderr_sha256'),
                                  'capture.stderr_sha256')
    if stderr_sha256 != _EMPTY_SHA256 or \
            stderr_sha256 != terminal_stderr_sha256:
        _refuse('capture.stderr_sha256 must be the empty input digest and '
                'match the owned terminal receipt')

    envelope = _exact_dict(expected_result_envelope,
                           'expected_result_envelope')
    envelope_raw = _canonical_bytes(envelope, ensure_ascii=False,
                                    label='expected_result_envelope')
    if len(envelope_raw) > MAX_ENVELOPE_BYTES:
        _refuse('expected_result_envelope exceeds the closed 1 MiB envelope '
                'limit')
    parsed = _load_unique_json(stdout_text, 'capture.stdout_utf8')
    if not _canonical_equal(parsed, envelope, 'capture.stdout_utf8',
                            'expected_result_envelope'):
        _refuse('the complete stdout JSON document does not equal the '
                'expected result envelope')
    return stdout_sha256, stderr_sha256


def _validate_collection(collection_receipt, refmap, binding_values, run_id,
                         capture_stdout_sha256, capture_stderr_sha256,
                         expected_result_envelope, expected_process_ref,
                         grant_digest, cleanup):
    receipt = _exact_dict(collection_receipt, 'collection_receipt')
    _exact_keys(receipt, COLLECTION_RECEIPT_KEYS, 'collection_receipt')
    if receipt.get('schema_version') != SCHEMA_COLLECTION:
        _refuse('collection_receipt schema_version refused')
    collection = _exact_dict(receipt.get('collection'), 'collection')
    _exact_keys(collection, COLLECTION_KEYS, 'collection')

    ref_record = _exact_dict(collection.get('process_ref'),
                             'collection.process_ref')
    _exact_keys(ref_record, set(refmap), 'collection.process_ref')
    for name in sorted(refmap):
        _match(refmap[name], ref_record[name],
               'collection.process_ref.' + name)

    result = _exact_dict(collection.get('result'), 'collection.result')
    _exact_keys(result, RESULT_KEYS, 'collection.result')
    _match(binding_values['job_id'],
           _string_field(result.get('job_id'), 'collection.result.job_id'),
           'collection.result.job_id')
    _match(run_id, _string_field(result.get('run_id'),
                                 'collection.result.run_id'),
           'collection.result.run_id')
    _match(_ref_required(refmap, 'worker_id', 'collection.result.worker_id'),
           _string_field(result.get('worker_id'),
                         'collection.result.worker_id'),
           'collection.result.worker_id')
    if result.get('status') != 'SUCCEEDED':
        _refuse('collection.result.status must be SUCCEEDED')
    if type(result.get('structured_output')) is not dict:
        _refuse('collection.result.structured_output must be a dict')
    if not _canonical_equal(result.get('structured_output'),
                            expected_result_envelope,
                            'collection.result.structured_output',
                            'expected_result_envelope'):
        _refuse('collection.result.structured_output does not equal the '
                'expected result envelope')
    if result.get('artifact_manifest') != []:
        _refuse('collection.result.artifact_manifest must be an empty list')
    if result.get('git_manifest') != {} or \
            type(result.get('git_manifest')) is not dict:
        _refuse('collection.result.git_manifest must be an empty dict')
    usage = _exact_dict(result.get('usage'), 'collection.result.usage')
    _json_safe(usage, 'collection.result.usage')
    _none_field(result.get('provider_session_id'),
                'collection.result.provider_session_id')
    exit_code = _int_field(result.get('exit_code'),
                           'collection.result.exit_code')
    if exit_code != 0:
        _refuse('collection.result.exit_code must be zero')
    _none_field(result.get('error'), 'collection.result.error')
    _match(_ref_required(refmap, 'started_at', 'collection.result.started_at'),
           _string_field(result.get('started_at'),
                         'collection.result.started_at'),
           'collection.result.started_at')
    _aware_datetime(result.get('finished_at'),
                    'collection.result.finished_at')

    _sha256_field(collection.get('stdout_sha256'),
                  'collection.stdout_sha256')
    _sha256_field(collection.get('stderr_sha256'),
                  'collection.stderr_sha256')
    result_sha256 = _sha256_field(collection.get('result_sha256'),
                                  'collection.result_sha256')
    if collection['stdout_sha256'] != capture_stdout_sha256:
        _refuse('collection.stdout_sha256 does not match the capture stdout '
                'digest')
    if collection['stderr_sha256'] != capture_stderr_sha256:
        _refuse('collection.stderr_sha256 does not match the capture stderr '
                'digest')
    if result_sha256 != capture_stdout_sha256:
        _refuse('collection.result_sha256 must equal the stdout digest; the '
                'retained result file holds the exact stdout bytes')

    fabric_cleanup = _exact_dict(receipt.get('fabric_cleanup'),
                                 'collection_receipt.fabric_cleanup')
    _json_safe(fabric_cleanup, 'collection_receipt.fabric_cleanup')
    if not _canonical_equal(fabric_cleanup, cleanup,
                            'collection_receipt.fabric_cleanup',
                            'owned_terminal.terminal.cleanup'):
        _refuse('collection_receipt.fabric_cleanup must equal the owned '
                'remote terminal cleanup receipt')
    _match(grant_digest,
           _sha256_field(receipt.get('effective_grant_digest'),
                         'collection_receipt.effective_grant_digest'),
           'collection_receipt.effective_grant_digest')


def _validate_validation_receipts(validation_receipts, binding_values,
                                  expected_grant, grant_digest):
    receipt = _exact_dict(validation_receipts, 'validation_receipts')
    _exact_keys(receipt, VALIDATION_KEYS, 'validation_receipts')
    _match(binding_values['attempt_id'],
           _string_field(receipt.get('attempt_id'),
                         'validation_receipts.attempt_id'),
           'validation_receipts.attempt_id')
    _match(binding_values['job_id'],
           _string_field(receipt.get('job_id'),
                         'validation_receipts.job_id'),
           'validation_receipts.job_id')
    commands = receipt.get('commands')
    if type(commands) is not list:
        _refuse('validation_receipts.commands must be a list')
    for item in commands:
        _string_field(item, 'validation_receipts.commands entry')
    argv = _exact_dict(expected_grant, 'expected_grant').get('validation_argv')
    if type(argv) is not list:
        _refuse('expected_grant.validation_argv must be a list')
    if not _canonical_equal(commands, argv, 'validation_receipts.commands',
                            'expected_grant.validation_argv'):
        _refuse('validation_receipts.commands must exactly match '
                'expected_grant.validation_argv')
    _match(grant_digest,
           _sha256_field(receipt.get('effective_grant_digest'),
                         'validation_receipts.effective_grant_digest'),
           'validation_receipts.effective_grant_digest')


def _validate_seal_identity(identity, label, control_uid):
    _exact_keys(identity, SEAL_IDENTITY_KEYS, label)
    _string_field(identity.get('path'), label + '.path')
    for name in ('device', 'inode', 'uid', 'gid', 'mtime_ns'):
        field = _int_field(identity.get(name), label + '.' + name)
        if field < 0:
            _refuse(label + '.' + name + ' must not be negative')
    mode = _int_field(identity.get('mode'), label + '.mode')
    return mode


def _validate_seal(seal, binding_values, grant_digest):
    wrapper = _exact_dict(seal, 'assignment_seal_receipt')
    _exact_keys(wrapper, SEAL_KEYS, 'assignment_seal_receipt')
    if wrapper['schema_version'] != SCHEMA_CONTROL_RETENTION:
        _refuse('paid Control retention schema refused')
    for key in ('attempt_id', 'job_id'):
        _match(binding_values[key], wrapper[key], 'paid Control retention identity')
    _match(grant_digest, wrapper['effective_grant_digest'], 'paid Control retention grant')
    record = _exact_dict(wrapper['control_seal'], 'Control assignment seal')
    _exact_keys(record, CONTROL_SEAL_KEYS, 'Control assignment seal')
    if record['schema_version'] != SCHEMA_SEAL:
        _refuse('Control assignment seal schema refused')
    _bool_true(record['passed'], 'Control assignment seal passed')
    _aware_datetime(record.get('sealed_at'),
                    'assignment_seal_receipt.sealed_at')
    control_uid = _int_field(record.get('control_uid'),
                             'assignment_seal_receipt.control_uid')
    if control_uid < 0:
        _refuse('assignment_seal_receipt.control_uid must not be negative')
    paths = _exact_dict(record.get('paths'), 'assignment_seal_receipt.paths')
    _exact_keys(paths, SEAL_PATH_KEYS, 'assignment_seal_receipt.paths')
    for name in SEAL_PATH_KEYS:
        entry = _exact_dict(paths[name],
                            'assignment_seal_receipt.paths.' + name)
        _json_safe(entry, 'assignment_seal_receipt.paths.' + name)
        _exact_keys(entry, ('before', 'after', 'worker_traversal_revoked'),
                    'assignment_seal_receipt.paths.' + name)
        _bool_true(entry.get('worker_traversal_revoked'),
                   'assignment_seal_receipt.paths.' + name
                   + '.worker_traversal_revoked')
        before = _exact_dict(entry.get('before'),
                             'assignment_seal_receipt.paths.' + name
                             + '.before')
        _json_safe(before, 'assignment_seal_receipt.paths.' + name
                   + '.before')
        after = _exact_dict(entry.get('after'),
                            'assignment_seal_receipt.paths.' + name
                            + '.after')
        _json_safe(after, 'assignment_seal_receipt.paths.' + name + '.after')
        before_mode = _validate_seal_identity(
            before, 'assignment_seal_receipt.paths.' + name + '.before',
            control_uid)
        after_mode = _validate_seal_identity(
            after, 'assignment_seal_receipt.paths.' + name + '.after',
            control_uid)
        for field in ('path', 'device', 'inode', 'uid', 'gid'):
            _match(before[field], after[field],
                   'assignment_seal_receipt.paths.' + name
                   + ' before/after identity ' + field)
        if after_mode & 0o777 != AFTER_MODE_BITS:
            _refuse('assignment_seal_receipt.paths.' + name
                    + '.after.mode must seal the workspace to 0700')
        if after['uid'] != control_uid:
            _refuse('assignment_seal_receipt.paths.' + name
                    + '.after.uid must equal the sealing control uid')

def validate_paid_model_terminal_evidence(
    value,
    *,
    expected_binding,
    expected_process_ref,
    expected_launch_attestation,
    expected_launch_identity_sha256,
    expected_result_envelope,
    expected_grant,
):
    """Validate sealed paid model terminal evidence and return it detached.

    The returned value is a plain, deep-copied, exact dict: mutating the
    caller's input afterwards never aliases into the validated result.  Every
    refusal raises :class:`PaidModelTerminalRefused` with a secret-free,
    structural message.  This validates DATA only; the caller separately
    qualifies the actual control owner, origin, compiled-input, physical and
    configuration joins, and owns role policy.
    """
    evidence = _exact_dict(value, 'sealed evidence')
    _json_safe(evidence, 'sealed evidence')
    _exact_keys(evidence, TOP_KEYS, 'sealed evidence')
    if evidence.get('schema_version') != SCHEMA_SEALED_EVIDENCE:
        _refuse('sealed evidence schema_version refused')
    _json_safe(evidence, 'sealed evidence')

    binding, binding_values = _validate_binding(expected_binding)
    refmap = _ref_bindings(expected_process_ref)

    attestation = _exact_dict(expected_launch_attestation,
                              'expected_launch_attestation')
    _json_safe(attestation, 'expected_launch_attestation')
    if attestation.get('schema_version') != SCHEMA_ATTESTATION:
        _refuse('expected_launch_attestation schema refused')
    if 'binding' not in attestation:
        _refuse('expected_launch_attestation.binding missing')
    if not _canonical_equal(attestation.get('binding'), binding,
                            'expected_launch_attestation.binding',
                            'expected_binding'):
        _refuse('expected_launch_attestation.binding does not equal '
                'expected_binding')
    att_view = _attestation_view(attestation)

    grant_digest = _validate_grant(expected_grant, binding, binding_values)
    _validate_launch_identity(evidence['launch_identity'], binding,
                              expected_launch_identity_sha256)

    owned_launch = evidence['owned_launch']
    _exact_dict(owned_launch, 'owned_launch')
    paths = _exact_dict(owned_launch.get('capture_paths'), 'owned capture paths')
    _exact_keys(paths, ('stdout_path', 'stderr_path', 'result_path'), 'owned capture paths')
    source = evidence['launch_identity']['request']['paid_source_config']
    capture_root = source['capture_root']
    context = _exact_dict(owned_launch.get('host_context'), 'owned host context')
    _exact_keys(context, ('host_env_path', 'host_env_sha256', 'boot_id', 'capture_identity'), 'owned host context')
    expected_context = {key: source['qualification'][key] for key in context}
    if (context != expected_context or context['boot_id'] != refmap['boot_session_id']
            or owned_launch.get('transport_host') != source['qualification']['registry_key']
            or refmap['host_ref'] != source['host_ref']):
        _refuse('owned host qualification differs')
    for name in paths:
        _match(refmap[name], paths[name], 'owned capture path')
        if PurePosixPath(paths[name]).parent != PurePosixPath(capture_root) / (binding['attempt_id'] + '.paid'):
            _refuse('owned capture namespace differs')
    _match(attestation['worker_id'], refmap['worker_id'], 'paid worker')
    _match(attestation['evidence']['physical_binding_sha256'], evidence['launch_identity']['physical_binding_sha256'], 'attested physical binding')
    _match(attestation['evidence']['pin_identity_sha256'], expected_launch_identity_sha256, 'attested Runtime pin')
    _match(attestation['evidence']['capture_contract_sha256'], _standard_digest(owned_launch['capture_contract'], 'capture contract'), 'attested capture contract')
    _match(attestation['evidence']['python_sha256'], refmap['binary']['sha256'], 'attested binary')
    run_id, pid, started_at = _validate_owned_launch(
        owned_launch, attestation, att_view, refmap, binding_values)
    contract = owned_launch['capture_contract']
    contract_limit = contract.get('capture_limit_bytes')

    stdout_bytes, stdout_sha256, stderr_bytes, stderr_sha256, cleanup = \
        _validate_owned_terminal(evidence['owned_terminal'], owned_launch,
                                 run_id, pid, started_at, refmap,
                                 binding_values['attempt_id'])
    capture_stdout_sha256, capture_stderr_sha256 = _validate_capture(
        evidence['capture'], contract_limit, stdout_bytes, stdout_sha256,
        stderr_bytes, stderr_sha256, expected_result_envelope)

    _validate_collection(evidence['collection_receipt'], refmap,
                         binding_values, run_id, capture_stdout_sha256,
                         capture_stderr_sha256, expected_result_envelope,
                         expected_process_ref, grant_digest, cleanup)
    _validate_validation_receipts(evidence['validation_receipts'],
                                  binding_values, expected_grant,
                                  grant_digest)
    _validate_seal(evidence['assignment_seal_receipt'], binding_values,
                   grant_digest)

    _sha256_field(evidence['collection_receipt_digest'],
                  'collection_receipt_digest')
    _sha256_field(evidence['validation_receipts_digest'],
                  'validation_receipts_digest')
    _sha256_field(evidence['assignment_seal_receipt_digest'],
                  'assignment_seal_receipt_digest')
    if evidence['collection_receipt_digest'] != _standard_digest(
            evidence['collection_receipt'], 'collection_receipt'):
        _refuse('collection_receipt_digest does not match the actual '
                'collection receipt')
    if evidence['validation_receipts_digest'] != _standard_digest(
            evidence['validation_receipts'], 'validation_receipts'):
        _refuse('validation_receipts_digest does not match the actual '
                'validation receipts')
    if evidence['assignment_seal_receipt_digest'] != _standard_digest(
            evidence['assignment_seal_receipt'],
            'assignment_seal_receipt'):
        _refuse('assignment_seal_receipt_digest does not match the actual '
                'assignment seal receipt')

    return copy.deepcopy(evidence)
