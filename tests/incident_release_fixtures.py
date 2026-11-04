"""Complete inert content records for connected incident protocol tests.

The observer's own tests use the lower-level World fixtures. These records
replace the native observation leaf for tests of its consuming protocol.
"""
from dataclasses import asdict

from control_plane import executive_incident_release_observation as i
from control_plane import executive_release_observation as r
from control_plane.executive_recovery_observation_normalization import Instance


def make_observation(*, source, boot, states=None, broker=Instance(20, 220, 2)):
    states = states or {}
    rows = []
    for index, spec in enumerate(r._SPECS):
        frozen = spec.role == "relay"
        content = r._InstalledContent(
            "mastermind.executive_release_service_content/v1", spec.role,
            spec.label, spec.uid, spec.plist, spec.config,
            r.peer._NETWORK_RUNTIME_LAUNCHER if spec.role == "gateway" else r.peer._PYTHON_LAUNCHER,
            spec.wrapper, i._FROZEN_RELAY_RELEASE if frozen else source["release_sha"],
            "d" * 40 if frozen else "c" * 40,
            "c" * 64 if frozen else source["manifest_sha256"],
            "d" * 64, "e" * 64, str(index + 1) * 64, "f" * 64)
        state = states.get(spec.role, "UNLOADED" if index < 3 else "RUNNING")
        process = broker if spec.role == "broker" else Instance(100 + index, 500 + index, 20 + index)
        rows.append(r._RoleObservation(spec.role, state, r._digest(r._CONTENT_DOMAIN, asdict(content)),
            content, "launchctl-exact-not-found-113" if state == "UNLOADED" else "launchctl-qualified-loaded-job",
            process.pid if state == "RUNNING" else None,
            process.unique_id if state == "RUNNING" else None,
            process.pidversion if state == "RUNNING" else None))
    rows = tuple(rows)
    return i._IncidentReleaseObservation(i._PURPOSE, boot, rows, i._cohort_digest(rows), r._Freshness(1, 2, 3))
