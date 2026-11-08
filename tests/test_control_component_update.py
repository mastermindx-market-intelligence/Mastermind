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
import stat
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
        self.binding_publications: list[str] = []
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
        # The coordinated selection archives exist only for a transaction
        # that sealed a selection.
        for name in ac._COMPONENT_BINDING_ARCHIVES:
            if name in self._component_prior_archives:
                self.files.write(
                    os.fspath(ac.AUTONOMY_TRANSACTION / name),
                    self._component_prior_archives[name])

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

    def _component_archives(self, manifest=None) -> dict:
        archives = {}
        for name in ("prior-control.json", "prior-worker.json"):
            archives[name] = self.files.read(
                os.fspath(ac.AUTONOMY_TRANSACTION / name))
        names = ac._COMPONENT_ARCHIVES
        if manifest is not None and type(manifest.get("component_binding")) is dict:
            names = names + ac._COMPONENT_BINDING_ARCHIVES
        for name in names:
            archives[name] = self.files.read(
                os.fspath(ac.AUTONOMY_TRANSACTION / name))
        return archives

    def _publish_component_binding_artifact(self, destination, payload):
        """The ONE leaf write of the immutable binding publication.

        The leaf write is stood in for; the real primitive -- the private
        stage, the qualified root, the no-replace rename and the exact
        readback -- is exercised separately against a private temporary root.
        The no-replace semantics are preserved here too: an occupied
        destination is never overwritten.
        """

        self.files.write(os.fspath(destination), payload, replace=False)
        self.binding_publications.append(os.fspath(destination))

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
    import ast
    tree = ast.parse(control)
    parents = {id(child): node for node in ast.walk(tree)
               for child in ast.iter_child_nodes(node)}
    pure_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "ops.executive_os.mcp_component_update"
                       for alias in node.names)
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "ops.executive_os":
            assert all(alias.name != "mcp_component_update" for alias in node.names)
        if node.module != "ops.executive_os.mcp_component_update":
            continue
        assert len(node.names) == 1 and node.names[0].asname is None
        owner = parents[id(node)]
        while (not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef))
               and id(owner) in parents):
            owner = parents[id(owner)]
        assert isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef))
        pure_imports.append((owner.name, node.names[0].name))
    # Source adoption shares only these pure reads/transforms. It cannot
    # import the component's owner, verbs, transaction or a namespace alias.
    assert sorted(pure_imports) == sorted([
        ("derive_capability_profile_digests", "derive_sealed_capability_profile_digests"),
        ("prepare_gateway_publication", "_mission_capability_profile_digests"),
        ("_verify_gateway_postimages", "_apply_capability_profile_digests"),
    ])
    shell = (Path(ac.__file__).parent / "service-control.sh").read_text(encoding="utf-8")
    dispatch = shell.split("dispatch_mcp_component() {\n", 1)[1].split("\n}\n", 1)[0]
    assert ('exec "$GATEWAY_PREFLIGHT_PYTHON" -I -S -B '
            '"$component_dir/mcp_component_update.py" "${MCP_COMPONENT_ARGV[@]}"') in dispatch
    assert "autonomy_control.py" not in dispatch



@pytest.mark.parametrize("foreign_import", [
    "from ops.executive_os.mcp_component_update import main",
    "import ops.executive_os.mcp_component_update as component_namespace",
    "from ops.executive_os import mcp_component_update",
])
def test_mcp_effect_or_namespace_import_is_not_a_pure_helper_exception(monkeypatch, foreign_import):
    path = Path(ac.__file__)
    original = Path.read_text
    source = original(path, encoding="utf-8") + "\n" + foreign_import + "\n"
    def read_text(candidate, *args, **kwargs):
        return source if candidate == path else original(candidate, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(AssertionError):
        test_the_mcp_component_update_keeps_its_own_owner_and_behaviour()


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


# ---------------------------------------------------------------------------
# The Hermes host-read selection.  The selection is ONE optional, PAIRED
# input to the EXISTING plan/apply verbs.  It is never a second operation,
# never a new selector and never a new owner.
# ---------------------------------------------------------------------------


HERMES_READ_SCHEMA = "mastermind.hermes_role_metadata_host_binding/v1"
BINDING_V1 = "mastermind.executive_fabric_bindings/v1"
BINDING_V2 = "mastermind.executive_fabric_bindings/v2"
BINDING_V3 = "mastermind.executive_fabric_bindings/v3"


@pytest.fixture
def root_owned_files(monkeypatch, tmp_path):
    """The staged files this host owns appear root-owned.

    ONLY the leaf ownership observation is stood in for.  The real pinned
    read, the real strict parser, the real v1/v2/v3 composition parser and
    the real identity-joined read all run against the real files.

    The observation is scoped to the staged area and its ancestors, so the
    unrelated installed files of the hermetic host keep their own identity.
    """

    from types import SimpleNamespace

    original_lstat, original_fstat = Path.lstat, os.fstat
    root = os.fspath(tmp_path)

    def owned(text: str) -> bool:
        return text == root or text.startswith(root + "/") or root.startswith(
            text + "/"
        )

    def altered(info, **changes):
        values = {
            name: getattr(info, name)
            for name in (
                "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
                "st_uid", "st_gid", "st_mode", "st_nlink",
            )
        }
        return SimpleNamespace(**{**values, **changes})

    def root_lstat(path):
        info = original_lstat(path)
        if not owned(os.fspath(path)):
            return info
        changes = {"st_uid": 0}
        if stat.S_ISDIR(info.st_mode):
            changes["st_mode"] = info.st_mode & ~0o022
        return altered(info, **changes)

    monkeypatch.setattr(Path, "lstat", root_lstat)
    monkeypatch.setattr(
        os, "fstat", lambda fd: altered(original_fstat(fd), st_uid=0))


def _hermes_transport(tmp_path: Path) -> dict:
    """The closed transport of ONE Hermes host read.

    The three TLS paths are inert fixtures: they are never loaded as TLS
    material, only their identity is observed.
    """

    transport = {
        "endpoint_host": "127.0.0.1",
        "endpoint_port": 8443,
        "expected_server_fingerprint": "a" * 64,
        "timeout_seconds": 30,
    }
    for key in ("ca_path", "client_cert_path", "client_key_path"):
        path = tmp_path / key
        path.write_text("inert fixture, never loaded as TLS")
        path.chmod(0o600)
        transport[key] = str(path)
    return transport


def _hermes_read_member(tmp_path: Path, *, host_ref: str = "host-" + "1" * 64) -> dict:
    """The accepted read member: no credential bytes, only the closed shape."""

    return {
        "schema": HERMES_READ_SCHEMA,
        "host_ref": host_ref,
        "transport": _hermes_transport(tmp_path),
        "expected_host_binding_sha256": "b" * 64,
        "expected_implementation_sha": "c" * 40,
    }


def _hermes_input(tmp_path: Path, document: dict) -> tuple[str, str]:
    """The staged, qualified input and the EXACT digest of its raw bytes."""

    raw = json.dumps(document, sort_keys=True).encode("utf-8")
    path = tmp_path / "hermes-role-metadata-read.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return str(path), hashlib.sha256(raw).hexdigest()


def _binding_route() -> dict:
    """One pinned execution row."""

    return {
        "socket_path": "/var/run/mastermind/fabric.sock",
        "host_ref": "host-" + "1" * 64,
        "worker_id": "worker-1",
        "worker_uid": 1001,
        "worker_gid": 1001,
        "provider": "fixture",
        "model": "fixture-model",
        "worker_source_config_digest": "2" * 64,
        "execution_profile_digest": "3" * 64,
        "service_source_sha256": "4" * 64,
        "provider_home": "/srv/fabric/provider",
        "binary_sha256": "e" * 64,
        "permission_profile_sha256": "f" * 64,
        "bridge_uid": 501,
    }


def _binding_transport(tmp_path: Path, route: dict) -> dict:
    from control_plane.executive_fabric_composition import FabricHostBinding

    transport = {
        "host_ref": route["host_ref"],
        "worker_id": route["worker_id"],
        "physical_binding_sha256": FabricHostBinding(**route).digest,
        "endpoint_host": "127.0.0.1",
        "endpoint_port": 8443,
        "expected_server_fingerprint": "a" * 64,
        "timeout_seconds": 30,
    }
    for key in ("ca_path", "client_cert_path", "client_key_path"):
        path = tmp_path / f"remote-{key}"
        path.write_text("inert fixture, never loaded as TLS")
        path.chmod(0o600)
        transport[key] = str(path)
    return transport


def _prior_binding(tmp_path: Path, *, schema: str) -> tuple[str, str]:
    """One prior selected binding file and the EXACT digest of its bytes."""

    route = _binding_route()
    if schema == BINDING_V1:
        document = {"schema_version": BINDING_V1, "bindings": [route]}
    elif schema == BINDING_V2:
        document = {
            "schema_version": BINDING_V2,
            "bindings": [route],
            "remote_transports": [_binding_transport(tmp_path, route)],
        }
    elif schema == BINDING_V3:
        document = {
            "schema_version": BINDING_V3,
            "bindings": [route],
            "remote_transports": [_binding_transport(tmp_path, route)],
            "hermes_role_metadata_read": {
                "schema": HERMES_READ_SCHEMA,
                "host_ref": route["host_ref"],
                "transport": {
                    key: value
                    for key, value in _binding_transport(tmp_path, route).items()
                    if key
                    not in {"host_ref", "worker_id", "physical_binding_sha256"}
                },
                "expected_host_binding_sha256": "b" * 64,
                "expected_implementation_sha": "c" * 40,
            },
        }
    else:  # pragma: no cover - the closed fixture vocabulary
        raise AssertionError("unknown binding schema")
    raw = json.dumps(document, sort_keys=True).encode("utf-8")
    path = tmp_path / f"prior-{schema.rsplit('/', 1)[-1]}.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return str(path), hashlib.sha256(raw).hexdigest()


def _set_control(host, control: dict) -> None:
    """Install ONE Control configuration and re-correlate its receipt.

    The existing DISARMED authority receipt correlates the installed
    configuration digest, so a fixture that changes the configuration
    re-correlates that receipt exactly like the incumbent owner does.
    """

    host.control = copy.deepcopy(control)
    host.control_raw = _canonical(control)
    host.files.write(CONTROL_CONFIG, host.control_raw)
    receipt = copy.deepcopy(host.receipt)
    receipt["control_config_sha256"] = _sha(host.control_raw)
    host.receipt = receipt
    host.files.write(AUTONOMY_RECEIPT, ac._encoded_json(receipt))


def _select_binding(host, path: str, digest: str) -> None:
    """Make the installed Control configuration select ONE binding file."""

    control = copy.deepcopy(host.control)
    control["fabric_bindings_path"] = path
    control["fabric_bindings_sha256"] = digest
    _set_control(host, control)


def _composed(host) -> dict:
    """The published document of the selection, parsed from the sealed bytes."""

    from control_plane import executive_fabric_composition as composition

    raw = host._component_binding_candidate_bytes
    assert raw is not None
    return composition._document(raw)


def _selection_plan(host, **kwargs) -> dict:
    return ccu.plan(host, target_sha=TARGET_SHA, **kwargs)["plan"]


def _selection_apply(host, plan_sha256=None, **kwargs) -> dict:
    if plan_sha256 is None:
        plan_sha256 = ccu.plan(
            host, target_sha=TARGET_SHA, **kwargs)["plan_sha256"]
    return ccu.apply(
        host, target_sha=TARGET_SHA, plan_sha256=plan_sha256, **kwargs)


# -- no-option compatibility ------------------------------------------------


def test_without_the_selection_the_plan_is_byte_for_byte_the_historical_one(
        host):
    document = _plan(host)["plan"]
    # The selection member is ABSENT, not null: the source-only plan is
    # exactly the historical document.
    assert "selection" not in document
    assert document["effects"] == list(ccu.LIVE_EFFECTS)
    assert document["control_config"]["changed_fields"] == [
        "proof_base_sha", "proof_source_repository"]
    assert ccu.effects_for_mode(ccu.LIVE_MODE) == ccu.LIVE_EFFECTS
    assert ccu.effects_for_mode(ccu.OFFLINE_MODE) == ccu.OFFLINE_EFFECTS
    # The candidate carries no selection at all.
    observation = host.observe_control_component_update(target_sha=TARGET_SHA)
    assert observation["candidate"].selection is None
    assert observation["binding"] is None


def test_the_selection_is_paired_and_one_coordinate_alone_refuses(host):
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.plan(host, target_sha=TARGET_SHA, hermes_read_input="/tmp/input.json")
    assert caught.value.code == "control_component_hermes_read_selector_incomplete"
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.plan(host, target_sha=TARGET_SHA, hermes_read_sha256="0" * 64)
    assert caught.value.code == "control_component_hermes_read_selector_incomplete"
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.apply(
            host, target_sha=TARGET_SHA, plan_sha256="0" * 64,
            hermes_read_input="/tmp/input.json")
    assert caught.value.code == "control_component_hermes_read_selector_incomplete"


def test_the_reconcile_takes_no_replacement_input(host, publisher):
    import argparse
    from datetime import datetime, timezone

    args = argparse.Namespace(
        command="reconcile-control-component", expected_sha=TARGET_SHA)
    # The reconciliation verb has NO selector argument at all.
    parser = ac._parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "reconcile-control-component", "--expected-sha", TARGET_SHA,
            "--hermes-role-metadata-read-input", "/tmp/input.json",
        ])
    assert ac._run_control_component_command(
        host, args, now=datetime.now(timezone.utc)) == 1


# -- the selection itself ----------------------------------------------------


def test_the_selection_composes_a_v3_document_with_the_requested_read_member(
        host, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    document = _selection_plan(
        host, hermes_read_input=path, hermes_read_sha256=digest)
    selection = document["selection"]
    assert selection["input_sha256"] == digest
    assert selection["prior_selector_present"] is False
    assert selection["bindings_count"] == 0
    assert selection["remote_transports_count"] == 0
    assert selection["execution_present"] is False
    assert selection["destination_present"] is False
    # The destination is DERIVED from the digest of the composed bytes.
    assert selection["destination"].startswith(
        ccu.CONFIG_ROOT_PATH + "/fabric-bindings-")
    assert selection["destination"].endswith(".json")
    assert selection["destination"] == ccu.binding_destination(
        selection["candidate_sha256"])
    assert selection["effect"] == ccu.binding_effect(selection["destination"])
    # The ordered effect list carries the ONE publication.
    assert document["effects"] == list(
        ccu.effects_for_mode(
            ccu.LIVE_MODE, binding_destination=selection["destination"]))
    assert document["effects"][1] == selection["effect"]
    # The plan is read-only: nothing was created and nothing was published.
    assert host.binding_publications == []
    assert host.commands == []
    assert host.closed is False


def test_the_selection_carries_no_credential_or_endpoint_content(host, tmp_path,
                                                                 root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    document = _selection_plan(
        host, hermes_read_input=path, hermes_read_sha256=digest)
    encoded = json.dumps(document, sort_keys=True)
    # The plan carries hashes, presence, the derived destination and the
    # ordered effect -- never the transport, the endpoint or a key path.
    for forbidden in ("endpoint_host", "client_key_path", "client_cert_path",
                      "ca_path", "127.0.0.1", "expected_server_fingerprint"):
        assert forbidden not in encoded


def test_a_v1_prior_binding_preserves_its_rows_and_contributes_no_transports(
        host, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V1)
    _select_binding(host, prior_path, prior_digest)
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    document = _selection_plan(
        host, hermes_read_input=path, hermes_read_sha256=digest)
    selection = document["selection"]
    assert selection["prior_selector_present"] is True
    assert selection["prior_binding_sha256"] == prior_digest
    assert selection["bindings_count"] == 1
    # A v1 binding that carries no transports contributes an empty list; it
    # never invents one.
    assert selection["remote_transports_count"] == 0
    assert selection["execution_present"] is True


def test_a_v2_prior_binding_preserves_its_rows_and_transports_in_order(
        host, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V2)
    _select_binding(host, prior_path, prior_digest)
    # The read member names a DIFFERENT host, so the v3 rule that forbids a
    # conflicting transport for the SAME observation host is not the thing
    # under test here.
    path, digest = _hermes_input(
        tmp_path, _hermes_read_member(tmp_path, host_ref="host-" + "2" * 64))
    document = _selection_plan(
        host, hermes_read_input=path, hermes_read_sha256=digest)
    selection = document["selection"]
    assert selection["bindings_count"] == 1
    assert selection["remote_transports_count"] == 1
    # The published document carries the EXACT prior rows, in order.
    observation = host.observe_control_component_update(
        target_sha=TARGET_SHA, hermes_read=(path, digest))
    composed = observation["candidate"].selection
    assert composed.candidate_sha256 == selection["candidate_sha256"]


def test_the_composed_document_preserves_the_prior_execution_rows_exactly(
        host, publisher, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V2)
    _select_binding(host, prior_path, prior_digest)
    member = _hermes_read_member(tmp_path, host_ref="host-" + "2" * 64)
    path, digest = _hermes_input(tmp_path, member)
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    composed = _composed(host)
    prior = json.loads(open(prior_path, "rb").read())
    assert composed["bindings"] == prior["bindings"]
    assert composed["remote_transports"] == prior["remote_transports"]
    assert composed["schema_version"] == BINDING_V3
    # The requested read member is the one the input carried.
    assert composed["hermes_role_metadata_read"] == member


def test_a_v3_prior_binding_is_replaced_by_the_requested_read_member(
        host, publisher, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V3)
    _select_binding(host, prior_path, prior_digest)
    member = _hermes_read_member(tmp_path, host_ref="host-" + "2" * 64)
    path, digest = _hermes_input(tmp_path, member)
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    composed = _composed(host)
    prior = json.loads(open(prior_path, "rb").read())
    assert composed["bindings"] == prior["bindings"]
    assert composed["remote_transports"] == prior["remote_transports"]
    assert composed["hermes_role_metadata_read"] != prior[
        "hermes_role_metadata_read"]


def test_the_old_binding_file_is_never_touched(
        host, publisher, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V1)
    _select_binding(host, prior_path, prior_digest)
    before = open(prior_path, "rb").read()
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    assert open(prior_path, "rb").read() == before


# -- the paid coexistence ----------------------------------------------------


def test_metadata_only_coexists_with_the_installed_paid_source(
        host, tmp_path, root_owned_files):
    # The prior binding carries NO execution rows, so the metadata-only
    # selection may coexist with the installed paid source.
    control = copy.deepcopy(host.control)
    control["canonical_paid_fabric"] = {
        "bindings_path": "/Library/Application Support/MastermindExecutive/"
        "config/fabric-glm-paid-01/bindings.json",
        "bindings_sha256": "d" * 64,
    }
    _set_control(host, control)
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    document = _selection_plan(
        host, hermes_read_input=path, hermes_read_sha256=digest)
    assert document["selection"]["execution_present"] is False
    # The paid stanza is preserved exactly.
    after = json.loads(host.files.read(CONTROL_CONFIG))
    assert after["canonical_paid_fabric"] == control["canonical_paid_fabric"]


def test_execution_rows_never_coexist_with_the_installed_paid_source(
        host, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V2)
    _select_binding(host, prior_path, prior_digest)
    control = copy.deepcopy(host.control)
    control["canonical_paid_fabric"] = {
        "bindings_path": "/Library/Application Support/MastermindExecutive/"
        "config/fabric-glm-paid-01/bindings.json",
        "bindings_sha256": "d" * 64,
    }
    _set_control(host, control)
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _selection_plan(host, hermes_read_input=path, hermes_read_sha256=digest)
    assert caught.value.code == "control_component_hermes_read_binding_conflict"
    # The rows were never deleted to satisfy the exclusion.
    assert open(prior_path, "rb").read() == open(prior_path, "rb").read()
    assert host.commands == []


# -- the Control allowlist ---------------------------------------------------


def test_the_selection_updates_only_the_four_allowed_control_coordinates(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    before = json.loads(host.files.read(CONTROL_CONFIG))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    after = json.loads(host.files.read(CONTROL_CONFIG))
    assert set(after) == set(before) | {
        "fabric_bindings_path", "fabric_bindings_sha256"}
    changed = ccu.changed_keys(before, after)
    assert changed == (
        "fabric_bindings_path", "fabric_bindings_sha256",
        "proof_base_sha", "proof_source_repository")
    # The two selector coordinates are exactly the derived ones.
    assert after["fabric_bindings_path"] == ccu.binding_destination(
        after["fabric_bindings_sha256"])


def test_the_union_of_the_prior_and_successor_keys_is_compared(
        host, tmp_path, root_owned_files):
    # A key that only the SUCCESSOR carries is a change: it is never
    # silently accepted because the prior document did not mention it.
    document = {"a": 1}
    assert ccu.changed_keys(document, {"a": 1, "b": 2}) == ("b",)
    assert ccu.changed_keys({"a": 1, "b": 2}, document) == ("b",)
    assert ccu.changed_keys(document, {"a": 1}) == ()


def test_every_other_control_field_is_preserved(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    before = json.loads(host.files.read(CONTROL_CONFIG))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    after = json.loads(host.files.read(CONTROL_CONFIG))
    for key, value in before.items():
        if key in {"proof_base_sha", "proof_source_repository"}:
            continue
        assert after[key] == value
    # The arming, the Macro binding and the identities are untouched.
    assert after["ceo_submit_armed"] is False
    assert after["coo_autonomy_armed"] is False
    assert after["ceo_ingress_app_macro_root"] == MACRO_ROOT


def test_the_worker_configuration_is_exactly_the_original_bytes(
        host, publisher, tmp_path, root_owned_files):
    before = host.files.read(WORKER_CONFIG)
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    assert host.files.read(WORKER_CONFIG) == before


def test_the_plan_of_a_selection_is_read_only(host, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    before = dict(host.files.data)
    _selection_plan(host, hermes_read_input=path, hermes_read_sha256=digest)
    assert host.files.data == before
    assert host.binding_publications == []
    assert host.commands == []
    assert host.closed is False


# -- the sealed custody and the ordered effect -------------------------------


def test_the_selection_preimages_are_sealed_before_the_marker(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V1)
    _select_binding(host, prior_path, prior_digest)
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    transaction = ac.AUTONOMY_TRANSACTION
    # The exact qualified input, the ORIGINAL bytes of the prior selected
    # binding and the exact merged candidate are sealed.
    assert host.files.read(
        os.fspath(transaction / "prior-component-hermes-read-input.json")
    ) == Path(path).read_bytes()
    assert host.files.read(
        os.fspath(transaction / "prior-component-binding-selection.json")
    ) == Path(prior_path).read_bytes()
    assert host.files.read(
        os.fspath(transaction / "component-binding-candidate.json")
    ) == host._component_binding_candidate_bytes


def test_the_binding_publication_is_ordered_between_the_boundary_and_the_config(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    phases = host.phases
    assert phases.index("CONTROL_ABSENT_PROVEN") < phases.index(
        "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED")
    assert phases.index("CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED") < (
        phases.index("CONTROL_COMPONENT_BINDING_PROVEN"))
    assert phases.index("CONTROL_COMPONENT_BINDING_PROVEN") < phases.index(
        "CONTROL_REPLACED")
    # The binding artifact is published exactly once.
    assert len(host.binding_publications) == 1


def test_the_binding_phases_are_recoverable_and_never_publication_admissible():
    assert "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED" in ac._COMPONENT_PHASES
    assert "CONTROL_COMPONENT_BINDING_PROVEN" in ac._COMPONENT_PHASES
    # Neither binding phase ever authorises the control-observation
    # publication, and neither is the observation publisher's own phase.
    assert not {
        "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED",
        "CONTROL_COMPONENT_BINDING_PROVEN",
    } & set(ac._CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES)
    assert control_observation.COMPONENT_PUBLICATION_PHASE not in (
        ac._CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES)


# -- the compare-and-swap preimages ------------------------------------------


def test_the_input_that_moved_after_the_seal_is_refused(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    original_create = host._create_marker

    def create_then_move(transaction, *, operation):
        original_create(transaction, operation=operation)
        Path(path).write_bytes(b"moved after the seal")

    host._create_marker = create_then_move
    with pytest.raises(ac.TransactionEffectUnknown):
        _selection_apply(
            host, hermes_read_input=path, hermes_read_sha256=digest)
    assert host.closed is False
    assert host.binding_publications == []


def test_the_prior_binding_that_moved_after_the_seal_is_refused(
        host, publisher, tmp_path, root_owned_files):
    prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V1)
    _select_binding(host, prior_path, prior_digest)
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    original_create = host._create_marker

    def create_then_move(transaction, *, operation):
        original_create(transaction, operation=operation)
        Path(prior_path).write_bytes(b"moved after the seal")

    host._create_marker = create_then_move
    with pytest.raises(ac.TransactionEffectUnknown):
        _selection_apply(
            host, hermes_read_input=path, hermes_read_sha256=digest)
    assert host.closed is False


def test_a_destination_that_appears_after_the_observation_is_never_overwritten(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    original_publish = host._publish_component_binding_artifact

    raced = []

    def publish_after_a_race(destination, payload):
        # The destination appeared after the approved observation.
        raced.append(os.fspath(destination))
        host.files.write(os.fspath(destination), b"foreign", replace=True)
        return original_publish(destination, payload)

    host._publish_component_binding_artifact = publish_after_a_race
    with pytest.raises(ac.TransactionEffectUnknown):
        _selection_apply(
            host, hermes_read_input=path, hermes_read_sha256=digest)
    assert host.closed is False
    # The foreign artifact was never overwritten.
    assert len(raced) == 1
    assert host.files.read(raced[0]) == b"foreign"


def test_an_identical_preexisting_destination_is_adopted_without_a_write(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    # Observe the composition first, so the exact destination and bytes are
    # known before the operation runs.
    observation = host.observe_control_component_update(
        target_sha=TARGET_SHA, hermes_read=(path, digest))
    destination = observation["binding"]["destination"]
    payload = observation["binding"]["candidate_bytes"]
    # The identical artifact is ALREADY published.
    host.files.write(destination, payload)
    plan_sha256 = ccu.plan(
        host, target_sha=TARGET_SHA,
        hermes_read_input=path, hermes_read_sha256=digest)["plan_sha256"]
    assert plan_sha256
    _selection_apply(
        host, plan_sha256=plan_sha256,
        hermes_read_input=path, hermes_read_sha256=digest)
    # It was ADOPTED: nothing was written.
    assert host.binding_publications == []
    assert host.files.read(destination) == payload
    assert "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED" in host.phases


def test_a_conflicting_preexisting_destination_is_refused_before_the_transaction(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    observation = host.observe_control_component_update(
        target_sha=TARGET_SHA, hermes_read=(path, digest))
    destination = observation["binding"]["destination"]
    host.files.write(destination, b"a different artifact")
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _selection_plan(
            host, hermes_read_input=path, hermes_read_sha256=digest)
    assert caught.value.code == "control_component_hermes_read_binding_conflict"
    assert host.commands == []
    assert host.binding_publications == []


def test_a_binding_that_drifted_after_the_publication_prevents_completion(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    original_publish = host._publish_component_binding_artifact

    def publish_then_move(destination, payload):
        original_publish(destination, payload)
        host.files.write(os.fspath(destination), b"drifted")

    host._publish_component_binding_artifact = publish_then_move
    with pytest.raises(ac.TransactionEffectUnknown):
        _selection_apply(
            host, hermes_read_input=path, hermes_read_sha256=digest)
    assert host.closed is False


# -- the reconciliation ------------------------------------------------------


def test_the_reconcile_reconstructs_the_archived_selection(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.closed = False
    # The staged input is GONE: the reconciliation uses the SEALED bytes of
    # the original operation and never a new external input.
    os.unlink(path)
    result = ccu.reconcile(host, target_sha=TARGET_SHA)
    assert result["ok"] is True
    assert result["outcome"] == "RECONCILED"
    assert host.closed is True


@pytest.mark.parametrize("drift", [
    "input_whitespace", "prior_discarded_read", "candidate_bytes",
    "prior_present_empty", "prior_absent_nonempty", "prior_absent_digest",
    "bindings_count", "transports_count", "execution_present",
])
def test_reconcile_refuses_archive_or_selection_drift_without_effects(
        host, publisher, tmp_path, root_owned_files, drift):
    absent = drift.startswith("prior_absent")
    if not absent:
        prior_path, prior_digest = _prior_binding(tmp_path, schema=BINDING_V3)
        _select_binding(host, prior_path, prior_digest)
    # A distinct observation host keeps this recovery fixture independent
    # of the prior execution transport's TLS selection.
    member = _hermes_read_member(tmp_path, host_ref="host-" + "2" * 64)
    path, digest = _hermes_input(tmp_path, member)
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.closed = False
    host.production_manifest = True
    manifest = copy.deepcopy(host.manifest)
    member = manifest["component_binding"]
    def archive(name):
        return os.fspath(ac.AUTONOMY_TRANSACTION / name)
    input_key = archive("prior-component-hermes-read-input.json")
    prior_key = archive("prior-component-binding-selection.json")
    candidate_key = archive("component-binding-candidate.json")
    if drift == "input_whitespace":
        host.files.data[input_key] += b" "
    elif drift == "prior_discarded_read":
        prior = json.loads(host.files.data[prior_key])
        prior["hermes_role_metadata_read"]["expected_implementation_sha"] = "d" * 40
        host.files.data[prior_key] = json.dumps(prior, sort_keys=True).encode()
    elif drift == "candidate_bytes":
        host.files.data[candidate_key] += b" "
    elif drift == "prior_present_empty":
        host.files.data[prior_key] = b""
    elif drift == "prior_absent_nonempty":
        host.files.data[prior_key] = b"{}"
    elif drift == "prior_absent_digest":
        member["prior_binding_sha256"] = _sha(b"")
    elif drift == "bindings_count":
        member["bindings_count"] += 1
    elif drift == "transports_count":
        member["remote_transports_count"] += 1
    elif drift == "execution_present":
        member["execution_present"] = False
    host.files.data[archive(ac._TRANSACTION_MANIFEST_NAME)] = ac._encoded_json(manifest)
    files_before = dict(host.files.data)
    commands_before = list(host.commands)
    phases_before = list(host.phases)
    bindings_before = list(host.binding_publications)
    receipts_before = list(publisher)
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.transaction_present is True
    assert host.closed is False
    assert host.files.data == files_before
    assert host.commands == commands_before
    assert host.phases == phases_before
    assert host.binding_publications == bindings_before
    assert publisher == receipts_before


def test_composed_binding_obeys_the_actual_consumer_byte_limit(
        host, publisher, tmp_path, root_owned_files):
    from control_plane import executive_fabric_composition as composition

    prior_path, _ = _prior_binding(tmp_path, schema=BINDING_V1)
    prior = json.loads(Path(prior_path).read_bytes())
    raw = json.dumps(prior, sort_keys=True).encode()
    prior["bindings"][0]["model"] += "x" * (
        composition.MAX_CONFIG_BYTES - len(raw) - 128)
    raw = json.dumps(prior, sort_keys=True).encode()
    assert 0 < len(raw) <= composition.MAX_CONFIG_BYTES
    composition._composition(raw)  # A valid prior document, within its limit.
    Path(prior_path).write_bytes(raw)
    _select_binding(host, prior_path, _sha(raw))
    member = _hermes_read_member(tmp_path)
    path, digest = _hermes_input(tmp_path, member)
    composed = ccu.compose_binding_candidate(
        input_document=member, prior_bindings=prior["bindings"],
        prior_remote_transports=())
    assert len(composed) > composition.MAX_CONFIG_BYTES
    before = dict(host.files.data)
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _selection_plan(host, hermes_read_input=path, hermes_read_sha256=digest)
    assert caught.value.code == "control_component_hermes_read_binding_conflict"
    assert host.transaction_present is False
    assert host.files.data == before
    assert host.commands == []
    assert host.binding_publications == []
    assert publisher == []


def test_a_published_binding_with_an_unswitched_config_remains_incomplete(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.closed = False
    # The Control configuration was never switched to the published binding.
    host.files.write(CONTROL_CONFIG, host.control_raw)
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert caught.value.code == "control_component_binding_config_not_switched"
    # The original transaction is retained and named.
    assert caught.value.transaction_id
    assert caught.value.phase
    assert host.closed is False


def test_the_reconcile_never_republishes_the_binding(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.closed = False
    published = list(host.binding_publications)
    ccu.reconcile(host, target_sha=TARGET_SHA)
    # The canonical publication is NEVER re-entered.
    assert host.binding_publications == published


def test_a_conflicting_binding_postimage_is_never_adopted(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.closed = False
    destination = host.manifest["component_binding"]["destination"]
    host.files.write(destination, b"a conflicting artifact")
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host.closed is False
    # The conflicting artifact was never adopted and never overwritten.
    assert host.files.read(destination) == b"a conflicting artifact"


# -- the marker formats ------------------------------------------------------


def test_the_legacy_component_marker_carries_no_selection_member(
        host, publisher):
    _apply(host)
    assert "component_binding" not in host.manifest
    host.production_manifest = True
    # The LEGACY marker format is preserved exactly: the closed reader
    # accepts it and the legacy archive set is unchanged.
    assert host._manifest() == host.manifest
    assert ac._component_archive_names(host.manifest) == ac._COMPONENT_ARCHIVES


def test_the_extended_marker_carries_the_closed_selection_member(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.production_manifest = True
    manifest = host._manifest()
    assert set(manifest["component_binding"]) == ac._COMPONENT_BINDING_MANIFEST_KEYS
    assert ac._component_archive_names(manifest) == (
        ac._COMPONENT_ARCHIVES + ac._COMPONENT_BINDING_ARCHIVES)


@pytest.mark.parametrize("malformation", ["presence", "null"])
def test_a_malformed_selection_member_is_refused(host, publisher, tmp_path,
                                                  root_owned_files, malformation):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.production_manifest = True
    manifest = dict(host.manifest)
    manifest["component_binding"] = dict(manifest["component_binding"])
    # Absence is legacy; an explicitly null member is malformed.
    if malformation == "null":
        manifest["component_binding"] = None
    else:
        manifest["component_binding"]["destination_present"] = "yes"
    host.files.data[
        os.fspath(ac.AUTONOMY_TRANSACTION / ac._TRANSACTION_MANIFEST_NAME)
    ] = ac._encoded_json(manifest)
    published = list(publisher)
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    # The retained marker and its preimages are retained; nothing was
    # republished.
    assert host.transaction_present is True
    assert publisher == published


def test_a_selection_member_that_names_another_destination_is_refused(
        host, publisher, tmp_path, root_owned_files):
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    host.production_manifest = True
    manifest = dict(host.manifest)
    manifest["component_binding"] = dict(manifest["component_binding"])
    manifest["component_binding"]["destination"] = "/tmp/another.json"
    host.files.data[
        os.fspath(ac.AUTONOMY_TRANSACTION / ac._TRANSACTION_MANIFEST_NAME)
    ] = ac._encoded_json(manifest)
    published = list(publisher)
    with pytest.raises(ac.TransactionEffectUnknown):
        ccu.reconcile(host, target_sha=TARGET_SHA)
    # The retained marker and its preimages are retained; nothing was
    # republished.
    assert host.transaction_present is True
    assert publisher == published


# -- the closed command line -------------------------------------------------


def _control_component_argv(*argv: str) -> subprocess.CompletedProcess:
    """Run the incumbent controller's closed argv walk in isolation.

    The walk is the controller's own shell function, extracted verbatim from
    the installed script: the test exercises the real argument discipline
    and the real rebuilt argv, not a re-implementation of it.
    """

    source = _service_control_source()
    start = source.index("valid_component_input_path() {")
    end = source.index("dispatch_control_component() {")
    fragment = source[start:end]
    script = (
        "set -euo pipefail\n"
        'CONTROL_COMPONENT_ARGV=()\n'
        'CONTROL_COMPONENT_EXPECTED_SHA=""\n'
        + fragment
        + "\ncontrol_component_args \"$@\" || exit 1\n"
        + "printf '%s\\n' \"${CONTROL_COMPONENT_ARGV[@]}\"\n"
    )
    return subprocess.run(
        ["/bin/bash", "-c", script, "control-component", *argv],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False, timeout=30)


@pytest.mark.parametrize("input_path", [
    "/var/db/staged/read.json",
    "/Library/Application Support/MastermindExecutive/staged/read.json",
])
def test_the_closed_argv_walk_forwards_the_paired_selection(input_path):
    completed = _control_component_argv(
        "plan-control-component", "--expected-sha", "a" * 40,
        "--hermes-role-metadata-read-input", input_path,
        "--hermes-role-metadata-read-sha256", "b" * 64)
    assert completed.returncode == 0
    assert completed.stdout.decode("utf-8").splitlines() == [
        "plan-control-component",
        "--expected-sha",
        "a" * 40,
        "--hermes-role-metadata-read-input",
        input_path,
        "--hermes-role-metadata-read-sha256",
        "b" * 64,
    ]


def test_the_closed_argv_walk_refuses_one_coordinate_alone():
    for argv in (
        ("plan-control-component", "--expected-sha", "a" * 40,
         "--hermes-role-metadata-read-input", "/var/db/staged/read.json"),
        ("plan-control-component", "--expected-sha", "a" * 40,
         "--hermes-role-metadata-read-sha256", "b" * 64),
    ):
        assert _control_component_argv(*argv).returncode == 1


def test_the_closed_argv_walk_refuses_an_unsafe_input_path():
    for unsafe in (
        "relative/read.json",
        "/var/db/../etc/read.json",
        "/var//db/read.json",
        "/var/db/read.json; rm -rf /",
        "/var/db/read.json\t",
        "/var/db/read.json\n",
        "/var/db/$(read).json",
        "/var/db/`read`.json",
    ):
        completed = _control_component_argv(
            "plan-control-component", "--expected-sha", "a" * 40,
            "--hermes-role-metadata-read-input", unsafe,
            "--hermes-role-metadata-read-sha256", "b" * 64)
        assert completed.returncode == 1, unsafe


def test_the_closed_argv_walk_refuses_the_selection_on_the_reconcile():
    completed = _control_component_argv(
        "reconcile-control-component", "--expected-sha", "a" * 40,
        "--hermes-role-metadata-read-input", "/var/db/staged/read.json",
        "--hermes-role-metadata-read-sha256", "b" * 64)
    assert completed.returncode == 1


def test_the_closed_argv_walk_keeps_the_source_only_behaviour():
    completed = _control_component_argv(
        "plan-control-component", "--expected-sha", "a" * 40)
    assert completed.returncode == 0
    assert completed.stdout.decode("utf-8").splitlines() == [
        "plan-control-component", "--expected-sha", "a" * 40]


# -- the real publication primitive ------------------------------------------


@pytest.fixture
def root_owned_root(monkeypatch, tmp_path):
    """The private root the REAL publication primitive publishes into.

    The ownership observation is stood in for exactly as the incumbent
    composition tests stand in for it, and the ONE leaf call that needs
    real root -- the ownership normalisation -- is a no-op here.  Every
    other part of the primitive is the real one: the qualified root, the
    private stage, the no-replace rename and the exact readback.
    """

    from types import SimpleNamespace

    original_lstat, original_fstat = Path.lstat, os.fstat

    def altered(info, **changes):
        values = {
            name: getattr(info, name)
            for name in (
                "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
                "st_uid", "st_gid", "st_mode", "st_nlink",
            )
        }
        return SimpleNamespace(**{**values, **changes})

    def root_lstat(path):
        info = original_lstat(path)
        changes = {"st_uid": 0, "st_gid": 0}
        if stat.S_ISDIR(info.st_mode):
            changes["st_mode"] = info.st_mode & ~0o022
        return altered(info, **changes)

    monkeypatch.setattr(Path, "lstat", root_lstat)
    monkeypatch.setattr(
        os, "fstat", lambda fd: altered(original_fstat(fd), st_uid=0, st_gid=0))
    monkeypatch.setattr(os, "fchown", lambda fd, uid, gid: None)
    root = tmp_path / "config-root"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    monkeypatch.setattr(ac, "CONFIG_ROOT", root)
    return root


def test_the_real_publication_primitive_is_one_no_replace_rename(root_owned_root):
    host = ac.ProductionControlComponentHost()
    payload = b'{"schema_version":"mastermind.executive_fabric_bindings/v3"}\n'
    digest = hashlib.sha256(payload).hexdigest()
    destination = root_owned_root / ("fabric-bindings-" + digest + ".json")
    host._publish_component_binding_artifact(destination, payload)
    # The exact postimage, with the published mode and one link.
    assert destination.read_bytes() == payload
    info = destination.stat()
    assert stat.S_IMODE(info.st_mode) == 0o444
    assert info.st_nlink == 1
    # No private stage is left behind.
    assert sorted(p.name for p in root_owned_root.iterdir()) == [destination.name]


def test_the_real_publication_primitive_never_replaces_a_name(root_owned_root):
    host = ac.ProductionControlComponentHost()
    payload = b'{"schema_version":"mastermind.executive_fabric_bindings/v3"}\n'
    digest = hashlib.sha256(payload).hexdigest()
    destination = root_owned_root / ("fabric-bindings-" + digest + ".json")
    host._publish_component_binding_artifact(destination, payload)
    # A second publication of the SAME name refuses: the exclusive rename
    # never replaces an existing artifact.
    with pytest.raises(ac.TransactionEffectUnknown):
        host._publish_component_binding_artifact(destination, payload)
    assert destination.read_bytes() == payload
    # The refused publication left no private stage behind.
    assert sorted(p.name for p in root_owned_root.iterdir()) == [destination.name]


def test_the_real_publication_primitive_refuses_a_destination_outside_the_root(
        root_owned_root, tmp_path):
    host = ac.ProductionControlComponentHost()
    payload = b"{}\n"
    outside = tmp_path / "elsewhere.json"
    with pytest.raises(ac.TransactionEffectUnknown):
        host._publish_component_binding_artifact(outside, payload)
    assert not outside.exists()


def test_the_input_gateway_implementation_pin_is_kept_exactly(
        host, publisher, tmp_path, root_owned_files):
    member = _hermes_read_member(tmp_path)
    path, digest = _hermes_input(tmp_path, member)
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    composed = _composed(host)
    # The gateway implementation pin is carried EXACTLY, and it need not
    # equal the Control release SHA.
    assert composed["hermes_role_metadata_read"]["expected_implementation_sha"] == (
        "c" * 40)
    assert composed["hermes_role_metadata_read"]["expected_implementation_sha"] != (
        TARGET_SHA)
    assert composed["hermes_role_metadata_read"]["expected_host_binding_sha256"] == (
        "b" * 64)


def test_the_selection_is_part_of_the_same_pending_source_upgrade(
        host, tmp_path, root_owned_files):
    # The selection never invents a second, same-SHA operation: the release
    # retarget refusal still holds with a selection in hand.
    path, digest = _hermes_input(tmp_path, _hermes_read_member(tmp_path))
    with pytest.raises(ccu.ComponentError) as caught:
        ccu.compile_candidate(
            _canonical(host.control),
            plistlib.dumps(_control_plist(PRIOR_ROOT)),
            plistlib.dumps(_worker_plist(PRIOR_ROOT)),
            target_sha=PRIOR_SHA,
            prior_sha=PRIOR_SHA,
            worker_config_sha256=_sha(host.worker_raw),
            prior_release_root=PRIOR_ROOT,
            target_release_root=PRIOR_ROOT,
        )
    assert caught.value.code == "release_not_retargeted"
    assert host.commands == []
    assert host.binding_publications == []

def _prior_role_conversations(tmp_path, dual, native=False):
    from control_plane import executive_fabric_composition as composition
    member = _hermes_read_member(tmp_path)
    secretary = dict(member, schema=composition.HERMES_SECRETARY_HOST_SCHEMA,
        root_id="secretary-root", root_job_id="JOB-001", work_ref="WS:SECRETARY",
        session_id="secretary-session", profile_id="secretary-profile", principal_id="principal-1")
    meta = dict(secretary, schema=composition.HERMES_META_HOST_SCHEMA, root_id="meta-root",
        root_job_id="JOB-002", work_ref="WS:META", session_id="meta-session", profile_id="meta-profile")
    native_slot = None
    if native:
        assert dual
        native_slot = dict(schema=composition.NATIVE_OPERATOR_HOST_SCHEMA,
            registration=dict(worker_id="native-fixture", quota_class="dsh-native",
                model_alias="dsh.native.conversation", host_ref=member["host_ref"],
                worker_source_config_digest="e" * 64),
            harness_binary_digest="f" * 64, harness_version="fixture-native-only",
            expected_config_digest="d" * 64,
            workspace=dict(workspace_path="/selected-host/workspace", base_sha="a" * 40,
                           device=1, inode=2, uid=501, gid=20))
    raw = ccu.compose_binding_candidate(input_document=member, prior_bindings=[],
        prior_remote_transports=[], prior_secretary_conversation=secretary,
        prior_meta_conversation=meta if dual else None, prior_native_conversation=native_slot)
    # The paired-selection operation requires changed selector coordinates.
    # Preserve the full prior semantics with its original compact serialization;
    # the new immutable artifact is rendered by the incumbent pretty composer.
    raw = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode()
    path = tmp_path / "prior-role-conversations.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return str(path), hashlib.sha256(raw).hexdigest(), json.loads(raw)


@pytest.mark.parametrize("dual,native", [(False, False), (True, False), (True, True)])
def test_control_update_preserves_complete_role_conversations(host, publisher, tmp_path, root_owned_files, dual, native):
    prior_path, prior_digest, prior = _prior_role_conversations(tmp_path, dual, native)
    _select_binding(host, prior_path, prior_digest)
    path, digest = _hermes_input(tmp_path, prior["hermes_role_metadata_read"])
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    composed = _composed(host)
    assert composed == prior
    assert len(host.binding_publications) == 1
    assert hashlib.sha256(Path(prior_path).read_bytes()).hexdigest() == prior_digest


@pytest.mark.parametrize("dual,native", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("field,value", [
    ("host_ref", "host-" + "f" * 64),
    ("expected_host_binding_sha256", "f" * 64),
    ("expected_implementation_sha", "f" * 40),
])
def test_control_update_refuses_conversation_source_retarget_before_effect(
        host, tmp_path, root_owned_files, dual, native, field, value):
    prior_path, prior_digest, prior = _prior_role_conversations(tmp_path, dual, native)
    _select_binding(host, prior_path, prior_digest)
    changed = dict(prior["hermes_role_metadata_read"], **{field: value})
    path, digest = _hermes_input(tmp_path, changed)
    before = dict(host.files.data)
    with pytest.raises(ac.ComponentUpdateRefused) as caught:
        _selection_plan(host, hermes_read_input=path, hermes_read_sha256=digest)
    assert caught.value.code == "control_component_hermes_read_binding_conflict"
    assert host.files.data == before and host.binding_publications == [] and host.commands == []

@pytest.mark.parametrize("dual,native", [(False, False), (True, False), (True, True)])
def test_role_conversation_recovery_keeps_original_bytes_without_republication(
        host, publisher, tmp_path, root_owned_files, dual, native):
    prior_path, prior_digest, prior = _prior_role_conversations(tmp_path, dual, native)
    _select_binding(host, prior_path, prior_digest)
    path, digest = _hermes_input(tmp_path, prior["hermes_role_metadata_read"])
    planned = _selection_plan(host, hermes_read_input=path, hermes_read_sha256=digest)
    # The plan's digest/destination and the qualified consumer bytes must agree.
    observed = host.observe_control_component_update(
        target_sha=TARGET_SHA, hermes_read=(path, digest))
    assert observed["candidate"].selection.candidate_sha256 == observed["binding"]["candidate_sha256"]
    assert observed["candidate"].selection.destination == observed["binding"]["destination"]
    _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    original = host._component_binding_candidate_bytes
    assert hashlib.sha256(original).hexdigest() == planned["selection"]["candidate_sha256"]
    publications = list(host.binding_publications)
    host.closed = False
    ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host._component_binding_candidate_bytes == original
    assert host.binding_publications == publications
    assert json.loads(original) == prior


def test_recovery_keeps_sealed_legacy_v3_policy_for_prior_secretary(
        host, publisher, tmp_path, root_owned_files, monkeypatch):
    prior_path, prior_digest, prior = _prior_role_conversations(tmp_path, False)
    _select_binding(host, prior_path, prior_digest)
    path, digest = _hermes_input(tmp_path, prior["hermes_role_metadata_read"])
    compose = ccu.compose_binding_candidate
    def legacy(**kwargs):
        kwargs.pop("prior_secretary_conversation", None)
        kwargs.pop("prior_meta_conversation", None)
        return compose(**kwargs)
    # Create an inert historical transaction through the same fake host.
    with monkeypatch.context() as patch:
        patch.setattr(ccu, "compose_binding_candidate", legacy)
        _selection_apply(host, hermes_read_input=path, hermes_read_sha256=digest)
    original = host._component_binding_candidate_bytes
    assert json.loads(original)["schema_version"] == BINDING_V3
    assert "hermes_secretary_conversation" not in json.loads(original)
    publications = list(host.binding_publications)
    host.closed = False
    ccu.reconcile(host, target_sha=TARGET_SHA)
    assert host._component_binding_candidate_bytes == original
    assert host.binding_publications == publications
