"""Closed native Go build and shared disposable publication fixtures."""
from contextlib import contextmanager, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = ROOT / "rollout"
sys.path.insert(0, str(ROLLOUT))
import build_review_stage as builder
import native_generation as g
import native_install as installer


def unseal(root):
    for directory, _, _ in os.walk(root, followlinks=False):
        os.chmod(directory, 0o700)


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("go-reviewed-build").resolve()
    default, application = root / "default", root / "application"
    for output, extra in ((default, []), (application, ["--include-go-application"])):
        with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *extra]), redirect_stdout(io.StringIO()):
            builder.main()
    yield SimpleNamespace(default=default, application=application)
    unseal(root)


@pytest.fixture(scope="module")
def native_stage(builds):
    return builds.application


@pytest.fixture
def published(native_stage, tmp_path):
    root = tmp_path.resolve()
    ext = root / "kit/ext"
    for relative in ("go_shim", "glm_shim", "state", "broker"):
        (ext / relative).mkdir(parents=True)
    (root / "kit/orch/fabric").mkdir(parents=True)
    original = ext / "go_shim/go_shim.py"
    original.write_bytes((ROOT / "source/go_shim.py").read_bytes())
    helper = ROOT.parent / "paid_canonical_glm/source/glm_shim.py"
    (ext / "glm_shim/glm_shim.py").write_bytes(helper.read_bytes())
    profile = root / "profile/accounts.json"
    profile.parent.mkdir(mode=0o700)
    profile.write_text(json.dumps({"account-a": {"api_key": "fixture-provider-a"}}))
    profile.chmod(0o600)
    (ext / "go_shim/.token").write_text("fixture-controller-credential-0123456789")
    (ext / "go_shim/.token").chmod(0o600)
    prices = {"models": {"fixture-model": {"rows": [{"monthly_usd": "20", "in": "1", "out": "1", "cached_read": "0", "cache_write": "0"}]}}, "unpriced": []}
    (ext / "go_shim/go_prices.json").write_text(json.dumps(prices))
    (ext / "go_shim/model_tiers.json").write_text(json.dumps({"models": {"fixture-model": {"weight": 1}}}))
    (ext / "go_shim/wire_matrix.json").write_text("{}")
    (ext / "state/go_wire_compat.json").write_text("{}")
    (ext / "hosts.json").write_text("{}")
    (root / "kit/orch/fabric/accounts.yaml").write_text("{}")
    (root / "kit/orch/fabric/status.json").write_text("{}")
    sqlite3.connect(ext / "broker/leases.sqlite").close()
    manifest = json.loads((native_stage / "native-manifest.json").read_bytes())
    release = g.publish(native_stage / "native-code-stage", ext, manifest)
    store = ext.parent / g.STORE_NAME
    selection = g.select(store, release.name, None)
    _, meta = g.verify(store, release.name)
    yield SimpleNamespace(root=root, ext=ext, original=original, profile=profile,
        release=release, store=store, meta=meta, manifest=manifest, selection=selection)
    unseal(root)


@contextmanager
def loaded_entry(published, *, clean_yaml=False):
    names = {Path(p).stem for p in published.manifest if p.startswith("ext/") and p.endswith(".py")}
    names.add("glm_shim")
    if clean_yaml:
        names.update(n for n in sys.modules if n == "yaml" or n.startswith("yaml."))
    previous = {name: sys.modules[name] for name in names if name in sys.modules}
    path_before = list(sys.path)
    for name in names:
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("native_go_entry", published.release / "ext/native_go_entry.py")
    entry = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = entry
    spec.loader.exec_module(entry)
    try:
        yield entry
    finally:
        for name in names:
            sys.modules.pop(name, None)
        for name in list(sys.modules):
            if clean_yaml and (name == "yaml" or name.startswith("yaml.")):
                sys.modules.pop(name, None)
        sys.modules.update(previous)
        sys.path[:] = path_before


def test_default_build_stays_exact_B102_and_go_adds_only_the_fixed_pair(builds):
    default_raw = (builds.default / "native-manifest.json").read_bytes()
    default = json.loads(default_raw)
    application = json.loads((builds.application / "native-manifest.json").read_bytes())
    assert len(default) == 102 and g.digest(default_raw) == builder.GO_BASE_MANIFEST_SHA256
    assert {k: v for k, v in application.items() if k in default} == default
    assert set(application) - set(default) == {g.GO_ENTRY, g.GO_HANDLER}
    assert len(application) == 104
    inventory = json.loads((builds.application / "native-source-inventory.json").read_bytes())
    component = json.loads((builds.application / "external-go-component/component.json").read_bytes())
    assert component["native_stage_dependencies"] == {n: application["ext/" + n] for n in builder.GO_APPLICATION_DEPENDENCIES}
    assert component["candidate_sha256"] == application[g.GO_HANDLER]
    for path, expected in application.items():
        raw = (builds.application / "native-code-stage" / path).read_bytes()
        assert g.digest(raw) == expected == inventory["files"][path]["sha256"]
        assert len(raw) == inventory["files"][path]["bytes"]


@pytest.mark.parametrize("corruption", ["handler", "dependency", "base", "entry-symlink"])
def test_closed_component_drift_refuses_before_go_pair_creation(builds, tmp_path, corruption):
    output = tmp_path / "copy"
    shutil.copytree(builds.default, output)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    component = json.loads((output / "external-go-component/component.json").read_bytes())
    root = ROOT
    if corruption == "handler":
        (output / "external-go-component/go_shim.py").write_bytes(b"wrong")
    elif corruption == "dependency":
        component["native_stage_dependencies"]["lease_broker.py"] = "0" * 64
    elif corruption == "base":
        manifest["ext/lease_broker.py"] = "0" * 64
    else:
        root = tmp_path / "source"
        (root / "candidate").mkdir(parents=True)
        (root / "candidate/native_go_entry.py").symlink_to(ROOT / "candidate/native_go_entry.py")
    with pytest.raises(ValueError):
        builder.compose_go_stage(root, output, manifest, inventory["files"], component)
    assert not (output / "native-code-stage" / g.GO_ENTRY).exists()
    assert not (output / "native-code-stage" / g.GO_HANDLER).exists()
