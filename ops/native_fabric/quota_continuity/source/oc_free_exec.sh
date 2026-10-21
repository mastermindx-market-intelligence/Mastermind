#!/bin/bash
# ONE entry point for OpenCode Zen FREE-tier runs on the NATIVE opencode harness.
# Usage: oc_free_exec.sh <cwd> <model> <prompt-file>
#
# WHY A NATIVE HARNESS AND NOT go_shim:
#   OpenCode's free tier is CLIENT-GATED. A raw HTTPS request to
#   https://opencode.ai/zen/v1 carrying a valid account key returns
#     403 {"type":"error","error":{"type":"FreeTierError",
#          "message":"OpenCode's free tier can only be used from within OpenCode"}}
#   on both the chat and responses wires (probed 2026-09-22). go_shim is a raw
#   HTTP proxy, so it CANNOT carry any `-free` model. This lane therefore runs the
#   real `opencode` binary, which satisfies the provider's own client gate. This is
#   the documented supported path, not a bypass of it.
#
# QUOTA BOUNDARY:
#   Free-tier calls are billed at $0 and consume NO OpenCode Go quota. They never
#   pass through go_shim, so they are invisible to its account router/usage ledger.
#   Slot pool is therefore `ocfree`, its own semaphore — a free run must not
#   occupy one of the 9 paid `go` slots.
#
# SECRET HANDLING:
#   The account key is read from ~/.opencode-go/accounts.json into this process's
#   environment only. Never on argv, never printed, never written to the log.
set -eu

if [ "$#" -lt 3 ]; then
  echo "usage: $(basename "$0") <cwd> <model> <prompt-file>" >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

# Per-provider call fuse. The outer slot owner enforces the whole commission's
# two-hour wall-clock ceiling; this inner alarm exists for no-slot/leased
# invocations and must not reintroduce the old 15-minute productivity ceiling.
# Complex bounded work gets one hour by default; frontier-tagged work may use
# the full two-hour fabric fuse. Callers may explicitly choose 60..7200 seconds.
_OC_FREE_TIMEOUT_DEFAULT=3600
case "${POOL_TASK_COMPLEXITY:-}" in
  C3_FRONTIER_JUDGMENT) _OC_FREE_TIMEOUT_DEFAULT=7200 ;;
esac
TIMEOUT="${OC_FREE_TIMEOUT:-$_OC_FREE_TIMEOUT_DEFAULT}"
case "$TIMEOUT" in
  ''|*[!0-9]*) echo "oc_free_exec: invalid OC_FREE_TIMEOUT" >&2; exit 2 ;;
esac
if [ "$TIMEOUT" -lt 60 ] || [ "$TIMEOUT" -gt 7200 ]; then
  echo "oc_free_exec: OC_FREE_TIMEOUT must be between 60 and 7200 seconds" >&2
  exit 2
fi

# ── Slot admission (mirrors go_codex_exec.sh) ────────────────────────────────
if [ "${OC_FREE_NO_SLOT:-}" != "1" ] && [ -z "${OC_FREE_SLOTTED:-}" ]; then
  export OC_FREE_SLOTTED=1
  if python3 -c "
import ast, sys
tree = ast.parse(open(sys.argv[1], encoding='utf-8').read())
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if getattr(t, 'id', None) == 'CAPS':
                keys = ast.literal_eval(node.value)
                sys.exit(0 if 'ocfree' in keys else 1)
sys.exit(1)
" "$HERE/slot.py"; then
    exec python3 "$HERE/slot.py" ocfree --wait "${OC_FREE_SLOT_WAIT:-1200}" -- "$0" "$@"
  else
    echo "SLOT_POOL_UNKNOWN" >&2
  fi
fi

CWD="${1:?cwd}"
MODEL="${2:?model}"
PROMPT_FILE="${3:?prompt-file}"
STUDIO_MCP_OPENCODE_URL="$("$HERE/studio_mcp_projection.sh" opencode url)" || {
  echo "STUDIO_MCP_PROJECTION_REFUSED provider=opencode" >&2
  exit 78
}

[ -d "$CWD" ] || { echo "oc_free_exec: cwd not a directory: $CWD" >&2; exit 2; }
[ -f "$PROMPT_FILE" ] || { echo "oc_free_exec: prompt file not found: $PROMPT_FILE" >&2; exit 2; }
command -v opencode >/dev/null 2>&1 || { echo "OPENCODE_CLI_MISSING" >&2; exit 75; }

# ── Account key → env only ──────────────────────────────────────────────────
ACCOUNTS="${GO_ACCOUNTS_PATH:-$HOME/.opencode-go/accounts.json}"
[ -f "$ACCOUNTS" ] || { echo "OC_FREE_ACCOUNTS_MISSING: $ACCOUNTS" >&2; exit 75; }
ACCT="${OC_FREE_ACCOUNT:-C1}"
KEY="$(python3 -c "
import json, sys
acct = sys.argv[2]
d = json.load(open(sys.argv[1]))
e = d.get(acct)
if not isinstance(e, dict) or not e.get('api_key'):
    sys.exit('OC_FREE_ACCOUNT_UNKNOWN: ' + acct)
sys.stdout.write(e['api_key'])
" "$ACCOUNTS" "$ACCT")" || exit 75
export OPENCODE_API_KEY="$KEY"
unset KEY

# ── Sealed runtime home ─────────────────────────────────────────────────────
# OPENCODE_CONFIG alone does NOT isolate: opencode still MERGES
# ~/.config/opencode/{config.json,opencode.json,opencode.jsonc} and every skills
# dir it finds (52 skills, with duplicate-name collisions, observed 2026-09-22).
# Relocating XDG_CONFIG_HOME/XDG_DATA_HOME gives the lane a private config+data
# root. XDG_CACHE_HOME is deliberately LEFT SHARED so the 4.8 MB models.dev
# catalog is not re-downloaded per run.
OC_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/oc_free_home.XXXXXX")"
OC_CHILD_PID=""
cleanup_oc_home() {
  if [ -n "$OC_CHILD_PID" ] && kill -0 "$OC_CHILD_PID" 2>/dev/null; then
    return 0  # live child: never destroy the home it is running out of
  fi
  rm -rf "$OC_SCRATCH" 2>/dev/null || true
}
trap cleanup_oc_home EXIT

mkdir -p "$OC_SCRATCH/config/opencode" "$OC_SCRATCH/data"
# small_model MUST be pinned: opencode's default title/summary agent otherwise
# calls a PAID Zen model (observed: gpt-5.4-nano -> "Insufficient account funds"
# on every run, because this account holds no Zen credit).
cat > "$OC_SCRATCH/config/opencode/opencode.json" <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "model": "opencode/$MODEL",
  "small_model": "opencode/$MODEL",
  "autoupdate": false,
  "share": "disabled",
  "permission": { "edit": "allow", "bash": "allow", "webfetch": "allow" },
  "mcp": { "mastermindStudio": { "type": "remote", "url": "$STUDIO_MCP_OPENCODE_URL" } }
}
EOF
export XDG_CONFIG_HOME="$OC_SCRATCH/config"
export XDG_DATA_HOME="$OC_SCRATCH/data"
unset OPENCODE_CONFIG 2>/dev/null || true

# ── Turn-ending STATUS contract (same shape as the codex lanes) ──────────────
RUN_LOG="$OC_SCRATCH/run.log"
_CONTINUE_DEFAULT=2
case "${POOL_TASK_COMPLEXITY:-}" in
  C2_COMPLEX_BOUNDED) _CONTINUE_DEFAULT=4 ;;
  C3_FRONTIER_JUDGMENT) _CONTINUE_DEFAULT=8 ;;
esac
MAX_CONTINUES="${OC_FREE_MAX_CONTINUES:-$_CONTINUE_DEFAULT}"
case "$MAX_CONTINUES" in ''|*[!0-9]*) MAX_CONTINUES="$_CONTINUE_DEFAULT" ;; esac
if [ "$MAX_CONTINUES" -gt 12 ]; then MAX_CONTINUES=12; fi
CONTINUATION="You ended your previous turn on a progress note without the required report. Continue the SAME task from where you stopped; do not restart or repeat completed steps; finish every remaining step; your final message must begin with STATUS: COMPLETE or STATUS: BLOCKED and end with the packet's verdict token."

has_status_line() { [ -f "$RUN_LOG" ] && grep -Eq '^STATUS: (COMPLETE|BLOCKED)' "$RUN_LOG"; }
has_pong() { [ -f "$RUN_LOG" ] && grep -q '^PONG$' "$RUN_LOG"; }

# OpenCode 1.18.31 reads piped stdin in run.ts before resolving the message.
# Send the prompt on stdin so it never appears in process arguments.

set +e
perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" \
  opencode run --auto --dir "$CWD" -m "opencode/$MODEL" < "$PROMPT_FILE" \
  > "$RUN_LOG" 2>&1
rc=$?
set -e
[ "$rc" -eq 142 ] && echo "OC_FREE_TIMEOUT after ${TIMEOUT}s" >&2

attempt=0
while [ "$rc" -eq 0 ] && [ "$attempt" -lt "$MAX_CONTINUES" ] && ! has_status_line && ! has_pong; do
  attempt=$((attempt + 1))
  echo "AUTO_CONTINUE $attempt/$MAX_CONTINUES" >&2
  set +e
  # --continue is unambiguous here: XDG_DATA_HOME is private to this run, so
  # exactly one session exists in it and no concurrent lane can be resumed.
  perl -e 'alarm shift; exec @ARGV' "$TIMEOUT" \
    opencode run --auto --continue --dir "$CWD" -m "opencode/$MODEL" <<< "$CONTINUATION" \
    >> "$RUN_LOG" 2>&1
  rc=$?
  set -e
done

if [ "$rc" -eq 0 ] && ! has_status_line && ! has_pong; then
  # 76 is reserved by the runtime for lease/cleanup uncertainty. Terminal
  # status exhaustion is a proven worker failure, so keep it on a distinct rc.
  echo "AUTO_CONTINUE_EXHAUSTED rc=77 reason=terminal_status_missing" >&2
  rc=77
fi

[ -f "$RUN_LOG" ] && cat "$RUN_LOG"
exit "$rc"
