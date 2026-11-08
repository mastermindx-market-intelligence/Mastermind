"""The attended closure carries the existing native Worker entry, never another service."""
import json
from pathlib import Path
import pytest
from integrations.deepseek_harness import package_attended as package
from control_plane.native_provider_attestation import (
    DSH_ENTRYPOINT, DSH_PROTOCOL_NAME, DSH_PROTOCOL_VERSION, DSH_MODEL_PROVIDER)


def test_same_release_carries_exact_fixed_native_worker_source_and_overlay(tmp_path):
    release=tmp_path/"release with spaces";release.mkdir()
    result=package.package_native_worker(release)
    assert result["native_worker"] == dict(schema="mastermind.dsh_native_worker_entry/v1",
        entry=DSH_ENTRYPOINT,sha256=package.sha(package.HERE/DSH_ENTRYPOINT),
        agent_name=DSH_PROTOCOL_NAME,agent_version=DSH_PROTOCOL_VERSION,model_provider=DSH_MODEL_PROVIDER)
    assert result["native_worker_patch_sha256"] == package.sha(package.HERE/"native_worker.patch.yml")
    for name in ("native_worker.mjs","native_worker.patch.yml"):
        assert (release/name).read_bytes() == (package.HERE/name).read_bytes()
        assert package.inventory(release)[name]["sha256"] == package.sha(package.HERE/name)
    assert sorted(path.name for path in release.iterdir()) == ["native_worker.mjs","native_worker.patch.yml"]
    with pytest.raises(FileExistsError): package.package_native_worker(release)


def test_native_worker_stage_cannot_follow_a_replaced_source_link(tmp_path,monkeypatch):
    inputs=tmp_path/"inputs";inputs.mkdir()
    (inputs/"native_worker.mjs").symlink_to(package.HERE/"native_worker.mjs")
    monkeypatch.setattr(package,"HERE",inputs)
    release=tmp_path/"release";release.mkdir()
    with pytest.raises(ValueError,match="source redirected"): package.package_native_worker(release)
    assert list(release.iterdir()) == []


@pytest.fixture
def qualified_worker_candidate(tmp_path,monkeypatch):
    import subprocess
    import shutil
    from ops.executive_os import os_public_edge_publication, install_source_policy
    release=tmp_path/"complete-release";release.mkdir()
    worker=package.package_native_worker(release)
    source=tmp_path/"source";source.mkdir()
    folder=source/"integrations/deepseek_harness";folder.mkdir(parents=True)
    for name in ("native_worker.mjs","native_worker.patch.yml"):
        shutil.copy2(release/name,folder/name)
    def git(*args):
        return subprocess.check_output(["git","-c","gc.auto=0","-C",str(source),*args],text=True).strip()
    git("init","-q","-b","master");git("add",".")
    git("-c","user.name=Fixture","-c","user.email=fixture@example.invalid",
        "-c","commit.gpgsign=false","commit","-qm","original native Worker source")
    head,tree=git("rev-parse","HEAD"),git("rev-parse","HEAD^{tree}")
    config={**worker,"native_session_patch":{"fixture":1},"native_owner_access":{"fixture":1},
        "native_acp_patch":{"fixture":1},"company_host_exports":{"./company-peer":{},"./executive-read-port":{}},
        "node":"/inert/source-qualified/node","node_sha256":"a"*64}
    accepted=dict(config)
    manifest=release/"package-manifest.json";manifest.write_text("{}\n")
    monkeypatch.setattr(os_public_edge_publication,"_root",lambda:None)
    def protected(*,source_repo,expected_sha):
        assert source_repo == source and expected_sha == head
        return tree
    monkeypatch.setattr(install_source_policy,"validate_acceptance_source",protected)
    def existing_closure(**kwargs):
        assert kwargs == dict(release=release,source_repo=source,source_sha=head)
        return (tree,manifest,manifest.read_bytes(),package.inventory_identity(release),accepted,
                b"separately qualified full closure",{},config,{})
    # The established full-package/root-custody checks are qualified elsewhere.
    # These tests exercise the new actual git-pinned entry/overlay boundary.
    monkeypatch.setattr(package,"_qualified_release_source",existing_closure)
    return release,source,head,config,accepted


def test_native_worker_qualification_uses_the_same_protected_overlay(qualified_worker_candidate):
    release,source,head,config,accepted=qualified_worker_candidate
    result=package.qualify_native_worker_package(release=release,source_repo=source,source_sha=head)
    assert result["native_worker"] == config["native_worker"]
    assert result["source_sha"] == head and result["entrypoint_sha256"] == package.sha(release/DSH_ENTRYPOINT)


@pytest.mark.parametrize("changed",["overlay-bytes","overlay-link","accepted-overlay"])
def test_native_qualifier_refuses_locally_relabelled_or_redirected_overlay(qualified_worker_candidate,tmp_path,changed):
    release,source,head,config,accepted=qualified_worker_candidate
    patch=release/"native_worker.patch.yml"
    if changed == "overlay-bytes":
        patch.write_bytes(patch.read_bytes()+b"\n# unaccepted local configuration\n")
        config["native_worker_patch_sha256"]=accepted["native_worker_patch_sha256"]=package.sha(patch)
    elif changed == "overlay-link":
        outside=tmp_path/"outside.yml";outside.write_bytes(patch.read_bytes())
        patch.unlink();patch.symlink_to(outside)
    else: accepted["native_worker_patch_sha256"]="f"*64
    with pytest.raises(ValueError):
        package.qualify_native_worker_package(release=release,source_repo=source,source_sha=head)
