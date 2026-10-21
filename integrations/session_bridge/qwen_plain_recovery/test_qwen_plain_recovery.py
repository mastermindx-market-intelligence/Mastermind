"""Original plaintext Qwen recovery: inert filesystem and fake transport only."""
import copy
from pathlib import Path

import pytest
import original_delivery_collector as c
import artifact_delivery as d
from test_original_artifact_regression import world, put
from test_plain_collection import plain


@pytest.fixture
def qwen(plain):
    w = plain
    w.scope.update(mode='qwen', requested_model='qwen3.8-max')
    w.binding.update(mode='qwen', requested_model='qwen3.8-max')
    log = Path(w.binding['sources']['log']['path'])
    put(log, log.read_bytes().replace(b'pool=minimax', b'pool=bailian'))
    w.binding['sources']['log']['sha256'] = c.sha(log.read_bytes())
    w.scope['source_pins'] = {k: w.binding['sources'][k]['sha256'] for k in ('log', 'support')}
    put(w.binding_path, c.canonical(w.binding))
    put(w.here/'hosts.json', c.canonical({'ubuntu1': {'ssh_alias': 'ubuntu1', 'allowed_modes': ['qwen']}}))
    return w


def test_qwen_original_parent_gets_complete_unchanged_bytes(qwen):
    w = qwen
    before = {k: p.read_bytes() for k, p in w.files.items()}
    receipt = w.collect()
    assert receipt['state'] == 'COMPLETE'
    assert receipt['mode'] == 'qwen'
    assert receipt['lease_settlement'] == receipt['controller_state'] == 'UNKNOWN'
    assert receipt['acceptance'] == 'NOT_RECORDED'
    assert receipt['original_operation_mutated'] is False
    assert receipt['plain_provenance']['producer_root_authenticated'] is False
    assert receipt['plain_provenance']['producer_packet_consumption_attested'] is False
    path = w.tmp_path/'delivered/receipt.json'
    assert c.read_collection(path, expected_sha256=c.sha(path.read_bytes()), run_id=w.rid,
                             root='original-root', parent='original-parent') == w.stdout
    assert before == {k: p.read_bytes() for k, p in w.files.items()}
    with pytest.raises(FileExistsError):
        w.collect()
    assert len(w.calls) == 1


@pytest.mark.parametrize('fault', ['root', 'parent', 'host', 'mode', 'model', 'caller',
                                  'inherited_root', 'destination', 'unscoped', 'packet',
                                  'log', 'support', 'second_launch'])
def test_qwen_wrong_binding_refuses_before_transport(qwen, monkeypatch, fault):
    w = qwen
    if fault in ('root', 'parent', 'host', 'mode'):
        w.binding[fault] = 'foreign'
    if fault == 'model': w.binding['requested_model'] = 'other-model'
    if fault == 'caller': monkeypatch.setenv('CODEX_THREAD_ID', 'proxy-root')
    if fault == 'inherited_root': monkeypatch.setenv('POOL_ORCHESTRATOR_ID', 'foreign')
    if fault == 'unscoped': monkeypatch.setattr(c, 'PLAIN_SCOPES', {})
    if fault in ('packet', 'log', 'support', 'second_launch'):
        key = 'log' if fault == 'second_launch' else fault
        source = w.binding['sources'][key]
        path = Path(source['path'])
        suffix = b'changed source\n'
        if fault == 'second_launch':
            suffix = b'2026-10-13T03:57Z [remote_sub id=original-run host=ubuntu1] LAUNCH_ATTEMPT attempt=1\n'
        put(path, path.read_bytes() + suffix)
        # Rehashing a changed source is not authority to replace its original pin.
        source['sha256'] = c.sha(path.read_bytes())
    put(w.binding_path, c.canonical(w.binding))
    with pytest.raises(ValueError):
        w.collect(w.tmp_path/'alternate' if fault == 'destination' else None)
    assert w.calls == []


@pytest.mark.parametrize('fault', ['packet', 'packet_symlink', 'shared_directory',
                                  'digest', 'capture', 'cleanup', 'label', 'nonzero'])
def test_qwen_unqualified_remote_bytes_never_publish(qwen, fault):
    w = qwen
    if fault == 'packet': put(w.remote_packet, b'different packet')
    if fault == 'packet_symlink':
        w.remote_packet.rename(w.remote_packet.with_suffix('.original'))
        w.remote_packet.symlink_to(w.remote_packet.with_suffix('.original'))
    if fault == 'shared_directory': w.remote_packet.parent.chmod(0o775)
    if fault == 'digest': w.process['stdout_sha256'] = '0'*64
    if fault == 'capture': w.process['cleanup']['stdout_capture_complete'] = False
    if fault == 'cleanup': w.process['cleanup']['residual_count'] = 1
    if fault == 'label': w.process['label'] = 'another-worker'
    if fault == 'nonzero': put(w.files['rc'], b'75\n')
    put(w.files['process'], c.canonical(w.process))
    with pytest.raises((ValueError, OSError)):
        w.collect()
    assert len(w.calls) == 1
    assert not (w.tmp_path/'delivered/receipt.json').exists()
    with pytest.raises(FileExistsError): w.collect()
    assert len(w.calls) == 1


def test_qwen_missing_rc_does_not_prove_death_or_authorize_retry(qwen):
    w = qwen
    w.files['rc'].unlink()
    receipt = w.collect()
    assert receipt['state'] == 'PENDING' and receipt['worker_terminal_proof'] is False
    assert receipt['acceptance'] == 'NOT_RECORDED'
    with pytest.raises(FileExistsError): w.collect()


def test_qwen_generated_reader_is_the_same_guarded_reader(qwen):
    w = qwen
    namespace = {}
    code = c.code_for_request(w.request)
    exec(code.split('\ntry:\n raw=sys.stdin.buffer.read(65537)')[0], namespace)
    response = namespace['remote_read'](w.request, home=w.home)
    assert c.validate_response(c.canonical(response), w.request, 'qwen')[0]['stdout'] == w.stdout
    with pytest.raises(ValueError): c.validate_response(c.canonical(response), w.request, 'minimax')


def test_qwen_generated_reader_omits_local_only_scope_metadata(qwen):
    w = qwen
    code = c.code_for_request(w.request)
    assert w.scope['packet_path'] not in code
    assert w.scope['destination'] not in code
    assert 'source_pins' not in code
    namespace = {}
    exec(code.split('\ntry:\n raw=sys.stdin.buffer.read(65537)')[0], namespace)
    assert set(namespace['PLAIN_SCOPES'][w.rid]) == {
        'root', 'parent', 'host', 'packet_sha256', 'support_digest'}


@pytest.mark.parametrize('available', [True, False])
def test_qwen_reuses_existing_qualified_historical_validator(qwen, monkeypatch, available):
    w = qwen
    seen = []
    class OriginalValidator:
        def parse_packet(self, text):
            assert text == w.remote_packet.read_text()
            return None
    def qualify(manifest):
        seen.append(manifest)
        if not available:
            raise ValueError('original_producer_validator_changed')
        return OriginalValidator()
    monkeypatch.setattr(d, 'original_validator_context', qualify)
    # Prove the new plaintext Qwen branch calls the existing closed-generation
    # qualifier and parser. Unknown source must fail before transport.
    if available:
        assert w.collect()['state'] == 'COMPLETE'
    else:
        with pytest.raises(ValueError, match='original_producer_validator_changed'):
            w.collect()
        assert w.calls == []
    assert seen


@pytest.mark.parametrize('fault', ['root', 'parent', 'path', 'host', 'mode', 'model', 'log', 'support'])
def test_qwen_consumption_preserves_original_scope(qwen, fault):
    w = qwen
    w.collect()
    path = w.tmp_path/'delivered/receipt.json'
    receipt = c.reader.strict_json(path.read_bytes())
    binding_path = path.with_name('binding.json')
    binding = c.reader.strict_json(binding_path.read_bytes())
    if fault == 'path': path = path.with_name('other.json')
    if fault in ('host', 'mode'): receipt[fault] = 'foreign'
    if fault == 'model': binding['requested_model'] = 'foreign'
    if fault in ('log', 'support'): binding['sources'][fault]['sha256'] = '0'*64
    put(binding_path, c.canonical(binding))
    receipt['binding_sha256'] = c.sha(binding_path.read_bytes())
    receipt['files'][0].update(bytes=binding_path.stat().st_size, sha256=receipt['binding_sha256'])
    put(path, c.canonical(receipt))
    with pytest.raises(ValueError):
        c.read_collection(path, expected_sha256=c.sha(path.read_bytes()), run_id=w.rid,
                          root='foreign' if fault == 'root' else 'original-root',
                          parent='foreign' if fault == 'parent' else 'original-parent')
