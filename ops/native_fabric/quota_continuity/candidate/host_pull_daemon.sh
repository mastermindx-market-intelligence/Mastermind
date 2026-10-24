#!/bin/bash
# host_pull_daemon.sh — source-controlled candidate for the original Fabric
# host-pull LaunchAgent lifecycle (flat ext/host_pull_daemon.sh).
#
# NOT INSTALLABLE FROM THIS FILE ALONE. This candidate and its plist template
# sit outside the sealed 95-member native manifest. native_generation.file_name()
# rejects a plist template (it is not ext/*.py, ext/*.sh, or a named exception).
# A separate native-policy integration gate — manifest admission plus a
# file_name() policy change, reconciled with the open manifest pins — is
# required before any host install. Running install-agent from this draft is
# not authorized and is not a sealed generation install.
#
# When that gate exists, install-agent still never reads a caller-supplied
# collector path. The only collector it will pin is
#   <native-code-releases>/<verified-64hex>/ext/host_pull.sh
# and only after native_generation.py verify, a CURRENT.json compare under the
# original publication lock immediately before each effect, and owner, mode,
# path, and RELEASE descriptor checks.
#
# Single-collector exclusion is /usr/bin/lockf -t 0 (contention status 75).
# This lifecycle does not use a pid-file check-then-write. Launchd state is
# loaded, definitively service-not-found, or uncertain. Uncertain fails closed
# (78) and is never treated as an absent label.

set -u
set -o pipefail

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LABEL="com.mastermind.host-pull"
PHASE=START
HERMETIC=0
HAD_PLIST=0
BACKUP=""
DEST_PLIST=""
RENDERED=""
BOOTSTRAP_NEW=0
BOOTSTRAP_ROLLBACK=0
BOOTED=0
WAIT_LIMIT=50
ADMIT_PID=""
ADMIT_RELEASE=""
FAULT=""

release_admission() {
  if [ -n "${ADMIT_RELEASE:-}" ]; then
    : > "$ADMIT_RELEASE" 2>/dev/null || true
  fi
  if [ -n "${ADMIT_PID:-}" ]; then
    wait "$ADMIT_PID" 2>/dev/null || true
    ADMIT_PID=""
  fi
  ADMIT_RELEASE=""
}

die() {
  local code=$1
  shift
  release_admission
  if [ -n "${RENDERED:-}" ]; then
    rm -f -- "$RENDERED"
  fi
  printf 'HOST_PULL_LIFECYCLE_REFUSED: %s\n' "$*" >&2
  exit "$code"
}

restore_plist() {
  [ -n "$DEST_PLIST" ] || return 1
  if [ "$HAD_PLIST" -eq 1 ]; then
    [ -n "$BACKUP" ] && [ -f "$BACKUP" ] || return 1
    py atomic-restore "$BACKUP" "$DEST_PLIST" || return 1
  else
    py atomic-remove "$DEST_PLIST" || return 1
  fi
}

on_signal() {
  local code=$1
  trap - TERM HUP INT
  release_admission
  case "$PHASE" in
    START|VERIFIED|BACKED_UP)
      exit "$code"
      ;;
    PLIST_REPLACED)
      # The signal itself makes launchd timing uncertain. Restore the plist
      # bytes and report a stopped receipt. Do not bootstrap.
      restore_plist || true
      write_receipt EFFECT_UNKNOWN "signal-$PHASE" "signal during $PHASE" || true
      exit 78
      ;;
    *)
      # Bootout, pid wait, or bootstrap already started. Another launchctl
      # call would be a second mutation against an unknown job state.
      write_receipt EFFECT_UNKNOWN "signal-$PHASE" "signal during $PHASE" || true
      exit 78
      ;;
  esac
}

trap 'on_signal 143' TERM
trap 'on_signal 130' INT
trap 'on_signal 129' HUP

usage() {
  die 78 "usage: host_pull_daemon.sh install-agent|collect --store DIR --generation HEX --expect-current HEX --publisher native_generation.py ..."
}

py() {
  python3 - "$@" <<'PY'
import fcntl, hashlib, json, os, re, stat, subprocess, sys, tempfile, time

cmd = sys.argv[1]
SAFE = re.compile(r"/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*\Z")
SERVICE_PATH = re.compile(
    r"/(?:[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*)"
    r"(?::/(?:[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*))*\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")

def fail(message):
    sys.stderr.write(message + "\n")
    raise SystemExit(78)

def require_safe(path, label):
    if type(path) is not str or SAFE.fullmatch(path) is None or path != os.path.abspath(path):
        fail("unsafe " + label)

def lstat_nofollow(path):
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        fail("symlink refused: " + path)
    return st

if cmd == "check-pin":
    store, generation, expect, publisher, pin = sys.argv[2:7]
    owner_required = int(sys.argv[7])
    require_safe(store, "store")
    require_safe(pin, "pin")
    require_safe(publisher, "publisher")
    if HEX.fullmatch(generation) is None or HEX.fullmatch(expect) is None:
        fail("generation identity")
    if os.path.basename(store) != "native-code-releases":
        fail("store name")
    if os.path.basename(publisher) != "native_generation.py":
        fail("publisher name")
    expected_pin = store + "/" + generation + "/ext/host_pull.sh"
    if pin != expected_pin:
        fail("pin is not the verified generation collector")
    for path in (store, publisher):
        st = lstat_nofollow(path)
        if not stat.S_ISDIR(st.st_mode) and path == store:
            fail("store kind")
        if path == publisher and not stat.S_ISREG(st.st_mode):
            fail("publisher kind")
        if st.st_uid != os.geteuid():
            fail("owner")
    st_store = lstat_nofollow(store)
    if stat.S_IMODE(st_store.st_mode) != 0o700:
        fail("store mode")
    current_path = store + "/CURRENT.json"
    st_cur = lstat_nofollow(current_path)
    if not stat.S_ISREG(st_cur.st_mode) or stat.S_IMODE(st_cur.st_mode) != 0o600:
        fail("current mode")
    if st_cur.st_uid != os.geteuid():
        fail("current owner")
    current = json.loads(open(current_path, "rb").read().decode("utf-8"))
    if (not isinstance(current, dict) or current.get("schema") != "native-code-selection.v1"
            or current.get("generation") != generation or current.get("generation") != expect
            or type(current.get("sequence")) is not int or current["sequence"] < 1
            or set(current) != {"schema", "generation", "sequence", "previous"}):
        fail("generation is not the selected current")
    previous = current["previous"]
    if previous is not None and (type(previous) is not str or HEX.fullmatch(previous) is None):
        fail("current previous")
    release_path = store + "/" + generation + "/RELEASE.json"
    st_rel = lstat_nofollow(release_path)
    if not stat.S_ISREG(st_rel.st_mode) or stat.S_IMODE(st_rel.st_mode) != 0o444:
        fail("release mode")
    if st_rel.st_uid != owner_required:
        fail("release owner")
    release = json.loads(open(release_path, "rb").read().decode("utf-8"))
    if (not isinstance(release, dict) or release.get("schema") != "native-code-generation.v1"
            or release.get("digest") != generation
            or not isinstance(release.get("files"), dict)
            or release["files"].get("ext/host_pull.sh") is None):
        fail("release descriptor")
    entry = release.get("entrypoints")
    if (not isinstance(entry, dict) or entry.get("pool") != "pool"
            or entry.get("task") != "ext/fabric_task.py"
            or entry.get("remote") != "ext/remote_sub.sh"):
        fail("release entrypoints")
    stable = release.get("stable_ext")
    if type(stable) is not str or os.path.abspath(stable) != os.path.dirname(store) + "/ext":
        fail("release stable_ext")
    links = release.get("links")
    if not isinstance(links, dict) or not links:
        fail("release links")
    st_pin = lstat_nofollow(pin)
    if not stat.S_ISREG(st_pin.st_mode):
        fail("pin kind")
    if st_pin.st_uid != owner_required:
        fail("pin owner")
    if stat.S_IMODE(st_pin.st_mode) != 0o555:
        fail("pin mode")
    raw = open(pin, "rb").read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != release["files"]["ext/host_pull.sh"]:
        fail("pin digest mismatch")
    # Every path component of the pin below the store must be a real directory
    # or the regular file, never a symlink.
    cursor = store
    for part in (generation, "ext", "host_pull.sh"):
        cursor = cursor + "/" + part
        lstat_nofollow(cursor)
    sys.stdout.write(digest + "\n")

elif cmd == "render":
    template, dest, pin, log_path, lock_path, service_path = sys.argv[2:8]
    for label, path in (("pin", pin), ("log", log_path), ("lock", lock_path),
                        ("template", template), ("dest", dest)):
        require_safe(path, label)
    if SERVICE_PATH.fullmatch(service_path) is None:
        fail("service path")
    if os.path.basename(os.path.dirname(dest)) != "LaunchAgents":
        fail("plist destination")
    if not dest.endswith("/com.mastermind.host-pull.plist"):
        fail("plist name")
    if "LaunchAgents" in lock_path.split("/") or "LaunchAgents" in log_path.split("/"):
        fail("lock or log inside LaunchAgents")
    text = open(template, "r", encoding="utf-8").read()
    lstat_nofollow(template)
    for marker in ("__HOST_PULL__", "__STDOUT_LOG__", "__STDERR_LOG__", "__PATH__", "__LOCK__"):
        if text.count(marker) != 1:
            fail("template marker " + marker)
    # Stdout and stderr share one operator log. Distinct markers keep the
    # exactly-once substitution check honest; a shared __LOG__ token cannot.
    values = {"__HOST_PULL__": pin, "__STDOUT_LOG__": log_path, "__STDERR_LOG__": log_path,
              "__PATH__": service_path, "__LOCK__": lock_path}
    for marker, value in values.items():
        if any(ch in value for ch in "&<>\"'"):
            fail("xml value")
        text = text.replace(marker, value)
    if "__" in text or text.count(pin) != 1 or "host_pull.sh" in text.replace(pin, ""):
        fail("rendered pin")
    if text.count(log_path) != 2:
        fail("rendered log")
    if text.count("/usr/bin/lockf") != 1 or "\n    <string>-t</string>\n    <string>0</string>\n" not in text:
        fail("rendered lockf")
    parent = os.path.dirname(dest)
    st_parent = lstat_nofollow(parent)
    if not stat.S_ISDIR(st_parent.st_mode) or st_parent.st_uid != os.geteuid():
        fail("plist dir")
    fd, name = tempfile.mkstemp(prefix="host-pull-render-", dir=os.environ.get("TMPDIR") or "/tmp")
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    sys.stdout.write(name + "\n")

elif cmd == "backup":
    src, directory, generation = sys.argv[2:5]
    require_safe(src, "plist")
    require_safe(directory, "backup")
    if HEX.fullmatch(generation) is None:
        fail("generation identity")
    if "LaunchAgents" in directory.split("/") or os.path.dirname(src) == directory:
        fail("backup location")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    st_dir = lstat_nofollow(directory)
    if stat.S_ISDIR(st_dir.st_mode) and not stat.S_ISLNK(st_dir.st_mode):
        if stat.S_IMODE(st_dir.st_mode) != 0o700:
            os.chmod(directory, 0o700)
            st_dir = lstat_nofollow(directory)
    if not stat.S_ISDIR(st_dir.st_mode) or stat.S_IMODE(st_dir.st_mode) != 0o700:
        fail("backup dir mode")
    if st_dir.st_uid != os.geteuid():
        fail("backup owner")
    st = lstat_nofollow(src)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600:
        fail("plist preimage")
    raw = open(src, "rb").read()
    target = directory + "/com.mastermind.host-pull.plist.pre-" + generation
    if os.path.lexists(target):
        fail("backup already exists")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    digest = hashlib.sha256(raw).hexdigest()
    if hashlib.sha256(open(target, "rb").read()).hexdigest() != digest:
        fail("backup readback")
    sys.stdout.write(target + "\n" + digest + "\n")

elif cmd == "install-rendered":
    src, dest = sys.argv[2:4]
    fault = sys.argv[4] if len(sys.argv) > 4 else ""
    if fault not in ("", "before-replace", "after-replace"):
        fail("install fault")
    require_safe(src, "rendered")
    require_safe(dest, "plist")
    st = lstat_nofollow(src)
    if not stat.S_ISREG(st.st_mode):
        fail("rendered kind")
    raw = open(src, "rb").read()
    if fault == "before-replace":
        fail("injected install failure before replace")
    if os.path.lexists(dest):
        st_dest = lstat_nofollow(dest)
        if not stat.S_ISREG(st_dest.st_mode):
            fail("plist kind")
    parent = os.path.dirname(dest)
    temporary = parent + "/.host-pull.plist." + str(os.getpid())
    if os.path.lexists(temporary):
        fail("plist temporary exists")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, dest)
    if fault == "after-replace":
        fail("injected install failure after replace")
    fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
        installed = os.read(fd, len(raw) + 1)
    finally:
        os.close(fd)
    if installed != raw:
        fail("plist readback")
    dirfd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)

elif cmd == "atomic-restore":
    src, dest = sys.argv[2:4]
    raw = open(src, "rb").read()
    parent = os.path.dirname(dest)
    temporary = parent + "/.host-pull.restore." + str(os.getpid())
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, dest)
    fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
        installed = os.read(fd, len(raw) + 1)
    finally:
        os.close(fd)
    if installed != raw or stat.S_IMODE(os.lstat(dest).st_mode) != 0o600:
        fail("restore readback")

elif cmd == "atomic-remove":
    dest = sys.argv[2]
    if os.path.lexists(dest):
        st = os.lstat(dest)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            fail("remove kind")
        os.unlink(dest)

elif cmd == "same-file":
    left, right = sys.argv[2:4]
    try:
        same = open(left, "rb").read() == open(right, "rb").read()
    except OSError:
        fail("plist drift")
    if not same:
        fail("plist drift")

elif cmd == "parse-launchctl":
    # Tri-state only: loaded-running, loaded-idle, or absent. Anything else,
    # including a loose "not found" and a bare "state = not running", is
    # uncertain and fails closed. absent is only the exact service-not-found
    # error for this label, or the hermetic V1 absent record.
    rc = int(sys.argv[2])
    out = open(sys.argv[3], "r", encoding="utf-8", errors="replace").read()
    err = open(sys.argv[4], "r", encoding="utf-8", errors="replace").read()
    absent_stderr = re.compile(
        r"(?:Bad request\.\n)?"
        r"Could not find service \"com\.mastermind\.host-pull\" "
        r"in domain for user gui: [0-9]+\n?\Z")
    header_re = re.compile(
        r"(?m)^(?:gui/[0-9]+|user/[0-9]+|system)/com\.mastermind\.host-pull = \{$")

    def emit(state, pid, argv):
        sys.stdout.write(state + "\n")
        sys.stdout.write((pid or "") + "\n")
        for arg in argv:
            if "\n" in arg or arg == "":
                fail("launchctl argv")
            sys.stdout.write(arg + "\n")

    def refuse():
        fail("launchctl state uncertain")

    lines = out.splitlines()
    if lines and lines[0] == "HOST_PULL_LAUNCHCTL_V1":
        if rc != 0 or err.strip():
            refuse()
        state = activity = pid = None
        argv = []
        seen = set()
        for line in lines[1:]:
            if line.startswith("argv="):
                argv.append(line.split("=", 1)[1])
                continue
            key, sep, value = line.partition("=")
            if sep != "=" or key in seen or key not in {"state", "activity", "pid"}:
                refuse()
            seen.add(key)
            if key == "state":
                state = value
            elif key == "activity":
                activity = value
            else:
                pid = value
        if seen != {"state", "activity", "pid"}:
            refuse()
        if state == "absent" and activity == "none" and pid == "" and not argv:
            emit("absent", "", [])
        elif (state == "loaded" and activity == "running"
              and re.fullmatch(r"[1-9][0-9]*", pid or "") and argv):
            emit("loaded-running", pid, argv)
        elif state == "loaded" and activity == "idle" and pid == "" and not argv:
            emit("loaded-idle", "", [])
        else:
            refuse()
        raise SystemExit(0)
    if rc != 0:
        if out.strip() == "" and absent_stderr.fullmatch(err):
            emit("absent", "", [])
            raise SystemExit(0)
        refuse()
    if err.strip() or re.search(r"not found|Could not find service", out, re.IGNORECASE):
        refuse()
    headers = header_re.findall(out)
    running_n = len(re.findall(r"(?m)^\s*state = running\s*$", out))
    idle_n = len(re.findall(r"(?m)^\s*state = not running\s*$", out))
    pid_lines = re.findall(r"(?m)^\s*pid = ([0-9]+)\s*$", out)
    if len(headers) != 1 or out.count("arguments = {") > 1 or len(pid_lines) > 1:
        refuse()
    argv = []
    if "arguments = {" in out:
        block = out.split("arguments = {", 1)[1].split("}", 1)
        if len(block) != 2:
            refuse()
        for line in block[0].splitlines():
            item = line.strip()
            if item:
                argv.append(item)
    if (running_n == 1 and idle_n == 0 and len(pid_lines) == 1
            and int(pid_lines[0]) > 0 and argv):
        emit("loaded-running", pid_lines[0], argv)
    elif idle_n == 1 and running_n == 0 and not pid_lines:
        emit("loaded-idle", "", [])
    else:
        refuse()

elif cmd == "paths-ready":
    for path in sys.argv[2:]:
        require_safe(path, "path")
        parent = os.path.dirname(path)
        st = lstat_nofollow(parent)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            fail("parent")
        if os.path.lexists(path):
            st_path = lstat_nofollow(path)
            if stat.S_ISDIR(st_path.st_mode):
                fail("path kind")

elif cmd == "under-root":
    root, found = sys.argv[2:4]
    root = os.path.realpath(root)
    found_real = os.path.realpath(found)
    if os.path.lexists(found):
        if stat.S_ISLNK(os.lstat(found).st_mode):
            fail("tool symlink")
    if found_real != found or not (found_real == root or found_real.startswith(root + "/")):
        fail("tool escaped fixture")
    if not os.path.isfile(found_real) or not os.access(found_real, os.X_OK):
        fail("tool")

elif cmd == "admit-hold":
    # Hold the original publication lock (store/.publication.lock, exclusive,
    # non-blocking, mode 0600) across one effect and prove CURRENT still names
    # this generation. Verify goes through the publisher CLI so a wrapper is
    # exercised as a program, not imported. This does not select or publish.
    store, generation, expect, publisher, held_path, release_path = sys.argv[2:8]
    require_safe(store, "store")
    require_safe(publisher, "publisher")
    require_safe(held_path, "admit held")
    require_safe(release_path, "admit release")
    if HEX.fullmatch(generation) is None or HEX.fullmatch(expect) is None:
        fail("generation identity")
    if os.path.basename(publisher) != "native_generation.py":
        fail("publisher name")
    if os.path.basename(store) != "native-code-releases":
        fail("store name")
    lock_path = store + "/.publication.lock"
    try:
        lock_fd = os.open(
            lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as exc:
        fail("admission refused: " + str(exc))
    try:
        observed = os.fstat(lock_fd)
        if (not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid()
                or stat.S_IMODE(observed.st_mode) != 0o600):
            fail("admission refused: invalid publication lock")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("admission refused: native publication already in progress")
        current_path = store + "/CURRENT.json"
        st_cur = lstat_nofollow(current_path)
        if (not stat.S_ISREG(st_cur.st_mode) or stat.S_IMODE(st_cur.st_mode) != 0o600
                or st_cur.st_uid != os.geteuid()):
            fail("admission refused: current")
        selected = json.loads(open(current_path, "rb").read().decode("utf-8"))
        if (not isinstance(selected, dict) or selected.get("schema") != "native-code-selection.v1"
                or selected.get("generation") != generation
                or selected.get("generation") != expect
                or type(selected.get("sequence")) is not int or selected["sequence"] < 1
                or set(selected) != {"schema", "generation", "sequence", "previous"}):
            fail("selector moved")
        verified = subprocess.run(
            [sys.executable, publisher, "verify", "--store", store, "--generation", generation],
            check=False, capture_output=True, text=True)
        if verified.returncode != 0:
            fail("admission refused: publisher verify failed")
        try:
            body = json.loads(verified.stdout)
        except json.JSONDecodeError:
            fail("admission refused: publisher verify output")
        if body.get("digest") != generation or not str(body.get("path", "")):
            fail("admission refused: publisher verify output")
        held_fd = os.open(held_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(held_fd)
        while not os.path.exists(release_path):
            if os.getppid() == 1:
                break
            time.sleep(0.05)
    finally:
        os.close(lock_fd)

elif cmd == "write-receipt":
    directory, generation, outcome, phase, reason = sys.argv[2:7]
    require_safe(directory, "receipt dir")
    if HEX.fullmatch(generation) is None:
        fail("generation identity")
    if outcome not in {"RECOVERED", "EFFECT_UNKNOWN"}:
        fail("receipt outcome")
    if re.fullmatch(r"[A-Za-z0-9._+-]{1,80}", phase) is None:
        fail("receipt phase")
    if "\n" in reason or len(reason) > 200:
        fail("receipt reason")
    st_dir = lstat_nofollow(directory)
    if not stat.S_ISDIR(st_dir.st_mode) or stat.S_IMODE(st_dir.st_mode) != 0o700:
        fail("receipt dir mode")
    service = "restored" if outcome == "RECOVERED" else "stopped-uncertain"
    body = json.dumps({
        "schema": "host-pull-lifecycle-receipt.v1",
        "outcome": outcome,
        "phase": phase,
        "service": service,
        "reason": reason,
    }, separators=(",", ":")).encode("utf-8") + b"\n"
    target = (directory + "/com.mastermind.host-pull.lifecycle-"
              + generation + "-" + phase + ".receipt")
    require_safe(target, "receipt")
    if os.path.lexists(target):
        fail("receipt already exists")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)

elif cmd == "not-user-launchagents":
    path = sys.argv[2]
    home = os.path.realpath(os.path.expanduser("~"))
    real = os.path.realpath(path)
    banned = home + "/Library/LaunchAgents"
    if real == banned or real.startswith(banned + "/"):
        fail("hermetic refuses the user LaunchAgents directory")

else:
    fail("unknown helper")
PY
}

hold_if_requested() {
  local flag=$1
  [ -n "$flag" ] || return 0
  [ "$HERMETIC" -eq 1 ] || die 78 "hold is hermetic-only"
  : > "${flag}.ready"
  while [ -e "$flag" ]; do
    sleep 0.05
  done
}

resolve_tool() {
  local name=$1 expected=$2
  local found
  found=$(command -v "$name" 2>/dev/null) || die 78 "missing $name"
  if [ "$HERMETIC" -eq 1 ]; then
    py under-root "$FIXTURE_ROOT" "$found" || die 78 "hermetic $name is not a fixture"
  else
    [ "$found" = "$expected" ] || die 78 "refusing $name at $found"
  fi
  TOOL_PATH=$found
}

parse_launchctl() {
  local rc=$1 out=$2 err=$3
  local parsed
  parsed=$(py parse-launchctl "$rc" "$out" "$err") || return 1
  LC_CLASS=$(printf '%s\n' "$parsed" | sed -n '1p')
  LC_PID=$(printf '%s\n' "$parsed" | sed -n '2p')
  LC_ARGV=$(printf '%s\n' "$parsed" | sed -n '1,2d;p')
  case "$LC_CLASS" in
    absent|loaded-running|loaded-idle) return 0 ;;
  esac
  return 1
}

launchctl_print() {
  local out err rc
  out=$(mktemp "${TMPDIR:-/tmp}/host-pull-lc-out.XXXXXX")
  err=$(mktemp "${TMPDIR:-/tmp}/host-pull-lc-err.XXXXXX")
  "$LAUNCHCTL" print "$DOMAIN/$LABEL" >"$out" 2>"$err"
  rc=$?
  if ! parse_launchctl "$rc" "$out" "$err"; then
    rm -f -- "$out" "$err"
    LC_CLASS=uncertain
    LC_PID=""
    LC_ARGV=""
    return 1
  fi
  rm -f -- "$out" "$err"
  return 0
}

ps_state() {
  local pid=$1 out rc observed
  out=$(mktemp "${TMPDIR:-/tmp}/host-pull-ps.XXXXXX")
  "$PS" -p "$pid" -o pid= >"$out" 2>"$out.err"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    observed=$(tr -cd '0-9' <"$out")
    rm -f -- "$out" "$out.err"
    if [ "$observed" != "$pid" ]; then
      PS_RESULT=uncertain
      return 0
    fi
    PS_RESULT=alive
    return 0
  fi
  if [ "$rc" -eq 1 ] && [ ! -s "$out" ]; then
    rm -f -- "$out" "$out.err"
    PS_RESULT=dead
    return 0
  fi
  rm -f -- "$out" "$out.err"
  PS_RESULT=uncertain
  return 0
}

wait_pid_dead() {
  local pid=$1 i=0
  if [ "$FAULT" = "wait-pid" ]; then
    return 2
  fi
  while [ "$i" -lt "$WAIT_LIMIT" ]; do
    ps_state "$pid"
    [ "$PS_RESULT" = "dead" ] && return 0
    [ "$PS_RESULT" = "uncertain" ] && return 2
    i=$((i + 1))
    if [ "$HERMETIC" -eq 0 ]; then
      sleep 0.1
    fi
  done
  return 1
}

write_receipt() {
  local outcome=$1 phase=$2
  shift 2
  [ -n "${BACKUP_DIR:-}" ] || return 1
  py write-receipt "$BACKUP_DIR" "$GENERATION" "$outcome" "$phase" "$*"
}

stop_uncertain() {
  local phase=$1
  shift
  local reason="$*"
  release_admission
  if [ "$PHASE" = "PLIST_REPLACED" ]; then
    restore_plist || true
  fi
  write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
  die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
}

recover_or_stop() {
  local phase=$1
  shift
  local reason="$*"
  local rc
  release_admission
  if [ "$BOOTED" -ne 1 ]; then
    die 78 "admission refused: $reason"
  fi
  # A known-absent label can take the original plist back. Any other read
  # is uncertain: restore bytes when we already replaced them, and do not
  # bootstrap.
  if ! launchctl_print || [ "$LC_CLASS" != "absent" ]; then
    if [ "$PHASE" = "PLIST_REPLACED" ]; then
      restore_plist || true
    fi
    write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
    die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
  fi
  restore_plist || {
    write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
    die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
  }
  if ! launchctl_print || [ "$LC_CLASS" != "absent" ]; then
    write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
    die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
  fi
  bootstrap_once rollback
  rc=$?
  if [ "$rc" -ne 0 ]; then
    write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
    die 78 "EFFECT_UNKNOWN rollback bootstrap failed: $reason"
  fi
  if ! launchctl_print; then
    write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
    die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
  fi
  case "$LC_CLASS" in
    loaded-running|loaded-idle) ;;
    *)
      write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
      die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
      ;;
  esac
  write_receipt RECOVERED "$phase" "$reason" || die 78 "receipt failed"
  die 78 "recovered original service: $reason"
}

admit_effect() {
  local dir held i
  release_admission
  dir=$(mktemp -d "${TMPDIR:-/tmp}/host-pull-admit.XXXXXX") || return 1
  ADMIT_RELEASE="$dir/release"
  held="$dir/held"
  py admit-hold "$STORE" "$GENERATION" "$EXPECT_CURRENT" "$PUBLISHER" "$held" "$ADMIT_RELEASE" &
  ADMIT_PID=$!
  i=0
  while [ ! -f "$held" ]; do
    # Signal 0 probes the admission helper only. It is not a collector pid check.
    if ! kill -s 0 -- "$ADMIT_PID" 2>/dev/null; then
      wait "$ADMIT_PID" 2>/dev/null || true
      ADMIT_PID=""
      return 1
    fi
    i=$((i + 1))
    if [ "$i" -ge 200 ]; then
      release_admission
      return 1
    fi
    sleep 0.05
  done
  return 0
}

expected_argv() {
  printf '%s\n' /usr/bin/lockf -t 0 "$LOCK" /bin/bash "$PIN"
}

argv_matches() {
  local want have
  want=$(expected_argv)
  have=$LC_ARGV
  [ "$want" = "$have" ]
}

bootstrap_once() {
  local kind=$1
  if [ "$kind" = "new" ]; then
    [ "$BOOTSTRAP_NEW" -eq 0 ] || die 78 "second bootstrap refused"
    BOOTSTRAP_NEW=1
    PHASE=BOOTSTRAP_STARTED
    "$LAUNCHCTL" bootstrap "$DOMAIN" "$DEST_PLIST"
    return $?
  fi
  [ "$BOOTSTRAP_ROLLBACK" -eq 0 ] || die 78 "second rollback bootstrap refused"
  BOOTSTRAP_ROLLBACK=1
  PHASE=ROLLING_BACK
  "$LAUNCHCTL" bootstrap "$DOMAIN" "$DEST_PLIST"
  return $?
}

require_verified_pin() {
  local owner
  local verr verify_out
  owner=$(id -u)
  if [ "$HERMETIC" -eq 1 ] && [ -n "${EXPECT_OWNER_UID:-}" ]; then
    owner=$EXPECT_OWNER_UID
  fi
  case $owner in
    ''|*[!0-9]*) die 78 "owner uid" ;;
  esac
  PIN="$STORE/$GENERATION/ext/host_pull.sh"
  py check-pin "$STORE" "$GENERATION" "$EXPECT_CURRENT" "$PUBLISHER" "$PIN" "$owner" >/dev/null \
    || die 78 "pin checks failed"
  verr=$(mktemp "${TMPDIR:-/tmp}/host-pull-verify.XXXXXX")
  verify_out=$("$PYTHON" "$PUBLISHER" verify --store "$STORE" --generation "$GENERATION" 2>"$verr") \
    || { rm -f -- "$verr"; die 78 "publisher verify failed"; }
  rm -f -- "$verr"
  "$PYTHON" -c 'import json,sys
body=json.loads(sys.argv[1])
if body.get("digest")!=sys.argv[2] or not str(body.get("path","")):
    raise SystemExit(78)' "$verify_out" "$GENERATION" \
    || die 78 "publisher verify output"
  # Re-read after verify so a generation that changes between the two checks
  # cannot be pinned.
  py check-pin "$STORE" "$GENERATION" "$EXPECT_CURRENT" "$PUBLISHER" "$PIN" "$owner" >/dev/null \
    || die 78 "pin checks failed after verify"
  PHASE=VERIFIED
}

COMMAND=${1:-}
[ -n "$COMMAND" ] || usage
shift

STORE=""
GENERATION=""
EXPECT_CURRENT=""
PUBLISHER=""
DEST_PLIST=""
LOG_PATH=""
LOCK=""
SERVICE_PATH=""
BACKUP_DIR=""
FIXTURE_ROOT=""
TEMPLATE=""
HOLD_MUTATION=""
HOLD_BOOTSTRAP=""
HOLD_BOOTOUT=""
HOLD_PLIST=""
EXPECT_OWNER_UID=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --store) STORE=${2:-}; shift 2 ;;
    --generation) GENERATION=${2:-}; shift 2 ;;
    --expect-current) EXPECT_CURRENT=${2:-}; shift 2 ;;
    --publisher) PUBLISHER=${2:-}; shift 2 ;;
    --plist) DEST_PLIST=${2:-}; shift 2 ;;
    --log) LOG_PATH=${2:-}; shift 2 ;;
    --lock) LOCK=${2:-}; shift 2 ;;
    --service-path) SERVICE_PATH=${2:-}; shift 2 ;;
    --backup-dir) BACKUP_DIR=${2:-}; shift 2 ;;
    --fixture-root) FIXTURE_ROOT=${2:-}; shift 2 ;;
    --template) TEMPLATE=${2:-}; shift 2 ;;
    --hold-before-mutation) HOLD_MUTATION=${2:-}; shift 2 ;;
    --hold-before-bootout) HOLD_BOOTOUT=${2:-}; shift 2 ;;
    --hold-before-plist) HOLD_PLIST=${2:-}; shift 2 ;;
    --hold-before-bootstrap) HOLD_BOOTSTRAP=${2:-}; shift 2 ;;
    --expect-owner-uid) EXPECT_OWNER_UID=${2:-}; shift 2 ;;
    --fault) FAULT=${2:-}; shift 2 ;;
    --wait-limit) WAIT_LIMIT=${2:-}; shift 2 ;;
    --hermetic) HERMETIC=1; shift ;;
    --program|--pidfile) die 78 "program and pidfile inputs are refused" ;;
    *) usage ;;
  esac
done

[ -n "$STORE" ] && [ -n "$GENERATION" ] && [ -n "$EXPECT_CURRENT" ] && [ -n "$PUBLISHER" ] || usage
PYTHON=$(command -v python3) || die 78 "python3 required"
case $WAIT_LIMIT in
  ''|*[!0-9]*) die 78 "wait limit" ;;
esac
if [ "$HERMETIC" -eq 1 ]; then
  [ -n "$FIXTURE_ROOT" ] || die 78 "hermetic fixture root required"
  [ "$WAIT_LIMIT" -le 200 ] || die 78 "wait limit"
  case "$FAULT" in
    ""|wait-pid|post-bootout-print|install-before-replace|install-after-replace|pre-bootstrap-print) ;;
    *) die 78 "unknown fault" ;;
  esac
else
  [ -z "$FIXTURE_ROOT" ] || die 78 "fixture root is hermetic-only"
  [ -z "$HOLD_MUTATION" ] && [ -z "$HOLD_BOOTSTRAP" ] && [ -z "$HOLD_BOOTOUT" ] \
    && [ -z "$HOLD_PLIST" ] && [ -z "$EXPECT_OWNER_UID" ] && [ -z "$FAULT" ] \
    || die 78 "test hooks are hermetic-only"
  [ "$WAIT_LIMIT" -eq 50 ] || die 78 "wait limit"
fi

DOMAIN="gui/$(id -u)"
case $DOMAIN in
  gui/[0-9]*) ;;
  *) die 78 "launchd domain" ;;
esac

case "$COMMAND" in
  collect)
    [ -n "$LOCK" ] || usage
    [ -z "$DEST_PLIST" ] && [ -z "$LOG_PATH" ] && [ -z "$SERVICE_PATH" ] || usage
    require_verified_pin
    py paths-ready "$LOCK" || die 78 "lock path"
    resolve_tool lockf /usr/bin/lockf
    LOCKF=$TOOL_PATH
    hold_if_requested "$HOLD_MUTATION"
    # exec transfers signals to lockf. A collector that cannot take the lock
    # returns lockf's status, including 75 when the single collector is held.
    exec "$LOCKF" -t 0 "$LOCK" /bin/bash "$PIN"
    ;;
  install-agent)
    [ -n "$DEST_PLIST" ] && [ -n "$LOG_PATH" ] && [ -n "$LOCK" ] && [ -n "$SERVICE_PATH" ] || usage
    if [ "$HERMETIC" -eq 1 ]; then
      py not-user-launchagents "$DEST_PLIST" || die 78 "hermetic launch agents path"
    fi
    resolve_tool launchctl /bin/launchctl
    LAUNCHCTL=$TOOL_PATH
    resolve_tool ps /bin/ps
    PS=$TOOL_PATH
    TEMPLATE=${TEMPLATE:-$HERE/launchd/com.mastermind.host-pull.plist.template}
    require_verified_pin
    py paths-ready "$LOCK" "$LOG_PATH" || die 78 "lock or log path"
    if [ -z "$BACKUP_DIR" ]; then
      BACKUP_DIR=$(dirname -- "$(dirname -- "$DEST_PLIST")")/com.mastermind.host-pull-plist-backups
    fi
    RENDERED=$(py render "$TEMPLATE" "$DEST_PLIST" "$PIN" "$LOG_PATH" "$LOCK" "$SERVICE_PATH") \
      || die 78 "render failed"
    launchctl_print || die 78 "launchctl state uncertain"
    NEED_BOOTOUT=0
    case "$LC_CLASS" in
      loaded-running)
        ps_state "$LC_PID"
        [ "$PS_RESULT" = "alive" ] || die 78 "process state uncertain"
        if argv_matches && py same-file "$RENDERED" "$DEST_PLIST"; then
          rm -f -- "$RENDERED"
          exit 0
        fi
        if argv_matches; then
          die 78 "launchctl and plist disagree"
        fi
        NEED_BOOTOUT=1
        ;;
      loaded-idle)
        NEED_BOOTOUT=1
        ;;
      absent)
        NEED_BOOTOUT=0
        ;;
      *)
        die 78 "launchctl state uncertain"
        ;;
    esac
    hold_if_requested "$HOLD_MUTATION"
    if [ -e "$DEST_PLIST" ]; then
      HAD_PLIST=1
      backup_out=$(py backup "$DEST_PLIST" "$BACKUP_DIR" "$GENERATION") || die 78 "backup failed"
      BACKUP=$(printf '%s\n' "$backup_out" | sed -n '1p')
    elif [ "$NEED_BOOTOUT" -eq 1 ]; then
      die 78 "running service has no plist preimage"
    fi
    PHASE=BACKED_UP
    if [ "$NEED_BOOTOUT" -eq 1 ]; then
      hold_if_requested "$HOLD_BOOTOUT"
      if ! admit_effect; then
        die 78 "selector moved before bootout"
      fi
      OLD_PID=$LC_PID
      PHASE=BOOTOUT_STARTED
      "$LAUNCHCTL" bootout "$DOMAIN/$LABEL" || die 78 "bootout failed"
      release_admission
      BOOTED=1
      PHASE=BOOTED_OUT
      if [ "$LC_CLASS" = "loaded-running" ]; then
        wait_pid_dead "$OLD_PID"
        wait_rc=$?
        if [ "$wait_rc" -eq 2 ]; then
          stop_uncertain WAIT_PID "process state uncertain"
        fi
        if [ "$wait_rc" -ne 0 ]; then
          stop_uncertain WAIT_PID "old pid did not exit"
        fi
      fi
      if [ "$FAULT" = "post-bootout-print" ]; then
        stop_uncertain POST_BOOTOUT_PRINT "launchctl state uncertain"
      fi
      launchctl_print || stop_uncertain POST_BOOTOUT_PRINT "launchctl state uncertain"
      [ "$LC_CLASS" = "absent" ] || stop_uncertain POST_BOOTOUT_PRINT "service still loaded after bootout"
    fi
    PHASE=PID_GONE
    hold_if_requested "$HOLD_PLIST"
    if ! admit_effect; then
      if [ "$BOOTED" -eq 1 ]; then
        recover_or_stop PLIST_ADMIT "selector moved before plist replace"
      fi
      die 78 "selector moved before plist replace"
    fi
    install_fault=""
    case "$FAULT" in
      install-before-replace) install_fault=before-replace ;;
      install-after-replace) install_fault=after-replace ;;
    esac
    py install-rendered "$RENDERED" "$DEST_PLIST" "$install_fault"
    install_rc=$?
    release_admission
    if [ "$install_rc" -ne 0 ]; then
      if [ "$BOOTED" -eq 1 ]; then
        recover_or_stop INSTALL "plist install failed"
      fi
      restore_plist || die 78 "rollback restore failed"
      die 78 "plist install failed"
    fi
    rm -f -- "$RENDERED"
    RENDERED=""
    PHASE=PLIST_REPLACED
    hold_if_requested "$HOLD_BOOTSTRAP"
    if [ "$FAULT" = "pre-bootstrap-print" ]; then
      stop_uncertain PRE_BOOTSTRAP_PRINT "launchctl state uncertain"
    fi
    if ! launchctl_print; then
      stop_uncertain PRE_BOOTSTRAP_PRINT "launchctl state uncertain"
    fi
    if [ "$LC_CLASS" != "absent" ]; then
      stop_uncertain PRE_BOOTSTRAP_PRINT "service still loaded"
    fi
    if ! admit_effect; then
      if [ "$BOOTED" -eq 1 ]; then
        recover_or_stop BOOTSTRAP_ADMIT "selector moved before bootstrap"
      fi
      restore_plist || die 78 "rollback restore failed"
      die 78 "selector moved before bootstrap"
    fi
    bootstrap_once new
    new_rc=$?
    release_admission
    if [ "$new_rc" -ne 0 ]; then
      if ! launchctl_print || [ "$LC_CLASS" != "absent" ]; then
        stop_uncertain BOOTSTRAP "bootstrap failed"
      fi
      restore_plist || stop_uncertain BOOTSTRAP "rollback restore failed"
      if ! launchctl_print || [ "$LC_CLASS" != "absent" ]; then
        stop_uncertain BOOTSTRAP "bootstrap failed"
      fi
      bootstrap_once rollback
      roll_rc=$?
      if [ "$roll_rc" -ne 0 ]; then
        stop_uncertain BOOTSTRAP "rollback bootstrap failed"
      fi
      if ! launchctl_print; then
        stop_uncertain BOOTSTRAP "recovered bootstrap unproven"
      fi
      case "$LC_CLASS" in
        loaded-running|loaded-idle) ;;
        *) stop_uncertain BOOTSTRAP "recovered bootstrap unproven" ;;
      esac
      write_receipt RECOVERED BOOTSTRAP "bootstrap failed" || die 78 "receipt failed"
      die 78 "recovered original service: bootstrap failed"
    fi
    PHASE=BOOTSTRAPPED
    launchctl_print || die 78 "launchctl state uncertain"
    [ "$LC_CLASS" = "loaded-running" ] || die 78 "launchctl state uncertain"
    ps_state "$LC_PID"
    [ "$PS_RESULT" = "alive" ] || die 78 "process state uncertain"
    argv_matches || die 78 "bootstrap did not pin the verified collector"
    exit 0
    ;;
  *)
    usage
    ;;
esac
