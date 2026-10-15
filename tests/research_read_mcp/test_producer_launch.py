"""Real isolated child processes; fake producer source never opens a real Store."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ops.research_producer import launch
from integrations.research_read_mcp.runtime import RuntimeRefused


def fixture(tmp_path, *, output=None, rc=0):
    root = tmp_path.resolve()
    mm, macro = root / ("a" * 40), root / ("b" * 40)
    source = Path(launch.__file__).parents[2]
    files = {"integrations/__init__.py": b""}
    for name in ("__init__.py", "runtime.py", "release_identity.py"):
        rel = "integrations/research_read_mcp/" + name
        files[rel] = (source / rel).read_bytes()
    files[launch.MODULE] = (source / launch.MODULE).read_bytes()
    if output is None:
        output = "PRIVATE_SYNTHETIC_BODY\ningest_research: original_capture_sha256=" + "c" * 64 + "\n"
    script = ("import json,pathlib,sys,tempfile\n"
              "def main():\n"
              " p=pathlib.Path(sys.argv[sys.argv.index('--generation-evidence-path')+1])\n"
              " (p.parent/'observed.json').write_text(json.dumps(sys.argv))\n"
              " (p.parent/'temp-path.txt').write_text(tempfile.gettempdir())\n"
              " print(" + repr(output) + ",end='',flush=True)\n"
              " return " + str(rc) + "\n")
    manifest = {
        "schema": "mastermind.research_read_stage.v1", "state": "INERT_CANDIDATE",
        "mastermind_commit": "a" * 40, "mastermind_tree": "d" * 40,
        "macro_commit": "b" * 40, "macro_tree": "e" * 40,
        "dependency_lock_sha256": "f" * 64, "macro_import_closure": "OWNER_QUALIFICATION_REQUIRED",
        "files": [], "members": {},
    }
    for project, release, entries in (("mastermind", mm, files),
                                     ("macro", macro, {"scripts/ingest_research.py": script.encode()})):
        rows = []
        for name, raw in entries.items():
            path = release / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            rows.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        manifest["members"][project] = rows
    path = root / "manifest.json"
    raw = json.dumps(manifest).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    for name in ("retention", "checkout", "runner"):
        (root / name).mkdir(mode=0o700)
    config = {"schema": launch.SCHEMA, "mastermind_release": str(mm),
              "macro_release": str(macro), "manifest_path": str(path),
              "manifest_sha256": hashlib.sha256(raw).hexdigest(),
              "retention_root": str(root / "retention"),
              "public_checkout": str(root / "checkout"), "runner_work_root": str(root / "runner")}
    config.update({key: manifest[key] for key in
                   ("macro_commit", "macro_tree", "mastermind_commit", "mastermind_tree")})
    return config


def test_default_preflight_is_readonly_and_not_admission(tmp_path, monkeypatch, capsys):
    config = fixture(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    before = set(tmp_path.rglob("*"))
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *_a, **_k: pytest.fail("child started"))
    assert launch.main(["--config", str(config_path), "--run-id", "123", "--attempt", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "INERT_PRODUCER_PLAN" and result["writer_admission"] is False
    assert set(tmp_path.rglob("*")) == before
    assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize("mode", ["preflight", "execute", "changed_source"])
def test_standalone_isolated_entry_uses_own_release_from_foreign_cwd(tmp_path, mode):
    config = fixture(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    foreign = tmp_path / "foreign-cwd"
    foreign.mkdir()
    hostile = foreign / "integrations"
    hostile.mkdir()
    (hostile / "__init__.py").write_text("raise RuntimeError('FOREIGN_IMPORT_EXECUTED')\n")
    environment = dict(os.environ, PYTHONPATH=str(foreign))
    environment.pop("RESEARCH_LOCAL_STORE", None)
    entry = Path(config["mastermind_release"]) / launch.MODULE
    if mode == "changed_source":
        (Path(config["macro_release"]) / "scripts/ingest_research.py").write_text(
            "raise RuntimeError('CHANGED_PRODUCER_EXECUTED')\n")
    command = [sys.executable, "-I", "-B", str(entry), "--config", str(config_path),
               "--run-id", "456", "--attempt", "1"]
    if mode != "preflight":
        command.append("--execute")
    before = set(tmp_path.rglob("*"))
    result = subprocess.run(command, cwd=foreign, env=environment, capture_output=True,
                            text=True, timeout=30)
    assert result.stderr == ""
    body = json.loads(result.stdout)
    assert "PRIVATE_SYNTHETIC_BODY" not in result.stdout
    assert "FOREIGN_IMPORT_EXECUTED" not in result.stdout
    if mode == "execute":
        assert result.returncode == 0 and body["state"] == "ORIGINAL_PROCESS_EXITED"
        assert body["original_capture_sha256"] == "c" * 64
        assert body["publication_complete"] is None
        assert (Path(config["retention_root"]) / "macro-456-1/observed.json").is_file()
    else:
        assert set(tmp_path.rglob("*")) == before
        assert result.returncode == (1 if mode == "changed_source" else 0)
        assert body["state"] == ("REFUSED" if mode == "changed_source" else "INERT_PRODUCER_PLAN")
    assert not list(tmp_path.rglob("*.pyc"))


@pytest.mark.parametrize("run,attempt", [("../x", "1"), ("1", "0"), (" 1", "1"),
                                         (1, "1"), ("1", True), ("01", "1"),
                                         ("1", "1\n"), ("9" * 21, "1")])
def test_run_identity_refuses_before_reservation(tmp_path, run, attempt):
    config = fixture(tmp_path)
    with pytest.raises(RuntimeRefused):
        launch.execute(config, run, attempt)
    assert not list(Path(config["retention_root"]).iterdir())


@pytest.mark.parametrize("change", ["retention_public", "retention_runner", "source_overlap",
                                    "private_mode", "symlink", "unknown", "bad_digest", "source_change"])
def test_unsafe_placement_or_source_cannot_execute(tmp_path, change, monkeypatch):
    config = fixture(tmp_path)
    retention = Path(config["retention_root"])
    if change == "retention_public":
        config["retention_root"] = config["public_checkout"]
    elif change == "retention_runner":
        config["retention_root"] = config["runner_work_root"]
    elif change == "source_overlap":
        config["public_checkout"] = config["macro_release"]
    elif change == "private_mode":
        retention.chmod(0o755)
    elif change == "symlink":
        link = tmp_path / "link"
        link.symlink_to(retention)
        config["retention_root"] = str(link)
    elif change == "unknown":
        config["admitted"] = True
    elif change == "bad_digest":
        config["manifest_sha256"] = "0" * 64
    elif change == "source_change":
        (Path(config["macro_release"]) / "scripts/ingest_research.py").write_text("raise AssertionError('UNPINNED')")
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *_a, **_k: pytest.fail("child started"))
    with pytest.raises(RuntimeRefused):
        launch.execute(config, "123", "1")
    assert not list(retention.iterdir())


def test_space_refuses_no_cleanup_or_start(tmp_path, monkeypatch):
    config = fixture(tmp_path)
    from collections import namedtuple
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(launch.shutil, "disk_usage", lambda _: usage(10, 9, 1))
    with pytest.raises(RuntimeRefused, match="RETENTION_SPACE"):
        launch.execute(config, "123", "1")
    assert not list(Path(config["retention_root"]).iterdir())


def test_real_child_uses_pin_and_keeps_private_output(tmp_path, capsys, monkeypatch):
    config = fixture(tmp_path)
    monkeypatch.delenv("RESEARCH_LOCAL_STORE", raising=False)
    result = launch.execute(config, "123", "1")
    run = Path(config["retention_root"]) / "macro-123-1"
    assert result["exit_code"] == 0 and result["original_capture_sha256"] == "c" * 64
    assert result["publication_complete"] is None and result["recovery_authorized"] is False
    args = json.loads((run / "observed.json").read_text())
    assert args[0] == config["macro_release"] + "/scripts/ingest_research.py"
    assert args[args.index("--generation-source-commit") + 1] == config["macro_commit"]
    assert args[args.index("--generation-run") + 1] == "github:mastermindx-market-intelligence/macro:123:1"
    assert args[args.index("--repo-dir") + 1] == config["public_checkout"] + "/data/research_vault"
    assert "PRIVATE_SYNTHETIC_BODY" in (run / "output.log").read_text()
    assert capsys.readouterr().out == ""
    assert (run / "temp-path.txt").read_text() == str(run / "tmp")
    assert (run / "tmp").stat().st_mode & 0o777 == 0o700
    assert run.stat().st_mode & 0o777 == 0o700
    for name in ("output.log", "launch.json", "process-result.json"):
        assert (run / name).stat().st_mode & 0o777 == 0o600
    assert not list(Path(config["mastermind_release"]).rglob("*.pyc"))
    assert not list(Path(config["macro_release"]).rglob("*.pyc"))
    original = (run / "output.log").read_bytes()
    with pytest.raises(RuntimeRefused, match="ORIGINAL_RUN_EXISTS"):
        launch.execute(config, "123", "1")
    assert (run / "output.log").read_bytes() == original


@pytest.mark.parametrize("output,rc,capture", [
    ("no capture\n", 0, None),
    ("ingest_research: original_capture_sha256=" + "c" * 64, 0, None),
    (("ingest_research: original_capture_sha256=" + "c" * 64 + "\n") * 2, 0, None),
    ("ingest_research: original_capture_sha256=" + "c" * 64 + "\n", 73, "c" * 64),
])
def test_capture_never_invents_completion(tmp_path, output, rc, capture, monkeypatch):
    config = fixture(tmp_path, output=output, rc=rc)
    monkeypatch.delenv("RESEARCH_LOCAL_STORE", raising=False)
    result = launch.execute(config, "321", "2")
    assert result["exit_code"] == rc and result["original_capture_sha256"] == capture
    assert result["publication_complete"] is None


def test_executor_reverifies_after_parent_preflight(tmp_path, monkeypatch):
    config = fixture(tmp_path)
    original = launch.subprocess.Popen
    def mutate_then_start(*args, **kwargs):
        (Path(config["macro_release"]) / "scripts/ingest_research.py").write_text("raise SystemExit(0)")
        return original(*args, **kwargs)
    monkeypatch.setattr(launch.subprocess, "Popen", mutate_then_start)
    result = launch.execute(config, "123", "1")
    assert result["exit_code"] != 0 and result["original_capture_sha256"] is None
    assert not (Path(config["retention_root"]) / "macro-123-1/observed.json").exists()


def test_environment_local_store_cannot_redirect_production(tmp_path, monkeypatch):
    config = fixture(tmp_path)
    monkeypatch.setenv("RESEARCH_LOCAL_STORE", str(tmp_path / "unadmitted"))
    result = launch.execute(config, "123", "1")
    assert result["exit_code"] != 0 and result["original_capture_sha256"] is None
    assert not (tmp_path / "unadmitted").exists()


def test_output_limit_keeps_original_exit_and_suppresses_capture(tmp_path, monkeypatch):
    config = fixture(tmp_path)
    monkeypatch.delenv("RESEARCH_LOCAL_STORE", raising=False)
    monkeypatch.setattr(launch, "MAX_LOG_BYTES", 1)
    result = launch.execute(config, "123", "1")
    assert result["exit_code"] == 0 and result["output_bound_exceeded"] is True
    assert result["original_capture_sha256"] is None
    run = Path(config["retention_root"]) / "macro-123-1"
    assert (run / "observed.json").exists() and (run / "output.log").stat().st_size <= 1


def test_config_errors_do_not_leak_paths(tmp_path, capsys):
    assert launch.main(["--config", str(tmp_path / "PRIVATE_SECRET_PATH"),
                        "--run-id", "123", "--attempt", "1"]) == 1
    output = capsys.readouterr().out
    assert "PRIVATE_SECRET_PATH" not in output and "REFUSED" in output


def test_result_persistence_failure_is_not_a_prelaunch_refusal(tmp_path, monkeypatch, capsys):
    config = fixture(tmp_path)
    monkeypatch.delenv("RESEARCH_LOCAL_STORE", raising=False)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    path.chmod(0o600)
    original = launch._write_new
    def lose_result(path, data):
        if path.name == "process-result.json":
            raise OSError("PRIVATE_FAILURE_DETAIL")
        return original(path, data)
    monkeypatch.setattr(launch, "_write_new", lose_result)
    assert launch.main(["--config", str(path), "--run-id", "123", "--attempt", "1", "--execute"]) == 1
    value = json.loads(capsys.readouterr().out)
    assert value == {"state": "ORIGINAL_RUN_UNSETTLED",
                     "code": "PRODUCER_ORIGINAL_RUN_REQUIRES_RECONCILIATION"}
    run = Path(config["retention_root"]) / "macro-123-1"
    assert (run / "observed.json").exists() and (run / "output.log").exists()
    with pytest.raises(RuntimeRefused, match="ORIGINAL_RUN_EXISTS"):
        launch.execute(config, "123", "1")
