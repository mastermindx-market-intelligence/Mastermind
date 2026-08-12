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
  if /usr/sbin/lsof -nP -a -u "$account" -iTCP -sTCP:LISTEN 2>/dev/null | /usr/bin/awk 'NR > 1 {found=1} END {exit !found}'; then
    /bin/echo "public_listener_violation=$account"
    /usr/sbin/lsof -nP -a -u "$account" -iTCP -sTCP:LISTEN 2>/dev/null
    FAILED=1
  else
    /bin/echo "tcp_listener_count=0 account=$account"
  fi
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
