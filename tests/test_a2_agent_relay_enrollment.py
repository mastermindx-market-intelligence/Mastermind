from __future__ import annotations

import asyncio
import importlib
import importlib.util
import io
import json
import os
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.slack_agent_dialogue import metadata_verifier
from integrations.slack_agent_dialogue.slack_web_api import (
    SLACK_API_ROOT,
    SlackHttpResponse,
)


WORKSPACE = "T0BRD2AQXQV"
CHANNEL = "C0BSBM78V1N"
BOT = "U0BST4WG996"
TOKEN = "".join(("xo", "xb-", "123456789012-", "abcdefghijklmnopqrstuvwxyz"))
SCOPES = ("channels:history", "chat:write")


def _module():
    name = "ops.executive_os.a2_agent_relay_enrollment"
    assert importlib.util.find_spec(name) is not None, "A2 enrollment helper is missing"
    return importlib.import_module(name)


class _IdentityTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request(self, *, token: str) -> metadata_verifier.HttpResult:
        self.calls.append(token)
        return metadata_verifier.HttpResult(
            status_code=200,
            final_url=metadata_verifier.SLACK_AUTH_TEST_URL,
            headers={
                "content-type": "application/json",
                "x-oauth-scopes": ",".join(reversed(SCOPES)),
            },
            body=json.dumps(
                {
                    "ok": True,
                    "team_id": WORKSPACE,
                    "user_id": BOT,
                    "bot_id": "B0BST4WG996",
                }
            ).encode("utf-8"),
        )


class _HistoryTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def request(self, **kwargs) -> SlackHttpResponse:
        self.calls.append(dict(kwargs))
        return SlackHttpResponse(
            status_code=200,
            final_url=(
                SLACK_API_ROOT
                + "conversations.history?channel=C0BSBM78V1N&limit=1"
            ),
            headers={"content-type": "application/json"},
            body=b'{"ok":true,"messages":[],"has_more":false,'
            b'"response_metadata":{"next_cursor":""}}',
        )


class _LineOnlyInput(io.BytesIO):
    def read(self, *args, **kwargs):  # pragma: no cover - must use one line
        raise AssertionError("token input must never read to EOF")


class _NoTokenRead(io.BytesIO):
    def readline(self, *args, **kwargs):
        raise AssertionError("host refusal must precede token input")


def test_parser_has_only_expected_bot_identity_and_no_secret_or_path_overrides():
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
    assert set(parser._subparsers._group_actions[0].choices) == {"enroll", "verify"}
    assert "--expected-bot-user-id" in options
    assert {"--token", "--workspace", "--channel", "--config", "--plist"}.isdisjoint(
        options
    )


def test_token_input_reuses_bounded_one_line_no_echo_ceremony():
    enrollment = _module()
    stream = _LineOnlyInput((TOKEN + "\nSECOND-LINE\n").encode("ascii"))
    assert enrollment.read_token_from_stdin(stream) == TOKEN
    assert stream.readline() == b"SECOND-LINE\n"

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_INPUT_REFUSED"):
        enrollment.read_token_from_stdin(io.BytesIO(b"contains whitespace\n"))


def test_fixed_policy_document_and_plist_are_release_bound_and_secret_free():
    enrollment = _module()
    release_sha = "a" * 40
    config = enrollment.build_config_document(bot_user_id=BOT, release_sha=release_sha)
    assert config == {
        "schema": "mastermind.agent_relay_enrollment.v1",
        "release_sha": release_sha,
        "slack_workspace_id": WORKSPACE,
        "slack_channel_id": CHANNEL,
        "slack_bot_user_id": BOT,
        "slack_scopes": list(SCOPES),
        "slack_token_file": os.fspath(enrollment.TOKEN_PATH),
        "relay_socket_path": os.fspath(enrollment.SOCKET_PATH),
        "relay_user": "_mastermind_agent_relay",
        "relay_uid": 457,
        "allowed_peer_uids": [450],
        "allowed_sol_user_ids": ["U0BRETDUAS2", "U0BSB73JWNL"],
        "allowed_parent_user_ids": ["U0BRETDUAS2"],
    }

    plist = plistlib.loads(
        enrollment.render_plist(bot_user_id=BOT, release_sha=release_sha)
    )
    assert plist["Label"] == "com.mastermind.executive.agent-relay"
    assert plist["UserName"] == "_mastermind_agent_relay"
    assert plist["GroupName"] == "_mastermind_agent_relay"
    assert plist["WorkingDirectory"].endswith(release_sha)
    assert plist["ProgramArguments"] == [
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "-I",
        "-S",
        "-B",
        f"/Library/Application Support/MastermindExecutive/releases/{release_sha}/scripts/slack_agent_dialogue_service.py",
        "--socket-path",
        os.fspath(enrollment.SOCKET_PATH),
        "--token-file",
        os.fspath(enrollment.TOKEN_PATH),
        "--workspace-id",
        WORKSPACE,
        "--channel-id",
        CHANNEL,
        "--bot-user-id",
        BOT,
        "--allowed-peer-uid",
        "450",
        "--allowed-sol-user-id",
        "U0BRETDUAS2",
        "--allowed-sol-user-id",
        "U0BSB73JWNL",
        "--allowed-parent-user-id",
        "U0BRETDUAS2",
    ]
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert not any(
        "xox" in str(value).lower()
        for value in plist["ProgramArguments"]
    )


def test_qualification_proves_exact_identity_scopes_and_channel_history():
    enrollment = _module()
    identity = _IdentityTransport()
    history = _HistoryTransport()

    receipt = asyncio.run(
        enrollment.qualify_token(
            token=TOKEN,
            bot_user_id=BOT,
            identity_transport=identity,
            history_transport=history,
        )
    )

    assert receipt == {
        "bot_id": "B0BST4WG996",
        "bot_user_id": BOT,
        "channel_id": CHANNEL,
        "scopes": list(SCOPES),
        "workspace_id": WORKSPACE,
    }
    assert identity.calls == [TOKEN]
    assert history.calls == [
        {
            "method": "GET",
            "path": "conversations.history",
            "token": TOKEN,
            "query": {"channel": CHANNEL, "limit": "1"},
            "json_body": None,
        }
    ]
    assert TOKEN not in json.dumps(receipt)


def _install_operation_fakes(monkeypatch, enrollment, tmp_path: Path):
    release_sha = "b" * 40
    system_root = tmp_path / "Library/Application Support/MastermindExecutive"
    config_parent = system_root / "config"
    config_parent.mkdir(parents=True, mode=0o755)
    for path in (
        tmp_path / "Library",
        tmp_path / "Library/Application Support",
        system_root,
        config_parent,
    ):
        path.chmod(0o755)
    token_path = config_parent / "agent-relay.token"
    config_path = config_parent / "agent-relay.json"
    plist_path = tmp_path / "agent-relay.plist"
    monkeypatch.setattr(enrollment, "SYSTEM_ROOT", system_root)
    monkeypatch.setattr(enrollment, "TOKEN_PATH", token_path)
    monkeypatch.setattr(enrollment, "CONFIG_PATH", config_path)
    monkeypatch.setattr(enrollment, "PLIST_PATH", plist_path)
    monkeypatch.setattr(enrollment, "RELAY_UID", os.geteuid())
    monkeypatch.setattr(enrollment, "RELAY_GID", os.getegid())
    monkeypatch.setattr(enrollment, "PLIST_UID", os.geteuid())
    monkeypatch.setattr(enrollment, "PLIST_GID", os.getegid())
    monkeypatch.setattr(enrollment, "_assert_host_prepared", lambda: release_sha)
    monkeypatch.setattr(enrollment, "_assert_disarmed", lambda: None)
    qualifications: list[tuple[str, str]] = []

    async def qualify_token(*, token, bot_user_id, **_kwargs):
        qualifications.append((token, bot_user_id))
        return {
            "bot_id": "B0BST4WG996",
            "bot_user_id": bot_user_id,
            "channel_id": CHANNEL,
            "scopes": list(SCOPES),
            "workspace_id": WORKSPACE,
        }

    monkeypatch.setattr(enrollment, "qualify_token", qualify_token)
    return release_sha, (token_path, config_path, plist_path), qualifications


def test_enroll_qualifies_then_commits_exact_three_files(monkeypatch, tmp_path: Path):
    enrollment = _module()
    release_sha, paths, qualifications = _install_operation_fakes(
        monkeypatch, enrollment, tmp_path
    )

    receipt = asyncio.run(
        enrollment._enroll(  # noqa: SLF001 - adversarial transaction proof
            bot_user_id=BOT,
            stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
        )
    )

    token_path, config_path, plist_path = paths
    assert qualifications == [(TOKEN, BOT)]
    assert token_path.read_text(encoding="ascii") == TOKEN + "\n"
    assert token_path.stat().st_mode & 0o777 == 0o400
    assert config_path.stat().st_mode & 0o777 == 0o400
    assert plist_path.stat().st_mode & 0o777 == 0o644
    assert json.loads(config_path.read_text(encoding="utf-8"))["release_sha"] == release_sha
    assert plistlib.loads(plist_path.read_bytes())["Label"] == enrollment.RELAY_LABEL
    assert receipt["action"] == "enrolled"
    assert receipt["release_sha"] == release_sha
    assert TOKEN not in json.dumps(receipt)


@pytest.mark.parametrize("collision_index", [0, 1, 2])
def test_enroll_refuses_any_preexisting_target_without_reads_or_writes(
    monkeypatch, tmp_path: Path, collision_index: int
):
    enrollment = _module()
    _release_sha, paths, qualifications = _install_operation_fakes(
        monkeypatch, enrollment, tmp_path
    )
    collision = paths[collision_index]
    collision.write_bytes(b"preexisting")
    before = collision.stat()

    class _NoRead(io.BytesIO):
        def readline(self, *args, **kwargs):
            raise AssertionError("collision must be refused before token input")

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_COLLISION"):
        asyncio.run(enrollment._enroll(bot_user_id=BOT, stdin=_NoRead()))  # noqa: SLF001

    after = collision.stat()
    assert qualifications == []
    assert collision.read_bytes() == b"preexisting"
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert [path.exists() for path in paths].count(True) == 1


def test_failed_plist_write_rolls_back_only_files_created_by_invocation(
    monkeypatch, tmp_path: Path
):
    enrollment = _module()
    _release_sha, paths, _qualifications = _install_operation_fakes(
        monkeypatch, enrollment, tmp_path
    )
    def fail_plist(path, payload, *, uid, gid, mode):
        del path, payload, uid, gid, mode
        raise enrollment.A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")

    monkeypatch.setattr(enrollment, "write_new_private_file", fail_plist)
    unrelated = tmp_path / "unrelated"
    unrelated.write_bytes(b"preserve")

    with pytest.raises(
        enrollment.A2EnrollmentError, match="A2_ENROLLMENT_WRITE_REFUSED"
    ):
        asyncio.run(
            enrollment._enroll(  # noqa: SLF001
                bot_user_id=BOT,
                stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
            )
        )

    assert not any(path.exists() for path in paths)
    assert unrelated.read_bytes() == b"preserve"


def test_enroll_refuses_mutated_bound_token_during_readback(monkeypatch, tmp_path: Path):
    enrollment = _module()
    _release_sha, paths, _qualifications = _install_operation_fakes(
        monkeypatch, enrollment, tmp_path
    )
    real_write = enrollment._write_new_bound_private_file  # noqa: SLF001

    def write_then_mutate(binding, name, payload, *, uid, gid, mode):
        identity = real_write(
            binding,
            name,
            payload,
            uid=uid,
            gid=gid,
            mode=mode,
        )
        if name == enrollment.TOKEN_PATH.name:
            os.chmod(
                name,
                0o600,
                dir_fd=binding.descriptor,
                follow_symlinks=False,
            )
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_TRUNC,
                dir_fd=binding.descriptor,
            )
            try:
                os.write(descriptor, b"mutated-token\n")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return identity

    monkeypatch.setattr(
        enrollment,
        "_write_new_bound_private_file",
        write_then_mutate,
    )

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_EXISTING_REFUSED"):
        asyncio.run(
            enrollment._enroll(  # noqa: SLF001
                bot_user_id=BOT,
                stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
            )
        )

    assert not any(path.exists() for path in paths)


def test_rollback_refuses_to_unlink_replaced_inode(monkeypatch, tmp_path: Path):
    enrollment = _module()
    target = tmp_path / "created"
    target.write_bytes(b"original")
    identity = enrollment._file_identity(target)  # noqa: SLF001
    target.unlink()
    target.write_bytes(b"replacement")

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_ROLLBACK_REFUSED"):
        enrollment._rollback_created([identity])  # noqa: SLF001
    assert target.read_bytes() == b"replacement"


def test_bound_rollback_refuses_to_unlink_replaced_inode(tmp_path: Path):
    enrollment = _module()
    directory_descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        directory_info = os.fstat(directory_descriptor)
        binding = enrollment._BoundDirectory(  # noqa: SLF001
            descriptor=directory_descriptor,
            device=directory_info.st_dev,
            inode=directory_info.st_ino,
            relay_gids=frozenset({os.getegid()}),
        )
        target = tmp_path / "agent-relay.token"
        target.write_bytes(b"original")
        original = target.stat()
        identity = enrollment._BoundCreatedFile(  # noqa: SLF001
            name=target.name,
            device=original.st_dev,
            inode=original.st_ino,
        )
        target.unlink()
        target.write_bytes(b"replacement")

        with pytest.raises(
            enrollment.A2EnrollmentError,
            match="A2_ENROLLMENT_ROLLBACK_REFUSED",
        ):
            enrollment._rollback_bound_created(binding, [identity])  # noqa: SLF001
        assert target.read_bytes() == b"replacement"
    finally:
        os.close(directory_descriptor)


def test_verify_is_read_only_and_requalifies_release_identity(monkeypatch, tmp_path: Path):
    enrollment = _module()
    release_sha, paths, qualifications = _install_operation_fakes(
        monkeypatch, enrollment, tmp_path
    )
    token_path, config_path, plist_path = paths
    token_path.write_text(TOKEN + "\n", encoding="ascii")
    token_path.chmod(0o400)
    config_path.write_bytes(
        enrollment._canonical_json_bytes(  # noqa: SLF001
            enrollment.build_config_document(bot_user_id=BOT, release_sha=release_sha)
        )
    )
    config_path.chmod(0o400)
    plist_path.write_bytes(enrollment.render_plist(bot_user_id=BOT, release_sha=release_sha))
    plist_path.chmod(0o644)
    before = {path: (path.stat().st_ino, path.read_bytes()) for path in paths}

    receipt = asyncio.run(enrollment._verify(bot_user_id=BOT))  # noqa: SLF001

    after = {path: (path.stat().st_ino, path.read_bytes()) for path in paths}
    assert after == before
    assert qualifications == [(TOKEN, BOT)]
    assert receipt["action"] == "verified"
    assert receipt["release_sha"] == release_sha


def test_host_gate_requires_distinct_relay_owner_exact_exec_client_and_disarmed_launchd(
    monkeypatch, tmp_path: Path
):
    enrollment = _module()
    _install_canonical_host_gate_fakes(monkeypatch, enrollment, tmp_path)

    assert enrollment._assert_host_prepared() == "d" * 40  # noqa: SLF001

    exec_account = SimpleNamespace(
        pw_uid=450,
        pw_gid=450,
        pw_dir="/var/db/mastermind-executive/control/home",
        pw_shell="/usr/bin/false",
    )
    monkeypatch.setattr(enrollment.pwd, "getpwnam", lambda _name: exec_account)
    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        enrollment._assert_host_prepared()  # noqa: SLF001


@pytest.mark.parametrize(
    "members,exec_gids",
    [
        ([], [450]),
        (["_mastermind_exec", "foreign"], [450, 457]),
        (["_mastermind_exec"], [450]),
    ],
)
def test_host_gate_refuses_missing_or_nonexact_shared_group(
    monkeypatch, tmp_path: Path, members: list[str], exec_gids: list[int]
):
    enrollment = _module()
    _install_canonical_host_gate_fakes(
        monkeypatch,
        enrollment,
        tmp_path,
        members=members,
        exec_gids=exec_gids,
    )
    chain = enrollment._credential_directory_chain()  # noqa: SLF001
    assert chain is not None
    assert all(
        enrollment._principal_can_traverse(path, uid=457, gids={457})  # noqa: SLF001
        for path in chain
    )

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        enrollment._assert_host_prepared()  # noqa: SLF001


def test_host_gate_refuses_credential_parent_not_traversable_by_relay(
    monkeypatch, tmp_path: Path
):
    enrollment = _module()
    config_parent = tmp_path / "config"
    config_parent.mkdir(mode=0o700)
    assert not enrollment._principal_can_traverse(  # noqa: SLF001
        config_parent, uid=457, gids={457}
    )
    config_parent.chmod(0o755)
    assert enrollment._principal_can_traverse(  # noqa: SLF001
        config_parent, uid=457, gids={457}
    )


def _install_canonical_host_gate_fakes(
    monkeypatch,
    enrollment,
    tmp_path: Path,
    *,
    intermediate_symlink: bool = False,
    relay_gids: list[int] | None = None,
    exec_gids: list[int] | None = None,
    members: list[str] | None = None,
    relay_uid: int = 457,
    relay_gid: int = 457,
):
    library = tmp_path / "Library"
    library.mkdir(mode=0o755)
    support = library / "Application Support"
    if intermediate_symlink:
        real_support = tmp_path / "real-application-support"
        (real_support / "MastermindExecutive/config").mkdir(parents=True, mode=0o755)
        support.symlink_to(real_support, target_is_directory=True)
        system_root = support / "MastermindExecutive"
    else:
        system_root = support / "MastermindExecutive"
        (system_root / "config").mkdir(parents=True, mode=0o755)
    for path in (library, system_root, system_root / "config"):
        path.chmod(0o755)
    if not intermediate_symlink:
        support.chmod(0o755)

    monkeypatch.setattr(enrollment, "SYSTEM_ROOT", system_root)
    monkeypatch.setattr(enrollment, "CONFIG_PATH", system_root / "config/agent-relay.json")
    monkeypatch.setattr(enrollment, "TOKEN_PATH", system_root / "config/agent-relay.token")
    monkeypatch.setattr(enrollment, "RELAY_UID", relay_uid)
    monkeypatch.setattr(enrollment, "RELAY_GID", relay_gid)
    monkeypatch.setattr(enrollment.os, "geteuid", lambda: 0)
    monkeypatch.setattr(enrollment.sys, "platform", "darwin")
    monkeypatch.setattr(enrollment.c1_enrollment, "_release_identity", lambda: "d" * 40)
    accounts = {
        "_mastermind_agent_relay": SimpleNamespace(
            pw_uid=relay_uid,
            pw_gid=relay_gid,
            pw_dir="/var/db/mastermind-agent-relay/home",
            pw_shell="/usr/bin/false",
        ),
        "_mastermind_exec": SimpleNamespace(
            pw_uid=450,
            pw_gid=450,
            pw_dir="/var/db/mastermind-executive/control/home",
            pw_shell="/usr/bin/false",
        ),
    }
    monkeypatch.setattr(enrollment.pwd, "getpwnam", accounts.__getitem__)
    monkeypatch.setattr(
        enrollment.grp,
        "getgrnam",
        lambda _name: SimpleNamespace(
            gr_gid=relay_gid,
            gr_mem=["_mastermind_exec"] if members is None else members,
        ),
    )
    groups = {
        "_mastermind_agent_relay": [relay_gid] if relay_gids is None else relay_gids,
        "_mastermind_exec": [450, relay_gid] if exec_gids is None else exec_gids,
    }
    monkeypatch.setattr(
        enrollment.os, "getgrouplist", lambda name, _gid: groups[name]
    )
    monkeypatch.setattr(
        enrollment.grp,
        "getgrgid",
        lambda gid: SimpleNamespace(
            gr_name={450: "_mastermind_exec", relay_gid: "_mastermind_agent_relay"}[gid]
        ),
    )
    monkeypatch.setattr(enrollment.c1_enrollment, "_launchd_loaded", lambda _label: False)
    monkeypatch.setattr(enrollment.c1_enrollment, "_launchd_disabled", lambda _label: True)
    return library, support, system_root


def test_host_gate_refuses_intermediate_credential_symlink(monkeypatch, tmp_path: Path):
    enrollment = _module()
    _install_canonical_host_gate_fakes(
        monkeypatch,
        enrollment,
        tmp_path,
        intermediate_symlink=True,
    )
    chain = enrollment._credential_directory_chain()  # noqa: SLF001
    assert chain is not None
    assert chain[1].is_symlink()

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        asyncio.run(enrollment._enroll(bot_user_id=BOT, stdin=_NoTokenRead()))  # noqa: SLF001


def test_host_gate_refuses_inaccessible_credential_ancestor(monkeypatch, tmp_path: Path):
    enrollment = _module()
    _library, support, _system_root = _install_canonical_host_gate_fakes(
        monkeypatch, enrollment, tmp_path
    )
    support.chmod(0o700)

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        asyncio.run(enrollment._enroll(bot_user_id=BOT, stdin=_NoTokenRead()))  # noqa: SLF001


def test_host_gate_refuses_group_or_other_writable_credential_parent(
    monkeypatch, tmp_path: Path
):
    enrollment = _module()
    _library, _support, system_root = _install_canonical_host_gate_fakes(
        monkeypatch, enrollment, tmp_path
    )
    (system_root / "config").chmod(0o777)

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        asyncio.run(enrollment._enroll(bot_user_id=BOT, stdin=_NoTokenRead()))  # noqa: SLF001


def test_host_gate_refuses_relay_membership_in_exec_group(monkeypatch, tmp_path: Path):
    enrollment = _module()
    _install_canonical_host_gate_fakes(
        monkeypatch,
        enrollment,
        tmp_path,
        relay_gids=[457, 450],
    )

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        asyncio.run(enrollment._enroll(bot_user_id=BOT, stdin=_NoTokenRead()))  # noqa: SLF001


def test_enroll_refuses_mid_qualification_ancestor_swap_without_secret_residue(
    monkeypatch, tmp_path: Path
):
    enrollment = _module()
    actual_uid = os.geteuid()
    actual_gid = os.getegid()
    _library, _support, system_root = _install_canonical_host_gate_fakes(
        monkeypatch,
        enrollment,
        tmp_path,
        relay_uid=actual_uid,
        relay_gid=actual_gid,
        relay_gids=[actual_gid],
        exec_gids=[450, actual_gid],
    )
    plist_path = tmp_path / "agent-relay.plist"
    monkeypatch.setattr(enrollment, "PLIST_PATH", plist_path)
    monkeypatch.setattr(enrollment, "PLIST_UID", actual_uid)
    monkeypatch.setattr(enrollment, "PLIST_GID", actual_gid)
    original_root = tmp_path / "original-mastermind-executive"
    redirected_root = tmp_path / "redirected-mastermind-executive"

    async def swap_during_qualification(*, token, bot_user_id, **_kwargs):
        assert token == TOKEN
        assert bot_user_id == BOT
        system_root.rename(original_root)
        (redirected_root / "config").mkdir(parents=True, mode=0o755)
        system_root.symlink_to(redirected_root, target_is_directory=True)
        return {
            "bot_id": "B0BST4WG996",
            "bot_user_id": bot_user_id,
            "channel_id": CHANNEL,
            "scopes": list(SCOPES),
            "workspace_id": WORKSPACE,
        }

    monkeypatch.setattr(enrollment, "qualify_token", swap_during_qualification)

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        asyncio.run(
            enrollment._enroll(  # noqa: SLF001
                bot_user_id=BOT,
                stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
            )
        )

    for parent in (original_root / "config", redirected_root / "config"):
        assert not (parent / "agent-relay.token").exists()
        assert not (parent / "agent-relay.json").exists()
    assert not plist_path.exists()


def test_enroll_rolls_back_bound_leaves_if_ancestor_moves_after_writes(
    monkeypatch, tmp_path: Path
):
    enrollment = _module()
    _release_sha, paths, _qualifications = _install_operation_fakes(
        monkeypatch, enrollment, tmp_path
    )
    system_root = enrollment.SYSTEM_ROOT
    original_root = tmp_path / "postwrite-original-mastermind-executive"
    redirected_root = tmp_path / "postwrite-redirected-mastermind-executive"
    real_write = enrollment.write_new_private_file

    def write_plist_then_swap(path, payload, *, uid, gid, mode):
        real_write(path, payload, uid=uid, gid=gid, mode=mode)
        system_root.rename(original_root)
        (redirected_root / "config").mkdir(parents=True, mode=0o755)
        system_root.symlink_to(redirected_root, target_is_directory=True)

    monkeypatch.setattr(enrollment, "write_new_private_file", write_plist_then_swap)

    with pytest.raises(enrollment.A2EnrollmentError, match="A2_ENROLLMENT_HOST_REFUSED"):
        asyncio.run(
            enrollment._enroll(  # noqa: SLF001
                bot_user_id=BOT,
                stdin=io.BytesIO((TOKEN + "\n").encode("ascii")),
            )
        )

    for parent in (original_root / "config", redirected_root / "config"):
        assert not (parent / "agent-relay.token").exists()
        assert not (parent / "agent-relay.json").exists()
    assert not paths[2].exists()


def test_source_has_no_principal_creation_service_arm_or_secret_surface():
    enrollment = _module()
    source = Path(enrollment.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "dscl",
        "launchctl enable",
        "launchctl bootstrap",
        "launchctl kickstart",
        "--token",
        'os.environ["SLACK',
        'os.getenv("SLACK',
    ):
        assert forbidden not in source
    assert "read_token_from_stdin" in source
    assert "_mastermind_exec" in source
    assert "_mastermind_agent_relay" in source
