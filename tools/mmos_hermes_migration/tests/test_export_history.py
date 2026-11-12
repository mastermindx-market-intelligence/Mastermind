"""Export/verify tests. All databases are synthetic fixtures in tmp dirs.

Never touches ~/.hermes or ~/.mastermind for real; refusal tests use a
monkeypatched fake HOME under tmp_path.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
EXPORT = TOOL_DIR / "export_history.py"

SECRETS = [
    "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF000011112222",
    "sk-proj-AAAABBBBCCCCDDDDEEEEFFFF000011112222",
    "ghp_" + "A1b2C3d4E5f6G7h8I9j0" * 2,
    "github_pat_" + "A1b2C3d4E5f6G7h8I9j0" * 2,
    "xoxb-123456789012-1234567890123-AbCdEfGhIjKl",
    "xapp-1-A0123456789-1234567890123-abcdefabcdef",
    "AKIAIOSFODNN7EXAMPLE",
    "ASIAIOSFODNN7EXAMPLE",
    "AIza" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "SuperSecretPass99",
    "Sup3rSecretValue!",
    "abcdef1234567890abcdef",
    "QuotedSecretValue123",
    "longauthvalue123456",
    "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU2Nzg5",
    "abcdefghijklmnopqrstuvwxyz0123456789",  # bearer token
]
# Contextual forms: every secret embedded the way its rule expects it.
SECRET_CONTEXTS = [
    SECRETS[0], SECRETS[1], SECRETS[2], SECRETS[3], SECRETS[4], SECRETS[5],
    SECRETS[6], SECRETS[7], SECRETS[8], SECRETS[9],
    f"https://user:{SECRETS[10]}@host.example/path",
    f"password={SECRETS[11]}",
    f"api_key: {SECRETS[12]}",
    f"secret='{SECRETS[13]}'",
    f"auth: {SECRETS[14]}",
    f"api_key={SECRETS[15]}",
    f"secret={SECRETS[16]}",
    f"Bearer {SECRETS[17]}",
]
SAFE_SHA = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"
SAFE_UUID = "123e4567-e89b-12d3-a456-426614174000"
CONTENT_MARKER = "UniqueContentMarker12345"
TITLE_MARKER = "UniqueTitleABCDEF"
REASONING_MARKERS = ["ReasoningMarkerDO_NOT_COPY_1", "RC_Marker_1", "API_Marker_1", "API_Marker_2"]

SESSION_COLS = (
    "id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT, display_name TEXT, "
    "model TEXT, parent_session_id TEXT, started_at REAL NOT NULL, ended_at REAL, "
    "message_count INTEGER, profile_name TEXT, archived INTEGER, hidden INTEGER, "
    "extra_unknown_col TEXT"
)
MESSAGE_COLS = (
    "id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, "
    "content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, "
    "timestamp REAL NOT NULL, finish_reason TEXT, active INTEGER, compacted INTEGER, "
    "display_kind TEXT, reasoning TEXT, reasoning_content TEXT, api_content TEXT, "
    "weird_extra_col TEXT"
)


def ts(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp()


def make_db(path, minimal=False):
    """Build a synthetic Hermes-shaped DB. minimal=True drops optional columns."""
    msg_cols = MESSAGE_COLS
    if minimal:
        for col in ("api_content TEXT", "reasoning_content TEXT", "display_kind TEXT", "finish_reason TEXT"):
            msg_cols = msg_cols.replace(", " + col, "")
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE sessions ({SESSION_COLS})")
    con.execute(f"CREATE TABLE messages ({msg_cols})")
    s1_started = ts(2026, 1, 2, 10, 0)
    s2_started = ts(2026, 1, 3, 11, 0)
    con.execute(
        "INSERT INTO sessions (id, source, title, display_name, model, started_at, ended_at, message_count, profile_name) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("sess-0001-aaaa", "cli", TITLE_MARKER + " migration", "Teammate One", "test-model", s1_started, s1_started + 3600, 4, "default"),
    )
    if not minimal:
        con.execute(
            "INSERT INTO sessions (id, source, title, display_name, model, started_at, ended_at, message_count, profile_name) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("sess-0002-bbbb", "web", None, "Teammate Two", "test-model", s2_started, None, 3, "default"),
        )
    long_tool = "TOOLONGSTART" + "x" * 5000 + "TOOLONGEND"
    tool_calls = json.dumps([
        {"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": json.dumps({"cmd": "echo hi"})}},
        {"id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "x", "key": SECRETS[0]})}},
    ])
    rows = [
        # id, session, role, content, tool_call_id, tool_calls, tool_name, ts, finish, active, compacted, display_kind, reasoning, rc, api
        (1, "sess-0001-aaaa", "user", f"Hello {CONTENT_MARKER} sha {SAFE_SHA} uuid {SAFE_UUID}", None, None, None, s1_started, "stop", 1, 0, None, None, None, None),
        (2, "sess-0001-aaaa", "assistant", f"Working. password={SECRETS[11]} and {SECRETS[0]}", None, tool_calls, None, s1_started + 60, "tool_calls", 1, 0, None, None, None, None),
        (3, "sess-0001-aaaa", "tool", long_tool, "call_1", None, "bash", s1_started + 120, None, 1, 0, "tool_result", None, None, None),
        (4, "sess-0001-aaaa", "assistant", "Old summary compacted away.", None, None, None, s1_started + 180, "stop", 0, 1, None, REASONING_MARKERS[0], REASONING_MARKERS[1], REASONING_MARKERS[2]),
        (5, "sess-0002-bbbb", "user", "Second session first user message about migration planning.", None, None, None, s2_started, "stop", 1, 0, None, None, None, None),
        (6, "sess-0002-bbbb", "assistant", " ".join(SECRET_CONTEXTS), None, None, None, s2_started + 60, "stop", 1, 0, None, None, None, REASONING_MARKERS[3]),
        (7, "sess-0002-bbbb", "tool", "inactive tool output", "call_9", None, "read", s2_started + 120, None, 0, 0, None, None, None, None),
    ]
    if minimal:
        rows = [r[:8] + r[9:11] for r in rows[:2]]  # drop finish_reason/display_kind/reasoning/rc/api
    con.executemany(
        "INSERT INTO messages (id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp"
        + ("" if minimal else ", finish_reason")
        + ", active, compacted"
        + ("" if minimal else ", display_kind, reasoning, reasoning_content, api_content")
        + ") VALUES (" + ",".join("?" * (10 if minimal else 15)) + ")",
        rows,
    )
    con.commit()
    con.close()
    return path


def run_cli(script, args, home=None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, timeout=180, env=env
    )


def all_bytes(root):
    blobs = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            blobs[str(p.relative_to(root))] = p.read_bytes()
    return blobs


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    base = tmp_path_factory.mktemp("exp")
    src = make_db(base / "copy.db")
    out = base / "archive"
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "testprofile", "--out", str(out)])
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    return {"base": base, "src": src, "out": out, "proc": proc, "manifest": manifest}


def test_counts_and_manifest(exported):
    m = exported["manifest"]
    cc = m["count_check"]
    assert cc["pass"] is True
    assert cc["sessions_in"] == cc["sessions_out"] == 2
    assert cc["messages_in"] == cc["messages_out"] == 7
    assert cc["by_role_in"] == cc["by_role_out"] == {"user": 2, "assistant": 3, "tool": 2}
    assert m["counts"]["sessions"] == 2 and m["counts"]["messages"] == 7
    assert m["counts"]["active"] == 5 and m["counts"]["inactive"] == 2
    assert m["counts"]["by_source"] == {"cli": 1, "web": 1}
    assert m["profile"] == "testprofile"
    assert m["omitted_fields"] == {"reasoning": 1, "reasoning_content": 1, "api_content": 2}
    assert m["redactions"] and sum(m["redactions"].values()) >= 15
    assert m["date_range"]["start"] == "2026-01-02" and m["date_range"]["end"] == "2026-01-03"
    assert m["source_sha256"] == hashlib.sha256(exported["src"].read_bytes()).hexdigest()
    assert m["tool_version"] and m["exported_at"]


def test_every_row_copied_flags_kept(exported):
    con = sqlite3.connect(f"file:{exported['out'] / 'archive.sqlite'}?mode=ro", uri=True)
    rows = con.execute("SELECT src_id, active, compacted FROM messages ORDER BY src_id").fetchall()
    con.close()
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert rows[3] == (4, 0, 1) and rows[6] == (7, 0, 0)


def test_secrets_and_reasoning_absent_safe_kept(exported):
    blobs = all_bytes(exported["out"])
    joined = b"\n".join(blobs.values())
    for s in SECRETS:
        assert s.encode() not in joined, f"secret leaked: {s[:6]}..."
    for marker in REASONING_MARKERS:
        assert marker.encode() not in joined
    assert SAFE_SHA.encode() in joined and SAFE_UUID.encode() in joined
    assert b"[REDACTED:" in joined


def test_markdown_files(exported):
    out = exported["out"]
    f1 = out / "sessions" / "2026-01-02_cli_sess-0001-aa.md"
    f2 = out / "sessions" / "2026-01-03_web_sess-0002-bb.md"
    assert f1.is_file() and f2.is_file()
    t1 = f1.read_text()
    assert "sess-0001-aaaa" in t1 and TITLE_MARKER in t1
    assert "### user ·" in t1 and "### assistant ·" in t1 and "### tool ·" in t1
    assert "(compacted)" in t1
    assert "… [truncated 1022 chars; full text in archive.sqlite src_id=3]" in t1
    assert "bash" in t1 and "read_file" in t1  # tool names line
    assert "TOOLONGEND" not in t1  # truncated tail not in md
    assert b"TOOLONGEND" in (out / "archive.sqlite").read_bytes()  # full text in sqlite
    idx = (out / "INDEX.md").read_text()
    assert idx.index("sess-0002") < idx.index("sess-0001")  # newest first
    assert "Second session first user message" in idx  # title fallback
    assert "2026-01-03_web_sess-0002-bb.md" in idx


def test_permissions(exported):
    out = exported["out"]
    assert stat.S_IMODE(out.stat().st_mode) == 0o500
    for p in out.rglob("*"):
        mode = stat.S_IMODE(p.stat().st_mode)
        assert mode == (0o500 if p.is_dir() else 0o400), (p, oct(mode))


def test_stdout_no_content(exported):
    text = exported["proc"].stdout + exported["proc"].stderr
    for s in SECRETS + [CONTENT_MARKER, TITLE_MARKER] + REASONING_MARKERS:
        assert s not in text
    assert "7" in text  # counts are printed


def test_source_unmodified(exported):
    assert hashlib.sha256(exported["src"].read_bytes()).hexdigest() == exported["manifest"]["source_sha256"]


def test_verify_pass(exported):
    proc = run_cli(EXPORT, ["verify", "--source", str(exported["src"]), "--archive", str(exported["out"])])
    assert proc.returncode == 0, proc.stderr
    line = json.loads(proc.stdout.strip().splitlines()[-1])
    assert line["pass"] is True and line["mismatches"] == []


def test_verify_detects_tamper(exported, tmp_path):
    tampered = tmp_path / "tampered_archive"
    tampered.mkdir()
    dst = tampered / "archive.sqlite"
    shutil.copy(exported["out"] / "archive.sqlite", dst)
    os.chmod(dst, 0o600)
    con = sqlite3.connect(dst)
    con.execute("DELETE FROM messages WHERE src_id = 6")
    con.commit()
    con.close()
    proc = run_cli(EXPORT, ["verify", "--source", str(exported["src"]), "--archive", str(tampered)])
    assert proc.returncode != 0
    line = json.loads(proc.stdout.strip().splitlines()[-1])
    assert line["pass"] is False and line["mismatches"]


def test_minimal_fixture_missing_columns(tmp_path):
    src = make_db(tmp_path / "minimal.db", minimal=True)
    out = tmp_path / "out_min"
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(out)])
    assert proc.returncode == 0, proc.stderr
    m = json.loads((out / "manifest.json").read_text())
    assert m["count_check"]["pass"] is True
    assert m["counts"]["sessions"] == 1 and m["counts"]["messages"] == 2
    assert m["omitted_fields"]["api_content"] == 0
    con = sqlite3.connect(f"file:{out / 'archive.sqlite'}?mode=ro", uri=True)
    assert con.execute("SELECT display_kind FROM messages WHERE src_id=1").fetchone()[0] is None
    con.close()


def test_refuse_source_under_hermes(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    hermes = fake_home / ".hermes"
    hermes.mkdir(parents=True)
    src = make_db(hermes / "state.db")
    monkeypatch.setenv("HOME", str(fake_home))
    out = tmp_path / "out"
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(out)], home=fake_home)
    assert proc.returncode != 0
    assert not out.exists()


def test_refuse_source_symlink(tmp_path):
    src = make_db(tmp_path / "real.db")
    link = tmp_path / "link.db"
    link.symlink_to(src)
    proc = run_cli(EXPORT, ["export", "--source", str(link), "--profile", "p", "--out", str(tmp_path / "o")])
    assert proc.returncode != 0


def test_refuse_source_forbid_root(tmp_path):
    src = make_db(tmp_path / "real.db")
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(tmp_path / "o"), "--forbid-root", str(tmp_path)])
    assert proc.returncode != 0


def test_refuse_out_under_hermes(tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    src = make_db(tmp_path / "real.db")
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(fake_home / ".hermes" / "arch")], home=fake_home)
    assert proc.returncode != 0


def test_refuse_out_under_t3_team(tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".mastermind" / "t3-team").mkdir(parents=True)
    src = make_db(tmp_path / "real.db")
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(fake_home / ".mastermind" / "t3-team" / "arch")], home=fake_home)
    assert proc.returncode != 0


def test_refuse_out_forbid_root(tmp_path):
    src = make_db(tmp_path / "real.db")
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(tmp_path / "o"), "--forbid-root", str(tmp_path)])
    assert proc.returncode != 0


def test_refuse_out_nonempty_one_line(tmp_path):
    src = make_db(tmp_path / "real.db")
    out = tmp_path / "o"
    out.mkdir()
    (out / "existing.txt").write_text("x")
    proc = run_cli(EXPORT, ["export", "--source", str(src), "--profile", "p", "--out", str(out)])
    assert proc.returncode != 0
    assert len(proc.stderr.strip().splitlines()) == 1
    assert (out / "existing.txt").read_text() == "x"
