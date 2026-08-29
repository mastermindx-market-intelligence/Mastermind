from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import stat
import termios
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE = "ops.linear_projector.host_enrollment"


def _module_spec():
    try:
        return importlib.util.find_spec(MODULE)
    except ModuleNotFoundError:
        return None


def _load():
    spec = _module_spec()
    assert spec is not None, "CRED0 host_enrollment module is not built yet"
    return importlib.import_module(MODULE)


class _LineOnlyInput(io.BytesIO):
    def read(self, *args, **kwargs):  # pragma: no cover - forbidden path
        raise AssertionError("secret input must use one bounded readline")


class _FakeTtyInput(io.BytesIO):
    def fileno(self) -> int:
        return 77


def test_linear_projector_host_enrollment_module_exists() -> None:
    assert _module_spec() is not None, "CRED0 host_enrollment module is not built yet"


def test_production_coordinates_and_identity_are_fixed() -> None:
    mod = _load()
    assert mod.ROOT == Path("/Library/Application Support/MastermindPortfolioProjector")
    assert mod.CONFIG_DIR == mod.ROOT / "config"
    assert mod.CONFIG_PATH == mod.CONFIG_DIR / "projector.json"
    assert mod.SECRET_PATH == mod.CONFIG_DIR / "oauth-client-secret"
    assert mod.WORKSPACE_ID == "93bfb3d6-93f1-48a8-9720-aa653cba4335"
    assert mod.TEAM_ID == "26b5bb87-2482-4f8f-a42f-955250bd9eaf"
    assert mod.TEAM_KEY == "MAS"
    assert mod.APP_NAME == "Mastermind Portfolio Projector"
    assert mod.CONFIG_SCHEMA == "mastermind.linear_projector_host.v1"

    joined = "\n".join(
        map(str, (mod.ROOT, mod.CONFIG_DIR, mod.CONFIG_PATH, mod.SECRET_PATH))
    )
    assert "MastermindExecutive" not in joined
    assert "multilogin" not in joined.lower()


def test_cli_surface_is_closed_to_fixed_prepare_enroll_verify_commands() -> None:
    mod = _load()
    parser = mod.build_parser()

    assert parser.parse_args(["prepare"]).command == "prepare"
    assert parser.parse_args(["enroll", "--client-id", "abc123"]).client_id == "abc123"
    assert (
        parser.parse_args(["verify", "--expected-client-id", "abc123"]).expected_client_id
        == "abc123"
    )

    with pytest.raises(mod.ProjectorHostError) as exc:
        parser.parse_args(["enroll", "--path", "/tmp/x", "--client-id", "abc123"])
    assert exc.value.code == "PROJECTOR_HOST_ARGUMENTS_REFUSED"

    with pytest.raises(mod.ProjectorHostError) as exc:
        parser.parse_args(["rotate", "--client-id", "abc123"])
    assert exc.value.code == "PROJECTOR_HOST_ARGUMENTS_REFUSED"


def test_secret_shaped_argv_or_environment_refuses_opaquely() -> None:
    mod = _load()

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.assert_secret_surfaces_clean(
            argv=["enroll", "--client-id", "abc123", "lin_api_example_secret"],
            environ={},
        )
    assert exc.value.code == "PROJECTOR_HOST_SECRET_SURFACE_REFUSED"
    assert "lin_api_example_secret" not in str(exc.value)

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.assert_secret_surfaces_clean(
            argv=["enroll", "--client-id", "abc123"],
            environ={"LINEAR_CLIENT_SECRET": "not-for-output"},
        )
    assert exc.value.code == "PROJECTOR_HOST_SECRET_SURFACE_REFUSED"
    assert "not-for-output" not in str(exc.value)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b" secret\n",
        b"secret \n",
        b"secret value\n",
        b"secret\tvalue\n",
        b"a\nsecond\n",
        b"\x7f\n",
        "caf\N{LATIN SMALL LETTER E WITH ACUTE}\n".encode("utf-8"),
        b"a" * 4097 + b"\n",
    ],
)
def test_decode_secret_refuses_malformed_input(raw: bytes) -> None:
    mod = _load()
    with pytest.raises(mod.ProjectorHostError) as exc:
        mod._decode_secret_bytes(raw)
    assert exc.value.code == "PROJECTOR_HOST_INPUT_REFUSED"


def test_secret_reader_uses_one_bounded_line_and_returns_bytes() -> None:
    mod = _load()
    stream = _LineOnlyInput(b"projector-secret\nsecond-line\n")
    assert mod.read_secret_from_stdin(stream) == b"projector-secret"
    assert stream.readline() == b"second-line\n"


def test_tty_echo_is_restored_even_when_secret_decode_refuses(monkeypatch) -> None:
    mod = _load()
    original = [0, 0, 0, termios.ECHO | 0x100]
    calls: list[list[int]] = []

    monkeypatch.setattr(mod.os, "isatty", lambda fd: fd == 77)
    monkeypatch.setattr(mod.termios, "tcgetattr", lambda fd: list(original))

    def _setattr(fd, when, attrs):
        assert fd == 77
        assert when == termios.TCSANOW
        calls.append(list(attrs))

    monkeypatch.setattr(mod.termios, "tcsetattr", _setattr)

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.read_secret_from_stdin(_FakeTtyInput(b"bad secret\n"))
    assert exc.value.code == "PROJECTOR_HOST_INPUT_REFUSED"
    assert calls[0][3] & termios.ECHO == 0
    assert calls[-1] == original


def test_secret_decoder_accepts_maximum_ascii_value() -> None:
    mod = _load()
    raw = b"x" * 4096 + b"\n"
    assert mod._decode_secret_bytes(raw) == b"x" * 4096


def test_prepare_host_creates_only_exact_safe_directories(tmp_path: Path) -> None:
    mod = _load()
    root = tmp_path / "projector"
    mod.prepare_host(root=root, uid=os.geteuid(), gid=os.getegid())

    config_dir = root / "config"
    assert root.is_dir()
    assert config_dir.is_dir()
    assert stat.S_IMODE(root.lstat().st_mode) == 0o750
    assert stat.S_IMODE(config_dir.lstat().st_mode) == 0o750
    assert root.lstat().st_uid == os.geteuid()
    assert root.lstat().st_gid == os.getegid()
    assert not (config_dir / "projector.json").exists()
    assert not (config_dir / "oauth-client-secret").exists()

    mod.prepare_host(root=root, uid=os.geteuid(), gid=os.getegid())


def test_prepare_host_refuses_symlink_non_directory_and_unsafe_mode(tmp_path: Path) -> None:
    mod = _load()
    uid = os.geteuid()
    gid = os.getegid()

    target = tmp_path / "target"
    target.mkdir()
    symlink_root = tmp_path / "symlink-root"
    symlink_root.symlink_to(target, target_is_directory=True)
    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.prepare_host(root=symlink_root, uid=uid, gid=gid)
    assert exc.value.code == "PROJECTOR_HOST_PERMISSIONS_REFUSED"

    file_root = tmp_path / "file-root"
    file_root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.prepare_host(root=file_root, uid=uid, gid=gid)
    assert exc.value.code == "PROJECTOR_HOST_PERMISSIONS_REFUSED"

    unsafe_root = tmp_path / "unsafe-root"
    unsafe_root.mkdir()
    unsafe_root.chmod(0o700)
    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.prepare_host(root=unsafe_root, uid=uid, gid=gid)
    assert exc.value.code == "PROJECTOR_HOST_PERMISSIONS_REFUSED"


def test_safe_directory_validator_refuses_wrong_owner(monkeypatch, tmp_path: Path) -> None:
    mod = _load()
    path = tmp_path / "prepared"
    path.mkdir()
    path.chmod(0o750)
    real = path.lstat()
    fake = SimpleNamespace(
        st_mode=real.st_mode,
        st_uid=os.geteuid() + 1,
        st_gid=os.getegid(),
    )
    monkeypatch.setattr(Path, "lstat", lambda self: fake)

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod._assert_safe_directory(
            path,
            uid=os.geteuid(),
            gid=os.getegid(),
            mode=0o750,
        )
    assert exc.value.code == "PROJECTOR_HOST_PERMISSIONS_REFUSED"


def test_config_document_is_exact_non_secret_identity() -> None:
    mod = _load()
    assert mod.build_config_document(client_id="client-abc123") == {
        "schema": "mastermind.linear_projector_host.v1",
        "app_name": "Mastermind Portfolio Projector",
        "client_id": "client-abc123",
        "workspace_id": "93bfb3d6-93f1-48a8-9720-aa653cba4335",
        "team_id": "26b5bb87-2482-4f8f-a42f-955250bd9eaf",
        "team_key": "MAS",
    }

    for value in ("", " client", "client ", "client id", "bad\x7f", "é", "x" * 257):
        with pytest.raises(mod.ProjectorHostError) as exc:
            mod.build_config_document(client_id=value)
        assert exc.value.code == "PROJECTOR_HOST_CONFIG_REFUSED"


def test_write_new_private_file_is_create_once_with_exact_metadata(tmp_path: Path) -> None:
    mod = _load()
    parent = tmp_path / "config"
    parent.mkdir()
    parent.chmod(0o750)
    path = parent / "projector.json"
    payload = b'{"schema":"test"}\n'

    mod.write_new_private_file(
        path,
        payload,
        uid=os.geteuid(),
        gid=os.getegid(),
        mode=0o640,
    )
    info = path.lstat()
    assert path.read_bytes() == payload
    assert stat.S_ISREG(info.st_mode)
    assert info.st_nlink == 1
    assert info.st_uid == os.geteuid()
    assert info.st_gid == os.getegid()
    assert stat.S_IMODE(info.st_mode) == 0o640

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.write_new_private_file(
            path,
            payload,
            uid=os.geteuid(),
            gid=os.getegid(),
            mode=0o640,
        )
    assert exc.value.code == "PROJECTOR_HOST_COLLISION"


def test_enroll_writes_deterministic_config_and_exact_secret_once(tmp_path: Path) -> None:
    mod = _load()
    root = tmp_path / "projector"
    uid = os.geteuid()
    gid = os.getegid()
    mod.prepare_host(root=root, uid=uid, gid=gid)

    mod.enroll(
        client_id="client-abc123",
        secret=b"projector-secret",
        root=root,
        uid=uid,
        gid=gid,
    )
    config_path = root / "config" / "projector.json"
    secret_path = root / "config" / "oauth-client-secret"
    expected_config = json.dumps(
        mod.build_config_document(client_id="client-abc123"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii") + b"\n"
    assert config_path.read_bytes() == expected_config
    assert secret_path.read_bytes() == b"projector-secret"
    assert stat.S_IMODE(config_path.lstat().st_mode) == 0o640
    assert stat.S_IMODE(secret_path.lstat().st_mode) == 0o600

    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.enroll(
            client_id="client-abc123",
            secret=b"projector-secret",
            root=root,
            uid=uid,
            gid=gid,
        )
    assert exc.value.code == "PROJECTOR_HOST_COLLISION"


def test_enroll_second_file_failure_is_not_retried_or_rolled_back(
    monkeypatch, tmp_path: Path
) -> None:
    mod = _load()
    root = tmp_path / "projector"
    uid = os.geteuid()
    gid = os.getegid()
    mod.prepare_host(root=root, uid=uid, gid=gid)
    original = mod.write_new_private_file
    calls: list[str] = []

    def _write(path, payload, *, uid, gid, mode):
        calls.append(Path(path).name)
        if Path(path).name == "oauth-client-secret":
            raise mod.ProjectorHostError("PROJECTOR_HOST_WRITE_REFUSED")
        return original(path, payload, uid=uid, gid=gid, mode=mode)

    monkeypatch.setattr(mod, "write_new_private_file", _write)
    with pytest.raises(mod.ProjectorHostError) as exc:
        mod.enroll(
            client_id="client-abc123",
            secret=b"projector-secret",
            root=root,
            uid=uid,
            gid=gid,
        )
    assert exc.value.code == "PROJECTOR_HOST_WRITE_REFUSED"
    assert calls == ["projector.json", "oauth-client-secret"]
    assert (root / "config" / "projector.json").is_file()
    assert not (root / "config" / "oauth-client-secret").exists()
