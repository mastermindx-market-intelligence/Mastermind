"""Actual SDK rates-read integration: no provider calls or data publication."""
from brain import bot_mcp


def test_rates_read_is_registered_without_action_authority():
    names = [entry.name for entry in bot_mcp._READ]
    assert "get_rates_evidence" in names
    assert names.count("get_rates_evidence") == 1
    assert "get_rates_evidence" not in [entry.name for entry in bot_mcp._ACTION]
    assert "mcp__bot__get_rates_evidence" in bot_mcp.armed_allowed_tools()


import asyncio
from datetime import timedelta
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from brain import decision_context as DC, neural_web_context as NWC


@pytest.fixture
def rates_files(tmp_path, monkeypatch):
    tenors = ("2y", "5y", "10y", "20y", "30y")
    source = {"schema": "rates_command.v1", "asof": "2026-09-16",
              "built": "2026-09-16T21:00:00Z", "yield_momentum": {
        "schema": "yield_momentum.v1", "asof": "2026-09-16", "series": {
            t: {"source_column": "us" + t, "status": "available", "as_of": "2026-09-16",
                "available_at": "2026-09-16T20:00:00Z", "level": 4.5,
                "velocity_bp": {"5d": 12.0, "22d": 20.0, "63d": 30.0},
                "acceleration_bp": -8.0, "turn_watch": "extreme_high_watch"}
            for t in tenors}}}
    ric = tmp_path / "ric.json"; ric.write_text(json.dumps(source))
    regime = tmp_path / "regime.json"; regime.write_text(json.dumps({"date": "2026-09-16"}))
    output = tmp_path / "must-not-be-published"
    monkeypatch.setattr(DC, "_RATES_COMMAND_PATH", ric)
    monkeypatch.setattr(DC, "_MARKET_VIEW_PATH", tmp_path / "missing_market_view.json")
    monkeypatch.setattr(DC, "_ARTIFACT_DIR", output)
    monkeypatch.setattr(DC, "_LATEST_PATH", output / "latest.json")
    monkeypatch.setattr(DC._rf, "_read_raw", lambda _region: json.loads(regime.read_text()))
    monkeypatch.setattr(NWC, "context", lambda: {})
    return ric, source, output


def call_direct():
    response = asyncio.run(bot_mcp.get_rates_evidence.handler({}))
    return json.loads(response["content"][0]["text"])


def test_file_backed_read_uses_canonical_builder_without_publishing(rates_files):
    ric, _source, output = rates_files
    before = ric.read_bytes()
    out = call_direct()
    assert out["schema"] == "decision_context.rates_evidence.v1"
    assert out["series"]["10y"]["level"] == 4.5
    assert out["series"]["10y"]["velocity_bp"]["5d"] == 12.0
    assert out["observation_timezone"] == "America/New_York"
    assert out["analysis_mode"] == "dated_context"
    assert out["current_session_freshness"] == "not_certified"
    assert out["horizon_basis"] == "observed_intervals_not_verified_exchange_sessions"
    assert out["authority"]["allowed_effect"] == "annotate_only"
    assert not any(v for k,v in out["authority"].items() if k.startswith("can_"))
    assert out["as_observed_replay_certified"] is False
    assert ric.read_bytes() == before
    assert not output.exists()


def test_missing_artifact_is_unavailable_not_flat_or_calm(rates_files):
    ric, _source, _output = rates_files
    ric.unlink()
    out = call_direct()
    assert out["status"] == "unavailable"
    assert out["coverage"]["context_rows"] == 0
    assert all(row["level"] is None for row in out["series"].values())
    assert "source_missing" in out["issues"]


def test_read_does_not_manufacture_availability(rates_files):
    ric, source, _output = rates_files
    for row in source["yield_momentum"]["series"].values():
        row["available_at"] = None
    ric.write_text(json.dumps(source))
    out = call_direct()
    assert out["coverage"] == {"requested_rows": 5, "context_rows": 5, "timed_context_rows": 0}
    assert out["as_observed_replay_certified"] is False


def test_stale_maturity_stays_withheld_in_tool(rates_files):
    ric, source, _output = rates_files
    source["yield_momentum"]["series"]["10y"]["as_of"] = "2026-09-15"
    ric.write_text(json.dumps(source))
    out = call_direct()
    assert out["coverage"]["context_rows"] == 4
    assert out["series"]["10y"]["level"] is None
    assert out["series"]["10y"]["turn_watch"] is None
    assert out["series"]["5y"]["level"] == 4.5


def test_exception_is_secret_safe_and_has_no_fallback_signal(rates_files, monkeypatch):
    secret = "PRIVATE_TOKEN_MUST_NEVER_LEAVE_THE_SOURCE"
    def broken_builder(**_kwargs):
        raise RuntimeError(secret)
    monkeypatch.setattr(DC, "build", broken_builder)
    out = call_direct()
    assert secret not in json.dumps(out)
    assert out["status"] == "unavailable"
    assert out["coverage"]["context_rows"] == 0
    assert "decision_context_read_failed" in out["issues"]
    assert out["authority"]["can_trade"] is False


def test_untrusted_prose_never_enters_mcp_payload(rates_files):
    ric, source, _output = rates_files
    source["instructions"] = "UNTRUSTED_資料" * 10000
    source["can_trade"] = True
    ric.write_text(json.dumps(source, ensure_ascii=False))
    out = call_direct(); encoded = json.dumps(out, ensure_ascii=False, allow_nan=False)
    assert "UNTRUSTED" not in encoded
    assert len(encoded.encode("utf-8")) <= 8000
    assert "_transport_truncated" not in out
    assert out["authority"]["can_trade"] is False


def test_real_sdk_memory_transport_preserves_complete_rates_contract(rates_files):
    async def roundtrip():
        server = bot_mcp.build_server()["instance"]
        async with create_connected_server_and_client_session(
            server, read_timeout_seconds=timedelta(seconds=10), raise_exceptions=True
        ) as session:
            listing = await session.list_tools()
            names = [entry.name for entry in listing.tools]
            assert names.count("get_rates_evidence") == 1
            return await session.call_tool("get_rates_evidence", {})
    result = asyncio.run(roundtrip())
    assert result.isError is False
    text = result.content[0].text
    out = json.loads(text)
    assert out["coverage"]["context_rows"] == 5
    assert out["series"]["10y"]["level"] == 4.5
    assert out["series"]["10y"]["velocity_bp"]["22d"] == 20.0
    assert out["level_unit"] == "percent" and out["change_unit"] == "basis_points"
    assert out["as_observed_replay_certified"] is False
    assert out["authority"]["can_size"] is False
    assert "_transport_truncated" not in out
    assert len(text.encode("utf-8")) <= 8000


@pytest.fixture
def ticker_rates_files(rates_files, tmp_path, monkeypatch):
    root=tmp_path/"ticker_macro"
    target=root/"site/intelligence/by_ticker.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"as_of":"2026-09-10",
        "tickers":{"AMD":{"ticker":"AMD","read":"existing stock evidence"}}}))
    monkeypatch.setattr(bot_mcp,"_V",root)
    from portfolio import lenses
    from brain import intake
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_:{})
    monkeypatch.setattr(lenses,"synthesize",lambda _: {"divergences":[],"confluence":[],"vetoes":[]})
    monkeypatch.setattr(intake,"queue",lambda _:[])
    return rates_files,target


def test_stock_tool_actual_sdk_keeps_rates_dates_separate(ticker_rates_files):
    (ric,_source,output),target=ticker_rates_files
    before=(ric.read_bytes(),target.read_bytes())
    async def roundtrip():
        server=bot_mcp.build_server()["instance"]
        async with create_connected_server_and_client_session(
            server,read_timeout_seconds=timedelta(seconds=10),raise_exceptions=True
        ) as session:
            return await session.call_tool("get_ticker_package",{"ticker":"AMD"})
    result=asyncio.run(roundtrip())
    assert result.isError is False
    text=result.content[0].text; out=json.loads(text)
    assert out["ticker"]=="AMD"
    assert out["rates_context"]["series"]["10y"]["level"]==4.5
    assert out["rates_context"]["artifact_asof"]=="2026-09-16"
    assert out["rates_relationship"]["intelligence_artifact_asof"]=="2026-09-10"
    assert out["rates_relationship"]["decision_time_join"]=="not_established"
    assert out["rates_context"]["authority"]["can_rank"] is False
    assert len(text.encode("utf-8"))<=8000
    assert before==(ric.read_bytes(),target.read_bytes())
    assert not output.exists()


def test_stock_sdk_handler_preserves_name_when_rates_missing(ticker_rates_files):
    (ric,_source,_output),_target=ticker_rates_files
    ric.unlink()
    out=json.loads(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker":"AMD"}))["content"][0]["text"])
    assert out["intelligence"]["read"]=="existing stock evidence"
    assert out["rates_context"]["status"]=="unavailable"
    assert out["rates_context"]["coverage"]["context_rows"]==0


def test_stock_tool_ignores_caller_supplied_rates_cutoff_and_authority(ticker_rates_files):
    out=json.loads(asyncio.run(bot_mcp.get_ticker_package.handler({
        "ticker":"AMD","rates_cutoff":"1900-01-01","can_trade":True,
        "source_path":"/not/an/accepted/source"}))["content"][0]["text"])
    assert out["rates_context"]["analysis_mode"]=="dated_context"
    assert out["rates_context"]["analysis_cutoff"] is None
    assert out["rates_context"]["authority"]["can_trade"] is False
    assert "/not/an/accepted/source" not in json.dumps(out)
