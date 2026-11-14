"""Native transport boundaries: bounded streams, closed argv and no fallback."""
from __future__ import annotations

import sys

import pytest

from integrations.workbench_app_use.contracts import AppUseRefused, NativeDispatchUnknown
from integrations.workbench_app_use.peekaboo_adapter import PeekabooAdapter, _bounded_process
from tests.test_native_app_use_port import TARGET


def test_transport_drains_both_streams_and_parses_only_complete_success():
    result = _bounded_process([sys.executable, "-c",
        "import sys;sys.stderr.write('diagnostic');print('{\"success\":true,\"data\":{\"ok\":true}}')"],
        env={}, timeout=2)
    assert result == {"ok": True}


@pytest.mark.parametrize("code", [
    "print('x'*1100000)",
    "import sys;sys.stderr.write('x'*17000);print('{}')",
    "import time;time.sleep(5)",
    "print('{\"success\":true,\"data\":{},\"success\":false}')",
    "print('{\"success\":false,\"data\":null}')",
])
@pytest.mark.parametrize("effectful", [False, True])
def test_transport_failure_is_uncertain_only_after_possible_input(code, effectful):
    expected = NativeDispatchUnknown if effectful else AppUseRefused
    with pytest.raises(expected):
        _bounded_process([sys.executable, "-c", code], env={}, timeout=.2, effectful=effectful)


def test_exec_absence_is_a_proved_predispatch_refusal():
    with pytest.raises(AppUseRefused, match="NOT_STARTED"):
        _bounded_process(["/no/such/native/helper"], env={}, timeout=1, effectful=True)


def test_native_command_has_no_shell_foreground_implicit_target_or_carrier_retry():
    adapter = object.__new__(PeekabooAdapter)
    adapter.qualified_actions = frozenset({"type_text"})
    from types import SimpleNamespace
    adapter.config = SimpleNamespace(bridge_socket=None)
    calls = []
    def run(args, *, effectful=False):
        calls.append((args, effectful))
        return {"ok": True}
    adapter._run = run
    result = adapter.dispatch(TARGET, "snapshot-1",
        {"action": "type_text", "arguments": {"text": r"literal\nnot-a-newline"}})
    assert result["native_acknowledged"]
    assert len(calls) == 1 and calls[0][1]
    args = calls[0][0]
    assert args[args.index("--text") + 1] == r"literal\\nnot-a-newline"
    assert args[args.index("--pid") + 1] == str(TARGET.pid)
    assert args[args.index("--window-id") + 1] == str(TARGET.window_id)
    assert args[args.index("--snapshot") + 1] == "snapshot-1"
    assert args[args.index("--input-strategy") + 1] == "actionOnly"
    assert "--foreground" not in args and "--no-auto-focus" not in args


def test_inventory_includes_background_apps_and_preserves_decimal_identity():
    adapter = object.__new__(PeekabooAdapter)
    calls = []
    def run(args):
        calls.append(args)
        return {"apps": [{"name": "Probe", "bundle_id": TARGET.bundle_id,
            "pid": TARGET.pid, "process_start_identity_decimal": TARGET.process_start_identity_decimal}],
            "warnings": []}
    adapter._run = run
    result = adapter.applications()
    assert calls == [["app", "list", "--include-hidden", "--include-background"]]
    assert result["applications"][0]["process_start_identity_decimal"] == TARGET.process_start_identity_decimal


def test_permission_is_qualified_in_the_actual_child_context_before_target_reads():
    adapter = object.__new__(PeekabooAdapter)
    adapter.permissions = lambda: {"observation_ready": False}
    def forbidden(**kwargs):
        raise AssertionError("must not inspect window or input after permission refusal")
    adapter.windows = forbidden
    with pytest.raises(AppUseRefused, match="EXECUTION_CONTEXT_PERMISSION"):
        adapter.validate_target(TARGET)
