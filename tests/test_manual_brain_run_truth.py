"""Manual active-book runs must use the same semantic outcome ledger as cron."""
import ast
from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
TREE = ast.parse(SOURCE)


def _function_source(name: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(SOURCE, node)
            assert segment is not None
            return segment
    raise AssertionError(f"missing endpoint function {name}")


def test_active_manual_runs_do_not_equate_return_with_success() -> None:
    for name in ("autonomous_run", "china_run", "hk_run"):
        function = _function_source(name)
        assert function.count("_brain_job_outcome(") == 2
        assert 'run_ledger.end_run(handle, "ok")' not in function
        assert "severity=_severity" in function
        assert "extra=_extra" in function


def test_wait_response_exposes_decision_lifecycle() -> None:
    assert '"target_status", "decision_effective",' in SOURCE
    for name in ("autonomous_run", "china_run", "hk_run"):
        function = _function_source(name)
        assert "return _manual_brain_response(out, _status, _extra)" in function


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _endpoint(path: str):
    from app.main import app

    return next(route.endpoint for route in app.routes if getattr(route, "path", None) == path)


@pytest.mark.parametrize("path,module_name,runner", [
    ("/api/autonomous/run", "bot.autonomous", "run_autonomous"),
    ("/api/china/run", "bot.china", "run_china"),
    ("/api/hk/run", "bot.hk", "run_hk"),
])
def test_wait_manual_missing_submission_records_one_truthful_receipt(
    path, module_name, runner, monkeypatch
):
    import asyncio
    import importlib
    from control_plane import locks, run_ledger

    module = importlib.import_module(module_name)
    result = {"target_status": "rejected_no_submission", "decision_effective": False}
    monkeypatch.setattr(module, runner, lambda **_kwargs: dict(result))
    monkeypatch.setattr(locks, "acquire_or_log", lambda *_args, **_kwargs: _Lock())
    monkeypatch.setattr(run_ledger, "start_run", lambda *_args, **_kwargs: object())
    receipts = []
    monkeypatch.setattr(run_ledger, "end_run",
                        lambda *args, **kwargs: receipts.append((args, kwargs)))

    response = asyncio.run(_endpoint(path)(force=True, wait=True))
    assert response["target_status"] == "rejected_no_submission"
    assert response["decision_effective"] is False
    assert response["run_status"] == "error"
    assert response["run_reason"] == "missing_submission"
    assert len(receipts) == 1
    assert receipts[0][0][1] == "error"
    assert receipts[0][1] == {
        "severity": "FREEZE",
        "extra": {"target_status": "rejected_no_submission", "reason": "missing_submission"},
    }


@pytest.mark.parametrize("path,module_name,runner", [
    ("/api/autonomous/run", "bot.autonomous", "run_autonomous"),
    ("/api/china/run", "bot.china", "run_china"),
    ("/api/hk/run", "bot.hk", "run_hk"),
])
def test_wait_manual_invalid_result_is_safe_and_not_double_finished(
    path, module_name, runner, monkeypatch
):
    import asyncio
    import importlib
    from control_plane import locks, run_ledger

    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, runner, lambda **_kwargs: None)
    monkeypatch.setattr(locks, "acquire_or_log", lambda *_args, **_kwargs: _Lock())
    monkeypatch.setattr(run_ledger, "start_run", lambda *_args, **_kwargs: object())
    receipts = []
    monkeypatch.setattr(run_ledger, "end_run",
                        lambda *args, **kwargs: receipts.append((args, kwargs)))

    response = asyncio.run(_endpoint(path)(force=False, wait=True))
    assert response == {
        "target_status": None,
        "decision_effective": False,
        "run_status": "error",
        "run_reason": "invalid_result",
    }
    assert len(receipts) == 1
    assert receipts[0][0][1] == "error"
    assert receipts[0][1]["extra"] == {"reason": "invalid_result"}
