"""Hermetic tests: source bundle verification NEVER changes a live Fabric tree."""
from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "ops/native_fabric/verify_selector_source_bundle.py"
SPEC = importlib.util.spec_from_file_location("verify_selector_source_bundle", SOURCE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

PAIRS = {
    "ext/fabric_task.py": (b"old fabric\n", b"new fabric\n"),
    "ext/pick.py": (b"old picker\n", b"final picker\n"),
    "ext/lease_broker.py": (b"old broker\n", b"new broker\n"),
    "ext/tests/test_r31_glm_burn_down.py": (b"old policy test\n", b"new policy test\n"),
    "ext/tests/test_pick_policy.py": (b"old picker test\n", b"new picker test\n"),
    "bin/pool": (b"old wrapper\n", b"new wrapper\n"),
}
PATCH_NAMES = (
    "fabric_task_expiry_host_select_20261012_v2.patch",
    "pick_exact_model_selection_20261012.patch",
    "pick_glm_paired_window_urgency_20261012.patch",
    "lease_broker_glm_expiry_preference_20261013.patch",
    "test_r31_paired_quota_truth_20261012.patch",
    "test_pick_policy_host_mock_20261013.patch",
    "pool_cli_selector_20261012.patch",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _patch(path: str, old: bytes, new: bytes) -> bytes:
    text = "".join(difflib.unified_diff(
        old.decode().splitlines(True), new.decode().splitlines(True),
        fromfile="a/" + path, tofile="b/" + path, n=3,
    ))
    return text.encode()


@pytest.fixture
def kit(tmp_path):
    ext = tmp_path / "installed" / "ext"
    bundle = tmp_path / "bundle"
    ext.mkdir(parents=True)
    patch_dir = bundle / "ops/native_fabric/patches"
    patch_dir.mkdir(parents=True)
    originals = {}
    sources = []
    wrapper = tmp_path / "installed-pool"
    for name,(before,after) in PAIRS.items():
        target = (wrapper if name == "bin/pool"
                  else ext / Path(name).relative_to("ext"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(before)
        originals[name]=before
        sources.append({"path":name,"sha256":_sha(before),"patched_sha256":_sha(after)})
    script_patches=[
        _patch("ext/fabric_task.py",b"old fabric\n",b"new fabric\n"),
        _patch("ext/pick.py",b"old picker\n",b"mid picker\n"),
        _patch("ext/pick.py",b"mid picker\n",b"final picker\n"),
        _patch("ext/lease_broker.py",b"old broker\n",b"new broker\n"),
        _patch("ext/tests/test_r31_glm_burn_down.py",b"old policy test\n",b"new policy test\n"),
        _patch("ext/tests/test_pick_policy.py",b"old picker test\n",b"new picker test\n"),
        _patch("bin/pool",b"old wrapper\n",b"new wrapper\n"),
    ]
    manifests=[]
    for name,source in zip(PATCH_NAMES,script_patches):
        patch=patch_dir/name
        patch.write_bytes(source)
        manifests.append({
            "path": "ops/native_fabric/patches/" + name,
            "sha256": _sha(source),
        })
    data={
        "schema":"mastermind.fabric_selector_source_bundle.v1",
        "mode":"SOURCE_ONLY_PREFLIGHT",
        "live_install_supported":False,
        "sources":sources,
        "patches":manifests,
    }
    manifest = bundle / "ops/native_fabric/selector_source_bundle_20261012.json"
    manifest.write_text(json.dumps(data,sort_keys=True))
    return ext,bundle,manifest,originals,wrapper


def test_complete_replay_verifies_and_leaves_original_source_unchanged(kit):
    ext,bundle,manifest,originals,wrapper=kit
    result=module.verify(ext,bundle,manifest,wrapper)
    assert result["result"]=="QUALIFIED_SOURCE_ONLY"
    assert result["patches_verified"]==7
    assert result["sources_verified"]==6
    assert result["live_source_modified"] is False
    assert result["account_or_lease_modified"] is False
    assert result["production_installed"] is False
    for name,raw in originals.items():
        file = wrapper if name == "bin/pool" else ext/Path(name).relative_to("ext")
        assert file.read_bytes()==raw
        assert result["targets"][name]==_sha(PAIRS[name][1])


@pytest.mark.parametrize("case,expected",[
    ("source_drift","SOURCE_DRIFT"),
    ("patch_drift","PATCH_DRIFT"),
    ("source_symlink","SOURCE_NOT_BOUNDED_REGULAR"),
    ("wrong_patched_digest","PATCH_RESULT_DRIFT"),
    ("missing_patch","FileNotFoundError"),
    ("wrapper_drift","SOURCE_DRIFT:bin/pool"),
    ("wrapper_symlink","SOURCE_NOT_BOUNDED_REGULAR:installed-pool"),
])
def test_error_prevents_installation_and_does_not_modify_inputs(kit,case,expected):
    ext,bundle,manifest,originals,wrapper=kit
    data=json.loads(manifest.read_text())
    if case=="source_drift":
        (ext/"fabric_task.py").write_text("altered source\n")
    elif case=="patch_drift":
        (bundle/data["patches"][0]["path"]).write_text("altered patch\n")
    elif case=="source_symlink":
        item=ext/"fabric_task.py"
        outside=ext.parent/"safe-target"
        outside.write_text("different source")
        item.unlink();item.symlink_to(outside)
    elif case=="wrong_patched_digest":
        data["sources"][1]["patched_sha256"]="0"*64
        manifest.write_text(json.dumps(data))
    elif case=="missing_patch":
        (bundle/data["patches"][0]["path"]).unlink()
    elif case=="wrapper_drift":
        wrapper.write_text("modified wrapper\n")
    elif case=="wrapper_symlink":
        target=ext.parent/"existing-wrapper-target"
        target.write_text("safe test data")
        wrapper.unlink();wrapper.symlink_to(target)
    with pytest.raises((module.PreflightRefusal,OSError)) as error:
        module.verify(ext,bundle,manifest,wrapper)
    message=str(error.value)
    assert expected in message or (case=="missing_patch" and isinstance(error.value,FileNotFoundError))
    # The other untouched source inputs remain untouched.
    for name,raw in originals.items():
        if (case in ("source_drift", "source_symlink")
                and name=="ext/fabric_task.py") or (
                case in ("wrapper_drift", "wrapper_symlink") and name=="bin/pool"
        ):
            continue
        file = wrapper if name == "bin/pool" else ext/Path(name).relative_to("ext")
        assert file.read_bytes()==raw


def test_manifest_refuses_install_mode(kit):
    ext,bundle,manifest,_,wrapper=kit
    data=json.loads(manifest.read_text())
    data["live_install_supported"]=True
    manifest.write_text(json.dumps(data))
    with pytest.raises(module.PreflightRefusal,match="INVALID_MANIFEST_SCHEMA"):
        module.verify(ext,bundle,manifest,wrapper)


@pytest.mark.parametrize("bad", [
    "../../private/file", "/etc/passwd", "ext/../../file",
    "ops/native_fabric/patches/../../escape", "",
])
def test_relative_path_validation_cannot_escape_working_copy(bad):
    with pytest.raises(module.PreflightRefusal):
        module._relative(bad,"ops/native_fabric/patches/")


def test_input_source_move_during_replay_is_detected(kit,monkeypatch):
    ext,bundle,manifest,_,wrapper=kit
    real_run=subprocess.run
    altered=[False]
    def wrapped_run(args,*a,**kw):
        result=real_run(args,*a,**kw)
        if (not altered[0] and result.returncode==0
                and "--check" not in args and args[:2]==["git","apply"]):
            (ext/"pick.py").write_text("changed during preflight\n")
            altered[0]=True
        return result
    monkeypatch.setattr(module.subprocess,"run",wrapped_run)
    with pytest.raises(module.PreflightRefusal,match="SOURCE_MOVED_DURING_PREFLIGHT"):
        module.verify(ext,bundle,manifest,wrapper)
    assert altered[0]


def test_replay_never_executes_shell_or_installer(kit,monkeypatch):
    ext,bundle,manifest,_,wrapper=kit
    real_run=subprocess.run
    seen=[]
    def wrapped_run(args,*a,**kw):
        seen.append((args,kw))
        assert args[:2]==["git","apply"]
        assert kw.get("shell") is None
        assert str(ext) != str(kw.get("cwd"))
        assert kw.get("timeout") == 15
        return real_run(args,*a,**kw)
    monkeypatch.setattr(module.subprocess,"run",wrapped_run)
    assert module.verify(ext,bundle,manifest,wrapper)["result"]=="QUALIFIED_SOURCE_ONLY"
    assert len(seen)==14  # seven check+apply pairs
