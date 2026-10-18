"""A selected native pilot can receive a complete, bounded canonical packet."""
from pathlib import Path
import json
from integrations.native_context.adapter import Binding, ReaderResult, encode_response, render_hook


def test_explicit_project_budget_includes_complete_typical_wire_packet():
    binding = Binding("EXAMPLE-CONTEXT", Path("/approved/Macro"), "a" * 40, "b" * 40)
    data = {
        "schema": "context_bundle.v1",
        "target": {"workstream": "WS:EXAMPLE-CONTEXT"},
        "repo_sha": "a" * 40,
        "source_records_digest": "sha256:" + "c" * 64,
        "generated_at": "2026-10-18T01:00:00Z",
        "sections": [{"id": "workstream", "items": [{
            "excerpt": "required constraint " * 1100 + " END_REQUIRED_SENTINEL"
        }]}],
        "excluded": [], "omitted_due_to_budget": [], "degraded": [],
        "no_answer_reason": None,
    }
    raw = json.dumps(data, indent=2).encode()
    assert 20000 < len(raw) < 26000
    calls = []
    def reader(*args):
        calls.append(args)
        return ReaderResult(True, raw)
    response = render_hook(
        b'{"hook_event_name":"SessionStart","source":"startup"}',
        provider="codex", binding=binding, hydrate=True, reader=reader,
        max_context_bytes=32768,
    )
    text = response["hookSpecificOutput"]["additionalContext"]
    assert "CANONICAL_PAYLOAD_INCLUDED" in text
    assert raw.decode() in text
    assert "END_REQUIRED_SENTINEL" in text
    assert len(calls) == 1
    assert len(text.encode()) <= 32768
    assert len(encode_response(response)) <= 65536


def test_default_budget_is_not_silently_increased():
    # The existing default remains bounded at 6 KB; a larger pilot must opt in.
    import inspect
    assert inspect.signature(render_hook).parameters["max_context_bytes"].default == 6000


def test_explicit_context_ceiling_remains_closed_before_reader():
    import pytest
    from integrations.native_context.adapter import ContextError
    binding = Binding("EXAMPLE-CONTEXT", Path("/approved/Macro"), "a" * 40, "b" * 40)
    for value in (32769, True, 1000000):
        with pytest.raises(ContextError, match="invalid_hook_budget"):
            render_hook(b'{"hook_event_name":"SessionStart","source":"startup"}',
                        provider="codex", binding=binding, hydrate=True,
                        max_context_bytes=value, reader=lambda *_: pytest.fail("reader called"))
