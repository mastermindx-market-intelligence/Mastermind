"""Closed APPLICATION-purpose transport control: qualification, stage, apply, reconcile.

The fixtures are real: a clean protected Git checkout, an exact-SHA sealed
release, a real upstream source checkout, real file hashes, real locks, real
atomic writes and strict input parsing. Only the OS service/process
observations and the launchctl commands are substituted.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest

from ops.executive_os import application_tunnel_control as control
from ops.executive_os import os_tunnel_entry
from ops.executive_os import release_manifest

REPO = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "ops/executive_os/application_tunnel_entry.py",
    "ops/executive_os/os_tunnel_entry.py",
    "ops/executive_os/application_tunnel_control.py",
    "control_plane/fs_security.py",
    "ops/executive_os/com.mastermind.executive.fabric-application-tunnel.plist.template",
)
EVIDENCE_PATHS = (
    "share/settings/users.go",
    "share/settings/user.go",
    "share/settings/remote.go",
    "server/server_handler.go",
)
FINGERPRINT = "F" * 43 + "="
CLIENT_SHA = "b" * 64
SERVER_SHA = "c" * 64
INCUMBENT = {
    "mastermind-os:ossecret": ["^R:127\\.0\\.0\\.1:49160$"],
    "operator:opsecret": ["^0\\.0\\.0\\.0:3000$"],
}

pytestmark = pytest.mark.skipif(os.geteuid() != 0,
                                reason="the closed transport mutation path requires root custody")


def _git(repo, *args):
    completed = subprocess.run(["/usr/bin/git", "-C", str(repo), *args],
                               capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def _own(path, mode):
    os.chmod(path, mode)
    os.chown(path, 0, 0)


def _commit_repository(root, files):
    repo = root
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Application Tunnel Fixture")
    _git(repo, "config", "commit.gpgsign", "false")
    for name, payload in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    _git(repo, "update-ref", "refs/remotes/origin/master", commit)
    return repo, commit, tree


def _source_repository(root):
    files = {name: (REPO / name).read_bytes() for name in SOURCE_FILES}
    return _commit_repository(root, files)


def _upstream_repository(root):
    files = {name: ("// upstream fixture evidence for %s\n" % name).encode()
             for name in EVIDENCE_PATHS}
    repo, commit, tree = _commit_repository(root, files)
    digests = {name: control.digest(payload) for name, payload in files.items()}
    return repo, commit, tree, digests


def _sealed_release(root, commit, tree):
    release = root
    release.mkdir(parents=True)
    for name in SOURCE_FILES:
        target = release / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / name).read_bytes())
    for directory in sorted((p for p in release.rglob("*") if p.is_dir()), reverse=True):
        _own(directory, 0o755)
    _own(release, 0o755)
    for name in SOURCE_FILES:
        _own(release / name, 0o444)
    release_manifest.create(release, commit, tree)
    return release


class FakeSystem:
    """Substitutes only the OS service/process observations and commands."""

    def __init__(self, *, client_sha=CLIENT_SHA, server_sha=SERVER_SHA,
                 client_version="1.12.0", server_version="1.12.0",
                 unit=None, listeners=(), processes=(), launchd=None,
                 bootstrap_returncode=0, bootout_returncode=0,
                 label=control.LABEL, autoload=True, pid=5150):
        self.calls = []
        self.label = label
        self.autoload = autoload
        self.pid = pid
        self.client_sha = client_sha
        self.server_sha = server_sha
        self.client_version = client_version
        self.server_version = server_version
        self.unit = unit if unit is not None else {"active": True, "main_pid": 4242, "argv": []}
        self._listeners = list(listeners)
        self._processes = list(processes)
        self._launchd = launchd if launchd is not None else {}
        self.bootstrap_returncode = bootstrap_returncode
        self.bootout_returncode = bootout_returncode

    def launchctl_print(self, label):
        return self._launchd.get(label, (False, {}))

    def launchctl_bootstrap(self, plist):
        self.calls.append(("bootstrap", str(plist)))
        if self.bootstrap_returncode == 0 and self.autoload:
            arguments = control._plist_arguments(Path(plist).read_bytes())
            self._launchd[self.label] = (True, {"arguments": arguments, "pid": self.pid})
        return {"returncode": self.bootstrap_returncode, "stderr": ""}

    def launchctl_bootout(self, label):
        self.calls.append(("bootout", label))
        if self.bootout_returncode == 0:
            self._launchd.pop(label, None)
        return {"returncode": self.bootout_returncode, "stderr": ""}

    def listeners(self, port):
        return list(self._listeners)

    def process_argv(self, pid):
        return []

    def process_matches(self, pid, expected):
        if pid == self.unit.get("main_pid"):
            return self.unit.get("argv") == expected
        for loaded, info in self._launchd.values():
            if loaded and type(pid) is int and pid > 0 and info.get("pid") == pid:
                return (expected[0].endswith("/chisel") and expected[1:] == [
                    "client", "--fingerprint", FINGERPRINT, "--keepalive", "20s",
                    control.SERVER, control.REVERSE_TARGET])
        return False

    def processes(self):
        return list(self._processes)

    def binary_identity(self, path):
        if "transports" in str(path):
            return {"sha256": self.client_sha, "output": self.client_version}
        return {"sha256": self.server_sha, "output": self.server_version}

    def unit_identity(self, unit):
        return self.unit

    def process_image_identity(self, pid):
        return {"pid": pid, "start_id": "fixture-original-start", "sha256": self.server_sha}


class Harness:
    """One real fixture: protected source, sealed release and upstream evidence."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.source, self.commit, self.tree = _source_repository(self.root / "source")
        self.upstream, self.upstream_commit, self.upstream_tree, self.upstream_files = \
            _upstream_repository(self.root / "upstream")
        self.release = _sealed_release(self.root / "release", self.commit, self.tree)
        self.paths = control.Paths.fixture(self.root / "host")
        for directory in (self.paths.executive_root, self.paths.executive_root / "config",
                          self.paths.plist.parent, self.paths.server_authfile.parent,
                          self.paths.server_binary.parent):
            directory.mkdir(parents=True, exist_ok=True)
            _own(directory, 0o755)
        self.qualification_path = self.write_qualification()

    def qualification(self, **overrides):
        record = {
            "schema": control.QUALIFICATION_SCHEMA,
            "server_fingerprint": FINGERPRINT,
            "client_binary": {"sha256": CLIENT_SHA, "version": "1.12.0", "build": "1.12.0"},
            "server_binary": {"sha256": SERVER_SHA, "version": "1.12.0", "build": "1.12.0"},
            "semantics": {"authfile_rename_reload": True, "new_tunnel_acl_refresh": True},
            "evidence": {
                "repository": control.UPSTREAM_REPOSITORY,
                "commit": self.upstream_commit,
                "tree": self.upstream_tree,
                "paths": list(EVIDENCE_PATHS),
                "files": dict(self.upstream_files),
                "mode": "source-tree",
                "source_root": str(self.upstream),
            },
            "custody": "root-owned source attestation; not a remote signature",
        }
        record.update(overrides)
        return record

    def write_qualification(self, record=None):
        path = self.root / "qualification.json"
        path.write_bytes(control.canonical(record if record is not None else self.qualification()))
        _own(path, 0o600)
        return path

    def write_authfile(self, entries=None, mode=0o600):
        path = self.paths.server_authfile
        path.write_bytes(json.dumps(entries if entries is not None else INCUMBENT, indent=2).encode())
        _own(path, mode)
        return path

    def stage(self, **overrides):
        arguments = {
            "source_repo": self.source,
            "source_sha": self.commit,
            "release_root": self.release,
            "release_commit_sha": self.commit,
            "release_tree_sha": self.tree,
            "qualification_path": self.qualification_path,
            "paths": self.paths,
            "system": FakeSystem(),
        }
        arguments.update(overrides)
        return control.stage(**arguments)

    def server_receipt(self):
        """Apply the server grant for this operation and return its receipt path."""
        self.write_authfile()
        raw, expected = self.bundle()
        bundle_path = self.root / "bundle.json"
        bundle_path.write_bytes(raw)
        _own(bundle_path, 0o600)
        system = FakeSystem(unit={"active": True, "main_pid": 4242,
                                  "argv": control._server_expected_argv(self.paths)})
        receipt = control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                                       paths=self.paths, system=system)
        path = self.root / "server-receipt.json"
        path.write_bytes(control.canonical(receipt))
        _own(path, 0o600)
        return path

    def bundle(self):
        stage = self.paths.operation_root / "stage"
        with control.publication.private(stage) as area:
            raw = area.read("server-bundle.json")
        return raw, control.digest(raw)


@pytest.fixture(scope="session")
def sealed_root():
    """A root-owned, non-world-writable base for the sealed temp fixtures.

    The incumbent sealed-path policy refuses a world-writable ancestor, so the
    temporary fixtures cannot live under a world-writable temporary directory.
    """
    if os.geteuid() != 0:
        pytest.skip("requires the isolated root-owned transport fixture")
    base = Path(os.environ.get("MM_APPLICATION_TRANSPORT_TEST_ROOT", str(Path.home())))
    control.assets._sealed_path(base, directory=True)
    with tempfile.TemporaryDirectory(prefix="mmx-application-tunnel-", dir=base) as directory:
        root = Path(directory)
        _own(root, 0o755)
        yield root


@pytest.fixture
def harness(sealed_root):
    """One real protected source, sealed release and upstream evidence fixture."""
    root = Path(tempfile.mkdtemp(prefix="case-", dir=str(sealed_root)))
    try:
        yield Harness(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------- qualification


def test_qualification_accepts_a_source_backed_record(harness):
    record = control._qualification(control.canonical(harness.qualification()))
    assert record["semantics"]["authfile_rename_reload"] is True
    assert record["evidence"]["mode"] == "source-tree"


@pytest.mark.parametrize("mutate,expected", [
    (lambda r: r.update(schema="other"), "qualification schema refused"),
    (lambda r: r.update(custody="handwritten"), "qualification custody refused"),
    (lambda r: r.update(server_fingerprint="short"), "qualification server fingerprint refused"),
    (lambda r: r["client_binary"].update(sha256="Z" * 64), "qualification binary digest refused"),
    (lambda r: r["client_binary"].update(version="1.11.8"), "binary semantics older"),
    (lambda r: r["server_binary"].update(version="1.11.8"), "binary semantics older"),
    (lambda r: r["semantics"].update(authfile_rename_reload=False), "unsupported authfile semantics refused"),
    (lambda r: r["semantics"].update(new_tunnel_acl_refresh=False), "unsupported authfile semantics refused"),
    (lambda r: r["evidence"].update(repository="https://example.invalid/chisel"),
     "qualification evidence repository refused"),
    (lambda r: r["evidence"].update(commit="zz"), "qualification evidence commit refused"),
    (lambda r: r["evidence"].update(mode="attested"), "attested evidence must not claim"),
    (lambda r: r["evidence"].update(source_root=None), "evidence source root refused"),
])
def test_qualification_refuses_missing_older_or_unverified_semantics(harness, mutate, expected):
    record = harness.qualification()
    mutate(record)
    with pytest.raises(ValueError) as error:
        control._qualification(control.canonical(record))
    assert expected in str(error.value)


def test_qualification_refuses_evidence_bytes_that_drift(harness):
    record = harness.qualification()
    record["evidence"]["files"][EVIDENCE_PATHS[0]] = "0" * 64
    with pytest.raises(ValueError) as error:
        control._qualification(control.canonical(record))
    assert "evidence source bytes differ" in str(error.value)


def test_qualification_refuses_evidence_from_another_checkout(harness):
    record = harness.qualification()
    record["evidence"]["tree"] = "0" * 40
    with pytest.raises(ValueError) as error:
        control._qualification(control.canonical(record))
    assert "evidence source identity differs" in str(error.value)


def test_qualification_refuses_an_evidence_commit_that_does_not_exist(harness):
    record = harness.qualification()
    record["evidence"]["commit"] = "0" * 40
    record["evidence"]["tree"] = "0" * 40
    with pytest.raises(ValueError) as error:
        control._qualification(control.canonical(record))
    assert "evidence source checkout refused" in str(error.value)


def test_a_version_string_alone_is_not_qualification(harness):
    record = harness.qualification()
    record["evidence"] = {"repository": control.UPSTREAM_REPOSITORY, "commit": "0" * 40,
                          "tree": "0" * 40, "paths": [], "files": {}, "mode": "attested",
                          "source_root": None}
    with pytest.raises(ValueError) as error:
        control._qualification(control.canonical(record))
    assert "qualification evidence paths refused" in str(error.value)


# ------------------------------------------------------------------ authfile


def test_authfile_merge_adds_exactly_one_anchored_acl_and_preserves_every_value():
    raw = json.dumps(INCUMBENT, indent=2).encode()
    entries, merged, changed = control._merge_authfile(raw, "mastermind-fabric-app:secret")
    assert changed is True
    assert entries == INCUMBENT
    assert merged["mastermind-fabric-app:secret"] == [r"^R:127\.0\.0\.1:50142$"]
    for key, value in INCUMBENT.items():
        assert merged[key] == value
    assert len(merged) == len(INCUMBENT) + 1


@pytest.mark.parametrize("entries,expected", [
    ({"mastermind-os:x": [""]}, "authfile wildcard refused"),
    ({"mastermind-os:x": ["*"]}, "authfile wildcard refused"),
    ({"mastermind-os:x": ["(?=R:127.0.0.1:50142)R:127.0.0.1:50142"]}, "authfile pattern refused"),
    ({"mastermind-os:x": ["^R:127\\.0\\.0\\.1:50142$"]},
     "an existing grant already authorizes the application listener"),
    ({"mastermind-os:x": ["50142"]},
     "an existing grant already authorizes the application listener"),
    ({"mastermind-fabric-app:other": ["^R:127\\.0\\.0\\.1:49160$"]},
     "conflicting existing application identity refused"),
    ({"nocolon": ["^R:127\\.0\\.0\\.1:49160$"]}, "authfile entry refused"),
    ({"mastermind-os:x": "^R:127\\.0\\.0\\.1:49160$"}, "authfile entry refused"),
    ({"mastermind-os:x": ["^R:127\\.0\\.0\\.1:49160$", "^R:127\\.0\\.0\\.1:50142$"]},
     "an existing grant already authorizes the application listener"),
])
def test_authfile_merge_refuses_wildcard_unanchored_or_conflicting_grants(entries, expected):
    raw = json.dumps(entries).encode()
    with pytest.raises(ValueError) as error:
        control._merge_authfile(raw, "mastermind-fabric-app:secret")
    assert expected in str(error.value)


def test_authfile_merge_refuses_duplicate_keys_and_nonfinite_values():
    with pytest.raises(ValueError) as error:
        control._merge_authfile(b'{"a:b": ["^x$"], "a:b": ["^y$"]}', "mastermind-fabric-app:s")
    assert "duplicate JSON key" in str(error.value)
    with pytest.raises(ValueError) as error:
        control._merge_authfile(b'{"a:b": ["^x$"], "c:d": NaN}', "mastermind-fabric-app:s")
    assert "nonfinite JSON" in str(error.value)


def test_authfile_merge_is_idempotent_for_its_own_exact_grant():
    raw = json.dumps({"mastermind-fabric-app:secret": [r"^R:127\.0\.0\.1:50142$"]}).encode()
    entries, merged, changed = control._merge_authfile(raw, "mastermind-fabric-app:secret")
    assert changed is False
    assert merged == entries


def test_authfile_refusal_never_leaks_a_secret_key():
    secret = "mastermind-fabric-app:supersecretvalue"
    raw = json.dumps({secret: ["^R:127\\.0\\.0\\.1:50142$"], "other:one": ["50142"]}).encode()
    with pytest.raises(ValueError) as error:
        control._merge_authfile(raw, "mastermind-fabric-app:othervalue")
    assert "supersecretvalue" not in str(error.value)
    assert "othervalue" not in str(error.value)


# --------------------------------------------------------------------- stage


def test_stage_creates_one_operation_with_a_single_dedicated_credential(harness):
    receipt = harness.stage()
    assert receipt["state"] == "STAGED"
    assert receipt["operation_id"] == control.operation_identity()
    assert receipt["tunnel_proven"] is False and receipt["application_proven"] is False
    stage = harness.paths.operation_root / "stage"
    with control.publication.private(stage) as area:
        credential = area.read("credential.auth")
        intent = json.loads(area.read("intent.json"))
        bundle = json.loads(area.read("server-bundle.json"))
    assert credential.startswith(b"mastermind-fabric-app:")
    assert credential.count(b":") == 1
    assert intent["credential_state"] == "PENDING"
    assert intent["relay_port"] == 50142 and intent["target_port"] == 4142
    assert bundle["remotes"] == [r"^R:127\.0\.0\.1:50142$"]
    assert bundle["auth"] == credential.decode()


def test_repeated_stage_never_generates_another_credential_or_rewrites(harness):
    first = harness.stage()
    stage = harness.paths.operation_root / "stage"
    with control.publication.private(stage) as area:
        credential = area.read("credential.auth")
    second = harness.stage()
    with control.publication.private(stage) as area:
        assert area.read("credential.auth") == credential
    assert second["credential_digest"] == first["credential_digest"]
    assert second["stage_digest"] == first["stage_digest"]
    assert second["bundle_digest"] == first["bundle_digest"]


def test_stage_refuses_to_rotate_the_credential(harness):
    harness.stage()
    other = harness.root / "other.auth"
    other.write_bytes(b"mastermind-fabric-app:" + b"z" * 43)
    _own(other, 0o600)
    with pytest.raises(ValueError) as error:
        harness.stage(credential_path=other)
    assert "credential rotation refused" in str(error.value)


def test_stage_refuses_a_different_operation_on_the_same_purpose(harness):
    harness.stage()
    record = harness.qualification()
    record["server_fingerprint"] = "G" * 43 + "="
    harness.write_qualification(record)
    with pytest.raises(ValueError) as error:
        harness.stage()
    assert "an existing operation differs" in str(error.value)


def test_stage_refuses_an_unqualified_binary_tuple(harness):
    record = harness.qualification()
    record["client_binary"]["version"] = "1.11.0"
    harness.write_qualification(record)
    with pytest.raises(ValueError) as error:
        harness.stage()
    assert "binary semantics older" in str(error.value)


def test_stage_refuses_a_release_that_is_not_the_protected_source(harness):
    with pytest.raises(ValueError) as error:
        harness.stage(release_commit_sha="0" * 40, release_tree_sha="0" * 40)
    assert "release" in str(error.value).lower()


# -------------------------------------------------------------- apply server


def test_apply_server_merges_one_acl_and_preserves_the_incumbent_authfile(harness):
    harness.stage()
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    receipt = control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                                   paths=harness.paths, system=system)
    assert receipt["state"] == "GRANT_FILE_APPLIED"
    assert receipt["grant_file_applied"] is True
    assert receipt["server_reload_proven"] is False
    assert receipt["tunnel_proven"] is False
    assert receipt["application_proven"] is False
    assert receipt["preserved_entries"] == len(INCUMBENT)
    merged = json.loads(harness.paths.server_authfile.read_bytes())
    assert merged["mastermind-os:ossecret"] == INCUMBENT["mastermind-os:ossecret"]
    assert merged["operator:opsecret"] == INCUMBENT["operator:opsecret"]
    assert len(merged) == len(INCUMBENT) + 1
    added = [key for key in merged if key not in INCUMBENT]
    assert len(added) == 1
    assert merged[added[0]] == [r"^R:127\.0\.0\.1:50142$"]


def test_apply_server_never_touches_the_server_key_or_the_unit_arguments(harness):
    harness.stage()
    harness.write_authfile()
    harness.paths.server_keyfile.write_bytes(b"server key material")
    _own(harness.paths.server_keyfile, 0o600)
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                          paths=harness.paths, system=system)
    assert harness.paths.server_keyfile.read_bytes() == b"server key material"


def test_apply_server_refuses_a_foreign_listener_on_the_application_port(harness):
    harness.stage()
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)},
                        listeners=[{"address": "127.0.0.1:50142", "pid": 999}])
    with pytest.raises(ValueError) as error:
        control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                             paths=harness.paths, system=system)
    assert "already held by another grant" in str(error.value)
    merged = json.loads(harness.paths.server_authfile.read_bytes())
    assert len(merged) == len(INCUMBENT)


def test_apply_server_refuses_a_server_binary_that_drifted(harness):
    harness.stage()
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(server_sha="d" * 64,
                        unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    with pytest.raises(ValueError) as error:
        control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                             paths=harness.paths, system=system)
    assert "server binary digest differs" in str(error.value)
    assert len(json.loads(harness.paths.server_authfile.read_bytes())) == len(INCUMBENT)


def test_apply_server_refuses_a_different_unit_or_inactive_server(harness):
    harness.stage()
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)[:-1]})
    with pytest.raises(ValueError) as error:
        control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                             paths=harness.paths, system=system)
    assert "unit arguments differ" in str(error.value)


# -------------------------------------------------------------- apply client


def test_apply_client_installs_only_the_three_closed_targets(harness):
    harness.stage()
    receipt = control.apply_client(paths=harness.paths, system=FakeSystem())
    assert receipt["state"] == "CLIENT_FILES_APPLIED"
    assert receipt["installed"] is True
    assert receipt["service_started"] is False
    assert set(receipt["targets"]) == {"config", "credential", "plist"}
    assert harness.paths.config.is_file()
    assert harness.paths.credential.is_file()
    assert harness.paths.plist.is_file()
    assert oct(harness.paths.credential.stat().st_mode & 0o777) == "0o400"
    assert oct(harness.paths.config.stat().st_mode & 0o777) == "0o444"
    assert oct(harness.paths.plist.stat().st_mode & 0o777) == "0o444"
    installed = json.loads(harness.paths.config.read_bytes())
    assert installed["schema"] == os_tunnel_entry.APPLICATION_SCHEMA
    assert installed["binary_sha256"] == CLIENT_SHA
    assert "relay_port" not in installed and "target_port" not in installed
    plist = harness.paths.plist.read_text()
    assert control.LABEL in plist
    assert "application-tunnel.auth" not in plist
    assert "AUTH" not in plist


def test_apply_client_is_idempotent_and_does_not_start_the_service(harness):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    second = control.apply_client(paths=harness.paths, system=FakeSystem())
    assert set(second["targets"].values()) == {"ALREADY_APPLIED"}


def test_apply_client_refuses_a_foreign_target(harness):
    harness.stage()
    harness.paths.config.parent.mkdir(parents=True, exist_ok=True)
    harness.paths.config.write_bytes(b"foreign bytes")
    _own(harness.paths.config, 0o444)
    with pytest.raises(ValueError) as error:
        control.apply_client(paths=harness.paths, system=FakeSystem())
    assert "foreign target" in str(error.value)
    assert harness.paths.config.read_bytes() == b"foreign bytes"


def test_apply_client_refuses_a_target_that_appeared_after_the_stage(harness):
    harness.stage()
    harness.paths.config.parent.mkdir(parents=True, exist_ok=True)
    harness.paths.config.write_bytes(b"drifted bytes")
    _own(harness.paths.config, 0o444)
    with pytest.raises(ValueError) as error:
        control.apply_client(paths=harness.paths, system=FakeSystem())
    assert "a foreign target is present" in str(error.value)


def test_apply_client_refuses_observed_drift_of_a_staged_preimage(harness):
    harness.paths.config.parent.mkdir(parents=True, exist_ok=True)
    harness.paths.config.write_bytes(b"original staged bytes")
    _own(harness.paths.config, 0o444)
    harness.stage()
    _own(harness.paths.config, 0o600)
    harness.paths.config.write_bytes(b"drifted bytes")
    _own(harness.paths.config, 0o444)
    with pytest.raises(ValueError) as error:
        control.apply_client(paths=harness.paths, system=FakeSystem())
    assert "changed since the stage" in str(error.value)


def test_apply_client_refuses_a_release_that_no_longer_matches_the_source(harness):
    harness.stage()
    entry = harness.release / "ops/executive_os/application_tunnel_entry.py"
    entry.chmod(0o644)
    entry.write_bytes(entry.read_bytes() + b"\n# drift\n")
    os.chown(entry, 0, 0)
    with pytest.raises(ValueError) as error:
        control.apply_client(paths=harness.paths, system=FakeSystem())
    assert "release" in str(error.value).lower()


def test_the_imported_helper_closure_comes_from_that_same_sealed_release(harness):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    release = harness.release
    plist = harness.paths.plist.read_text()
    assert str(release / "ops/executive_os/application_tunnel_entry.py") in plist
    entries = {}
    for name in control.IMPORT_CLOSURE:
        entries[name] = control.digest((release / name).read_bytes())
    resolved = control._import_closure(release, harness.paths.python, entries)
    assert Path(resolved["entry"]).resolve() == (
        release / "ops/executive_os/application_tunnel_entry.py").resolve()
    assert Path(resolved["helper"]).resolve() == (
        release / "ops/executive_os/os_tunnel_entry.py").resolve()


def test_a_release_without_the_helper_closure_is_refused(harness):
    harness.stage()
    helper = harness.release / "ops/executive_os/os_tunnel_entry.py"
    helper.chmod(0o644)
    helper.unlink()
    os.chown(harness.release / "ops/executive_os", 0, 0)
    with pytest.raises(ValueError) as error:
        control.apply_client(paths=harness.paths, system=FakeSystem())
    assert "release" in str(error.value).lower()


def test_the_cli_exposes_no_target_path_purpose_or_endpoint_selector():
    parser = control.build_parser()
    commands = parser._subparsers._group_actions[0].choices
    options = set()
    for command in commands.values():
        for action in command._actions:
            options |= set(action.option_strings)
    for forbidden in ("--config", "--credential-source", "--plist", "--authfile", "--purpose",
                      "--relay-port", "--target-port", "--host", "--server", "--executable",
                      "--command", "--label", "--port", "--proxy", "--socks", "--target"):
        assert forbidden not in options
    assert "--source-repo" in options and "--release-root" in options


# ------------------------------------------------------------------ reconcile


def test_reconcile_reports_each_target_disposition(harness):
    harness.stage()
    receipt = control.reconcile(paths=harness.paths, system=FakeSystem())
    assert receipt["targets"] == {"config": "NOT_APPLIED", "credential": "NOT_APPLIED",
                                  "plist": "NOT_APPLIED"}
    assert receipt["grant_state"] == "NOT_PROVIDED"
    assert receipt["credential_state"] == "CREATED"
    assert receipt["tunnel_proven"] is False
    control.apply_client(paths=harness.paths, system=FakeSystem())
    receipt = control.reconcile(paths=harness.paths, system=FakeSystem())
    assert receipt["targets"] == {"config": "APPLIED", "credential": "APPLIED",
                                  "plist": "APPLIED"}


def test_reconcile_reports_a_conflicting_target(harness):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    harness.paths.config.chmod(0o644)
    harness.paths.config.write_bytes(b"foreign bytes")
    os.chown(harness.paths.config, 0, 0)
    receipt = control.reconcile(paths=harness.paths, system=FakeSystem())
    assert receipt["targets"]["config"] == "CONFLICT"
    assert receipt["state"] == "RECONCILIATION_REQUIRED"


def test_public_receipts_redact_credential_material(harness):
    harness.stage()
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    server = control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                                  paths=harness.paths, system=system)
    client = control.apply_client(paths=harness.paths, system=FakeSystem())
    stage = harness.paths.operation_root / "stage"
    with control.publication.private(stage) as area:
        credential = area.read("credential.auth").decode()
    secret = credential.split(":", 1)[1]
    for payload in (control.canonical(server), control.canonical(client)):
        assert secret.encode() not in payload
        assert credential.encode() not in payload


def test_a_non_root_caller_cannot_stage_or_mutate(harness, monkeypatch):
    # A container can have only UID0 mapped; changing to an unmapped kernel UID
    # cannot test the application refusal. Substitute only the OS UID reading.
    # Every real operation must refuse before even opening a supplied path.
    monkeypatch.setattr(control.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(control, "_read_root_private", lambda *a, **kw: pytest.fail("read before root refusal"))
    calls = [lambda: harness.stage(),
             lambda: control.apply_server(bundle_path="/unopened", expected_digest="0" * 64),
             lambda: control.reconcile_server(bundle_path="/unopened", expected_digest="0" * 64),
             lambda: control.apply_client(), lambda: control.reconcile(),
             lambda: control.start_client(server_receipt="/unopened"), lambda: control.stop_client()]
    for call in calls:
        with pytest.raises(ValueError, match="root custody required"):
            call()
    assert not harness.paths.operation_root.exists()


def _server_request(harness):
    harness.stage()
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle = harness.root / "original-bundle.json"
    bundle.write_bytes(raw)
    _own(bundle, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    return dict(bundle_path=bundle, expected_digest=expected, paths=harness.paths, system=system)


def test_real_cli_stage_server_apply_and_reconciliation(harness, capsys):
    argv = ["stage", "--source-repo", str(harness.source), "--source-sha", harness.commit,
            "--release-root", str(harness.release), "--release-commit-sha", harness.commit,
            "--release-tree-sha", harness.tree, "--qualification", str(harness.qualification_path)]
    assert control.main(argv, paths=harness.paths, system=FakeSystem()) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "STAGED"
    harness.write_authfile()
    raw, expected = harness.bundle()
    bundle = harness.root / "cli-bundle.json"
    bundle.write_bytes(raw)
    _own(bundle, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    for command in ("apply-server", "reconcile-server"):
        assert control.main([command, "--bundle", str(bundle), "--expected-digest", expected],
                            paths=harness.paths, system=system) == 0
        receipt = json.loads(capsys.readouterr().out)
        assert receipt["state"] == "GRANT_FILE_APPLIED"
        assert receipt["source"]["sha"] == harness.commit
        assert not receipt["server_reload_proven"]


def test_server_repeat_keeps_original_preimage_and_never_rewrites(harness, monkeypatch):
    request = _server_request(harness)
    before = control.digest(harness.paths.server_authfile.read_bytes())
    first = control.apply_server(**request)
    stamp = harness.paths.server_authfile.stat()
    monkeypatch.setattr(control, "_install", lambda *a, **kw: pytest.fail("duplicate grant write"))
    second = control.apply_server(**request)
    assert first == second
    assert second["authfile_preimage_sha256"] == before
    assert harness.paths.server_authfile.stat().st_ino == stamp.st_ino


def test_server_lost_ack_reconciles_original_committed_grant(harness, monkeypatch):
    request = _server_request(harness)
    write = control._write_once
    def fail_receipt(area, name, raw):
        if name == "server-receipt.json":
            raise RuntimeError("synthetic lost acknowledgement after target commit")
        return write(area, name, raw)
    monkeypatch.setattr(control, "_write_once", fail_receipt)
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        control.apply_server(**request)
    target = harness.paths.server_authfile.read_bytes()
    monkeypatch.setattr(control, "_write_once", write)
    monkeypatch.setattr(control, "_install", lambda *a, **kw: pytest.fail("reconciliation wrote a grant"))
    receipt = control.reconcile_server(**request)
    assert receipt["state"] == "GRANT_FILE_APPLIED"
    assert harness.paths.server_authfile.read_bytes() == target
    assert control.apply_server(**request) == receipt


def test_server_before_write_reconcile_is_read_only_and_apply_continues(harness, monkeypatch):
    request = _server_request(harness)
    install = control._install
    before = harness.paths.server_authfile.read_bytes()
    monkeypatch.setattr(control, "_install", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("before target write")))
    with pytest.raises(RuntimeError, match="before target"):
        control.apply_server(**request)
    assert control.reconcile_server(**request)["state"] == "NOT_APPLIED"
    assert harness.paths.server_authfile.read_bytes() == before
    monkeypatch.setattr(control, "_install", install)
    assert control.apply_server(**request)["state"] == "GRANT_FILE_APPLIED"


@pytest.mark.parametrize("boundary", ["server-intent.json", "bundle.json", "preimage.json", "candidate.json"])
def test_server_partial_staging_keeps_same_original_payload(harness, monkeypatch, boundary):
    request = _server_request(harness)
    write = control.publication.PrivateDirectory.write
    failed = []
    def interrupted(area, name, raw):
        value = write(area, name, raw)
        if name == boundary and not failed:
            failed.append(name)
            raise RuntimeError("after original stage boundary")
        return value
    monkeypatch.setattr(control.publication.PrivateDirectory, "write", interrupted)
    before = harness.paths.server_authfile.read_bytes()
    with pytest.raises(RuntimeError, match="original stage"):
        control.apply_server(**request)
    assert harness.paths.server_authfile.read_bytes() == before
    monkeypatch.setattr(control.publication.PrivateDirectory, "write", write)
    assert control.apply_server(**request)["state"] == "GRANT_FILE_APPLIED"
    assert control.reconcile_server(**request)["state"] == "GRANT_FILE_APPLIED"


def test_server_canonical_custody_follows_operation_not_bundle_directory(harness):
    request = _server_request(harness)
    first = control.apply_server(**request)
    other = harness.root / "redelivered.json"
    other.write_bytes(request["bundle_path"].read_bytes())
    _own(other, 0o600)
    assert control.apply_server(**dict(request, bundle_path=other)) == first
    assert (harness.paths.server_operation_root / "operation/server-intent.json").exists()
    assert not list(harness.root.glob(".application-tunnel-*"))


def test_server_drift_after_commit_is_never_overwritten(harness, monkeypatch):
    request = _server_request(harness)
    control.apply_server(**request)
    doc = json.loads(harness.paths.server_authfile.read_bytes())
    doc["another:secret"] = ["^elsewhere$"]
    harness.paths.server_authfile.write_bytes(control.canonical(doc))
    changed = harness.paths.server_authfile.read_bytes()
    monkeypatch.setattr(control, "_install", lambda *a, **kw: pytest.fail("foreign grant overwritten"))
    for action in (control.apply_server, control.reconcile_server):
        with pytest.raises(ValueError, match="conflicts"):
            action(**request)
    assert harness.paths.server_authfile.read_bytes() == changed


def test_server_uses_fixed_purpose_lock_and_rejects_an_alias(harness):
    request = _server_request(harness)
    with control._PurposeLock(harness.paths, create=True, server=True):
        with pytest.raises(ValueError, match="busy"):
            control.apply_server(**request)
    lock = harness.paths.server_operation_root / "purpose.lock"
    os.link(lock, lock.with_name("alias.lock"))
    with pytest.raises(ValueError, match="lock custody"):
        control.apply_server(**request)


def test_stage_persists_intent_before_mint_and_never_regenerates_after_interruption(harness, monkeypatch):
    def interrupted_mint(_):
        intent = harness.paths.operation_root / "stage/intent.json"
        assert intent.exists()
        raise RuntimeError("mint was interrupted")
    monkeypatch.setattr(control.secrets, "token_urlsafe", interrupted_mint)
    with pytest.raises(RuntimeError, match="mint was interrupted"):
        harness.stage()
    monkeypatch.setattr(control.secrets, "token_urlsafe", lambda *a: pytest.fail("second credential minted"))
    with pytest.raises(ValueError, match="regeneration refused"):
        harness.stage()


def test_unqualified_client_binary_refuses_before_secret_creation(harness, monkeypatch):
    monkeypatch.setattr(control.secrets, "token_urlsafe", lambda *a: pytest.fail("secret minted before qualification"))
    with pytest.raises(ValueError, match="client binary digest"):
        harness.stage(system=FakeSystem(client_sha="d" * 64))
    assert not harness.paths.operation_root.exists()


def test_existing_own_acl_does_not_hide_overlapping_foreign_acl():
    auth = "mastermind-fabric-app:" + "x" * 32
    with pytest.raises(ValueError, match="already authorizes"):
        control._merge_authfile(control.canonical({auth: [control.REMOTE_REGEX],
            "other:secret": [control.REMOTE_REGEX]}), auth)


def test_changed_lock_inode_refuses_before_server_target_write(harness, monkeypatch):
    request = _server_request(harness)
    observe = control._server_observation
    seen = []
    def changed(paths, system, qualification):
        result = observe(paths, system, qualification)
        if seen:
            lock = paths.server_operation_root / "purpose.lock"
            lock.rename(lock.with_name("retained.lock"))
            lock.write_bytes(b"")
            _own(lock, 0o600)
        seen.append(True)
        return result
    monkeypatch.setattr(control, "_server_observation", changed)
    before = harness.paths.server_authfile.read_bytes()
    with pytest.raises(ValueError, match="lock identity"):
        control.apply_server(**request)
    assert harness.paths.server_authfile.read_bytes() == before


def test_running_old_server_image_refuses_qualified_new_disk_binary(harness):
    request = _server_request(harness)
    request["system"].process_image_identity = lambda pid: {
        "pid": pid, "start_id": "original", "sha256": "d" * 64}
    before = harness.paths.server_authfile.read_bytes()
    with pytest.raises(ValueError, match="running server image"):
        control.apply_server(**request)
    assert harness.paths.server_authfile.read_bytes() == before


def test_actual_linux_process_image_observation_binds_this_running_python():
    if not sys.platform.startswith("linux"):
        pytest.skip("the server process-image owner is Linux")
    if os.readlink("/proc/self") != str(os.getpid()):
        pytest.skip("this fixture has a different proc filesystem PID namespace")
    result = control.System().process_image_identity(os.getpid())
    assert result["pid"] == os.getpid()
    assert result["start_id"].isdigit()
    assert result["sha256"] == control.digest(Path("/proc/self/exe").read_bytes())


def test_process_image_refuses_mismatched_namespace_before_process_read(monkeypatch):
    monkeypatch.setattr(control.os, "readlink", lambda _: "unmatched-namespace")
    monkeypatch.setattr(Path, "read_text", lambda *a, **kw: pytest.fail("read in mismatched process namespace"))
    with pytest.raises(ValueError, match="namespace differ"):
        control.System().process_image_identity(os.getpid())


@pytest.mark.parametrize("name", ["config", "credential", "plist"])
def test_settled_client_target_same_bytes_at_new_inode_is_foreign(harness, name, monkeypatch):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    target = getattr(harness.paths, name)
    before = target.stat()
    other = target.with_name(target.name + ".replacement")
    other.write_bytes(target.read_bytes())
    _own(other, before.st_mode & 0o777)
    other.replace(target)
    assert target.stat().st_ino != before.st_ino
    assert control.reconcile(paths=harness.paths, system=FakeSystem())["targets"][name] == "CONFLICT"
    monkeypatch.setattr(control, "_install", lambda *a, **kw: pytest.fail("settled target overwritten"))
    with pytest.raises(ValueError, match="settled client target"):
        control.apply_client(paths=harness.paths, system=FakeSystem())
    with pytest.raises(ValueError, match="not installed"):
        control.stop_client(paths=harness.paths, system=FakeSystem())


def test_client_missing_target_receipt_is_distinct_and_reconciles_without_rewrite(harness, monkeypatch):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    receipt = harness.paths.operation_root / "stage/operation/apply-config.json"
    receipt.unlink()
    assert control.reconcile(paths=harness.paths, system=FakeSystem())["targets"]["config"] \
        == "COMMITTED_RECEIPT_MISSING"
    monkeypatch.setattr(control, "_install", lambda *a, **kw: pytest.fail("committed target rewritten"))
    control.apply_client(paths=harness.paths, system=FakeSystem())
    assert control.reconcile(paths=harness.paths, system=FakeSystem())["targets"]["config"] == "APPLIED"


def test_same_bytes_preimage_with_changed_inode_is_conflict(harness):
    target = harness.paths.config
    target.write_bytes(b"original")
    _own(target, 0o444)
    harness.stage()
    other = target.with_name("other.json")
    other.write_bytes(b"original")
    _own(other, 0o444)
    other.replace(target)
    assert control.reconcile(paths=harness.paths, system=FakeSystem())["targets"]["config"] == "CONFLICT"


def test_isolated_control_script_has_a_real_cli_without_config_reads():
    result = subprocess.run([sys.executable, "-I", "-B", str(REPO / "ops/executive_os/application_tunnel_control.py"),
                             "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "reconcile-server" in result.stdout
