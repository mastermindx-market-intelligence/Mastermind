"""Closed additive Browser Link native installation through the Web Sol transaction.

Rendering is pure. The release owner qualifies the interpreter, immutable source
release and browser registration root before the existing applier writes files.
Enrollment carries no lease, process, action, or browser-consent authority.
"""
from __future__ import annotations

import base64
import dataclasses
import re
from pathlib import Path

from integrations.mastermind_browser_link.native_channel import LinkEnrollment, native_host_name
from . import web_sol_deployment as d

NATIVE_BUNDLE_SCHEMA = "mastermind.browser_link.native_host_deployment.v1"
_HEX40 = re.compile(r"[0-9a-f]{40}")


def _path(value, field):
    path = d._absolute_path(value, field=field)
    if not isinstance(value, Path) or str(path) != str(value):
        raise d.WebSolDeploymentError("native_path_invalid")
    return path


def _components(*, native_hosts_root, release_root, python_executable, enrollment):
    root = _path(native_hosts_root, "native_hosts_root")
    release = _path(release_root, "release_root")
    python = _path(python_executable, "python_executable")
    if type(enrollment) is not LinkEnrollment:
        raise d.WebSolDeploymentError("native_enrollment_invalid")
    enrollment.__post_init__()
    _path(enrollment.socket_path, "socket_path")
    host_name = native_host_name(enrollment.instance_id)
    payload_root = root / "mastermind-browser-link" / enrollment.instance_id
    config_path = payload_root / "enrollment.json"
    launcher_path = payload_root / "host"
    argv = (str(python), "-I", "-S", "-B",
            str(release / "scripts/mastermind_browser_link_native_host.py"),
            "--config", str(config_path))
    launcher = ("#!/bin/sh\nexec " + " ".join(d._shell_literal(item) for item in argv)
                + ' "$@"\n').encode("utf-8")
    manifest = {"name": host_name, "description": "Mastermind Browser Link",
                "path": str(launcher_path), "type": "stdio",
                "allowed_origins": [f"chrome-extension://{enrollment.extension_id}/"]}
    # Publication order is part of the closed contract. Rollback reverses it.
    artifacts = (
        d.DeploymentArtifact("browser_link_native_enrollment", config_path,
                             d._canonical_bytes(enrollment.document()) + b"\n", 0o600),
        d.DeploymentArtifact("browser_link_native_launcher", launcher_path, launcher, 0o700),
        d.DeploymentArtifact("browser_link_native_manifest", root / (host_name + ".json"),
                             d._canonical_bytes(manifest) + b"\n", 0o600),
    )
    return argv, artifacts


def _native_digest(fields):
    return d._sha256(d._canonical_bytes({
        "schema": NATIVE_BUNDLE_SCHEMA,
        **{name: fields[name] for name in ("instance_id", "native_host_name", "source_commit", "wrapper_argv")},
        **{name: str(fields[name]) for name in ("native_hosts_root", "release_root", "python_executable")},
        "enrollment": fields["enrollment"].document(),
        "artifacts": [{"kind": row.kind, "destination": str(row.destination),
                       "mode": row.mode, "sha256": row.sha256} for row in fields["artifacts"]],
    }))


@dataclasses.dataclass(frozen=True)
class BrowserLinkNativeBundle(d.DeploymentBundle):
    native_hosts_root: Path
    release_root: Path
    python_executable: Path
    enrollment: LinkEnrollment

    def __post_init__(self):
        validate_native_bundle(self)

    @property
    def public_receipt(self):
        return {"schema": "mastermind.browser_link.native_host_public_receipt.v1",
                "scope": "native_host_installation", "source_commit": self.source_commit,
                "native_protocol_version": 2, "bundle_digest": self.bundle_digest,
                "artifact_digests": {row.kind: row.sha256 for row in self.artifacts}}

    def private_document(self):
        return {
            "schema": NATIVE_BUNDLE_SCHEMA,
            **{name: getattr(self, name) for name in
               ("instance_id", "native_host_name", "source_commit", "bundle_digest")},
            **{name: str(getattr(self, name)) for name in
               ("native_hosts_root", "release_root", "python_executable")},
            "wrapper_argv": list(self.wrapper_argv),
            "enrollment": self.enrollment.document(),
            "artifacts": [{"kind": row.kind, "destination": str(row.destination), "mode": row.mode,
                           "sha256": row.sha256, "content_base64": base64.b64encode(row.content).decode("ascii")}
                          for row in self.artifacts],
        }


def validate_native_bundle(bundle):
    if type(bundle) is not BrowserLinkNativeBundle:
        raise d.WebSolDeploymentError("native_bundle_invalid")
    if (type(bundle.source_commit) is not str or not _HEX40.fullmatch(bundle.source_commit)
            or type(bundle.enrollment) is not LinkEnrollment
            or bundle.instance_id != bundle.enrollment.instance_id
            or bundle.native_host_name != native_host_name(bundle.enrollment.instance_id)):
        raise d.WebSolDeploymentError("native_identity_invalid")
    argv, expected = _components(native_hosts_root=bundle.native_hosts_root,
                                 release_root=bundle.release_root,
                                 python_executable=bundle.python_executable,
                                 enrollment=bundle.enrollment)
    if (type(bundle.wrapper_argv) is not tuple or bundle.wrapper_argv != argv
            or type(bundle.artifacts) is not tuple
            or any(type(row) is not d.DeploymentArtifact for row in bundle.artifacts)
            or bundle.artifacts != expected):
        raise d.WebSolDeploymentError("native_artifacts_invalid")
    if type(bundle.bundle_digest) is not str or bundle.bundle_digest != _native_digest(vars(bundle)):
        raise d.WebSolDeploymentError("native_digest_mismatch")


def validate_native_plan(bundle, plan):
    validate_native_bundle(bundle)
    if (type(plan) is not d.DeploymentPlan or plan.bundle_digest != bundle.bundle_digest
            or type(plan.changes) is not tuple or any(type(row) is not d.DeploymentChange for row in plan.changes)):
        raise d.WebSolDeploymentError("native_plan_invalid")
    if (tuple(row.path for row in plan.changes) != tuple(row.destination for row in bundle.artifacts)
            or {row.action for row in plan.changes} not in ({"CREATE"}, {"UNCHANGED"})):
        # A partially installed bundle must use its original transaction's
        # recovery, never a new mixed CREATE/UNCHANGED or UPDATE transaction.
        raise d.WebSolDeploymentError("native_preimages_invalid")
    rollback = []
    for change, artifact in zip(plan.changes, bundle.artifacts):
        prior = None if change.action == "CREATE" else artifact.sha256
        if (type(change) is not d.DeploymentChange or change.prior_sha256 != prior
                or change.next_sha256 != artifact.sha256 or change.mode != artifact.mode):
            raise d.WebSolDeploymentError("native_plan_invalid")
        rollback.append((str(artifact.destination), "ABSENT" if prior is None else "PRESENT", prior))
    if plan._rollback_entries != tuple(rollback):
        raise d.WebSolDeploymentError("native_rollback_invalid")


def render_browser_link_native_bundle(*, source_commit, native_hosts_root, release_root,
                                      python_executable, enrollment):
    """Render only the three fixed artifacts; do not inspect or mutate a profile."""
    if type(enrollment) is not LinkEnrollment:
        raise d.WebSolDeploymentError("native_enrollment_invalid")
    fields = {"instance_id": enrollment.instance_id, "native_host_name": native_host_name(enrollment.instance_id),
              "source_commit": source_commit, "native_hosts_root": Path(native_hosts_root),
              "release_root": Path(release_root), "python_executable": Path(python_executable),
              "enrollment": enrollment}
    fields["wrapper_argv"], fields["artifacts"] = _components(
        native_hosts_root=fields["native_hosts_root"], release_root=fields["release_root"],
        python_executable=fields["python_executable"], enrollment=enrollment)
    return BrowserLinkNativeBundle(**fields, bundle_digest=_native_digest(fields))
