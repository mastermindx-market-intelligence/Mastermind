"""Exact installed-profile overlays through the existing deployment transaction."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from control_plane import surface_bindings
from integrations.chairman_surfaces import web_sol_browser_link_overlay as overlay
from integrations.chairman_surfaces import web_sol_deployment as deployment
from integrations.chairman_surfaces import web_sol_deployment_apply as applier
from integrations.chairman_surfaces import web_sol_instance as instance
from scripts import web_sol_deployment_apply as cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/web_sol_overlay"
LINK = ROOT / "integrations/mastermind_browser_link/extension"


def _binding():
    return surface_bindings.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM", role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={"env_manager": "multilogin",
                 "folder_id": "11111111-1111-4111-8111-111111111111",
                 "profile_id": "22222222-2222-4222-8222-222222222222",
                 "url": "https://chatgpt.com/c/fictional-overlay-fixture"},
        observed_at="2026-08-30T10:00:00Z", seat_ref="chatgpt1",
        binding_id="33333333-3333-4333-8333-333333333333",
    )


def _config(binding, version):
    identity = instance.adapter_instance_id(binding)
    return {
        "schema": "mastermind.web_sol_instance_config.v1",
        "instanceId": identity, "nativeHost": instance.native_host_name(identity),
        "protocolMajor": 1, "clientPackageVersion": version,
        "nativePackageVersion": version, "extensionPackageVersion": version,
        "capabilityDigest": overlay._base_release(version).capability_digest,
    }


def _config_bytes(config):
    return b"globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze(" + json.dumps(
        config, sort_keys=True, separators=(",", ":")
    ).encode() + b");\n"


def _inputs(tmp_path, version):
    root = tmp_path / "exact-installed-profile"
    root.mkdir(mode=0o700)
    binding = _binding()
    sources = {path.name: path.read_bytes() for path in (FIXTURES / version).iterdir()}
    sources["instance_config.js"] = _config_bytes(_config(binding, version))
    assets = {
        "browser-link-bootstrap.js": (LINK / "websol-bootstrap.js").read_bytes(),
        "browser-link/worker.bundle.js": b'(() => { "use strict"; })();\n',
        **{f"browser-link/{name}": (LINK / name).read_bytes()
           for name in ("popup.html", "popup.css", "popup.mjs")},
    }
    for name, content in sources.items():
        (root / name).write_bytes(content)
        (root / name).chmod(0o600)
    return root, binding, sources, assets


def _render(root, binding, sources, assets):
    return overlay.render_browser_link_overlay(
        binding, source_commit="b" * 40, extension_root=root,
        installed_files=sources, browser_link_files=assets,
        expected_browser_link_digests={
            name: hashlib.sha256(content).hexdigest() for name, content in assets.items()
        },
    )


def _prepare(bundle, root, sources):
    current = {str(root / name): content for name, content in sources.items()}
    return applier.prepare_deployment(
        bundle, deployment.plan_deployment(bundle, current),
        install_root=root, expected_uid=root.stat().st_uid,
        expected_gid=root.stat().st_gid, operation_key="browser-overlay-fixture",
    )


def _request(bundle, prepared):
    plan = prepared.plan
    return {
        "schema": cli.REQUEST_SCHEMA,
        "operation_key": prepared.operation_key, "install_root": str(prepared.install_root),
        "expected_uid": prepared.expected_uid, "expected_gid": prepared.expected_gid,
        "bundle": bundle.private_document(),
        "plan": {
            "bundle_digest": plan.bundle_digest,
            "changes": [
                {**dataclasses.asdict(change), "path": str(change.path)}
                for change in plan.changes
            ],
            "rollback_entries": plan.rollback_manifest["entries"],
        },
    }


@pytest.mark.parametrize("version,unchanged", [("0.2.0", 6), ("0.4.0", 7)])
def test_exact_overlay_apply_private_recovery_and_rollback(tmp_path, version, unchanged):
    root, binding, sources, assets = _inputs(tmp_path, version)
    bundle = _render(root, binding, sources, assets)
    assert bundle.wrapper_argv == ()
    assert bundle.public_receipt["package_version"] == version
    assert bundle.public_receipt["capability_digest"] == _config(binding, version)["capabilityDigest"]
    assert all(row.destination.is_relative_to(root) for row in bundle.artifacts)
    assert cli._decode_bundle(bundle.private_document()) == bundle
    prepared = _prepare(bundle, root, sources)
    assert prepared.public_receipt["update_count"] == 2
    assert prepared.public_receipt["create_count"] == 5
    assert sum(row.action == "UNCHANGED" for row in prepared.plan.changes) == unchanged
    request = _request(bundle, prepared)
    state = cli._private_state_document(
        request_document=request, prepared=prepared, phase="PREPARED"
    )
    phase, _request_copy, recovered, _applied, _digest = cli._decode_private_state(state)
    assert phase == "PREPARED"
    assert type(recovered.bundle) is overlay.BrowserLinkOverlayBundle
    applied = applier.apply_deployment(recovered)
    assert applier.verify_applied_deployment(applied)["target_count"] == len(bundle.artifacts)
    for name, content in sources.items():
        if name not in {"manifest.json", "census.html"}:
            assert (root / name).read_bytes() == content
        assert (root / name).stat().st_mode & 0o777 == 0o600
    after = cli._private_state_document(
        request_document=request, prepared=recovered, phase="APPLIED", applied=applied
    )
    phase, _, recovered_again, applied_again, _ = cli._decode_private_state(after)
    assert phase == "APPLIED"
    assert recovered_again.bundle == bundle
    applier.rollback_deployment(applied_again)
    assert all((root / name).read_bytes() == content for name, content in sources.items())
    assert all(not (root / name).exists() for name in assets)


@pytest.mark.parametrize("version", ["0.2.0", "0.4.0"])
@pytest.mark.parametrize("defect", [
    "instanceId", "nativeHost", "protocolMajor", "clientPackageVersion",
    "nativePackageVersion", "extensionPackageVersion", "capabilityDigest",
    "extra_field", "executable_suffix", "duplicate_field",
])
def test_overlay_refuses_unqualified_instance_configuration(tmp_path, version, defect):
    root, binding, sources, assets = _inputs(tmp_path, version)
    config = _config(binding, version)
    if defect == "protocolMajor":
        config[defect] = True
    elif defect == "extra_field":
        config["extra"] = "unexpected"
    elif defect not in {"executable_suffix", "duplicate_field"}:
        config[defect] = "wrong"
    content = _config_bytes(config)
    if defect == "executable_suffix":
        content += b"globalThis.unreviewed = true;\n"
    elif defect == "duplicate_field":
        content = content.replace(b'{"capabilityDigest":', b'{"protocolMajor":1,"capabilityDigest":', 1)
    sources["instance_config.js"] = content
    with pytest.raises(deployment.WebSolDeploymentError):
        _render(root, binding, sources, assets)


@pytest.mark.parametrize("defect", ["changed_asset", "unknown_version", "missing_continuation", "extra_asset"])
def test_overlay_requires_the_exact_frozen_base(tmp_path, defect):
    root, binding, sources, assets = _inputs(tmp_path, "0.4.0")
    if defect == "changed_asset":
        sources["background.js"] += b"\n"
    elif defect == "unknown_version":
        sources["manifest.json"] = sources["manifest.json"].replace(b"0.4.0", b"0.5.0")
    elif defect == "missing_continuation":
        del sources["continuation_core.js"]
    else:
        sources["arbitrary.js"] = b"unexpected"
    with pytest.raises(deployment.WebSolDeploymentError):
        _render(root, binding, sources, assets)


@pytest.mark.parametrize("defect", ["fresh_install", "changed_preimage", "existing_link"])
def test_applier_refuses_replacement_plan_outside_qualified_overlay(tmp_path, defect):
    root, binding, sources, assets = _inputs(tmp_path, "0.4.0")
    bundle = _render(root, binding, sources, assets)
    if defect == "fresh_install":
        current = {}
    else:
        current = dict(sources)
        if defect == "changed_preimage":
            current["background.js"] += b"changed"
        else:
            current["browser-link/popup.css"] = assets["browser-link/popup.css"]
    with pytest.raises(applier.WebSolDeploymentApplyError, match="OVERLAY_PLAN_INVALID"):
        _prepare(bundle, root, current)
    assert (root / "manifest.json").read_bytes() == sources["manifest.json"]


@pytest.mark.parametrize("name", ["background.js", "instance_config.js", "continuation_core.js"])
def test_unchanged_file_drift_after_prepare_prevents_any_overlay_write(tmp_path, name):
    root, binding, sources, assets = _inputs(tmp_path, "0.4.0")
    bundle = _render(root, binding, sources, assets)
    prepared = _prepare(bundle, root, sources)
    (root / name).write_bytes(sources[name] + b"\n")
    with pytest.raises(applier.WebSolDeploymentApplyError, match="PREIMAGE_CONFLICT"):
        applier.apply_deployment(prepared)
    assert (root / "manifest.json").read_bytes() == sources["manifest.json"]
    assert all(not (root / name).exists() for name in assets)


@pytest.mark.parametrize("defect", ["native_artifact", "path_escape", "preimage", "version", "wrapper", "extra"])
def test_closed_cli_overlay_rejects_modified_bundle_even_with_new_digest(tmp_path, defect):
    root, binding, sources, assets = _inputs(tmp_path, "0.4.0")
    bundle = _render(root, binding, sources, assets)
    wire = bundle.private_document()
    if defect == "native_artifact":
        wire["artifacts"][0]["kind"] = "native_manifest"
    elif defect == "path_escape":
        wire["artifacts"][0]["destination"] = str(root.parent / "outside.js")
    elif defect == "preimage":
        wire["required_preimage_digests"][0]["sha256"] = "0" * 64
    elif defect == "version":
        wire["base_package_version"] = "0.2.0"
    elif defect == "wrapper":
        wire["wrapper_argv"] = ["/usr/bin/true"]
    else:
        wire["unrecognized"] = "value"
    fields = dict(vars(bundle))
    for name in ("base_package_version", "base_source_commit", "base_capability_digest"):
        fields[name] = wire[name]
    fields["wrapper_argv"] = tuple(wire["wrapper_argv"])
    fields["artifacts"] = tuple(cli._decode_artifact(row) for row in wire["artifacts"])
    fields["required_preimage_digests"] = tuple(
        (row["name"], row["sha256"]) for row in wire["required_preimage_digests"]
    )
    wire["bundle_digest"] = overlay._overlay_digest(fields)
    with pytest.raises(applier.WebSolDeploymentApplyError, match="INVALID_INPUT"):
        cli._decode_bundle(wire)


def test_overlay_requires_exact_install_root(tmp_path):
    root, binding, sources, assets = _inputs(tmp_path, "0.2.0")
    bundle = _render(root, binding, sources, assets)
    plan = deployment.plan_deployment(bundle, {str(root / name): value for name, value in sources.items()})
    with pytest.raises(applier.WebSolDeploymentApplyError, match="OVERLAY_ROOT_MISMATCH"):
        applier.prepare_deployment(
            bundle, plan, install_root=tmp_path,
            expected_uid=tmp_path.stat().st_uid, expected_gid=tmp_path.stat().st_gid,
            operation_key="browser-overlay-wrong-root",
        )


def test_overlay_reads_each_caller_source_mapping_once(tmp_path):
    from collections.abc import Mapping

    root, binding, sources, assets = _inputs(tmp_path, "0.4.0")

    class Changing(Mapping):
        def __init__(self, data):
            self.data, self.reads = data, {}

        def __iter__(self):
            return iter(self.data)

        def __len__(self):
            return len(self.data)

        def __getitem__(self, key):
            self.reads[key] = self.reads.get(key, 0) + 1
            return self.data[key] if self.reads[key] == 1 else b"unvalidated replacement"

    changing = Changing(sources)
    bundle = _render(root, binding, changing, assets)
    assert set(changing.reads.values()) == {1}
    assert all(b"unvalidated replacement" not in row.content for row in bundle.artifacts)


def test_recovered_applied_overlay_refuses_root_change_despite_rehashed_state(tmp_path):
    root, binding, sources, assets = _inputs(tmp_path, "0.4.0")
    bundle = _render(root, binding, sources, assets)
    prepared = _prepare(bundle, root, sources)
    request = _request(bundle, prepared)
    applied = applier.apply_deployment(prepared)
    state = cli._private_state_document(
        request_document=request, prepared=prepared, phase="APPLIED", applied=applied
    )
    state["request"]["install_root"] = str(root.parent)
    state.pop("state_digest")
    state["state_digest"] = hashlib.sha256(cli._canonical_bytes(state)).hexdigest()
    with pytest.raises(applier.WebSolDeploymentApplyError, match="INVALID_INPUT"):
        cli._decode_private_state(state)

    # Direct Python entry points must enforce the same declared profile root.
    prepared.install_root = root.parent
    for operation in (applier.verify_applied_deployment, applier.rollback_deployment):
        with pytest.raises(applier.WebSolDeploymentApplyError, match="OVERLAY_ROOT_MISMATCH"):
            operation(applied)
        assert applied._state == prepared._state == "APPLIED"
    prepared.install_root = root
    applier.rollback_deployment(applied)
    assert all((root / name).read_bytes() == value for name, value in sources.items())
