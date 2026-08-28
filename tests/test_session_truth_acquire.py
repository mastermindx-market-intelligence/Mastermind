from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess

import pytest


MODULE = "control_plane.session_truth_acquire"


def _acquire():
    try:
        return importlib.import_module(MODULE)
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing Session Truth acquisition module: {exc}")


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
    _git(repo, "config", "user.name", "Session Truth Tests")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write_index(repo: Path, *, version: str = "1.0.0", minimum: int = 1) -> None:
    path = repo / "docs" / "sol_skills" / "INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "schema: mastermind.sol_skillpack.v1\n"
        f"skillpack_version: {version}\n"
        f"minimum_bootstrap_major: {minimum}\n"
        "skill: index\n"
        "---\n\n# Test Skillpack\n",
        encoding="utf-8",
    )


def _two_commit_skillpack_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "Mastermind"
    _init_git(repo)
    _write_index(repo, version="1.0.0")
    protected = _commit_all(repo, "protected")
    _write_index(repo, version="9.9.9")
    _commit_all(repo, "branch-head")
    assert _git(repo, "rev-parse", "HEAD") != protected
    return repo, protected


def _snapshot_files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


def _macro_fixture(tmp_path: Path) -> Path:
    macro = tmp_path / "macro"
    _init_git(macro)
    (macro / "agentos").mkdir(parents=True)
    (macro / "agentos" / ".keep").write_text("\n", encoding="utf-8")
    script = macro / "scripts" / "agentos.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """#!/usr/bin/env python3
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
args = sys.argv[1:]
now = None
if '--now' in args:
    idx = args.index('--now')
    now = args[idx + 1]

if args and args[0] == 'status' and '--dry-run' in args:
    payload = {
        'schema': 'agent_os_state.v1',
        'generated_at': now,
        'workstreams': [
            {
                'key': 'TARGET', 'title': 'Target', 'status': 'active',
                'repos': ['Mastermind'], 'next_action': 'prove receipt',
                'updated': '2026-08-27', 'waves': [], 'wave_detail': [],
                'prs': [], 'source': 'agentos/workstreams/WS-TARGET.md',
            }
        ],
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True) + '\\nstatus summary\\n')
    raise SystemExit(0)

if args and args[0] == 'compile-context' and '--workstream' in args:
    value = args[args.index('--workstream') + 1]
    key = value[3:] if value.startswith('WS:') else value
    payload = {
        'schema': 'context_bundle.v1',
        'target': {'workstream': 'WS:' + key},
        'repo_sha': 'fixture',
        'sections': [], 'excluded': [], 'omitted_due_to_budget': [],
        'degraded': [], 'generated_at': now,
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

(root / '.ILLEGAL_WRITE').write_text('unexpected args: ' + repr(args), encoding='utf-8')
raise SystemExit(7)
""",
        encoding="utf-8",
    )
    _commit_all(macro, "fixture")
    return macro


def test_collect_skillpack_reads_exact_commit_not_branch_head(tmp_path):
    module = _acquire()
    repo, protected_sha = _two_commit_skillpack_repo(tmp_path)
    got = module.collect_skillpack(repo, protected_sha=protected_sha, bootstrap_major=1)
    assert got == {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "sha": protected_sha,
        "schema": "mastermind.sol_skillpack.v1",
        "version": "1.0.0",
        "minimum_bootstrap_major": 1,
        "available": True,
    }


def test_collect_skillpack_never_relabels_missing_commit_as_protected(tmp_path):
    module = _acquire()
    repo, _ = _two_commit_skillpack_repo(tmp_path)
    missing = "f" * 40
    got = module.collect_skillpack(repo, protected_sha=missing, bootstrap_major=1)
    assert got == {
        "available": False,
        "reason": "SKILLPACK_COMMIT_UNAVAILABLE",
        "sha": missing,
    }


def test_collect_skillpack_fails_on_incompatible_bootstrap(tmp_path):
    module = _acquire()
    repo = tmp_path / "Mastermind"
    _init_git(repo)
    _write_index(repo, minimum=2)
    protected = _commit_all(repo, "requires-bootstrap-2")
    with pytest.raises(module.AcquisitionError, match="bootstrap major"):
        module.collect_skillpack(repo, protected_sha=protected, bootstrap_major=1)


def test_collect_skillpack_fails_on_malformed_frontmatter(tmp_path):
    module = _acquire()
    repo = tmp_path / "Mastermind"
    _init_git(repo)
    path = repo / "docs" / "sol_skills" / "INDEX.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nschema:\n---\n", encoding="utf-8")
    protected = _commit_all(repo, "malformed")
    with pytest.raises(module.AcquisitionError, match="frontmatter"):
        module.collect_skillpack(repo, protected_sha=protected, bootstrap_major=1)


def test_collect_agentos_uses_status_and_context_without_writes(tmp_path):
    module = _acquire()
    macro = _macro_fixture(tmp_path)
    before = _snapshot_files(macro)
    got = module.collect_agentos(
        os.fspath(macro),
        ["WS:TARGET"],
        environ={},
        now="2026-08-27T05:00:00Z",
        timeout=5,
    )
    assert got["available"] is True
    assert got["source_sha"] == _git(macro, "rev-parse", "HEAD")
    assert got["state"]["schema"] == "agent_os_state.v1"
    assert got["state"]["workstreams"][0]["key"] == "TARGET"
    assert got["contexts"][0]["schema"] == "context_bundle.v1"
    assert got["contexts"][0]["target"]["workstream"] == "WS:TARGET"
    assert got["warnings"] == ["agentos status emitted trailing non-JSON diagnostics"]
    assert _snapshot_files(macro) == before
    assert not (macro / ".ILLEGAL_WRITE").exists()


def test_collect_agentos_missing_read_path_is_explicitly_unavailable(tmp_path):
    module = _acquire()
    got = module.collect_agentos(
        os.fspath(tmp_path / "missing"),
        ["WS:TARGET"],
        environ={},
        now="2026-08-27T05:00:00Z",
        timeout=5,
    )
    assert got["available"] is False
    assert got["reason"] == "AGENTOS_READ_PATH_UNAVAILABLE"
    assert got["contexts"] == []


def test_collect_agentos_rejects_non_workstream_identity(tmp_path):
    module = _acquire()
    macro = _macro_fixture(tmp_path)
    with pytest.raises(module.AcquisitionError, match="WS:"):
        module.collect_agentos(
            os.fspath(macro),
            ["TARGET"],
            environ={},
            now="2026-08-27T05:00:00Z",
            timeout=5,
        )


# --- Owner-record identity amendment falsifiers (2026-08-28, Sol) -----------------
#
# §5: canonical Agent OS output parsing rejects NaN / Infinity / -Infinity through
# ``parse_constant`` on the typed acquisition error path.


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_decode_leading_json_rejects_non_finite_numbers(constant):
    module = _acquire()
    with pytest.raises(module.AcquisitionError):
        module._decode_leading_json(
            '{"schema": "agent_os_state.v1", "age": ' + constant + "}",
            "Agent OS status",
        )


def test_decode_leading_json_still_accepts_finite_numbers():
    module = _acquire()
    value, trailing = module._decode_leading_json(
        '{"schema": "agent_os_state.v1", "age": 1.5}\ntrailing',
        "Agent OS status",
    )
    assert value["age"] == 1.5
    assert trailing == "trailing"
