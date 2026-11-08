"""Provider preservation through the existing native Go transaction owners."""
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
import zlib

import pytest

import test_quota_reset_native_stage as quota_proof

from test_go_native_stage import builds, native_stage, ROOT, g, installer, builder
from test_go_native_install import (source_owners, owner, go_owner, retained_go_owner,
                                   assert_history, assert_retained_history)


@pytest.fixture(scope="module")
def provider_stage(tmp_path_factory):
    # Use the authenticated historical predecessor and existing sequence-38
    # fixture owner. The moving default composer is a different source cohort.
    repository = ROOT.parents[2]
    sys.path.insert(0, str(repository / "tests"))
    try:
        from provider_plan_fixed_parent import materialize_fixed_sequence38
    finally:
        sys.path.pop(0)
    fixture = json.loads((repository / "tests/fixtures/provider-plan-auto-predecessor.json").read_bytes())
    record, _ = builder.provider_application_record(ROOT)
    profile = json.loads(builder._provider_source(
        ROOT / builder.PROVIDER_APPLICATION_PROFILE_SOURCE, record["provider_profile_sha256"]))
    assert fixture["files"] == profile["base_files"]
    root = tmp_path_factory.mktemp("provider-preserved-input").resolve()
    base = root / "base"
    for relative, spec in fixture["sources"].items():
        raw = ((repository / spec["source"]).read_bytes() if "source" in spec else
               zlib.decompress(base64.b64decode(spec["zlib_base64"], validate=True)))
        assert g.digest(raw) == fixture["files"][relative]
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (base / "RELEASE.json").write_text(json.dumps({
        "digest": profile["base_selection"]["generation"], "files": profile["base_files"]}))
    stage = materialize_fixed_sequence38(root / "provider", base)
    assert {relative: g.digest((stage / relative).read_bytes())
            for relative in profile["files"]} == profile["files"]
    return SimpleNamespace(root=root, stage=stage, files=profile["files"])


def select_provider(case, provider_stage, *, fault=None):
    stage = case.root / "provider-source"
    stage.mkdir()
    files = dict(provider_stage.files)
    for relative in files:
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((provider_stage.stage / relative).read_bytes())
    if fault == "changed":
        key = "ext/native_plan_worker.py"
        raw = (stage / key).read_bytes() + b"\n# changed provider source\n"
        (stage / key).write_bytes(raw)
        files[key] = g.digest(raw)
    elif fault in {"partial", "no-additions"}:
        missing = ({"ext/experiential_transport.py"} if fault == "partial" else
                   builder.PROVIDER_APPLICATION_MEMBERS)
        for key in missing:
            del files[key]
            (stage / key).unlink()
    release = g.publish(stage, case.ext, files)
    selected = g.select(case.store, release.name, g.current(case.store)["generation"])
    return selected


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http"])
def test_selected_provider_cannot_prepare_legacy_application(owner_name, extension, request, provider_stage, builds):
    case = request.getfixturevalue(owner_name)
    selected = select_provider(case, provider_stage)
    target, component = application_target(case, getattr(builds, extension))
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.fixture(scope="module")
def combined_builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("provider-application-build").resolve()
    outputs = {}
    for name, flags in (
            ("base", []), ("application", ["--include-go-application"]),
            ("http", ["--include-go-application", "--include-application-http"]),
            ("quota_base", ["--include-quota-reset-recovery"]),
            ("quota_application", ["--include-quota-reset-recovery", "--include-go-application"]),
            ("quota_http", ["--include-quota-reset-recovery", "--include-go-application",
                            "--include-application-http"])):
        output = root / name
        argv = ["builder", "--output", str(output), "--include-provider-plan-application", *flags]
        with mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            builder.main()
        outputs[name] = output
    return SimpleNamespace(**outputs)


def application_target(case, source):
    output = case.root / "selected-application-source"
    shutil.copytree(source, output)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    builder.stage_external_go_component(ROOT, output, str(case.ext), staged_manifest=manifest)
    target = g.publish(output / "native-code-stage", case.ext, manifest)
    return target, output / "external-go-component"


def owner_api(owner_name):
    if owner_name == "go_owner":
        return SimpleNamespace(prepare=installer.prepare_go, apply=installer.apply_go,
            read=installer.read_go, reconcile=installer.reconcile_go, history=assert_history)
    return SimpleNamespace(prepare=installer.prepare_retained_go, apply=installer.apply_retained_go,
        read=installer.read_retained_go, reconcile=installer.reconcile_retained_go,
        history=assert_retained_history)


def refuse_prepare(case, owner_name, target, component, selected):
    output = case.root / "forbidden-provider-transition"
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("refusal wrote")):
        with pytest.raises(ValueError, match="provider.*transition"):
            owner_api(owner_name).prepare(case.successor, target.name, component, output)
    assert not output.exists() and g.current(case.store) == selected
    owner_api(owner_name).history(case)


def prepare_combined(case, owner_name, provider_stage, source):
    selected = select_provider(case, provider_stage)
    target, component = application_target(case, source)
    bundle = case.root / "provider-application-transition"
    api = owner_api(owner_name)
    plan = api.prepare(case.successor, target.name, component, bundle)
    assert plan["expected_selection"] == selected
    assert g.current(case.store) == selected
    return api, plan, bundle


@pytest.mark.parametrize("extension,count", [
    ("application", 118), ("http", 121), ("quota_application", 118), ("quota_http", 121)])
def test_actual_component_preserves_candidate_and_staged_broker(combined_builds, builds, extension, count):
    output = getattr(combined_builds, extension)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    record = json.loads((output / "external-go-component/component.json").read_bytes())
    original = json.loads((builds.default / "native-manifest.json").read_bytes())
    unchanged = dict(manifest)
    base = {k: v for k, v in manifest.items()
            if k not in {g.GO_ENTRY, g.GO_HANDLER} | builder.HTTP_GENERATION_MEMBERS}
    assert len(manifest) == count and len(base) == 116
    parent = builder.before_quota_reset_recovery(base)
    assert builder.before_provider_application(parent) == original
    assert manifest == unchanged
    broker = "lease_broker.py"
    assert record["native_stage_dependencies"][broker] == manifest["ext/" + broker]
    if extension.startswith("quota_"):
        assert builder._manifest_digest(base) == builder.PROVIDER_QUOTA_RESET_MANIFEST_SHA256
        assert builder._manifest_digest(parent) == builder.PROVIDER_QUOTA_RESET_PARENT_SHA256
        assert record["dependencies"][broker]["sha256"] == builder.PROVIDER_QUOTA_RESET_DIGESTS[broker]
        for name in builder.QUOTA_RESET_PATCHES:
            row = inventory["files"]["ext/" + name]
            composition = row["composition"]
            assert composition["preimage_sha256"] == builder.PROVIDER_QUOTA_RESET_PREIMAGES[name]
            assert composition["patch_sha256"] == builder.QUOTA_RESET_PATCHES[name]
            assert composition["provider_preimage"]["preimage_sha256"] == original["ext/" + name]
            assert composition["provider_preimage"]["sha256"] == builder.PROVIDER_QUOTA_RESET_PREIMAGES[name]
            assert composition["provider_preimage"]["composition_sha256"] == builder.PROVIDER_APPLICATION_RECORD_SHA256
            assert row["source"] == "candidate/" + name
            assert "composition_preimage_sha256" not in row and "patch_sha256" not in row
        assert record["dependencies"][broker]["composition"] == inventory["files"]["ext/" + broker]["composition"]
    else:
        assert record["dependencies"][broker]["sha256"] == original["ext/" + broker]
        assert record["dependencies"][broker]["sha256"] != record["native_stage_dependencies"][broker]
    assert installer._go_component(output / "external-go-component", Path(record["stable_ext"]), manifest)
    for key, digest in manifest.items():
        raw = (output / "native-code-stage" / key).read_bytes()
        assert g.digest(raw) == digest == inventory["files"][key]["sha256"]
        assert len(raw) == inventory["files"][key]["bytes"]
    before = dict(base)
    hashes = {name: row["sha256"] for name, row in record["dependencies"].items()}
    if extension.startswith("quota_"):
        builder.validate_go_base_manifest(base, hashes)
        hashes[broker] = builder.PROVIDER_QUOTA_RESET_PREIMAGES[broker]
    with pytest.raises(ValueError, match="captured application dependency"):
        builder.validate_go_base_manifest(base, hashes)
    assert base == before


@pytest.mark.parametrize("fault", ["broker-preimage", "missing-addition", "changed-retained", "unexpected"])
def test_partial_or_mixed_combined_source_refuses(combined_builds, fault):
    base = json.loads((combined_builds.base / "native-manifest.json").read_bytes())
    record, _ = builder.provider_application_record()
    if fault == "broker-preimage":
        base["ext/lease_broker.py"] = record["replacements"]["ext/lease_broker.py"]["preimage_sha256"]
    elif fault == "missing-addition":
        del base["ext/experiential_transport.py"]
    elif fault == "changed-retained":
        base["ext/model_tier.py"] = "0" * 64
    else:
        base["ext/foreign.py"] = "0" * 64
    before = dict(base)
    with pytest.raises(ValueError, match="provider APPLICATION source cohort"):
        builder.before_provider_application(base)
    assert base == before


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http", "quota_application", "quota_http"])
def test_combined_application_commits_and_recovers_original_transaction(
        owner_name, extension, request, provider_stage, combined_builds):
    case = request.getfixturevalue(owner_name)
    api, plan, bundle = prepare_combined(case, owner_name, provider_stage, getattr(combined_builds, extension))
    with mock.patch.object(g, "_select_locked", wraps=g._select_locked) as select:
        receipt = api.apply(bundle)
        assert select.call_count == 1
    assert receipt["selection"] == g.current(case.store)
    assert receipt["selection"]["sequence"] == plan["expected_selection"]["sequence"] + 1
    assert receipt["bridged"] == ["pool", "task", "go"] and receipt["remote"] == "legacy"
    assert api.read(bundle)[0] == plan
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("completed replay selected")):
        assert api.apply(bundle) == receipt
        assert api.reconcile(bundle) == receipt
    api.history(case)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("fault", ["changed", "partial", "no-additions"])
@pytest.mark.parametrize("target_kind", ["legacy", "provider", "quota"])
def test_invalid_provider_predecessor_cannot_fall_through(
        owner_name, fault, target_kind, request, provider_stage, combined_builds, builds):
    case = request.getfixturevalue(owner_name)
    selected = select_provider(case, provider_stage, fault=fault)
    source = {"legacy": builds.application, "provider": combined_builds.application,
              "quota": combined_builds.quota_application}[target_kind]
    target, component = application_target(case, source)
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "quota_application"])
def test_combined_target_requires_qualified_provider_predecessor(owner_name, extension, request, combined_builds):
    case = request.getfixturevalue(owner_name)
    selected = g.current(case.store)
    target, component = application_target(case, getattr(combined_builds, extension))
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.mark.parametrize("extension", ["application", "http", "quota_application", "quota_http"])
def test_rewound_staged_dependency_is_not_an_installer_component(combined_builds, extension, tmp_path):
    output = tmp_path / "source"
    shutil.copytree(getattr(combined_builds, extension), output)
    path = output / "external-go-component/component.json"
    record = json.loads(path.read_bytes())
    record["native_stage_dependencies"]["lease_broker.py"] = (
        builder.PROVIDER_QUOTA_RESET_PREIMAGES["lease_broker.py"] if extension.startswith("quota_")
        else record["dependencies"]["lease_broker.py"]["sha256"])
    path.write_text(json.dumps(record))
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    with pytest.raises(ValueError, match="exact reviewed source"):
        installer._go_component(output / "external-go-component", Path(record["stable_ext"]), manifest)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("boundary", ["selection", "receipt"])
@pytest.mark.parametrize("extension", ["http", "quota_http"])
def test_combined_postcommit_interruption_does_not_select_again(
        owner_name, boundary, extension, request, provider_stage, combined_builds):
    case = request.getfixturevalue(owner_name)
    api, plan, bundle = prepare_combined(case, owner_name, provider_stage, getattr(combined_builds, extension))
    original = g.atomic_bytes
    seen = []
    def write(path, raw, mode):
        original(path, raw, mode)
        name = Path(path).name
        kind = ("selection" if name == "CURRENT.json" else
                "receipt" if name == plan["digest"] + ".go.json" else None)
        if kind == boundary and not seen:
            seen.append(kind)
            raise OSError("fixture after combined " + kind)
    with mock.patch.object(g, "atomic_bytes", side_effect=write), pytest.raises(OSError, match="fixture"):
        api.apply(bundle)
    assert seen == [boundary] and api.read(bundle)[0] == plan
    with mock.patch.object(g, "_select_locked", side_effect=AssertionError("recovery selected again")):
        receipt = api.reconcile(bundle)
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed recovery wrote")):
        assert api.apply(bundle) == receipt
        assert api.reconcile(bundle) == receipt
    api.history(case)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "quota_application"])
def test_combined_plan_rechecks_complete_pointer_before_any_write(
        owner_name, extension, request, provider_stage, combined_builds):
    case = request.getfixturevalue(owner_name)
    api, plan, bundle = prepare_combined(case, owner_name, provider_stage, getattr(combined_builds, extension))
    before = g.current(case.store)
    later = g.select(case.store, before["generation"], before["generation"])
    assert later["sequence"] == before["sequence"] + 1
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale plan wrote")):
        with pytest.raises(ValueError, match="compare-and-swap"):
            api.apply(bundle)
    assert g.current(case.store) == later
    api.history(case)


@pytest.mark.parametrize("extension", ["application", "quota_application"])
def test_combined_source_retains_original_application_v3_journeys(combined_builds, extension, tmp_path):
    # Reuse the original owner tests in their asserted layout. A fresh process
    # ensures no previously imported candidate can impersonate the staged bytes.
    fixture = tmp_path / "ops/native_fabric/quota_continuity"
    tests = fixture / "tests"
    tests.mkdir(parents=True)
    (fixture / "source").mkdir()
    source = getattr(combined_builds, extension)
    stage = source / "native-code-stage"
    manifest = json.loads((source / "native-manifest.json").read_bytes())
    shutil.copytree(stage / "ext", fixture / "candidate")
    for relative, digest in manifest.items():
        if relative.startswith("ext/"):
            assert g.digest((fixture / "candidate" / Path(relative).name).read_bytes()) == digest
    # The existing selection fixture reads the external handler by its source
    # filename. It is the identical captured handler, not a substitute owner.
    handler = (stage / g.GO_HANDLER).read_bytes()
    assert g.digest(handler) == manifest[g.GO_HANDLER]
    (fixture / "candidate/go_shim.py").write_bytes(handler)
    for name in ("test_application_auto_request.py", "test_application_registered_pool_selection.py",
                 "test_application_turn_admission.py", "_offline_boundary.py",
                 "test_adapter_continuity.py", "test_quota_continuity.py"):
        (tests / name).write_bytes((ROOT / "tests" / name).read_bytes())
    script = """import json, unittest
suite = unittest.defaultTestLoader.loadTestsFromNames([
    'test_application_auto_request.ExactScopedCustodyTests',
    'test_adapter_continuity.Adapter.test_interrupted_descriptor_preserves_original_uncertainty_without_replay',
    'test_adapter_continuity.Adapter.test_orphan_native_artifacts_are_uncertainty_without_content_reads',
    'test_adapter_continuity.Adapter.test_metadata_failure_cannot_be_reported_as_not_found',
    'test_adapter_continuity.Adapter.test_absence_requires_all_incumbent_request_artifacts_to_be_missing',
])
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps(dict(tests=result.testsRun, failures=len(result.failures),
                      errors=len(result.errors), skipped=len(result.skipped))))
raise SystemExit(not result.wasSuccessful() or bool(result.skipped))
"""
    env = dict(os.environ, PYTHONPATH=str(tests), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=tests, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {
        "tests": 14, "failures": 0, "errors": 0, "skipped": 0}


@pytest.mark.parametrize("member", sorted(builder.PROVIDER_QUOTA_RESET_DIGESTS))
@pytest.mark.parametrize("replacement", ["preimage", "foreign"])
def test_provider_quota_partial_or_foreign_quartet_refuses(combined_builds, member, replacement):
    actual = json.loads((combined_builds.quota_base / "native-manifest.json").read_bytes())
    actual["ext/" + member] = (builder.PROVIDER_QUOTA_RESET_PREIMAGES[member]
                              if replacement == "preimage" else "0" * 64)
    before = dict(actual)
    with pytest.raises(ValueError, match="provider quota reset cohort"):
        builder.before_quota_reset_recovery(actual)
    assert actual == before


@pytest.mark.parametrize("fault", ["legacy-quartet", "missing-provider", "foreign-parent"])
def test_provider_quota_cannot_relabel_legacy_or_foreign_parent(combined_builds, fault):
    actual = json.loads((combined_builds.quota_application / "native-manifest.json").read_bytes())
    if fault == "legacy-quartet":
        actual.update({"ext/" + name: digest for name, digest in builder.QUOTA_RESET_DIGESTS.items()})
    elif fault == "missing-provider":
        del actual["ext/experiential_transport.py"]
    else:
        actual["ext/model_tier.py"] = "0" * 64
    before = dict(actual)
    _, provider = builder.provider_application_record()
    with pytest.raises(ValueError, match="provider.*transition"):
        builder.validate_go_source_transition(provider, actual)
    assert actual == before


def test_provider_quota_component_authenticates_both_patch_steps(combined_builds, tmp_path):
    output = tmp_path / "source"
    shutil.copytree(combined_builds.quota_http, output)
    path = output / "external-go-component/component.json"
    record = json.loads(path.read_bytes())
    record["dependencies"]["lease_broker.py"]["composition"]["provider_preimage"]["sha256"] = \
        builder.QUOTA_RESET_PREIMAGES["lease_broker.py"]
    path.write_text(json.dumps(record))
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    with pytest.raises(ValueError, match="exact reviewed source"):
        installer._go_component(output / "external-go-component", Path(record["stable_ext"]), manifest)


class TestProviderQuotaResetBrokerJourney(quota_proof.TestEmittedGlmResetBrokerJourney):
    """Run the original sixteen GLM claim/settlement cases on combined bytes."""

    @classmethod
    def setUpClass(cls):
        cls.stage_temp = tempfile.TemporaryDirectory(prefix="provider-emitted-h2-")
        cls.addClassCleanup(cls.stage_temp.cleanup)
        cls.stage = quota_proof.build(Path(cls.stage_temp.name).resolve() / "http",
            "--include-provider-plan-application", "--include-go-application", "--include-application-http")
        cls.stage_manifest = quota_proof.manifest(cls.stage)


# Sequence-39 keeps the protected remote picker while the original installer
# owns one complete provider/APPLICATION transaction. These are inert fixtures.
@pytest.fixture(scope="module")
def remote_placement_provider_stage(provider_stage, tmp_path_factory):
    repository = ROOT.parents[2]
    sys.path.insert(0, str(repository))
    try:
        from ops.native_fabric.provider_plans import compose
    finally:
        sys.path.pop(0)
    profile = json.loads((compose.HERE / "remote_placement/profile.json").read_bytes())
    assert provider_stage.files == profile["base_files"]
    root = tmp_path_factory.mktemp("provider-remote-placement-input").resolve()
    base, stage = root / "base", root / "provider"
    shutil.copytree(provider_stage.stage, base)
    (base / "RELEASE.json").write_text(json.dumps({
        "digest": profile["base_selection"]["generation"], "files": profile["base_files"],
    }))
    compose.compose(base, stage, profile_name="current116-remote-placement")
    assert {key: g.digest((stage / key).read_bytes()) for key in profile["files"]} == profile["files"]
    return SimpleNamespace(root=root, stage=stage, files=profile["files"])


@pytest.fixture(scope="module")
def remote_placement_builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("provider-remote-application-build").resolve()
    outputs = {}
    for name, flags in (
        ("base", []), ("application", ["--include-go-application"]),
        ("http", ["--include-go-application", "--include-application-http"]),
    ):
        output = root / name
        argv = [
            "builder", "--output", str(output), "--include-provider-plan-application",
            "--include-provider-plan-remote-placement", *flags,
        ]
        with mock.patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            builder.main()
        outputs[name] = output
    return SimpleNamespace(**outputs)


@pytest.mark.parametrize("extension,count", [("base", 116), ("application", 118), ("http", 121)])
def test_remote_placement_complete_build_and_real_dependency_bytes(
        extension, count, remote_placement_builds, combined_builds, builds):
    output = getattr(remote_placement_builds, extension)
    old_output = getattr(combined_builds, extension)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    old = json.loads((old_output / "native-manifest.json").read_bytes())
    expected = dict(old)
    expected["ext/pick.py"] = builder.PROVIDER_REMOTE_PLACEMENT_PICKER_SHA256
    assert manifest == expected and len(manifest) == count
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    for key, digest in manifest.items():
        raw = (output / "native-code-stage" / key).read_bytes()
        assert g.digest(raw) == digest == inventory["files"][key]["sha256"]
        assert len(raw) == inventory["files"][key]["bytes"]
        if key != "ext/pick.py":
            assert raw == (old_output / "native-code-stage" / key).read_bytes()
    row = inventory["files"]["ext/pick.py"]
    record, providers, _ = builder.provider_remote_placement_record()
    chain = row["composition"]
    assert chain["preimage_sha256"] == record["picker"]["preimage_sha256"]
    assert chain["patch_sha256"] == record["picker"]["patch_sha256"]
    assert chain["provider_preimage"]["composition_sha256"] == builder.PROVIDER_APPLICATION_RECORD_SHA256
    assert chain["provider_preimage"]["sha256"] == record["picker"]["preimage_sha256"]
    assert chain["successor_composition_sha256"] == builder.PROVIDER_REMOTE_PLACEMENT_RECORD_SHA256
    base = {key: value for key, value in manifest.items()
            if key not in {g.GO_ENTRY, g.GO_HANDLER} | builder.HTTP_GENERATION_MEMBERS}
    original = json.loads((builds.default / "native-manifest.json").read_bytes())
    unchanged = dict(base)
    assert builder.before_provider_application(base) == original
    assert base == unchanged
    if extension != "base":
        component = json.loads((output / "external-go-component/component.json").read_bytes())
        for name, digest in component["native_stage_dependencies"].items():
            assert digest == manifest["ext/" + name]
        assert installer._go_component(output / "external-go-component",
                                       Path(component["stable_ext"]), manifest)
        before, after = dict(providers), dict(manifest)
        builder.validate_go_source_transition(before, after)
        assert before == providers and after == manifest


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http"])
def test_remote_placement_original_installer_commit_and_recovery(
        owner_name, extension, request, remote_placement_provider_stage, remote_placement_builds):
    test_combined_application_commits_and_recovers_original_transaction(
        owner_name, extension, request, remote_placement_provider_stage, remote_placement_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http"])
@pytest.mark.parametrize("direction", ["rollback-picker", "unqualified-old-predecessor"])
def test_remote_placement_transition_does_not_cross_cohorts(
        owner_name, extension, direction, request, provider_stage,
        remote_placement_provider_stage, combined_builds, remote_placement_builds):
    case = request.getfixturevalue(owner_name)
    before = remote_placement_provider_stage if direction == "rollback-picker" else provider_stage
    after = combined_builds if direction == "rollback-picker" else remote_placement_builds
    selected = select_provider(case, before)
    target, component = application_target(case, getattr(after, extension))
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("fault", ["changed", "partial", "no-additions"])
def test_remote_placement_foreign_provider_predecessor_refuses(
        owner_name, fault, request, remote_placement_provider_stage, remote_placement_builds):
    case = request.getfixturevalue(owner_name)
    selected = select_provider(case, remote_placement_provider_stage, fault=fault)
    target, component = application_target(case, remote_placement_builds.http)
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.mark.parametrize("fault", ["broker-preimage", "missing-addition", "changed-retained", "unexpected"])
def test_remote_placement_original_map_is_checked_before_inverse(remote_placement_builds, fault):
    manifest = json.loads((remote_placement_builds.base / "native-manifest.json").read_bytes())
    legacy, _ = builder.provider_application_record()
    if fault == "broker-preimage":
        manifest["ext/lease_broker.py"] = legacy["replacements"]["ext/lease_broker.py"]["preimage_sha256"]
    elif fault == "missing-addition":
        del manifest["ext/experiential_transport.py"]
    elif fault == "changed-retained":
        manifest["ext/model_tier.py"] = "0" * 64
    else:
        manifest["ext/foreign.py"] = "0" * 64
    unchanged = dict(manifest)
    with pytest.raises(ValueError, match="remote placement APPLICATION closure"):
        builder.before_provider_application(manifest)
    assert manifest == unchanged


@pytest.mark.parametrize("path", [
    "rollout/provider_application/remote-placement.json",
    "rollout/provider_application/composition.json",
    builder.PROVIDER_APPLICATION_PROFILE_SOURCE,
    "../provider_plans/remote_placement/profile.json",
    "../provider_plans/patches/pick_remote_plan_modes.forward.patch",
])
@pytest.mark.parametrize("fault", ["changed", "symlink"])
def test_remote_placement_source_commitments_refuse_drift(tmp_path, path, fault):
    root = tmp_path / "native_fabric/quota_continuity"
    paths = [
        "rollout/provider_application/remote-placement.json",
        "rollout/provider_application/composition.json",
        builder.PROVIDER_APPLICATION_PROFILE_SOURCE,
        "../provider_plans/remote_placement/profile.json",
        "../provider_plans/patches/pick_remote_plan_modes.forward.patch",
    ]
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    # Prove the complete retained baseline before exercising the chosen fault.
    builder.provider_remote_placement_record(root)
    target = root / path
    if fault == "changed":
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        retained = tmp_path / "retained-source"
        retained.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(retained)
    with pytest.raises(ValueError):
        builder.provider_remote_placement_record(root)


@pytest.mark.parametrize("flags", [
    ["--include-provider-plan-remote-placement"],
    ["--include-provider-plan-application", "--include-provider-plan-remote-placement",
     "--include-quota-reset-recovery"],
])
def test_remote_placement_unqualified_flag_pairs_refuse_before_output(tmp_path, flags):
    output = tmp_path / "must-not-exist"
    with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *flags]):
        with pytest.raises(SystemExit) as stopped:
            builder.main()
    assert stopped.value.code == 2 and not output.exists()


@pytest.mark.parametrize("fault", ["changed", "symlink", "missing"])
def test_frozen_provider_realm_refuses_drift_before_stage_write(tmp_path, builds, fault):
    root = tmp_path / "repository/ops/native_fabric/quota_continuity"
    record, _ = builder.provider_application_record(ROOT)
    paths = {
        "rollout/provider_application/composition.json",
        builder.PROVIDER_APPLICATION_PROFILE_SOURCE,
        builder.PROVIDER_APPLICATION_REALM_SOURCE,
        *(row["source"] for row in record["replacements"].values()),
        *(row["source"] for key, row in record["additions"].items()
          if key != "ext/codex_provider_realm.py"),
    }
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())

    def stage(name):
        output = tmp_path / name
        output.mkdir()
        shutil.copytree(builds.default / "native-code-stage", output / "native-code-stage")
        manifest = json.loads((builds.default / "native-manifest.json").read_bytes())
        files = json.loads((builds.default / "native-source-inventory.json").read_bytes())["files"]
        return output, manifest, files

    baseline, complete, inventory = stage("valid")
    builder.compose_provider_application_stage(root, baseline, complete, inventory)
    assert len(complete) == 116
    assert inventory["ext/codex_provider_realm.py"]["source"] == builder.PROVIDER_APPLICATION_REALM_SOURCE
    assert (
        g.digest((baseline / "native-code-stage/ext/codex_provider_realm.py").read_bytes())
        == record["additions"]["ext/codex_provider_realm.py"]["sha256"]
    )

    target = root / builder.PROVIDER_APPLICATION_REALM_SOURCE
    if fault == "changed":
        target.write_bytes(target.read_bytes() + b"\n")
    elif fault == "symlink":
        retained = tmp_path / "retained-realm"
        target.rename(retained)
        target.symlink_to(retained)
    else:
        target.unlink()
    output, manifest, files = stage("refused")
    original_manifest = dict(manifest)
    original_inventory = json.loads(json.dumps(files))
    with pytest.raises(ValueError, match="provider APPLICATION source"):
        builder.compose_provider_application_stage(root, output, manifest, files)
    assert manifest == original_manifest and files == original_inventory
    assert {name: g.digest((output / "native-code-stage" / name).read_bytes())
            for name in original_manifest} == original_manifest
    assert not (output / "native-code-stage/ext/codex_provider_realm.py").exists()
