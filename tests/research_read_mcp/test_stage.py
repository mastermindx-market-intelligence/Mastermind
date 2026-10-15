"""Inert staging evidence on synthetic repositories, with no service effects."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from ops.research_read_tunnel import stage

UNIT = Path(stage.__file__).with_name("mastermind-research-read.service").read_text()


def repository(root, files):
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name, raw in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).decode().strip()
    return root, commit, tree


def test_unit_is_closed_hardened_exact_pin():
    rendered = stage.render_unit(UNIT, commit="a" * 40, lock_sha256="b" * 64)
    assert "User=mastermind-research" in rendered
    assert "/releases/" + "a" * 40 in rendered
    assert "/venvs/" + "b" * 64 in rendered
    assert "ReadWritePaths=/var/lib/mastermind-research/audit" in rendered
    for hostile in (UNIT + "\nExecStartPost=/bin/true\n", UNIT.replace("ProtectSystem=strict", "ProtectSystem=false"),
                    UNIT.replace("User=mastermind-research", "User=root"),
                    UNIT.replace("ReadWritePaths=/var/lib/mastermind-research/audit\n", ""),
                    UNIT.replace("ReadWritePaths=/var/lib/mastermind-research/audit", "ReadWritePaths=/var/lib"),
                    UNIT + "\nReadWritePaths=/etc/mastermind\n",
                    UNIT + "\nReadWritePaths=/opt/mastermind-research\n"):
        with pytest.raises(stage.StageRefused):
            stage.render_unit(hostile, commit="a" * 40, lock_sha256="b" * 64)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", ".git/config", ".lane/log", ".env",
                                    "app/.env.production", "engine/*", ":(glob)engine", "-x", "x//y"])
def test_paths_reject_selectors_and_credential_paths(path):
    with pytest.raises(stage.StageRefused):
        stage._paths((path,))


def test_archive_identity_members_dirty_and_limits(tmp_path, monkeypatch):
    root, commit, tree = repository(tmp_path.resolve() / "source", {"engine/code.py": "SYNTHETIC = 1\n"})
    raw, members = stage.source_archive(root, commit, tree, ["engine"])
    assert raw and members == [{"path": "engine/code.py", "bytes": 14,
                               "sha256": hashlib.sha256(b"SYNTHETIC = 1\n").hexdigest()}]
    with pytest.raises(stage.StageRefused):
        stage.source_archive(root, commit, "f" * 40, ["engine"])
    with pytest.raises(stage.StageRefused):
        stage.source_archive(root, commit, tree, ["missing.py"])
    monkeypatch.setattr(stage, "MAX_BYTES", 1)
    with pytest.raises(stage.StageRefused):
        stage.source_archive(root, commit, tree, ["engine"])
    (root / "untracked").write_text("fixture")
    with pytest.raises(stage.StageRefused, match="STAGE_SOURCE_DIRTY"):
        stage.qualify_source(root, commit, tree)


def test_git_symlink_member_refuses(tmp_path):
    root, _commit, _tree = repository(tmp_path.resolve() / "source", {"engine/code.py": "fixture"})
    (root / "engine/link").symlink_to("code.py")
    subprocess.run(["git", "-C", str(root), "add", "engine/link"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "symlinkfixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).decode().strip()
    with pytest.raises(stage.StageRefused, match="STAGE_MEMBER_REFUSED"):
        stage.source_archive(root, commit, tree, ["engine"])


@pytest.mark.parametrize("include_producer", [False, True])
def test_bundle_is_inert_scoped_and_cannot_overwrite(tmp_path, include_producer):
    root = tmp_path.resolve()
    mm, mm_commit, mm_tree = repository(root / "mastermind", {
        "common/__init__.py": "", "control_plane/__init__.py": "", "integrations/__init__.py": "",
        stage.SERVER_PATH: "# synthetic launcher fixture only\n", stage.LOCK_PATH: "# synthetic lock fixture\n",
        stage.UNIT_PATH: UNIT,
        stage.PRODUCER_PATH: "raise AssertionError('STAGING_EXECUTED_PRODUCER')\n",
    })
    macro, macro_commit, macro_tree = repository(root / "macro", {"engine/source.py": "SYNTHETIC = 1\n"})
    kwargs = dict(mastermind_source=mm, mastermind_commit=mm_commit, mastermind_tree=mm_tree,
                  macro_source=macro, macro_commit=macro_commit, macro_tree=macro_tree,
                  macro_roots=["engine"], output=root / "candidate", include_producer=include_producer)
    manifest = stage.prepare_bundle(**kwargs)
    assert (stage.PRODUCER_PATH in {row["path"] for row in manifest["members"]["mastermind"]}) is include_producer
    assert manifest["state"] == "INERT_CANDIDATE"
    assert manifest["macro_import_closure"] == "OWNER_QUALIFICATION_REQUIRED"
    assert json.loads((kwargs["output"] / "manifest.json").read_text()) == manifest
    for file in manifest["files"]:
        path = kwargs["output"] / file["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == file["sha256"]
        assert path.stat().st_mode & 0o777 == 0o600
    assert kwargs["output"].stat().st_mode & 0o777 == 0o700
    with pytest.raises(stage.StageRefused, match="STAGE_OUTPUT_REFUSED"):
        stage.prepare_bundle(**kwargs)


def test_incomplete_launcher_cannot_stage(tmp_path):
    root, commit, tree = repository(tmp_path.resolve() / "source", {"integrations/__init__.py": ""})
    with pytest.raises(stage.StageRefused):
        stage.source_archive(root, commit, tree, stage.MASTERMIND_ROOTS)


@pytest.mark.parametrize("attribute,text", [
    ("export-ignore", "fixture"), ("export-subst", "$Format:%H$"),
])
def test_archive_cannot_silently_drop_or_substitute_source_bytes(tmp_path, attribute, text):
    root, commit, tree = repository(tmp_path.resolve() / "source", {
        "engine/code.py": text, ".gitattributes": f"engine/code.py {attribute}\n",
    })
    with pytest.raises(stage.StageRefused, match="STAGE_ARCHIVE_IDENTITY_REFUSED"):
        stage.source_archive(root, commit, tree, ["engine"])


@pytest.mark.parametrize("option", ["true", 1, None])
def test_producer_packaging_option_cannot_coerce_truthy_inputs(tmp_path, option):
    with pytest.raises(stage.StageRefused, match="STAGE_PRODUCER_OPTION_REFUSED"):
        stage.prepare_bundle(mastermind_source=tmp_path, mastermind_commit="a" * 40,
            mastermind_tree="b" * 40, macro_source=tmp_path, macro_commit="c" * 40,
            macro_tree="d" * 40, macro_roots=["engine"], output=tmp_path / "candidate",
            include_producer=option)
    assert not (tmp_path / "candidate").exists()
