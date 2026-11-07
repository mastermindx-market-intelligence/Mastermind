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
from types import SimpleNamespace
from unittest import mock
import zlib

import pytest

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
    for name, flags in (("base", []), ("application", ["--include-go-application"]),
                        ("http", ["--include-go-application", "--include-application-http"])):
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


@pytest.mark.parametrize("extension,count", [("application", 118), ("http", 121)])
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
    assert builder.before_provider_application(base) == original
    assert manifest == unchanged
    broker = "lease_broker.py"
    assert record["dependencies"][broker]["sha256"] == original["ext/" + broker]
    assert record["native_stage_dependencies"][broker] == manifest["ext/" + broker]
    assert record["dependencies"][broker]["sha256"] != record["native_stage_dependencies"][broker]
    assert installer._go_component(output / "external-go-component", Path(record["stable_ext"]), manifest)
    for key, digest in manifest.items():
        raw = (output / "native-code-stage" / key).read_bytes()
        assert g.digest(raw) == digest == inventory["files"][key]["sha256"]
        assert len(raw) == inventory["files"][key]["bytes"]
    before = dict(base)
    with pytest.raises(ValueError, match="captured application dependency"):
        builder.validate_go_base_manifest(base,
            {name: row["sha256"] for name, row in record["dependencies"].items()})
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
@pytest.mark.parametrize("extension", ["application", "http"])
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
@pytest.mark.parametrize("combined", [False, True])
def test_invalid_provider_predecessor_cannot_fall_through(
        owner_name, fault, combined, request, provider_stage, combined_builds, builds):
    case = request.getfixturevalue(owner_name)
    selected = select_provider(case, provider_stage, fault=fault)
    source = combined_builds.application if combined else builds.application
    target, component = application_target(case, source)
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
def test_combined_target_requires_qualified_provider_predecessor(owner_name, request, combined_builds):
    case = request.getfixturevalue(owner_name)
    selected = g.current(case.store)
    target, component = application_target(case, combined_builds.application)
    refuse_prepare(case, owner_name, target, component, selected)


@pytest.mark.parametrize("extension", ["application", "http"])
def test_rewound_staged_dependency_is_not_an_installer_component(combined_builds, extension, tmp_path):
    output = tmp_path / "source"
    shutil.copytree(getattr(combined_builds, extension), output)
    path = output / "external-go-component/component.json"
    record = json.loads(path.read_bytes())
    record["native_stage_dependencies"]["lease_broker.py"] = record["dependencies"]["lease_broker.py"]["sha256"]
    path.write_text(json.dumps(record))
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    with pytest.raises(ValueError, match="exact reviewed source"):
        installer._go_component(output / "external-go-component", Path(record["stable_ext"]), manifest)


@pytest.mark.parametrize("owner_name", ["go_owner", "retained_go_owner"])
@pytest.mark.parametrize("boundary", ["selection", "receipt"])
def test_combined_postcommit_interruption_does_not_select_again(
        owner_name, boundary, request, provider_stage, combined_builds):
    case = request.getfixturevalue(owner_name)
    api, plan, bundle = prepare_combined(case, owner_name, provider_stage, combined_builds.http)
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
def test_combined_plan_rechecks_complete_pointer_before_any_write(
        owner_name, request, provider_stage, combined_builds):
    case = request.getfixturevalue(owner_name)
    api, plan, bundle = prepare_combined(case, owner_name, provider_stage, combined_builds.application)
    before = g.current(case.store)
    later = g.select(case.store, before["generation"], before["generation"])
    assert later["sequence"] == before["sequence"] + 1
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("stale plan wrote")):
        with pytest.raises(ValueError, match="compare-and-swap"):
            api.apply(bundle)
    assert g.current(case.store) == later
    api.history(case)


def test_combined_source_retains_original_application_v3_journeys(combined_builds, tmp_path):
    # Reuse the original owner tests in their asserted layout. A fresh process
    # ensures no previously imported candidate can impersonate the staged bytes.
    fixture = tmp_path / "ops/native_fabric/quota_continuity"
    tests = fixture / "tests"
    tests.mkdir(parents=True)
    (fixture / "source").mkdir()
    stage = combined_builds.application / "native-code-stage"
    manifest = json.loads((combined_builds.application / "native-manifest.json").read_bytes())
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


def test_unqualified_provider_quota_flag_combination_refuses_before_output(tmp_path, capsys):
    output = tmp_path / "unqualified-mixed-source"
    argv = ["builder", "--output", str(output),
            "--include-provider-plan-application", "--include-quota-reset-recovery",
            "--include-go-application", "--include-application-http"]
    with mock.patch.object(sys, "argv", argv), pytest.raises(SystemExit) as refused:
        builder.main()
    assert refused.value.code == 2
    assert "separately qualified combined cohort" in capsys.readouterr().err
    assert not output.exists()
