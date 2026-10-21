"""Independent candidate review: consumer effect truth and exact workspace identity."""
import json
from pathlib import Path
import subprocess
import pytest

from scripts import install_mini_worktree_host as installer
from scripts import mini_worktree as mw
from test_mini_worktree import _fixture


@pytest.fixture(autouse=True)
def _macro_private_remote(monkeypatch):
    monkeypatch.setenv(
        installer.MACRO_REMOTE_ENV,
        "git@github.com:mastermindx-market-intelligence/macro.git",
    )
    monkeypatch.setenv(
        installer.MACRO_SSH_COMMAND_ENV,
        "ssh -i /owner/private/macro-readonly -o IdentitiesOnly=yes",
    )


def test_installer_preserves_unknown_bootstrap_effect(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    (source / "scripts" / "mini_worktree.py").write_text("# candidate helper\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setattr(installer, "_git_sha", lambda _: "a" * 40)

    def failed_bootstrap(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=2,
            stdout="",
            stderr=json.dumps({
                "schema_version": "mastermind.mini_worktree/v1",
                "action": "bootstrap",
                "effect": "EFFECT_UNKNOWN",
                "reconciliation_required": True,
                "error": "injected partial bootstrap",
            }),
        )

    monkeypatch.setattr(installer.subprocess, "run", failed_bootstrap)
    rc = installer.main([
        "--source-root", str(source),
        "--home", str(home),
        "--bootstrap",
    ])
    assert rc == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["effect"] == "EFFECT_UNKNOWN", payload
    assert payload["reconciliation_required"] is True, payload


def test_exact_session_resume_rejects_symlink_substitution(tmp_path):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "alias", "audit")
    path = Path(first["workspace"])
    outside = tmp_path / "outside-preserved-workspace"
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(mw.MiniWorktreeError, match="symlink|identity|unavailable|reconcile"):
        mw.create_worktree(cfg, "fixture", "alias", "audit")


def test_census_symlink_substitution_cannot_be_ready_or_disappear(tmp_path):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "alias-census", "audit")
    path = Path(first["workspace"])
    outside = tmp_path / "outside-preserved-census"
    path.rename(outside)
    path.symlink_to(outside, target_is_directory=True)

    try:
        repo = mw.census(cfg)["repositories"]["fixture"]
    except mw.MiniWorktreeError:
        return
    assert repo["state"] == "PARTIAL", repo
    assert len(repo["worktrees"]) == 1, repo
    row = repo["worktrees"][0]
    assert row["dirty"] is None, row
    assert row["observation_state"] == "UNKNOWN", row


def test_foreign_session_identity_still_refuses_resume(tmp_path):
    cfg, _ = _fixture(tmp_path)
    mw.create_worktree(cfg, "fixture", "foreign", "audit-a")
    with pytest.raises(mw.MiniWorktreeError, match="identity"):
        mw.create_worktree(cfg, "fixture", "foreign", "audit-b")


@pytest.mark.parametrize(
    "bootstrap_stdout",
    [
        "not-json",
        json.dumps({
            "schema_version": "wrong",
            "action": "bootstrap",
            "effect": "APPLIED",
            "receipt": [],
        }),
    ],
)
def test_installer_rejects_unqualified_success_receipt_as_unknown(
    tmp_path, monkeypatch, capsys, bootstrap_stdout
):
    source = tmp_path / "source-schema"
    (source / "scripts").mkdir(parents=True)
    (source / "scripts" / "mini_worktree.py").write_text("# candidate helper\n", encoding="utf-8")
    home = tmp_path / "home-schema"
    home.mkdir()
    monkeypatch.setattr(installer, "_git_sha", lambda _: "b" * 40)

    def unqualified_success(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=bootstrap_stdout,
            stderr="",
        )

    monkeypatch.setattr(installer.subprocess, "run", unqualified_success)
    rc = installer.main([
        "--source-root", str(source),
        "--home", str(home),
        "--bootstrap",
    ])
    assert rc == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["effect"] == "EFFECT_UNKNOWN", payload
    assert payload["reconciliation_required"] is True, payload
