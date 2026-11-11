#!/bin/bash
# ONE entry point for Bailian Codex runs.
# Usage: qwen_exec.sh <cwd> <model> <prompt-file>
# Picks a Token-Plan key by NAME; the helper passes its value only to Codex,
# runs `codex exec --json` under CODEX_HOME=$HERE/../codex_bailian, publishes
# only the final response after the same-thread completion loop. Final rc propagates. Bash 3.2 compatible. Never prints a key
# value. Disable inherited shell tracing before handling invocation data.
#
# An explicit <model> is preserved. Blank requests default to qwen3.8-flash;
# the discount window changes capacity/pricing, never the selected model.
# `bailian_keys.py model <requested>` resolves and logs the effective model.
#
# Failover: cool the rejected key down, then RESUME THE SAME CODEX THREAD under
# the next key (max 3 keys per run). Captured output is matched in this order:
#   401  a line carrying 401 together with InvalidApiKey / invalid_api_key /
#        Unauthorized, or a JSON `"code":"InvalidApiKey"`
#        -> cooldown 86400 s, reason invalid_api_key. The key looks valid but the
#           Token-Plan endpoint rejects it; a short bounce would hand a dead key
#           straight back to the pool, so it is parked for a day.
#   403  a line carrying 403 together with AccessDenied / access_denied, or a
#        JSON `"code":"AccessDenied..."`
#        -> cooldown 86400 s, reason access_denied. Same idea: not a quota, it
#           will not clear by waiting 30 minutes.
#   429  HTTP 429 / rate limit / too many requests
#        -> cooldown 1800 s, reason http_429.
#   402  HTTP 402 / unexpected status 402 co-located with quota/insufficient/
#        exhausted/Arrearage, OR a JSON `"code":"InsufficientQuota..."` /
#        `"code":"QuotaExceeded"` / etc., OR Codex reconnect error with quota
#        keyword
#        -> cooldown until the next off-peak window, reason quota_or_insufficient.
#        Tight: quota/insufficient on a bare line (no 402/status) does NOT fire.
# 401/403 evidence has to be tight and co-located: a bare word like
# "unauthorized" elsewhere in the file (agent prose, a lane's own report) must
# not cost a healthy key 24 h. They also fail over only when the run itself
# failed (rc != 0). 429 and 402/quota rules are unchanged.
#
# No usable key: when `bailian_keys.py pick` returns nothing (every key cooling
# or at cap) codex is NEVER launched -- an empty key name used to burn a whole
# lane on `unknown key name ''` / `Missing environment
# variable: BAILIAN_API_KEY`. Instead this script waits: it sleeps
# `bailian_keys.py next_usable_in` seconds (base 30 s, floor 1 s, cap 60 s per
# sleep) and retries, for up to QWEN_EXEC_KEY_WAIT seconds (default 1800) in
# total across the run. When that budget is spent it prints
# `qwen_exec: NO_USABLE_KEY` and exits rc 75 -- the SLOT_TIMEOUT code lane2.py
# already spills on, with nothing on stdout.
set +x
set -eu
# A parent-supplied credential never authorizes this run or reaches its helpers.
# Only bailian_keys.py exec-codex loads the selected value into a Codex child.
unset BAILIAN_API_KEY

# Bad invocation: say so before burning a pool slot (slot.py re-execs us).
if [ "$#" -lt 3 ]; then
  echo "usage: $(basename "$0") <cwd> <model> <prompt-file>" >&2
  exit 2
fi

# A remote child consumes the parent's exact account lease. It cannot
# substitute an account or rebind a lease owned by another process.
if [ "${LANE_LEASED:-0}" = "1" ]; then
  case "${POOL_ACCOUNT:-}" in
    ''|*[!A-Za-z0-9._-]*)
      echo "qwen_exec: OUTER_LEASE_ACCOUNT_REQUIRED" >&2
      exit 78
      ;;
  esac
fi

# Check before the local slot/projection/config/key owners, and again before
# each actual Codex entry if the wall clock moved while the run was waiting.
qwen_not_before_check() {
  if [ "${POOL_CALLER_NOT_BEFORE+x}" = x ]; then
    python3 "$(cd "$(dirname "$0")" && pwd)/commission_deadline.py" not-before || return $?
  fi
}
qwen_not_before_check || exit $?

if [ -z "${QWEN_EXEC_SLOTTED:-}" ]; then
  export QWEN_EXEC_SLOTTED=1
  exec python3 "$(cd "$(dirname "$0")" && pwd)/slot.py" qwen --wait "${QWEN_EXEC_SLOT_WAIT:-3600}" -- "$0" "$@"
fi

CWD="${1:?cwd}"
MODEL="${2:?model}"
PROMPT_FILE="${3:?prompt-file}"

HERE="$(cd "$(dirname "$0")" && pwd)"
STUDIO_MCP_CODEX_OVERRIDE="$("$HERE/studio_mcp_projection.sh" codex codex-override)" || {
  echo "STUDIO_MCP_PROJECTION_REFUSED provider=codex" >&2
  exit 78
}
KEYS="$HERE/bailian_keys.py"
CODEX_HOME_DIR="$HERE/../codex_bailian"
# Fabric support releases contain only attested executor code. The host-owned
# Bailian provider registration is durable outside each versioned release.
# This switches config location only: it does not select an account or bypass
# the existing broker/slot/economic provider gates.
if [ "${LANE_LEASED:-0}" = "1" ]; then
  # The ordinary controller binds its published physical owner explicitly.
  # Its release-relative provider link is already verified by support_bundle;
  # do not select configuration again through a retargetable ~/lanes alias.
  # Other routes retain their existing host-owned configuration selection.
  if [ "${REMOTE_SUB_QWEN_PHYSICAL_CONFIG:-0}" != "1" ]; then
    CODEX_HOME_DIR="$HOME/lanes/codex_bailian"
  fi
  [ -f "$CODEX_HOME_DIR/config.toml" ] || {
    echo "QWEN_REMOTE_PROVIDER_CONFIG_MISSING" >&2
    exit 78
  }
fi
# Selection is consumed here; it grants no authority to a provider/tool child.
unset REMOTE_SUB_QWEN_PHYSICAL_CONFIG
export CODEX_HOME="$CODEX_HOME_DIR"

if [ ! -f "$PROMPT_FILE" ]; then
  echo "qwen_exec: prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

# Use a private unpredictable directory; a PID-derived shared /tmp name could
# collide or inherit prior session material after an interrupted process.
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/qwen_exec.XXXXXXXX")" || {
  echo "QWEN_RUN_HOME_CREATE_REFUSED" >&2
  exit 78
}
chmod 700 "$WORKDIR"
THREAD_FILE="$WORKDIR/thread"
RAW_FILE="$WORKDIR/raw.jsonl"
ERR_FILE="$WORKDIR/err.txt"
TEXT_FILE="$WORKDIR/text.txt"
SCAN_FILE="$WORKDIR/scan.txt"
FEEDBACK_FILE="$WORKDIR/qwen_429_feedback.json"
# This credential-free helper is part of the immutable wrapper, copied only
# into the existing private run directory. No support/dispatch surface changes.
FINAL_STREAM_FILE="$WORKDIR/final_response_stream.py"
cat > "$FINAL_STREAM_FILE" <<'QWEN_FINAL_RESPONSE_STREAM_PY' || exit 78
"""Credential-free complete-turn projection used by the Qwen run wrapper."""
import json
import os
import sys
from typing import IO, Optional


def stream_final_jsonl(in_f: IO[str], out_f: IO[str], thread_path: str,
                       raw_path: str) -> Optional[str]:
    """One completed Codex exec turn, projected to its last assistant message.

    The raw stream remains available to the existing diagnostic/limit scanner.
    Tool output and progress are never a final response, even when they contain
    terminal-looking text. No partial response is published on framing failure.
    This projection does not accept the worker's answer or truncate its content.
    """
    thread_id = None
    last_text = None
    completed = False
    failed = False
    started = False
    with open(raw_path, "w", encoding="utf-8") as raw:
        for line in in_f:
            raw.write(line)
            raw.flush()
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                failed = True
                continue
            if not isinstance(ev, dict):
                failed = True
                continue
            kind = ev.get("type")
            if kind == "thread.started":
                tid = ev.get("thread_id")
                if (not isinstance(tid, str) or not tid.strip()
                        or thread_id is not None or completed):
                    failed = True
                    continue
                thread_id = tid
                with open(thread_path + ".tmp", "w", encoding="utf-8") as target:
                    target.write(tid + "\n")
                os.replace(thread_path + ".tmp", thread_path)
            elif kind == "turn.started":
                if started or completed:
                    failed = True
                started = True
            elif kind in ("error", "turn.failed"):
                failed = True
            elif kind == "item.completed":
                item = ev.get("item")
                if not isinstance(item, dict):
                    failed = True
                    continue
                if item.get("type") == "agent_message":
                    text = item.get("text")
                    if not isinstance(text, str) or completed:
                        failed = True
                    elif item.get("phase") != "commentary":
                        last_text = text
            elif kind == "turn.completed":
                if completed:
                    failed = True
                completed = True
    if failed or not completed or not thread_id or not last_text:
        raise ValueError("QWEN_FINAL_RESPONSE_UNCONFIRMED")
    out_f.write(last_text)
    if not last_text.endswith("\n"):
        out_f.write("\n")
    out_f.flush()
    return thread_id


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("QWEN_FINAL_RESPONSE_ARGUMENTS_INVALID", file=sys.stderr)
        return 77
    try:
        stream_final_jsonl(sys.stdin, sys.stdout, argv[0], argv[1])
    except (ValueError, OSError, UnicodeError):
        print("QWEN_FINAL_RESPONSE_UNCONFIRMED", file=sys.stderr)
        return 77
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
QWEN_FINAL_RESPONSE_STREAM_PY
chmod 600 "$FINAL_STREAM_FILE" || exit 78
NAME=""
MAX_KEYS=3
[ "${LANE_LEASED:-0}" != "1" ] || MAX_KEYS=1
# A successful Codex turn can still end on a progress note. Keep the legacy
# two-resume behavior for short/unclassified work, but give classified long
# work enough same-thread turns to use the outer owned-process window.
_CONTINUE_DEFAULT=2
case "${POOL_TASK_COMPLEXITY:-}" in
  C2_COMPLEX_BOUNDED) _CONTINUE_DEFAULT=4 ;;
  C3_FRONTIER_JUDGMENT) _CONTINUE_DEFAULT=8 ;;
esac
MAX_CONTINUES="${QWEN_EXEC_MAX_CONTINUES:-$_CONTINUE_DEFAULT}"
case "$MAX_CONTINUES" in
  ''|*[!0-9]*) MAX_CONTINUES="$_CONTINUE_DEFAULT" ;;
esac
if [ "$MAX_CONTINUES" -gt 12 ]; then MAX_CONTINUES=12; fi
CONTINUE_USED=0
RC=1
# Key-wait budget (seconds, cumulative across the whole run). A bad override
# falls back to the default instead of disabling the wait.
KEY_WAIT="${QWEN_EXEC_KEY_WAIT:-1800}"
case "$KEY_WAIT" in
  '' | *[!0-9]*) KEY_WAIT=1800 ;;
esac
KEY_POLL=30       # retry step when next_usable_in gives no signal
KEY_SLEEP_MAX=60  # cap on any single sleep, however far off the next expiry is
KEY_WAITED=0      # seconds already spent waiting for a key
PICK_ERR=""

cleanup() {
  # EXIT is the only cleanup edge. Once it starts, finish the release/removal
  # exactly once even if the outer process owner repeats its stop signal.
  trap '' INT TERM HUP
  if [ -n "$NAME" ]; then
    python3 "$KEYS" release "$NAME" "$$" >/dev/null 2>&1 || true
    NAME=""
  fi
  unset BAILIAN_API_KEY 2>/dev/null || true
  # Capture only the *one* native Codex session in this run's private home.
  # Unknown telemetry remains unknown; never synthesize positive token counts.
  if [ -n "${CODEX_RUN_HOME:-}" ] && [ -n "${POOL_USAGE_FILE:-}" ] &&
     [ -n "${POOL_USAGE_RUN_ID:-}" ] && [ -f "$HERE/codex_usage.py" ]; then
    if [ ! -e "$POOL_USAGE_FILE" ] && [ ! -L "$POOL_USAGE_FILE" ]; then
      _usage_tmp="$(mktemp "${POOL_USAGE_FILE}.tmp.XXXXXXXX" 2>/dev/null || true)"
      if [ -n "$_usage_tmp" ]; then
        if chmod 600 "$_usage_tmp" 2>/dev/null &&
           python3 "$HERE/codex_usage.py" "$CODEX_RUN_HOME"              --run-id "$POOL_USAGE_RUN_ID" --with-native-compactions              > "$_usage_tmp" 2>/dev/null; then
          mv -n "$_usage_tmp" "$POOL_USAGE_FILE" 2>/dev/null || true
        fi
        rm -f "$_usage_tmp" 2>/dev/null || true
      fi
    fi
  fi
  rm -rf "$WORKDIR" 2>/dev/null || true
}
# Bash defers trapped signals until its foreground pipeline has settled. A
# signal must then end this wrapper before scan/classification, account rotation
# or another dispatch. The existing outer process-group owner still owns the
# deadline, escalation and residual-process proof; do not signal its group here.
terminate_from_signal() {
  trap '' INT TERM HUP
  printf 'qwen_exec: terminated signal=%s rc=%s\n' "$2" "$1" >&2
  exit "$1"
}
trap cleanup EXIT
trap 'terminate_from_signal 130 INT' INT
trap 'terminate_from_signal 143 TERM' TERM
trap 'terminate_from_signal 129 HUP' HUP

# Fabric release scripts are ephemeral and multiple tasks share a host.
# Keep each Codex session and its native metering private to one leased run.
# Provider authorization still comes from the incumbent lease/key picker.
CODEX_RUN_HOME=""
if [ "${LANE_LEASED:-0}" = "1" ]; then
  CODEX_RUN_HOME="$WORKDIR/codex_home"
  mkdir -m 700 "$CODEX_RUN_HOME" || exit 78
  if [ -L "$CODEX_HOME_DIR/config.toml" ] ||
     [ ! -f "$CODEX_HOME_DIR/config.toml" ]; then
    echo "QWEN_REMOTE_PROVIDER_CONFIG_INVALID" >&2
    exit 78
  fi
  cp "$CODEX_HOME_DIR/config.toml" "$CODEX_RUN_HOME/config.toml" || exit 78
  chmod 600 "$CODEX_RUN_HOME/config.toml" || exit 78
  export CODEX_HOME="$CODEX_RUN_HOME"
fi

log() {
  echo "qwen_exec: $*" >&2
}

# Resolve the effective model once per run, before any key is picked and before
# codex launches. If the resolver is unavailable, keep the requested model rather
# than killing the run.
MODEL_REQUESTED="$MODEL"
MODEL_RESOLVED="$(python3 "$KEYS" model "$MODEL_REQUESTED" 2>/dev/null || true)"
if [ -n "$MODEL_RESOLVED" ]; then
  MODEL="$MODEL_RESOLVED"
fi
log "model=$MODEL (requested=$MODEL_REQUESTED)"

# Official Alibaba Model Studio Codex metadata (qwen3.8-flash, 983616).
# Scope it to this one run's temporary directory. Never touch a global Codex
# config or provider credentials; unsupported aliases retain old fallback.
# Vendor: https://www.alibabacloud.com/help/en/model-studio/codex
CODEX_MODEL_CATALOG_OVERRIDE=""
if [ "$MODEL" = "qwen3.8-flash" ]; then
  QWEN_MODEL_CATALOG_FILE="$WORKDIR/qwen-model-catalog.json"
  if ! printf '%s\n' '{"models":[{"slug":"qwen3.8-flash","display_name":"qwen3.8-flash","description":"DashScope model: qwen3.8-flash","default_reasoning_level":"xhigh","supported_reasoning_levels":[{"effort":"low","description":"Fast responses with lighter reasoning"},{"effort":"medium","description":"Balances speed and reasoning depth"},{"effort":"xhigh","description":"Extra high reasoning depth for complex problems"}],"context_window":983616,"effective_context_window_percent":95,"supports_parallel_tool_calls":false,"supports_image_detail_original":true,"input_modalities":["text","image"],"shell_type":"default","visibility":"list","supported_in_api":true,"priority":2,"base_instructions":"","support_verbosity":false,"supports_reasoning_summaries":false,"experimental_supported_tools":[],"truncation_policy":{"mode":"bytes","limit":10000}}]}' > "$QWEN_MODEL_CATALOG_FILE" ||
     ! chmod 600 "$QWEN_MODEL_CATALOG_FILE"; then
    echo "QWEN_MODEL_CATALOG_CREATE_REFUSED" >&2
    exit 78
  fi
  CODEX_MODEL_CATALOG_OVERRIDE="$(python3 -c 'import json,sys;print("model_catalog_json="+json.dumps(sys.argv[1]))' "$QWEN_MODEL_CATALOG_FILE")" || exit 78
fi

# True when some line of file `$1` carries HTTP status `$2` (right-bounded, so
# 4013 / 4014010 cannot read as a 401) *and* one of the error tokens `$3`.
# Both halves are case-insensitive and must share a single line: that locality
# is what keeps a lane's own prose ("unauthorized access was denied") from
# costing a healthy key a 24 h cooldown.
# The numeric side keeps the shapes the old matcher knew (HTTP 401, status=401)
# and adds a word-bounded bare code, so `(401 Unauthorized)` and
# `"status_code":401,` still match while 4013 / 1401 / f401a never do.
status_with_token() {
  _s="$1"
  _code="$2"
  _token="$3"
  grep -iE "HTTP[[:space:]/]*${_code}([^0-9]|\$)|status[_a-z]{0,6}[^0-9]{0,3}${_code}([^0-9]|\$)|(^|[^0-9A-Za-z])${_code}([^0-9A-Za-z]|\$)" "$_s" \
    | grep -qiE "$_token"
}

# Classify captured output. Prints: none | 401 | 403 | 429 | 402
classify_limit() {
  _f="$1"
  # Auth failures are tested first: a hard key rejection must not be masked by a
  # transient 429 that scrolled past earlier in the same captured output.
  # 401/403 need co-located evidence, not a bare word (see status_with_token).
  # An explicit JSON error code is decisive on its own -- it is a machine field,
  # not prose -- so it does not need a status digit on the same line.
  if grep -qiE '"(code|error_code)"[[:space:]]*:[[:space:]]*"invalid[_[:space:]-]?api[_[:space:]-]?key' "$_f"; then
    echo 401
    return 0
  fi
  if status_with_token "$_f" 401 'invalid[_[:space:]-]?api[_[:space:]-]?key|unauthorized'; then
    echo 401
    return 0
  fi
  if grep -qiE '"(code|error_code)"[[:space:]]*:[[:space:]]*"access[_[:space:]-]?denied' "$_f"; then
    echo 403
    return 0
  fi
  if status_with_token "$_f" 403 'access[_[:space:]-]?denied'; then
    echo 403
    return 0
  fi
  if grep -qiE 'HTTP[[:space:]]*429|[[:space:]]429[[:space:]]|429[[:space:]]|rate limit|too many requests' "$_f"; then
    echo 429
    return 0
  fi
  # Case 1: JSON error object with quota code (machine field, no status digit needed)
  if grep -qiE '"(code|error_code)"[[:space:]]*:[[:space:]]*"(InsufficientQuota|insufficient_quota|QuotaExceeded|Arrearage|AccessDenied\.Unpurchased)' "$_f"; then
    echo 402
    return 0
  fi
  # Case 2: HTTP 402 or "unexpected status" co-located with quota keywords
  if status_with_token "$_f" 402 'quota|insufficient|exhausted|Arrearage'; then
    echo 402
    return 0
  fi
  # Case 3: Codex reconnect error with quota keywords
  if grep -qi 'reconnect' "$_f" | grep -qiE 'quota|insufficient|exhausted|Arrearage'; then
    echo 402
    return 0
  fi
  echo none
}

# True if this run should failover (never on a clean success that merely
# mentioned the word "quota" in ordinary agent text). Kinds outside the 429/402
# list below (i.e. 401/403) fail over only when rc != 0.
should_failover() {
  _rc="$1"
  _kind="$2"
  if [ "$_kind" = "none" ]; then
    return 1
  fi
  if [ "$_rc" -ne 0 ]; then
    return 0
  fi
  if [ "$_kind" = "429" ] || [ "$_kind" = "402" ]; then
    return 0
  fi
  return 1
}

release_current() {
  if [ -n "$NAME" ]; then
    python3 "$KEYS" release "$NAME" "$$" >/dev/null 2>&1 || true
    NAME=""
  fi
  unset BAILIAN_API_KEY 2>/dev/null || true
}

# Take a key slot for this pid and check that its credential can be loaded.
# The value never enters this shell. On failure NAME is empty and PICK_ERR
# carries a short reason. The Codex child rechecks the exact account at exec.
# Called from a condition context, so errexit is
# already off here -- every failure has to be checked explicitly.
pick_and_check() {
  # A wait/rotation can outlive the initial admission or a UTC rollback.
  # Pending/invalid narrowing witnesses terminate, rather than re-enter wait.
  qwen_not_before_check || exit $?
  NAME=""
  PICK_ERR=""
  unset BAILIAN_API_KEY 2>/dev/null || true
  # An outer lease binds one account. Local selection must not reserve a
  # different account even temporarily. Unleased calls retain soft preference.
  _pick_args="pick"
  if [ "${LANE_LEASED:-0}" = "1" ]; then
    _pick_args="pick --require $POOL_ACCOUNT"
  elif [ -n "${POOL_ACCOUNT:-}" ]; then
    case "$POOL_ACCOUNT" in
      *[!A-Za-z0-9._-]*) ;;
      *) _pick_args="pick --prefer $POOL_ACCOUNT" ;;
    esac
  fi
  if ! python3 "$KEYS" $_pick_args >"$WORKDIR/pick.out" 2>"$WORKDIR/pick.err"; then
    PICK_ERR="$(head -n 1 "$WORKDIR/pick.err" 2>/dev/null || true)"
    return 1
  fi
  # One safe token, nothing else, before the account is checked or executed.
  NAME="$(tr -d ' \t\r\n' < "$WORKDIR/pick.out")"
  case "$NAME" in
    '' | *[!A-Za-z0-9._-]*)
      PICK_ERR="$(head -n 1 "$WORKDIR/pick.err" 2>/dev/null || true)"
      if [ -z "$PICK_ERR" ]; then
        PICK_ERR="pick succeeded but printed no usable key name"
      fi
      NAME=""
      return 1
      ;;
  esac
  if [ "${LANE_LEASED:-0}" = "1" ] && [ "$NAME" != "$POOL_ACCOUNT" ]; then
    # Reject before a credential is loaded or Codex starts. Undo only the
    # local candidate key slot; the remote parent retains its broker lease.
    python3 "$KEYS" release "$NAME" "$$" >/dev/null 2>&1 || true
    PICK_ERR="OUTER_LEASE_ACCOUNT_MISMATCH granted=$POOL_ACCOUNT selected=$NAME"
    NAME=""
    return 1
  fi
  # Preserve the existing wait/release behavior without a credential-bearing
  # stdout payload. The helper reports only success or a credential-free error.
  qwen_not_before_check || exit $?
  if ! python3 "$KEYS" check-key "$NAME" > /dev/null 2>"$WORKDIR/pick.err"; then
    PICK_ERR="$(head -n 1 "$WORKDIR/pick.err" 2>/dev/null || true)"
    if [ -z "$PICK_ERR" ]; then
      PICK_ERR="credential unavailable for key=$NAME"
    fi
    python3 "$KEYS" release "$NAME" "$$" >/dev/null 2>&1 || true
    NAME=""
    return 1
  fi
  return 0
}

# After a key rotation the broker lease must follow the new account (B3).
# Release the old lease and acquire one bound to $1; fail the step if we cannot.
# Never puts a key value on argv — account names only.
rebind_pool_lease() {
  _new="$1"
  if [ -z "${POOL_LEASE_ID:-}" ]; then
    return 0
  fi
  if [ -z "$_new" ]; then
    return 1
  fi
  if [ "${POOL_ACCOUNT:-}" = "$_new" ]; then
    return 0
  fi
  _oid="${POOL_ORCHESTRATOR_ID:-}"
  _old="${POOL_LEASE_ID}"
  if [ -n "$_oid" ]; then
    python3 "$HERE/lease_broker.py" release "$_old" --orchestrator-id "$_oid" >/dev/null 2>&1 || true
  else
    python3 "$HERE/lease_broker.py" release "$_old" >/dev/null 2>&1 || true
  fi
  _out=$(python3 "$HERE/lease_broker.py" acquire \
    --orchestrator-id "${_oid:-qwen-exec-$$}" \
    --pool qwen \
    --account "$_new" \
    --task-class "${POOL_TASK_CLASS:-unknown}" \
    --host "$(hostname -s 2>/dev/null || hostname | awk '{print $1}')" \
    --pid "$$" \
    --wait 0) || {
    log "LEASE_REBIND_FAIL old_account=${POOL_ACCOUNT:-none} new_account=$_new"
    return 1
  }
  _lid=$(printf '%s' "$_out" | awk '{for(i=1;i<=NF;i++) if($i ~ /^LEASE=/) {sub(/^LEASE=/,"",$i); print $i}}')
  if [ -z "$_lid" ]; then
    log "LEASE_REBIND_FAIL parse new_account=$_new"
    return 1
  fi
  export POOL_LEASE_ID="$_lid"
  export POOL_ACCOUNT="$_new"
  log "LEASE_REBIND lease=$_lid account=$_new"
  return 0
}

# Wait for a usable key, then take it. Returns 0 with NAME set, or 1 only after
# the QWEN_EXEC_KEY_WAIT budget is spent. Sleep length is
# `next_usable_in` (how long until the earliest cooldown expires) clamped to
# [1, KEY_SLEEP_MAX] seconds; when that gives no signal the base KEY_POLL step
# is used. Logs names and timings only -- never a key value.
acquire_key() {
  _said=0
  while :; do
    if pick_and_check; then
      return 0
    fi
    if [ "${LANE_LEASED:-0}" = "1" ]; then
      log "OUTER_LEASE_KEY_UNAVAILABLE ${PICK_ERR:-pick failed}"
      return 1
    fi
    if [ "$_said" -eq 0 ]; then
      log "no usable key: ${PICK_ERR:-pick failed}"
      _said=1
    fi
    _left=$((KEY_WAIT - KEY_WAITED))
    if [ "$_left" -le 0 ]; then
      return 1
    fi
    _step="$KEY_POLL"
    _nii="$(python3 "$KEYS" next_usable_in 2>/dev/null || true)"
    case "$_nii" in
      '' | -1 | *[!0-9]*) ;;
      0) _step=5 ;;
      *)
        if [ "$_nii" -gt "$KEY_SLEEP_MAX" ]; then
          _step="$KEY_SLEEP_MAX"
        else
          _step="$_nii"
        fi
        ;;
    esac
    if [ "$_step" -gt "$_left" ]; then
      _step="$_left"
    fi
    if [ "$_step" -lt 1 ]; then
      _step=1
    fi
    log "key wait slept=${KEY_WAITED}s budget=${KEY_WAIT}s retry_in=${_step}s next_usable_in=${_nii:-unknown}"
    sleep "$_step"
    KEY_WAITED=$((KEY_WAITED + _step))
  done
}

# Send the terminal response contract on the initial turn as well as resume.
# Keep caller bytes untouched and long prompts on stdin in the private workdir.
INITIAL_PROMPT_FILE=""
build_initial_prompt() {
  if [ -n "$INITIAL_PROMPT_FILE" ]; then
    return 0
  fi
  _ipf="$WORKDIR/initial_prompt.md"
  cp "$PROMPT_FILE" "$_ipf" || return 1
  cat >>"$_ipf" <<'QWEN_TERMINAL_CONTRACT_EOF' || return 1

<<<TERMINAL RESPONSE CONTRACT>>>
When the bounded task above is fully finished, begin your final response with
exactly STATUS: COMPLETE. If an actual blocker prevents completion, begin with
exactly STATUS: BLOCKED and identify the precise limitation. Never mark progress
or unverified work COMPLETE. Preserve the task's verdict token and output bound;
deliver the result once, without repeating it as a second summary. This response
shape grants no additional authority and does not constitute parent acceptance.
QWEN_TERMINAL_CONTRACT_EOF
  chmod 600 "$_ipf" || return 1
  INITIAL_PROMPT_FILE="$_ipf"
  return 0
}

run_codex() {
  qwen_not_before_check || exit $?
  # $1 = mode: new | resume
  # Capture both the provider and the credential-free response projection.
  _mode="$1"
  # Build only the flags applicable to this provider; avoid Bash 3.2 empty
  # array expansion under set -u. The catalog never changes authorization.
  set -- -c "$STUDIO_MCP_CODEX_OVERRIDE"
  if [ -n "$CODEX_MODEL_CATALOG_OVERRIDE" ]; then
    set -- "$@" -c "$CODEX_MODEL_CATALOG_OVERRIDE"
  fi
  : > "$THREAD_FILE"
  : > "$RAW_FILE"
  : > "$ERR_FILE"
  : > "$TEXT_FILE"
  set +e
  if [ "$_mode" = "resume" ]; then
    _prompt="${QWEN_EXEC_RESUME_PROMPT:-Continue exactly where you left off. Do not restart or repeat completed work. Finish every remaining step in the same task. Your final message must begin with STATUS: COMPLETE or STATUS: BLOCKED and end with the required verdict token.}"
    python3 "$KEYS" exec-codex "$NAME" -- resume "$THREAD_ID" \
      "$@" \
      --json \
      --dangerously-bypass-approvals-and-sandbox \
      --skip-git-repo-check \
      -m "$MODEL" \
      "$_prompt" </dev/null 2>"$ERR_FILE" \
      | python3 "$FINAL_STREAM_FILE" "$THREAD_FILE" "$RAW_FILE" > "$TEXT_FILE"
  else
    # Refuse before provider execution if the private prompt cannot be built.
    if ! build_initial_prompt; then
      log "QWEN_INITIAL_PROMPT_REFUSED rc=78"
      exit 78
    fi
    python3 "$KEYS" exec-codex "$NAME" -- \
      "$@" \
      --json \
      --dangerously-bypass-approvals-and-sandbox \
      --skip-git-repo-check \
      -C "$CWD" \
      -m "$MODEL" \
      - < "$INITIAL_PROMPT_FILE" 2>"$ERR_FILE" \
      | python3 "$FINAL_STREAM_FILE" "$THREAD_FILE" "$RAW_FILE" > "$TEXT_FILE"
  fi
  # Capture both statuses in one assignment before Bash overwrites PIPESTATUS.
  # A zero provider exit cannot hide an incomplete/invalid response stream.
  _pipeline_rc=("${PIPESTATUS[@]}")
  _rc="${_pipeline_rc[0]}"
  if [ "$_rc" -eq 0 ] && [ "${_pipeline_rc[1]}" -ne 0 ]; then
    _rc=77
  fi
  # Errexit stays OFF through the tail of this function and is restored by the
  # caller once RC=$? is captured. Re-enabling it here was fatal: `return "$_rc"`
  # with a non-zero status under `set -e` aborts the whole script, so a Codex run
  # that died (401/403/429 after its own reconnects) never reached classify_limit
  # -- no cooldown, no failover, just rc=1.
  if [ -z "$_rc" ]; then
    _rc=1
  fi
  if [ -s "$THREAD_FILE" ]; then
    THREAD_ID="$(tr -d ' \n' < "$THREAD_FILE")"
  fi
  cat "$TEXT_FILE" "$ERR_FILE" "$RAW_FILE" > "$SCAN_FILE" 2>/dev/null || true
  return "$_rc"
}

has_status_line() {
  [ -f "$TEXT_FILE" ] && grep -Eq '^STATUS: (COMPLETE|BLOCKED)' "$TEXT_FILE"
}
has_pong() {
  [ -f "$TEXT_FILE" ] && grep -q '^PONG$' "$TEXT_FILE"
}

THREAD_ID="${QWEN_EXEC_RESUME:-}"
ATTEMPT=0
FINAL_RC=1

while [ "$ATTEMPT" -lt "$MAX_KEYS" ]; do
  ATTEMPT=$((ATTEMPT + 1))
  release_current
  if ! acquire_key; then
    log "NO_USABLE_KEY waited=${KEY_WAITED}s budget=${KEY_WAIT}s attempts=$ATTEMPT rc=75"
    FINAL_RC=75
    break
  fi
  # The helper checks the selected credential again immediately before exec;
  # the wrapper carries only the account name and never a credential value.
  if [ -z "$NAME" ]; then
    log "NO_USABLE_KEY refusing to launch codex without a key rc=75"
    FINAL_RC=75
    break
  fi
  if [ -n "${POOL_LEASE_ID:-}" ] && [ "$NAME" != "${POOL_ACCOUNT:-}" ]; then
    if ! rebind_pool_lease "$NAME"; then
      log "NO_LEASE_FOR_NEW_ACCOUNT account=$NAME rc=75"
      FINAL_RC=75
      break
    fi
  fi
  log "key=$NAME attempt=$ATTEMPT waited=${KEY_WAITED}s thread=${THREAD_ID:-new}"
  set +e
  if [ -n "$THREAD_ID" ] && [ "$ATTEMPT" -gt 1 ]; then
    run_codex resume
    RC=$?
  elif [ -n "${QWEN_EXEC_RESUME:-}" ] && [ "$ATTEMPT" -eq 1 ]; then
    run_codex resume
    RC=$?
  else
    run_codex new
    RC=$?
  fi
  set -e

  # A clean provider rc is not completion if the turn ended on a progress note.
  # Resume the same captured Codex thread under the same account; if a resumed
  # call hits quota/auth, the existing classifier below rotates/reconciles it.
  while [ "$RC" -eq 0 ] && [ "$CONTINUE_USED" -lt "$MAX_CONTINUES" ] && ! has_status_line && ! has_pong; do
    if [ -z "$THREAD_ID" ]; then
      log "AUTO_CONTINUE_UNAVAILABLE thread=none"
      break
    fi
    CONTINUE_USED=$((CONTINUE_USED + 1))
    log "AUTO_CONTINUE $CONTINUE_USED/$MAX_CONTINUES"
    set +e
    run_codex resume
    RC=$?
    set -e
  done
  if [ "$RC" -eq 0 ] && ! has_status_line && ! has_pong && [ "$CONTINUE_USED" -ge "$MAX_CONTINUES" ]; then
    # 76 is reserved by the runtime for lease/cleanup uncertainty. Terminal
    # status exhaustion is a proven worker failure, so keep it on a distinct rc.
    log "AUTO_CONTINUE_EXHAUSTED rc=77 reason=terminal_status_missing"
    RC=77
  fi

  KIND="$(classify_limit "$SCAN_FILE")"
  if should_failover "$RC" "$KIND"; then
    case "$KIND" in
      429)
        SECS=1800
        REASON="http_429"
        ;;
      401)
        SECS=86400
        REASON="invalid_api_key"
        ;;
      403)
        SECS=86400
        REASON="access_denied"
        ;;
      *)
        SECS="$(python3 "$KEYS" seconds_until_offpeak)"
        REASON="quota_or_insufficient"
        ;;
    esac
    log "failover key=$NAME kind=$KIND cooldown=${SECS}s rc=$RC"
    # Ask the SAME helper process to commit the cooldown AND write the actual
    # adaptive-429 policy receipt into this run's private WORKDIR. The wrapper
    # classifier drove this decision, so its inference stays labeled as such;
    # the receipt never upgrades prose into typed or HTTP proof. If the helper
    # cannot take the combined request, the incumbent protective cooldown runs
    # exactly as before and only the receipt is absent.
    if [ "$KIND" = "429" ]; then
      if ! python3 "$KEYS" cooldown-receipt "$NAME" "$SECS" "$REASON" "$FEEDBACK_FILE" qwen_wrapper_inference > /dev/null 2>"$WORKDIR/receipt.err"; then
        log "qwen_429_receipt unavailable cooldown_recommitted helper=$(head -n 1 "$WORKDIR/receipt.err" 2>/dev/null || true)"
        python3 "$KEYS" cooldown "$NAME" "$SECS" "$REASON" >/dev/null
      fi
    else
      python3 "$KEYS" cooldown "$NAME" "$SECS" "$REASON" >/dev/null
    fi
    if [ "$ATTEMPT" -ge "$MAX_KEYS" ]; then
      FINAL_RC=$RC
      break
    fi
    if [ -z "$THREAD_ID" ]; then
      log "no thread id captured; next key will start a new thread"
    fi
    continue
  fi
  FINAL_RC=$RC
  break
done

# Best-effort ledger append (never fails the run).
# R22: task_class keeps the engine-shaped vocabulary the ledger already uses
# ("qwen") because GLM/Bailian accounting and pick's model selection key on it;
# the REAL work class goes in job_class. This entry point is BOTH an executor
# and a reviewer surface -- qwen_review.py:24 runs Qwen second-opinion reviews
# through it -- so job_class must never be hard-coded to "execute": that would
# stamp every Qwen review as execute and re-create exactly the class pollution
# job_class exists to end. Nothing in the kit sets POOL_JOB_CLASS today, so when
# it is unset the flag is OMITTED rather than guessed. The call is duplicated
# instead of built in an array because this host is bash 3.2 under `set -eu`,
# where "${arr[@]}" on an EMPTY array is an unbound-variable error.
if [ -n "${POOL_JOB_CLASS:-}" ]; then
  python3 "$HERE/pool_ledger.py" append \
    --pool bailian \
    --key "${NAME:-none}" \
    --job-class "$POOL_JOB_CLASS" \
    --task-class qwen \
    --rc "$FINAL_RC" \
    --signal "$(echo "${KIND:-ok}" | tr -d ' \n')" \
    2>/dev/null || true
else
  python3 "$HERE/pool_ledger.py" append \
    --pool bailian \
    --key "${NAME:-none}" \
    --task-class qwen \
    --rc "$FINAL_RC" \
    --signal "$(echo "${KIND:-ok}" | tr -d ' \n')" \
    2>/dev/null || true
fi

if [ -n "${THREAD_ID:-}" ]; then
  log "done key=${NAME:-none} thread=$THREAD_ID rc=$FINAL_RC"
else
  log "done key=${NAME:-none} thread=none rc=$FINAL_RC"
fi

# Publish once after the owned continuation loop. Earlier progress/tool events
# remain private scanner input; failed framing cannot leak a success-shaped tail.
if [ "$FINAL_RC" -eq 0 ]; then
  cat "$TEXT_FILE" || exit 77
elif [ -s "$ERR_FILE" ]; then
  cat "$ERR_FILE" >&2
fi

# Prospective final outcome production, BEFORE this run's cleanup removes the
# private WORKDIR. It binds the exact actual final stdout bytes (EMPTY on any
# failure, matching the owned process receipt) to the original private
# one-session Codex capture of this leased run. provider_outcome.py writes
# O_EXCL and withholds the whole outcome when the original scope binding is
# unavailable; this wrapper then only leaves that diagnostic, never a
# synthetic identity. No cooldown receipt exists unless the helper wrote one.
if [ -n "${CODEX_RUN_HOME:-}" ] && [ -n "${POOL_OUTCOME_FILE:-}" ] && [ -f "$HERE/provider_outcome.py" ]; then
  if [ "$FINAL_RC" -eq 0 ] && [ -f "$TEXT_FILE" ]; then
    FINAL_STDOUT_FILE="$TEXT_FILE"
  else
    : > "$WORKDIR/final_stdout_empty"
    FINAL_STDOUT_FILE="$WORKDIR/final_stdout_empty"
  fi
  python3 "$HERE/provider_outcome.py" codex "$CODEX_RUN_HOME" "$FINAL_RC" bailian "$MODEL" "$FINAL_STDOUT_FILE" "$FEEDBACK_FILE" ||
    log "PROVIDER_OUTCOME_INVOCATION_FAILED rc=$FINAL_RC"
fi

exit "$FINAL_RC"
