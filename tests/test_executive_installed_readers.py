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
    def runner(argv, *, cwd, timeout, max_bytes):
        observed.update(argv=list(argv), cwd=Path(cwd), timeout=timeout, max_bytes=max_bytes)
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
        python_executable=python,
        runner=runner,
    )
    actual = collector(
        repo_root=repo,
        macro_root_flag=str(macro),
        now="2026-09-15T03:00:00Z",
        timeout=7.0,
    )

    assert actual == packet
    assert observed["cwd"] == repo
    argv = observed["argv"]
    assert argv[0] == str(python)
    assert argv[1:3] == ["-I", "-B"]
    assert argv[3] == str(repo / "scripts" / "ceo_boot_packet.py")
    assert argv[argv.index("--repo-root") + 1] == str(repo)
    assert argv[argv.index("--macro-root") + 1] == str(macro)
    assert argv[argv.index("--now") + 1] == "2026-09-15T03:00:00Z"
    assert argv[argv.index("--timeout") + 1] == "7"


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
        packet_python=python, packet_runner=runner,
    )
    assert isinstance(readers._packet_builder, InstalledBootPacketCollector)


def test_installed_boot_packet_collector_has_bounded_default_subprocess_runner(tmp_path: Path):
    import sys
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    repo = tmp_path / "mastermind"
    macro = tmp_path / "macro"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    macro.mkdir()
    script = scripts / "ceo_boot_packet.py"
    script.write_text(
        "import json,sys\n"
        "def arg(name): return sys.argv[sys.argv.index(name)+1]\n"
        "repo=arg('--repo-root'); macro=arg('--macro-root')\n"
        "print(json.dumps({'schema':'mastermind.ceo_boot_packet.v1','generated_at':'2026-09-15T03:00:00Z',"
        "'mastermind':{'root':repo,'sha':'a'*40,'branch':'HEAD'},"
        "'macro':{'root':macro,'sha':'b'*40,'resolved_via':'flag','candidates_tried':[]},"
        "'strategic_state':{},'brief':{},'handoffs':[],'degraded':[],'next_recommended_act':'continue'}))\n",
        encoding="utf-8",
    )
    collector = InstalledBootPacketCollector(
        source_root=repo,
        macro_root=macro,
        python_executable=Path(sys.executable),
    )
    packet = collector(
        repo_root=repo,
        macro_root_flag=str(macro),
        now="2026-09-15T03:00:00Z",
        timeout=5.0,
    )

    assert packet["mastermind"]["root"] == str(repo)
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
    def runner(_argv, **_kwargs):
        return {
            "code": 0, "stdout": json.dumps(packet), "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, python_executable=python, runner=runner,
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

    def runner(argv, **_kwargs):
        observed["argv"] = list(argv)
        return {
            "code": 0, "stdout": json.dumps(packet), "stderr": "",
            "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro,
        python_executable=configured_python, runner=runner,
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
