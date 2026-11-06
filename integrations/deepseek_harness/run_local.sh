#!/bin/sh
# Pinned DeepSeek Harness full-app *developer* pilot; no Mastermind admission.
# Loops back only, runs in an isolated home/workspace, inherits no model keys.
set -eu
umask 077

DONOR_SHA=687f282e8625c6b8d11ff58211a90524be2e4317
CHECK_ONLY=0
case "$#" in
  0) ;;
  1) if [ "$1" = "--check-only" ]; then CHECK_ONLY=1; else echo "Only --check-only is supported" >&2; exit 2; fi ;;
  *) echo "Unapproved DSH launcher arguments" >&2; exit 2 ;;
esac

if [ -z "${DSH_SOURCE:-}" ]; then
  echo "Set DSH_SOURCE to an exact pinned donor checkout" >&2
  exit 2
fi
case "$DSH_SOURCE" in
  /*) ;;
  *) echo "DSH_SOURCE must be an absolute path" >&2; exit 2 ;;
esac
if [ ! -d "$DSH_SOURCE" ] || [ -L "$DSH_SOURCE" ]; then
  echo "Pinned donor directory unavailable or symlinked" >&2
  exit 2
fi
actual="$(git -C "$DSH_SOURCE" rev-parse HEAD 2>/dev/null || true)"
top="$(git -C "$DSH_SOURCE" rev-parse --show-toplevel 2>/dev/null || true)"
if [ "$top" != "$DSH_SOURCE" ] || [ "$actual" != "$DONOR_SHA" ]; then
  echo "Donor pin mismatch or unavailable: exact approved revision required" >&2
  exit 3
fi
if [ ! -d "$DSH_SOURCE/node_modules" ]; then
  echo "Install pinned donor dependencies before launching" >&2
  exit 4
fi
if [ ! -f "$DSH_SOURCE/apps/cli/lib/bin.js" ] || [ ! -f "$DSH_SOURCE/apps/web/dist/index.html" ]; then
  echo "Full donor artifacts missing: run the upstream dependency-aware build" >&2
  exit 5
fi
node_bin="$(command -v node || true)"
if [ -z "$node_bin" ] || [ ! -x "$node_bin" ]; then
  echo "Node runtime unavailable" >&2
  exit 6
fi
# Port 0 selects an unoccupied local port. No public bind or passthrough
# --host/--public-url/--trusted-host arguments are accepted in this pilot.
port="${DSH_PORT:-0}"
case "$port" in
  ''|*[!0-9]*) echo "DSH_PORT must be 0..65535" >&2; exit 7 ;;
esac
if [ "${#port}" -gt 5 ] || [ "$port" -gt 65535 ]; then
  echo "DSH_PORT must be 0..65535" >&2
  exit 7
fi

pilot_root="${DSH_HOME:-$HOME/.mastermind/dsh-developer-preview}"
case "$pilot_root" in
  /*) ;;
  *) echo "DSH_HOME must be an absolute path" >&2; exit 8 ;;
esac
case "$pilot_root/" in
  "$DSH_SOURCE"/*) echo "Never use the donor checkout as a DSH workspace" >&2; exit 8 ;;
esac
for part in "$pilot_root" "$pilot_root/home" "$pilot_root/state" "$pilot_root/workspace"; do
  if [ -L "$part" ]; then
    echo "DSH pilot state symlink refused" >&2
    exit 8
  fi
done
if [ "$CHECK_ONLY" -eq 1 ]; then
  printf '%s\n' "DSH_PINNED_DEV_PREFLIGHT_PASS"
  exit 0
fi
mkdir -p "$pilot_root/home" "$pilot_root/state" "$pilot_root/workspace"
chmod 700 "$pilot_root" "$pilot_root/home" "$pilot_root/state" "$pilot_root/workspace"

# The donor's default agent workspace is its cwd. Do not give it the source
# checkout or any real account home. env -i withholds ambient credentials.
cd "$pilot_root/workspace"
exec env -i HOME="$pilot_root/home" DSH_HOME="$pilot_root/state" \
  PATH="$(dirname "$node_bin"):/usr/bin:/bin" LANG="en_US.UTF-8" \
  "$node_bin" "$DSH_SOURCE/apps/cli/lib/bin.js" web \
  --host 127.0.0.1 --port "$port" --no-open
