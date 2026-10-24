"""Existing Claude invocation identity on a local start refusal.

The real bridge, veto, run-log persistence and exception routing execute.
Transports and credential/cost effects are recording fakes; no provider runs.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone
import inspect
import json
from types import SimpleNamespace

import pytest

from test_provider_start_veto_cleanup import FIXED_REFUSAL, invalid_verdict

BOOKS = ("autonomous", "china", "hk")
CANDIDATES = [
    {"key_id": "fixture-a", "env_name": "SYNTHETIC_UNUSED_A"},
    {"key_id": "fixture-b", "env_name": "SYNTHETIC_UNUSED_B"},
]
AUTH_FAILURE = "disabled claude subscription access"


class RunBindingHarness:
    def __init__(self, monkeypatch, root):
        from brain import cli_bridge, key_rotor, runlog, thinking_log
        self.cb, self.kr, self.rl = cli_bridge, key_rotor, runlog
        self.mp, self.root = monkeypatch, root
        self.created, self.refusals, self.checks = [], [], []
        self.providers, self.classifications, self.cooling, self.sessions = [], [], [], []
        self.plans = []
        self.clock_tick = 0
        monkeypatch.setattr(cli_bridge, "_SDK", True)
        monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/synthetic/claude")
        monkeypatch.setattr(cli_bridge, "_cfg", lambda: {"reasoning": {
            "max_turns": 2, "research_max_turns": 2, "permission_mode": "default",
        }})
        monkeypatch.setattr(cli_bridge, "_Options", lambda **kw: SimpleNamespace(**kw), raising=False)
        monkeypatch.setattr(cli_bridge, "_sdk_query", self.query, raising=False)
        monkeypatch.setattr(cli_bridge, "_subscription_env", lambda *_: {})
        monkeypatch.setattr(cli_bridge, "_record_cli_cost", lambda *a, **kw: None)
        monkeypatch.setattr(thinking_log, "log_turn_async", lambda **kw: None)
        monkeypatch.setattr(key_rotor, "candidates", lambda: [])
        real_classify = key_rotor.classify_failure
        def classify(value, *a, **kw):
            self.classifications.append((value, a, kw))
            return real_classify(value, *a, **kw)
        monkeypatch.setattr(key_rotor, "classify_failure", classify)
        monkeypatch.setattr(key_rotor, "mark_cooling", lambda *a, **kw: self.cooling.append((a, kw)))
        monkeypatch.setattr(key_rotor, "record_session", lambda *a, **kw: self.sessions.append((a, kw)))
        monkeypatch.setattr(runlog, "_RUNS_DIR", root / "runs")
        monkeypatch.setattr(runlog, "_INDEX", root / "runs" / "index.jsonl")
        monkeypatch.setattr(runlog, "_now", self.now)
        original_start = runlog.start_run
        def start(*a, **kw):
            run_id = original_start(*a, **kw)
            self.created.append(run_id)
            return run_id
        monkeypatch.setattr(runlog, "start_run", start)
        original_require = cli_bridge._require_provider_start
        def require(guard):
            self.checks.append(guard)
            try:
                return original_require(guard)
            except cli_bridge.ProviderStartRefused as exc:
                self.refusals.append((exc, exc.args, str(exc), repr(exc)))
                raise
        monkeypatch.setattr(cli_bridge, "_require_provider_start", require)
        async def process(*a, **kw):
            self.providers.append(("process", a, kw))
            raise AssertionError("A refused provider process was started")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", process)

    def now(self):
        self.clock_tick += 1
        return (datetime(2026, 10, 16, 22, tzinfo=timezone.utc)
                + timedelta(milliseconds=self.clock_tick)).isoformat(timespec="milliseconds")

    async def query(self, *, prompt, options):
        index = len([p for p in self.providers if p[0] == "sdk"])
        self.providers.append(("sdk", prompt, copy.deepcopy(vars(options))))
        for item in self.plans[index]:
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                effect = item()
                if inspect.isawaitable(effect):
                    await effect
            else:
                yield item

    async def invoke(self, guard, *, book="autonomous", role="deep", arm=True,
                     log_run=True, candidates=None):
        return await self.cb._reason(
            "Synthetic local-run provenance test", model="synthetic-model",
            role=role, arm=arm, allowed_tools=[], add_dirs=[], mcp_servers={},
            cwd=str(self.root), book=book, log_run=log_run,
            _backend_override="cli", _subscription_slots=CANDIDATES if candidates is None else candidates,
            before_provider_start=guard,
        )

    def route(self, lane, *, book="autonomous", role="deep", log_run=True,
              location="attribute"):
        late = lane in {"later-candidate", "sdk-to-cli"}
        self.mp.setattr(self.cb, "_SDK", lane != "direct-cli")
        self.plans = [[RuntimeError(AUTH_FAILURE if lane == "later-candidate" else "ordinary synthetic SDK failure")]]
        calls = []
        def guard():
            calls.append(1)
            if len(calls) == (2 if late else 1):
                return invalid_verdict(location, RuntimeError("SYNTHETIC_PRIVATE_CLEANUP"))
            return None
        with pytest.raises(self.cb.ProviderStartRefused) as caught:
            asyncio.run(self.invoke(guard, book=book, role=role,
                                   arm=lane in {"initial-sdk", "later-candidate"}, log_run=log_run))
        assert len(calls) == (2 if late else 1)
        assert self.checks == [guard] * len(calls)
        assert not [p for p in self.providers if p[0] == "process"]
        assert len([p for p in self.providers if p[0] == "sdk"]) == int(late)
        assert len(self.classifications) == int(late)
        assert len(self.cooling) == int(lane == "later-candidate")
        assert self.sessions == []
        assert len(self.refusals) == 1
        original, args, text, representation = self.refusals[0]
        assert caught.value is original
        assert (caught.value.args, str(caught.value), repr(caught.value)) == (args, text, representation)
        assert str(caught.value) == FIXED_REFUSAL
        return caught.value


def bound_id(cb, error, book="autonomous", role="deep"):
    # Parent source has no recovery API. Returning unavailable there makes the
    # RED causal expectation about the missing identity, not a collection error.
    reader = getattr(cb, "provider_refusal_run_id", None)
    return reader(error, book=book, role=role) if reader else None


@pytest.mark.parametrize("lane", ["initial-sdk", "later-candidate", "sdk-to-cli", "direct-cli"])
@pytest.mark.parametrize("location", ["attribute", "call"])
def test_refusal_preserves_the_exact_created_run_without_control_change(monkeypatch, tmp_path, lane, location):
    h = RunBindingHarness(monkeypatch, tmp_path)
    error = h.route(lane, location=location)
    assert len(h.created) == 1
    run_id = h.created[0]
    assert h.rl.read_run(run_id)["run_id"] == run_id
    assert h.rl.read_run(run_id)["ts"] is not None
    assert bound_id(h.cb, error) == run_id
    assert bound_id(h.cb, error, book="hk") is None
    assert bound_id(h.cb, error, role="analyst") is None
    # Refusal does not acquire normal-completion bookkeeping merely to expose ID.
    assert h.rl.list_runs() == []


@pytest.mark.parametrize("failure", ["disabled", "start-failed", "malformed"])
def test_missing_run_creation_remains_unavailable(monkeypatch, tmp_path, failure):
    h = RunBindingHarness(monkeypatch, tmp_path)
    if failure == "start-failed":
        def fail(*a, **kw):
            raise OSError("synthetic run logger unavailable")
        monkeypatch.setattr(h.rl, "start_run", fail)
    elif failure == "malformed":
        monkeypatch.setattr(h.rl, "start_run", lambda *a, **kw: {"run_id": "foreign"})
        monkeypatch.setattr(h.rl, "log_step", lambda *a, **kw: None)
    error = h.route("initial-sdk", log_run=failure != "disabled")
    assert bound_id(h.cb, error) is None
    assert h.created == []


@pytest.mark.parametrize("lane", ["sdk", "cli", "codex"])
def test_low_level_and_codex_refusals_do_not_borrow_run_identity(monkeypatch, tmp_path, lane):
    from brain import codex_bridge
    h = RunBindingHarness(monkeypatch, tmp_path)
    def deny():
        return False
    with pytest.raises(h.cb.ProviderStartRefused) as caught:
        if lane == "sdk":
            asyncio.run(h.cb._via_sdk(
                "Synthetic", "synthetic-model", "deep", None, None, [], [], 1,
                str(tmp_path), "default", {}, None, False,
                run_id="supplied-is-not-owned", before_provider_start=deny,
            ))
        elif lane == "cli":
            asyncio.run(h.cb._via_subprocess(
                "Synthetic", "synthetic-model", "deep", None, None, [], [], 1,
                str(tmp_path), "default", {}, before_provider_start=deny,
            ))
        else:
            monkeypatch.setattr(codex_bridge, "codex_path", lambda: "/synthetic/codex")
            monkeypatch.setattr(codex_bridge, "available", lambda: True)
            monkeypatch.setattr(codex_bridge, "_subprocess_env", lambda: {})
            monkeypatch.setattr(codex_bridge, "_mcp_secret_bundle", lambda: (None, None))
            asyncio.run(codex_bridge.reason(
                "Synthetic", role="deep", arm=False, book="autonomous",
                allowed_tools=[], cwd=str(tmp_path), log_run=True, before_provider_start=deny,
            ))
    assert bound_id(h.cb, caught.value) is None
    assert h.created == [] and h.providers == []


@pytest.mark.parametrize("location", ["attribute", "call"])
def test_cancellation_identity_is_not_converted_to_bound_refusal(monkeypatch, tmp_path, location):
    h = RunBindingHarness(monkeypatch, tmp_path)
    cancel = asyncio.CancelledError("synthetic original cancellation")
    def guard():
        return invalid_verdict(location, cancel)
    with pytest.raises(asyncio.CancelledError) as caught:
        asyncio.run(h.invoke(guard))
    assert caught.value is cancel
    assert bound_id(h.cb, cancel) is None
    assert h.providers == h.classifications == h.cooling == h.sessions == []


def test_foreign_exception_and_subclass_attributes_are_never_trusted(monkeypatch, tmp_path):
    h = RunBindingHarness(monkeypatch, tmp_path)
    error = h.route("initial-sdk")
    assert bound_id(h.cb, error) == h.created[0]
    accesses = []
    class Foreign(RuntimeError):
        @property
        def run_id(self):
            accesses.append("foreign")
            raise AssertionError("Untrusted property read")
    class RefusalSubclass(h.cb.ProviderStartRefused):
        @property
        def run_id(self):
            accesses.append("subclass")
            raise AssertionError("Subclass property read")
    for other in (Foreign(FIXED_REFUSAL), RefusalSubclass(FIXED_REFUSAL)):
        other.__dict__.update(error.__dict__)
        assert bound_id(h.cb, other) is None
    assert accesses == []


def test_typed_binding_is_immutable_and_conflict_stays_unavailable(monkeypatch, tmp_path):
    from dataclasses import FrozenInstanceError
    h = RunBindingHarness(monkeypatch, tmp_path)
    error = h.route("initial-sdk")
    assert bound_id(h.cb, error) == h.created[0]
    binding = error.__dict__["_provider_refusal_run"]
    with pytest.raises(FrozenInstanceError):
        binding.run_id = "replacement"
    binder = h.cb._bind_provider_refusal_run
    binder(error, h.created[0], "autonomous", "deep")
    assert bound_id(h.cb, error) == h.created[0]
    binder(error, "another-invocation", "autonomous", "deep")
    assert bound_id(h.cb, error) is None
    binder(error, h.created[0], "autonomous", "deep")
    assert bound_id(h.cb, error) is None


@pytest.mark.parametrize("bad", [None, {}, "foreign-run", ("foreign-run", "autonomous", "deep")])
def test_malformed_preexisting_binding_is_not_replaced(monkeypatch, tmp_path, bad):
    h = RunBindingHarness(monkeypatch, tmp_path)
    error = h.cb.ProviderStartRefused(FIXED_REFUSAL)
    error.__dict__["_provider_refusal_run"] = bad
    async def refused(*a, **kw):
        raise error
    monkeypatch.setattr(h.cb, "_via_sdk", refused)
    with pytest.raises(h.cb.ProviderStartRefused) as caught:
        asyncio.run(h.invoke(lambda: None))
    assert caught.value is error
    assert bound_id(h.cb, error) is None


def test_interleaved_invocations_keep_their_own_run_and_book(monkeypatch, tmp_path):
    h = RunBindingHarness(monkeypatch, tmp_path)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def query(**kwargs):
            h.providers.append(("sdk",))
            entered.set()
            await release.wait()
            raise RuntimeError(AUTH_FAILURE)
            yield
        monkeypatch.setattr(h.cb, "_sdk_query", query)
        checks = []
        def first_guard():
            checks.append(1)
            return None if len(checks) == 1 else False
        first = asyncio.create_task(h.invoke(first_guard, book="autonomous"))
        await entered.wait()
        with pytest.raises(h.cb.ProviderStartRefused) as second:
            await h.invoke(lambda: False, book="hk")
        release.set()
        with pytest.raises(h.cb.ProviderStartRefused) as original:
            await first
        return original.value, second.value
    first, second = asyncio.run(scenario())
    assert len(h.created) == 2 and h.created[0] != h.created[1]
    assert bound_id(h.cb, first, book="autonomous") == h.created[0]
    assert bound_id(h.cb, second, book="hk") == h.created[1]
    assert bound_id(h.cb, first, book="hk") is None
    assert bound_id(h.cb, second, book="autonomous") is None
    assert len(h.providers) == 1 and len(h.cooling) == 1
