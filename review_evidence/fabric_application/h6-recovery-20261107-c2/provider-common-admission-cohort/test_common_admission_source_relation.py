"""Closed source relation and real installer refusal checks for one proposal."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from types import SimpleNamespace
from unittest import mock
import pytest

COHORT = Path(os.environ["H6_COMMON_ADMISSION_COHORT"])
SOURCE = COHORT / "source/ops/native_fabric/quota_continuity"
ROLLOUT = SOURCE / "rollout"

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

@pytest.fixture(scope="module")
def owners():
    B = load("h6_relation_builder", ROLLOUT / "build_review_stage.py")
    G = load("h6_relation_generation", ROLLOUT / "native_generation.py")
    with mock.patch.dict(sys.modules, {"build_review_stage": B, "native_generation": G}):
        I = load("h6_relation_installer", ROLLOUT / "native_install.py")
    assert I.stage_builder is B and I.generation is G
    return SimpleNamespace(B=B, G=G, I=I)

def read_manifest(name, final=False):
    folder = COHORT / ("builds-final" if final else "builds") / name
    return json.loads((folder / "native-manifest.json").read_bytes())

MEMBERS = ("ext/lease_broker.py", "ext/native_runtime_bindings.py",
           "ext/paid_model_owner.py", "ext/paid_provider_entry.py",
           "ext/quota_remote.py", "ext/remote_sub.sh", "ext/support_bundle.py")

@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("fault", ["preimage", "foreign"])
def test_partial_or_foreign_member_refuses_at_each_normalization_boundary(owners, member, fault):
    B = owners.B
    base = B._application_base(read_manifest("common-http", True))
    parent = read_manifest("provider-quota-base")
    base[member] = parent[member] if fault == "preimage" else "f" * 64
    original = dict(base)
    for call in (
        lambda: B.before_common_admission(base),
        lambda: B.normalize_application_carrier_base_manifest(base),
        lambda: B.go_application_dependencies(SOURCE, staged_manifest=base),
        lambda: B.go_staged_dependency_hashes(base, {}),
        lambda: B.validate_go_source_transition(B.provider_application_record()[1], base)):
        with pytest.raises(ValueError, match="common admission"):
            call()
        assert base == original

@pytest.mark.parametrize("fault", ["missing", "untouched"])
def test_whole_manifest_identity_refuses_partial_or_foreign_unchanged_members(owners, fault):
    B = owners.B
    base = B._application_base(read_manifest("common-http", True))
    if fault == "missing":
        del base["ext/pool_status.py"]
    else:
        base["ext/pool_status.py"] = "f" * 64
    with pytest.raises(ValueError, match="common admission"):
        B.before_common_admission(base)

def test_legacy_family_cannot_take_the_seven_forward_members(owners):
    B = owners.B
    legacy = read_manifest("quota-base")
    legacy.update(B.COMMON_ADMISSION_BASE_DIGESTS)
    with pytest.raises(ValueError, match="common admission"):
        B.before_common_admission(legacy)

def test_exact_inverse_preserves_current_and_historical_views_and_inputs(owners):
    B = owners.B
    current = read_manifest("common-http", True)
    saved = copy.deepcopy(current)
    base = B._application_base(current)
    assert B.before_common_admission(base) == read_manifest("provider-quota-base")
    normalized = B.before_quota_reset_recovery(B.before_common_admission(base))
    assert normalized == read_manifest("provider-base")
    assert B.before_provider_application(normalized) == read_manifest("ordinary-base")
    deps = B.go_application_dependencies(SOURCE, staged_manifest=current)
    assert deps["lease_broker.py"]["sha256"] == "3a210b259681460ec1e8ded91c45f84f6807e6ba4da1704b1ce587693d6531ed"
    assert "provider_preimage" in deps["lease_broker.py"]["composition"]
    staged = B.go_staged_dependency_hashes(current, {k:v["sha256"] for k,v in deps.items()})
    assert staged["lease_broker.py"] == current["ext/lease_broker.py"]
    B.validate_go_base_manifest(base, staged)
    assert B.validate_common_admission_manifest(current) is True
    assert current == saved

@pytest.mark.parametrize("fault", [
    "new-base-old-entry", "old-base-new-entry", "missing-http",
    "old-staged-broker", "forged-captured-broker", "untouched-stage-bytes"])
def test_actual_installer_rejects_cross_cohort_and_changed_component(owners, tmp_path, fault):
    B, I = owners.B, owners.I
    if fault == "old-base-new-entry":
        source = COHORT / "builds/provider-quota-http"
    else:
        source = COHORT / "builds-final/common-http"
    output = tmp_path.resolve() / "artifact"
    shutil.copytree(source, output)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    bundle = output / "external-go-component"
    record = json.loads((bundle / "component.json").read_bytes())
    if fault in {"new-base-old-entry", "old-base-new-entry"}:
        path = output / "native-code-stage/ext/native_go_entry.py"
        raw = ((SOURCE / "candidate/native_go_entry.py").read_bytes()
               if fault == "new-base-old-entry" else
               (COHORT / "builds-final/common-http/native-code-stage/ext/native_go_entry.py").read_bytes())
        path.write_bytes(raw)
        manifest["ext/native_go_entry.py"] = B.sha(raw)
    elif fault == "missing-http":
        del manifest["ext/application_http_realms.v1.json"]
        (output / "native-code-stage/ext/application_http_realms.v1.json").unlink()
    elif fault == "old-staged-broker":
        record["native_stage_dependencies"]["lease_broker.py"] = "3a210b259681460ec1e8ded91c45f84f6807e6ba4da1704b1ce587693d6531ed"
    elif fault == "forged-captured-broker":
        record["dependencies"]["lease_broker.py"]["sha256"] = manifest["ext/lease_broker.py"]
    else:
        p = output / "native-code-stage/ext/pool_status.py"
        p.write_bytes(p.read_bytes() + b"\n# corrupted untouched fixture member\n")
    (output / "native-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    (bundle / "component.json").write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError):
        I._go_component(bundle, Path(record["stable_ext"]), manifest)

def test_changed_captured_broker_cannot_skip_existing_provider_h2_provenance(owners):
    B = owners.B
    current = read_manifest("common-http", True)
    deps = B.go_application_dependencies(SOURCE, staged_manifest=current)
    values = {k:v["sha256"] for k,v in deps.items()}
    values["lease_broker.py"] = current["ext/lease_broker.py"]
    with pytest.raises(ValueError, match="captured dependency"):
        B.go_staged_dependency_hashes(current, values)

def test_composer_authenticates_untouched_staged_parent_before_any_replacement(owners, tmp_path):
    B = owners.B
    output = tmp_path.resolve() / "parent"
    shutil.copytree(COHORT / "builds/provider-quota-base", output)
    manifest = json.loads((output / "native-manifest.json").read_bytes())
    files = json.loads((output / "native-source-inventory.json").read_bytes())["files"]
    saved = copy.deepcopy(files)
    originals = {key:(output / "native-code-stage" / key).read_bytes() for key in MEMBERS}
    p = output / "native-code-stage/ext/pool_status.py"
    p.write_bytes(p.read_bytes() + b"\n# corrupted untouched fixture member\n")
    with pytest.raises(ValueError, match="source commitment differs"):
        B.compose_common_admission_stage(SOURCE, output, manifest, files)
    assert files == saved
    assert all((output / "native-code-stage" / key).read_bytes() == raw for key,raw in originals.items())

@pytest.mark.parametrize("entry", [False, True])
def test_corrupted_patch_refuses_in_real_composer_or_entry_resolver(owners, tmp_path, entry):
    B = owners.B
    root = tmp_path.resolve() / "source"
    overlay = root / "rollout/common_admission_cohort"
    shutil.copytree(ROLLOUT / "common_admission_cohort", overlay)
    name = "native_go_entry.py" if entry else "lease_broker.py"
    p = overlay / (name + ".patch")
    p.write_bytes(p.read_bytes() + b"\n# corrupted fixture patch\n")
    if entry:
        (root / "candidate").mkdir()
        shutil.copyfile(SOURCE / "candidate/native_go_entry.py", root / "candidate/native_go_entry.py")
        with pytest.raises(ValueError, match="source commitment differs"):
            B.go_entry_source(root, staged_manifest=read_manifest("common-http", True))
    else:
        output = tmp_path.resolve() / "parent"
        shutil.copytree(COHORT / "builds/provider-quota-base", output)
        manifest = json.loads((output / "native-manifest.json").read_bytes())
        files = json.loads((output / "native-source-inventory.json").read_bytes())["files"]
        originals = {key:(output / "native-code-stage" / key).read_bytes() for key in MEMBERS}
        with pytest.raises(ValueError, match="source commitment differs"):
            B.compose_common_admission_stage(root, output, manifest, files)
        assert all((output / "native-code-stage" / key).read_bytes() == raw for key,raw in originals.items())

def test_changed_transition_predecessor_still_refuses(owners):
    B = owners.B
    before = dict(B.provider_application_record()[1])
    before["pool"] = "f" * 64
    with pytest.raises(ValueError, match="source transition differs"):
        B.validate_go_source_transition(before, read_manifest("common-http", True))

def test_current_inventory_describes_current_step_and_preserves_complete_prior_row(owners):
    B = owners.B
    prior = json.loads((COHORT / "builds/provider-quota-base/native-source-inventory.json").read_bytes())["files"]
    current = json.loads((COHORT / "builds-final/common-http/native-source-inventory.json").read_bytes())["files"]
    record = B.common_admission_record()
    for key in MEMBERS:
        row = current[key]
        assert row["source"] == record["replacements"][key]["patch_source"]
        assert row["sha256"] == record["replacements"][key]["sha256"]
        assert not {"source_kind","composition_preimage_source","composition_preimage_sha256","patch_sha256"} & set(row)
        assert row["composition"]["preimage_inventory"] == prior[key]
        assert row["composition"]["composition_sha256"] == B.COMMON_ADMISSION_RECORD_SHA256
