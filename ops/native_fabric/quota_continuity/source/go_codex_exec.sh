#!/bin/bash
# ONE entry point for OpenCode Go Codex runs.
# Usage: go_codex_exec.sh <cwd> <model> <prompt-file>
# Slot pool = go. CODEX_HOME = scratch copy of ext/codex_go
# (committed config.toml stays clean; codex may write [projects.*] trust).
# Shim token from ext/go_shim/.token into this process env only. Never argv. Never printed.
set -eu

if [ "$#" -lt 3 ]; then
  echo "usage: $(basename "$0") <cwd> <model> <prompt-file>" >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

# A remote lease uses only its short-lived capability. Never read a controller
# token or restart a local service on this path; the existing transport owns it.
if [ -n "${GO_REMOTE_CAPABILITY_FILE:-}" ]; then
  exec python3 "$HERE/go_remote_codex.py" "$@"
fi

if [ "${GO_CODEX_NO_SLOT:-}" != "1" ] && [ -z "${GO_CODEX_SLOTTED:-}" ]; then
  export GO_CODEX_SLOTTED=1
  if python3 -c "
import ast, sys
tree = ast.parse(open(sys.argv[1], encoding='utf-8').read())
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if getattr(t, 'id', None) == 'CAPS':
                keys = ast.literal_eval(node.value)
                sys.exit(0 if 'go' in keys else 1)
sys.exit(1)
" "$HERE/slot.py"; then
    exec python3 "$HERE/slot.py" go --wait "${GO_CODEX_SLOT_WAIT:-1200}" -- "$0" "$@"
  else
    echo "SLOT_POOL_UNKNOWN" >&2
  fi
fi

# Conserve the outer broker account; inherited shim metadata is never authority.
unset GO_BOUND_ACCOUNT GO_LEASE_MODE
if [ "${LANE_LEASED:-0}" = "1" ] || [ -n "${POOL_LEASE_ID:-}" ]; then
  case "${POOL_ACCOUNT:-}" in
    ''|*[!A-Za-z0-9_.:-]*) echo "GO_OUTER_ACCOUNT_INVALID" >&2; exit 78 ;;
  esac
  export GO_BOUND_ACCOUNT="$POOL_ACCOUNT" GO_LEASE_MODE=1
fi

CWD="${1:?cwd}"
MODEL="${2:?model}"
PROMPT_FILE="${3:?prompt-file}"
HERE="$(cd "$(dirname "$0")" && pwd)"
STUDIO_MCP_CODEX_OVERRIDE="$("$HERE/studio_mcp_projection.sh" codex codex-override)" || {
  echo "STUDIO_MCP_PROJECTION_REFUSED provider=codex" >&2
  exit 78
}
SRC_HOME="$HERE/codex_go"
CODEX_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/go_codex_home.XXXXXX")"
cp "$SRC_HOME/config.toml" "$CODEX_SCRATCH/config.toml"
export CODEX_HOME="$CODEX_SCRATCH"
# Track any backgrounded codex/agent child pid this script may have launched.
# codex exec is run synchronously in this script, so $! is never set; the
# variable stays empty in the current shape and the live-child guard is a
# defensive no-op. If a future refactor backgrounds codex, the guard is
# already wired so a still-alive child is not destroyed by our cleanup.
CODEX_CHILD_PID=""
cleanup_codex_home() {
  # I1: the EXIT trap's `|| true` already prevents a failing rm from
  # deciding this script's exit status.
  #
  # I2: a parent's cleanup must not destroy a directory a STILL-RUNNING
  # child it launched is using as its CODEX_HOME. If a tracked child pid
  # is alive at EXIT, leave the scratch dir; a leaked temp dir is
  # harmless, a destroyed live child is not.
  if [ -n "$CODEX_CHILD_PID" ] && kill -0 "$CODEX_CHILD_PID" 2>/dev/null; then
    return 0  # live child: do not touch the scratch dir
  fi
  rm -rf "$CODEX_SCRATCH" 2>/dev/null || true
}
trap cleanup_codex_home EXIT

if ! "$HERE/go_shim/go_ctl.sh" status | grep -q '^running pid='; then
  echo "GO_SHIM_NOT_RUNNING (seat act: bash ext/go_shim/go_ctl.sh start)" >&2
  exit 75
fi

# An older shim silently ignores binding headers. Refuse that route before inference.
if [ "${GO_LEASE_MODE:-0}" = "1" ]; then
  if ! python3 - <<'PY_HEALTH'
import json, sys
from urllib.request import urlopen
try:
    with urlopen("http://127.0.0.1:4142/health", timeout=3) as response:
        data = json.load(response)
    ok = data.get("account_binding") == "exact-v1"
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY_HEALTH
  then
    echo "GO_SHIM_ACCOUNT_BINDING_UNAVAILABLE" >&2
    exit 78
  fi
fi

TOKEN_FILE="$HERE/go_shim/.token"
if [ ! -f "$TOKEN_FILE" ]; then
  echo "go_codex_exec: shim token missing: $TOKEN_FILE" >&2
  exit 2
fi
export GO_SHIM_TOKEN="$(tr -d ' \n' < "$TOKEN_FILE")"

if [ ! -f "$PROMPT_FILE" ]; then
  echo "go_codex_exec: prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

# Prompt via `-` so the text stays off argv. Final agent message goes to
# LAST_MSG via -o for the turn-ending STATUS contract.
LAST_MSG="$CODEX_SCRATCH/last_message.txt"
CODEX_STDERR="$CODEX_SCRATCH/codex.stderr"
MAX_CONTINUES="${GO_CODEX_MAX_CONTINUES:-2}"
case "$MAX_CONTINUES" in
  ''|*[!0-9]*) MAX_CONTINUES=2 ;;
esac
CONTINUATION="You ended your previous turn on a progress note without the required report. Continue the SAME task from where you stopped; do not restart or repeat completed steps; finish every remaining step; your final message must begin with STATUS: COMPLETE or STATUS: BLOCKED and end with the packet's verdict token."

has_status_line() {
  [ -f "$LAST_MSG" ] && grep -Eq '^STATUS: (COMPLETE|BLOCKED)' "$LAST_MSG"
}

has_pong() {
  [ -f "$LAST_MSG" ] && [ "$(tr -d '\\r\\n' < "$LAST_MSG")" = "PONG" ]
}

: > "$CODEX_STDERR"
set +e
codex exec \
    -c "$STUDIO_MCP_CODEX_OVERRIDE" \
  --dangerously-bypass-approvals-and-sandbox \
  --skip-git-repo-check \
  -C "$CWD" \
  -m "$MODEL" \
  -o "$LAST_MSG" \
  - < "$PROMPT_FILE" > /dev/null 2> "$CODEX_STDERR"
rc=$?
set -e
if [ "$rc" -ne 0 ] && [ -s "$CODEX_STDERR" ]; then
  echo "CODEX_EXEC_FAILED rc=$rc stderr_tail_bounded=65536" >&2
  tail -c 65536 "$CODEX_STDERR" >&2 || true
fi

attempt=0
while [ "$rc" -eq 0 ] && [ "$attempt" -lt "$MAX_CONTINUES" ] && ! has_status_line && ! has_pong; do
  attempt=$((attempt + 1))
  echo "AUTO_CONTINUE $attempt/$MAX_CONTINUES" >&2
  : > "$CODEX_STDERR"
  set +e
  codex -C "$CWD" exec resume --last \
      -c "$STUDIO_MCP_CODEX_OVERRIDE" \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    -m "$MODEL" \
    -o "$LAST_MSG" \
    "$CONTINUATION" > /dev/null 2> "$CODEX_STDERR"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ] && [ -s "$CODEX_STDERR" ]; then
    echo "CODEX_EXEC_FAILED rc=$rc stderr_tail_bounded=65536" >&2
    tail -c 65536 "$CODEX_STDERR" >&2 || true
  fi
done

if [ "$rc" -eq 0 ] && ! has_status_line && ! has_pong; then
  # 76 is reserved by the runtime for lease/cleanup uncertainty. Terminal
  # status exhaustion is a proven worker failure, so keep it on a distinct rc.
  echo "AUTO_CONTINUE_EXHAUSTED rc=77 reason=terminal_status_missing" >&2
  rc=77
fi

if [ -f "$LAST_MSG" ]; then
  cat "$LAST_MSG"
fi

if [ -z "$rc" ]; then
  rc=1
fi
exit "$rc"
