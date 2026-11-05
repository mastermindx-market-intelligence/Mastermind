from __future__ import annotations

import ast
import base64
import hashlib
import json
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import web_sol_deployment as deployment
from integrations.chairman_surfaces import web_sol_instance as instance
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp


FOLDER_ID = "11111111-1111-4111-8111-111111111111"
PROFILE_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_COMMIT = "a" * 40


def binding(
    *,
    folder_id: str = FOLDER_ID,
    profile_id: str = PROFILE_ID,
    url: str = "https://chatgpt.com/c/session-alpha",
) -> dict:
    return sb.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "multilogin",
            "folder_id": folder_id,
            "profile_id": profile_id,
            "url": url,
        },
        observed_at="2026-08-30T10:00:00Z",
        seat_ref="chatgpt1",
        binding_id="33333333-3333-4333-8333-333333333333",
    )


def release(**overrides) -> deployment.WebSolRelease:
    values = {
        "package_version": wsp.WEB_SOL_PACKAGE_VERSION,
        "source_commit": SOURCE_COMMIT,
        "repository_root": Path("/opt/mastermind/Mastermind"),
        "python_executable": Path("/usr/bin/python3"),
        "install_root": Path("/Users/wsx/Library/Application Support/Mastermind/web-sol"),
    }
    values.update(overrides)
    return deployment.WebSolRelease(**values)


def files(bundle: deployment.DeploymentBundle) -> dict[str, bytes]:
    return bundle.as_files()


def artifact(bundle: deployment.DeploymentBundle, kind: str) -> deployment.DeploymentArtifact:
    matches = [row for row in bundle.artifacts if row.kind == kind]
    assert len(matches) == 1
    return matches[0]


def parse_instance_config(payload: bytes) -> dict:
    text = payload.decode("utf-8")
    prefix = "globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze("
    assert text.startswith(prefix)
    assert text.endswith(");\n")
    return json.loads(text[len(prefix) : -3])


def test_rendered_profile_bundle_is_deterministic_content_addressed_and_profile_specific():
    first = deployment.render_bundle(binding(), release())
    second = deployment.render_bundle(binding(), release())
    changed = deployment.render_bundle(
        binding(profile_id="44444444-4444-4444-8444-444444444444"),
        release(),
    )

    assert first == second
    assert first.bundle_digest == second.bundle_digest
    assert files(first) == files(second)
    assert first.instance_id == instance.adapter_instance_id(binding())
    assert first.native_host_name == instance.native_host_name(first.instance_id)
    assert first.instance_id != changed.instance_id
    assert first.native_host_name != changed.native_host_name
    assert first.bundle_digest != changed.bundle_digest


def test_instance_config_closes_all_three_package_versions_and_transport_identity():
    bundle = deployment.render_bundle(binding(), release())
    config = parse_instance_config(artifact(bundle, "instance_config").content)

    assert config == {
        "schema": wsp.INSTANCE_CONFIG_SCHEMA,
        "instanceId": bundle.instance_id,
        "nativeHost": bundle.native_host_name,
        "protocolMajor": wsp.TRANSPORT_PROTOCOL_MAJOR,
        "clientPackageVersion": wsp.WEB_SOL_PACKAGE_VERSION,
        "nativePackageVersion": wsp.WEB_SOL_PACKAGE_VERSION,
        "extensionPackageVersion": wsp.WEB_SOL_PACKAGE_VERSION,
        "capabilityDigest": wsp.transport_capability_digest(),
    }


def test_native_manifest_uses_unique_host_exact_extension_origin_and_absolute_wrapper():
    bundle = deployment.render_bundle(binding(), release())
    manifest = json.loads(artifact(bundle, "native_host_manifest").content)
    wrapper = artifact(bundle, "native_host_wrapper")

    assert manifest == {
        "name": bundle.native_host_name,
        "description": "Mastermind Web Sol exact-profile native bridge",
        "path": str(wrapper.destination),
        "type": "stdio",
        "allowed_origins": [native.ALLOWED_EXTENSION_ORIGIN],
    }
    assert wrapper.destination.is_absolute()
    assert wrapper.mode == 0o700
    assert manifest["name"] != native.NATIVE_HOST_NAME


def test_wrapper_fixes_repository_python_module_and_full_instance_before_chrome_arguments():
    bundle = deployment.render_bundle(binding(), release())
    wrapper = artifact(bundle, "native_host_wrapper").content.decode("utf-8")

    assert bundle.wrapper_argv == (
        "/usr/bin/python3",
        "-E",
        "-s",
        "-B",
        "-m",
        "integrations.chairman_surfaces.web_sol_native_host",
        "--instance-id",
        bundle.instance_id,
    )
    assert "cd '/opt/mastermind/Mastermind'" in wrapper
    assert "exec '/usr/bin/python3' -E -s -B -m integrations.chairman_surfaces.web_sol_native_host" in wrapper
    assert f"--instance-id {bundle.instance_id}" in wrapper
    assert wrapper.index(f"--instance-id {bundle.instance_id}") < wrapper.index('"$@"')
    assert "--instance-id=\"$" not in wrapper


def test_public_receipt_and_artifacts_do_not_expose_profile_folder_url_or_binding_identity():
    row = binding()
    bundle = deployment.render_bundle(row, release())
    rendered = json.dumps(bundle.public_receipt, sort_keys=True) + "\n" + "\n".join(
        item.content.decode("utf-8") for item in bundle.artifacts
    )

    for forbidden in (
        row["locator"]["folder_id"],
        row["locator"]["profile_id"],
        row["locator"]["url"],
        row["binding_id"],
        row["work_ref"],
        row["seat_ref"],
    ):
        assert forbidden not in rendered

    assert bundle.public_receipt["schema"] == deployment.PUBLIC_RECEIPT_SCHEMA
    assert bundle.public_receipt["source_commit"] == SOURCE_COMMIT
    assert bundle.public_receipt["instance_id"] == bundle.instance_id
    assert bundle.public_receipt["bundle_digest"] == bundle.bundle_digest
    assert set(bundle.public_receipt["artifact_digests"]) == {
        item.kind for item in bundle.artifacts
    }


def test_artifact_destinations_stay_inside_the_exact_install_root_and_are_unique():
    spec = release()
    bundle = deployment.render_bundle(binding(), spec)
    destinations = [item.destination for item in bundle.artifacts]

    assert len(destinations) == len(set(destinations))
    for destination in destinations:
        assert destination.is_absolute()
        assert destination.is_relative_to(spec.install_root)


def test_release_refuses_relative_or_unsafe_coordinates_and_mutable_source_names():
    cases = (
        {"repository_root": Path("relative/repo")},
        {"python_executable": Path("python3")},
        {"install_root": Path("relative/install")},
        {"source_commit": "main"},
        {"source_commit": "a" * 39},
        {"package_version": "latest"},
        {"package_version": "0.1"},
    )
    for overrides in cases:
        with pytest.raises(deployment.WebSolDeploymentError):
            release(**overrides)


def test_dry_run_plan_distinguishes_create_update_and_unchanged_without_writing():
    bundle = deployment.render_bundle(binding(), release())
    expected = files(bundle)

    create_plan = deployment.plan_deployment(bundle, {})
    assert {row.action for row in create_plan.changes} == {"CREATE"}

    unchanged_plan = deployment.plan_deployment(bundle, expected)
    assert {row.action for row in unchanged_plan.changes} == {"UNCHANGED"}

    changed_files = dict(expected)
    changed_path = next(iter(changed_files))
    changed_files[changed_path] = b"old bytes"
    update_plan = deployment.plan_deployment(bundle, changed_files)
    by_path = {str(row.path): row for row in update_plan.changes}
    assert by_path[changed_path].action == "UPDATE"
    assert by_path[changed_path].prior_sha256 == hashlib.sha256(b"old bytes").hexdigest()
    assert by_path[changed_path].next_sha256 == hashlib.sha256(expected[changed_path]).hexdigest()

    assert all(row.action in {"CREATE", "UPDATE", "UNCHANGED"} for row in update_plan.changes)
    assert not any(item.action == "DELETE" for item in update_plan.changes)


def test_rollback_manifest_records_exact_prior_presence_and_digest_without_copying_prior_bytes():
    bundle = deployment.render_bundle(binding(), release())
    expected = files(bundle)
    current = {next(iter(expected)): b"prior adapter bytes"}
    plan = deployment.plan_deployment(bundle, current)
    rollback = plan.rollback_manifest

    assert rollback["schema"] == deployment.ROLLBACK_MANIFEST_SCHEMA
    entries = {entry["path"]: entry for entry in rollback["entries"]}
    prior_path = next(iter(current))
    assert entries[prior_path] == {
        "path": prior_path,
        "prior_state": "PRESENT",
        "prior_sha256": hashlib.sha256(b"prior adapter bytes").hexdigest(),
    }
    for path, entry in entries.items():
        if path != prior_path:
            assert entry == {"path": path, "prior_state": "ABSENT", "prior_sha256": None}
    serialized = json.dumps(rollback, sort_keys=True)
    assert base64.b64encode(b"prior adapter bytes").decode("ascii") not in serialized
    assert "prior adapter bytes" not in serialized


def test_exact_readback_verification_passes_only_for_the_complete_bundle():
    bundle = deployment.render_bundle(binding(), release())
    expected = files(bundle)
    receipt = deployment.verify_deployment_readback(bundle, expected)

    assert receipt["schema"] == deployment.READBACK_RECEIPT_SCHEMA
    assert receipt["bundle_digest"] == bundle.bundle_digest
    assert receipt["ok"] is True

    missing = dict(expected)
    missing.pop(next(iter(missing)))
    with pytest.raises(deployment.WebSolDeploymentError, match="readback_mismatch"):
        deployment.verify_deployment_readback(bundle, missing)

    changed = dict(expected)
    changed[next(iter(changed))] = b"tampered"
    with pytest.raises(deployment.WebSolDeploymentError, match="readback_mismatch"):
        deployment.verify_deployment_readback(bundle, changed)


def test_bundle_digest_covers_destination_mode_content_and_source_commit():
    original = deployment.render_bundle(binding(), release())
    changed_commit = deployment.render_bundle(binding(), release(source_commit="b" * 40))
    changed_root = deployment.render_bundle(
        binding(),
        release(install_root=Path("/Users/wsx/Library/Application Support/Mastermind/web-sol-alt")),
    )

    assert original.bundle_digest != changed_commit.bundle_digest
    assert original.bundle_digest != changed_root.bundle_digest


def test_deployment_generator_is_pure_and_contains_no_install_shell_or_network_actuation():
    source_path = Path(deployment.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert imported.isdisjoint({"subprocess", "socket", "urllib", "requests", "httpx", "shutil"})
    lowered = source.lower()
    for forbidden in (
        "os.replace",
        "path.write_",
        "open(",
        "chmod(",
        "unlink(",
        "mkdir(",
        "system(",
        "popen(",
        "curl ",
        "wget ",
        "security ",
        "keychain",
    ):
        assert forbidden not in lowered
