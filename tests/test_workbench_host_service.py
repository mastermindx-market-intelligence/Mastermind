"""Typed Workbench lifecycle with real private files and a finite launchd model."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.studio_direct_mcp import private_service as owner
from integrations.studio_direct_mcp import workbench_host_service as host
from integrations.mastermind_browser_link.profile_grant import PROFILES_SCHEMA
from integrations.workbench_action_mcp import service
from ops.executive_os import company_mcp_edge as runtime_owner
from ops.executive_os import workbench_mcp_runtime as runtime
from tests.workbench_action_mcp.test_browser_fabric_startup import _v3_document

SHA = "a" * 40


class LaunchdModel:
    def __init__(self, target):
        self.target = target
        self.observed = None
        self.effects = []
        self.ready = True
        self.boot = "original-boot"
        self.exit_code = 0
        self.signal = None
        self.absent = False
        self.bootstrap_unknown = False
        self.bootout_unknown = False
        self.stop_pending = False

    def response(self):
        t, row = self.target, self.observed
        if row is None:
            return SimpleNamespace(returncode=113, stdout="", stderr=(
                f'Bad request.\nCould not find service "{host.LABEL}" in domain for user gui: {t.uid}\n'))
        lines = [t.launch_target + " = {", "\tpath = " + str(t.plist),
                 "\tstate = " + row["state"], "\truns = " + str(row["runs"])]
        if row["pid"] is not None:
            lines.append("\tpid = " + str(row["pid"]))
        if row["never_exited"]:
            lines.append("\tlast exit code = (never exited)")
        elif row["exit_code"] is not None:
            lines.append("\tlast exit code = " + str(row["exit_code"]))
        if row["signal"] is not None:
            lines.append("\tlast terminating signal = " + str(row["signal"]))
        lines += ["\tcoalition = {", "\t\tstate = running", "\t\tpid = 999", "\t}", "}"]
        return SimpleNamespace(returncode=0, stdout="\n".join(lines) + "\n", stderr="")

    @staticmethod
    def waiting(runs=0, code=None):
        return dict(state="waiting", pid=None, runs=runs, exit_code=code, never_exited=runs == 0, signal=None)

    def run(self, argv, **kwargs):
        assert argv[0] == "/bin/launchctl"
        operation = argv[1]
        if operation == "print":
            return self.response()
        self.effects.append(tuple(argv))
        if operation == "bootstrap":
            assert argv[2:] == [self.target.domain, str(self.target.plist)]
            self.observed = self.waiting()
            if self.bootstrap_unknown:
                raise TimeoutError("synthetic ambiguous bootstrap")
        elif operation == "kickstart":
            assert argv[2:] == [self.target.launch_target]
            self.observed = dict(state="running", pid=445551, runs=1, exit_code=None, never_exited=True, signal=None)
            self.absent = False
        elif operation == "kill":
            assert argv[2:] == ["SIGTERM", self.target.launch_target]
            if not self.stop_pending:
                self.observed = self.waiting(1, self.exit_code)
                self.observed["signal"] = self.signal
                self.absent = True
        elif operation == "bootout":
            assert argv[2:] == [self.target.launch_target]
            if self.bootout_unknown:
                return SimpleNamespace(returncode=1, stdout="", stderr="ambiguous")
            self.observed = None
        else:
            pytest.fail("unexpected operation")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    uid = os.geteuid()
    t = host.Target(uid, home)
    monkeypatch.setattr(host, "target", lambda: t)
    monkeypatch.setattr(owner, "_user_root", lambda: home)
    monkeypatch.setattr(runtime_owner, "SYSTEM", tmp_path / "system")
    def qualified(release_sha, service_uid):
        assert service_uid == uid
        assert release_sha in {SHA, "b" * 40}
        return {
            "schema": runtime.SCHEMA, "release_sha": release_sha, "service_uid": uid,
            "source": {"release_sha": release_sha, "tree_sha": "d" * 40,
                       "source_manifest_sha256": "e" * 64, "lock_sha256": "f" * 64},
            "runtime_root": str(tmp_path / "sdk" / release_sha),
            "python_executable": str(tmp_path / "sdk" / release_sha / "bin/python3.12"),
            "entry_sha256": "1" * 64, "receipt_sha256": "2" * 64,
            "inventory_sha256": "3" * 64, "base": {"fixture": True},
        }
    monkeypatch.setattr(runtime, "verify", qualified)
    # Keep the interpreter builder's closed shape; production UID validation is
    # covered separately, including CI runners that execute fixtures as root.
    monkeypatch.setattr(runtime, "launch_argv", lambda release, selected_uid:
                        ["/fixed/base/python3.12", "-I", "-S", "-B", "-c", runtime.BOOTSTRAP,
                         str(runtime_owner.SYSTEM / "releases" / release), "serve", "--release", release])
    inputs = home / "inputs"
    inputs.mkdir(mode=0o700)
    document, _ = _v3_document(inputs)
    profiles = inputs / "profiles.json"
    profiles.write_text(json.dumps({"schema": PROFILES_SCHEMA, "profiles": []}))
    profiles.chmod(0o600)
    document["io_timeout_seconds"] = 10
    document["browser"] = {
        "schema": service._LINK_BROWSER_SCHEMA,
        "source_root": str(runtime_owner.SYSTEM / "releases" / SHA),
        "python_executable": qualified(SHA, uid)["python_executable"],
        "relay_root": str(inputs / "relay"), "output_root": str(inputs / "output"),
        "startup_timeout_seconds": 5, "profiles_file": str(profiles),
    }
    host._prepare_directories(t)
    host._write(t.candidate, host._encoded(document))
    model = LaunchdModel(t)
    monkeypatch.setattr(owner, "_run", model.run)
    monkeypatch.setattr(host, "_boot", lambda: model.boot)
    monkeypatch.setattr(host, "_process", lambda selected, pid:
                        {"pid": pid, "process_start_identity": "instance-one",
                         "service_uid": uid, "boot_session_id": model.boot})
    monkeypatch.setattr(host, "_process_absent", lambda selected, original: model.absent and model.boot == original["boot_session_id"])
    monkeypatch.setattr(host, "_probe", lambda *args, **kwargs: model.ready)
    counter = iter(range(0, 1000000, 1000))
    monkeypatch.setattr(host, "time", SimpleNamespace(monotonic=lambda: next(counter), sleep=lambda seconds: None))
    return SimpleNamespace(t=t, document=document, model=model, qualified=qualified)


def staged(setup):
    plan = host.preview(SHA)
    result = host.stage(SHA, host._hash(plan))
    assert result["status"] == "STAGED"
    return result["install_sha256"], plan


def test_fresh_stage_preserves_keys_store_and_has_explicit_start_policy(setup):
    key = Path(setup.document["action_key_file"])
    store = Path(setup.document["artifact_directory"])
    original = (key.read_bytes(), key.stat().st_ino, store.stat().st_dev, store.stat().st_ino)
    digest, plan = staged(setup)
    assert setup.model.effects == []
    assert plan["plist"]["RunAtLoad"] is False and plan["plist"]["KeepAlive"] is False
    assert plan["plist"]["ExitTimeOut"] > 2 * setup.document["close_timeout_seconds"]
    assert (key.read_bytes(), key.stat().st_ino, store.stat().st_dev, store.stat().st_ino) == original
    assert host.stage(SHA, digest)["status"] == "UNCHANGED"


@pytest.mark.parametrize("interrupt_at", ["plist", "lifecycle", "manifest"])
def test_stage_recovers_only_exact_original_outputs(setup, monkeypatch, interrupt_at):
    plan = host.preview(SHA)
    destination = getattr(setup.t, interrupt_at)
    actual_write = host._write
    def interrupted(path, data, **kwargs):
        if path == destination:
            raise OSError("synthetic interrupted stage")
        return actual_write(path, data, **kwargs)
    monkeypatch.setattr(host, "_write", interrupted)
    with pytest.raises(OSError):
        host.stage(SHA, host._hash(plan))
    assert host._read(setup.t.journal)["phase"] == "PREPARED"
    config_inode = setup.t.config.stat().st_ino
    monkeypatch.setattr(host, "_write", actual_write)
    assert host.stage(SHA, host._hash(plan))["status"] == "STAGED"
    assert setup.t.config.stat().st_ino == config_inode
    assert setup.model.effects == []


def test_stage_refuses_changed_partial_destination(setup, monkeypatch):
    plan = host.preview(SHA)
    actual_write = host._write
    def interrupted(path, data, **kwargs):
        if path == setup.t.plist:
            raise OSError("interrupted")
        return actual_write(path, data, **kwargs)
    monkeypatch.setattr(host, "_write", interrupted)
    with pytest.raises(OSError):
        host.stage(SHA, host._hash(plan))
    monkeypatch.setattr(host, "_write", actual_write)
    host._write(setup.t.config, b'{"changed":true}\n')
    with pytest.raises(host.LifecycleError, match="DESTINATION_CHANGED"):
        host.stage(SHA, host._hash(plan))
    assert setup.model.effects == []


@pytest.mark.parametrize("change", ["key", "store", "project", "source", "python", "policy_size"])
def test_changed_prerequisite_refuses_before_launch(setup, change):
    digest, _ = staged(setup)
    if change == "key":
        Path(setup.document["action_key_file"]).write_text("8" * 64 + "\n")
    elif change in {"store", "project"}:
        field = "artifact_directory" if change == "store" else "project_root"
        directory = Path(setup.document[field])
        directory.rename(directory.with_name(directory.name + "-original"))
        directory.mkdir(mode=0o700)
    elif change in {"source", "python"}:
        config = copy.deepcopy(setup.document)
        config["browser"]["source_root" if change == "source" else "python_executable"] = "/foreign"
        host._write(setup.t.config, host._encoded(config))
    else:
        with Path(setup.document["policy_file"]).open("a") as stream:
            stream.write(" " * 65536)
    with pytest.raises((host.LifecycleError, service.ServiceConfigurationError)):
        host.start(digest)
    assert setup.model.effects == []


def test_start_requires_signed_ready_and_revisits_one_original_attempt(setup):
    digest, _ = staged(setup)
    setup.model.ready = None
    first = host.start(digest)
    assert first["phase"] == "KICKSTART_ISSUED" and first["runtime_ready"] is None
    assert [x[1] for x in setup.model.effects] == ["bootstrap", "kickstart"]
    setup.model.ready = True
    assert host.start(digest)["runtime_ready"] is True
    assert [x[1] for x in setup.model.effects] == ["bootstrap", "kickstart"]


def test_ambiguous_bootstrap_never_kickstarts_registered_waiting_job(setup):
    digest, _ = staged(setup)
    setup.model.bootstrap_unknown = True
    first = host.start(digest)
    assert first["phase"] == "BOOTSTRAP_ISSUED"
    second = host.start(digest)
    assert second["phase"] == "BOOTSTRAP_ISSUED"
    assert [x[1] for x in setup.model.effects] == ["bootstrap"]


def test_clean_stop_signals_then_records_exit_before_bootout(setup):
    digest, _ = staged(setup)
    assert host.start(digest)["runtime_ready"] is True
    result = host.stop(digest)
    assert result["phase"] == "STOPPED" and result["exit_code"] == 0
    assert [x[1] for x in setup.model.effects] == ["bootstrap", "kickstart", "kill", "bootout"]
    assert host.stop(digest)["phase"] == "STOPPED"
    assert len(setup.model.effects) == 4


@pytest.mark.parametrize("code,reason", [(2, "CONFIGURATION_REFUSED"), (3, "PHYSICAL_DRAIN_INCOMPLETE"),
                                        (4, "CLEANUP_UNCERTAIN"), (5, "SHUTDOWN_UNQUALIFIED"),
                                        (None, "SHUTDOWN_UNQUALIFIED")])
def test_stop_retains_precise_exit_holds_across_repeated_calls_and_reboot(setup, code, reason):
    digest, _ = staged(setup)
    host.start(digest)
    setup.model.exit_code = code
    result = host.stop(digest)
    assert result["phase"] == "HOLD" and result["hold"].endswith(reason)
    setup.model.boot = "later-boot"
    setup.model.observed = None
    assert host.start(digest)["phase"] == host.stop(digest)["phase"] == "HOLD"
    assert [x[1] for x in setup.model.effects] == ["bootstrap", "kickstart", "kill"]


@pytest.mark.parametrize("code,phase", [(0, "CLEAN_EXIT"), (3, "HOLD"), (4, "HOLD")])
def test_spontaneous_exit_is_classified_without_another_launch(setup, code, phase):
    digest, _ = staged(setup)
    host.start(digest)
    setup.model.observed = setup.model.waiting(1, code)
    setup.model.absent = True
    before = setup.t.lifecycle.read_bytes()
    assert host.inspect()["phase"] == phase
    assert setup.t.lifecycle.read_bytes() == before
    assert host.start(digest)["phase"] == phase
    assert [x[1] for x in setup.model.effects] == ["bootstrap", "kickstart"]
    result = host.stop(digest)
    assert result["phase"] == ("STOPPED" if code == 0 else "HOLD")
    assert "kill" not in [x[1] for x in setup.model.effects]


def test_pending_stop_observes_original_without_resending_signal(setup):
    digest, _ = staged(setup)
    host.start(digest)
    setup.model.stop_pending = True
    assert host.stop(digest)["phase"] == "STOP_ISSUED"
    assert host.stop(digest)["phase"] == "STOP_ISSUED"
    assert [x[1] for x in setup.model.effects].count("kill") == 1
    setup.model.observed = setup.model.waiting(1, 0)
    setup.model.absent = True
    assert host.stop(digest)["phase"] == "STOPPED"


@pytest.mark.parametrize("replacement", ["running", "boot", "runs"])
def test_clean_exit_record_cannot_bootout_a_replacement_generation(setup, replacement):
    digest, _ = staged(setup)
    host.start(digest)
    state = host._read_state(setup.t)
    host._save(setup.t, state, phase="CLEAN_EXIT", exit_code=0)
    setup.model.observed = setup.model.waiting(1, 0)
    setup.model.absent = True
    if replacement == "running":
        setup.model.observed.update(state="running", pid=445552)
    elif replacement == "boot":
        setup.model.boot = "later-boot"
    else:
        setup.model.observed["runs"] = 2
    assert host.stop(digest)["phase"] == "HOLD"
    assert "bootout" not in [x[1] for x in setup.model.effects]


def test_unknown_bootout_is_observed_without_repeat(setup):
    digest, _ = staged(setup)
    host.start(digest)
    setup.model.bootout_unknown = True
    assert host.stop(digest)["phase"] == "BOOTOUT_ISSUED"
    assert host.stop(digest)["phase"] == "BOOTOUT_ISSUED"
    setup.model.observed = None
    assert host.stop(digest)["phase"] == "STOPPED"
    assert [x[1] for x in setup.model.effects].count("bootout") == 1


def test_shared_lifecycle_lock_refuses_concurrent_mutation(setup):
    digest, _ = staged(setup)
    with owner._owned_lifecycle_mutex(setup.t.lock, subject="Workbench test"):
        with pytest.raises(SystemExit, match="concurrent"):
            host.start(digest)
    assert setup.model.effects == []


@pytest.mark.parametrize("mutation", ["duplicate_pid", "wrong_path", "signal_nested", "unknown_failure"])
def test_strict_launchd_observation_never_infers_absence(setup, mutation):
    model = setup.model
    model.observed = dict(state="running", pid=445551, runs=1, exit_code=None, never_exited=True, signal=None)
    result = model.response()
    if mutation == "signal_nested":
        result.stdout = result.stdout.replace("\tcoalition = {", "\tcoalition = {\n\t\tlast terminating signal = 9")
        assert host.parse_observation(result, setup.t)["signal"] is None
        return
    if mutation == "duplicate_pid":
        result.stdout = result.stdout.replace("\tpid = 445551", "\tpid = 445551\n\tpid = 444444")
    elif mutation == "wrong_path":
        result.stdout = result.stdout.replace(str(setup.t.plist), "/foreign.plist")
    else:
        result.returncode, result.stdout, result.stderr = 1, "", "temporary launchd failure"
    with pytest.raises(host.LifecycleError, match="OBSERVATION_UNKNOWN"):
        host.parse_observation(result, setup.t)


def test_workbench_cli_cannot_select_arbitrary_target():
    parser = owner.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["workbench-start", "--expected-install-sha256", "a" * 64, "--account", "other"])


def test_v5_install_pins_enrollment_and_allows_secret_and_token_rotation(setup):
    from dataclasses import asdict, replace
    from integrations.mastermind_browser_plugin.workbench_credentials import ENROLLMENT_SCHEMA
    from tests.test_mastermind_browser_workbench_transport import Host
    inputs = setup.t.home / "inputs"
    remote = Host("host-plan-credential")
    route = replace(remote.route, credential_file=inputs / "rotating-token.json")
    routes = inputs / "routes.json"
    routes.write_text(json.dumps({"schema": "mastermind.browser_fabric_routes.v1", "routes": [
        {**asdict(route), "credential_file": str(route.credential_file)}]}))
    routes.chmod(0o600)
    secret = inputs / "rotating-secret"
    secret.write_text("synthetic-secret-one")
    secret.chmod(0o600)
    enrollment = inputs / "credential-enrollment.json"
    enrolled = {"schema": ENROLLMENT_SCHEMA, "credentials": [{
        "host_ref": route.host_ref, "client_id": remote.client_id, "client_secret_file": str(secret),
        "policy": asdict(remote.policy)}]}
    enrollment.write_text(json.dumps(enrolled))
    enrollment.chmod(0o600)
    setup.document.update(schema=service.SERVICE_SCHEMA_V5, browser_fabric_routes_file=str(routes),
                          browser_fabric_credentials_file=str(enrollment))
    host._write(setup.t.candidate, host._encoded(setup.document))
    digest, plan = staged(setup)
    assert "credentials" in plan["dependencies"]
    secret.write_text("synthetic-secret-two")
    route.credential_file.write_text("synthetic-new-token")
    route.credential_file.chmod(0o600)
    assert host._verify_install(setup.t)[0]["install_sha256"] == digest
    assert host.preview(SHA) == plan
    enrolled["credentials"][0]["client_id"] = "changed-enrollment"
    enrollment.write_text(json.dumps(enrolled))
    with pytest.raises(host.LifecycleError):
        host._verify_install(setup.t)
