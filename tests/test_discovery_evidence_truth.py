"""Brain discovery surfaces must not convert unreadable evidence into an empty universe."""
from __future__ import annotations

import asyncio
import builtins
import importlib
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest


@contextmanager
def _bot_mcp_with_fake_sdk(monkeypatch):
    import brain

    missing = object()
    previous_module = sys.modules.get("brain.bot_mcp", missing)
    previous_attribute = vars(brain).get("bot_mcp", missing)
    fake = types.ModuleType("claude_agent_sdk")

    class ToolWrap:
        def __init__(self, name, handler):
            self.name = name
            self.handler = handler

    def tool(name, _description, _schema):
        def deco(fn):
            return ToolWrap(name, fn)
        return deco

    fake.tool = tool
    fake.create_sdk_mcp_server = lambda **kwargs: kwargs
    with monkeypatch.context() as sdk_patch:
        sdk_patch.setitem(sys.modules, "claude_agent_sdk", fake)
        sys.modules.pop("brain.bot_mcp", None)
        vars(brain).pop("bot_mcp", None)
        try:
            yield importlib.import_module("brain.bot_mcp")
        finally:
            if previous_module is missing:
                sys.modules.pop("brain.bot_mcp", None)
            else:
                sys.modules["brain.bot_mcp"] = previous_module
            if previous_attribute is missing:
                vars(brain).pop("bot_mcp", None)
            else:
                setattr(brain, "bot_mcp", previous_attribute)


@pytest.fixture
def bot_mcp(monkeypatch):
    with _bot_mcp_with_fake_sdk(monkeypatch) as module:
        yield module


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _break(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken secret token=do-not-return")


def test_missing_themes_are_unavailable_not_false_empty(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload == {
        "as_of": None,
        "themes": None,
        "read_status": "unavailable",
        "error": "themes_unavailable",
        "failed_sources": ["themes"],
    }


def test_healthy_empty_theme_universe_is_still_a_real_empty_result(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "basketdata" / "baskets.json", {
        "as_of": "2026-09-17", "baskets": []
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload == {"as_of": "2026-09-17", "themes": []}


def test_corrupt_themes_are_closed_unavailable(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "basketdata" / "baskets.json")

    raw = _text(asyncio.run(bot_mcp.get_themes.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["themes"] is None
    assert payload["error"] == "themes_unavailable"
    assert "secret" not in raw and "do-not-return" not in raw


def test_malformed_theme_row_preserves_good_rows_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "basketdata" / "baskets.json", {
        "as_of": "2026-09-17",
        "baskets": [
            {"id": "ai", "name": "AI", "category": "theme", "perf": {"20d": {"rel": 0.12}}, "n_members": 8},
            "wrong-row",
        ],
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload["themes"][0]["id"] == "ai"
    assert len(payload["themes"]) == 1
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["themes"]


def test_missing_standouts_keeps_existing_not_built_message(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    assert _text(asyncio.run(bot_mcp.get_standouts.handler({}))) == (
        "us_standouts.json not built locally (ships in the Pages artifact)."
    )


def test_corrupt_or_empty_existing_standouts_are_unavailable(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "factordata" / "us_standouts.json"
    _break(path)

    raw = _text(asyncio.run(bot_mcp.get_standouts.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "standouts_unavailable"
    assert payload["buy"] is None
    assert "not built locally" not in raw

    _write_json(path, {})
    payload = json.loads(_text(asyncio.run(bot_mcp.get_standouts.handler({}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "standouts_unavailable"


def test_wrong_standout_buy_shape_preserves_metadata_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "factordata" / "us_standouts.json", {
        "gate_go": True,
        "rank_by": "score",
        "buy": {"AAPL": 9},
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_standouts.handler({}))))
    assert payload["gate_go"] is True
    assert payload["rank_by"] == "score"
    assert payload["buy"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["standouts"]


def _wire_intake(monkeypatch, *, build_fail=False, salience_fail=False):
    from brain import intake

    if build_fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/intake api_key=do-not-return")
        monkeypatch.setattr(intake, "build", explode)
    else:
        monkeypatch.setattr(intake, "build", lambda limit=30: {
            "as_of": "2026-09-17",
            "candidates": [{"ticker": "AAPL", "score": 9}],
        })

    if salience_fail:
        def explode_salience(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/salience token=do-not-return")
        monkeypatch.setattr(intake, "salience_tiers", explode_salience)
    else:
        monkeypatch.setattr(intake, "salience_tiers", lambda limit=30: {"act": ["AAPL"]})


def test_intake_build_failure_is_unavailable_and_secret_safe(bot_mcp, monkeypatch):
    _wire_intake(monkeypatch, build_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5})))
    payload = json.loads(raw)
    assert payload == {
        "read_status": "unavailable",
        "error": "intake_candidates_unavailable",
        "failed_sources": ["intake"],
        "candidates": None,
    }
    assert "secret" not in raw and "api_key" not in raw


def test_salience_failure_preserves_candidate_queue_as_partial(bot_mcp, monkeypatch):
    _wire_intake(monkeypatch, salience_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5, "tiers": True})))
    payload = json.loads(raw)
    assert payload["candidates"] == [{"ticker": "AAPL", "score": 9}]
    assert payload["salience"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake_salience"]
    assert "secret" not in raw and "do-not-return" not in raw


def test_healthy_intake_queue_keeps_existing_shape(bot_mcp, monkeypatch):
    _wire_intake(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5, "tiers": True}))))
    assert payload["candidates"][0]["ticker"] == "AAPL"
    assert payload["salience"] == {"act": ["AAPL"]}
    assert "read_status" not in payload


def _standouts_path(bot_mcp, monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "factordata" / "us_standouts.json"
    path.parent.mkdir(parents=True)
    return path


def _unavailable_standouts(bot_mcp, path):
    raw = _text(asyncio.run(bot_mcp.get_standouts.handler({})))
    assert json.loads(raw) == {
        "gate_go": None, "rank_by": None, "buy": None,
        "read_status": "unavailable", "error": "standouts_unavailable",
        "failed_sources": ["standouts"],
    }
    assert str(path) not in raw and "private-secret" not in raw
    return raw


@pytest.mark.parametrize("case", [
    "null", "empty_mapping", "empty_list", "false", "zero", "empty_string",
    "dangling_leaf", "dangling_parent", "unreadable_leaf", "unreadable_parent",
    "regular_file_parent", "invalid_utf8",
])
def test_existing_or_unavailable_standouts_are_not_absent(bot_mcp, monkeypatch, tmp_path, case):
    path = _standouts_path(bot_mcp, monkeypatch, tmp_path)
    values = {"null": None, "empty_mapping": {}, "empty_list": [],
              "false": False, "zero": 0, "empty_string": ""}
    restore = None
    if case in values:
        path.write_text(json.dumps(values[case]), encoding="utf-8")
    elif case == "dangling_leaf":
        path.symlink_to(path.parent / "missing-target.json")
    elif case == "dangling_parent":
        path.parent.rmdir()
        path.parent.symlink_to(path.parent.parent / "missing-directory", target_is_directory=True)
    elif case == "unreadable_leaf":
        path.write_text('{"private-secret": true}', encoding="utf-8")
        path.chmod(0)
        restore = (path, 0o600)
    elif case == "unreadable_parent":
        path.write_text('{"private-secret": true}', encoding="utf-8")
        path.parent.chmod(0)
        restore = (path.parent, 0o700)
    elif case == "regular_file_parent":
        path.parent.rmdir()
        path.parent.write_text("private-secret", encoding="utf-8")
    else:
        path.write_bytes(b'{"value": "\xff"}')
    try:
        if case in {"unreadable_leaf", "unreadable_parent"}:
            with pytest.raises(PermissionError):
                path.read_text()
        _unavailable_standouts(bot_mcp, path)
    finally:
        if restore:
            restore[0].chmod(restore[1])


def test_standouts_failed_absence_inspection_is_unavailable(bot_mcp, monkeypatch, tmp_path):
    path = _standouts_path(bot_mcp, monkeypatch, tmp_path)
    original_lstat = Path.lstat

    def failed_lstat(target, *args, **kwargs):
        if target == path:
            raise PermissionError("private-secret absence inspection")
        return original_lstat(target, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", failed_lstat)
    _unavailable_standouts(bot_mcp, path)


def test_standouts_appeared_entry_is_not_retried_or_absent(bot_mcp, monkeypatch, tmp_path):
    path = _standouts_path(bot_mcp, monkeypatch, tmp_path)
    original_read = Path.read_text
    reads = []

    def appeared_read(target, *args, **kwargs):
        if target == path:
            reads.append(target)
            path.write_text('{"private-secret": true}', encoding="utf-8")
            raise FileNotFoundError("private-secret original read")
        return original_read(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", appeared_read)
    _unavailable_standouts(bot_mcp, path)
    assert reads == [path]
    assert path.is_file()


@pytest.mark.parametrize("first_kind", ["missing", "null", "dangling", "corrupt"])
def test_checked_reader_retains_healthy_fallback_and_failure_truth(bot_mcp, tmp_path, first_kind):
    first = tmp_path / "first.json"
    if first_kind == "null":
        first.write_text("null", encoding="utf-8")
    elif first_kind == "dangling":
        first.symlink_to(tmp_path / "missing-target.json")
    elif first_kind == "corrupt":
        first.write_text("{ private-secret", encoding="utf-8")
    fallback = tmp_path / "fallback.json"
    expected = {"known": [1, 2, 3]}
    fallback.write_text(json.dumps(expected), encoding="utf-8")
    value, failed = bot_mcp._read_first_nonempty_mapping_checked((first, fallback))
    assert value == expected
    assert failed is (first_kind != "missing")


def test_checked_reader_reads_before_any_exists_observation(bot_mcp, monkeypatch, tmp_path):
    path = tmp_path / "readable.json"
    expected = {"known": [1, 2, 3]}
    path.write_text(json.dumps(expected), encoding="utf-8")
    original_exists = Path.exists

    def unavailable_exists(target, *args, **kwargs):
        if target == path:
            return False
        return original_exists(target, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", unavailable_exists)
    assert bot_mcp._read_first_nonempty_mapping_checked((path,)) == (expected, False)


@pytest.mark.parametrize("level,value", [
    ("perf", False), ("perf", 0), ("perf", []), ("perf", ""),
    ("20d", False), ("20d", 0), ("20d", []), ("20d", ""),
])
def test_malformed_falsy_theme_performance_is_partial(bot_mcp, monkeypatch, tmp_path, level, value):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    basket = {"id": "ai", "name": "AI", "category": "theme", "n_members": 8}
    basket["perf"] = value if level == "perf" else {"20d": value}
    _write_json(vendor / "site" / "basketdata" / "baskets.json", {
        "as_of": "2026-09-17", "baskets": [basket],
    })
    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload["themes"] == [{
        "id": "ai", "name": "AI", "category": "theme", "perf_20d_rel": None, "n_members": 8,
    }]
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["themes"]


@pytest.mark.parametrize("level,value", [
    ("perf", None), ("perf", {}), ("20d", None), ("20d", {}),
])
def test_optional_theme_performance_remains_healthy(bot_mcp, monkeypatch, tmp_path, level, value):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    basket = {"id": "ai", "name": "AI"}
    basket["perf"] = value if level == "perf" else {"20d": value}
    _write_json(vendor / "site" / "basketdata" / "baskets.json", {
        "as_of": "2026-09-17", "baskets": [basket],
    })
    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload["themes"][0]["id"] == "ai"
    assert payload["themes"][0]["perf_20d_rel"] is None
    assert "read_status" not in payload


@pytest.mark.parametrize("value", [False, 0, {}, ""])
def test_malformed_falsy_buy_preserves_partial_truth_and_usable_fallback(bot_mcp, monkeypatch, tmp_path, value):
    path = _standouts_path(bot_mcp, monkeypatch, tmp_path)
    source = {"gate_go": True, "rank_by": "score", "buy": value}
    _write_json(path, source)
    payload = json.loads(_text(asyncio.run(bot_mcp.get_standouts.handler({}))))
    assert payload["gate_go"] is True and payload["rank_by"] == "score"
    assert payload["buy"] is None
    assert payload["read_status"] == "partial"
    rows = [{"ticker": "AAPL", "score": 9}]
    source["standouts"] = rows
    _write_json(path, source)
    payload = json.loads(_text(asyncio.run(bot_mcp.get_standouts.handler({}))))
    assert payload["gate_go"] is True and payload["rank_by"] == "score"
    assert payload["buy"] == rows
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["standouts"]


@pytest.mark.parametrize("buy_kind", ["absent", "none", "empty"])
def test_healthy_legacy_standouts_fallback_is_preserved(bot_mcp, monkeypatch, tmp_path, buy_kind):
    path = _standouts_path(bot_mcp, monkeypatch, tmp_path)
    rows = [{"ticker": "AAPL", "score": 9}]
    source = {"gate_go": True, "rank_by": "score", "standouts": rows}
    if buy_kind != "absent":
        source["buy"] = None if buy_kind == "none" else []
    _write_json(path, source)
    payload = json.loads(_text(asyncio.run(bot_mcp.get_standouts.handler({}))))
    assert payload == {"gate_go": True, "rank_by": "score", "buy": rows}


def _unavailable_intake(bot_mcp, args):
    raw = _text(asyncio.run(bot_mcp.get_intake_candidates.handler(args)))
    assert json.loads(raw) == {
        "read_status": "unavailable",
        "error": "intake_candidates_unavailable",
        "failed_sources": ["intake"],
        "candidates": None,
    }
    assert "private-secret" not in raw
    return raw


def test_intake_import_failure_is_closed(bot_mcp, monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "brain" and "intake" in fromlist:
            raise ImportError("private-secret intake setup")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    _unavailable_intake(bot_mcp, {"limit": 5})


def test_intake_argument_setup_failure_is_closed(bot_mcp):
    _unavailable_intake(bot_mcp, {"limit": "private-secret invalid limit"})


def test_intake_serialization_failure_is_closed(bot_mcp, monkeypatch):
    from brain import intake

    circular = {}
    circular["candidates"] = circular
    monkeypatch.setattr(intake, "build", lambda limit=30: circular)
    _unavailable_intake(bot_mcp, {"limit": 5})


@pytest.mark.parametrize("salience", [None, [], False, "cycle"])
def test_invalid_optional_salience_preserves_available_candidates(bot_mcp, monkeypatch, salience):
    from brain import intake

    _wire_intake(monkeypatch)
    if salience == "cycle":
        salience = {}
        salience["act"] = salience
    monkeypatch.setattr(intake, "salience_tiers", lambda limit=30: salience)
    payload = json.loads(_text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5, "tiers": True}))))
    assert payload["candidates"] == [{"ticker": "AAPL", "score": 9}]
    assert payload["salience"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake_salience"]


def test_salience_failure_preserves_current_producer_authority_fields(bot_mcp, monkeypatch):
    from brain import intake

    producer = {
        "as_of": "2026-09-17",
        "macro_context": {"regime": "risk-on"},
        "n_universe": 5,
        "candidates": [{
            "ticker": "AAPL", "score": 9, "candidacy_score": 0,
            "sources": ["context"], "n_sources": 0, "n_observed_sources": 1,
            "reasons": ["inspectable context"], "lean": "watch", "confidence": 0.4,
            "falsifier": "new independent evidence", "source_qualification": {"context": "context_only"},
            "divergent": False,
        }],
        "note": "Research salience preserves context; portfolio candidacy requires independent qualifying evidence.",
    }
    monkeypatch.setattr(intake, "build", lambda limit=30: dict(producer))

    def failed_salience(limit=30):
        raise RuntimeError("private-secret optional salience")

    monkeypatch.setattr(intake, "salience_tiers", failed_salience)
    raw = _text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5, "tiers": True})))
    payload = json.loads(raw)
    assert {key: payload[key] for key in producer} == producer
    assert payload["salience"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake_salience"]
    assert payload["salience_note"] == "Candidate queue is available; salience tiers did not complete."
    assert "private-secret" not in raw
