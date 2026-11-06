"""Keep this lane independent of the portfolio-wide test environment."""
from __future__ import annotations

import socket
import subprocess
import urllib.request
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--chaos-seed", action="append", default=[],
        help="Replay an integer seed (decimal or 0x hex); repeat for several seeds.",
    )


def pytest_generate_tests(metafunc):
    if "chaos_seed" in metafunc.fixturenames:
        values = metafunc.config.getoption("--chaos-seed") or ["0", "1", "0x2410"]
        seeds = [int(value, 0) for value in values]
        metafunc.parametrize("chaos_seed", seeds, ids=[f"seed-{seed}" for seed in seeds])


@pytest.fixture(autouse=True)
def offline_only(monkeypatch, tmp_path):
    """Fail on external network/host execution; allow disposable Git fixtures."""
    original_connect = socket.socket.connect
    original_popen = subprocess.Popen

    def connect(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            pytest.fail("H24-10 attempted a network connection")
        return original_connect(sock, address)

    def forbidden(*args, **kwargs):
        pytest.fail("H24-10 attempted external network or process execution")

    def fixture_git(args, *positional, **kwargs):
        # The incumbent plan fixture creates a disposable Git repository.
        # It may not use a provider binary, shell, remote or the working tree.
        if not isinstance(args, (list, tuple)) or Path(args[0]).name != "git" or kwargs.get("shell"):
            return forbidden()
        if "-C" in args:
            target = Path(args[args.index("-C") + 1]).resolve()
            verb = args[args.index("-C") + 2]
        elif len(args) > 2 and args[1] in {"init", "clone"}:
            target, verb = Path(args[-1]).resolve(), args[1]
            if verb == "clone" and not Path(args[-2]).resolve().is_relative_to(tmp_path.resolve()):
                return forbidden()
        else:
            target, verb = Path(kwargs.get("cwd", ".")).resolve(), args[1]
        allowed = {"init", "config", "add", "commit", "rev-parse", "status", "show", "ls-files",
                   "diff", "log", "ls-tree", "cat-file", "rev-list", "check-ref-format",
                   "clone", "pack-objects", "unpack-objects", "index-pack", "for-each-ref",
                   "update-ref", "checkout", "switch", "symbolic-ref", "merge-base", "remote"}
        if not target.is_relative_to(tmp_path.resolve()) or verb not in allowed:
            return forbidden()
        return original_popen(args, *positional, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", fixture_git)
