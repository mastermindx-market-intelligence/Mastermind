import json
import os

import pytest

from integrations.mosyle_mdm import credential as credential_file
from ops.executive_os import install_mosyle_credential as install


def payload(token, bearer=None):
    value = {"access_token": token}
    if bearer is not None:
        value["bearer_token"] = bearer
    return json.dumps(value).encode()


@pytest.fixture
def safe_metadata(monkeypatch):
    monkeypatch.setattr(credential_file, "_validate_parent", lambda _path: None)
    monkeypatch.setattr(
        credential_file, "_has_acl", lambda _path, _identity, _descriptor: False
    )
    monkeypatch.setattr(os, "fchown", lambda _fd, _uid, _gid: None)


def test_new_install_is_canonical_atomic_and_secret_free(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    status = install.install_credential(
        payload("a" * 32, "b" * 32),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    assert status == "INSTALLED"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.read_text() == json.dumps(
        {"access_token": "a" * 32, "bearer_token": "b" * 32},
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def test_identical_existing_is_reconciliation_not_replacement(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    first = install.install_credential(
        payload("a" * 32),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    before = target.stat()
    second = install.install_credential(
        payload("a" * 32),
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
        payload("a" * 32),
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
    assert "a" * 32 in target.read_text()
    assert "c" * 32 not in target.read_text()


def test_explicit_replace_changes_only_fixed_target(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    install.install_credential(
        payload("a" * 32),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=False,
    )
    status = install.install_credential(
        payload("c" * 32),
        target=target,
        service_uid=os.geteuid(),
        service_gid=os.getegid(),
        replace_existing=True,
    )
    assert status == "INSTALLED"
    assert "c" * 32 in target.read_text()
    assert "a" * 32 not in target.read_text()


def test_replace_absent_refuses(tmp_path, safe_metadata):
    target = tmp_path / "mosyle-readonly.json"
    with pytest.raises(install.InstallError, match="target is absent"):
        install.install_credential(
            payload("a" * 32),
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
    canonical = install._canonical_payload(payload("a" * 32))
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
            payload("a" * 32),
            target=target,
            service_uid=os.geteuid(),
            service_gid=os.getegid(),
            replace_existing=False,
        )
    assert target.exists()


def test_cli_has_no_secret_or_target_arguments():
    source = (
        __import__("pathlib").Path(install.__file__).read_text(encoding="utf-8")
    )
    assert "--replace-existing" in source
    for forbidden in (
        "--token",
        "--access-token",
        "--bearer",
        "--password",
        "--credential-path",
        "--target",
        "--uid",
        "--gid",
    ):
        assert forbidden not in source
