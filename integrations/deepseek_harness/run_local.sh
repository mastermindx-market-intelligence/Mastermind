#!/bin/sh
# Full DeepSeek Harness web pilot; does not arm Executive or Fabric.
set -eu
DSH_SOURCE="${DSH_SOURCE:-/Volumes/Mastermind/agent-workspaces/dsh-donor-20261022}"
DSH_HOME="${DSH_HOME:-$HOME/.mastermind/dsh-developer-preview}"
DONOR_SHA="687f282e8625c6b8d11ff58211a90524be2e4317"
test -d "$DSH_SOURCE/.git" || { echo "Missing donor checkout" >&2; exit 2; }
actual="$(git -C "$DSH_SOURCE" rev-parse HEAD)"
test "$actual" = "$DONOR_SHA" || { echo "Donor pin mismatch: $actual" >&2; exit 3; }
test -d "$DSH_SOURCE/node_modules" || { echo "Install donor dependencies with pnpm 11.28.5 first" >&2; exit 4; }
mkdir -p "$DSH_HOME"
chmod 700 "$DSH_HOME"
export DSH_HOME
cd "$DSH_SOURCE"
exec node apps/cli/lib/bin.js web --no-open "$@"
