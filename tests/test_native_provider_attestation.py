"""Native attestation drift/refusal tests; no provider or credential access."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import native_provider_attestation as att


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(att, "_ROOT_UID", os.geteuid())
    @contextlib.contextmanager
    def opened(path, *, directory=False):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0))
        try:
            before = os.fstat(fd)
            yield fd, before
            assert att._identity(before) == att._identity(os.fstat(fd))
        finally:
            os.close(fd)
    # The shared realm-owner walker has its own descriptor/ACL/custody tests.
    monkeypatch.setattr(att, "_native_open", opened)
    binary = root / "claude"
    binary.write_bytes(b"qualified native CLI"); binary.chmod(0o555)
    sdk = root / "sdk"; (sdk / "bin").mkdir(parents=True)
    python = sdk / "bin/python3.12"
    python.write_bytes(b"qualified SDK interpreter"); python.chmod(0o555)
    package = sdk / "package.py"; package.write_bytes(b"sdk implementation"); package.chmod(0o444)
    cli_source = root / "cli-install.json"
    cli_source.write_text(json.dumps({"schema":"mastermind.claude_native_host_provision.v1",
        "status":"PROVISIONED_NOT_AUTHENTICATED", "binary":str(binary),
        "binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),
        "version_under_principal":f"{att.CLI_VERSION} (Claude Code)"}))
    sdk_source = root / "sdk-install.json"
    sdk_source.write_text(json.dumps({"status":"INSTALLED_IMPORT_PROVEN", "target":str(sdk),
        "python_path":str(python), "python_sha256":hashlib.sha256(python.read_bytes()).hexdigest(),
        "import_probe":{"sdk":att.SDK_VERSION}}))
    cli_source.chmod(0o600); sdk_source.chmod(0o400)
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        assert argv[0] == "/usr/bin/codesign"
        return SimpleNamespace(stderr=f"TeamIdentifier={att.CLAUDE_TEAM}\n".encode())
    monkeypatch.setattr(att.subprocess, "run", command)
    args = dict(binary_path=binary, sdk_python=python,
        cli_provision_receipt=cli_source, cli_receipt_sha256=hashlib.sha256(cli_source.read_bytes()).hexdigest(),
        sdk_provision_receipt=sdk_source, sdk_receipt_sha256=hashlib.sha256(sdk_source.read_bytes()).hexdigest())
    document = att.build_native_claude_attestation(**args)
    receipt = root / "attestation.json"
    def publish(value=document):
        receipt.chmod(0o600) if receipt.exists() else None
        receipt.write_text(json.dumps(value))
        os.chown(receipt, -1, os.getegid())
        receipt.chmod(0o440)
    publish()
    def load():
        return att.load_native_claude_attestation(receipt, expected_binary_path=binary,
            expected_owner_gid=os.getegid(), allowed_versions=frozenset({att.CLI_VERSION}), sdk_python=python)
    return SimpleNamespace(root=root,binary=binary,sdk=sdk,python=python,package=package,
        args=args,document=document,receipt=receipt,publish=publish,load=load,calls=calls)


def test_reader_reuses_installed_authority_without_launching_provider(installation):
    i=installation; calls=len(i.calls); result=i.load()
    assert result.path==str(i.binary) and result.sha256==i.document['cli']['sha256']
    assert result.team_identifier==att.CLAUDE_TEAM
    assert len(i.calls)==calls




def test_v2_receipt_excludes_boot_local_device_identity(installation):
    i = installation
    assert i.document["schema_version"] == att.SCHEMA
    assert att.SCHEMA.endswith("/v2")
    assert "device" not in i.document["cli"]["identity"]
    assert "device" not in i.document["sdk"]["python"]["identity"]
    assert set(i.document["cli"]["identity"]) == set(att._DURABLE_IDENTITY)


def test_device_renumber_after_receipt_does_not_invalidate_durable_installation(
    installation, monkeypatch
):
    i = installation
    original = att._identity
    original_device = os.stat(i.binary).st_dev

    def renumbered(info):
        value = original(info)
        value["device"] += 4096
        return value

    monkeypatch.setattr(att, "_identity", renumbered)
    result = i.load()
    assert result.sha256 == i.document["cli"]["sha256"]
    assert result.inode == i.document["cli"]["identity"]["inode"]
    assert result.device == original_device + 4096


def test_same_bytes_replaced_cli_is_stale(installation):
    i=installation; data=i.binary.read_bytes(); i.binary.unlink(); i.binary.write_bytes(data);i.binary.chmod(0o555)
    with pytest.raises(att.NativeAttestationError,match='executable changed'):i.load()


@pytest.mark.parametrize('change',['content','new-file','symlink','hardlink','writable'])
def test_sdk_postimage_drift_refuses(installation,change):
    i=installation
    if change=='content':i.package.chmod(0o644);i.package.write_bytes(b'changed SDK content');i.package.chmod(0o444)
    elif change=='new-file':(i.sdk/'unexpected.py').write_bytes(b'new import')
    elif change=='symlink':(i.sdk/'alias').symlink_to(i.package)
    elif change=='hardlink':os.link(i.package,i.sdk/'alias')
    else:i.package.chmod(0o666)
    with pytest.raises(att.NativeAttestationError):i.load()


@pytest.mark.parametrize('change',['unknown','signer','sdk-version','count-bool','identity-bool','source','timestamp','digest'])
def test_closed_receipt_and_qualified_identity(installation,change):
    i=installation; d=i.document
    if change=='unknown':d['extra']=True
    elif change=='signer':d['cli']['team_identifier']='another-provider'
    elif change=='sdk-version':d['sdk']['version']='0.0.0'
    elif change=='count-bool':d['sdk']['entries']=True
    elif change=='identity-bool':d['cli']['identity']['uid']=False
    elif change=='source':d['source_receipts']={}
    elif change=='timestamp':d['recorded_at']='2026-09-27T00:00:00'
    else:d['sdk']['identity_sha256']='broken'
    i.publish()
    with pytest.raises(att.NativeAttestationError):i.load()


@pytest.mark.parametrize('mode',[0o400,0o444,0o640,0o660])
def test_receipt_exact_consumer_mode(installation,mode):
    i=installation;i.receipt.chmod(mode)
    with pytest.raises(att.NativeAttestationError,match='mode/group'):i.load()


def test_duplicate_receipt_field_refuses(installation):
    i=installation;i.receipt.chmod(0o600)
    raw=i.receipt.read_text();i.receipt.write_text('{"schema_version":"forged",'+raw[1:]);i.receipt.chmod(0o440)
    with pytest.raises(att.NativeAttestationError,match='duplicate'):i.load()


def test_producer_rejects_changed_provision_receipt(installation):
    i=installation;args={**i.args,'cli_receipt_sha256':'0'*64}
    with pytest.raises(att.NativeAttestationError,match='source receipt'):att.build_native_claude_attestation(**args)


def test_reader_refuses_cli_replacement_during_sdk_observation(installation,monkeypatch):
    i=installation; original=att._sdk_tree
    def observe(root,**kwargs):
        result=original(root,**kwargs)
        data=i.binary.read_bytes();i.binary.unlink();i.binary.write_bytes(data);i.binary.chmod(0o555)
        return result
    monkeypatch.setattr(att,'_sdk_tree',observe)
    with pytest.raises(att.NativeAttestationError,match='during SDK'):i.load()
