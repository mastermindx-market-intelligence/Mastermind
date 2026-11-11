"""Finding 8 (R4b review) + the pairing-helper default: the pairing command
must be IMPOSSIBLE to run unless the T3 home's own runtime state names the
pinned dev port, and the helper takes its target as a required argument with
no fallback to the live app (3773).

On 2026-11-10 the old shape minted 14 pairing codes on the Chairman's own T3
app exactly because the CLI leg picked its server from T3CODE_HOME while the
HTTP legs used BASE (default 3773).  These tests pin the new law; no test
here ever runs the real CLI or touches any server.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_t3_live_proof_pairing_target.py
"""
import importlib.util
import json
import os
import sys
import urllib.error
from pathlib import Path

import pytest

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "integrations", "t3", "live_proof",
                   "t3_live_proof.py")
_spec = importlib.util.spec_from_file_location("t3lp_pairing", SRC)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


class _Reply:
    def __init__(self, payload: dict, status: int = 200):
        self._raw = json.dumps(payload).encode()
        self.headers = {"Content-Type": "application/json"}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def read(self):
        return self._raw


def _state(home: Path, *, port: int, pid: int, origin: str | None = None):
    """Write a home's server-runtime.json exactly in the server's shape."""
    userdata = home / "userdata"
    userdata.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "pid": pid, "port": port,
               "origin": origin or f"http://127.0.0.1:{port}",
               "startedAt": "2026-11-11T00:00:00Z", "serverVersion": "0.1.7"}
    (userdata / "server-runtime.json").write_text(json.dumps(payload) + "\n",
                                                  encoding="utf-8")


def _cli(monkeypatch, *, ok=True):
    """Capture the pairing CLI invocation; it must NEVER really run."""
    import subprocess as stdlib_subprocess
    calls: list[dict] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), "kwargs": kwargs})
        if not ok:
            class P:
                returncode = 1
                stdout = ""
                stderr = "refused"
            return P()

        class P:
            returncode = 0
            stdout = json.dumps({"token": "pairing-secret-not-a-test-value"})
            stderr = ""
        return P()

    monkeypatch.setattr(stdlib_subprocess, "run", fake_run)
    return calls


def _oauth(monkeypatch, base: str):
    """The register/decision/token HTTP legs, against `base` only."""
    urls: list[str] = []

    def fake_urlopen(req, timeout=None):
        urls.append(req.full_url)
        path = req.full_url[len(base):]
        if path.startswith("/oauth/mcp/register"):
            return _Reply({"client_id": "cid-1"}, status=201)
        if path.startswith("/oauth/mcp/decision"):
            return _Reply({"redirectTo": "http://localhost:51234/callback?code=gc"})
        if path.startswith("/oauth/mcp/token"):
            from urllib.parse import parse_qs
            body = parse_qs(req.data.decode())
            assert body["code"] == ["gc"]
            return _Reply({"access_token": "at-dev", "scope": "mcp"})
        raise AssertionError(f"unexpected url {req.full_url}")

    monkeypatch.setattr(harness.urllib.request, "urlopen", fake_urlopen)
    return urls


# ---------------------------------------------------------------------------
# no implicit live-app target
# ---------------------------------------------------------------------------

def test_no_3773_default_anywhere(monkeypatch):
    monkeypatch.delenv("T3_PROOF_BASE_URL", raising=False)
    fresh = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location("t3lp_pairing_fresh", SRC))
    fresh.__loader__.exec_module(fresh)
    assert fresh.BASE is None, "the live app (3773) must never be an implicit target"
    with pytest.raises(TypeError):
        fresh.obtain_mcp_access_token("/tmp/x.txt", "label")


def test_target_is_required_positional_compat_raises(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _state(home, port=3796, pid=os.getpid())
    calls = _cli(monkeypatch)
    # old call shape (the canaries' / the incident's shape) must fail loudly
    with pytest.raises(TypeError):
        harness.obtain_mcp_access_token(str(tmp_path / "tok.txt"), "label")
    assert calls == []


# ---------------------------------------------------------------------------
# the mint is refused unless the home's runtime state names the pinned port
# ---------------------------------------------------------------------------

def test_mint_refused_when_home_has_no_runtime_state(monkeypatch, tmp_path):
    calls = _cli(monkeypatch)
    home = tmp_path / "home"  # never started a server: no server-runtime.json
    with pytest.raises(RuntimeError, match="server-runtime"):
        harness.obtain_mcp_access_token(
            str(tmp_path / "tok.txt"), "label",
            base_url="http://127.0.0.1:3796", home_dir=str(home))
    assert calls == [], "the pairing CLI must never run for an unpinned home"


def test_mint_refused_when_state_names_a_foreign_port(monkeypatch, tmp_path):
    calls = _cli(monkeypatch)
    home = tmp_path / "home"
    # the home's own server runs on 3800, but the pinned base says 3796:
    # a stale/foreign home is exactly the 14-code incident's shape
    _state(home, port=3800, pid=os.getpid())
    with pytest.raises(RuntimeError, match="names port 3800"):
        harness.obtain_mcp_access_token(
            str(tmp_path / "tok.txt"), "label",
            base_url="http://127.0.0.1:3796", home_dir=str(home))
    assert calls == []


def test_mint_refused_when_state_origin_disagrees(monkeypatch, tmp_path):
    calls = _cli(monkeypatch)
    home = tmp_path / "home"
    _state(home, port=3796, pid=os.getpid(),
           origin="http://127.0.0.1:3773")  # a lie in the state file
    with pytest.raises(RuntimeError, match="origin"):
        harness.obtain_mcp_access_token(
            str(tmp_path / "tok.txt"), "label",
            base_url="http://127.0.0.1:3796", home_dir=str(home))
    assert calls == []


def test_mint_refused_when_state_pid_is_dead(monkeypatch, tmp_path):
    calls = _cli(monkeypatch)
    home = tmp_path / "home"
    _state(home, port=3796, pid=999999999)  # not a live process
    with pytest.raises(RuntimeError, match="not alive"):
        harness.obtain_mcp_access_token(
            str(tmp_path / "tok.txt"), "label",
            base_url="http://127.0.0.1:3796", home_dir=str(home))
    assert calls == [], "a stale state file names no live server; no mint"


def test_mint_refused_for_non_dev_base(monkeypatch, tmp_path):
    calls = _cli(monkeypatch)
    home = tmp_path / "home"
    _state(home, port=3773, pid=os.getpid())  # state names the LIVE app port
    with pytest.raises(RuntimeError, match="3773"):
        harness.obtain_mcp_access_token(
            str(tmp_path / "tok.txt"), "label",
            base_url="http://127.0.0.1:3773", home_dir=str(home))
    assert calls == [], "the live app is never a mint target for this helper"


# ---------------------------------------------------------------------------
# the pinned happy path: CLI env pinned, HTTP legs on the named base only
# ---------------------------------------------------------------------------

def test_mint_pins_cli_env_and_http_base_to_the_pinned_server(
        monkeypatch, tmp_path):
    base = "http://127.0.0.1:3796"
    home = tmp_path / "home"
    _state(home, port=3796, pid=os.getpid())
    calls = _cli(monkeypatch)
    urls = _oauth(monkeypatch, base)
    token_path = tmp_path / "worker-token.txt"

    token, reg = harness.obtain_mcp_access_token(
        str(token_path), "t4c-door-worker",
        base_url=base, home_dir=str(home))

    assert token == "at-dev"
    assert len(calls) == 1, "exactly ONE pairing command"
    argv = calls[0]["argv"]
    assert argv[1:4] == ["auth", "pairing", "create"]
    env = calls[0]["kwargs"]["env"]
    assert env["T3CODE_HOME"] == str(home)
    assert env["T3CODE_PORT"] == "3796"
    # every HTTP leg went to the PINNED base, never to 3773
    assert urls and all(u.startswith(base + "/oauth/mcp/") for u in urls), urls
    # the token is a 0600 file
    assert token_path.read_text().strip() == "at-dev"
    assert (token_path.stat().st_mode & 0o777) == 0o600


def test_cached_token_never_mints(monkeypatch, tmp_path):
    calls = _cli(monkeypatch)
    token_path = tmp_path / "worker-token.txt"
    token_path.write_text("cached-token", encoding="utf-8")
    home = tmp_path / "home"  # no state at all: reuse needs no server
    token, _reg = harness.obtain_mcp_access_token(
        str(token_path), "label",
        base_url="http://127.0.0.1:3796", home_dir=str(home))
    assert token == "cached-token"
    assert calls == []


# ---------------------------------------------------------------------------
# the door's executor mints ONLY through the pinned target (finding 8)
# ---------------------------------------------------------------------------

DOOR_SRC = os.path.join(HERE, "..", "tools", "mmos_coding_job", "door.py")
_dspec = importlib.util.spec_from_file_location("t4c_door_pairing", DOOR_SRC)
door_mod = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(door_mod)


def test_door_executor_pins_base_and_home_and_survives_refusal(
        monkeypatch, tmp_path):
    import threading

    door = door_mod.CodingJobDoor(door_mod.DoorConfig({
        "scratch_root": str(tmp_path),
        "paperclip_base_url": "http://127.0.0.1:3190",
        "paperclip_company_id": "c",
        "t3": {
            "proof_base_url": "http://127.0.0.1:3796",
            "home_dir": str(tmp_path / "t3home"),  # no runtime state at all
            "port": 3796,
            "token_path": str(tmp_path / "worker-token.txt"),
            "token_label": "t4c-door-worker",
            "project_id": "p", "model_selection": "{}"},
    }))
    mint_calls: list[dict] = []

    def fake_mint(token_path, label, *, base_url, home_dir):
        mint_calls.append({"base_url": base_url, "home_dir": home_dir})
        # the real guard refuses: the pinned home has no server-runtime.json
        harness._pinned_pairing_target(base_url, home_dir)
        raise AssertionError("the guard must refuse before this point")

    import integrations.t3.live_proof.t3_live_proof as real_proof
    monkeypatch.setattr(real_proof, "obtain_mcp_access_token", fake_mint)

    class _R:  # the readiness probe passes: something answers on 3796
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def read(self):
            return b"{}"

    monkeypatch.setattr(door_mod.urllib.request, "urlopen",
                        lambda *a, **k: _R())

    def run_executor():
        # one wait() on the stopping event ends both loops after the first
        # mint attempt, so the thread terminates deterministically
        def wait_once(timeout=None):
            door._stopping.set()
            return True
        door._stopping.wait = wait_once
        door._executor_main()

    thread = threading.Thread(target=run_executor, daemon=True)
    thread.start()
    thread.join(timeout=10.0)
    assert not thread.is_alive()
    # restore the T3 env the executor applied (stop() was not called)
    backup = getattr(door, "_t3_env_backup", None)
    if backup is not None:
        door._restore_t3_env(backup)
    # the executor TRIED the mint exactly once, with the pinned target, and
    # the guard refused it — no crash, no live-app fallback
    assert len(mint_calls) == 1
    assert mint_calls[0]["base_url"] == "http://127.0.0.1:3796"
    assert mint_calls[0]["home_dir"] == str(tmp_path / "t3home")
