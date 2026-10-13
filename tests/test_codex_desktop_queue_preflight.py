"""Read-only desktop/daemon queue-topology falsifiers; no provider calls."""
from __future__ import annotations

from scripts.ohf import codex_desktop_queue_preflight as q


def _rows():
    return [
        q.ProcessInfo(101, 1, 501, "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"),
        q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server --listen stdio://"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix:///tmp/secure.sock"),
    ]


def _evaluate(rows=None, *, socket=True, listener=(201,), inodes=None, uid=501):
    if rows is None:
        rows = _rows()
    if inodes is None:
        inodes = {102: {(4, 15), (4, 19)}, 201: {(4, 15)}}
    return q.reduce_topology(
        rows, owner_uid=uid, socket_private=socket,
        socket_owner_pids=frozenset(listener), state_db_inodes=inodes,
        app_version="26.930.21537",
    )


def test_candidate_never_claims_canary_or_target_auth():
    result = _evaluate()
    assert result["schema"] == "mastermind.codex_desktop_queue_preflight.v1"
    assert result["status"] == "TOPOLOGY_CANDIDATE_ONLY"
    assert result["proof"] == "READ_ONLY_METADATA"
    assert result["provider_effect"] == "NONE"
    assert result["eligible_thread_proven"] is False
    assert result["queue_api_production_supported"] is False
    assert result["experimental_api_enabled_by_preflight"] is False
    assert result["native_delivery_proven"] is False
    assert result["shared_state_database_observed"] is True
    assert result["managed_socket_owner_count"] == 1
    assert "process_pids" not in result
    assert "paths" not in result


def test_missing_desktop_owner_is_unqualified():
    result = _evaluate(rows=_rows()[1:])
    assert result["status"] == "UNQUALIFIED"
    assert "DESKTOP_APP_SERVER_NOT_OBSERVED" in result["reasons"]


def test_no_shared_state_is_unqualified_not_new_writer_permission():
    result = _evaluate(inodes={102: {(4, 15)}, 201: {(4, 16)}})
    assert result["status"] == "UNQUALIFIED"
    assert "STATE_DATABASE_OVERLAP_NOT_OBSERVED" in result["reasons"]


def test_cross_uid_server_is_rejected():
    rows = [q.ProcessInfo(r.pid, r.ppid, 777 if r.pid == 201 else r.uid, r.command) for r in _rows()]
    result = _evaluate(rows=rows)
    assert result["status"] == "UNQUALIFIED"
    assert "MANAGED_SOCKET_OWNER_NOT_VERIFIED" in result["reasons"]


def test_no_live_managed_socket_owner_is_rejected():
    result = _evaluate(listener=())
    assert "MANAGED_SOCKET_OWNER_NOT_VERIFIED" in result["reasons"]


def test_two_socket_owners_are_ambiguous():
    rows = _rows() + [q.ProcessInfo(202, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix://")]
    result = _evaluate(rows=rows, listener=(201, 202))
    assert result["status"] == "UNQUALIFIED"
    assert "MULTIPLE_MANAGED_SOCKET_OWNERS" in result["reasons"]


def test_unsafe_socket_refuses_even_if_all_processes_are_visible():
    result = _evaluate(socket=False)
    assert result["status"] == "UNQUALIFIED"
    assert "PRIVATE_SOCKET_NOT_VERIFIED" in result["reasons"]


def test_unrelated_app_command_does_not_impersonate_desktop_ancestor():
    rows = [
        q.ProcessInfo(101, 1, 501, "/usr/bin/python worker.py --title ChatGPT"),
        q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix://"),
    ]
    assert _evaluate(rows=rows)["status"] == "UNQUALIFIED"


def test_parent_cycle_never_establishes_desktop_ownership():
    rows = [
        q.ProcessInfo(101, 102, 501, "fake"),
        q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix://"),
    ]
    assert _evaluate(rows=rows)["status"] == "UNQUALIFIED"


def test_ps_parser_ignores_broken_lines_and_keeps_commands_private():
    value = q.parse_ps_rows(
        " 101 1 501 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n"
        " 102 101 501 /opt/homebrew/bin/codex app-server\n"
        " no-identifiers /private/path?secret=abc\n"
        " 103 -1 501 cannot-pass\n"
    )
    assert len(value) == 2
    assert value[0].pid == 101
    assert value[1].command.endswith("app-server")
    assert "secret" not in str(q.reduce_topology(
        value, owner_uid=501, socket_private=False,
        socket_owner_pids=frozenset(), state_db_inodes={},
        app_version=None))


def test_duplicate_process_id_is_refused_before_ancestry_inference():
    rows = _rows() + [q.ProcessInfo(102, 1, 501, "/Applications/Codex.app/Contents/MacOS/Codex")]
    out = _evaluate(rows=rows)
    assert out["status"] == "UNQUALIFIED"
    assert "DUPLICATE_PROCESS_ID" in out["reasons"]


def test_not_running_as_same_owner_refuses():
    out = _evaluate(uid=777)
    assert out["status"] == "UNQUALIFIED"
    assert "DESKTOP_APP_SERVER_NOT_OBSERVED" in out["reasons"]


def test_unknown_shared_file_handles_is_not_treated_as_no_shared_storage():
    result = _evaluate(inodes={102: None, 201: {(4, 15)}})
    assert result["status"] == "UNQUALIFIED"
    assert "STATE_DATABASE_OBSERVATION_INCOMPLETE" in result["reasons"]


def test_no_socket_or_process_path_escapes_in_result():
    rows = [
        q.ProcessInfo(101, 1, 501, "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT --password=SECRET_CANARY"),
        q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server --token SECRET_CANARY"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix:///Users/private/SECRET_CANARY"),
    ]
    out = _evaluate(rows=rows)
    assert "SECRET_CANARY" not in str(out)


def test_json_output_is_bounded_and_no_runtime_claim_is_upgraded():
    import json
    out = _evaluate()
    encoded = json.dumps(out, sort_keys=True).encode()
    assert len(encoded) < 2048
    assert out["authorization_proven"] is False
    assert out["turn_completion_proven"] is False
    assert out["original_parent_return_proven"] is False


def test_codex_helpers_descended_from_gui_are_not_mistaken_for_owner():
    rows = _rows() + [
        q.ProcessInfo(103, 101, 501, "/opt/homebrew/bin/node code-mode-host"),
        q.ProcessInfo(104, 103, 501, "/opt/homebrew/bin/codex app-server --listen stdio://"),
    ]
    out = _evaluate(rows=rows)
    assert out["status"] == "TOPOLOGY_CANDIDATE_ONLY"
    assert out["desktop_app_server_count"] == 1


def test_indirect_only_server_is_not_safe_current_writer_proof():
    rows = [
        q.ProcessInfo(101, 1, 501, "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"),
        q.ProcessInfo(103, 101, 501, "/opt/homebrew/bin/node helper"),
        q.ProcessInfo(104, 103, 501, "/opt/homebrew/bin/codex app-server"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix://"),
    ]
    out = _evaluate(rows=rows)
    assert out["status"] == "UNQUALIFIED"
    assert "DESKTOP_APP_SERVER_NOT_OBSERVED" in out["reasons"]


def test_fake_gui_executable_in_command_argument_is_not_owner():
    rows = [
        q.ProcessInfo(101, 1, 501, "/usr/bin/python --log=/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"),
        q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix://"),
    ]
    assert "DESKTOP_APP_SERVER_NOT_OBSERVED" in _evaluate(rows=rows)["reasons"]


def test_missing_version_never_claims_version_qualified_topology():
    rows = _rows()
    out = q.reduce_topology(
        rows, owner_uid=501, socket_private=True, socket_owner_pids={201},
        state_db_inodes={102: {(4, 15)}, 201: {(4, 15)}},
        app_version=None,
    )
    assert out["status"] == "UNQUALIFIED"
    assert "DESKTOP_VERSION_NOT_OBSERVED" in out["reasons"]


def test_private_symlink_to_owned_unix_socket_is_observed_without_connecting(tmp_path):
    import os
    import socket
    endpoint = tmp_path / "target.sock"
    symlink = tmp_path / "control.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as handle:
        handle.bind(str(endpoint))
        os.chmod(endpoint, 0o600)
        symlink.symlink_to(endpoint)
        good, resolved = q._socket_metadata(symlink)
        assert good is True and resolved == str(endpoint)
        os.chmod(endpoint, 0o666)
        assert q._socket_metadata(symlink) == (False, None)


def test_stale_symlink_does_not_establish_socket_readiness(tmp_path):
    link = tmp_path / "control.sock"
    link.symlink_to(tmp_path / "missing.sock")
    assert q._socket_metadata(link) == (False, None)


def test_read_only_collector_never_returns_untrusted_process_paths(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(q.os, "uname", lambda: SimpleNamespace(sysname="Unsupported"))
    text = str(q.collect_local())
    assert "UNSUPPORTED_OS" in text
    assert "NO_SUCH_SECRET" not in text


def test_multiple_direct_desktop_engines_cannot_claim_one_writer():
    rows = _rows() + [
        q.ProcessInfo(105, 101, 501, "/opt/homebrew/bin/codex app-server --listen stdio://"),
    ]
    out = _evaluate(rows=rows, inodes={
        102: {(4, 15)}, 105: {(4, 15)}, 201: {(4, 15)},
    })
    assert out["status"] == "UNQUALIFIED"
    assert "MULTIPLE_DESKTOP_APP_SERVERS" in out["reasons"]


def test_app_version_is_selected_from_actual_desktop_parent(tmp_path):
    import plistlib
    app = tmp_path / "Codex.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    with (app / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleShortVersionString": "1.3.7"}, stream)
    parent = q.ProcessInfo(101, 1, 501, str(app / "Contents" / "MacOS" / "Codex"))
    worker = q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server")
    assert q._app_version([worker], {101: parent, 102: worker}) == "1.3.7"


def test_other_installed_desktop_does_not_substitute_missing_selected_version(tmp_path):
    app = tmp_path / "Codex.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    parent = q.ProcessInfo(101, 1, 501, str(app / "Contents" / "MacOS" / "Codex"))
    worker = q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server")
    assert q._app_version([worker], {101: parent, 102: worker}) is None


def test_process_output_is_enforced_during_read_and_child_is_reaped(monkeypatch):
    """Oversized metadata is refused immediately; a runaway child cannot linger."""
    import subprocess
    import sys
    import time

    spawned = []
    actual_popen = q.subprocess.Popen

    def tracked(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        spawned.append(child)
        return child

    monkeypatch.setattr(q.subprocess, "Popen", tracked)
    started = time.monotonic()
    result = q._run_fixed(
        [sys.executable, "-c",
         "import sys,time;sys.stdout.buffer.write(b'x'*524288);"
         "sys.stdout.flush();time.sleep(8)"],
        byte_limit=1024,
    )
    duration = time.monotonic() - started
    assert result is None
    assert duration < 3.0
    assert len(spawned) == 1
    assert spawned[0].poll() is not None


def test_process_deadline_reaps_quiet_child(monkeypatch):
    import subprocess
    import sys
    import time

    spawned = []
    actual = q.subprocess.Popen
    def tracked(*args, **kwargs):
        child = actual(*args, **kwargs)
        spawned.append(child)
        return child

    monkeypatch.setattr(q.subprocess, "Popen", tracked)
    monkeypatch.setattr(q, "_RUN_TIMEOUT_SECONDS", 0.25, raising=False)
    start = time.monotonic()
    assert q._run_fixed(
        [sys.executable, "-c", "import time;time.sleep(8)"],
        byte_limit=1024,
    ) is None
    assert time.monotonic() - start < 2.0
    assert len(spawned) == 1 and spawned[0].poll() is not None


def test_bounded_subprocess_good_result_and_nonzero_exit():
    import sys
    assert q._run_fixed(
        [sys.executable, "-c", "print('alpha')"], byte_limit=32
    ) == "alpha\n"
    assert q._run_fixed(
        [sys.executable, "-c", "import sys;print('beta');sys.exit(5)"], byte_limit=32
    ) is None


def test_python_argv_cannot_impersonate_codex_app_server():
    rows = [
        q.ProcessInfo(101, 1, 501, "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"),
        q.ProcessInfo(102, 101, 501, "/usr/bin/python /tmp/codex app-server --listen stdio://"),
        q.ProcessInfo(201, 1, 501, "/opt/homebrew/bin/codex app-server --listen unix:///tmp/s.sock"),
    ]
    out = _evaluate(rows=rows)
    assert out["status"] == "UNQUALIFIED"
    assert "DESKTOP_APP_SERVER_NOT_OBSERVED" in out["reasons"]


def test_unrelated_app_cannot_impersonate_managed_unix_listener():
    rows = [
        q.ProcessInfo(101, 1, 501, "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"),
        q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server --listen stdio://"),
        q.ProcessInfo(201, 1, 501, "/usr/bin/python /tmp/codex app-server --listen unix:///tmp/s.sock"),
    ]
    out = _evaluate(rows=rows)
    assert out["status"] == "UNQUALIFIED"
    assert "MANAGED_SOCKET_OWNER_NOT_VERIFIED" in out["reasons"]


def test_codex_executable_and_both_unix_argument_spellings():
    assert q._app_server("/opt/homebrew/bin/codex app-server --listen stdio://")
    assert q._managed_unix("/opt/homebrew/bin/codex app-server --listen unix:///tmp/x")
    assert q._managed_unix("codex app-server --listen=unix:///tmp/x")
    assert not q._managed_unix("/opt/homebrew/bin/codex app-server --listen stdio://")


def test_real_codex_command_with_pre_subcommand_flags_is_eligible():
    assert q._app_server("/opt/homebrew/bin/codex --config proto=1 --feature=f2 app-server --listen stdio://")
    assert q._managed_unix("/opt/homebrew/bin/codex --config proto=1 app-server --listen unix:///tmp/server.sock")
    assert not q._app_server("/usr/bin/python --config proto=1 codex app-server --listen unix:///tmp/server.sock")


def test_open_descriptor_inode_wins_after_database_path_replacement(tmp_path):
    """Review P2: pathname reuse must not conflate two open SQLite generations."""
    import os

    current = tmp_path / "state.sqlite"
    previous = tmp_path / "previous.sqlite"
    current.write_bytes(b"old generation")
    with current.open("rb") as held:
        old = os.fstat(held.fileno())
        current.rename(previous)
        current.write_bytes(b"new generation")
        new = current.stat()
        assert (old.st_dev, old.st_ino) != (new.st_dev, new.st_ino)
        wire = (
            f"p123\nf9\ntREG\nD{old.st_dev:#x}\ni{old.st_ino}\nn{current}\n"
        )
        records = q._parse_lsof_records(wire)
        assert q._state_db_ids(records) == {(old.st_dev, old.st_ino)}
        assert (new.st_dev, new.st_ino) not in q._state_db_ids(records)


def test_lsof_records_are_descriptor_scoped_and_reject_malformed_fields():
    good = (
        "p123\nf3\ntREG\nD0x1000023\ni42\nn/tmp/state.sqlite\n"
        "f4\ntREG\nD0x1000023\ni47\nn/tmp/state.sqlite\n"
        "f5\ntunix\nn/tmp/control.sock\n"
    )
    records = q._parse_lsof_records(good)
    assert q._state_db_ids(records) == {(0x1000023, 42), (0x1000023, 47)}
    assert [r.name for r in records if r.name.endswith(".sock")] == [
        "/tmp/control.sock"
    ]
    for bad in (
        "f3\ntREG\nD0x1000023\ni42\ni43\nn/tmp/state.sqlite\n",
        "f3\ntREG\nD0xGHI\ni42\nn/tmp/state.sqlite\n",
        "f3\ntREG\nD0x1000023\ni0\nn/tmp/state.sqlite\n",
        "f3\ntREG\nD0x1000023\ni42\nn/tmp/state.sqlite\nn/tmp/a.sqlite\n",
    ):
        assert not q._state_db_ids(q._parse_lsof_records(bad))


def test_info_plist_fifo_rejected_without_open(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    app = tmp_path / "Codex.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    entry = app / "Contents" / "Info.plist"
    os.mkfifo(entry)
    original = Path.open

    def guarded_open(self, *a, **kw):
        if self == entry:
            raise AssertionError("FIFO Info.plist must not be opened")
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "open", guarded_open)
    parent = q.ProcessInfo(101, 1, 501, str(app / "Contents" / "MacOS" / "Codex"))
    worker = q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server")
    assert q._app_version([worker], {101: parent, 102: worker}) is None


def test_large_info_plist_is_rejected_before_parse(tmp_path, monkeypatch):
    import plistlib
    app = tmp_path / "Codex.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    entry = app / "Contents" / "Info.plist"
    with entry.open("wb") as stream:
        plistlib.dump({
            "CFBundleShortVersionString": "1.2.3",
            "long": "a" * (256 * 1024),
        }, stream)
    def forbidden_parser(*a, **kw):
        raise AssertionError("oversized plist must not reach parser")
    monkeypatch.setattr(plistlib, "load", forbidden_parser)
    monkeypatch.setattr(plistlib, "loads", forbidden_parser)
    parent = q.ProcessInfo(101, 1, 501, str(app / "Contents" / "MacOS" / "Codex"))
    worker = q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server")
    assert q._app_version([worker], {101: parent, 102: worker}) is None


def test_symlinked_info_plist_is_rejected_without_open(tmp_path, monkeypatch):
    from pathlib import Path
    app = tmp_path / "Codex.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    entry = app / "Contents" / "Info.plist"
    target = tmp_path / "external.plist"
    target.write_bytes(b"<plist>not the bundle's own version</plist>")
    entry.symlink_to(target)
    orig = Path.open

    def forbidden_open(self, *a, **kw):
        if self == entry:
            raise AssertionError("symlinked plist must not be followed")
        return orig(self, *a, **kw)

    monkeypatch.setattr(Path, "open", forbidden_open)
    parent = q.ProcessInfo(101, 1, 501, str(app / "Contents" / "MacOS" / "Codex"))
    worker = q.ProcessInfo(102, 101, 501, "/opt/homebrew/bin/codex app-server")
    assert q._app_version([worker], {101: parent, 102: worker}) is None
