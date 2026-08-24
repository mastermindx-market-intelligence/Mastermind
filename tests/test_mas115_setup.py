"""MAS-115 operator setup — hermetic privacy and fail-closed tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import nonseat_canary as canary
from scripts import mas115_setup as setup


def test_documented_direct_status_command_bootstraps_repository_imports(tmp_path):
    repo_root = Path(setup.__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["HOME"] = os.fspath(tmp_path)

    completed = subprocess.run(
        [sys.executable, "scripts/mas115_setup.py", "status"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    status = json.loads(completed.stdout)
    assert status["bindings_healthy"] is True
    assert status["chairman_seats_enrolled"] == 0
    assert status["disposable_provision_code"] == "PROVISION_MISSING"


def _mlx(index: int, *, running: bool = True) -> dict:
    digit = str(index)
    return {
        "env_manager": "multilogin",
        "workspace_id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
        "folder_id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
        "profile_id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
        "running": running,
    }


def _selections() -> dict:
    return {
        seat: (_mlx(index), f"https://chatgpt.com/c/seat-{index}")
        for index, seat in enumerate(setup.SEAT_REFS, start=1)
    }


def test_build_enrollment_document_is_exact_three_distinct_seats_and_preserves_unrelated():
    unrelated = sb.new_binding(
        work_ref="WS:OTHER", role="worker", provider="codex",
        locator_kind="codex_session", locator={"session_id": "session-other"},
        observed_at="2026-08-23T12:00:00Z",
        binding_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    old_chatgpt = sb.new_binding(
        work_ref=setup.WORK_REF, role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin", "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "url": "https://chatgpt.com/c/old",
        },
        observed_at="2026-08-22T12:00:00Z", seat_ref="chatgpt1",
        binding_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )
    seat_one = _mlx(1)
    work_specific_chat = sb.new_binding(
        work_ref="WS:OTHER-CHAT", role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "multilogin",
            "folder_id": seat_one["folder_id"],
            "profile_id": seat_one["profile_id"],
            "url": "https://chatgpt.com/c/work-specific",
        },
        observed_at="2026-08-22T12:00:00Z", seat_ref="chatgpt1",
        binding_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )
    doc = setup.build_enrollment_document(
        {"schema": sb.SCHEMA, "bindings": [unrelated, old_chatgpt, work_specific_chat]},
        _selections(), observed_at="2026-08-23T12:00:00Z",
    )
    assert sb.validate_bindings_document(doc) == []
    assert doc["bindings"][0] == unrelated
    chatgpt_rows = [row for row in doc["bindings"] if row["provider"] == "chatgpt"]
    assert {row["seat_ref"] for row in chatgpt_rows} == set(setup.SEAT_REFS)
    assert {row["work_ref"] for row in chatgpt_rows} == {setup.WORK_REF, "WS:OTHER-CHAT"}
    assert {row["role"] for row in chatgpt_rows} == {"ceo"}
    assert work_specific_chat in chatgpt_rows
    anchors = [row for row in chatgpt_rows if row["work_ref"] == setup.WORK_REF]
    assert len(anchors) == 3
    assert all(row["observed_at"] == "2026-08-23T12:00:00Z" for row in anchors)
    assert sb.find_conflicts(doc) == []


def test_build_enrollment_document_refuses_partial_or_duplicate_mapping():
    partial = _selections()
    partial.pop("chatgpt3")
    with pytest.raises(setup.SetupRefusal, match="all three"):
        setup.build_enrollment_document(None, partial, observed_at="2026-08-23T12:00:00Z")

    duplicate = _selections()
    duplicate["chatgpt3"] = duplicate["chatgpt2"]
    with pytest.raises(setup.SetupRefusal, match="cannot be assigned"):
        setup.build_enrollment_document(None, duplicate, observed_at="2026-08-23T12:00:00Z")


def test_reenrollment_refuses_to_orphan_existing_work_chat_on_different_environment():
    conflicting = sb.new_binding(
        work_ref="WS:OTHER-CHAT", role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin", "profile_id": "a" * 24,
            "url": "https://chatgpt.com/c/work-specific",
        },
        observed_at="2026-08-22T12:00:00Z", seat_ref="chatgpt1",
    )
    with pytest.raises(setup.SetupRefusal, match="different environment"):
        setup.build_enrollment_document(
            {"schema": sb.SCHEMA, "bindings": [conflicting]},
            _selections(), observed_at="2026-08-23T12:00:00Z",
        )


@pytest.mark.parametrize(
    "url",
    ["https://chatgpt.com/", "https://chatgpt.com/g/g-p-project/project"],
)
def test_private_url_refuses_non_conversation_addresses(monkeypatch, url):
    monkeypatch.setattr(setup.getpass, "getpass", lambda _prompt: url)
    with pytest.raises(setup.SetupRefusal, match="exact conversation URL"):
        setup._private_url("hidden: ")


def test_disposable_preflight_requires_fresh_exact_three_seat_census_and_refuses_collision():
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    complete = setup.build_enrollment_document(
        None, _selections(), observed_at="2026-08-23T12:00:00Z",
    )
    disposable = _mlx(4, running=False)
    setup.assert_current_nonseat(complete, disposable, now=now)

    partial = dict(complete)
    partial["bindings"] = partial["bindings"][:-1]
    with pytest.raises(setup.SetupRefusal, match="all three current"):
        setup.assert_current_nonseat(partial, disposable, now=now)

    with pytest.raises(setup.SetupRefusal, match="collides"):
        setup.assert_current_nonseat(complete, _mlx(1, running=False), now=now)


def test_candidate_rows_normalizes_only_supported_local_identity_shapes():
    row = _mlx(1)
    census = {
        "multilogin": [{
            "workspace_id": row["workspace_id"], "folder_id": row["folder_id"],
            "profile_id": row["profile_id"], "running": True,
        }],
        "gologin": [{"profile_id": "a" * 24, "running": False}],
    }
    rows = setup._candidate_rows(census)
    assert len(rows) == 2
    assert {row["env_manager"] for row in rows} == {"gologin", "multilogin"}


def test_build_provision_requires_stopped_profile_and_exact_multilogin_core():
    with pytest.raises(setup.SetupRefusal, match="must be stopped"):
        setup.build_provision(_mlx(1, running=True), browser_type="mimic")
    stopped = _mlx(1, running=False)
    with pytest.raises(setup.SetupRefusal, match="positively identified"):
        setup.build_provision(stopped, browser_type=None)
    provision = setup.build_provision(stopped, browser_type="stealthfox")
    assert provision == {
        "schema": canary.PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": stopped["profile_id"],
        "folder_id": stopped["folder_id"],
        "browser_type": "stealthfox",
        "benign_origin": "http://127.0.0.1:7777",
        "disposable_ack": canary.REQUIRED_ACK,
    }


@pytest.mark.parametrize(
    "marker,expected",
    [("Default", "mimic"), ("prefs.js", "stealthfox")],
)
def test_browser_core_detection_reads_shape_not_profile_content(tmp_path, marker, expected):
    row = _mlx(1, running=False)
    profile = tmp_path / row["workspace_id"] / row["folder_id"] / row["profile_id"]
    profile.mkdir(parents=True)
    target = profile / marker
    if marker == "Default":
        target.mkdir()
    else:
        target.write_text("private-content-never-read", encoding="utf-8")
    assert setup._detect_multilogin_browser_type(row, mlx_profiles_root=str(tmp_path)) == expected


def test_credential_setup_is_fixed_native_prompt_with_no_secret_carrier():
    argv = setup.credential_setup_argv("multilogin")
    assert argv[0] == "/usr/bin/security"
    assert argv[-1] == "-w"
    assert argv == [
        "/usr/bin/security", "add-generic-password", "-U",
        "-a", "mastermind-mas115-canary",
        "-s", "mastermind.mas115.multilogin.disposable", "-w",
    ]
    assert not any("token" in value.lower() or "password=" in value.lower() for value in argv)
    with pytest.raises(setup.SetupRefusal, match="GoLogin live lifecycle remains unsupported"):
        setup.credential_setup_argv("gologin")


def test_atomic_private_provision_is_0600_and_canonical(tmp_path):
    path = tmp_path / "private" / "provision.json"
    doc = setup.build_provision(_mlx(1, running=False), browser_type="mimic")
    setup._atomic_private_json(doc, path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == doc
    assert path.read_text(encoding="utf-8") == json.dumps(doc, indent=2, sort_keys=True) + "\n"
