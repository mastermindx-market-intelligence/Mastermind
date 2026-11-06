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


def before_participant_cohort(manifest):
    prior = dict(manifest)
    prior.update({"ext/" + name: digest
                  for name, digest in builder.GO_PROTECTED_CUSTODY_PREIMAGES.items()})
    assert prior.pop("ext/participant_binding.py") == "09aafda1390914e283915204459e37900123cd54a3d0f4e9116102f3a8921f56"
    assert prior.pop("ext/fabric_participant_owner.py") == "1619505962de4c73f415312871cc407777bf6c04ba6d02fb9be62c9d54a5545c"
    assert prior["ext/fabric_operator_owner.py"] == "90c6eee6bd7f2ca7d36c6b915a4fe2cae42b749d99ec2170fb39f55c5f72c0c7"
    prior["ext/fabric_operator_owner.py"] = "f81b4f053a22ba973b06214f6d06ed2d66e3fc471c781311f074718683cf4675"
    assert prior["ext/original_delivery_collector.py"] in {
        "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183",
        "44dcbb648bfdd0d0c4b6d5866529aec9341779baf5afd5071330997d1b227a83"}
    prior["ext/original_delivery_collector.py"] = "4343b5c9dc3e4fbed10a68cad8758157412f94e2903a7974bd5abdf7a9154183"
    return prior


def test_default_build_stays_exact_reviewed_106_and_go_adds_only_the_fixed_pair(builds):
    default_raw = (builds.default / "native-manifest.json").read_bytes()
    default = json.loads(default_raw)
    application = json.loads((builds.application / "native-manifest.json").read_bytes())
    assert len(default) == 106
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
        assert default["ext/" + name] == builder.GO_UBUNTU4_DIGESTS[name]
        historical["ext/" + name] = original
    for name, original in builder.GO_PROTECTED_CUSTODY_PREIMAGES.items():
        assert default["ext/" + name] == builder.GO_PROTECTED_CUSTODY_DIGESTS[name]
        historical["ext/" + name] = original
    for name, original in builder.GO_COMPLETED_POLL_PREIMAGES.items():
        assert historical["ext/" + name] == builder.GO_COMPLETED_POLL_DIGESTS[name]
        historical["ext/" + name] = original
    for name, original in builder.GO_POST_FAILURE_PREIMAGES.items():
        assert default["ext/" + name] == builder.GO_POST_FAILURE_DIGESTS[name]
        historical["ext/" + name] = original
    for name, digest in builder.GO_POST_FAILURE_DIAGNOSTICS_ADDITIONS.items():
        assert default["ext/" + name] == digest
        del historical["ext/" + name]
    assert g.digest((json.dumps(historical, sort_keys=True, indent=2) + "\n").encode()) == builder.GO_BASE_MANIFEST_SHA256
    assert {k: v for k, v in application.items() if k in default} == default
    assert set(application) - set(default) == {g.GO_ENTRY, g.GO_HANDLER}
    assert len(application) == 108
    http = json.loads((builds.http / "native-manifest.json").read_bytes())
    assert len(http) == 111
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
    original = dict(current)
    captured = {name: current["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}
    prior = before_participant_cohort(current)
    assert len(prior) == 104
    builder.validate_go_base_manifest(prior, captured)
    builder.validate_go_base_manifest(current, captured)
    assert current == original


def test_original_collection_successor_preserves_prior_releases_without_backdating(builds):
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
    for predecessor in (prior, historical):
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
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
        for name in builder.GO_POST_FAILURE_ADDITIONS: del bad["ext/" + name]
        assert len(bad) == 104
    with pytest.raises(ValueError): builder.validate_go_base_manifest(bad, captured)


@pytest.mark.parametrize("count", [104, 102])
def test_protected_custody_cannot_relabel_prior_namespace(builds, count):
    current = json.loads((builds.default / "native-manifest.json").read_bytes())
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
