#!/bin/bash
# ONE entry point for MiniMax Codex runs (qwen_exec.sh sibling).
# Usage: mm_codex_exec.sh <cwd> <model> <prompt-file>
# Slot pool = minimax. CODEX_HOME = scratch copy of ext/codex_minimax
# (committed config.toml stays clean; codex may write [projects.*] trust).
# Key from ~/.minimax/config.json into this process env only. Never argv. Never printed.
set -eu

if [ "$#" -lt 3 ]; then
  echo "usage: $(basename "$0") <cwd> <model> <prompt-file>" >&2
  exit 2
fi

if [ -z "${MM_CODEX_SLOTTED:-}" ]; then
  export MM_CODEX_SLOTTED=1
  exec python3 "$(cd "$(dirname "$0")" && pwd)/slot.py" minimax-codex --wait "${MM_CODEX_SLOT_WAIT:-1200}" -- "$0" "$@"
fi

CWD="${1:?cwd}"
MODEL="${2:?model}"
PROMPT_FILE="${3:?prompt-file}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# The versioned remote worker scripts may link to older host-stable CODEX_HOME
# configs. Bind qualified 1M/late-compaction policy on BOTH exec and resume;
# the host's mutable config is not evidence that a launched worker uses it.
CODEX_CONTEXT_ARGS=()
case "$MODEL" in
  MiniMax-M3|minimax-m3)
    _ctx="${POOL_MAX_CONTEXT_TOKENS:-1000000}"
    case "$_ctx" in ''|*[!0-9]*|0*) echo "CODEX_CONTEXT_REFUSED reason=window_invalid" >&2; exit 78 ;; esac
    if [ "${#_ctx}" -gt 7 ] || [ "$_ctx" -lt 100000 ] || [ "$_ctx" -gt 1000000 ]; then
      echo "CODEX_CONTEXT_REFUSED reason=window_out_of_bounds" >&2; exit 78
    fi
    _compact="${POOL_AUTO_COMPACT_WINDOW_TOKENS:-}"
    if [ -z "$_compact" ]; then
      _compact=$((_ctx * 9 / 10))
      [ "$_compact" -ge 100000 ] || _compact=100000
    fi
    case "$_compact" in ''|*[!0-9]*|0*) echo "CODEX_CONTEXT_REFUSED reason=compaction_invalid" >&2; exit 78 ;; esac
    if [ "${#_compact}" -gt 7 ] || [ "$_compact" -lt 100000 ] || [ "$_compact" -gt "$_ctx" ]; then
      echo "CODEX_CONTEXT_REFUSED reason=compaction_out_of_bounds" >&2; exit 78
    fi
    # An auto-compaction limit at the *same* token count as the context
    # window leaves no budget for the next prompt or compaction request.
    # Reject the 100K/100K corner rather than implying safe auto-compaction.
    if [ "$_compact" -ge "$_ctx" ]; then
      echo "CODEX_CONTEXT_REFUSED reason=compaction_headroom_required" >&2; exit 78
    fi
    CODEX_CONTEXT_ARGS=(-c "model_context_window=$_ctx" -c "model_auto_compact_token_limit=$_compact")
    echo "CODEX_CONTEXT_POLICY window=$_ctx compact=$_compact" >&2
    ;;
  *)
    if [ -n "${POOL_MAX_CONTEXT_TOKENS:-}" ] || [ -n "${POOL_AUTO_COMPACT_WINDOW_TOKENS:-}" ]; then
      echo "CODEX_CONTEXT_REFUSED reason=unqualified_model" >&2; exit 78
    fi
    ;;
esac
STUDIO_MCP_CODEX_OVERRIDE="$("$HERE/studio_mcp_projection.sh" codex codex-override)" || {
  echo "STUDIO_MCP_PROJECTION_REFUSED provider=codex" >&2
  exit 78
}
SRC_HOME="$HERE/codex_minimax"
CODEX_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/mm_codex_home.XXXXXX")"
cp "$SRC_HOME/config.toml" "$CODEX_SCRATCH/config.toml"
export CODEX_HOME="$CODEX_SCRATCH"
# Track any backgrounded codex/agent child pid this script may have launched.
# codex exec is run synchronously in this script, so $! is never set; the
# variable stays empty in the current shape and the live-child guard is a
# defensive no-op. If a future refactor backgrounds codex, the guard is
# already wired so a still-alive child is not destroyed by our cleanup.
CODEX_CHILD_PID=""
cleanup_codex_home() {
  # I1: the EXIT trap must never decide this script's exit status. codex
  # keeps cloning plugins into $CODEX_SCRATCH/.tmp while the trap runs, so
  # rm can lose the race and fail "Directory not empty" — observed
  # 2026-09-15, a successful PONG canary returned rc=1 purely from this
  # trap. Retry once, then swallow: a leftover temp dir is harmless, a
  # false rc is not.
  #
  # I2: a parent's cleanup must not destroy a directory a STILL-RUNNING
  # child it launched is using as its CODEX_HOME. If a tracked child pid
  # is alive at EXIT, leave the scratch dir; a leaked temp dir is
  # harmless, a destroyed live child is not.
  if [ -n "$CODEX_CHILD_PID" ] && kill -0 "$CODEX_CHILD_PID" 2>/dev/null; then
    return 0  # live child: do not touch the scratch dir
  fi
  # Match GLM's incumbent native receipt contract: account-locally parse
  # private cumulative usage before deleting the scratch session. A failed
  # receipt write must never flip the provider's actual exit code.
  if [ -n "${POOL_USAGE_FILE:-}" ] && [ -n "${POOL_USAGE_RUN_ID:-}" ]; then
    _usage_tmp="$(mktemp "${POOL_USAGE_FILE}.tmp.XXXXXX" 2>/dev/null || true)"
    if [ -n "$_usage_tmp" ]; then
      if chmod 600 "$_usage_tmp" 2>/dev/null &&
          python3 "$HERE/codex_usage.py" "$CODEX_SCRATCH" \
            --run-id "$POOL_USAGE_RUN_ID" --with-native-compactions \
            > "$_usage_tmp" 2>/dev/null; then
        mv -f "$_usage_tmp" "$POOL_USAGE_FILE" 2>/dev/null || true
      fi
      rm -f "$_usage_tmp" 2>/dev/null || true
    fi
  fi
  rm -rf "$CODEX_SCRATCH" 2>/dev/null || rm -rf "$CODEX_SCRATCH" 2>/dev/null || true
}
trap cleanup_codex_home EXIT
export MINIMAX_API_KEY="$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.minimax/config.json")))["api_key"])')"

if [ ! -f "$PROMPT_FILE" ]; then
  echo "mm_codex_exec: prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

# Prompt via `-` so the text stays off argv (same as qwen_exec.sh).
# Final agent message goes to LAST_MSG via -o so the auto-continue check
# below can see whether the turn ended with the required STATUS: packet.
LAST_MSG="$CODEX_SCRATCH/last_message.txt"
CODEX_STDERR="$CODEX_SCRATCH/codex.stderr"
_CONTINUE_DEFAULT=2
case "${POOL_TASK_COMPLEXITY:-}" in
  C2_COMPLEX_BOUNDED) _CONTINUE_DEFAULT=4 ;;
  C3_FRONTIER_JUDGMENT) _CONTINUE_DEFAULT=8 ;;
esac
MAX_CONTINUES="${MM_CODEX_MAX_CONTINUES:-$_CONTINUE_DEFAULT}"
case "$MAX_CONTINUES" in
  ''|*[!0-9]*) MAX_CONTINUES="$_CONTINUE_DEFAULT" ;;
esac
# Explicit callers may tighten to zero or a smaller count. Bound any stale or
# accidental huge override so continuation remains a custody-safe recovery
# mechanism rather than an unbounded turn loop; the outer slot wall clock is
# still the primary whole-commission fuse.
if [ "$MAX_CONTINUES" -gt 12 ]; then MAX_CONTINUES=12; fi
# Fixed secret-free continuation prompt. On argv by design (it is not a secret);
# the original task prompt stays on stdin/`-` and is never repeated here.
CONTINUATION="Your last message did not start with the required terminal STATUS. Continue the SAME task only if important work genuinely remains; do not rerun completed implementation, checks, or tools. If the work is already complete, write its final report NOW without extra tool calls. Begin your first nonblank line with STATUS: COMPLETE or STATUS: BLOCKED, explain concise verified evidence and any unmet requirements, and end with the packet's verdict token. Never claim unverified work."

has_status_line() {
  # A status-like line buried in prose/evidence is not the required terminal
  # report. Only the first nonblank line can establish completion/blockage.
  [ -f "$LAST_MSG" ] &&
    awk 'NF { print; exit }' "$LAST_MSG" |
      grep -Eq '^STATUS: (COMPLETE|BLOCKED)([[:space:]]|$)'
}
has_pong() {
  [ -f "$LAST_MSG" ] && [ "$(tr -d '\r\n' < "$LAST_MSG")" = "PONG" ]
}

# Preserve one *bounded* earlier substantial report inside this job's existing
# private scratch directory. Codex rewrites LAST_MSG on every continuation.
# Only surface this as UNACCEPTED evidence if the whole run exhausts with rc77;
# it never becomes a terminal verdict or creates a separate memory/receipt plane.
UNACCEPTED_EARLY="$CODEX_SCRATCH/first_unaccepted_report.txt"
capture_unaccepted_report() {
  [ -s "$UNACCEPTED_EARLY" ] && return 0
  [ -s "$LAST_MSG" ] || return 0
  _report_bytes="$(wc -c < "$LAST_MSG" 2>/dev/null | tr -d '[:space:]')"
  case "$_report_bytes" in ''|*[!0-9]*) return 0 ;; esac
  [ "$_report_bytes" -ge 256 ] || return 0
  head -c 32768 "$LAST_MSG" > "$UNACCEPTED_EARLY" || true
}

: > "$CODEX_STDERR"
set +e
codex exec \
    -c "$STUDIO_MCP_CODEX_OVERRIDE" \
    "${CODEX_CONTEXT_ARGS[@]}" \
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

# Auto-continue: a lane may end its turn on a progress note ("I'm checking
# whether ...") and exit 0 without the STATUS: packet — nothing resumes it.
# The scratch CODEX_HOME is lane-private and lives for the whole script, so
# the initial session is the newest recorded one and --last is unambiguous.
# Resume until the packet appears or MAX_CONTINUES is exhausted. A non-zero
# rc from codex is never continued; it is surfaced unchanged.
attempt=0
while [ "$rc" -eq 0 ] && [ "$attempt" -lt "$MAX_CONTINUES" ] && ! has_status_line && ! has_pong; do
  capture_unaccepted_report
  attempt=$((attempt + 1))
  echo "AUTO_CONTINUE $attempt/$MAX_CONTINUES" >&2
  : > "$CODEX_STDERR"
  set +e
  codex -C "$CWD" exec resume --last \
      -c "$STUDIO_MCP_CODEX_OVERRIDE" \
      "${CODEX_CONTEXT_ARGS[@]}" \
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
  capture_unaccepted_report
  # 76 is reserved by the runtime for lease/cleanup uncertainty. Terminal
  # status exhaustion is a proven worker failure, so keep it on a distinct rc.
  echo "AUTO_CONTINUE_EXHAUSTED rc=77 reason=terminal_status_missing" >&2
  rc=77
fi

# Keep the seat contract: the lane .out still ends with the final report.
if [ -f "$LAST_MSG" ]; then
  cat "$LAST_MSG"
fi
# A failed terminal contract can otherwise hide earlier useful implementation
# evidence. Keep it unmistakably unaccepted and bounded to 32KiB/80 lines in
# the incumbent parent-visible report stream; rc77 stays the verdict.
if [ "$rc" -eq 77 ] && [ -s "$UNACCEPTED_EARLY" ]; then
  printf '\nUNACCEPTED_EARLIER_REPORT rc=77 reference_only=1\n'
  sed -n '1,80{s/^/EVIDENCE> /;p;}' "$UNACCEPTED_EARLY"
  printf 'END_UNACCEPTED_EARLIER_REPORT\n'
fi

if [ -z "$rc" ]; then
  rc=1
fi
exit "$rc"
