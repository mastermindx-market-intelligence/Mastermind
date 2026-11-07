"""Advisor chat: persona + session glue + the SSE streaming transform.

These run WITHOUT a Claude credential — the live SDK call is monkeypatched with a fake
message stream so we can assert that cli_bridge.chat_stream maps SDK messages
(AssistantMessage text/tool_use blocks, ResultMessage) to the right SSE event dicts.
"""
from __future__ import annotations

import asyncio

from brain import advisor, cli_bridge


# --------------------------------------------------------------------------- #
# persona + session store
# --------------------------------------------------------------------------- #
def test_persona_encodes_doctrine():
    s = advisor.SYSTEM.lower()
    assert "mastermind portfolio research advisor" in s
    assert "not the public mastermind ai" in s
    assert "no real money" in s              # paper-only safety
    assert "decision_matrix" in s            # tool playbook present
    # evaluate -> research paper -> proposal; deterministic engines retain action authority
    assert "evaluate_gate" in s and "file_research_paper" in s
    assert "propose_portfolio_action" in s and "execute_trade" not in s
    assert "cannot size an order" in s and "book did not change" in s


def test_public_advisor_greeting_is_proposal_only():
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app" / "static" / "chat.js").read_text()
    assert "queue an ADD proposal for deterministic review" in source
    assert "No order is sized or filled here, and the book does not change" in source
    assert "排队一份交由确定性引擎审核的加仓提案" in source
    assert "decide whether to add it to the paper book" not in source
    assert "再决定是否加入模拟组合" not in source


def test_session_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(advisor, "_SESSIONS", tmp_path / "chat_sessions.json")
    cid = advisor.new_conversation_id()
    assert advisor.get_session(cid) is None
    advisor.set_session(cid, "sess-1")
    assert advisor.get_session(cid) == "sess-1"
    advisor.set_session(cid, None)           # no-op: never clobber with empty
    assert advisor.get_session(cid) == "sess-1"
    advisor.set_session(cid, "sess-2")       # next turn updates the resume token
    assert advisor.get_session(cid) == "sess-2"


# --------------------------------------------------------------------------- #
# the streaming transform
# --------------------------------------------------------------------------- #
class _Block:
    def __init__(self, type, text=None, name=None, input=None):
        self.type = type
        if text is not None:
            self.text = text
        if name is not None:
            self.name = name
        if input is not None:
            self.input = input


class _Assistant:                            # has .content, no .result
    def __init__(self, content):
        self.content = content


class _Result:                               # has .result -> end of turn
    def __init__(self, result, session_id, cost):
        self.result = result
        self.session_id = session_id
        self.total_cost_usd = cost


def _drain(agen):
    async def run():
        return [ev async for ev in agen]
    return asyncio.run(run())


def test_chat_stream_maps_messages_to_events(monkeypatch):
    async def fake_query(*, prompt, options):
        # the advisor persona must be wired onto the SDK options
        assert options.append_system_prompt
        assert "Mastermind Portfolio Research Advisor" in options.append_system_prompt
        assert options.setting_sources == ["project"]
        yield _Assistant([
            _Block("text", text="Regime is Goldilocks."),
            _Block("tool_use", name="mcp__bot__get_regime", input={}),
        ])
        yield _Result("final", "sess-xyz", 0.012)

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", fake_query)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")

    evs = _drain(cli_bridge.chat_stream("hi", append_system=advisor.SYSTEM))
    types = [e["type"] for e in evs]
    assert "text" in types and "tool" in types
    assert types[-1] == "done"
    assert next(e for e in evs if e["type"] == "text")["text"] == "Regime is Goldilocks."
    assert next(e for e in evs if e["type"] == "tool")["name"] == "mcp__bot__get_regime"
    done = evs[-1]
    assert done["session_id"] == "sess-xyz"
    assert done["tools_used"] == ["mcp__bot__get_regime"]


# Doubles that mimic the REAL claude_agent_sdk content blocks: dataclass-like objects
# whose KIND is carried by the class NAME, with NO `.type` field. The legacy `.type`-based
# dispatch dropped these silently -> the live-chat "(no response)" regression. _block_kind
# must key off the class name; these guard it.
class TextBlock:
    def __init__(self, text):
        self.text = text


class ToolUseBlock:
    def __init__(self, name, input=None, id="t1"):
        self.id, self.name, self.input = id, name, input or {}


class ToolResultBlock:
    def __init__(self, content, tool_use_id="t1"):
        self.tool_use_id, self.content, self.is_error = tool_use_id, content, False


def test_chat_stream_handles_typeless_sdk_blocks(monkeypatch):
    """Regression: real SDK blocks have no `.type` — text must still stream."""
    async def fake_query(*, prompt, options):
        yield _Assistant([
            TextBlock("Regime is Goldilocks."),
            ToolUseBlock("mcp__bot__get_regime", {}),
        ])
        yield _Result("Regime is Goldilocks.", "sess-xyz", 0.012)

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", fake_query)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")

    evs = _drain(cli_bridge.chat_stream("hi"))
    texts = [e["text"] for e in evs if e["type"] == "text"]
    assert texts == ["Regime is Goldilocks."]          # streamed once (not also via fallback)
    assert next(e for e in evs if e["type"] == "tool")["name"] == "mcp__bot__get_regime"
    assert evs[-1]["type"] == "done" and evs[-1]["tools_used"] == ["mcp__bot__get_regime"]


def test_chat_stream_falls_back_to_result_text(monkeypatch):
    """Backstop: if no text block is recognised but the ResultMessage carries the final
    text, surface it so the chat is never silently empty."""
    class _Mystery:                                    # an unrecognised content shape
        def __init__(self):
            self.content = [object()]                  # neither text/tool/tool_result

    async def fake_query(*, prompt, options):
        yield _Mystery()
        yield _Result("Here is the answer.", "sess-1", 0.01)

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", fake_query)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")

    evs = _drain(cli_bridge.chat_stream("hi"))
    assert [e["text"] for e in evs if e["type"] == "text"] == ["Here is the answer."]
    assert evs[-1]["type"] == "done"


def test_chat_stream_surfaces_sdk_exception(monkeypatch):
    async def boom(*, prompt, options):
        if False:
            yield {}
        raise RuntimeError("cli exploded")

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", boom)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")

    evs = _drain(cli_bridge.chat_stream("hi"))
    # The stream surfaces the error, then still terminates with a `done` (which
    # carries the resume session_id + tools_used even on a failed turn) — post-stream
    # bookkeeping (key-failure detection, response ledger) runs between the two.
    err = next(e for e in evs if e["type"] == "error")
    assert "cli exploded" in err["error"]
    assert evs[-1]["type"] == "done"


def test_chat_stream_errors_without_sdk(monkeypatch):
    monkeypatch.setattr(cli_bridge, "_SDK", False)
    evs = _drain(cli_bridge.chat_stream("hi"))
    assert len(evs) == 1 and evs[0]["type"] == "error"


# --------------------------------------------------------------------------- #
# Phase 3: typed convenience tools + transcript persistence
# --------------------------------------------------------------------------- #
def test_typed_tools_registered_and_armed():
    from brain import bot_mcp
    for nm in ("get_fundamentals", "get_options", "get_anticipation"):
        full = "mcp__bot__" + nm
        assert full in bot_mcp.TOOL_NAMES
        assert full in bot_mcp.armed_allowed_tools()
    assert "mcp__bot__propose_portfolio_action" in bot_mcp.TOOL_NAMES
    assert "mcp__bot__propose_portfolio_action" in bot_mcp.armed_allowed_tools()
    assert "mcp__bot__execute_trade" not in bot_mcp.TOOL_NAMES
    assert "mcp__bot__execute_trade" not in bot_mcp.armed_allowed_tools()
    schema = bot_mcp.propose_portfolio_action.input_schema
    assert set(schema["required"]) == {"ticker", "action", "thesis", "evidence", "urgency"}
    assert not ({"weight", "size", "shares", "notional", "price", "fill"}
                & set(schema["properties"]))


def test_chat_stream_emits_paper_event(monkeypatch):
    import json as _json

    from brain import bot_mcp

    class _Blk:
        def __init__(self, **k):
            self.__dict__.update(k)

    class _Msg:
        def __init__(self, blocks):
            self.content = blocks

    class _Res:
        def __init__(self):
            self.result = "done"
            self.session_id = "sid"
            self.total_cost_usd = 0.0

    meta = {"paper_id": "2026-06-21-NVDA", "ticker": "NVDA", "combined": 71, "confirmed": True}

    async def fake_query(*, prompt, options):
        yield _Msg([_Blk(type="tool_use", name="mcp__bot__file_research_paper", input={"ticker": "NVDA"})])
        yield _Msg([_Blk(type="tool_result", content=bot_mcp.PAPER_MARKER + " " + _json.dumps(meta))])
        yield _Res()

    monkeypatch.setattr(cli_bridge, "_SDK", True)
    monkeypatch.setattr(cli_bridge, "_sdk_query", fake_query)
    monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/usr/bin/claude")
    evs = _drain(cli_bridge.chat_stream("add NVDA"))
    paper = next(e for e in evs if e["type"] == "paper")
    assert paper["ticker"] == "NVDA" and paper["confirmed"] is True and paper["combined"] == 71


def test_execute_fill_never_touches_other_positions(tmp_path, monkeypatch):
    import json as _json

    from portfolio import paper_account as pa
    monkeypatch.setattr(pa, "_DATA", tmp_path)
    monkeypatch.setattr(pa, "_ACCOUNT_PATH", tmp_path / "account.json")
    monkeypatch.setattr(pa, "_FILLS_PATH", tmp_path / "fills.jsonl")
    (tmp_path / "account.json").write_text(_json.dumps({
        "inception_date": "2026-06-20", "starting_nav": 1_000_000.0, "cash": 500_000.0,
        "positions": {"XLK": {"shares": 1000, "avg_cost": 200.0}}, "spy_shares": None}))
    r = pa.execute_fill("NVDA", "buy", weight=0.03, price=100.0, asof="2026-06-21")
    acct = _json.loads((tmp_path / "account.json").read_text())
    assert r["ok"] and "NVDA" in acct["positions"]
    assert acct["positions"]["XLK"]["shares"] == 1000          # untouched
    assert acct["cash"] < 500_000.0
    # exit closes the single name only
    pa.execute_fill("NVDA", "sell", price=110.0, asof="2026-06-21")
    acct = _json.loads((tmp_path / "account.json").read_text())
    assert "NVDA" not in acct["positions"] and acct["positions"]["XLK"]["shares"] == 1000
    fills = [l for l in (tmp_path / "fills.jsonl").read_text().splitlines() if l.strip()]
    assert len(fills) == 2
    # selling a name we don't hold is refused, not an exception
    assert pa.execute_fill("ZZZZ", "sell", price=5.0)["ok"] is False


def test_advisor_action_is_proposal_only_and_cannot_touch_paper_state(tmp_path, monkeypatch):
    import json as _json

    from brain import bot_mcp
    from brain import research_paper as rp
    from portfolio import advisor_trade
    from portfolio import paper_account as pa
    from portfolio import position_log as pl

    proposals = tmp_path / "recommendations.jsonl"
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", proposals)
    monkeypatch.setattr(rp, "latest_for", lambda ticker: {"ticker": ticker, "confirmed": True})

    # Any regression into the former mutation path fails loudly.
    monkeypatch.setattr(pa, "execute_fill", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Portfolio Advisor must not call paper_account.execute_fill")))
    monkeypatch.setattr(pl, "record_manual", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Portfolio Advisor must not write the position ledger")))

    result = asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "aapl",
        "action": "add",
        "thesis": "Services mix and device replacement improve earnings durability.",
        "evidence": ["research:2026-06-21-AAPL", "decision_matrix:confluence=0.42"],
        "urgency": "next_cycle",
    }))
    text = result["content"][0]["text"]
    assert "PROPOSAL_QUEUED" in text and "no order was sized or filled" in text

    row = _json.loads(proposals.read_text().strip())
    assert row["schema"] == "portfolio_action_proposal.v1"
    assert row["ticker"] == "AAPL" and row["action"] == "add"
    assert row["status"] == "proposed" and row["executed"] is False
    assert row["urgency"] == "next_cycle" and len(row["evidence"]) == 2
    assert row["sizing_authority"] == "deterministic_scheduled_engine_only"
    assert not ({"weight", "size", "shares", "notional", "price", "fill"} & set(row))
    assert not hasattr(advisor_trade, "execute")


def test_advisor_action_refuses_size_fields_before_writing(tmp_path, monkeypatch):
    from brain import bot_mcp
    from brain import research_paper as rp
    from portfolio import advisor_trade

    proposals = tmp_path / "recommendations.jsonl"
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", proposals)
    monkeypatch.setattr(rp, "latest_for", lambda ticker: {"ticker": ticker, "confirmed": True})

    result = asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL",
        "action": "add",
        "thesis": "Confirmed research thesis.",
        "evidence": ["research:2026-06-21-AAPL"],
        "urgency": "next_cycle",
        "weight": 0.03,  # direct handler call bypasses the MCP JSON-schema validator
    }))
    text = result["content"][0]["text"]
    assert "REFUSED" in text and "weight" in text
    assert "No proposal queued" in text and "no paper account changed" in text
    assert not proposals.exists()


def test_add_proposal_requires_confirmed_research(tmp_path, monkeypatch):
    from brain import bot_mcp
    from brain import research_paper as rp
    from portfolio import advisor_trade

    proposals = tmp_path / "recommendations.jsonl"
    monkeypatch.setattr(advisor_trade, "_PROPOSALS", proposals)
    monkeypatch.setattr(rp, "latest_for", lambda ticker: None)
    result = asyncio.run(bot_mcp.propose_portfolio_action.handler({
        "ticker": "AAPL",
        "action": "add",
        "thesis": "Not yet confirmed.",
        "evidence": ["decision_matrix:preliminary"],
        "urgency": "routine",
    }))
    text = result["content"][0]["text"]
    assert "no CONFIRMED research paper" in text
    assert "No proposal queued" in text and not proposals.exists()


def test_history_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(advisor, "_HISTORY", tmp_path)
    cid = advisor.new_conversation_id()
    assert advisor.load_history(cid) == []
    advisor.append_turn(cid, "user", "should we add NVDA?")
    advisor.append_turn(cid, "brain", "ADD — starter only.",
                        [{"name": "mcp__bot__get_decision_matrix", "args": {"subject": "NVDA"}}])
    advisor.append_turn(cid, "brain", "", None)            # empty turn is a no-op
    h = advisor.load_history(cid)
    assert len(h) == 2
    assert h[0]["role"] == "user" and h[0]["content"] == "should we add NVDA?"
    assert h[1]["tools"][0]["name"].endswith("get_decision_matrix")
    assert advisor.load_history(None) == []                # missing id never throws
