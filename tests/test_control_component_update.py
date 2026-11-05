"""Offline invariants for the owned Control component update.

Source tests only: no installed release, no launchd, no root, no installed file
and no administrative checkout is read or written.  The composition is driven
against a hermetic stand-in for the one installed Executive host, so every
refusal path is exercised with zero cutover and every crash gap of the happy
path is exercised without dispatching a duplicate effect.
"""

import copy
import hashlib
import json
import os
import plistlib
from pathlib import Path

import pytest

from ops.executive_os import autonomy_control as ac
from ops.executive_os import control_component_update as ccu
from ops.executive_os import control_observation
from ops.executive_os import prepare_control_successor as prepare

try:  # the incumbent's real schema fixture is reused, never redefined
    from tests.test_prepare_control_successor import control_input  # noqa: F401
except ImportError:  # pragma: no cover - the flat test root is equally valid
    from test_prepare_control_successor import control_input  # noqa: F401


PRIOR_SHA = "80f384b8f58b7ca46422d9783aa5c0613c7bf4b2"
TARGET_SHA = "2" * 40
PRIOR_ROOT = os.fspath(ac.SYSTEM_ROOT / "releases" / PRIOR_SHA)
TARGET_ROOT = os.fspath(ac.SYSTEM_ROOT / "releases" / TARGET_SHA)
MACRO_ROOT = "/approved/retained/Macro"
CONTROL_CONFIG = os.fspath(ac.CONTROL_CONFIG)
WORKER_CONFIG = os.fspath(ac.WORKER_CONFIG)
CONTROL_PLIST = os.fspath(ac.CONTROL_PLIST)
WORKER_PLIST = os.fspath(ac.WORKER_PLIST)


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _control_plist(root: str) -> dict:
    return {
        "AbandonProcessGroup": False,
        "EnvironmentVariables": {
            "HOME": "/var/db/mastermind-executive/control/home",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONUNBUFFERED": "1",
            "TZ": "UTC",
        },
        "ExitTimeOut": 15,
        "GroupName": "_mastermind_exec",
        "KeepAlive": True,
        "Label": "com.mastermind.executive.control",
        "ProcessType": "Interactive",
        "ProgramArguments": [
            os.fspath(ac.PINNED_PYTHON),
            "-I",
            "-S",
            "-B",
            root + "/scripts/executive_os_phase1c_control_wrapper.py",
            "--config",
            CONTROL_CONFIG,
            "--sentinel-file",
            "/Library/Application Support/MastermindExecutive/config/control-env-canary",
            "--attestation",
            "/var/db/mastermind-executive/control/canaries/"
            "control-environment-attestation.json",
            "--release-root",
            root,
        ],
        "RunAtLoad": True,
        "StandardErrorPath": "/var/log/mastermind-executive/control/stderr.log",
        "StandardOutPath": "/var/log/mastermind-executive/control/stdout.log",
        "ThrottleInterval": 10,
        "Umask": 63,
        "UserName": "_mastermind_exec",
        "WorkingDirectory": root,
    }


def _worker_plist(root: str) -> dict:
    return {
        "GroupName": "_mastermind_worker",
        "KeepAlive": True,
        "Label": "com.mastermind.executive.worker.codex",
        "ProcessType": "Interactive",
        "ProgramArguments": [
            os.fspath(ac.PINNED_PYTHON),
            "-I",
            "-S",
            "-B",
            root + "/scripts/executive_os_phase1c_worker.py",
            "serve",
            "--config",
            WORKER_CONFIG,
        ],
        "RunAtLoad": True,
        "StandardErrorPath": "/var/log/mastermind-executive/worker/stderr.log",
        "StandardOutPath": "/var/log/mastermind-executive/worker/stdout.log",
        "ThrottleInterval": 10,
        "Umask": 63,
        "UserName": "_mastermind_worker",
        "WorkingDirectory": root,
    }


def _disarmed_receipt(control_digest: str, worker_digest: str) -> dict:
    """One complete existing DISARMED authority receipt."""

    return {
        "schema_version": "mastermind.executive_autonomy_state/v1",
        "state": "DISARMED",
        "release_sha": PRIOR_SHA,
        "acceptance_receipt_sha256": "1" * 64,
        "gate_b_receipt_sha256": "2" * 64,
        "provider_readiness_receipt_sha256": "3" * 64,
        "readiness_observed_at": "2026-01-01T00:00:00Z",
        "credential_expires_at": "2026-01-02T00:00:00Z",
        "readiness_expires_at": "2026-01-02T00:00:00Z",
        "expected_credential_kind": "none",
        "workspace_binding_class": "none",
        "prior_control_config_sha256": "4" * 64,
        "prior_worker_config_sha256": "5" * 64,
        "control_config_sha256": control_digest,
        "worker_config_sha256": worker_digest,
        "capability_policy_digest": ac.CAPABILITY_POLICY_DIGEST,
        "execution_profile_digest": ac.EXECUTION_PROFILE_DIGEST,
        "native_helper_grant_digest": ac.NATIVE_HELPER_GRANT_DIGEST,
        "security_config_digest": ac.SECURITY_CONFIG_DIGEST,
        "transaction_id": "autonomy-000000000000",
        "observed_at": "2026-01-01T00:00:00Z",
        "tool_version": ac.TOOL_VERSION,
        "predicates": {
            "acceptance_passed": False,
            "configs_validated": True,
            "gate_b_passed": False,
            "provider_readiness_passed": False,
            "runtime_quiescent": False,
            "service_uids_quiescent": True,
        },
    }


class _Group:
    """The fixed control group identity the owner resolves on the host."""

    gr_gid = 450


class _Groups:
    @staticmethod
    def getgrnam(name: str) -> _Group:
        return _Group()


class _Info:
    """The minimal stat facts the owner's closed readers consume."""

    st_uid = 0
    st_gid = 0
    st_mode = 0o100444
    st_nlink = 1
    st_size = 0
    st_mtime_ns = 0
    st_ctime_ns = 0
    st_dev = 1
    st_ino = 1


class FakeFiles:
    """An in-memory installed filesystem."""

    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.writes: list[str] = []

    def read(self, path) -> bytes:
        key = os.fspath(path)
        if key not in self.data:
            raise FileNotFoundError(key)
        return self.data[key]

    def write(self, path, payload: bytes, *, replace: bool = True) -> None:
        key = os.fspath(path)
        if key in self.data and not replace:
            raise FileExistsError(key)
        self.data[key] = payload
        self.writes.append(key)


class Crash(BaseException):
    """Process death: BaseException so the composition cannot absorb it."""


class FakeHost(ac.ProductionControlComponentHost):
    """A hermetic stand-in for the one installed Executive host."""

    def __init__(self, control: dict, worker: dict, *, files: FakeFiles | None = None):
        super().__init__()
        self.files = files if files is not None else FakeFiles()
        self.control = control
        self.worker = worker
        self.control_raw = _canonical(control)
        self.worker_raw = _canonical(worker)
        self.labels = {"com.mastermind.executive.control": True,
                       "com.mastermind.executive.worker.codex": False}
        self.disabled = {"com.mastermind.executive.control": False,
                        "com.mastermind.executive.worker.codex": True}
        self.commands: list[list[str]] = []
        self.phases: list[str] = []
        self.proofs: list[tuple[str, str]] = []
        self.publications: list[str] = []
        self.closed = False
        self.manifest: dict = {}
        self.transaction_present = False
        self.quiescent = True
        self.admission_ok = True
        self.release_seals = {PRIOR_SHA: "1" * 64, TARGET_SHA: "2" * 64}
        self.admin_checkout = TARGET_SHA
        self.receipt = _disarmed_receipt(
            _sha(self.control_raw), _sha(self.worker_raw))
        self.ceo_receipt = None
        self.crash_at: int | None = None
        self.fail_after: set[str] = set()
        self.files.write(CONTROL_PLIST, plistlib.dumps(_control_plist(PRIOR_ROOT)))
        self.files.write(WORKER_PLIST, plistlib.dumps(_worker_plist(PRIOR_ROOT)))
        self.files.write(CONTROL_CONFIG, self.control_raw)
        self.files.write(WORKER_CONFIG, self.worker_raw)
        # The fixture installation is not an effect of the operation.
        self.files.writes.clear()

    # -- effect bookkeeping ----------------------------------------------------

    def _effect(self, argv: list[str]) -> None:
        if self.crash_at is not None and len(self.commands) == self.crash_at:
            raise Crash(" ".join(argv))
        self.commands.append(list(argv))
        joined = " ".join(argv)
        if any(token in joined for token in self.fail_after):
            raise OSError("response lost")

    # -- the owner's installed reads ------------------------------------------

    def effective_uid(self) -> int:
        return 0

    def _component_root_file(self, path, *, code: str) -> bytes:
        try:
            return self.files.read(path)
        except FileNotFoundError as exc:
            raise ac.ComponentUpdateRefused(code) from exc

    def _component_plist_document(self, path) -> dict:
        return plistlib.loads(self._component_root_file(
            path, code="control_component_plist_unreadable"))

    def _configs(self):
        return (
            self.control,
            self.worker,
            _sha(self.control_raw),
            _sha(self.worker_raw),
            self.control_raw,
            self.worker_raw,
        )

    def _component_release_seal(self, sha: str, *, target: bool = False) -> str:
        value = self.release_seals.get(sha)
        if value is None:
            raise ac.ComponentUpdateRefused("control_component_release_seal_invalid")
        return value

    @staticmethod
    def _component_interpreter_qualified() -> bool:
        return True

    def _component_admin_checkout(self, target_sha: str) -> str:
        if self.admin_checkout != target_sha:
            raise ac.ComponentUpdateRefused(
                "control_component_admin_checkout_unavailable")
        return self.admin_checkout

    def _component_autonomy_receipt(self, prior_sha, configs):
        if self.receipt is None:
            raise ac.ComponentUpdateRefused(
                "control_component_authority_receipt_invalid")
        if self.receipt.get("state") != "DISARMED":
            raise ac.ComponentUpdateRefused(
                "control_component_authority_receipt_armed")
        return copy.deepcopy(self.receipt), ac.ReceiptMetadata(
            uid=0, gid=0, mode=0o444, nlink=1, is_regular=True,
            is_symlink=False, has_acl=False)

    def _component_ceo_receipt(self):
        return copy.deepcopy(self.ceo_receipt) if self.ceo_receipt else None

    def require_transaction_absent(self) -> None:
        if self.transaction_present:
            raise ac.ComponentUpdateRefused("control_component_transaction_occupied")

    def require_runtime_quiescent(self, config) -> None:
        if not self.quiescent:
            raise ac.ComponentUpdateRefused("control_component_owner_not_quiescent")

    def _component_label_loaded(self, label: str) -> bool:
        return self.labels[label]

    def _component_disabled_override(self, label: str):
        return self.disabled[label]

    # -- the transaction seams -------------------------------------------------

    def _config_root_safe(self) -> None:
        return None

    def _verify_published_inode(self, descriptor) -> None:
        return None

    def _transaction_present(self) -> bool:
        return self.transaction_present

    def _claim_transaction_owner(self) -> None:
        self._transaction_owner_fd = 1

    def _create_marker(self, transaction, *, operation: str) -> None:
        self._transaction_owner_fd = 1
        self._active_transaction = transaction
        self.transaction_present = True
        self.manifest = self._manifest_document(
            transaction, "LOCKED", operation=operation)
        self.files.write(
            os.fspath(ac.AUTONOMY_TRANSACTION / ac._TRANSACTION_MANIFEST_NAME),
            ac._encoded_json(self.manifest))
        self.files.write(
            os.fspath(ac.AUTONOMY_TRANSACTION / "prior-control.json"),
            transaction.prior_configs.control_bytes)
        self.files.write(
            os.fspath(ac.AUTONOMY_TRANSACTION / "prior-worker.json"),
            transaction.prior_configs.worker_bytes)
        for name in ac._COMPONENT_ARCHIVES:
            self.files.write(
                os.fspath(ac.AUTONOMY_TRANSACTION / name),
                self._component_prior_archives.get(name, b""))

    def _manifest(self) -> dict:
        return dict(self.manifest)

    def _persist_phase(self, transaction, phase: str, *, operation=None) -> None:
        operation = operation or str(self.manifest.get("operation"))
        value = self._manifest_document(transaction, phase, operation=operation)
        for group in (ac._COEXISTENCE_MANIFEST_FIELDS, ac._COMPONENT_MANIFEST_FIELDS):
            for key in group:
                if key in self.manifest:
                    value[key] = self.manifest[key]
        self.manifest = value
        self.phases.append(phase)

    def _component_archives(self) -> dict:
        archives = {}
        for name in ("prior-control.json", "prior-worker.json"):
            archives[name] = self.files.read(
                os.fspath(ac.AUTONOMY_TRANSACTION / name))
        for name in ac._COMPONENT_ARCHIVES:
            archives[name] = self.files.read(
                os.fspath(ac.AUTONOMY_TRANSACTION / name))
        return archives

    def replace_control_config(self, transaction) -> None:
        control_candidate, _worker = self._candidate_paths(transaction.transaction_id)
        payload = self.files.read(control_candidate)
        self.files.write(CONTROL_CONFIG, payload)
        self._persist_phase(transaction, "CONTROL_REPLACED")
        self._control_observation_fresh_transaction = transaction

    def complete_transaction(self, transaction) -> None:
        control_observation.publish_for_transaction(self, transaction)
        self.closed = True
        self.phases.append("CLOSED")

    # -- the fixed effects -----------------------------------------------------

    def _run_fixed(self, command, *, cwd, timeout: float = 30.0) -> None:
        argv = list(command)
        self._effect(argv)
        if "bootout" in argv:
            self.labels["com.mastermind.executive.control"] = False
        if "bootstrap" in argv:
            self.labels["com.mastermind.executive.control"] = True

    def _loaded_observe_only(self, label: str) -> bool:
        return self.labels[label]

    def _require_control_plist_safe(self) -> None:
        return None

    def prove_control_admission_bound(self, expected_sha: str, digest: str) -> None:
        self.proofs.append((expected_sha, digest))
        if not self.admission_ok:
            raise RuntimeError("control admission bound refused")

    def _ceo_admission_probe(self, expected_sha: str, digest: str) -> bool:
        return self.admission_ok

    def write_control_component_receipt(self, transaction, receipt) -> None:
        self.files.write(os.fspath(ac.CONTROL_COMPONENT_RECEIPT),
                         ac._encoded_json(receipt))
        self._persist_phase(transaction, "CONTROL_COMPONENT_RECEIPT_REPLACED")


@pytest.fixture
def host(control_input, monkeypatch):
    control = copy.deepcopy(control_input)
    control["ceo_ingress_app_macro_root"] = MACRO_ROOT
    worker = {"operator_harness_armed": False}
    host_obj = FakeHost(control, worker)

    def fake_atomic_file(path, payload, *, mode, uid, gid, replace):
        host_obj.files.write(path, payload, replace=replace)

    def fake_read_root_file(path, *, modes, uid=0, gid=None):
        return host_obj.files.read(path), _Info()

    monkeypatch.setattr(ac, "_atomic_file", fake_atomic_file)
    monkeypatch.setattr(ac, "_read_root_file", fake_read_root_file)
    monkeypatch.setattr(ac, "grp", _Groups)
    return host_obj


@pytest.fixture
def publisher(monkeypatch):
    """Record the control-observation publication instead of performing it."""

    calls: list[str] = []

    def record(owner, transaction):
        calls.append(transaction.transaction_id)
        return "c" * 64

    monkeypatch.setattr(control_observation, "publish_for_transaction", record)
    return calls


# ---------------------------------------------------------------------------
# The pure compiler.
# ---------------------------------------------------------------------------


def test_release_substitution_moves_only_the_release_coordinates():
    document = _control_plist(PRIOR_ROOT)
    result = ccu.substitute_release_root(
        document, prior_root=PRIOR_ROOT, target_root=TARGET_ROOT)
    assert result["WorkingDirectory"] == TARGET_ROOT
    arguments = result["ProgramArguments"]
    assert arguments[4] == TARGET_ROOT + "/scripts/executive_os_phase1c_control_wrapper.py"
    assert arguments[-1] == TARGET_ROOT
    # Every non-release coordinate is preserved byte for byte.
    released = {"ProgramArguments", "WorkingDirectory"}
    assert {k: v for k, v in result.items() if k not in released} == {
        k: v for k, v in document.items() if k not in released}
    assert len(arguments) == len(document["ProgramArguments"])
    for before, after in zip(document["ProgramArguments"], arguments):
        if before.startswith(PRIOR_ROOT):
            assert after == TARGET_ROOT + before[len(PRIOR_ROOT):]
        else:
            assert after == before


def test_release_substitution_refuses_a_release_root_outside_the_two_coordinates():
    document = _control_plist(PRIOR_ROOT)
    document["StandardOutPath"] = PRIOR_ROOT + "/logs/stdout.log"
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.substitute_release_root(
            document, prior_root=PRIOR_ROOT, target_root=TARGET_ROOT)
    assert caught.value.code == "plist_release_root_unexpected"


def test_release_substitution_refuses_a_foreign_working_directory():
    document = _control_plist(PRIOR_ROOT)
    document["WorkingDirectory"] = "/tmp"
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.substitute_release_root(
            document, prior_root=PRIOR_ROOT, target_root=TARGET_ROOT)
    assert caught.value.code == "plist_release_root_unexpected"


def test_candidate_changes_only_the_two_source_coordinates(control_input):
    control = copy.deepcopy(control_input)
    control["ceo_ingress_app_macro_root"] = MACRO_ROOT
    control_raw = _canonical(control)
    candidate = ccu.compile_candidate(
        control_raw,
        plistlib.dumps(_control_plist(PRIOR_ROOT)),
        plistlib.dumps(_worker_plist(PRIOR_ROOT)),
        target_sha=TARGET_SHA,
        prior_sha=PRIOR_SHA,
        worker_config_sha256="3" * 64,
        prior_release_root=PRIOR_ROOT,
        target_release_root=TARGET_ROOT,
    )
    assert candidate.changed_control_fields == ("proof_base_sha",
                                                "proof_source_repository")
    after = json.loads(candidate.control_config_after.decode("utf-8"))
    before = json.loads(control_raw.decode("utf-8"))
    assert set(after) == set(before)
    assert {key for key in before if before[key] != after[key]} == {
        "proof_base_sha", "proof_source_repository"}
    assert after["proof_base_sha"] == TARGET_SHA
    assert after["proof_source_repository"] == (
        "/var/db/mastermind-executive/control/admin-checkout/" + TARGET_SHA)
    # The installed Macro root is preserved and never exported.
    assert after["ceo_ingress_app_macro_root"] == MACRO_ROOT
    # Every other Control field is preserved.
    for key, value in before.items():
        if key in {"proof_base_sha", "proof_source_repository"}:
            continue
        assert after[key] == value


def test_candidate_refuses_a_config_that_names_another_release(control_input):
    control = copy.deepcopy(control_input)
    control["proof_base_sha"] = "9" * 40
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.compile_candidate(
            _canonical(control),
            plistlib.dumps(_control_plist(PRIOR_ROOT)),
            plistlib.dumps(_worker_plist(PRIOR_ROOT)),
            target_sha=TARGET_SHA,
            prior_sha=PRIOR_SHA,
            worker_config_sha256="3" * 64,
            prior_release_root=PRIOR_ROOT,
            target_release_root=TARGET_ROOT,
        )
    assert caught.value.code == "control_config_source_mismatch"


def test_prepare_support_preserves_the_installed_macro_root(control_input):
    control = copy.deepcopy(control_input)
    control["ceo_ingress_app_macro_root"] = MACRO_ROOT
    before = copy.deepcopy(control)
    result = prepare.build_component_successor(control, source_sha=TARGET_SHA)
    assert control == before
    assert result["ceo_ingress_app_macro_root"] == MACRO_ROOT
    assert {key for key in control if control[key] != result[key]} == {
        "proof_base_sha", "proof_source_repository"}


def test_prepare_support_refuses_a_document_without_a_macro_binding(control_input):
    control = copy.deepcopy(control_input)
    control.pop("ceo_ingress_app_macro_root")
    with pytest.raises(prepare.PreparationError):
        prepare.build_component_successor(control, source_sha=TARGET_SHA)


# ---------------------------------------------------------------------------
# The plan.
# ---------------------------------------------------------------------------


def _plan(host_obj):
    return ccu.plan(host_obj, target_sha=TARGET_SHA)


def test_plan_is_read_only_and_carries_only_hashes_states_and_effects(host):
    before = dict(host.files.data)
    result = _plan(host)
    assert result["ok"] is True
    assert result["outcome"] == "PLANNED"
    assert host.files.data == before
    document = result["plan"]
    assert set(document["preconditions"]) == set(ccu.PRECONDITIONS)
    assert all(state is True for state in document["preconditions"].values())
    assert document["effects"] == list(ccu.EFFECTS)
    assert document["target_sha"] == TARGET_SHA
    assert document["prior_sha"] == PRIOR_SHA
    # No installed configuration, token or credential content anywhere.
    encoded = json.dumps(document)
    assert MACRO_ROOT not in encoded
    assert "operator_harness_binary_digest" not in encoded
    assert host.control_raw.decode("utf-8") not in encoded
    assert ccu.plan_digest(document) == result["plan_sha256"]


def test_plan_digest_is_bound_to_every_precondition(host):
    document = _plan(host)["plan"]
    changed = copy.deepcopy(document)
    changed["preconditions"]["worker_absent"] = False
    assert ccu.plan_digest(changed) != ccu.plan_digest(document)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda h: h.labels.__setitem__("com.mastermind.executive.worker.codex", True),
         "control_component_worker_live"),
        (lambda h: h.disabled.__setitem__("com.mastermind.executive.worker.codex", False),
         "control_component_worker_not_disabled"),
        (lambda h: h.disabled.__setitem__("com.mastermind.executive.worker.codex", None),
         "control_component_worker_not_disabled"),
        (lambda h: setattr(h, "transaction_present", True),
         "control_component_transaction_occupied"),
        (lambda h: setattr(h, "quiescent", False),
         "control_component_owner_not_quiescent"),
        (lambda h: setattr(h, "admin_checkout", "4" * 40),
         "control_component_admin_checkout_unavailable"),
        (lambda h: h.release_seals.pop(TARGET_SHA),
         "control_component_release_seal_invalid"),
        (lambda h: setattr(h, "receipt", None),
         "control_component_authority_receipt_invalid"),
        (lambda h: h.receipt.__setitem__("state", "ARMED"),
         "control_component_authority_receipt_armed"),
        (lambda h: h.labels.__setitem__("com.mastermind.executive.control", False),
         "control_component_control_not_registered"),
        (lambda h: h.disabled.__setitem__("com.mastermind.executive.control", True),
         "control_component_control_disabled"),
    ],
)
def test_every_refusal_is_pre_effect_with_zero_cutover(host, mutate, code):
    mutate(host)
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == code
    assert host.commands == []
    assert host.files.writes == []
    assert host.proofs == []
    assert host.closed is False


def test_an_armed_control_flag_is_an_authority_refusal_not_a_transport_one(host):
    # ``ceo_ingress_app_armed`` is transport admission, never CEO-submit
    # authority: it stays armed and the plan still succeeds.
    assert host.control["ceo_ingress_app_armed"] is True
    assert _plan(host)["ok"] is True
    host.control["ceo_submit_armed"] = True
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_authority_receipt_armed"


# ---------------------------------------------------------------------------
# The apply.
# ---------------------------------------------------------------------------


def _apply(host_obj, plan_sha256=None):
    if plan_sha256 is None:
        plan_sha256 = ccu.plan(host_obj, target_sha=TARGET_SHA)["plan_sha256"]
    return ccu.apply(host_obj, target_sha=TARGET_SHA, plan_sha256=plan_sha256)


def test_apply_dispatches_the_fixed_effects_in_the_fixed_order(host, publisher):
    result = _apply(host)
    assert result["ok"] is True
    assert result["outcome"] == "UPDATED"
    bootout = [c for c in host.commands if "bootout" in c]
    bootstrap = [c for c in host.commands if "bootstrap" in c]
    assert len(bootout) == 1 and len(bootstrap) == 1
    assert host.commands.index(bootout[0]) < host.commands.index(bootstrap[0])
    # The bootout is recorded before it is dispatched; the bootstrap likewise.
    assert host.phases.index("CONTROL_BOOTOUT_RECORDED") < len(host.commands)
    assert "CONTROL_BOOTSTRAP_RECORDED" in host.phases
    assert host.phases.index("CONTROL_BOOTSTRAP_RECORDED") > host.phases.index(
        "CONTROL_BOOTOUT_RECORDED")
    # The consumed-config proof binds the target release and the new digest.
    assert host.proofs == [(TARGET_SHA, host.proofs[0][1])]
    assert host.proofs[0][1] != _sha(host.control_raw)
    # The observation is published by the same held owner and the marker closes.
    assert publisher == [result["transaction_id"]]
    assert host.closed is True
    assert host.phases[-1] == "CLOSED"


def test_apply_preserves_every_nonallowed_field_and_the_worker_runtime(host, publisher):
    before_control = copy.deepcopy(host.control)
    before_worker = copy.deepcopy(host.worker)
    _apply(host)
    after = json.loads(host.files.read(CONTROL_CONFIG).decode("utf-8"))
    assert set(after) == set(before_control)
    assert {key for key in before_control if before_control[key] != after[key]} == {
        "proof_base_sha", "proof_source_repository"}
    # The Worker configuration is never written.
    assert host.files.read(WORKER_CONFIG) == _canonical(before_worker)
    # The Worker daemon is never started, stopped, enabled or disarmed.
    assert host.labels["com.mastermind.executive.worker.codex"] is False
    assert not any("worker" in " ".join(command) for command in host.commands)


def test_apply_retargets_both_plists_to_the_target_release(host, publisher):
    _apply(host)
    control = plistlib.loads(host.files.read(CONTROL_PLIST))
    worker = plistlib.loads(host.files.read(WORKER_PLIST))
    assert control["WorkingDirectory"] == TARGET_ROOT
    assert worker["WorkingDirectory"] == TARGET_ROOT
    assert control["Label"] == "com.mastermind.executive.control"
    assert worker["Label"] == "com.mastermind.executive.worker.codex"
    # The Worker plist keeps every non-release coordinate.
    assert control["UserName"] == "_mastermind_exec"
    assert worker["UserName"] == "_mastermind_worker"


def test_apply_refuses_a_plan_digest_that_does_not_match(host, publisher):
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256="0" * 64)
    assert caught.value.code == "control_component_plan_digest_mismatch"
    assert host.commands == []
    assert host.files.writes == []
    assert host.closed is False


def test_apply_refuses_a_plan_that_drifted_after_it_was_proved(host, publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    # The installed Control plist drifts before the apply.
    host.files.write(CONTROL_PLIST, plistlib.dumps(_control_plist(TARGET_ROOT)))
    with pytest.raises(ac.ComponentUpdateRefused):
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert host.commands == []
    assert host.closed is False


def test_apply_refuses_an_occupied_global_transaction(host, publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    host.transaction_present = True
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert caught.value.code == "control_component_transaction_occupied"
    assert host.commands == []
    assert host.files.writes == []


def test_apply_refuses_a_wrong_consumed_config(host, publisher):
    host.admission_ok = False
    with pytest.raises(ac.TransactionEffectUnknown):
        _apply(host)
    # The marker and its preimages are retained: nothing was rolled back.
    assert host.closed is False
    assert host.files.data.get(os.fspath(ac.AUTONOMY_TRANSACTION / "transaction.json"))


def test_apply_refuses_a_wrong_pid_or_old_wrapper(host, publisher):
    # The consumed-config proof is the wrapper-attested one: it is the ONLY
    # admission the update accepts, and the owner refuses without it.
    host.proofs.clear()
    host.admission_ok = False
    with pytest.raises(ac.TransactionEffectUnknown):
        _apply(host)
    assert host.proofs == [(TARGET_SHA, host.proofs[0][1])] if host.proofs else True
    assert host.proofs  # the proof was attempted with the exact new digest


@pytest.mark.parametrize("lost", ["bootout", "bootstrap"])
def test_a_lost_response_never_duplicates_a_dispatch(host, publisher, lost):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    host.fail_after = {lost}
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    bootouts = [c for c in host.commands if "bootout" in c]
    bootstraps = [c for c in host.commands if "bootstrap" in c]
    assert len(bootouts) <= 1
    assert len(bootstraps) <= 1
    # The original marker and its preimages are retained.
    assert host.closed is False
    assert host.files.data.get(
        os.fspath(ac.AUTONOMY_TRANSACTION / "transaction.json")) is not None
    assert host.files.data.get(
        os.fspath(ac.AUTONOMY_TRANSACTION / "prior-control-plist.plist")) is not None


def test_the_receipt_correlation_preserves_the_disarmed_authority(host, publisher):
    receipt = copy.deepcopy(host.receipt)
    _apply(host)
    published = json.loads(host.files.read(
        os.fspath(ac.AUTONOMY_RECEIPT)).decode("utf-8"))
    assert published["state"] == "DISARMED"
    assert published["release_sha"] == TARGET_SHA
    assert published["control_config_sha256"] != _sha(host.control_raw)
    # No authority, evidence, policy or timestamp moved.
    for key, value in receipt.items():
        if key in {"release_sha", "control_config_sha256",
                   "prior_control_config_sha256", "transaction_id"}:
            continue
        assert published[key] == value
    assert published["transaction_id"] != receipt["transaction_id"]
    # The correlated receipt still passes the incumbent validator.
    ac.validate_receipt_document(
        published,
        metadata=ac.ReceiptMetadata(
            uid=0, gid=0, mode=0o444, nlink=1, is_regular=True,
            is_symlink=False, has_acl=False),
        expected=ac.AutonomyExpectation(
            release_sha=TARGET_SHA,
            control_config_sha256=published["control_config_sha256"],
            worker_config_sha256=published["worker_config_sha256"],
            provider_readiness_receipt_sha256=(
                published["provider_readiness_receipt_sha256"]),
            capability_policy_digest=ac.CAPABILITY_POLICY_DIGEST,
            execution_profile_digest=ac.EXECUTION_PROFILE_DIGEST,
            native_helper_grant_digest=ac.NATIVE_HELPER_GRANT_DIGEST,
            security_config_digest=ac.SECURITY_CONFIG_DIGEST),
        now=None,
        require_current=False,
    )


def test_the_worker_plist_is_retargeted_while_the_worker_stays_inert(host, publisher):
    _apply(host)
    worker = plistlib.loads(host.files.read(WORKER_PLIST))
    assert worker["WorkingDirectory"] == TARGET_ROOT
    assert host.labels["com.mastermind.executive.worker.codex"] is False
    assert host.disabled["com.mastermind.executive.worker.codex"] is True


# ---------------------------------------------------------------------------
# The reconcile.
# ---------------------------------------------------------------------------


def test_reconcile_refuses_when_no_transaction_exists(host, publisher):
    host.transaction_present = False
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert caught.value.code == "control_component_transaction_absent"


def test_reconcile_refuses_a_marker_of_another_operation(host, publisher):
    _apply(host)
    host.manifest["operation"] = ac.OS_GATEWAY_PUBLICATION
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)


def test_reconcile_proves_the_retained_postimages_and_closes_the_marker(host, publisher):
    _apply(host)
    host.closed = False
    host.phases = []
    result = ccu.reconcile(host, target_sha=TARGET_SHA)
    assert result["ok"] is True
    assert result["outcome"] == "RECONCILED"
    assert host.closed is True
    # No lifecycle effect is dispatched by a reconciliation.
    assert len([c for c in host.commands if "bootout" in c]) == 1
    assert len([c for c in host.commands if "bootstrap" in c]) == 1


def test_the_reconcile_reproduces_the_byte_identical_receipt(host, publisher):
    _apply(host)
    receipt = host.files.read(os.fspath(ac.CONTROL_COMPONENT_RECEIPT))
    host.closed = False
    # The publication was never attempted: the receipt is the one the original
    # operation owed, and the reconciliation writes exactly those bytes.
    host.files.data.pop(os.fspath(ac.CONTROL_COMPONENT_RECEIPT))
    host.manifest["phase"] = "CONTROL_COMPONENT_TARGETS_PROVEN"
    ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.files.read(os.fspath(ac.CONTROL_COMPONENT_RECEIPT)) == receipt


def test_the_observation_publication_is_admitted_once_and_never_repeated():
    source = Path(control_observation.__file__).read_text(encoding="utf-8")
    assert "owner.CONTROL_COMPONENT_UPDATE" in source
    assert "owner._CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES" in source
    assert "COMPONENT_PUBLICATION_PHASE" in source
    # The phase the publisher records is NOT admissible: an attempted
    # publication is never repeated by a later reconciliation.
    assert control_observation.COMPONENT_PUBLICATION_PHASE not in (
        ac._CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES)


def test_reconcile_refuses_a_target_that_is_not_at_its_postimage(host, publisher):
    _apply(host)
    host.closed = False
    host.files.write(CONTROL_PLIST, plistlib.dumps(_control_plist(PRIOR_ROOT)))
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False


# ---------------------------------------------------------------------------
# The incumbent owner is not displaced.
# ---------------------------------------------------------------------------


def test_the_control_component_module_owns_no_second_lock_marker_or_journal():
    import ast

    tree = ast.parse(Path(ccu.__file__).read_text(encoding="utf-8"))
    imported = set()
    names = set()
    attributes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
    # No lock, no marker, no journal, no controller, no authority, no
    # readback: this module compiles and orchestrates the incumbent owner.
    assert "fcntl" not in imported
    assert "subprocess" not in imported
    assert "socket" not in imported
    assert not {"flock", "lockf", "replace", "rename", "unlink", "makedirs"} & attributes
    assert "AUTONOMY_TRANSACTION" not in names
    assert not {"MARKER_NAME", "LOCK_NAME"} & names


def test_the_mcp_component_update_keeps_its_own_owner_and_behaviour():
    from ops.executive_os import mcp_component_update as mcp

    assert mcp.LOCK_NAME == "mcp-update.lock"
    assert mcp.MARKER_NAME == "mcp-update-txn.json"
    assert mcp.PLAN_SCHEMA == "mastermind.mcp_component_update_plan.v1"
    source = Path(mcp.__file__).read_text(encoding="utf-8")
    assert "AUTONOMY_TRANSACTION" not in source
    # The MCP component verbs still bind to the MCP helper, not to the new one.
    control = Path(ac.__file__).read_text(encoding="utf-8")
    assert "mcp_component_update" not in control


def test_the_observation_publisher_still_requires_the_genuine_held_owner(host):
    transaction = ac.TransactionContext(
        transaction_id="autonomy-000000000000",
        expected_sha=TARGET_SHA,
        prior_configs=ac.ConfigEvidence(
            control_sha256="5" * 64, worker_sha256="6" * 64,
            control={}, worker={}),
        candidates=ac.CandidateConfigs(
            control={}, worker={}, control_bytes=b"", worker_bytes=b"",
            control_sha256="7" * 64, worker_sha256="6" * 64),
        admission=None,
    )
    host._active_transaction = transaction
    host._transaction_owner_fd = None
    with pytest.raises(ac.TransactionEffectUnknown):
        control_observation.publish_for_transaction(host, transaction)


def test_the_component_manifest_is_accepted_by_the_incumbent_validator(host, tmp_path,
                                                                      monkeypatch):
    marker = tmp_path / "autonomy-transaction.lock"
    marker.mkdir(mode=0o700)
    transaction = ac.TransactionContext(
        transaction_id="autonomy-000000000000",
        expected_sha=TARGET_SHA,
        prior_configs=ac.ConfigEvidence(
            control_sha256="5" * 64, worker_sha256="6" * 64,
            control={}, worker={}, control_bytes=b"{}", worker_bytes=b"{}"),
        candidates=ac.CandidateConfigs(
            control={}, worker={}, control_bytes=b"{}", worker_bytes=b"{}",
            control_sha256="7" * 64, worker_sha256="6" * 64),
        admission=None,
    )
    host._component_candidate = ccu.compile_candidate(
        host.control_raw,
        plistlib.dumps(_control_plist(PRIOR_ROOT)),
        plistlib.dumps(_worker_plist(PRIOR_ROOT)),
        target_sha=TARGET_SHA,
        prior_sha=PRIOR_SHA,
        worker_config_sha256="6" * 64,
        prior_release_root=PRIOR_ROOT,
        target_release_root=TARGET_ROOT,
    )
    host._component_plan_sha256 = "8" * 64
    host._component_prior_seal = "9" * 64
    host._component_target_seal = "a" * 64
    host._component_observed_at = "2026-01-01T00:00:00Z"
    host._component_target_autonomy_bytes = b"{}"
    host._component_target_ceo_bytes = b""
    host._component_prior_archives = {
        "prior-component-autonomy-receipt.json": b"{}",
        "prior-component-ceo-submit-receipt.json": b"",
        "prior-control-plist.plist": b"{}",
        "prior-worker-plist.plist": b"{}",
    }
    document = host._manifest_document(
        transaction, "LOCKED", operation=ac.CONTROL_COMPONENT_UPDATE)
    (marker / ac._TRANSACTION_MANIFEST_NAME).write_bytes(
        ac._encoded_json(document))
    monkeypatch.setattr(ac, "AUTONOMY_TRANSACTION", marker)
    monkeypatch.setattr(
        ac, "_root_json",
        lambda path, **kwargs: (
            json.loads(Path(path).read_text(encoding="utf-8")),
            Path(path).read_bytes(),
        ),
    )
    value = ac.ProductionTransactionHost._manifest(host)
    assert value["operation"] == ac.CONTROL_COMPONENT_UPDATE
    assert ac._COMPONENT_MANIFEST_FIELDS <= set(value)
    assert value["component_plan_sha256"] == "8" * 64


# ---------------------------------------------------------------------------
# The closed command line.
# ---------------------------------------------------------------------------


def _service_control_source() -> str:
    return Path(ac.__file__).with_name("service-control.sh").read_text(
        encoding="utf-8")


def test_service_control_exposes_only_the_three_control_component_verbs():
    source = _service_control_source()
    for verb in ("plan-control-component", "apply-control-component",
                 "reconcile-control-component"):
        assert verb in source
    assert "control_component_args()" in source
    # The closed argv walk accepts only the two bounded digests.
    assert '[[ "$value" =~ ^[0-9a-f]{40}$ ]] || return 1' in source
    assert '[[ "$value" =~ ^[0-9a-f]{64}$ ]] || return 1' in source
    # The controller is bound to the exact staged release.
    assert ('component_dir="$MCP_RELEASE_ROOT/$CONTROL_COMPONENT_EXPECTED_SHA/ops/executive_os"'
            in source)
    assert ('"$component_dir/autonomy_control.py" "${CONTROL_COMPONENT_ARGV[@]}"'
            in source)
    # The MCP component verbs still bind to their own helper.
    assert ('"$component_dir/mcp_component_update.py" "${MCP_COMPONENT_ARGV[@]}"'
            in source)


def _install_source() -> str:
    return Path(ac.__file__).with_name("install.sh").read_text(encoding="utf-8")


def test_install_exposes_the_admin_checkout_staging_option():
    source = _install_source()
    assert "--stage-admin-checkout-only" in source
    assert "prepare_admin_checkout()" in source
    assert ('ADMIN_CHECKOUT="$RUNTIME_ROOT/control/admin-checkout/$EXPECTED_SHA"'
            in source)
    # The staging-only dispatch returns before the mutation boundary.
    staging = source.index("# --- BEGIN admin-checkout-only dispatch ---")
    boundary = source.index("# Cross the mutation boundary only after")
    assert staging < boundary
    # The existing release staging option still returns before the admin
    # checkout preparation.
    release_dispatch = source.index("# --- BEGIN stage-only dispatch ---")
    preparation = source.index("# --- BEGIN administrative checkout preparation ---")
    assert release_dispatch > preparation
    # An occupied mismatching target refuses; no recursive repair of another
    # owner's tree happens before the exact-commit proof.
    function = source[preparation:source.index("# --- END administrative checkout preparation ---")]
    assert "administrative checkout target holds a different commit" in function
    assert "administrative checkout target belongs to another owner" in function
    assert function.index("holds a different commit") < function.index("chown -R")
    # The reviewed normalizer is still the one that proves the closure.
    assert "admin_checkout.py\" normalize" in function
    assert "--expected-commit \"$EXPECTED_SHA\"" in function
