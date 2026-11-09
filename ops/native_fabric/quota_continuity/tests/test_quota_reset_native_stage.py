"""Complete H2 successor proof through the incumbent builder and Go installer.

Provider reads, quota exhaustion and claims use disposable fixture state. This
suite never installs/selects a production generation or calls a live provider.
"""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = ROOT / "rollout"
sys.path.insert(0, str(ROLLOUT))
import build_review_stage as builder
import native_install as installer

spec = importlib.util.spec_from_file_location(
    "h6_h2_component_journeys", ROOT.parents[2] / "tests/test_native_fabric_glm_reset_recovery.py")
component = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = component
spec.loader.exec_module(component)


def build(output, *flags):
    with mock.patch.object(sys, "argv", [
            "builder", "--output", str(output), "--include-quota-reset-recovery", *flags
    ]), redirect_stdout(io.StringIO()):
        builder.main()
    return output


def manifest(output):
    return json.loads((output / "native-manifest.json").read_bytes())


def base_manifest(output):
    return {key: value for key, value in manifest(output).items()
            if key not in {"ext/native_go_entry.py", "ext/go_application_handler.py"}
            | builder.HTTP_GENERATION_MEMBERS}


@pytest.fixture(scope="module")
def stages(tmp_path_factory):
    root = tmp_path_factory.mktemp("h2-complete-native").resolve()
    return SimpleNamespace(
        base=build(root / "base"),
        application=build(root / "application", "--include-go-application"),
        http=build(root / "http", "--include-go-application", "--include-application-http"))


@pytest.mark.parametrize("kind,count", [("base", 107), ("application", 109), ("http", 112)])
def test_complete_emitted_generation_preserves_exact_parent_and_source_provenance(stages, kind, count):
    output = getattr(stages, kind)
    actual = manifest(output)
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    parent = json.loads((ROLLOUT / "native-manifest.json").read_bytes())
    assert len(actual) == count
    before = base_manifest(output)
    original = dict(before)
    assert builder.before_quota_reset_recovery(before) == parent
    assert before == original
    assert {name for name in parent if before[name] != parent[name]} == {
        "ext/" + name for name in builder.QUOTA_RESET_DIGESTS}
    for relative, digest in actual.items():
        raw = (output / "native-code-stage" / relative).read_bytes()
        assert builder.sha(raw) == digest == inventory["files"][relative]["sha256"]
        assert len(raw) == inventory["files"][relative]["bytes"]
    expected_preimages = {
        **builder.QUOTA_RESET_PREIMAGES, **builder.QUOTA_RESET_COMPOSED_PREIMAGES}
    for name in builder.QUOTA_RESET_PATCHES:
        row = inventory["files"]["ext/" + name]
        assert row["composition"]["preimage_sha256"] == expected_preimages[name]
        assert row["composition"]["patch_sha256"] == builder.QUOTA_RESET_PATCHES[name]
        assert row["source"] == "candidate/" + name
    dependencies = json.loads((output / "external-go-component/component.json").read_bytes())
    assert dependencies["dependencies"]["lease_broker.py"]["sha256"] == builder.QUOTA_RESET_COMPOSED_DIGESTS["lease_broker.py"]
    assert dependencies["native_stage_dependencies"] == {
        name: actual["ext/" + name] for name in builder.GO_APPLICATION_DEPENDENCIES}


@pytest.mark.parametrize("kind", ["application", "http"])
def test_original_installer_validates_actual_composed_broker_and_complete_artifact(stages, kind):
    output = getattr(stages, kind)
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    receipt = installer._go_component(
        output / "external-go-component", Path(inventory["stable_ext"]), manifest(output))
    assert receipt[1] == builder.sha((output / "native-manifest.json").read_bytes())


@pytest.mark.parametrize("member", sorted(builder.QUOTA_RESET_DIGESTS))
@pytest.mark.parametrize("replacement", ["preimage", "foreign"])
def test_partial_or_foreign_cohort_refuses_without_mutating_manifest(stages, member, replacement):
    actual = base_manifest(stages.base)
    actual["ext/" + member] = (builder.QUOTA_RESET_PREIMAGES[member]
                              if replacement == "preimage" else "0" * 64)
    before = dict(actual)
    with pytest.raises(ValueError, match="quota reset cohort"):
        builder.before_quota_reset_recovery(actual)
    assert actual == before


def test_complete_cohort_cannot_relabel_a_different_parent(stages):
    actual = base_manifest(stages.base)
    actual["ext/original_delivery_collector.py"] = builder.GO_BASE_ORIGINAL_COLLECTOR_SHA256
    with pytest.raises(ValueError, match="quota reset parent closure"):
        builder.before_quota_reset_recovery(actual)



def _historical_quota_reset_parent():
    previous = json.loads((ROLLOUT / "native-manifest.json").read_bytes())
    previous = builder.before_host_pull_integrity(previous)
    previous["ext/remote_sub_exec.py"] = \
        "bb0369140835dacf1bd08aef6fe96878c5088a8109580fd006436e53d05801ea"
    assert builder.sha((json.dumps(previous, sort_keys=True, indent=2) + "\n").encode()) == \
        "c7f5d2e62980e4cb38580496ef82125673015881f70d4fc4d6763137eed30459"
    return previous


def test_historical_complete_h2_parent_retains_its_exact_inverse():
    previous = _historical_quota_reset_parent()
    historical = dict(previous)
    historical.update({"ext/" + name: digest for name, digest in builder.QUOTA_RESET_DIGESTS.items()})
    before = dict(historical)
    assert builder.before_quota_reset_recovery(historical) == previous
    assert historical == before


def test_current_builder_refuses_historical_parent_before_new_emission(tmp_path):
    previous = _historical_quota_reset_parent()
    output = tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="requires exact complete APPLICATION parent"):
        builder.compose_quota_reset_stage(ROOT, output, previous, {})
    assert not output.exists()


def test_stale_go_dependency_receipt_is_not_accepted_through_historical_inverse(stages):
    actual = base_manifest(stages.base)
    current = builder.go_application_dependencies(ROOT, staged_manifest=actual)
    hashes = {name: row["sha256"] for name, row in current.items()}
    builder.validate_go_base_manifest(actual, hashes)
    hashes["lease_broker.py"] = builder.QUOTA_RESET_PREIMAGES["lease_broker.py"]
    with pytest.raises(ValueError, match="captured application dependency"):
        builder.validate_go_base_manifest(actual, hashes)


def copy_sources(tmp_path):
    root = tmp_path / "quota_continuity"
    overlay = root.parent / "grok47/quota_billing"
    (root / "candidate").mkdir(parents=True)
    overlay.mkdir(parents=True)
    for name in builder.QUOTA_RESET_PREIMAGES:
        shutil.copyfile(ROOT / "candidate" / name, root / "candidate" / name)
        suffix = ".patch" if name in builder.QUOTA_RESET_PATCHES else ""
        shutil.copyfile(ROOT.parent / "grok47/quota_billing" / (name + suffix), overlay / (name + suffix))
    # Copied candidates are the reviewed maintenance-composed parent.
    # Establish that valid fixture before any intentional source mutation.
    builder.quota_reset_sources(root, composed_parent=True)
    return root, overlay


@pytest.mark.parametrize("surface", ["preimage", "patch", "overlay"])
def test_changed_reviewed_source_refuses_before_any_stage_write(tmp_path, surface):
    root, overlay = copy_sources(tmp_path)
    target = {"preimage": root / "candidate/lease_broker.py",
              "patch": overlay / "pick.py.patch",
              "overlay": overlay / "quota_remote.py"}[surface]
    target.write_bytes(target.read_bytes() + b"\n# unqualified drift\n")
    with pytest.raises(ValueError, match="quota reset source digest"):
        builder.quota_reset_sources(root, composed_parent=True)


@pytest.mark.parametrize("member", sorted(builder.QUOTA_RESET_DIGESTS))
def test_exact_bytes_through_symlink_are_not_a_qualified_source(tmp_path, member):
    root, _ = copy_sources(tmp_path)
    source = root / "candidate" / member
    retained = source.with_suffix(".retained")
    source.rename(retained)
    source.symlink_to(retained)
    with pytest.raises(ValueError, match="regular file"):
        builder.quota_reset_sources(root, composed_parent=True)


@pytest.mark.parametrize("part", ["component", "stage"])
def test_installer_refuses_a_changed_bundle_or_staged_postimage(stages, tmp_path, part):
    output = tmp_path / "changed"
    shutil.copytree(stages.http, output)
    inventory = json.loads((output / "native-source-inventory.json").read_bytes())
    if part == "component":
        path = output / "external-go-component/component.json"
        record = json.loads(path.read_bytes())
        record["dependencies"]["lease_broker.py"]["sha256"] = builder.QUOTA_RESET_PREIMAGES["lease_broker.py"]
        path.write_text(json.dumps(record))
    else:
        path = output / "native-code-stage/ext/pick.py"
        path.write_bytes(path.read_bytes() + b"\n# changed staged source\n")
    with pytest.raises(ValueError, match="exact reviewed source|captured Go stage changed"):
        installer._go_component(output / "external-go-component",
                                Path(inventory["stable_ext"]), manifest(output))


class TestEmittedGlmResetBrokerJourney(component.GlmResetBrokerJourney):
    """Run all sixteen existing real claim/settlement journeys on emitted code."""

    @classmethod
    def setUpClass(cls):
        cls.stage_temp = tempfile.TemporaryDirectory(prefix="h6-emitted-h2-")
        cls.addClassCleanup(cls.stage_temp.cleanup)
        cls.stage = build(Path(cls.stage_temp.name).resolve() / "http",
                          "--include-go-application", "--include-application-http")
        cls.stage_manifest = manifest(cls.stage)

    def runtime_sources(self):
        sources = {name: self.stage / "native-code-stage/ext" / name
                   for name in builder.QUOTA_RESET_DIGESTS}
        for name, path in sources.items():
            self.assertEqual(builder.sha(path.read_bytes()), self.stage_manifest["ext/" + name])
        return sources
