"""Offline checks of the actual current-selection adapter and publisher.

The fixture uses only disposable source and state roots. No runtime selection,
provider call, grant, or accepted artifact is created.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

sys.dont_write_bytecode = True
ROOT = Path(os.environ["H6_COMMON_FENCE_SOURCE"]).resolve()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

G = load("h6_reader_native_generation", ROOT / "rollout/native_generation.py")
B = load("h6_reader_native_bindings", ROOT / "ext/native_runtime_bindings.py")
S = load("h6_reader_support_bundle", ROOT / "ext/support_bundle.py")

@pytest.fixture
def release(tmp_path):
    base = tmp_path.resolve()
    stable = base / "kit" / "ext"
    stable.mkdir(parents=True, mode=0o700)
    (stable / "active").mkdir(mode=0o700)
    (stable.parent / "orch/fabric").mkdir(parents=True, mode=0o700)
    policy = base / "initial-policy.yaml"
    policy.write_bytes(b"pools: {}\n")
    S.ensure_policy(policy, stable, hashlib.sha256(policy.read_bytes()).hexdigest())
    source = base / "source"
    (source / "ext").mkdir(parents=True, mode=0o700)
    names = ("pool", "ext/fabric_task.py", "ext/remote_sub.sh",
             "ext/native_runtime_bindings.py", "ext/support_bundle.py")
    for name in names:
        shutil.copyfile(ROOT / name, source / name)
    files = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
             for name in names}
    first = G.publish(source, stable, files)
    store = G.store_path(stable)
    selected = G.select(store, first.name, None)
    return dict(base=base, stable=stable, source=source, names=names,
                first=first, store=store, selected=selected)

def pointer(release):
    return release["store"] / "CURRENT.json"

def write_pointer(release, value):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode() + b"\n"
    G.atomic_bytes(pointer(release), raw, 0o600)

def second_selection(release):
    source = release["source"]
    with (source / "pool").open("ab") as handle:
        handle.write(b"\n# disposable successor identity for adapter qualification\n")
    files = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
             for name in release["names"]}
    second = G.publish(source, release["stable"], files)
    selected = G.select(release["store"], second.name, release["first"].name)
    return second, selected

def test_actual_publisher_selection_is_read(release):
    before = {str(p): (p.lstat(), p.read_bytes()) for p in
              (pointer(release), release["first"] / "RELEASE.json")}
    observed = B.require_current_selection(release["first"] / "ext")
    assert observed == release["selected"]
    for name, (info, raw) in before.items():
        p = Path(name)
        after = p.lstat()
        assert p.read_bytes() == raw
        assert (info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns) == (
            after.st_ino, after.st_mode, after.st_mtime_ns, after.st_ctime_ns)
    observed["sequence"] = 400
    assert B.require_current_selection(release["first"] / "ext")["sequence"] == 1

def test_changed_selection_refuses_old_new_claim_but_preserves_original_owner(release):
    first = release["first"]
    second, selected = second_selection(release)
    with pytest.raises(ValueError, match="no longer selected"):
        B.require_current_selection(first / "ext")
    assert B.require_current_selection(second / "ext") == selected
    assert B.owner_path(first / "ext/active/original.json", first / "ext") == (
        release["stable"] / "active/original.json")

def test_environment_label_cannot_replace_canonical_selection(release, monkeypatch):
    monkeypatch.setenv("FABRIC_NATIVE_CODE_GENERATION", "0" * 64)
    assert B.require_current_selection(release["first"] / "ext") == release["selected"]
    second_selection(release)
    monkeypatch.setenv("FABRIC_NATIVE_CODE_GENERATION", release["first"].name)
    with pytest.raises(ValueError, match="no longer selected"):
        B.require_current_selection(release["first"] / "ext")

def test_missing_pointer_refuses_without_breaking_original_owner(release):
    pointer(release).unlink()
    with pytest.raises(ValueError, match="selection unavailable"):
        B.require_current_selection(release["first"] / "ext")
    assert B.owner_path(release["first"] / "ext/active", release["first"] / "ext") == (
        release["stable"] / "active")

@pytest.mark.parametrize("mode", [0o444, 0o644, 0o666, 0o400])
def test_pointer_mode_must_be_exact(release, mode):
    pointer(release).chmod(mode)
    with pytest.raises(ValueError, match="metadata custody"):
        B.require_current_selection(release["first"] / "ext")

@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "fifo"])
def test_pointer_kind_and_link_custody(release, kind):
    path = pointer(release)
    if kind == "hardlink":
        os.link(path, release["base"] / "extra-link")
    else:
        path.unlink()
        if kind == "symlink":
            target = release["base"] / "other-pointer"
            target.write_text(json.dumps(release["selected"]))
            target.chmod(0o600)
            path.symlink_to(target)
        elif kind == "directory":
            path.mkdir(mode=0o700)
        else:
            os.mkfifo(path, mode=0o600)
    with pytest.raises(ValueError):
        B.require_current_selection(release["first"] / "ext")

@pytest.mark.parametrize("raw", [
    b"x" * 4097,
    b'{"schema":',
    b'{"schema":"native-code-selection.v1","schema":"native-code-selection.v1"}',
    b"[]",
    b"null",
])
def test_bounded_strict_json(release, raw):
    write_pointer(release, raw)
    with pytest.raises(ValueError):
        B.require_current_selection(release["first"] / "ext")

@pytest.mark.parametrize("change", [
    {"sequence": True}, {"sequence": 0}, {"sequence": -1},
    {"sequence": "1"}, {"sequence": 1.0},
    {"schema": "other"}, {"generation": "A" * 64},
    {"generation": 1}, {"previous": "invalid"}, {"previous": False},
    {"extra": "not accepted"},
])
def test_exact_selection_schema(release, change):
    write_pointer(release, dict(release["selected"], **change))
    with pytest.raises(ValueError, match="selection malformed"):
        B.require_current_selection(release["first"] / "ext")

def test_missing_selection_field(release):
    value = dict(release["selected"])
    del value["previous"]
    write_pointer(release, value)
    with pytest.raises(ValueError, match="selection malformed"):
        B.require_current_selection(release["first"] / "ext")

@pytest.mark.parametrize("context", ["relative", "flat", "wrong-generation", "symlink"])
def test_only_canonical_native_source_context(release, context):
    if context == "relative":
        here = Path("native-code-releases") / release["first"].name / "ext"
    elif context == "flat":
        here = release["stable"]
    elif context == "wrong-generation":
        here = release["store"] / "not-a-generation" / "ext"
    else:
        alias = release["base"] / "kit-alias"
        alias.symlink_to(release["stable"].parent, target_is_directory=True)
        here = alias / "native-code-releases" / release["first"].name / "ext"
    with pytest.raises(ValueError):
        B.require_current_selection(here)

def test_changed_fixed_alias_refuses(release):
    ext = release["first"] / "ext"
    ext.chmod(0o755)
    (ext / "active").unlink()
    (ext / "active").symlink_to(release["base"] / "other-active")
    ext.chmod(0o555)
    with pytest.raises(ValueError, match="visible alias changed"):
        B.require_current_selection(ext)

def test_changed_release_metadata_refuses(release):
    meta = release["first"] / "RELEASE.json"
    value = json.loads(meta.read_text())
    value["schema"] = "other"
    meta.chmod(0o644)
    meta.write_text(json.dumps(value))
    meta.chmod(0o444)
    with pytest.raises(ValueError, match="metadata shape"):
        B.require_current_selection(release["first"] / "ext")
