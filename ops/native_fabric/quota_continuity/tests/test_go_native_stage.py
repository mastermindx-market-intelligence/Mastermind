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
    default, application, http = root / "default", root / "application", root / "http"
    for output, extra in ((default, []), (application, ["--include-go-application"]),
                          (http, ["--include-go-application", "--include-application-http"])):
        with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *extra]), redirect_stdout(io.StringIO()):
            builder.main()
    yield SimpleNamespace(default=default, application=application, http=http)
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


def test_default_build_stays_exact_reviewed_104_and_go_adds_only_the_fixed_pair(builds):
    default_raw = (builds.default / "native-manifest.json").read_bytes()
    default = json.loads(default_raw)
    application = json.loads((builds.application / "native-manifest.json").read_bytes())
    assert len(default) == 104
    captured = {name: g.digest((ROOT / "candidate" / name).read_bytes())
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(default, captured)
    assert default["ext/pick.py"] == builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["pick.py"]
    historical = dict(default)
    historical.update({"ext/" + name: value for name, value in builder.GO_BASE_DEPENDENCIES.items()})
    historical["ext/pick.py"] = builder.GO_BASE_PICKER_SHA256
    historical.update({"ext/" + name: value for name, value in builder.GO_SELECTION_SUPPORT_PREIMAGES.items()})
    assert default["ext/provider_outcome.py"] == builder.GO_PROTECTED_PROVIDER_OUTCOME_SHA256
    historical["ext/provider_outcome.py"] = builder.GO_BASE_PROVIDER_OUTCOME_SHA256
    for name, original in builder.GO_COMPLETED_POLL_PREIMAGES.items():
        assert default["ext/" + name] == builder.GO_COMPLETED_POLL_DIGESTS[name]
        historical["ext/" + name] = original
    for name, original in builder.GO_POST_FAILURE_PREIMAGES.items():
        assert default["ext/" + name] == builder.GO_POST_FAILURE_DIGESTS[name]
        historical["ext/" + name] = original
    for name, digest in builder.GO_POST_FAILURE_ADDITIONS.items():
        assert default["ext/" + name] == digest
        del historical["ext/" + name]
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == builder.GO_BASE_MANIFEST_SHA256
    assert {k: v for k, v in application.items() if k in default} == default
    assert set(application) - set(default) == {g.GO_ENTRY, g.GO_HANDLER}
    assert len(application) == 106
    inventory = json.loads((builds.application / "native-source-inventory.json").read_bytes())
    component = json.loads((builds.application / "external-go-component/component.json").read_bytes())
    assert component["native_stage_dependencies"] == {n: application["ext/" + n] for n in builder.GO_APPLICATION_DEPENDENCIES}
    assert component["candidate_sha256"] == application[g.GO_HANDLER]
    for path, expected in application.items():
        raw = (builds.application / "native-code-stage" / path).read_bytes()
        assert g.digest(raw) == expected == inventory["files"][path]["sha256"]
        assert len(raw) == inventory["files"][path]["bytes"]


def test_exact_historical_picker_remains_a_valid_base_but_no_arbitrary_fourth_member(builds):
    manifest = json.loads((builds.default / "native-manifest.json").read_bytes())
    captured = {name: manifest["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    historical = dict(manifest)
    historical["ext/pick.py"] = builder.GO_BASE_PICKER_SHA256
    builder.validate_go_base_manifest(historical, captured)
    for digest in (builder.GO_BASE_PROVIDER_OUTCOME_SHA256,
                   builder.GO_PROTECTED_PROVIDER_OUTCOME_SHA256):
        exact = dict(manifest)
        exact["ext/provider_outcome.py"] = digest
        builder.validate_go_base_manifest(exact, captured)
    for member in ("ext/pick.py", "ext/model_tier.py", "ext/quota_circuit.py",
                   "ext/pool_ledger.py", "ext/provider_outcome.py"):
        bad = dict(manifest)
        bad[member] = "f" * 64
        with pytest.raises(ValueError):
            builder.validate_go_base_manifest(bad, captured)
    bad = dict(manifest, unexpected="f" * 64)
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(bad, captured)


@pytest.mark.parametrize("corruption", ["handler", "dependency", "base", "picker", "provider-outcome", "post-failure", "other-member", "entry-symlink"])
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
    elif corruption == "picker":
        manifest["ext/pick.py"] = "0" * 64
    elif corruption == "provider-outcome":
        manifest["ext/provider_outcome.py"] = "0" * 64
    elif corruption == "post-failure":
        manifest["ext/post_failure_observation.py"] = "0" * 64
    elif corruption == "other-member":
        manifest["ext/model_tier.py"] = "0" * 64
    else:
        root = tmp_path / "source"
        (root / "candidate").mkdir(parents=True)
        (root / "candidate/native_go_entry.py").symlink_to(ROOT / "candidate/native_go_entry.py")
    with pytest.raises(ValueError):
        builder.compose_go_stage(root, output, manifest, inventory["files"], component)
    assert not (output / "native-code-stage" / g.GO_ENTRY).exists()
    assert not (output / "native-code-stage" / g.GO_HANDLER).exists()

def test_exact_post_failure_cohort_and_prior_102_are_both_closed(builds):
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = dict(current)
    for name, original in builder.GO_COMPLETED_POLL_PREIMAGES.items():
        prior["ext/" + name] = original
    for name, original in builder.GO_POST_FAILURE_PREIMAGES.items():
        prior["ext/" + name] = original
    for name in builder.GO_POST_FAILURE_ADDITIONS:
        del prior["ext/" + name]
    assert len(prior) == 102
    builder.validate_go_base_manifest(prior, captured)
    members = set(builder.GO_POST_FAILURE_PREIMAGES) | set(builder.GO_POST_FAILURE_ADDITIONS)
    for name in members:
        bad = dict(current)
        bad["ext/" + name] = "f" * 64
        with pytest.raises(ValueError):
            builder.validate_go_base_manifest(bad, captured)
    for name in builder.GO_POST_FAILURE_ADDITIONS:
        partial = dict(current)
        del partial["ext/" + name]
        with pytest.raises(ValueError):
            builder.validate_go_base_manifest(partial, captured)
    missing_both = {k: v for k, v in current.items()
                    if k not in {"ext/" + n for n in builder.GO_POST_FAILURE_ADDITIONS}}
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(missing_both, captured)
    mixed = dict(current)
    name = next(iter(builder.GO_POST_FAILURE_PREIMAGES))
    mixed["ext/" + name] = builder.GO_POST_FAILURE_PREIMAGES[name]
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(mixed, captured)


def test_completed_poll_pair_is_closed_and_cannot_relabel_historical_102(builds):
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(current, captured)
    pre_poll = dict(current)
    pre_poll.update({"ext/" + name: digest
                     for name, digest in builder.GO_COMPLETED_POLL_PREIMAGES.items()})
    builder.validate_go_base_manifest(pre_poll, captured)
    for name, original in builder.GO_COMPLETED_POLL_PREIMAGES.items():
        for digest in (original, "f" * 64):
            mixed = dict(current)
            mixed["ext/" + name] = digest
            with pytest.raises(ValueError, match="completed-poll cohort"):
                builder.validate_go_base_manifest(mixed, captured)
    synthetic_prior = dict(current)
    synthetic_prior.update({"ext/" + name: digest
                            for name, digest in builder.GO_POST_FAILURE_PREIMAGES.items()})
    for name in builder.GO_POST_FAILURE_ADDITIONS:
        del synthetic_prior["ext/" + name]
    assert len(synthetic_prior) == 102
    with pytest.raises(ValueError, match="completed-poll cohort"):
        builder.validate_go_base_manifest(synthetic_prior, captured)
