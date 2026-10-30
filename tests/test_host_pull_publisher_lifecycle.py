"""Hermetic tests for the host-pull publisher lifecycle candidate.

PATH fixtures replace launchctl, lockf, and ps. These tests never call the
real launchctl, the real lockf, the real ps, or the original host_pull
collector.

The candidate under test is admitted as two flat manifest members. Admission
is not selection and is not an install. These tests do not select or install
a live native generation. Advance tests call the original publisher select
only against the temporary store in the fixture.
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
    ROOT / "ops/native_fabric/quota_continuity/candidate"
    / "host_pull_launchd.plist.template"
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
    if [ -f "$STUB_STATE/print-budget" ]; then
      budget=$(cat "$STUB_STATE/print-budget")
      if [ "$budget" -le 0 ]; then
        printf 'hello\n'
        exit 0
      fi
      printf '%s\n' "$((budget - 1))" > "$STUB_STATE/print-budget"
    fi
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
        "/bin/bash", str(extra.pop("daemon", DAEMON)), extra.pop("command", "install-agent"),
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
    assert text.count("$HERE/host_pull_launchd.plist.template") == 1
    assert "launchd/com.mastermind.host-pull.plist.template" not in text


@pytest.mark.parametrize("trailing_slash", [False, True])
@pytest.mark.parametrize("preflight_repair", [False, True])
def test_stopped_publication_pins_only_verified_generation(
    workspace, trailing_slash, preflight_repair,
):
    ctx = prepare(workspace)
    ctx["env"]["TMPDIR"] = str(workspace) + ("/" if trailing_slash else "")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    if preflight_repair:
        # Full installer: mode refusal happens after its transaction marker
        # is armed. Clean pre-effect failure must permit a corrected retry.
        ctx["plist"].write_bytes(b"PRE-EFFECT-PLIST\n")
        ctx["plist"].chmod(0o644)
        refused = run(ctx)
        assert refused.returncode == 78, refused.stderr
        assert "backup failed" in refused.stderr
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        ctx["plist"].chmod(0o600)
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


def test_bootstrap_failure_preserves_original_backup(workspace):
    daemon = DAEMON.read_text()
    assert daemon.count("$HERE/host_pull_launchd.plist.template") == 1
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "bootstrap-fail-left").write_text("1\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    args = base_args(ctx)
    assert "--template" not in args
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert ctx["plist"].read_bytes() != original
    assert receipt_body(ctx)["outcome"] == "EFFECT_UNKNOWN"
    assert (ctx["store"] / ".install-transaction.marker").exists()
    backups = list(ctx["backup"].glob("com.mastermind.host-pull.plist.pre-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert_not_executed(ctx)


def _daemon_beside(directory, template_bytes=None, symlink_target=None):
    directory.mkdir()
    daemon = directory / "host_pull_daemon.sh"
    daemon.write_bytes(DAEMON.read_bytes())
    daemon.chmod(0o755)
    target = directory / "host_pull_launchd.plist.template"
    if symlink_target is not None:
        target.symlink_to(symlink_target)
    elif template_bytes is not None:
        target.write_bytes(template_bytes)
    return daemon


def test_nested_and_alias_plists_are_refused(workspace):
    ctx = prepare(workspace)
    nested = workspace / "nested" / "launchd"
    nested.mkdir(parents=True)
    unsigned = nested / "com.mastermind.host-pull.plist.template"
    unsigned.write_text("<plist><string>/bin/sh</string></plist>\n")
    alias = workspace / "host_pull_launchd.plist"
    alias.write_bytes(TEMPLATE.read_bytes())
    admitted_nested = workspace / "nested" / "sub"
    admitted_nested.mkdir()
    admitted_copy = admitted_nested / "host_pull_launchd.plist.template"
    admitted_copy.write_bytes(TEMPLATE.read_bytes())
    for path in (unsigned, alias, admitted_copy):
        result = run(ctx, template=path)
        assert result.returncode == 78, result.stderr
        assert "template path" in result.stderr
        assert not ctx["plist"].exists()
        assert (ctx["stub"] / "launchctl.log").read_text() == ""
        assert_not_executed(ctx)


def test_symlink_template_at_the_fixed_lookup_is_refused(workspace):
    ctx = prepare(workspace)
    daemon = _daemon_beside(workspace / "symlink_lookup", symlink_target=TEMPLATE)
    result = run(ctx, daemon=daemon)
    assert result.returncode == 78, result.stderr
    assert "symlink refused" in result.stderr
    assert not ctx["plist"].exists()
    assert (ctx["stub"] / "launchctl.log").read_text() == ""
    assert_not_executed(ctx)


def test_unsigned_template_at_the_fixed_lookup_is_refused(workspace):
    ctx = prepare(workspace)
    mutated = TEMPLATE.read_bytes().replace(b"/usr/bin/lockf", b"/bin/sh")
    assert mutated != TEMPLATE.read_bytes()
    daemon = _daemon_beside(workspace / "unsigned_lookup", template_bytes=mutated)
    result = run(ctx, daemon=daemon)
    assert result.returncode == 78, result.stderr
    assert "template digest" in result.stderr
    assert not ctx["plist"].exists()
    assert (ctx["stub"] / "launchctl.log").read_text() == ""
    assert_not_executed(ctx)


def test_bootstrap_failure_retains_candidate_and_is_not_green(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "bootstrap-fail-left").write_text("1\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    # A label absent before installation cannot be certified as the recovered
    # *original* collector merely because rollback bootstrap returned zero.
    assert "EFFECT_UNKNOWN" in result.stderr
    assert "bootstrap failed" in result.stderr
    assert "recovered original service:" not in result.stderr
    assert (ctx["store"] / ".install-transaction.marker").is_file()
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["phase"] == "BOOTSTRAP"
    assert ctx["plist"].read_bytes() != original
    assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o600
    assert launch_log(ctx).count("bootstrap ") == 1
    backups = list(ctx["backup"].glob("com.mastermind.host-pull.plist.pre-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert_not_executed(ctx)


def test_running_service_missing_preimage_refuses_before_mutation(workspace):
    ctx = prepare(workspace)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    before = json.loads((ctx["store"] / "CURRENT.json").read_text())
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "running service has no plist preimage" in result.stderr
    assert not (ctx["store"] / ".install-transaction.marker").exists()
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert json.loads((ctx["store"] / "CURRENT.json").read_text()) == before
    assert_not_executed(ctx)


def test_post_bootstrap_unverified_argv_records_effect_unknown(workspace):
    ctx = prepare(workspace)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    # Existing fixture advertises a different collector without any argv edit.
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert "bootstrap did not pin the verified collector" in result.stderr
    assert launch_log(ctx).count("bootstrap ") == 1
    assert "bootout " not in launch_log(ctx)
    assert (ctx["store"] / ".install-transaction.marker").exists()
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["phase"] == "POST_BOOTSTRAP_VERIFY"
    assert_not_executed(ctx)


def test_failed_bootstrap_does_not_attempt_unowned_rollback(workspace):
    ctx = prepare(workspace)
    original = b"OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "bootstrap-fail-left").write_text("2\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    result = run(ctx)
    assert result.returncode == 78, result.stderr
    assert "bootstrap failed" in result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert ctx["plist"].read_bytes() != original
    assert launch_log(ctx).count("bootstrap ") == 1
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
    rendered = ctx["plist"].read_bytes()
    assert rendered != original
    proc.send_signal(signal.SIGTERM)
    _, err = proc.communicate(timeout=5)
    assert proc.returncode == 78, err
    assert "EFFECT_UNKNOWN" in err
    assert ctx["plist"].read_bytes() == rendered
    assert receipt_body(ctx)["outcome"] == "EFFECT_UNKNOWN"
    assert (ctx["store"] / ".install-transaction.marker").exists()
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


def test_candidate_admission_is_not_a_selected_install():
    daemon = DAEMON.read_text()
    template = TEMPLATE.read_text()
    for blob in (daemon, template):
        assert "Admission is not selection" in blob
        assert "is not an install" in blob
        assert "file_name()" in blob
        assert "do not bootstrap" in blob.lower()
    assert "NOT INSTALLABLE" in daemon
    assert "ext/host_pull_launchd.plist.template" in daemon
    assert "95-member" not in daemon
    assert "launchd/com.mastermind.host-pull.plist.template" not in daemon


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
        ("install-before-replace", "EFFECT_UNKNOWN", 0, "plist install failed"),
        ("install-after-replace", "EFFECT_UNKNOWN", 0, "plist install failed"),
        ("pre-bootstrap-print", "EFFECT_UNKNOWN", 0, "launchctl state uncertain"),
    ],
)
def test_post_bootout_fault_injection(workspace, fault, outcome, bootstraps, snippet):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    result = run(ctx, fault=fault)
    assert result.returncode == 78, result.stderr
    assert snippet in result.stderr
    if fault in ("install-after-replace", "pre-bootstrap-print"):
        assert ctx["plist"].read_bytes() != original
    else:
        assert ctx["plist"].read_bytes() == original
    assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o600
    assert launch_log(ctx).count("bootstrap ") == bootstraps
    assert launch_log(ctx).count("bootout ") == 1
    receipt = receipt_body(ctx)
    assert receipt["schema"] == "host-pull-lifecycle-receipt.v1"
    assert receipt["outcome"] == outcome
    assert outcome == "EFFECT_UNKNOWN"
    assert "EFFECT_UNKNOWN" in result.stderr
    assert "recovered original service" not in result.stderr
    assert receipt["service"] == "stopped-uncertain"
    assert (ctx["store"] / ".install-transaction.marker").exists()
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


def test_selector_move_before_plist_replace_holds_stopped_service(workspace):
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
    assert "EFFECT_UNKNOWN" in err
    assert "recovered original service" not in err
    assert ctx["plist"].read_bytes() == original
    assert launch_log(ctx).count("bootstrap ") == 0
    assert launch_log(ctx).count("bootout ") == 1
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert (ctx["store"] / ".install-transaction.marker").exists()
    assert receipt["service"] == "stopped-uncertain"
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    assert_not_executed(ctx)





@pytest.mark.parametrize(
    ("phase", "pre_effect_proven", "effect_started"),
    [
        ("PLIST_REPLACED", False, False),
        ("BOOTSTRAP_STARTED", True, False),
        ("BOOTSTRAP_STARTED", False, False),
        ("BOOTSTRAP_STARTED", True, True),
        ("BOOTSTRAP_STARTED", False, True),
        ("BOOTSTRAPPED", False, True),
    ],
)
def test_holder_loss_source_never_restores_peer_plist(
    tmp_path, phase, pre_effect_proven, effect_started,
):
    # Execute literal installed-source functions only. No real launchctl,
    # fake-launchctl argv fixture, host service, or native selection.
    raw = DAEMON.read_text()
    start = raw.index("lose_install_holder() {\n")
    end = raw.index("\n}\n\nprove_install_holder() {", start) + 2
    function = raw[start:end]
    proof_start = raw.index("effect_was_not_started() {\n")
    proof_end = raw.index("\n}\n\nselector_moved_before_effect() {", proof_start) + 2
    proof_function = raw[proof_start:proof_end]

    locked = tmp_path / "current-locked-effect"
    locked.mkdir()
    if effect_started:
        (locked / "started").write_bytes(b"effect-began\n")
    plist = tmp_path / "installed.plist"
    plist.write_bytes(b"CURRENT_PLIST\n")
    selector = tmp_path / "CURRENT.json"
    selector.write_bytes(b"SELECTOR_STAYS\n")
    transaction = tmp_path / "transaction-marker"
    transaction.write_bytes(b"UNCERTAIN_TX_STAYS\n")
    fixture = (
        "set -u\n"
        + "PHASE=" + phase + "\n"
        + "STOP_LOCKED=" + ("1" if pre_effect_proven else "0") + "\n"
        + 'LOCKED_DIR="' + str(locked) + '"\n'
        + 'TEST_PLIST="' + str(plist) + '"\n'
        + 'restore_plist(){ printf "RESTORED\\n"; '
          'printf "ORIGINAL_PLIST\\n" > "$TEST_PLIST"; }\n'
        + 'note_install_blocked(){ printf "RECEIPT:EFFECT_UNKNOWN:%s\\n" "$1"; }\n'
        + 'bootstrap_once(){ printf "UNSAFE_REBOOTSTRAP\\n"; }\n'
        + 'die(){ printf "REFUSED\\n"; exit "$1"; }\n'
        + proof_function + "\n"
        + function + "\nlose_install_holder\n"
    )
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", fixture],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True, text=True,
    )
    assert result.returncode == 78, result.stderr
    expected = ["RECEIPT:EFFECT_UNKNOWN:INSTALL_HOLDER_LOST", "REFUSED"]
    assert result.stdout.splitlines() == expected
    assert plist.read_bytes() == b"CURRENT_PLIST\n"
    assert selector.read_bytes() == b"SELECTOR_STAYS\n"
    assert transaction.read_bytes() == b"UNCERTAIN_TX_STAYS\n"
    assert (locked / "started").exists() == effect_started



def test_bootstrap_effect_return_79_after_started_is_not_holder_loss(tmp_path):
    # Execute the literal run_locked Bash function with a harmless py stub
    # simulating a child command returning 79 *after* its started receipt.
    # The original rc79 shortcut mislabeled this as holder death.
    raw = DAEMON.read_text()
    start = raw.index("run_locked() {\n")
    end = raw.index("\n}\n\neffect_was_not_started() {", start) + 2
    function = raw[start:end]
    fixture = (
        'set -u\n'
        + 'TMPROOT=' + str(tmp_path) + '\n'
        + 'STORE=inert\nGENERATION=inert\nEXPECT_CURRENT=inert\n'
        + 'PUBLISHER=inert\nINSTALL_FENCE=inert\nHOLD_DURING_LOCK=\n'
        + 'prove_install_holder(){ :; }\n'
        + 'lose_install_holder(){ printf "WRONG_HOLDER_LOSS\\n"; exit 90; }\n'
        + 'py(){ if [ "$1" = "locked-effect" ]; then '
          ': > "$LOCKED_DIR/started"; return 79; fi; return 0; }\n'
        + function + '\n'
        + 'run_locked bootstrap /bin/false\n'
        + 'printf "EXIT=%s STOP=%s\\n" "$?" "$STOP_LOCKED"\n'
    )
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", fixture],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["EXIT=79 STOP=0"]



def test_bootstrap_effect_return_79_before_started_refuses_with_pre_effect_proof(tmp_path):
    # Run the literal run_locked function. A pre-admission holder loss must
    # retain the pre-effect PLIST_REPLACED phase; rc79 with no started marker
    # must then furnish positive STOP_LOCKED proof before loss handling.
    raw = DAEMON.read_text()
    start = raw.index("run_locked() {\n")
    end = raw.index("\n}\n\neffect_was_not_started() {", start) + 2
    function = raw[start:end]
    fixture = (
        "set -u\n"
        + "PHASE=PLIST_REPLACED\n"
        + 'TMPROOT="' + str(tmp_path) + '"\n'
        + 'STORE=inert\nGENERATION=inert\nEXPECT_CURRENT=inert\n'
        + 'PUBLISHER=inert\nINSTALL_FENCE=inert\nHOLD_DURING_LOCK=\n'
        + 'prove_install_holder(){ [ "$PHASE" = "PLIST_REPLACED" ] || exit 91; }\n'
        + 'lose_install_holder(){ '
          '[ "$STOP_LOCKED" -eq 1 ] && [ "$PHASE" = "BOOTSTRAP_STARTED" ] '
          '|| exit 92; printf "PRE_EFFECT_REFUSAL\\n"; exit 78; }\n'
        + 'py(){ if [ "$1" = "locked-effect" ]; then return 79; '
          'fi; return 0; }\n'
        + function + "\n"
        + 'run_locked bootstrap /bin/false\n'
        + 'printf "UNEXPECTED_BOOTSTRAP_SUCCESS\\n"\n'
    )
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", fixture],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True, text=True,
    )
    assert result.returncode == 78, result.stderr
    assert result.stdout.splitlines() == ["PRE_EFFECT_REFUSAL"]



def test_absent_label_holder_death_preserves_candidate(workspace):
    # Existing hermetic launcher helper only; no fake launchctl argv/stub edits,
    # external service, original collector or native release effect.
    ctx = prepare(workspace)
    original = b"ORIGINAL-ABSENT-LABEL-PREIMAGE\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    hold = workspace / "hold-bootstrap"
    hold.write_text("")
    report = workspace / "holder-report"
    fd = os.open(report, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold, holder_report=report),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        installed = ctx["plist"].read_bytes()
        assert installed != original
        deadline = time.time() + 8
        while time.time() < deadline and b"armed\n" not in report.read_bytes():
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read())
            time.sleep(0.05)
        assert b"armed\n" in report.read_bytes()
        fields = dict(line.split("=", 1)
                      for line in report.read_text().splitlines() if "=" in line)
        holder = int(fields["pid"])
        assert "bootstrap " not in launch_log(ctx)
        os.kill(holder, signal.SIGKILL)
        _wait_transaction_unlocked(ctx)
        hold.unlink()
        _out, err = proc.communicate(timeout=10)
        assert proc.returncode == 78, err
        assert "install transaction holder lost" in err
        assert ctx["plist"].read_bytes() == installed
        assert "EFFECT_UNKNOWN" in err
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "INSTALL_HOLDER_LOST"
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


def test_absent_label_selector_move_before_bootstrap_preserves_candidate(workspace):
    # New negative-path coverage reuses the existing accepted hermetic stub;
    # no launchctl argv/stub implementation change or real host effect.
    ctx = prepare(workspace)
    original = b"ORIGINAL-ABSENT-LABEL-PLIST\\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    hold = workspace / "hold-bootstrap"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        installed = ctx["plist"].read_bytes()
        assert installed != original
        _move_selector(ctx, workspace)
        hold.unlink()
        _out, err = proc.communicate(timeout=10)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert ctx["plist"].read_bytes() == installed
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "BOOTSTRAP_ADMIT"
        assert "selector moved before bootstrap" in receipt["reason"]
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


def test_fresh_absent_plist_pre_bootstrap_error_writes_receipt_without_backup(workspace):
    ctx = prepare(workspace)
    assert not ctx["plist"].exists() and not ctx["backup"].exists()
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    result = run(ctx, fault="pre-bootstrap-print")
    assert result.returncode == 78, result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert ctx["plist"].exists()
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["phase"] == "PRE_BOOTSTRAP_PRINT"
    assert "launchctl state uncertain" in receipt["reason"]
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)

def test_selector_move_before_bootstrap_preserves_unknown_mismatched_service(workspace):
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-bootstrap"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _release_hold(proc, hold)
    installed = ctx["plist"].read_bytes()
    assert installed != original
    assert "bootstrap " not in launch_log(ctx)
    other = _move_selector(ctx, workspace)
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    hold.unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "selector moved" in err
    assert "EFFECT_UNKNOWN" in err
    assert "recovered original service" not in err
    assert ctx["plist"].read_bytes() == installed
    assert launch_log(ctx).count("bootstrap ") == 0
    assert launch_log(ctx).count("bootout ") == 1
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    current = json.loads((ctx["store"] / "CURRENT.json").read_text())
    assert current["generation"] == other.name
    assert (ctx["store"] / ".install-transaction.marker").exists()
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
    assert log.count("print ") == 3
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


def test_holder_death_before_arm_does_not_mutate_after_peer_install(workspace):
    """Kill only A's lock helper after the old label read and before arm.

    B then completes the install and clears the marker. A must not boot out
    or replace B's service from the stale read.
    """
    ctx = prepare(workspace)
    original = arm_running(ctx, workspace)
    hold = workspace / "hold-arm"
    hold.write_text("")
    report = workspace / "holder-report"
    fd = os.open(report, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    proc = subprocess.Popen(
        base_args(ctx, hold_before_arm=hold, holder_report=report),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _release_hold(proc, hold)
        deadline = time.time() + 8
        while time.time() < deadline and b"armed\n" not in report.read_bytes():
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read())
            time.sleep(0.05)
        fields = dict(
            line.split("=", 1) for line in report.read_text().splitlines() if "=" in line)
        holder = int(fields["pid"])
        assert proc.poll() is None
        log_at_pause = launch_log(ctx)
        assert "print " in log_at_pause
        assert "bootout " not in log_at_pause
        assert "bootstrap " not in log_at_pause
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        assert ctx["plist"].read_bytes() == original
        os.kill(holder, signal.SIGKILL)
        _wait_transaction_unlocked(ctx)
        assert proc.poll() is None
        (ctx["stub"] / "pause-pid").write_text("")
        other = subprocess.Popen(
            base_args(ctx), env=ctx["env"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.time() + 8
        while time.time() < deadline and not (ctx["stub"] / "ps-entered").exists():
            if other.poll() is not None:
                _out, err = other.communicate()
                raise AssertionError(err)
            time.sleep(0.05)
        (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
        (ctx["stub"] / "pause-pid").unlink()
        _out, err = other.communicate(timeout=10)
        assert other.returncode == 0, err
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        log_after_peer = launch_log(ctx)
        plist_after_peer = ctx["plist"].read_bytes()
        backups_after_peer = _plist_backups(ctx)
        assert log_after_peer.count("bootout ") == 1
        assert log_after_peer.count("bootstrap ") == 1
        assert plist_after_peer != original
        assert backups_after_peer
        hold.unlink()
        _out, err = proc.communicate(timeout=10)
        assert proc.returncode == 78, err
        assert "install transaction holder lost" in err
        assert "bootout had no effect" not in err
        assert launch_log(ctx) == log_after_peer
        assert ctx["plist"].read_bytes() == plist_after_peer
        assert _plist_backups(ctx) == backups_after_peer
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        assert (ctx["stub"] / "print-mode").read_text().strip() == "running"
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "INSTALL_HOLDER_LOST"
        assert "holder lost" in receipt["reason"]
        assert_not_executed(ctx)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.communicate(timeout=5)


def _selection(ctx):
    return json.loads((ctx["store"] / "CURRENT.json").read_text())


def _reviewed_target(ctx, workspace, body):
    store, release = publish(workspace, body, False)
    assert store == ctx["store"]
    return release


def _wait_for(proc, path):
    deadline = time.time() + 8
    while time.time() < deadline and not path.exists():
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise AssertionError(err or out)
        time.sleep(0.05)
    assert path.exists()


def test_advance_rebinds_launchd_only_after_old_pid_settles(workspace):
    """Selector CAS and the launchd pin move together, and only after the old pid is dead."""
    ctx = prepare(workspace, body=b"#!/bin/bash\nexit 7\n")
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 8\n")
    pin = target / "ext" / "host_pull.sh"
    original = b"OLD-LAUNCHD-8458592a\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "pause-pid").write_text("")
    (ctx["stub"] / "argv").write_text("/bin/bash\n/generations/8458592a/ext/host_pull.sh\n")
    proc = subprocess.Popen(
        base_args(ctx, generation=target.name, expect=selector.name, advance_from=selector.name),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_for(proc, ctx["stub"] / "ps-entered")
    mid = _selection(ctx)
    assert mid["generation"] == target.name
    assert mid["previous"] == selector.name
    assert mid["sequence"] == before["sequence"] + 1
    assert ctx["plist"].read_bytes() == original
    paused = launch_log(ctx)
    assert "bootout " in paused
    assert "bootstrap " not in paused
    assert paused.count("print ") == 1
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], pin))
    (ctx["stub"] / "pause-pid").unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 0, err
    final = _selection(ctx)
    assert final["generation"] == target.name
    assert final["previous"] == selector.name
    assert final["sequence"] == before["sequence"] + 1
    plist = plistlib.loads(ctx["plist"].read_bytes())
    assert plist["ProgramArguments"][-1] == str(pin)
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert log.count("bootstrap ") == 1
    assert log.index("bootout ") < log.index("bootstrap ")
    assert not (ctx["store"] / ".install-transaction.marker").exists()
    assert_not_executed(ctx)


def test_rebind_without_advance_does_not_touch_launchd(workspace):
    ctx = prepare(workspace)
    selector = ctx["release"].name
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 9\n")
    original = arm_running(ctx, workspace)
    result = run(ctx, generation=target.name, expect=selector)
    assert result.returncode == 78, result.stderr
    assert "pin checks failed" in result.stderr
    assert launch_log(ctx) == ""
    assert _selection(ctx) == before
    assert ctx["plist"].read_bytes() == original
    assert "bootout " not in launch_log(ctx)
    assert_not_executed(ctx)


def test_advance_from_must_name_the_live_selector(workspace):
    ctx = prepare(workspace)
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 10\n")
    original = arm_running(ctx, workspace)
    other = "ab" * 32
    result = run(ctx, generation=target.name, expect=other, advance_from=other)
    assert result.returncode == 78, result.stderr
    assert "pin checks failed" in result.stderr
    assert "generation is not the selected current" in result.stderr
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert _selection(ctx) == before
    assert ctx["plist"].read_bytes() == original
    assert_not_executed(ctx)


def test_advance_target_equal_to_current_is_refused(workspace):
    ctx = prepare(workspace)
    before = _selection(ctx)
    name = ctx["release"].name
    result = run(ctx, advance_from=name)
    assert result.returncode == 78, result.stderr
    assert "advance target is already current" in result.stderr
    assert launch_log(ctx) == ""
    assert _selection(ctx) == before
    assert_not_executed(ctx)


def test_advance_refuses_while_publication_lock_is_held(workspace):
    ctx = prepare(workspace)
    selector = ctx["release"].name
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 11\n")
    original = arm_running(ctx, workspace)
    lock = ctx["store"] / ".publication.lock"
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run(ctx, generation=target.name, expect=selector, advance_from=selector)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert result.returncode == 78, result.stderr
    assert "selector advance refused" in result.stderr
    assert "native publication already in progress" in result.stderr
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert _selection(ctx) == before
    assert ctx["plist"].read_bytes() == original
    assert not (ctx["store"] / ".install-transaction.marker").exists()
    assert_not_executed(ctx)


def test_advance_preserves_selector_when_rollback_argv_mismatches(workspace):
    ctx = prepare(workspace, body=b"#!/bin/bash\nexit 12\n")
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 13\n")
    original = b"OLD-LAUNCHD-PIN\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "pause-pid").write_text("")
    (ctx["stub"] / "bootstrap-fail-left").write_text("1\n")
    (ctx["stub"] / "argv").write_text("/bin/bash\n/old/generation/ext/host_pull.sh\n")
    proc = subprocess.Popen(
        base_args(ctx, generation=target.name, expect=selector.name, advance_from=selector.name),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _wait_for(proc, ctx["stub"] / "ps-entered")
    assert "bootstrap " not in launch_log(ctx)
    assert ctx["plist"].read_bytes() == original
    assert _selection(ctx)["generation"] == target.name
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], target / "ext" / "host_pull.sh"))
    (ctx["stub"] / "pause-pid").unlink()
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode == 78, err
    assert "EFFECT_UNKNOWN" in err
    assert "recovered original service" not in err
    assert ctx["plist"].read_bytes() != original
    final = _selection(ctx)
    assert final["generation"] == target.name
    assert final["previous"] == selector.name
    assert final["sequence"] == before["sequence"] + 1
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert log.count("bootstrap ") == 1
    assert log.index("bootout ") < log.index("bootstrap ")
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert receipt["phase"] == "BOOTSTRAP"
    assert (ctx["store"] / ".install-transaction.marker").exists()
    assert_not_executed(ctx)


def test_advance_no_effect_bootout_rolls_selector_back(workspace):
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 14\n")
    original = arm_running(ctx, workspace)
    (ctx["stub"] / "bootout-rc").write_text("1\n")
    result = run(ctx, generation=target.name, expect=selector.name, advance_from=selector.name)
    assert result.returncode == 78, result.stderr
    assert "bootout had no effect" in result.stderr
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "NO_EFFECT"
    assert receipt["service"] == "still-loaded"
    assert ctx["plist"].read_bytes() == original
    final = _selection(ctx)
    assert final["generation"] == selector.name
    assert final["previous"] == target.name
    assert final["sequence"] == before["sequence"] + 2
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert "bootstrap " not in log
    assert_not_executed(ctx)


def test_advance_effect_unknown_does_not_roll_the_selector_back(workspace):
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 15\n")
    original = arm_running(ctx, workspace)
    result = run(
        ctx, generation=target.name, expect=selector.name, advance_from=selector.name,
        fault="post-bootout-print")
    assert result.returncode == 78, result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["service"] == "stopped-uncertain"
    assert "roll" not in receipt["reason"]
    final = _selection(ctx)
    assert final["generation"] == target.name
    assert final["previous"] == selector.name
    assert final["sequence"] == before["sequence"] + 1
    assert ctx["plist"].read_bytes() == original
    log = launch_log(ctx)
    assert log.count("bootout ") == 1
    assert "bootstrap " not in log
    assert_not_executed(ctx)


def test_ready_before_watch_registration_is_refused(workspace):
    """A premature 0 is not readiness. Watch registration must already have succeeded."""
    ctx = prepare(workspace)
    result = run(ctx, fault="watch-after-ready")
    assert result.returncode == 78, result.stderr
    assert "install transaction watch refused" in result.stderr
    assert "print " not in launch_log(ctx)
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert _plist_backups(ctx) == []
    assert not (ctx["store"] / ".install-transaction.marker").exists()
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["phase"] == "INSTALL_WATCH_REFUSED"
    assert "watch refused" in receipt["reason"]
    assert_not_executed(ctx)


_SELECT_FAULT_PUBLISHER = r'''import importlib.util
import os
import signal
import sys
from pathlib import Path

real = os.environ["HOST_PULL_REAL_PUBLISHER"]
spec = importlib.util.spec_from_file_location("native_generation_under_test", real)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
current = module.current
_fsync = module.fsync_directory


def fsync_directory(path):
    fault = Path(os.environ["HOST_PULL_SELECT_FAULT"])
    seen = Path(str(fault) + ".seen")
    fence = Path(os.environ["HOST_PULL_STORE"]) / ".select-pending"
    if not fence.is_file():
        seen.write_text("missing\n")
        raise OSError("select fence missing")
    seen.write_text("present\n")
    mode = fault.read_text().strip() if fault.exists() else ""
    if mode == "fsync-once":
        fault.write_text("done\n")
        raise OSError("INJECTED_POST_RENAME_FSYNC_FAILURE")
    result = _fsync(path)
    installer = int(os.environ.get("HOST_PULL_INSTALLER_PID") or "0")
    if mode == "signal-term":
        fault.write_text("done\n")
        os.kill(installer, signal.SIGTERM)
    elif mode == "signal-hup":
        fault.write_text("done\n")
        os.kill(installer, signal.SIGHUP)
    return result


module.fsync_directory = fsync_directory

if __name__ == "__main__":
    try:
        module.main()
    except (OSError, ValueError) as exc:
        print("NATIVE_GENERATION_REFUSED: " + str(exc), file=sys.stderr)
        raise SystemExit(78)
'''


def _faulty_publisher(ctx, mode):
    directory = ctx["stub"] / "publisher"
    directory.mkdir()
    path = directory / "native_generation.py"
    path.write_text(_SELECT_FAULT_PUBLISHER)
    fault = ctx["stub"] / "select-fault"
    fault.write_text(mode + "\n")
    ctx["env"]["HOST_PULL_REAL_PUBLISHER"] = str(PUBLISHER)
    ctx["env"]["HOST_PULL_SELECT_FAULT"] = str(fault)
    ctx["env"]["HOST_PULL_STORE"] = str(ctx["store"])
    return path


def _arm_old_collector(ctx):
    original = b"OLD-LAUNCHD-PREIMAGE\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("running\n")
    (ctx["stub"] / "ps-alive").write_text("")
    (ctx["stub"] / "argv").write_text("/bin/bash\n/old/generation/ext/host_pull.sh\n")
    return original


def test_advance_fsync_after_rename_rolls_back_only_the_proven_preimage(workspace):
    """A publisher error after CURRENT is renamed is not NO_EFFECT."""
    ctx = prepare(workspace, body=b"#!/bin/bash\nexit 21\n")
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 22\n")
    original = _arm_old_collector(ctx)
    publisher = _faulty_publisher(ctx, "fsync-once")
    result = run(
        ctx, publisher=publisher, generation=target.name,
        expect=selector.name, advance_from=selector.name)
    assert result.returncode == 78, result.stderr
    assert "INJECTED_POST_RENAME_FSYNC_FAILURE" in result.stderr
    assert "selector advance refused" in result.stderr
    assert "EFFECT_UNKNOWN" not in result.stderr
    assert (ctx["stub"] / "select-fault.seen").read_text() == "present\n"
    final = _selection(ctx)
    assert final["generation"] == selector.name
    assert final["previous"] == target.name
    assert final["sequence"] == before["sequence"] + 2
    assert ctx["plist"].read_bytes() == original
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert not (ctx["store"] / ".install-transaction.marker").exists()
    assert not (ctx["store"] / ".select-pending").exists()
    assert list(ctx["backup"].glob("*.receipt")) == []
    assert_not_executed(ctx)


def test_advance_fsync_after_rename_keeps_unknown_when_service_is_unreadable(workspace):
    ctx = prepare(workspace, body=b"#!/bin/bash\nexit 23\n")
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 24\n")
    original = _arm_old_collector(ctx)
    (ctx["stub"] / "print-budget").write_text("1\n")
    publisher = _faulty_publisher(ctx, "fsync-once")
    result = run(
        ctx, publisher=publisher, generation=target.name,
        expect=selector.name, advance_from=selector.name)
    assert result.returncode == 78, result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    final = _selection(ctx)
    assert final["generation"] == target.name
    assert final["previous"] == selector.name
    assert final["sequence"] == before["sequence"] + 1
    assert ctx["plist"].read_bytes() == original
    assert (ctx["store"] / ".install-transaction.marker").is_file()
    fence = (ctx["store"] / ".select-pending").read_text()
    assert fence == selector.name + " " + target.name + "\n"
    receipt = receipt_body(ctx)
    assert receipt["outcome"] == "EFFECT_UNKNOWN"
    assert receipt["phase"] == "SELECT_UNKNOWN"
    assert_not_executed(ctx)


@pytest.mark.parametrize(("mode", "text"), [
    ("signal-term", "signal during select"),
    ("signal-hup", "signal during select"),
])
def test_signal_between_select_cas_and_ack_reconciles_current(workspace, mode, text):
    ctx = prepare(workspace, body=b"#!/bin/bash\nexit 25\n")
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 26\n")
    original = _arm_old_collector(ctx)
    publisher = _faulty_publisher(ctx, mode)
    result = run(
        ctx, publisher=publisher, generation=target.name,
        expect=selector.name, advance_from=selector.name)
    assert result.returncode == 78, result.stderr
    assert text in result.stderr
    assert "EFFECT_UNKNOWN" not in result.stderr
    assert (ctx["stub"] / "select-fault.seen").read_text() == "present\n"
    final = _selection(ctx)
    assert final["generation"] == selector.name
    assert final["previous"] == target.name
    assert final["sequence"] == before["sequence"] + 2
    assert ctx["plist"].read_bytes() == original
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert not (ctx["store"] / ".install-transaction.marker").exists()
    assert not (ctx["store"] / ".select-pending").exists()
    assert list(ctx["backup"].glob("*.receipt")) == []
    assert_not_executed(ctx)


@pytest.mark.parametrize("initial_marker", [0, 1])
def test_committed_select_fence_cleanup_failure_is_effect_unknown(tmp_path, initial_marker):
    # Execute the exact advance_selector source under inert, no-launcher
    # functions. The publisher already acknowledged CURRENT=target; the
    # fence cleanup fails. No fake-launchctl argv, selector, or host mutation.
    raw = DAEMON.read_text()
    start = raw.index("advance_selector() {\n")
    end = raw.index("\n}\n\n# CAS back", start) + 2
    function = raw[start:end]
    script = (
        "set -u\n"
        + 'ADVANCE_FROM=prior\nGENERATION=target\nEXPECT_CURRENT=prior\n'
        + 'SELECTED_ADVANCE=0\nSELECT_FENCE=0\nMARKER_OWNED=' + str(initial_marker) + '\n'
        + 'PHASE=' + ('BACKED_UP' if initial_marker else 'VERIFIED') + '\n'
        + 'STORE=inert\nPUBLISHER=inert\nINSTALL_FENCE=inert\n'
        + 'TMPROOT="' + str(tmp_path) + '"\nPYTHON=/bin/echo\n'
        + 'prove_install_holder(){ :; }\n'
        + 'py(){ [ "$1" = "install-transaction-arm" ] || return 88; printf "ARMED\\n"; }\n'
        + 'snapshot_service(){ :; }\n'
        + 'arm_select_fence(){ SELECT_FENCE=1; }\n'
        + 'confirm_selection_json(){ :; }\n'
        + 'read_selector_generation(){ SELECT_GENERATION="$GENERATION"; SELECT_PREVIOUS="$ADVANCE_FROM"; }\n'
        + 'clear_select_fence(){ return 78; }\n'
        + 'write_receipt(){ printf "RECEIPT:%s:%s\n" "$1" "$2"; }\n'
        + 'note_install_blocked(){ return 1; }\n'
        + 'die(){ printf "REFUSED:%s\n" "$*"; '
          'printf "STATE:%s:%s:%s:%s\n" "$SELECTED_ADVANCE" "$SELECT_FENCE" "$MARKER_OWNED" "$PHASE"; exit "$1"; }\n'
        + 'keep_select_unknown(){ '
          'write_receipt EFFECT_UNKNOWN SELECT_UNKNOWN "$1" || true; '
          'die 78 "EFFECT_UNKNOWN service stopped pending repair: $1"; }\n'
        + function + "\nadvance_selector\n"
    )
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", script],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True, text=True,
    )
    assert result.returncode == 78, result.stderr
    assert "RECEIPT:EFFECT_UNKNOWN:SELECT_UNKNOWN" in result.stdout
    assert ("STATE:0:1:1:PAIRING" if initial_marker == 0
            else "STATE:0:1:1:BACKED_UP") in result.stdout
    assert ("ARMED" in result.stdout) == (initial_marker == 0)
    assert "EFFECT_UNKNOWN" in result.stdout



@pytest.mark.parametrize(("sig", "exit_code"), [
    (signal.SIGTERM, 143), (signal.SIGHUP, 129), (signal.SIGINT, 130),
])
@pytest.mark.parametrize("drift", ["intact", "disappeared", "argv", "plist"])
def test_signal_after_ack_before_bootout_reproves_original_identity(
    workspace, sig, exit_code, drift,
):
    """After selector CAS/fence ack, signals may reverse only a proven old service."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    baseline = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 61\n")
    original = arm_running(ctx, workspace)
    hold = workspace / "post-select-pre-bootout"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(
            ctx, generation=target.name, expect=selector.name,
            advance_from=selector.name, hold_before_bootout=hold,
        ),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        assert _selection(ctx)["generation"] == target.name
        assert "bootout " not in launch_log(ctx)
        if drift == "disappeared":
            (ctx["stub"] / "print-mode").write_text("stopped\n")
        elif drift == "argv":
            (ctx["stub"] / "argv").write_text(
                expected_argv(ctx["lock"], target / "ext" / "host_pull.sh")
            )
        elif drift == "plist":
            ctx["plist"].write_bytes(b"PEER-PLIST-AFTER-CAS\n")
        proc.send_signal(sig)
        _out, err = proc.communicate(timeout=12)
        last = _selection(ctx)
        if drift == "intact":
            assert proc.returncode == exit_code, err
            assert last["generation"] == selector.name
            assert last["sequence"] == baseline["sequence"] + 2
            assert "EFFECT_UNKNOWN" not in err
        else:
            assert proc.returncode == 78, err
            assert "EFFECT_UNKNOWN" in err
            assert "original service identity unproven" in err
            assert last["generation"] == target.name
            assert last["previous"] == selector.name
            assert last["sequence"] == baseline["sequence"] + 1
            receipt = receipt_body(ctx)
            assert receipt["outcome"] == "EFFECT_UNKNOWN"
            assert receipt["phase"] == "signal-BACKED_UP"
            assert (ctx["store"] / ".install-transaction.marker").exists()
        assert ctx["plist"].read_bytes() == (
            b"PEER-PLIST-AFTER-CAS\n" if drift == "plist" else original
        )
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize("drift", ["argv", "plist"])
def test_bootout_nonzero_same_pid_with_identity_drift_is_unknown(workspace, drift):
    """Nonzero bootout + same live PID does not prove argv or plist continuity."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 62\n")
    original = arm_running(ctx, workspace)
    (ctx["stub"] / "bootout-rc").write_text("1\n")
    hold = workspace / "post-select-bootout-drift"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(
            ctx, generation=target.name, expect=selector.name,
            advance_from=selector.name, hold_before_bootout=hold,
        ),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        assert _selection(ctx)["generation"] == target.name
        if drift == "argv":
            (ctx["stub"] / "argv").write_text(
                expected_argv(ctx["lock"], target / "ext" / "host_pull.sh")
            )
        else:
            ctx["plist"].write_bytes(b"PEER-PLIST-BEFORE-BOOTOUT\n")
        hold.unlink()
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert "original service identity unproven" in err
        assert "bootout had no effect" not in err
        last = _selection(ctx)
        assert last["generation"] == target.name
        assert last["previous"] == selector.name
        assert last["sequence"] == before["sequence"] + 1
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "BOOTOUT_ROLLBACK"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert ctx["plist"].read_bytes() == (
            b"PEER-PLIST-BEFORE-BOOTOUT\n" if drift == "plist" else original
        )
        assert (ctx["stub"] / "pid").read_text().strip() == "4242"
        assert (ctx["stub"] / "ps-alive").exists()
        assert launch_log(ctx).count("bootout ") == 1
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize("drift", ["intact-absent", "became-loaded", "unreadable"])
def test_absent_prebootout_install_failure_requires_saved_service_state(
    workspace, drift,
):
    """An originally absent collector must stay absent through selector rollback."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 63\n")
    original = b"ABSENT-LABEL-ORIGINAL-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    hold = workspace / "absent-install-refusal"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(
            ctx, generation=target.name, expect=selector.name,
            advance_from=selector.name, hold_before_plist=hold,
            fault="install-before-replace",
        ),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        assert _selection(ctx)["generation"] == target.name
        assert "bootout " not in launch_log(ctx)
        if drift == "became-loaded":
            (ctx["stub"] / "print-mode").write_text("running\n")
            (ctx["stub"] / "ps-alive").write_text("")
            (ctx["stub"] / "argv").write_text("/bin/bash\n/peer/collector.sh\n")
        elif drift == "unreadable":
            (ctx["stub"] / "print-style").write_text("garbage\n")
        hold.unlink()
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        last = _selection(ctx)
        assert ctx["plist"].read_bytes() == original
        if drift == "intact-absent":
            assert "plist install failed" in err
            assert "EFFECT_UNKNOWN" not in err
            assert last["generation"] == selector.name
            assert last["sequence"] == before["sequence"] + 2
        else:
            assert "EFFECT_UNKNOWN" in err
            assert "original service/plist identity unproven" in err
            assert last["generation"] == target.name
            assert last["previous"] == selector.name
            assert last["sequence"] == before["sequence"] + 1
            receipt = receipt_body(ctx)
            assert receipt["outcome"] == "EFFECT_UNKNOWN"
            assert receipt["phase"] == "INSTALL"
            assert (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)



@pytest.mark.parametrize(("initial", "peer"), [
    (b"PRE-PEER-PLIST\n", b"PEER-REPLACED-PLIST\n"),
    (b"PRE-PEER-PLIST\n", None),
    (None, b"PEER-CREATED-PLIST\n"),
])
def test_install_before_replace_never_restores_over_peer_plist(workspace, initial, peer):
    """Pre-replace failure preserves concurrent peer creation/edit/deletion."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 64\n")
    if initial is not None:
        ctx["plist"].write_bytes(initial)
        ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    hold = workspace / "hold-preinstall-peer-change"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, generation=target.name, expect=selector.name,
                  advance_from=selector.name, hold_before_plist=hold,
                  fault="install-before-replace"),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _release_hold(proc, hold)
        assert _selection(ctx)["generation"] == target.name
        if peer is None:
            ctx["plist"].unlink()
        else:
            ctx["plist"].write_bytes(peer)
            ctx["plist"].chmod(0o600)
        hold.unlink()
        _out, err = proc.communicate(timeout=15)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert "original service/plist identity unproven" in err
        assert ctx["plist"].exists() == (peer is not None)
        if peer is not None:
            assert ctx["plist"].read_bytes() == peer
        final = _selection(ctx)
        assert final["generation"] == target.name
        assert final["previous"] == selector.name
        assert final["sequence"] == before["sequence"] + 1
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "INSTALL"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize("post_failure_peer", [False, True])
def test_install_after_replace_failure_retains_own_or_peer_bytes_and_unknown(
    workspace, post_failure_peer,
):
    """Postreplace failure cannot overwrite later peer bytes during recovery."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 65\n")
    original = b"ORIGINAL-BEFORE-REPLACE\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    hold = workspace / "hold-after-failed-install"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, generation=target.name, expect=selector.name,
                  advance_from=selector.name, hold_after_install_failure=hold,
                  fault="install-after-replace"),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _release_hold(proc, hold)
        assert _selection(ctx)["generation"] == target.name
        installed = ctx["plist"].read_bytes()
        assert installed != original
        assert plistlib.loads(installed)["ProgramArguments"][-1] == str(
            target / "ext" / "host_pull.sh"
        )
        peer = b"PEER-AFTER-FAILED-REPLACE\n"
        if post_failure_peer:
            ctx["plist"].write_bytes(peer)
        hold.unlink()
        _out, err = proc.communicate(timeout=15)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert "original service/plist identity unproven" in err
        assert ctx["plist"].read_bytes() == (peer if post_failure_peer else installed)
        final = _selection(ctx)
        assert final["generation"] == target.name
        assert final["previous"] == selector.name
        assert final["sequence"] == before["sequence"] + 1
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "INSTALL"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


def test_install_failure_without_selector_still_refuses_unverified_plist(workspace):
    """No selector CAS does not excuse an unproven post-install plist effect."""
    ctx = prepare(workspace)
    original = b"NO-SELECTOR-OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    selected_before = _selection(ctx)
    result = run(ctx, fault="install-after-replace")
    assert result.returncode == 78, result.stderr
    assert "EFFECT_UNKNOWN" in result.stderr
    assert ctx["plist"].read_bytes() != original
    assert _selection(ctx) == selected_before
    assert receipt_body(ctx)["outcome"] == "EFFECT_UNKNOWN"
    assert (ctx["store"] / ".install-transaction.marker").exists()
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)


@pytest.mark.parametrize(("original", "action"), [
    (b"ORIGINAL-BEFORE-SIGNAL\n", "edit"),
    (b"ORIGINAL-BEFORE-SIGNAL\n", "delete"),
    (None, "delete-and-create"),
])
def test_signal_after_plist_replace_preserves_peer_effects(
    workspace, original, action,
):
    """No peer edit/deletion/recreation can be clobbered by the signal handler."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 66\n")
    if original is not None:
        ctx["plist"].write_bytes(original)
        ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    hold = workspace / "hold-signal-post-install"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, generation=target.name, expect=selector.name,
                  advance_from=selector.name, hold_before_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        installed = ctx["plist"].read_bytes()
        assert original is None or installed != original
        assert _selection(ctx)["generation"] == target.name
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        peer = b"PEER-WRITTEN-AFTER-OUR-INSTALL\n"
        if action == "delete":
            ctx["plist"].unlink()
        elif action == "delete-and-create":
            ctx["plist"].unlink()
            ctx["plist"].write_bytes(peer)
            ctx["plist"].chmod(0o600)
        else:
            ctx["plist"].write_bytes(peer)
        proc.send_signal(signal.SIGTERM)
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert "signal during PLIST_REPLACED" in err
        assert ctx["plist"].exists() == (action != "delete")
        if action != "delete":
            assert ctx["plist"].read_bytes() == peer
        final = _selection(ctx)
        assert final["generation"] == target.name
        assert final["previous"] == selector.name
        assert final["sequence"] == before["sequence"] + 1
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "signal-PLIST_REPLACED"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)



def test_source_has_no_unconditional_plist_restore_path():
    """Fail if rollback again writes a plist without exclusive file ownership."""
    text = DAEMON.read_text()
    assert "restore_plist()" not in text
    assert "restore_plist ||" not in text
    assert "py atomic-restore" not in text
    assert "py atomic-remove" not in text


@pytest.mark.parametrize("action", ["edit", "delete", "delete-and-create"])
def test_holder_loss_after_install_preserves_peer_plist(workspace, action):
    """A dead transaction holder cannot rewrite peer plist after install."""
    ctx = prepare(workspace)
    original = b"HOLDER-OLD-PLIST\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    before = _selection(ctx)
    hold = workspace / "holder-loss-peer-hold"
    hold.write_text("")
    report = workspace / "holder-loss-report"
    report.touch(mode=0o600)
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold, holder_report=report),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        installed = ctx["plist"].read_bytes()
        assert installed != original
        deadline = time.time() + 8
        while time.time() < deadline and b"armed\n" not in report.read_bytes():
            if proc.poll() is not None:
                raise AssertionError(proc.stderr.read())
            time.sleep(0.05)
        assert b"armed\n" in report.read_bytes()
        fields = dict(line.split("=", 1)
                      for line in report.read_text().splitlines() if "=" in line)
        peer = b"PEER-AFTER-INSTALL-HOLDER\n"
        if action == "delete":
            ctx["plist"].unlink()
        elif action == "delete-and-create":
            ctx["plist"].unlink()
            ctx["plist"].write_bytes(peer)
        else:
            ctx["plist"].write_bytes(peer)
        os.kill(int(fields["pid"]), signal.SIGKILL)
        _wait_transaction_unlocked(ctx)
        hold.unlink()
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert "install transaction holder lost" in err
        assert ctx["plist"].exists() == (action != "delete")
        if action != "delete":
            assert ctx["plist"].read_bytes() == peer
        assert _selection(ctx) == before
        assert receipt_body(ctx)["outcome"] == "EFFECT_UNKNOWN"
        assert receipt_body(ctx)["phase"] == "INSTALL_HOLDER_LOST"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_uncertain_prebootstrap_print_retains_peer_plist(workspace, action):
    """Uncertain launchctl print must not restore over later peer bytes."""
    ctx = prepare(workspace)
    old = b"OLD-BEFORE-PRINT\n"
    ctx["plist"].write_bytes(old)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    before = _selection(ctx)
    hold = workspace / "uncertain-print-plist"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        assert ctx["plist"].read_bytes() != old
        peer = b"PEER-UNCERTAIN-PRINT\n"
        if action == "delete":
            ctx["plist"].unlink()
        else:
            ctx["plist"].write_bytes(peer)
        (ctx["stub"] / "print-style").write_text("garbage\n")
        hold.unlink()
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert ctx["plist"].exists() == (action != "delete")
        if action != "delete":
            assert ctx["plist"].read_bytes() == peer
        assert _selection(ctx) == before
        assert receipt_body(ctx)["phase"] == "PRE_BOOTSTRAP_PRINT"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert "bootout " not in launch_log(ctx)
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_postbootout_failed_install_never_restores_over_peer(workspace, action):
    """BOOTED recovery refuses another plist write or launchctl bootstrap."""
    ctx = prepare(workspace)
    selector = ctx["release"]
    before = _selection(ctx)
    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\nexit 67\n")
    arm_running(ctx, workspace)
    hold = workspace / "postbootout-failed-install"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, generation=target.name, expect=selector.name,
                  advance_from=selector.name, hold_after_install_failure=hold,
                  fault="install-after-replace"),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        assert _selection(ctx)["generation"] == target.name
        assert "bootout " in launch_log(ctx)
        peer = b"PEER-AFTER-BOOTOUT\n"
        if action == "delete":
            ctx["plist"].unlink()
        else:
            ctx["plist"].write_bytes(peer)
        hold.unlink()
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert ctx["plist"].exists() == (action != "delete")
        if action != "delete":
            assert ctx["plist"].read_bytes() == peer
        final = _selection(ctx)
        assert final["generation"] == target.name
        assert final["previous"] == selector.name
        assert final["sequence"] == before["sequence"] + 1
        assert receipt_body(ctx)["phase"] == "INSTALL"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert launch_log(ctx).count("bootout ") == 1
        assert "bootstrap " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_bootstrap_failure_does_not_restore_peer_plist(workspace, action):
    """Failed bootstrap does not overwrite peer file before recovery."""
    ctx = prepare(workspace)
    original = b"BOOTSTRAP-PEER-PREIMAGE\n"
    ctx["plist"].write_bytes(original)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "bootstrap-fail-left").write_text("1\n")
    before = _selection(ctx)
    hold = workspace / "failed-bootstrap-peer"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_before_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        assert ctx["plist"].read_bytes() != original
        peer = b"PEER-BEFORE-FAILED-BOOTSTRAP\n"
        if action == "delete":
            ctx["plist"].unlink()
        else:
            ctx["plist"].write_bytes(peer)
        hold.unlink()
        _out, err = proc.communicate(timeout=12)
        assert proc.returncode == 78, err
        assert "EFFECT_UNKNOWN" in err
        assert ctx["plist"].exists() == (action != "delete")
        if action != "delete":
            assert ctx["plist"].read_bytes() == peer
        assert _selection(ctx) == before
        assert receipt_body(ctx)["phase"] == "BOOTSTRAP"
        assert (ctx["store"] / ".install-transaction.marker").exists()
        assert launch_log(ctx).count("bootstrap ") == 1
        assert "bootout " not in launch_log(ctx)
        assert_not_executed(ctx)
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)



@pytest.mark.parametrize("action", [
    "intact", "edit", "delete", "wrong-mode", "symlink",
])
def test_postbootstrap_success_reproves_admitted_plist(workspace, action):
    """Running PID/argv alone must not release the marker for a changed disk plist."""
    ctx = prepare(workspace)
    (ctx["stub"] / "print-mode").write_text("stopped\n")
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    original_selector = _selection(ctx)
    hold = workspace / "hold-after-bootstrap-verify"
    hold.write_text("")
    proc = subprocess.Popen(
        base_args(ctx, hold_after_bootstrap=hold),
        env=ctx["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _release_hold(proc, hold)
        installed = ctx["plist"].read_bytes()
        assert installed
        assert "bootstrap " in launch_log(ctx)
        assert (ctx["stub"] / "print-mode").read_text().strip() == "running"
        assert (ctx["stub"] / "argv").read_text() == expected_argv(ctx["lock"], ctx["pin"])
        assert (ctx["stub"] / "ps-alive").exists()
        peer = b"PEER-POST-BOOTSTRAP-PLIST\n"
        peer_file = workspace / "thirdparty-plist"
        if action == "edit":
            ctx["plist"].write_bytes(peer)
        elif action == "delete":
            ctx["plist"].unlink()
        elif action == "wrong-mode":
            ctx["plist"].chmod(0o644)
        elif action == "symlink":
            peer_file.write_bytes(peer)
            ctx["plist"].unlink()
            ctx["plist"].symlink_to(peer_file)
        hold.unlink()
        _out, err = proc.communicate(timeout=15)
        assert _selection(ctx) == original_selector
        log = launch_log(ctx)
        assert "bootout " not in log
        assert log.count("bootstrap ") == 1
        assert_not_executed(ctx)
        if action == "intact":
            assert proc.returncode == 0, err
            assert not (ctx["store"] / ".install-transaction.marker").exists()
            assert ctx["plist"].read_bytes() == installed
            assert list(ctx["backup"].glob("*.receipt")) == []
        else:
            assert proc.returncode == 78, err
            assert "EFFECT_UNKNOWN" in err
            assert "installed plist identity unproven" in err
            receipt = receipt_body(ctx)
            assert receipt["outcome"] == "EFFECT_UNKNOWN"
            assert receipt["phase"] == "POST_BOOTSTRAP_VERIFY"
            assert (ctx["store"] / ".install-transaction.marker").exists()
            if action == "edit":
                assert ctx["plist"].read_bytes() == peer
            elif action == "delete":
                assert not ctx["plist"].exists()
            elif action == "wrong-mode":
                assert ctx["plist"].read_bytes() == installed
                assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o644
            elif action == "symlink":
                assert ctx["plist"].is_symlink()
                assert ctx["plist"].read_bytes() == peer
                assert peer_file.read_bytes() == peer
    finally:
        hold.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)


def test_postbootstrap_plist_seal_guard_is_production_noninteractive(workspace):
    """A fixture pause after bootstrap is rejected outside hermetic mode."""
    candidate = DAEMON.read_text()
    assert 'elif cmd == "verify-installed-plist":' in candidate
    assert 'py verify-installed-plist "$DEST_PLIST" "$RENDERED_SHA"' in candidate
    assert 'HOLD_AFTER_BOOTSTRAP=""' in candidate
    assert '[ -z "$HOLD_AFTER_BOOTSTRAP" ]' in candidate
    assert '--hold-after-bootstrap) HOLD_AFTER_BOOTSTRAP=' in candidate



@pytest.mark.parametrize("action", ["intact", "wrong-mode", "symlink"])
def test_already_running_target_must_prove_disk_plist_identity(workspace, action):
    """Fast-path byte equality must not accept mutable symlink or mode drift."""
    ctx = prepare(workspace)
    (ctx["stub"] / "print-style").write_text("notfound\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    initial = run(ctx)
    assert initial.returncode == 0, initial.stderr
    installed = ctx["plist"].read_bytes()
    before = _selection(ctx)
    (ctx["stub"] / "launchctl.log").write_text("")
    peer_file = workspace / "identical-peer-plist"
    if action == "wrong-mode":
        ctx["plist"].chmod(0o644)
    elif action == "symlink":
        peer_file.write_bytes(installed)
        ctx["plist"].unlink()
        ctx["plist"].symlink_to(peer_file)
    second = run(ctx)
    assert _selection(ctx) == before
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)
    if action == "intact":
        assert second.returncode == 0, second.stderr
        assert ctx["plist"].read_bytes() == installed
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        assert list(ctx["backup"].glob("*.receipt")) == []
    else:
        assert second.returncode == 78, second.stderr
        assert "EFFECT_UNKNOWN" in second.stderr
        assert "installed plist identity unproven" in second.stderr
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "ALREADY_RUNNING_VERIFY"
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        assert ctx["plist"].read_bytes() == installed
        if action == "wrong-mode":
            assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o644
        else:
            assert ctx["plist"].is_symlink()
            assert peer_file.read_bytes() == installed


@pytest.mark.parametrize("action", ["intact", "wrong-mode", "symlink"])
def test_advance_from_pairs_only_after_strict_disk_plist_identity(workspace, action):
    """A matching live target cannot CAS CURRENT until disk plist is trusted.

    All paths are isolated fixture stores; no real launchd, selector or host
    service is used. These cases cover the formerly missing --advance-from
    pairing path, not merely the already-selected idempotent path.
    """
    ctx = prepare(workspace, body=b"#!/bin/bash\\nexit 71\\n")
    (ctx["stub"] / "print-style").write_text("notfound\\n")
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], ctx["pin"]))
    installed = run(ctx)
    assert installed.returncode == 0, installed.stderr
    original = ctx["release"]
    before = _selection(ctx)

    target = _reviewed_target(ctx, workspace, b"#!/bin/bash\\nexit 72\\n")
    target_pin = target / "ext" / "host_pull.sh"
    old_pin = str(ctx["pin"]).encode()
    rendered = ctx["plist"].read_bytes()
    assert rendered.count(old_pin) == 1
    admitted_target = rendered.replace(old_pin, str(target_pin).encode())
    ctx["plist"].write_bytes(admitted_target)
    ctx["plist"].chmod(0o600)
    (ctx["stub"] / "argv").write_text(expected_argv(ctx["lock"], target_pin))
    (ctx["stub"] / "launchctl.log").write_text("")

    peer_file = workspace / "advance-from-identical-peer-plist"
    if action == "wrong-mode":
        ctx["plist"].chmod(0o644)
    elif action == "symlink":
        peer_file.write_bytes(admitted_target)
        ctx["plist"].unlink()
        ctx["plist"].symlink_to(peer_file)

    result = run(ctx, generation=target.name, expect=original.name,
                 advance_from=original.name)
    final = _selection(ctx)
    assert "bootout " not in launch_log(ctx)
    assert "bootstrap " not in launch_log(ctx)
    assert_not_executed(ctx)
    assert ctx["plist"].read_bytes() == admitted_target

    if action == "intact":
        assert result.returncode == 0, result.stderr
        assert final["generation"] == target.name
        assert final["previous"] == original.name
        assert final["sequence"] == before["sequence"] + 1
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        assert list(ctx["backup"].glob("*.receipt")) == []
    else:
        assert result.returncode == 78, result.stderr
        assert "EFFECT_UNKNOWN" in result.stderr
        assert "installed plist identity unproven before selector advance" in result.stderr
        # The crucial regression: even with same bytes and matching launchctl
        # argv, a symlink or wrong-mode destination must not move CURRENT.
        assert final == before
        receipt = receipt_body(ctx)
        assert receipt["outcome"] == "EFFECT_UNKNOWN"
        assert receipt["phase"] == "ALREADY_RUNNING_VERIFY"
        assert not (ctx["store"] / ".install-transaction.marker").exists()
        if action == "wrong-mode":
            assert stat.S_IMODE(ctx["plist"].stat().st_mode) == 0o644
        else:
            assert ctx["plist"].is_symlink()
            assert peer_file.read_bytes() == admitted_target
