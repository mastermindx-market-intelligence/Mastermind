"""Current 37-file producer through the unchanged original-parent read contract."""
import importlib.util
import json
from pathlib import Path

import pytest
import artifact_reader as reader
import artifact_production as production
import run_observation as remote
import run_observation_delivery as observation
import support_bundle

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "prior_artifact_observation_cases",
    ROOT / "integrations/session_bridge/artifact_original_observation/test_artifact_observation.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
original = prior.original


@pytest.fixture
def current(original):
    o = original
    o['manifest'] = {name: prior.digest(name.encode()) for name in support_bundle.SOURCE_FILES}
    o['support'] = prior.digest(reader.canonical(
        {'schema': 'remote-support-code.v1', 'files': o['manifest']}))
    o['packet'] = production.encode_packet('bounded input', root=o['root'],
        parent=o['parent'], run_id=o['rid'], names=['patch.diff'],
        support_digest=o['support']).encode()
    o['packet_path'].write_bytes(o['packet'])
    (o['state'] / (o['rid'] + '.support.json')).write_bytes(reader.canonical(o['manifest']))
    o['binding'].update(packet_sha256=prior.digest(o['packet']), support_digest=o['support'])
    o['events'][3] = 'SUPPORT_VERSION_READY digest=' + o['support'] + ' policy=' + 'c' * 64
    o['events'][4] = 'LAUNCH_BINDING ' + json.dumps(o['binding'])
    o['log'].write_bytes(o['log_bytes']())
    return o


def test_actual_producer_closure_qualifies(current):
    assert len(support_bundle.SOURCE_FILES) == 37
    assert remote.DEADLINE_ARTIFACT_SUPPORT_FILES == support_bundle.SOURCE_FILES
    request = prior.request(current)
    assert request['kind'] == 'ordinary_artifact'
    assert request['observe_pid'] is False
    assert observation.qualify(request)['account_binding'] == 'retained_original_broker_row'
    prior.test_remote_packet_binding_is_checked_without_stdout_read(current)
    prior.test_embedded_observer_uses_qualified_packet_and_no_pid(current)


@pytest.mark.parametrize('fault', [None, 'code', 'manifest', 'manifest_changed'])
def test_all_current_support_bytes_are_checked(current, fault):
    o = current
    data = {'schema': 'remote-support-code.v1', 'files': o['manifest'], 'digest': o['support']}
    class CodeReader:
        def __init__(self):
            self.manifest_reads = 0
            self.code_reads = []

        def read(self, parts, limit, **kwargs):
            assert parts[:3] == ('lanes', 'support-releases', o['support'])
            if parts[-1] == 'RELEASE.json':
                assert kwargs == {'mode': 0o444}
                self.manifest_reads += 1
                value = dict(data)
                if fault == 'manifest' or fault == 'manifest_changed' and self.manifest_reads == 2:
                    value['files'] = {**o['manifest'], 'outside.py': '0' * 64}
                return reader.canonical(value), None
            assert parts[3] == 'ext' and parts[-1] in o['manifest']
            assert kwargs == {'mode': 0o555}
            self.code_reads.append(parts[-1])
            return (b'changed' if fault == 'code' and parts[-1] == 'commission_deadline.py'
                    else parts[-1].encode()), None
    fixture = CodeReader()
    if fault:
        with pytest.raises(remote.Invalid):
            remote.support(fixture, o['support'], expected_files=o['manifest'])
    else:
        result = remote.support(fixture, o['support'], expected_files=o['manifest'])
        assert result['verified_code_files'] == 37
        assert set(fixture.code_reads) == support_bundle.SOURCE_FILES
        assert result['running_process_source_identity_proven'] is False


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'hash', 'path', 'previous36'])
def test_unknown_closures_remain_closed(current, mutation):
    files = dict(current['manifest'])
    if mutation == 'extra':
        files['extra.py'] = 'a' * 64
    elif mutation in ('missing', 'previous36'):
        del files['native_runtime_bindings.py' if mutation == 'missing' else 'commission_deadline.py']
    elif mutation == 'hash':
        files['commission_deadline.py'] = 'not-a-hash'
    else:
        files['../commission_deadline.py'] = files.pop('commission_deadline.py')
    with pytest.raises(remote.Invalid, match='artifact_support_files_invalid'):
        remote.validate_artifact_files(files)


@pytest.mark.parametrize('mutation', [
    'root', 'parent', 'inherited_root', 'missing_parent', 'packet', 'plain_packet',
    'support', 'host', 'duplicate_launch', 'repeat_attempt', 'refusal', 'effect_unknown',
    'foreign_line', 'terminal', 'wrong_packet_path', 'lease_root', 'lease_host',
    'lease_account', 'lease_model', 'lease_pool', 'lease_missing',
])
def test_current_producer_retains_original_admission(current, monkeypatch, mutation):
    prior.test_mismatch_refuses_before_destination_or_transport(current, monkeypatch, mutation)


def test_current_producer_permission_denial_stops(current, monkeypatch):
    prior.test_permission_denial_stops_observation_without_alternate_read(current, monkeypatch)


@pytest.mark.parametrize('mutation', ['packet', 'root', 'parent', 'support',
                                      'arbitrary_file', 'arbitrary_artifact', 'pid'])
def test_current_producer_remote_binding(current, mutation):
    prior.test_remote_negative_contracts(current, mutation)
