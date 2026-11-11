"""MMOS lane T2 — setup_teammate file-writing rules."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools",
                                "mmos_teammate"))
import setup_teammate as st  # noqa: E402


def make_home(tmp_path):
    home = tmp_path / "home"
    (home / "userdata").mkdir(parents=True)
    settings_path = home / "userdata" / "settings.json"
    settings_path.write_text(json.dumps({"providerInstances": {
        "capacity_fabric": {"driver": "claudeAgent",
                            "config": {"customModels": {}}}}}))
    os.chmod(settings_path, 0o644)
    charter = tmp_path / "charter.md"
    charter.write_text("# charter\n")
    spec = {"name": "Assurance",
            "t3": {"dev_home": str(home), "dev_root": str(tmp_path / "root"),
                   "t3_bin": "/x/t3", "home_path": str(tmp_path / "th"),
                   "charter_path": str(charter), "instance_id": "assurance"}}
    return spec, settings_path


def test_settings_write_is_atomic_private_and_never_partial(tmp_path,
                                                            monkeypatch):
    # R2a finding 11: the dev server watches settings.json and reloads about
    # 100ms after a change, so the write must be one rename from a staged
    # file that is 0600 from creation — never an in-place truncate. A
    # mid-write failure leaves the original bytes untouched and no staged
    # leftovers; the successful path lands valid JSON at mode 0600.
    spec, settings_path = make_home(tmp_path)
    before = settings_path.read_bytes()
    real_dump = json.dump  # captured before any patching

    def exploding_dump(obj, fh, *args, **kwargs):
        fh.write("{ partial")  # the write dies halfway
        raise RuntimeError("disk full")

    monkeypatch.setattr(st.json, "dump", exploding_dump)
    with pytest.raises(RuntimeError):
        st.ensure_t3_instance(spec)
    assert settings_path.read_bytes() == before  # untouched, not truncated
    assert not [p for p in os.listdir(settings_path.parent)
                if ".new-" in p]  # the failed staging is cleaned up

    monkeypatch.setattr(st.json, "dump", real_dump)
    st.ensure_t3_instance(spec)
    data = json.loads(settings_path.read_text())
    instance = data["providerInstances"]["assurance"]
    assert instance["config"]["homePath"] == st.expand(str(tmp_path / "th"))
    assert "--append-system-prompt-file" in instance["config"]["launchArgs"]
    assert (os.stat(settings_path).st_mode & 0o777) == 0o600
    assert not [p for p in os.listdir(settings_path.parent) if ".new-" in p]


# --- the dev-instance client refuses what it must not transport -------------

def _loopback_server(status, body=b"", location=None):
    """A throwaway loopback origin that answers every request alike."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("content-type", "application/json")
            self.end_headers()
            if body:
                self.wfile.write(body)

        do_GET = do_POST = do_PATCH = _answer

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_http_dies_on_a_redirect_instead_of_following_it():
    # Every call this client makes carries the dev actor's local_trusted
    # header. A 3xx answer would carry that header to whatever origin the
    # Location names — the client must die on the spot, not follow.
    srv = _loopback_server(302, b"{}", location="http://127.0.0.1:9/leak")
    try:
        http = st.Http(f"http://127.0.0.1:{srv.server_port}")
        with pytest.raises(SystemExit):
            http.get("/api/agents/ag-1")
    finally:
        srv.shutdown()


def test_http_error_message_prints_status_only_never_the_body(capsys):
    # An error body can quote secrets, tokens or a person's text, and the
    # failure line goes to a terminal someone reads. The law for refused
    # HTTP: the type and the status, never bodies.
    srv = _loopback_server(400, b'{"error":{"message":"SECRET-VALUE"}}')
    try:
        http = st.Http(f"http://127.0.0.1:{srv.server_port}")
        with pytest.raises(SystemExit):
            http.get("/api/issues/is-1")
    finally:
        srv.shutdown()
    err = capsys.readouterr().err
    assert "400" in err
    assert "SECRET-VALUE" not in err


def test_an_unsignalable_pid_means_the_server_is_running(tmp_path,
                                                          monkeypatch):
    # kill(pid, 0) raising PermissionError says the process EXISTS under
    # another user. Swallowing that as "not running" edits settings.json
    # while a live dev server watches the file and reloads it.
    spec, settings_path = make_home(tmp_path)
    run_dir = os.path.join(st.expand(spec["t3"]["dev_root"]), "run")
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "server.pid"), "w") as fh:
        fh.write("4242")

    def eperm(pid, sig):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "kill", eperm)
    with pytest.raises(SystemExit):
        st.ensure_t3_instance(spec)


def test_rotate_refuses_while_the_agent_still_holds_open_work(tmp_path,
                                                              monkeypatch):
    # cmd_rotate minted a fresh primary thread and rewrote the binding
    # without looking at the board: issues still assigned to this agent
    # would keep waking a carrier whose thread home just moved under it.
    # The mint is the irreversible step — it must not start while the agent
    # still holds open work.
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    result = {"agentId": "ag-1",
              "binding": {"environmentId": "e", "projectId": "p",
                          "providerInstanceId": "i",
                          "primaryThreadId": "th-1"}}
    (agent_dir / "setup_result.json").write_text(json.dumps(result))
    spec = {"paperclip_base": "http://127.0.0.1:3100", "company_id": "co-1",
            "agent_dir": str(agent_dir), "t3": {}}

    class BoardWithOpenWork:
        def __init__(self, base):
            self.gets = []

        def get(self, path):
            self.gets.append(path)
            if "status=todo" in path:
                return [{"id": "is-9", "status": "todo"}]
            return []

    minted = []
    monkeypatch.setattr(st, "Http", BoardWithOpenWork)
    monkeypatch.setattr(st, "start_primary_thread",
                        lambda spec_: minted.append(spec_) or {"threadId": "th-2"})
    monkeypatch.setattr(st, "write_binding", lambda *a, **k: {})
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(SystemExit):
        st.cmd_rotate(str(spec_path), "new home", None)
    assert not minted  # the thread was never minted
