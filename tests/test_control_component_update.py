"""Offline invariants for the owned Control component update.

Source tests only: no installed release, no launchd, no root, no installed file
and no administrative checkout is read or written.  The composition is driven
against a hermetic stand-in for the one installed Executive host, so every
refusal path is exercised with zero cutover and every crash gap of the happy
path is exercised without dispatching a duplicate effect.

The production QUALIFIERS are not replaced by a stub: the administrative
checkout is proved by the real production method against a real hermetic Git
repository, and the receipt, manifest, compare-and-swap and effect-order
discipline is the production one.

The pinned interpreter is the ONE documented exception, and the exception is
deliberate and narrow: the installed peer's two leaf runtime entry points
(``installed._verify_python_runtime`` and
``installed._recheck_python_runtime``) inspect the real installed interpreter
binaries, their version, their code signature and their whole ancestor
closure on this host, so they are stood in for.  Everything the component
itself owns around them IS the production code: the retained observation, the
ONE budget it was observed under, and the recheck of that same observation
under that same budget immediately before the first effect.

Only the leaf host observations (launchd, the process table, the installed
release tree, the installed files) are stood in for, so a defect inside a
qualification cannot hide behind an override.
"""

import copy
import hashlib
import json
import os
import plistlib
import subprocess
import tempfile
from pathlib import Path

import pytest

from control_plane import executive_installed_peer as installed
from ops.executive_os import autonomy_control as ac
from ops.executive_os import control_component_update as ccu
from ops.executive_os import control_observation
from ops.executive_os import prepare_control_successor as prepare
from ops.executive_os.capacity_broker_topology import CONTROL_UID

try:  # the incumbent's real schema fixture is reused, never redefined
    from tests.test_prepare_control_successor import control_input  # noqa: F401
except ImportError:  # pragma: no cover - the flat test root is equally valid
    from test_prepare_control_successor import control_input  # noqa: F401


def _git(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=None if cwd is None else os.fspath(cwd),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False, timeout=30,
        env=None if env is None else {**os.environ, **env})
    if completed.returncode != 0:
        raise RuntimeError("git observation failed")
    return completed.stdout.decode("utf-8").strip()


# The fixed identity of the hermetic administrative checkout.  The commit is
# built from a fixed tree and fixed author/committer coordinates, so its
# object id is the same on every machine: the production owner compares the
# checkout HEAD against the target commit exactly.
_COMMIT_ENVIRONMENT = {
    "GIT_AUTHOR_NAME": "Component Test",
    "GIT_AUTHOR_EMAIL": "component@example.invalid",
    "GIT_COMMITTER_NAME": "Component Test",
    "GIT_COMMITTER_EMAIL": "component@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
}


def _build_admin_checkout(root: Path) -> tuple[Path, str]:
    """One real, local, credential-free Git checkout of the exact target."""

    staging = root / "staging"
    staging.mkdir(parents=True)
    _git("init", "-q", "--", os.fspath(staging))
    (staging / "source.txt").write_text("control component\n", encoding="utf-8")
    _git("add", "source.txt", cwd=staging)
    tree = _git("write-tree", cwd=staging)
    commit = _git("commit-tree", tree, "-m", "target", cwd=staging,
                  env=_COMMIT_ENVIRONMENT)
    _git("update-ref", "refs/heads/component-target", commit, cwd=staging)
    _git("symbolic-ref", "HEAD", "refs/heads/component-target", cwd=staging)
    _git("reset", "--hard", "-q", commit, cwd=staging)
    final = root / commit
    os.rename(staging, final)
    return final, commit


_ADMIN_ROOT = Path(tempfile.mkdtemp(prefix="c14-admin-checkout-"))
_ADMIN_CHECKOUT, TARGET_SHA = _build_admin_checkout(_ADMIN_ROOT)

PRIOR_SHA = "80f384b8f58b7ca46422d9783aa5c0613c7bf4b2"
PRIOR_ROOT = os.fspath(ac.SYSTEM_ROOT / "releases" / PRIOR_SHA)
TARGET_ROOT = os.fspath(ac.SYSTEM_ROOT / "releases" / TARGET_SHA)
MACRO_ROOT = "/approved/retained/Macro"
CONTROL_CONFIG = os.fspath(ac.CONTROL_CONFIG)
WORKER_CONFIG = os.fspath(ac.WORKER_CONFIG)
CONTROL_PLIST = os.fspath(ac.CONTROL_PLIST)
WORKER_PLIST = os.fspath(ac.WORKER_PLIST)
AUTONOMY_RECEIPT = os.fspath(ac.AUTONOMY_RECEIPT)
CEO_SUBMIT_RECEIPT = os.fspath(ac.CEO_SUBMIT_RECEIPT)
COMPONENT_RECEIPT = os.fspath(ac.CONTROL_COMPONENT_RECEIPT)
CONTROL = "com.mastermind.executive.control"
WORKER = "com.mastermind.executive.worker.codex"


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
        "Label": CONTROL,
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
        "Label": WORKER,
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


def _disarmed_ceo_receipt() -> bytes:
    """One complete existing DISARMED CEO-submit receipt.

    The incumbent validator is the only authority on its shape, so the
    fixture is built from the incumbent's own projection digest rather than
    from a hand-written digest.
    """

    projection = {
        "ceo_submit_armed": False,
        "ceo_ingress_app_peer_uid": 501,
        "ceo_ingress_app_armed": False,
        "ceo_ingress_peer_uid": 502,
        "ceo_ingress_socket_path": "/var/run/mastermind/ceo-ingress.sock",
        "ceo_ingress_launchd_socket_name": "com.mastermind.executive.ceo",
        "ceo_ingress_app_macro_root": MACRO_ROOT,
        "coo_autonomy_armed": False,
        "coo_operator_harness_armed": False,
        "release_sha": PRIOR_SHA,
        "installed_sha": PRIOR_SHA,
        "app_peer_user": "_mastermind_ceo_app",
        "app_binding_valid": True,
        "app_acl_valid": True,
        "app_topology_valid": True,
        "worker_operator_harness_armed": False,
        "worker_config_sha256": "5" * 64,
        "transaction_id": "autonomy-000000000000",
    }
    receipt = {
        "schema_version": ac.CEO_SUBMIT_RECEIPT_SCHEMA,
        "state": "CEO_SUBMIT_DISARMED",
        "operation": "CEO_SUBMIT_DISARM",
        "projection": projection,
        "projection_digest": ac.ceo_submit_projection_digest(projection),
        "transaction_id": "autonomy-000000000000",
        "observed_at": "2026-01-01T00:00:00Z",
        "tool_version": ac.TOOL_VERSION,
    }
    assert ac.validate_ceo_submit_receipt_document(receipt, armed=False)
    return ac._encoded_json(receipt)


class _NoAmbientPath:
    """One installed path that refuses every ambient existence probe.

    An ``exists()`` or ``is_symlink()`` probe bypasses the qualified receipt
    owner: it observes whatever the live host happens to carry instead of the
    sealed bytes, and it cannot tell an absent receipt from an unreadable
    one.  This stand-in turns such a probe into a hard test failure.
    """

    def __init__(self, path) -> None:
        self._path = path

    def __fspath__(self) -> str:
        return os.fspath(self._path)

    def exists(self) -> bool:
        raise AssertionError("ambient existence probe on an installed receipt")

    def is_symlink(self) -> bool:
        raise AssertionError("ambient symlink probe on an installed receipt")


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


class _Passwd:
    """The identity source: the test principal owns the hermetic checkout."""

    @staticmethod
    def getpwnam(name: str):
        return type("_Entry", (), {"pw_uid": os.geteuid()})()


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
    """A hermetic stand-in for the one installed Executive host.

    Only the LEAF host observations are stood in for: launchd, the process
    table, the installed release tree and the installed files.  Every
    qualification method of the component -- the administrative checkout, the
    interpreter, the mode derivation, the receipt preimages, the compare-and-
    swap and the manifest -- is the production one.
    """

    def __init__(self, control: dict, worker: dict, *, files: FakeFiles | None = None):
        super().__init__()
        self.files = files if files is not None else FakeFiles()
        self.control = control
        self.worker = worker
        self.control_raw = _canonical(control)
        self.worker_raw = _canonical(worker)
        self.labels = {CONTROL: True, WORKER: False}
        self.disabled = {CONTROL: False, WORKER: True}
        self.commands: list[list[str]] = []
        self.phases: list[str] = []
        self.proofs: list[tuple[str, str]] = []
        self.publications: list[str] = []
        self.closed = False
        self.manifest: dict = {}
        self.transaction_present = False
        self.quiescent = True
        self.admission_ok = True
        self.service_uids_quiescent = True
        self.service_uid_failures = 0
        self.census_observed_at: list[int] = []
        self.release_seals = {PRIOR_SHA: "1" * 64, TARGET_SHA: "2" * 64}
        self.receipt = _disarmed_receipt(
            _sha(self.control_raw), _sha(self.worker_raw))
        self.crash_at: int | None = None
        self.fail_after: set[str] = set()
        # When true, the CLOSED manifest reader is the production one, over the
        # same in-memory installed file.  The fake reader is only a shortcut
        # for the happy path; a malformed retained manifest must be classified
        # by the real reader.
        self.production_manifest = False
        self.interpreter_calls: dict = {"verify": [], "recheck": []}
        self.files.write(CONTROL_PLIST, plistlib.dumps(_control_plist(PRIOR_ROOT)))
        self.files.write(WORKER_PLIST, plistlib.dumps(_worker_plist(PRIOR_ROOT)))
        self.files.write(CONTROL_CONFIG, self.control_raw)
        self.files.write(WORKER_CONFIG, self.worker_raw)
        self.files.write(AUTONOMY_RECEIPT, ac._encoded_json(self.receipt))
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

    # -- the leaf host observations -------------------------------------------

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
        """The ACTUAL installed configurations, as the incumbent owner reads them.

        The installed Control configuration is replaced by the operation, so
        the qualified configuration owner must report what is on disk now and
        not the state it had before the update.  ``self.control`` and
        ``self.worker`` keep the PRIOR installed state for the assertions
        that compare against it.
        """

        control_raw = self.files.read(CONTROL_CONFIG)
        worker_raw = self.files.read(WORKER_CONFIG)
        control = json.loads(control_raw.decode("utf-8"))
        worker = json.loads(worker_raw.decode("utf-8"))
        return (
            control,
            worker,
            _sha(control_raw),
            _sha(worker_raw),
            control_raw,
            worker_raw,
        )

    def _component_release_seal(self, sha: str, *, target: bool = False) -> str:
        value = self.release_seals.get(sha)
        if value is None:
            raise ac.ComponentUpdateRefused("control_component_release_seal_invalid")
        return value

    def require_transaction_absent(self) -> None:
        if self.transaction_present:
            raise ac.ComponentUpdateRefused("control_component_transaction_occupied")

    def require_runtime_quiescent(self, config) -> None:
        if not self.quiescent:
            raise ac.ComponentUpdateRefused("control_component_owner_not_quiescent")

    def require_service_uids_quiescent(self) -> None:
        self.census_observed_at.append(len(self.commands))
        if self.service_uid_failures > 0:
            self.service_uid_failures -= 1
            raise ac.ArmAdmissionError("service_uid_process_live")
        if not self.service_uids_quiescent:
            raise ac.ArmAdmissionError("service_uid_process_unknown")

    def _read_launchd_disabled_override(self, target_label: str, *,
                                       allow_absent: bool = False):
        value = self.disabled.get(target_label)
        if value is None:
            if allow_absent:
                return None
            raise ac.TransactionEffectUnknown()
        return value

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
        if self.production_manifest:
            # The incumbent's own closed manifest reader, over the same
            # in-memory installed file.
            return super()._manifest()
        return dict(self.manifest)

    def _persist_phase(self, transaction, phase: str, *, operation=None) -> None:
        operation = operation or str(self.manifest.get("operation"))
        value = self._manifest_document(transaction, phase, operation=operation)
        for group in (ac._COEXISTENCE_MANIFEST_FIELDS, ac._COMPONENT_MANIFEST_FIELDS):
            for key in group:
                if key in self.manifest:
                    value[key] = self.manifest[key]
        self.manifest = value
        # The retained marker file follows the retained phase, so the
        # production manifest reader sees exactly the same document.
        self.files.data[
            os.fspath(ac.AUTONOMY_TRANSACTION / ac._TRANSACTION_MANIFEST_NAME)
        ] = ac._encoded_json(value)
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
            self.labels[CONTROL] = False
        if "bootstrap" in argv:
            self.labels[CONTROL] = True
        if "enable" in argv:
            self.disabled[CONTROL] = False

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




def _fake_component_run(argv, *, timeout, stdin_bytes=None):
    """Run the real Git command the production owner asks for.

    The fixed Control-principal owner prefix is dropped -- the hermetic
    checkout is owned by the test principal -- and the real Git binary runs
    the real command, so the production qualification is exercised against
    real Git output.
    """

    command = list(argv)
    index = command.index("/usr/bin/git")
    if stdin_bytes is None:
        completed = subprocess.run(
            command[index:], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=timeout)
    else:
        completed = subprocess.run(
            command[index:], input=stdin_bytes, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=timeout)
    return completed.returncode, completed.stdout


class _RuntimeObservation:
    """The installed peer's own runtime observation, as a stand-in."""

    def __init__(self):
        self.ancestor_identities = ()


@pytest.fixture
def host(control_input, monkeypatch, tmp_path):
    control = copy.deepcopy(control_input)
    control["ceo_ingress_app_macro_root"] = MACRO_ROOT
    worker = {"operator_harness_armed": False}
    host_obj = FakeHost(control, worker)

    def fake_atomic_file(path, payload, *, mode, uid, gid, replace):
        host_obj.files.write(path, payload, replace=replace)

    def fake_read_root_file(path, *, modes, uid=0, gid=None):
        return host_obj.files.read(path), _Info()

    def fake_receipt_metadata(path):
        return ac.ReceiptMetadata(
            uid=0, gid=0, mode=0o444, nlink=1, is_regular=True,
            is_symlink=False, has_acl=False)

    def fake_verify_python_runtime(budget):
        host_obj.interpreter_calls["verify"].append(budget)
        return _RuntimeObservation()

    def fake_recheck_python_runtime(observation, budget):
        host_obj.interpreter_calls["recheck"].append(
            (observation, budget, len(host_obj.commands)))

    monkeypatch.setattr(ac, "_atomic_file", fake_atomic_file)
    monkeypatch.setattr(ac, "_read_root_file", fake_read_root_file)
    monkeypatch.setattr(ac, "_receipt_metadata", fake_receipt_metadata)
    monkeypatch.setattr(ac, "grp", _Groups)
    monkeypatch.setattr(ac, "pwd", _Passwd)
    monkeypatch.setattr(ac, "_CONTROL_ADMIN_CHECKOUT_ROOT", _ADMIN_ROOT)
    monkeypatch.setattr(ac, "_component_run", _fake_component_run)
    monkeypatch.setattr(
        installed, "_verify_python_runtime", fake_verify_python_runtime)
    monkeypatch.setattr(
        installed, "_recheck_python_runtime", fake_recheck_python_runtime)
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


def test_the_two_modes_bind_different_closed_precondition_and_effect_lists():
    assert ccu.COMPONENT_MODES == ("live", "offline")
    assert set(ccu.LIVE_PRECONDITIONS) != set(ccu.OFFLINE_PRECONDITIONS)
    assert "control_registered" in ccu.LIVE_PRECONDITIONS
    assert "control_absent" in ccu.OFFLINE_PRECONDITIONS
    assert "worker_absent" in ccu.LIVE_PRECONDITIONS
    assert "worker_absent" in ccu.OFFLINE_PRECONDITIONS
    # The live mode keeps the incumbent bootout; the offline mode has NO
    # bootout to record and exactly one enable instead.
    assert ccu.LIVE_EFFECTS[0].startswith("bootout ")
    assert not any(effect.startswith("bootout ") for effect in ccu.OFFLINE_EFFECTS)
    assert [effect for effect in ccu.OFFLINE_EFFECTS if effect.startswith("enable ")]
    assert ccu.effects_for_mode("live") == ccu.LIVE_EFFECTS
    assert ccu.effects_for_mode("offline") == ccu.OFFLINE_EFFECTS
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.effects_for_mode("maintenance")
    assert caught.value.code == "component_mode_invalid"


def test_the_offline_mode_refuses_a_preimage_that_contradicts_the_mode():
    candidate = ccu.Candidate(
        target_sha=TARGET_SHA,
        prior_sha=PRIOR_SHA,
        control_config_before=b"{}",
        control_config_after=b"{}",
        control_plist_before=b"{}",
        control_plist_after=b"{}",
        worker_plist_before=b"{}",
        worker_plist_after=b"{}",
        worker_config_sha256="3" * 64,
        changed_control_fields=("proof_base_sha",),
    )
    receipts = {
        name: ccu.ReceiptPreimage(path="/x", present=True, sha256="0" * 64)
        for name in ccu.RECEIPT_PREIMAGE_NAMES
    }
    # The offline mode requires the Control to be explicitly disabled.
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.plan_document(
            candidate, mode="offline",
            preconditions={key: True for key in ccu.OFFLINE_PRECONDITIONS},
            prior_release_manifest_sha256="1" * 64,
            target_release_manifest_sha256="2" * 64,
            admin_checkout_commit=TARGET_SHA,
            receipts=receipts,
            launchd_disabled={"control": False, "worker": True},
        )
    assert caught.value.code == "launchd_preimage_invalid"
    # The Worker is disabled in BOTH modes.
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.plan_document(
            candidate, mode="live",
            preconditions={key: True for key in ccu.LIVE_PRECONDITIONS},
            prior_release_manifest_sha256="1" * 64,
            target_release_manifest_sha256="2" * 64,
            admin_checkout_commit=TARGET_SHA,
            receipts=receipts,
            launchd_disabled={"control": False, "worker": False},
        )
    assert caught.value.code == "launchd_preimage_invalid"


def test_the_plan_binds_receipt_presence_and_exact_raw_digests(host):
    document = ccu.plan(host, target_sha=TARGET_SHA)["plan"]
    receipts = document["receipts"]
    assert set(receipts) == set(ccu.RECEIPT_PREIMAGE_NAMES)
    assert receipts["authority_receipt"]["present"] is True
    assert receipts["authority_receipt"]["before_sha256"] == _sha(
        host.files.read(AUTONOMY_RECEIPT))
    assert receipts["ceo_submit_receipt"]["present"] is False
    assert receipts["component_receipt"]["present"] is False
    assert document["launchd_disabled"] == {"control": False, "worker": True}
    assert document["mode"] == "live"


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
    assert set(document["preconditions"]) == set(ccu.LIVE_PRECONDITIONS)
    assert all(state is True for state in document["preconditions"].values())
    assert document["effects"] == list(ccu.EFFECTS if hasattr(ccu, "EFFECTS")
                                       else ccu.LIVE_EFFECTS)
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


def test_plan_digest_is_bound_to_the_mode_and_the_launchd_preimages(host):
    document = _plan(host)["plan"]
    changed = copy.deepcopy(document)
    changed["mode"] = "offline"
    assert ccu.plan_digest(changed) != ccu.plan_digest(document)
    changed = copy.deepcopy(document)
    changed["launchd_disabled"]["worker"] = False
    assert ccu.plan_digest(changed) != ccu.plan_digest(document)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda h: h.labels.__setitem__(WORKER, True),
         "control_component_worker_live"),
        (lambda h: h.disabled.__setitem__(WORKER, False),
         "control_component_worker_not_disabled"),
        (lambda h: h.disabled.__setitem__(WORKER, None),
         "control_component_worker_not_disabled"),
        (lambda h: setattr(h, "transaction_present", True),
         "control_component_transaction_occupied"),
        (lambda h: setattr(h, "quiescent", False),
         "control_component_owner_not_quiescent"),
        (lambda h: h.release_seals.pop(TARGET_SHA),
         "control_component_release_seal_invalid"),
        (lambda h: h.files.data.pop(AUTONOMY_RECEIPT),
         "control_component_authority_receipt_invalid"),
        (lambda h: h.files.write(AUTONOMY_RECEIPT, ac._encoded_json(
            dict(h.receipt, state="ARMED"))),
         "control_component_authority_receipt_armed"),
        # A Control that is absent but not explicitly disabled matches
        # NEITHER closed mode.
        (lambda h: h.labels.__setitem__(CONTROL, False),
         "control_component_control_state_mixed"),
        # A Control that is registered AND explicitly disabled matches
        # NEITHER closed mode either.
        (lambda h: h.disabled.__setitem__(CONTROL, True),
         "control_component_control_state_mixed"),
    ],
)
def test_every_refusal_is_pre_effect_with_zero_cutover(host, mutate, code):
    mutate(host)
    # A mutation that installs a fixture state is not an effect of the
    # operation: only what the operation itself writes is observed.
    host.files.writes.clear()
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == code
    assert host.commands == []
    assert host.files.writes == []
    assert host.proofs == []
    assert host.closed is False


def test_an_unqualified_interpreter_refuses_before_any_effect(host, monkeypatch):
    def refuse(budget):
        raise installed._refuse("SERVICE_RUNTIME_DIGEST_MISMATCH")

    monkeypatch.setattr(installed, "_verify_python_runtime", refuse)
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_interpreter_unqualified"
    assert host.commands == []
    assert host.files.writes == []


def test_an_armed_control_flag_is_an_authority_refusal_not_a_transport_one(host):
    # ``ceo_ingress_app_armed`` is transport admission, never CEO-submit
    # authority: it stays armed and the plan still succeeds.
    assert host.control["ceo_ingress_app_armed"] is True
    assert _plan(host)["ok"] is True
    # The INSTALLED configuration carries the armed flag; the qualified
    # configuration owner reads it from the installed file.
    host.files.write(CONTROL_CONFIG, _canonical(
        dict(host.control, ceo_submit_armed=True)))
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
    assert host.labels[WORKER] is False
    assert not any("worker" in " ".join(command) for command in host.commands)


def test_apply_retargets_both_plists_to_the_target_release(host, publisher):
    _apply(host)
    control = plistlib.loads(host.files.read(CONTROL_PLIST))
    worker = plistlib.loads(host.files.read(WORKER_PLIST))
    assert control["WorkingDirectory"] == TARGET_ROOT
    assert worker["WorkingDirectory"] == TARGET_ROOT
    assert control["Label"] == CONTROL
    assert worker["Label"] == WORKER
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
    assert host.labels[WORKER] is False
    assert host.disabled[WORKER] is True


# ---------------------------------------------------------------------------
# The bound preimages and the receipt compare-and-swap.
# ---------------------------------------------------------------------------


def test_the_archive_holds_the_exact_original_receipt_bytes(host, publisher):
    # The installed authority receipt is NOT canonically serialised.
    original = json.dumps(host.receipt, indent=4).encode("utf-8")
    host.files.write(AUTONOMY_RECEIPT, original)
    _apply(host)
    archived = host.files.read(
        os.fspath(ac.AUTONOMY_TRANSACTION / "prior-component-autonomy-receipt.json"))
    assert archived == original
    assert archived != ac._encoded_json(host.receipt)
    # The manifest binds the digest of the EXACT prior bytes.
    assert host.manifest["component_prior_autonomy_receipt_sha256"] == _sha(original)
    assert host.manifest["component_prior_autonomy_receipt_present"] is True


def test_a_receipt_that_moved_after_the_seal_is_never_overwritten(host, publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    # The authority receipt changes between the plan and the apply.
    host.files.write(AUTONOMY_RECEIPT, ac._encoded_json(
        dict(host.receipt, transaction_id="autonomy-999999999999")))
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert caught.value.code == "control_component_plan_digest_mismatch"
    assert host.commands == []
    assert host.closed is False


def test_a_receipt_that_moves_after_the_marker_is_never_overwritten(host, publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    original = ac._encoded_json(host.receipt)

    class _Moving(ac.ProductionControlComponentHost):
        pass

    host_obj = host
    original_publish = host_obj._publish_control_component_receipts

    def move_then_publish(transaction):
        # A later actor replaces the receipt between the seal and the
        # publication.
        host_obj.files.write(AUTONOMY_RECEIPT, b'{"moved": true}')
        return original_publish(transaction)

    host_obj._publish_control_component_receipts = move_then_publish
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    # The moved receipt was NOT overwritten.
    assert host_obj.files.read(AUTONOMY_RECEIPT) == b'{"moved": true}'
    assert host_obj.closed is False
    assert original != b'{"moved": true}'


def test_the_component_receipt_is_never_overwritten_when_it_moved(host, publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    host.files.write(COMPONENT_RECEIPT, b'{"unbound": true}')
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert caught.value.code == "control_component_plan_digest_mismatch"
    assert host.files.read(COMPONENT_RECEIPT) == b'{"unbound": true}'
    assert host.commands == []


# ---------------------------------------------------------------------------
# The interpreter qualification and the stopped boundary.
# ---------------------------------------------------------------------------


def test_the_interpreter_is_qualified_and_rechecked_before_the_first_effect(
        host, publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    host.interpreter_calls["verify"].clear()
    host.interpreter_calls["recheck"].clear()
    ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    verify = host.interpreter_calls["verify"]
    recheck = host.interpreter_calls["recheck"]
    assert len(verify) == 1
    assert len(recheck) == 1
    # The SAME budget is used for the observation and the recheck.
    assert recheck[0][1] is verify[0]
    assert isinstance(verify[0], installed._Budget)
    # The recheck happened before the first dispatched effect.
    assert recheck[0][2] == 0
    assert host.commands


def test_the_reconcile_qualifies_the_runtime_freshly(host, publisher):
    _apply(host)
    host.interpreter_calls["verify"].clear()
    host.interpreter_calls["recheck"].clear()
    host.closed = False
    ccu.reconcile(host, target_sha=TARGET_SHA)
    assert len(host.interpreter_calls["verify"]) == 1
    assert len(host.interpreter_calls["recheck"]) == 1
    assert host.interpreter_calls["recheck"][0][1] is (
        host.interpreter_calls["verify"][0])


def test_the_stopped_boundary_proves_the_service_uid_census(host, publisher):
    _apply(host)
    # The census is observed at the stopped boundary, after the bootout and
    # before the first publication.
    assert host.census_observed_at
    bootout = [c for c in host.commands if "bootout" in c]
    assert host.census_observed_at[0] == host.commands.index(bootout[0]) + 1


def test_a_live_service_uid_at_the_stopped_boundary_refuses(host, publisher,
                                                            monkeypatch):
    monkeypatch.setattr(ac, "_CONTROL_COMPONENT_UID_CENSUS_TIMEOUT", 0.0)
    host.service_uids_quiescent = False
    with pytest.raises(ac.TransactionEffectUnknown):
        _apply(host)
    # The transaction is retained; nothing was rolled back.
    assert host.closed is False
    assert host.files.data.get(
        os.fspath(ac.AUTONOMY_TRANSACTION / "transaction.json")) is not None


def test_the_stopped_boundary_waits_within_one_bounded_window(host, publisher,
                                                              monkeypatch):
    monkeypatch.setattr(ac, "_CONTROL_COMPONENT_UID_CENSUS_TIMEOUT", 5.0)
    host.service_uid_failures = 1
    _apply(host)
    # The census was observed again after the first live observation.
    assert len(host.census_observed_at) >= 2
    assert host.closed is True


# ---------------------------------------------------------------------------
# The offline mode.
# ---------------------------------------------------------------------------


def _offline(host_obj):
    """The closed offline input state: both absent and explicitly disabled."""

    host_obj.labels[CONTROL] = False
    host_obj.disabled[CONTROL] = True
    host_obj.labels[WORKER] = False
    host_obj.disabled[WORKER] = True
    return host_obj


def test_the_offline_mode_is_selected_and_bound_by_the_plan(host):
    _offline(host)
    document = ccu.plan(host, target_sha=TARGET_SHA)["plan"]
    assert document["mode"] == "offline"
    assert document["launchd_disabled"] == {"control": True, "worker": True}
    assert set(document["preconditions"]) == set(ccu.OFFLINE_PRECONDITIONS)
    assert document["effects"] == list(ccu.OFFLINE_EFFECTS)


def test_the_offline_mode_skips_the_bootout_and_records_no_bootout_history(
        host, publisher):
    _offline(host)
    result = _apply(host)
    assert result["outcome"] == "UPDATED"
    assert not any("bootout" in " ".join(command) for command in host.commands)
    assert "CONTROL_BOOTOUT_RECORDED" not in host.phases
    assert "CONTROL_ABSENT_PROVEN" in host.phases
    assert host.closed is True


def test_the_offline_mode_enables_once_before_the_single_bootstrap(host, publisher):
    _offline(host)
    _apply(host)
    enables = [c for c in host.commands if "enable" in c]
    bootstraps = [c for c in host.commands if "bootstrap" in c]
    assert len(enables) == 1
    assert len(bootstraps) == 1
    assert host.commands.index(enables[0]) < host.commands.index(bootstraps[0])
    assert host.phases.index("CONTROL_ENABLE_RECORDED") < host.phases.index(
        "CONTROL_BOOTSTRAP_RECORDED")
    assert "CONTROL_ENABLED_PROVEN" in host.phases


def test_the_offline_mode_preserves_the_worker(host, publisher):
    _offline(host)
    before = host.files.read(WORKER_CONFIG)
    _apply(host)
    assert host.files.read(WORKER_CONFIG) == before
    assert host.labels[WORKER] is False
    assert host.disabled[WORKER] is True
    assert not any(WORKER in " ".join(command) for command in host.commands)


def test_the_offline_mode_refuses_a_mixed_control_boundary(host):
    # Absent but NOT explicitly disabled: neither closed mode.
    host.labels[CONTROL] = False
    host.disabled[CONTROL] = False
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_control_state_mixed"
    assert host.commands == []


def test_the_offline_mode_refuses_a_registered_and_disabled_control(host):
    host.labels[CONTROL] = True
    host.disabled[CONTROL] = True
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_control_state_mixed"
    assert host.commands == []


def test_an_unknown_worker_state_refuses_before_any_effect(host):
    host.disabled[WORKER] = None
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_worker_not_disabled"
    assert host.commands == []


def test_an_absent_launchd_row_is_the_default_enabled_state(host, publisher):
    # The Control label carries no persistent override row at all: launchd's
    # default is enabled, which is the live mode.  The row's ABSENCE is not
    # an unknown state, and it is not the same state as being disabled.
    host.disabled[CONTROL] = None
    document = ccu.plan(host, target_sha=TARGET_SHA)["plan"]
    assert document["mode"] == "live"
    assert document["launchd_disabled"]["control"] is False
    _apply(host)
    assert host.closed is True


def test_a_lost_enable_response_retains_the_original_transaction(host, publisher):
    _offline(host)
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    host.fail_after = {"enable"}
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert len([c for c in host.commands if "enable" in c]) == 1
    assert host.closed is False
    assert host.files.data.get(
        os.fspath(ac.AUTONOMY_TRANSACTION / "transaction.json")) is not None


# ---------------------------------------------------------------------------
# A refusal after the effect boundary.
# ---------------------------------------------------------------------------


def test_a_refusal_after_the_effect_boundary_retains_the_transaction(host,
                                                                    publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    original = host._component_receipt_cas

    def refuse_cas(path, *, prior_field):
        raise ac.ComponentUpdateRefused("control_component_receipt_preimage_mismatch")

    host._component_receipt_cas = refuse_cas
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert caught.value.code == "control_component_receipt_preimage_mismatch"
    # The original transaction is retained and the phase is named: this is
    # NOT a zero-effect refusal.
    assert caught.value.incomplete is True
    assert caught.value.transaction_id is not None
    assert caught.value.phase is not None
    assert host.closed is False
    assert host.files.data.get(
        os.fspath(ac.AUTONOMY_TRANSACTION / "transaction.json")) is not None
    assert original is not refuse_cas


def test_the_target_source_is_rechecked_under_the_claimed_transaction(host,
                                                                      publisher,
                                                                      monkeypatch):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    original_create = host._create_marker

    def create_then_move(transaction, *, operation):
        original_create(transaction, operation=operation)
        # The administrative checkout moves after the marker was claimed.
        monkeypatch.setattr(ac, "_CONTROL_ADMIN_CHECKOUT_ROOT", _ADMIN_ROOT / "gone")

    host._create_marker = create_then_move
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert caught.value.code == "control_component_admin_checkout_unavailable"
    # The original transaction is retained and no effect was dispatched.
    assert caught.value.incomplete is True
    assert host.commands == []
    assert host.closed is False


def test_the_target_seal_is_rechecked_under_the_claimed_transaction(host,
                                                                   publisher):
    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]
    original_create = host._create_marker

    def create_then_move(transaction, *, operation):
        original_create(transaction, operation=operation)
        host.release_seals[TARGET_SHA] = "9" * 64

    host._create_marker = create_then_move
    # The sealed target release moved after the marker was claimed: the
    # original transaction is retained and the outcome is uncertain.
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.apply(host, target_sha=TARGET_SHA, plan_sha256=plan_sha256)
    assert host.commands == []
    assert host.closed is False


def test_the_cli_reports_a_post_effect_refusal_as_incomplete(host, capsys):
    import argparse
    from datetime import datetime, timezone

    plan_sha256 = ccu.plan(host, target_sha=TARGET_SHA)["plan_sha256"]

    def refuse_cas(path, *, prior_field):
        raise ac.ComponentUpdateRefused("control_component_receipt_preimage_mismatch")

    host._component_receipt_cas = refuse_cas
    args = argparse.Namespace(
        command="apply-control-component", expected_sha=TARGET_SHA,
        plan_sha256=plan_sha256)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "INCOMPLETE"
    assert document["code"] == "control_component_receipt_preimage_mismatch"
    assert document["transaction_id"]
    assert document["phase"]


def test_the_cli_reports_a_zero_effect_refusal_as_refused(host, capsys):
    import argparse
    from datetime import datetime, timezone

    host.labels[WORKER] = True
    args = argparse.Namespace(
        command="plan-control-component", expected_sha=TARGET_SHA,
        plan_sha256="0" * 64)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    assert code == 1
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "REFUSED"
    assert document["code"] == "control_component_worker_live"
    assert "phase" not in document


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


def test_reconcile_proves_the_retained_postimages_and_closes_the_marker(host,
                                                                      publisher):
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


def test_reconcile_refuses_a_target_whose_seal_moved(host, publisher):
    _apply(host)
    host.closed = False
    host.release_seals[TARGET_SHA] = "9" * 64
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False


def test_reconcile_refuses_a_target_whose_admin_checkout_moved(host, publisher,
                                                              monkeypatch):
    _apply(host)
    host.closed = False
    monkeypatch.setattr(
        ac, "_CONTROL_ADMIN_CHECKOUT_ROOT", ac._CONTROL_ADMIN_CHECKOUT_ROOT / "gone")
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False


def test_reconcile_refuses_a_retained_receipt_that_moved(host, publisher):
    _apply(host)
    host.closed = False
    host.files.write(AUTONOMY_RECEIPT, b'{"moved": true}')
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False


def test_reconcile_refuses_a_worker_that_came_back(host, publisher):
    _apply(host)
    host.closed = False
    host.labels[WORKER] = True
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False


def test_reconcile_refuses_a_component_receipt_that_is_not_there(host, publisher):
    _apply(host)
    host.closed = False
    host.files.data.pop(os.fspath(ac.CONTROL_COMPONENT_RECEIPT))
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False


def test_reconcile_refuses_a_component_receipt_that_moved(host, publisher):
    _apply(host)
    host.closed = False
    host.files.write(COMPONENT_RECEIPT, b'{"unbound": true}')
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False
    # The unbound later receipt was not overwritten.
    assert host.files.read(COMPONENT_RECEIPT) == b'{"unbound": true}'


def test_reconcile_never_replays_a_recorded_lifecycle_action(host, publisher):
    _apply(host)
    host.closed = False
    before = [list(command) for command in host.commands]
    ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.commands == before


def test_reconcile_refuses_an_unqualified_runtime(host, publisher, monkeypatch):
    _apply(host)
    host.closed = False

    def refuse(budget):
        raise installed._refuse("SERVICE_RUNTIME_DIGEST_MISMATCH")

    monkeypatch.setattr(installed, "_verify_python_runtime", refuse)
    # The original transaction is retained and nothing is replayed: a
    # reconciliation that cannot freshly qualify the runtime is uncertain.
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


def test_the_component_manifest_is_accepted_by_the_incumbent_validator(host,
                                                                      tmp_path,
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
    host._component_target_component_bytes = b"{}"
    host._component_mode_bound = ac._COMPONENT_LIVE_MODE
    host._component_control_launchd_disabled = False
    host._component_worker_launchd_disabled = True
    host._component_prior_archives = {
        "prior-component-autonomy-receipt.json": b"{}",
        "prior-component-ceo-submit-receipt.json": b"",
        "prior-component-receipt.json": b"",
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
    assert value["component_mode"] == ac._COMPONENT_LIVE_MODE


def test_the_component_manifest_refuses_a_mode_that_contradicts_its_preimages(
        host, tmp_path, monkeypatch):
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
    host._component_target_component_bytes = b"{}"
    host._component_mode_bound = ac._COMPONENT_OFFLINE_MODE
    host._component_control_launchd_disabled = False
    host._component_worker_launchd_disabled = True
    host._component_prior_archives = {
        "prior-component-autonomy-receipt.json": b"{}",
        "prior-component-ceo-submit-receipt.json": b"",
        "prior-component-receipt.json": b"",
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
    with pytest.raises(ac.TransactionEffectUnknown):
        ac.ProductionTransactionHost._manifest(host)


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
    # checkout is prepared.
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


def test_the_administrative_checkout_is_read_by_the_control_principal():
    # The Git observation is made AS the Control principal: Git refuses a
    # repository owned by another principal, and no safe.directory or other
    # trust exception is ever granted.
    argv = ac._component_git_argv(Path("/var/db/x"), "rev-parse", "HEAD")
    assert argv[0] == "/usr/bin/sudo"
    assert argv[1] == "-u"
    assert argv[2] == ac.CONTROL_USER
    assert "/usr/bin/git" in argv
    assert not any("safe.directory" in token for token in argv)
    assert "GIT_CONFIG_GLOBAL=/dev/null" in argv
    assert "GIT_CONFIG_NOSYSTEM=1" in argv
    assert "GIT_TERMINAL_PROMPT=0" in argv


# ---------------------------------------------------------------------------
# The final Control component repair.
#
#   1. the recovered publication phase is a RECOVERABLE phase, and only the
#      exact-byte readback may consume the observation that was published;
#   2. the semantic validation, the archival, the presence and the
#      correlation are bound to ONE qualified raw snapshot;
#   3. the reconciliation re-reads the ACTUAL Worker configuration through
#      the incumbent qualified configuration owner;
#   4. every post-claim qualification or read failure retains the original
#      transaction instead of reporting a zero-effect refusal;
#   5. the digest-bound effect list is the order the effects happen in.
# ---------------------------------------------------------------------------


_OBSERVATION_ANCESTRY = (
    (
        "/Library/Application Support/MastermindExecutive/config",
        (1, 2, 0o40700, 0, 0, 1, 0, 0, 0),
    ),
)


class _ObservationInfo:
    """The stat facts the observation publisher's own reader consumes."""

    def __init__(self, size: int):
        self.st_dev = 1
        self.st_ino = 1
        self.st_mode = 0o100440
        self.st_uid = 0
        self.st_gid = CONTROL_UID
        self.st_nlink = 1
        self.st_size = size
        self.st_mtime_ns = 0
        self.st_ctime_ns = 0


@pytest.fixture
def real_publisher(host, tmp_path, monkeypatch):
    """The REAL control-observation publisher, with only the leaf I/O stood in.

    The installed-source proof is an environment fact a hermetic run cannot
    have, and the two installed-peer readers are the leaf I/O.  Every
    publisher decision -- the admission, the phase it records, the exact-byte
    readback and the write itself -- is the production one.
    """

    observation_path = tmp_path / "control-observation.json"
    monkeypatch.setattr(
        control_observation.contract,
        "OBSERVATION_PATH",
        os.fspath(observation_path),
    )
    monkeypatch.setattr(control_observation, "_source", lambda expected_sha: None)

    def fake_atomic_file(path, payload, *, mode, uid, gid, replace):
        host.files.write(path, payload, replace=replace)
        if os.fspath(path) == os.fspath(observation_path):
            observation_path.write_bytes(payload)
            os.chmod(observation_path, 0o444)

    monkeypatch.setattr(ac, "_atomic_file", fake_atomic_file)

    def observe_ancestors(path, budget):
        return _OBSERVATION_ANCESTRY

    def read_trusted_bytes(
        path, *, budget, maximum, expected_mode=None, expected_gid=None
    ):
        raw = host.files.read(path)
        return raw, _ObservationInfo(len(raw))

    monkeypatch.setattr(installed, "_observe_ancestors", observe_ancestors)
    monkeypatch.setattr(installed, "_read_trusted_bytes", read_trusted_bytes)
    return observation_path


def test_the_recovered_publication_phase_is_recoverable_and_never_republished(
        host, real_publisher):
    """An interruption AFTER the publication closes by an exact-byte readback."""

    def interrupted(transaction):
        raise Crash("the closeout never ran")

    # The original operation is interrupted before its closeout: the
    # publication never happened and the marker is retained at the phase
    # that was still incomplete.
    host.complete_transaction = interrupted
    with pytest.raises(Crash):
        _apply(host)
    assert host.manifest["phase"] == "CONTROL_COMPONENT_RECEIPT_REPLACED"
    assert not real_publisher.exists()

    # The first reconciliation performs the ONE publication the transaction
    # owes and is interrupted right after the publisher recorded its phase.
    with pytest.raises(Crash):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.manifest["phase"] == "CONTROL_COMPONENT_PUBLICATION_STARTED"
    assert real_publisher.exists()
    published = real_publisher.read_bytes()
    writes = [w for w in host.files.writes if w == os.fspath(real_publisher)]
    assert len(writes) == 1
    commands = [list(command) for command in host.commands]

    # The second reconciliation closes the marker by reading the EXACT
    # published bytes back: no second observation write, no lifecycle effect.
    del host.complete_transaction
    result = ccu.reconcile(host, target_sha=TARGET_SHA)
    assert result["ok"] is True
    assert result["outcome"] == "RECONCILED"
    assert host.closed is True
    assert real_publisher.read_bytes() == published
    assert [w for w in host.files.writes if w == os.fspath(real_publisher)] == writes
    assert [list(command) for command in host.commands] == commands


def test_the_publication_phase_itself_is_never_publication_admissible():
    # The phase the component publication records is RECOVERABLE, and it is
    # NOT admissible for another publication: an attempted publication is
    # never repeated.
    assert "CONTROL_COMPONENT_PUBLICATION_STARTED" in ac._COMPONENT_PHASES
    assert control_observation.COMPONENT_PUBLICATION_PHASE not in (
        ac._CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES
    )


def test_a_malformed_receipt_is_refused_and_never_read_as_absent(host):
    # A malformed receipt is NOT an absent receipt: the two states lead to
    # different correlations, so the operation refuses instead of guessing.
    host.files.write(CEO_SUBMIT_RECEIPT, b'{"schema_version": ')
    host.files.writes.clear()
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_receipt_invalid"
    assert host.commands == []
    assert host.files.writes == []
    assert host.closed is False


def test_an_empty_receipt_is_refused_and_never_read_as_absent(host):
    host.files.write(CEO_SUBMIT_RECEIPT, b"")
    host.files.writes.clear()
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_receipt_invalid"
    assert host.commands == []
    assert host.files.writes == []


def test_an_unreadable_receipt_is_refused_and_never_read_as_absent(
        host, monkeypatch):
    original = ac._read_root_file

    def unreadable(path, *, modes, uid=0, gid=None):
        if os.fspath(path) == CEO_SUBMIT_RECEIPT:
            raise ac.HostControlError("config_identity_unavailable")
        return original(path, modes=modes, uid=uid, gid=gid)

    monkeypatch.setattr(ac, "_read_root_file", unreadable)
    host.files.write(CEO_SUBMIT_RECEIPT, b'{"state": "CEO_SUBMIT_DISARMED"}')
    host.files.writes.clear()
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_receipt_invalid"
    assert host.commands == []
    assert host.files.writes == []


def test_an_absent_receipt_stays_distinct_from_a_malformed_one(host):
    # The ABSENT CEO-submit receipt is a closed input state, not a failure:
    # the plan binds it as absent and correlates nothing.
    document = _plan(host)["plan"]
    assert document["receipts"]["ceo_submit_receipt"]["present"] is False
    # The MALFORMED one refuses before any marker or effect.
    host.files.write(CEO_SUBMIT_RECEIPT, b"{")
    host.files.writes.clear()
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _plan(host)
    assert caught.value.code == "control_component_receipt_invalid"


def test_the_receipt_is_read_once_and_the_archive_joins_the_validated_bytes(
        host, publisher, monkeypatch):
    reads: list[str] = []
    original = ac._read_root_file

    def counted(path, *, modes, uid=0, gid=None):
        reads.append(os.fspath(path))
        return original(path, modes=modes, uid=uid, gid=gid)

    monkeypatch.setattr(ac, "_read_root_file", counted)
    # The installed authority receipt is NOT canonically serialised.
    original_bytes = json.dumps(host.receipt, indent=4).encode("utf-8")
    host.files.write(AUTONOMY_RECEIPT, original_bytes)
    document = _plan(host)["plan"]
    # ONE qualified read: the semantic validation, the archived preimage, the
    # presence flag and the correlation all name the same bytes.
    assert reads.count(AUTONOMY_RECEIPT) == 1
    assert document["receipts"]["authority_receipt"]["before_sha256"] == _sha(
        original_bytes
    )
    _apply(host)
    archived = host.files.read(
        os.fspath(ac.AUTONOMY_TRANSACTION / "prior-component-autonomy-receipt.json")
    )
    assert archived == original_bytes
    published = json.loads(host.files.read(AUTONOMY_RECEIPT).decode("utf-8"))
    # The correlation moved only the four correlation fields of the SAME
    # document the archived bytes carry.
    for key, value in host.receipt.items():
        if key in {"release_sha", "control_config_sha256",
                   "prior_control_config_sha256", "transaction_id"}:
            continue
        assert published[key] == value


def test_an_empty_receipt_stays_present_in_the_sealed_marker(host, publisher):
    # Presence is EXPLICIT: it is never inferred from the byte length of the
    # archived preimage.  An empty receipt is present.
    host.files.write(COMPONENT_RECEIPT, b"")
    _apply(host)
    assert host.manifest["component_prior_component_receipt_present"] is True
    assert host.manifest["component_prior_component_receipt_sha256"] == _sha(b"")


def test_a_worker_that_drifted_after_the_interruption_is_refused(host, publisher):
    _apply(host)
    host.closed = False
    before = [list(command) for command in host.commands]
    # The Worker configuration drifted after the interrupted update.  The
    # reconciliation never took the retained manifest's Worker digest for the
    # installed one.
    host.files.write(WORKER_CONFIG, _canonical(
        dict(host.worker, operator_harness_armed=True)))
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    # The marker is retained and NOTHING is published, dispatched or closed.
    assert host.closed is False
    assert [list(command) for command in host.commands] == before
    assert host.manifest["phase"] == "CONTROL_COMPONENT_RECEIPT_REPLACED"


def test_the_reconciliation_reads_both_actual_configurations(host, publisher,
                                                             monkeypatch):
    _apply(host)
    host.closed = False
    reads: list[str] = []
    original_read = host.files.read

    def counted(path):
        reads.append(os.fspath(path))
        return original_read(path)

    monkeypatch.setattr(host.files, "read", counted)
    ccu.reconcile(host, target_sha=TARGET_SHA)
    # BOTH actual configurations are re-read through the incumbent qualified
    # configuration owner; the retained manifest is never their substitute.
    assert CONTROL_CONFIG in reads
    assert WORKER_CONFIG in reads


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("control_plist", "control_component_plist_unreadable"),
        ("lifecycle", "control_component_worker_state_unknown"),
    ],
)
def test_the_cli_reports_a_post_claim_refusal_as_incomplete(
        host, publisher, capsys, monkeypatch, failure, expected):
    import argparse
    from datetime import datetime, timezone

    _apply(host)
    host.closed = False

    if failure == "control_plist":
        def unreadable(path, *, code):
            raise ac.ComponentUpdateRefused(code)
        monkeypatch.setattr(host, "_component_root_file", unreadable)
    else:
        def unknown(label):
            raise ac.ArmAdmissionError("service_uid_process_unknown")
        monkeypatch.setattr(host, "_loaded_observe_only", unknown)

    args = argparse.Namespace(
        command="reconcile-control-component", expected_sha=TARGET_SHA,
        plan_sha256="0" * 64)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    # The original transaction was already claimed: this is NOT a zero-effect
    # refusal.
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "INCOMPLETE"
    assert document["code"] == expected
    assert document["transaction_id"] == host.manifest["transaction_id"]
    assert document["phase"]
    assert host.closed is False


def test_the_cli_reports_a_post_claim_read_failure_as_effect_unknown(
        host, publisher, capsys, monkeypatch):
    import argparse
    from datetime import datetime, timezone

    _apply(host)
    host.closed = False

    def unreadable():
        raise ac.HostControlError("config_identity_unavailable")

    monkeypatch.setattr(host, "_configs", unreadable)
    args = argparse.Namespace(
        command="reconcile-control-component", expected_sha=TARGET_SHA,
        plan_sha256="0" * 64)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "EFFECT_UNKNOWN"
    assert host.closed is False


def test_the_effect_list_is_the_order_the_effects_happen_in(host, publisher):
    live = list(ccu.LIVE_EFFECTS)
    offline = list(ccu.OFFLINE_EFFECTS)
    # Both installed plists are retargeted BEFORE the Control configuration
    # is replaced.
    assert live.index("replace " + ccu.CONTROL_PLIST_PATH) < live.index(
        "replace " + ccu.CONTROL_CONFIG_PATH)
    assert live.index("replace " + ccu.WORKER_PLIST_PATH) < live.index(
        "replace " + ccu.CONTROL_CONFIG_PATH)
    # The offline enable happens AFTER the publications, immediately before
    # the single bootstrap.
    assert offline.index("enable system/com.mastermind.executive.control") > \
        offline.index("replace " + ccu.CONTROL_CONFIG_PATH)
    assert offline.index("enable system/com.mastermind.executive.control") < \
        offline.index("bootstrap system/" + ccu.CONTROL_PLIST_PATH)
    assert _plan(host)["plan"]["effects"] == live

    # The owner dispatches them in exactly that order.
    _apply(host)
    assert host.phases.index("CONTROL_PLIST_REPLACED") < host.phases.index(
        "CONTROL_REPLACED")
    assert host.phases.index("WORKER_PLIST_REPLACED") < host.phases.index(
        "CONTROL_REPLACED")
    assert host.phases.index("CONTROL_REPLACED") < host.phases.index(
        "AUTHORITY_RECEIPT_CORRELATED")
    assert host.phases.index("AUTHORITY_RECEIPT_CORRELATED") < host.phases.index(
        "CONTROL_BOOTSTRAP_RECORDED")


def test_the_offline_mode_enables_after_the_publications(host, publisher):
    _offline(host)
    _apply(host)
    assert host.phases.index("AUTHORITY_RECEIPT_CORRELATED") < host.phases.index(
        "CONTROL_ENABLE_RECORDED")
    assert host.phases.index("CONTROL_ENABLE_RECORDED") < host.phases.index(
        "CONTROL_BOOTSTRAP_RECORDED")


def test_the_cli_reports_a_post_claim_receipt_read_failure_as_effect_unknown(
        host, publisher, capsys, monkeypatch):
    import argparse
    from datetime import datetime, timezone

    _apply(host)
    host.closed = False

    original = ac._read_root_file

    def unreadable(path, *, modes, uid=0, gid=None):
        if os.fspath(path) == AUTONOMY_RECEIPT:
            raise ac.HostControlError("config_identity_unavailable")
        return original(path, modes=modes, uid=uid, gid=gid)

    monkeypatch.setattr(ac, "_read_root_file", unreadable)
    args = argparse.Namespace(
        command="reconcile-control-component", expected_sha=TARGET_SHA,
        plan_sha256="0" * 64)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "EFFECT_UNKNOWN"
    # The original transaction is retained: nothing is replayed or rolled back.
    assert host.closed is False
    assert host.manifest["transaction_id"]


# ---------------------------------------------------------------------------
# The claimed-transaction classification.  Once the original transaction
# owner is claimed, EVERY outcome is INCOMPLETE or EFFECT_UNKNOWN: a claimed
# transaction is never reported as a clean zero-effect refusal.
# ---------------------------------------------------------------------------


def test_a_claimed_malformed_manifest_is_effect_unknown_and_never_refused(
        host, publisher, capsys):
    """The manifest read belongs INSIDE the claimed region.

    A malformed but qualified retained manifest used to escape the
    reconciliation as an unhandled error, which the CLI reported as a
    generic REFUSED.  That is a false zero-effect report about an operation
    that had already claimed the global transaction owner.
    """

    import argparse
    from datetime import datetime, timezone

    _apply(host)
    host.closed = False
    host.production_manifest = True
    manifest_path = os.fspath(
        ac.AUTONOMY_TRANSACTION / ac._TRANSACTION_MANIFEST_NAME)
    # The retained marker now carries a qualified but malformed document.
    host.files.data[manifest_path] = b'{"operation":[]}'
    before = dict(host.files.data)
    commands = [list(command) for command in host.commands]
    published = list(publisher)
    # The PRODUCTION closed manifest reader is the one that classifies this
    # document, and it is exactly the unhashable-membership defect that used
    # to escape the guarded region.
    with pytest.raises(TypeError):
        super(FakeHost, host)._manifest()
    args = argparse.Namespace(
        command="reconcile-control-component", expected_sha=TARGET_SHA)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] == "EFFECT_UNKNOWN"
    assert document["code"]
    assert "phase" not in document
    # The original artifacts are unchanged, and NOTHING was published,
    # dispatched, adopted or replayed.
    assert host.files.data == before
    assert [list(command) for command in host.commands] == commands
    assert publisher == published
    assert host.closed is False


def test_a_claimed_malformed_manifest_is_never_reported_as_refused(
        host, publisher, capsys):
    """The generic refusal branch must not be reachable after a claim."""

    import argparse
    from datetime import datetime, timezone

    _apply(host)
    host.closed = False
    host.production_manifest = True
    host.files.data[
        os.fspath(ac.AUTONOMY_TRANSACTION / ac._TRANSACTION_MANIFEST_NAME)
    ] = b'{"operation":[]}'
    args = argparse.Namespace(
        command="reconcile-control-component", expected_sha=TARGET_SHA)
    code = ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc))
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["outcome"] != "REFUSED"
    assert document["outcome"] == "EFFECT_UNKNOWN"


def test_the_reconcile_never_probes_the_ceo_receipt_path_ambiently(
        host, publisher, monkeypatch):
    """The CEO receipt is read through the SAME qualified receipt owner.

    A direct ``exists()``/``is_symlink()`` probe bypasses the owner and
    observes whatever the live host happens to carry; on a host that already
    has a CEO-submit receipt it turned a provable reconciliation into an
    uncertain one.
    """

    _apply(host)
    host.closed = False
    reads: list[str] = []
    original = host._component_receipt_bytes

    def counted(path):
        if os.fspath(path) == CEO_SUBMIT_RECEIPT:
            reads.append(os.fspath(path))
        return original(path)

    monkeypatch.setattr(host, "_component_receipt_bytes", counted)
    monkeypatch.setattr(
        ac, "CEO_SUBMIT_RECEIPT", _NoAmbientPath(ac.CEO_SUBMIT_RECEIPT))
    commands = [list(command) for command in host.commands]
    result = ccu.reconcile(host, target_sha=TARGET_SHA)
    assert result["ok"] is True
    assert result["outcome"] == "RECONCILED"
    # Exactly ONE qualified read of the CEO receipt: the snapshot that proved
    # the retained postimage is the snapshot the correlated bytes reuse.
    assert len(reads) == 1
    assert host._component_target_ceo_bytes == b""
    # A reconciliation dispatches no lifecycle effect.
    assert [list(command) for command in host.commands] == commands


def test_the_reconcile_reuses_the_one_qualified_ceo_receipt_snapshot(
        host, publisher, monkeypatch):
    """The correlated CEO bytes and the sealed digest name ONE snapshot."""

    host.files.write(CEO_SUBMIT_RECEIPT, _disarmed_ceo_receipt())
    _apply(host)
    host.closed = False
    reads: list[bytes] = []
    original = host._component_receipt_bytes

    def counted(path):
        present, raw = original(path)
        if os.fspath(path) == CEO_SUBMIT_RECEIPT:
            reads.append(raw)
        return present, raw

    monkeypatch.setattr(host, "_component_receipt_bytes", counted)
    monkeypatch.setattr(
        ac, "CEO_SUBMIT_RECEIPT", _NoAmbientPath(ac.CEO_SUBMIT_RECEIPT))
    result = ccu.reconcile(host, target_sha=TARGET_SHA)
    assert result["outcome"] == "RECONCILED"
    assert len(reads) == 1
    # The correlated bytes are exactly the bytes the single qualified read
    # returned: no second read of the same receipt exists.
    assert host._component_target_ceo_bytes == reads[0]
    assert host._component_target_ceo_bytes == host.files.read(CEO_SUBMIT_RECEIPT)
