"""Call-local reader settlement must not erase payload/CLI/source boundaries."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import ceo_boot_packet as cli
from integrations.native_context.adapter import Binding, render_hook
from integrations.native_context.bridge import CanonicalBootReader

SHA = "a" * 40
READER_SHA = "b" * 40
EVENT = b'{"hook_event_name":"SessionStart","source":"startup"}'


def payload():
    return json.dumps({"schema": "context_bundle.v1",
        "target": {"workstream": "WS:EXAMPLE-CONTEXT"}, "repo_sha": SHA,
        "source_records_digest": "sha256:" + "c" * 64,
        "generated_at": "2026-10-18T01:00:00Z", "sections": [], "excluded": [],
        "omitted_due_to_budget": [], "degraded": [], "no_answer_reason": None})


def observed(**changes):
    return {"code": 0, "stdout": payload(), "stderr": "",
        "timed_out": False, "limit_exceeded": False, "invalid_utf8": False, **changes}


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "Macro"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/agentos.py").write_text("pass\n")
    monkeypatch.setattr(cli, "resolve_macro_root", lambda *a: (root, "fixture", []))
    monkeypatch.setattr(cli, "git_sha", lambda *a: SHA)
    return root


def argv(root, timeout="1"):
    return ["--workstream", "WS:EXAMPLE-CONTEXT", "--macro-root", str(root),
        "--expected-macro-sha", SHA, "--context-budget", "4000", "--timeout", timeout]


def typed_main():
    method = getattr(cli, "main_with_outcome", None)
    assert callable(method), "existing CLI must expose an immutable per-call outcome"
    return method


@pytest.mark.parametrize("flag,diagnostic", [
    ("timed_out", "reader timed out"),
    ("limit_exceeded", "transport output limit exceeded; context was not truncated"),
    ("invalid_utf8", "reader emitted invalid UTF-8"),
])
def test_settled_failure_preserves_cli_diagnostic_and_withholds_body(source, monkeypatch, capsys, flag, diagnostic):
    monkeypatch.setattr(cli, "bounded_subprocess_runner", lambda *a, **k: observed(**{flag: True}, stdout="PRIVATE_PARTIAL"))
    code, outcome = typed_main()(argv(source))
    streams = capsys.readouterr()
    assert code == 1 and outcome.state == "SETTLED"
    assert streams.out == ""
    assert streams.err == f"Agent OS context unavailable: {diagnostic}. No generic brief fallback.\n"


@pytest.mark.parametrize("error", [OSError, ValueError, RuntimeError])
def test_any_runner_exception_remains_unknown(source, monkeypatch, capsys, error):
    def fail(*args, **kwargs):
        raise error("PRIVATE_DIAGNOSTIC")
    monkeypatch.setattr(cli, "bounded_subprocess_runner", fail)
    code, outcome = typed_main()(argv(source))
    streams = capsys.readouterr()
    assert code == 1 and outcome.state == "UNKNOWN"
    assert streams.out == "" and "PRIVATE_DIAGNOSTIC" not in streams.err
    assert "reconcile the existing reader" in streams.err


def test_not_started_is_only_pre_dispatch(source, monkeypatch, capsys):
    monkeypatch.setattr(cli, "git_sha", lambda *a: "d" * 40)
    monkeypatch.setattr(cli, "bounded_subprocess_runner", lambda *a, **k: pytest.fail("dispatched"))
    code, outcome = typed_main()(argv(source))
    assert code == 1 and outcome.state == "NOT_STARTED"
    assert "expected source pin" in capsys.readouterr().err


def test_source_drift_does_not_invent_unsettled_process(source, monkeypatch, capsys):
    revisions = iter([SHA, "d" * 40])
    monkeypatch.setattr(cli, "git_sha", lambda *a: next(revisions))
    monkeypatch.setattr(cli, "bounded_subprocess_runner", lambda *a, **k: observed())
    code, outcome = typed_main()(argv(source))
    streams = capsys.readouterr()
    assert code == 1 and outcome.state == "SETTLED"
    assert streams.out == "" and "Macro source changed" in streams.err


def test_consecutive_calls_have_independent_immutable_outcomes(source, monkeypatch, capsys):
    from dataclasses import FrozenInstanceError
    results = iter([observed(timed_out=True), observed()])
    monkeypatch.setattr(cli, "bounded_subprocess_runner", lambda *a, **k: next(results))
    first = typed_main()(argv(source))
    capsys.readouterr()
    second = typed_main()(argv(source))
    assert first[0] == 1 and second[0] == 0
    assert first[1] is not second[1]
    assert first[1].state == second[1].state == "SETTLED"
    assert capsys.readouterr().out == payload() + "\n"
    with pytest.raises(FrozenInstanceError):
        first[1].state = "UNKNOWN"


def test_settled_timeout_reaches_real_hook_as_distinct_failure(source, monkeypatch):
    monkeypatch.setattr(cli, "bounded_subprocess_runner", lambda *a, **k: observed(timed_out=True, stdout="PRIVATE_PARTIAL"))
    reader = CanonicalBootReader(root=Path("/reader"), main=cli.main, git_sha=lambda *a: READER_SHA, typed_main=typed_main())
    binding = Binding("EXAMPLE-CONTEXT", source, SHA, READER_SHA)
    result = render_hook(EVENT, provider="codex", binding=binding, hydrate=True, reader=reader)
    text = result["hookSpecificOutput"]["additionalContext"]
    assert "READER_SETTLED_FAILURE" in text
    assert "READER_RECONCILIATION_REQUIRED" not in text and "PRIVATE_PARTIAL" not in text


def test_known_not_started_does_not_become_reconciliation(source, monkeypatch):
    monkeypatch.setattr(cli, "git_sha", lambda *a: "d" * 40)
    reader = CanonicalBootReader(root=Path("/reader"), main=cli.main, git_sha=lambda *a: READER_SHA, typed_main=typed_main())
    text = render_hook(EVENT, provider="codex", binding=Binding("EXAMPLE-CONTEXT", source, SHA, READER_SHA), hydrate=True, reader=reader)["hookSpecificOutput"]["additionalContext"]
    assert "READER_UNAVAILABLE" in text and "READER_RECONCILIATION_REQUIRED" not in text


@pytest.mark.parametrize("code", [True, False, None, "0"])
def test_malformed_typed_exit_cannot_report_success(code):
    reader = CanonicalBootReader(root=Path("/reader"), main=lambda a: pytest.fail("legacy replay"), git_sha=lambda *a: READER_SHA,
        typed_main=lambda a: (code, SimpleNamespace(state="SETTLED")))
    result = reader(Binding("EXAMPLE-CONTEXT", Path("/macro"), SHA, READER_SHA), 4000, 1)
    assert not result.ok and result.raw == b""
    assert result.reason == "canonical_reader_unavailable_reconcile"


def test_real_short_timeout_uses_existing_settlement_owner(source, capsys):
    (source / "scripts/agentos.py").write_text("import time\nprint('PRIVATE_PARTIAL', flush=True)\ntime.sleep(30)\n")
    code, outcome = typed_main()(argv(source, timeout="0.05"))
    streams = capsys.readouterr()
    assert code == 1 and outcome.state == "SETTLED"
    assert streams.out == "" and "reader timed out" in streams.err
