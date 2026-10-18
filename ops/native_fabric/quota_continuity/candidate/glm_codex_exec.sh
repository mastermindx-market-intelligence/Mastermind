#!/bin/bash
# ONE entry point for GLM Codex runs (mm_codex_exec.sh sibling).
# Usage: glm_codex_exec.sh <cwd> <model> <prompt-file>
# Slot pool = glm. CODEX_HOME = scratch copy of ext/codex_glm
# (committed config.toml stays clean; codex may write [projects.*] trust).
# GLM auth is process-local only: remote hosts may inherit the controller-shim bearer from HOST_ENV; local runs fall back to ext/glm_shim/.token. Never argv. Never printed.
set -eu

if [ "$#" -lt 3 ]; then
  echo "usage: $(basename "$0") <cwd> <model> <prompt-file>" >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "${GLM_CODEX_NO_SLOT:-}" != "1" ] && [ -z "${GLM_CODEX_SLOTTED:-}" ]; then
  export GLM_CODEX_SLOTTED=1
  if python3 -c "
import ast, sys
tree = ast.parse(open(sys.argv[1], encoding='utf-8').read())
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if getattr(t, 'id', None) == 'CAPS':
                keys = ast.literal_eval(node.value)
                sys.exit(0 if 'glm' in keys else 1)
sys.exit(1)
" "$HERE/slot.py"; then
    # Seat 2026-09-19: glm-5.3 calls must take the glm-frontier semaphore (vendor in-flight cap 5), not the flash pool (cap 20).
    _POOL="glm"; case "${2:-}" in glm-5.3|glm-5.3-*) case "${2:-}" in *flash*) _POOL="glm";; *) _POOL="glm-frontier";; esac;; esac
    exec python3 "$HERE/slot.py" "$_POOL" --wait "${GLM_CODEX_SLOT_WAIT:-1200}" -- "$0" "$@"
  else
    echo "SLOT_POOL_UNKNOWN" >&2
  fi
fi

CWD="${1:?cwd}"
MODEL="${2:?model}"
PROMPT_FILE="${3:?prompt-file}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# Versioned worker scripts may resolve codex_glm to a host-stable older
# config. A qualified model's context must therefore be explicit on both
# initial CLI invocation and resume, independent of mutable host defaults.
CODEX_CONTEXT_ARGS=()
case "$MODEL" in
  glm-5.3|glm-5.3-flash)
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
SRC_HOME="$HERE/codex_glm"
if [ -n "${REMOTE_SUB_RUN_ID:-}" ]; then
  CODEX_SCRATCH="$(POOL_RECOVERY_MODEL="$MODEL" python3 "$HERE/recovery_artifacts.py" create "$HERE" "$REMOTE_SUB_RUN_ID" glm)" || exit 78
else
  CODEX_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/glm_codex_home.XXXXXX")"
fi
export CODEX_HOME="$CODEX_SCRATCH"
CODEX_TERMINAL_CONFIRMED=0
# Track any backgrounded codex/agent child pid this script may have launched.
# codex exec is run synchronously in this script, so $! is never set; the
# variable stays empty in the current shape and the live-child guard is a
# defensive no-op. If a future refactor backgrounds codex, the guard is
# already wired so a still-alive child is not destroyed by our cleanup.
CODEX_CHILD_PID=""
cleanup_codex_home() {
  _exit_status=$?
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
  if [ -n "${POOL_USAGE_FILE:-}" ] && [ -n "${POOL_USAGE_RUN_ID:-}" ]; then
    # Same-directory temporary file makes the final rename atomic even when
    # the scratch home and receipt directory are on different filesystems.
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
  if [ -n "${GLM_REMOTE_CAPABILITY_FILE:-}" ]; then
    rm -f "$GLM_REMOTE_CAPABILITY_FILE" 2>/dev/null || true
  fi
  if [ -n "${POOL_OUTCOME_FILE:-}" ]; then
    python3 "$HERE/provider_outcome.py" codex "$CODEX_SCRATCH" "$_exit_status" glm "$MODEL" "${LAST_MSG:-$CODEX_SCRATCH/last_message.txt}" || true
  fi
  if [ "$_exit_status" -ne 0 ] || [ "$CODEX_TERMINAL_CONFIRMED" -ne 1 ]; then
    if [ -n "${REMOTE_SUB_RUN_ID:-}" ]; then
      python3 "$HERE/recovery_artifacts.py" retain "$HERE" "$REMOTE_SUB_RUN_ID" "$CODEX_SCRATCH" \
        "${POOL_ORCHESTRATOR_ID:-}" "${POOL_PARENT_RUN_ID:-}" glm "$MODEL" \
        "${POOL_LEASE_ID:-}" "${POOL_ACCOUNT:-}" "${LANE_REMOTE_HOST:-}" "$_exit_status" || true
    fi
    printf 'CODEX_SESSION_RETAINED rc=%s path=%q\n' "$_exit_status" "$CODEX_SCRATCH" >&2 || true
    return 0
  fi
  rm -rf "$CODEX_SCRATCH" 2>/dev/null || rm -rf "$CODEX_SCRATCH" 2>/dev/null || true
}
trap cleanup_codex_home EXIT
cp "$SRC_HOME/config.toml" "$CODEX_SCRATCH/config.toml"

# Remote fleet runs prefer a short-lived broker-bound capability. The provider
# API key never leaves the controller. The capability is consumed into this
# process environment and removed from disk before Codex starts. Local seats
# preserve the existing static controller-bearer path.
GLM_WORKER_ARGS=()
if [ -n "${GLM_REMOTE_CAPABILITY_FILE:-}" ]; then
  case "$GLM_REMOTE_CAPABILITY_FILE" in
    /*) ;;
    *) echo "glm_codex_exec: capability path refused" >&2; exit 78 ;;
  esac
  if [ ! -f "$GLM_REMOTE_CAPABILITY_FILE" ] || [ -L "$GLM_REMOTE_CAPABILITY_FILE" ]; then
    echo "glm_codex_exec: capability file refused" >&2
    exit 78
  fi
  _cap_mode="$(stat -f '%Lp' "$GLM_REMOTE_CAPABILITY_FILE" 2>/dev/null || stat -c '%a' "$GLM_REMOTE_CAPABILITY_FILE" 2>/dev/null || true)"
  if [ "$_cap_mode" != "600" ]; then
    echo "glm_codex_exec: capability mode refused" >&2
    exit 78
  fi
  GLM_SHIM_TOKEN="$(python3 - "$GLM_REMOTE_CAPABILITY_FILE" "$MODEL" <<'PY_GLM_CAP'
import json, os, sys, time
path, model = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    value = json.load(fh)
expected = {
    "token", "expires_at", "account", "lease_id", "model",
    "run_id", "host", "root",
}
if not isinstance(value, dict) or set(value) != expected:
    raise SystemExit(78)
checks = {
    "account": os.environ.get("POOL_ACCOUNT", ""),
    "lease_id": os.environ.get("POOL_LEASE_ID", ""),
    "model": model,
    "run_id": os.environ.get("REMOTE_SUB_RUN_ID", ""),
    "host": os.environ.get("LANE_REMOTE_HOST", ""),
    "root": os.environ.get("POOL_ORCHESTRATOR_ID", ""),
}
if any(not expected_value or value.get(key) != expected_value
       for key, expected_value in checks.items()):
    raise SystemExit(78)
token = value.get("token")
expires = value.get("expires_at")
if not isinstance(token, str) or not token.startswith("v1.") or len(token) > 4096:
    raise SystemExit(78)
if isinstance(expires, bool) or not isinstance(expires, (int, float)):
    raise SystemExit(78)
if not float(expires) > time.time() + 5:
    raise SystemExit(78)
print(token)
PY_GLM_CAP
  )" || { echo "glm_codex_exec: capability validation refused" >&2; exit 78; }
  rm -f "$GLM_REMOTE_CAPABILITY_FILE" || {
    echo "glm_codex_exec: capability cleanup refused" >&2
    exit 78
  }
  export GLM_SHIM_TOKEN
  export GLM_WORKER_RUN="$REMOTE_SUB_RUN_ID"
  export GLM_WORKER_HOST="$LANE_REMOTE_HOST"
  export GLM_WORKER_MODEL="$MODEL"
  GLM_WORKER_ARGS=(
    -c 'model_providers.glm.env_http_headers={ "X-MM-Run-Id" = "GLM_WORKER_RUN", "X-MM-Host" = "GLM_WORKER_HOST", "X-MM-Worker-Model" = "GLM_WORKER_MODEL" }'
    -c 'model_providers.glm.request_max_retries=0'
    -c 'model_providers.glm.stream_max_retries=0'
    -c 'model_providers.glm.supports_websockets=false'
  )
elif [ -n "${GLM_SHIM_TOKEN:-}" ]; then
  case "${GLM_SHIM_URL:-http://127.0.0.1:4141}" in
    http://127.0.0.1:4141) ;;
    *)
      echo "glm_codex_exec: external shim URL refused" >&2
      exit 78
      ;;
  esac
else
  "$HERE/glm_shim/shim_ctl.sh" ensure
  TOKEN_FILE="$HERE/glm_shim/.token"
  if [ ! -f "$TOKEN_FILE" ]; then
    echo "glm_codex_exec: shim token missing: $TOKEN_FILE" >&2
    exit 2
  fi
  export GLM_SHIM_TOKEN="$(tr -d ' \n\r' < "$TOKEN_FILE")"
fi
case "$GLM_SHIM_TOKEN" in
  ''|*$'\n'*|*$'\r'*)
    echo "glm_codex_exec: shim token invalid" >&2
    exit 78
    ;;
esac

if [ ! -f "$PROMPT_FILE" ]; then
  echo "glm_codex_exec: prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

# Keep the task packet byte-exact and put the Fabric contract on Codex's
# higher-priority developer-instructions surface. The memory body still comes
# from sub.sh so Claude- and Codex-harness GLM share one canonical definition.
EFFECTIVE_PROMPT="$CODEX_SCRATCH/task_prompt.md"
cp "$PROMPT_FILE" "$EFFECTIVE_PROMPT"
DEVELOPER_MEMORY="$CODEX_SCRATCH/developer_memory.txt"
if ! "$HERE/sub.sh" __glm_memory _ "$CWD" "$MODEL" > "$DEVELOPER_MEMORY"; then
  echo "glm_codex_exec: GLM_MEMORY_REFUSED" >&2
  exit 78
fi
DEVELOPER_CONFIG=""
if [ -s "$DEVELOPER_MEMORY" ]; then
  DEVELOPER_CONFIG="$(python3 - "$DEVELOPER_MEMORY" <<'PY_DEV_CONFIG'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print("developer_instructions=" + json.dumps(fh.read(), ensure_ascii=True))
PY_DEV_CONFIG
)" || { echo "glm_codex_exec: GLM_MEMORY_CONFIG_REFUSED" >&2; exit 78; }
fi

# Prompt via `-` so the text stays off argv (same as mm_codex_exec.sh).
# Final agent message goes to LAST_MSG via -o so the auto-continue check
# below can see whether the turn ended with the required STATUS: packet.
LAST_MSG="$CODEX_SCRATCH/last_message.txt"
CODEX_STDERR="$CODEX_SCRATCH/codex.stderr"
_CONTINUE_DEFAULT=2
case "${POOL_TASK_COMPLEXITY:-}" in
  C2_COMPLEX_BOUNDED) _CONTINUE_DEFAULT=4 ;;
  C3_FRONTIER_JUDGMENT) _CONTINUE_DEFAULT=8 ;;
esac
MAX_CONTINUES="${GLM_CODEX_MAX_CONTINUES:-$_CONTINUE_DEFAULT}"
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
if [ -n "$DEVELOPER_CONFIG" ]; then
  codex exec \
    -c "$STUDIO_MCP_CODEX_OVERRIDE" \
    ${GLM_WORKER_ARGS[@]+"${GLM_WORKER_ARGS[@]}"} \
    -c "$DEVELOPER_CONFIG" \
    ${CODEX_CONTEXT_ARGS[@]+"${CODEX_CONTEXT_ARGS[@]}"} \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    -C "$CWD" \
    -m "$MODEL" \
    -o "$LAST_MSG" \
    - < "$EFFECTIVE_PROMPT" > /dev/null 2> "$CODEX_STDERR"
else
  codex exec \
    -c "$STUDIO_MCP_CODEX_OVERRIDE" \
    ${GLM_WORKER_ARGS[@]+"${GLM_WORKER_ARGS[@]}"} \
    ${CODEX_CONTEXT_ARGS[@]+"${CODEX_CONTEXT_ARGS[@]}"} \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    -C "$CWD" \
    -m "$MODEL" \
    -o "$LAST_MSG" \
    - < "$EFFECTIVE_PROMPT" > /dev/null 2> "$CODEX_STDERR"
fi
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
  if [ -n "$DEVELOPER_CONFIG" ]; then
    codex -C "$CWD" exec resume --last \
      -c "$STUDIO_MCP_CODEX_OVERRIDE" \
      ${GLM_WORKER_ARGS[@]+"${GLM_WORKER_ARGS[@]}"} \
      -c "$DEVELOPER_CONFIG" \
      ${CODEX_CONTEXT_ARGS[@]+"${CODEX_CONTEXT_ARGS[@]}"} \
      --dangerously-bypass-approvals-and-sandbox \
      --skip-git-repo-check \
      -m "$MODEL" \
      -o "$LAST_MSG" \
      "$CONTINUATION" > /dev/null 2> "$CODEX_STDERR"
  else
    codex -C "$CWD" exec resume --last \
      -c "$STUDIO_MCP_CODEX_OVERRIDE" \
      ${GLM_WORKER_ARGS[@]+"${GLM_WORKER_ARGS[@]}"} \
      ${CODEX_CONTEXT_ARGS[@]+"${CODEX_CONTEXT_ARGS[@]}"} \
      --dangerously-bypass-approvals-and-sandbox \
      --skip-git-repo-check \
      -m "$MODEL" \
      -o "$LAST_MSG" \
      "$CONTINUATION" > /dev/null 2> "$CODEX_STDERR"
  fi
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
if [ "$rc" -eq 0 ] && { has_pong || awk 'NF { print; exit }' "$LAST_MSG" | grep -Eq '^STATUS: COMPLETE([[:space:]]|$)'; }; then
  CODEX_TERMINAL_CONFIRMED=1
fi
exit "$rc"
