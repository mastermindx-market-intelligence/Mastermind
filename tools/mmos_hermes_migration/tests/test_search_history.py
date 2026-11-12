"""Search CLI tests over a synthetic exported archive (tmp dirs only)."""
import json
import os
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
SEARCH = TOOL_DIR / "search_history.py"
EXPORT = TOOL_DIR / "export_history.py"


def ts(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp()


def make_search_db(path):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT, "
        "display_name TEXT, model TEXT, parent_session_id TEXT, started_at REAL NOT NULL, "
        "ended_at REAL, message_count INTEGER, profile_name TEXT, archived INTEGER, hidden INTEGER)"
    )
    con.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, "
        "content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, timestamp REAL NOT NULL, "
        "finish_reason TEXT, active INTEGER, compacted INTEGER, display_kind TEXT, reasoning TEXT, "
        "reasoning_content TEXT, api_content TEXT)"
    )
    a = ts(2026, 2, 1, 9, 0)
    b = ts(2026, 2, 3, 9, 0)
    con.executemany(
        "INSERT INTO sessions (id, source, title, started_at, message_count) VALUES (?,?,?,?,?)",
        [("alpha-0001-aaaa", "cli", "Alpha planning", a, 3), ("beta-0002-bbbb", "web", None, b, 2)],
    )
    con.executemany(
        "INSERT INTO messages (id, session_id, role, content, tool_name, timestamp, active, compacted) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "alpha-0001-aaaa", "user", "needle alpha user message", None, a, 1, 0),
            (2, "alpha-0001-aaaa", "assistant", "needle alpha assistant reply", None, a + 60, 1, 0),
            (3, "alpha-0001-aaaa", "tool", "needle alpha tool output", "grep", a + 120, 1, 0),
            (4, "beta-0002-bbbb", "user", "needle beta user message", None, b, 1, 0),
            (5, "beta-0002-bbbb", "assistant", "needle beta assistant reply", None, b + 60, 1, 0),
        ],
    )
    con.commit()
    con.close()


def run(args, home=None):
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run([sys.executable, str(SEARCH), *args], capture_output=True, text=True, timeout=180, env=env)


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    base = tmp_path_factory.mktemp("search")
    src = base / "copy.db"
    make_search_db(src)
    out = base / "archive"
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, str(EXPORT), "export", "--source", str(src), "--profile", "p", "--out", str(out)],
        capture_output=True, text=True, timeout=180, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return out


def hits_json(proc):
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_phrase_found(archive):
    proc = run([str(archive), "needle", "alpha", "--json"])
    hits = hits_json(proc)
    assert {h["src_id"] for h in hits} == {1, 2, 3}
    for h in hits:
        assert h["snippet"] and len(h["snippet"]) <= 300
        assert h["session_file"].endswith(".md")
        assert h["date"] and h["role"]


def test_text_output_marks_match(archive):
    proc = run([str(archive), "needle"])
    assert proc.returncode == 0, proc.stderr
    assert "src_id=1" in proc.stdout
    assert "[[needle]]" in proc.stdout
    assert "2026-02-01_cli_alpha-0001-a.md" in proc.stdout


def test_role_filter(archive):
    hits = hits_json(run([str(archive), "needle", "--role", "assistant", "--json"]))
    assert {h["src_id"] for h in hits} == {2, 5}
    assert all(h["role"] == "assistant" for h in hits)


def test_since_until(archive):
    hits = hits_json(run([str(archive), "needle", "--since", "2026-02-02", "--json"]))
    assert {h["src_id"] for h in hits} == {4, 5}
    hits = hits_json(run([str(archive), "needle", "--until", "2026-02-02", "--json"]))
    assert {h["src_id"] for h in hits} == {1, 2, 3}


def test_session_prefix(archive):
    hits = hits_json(run([str(archive), "needle", "--session", "alpha", "--json"]))
    assert {h["src_id"] for h in hits} == {1, 2, 3}


def test_limit(archive):
    hits = hits_json(run([str(archive), "needle", "--limit", "2", "--json"]))
    assert len(hits) == 2
    proc = run([str(archive), "needle", "--limit", "999", "--json"])
    assert proc.returncode == 0
    assert len(hits_json(proc)) <= 50


def test_quotes_and_fts_operators_no_crash(archive):
    for q in ['needle "alpha" OR (', '"', 'needle AND OR NEAR(', 'a"b', "needle)"]:
        proc = run([str(archive), q, "--json"])
        assert proc.returncode == 0, (q, proc.stderr)
        assert "Traceback" not in proc.stderr


def test_no_results(archive):
    proc = run([str(archive), "zzzznotpresent", "--json"])
    assert proc.returncode == 0
    assert hits_json(proc) == []


def test_show_context(archive):
    proc = run([str(archive), "--show", "2"])
    assert proc.returncode == 0, proc.stderr
    for text in ("needle alpha user message", "needle alpha assistant reply", "needle alpha tool output"):
        assert text in proc.stdout
    assert "needle beta" not in proc.stdout
    proc = run([str(archive), "--show", "4"])
    assert proc.returncode == 0, proc.stderr
    assert "needle beta user message" in proc.stdout and "needle beta assistant reply" in proc.stdout
    assert "needle alpha" not in proc.stdout


def test_archive_stays_readonly(archive):
    db = archive / "archive.sqlite"
    before = stat.S_IMODE(db.stat().st_mode)
    run([str(archive), "needle", "--json"])
    assert stat.S_IMODE(db.stat().st_mode) == before == 0o400
