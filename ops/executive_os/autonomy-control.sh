#!/bin/bash
# Root-only wrapper for the exact installed Executive autonomy control surface.
set -euo pipefail
umask 077

[ "$#" -ge 3 ] || {
  /bin/echo "usage: sudo /bin/bash $0 {status|arm|disarm} --expected-sha SHA [arm gates]" >&2
  exit 64
}
[ "$1" = "status" ] || [ "$1" = "arm" ] || [ "$1" = "disarm" ] || {
  /bin/echo "autonomy-control.sh accepts only status, arm, or disarm" >&2
  exit 64
}
[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "autonomy-control.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "autonomy-control.sh supports macOS only" >&2
  exit 69
}

EXPECTED_SHA=""
EXPECT_VALUE="false"
for argument in "$@"; do
  if [ "$EXPECT_VALUE" = "true" ]; then
    EXPECTED_SHA="$argument"
    EXPECT_VALUE="false"
  elif [ "$argument" = "--expected-sha" ]; then
    EXPECT_VALUE="true"
  fi
done
[ -n "$EXPECTED_SHA" ] && [ "$EXPECT_VALUE" = "false" ] || {
  /bin/echo "autonomy-control.sh requires one exact expected SHA" >&2
  exit 64
}
case "$EXPECTED_SHA" in *[!0-9a-f]*|'') /bin/echo "expected SHA is invalid" >&2; exit 65 ;; esac
[ "${#EXPECTED_SHA}" -eq 40 ] || {
  /bin/echo "expected SHA must contain exactly 40 hexadecimal characters" >&2
  exit 65
}

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"
RELEASE_ROOT="$(cd -P "$SCRIPT_DIR/../.." && /bin/pwd)"
EXPECTED_RELEASE_ROOT="/Library/Application Support/MastermindExecutive/releases/$EXPECTED_SHA"
[ "$RELEASE_ROOT" = "$EXPECTED_RELEASE_ROOT" ] || {
  /bin/echo "autonomy control must run from the exact installed release" >&2
  exit 65
}

CONTROL_PLIST="/Library/LaunchDaemons/com.mastermind.executive.control.plist"
[ -f "$CONTROL_PLIST" ] && [ ! -L "$CONTROL_PLIST" ] || {
  /bin/echo "installed control plist is unavailable" >&2
  exit 65
}
PYTHON_BINARY="$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "$CONTROL_PLIST")"
[ "$PYTHON_BINARY" = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" ] \
  && [ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || {
  /bin/echo "installed control Python is unavailable" >&2
  exit 65
}

exec "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/autonomy_control.py" "$@"
