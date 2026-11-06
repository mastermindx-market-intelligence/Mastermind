"""Parent integration checks: real capture and manifest joins over inert OS facts.

No native host, service, credential, provider, or installed release is accessed.
The existing trusted-filesystem leaves are represented by two independent byte
inventories. The production manifest verifier and its recheck both run unchanged.
"""
from dataclasses import replace
import hashlib
import json
import plistlib
import stat
from types import SimpleNamespace as S

import pytest

from control_plane import executive_incident_release_observation as incident
from control_plane import executive_release_observation as generic
from tests.test_executive_release_observation import World


class IncidentWorld(World):
    def __init__(self, monkeypatch):
        verify = generic.peer._verify_release
        recheck = generic.peer._recheck_release
        super().__init__(monkeypatch)
        self.entry = incident._observe_incident_release
        self.states.update(control="UNLOADED", worker="UNLOADED", relay="UNLOADED")
        self.old = incident._FROZEN_RELAY_RELEASE
        self.old_tree = "6" * 40
        self.verified, self.rechecked = [], []
        self.payloads, self.manifests, self.info = {}, {}, {}
        self.source_reads = 0
        self.denied_path = None
        for n, (commit, tree) in enumerate(((self.release, self.tree), (self.old, self.old_tree))):
            root = generic._RELEASES + commit
            files = {spec.wrapper: (commit + ":" + spec.role).encode() for spec in generic._SPECS}
            files["other-source.txt"] = ("full closure " + commit).encode()
            self.payloads[commit] = files
            entries = [dict(path=path, type="file", mode=0o444, uid=0, gid=0,
                            size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                       for path, raw in sorted(files.items())]
            manifest = root + "/.executive-release-manifest.json"
            self.manifests[commit] = manifest
            self.artifacts[manifest] = json.dumps(dict(schema_version=generic.peer._RELEASE_MANIFEST_SCHEMA,
                commit_sha=commit, tree_sha=tree, entries=entries)).encode()
            self.identities[manifest] = (1, 9000 + n, 10)
            self.info[root] = self.stat(4000 + n, stat.S_IFDIR | 0o555, 0)
            self.info[manifest] = self.stat(5000 + n, stat.S_IFREG | 0o444, len(self.artifacts[manifest]))
            for j, (path, raw) in enumerate(sorted(files.items())):
                self.info[root + "/" + path] = self.stat(6000 + 100 * n + j, stat.S_IFREG | 0o444, len(raw))
        spec = generic._SPECS[2]
        self.artifacts[spec.plist] = self.artifacts[spec.plist].replace(self.release.encode(), self.old.encode())
        self.argvs["relay"] = tuple(plistlib.loads(self.artifacts[spec.plist])["ProgramArguments"])
        self.artifacts[spec.config] = json.dumps(dict(schema=generic._RELAY_CONFIG_SCHEMA, relay_version=self.old)).encode()
        gateway = generic._SPECS[3]
        config = json.loads(self.artifacts[gateway.config])
        config["executive_mcp_profile"] = "web_ceo_v3"
        self.artifacts[gateway.config] = json.dumps(config).encode()
        self.source = dict(release_sha=self.release,
            manifest_sha256=hashlib.sha256(self.artifacts[self.manifests[self.release]]).hexdigest())
        monkeypatch.setattr(incident, "_loaded_source", self.loaded_source)
        monkeypatch.setattr(generic, "_artifact", self.checked_artifact)
        monkeypatch.setattr(generic.peer, "_observe_ancestors", lambda path, budget: ((1, 2, 3),))
        monkeypatch.setattr(generic.peer, "_open_trusted", lambda path, **kw: (10, self.info[path], ()))
        monkeypatch.setattr(generic.peer, "_close", lambda fd: None)
        monkeypatch.setattr(generic.peer, "_read_trusted_bytes", self.read_bytes)
        monkeypatch.setattr(generic.peer, "_walk_release", self.walk)
        def verified(topology, commit, budget):
            self.verified.append(commit)
            return verify(topology, commit, budget)
        def rechecked(before, budget):
            self.rechecked.append(before.release)
            return recheck(before, budget)
        monkeypatch.setattr(generic.peer, "_verify_release", verified)
        monkeypatch.setattr(generic.peer, "_recheck_release", rechecked)
        original = incident._recheck_content
        def recheck_content(snapshot, budget):
            self.rechecking = True
            self.hit("final_content")
            return original(snapshot, budget)
        monkeypatch.setattr(incident, "_recheck_content", recheck_content)

    @staticmethod
    def stat(inode, mode, size):
        return S(st_dev=1, st_ino=inode, st_mode=mode, st_uid=0, st_gid=0,
                 st_nlink=1, st_size=size, st_mtime_ns=10, st_ctime_ns=10)

    def loaded_source(self):
        self.source_reads += 1
        if self.source_reads > 1:
            self.hit("final_source")
        if self.drift == "source" and self.source_reads > 1:
            return dict(self.source, release_sha="c" * 40)
        return dict(self.source)

    def checked_artifact(self, path, mode, gid, budget):
        if path == self.denied_path:
            raise PermissionError("inert denied artifact")
        return self.artifact(path, mode, gid, budget)

    def read_bytes(self, path, **kwargs):
        kwargs["budget"].check()
        if path == self.denied_path:
            raise PermissionError("inert denied release bytes")
        commit, relative = path.removeprefix(generic._RELEASES).split("/", 1)
        raw = self.artifacts[path] if relative == ".executive-release-manifest.json" else self.payloads[commit][relative]
        return raw, self.info[path]

    def walk(self, root, budget, *, hash_files=True):
        budget.check()
        commit = root.removeprefix(generic._RELEASES)
        return [(path, "file", 0o444, 0, 0, len(raw), hashlib.sha256(raw).hexdigest() if hash_files else "",
                 generic.peer._object_identity(self.info[root + "/" + path]))
                for path, raw in sorted(self.payloads[commit].items())]

    def command(self, argv, budget):
        rc, out, err = super().command(argv, budget)
        if argv == ("/bin/launchctl", "print", generic._SPECS[2].service):
            out = out.replace(("working directory = " + generic._RELEASES + self.release).encode(),
                              ("working directory = " + generic._RELEASES + self.old).encode())
        return rc, out, err


@pytest.fixture
def world(monkeypatch):
    return IncidentWorld(monkeypatch)


def test_full_capture_verifies_and_rechecks_both_distinct_manifest_closures(world):
    value = world.capture()
    assert type(value) is incident._IncidentReleaseObservation
    assert value.purpose == incident._PURPOSE
    assert world.verified == world.rechecked == [world.release, world.old]
    assert world.commands == dict.fromkeys(generic._ROLES, 2)
    assert world.source_reads == 2 and world.boot_reads == 2
    assert world.write_calls == []
    assert value.freshness.deadline_monotonic_ns == world.deadline
    relay = value.roles[2]
    assert relay.state == "UNLOADED" and (relay.pid, relay.unique_id, relay.pidversion) == (None, None, None)
    assert relay.content.release_commit == world.old and relay.content.release_tree == world.old_tree
    for role in value.roles:
        commit = world.old if role.role == "relay" else world.release
        assert role.content.installed_manifest_digest == hashlib.sha256(world.artifacts[world.manifests[commit]]).hexdigest()
        assert role.content.wrapper_digest == hashlib.sha256(world.payloads[commit][role.content.wrapper_relative]).hexdigest()
    assert relay.content.wrapper_digest != hashlib.sha256(world.payloads[world.release][relay.content.wrapper_relative]).hexdigest()


@pytest.mark.parametrize("role", generic._ROLES)
def test_arbitrary_role_release_refuses_before_any_closure_is_verified(world, role):
    spec = generic._SPECS[generic._ROLES.index(role)]
    old = world.old if role == "relay" else world.release
    world.artifacts[spec.plist] = world.artifacts[spec.plist].replace(old.encode(), b"d" * 40)
    with pytest.raises(generic.ReleaseObservationError, match="ROLE_SOURCE_REFUSED"):
        world.capture()
    assert world.verified == [] and world.write_calls == []


@pytest.mark.parametrize("state", ["LOADED_IDLE", "RUNNING"])
def test_relay_must_be_exactly_unloaded(world, state):
    world.states["relay"] = state
    with pytest.raises(generic.ReleaseObservationError, match="FROZEN_RELAY_NOT_STOPPED"):
        world.capture()


def test_generic_capture_and_validator_still_refuse_mixed_source(world):
    value = world.capture()
    with pytest.raises(generic.ReleaseObservationError, match="MIXED_CONTENT"):
        generic._validate_roles(value.roles)
    with pytest.raises(generic.ReleaseObservationError, match="MIXED_CONTENT"):
        generic._observe_release(deadline_monotonic_ns=world.deadline)


@pytest.mark.parametrize("substitution", ["generic", "purpose", "digest", "relay_pid"])
def test_closed_type_purpose_content_and_stopped_identity(world, substitution):
    value = world.capture()
    if substitution == "generic":
        bad = generic._ReleaseObservation(value.boot_id, value.roles, "a" * 64, value.freshness)
    elif substitution == "purpose":
        bad = replace(value, purpose="mastermind.due10_frozen_relay_observation/v1")
    elif substitution == "digest":
        bad = replace(value, cohort_content_sha256="a" * 64)
    else:
        roles = list(value.roles)
        roles[2] = replace(roles[2], pid=102)
        bad = replace(value, roles=tuple(roles))
    with pytest.raises(generic.ReleaseObservationError):
        incident._validate_observation(bad)


@pytest.mark.parametrize("which", ["current", "frozen"])
@pytest.mark.parametrize("fault", ["missing_manifest", "wrong_manifest_commit", "wrapper_hash", "unconsumed_hash", "denied_manifest"])
def test_both_complete_closures_are_required(world, which, fault):
    commit = world.release if which == "current" else world.old
    manifest = world.manifests[commit]
    if fault == "missing_manifest":
        del world.artifacts[manifest]
    elif fault == "wrong_manifest_commit":
        doc = json.loads(world.artifacts[manifest])
        doc["commit_sha"] = "d" * 40
        world.artifacts[manifest] = json.dumps(doc).encode()
    elif fault == "denied_manifest":
        world.denied_path = manifest
    else:
        path = generic._SPECS[2].wrapper if fault == "wrapper_hash" else "other-source.txt"
        world.payloads[commit][path] += b"drift"
    with pytest.raises(generic.ReleaseObservationError, match="INCIDENT_OBSERVATION_UNAVAILABLE"):
        world.capture()
    assert world.write_calls == []


@pytest.mark.parametrize("which", ["current", "frozen"])
def test_manifest_readback_cannot_disagree_with_verified_closure(world, monkeypatch, which):
    commit = world.release if which == "current" else world.old
    original = generic._artifact
    def changed(path, mode, gid, budget):
        item = original(path, mode, gid, budget)
        return replace(item, raw=item.raw + b" ") if path == world.manifests[commit] else item
    monkeypatch.setattr(generic, "_artifact", changed)
    with pytest.raises(generic.ReleaseObservationError, match="CONTENT_DRIFT"):
        world.capture()


@pytest.mark.parametrize("which", ["current", "frozen"])
@pytest.mark.parametrize("fault", ["manifest_bytes", "unconsumed_identity"])
def test_final_recheck_covers_both_whole_closures(world, monkeypatch, which, fault):
    commit = world.release if which == "current" else world.old
    original = incident._recheck_content
    def changed(snapshot, budget):
        if fault == "manifest_bytes":
            world.artifacts[world.manifests[commit]] += b" "
        else:
            path = generic._RELEASES + commit + "/other-source.txt"
            world.info[path].st_ino += 1
        return original(snapshot, budget)
    monkeypatch.setattr(incident, "_recheck_content", changed)
    code = "CONTENT_DRIFT" if fault == "manifest_bytes" else "INCIDENT_OBSERVATION_UNAVAILABLE"
    with pytest.raises(generic.ReleaseObservationError, match=code):
        world.capture()


@pytest.mark.parametrize("fault,code", [
    ("manifest", "CONTENT_DRIFT"), ("file_identity", "CONTENT_DRIFT"),
    ("state", "SERVICE_DRIFT"), ("process_instance", "SERVICE_DRIFT"),
    ("boot", "BOOT_DRIFT"), ("source", "SOURCE_DRIFT"),
    ("clock_rollback", "CLOCK"),
])
def test_fresh_capture_refuses_observed_drift(world, fault, code):
    world.drift = fault
    with pytest.raises(generic.ReleaseObservationError, match=code):
        world.capture()


@pytest.mark.parametrize("edge", ["fifth_role", "final_content", "final_boot", "final_process", "final_source"])
def test_original_absolute_deadline_is_not_refreshed(world, edge):
    world.expire_at(edge)
    with pytest.raises(generic.ReleaseObservationError, match="DEADLINE"):
        world.capture()
    assert world.now == world.deadline


def test_declared_current_manifest_must_match_current_verified_bytes(world):
    world.source["manifest_sha256"] = "9" * 64
    with pytest.raises(generic.ReleaseObservationError, match="SOURCE_MISMATCH"):
        world.capture()


def test_public_call_has_no_release_or_exception_selector(world):
    with pytest.raises(TypeError):
        incident._observe_incident_release(deadline_monotonic_ns=world.deadline, release_sha=world.release)

