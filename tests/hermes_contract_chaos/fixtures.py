"""Deterministic fault drivers around the incumbent public contracts.

Only clocks, transports and disposable filesystem/connection boundaries are
injected. Runtime/claim/event/wake/publication owners remain the real code.
No fixture is evidence of native Hermes startup, host security or admission.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import tempfile

import pytest


BASE_SHA = "b54cb10e4abdd3766c62d4088f6a576ecfe80437"
SECRET_SENTINEL = "h24-offline-secret-sentinel-never-a-real-key"
DEFAULT_SEEDS = (0, 1, 0x2410)


@dataclass
class ManualClock:
    """A controlled clock, including explicit wall rollback, with no sleeps."""
    wall: float = 1_800_000_000.0
    ticks: float = 0.0

    def monotonic(self):
        return self.ticks

    def now(self):
        return datetime.fromtimestamp(self.wall, tz=timezone.utc).isoformat()

    def advance(self, seconds):
        assert seconds >= 0
        self.ticks += seconds
        self.wall += seconds

    def rewind_wall(self, seconds):
        assert seconds >= 0
        self.wall -= seconds


class Schedule:
    """Seeded, explicit release order. Timeout is a deadlock watchdog only."""
    MAX_PENDING = 64

    def __init__(self, seed):
        self.seed = seed
        self.random = random.Random(seed)
        self.arrivals = {}
        self.releases = {}
        self.parked = set()
        self.trace = []

    def _slot(self, name):
        if name not in self.arrivals:
            assert len(self.arrivals) < self.MAX_PENDING
            self.arrivals[name] = asyncio.Event()
            self.releases[name] = asyncio.Event()
        return self.arrivals[name], self.releases[name]

    def order(self, names):
        names = list(names)
        self.random.shuffle(names)
        return names

    async def park(self, name):
        assert name not in self.parked, (self.seed, name, self.trace)
        self.parked.add(name)
        arrival, release = self._slot(name)
        self.trace.append(("park", name))
        arrival.set()
        await asyncio.wait_for(release.wait(), 5)
        self.trace.append(("resume", name))

    async def entered(self, name):
        arrival, _ = self._slot(name)
        await asyncio.wait_for(arrival.wait(), 5)

    def release(self, name):
        assert name in self.releases, (self.seed, name, self.trace)
        self.trace.append(("release", name))
        self.releases[name].set()


class FaultScript:
    """One-shot boundary faults; exhausting a script is an assertion failure."""
    def __init__(self, *steps, clock=None):
        self.steps = list(steps)
        self.calls = []
        self.clock = clock or ManualClock()

    def take(self, label):
        assert self.steps, f"unexpected extra effect at {label}"
        self.calls.append(label)
        self.clock.advance(0.025)
        value = self.steps.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value() if callable(value) else value

    def post_json(self, url, headers, body, timeout):
        # Do not retain Authorization, prompts, URLs or secret-bearing errors.
        return self.take(body["model"])


def counts(runtime):
    """Read actual durable cardinalities, not fixture-side counters."""
    with runtime.store.read() as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("jobs", "attempts", "events"))


def event_digest(runtime):
    with runtime.store.read() as connection:
        rows = [tuple(row) for row in connection.execute("SELECT * FROM events ORDER BY event_id")]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


@asynccontextmanager
async def selected_case(tmp_path, *, supervisor_factory=None):
    """Real Control/Runtime owners with a deliberately in-process transport.

    No listener is bound. Socket/authentication/host startup is not qualified.
    The incumbent fixture still constructs and validates its real source plan.
    """
    from tests import test_hermes_selected_child_dispatch as incumbent
    from tests.test_hermes_selected_child_dispatch import (
        _admit_work_child, _install, _selected_child_service,
    )
    from control_plane.executive_service import ExecutiveControlService, CONTROL_PROTOCOL_VERSION
    from integrations.hermes_delegate.executive import (
        clear_selected_child_composition, selected_child_composition,
    )
    kwargs = {} if supervisor_factory is None else {"supervisor_factory": supervisor_factory}

    async def no_listener(self, *, start_serving=True):
        return None

    async def inprocess_request(service, command, args=None):
        result = await service._dispatch_request(dict(version=CONTROL_PROTOCOL_VERSION,
                                                      command=command, args=args or {}))
        return {"ok": True, "result": result}

    with tempfile.TemporaryDirectory(prefix="h24-", dir="/tmp") as sockets, pytest.MonkeyPatch.context() as patch:
        patch.setattr(ExecutiveControlService, "_bind_operator_server", no_listener)
        patch.setattr(incumbent, "_request", inprocess_request)
        async with _selected_child_service(tmp_path, Path(sockets), name="h24-chaos", **kwargs) as values:
            service, supervisor, root, received, finish = values
            work = _admit_work_child(service, root)
            command = _install(service, service.runtime, work)
            try:
                yield service, supervisor, work, command, selected_child_composition(), received, finish
            finally:
                finish.set()
                try:
                    tasks = tuple(service._dispatch_tasks.values())
                    if tasks:
                        await asyncio.wait_for(asyncio.gather(*tasks), 5)
                finally:
                    clear_selected_child_composition()


@pytest.fixture
def native_case(tmp_path, monkeypatch):
    from tests.test_executive_fabric_composition import root_stats
    from tests.test_hermes_session_runtime import native
    root_stats.__wrapped__(monkeypatch)
    return native.__wrapped__(tmp_path, None, monkeypatch)


@pytest.fixture
def publication_case(tmp_path, monkeypatch):
    from tests.test_dialogue_wake_canary_control import installed
    return installed.__wrapped__(monkeypatch, tmp_path)
