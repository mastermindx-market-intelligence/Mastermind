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

def before_admission_integrity(manifest):
    # Historical-generation cases retain their exact parent, while the current
    # build and the new successor tests below inspect the actual repaired bytes.
    previous = builder.before_host_pull_integrity(manifest)
    if any(previous.get(name) == digest
           for name, digest in builder.ADMISSION_INTEGRITY_DIGESTS.items()):
        assert {name: previous[name] for name in builder.ADMISSION_INTEGRITY_DIGESTS} == builder.ADMISSION_INTEGRITY_DIGESTS
        previous.update(builder.ADMISSION_INTEGRITY_PREIMAGES)
        assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == builder.ADMISSION_INTEGRITY_PARENT_MANIFEST_SHA256
    return previous


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
        "44dcbb648bfdd0d0c4b6d5866529aec9341779baf5afd5071330997d1b227a83"}
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
    default = json.loads(default_raw)
    application = json.loads((builds.application / "native-manifest.json").read_bytes())
    assert len(default) == 107
    previous = before_original_artifact_recovery(default)
    captured = {name: g.digest((ROOT / "candidate" / name).read_bytes())
                for name in builder.GO_APPLICATION_DEPENDENCIES}
    builder.validate_go_base_manifest(default, captured)
    assert default["ext/pick.py"] == builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["pick.py"]
    historical = before_participant_cohort(default)
    historical.update({"ext/" + name: value for name, value in builder.GO_BASE_DEPENDENCIES.items()})
    historical["ext/pick.py"] = builder.GO_BASE_PICKER_SHA256
    assert default["ext/remote_sub_exec.py"] == builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS["remote_sub_exec.py"]
    historical["ext/remote_sub_exec.py"] = builder.GO_BASE_EXECUTOR_SHA256
    historical.update({"ext/" + name: value for name, value in builder.GO_SELECTION_SUPPORT_PREIMAGES.items()})
    assert default["ext/provider_outcome.py"] == builder.GO_PROTECTED_PROVIDER_OUTCOME_SHA256
    historical["ext/provider_outcome.py"] = builder.GO_BASE_PROVIDER_OUTCOME_SHA256
    for name, original in builder.GO_UBUNTU4_PREIMAGES.items():
        expected = (builder.ADMISSION_INTEGRITY_DIGESTS["ext/fabric_task.py"] if name == "fabric_task.py"
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
    assert {k: v for k, v in application.items() if k in default} == default
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
    manifest = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_participant_cohort(current)
    assert len(prior) == 104
    builder.validate_go_base_manifest(prior, captured)
    builder.validate_go_base_manifest(current, captured)
    assert current == original


def test_original_collection_successor_preserves_prior_releases_without_backdating(builds):
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    key = "ext/original_delivery_collector.py"
    old = "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183"
    new = "44dcbb648bfdd0d0c4b6d5866529aec9341779baf5afd5071330997d1b227a83"
    assert current[key] == new
    for digest in (old, new):
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
        backdated = dict(predecessor, **{key: new})
        with pytest.raises(ValueError, match="original collector"):
            builder.validate_go_base_manifest(backdated, captured)
    for digest in ("f" * 64, "", None):
        with pytest.raises(ValueError, match="original collector"):
            builder.validate_go_base_manifest(dict(current, **{key: digest}), captured)


@pytest.mark.parametrize("corruption", ["binding-absent", "owner-absent", "binding-hash",
    "owner-hash", "old-operator-with-pair", "new-operator-without-pair", "participants-without-diagnostics"])
def test_participant_cohort_cannot_relabel_legacy_namespace(builds, corruption):
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    previous = before_original_artifact_recovery(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    for manifest in (previous, current):
        original = dict(manifest)
        builder.validate_go_base_manifest(manifest, captured)
        assert manifest == original
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "5721f06f28d39b493a3b1cfc7d37d3ae5741818e0197ef723a23db15f109c295"


@pytest.mark.parametrize("corruption", ["reader-missing", "reader-hash", "delivery-hash",
    "new-reader-old-delivery", "new-delivery-without-reader", "pair-in104", "pair-in102"])
def test_original_artifact_pair_cannot_expand_or_relabel_historical_namespace(builds, corruption):
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    current["ext/lane_runtime.py"] = digest
    before = dict(current)
    with pytest.raises(ValueError, match="census is not the exact"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def test_exact_remote_cwd_task_preserves_original_107_and_caller_manifest(builds):
    current = before_request_refusal_task(before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes())))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
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
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    current["ext/fabric_task.py"] = digest
    before = dict(current)
    with pytest.raises(ValueError):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def test_refusal_diagnostics_preserve_exact_remote_cwd_107_and_raw_identity(builds):
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    assert len(current) == 107
    assert current["ext/fabric_task.py"] == builder.GO_REQUEST_REFUSAL_TASK_DIGEST
    previous = before_request_refusal_task(current)
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == "c7cf946bc1d8f13ef7b512d071d85097e1ddc58979af76bf367a7707aa90617d"
    for manifest in (current, previous):
        before = dict(manifest)
        builder.validate_go_base_manifest(manifest, captured)
        assert manifest == before


def test_refusal_task_cannot_mix_the_predecessor_poll_helper(builds):
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    current["ext/remote_sub_helpers.py"] = builder.GO_COMPLETED_POLL_PREIMAGES["remote_sub_helpers.py"]
    before = dict(current)
    with pytest.raises(ValueError, match="completed-poll cohort"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


@pytest.mark.parametrize("missing", ["pool", "ext/participant_binding.py"])
def test_refusal_task_requires_the_complete_raw_namespace(builds, missing):
    current = before_admission_integrity(json.loads((builds.default / "native-manifest.json").read_bytes()))
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    del current[missing]
    before = dict(current)
    with pytest.raises(ValueError, match="dependency closure"):
        builder.validate_go_base_manifest(current, captured)
    assert current == before


def test_admission_integrity_successor_binds_actual_sources_and_preserves_parent(builds):
    current = builder.before_host_pull_integrity(
        json.loads((builds.default / "native-manifest.json").read_bytes()))
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    previous = before_admission_integrity(current)
    assert previous != current
    assert {name for name in current if current[name] != previous[name]} == set(builder.ADMISSION_INTEGRITY_DIGESTS)
    assert g.digest((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == builder.ADMISSION_INTEGRITY_PARENT_MANIFEST_SHA256
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
    current = builder.before_host_pull_integrity(
        json.loads((builds.default / "native-manifest.json").read_bytes()))
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
        bad = (before_original_artifact_recovery(current)
               if corruption == "historical106" else before_participant_cohort(current))
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
