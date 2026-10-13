"""Compare actual old/new executor functions with inert process/lease fixtures."""
import ast
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from test_fabric_original_owner_runner import lr, BUNDLE
from test_fabric_bound_controller_wire import patched


def invoke(source, tmp, mode, outcome, monkeypatch):
    captured = []; errors = []; holds = []; signals = []
    class Lease:
        def __enter__(self): return self
        def __exit__(self, *args): captured.append('release')
        def hold_for_reconciliation(self, reason): holds.append(reason)
    class Leases:
        @staticmethod
        def acquire(*args, **kw):
            captured.append(('admit', kw['key'])); return Lease()
    receipt = tmp/'lanes'/'original.process.jsonl'
    def process(command=None, **kwargs):
        captured.append(dict(command=command, **kwargs))
        if outcome == 'exec_failure': raise lr.OwnedProcessStartError(7)
        cleanup = dict(identity_verified=True,census_proven=True,
                       residual_count=0 if outcome=='ok' else 1)
        receipt.write_text(json.dumps(dict(label='original',cleanup=cleanup))+'\n')
        return SimpleNamespace(stdout='',stderr='',returncode=0,
            cleanup_proven=outcome=='ok',stdout_truncated=False,stderr_truncated=False)
    tree=ast.parse(source.read_text())
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef)
           and n.name in {'_execute','_run_lease_process','_retain_original_cleanup_hold'}]
    namespace=dict(__file__=str(tmp/'remote_sub_exec.py'), Path=Path, json=json,
        os=SimpleNamespace(environ={},cpu_count=lambda:2), sys=SimpleNamespace(platform='darwin'),
        ExitStack=ExitStack, native_remote=SimpleNamespace(MODES=()),
        _fail=lambda message,code:(errors.append(message),code)[1],
        parse_bounded_seconds=lambda *a,**kw:60,
        load_runtime_config=lambda *a,**kw:SimpleNamespace(nice=10),
        install_signal_cleanup=lambda *a,**kw:signals.append('installed'),
        LaneLease=Leases,LaneAdmissionRefused=TypeError,LaneRuntimeError=lr.LaneRuntimeError,
        LaneRuntimeConfigError=ValueError,OwnedProcessStartError=lr.OwnedProcessStartError,
        cleanup_receipt_is_proven=lr.cleanup_receipt_is_proven,run_owned_process=process)
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(source),'exec'),namespace)
    monkeypatch.setitem(sys.modules,'fabric_launch_transport',SimpleNamespace(remote_launch_arguments=lambda *a:{}))
    packet=tmp/'packet';packet.write_text('bounded inert task')
    state={'started':False}
    rc=namespace['_execute'](['remote_sub_exec.py','original',mode,str(packet),str(tmp),'model'],state)
    return dict(rc=rc,state=state,captured=captured,errors=errors,holds=holds,signals=signals)


@pytest.mark.parametrize('mode',['glm','minimax','qwen'])
@pytest.mark.parametrize('outcome',['ok','exec_failure','cleanup_unproven'])
def test_ordinary_cli_keeps_exact_command_errno_cleanup_and_lease(tmp_path,monkeypatch,mode,outcome):
    (tmp_path/'lanes').mkdir()
    before=invoke(BUNDLE/'fixtures/remote_sub_exec.base.py',tmp_path,mode,outcome,monkeypatch)
    patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json')
    after=invoke(tmp_path/'remote_sub_exec.py',tmp_path,mode,outcome,monkeypatch)
    assert after == before
