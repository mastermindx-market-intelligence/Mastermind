"""Closed native Go build and shared disposable publication fixtures."""
from contextlib import contextmanager, redirect_stdout
import importlib.util
import io
import itertools
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
def native_module_namespace(manifest, *, clean_yaml=False):
    """Own one disposable native namespace and restore every prior module."""
    names = {Path(p).stem for p in manifest if p.startswith("ext/") and p.endswith(".py")}
    names.add("glm_shim")
    if clean_yaml:
        names.update(n for n in sys.modules if n == "yaml" or n.startswith("yaml."))
    previous = {name: sys.modules[name] for name in names if name in sys.modules}
    path_before = list(sys.path)
    for name in names:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in names:
            sys.modules.pop(name, None)
        for name in list(sys.modules):
            if clean_yaml and (name == "yaml" or name.startswith("yaml.")):
                sys.modules.pop(name, None)
        sys.modules.update(previous)
        sys.path[:] = path_before


@contextmanager
def loaded_entry(published, *, clean_yaml=False):
    with native_module_namespace(published.manifest, clean_yaml=clean_yaml):
        spec = importlib.util.spec_from_file_location("native_go_entry", published.release / "ext/native_go_entry.py")
        entry = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = entry
        spec.loader.exec_module(entry)
        yield entry


def test_native_module_namespace_restores_the_exact_foreign_owner(monkeypatch):
    name = "a04_terminal_reconcile"
    original = SimpleNamespace(__file__="fixture:foreign-owner")
    replacement = SimpleNamespace(__file__="fixture:disposable-owner")
    monkeypatch.setitem(sys.modules, name, original)
    paths = list(sys.path)
    with native_module_namespace({"ext/a04_terminal_reconcile.py": "a" * 64}):
        assert name not in sys.modules
        sys.modules[name] = replacement
        sys.path.insert(0, "fixture:temporary-import-path")
    assert sys.modules[name] is original and sys.path == paths


def before_extended_host_pull_epoch(manifest):
    """Reconstruct an exact historical test image; never validate an extended base."""
    historical_by_current = {
        "a3b345e305c34a5f8b6284fc5ee00c36c0ddf274635886038c472eb88284780f": "59e99bc523a627e72b5df97e37c9765eebe61480981b801ab6b9b4165ac469d0",
        "bbc0d92d0d6377603ea162c9f5efe3205069235fc4959d49ab1bddd86520b3af": "8443024b1ad7982ea66747f409b27b0e69abec20af15d662854862a679a781ec",
        "f3d9ae365345a7dddfbe0aba7e257b248684678e821d4dc13f76762f4d9166f2": "acf6fdcc2df38eb2865c83f114e4bfec5c05f7ebfb66c4677ad6cfe87f5aa8c8",
        "38368f3a7d2438a191049088b44000abb3e0fac04a03cff3ffcf016de2fddd44": "7d814132900a7f4bb11ef10c566a4b5d18bb85a3a0b19c2be260cac3270efd61",
    }
    actual = g.digest((json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    assert actual in historical_by_current
    previous = dict(manifest)
    previous.update(builder.HOST_PULL_INTEGRITY_PREIMAGES)
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == historical_by_current[actual]
    return previous


@pytest.mark.parametrize("extended", ["application", "http"])
def test_current_host_pull_epoch_refuses_extended_native_base(builds, extended):
    current = json.loads((getattr(builds, extended) / "native-manifest.json").read_bytes())
    before = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    captured_before = dict(captured)
    with pytest.raises(ValueError, match="native host-pull integrity parent closure differs"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before
    assert captured == captured_before


def before_collection_successor(manifest):
    manifest = builder.before_host_pull_integrity(manifest)
    # Frozen historical tests keep their original bytes. This test-only inverse
    # binds both complete current and prior closures before changing one member.
    previous = dict(manifest)
    key = "ext/original_delivery_collector.py"
    if (previous.get(key) == builder.GO_ORIGINAL_COLLECTION_SUCCESSOR_SHA256
            and previous.get("ext/support_bundle.py") == builder.APPLICATION_POOL_COMPOSITION_DIGESTS["ext/support_bundle.py"]
            and previous.get("ext/remote_sub_exec.py") == builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_DIGEST):
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e"
        previous[key] = builder.GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "0084f7d0a3b78f3c434c872c9bbf2c5ab764f54cf565d5f24c00480a1855cbfe"
    return previous


def before_pool_publisher(manifest):
    # Reconstruct the previously qualified sparse/scoped fixture from the
    # current combined source; the immutable whole parent is checked here.
    previous = before_collection_successor(manifest)
    if previous.get("ext/support_bundle.py") == builder.APPLICATION_POOL_COMPOSITION_DIGESTS["ext/support_bundle.py"]:
        previous["ext/support_bundle.py"] = builder.APPLICATION_POOL_COMPOSITION_PREIMAGES["ext/support_bundle.py"]
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "d416ac1611112f757d602ddc73b4ed61636a7dd53c4b66866ce302aeabd7a86f"
    return previous


def pool_source_fixture(builds):
    raw = (ROOT.parents[2] / "tests/fixtures/fabric-application-pool107-b955c82.json").read_bytes()
    assert g.digest(raw) == "d8a112411c28c42e812907435f5b182ce351a4cb4c00e47b94ca1ddf58294ac9"
    prior = json.loads(raw)
    current = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    assert set(prior) == set(current)
    assert {key for key in current if current[key] != prior[key]} == {
        "ext/remote_sub_exec.py", "ext/original_delivery_collector.py"}
    return prior


def before_exact_scoped_models(manifest):
    previous = before_pool_publisher(manifest)
    if any(previous.get(name) == digest
           for name, digest in builder.EXACT_SCOPED_MODEL_DIGESTS.items()):
        assert {name: previous[name] for name in builder.EXACT_SCOPED_MODEL_DIGESTS} == builder.EXACT_SCOPED_MODEL_DIGESTS
        previous.update(builder.EXACT_SCOPED_MODEL_PREIMAGES)
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "1bb6f2ec3af603e44c345558931d3bf5daec28fa7bc9db14cbad830674ea84d0"
    return previous


def before_sparse_commit_preflight(manifest):
    previous = before_exact_scoped_models(manifest)
    if previous.get("ext/remote_sub_exec.py") == builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_DIGEST:
        previous["ext/remote_sub_exec.py"] = builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_PREIMAGE
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == builder.SPARSE_COMMIT_PREFLIGHT_PARENT_MANIFEST_SHA256
    return previous


def before_admission_integrity(manifest):
    # Historical-generation cases retain their exact parent, while the current
    # build and the new successor tests below inspect the actual repaired bytes.
    manifest = before_collection_successor(manifest)
    if manifest.get("ext/support_bundle.py") == builder.APPLICATION_POOL_COMPOSITION_DIGESTS["ext/support_bundle.py"]:
        previous = builder.before_application_pool_composition(dict(manifest))
        previous = builder.before_sparse_commit_preflight(previous)
    else:
        previous = before_sparse_commit_preflight(manifest)
    if any(previous.get(name) == digest
           for name, digest in builder.ADMISSION_INTEGRITY_DIGESTS.items()):
        assert {name: previous[name] for name in builder.ADMISSION_INTEGRITY_DIGESTS} == builder.ADMISSION_INTEGRITY_DIGESTS
        previous.update(builder.ADMISSION_INTEGRITY_PREIMAGES)
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) in {
            builder.ADMISSION_INTEGRITY_PARENT_MANIFEST_SHA256,
            builder.ADMISSION_INTEGRITY_APPLICATION_PARENT_MANIFEST_SHA256,
            builder.ADMISSION_INTEGRITY_APPLICATION_SUCCESSOR_PARENT_MANIFEST_SHA256,
        }
    return previous




def before_application_carrier(manifest):
    # The historical cohort tests exercise their original frozen source. The
    # current APPLICATION manifest is separately qualified below.
    prior = before_admission_integrity(manifest)
    prior.update({
        "ext/native_remote.py": "2beef7dd4de1dab2908970bed48cfd3fdfd99da2d99bc8de72a92d2a1b2418b6",
        "ext/remote_sub.sh": "0835b0ff65f36becb4b150dc3c733e015ae9b3b3d27a00091a4ee1c16c4cfb0c",
        "ext/remote_sub_exec.py": "710115e08673467ce39a0322da2cf718a66e5b95d4a62a9eff94e160f79515db",
        "ext/remote_sub_helpers.py": "f7d62e9bdfa7388b7f86c0f968a021bf3949141ddcc8515103075ed3a1da2f93",
        "ext/support_bundle.py": "212df1af82652235ea10c9cabe95400aa40f8e819c6d5ef4c15666dbbfca3a4b"
})
    return prior


def before_application_auto_dependencies(manifest):
    # Preserve raw historical identities separately from the current accepted
    # application dependency composition. These are the protected pre-AUTO
    # member bytes, not an allowance in the production source validator.
    prior = dict(manifest)
    prior.update({
        "ext/go_lease_capability.py": "5227bf4d7b2b4b5664392c5178f31b113603e42490e9693fc0da5c79401c7938",
        "ext/go_lease_gateway.py": "19f4276840361a1efafd329f72e919a2b9d4d898c9eb67ee5fddaaf3b8a27c03",
        "ext/lease_broker.py": "9525c86bcc78dd01a51c103d5f4b3a587b2611c7fdfe863407e1b919a8ac931a",
    })
    return prior

def before_request_refusal_task(manifest):
    prior = before_admission_integrity(manifest)
    if prior["ext/fabric_task.py"] == builder.GO_REQUEST_REFUSAL_TASK_DIGEST:
        prior["ext/fabric_task.py"] = builder.GO_REMOTE_CWD_TASK_DIGEST
    return prior


def before_remote_cwd_task(manifest):
    prior = before_request_refusal_task(manifest)
    if prior["ext/fabric_task.py"] == builder.GO_REMOTE_CWD_TASK_DIGEST:
        prior["ext/fabric_task.py"] = builder.GO_UBUNTU4_DIGESTS["fabric_task.py"]
    return prior


def before_census_runtime(manifest):
    prior = before_remote_cwd_task(manifest)
    assert len(prior) == 107
    assert prior["ext/lane_runtime.py"] in (builder.GO_CENSUS_RUNTIME_DIGEST,
                                            builder.GO_CENSUS_EXIT_RUNTIME_DIGEST)
    prior["ext/lane_runtime.py"] = builder.GO_CENSUS_RUNTIME_PREIMAGE
    return prior


def before_original_artifact_recovery(manifest):
    prior = before_census_runtime(manifest)
    assert prior["ext/original_delivery_collector.py"] in {
        "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183",
        "44dcbb648bfdd0d0c4b6d5866529aec9341779baf5afd5071330997d1b227a83",
        "5219fb35f940831752638d348feefd92d02ad00ba9394fa9d66cf1d281091a9d"}
    prior["ext/original_delivery_collector.py"] = "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183"
    assert len(prior) == 107
    assert prior.pop("ext/original_advertised_artifact.py") == "46a06945d0e640794cb52945a5caece440abee6da1c0ba13eaff371d9dc6e3c0"
    assert prior["ext/artifact_delivery.py"] == "6848a4bfa60708a85dcea130d5b0be8f0d56bba0386b27bf3b5fd355d433494d"
    prior["ext/artifact_delivery.py"] = "81749610b8afd7151dbadb4cbcedbef853fc18ad9de9364fd3b2b1d747d535b1"
    assert len(prior) == 106
    return prior


def before_participant_cohort(manifest):
    prior = before_original_artifact_recovery(manifest)
    prior.update({"ext/" + name: digest
                  for name, digest in builder.GO_PROTECTED_CUSTODY_PREIMAGES.items()})
    assert prior.pop("ext/participant_binding.py") == "09aafda1390914e283915204459e37900123cd54a3d0f4e9116102f3a8921f56"
    assert prior.pop("ext/fabric_participant_owner.py") == "1619505962de4c73f415312871cc407777bf6c04ba6d02fb9be62c9d54a5545c"
    assert prior["ext/fabric_operator_owner.py"] == "90c6eee6bd7f2ca7d36c6b915a4fe2cae42b749d99ec2170fb39f55c5f72c0c7"
    prior["ext/fabric_operator_owner.py"] = "f81b4f053a22ba973b06214f6d06ed2d66e3fc471c781311f074718683cf4675"
    return prior


def test_default_build_stays_exact_reviewed_107_and_go_adds_only_the_fixed_pair(builds):
    default_raw = (builds.default / "native-manifest.json").read_bytes()
    actual_default = json.loads(default_raw)
    default = before_application_carrier(actual_default)
    application = json.loads((builds.application / "native-manifest.json").read_bytes())
    assert len(default) == 107
    previous = before_original_artifact_recovery(default)
    captured = {name: g.digest((ROOT / "candidate" / name).read_bytes())
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    historical_captured = {name: default["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(default, historical_captured)
    builder.validate_go_base_manifest(actual_default, captured)
    assert default["ext/pick.py"] == builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["pick.py"]
    historical = before_participant_cohort(default)
    historical.update({"ext/" + name: value for name, value in builder.GO_BASE_DEPENDENCIES.items()})
    historical["ext/pick.py"] = builder.GO_BASE_PICKER_SHA256
    assert default["ext/remote_sub_exec.py"] == builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["remote_sub_exec.py"]
    historical["ext/remote_sub_exec.py"] = builder.GO_BASE_EXECUTOR_SHA256
    historical.update({"ext/" + name: value for name, value in builder.GO_SELECTION_SUPPORT_PREIMAGES.items()})
    assert default["ext/provider_outcome.py"] == builder.GO_PROTECTED_PROVIDER_OUTCOME_SHA256
    historical["ext/provider_outcome.py"] = builder.GO_BASE_PROVIDER_OUTCOME_SHA256
    # Assert the repaired current payload separately from the original
    # request-refusal carrier used to reconstruct historical predecessors.
    assert actual_default["ext/fabric_task.py"] == builder.ADMISSION_INTEGRITY_DIGESTS["ext/fabric_task.py"]
    for name, original in builder.GO_UBUNTU4_PREIMAGES.items():
        expected = (builder.GO_REQUEST_REFUSAL_TASK_DIGEST if name == "fabric_task.py"
                    else builder.GO_UBUNTU4_DIGESTS[name])
        assert default["ext/" + name] == expected
        historical["ext/" + name] = original
    for name, original in builder.GO_PROTECTED_CUSTODY_PREIMAGES.items():
        assert default["ext/" + name] == builder.GO_PROTECTED_CUSTODY_DIGESTS[name]
        historical["ext/" + name] = original
    for name, original in builder.GO_COMPLETED_POLL_PREIMAGES.items():
        assert historical["ext/" + name] == builder.GO_COMPLETED_POLL_DIGESTS[name]
        historical["ext/" + name] = original
    for name, original in builder.GO_POST_FAILURE_PREIMAGES.items():
        assert previous["ext/" + name] == builder.GO_POST_FAILURE_DIGESTS[name]
        historical["ext/" + name] = original
    for name, digest in builder.GO_POST_FAILURE_DIAGNOSTICS_ADDITIONS.items():
        assert default["ext/" + name] == digest
        del historical["ext/" + name]
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == builder.GO_BASE_MANIFEST_SHA256
    assert {k: v for k, v in application.items() if k in actual_default} == actual_default
    assert set(application) - set(default) == {g.GO_ENTRY, g.GO_HANDLER}
    assert len(application) == 109
    http = json.loads((builds.http / "native-manifest.json").read_bytes())
    assert len(http) == 112
    assert set(http) - set(application) == set(g.HTTP_REQUIRED)
    inventory = json.loads((builds.application / "native-source-inventory.json").read_bytes())
    component = json.loads((builds.application / "external-go-component/component.json").read_bytes())
    assert component["native_stage_dependencies"] == {n: application["ext/" + n] for n in builder.GO_APPLICATION_DEPENDENCIES}
    assert component["candidate_sha256"] == application[g.GO_HANDLER]
    for path, expected in application.items():
        raw = (builds.application / "native-code-stage" / path).read_bytes()
        assert g.digest(raw) == expected == inventory["files"][path]["sha256"]
        assert len(raw) == inventory["files"][path]["bytes"]


def test_exact_historical_picker_remains_a_valid_base_but_no_arbitrary_fourth_member(builds):
    manifest = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
                   "ext/pool_ledger.py", "ext/provider_outcome.py", "ext/remote_sub_exec.py"):
        bad = dict(manifest)
        bad[member] = "f" * 64
        with pytest.raises(ValueError):
            builder.validate_go_base_manifest(bad, captured)
    bad = dict(manifest, unexpected="f" * 64)
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(bad, captured)


@pytest.mark.parametrize("corruption", ["handler", "dependency", "base", "picker", "executor", "original-collector", "ubuntu4", "provider-outcome", "post-failure", "post-failure-old-observer", "post-failure-old-delivery", "other-member", "entry-symlink"])
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
    elif corruption == "executor":
        manifest["ext/remote_sub_exec.py"] = "0" * 64
    elif corruption == "original-collector":
        manifest["ext/original_delivery_collector.py"] = "0" * 64
    elif corruption == "ubuntu4":
        manifest["ext/fabric_host_qualification.py"] = builder.GO_UBUNTU4_PREIMAGES["fabric_host_qualification.py"]
    elif corruption == "provider-outcome":
        manifest["ext/provider_outcome.py"] = "0" * 64
    elif corruption == "post-failure":
        manifest["ext/post_failure_observation.py"] = "0" * 64
    elif corruption in {"post-failure-old-observer", "post-failure-old-delivery"}:
        name = ("post_failure_observation.py" if corruption.endswith("observer")
                else "post_failure_observation_delivery.py")
        manifest["ext/" + name] = builder.GO_POST_FAILURE_ADDITIONS[name]
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
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_participant_cohort(current)
    prior.update({"ext/" + name: digest for name, digest in builder.GO_UBUNTU4_PREIMAGES.items()})
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


def test_old_and_updated_post_failure_pairs_remain_exact_cohorts(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    pairs = (
        {
            "post_failure_observation.py": "2a78630ccaf574da752c77d7b8f821723ccb264b970e2fe38b1976d886ca97a0",
            "post_failure_observation_delivery.py": "0e096d439e71600a20aabd6f29ea94127596ab3c1a4fb31d567194eba145c7f3",
        },
        {
            "post_failure_observation.py": "80fc9d95068099fb797c9e7a05981a9650d50ec170935d748d92a8e7bcd04337",
            "post_failure_observation_delivery.py": "81ab6f7f673e53c53b0e0a0cf4f3f1324642e29563f9213170f2a1ae29a0e4fc",
        },
        {
            "post_failure_observation.py": "80fc9d95068099fb797c9e7a05981a9650d50ec170935d748d92a8e7bcd04337",
            "post_failure_observation_delivery.py": "45636d279cd784248942d37c76e5625b2af7824a8f83638f804d56cff2d568e1",
        },
    )
    for pair in pairs:
        exact = dict(current)
        exact.update({"ext/" + name: digest for name, digest in pair.items()})
        builder.validate_go_base_manifest(exact, captured)


def test_completed_poll_pair_is_closed_and_cannot_relabel_historical_102(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(current, captured)
    # Isolate the original poll pair after reversing the whole Ubuntu4 cohort.
    current.update({"ext/" + name: digest for name, digest in builder.GO_UBUNTU4_PREIMAGES.items()})
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
    synthetic_prior = before_participant_cohort(current)
    synthetic_prior.update({"ext/" + name: digest
                            for name, digest in builder.GO_POST_FAILURE_PREIMAGES.items()})
    for name in builder.GO_POST_FAILURE_ADDITIONS:
        del synthetic_prior["ext/" + name]
    assert len(synthetic_prior) == 102
    with pytest.raises(ValueError, match="completed-poll cohort"):
        builder.validate_go_base_manifest(synthetic_prior, captured)


def test_ubuntu4_runtime_cohort_preserves_prior_generation_and_rejects_mixtures(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    previous = dict(current)
    previous.update({"ext/" + name: digest for name, digest in builder.GO_UBUNTU4_PREIMAGES.items()})
    builder.validate_go_base_manifest(current, captured)
    builder.validate_go_base_manifest(previous, captured)
    names = tuple(builder.GO_UBUNTU4_DIGESTS)
    for count in (1, 2):
        for selected in itertools.combinations(names, count):
            mixed = dict(previous)
            mixed.update({"ext/" + name: builder.GO_UBUNTU4_DIGESTS[name] for name in selected})
            with pytest.raises(ValueError, match="Ubuntu4 cohort"):
                builder.validate_go_base_manifest(mixed, captured)
    for name in names:
        corrupt = dict(current)
        corrupt["ext/" + name] = "f" * 64
        with pytest.raises(ValueError):
            builder.validate_go_base_manifest(corrupt, captured)
    old_helper = dict(current)
    old_helper["ext/remote_sub_helpers.py"] = builder.GO_COMPLETED_POLL_PREIMAGES["remote_sub_helpers.py"]
    with pytest.raises(ValueError, match="completed-poll cohort"):
        builder.validate_go_base_manifest(old_helper, captured)
    historical_namespace = before_participant_cohort(current)
    historical_namespace.update({"ext/" + name: digest
                                 for name, digest in builder.GO_POST_FAILURE_PREIMAGES.items()})
    for name in builder.GO_POST_FAILURE_ADDITIONS:
        del historical_namespace["ext/" + name]
    assert len(historical_namespace) == 102
    with pytest.raises(ValueError, match="Ubuntu4 cohort"):
        builder.validate_go_base_manifest(historical_namespace, captured)
    assert current == original



def test_protected_process_custody_is_one_exact_reversible_source_cohort(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    original = dict(current)
    captured = {name: current["ext/" + name]
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    before = dict(current)
    before.update({"ext/" + name: digest
                   for name, digest in builder.GO_PROTECTED_CUSTODY_PREIMAGES.items()})
    # Both exact historical/source-current members are admitted, but a
    # fabricated hybrid, missing version, or foreign source hash is not.
    builder.validate_go_base_manifest(current, captured)
    builder.validate_go_base_manifest(before, captured)
    names = tuple(builder.GO_PROTECTED_CUSTODY_PREIMAGES)
    for count in (1, 2):
        for changed in itertools.combinations(names, count):
            mixed = dict(before)
            mixed.update({"ext/" + name: builder.GO_PROTECTED_CUSTODY_DIGESTS[name]
                          for name in changed})
            with pytest.raises(ValueError, match="custody cohort"):
                builder.validate_go_base_manifest(mixed, captured)
    for name in names:
        forged = dict(current)
        forged["ext/" + name] = "f" * 64
        with pytest.raises(ValueError, match="custody cohort"):
            builder.validate_go_base_manifest(forged, captured)
    assert current == original

def test_sparse_config_executor_successor_is_exact_and_does_not_mutate_manifest(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    previous = dict(current)
    previous.update({"ext/" + name: digest for name, digest in builder.GO_UBUNTU4_PREIMAGES.items()})
    for cohort in (previous, current):
        for digest in (builder.GO_BASE_EXECUTOR_SHA256,
                       builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["remote_sub_exec.py"]):
            exact = dict(cohort)
            exact["ext/remote_sub_exec.py"] = digest
            before = dict(exact)
            builder.validate_go_base_manifest(exact, captured)
            assert exact == before
    wrong = dict(current)
    wrong["ext/remote_sub_exec.py"] = "f" * 64
    with pytest.raises(ValueError, match="executor"):
        builder.validate_go_base_manifest(wrong, captured)


def test_participant_cohort_preserves_prior_104_and_input_identity(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_participant_cohort(current)
    assert len(prior) == 104
    builder.validate_go_base_manifest(prior, captured)
    builder.validate_go_base_manifest(current, captured)
    assert current == original


def test_original_collection_successor_preserves_prior_releases_without_backdating(builds):
    current = builder.normalize_application_carrier_base_manifest(builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes())))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    key = "ext/original_delivery_collector.py"
    old = "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183"
    prior_forward = "44dcbb648bfdd0d0c4b6d5866529aec9341779baf5afd5071330997d1b227a83"
    new = "5219fb35f940831752638d348feefd92d02ad00ba9394fa9d66cf1d281091a9d"
    assert (builder.GO_BASE_ORIGINAL_COLLECTOR_SHA256,
            builder.GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256,
            builder.GO_ORIGINAL_COLLECTION_SUCCESSOR_SHA256) == (old, prior_forward, new)
    assert current[key] == new
    for digest in (old, prior_forward, new):
        exact = dict(current, **{key: digest})
        before = dict(exact)
        builder.validate_go_base_manifest(exact, captured)
        assert exact == before
    prior = before_participant_cohort(current)
    historical = dict(prior)
    for mapping in (builder.GO_UBUNTU4_PREIMAGES, builder.GO_COMPLETED_POLL_PREIMAGES,
                    builder.GO_POST_FAILURE_PREIMAGES):
        historical.update({"ext/" + name: digest for name, digest in mapping.items()})
    for name in builder.GO_POST_FAILURE_ADDITIONS:
        del historical["ext/" + name]
    assert len(prior) == 104 and len(historical) == 102
    previous = before_original_artifact_recovery(current)
    assert len(previous) == 106
    for predecessor in (previous, prior, historical):
        assert predecessor[key] == old
        builder.validate_go_base_manifest(predecessor, captured)
        for digest in (prior_forward, new):
            backdated = dict(predecessor, **{key: digest})
            with pytest.raises(ValueError, match="original collector"):
                builder.validate_go_base_manifest(backdated, captured)
    for digest in ("f" * 64, "", None):
        with pytest.raises(ValueError, match="original collector"):
            builder.validate_go_base_manifest(dict(current, **{key: digest}), captured)


def test_committed_original_collection_successor_carries_one_qualified_member(builds):
    """The committed J collector is one exact member of the current closure.

    The successor replaces exactly one source member, so the published
    generation keeps validating and no other source or entrypoint hash moves.
    """
    current = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    key = "ext/original_delivery_collector.py"
    successor = builder.GO_ORIGINAL_COLLECTION_SUCCESSOR_SHA256
    assert current[key] == successor
    assert g.digest((ROOT / "candidate/original_delivery_collector.py").read_bytes()) == successor
    # Only that one member differs from the prior published forward lineage.
    prior_forward = dict(current, **{key: builder.GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256})
    assert {name for name in current if current[name] != prior_forward[name]} == {key}
    # The prior lineage is still an accepted complete current closure.
    for view in (current, prior_forward):
        before = dict(view)
        builder.validate_go_base_manifest(view, captured)
        assert view == before


def test_committed_original_collection_successor_keeps_parent_closures_exact(builds):
    """Each successor parent closure is an exact whole-manifest identity."""
    current = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    key = "ext/original_delivery_collector.py"
    assert g.digest((json.dumps(current, sort_keys=True, indent=2) + "\n").encode()) == "bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e"
    sparse_parent = builder.before_application_pool_composition(current)
    assert g.digest((json.dumps(sparse_parent, sort_keys=True, indent=2) + "\n").encode()) == builder.APPLICATION_POOL_COMPOSITION_SPARSE_SUCCESSOR_PARENT_SHA256
    parent = builder.before_sparse_commit_preflight(sparse_parent)
    assert g.digest((json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()) == (
        "4f6a64b8b22188c324923b4575dcc1b6490ca59df21ba303d9f16db0f6fd6552")
    installed = builder.before_admission_integrity(parent)
    assert g.digest((json.dumps(installed, sort_keys=True, indent=2) + "\n").encode()) == (
        "6d8adb18ece5b01dadb8ea60aa868e490f78d4371898934d63ea2e30b66eab82")
    historical = builder.normalize_application_carrier_base_manifest(current)
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == (
        "a68a4af9834da02d85ac00300ccaf0540c0fbccedd9c3a7c883157696558df35")
    assert (builder.APPLICATION_POOL_COMPOSITION_SUCCESSOR_PARENT_SHA256,
            builder.ADMISSION_INTEGRITY_APPLICATION_SUCCESSOR_PARENT_MANIFEST_SHA256,
            builder.APPLICATION_CARRIER_SUCCESSOR_BASE_SHA256) == (
        "4f6a64b8b22188c324923b4575dcc1b6490ca59df21ba303d9f16db0f6fd6552",
        "6d8adb18ece5b01dadb8ea60aa868e490f78d4371898934d63ea2e30b66eab82",
        "a68a4af9834da02d85ac00300ccaf0540c0fbccedd9c3a7c883157696558df35")
    # The prior published closures stay accepted for the same projections.
    prior = dict(current, **{key: builder.GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256})
    prior_sparse_parent = builder.before_application_pool_composition(prior)
    assert g.digest((json.dumps(prior_sparse_parent, sort_keys=True, indent=2) + "\n").encode()) == builder.APPLICATION_POOL_COMPOSITION_SPARSE_PARENT_SHA256
    prior_parent = builder.before_sparse_commit_preflight(prior_sparse_parent)
    assert g.digest((json.dumps(prior_parent, sort_keys=True, indent=2) + "\n").encode()) == (
        builder.APPLICATION_POOL_COMPOSITION_PARENT_SHA256)
    prior_installed = builder.before_admission_integrity(prior_parent)
    assert g.digest((json.dumps(prior_installed, sort_keys=True, indent=2) + "\n").encode()) == (
        builder.ADMISSION_INTEGRITY_APPLICATION_PARENT_MANIFEST_SHA256)
    prior_historical = builder.normalize_application_carrier_base_manifest(prior)
    assert g.digest((json.dumps(prior_historical, sort_keys=True, indent=2) + "\n").encode()) == (
        builder.APPLICATION_CARRIER_BASE_SHA256)
    # A single mutated member leaves every successor closure unmatched.
    for name in ("ext/lease_broker.py", "ext/fabric_task.py", "ext/lane_runtime.py",
                 "ext/original_delivery_collector.py"):
        mutated = dict(current)
        mutated[name] = "f" * 64
        with pytest.raises(ValueError):
            builder.normalize_application_carrier_base_manifest(mutated)


@pytest.mark.parametrize("successor", [False, True])
@pytest.mark.parametrize("publisher", [False, True])
def test_collector_sparse_and_pool_or_scoped_routes_bind_complete_parents(builds, successor, publisher):
    current = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    if not successor:
        current["ext/original_delivery_collector.py"] = builder.GO_ORIGINAL_COLLECTION_COLLECTOR_SHA256
    if not publisher:
        current["ext/support_bundle.py"] = builder.APPLICATION_POOL_COMPOSITION_PREIMAGES["ext/support_bundle.py"]
    before = dict(current)
    inverse = builder.before_application_pool_composition if publisher else builder.before_exact_scoped_models
    parent = inverse(current)
    expected = (builder.APPLICATION_POOL_COMPOSITION_SPARSE_SUCCESSOR_PARENT_SHA256
                if successor else builder.APPLICATION_POOL_COMPOSITION_SPARSE_PARENT_SHA256)
    assert g.digest((json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()) == expected
    before_sparse = builder.before_sparse_commit_preflight(parent)
    expected = (builder.APPLICATION_POOL_COMPOSITION_SUCCESSOR_PARENT_SHA256
                if successor else builder.APPLICATION_POOL_COMPOSITION_PARENT_SHA256)
    assert g.digest((json.dumps(before_sparse, sort_keys=True, indent=2) + "\n").encode()) == expected
    dependencies = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(current, dependencies)
    for member in ("ext/pick.py", "ext/original_delivery_collector.py"):
        foreign = dict(current, **{member: "f" * 64})
        with pytest.raises(ValueError, match="parent closure"):
            inverse(foreign)
    assert current == before


def test_flagged_build_publishes_the_committed_collector_in_the_complete_release(builds):
    """The real Go + APPLICATION HTTP build carries the committed collector."""
    manifest = json.loads((builds.http / "native-manifest.json").read_bytes())
    inventory = json.loads((builds.http / "native-source-inventory.json").read_bytes())
    assert len(manifest) == len(inventory["files"]) == 112
    key = "ext/original_delivery_collector.py"
    assert manifest[key] == builder.GO_ORIGINAL_COLLECTION_SUCCESSOR_SHA256
    staged = (builds.http / "native-code-stage" / key).read_bytes()
    assert g.digest(staged) == manifest[key]
    row = inventory["files"][key]
    assert row["sha256"] == manifest[key]
    assert row["bytes"] == len(staged)
    assert row["source"] == "candidate/original_delivery_collector.py"
    # Every other member keeps its reviewed source identity.
    for name, digest in manifest.items():
        assert inventory["files"][name]["sha256"] == digest
        assert g.digest((builds.http / "native-code-stage" / name).read_bytes()) == digest


def test_installer_go_validation_accepts_the_committed_collector_release(builds):
    """The unchanged installer's own validation input accepts the new release.

    native_install validates the base closure exactly as the installed owner
    does: the 112-member bundle manifest minus the Go pair and the HTTP
    members, with the captured application dependency digests.
    """
    manifest = json.loads((builds.http / "native-manifest.json").read_bytes())
    http_members = builder.HTTP_GENERATION_MEMBERS & set(manifest)
    assert http_members == builder.HTTP_GENERATION_MEMBERS
    base = {key: value for key, value in manifest.items()
            if key not in {g.GO_ENTRY, g.GO_HANDLER} | http_members}
    assert len(base) == 107
    dependencies = {name: g.digest((ROOT / "candidate" / name).read_bytes())
                    for name in builder.GO_APPLICATION_DEPENDENCIES}
    before = dict(base)
    builder.validate_go_base_manifest(base, dependencies)
    assert base == before


@pytest.mark.parametrize("corruption", ["binding-absent", "owner-absent", "binding-hash",
    "owner-hash", "old-operator-with-pair", "new-operator-without-pair", "participants-without-diagnostics"])
def test_participant_cohort_cannot_relabel_legacy_namespace(builds, corruption):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    bad = dict(current)
    if corruption == "binding-absent": del bad["ext/participant_binding.py"]
    elif corruption == "owner-absent": del bad["ext/fabric_participant_owner.py"]
    elif corruption == "binding-hash": bad["ext/participant_binding.py"] = "f" * 64
    elif corruption == "owner-hash": bad["ext/fabric_participant_owner.py"] = "f" * 64
    elif corruption == "old-operator-with-pair":
        bad["ext/fabric_operator_owner.py"] = "f81b4f053a22ba973b06214f6d06ed2d66e3fc471c781311f074718683cf4675"
    elif corruption == "new-operator-without-pair":
        bad = before_participant_cohort(current)
        bad["ext/fabric_operator_owner.py"] = current["ext/fabric_operator_owner.py"]
    else:
        bad = before_original_artifact_recovery(current)
        for name in builder.GO_POST_FAILURE_ADDITIONS: del bad["ext/" + name]
        assert len(bad) == 104
    with pytest.raises(ValueError): builder.validate_go_base_manifest(bad, captured)


@pytest.mark.parametrize("count", [104, 102])
def test_protected_custody_cannot_relabel_prior_namespace(builds, count):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_participant_cohort(current)
    if count == 102:
        for cohort in (builder.GO_UBUNTU4_PREIMAGES, builder.GO_COMPLETED_POLL_PREIMAGES,
                       builder.GO_POST_FAILURE_PREIMAGES):
            prior.update({"ext/" + name: digest for name, digest in cohort.items()})
        for name in builder.GO_POST_FAILURE_ADDITIONS:
            del prior["ext/" + name]
    assert len(prior) == count
    builder.validate_go_base_manifest(prior, captured)
    wrong = dict(prior)
    wrong.update({"ext/" + name: digest for name, digest in builder.GO_PROTECTED_CUSTODY_DIGESTS.items()})
    with pytest.raises(ValueError, match="custody cannot relabel historical namespace"):
        builder.validate_go_base_manifest(wrong, captured)



def test_original_artifact_recovery_preserves_exact_previous106_and_raw_identity(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    previous = before_original_artifact_recovery(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    for manifest in (previous, current):
        original = dict(manifest)
        builder.validate_go_base_manifest(manifest, captured)
        assert manifest == original
    historical = before_application_auto_dependencies(previous)
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == "5721f06f28d39b493a3b1cfc7d37d3ae5741818e0197ef723a23db15f109c295"


@pytest.mark.parametrize("corruption", ["reader-missing", "reader-hash", "delivery-hash",
    "new-reader-old-delivery", "new-delivery-without-reader", "pair-in104", "pair-in102"])
def test_original_artifact_pair_cannot_expand_or_relabel_historical_namespace(builds, corruption):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    bad = dict(current)
    if corruption == "reader-missing":
        del bad["ext/original_advertised_artifact.py"]
    elif corruption == "reader-hash":
        bad["ext/original_advertised_artifact.py"] = "f" * 64
    elif corruption == "delivery-hash":
        bad["ext/artifact_delivery.py"] = "f" * 64
    elif corruption == "new-reader-old-delivery":
        bad["ext/artifact_delivery.py"] = builder.GO_ORIGINAL_ARTIFACT_PREIMAGE
    elif corruption == "new-delivery-without-reader":
        bad = before_original_artifact_recovery(current)
        bad["ext/artifact_delivery.py"] = builder.GO_ORIGINAL_ARTIFACT_DIGEST
    else:
        bad = before_participant_cohort(current)
        if corruption == "pair-in102":
            for cohort in (builder.GO_UBUNTU4_PREIMAGES, builder.GO_COMPLETED_POLL_PREIMAGES,
                           builder.GO_POST_FAILURE_PREIMAGES):
                bad.update({"ext/" + name: digest for name, digest in cohort.items()})
            for name in builder.GO_POST_FAILURE_ADDITIONS:
                del bad["ext/" + name]
        bad["ext/original_advertised_artifact.py"] = current["ext/original_advertised_artifact.py"]
        bad["ext/artifact_delivery.py"] = builder.GO_ORIGINAL_ARTIFACT_DIGEST
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(bad, captured)


def test_exact_census_successor_preserves_original_107_without_mutation(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    assert current["ext/lane_runtime.py"] == builder.GO_CENSUS_EXIT_RUNTIME_DIGEST
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    previous = dict(current, **{"ext/lane_runtime.py": builder.GO_CENSUS_RUNTIME_DIGEST})
    for candidate in (current, previous, before_census_runtime(current)):
        before = dict(candidate)
        builder.validate_go_base_manifest(candidate, captured)
        assert candidate == before


@pytest.mark.parametrize("namespace", ["106", "104", "102"])
@pytest.mark.parametrize("runtime_digest", [builder.GO_CENSUS_RUNTIME_DIGEST,
                                             builder.GO_CENSUS_EXIT_RUNTIME_DIGEST])
def test_census_successor_cannot_be_backdated_to_a_historical_namespace(builds, namespace, runtime_digest):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_original_artifact_recovery(current) if namespace == "106" else before_participant_cohort(current)
    if namespace == "102":
        for name, digest in builder.GO_POST_FAILURE_PREIMAGES.items():
            prior["ext/" + name] = digest
        for name in builder.GO_POST_FAILURE_ADDITIONS:
            del prior["ext/" + name]
    assert len(prior) == int(namespace)
    prior["ext/lane_runtime.py"] = runtime_digest
    before = dict(prior)
    with pytest.raises(ValueError, match="census cannot relabel"):
        builder.validate_go_base_manifest(prior, captured)
    assert prior == before


@pytest.mark.parametrize("digest", ["f" * 64, ""])
def test_unknown_census_bytes_refuse_without_changing_the_manifest(builds, digest):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    current["ext/lane_runtime.py"] = digest
    before = dict(current)
    with pytest.raises(ValueError, match="census is not the exact"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def test_exact_remote_cwd_task_preserves_original_107_and_caller_manifest(builds):
    current = before_request_refusal_task(before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes())))
    before = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    assert current["ext/fabric_task.py"] == "72f6b0d70d4596c1d059cf57504ff7fd39ca6d3464d96e9f9c6c8172b1a69037"
    previous = before_remote_cwd_task(current)
    previous_before = dict(previous)
    for task_generation in (current, previous):
        for runtime in (builder.GO_CENSUS_RUNTIME_DIGEST, builder.GO_CENSUS_EXIT_RUNTIME_DIGEST,
                        builder.GO_CENSUS_RUNTIME_PREIMAGE):
            manifest = dict(task_generation)
            manifest["ext/lane_runtime.py"] = runtime
            unchanged = dict(manifest)
            builder.validate_go_base_manifest(manifest, captured)
            assert manifest == unchanged
    assert current == before
    assert previous == previous_before


@pytest.mark.parametrize("namespace", ["106", "104", "102"])
@pytest.mark.parametrize("task_digest,error", [
    (builder.GO_REMOTE_CWD_TASK_DIGEST, "remote-cwd task cannot relabel"),
    (builder.GO_REQUEST_REFUSAL_TASK_DIGEST, "refusal task cannot relabel"),
])
def test_remote_cwd_task_cannot_be_backdated_to_a_historical_namespace(builds, namespace, task_digest, error):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_original_artifact_recovery(current) if namespace == "106" else before_participant_cohort(current)
    if namespace == "102":
        prior.update({"ext/" + name: digest for name, digest in builder.GO_UBUNTU4_PREIMAGES.items()})
        prior.update({"ext/" + name: digest for name, digest in builder.GO_COMPLETED_POLL_PREIMAGES.items()})
        prior.update({"ext/" + name: digest for name, digest in builder.GO_POST_FAILURE_PREIMAGES.items()})
        for name in builder.GO_POST_FAILURE_ADDITIONS:
            del prior["ext/" + name]
    assert len(prior) == int(namespace)
    builder.validate_go_base_manifest(prior, captured)
    prior["ext/fabric_task.py"] = task_digest
    before = dict(prior)
    with pytest.raises(ValueError, match=error):
        builder.validate_go_base_manifest(prior, captured)
    assert prior == before


@pytest.mark.parametrize("members", [
    ("fabric_host_qualification.py",), ("remote_sub.sh",),
    ("fabric_host_qualification.py", "remote_sub.sh"),
])
@pytest.mark.parametrize("task_digest", [builder.GO_REMOTE_CWD_TASK_DIGEST,
                                         builder.GO_REQUEST_REFUSAL_TASK_DIGEST])
def test_remote_cwd_task_still_requires_the_complete_ubuntu4_cohort(builds, members, task_digest):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    current["ext/fabric_task.py"] = task_digest
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    for member in members:
        current["ext/" + member] = builder.GO_UBUNTU4_PREIMAGES[member]
    before = dict(current)
    with pytest.raises(ValueError, match="Ubuntu4 cohort"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


@pytest.mark.parametrize("digest", ["f" * 64, "",
    "0a6cb393fc30d978a78686b9e588f6f51b1b9ec191e291aea4ccf96a4d7bdaa0"])
def test_unknown_remote_cwd_task_bytes_refuse_without_changing_the_manifest(builds, digest):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    current["ext/fabric_task.py"] = digest
    before = dict(current)
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def test_refusal_diagnostics_preserve_exact_remote_cwd_107_and_raw_identity(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    assert len(current) == 107
    assert current["ext/fabric_task.py"] == builder.GO_REQUEST_REFUSAL_TASK_DIGEST
    previous = before_request_refusal_task(current)
    historical = before_application_auto_dependencies(previous)
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == "c7cf946bc1d8f13ef7b512d071d85097e1ddc58979af76bf367a7707aa90617d"
    for manifest in (current, previous):
        before = dict(manifest)
        builder.validate_go_base_manifest(manifest, captured)
        assert manifest == before


def test_refusal_task_cannot_mix_the_predecessor_poll_helper(builds):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    current["ext/remote_sub_helpers.py"] = builder.GO_COMPLETED_POLL_PREIMAGES["remote_sub_helpers.py"]
    before = dict(current)
    with pytest.raises(ValueError, match="completed-poll cohort"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


@pytest.mark.parametrize("missing", ["pool", "ext/participant_binding.py"])
def test_refusal_task_requires_the_complete_raw_namespace(builds, missing):
    current = before_application_carrier(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    del current[missing]
    before = dict(current)
    with pytest.raises(ValueError, match="dependency closure"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def application_carrier_parent_manifest(builds):
    # Preserve the original APPLICATION-cohort rejection cases at their exact
    # parent; the combined repair has its own complete-parent cases below.
    return before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))


def test_application_carrier_preserves_actual_and_historical_manifest_identity(builds):
    current = application_carrier_parent_manifest(builds)
    before = dict(current)
    captured = {name: current["ext/" + name]
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(current, captured)
    prior = before_application_carrier(current)
    assert g.digest((json.dumps(prior, sort_keys=True, indent=2) + "\n").encode()) == "e43384b1bfdae31d694f6771455dc32681241c80ec18e7747e364351fe3d92f4"
    builder.validate_go_base_manifest(prior, captured)
    assert current == before
    assert current != prior
    assert len(current) == len(prior) == 107
    for name, expected in builder.APPLICATION_CARRIER_DIGESTS.items():
        assert current["ext/" + name] == expected


@pytest.mark.parametrize("member", [
    "native_remote.py", "remote_sub_exec.py", "remote_sub.sh",
    "remote_sub_helpers.py", "support_bundle.py",
])
@pytest.mark.parametrize("replacement", ["historical", "foreign"])
def test_application_carrier_rejects_partial_or_foreign_member(builds, member, replacement):
    current = application_carrier_parent_manifest(builds)
    current["ext/" + member] = (
        before_application_carrier(current)["ext/" + member]
        if replacement == "historical" else "f" * 64)
    before = dict(current)
    captured = {name: current["ext/" + name]
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="application carrier manifest cohort"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


@pytest.mark.parametrize("mutation", ["prior-namespace", "extra-member", "old-picker", "changed-pool"])
def test_application_carrier_cannot_relabel_another_complete_base(builds, mutation):
    current = application_carrier_parent_manifest(builds)
    if mutation == "prior-namespace":
        del current["ext/original_advertised_artifact.py"]
    elif mutation == "extra-member":
        current["ext/unreviewed.py"] = "f" * 64
    elif mutation == "old-picker":
        current["ext/pick.py"] = builder.GO_BASE_PICKER_SHA256
    else:
        current["pool"] = "f" * 64
    before = dict(current)
    captured = {name: current["ext/" + name]
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="cannot relabel a prior or mixed native base"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def test_application_carrier_inventory_retains_actual_candidate_provenance(builds):
    inventory = json.loads((builds.default / "native-source-inventory.json").read_bytes())
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
    for name, expected in builder.application_carrier_candidate_digests(ROOT).items():
        row = inventory["files"]["ext/" + name]
        raw = (builds.default / "native-code-stage/ext" / name).read_bytes()
        assert row["source"] == "candidate/" + name
        assert row["sha256"] == current["ext/" + name] == expected == g.digest(raw)
        assert row["bytes"] == len(raw)


def test_application_carrier_source_requires_all_five_exact_members(builds, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    for name in builder.APPLICATION_CARRIER_DIGESTS:
        (candidate / name).write_bytes(
            (builds.default / "native-code-stage/ext" / name).read_bytes())
    assert builder.application_carrier_candidate_cohort(tmp_path) is True
    member = candidate / "support_bundle.py"
    member.write_bytes(member.read_bytes() + b"\n# foreign\n")
    with pytest.raises(ValueError, match="candidate cohort is incomplete"):
        builder.application_carrier_candidate_cohort(tmp_path)


def test_admission_integrity_successor_binds_actual_sources_and_preserves_parent(builds):
    current = before_sparse_commit_preflight(json.loads((builds.default / "native-manifest.json").read_bytes()))
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    previous = before_admission_integrity(current)
    assert previous != current
    assert {name for name in current if current[name] != previous[name]} == set(builder.ADMISSION_INTEGRITY_DIGESTS)
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == builder.ADMISSION_INTEGRITY_APPLICATION_PARENT_MANIFEST_SHA256
    for manifest in (current, previous):
        unchanged = dict(manifest)
        builder.validate_go_base_manifest(manifest, captured)
        assert manifest == unchanged
    for output in (builds.default, builds.application, builds.http):
        manifest = json.loads((output / "native-manifest.json").read_bytes())
        for name, digest in builder.ADMISSION_INTEGRITY_DIGESTS.items():
            assert manifest[name] == digest
            assert g.digest((output / "native-code-stage" / name).read_bytes()) == digest
            assert g.digest((ROOT / "candidate" / Path(name).name).read_bytes()) == digest
    assert current == original


@pytest.mark.parametrize("corruption", [
    "old-task", "old-runtime", "foreign-task", "foreign-runtime", "missing-task",
    "missing-runtime", "extra-member", "foreign-parent", "different-valid-parent",
    "historical106", "historical104", "historical102",
])
def test_admission_integrity_rejects_partial_foreign_and_backdated_closures(builds, corruption):
    current = before_sparse_commit_preflight(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    bad = dict(current)
    if corruption in ("old-task", "old-runtime"):
        name = "ext/fabric_task.py" if corruption == "old-task" else "ext/lane_runtime.py"
        bad[name] = builder.ADMISSION_INTEGRITY_PREIMAGES[name]
    elif corruption in ("foreign-task", "foreign-runtime"):
        name = "ext/fabric_task.py" if corruption == "foreign-task" else "ext/lane_runtime.py"
        bad[name] = "f" * 64
    elif corruption in ("missing-task", "missing-runtime"):
        del bad["ext/fabric_task.py" if corruption == "missing-task" else "ext/lane_runtime.py"]
    elif corruption == "extra-member":
        bad["ext/foreign.py"] = "f" * 64
    elif corruption == "foreign-parent":
        bad["pool"] = "f" * 64
    elif corruption == "different-valid-parent":
        bad["ext/pick.py"] = builder.GO_BASE_PICKER_SHA256
    else:
        historical_parent = before_application_carrier(current)
        bad = (before_original_artifact_recovery(historical_parent)
               if corruption == "historical106" else before_participant_cohort(historical_parent))
        if corruption == "historical102":
            for cohort in (builder.GO_UBUNTU4_PREIMAGES, builder.GO_COMPLETED_POLL_PREIMAGES,
                           builder.GO_POST_FAILURE_PREIMAGES):
                bad.update({"ext/" + name: digest for name, digest in cohort.items()})
            for name in builder.GO_POST_FAILURE_ADDITIONS:
                del bad["ext/" + name]
        builder.validate_go_base_manifest(bad, captured)
        bad.update(builder.ADMISSION_INTEGRITY_DIGESTS)
    unchanged = dict(bad)
    with pytest.raises(ValueError, match="admission integrity"):
        builder.validate_go_base_manifest(bad, captured)
    assert bad == unchanged


def test_admission_integrity_forward_delta_is_reversible_and_source_exact(tmp_path):
    import hashlib
    import subprocess
    patch_path = ROOT.parents[2] / "tests/fixtures/fabric-native-admission-integrity-20261107.patch"
    assert hashlib.sha256(patch_path.read_bytes()).hexdigest() == "68c1abf049ee9e4c04fc749eebb9a4b99ba71a71c22945e0f5d02bc8fe107753"
    current = {}
    for relative, digest in builder.ADMISSION_INTEGRITY_DIGESTS.items():
        name = Path(relative).name
        current[name] = (ROOT / "candidate" / name).read_bytes()
        assert g.digest(current[name]) == digest
        (tmp_path / name).write_bytes(current[name])
    def apply(*options):
        result = subprocess.run(
            ["git", "apply", "--unidiff-zero", *options, str(patch_path)],
            cwd=tmp_path, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
    apply("--reverse", "--check")
    apply("--reverse")
    for relative, digest in builder.ADMISSION_INTEGRITY_PREIMAGES.items():
        assert g.digest((tmp_path / Path(relative).name).read_bytes()) == digest
    apply("--check")
    apply()
    for name, raw in current.items():
        assert (tmp_path / name).read_bytes() == raw


@pytest.mark.parametrize("lineage", ["worker", "application", "application-j"])
def test_both_exact_admission_repair_lineages_remain_distinct(builds, lineage):
    # Immutable WORKER fixture is the exact manifest from repair source
    # 3b2338d3946209b6f6ce6a0b694cf609015fb07f; it is not another runtime owner.
    if lineage == "worker":
        raw = (ROOT.parents[2] / "tests/fixtures/fabric-admission-integrity-worker107-3b2338d.json").read_bytes()
        current_identity = "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
        parent_identity = "815ec3c880b5f66590b7dcc04ac42c6c5384ba296b44e83af7e96c23326f6347"
        historical_identity = parent_identity
    elif lineage == "application":
        actual = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
        raw = (json.dumps(before_sparse_commit_preflight(actual), sort_keys=True, indent=2) + "\n").encode()
        current_identity = "b9fd5f760bd578bb40ef93feee861763d287f098ecddab07ed28f44863ee5da4"
        parent_identity = "3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9"
        historical_identity = "e43384b1bfdae31d694f6771455dc32681241c80ec18e7747e364351fe3d92f4"
    else:
        actual = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
        parent = builder.before_sparse_commit_preflight(builder.before_application_pool_composition(actual))
        raw = (json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()
        current_identity = "4f6a64b8b22188c324923b4575dcc1b6490ca59df21ba303d9f16db0f6fd6552"
        parent_identity = "6d8adb18ece5b01dadb8ea60aa868e490f78d4371898934d63ea2e30b66eab82"
        historical_identity = "a68a4af9834da02d85ac00300ccaf0540c0fbccedd9c3a7c883157696558df35"
    assert g.digest(raw) == current_identity
    current = json.loads(raw)
    original = dict(current)
    parent = builder.before_admission_integrity(current)
    assert g.digest((json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()) == parent_identity
    assert len(current) == len(parent) == 107
    assert {name for name in current if current[name] != parent[name]} == {
        "ext/fabric_task.py", "ext/lane_runtime.py",
    }
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    for view in (current, parent):
        before = dict(view)
        builder.validate_go_base_manifest(view, captured)
        assert view == before
    historical = builder.normalize_application_carrier_base_manifest(current)
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == historical_identity
    assert current == original


@pytest.mark.parametrize("member", [
    "go_lease_capability.py", "go_lease_gateway.py", "lease_broker.py",
    "native_remote.py", "remote_sub.sh", "remote_sub_exec.py",
    "remote_sub_helpers.py", "support_bundle.py",
])
@pytest.mark.parametrize("replacement", ["worker", "foreign"])
def test_repaired_application_rejects_change_to_any_preserved_member(builds, member, replacement):
    current = before_sparse_commit_preflight(json.loads((builds.default / "native-manifest.json").read_bytes()))
    worker_raw = (ROOT.parents[2] / "tests/fixtures/fabric-admission-integrity-worker107-3b2338d.json").read_bytes()
    assert g.digest(worker_raw) == "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
    worker = json.loads(worker_raw)
    key = "ext/" + member
    assert current[key] != worker[key]
    current[key] = worker[key] if replacement == "worker" else "f" * 64
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="admission integrity parent closure"):
        builder.validate_go_base_manifest(current, captured)
    assert current == original


@pytest.mark.parametrize("extended", ["application", "http"])
def test_repaired_base_cannot_relabel_an_extended_namespace(builds, extended):
    manifest = before_extended_host_pull_epoch(json.loads((getattr(builds, extended) / "native-manifest.json").read_bytes()))
    manifest.update(builder.EXACT_SCOPED_MODEL_PREIMAGES)
    manifest["ext/support_bundle.py"] = builder.APPLICATION_POOL_COMPOSITION_PREIMAGES["ext/support_bundle.py"]
    assert manifest["ext/remote_sub_exec.py"] == builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_DIGEST
    manifest["ext/remote_sub_exec.py"] = builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_PREIMAGE
    original = dict(manifest)
    captured = {name: manifest["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="admission integrity parent closure"):
        builder.validate_go_base_manifest(manifest, captured)
    assert manifest == original



def test_sparse_preflight_is_one_exact_successor_of_the_repaired_application_parent(builds):
    current = before_exact_scoped_models(json.loads((builds.default / "native-manifest.json").read_bytes()))
    raw = (json.dumps(current, sort_keys=True, indent=2) + "\n").encode()
    assert g.digest(raw) == "1bb6f2ec3af603e44c345558931d3bf5daec28fa7bc9db14cbad830674ea84d0"
    original = dict(current)
    previous = builder.before_sparse_commit_preflight(current)
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "b9fd5f760bd578bb40ef93feee861763d287f098ecddab07ed28f44863ee5da4"
    assert {name for name in current if current[name] != previous[name]} == {"ext/remote_sub_exec.py"}
    installed_parent = builder.before_admission_integrity(previous)
    assert {name for name in current if current[name] != installed_parent[name]} == {
        "ext/fabric_task.py", "ext/lane_runtime.py", "ext/remote_sub_exec.py",
    }
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    for value in (current, previous):
        unchanged = dict(value)
        builder.validate_go_base_manifest(value, captured)
        assert value == unchanged
    assert builder.normalize_application_carrier_base_manifest(current) == builder.normalize_application_carrier_base_manifest(previous)
    for output in (builds.default, builds.application, builds.http):
        manifest = json.loads((output / "native-manifest.json").read_bytes())
        raw = (output / "native-code-stage/ext/remote_sub_exec.py").read_bytes()
        assert manifest["ext/remote_sub_exec.py"] == g.digest(raw) == builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_DIGEST
    assert current == original


@pytest.mark.parametrize("corruption", [
    "old-task", "old-runtime", "old-application-parent", "worker-lineage",
    "foreign-member", "missing-member", "extra-member", "application109", "http112",
])
def test_sparse_preflight_cannot_relabel_a_different_complete_parent(builds, corruption):
    current = before_exact_scoped_models(json.loads((builds.default / "native-manifest.json").read_bytes()))
    bad = dict(current)
    if corruption in {"old-task", "old-runtime"}:
        name = "ext/fabric_task.py" if corruption == "old-task" else "ext/lane_runtime.py"
        bad[name] = builder.ADMISSION_INTEGRITY_PREIMAGES[name]
    elif corruption == "old-application-parent":
        bad.update(builder.ADMISSION_INTEGRITY_PREIMAGES)
    elif corruption == "worker-lineage":
        fixture = ROOT.parents[2] / "tests/fixtures/fabric-admission-integrity-worker107-3b2338d.json"
        assert g.digest(fixture.read_bytes()) == "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
        bad = json.loads(fixture.read_bytes())
        bad["ext/remote_sub_exec.py"] = builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_DIGEST
    elif corruption == "foreign-member":
        bad["ext/lease_broker.py"] = "f" * 64
    elif corruption == "missing-member":
        del bad["ext/original_advertised_artifact.py"]
    elif corruption == "extra-member":
        bad["ext/foreign.py"] = "f" * 64
    else:
        output = builds.application if corruption == "application109" else builds.http
        bad = before_extended_host_pull_epoch(json.loads((output / "native-manifest.json").read_bytes()))
        bad.update(builder.EXACT_SCOPED_MODEL_PREIMAGES)
        bad["ext/support_bundle.py"] = builder.APPLICATION_POOL_COMPOSITION_PREIMAGES["ext/support_bundle.py"]
    unchanged = dict(bad)
    captured = {name: bad["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="sparse commit preflight parent closure"):
        builder.validate_go_base_manifest(bad, captured)
    assert bad == unchanged


def test_scoped_model_successor_binds_actual_dependencies_and_preserves_parent(builds):
    prior = before_pool_publisher(json.loads((builds.default / "native-manifest.json").read_bytes()))
    raw = (json.dumps(prior, sort_keys=True, indent=2) + "\n").encode()
    assert g.digest(raw) == "d416ac1611112f757d602ddc73b4ed61636a7dd53c4b66866ce302aeabd7a86f"
    current = json.loads(raw)
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    captured_original = dict(captured)
    builder.validate_go_base_manifest(current, captured)
    previous = builder.before_exact_scoped_models(current)
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "1bb6f2ec3af603e44c345558931d3bf5daec28fa7bc9db14cbad830674ea84d0"
    assert {name for name in current if current[name] != previous[name]} == {
        "ext/go_lease_gateway.py", "ext/lease_broker.py",
    }
    previous_captured = {name: previous["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(previous, previous_captured)
    assert builder.normalize_application_carrier_base_manifest(current) == builder.normalize_application_carrier_base_manifest(previous)
    # Historical normalization must never stand in for captured current source.
    for manifest, dependencies in ((current, previous_captured), (previous, captured)):
        with pytest.raises(ValueError, match="base differs from captured application dependency"):
            builder.validate_go_base_manifest(manifest, dependencies)
    assert captured == captured_original
    assert current == original
    for output in (builds.default, builds.application, builds.http):
        manifest = json.loads((output / "native-manifest.json").read_bytes())
        inventory = json.loads((output / "native-source-inventory.json").read_bytes())
        for name, expected in builder.EXACT_SCOPED_MODEL_DIGESTS.items():
            staged = (output / "native-code-stage" / name).read_bytes()
            source = (ROOT / "candidate" / Path(name).name).read_bytes()
            assert staged == source
            assert g.digest(staged) == manifest[name] == inventory["files"][name]["sha256"] == expected
            assert inventory["files"][name]["source"] == "candidate/" + Path(name).name


@pytest.mark.parametrize("corruption", [
    "old-gateway", "old-broker", "foreign-gateway", "foreign-broker",
    "old-executor", "old-task", "changed-pool", "missing-member", "extra-member",
    "application109", "http112", "worker-parent",
])
def test_scoped_model_successor_rejects_partial_foreign_or_backdated_parent(builds, corruption):
    bad = before_pool_publisher(json.loads((builds.default / "native-manifest.json").read_bytes()))
    if corruption in {"old-gateway", "old-broker", "foreign-gateway", "foreign-broker"}:
        key = "ext/go_lease_gateway.py" if corruption.endswith("gateway") else "ext/lease_broker.py"
        bad[key] = builder.EXACT_SCOPED_MODEL_PREIMAGES[key] if corruption.startswith("old-") else "f" * 64
    elif corruption == "old-executor":
        bad["ext/remote_sub_exec.py"] = builder.SPARSE_COMMIT_PREFLIGHT_EXECUTOR_PREIMAGE
    elif corruption == "old-task":
        bad["ext/fabric_task.py"] = builder.ADMISSION_INTEGRITY_PREIMAGES["ext/fabric_task.py"]
    elif corruption == "changed-pool":
        bad["pool"] = "f" * 64
    elif corruption == "missing-member":
        del bad["ext/original_advertised_artifact.py"]
    elif corruption == "extra-member":
        bad["ext/foreign.py"] = "f" * 64
    elif corruption == "worker-parent":
        fixture = ROOT.parents[2] / "tests/fixtures/fabric-admission-integrity-worker107-3b2338d.json"
        assert g.digest(fixture.read_bytes()) == "8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6"
        bad = json.loads(fixture.read_bytes())
        bad.update(builder.EXACT_SCOPED_MODEL_DIGESTS)
    else:
        output = builds.application if corruption == "application109" else builds.http
        bad = before_extended_host_pull_epoch(json.loads((output / "native-manifest.json").read_bytes()))
        bad["ext/support_bundle.py"] = builder.APPLICATION_POOL_COMPOSITION_PREIMAGES["ext/support_bundle.py"]
    unchanged = dict(bad)
    captured = {name: bad["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    captured_unchanged = dict(captured)
    with pytest.raises(ValueError, match="native scoped-model (cohort|parent closure)"):
        builder.validate_go_base_manifest(bad, captured)
    assert bad == unchanged
    assert captured == captured_unchanged


def test_application_pool_composition_has_one_exact_parent_and_actual_dependencies(builds):
    current = pool_source_fixture(builds)
    original = dict(current)
    parent = builder.before_application_pool_composition(current)
    assert g.digest((json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()) == "b9fd5f760bd578bb40ef93feee861763d287f098ecddab07ed28f44863ee5da4"
    assert len(current) == len(parent) == 107
    assert {key for key in current if current[key] != parent[key]} == set(builder.APPLICATION_POOL_COMPOSITION_DIGESTS)
    installed = builder.before_admission_integrity(parent)
    assert g.digest((json.dumps(installed, sort_keys=True, indent=2) + "\n").encode()) == "3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9"
    assert {key for key in current if current[key] != installed[key]} == (
        set(builder.APPLICATION_POOL_COMPOSITION_DIGESTS) | set(builder.ADMISSION_INTEGRITY_DIGESTS))
    for view in (current, parent):
        captured = {name: view["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
        before = dict(view)
        builder.validate_go_base_manifest(view, captured)
        assert view == before
    stale = {name: parent["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="differs from captured application dependency"):
        builder.validate_go_base_manifest(current, stale)
    assert current == original


@pytest.mark.parametrize("member", tuple(builder.APPLICATION_POOL_COMPOSITION_DIGESTS))
@pytest.mark.parametrize("mutation", ["missing", "foreign", "preimage"])
def test_application_pool_composition_rejects_partial_or_mixed_members(builds, member, mutation):
    current = pool_source_fixture(builds)
    if mutation == "missing":
        del current[member]
    else:
        current[member] = ("f" * 64 if mutation == "foreign"
                           else builder.APPLICATION_POOL_COMPOSITION_PREIMAGES[member])
    original = dict(current)
    captured = {name: current.get("ext/" + name) for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="application pool composition cohort"):
        builder.before_application_pool_composition(current)
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(current, captured)
    assert current == original


@pytest.mark.parametrize("mutation", ["old-task", "old-runtime", "foreign-pool", "foreign-executor", "missing-member", "extra-member", "historical102", "historical104", "historical106"])
def test_application_pool_composition_rejects_unqualified_whole_parents(builds, mutation):
    current = pool_source_fixture(builds)
    if mutation in ("old-task", "old-runtime"):
        key = "ext/fabric_task.py" if mutation == "old-task" else "ext/lane_runtime.py"
        current[key] = builder.ADMISSION_INTEGRITY_PREIMAGES[key]
    elif mutation in ("foreign-pool", "foreign-executor"):
        current["pool" if mutation == "foreign-pool" else "ext/remote_sub_exec.py"] = "f" * 64
    elif mutation == "missing-member":
        del current["ext/pick.py"]
    elif mutation == "extra-member":
        current["ext/unqualified.py"] = "f" * 64
    else:
        historical = before_application_carrier(current)
        historical = (before_original_artifact_recovery(historical)
                      if mutation == "historical106" else before_participant_cohort(historical))
        if mutation == "historical102":
            for cohort in (builder.GO_UBUNTU4_PREIMAGES, builder.GO_COMPLETED_POLL_PREIMAGES, builder.GO_POST_FAILURE_PREIMAGES):
                historical.update({"ext/" + name: value for name, value in cohort.items()})
            for name in builder.GO_POST_FAILURE_ADDITIONS:
                del historical["ext/" + name]
        current = historical
        current.update(builder.APPLICATION_POOL_COMPOSITION_DIGESTS)
    original = dict(current)
    with pytest.raises(ValueError, match="application pool composition parent closure"):
        builder.before_application_pool_composition(current)
    assert current == original


def test_publisher_only_source_is_not_an_application_precursor(builds):
    raw = (ROOT.parents[2] / "tests/fixtures/fabric-publisher-only107-b617445.json").read_bytes()
    assert g.digest(raw) == "c651b8e58d89c7d1968f1c95d2c1153a7077184d7a042deca9bb713d4b2f47f2"
    publisher = json.loads(raw)
    assert publisher["ext/support_bundle.py"] == "bd8058657f884ee4fb7fbad1d937c24041e6d4c204fb1e3dc00953f7482bf3b3"
    for view in (publisher, {**publisher, **builder.APPLICATION_POOL_COMPOSITION_DIGESTS}):
        original = dict(view)
        dependencies = {name: view["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
        with pytest.raises(ValueError):
            builder.validate_go_base_manifest(view, dependencies)
        assert view == original


@pytest.mark.parametrize("variant,members", [("default", 107), ("application", 109), ("http", 112)])
def test_application_pool_composition_emits_actual_complete_provenance(builds, variant, members):
    output = getattr(builds, variant)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    assert len(manifest) == len(inventory["files"]) == members
    for name, digest in manifest.items():
        raw = (output / "native-code-stage" / name).read_bytes()
        row = inventory["files"][name]
        assert g.digest(raw) == row["sha256"] == digest
        assert len(raw) == row["bytes"]
    for key, digest in builder.APPLICATION_POOL_COMPOSITION_DIGESTS.items():
        assert manifest[key] == digest
        assert inventory["files"][key]["source"] == "candidate/" + Path(key).name
        assert g.digest((ROOT / inventory["files"][key]["source"]).read_bytes()) == digest


def test_application_pool_forward_delta_is_reversible_and_source_exact(tmp_path):
    import subprocess
    patch = ROOT.parents[2] / "tests/fixtures/fabric-application-pool-composition-20261107.patch"
    assert g.digest(patch.read_bytes()) == "3fe89c2b49afc8b96352c339790d302806fb3d4516407c4476524168367b428c"
    original = {}
    for key, digest in builder.APPLICATION_POOL_COMPOSITION_DIGESTS.items():
        name = Path(key).name
        original[name] = (ROOT / "candidate" / name).read_bytes()
        assert g.digest(original[name]) == digest
        (tmp_path / name).write_bytes(original[name])
    for options in (("--reverse", "--check"), ("--reverse",)):
        subprocess.run(["git", "apply", *options, str(patch)], cwd=tmp_path, check=True,
                       capture_output=True, timeout=10)
    for key, digest in builder.APPLICATION_POOL_COMPOSITION_PREIMAGES.items():
        assert g.digest((tmp_path / Path(key).name).read_bytes()) == digest
    for options in (("--check",), ()):
        subprocess.run(["git", "apply", *options, str(patch)], cwd=tmp_path, check=True,
                       capture_output=True, timeout=10)
    for name, raw in original.items():
        assert (tmp_path / name).read_bytes() == raw


def test_combined_pool_and_sparse_source_preserves_both_exact_lineages(builds):
    current = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    unchanged = dict(current)
    fixtures = (
        ("fabric-application-sparse-scoped107-317cc5d.json", "d416ac1611112f757d602ddc73b4ed61636a7dd53c4b66866ce302aeabd7a86f", "ext/support_bundle.py"),
        ("fabric-application-pool107-b955c82.json", "d8a112411c28c42e812907435f5b182ce351a4cb4c00e47b94ca1ddf58294ac9", "ext/remote_sub_exec.py"),
    )
    for name, digest, changed in fixtures:
        raw = (ROOT.parents[2] / "tests/fixtures" / name).read_bytes()
        assert g.digest(raw) == digest
        prior = json.loads(raw)
        assert len(current) == len(prior) == 107
        assert set(current) == set(prior)
        assert {key for key in current if current[key] != prior[key]} == {changed, "ext/original_delivery_collector.py"}
        dependencies = {name: prior["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
        builder.validate_go_base_manifest(prior, dependencies)
    parent = builder.before_application_pool_composition(current)
    assert g.digest((json.dumps(parent, sort_keys=True, indent=2) + "\n").encode()) == "2ebfb9435053b90e4ce3bf9dfc6780460f6b2669f070c40c16f5772e928c9608"
    before_sparse = builder.before_sparse_commit_preflight(parent)
    assert g.digest((json.dumps(before_sparse, sort_keys=True, indent=2) + "\n").encode()) == "4f6a64b8b22188c324923b4575dcc1b6490ca59df21ba303d9f16db0f6fd6552"
    dependencies = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    saved_dependencies = dict(dependencies)
    builder.validate_go_base_manifest(current, dependencies)
    historical_dependencies = {name: parent["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    with pytest.raises(ValueError, match="differs from captured application dependency"):
        builder.validate_go_base_manifest(current, historical_dependencies)
    assert dependencies == saved_dependencies
    assert current == unchanged


@pytest.mark.parametrize("mutation", [
    "old-gateway", "old-broker", "foreign-publisher", "foreign-executor",
    "old-task", "old-runtime", "foreign-pool", "missing-member", "extra-member",
    "application109", "http112",
])
def test_combined_pool_and_sparse_source_refuses_unqualified_closures(builds, mutation):
    current = builder.before_host_pull_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    if mutation in {"old-gateway", "old-broker"}:
        key = "ext/go_lease_gateway.py" if mutation == "old-gateway" else "ext/lease_broker.py"
        current[key] = builder.APPLICATION_POOL_COMPOSITION_PREIMAGES[key]
    elif mutation in {"foreign-publisher", "foreign-executor", "foreign-pool"}:
        key = {"foreign-publisher": "ext/support_bundle.py", "foreign-executor": "ext/remote_sub_exec.py", "foreign-pool": "pool"}[mutation]
        current[key] = "f" * 64
    elif mutation in {"old-task", "old-runtime"}:
        key = "ext/fabric_task.py" if mutation == "old-task" else "ext/lane_runtime.py"
        current[key] = builder.ADMISSION_INTEGRITY_PREIMAGES[key]
    elif mutation == "missing-member":
        del current["ext/original_advertised_artifact.py"]
    elif mutation == "extra-member":
        current["ext/foreign.py"] = "f" * 64
    else:
        output = builds.application if mutation == "application109" else builds.http
        current = json.loads((output / "native-manifest.json").read_bytes())
    original = dict(current)
    dependencies = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    saved_dependencies = dict(dependencies)
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(current, dependencies)
    assert current == original
    assert dependencies == saved_dependencies
