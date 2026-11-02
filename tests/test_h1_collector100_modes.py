"""Hermetic 100-member/one-collector H1 source contract; no live host effects."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
CANDIDATE = NATIVE / "candidate"
ROLLOUT = NATIVE / "rollout"
HOST = CANDIDATE / "host_pull.sh"
DAEMON = CANDIDATE / "host_pull_daemon.sh"
PLIST = CANDIDATE / "host_pull_launchd.plist.template"


def test_fused_native_manifest_exact_100_sha_and_f1_r28():
    manifest = json.loads((ROLLOUT / "native-manifest.json").read_text())
    inventory = json.loads((ROLLOUT / "native-source-inventory.json").read_text())
    assert len(manifest) == inventory["native_code_files"] == len(inventory["files"]) == 100
    assert manifest["ext/pick.py"] == "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b"
    assert manifest["pool"] == "12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679"
    for name in ("host_pull_daemon.sh", "host_pull_launchd.plist.template", "paid_initializer.py",
                 "paid_initializer_nested_data.py", "paid_initializer_token_data.py"):
        relative = "ext/" + name
        raw = (CANDIDATE / name).read_bytes()
        assert manifest[relative] == hashlib.sha256(raw).hexdigest()
        assert inventory["files"][relative]["source"] == "candidate/" + name
        assert inventory["files"][relative]["installed_preimage_sha256"] is None
    assert "host_pull_launchd.plist.template" in inventory["new_code_files"]
    assert "paid_initializer.py" in inventory["new_code_files"]


def test_single_launchd_argv_is_fixed_and_matches_pinned_renderer():
    argv = plistlib.loads(PLIST.read_bytes())["ProgramArguments"]
    assert argv == ["/usr/bin/lockf", "-t", "0", "__LOCK__", "/bin/bash", "__HOST_PULL__",
                    "--qualification-mode", "__QUALIFICATION_MODE__"]
    body = DAEMON.read_text()
    assert hashlib.sha256(PLIST.read_bytes()).hexdigest() in body
    assert '"__QUALIFICATION_MODE__": mode' in body
    assert 'expected_argv()' in body and '--qualification-mode "$QUALIFICATION_MODE"' in body
    assert 'exec "$LOCKF" -t 0 "$LOCK" /bin/bash "$PIN" --qualification-mode "$QUALIFICATION_MODE"' in body
    assert 'die 78 "qualified recurring context unavailable"' in body
    assert 'advance_selector' in body and 'rollback_advanced_selector' in body
    assert plistlib.loads(PLIST.read_bytes())["Label"] == "com.mastermind.host-pull"


def fixture(tmp_path):
    """Only a scratch backend and fake perl transport, never real SSH/producer."""
    stage = tmp_path / "source"
    stage.mkdir()
    shutil.copyfile(HOST, stage / "host_pull.sh")
    (stage / "host_pull_probe.template").write_text(":\n")
    (stage / "hosts.json").write_text('{}\n')
    (stage / "host_pull_backend.py").write_text('''import json,sys
mode=sys.argv[1]
if mode=='read-hosts':
    pass
elif mode=='physical-diagnostic-prepare':
    assert sys.argv[3]=='ubuntu0';print('opaque-fixture-alias');print(':')
elif mode=='physical-diagnostic-result':
    raw=sys.stdin.read(256)
    assert 'FIXED_PHYSICAL_DATA' in raw
    print(json.dumps({'status':'OBSERVED','physical_only':True},sort_keys=True))
else:
    raise SystemExit(78)
''')
    tools = tmp_path / "bin"
    tools.mkdir()
    perl = tools / "perl"
    perl.write_text('#!/bin/sh\nprintf "%s\\n" "FIXED_PHYSICAL_DATA"\n')
    perl.chmod(0o755)
    env = dict(os.environ)
    env.update(PATH=str(tools) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
               HOST_PULL_HOSTS_JSON=str(stage / "hosts.json"),
               HOST_PULL_STATE_DIR=str(tmp_path / "disallowed-state"),
               HOST_PULL_PIDFILE=str(tmp_path / "disallowed-pid"))
    return stage / "host_pull.sh", env


def run(host, env, *args):
    return subprocess.run(["/bin/bash", str(host), *args], env=env, text=True,
                          capture_output=True, timeout=8)


def test_physical_mode_one_pass_keeps_legacy_loop_and_no_readiness_publication(tmp_path):
    host, env = fixture(tmp_path)
    result = run(host, env, "--qualification-mode", "physical-only", "--once")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "OBSERVED", "physical_only": True}
    assert not list((tmp_path / "disallowed-state").glob("*.json"))
    assert not (tmp_path / "disallowed-pid").exists()
    text = HOST.read_text()
    assert 'pass_once\n  PASS_RC=$?' in text
    assert 'if [ "$QUALIFICATION_MODE" = "physical-only" ]; then' in text


@pytest.mark.parametrize('args', [
    ("--qualification-mode", "unknown", "--once"),
    ("--qualification-mode",),
    ("--qualification-mode", "physical-only", "--qualification-mode", "physical-only", "--once"),
    ("--qualification-mode", "qualified-readiness", "--once"),
])
def test_invalid_or_unqualified_mode_refuses_before_any_probe(tmp_path, args):
    host, env = fixture(tmp_path)
    result = run(host, env, *args)
    assert result.returncode == 78, result.stderr
    assert not list((tmp_path / "disallowed-state").glob("*.json"))
    assert not (tmp_path / "disallowed-pid").exists()


def test_legacy_mode_remains_explicit_and_no_qualification_effect(tmp_path):
    host, env = fixture(tmp_path)
    result = run(host, env, "--qualification-mode", "off", "--once")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not list((tmp_path / "disallowed-state").glob("*.json"))


def test_b12_nonempty_host_physical_mode_excludes_account_reads_even_on_failure(tmp_path):
    """One eligible remote host; all transport/backend effects are scratch stubs."""
    host, env = fixture(tmp_path)
    stage = host.parent
    sentinel = tmp_path / "forbidden-account-probe"
    capture = tmp_path / "probe-capture"
    env["B12_SENTINEL"] = str(sentinel)
    env["B12_CAPTURE"] = str(capture)
    (stage / "glm_host_account_probe.py").write_text(
        "import os,pathlib\n"
        "pathlib.Path(os.environ['B12_SENTINEL']).write_text('read')\n"
        "print('FORBIDDEN_PROVIDER_READINESS=known')\n")
    (stage / "host_pull_backend.py").write_text(r'''import json, sys
from pathlib import Path
action = sys.argv[1]
if action == "read-hosts":
    print("ubuntu0|0|fixture-ssh|/worktrees|" +
          ("0" if sys.argv[-1] == "--physical-only" else "1"))
elif action == "write-state":
    if len(sys.argv) != 8 or sys.argv[7] != "physical-only":
        raise SystemExit(78)
    raw = sys.argv[5]
    if "FORBIDDEN_PROVIDER_READINESS" in raw:
        raise SystemExit(78)
    good = (sys.argv[4] == "0" and "PHYSICAL_EXIT 0" in raw
            and "load1=0.25" in raw and "ncpu=4" in raw)
    directory = Path(sys.argv[2])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (sys.argv[3] + ".json")).write_text(
        json.dumps({"host": sys.argv[3], "reachable": good,
                    "load1": 0.25 if good else None, "ncpu": 4 if good else None}))
    print("physical-only-census")
elif action == "physical-diagnostic-prepare":
    print("fixture-ssh")
    print(":")
elif action == "physical-diagnostic-result":
    print('{"status":"DIAGNOSTIC_ONLY","readiness":"NOT_REQUESTED"}')
else:
    raise SystemExit(78)
''')
    fake = tmp_path / "bin" / "perl"
    fake.write_text(r'''#!/bin/sh
cat > "$B12_CAPTURE"
printf '%s\n' 'HOST_PULL_STAGE_V1 PHYSICAL_BEGIN' 'load1=0.25' 'ncpu=4'
if [ "$B12_FAIL_PHYSICAL" = "1" ]; then
    printf '%s\n' 'HOST_PULL_STAGE_V1 PHYSICAL_EXIT 1' \
        'HOST_PULL_STAGE_V1 READINESS_BEGIN' 'HOST_PULL_STAGE_V1 READINESS_EXIT 0'
    exit 1
fi
printf '%s\n' 'HOST_PULL_STAGE_V1 PHYSICAL_EXIT 0' \
    'HOST_PULL_STAGE_V1 READINESS_BEGIN' 'HOST_PULL_STAGE_V1 READINESS_EXIT 0'
''')
    fake.chmod(0o755)
    for failed in (False, True):
        child_env = dict(env, B12_FAIL_PHYSICAL="1" if failed else "0")
        result = run(host, child_env, "--qualification-mode", "physical-only", "--once")
        assert result.returncode == 0, result.stderr
        assert not sentinel.exists()
        assert "FORBIDDEN_PROVIDER_READINESS" not in capture.read_text()
        doc = json.loads((tmp_path / "disallowed-state" / "ubuntu0.json").read_text())
        assert doc["reachable"] is not failed
        assert "glm_local_account_readiness" not in doc
        assert "bailian_local_account_readiness" not in doc
