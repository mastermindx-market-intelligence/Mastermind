"""Real Git/namespace/publication checks with explicit root/ACL metadata doubles.

The small Git commit is a fixture, not the production Hermes identity. The
production contract pins are tested separately. No host/runtime proof is implied.
"""
from contextlib import ExitStack
from dataclasses import replace
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from ops.executive_os import native_gateway_sources as source
from ops.executive_os import release_manifest as manifest
from integrations.hermes_qualification.computer_env_guard import qualify as guard
from integrations.hermes_qualification.diagnostic_privacy import qualify as privacy_guard
from integrations.hermes_qualification.workspace_oauth_privacy import qualify as workspace_guard
from tests.test_hermes_diagnostic_privacy import privacy_sources
from integrations.hermes_runtime import install as installer
from integrations.hermes_runtime.errors import RuntimeRefusal


def git(root, *args):
    # Optional locks do not disable detached maintenance in disposable Git repos.
    # Keep the fixture namespace stable through the complete metadata walk.
    result = subprocess.run(["git", "-c", "maintenance.auto=false", "-c", "gc.auto=0",
                             "-C", str(root), *args], check=True, capture_output=True,
                            env={"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1",
                                 "GIT_CONFIG_GLOBAL": os.devnull,
                                 "GIT_OPTIONAL_LOCKS": "0"}, text=True)
    return result.stdout.strip()


@pytest.fixture(params=["computer_env_guard", "diagnostic_privacy", "workspace_oauth_privacy"])
def world(tmp_path, monkeypatch, request):
    kind = request.param
    patch, postimages, _ = source._derivation_policy(kind)
    selected_guard = {source.DERIVATION_KIND: guard, source.PRIVACY_DERIVATION_KIND: privacy_guard,
                      source.WORKSPACE_OAUTH_DERIVATION_KIND: workspace_guard}[kind]
    base = tmp_path / "base"
    base.mkdir(mode=0o755)
    git(base, "init", "--quiet")
    originals = {name: (guard.ROOT / "fixtures" / (name + ".source")).read_bytes()
                 for name in source.DERIVATION_POSTIMAGES}
    originals.update(privacy_sources("upstream"))
    provenance = json.loads((workspace_guard.ROOT / "fixtures/provenance.json").read_bytes())
    originals.update({name: (workspace_guard.ROOT / "fixtures" / provenance["files"][name]["fixture"]).read_bytes()
                      for name in workspace_guard.PATHS})
    for name, data in originals.items():
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (base / "plain.txt").write_text("exact base\n", encoding="utf-8")
    (base / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
    (base / "run.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (base / "run.sh").chmod(0o755)
    git(base, "add", ".")
    git(base, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--quiet", "-m", "fixture base")
    sha = git(base, "rev-parse", "HEAD")
    # The host may use umask 077. This disposable fixture explicitly selects
    # the readable immutable-root modes required by the production qualifier.
    base.chmod(0o755)
    for item in base.rglob("*"):
        item.chmod(0o755 if item.is_dir() or item.stat().st_mode & 0o111 else 0o644)
    monkeypatch.setattr(source, "DERIVATION_BASE", sha)
    destination = tmp_path / "derived"
    ancestors = {(p.stat().st_dev, p.stat().st_ino) for p in base.parents}
    real_os = os
    wrong_owner = set()
    def mapped(info):
        fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        fields.update(st_uid=1 if (info.st_dev, info.st_ino) in wrong_owner else 0, st_gid=0)
        if (info.st_dev, info.st_ino) in ancestors:
            fields["st_mode"] |= 0o005
        return SimpleNamespace(**fields)
    class OS:
        def __getattr__(self, name):
            return getattr(real_os, name)
        def fstat(self, fd):
            return mapped(real_os.fstat(fd))
        def stat(self, *args, **kwargs):
            return mapped(real_os.stat(*args, **kwargs))
        def getuid(self):
            return 0
        def geteuid(self):
            return 0
        def fchown(self, fd, uid, gid):
            assert uid == gid == 0
        def chown(self, path, uid, gid):
            assert uid == gid == 0
    monkeypatch.setattr(source, "os", OS())
    fds = []
    class Owner:
        root = Path(__file__).resolve().parents[1]
        def hold(self, path, *, directory=False):
            fd = real_os.open(path, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0))
            fds.append(fd)
            return fd
        def source(self, relative):
            return (self.root / relative).read_bytes()
        def read(self, path, maximum):
            return real_os.pread(self.hold(path), maximum + 1, 0)
        def check(self):
            pass  # explicit custody double; real namespace/hash logic is used
    owner, acl = Owner(), lambda *args: None
    recipe = {"vendor_root": str(destination), "import_roots": [str(destination)],
              "dependency_inventory": {"path": str(tmp_path / "inventory.json"), "sha256": "", "size": 0},
              "vendor_derivation": {"kind": kind, "base_sha": sha,
                  "patch_sha256": patch, "source_root": str(base)}}
    def freeze():
        document = json.loads(source.candidate_inventory(owner, [str(base)], acl))
        document["roots"][0]["path"] = str(destination)
        patched = selected_guard.prepare_sources({name: (base / name).read_bytes() for name in postimages})
        for row in document["roots"][0]["entries"]:
            if row["path"] in patched:
                data = patched[row["path"]]
                row.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        frozen = (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        recipe["dependency_inventory"].update(size=len(frozen), sha256=hashlib.sha256(frozen).hexdigest())
        return frozen
    frozen = freeze()
    yield SimpleNamespace(base=base, destination=destination, recipe=recipe, owner=owner,
                          acl=acl, sha=sha, wrong_owner=wrong_owner, freeze=freeze, frozen=frozen,
                          kind=kind, patch=patch, postimages=postimages, guard=selected_guard)
    for fd in fds:
        real_os.close(fd)


def test_materialize_exact_repair_preserves_git_base_and_freezes_full_namespace(world):
    original = source.candidate_inventory(world.owner, [str(world.base)], world.acl)
    receipt = source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    source.prepare_inventory(world.owner, world.recipe, world.acl)
    assert git(world.destination, "rev-parse", "HEAD") == world.sha
    assert source.candidate_inventory(world.owner, [str(world.base)], world.acl) == original
    assert Path(world.recipe["dependency_inventory"]["path"]).read_bytes() == world.frozen
    assert receipt["postimages"] == world.postimages
    assert receipt["kind"] == world.kind
    assert receipt["base_sha"] == world.sha
    # Git diff can refresh a caller-owned fixture index. The real runtime role
    # cannot write the root-owned artifact; use the actual immutable closure to
    # verify complete bytes here, rather than introducing a second Git writer.
    assert (world.destination / "plain.txt").read_bytes() == (world.base / "plain.txt").read_bytes()
    closure = source.NativeSourceClosure(world.owner, world.recipe, world.acl)
    closure.check()
    closure.close()


def test_matching_destination_is_read_only_adoption(world):
    first = source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    before = {str(p): (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
              for p in world.destination.rglob("*") if p.is_file()}
    second = source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert first == second
    assert before == {str(p): (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
                      for p in world.destination.rglob("*") if p.is_file()}


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_real_git_index_flags_cannot_hide_changed_bytes(world, flag):
    git(world.base, "update-index", flag, "plain.txt")
    (world.base / "plain.txt").write_text("hidden drift\n")
    assert git(world.base, "status", "--porcelain=v1") == ""
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert not world.destination.exists()


@pytest.mark.parametrize("mutation", ["ignored", "empty_directory", "executable", "symlink", "hardlink", "wrong_owner"])
def test_base_source_must_match_complete_custody_and_git_membership(world, mutation):
    if mutation == "ignored":
        (world.base / "ignored.tmp").write_text("untracked")
        assert git(world.base, "status", "--porcelain=v1") == ""
    elif mutation == "empty_directory":
        (world.base / "empty").mkdir()
    elif mutation == "executable":
        (world.base / "run.sh").chmod(0o644)
    elif mutation == "symlink":
        (world.base / "extra").symlink_to(world.base / "plain.txt")
    elif mutation == "hardlink":
        os.link(world.base / "plain.txt", world.base / "extra")
    else:
        info = (world.base / "plain.txt").stat()
        world.wrong_owner.add((info.st_dev, info.st_ino))
    with pytest.raises((source.NativeSourceRefusal, OSError)):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert not world.destination.exists()


def test_wrong_frozen_inventory_prevents_any_publication(world):
    world.recipe["dependency_inventory"]["sha256"] = "0" * 64
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert not world.destination.exists()


@pytest.mark.parametrize("name", ["plain.txt", "patched", ".git/HEAD"])
def test_existing_wrong_artifact_is_never_repaired(world, name):
    source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    target = world.destination / (next(iter(world.postimages)) if name == "patched" else name)
    target.write_text("wrong\n")
    identity = (target.stat().st_ino, target.stat().st_mtime_ns)
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert target.read_text() == "wrong\n"
    assert (target.stat().st_ino, target.stat().st_mtime_ns) == identity


def test_real_no_replace_rename_cannot_replace_even_an_empty_racing_destination(world, monkeypatch):
    publish = source._publish_derivation
    observed = []
    def race(parent, temporary, destination):
        world.destination.mkdir()
        observed.append(world.destination.stat().st_ino)
        return publish(parent, temporary, destination)
    monkeypatch.setattr(source, "_publish_derivation", race)
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert world.destination.stat().st_ino == observed[0]
    assert list(world.destination.iterdir()) == []
    assert not list(world.destination.parent.glob(".hermes-derivation-*"))


def test_lost_publication_ack_retains_original_artifact_for_exact_reconciliation(world, monkeypatch):
    publish = source._publish_derivation
    def lost_ack(*args):
        assert publish(*args) is True
        raise OSError(errno.EIO, "lost acknowledgement")
    monkeypatch.setattr(source, "_publish_derivation", lost_ack)
    with pytest.raises(OSError):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    before = world.destination.stat().st_ino
    # Reconciliation reads the original destination; it must not call publish.
    receipt = source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert receipt["vendor_root"] == str(world.destination)
    assert world.destination.stat().st_ino == before


def test_adoption_also_binds_git_metadata_to_frozen_inventory(world):
    source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    path = world.destination / ".git/info/exclude"
    path.write_text("new unselected metadata\n")
    before = path.stat().st_ino
    with pytest.raises(source.NativeSourceRefusal):
        source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    assert path.stat().st_ino == before and path.read_text() == "new unselected metadata\n"


def test_installer_uses_real_frozen_closure_and_original_recipe(world, monkeypatch):
    source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    source.prepare_inventory(world.owner, world.recipe, world.acl)
    profile = SimpleNamespace(role="mmsecretary", state_dir=world.base.parent / "state")
    row = {"role": profile.role, "state_dir": str(profile.state_dir), "native_gateway": world.recipe}
    world.owner.hermes_runtime_input = lambda: {"roles": [row]}
    world.owner.close = lambda: None
    monkeypatch.setattr(manifest, "_HeldReleaseSources", lambda root: world.owner)
    monkeypatch.setattr(manifest, "_linux_source_acl", world.acl)
    with ExitStack() as lifetime:
        receipt, check = installer._qualify_native_derivation(world.recipe, profile, lifetime)
        assert receipt["patch_sha256"] == world.patch
        check()
        (world.destination / "plain.txt").write_text("changed after qualification\n")
        with pytest.raises(source.NativeSourceRefusal):
            check()
    row["native_gateway"] = {**world.recipe, "different": True}
    with ExitStack() as lifetime, pytest.raises(RuntimeRefusal, match="RECIPE_MISMATCH"):
        installer._qualify_native_derivation(world.recipe, profile, lifetime)


@pytest.mark.parametrize("kind", ["computer_env_guard", "diagnostic_privacy", "workspace_oauth_privacy"])
def test_actual_installed_receipt_and_launch_compare_explicit_derivation(tmp_path, kind):
    from integrations.hermes_harness.stack import compose_profile
    state = tmp_path / "state"
    profile = replace(compose_profile("mmsecretary", state_dir=state,
                      secrets_file=tmp_path / "keys.env"),
                      gateway_backend="native-session-authority",
                      tool_allowlist=frozenset({"clarify"}),
                      native_provider_id="byteplus-modelark.glm-5.3-flash")
    release = state / "releases/1"
    release.mkdir(parents=True)
    launcher = installer.repo_root() / "integrations/hermes_runtime/native/hermes"
    native = native_recipe()
    native["vendor_derivation"] = derivation(kind)
    patch, postimages, _ = source._derivation_policy(kind)
    proof = {"kind": kind, "base_sha": derivation(kind)["base_sha"],
             "patch_sha256": patch, "postimages": dict(postimages),
             "vendor_root": native["vendor_root"], "license_sha256": "c" * 64}
    installer._write_release(profile, release, launcher, True,
                             native_installation=native, native_derivation=proof)
    (state / "current").symlink_to("releases/1")
    receipt = json.loads((release / "install-receipt.json").read_text())
    assert receipt["native_vendor_derivation"] == proof
    fake = SimpleNamespace(recipe=native, derivation=proof, launcher=launcher,
        launcher_bytes=launcher.read_bytes(),
        adapter_bytes=(installer.repo_root() / "integrations/hermes_runtime/native_gateway_entry.py").read_bytes(),
        row={"role": profile.role, "state_dir": str(state), "uid": os.getuid(), "gid": os.getgid()},
        check=lambda: None)
    manifest._NativeGatewayLaunch.qualify(fake, profile, state / "current/bin/hermes")
    fake.derivation = {**proof, "patch_sha256": "0" * 64}
    with pytest.raises(RuntimeRefusal, match="RECEIPT_MISMATCH"):
        manifest._NativeGatewayLaunch.qualify(fake, profile, state / "current/bin/hermes")


def test_derived_receipt_cannot_be_written_without_qualification(tmp_path):
    from integrations.hermes_harness.stack import compose_profile
    profile = replace(compose_profile("mmsecretary", state_dir=tmp_path / "state",
                      secrets_file=tmp_path / "keys.env"), tool_allowlist=frozenset({"clarify"}),
                      native_provider_id="byteplus-modelark.glm-5.3-flash")
    native = native_recipe()
    native["vendor_derivation"] = derivation()
    release = tmp_path / "unselected-release"
    release.mkdir()
    with pytest.raises(RuntimeRefusal, match="DERIVATION_PROOF_REQUIRED"):
        installer._write_release(profile, release,
            installer.repo_root() / "integrations/hermes_runtime/native/hermes", True,
            native_installation=native)
    assert not (release / "install-receipt.json").exists()


def native_recipe():
    return {"schema": "mastermind.hermes_native_gateway_installation/v1",
            "python": {"path": "/opt/python/bin/python", "real_path": "/opt/python/bin/python", "sha256": "a" * 64},
            "startup": {"profile": manifest.HERMES_RUNTIME_PROFILE,
                        **{key: "/opt/python" for key in ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix")}},
            "vendor_root": "/opt/hermes/derived", "import_roots": ["/opt/hermes/derived"],
            "dependency_inventory": {"path": "/opt/hermes/inventory.json", "sha256": "b" * 64, "size": 100}}


def derivation(kind="computer_env_guard"):
    patch, _, _ = source._derivation_policy(kind)
    return {"kind": kind, "base_sha": "1c0cd667746d3395fe9e1b6c74f8f85952486f18",
            "patch_sha256": patch,
            "source_root": "/opt/hermes/base"}


def test_closed_recipe_preserves_pristine_path_and_detaches_named_repair():
    recipe = native_recipe()
    assert manifest._hermes_native_gateway(recipe) == recipe
    recipe["vendor_derivation"] = derivation()
    qualified = manifest._hermes_native_gateway(recipe)
    recipe["vendor_derivation"]["source_root"] = "/changed"
    assert qualified["vendor_derivation"] == derivation()


@pytest.mark.parametrize("key,value", [("kind", "general_patch"), ("base_sha", "0" * 40),
    ("patch_sha256", "0" * 64), ("source_root", "/opt/hermes/derived"),
    ("source_root", "/opt/hermes"), ("source_root", "/opt/hermes/derived/nested"),
    ("source_root", "../base"), ("allow_dirty", True)])
def test_no_general_dirty_or_patch_escape_in_recipe(key, value):
    recipe = native_recipe()
    recipe["vendor_derivation"] = {**derivation(), key: value}
    with pytest.raises(manifest.ReleaseManifestError):
        manifest._hermes_native_gateway(recipe)


def test_null_derivation_is_not_an_absent_selection():
    recipe = native_recipe()
    recipe["vendor_derivation"] = None
    with pytest.raises(manifest.ReleaseManifestError):
        manifest._hermes_native_gateway(recipe)


def test_native_rollback_refuses_different_recipe_before_switching(tmp_path):
    state = tmp_path / "state"
    launcher = tmp_path / "hermes"
    launcher.write_text("inert")
    for release in ("1", "2"):
        folder = state / "releases" / release
        (folder / "bin").mkdir(parents=True)
        (folder / "bin/hermes").symlink_to(launcher)
        (folder / "install-receipt.json").write_text(json.dumps({"native_gateway": {"version": release}}))
    (state / "current").symlink_to("releases/2")
    with pytest.raises(RuntimeRefusal, match="MATCHING_RELEASE_RECIPE"):
        installer.rollback(state)
    assert os.readlink(state / "current") == "releases/2"


def test_matching_native_tuple_can_roll_back_without_claiming_service_restart(tmp_path):
    state = tmp_path / "state"
    launcher = tmp_path / "hermes"
    launcher.write_text("inert")
    for release in ("1", "2"):
        folder = state / "releases" / release
        (folder / "bin").mkdir(parents=True)
        (folder / "bin/hermes").symlink_to(launcher)
        (folder / "install-receipt.json").write_text(json.dumps({"native_gateway": native_recipe()}))
    (state / "current").symlink_to("releases/2")
    (state / "install-manifest.json").write_text(json.dumps({"current_release": "2"}))
    result = installer.rollback(state)
    assert result["release"] == "1" and "service_started" not in result
    assert os.readlink(state / "current") == "releases/1"


@pytest.mark.parametrize("change", ["cross_variant", "combined"])
def test_selected_derivation_refuses_other_or_combined_postimages(world, change):
    source.prepare_vendor_derivation(world.owner, world.recipe, world.acl)
    other = "diagnostic_privacy" if world.kind == "computer_env_guard" else "computer_env_guard"
    patch, postimages, _ = source._derivation_policy(other)
    if change == "cross_variant":
        world.recipe["vendor_derivation"].update(kind=other, patch_sha256=patch)
    else:
        qualifier = privacy_guard if other == "diagnostic_privacy" else guard
        patched = qualifier.prepare_sources({name: (world.base / name).read_bytes() for name in postimages})
        for name, data in patched.items():
            (world.destination / name).write_bytes(data)
    with pytest.raises(source.NativeSourceRefusal):
        source.verify_vendor_derivation(world.owner, world.recipe, world.acl)


@pytest.mark.parametrize("kind", ["computer_env_guard", "diagnostic_privacy", "workspace_oauth_privacy"])
def test_closed_recipe_admits_only_matching_fixed_patch(kind):
    native = native_recipe()
    native["vendor_derivation"] = derivation(kind)
    assert manifest._hermes_native_gateway(native) == native
    other = "diagnostic_privacy" if kind == "computer_env_guard" else "computer_env_guard"
    native["vendor_derivation"]["patch_sha256"] = derivation(other)["patch_sha256"]
    with pytest.raises(manifest.ReleaseManifestError):
        manifest._hermes_native_gateway(native)


def test_rollback_refuses_variant_drift_before_changing_current(tmp_path):
    state = tmp_path / "state"
    for number, kind in (("1", "computer_env_guard"), ("2", "diagnostic_privacy")):
        folder = state / "releases" / number
        folder.mkdir(parents=True)
        native = native_recipe()
        native["vendor_derivation"] = derivation(kind)
        (folder / "install-receipt.json").write_text(json.dumps({"native_gateway": native}))
    (state / "current").symlink_to("releases/2")
    with pytest.raises(RuntimeRefusal, match="MATCHING_RELEASE_RECIPE"):
        installer.rollback(state)
    assert os.readlink(state / "current") == "releases/2"
