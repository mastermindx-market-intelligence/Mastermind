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
    # Use the existing authenticated predecessor and unchanged seq36->37
    # composer. The resulting RELEASE metadata is not a live selection receipt.
    repository = ROOT.parents[2]
    sys.path.insert(0, str(repository))
    try:
        from ops.native_fabric.provider_plans import compose
    finally:
        sys.path.pop(0)
    fixture = json.loads((repository / "tests/fixtures/provider-plan-auto-predecessor.json").read_bytes())
    profile = json.loads((compose.HERE / "profile.json").read_bytes())
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
    stage = root / "provider"
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    git_env = {"GIT_CONFIG_COUNT": str(count + 2),
        f"GIT_CONFIG_KEY_{count}": "gc.auto", f"GIT_CONFIG_VALUE_{count}": "0",
        f"GIT_CONFIG_KEY_{count + 1}": "maintenance.auto", f"GIT_CONFIG_VALUE_{count + 1}": "false"}
    with mock.patch.dict(os.environ, git_env):
        compose.compose(base, stage)
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
    historical_original = builder.before_glm_application_core(original)
    unchanged = dict(manifest)
    base = {k: v for k, v in manifest.items()
            if k not in {g.GO_ENTRY, g.GO_HANDLER} | builder.HTTP_GENERATION_MEMBERS}
    assert len(manifest) == count and len(base) == 116
    parent = builder.before_quota_reset_recovery(base)
    assert builder.before_provider_application(parent) == historical_original
    assert manifest == unchanged
    broker = "lease_broker.py"
    expected_core = {
        "go_lease_capability.py": "c4b7ec997cb73a5fbbcd40868de9f9825e18770a82ba4202b8a6de27c9dbcc86",
        "go_lease_gateway.py": "4e34f9aa2810a9d897d2b2b3135f91f6f4759e7c08c0575e50cdbab7996e8193",
        broker: ("470991af25bccc430a6310fb2de5438c6d4f66135f6faf614b405a1ff8c2004c" if extension.startswith("quota_")
                 else "5a672d318d49ae0d0be91c4669bdbca23a9e589e576aeed16531197664c8fdd0"),
    }
    assert {name: manifest["ext/" + name] for name in expected_core} == expected_core
    assert original["ext/" + broker] == "b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004"
    assert record["native_stage_dependencies"][broker] == manifest["ext/" + broker]
    if extension.startswith("quota_"):
        assert builder._manifest_digest(builder.before_glm_application_core(base)) == builder.PROVIDER_QUOTA_RESET_MANIFEST_SHA256
        assert builder._manifest_digest(parent) == builder.PROVIDER_QUOTA_RESET_PARENT_SHA256
        assert record["dependencies"][broker]["sha256"] == "470991af25bccc430a6310fb2de5438c6d4f66135f6faf614b405a1ff8c2004c"
        for name in builder.QUOTA_RESET_PATCHES:
            row = inventory["files"]["ext/" + name]
            composition = (record["dependencies"][broker]["composition"]["inherited"]
                           if name == broker else row["composition"])
            assert composition["preimage_sha256"] == builder.PROVIDER_QUOTA_RESET_PREIMAGES[name]
            assert composition["patch_sha256"] == builder.QUOTA_RESET_PATCHES[name]
            assert composition["provider_preimage"]["preimage_sha256"] == historical_original["ext/" + name]
            assert composition["provider_preimage"]["sha256"] == builder.PROVIDER_QUOTA_RESET_PREIMAGES[name]
            assert composition["provider_preimage"]["composition_sha256"] == builder.PROVIDER_APPLICATION_RECORD_SHA256
            assert row["source"] == "candidate/" + name
            assert "composition_preimage_sha256" not in row and "patch_sha256" not in row
        expected_outer = {"schema":"mastermind.glm-native-core-source.v1","preimage_sha256":"831fadce3c723d011c0b164d791efcbbe5eac286e9008f7a25394136a1632173","candidate_sha256":"b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004"}
        expected_inherited = {"schema":"native-exact-forward-patch.v1","preimage_sha256":"77648f14204d0f314b6ce5770f6c0d7e130cba5c197fa14c3b61c88ca462562b","patch_source":"../grok47/quota_billing/lease_broker.py.patch","patch_sha256":"b4ef4980f85ef0cce64c6843c9c5d0d16abf0459fda8a438b474789d86c6f421","provider_preimage":{"composition_sha256":"7bbe9fbffd0087d7ae5c191a50e8c6f6ce28fae43554a97e4efc0c23bba26584","source":"rollout/provider_application/lease_broker.py.patch","patch_sha256":"1b412ede2621442f1a85f9e3033a4132a4f3bc47c19afe498345d7fb1b69878b","preimage_sha256":"0bbf1ca05b655c30e895cebf63c914cbf97f9d17fc8b3e55c852fd4652ed8807","sha256":"77648f14204d0f314b6ce5770f6c0d7e130cba5c197fa14c3b61c88ca462562b"}}
        assert inventory["files"]["ext/" + broker]["composition"] == expected_outer
        assert record["dependencies"][broker]["composition"] == dict(
            expected_outer, inherited=expected_inherited)
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
        base["ext/lease_broker.py"] = "b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004"
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
def test_combined_source_retains_original_application_v3_journeys(
        combined_builds, extension, tmp_path, *, memory_support=False):
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
    if memory_support:
        # Native42 deliberately refuses unsafe packet objects before the old
        # generic uncertainty reader. Preserve that stronger privacy contract.
        privacy = """import test_adapter_continuity as adapter
from fabric_operator_contract import DelegationRefused
native42_privacy_refusals = []
class Native42Adapter(adapter.Adapter):
    def assert_unverified_original(self, run):
        if run not in {'orphan-packet-directory', 'orphan-packet-dangling_symlink'}:
            return super().assert_unverified_original(run)
        packet = self.path(run, '.request.packet')
        self.assertTrue(packet.is_dir() or packet.is_symlink())
        with self.assertRaisesRegex(DelegationRefused, '^participant_view_required$'):
            adapter.api.inspect_run(run, owner_ext=self.root)
        self.assertEqual(self.calls, [])
        native42_privacy_refusals.append(run)
"""
        script = privacy + script.replace(
            "'test_adapter_continuity.Adapter.", "'__main__.Native42Adapter.")
        script = script.replace(
            "raise SystemExit(not result.wasSuccessful() or bool(result.skipped))",
            "assert sorted(native42_privacy_refusals) == "
            "['orphan-packet-dangling_symlink', 'orphan-packet-directory']\n"
            "raise SystemExit(not result.wasSuccessful() or bool(result.skipped))")
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
    actual = builder.before_glm_application_core(actual)
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
    record["dependencies"]["lease_broker.py"]["composition"]["inherited"]["provider_preimage"]["sha256"] = \
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
    assert builder.before_provider_application(base) == builder.before_glm_application_core(original)
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
        manifest["ext/lease_broker.py"] = "b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004"
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
    "../provider_plans/profile.json",
    "../provider_plans/remote_placement/profile.json",
    "../provider_plans/patches/pick_remote_plan_modes.forward.patch",
])
@pytest.mark.parametrize("fault", ["changed", "symlink"])
def test_remote_placement_source_commitments_refuse_drift(tmp_path, path, fault):
    root = tmp_path / "native_fabric/quota_continuity"
    paths = [
        "rollout/provider_application/remote-placement.json",
        "rollout/provider_application/composition.json",
        "../provider_plans/profile.json",
        "../provider_plans/remote_placement/profile.json",
        "../provider_plans/patches/pick_remote_plan_modes.forward.patch",
    ]
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
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


# The selected maintenance family retains its sealed provider parent. It is not
# the different five-member variant produced by the ordinary provider fixture.
@pytest.fixture(scope="module")
def maintenance_guard_provider_stage(tmp_path_factory):
    from tests.provider_plan_fixed_parent import materialize_fixed_parent
    from ops.native_fabric.provider_plans import compose
    root = tmp_path_factory.mktemp("provider-maintenance-input").resolve()
    base = materialize_fixed_parent(root / "base")
    stage = root / "provider"
    profile_bytes = (
        ROOT / "rollout/provider_application/maintenance_guard/native40-profile.json"
    ).read_bytes()
    profile = json.loads(profile_bytes)
    files = builder.provider_maintenance_guard_files()
    assert profile["files"] == files
    assert profile["source_map"] == {}
    profile_root = root / "profile-source"
    (profile_root / "maintenance_guard").mkdir(parents=True)
    (profile_root / "maintenance_guard/profile.json").write_bytes(profile_bytes)
    original_here = compose.HERE
    for row in profile["patches"].values():
        patch_bytes = (original_here / row["patch"]).read_bytes()
        assert g.digest(patch_bytes) == row["patch_sha256"]
        patch_path = profile_root / row["patch"]
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_bytes(patch_bytes)
    with mock.patch.object(compose, "HERE", profile_root):
        compose.compose(base, stage, profile_name="current116-maintenance-guard")
    assert compose.HERE == original_here
    assert {name: g.digest((stage / name).read_bytes()) for name in files} == files
    assert files == builder.provider_maintenance_guard_files()
    return SimpleNamespace(root=root, stage=stage, files=files)


@pytest.fixture(scope="module")
def maintenance_guard_builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("provider-maintenance-application").resolve()
    outputs = {}
    for name, flags in (
        ("base", []), ("application", ["--include-go-application"]),
        ("http", ["--include-go-application", "--include-application-http"]),
    ):
        output = root / name
        with mock.patch.object(sys, "argv", [
                "builder", "--output", str(output),
                "--include-provider-plan-application",
                "--include-provider-plan-remote-placement",
                "--include-provider-plan-maintenance-guard", *flags,
        ]), redirect_stdout(io.StringIO()):
            builder.main()
        outputs[name] = output
    return SimpleNamespace(**outputs)


@pytest.mark.parametrize("extension,count", [("base", 116), ("application", 118), ("http", 121)])
def test_maintenance_composition_retains_only_the_five_protected_payloads(
        extension, count, maintenance_guard_builds, remote_placement_builds):
    output = getattr(maintenance_guard_builds, extension)
    prior_output = getattr(remote_placement_builds, extension)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    prior = json.loads((prior_output / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    assert len(manifest) == count and set(manifest) == set(prior)
    assert {key for key in manifest if manifest[key] != prior[key]} == set(builder.PROVIDER_MAINTENANCE_GUARD_MEMBERS)
    for name, digest in manifest.items():
        raw = (output / "native-code-stage" / name).read_bytes()
        row = inventory["files"][name]
        assert g.digest(raw) == row["sha256"] == digest and len(raw) == row["bytes"]
        if name in builder.PROVIDER_MAINTENANCE_GUARD_MEMBERS:
            protected = builder.PROVIDER_MAINTENANCE_GUARD_MEMBERS[name]
            assert digest == protected["sha256"]
            assert raw == (ROOT / protected["source"]).read_bytes()
            assert row["composition"]["source_commit"] == "2541a68e9240ca3fb5c1fda7b68e1df8984c973b"
            assert row["composition"]["source_blob"] == protected["source_blob"]
            assert row["composition"]["preimage_sha256"] == prior[name]
            assert row["composition"]["inherited"]["sha256"] == prior[name]
        else:
            assert raw == (prior_output / "native-code-stage" / name).read_bytes()
    base = {key: value for key, value in manifest.items()
            if key not in {g.GO_ENTRY, g.GO_HANDLER} | builder.HTTP_GENERATION_MEMBERS}
    before = dict(base)
    assert builder.before_provider_application(base) == builder.before_provider_application(
        {key: value for key, value in prior.items()
         if key not in {g.GO_ENTRY, g.GO_HANDLER} | builder.HTTP_GENERATION_MEMBERS})
    assert base == before
    if extension != "base":
        component = json.loads((output / "external-go-component/component.json").read_bytes())
        assert installer._go_component(output / "external-go-component", Path(component["stable_ext"]), manifest)
        for name, digest in component["native_stage_dependencies"].items():
            assert digest == manifest["ext/" + name]
        predecessor = builder.provider_maintenance_guard_files()
        saved = dict(predecessor), dict(manifest)
        builder.validate_go_source_transition(predecessor, manifest)
        assert (predecessor, manifest) == saved


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http"])
def test_maintenance_original_installer_commits_and_recovers(
        owner_name, extension, request, maintenance_guard_provider_stage, maintenance_guard_builds):
    test_combined_application_commits_and_recovers_original_transaction(
        owner_name, extension, request, maintenance_guard_provider_stage, maintenance_guard_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
def test_maintenance_current_cas_is_checked_before_any_write(
        owner_name, request, maintenance_guard_provider_stage, maintenance_guard_builds):
    case = request.getfixturevalue(owner_name)
    api, plan, bundle = prepare_combined(case, owner_name, maintenance_guard_provider_stage,
                                        maintenance_guard_builds.http)
    selected = g.current(case.store)
    later = g.select(case.store, selected["generation"], selected["generation"])
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale CURRENT wrote")):
        with pytest.raises(ValueError, match="compare-and-swap"):
            api.apply(bundle)
    assert g.current(case.store) == later
    api.history(case)


@pytest.mark.parametrize("direction", ["maintenance-to-legacy", "legacy-to-maintenance"])
def test_maintenance_predecessor_and_target_families_cannot_cross(
        direction, maintenance_guard_builds, remote_placement_builds):
    _, legacy, _ = builder.provider_remote_placement_record()
    maintenance = builder.provider_maintenance_guard_files()
    source, output = ((maintenance, remote_placement_builds.http)
                      if direction == "maintenance-to-legacy" else (legacy, maintenance_guard_builds.http))
    target = json.loads((output / "native-manifest.json").read_bytes())
    saved = dict(source), dict(target)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(source, target)
    assert (source, target) == saved


@pytest.mark.parametrize("fault", [
    "broker-only", "executor-only", "provider-variant", "retained-member",
    "missing-member", "extra-member", "picker", "unknown-broker",
])
def test_maintenance_partial_or_foreign_predecessor_cannot_normalize(fault, maintenance_guard_builds):
    before = builder.provider_maintenance_guard_files()
    _, legacy, _ = builder.provider_remote_placement_record()
    if fault == "broker-only":
        before["ext/remote_sub_exec.py"] = legacy["ext/remote_sub_exec.py"]
    elif fault == "executor-only":
        before["ext/lease_broker.py"] = legacy["ext/lease_broker.py"]
    elif fault == "provider-variant":
        before["ext/native_plan_worker.py"] = legacy["ext/native_plan_worker.py"]
    elif fault == "retained-member":
        before["ext/model_tier.py"] = "0" * 64
    elif fault == "missing-member":
        del before["ext/experiential_transport.py"]
    elif fault == "extra-member":
        before["ext/foreign.py"] = "0" * 64
    elif fault == "picker":
        before["ext/pick.py"] = "0" * 64
    else:
        before["ext/lease_broker.py"] = "0" * 64
    after = json.loads((maintenance_guard_builds.http / "native-manifest.json").read_bytes())
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("member", tuple(builder.PROVIDER_MAINTENANCE_GUARD_MEMBERS) + ("ext/model_tier.py",))
def test_maintenance_partial_target_cannot_use_a_complete_predecessor(member, maintenance_guard_builds):
    before = builder.provider_maintenance_guard_files()
    after = json.loads((maintenance_guard_builds.http / "native-manifest.json").read_bytes())
    after[member] = "0" * 64
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)


MAINTENANCE_SOURCE_INPUTS = [
    "rollout/provider_application/remote-placement.json",
    "rollout/provider_application/composition.json",
    "../provider_plans/profile.json",
    "../provider_plans/remote_placement/profile.json",
    "../provider_plans/patches/pick_remote_plan_modes.forward.patch",
    "rollout/provider_application/maintenance_guard/native40-profile.json",
    "rollout/provider_application/maintenance_guard/native40-provenance.json",
    "../provider_plans/router_admission.json",
    "../provider_plans/maintenance_guard/lease_broker.py.patch",
    "../provider_plans/maintenance_guard/remote_sub_exec.py.patch",
] + [row["source"] for row in builder.PROVIDER_MAINTENANCE_GUARD_MEMBERS.values()]


@pytest.mark.parametrize("path", MAINTENANCE_SOURCE_INPUTS[5:])
@pytest.mark.parametrize("fault", ["changed", "symlink"])
def test_maintenance_retained_source_commitments_fail_closed(tmp_path, path, fault):
    root = tmp_path / "native_fabric/quota_continuity"
    for relative in MAINTENANCE_SOURCE_INPUTS:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    assert builder.provider_maintenance_guard_files(root) == builder.provider_maintenance_guard_files()
    target = root / path
    if fault == "changed":
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        retained = tmp_path / "foreign-source"
        retained.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(retained)
    with pytest.raises(ValueError):
        builder.provider_maintenance_guard_files(root)


@pytest.mark.parametrize("flags", [
    ["--include-provider-plan-maintenance-guard"],
    ["--include-provider-plan-application", "--include-provider-plan-maintenance-guard"],
    ["--include-provider-plan-application", "--include-provider-plan-remote-placement",
     "--include-provider-plan-maintenance-guard", "--include-quota-reset-recovery"],
])
def test_maintenance_unqualified_flags_refuse_before_output(tmp_path, flags):
    output = tmp_path / "must-not-exist"
    with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *flags]):
        with pytest.raises(SystemExit) as stopped:
            builder.main()
    assert stopped.value.code == 2 and not output.exists()


# Actual selected native41 retains terminal diagnostics from the protected
# provider composer. The retained guard profile above is a distinct source
# cohort; neither its name nor a worker-only match is an installation proof.
@pytest.fixture(scope="module")
def terminal_provider_stage(tmp_path_factory):
    repository = ROOT.parents[2]
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    git_env = {"GIT_CONFIG_COUNT": str(count + 2),
        f"GIT_CONFIG_KEY_{count}": "gc.auto", f"GIT_CONFIG_VALUE_{count}": "0",
        f"GIT_CONFIG_KEY_{count + 1}": "maintenance.auto",
        f"GIT_CONFIG_VALUE_{count + 1}": "false"}
    with mock.patch.object(sys, "path", [str(repository / "tests"), str(repository), *sys.path]), \
            mock.patch.dict(os.environ, git_env):
        from test_current116_maintenance_guard_composition import current_source
        from test_current40_terminal_diagnostic_composition import source40
        from test_terminal_memory_successor_composition import terminal_source
        source39 = current_source.__wrapped__(tmp_path_factory)
        source40_path = source40.__wrapped__(source39, tmp_path_factory)
        stage = terminal_source.__wrapped__(source40_path, tmp_path_factory)
    files = json.loads((stage / "FILES.json").read_bytes())
    assert files == builder.provider_terminal_diagnostics_files()
    assert len(files) == 116
    return SimpleNamespace(root=stage.parent, stage=stage, files=files)


@pytest.fixture(scope="module")
def terminal_diagnostics_builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("terminal-application-builds").resolve()
    outputs = {}
    common = ["--include-provider-plan-application",
              "--include-provider-plan-remote-placement",
              "--include-provider-plan-maintenance-guard"]
    for name, flags in (
        ("base", []), ("application", ["--include-go-application"]),
        ("http", ["--include-go-application", "--include-application-http"]),
        ("glm", ["--include-go-application", "--include-application-http",
                 "--include-application-glm"]),
        ("legacy_glm", ["--include-go-application", "--include-application-http",
                        "--include-application-glm"]),
    ):
        output = root / name
        terminal = [] if name == "legacy_glm" else [
            "--include-provider-plan-terminal-diagnostics"]
        with mock.patch.object(sys, "argv", [
                "builder", "--output", str(output), *common, *terminal, *flags,
        ]), redirect_stdout(io.StringIO()):
            builder.main()
        outputs[name] = output
    return SimpleNamespace(**outputs)


@pytest.mark.parametrize("extension,count", [
    ("base", 116), ("application", 118), ("http", 121), ("glm", 123),
])
def test_terminal_join_preserves_complete_application_closures(
        extension, count, terminal_diagnostics_builds, maintenance_guard_builds):
    output = getattr(terminal_diagnostics_builds, extension)
    previous = (terminal_diagnostics_builds.legacy_glm if extension == "glm"
                else getattr(maintenance_guard_builds, extension))
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    prior = json.loads((previous / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    record, predecessor, patch = builder.provider_terminal_diagnostics_record()
    member = record["member"]
    assert len(manifest) == count and set(manifest) == set(prior)
    assert {name for name in manifest if manifest[name] != prior[name]} == {member}
    assert manifest[member] == record["combined_sha256"]
    assert g.digest(patch) == record["forward_patch_sha256"]
    for name, wanted in manifest.items():
        raw = (output / "native-code-stage" / name).read_bytes()
        row = inventory["files"][name]
        assert g.digest(raw) == wanted == row["sha256"]
        assert len(raw) == row["bytes"]
        if name != member:
            assert raw == (previous / "native-code-stage" / name).read_bytes()
    row = inventory["files"][member]
    assert row["composition"]["preimage_sha256"] == prior[member]
    assert row["composition"]["inherited"]["sha256"] == prior[member]
    assert row["composition"]["successor_composition_sha256"] == (
        builder.PROVIDER_TERMINAL_DIAGNOSTICS_RECORD_SHA256)
    assert builder.before_provider_application(builder._application_base(manifest)) == (
        builder.before_provider_application(builder._application_base(prior)))
    if extension != "base":
        saved = dict(predecessor), dict(manifest)
        builder.validate_go_source_transition(predecessor, manifest)
        assert (predecessor, manifest) == saved
        component = json.loads((output / "external-go-component/component.json").read_bytes())
        assert installer._go_component(
            output / "external-go-component", Path(component["stable_ext"]), manifest)
        assert all(manifest["ext/" + name] == wanted
                   for name, wanted in component["native_stage_dependencies"].items())
    if extension == "glm":
        # This existing metadata field follows the source HEAD, so a historical
        # 479d stage cannot be compared as a raw manifest after a new commit.
        realm = json.loads((previous / "native-code-stage/ext/application_http_realms.v2.json").read_bytes())
        head = subprocess.check_output(
            ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false",
             "-C", str(ROOT.parents[2]), "rev-parse", "HEAD"], text=True).strip()
        assert realm["glm_source_commit"] == head


def test_terminal_join_retains_both_exact_worker_parents(
        terminal_provider_stage, terminal_diagnostics_builds, tmp_path):
    import ast
    record, predecessor, patch = builder.provider_terminal_diagnostics_record()
    member = record["member"]
    terminal = (terminal_provider_stage.stage / member).read_bytes()
    guard = (ROOT / builder.PROVIDER_MAINTENANCE_GUARD_MEMBERS[member]["source"]).read_bytes()
    joined = (terminal_diagnostics_builds.base / "native-code-stage" / member).read_bytes()
    original_patch = (ROOT / record["original_component"]["patch_source"]).read_bytes()
    assert g.digest(terminal) == record["original_component"]["after"] == predecessor[member]
    assert g.digest(guard) == record["guard_preimage_sha256"]
    assert builder._quota_reset_patch(guard, patch, "native_plan_worker.py") == joined
    # The original patch uses Git's accepted blank-context representation,
    # whereas the new APPLICATION patch uses the stricter incumbent parser.
    # Reverse the original component mechanically; this does not re-admit its
    # frozen parent or create a selected-generation receipt.
    reversed_worker = tmp_path / member
    reversed_worker.parent.mkdir(parents=True)
    reversed_worker.write_bytes(joined)
    inverse = subprocess.run(
        ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false",
         "apply", "--reverse", "--whitespace=nowarn", "-"],
        input=original_patch, cwd=tmp_path, capture_output=True)
    assert inverse.returncode == 0, inverse.stderr.decode()
    assert reversed_worker.read_bytes() == guard

    def invoke(raw):
        text = raw.decode()
        node = next(item for item in ast.parse(text).body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "invoke")
        return "".join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno]).encode()

    assert invoke(joined) == invoke(guard)
    assert joined.count(invoke(joined)) == 1
    assert joined.replace(invoke(joined), invoke(terminal), 1) == terminal
    assert builder.provider_terminal_diagnostics_files() == predecessor
    assert builder.provider_maintenance_guard_files()[member] == record["guard_preimage_sha256"]


@pytest.mark.parametrize("fault", [
    "guard-worker", "preterminal-worker", "mixed-guard", "retained",
    "missing", "extra", "picker",
])
def test_terminal_join_rejects_partial_or_foreign_predecessors(fault, terminal_diagnostics_builds):
    before = builder.provider_terminal_diagnostics_files()
    guard = builder.provider_maintenance_guard_files()
    record, _, _ = builder.provider_terminal_diagnostics_record()
    if fault == "guard-worker":
        before[record["member"]] = guard[record["member"]]
    elif fault == "preterminal-worker":
        before[record["member"]] = record["original_component"]["before"]
    elif fault == "mixed-guard":
        before["ext/experiential_transport.py"] = guard["ext/experiential_transport.py"]
    elif fault == "retained":
        before["ext/model_tier.py"] = "0" * 64
    elif fault == "missing":
        del before["ext/experiential_transport.py"]
    elif fault == "extra":
        before["ext/foreign.py"] = "0" * 64
    else:
        before["ext/pick.py"] = "0" * 64
    after = json.loads((terminal_diagnostics_builds.glm / "native-manifest.json").read_bytes())
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("fault", [
    "parent-worker", "guard-worker", "retained", "missing-go", "extra",
    "mixed-guard",
])
def test_terminal_join_cannot_hide_invalid_expanded_target(fault, terminal_diagnostics_builds):
    before = builder.provider_terminal_diagnostics_files()
    after = json.loads((terminal_diagnostics_builds.glm / "native-manifest.json").read_bytes())
    record, _, _ = builder.provider_terminal_diagnostics_record()
    if fault == "parent-worker":
        after[record["member"]] = before[record["member"]]
    elif fault == "guard-worker":
        after[record["member"]] = record["guard_preimage_sha256"]
    elif fault == "retained":
        after["ext/model_tier.py"] = "0" * 64
    elif fault == "missing-go":
        del after[g.GO_HANDLER]
    elif fault == "extra":
        after["ext/foreign.py"] = "0" * 64
    else:
        after["ext/experiential_transport.py"] = before["ext/experiential_transport.py"]
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http", "glm"])
def test_terminal_native41_original_transaction_commits_and_recovers(
        owner_name, extension, request, terminal_provider_stage, terminal_diagnostics_builds):
    test_combined_application_commits_and_recovers_original_transaction(
        owner_name, extension, request, terminal_provider_stage, terminal_diagnostics_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("boundary", ["selection", "receipt"])
def test_terminal_native41_postcommit_recovery_does_not_select_again(
        owner_name, boundary, request, terminal_provider_stage, terminal_diagnostics_builds):
    test_combined_postcommit_interruption_does_not_select_again(
        owner_name, boundary, "glm", request, terminal_provider_stage, terminal_diagnostics_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
def test_terminal_native41_stale_current_refuses_before_any_write(
        owner_name, request, terminal_provider_stage, terminal_diagnostics_builds):
    test_combined_plan_rechecks_complete_pointer_before_any_write(
        owner_name, "glm", request, terminal_provider_stage, terminal_diagnostics_builds)


@pytest.mark.parametrize("flags", [
    ["--include-provider-plan-terminal-diagnostics"],
    ["--include-provider-plan-application", "--include-provider-plan-remote-placement",
     "--include-provider-plan-terminal-diagnostics"],
])
def test_terminal_unqualified_flags_refuse_before_output(tmp_path, flags):
    output = tmp_path / "must-not-exist"
    with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *flags]):
        with pytest.raises(SystemExit) as stopped:
            builder.main()
    assert stopped.value.code == 2 and not output.exists()


@pytest.mark.parametrize("members", ["HTTP_GENERATION_MEMBERS", "GLM_HTTP_GENERATION_MEMBERS"])
def test_terminal_transport_hashes_remain_bound_by_original_installer(
        members, terminal_diagnostics_builds):
    output = terminal_diagnostics_builds.glm
    component_path = output / "external-go-component"
    component = json.loads((component_path / "component.json").read_bytes())
    stable_ext = Path(component["stable_ext"])
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    assert installer._go_component(component_path, stable_ext, manifest)
    manifest[next(iter(sorted(getattr(builder, members))))] = "0" * 64
    saved = dict(manifest)
    with pytest.raises(ValueError):
        installer._go_component(component_path, stable_ext, manifest)
    assert manifest == saved


# Native42 adds memory/support to the exact selected terminal cohort. The
# fixtures use the original public composer; no installed runtime is read.
@pytest.fixture(scope="module")
def memory_support_provider_stage(terminal_provider_stage, tmp_path_factory):
    repository = ROOT.parents[2]
    with mock.patch.object(sys, "path", [str(repository), *sys.path]):
        from ops.native_fabric.provider_plans import compose
    stage = tmp_path_factory.mktemp("memory-support-provider") / "code"
    result = compose.compose(terminal_provider_stage.stage, stage,
                             profile_name="terminal116-protected-memory-support-status")
    files = json.loads((stage / "FILES.json").read_bytes())
    assert result["publication_performed"] is result["selection_performed"] is False
    assert files == builder.provider_memory_support_files() and len(files) == 119
    return SimpleNamespace(root=stage.parent, stage=stage, files=files)


@pytest.fixture(scope="module")
def memory_support_builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("memory-support-application-builds").resolve()
    outputs = {}
    common = ["--include-provider-plan-application",
              "--include-provider-plan-remote-placement",
              "--include-provider-plan-maintenance-guard",
              "--include-provider-plan-terminal-diagnostics",
              "--include-provider-plan-memory-support"]
    for name, flags in (
        ("base", []), ("application", ["--include-go-application"]),
        ("http", ["--include-go-application", "--include-application-http"]),
        ("glm", ["--include-go-application", "--include-application-http",
                 "--include-application-glm"]),
    ):
        output = root / name
        with mock.patch.object(sys, "argv", [
                "builder", "--output", str(output), *common, *flags,
        ]), redirect_stdout(io.StringIO()):
            builder.main()
        outputs[name] = output
    return SimpleNamespace(**outputs)


@pytest.mark.parametrize("extension,count", [
    ("base", 119), ("application", 121), ("http", 124), ("glm", 126),
])
def test_memory_support_preserves_closed_source_and_actual_dependencies(
        extension, count, memory_support_builds, terminal_diagnostics_builds,
        memory_support_provider_stage):
    output = getattr(memory_support_builds, extension)
    previous = getattr(terminal_diagnostics_builds, extension)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    prior = json.loads((previous / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    record, predecessor, _ = builder.provider_memory_support_record()
    assert len(manifest) == count
    assert set(manifest) - set(prior) == builder.PROVIDER_MEMORY_SUPPORT_ADDITIONS
    assert {name for name in manifest if manifest[name] != prior.get(name)} == set(record["members"])
    assert manifest["ext/lease_broker.py"] == (
        "991aca0c5e902b9fb8fc699524a249957ca686299a3d1448f9f31c2305b84a41")
    inherited = inventory["files"]["ext/lease_broker.py"]["composition"]["inherited"]
    assert inherited["successor_composition_sha256"] == builder.PROVIDER_MEMORY_SUPPORT_RECORD_SHA256
    assert inherited["patch_sha256"] == record["members"]["ext/lease_broker.py"]["patch_sha256"]
    assert inherited["preimage_sha256"] == record["members"]["ext/lease_broker.py"]["before"]
    core = builder._application_base(manifest)
    old_core = builder.before_glm_application_core(builder._application_base(prior))
    unwrapped = builder.before_glm_application_core(core)
    assert builder.before_provider_memory_support(unwrapped) == old_core
    assert builder.before_provider_application(core) == builder.before_provider_application(old_core)
    for relative, wanted in manifest.items():
        raw = (output / "native-code-stage" / relative).read_bytes()
        row = inventory["files"][relative]
        assert g.digest(raw) == wanted == row["sha256"]
        assert len(raw) == row["bytes"]
        if relative not in record["members"]:
            assert raw == (previous / "native-code-stage" / relative).read_bytes()
        elif relative not in {"ext/fabric_task.py", "ext/lease_broker.py"}:
            assert raw == (memory_support_provider_stage.stage / relative).read_bytes()
    if extension != "base":
        saved = dict(predecessor), dict(manifest)
        builder.validate_go_source_transition(predecessor, manifest)
        assert (predecessor, manifest) == saved
        component = json.loads((output / "external-go-component/component.json").read_bytes())
        assert component["dependencies"]["lease_broker.py"]["sha256"] == (
            "b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004")
        assert component["native_stage_dependencies"]["lease_broker.py"] == manifest["ext/lease_broker.py"]
        assert installer._go_component(
            output / "external-go-component", Path(component["stable_ext"]), manifest)


def test_memory_support_join_preserves_both_task_and_broker_parents(
        memory_support_provider_stage, terminal_diagnostics_builds, memory_support_builds):
    import ast
    record, _, payloads = builder.provider_memory_support_record()
    application = terminal_diagnostics_builds.base / "native-code-stage"
    joined = memory_support_builds.base / "native-code-stage"
    memory = memory_support_provider_stage.stage

    def functions(raw):
        nodes = {}
        for node in ast.parse(raw).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        nodes[node.name + "." + child.name] = child
        return nodes

    task = "ext/fabric_task.py"
    old_nodes = functions((application / task).read_bytes())
    new_nodes = functions((joined / task).read_bytes())
    memory_nodes = functions((memory / task).read_bytes())
    old_nodes["inspect_run"].name = "_inspect_run"
    assert ast.dump(old_nodes["inspect_run"]) == ast.dump(new_nodes["_inspect_run"])
    for name in ("inspect_run", "read_result", "main"):
        assert ast.dump(new_nodes[name]) == ast.dump(memory_nodes[name])

    broker = "ext/lease_broker.py"
    before = (ROOT / builder.GLM_CORE_SOURCE_DIRECTORY / "lease_broker_provider.py").read_bytes()
    merged = builder._quota_reset_patch(before, payloads[broker], "lease_broker.py")
    assert g.digest(merged) == record["members"][broker]["after"]
    assert merged == (ROOT / builder.GLM_CORE_SOURCE_DIRECTORY / "lease_broker_provider_memory.py").read_bytes()
    assert builder._glm_broker_forward(ROOT, merged) == (joined / broker).read_bytes()
    joined_nodes = functions((joined / broker).read_bytes())
    memory_nodes = functions((memory / broker).read_bytes())
    for name in ("_connect", "Broker.__init__", "Broker._conn", "Broker._lock",
                 "Broker._try_acquire_in_transaction"):
        assert ast.dump(joined_nodes[name]) == ast.dump(memory_nodes[name])


@pytest.mark.parametrize("fault", [
    "native41", "missing-memory", "mixed-task", "mixed-broker", "guard-worker",
    "retained", "extra",
])
def test_memory_support_rejects_partial_or_foreign_predecessor(fault, memory_support_builds):
    before = builder.provider_memory_support_files()
    terminal = builder.provider_terminal_diagnostics_files()
    if fault == "native41":
        before = terminal
    elif fault == "missing-memory":
        del before["ext/fabric_memory_view.py"]
    elif fault == "mixed-task":
        before["ext/fabric_task.py"] = terminal["ext/fabric_task.py"]
    elif fault == "mixed-broker":
        before["ext/lease_broker.py"] = terminal["ext/lease_broker.py"]
    elif fault == "guard-worker":
        before["ext/native_plan_worker.py"] = builder.PROVIDER_TERMINAL_DIAGNOSTICS_WORKER_SHA256
    elif fault == "retained":
        before["ext/model_tier.py"] = "0" * 64
    else:
        before["ext/foreign.py"] = "0" * 64
    after = json.loads((memory_support_builds.glm / "native-manifest.json").read_bytes())
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("fault", [
    "missing-memory", "missing-go", "native-task", "native-broker",
    "previous-task", "previous-broker", "retained", "extra",
])
def test_memory_support_cannot_hide_invalid_target(
        fault, memory_support_builds, terminal_diagnostics_builds):
    before = builder.provider_memory_support_files()
    after = json.loads((memory_support_builds.glm / "native-manifest.json").read_bytes())
    previous = json.loads((terminal_diagnostics_builds.glm / "native-manifest.json").read_bytes())
    if fault == "missing-memory":
        del after["ext/protected_memory_economic.py"]
    elif fault == "missing-go":
        del after[g.GO_HANDLER]
    elif fault in {"native-task", "previous-task"}:
        after["ext/fabric_task.py"] = (before if fault == "native-task" else previous)["ext/fabric_task.py"]
    elif fault in {"native-broker", "previous-broker"}:
        after["ext/lease_broker.py"] = (before if fault == "native-broker" else previous)["ext/lease_broker.py"]
    elif fault == "retained":
        after["ext/model_tier.py"] = "0" * 64
    else:
        after["ext/foreign.py"] = "0" * 64
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http", "glm"])
def test_memory_support_native42_original_transaction_commits_and_recovers(
        owner_name, extension, request, memory_support_provider_stage, memory_support_builds):
    test_combined_application_commits_and_recovers_original_transaction(
        owner_name, extension, request, memory_support_provider_stage, memory_support_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("boundary", ["selection", "receipt"])
def test_memory_support_native42_postcommit_recovery_does_not_select_again(
        owner_name, boundary, request, memory_support_provider_stage, memory_support_builds):
    test_combined_postcommit_interruption_does_not_select_again(
        owner_name, boundary, "glm", request, memory_support_provider_stage, memory_support_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
def test_memory_support_native42_stale_current_refuses_before_write(
        owner_name, request, memory_support_provider_stage, memory_support_builds):
    test_combined_plan_rechecks_complete_pointer_before_any_write(
        owner_name, "glm", request, memory_support_provider_stage, memory_support_builds)


@pytest.mark.parametrize("members", ["HTTP_GENERATION_MEMBERS", "GLM_HTTP_GENERATION_MEMBERS"])
def test_memory_support_transport_still_binds_actual_bytes(members, memory_support_builds):
    test_terminal_transport_hashes_remain_bound_by_original_installer(members, memory_support_builds)


@pytest.mark.parametrize("stale", [
    "77648f14204d0f314b6ce5770f6c0d7e130cba5c197fa14c3b61c88ca462562b",
    "5a672d318d49ae0d0be91c4669bdbca23a9e589e576aeed16531197664c8fdd0",
])
def test_memory_support_rejects_historical_staged_dependency(
        stale, memory_support_builds, tmp_path):
    output = tmp_path / "captured-source"
    shutil.copytree(memory_support_builds.glm, output)
    component = output / "external-go-component"
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    record = json.loads((component / "component.json").read_bytes())
    assert installer._go_component(component, Path(record["stable_ext"]), manifest)
    record["native_stage_dependencies"]["lease_broker.py"] = stale
    (component / "component.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        installer._go_component(component, Path(record["stable_ext"]), manifest)


@pytest.mark.parametrize("member", ["ext/fabric_task.py", "ext/support_policy_status.py"])
def test_memory_support_changed_or_symlinked_source_refuses(member, tmp_path):
    record, _, _ = builder.provider_memory_support_record()
    row = record["members"][member]
    source = ROOT / row.get("patch_source", row.get("source"))
    replacement = tmp_path / "changed"
    replacement.write_bytes(source.read_bytes() + b"\n# changed\n")
    original = builder._provider_source

    def route(path, expected):
        return original(replacement if Path(path).resolve() == source.resolve() else path, expected)

    with mock.patch.object(builder, "_provider_source", side_effect=route):
        with pytest.raises(ValueError, match="source commitment differs"):
            builder.provider_memory_support_record()
    replacement.unlink()
    replacement.symlink_to(source)
    with mock.patch.object(builder, "_provider_source", side_effect=route):
        with pytest.raises(ValueError, match="regular file"):
            builder.provider_memory_support_record()


@pytest.mark.parametrize("flags", [
    ["--include-provider-plan-memory-support"],
    ["--include-provider-plan-application", "--include-provider-plan-remote-placement",
     "--include-provider-plan-maintenance-guard", "--include-provider-plan-memory-support"],
])
def test_memory_support_unqualified_flags_refuse_before_output(tmp_path, flags):
    output = tmp_path / "must-not-exist"
    with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *flags]):
        with pytest.raises(SystemExit) as stopped:
            builder.main()
    assert stopped.value.code == 2 and not output.exists()


def test_memory_support_staged_application_and_memory_journeys(
        memory_support_builds, tmp_path):
    test_combined_source_retains_original_application_v3_journeys(
        memory_support_builds, "glm", tmp_path, memory_support=True)
    # Reuse the original memory owner tests in a fresh interpreter. Their imports
    # must resolve to this exact staged closure, never an earlier candidate.
    stage = memory_support_builds.glm / "native-code-stage"
    script = """import json, sys
from pathlib import Path
from pytest import MonkeyPatch
import test_current116_memory118_composition as proof
joined, scratch = map(Path, sys.argv[1:])
with MonkeyPatch.context() as mp:
    proof.test_real_joined_broker_existing_only_reopens_without_creation_or_schema_change(
        joined, scratch, mp)
with MonkeyPatch.context() as mp:
    proof.test_actual_current_task_ordinary_inspection_still_uses_owned_reader(joined, mp)
for channel in ("inspect", "result", "cli"):
    with MonkeyPatch.context() as mp:
        proof.test_actual_current_task_privacy_guard_runs_before_original_channel(
            joined, mp, channel)
import fabric_memory_view
assert Path(fabric_memory_view.__file__).resolve() == (joined / "ext/fabric_memory_view.py").resolve()
print(json.dumps({"memory_cases": 5, "passed": 5}))
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(ROOT.parents[2] / "tests"), str(ROOT.parents[2])]),
        PYTHONDONTWRITEBYTECODE="1")
    scratch = tmp_path / "existing-memory-store"
    scratch.mkdir()
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(stage), str(scratch)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"memory_cases": 5, "passed": 5}


@pytest.fixture
def copied_memory_guard(tmp_path):
    import runpy
    # This is the actual copied Control source location. No source record or
    # fallback checkout is supplied to this isolated builder.
    target = tmp_path / "control/ops/native_fabric/quota_continuity/rollout/build_review_stage.py"
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / "rollout/build_review_stage.py").read_bytes())
    return runpy.run_path(str(target), run_name="isolated_control_builder")


def test_memory_support_copied_legacy_guard_needs_no_new_record(copied_memory_guard, builds):
    manifest = json.loads((builds.default / "native-manifest.json").read_bytes())
    original = dict(manifest)
    assert copied_memory_guard["before_provider_memory_support"](manifest) == manifest
    copied_memory_guard["validate_go_base_manifest"](
        manifest, {name: manifest["ext/" + name]
                   for name in copied_memory_guard["GO_APPLICATION_DEPENDENCIES"]})
    assert manifest == original


@pytest.mark.parametrize("member", sorted(builder.PROVIDER_MEMORY_SUPPORT_MARKERS))
def test_memory_support_copied_changed_member_requires_source_record(copied_memory_guard, member):
    # Even when every addition path is missing, each changed-member digest
    # must enter authenticated validation instead of taking the legacy path.
    manifest = {member: copied_memory_guard["PROVIDER_MEMORY_SUPPORT_MARKERS"][member]}
    with pytest.raises(ValueError, match="regular file"):
        copied_memory_guard["before_provider_memory_support"](manifest)


@pytest.mark.parametrize("member", sorted(builder.PROVIDER_MEMORY_SUPPORT_ADDITIONS))
def test_memory_support_copied_addition_requires_source_record(copied_memory_guard, member):
    with pytest.raises(ValueError, match="regular file"):
        copied_memory_guard["before_provider_memory_support"]({member: "0" * 64})


@pytest.mark.parametrize("cohort", ["memory_support", "fleet_launch_repair"])
def test_memory_support_installed_control_reads_exact_retained_transition(
        retained_go_owner, cohort, tmp_path,
        memory_support_provider_stage, memory_support_builds,
        fleet_launch_repair_provider_stage, fleet_launch_repair_builds):
    """Read the marked 119-to-126 plan using only the sealed installed closure."""
    import ast
    import hashlib
    import importlib.util
    import stat
    case = retained_go_owner
    # Declare both module fixtures above so public source composition completes
    # before the function-scoped installer fixture activates its process guard.
    provider_stage, builds = {
        "memory_support": (memory_support_provider_stage, memory_support_builds),
        "fleet_launch_repair": (fleet_launch_repair_provider_stage, fleet_launch_repair_builds),
    }[cohort]
    api, plan, forward = prepare_combined(
        case, "retained_go_owner", provider_stage, builds.glm)

    def owner_bytes():
        result = {}
        for path in sorted(case.root.rglob("*")):
            info = path.lstat()
            value = (os.readlink(path) if path.is_symlink() else
                     hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else
                     "directory")
            result[str(path.relative_to(case.root))] = (stat.S_IMODE(info.st_mode), value)
        return result

    before = owner_bytes()
    pointer = g.current(case.store)
    assert len(g.verify(case.store, pointer["generation"])[1]["files"]) == 119
    assert len(g.verify(case.store, plan["target_generation"])[1]["files"]) == 126
    # Close the incumbent fixture's audited mutation phase normally. Registered
    # cleanup keeps its real retained history alive for the isolated read phase.
    case.tearDown()
    source = ROOT.parents[2] / "integrations/studio_direct_mcp"
    spec = importlib.util.spec_from_file_location(
        "memory_installed_control_bundle", source / "control_bundle.py")
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    repository = tmp_path / "captured-release"
    copied_source = repository / "integrations/studio_direct_mcp"
    for name, original in bundle._source_files(source).items():
        destination = (copied_source / name if len(Path(name).parts) == 1
                       else repository / name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original.read_bytes())
        destination.chmod(0o600)
    repository.chmod(0o700)
    for directory in repository.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    # These are the existing retained-history fixture pins, captured before
    # sealing the disposable source. No installed byte or reader is mocked.
    native = repository / "ops/native_fabric/quota_continuity/rollout/native_install.py"
    raw = native.read_text()
    lines = raw.splitlines(keepends=True)
    pins = {"RETAINED_STATUS_PROOF_SHA256": case.pins,
            "RETAINED_STATUS_PLAN_DIGEST": case.successor_plan["digest"]}
    nodes = [node for node in ast.parse(raw).body if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
             and node.targets[0].id in pins]
    assert {node.targets[0].id for node in nodes} == set(pins)
    for node in sorted(nodes, key=lambda item: item.lineno, reverse=True):
        name = node.targets[0].id
        lines[node.lineno - 1:node.end_lineno] = [name + " = " + repr(pins[name]) + "\n"]
    native.write_text("".join(lines))

    home = tmp_path / "installed-home"
    home.mkdir(mode=0o700)
    control = home / ".local/share/studio-direct-mcp/control"
    control.mkdir(parents=True, mode=0o700)
    (home / ".local/share/studio-direct-mcp/private").mkdir(mode=0o700)
    launcher = home / ".local/bin/studio-direct"
    launcher.parent.mkdir(parents=True, mode=0o700)
    launcher.write_text("#!/bin/sh\nexit 0\n")
    launcher.chmod(0o700)
    for directory in home.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    with mock.patch.object(bundle.Path, "home", return_value=home):
        installed = bundle.install(source=copied_source, control_root=control,
                                   launcher=launcher)
        verified = bundle.verify(control_root=control, launcher=launcher)
        assert installed["state"] == "CONTROL_BUNDLE_INSTALLED"
        assert verified == {**installed, "state": "CONTROL_BUNDLE_VERIFIED"}
    assert len(installed["files"]) == 74
    assert installed["source"] == str(copied_source)
    shutil.rmtree(repository)
    assert not copied_source.exists()
    code = r"""
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("installed_memory_forward_proof",root/"private_service.py")
svc=importlib.util.module_from_spec(spec);sys.modules[spec.name]=svc
spec.loader.exec_module(svc)
assert svc._INSTALLED_CONTROL_CONTEXT["root"]==root
calls=[]
actual=svc.subprocess.run
def record(argv,*args,**kwargs):
    result=actual(argv,*args,**kwargs)
    calls.append(argv)
    if result.returncode:
        sys.stderr.write(result.stderr.decode(errors="replace"))
    return result
svc.subprocess.run=record
args=SimpleNamespace(forward_go_bundle=Path(sys.argv[2]),operation="preview")
with svc._pin_forward_native_context(args) as observed:
    assert observed["phase"]=="PREVIOUS"
assert len(calls)==2
for argv in calls:
    assert argv[1:4]==["-I","-S","-B"]
    assert Path(argv[6])==root/"ops/native_fabric/quota_continuity/rollout"
print(json.dumps({"observed":observed,"real_reader_calls":len(calls)},sort_keys=True))
"""

    def read_installed():
        return subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", code, str(control), str(forward)],
            cwd=home, env={"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "C"},
            capture_output=True, text=True, timeout=90)

    result = read_installed()
    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["real_reader_calls"] == 2
    prior = case.successor_plan
    entry = prior["entries"]["pool"]
    expected = {
        "original_successor": {
            "successor_bundle": str(case.successor), "successor_digest": prior["digest"],
            "target_generation": prior["target_generation"],
            "expected_selection": prior["expected_selection"],
            "pool_target": entry["target"], "pool_previous": entry["previous"],
            "pool_bridge": entry["bridge"]},
        "go_digest": plan["digest"], "go_schema": plan["schema"],
        "go_generation": plan["target_generation"],
        "go_expected_selection": plan["expected_selection"],
        "go_bootstrap_digest": plan["bootstrap_digest"],
        "go_prior_successor_digest": plan["prior_successor_digest"],
        "go_component_sha256": plan["component_sha256"],
        "go_manifest_sha256": plan["manifest_sha256"],
        "pool_target": plan["entries"]["pool"]["target"],
        "pool_previous": plan["entries"]["pool"]["previous"],
        "pool_bridge": plan["entries"]["pool"]["bridge"],
        "store": plan["store"], "phase": "PREVIOUS",
    }
    assert value["observed"] == expected
    assert owner_bytes() == before and g.current(case.store) == pointer
    api.history(case)
    fault_members = [
        "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/composition.json"]
    if cohort == "fleet_launch_repair":
        fault_members.extend(bundle.FLEET_REVIEW_SOURCE_FILES)
    for member in fault_members:
        captured = control / member
        original = captured.read_bytes()
        for fault in ("missing", "changed"):
            try:
                if fault == "missing":
                    captured.unlink()
                else:
                    captured.write_bytes(original + b"\n")
                refused = read_installed()
                assert refused.returncode != 0
                assert "CONTROL_BUNDLE_CLOSURE_REFUSED" in refused.stderr
                assert owner_bytes() == before and g.current(case.store) == pointer
                api.history(case)
            finally:
                captured.write_bytes(original)
                captured.chmod(0o600)


# Native43 preserves the released fleet repair inside the existing APPLICATION
# composition and original retained-Go transaction. All fixtures are offline.
@pytest.fixture(scope="module")
def fleet_launch_repair_provider_stage(memory_support_provider_stage, tmp_path_factory):
    repository = ROOT.parents[2]
    with mock.patch.object(sys, "path", [str(repository), *sys.path]):
        from ops.native_fabric.provider_plans import compose
    root = tmp_path_factory.mktemp("fleet-launch-repair-provider")
    base, stage = root / "selected119", root / "code"
    shutil.copytree(memory_support_provider_stage.stage, base)
    profile = json.loads((compose.HERE / "fleet_launch_repair/profile.json").read_bytes())
    (base / "RELEASE.json").write_text(json.dumps({
        "digest": profile["base_selection"]["generation"],
        "files": memory_support_provider_stage.files,
        "fixture_premise": "SOURCE_ONLY, not an installed receipt"}))
    result = compose.compose(base, stage, profile_name="terminal119-fleet-launch-repair")
    files = json.loads((stage / "FILES.json").read_bytes())
    assert result["publication_performed"] is result["selection_performed"] is False
    assert files == builder.provider_fleet_launch_repair_files() and len(files) == 119
    return SimpleNamespace(root=root, stage=stage, files=files)


@pytest.fixture(scope="module")
def fleet_launch_repair_builds(tmp_path_factory):
    root = tmp_path_factory.mktemp("fleet-launch-repair-application-builds").resolve()
    outputs = {}
    common = ["--include-provider-plan-application",
              "--include-provider-plan-remote-placement",
              "--include-provider-plan-maintenance-guard",
              "--include-provider-plan-terminal-diagnostics",
              "--include-provider-plan-memory-support",
              "--include-provider-plan-fleet-launch-repair"]
    for name, flags in (
        ("base", []), ("application", ["--include-go-application"]),
        ("http", ["--include-go-application", "--include-application-http"]),
        ("glm", ["--include-go-application", "--include-application-http",
                 "--include-application-glm"]),
    ):
        output = root / name
        with mock.patch.object(sys, "argv", [
                "builder", "--output", str(output), *common, *flags,
        ]), redirect_stdout(io.StringIO()):
            builder.main()
        outputs[name] = output
    return SimpleNamespace(**outputs)


@pytest.mark.parametrize("extension,count", [
    ("base", 119), ("application", 121), ("http", 124), ("glm", 126),
])
def test_fleet_launch_repair_preserves_whole_source_and_dependencies(
        extension, count, fleet_launch_repair_builds, memory_support_builds,
        fleet_launch_repair_provider_stage):
    output = getattr(fleet_launch_repair_builds, extension)
    previous = getattr(memory_support_builds, extension)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    prior = json.loads((previous / "native-manifest.json").read_bytes())
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    record, predecessor, _ = builder.provider_fleet_launch_repair_record()
    assert predecessor == fleet_launch_repair_provider_stage.files
    assert len(manifest) == count and set(manifest) == set(prior)
    assert {name for name in manifest if manifest[name] != prior[name]} == set(record["members"])
    assert manifest["ext/lease_broker.py"] == (
        "cd1537c409fa9f6c8d99a453747e355998980e03352c1ffb4c66fc447fb79d74")
    unwrapped = builder.before_glm_application_core(builder._application_base(manifest))
    old_core = builder.before_glm_application_core(builder._application_base(prior))
    assert builder.before_provider_fleet_launch_repair(unwrapped) == old_core
    assert builder.before_provider_application(unwrapped) == builder.before_provider_application(old_core)
    for relative, wanted in manifest.items():
        raw = (output / "native-code-stage" / relative).read_bytes()
        row = inventory["files"][relative]
        assert g.digest(raw) == wanted == row["sha256"] and len(raw) == row["bytes"]
        if relative not in record["members"]:
            assert raw == (previous / "native-code-stage" / relative).read_bytes()
    broker = inventory["files"]["ext/lease_broker.py"]["composition"]["inherited"]
    assert broker["successor_composition_sha256"] == builder.PROVIDER_FLEET_LAUNCH_REPAIR_RECORD_SHA256
    assert broker["preimage_sha256"] == record["members"]["ext/lease_broker.py"]["before"]
    assert broker["inherited"]["composition"]["successor_composition_sha256"] == (
        builder.PROVIDER_MEMORY_SUPPORT_RECORD_SHA256)
    if extension != "base":
        saved = dict(predecessor), dict(manifest)
        builder.validate_go_source_transition(predecessor, manifest)
        assert (predecessor, manifest) == saved
        component = json.loads((output / "external-go-component/component.json").read_bytes())
        assert component["native_stage_dependencies"]["lease_broker.py"] == manifest["ext/lease_broker.py"]
        assert installer._go_component(
            output / "external-go-component", Path(component["stable_ext"]), manifest)


@pytest.mark.parametrize("member", sorted(builder.PROVIDER_FLEET_LAUNCH_REPAIR_MARKERS))
def test_fleet_launch_repair_refuses_each_mixed_predecessor(member, fleet_launch_repair_builds):
    before = builder.provider_fleet_launch_repair_files()
    before[member] = builder.provider_memory_support_files()[member]
    after = json.loads((fleet_launch_repair_builds.glm / "native-manifest.json").read_bytes())
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("fault", ["missing", "extra", "unrelated"])
def test_fleet_launch_repair_binds_complete_predecessor(fault, fleet_launch_repair_builds):
    before = builder.provider_fleet_launch_repair_files()
    if fault == "missing":
        del before["ext/model_tier.py"]
    elif fault == "extra":
        before["ext/foreign.py"] = "0" * 64
    else:
        before["ext/model_tier.py"] = "0" * 64
    after = json.loads((fleet_launch_repair_builds.glm / "native-manifest.json").read_bytes())
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)


@pytest.mark.parametrize("member", sorted(builder.PROVIDER_FLEET_LAUNCH_REPAIR_MARKERS))
@pytest.mark.parametrize("source", ["native", "previous"])
def test_fleet_launch_repair_refuses_each_mixed_target(
        member, source, fleet_launch_repair_builds, memory_support_builds):
    before = builder.provider_fleet_launch_repair_files()
    after = json.loads((fleet_launch_repair_builds.glm / "native-manifest.json").read_bytes())
    previous = json.loads((memory_support_builds.glm / "native-manifest.json").read_bytes())
    after[member] = (before if source == "native" else previous)[member]
    # remote_sub.sh intentionally equals the exact protected native43 source.
    if after[member] == json.loads(
            (fleet_launch_repair_builds.glm / "native-manifest.json").read_bytes())[member]:
        assert member == "ext/remote_sub.sh" and source == "native"
        return
    saved = dict(before), dict(after)
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)
    assert (before, after) == saved


@pytest.mark.parametrize("fault", ["old-native42-target", "missing-go", "extra", "unrelated"])
def test_fleet_launch_repair_cannot_hide_invalid_target(
        fault, fleet_launch_repair_builds, memory_support_builds):
    before = builder.provider_fleet_launch_repair_files()
    after = json.loads((fleet_launch_repair_builds.glm / "native-manifest.json").read_bytes())
    if fault == "old-native42-target":
        after = json.loads((memory_support_builds.glm / "native-manifest.json").read_bytes())
    elif fault == "missing-go":
        del after[g.GO_HANDLER]
    elif fault == "extra":
        after["ext/foreign.py"] = "0" * 64
    else:
        after["ext/model_tier.py"] = "0" * 64
    with pytest.raises(ValueError):
        builder.validate_go_source_transition(before, after)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("extension", ["application", "http", "glm"])
def test_fleet_launch_repair_native43_original_transaction_commits_and_recovers(
        owner_name, extension, request, fleet_launch_repair_provider_stage,
        fleet_launch_repair_builds):
    test_combined_application_commits_and_recovers_original_transaction(
        owner_name, extension, request, fleet_launch_repair_provider_stage, fleet_launch_repair_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("boundary", ["selection", "receipt"])
def test_fleet_launch_repair_native43_postcommit_recovery_does_not_select_again(
        owner_name, boundary, request, fleet_launch_repair_provider_stage, fleet_launch_repair_builds):
    test_combined_postcommit_interruption_does_not_select_again(
        owner_name, boundary, "glm", request, fleet_launch_repair_provider_stage, fleet_launch_repair_builds)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
def test_fleet_launch_repair_native43_stale_current_refuses_before_write(
        owner_name, request, fleet_launch_repair_provider_stage, fleet_launch_repair_builds):
    test_combined_plan_rechecks_complete_pointer_before_any_write(
        owner_name, "glm", request, fleet_launch_repair_provider_stage, fleet_launch_repair_builds)


def test_fleet_launch_repair_staged_application_and_memory_journeys(fleet_launch_repair_builds, tmp_path):
    test_memory_support_staged_application_and_memory_journeys(fleet_launch_repair_builds, tmp_path)


def test_fleet_launch_repair_preserves_application_publisher_and_inspector(
        fleet_launch_repair_builds, memory_support_builds):
    import ast
    def function(stage, member, name):
        tree = ast.parse((stage / "native-code-stage" / member).read_bytes())
        return ast.dump(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name))
    for member, name in (("ext/support_bundle.py", "ensure_policy"), ("ext/fabric_task.py", "_inspect_run")):
        assert function(fleet_launch_repair_builds.base, member, name) == function(
            memory_support_builds.base, member, name)


def test_fleet_launch_repair_staged_original_runtime_behaviors(fleet_launch_repair_builds, tmp_path):
    script = """import json, sys
from pathlib import Path
import test_fleet_launch_repair_composition as proof
stage, scratch = map(Path, sys.argv[1:])
proof.test_support_status_reader_pins_repaired_support_bundle(stage)
proof.test_retained_settlements_are_metadata_and_everything_else_blocks(stage, scratch)
proof.test_status_snapshot_serializes_yaml_timestamps_and_refusal_names_detail(stage, scratch)
print(json.dumps({"fleet_cases": 3, "passed": 3}))
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(ROOT.parents[2] / "tests"), str(ROOT.parents[2])]), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-B", "-c", script,
        str(fleet_launch_repair_builds.glm / "native-code-stage"), str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"fleet_cases": 3, "passed": 3}


@pytest.mark.parametrize("member", sorted(builder.PROVIDER_FLEET_LAUNCH_REPAIR_MARKERS))
def test_fleet_launch_repair_copied_marker_requires_source_record(copied_memory_guard, member):
    manifest = {member: copied_memory_guard["PROVIDER_FLEET_LAUNCH_REPAIR_MARKERS"][member]}
    with pytest.raises(ValueError, match="regular file"):
        copied_memory_guard["before_provider_fleet_launch_repair"](manifest)


def test_fleet_launch_repair_copied_legacy_guard_needs_no_new_record(copied_memory_guard):
    manifest = {"ext/legacy.py": "0" * 64}
    assert copied_memory_guard["before_provider_fleet_launch_repair"](manifest) == manifest


@pytest.mark.parametrize("flags", [
    ["--include-provider-plan-fleet-launch-repair"],
    ["--include-provider-plan-application", "--include-provider-plan-remote-placement",
     "--include-provider-plan-maintenance-guard", "--include-provider-plan-terminal-diagnostics",
     "--include-provider-plan-fleet-launch-repair"],
])
def test_fleet_launch_repair_unqualified_flags_refuse_before_output(tmp_path, flags):
    output = tmp_path / "must-not-exist"
    with mock.patch.object(sys, "argv", ["builder", "--output", str(output), *flags]):
        with pytest.raises(SystemExit) as stopped:
            builder.main()
    assert stopped.value.code == 2 and not output.exists()
