"""Real enrollment transaction wiring to the existing physical admission helper.

The historical delivered fixture keeps its authenticated launcher and manifest.
Only verified_admission_scope is wired to the actual candidate helper here;
sealed helper delivery/current selection are separately proven in73 cases.
"""
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
SOURCE = Path(os.environ["H6_COMMON_FENCE_SOURCE"])
NATIVE = REPO / "ops/native_fabric/quota_continuity"
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
from test_go_native_stage import builds, native_stage, g, installer, loaded_entry
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner
import test_go_service_enrollment as enrollment
from test_go_service_enrollment import service_owner, reseal_modified_entry_for_disposable_fixtures

S = load_exact("h6_enrollment_physical_helper", SOURCE / "ext/support_bundle.py",
    "c38319838f286f1cc1591d1050870a91c44df5c787ac6fa27f7bc916b0f1411e")

@pytest.fixture(params=["single", "set"])
def fenced_service(service_owner, monkeypatch, request):
    case = service_owner
    # These are explicit pre-existing fixture installation objects. Enrollment
    # itself must never create or repair the physical admission owner.
    active = case.ext / "active"
    active.mkdir(mode=0o700, exist_ok=True)
    admission = active / ".admission.lock"
    if not admission.exists():
        fd = os.open(admission, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    assert admission.stat().st_mode & 0o777 == 0o600
    assert admission.stat().st_size == 0 and admission.stat().st_nlink == 1

    # Preserve the actual installer filename in the prepared source binding.
    # Its source-relative historical launcher remains the exact repository file.
    rollout = case.root / "tested-source/ops/native_fabric/quota_continuity/rollout"
    (rollout / "preimages").mkdir(parents=True)
    shutil.copyfile(SOURCE / "rollout/native_install.py", rollout / "native_install.py")
    shutil.copyfile(NATIVE / "rollout/preimages/native_generation_75330d.py",
                    rollout / "preimages/native_generation_75330d.py")
    current = load_exact("h6_fenced_native_install", rollout / "native_install.py",
        "2daa1ff46e22d8e8329b060f17fc46f38a832a363dc5453b1e6215c911cb7459")
    assert current.generation is g
    seam_calls = []
    @contextmanager
    def actual_physical_scope(store, generation, *, deadline_ns=None):
        # This seam intentionally leaves historical helper-delivery evidence
        # separate. The original fixture release and stable owner still verify.
        _, metadata = g.verify(store, generation)
        assert Path(metadata["stable_ext"]) == case.ext
        seam_calls.append({"store": str(store), "generation": generation})
        with S.admission_scope(case.ext, deadline_ns=deadline_ns) as held:
            yield held
    monkeypatch.setattr(g, "verified_admission_scope", actual_physical_scope, raising=False)
    monkeypatch.setattr(enrollment, "installer", current)
    if request.param == "set":
        enrollment.set_specification(case)
        plan = enrollment.prepare_set(case)
    else:
        plan = enrollment.prepare(case)
    assert plan["installer_sha256"] == hashlib.sha256((rollout / "native_install.py").read_bytes()).hexdigest()
    return SimpleNamespace(case=case, installer=current, plan=plan, family=request.param,
        admission=admission, seam_calls=seam_calls, expected_mints=2 if request.param == "set" else 1)

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
    assert len(f.seam_calls) == 3
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
         pytest.raises(S.PolicyPublicationRefused, match="POLICY_ADMISSION_LOCK_CHANGED"):
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
         pytest.raises(S.PolicyPublicationRefused, match="POLICY_ADMISSION_LOCK_CHANGED"):
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
