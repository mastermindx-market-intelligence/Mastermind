"""Offline collection/execution and a complete per-invocation pytest manifest."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from .offline_guard import OfflineGuard


_guard = None
_collected = []
_deselected = []
_reports = []


def pytest_addoption(parser):
    parser.addoption("--chaos-seed", action="append", default=[],
                     help="Replay an integer seed; repeat for several seeds.")


def pytest_configure(config):
    global _guard
    _collected.clear()
    _deselected.clear()
    _reports.clear()
    _guard = OfflineGuard()
    _guard.install()  # Before test-module imports; no disposable Git exception yet.


def pytest_unconfigure(config):
    global _guard
    if _guard is not None:
        _guard.close()
        _guard = None


def pytest_generate_tests(metafunc):
    if "chaos_seed" in metafunc.fixturenames:
        values = metafunc.config.getoption("--chaos-seed") or ["0", "1", "0x2410"]
        seeds = [int(value, 0) for value in values]
        metafunc.parametrize("chaos_seed", seeds, ids=[f"seed-{seed}" for seed in seeds])


def pytest_collection_finish(session):
    _collected.extend(item.nodeid for item in session.items)


def pytest_deselected(items):
    _deselected.extend(item.nodeid for item in items)


def pytest_runtest_logreport(report):
    _reports.append({"node_id": report.nodeid, "when": report.when, "outcome": report.outcome})


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("H24_EXECUTION_MANIFEST")
    if target:
        Path(target).write_text(json.dumps({
            "schema": "mastermind.h24_pytest_execution.v1",
            "invocation_id": os.environ["H24_INVOCATION_ID"],
            "collected": _collected, "deselected": _deselected, "reports": _reports,
            "pytest_exit_code": int(exitstatus),
        }, sort_keys=True) + "\n")


@pytest.fixture(autouse=True)
def offline_only(tmp_path):
    assert _guard is not None
    _guard.root = tmp_path
    try:
        yield
    finally:
        _guard.root = None
