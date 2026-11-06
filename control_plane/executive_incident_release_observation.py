"""Private incident observation of current authority and an inert frozen Relay.

This is not generic five-role release convergence. The incident owner alone
uses this purpose, with no caller-selected exceptions or release hints. The
old Relay's complete provenance is retained and it must remain UNLOADED.
Observation never activates a policy, rebinds C1, or authorizes a retry.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

from control_plane import executive_release_observation as release

__all__ = ()
_PURPOSE = "mastermind.due10_frozen_relay_observation/v2"
_FROZEN_RELAY_RELEASE = "326c8469a21d7f50fc9ecb1848196bf1c6e66685"
_COHORT_DOMAIN = b"mastermind.due10_frozen_relay_content/v2\x00"


def _refuse(code):
    raise release.ReleaseObservationError(code) from None


def _loaded_source():
    from control_plane import executive_incident_composition as composition

    source = composition._loaded_source()
    if Path(__file__).resolve(strict=True).parents[1] != Path(release._RELEASES + source["release_sha"]):
        _refuse("INCIDENT_OBSERVATION_SOURCE_MISMATCH")
    return source


@dataclass(frozen=True, slots=True)
class _IncidentReleaseObservation:
    purpose: str
    boot_id: str
    roles: tuple
    cohort_content_sha256: str
    freshness: release._Freshness


@dataclass(frozen=True, slots=True)
class _IncidentContentSnapshot:
    contents: tuple
    argvs: tuple
    artifacts: tuple
    releases: tuple
    runtime: object
    network: object


def _cohort_digest(roles):
    # Content only: the broker's expected bootstrap changes state, not bytes.
    return release._digest(_COHORT_DOMAIN, {
        "purpose": _PURPOSE, "roles": [asdict(row.content) for row in roles],
    })


def _validate_observation(value):
    if type(value) is not _IncidentReleaseObservation or value.purpose != _PURPOSE:
        _refuse("INCIDENT_OBSERVATION_PURPOSE_REFUSED")
    release._validate_role_records(value.roles)
    authority = {(
        row.content.release_commit, row.content.release_tree,
        row.content.installed_manifest_digest,
    ) for row in value.roles if row.role != "relay"}
    if len(authority) != 1 or next(iter(authority))[0] == _FROZEN_RELAY_RELEASE:
        _refuse("INCIDENT_OBSERVATION_AUTHORITY_COHORT_REFUSED")
    relay = value.roles[2]
    if relay.content.release_commit != _FROZEN_RELAY_RELEASE:
        _refuse("INCIDENT_OBSERVATION_FROZEN_RELAY_SOURCE_REFUSED")
    if relay.state != "UNLOADED":
        _refuse("INCIDENT_OBSERVATION_FROZEN_RELAY_NOT_STOPPED")
    if value.cohort_content_sha256 != _cohort_digest(value.roles):
        _refuse("INCIDENT_OBSERVATION_CONTENT_DIGEST_REFUSED")
    return value


def _content_snapshot(source, budget):
    peer = release.peer
    artifacts, plists, configs, commits = [], [], [], []
    for spec in release._SPECS:
        plist = budget.call(release._artifact, spec.plist, 0o644, 0, budget)
        document = peer._load_strict_plist(plist.raw, code="SERVICE_PLIST_MALFORMED")
        found = []
        if not peer._profile_matches(release._profile(spec), document, found) or len(found) != 1:
            _refuse("RELEASE_OBSERVATION_PLIST_REFUSED")
        expected = _FROZEN_RELAY_RELEASE if spec.role == "relay" else source["release_sha"]
        if found[0] != expected:
            _refuse("INCIDENT_OBSERVATION_ROLE_SOURCE_REFUSED")
        config = budget.call(release._artifact, spec.config, spec.config_mode, spec.config_gid, budget)
        release._config_join(spec, peer._load_strict_json(config.raw, code="SERVICE_CONFIG_MALFORMED"), expected)
        artifacts.extend((plist, config))
        plists.append((plist, tuple(document["ProgramArguments"])))
        configs.append(config)
        commits.append(expected)
    if source["release_sha"] == _FROZEN_RELAY_RELEASE:
        _refuse("INCIDENT_OBSERVATION_AUTHORITY_COHORT_REFUSED")

    # Verify both entire closures; never borrow a current wrapper for old Relay.
    closures = {}
    for commit in dict.fromkeys(commits):
        verified = budget.call(peer._verify_release, peer._ROLE_TOPOLOGIES["control"], commit, budget)
        manifest = budget.call(release._artifact, release._RELEASES + commit + "/.executive-release-manifest.json", 0o444, 0, budget)
        if manifest.digest != verified.manifest_digest:
            _refuse("RELEASE_OBSERVATION_CONTENT_DRIFT")
        if commit == source["release_sha"] and manifest.digest != source["manifest_sha256"]:
            _refuse("INCIDENT_OBSERVATION_SOURCE_MISMATCH")
        tree = peer._load_strict_json(manifest.raw, code="SERVICE_MANIFEST_MALFORMED")["tree_sha"]
        if type(tree) is not str or release._HEX40.fullmatch(tree) is None or tree == "0" * 40:
            _refuse("RELEASE_OBSERVATION_CONTENT_REFUSED")
        artifacts.append(manifest)
        closures[commit] = (verified, manifest, tree)
    runtime = budget.call(peer._verify_python_runtime, budget)
    network = budget.call(peer._verify_network_closure, budget)
    contents = []
    for spec, (plist, argv), config, commit in zip(release._SPECS, plists, configs, commits, strict=True):
        verified, manifest, tree = closures[commit]
        row = next((row for row in verified.digests if row[0] == spec.wrapper), None)
        if row is None or row[1] != "file" or release._HEX64.fullmatch(str(row[6])) is None:
            _refuse("RELEASE_OBSERVATION_WRAPPER_REFUSED")
        closure = {"python_launcher": runtime.launcher_digest, "python_dylib": runtime.dylib_digest, "python_main": runtime.main_digest}
        if spec.role == "gateway":
            closure["network"] = network.aggregate
        contents.append(release._InstalledContent(
            "mastermind.executive_release_service_content/v1", spec.role, spec.label,
            spec.uid, spec.plist, spec.config, argv[0], spec.wrapper, commit, tree,
            manifest.digest, config.digest, plist.digest, row[6],
            release._digest(release._EXECUTABLE_DOMAIN, closure)))
    return _IncidentContentSnapshot(tuple(contents), tuple(row[1] for row in plists),
        tuple(artifacts), tuple(row[0] for row in closures.values()), runtime, network)


def _recheck_content(snapshot, budget):
    for before in snapshot.artifacts:
        if budget.call(release._artifact, before.path, before.mode, before.gid, budget) != before:
            _refuse("RELEASE_OBSERVATION_CONTENT_DRIFT")
    for before in snapshot.releases:
        budget.call(release.peer._recheck_release, before, budget)
    budget.call(release.peer._recheck_python_runtime, snapshot.runtime, budget)
    budget.call(release.peer._recheck_network_closure, snapshot.network, budget)


def _observe_incident_release(*, deadline_monotonic_ns):
    """Fresh private v2 snapshot; no release, purpose or exception selector."""
    try:
        budget = release._Budget(deadline_monotonic_ns)
        if sys.platform != "darwin":
            _refuse("RELEASE_OBSERVATION_PLATFORM_UNSUPPORTED")
        if release.peer._LAUNCHD_KERNEL_PATTERN.fullmatch(release._line(release.peer._SYSCTL_OSRELEASE_ARGV, budget)) is None:
            _refuse("RELEASE_OBSERVATION_PLATFORM_UNSUPPORTED")
        source = budget.call(_loaded_source)
        boot = budget.call(release._boot, budget)
        snapshot = budget.call(_content_snapshot, source, budget)
        roles = tuple(budget.call(release._service, spec, content, argv, budget)
            for spec, content, argv in zip(release._SPECS, snapshot.contents, snapshot.argvs, strict=True))
        value = _IncidentReleaseObservation(_PURPOSE, boot, roles, _cohort_digest(roles),
            release._Freshness(budget.started, budget.last, budget.endpoint))
        _validate_observation(value)
        budget.call(_recheck_content, snapshot, budget)
        for spec, content, argv, before in zip(release._SPECS, snapshot.contents, snapshot.argvs, roles, strict=True):
            if budget.call(release._service, spec, content, argv, budget) != before:
                _refuse("RELEASE_OBSERVATION_SERVICE_DRIFT")
        for row in roles:
            if row.state == "RUNNING" and budget.call(release._instance, row.pid, budget) != (row.unique_id, row.pidversion):
                _refuse("RELEASE_OBSERVATION_PROCESS_DRIFT")
        if budget.call(release._boot, budget) != boot:
            _refuse("RELEASE_OBSERVATION_BOOT_DRIFT")
        if budget.call(_loaded_source) != source:
            _refuse("INCIDENT_OBSERVATION_SOURCE_DRIFT")
        budget.check(force=True)
        return _IncidentReleaseObservation(_PURPOSE, boot, roles, value.cohort_content_sha256,
            release._Freshness(budget.started, budget.last, budget.endpoint))
    except release.ReleaseObservationError:
        raise
    except Exception:
        _refuse("INCIDENT_OBSERVATION_UNAVAILABLE")
