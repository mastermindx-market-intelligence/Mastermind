"""Complete census packaging: integrity/readback proof, never installation proof."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from integrations.chairman_surfaces import web_sol_deployment as deployment
from test_web_sol_deployment import binding, release

NAMES = ("manifest.json", "background.js", "content.js", "census.html",
         "census.css", "census_core.js", "census.js")
ROOT = Path(__file__).resolve().parents[1]


def digest_map(assets):
    return {name: hashlib.sha256(value).hexdigest() for name, value in assets.items()}


@pytest.fixture
def assets():
    root = ROOT / "integrations/chairman_surfaces/web_sol_extension"
    values = {name: (root / name).read_bytes() for name in NAMES[:3]}
    manifest = json.loads(values["manifest.json"])
    manifest["action"] = {"default_title": "Session census", "default_popup": "census.html"}
    values["manifest.json"] = json.dumps(manifest).encode()
    values.update({"census.html": b'<!doctype html><script src="instance_config.js"></script><script src="census_core.js"></script><script src="census.js"></script><link rel="stylesheet" href="census.css">', "census.css": b"body {}", "census_core.js": b'"use strict";', "census.js": b'"use strict";'})
    return values


def render(assets, expected=None, row=None, spec=None):
    method = getattr(deployment, "render_census_extension_bundle", None)
    assert callable(method), "complete census bundle renderer is not implemented"
    return method(binding() if row is None else row, release() if spec is None else spec,
                  source_files=assets, expected_source_digests=digest_map(assets) if expected is None else expected)


def test_complete_bundle_preserves_generated_contract_and_all_source_bytes(assets):
    legacy = deployment.render_bundle(binding(), release())
    complete = render(assets)
    assert len(complete.artifacts) == 10
    assert set(legacy.artifacts).issubset(set(complete.artifacts))
    assert complete.bundle_digest != legacy.bundle_digest
    assert complete.wrapper_argv == legacy.wrapper_argv
    rows = {item.destination.name: item for item in complete.artifacts}
    for name, content in assets.items():
        assert rows[name].content == content and rows[name].mode == 0o600
        assert rows[name].destination.parent.name == complete.instance_id[:24]
    assert len(complete.public_receipt["artifact_digests"]) == 10
    assert deployment.verify_deployment_readback(complete, complete.as_files())["ok"] is True


def test_complete_bundle_public_receipt_exposes_integrity_not_source_or_profile_identity(assets):
    raw_profile_id = "44444444-4444-4444-8444-444444444444"
    exact_source_commit = "f" * 40
    bundle = render(
        assets,
        row=binding(profile_id=raw_profile_id),
        spec=release(source_commit=exact_source_commit),
    )

    receipt = bundle.public_receipt
    assert set(receipt) == {
        "schema",
        "package_version",
        "protocol_major",
        "capability_digest",
        "bundle_digest",
        "artifact_digests",
    }
    assert receipt["schema"] == deployment.PUBLIC_RECEIPT_SCHEMA
    assert receipt["bundle_digest"] == bundle.bundle_digest
    assert receipt["artifact_digests"] == {
        item.kind: item.sha256 for item in bundle.artifacts
    }

    serialized = json.dumps(receipt, sort_keys=True)
    for forbidden in (
        exact_source_commit,
        raw_profile_id,
        bundle.instance_id,
        bundle.native_host_name,
    ):
        assert forbidden not in serialized


def test_order_independence_immutability_and_profile_isolation(assets):
    before = copy.deepcopy(assets)
    first = render(assets)
    second = render(dict(reversed(list(assets.items()))))
    assert first == second and assets == before
    other = render(assets, row=binding(profile_id="44444444-4444-4444-8444-444444444444"))
    assert first.instance_id != other.instance_id and first.bundle_digest != other.bundle_digest


@pytest.mark.parametrize("name", NAMES)
def test_every_source_member_is_required(assets, name):
    assets.pop(name)
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_sources_invalid"):
        render(assets)


@pytest.mark.parametrize("name", NAMES)
def test_every_source_member_is_integrity_checked(assets, name):
    expected = digest_map(assets)
    assets[name] += b"tampered-private-marker"
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_source_digest_mismatch") as caught:
        render(assets, expected)
    assert "private-marker" not in str(caught.value)


@pytest.mark.parametrize("name", ["../private.js", "https://invalid.test/a.js", "instance_config.js"])
def test_extra_or_generated_source_is_rejected(assets, name):
    assets[name] = b"private-marker"
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_sources_invalid"):
        render(assets)


@pytest.mark.parametrize("bad", [b"", "not-bytes", bytearray(b"mutable"), b"x" * 262145])
def test_bad_source_type_and_size_are_rejected(assets, bad):
    assets["census.css"] = bad
    expected = {name: "a" * 64 for name in NAMES}
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_source_content_invalid"):
        render(assets, expected)


@pytest.mark.parametrize("field,value", [
    ("manifest_version", True), ("manifest_version", 2), ("version", "9.0.0"),
    ("background", {"service_worker": "elsewhere.js"}),
    ("permissions", ["nativeMessaging", "alarms", "debugger"]),
    ("host_permissions", ["<all_urls>"]),
    ("action", {"default_popup": "https://invalid.test/a.html"}),
    ("content_scripts", [{"js": ["remote.js"]}]),
    ("key", "not-a-public-key"), ("web_accessible_resources", []),
])
def test_unsupported_manifest_layout_is_rejected(assets, field, value):
    manifest = json.loads(assets["manifest.json"])
    manifest[field] = value
    assets["manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_manifest_invalid"):
        render(assets)


@pytest.mark.parametrize("payload", [b"not-json", b"[]", b"\xff", b'{"version":"0.1.0","version":"9"}'])
def test_malformed_or_duplicate_manifest_is_rejected(assets, payload):
    assets["manifest.json"] = payload
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_manifest_invalid"):
        render(assets)


@pytest.mark.parametrize("digest", [None, True, "A" * 64, "a" * 63, "private-marker"])
def test_malformed_expected_digest_is_rejected(assets, digest):
    expected = digest_map(assets); expected["census.css"] = digest
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_source_digests_invalid"):
        render(assets, expected)


@pytest.mark.parametrize("index", range(10))
@pytest.mark.parametrize("change", ["missing", "modified"])
def test_readback_requires_every_generated_and_static_artifact(assets, index, change):
    bundle = render(assets); observed = bundle.as_files()
    name = str(bundle.artifacts[index].destination)
    if change == "missing":
        observed.pop(name)
    else:
        observed[name] = b"untrusted bytes"
    with pytest.raises(deployment.WebSolDeploymentError, match="readback_mismatch"):
        deployment.verify_deployment_readback(bundle, observed)


def test_complete_plan_and_rollback_cover_new_and_prior_assets(assets):
    bundle = render(assets); observed = bundle.as_files()
    before = {str(item.destination): b"prior" for item in bundle.artifacts[:4]}
    original = dict(before)
    plan = deployment.plan_deployment(bundle, before)
    assert len(plan.changes) == 10 and before == original
    assert [row.action for row in plan.changes].count("UPDATE") == 4
    assert [row.action for row in plan.changes].count("CREATE") == 6
    entries = plan.rollback_manifest["entries"]
    assert {entry["path"] for entry in entries} == set(observed)
    for entry in entries:
        assert entry["prior_state"] == ("PRESENT" if entry["path"] in before else "ABSENT")
    unchanged = deployment.plan_deployment(bundle, observed)
    assert {row.action for row in unchanged.changes} == {"UNCHANGED"}
    receipt = json.dumps(bundle.public_receipt)
    assert str(release().install_root) not in receipt and "prior" not in receipt


def test_generation_digest_changes_but_native_capability_does_not(assets):
    first = render(assets)
    assets["census.css"] += b"\n/* reviewed new bytes */"
    second = render(assets)
    assert first.bundle_digest != second.bundle_digest
    assert first.public_receipt["capability_digest"] == second.public_receipt["capability_digest"]
    assert first.public_receipt["package_version"] == second.public_receipt["package_version"]
    newer = render(assets, spec=release(source_commit="b" * 40))
    assert second.bundle_digest != newer.bundle_digest


def test_total_size_and_digest_key_census_are_bounded(assets):
    oversized = dict(assets)
    for name in NAMES[1:]:
        oversized[name] = b"x" * 262144
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_source_content_invalid"):
        render(oversized)
    for expected in [{}, {**digest_map(assets), "extra": "a" * 64}]:
        with pytest.raises(deployment.WebSolDeploymentError, match="extension_source_digests_invalid"):
            render(assets, expected)


def test_renderer_does_not_read_source_paths(assets, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("renderer attempted filesystem access")
    with monkeypatch.context() as guard:
        guard.setattr(Path, "read_bytes", forbidden)
        guard.setattr(Path, "read_text", forbidden)
        assert len(render(assets).artifacts) == 10


def test_duplicate_otherwise_valid_manifest_field_is_refused(assets):
    original = assets["manifest.json"]
    assets["manifest.json"] = original[:-1] + b',"version":"0.1.0"}'
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_manifest_invalid"):
        render(assets)


def test_wrong_identity_is_refused_even_with_valid_base64(assets):
    import base64
    manifest = json.loads(assets["manifest.json"])
    manifest["key"] = base64.b64encode(b"another extension public key").decode("ascii")
    assets["manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_manifest_invalid"):
        render(assets)


@pytest.mark.parametrize("bad", [None, [], "private-marker"])
def test_non_mapping_source_is_refused_without_payload(assets, bad):
    method = getattr(deployment, "render_census_extension_bundle", None)
    assert callable(method)
    with pytest.raises(deployment.WebSolDeploymentError, match="extension_sources_invalid") as caught:
        method(binding(), release(), source_files=bad, expected_source_digests=digest_map(assets))
    assert "private-marker" not in str(caught.value)
