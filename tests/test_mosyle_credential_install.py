import json
import os
from pathlib import Path

import pytest

from integrations.mosyle_mdm import credential as credential_file
from ops.executive_os import install_mosyle_credential as install


def payload(
    token="a" * 32,
    *,
    auth_mode="jwt",
    email=None,
    password=None,
    extra=None,
):
    value = {"auth_mode": auth_mode, "access_token": token}
    if email is not None:
        value["email"] = email
    if password is not None:
        value["password"] = password
    if extra:
        value.update(extra)
    return json.dumps(value).encode()


def session_payload(token="a" * 32):
    return payload(
        token,
        auth_mode="session_login",
        email="api-user@example.com",
        password="secret123",
    )


@pytest.fixture
def safe_metadata(monkeypatch):
    monkeypatch.setattr(credential_file, "_validate_parent", lambda _path: None)
    monkeypatch.setattr(
        credential_file, "_has_acl", lambda _path, _identity, _descriptor: False
    )
    monkeypatch.setattr(os, "fchown", lambda _fd, _uid, _gid: None)


def test_session_login_install_is_canonical_atomic_and_has_no_bearer(
    tmp_path, safe_metadata
):
    target = tmp_path / "mosyle-readonly.json"
    status = install.install_credential(
        session_payload(),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    assert status == "INSTALLED"
    assert target.stat().st_mode & 0o777 == 0o600
    stored = json.loads(target.read_text())
    assert stored == {
        "auth_mode": "session_login",
        "access_token": "a" * 32,
        "email": "api-user@example.com",
        "password": "secret123",
    }
    assert "bearer_token" not in stored


def test_jwt_install_is_minimal(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    status = install.install_credential(
        payload(),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    assert status == "INSTALLED"
    assert json.loads(target.read_text()) == {
        "auth_mode": "jwt",
        "access_token": "a" * 32,
    }


def test_identical_existing_is_reconciliation_not_replacement(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    first = install.install_credential(
        session_payload(),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    before = target.stat()
    second = install.install_credential(
        session_payload(),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    after = target.stat()
    assert first == "INSTALLED"
    assert second == "ALREADY_INSTALLED"
    assert (before.st_dev, before.st_ino, before.st_mtime_ns) == (
        after.st_dev,
        after.st_ino,
        after.st_mtime_ns,
    )


def test_different_existing_requires_explicit_replace(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    install.install_credential(
        payload(),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    with pytest.raises(install.InstallError, match="explicit replacement"):
        install.install_credential(
            payload("c" * 32),
            target=target,
            service_uid=os.geteuid(),
            service_gid=os.getegid(),
            replace_existing=False,
        )
    stored = json.loads(target.read_text())
    assert stored["access_token"] == "a" * 32


def test_explicit_replace_changes_only_fixed_target(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    install.install_credential(
        payload(),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    status = install.install_credential(
        session_payload("c" * 32),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=True,
    )
    assert status == "INSTALLED"
    stored = json.loads(target.read_text())
    assert stored["auth_mode"] == "session_login"
    assert stored["access_token"] == "c" * 32
    assert stored["email"] == "api-user@example.com"
    assert "bearer_token" not in stored


def test_replace_absent_refuses(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    with pytest.raises(install.InstallError, match="target is absent"):
        install.install_credential(
            payload(),
            target=target,
            service_uid=os.geteuid(),
            service_gid=os.getegid(),
            replace_existing=True,
        )
    assert not target.exists()


def test_post_replace_verification_failure_is_effect_unknown(
    tmp_path, safe_metadata, monkeypatch
):
    target = tmp_path / "mosyle-readonly.json"
    canonical = install._canonical_payload(payload())
    calls = 0

    def read(path, *, expected_uid, expected_gid):
        nonlocal calls
        calls += 1
        if calls == 1:
            return canonical
        raise credential_file.MosyleCredentialFileError("lost verification")

    monkeypatch.setattr(credential_file, "_read_credential_file", read)
    with pytest.raises(install.InstallEffectUnknown):
        install.install_credential(
            payload(),
            target=target,
            service_uid=os.geteuid(),
            service_gid=os.getegid(),
            replace_existing=False,
        )
    assert target.exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not-json",
        payload("short"),
        payload(extra={"bearer_token": "b" * 32}),
        payload(auth_mode="jwt", email="api@example.com"),
        payload(auth_mode="session_login"),
        payload(
            auth_mode="session_login",
            email="api@example.com",
            password=None,
        ),
    ],
)
def test_credential_parser_refuses_invalid_or_dynamic_bearer_shape(raw):
    with pytest.raises(credential_file.MosyleCredentialFileError):
        credential_file._parse_credential(raw)


def test_cli_has_no_secret_or_target_arguments():
    source = Path(install.__file__).read_text(encoding="utf-8")
    assert "--replace-existing" in source
    for forbidden in (
        "--token",
        "--access-token",
        "--bearer",
        "--email",
        "--password",
        "--credential-path",
        "--target",
        "--uid",
        "--gid",
    ):
        assert forbidden not in source


def test_durable_credential_implementation_has_no_bearer_field():
    source = Path(credential_file.__file__).read_text(encoding="utf-8")
    installer = Path(install.__file__).read_text(encoding="utf-8")
    assert "bearer_token" not in source
    assert "bearer_token" not in installer
