#!/bin/bash
# Root-gated wrapper for evidence-preserving Phase 1C-A acceptance retries.
set -euo pipefail
umask 077

[ "$(/usr/bin/id -u)" -eq 0 ] || {
  /bin/echo "acceptance-retry.sh must run as root" >&2
  exit 77
}
[ "$(/usr/bin/uname -s)" = "Darwin" ] || {
  /bin/echo "acceptance-retry.sh supports macOS only" >&2
  exit 69
}
[ "$#" -eq 2 ] && [ "$1" = "--expected-sha" ] || {
  /bin/echo "usage: sudo /bin/bash $0 --expected-sha 40-hex-sha" >&2
  exit 64
}
EXPECTED_SHA="$2"
case "$EXPECTED_SHA" in *[!0-9a-f]*|'') /bin/echo "expected SHA is invalid" >&2; exit 65 ;; esac
[ "${#EXPECTED_SHA}" -eq 40 ] || {
  /bin/echo "expected SHA must contain exactly 40 hexadecimal characters" >&2
  exit 65
}

SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"
RELEASE_ROOT="$(cd -P "$SCRIPT_DIR/../.." && /bin/pwd)"
EXPECTED_RELEASE_ROOT="/Library/Application Support/MastermindExecutive/releases/$EXPECTED_SHA"
[ "$RELEASE_ROOT" = "$EXPECTED_RELEASE_ROOT" ] || {
  /bin/echo "acceptance retry must run from the exact installed release" >&2
  exit 65
}
if [ -n "$(/usr/bin/find "$RELEASE_ROOT" ! -user root -print -quit)" ] \
  || [ -n "$(/usr/bin/find "$RELEASE_ROOT" ! -group wheel -print -quit)" ] \
  || [ -n "$(/usr/bin/find "$RELEASE_ROOT" -perm +022 -print -quit)" ]; then
  /bin/echo "installed release ownership or modes drifted" >&2
  exit 65
fi
if [ -n "$(/usr/bin/find "$RELEASE_ROOT" -exec /usr/bin/stat -f '%Sp' {} \; \
  | /usr/bin/awk '/\+/{found=1} END {if(found) print "ACL"}')" ]; then
  /bin/echo "installed release contains a filesystem ACL" >&2
  exit 65
fi
CONTROL_PLIST="/Library/LaunchDaemons/com.mastermind.executive.control.plist"
[ -r "$CONTROL_PLIST" ] || {
  /bin/echo "private installed control plist is unavailable; retry install.sh first" >&2
  exit 65
}
PYTHON_BINARY="$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "$CONTROL_PLIST")"
[ "$PYTHON_BINARY" = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" ] \
  && [ -x "$PYTHON_BINARY" ] && [ ! -L "$PYTHON_BINARY" ] || {
  /bin/echo "installed control Python is unavailable" >&2
  exit 65
}
MANIFEST="$RELEASE_ROOT/.executive-release-manifest.json"
[ -f "$MANIFEST" ] && [ ! -L "$MANIFEST" ] || {
  /bin/echo "installed release manifest is unavailable" >&2
  exit 65
}
MANIFEST_COMMIT="$(/usr/bin/plutil -extract commit_sha raw -o - "$MANIFEST")"
TREE_SHA="$(/usr/bin/plutil -extract tree_sha raw -o - "$MANIFEST")"
[ "$MANIFEST_COMMIT" = "$EXPECTED_SHA" ] || {
  /bin/echo "installed release manifest commit differs from expected SHA" >&2
  exit 65
}
"$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/release_manifest.py" verify \
  --root "$RELEASE_ROOT" --commit-sha "$EXPECTED_SHA" --tree-sha "$TREE_SHA" \
  >/dev/null
exec "$PYTHON_BINARY" -I -S -B "$SCRIPT_DIR/acceptance_retry.py" "$@"
