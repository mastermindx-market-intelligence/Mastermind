"""Research proposal queue persistence and producer/consumer serialization truth."""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import threading
import time
import types
from pathlib import Path


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


def _args(subject="NVDA", lean="add"):
    return {
        "subject": subject,
        "lean": lean,
        "conviction": "high",
        "horizon_d": 21,
        "thesis": f"{subject} thesis",
        "evidence": ["e1"],
        "prob_correct": 0.72,
    }


def _row(subject="NVDA", lean="add", status="proposed"):
    return {
        "source": "claude_cli",
        "status": status,
        **_args(subject, lean),
        "logged_at": "2026-09-17T20:00:00+00:00",
    }


def _wire_queue(monkeypatch, bot_mcp, rd, tmp_path):
    queue = tmp_path / "proposals.jsonl"
    monkeypatch.setattr(bot_mcp, "_PROPOSALS", queue)
    monkeypatch.setattr(rd, "_PROPOSALS", queue)
    return queue


def _text(result):
    return result["content"][0]["text"]


def _rows(queue: Path):
    return [json.loads(line) for line in queue.read_text().splitlines() if line.strip()]


def test_producer_write_failure_is_closed_and_preserves_prior_queue(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    previous = json.dumps(_row("OLD")) + "\n"
    queue.write_text(previous)
    original_open = Path.open
    original_replace = os.replace

    class PartialAppend:
        def __init__(self, fh):
            self.fh = fh
        def __enter__(self):
            return self
        def write(self, _text):
            self.fh.write("{")
            self.fh.flush()
            raise OSError("secret /Users/private/queue token=do-not-return")
        def __exit__(self, *_args):
            self.fh.close()
            return False

    def injected_open(self, mode="r", *args, **kwargs):
        if self == queue and mode == "a":
            return PartialAppend(original_open(self, mode, *args, **kwargs))
        return original_open(self, mode, *args, **kwargs)

    def fail_replace(src, dst):
        if Path(dst) == queue:
            raise OSError("secret /Users/private/replace token=do-not-return")
        return original_replace(src, dst)

    monkeypatch.setattr(Path, "open", injected_open)
    monkeypatch.setattr(os, "replace", fail_replace)

    try:
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW"))))
    except Exception as exc:  # parent RED: raw direct-append failure
        raw = f"RAISED:{type(exc).__name__}:{exc}"

    assert not raw.startswith("RAISED:")
    payload = json.loads(raw)
    assert payload["write_status"] == "unavailable"
    assert payload["error"] == "research_proposal_queue_unavailable"
    assert payload["proposal_queued"] is False
    assert queue.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))
    assert "secret" not in raw and "/Users/private" not in raw and "token=" not in raw


def test_malformed_existing_queue_blocks_producer_without_overwrite(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    malformed = '{broken-existing-evidence\n'
    queue.write_text(malformed)

    raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("AAPL"))))

    payload = json.loads(raw)
    assert payload["write_status"] == "unavailable"
    assert payload["error"] == "research_proposal_queue_unavailable"
    assert payload["proposal_queued"] is False
    assert queue.read_text() == malformed


def test_enqueue_during_ingest_is_not_lost(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import ledger
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    queue.write_text(json.dumps(_row("NVDA")) + "\n")
    monkeypatch.setattr(rd, "_engine_blocked", lambda _subject: False)

    inside_ingest = threading.Event()
    release_ingest = threading.Event()
    producer_started = threading.Event()
    producer_done = threading.Event()
    errors = []
    ingest_result = []
    producer_text = []

    def gated_ledger_append(_doc):
        inside_ingest.set()
        if not release_ingest.wait(timeout=5):
            raise TimeoutError("test did not release ingest")
        return {"appended": True, "thesis_id": _doc["id"], "reason": None}

    monkeypatch.setattr(ledger, "append_receipt", gated_ledger_append)

    def run_ingest():
        try:
            ingest_result.append(rd.ingest_proposals(asof="2026-09-17"))
        except Exception as exc:
            errors.append(exc)

    def run_producer():
        producer_started.set()
        try:
            producer_text.append(_text(asyncio.run(bot_mcp.propose_thesis.handler(_args("MSFT")))))
        except Exception as exc:
            errors.append(exc)
        finally:
            producer_done.set()

    ingest = threading.Thread(target=run_ingest)
    ingest.start()
    assert inside_ingest.wait(timeout=5)

    producer = threading.Thread(target=run_producer)
    producer.start()
    assert producer_started.wait(timeout=5)
    # Historical code appends immediately here; repaired code waits on the shared queue lock.
    time.sleep(0.10)
    release_ingest.set()
    ingest.join(timeout=10)
    producer.join(timeout=10)

    assert not ingest.is_alive() and not producer.is_alive()
    assert errors == []
    assert ingest_result and ingest_result[0]["ingested"] == 1
    assert producer_done.is_set() and producer_text and "thesis proposed" in producer_text[0]
    rows = _rows(queue)
    by_subject = {row["subject"]: row for row in rows}
    assert set(by_subject) == {"NVDA", "MSFT"}
    assert by_subject["NVDA"]["status"] == "ingested"
    assert by_subject["MSFT"]["status"] == "proposed"


def test_post_ledger_queue_update_failure_returns_effect_receipt_and_preserves_queue(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import ledger
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    previous = json.dumps(_row("NVDA")) + "\n"
    queue.write_text(previous)
    monkeypatch.setattr(rd, "_engine_blocked", lambda _subject: False)
    effects = []
    monkeypatch.setattr(
        ledger,
        "append_receipt",
        lambda doc: effects.append(dict(doc)) or {"appended": True, "thesis_id": doc["id"], "reason": None},
    )
    original_write_text = Path.write_text
    original_replace = os.replace

    def partial_direct_rewrite(self, text, *args, **kwargs):
        if self == queue:
            original_write_text(self, "{", *args, **kwargs)
            raise OSError("secret /Users/private/rewrite token=do-not-return")
        return original_write_text(self, text, *args, **kwargs)

    def fail_replace(src, dst):
        if Path(dst) == queue:
            raise OSError("secret /Users/private/replace token=do-not-return")
        return original_replace(src, dst)

    monkeypatch.setattr(Path, "write_text", partial_direct_rewrite)
    monkeypatch.setattr(os, "replace", fail_replace)

    try:
        out = rd.ingest_proposals(asof="2026-09-17")
    except Exception as exc:  # parent RED: raw rewrite failure after ledger effect
        out = {"raised": f"{type(exc).__name__}:{exc}"}

    assert "raised" not in out
    assert len(effects) == 1
    assert out["proposal_queue_status"] == "unavailable"
    assert out["error"] == "proposal_queue_update_unavailable"
    assert out["proposal_rows_marked"] is False
    assert out["ingested"] == 1
    assert out["theses"][0]["appended"] is True
    assert queue.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))
    assert "effect" in out["note"].lower() or "ledger" in out["note"].lower()


def test_normal_enqueue_then_ingest_preserves_existing_success_contract(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    from brain import ledger
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    monkeypatch.setattr(ledger, "_LEDGER", tmp_path / "theses.jsonl")
    monkeypatch.setattr(rd, "_engine_blocked", lambda _subject: False)

    text = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NVDA"))))
    assert "thesis proposed" in text and "NOT executed" in text
    proposed = _rows(queue)
    assert len(proposed) == 1 and proposed[0]["status"] == "proposed"
    assert proposed[0]["subject"] == "NVDA" and proposed[0].get("logged_at")

    out = rd.ingest_proposals(asof="2026-09-17")
    assert set(out) == {"ingested", "clamped", "theses", "asof"}
    assert out["ingested"] == 1 and out["theses"][0]["appended"] is True
    consumed = _rows(queue)
    assert consumed[0]["status"] == "ingested" and consumed[0]["thesis_id"]
    assert ledger.all_theses()[0]["subject"] == "NVDA"
