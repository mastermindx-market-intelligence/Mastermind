"""Exercise the actual executor's preflight; no host, process or provider I/O."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_fabric_bound_controller_wire import patched


class AdmissionReached(Exception):
    pass


def execute(tmp_path, monkeypatch, *, mode, context, digest=True):
    source = tmp_path / 'remote_sub_exec.py'
    tree = ast.parse(patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_execute')
    errors = []
    effects = []

    def acquire(*a, **kw):
        effects.append('physical_admission')
        raise AdmissionReached()

    def remote_arguments(*a, **kw):
        if isinstance(context, Exception):
            raise context
        return context

    monkeypatch.setitem(__import__('sys').modules, 'fabric_launch_transport',
                        SimpleNamespace(remote_launch_arguments=remote_arguments))
    environment = {'FABRIC_LAUNCH_SNAPSHOT_SHA256': 'a' * 64} if digest else {}
    namespace = dict(__file__=str(source), Path=Path, os=SimpleNamespace(environ=environment, cpu_count=lambda: 2),
                     native_remote=SimpleNamespace(MODES=()),
                     _fail=lambda message, code: (errors.append(message), code)[1],
                     parse_bounded_seconds=lambda *a, **kw: 10,
                     load_runtime_config=lambda *a, **kw: SimpleNamespace(nice=10),
                     install_signal_cleanup=lambda *a, **kw: effects.append('signal_handlers'),
                     LaneLease=SimpleNamespace(acquire=acquire),
                     LaneAdmissionRefused=TypeError, LaneRuntimeError=ValueError,
                     LaneRuntimeConfigError=ValueError)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    packet = tmp_path / 'packet'
    packet.write_text('READ only. Bash, tools and writes are not authorized.')
    return namespace['_execute'], ['remote_sub_exec.py', 'attempt-1', mode, str(packet), str(tmp_path), 'fixed-model'], errors, effects


@pytest.mark.parametrize('mode', ['glm', 'minimax', 'qwen'])
def test_bound_request_cannot_reach_legacy_admission(tmp_path, monkeypatch, mode):
    fn, argv, errors, effects = execute(tmp_path, monkeypatch, mode=mode, context={
        'launch_receipt_path': '/not-read/launch.json',
        'launch_receipt_metadata': {'attempt_id': 'attempt-1'},
        'launch_receipt_context_sha256': 'a' * 64,
    })
    assert fn(argv, {}) == 78
    assert errors == ['BOUND_ATTENDED_EXECUTOR_UNAVAILABLE before_admission=1 before_spawn=1']
    assert effects == []


def test_digest_cannot_downgrade_to_unbound_path(tmp_path, monkeypatch):
    fn, argv, errors, effects = execute(tmp_path, monkeypatch, mode='minimax', context={})
    assert fn(argv, {}) == 78
    assert errors == ['BOUND_ATTENDED_EXECUTOR_UNAVAILABLE before_admission=1 before_spawn=1']
    assert effects == []


def test_unbound_ordinary_shell_path_is_preserved(tmp_path, monkeypatch):
    fn, argv, errors, effects = execute(tmp_path, monkeypatch, mode='minimax', context={}, digest=False)
    with pytest.raises(AdmissionReached):
        fn(argv, {})
    assert errors == []
    assert effects == ['signal_handlers', 'physical_admission']


def test_invalid_correlation_keeps_existing_preflight_refusal(tmp_path, monkeypatch):
    fn, argv, errors, effects = execute(tmp_path, monkeypatch, mode='minimax', context=ValueError('bad'))
    assert fn(argv, {}) == 78
    assert errors == ['BOUND_LAUNCH_CONTEXT_REFUSED before_spawn=1']
    assert effects == []
