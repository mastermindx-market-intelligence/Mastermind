"""Native tool dispatch, process environment, snapshots and pre-persistence redaction."""
import json
import logging
from pathlib import Path
import time
import traceback
from contextlib import contextmanager
from contextvars import copy_context

import pytest

from agent import launch_credential_binding as binding

SECRET = 'qualification-sentinel-only-8a31b60f'


@contextmanager
def _run(*, session='parent', transcripts=('parent', 'compressed')):
    lease = binding.CredentialLease('fixture-profile', 'fixture-principal', session, 'fixture', 1,
        {'credential_fingerprints': {'TEST_RUN_TOKEN': 'fixture-digest'}, 'expires_at': time.time() + 3600},
        {'TEST_RUN_TOKEN': SECRET}, {'TEST_RUN_ID': 'fixture-run'})
    claim = lease.claim(profile_id='fixture-profile', principal_id='fixture-principal', session_id=session,
                        instance_id='fixture', owner_epoch=1, admission_id='admission', generation=1, finite=True)
    with binding.execution_scope(lease, claim, transcript_check=lambda sid: sid in transcripts):
        yield lease


def test_real_dispatch_redacts_before_middleware_and_observers(monkeypatch):
    import model_tools
    from tools.registry import registry
    from hermes_cli import lifecycle, middleware
    seen = []
    registry.register(name='launch_fixture_echo', toolset='terminal',
        schema={'name': 'launch_fixture_echo', 'description': 'Qualification echo', 'parameters': {'type': 'object'}},
        handler=lambda args, **kw: json.dumps({'value': SECRET}), check_fn=lambda: True)
    def execution(name, args, callback, **kwargs):
        value = callback(args)
        seen.append(('middleware', value))
        return value
    monkeypatch.setattr(middleware, 'run_tool_execution_middleware', execution)
    monkeypatch.setattr(lifecycle, 'has_hook', lambda name: name in {'post_tool_call', 'transform_tool_result'})
    def hook(name, **kwargs):
        seen.append((name, kwargs))
        return [SECRET] if name == 'transform_tool_result' else []
    monkeypatch.setattr(lifecycle, 'invoke_hook', hook)
    with _run():
        result = model_tools.handle_function_call('launch_fixture_echo', {}, session_id='parent',
            skip_pre_tool_call_hook=True, skip_tool_request_middleware=True)
        assert 'REDACTED_LAUNCH_CREDENTIAL' in result
    assert seen and SECRET not in json.dumps(seen)


def test_real_local_environment_and_snapshot_never_retain_run_token(tmp_path):
    from tools.environments.local import LocalEnvironment, _make_run_env
    from tools.code_execution_env import _build_child_env
    import sys
    terminal = LocalEnvironment(cwd=str(tmp_path), timeout=10)
    try:
        with _run(), binding.tool_dispatch_scope('parent', 'terminal', {}):
            assert _make_run_env({})['TEST_RUN_TOKEN'] == SECRET
            terminal.init_session()
            result = terminal.execute('test -n "$TEST_RUN_TOKEN" && printf credential-present')
            assert 'credential-present' in str(result)
            snapshot = Path(terminal._snapshot_path).read_text()
            assert SECRET not in snapshot and 'export TEST_RUN_TOKEN=' not in snapshot
            # Persistent code kernels never get a copy; their synchronous tool RPC
            # instead reuses the existing per-cell authority and dispatch context.
            kernel_env = _build_child_env(rpc_endpoint='fixture', rpc_token='fixture-rpc',
                                          tmpdir=str(tmp_path), child_python=sys.executable)
            assert 'TEST_RUN_TOKEN' not in kernel_env
        assert 'TEST_RUN_TOKEN' not in _make_run_env({})
        assert 'TEST_RUN_TOKEN' in terminal._snapshot_excluded_passthrough_names()
    finally:
        terminal.cleanup()


def test_compression_nested_calls_and_copied_children_are_fenced():
    from agent.delegation_context import non_dispatcher_owned_context
    with _run():
        with binding.tool_dispatch_scope('compressed', 'execute_code', {}):
            # Missing inner transcript identity is permitted only while the
            # inherited outer dispatch is still live (the native CellAuthority path).
            with binding.tool_dispatch_scope(None, 'terminal', {}):
                assert binding.tool_environment()['TEST_RUN_TOKEN'] == SECRET
            delayed = copy_context()
            with non_dispatcher_owned_context():
                with pytest.raises(binding.LaunchCredentialError, match='child_scope_refused'):
                    binding.tool_environment()
        with pytest.raises(binding.LaunchCredentialError, match='tool_scope_retired'):
            delayed.run(binding.tool_environment)
        with pytest.raises(binding.LaunchCredentialError, match='transcript_mismatch'):
            with binding.tool_dispatch_scope('forked-child', 'terminal', {}):
                pytest.fail('child dispatch entered')
        with pytest.raises(binding.LaunchCredentialError, match='background_unsupported'):
            with binding.tool_dispatch_scope('parent', 'terminal', {'background': True}):
                pytest.fail('background process started')


def test_producer_logging_scrubs_exception_extra_and_late_cleanup():
    import hermes_logging
    from hermes_logging import _NonFormattingQueueHandler
    records = []
    class Capture(logging.Handler):
        def emit(self, record):
            records.append(_NonFormattingQueueHandler(None).prepare(record))
    logger = logging.getLogger('qualification.launch-credentials')
    handler = Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        with _run() as lease:
            lease.retire()
            try:
                raise ValueError(SECRET)
            except ValueError:
                logger.exception('failed %s', SECRET, extra={'detail': {'token': SECRET}})
        assert len(records) == 1
        record = records[0]
        assert record.exc_info is None
        assert SECRET not in repr(vars(record))
        assert SECRET not in logging.Formatter().format(record)
    finally:
        logger.removeHandler(handler)


def test_unformattable_log_objects_produce_only_a_safe_record():
    class Unformattable:
        def __eq__(self, other):
            raise RuntimeError(SECRET)
        def __str__(self):
            raise RuntimeError(SECRET)
    record = logging.LogRecord('qualification.bad-object', logging.ERROR, '', 0,
                               Unformattable(), (SECRET,), None)
    record.untrusted_detail = SECRET
    with _run():
        binding.sanitize_log_record(record)
    assert record.getMessage() == 'launch_credential_log_format_refused'
    assert SECRET not in repr(vars(record)) and record.args == ()


def test_websocket_frame_logs_and_malformed_private_validation_are_input_free(monkeypatch):
    import hermes_logging
    from websockets.frames import Frame, Opcode
    from pydantic import ValidationError
    from tui_gateway.contracts.canonical_sessions import CanonicalCreateParams
    from tui_gateway.contracts import registry
    logger = logging.getLogger('embedding.custom.transport')
    frame = Frame(Opcode.TEXT, json.dumps({'params': {binding.PRIVATE_FIELD: {'token': SECRET}}}).encode())
    record = logger.makeRecord(logger.name, logging.DEBUG, '', 0, '> %s', (frame,), None)
    assert SECRET not in record.getMessage() and not record.args
    monkeypatch.setattr(registry, 'STRICT', True)
    with pytest.raises(registry.ContractViolation) as caught:
        try:
            CanonicalCreateParams.model_validate({binding.PRIVATE_FIELD: [SECRET]})
        except ValidationError as error:
            registry._report('params', 'session.create', error)
    assert SECRET not in ''.join(traceback.format_exception(caught.value))
    contract = registry.CANONICAL_METHODS['session.create']
    fields = registry.canonical_param_problems(contract, {binding.PRIVATE_FIELD: [SECRET]})
    assert fields == [binding.PRIVATE_FIELD]


def test_optional_display_redaction_toggle_cannot_disable_run_redaction(monkeypatch):
    from agent import redact as display_redact
    monkeypatch.setattr(display_redact, '_redact_enabled', lambda: False)
    with _run():
        assert SECRET not in display_redact.redact_sensitive_text(SECRET)
