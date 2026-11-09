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
from contextlib import contextmanager, nullcontext

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
    from brain import ledger
    monkeypatch.setattr(ledger, "_LEDGER", tmp_path / "theses.jsonl")
    monkeypatch.setattr(rd, "_engine_blocked", lambda _subject: False)
    return queue


def _text(result):
    return result["content"][0]["text"]


def _rows(queue: Path):
    return [json.loads(line) for line in queue.read_text().splitlines() if line.strip()]


def test_producer_write_failure_is_closed_and_preserves_prior_queue(tmp_path, monkeypatch, bot_mcp):
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    previous = json.dumps(_row("OLD")) + "\n"
    queue.write_text(previous)
    original_open = Path.open

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

    def fail_fsync(_fd):
        raise OSError("secret /Users/private/staging token=do-not-return")

    monkeypatch.setattr(Path, "open", injected_open)
    monkeypatch.setattr(os, "fsync", fail_fsync)

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


def test_malformed_existing_queue_blocks_producer_without_overwrite(tmp_path, monkeypatch, bot_mcp):
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


def test_enqueue_during_ingest_is_not_lost(tmp_path, monkeypatch, bot_mcp):
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


def test_post_ledger_queue_update_failure_returns_effect_receipt_and_preserves_queue(tmp_path, monkeypatch, bot_mcp):
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

    def partial_direct_rewrite(self, text, *args, **kwargs):
        if self == queue:
            original_write_text(self, "{", *args, **kwargs)
            raise OSError("secret /Users/private/rewrite token=do-not-return")
        return original_write_text(self, text, *args, **kwargs)

    def fail_fsync(_fd):
        raise OSError("secret /Users/private/staging token=do-not-return")

    monkeypatch.setattr(Path, "write_text", partial_direct_rewrite)
    monkeypatch.setattr(os, "fsync", fail_fsync)

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


def test_normal_enqueue_then_ingest_preserves_existing_success_contract(tmp_path, monkeypatch, bot_mcp):
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


def _assert_sanitized(raw):
    assert "secret" not in raw
    assert "/Users/private" not in raw
    assert "token=" not in raw


def _wire_real(tmp_path, monkeypatch, bot_mcp):
    from brain import ledger
    from brain import research_desk as rd

    queue = _wire_queue(monkeypatch, bot_mcp, rd, tmp_path)
    return rd, ledger, queue


def _fail_queue_staging(monkeypatch, rd, queue, phase, error_type=OSError):
    original = rd.tempfile.NamedTemporaryFile

    class FailingStaging:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            result = self.wrapped.__exit__(*args)
            if phase == "close":
                raise error_type("secret /Users/private/staging token=do-not-return")
            return result

        def write(self, text):
            if phase == "write":
                self.wrapped.write("{")
                raise error_type("secret /Users/private/staging token=do-not-return")
            return self.wrapped.write(text)

        def flush(self):
            if phase == "flush":
                raise error_type("secret /Users/private/staging token=do-not-return")
            return self.wrapped.flush()

    def factory(**kwargs):
        staged = original(**kwargs)
        if kwargs.get("prefix") == f".{queue.name}.":
            return FailingStaging(staged)
        return staged

    monkeypatch.setattr(rd.tempfile, "NamedTemporaryFile", factory)


@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_dangling_queue_cannot_be_reclassified_as_absent(
    tmp_path, monkeypatch, bot_mcp, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    missing = tmp_path / "missing-queue.jsonl"
    queue.symlink_to(missing)

    if operation == "producer":
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW"))))
        payload = json.loads(raw)
        assert payload["proposal_queued"] is False
        assert payload["write_status"] == "unavailable"
        _assert_sanitized(raw)
    else:
        with pytest.raises(FileNotFoundError):
            rd.ingest_proposals(asof="2026-09-17")

    assert queue.is_symlink() and queue.readlink() == missing
    assert not missing.exists()
    assert ledger.all_theses() == []


@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_unavailable_queue_lookup_preserves_evidence_before_effects(
    tmp_path, monkeypatch, bot_mcp, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    previous = json.dumps(_row("NVDA")) + "\n"
    queue.write_text(previous)
    original_stat, original_lstat = Path.stat, Path.lstat

    def fail_stat(self, *args, **kwargs):
        if self == queue:
            raise OSError("secret /Users/private/lookup token=do-not-return")
        return original_stat(self, *args, **kwargs)

    def fail_lstat(self, *args, **kwargs):
        if self == queue:
            raise OSError("secret /Users/private/lookup token=do-not-return")
        return original_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "lstat", fail_lstat)

    if operation == "producer":
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW"))))
        payload = json.loads(raw)
        assert payload["proposal_queued"] is False
        assert payload["write_status"] == "unavailable"
        _assert_sanitized(raw)
    else:
        with pytest.raises(OSError):
            rd.ingest_proposals(asof="2026-09-17")

    assert queue.read_text() == previous
    assert ledger.all_theses() == []


@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_nonmapping_queue_row_refuses_the_whole_batch_before_effects(
    tmp_path, monkeypatch, bot_mcp, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    previous = json.dumps(_row("NVDA")) + "\nnull\n"
    queue.write_text(previous)

    if operation == "producer":
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW"))))
        payload = json.loads(raw)
        assert payload["proposal_queued"] is False
        assert payload["write_status"] == "unavailable"
    else:
        with pytest.raises(ValueError, match="row is not a mapping"):
            rd.ingest_proposals(asof="2026-09-17")

    assert queue.read_text() == previous
    assert ledger.all_theses() == []


@pytest.mark.parametrize("phase", ["write", "flush", "close"])
@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_known_queue_staging_failure_preserves_real_ledger_effect_receipts(
    tmp_path, monkeypatch, bot_mcp, phase, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    previous = json.dumps(_row("NVDA")) + "\n"
    queue.write_text(previous)
    _fail_queue_staging(monkeypatch, rd, queue, phase)

    if operation == "producer":
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW"))))
        payload = json.loads(raw)
        assert payload["proposal_queued"] is False
        assert payload["write_status"] == "unavailable"
        assert payload["error"] == "research_proposal_queue_unavailable"
        assert ledger.all_theses() == []
    else:
        payload = rd.ingest_proposals(asof="2026-09-17")
        raw = json.dumps(payload)
        assert payload["proposal_rows_marked"] is False
        assert payload["proposal_queue_status"] == "unavailable"
        assert payload["error"] == "proposal_queue_update_unavailable"
        assert payload["ingested"] == 1
        assert payload["theses"][0]["appended"] is True
        assert [row["id"] for row in ledger.all_theses()] == [payload["theses"][0]["id"]]

    assert queue.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))
    _assert_sanitized(raw)


@pytest.mark.parametrize("replacement_completed", [False, True])
@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_uncertain_queue_replace_never_claims_no_effect_or_retries(
    tmp_path, monkeypatch, bot_mcp, replacement_completed, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    previous = json.dumps(_row("NVDA")) + "\n"
    queue.write_text(previous)
    original_replace = os.replace
    calls = []

    def uncertain_replace(src, dst):
        if Path(dst) != queue:
            return original_replace(src, dst)
        calls.append((src, dst))
        if replacement_completed:
            original_replace(src, dst)
        raise OSError("secret /Users/private/replace token=do-not-return")

    monkeypatch.setattr(os, "replace", uncertain_replace)

    if operation == "producer":
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW"))))
        payload = json.loads(raw)
        assert payload["proposal_queued"] is None
        assert payload["write_status"] == "unknown"
        assert payload["error"] == "research_proposal_queue_outcome_unknown"
        assert ledger.all_theses() == []
        assert [row["subject"] for row in _rows(queue)] == (
            ["NVDA", "NEW"] if replacement_completed else ["NVDA"]
        )
    else:
        payload = rd.ingest_proposals(asof="2026-09-17")
        raw = json.dumps(payload)
        assert payload["proposal_rows_marked"] is None
        assert payload["proposal_queue_status"] == "unknown"
        assert payload["error"] == "proposal_queue_update_outcome_unknown"
        assert payload["ingested"] == 1
        assert payload["theses"][0]["appended"] is True
        assert [row["id"] for row in ledger.all_theses()] == [payload["theses"][0]["id"]]
        assert _rows(queue)[0]["status"] == ("ingested" if replacement_completed else "proposed")

    assert len(calls) == 1
    assert not list(tmp_path.glob(".*.tmp"))
    _assert_sanitized(raw)


def test_unclassified_enqueue_error_is_unknown_at_the_handler(tmp_path, monkeypatch, bot_mcp):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    calls = []

    def unclassified(row, **_kwargs):
        calls.append(row)
        raise RuntimeError("secret /Users/private/unknown token=do-not-return")

    monkeypatch.setattr(rd, "enqueue_proposal", unclassified)

    raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args())))

    payload = json.loads(raw)
    assert payload["proposal_queued"] is None
    assert payload["write_status"] == "unknown"
    assert payload["error"] == "research_proposal_queue_outcome_unknown"
    assert len(calls) == 1
    assert not queue.exists()
    assert ledger.all_theses() == []
    _assert_sanitized(raw)


def _queue_cleanup_fault(monkeypatch, rd, queue, fault):
    original_open = Path.open
    original_flock = rd.fcntl.flock
    queue_fds, observed = set(), []

    class FailingClose:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

        def close(self):
            self.wrapped.close()
            observed.append("close")
            raise OSError("secret queue close cleanup")

    def opened(self, *args, **kwargs):
        fh = original_open(self, *args, **kwargs)
        if self == rd._proposal_lock_path(queue):
            queue_fds.add(fh.fileno())
            if fault == "close":
                return FailingClose(fh)
        return fh

    def flock(fd, mode):
        if fault == "unlock" and fd in queue_fds and mode == rd.fcntl.LOCK_UN:
            observed.append("unlock")
            raise OSError("secret queue unlock cleanup")
        return original_flock(fd, mode)

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(rd.fcntl, "flock", flock)
    return observed


@pytest.mark.parametrize("fault", ["unlock", "close"])
@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_queue_cleanup_preserves_known_committed_result(
    tmp_path, monkeypatch, bot_mcp, fault, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    queue.write_text(json.dumps(_row("NVDA")) + "\n")
    observed = _queue_cleanup_fault(monkeypatch, rd, queue, fault)

    if operation == "producer":
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(_args("MSFT"))))
        assert "thesis proposed" in raw
        assert [row["subject"] for row in _rows(queue)] == ["NVDA", "MSFT"]
        assert ledger.all_theses() == []
    else:
        result = rd.ingest_proposals(asof="2026-09-17")
        assert set(result) == {"ingested", "clamped", "theses", "asof"}
        assert result["ingested"] == 1 and result["theses"][0]["appended"] is True
        assert _rows(queue)[0]["status"] == "ingested"
        assert len(ledger.all_theses()) == 1

    assert observed == [fault]


@pytest.mark.parametrize("failure", ["acquire", "replace"])
def test_queue_close_cleanup_keeps_the_primary_failure(
    tmp_path, monkeypatch, bot_mcp, failure
):
    rd, _ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    previous = json.dumps(_row("NVDA")) + "\n"
    queue.write_text(previous)
    observed = _queue_cleanup_fault(monkeypatch, rd, queue, "close")
    primary = OSError("primary queue operation failure")
    original_flock = rd.fcntl.flock

    def fail_flock(fd, mode):
        if mode == rd.fcntl.LOCK_EX:
            raise primary
        return original_flock(fd, mode)

    def fail_replace(_src, _dst):
        raise primary

    if failure == "acquire":
        monkeypatch.setattr(rd.fcntl, "flock", fail_flock)
    else:
        monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError) as caught:
        rd.enqueue_proposal(_row("NEW"))

    if failure == "acquire":
        assert caught.value.__cause__ is primary
    else:
        assert caught.value is primary
    assert observed == ["close"]
    assert queue.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("operation", ["producer", "consumer"])
def test_queue_cancellation_propagates_without_a_false_failure_response(
    tmp_path, monkeypatch, bot_mcp, operation
):
    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    previous = json.dumps(_row("NVDA")) + "\n"
    queue.write_text(previous)

    class ControlledCancellation(BaseException):
        pass

    _fail_queue_staging(monkeypatch, rd, queue, "write", ControlledCancellation)

    with pytest.raises(ControlledCancellation):
        if operation == "producer":
            asyncio.run(bot_mcp.propose_thesis.handler(_args("NEW")))
        else:
            rd.ingest_proposals(asof="2026-09-17")

    assert queue.read_text() == previous
    assert len(ledger.all_theses()) == (0 if operation == "producer" else 1)
    assert not list(tmp_path.glob(".*.tmp"))


def test_producer_retains_current_trusted_provenance_and_owner_fields(
    tmp_path, monkeypatch, bot_mcp
):
    _rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    provenance = {"source": "fixture_trusted_owner", "operation_key": "fixture-operation"}
    token = bot_mcp._INFERENCE_PROVENANCE.set(provenance)
    try:
        args = {**_args("NVDA"), "source": "forged", "operation_key": "forged",
                "status": "ingested", "logged_at": "forged"}
        raw = _text(asyncio.run(bot_mcp.propose_thesis.handler(args)))
    finally:
        bot_mcp._INFERENCE_PROVENANCE.reset(token)

    assert "thesis proposed" in raw
    row = _rows(queue)[0]
    assert row["source"] == provenance["source"]
    assert row["operation_key"] == provenance["operation_key"]
    assert row["status"] == "proposed"
    assert row["logged_at"] != "forged"
    assert ledger.all_theses() == []


@pytest.mark.parametrize("previously_present", [False, True])
@pytest.mark.parametrize("failure", ["none", "body", "import"])
def test_queue_sdk_fixture_restores_exact_cache_identity(
    monkeypatch, previously_present, failure
):
    import brain

    missing = object()
    sdk_before = sys.modules.get("claude_agent_sdk", missing)
    previous_module = types.ModuleType("previous_brain_bot_mcp")
    previous_attribute = object()
    if previously_present:
        monkeypatch.setitem(sys.modules, "brain.bot_mcp", previous_module)
        monkeypatch.setattr(brain, "bot_mcp", previous_attribute, raising=False)
    else:
        monkeypatch.delitem(sys.modules, "brain.bot_mcp", raising=False)
        monkeypatch.delattr(brain, "bot_mcp", raising=False)

    if failure == "import":
        original_import = importlib.import_module

        def fail_import(name, *args, **kwargs):
            if name == "brain.bot_mcp":
                raise ImportError("controlled queue fixture import")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", fail_import)

    expected = (
        pytest.raises(ImportError, match="controlled queue fixture import")
        if failure == "import"
        else pytest.raises(AssertionError, match="controlled queue fixture body")
        if failure == "body"
        else nullcontext()
    )
    with expected:
        with _bot_mcp_with_fake_sdk(monkeypatch) as loaded:
            assert sys.modules["brain.bot_mcp"] is loaded
            assert vars(brain)["bot_mcp"] is loaded
            if failure == "body":
                raise AssertionError("controlled queue fixture body")

    if previously_present:
        assert sys.modules["brain.bot_mcp"] is previous_module
        assert vars(brain)["bot_mcp"] is previous_attribute
    else:
        assert "brain.bot_mcp" not in sys.modules
        assert "bot_mcp" not in vars(brain)
    if sdk_before is missing:
        assert "claude_agent_sdk" not in sys.modules
    else:
        assert sys.modules["claude_agent_sdk"] is sdk_before


def test_process_queue_lock_prevents_lost_proposal_during_real_ingestion(
    tmp_path, monkeypatch, bot_mcp
):
    import fcntl
    import multiprocessing as mp

    rd, ledger, queue = _wire_real(tmp_path, monkeypatch, bot_mcp)
    queue.write_text(json.dumps(_row("NVDA")) + "\n")
    ctx = mp.get_context("fork")
    entered, attempting, release = ctx.Event(), ctx.Event(), ctx.Event()
    contended = ctx.Value("b", False)
    ingested = ctx.Value("i", -1)
    queued = ctx.Value("b", False)
    completed_after_release = ctx.Value("b", False)
    original_append = ledger.append_receipt

    def gated_append(doc):
        entered.set()
        assert release.wait(timeout=5)
        return original_append(doc)

    monkeypatch.setattr(ledger, "append_receipt", gated_append)

    def consumer():
        ingested.value = rd.ingest_proposals(asof="2026-09-17")["ingested"]

    def producer():
        assert entered.wait(timeout=5)
        with rd._proposal_lock_path(queue).open("a+", encoding="utf-8") as probe:
            try:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                contended.value = True
            else:
                fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        attempting.set()
        queued.value = rd.enqueue_proposal(_row("MSFT"))["subject"] == "MSFT"
        completed_after_release.value = release.is_set()

    first, second = ctx.Process(target=consumer), ctx.Process(target=producer)
    try:
        first.start()
        assert entered.wait(timeout=5)
        second.start()
        assert attempting.wait(timeout=5)
        assert bool(contended.value), "independent process must observe held queue lock"
        assert first.pid != second.pid and os.getpid() not in (first.pid, second.pid)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)

    assert first.exitcode == 0 and second.exitcode == 0
    assert ingested.value == 1 and bool(queued.value) is True
    assert bool(completed_after_release.value) is True
    by_subject = {row["subject"]: row for row in _rows(queue)}
    assert set(by_subject) == {"NVDA", "MSFT"}
    assert by_subject["NVDA"]["status"] == "ingested"
    assert by_subject["MSFT"]["status"] == "proposed"
    assert [row["subject"] for row in ledger.all_theses()] == ["NVDA"]
