"""Brain discovery surfaces must not convert unreadable evidence into an empty universe."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types


def _load_bot_mcp_with_fake_sdk(monkeypatch):
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
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    sys.modules.pop("brain.bot_mcp", None)
    return importlib.import_module("brain.bot_mcp")


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _break(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken secret token=do-not-return")


def test_missing_themes_are_unavailable_not_false_empty(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload == {
        "as_of": None,
        "themes": None,
        "read_status": "unavailable",
        "error": "themes_unavailable",
        "failed_sources": ["themes"],
    }


def test_healthy_empty_theme_universe_is_still_a_real_empty_result(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "basketdata" / "baskets.json", {
        "as_of": "2026-09-17", "baskets": []
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({}))))
    assert payload == {"as_of": "2026-09-17", "themes": []}


def test_corrupt_themes_are_closed_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "basketdata" / "baskets.json")

    raw = _text(asyncio.run(bot_mcp.get_themes.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["themes"] is None
    assert payload["error"] == "themes_unavailable"
    assert "secret" not in raw and "do-not-return" not in raw


def test_malformed_theme_row_preserves_good_rows_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
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


def test_missing_standouts_keeps_existing_not_built_message(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    assert _text(asyncio.run(bot_mcp.get_standouts.handler({}))) == (
        "us_standouts.json not built locally (ships in the Pages artifact)."
    )


def test_corrupt_or_empty_existing_standouts_are_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
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


def test_wrong_standout_buy_shape_preserves_metadata_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
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


def test_intake_build_failure_is_unavailable_and_secret_safe(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
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


def test_salience_failure_preserves_candidate_queue_as_partial(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    _wire_intake(monkeypatch, salience_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5, "tiers": True})))
    payload = json.loads(raw)
    assert payload["candidates"] == [{"ticker": "AAPL", "score": 9}]
    assert payload["salience"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake_salience"]
    assert "secret" not in raw and "do-not-return" not in raw


def test_healthy_intake_queue_keeps_existing_shape(monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    _wire_intake(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 5, "tiers": True}))))
    assert payload["candidates"][0]["ticker"] == "AAPL"
    assert payload["salience"] == {"act": ["AAPL"]}
    assert "read_status" not in payload
