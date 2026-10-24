"""Pure Browser Link overlays for the two qualified installed Web Sol releases.

An overlay preserves the installed transport/configuration and uses the existing
deployment transaction. It is not a full Web Sol installer or native-host release.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import re
from collections.abc import Mapping
from pathlib import Path

from . import web_sol_deployment as d
from . import web_sol_instance as instance

OVERLAY_SCHEMA = "mastermind.web_sol_browser_link_overlay.v1"
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CONFIG_PREFIX = b"globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze("
_CONFIG_SUFFIX = b");\n"

_COMMON = (
    ("census.html", "f7f3627d79379c81550b299c67f2309312a6f59587d9145ddbc4d4b4e3d0c404"),
    ("census.css", "35e89371a3b772c7136e93324a01a11c1173da06d46e7edd301e85f3fe239745"),
    ("census_core.js", "a4300ffc24e40c6c9f735a7ed556bd76c9adeca570ae83209349da1e1a999a84"),
    ("census.js", "b43e735ef13366cf8dad5ad86a252f456c14705a98e7974a7b25bc1cbbf97b43"),
)
_UPDATED_CENSUS = "77b1e36f888e1aa54521e638e6e90bf08a9bc0406b0207a16323c2ea45220a5c"


@dataclasses.dataclass(frozen=True)
class _BaseRelease:
    version: str
    source_commit: str
    capability_digest: str
    digests: tuple[tuple[str, str], ...]
    updated_manifest_digest: str


_BASE_RELEASES = (
    _BaseRelease(
        "0.2.0", "320f586126b7c82c843ef17612f12d40d20a42e0",
        "89a0dcb05a6c1c31000f841671e6cbf6c29a69dd73ed9726c8b5b99535485e50",
        _COMMON + (
            ("manifest.json", "043e8365f62e36dc278abb24a43b27ce7e67c99ed0540308387a3fd51804def0"),
            ("background.js", "6543ecb24229fd4f0d807247fd6ca9ffe7a91fa66382dbede4b3c311907b78bf"),
            ("content.js", "8e993887920bcba4ac7e26f11558fe89eed756a46362de0c2e51a5ab65d5b7d3"),
        ),
        "c70227683ad0d060759be88f5b45b09cd925ea74ac32b11a594411ad14c42545",
    ),
    _BaseRelease(
        "0.4.0", "e6140689976a95e029d499633a3054418d99bd76",
        "d9fba04ca5045c3f5261c50ebd2a2d1fc60204e2d8662a9aa31e08a7bd79e6e0",
        _COMMON + (
            ("manifest.json", "c2d45de42fc9500e25891e2a91bb4c18560b76021b1583254509622b4a0484eb"),
            ("background.js", "ee275dc19a3fc0fc4829ae78894a81350b3016fa3ce911675b84de0c4d75fd94"),
            ("content.js", "5bc8d4b9fa11535c37516ece2fb4029bbe2c13743e9bd1408f95e0075f14feef"),
            ("continuation_core.js", "6a545054a95332afb8cd273deb046cad4dba42097d47f10830a167b4a226d7a4"),
        ),
        "4d983daa5d9c34ab7992f38cbecdd25a21602291a3244acc321666e67a9ca982",
    ),
)


def _refuse(code: str):
    raise d.WebSolDeploymentError(code)


def _base_release(version: str) -> _BaseRelease:
    for release in _BASE_RELEASES:
        if type(version) is str and release.version == version:
            return release
    _refuse("overlay_base_release_invalid")


def _base_kinds(release: _BaseRelease) -> dict[str, str]:
    result = dict(d._CENSUS_SOURCE_KINDS)
    if release.version == "0.4.0":
        result["continuation_core.js"] = "extension_continuation_core"
    result["instance_config.js"] = "instance_config"
    return result


def _validate_config(payload: bytes, instance_id: str, host_name: str, release: _BaseRelease):
    if (type(payload) is not bytes or not 0 < len(payload) <= 16384
            or not payload.startswith(_CONFIG_PREFIX) or not payload.endswith(_CONFIG_SUFFIX)):
        _refuse("overlay_instance_config_invalid")
    try:
        body = json.loads(
            payload[len(_CONFIG_PREFIX):-len(_CONFIG_SUFFIX)].decode("utf-8"),
            object_pairs_hook=d._manifest_members,
            parse_constant=lambda _value: _refuse("overlay_instance_config_invalid"),
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise d.WebSolDeploymentError("overlay_instance_config_invalid") from error
    expected = {
        "schema": "mastermind.web_sol_instance_config.v1",
        "instanceId": instance_id, "nativeHost": host_name, "protocolMajor": 1,
        "clientPackageVersion": release.version,
        "nativePackageVersion": release.version,
        "extensionPackageVersion": release.version,
        "capabilityDigest": release.capability_digest,
    }
    if type(body) is not dict or body != expected or type(body.get("protocolMajor")) is not int:
        _refuse("overlay_instance_config_mismatch")


def _overlay_digest(fields: Mapping[str, object]) -> str:
    document = {
        "schema": OVERLAY_SCHEMA,
        **{name: fields[name] for name in (
            "instance_id", "native_host_name", "source_commit", "wrapper_argv",
            "base_package_version", "base_source_commit", "base_capability_digest",
        )},
        "extension_root": str(fields["extension_root"]),
        "required_preimage_digests": fields["required_preimage_digests"],
        "artifacts": [
            {"kind": row.kind, "destination": str(row.destination),
             "mode": row.mode, "sha256": row.sha256}
            for row in fields["artifacts"]
        ],
    }
    return d._sha256(d._canonical_bytes(document))


@dataclasses.dataclass(frozen=True)
class BrowserLinkOverlayBundle(d.DeploymentBundle):
    base_package_version: str
    base_source_commit: str
    base_capability_digest: str
    extension_root: Path
    required_preimage_digests: tuple[tuple[str, str | None], ...]

    def __post_init__(self):
        validate_overlay_bundle(self)

    @property
    def public_receipt(self) -> dict[str, object]:
        return {
            "schema": "mastermind.web_sol_browser_link_overlay_public_receipt.v1",
            "scope": "extension_overlay",
            "source_commit": self.source_commit,
            "base_source_commit": self.base_source_commit,
            "package_version": self.base_package_version,
            "protocol_major": 1,
            "capability_digest": self.base_capability_digest,
            "bundle_digest": self.bundle_digest,
            "artifact_digests": {row.kind: row.sha256 for row in self.artifacts},
        }

    def private_document(self) -> dict[str, object]:
        """Existing private CLI carrier; contains exact paths and file bytes."""
        return {
            "schema": OVERLAY_SCHEMA,
            **{name: getattr(self, name) for name in (
                "instance_id", "native_host_name", "source_commit", "bundle_digest",
                "base_package_version", "base_source_commit", "base_capability_digest",
            )},
            "wrapper_argv": [],
            "extension_root": str(self.extension_root),
            "required_preimage_digests": [
                {"name": name, "sha256": digest}
                for name, digest in self.required_preimage_digests
            ],
            "artifacts": [
                {"kind": row.kind, "destination": str(row.destination), "mode": row.mode,
                 "sha256": row.sha256,
                 "content_base64": base64.b64encode(row.content).decode("ascii")}
                for row in self.artifacts
            ],
        }


def validate_overlay_bundle(bundle: BrowserLinkOverlayBundle) -> None:
    if type(bundle) is not BrowserLinkOverlayBundle:
        _refuse("overlay_bundle_invalid")
    release = _base_release(bundle.base_package_version)
    if (type(bundle.instance_id) is not str or not _HEX64.fullmatch(bundle.instance_id)
            or type(bundle.source_commit) is not str or not _HEX40.fullmatch(bundle.source_commit)
            or bundle.native_host_name != instance.native_host_name(bundle.instance_id)
            or type(bundle.wrapper_argv) is not tuple or bundle.wrapper_argv
            or bundle.base_source_commit != release.source_commit
            or bundle.base_capability_digest != release.capability_digest):
        _refuse("overlay_identity_invalid")
    root = d._absolute_path(bundle.extension_root, field="extension_root")
    if not isinstance(bundle.extension_root, Path) or root != bundle.extension_root:
        _refuse("overlay_root_invalid")
    base_kinds = _base_kinds(release)
    kinds = {**base_kinds, **dict(d._BROWSER_LINK_SOURCE_KINDS)}
    if type(bundle.artifacts) is not tuple or len(bundle.artifacts) != len(kinds):
        _refuse("overlay_artifacts_invalid")
    if any(type(row) is not d.DeploymentArtifact for row in bundle.artifacts):
        _refuse("overlay_artifacts_invalid")
    by_path = {row.destination: row for row in bundle.artifacts}
    if (set(by_path) != {root / name for name in kinds}
            or tuple(sorted(bundle.artifacts, key=lambda row: (str(row.destination), row.kind))) != bundle.artifacts
            or any(row.kind != kinds[str(row.destination.relative_to(root))]
                   or row.mode != 0o600 or type(row.content) is not bytes
                   or not 0 < len(row.content) <= d._CENSUS_MAX_FILE_BYTES
                   for row in bundle.artifacts)
            or sum(len(row.content) for row in bundle.artifacts) > d._CENSUS_MAX_TOTAL_BYTES):
        _refuse("overlay_artifacts_invalid")
    postimages = dict(release.digests)
    postimages["manifest.json"] = release.updated_manifest_digest
    postimages["census.html"] = _UPDATED_CENSUS
    if any(by_path[root / name].sha256 != digest for name, digest in postimages.items()):
        _refuse("overlay_base_postimage_mismatch")
    config = by_path[root / "instance_config.js"]
    _validate_config(config.content, bundle.instance_id, bundle.native_host_name, release)
    required = tuple(sorted((
        *release.digests,
        ("instance_config.js", config.sha256),
        *((name, None) for name in d._BROWSER_LINK_SOURCE_NAMES),
    )))
    if (type(bundle.required_preimage_digests) is not tuple
            or any(type(row) is not tuple for row in bundle.required_preimage_digests)
            or bundle.required_preimage_digests != required):
        _refuse("overlay_preimages_invalid")
    if (type(bundle.bundle_digest) is not str or not _HEX64.fullmatch(bundle.bundle_digest)
            or bundle.bundle_digest != _overlay_digest(vars(bundle))):
        _refuse("overlay_digest_mismatch")


def validate_overlay_plan(bundle: BrowserLinkOverlayBundle, plan: d.DeploymentPlan) -> None:
    validate_overlay_bundle(bundle)
    if type(plan) is not d.DeploymentPlan or plan.bundle_digest != bundle.bundle_digest:
        _refuse("overlay_plan_invalid")
    by_path = {row.path: row for row in plan.changes}
    if len(by_path) != len(plan.changes) or set(by_path) != {row.destination for row in bundle.artifacts}:
        _refuse("overlay_plan_invalid")
    originals = dict(bundle.required_preimage_digests)
    expected_rollback = []
    for artifact in bundle.artifacts:
        name = str(artifact.destination.relative_to(bundle.extension_root))
        prior = originals[name]
        action = "CREATE" if prior is None else "UPDATE" if name in {"manifest.json", "census.html"} else "UNCHANGED"
        change = by_path[artifact.destination]
        if (change.action != action or change.prior_sha256 != prior
                or change.next_sha256 != artifact.sha256 or change.mode != artifact.mode):
            _refuse("overlay_plan_preimage_mismatch")
        expected_rollback.append((str(artifact.destination), "ABSENT" if prior is None else "PRESENT", prior))
    if tuple(sorted(plan._rollback_entries)) != tuple(sorted(expected_rollback)):
        _refuse("overlay_rollback_mismatch")


def render_browser_link_overlay(
    binding: dict, *, source_commit: str, extension_root: Path,
    installed_files: Mapping[str, bytes], browser_link_files: Mapping[str, bytes],
    expected_browser_link_digests: Mapping[str, str],
) -> BrowserLinkOverlayBundle:
    """Render an exact installed-profile upgrade, never a fresh installation.

    Frozen base hashes qualify compatibility. The caller still authenticates the
    new source/build receipt and supplies an admitted exact profile target.
    """
    root = d._absolute_path(extension_root, field="extension_root")
    if not isinstance(installed_files, Mapping):
        _refuse("overlay_sources_invalid")
    snapshot = dict(installed_files)
    if any(type(value) is not bytes or not 0 < len(value) <= d._CENSUS_MAX_FILE_BYTES
           for value in snapshot.values()) or sum(map(len, snapshot.values())) > d._CENSUS_MAX_TOTAL_BYTES:
        _refuse("overlay_sources_invalid")
    manifest = snapshot.get("manifest.json", b"")
    release = next((row for row in _BASE_RELEASES
                    if dict(row.digests)["manifest.json"] == d._sha256(manifest)), None)
    if release is None or set(snapshot) != set(_base_kinds(release)):
        _refuse("overlay_base_release_invalid")
    if any(d._sha256(snapshot[name]) != digest for name, digest in release.digests):
        _refuse("overlay_base_digest_mismatch")
    try:
        instance_id = instance.adapter_instance_id(binding)
        host_name = instance.native_host_name(instance_id)
    except instance.WebSolInstanceError as error:
        raise d.WebSolDeploymentError(error.code) from error
    _validate_config(snapshot["instance_config.js"], instance_id, host_name, release)
    added = d._validated_browser_link_sources(browser_link_files, expected_browser_link_digests)
    manifest_bytes, census_bytes = d._browser_link_base_changes(manifest, snapshot["census.html"])
    updated = {**snapshot, "manifest.json": manifest_bytes, "census.html": census_bytes, **added}
    kinds = {**_base_kinds(release), **dict(d._BROWSER_LINK_SOURCE_KINDS)}
    artifacts = tuple(sorted(
        (d.DeploymentArtifact(kinds[name], root / name, content, 0o600)
         for name, content in updated.items()),
        key=lambda row: (str(row.destination), row.kind),
    ))
    fields = dict(
        instance_id=instance_id, native_host_name=host_name, source_commit=source_commit,
        wrapper_argv=(), artifacts=artifacts,
        base_package_version=release.version, base_source_commit=release.source_commit,
        base_capability_digest=release.capability_digest, extension_root=root,
        required_preimage_digests=tuple(sorted(
            [(name, d._sha256(content)) for name, content in snapshot.items()]
            + [(name, None) for name in added]
        )),
    )
    return BrowserLinkOverlayBundle(**fields, bundle_digest=_overlay_digest(fields))
