"""Hermetic tests for the host-pull publisher lifecycle candidate.

PATH fixtures replace launchctl, lockf, and ps. These tests never call the
real launchctl, the real lockf, the real ps, or the original host_pull
collector.

The candidate under test is not an installable sealed generation. The plist
template is refused by native_generation.file_name(), and these tests do not
admit it to the 95-member manifest.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import stat
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "ops/native_fabric/quota_continuity/candidate/host_pull_daemon.sh"
TEMPLATE = (
    ROOT / "ops/native_fabric/quota_continuity/candidate/launchd"
    / "com.mastermind.host-pull.plist.template"
)
PUBLISHER = ROOT / "ops/native_fabric/quota_continuity/rollout/native_generation.py"
ORIGINAL_HOST_PULL = ROOT / "ops/native_fabric/quota_continuity/candidate/host_pull.sh"
LABEL = "com.mastermind.host-pull"
SERVICE_PATH = "/usr/bin:/bin"


def load_generation():
    spec = importlib.util.spec_from_file_location(
        "host_pull_lifecycle_generation", PUBLISHER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATION = load_generation()


def _chmod_tree(root):
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        os.chmod(directory, 0o700)
        for name in list(dirnames):
            path = os.path.join(directory, name)
            if os.path.islink(path):
                dirnames.remove(name)
        for name in filenames:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                os.chmod(path, 0o700)


@pytest.fixture
def workspace(tmp_path):
    try:
        yield tmp_path
    finally:
        _chmod_tree(tmp_path)


def publish(workspace, body, select_expect=None):
    kit = workspace / "kit"
    ext = kit / "ext"
    ext.mkdir(parents=True, exist_ok=True)
    source = workspace / ("source-" + hashlib.sha256(body).hexdigest()[:8])
    if source.exists():
        source = workspace / (source.name + "-b")
    (source / "ext").mkdir(parents=True)
    (source / "pool").write_bytes(b"#!/bin/bash\nexit 0\n")
    (source / "ext" / "fabric_task.py").write_bytes(b"raise SystemExit(0)\n")
    (source / "ext" / "remote_sub.sh").write_bytes(b"#!/bin/bash\nexit 0\n")
    (source / "ext" / "host_pull.sh").write_bytes(body)
    files = {"pool": GENERATION.digest((source / "pool").read_bytes())}
    for path in (source / "ext").iterdir():
        files["ext/" + path.name] = GENERATION.digest(path.read_bytes())
    release = GENERATION.publish(source, ext, files)
    store = release.parent
    current = GENERATION.current(store)
    previous = current["generation"] if current else None
    if select_expect is not False:
        GENERATION.select(store, release.name, previous if select_expect is None else select_expect)
    return store, release


def write_stubs(bin_dir, state):
    bin_dir.mkdir()
    state.mkdir()
    launchctl = bin_dir / "launchctl"
    launchctl.write_text(r"""#!/bin/sh
set -u
printf '%s\n' "$*" >> "$STUB_STATE/launchctl.log"
cmd=$1
mode=$(cat "$STUB_STATE/print-mode" 2>/dev/null || echo absent)
style=$(cat "$STUB_STATE/print-style" 2>/dev/null || echo v1)
pid=$(cat "$STUB_STATE/pid" 2>/dev/null || echo 4242)
print_running() {
  if [ "$style" = "production" ]; then
    printf 'gui/501/com.mastermind.host-pull = {\n'
    printf '\tstate = running\n'
    printf '\targuments = {\n'
    while IFS= read -r arg; do
      printf '\t\t%s\n' "$arg"
    done < "$STUB_STATE/argv"
    printf '\t}\n'
    printf '\tpid = %s\n' "$pid"
    printf '}\n'
    return 0
  fi
  printf 'HOST_PULL_LAUNCHCTL_V1\n'
  printf 'state=loaded\n'
  printf 'activity=running\n'
  printf 'pid=%s\n' "$pid"
  while IFS= read -r arg; do
    printf 'argv=%s\n' "$arg"
  done < "$STUB_STATE/argv"
}
case "$cmd" in
  print)
    case "$style" in
      garbage)
        printf 'hello\n'
        exit 0
        ;;
      bad-exit)
        printf 'launchctl failed\n' >&2
        exit 9
        ;;
      not-found-noise)
        printf 'helper: file not found\n' >&2
        exit 9
        ;;
      wrong-label)
        printf 'Could not find service "com.other.job" in domain for user gui: 501\n' >&2
        exit 113
        ;;
      not-found-extra)
        printf 'Could not find service "com.mastermind.host-pull" in domain for user gui: 501\n' >&2
        printf 'also not found\n' >&2
        exit 113
        ;;
      bare-not-running)
        printf '\tstate = not running\n'
        exit 0
        ;;
      running-not-found)
        printf 'gui/501/com.mastermind.host-pull = {\n'
        printf '\tstate = running\n'
        printf '\targuments = {\n'
        printf '\t\t/bin/bash\n'
        printf '\t}\n'
        printf '\tpid = %s\n' "$pid"
        printf '\tnote = not found\n'
        printf '}\n'
        exit 0
        ;;
    esac
    if [ "$mode" = "running" ]; then
      print_running
      exit 0
    fi
    if [ "$mode" = "idle" ]; then
      printf 'gui/501/com.mastermind.host-pull = {\n'
      printf '\tstate = not running\n'
      printf '\targuments = {\n'
      printf '\t\t/bin/bash\n'
      printf '\t\t/old/generation/ext/host_pull.sh\n'
      printf '\t}\n'
      printf '}\n'
      exit 0
    fi
    if [ "$mode" = "absent" ] || [ "$mode" = "stopped" ]; then
      printf 'Bad request.\nCould not find service "%s" in domain for user gui: 501\n' com.mastermind.host-pull >&2
      exit 113
    fi
    printf 'unrecognized stub mode\n' >&2
    exit 78
    ;;
  bootout)
    if [ -f "$STUB_STATE/pause-bootout" ]; then
      : > "$STUB_STATE/bootout-entered"
      while [ -f "$STUB_STATE/pause-bootout" ]; do
        sleep 0.05
      done
    fi
    # Nonzero after the label has already transitioned. The daemon must not
    # retry bootout or follow this with bootstrap.
    if [ -f "$STUB_STATE/bootout-fail-after-effect" ]; then
      if [ ! -f "$STUB_STATE/bootout-keep-alive" ]; then
        rm -f "$STUB_STATE/ps-alive"
      fi
      printf 'absent\n' > "$STUB_STATE/print-mode"
      exit 1
    fi
    if [ -f "$STUB_STATE/bootout-rc" ]; then
      exit "$(cat "$STUB_STATE/bootout-rc")"
    fi
    if [ ! -f "$STUB_STATE/bootout-keep-alive" ]; then
      rm -f "$STUB_STATE/ps-alive"
    fi
    printf 'absent\n' > "$STUB_STATE/print-mode"
    exit 0
    ;;
  bootstrap)
    left=0
    if [ -f "$STUB_STATE/bootstrap-fail-left" ]; then
      left=$(cat "$STUB_STATE/bootstrap-fail-left")
    fi
    if [ "$left" -gt 0 ]; then
      printf '%s\n' "$((left - 1))" > "$STUB_STATE/bootstrap-fail-left"
      exit 1
    fi
    printf 'running\n' > "$STUB_STATE/print-mode"
    printf '5151\n' > "$STUB_STATE/pid"
    : > "$STUB_STATE/ps-alive"
    exit 0
    ;;
  *)
    printf 'unexpected launchctl\n' >&2
    exit 78
    ;;
esac
""")
    ps = bin_dir / "ps"
    ps.write_text(r"""#!/bin/sh
set -u
printf '%s\n' "$*" >> "$STUB_STATE/ps.log"
# The pre-bootout liveness check must not block. Pause only the wait that
# follows a recorded bootout, which is the old pid actually exiting.
if [ -f "$STUB_STATE/pause-pid" ] && grep -q '^bootout ' "$STUB_STATE/launchctl.log" 2>/dev/null; then
  : > "$STUB_STATE/ps-entered"
  while [ -f "$STUB_STATE/pause-pid" ]; do
    sleep 0.05
  done
fi
if [ -f "$STUB_STATE/ps-uncertain" ]; then
  printf 'ps uncertain\n' >&2
  exit 2
fi
if [ -f "$STUB_STATE/ps-alive" ]; then
  printf '%s\n' "$2"
  exit 0
fi
exit 1
""")
    lockf = bin_dir / "lockf"
    lockf.write_text(r"""#!/bin/sh
set -u
printf '%s\n' "$*" >> "$STUB_STATE/lockf.log"
if [ "$1" != "-t" ] || [ "$2" != "0" ]; then
  printf 'bad lockf invocation\n' >&2
  exit 78
fi
lock=$3
shift 3
if ! mkdir "$lock.d" 2>/dev/null; then
  exit 75
fi
printf '%s\n' "$@" > "$STUB_STATE/lockf.args"
if [ -n "${LOCKF_HOLD_FILE:-}" ]; then
  : > "${LOCKF_HOLD_FILE}.acquired"
  while [ -f "$LOCKF_HOLD_FILE" ]; do
    sleep 0.05
  done
fi
rmdir "$lock.d" 2>/dev/null || true
exit 0
""")
    for path in (launchctl, ps, lockf):
        path.chmod(0o755)
    (state / "print-mode").write_text("stopped\n")
    (state / "print-style").write_text("v1\n")
    (state / "pid").write_text("4242\n")
    (state / "argv").write_text("/bin/bash\n/old/ext/host_pull.sh\n")
    (state / "launchctl.log").write_text("")


def expected_argv(lock, pin):
    return "/usr/bin/lockf\n-t\n0\n" + str(lock) + "\n/bin/bash\n" + str(pin) + "\n"


def prepare(workspace, *, body=b"#!/bin/bash\nexit 91\n", select=True):
    store, release = publish(workspace, body, None if select else False)
    agents = workspace / "LaunchAgents"
    agents.mkdir()
    state = workspace / "state"
    state.mkdir()
    log = state / "host_pull.log"
    lock = state / "host_pull.lock"
    plist = agents / "com.mastermind.host-pull.plist"
    bin_dir = workspace / "bin"
    stub = workspace / "stub"
    write_stubs(bin_dir, stub)
    marker = workspace / "executed.txt"
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + ":/usr/bin:/bin"
    env["TMPDIR"] = str(workspace)
    env["HOME"] = str(workspace / "home")
    env["STUB_STATE"] = str(stub)
    env["HOST_PULL_WAS_EXECUTED"] = str(marker)
    (workspace / "home").mkdir()
    return {
        "store": store,
        "release": release,
        "pin": release / "ext" / "host_pull.sh",
        "plist": plist,
        "log": log,
        "lock": lock,
        "stub": stub,
        "env": env,
        "marker": marker,
        "backup": workspace / "com.mastermind.host-pull-plist-backups",
    }


def base_args(ctx, **extra):
    args = [
        "/bin/bash", str(DAEMON), extra.pop("command", "install-agent"),
        "--store", str(ctx["store"]),
        "--generation", ctx["release"].name,
        "--expect-current", extra.pop("expect", ctx["release"].name),
        "--publisher", str(extra.pop("publisher", PUBLISHER)),
        "--hermetic", "--fixture-root", str(ctx["env"]["PATH"].split(":")[0]),
    ]
    if args[2] == "install-agent":
        args.extend([
            "--plist", str(ctx["plist"]),
            "--log", str(ctx["log"]),
            "--lock", str(ctx["lock"]),
            "--service-path", SERVICE_PATH,
            "--backup-dir", str(ctx["backup"]),
            "--wait-limit", str(extra.pop("wait_limit", 5)),
        ])
    else:
        args.extend(["--lock", str(ctx["lock"])])
    for key, value in extra.items():
        flag = "--" + key.replace("_", "-")
        if value is True:
            args.append(flag)
        else:
            args.extend([flag, str(value)])
    return args


def run(ctx, **extra):
    return subprocess.run(
        base_args(ctx, **extra), env=ctx["env"], capture_output=True, text=True, timeout=15)


def launch_log(ctx):
    return (ctx["stub"] / "launchctl.log").read_text()


def assert_not_executed(ctx):
    assert not ctx["marker"].exists()
    assert ORIGINAL_HOST_PULL.is_file()


def test_bash_syntax_and_no_pidfile_race():
    subprocess.run(["/bin/bash", "-n", str(DAEMON)], check=True)
    text = DAEMON.read_text()
    assert "PIDFILE" not in text
    assert "echo $$" not in text
    assert "kill -0" not in text
    assert "$HERE/host_pull.sh" not in text
    template = TEMPLATE.read_text()
    for marker in ("__HOST_PULL__", "__STDOUT_LOG__", "__STDERR_LOG__", "__PATH__", "__LOCK__"):
        assert template.count(marker) == 1
    assert "__LOG__" not in template
    assert "com.mastermind.host-pull" in template


def test_stopped_publication_pins_only_verified_generation(workspace):
    ctx = prepare(workspace)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 0, result.stderr
    plist = plistlib.loads(ctx["plist"].read_bytes())
    assert plist["Label"] == LABEL
    assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
    assert plist["ProgramArguments"] == [
        "/usr/bin/lockf", "-t", "0", str(ctx["lock"]), "/bin/bash", str(ctx["pin"]),
    ]
    assert plist["StandardOutPath"] == plist["StandardErrorPath"] == str(ctx["log"])
    text = ctx["plist"].read_text()
    assert text.count("host_pull.sh") == 1
    assert str(ctx["pin"]) in text
    assert "/ext/host_pull.sh" in text
    assert "native-code-releases/" + ctx["release"].name + "/ext/host_pull.sh" in text
    log = launch_log(ctx)
    assert log.count("\nbootstrap ") == 1 or log.count("bootstrap ") == 1
    assert "bootout " not in log
    assert not (ctx["stub"] / "lockf.log").exists() or (ctx["stub"] / "lockf.log").read_text() == ""
    assert_not_executed(ctx)


def test_bootout_waits_for_old_pid_before_one_bootstrap(workspace):
    ctx = prepare(workspace)
    ctx["plist"].write_bytes(b"OLD-PLIST\n")
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "pause-pid").write_text("")
    (ctx["stub"] / "argv").write_text("/bin/bash\n/old/generation/ext/host_pull.sh\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    # The running job still advertises the old collector. The post-bootstrap
    # print uses the same argv file, which must then be the verified pin.
    (ctx["stub"] / "argv").write_text("/bin/bash\n/old/generation/ext/host_pull.sh\n")
    proc = subprocess.Popen(
        base_args(ctx), env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 5
    while time.time() < deadline and not (ctx["stub"] / "ps-entered").exists():
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise AssertionError(err or out)
        time.sleep(0.05)
    assert ctx["plist"].read_bytes() == b"OLD-PLIST\n"
    assert "bootstrap " not in launch_log(ctx)
    assert "bootout " in launch_log(ctx)
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    (ctx["stub"] / "pause-pid").unlink()
    out, err = proc.communicate(timeout=10)
    assert proc.returncode == 0, err
    assert ctx["plist"].read_bytes() != b"OLD-PLIST\n"
    assert launch_log(ctx).count("bootstrap ") == 1
    assert_not_executed(ctx)


def test_bootstrap_failure_restores_plist_and_is_not_green(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "bootstrap-fail-left").write_text("1\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "bootstrap failed" in result.stderr
    assert ctx["plist"].read_bytes() == original
    assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o600
    assert launch_log(ctx).count("bootstrap ") == 2
    backups = list(ctx["backup"].glob("com.mastermind.host-pull.plist.pre-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert_not_executed(ctx)


def test_rollback_bootstrap_failure_does_not_retry(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "bootstrap-fail-left").write_text("2\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "rollback bootstrap failed" in result.stderr
    assert ctx["plist"].read_bytes() == original
    assert launch_log(ctx).count("bootstrap ") == 2
    assert_not_executed(ctx)


def test_idempotent_when_already_pinned(workspace):
    ctx = prepare(workspace)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    first = run(ctx)
    assert first.returncode == 0, first.stderr
    pinned = ctx["plist"].read_bytes()
    (ctx["stub"] / "launchctl.log").write_text("")
    second = run(ctx)
    assert second.returncode == 0, second.stderr
    assert ctx["plist"].read_bytes() == pinned
    assert launch_log(ctx) == "" or "bootstrap " not in launch_log(ctx)
    assert "bootout " not in launch_log(ctx)
    assert_not_executed(ctx)


def test_disk_plist_drift_while_running_fails_closed(workspace):
    ctx = prepare(workspace)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    assert run(ctx).returncode == 0
    ctx["plist"].chmod(0o600)
    ctx["plist"].write_bytes(ctx["plist"].read_bytes() + b"\n")
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "launchctl.log").write_text("")
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "disagree" in result.stderr
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)


def test_uncertain_launchctl_or_ps_fails_closed(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("garbage\n")
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "uncertain" in result.stderr
    assert ctx["plist"].read_bytes() == original
    assert launch_log(ctx).count("bootstrap ") == 0
    assert "bootout " not in launch_log(ctx)

    (ctx["stub"] / "print-style").write_text("v1\n")
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-uncertain").write_text("")
    (ctx["stub"] / "launchctl.log").write_text("")
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "process state uncertain" in result.stderr
    assert "bootout " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    assert_not_executed(ctx)


def test_pid_that_does_not_exit_is_not_bootstrapped(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "bootout-keep-alive").write_text("")
    result = run(ctx, wait_limit=2)
    assert result.returncode == 78, result.stderr
    assert "old pid did not exit" in result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert ctx["plist"].read_bytes() == original
    assert "bootstrap " not in launch_log(ctx)
    assert "bootout " in launch_log(ctx)
    receipt = json.loads(next(ctx["backup"].glob("*.receipt")).read_text())
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert_not_executed(ctx)


def test_sha_symlink_and_alternate_generation_fail_closed(workspace):
    ctx = prepare(workspace)
    original = b"UNTOUCHED\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    pin = ctx["pin"]
    os.chmod(ctx["release"], 0o755)
    os.chmod(ctx["release"] / "ext", 0o755)
    pin.chmod(0o755)
    pin.write_bytes(pin.read_bytes() + b"# mutated\n")
    os.chmod(pin, 0o555)
    os.chmod(ctx["release"] / "ext", 0o555)
    os.chmod(ctx["release"], 0o555)
    mismatch = run(ctx)
    assert mismatch.returncode == 78, mismatch.stderr
    assert "digest" in mismatch.stderr or "verify" in mismatch.stderr
    assert ctx["plist"].read_bytes() == original
    assert "bootstrap " not in launch_log(ctx)

    os.chmod(ctx["release"], 0o755)
    os.chmod(ctx["release"] / "ext", 0o755)
    pin.unlink()
    pin.symlink_to(ctx["release"] / "ext" / "fabric_task.py")
    os.chmod(ctx["release"] / "ext", 0o555)
    os.chmod(ctx["release"], 0o555)
    linked = run(ctx)
    assert linked.returncode == 78, linked.stderr
    assert "symlink" in linked.stderr
    assert ctx["plist"].read_bytes() == original

    other_store_root = workspace / "other"
    other_store_root.mkdir()
    store2, release2 = publish(other_store_root, b"#!/bin/bash\nexit 92\n", select_expect=False)
    # publish() selects by default. Build a second generation in the SAME store
    # without selecting it, by publishing another body into the existing kit.
    _chmod_tree(ctx["release"])
    # The selected generation is still ctx; publish another into the same ext.
    second_body = b"#!/bin/bash\nexit 93\n"
    source = workspace / "source-alt"
    (source / "ext").mkdir(parents=True)
    (source / "pool").write_bytes(b"#!/bin/bash\nexit 0\n")
    (source / "ext" / "fabric_task.py").write_bytes(b"raise SystemExit(0)\n")
    (source / "ext" / "remote_sub.sh").write_bytes(b"#!/bin/bash\nexit 0\n")
    (source / "ext" / "host_pull.sh").write_bytes(second_body)
    # The first release directory is sealed. publish() of a new generation uses
    # the same stable ext and store and does not require the old generation to
    # be writable. Restore the sealed modes after the mutation above.
    os.chmod(ctx["release"], 0o555)
    os.chmod(ctx["release"] / "ext", 0o555)
    files = {"pool": GENERATION.digest((source / "pool").read_bytes())}
    for path in (source / "ext").iterdir():
        files["ext/" + path.name] = GENERATION.digest(path.read_bytes())
    alternate = GENERATION.publish(source, ctx["store"].parent / "ext", files)
    assert alternate.name != ctx["release"].name
    refused = run(ctx, generation=alternate.name, expect_current=alternate.name)
    assert refused.returncode == 78, refused.stderr
    assert "selected current" in refused.stderr
    assert ctx["plist"].read_bytes() == original
    assert_not_executed(ctx)
    assert store2
    assert release2.name


def test_owner_and_mode_checks_fail_closed(workspace):
    ctx = prepare(workspace)
    original = b"UNTOUCHED\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    pin = ctx["pin"]
    pin.chmod(0o644)
    mode = run(ctx)
    assert mode.returncode == 78, mode.stderr
    assert "mode" in mode.stderr
    assert ctx["plist"].read_bytes() == original
    pin.chmod(0o555)
    foreign = "0" if os.geteuid() != 0 else "1"
    owner = run(ctx, expect_owner_uid=foreign)
    assert owner.returncode == 78, owner.stderr
    assert "owner" in owner.stderr
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)


def test_publisher_verify_is_required(workspace):
    ctx = prepare(workspace)
    original = b"UNTOUCHED\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    liar = workspace / "native_generation.py"
    liar.write_text("import sys\nsys.exit(9)\n")
    refused = run(ctx, publisher=liar)
    assert refused.returncode == 78, refused.stderr
    assert "publisher verify failed" in refused.stderr
    assert ctx["plist"].read_bytes() == original

    log = workspace / "publisher.log"
    wrapper = workspace / "wrapped-native_generation.py"
    # Basename must be native_generation.py. Keep the wrapper in its own directory.
    wrapped_dir = workspace / "publisher"
    wrapped_dir.mkdir()
    wrapper = wrapped_dir / "native_generation.py"
    wrapper.write_text(
        "import os, sys\n"
        "open(os.environ['PUBLISHER_LOG'], 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "os.execv(sys.executable, [sys.executable, os.environ['REAL_PUBLISHER'], *sys.argv[1:]])\n")
    ctx["env"]["PUBLISHER_LOG"] = str(log)
    ctx["env"]["REAL_PUBLISHER"] = str(PUBLISHER)
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx, publisher=wrapper)
    assert result.returncode == 0, result.stderr
    recorded = log.read_text()
    assert "verify --store " in recorded
    assert ctx["release"].name in recorded
    assert_not_executed(ctx)


def test_program_override_and_user_launchagents_refused(workspace):
    ctx = prepare(workspace)
    refused = subprocess.run(
        base_args(ctx) + ["--program", str(ctx["pin"])],
        env=ctx["env"], capture_output=True, text=True, timeout=15)
    assert refused.returncode == 78
    assert "refused" in refused.stderr
    home_plist = Path(ctx["env"]["HOME"]) / "Library" / "LaunchAgents" / "com.mastermind.host-pull.plist"
    blocked = run(ctx, plist=home_plist)
    assert blocked.returncode == 78, blocked.stderr
    assert "LaunchAgents" in blocked.stderr
    assert not home_plist.exists()
    assert_not_executed(ctx)


def test_term_before_mutation_and_during_wait_and_before_bootstrap(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    hold = workspace / "hold-mutation"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_mutation=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ready = Path(str(hold) + ".ready")
    deadline = time.time() + 5
    while time.time() < deadline and not ready.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    out, err = proc.communicate(timeout=5)
    assert proc.returncode == 143, err
    assert ctx["plist"].read_bytes() == original
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)

    for sig, code in ((signal.SIGHUP, 129), (signal.SIGINT, 130)):
        (ctx["stub"] / "launchctl.log").write_text("")
        hold.write_text("")
        ready.unlink(missing_ok=True)
        proc = subprocess.Popen(
            base_args(ctx, hold_before_mutation=hold),
            env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.time() + 5
        while time.time() < deadline and not ready.exists():
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read())
            time.sleep(0.05)
        proc.send_signal(sig)
        _, err = proc.communicate(timeout=5)
        assert proc.returncode == code, err
        assert ctx["plist"].read_bytes() == original

    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "print-style").write_text("v1\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "pause-pid").write_text("")
    (ctx["stub"] / "launchctl.log").write_text("")
    proc = subprocess.Popen(
        base_args(ctx), env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 5
    while time.time() < deadline and not (ctx["stub"] / "ps-entered").exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    proc.send_signal(signal.SIGTERM)
    (ctx["stub"] / "pause-pid").unlink()
    _, err = proc.communicate(timeout=5)
    assert proc.returncode == 78, err
    assert ctx["plist"].read_bytes() == original
    assert "bootstrap " not in launch_log(ctx)

    (ctx["stub"] / "pause-pid").unlink(missing_ok=True)
    (ctx["stub"] / "ps-entered").unlink(missing_ok=True)
    (ctx["stub"] / "ps-alive").unlink(missing_ok=True)
    if ctx["backup"].exists():
        _chmod_tree(ctx["backup"])
        for child in ctx["backup"].iterdir():
            child.unlink()
    # The pid-wait signal abandoned the transaction. This next scenario is a
    # fresh absent install, so the crash marker is cleared with the rest of
    # the fixture. A real successor must leave that marker and fail closed.
    (ctx["store"] / ".install-transaction.marker").unlink(missing_ok=True)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "launchctl.log").write_text("")
    hold2 = workspace / "hold-bootstrap"
    hold2.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold2),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ready2 = Path(str(hold2) + ".ready")
    deadline = time.time() + 5
    while time.time() < deadline and not ready2.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    assert ctx["plist"].read_bytes() != original
    proc.send_signal(signal.SIGTERM)
    _, err = proc.communicate(timeout=5)
    assert proc.returncode == 78, err
    assert ctx["plist"].read_bytes() == original
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)


def test_lockf_contention_returns_75(workspace):
    ctx = prepare(workspace)
    env = ctx["env"].copy()
    hold = workspace / "lock-hold"
    hold.write_text("")
    env["LOCKF_HOLD_FILE"] = str(hold)
    first = subprocess.Popen(
        base_args(ctx, command="collect"),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    acquired = Path(str(hold) + ".acquired")
    deadline = time.time() + 5
    while time.time() < deadline and not acquired.exists():
        if first.poll() is not None:
            raise AssertionError(first.stderr.read())
        time.sleep(0.05)
    second = subprocess.run(
        base_args(ctx, command="collect"),
        env=env, capture_output=True, text=True, timeout=10)
    assert second.returncode == 75, second.stderr
    hold.unlink()
    out, err = first.communicate(timeout=5)
    assert first.returncode == 0, err
    recorded = (ctx["stub"] / "lockf.args").read_text().splitlines()
    assert recorded == ["/bin/bash", str(ctx["pin"])]
    assert "/usr/bin/lockf" not in recorded
    log = (ctx["stub"] / "lockf.log").read_text()
    assert "-t 0 " in log
    assert_not_executed(ctx)
    assert out == ""


def test_production_launchctl_print_shape_is_accepted(workspace):
    ctx = prepare(workspace)
    (ctx["stub"] / "print-style").write_text("production\n")
    (ctx["stub"] / "print-mode").write_text("absent\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 0, result.stderr
    plist = plistlib.loads(ctx["plist"].read_bytes())
    assert plist["ProgramArguments"][-1] == str(ctx["pin"])
    assert plist["EnvironmentVariables"]["PATH"] == SERVICE_PATH
    (ctx["stub"] / "launchctl.log").write_text("")
    second = run(ctx)
    assert second.returncode == 0, second.stderr
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)


def test_release_descriptor_fields_are_the_ones_verify_seals(workspace):
    ctx = prepare(workspace)
    release = json.loads((ctx["release"] / "RELEASE.json").read_text())
    assert release["schema"] == "native-code-generation.v1"
    assert release["digest"] == ctx["release"].name
    assert release["files"]["ext/host_pull.sh"] == hashlib.sha256(ctx["pin"].read_bytes()).hexdigest()
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == ctx["release"].name
    assert current["schema"] == "native-code-selection.v1"
    assert_not_executed(ctx)


def test_candidate_is_not_an_installable_sealed_member():
    daemon = DAEMON.read_text()
    template = TEMPLATE.read_text()
    for blob in (daemon, template):
        assert "native-policy integration gate" in blob
        assert "file_name()" in blob
    assert "95-member" in daemon
    assert "NOT INSTALLABLE" in daemon


def arm_running(ctx, workspace):
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "argv").write_text("/bin/bash\n/old/generation/ext/host_pull.sh\n")
    return original


def receipt_body(ctx):
    receipts = list(ctx["backup"].glob("*.receipt"))
    assert len(receipts) == 1
    return json.loads(receipts[0].read_text())


@pytest.mark.parametrize(
    ("fault", "outcome", "bootstraps", "snippet"),
    [
        ("wait-pid", "EFFECT_UNKNOWN", 0, "process state uncertain"),
        ("post-bootout-print", "EFFECT_UNKNOWN", 0, "launchctl state uncertain"),
        ("install-before-replace", "RECOVERED", 1, "recovered original service"),
        ("install-after-replace", "RECOVERED", 1, "recovered original service"),
        ("pre-bootstrap-print", "EFFECT_UNKNOWN", 0, "launchctl state uncertain"),
    ],
)
def test_post_bootout_fault_injection(workspace, fault, outcome, bootstraps, snippet):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    result = run(ctx, fault=fault)
    assert result.returncode == 78, result.stderr
    assert snippet in result.stderr
    assert ctx["plist"].read_bytes() == original
    assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o600
    assert launch_log(ctx).count("bootstrap ") == bootstraps
    assert launch_log(ctx).count("bootout ") == 1
    receipt = receipt_body(ctx)
    assert receipt["schema"] == "host-pull-lifecycle-receipt.v1"
    assert receipt["outcome"] == outcome
    if outcome == "EFFECT_UNKNOWN":
        assert "EFFECT_UNKNOWN" in result.stderr
        assert "recovered original service" not in result.stderr
        assert receipt["service"] == "stopped-uncertain"
    else:
        assert "recovered original service" in result.stderr
        assert receipt["service"] == "restored"
    assert_not_executed(ctx)


@pytest.mark.parametrize("style", [
    "not-found-noise",
    "wrong-label",
    "not-found-extra",
    "bare-not-running",
    "running-not-found",
])
def test_launchctl_lookalikes_fail_closed(workspace, style):
    ctx = prepare(workspace)
    original = b"UNTOUCHED\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text(style + "\n")
    if style == "running-not-found":
        (ctx["stub"] / "print-mode").write_text("running\n")
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "uncertain" in result.stderr
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    assert_not_executed(ctx)


def test_loaded_idle_is_booted_out_before_one_bootstrap(workspace):
    ctx = prepare(workspace)
    ctx["plist"].write_bytes(b"OLD-PLIST\n")
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("idle\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 0, result.stderr
    log = launch_log(ctx)
    assert log.index("bootout ") < log.index("bootstrap ")
    assert log.count("bootstrap ") == 1
    plist = plistlib.loads(ctx["plist"].read_bytes())
    assert plist["ProgramArguments"][-1] == str(ctx["pin"])
    assert_not_executed(ctx)


def test_publication_lock_blocks_select_during_bootout(workspace):
    ctx = prepare(workspace)
    arm_running(ctx, workspace)
    _store, other = publish(workspace, b"#!/bin/bash\nexit 92\n", False)
    (ctx["stub"] / "pause-bootout").write_text("")
    proc = subprocess.Popen(
        base_args(ctx), env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    entered = ctx["stub"] / "bootout-entered"
    deadline = time.time() + 8
    while time.time() < deadline and not entered.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    assert entered.exists()
    with pytest.raises(ValueError, match="native publication already in progress"):
        GENERATION.select(ctx["store"], other.name, ctx["release"].name)
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    (ctx["stub"] / "pause-bootout").unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 0, err
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == ctx["release"].name
    assert_not_executed(ctx)


def _move_selector(ctx, workspace):
    _store, other = publish(workspace, b"#!/bin/bash\nexit 92\n", False)
    assert _store == ctx["store"]
    GENERATION.select(ctx["store"], other.name, ctx["release"].name)
    return other


def _release_hold(proc, hold):
    ready = Path(str(hold) + ".ready")
    deadline = time.time() + 8
    while time.time() < deadline and not ready.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    assert ready.exists()
    return proc


def test_selector_move_before_bootout_does_not_bootout(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-bootout"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootout=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _release_hold(proc, hold)
    other = _move_selector(ctx, workspace)
    hold.unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "selector moved" in err
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    assert_not_executed(ctx)


def test_selector_move_before_plist_replace_restores_original_service(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-plist"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_plist=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _release_hold(proc, hold)
    assert "bootout " in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    other = _move_selector(ctx, workspace)
    hold.unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "selector moved" in err
    assert "recovered original service" in err
    assert ctx["plist"].read_bytes() == original
    assert launch_log(ctx).count("bootstrap ") == 1
    assert launch_log(ctx).count("bootout ") == 1
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "RECOVERED"
    assert receipt["service"] == "restored"
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    assert_not_executed(ctx)


def test_selector_move_before_bootstrap_restores_original_service(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-bootstrap"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _release_hold(proc, hold)
    assert ctx["plist"].read_bytes() != original
    assert "bootstrap " not in launch_log(ctx)
    other = _move_selector(ctx, workspace)
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    hold.unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "selector moved" in err
    assert "recovered original service" in err
    assert ctx["plist"].read_bytes() == original
    assert launch_log(ctx).count("bootstrap ") == 1
    assert launch_log(ctx).count("bootout ") == 1
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "RECOVERED"
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    assert_not_executed(ctx)


def test_bootout_nonzero_after_effect_is_effect_unknown(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    (ctx["stub"] / "bootout-fail-after-effect").write_text("")
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert "bootout failed" in result.stderr
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert receipt["phase"] == "BOOTOUT"
    assert ctx["plist"].read_bytes() == original
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert "bootstrap " not in log
    assert_not_executed(ctx)


def test_bootout_nonzero_without_effect_is_no_effect(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    (ctx["stub"] / "bootout-rc").write_text("1\n")
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "bootout had no effect" in result.stderr
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "NO_EFFECT"
    assert receipt["service"] == "still-loaded"
    assert receipt["phase"] == "BOOTOUT_NO_EFFECT"
    assert ctx["plist"].read_bytes() == original
    assert (ctx["stub"] / "print-mode").read_text().strip() == "running"
    assert (ctx["stub"] / "ps-alive").exists()
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert log.count("print ") == 2
    assert "bootstrap " not in log
    assert_not_executed(ctx)


def test_holder_death_before_effect_allows_select_and_does_not_mutate(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    _store, other = publish(workspace, b"#!/bin/bash\nexit 92\n", False)
    hold = workspace / "hold-lock"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_during_lock=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    holder = Path(str(hold) + ".holder")
    deadline = time.time() + 8
    while time.time() < deadline and not holder.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    assert holder.exists()
    pid = int(holder.read_text().strip())
    os.kill(pid, signal.SIGKILL)
    gone = time.time() + 8
    while time.time() < gone:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("lock holder still alive")
    GENERATION.select(ctx["store"], other.name, ctx["release"].name)
    hold.unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "EFFECT_UNKNOWN" in err
    assert "holder died" in err
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert "holder died" in receipt["reason"]
    assert_not_executed(ctx)


def test_holder_death_during_bootout_does_not_mutate_again(workspace):
    """The in-flight bootout can finish after the holder dies. The parent
    must not issue a second bootout or a bootstrap, and the receipt is
    EFFECT_UNKNOWN."""
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    _store, other = publish(workspace, b"#!/bin/bash\nexit 92\n", False)
    hold = workspace / "hold-lock"
    hold.write_text("")
    (ctx["stub"] / "pause-bootout").write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_during_lock=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    holder = Path(str(hold) + ".holder")
    deadline = time.time() + 8
    while time.time() < deadline and not holder.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    pid = int(holder.read_text().strip())
    hold.unlink()
    entered = ctx["stub"] / "bootout-entered"
    deadline = time.time() + 8
    while time.time() < deadline and not entered.exists():
        if proc.poll() is not None:
            raise AssertionError(proc.stderr.read())
        time.sleep(0.05)
    assert entered.exists()
    os.kill(pid, signal.SIGKILL)
    gone = time.time() + 8
    while time.time() < gone:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("lock holder still alive")
    GENERATION.select(ctx["store"], other.name, ctx["release"].name)
    (ctx["stub"] / "pause-bootout").unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "EFFECT_UNKNOWN" in err
    assert "bootout failed" in err
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert "bootstrap " not in log
    assert ctx["plist"].read_bytes() == original
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert receipt["phase"] == "BOOTOUT"
    assert_not_executed(ctx)


def _plist_backups(ctx):
    if not ctx["backup"].exists():
        return []
    return sorted(path.name for path in ctx["backup"].glob("com.mastermind.host-pull.plist.pre-*"))


def _wait_transaction_unlocked(ctx, timeout=3):
    lock = ctx["store"] / ".install-transaction.lock"
    deadline = time.time() + timeout
    while time.time() < deadline:
        fd = os.open(lock, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            time.sleep(0.05)
            continue
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return
        finally:
            os.close(fd)
    raise AssertionError("transaction lock still held")


def test_second_installer_makes_no_mutation_while_first_holds_transaction(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-plist"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_plist=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _release_hold(proc, hold)
    assert "bootout " in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    log_before = launch_log(ctx)
    backups_before = _plist_backups(ctx)
    assert backups_before
    other = run(ctx)
    assert other.returncode == 78, other.stderr
    assert "install transaction already in progress" in other.stderr
    assert launch_log(ctx) == log_before
    assert ctx["plist"].read_bytes() == original
    assert _plist_backups(ctx) == backups_before
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["phase"] == "INSTALL_CONTENTION"
    assert "already in progress" in receipt["reason"]
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    hold.unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 0, err
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert log.count("bootstrap ") == 1
    plist = plistlib.loads(ctx["plist"].read_bytes())
    assert plist["ProgramArguments"] == [
        "/usr/bin/lockf", "-t", "0", str(ctx["lock"]), "/bin/bash", str(ctx["pin"]),
    ]
    assert plist["ProgramArguments"].count("/bin/bash") == 1
    lockf_log = ctx["stub"] / "lockf.log"
    assert not lockf_log.exists() or lockf_log.read_text() == ""
    assert_not_executed(ctx)


def test_installer_crash_releases_mutex_and_next_fails_closed(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-plist"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_plist=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _release_hold(proc, hold)
    log_before = launch_log(ctx)
    backups_before = _plist_backups(ctx)
    assert "bootout " in log_before
    os.kill(proc.pid, signal.SIGKILL)
    proc.communicate(timeout=5)
    marker = ctx["store"] / ".install-transaction.marker"
    assert marker.is_file()
    _wait_transaction_unlocked(ctx)
    later = run(ctx)
    assert later.returncode == 78, later.stderr
    assert "install transaction incomplete" in later.stderr
    assert "already in progress" not in later.stderr
    assert launch_log(ctx) == log_before
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    assert _plist_backups(ctx) == backups_before
    assert (ctx["stub"] / "print-mode").read_text().strip() == "absent"
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert receipt["phase"] == "INSTALL_ABANDONED"
    assert marker.is_file()
    assert_not_executed(ctx)


def test_outliving_child_does_not_keep_transaction_lock(workspace):
    """Inert /bin/bash fixture: a descendant outlives the installer.

    It must not inherit the transaction descriptor. After the installer is
    killed, that descendant stays alive and the flock is releasable. The
    successor then fail-closes on the abandoned marker and does not mutate.
    """
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-plist"
    hold.write_text("")
    report = workspace / "descendant-report"
    proc = subprocess.Popen(
        base_args(ctx, hold_before_plist=hold, lock_descendant=report),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    desc_pid = None
    try:
        _release_hold(proc, hold)
        deadline = time.time() + 8
        while time.time() < deadline and not report.exists():
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read())
            time.sleep(0.05)
        fields = dict(line.split("=", 1) for line in report.read_text().splitlines())
        assert fields["inherited"] == "0"
        assert fields["fd9_open"] == "0"
        desc_pid = int(fields["pid"])
        os.kill(desc_pid, 0)
        log_before = launch_log(ctx)
        backups_before = _plist_backups(ctx)
        assert "bootout " in log_before
        assert "bootstrap " not in log_before
        blocked = run(ctx)
        assert blocked.returncode == 78, blocked.stderr
        assert "install transaction already in progress" in blocked.stderr
        assert launch_log(ctx) == log_before
        assert ctx["plist"].read_bytes() == original
        assert _plist_backups(ctx) == backups_before
        os.kill(proc.pid, signal.SIGKILL)
        proc.communicate(timeout=5)
        os.kill(desc_pid, 0)
        _wait_transaction_unlocked(ctx)
        os.kill(desc_pid, 0)
        later = run(ctx)
        assert later.returncode == 78, later.stderr
        assert "install transaction incomplete" in later.stderr
        assert "already in progress" not in later.stderr
        assert launch_log(ctx) == log_before
        assert "bootstrap " not in launch_log(ctx)
        assert ctx["plist"].read_bytes() == original
        assert _plist_backups(ctx) == backups_before
        os.kill(desc_pid, 0)
        assert_not_executed(ctx)
    finally:
        if desc_pid is not None:
            try:
                os.kill(desc_pid, signal.SIGKILL)
            except OSError:
                pass
