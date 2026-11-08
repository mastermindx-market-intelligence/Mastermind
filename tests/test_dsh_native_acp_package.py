"""Real-file custody of the original native ACP layer in the full application."""
import difflib
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from integrations.deepseek_harness.runtime_compat import native_acp_package as package

native = package.native


def git(root, *args):
    return subprocess.check_output(["git", "-c", "gc.auto=0", "-C", str(root), *args], text=True).strip()


def commit(root):
    git(root, "add", ".")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "ACP package fixture")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    donor, inputs = tmp_path / "donor", tmp_path / "inputs"
    donor.mkdir(); inputs.mkdir()
    old, new = b"export const native = 'original';\n", b"export const native = 'correlated';\n"
    names = native.CHANGED | {"packages/acp/acp/src/codec.ts"}
    for name in names:
        path = donor / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(old)
    (donor / "pnpm-lock.yaml").write_text("fixture: original native ACP\n")
    git(donor, "init", "-q", "-b", "master"); pin = commit(donor)
    monkeypatch.setattr(native, "ROOT", inputs); monkeypatch.setattr(native, "PIN", pin)
    patch = "".join(line for name in sorted(native.CHANGED) for line in difflib.unified_diff(
        old.decode().splitlines(True), new.decode().splitlines(True), fromfile="a/"+name, tofile="b/"+name)).encode()
    expected = {"schema": "mastermind.dsh_native_acp_source.v1", "donor_sha": pin,
        "donor_lock_sha256": native.sha(donor / "pnpm-lock.yaml"), "production_armed": False,
        "source_sha256": {name: package.digest(old) for name in names},
        "output_sha256": {name: package.digest(new) for name in native.CHANGED},
        "patch_sha256": package.digest(patch)}
    (inputs / "native-acp-source.json").write_text(json.dumps(expected))
    (inputs / "native-acp-lifecycle.patch").write_bytes(patch)
    release = tmp_path / "release"; release.mkdir()
    shutil.copytree(donor, release / "app", ignore=shutil.ignore_patterns(".git"))
    identity = package.package(release, donor)
    protected = tmp_path / "protected"; protected.mkdir()
    for relative in package.FILES.values():
        target = protected / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((inputs / Path(relative).name).read_bytes())
    git(protected, "init", "-q", "-b", "master"); head = commit(protected)
    config = {package.KEY: identity}
    return donor, release, config, protected, head, expected


def test_full_package_retains_the_exact_native_acp_source_and_receipt(fixture):
    donor, release, config, protected, head, expected = fixture
    package.verify(release, config, config, protected, head)
    assert json.loads((release / "native-acp-receipt.json").read_bytes()) == package.receipt(expected)
    assert git(donor, "status", "--porcelain") == ""
    assert package.qualify_inputs() == expected


@pytest.mark.parametrize("relative", ["packages/acp/acp/src/session.ts", "packages/acp/acp/src/codec.ts"])
def test_changed_native_output_or_unchanged_dependency_is_refused(fixture, relative):
    donor, release, config, protected, head, _ = fixture
    (release / "app" / relative).write_text("unqualified source\n")
    with pytest.raises(ValueError, match="source differs"):
        package.verify(release, config, config, protected, head)


def test_local_receipt_cannot_relabel_protected_acp_inputs(fixture):
    donor, release, config, protected, head, _ = fixture
    file = protected / package.FILES["patch"]; file.write_bytes(file.read_bytes() + b"\n# changed source\n")
    head = commit(protected)
    with pytest.raises(ValueError, match="source refused"):
        package.verify(release, config, config, protected, head)


def test_redirected_native_source_is_refused(fixture, tmp_path):
    donor, release, config, protected, head, _ = fixture
    path = release / "app/packages/acp/acp/src/session.ts"; external = tmp_path / "external.ts"
    external.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(external)
    with pytest.raises(ValueError, match="source differs"):
        package.verify(release, config, config, protected, head)


def test_earlier_qualified_packages_keep_their_original_absence(tmp_path):
    package.verify(tmp_path, {}, {}, tmp_path, "unused")
    with pytest.raises(ValueError, match="protected build"):
        package.verify(tmp_path, {}, {package.KEY: {}}, tmp_path, "unused")
