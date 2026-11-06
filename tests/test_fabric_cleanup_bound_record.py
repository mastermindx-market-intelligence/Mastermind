"""Real inert child receipts; identities/census are mocked, no host attestation."""
import hashlib
import json
import sys

import pytest

from control_plane import fabric_cleanup_contract as contract
from test_fabric_owned_process_phases import lr


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


@pytest.fixture
def actual_record(lr, tmp_path):
    root = tmp_path.resolve()
    root.chmod(0o700)
    run_dir = root / 'run'
    run_dir.mkdir(mode=0o700)
    terminal = root / 'terminal.jsonl'
    binding = dict(root_id='original-root', job_id='original-job', attempt_id='original-run',
                   effective_grant_digest='a' * 64, commission_sha256='b' * 64)
    owner = lr.begin_owned_process(
        [sys.executable, '-c', 'print(\'{"structured_output":{"summary":"local check"}}\')'],
        timeout=3, label='original-run', receipt_path=terminal,
        launch_receipt_path=root / 'early.json',
        launch_receipt_metadata={**{k: binding[k] for k in ('root_id', 'job_id', 'attempt_id')},
            'effective_grant_sha256': 'a' * 64, 'commission_sha256': 'b' * 64,
            'physical_binding_sha256': 'c' * 64, 'start_request_sha256': 'd' * 64},
        launch_receipt_context_sha256='e' * 64,
        owned_capture_run_dir=run_dir,
        owned_capture_result_schema_json=json.dumps({'type': 'object',
            'properties': {'summary': {'type': 'string'}}, 'required': ['summary']}))
    result = lr.finish_owned_process(owner)
    assert result.returncode == 0 and result.cleanup_proven
    raw = terminal.read_bytes()
    lane = json.loads(raw)
    identity = dict(host_ref='inert-host', boot_session_id=owner.process_identity['boot_id'],
        pid=owner.process.pid, pgid=owner.process.pid, session_id=owner.process.pid,
        process_start_identity=owner.process_identity['process_start_identity'])
    receipt = dict(schema_version=contract.FABRIC_CLEANUP_SCHEMA_VERSION,
        binding=binding, physical_binding_sha256='c' * 64, process_identity=identity,
        lane_started_at=lane['started_at'], lane_receipt_sha256=hashlib.sha256(canonical(lane)).hexdigest(),
        lane_receipt_bytes_sha256=hashlib.sha256(raw).hexdigest(),
        capture_complete=True, cleanup_verified=True, uncertainty=None)
    return dict(receipt=receipt, expected_binding=binding,
        expected_physical_binding_sha256='c' * 64, expected_process_identity=identity,
        lane_receipt_bytes=raw)


def edit_record(example, edit):
    row = json.loads(example['lane_receipt_bytes'])
    edit(row)
    raw = canonical(row) + b'\n'
    example['lane_receipt_bytes'] = raw
    example['receipt']['lane_receipt_sha256'] = hashlib.sha256(canonical(row)).hexdigest()
    example['receipt']['lane_receipt_bytes_sha256'] = hashlib.sha256(raw).hexdigest()


def test_actual_bound_capture_bytes_validate_without_projection(actual_record):
    evidence = contract.validate_fabric_cleanup_receipt(**actual_record)
    assert evidence.capability == 'same_run_process_group_cleanup'
    assert evidence.dedicated_user_isolation is False
    assert evidence.lane_receipt_bytes_sha256 == hashlib.sha256(actual_record['lane_receipt_bytes']).hexdigest()


@pytest.mark.parametrize('change', [
    lambda r: r.update(unknown_extension=True),
    lambda r: r.update(stdout_sha256='not-a-digest'),
    lambda r: r['launch_capture'].update(provider_execution_attested=True),
    lambda r: r['launch_capture'].update(phase='FULL_START'),
    lambda r: r['owned_capture'].update(file_descriptors_closed=False),
    lambda r: r['owned_capture'].update(result_file_complete=False),
    lambda r: r['owned_capture']['stdout'].update(file_sha256='f' * 64),
    lambda r: r['owned_capture']['stderr'].update(stream_bytes=3),
    lambda r: r['cleanup'].update(stdout_file_capture_complete=False),
    lambda r: r['cleanup'].pop('result_file_capture_complete'),
])
def test_rehashed_bound_capture_uncertainty_refuses(actual_record, change):
    edit_record(actual_record, change)
    with pytest.raises(contract.FabricCleanupContractError):
        contract.validate_fabric_cleanup_receipt(**actual_record)
