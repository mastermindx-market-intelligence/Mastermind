from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_installed_boot_packet_collector_uses_dependency_python_and_exact_roots(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    repo.mkdir()
    macro.mkdir()
    python = tmp_path / "network-python"
    python.write_text("fixture", encoding="utf-8")
    code = tmp_path / "immutable-release"
    (code / "scripts").mkdir(parents=True)
    observed: dict[str, object] = {}
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "generated_at": "2026-09-15T03:00:00Z",
        "mastermind": {"root": str(repo), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40, "resolved_via": "flag", "candidates_tried": []},
        "strategic_state": {"schema": "mastermind.strategic_state.v1"},
        "brief": {"schema": "ceo_brief.v1"},
        "handoffs": [], "degraded": [], "next_recommended_act": "continue",
    }
    def runner(argv, *, cwd, timeout, max_bytes, env):
        if str(argv[0]) == "git":
            return _git_status_result("a" * 40 if Path(cwd) == repo else "b" * 40)
        observed.update(
            argv=list(argv), cwd=Path(cwd), timeout=timeout,
            max_bytes=max_bytes, env=dict(env),
        )
        return {
            "code": 0,
            "stdout": json.dumps(packet),
            "stderr": "",
            "timed_out": False,
            "limit_exceeded": False,
            "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo,
        macro_root=macro,
        code_root=code,
        python_executable=python,
        runner=runner, expected_source_sha="a" * 40,
    )
    actual = collector(
        repo_root=repo,
        macro_root_flag=str(macro),
        now="2026-09-15T03:00:00Z",
        timeout=7.0,
    )

    assert actual == packet
    assert observed["cwd"] == code
    argv = observed["argv"]
    assert argv[0] == str(python)
    assert argv[1:3] == ["-I", "-B"]
    assert argv[3] == str(code / "scripts" / "ceo_boot_packet.py")
    assert argv[argv.index("--repo-root") + 1] == str(repo)
    assert argv[argv.index("--macro-root") + 1] == str(macro)
    assert argv[argv.index("--now") + 1] == "2026-09-15T03:00:00Z"
    assert argv[argv.index("--timeout") + 1] == "5"


def test_ceo_boot_packet_cli_accepts_explicit_repo_root(tmp_path: Path):
    from scripts import ceo_boot_packet as cli

    repo = tmp_path / "reviewed-mastermind"
    args = cli._parser().parse_args(["--json", "--repo-root", str(repo)])

    assert args.repo_root == str(repo)


def test_installed_readers_wires_dependency_complete_packet_collector(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector, InstalledExecutiveReaders

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    runtime = tmp_path / "runtime"
    for path in (repo, macro, runtime):
        path.mkdir()
    python = tmp_path / "network-python"
    python.write_text("fixture", encoding="utf-8")

    def runner(_argv, **_kwargs):
        raise AssertionError("constructor must not execute the collector")

    readers = InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
        boot_python=python, packet_runner=runner, code_root=repo,
        expected_source_sha="a" * 40,
    )
    assert isinstance(readers._packet_builder, InstalledBootPacketCollector)


def test_installed_boot_packet_collector_has_bounded_default_subprocess_runner(tmp_path: Path):
    import subprocess
    import sys
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    code = tmp_path / "immutable-release"
    repo.mkdir(); macro.mkdir(); (code / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("source\n", encoding="utf-8")
    (macro / "README.md").write_text("macro\n", encoding="utf-8")
    for root in (repo, macro):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
    source_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    script = code / "scripts" / "ceo_boot_packet.py"
    script.write_text(
        "import json,subprocess,sys\n"
        "def arg(name): return sys.argv[sys.argv.index(name)+1]\n"
        "repo=arg('--repo-root'); macro=arg('--macro-root')\n"
        "def sha(root): return subprocess.run(['git','-C',root,'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()\n"
        "print(json.dumps({'schema':'mastermind.ceo_boot_packet.v1','generated_at':'2026-09-15T03:00:00Z',"
        "'mastermind':{'root':repo,'sha':sha(repo),'branch':'HEAD'},"
        "'macro':{'root':macro,'sha':sha(macro),'resolved_via':'flag','candidates_tried':[]},"
        "'strategic_state':{},'brief':{},'handoffs':[],'degraded':[],'next_recommended_act':'continue'}))\n",
        encoding="utf-8",
    )
    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=Path(sys.executable), expected_source_sha=source_sha,
    )
    packet = collector(
        repo_root=repo, macro_root_flag=str(macro),
        now="2026-09-15T03:00:00Z", timeout=5.0,
    )

    assert packet["mastermind"]["root"] == str(repo)
    assert packet["mastermind"]["sha"] == source_sha
    assert packet["macro"]["root"] == str(macro)
    assert packet["degraded"] == []


def test_installed_boot_packet_collector_reads_real_macro_from_materialization(tmp_path: Path):
    import subprocess
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    code = tmp_path / "immutable-release"
    repo.mkdir(); macro.mkdir(); (code / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("source\n", encoding="utf-8")
    (macro / "agentos").mkdir()
    (macro / "agentos" / "record.md").write_text("record\n", encoding="utf-8")
    for root in (repo, macro):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
    source_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    macro_sha = subprocess.run(
        ["git", "-C", str(macro), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    python = tmp_path / "network-python"
    python.write_text("fixture", encoding="utf-8")
    observed: dict[str, Path] = {}

    def runner(argv, **kwargs):
        if str(argv[0]) == "git":
            return _default_packet_runner(argv, **kwargs)
        child_macro = Path(argv[argv.index("--macro-root") + 1])
        observed["macro_root"] = child_macro
        packet = {
            "schema": "mastermind.ceo_boot_packet.v1",
            "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
            "macro": {
                "root": str(child_macro), "sha": macro_sha, "resolved_via": "flag",
                "candidates_tried": [{"via": "flag", "path": str(child_macro), "usable": True, "reason": None}],
            },
        }
        return {
            "code": 0, "stdout": json.dumps(packet), "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    packet = collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0)

    child_macro = observed["macro_root"]
    assert child_macro != macro
    assert packet["macro"]["root"] == str(macro)
    assert packet["macro"]["candidates_tried"][0]["path"] == str(macro)
    assert child_macro.exists() is False


def test_installed_boot_packet_collector_refuses_live_macro_mutate_and_restore(
    tmp_path: Path,
):
    import subprocess
    import time
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    code = tmp_path / "immutable-release"
    repo.mkdir(); macro.mkdir(); (code / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("source\n", encoding="utf-8")
    record = macro / "agentos" / "record.md"
    record.parent.mkdir()
    record.write_text("original\n", encoding="utf-8")
    for root in (repo, macro):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"], check=True)
    source_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    macro_sha = subprocess.run(
        ["git", "-C", str(macro), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    python = tmp_path / "network-python"
    python.write_text("fixture", encoding="utf-8")

    def runner(argv, **kwargs):
        if str(argv[0]) == "git":
            return _default_packet_runner(argv, **kwargs)
        child_macro = Path(argv[argv.index("--macro-root") + 1])
        assert child_macro != macro
        before_ctime = record.stat().st_ctime_ns
        original = record.read_bytes()
        time.sleep(0.01)
        record.write_bytes(b"transient mutation\n")
        record.write_bytes(original)
        assert record.read_bytes() == original
        assert record.stat().st_ctime_ns != before_ctime
        packet = {
            "schema": "mastermind.ceo_boot_packet.v1",
            "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
            "macro": {
                "root": str(child_macro), "sha": macro_sha, "resolved_via": "flag",
                "candidates_tried": [],
            },
        }
        return {
            "code": 0, "stdout": json.dumps(packet), "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    with pytest.raises(GatewayError, match="changed during boot-packet read"):
        collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0)


def test_installed_boot_packet_collector_refuses_foreign_packet_roots(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector
    from integrations.executive_mcp.schemas import GatewayError

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    repo.mkdir()
    macro.mkdir()
    python = tmp_path / "network-python"
    python.write_text("fixture", encoding="utf-8")
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "mastermind": {"root": str(tmp_path / "foreign"), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40, "resolved_via": "flag", "candidates_tried": []},
    }
    def runner(argv, *, cwd, **_kwargs):
        if str(argv[0]) == "git":
            return _git_status_result("a" * 40 if Path(cwd) == repo else "b" * 40)
        return {
            "code": 0, "stdout": json.dumps(packet), "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=repo,
        python_executable=python, runner=runner, expected_source_sha="a" * 40,
    )
    with pytest.raises(GatewayError, match="roots"):
        collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0)


def test_installed_boot_packet_collector_preserves_configured_python_environment_path(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    repo.mkdir()
    macro.mkdir()
    target = tmp_path / "real-python"
    target.write_text("fixture", encoding="utf-8")
    runtime_bin = tmp_path / "runtime" / "bin"
    runtime_bin.mkdir(parents=True)
    configured_python = runtime_bin / "python"
    configured_python.symlink_to(target)
    observed: dict[str, object] = {}
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "mastermind": {"root": str(repo), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40, "resolved_via": "flag", "candidates_tried": []},
    }

    def runner(argv, *, cwd, **_kwargs):
        if str(argv[0]) == "git":
            return _git_status_result("a" * 40 if Path(cwd) == repo else "b" * 40)
        observed["argv"] = list(argv)
        return {
            "code": 0, "stdout": json.dumps(packet), "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=repo,
        python_executable=configured_python, runner=runner, expected_source_sha="a" * 40,
    )
    collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0)

    assert observed["argv"][0] == str(configured_python)


def test_default_packet_runner_kills_output_overflow(tmp_path: Path):
    import sys
    from integrations.executive_mcp.installed import _default_packet_runner

    script = tmp_path / "overflow.py"
    script.write_text("print('x' * 2048)\n", encoding="utf-8")
    result = _default_packet_runner(
        [sys.executable, str(script)], cwd=tmp_path, timeout=5.0, max_bytes=64,
    )

    assert result["limit_exceeded"] is True
    assert result["timed_out"] is False


def test_default_packet_runner_kills_timeout(tmp_path: Path):
    import sys
    from integrations.executive_mcp.installed import _default_packet_runner

    script = tmp_path / "slow.py"
    script.write_text("import time; time.sleep(5)\n", encoding="utf-8")
    result = _default_packet_runner(
        [sys.executable, str(script)], cwd=tmp_path, timeout=0.05, max_bytes=1024,
    )

    assert result["timed_out"] is True


def test_executive_mcp_runtime_lock_includes_dependency_complete_read_stack():
    root = Path(__file__).resolve().parents[1]
    direct = (root / "requirements" / "executive-mcp-macos-arm64-py312.in").read_text(encoding="utf-8")
    lock = (root / "requirements" / "executive-mcp-macos-arm64-py312.lock").read_text(encoding="utf-8").lower()

    assert "mcp==1.28.1" in direct
    assert "PyJWT[crypto]==2.13.0" in direct
    assert "PyYAML==6.0.3" in direct
    assert "uvicorn[standard]==0.52.4" in direct
    assert "mcp==1.28.1" in lock
    assert "pyyaml==6.0.3" in lock


def test_installed_collector_scopes_git_trust_and_mastermind_sibling(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = (tmp_path / "mastermind").resolve()
    macro = (tmp_path / "macro").resolve()
    repo.mkdir()
    macro.mkdir()
    python = (tmp_path / "network-python").resolve()
    python.write_text("fixture", encoding="utf-8")
    observed: dict[str, object] = {}
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "mastermind": {"root": str(repo), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40, "resolved_via": "flag", "candidates_tried": []},
    }

    def runner(argv, **kwargs):
        if str(argv[0]) == "git":
            return _git_status_result("a" * 40 if Path(kwargs["cwd"]) == repo else "b" * 40)
        observed.update(kwargs)
        return {"code": 0, "stdout": json.dumps(packet), "stderr": "",
                "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}
    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=repo,
        python_executable=python, runner=runner, expected_source_sha="a" * 40,
    )
    collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0)

    env = observed["env"]
    assert set(env) == {
        "PATH", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE",
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_NO_REPLACE_OBJECTS",
        "GIT_NO_LAZY_FETCH",
        "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
        "MACRO_MASTERMIND_REPO", "MACRO_TERMINAL_REPO",
    }
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_NO_LAZY_FETCH"] == "1"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "safe.directory"
    assert env["GIT_CONFIG_VALUE_0"] == str(macro)
    assert env["MACRO_MASTERMIND_REPO"] == str(repo)
    assert env["MACRO_TERMINAL_REPO"] == str(repo / ".executive-no-terminal-repo")


def test_default_packet_runner_uses_explicit_environment(tmp_path: Path):
    import os
    import sys
    from integrations.executive_mcp.installed import _default_packet_runner

    script = tmp_path / "env_probe.py"
    script.write_text("import os; print(os.environ['MMX_PACKET_ENV'])\n", encoding="utf-8")
    env = dict(os.environ)
    env["MMX_PACKET_ENV"] = "scoped"
    result = _default_packet_runner(
        [sys.executable, str(script)], cwd=tmp_path, timeout=5.0,
        max_bytes=1024, env=env,
    )

    assert result["code"] == 0
    assert result["stdout"].strip() == "scoped"
    assert result["timed_out"] is False
    assert result["limit_exceeded"] is False


def test_installed_grounding_observer_uses_scoped_git_trust(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledExecutiveReaders

    repo = (tmp_path / "mastermind").resolve()
    macro = (tmp_path / "macro").resolve()
    runtime = (tmp_path / "runtime").resolve()
    for path in (repo, macro, runtime):
        path.mkdir()
    python = (tmp_path / "network-python").resolve()
    python.write_text("fixture", encoding="utf-8")
    calls: list[tuple[Path, dict[str, str]]] = []

    def runner(argv, *, cwd, timeout, max_bytes, env):
        calls.append((Path(cwd), dict(env)))
        sha = "a" * 40 if Path(cwd) == repo else "b" * 40
        return _git_status_result(sha)

    readers = InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
        boot_python=python, packet_runner=runner, code_root=repo,
        expected_source_sha="a" * 40,
    )
    observed = readers.observe()

    assert observed == {
        "mastermind_sha": "a" * 40,
        "macro_sha": "b" * 40,
        "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
    }
    assert [cwd for cwd, _env in calls] == [repo, macro]
    for _cwd, env in calls:
        assert env["GIT_CONFIG_VALUE_0"] == str(macro)
        assert env["MACRO_MASTERMIND_REPO"] == str(repo)
        assert env["MACRO_TERMINAL_REPO"] == str(repo / ".executive-no-terminal-repo")
        assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
        assert env["GIT_NO_REPLACE_OBJECTS"] == "1"


def _git_status_result(sha: str, *, dirty: str = "") -> dict[str, object]:
    body = f"# branch.oid {sha}\n# branch.head (detached)\n{dirty}"
    return {"code": 0, "stdout": body, "stderr": "", "timed_out": False,
            "limit_exceeded": False, "invalid_utf8": False}


def test_installed_collector_executes_immutable_code_root_and_binds_clean_snapshots(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = (tmp_path / "mastermind-data").resolve()
    macro = (tmp_path / "macro-data").resolve()
    code = (tmp_path / "immutable-release").resolve()
    for path in (repo, macro, code / "scripts"):
        path.mkdir(parents=True, exist_ok=True)
    python = tmp_path / "python"; python.write_text("fixture", encoding="utf-8")
    (code / "scripts" / "ceo_boot_packet.py").write_text("# immutable fixture\n", encoding="utf-8")
    calls: list[tuple[list[str], Path, dict[str, str]]] = []
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "mastermind": {"root": str(repo), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40,
                  "resolved_via": "flag", "candidates_tried": []},
    }

    def runner(argv, *, cwd, timeout, max_bytes, env):
        argv = [str(v) for v in argv]
        calls.append((argv, Path(cwd), dict(env)))
        if argv[:3] == ["git", "status", "--porcelain=v2"]:
            return _git_status_result("a" * 40 if Path(cwd) == repo else "b" * 40)
        return {"code": 0, "stdout": json.dumps(packet), "stderr": "",
                "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha="a" * 40,
    )
    actual = collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=7.0)

    assert actual == packet
    helper_calls = [call for call in calls if call[0][0] != "git"]
    assert len(helper_calls) == 1
    argv, cwd, env = helper_calls[0]
    assert cwd == code
    assert argv[1:3] == ["-I", "-B"]
    assert argv[3] == str(code / "scripts" / "ceo_boot_packet.py")
    assert argv[argv.index("--repo-root") + 1] == str(repo)
    assert env["MACRO_MASTERMIND_REPO"] == str(code)
    assert len([call for call in calls if call[0][0] == "git"]) == 4


def test_installed_collector_refuses_dirty_source_before_helper(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector
    from integrations.executive_mcp.schemas import GatewayError

    repo = (tmp_path / "repo").resolve(); repo.mkdir()
    macro = (tmp_path / "macro").resolve(); macro.mkdir()
    code = (tmp_path / "release").resolve(); (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"; python.write_text("fixture", encoding="utf-8")
    helper_called = False

    def runner(argv, *, cwd, timeout, max_bytes, env):
        nonlocal helper_called
        argv = [str(v) for v in argv]
        if argv[0] == "git":
            if Path(cwd) == repo:
                return _git_status_result("a" * 40, dirty="1 .M N... 100644 100644 100644 a b config/strategic_state.yml\n")
            return _git_status_result("b" * 40)
        helper_called = True
        raise AssertionError("dirty data root must refuse before helper execution")

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha="a" * 40,
    )
    with pytest.raises(GatewayError, match="clean"):
        collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=7.0)
    assert helper_called is False


def test_installed_collector_refuses_source_sha_change_after_read(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector
    from integrations.executive_mcp.schemas import GatewayError

    repo = (tmp_path / "repo").resolve(); repo.mkdir()
    macro = (tmp_path / "macro").resolve(); macro.mkdir()
    code = (tmp_path / "release").resolve(); (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"; python.write_text("fixture", encoding="utf-8")
    source_reads = 0
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "mastermind": {"root": str(repo), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40,
                  "resolved_via": "flag", "candidates_tried": []},
    }

    def runner(argv, *, cwd, timeout, max_bytes, env):
        nonlocal source_reads
        argv = [str(v) for v in argv]
        if argv[0] == "git":
            if Path(cwd) == repo:
                source_reads += 1
                return _git_status_result(("a" if source_reads == 1 else "c") * 40)
            return _git_status_result("b" * 40)
        return {"code": 0, "stdout": json.dumps(packet), "stderr": "",
                "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha="a" * 40,
    )
    with pytest.raises(GatewayError, match="changed"):
        collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=7.0)


def test_installed_collector_reserves_inner_timeout_margin(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = (tmp_path / "repo").resolve(); repo.mkdir()
    macro = (tmp_path / "macro").resolve(); macro.mkdir()
    code = (tmp_path / "release").resolve(); (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"; python.write_text("fixture", encoding="utf-8")
    packet = {
        "schema": "mastermind.ceo_boot_packet.v1",
        "mastermind": {"root": str(repo), "sha": "a" * 40, "branch": "HEAD"},
        "macro": {"root": str(macro), "sha": "b" * 40,
                  "resolved_via": "flag", "candidates_tried": []},
    }
    helper: dict[str, object] = {}

    def runner(argv, *, cwd, timeout, max_bytes, env):
        argv = [str(v) for v in argv]
        if argv[0] == "git":
            return _git_status_result("a" * 40 if Path(cwd) == repo else "b" * 40)
        helper.update(argv=argv, timeout=timeout)
        return {"code": 0, "stdout": json.dumps(packet), "stderr": "",
                "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha="a" * 40,
    )
    collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=7.0)
    argv = helper["argv"]
    inner = float(argv[argv.index("--timeout") + 1])
    assert helper["timeout"] == 7.0
    assert 0 < inner <= 5.0


def test_default_packet_runner_repeated_fast_exit_overflow_is_closed(tmp_path: Path):
    import sys
    from integrations.executive_mcp.installed import _default_packet_runner

    script = tmp_path / "fast_overflow.py"
    script.write_text("print('x' * 2048)\n", encoding="utf-8")
    for _ in range(100):
        result = _default_packet_runner(
            [sys.executable, str(script)], cwd=tmp_path, timeout=5.0, max_bytes=64,
        )
        assert result["limit_exceeded"] is True


def test_default_packet_runner_kills_quiet_descendant_group(tmp_path: Path):
    import os
    import sys
    import time
    from integrations.executive_mcp.installed import _default_packet_runner

    pid_file = tmp_path / "child.pid"
    script = tmp_path / "descendant.py"
    script.write_text(
        "import os,subprocess,sys,time\n"
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"open({str(pid_file)!r},'w').write(str(p.pid))\n"
        "print('done', flush=True)\n",
        encoding="utf-8",
    )
    result = _default_packet_runner(
        [sys.executable, str(script)], cwd=tmp_path, timeout=5.0, max_bytes=1024,
    )
    assert result["code"] == 0
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 1.0
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail("owned descendant survived runner return")
        time.sleep(0.01)


def test_process_group_cleanup_refuses_uncertain_live_group(monkeypatch):
    import control_plane.ceo_boot_packet as packet

    class FakeProcess:
        pid = 424242
        returncode = None

        def poll(self):
            return None

        def kill(self):
            raise PermissionError("leader kill refused")

        def wait(self, timeout=None):
            raise AssertionError("uncertain live leader must refuse before wait")

    monkeypatch.setattr(packet, "_process_group_presence", lambda _pgid: True)
    monkeypatch.setattr(packet, "_positively_settled", lambda _proc, *, timeout: False)
    monkeypatch.setattr(packet.os, "killpg", lambda _pgid, _sig: (_ for _ in ()).throw(PermissionError("group kill refused")))

    with pytest.raises(RuntimeError, match="cleanup is uncertain"):
        packet._terminate_owned_process_group(FakeProcess())


def _capacity_runtime_contract_fixture(tmp_path: Path, monkeypatch):
    import hashlib
    import os
    from types import SimpleNamespace
    from control_plane import ceo_boot_packet as packet

    runtime = tmp_path / "capacity-runtimes" / "fixture"
    python = runtime / "bin" / "python3.12"
    site_packages = runtime / "lib" / "python3.12" / "site-packages"
    record = site_packages / "pyyaml-6.0.3.dist-info" / "RECORD"
    record.parent.mkdir(parents=True)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"fixture-python")
    python.chmod(0o555)
    record.write_text("fixture,sha256=fixture,1\n", encoding="utf-8")
    record.chmod(0o444)
    for directory in (runtime, runtime / "bin", runtime / "lib", runtime / "lib" / "python3.12", site_packages, record.parent):
        directory.chmod(0o555)

    contract = SimpleNamespace(
        runtime_root=runtime,
        python_binary=python,
        site_packages=site_packages,
        python_version="3.12.10",
        python_binary_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),
        pyyaml_version="6.0.3",
        pyyaml_record_sha256="a" * 64,
        runtime_tree_sha256="b" * 64,
        owner_uid=os.getuid(),
        owner_gid=os.getgid(),
        has_extended_acl=lambda _descriptor: False,
        verify_pyyaml_record=lambda root: "a" * 64,
        runtime_tree_digest=lambda root: "b" * 64,
    )
    monkeypatch.setattr(packet, "_capacity_runtime_contract", lambda: contract, raising=False)
    return packet, contract


def test_capacity_boot_runtime_attestor_binds_exact_closure_and_probe(
    tmp_path: Path, monkeypatch,
):
    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)
    calls = []

    def runner(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return {
            "code": 0, "stdout": "CAPACITY_RUNTIME_OK\n", "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    site_packages = packet.attest_capacity_boot_runtime(
        contract.python_binary, runner=runner,
    )

    assert site_packages == contract.site_packages
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:4] == [str(contract.python_binary), "-I", "-S", "-B"]
    probe_code = argv[5]
    assert "sys.prefix" not in probe_code
    assert "sys.base_prefix" not in probe_code
    assert "site.ENABLE_USER_SITE is not True" in probe_code
    assert kwargs["env"] == {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    assert str(contract.site_packages) in argv
    assert contract.python_version in argv
    assert contract.pyyaml_version in argv


def test_capacity_boot_runtime_attestor_allows_root_owned_sealed_ancestor_with_different_gid(
    tmp_path: Path, monkeypatch,
):
    import os
    import stat
    from types import SimpleNamespace

    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)
    outer = tmp_path / "system-ancestor"
    outer.mkdir()
    contract.trusted_ancestors = (outer, contract.runtime_root)
    original_lstat = Path.lstat
    original_fstat = os.fstat
    outer_real = original_lstat(outer)

    def observed_outer(real):
        return SimpleNamespace(
            st_dev=real.st_dev, st_ino=real.st_ino,
            st_mode=stat.S_IFDIR | 0o755, st_uid=contract.owner_uid,
            st_gid=contract.owner_gid + 1, st_nlink=real.st_nlink,
        )

    def lstat(path):
        if path == outer:
            return observed_outer(original_lstat(path))
        return original_lstat(path)

    def fstat(descriptor):
        real = original_fstat(descriptor)
        if (real.st_dev, real.st_ino) == (outer_real.st_dev, outer_real.st_ino):
            return observed_outer(real)
        return real

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(os, "fstat", fstat)
    result = packet.attest_capacity_boot_runtime(
        contract.python_binary,
        runner=lambda *_args, **_kwargs: {
            "code": 0, "stdout": "CAPACITY_RUNTIME_OK\n", "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        },
    )
    assert result == contract.site_packages


def test_capacity_boot_runtime_attestor_keeps_runtime_root_on_exact_group(
    tmp_path: Path, monkeypatch,
):
    import stat
    from types import SimpleNamespace

    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)
    contract.trusted_ancestors = (contract.runtime_root,)
    contract.strict_group_ancestors = (contract.runtime_root,)
    original_lstat = Path.lstat

    def lstat(path):
        if path == contract.runtime_root:
            observed = original_lstat(path)
            return SimpleNamespace(
                st_mode=observed.st_mode, st_uid=contract.owner_uid,
                st_gid=contract.owner_gid + 1, st_nlink=observed.st_nlink,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(RuntimeError, match="capacity runtime ancestor metadata differs"):
        packet.attest_capacity_boot_runtime(
            contract.python_binary,
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("probe must not run after runtime-root group drift")
            ),
        )


@pytest.mark.parametrize("owner_delta,mode", [(1, 0o755), (0, 0o775)])
def test_capacity_boot_runtime_attestor_refuses_untrusted_traversal_ancestor(
    tmp_path: Path, monkeypatch, owner_delta: int, mode: int,
):
    import stat
    from types import SimpleNamespace

    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)
    outer = tmp_path / "system-ancestor"
    outer.mkdir()
    contract.trusted_ancestors = (outer, contract.runtime_root)
    original_lstat = Path.lstat

    def lstat(path):
        if path == outer:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | mode,
                st_uid=contract.owner_uid + owner_delta,
                st_gid=contract.owner_gid + 1, st_nlink=2,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(RuntimeError, match="capacity runtime ancestor metadata differs"):
        packet.attest_capacity_boot_runtime(
            contract.python_binary,
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("probe must not run after ancestor trust failure")
            ),
        )


def test_capacity_boot_runtime_attestor_refuses_tree_digest_drift(
    tmp_path: Path, monkeypatch,
):
    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)
    contract.runtime_tree_digest = lambda root: "c" * 64

    with pytest.raises(RuntimeError, match="runtime tree digest differs"):
        packet.attest_capacity_boot_runtime(
            contract.python_binary,
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("probe must not run after closure drift")
            ),
        )


def test_installed_reader_reserves_gateway_timeout_margin(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledExecutiveReaders
    from integrations.executive_mcp.schemas import READ_TIMEOUT_SECONDS

    repo = (tmp_path / "repo").resolve()
    macro = (tmp_path / "macro").resolve()
    runtime = (tmp_path / "runtime").resolve()
    for path in (repo, macro, runtime):
        path.mkdir()

    readers = InstalledExecutiveReaders(
        repo_root=repo, macro_root=macro, runtime_root=runtime,
    )

    assert readers.config.boot_packet_timeout == READ_TIMEOUT_SECONDS - 2.0
    assert readers.config.boot_packet_timeout < READ_TIMEOUT_SECONDS


def test_installed_boot_packet_collector_refuses_materialized_macro_mutate_and_restore(
    tmp_path: Path,
):
    import json
    import subprocess
    import time
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    code = tmp_path / "immutable-release"
    repo.mkdir()
    macro.mkdir()
    (code / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("source\n", encoding="utf-8")
    record = macro / "agentos" / "workstreams" / "WS-TEST.md"
    record.parent.mkdir(parents=True)
    record.write_text("---\nkey: WS-TEST\n---\noriginal\n", encoding="utf-8")
    for root in (repo, macro):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-q", "-m", "fixture"],
            check=True,
        )
    source_sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    macro_sha = subprocess.run(
        ["git", "-C", str(macro), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    python = tmp_path / "network-python"
    python.write_text("fixture", encoding="utf-8")

    def runner(argv, **kwargs):
        if str(argv[0]) == "git":
            return _default_packet_runner(argv, **kwargs)
        child_macro = Path(argv[argv.index("--macro-root") + 1])
        child_record = child_macro / "agentos" / "workstreams" / "WS-TEST.md"
        original = child_record.read_bytes()
        before_ctime = child_record.stat().st_ctime_ns
        time.sleep(0.01)
        child_record.write_bytes(b"transient child mutation\n")
        child_record.write_bytes(original)
        assert child_record.read_bytes() == original
        assert child_record.stat().st_ctime_ns != before_ctime
        packet = {
            "schema": "mastermind.ceo_boot_packet.v1",
            "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
            "macro": {
                "root": str(child_macro),
                "sha": macro_sha,
                "resolved_via": "flag",
                "candidates_tried": [],
            },
        }
        return {
            "code": 0,
            "stdout": json.dumps(packet),
            "stderr": "",
            "timed_out": False,
            "limit_exceeded": False,
            "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo,
        macro_root=macro,
        code_root=code,
        python_executable=python,
        runner=runner,
        expected_source_sha=source_sha,
    )
    with pytest.raises(GatewayError, match="materialized Macro changed during boot-packet read"):
        collector(repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0)


def test_capacity_boot_runtime_attestor_refuses_extended_acl_observation(
    tmp_path: Path, monkeypatch,
):
    from control_plane import ceo_boot_packet as packet

    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)
    contract.has_extended_acl = lambda _descriptor: True

    with pytest.raises(RuntimeError, match="capacity runtime ACL seal differs"):
        packet.attest_capacity_boot_runtime(
            contract.python_binary,
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("probe must not run after ACL drift")
            ),
        )


def test_capacity_boot_runtime_attestor_refuses_acl_observer_failure(
    tmp_path: Path, monkeypatch,
):
    from control_plane import ceo_boot_packet as packet

    packet, contract = _capacity_runtime_contract_fixture(tmp_path, monkeypatch)

    def fail_acl(_descriptor):
        raise OSError("acl observer unavailable")

    contract.has_extended_acl = fail_acl
    with pytest.raises(RuntimeError, match="capacity runtime ACL inspection failed"):
        packet.attest_capacity_boot_runtime(
            contract.python_binary,
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("probe must not run after ACL observer failure")
            ),
        )


def test_capacity_boot_runtime_contract_reuses_capacity_acl_owner():
    from control_plane import ceo_boot_packet as packet
    from ops.executive_os import capacity_host_artifacts

    contract = packet._capacity_runtime_contract()
    assert contract.has_extended_acl is capacity_host_artifacts._descriptor_has_extended_acl
