"""Hermetic contracts for the inert Steward public-edge staging bundle."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from ops.steward_public_edge import stage as subject


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "ops/steward_public_edge/mastermind-steward.service"
CADDY = ROOT / "ops/steward_public_edge/mastermind-steward.caddy"
STAGER = ROOT / "ops/steward_public_edge/stage.py"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", os.fspath(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _fixture_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "steward-stage@example.invalid")
    _git(repo, "config", "user.name", "Steward Stage Fixture")

    for relative, body in (
        ("common/__init__.py", ""),
        ("control_plane/__init__.py", ""),
        ("integrations/__init__.py", ""),
        ("scripts/mastermind_steward_app.py", "print('fixture')\n"),
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    for source, relative in (
        (UNIT, subject.UNIT_TEMPLATE),
        (CADDY, subject.CADDY_TEMPLATE),
    ):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    return (
        repo,
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "rev-parse", "HEAD^{tree}"),
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stage_binds_exact_source_host_paths_and_effect_falsehoods(tmp_path):
    repo, commit, tree = _fixture_repo(tmp_path)
    output = tmp_path / "staged"
    manifest = subject.stage(
        source_repo=repo,
        accepted_commit=commit,
        accepted_tree=tree,
        output_dir=output,
    )

    assert manifest["schema"] == subject.SCHEMA
    assert manifest["status"] == "STAGED_INERT"
    assert manifest["source_commit"] == commit
    assert manifest["source_tree"] == tree
    assert manifest["public_host"] == "mcp.mastermind-x.com"
    assert manifest["resource_url"] == (
        "https://mcp.mastermind-x.com/mcp/steward/v1"
    )
    assert manifest["resource_metadata_url"] == (
        "https://mcp.mastermind-x.com/"
        ".well-known/oauth-protected-resource/mcp/steward/v1"
    )
    for field in (
        "service_effect_applied",
        "proxy_effect_applied",
        "dns_effect_applied",
        "oauth_effect_applied",
        "workspace_effect_applied",
        "provider_effect_applied",
        "production_acceptance_granted",
    ):
        assert manifest[field] is False

    unit = (output / subject.UNIT_NAME).read_text(encoding="utf-8")
    assert "@EXPECTED_COMMIT@" not in unit
    assert f"/opt/mastermind-steward/releases/{commit}" in unit
    assert "User=mastermind-steward" in unit
    assert "--host 127.0.0.1 --port 8766" in unit
    assert "EnvironmentFile=" not in unit
    assert "User=root" not in unit

    caddy = (output / subject.CADDY_NAME).read_text(encoding="utf-8")
    assert "@PUBLIC_HOST@" not in caddy
    assert caddy.count("mcp.mastermind-x.com") == 3
    assert caddy.count("reverse_proxy 127.0.0.1:8766") == 2
    assert "tls internal" not in caddy
    assert "control.mastermind-x.com" not in caddy
    assert "forward_auth" not in caddy
    assert "path /mcp/*" not in caddy

    stored = json.loads((output / subject.MANIFEST_NAME).read_text())
    assert stored["source_commit"] == commit
    assert stored["archive"]["sha256"] == _sha(output / subject.ARCHIVE_NAME)
    assert stored["unit"]["sha256"] == _sha(output / subject.UNIT_NAME)
    assert stored["caddy"]["sha256"] == _sha(output / subject.CADDY_NAME)
    assert manifest["manifest_sha256"] == _sha(output / subject.MANIFEST_NAME)

    with tarfile.open(output / subject.ARCHIVE_NAME, mode="r:") as archive:
        names = set(archive.getnames())
    assert "common/__init__.py" in names
    assert "control_plane/__init__.py" in names
    assert "integrations/__init__.py" in names
    assert "scripts/mastermind_steward_app.py" in names
    assert not any(name.startswith(".git/") for name in names)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("dirty", "SOURCE_DIRTY"),
        ("commit", "SOURCE_COMMIT_MISMATCH"),
        ("tree", "SOURCE_TREE_MISMATCH"),
    ],
)
def test_stage_refuses_source_identity_drift_without_output(tmp_path, mutation, code):
    repo, commit, tree = _fixture_repo(tmp_path)
    output = tmp_path / "staged"
    if mutation == "dirty":
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    elif mutation == "commit":
        commit = "c" * 40
    else:
        tree = "d" * 40

    with pytest.raises(subject.StageError, match=code):
        subject.stage(
            source_repo=repo,
            accepted_commit=commit,
            accepted_tree=tree,
            output_dir=output,
        )
    assert not output.exists()


def test_stage_refuses_existing_or_source_overlapping_output(tmp_path):
    repo, commit, tree = _fixture_repo(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()

    with pytest.raises(subject.StageError, match="OUTPUT_PATH_REFUSED"):
        subject.stage(
            source_repo=repo,
            accepted_commit=commit,
            accepted_tree=tree,
            output_dir=existing,
        )
    with pytest.raises(subject.StageError, match="OUTPUT_PATH_REFUSED"):
        subject.stage(
            source_repo=repo,
            accepted_commit=commit,
            accepted_tree=tree,
            output_dir=repo / "stage",
        )


def test_stage_refuses_symlink_output_parent(tmp_path):
    repo, commit, tree = _fixture_repo(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(subject.StageError, match="OUTPUT_PATH_REFUSED"):
        subject.stage(
            source_repo=repo,
            accepted_commit=commit,
            accepted_tree=tree,
            output_dir=link / "staged",
        )
    assert not (real / "staged").exists()


def test_archive_member_allowance_is_root_and_ancestor_scoped():
    assert subject._archive_member_allowed("common", is_directory=True)
    assert subject._archive_member_allowed("common/module.py", is_directory=False)
    assert subject._archive_member_allowed("scripts", is_directory=True)
    assert subject._archive_member_allowed(
        "scripts/mastermind_steward_app.py", is_directory=False,
    )
    assert not subject._archive_member_allowed("scripts", is_directory=False)
    assert not subject._archive_member_allowed("scripts/unrelated.py", is_directory=False)
    assert not subject._archive_member_allowed("script", is_directory=True)
    assert not subject._archive_member_allowed("../scripts", is_directory=True)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace("User=mastermind-steward", "User=root"),
        lambda text: text.replace("--host 127.0.0.1", "--host 0.0.0.0"),
        lambda text: text + "\nEnvironmentFile=/tmp/foreign\n",
    ],
)
def test_unit_renderer_refuses_privilege_or_bind_widening(mutation):
    template = UNIT.read_text(encoding="utf-8")
    with pytest.raises(subject.StageError, match="UNIT_TEMPLATE_INVALID"):
        subject._render_unit(mutation(template), "a" * 40)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace(
            "path /mcp/steward/v1", "path /mcp/*"
        ),
        lambda text: text.replace(
            "@PUBLIC_HOST@", "control.mastermind-x.com"
        ),
        lambda text: text.replace(
            "reverse_proxy 127.0.0.1:8766", "reverse_proxy 0.0.0.0:8766"
        ),
    ],
)
def test_caddy_renderer_refuses_route_or_host_widening(mutation):
    template = CADDY.read_text(encoding="utf-8")
    with pytest.raises(subject.StageError, match="CADDY_TEMPLATE_INVALID"):
        subject._render_caddy(mutation(template))


@pytest.mark.parametrize("directive", [
    "tls internal",
    "tls /tmp/cert.pem /tmp/key.pem",
    "tls {\n\t\ton_demand\n\t}",
    '"tls" internal',
    "`tls` internal",
])
def test_caddy_renderer_requires_automatic_public_tls(directive):
    template = CADDY.read_text(encoding="utf-8").replace("\n\ttls internal", "")
    subject._render_caddy(template)
    mutated = template.replace("\n}", f"\n\t{directive}\n}}")
    with pytest.raises(subject.StageError, match="CADDY_TEMPLATE_INVALID"):
        subject._render_caddy(mutated)


@pytest.mark.parametrize("mutation", [
    lambda text: text + "# harmless-looking drift\n",
    lambda text: text.replace('Cache-Control "private, no-store"',
                              'Cache-Control "private, no-store"\n\t\t# drift'),
])
def test_caddy_renderer_refuses_noncanonical_template_drift(mutation):
    with pytest.raises(subject.StageError, match="CADDY_TEMPLATE_INVALID"):
        subject._render_caddy(mutation(CADDY.read_text(encoding="utf-8")))


def _published_fixture(tmp_path):
    output = tmp_path / "published"
    output.mkdir(mode=subject.OUTPUT_DIR_MODE)
    expected = {}
    for name, content in (
        (subject.ARCHIVE_NAME, b"archive"),
        (subject.UNIT_NAME, b"unit"),
        (subject.CADDY_NAME, b"caddy"),
        (subject.MANIFEST_NAME, b"manifest"),
    ):
        path = output / name
        path.write_bytes(content)
        path.chmod(subject.OUTPUT_FILE_MODE)
        expected[name] = (hashlib.sha256(content).hexdigest(), len(content))
    return output, expected


def test_published_verifier_stops_at_fifth_directory_observation(tmp_path, monkeypatch):
    output, expected = _published_fixture(tmp_path)
    for name in ("unexpected-1", "unexpected-2"):
        (output / name).write_text("extra", encoding="utf-8")
    scandir = os.scandir
    observed = 0

    class GuardedScandir:
        def __init__(self, path):
            self._iterator = scandir(path)

        def __enter__(self):
            self._iterator.__enter__()
            return self

        def __exit__(self, *args):
            return self._iterator.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal observed
            observed += 1
            if observed > len(expected) + 1:
                raise AssertionError("directory verification exceeded its observation bound")
            return next(self._iterator)

    monkeypatch.setattr(subject.os, "scandir", GuardedScandir)
    assert subject._published_bundle_matches(output, expected) is False
    assert observed == len(expected) + 1


def test_published_verifier_refuses_size_mismatch_before_hashing(tmp_path, monkeypatch):
    output, expected = _published_fixture(tmp_path)
    archive = output / subject.ARCHIVE_NAME
    archive.write_bytes(b"archive-overflow")
    archive.chmod(subject.OUTPUT_FILE_MODE)

    sha256_fd_exact = subject._sha256_fd_exact

    def bounded_hash_forbidden(fd, size):
        if os.fstat(fd).st_size != size:
            raise AssertionError("size mismatch must refuse before a hash read")
        return sha256_fd_exact(fd, size)

    monkeypatch.setattr(subject, "_sha256_fd_exact", bounded_hash_forbidden)
    assert subject._published_bundle_matches(output, expected) is False


def test_replace_that_publishes_then_errors_is_effect_unknown(tmp_path, monkeypatch):
    repo, commit, tree = _fixture_repo(tmp_path)
    output = tmp_path / "staged"
    replace = os.replace

    def publish_then_raise(source, destination):
        replace(source, destination)
        raise OSError("ambiguous rename acknowledgement")

    monkeypatch.setattr(subject.os, "replace", publish_then_raise)
    with pytest.raises(subject.StageError, match="PUBLISH_EFFECT_UNKNOWN"):
        subject.stage(
            source_repo=repo,
            accepted_commit=commit,
            accepted_tree=tree,
            output_dir=output,
        )
    assert output.is_dir()
    assert (output / subject.MANIFEST_NAME).is_file()


@pytest.mark.parametrize("failure", ["parent_fsync", "readback", "readback_mismatch"])
def test_postrename_failure_is_effect_unknown_and_preserves_output(
    tmp_path, monkeypatch, failure,
):
    repo, commit, tree = _fixture_repo(tmp_path)
    output = tmp_path / "staged"
    if failure == "parent_fsync":
        fsync = os.fsync

        def fail_parent_fsync(fd):
            if output.exists() and os.fstat(fd).st_ino == output.parent.stat().st_ino:
                raise OSError("parent durability unknown")
            return fsync(fd)

        monkeypatch.setattr(subject.os, "fsync", fail_parent_fsync)
    elif failure == "readback":
        def fail_published_readback(_fd, _size):
            raise OSError("published descriptor read failed")

        monkeypatch.setattr(subject, "_sha256_fd_exact", fail_published_readback)
    else:
        replace = os.replace

        def publish_then_corrupt(source, destination):
            replace(source, destination)
            (Path(destination) / subject.CADDY_NAME).write_text(
                "corrupt after publish\n", encoding="utf-8",
            )

        monkeypatch.setattr(subject.os, "replace", publish_then_corrupt)

    with pytest.raises(subject.StageError, match="PUBLISH_EFFECT_UNKNOWN"):
        subject.stage(
            source_repo=repo,
            accepted_commit=commit,
            accepted_tree=tree,
            output_dir=output,
        )
    assert output.is_dir()
    assert (output / subject.MANIFEST_NAME).is_file()


def test_stager_is_inert_and_templates_do_not_touch_existing_control_room():
    source = STAGER.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    caddy = CADDY.read_text(encoding="utf-8")

    for forbidden in (
        "systemctl",
        "service start",
        "service restart",
        "caddy reload",
        "ssh ",
        "curl ",
        "socket.create_connection",
        "requests.",
        "httpx.",
    ):
        assert forbidden not in source.lower()
    assert "control.mastermind-x.com" not in caddy
    assert "mastermind-control-room" not in unit
    assert "mastermind-control-room" not in caddy
    assert caddy.count("@PUBLIC_HOST@") == 3
    assert "mcp.mastermind-x.com" not in caddy
    assert "tls internal" not in caddy


def test_cli_refusal_is_fixed_and_does_not_echo_paths(tmp_path, capsys):
    repo, commit, tree = _fixture_repo(tmp_path)
    private = repo / "very-private-name"
    private.write_text("dirty\n", encoding="utf-8")
    code = subject.main(
        [
            "--source-repo",
            os.fspath(repo),
            "--accepted-commit",
            commit,
            "--accepted-tree",
            tree,
            "--output-dir",
            os.fspath(tmp_path / "staged"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert json.loads(out) == {
        "schema": subject.SCHEMA,
        "ok": False,
        "error": "SOURCE_DIRTY",
    }
    assert "very-private-name" not in out
