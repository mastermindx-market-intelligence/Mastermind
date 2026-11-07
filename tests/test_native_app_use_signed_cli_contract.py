"""Pin native background click arguments to the signed Peekaboo CLI contract."""
from __future__ import annotations

from types import SimpleNamespace

from integrations.workbench_app_use.peekaboo_adapter import PeekabooAdapter
from tests.test_native_app_use_port import TARGET


def test_background_click_omits_foreground_only_focus_options():
    adapter = object.__new__(PeekabooAdapter)
    adapter.qualified_actions = frozenset({"click_element"})
    adapter.config = SimpleNamespace(bridge_socket=None)
    calls: list[tuple[list[str], bool]] = []

    def run(args, *, effectful=False):
        calls.append((args, effectful))
        return {"ok": True}

    adapter._run = run
    result = adapter.dispatch(
        TARGET, "ps1_" + "a" * 32,
        {"action": "click_element", "arguments": {"element_id": "fixture-increment"}},
    )
    assert result["native_acknowledged"] is True
    assert len(calls) == 1 and calls[0][1] is True
    argv = calls[0][0]
    assert argv[0] == "click"
    assert "--foreground" not in argv
    assert "--no-auto-focus" not in argv
    assert argv[argv.index("--pid") + 1] == str(TARGET.pid)
    assert argv[argv.index("--window-id") + 1] == str(TARGET.window_id)
    assert argv[argv.index("--snapshot") + 1] == "ps1_" + "a" * 32
    assert argv[argv.index("--input-strategy") + 1] == "actionOnly"
