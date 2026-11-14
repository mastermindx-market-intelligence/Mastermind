"""B-PRESFIX (F5/F8/F9): properties of tools/mmos_team_server/lock_census.py.

Every fixture is a FAKE team home under a tmp dir — no real root, no server,
no network, no port is bound. The census runs as a subprocess.

F5: the census opens the state database with its OWN `?mode=ro` connection
(never immutable=1) and prints the journal mode. The main DB file is never
written; on a WAL DB with the server stopped sqlite may create -wal/-shm
sidecars when the read-only connection opens (with the server running they
already exist and are the server's) — the tests therefore assert the MAIN
DB's sha is unchanged, not the absence of sidecars.

Run:
  TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
    -p no:cacheprovider tests/test_mmos_lock_census.py
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

import pytest

CENSUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools", "mmos_team_server", "lock_census.py")

FAKE_SECRET = "FAKE-SECRET-do-not-leak-9f3a2b7c"
FAKE_TITLE = "SENSITIVE-TITLE-abc123"


def sha_file(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_home(tmp_path, wal=False, threads=None, mates=None, instances=None,
               project=True, state=None):
    """A fake team home: projection DB, settings.json, spec, roster state."""
    root = tmp_path / "team"
    home = root / "home"
    ud = home / "userdata"
    ud.mkdir(parents=True)
    (root / "team-project").mkdir()
    (root / "run").mkdir()
    dbp = ud / "statev2.sqlite"
    conn = sqlite3.connect(str(dbp))
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE projection_projects (project_id TEXT, "
                 "title TEXT, workspace_root TEXT, deleted_at TEXT)")
    conn.execute("CREATE TABLE orchestration_v2_projection_threads "
                 "(thread_id TEXT, title TEXT, payload_json TEXT, "
                 "provider_instance_id TEXT, project_id TEXT, "
                 "deleted_at TEXT, created_at TEXT)")
    wroot = str(root / "team-project")
    if project:
        conn.execute("INSERT INTO projection_projects VALUES (?,?,?,NULL)",
                     ("proj-1", "Team", wroot))
    if threads is None:
        threads = [("t1", FAKE_TITLE, "assurance", None),
                   ("t2", "x", "capacity_fabric", None),
                   ("t3", "y", "capacity_fabric", None)]
    for tid, title, inst, deleted in threads:
        conn.execute("INSERT INTO orchestration_v2_projection_threads "
                     "VALUES (?,?,?,?,?,?,?)",
                     (tid, title, "{}", inst, "proj-1", deleted,
                      "2026-01-01"))
    conn.commit()
    conn.close()  # clean close: no -wal/-shm left behind by the fixture
    if instances is None:
        instances = {"assurance": {},
                     "capacity_fabric": {"config": {"apiKey": FAKE_SECRET}}}
    (ud / "settings.json").write_text(
        json.dumps({"providerInstances": instances}), encoding="utf-8")
    if mates is None:
        mates = [{"name": "Assurance", "slug": "assurance", "role": "r",
                  "role_line": "assurance", "accent_color": "#112233",
                  "instance": "assurance", "charter": "c"}]
    spec = {"server": {"root": str(root), "home": str(home),
                       "t3_bin": "/usr/bin/true", "port": 3830},
            "project": {"title": "Team", "workspace_root": wroot},
            "model": "m", "teammates": mates}
    sp = root / "spec.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    if state is None:
        state = {"teammates": {"Assurance": {"threadId": "t1"}}}
    if state is not False:
        (root / "run" / "team_roster_state.json").write_text(
            json.dumps(state), encoding="utf-8")
    return sp, dbp, ud


def run_census(sp):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, CENSUS, str(sp)],
                          capture_output=True, text=True, timeout=60,
                          env=env)


def test_wal_main_db_unchanged_and_journal_mode(tmp_path):
    sp, dbp, _ud = build_home(tmp_path, wal=True)
    before = sha_file(dbp)
    r = run_census(sp)
    assert r.returncode == 0, r.stderr
    # the MAIN database file is never written (sidecars may appear; they
    # are sqlite's WAL machinery, not a write to the main DB)
    assert sha_file(dbp) == before
    out = json.loads(r.stdout)
    assert out["journalMode"] == "wal"
    assert out["ok"] is True
    assert out["conversations"] == 3


def test_delete_mode_journal_mode_printed(tmp_path):
    sp, dbp, _ud = build_home(tmp_path)
    before = sha_file(dbp)
    r = run_census(sp)
    assert r.returncode == 0, r.stderr
    assert sha_file(dbp) == before
    out = json.loads(r.stdout)
    assert out["journalMode"] == "delete"
    assert out["ok"] is True


def test_happy_path_counts_and_no_leak(tmp_path):
    sp, _dbp, _ud = build_home(tmp_path)
    r = run_census(sp)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["project"] == "proj-1"
    assert out["conversations"] == 3
    assert out["byInstance"] == {"assurance": 1, "capacity_fabric": 2}
    assert out["onMissingInstance"] == []
    assert out["primaryMismatch"] == []
    assert out["ok"] is True
    # no conversation text, title or secret anywhere in the output
    assert FAKE_SECRET not in r.stdout + r.stderr
    assert FAKE_TITLE not in r.stdout + r.stderr


def test_missing_project_clean_die(tmp_path):
    sp, _dbp, _ud = build_home(tmp_path, project=False)
    r = run_census(sp)
    assert r.returncode != 0
    assert "Traceback" not in r.stderr
    assert "lock_census" in r.stderr


def test_missing_db_clean_die(tmp_path):
    sp, dbp, _ud = build_home(tmp_path)
    dbp.unlink()
    r = run_census(sp)
    assert r.returncode != 0
    assert "Traceback" not in r.stderr


def test_no_title_text_in_stderr(tmp_path):
    # load_spec's long-title warning carries the teammate title; the census
    # prints no titles, so the warning must be suppressed (F9)
    long_role = "a-very-long-role-line-that-exceeds"
    mates = [{"name": "Assurance", "slug": "assurance", "role": "r",
              "role_line": long_role, "accent_color": "#112233",
              "instance": "assurance", "charter": "c"}]
    sp, _dbp, _ud = build_home(tmp_path, mates=mates)
    spec = json.loads(sp.read_text())
    spec["allow_long_titles"] = True
    sp.write_text(json.dumps(spec), encoding="utf-8")
    r = run_census(sp)
    assert r.returncode == 0, r.stderr
    assert long_role not in r.stderr
    assert "Assurance" not in r.stderr


def test_missing_instance_nonzero(tmp_path):
    sp, _dbp, _ud = build_home(tmp_path, instances={"assurance": {}})
    r = run_census(sp)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert set(out["onMissingInstance"]) == {"t2", "t3"}


def test_primary_mismatch_nonzero(tmp_path):
    sp, _dbp, _ud = build_home(tmp_path, state={"teammates": {}})
    r = run_census(sp)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert out["primaryMismatch"]


def test_deleted_primary_thread_nonzero(tmp_path):
    sp, _dbp, _ud = build_home(
        tmp_path, threads=[("t1", FAKE_TITLE, "assurance", "2026-01-02"),
                           ("t2", "x", "capacity_fabric", None)])
    r = run_census(sp)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert out["primaryMismatch"]
