from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pytest

from control_plane.session_truth import semantic_projection


MODULE = "scripts.session_truth_receipt"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "session_truth"
MASTER = "mastermindx-market-intelligence/Mastermind"


def _cli():
    try:
        return importlib.import_module(MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != MODULE:
            raise

        class Missing:
            @staticmethod
            def main(*_args, **_kwargs):
                raise NotImplementedError("session_truth_receipt CLI not implemented")

        return Missing()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", os.fspath(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_git(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@invalid.local")
    _git(repo, "config", "user.name", "Session Truth CLI Tests")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _skillpack_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "Mastermind"
    _init_git(repo)
    index = repo / "docs" / "sol_skills" / "INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text(
        "---\n"
        "schema: mastermind.sol_skillpack.v1\n"
        "skillpack_version: 1.0.0\n"
        "minimum_bootstrap_major: 1\n"
        "skill: index\n"
        "---\n\n# Test Skillpack\n",
        encoding="utf-8",
    )
    return repo, _commit_all(repo, "protected")


def _macro_repo(tmp_path: Path, *, status_delay: float = 0.0) -> Path:
    macro = tmp_path / "macro"
    _init_git(macro)
    ws = macro / "agentos" / "workstreams" / "WS-CHAIRMAN-CONTROL-ROOM.md"
    ws.parent.mkdir(parents=True)
    ws.write_text("# fixture\n", encoding="utf-8")
    script = macro / "scripts" / "agentos.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[1]
args = sys.argv[1:]
status_delay = STATUS_DELAY

if args and args[0] == "status" and "--dry-run" in args:
    time.sleep(status_delay)
    payload = {
        "schema": "agent_os_state.v1",
        "generated_at": "2026-08-27T08:00:00Z",
        "workstreams": [
            {
                "key": "CHAIRMAN-CONTROL-ROOM",
                "status": "active",
                "repos": ["Mastermind"],
                "next_action": "prove session truth",
                "updated": "2026-08-27",
                "waves": {"in_progress": 1},
                "wave_detail": [],
                "prs": [],
                "warnings": [],
                "source": "agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md"
            }
        ],
        "warnings": []
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

if args and args[0] == "compile-context" and "--workstream" in args:
    value = args[args.index("--workstream") + 1]
    payload = {
        "schema": "context_bundle.v1",
        "target": {"workstream": "WS:" + value, "resolution": "explicit"},
        "sections": [],
        "excluded": [],
        "omitted_due_to_budget": [],
        "degraded": [],
        "generated_at": "2026-08-27T08:00:00Z"
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

(root / ".ILLEGAL_WRITE").write_text(repr(args), encoding="utf-8")
raise SystemExit(7)
""".replace("STATUS_DELAY", repr(status_delay)),
        encoding="utf-8",
    )
    _commit_all(macro, "fixture")
    return macro


def _snapshot_dir(tmp_path: Path) -> Path:
    root = tmp_path / "snapshots"
    root.mkdir()
    for name in (
        "github_minimal.json",
        "linear_minimal.json",
        "slack_minimal.json",
        "executive_unavailable.json",
        "identity_minimal.json",
    ):
        shutil.copyfile(FIXTURES / name, root / name)
    return root


def _tree_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _argv(
    snapshots: Path,
    macro: Path,
    protected_sha: str,
    *,
    now: str = "2026-08-27T05:00:00Z",
) -> list[str]:
    return [
        "--workstream",
        "WS:CHAIRMAN-CONTROL-ROOM",
        "--repository",
        MASTER,
        "--github-snapshot",
        os.fspath(snapshots / "github_minimal.json"),
        "--linear-snapshot",
        os.fspath(snapshots / "linear_minimal.json"),
        "--slack-snapshot",
        os.fspath(snapshots / "slack_minimal.json"),
        "--executive-snapshot",
        os.fspath(snapshots / "executive_unavailable.json"),
        "--identity-snapshot",
        os.fspath(snapshots / "identity_minimal.json"),
        "--macro-root",
        os.fspath(macro),
        "--protected-skillpack-sha",
        protected_sha,
        "--now",
        now,
        "--json",
    ]


def _run(cli, argv: list[str], repo: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(
        argv,
        repo_root=repo,
        environ={},
        stdout=stdout,
        stderr=stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_literal_fixture_invocation_emits_degraded_json(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)

    code, stdout, stderr = _run(cli, _argv(snapshots, macro, protected), repo)

    assert code == 0
    assert stderr == ""
    receipt = json.loads(stdout)
    assert receipt["schema"] == "mastermind.session_truth_receipt.v1"
    assert receipt["scope"] == {
        "workstreams": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "linear": [],
        "repositories": [MASTER],
        "operation_key": None,
        "requires_executive": False,
    }
    assert receipt["skillpack"]["sha"] == protected
    assert receipt["observations"]["executive"] == {
        "available": False,
        "reason": "EXECUTIVE_READ_PATH_UNAVAILABLE",
    }
    # The current estate carries no Macro owner digest, so an Agent OS-scoped request
    # is truthfully blocked rather than modification-capable (amendment §3.2).
    assert receipt["admission"]["mode"] == "DIALOGUE_ONLY"
    assert receipt["admission"]["modification_safe"] is False
    assert "AGENTOS_RECORD_IDENTITY_UNAVAILABLE" in receipt["admission"]["blocking_codes"]


def test_plan_literal_protected_sha_is_passed_exactly(tmp_path, monkeypatch):
    cli = _cli()
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)
    literal = "a" * 40

    def fake_collect_skillpack(repo_root, protected_sha, bootstrap_major=1):
        assert Path(repo_root) == tmp_path / "unused-repo-root"
        assert protected_sha == literal
        assert bootstrap_major == 1
        return {
            "repository": MASTER,
            "sha": literal,
            "schema": "mastermind.sol_skillpack.v1",
            "version": "1.0.0",
            "minimum_bootstrap_major": 1,
            "available": True,
        }

    monkeypatch.setattr(cli, "collect_skillpack", fake_collect_skillpack, raising=False)
    code, stdout, stderr = _run(
        cli,
        _argv(snapshots, macro, literal),
        tmp_path / "unused-repo-root",
    )

    assert code == 0
    assert stderr == ""
    assert json.loads(stdout)["skillpack"]["sha"] == literal


def test_all_stable_flags_are_wired(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)

    argv = _argv(snapshots, macro, protected)
    argv[4:4] = ["--linear", "MAS-109"]
    argv[6:6] = ["--operation-key", "op-cli"]
    argv[8:8] = ["--requires-executive"]

    code, stdout, stderr = _run(cli, argv, repo)

    assert code == 0
    assert stderr == ""
    receipt = json.loads(stdout)
    assert receipt["scope"]["linear"] == ["MAS-109"]
    assert receipt["scope"]["operation_key"] == "op-cli"
    assert receipt["scope"]["requires_executive"] is True
    assert receipt["admission"]["mode"] == "DIALOGUE_ONLY"


def test_network_is_forbidden_and_source_trees_are_byte_identical(tmp_path, monkeypatch):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)
    before_macro = _tree_hashes(macro)
    before_snapshots = _tree_hashes(snapshots)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    code, stdout, stderr = _run(cli, _argv(snapshots, macro, protected), repo)

    assert code == 0
    assert json.loads(stdout)["schema"] == "mastermind.session_truth_receipt.v1"
    assert stderr == ""
    assert _tree_hashes(macro) == before_macro
    assert _tree_hashes(snapshots) == before_snapshots
    assert not (macro / ".ILLEGAL_WRITE").exists()


def test_two_runs_ignore_envelope_clock_but_cover_source_change(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)

    one_code, one_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T05:00:00Z"),
        repo,
    )
    two_code, two_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T05:10:00Z"),
        repo,
    )
    one = json.loads(one_stdout)
    two = json.loads(two_stdout)

    assert one_code == two_code == 0
    assert one["observation"] != two["observation"]
    assert one["semantic_hash"] == two["semantic_hash"]
    assert semantic_projection(one) == semantic_projection(two)

    github_path = snapshots / "github_minimal.json"
    github = json.loads(github_path.read_text(encoding="utf-8"))
    github["pull_requests"][0]["head_sha"] = "c" * 40
    github_path.write_text(json.dumps(github), encoding="utf-8")

    changed_code, changed_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T05:20:00Z"),
        repo,
    )
    changed = json.loads(changed_stdout)
    assert changed_code == 0
    assert changed["semantic_hash"] != one["semantic_hash"]
    assert [f["code"] for f in changed["findings"]] == sorted(
        [f["code"] for f in changed["findings"]],
        key=lambda code: (
            {"FATAL": 0, "BLOCKING": 1, "WARNING": 2, "INFO": 3}[
                next(f["severity"] for f in changed["findings"] if f["code"] == code)
            ],
            code,
        ),
    )


def test_malformed_secret_bearing_snapshot_exits_2_without_echo(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)
    github_path = snapshots / "github_minimal.json"
    github = json.loads(github_path.read_text(encoding="utf-8"))
    github["token"] = "SHOULD-NOT-LEAK"
    github_path.write_text(json.dumps(github), encoding="utf-8")

    code, stdout, stderr = _run(cli, _argv(snapshots, macro, protected), repo)

    assert code == 2
    assert stdout == ""
    assert 0 < len(stderr) <= 256
    assert "SHOULD-NOT-LEAK" not in stderr
    assert "\n" not in stderr.rstrip("\n")


def test_direct_agentos_identity_error_exits_2_without_running_invalid_command(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)
    argv = _argv(snapshots, macro, protected)
    index = argv.index("WS:CHAIRMAN-CONTROL-ROOM")
    argv[index] = "CHAIRMAN-CONTROL-ROOM"

    code, stdout, stderr = _run(cli, argv, repo)

    assert code == 2
    assert stdout == ""
    assert 0 < len(stderr) <= 256
    assert not (macro / ".ILLEGAL_WRITE").exists()


def test_agentos_timeout_exits_2_without_receipt(tmp_path, monkeypatch):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path, status_delay=5.0)
    snapshots = _snapshot_dir(tmp_path)
    original_collect_agentos = cli.collect_agentos

    def collect_with_scaled_test_timeout(macro_root, workstreams, *, environ, now):
        return original_collect_agentos(
            macro_root,
            workstreams,
            environ=environ,
            now=now,
            timeout=0.05,
        )

    monkeypatch.setattr(cli, "collect_agentos", collect_with_scaled_test_timeout)
    started = time.monotonic()
    code, stdout, stderr = _run(cli, _argv(snapshots, macro, protected), repo)

    assert code == 2
    assert stdout == ""
    assert stderr == "session-truth error: canonical acquisition failed\n"
    assert time.monotonic() - started < 2.0
    assert "--agentos-timeout" not in cli._parser()._option_string_actions


def test_text_mode_uses_bounded_renderer(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)
    argv = _argv(snapshots, macro, protected)
    argv.remove("--json")

    code, stdout, stderr = _run(cli, argv, repo)

    assert code == 0
    assert stderr == ""
    assert stdout.startswith("Session Truth Receipt\n")
    assert "source.executive: available=false reason=EXECUTIVE_READ_PATH_UNAVAILABLE" in stdout
    assert "DELIVERY_ONLY" not in stdout


# --- Owner-record identity amendment falsifiers (2026-08-28, Sol) -----------------
#
# Synthetic digest-backed two-clock proof (§3.1, migration step 4 SYNTHETIC ONLY):
# a stub canonical reader emits owner digests plus --now-derived volatile fields, so
# only a digest-backed positive projection can keep the semantic identity stable.
# This is NOT the real current-estate Task 7 acceptance; canonical Macro does not yet
# emit ``source_records_digest``.

STATE_DIGEST = "sha256:" + "3" * 64
CONTEXT_DIGEST = "sha256:" + "4" * 64


def _digest_macro_repo(tmp_path: Path) -> Path:
    macro = tmp_path / "macro-digest"
    _init_git(macro)
    ws = macro / "agentos" / "workstreams" / "WS-CHAIRMAN-CONTROL-ROOM.md"
    ws.parent.mkdir(parents=True)
    ws.write_text("# fixture\n", encoding="utf-8")
    script = macro / "scripts" / "agentos.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
now = args[args.index("--now") + 1] if "--now" in args else "unset"

if args and args[0] == "status" and "--dry-run" in args:
    payload = {
        "schema": "agent_os_state.v1",
        "generated_at": now,
        "source_records_digest": "sha256:" + "3" * 64,
        "inputs": {
            "workstreams": 1,
            "active_builds": "data/governance/active_builds.json@2026-08-24T01:18:31+00:00",
            "active_builds_age_hours": float(now[14:16] or 0) + 76.0,
            "degraded": ["stale probe measured at " + now],
        },
        "workstreams": [
            {
                "key": "CHAIRMAN-CONTROL-ROOM",
                "status": "active",
                "stale_days": int(now[15:16] or 0),
                "next_action": "prove session truth",
                "updated": "2026-08-27",
                "prs": [],
                "warnings": [],
                "source": "agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md"
            }
        ],
        "warnings": []
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

if args and args[0] == "compile-context" and "--workstream" in args:
    value = args[args.index("--workstream") + 1]
    payload = {
        "schema": "context_bundle.v1",
        "generated_at": now,
        "source_records_digest": "sha256:" + "4" * 64,
        "target": {"workstream": "WS:" + value, "resolution": "explicit"},
        "sections": [{"id": "handoff", "items": []}],
        "excluded": [],
        "omitted_due_to_budget": [],
        "degraded": []
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

raise SystemExit(7)
""",
        encoding="utf-8",
    )
    _commit_all(macro, "digest fixture")
    return macro


def test_synthetic_digest_backed_two_clock_proof(tmp_path):
    """Same records + owner digests at two acquisition clocks -> one semantic identity."""

    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _digest_macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)

    one_code, one_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T05:00:00Z"),
        repo,
    )
    two_code, two_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T06:11:00Z"),
        repo,
    )
    one = json.loads(one_stdout)
    two = json.loads(two_stdout)

    assert one_code == two_code == 0
    # The volatile fields really did move between the two observations...
    assert (
        one["observations"]["agentos"]["state"]["inputs"]["degraded"]
        != two["observations"]["agentos"]["state"]["inputs"]["degraded"]
    )
    assert (
        one["observations"]["agentos"]["state"]["workstreams"][0]["stale_days"]
        != two["observations"]["agentos"]["state"]["workstreams"][0]["stale_days"]
    )
    # ...yet unchanged direct records keep one digest-backed semantic identity.
    assert one["semantic_hash"] == two["semantic_hash"]
    assert semantic_projection(one) == semantic_projection(two)
    codes = {finding["code"] for finding in one["findings"]}
    assert "AGENTOS_RECORD_IDENTITY_UNAVAILABLE" not in codes


def test_synthetic_digest_change_moves_semantic_hash(tmp_path):
    cli = _cli()
    repo, protected = _skillpack_repo(tmp_path)
    macro = _digest_macro_repo(tmp_path)
    snapshots = _snapshot_dir(tmp_path)

    one_code, one_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T05:00:00Z"),
        repo,
    )
    script = macro / "scripts" / "agentos.py"
    script.write_text(
        script.read_text(encoding="utf-8").replace('"sha256:" + "3" * 64', '"sha256:" + "5" * 64'),
        encoding="utf-8",
    )
    two_code, two_stdout, _ = _run(
        cli,
        _argv(snapshots, macro, protected, now="2026-08-27T05:00:00Z"),
        repo,
    )
    assert one_code == two_code == 0
    assert json.loads(one_stdout)["semantic_hash"] != json.loads(two_stdout)["semantic_hash"]
