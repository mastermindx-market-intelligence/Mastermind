"""Lane TSH: teammate titles and primary-thread recovery.

Pure unit tests — no server is started or contacted, no real T3 home is read.
Each test builds a throwaway ``statev2.sqlite`` with the real
``orchestration_v2_projection_threads`` schema and stubs ``t3`` so a launch
would be recorded rather than performed.
"""

import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "mmos_team_server" / "team_roster.py"
SPEC = REPO / "tools" / "mmos_team_server" / "specs" / "team_roster.json"

spec_loader = importlib.util.spec_from_file_location("team_roster", TOOL)
team_roster = importlib.util.module_from_spec(spec_loader)
spec_loader.loader.exec_module(team_roster)

PROJECT = "project-1"

# The columns the server actually writes (apps/server/src/orchestration-v2/
# ProjectionStore.ts); provider_instance_id is the durable owner of a thread.
THREADS_DDL = """
CREATE TABLE orchestration_v2_projection_threads (
  thread_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  default_provider TEXT NOT NULL,
  runtime_mode TEXT NOT NULL,
  interaction_mode TEXT NOT NULL,
  active_provider_thread_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived_at TEXT,
  deleted_at TEXT,
  payload_json TEXT NOT NULL,
  provider_instance_id TEXT
)
"""


def make_spec(tmp_path, mates=None):
    root = str(tmp_path / "t3-team")
    return {
        "server": {"root": root, "home": os.path.join(root, "home"),
                   "t3_bin": "/bin/echo", "port": 3780,
                   "provider_source_instance": "capacity_fabric"},
        "project": {"title": "Team",
                    "workspace_root": os.path.join(root, "team-project")},
        "model": "glm-5.3",
        "state_file": os.path.join(root, "run", "team_roster_state.json"),
        "teammates": mates or [
            {"name": "A", "slug": "a", "role": "qa", "role_line": "quality",
             "accent_color": "#e0b64d", "instance": "a", "charter": "# A\n"},
            {"name": "B", "slug": "b", "role": "designer",
             "role_line": "product", "accent_color": "#3fb6a8", "instance": "b",
             "charter": "# B\n"},
        ],
    }


def load(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return team_roster.load_spec(str(path))


def make_db(spec, threads=()):
    """Create the throwaway state database with the given live threads."""
    path = team_roster.db_path(spec)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(THREADS_DDL)
    for t in threads:
        payload = {"id": t["threadId"], "projectId": PROJECT,
                   "title": t["title"],
                   "providerInstanceId": t.get("instance")}
        conn.execute(
            "INSERT INTO orchestration_v2_projection_threads "
            "(thread_id, project_id, title, default_provider, runtime_mode, "
            "interaction_mode, created_at, updated_at, payload_json, "
            "provider_instance_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (t["threadId"], PROJECT, t["title"], "claudeAgent", "full-access",
             "default", t.get("createdAt", "2026-11-10T00:00:00Z"),
             "2026-11-10T00:00:00Z", json.dumps(payload),
             t.get("instance")))
    conn.commit()
    conn.close()
    return path


def write_state(spec, teammates):
    path = team_roster.expand(spec["state_file"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"teammates": teammates}, fh)


class FakeT3:
    """Records every launch; never runs a process."""

    def __init__(self):
        self.calls = []

    def __call__(self, spec, args, stdin_text=None, timeout=900):
        self.calls.append(list(args))
        thread_id = f"mcp:new-{len(self.calls)}"
        out = json.dumps({"threadId": thread_id, "title": args[-3]})

        class Proc:
            returncode = 0
            stdout = out + "\n"
            stderr = ""

        return Proc()


@pytest.fixture
def fake_t3(monkeypatch):
    fake = FakeT3()
    monkeypatch.setattr(team_roster, "t3", fake)
    return fake


class TestTeammateTitle:
    def test_exact_format(self):
        mate = {"name": "Assurance", "role_line": "quality"}
        assert team_roster.teammate_title(mate) == "Assurance — quality"

    def test_real_spec_titles_fit_24(self):
        spec = team_roster.load_spec(str(SPEC))
        titles = {m["name"]: team_roster.teammate_title(m)
                  for m in spec["teammates"]}
        assert titles["Assurance"] == "Assurance — quality"
        assert titles["Design Lead"] == "Design Lead — product"
        # 9 + " — " (3) + 7 = 19; 11 + " — " (3) + 7 = 21. Both fit 24.
        assert len(titles["Assurance"]) == 19
        assert len(titles["Design Lead"]) == 21
        for title in titles.values():
            assert len(title) <= team_roster.TITLE_MAX

    @pytest.mark.parametrize("role_line", ["quality & security", "product design",
                                           "two words", "with space", "é"])
    def test_role_line_must_be_one_ascii_word(self, tmp_path, role_line):
        spec = make_spec(tmp_path)
        spec["teammates"][0]["role_line"] = role_line
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    def test_title_over_24_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"][0]["name"] = "A Very Long Teammate Name"
        with pytest.raises(SystemExit):
            load(tmp_path, spec)

    def test_name_with_em_dash_refused(self, tmp_path):
        spec = make_spec(tmp_path)
        spec["teammates"][0]["name"] = "A — B"
        with pytest.raises(SystemExit):
            load(tmp_path, spec)


class TestListThreads:
    def test_returns_instance_and_pin(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"}])
        rows = team_roster.list_threads(spec, PROJECT)
        assert rows == [{"threadId": "t1", "title": "A — quality",
                         "pinnedAt": None, "instance": "a"}]

    def test_compat_view_keeps_exact_title_dict(self, tmp_path):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"}])
        assert team_roster.threads_in_project(spec, PROJECT) == {
            "A — quality": {"threadId": "t1", "pinnedAt": None}}


class TestRecovery:
    def test_renamed_title_with_state_is_same_thread(self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "A — renamed by hand",
                        "instance": "a"},
                       {"threadId": "t2", "title": "B — product",
                        "instance": "b"}])
        write_state(spec, {"A": {"instance": "a", "threadId": "t1"},
                           "B": {"instance": "b", "threadId": "t2"}})
        threads, _ = team_roster.ensure_threads(spec, PROJECT)
        assert threads["A"]["threadId"] == "t1"
        assert threads["A"]["created"] is False
        assert threads["A"]["recoveredBy"] == "state"
        assert fake_t3.calls == []

    def test_full_state_loss_recovers_by_instance(self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"},
                       {"threadId": "t2", "title": "B — product",
                        "instance": "b"}])
        # no state file at all
        threads, _ = team_roster.ensure_threads(spec, PROJECT)
        assert threads["A"]["threadId"] == "t1"
        assert threads["B"]["threadId"] == "t2"
        assert threads["A"]["recoveredBy"] == "instance"
        assert fake_t3.calls == []

    def test_full_state_loss_recovers_by_title_prefix(self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        # instance column absent (older row): only the stable title remains
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": None},
                       {"threadId": "t2", "title": "B — product",
                        "instance": None}])
        threads, _ = team_roster.ensure_threads(spec, PROJECT)
        assert threads["A"]["threadId"] == "t1"
        assert threads["A"]["recoveredBy"] == "title"
        assert fake_t3.calls == []

    def test_two_instance_candidates_refused(self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"},
                       {"threadId": "t2", "title": "A — scratch",
                        "instance": "a"}])
        with pytest.raises(SystemExit):
            team_roster.ensure_threads(spec, PROJECT)
        assert fake_t3.calls == []

    def test_thread_titled_for_one_mate_owned_by_another_refused(
            self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        # Titled for A, but its durable instance is B's: adopting it would put
        # A into B's conversation.
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "b"}])
        with pytest.raises(SystemExit):
            team_roster.ensure_threads(spec, PROJECT)
        assert fake_t3.calls == []

    def test_state_pointing_at_another_mates_thread_refused(
            self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "B — product",
                        "instance": "b"}])
        write_state(spec, {"A": {"instance": "a", "threadId": "t1"},
                           "B": {"instance": "b", "threadId": "t1"}})
        with pytest.raises(SystemExit):
            team_roster.ensure_threads(spec, PROJECT)
        assert fake_t3.calls == []

    def test_creates_only_when_nothing_matches(self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [])
        threads, _ = team_roster.ensure_threads(spec, PROJECT)
        assert threads["A"]["created"] is True
        assert threads["B"]["created"] is True
        assert len(fake_t3.calls) == 2
        assert fake_t3.calls[0][:2] == ["thread", "start"]
        assert "--title" in fake_t3.calls[0]
        assert fake_t3.calls[0][fake_t3.calls[0].index("--title") + 1] == \
            "A — quality"

    def test_state_records_durable_evidence(self, tmp_path, fake_t3):
        spec = load(tmp_path, make_spec(tmp_path))
        make_db(spec, [{"threadId": "t1", "title": "A — quality",
                        "instance": "a"},
                       {"threadId": "t2", "title": "B — product",
                        "instance": "b"}])
        team_roster.ensure_threads(spec, PROJECT)
        state = json.load(open(team_roster.expand(spec["state_file"])))
        assert state["teammates"]["A"]["threadId"] == "t1"
        assert state["teammates"]["A"]["threadInstance"] == "a"
        assert state["teammates"]["A"]["recoveredBy"] == "instance"
        assert state["teammates"]["A"]["title"] == "A — quality"
