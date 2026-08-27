from __future__ import annotations

import asyncio
import importlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.slack_executive import slack_web_api


WORKSPACE = "T0BRD2AQXQV"
CHANNEL = "C0BSGABKBFY"
BOT = "U0C1BOTFIX1"
TOKEN = "INERT-C1-NATIVE-TOKEN"
SCOPES = ("chat:write", "groups:history")


def _module():
    try:
        return importlib.import_module("ops.executive_os.c1_relay_enrollment")
    except ModuleNotFoundError:
        pytest.fail("native C1 enrollment helper is not implemented")


class _Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    async def request(self, **kwargs):
        self.calls.append(dict(kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def aclose(self):
        self.closed = True


class _LineOnlyInput(io.BytesIO):
    def read(self, *args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("native token input must use readline, not read-to-EOF")


def _response(path: str, payload, *, scopes=None):
    headers = {"content-type": "application/json; charset=utf-8"}
    if scopes is not None:
        headers["x-oauth-scopes"] = ",".join(scopes)
    return slack_web_api.SlackHttpResponse(
        status_code=200,
        final_url=slack_web_api.SLACK_API_ROOT + path,
        headers=headers,
        body=json.dumps(payload).encode("utf-8"),
    )


def test_parser_never_accepts_token_or_channel_workspace_overrides():
    enrollment = _module()
    parser = enrollment.build_parser()
    parsed = parser.parse_args(["enroll", "--expected-bot-user-id", BOT])
    assert parsed.command == "enroll"
    assert parsed.expected_bot_user_id == BOT

    options = {
        option
        for action in parser._actions
        for option in getattr(action, "option_strings", ())
    }
    for subparser in parser._subparsers._group_actions[0].choices.values():
        options |= {
            option
            for action in subparser._actions
            for option in getattr(action, "option_strings", ())
        }
    assert "--expected-bot-user-id" in options
    assert "--token" not in options
    assert "--channel" not in options
    assert "--workspace" not in options
    assert "--config" not in options


def test_token_is_read_only_from_one_bounded_line():
    enrollment = _module()
    stream = _LineOnlyInput((TOKEN + "\nSECOND-LINE-MUST-NOT-BE-CONSUMED\n").encode())
    assert enrollment.read_token_from_stdin(stream) == TOKEN
    assert stream.readline() == b"SECOND-LINE-MUST-NOT-BE-CONSUMED\n"

    with pytest.raises(enrollment.C1EnrollmentError, match="C1_ENROLLMENT_INPUT_REFUSED"):
        enrollment.read_token_from_stdin(io.BytesIO(b""))
    with pytest.raises(enrollment.C1EnrollmentError, match="C1_ENROLLMENT_INPUT_REFUSED"):
        enrollment.read_token_from_stdin(io.BytesIO(b"contains whitespace\n"))


def test_config_document_is_exact_fixed_policy_and_release_bound():
    enrollment = _module()
    release_sha = "a" * 40
    document = enrollment.build_config_document(
        bot_user_id=BOT,
        release_sha=release_sha,
    )

    assert document == {
        "schema": "mastermind.sol_state_relay_config.v1",
        "executive_socket": "/var/run/mastermind-executive/ceo-ingress.sock",
        "slack_workspace_id": WORKSPACE,
        "slack_channel_id": CHANNEL,
        "slack_bot_user_id": BOT,
        "slack_token_file": "/Library/Application Support/MastermindExecutive/config/sol-state-relay.token",
        "poll_seconds": 30,
        "heartbeat_seconds": 60,
        "max_executive_age_seconds": 120,
        "relay_version": release_sha,
    }


def test_qualify_token_proves_identity_scopes_and_private_channel_access():
    enrollment = _module()
    identity = _Transport(
        [
            _response(
                "auth.test",
                {"ok": True, "team_id": WORKSPACE, "user_id": BOT},
                scopes=SCOPES,
            )
        ]
    )
    history = _Transport(
        [
            _response(
                "conversations.history",
                {
                    "ok": True,
                    "messages": [],
                    "has_more": False,
                    "response_metadata": {"next_cursor": ""},
                },
            )
        ]
    )

    receipt = asyncio.run(
        enrollment.qualify_token(
            token=TOKEN,
            bot_user_id=BOT,
            identity_transport=identity,
            history_transport=history,
        )
    )

    assert receipt == {
        "bot_user_id": BOT,
        "channel_id": CHANNEL,
        "scopes": list(SCOPES),
        "workspace_id": WORKSPACE,
    }
    assert identity.calls == [{"method": "POST", "path": "auth.test", "token": TOKEN}]
    assert history.calls == [
        {
            "method": "GET",
            "path": "conversations.history",
            "token": TOKEN,
            "query": {"channel": CHANNEL, "limit": "1"},
            "json_body": None,
        }
    ]


def test_validate_host_relay_groups_reuses_runtime_allowlist(monkeypatch):
    enrollment = _module()
    reviewed = {
        452: "_mastermind_sol_relay",
        12: "everyone",
        61: "localaccounts",
        100: "_lpoperator",
        396: "com.apple.access_disabled",
    }
    monkeypatch.setattr(enrollment.os, "getgrouplist", lambda _name, _gid: list(reviewed))
    monkeypatch.setattr(
        enrollment.grp,
        "getgrgid",
        lambda gid: SimpleNamespace(gr_name=reviewed[gid]),
    )
    enrollment.validate_host_relay_groups()

    drifted = dict(reviewed)
    drifted[80] = "admin"
    monkeypatch.setattr(enrollment.os, "getgrouplist", lambda _name, _gid: list(drifted))
    monkeypatch.setattr(
        enrollment.grp,
        "getgrgid",
        lambda gid: SimpleNamespace(gr_name=drifted[gid]),
    )
    with pytest.raises(enrollment.C1EnrollmentError, match="C1_ENROLLMENT_HOST_REFUSED"):
        enrollment.validate_host_relay_groups()


def test_write_new_private_file_is_no_overwrite_exact_metadata(tmp_path: Path):
    enrollment = _module()
    path = tmp_path / "private"
    enrollment.write_new_private_file(
        path,
        b"payload\n",
        uid=os.geteuid(),
        gid=os.getegid(),
        mode=0o400,
    )
    info = path.stat()
    assert path.read_bytes() == b"payload\n"
    assert info.st_uid == os.geteuid()
    assert info.st_gid == os.getegid()
    assert info.st_mode & 0o777 == 0o400
    assert info.st_nlink == 1

    with pytest.raises(enrollment.C1EnrollmentError, match="C1_ENROLLMENT_COLLISION"):
        enrollment.write_new_private_file(
            path,
            b"replacement\n",
            uid=os.geteuid(),
            gid=os.getegid(),
            mode=0o400,
        )


def _install_enrollment_fakes(monkeypatch, enrollment, *, present=None):
    release_sha = "b" * 40
    present_paths = set(present or ())
    writes = []
    qualifications = []

    monkeypatch.setattr(enrollment, "_assert_host_prepared", lambda: release_sha)
    monkeypatch.setattr(enrollment, "_path_present", lambda path: path in present_paths)

    async def qualify_token(*, token, bot_user_id, **_kwargs):
        qualifications.append((token, bot_user_id))
        return {
            "bot_user_id": bot_user_id,
            "channel_id": CHANNEL,
            "scopes": list(SCOPES),
            "workspace_id": WORKSPACE,
        }

    def write_new_private_file(path, payload, *, uid, gid, mode):
        assert path not in present_paths
        writes.append((path, payload, uid, gid, mode))
        present_paths.add(path)

    monkeypatch.setattr(enrollment, "qualify_token", qualify_token)
    monkeypatch.setattr(enrollment, "write_new_private_file", write_new_private_file)
    return release_sha, present_paths, writes, qualifications


def test_enroll_qualifies_before_committing_token_then_config(monkeypatch):
    enrollment = _module()
    release_sha, _present, writes, qualifications = _install_enrollment_fakes(
        monkeypatch, enrollment
    )
    monkeypatch.setattr(
        enrollment.c1_runtime,
        "load_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            slack_bot_user_id=BOT,
            relay_version=release_sha,
        ),
    )

    receipt = asyncio.run(
        enrollment._enroll(  # noqa: SLF001 - adversarial state-machine test
            bot_user_id=BOT,
            stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
        )
    )

    assert qualifications == [(TOKEN, BOT)]
    assert [row[0] for row in writes] == [
        enrollment.c1_runtime.TOKEN_PATH,
        enrollment.c1_runtime.CONFIG_PATH,
    ]
    token_write, config_write = writes
    assert token_write[1:] == ((TOKEN + "\n").encode("ascii"), 452, 452, 0o400)
    config_doc = json.loads(config_write[1])
    assert config_doc["slack_bot_user_id"] == BOT
    assert config_doc["relay_version"] == release_sha
    assert config_write[2:] == (0, 452, 0o440)
    assert receipt["action"] == "enrolled"
    assert receipt["release_sha"] == release_sha
    assert TOKEN not in json.dumps(receipt)


def test_token_only_crash_state_requires_resume_and_never_blind_reenroll(monkeypatch):
    enrollment = _module()
    token_path = enrollment.c1_runtime.TOKEN_PATH
    release_sha, _present, writes, qualifications = _install_enrollment_fakes(
        monkeypatch,
        enrollment,
        present={token_path},
    )
    monkeypatch.setattr(enrollment, "_existing_token", lambda: TOKEN)
    monkeypatch.setattr(
        enrollment.c1_runtime,
        "load_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            slack_bot_user_id=BOT,
            relay_version=release_sha,
        ),
    )

    with pytest.raises(enrollment.C1EnrollmentError, match="C1_ENROLLMENT_COLLISION"):
        asyncio.run(
            enrollment._enroll(  # noqa: SLF001
                bot_user_id=BOT,
                stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
            )
        )

    receipt = asyncio.run(enrollment._resume(bot_user_id=BOT))  # noqa: SLF001
    assert qualifications == [(TOKEN, BOT)]
    assert [row[0] for row in writes] == [enrollment.c1_runtime.CONFIG_PATH]
    assert receipt["action"] == "resumed"
    assert receipt["release_sha"] == release_sha


def test_resume_refuses_any_state_except_exact_token_only(monkeypatch):
    enrollment = _module()
    token_path = enrollment.c1_runtime.TOKEN_PATH
    config_path = enrollment.c1_runtime.CONFIG_PATH

    for present in ({config_path}, {token_path, config_path}, set()):
        _release_sha, _paths, _writes, _qualifications = _install_enrollment_fakes(
            monkeypatch,
            enrollment,
            present=present,
        )
        with pytest.raises(
            enrollment.C1EnrollmentError,
            match="C1_ENROLLMENT_EXISTING_REFUSED",
        ):
            asyncio.run(enrollment._resume(bot_user_id=BOT))  # noqa: SLF001


def test_verify_is_read_only_and_requalifies_exact_existing_identity(monkeypatch):
    enrollment = _module()
    release_sha, _present, writes, qualifications = _install_enrollment_fakes(
        monkeypatch,
        enrollment,
        present={enrollment.c1_runtime.TOKEN_PATH, enrollment.c1_runtime.CONFIG_PATH},
    )
    monkeypatch.setattr(enrollment, "_existing_token", lambda: TOKEN)
    monkeypatch.setattr(
        enrollment.c1_runtime,
        "load_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            slack_bot_user_id=BOT,
            relay_version=release_sha,
        ),
    )

    receipt = asyncio.run(enrollment._verify(bot_user_id=BOT))  # noqa: SLF001

    assert writes == []
    assert qualifications == [(TOKEN, BOT)]
    assert receipt["action"] == "verified"
    assert receipt["release_sha"] == release_sha
    assert TOKEN not in json.dumps(receipt)


def test_source_has_no_service_arm_or_secret_argv_environment_path():
    enrollment = _module()
    source = Path(enrollment.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "launchctl enable",
        "launchctl bootstrap",
        "launchctl kickstart",
        "--token",
        "os.environ[\"SLACK",
        "os.getenv(\"SLACK",
    ):
        assert forbidden not in source
    assert "termios.ECHO" in source
    assert "tcsetattr" in source
    assert "validate_relay_group_names" in source
