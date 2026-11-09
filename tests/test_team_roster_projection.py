"""Team roster projection tests — fixtures only, never the live install."""
import json
import sqlite3
from pathlib import Path

import pytest

from control_plane.team_roster_projection import (
    DELETED_PROFILES_DIR,
    TEAM_ROSTER_SCHEMA,
    enumerate_profiles,
    gateway_observation,
    generate_team_roster,
    profile_display_name,
    profile_is_bot_managed,
    profile_role,
    probe_control_socket,
    read_activity,
    read_gateway_lock,
    scrub,
    validate_team_roster,
    verify_lock_pid,
)

HOST = "m2studio.test"


def make_profile(root: Path, name: str, *, profile_yaml: str | None = None,
                 lock: dict | None = None, activity: tuple | None = None) -> Path:
    directory = root / "profiles" / name
    directory.mkdir(parents=True)
    (directory / "SOUL.md").write_text("soul\n", encoding="utf-8")
    if profile_yaml is not None:
        (directory / "profile.yaml").write_text(profile_yaml, encoding="utf-8")
    if lock is not None:
        (directory / "gateway.lock").write_text(json.dumps(lock), encoding="utf-8")
    if activity is not None:
        db = directory / "state.db"
        con = sqlite3.connect(db)
        con.execute("create table sessions (last_activity_at real, title text, "
                    "last_activity_description text)")
        con.execute("insert into sessions values (?,?,?)", activity)
        con.commit()
        con.close()
    return directory


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "SOUL.md").write_text("default soul\n", encoding="utf-8")
    return tmp_path


def lock(pid: int, start_time: int, home: str) -> dict:
    return {"pid": pid, "kind": "hermes-gateway",
            "argv": ["hermes_cli/main.py", "gateway", "run", "--quiet"],
            "start_time": start_time, "hermes_home": home}


def ps(pid: str, started: float, command: str = "python hermes_cli/main.py gateway run --quiet"):
    return {pid: {"started_epoch_s": started, "command": command}}


class TestEnumeration:
    def test_default_plus_named_live_profiles_only(self, root):
        make_profile(root, "engineering", profile_yaml="display_name: Eng\n")
        make_profile(root, "secretary")
        (root / "profiles" / "cache").mkdir()  # no identity marker → infra dir
        (root / "profiles" / "Bad_Name").mkdir()  # invalid id grammar
        ghost = root / "profiles" / "ghost"
        ghost.mkdir()  # marker-less ghost shell
        (ghost / "logs").mkdir()
        names = [name for name, _ in enumerate_profiles(root)]
        assert names == ["default", "engineering", "secretary"]

    def test_tombstoned_profile_is_not_a_teammate(self, root):
        gone = make_profile(root, "retired")
        (root / "profiles" / DELETED_PROFILES_DIR).mkdir()
        (root / "profiles" / DELETED_PROFILES_DIR / "retired").write_text("deleted\n")
        assert "retired" not in [name for name, _ in enumerate_profiles(root)]
        assert gone.name == "retired"


class TestProfileFacts:
    def test_display_and_role_come_from_profile_yaml(self):
        data = {"display_name": "Eng", "description": "builds things",
                "ui_meta": {"hermes-bots": {"title": "Engineer"}}}
        assert profile_display_name("engineering", data) == "Engineer"
        assert profile_display_name("engineering", {"display_name": "Eng"}) == "Eng"
        assert profile_display_name("engineering", None) == "engineering"
        assert profile_role(data) == "Engineer — builds things"
        assert profile_role(None) == ""
        assert profile_is_bot_managed(data) is True
        assert profile_is_bot_managed({"display_name": "x"}) is False
        assert profile_is_bot_managed(None) is False

    def test_secret_shapes_never_survive_scrub(self):
        assert "REDACTED" in scrub("key sk-abcdefghij123456 end")
        assert "REDACTED" in scrub("Authorization: Bearer abcdefghijklmnop")
        assert "abcdefghij" not in scrub("token ghp_abcdefghijk")


class TestGatewayEvidence:
    def test_verified_lock_pid_is_ready(self, root):
        directory = make_profile(root, "engineering",
                                 lock=lock(4242, 1_794_000_000_000, str(root)))
        observed = gateway_observation(
            directory, processes=ps("4242", 1_794_000_000.0))
        assert observed["readiness"] == "ready"
        assert observed["readinessReason"] == "GATEWAY_LOCK_PID_VERIFIED"
        assert observed["gateway"]["source"] == "gateway_lock"
        assert observed["gateway"]["pid"] == 4242

    def test_recycled_pid_is_degraded_never_ready(self, root):
        directory = make_profile(root, "engineering", lock=lock(4242, 0, str(root)))
        observed = gateway_observation(
            directory, processes=ps("4242", 9_000_000.0, command="MTLCompilerService"))
        assert observed["readiness"] == "degraded"
        assert observed["readinessReason"] == "GATEWAY_PID_RECYCLED"

    def test_start_time_mismatch_is_degraded(self, root):
        directory = make_profile(root, "engineering",
                                 lock=lock(4242, 1_794_000_000_000, str(root)))
        observed = gateway_observation(
            directory, processes=ps("4242", 9_000_000.0))
        assert observed["readinessReason"] == "GATEWAY_PID_START_MISMATCH"

    def test_dead_pid_is_degraded_and_absent_lock_is_unknown(self, root):
        directory = make_profile(root, "engineering",
                                 lock=lock(4242, 1_794_000_000_000, str(root)))
        assert gateway_observation(directory, processes={})["readinessReason"] == "GATEWAY_PID_NOT_RUNNING"
        bare = make_profile(root, "secretary")
        observed = gateway_observation(bare, processes={})
        assert observed["readiness"] == "unknown"
        assert observed["readinessReason"] == "NO_GATEWAY_LOCK"
        assert observed["gateway"] == {"observed": False, "source": "none",
                                       "instanceId": None, "authorityEpoch": None,
                                       "codeVersion": None, "pid": None, "state": None}

    def test_identify_beats_lock_and_home_mismatch_never_qualifies(self, root):
        directory = make_profile(root, "engineering",
                                 lock=lock(1, 1_794_000_000_000, str(root)))
        identify = {"observed": True, "state": "ready", "instance_id": "inst-1",
                    "authority_epoch": 3, "code_version": "0.23.0",
                    "hermes_home": str(directory)}
        observed = gateway_observation(directory, processes={}, identify=identify)
        assert observed["readiness"] == "ready"
        assert observed["gateway"]["source"] == "control_socket_identify"
        assert observed["gateway"]["instanceId"] == "inst-1"
        assert observed["gateway"]["authorityEpoch"] == 3
        mismatch = gateway_observation(
            directory, processes={},
            identify={**identify, "hermes_home": "/elsewhere"})
        assert mismatch["readiness"] == "degraded"
        assert mismatch["readinessReason"] == "GATEWAY_HOME_MISMATCH"

    def test_identify_in_a_non_ready_state_is_degraded(self, root):
        directory = make_profile(root, "engineering")
        observed = gateway_observation(directory, processes={}, identify={
            "observed": True, "state": "draining", "instance_id": "inst-1",
            "authority_epoch": 3, "code_version": "0.23.0",
            "hermes_home": str(directory)})
        assert observed["readiness"] == "degraded"
        assert observed["readinessReason"] == "GATEWAY_NOT_READY_STATE"


class TestProbeSocket:
    def test_absent_socket_is_reported_not_guessed(self, root, monkeypatch):
        monkeypatch.chdir(root)
        assert probe_control_socket(root / "profiles" / "none")["reason"] == "NO_CONTROL_SOCKET"


class TestActivity:
    def test_activity_columns_project_to_iso_and_summary(self, root):
        directory = make_profile(root, "engineering", activity=(
            1794200000.0, "Old title", "sequential tool running (451s): delegate_task"))
        result = read_activity(directory)
        assert result["lastActivity"].startswith("2026-")
        assert result["activitySummary"] == "sequential tool running (451s): delegate_task"
        assert "activityReason" not in result

    def test_unobserved_activity_carries_a_typed_reason(self, root):
        directory = make_profile(root, "engineering")
        assert read_activity(directory)["activityReason"] == "NO_STATE_DB"
        (directory / "state.db").write_bytes(b"not sqlite")
        result = read_activity(directory)
        assert result["activityReason"] == "STATE_DB_UNREADABLE"
        assert result["lastActivity"] is None


class TestProjection:
    def roster(self, root, **kwargs):
        make_profile(root, "engineering", profile_yaml=(
            "display_name: Eng\ndescription: builds\n"
            "ui_meta:\n  hermes-bots:\n    title: Engineer\n"),
            lock=lock(4242, 0, str(root)), activity=(1794200000.0, "T", "waiting"))
        return generate_team_roster(root, host=HOST,
                                    processes=ps("4242", 0.0), **kwargs)

    def test_document_is_closed_and_valid(self, root):
        document = self.roster(root)
        assert document["schema"] == TEAM_ROSTER_SCHEMA
        assert document["host"] == HOST
        assert [bot["id"] for bot in document["bots"]] == ["default", "engineering"]
        assert validate_team_roster(document) is document
        engineering = document["bots"][1]
        assert engineering["displayName"] == "Engineer"
        assert engineering["role"] == "Engineer — builds"
        assert engineering["managed"] is True
        assert engineering["profilePath"].startswith(str(root))
        assert engineering["readiness"] == "ready"
        assert engineering["lastActivity"] is not None

    def test_default_profile_without_yaml_degrades_honestly(self, root):
        document = self.roster(root)
        default = document["bots"][0]
        assert default["displayName"] == "default"
        assert default["role"] == ""
        assert default["managed"] is None  # profile.yaml absent → not observed
        assert default["readiness"] == "unknown"
        assert default["readinessReason"] == "NO_GATEWAY_LOCK"
        assert default["lastActivity"] is None
        assert default["activityReason"] == "NO_STATE_DB"

    def test_never_a_fabricated_fixture_count(self, root):
        empty_root = root / "elsewhere"
        empty_root.mkdir()
        (empty_root / "SOUL.md").write_text("x\n")
        document = generate_team_roster(empty_root, host=HOST, processes={})
        assert [bot["id"] for bot in document["bots"]] == ["default"]
        assert validate_team_roster(document) is document


class TestValidation:
    def valid(self, root):
        make_profile(root, "engineering")
        return generate_team_roster(root, host=HOST, processes={})

    def test_rejects_unknown_fields_and_bad_values(self, root):
        base = json.loads(json.dumps(self.valid(root)))
        broken = {**base, "schema": "other"}
        with pytest.raises(ValueError):
            validate_team_roster(broken)
        with pytest.raises(ValueError):
            validate_team_roster({**base, "generatedAt": "not-a-time"})
        with pytest.raises(ValueError):
            validate_team_roster({**base, "host": "bad host!"})
        with pytest.raises(ValueError):
            validate_team_roster({**base, "bots": [{"id": "x"}]})
        with pytest.raises(ValueError):
            validate_team_roster({**base, "bots": [{**base["bots"][0], "extra": 1}]})
        duplicate = {**base["bots"][0]}
        with pytest.raises(ValueError):
            validate_team_roster({**base, "bots": [duplicate, {**duplicate, "id": "default"}]})

    def test_rejects_bad_rows_and_reasons(self, root):
        base = json.loads(json.dumps(self.valid(root)))
        for change in (
            {"id": "../etc"}, {"id": ""}, {"readiness": "healthy"},
            {"readinessReason": "looks fine"}, {"displayName": None},
            {"profilePath": "~/hermes"}, {"lastActivity": "yesterday"},
            {"managed": "yes"}, {"gateway": {"observed": True, "source": "guess"}},
        ):
            row = {**base["bots"][0], **change}
            if change.get("gateway") == {"observed": True, "source": "guess"}:
                row["gateway"] = {**base["bots"][0]["gateway"], "source": "guess"}
            with pytest.raises(ValueError):
                validate_team_roster({**base, "bots": [row]})

    def test_activity_null_needs_reason_and_vice_versa(self, root):
        base = json.loads(json.dumps(self.valid(root)))
        row = {**base["bots"][0]}
        assert row["lastActivity"] is None and row["activityReason"] == "NO_STATE_DB"
        reasonless = {k: v for k, v in row.items() if k != "activityReason"}
        with pytest.raises(ValueError):
            validate_team_roster({**base, "bots": [reasonless]})
        observed = {**row, "lastActivity": "2026-11-09T00:00:00+00:00"}
        with pytest.raises(ValueError):
            validate_team_roster({**base, "bots": [observed]})
        assert validate_team_roster({**base, "bots": [
            {k: v for k, v in observed.items() if k != "activityReason"}]}) is not None


def test_gateway_lock_reader_tolerates_garbage(root):
    directory = make_profile(root, "engineering")
    (directory / "gateway.lock").write_text("{not json", encoding="utf-8")
    assert read_gateway_lock(directory) is None


def test_verify_lock_pid_requires_int_pid():
    assert verify_lock_pid({}, {}) == (False, "LOCK_PID_INVALID")
    assert verify_lock_pid({"pid": "4242"}, {}) == (False, "LOCK_PID_INVALID")
