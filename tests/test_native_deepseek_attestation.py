"""Root/package currentness falsifiers; only virtual root custody, no provider."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import native_provider_attestation as att
from integrations.deepseek_harness import package_attended as package


@pytest.fixture
def deepseek_installation(tmp_path, monkeypatch):
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
    monkeypatch.setattr(att, "_native_open", opened)
    # Root path/descriptor/ACL ownership has independent real walker tests.
    # The package traversal, identities and content below are actual files.
    monkeypatch.setattr(att, "has_macos_acl", lambda *a, **kw: False)
    binary = root / "node"; binary.write_bytes(b"fixture Node executable"); binary.chmod(0o555)
    release = root / "release"; release.mkdir()
    entry = release / att.DSH_ENTRYPOINT; entry.write_bytes(b"// fixed compiled entry\n"); entry.chmod(0o444)
    (release / "app/node_modules/.pnpm/pkg/node_modules/pkg").mkdir(parents=True)
    payload = release / "app/node_modules/.pnpm/pkg/node_modules/pkg/index.js"
    payload.write_bytes(b"exports.fixture = true;\n"); payload.chmod(0o444)
    link = release / "app/node_modules/pkg"
    link.symlink_to(".pnpm/pkg/node_modules/pkg")
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        assert argv == [str(binary), "--version"]
        return SimpleNamespace(stdout=b"v26.5.0\n", stderr=b"")
    monkeypatch.setattr(att.subprocess, "run", command)
    qualified = {}
    def qualify(**kwargs):
        assert kwargs == dict(release=release, source_repo=root, source_sha="a"*40)
        return dict(qualified)
    monkeypatch.setattr(package, "qualify_native_worker_package", qualify)
    from ops.executive_os import install_source_policy
    monkeypatch.setattr(install_source_policy, "validate_acceptance_source",
                        lambda **kw: "b"*40)
    manifest = release / "package-manifest.json"
    args = dict(binary_path=binary, release=release, source_repo=root, source_sha="a"*40)
    def build():
        manifest.chmod(0o644) if manifest.exists() else None
        files = package.inventory(release); files.pop("package-manifest.json", None)
        manifest.write_text(json.dumps({"schema": "mastermind.dsh_attended_package_closure.v1",
            "donor_sha": att.DSH_DONOR_SHA, "files": files, "installed": False}))
        manifest.chmod(0o444)
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        worker = dict(schema="mastermind.dsh_native_worker_entry/v1", entry=att.DSH_ENTRYPOINT,
            sha256=sha(entry), agent_name=att.DSH_PROTOCOL_NAME,
            agent_version=att.DSH_PROTOCOL_VERSION, model_provider=att.DSH_MODEL_PROVIDER)
        qualified.update(schema="mastermind.dsh_native_worker_qualification/v1",
            source_sha="a"*40, source_tree="b"*40, build_sha256="c"*64,
            package_manifest_sha256=sha(manifest), entrypoint_sha256=sha(entry), native_worker=worker,
            node={"path":str(binary),"sha256":sha(binary)})
        return att.build_native_deepseek_attestation(**args)
    document = build()
    receipt = root / "attestation.json"
    def publish(value=None):
        receipt.chmod(0o600) if receipt.exists() else None
        receipt.write_text(json.dumps(document if value is None else value))
        os.chown(receipt, -1, os.getegid()); receipt.chmod(0o440)
    publish()
    def load():
        return att.load_native_deepseek_attestation(receipt, expected_binary_path=binary,
            expected_release=release, expected_owner_gid=os.getegid(),
            allowed_versions=frozenset({"v26.5.0"}))
    return SimpleNamespace(root=root, release=release, binary=binary, entry=entry,
        payload=payload, link=link, document=document, receipt=receipt,
        publish=publish, load=load, build=build, calls=calls, qualified=qualified)


def test_original_node_package_and_source_guard_without_provider_or_subprocess(deepseek_installation):
    i = deepseek_installation; before = list(i.calls)
    owned = i.load(); owned.require_current()
    assert owned.binary.sha256 == i.document["node"]["sha256"]
    assert owned.binary.version == "v26.5.0"
    assert owned.entrypoint == i.entry and owned.release == i.release
    assert owned.source_digest == hashlib.sha256(i.receipt.read_bytes()).hexdigest()
    assert i.calls == before
    assert "device" not in i.document["node"]["identity"]


@pytest.mark.parametrize("change", ["external-link", "dangling-link", "cycle", "inline", "replace",
    "writable-file", "writable-directory", "unmanifested", "hardlink", "missing-entry"])
def test_package_drift_never_becomes_launch_authority(deepseek_installation, change):
    i = deepseek_installation; owned = i.load()
    if change in {"external-link", "dangling-link", "cycle"}:
        i.link.unlink()
        i.link.symlink_to({"external-link": str(i.root), "dangling-link": "missing",
                          "cycle": "pkg"}[change])
    elif change == "inline":
        i.payload.chmod(0o644); i.payload.write_bytes(b"other implementation\n"); i.payload.chmod(0o444)
    elif change == "replace":
        raw=i.payload.read_bytes();i.payload.unlink();i.payload.write_bytes(raw);i.payload.chmod(0o444)
    elif change == "writable-file": i.payload.chmod(0o666)
    elif change == "writable-directory": i.payload.parent.chmod(0o777)
    elif change == "unmanifested": (i.release/"unexpected.js").write_text("unqualified")
    elif change == "hardlink": os.link(i.payload, i.release/"alias")
    else: i.entry.unlink()
    with pytest.raises((att.NativeAttestationError, OSError)): owned.require_current()
    with pytest.raises(att.NativeAttestationError): i.load()


def test_absolute_contained_link_preserves_existing_manifest_semantics(deepseek_installation):
    i = deepseek_installation; i.link.unlink(); i.link.symlink_to(i.payload.parent)
    i.document = i.build(); i.publish(i.document)
    i.load().require_current()


def test_receipt_same_bytes_replacement_revokes_retained_source_capability(deepseek_installation):
    i=deepseek_installation; owned=i.load()
    raw=i.receipt.read_bytes();i.receipt.unlink();i.receipt.write_bytes(raw)
    os.chown(i.receipt,-1,os.getegid());i.receipt.chmod(0o440)
    with pytest.raises(att.NativeAttestationError,match="receipt changed"):owned.require_current()


def test_receipt_replacement_during_package_observation_refuses(deepseek_installation, monkeypatch):
    i=deepseek_installation; original=att._deepseek_tree
    def changed(root, **kwargs):
        result=original(root,**kwargs);i.publish();return result
    monkeypatch.setattr(att,"_deepseek_tree",changed)
    with pytest.raises(att.NativeAttestationError,match="receipt changed"):i.load()


def test_link_retargeting_during_read_refuses(deepseek_installation,monkeypatch):
    i=deepseek_installation; original=att.os.readlink
    def changed(name,*args,**kwargs):
        result=original(name,*args,**kwargs)
        if name=="pkg" and "dir_fd" in kwargs:
            i.link.unlink();i.link.symlink_to("missing")
        return result
    monkeypatch.setattr(att.os,"readlink",changed)
    with pytest.raises(att.NativeAttestationError,match="link changed"):i.load()


def test_acl_on_original_package_entry_refuses(deepseek_installation,monkeypatch):
    i=deepseek_installation
    monkeypatch.setattr(att,"has_macos_acl",lambda path,**kw: Path(path)==i.payload.parent)
    with pytest.raises(att.NativeAttestationError,match="custody"):i.load()


@pytest.mark.parametrize("change", ["schema","old-entry","extra","count-bool","identity-bool",
    "donor","protocol","source","digest","node-version","mode"])
def test_closed_root_receipt_cannot_select_another_launch(deepseek_installation,change):
    i=deepseek_installation;d=json.loads(json.dumps(i.document))
    if change=="schema":d["schema_version"]="mastermind.native_claude_attestation/v2"
    elif change=="old-entry":d["qualification"]["native_worker"]["entry"]="launch_attended.mjs"
    elif change=="extra":d["caller_ready"]=True
    elif change=="count-bool":d["package"]["entries"]=True
    elif change=="identity-bool":d["node"]["identity"]["uid"]=False
    elif change=="donor":d["package"]["donor_sha"]="d"*40
    elif change=="protocol":d["qualification"]["native_worker"]["agent_version"]="unqualified"
    elif change=="source":d["qualification"]["source_sha"]="a"*64
    elif change=="digest":d["qualification"]["build_sha256"]="broken"
    elif change=="node-version":d["node"]["version"]="26.5.0"
    i.publish(d)
    if change=="mode":i.receipt.chmod(0o444)
    with pytest.raises(att.NativeAttestationError):i.load()


@pytest.mark.parametrize("kind", ["entries","bytes","depth","path"])
def test_fixed_package_bounds_refuse(deepseek_installation,monkeypatch,kind):
    i=deepseek_installation
    monkeypatch.setattr(att,{"entries":"_DSH_ENTRIES","bytes":"_DSH_BYTES",
        "depth":"_DSH_DEPTH","path":"_DSH_PATH_BYTES"}[kind],1)
    with pytest.raises(att.NativeAttestationError):i.load()


@pytest.mark.parametrize("change", ["entrypoint","source_digest","source_sha"])
def test_nominal_source_binding_cannot_be_replaced(deepseek_installation,change):
    from dataclasses import replace
    i=deepseek_installation;owned=i.load()
    value={"entrypoint":i.release/"launch_attended.mjs","source_digest":"a"*64,"source_sha":"d"*40}[change]
    with pytest.raises(att.NativeAttestationError):
        replace(owned,**{change:value}).require_current()


def test_oversized_receipt_refuses_before_body_hash(deepseek_installation,monkeypatch):
    i=deepseek_installation
    i.receipt.chmod(0o600)
    i.receipt.write_bytes(b"x"*(att._LIMIT+1));i.receipt.chmod(0o440)
    monkeypatch.setattr(att,"_read",lambda *a,**kw:pytest.fail("oversized receipt body read"))
    with pytest.raises(att.NativeAttestationError,match="exceeds its bound"):i.load()


def test_package_budget_precedes_protected_inventory(deepseek_installation,monkeypatch):
    i=deepseek_installation
    monkeypatch.setattr(att,"_DSH_ENTRIES",1)
    monkeypatch.setattr(package,"qualify_native_worker_package",
                        lambda **kw:pytest.fail("unbounded qualification before custody"))
    with pytest.raises(att.NativeAttestationError,match="entry bound"):
        att.build_native_deepseek_attestation(binary_path=i.binary,release=i.release,
                                             source_repo=i.root,source_sha="a"*40)


def test_protected_node_mismatch_refuses_before_version_probe(deepseek_installation,monkeypatch):
    i=deepseek_installation;i.qualified["node"]={"path":str(i.binary),"sha256":"f"*64}
    monkeypatch.setattr(att.subprocess,"run",lambda *a,**kw:pytest.fail("foreign Node executed"))
    with pytest.raises(att.NativeAttestationError,match="Node differs from protected"):
        att.build_native_deepseek_attestation(binary_path=i.binary,release=i.release,
                                             source_repo=i.root,source_sha="a"*40)


def test_source_changed_during_root_observation_refuses(deepseek_installation,monkeypatch):
    i=deepseek_installation
    from ops.executive_os import install_source_policy
    monkeypatch.setattr(install_source_policy,"validate_acceptance_source",lambda **kw:"f"*40)
    with pytest.raises(att.NativeAttestationError,match="protected source changed"):
        att.build_native_deepseek_attestation(binary_path=i.binary,release=i.release,
                                             source_repo=i.root,source_sha="a"*40)
