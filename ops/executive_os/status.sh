#!/bin/bash
# Read-only host/service status and no-public-listener proof.
set -u

CONTROL_LABEL="com.mastermind.executive.control"
WORKER_LABEL="com.mastermind.executive.worker.codex"
CONTROL_USER="_mastermind_exec"
WORKER_USER="_mastermind_worker"
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"
FAILED=0

check_file() {
  local path="$1"
  if [ ! -f "$path" ] || [ -L "$path" ]; then
    /bin/echo "missing_or_unsafe_file=$path"
    FAILED=1
    return
  fi
  /usr/bin/stat -f 'file=%N owner=%Su group=%Sg mode=%Sp' "$path" 2>/dev/null \
    || /bin/echo "file=$path metadata=present_private"
}

check_service() {
  local label="$1"
  local output
  if ! output="$(/bin/launchctl print "system/$label" 2>&1)"; then
    /bin/echo "service=$label state=missing"
    FAILED=1
    return
  fi
  /bin/echo "$output" | /usr/bin/awk -v label="$label" '
    /state =|pid =|last exit code =|program =/ {print "service=" label " " $0}
  '
}

check_listeners() {
  local account="$1"
  local account_uid observation status
  # Darwin lsof silently omits processes the caller may not inspect: an
  # unprivileged query for another account exits 1 with no output at all,
  # which is indistinguishable from a true zero. Only root or the account
  # itself can observe; anyone else reports UNKNOWN without querying.
  account_uid="$(/usr/bin/id -u "$account")"
  if [ "$INSPECTOR_UID" != "0" ] && [ "$INSPECTOR_UID" != "$account_uid" ]; then
    /bin/echo "tcp_listener_state=UNKNOWN account=$account reason=insufficient_privilege inspector_uid=$INSPECTOR_UID"
    FAILED=1
    return
  fi
  # One observation per account. A failed or unparseable inspection is
  # UNKNOWN and fails the status; it is never evidence of zero listeners.
  observation="$(/usr/sbin/lsof -nP -a -u "$account" -iTCP -sTCP:LISTEN 2>&1)"
  status=$?
  if [ "$status" -eq 1 ] && [ -z "$observation" ]; then
    /bin/echo "tcp_listener_count=0 account=$account"
    return
  fi
  # Darwin lsof table: a header row, then one 10-token row per listening
  # socket ending in "TCP <addr>:<port> (LISTEN)"; spaces in COMMAND are
  # printed as \x20, so token positions are stable.
  if [ "$status" -eq 0 ] && /bin/echo "$observation" | /usr/bin/awk '
    NR == 1 { if ($1 != "COMMAND" || $2 != "PID" || $NF != "NAME") bad = 1; next }
    { if (NF < 10 || $(NF-2) != "TCP" || $NF != "(LISTEN)") bad = 1; rows++ }
    END { exit (bad || rows < 1) }
  '; then
    /bin/echo "public_listener_violation=$account"
    /bin/echo "$observation"
    FAILED=1
    return
  fi
  if [ "$status" -eq 0 ]; then
    /bin/echo "tcp_listener_state=UNKNOWN account=$account reason=malformed_observation lsof_exit=$status"
  else
    /bin/echo "tcp_listener_state=UNKNOWN account=$account reason=inspection_failed lsof_exit=$status"
  fi
  if [ -n "$observation" ]; then
    /bin/echo "$observation"
  fi
  FAILED=1
}

INSPECTOR_UID="$(/usr/bin/id -u)"

check_file "$CONTROL_PLIST"
check_file "$WORKER_PLIST"
if [ -r "$CONTROL_PLIST" ]; then
  /usr/bin/plutil -lint "$CONTROL_PLIST" || FAILED=1
elif [ -f "$CONTROL_PLIST" ]; then
  /bin/echo "plist=$CONTROL_PLIST lint=skipped_not_readable"
fi
if [ -f "$WORKER_PLIST" ]; then /usr/bin/plutil -lint "$WORKER_PLIST" || FAILED=1; fi
check_service "$CONTROL_LABEL"
check_service "$WORKER_LABEL"

for account in "$CONTROL_USER" "$WORKER_USER"; do
  if ! /usr/bin/id "$account"; then
    FAILED=1
    continue
  fi
  check_listeners "$account"
done

for path in /var/run/mastermind-executive/control.sock /var/run/mastermind-executive/worker.sock; do
  if [ -S "$path" ]; then
    /usr/bin/stat -f 'unix_socket=%N owner=%Su group=%Sg mode=%Sp' "$path"
  else
    /bin/echo "missing_unix_socket=$path"
    FAILED=1
  fi
done

exit "$FAILED"
