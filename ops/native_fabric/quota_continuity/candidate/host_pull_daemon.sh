#!/bin/bash
# host_pull_daemon.sh — source-controlled candidate for the original Fabric
# host-pull LaunchAgent lifecycle (flat ext/host_pull_daemon.sh).
#
# The native source inventory admits exactly two flat host-pull lifecycle
# files: ext/host_pull_daemon.sh and ext/host_pull_launchd.plist.template.
# native_generation.file_name() allows that one plist relative and no other
# plist. Admission is not selection and is not an install. The live native
# generation and the selector are unchanged. This candidate is NOT INSTALLABLE
# as a selected generation. Do not bootstrap this file from this PR.
#
# install-agent never reads a caller-supplied collector path. The only
# collector it will pin is
#   <native-code-releases>/<verified-64hex>/ext/host_pull.sh
# and only after native_generation.py verify, a CURRENT.json compare under the
# original publication lock immediately before each effect, and owner, mode,
# path, and RELEASE descriptor checks.
#
# --advance-from HEX is the only way to move the selector and the launchd
# service together. It must equal --expect-current and must differ from
# --generation. Before any effect, CURRENT must still be that prior generation
# and the target generation must verify. After the install marker is armed,
# and before bootout, this process writes a durable select fence and then
# calls the original publisher select CLI. That call is not nested under
# .publication.lock. A nonzero exit or a caught signal re-reads CURRENT and
# the service sampled before the call. A proven unchanged selector releases
# the fence. A proven new selector is CAS-rolled back only while that service
# preimage is still proven. Anything else keeps the fence, the install
# marker, and an EFFECT_UNKNOWN receipt. Bootstrap is refused until the old
# pid is dead and the label is absent. A later path that restores the old
# plist and proves the service CAS-selects back to --advance-from. An unknown
# service state leaves the selector where the first CAS put it and records
# EFFECT_UNKNOWN. Rebinding launchd while CURRENT names a different
# generation, without --advance-from, fails before launchctl.
#
# Single-collector exclusion is /usr/bin/lockf -t 0 (contention status 75).
# This lifecycle does not use a pid-file check-then-write. Launchd state is
# loaded, definitively service-not-found, or uncertain. Uncertain fails closed
# (78) and is never treated as an absent label.
#
# .publication.lock is held by the same process that runs bootout, plist
# replacement, and bootstrap, from the moment the command is allowed until
# that command returns. The parent does not run the command itself. If that
# holder dies before the command, the parent writes EFFECT_UNKNOWN and does
# not issue the command. A kill during the launchctl syscall can still let
# that one in-flight call finish after the lock drops; the parent does not
# issue a second bootout or bootstrap. A nonzero bootout is never retried
# and is never followed by bootstrap.
#
# install-agent additionally keeps a nonblocking kernel flock on
# <store>/.install-transaction.lock for the whole transaction: the first
# launchd read, backup, bootout, pid wait, plist replace, bootstrap, and the
# final receipt. The file is mode 0600 and owned by the installing user. The
# flock is owned by one helper this process starts. That helper opens the lock
# itself with O_CLOEXEC. This shell does not keep the descriptor, so launchctl,
# ps, publisher, and other descendants do not inherit it. The helper releases
# the flock when this installer exits, including SIGKILL: it watches this pid
# and treats a Linux zombie as already dead. The death watch is registered
# before readiness is visible. A status of 0 is not readiness. An unrelated
# descendant that outlives the installer does not hold the flock. This is not
# .publication.lock and it is not the collector's /usr/bin/lockf.
#
# The helper also holds a private fence flock for its whole life. This shell
# re-proves that fence immediately before the launchd read, before the marker
# arm, and inside every effect process before the command. A dead helper fails
# this installer closed with INSTALL_HOLDER_LOST and no further launchctl,
# plist, or backup effect. A one-time kill check is not that fence. A kill of
# the helper during an already-started launchctl syscall can still let that
# one call finish; this process does not issue another. A second install-agent
# finds the transaction flock busy and exits before any launchctl, plist, or
# backup write. Once this process is about to mutate, it writes
# .install-transaction.marker. A crash after that leaves the marker; the next
# installer can acquire the flock and then fail-closes without mutating. A
# crash before the marker has not mutated, and the helper releases the flock
# when this process dies.

set -u
set -o pipefail

# Canonicalize caller temp root: macOS TMPDIR commonly ends with a slash.
# The strict no-follow path guard must never see a double path separator.
TMPROOT=${TMPDIR:-/tmp}
while [ "${TMPROOT%/}" != "$TMPROOT" ]; do
  TMPROOT=${TMPROOT%/}
done
[ -n "$TMPROOT" ] || { printf '%s\n' 'HOST_PULL_LIFECYCLE_REFUSED: unsafe TMPDIR' >&2; exit 78; }

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
MARKER_OWNED=0
INSTALL_HOLDER_PID=""
INSTALL_FENCE=""
ADVANCE_FROM=""
SELECTED_ADVANCE=0
SELECT_FENCE=0
SELECT_SETTLED=0
SELECT_ROLLBACK=0
SELECT_CLASS=unknown
SELECT_GENERATION=""
SELECT_PREVIOUS=""
PRE_CLASS=""
PRE_PID=""
PRE_ARGV=""
PRE_IS_TARGET=0
PRE_PLIST_SHA=""

release_install_holder() {
  if [ -z "${INSTALL_HOLDER_PID:-}" ]; then
    return 0
  fi
  # Clean exits drop the helper explicitly. SIGKILL cannot run this; the
  # helper notices the installer pid is dead or zombie and exits itself.
  kill -s TERM "$INSTALL_HOLDER_PID" 2>/dev/null || true
  wait "$INSTALL_HOLDER_PID" 2>/dev/null || true
  INSTALL_HOLDER_PID=""
}

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
  # A clean START/VERIFIED preflight refusal has not mutated. A crash cannot run this path,
  # so an abandoned marker stays for the next installer.
  if { [ "${PHASE:-START}" = "START" ] || [ "${PHASE:-START}" = "VERIFIED" ]; } \
      && [ "${MARKER_OWNED:-0}" -eq 1 ] && [ -n "${STORE:-}" ]; then
    py install-transaction-complete "$STORE" || true
    MARKER_OWNED=0
  fi
  if [ -n "${RENDERED:-}" ]; then
    rm -f -- "$RENDERED"
  fi
  release_install_holder
  printf 'HOST_PULL_LIFECYCLE_REFUSED: %s\n' "$*" >&2
  exit "$code"
}

finish_install_success() {
  prove_install_holder
  if [ "${MARKER_OWNED:-0}" -eq 1 ] && [ -n "${STORE:-}" ]; then
    py install-transaction-complete "$STORE" || die 78 "install transaction marker"
    MARKER_OWNED=0
  fi
  release_install_holder
  exit 0
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
  # A signal during publisher select is not proof the CAS had no effect.
  # SELECTED_ADVANCE is still 0 until the shell has accepted the ack.
  if [ "${SELECT_FENCE:-0}" -eq 1 ]; then
    if [ "${SELECT_ROLLBACK:-0}" -eq 1 ]; then
      if read_selector_generation && [ "$SELECT_GENERATION" = "$ADVANCE_FROM" ] \
          && service_still_snapshot && [ "${PRE_IS_TARGET:-1}" -eq 0 ]; then
        clear_select_fence || true
        SELECT_FENCE=0
        release_owned_marker || true
        die 78 "signal during select rollback"
      fi
      write_receipt EFFECT_UNKNOWN SELECT_UNKNOWN "signal during select rollback" \
        || note_install_blocked SELECT_UNKNOWN "signal during select rollback" \
        || true
      die 78 "EFFECT_UNKNOWN service stopped pending repair: signal during select rollback"
    fi
    settle_failed_select "signal during select"
  fi
  case "$PHASE" in
    START|VERIFIED)
      # No backup and no bootout yet. Release the transaction marker so a
      # later installer is not stuck on a clean signal. SIGKILL cannot get here.
      if [ "${MARKER_OWNED:-0}" -eq 1 ] && [ -n "${STORE:-}" ]; then
        py install-transaction-complete "$STORE" || true
        MARKER_OWNED=0
      fi
      release_install_holder
      exit "$code"
      ;;
    BACKED_UP)
      # Select may already have moved CURRENT. Launchd has not been booted
      # out, so a proven pre-effect signal rolls that CAS back. A failed
      # rollback is not claimed as a restored pair.
      if [ "${SELECTED_ADVANCE:-0}" -eq 1 ]; then
        # The selector CAS was acknowledged, but bootout has not started.
        # Re-prove the saved launchd class/PID/argv/plist and process before
        # reversing CURRENT. Unknown identity must retain the marker/CURRENT.
        if ! service_still_snapshot; then
          stop_uncertain "signal-$PHASE" "original service identity unproven before selector rollback"
        fi
        if ! rollback_advanced_selector; then
          stop_uncertain "signal-$PHASE" "selector rollback failed"
        fi
      fi
      release_install_holder
      exit "$code"
      ;;
    PLIST_REPLACED)
      # The rendered plist was installed but bootstrap has not begun.
      # A peer may have edited/replaced the destination since our install.
      # An unconditional restore/remove would destroy that peer's bytes.
      # Keep the observed plist, CURRENT and marker for reconciliation;
      # issue no additional launchctl or plist write on this signal.
      write_receipt EFFECT_UNKNOWN "signal-$PHASE" "signal during $PHASE" || true
      die 78 "EFFECT_UNKNOWN service stopped pending repair: signal during $PHASE"
      ;;
    *)
      # Bootout, pid wait, or bootstrap already started. Another launchctl
      # call would be a second mutation against an unknown job state.
      write_receipt EFFECT_UNKNOWN "signal-$PHASE" "signal during $PHASE" || true
      release_install_holder
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
import fcntl, hashlib, importlib.util, json, os, re, stat, subprocess, sys, tempfile, time

cmd = sys.argv[1]
SAFE = re.compile(r"/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*\Z")
SERVICE_PATH = re.compile(
    r"/(?:[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*)"
    r"(?::/(?:[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*))*\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
ADMITTED_TEMPLATE_NAME = "host_pull_launchd.plist.template"
ADMITTED_TEMPLATE_SHA256 = "31a7108382df97357e8173b6edd7a5612178a042ecbc165591d89e9152846d9f"

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

def transaction_fence_held(path):
    # True only while the install helper still holds its private fence flock.
    # Acquiring the flock here means that helper is gone; release it at once.
    require_safe(path, "install fence")
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        blob = os.read(fd, 128)
        if not blob.startswith(b"armed\n"):
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)

def perform_install(src, dest, fault):
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

if cmd == "check-pin" or cmd == "check-advance":
    store, generation, expect, publisher, pin = sys.argv[2:7]
    owner_required = int(sys.argv[7])
    advancing = cmd == "check-advance"
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
    wanted = expect if advancing else generation
    if (not isinstance(current, dict) or current.get("schema") != "native-code-selection.v1"
            or current.get("generation") != wanted
            or (not advancing and current.get("generation") != expect)
            or (advancing and generation == expect)
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
    if os.path.basename(template) != ADMITTED_TEMPLATE_NAME:
        fail("template name")
    st_template = lstat_nofollow(template)
    if not stat.S_ISREG(st_template.st_mode):
        fail("template file")
    try:
        template_fd = os.open(template, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        fail("template file")
    try:
        raw_template = os.read(template_fd, st_template.st_size + 1)
        if (len(raw_template) != st_template.st_size
                or os.fstat(template_fd).st_ino != st_template.st_ino):
            fail("template file")
    finally:
        os.close(template_fd)
    if hashlib.sha256(raw_template).hexdigest() != ADMITTED_TEMPLATE_SHA256:
        fail("template digest")
    text = raw_template.decode("utf-8")
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
    perform_install(src, dest, fault)

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

elif cmd == "locked-effect":
    # This process holds .publication.lock while it performs the one effect.
    # Exit 76: bootout returned nonzero and the same pid is still loaded.
    # Exit 77: bootout returned nonzero and the result is not that proof.
    # The parent must not issue another bootout or a bootstrap for either.
    store, generation, expect, publisher, work, pause, kind, fence = sys.argv[2:10]
    effect_args = sys.argv[10:]
    require_safe(store, "store")
    require_safe(publisher, "publisher")
    require_safe(work, "lock work")
    if pause != "-":
        require_safe(pause, "lock hold")
        require_safe(pause + ".holder", "lock holder")
    if HEX.fullmatch(generation) is None or HEX.fullmatch(expect) is None:
        fail("generation identity")
    if os.path.basename(publisher) != "native_generation.py":
        fail("publisher name")
    if os.path.basename(store) != "native-code-releases":
        fail("store name")
    if kind not in {"bootout", "bootstrap", "install"}:
        fail("locked effect")
    if kind == "bootout" and len(effect_args) != 4:
        fail("bootout args")
    if kind == "install" and len(effect_args) != 3:
        fail("install args")
    purpose = ""
    if kind == "bootstrap":
        if len(effect_args) != 4:
            fail("bootstrap args")
        purpose = effect_args[3]
        if purpose not in {"new", "rollback"}:
            fail("bootstrap purpose")
    # Rollback restores the preimage after the selector has already moved.
    # It still holds this lock for the whole command. It does not require
    # CURRENT to name the generation being abandoned.
    enforce_generation = purpose != "rollback"

    def read_selected():
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
            # A token file, not stderr. A killed holder dumps this source
            # into the shell's death message, which also contains the words.
            fd = os.open(work + "/reason", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.write(fd, b"selector-moved\n")
            os.fsync(fd)
            os.close(fd)
            fail("selector moved")

    def verify_publisher():
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

    def mark_started():
        fd = os.open(work + "/started", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)

    def same_pid_still_running(launchctl, ps_bin, target, pid):
        if re.fullmatch(r"[1-9][0-9]*", pid or "") is None:
            return False
        proc = subprocess.run([launchctl, "print", target], check=False, capture_output=True, text=True)
        out, err = proc.stdout, proc.stderr
        if proc.returncode != 0 or err.strip():
            return False
        if re.search(r"not found|Could not find service", out, re.IGNORECASE):
            return False
        v1 = ("HOST_PULL_LAUNCHCTL_V1\n" in out and "\nstate=loaded\n" in "\n" + out
              and "\nactivity=running\n" in "\n" + out and ("\npid=%s\n" % pid) in "\n" + out)
        pid_lines = re.findall(r"(?m)^\s*pid = ([0-9]+)\s*$", out)
        prod = bool(re.search(
            r"(?m)^(?:gui/[0-9]+|user/[0-9]+|system)/com\.mastermind\.host-pull = \{$", out)) and bool(
            re.search(r"(?m)^\s*state = running\s*$", out)) and "state = not running" not in out and pid_lines == [pid]
        if not (v1 or prod):
            return False
        ps = subprocess.run([ps_bin, "-p", pid, "-o", "pid="], check=False, capture_output=True, text=True)
        observed = "".join(ch for ch in ps.stdout if ch.isdigit())
        return ps.returncode == 0 and observed == pid

    # O_CLOEXEC keeps the lock on this process across the effect subprocess.
    # The open mode and flock match native_generation.publication_lock.
    lock_fd = os.open(store + "/.publication.lock",
                      os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        observed = os.fstat(lock_fd)
        if (not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid()
                or stat.S_IMODE(observed.st_mode) != 0o600):
            fail("admission refused: invalid publication lock")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("admission refused: native publication already in progress")
        if enforce_generation:
            read_selected()
            verify_publisher()
        if pause != "-":
            holder = os.open(pause + ".holder", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.write(holder, str(os.getpid()).encode("ascii") + b"\n")
            os.fsync(holder)
            os.close(holder)
            while os.path.exists(pause):
                time.sleep(0.05)
            if enforce_generation:
                read_selected()
        # The transaction helper must still hold its fence. Otherwise the
        # publication lock would fence a command the installer no longer owns.
        if not transaction_fence_held(fence):
            raise SystemExit(79)
        mark_started()
        if kind == "bootout":
            launchctl, ps_bin, target, expected_pid = effect_args
            require_safe(launchctl, "launchctl")
            require_safe(ps_bin, "ps")
            if re.fullmatch(r"gui/[0-9]+/com\.mastermind\.host-pull", target) is None:
                fail("bootout target")
            proc = subprocess.run([launchctl, "bootout", target], check=False)
            if proc.returncode != 0:
                # One classification read. Never a second bootout.
                if same_pid_still_running(launchctl, ps_bin, target, expected_pid):
                    raise SystemExit(76)
                raise SystemExit(77)
        elif kind == "bootstrap":
            launchctl, domain, dest, _purpose = effect_args
            require_safe(launchctl, "launchctl")
            require_safe(dest, "plist")
            if re.fullmatch(r"gui/[0-9]+", domain) is None:
                fail("bootstrap domain")
            proc = subprocess.run([launchctl, "bootstrap", domain, dest], check=False)
            if proc.returncode != 0:
                raise SystemExit(proc.returncode if proc.returncode != 76 else 1)
        else:
            src, dest, fault = effect_args
            if fault == "-":
                fault = ""
            perform_install(src, dest, fault)
        if enforce_generation:
            read_selected()
    finally:
        os.close(lock_fd)

elif cmd == "write-receipt":
    directory, generation, outcome, phase, reason = sys.argv[2:7]
    require_safe(directory, "receipt dir")
    if HEX.fullmatch(generation) is None:
        fail("generation identity")
    if outcome not in {"RECOVERED", "EFFECT_UNKNOWN", "NO_EFFECT"}:
        fail("receipt outcome")
    if re.fullmatch(r"[A-Za-z0-9._+-]{1,80}", phase) is None:
        fail("receipt phase")
    if "\n" in reason or len(reason) > 200:
        fail("receipt reason")
    st_dir = lstat_nofollow(directory)
    if not stat.S_ISDIR(st_dir.st_mode) or stat.S_IMODE(st_dir.st_mode) != 0o700:
        fail("receipt dir mode")
    if outcome == "RECOVERED":
        service = "restored"
    elif outcome == "NO_EFFECT":
        service = "still-loaded"
    else:
        service = "stopped-uncertain"
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

elif cmd == "install-transaction-prepare":
    path = sys.argv[2]
    require_safe(path, "install transaction")
    if os.path.lexists(path):
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            fail("install transaction lock kind")
        if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600:
            fail("install transaction lock owner")
    else:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

elif cmd == "install-transaction-arm":
    store, generation, pid, fence = sys.argv[2:6]
    require_safe(store, "store")
    if HEX.fullmatch(generation) is None:
        fail("generation identity")
    if re.fullmatch(r"[1-9][0-9]*", pid) is None:
        fail("install transaction pid")
    if not transaction_fence_held(fence):
        fail("install transaction holder lost")
    marker = store + "/.install-transaction.marker"
    require_safe(marker, "install transaction marker")
    if os.path.lexists(marker):
        fail("install transaction marker exists")
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (pid + " " + generation + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)

elif cmd == "install-transaction-prove":
    if not transaction_fence_held(sys.argv[2]):
        raise SystemExit(79)

elif cmd == "install-transaction-complete":
    store = sys.argv[2]
    require_safe(store, "store")
    marker = store + "/.install-transaction.marker"
    require_safe(marker, "install transaction marker")
    if not os.path.lexists(marker):
        raise SystemExit(0)
    st_marker = os.lstat(marker)
    if stat.S_ISLNK(st_marker.st_mode) or not stat.S_ISREG(st_marker.st_mode):
        fail("install transaction marker kind")
    os.unlink(marker)

elif cmd == "ensure-receipt-dir":
    directory = sys.argv[2]
    require_safe(directory, "receipt dir")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    st_dir = lstat_nofollow(directory)
    if stat.S_ISDIR(st_dir.st_mode) and stat.S_IMODE(st_dir.st_mode) != 0o700:
        os.chmod(directory, 0o700)
        st_dir = lstat_nofollow(directory)
    if (not stat.S_ISDIR(st_dir.st_mode) or stat.S_IMODE(st_dir.st_mode) != 0o700
            or st_dir.st_uid != os.geteuid()):
        fail("receipt dir")

elif cmd == "file-sha":
    path = sys.argv[2]
    require_safe(path, "plist")
    observed = lstat_nofollow(path)
    if (not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid()):
        fail("plist owner")
    sys.stdout.write(hashlib.sha256(open(path, "rb").read()).hexdigest() + "\n")

elif cmd == "write-select-fence":
    store, prior, generation = sys.argv[2:5]
    require_safe(store, "store")
    if (HEX.fullmatch(prior) is None or HEX.fullmatch(generation) is None
            or prior == generation or os.path.basename(store) != "native-code-releases"):
        fail("select fence")
    path = store + "/.select-pending"
    require_safe(path, "select fence")
    if os.path.lexists(path):
        fail("select fence exists")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (prior + " " + generation + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(store, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

elif cmd == "clear-select-fence":
    store, prior, generation = sys.argv[2:5]
    require_safe(store, "store")
    if HEX.fullmatch(prior) is None or HEX.fullmatch(generation) is None:
        fail("select fence")
    path = store + "/.select-pending"
    require_safe(path, "select fence")
    observed = lstat_nofollow(path)
    if (not stat.S_ISREG(observed.st_mode) or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_uid != os.geteuid()):
        fail("select fence owner")
    raw = open(path, "rb").read()
    if raw != (prior + " " + generation + "\n").encode("ascii"):
        fail("select fence body")
    os.unlink(path)
    directory = os.open(store, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

elif cmd == "read-current":
    store, publisher = sys.argv[2:4]
    require_safe(store, "store")
    require_safe(publisher, "publisher")
    if os.path.basename(publisher) != "native_generation.py":
        fail("publisher name")
    if os.path.basename(store) != "native-code-releases":
        fail("store name")
    spec = importlib.util.spec_from_file_location("host_pull_select_publisher", publisher)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        selected = module.current(store)
    except (OSError, ValueError):
        fail("current unreadable")
    if selected is None:
        fail("current absent")
    previous = selected["previous"] if selected["previous"] is not None else "-"
    sys.stdout.write(selected["generation"] + "\n" + str(previous) + "\n")

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
  # Every launchd read is inside the helper's lifetime, including preflight.
  prove_install_holder
  out=$(mktemp "$TMPROOT/host-pull-lc-out.XXXXXX")
  err=$(mktemp "$TMPROOT/host-pull-lc-err.XXXXXX")
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
  out=$(mktemp "$TMPROOT/host-pull-ps.XXXXXX")
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
    prove_install_holder
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
  # Fresh installs have no old plist to back up, yet uncertain effects
  # must still leave a durable receipt in the publisher's receipt store.
  py ensure-receipt-dir "$BACKUP_DIR" || return 1
  py write-receipt "$BACKUP_DIR" "$GENERATION" "$outcome" "$phase" "$*"
}

note_install_blocked() {
  local phase=$1
  shift
  [ -n "${BACKUP_DIR:-}" ] || return 1
  py ensure-receipt-dir "$BACKUP_DIR" || return 1
  py write-receipt "$BACKUP_DIR" "$GENERATION" "EFFECT_UNKNOWN" "$phase" "$*"
}

# The private fence flock is the lifetime proof. Process-liveness alone is not.
lose_install_holder() {
  # Proven pre-effect only: prove_install_holder refuses before effect launch,
  # and rc79 is a holder loss only if the per-effect started file is absent.
  # Never restore on an effect that may have begun.
  case "$PHASE" in
    PLIST_REPLACED) restore_plist || true ;;
    BOOTSTRAP_STARTED)
      # Restore only on a proven current-effect pre-start refusal. A holder
      # lost after bootstrap may have begun must leave plist bytes untouched.
      if effect_was_not_started \
          && [ -n "${LOCKED_DIR:-}" ] \
          && [ ! -e "$LOCKED_DIR/started" ] \
          && [ ! -L "$LOCKED_DIR/started" ]; then
        restore_plist || true
      fi
      ;;
  esac
  note_install_blocked INSTALL_HOLDER_LOST "install transaction holder lost" || true
  die 78 "install transaction holder lost"
}

prove_install_holder() {
  if [ -z "${INSTALL_FENCE:-}" ] || [ -z "${INSTALL_HOLDER_PID:-}" ]; then
    lose_install_holder
  fi
  py install-transaction-prove "$INSTALL_FENCE" || lose_install_holder
}

# The helper, not this shell, owns the transaction flock. It is a direct child
# and exits when this installer exits, so descendants cannot keep the flock.
# Readiness is the word "armed", written only after the death watch is registered
# and the private fence flock is held. A bare 0 is a failed watch and is refused.
acquire_install_transaction() {
  local lockpath status line waited fence
  lockpath="$STORE/.install-transaction.lock"
  py install-transaction-prepare "$lockpath" || die 78 "install transaction lock refused"
  status=$(mktemp "$TMPROOT/host-pull-tx.XXXXXX")
  if [ -n "${HOLDER_REPORT:-}" ]; then
    [ "$HERMETIC" -eq 1 ] || die 78 "holder report is hermetic-only"
    fence=$HOLDER_REPORT
  else
    fence=$(mktemp "$TMPROOT/host-pull-fence.XXXXXX")
  fi
  INSTALL_FENCE=$fence
  "$PYTHON" - "$STORE" "$GENERATION" "$status" "$$" "$fence" "${FAULT:-}" >"$status.out" 2>"$status.err" <<'PY' &
import fcntl, os, re, stat, sys, time
store, generation, status, installer, fence, fault = sys.argv[1:7]
HEX = re.compile(r"[0-9a-f]{64}\Z")
SAFE = re.compile(r"/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*\Z")

def report(code):
    fd = os.open(status, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (str(code) + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)

def linux_installer_dead(pid):
    proc = "/proc/%d/stat" % pid
    try:
        raw = open(proc, "r", encoding="ascii", errors="replace").read()
    except OSError:
        return True
    try:
        state = raw.rsplit(")", 1)[1].split()[0]
    except (IndexError, ValueError):
        return True
    # Z means the process has exited and its descriptors are already closed.
    return state == "Z"

def register_watch(pid):
    # Registration finishes before any readiness token is written.
    if sys.platform == "darwin":
        import select
        kq = select.kqueue()
        watch = select.kevent(
            pid,
            filter=select.KQ_FILTER_PROC,
            flags=select.KQ_EV_ADD,
            fflags=select.KQ_NOTE_EXIT,
        )
        kq.control([watch], 0)
        return ("darwin", kq, watch)
    proc = "/proc/%d/stat" % pid
    raw = open(proc, "r", encoding="ascii", errors="replace").read()
    state = raw.rsplit(")", 1)[1].split()[0]
    if state == "Z":
        raise RuntimeError("installer already dead")
    return ("linux", None, None)

def watch_installer(kind, kq, watch, pid):
    if kind == "darwin":
        while True:
            events = kq.control(None, 1, 0.2)
            if events:
                return
            try:
                os.kill(pid, 0)
            except OSError:
                return
        return
    while not linux_installer_dead(pid):
        time.sleep(0.05)

def hold_fence(path):
    if SAFE.fullmatch(path) is None:
        raise RuntimeError("unsafe install fence")
    st_path = os.lstat(path)
    if stat.S_ISLNK(st_path.st_mode) or not stat.S_ISREG(st_path.st_mode):
        raise RuntimeError("install fence kind")
    fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    st_fd = os.fstat(fd)
    if (st_fd.st_ino != st_path.st_ino or st_fd.st_dev != st_path.st_dev
            or st_fd.st_uid != os.geteuid() or stat.S_IMODE(st_fd.st_mode) != 0o600):
        raise RuntimeError("install fence owner")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, ("armed\npid=%d\n" % os.getpid()).encode("ascii"))
    os.fsync(fd)
    return fd

try:
    if SAFE.fullmatch(store) is None or SAFE.fullmatch(status) is None:
        raise RuntimeError("unsafe install transaction path")
    if SAFE.fullmatch(fence) is None:
        raise RuntimeError("unsafe install fence")
    if HEX.fullmatch(generation) is None or re.fullmatch(r"[1-9][0-9]*", installer) is None:
        raise RuntimeError("install transaction identity")
    lockpath = store + "/.install-transaction.lock"
    marker = store + "/.install-transaction.marker"
    st_path = os.lstat(lockpath)
    if stat.S_ISLNK(st_path.st_mode) or not stat.S_ISREG(st_path.st_mode):
        raise RuntimeError("install transaction lock kind")
    # Opened only in this helper. O_CLOEXEC keeps it out of any exec this
    # helper might perform. The installer shell never has this descriptor.
    lock_fd = os.open(lockpath, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
    st_fd = os.fstat(lock_fd)
    if (st_fd.st_ino != st_path.st_ino or st_fd.st_dev != st_path.st_dev
            or st_fd.st_uid != os.geteuid() or stat.S_IMODE(st_fd.st_mode) != 0o600):
        raise RuntimeError("install transaction lock owner")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        report(75)
        raise SystemExit(75)
    if os.path.lexists(marker):
        st_marker = os.lstat(marker)
        if stat.S_ISLNK(st_marker.st_mode) or not stat.S_ISREG(st_marker.st_mode):
            raise RuntimeError("install transaction marker kind")
        kind, kq, watch = register_watch(int(installer))
        report(77)
        watch_installer(kind, kq, watch, int(installer))
        raise SystemExit(77)
    # Hermetic stand-in for a watcher that announces readiness and then fails
    # to register. The parent must not treat 0 as armed.
    if fault == "watch-after-ready":
        report(0)
        raise SystemExit(78)
    kind, kq, watch = register_watch(int(installer))
    hold_fence(fence)
    report("armed")
    watch_installer(kind, kq, watch, int(installer))
    raise SystemExit(0)
except SystemExit:
    raise
except Exception:
    try:
        report(78)
    except Exception:
        pass
    raise
PY
  INSTALL_HOLDER_PID=$!
  line=""
  waited=0
  while [ "$waited" -lt 100 ]; do
    line=$(tr -cd 'A-Za-z0-9' <"$status" 2>/dev/null || true)
    if [ "$line" = "armed" ] || [ "$line" = "75" ] || [ "$line" = "77" ] || [ "$line" = "78" ]; then
      break
    fi
    if ! kill -s 0 "$INSTALL_HOLDER_PID" 2>/dev/null; then
      line=$(tr -cd 'A-Za-z0-9' <"$status" 2>/dev/null || true)
      break
    fi
    waited=$((waited + 1))
    sleep 0.05
  done
  if [ "$line" = "armed" ]; then
    prove_install_holder
    if [ -n "${LOCK_DESCENDANT:-}" ]; then
      [ "$HERMETIC" -eq 1 ] || die 78 "lock descendant is hermetic-only"
      # This child is the inheritance probe. It must stay alive after the
      # installer dies and must not hold the transaction descriptor.
      # Stdio is detached so the probe cannot keep the installer's pipes open.
      "$PYTHON" - "$lockpath" "$LOCK_DESCENDANT" >/dev/null 2>&1 <<'PY' &
import os, stat, sys, time
lockpath, report = sys.argv[1:3]
target = os.lstat(lockpath)
inherited = 0
for fd in range(0, 256):
    try:
        st = os.fstat(fd)
    except OSError:
        continue
    if st.st_ino == target.st_ino and st.st_dev == target.st_dev:
        inherited = 1
fd9_open = 0
try:
    os.fstat(9)
    fd9_open = 1
except OSError:
    fd9_open = 0
fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
try:
    os.write(fd, ("inherited=%d\nfd9_open=%d\npid=%d\n" % (inherited, fd9_open, os.getpid())).encode("ascii"))
    os.fsync(fd)
finally:
    os.close(fd)
while True:
    time.sleep(0.2)
PY
    fi
    return 0
  fi
  if [ "$line" = "75" ]; then
    release_install_holder
    note_install_blocked INSTALL_CONTENTION "install transaction already in progress" || true
    die 78 "install transaction already in progress"
  fi
  if [ "$line" = "77" ]; then
    note_install_blocked INSTALL_ABANDONED "install transaction incomplete" || true
    die 78 "install transaction incomplete"
  fi
  if [ "$line" = "0" ]; then
    note_install_blocked INSTALL_WATCH_REFUSED "install transaction watch refused" || true
    die 78 "install transaction watch refused"
  fi
  die 78 "install transaction lock refused"
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
    # Before an admitted bootstrap starts, there was no pre-existing service
    # to recover. Restore the displaced plist and record a durable hold;
    # never bootstrap the old service or reverse a peer's moved selector.
    if [ "$PHASE" = "BOOTSTRAP_STARTED" ] && effect_was_not_started; then
      restore_plist || true
      write_receipt EFFECT_UNKNOWN "$phase" "$reason" || true
      die 78 "EFFECT_UNKNOWN service stopped pending repair: $reason"
    fi
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
  # A loaded label is NOT proof of the original collector. Require the saved
  # preimage arguments, exact restored plist digest, and a live recovered PID
  # before any selector rollback or RECOVERED receipt.
  if ! recovered_original_service; then
    write_receipt EFFECT_UNKNOWN "$phase" "restored collector identity unproven: $reason" || true
    die 78 "EFFECT_UNKNOWN recovered collector identity unproven: $reason"
  fi
  # The service preimage is proven. Only then is the selector CAS reversed.
  if ! rollback_advanced_selector; then
    write_receipt EFFECT_UNKNOWN "$phase" "selector rollback failed" || true
    die 78 "EFFECT_UNKNOWN service stopped pending repair: selector rollback failed"
  fi
  write_receipt RECOVERED "$phase" "$reason" || die 78 "receipt failed"
  die 78 "recovered original service: $reason"
}

run_locked() {
  local kind=$1
  shift
  local pause rc
  # Leave the pre-bootstrap phase in place until holder admission succeeds.
  # A refusal here is provably pre-effect and may restore the original plist.
  prove_install_holder
  if [ "$kind" = "bootstrap" ] && [ "${PHASE:-START}" = "PLIST_REPLACED" ]; then
    PHASE=BOOTSTRAP_STARTED
  fi
  LOCKED_DIR=$(mktemp -d "$TMPROOT/host-pull-lock.XXXXXX") || return 78
  LOCKED_DETAIL=""
  STOP_LOCKED=0
  pause="${HOLD_DURING_LOCK:-"-"}"
  [ -n "$pause" ] || pause="-"
  py locked-effect "$STORE" "$GENERATION" "$EXPECT_CURRENT" "$PUBLISHER" \
    "$LOCKED_DIR" "$pause" "$kind" "$INSTALL_FENCE" "$@" 2>"$LOCKED_DIR/err"
  rc=$?
  # An effect command may itself exit 79 AFTER mark_started. Only a
  # missing started marker proves the pre-effect transaction-fence refusal.
  if [ "$rc" -eq 79 ] && [ ! -f "$LOCKED_DIR/started" ]; then
    # The locked child refused before mark_started: expose positive pre-effect
    # evidence before the holder-loss handler decides whether to restore.
    STOP_LOCKED=1
    lose_install_holder
  fi
  LOCKED_DETAIL=$(cat "$LOCKED_DIR/err" 2>/dev/null || true)
  if [ -n "$LOCKED_DETAIL" ]; then
    printf '%s\n' "$LOCKED_DETAIL" >&2
  fi
  if [ "$rc" -ne 0 ] && [ ! -f "$LOCKED_DIR/started" ]; then
    STOP_LOCKED=1
  fi
  return "$rc"
}

effect_was_not_started() {
  [ "${STOP_LOCKED:-0}" -eq 1 ]
}

selector_moved_before_effect() {
  [ "${STOP_LOCKED:-0}" -eq 1 ] && [ -f "${LOCKED_DIR:-}/reason" ] \
    && grep -qx 'selector-moved' "$LOCKED_DIR/reason"
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
    # run_locked sets BOOTSTRAP_STARTED only after proving the install holder.
  else
    [ "$BOOTSTRAP_ROLLBACK" -eq 0 ] || die 78 "second rollback bootstrap refused"
    BOOTSTRAP_ROLLBACK=1
    PHASE=ROLLING_BACK
  fi
  # One bootstrap inside the lock holder. A holder death before the command
  # sets STOP_LOCKED so the caller does not issue another one.
  HOLD_DURING_LOCK="" run_locked bootstrap "$LAUNCHCTL" "$DOMAIN" "$DEST_PLIST" "$kind"
  return $?
}

confirm_selection_json() {
  "$PYTHON" -c 'import json,sys
body=json.loads(sys.argv[1])
if (body.get("schema")!="native-code-selection.v1"
        or body.get("generation")!=sys.argv[2]
        or body.get("previous")!=sys.argv[3]
        or type(body.get("sequence")) is not int
        or body["sequence"]<1
        or set(body)!={"schema","generation","sequence","previous"}):
    raise SystemExit(78)' "$1" "$2" "$3"
}

snapshot_service() {
  PRE_CLASS=$LC_CLASS
  PRE_PID=${LC_PID:-}
  PRE_ARGV=$LC_ARGV
  if argv_matches; then
    PRE_IS_TARGET=1
  else
    PRE_IS_TARGET=0
  fi
  if [ -e "$DEST_PLIST" ]; then
    PRE_PLIST_SHA=$(py file-sha "$DEST_PLIST") || PRE_PLIST_SHA=unreadable
  else
    PRE_PLIST_SHA=absent
  fi
}

# A rollback is RECOVERED only if the *original* collector is again running.
# Launchd loaded status alone can describe a different generation or stale job.
# Snapshot is taken before the first mutation; the restored PID may be new.
recovered_original_service() {
  local actual_sha
  case "${PRE_CLASS:-}" in loaded-running|loaded-idle) ;; *) return 1 ;; esac
  [ -n "${PRE_ARGV:-}" ] || return 1
  [ -n "${PRE_PLIST_SHA:-}" ] || return 1
  [ "$PRE_PLIST_SHA" != "unreadable" ] && [ "$PRE_PLIST_SHA" != "absent" ] || return 1
  [ "${LC_CLASS:-}" = "loaded-running" ] || return 1
  [ "${LC_ARGV:-}" = "$PRE_ARGV" ] || return 1
  actual_sha=$(py file-sha "$DEST_PLIST") || return 1
  [ "$actual_sha" = "$PRE_PLIST_SHA" ] || return 1
  [ -n "${LC_PID:-}" ] || return 1
  ps_state "$LC_PID"
  [ "$PS_RESULT" = "alive" ] || return 1
  return 0
}

service_still_snapshot() {
  local now
  launchctl_print || return 1
  [ "$LC_CLASS" = "$PRE_CLASS" ] || return 1
  [ "${LC_PID:-}" = "$PRE_PID" ] || return 1
  [ "$LC_ARGV" = "$PRE_ARGV" ] || return 1
  if [ "$PRE_PLIST_SHA" = "absent" ]; then
    [ ! -e "$DEST_PLIST" ] || return 1
  elif [ "$PRE_PLIST_SHA" = "unreadable" ]; then
    return 1
  else
    now=$(py file-sha "$DEST_PLIST") || return 1
    [ "$now" = "$PRE_PLIST_SHA" ] || return 1
  fi
  if [ "$PRE_CLASS" = "loaded-running" ]; then
    ps_state "$PRE_PID"
    [ "$PS_RESULT" = "alive" ] || return 1
  fi
  return 0
}

read_selector_generation() {
  local body
  body=$(py read-current "$STORE" "$PUBLISHER" 2>/dev/null) || return 1
  SELECT_GENERATION=$(printf '%s\n' "$body" | sed -n '1p')
  SELECT_PREVIOUS=$(printf '%s\n' "$body" | sed -n '2p')
  [ -n "$SELECT_GENERATION" ]
}

classify_select_result() {
  SELECT_CLASS=unknown
  service_still_snapshot || return 0
  read_selector_generation || return 0
  if [ "$SELECT_GENERATION" = "$ADVANCE_FROM" ]; then
    SELECT_CLASS=unchanged
  elif [ "$SELECT_GENERATION" = "$GENERATION" ] && [ "$SELECT_PREVIOUS" = "$ADVANCE_FROM" ]; then
    SELECT_CLASS=new
  fi
}

arm_select_fence() {
  py write-select-fence "$STORE" "$ADVANCE_FROM" "$GENERATION" || die 78 "select fence"
  SELECT_FENCE=1
}

clear_select_fence() {
  py clear-select-fence "$STORE" "$ADVANCE_FROM" "$GENERATION"
}

release_owned_marker() {
  if [ "${MARKER_OWNED:-0}" -eq 1 ] && [ -n "${STORE:-}" ]; then
    py install-transaction-complete "$STORE" || return 1
    MARKER_OWNED=0
  fi
  return 0
}

keep_select_unknown() {
  local why=$1
  write_receipt EFFECT_UNKNOWN SELECT_UNKNOWN "$why" \
    || note_install_blocked SELECT_UNKNOWN "$why" \
    || true
  die 78 "EFFECT_UNKNOWN service stopped pending repair: $why"
}

# One CAS back to the fenced prior generation. The exit status is not the
# effect. Fresh CURRENT plus the sampled service decides.
rollback_unacked_select() {
  local out verr rc
  SELECT_ROLLBACK=1
  verr=$(mktemp "$TMPROOT/host-pull-select-back.XXXXXX")
  out=$(HOST_PULL_INSTALLER_PID=$$ "$PYTHON" "$PUBLISHER" select --store "$STORE" --generation "$ADVANCE_FROM" --expect "$GENERATION" 2>"$verr") && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$(cat "$verr" 2>/dev/null || true)" >&2
  fi
  rm -f -- "$verr"
  read_selector_generation || return 1
  [ "$SELECT_GENERATION" = "$ADVANCE_FROM" ] || return 1
  service_still_snapshot || return 1
  [ "$PRE_IS_TARGET" -eq 0 ] || return 1
  EXPECT_CURRENT=$ADVANCE_FROM
  SELECTED_ADVANCE=0
  SELECT_ROLLBACK=0
  return 0
}

settle_failed_select() {
  local why=$1
  [ "${SELECT_SETTLED:-0}" -eq 0 ] || keep_select_unknown "$why"
  SELECT_SETTLED=1
  classify_select_result
  case "$SELECT_CLASS" in
    unchanged)
      clear_select_fence || keep_select_unknown "select fence"
      SELECT_FENCE=0
      release_owned_marker || keep_select_unknown "install transaction marker"
      die 78 "$why"
      ;;
    new)
      if [ "$PRE_IS_TARGET" -eq 0 ] && rollback_unacked_select; then
        clear_select_fence || keep_select_unknown "select fence"
        SELECT_FENCE=0
        release_owned_marker || keep_select_unknown "install transaction marker"
        die 78 "$why"
      fi
      keep_select_unknown "$why"
      ;;
    *)
      keep_select_unknown "$why"
      ;;
  esac
}

# Publisher select is a separate process and is not nested under
# .publication.lock. The fence is durable before that process starts. A
# refused or interrupted CAS is reconciled from CURRENT and the service
# sampled above; the publisher's exit status alone never clears the marker.
advance_selector() {
  local out verr rc
  [ -n "$ADVANCE_FROM" ] || return 0
  [ "$SELECTED_ADVANCE" -eq 0 ] || die 78 "selector already advanced"
  [ "$SELECT_FENCE" -eq 0 ] || die 78 "select fence already armed"
  prove_install_holder
  # The already-running target service can pair CURRENT without reaching the
  # normal backup/marker-arm path. A successful CAS followed by an ambiguous
  # select-fence unlink/fsync still needs a durable transaction marker.
  # Arm it here if this is the idempotent fast path; the ordinary path owns one.
  if [ "${MARKER_OWNED:-0}" -eq 0 ]; then
    py install-transaction-arm "$STORE" "$GENERATION" "$$" "$INSTALL_FENCE" \
      || lose_install_holder
    MARKER_OWNED=1
    # The service was already the TARGET: if a signal follows the selector
    # CAS, rolling CURRENT back as BACKED_UP would mispair launchd again.
    # PAIRING takes the signal handler's EFFECT_UNKNOWN/no-mutation path.
    PHASE=PAIRING
  fi
  snapshot_service
  arm_select_fence
  verr=$(mktemp "$TMPROOT/host-pull-select.XXXXXX")
  out=$(HOST_PULL_INSTALLER_PID=$$ "$PYTHON" "$PUBLISHER" select --store "$STORE" --generation "$GENERATION" --expect "$ADVANCE_FROM" 2>"$verr") && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$(cat "$verr" 2>/dev/null || true)" >&2
    rm -f -- "$verr"
    settle_failed_select "selector advance refused"
  fi
  rm -f -- "$verr"
  if ! confirm_selection_json "$out" "$GENERATION" "$ADVANCE_FROM"; then
    settle_failed_select "selector advance output"
  fi
  read_selector_generation || settle_failed_select "selector advance output"
  if [ "$SELECT_GENERATION" != "$GENERATION" ] || [ "$SELECT_PREVIOUS" != "$ADVANCE_FROM" ]; then
    settle_failed_select "selector advance output"
  fi
  # CURRENT may already name the target; a failed fence unlink/fsync cannot
  # be treated as a clean refusal. Preserve both transaction and selector
  # uncertainty without replaying CAS or touching launchd.
  clear_select_fence || keep_select_unknown "select fence cleanup after committed advance"
  SELECT_FENCE=0
  EXPECT_CURRENT=$GENERATION
  SELECTED_ADVANCE=1
}

# CAS back to the generation we advanced from. The caller may invoke this
# only after the old service state is proven. A publisher error is re-read:
# CURRENT at the prior generation is a committed rollback. Failure leaves
# SELECTED_ADVANCE set so the receipt stays EFFECT_UNKNOWN instead of RECOVERED.
rollback_advanced_selector() {
  local out verr rc
  [ "$SELECTED_ADVANCE" -eq 1 ] || return 0
  prove_install_holder
  verr=$(mktemp "$TMPROOT/host-pull-select-back.XXXXXX")
  out=$(HOST_PULL_INSTALLER_PID=$$ "$PYTHON" "$PUBLISHER" select --store "$STORE" --generation "$ADVANCE_FROM" --expect "$GENERATION" 2>"$verr") && rc=0 || rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '%s\n' "$(cat "$verr" 2>/dev/null || true)" >&2
  fi
  rm -f -- "$verr"
  if [ "$rc" -eq 0 ]; then
    confirm_selection_json "$out" "$ADVANCE_FROM" "$GENERATION" || true
  fi
  read_selector_generation || return 1
  [ "$SELECT_GENERATION" = "$ADVANCE_FROM" ] || return 1
  EXPECT_CURRENT=$ADVANCE_FROM
  SELECTED_ADVANCE=0
}

require_advance_pin() {
  local owner
  local verr verify_out
  [ -n "$ADVANCE_FROM" ] || die 78 "advance-from required"
  [ "$ADVANCE_FROM" = "$EXPECT_CURRENT" ] || die 78 "advance-from must be the expected current generation"
  [ "$ADVANCE_FROM" != "$GENERATION" ] || die 78 "advance target is already current"
  owner=$(id -u)
  if [ "$HERMETIC" -eq 1 ] && [ -n "${EXPECT_OWNER_UID:-}" ]; then
    owner=$EXPECT_OWNER_UID
  fi
  case $owner in
    ''|*[!0-9]*) die 78 "owner uid" ;;
  esac
  PIN="$STORE/$GENERATION/ext/host_pull.sh"
  py check-advance "$STORE" "$GENERATION" "$ADVANCE_FROM" "$PUBLISHER" "$PIN" "$owner" >/dev/null \
    || die 78 "pin checks failed"
  verr=$(mktemp "$TMPROOT/host-pull-verify.XXXXXX")
  verify_out=$("$PYTHON" "$PUBLISHER" verify --store "$STORE" --generation "$GENERATION" 2>"$verr") \
    || { rm -f -- "$verr"; die 78 "publisher verify failed"; }
  rm -f -- "$verr"
  "$PYTHON" -c 'import json,sys
body=json.loads(sys.argv[1])
if body.get("digest")!=sys.argv[2] or not str(body.get("path","")):
    raise SystemExit(78)' "$verify_out" "$GENERATION" \
    || die 78 "publisher verify output"
  py check-advance "$STORE" "$GENERATION" "$ADVANCE_FROM" "$PUBLISHER" "$PIN" "$owner" >/dev/null \
    || die 78 "pin checks failed after verify"
  PHASE=VERIFIED
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
  verr=$(mktemp "$TMPROOT/host-pull-verify.XXXXXX")
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
HOLD_INSTALL_FAILURE=""
HOLD_DURING_LOCK=""
HOLD_ARM=""
LOCK_DESCENDANT=""
HOLDER_REPORT=""
EXPECT_OWNER_UID=""
ADVANCE_FROM=""
SELECTED_ADVANCE=0
SELECT_FENCE=0
SELECT_SETTLED=0
SELECT_ROLLBACK=0
SELECT_CLASS=unknown
SELECT_GENERATION=""
SELECT_PREVIOUS=""
PRE_CLASS=""
PRE_PID=""
PRE_ARGV=""
PRE_IS_TARGET=0
PRE_PLIST_SHA=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --store) STORE=${2:-}; shift 2 ;;
    --generation) GENERATION=${2:-}; shift 2 ;;
    --expect-current) EXPECT_CURRENT=${2:-}; shift 2 ;;
    --advance-from) ADVANCE_FROM=${2:-}; shift 2 ;;
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
    --hold-after-install-failure) HOLD_INSTALL_FAILURE=${2:-}; shift 2 ;;
    --hold-before-bootstrap) HOLD_BOOTSTRAP=${2:-}; shift 2 ;;
    --hold-during-lock) HOLD_DURING_LOCK=${2:-}; shift 2 ;;
    --hold-before-arm) HOLD_ARM=${2:-}; shift 2 ;;
    --lock-descendant) LOCK_DESCENDANT=${2:-}; shift 2 ;;
    --holder-report) HOLDER_REPORT=${2:-}; shift 2 ;;
    --expect-owner-uid) EXPECT_OWNER_UID=${2:-}; shift 2 ;;
    --fault) FAULT=${2:-}; shift 2 ;;
    --wait-limit) WAIT_LIMIT=${2:-}; shift 2 ;;
    --hermetic) HERMETIC=1; shift ;;
    --program|--pidfile) die 78 "program and pidfile inputs are refused" ;;
    *) usage ;;
  esac
done

[ -n "$STORE" ] && [ -n "$GENERATION" ] && [ -n "$EXPECT_CURRENT" ] && [ -n "$PUBLISHER" ] || usage
if [ -n "$ADVANCE_FROM" ]; then
  case "$ADVANCE_FROM" in
    *[!0-9a-f]*) die 78 "advance-from identity" ;;
  esac
  [ "${#ADVANCE_FROM}" -eq 64 ] || die 78 "advance-from identity"
  [ "$ADVANCE_FROM" = "$EXPECT_CURRENT" ] || die 78 "advance-from must be the expected current generation"
  [ "$ADVANCE_FROM" != "$GENERATION" ] || die 78 "advance target is already current"
fi
PYTHON=$(command -v python3) || die 78 "python3 required"
case $WAIT_LIMIT in
  ''|*[!0-9]*) die 78 "wait limit" ;;
esac
if [ "$HERMETIC" -eq 1 ]; then
  [ -n "$FIXTURE_ROOT" ] || die 78 "hermetic fixture root required"
  [ "$WAIT_LIMIT" -le 200 ] || die 78 "wait limit"
  case "$FAULT" in
    ""|wait-pid|post-bootout-print|install-before-replace|install-after-replace|pre-bootstrap-print|watch-after-ready) ;;
    *) die 78 "unknown fault" ;;
  esac
else
  [ -z "$FIXTURE_ROOT" ] || die 78 "fixture root is hermetic-only"
  [ -z "$HOLD_MUTATION" ] && [ -z "$HOLD_BOOTSTRAP" ] && [ -z "$HOLD_BOOTOUT" ] \
    && [ -z "$HOLD_PLIST" ] && [ -z "$HOLD_INSTALL_FAILURE" ] \
    && [ -z "$HOLD_DURING_LOCK" ] && [ -z "$HOLD_ARM" ] \
    && [ -z "$LOCK_DESCENDANT" ] && [ -z "$HOLDER_REPORT" ] \
    && [ -z "$EXPECT_OWNER_UID" ] && [ -z "$FAULT" ] && [ -z "$TEMPLATE" ] \
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
    [ -z "$ADVANCE_FROM" ] || die 78 "advance-from is install-agent only"
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
    if [ -z "$BACKUP_DIR" ]; then
      BACKUP_DIR=$(dirname -- "$(dirname -- "$DEST_PLIST")")/com.mastermind.host-pull-plist-backups
    fi
    # Before the first launchd read. Contention writes a receipt and returns
    # without launchctl, plist, or backup mutations.
    acquire_install_transaction
    resolve_tool launchctl /bin/launchctl
    LAUNCHCTL=$TOOL_PATH
    resolve_tool ps /bin/ps
    PS=$TOOL_PATH
    ADMITTED_TEMPLATE=$HERE/host_pull_launchd.plist.template
    if [ -n "$TEMPLATE" ] && [ "$TEMPLATE" != "$ADMITTED_TEMPLATE" ]; then
      die 78 "template path"
    fi
    TEMPLATE=$ADMITTED_TEMPLATE
    if [ -n "$ADVANCE_FROM" ]; then
      require_advance_pin
    else
      require_verified_pin
    fi
    py paths-ready "$LOCK" "$LOG_PATH" || die 78 "lock or log path"
    RENDERED=$(py render "$TEMPLATE" "$DEST_PLIST" "$PIN" "$LOG_PATH" "$LOCK" "$SERVICE_PATH") \
      || die 78 "render failed"
    launchctl_print || die 78 "launchctl state uncertain"
    # Capture the old identity before a marker, selector CAS or launchd effect.
    # advance_selector may refresh this while the old service is still intact.
    snapshot_service
    NEED_BOOTOUT=0
    case "$LC_CLASS" in
      loaded-running)
        ps_state "$LC_PID"
        [ "$PS_RESULT" = "alive" ] || die 78 "process state uncertain"
        if argv_matches && py same-file "$RENDERED" "$DEST_PLIST"; then
          # Launchd already runs the target collector. Pair the selector
          # without a second bootout. A refused CAS leaves both sides as found.
          if [ -n "$ADVANCE_FROM" ]; then
            advance_selector
          fi
          rm -f -- "$RENDERED"
          RENDERED=""
          finish_install_success
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
    # The fence is re-checked after the old label was sampled and again after
    # any hold, before the marker exists. A helper that died in that window
    # cannot leave this process free to arm on the stale read.
    prove_install_holder
    hold_if_requested "$HOLD_ARM"
    prove_install_holder
    py install-transaction-arm "$STORE" "$GENERATION" "$$" "$INSTALL_FENCE" \
      || lose_install_holder
    MARKER_OWNED=1
    hold_if_requested "$HOLD_MUTATION"
    prove_install_holder
    if [ -e "$DEST_PLIST" ]; then
      HAD_PLIST=1
      backup_out=$(py backup "$DEST_PLIST" "$BACKUP_DIR" "$GENERATION") || die 78 "backup failed"
      BACKUP=$(printf '%s\n' "$backup_out" | sed -n '1p')
    elif [ "$NEED_BOOTOUT" -eq 1 ]; then
      die 78 "running service has no plist preimage"
    fi
    PHASE=BACKED_UP
    # One publisher CAS, then the launchd rebind. The publication lock is
    # free here. Later effects refuse to run unless CURRENT is the target.
    if [ -n "$ADVANCE_FROM" ]; then
      advance_selector
    fi
    if [ "$NEED_BOOTOUT" -eq 1 ]; then
      hold_if_requested "$HOLD_BOOTOUT"
      OLD_PID=${LC_PID:-"-"}
      [ -n "$OLD_PID" ] || OLD_PID="-"
      PHASE=BOOTOUT_STARTED
      # The holder performs the one bootout. Nonzero is never retried.
      run_locked bootout "$LAUNCHCTL" "$PS" "$DOMAIN/$LABEL" "$OLD_PID"
      boot_rc=$?
      if [ "$boot_rc" -eq 0 ]; then
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
      elif [ "$boot_rc" -eq 76 ]; then
        # The helper proved only that the same PID was observable. That is
        # insufficient for NO_EFFECT: re-check full original launchd identity
        # and the plist digest before any selector reversal or receipt.
        if ! service_still_snapshot; then
          stop_uncertain BOOTOUT_ROLLBACK "original service identity unproven after failed bootout"
        fi
        if ! rollback_advanced_selector; then
          write_receipt EFFECT_UNKNOWN BOOTOUT_ROLLBACK \
            "selector rollback failed after bootout had no effect" \
            || die 78 "receipt failed"
          die 78 "EFFECT_UNKNOWN service stopped pending repair: selector rollback failed"
        fi
        write_receipt NO_EFFECT BOOTOUT_NO_EFFECT \
          "bootout returned nonzero and the same pid is still loaded" \
          || die 78 "receipt failed"
        die 78 "bootout had no effect"
      elif selector_moved_before_effect; then
        die 78 "selector moved before bootout"
      elif effect_was_not_started; then
        write_receipt EFFECT_UNKNOWN BOOTOUT "admission holder died before bootout" || true
        die 78 "EFFECT_UNKNOWN service stopped pending repair: admission holder died before bootout"
      else
        write_receipt EFFECT_UNKNOWN BOOTOUT "bootout failed" || true
        die 78 "EFFECT_UNKNOWN service stopped pending repair: bootout failed"
      fi
    fi
    PHASE=PID_GONE
    hold_if_requested "$HOLD_PLIST"
    install_fault="-"
    case "$FAULT" in
      install-before-replace) install_fault=before-replace ;;
      install-after-replace) install_fault=after-replace ;;
    esac
    run_locked install "$RENDERED" "$DEST_PLIST" "$install_fault"
    install_rc=$?
    if [ "$install_rc" -ne 0 ]; then
      # Hermetic-only pause after the failed effect, before rollback.
      hold_if_requested "$HOLD_INSTALL_FAILURE"
      if selector_moved_before_effect; then
        if [ "$BOOTED" -eq 1 ]; then
          recover_or_stop PLIST_ADMIT "selector moved before plist replace"
        fi
        die 78 "selector moved before plist replace"
      fi
      if effect_was_not_started; then
        if [ "$BOOTED" -eq 1 ]; then
          stop_uncertain INSTALL "admission holder died before plist replace"
        fi
        die 78 "EFFECT_UNKNOWN service stopped pending repair: admission holder died before plist replace"
      fi
      if [ "$BOOTED" -eq 1 ]; then
        recover_or_stop INSTALL "plist install failed"
      fi
      # No bootout has occurred. The failed install may have replaced the
      # plist, or a peer may have changed it independently. Do NOT restore
      # here: unconditional atomic-restore can overwrite the peer and
      # conceal its drift in the subsequent preimage check.
      # If saved class/PID/argv/plist/liveness are still proven, the old
      # bytes are already intact and need no write. Otherwise preserve
      # observed bytes, CURRENT and marker and report EFFECT_UNKNOWN.
      if ! service_still_snapshot; then
        stop_uncertain INSTALL "original service/plist identity unproven after failed plist install"
      fi
      if ! rollback_advanced_selector; then
        write_receipt EFFECT_UNKNOWN INSTALL "selector rollback failed" || true
        die 78 "EFFECT_UNKNOWN service stopped pending repair: selector rollback failed"
      fi
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
    bootstrap_once new
    new_rc=$?
    if [ "$new_rc" -ne 0 ] && effect_was_not_started; then
      if selector_moved_before_effect; then
        recover_or_stop BOOTSTRAP_ADMIT "selector moved before bootstrap"
      fi
      recover_or_stop BOOTSTRAP_ADMIT "admission holder died before bootstrap"
    fi
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
      if ! recovered_original_service; then
        stop_uncertain BOOTSTRAP "recovered collector identity unproven"
      fi
      if ! rollback_advanced_selector; then
        stop_uncertain BOOTSTRAP "selector rollback failed"
      fi
      write_receipt RECOVERED BOOTSTRAP "bootstrap failed" || die 78 "receipt failed"
      die 78 "recovered original service: bootstrap failed"
    fi
    PHASE=BOOTSTRAPPED
    # A zero bootstrap rc is an effect, not proof of a verified live collector.
    # In this phase die() must keep the owned marker; stop_uncertain adds a
    # durable EFFECT_UNKNOWN receipt and never issues another launchd command.
    launchctl_print || stop_uncertain POST_BOOTSTRAP_VERIFY "launchctl state uncertain"
    [ "$LC_CLASS" = "loaded-running" ] || stop_uncertain POST_BOOTSTRAP_VERIFY "launchctl state uncertain"
    ps_state "$LC_PID"
    [ "$PS_RESULT" = "alive" ] || stop_uncertain POST_BOOTSTRAP_VERIFY "process state uncertain"
    argv_matches || stop_uncertain POST_BOOTSTRAP_VERIFY "bootstrap did not pin the verified collector"
    finish_install_success
    ;;
  *)
    usage
    ;;
esac
