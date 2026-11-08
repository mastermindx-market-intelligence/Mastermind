"""Real staging/layout and protected-source relocation, with inert donor build seams.

These fixtures copy/seal actual files and qualify actual temporary Git blobs.
They do not represent a full donor build, root installation or provider access.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
from types import SimpleNamespace
import pytest

from integrations.deepseek_harness import package_attended as package
from test_deepseek_attended_export import native_package


@pytest.fixture
def stage_inputs(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    donor = root/"donor with spaces"
    donor.mkdir()
    files = {
        "apps/cli/lib/bin.js": "// inert CLI\n",
        "apps/web/dist/index.html": "<html>fixture</html>\n",
        "packages/core/scope/package.json": '{"name":"@deepseek-ai/dsh-scope"}',
        "packages/core/scope/lib/index.js": "export {};\n",
        "node_modules/.pnpm/pkg/node_modules/pkg/index.js": "export {};\n",
        "LICENSE": "fixture upstream license\n",
    }
    for name, raw in files.items():
        path = donor/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
    (donor/"apps/cli/lib/bin.js").chmod(0o755)
    (donor/"node_modules/pkg").symlink_to(".pnpm/pkg/node_modules/pkg", target_is_directory=True)
    source = root/"company source"
    company = source/"company_plugin"
    (company/"lib").mkdir(parents=True)
    (company/"src").mkdir()
    (company/"src/index.ts").write_text("// inert company source\n")
    for name in ("client.js", "index.js", "company-peer.js", "executive-read-port.js"):
        (company/"lib"/name).write_text("export {};\n")
    build = {"schema":"mastermind.dsh.company_build.v1", "donor_sha":package.PIN,
        "source_sha256":{"src/index.ts":package.sha(company/"src/index.ts")},
        "client_sha256":package.sha(company/"lib/client.js"),
        "host_exports":{key:{"file":name, "sha256":package.sha(company/"lib"/name)}
            for key,name in (("./company-peer","company-peer.js"),
                             ("./executive-read-port","executive-read-port.js"))}}
    (company/"lib/build-manifest.json").write_text(json.dumps(build))
    (company/"package.json").write_text('{"name":"fixture-company"}')
    original_source = package.HERE
    for name in ("launch_attended.mjs", "native_worker.mjs", "native_worker.patch.yml"):
        shutil.copyfile(original_source/name, source/name)
    monkeypatch.setattr(package, "HERE", source)
    node = root/"signed build Node"
    node.write_bytes(b"#!/bin/sh\nexit 99\n")
    node.chmod(0o755)
    pnpm = root/"pnpm/bin/pnpm.cjs"
    pnpm.parent.mkdir(parents=True)
    pnpm.write_text("// inert build-tool entry\n")
    (pnpm.parent.parent/"package.json").write_text('{"version":"11.28.5"}')
    args = SimpleNamespace(donor=str(donor), release=str(root/"private native candidate"),
        state=None, native_layout=True, installed_release=str(root/"enrolled final package"),
        installed_node=str(root/"enrolled final Node"), node=str(node), pnpm=str(pnpm),
        public_url="https://chat.mastermind-x.com/", port=4180, relay_port=4181)
    calls = []
    def git(argv, **kwargs):
        assert argv[:5] == ["git", "-c", "gc.auto=0", "-C", str(donor)]
        if argv[5:] == ["rev-parse", "HEAD"]: return package.PIN+"\n"
        assert argv[5:] == ["status", "--porcelain"]
        return ""
    def build_artifacts(argv, **kwargs):
        assert argv == [str(node), str(pnpm), "run", "build:artifacts"]
        assert kwargs["cwd"] == Path(args.release)/"app"
        assert kwargs["env"]["PATH"].split(os.pathsep)[0] == str(node.parent)
        assert kwargs["env"]["DSH_CLIENT_TITLE"] == "Mastermind"
        assert kwargs["env"]["DSH_CLIENT_COMMIT_HASH"] == package.PIN
        assert kwargs["check"] is True and kwargs["stdin"] == subprocess.DEVNULL
        calls.append(argv)
        target = kwargs["cwd"]/".dsh-build/client-build-environment.json"
        target.parent.mkdir()
        target.write_text(json.dumps({"environment":{"DSH_CLIENT_TITLE":"Mastermind"}}))
    monkeypatch.setattr(package, "subprocess", SimpleNamespace(
        check_output=git, run=build_artifacts, DEVNULL=subprocess.DEVNULL))
    # Original patch transformations have independent donor/source qualification.
    # This fixture concentrates on layout, full-copy sealing and build Node choice.
    monkeypatch.setattr(package.native_session, "manifest", lambda: None)
    monkeypatch.setattr(package.native_owner_access, "qualify_inputs", lambda: None)
    monkeypatch.setattr(package.native_acp_lifecycle, "qualify_inputs", lambda: None)
    monkeypatch.setattr(package, "package_native_session", lambda *a: {"fixture":"original-session"})
    monkeypatch.setattr(package.native_owner_access, "package", lambda *a: {"fixture":"original-access"})
    monkeypatch.setattr(package.native_acp_lifecycle, "package", lambda *a: {"fixture":"original-acp"})
    return args, calls


def test_native_stage_records_final_paths_before_sealing_without_creating_state_or_plist(stage_inputs):
    args, calls = stage_inputs
    node_before = Path(args.node).read_bytes(), Path(args.node).stat().st_mode
    original_state = Path(args.release).parent/"original Worker state"
    original_state.mkdir()
    sentinel = original_state/"account-sentinel"
    sentinel.write_bytes(b"original owner unchanged")
    old_umask = os.umask(0o077)
    try:
        result = package.stage(args)
    finally:
        os.umask(old_umask)
    assert (Path(args.node).read_bytes(), Path(args.node).stat().st_mode) == node_before
    assert sentinel.read_bytes() == b"original owner unchanged"
    release = Path(args.release)
    config = json.loads((release/"app.json").read_bytes())
    assert config["release"] == args.installed_release and config["node"] == args.installed_node
    assert config["node_sha256"] == package.sha(Path(args.node))
    assert config["state"] is None and config["state_owner"] == "original-worker"
    assert result["state"] is None and result["state_owner"] == "original-worker"
    assert result["installation_release"] == args.installed_release
    assert not result["installed"] and result["provider_calls"] == 0
    assert not Path(args.installed_release).exists() and not Path(args.installed_node).exists()
    for name in ("home", "state", "workspace", "logs", "com.mastermind.deepseek.web.plist"):
        assert not (release/name).exists()
    overlay = json.loads((release/"company.patch.yml").read_bytes())
    assert overlay[0]["insert"][0]["name"] == args.installed_release+"/company_plugin/lib/index.js"
    manifest = json.loads((release/"package-manifest.json").read_bytes())
    observed = package.inventory(release)
    observed.pop("package-manifest.json")
    assert manifest["files"] == observed and manifest["installed"] is False
    assert (release/"package-manifest.json").stat().st_mode & 0o777 == 0o444
    assert release.stat().st_mode & 0o777 == 0o755
    assert all(p.stat().st_mode & 0o777 == 0o755 for p in release.rglob("*")
               if p.is_dir() and not p.is_symlink())
    assert observed["app/apps/cli/lib/bin.js"]["mode"] == 0o555
    assert all(row["mode"] in (0o444, 0o555) for row in observed.values() if "mode" in row)
    assert os.readlink(release/"app/node_modules/pkg") == ".pnpm/pkg/node_modules/pkg"
    package.verify_company_scope(release)
    assert calls == [[args.node, args.pnpm, "run", "build:artifacts"]]


def test_legacy_attended_stage_retains_original_state_and_launcher_contract(stage_inputs):
    args, _ = stage_inputs
    args.native_layout = False
    args.installed_release = args.installed_node = None
    args.state = str(Path(args.release).parent/"attended state")
    result = package.stage(args)
    release = Path(args.release)
    config = json.loads((release/"app.json").read_bytes())
    assert config["release"] == args.release and config["node"] == args.node
    assert config["state"] == args.state and "state_owner" not in config
    assert result["state"] == args.state and "installation_release" not in result
    for name in ("home", "state/profiles/web", "workspace", "logs"):
        path = Path(args.state)/name
        assert path.is_dir() and path.stat().st_mode & 0o777 == 0o700
    plist = plistlib.loads((release/"com.mastermind.deepseek.web.plist").read_bytes())
    assert plist["ProgramArguments"] == [args.node, str(release/"launch_attended.mjs")]
    assert plist["WorkingDirectory"] == args.state+"/workspace"
    assert plist["StandardOutPath"] == args.state+"/logs/native.stdout.log"


@pytest.mark.parametrize("change", ["state", "no-release", "no-node", "no-build-node",
                                    "nested-node", "legacy-final-paths", "legacy-no-state"])
def test_mixed_or_incomplete_layout_refuses_before_creating_package(stage_inputs, change):
    args, _ = stage_inputs
    if change == "state": args.state = str(Path(args.release).parent/"unexpected state")
    elif change == "no-release": args.installed_release = None
    elif change == "no-node": args.installed_node = None
    elif change == "no-build-node": args.node = None
    elif change == "nested-node": args.installed_node = args.installed_release+"/node"
    else:
        args.native_layout = False
        if change == "legacy-no-state": args.installed_release = args.installed_node = None
    with pytest.raises(ValueError):
        package.stage(args)
    assert not Path(args.release).exists()
    if args.state: assert not Path(args.state).exists()


@pytest.mark.parametrize("fault", ["absolute-link", "external-link", "hardlink", "fifo"])
def test_native_seal_refuses_nonportable_or_shared_artifacts(tmp_path, fault):
    root = tmp_path.resolve()/"owned candidate"
    root.mkdir()
    payload = root/"file"
    payload.write_bytes(b"immutable")
    if fault == "absolute-link": (root/"bad").symlink_to(payload)
    elif fault == "external-link": (root/"bad").symlink_to("../")
    elif fault == "hardlink": os.link(payload, root/"bad")
    else: os.mkfifo(root/"bad")
    with pytest.raises(ValueError):
        package.seal_native_layout(root)


def test_real_protected_qualification_distinguishes_private_stage_and_final_placement(native_package):
    f = native_package
    release, source = f["release"], f["source_repo"]
    final = release.with_name("enrolled final package")
    config = json.loads((release/"app.json").read_bytes())
    config.update(release=str(final), state=None, state_owner="original-worker",
                  node=str(final.with_name("enrolled Node")), node_sha256="a"*64)
    overlay = [{"insert":[{"id":"mastermind-company",
        "name":str(final/"company_plugin/lib/index.js"), "config":{}}]}]
    (release/"company.patch.yml").write_text(json.dumps(overlay))
    config["company_patch_sha256"] = package.sha(release/"company.patch.yml")
    (release/"app.json").write_text(json.dumps(config))
    manifest = json.loads((release/"package-manifest.json").read_bytes())
    manifest["files"] = package.inventory(release)
    manifest["files"].pop("package-manifest.json")
    (release/"package-manifest.json").write_text(json.dumps(manifest))
    accepted_path = source/package.QUALIFIED_BUILD_PATH
    accepted = json.loads(accepted_path.read_bytes())
    accepted.update(package_manifest_sha256=package.sha(release/"package-manifest.json"),
                    app_config_sha256=package.sha(release/"app.json"))
    accepted_path.write_text(json.dumps(accepted))
    def git(*argv):
        return subprocess.check_output(["git", "-c", "gc.auto=0", "-C", str(source), *argv],
                                       text=True).strip()
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "qualified final coordinates")
    sha = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/master", sha)
    args = dict(release=release, source_repo=source, source_sha=sha)
    qualified = package._qualified_release_source(**args, installation_root=final)
    assert qualified[7]["release"] == str(final) and qualified[7]["state"] is None
    with pytest.raises(ValueError, match="publication binding"):
        package._qualified_release_source(**args)
    release.rename(final)
    qualified = package._qualified_release_source(release=final, source_repo=source, source_sha=sha)
    assert qualified[7]["release"] == str(final)
