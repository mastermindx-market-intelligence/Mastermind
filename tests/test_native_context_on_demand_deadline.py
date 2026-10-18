"""Explicit on-demand context reads use bounded canonical-reader deadlines."""
from pathlib import Path
import pytest
from integrations.native_context.adapter import Binding, ReaderResult, render_hook


@pytest.mark.parametrize("timeout", [16, 45, 60])
def test_explicit_reader_deadline_reaches_existing_owner_once(timeout):
    calls = []
    binding = Binding("EXAMPLE-CONTEXT", Path("/approved/Macro"), "a" * 40, "b" * 40)
    def reader(bound, budget, deadline):
        calls.append((bound, budget, deadline))
        return ReaderResult(False)
    result = render_hook(
        b'{"hook_event_name":"SessionStart","source":"startup"}',
        provider="codex", binding=binding, hydrate=True, reader=reader, timeout=timeout,
    )
    assert calls == [(binding, 4000, timeout)]
    assert "READER_UNAVAILABLE" in result["hookSpecificOutput"]["additionalContext"]


def test_default_startup_reader_deadline_stays_ten_seconds():
    calls = []
    binding = Binding("EXAMPLE-CONTEXT", Path("/approved/Macro"), "a" * 40, "b" * 40)
    def reader(bound, budget, deadline):
        calls.append(deadline)
        return ReaderResult(False)
    render_hook(b'{"hook_event_name":"SessionStart","source":"startup"}',
                provider="codex", binding=binding, hydrate=True, reader=reader)
    assert calls == [10.0]
