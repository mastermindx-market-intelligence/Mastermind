#!/usr/bin/env python3
"""Minimal `launchctl` stand-in for the team-server ops harness.

The tool under test calls `/bin/launchctl bootstrap gui/<uid>` by ABSOLUTE path,
which cannot be intercepted on PATH. That call is made harmless by faking `id`
(uid 59999 has no launchd domain, so the real call is refused), and every PATH
`launchctl` call — print, load, bootout, unload, kickstart — lands here.

`load`/`bootstrap` read ProgramArguments and StandardOutPath from the plist and
actually start the job, appending its output to the log, exactly as launchd
would (the installed runner then execs the fake server, which really serves
127.0.0.1 and really prints a banner). `print`/`bootout` are driven by marker
files in the state dir, so "loaded" survives this short-lived process just as
a real job survives its launcher.

Round 3 (FU1/FU6): the tool now runs its `load -w` / `unload -w` fallbacks
under `env -i`, which strips FAKE_LAUNCHCTL_STATE from the environment. The
state dir therefore also travels as the FIRST argv pair (`--state <dir>`,
baked into the wrapper the harness installs) — argv survives env -i. Failure
injection moved to state-dir markers for the same reason:
  <label>.BOOTSTRAP_FAIL  — `bootstrap` exits 5 (forces the load -w fallback)
  <label>.KICKSTART_FAIL  — `kickstart` exits 5 (FU6: truthful start failure)
  <label>.BOTOUT_FAIL     — `bootout`/`unload` exits 5 (panel R6)
(FAKE_LAUNCHCTL_BOTOUT_FAIL still works for the non-env-i bootout paths.)
Every invocation appends one line to <state>/invocations.log so tests can
prove a specific verb ran — and survived env -i.
"""
import os
import plistlib
import signal
import subprocess
import sys
import time


def _state_dir(argv):
    """--state <dir> as the leading argv pair, else FAKE_LAUNCHCTL_STATE."""
    if len(argv) >= 2 and argv[0] == "--state":
        return argv[1]
    return os.environ["FAKE_LAUNCHCTL_STATE"]


def marker(label, suffix):
    return os.path.join(STATE, label + suffix)


def is_loaded(label):
    return os.path.exists(marker(label, ".loaded"))


def flag(label, name):
    return os.path.exists(marker(label, "." + name))


def pid_of(label):
    try:
        with open(marker(label, ".pid")) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def stop_pid(pid):
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def clear(label):
    stop_pid(pid_of(label))
    for suffix in (".pid", ".loaded", ".plist"):
        try:
            os.unlink(marker(label, suffix))
        except OSError:
            pass


def start_from_plist(plist_path):
    with open(plist_path, "rb") as fh:
        plist = plistlib.load(fh)
    label = plist["Label"]
    if is_loaded(label):
        return 0
    argv = plist["ProgramArguments"]
    cwd = plist.get("WorkingDirectory") or None
    out = plist.get("StandardOutPath") or os.devnull
    os.makedirs(os.path.dirname(out), exist_ok=True)
    log = open(out, "ab")
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log,
            stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        log.close()
    with open(marker(label, ".pid"), "w") as fh:
        fh.write(str(proc.pid))
    with open(marker(label, ".loaded"), "w") as fh:
        fh.write(label)
    with open(marker(label, ".plist"), "w") as fh:
        fh.write(plist_path)
    return 0


def label_from_target(target):
    base = os.path.basename(target)
    if base.endswith(".plist"):
        return base[: -len(".plist")]
    return target.rsplit("/", 1)[-1]


def main(argv):
    global STATE
    STATE = _state_dir(argv)
    if argv and argv[0] == "--state":
        argv = argv[2:]
    try:
        with open(os.path.join(STATE, "invocations.log"), "a") as fh:
            fh.write(" ".join(argv) + "\n")
    except OSError:
        pass
    if not argv:
        return 2
    verb, rest = argv[0], argv[1:]
    if verb in ("load", "bootstrap"):
        plist = rest[-1]
        label = label_from_target(plist)
        if verb == "bootstrap" and flag(label, "BOOTSTRAP_FAIL"):
            # Round 3 FU1: force install/start down the env -i'd load -w
            # fallback path.
            print(f"Bootstrap failed: {label}", file=sys.stderr)
            return 5
        return start_from_plist(plist)
    if verb == "print":
        label = label_from_target(rest[-1])
        if not is_loaded(label):
            print(f"Could not find service {label}", file=sys.stderr)
            return 113
        pid = pid_of(label)
        # Real `launchctl print` names the plist the job was loaded from
        # (panel atk-7: a squatted /tmp plist under the same label).
        try:
            with open(marker(label, ".plist")) as fh:
                plist = fh.read().strip()
        except OSError:
            plist = os.path.join(
                os.path.expanduser("~/Library/LaunchAgents"), label + ".plist")
        print(f"{rest[-1]} = {{")
        print(f"\tpid = {pid if pid else 0}")
        print(f"\tpath = {plist}")
        print("\tstate = running")
        print("}")
        return 0
    if verb in ("bootout", "unload"):
        # unload takes a plist path; bootout takes gui/<uid>/<label>
        label = label_from_target(rest[-1])
        if not is_loaded(label):
            return 113
        if flag(label, "BOTOUT_FAIL") or os.environ.get(
                "FAKE_LAUNCHCTL_BOTOUT_FAIL"):
            # Panel R6: launchd refuses to boot the job out — the tool must
            # not report the label gone.
            print(f"Bootout failed: {label}", file=sys.stderr)
            return 5
        clear(label)
        return 0
    if verb == "kickstart":
        label = label_from_target(rest[-1])
        if not is_loaded(label):
            return 113
        if flag(label, "KICKSTART_FAIL"):
            # Round 3 FU6: kickstart fails on a loaded, running job.
            print(f"Kickstart failed: {label}", file=sys.stderr)
            return 5
        return 0
    print(f"fake_launchctl: unsupported verb {verb}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
