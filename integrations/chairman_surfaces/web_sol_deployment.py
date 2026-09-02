"""Pure deterministic deployment artifacts for one exact Web-Sol profile.

This module renders and verifies bytes only. It performs no filesystem write,
process launch, browser operation, credential access, network call, install,
rollback, or lifecycle mutation. A later privileged installer may consume a
reviewed bundle and must independently enforce ownership and effect safety.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from . import web_sol_instance as wsi
from . import web_sol_native_host as native
from . import web_sol_protocol as wsp

PUBLIC_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_public_receipt.v1"
ROLLBACK_MANIFEST_SCHEMA = "mastermind.web_sol_deployment_rollback_manifest.v1"
READBACK_RECEIPT_SCHEMA = "mastermind.web_sol_deployment_readback_receipt.v1"

_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MODULE = "integrations.chairman_surfaces.web_sol_native_host"


class WebSolDeploymentError(ValueError):
    """A pure Web-Sol deployment description or readback is invalid."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _absolute_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, Path):
        value = Path(value) if isinstance(value, str) else None
    if (
        value is None
        or not value.is_absolute()
        or ".." in value.parts
        or not str(value)
        or any(marker in str(value) for marker in ("\x00", "\n", "\r"))
    ):
        raise WebSolDeploymentError(f"{field}_invalid")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _shell_literal(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


@dataclasses.dataclass(frozen=True)
class WebSolRelease:
    package_version: str
    source_commit: str
    repository_root: Path
    python_executable: Path
    install_root: Path

    def __post_init__(self) -> None:
        package = str(self.package_version or "").strip()
        source = str(self.source_commit or "").strip().lower()
        if _SEMVER_RE.fullmatch(package) is None:
            raise WebSolDeploymentError("package_version_invalid")
        if package != wsp.WEB_SOL_PACKAGE_VERSION:
            raise WebSolDeploymentError("package_version_mismatch")
        if _COMMIT_RE.fullmatch(source) is None:
            raise WebSolDeploymentError("source_commit_invalid")
        object.__setattr__(self, "package_version", package)
        object.__setattr__(self, "source_commit", source)
        object.__setattr__(
            self,
            "repository_root",
            _absolute_path(self.repository_root, field="repository_root"),
        )
        object.__setattr__(
            self,
            "python_executable",
            _absolute_path(self.python_executable, field="python_executable"),
        )
        object.__setattr__(
            self,
            "install_root",
            _absolute_path(self.install_root, field="install_root"),
        )


@dataclasses.dataclass(frozen=True)
class DeploymentArtifact:
    kind: str
    destination: Path
    content: bytes
    mode: int

    def __post_init__(self) -> None:
        kind = str(self.kind or "").strip()
        if not kind or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind) is None:
            raise WebSolDeploymentError("artifact_kind_invalid")
        destination = _absolute_path(
            self.destination,
            field="artifact_destination",
        )
        if not isinstance(self.content, bytes) or not self.content:
            raise WebSolDeploymentError("artifact_content_invalid")
        if type(self.mode) is not int or self.mode not in {0o600, 0o700}:
            raise WebSolDeploymentError("artifact_mode_invalid")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "destination", destination)

    @property
    def sha256(self) -> str:
        return _sha256(self.content)


@dataclasses.dataclass(frozen=True)
class DeploymentBundle:
    instance_id: str
    native_host_name: str
    source_commit: str
    wrapper_argv: tuple[str, ...]
    artifacts: tuple[DeploymentArtifact, ...]
    bundle_digest: str

    def as_files(self) -> dict[str, bytes]:
        return {str(item.destination): item.content for item in self.artifacts}

    @property
    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": PUBLIC_RECEIPT_SCHEMA,
            "source_commit": self.source_commit,
            "instance_id": self.instance_id,
            "native_host_name": self.native_host_name,
            "package_version": wsp.WEB_SOL_PACKAGE_VERSION,
            "protocol_major": wsp.TRANSPORT_PROTOCOL_MAJOR,
            "capability_digest": wsp.transport_capability_digest(),
            "bundle_digest": self.bundle_digest,
            "artifact_digests": {
                item.kind: item.sha256 for item in self.artifacts
            },
        }


@dataclasses.dataclass(frozen=True)
class DeploymentChange:
    path: Path
    action: str
    prior_sha256: str | None
    next_sha256: str
    mode: int


@dataclasses.dataclass(frozen=True)
class DeploymentPlan:
    bundle_digest: str
    changes: tuple[DeploymentChange, ...]
    _rollback_entries: tuple[tuple[str, str, str | None], ...]

    @property
    def rollback_manifest(self) -> dict[str, object]:
        return {
            "schema": ROLLBACK_MANIFEST_SCHEMA,
            "bundle_digest": self.bundle_digest,
            "entries": [
                {
                    "path": path,
                    "prior_state": state,
                    "prior_sha256": digest,
                }
                for path, state, digest in self._rollback_entries
            ],
        }


def _instance_config(
    *,
    instance_id: str,
    native_host_name: str,
    package_version: str,
) -> bytes:
    document = {
        "schema": wsp.INSTANCE_CONFIG_SCHEMA,
        "instanceId": instance_id,
        "nativeHost": native_host_name,
        "protocolMajor": wsp.TRANSPORT_PROTOCOL_MAJOR,
        "clientPackageVersion": package_version,
        "nativePackageVersion": package_version,
        "extensionPackageVersion": package_version,
        "capabilityDigest": wsp.transport_capability_digest(),
    }
    return (
        "globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze("
        + json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + ");\n"
    ).encode("utf-8")


def _wrapper(
    *,
    release: WebSolRelease,
    instance_id: str,
) -> tuple[tuple[str, ...], bytes]:
    argv = (
        str(release.python_executable),
        "-E",
        "-s",
        "-B",
        "-m",
        _MODULE,
        "--instance-id",
        instance_id,
    )
    rendered = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"cd {_shell_literal(str(release.repository_root))}\n"
        f"exec {_shell_literal(str(release.python_executable))} "
        f"-E -s -B -m {_MODULE} --instance-id {instance_id} \"$@\"\n"
    ).encode("utf-8")
    return argv, rendered


def _bundle_digest(
    *,
    release: WebSolRelease,
    instance_id: str,
    artifacts: tuple[DeploymentArtifact, ...],
) -> str:
    document = {
        "schema": "mastermind.web_sol_deployment_bundle.v1",
        "source_commit": release.source_commit,
        "package_version": release.package_version,
        "instance_id": instance_id,
        "artifacts": [
            {
                "kind": item.kind,
                "destination": str(item.destination),
                "mode": item.mode,
                "sha256": item.sha256,
            }
            for item in artifacts
        ],
    }
    return _sha256(_canonical_bytes(document))


def render_bundle(
    binding: dict[str, Any],
    release: WebSolRelease,
) -> DeploymentBundle:
    """Render one immutable exact-profile artifact bundle without applying it."""

    if not isinstance(release, WebSolRelease):
        raise WebSolDeploymentError("release_invalid")
    try:
        instance_id = wsi.adapter_instance_id(binding)
        host_name = wsi.native_host_name(instance_id)
    except wsi.WebSolInstanceError as exc:
        raise WebSolDeploymentError(exc.code) from exc

    extension_root = release.install_root / "extensions" / instance_id[:24]
    wrapper_destination = release.install_root / "bin" / host_name
    manifest_destination = (
        release.install_root / "native-hosts" / f"{host_name}.json"
    )
    config_destination = extension_root / "instance_config.js"

    wrapper_argv, wrapper_content = _wrapper(
        release=release,
        instance_id=instance_id,
    )
    manifest_content = (
        json.dumps(
            {
                "name": host_name,
                "description": "Mastermind Web Sol exact-profile native bridge",
                "path": str(wrapper_destination),
                "type": "stdio",
                "allowed_origins": [native.ALLOWED_EXTENSION_ORIGIN],
            },
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

    artifacts = tuple(
        sorted(
            (
                DeploymentArtifact(
                    "instance_config",
                    config_destination,
                    _instance_config(
                        instance_id=instance_id,
                        native_host_name=host_name,
                        package_version=release.package_version,
                    ),
                    0o600,
                ),
                DeploymentArtifact(
                    "native_host_manifest",
                    manifest_destination,
                    manifest_content,
                    0o600,
                ),
                DeploymentArtifact(
                    "native_host_wrapper",
                    wrapper_destination,
                    wrapper_content,
                    0o700,
                ),
            ),
            key=lambda item: (str(item.destination), item.kind),
        )
    )
    digest = _bundle_digest(
        release=release,
        instance_id=instance_id,
        artifacts=artifacts,
    )
    return DeploymentBundle(
        instance_id=instance_id,
        native_host_name=host_name,
        source_commit=release.source_commit,
        wrapper_argv=wrapper_argv,
        artifacts=artifacts,
        bundle_digest=digest,
    )


def _coerce_current_files(value: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(value, Mapping):
        raise WebSolDeploymentError("current_files_invalid")
    result: dict[str, bytes] = {}
    for raw_path, payload in value.items():
        if (
            not isinstance(raw_path, str)
            or not Path(raw_path).is_absolute()
            or ".." in Path(raw_path).parts
        ):
            raise WebSolDeploymentError("current_file_path_invalid")
        if not isinstance(payload, bytes):
            raise WebSolDeploymentError("current_file_content_invalid")
        result[raw_path] = payload
    return result


def plan_deployment(
    bundle: DeploymentBundle,
    current_files: Mapping[str, bytes],
) -> DeploymentPlan:
    """Produce a dry-run change and rollback-digest plan; never mutate files."""

    if not isinstance(bundle, DeploymentBundle):
        raise WebSolDeploymentError("bundle_invalid")
    current = _coerce_current_files(current_files)
    changes: list[DeploymentChange] = []
    rollback: list[tuple[str, str, str | None]] = []
    for item in bundle.artifacts:
        path = str(item.destination)
        before = current.get(path)
        if before is None:
            action = "CREATE"
            prior_digest = None
            prior_state = "ABSENT"
        else:
            prior_digest = _sha256(before)
            prior_state = "PRESENT"
            action = "UNCHANGED" if before == item.content else "UPDATE"
        changes.append(
            DeploymentChange(
                path=item.destination,
                action=action,
                prior_sha256=prior_digest,
                next_sha256=item.sha256,
                mode=item.mode,
            )
        )
        rollback.append((path, prior_state, prior_digest))
    return DeploymentPlan(
        bundle_digest=bundle.bundle_digest,
        changes=tuple(changes),
        _rollback_entries=tuple(rollback),
    )


def verify_deployment_readback(
    bundle: DeploymentBundle,
    current_files: Mapping[str, bytes],
) -> dict[str, object]:
    """Verify exact targeted artifact bytes and return a public receipt."""

    if not isinstance(bundle, DeploymentBundle):
        raise WebSolDeploymentError("bundle_invalid")
    current = _coerce_current_files(current_files)
    expected = bundle.as_files()
    if any(current.get(path) != payload for path, payload in expected.items()):
        raise WebSolDeploymentError("readback_mismatch")
    return {
        "schema": READBACK_RECEIPT_SCHEMA,
        "ok": True,
        "instance_id": bundle.instance_id,
        "bundle_digest": bundle.bundle_digest,
        "artifact_digests": {
            item.kind: item.sha256 for item in bundle.artifacts
        },
    }


__all__ = [
    "DeploymentArtifact",
    "DeploymentBundle",
    "DeploymentChange",
    "DeploymentPlan",
    "PUBLIC_RECEIPT_SCHEMA",
    "READBACK_RECEIPT_SCHEMA",
    "ROLLBACK_MANIFEST_SCHEMA",
    "WebSolDeploymentError",
    "WebSolRelease",
    "plan_deployment",
    "render_bundle",
    "verify_deployment_readback",
]
