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
        packet_python=python, packet_runner=runner, code_root=repo,
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
        "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
        "MACRO_MASTERMIND_REPO", "MACRO_TERMINAL_REPO",
    }
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
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
        packet_python=python, packet_runner=runner, code_root=repo,
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
