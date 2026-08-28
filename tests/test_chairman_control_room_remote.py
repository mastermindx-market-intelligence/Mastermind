"""Fail-closed contracts for the remote read-only Chairman Control Room."""
from __future__ import annotations

import copy
import collections
import contextlib
import http.client
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane import chairman_control_room as ccr
from control_plane import chairman_control_room_remote as remote
from scripts import chairman_control_room_remote as server


FIXTURES = Path(__file__).parent / "fixtures" / "chairman_control_room"
NOW = "2026-08-28T20:00:00Z"
IDENTITY = remote.BuildIdentity(
    commit="a" * 40,
    tree="b" * 40,
    artifact_digest="sha256:" + "c" * 64,
)
FRESHNESS = {
    remote.SOURCE_AGENT_OS_BRIEF: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_AGENT_OS_STATE: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_ACTIVE_BUILDS: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_EXECUTIVE_RUNTIME: remote.SourceFreshness("fresh", NOW, NOW, None),
}


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def canonical_doc():
    return ccr.compose_control_room(
        inbox=_load("executive_inbox_v2.json"),
        boot_packet=_load("boot_packet_v1.json"),
        active_builds=_load("active_builds_v1.json"),
        agent_os_state=_load("agent_os_state_v1.json"),
        runtime_jobs=_load("runtime_jobs_v1.json"),
        bindings=_load("bindings_v1.json"),
        binding_problems=(),
        generated_at=NOW,
    )


@pytest.fixture
def canonical_macro_active_builds_payload():
    """Match collect_source_snapshot/build_map's aware-UTC isoformat contract."""
    document = _load("active_builds_v1.json")
    document["collected_at"] = datetime(
        2026, 8, 28, 20, tzinfo=timezone.utc
    ).isoformat()
    assert document["collected_at"] == "2026-08-28T20:00:00+00:00"
    return document


def _project(doc):
    return remote.project_remote_document(
        doc, observed_at=NOW, freshness=FRESHNESS, build_identity=IDENTITY
    )


def test_remote_projection_is_closed_and_omits_local_authority(canonical_doc):
    projected = _project(canonical_doc)
    assert projected["schema"] == "mastermind.chairman_control_room_remote.v1"
    assert set(projected) == {
        "schema", "observed_at", "code_identity", "source_freshness",
        "degraded", "attention", "work", "unjoined_open_prs",
    }
    assert set(projected["code_identity"]) == {"commit", "tree", "artifact_digest"}
    assert set(projected["source_freshness"]) == remote.COLLECTOR_SOURCES
    assert all(
        set(row) == {"state", "observed_at", "source_time", "reason"}
        for row in projected["source_freshness"].values()
    )
    assert set(projected["attention"]) == {"chairman", "ceo", "coo"}
    assert all(
        set(item) == {
            "attention_id", "kind", "title", "summary", "workstream",
            "state", "reason_code",
        }
        for bucket in projected["attention"].values()
        for item in bucket
    )
    assert all(
        set(card) == {
            "work_ref", "agent_os", "executive", "github",
            "attention_ids", "disagreements",
        }
        for card in projected["work"]
    )
    assert all(
        card["agent_os"] is None or set(card["agent_os"]) == {
            "workstream", "title", "status", "program", "next_action",
            "state", "reason_code", "reason", "depends_on",
            "unmet_dependencies",
        }
        for card in projected["work"]
    )
    assert all(set(card["executive"]) == {"jobs", "joined_by"} for card in projected["work"])
    assert all(
        set(job) == {"job_id", "status", "workstream"}
        for card in projected["work"] for job in card["executive"]["jobs"]
    )
    assert all(set(card["github"]) == {"prs"} for card in projected["work"])
    assert all(
        set(pr) == {"repo", "number", "url", "title", "branch", "draft", "merge_state"}
        for card in projected["work"] for pr in card["github"]["prs"]
    )
    assert all(
        set(pr) == {"repo", "number", "url", "title", "branch", "draft", "merge_state"}
        for pr in projected["unjoined_open_prs"]
    )
    encoded = json.dumps(projected, sort_keys=True)
    for forbidden in (
        "macro_root", "bindings", "binding_conflicts", "unbound_surfaces",
        "locator", "seat_ref", "argv", "traceback", "/Users/", "/opt/",
        "X-CCR-Token", "@example.com",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda d: d.__setitem__("future", True), "unexpected_keys"),
        (lambda d: d["work"][0].__setitem__("future", True), "unexpected_keys"),
        (lambda d: d.__setitem__("schema", "mastermind.future.v9"), "schema_mismatch"),
        (lambda d: d.__setitem__("work", {}), "invalid_type"),
        (lambda d: d["work"][0].__setitem__("attention_ids", "not-a-list"), "invalid_type"),
        (lambda d: d["work"][0]["executive"]["jobs"][0].__setitem__("status", float("nan")), "non_finite_number"),
        (lambda d: d["work"][0]["executive"]["jobs"][0].__setitem__("status", float("inf")), "non_finite_number"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["host.local"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["/opt/private/file"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["person@example.com"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["provider_session_id=raw-123"]), "sensitive_value"),
        (lambda d: d["degraded"].append("failed at path=/opt/private/file"), "sensitive_value"),
        (lambda d: d["degraded"].append("failed at uri=file:///var/lib/private"), "sensitive_value"),
        (lambda d: d["degraded"].append("failed at root:'/Users/chris/private'"), "sensitive_value"),
    ],
)
def test_remote_projection_rejects_adversarial_canonical_documents(canonical_doc, mutation, code):
    bad = copy.deepcopy(canonical_doc)
    mutation(bad)
    with pytest.raises(remote.RemoteProjectionError) as exc:
        _project(bad)
    assert exc.value.code == code


def test_remote_projection_rejects_bad_freshness_and_identity(canonical_doc):
    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.project_remote_document(
            canonical_doc,
            observed_at=NOW,
            freshness={remote.SOURCE_AGENT_OS_BRIEF: FRESHNESS[remote.SOURCE_AGENT_OS_BRIEF]},
            build_identity=IDENTITY,
        )
    assert exc.value.code == "freshness_sources_mismatch"

    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.project_remote_document(
            canonical_doc,
            observed_at=NOW,
            freshness=FRESHNESS,
            build_identity=remote.BuildIdentity("HEAD", "b" * 40, "sha256:" + "c" * 64),
        )
    assert exc.value.code == "invalid_build_identity"


def test_remote_projection_is_deterministic_and_does_not_mutate_input(canonical_doc):
    before = copy.deepcopy(canonical_doc)
    first = _project(canonical_doc)
    second = _project(canonical_doc)
    assert canonical_doc == before
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )


@pytest.fixture
def collector_config(tmp_path):
    macro = tmp_path / "macro"
    (macro / "scripts").mkdir(parents=True)
    active = _load("active_builds_v1.json")
    active["collected_at"] = NOW
    source_dir = tmp_path / "sources"
    source_dir.mkdir(mode=0o750)
    active_path = source_dir / "project-active-builds.json"
    active_path.write_text(json.dumps(active), encoding="utf-8")
    active_path.chmod(0o640)
    repo_root = tmp_path / "mastermind"
    runtime_db = repo_root / remote.executive_inbox.DB_RELATIVE_PATH
    runtime_db.parent.mkdir(parents=True)
    runtime_db.write_bytes(b"")
    runtime_clock = datetime.fromisoformat(NOW.replace("Z", "+00:00")).timestamp()
    os.utime(runtime_db, (runtime_clock, runtime_clock))
    return remote.CollectorConfig(
        repo_root=repo_root,
        macro_root=macro,
        timeout_seconds=12.0,
        max_output_bytes=4096,
        active_builds_path=active_path,
        active_builds_directory_owner_uid=os.getuid(),
        active_builds_directory_group_gid=os.getgid(),
        active_builds_owner_uid=os.getuid(),
        active_builds_group_gid=os.getgid(),
        environ={},
    )


def _patch_collectors(monkeypatch, canonical_doc):
    packet = _load("boot_packet_v1.json")
    inbox = _load("executive_inbox_v2.json")
    agent_state = _load("agent_os_state_v1.json")
    runtime_jobs = _load("runtime_jobs_v1.json")
    packet_calls = []
    inbox_calls = []

    def fake_packet(**kwargs):
        packet_calls.append(kwargs)
        return packet

    def fake_inbox(**kwargs):
        inbox_calls.append(kwargs)
        assert kwargs["boot_packet"] is packet
        return inbox

    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", fake_packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", fake_inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (agent_state, None))
    monkeypatch.setattr(remote.ccr, "_read_runtime_jobs", lambda _: (runtime_jobs, None))
    return packet_calls, inbox_calls


def test_collector_routes_agent_os_through_bounded_runner_and_injects_fixed_artifact(
    monkeypatch, collector_config, canonical_doc
):
    packet_calls, inbox_calls = _patch_collectors(monkeypatch, canonical_doc)
    bounded_runner = object()
    collector_config.runner = bounded_runner
    compose_calls = []
    monkeypatch.setattr(remote.ccr, "build_control_room", lambda **_: pytest.fail("forbidden"))
    monkeypatch.setattr(
        remote.ccr,
        "_read_active_builds",
        lambda *_: pytest.fail("stale active-build file must not be read"),
    )
    monkeypatch.setattr(
        remote.ccr,
        "compose_control_room",
        lambda **kwargs: compose_calls.append(kwargs) or canonical_doc,
    )

    inputs = remote.collect_once(collector_config, now=NOW)
    projected = remote.compose_collected(inputs, IDENTITY)

    assert len(packet_calls) == len(inbox_calls) == 1
    assert packet_calls[0]["runner"] is bounded_runner
    assert packet_calls[0]["max_output_bytes"] == collector_config.max_output_bytes
    assert len(compose_calls) == 1
    assert compose_calls[0]["active_builds"]["schema"] == "project_active_builds.v1"
    assert compose_calls[0]["active_builds"]["collected_at"] == NOW
    assert compose_calls[0]["bindings"] is None
    assert compose_calls[0]["binding_problems"] == ()
    assert projected["schema"] == remote.REMOTE_SCHEMA


@pytest.mark.parametrize(
    ("source_time", "state", "reported_source_time", "reason"),
    [
        ("2026-08-28T19:45:00Z", "fresh", "2026-08-28T19:45:00Z", None),
        ("2026-08-28T19:45:00+00:00", "fresh", "2026-08-28T19:45:00Z", None),
        ("2026-08-28T19:44:59Z", "stale", "2026-08-28T19:44:59Z", "active_builds_source_over_age"),
        (None, "unavailable", None, "active_builds_source_time_missing"),
        ("not-a-time", "unavailable", None, "active_builds_source_time_malformed"),
        ("2026-08-28T19:45:00-07:00", "unavailable", None, "active_builds_source_time_non_utc"),
        ("2026-08-28T19:45:00", "unavailable", None, "active_builds_source_time_non_utc"),
        ("2026-08-28T20:00:01Z", "unavailable", "2026-08-28T20:00:01Z", "active_builds_source_time_future"),
    ],
)
def test_source_freshness_uses_exact_utc_source_clock_boundary(
    source_time, state, reported_source_time, reason
):
    entry = remote.classify_source_freshness(
        "active_builds",
        present=True,
        observed_at=NOW,
        source_time=source_time,
        stale_after_seconds=900.0,
    )
    assert entry == remote.SourceFreshness(state, NOW, reported_source_time, reason)


def test_reader_accepts_canonical_macro_builder_utc_shape(
    collector_config, canonical_macro_active_builds_payload
):
    collector_config.active_builds_path.write_text(
        json.dumps(canonical_macro_active_builds_payload), encoding="utf-8"
    )
    collector_config.active_builds_path.chmod(0o640)

    loaded, freshness = remote.read_active_builds_artifact(
        collector_config, observed_at=NOW
    )

    assert loaded == canonical_macro_active_builds_payload
    assert freshness == remote.SourceFreshness("fresh", NOW, NOW, None)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (b"not-json", "active_builds_invalid_json"),
        (b'{"schema":"project_active_builds.v1","schema":"duplicate"}', "active_builds_duplicate_json_key"),
        (b'{"schema":"project_active_builds.v1","collected_at":"2026-08-28T20:00:00Z","n":NaN}', "active_builds_non_finite_number"),
        (b'{"schema":"wrong","collected_at":"2026-08-28T20:00:00Z"}', "active_builds_schema_mismatch"),
    ],
)
def test_malformed_active_build_artifact_is_typed_unavailable_not_generation_fatal(
    monkeypatch, collector_config, canonical_doc, payload, reason
):
    _patch_collectors(monkeypatch, canonical_doc)
    collector_config.active_builds_path.write_bytes(payload)
    collector_config.active_builds_path.chmod(0o640)
    inputs = remote.collect_once(collector_config, now=NOW)
    assert inputs.active_builds is None
    assert inputs.freshness[remote.SOURCE_ACTIVE_BUILDS] == remote.SourceFreshness(
        "unavailable", NOW, None, reason
    )
    assert inputs.agent_os_state is not None
    assert inputs.runtime_jobs is not None


def test_unavailable_source_clocks_omit_only_their_documents_from_composition(
    monkeypatch, collector_config
):
    packet = _load("boot_packet_v1.json")
    packet["brief"]["generated_at"] = "2026-08-28T20:00:01Z"
    inbox = _load("executive_inbox_v2.json")
    agent_state = _load("agent_os_state_v1.json")
    agent_state["generated_at"] = "2026-08-28T20:00:01Z"
    runtime_jobs = _load("runtime_jobs_v1.json")
    runtime_db = collector_config.repo_root / remote.executive_inbox.DB_RELATIVE_PATH
    future_clock = datetime(2026, 8, 28, 20, 0, 1, tzinfo=timezone.utc).timestamp()
    os.utime(runtime_db, (future_clock, future_clock))

    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", lambda **_: packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", lambda **_: inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (agent_state, None))
    monkeypatch.setattr(remote.ccr, "_read_runtime_jobs", lambda _: (runtime_jobs, None))

    inputs = remote.collect_once(collector_config, now=NOW)

    assert inputs.inbox == inbox
    assert inputs.inbox is not inbox
    assert inputs.boot_packet is not packet
    assert inputs.boot_packet["brief"] is None
    assert packet["brief"] is not None
    assert inputs.agent_os_state is None
    assert inputs.runtime_jobs is None
    assert inputs.active_builds is not None
    assert {
        source: inputs.freshness[source].reason
        for source in (
            remote.SOURCE_AGENT_OS_BRIEF,
            remote.SOURCE_AGENT_OS_STATE,
            remote.SOURCE_EXECUTIVE_RUNTIME,
        )
    } == {
        remote.SOURCE_AGENT_OS_BRIEF: "agent_os_brief_source_time_future",
        remote.SOURCE_AGENT_OS_STATE: "agent_os_state_source_time_future",
        remote.SOURCE_EXECUTIVE_RUNTIME: "executive_runtime_source_time_future",
    }


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing", "active_builds_not_found"),
        ("symlink", "active_builds_path_unsafe"),
        ("hardlink", "active_builds_hardlink_forbidden"),
        ("writable", "active_builds_mode_unsafe"),
        ("owner", "active_builds_owner_mismatch"),
        ("group", "active_builds_group_mismatch"),
        ("too_large", "active_builds_too_large"),
        ("wrong_mode", "active_builds_mode_unsafe"),
        ("parent_mode", "active_builds_path_unsafe"),
    ],
)
def test_active_build_artifact_file_boundary_fails_closed(
    monkeypatch, collector_config, canonical_doc, tmp_path, mutation, reason
):
    _patch_collectors(monkeypatch, canonical_doc)
    path = collector_config.active_builds_path
    if mutation == "missing":
        path.unlink()
    elif mutation == "symlink":
        target = tmp_path / "target.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    elif mutation == "hardlink":
        os.link(path, tmp_path / "second-link.json")
    elif mutation == "writable":
        path.chmod(0o660)
    elif mutation == "owner":
        collector_config.active_builds_owner_uid = os.getuid() + 1
    elif mutation == "group":
        collector_config.active_builds_group_gid = os.getgid() + 1
    elif mutation == "too_large":
        collector_config.max_output_bytes = 8
    elif mutation == "wrong_mode":
        path.chmod(0o600)
    elif mutation == "parent_mode":
        path.parent.chmod(0o700)
    inputs = remote.collect_once(collector_config, now=NOW)
    assert inputs.active_builds is None
    assert inputs.freshness[remote.SOURCE_ACTIVE_BUILDS].reason == reason


def test_brief_freshness_uses_brief_clock_not_wrapper_clock(
    monkeypatch, collector_config, canonical_doc
):
    packet = _load("boot_packet_v1.json")
    packet["generated_at"] = NOW
    packet["brief"]["generated_at"] = "2026-08-28T19:44:59Z"
    inbox = _load("executive_inbox_v2.json")
    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", lambda **_: packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", lambda **_: inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (None, "missing"))
    monkeypatch.setattr(remote.ccr, "_read_runtime_jobs", lambda _: (None, "missing"))
    inputs = remote.collect_once(collector_config, now=NOW)
    assert inputs.freshness[remote.SOURCE_AGENT_OS_BRIEF].source_time == "2026-08-28T19:44:59Z"
    assert inputs.freshness[remote.SOURCE_AGENT_OS_BRIEF].state == "stale"


def test_active_build_artifact_age_and_future_control_document_admission(collector_config):
    document = json.loads(collector_config.active_builds_path.read_text(encoding="utf-8"))
    document["collected_at"] = "2026-08-28T19:44:59Z"
    collector_config.active_builds_path.write_text(json.dumps(document), encoding="utf-8")
    collector_config.active_builds_path.chmod(0o640)
    os.utime(collector_config.active_builds_path, (2_000_000_000, 2_000_000_000))
    loaded, freshness = remote.read_active_builds_artifact(
        collector_config, observed_at=NOW
    )
    assert loaded is not None
    assert freshness.state == "stale"
    assert freshness.reason == "active_builds_source_over_age"

    document["collected_at"] = "2026-08-28T20:00:01Z"
    collector_config.active_builds_path.write_text(json.dumps(document), encoding="utf-8")
    collector_config.active_builds_path.chmod(0o640)
    loaded, freshness = remote.read_active_builds_artifact(
        collector_config, observed_at=NOW
    )
    assert loaded is None
    assert freshness.state == "unavailable"
    assert freshness.reason == "active_builds_source_time_future"


def test_active_build_artifact_refuses_platform_without_nofollow(
    monkeypatch, collector_config
):
    monkeypatch.delattr(remote.os, "O_NOFOLLOW")
    loaded, freshness = remote.read_active_builds_artifact(
        collector_config, observed_at=NOW
    )
    assert loaded is None
    assert freshness.reason == "active_builds_nofollow_unavailable"


def test_active_build_artifact_inode_swap_between_lstat_and_open_is_refused(
    monkeypatch, collector_config, tmp_path
):
    path = collector_config.active_builds_path
    original = tmp_path / "original.json"
    real_open = os.open

    def swapping_open(candidate, flags, *args, **kwargs):
        if Path(candidate) == path:
            path.replace(original)
            path.write_bytes(original.read_bytes())
            path.chmod(0o640)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(remote.os, "open", swapping_open)
    loaded, freshness = remote.read_active_builds_artifact(
        collector_config, observed_at=NOW
    )
    assert loaded is None
    assert freshness.reason == "active_builds_path_changed"


def test_post_success_active_build_failure_publishes_current_other_sources(
    monkeypatch, collector_config, canonical_doc
):
    packet = _load("boot_packet_v1.json")
    inbox = _load("executive_inbox_v2.json")
    agent_state = _load("agent_os_state_v1.json")
    runtime_jobs = _load("runtime_jobs_v1.json")
    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", lambda **_: packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", lambda **_: inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (agent_state, None))
    monkeypatch.setattr(remote.ccr, "_read_runtime_jobs", lambda _: (runtime_jobs, None))
    monkeypatch.setattr(
        remote,
        "compose_collected",
        lambda inputs, _identity: {
            "active_available": inputs.active_builds is not None,
            "agent_title": inputs.agent_os_state["workstreams"][0]["title"],
        },
    )
    monotonic = [1.0]
    cache = remote.RemoteStateCache(
        collector_config,
        IDENTITY,
        monotonic_fn=lambda: monotonic[0],
        now_fn=lambda: NOW,
    )
    assert cache.refresh() is True
    assert cache.snapshot() == {
        "active_available": True,
        "agent_title": "Alpha One Rollout",
    }

    collector_config.active_builds_path.write_text("not-json", encoding="utf-8")
    collector_config.active_builds_path.chmod(0o640)
    agent_state["workstreams"][0]["title"] = "Current Agent OS Title"
    monotonic[0] = 2.0
    assert cache.refresh() is True
    assert cache.snapshot() == {
        "active_available": False,
        "agent_title": "Current Agent OS Title",
    }


def test_bounded_runner_kills_and_reaps_continuous_stdout_stderr_and_timeout(tmp_path):
    for stream in ("stdout", "stderr"):
        fd = "1" if stream == "stdout" else "2"
        started = time.monotonic()
        result = remote.default_runner(
            [sys.executable, "-c", f'import os\nwhile True: os.write({fd}, b"x" * 4096)'],
            cwd=tmp_path,
            timeout=5.0,
            max_bytes=1024,
        )
        assert time.monotonic() - started < 2.0
        assert result["limit_exceeded"] is True
        assert result["timed_out"] is False
        assert result["code"] is not None
        assert len(result[stream].encode("utf-8")) <= 1024

    started = time.monotonic()
    result = remote.default_runner(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        timeout=0.2,
        max_bytes=1024,
    )
    assert time.monotonic() - started < 2.0
    assert result["timed_out"] is True
    assert result["limit_exceeded"] is False
    assert result["code"] is not None


def test_bounded_runner_cleanup_never_uses_unbounded_wait_on_unkillable_fake_proc(
    monkeypatch,
):
    class FakeProc:
        pid = 42
        returncode = None

        def __init__(self):
            self.wait_timeouts = []
            self.kill_calls = 0

        def poll(self):
            return None

        def kill(self):
            self.kill_calls += 1

        def wait(self, *, timeout):
            self.wait_timeouts.append(timeout)
            raise remote.subprocess.TimeoutExpired(["fake"], timeout)

    proc = FakeProc()
    monkeypatch.setattr(remote.os, "killpg", lambda *_args: None)

    assert remote._terminate_process_group(proc) is False
    assert proc.wait_timeouts == [0.5, 0.5]
    assert proc.kill_calls == 1


def test_bounded_runner_kills_process_group_when_leader_exits_before_descendant(
    tmp_path
):
    script = (
        "import subprocess,sys\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "stdout=sys.stdout,stderr=sys.stderr)\n"
        "print(child.pid,flush=True)\n"
    )
    child_pid = None
    try:
        started = time.monotonic()
        result = remote.default_runner(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            timeout=1.0,
            max_bytes=1024,
        )
        assert time.monotonic() - started < 2.0
        child_pid = int(result["stdout"].strip())
        assert result["timed_out"] is True
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                pytest.fail("bounded runner left its descendant alive")
            time.sleep(0.01)
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, remote.signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_bounded_runner_kills_quiet_descendant_after_clean_leader_exit(tmp_path):
    script = (
        "import subprocess,sys\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "print(child.pid,flush=True)\n"
    )
    child_pid = None
    try:
        result = remote.default_runner(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            timeout=2.0,
            max_bytes=1024,
        )
        child_pid = int(result["stdout"].strip())
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                pytest.fail("bounded runner left its quiet descendant alive")
            time.sleep(0.01)
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, remote.signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_absent_runtime_database_is_degraded_and_never_created(
    monkeypatch, collector_config, canonical_doc
):
    packet = _load("boot_packet_v1.json")
    inbox = _load("executive_inbox_v2.json")
    monkeypatch.setattr(remote.ceo_boot_packet, "build_packet", lambda **_: packet)
    monkeypatch.setattr(remote.executive_inbox, "build_inbox", lambda **_: inbox)
    monkeypatch.setattr(remote.ccr, "_read_agent_os_state", lambda _: (None, "missing"))
    db = collector_config.repo_root / remote.executive_inbox.DB_RELATIVE_PATH
    db.unlink()
    assert not db.exists()
    inputs = remote.collect_once(collector_config, now=NOW)
    assert not db.exists()
    assert inputs.runtime_jobs is None
    assert inputs.freshness[remote.SOURCE_EXECUTIVE_RUNTIME].state == "unavailable"


def test_cache_starts_empty_single_flights_and_expires_last_good(monkeypatch, collector_config):
    assert collector_config.interval_seconds == 300.0
    assert collector_config.stale_after_seconds == 900.0
    entered = threading.Event()
    release = threading.Event()
    calls = []
    monotonic = [100.0]
    document = {"schema": remote.REMOTE_SCHEMA, "value": "accepted"}

    def collect(_config, *, now):
        calls.append(now)
        entered.set()
        release.wait(timeout=5)
        return object()

    monkeypatch.setattr(remote, "collect_once", collect)
    monkeypatch.setattr(remote, "compose_collected", lambda *_: document)
    cache = remote.RemoteStateCache(
        collector_config,
        IDENTITY,
        monotonic_fn=lambda: monotonic[0],
        now_fn=lambda: NOW,
    )
    assert cache.snapshot() is None
    thread = threading.Thread(target=cache.refresh)
    thread.start()
    assert entered.wait(timeout=5)
    assert cache.refresh() is False
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(calls) == 1
    assert cache.snapshot() == document

    monotonic[0] = 1000.0
    assert cache.snapshot() == document
    monotonic[0] = 1000.0001
    assert cache.snapshot() is None
    assert remote.RemoteStateCache(collector_config, IDENTITY).snapshot() is None


def test_refresh_failure_preserves_only_bounded_last_good(monkeypatch, collector_config):
    monotonic = [10.0]
    outcomes = [object(), remote.RemoteProjectionError("refresh_failed")]
    monkeypatch.setattr(
        remote,
        "collect_once",
        lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(outcomes.pop(0))
            if isinstance(outcomes[0], Exception)
            else outcomes.pop(0)
        ),
    )
    monkeypatch.setattr(remote, "compose_collected", lambda *_: {"ok": "last-good"})
    cache = remote.RemoteStateCache(
        collector_config, IDENTITY, monotonic_fn=lambda: monotonic[0], now_fn=lambda: NOW
    )
    assert cache.refresh() is True
    monotonic[0] = 20.0
    assert cache.refresh() is False
    assert cache.last_error == "refresh_failed"
    assert cache.snapshot() == {"ok": "last-good"}
    monotonic[0] = 911.0
    assert cache.snapshot() is None


def test_snapshot_is_memory_only(monkeypatch, collector_config):
    cache = remote.RemoteStateCache(collector_config, IDENTITY)
    monkeypatch.setattr(Path, "read_bytes", lambda *_: pytest.fail("no filesystem reads"))
    monkeypatch.setattr(remote.subprocess, "run", lambda *_a, **_k: pytest.fail("no subprocess"))
    assert cache.snapshot() is None


class StaticCache:
    def __init__(self, document=None):
        self.document = document
        self.snapshot_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return copy.deepcopy(self.document)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path):
        super().__init__("localhost", timeout=5)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(os.fspath(self.socket_path))


@contextlib.contextmanager
def _running_remote_server(tmp_path, *, document=None):
    static = tmp_path / "static"
    static.mkdir()
    (static / "remote.html").write_text("<html>remote</html>", encoding="utf-8")
    (static / "control_room.css").write_text("body{}", encoding="utf-8")
    (static / "control_room.js").write_text("/* remote */", encoding="utf-8")
    # Darwin's AF_UNIX pathname ceiling is shorter than pytest's nested tmp
    # fixture path. Keep only the socket seam in a separately owned short dir.
    socket_root = Path(tempfile.mkdtemp(prefix="ccr-remote-", dir="/tmp"))
    socket_path = socket_root / "remote.sock"
    cache = StaticCache(document)
    config = server.RemoteServerConfig(
        socket_path=socket_path,
        static_dir=static,
        cache=cache,
        caddy_gid=os.getgid(),
        service_uid=os.getuid(),
        events=collections.deque(maxlen=8),
    )
    httpd = server.ControlRoomUnixServer(
        socket_path, server.RemoteControlRoomHandler, config
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, socket_path, cache
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        shutil.rmtree(socket_root)


def _unix_request(socket_path, method, path, headers=None):
    conn = UnixHTTPConnection(socket_path)
    try:
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def test_remote_cli_has_no_tcp_or_socket_override():
    parser = server.build_parser()
    args = parser.parse_args([
        "--repo-root", "/release", "--macro-root", "/macro",
        "--expected-commit", "a" * 40, "--build-metadata", "/release/build.json",
        "--interval-seconds", "300", "--stale-after-seconds", "900",
        "--timeout-seconds", "10", "--max-output-bytes", "4096",
    ])
    assert args.expected_commit == "a" * 40
    for option in ("--host", "--port", "--bind", "--socket", "--active-builds-path"):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([option, "value"])
        assert exc.value.code == 2


def test_service_wires_fixed_root_caddy_artifact_boundary(monkeypatch, tmp_path):
    captured = {}

    class Cache:
        def __init__(self, collector, identity):
            captured["collector"] = collector
            captured["identity"] = identity

        def run(self, _stop):
            return None

    class Thread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

        def join(self, **_kwargs):
            pass

    class Httpd:
        def __init__(self, _socket, _handler, config):
            captured["server_config"] = config

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    caddy_gid = 456
    monkeypatch.setattr(server, "_load_build_identity", lambda *_: IDENTITY)
    monkeypatch.setattr(server.grp, "getgrnam", lambda name: type("G", (), {"gr_gid": caddy_gid})() if name == "caddy" else None)
    monkeypatch.setattr(server.remote, "RemoteStateCache", Cache)
    monkeypatch.setattr(server.threading, "Thread", Thread)
    monkeypatch.setattr(server, "ControlRoomUnixServer", Httpd)
    monkeypatch.setattr(server.os, "geteuid", lambda: 497)

    assert server.main([
        "--repo-root", os.fspath(tmp_path / "release"),
        "--macro-root", os.fspath(tmp_path / "macro"),
        "--expected-commit", "a" * 40,
        "--build-metadata", os.fspath(tmp_path / "release/control_room_build.json"),
    ]) == 0

    collector = captured["collector"]
    assert collector.active_builds_path == remote.ACTIVE_BUILDS_ARTIFACT
    assert collector.active_builds_directory_owner_uid == 0
    assert collector.active_builds_owner_uid == 0
    assert collector.active_builds_directory_group_gid == caddy_gid
    assert collector.active_builds_group_gid == caddy_gid
    assert captured["server_config"].caddy_gid == caddy_gid


def test_request_event_sink_is_absent_by_default_and_bounded_when_injected(tmp_path):
    config = server.RemoteServerConfig(
        socket_path=tmp_path / "unused.sock",
        static_dir=tmp_path,
        cache=StaticCache(),
        caddy_gid=os.getgid(),
        service_uid=os.getuid(),
    )
    assert config.events is None
    with pytest.raises(ValueError, match="bounded test-only event sink"):
        server.RemoteServerConfig(
            socket_path=tmp_path / "unbounded.sock",
            static_dir=tmp_path,
            cache=StaticCache(),
            caddy_gid=os.getgid(),
            service_uid=os.getuid(),
            events=[],
        )

    with _running_remote_server(tmp_path, document={"ok": True}) as (
        httpd, sock, _cache
    ):
        for _ in range(20):
            assert _unix_request(sock, "GET", "/healthz")[0] == 200
        assert len(httpd.config.events) == 8


def test_remote_server_is_unix_only_with_restricted_metadata(tmp_path):
    with _running_remote_server(tmp_path) as (httpd, socket_path, _cache):
        assert httpd.address_family == socket.AF_UNIX
        assert stat.S_IMODE(socket_path.parent.stat().st_mode) == 0o750
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o660
        assert socket_path.stat().st_gid == os.getgid()
    assert not socket_path.exists()


def test_fixed_get_head_health_and_state_routes(tmp_path):
    document = {"schema": remote.REMOTE_SCHEMA, "observed_at": NOW}
    with _running_remote_server(tmp_path, document=document) as (_httpd, sock, cache):
        for path in ("/", "/static/control_room.css", "/static/control_room.js"):
            get_status, get_headers, get_body = _unix_request(sock, "GET", path)
            head_status, head_headers, head_body = _unix_request(sock, "HEAD", path)
            assert get_status == head_status == 200
            assert get_headers["Content-Length"] == head_headers["Content-Length"]
            assert get_body
            assert head_body == b""

        status, headers, body = _unix_request(sock, "GET", "/healthz")
        assert status == 200
        assert headers["Content-Type"] == "text/plain; charset=utf-8"
        assert body == b"ok\n"
        assert cache.snapshot_calls == 0

        status, _headers, body = _unix_request(sock, "GET", "/api/state")
        assert status == 200
        assert json.loads(body) == {"ok": True, "control_room": document}


def test_state_is_typed_unavailable_before_first_success(tmp_path):
    with _running_remote_server(tmp_path) as (_httpd, sock, _cache):
        status, _headers, body = _unix_request(sock, "GET", "/api/state")
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": {"code": "state_unavailable"}}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_methods_are_closed_before_cache(method, tmp_path):
    with _running_remote_server(tmp_path, document={"secret": "must-not-read"}) as (
        _httpd, sock, cache
    ):
        status, headers, _body = _unix_request(sock, method, "/api/state")
    assert status == 405
    assert headers["Allow"] == "GET, HEAD"
    assert cache.snapshot_calls == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/open", "/api/bind", "/api/unbind", "/api/refresh-builds",
        "/api/state?x=1", "//api/state", "/x/../api/state", "/%2e%2e/api/state",
        "/static%2fcontrol_room.js", "/static%252fcontrol_room.js", "/x%00",
        "/static\\control_room.js", "/bad%zz", "/wild/*",
    ],
)
def test_unexpected_or_ambiguous_read_paths_fail_before_cache(path, tmp_path):
    with _running_remote_server(tmp_path, document={"ok": "hidden"}) as (
        _httpd, sock, cache
    ):
        status, _headers, _body = _unix_request(sock, "GET", path)
    assert status in (400, 404)
    assert cache.snapshot_calls == 0


def test_browser_credentials_and_forged_headers_change_no_decision_or_log(tmp_path):
    document = {"schema": remote.REMOTE_SCHEMA}
    with _running_remote_server(tmp_path, document=document) as (httpd, sock, _cache):
        baseline = _unix_request(sock, "GET", "/api/state")
        forged = _unix_request(
            sock,
            "GET",
            "/api/state",
            headers={
                "X-CCR-Token": "secret-nonce", "Cookie": "secret-cookie",
                "Authorization": "Bearer secret", "Host": "evil.example",
                "Origin": "https://evil.example", "X-Forwarded-User": "admin",
            },
        )
        events = list(httpd.config.events)
    assert forged == baseline
    encoded = json.dumps(events)
    for secret in ("secret-nonce", "secret-cookie", "Bearer secret", "evil.example", "admin"):
        assert secret not in encoded
