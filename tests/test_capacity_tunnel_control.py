"""Closed CAPACITY-purpose transport control: identity, ACL, stage, apply, rollback.

The fixtures are real: a clean protected Git checkout, an exact-SHA sealed
release, a real upstream source checkout, real file hashes, real locks, real
atomic writes and strict input parsing. Only the OS service/process
observations and the launchctl commands are substituted.

The capacity transport must not be able to acquire the APPLICATION purpose by
import, so the reuse decision is tested structurally as well as by behaviour.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types

import pytest

from ops.executive_os import application_tunnel_control as application
from ops.executive_os import capacity_tunnel_control as control
from ops.executive_os import os_tunnel_entry
from ops.executive_os import release_manifest

REPO = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "ops/executive_os/capacity_tunnel_entry.py",
    "ops/executive_os/os_tunnel_entry.py",
    "ops/executive_os/capacity_tunnel_control.py",
    "control_plane/fs_security.py",
    "ops/executive_os/com.mastermind.executive.capacity-tunnel.plist.template",
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
CAPACITY_SECRET = b"mastermind-capacity:" + b"q" * 48
INCUMBENT = {
    "mastermind-os:ossecret": [r"^R:127\.0\.0\.1:49160$"],
    "operator:opsecret": [r"^0\.0\.0\.0:3000$"],
}
requires_root = pytest.mark.skipif(
    os.geteuid() != 0, reason="the closed transport mutation path requires root custody")


# ------------------------------------------------------------ closed contract


def test_closed_constants_name_one_fixed_capacity_reverse():
    assert control.PURPOSE == "capacity-transport"
    assert control.LABEL == "com.mastermind.executive.capacity-tunnel"
    assert control.AUDIENCE == "mastermind-capacity"
    assert control.RELAY_PORT == 8313
    assert control.TARGET_PORT == 8313
    assert control.REMOTE_ADDRESS == "R:127.0.0.1:8313"
    assert control.REMOTE_REGEX == r"^R:127\.0\.0\.1:8313$"
    assert control.REVERSE_TARGET == "R:127.0.0.1:8313:127.0.0.1:8313"
    assert control.REMOTE_ADDRESS == os_tunnel_entry.CAPACITY_REVERSE
    assert control.REVERSE_TARGET == os_tunnel_entry.CAPACITY_REVERSE_TARGET
    assert control.TEMPLATE_PATH.endswith("com.mastermind.executive.capacity-tunnel.plist.template")


def test_operation_identity_is_deterministic_and_purpose_scoped():
    identity = control.operation_identity()
    assert identity == control.operation_identity()
    assert identity.startswith("capacity-tunnel-") and len(identity) == len("capacity-tunnel-") + 32
    assert identity != application.operation_identity()


def test_capacity_paths_never_collide_with_the_application_owner():
    capacity, owner = control.Paths(), application.Paths()
    assert capacity.operation_root != owner.operation_root
    assert capacity.config != owner.config
    assert capacity.credential != owner.credential
    assert capacity.plist != owner.plist
    assert capacity.operation_root.name == "capacity-tunnel"
    assert capacity.config.name == "capacity-tunnel.json"
    assert capacity.credential.name == "capacity-tunnel.auth"
    # The incumbent server owner is shared by design; the ACL is what separates us.
    assert capacity.server_authfile == owner.server_authfile


def test_capacity_control_never_names_the_application_binding():
    source = (REPO / "ops/executive_os/capacity_tunnel_control.py").read_text()
    for forbidden in ("mastermind-fabric-app", "application-tunnel.json",
                      "application-tunnel.auth", "fabric-application-tunnel.plist",
                      "50142", "127.0.0.2", "127.0.0.3", ":4142", "8443"):
        assert forbidden not in source


def test_capacity_flows_are_its_own_not_the_application_flows():
    flows = ("Paths", "System", "operation_identity", "stage", "apply_server", "apply_client",
             "reconcile", "start_client", "stop_client", "rollback_server", "rollback_client",
             "_merge_authfile", "_authorizes_capacity_listener", "_server_transaction",
             "_server_bundle", "_server_observation", "_load_stage", "_render_plist",
             "_redact", "_normalise_credential", "_qualification")
    for name in flows:
        assert getattr(control, name) is not getattr(application, name, None), name


def _code_text(code):
    """Every name and string constant a code object references, nested included."""
    text = set(code.co_names) | {code.co_name}
    text |= {value for value in code.co_consts if isinstance(value, str)}
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            text |= _code_text(value)
    return text


def _referenced_text(callable_object):
    if isinstance(callable_object, type):
        parts = []
        for attribute in vars(callable_object).values():
            if isinstance(attribute, (staticmethod, classmethod)):
                attribute = attribute.__func__
            if callable(getattr(attribute, "__code__", None)):
                parts.append(_referenced_text(attribute))
        return set().union(*parts) if parts else set()
    return _code_text(callable_object.__code__)


def test_structural_probe_descends_into_nested_functions():
    # _sealed_path is referenced only from _install's nested check_parent; a
    # top-level-only probe would miss coupling hidden one level down.
    text = _referenced_text(control._install)
    assert "_sealed_path" in text and "check_parent" in text


def test_reused_primitives_carry_no_application_purpose_constant():
    for name in control.REUSED_PRIMITIVES:
        reused = getattr(control, name)
        text = _referenced_text(reused)
        for token in control._APPLICATION_TOKENS:
            assert not any(token in item for item in text), (name, token)


def test_parser_offers_no_purpose_host_port_or_target_selector():
    options = set()

    def walk(parser):
        for action in parser._actions:
            options.update(action.option_strings)
            if hasattr(action, "choices") and isinstance(getattr(action, "choices", None), dict):
                for child in action.choices.values():
                    walk(child)

    walk(control.build_parser())
    for forbidden in ("--purpose", "--host", "--port", "--target", "--remote", "--server",
                      "--label", "--audience", "--schema", "--executable", "--command",
                      "--proxy", "--socks", "--paths"):
        assert forbidden not in options


# --------------------------------------------------------------------- ACL


def test_the_capacity_acl_is_anchored_exact_and_re2_safe():
    assert control._go_regex_safe(control.REMOTE_REGEX)
    assert re.fullmatch(control.REMOTE_REGEX, "R:127.0.0.1:8313")
    for foreign in ("R:127.0.0.1:83130", "R:127.0.0.1:831", "R:127.0.0.10:8313",
                    "R:127.0.0.2:8313", "R:0.0.0.0:8313", "R:127.0.0.1:8313:127.0.0.1:8313",
                    "R:127.0.0.1:8314", " R:127.0.0.1:8313", "R:127.0.0.1:8313 "):
        assert re.fullmatch(control.REMOTE_REGEX, foreign) is None, foreign


def test_go_unsafe_incumbent_rules_are_refused_before_any_merge():
    for pattern in ("(?=x)", "(?<!y)", "\\1", "(?P<n>x)", "(?>x)", "a*+", "a++",
                    "a?+", "a{2,3}+"):
        raw = json.dumps({"operator:opsecret": [pattern]}).encode()
        with pytest.raises(ValueError):
            control._merge_authfile(raw, "mastermind-capacity:" + "q" * 48)


def test_possessive_quantifiers_are_refused_but_literal_pluses_are_not():
    for pattern in ("a*+", "a++", "a?+", "a{2,3}+", "(?:a)++"):
        assert control._go_regex_safe(pattern) is False, pattern
    for pattern in (control.REMOTE_REGEX, r"a\+b", r"[\++]x", r"^0\.0\.0\.0:3000$",
                    r"a{b}c"):
        assert control._go_regex_safe(pattern) is True, pattern


def test_authfile_wildcards_are_refused():
    for pattern in ("", "*", ".*"):
        raw = json.dumps({"operator:opsecret": [pattern]}).encode()
        with pytest.raises(ValueError):
            control._merge_authfile(raw, "mastermind-capacity:" + "q" * 48)


def test_merge_preserves_every_incumbent_user_and_acl_value():
    raw = json.dumps(INCUMBENT).encode()
    entries, merged, changed = control._merge_authfile(raw, "mastermind-capacity:" + "q" * 48)
    assert changed is True
    assert entries == INCUMBENT
    assert merged["mastermind-os:ossecret"] == INCUMBENT["mastermind-os:ossecret"]
    assert merged["operator:opsecret"] == INCUMBENT["operator:opsecret"]
    assert merged["mastermind-capacity:" + "q" * 48] == [control.REMOTE_REGEX]
    assert len(merged) == len(INCUMBENT) + 1
    assert json.loads(raw) == INCUMBENT


def test_merge_is_idempotent_only_for_the_exact_original_grant():
    auth = "mastermind-capacity:" + "q" * 48
    raw = json.dumps({**INCUMBENT, auth: [control.REMOTE_REGEX]}).encode()
    _, merged, changed = control._merge_authfile(raw, auth)
    assert changed is False
    assert merged == {**INCUMBENT, auth: [control.REMOTE_REGEX]}


def test_merge_refuses_a_second_grant_of_the_capacity_listener():
    raw = json.dumps({**INCUMBENT, "operator:other": [r"^R:127\.0\.0\.1:8313$"]}).encode()
    with pytest.raises(ValueError, match="already authorizes"):
        control._merge_authfile(raw, "mastermind-capacity:" + "q" * 48)


def test_merge_refuses_a_conflicting_capacity_identity():
    raw = json.dumps({**INCUMBENT, "mastermind-capacity:other": [r"^R:127\.0\.0\.1:9000$"]}).encode()
    with pytest.raises(ValueError, match="conflicting existing capacity identity"):
        control._merge_authfile(raw, "mastermind-capacity:" + "q" * 48)


def test_merge_refuses_a_differing_existing_grant_for_our_own_identity():
    auth = "mastermind-capacity:" + "q" * 48
    raw = json.dumps({**INCUMBENT, auth: [r"^R:127\.0\.0\.1:9000$"]}).encode()
    with pytest.raises(ValueError, match="refusing to rewrite"):
        control._merge_authfile(raw, auth)


def test_capacity_listener_authorization_is_checked_against_the_closed_remote():
    assert control._authorizes_capacity_listener([control.REMOTE_REGEX])
    assert control._authorizes_capacity_listener([r"R:127\.0\.0\.1:8313"])
    assert not control._authorizes_capacity_listener([r"^R:127\.0\.0\.1:50142$"])


# ------------------------------------------------------------------- plist


def test_the_capacity_plist_compiles_the_fixed_root_transport_and_no_secret():
    template = (REPO / control.TEMPLATE_PATH).read_bytes()
    plist = control._render_plist(template, python="/usr/bin/python3", release_root="/release")
    arguments = control._plist_arguments(plist)
    assert arguments == ["/usr/bin/python3", "-I", "-B",
                         "/release/ops/executive_os/capacity_tunnel_entry.py"]
    text = plist.decode()
    assert "<key>KeepAlive</key>\n  <true/>" in text
    assert "<key>Umask</key>\n  <integer>63</integer>" in text
    assert "<string>root</string>" in text and "<string>wheel</string>" in text
    assert control.LABEL in text
    assert control.AUDIENCE not in text and "AUTH" not in text
    assert CAPACITY_SECRET.decode() not in text
    assert "__" not in text


def test_the_capacity_plist_xml_escapes_every_substituted_value():
    template = (REPO / control.TEMPLATE_PATH).read_bytes()
    release_root = "/release/rock&roll<1>"
    plist = control._render_plist(template, python="/usr/bin/python3",
                                  release_root=release_root)
    assert b"rock&amp;roll&lt;1&gt;" in plist
    arguments = control._plist_arguments(plist)
    assert arguments == ["/usr/bin/python3", "-I", "-B",
                         release_root + "/ops/executive_os/capacity_tunnel_entry.py"]


def test_the_capacity_plist_refuses_an_unresolved_placeholder():
    template = (REPO / control.TEMPLATE_PATH).read_bytes().replace(b"__LABEL__", b"__SOMETHING__")
    with pytest.raises(ValueError, match="unresolved plist placeholder"):
        control._render_plist(template, python="/usr/bin/python3", release_root="/release")


def test_the_capacity_plist_refuses_credential_material():
    template = (REPO / control.TEMPLATE_PATH).read_bytes().replace(
        b"<key>Label</key>", b"<key>AUTH</key>")
    with pytest.raises(ValueError, match="must not carry credential material"):
        control._render_plist(template, python="/usr/bin/python3", release_root="/release")


def test_plist_arguments_refuse_a_foreign_label():
    template = (REPO / control.TEMPLATE_PATH).read_bytes()
    plist = control._render_plist(template, python="/usr/bin/python3", release_root="/r")
    foreign = plist.replace(control.LABEL.encode(), b"com.mastermind.executive.something-else")
    with pytest.raises(ValueError, match="plist label refused"):
        control._plist_arguments(foreign)


# -------------------------------------------------------------- credential


def test_normalise_credential_accepts_one_newline_and_the_exact_identity():
    assert control._normalise_credential(CAPACITY_SECRET) == CAPACITY_SECRET
    assert control._normalise_credential(CAPACITY_SECRET + b"\n") == CAPACITY_SECRET


@pytest.mark.parametrize("raw", [
    b"", b"mastermind-fabric-app:" + b"q" * 48, b"mastermind-os:" + b"q" * 48,
    b"mastermind-capacity:short", CAPACITY_SECRET + b"\nextra", CAPACITY_SECRET + b"\x00",
    CAPACITY_SECRET + b" ", b"\xff\xfe",
])
def test_normalise_credential_refuses_any_foreign_or_malformed_secret(raw):
    with pytest.raises(ValueError):
        control._normalise_credential(raw)


def test_redact_removes_the_capacity_secret_from_observed_output():
    message = "failed with mastermind-capacity:" + "q" * 48 + " and more"
    redacted = control._redact(message)
    assert "q" * 48 not in redacted
    assert "mastermind-capacity:<redacted>" in redacted
    assert control._redact(None) == ""


def test_redact_does_not_mangle_a_short_non_secret_prefix():
    assert control._redact("mastermind-capacity:short") == "mastermind-capacity:short"


# ------------------------------------------------------------------ harness


def _git(repo, *args):
    completed = subprocess.run(["/usr/bin/git", "-C", str(repo), *args],
                               capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def _own(path, mode):
    os.chmod(path, mode)
    os.chown(path, 0, 0)


def _commit_repository(root, files, name):
    repo = root
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", name)
    _git(repo, "config", "commit.gpgsign", "false")
    for relative, payload in files.items():
        target = repo / relative
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
    return _commit_repository(root, files, "Capacity Tunnel Fixture")


def _upstream_repository(root):
    files = {name: ("// upstream fixture evidence for %s\n" % name).encode()
             for name in EVIDENCE_PATHS}
    repo, commit, tree = _commit_repository(root, files, "Capacity Upstream Fixture")
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
                 client_version="1.12.0", server_version="1.12.0", unit=None,
                 listeners=(), processes=(), launchd=None, bootstrap_returncode=0,
                 bootout_returncode=0, label=control.LABEL, autoload=True, pid=5150):
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

    def bundle(self):
        stage = self.paths.operation_root / "stage"
        with control.publication.private(stage) as area:
            raw = area.read("server-bundle.json")
        return raw, control.digest(raw)

    def credential(self):
        stage = self.paths.operation_root / "stage"
        with control.publication.private(stage) as area:
            return control._normalise_credential(area.read("credential.auth"))

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


@pytest.fixture(scope="session")
def sealed_root():
    """A root-owned, non-world-writable base for the sealed temp fixtures."""
    if os.geteuid() != 0:
        pytest.skip("requires the isolated root-owned transport fixture")
    base = Path(os.environ.get("MM_CAPACITY_TRANSPORT_TEST_ROOT", str(Path.home())))
    control.assets._sealed_path(base, directory=True)
    with tempfile.TemporaryDirectory(prefix="mmx-capacity-tunnel-", dir=base) as directory:
        root = Path(directory)
        _own(root, 0o755)
        yield root


@pytest.fixture
def harness(sealed_root):
    root = Path(tempfile.mkdtemp(prefix="case-", dir=str(sealed_root)))
    try:
        yield Harness(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------- root-gated lifecycle


@requires_root
def test_stage_records_the_capacity_identity_and_a_closed_server_bundle(harness):
    result = harness.stage()
    assert result["state"] == "STAGED" and result["staged"] is True
    assert result["installed"] is False and result["tunnel_proven"] is False
    raw, expected = harness.bundle()
    assert control.digest(raw) == expected
    bundle = control.decode(raw)
    assert bundle["purpose"] == "capacity-transport"
    assert bundle["audience"] == "mastermind-capacity"
    assert bundle["remotes"] == [control.REMOTE_REGEX]
    assert bundle["auth"].startswith("mastermind-capacity:")
    assert bundle["source"] == {"sha": harness.commit, "tree": harness.tree}


@requires_root
def test_stage_refuses_a_credential_rotation_on_the_original_operation(harness):
    harness.stage()
    rotation = harness.root / "rotation.auth"
    rotation.write_bytes(b"mastermind-capacity:" + b"r" * 48 + b"\n")
    _own(rotation, 0o600)
    with pytest.raises(ValueError, match="credential rotation refused"):
        harness.stage(credential_path=rotation)
    assert harness.credential() != b"mastermind-capacity:" + b"r" * 48


@requires_root
def test_apply_server_adds_one_capacity_acl_and_preserves_the_incumbent(harness):
    harness.stage()
    request = harness.server_receipt()
    receipt = control.decode(Path(request).read_bytes())
    assert receipt["state"] == "GRANT_FILE_APPLIED"
    assert receipt["grant_file_applied"] is True
    assert receipt["server_reload_proven"] is False and receipt["tunnel_proven"] is False
    assert receipt["gateway_proven"] is False
    authfile = json.loads(harness.paths.server_authfile.read_bytes())
    credential = harness.credential().decode()
    assert authfile[credential] == [control.REMOTE_REGEX]
    assert {key: value for key, value in authfile.items() if key != credential} == INCUMBENT
    assert receipt["identity_sha256"] == control.digest(credential.encode())


@requires_root
def test_apply_server_is_serialized_on_the_incumbent_application_server_lock(harness):
    harness.write_authfile()
    harness.stage()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    shared = application.Paths.fixture(harness.root / "host")
    with application._PurposeLock(shared, create=True, server=True):
        with pytest.raises(ValueError, match="purpose custody is busy"):
            control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                                 paths=harness.paths, system=system)
    assert json.loads(harness.paths.server_authfile.read_bytes()) == INCUMBENT
    control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                         paths=harness.paths, system=system)
    credential = harness.credential().decode()
    assert json.loads(harness.paths.server_authfile.read_bytes())[credential] == [
        control.REMOTE_REGEX]


@requires_root
def test_apply_client_installs_only_capacity_targets_and_lifecycle_is_proven(harness):
    harness.stage()
    request = harness.server_receipt()
    result = control.apply_client(server_receipt=request, paths=harness.paths, system=FakeSystem())
    assert result["state"] == "CLIENT_FILES_APPLIED"
    assert result["targets"] == {"config": "APPLIED", "credential": "APPLIED", "plist": "APPLIED"}
    assert oct(harness.paths.config.lstat().st_mode & 0o777) == "0o444"
    assert oct(harness.paths.credential.lstat().st_mode & 0o777) == "0o400"
    assert oct(harness.paths.plist.lstat().st_mode & 0o777) == "0o444"
    assert harness.paths.credential.read_bytes() == harness.credential()
    system = FakeSystem()
    started = control.start_client(server_receipt=request, paths=harness.paths, system=system)
    assert started["state"] == "STARTED" and started["commands"] == 1
    assert started["gateway_proven"] is False and started["tunnel_proven"] is False
    state = control.reconcile(paths=harness.paths, system=system)
    assert state["targets"] == {"config": "APPLIED", "credential": "APPLIED", "plist": "APPLIED"}
    assert state["service_state"] == "STARTED"
    stopped = control.stop_client(paths=harness.paths, system=system)
    assert stopped["state"] == "STOPPED" and stopped["commands"] == 1
    assert system.calls == [("bootstrap", str(harness.paths.plist)),
                            ("bootout", control.LABEL)]


@requires_root
def test_start_client_refuses_without_a_proven_server_grant(harness):
    harness.stage()
    control.apply_client(paths=harness.paths, system=FakeSystem())
    with pytest.raises(ValueError, match="server grant is not applied"):
        control.start_client(server_receipt=None, paths=harness.paths, system=FakeSystem())


@requires_root
def test_apply_client_refuses_a_target_that_changed_after_the_stage(harness):
    harness.stage()
    harness.paths.credential.write_bytes(b"foreign bytes")
    _own(harness.paths.credential, 0o400)
    with pytest.raises(ValueError, match="refusing observed drift"):
        control.apply_client(paths=harness.paths, system=FakeSystem())


@requires_root
def test_rollback_restores_the_incumbent_authfile_and_removes_only_capacity_files(harness):
    harness.stage()
    request = harness.server_receipt()
    control.apply_client(server_receipt=request, paths=harness.paths, system=FakeSystem())
    _, expected = harness.bundle()

    client = control.rollback_client(paths=harness.paths, system=FakeSystem())
    assert client["state"] == "CLIENT_FILES_ROLLED_BACK"
    assert set(client["removed"]) == {"config", "credential", "plist"}
    for path in (harness.paths.config, harness.paths.credential, harness.paths.plist):
        assert not os.path.lexists(path)
    assert os.path.lexists(harness.paths.server_authfile)

    server = control.rollback_server(bundle_path=harness.root / "bundle.json",
                                     expected_digest=expected, paths=harness.paths,
                                     system=FakeSystem())
    assert server["state"] == "GRANT_FILE_ROLLED_BACK"
    assert json.loads(harness.paths.server_authfile.read_bytes()) == INCUMBENT
    again = control.rollback_server(bundle_path=harness.root / "bundle.json",
                                    expected_digest=expected, paths=harness.paths,
                                    system=FakeSystem())
    assert again["state"] == "ALREADY_ROLLED_BACK"


APPLICATION_AUTH = "mastermind-fabric-app:appsecret"
APPLICATION_ACL = [r"^R:127\.0\.0\.1:50142$"]


@requires_root
def test_rollback_never_touches_an_application_owned_authfile_entry(harness):
    incumbent = {**INCUMBENT, APPLICATION_AUTH: APPLICATION_ACL}
    harness.write_authfile(incumbent)
    harness.stage()
    raw, expected = harness.bundle()
    bundle_path = harness.root / "bundle.json"
    bundle_path.write_bytes(raw)
    _own(bundle_path, 0o600)
    system = FakeSystem(unit={"active": True, "main_pid": 4242,
                              "argv": control._server_expected_argv(harness.paths)})
    control.apply_server(bundle_path=bundle_path, expected_digest=expected,
                         paths=harness.paths, system=system)
    applied = json.loads(harness.paths.server_authfile.read_bytes())
    assert APPLICATION_AUTH in applied
    control.rollback_server(bundle_path=bundle_path, expected_digest=expected,
                            paths=harness.paths, system=FakeSystem())
    assert json.loads(harness.paths.server_authfile.read_bytes()) == incumbent


@requires_root
def test_rollback_preserves_an_application_grant_added_after_the_capacity_apply(harness):
    harness.stage()
    harness.server_receipt()
    _, expected = harness.bundle()
    # The APPLICATION owner installs its own grant only after the capacity
    # grant settled; the surgical rollback must preserve it.
    applied = json.loads(harness.paths.server_authfile.read_bytes())
    applied[APPLICATION_AUTH] = APPLICATION_ACL
    harness.write_authfile(applied)
    result = control.rollback_server(bundle_path=harness.root / "bundle.json",
                                     expected_digest=expected, paths=harness.paths,
                                     system=FakeSystem())
    assert result["state"] == "GRANT_FILE_ROLLED_BACK"
    assert result["preserved_entries"] == len(INCUMBENT) + 1
    assert json.loads(harness.paths.server_authfile.read_bytes()) == {
        **INCUMBENT, APPLICATION_AUTH: APPLICATION_ACL}


@requires_root
def test_rollback_refuses_when_the_capacity_entry_itself_drifted(harness):
    harness.stage()
    harness.server_receipt()
    _, expected = harness.bundle()
    credential = harness.credential().decode()
    drifted = json.loads(harness.paths.server_authfile.read_bytes())
    drifted[credential] = [r"^R:127\.0\.0\.1:9000$"]
    harness.write_authfile(drifted)
    with pytest.raises(ValueError, match="capacity grant itself drifted"):
        control.rollback_server(bundle_path=harness.root / "bundle.json",
                                expected_digest=expected, paths=harness.paths,
                                system=FakeSystem())
    assert json.loads(harness.paths.server_authfile.read_bytes()) == drifted
