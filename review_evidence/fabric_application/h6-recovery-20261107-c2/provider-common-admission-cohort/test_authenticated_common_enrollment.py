"""Authenticated single/set enrollment through the isolated exact emitted cohort."""
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.dont_write_bytecode = True
REPO = Path(os.environ["H6_REPOSITORY"])
COHORT = Path(os.environ["H6_COMMON_ADMISSION_COHORT"])
NATIVE = REPO / "ops/native_fabric/quota_continuity"
SOURCE = COHORT / "source/ops/native_fabric/quota_continuity"
ROLLOUT = SOURCE / "rollout"
sys.path[:0] = [str(NATIVE / "rollout"), str(REPO / "tests"), str(NATIVE / "tests"), str(REPO)]

def load_exact(name, path, wanted):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == wanted, str(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module

historical = load_exact("test_native_launcher_upgrade",
    NATIVE / "rollout/test_native_launcher_upgrade.py",
    "01699f5fb92b43424ed3f49d41d7641f4613cd4b8744e9efcd4c50a053031416")
from test_go_native_stage import builds, native_stage, g, installer, native_module_namespace
import test_go_native_install as go_history
from test_native_launcher_successor_transition import source_owners, owner
import test_go_service_enrollment as enrollment
from test_go_service_enrollment import reseal_modified_entry_for_disposable_fixtures
from test_provider_application_transition import provider_stage, select_provider

@pytest.fixture(params=["single", "set"])
def fenced_service(owner, provider_stage, monkeypatch, request):
    case = owner
    # Genuine bootstrap and completed historical successor remain under their
    # historical owner. No new helper is granted to an old generation.
    go_history.history.prepare(case)
    case.successor_receipt = installer.apply_successor(case.successor)
    case.successor_bytes = {p.name: p.read_bytes() for p in case.successor.iterdir()}
    selected_provider = select_provider(case, provider_stage)

    # Explicit owned fixture bootstrap, before any new selector/enrollment use.
    policy = case.ext.parent / "orch/fabric"
    policy.mkdir(parents=True, mode=0o700)
    policy_identity = (policy.stat().st_dev, policy.stat().st_ino)
    active = case.ext / "active"
    active.mkdir(mode=0o700, exist_ok=True)
    admission = active / ".admission.lock"
    fd = os.open(admission, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    assert admission.stat().st_nlink == 1 and admission.stat().st_size == 0

    current_builder = load_exact("h6_auth_cohort_builder", ROLLOUT / "build_review_stage.py",
        "6712da261b70388478fd914adb2c6af035ab416b20a3edf2775754bd4022e38b")
    current_g = load_exact("h6_auth_cohort_generation", ROLLOUT / "native_generation.py",
        "a570210825da7eb58be83381860c5ffa013ed5889486e4a3b822f96d0dab09db")
    monkeypatch.setitem(sys.modules, "build_review_stage", current_builder)
    monkeypatch.setitem(sys.modules, "native_generation", current_g)
    current_i = load_exact("h6_auth_cohort_install", ROLLOUT / "native_install.py",
        "2f7b84507fa5db3a10d9d464f740084b9f18831be5be69c6ef24adcafcaddb3a")
    assert current_i.generation is current_g and current_i.stage_builder is current_builder
    assert current_g.verified_admission_scope.__wrapped__.__code__.co_filename == str(ROLLOUT / "native_generation.py")
    monkeypatch.setitem(globals(), "g", current_g)
    monkeypatch.setattr(enrollment, "g", current_g)
    monkeypatch.setattr(enrollment, "installer", current_i)

    case.go_output = case.root / "authenticated-common-source"
    shutil.copytree(COHORT / "builds-final/common-http", case.go_output)
    case.go_manifest = json.loads((case.go_output / "native-manifest.json").read_bytes())
    assert len(case.go_manifest) == 121
    assert current_builder._manifest_digest(case.go_manifest) == "db3a75f12f2a013073692902be03b06e45381022dd2d200bd8e189dd45fa7357"
    current_builder.stage_external_go_component(SOURCE, case.go_output, str(case.ext),
                                               staged_manifest=case.go_manifest)
    (case.ext / "go_shim").mkdir()
    case.go_original = case.ext / "go_shim/go_shim.py"
    case.go_original.write_bytes((NATIVE / "source/go_shim.py").read_bytes())
    case.go_target = current_g.publish(case.go_output / "native-code-stage", case.ext, case.go_manifest)
    case.go_bundle = case.root / "authenticated-common-go-transition"
    case.go_plan = current_i.prepare_go(case.successor, case.go_target.name,
        case.go_output / "external-go-component", case.go_bundle)
    assert case.go_plan["expected_selection"] == selected_provider
    assert case.go_plan["to_launcher"] == hashlib.sha256((ROLLOUT / "native_generation.py").read_bytes()).hexdigest()
    receipt = current_i.apply_go(case.go_bundle)
    assert receipt["selection"] == current_g.current(case.store)
    assert receipt["to_launcher"] == case.go_plan["to_launcher"]
    assert current_g.current(case.store)["generation"] == case.go_target.name
    _, metadata = current_g.verify(case.store, case.go_target.name)
    assert metadata["files"] == case.go_manifest
    assert hashlib.sha256((case.go_target / "ext/support_bundle.py").read_bytes()).hexdigest() == "c38319838f286f1cc1591d1050870a91c44df5c787ac6fa27f7bc916b0f1411e"
    # The unchanged service fixture predates the selector's required policy
    # directory and creates it itself. Reuse exactly this already-created empty
    # fixture directory; every other mkdir keeps its original behavior.
    original_mkdir = Path.mkdir
    reused_policy = []
    def fixture_mkdir(path, *args, **kwargs):
        if path == policy:
            assert not args and kwargs == {"parents": True}
            assert path.is_dir() and not list(path.iterdir())
            assert (path.stat().st_dev, path.stat().st_ino) == policy_identity
            assert path.stat().st_uid == os.geteuid()
            reused_policy.append(str(path))
            return None
        return original_mkdir(path, *args, **kwargs)
    with mock.patch.object(Path, "mkdir", fixture_mkdir):
        case = enrollment.service_owner_from_completed_go(case)
    assert reused_policy == [str(policy)]
    assert (policy.stat().st_dev, policy.stat().st_ino) == policy_identity
    with native_module_namespace(case.go_manifest, clean_yaml=True):
        if request.param == "set":
            enrollment.set_specification(case)
            plan = enrollment.prepare_set(case)
        else:
            plan = enrollment.prepare(case)
        assert plan["installer_sha256"] == hashlib.sha256((ROLLOUT / "native_install.py").read_bytes()).hexdigest()
        proof = {"family": request.param, "manifest_sha256": current_builder._manifest_digest(case.go_manifest),
                 "generation": case.go_target.name, "launcher_sha256": receipt["to_launcher"],
                 "installer_sha256": plan["installer_sha256"],
                 "builder_sha256": hashlib.sha256((ROLLOUT / "build_review_stage.py").read_bytes()).hexdigest(),
                 "composition_sha256": current_builder.COMMON_ADMISSION_RECORD_SHA256,
                 "go_plan_digest": case.go_plan["digest"], "service_plan_digest": plan["digest"],
                 "scope_injected": False, "actual_common_helper": True, "live_acceptance": False}
        (case.root / "authenticated-source-proof.json").write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")
        yield SimpleNamespace(case=case, installer=current_i, plan=plan, family=request.param,
            admission=admission, expected_mints=2 if request.param == "set" else 1)

def file_identity(path):
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

def original_state(f):
    c = f.case
    return {"accounts": (c.accounts.read_bytes(), file_identity(c.accounts)),
            "broker": tuple(file_identity(c.ext / ("broker/" + name)) for name in ("leases.lock", "leases.sqlite"))}

def assert_preserved(f, before):
    c = f.case
    assert (c.accounts.read_bytes(), file_identity(c.accounts)) == before["accounts"]
    assert tuple(file_identity(c.ext / ("broker/" + name)) for name in ("leases.lock", "leases.sqlite")) == before["broker"]
    enrollment.unchanged_ingress(c)

def replace_admission(f):
    replacement = f.admission.with_name(".fixture-new-admission")
    fd = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    before = f.admission.stat().st_ino
    os.replace(replacement, f.admission)
    assert f.admission.stat().st_ino != before

def test_physical_lock_excludes_then_original_bundle_completes_once(fenced_service):
    f = fenced_service
    c, I = f.case, f.installer
    before = original_state(f)
    inode = f.admission.stat().st_ino
    fd = os.open(f.admission, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with mock.patch.object(I, "_service_broker_lock", side_effect=AssertionError("entered Broker before admission")), \
             mock.patch.object(I.secrets, "token_urlsafe", side_effect=AssertionError("blocked enrollment minted")), \
             mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("blocked enrollment published")), \
             pytest.raises(BlockingIOError, match="SUPPORT_ADMISSION_LOCK_BUSY"):
            I.apply_go_service_enrollment(c.service_bundle)
    finally:
        os.close(fd)
    assert f.admission.stat().st_ino == inode
    assert not c.intent.exists() and not c.binding.exists() and not c.service_receipt.exists()
    assert not (c.service_bundle / I._SERVICE_PRIVATE).exists()
    assert_preserved(f, before)
    with mock.patch.object(I.secrets, "token_urlsafe", wraps=I.secrets.token_urlsafe) as minted:
        receipt = I.apply_go_service_enrollment(c.service_bundle)
        assert minted.call_count == f.expected_mints
    assert receipt["plan_digest"] == f.plan["digest"]
    assert len(json.loads(c.accounts.read_bytes())["application_grants"]) == f.expected_mints
    binding_before = (c.binding.read_bytes(), file_identity(c.binding))
    accounts_before = (c.accounts.read_bytes(), file_identity(c.accounts))
    with mock.patch.object(I.secrets, "token_urlsafe", side_effect=AssertionError("reconcile reminted")), \
         mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed reconcile rewrote")):
        assert I.reconcile_go_service_enrollment(c.service_bundle) == receipt
    assert (c.binding.read_bytes(), file_identity(c.binding)) == binding_before
    assert (c.accounts.read_bytes(), file_identity(c.accounts)) == accounts_before
    assert f.admission.stat().st_ino == inode
    enrollment.unchanged_ingress(c)

def test_replaced_admission_inode_after_broker_lock_refuses_before_intent(fenced_service):
    f = fenced_service
    c, I = f.case, f.installer
    before = original_state(f)
    real_broker = I._service_broker_lock
    @contextmanager
    def replace_after_broker(*args, **kwargs):
        with real_broker(*args, **kwargs):
            replace_admission(f)
            yield
    with mock.patch.object(I, "_service_broker_lock", replace_after_broker), \
         mock.patch.object(I.secrets, "token_urlsafe", side_effect=AssertionError("changed owner minted")), \
         mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("changed owner published")), \
         pytest.raises(ValueError, match="POLICY_ADMISSION_LOCK_CHANGED"):
        I.apply_go_service_enrollment(c.service_bundle)
    assert not c.intent.exists() and not c.binding.exists() and not c.service_receipt.exists()
    assert not (c.service_bundle / I._SERVICE_PRIVATE).exists()
    assert_preserved(f, before)

def test_late_admission_replacement_preserves_prepared_effect_without_binding_rename(fenced_service):
    f = fenced_service
    c, I = f.case, f.installer
    before = original_state(f)
    prepared = c.store / "bootstrap" / (f.plan["digest"] + ".service-binding-prepared.json")
    real_write = g.atomic_bytes
    seen = []
    def write_then_replace(path, raw, mode):
        real_write(path, raw, mode)
        if Path(path) == prepared:
            assert not seen
            seen.append(str(path))
            replace_admission(f)
    with mock.patch.object(g, "atomic_bytes", side_effect=write_then_replace), \
         mock.patch.object(I.secrets, "token_urlsafe", wraps=I.secrets.token_urlsafe) as minted, \
         pytest.raises(ValueError, match="POLICY_ADMISSION_LOCK_CHANGED"):
        I.apply_go_service_enrollment(c.service_bundle)
    assert seen == [str(prepared)]
    assert minted.call_count == f.expected_mints
    assert c.intent.exists() and prepared.exists()
    private = c.service_bundle / I._SERVICE_PRIVATE
    assert private.exists()
    commitment = json.loads(prepared.read_bytes())
    stage = Path(commitment["stage"])
    assert stage.exists() and stage.read_bytes() == private.read_bytes()
    assert hashlib.sha256(stage.read_bytes()).hexdigest() == commitment["sha256"]
    assert not c.binding.exists() and not c.service_receipt.exists()
    assert_preserved(f, before)
