"""Small real-file source fixtures for the attended snapshot exporter.

No donor build, installed application, live route or provider is represented.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from integrations.deepseek_harness import package_attended as package
from ops.executive_os import os_public_edge_publication as publication


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def native_package(tmp_path, monkeypatch):
    monkeypatch.setattr(publication, "_root", lambda: None)
    monkeypatch.setattr(publication.assets, "require_sealed_path", lambda *a, **k: None)
    monkeypatch.setattr(publication.assets, "_no_acl", lambda *a, **k: None)
    monkeypatch.setattr(publication, "_owner", lambda s: publication.require(
        s.st_uid == os.getuid() and not s.st_mode & 0o022, "fixture custody"))
    release, source = tmp_path / "app", tmp_path / "source"
    release.mkdir()
    source.mkdir()
    contents = {
        "app/apps/web/dist/index.html": b'<script src="./assets/index-fixture.js"></script><link href="./assets/index-fixture.css">',
        "app/apps/web/dist/assets/index-fixture.js": b"export const fixture = true;",
        "app/apps/web/dist/assets/index-fixture.css": b"body{color:white}",
        "app/.dsh-build/client-build-environment.json": b'{"environment":{"DSH_CLIENT_TITLE":"Mastermind"}}',
        "company_plugin/lib/client.js": b"export {};",
        "company_plugin/lib/index.js": b"export {};",
        "launch_attended.mjs": b"// inert fixture launcher\n",
        "unused-native-file.txt": b"closure still must bind this",
    }
    for name, raw in contents.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    source_plugin = source / "integrations/deepseek_harness/company_plugin/src/index.ts"
    source_plugin.parent.mkdir(parents=True)
    source_plugin.write_text("// fixture source\n")
    source_launcher = source / "integrations/deepseek_harness/launch_attended.mjs"
    source_launcher.write_bytes(contents["launch_attended.mjs"])
    build = {"schema": "mastermind.dsh.company_build.v1", "donor_sha": package.PIN,
             "source_sha256": {"src/index.ts": package.sha(source_plugin)},
             "client_sha256": package.sha(release / "company_plugin/lib/client.js")}
    (release / "company_plugin/lib/build-manifest.json").write_text(json.dumps(build))
    patch = [{"insert": [{"id": "mastermind-company",
        "name": str(release / "company_plugin/lib/index.js"), "config": {}}]}]
    (release / "company.patch.yml").write_text(json.dumps(patch))
    config = {"schema": "mastermind.dsh_attended_package.v1", "release": str(release),
              "donor_sha": package.PIN, "public_url": "https://chat.mastermind-x.com/",
              "port": 4180, "relay_port": 4181, "execution": "native-attended",
              "company_worker_admission": False, "company_client_sha256": build["client_sha256"],
              "company_patch_sha256": package.sha(release / "company.patch.yml"),
              "native_client_build_sha256": package.sha(release / "app/.dsh-build/client-build-environment.json")}
    (release / "app.json").write_text(json.dumps(config))
    manifest = {"schema": "mastermind.dsh_attended_package_closure.v1",
                "donor_sha": package.PIN, "files": package.inventory(release), "installed": False}
    (release / "package-manifest.json").write_text(json.dumps(manifest))
    accepted = {"schema": "mastermind.dsh_attended_build.v1", "donor_sha": package.PIN,
                "package_manifest_sha256": package.sha(release / "package-manifest.json"),
                "app_config_sha256": package.sha(release / "app.json"),
                "company_client_sha256": build["client_sha256"],
                "native_client_build_sha256": config["native_client_build_sha256"],
                "index_sha256": package.sha(release / "app/apps/web/dist/index.html"),
                "installed": False, "provider_calls": 0}
    (source / package.QUALIFIED_BUILD_PATH).write_text(json.dumps(accepted))
    _git(source, "init", "-q", "-b", "master")
    _git(source, "add", ".")
    _git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "qualified source fixture")
    sha = _git(source, "rev-parse", "HEAD")
    _git(source, "update-ref", "refs/remotes/origin/master", sha)
    return {"release": release, "source_repo": source, "source_sha": sha, "out": tmp_path / "export"}


def test_export_captures_exact_assets_from_protected_package(native_package):
    result = package.export_publication(**native_package)
    assert result["state"] == "EXPORTED" and not result["installed"]
    with publication.private(native_package["out"]) as area:
        receipt, captures = publication._dsh_artifact(area, result["artifact_digest"])
        assert receipt["source"]["sha"] == native_package["source_sha"]
        assert set(captures) == {"artifact-receipt.json", "client.js.blob", "client.css.blob"}
        assert not receipt["public_route_qualified"] and receipt["provider_calls"] == 0


def test_local_manifest_cannot_approve_changed_package(native_package):
    release = native_package["release"]
    (release / "unused-native-file.txt").write_text("changed")
    path = release / "package-manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["files"]["unused-native-file.txt"]["sha256"] = package.sha(release / "unused-native-file.txt")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="protected build qualification"):
        package.export_publication(**native_package)
    assert not native_package["out"].exists()


def test_snapshot_refuses_non_asset_drift_during_capture(native_package, monkeypatch):
    inventory = package.inventory

    def changed(root):
        result = inventory(root)
        (root / "unused-native-file.txt").write_text("changed after original complete read")
        return result

    monkeypatch.setattr(package, "inventory", changed)
    with pytest.raises(ValueError, match="changed during qualification"):
        package.export_publication(**native_package)
    assert not native_package["out"].exists()


def test_old_attended_build_cannot_qualify_native_worker(native_package):
    args={key:native_package[key] for key in ("release","source_repo","source_sha")}
    with pytest.raises(ValueError,match="complete original owner patch closure"):
        package.qualify_native_worker_package(**args)
    assert not native_package["out"].exists()
