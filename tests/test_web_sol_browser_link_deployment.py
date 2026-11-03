"""Combined extension composition through the incumbent transactional owner."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys

import pytest

from control_plane import surface_bindings
from integrations.chairman_surfaces import web_sol_deployment as deployment
from integrations.chairman_surfaces import web_sol_deployment_apply as applier
from integrations.chairman_surfaces import web_sol_protocol as protocol
from scripts import web_sol_deployment_apply as cli

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrations/chairman_surfaces/web_sol_extension"
LINK = ROOT / "integrations/mastermind_browser_link/extension"
NAMES = ("manifest.json", "background.js", "content.js", "census.html",
         "census.css", "census_core.js", "census.js")


def digests(rows):
    return {name: hashlib.sha256(value).hexdigest() for name, value in rows.items()}


def inputs(tmp_path):
    root = tmp_path / "install"
    root.mkdir(mode=0o700)
    release = deployment.WebSolRelease(
        package_version=protocol.WEB_SOL_PACKAGE_VERSION,
        source_commit="c" * 40, repository_root=tmp_path / "repo",
        python_executable=Path(sys.executable), install_root=root,
    )
    binding = surface_bindings.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM", role="ceo", provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={"env_manager": "multilogin",
                 "folder_id": "11111111-1111-4111-8111-111111111111",
                 "profile_id": "22222222-2222-4222-8222-222222222222",
                 "url": "https://chatgpt.com/c/session-alpha"},
        observed_at="2026-08-30T10:00:00Z", seat_ref="chatgpt1",
        binding_id="33333333-3333-4333-8333-333333333333",
    )
    sources = {name: (SOURCE / name).read_bytes() for name in NAMES}
    assets = {
        "browser-link-bootstrap.js": (LINK / "websol-bootstrap.js").read_bytes(),
        "browser-link/worker.bundle.js": b'(() => { "use strict"; })();\n',
        **{f"browser-link/{name}": (LINK / name).read_bytes()
           for name in ("popup.html", "popup.css", "popup.mjs")},
    }
    return binding, release, sources, assets


def compose(binding, release, sources, assets, **overrides):
    kwargs = dict(source_files=sources, expected_source_digests=digests(sources),
                  browser_link_files=assets, expected_browser_link_digests=digests(assets))
    kwargs.update(overrides)
    return deployment.render_browser_link_extension_bundle(binding, release, **kwargs)


def test_combined_bundle_preserves_identity_transport_and_original_worker(tmp_path):
    binding, release, sources, assets = inputs(tmp_path)
    base = deployment.render_census_extension_bundle(
        binding, release, source_files=sources, expected_source_digests=digests(sources))
    combined = compose(binding, release, sources, assets)
    before = {row.kind: row for row in base.artifacts}
    after = {row.kind: row for row in combined.artifacts}
    assert len(combined.artifacts) == len(base.artifacts) + 5
    for kind, row in before.items():
        if kind not in {"extension_manifest", "extension_census_html"}:
            assert row == after[kind]
    old = json.loads(before["extension_manifest"].content)
    new = json.loads(after["extension_manifest"].content)
    for key in ("key", "version", "host_permissions", "content_scripts", "action"):
        assert new[key] == old[key]
    assert new["permissions"] == ["nativeMessaging", "alarms", "debugger", "tabs", "storage"]
    assert new["background"] == {"service_worker": "browser-link-bootstrap.js"}
    assert new["action"]["default_popup"] == "census.html"
    assert new["minimum_chrome_version"] == "116"
    html = after["extension_census_html"].content
    assert b'href="browser-link/popup.html"' in html
    assert b'target="_blank"' not in html
    assert combined.public_receipt["package_version"] == base.public_receipt["package_version"]
    assert combined.bundle_digest != base.bundle_digest
    assert combined == compose(binding, release, sources, assets)


@pytest.mark.parametrize("defect", ["extra", "missing", "empty", "oversize", "digest"])
def test_combined_assets_are_closed_bounded_and_exact(tmp_path, defect):
    binding, release, sources, assets = inputs(tmp_path)
    expected = digests(assets)
    if defect == "extra":
        assets["../escape.js"] = b"unexpected"
    elif defect == "missing":
        del assets["browser-link/popup.css"]
    elif defect == "empty":
        assets["browser-link/popup.css"] = b""
    elif defect == "oversize":
        assets["browser-link/worker.bundle.js"] = b"x" * 262145
    else:
        assets["browser-link/worker.bundle.js"] += b"drift"
    with pytest.raises(deployment.WebSolDeploymentError):
        compose(binding, release, sources, assets, expected_browser_link_digests=expected)


def test_combined_renderer_refuses_other_web_sol_release_and_legacy_permission_widening(tmp_path):
    binding, release, sources, assets = inputs(tmp_path)
    manifest = json.loads(sources["manifest.json"])
    manifest["version"] = "0.4.0"
    sources["manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_manifest_invalid"):
        compose(binding, release, sources, assets)
    manifest["version"] = protocol.WEB_SOL_PACKAGE_VERSION
    manifest["permissions"].append("debugger")
    sources["manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_manifest_invalid"):
        deployment.render_census_extension_bundle(
            binding, release, source_files=sources, expected_source_digests=digests(sources))


def test_combined_bundle_round_trips_through_existing_private_cli_decoder(tmp_path):
    binding, release, sources, assets = inputs(tmp_path)
    bundle = compose(binding, release, sources, assets)
    wire = {
        "instance_id": bundle.instance_id, "native_host_name": bundle.native_host_name,
        "source_commit": bundle.source_commit, "wrapper_argv": list(bundle.wrapper_argv),
        "bundle_digest": bundle.bundle_digest,
        "artifacts": [
            {"kind": row.kind, "destination": str(row.destination), "mode": row.mode,
             "content_base64": base64.b64encode(row.content).decode(), "sha256": row.sha256}
            for row in bundle.artifacts
        ],
    }
    decoded = cli._decode_bundle(wire)
    assert decoded.as_files() == bundle.as_files()
    assert decoded.bundle_digest == bundle.bundle_digest


def test_real_transactional_upgrade_readback_and_rollback_preserve_base(tmp_path):
    binding, release, sources, assets = inputs(tmp_path)
    base = deployment.render_census_extension_bundle(
        binding, release, source_files=sources, expected_source_digests=digests(sources))
    combined = compose(binding, release, sources, assets)
    root = release.install_root

    def prepare(bundle, current, operation):
        return applier.prepare_deployment(
            bundle, deployment.plan_deployment(bundle, current),
            install_root=root, expected_uid=root.stat().st_uid,
            expected_gid=root.stat().st_gid, operation_key=operation)

    initial = applier.apply_deployment(prepare(base, {}, "browser-base-test"))
    assert applier.verify_applied_deployment(initial)["target_count"] == len(base.artifacts)
    upgrade = prepare(combined, base.as_files(), "browser-combined-test")
    assert upgrade.public_receipt["update_count"] == 2
    assert upgrade.public_receipt["create_count"] == 5
    applied = applier.apply_deployment(upgrade)
    assert applier.verify_applied_deployment(applied)["target_count"] == len(combined.artifacts)
    assert deployment.verify_deployment_readback(
        combined, {str(row.destination): row.destination.read_bytes() for row in combined.artifacts}
    )["ok"] is True
    applier.rollback_deployment(applied)
    assert all(row.destination.read_bytes() == row.content for row in base.artifacts)
    assert all(not row.destination.exists() for row in combined.artifacts
               if row.kind not in {base_row.kind for base_row in base.artifacts})


def test_combination_uses_the_validated_immutable_base_snapshot(tmp_path):
    from collections.abc import Mapping

    binding, release, sources, assets = inputs(tmp_path)

    class ChangingSources(Mapping):
        def __init__(self):
            self.reads = {}

        def __iter__(self):
            return iter(sources)

        def __len__(self):
            return len(sources)

        def __getitem__(self, name):
            self.reads[name] = self.reads.get(name, 0) + 1
            if self.reads[name] > 1:
                return b"unvalidated replacement"
            return sources[name]

    changing = ChangingSources()
    bundle = deployment.render_browser_link_extension_bundle(
        binding, release, source_files=changing,
        expected_source_digests=digests(sources),
        browser_link_files=assets, expected_browser_link_digests=digests(assets),
    )
    assert changing.reads["manifest.json"] == 1
    assert changing.reads["census.html"] == 1
    assert b"unvalidated replacement" not in b"".join(row.content for row in bundle.artifacts)
