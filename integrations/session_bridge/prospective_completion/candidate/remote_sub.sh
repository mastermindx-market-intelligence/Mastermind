#!/bin/bash
# Place a sub.sh packet on a telemetry-eligible host and retrieve its stdout.
# Packet content is transported by scp and read remotely; it is never argv.
set -u

# Read/export only: enter before any reservation, lease, trap or worker launch.
if [ "${1:-}" = "--collect-existing" ]; then
  shift
  exec python3 "$(cd "$(dirname "$0")" && pwd)/original_delivery_collector.py" "$@"
fi

if [ "${1:-}" = "--read-artifacts" ]; then
  shift
  exec python3 "$(cd "$(dirname "$0")" && pwd)/artifact_delivery.py" "$@"
fi

usage() {
  cat >&2 <<'USAGE'
usage: remote_sub.sh <host|auto> <mode> <packet_file> <remote_cwd> [model]
                     [--run-id <stable_id>] [--out <local_out>] [--dry-run]
                     [--max-age <secs>] [--refresh]
                     [--expect-output-token <literal-token>]
USAGE
  exit 2
}

HOST_ARG=""
MODE=""
PACKET=""
REMOTE_CWD=""
MODEL=""
LOCAL_OUT=""
RUN_ID_ARG=""
EXPECT_OUTPUT_TOKEN=""
EXPECT_OUTPUT_SPECIFIED=0
DRY_RUN=0
MAX_AGE=600
MAX_AGE_EXPLICIT=0
REFRESH=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --run-id) [ "$#" -ge 2 ] || usage; RUN_ID_ARG="$2"; shift ;;
    --out) [ "$#" -ge 2 ] || usage; LOCAL_OUT="$2"; shift ;;
    --max-age) [ "$#" -ge 2 ] || usage; MAX_AGE="$2"; MAX_AGE_EXPLICIT=1; shift ;;
    --refresh) REFRESH=1 ;;
    --expect-output-token)
      [ "$#" -ge 2 ] || usage
      EXPECT_OUTPUT_TOKEN="$2"
      EXPECT_OUTPUT_SPECIFIED=1
      shift ;;
    -*) usage ;;
    *)
      if [ -z "$HOST_ARG" ]; then HOST_ARG="$1"
      elif [ -z "$MODE" ]; then MODE="$1"
      elif [ -z "$PACKET" ]; then PACKET="$1"
      elif [ -z "$REMOTE_CWD" ]; then REMOTE_CWD="$1"
      elif [ -z "$MODEL" ]; then MODEL="$1"
      else usage
      fi
      ;;
  esac
  shift
done
[ -n "$HOST_ARG" ] && [ -n "$MODE" ] && [ -n "$PACKET" ] && [ -n "$REMOTE_CWD" ] || usage
case "$MODE" in
  glm|glm-codex|minimax|minimax-codex|grok|cursor|qwen|go-codex|codex-native|claude-native|oc-free) ;;
  *) echo "unsupported mode: $MODE" >&2; exit 2 ;;
esac
case "$MODE" in
  go-codex) MODEL="${MODEL:-deepseek-v4.1-flash}" ;;
  qwen) MODEL="${MODEL:-qwen3.8-flash}" ;;
  grok|cursor|codex-native|claude-native|oc-free) [ -n "$MODEL" ] || { echo "Native CLI requires explicit model" >&2; exit 2; } ;;
esac
NATIVE_MODE=0
case "$MODE" in grok|cursor|codex-native|claude-native|oc-free) NATIVE_MODE=1;; esac
case "$MAX_AGE" in
  ''|*[!0-9]*) echo "--max-age must be a non-negative integer" >&2; exit 2 ;;
esac
# Opt-in response-quality gate. A model's rc=0 proves transport completion,
# not that its returned answer contains a caller-required verdict token.
# Tokens are literal, one line, never commands/regex; no retry/redispatch.
if [ "$EXPECT_OUTPUT_SPECIFIED" -eq 1 ] &&
   [[ ! "$EXPECT_OUTPUT_TOKEN" =~ ^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$ ]]; then
  echo "OUTPUT_CONTRACT_TOKEN_REFUSED" >&2
  exit 2
fi

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
HERE="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
if [ -n "${REMOTE_SUB_HERE:-}" ]; then HERE="$REMOTE_SUB_HERE"; fi
SSH_CMD=${REMOTE_SUB_SSH_CMD:-ssh}
SCP_CMD=${REMOTE_SUB_SCP_CMD:-scp}
RSYNC_CMD=${REMOTE_SUB_RSYNC_CMD:-rsync}
REMOTE_SUB_PYTHON=${REMOTE_SUB_PYTHON:-python3}
REMOTE_SUB_BROKER_CMD=${REMOTE_SUB_BROKER_CMD:-}
REMOTE_SUB_LEDGER_CMD=${REMOTE_SUB_LEDGER_CMD:-}
if [ -n "$RUN_ID_ARG" ]; then
  if [[ ! "$RUN_ID_ARG" =~ ^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$ ]]; then
    echo "RUN_ID_REFUSED" >&2
    exit 2
  fi
  ID="$RUN_ID_ARG"
else
  ID="rs_$(date -u +%Y%m%dT%H%M%SZ)_$$"
fi
# Correlation fields describe this transport; they do not grant admission.
RUN_STARTED_SECONDS=$SECONDS
USAGE_VALID=0
VALIDATED_USAGE_FILE=""
declare -a USAGE_TOKEN_ARGS=()
PACKET_BASE="$(basename "$PACKET")"
LOG_DIR="${REMOTE_SUB_LOG_DIR:-$HERE/state/remote_sub}"
LOG_FILE="$LOG_DIR/${ID}.log"
LEASE_ID=""
LEASE_POOL=""
PRESERVE_LEASE=0
LEDGER_POOL=""
ACQUIRE_POOL=""
ORCH_ID=""
GLM_CAP_REMOTE=""
GLM_CAP_LOCAL=""
OPERATOR_CAP_REMOTE=""
OPERATOR_ENV=""
OPERATOR_CHILD_BUDGET="${POOL_OPERATOR_CHILD_BUDGET:-0}"
RC=1
WORKER_RC=""
RC_OBSERVED=0
RESULT_FAILURE_REASON=""
POLL_FILE="$HERE/lanes/${ID}.poll"
declare -a SCRATCH_PATHS=()
declare -a TEMP_FILES=()
SCRATCH_PATHS+=()
TEMP_FILES+=()

log() {
  local line
  line="$(date -u +%Y-%m-%dT%H:%MZ) [remote_sub id=$ID host=$HOST_ARG] $*"
  printf '%s\n' "$line" >&2
  if [ -n "${REMOTE_SUB_LOG_READY:-}" ]; then
    printf '%s\n' "$line" >> "$LOG_FILE" 2>/dev/null || true
  fi
}

if [ -n "${FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION:-}" ]; then
  [ "$ID" = fabric-paid-operator-return-proof-01a11e90-v1 ] &&
  [ "${FABRIC_OPERATOR_PRELEASE_CONTINUATION:-}" = "$ID" ] &&
  [ "$FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION" = "$ID" ] || {
    RC=78; log "ORIGINAL_POST_SUPPORT_SCOPE_REFUSED rc=$RC"; exit "$RC";
  }
fi

if [ "$OPERATOR_CHILD_BUDGET" != "0" ]; then
  [[ "$OPERATOR_CHILD_BUDGET" =~ ^[1-9][0-9]?$ ]] && [ "$OPERATOR_CHILD_BUDGET" -le 64 ] &&
    [ "${POOL_TASK_CLASS:-}" = "domain_orchestration" ] &&
    { { [ "$MODE" = glm ] && [ "$MODEL" = glm-5.3 ]; } || { [ "$MODE" = grok ] && [ "$MODEL" = grok-4.6 ]; }; } || {
      RC=78; log "OPERATOR_SCOPE_REFUSED"; exit "$RC";
    }
  if LC_ALL=C grep -q '^FABRIC_ARTIFACT_REQUEST_V1 ' "$PACKET"; then
    RC=78; log "OPERATOR_ARTIFACT_COMBINATION_UNSUPPORTED"; exit "$RC";
  fi
fi

normalize_remote_cwd() {
  case "$1" in
    "$HOME") printf '%s\n' "$HOME" ;;
    "$HOME"/*) printf '%s\n' "$1" ;;
    *) return 2 ;;
  esac
}

# The receiving host owns tilde expansion; its account may differ from ours.
if [[ "$REMOTE_CWD" == "~"* && "$REMOTE_CWD" != "~" && "$REMOTE_CWD" != "~/"* ]]; then
  log "REMOTE_CWD_REFUSED path=$REMOTE_CWD"
  exit 2
fi

release_lease() {
  if [ "$PRESERVE_LEASE" = "1" ]; then
    log "LEASE_PRESERVED effect_unknown=1 lease=$LEASE_ID"
    return 0
  fi
  if [ -n "$LEASE_ID" ]; then
    if [ -n "$ORCH_ID" ]; then
      broker release "$LEASE_ID" --orchestrator-id "$ORCH_ID" >/dev/null 2>&1 || true
    else
      broker release "$LEASE_ID" >/dev/null 2>&1 || true
    fi
  fi
}

cleanup() {
  local controller_exit_rc=$?
  # Finish this one cleanup with the captured status; later signals cannot re-enter it.
  trap ':' INT TERM HUP
  RC="${RC:-1}"
  # A successful worker does not make a later controller failure successful.
  # Preserve existing nonzero effect/transport classifications.
  if [ "$RC" -eq 0 ] && [ "$controller_exit_rc" -ne 0 ]; then
    RC="$controller_exit_rc"
    log "CONTROLLER_EXIT_FAILED rc=$RC prior_rc=0"
  fi
  if [ "${#TEMP_FILES[@]}" -gt 0 ]; then
    for _path in "${TEMP_FILES[@]}"; do rm -f "$_path"; done
  fi
  if [ "${#SCRATCH_PATHS[@]}" -gt 0 ]; then
    for _path in "${SCRATCH_PATHS[@]}"; do rm -f "$_path"; done
  fi
  release_lease
  exit "$RC"
}
# Signal handlers select the shell status; EXIT owns cleanup exactly once.
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

show_args() {
  printf '%s\n' "$@"
}
broker() {
  if [ -n "$REMOTE_SUB_BROKER_CMD" ]; then
    "$REMOTE_SUB_BROKER_CMD" "$@"
  else
    "$REMOTE_SUB_PYTHON" "$HERE/lease_broker.py" "$@"
  fi
}
ledger() {
  if [ -n "$REMOTE_SUB_LEDGER_CMD" ]; then
    "$REMOTE_SUB_LEDGER_CMD" "$@"
  else
    "$REMOTE_SUB_PYTHON" "$HERE/pool_ledger.py" "$@"
  fi
}
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    show_args "$@"
    return 0
  fi
  "$@"
}

AUTO_REQUESTED=0
if [ "$HOST_ARG" = auto ]; then
  AUTO_REQUESTED=1
  # Live occupancy changes much faster than the historical 10m
  # telemetry allowance. Refresh eligible stale candidates before
  # a new remote lease; preserve dry-run as read-only and honor a
  # deliberately supplied --max-age override.
  if [ "$DRY_RUN" -eq 0 ]; then
    [ "$MAX_AGE_EXPLICIT" -eq 1 ] || MAX_AGE=30
    REFRESH=1
  fi
  PICK_ARGS=(--mode "$MODE" --max-age "$MAX_AGE")
  [ "$REFRESH" -eq 1 ] && PICK_ARGS+=(--refresh)
  if [ "${REMOTE_SUB_ALLOW_SEAT:-0}" != 1 ]; then
    PICK_ARGS+=(--exclude m2)
  fi
  # Host selection is a read-only policy decision and must execute even in
  # --dry-run mode. Using run() here caused dry-run to capture the printed
  # argv (python3 ... host_pick.py ...) as HOST_ARG instead of a host name.
  HOST_ARG=$(HOST_PICK_SELECTION_KEY="$ID" "$REMOTE_SUB_PYTHON" "$HERE/host_pick.py" "${PICK_ARGS[@]}") || {
    RC=$?
    log "NO_HOST rc=$RC"
    exit "$RC"
  }
fi

# Local M2 dispatch does not capture stdout into LOCAL_OUT, so it cannot
# meet an opt-in exact-output contract. Refuse before packet/lease/launch
# rather than silently reporting rc0 without verifying the model's answer.
if [ "$HOST_ARG" = m2 ] && [ "$EXPECT_OUTPUT_SPECIFIED" -eq 1 ] &&
   [ "$DRY_RUN" -ne 1 ]; then
  RC=78
  echo "OUTPUT_CONTRACT_LOCAL_UNSUPPORTED before_launch=1" >&2
  exit "$RC"
fi

if [ -z "$LOCAL_OUT" ]; then
  LOCAL_OUT="$HERE/lanes/${ID}.remote.stdout"
fi

# The optional success contract must validate newly collected bytes, never
# stale output or symlinks from a prior run. Refuse before provider leasing.
if [ "$EXPECT_OUTPUT_SPECIFIED" -eq 1 ] && [ "$DRY_RUN" -ne 1 ]; then
  if [ -e "$LOCAL_OUT" ] || [ -L "$LOCAL_OUT" ]; then
    RC=78
    log "OUTPUT_CONTRACT_DESTINATION_PREEXISTS rc=78 before_lease=1"
    exit "$RC"
  fi
fi

if [ ! -f "$PACKET" ]; then
  log "PACKET_MISSING path=$PACKET_BASE"
  RC=2
  exit "$RC"
fi

if [ "$DRY_RUN" -ne 1 ]; then
  mkdir -p "$HERE/lanes" 2>/dev/null || true
  chmod 700 "$HERE/lanes" 2>/dev/null || true
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  # The existing per-run durable log is also the idempotency fence. Reserve it
  # atomically before any provider lease or remote effect can begin.
  if "$REMOTE_SUB_PYTHON" - "$LOG_FILE" "$ID" "$HOST_ARG" "$MODE" "$MODEL" "$PACKET" "$REMOTE_CWD" "$HERE" <<'PY_RESERVE'
import os
import sys

try:
    fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
except FileExistsError:
    if os.environ.get('FABRIC_OPERATOR_PRELEASE_CONTINUATION') == sys.argv[2]:
        sys.path.insert(0,sys.argv[8])
        from fabric_operator_recovery import reserve
        try:reserve(*sys.argv[1:8])
        except Exception:
            print("ORIGINAL_PRELEASE_CONTINUATION_REFUSED",file=sys.stderr)
            raise SystemExit(75)
        raise SystemExit(0)
    print(f"RUN_EXISTS id={sys.argv[2]}", file=sys.stderr)
    raise SystemExit(75)
except OSError as exc:
    print(f"LOG_RESERVATION_FAILED id={sys.argv[2]} errno={exc.errno} before_lease=1 before_launch=1", file=sys.stderr)
    raise SystemExit(73)
os.close(fd)
PY_RESERVE
  then
    :
  else
    RESERVATION_RC=$?
    case "$RESERVATION_RC" in
      75|73) RC=$RESERVATION_RC ;;
      *) RC=73; echo "LOG_RESERVATION_UNAVAILABLE id=$ID interpreter_rc=$RESERVATION_RC before_lease=1 before_launch=1" >&2 ;;
    esac
    exit "$RC"
  fi
  chmod 600 "$LOG_FILE" 2>/dev/null || true
  REMOTE_SUB_LOG_READY=1
  log "RUN_RESERVED explicit=$([ -n "$RUN_ID_ARG" ] && echo 1 || echo 0)"
  SCRATCH_PATHS=("$POLL_FILE")
  LEASE_OUTPUT_FILE="$(mktemp "${TMPDIR:-/tmp}/remote_sub_lease.XXXXXX")"
  TEMP_FILES+=("$LEASE_OUTPUT_FILE")
fi

if [ "$HOST_ARG" = m2 ]; then
  if [ "$OPERATOR_CHILD_BUDGET" != "0" ] || [ -n "${FABRIC_OPERATOR_CHILD_ID:-}" ]; then
    RC=78; log "OPERATOR_REQUIRES_ADMITTED_REMOTE_PATH"; exit "$RC";
  fi
  log "LOCAL_HOST packet=$PACKET_BASE cwd=$REMOTE_CWD"
  if [ "$DRY_RUN" -eq 1 ]; then
    show_args bash "$HERE/sub.sh" "$MODE" "<contents-of-$PACKET_BASE>" "$REMOTE_CWD" $MODEL
    RC=0
    exit "$RC"
  fi
  LOCAL_SUB_CMD=${REMOTE_SUB_LOCAL_CMD:-bash}
  if [ -n "$MODEL" ]; then
    RC=0
    "$LOCAL_SUB_CMD" "$HERE/sub.sh" "$MODE" "$(cat "$PACKET")" "$REMOTE_CWD" "$MODEL" || RC=$?
  else
    RC=0
    "$LOCAL_SUB_CMD" "$HERE/sub.sh" "$MODE" "$(cat "$PACKET")" "$REMOTE_CWD" || RC=$?
  fi
  exit "$RC"
fi

# The same canonical registry constraints apply to initial and CWD-aware
# reselected candidates. Do not duplicate or weaken these policy checks.
load_host_registry() {
  REGISTRY=$("$REMOTE_SUB_PYTHON" -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh: doc=json.load(fh)
entry=doc.get(sys.argv[2])
if not isinstance(entry, dict): raise SystemExit(3)
alias=entry.get("ssh_alias")
cores=entry.get("cores")
max_active=entry.get("max_active")
load_gate=entry.get("load_gate")
roles=entry.get("roles")
mode=sys.argv[3]
allowed=entry.get("allowed_modes")
if not isinstance(alias,str) or not isinstance(cores,int) or not isinstance(max_active,int) or not isinstance(load_gate,(int,float)): raise SystemExit(3)
if roles is not None:
    if not isinstance(roles,list) or "lanes" not in roles: raise SystemExit(4)
if mode in {"go-codex", "grok", "cursor", "codex-native", "claude-native", "oc-free"} and allowed is None: raise SystemExit(5)
if allowed is not None:
    if not isinstance(allowed,list) or not all(isinstance(v,str) and v for v in allowed): raise SystemExit(3)
    if mode not in allowed: raise SystemExit(5)
min_free_mem = entry.get("min_free_mem_gb", 0)
if (isinstance(min_free_mem, bool) or not isinstance(min_free_mem, (int, float))
        or not 0 <= min_free_mem <= 256):
    raise SystemExit(3)
thermal_enabled = entry.get("require_thermal", False)
if type(thermal_enabled) is not bool:
    raise SystemExit(3)
thermal_limit = entry.get("cpu_tctl_limit_c") if thermal_enabled else 0
if (isinstance(thermal_limit, bool)
        or not isinstance(thermal_limit, (int, float))
        or (thermal_enabled and not 50 <= thermal_limit <= 100)):
    raise SystemExit(3)
min_free_disk = entry.get("min_free_gb", 0)
checkout_reserve = entry.get("checkout_reserve_gb", 0)
if (type(min_free_disk) not in (int, float) or not 0 <= min_free_disk <= 1024
        or type(checkout_reserve) not in (int, float) or not 0 <= checkout_reserve <= 128):
    raise SystemExit(3)
# Absent reserve does not change legacy Mac/seat last-mile behavior.
last_mile_disk = float(min_free_disk) + float(checkout_reserve) if checkout_reserve else 0.0
print(alias, cores, max_active, load_gate, min_free_mem, thermal_limit, f"{last_mile_disk:.3f}")
' "$HERE/hosts.json" "$HOST_ARG" "$MODE" 2>/dev/null) || REGISTRY=""
  [ -n "$REGISTRY" ] || { log "HOST_POLICY_REFUSED host=$HOST_ARG"; RC=3; return "$RC"; }
  read -r SSH_ALIAS CORES MAX_ACTIVE LOAD_GATE MIN_FREE_MEM_GB MAX_CPU_TCTL_C MIN_FREE_DISK_GB <<< "$REGISTRY"
  LANE_HOST_LOAD_RATIO=$(awk -v g="$LOAD_GATE" -v c="$CORES" 'BEGIN{if(c+0<=0) exit 1; printf "%.4f", (g+0)/(c+0)}') || { log "HOST_POLICY_RATIO_REFUSED"; RC=3; return "$RC"; }
}
load_host_registry || exit "$RC"

# Economic decision is pure: static model/class policy only, before a lease.
# Dry-run stays an inspection path. Real children repeat the same check.
if [ "$DRY_RUN" -ne 1 ]; then
  case "$MODE" in
    glm|glm-codex|grok|cursor|go|go-codex|qwen|bailian|codex-native|claude-native|oc-free)
      POLICY_SOURCE="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
      if ! ECONOMIC_DECISION=$("$REMOTE_SUB_PYTHON" "$POLICY_SOURCE/pick.py" launch-policy \
          --mode "$MODE" --class "${POOL_TASK_CLASS:-}" --model "$MODEL" \
          --task-complexity "${POOL_TASK_COMPLEXITY:-}" \
          --escalation-reason "${POOL_ESCALATION_REASON:-}"); then
        log "ECONOMIC_POLICY_REFUSED $ECONOMIC_DECISION"
        RC=78
        exit "$RC"
      fi
      case "$MODE" in
        glm|glm-codex)
          ECONOMIC_MODEL=$(printf '%s' "$ECONOMIC_DECISION" | "$REMOTE_SUB_PYTHON" -c 'import json,sys; print(str(json.load(sys.stdin).get("requested_model") or ""))' 2>/dev/null) || ECONOMIC_MODEL=""
          [ -n "$ECONOMIC_MODEL" ] || { log "ECONOMIC_POLICY_REFUSED normalized_glm_model_missing"; RC=78; exit "$RC"; }
          MODEL="$ECONOMIC_MODEL"
          ;;
      esac
      log "ECONOMIC_POLICY $ECONOMIC_DECISION"
      ;;
  esac
fi

case "$MODE" in
  minimax|minimax-codex)
    ACQUIRE_POOL=minimax
    LEDGER_POOL=minimax
    ;;
  codex-native|claude-native)
    ACQUIRE_POOL="$MODE"
    LEDGER_POOL="$MODE"
    ;;
  oc-free)
    ACQUIRE_POOL=ocfree
    LEDGER_POOL=ocfree
    ;;
  grok)
    ACQUIRE_POOL=grok
    LEDGER_POOL=grok
    ;;
  cursor)
    ACQUIRE_POOL=cursor
    LEDGER_POOL=cursor
    ;;
  glm|glm-codex)
    ACQUIRE_POOL=glm
    LEDGER_POOL=glm
    if [ "$MODE" = glm ] && [ "$MODEL" = "glm-5.3" ]; then
      if "$REMOTE_SUB_PYTHON" -c '
import sys
sys.path.insert(0, sys.argv[1])
import slot
sys.exit(0 if "glm-frontier" in slot.CAPS else 1)
' "$HERE" >/dev/null 2>&1; then
        ACQUIRE_POOL=glm-frontier
        LEDGER_POOL=glm
      fi
    fi
    ;;
  go-codex)
    ACQUIRE_POOL=go
    LEDGER_POOL=go
    ;;
  qwen)
    ACQUIRE_POOL=bailian
    LEDGER_POOL=bailian
    ;;
esac

# Worker-runtime policy. Keep a hard deadline for custody/recovery, but do not
# force long bounded native workers into the old ~3 minute window.
if [ "$MODE" = go-codex ]; then
  POLL_SECS="${REMOTE_SUB_POLL_SECS:-10}"
  MAX_SECS="${REMOTE_SUB_MAX_SECS:-210}"
elif [ "$NATIVE_MODE" -eq 1 ]; then
  POLL_SECS="${REMOTE_SUB_POLL_SECS:-10}"
  MAX_SECS="${REMOTE_SUB_MAX_SECS:-3600}"
else
  # Long workers may run for hours, but completion visibility should not lag
  # by the old 150-second polling interval. A 30-second controller poll keeps
  # SSH overhead bounded while avoiding minutes of post-completion latency
  # that can trip an upper transport/tool deadline after the worker is done.
  POLL_SECS="${REMOTE_SUB_POLL_SECS:-30}"
  MAX_SECS="${REMOTE_SUB_MAX_SECS:-7200}"
fi
case "$POLL_SECS" in ''|*[!0-9]*|0) echo "invalid REMOTE_SUB_POLL_SECS" >&2; RC=2; exit "$RC";; esac
case "$MAX_SECS" in ''|*[!0-9]*|0) echo "invalid REMOTE_SUB_MAX_SECS" >&2; RC=2; exit "$RC";; esac
if [ "$MAX_SECS" -gt 7200 ]; then
  echo "REMOTE_SUB_MAX_SECS must not exceed 7200" >&2
  RC=2
  exit "$RC"
fi
if [ "$MAX_SECS" -lt "$POLL_SECS" ]; then
  echo "REMOTE_SUB_MAX_SECS must be at least REMOTE_SUB_POLL_SECS" >&2
  RC=2
  exit "$RC"
fi

# A caller-supplied short deadline must not silently collapse a task that was
# already classified as long bounded work. Complexity is an existing economic
# classification, not a new lifecycle plane. C2 gets at least one hour; C3 gets
# the full two-hour fabric fuse. The special go-codex profile remains short by
# design and is not lifted here.
RUNTIME_FLOOR_SECS=0
if [ "$MODE" != go-codex ]; then
  case "${POOL_TASK_COMPLEXITY:-}" in
    C0_MECHANICAL|C1_ROUTINE_BOUNDED) RUNTIME_FLOOR_SECS=0 ;;
    C2_COMPLEX_BOUNDED) RUNTIME_FLOOR_SECS=3600 ;;
    C3_FRONTIER_JUDGMENT) RUNTIME_FLOOR_SECS=7200 ;;
    "")
      # Legacy callers predate complexity tagging. Treat a stale short override
      # as unsafe for real worker labor; short probes must opt into C0/C1.
      RUNTIME_FLOOR_SECS=3600
      ;;
  esac
fi
if [ "$RUNTIME_FLOOR_SECS" -gt 0 ] && [ "$MAX_SECS" -lt "$RUNTIME_FLOOR_SECS" ]; then
  log "RUNTIME_FLOOR_LIFT complexity=${POOL_TASK_COMPLEXITY:-unclassified} requested=$MAX_SECS effective=$RUNTIME_FLOOR_SECS"
  MAX_SECS="$RUNTIME_FLOOR_SECS"
fi

ADMISSION_WAIT_SECS="${REMOTE_SUB_ADMISSION_WAIT_SECS:-20}"
ADMISSION_RETRY_SECS="${REMOTE_SUB_ADMISSION_RETRY_SECS:-2}"
case "$ADMISSION_WAIT_SECS" in ''|*[!0-9]*) echo "invalid REMOTE_SUB_ADMISSION_WAIT_SECS" >&2; RC=2; exit "$RC";; esac
case "$ADMISSION_RETRY_SECS" in ''|*[!0-9]*|0) echo "invalid REMOTE_SUB_ADMISSION_RETRY_SECS" >&2; RC=2; exit "$RC";; esac
if [ "$ADMISSION_WAIT_SECS" -gt 120 ]; then
  echo "REMOTE_SUB_ADMISSION_WAIT_SECS must not exceed 120" >&2
  RC=2
  exit "$RC"
fi
if [ "$ADMISSION_RETRY_SECS" -gt 10 ]; then
  echo "REMOTE_SUB_ADMISSION_RETRY_SECS must not exceed 10" >&2
  RC=2
  exit "$RC"
fi
RETRYABLE_ADMISSION_MODE=0
case "$MODE" in
  glm|glm-codex|minimax|minimax-codex|qwen) RETRYABLE_ADMISSION_MODE=1 ;;
esac
if [ -n "${FABRIC_COMPLETION_CONTEXT:-}" ]; then RETRYABLE_ADMISSION_MODE=0; fi
if [ "$MAX_SECS" -gt "$POLL_SECS" ]; then
  CHILD_TIMEOUT=$((MAX_SECS - POLL_SECS))
else
  CHILD_TIMEOUT=$MAX_SECS
fi
if [ "$MODE" = go-codex ] && { [ "$CHILD_TIMEOUT" -lt 1 ] || [ "$CHILD_TIMEOUT" -gt 240 ]; }; then
  RC=2; log "GO_CHILD_TIMEOUT_REFUSED"; exit "$RC"
fi

# The provider lease must cover the owned worker plus settlement headroom.
# Heartbeats renew normal work; this TTL also gives exact-carrier recovery time
# if the controller loses the terminal receipt.
PROVIDER_LEASE_TTL=$((CHILD_TIMEOUT + 300))
[ "$PROVIDER_LEASE_TTL" -lt 900 ] && PROVIDER_LEASE_TTL=900
[ "$PROVIDER_LEASE_TTL" -gt 7500 ] && PROVIDER_LEASE_TTL=7500

# A healthy SSH/tool host is not necessarily ready for this task's worktree.
# Validate task-specific source roots before reserving scarce provider slots.
# Remote Python expands ~ for the selected host's user, just as the real
# remote_sub_exec does. Hex transport prevents shell interpolation of the path.
# Generic CWDs remain on the legacy execution path: newly admitted workers
# may legitimately rely on later support setup for ~/lanes/tmp and ext.
case "$REMOTE_CWD" in
  "~/lanes/wt/"* | "/home/"*/"lanes/wt/"* | "~/lanes/repos/"* | "/home/"*/"lanes/repos/"*)
    if [ "$DRY_RUN" -eq 0 ]; then
      REMOTE_PROJECT_CWD_HEX=$("$REMOTE_SUB_PYTHON" -c \
        'import sys; print(sys.argv[1].encode("utf-8").hex())' "$REMOTE_CWD") || {
        RC=78; log "REMOTE_PROJECT_CWD_ENCODING_REFUSED"; exit "$RC"
      }
      REMOTE_PROJECT_CWD_PROBE="python3 -c 'import os,sys; p=bytes.fromhex(sys.argv[1]).decode(\"utf-8\"); sys.exit(0 if os.path.isdir(os.path.expanduser(p)) else 78)' '$REMOTE_PROJECT_CWD_HEX'"
      AUTO_CWD_PROBES=0
      while :; do
        AUTO_CWD_PROBES=$((AUTO_CWD_PROBES + 1))
        if [ "$AUTO_CWD_PROBES" -gt 32 ]; then
          RC=78
          log "NO_HOST_WITH_PROJECT_CWD probe_limit=32"
          exit "$RC"
        fi
        if "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=8 "$SSH_ALIAS" \
            "$REMOTE_PROJECT_CWD_PROBE"; then
          log "REMOTE_PROJECT_CWD_PREFLIGHT_OK"
          break
        else
          PROBE_RC=$?
        fi
        if [ "$PROBE_RC" -ne 78 ]; then
          # Unknown SSH or authorization failure is not host retry permission.
          RC=75
          log "REMOTE_PROJECT_CWD_PREFLIGHT_UNAVAILABLE remote_rc=$PROBE_RC"
          exit "$RC"
        fi
        if [ "$AUTO_REQUESTED" -ne 1 ]; then
          RC=78
          log "REMOTE_PROJECT_CWD_MISSING_PRELEASE"
          exit "$RC"
        fi
        # Only a proven missing task directory permits an alternative host.
        # The canonical picker and eligibility gates apply on every retry.
        log "AUTO_PROJECT_CWD_SKIP host=$HOST_ARG"
        PICK_ARGS+=(--exclude "$HOST_ARG")
        NEXT_HOST=$(HOST_PICK_SELECTION_KEY="$ID" "$REMOTE_SUB_PYTHON" "$HERE/host_pick.py" "${PICK_ARGS[@]}") || {
          RC=78
          log "NO_HOST_WITH_PROJECT_CWD"
          exit "$RC"
        }
        if [ -z "$NEXT_HOST" ] || [ "$NEXT_HOST" = "$HOST_ARG" ]; then
          RC=78
          log "NO_HOST_WITH_PROJECT_CWD"
          exit "$RC"
        fi
        # Local seat execution has a distinct path earlier in this script.
        # Never turn a late auto fallback into an unreviewed remote-to-seat hop.
        if [ "$NEXT_HOST" = m2 ]; then
          RC=78
          log "AUTO_PROJECT_CWD_LOCAL_RESELECT_REFUSED"
          exit "$RC"
        fi
        HOST_ARG="$NEXT_HOST"
        load_host_registry || exit "$RC"
        log "AUTO_PROJECT_CWD_RESELECTED"
      done
    fi
    ;;
esac

OPERATOR_CHILD_ARGS=()
if [ -n "${FABRIC_OPERATOR_CHILD_ID:-}" ]; then
  [ "$FABRIC_OPERATOR_CHILD_ID" = "$ID" ] || { RC=78; log "OPERATOR_CHILD_ID_REFUSED"; exit "$RC"; }
  OPERATOR_CHILD_ARGS=(--operator-child-id "$ID")
fi
if [ -n "$ACQUIRE_POOL" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    show_args "<broker>" acquire --orchestrator-id "remote-sub-$ID" --pool "$ACQUIRE_POOL" --task-class "remote-$MODE" --model "$MODEL" --pid "$$" --ttl "$PROVIDER_LEASE_TTL" --wait "${REMOTE_SUB_LEASE_WAIT:-3600}"
    log "LEASE_WAIT pool=$ACQUIRE_POOL wait=${REMOTE_SUB_LEASE_WAIT:-3600}"
  else
    log "LEASE_WAIT pool=$ACQUIRE_POOL wait=${REMOTE_SUB_LEASE_WAIT:-3600}"
    ORCH_ID="${POOL_ORCHESTRATOR_ID:-${CLAUDE_SESSION_ID:-remote-sub-$ID}}"
    if [ "$NATIVE_MODE" -eq 1 ]; then
      broker acquire ${OPERATOR_CHILD_ARGS[@]+"${OPERATOR_CHILD_ARGS[@]}"} --host "$HOST_ARG" --orchestrator-id "$ORCH_ID" --pool "$ACQUIRE_POOL" --task-class "remote-$MODE" --model "$MODEL" --pid "$$" --ttl "$PROVIDER_LEASE_TTL" --wait "${REMOTE_SUB_LEASE_WAIT:-3600}" > "$LEASE_OUTPUT_FILE" || {
        RC=$?
        log "LEASE_REFUSED rc=$RC"
        exit "$RC"
      }
    else
      broker acquire ${OPERATOR_CHILD_ARGS[@]+"${OPERATOR_CHILD_ARGS[@]}"} --host "$HOST_ARG" --orchestrator-id "$ORCH_ID" --pool "$ACQUIRE_POOL" --task-class "remote-$MODE" --model "$MODEL" --pid "$$" --ttl "$PROVIDER_LEASE_TTL" --wait "${REMOTE_SUB_LEASE_WAIT:-3600}" > "$LEASE_OUTPUT_FILE" || {
        RC=$?
        log "LEASE_REFUSED rc=$RC"
        exit "$RC"
      }
    fi
    LEASE_ID=$(awk '{for(i=1;i<=NF;i++) if($i ~ /^LEASE=/) {sub(/^LEASE=/,"",$i); print $i; exit}}' "$LEASE_OUTPUT_FILE")
    LEASE_POOL="$ACQUIRE_POOL"
    POOL_ACCOUNT=$(awk '{for(i=1;i<=NF;i++) if($i ~ /^ACCOUNT=/) {sub(/^ACCOUNT=/,"",$i); print $i; exit}}' "$LEASE_OUTPUT_FILE")
    if [ -z "$LEASE_ID" ]; then
      log "LEASE_PARSE_FAILED"
      RC=75
      exit "$RC"
    fi
    log "LEASE_OK pool=$ACQUIRE_POOL"
    if [ "${FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION:-}" = "$ID" ] && [ "$POOL_ACCOUNT" != chairman-max ]; then
      RC=78; log "ORIGINAL_ACCOUNT_CONTINUATION_REFUSED rc=$RC"; exit "$RC";
    fi
  fi
fi

RPATH='export PATH=$HOME/lanes/venv/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH'
REMOTE_PACKET="~/lanes/tmp/${ID}.txt"
REMOTE_STDOUT="lanes_${ID}.stdout"
REMOTE_RC="lanes_${ID}.rc"

run "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
  'mkdir -p ~/lanes/tmp ~/lanes/ext/active ~/lanes/ext/lanes ~/lanes/orch/fabric' || { RC=$?; log "REMOTE_SETUP_FAILED rc=$RC"; exit "$RC"; }

SUPPORT_FILES=(
  pools.yaml fabric_policy_snapshot.py remote_sub_exec.py native_remote.py fabric_operator_client.py fabric_operator_stop.py fabric_operator_diagnostics.py artifact_production.py artifact_reader.py lane_runtime.py sub.sh slot.py pick.py glm_bound_claude.py model_tier.py yes
  codex_usage.py go_remote_codex.py go_remote_capsule.py
  mm_codex_exec.sh glm_codex_exec.sh go_codex_exec.sh qwen_exec.sh
  fabric_client_projection.py studio_mcp_projection.sh
  mm_feeder_lib.py pool_ledger.py lease_broker.py glm_keys.py bailian_keys.py
)
SUPPORT_MANIFEST="$LOG_DIR/${ID}.support.json"
REMOTE_SUPPORT_SOURCE="~/lanes/tmp/${ID}.support-src"
TEMP_FILES+=("$SUPPORT_MANIFEST")
SUPPORT_DIGEST="<verified-code-digest>"
POLICY_SHA="<verified-policy-digest>"
if [ "$DRY_RUN" -eq 0 ]; then
  SUPPORT_META=$("$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" support-meta "$HERE" "$SUPPORT_MANIFEST" "${SUPPORT_FILES[@]}"
  ) || { RC=3; log "SUPPORT_HASH_FAILED"; exit "$RC"; }
  read -r SUPPORT_DIGEST POLICY_SHA <<< "$SUPPORT_META"
  if [[ ! "$SUPPORT_DIGEST" =~ ^[a-f0-9]{64}$ || ! "$POLICY_SHA" =~ ^[a-f0-9]{64}$ ]]; then
    RC=3; log "SUPPORT_METADATA_INVALID"; exit "$RC"
  fi
fi

run_scp() {
  if [ "$DRY_RUN" -eq 1 ]; then
    show_args "$SCP_CMD" -q "$PACKET_BASE" "$SSH_ALIAS:$REMOTE_PACKET"
    show_args "$SCP_CMD" -q "${SUPPORT_FILES[@]}" support_bundle.py pools.yaml "$(basename "$SUPPORT_MANIFEST")" "$SSH_ALIAS:$REMOTE_SUPPORT_SOURCE/"
    show_args "<support-publication>" "same shared ext/active and ext/orch state; code=$SUPPORT_DIGEST; immutable advisory snapshot; shared admission recheck"
    return 0
  fi
  "$SCP_CMD" -q "$PACKET" "$SSH_ALIAS:$REMOTE_PACKET" || return $?
  # Per-run upload directory is new; existing published code is never overwritten.
  "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
    "mkdir -p \"\$HOME/lanes/support-releases\" && mkdir \"\$HOME/lanes/tmp/${ID}.support-src\"" || return $?
  _src=()
  for _f in "${SUPPORT_FILES[@]}"; do [ "$_f" = pools.yaml ] || _src+=("$HERE/$_f"); done
  "$SCP_CMD" -q "${_src[@]}" "$HERE/support_bundle.py" "$SSH_ALIAS:$REMOTE_SUPPORT_SOURCE/" || return $?
  "$SCP_CMD" -q "$SUPPORT_MANIFEST" "$SSH_ALIAS:$REMOTE_SUPPORT_SOURCE/manifest.json" || return $?
  "$SCP_CMD" -q "$HERE/../orch/fabric/pools.yaml" "$SSH_ALIAS:$REMOTE_SUPPORT_SOURCE/pools.yaml" || return $?
  # New generation carries hash-bound advisory policy. Publication checks
  # exact semantic compatibility without replacing policy under active workers.
  # Physical admission rechecks under the original lock before marker creation.
  "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
    "$RPATH; python3 \"\$HOME/lanes/tmp/${ID}.support-src/support_bundle.py\" \"\$HOME/lanes/tmp/${ID}.support-src\" \"\$HOME/lanes/ext\" \"\$HOME/lanes/tmp/${ID}.support-src/manifest.json\" && test -f \"\$HOME/lanes/support-releases/${SUPPORT_DIGEST}/ext/remote_sub_exec.py\"" \
    || { log "SUPPORT_PUBLICATION_REFUSED"; return 75; }
  log "SUPPORT_VERSION_READY digest=$SUPPORT_DIGEST policy=$POLICY_SHA"
  return 0
}

# Explicit local-principal operator opt-in; ordinary leaves stay unchanged.
if [ "$OPERATOR_CHILD_BUDGET" != "0" ]; then
  OPERATOR_PACKET=$(mktemp "$LOG_DIR/${ID}.operator-packet.XXXXXX") || exit 78
  TEMP_FILES+=("$OPERATOR_PACKET")
  "$REMOTE_SUB_PYTHON" - "$PACKET" "$OPERATOR_PACKET" "$HERE" <<'PY_OPERATOR_PACKET'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
from fabric_operator_client import OPERATOR_INSTRUCTIONS
Path(sys.argv[2]).write_bytes(Path(sys.argv[1]).read_bytes()+OPERATOR_INSTRUCTIONS.encode())
PY_OPERATOR_PACKET
  [ "$?" -eq 0 ] || { RC=78; log "OPERATOR_PACKET_REFUSED"; exit "$RC"; }
  PACKET="$OPERATOR_PACKET"
fi

log "SCP packet=$PACKET_BASE support=executor-surface"
if [ "${FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION:-}" = "$ID" ]; then
  [ "$SUPPORT_DIGEST" = 1a68f64af6955a62309e4aa9eb7e3f0ba08985bd88290af60d4b1197890750eb ] || {
    RC=78; log "ORIGINAL_SUPPORT_CONTINUATION_REFUSED rc=$RC"; exit "$RC";
  }
  FINAL_OPERATOR_PACKET_SHA=$("$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" glm-cap-sha "$PACKET") || exit 78
  "$SSH_CMD" -T -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
    "python3 - '$ID' '$SUPPORT_DIGEST' '$FINAL_OPERATOR_PACKET_SHA'" <<'PY_VERIFY_ORIGINAL_SUPPORT'
import hashlib,json,os,stat,sys
from pathlib import Path
run,support,packet_digest=sys.argv[1:]
assert run=='fabric-paid-operator-return-proof-01a11e90-v1'
assert support=='1a68f64af6955a62309e4aa9eb7e3f0ba08985bd88290af60d4b1197890750eb'
def read_regular(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        assert stat.S_ISREG(st.st_mode) and st.st_uid==os.getuid() and 0<st.st_size<=limit
        with os.fdopen(fd,'rb',closefd=False) as f:data=f.read(limit+1)
        assert len(data)==st.st_size
        return data
    finally:os.close(fd)
root=Path.home()/'lanes/support-releases'/support
assert stat.S_ISDIR(root.lstat().st_mode) and stat.S_IMODE(root.stat().st_mode)==0o555
meta=json.loads(read_regular(root/'RELEASE.json',65536))
canonical=json.dumps({'schema':'remote-support-code.v1','files':meta['files']},sort_keys=True,separators=(',',':')).encode()
assert hashlib.sha256(canonical).hexdigest()==support and meta['digest']==support
for name,want in meta['files'].items():
    assert Path(name).name==name
    assert hashlib.sha256(read_regular(root/'ext'/name,2097152)).hexdigest()==want
assert hashlib.sha256(read_regular(Path.home()/'lanes/tmp'/(run+'.txt'),1048576)).hexdigest()==packet_digest
capsule=Path.home()/'lanes/tmp'/(run+'.operator-cap.json')
try:capsule.lstat()
except FileNotFoundError:pass
else:raise ValueError('original capsule unexpectedly exists')
print('ORIGINAL_SUPPORT_PACKET_VERIFIED_CAPSULE_NOT_PUBLISHED')
PY_VERIFY_ORIGINAL_SUPPORT
  [ "$?" -eq 0 ] || { RC=78; log "ORIGINAL_PUBLICATION_CONTINUATION_REFUSED rc=$RC"; exit "$RC"; }
  log "SUPPORT_VERSION_REUSED original_publication_verified=1 digest=$SUPPORT_DIGEST"
else
  run_scp || { RC=$?; log "SCP_FAILED rc=$RC"; exit "$RC"; }
fi

if [ "$MODE" = go-codex ] && [ "$DRY_RUN" -eq 0 ]; then
  GO_RUN_RECEIPT="$LOG_DIR/${ID}.go-run.json"
  # Default to preserving the existing lease before any possible worker effect.
  PRESERVE_LEASE=1
  RC=0
  "$REMOTE_SUB_PYTHON" "$HERE/go_remote_run.py" \
    --run-id "$ID" --root "$ORCH_ID" --lease-id "$LEASE_ID" --account "$POOL_ACCOUNT" \
    --host "$HOST_ARG" --ssh-alias "$SSH_ALIAS" --model "$MODEL" --cwd "$REMOTE_CWD" \
    --support-digest "$SUPPORT_DIGEST" --child-timeout "$CHILD_TIMEOUT" \
    --max-active "$MAX_ACTIVE" --load-ratio "$LANE_HOST_LOAD_RATIO" \
    --min-free-mem-gb "$MIN_FREE_MEM_GB" --max-cpu-tctl-c "$MAX_CPU_TCTL_C" \
    --min-free-disk-gb "$MIN_FREE_DISK_GB" \
    --out "$LOCAL_OUT" --receipt "$GO_RUN_RECEIPT" || RC=$?
  if "$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" go-settled "$GO_RUN_RECEIPT" "$ID" "$ORCH_ID" "$LEASE_ID" "$POOL_ACCOUNT" "$HOST_ARG" "$MODEL"
  then PRESERVE_LEASE=0; log "GO_SETTLED receipt=$(basename "$GO_RUN_RECEIPT")"
  else log "GO_EFFECT_UNKNOWN same_carrier_reconciliation_required=1"
  fi
else
REMOTE_INNER='umask 077 || exit; python3 "$HOME/lanes/support-releases/$SUPPORT_DIGEST/ext/remote_sub_exec.py" "$KEY" "$MODE" "$PACKET" "$REMOTE_CWD" "$MODEL"; echo $? > "$RC_FILE"'
HOST_ENV='source ~/lanes/ext/HOST_ENV.sh 2>/dev/null'

if [ "$DRY_RUN" -eq 1 ]; then
  show_args "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" "<launch: $REMOTE_PACKET -> $(basename "$REMOTE_PACKET")>"
  show_args "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" "test -f \"$REMOTE_RC\" && cat \"$REMOTE_RC\" (poll ${POLL_SECS}s)"
  show_args "$RSYNC_CMD" -aq "$SSH_ALIAS:~/lanes/ext/$REMOTE_STDOUT" "<out:$(basename "$LOCAL_OUT")>"
  show_args "<ledger>" append --pool "$LEDGER_POOL" --task-class "remote-$MODE" --rc 0 --signal ok
  RC=0
  exit "$RC"
fi

# The already leased GLM account must exist on this exact selected host.
# This is a readiness read, not account selection or a provider request. The
# launcher repeats the same key validator immediately before its actual exec.
if [ "$MODE" = "glm" ]; then
  GLM_ACCOUNT_QUOTED=$("$REMOTE_SUB_PYTHON" -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "${POOL_ACCOUNT:-}") || {
    RC=78; log "GLM_ACCOUNT_READINESS_ENCODING_FAILED rc=$RC"; exit "$RC";
  }
  GLM_ACCOUNT_READY=""
  GLM_ACCOUNT_READ_RC=0
  GLM_ACCOUNT_READY=$("$SSH_CMD" -T -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
    "$RPATH; $HOST_ENV; python3 \"\$HOME/lanes/support-releases/$SUPPORT_DIGEST/ext/glm_keys.py\" account-ready $GLM_ACCOUNT_QUOTED" \
    2>/dev/null) || GLM_ACCOUNT_READ_RC=$?
  if [ "$GLM_ACCOUNT_READ_RC" -ne 0 ] || [ "$GLM_ACCOUNT_READY" != "1" ]; then
    RC=78; log "GLM_EXACT_ACCOUNT_READINESS_REFUSED read_rc=$GLM_ACCOUNT_READ_RC rc=$RC"; exit "$RC";
  fi
  log "GLM_EXACT_ACCOUNT_READY"
fi

# GLM-Codex remote workers prefer a short-lived capability signed by the
# controller shim and bound to this exact broker lease/root/account/model/run/host.
# A host-local native GLM installation remains a compatibility fallback (M1).
# Provider API keys are never copied by this path.
if [ "$MODE" = "glm-codex" ]; then
  if "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=8 "$SSH_ALIAS"       'curl -fsS --max-time 3 http://127.0.0.1:4141/health | python3 -c '"'"'import json,sys; v=json.load(sys.stdin); raise SystemExit(0 if v.get("worker_capabilities")=="lease-v1" else 1)'"'"''       >/dev/null 2>&1; then
    CAP_TTL=$((CHILD_TIMEOUT + 300))
    [ "$CAP_TTL" -gt 7500 ] && CAP_TTL=7500
    [ "$CAP_TTL" -lt 60 ] && CAP_TTL=60
    GLM_CAP_LOCAL="$(mktemp "${TMPDIR:-/tmp}/glm_remote_capability.XXXXXX")" || {
      RC=78; log "GLM_CAPABILITY_LOCAL_TEMP_FAILED"; exit "$RC";
    }
    TEMP_FILES+=("$GLM_CAP_LOCAL")
    chmod 600 "$GLM_CAP_LOCAL" || {
      RC=78; log "GLM_CAPABILITY_LOCAL_MODE_FAILED"; exit "$RC";
    }
    "$REMOTE_SUB_PYTHON" "$HERE/glm_remote_capability.py"       --lease-id "$LEASE_ID" --root "$ORCH_ID" --account "$POOL_ACCOUNT"       --model "$MODEL" --run-id "$ID" --host "$HOST_ARG" --ttl "$CAP_TTL"       --out "$GLM_CAP_LOCAL" >/dev/null || {
        RC=78; log "GLM_CAPABILITY_ISSUE_REFUSED"; exit "$RC";
      }
    GLM_CAP_REMOTE="lanes/tmp/${ID}.glm-cap.json"
    GLM_CAP_SHA=$("$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" glm-cap-sha "$GLM_CAP_LOCAL"
    ) || { RC=78; log "GLM_CAPABILITY_HASH_FAILED"; exit "$RC"; }
    GLM_CAP_TRANSFER_RC=0
    "$SSH_CMD" -T -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS"       "set -eu; d=\"\$HOME/lanes/tmp\"; t=\"\$d/${ID}.glm-cap.json\"; [ -d \"\$d\" ] && [ ! -L \"\$d\" ]; [ ! -e \"\$t\" ] && [ ! -L \"\$t\" ]; umask 077; x=\$(mktemp \"\$d/${ID}.glm-cap.tmp.XXXXXX\"); trap 'rm -f \"\$x\"' EXIT HUP INT TERM; cat > \"\$x\"; chmod 600 \"\$x\"; n=\$(wc -c < \"\$x\" | tr -d ' '); [ \"\$n\" -ge 1 ] && [ \"\$n\" -le 16384 ]; mv \"\$x\" \"\$t\"; trap - EXIT HUP INT TERM"       < "$GLM_CAP_LOCAL" || GLM_CAP_TRANSFER_RC=$?
    GLM_CAP_REMOTE_META=$("$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=8 "$SSH_ALIAS"       "python3 - \"\$HOME/lanes/tmp/${ID}.glm-cap.json\" <<'PY_GLM_REMOTE_META'
import hashlib, os, stat, sys
p=sys.argv[1]
s=os.lstat(p)
assert stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode)
assert stat.S_IMODE(s.st_mode)==0o600 and 1 <= s.st_size <= 16384
with open(p,'rb') as fh: data=fh.read()
print(hashlib.sha256(data).hexdigest())
PY_GLM_REMOTE_META
" 2>/dev/null || true)
    if [ "$GLM_CAP_REMOTE_META" != "$GLM_CAP_SHA" ]; then
      RC=78
      log "GLM_CAPABILITY_TRANSFER_UNPROVEN rc=$GLM_CAP_TRANSFER_RC"
      exit "$RC"
    fi
    log "GLM_CAPABILITY_READY lease=$LEASE_ID ttl=$CAP_TTL transport=ssh-stdin"
  elif "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=8 "$SSH_ALIAS"       'curl -fsS --max-time 3 http://127.0.0.1:4141/health >/dev/null && { { test -s "$HOME/.glm/config.json" && test -s "$HOME/lanes/ext/glm_shim/.token"; } || test -s "$HOME/lanes/ext/.host_glm_token.sh"; }'       >/dev/null 2>&1; then
    log "GLM_LEGACY_LOCAL_CREDENTIAL host=$HOST_ARG"
  else
    RC=78
    log "GLM_REMOTE_AUTH_UNAVAILABLE host=$HOST_ARG"
    exit "$RC"
  fi
fi

# A separate bounded operator capability travels only through the existing
# controller transport. It is never the provider credential or the parent lease.
if [ "$OPERATOR_CHILD_BUDGET" != "0" ]; then
  OPERATOR_CAP_LOCAL=$(mktemp "${TMPDIR:-/tmp}/fabric_operator_cap.XXXXXX") || exit 78
  TEMP_FILES+=("$OPERATOR_CAP_LOCAL")
  chmod 600 "$OPERATOR_CAP_LOCAL" || exit 78
  "$REMOTE_SUB_PYTHON" "$HERE/fabric_operator_issue.py" issue \
    --packet "$PACKET" --run-id "$ID" --pool "$ACQUIRE_POOL" --model "$MODEL" \
    --root "$ORCH_ID" --lease-id "$LEASE_ID" --account "$POOL_ACCOUNT" \
    --host "$HOST_ARG" --support-sha256 "$SUPPORT_DIGEST" \
    --child-budget "$OPERATOR_CHILD_BUDGET" --out "$OPERATOR_CAP_LOCAL" || {
      RC=78; log "OPERATOR_CAPABILITY_ISSUE_REFUSED rc=$RC"; exit "$RC";
    }
  OPERATOR_CAP_REMOTE="lanes/tmp/${ID}.operator-cap.json"
  OPERATOR_CAP_SHA=$("$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" glm-cap-sha "$OPERATOR_CAP_LOCAL") || exit 78
  OPERATOR_CAP_READBACK=$("$SSH_CMD" -T -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
    "python3 \"\$HOME/lanes/support-releases/$SUPPORT_DIGEST/ext/fabric_operator_client.py\" receive '$ID'" \
    < "$OPERATOR_CAP_LOCAL") || { RC=78; log "OPERATOR_CAPABILITY_TRANSFER_UNVERIFIED"; exit "$RC"; }
  [ "$OPERATOR_CAP_READBACK" = "$OPERATOR_CAP_SHA" ] || { RC=78; log "OPERATOR_CAPABILITY_DIGEST_UNVERIFIED"; exit "$RC"; }
  OPERATOR_ENV="FABRIC_OPERATOR_CAPSULE='$OPERATOR_CAP_REMOTE'"
  log "OPERATOR_CAPABILITY_READY child_budget=$OPERATOR_CHILD_BUDGET transport=private-stdin"
fi

# MODE/PACKET/CWD/MODEL are quoted for the remote shell; values never expand
# on the seat, and the packet is read only inside that remote shell.
if [ -n "${FABRIC_OPERATOR_CHILD_ID:-}" ]; then
  "$REMOTE_SUB_PYTHON" "$HERE/fabric_operator_issue.py" child-start --packet "$PACKET" \
    --run-id "$ID" --root "$ORCH_ID" --lease-id "$LEASE_ID" \
    --pool "$ACQUIRE_POOL" --model "$MODEL" --account "$POOL_ACCOUNT" --host "$HOST_ARG" || {
      RC=78; log "OPERATOR_CHILD_START_REFUSED"; exit "$RC";
    }
fi
ACCOUNT_ARG=${POOL_ACCOUNT:-}
# Quote each value for the remote shell; never evaluate metadata locally.
# Root/parent/class are correlation; the optional context ceiling is a caller-supplied bound. Neither grants authority.
# Preserve the exact broker-acquired root even if it was local shell state.
# The remote child must not substitute an unset inherited environment value.
ROUTING_ROOT="${ORCH_ID:-${POOL_ORCHESTRATOR_ID:-${CLAUDE_SESSION_ID:-remote-sub-$ID}}}"
ROUTING_ENV=$(POOL_ORCHESTRATOR_ID="$ROUTING_ROOT" "$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" routing-env
) || { log "ROUTING_METADATA_ENCODING_FAILED"; RC=78; exit "$RC"; }
NATIVE_LEASE_ISSUED=""
NATIVE_LEASE_DEADLINE=""
if [ "$NATIVE_MODE" -eq 1 ]; then
  NATIVE_WINDOW=$("$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" native-window "$HERE" "$LEASE_ID" "$ORCH_ID" "$POOL_ACCOUNT" "$HOST_ARG" "$CHILD_TIMEOUT" "$ACQUIRE_POOL"
  ) || { RC=78; log "NATIVE_LEASE_WINDOW_REFUSED"; exit "$RC"; }
  read -r NATIVE_LEASE_ISSUED NATIVE_LEASE_DEADLINE <<< "$NATIVE_WINDOW"
  log "NATIVE_WINDOW issued=$NATIVE_LEASE_ISSUED deadline=$NATIVE_LEASE_DEADLINE support=$SUPPORT_DIGEST"
fi
# Numeric timing only. No new Python startup or SSH roundtrip before admission.
# These observations never grant freshness, admission, retry or settlement.
NATIVE_TIMING_PREFIX=""
NATIVE_TIMING_AFTER_ENV=""
NATIVE_TIMING_ENV=""
if [ "$NATIVE_MODE" -eq 1 ]; then
  NATIVE_TIMING_PREFIX='NATIVE_REMOTE_SHELL_ENTERED=$(date -u +%s);'
  NATIVE_TIMING_AFTER_ENV='NATIVE_REMOTE_ENV_READY=$(date -u +%s);'
  NATIVE_TIMING_ENV='NATIVE_REMOTE_SHELL_ENTERED="$NATIVE_REMOTE_SHELL_ENTERED" NATIVE_REMOTE_ENV_READY="$NATIVE_REMOTE_ENV_READY"'
  REMOTE_INNER='export NATIVE_REMOTE_PYTHON_INVOKED=$(date -u +%s); '"$REMOTE_INNER"
fi
if [ -n "$GLM_CAP_REMOTE" ]; then
  REMOTE_INNER='export GLM_REMOTE_CAPABILITY_FILE="$HOME/lanes/tmp/$KEY.glm-cap.json"; '"$REMOTE_INNER"
fi
# New opt-in runs alone: persist exact controller/lease/source identity before
# the first provider launch. Collection bypasses this whole controller above.
if [ -n "${FABRIC_COMPLETION_CONTEXT:-}" ]; then
  [ "$DRY_RUN" -eq 0 ] && [ "$REMOTE_CWD" = '~' ] && [ "$HOST_ARG" != m2 ] || { RC=78; exit "$RC"; }
  case "$MODE" in glm|qwen|minimax) ;; *) RC=78; exit "$RC";; esac
  COMPLETION_FILE=$("$REMOTE_SUB_PYTHON" "$HERE/original_delivery_collector.py" "$ID" \
    --root "$ROUTING_ROOT" --parent "${POOL_PARENT_RUN_ID:-}" --seal-completion \
    "$FABRIC_COMPLETION_CONTEXT" "$ID" "$ROUTING_ROOT" "${POOL_PARENT_RUN_ID:-}" \
    "$HOST_ARG" "$MODE" "$MODEL" "$ACCOUNT_ARG" "$LEASE_ID" "$SUPPORT_DIGEST" \
    "$MAX_SECS" "$CHILD_TIMEOUT" "$PROVIDER_LEASE_TTL" \
    "${FABRIC_COMPLETION_CONTROLLER_PID:-}" "${FABRIC_COMPLETION_CUSTODY_FD:-}") || {
      RC=78; log 'COMPLETION_BINDING_REFUSED'; exit "$RC";
    }
  # Existing upload transport, inside this run's newly created support directory.
  "$SCP_CMD" -q "$COMPLETION_FILE" "$SSH_ALIAS:$REMOTE_SUPPORT_SOURCE/completion.json" || {
    RC=78; log 'COMPLETION_TRANSFER_UNCONFIRMED'; exit "$RC";
  }
  REMOTE_INNER='export FABRIC_COMPLETION_BINDING="$HOME/lanes/tmp/$KEY.support-src/completion.json"; '"$REMOTE_INNER"
fi
log "LAUNCH stdout=$REMOTE_STDOUT rc_file=ext/$REMOTE_RC cwd=$REMOTE_CWD"
LAUNCH_REMOTE="$NATIVE_TIMING_PREFIX $RPATH; $HOST_ENV; $NATIVE_TIMING_AFTER_ENV umask 077 || exit; cd ~/lanes/ext || exit; rm -f \"$REMOTE_STDOUT\" \"$REMOTE_RC\" || exit; KEY='$ID' MODE='$MODE' PACKET=\"\$HOME/lanes/tmp/${ID}.txt\" REMOTE_CWD='$REMOTE_CWD' MODEL='$MODEL' RC_FILE=\"\$HOME/lanes/ext/$REMOTE_RC\" nohup env $NATIVE_TIMING_ENV $ROUTING_ENV $OPERATOR_ENV SUPPORT_DIGEST='$SUPPORT_DIGEST' PYTHONDONTWRITEBYTECODE=1 LANE_LEASED=1 POOL_ACCOUNT='$ACCOUNT_ARG' POOL_LEASE_ID='$LEASE_ID' REMOTE_SUB_RUN_ID='$ID' LANE_REMOTE_HOST='$HOST_ARG' NATIVE_LEASE_ISSUED='$NATIVE_LEASE_ISSUED' NATIVE_LEASE_DEADLINE='$NATIVE_LEASE_DEADLINE' LANE_MAX_ACTIVE='$MAX_ACTIVE' LANE_MIN_FREE_MEM_GB='$MIN_FREE_MEM_GB' LANE_MAX_CPU_TCTL_C='$MAX_CPU_TCTL_C' LANE_MIN_FREE_DISK_GB='$MIN_FREE_DISK_GB' LANE_MAX_LOAD_RATIO='$LANE_HOST_LOAD_RATIO' LANE_NICE=10 REMOTE_SUB_CHILD_TIMEOUT='$CHILD_TIMEOUT' bash -c '$REMOTE_INNER' </dev/null > \"$REMOTE_STDOUT\" 2>&1 &"
ADMISSION_FILE="$HERE/lanes/${ID}.admission"
if [ "$DRY_RUN" -ne 1 ]; then SCRATCH_PATHS+=("$ADMISSION_FILE"); fi
ADMISSION_WAIT_STARTED_SECONDS=""
launch_attempt=0

while true; do
  launch_attempt=$((launch_attempt + 1))
  log "LAUNCH_ATTEMPT attempt=$launch_attempt"
  # From this point the remote launch may have taken effect even if the SSH reply is lost.
  # Keep provider custody until the exact run reaches a reconciled terminal observation.
  PRESERVE_LEASE=1
  LAUNCH_RC=0
  if [ "$NATIVE_MODE" -eq 1 ]; then log "NATIVE_SSH_ENTER epoch_s=$(date -u +%s)"; fi
  "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" "$LAUNCH_REMOTE" || LAUNCH_RC=$?
  if [ "$NATIVE_MODE" -eq 1 ]; then log "NATIVE_SSH_RETURN epoch_s=$(date -u +%s) rc=$LAUNCH_RC"; fi
  if [ "$LAUNCH_RC" -ne 0 ]; then
    RC=$LAUNCH_RC
    log "LAUNCH_FAILED rc=$RC"
    exit "$RC"
  fi

  WAIT_STARTED_SECONDS=$SECONDS
  RC=""
  poll_count=0
  while [ $((SECONDS - WAIT_STARTED_SECONDS)) -lt "$MAX_SECS" ]; do
    if [ -n "$LEASE_ID" ]; then
      broker heartbeat "$LEASE_ID" >/dev/null 2>&1 || true
    fi
    poll_count=$((poll_count + 1))
    elapsed=$((SECONDS - WAIT_STARTED_SECONDS))
    log "POLL $poll_count/$MAX_SECS elapsed=$elapsed file=~/lanes/ext/$REMOTE_RC"
    poll_rc=0
    "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
          "if [ -f \"\$HOME/lanes/ext/$REMOTE_RC\" ]; then cat \"\$HOME/lanes/ext/$REMOTE_RC\"; else printf '%s\n' '__REMOTE_SUB_PENDING__'; fi" > "$POLL_FILE" || poll_rc=$?
    if [ "$poll_rc" -eq 0 ]; then
      POLL_VALUE="$(cat "$POLL_FILE" 2>/dev/null || true)"
      if [[ "$POLL_VALUE" =~ ^[0-9]+$ ]]; then
        RC="$POLL_VALUE"
        log "RC value=$RC poll=$poll_count"
        break
      elif [ "$POLL_VALUE" = "__REMOTE_SUB_PENDING__" ]; then
        log "POLL_PENDING poll=$poll_count"
      else
        log "POLL_PROTOCOL_INVALID poll=$poll_count bytes=$(wc -c < "$POLL_FILE" 2>/dev/null || echo 0)"
      fi
    else
      log "POLL_TRANSPORT_FAILED rc=$poll_rc poll=$poll_count"
    fi
    elapsed=$((SECONDS - WAIT_STARTED_SECONDS))
    remaining=$((MAX_SECS - elapsed))
    [ "$remaining" -gt 0 ] || break
    sleep_for="$POLL_SECS"
    [ "$sleep_for" -le "$remaining" ] || sleep_for="$remaining"
    sleep "$sleep_for"
  done

  if [ -z "$RC" ]; then
    log "EFFECT_UNKNOWN timeout max_secs=$MAX_SECS rc_file_missing=1; preserve broker lease until TTL"
    PRESERVE_LEASE=1
    RC=124
    break
  fi

  RC_OBSERVED=1
  log "REMOTE_DONE rc=$RC"
  if [ "$RETRYABLE_ADMISSION_MODE" -eq 1 ] && [ "$RC" -eq 75 ] && [ "$ADMISSION_WAIT_SECS" -gt 0 ]; then
    admission_read_rc=0
    "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
      "if grep -Fq 'REMOTE_SUB_ADMISSION_REFUSED ' \"\$HOME/lanes/ext/$REMOTE_STDOUT\" 2>/dev/null && grep -Fq 'active_lane_limit_reached' \"\$HOME/lanes/ext/$REMOTE_STDOUT\" 2>/dev/null; then tail -c 4096 \"\$HOME/lanes/ext/$REMOTE_STDOUT\"; else exit 1; fi" \
      > "$ADMISSION_FILE" || admission_read_rc=$?
    if [ "$admission_read_rc" -eq 0 ] && grep -Fq "active_lane_limit_reached" "$ADMISSION_FILE" 2>/dev/null; then
      if [ -z "$ADMISSION_WAIT_STARTED_SECONDS" ]; then ADMISSION_WAIT_STARTED_SECONDS=$SECONDS; fi
      admission_elapsed=$((SECONDS - ADMISSION_WAIT_STARTED_SECONDS))
      admission_remaining=$((ADMISSION_WAIT_SECS - admission_elapsed))
      if [ "$admission_remaining" -gt 0 ]; then
        log "ADMISSION_BUSY active_lane_limit_reached wait_remaining=$admission_remaining attempt=$launch_attempt"
        if [ -n "$LEASE_ID" ]; then broker heartbeat "$LEASE_ID" >/dev/null 2>&1 || true; fi
        admission_sleep="$ADMISSION_RETRY_SECS"
        [ "$admission_sleep" -le "$admission_remaining" ] || admission_sleep="$admission_remaining"
        sleep "$admission_sleep"
        RC_OBSERVED=0
        log "ADMISSION_RETRY same_run=1 same_host=1 next_attempt=$((launch_attempt + 1))"
        continue
      fi
      log "ADMISSION_WAIT_EXHAUSTED wait_secs=$ADMISSION_WAIT_SECS attempts=$launch_attempt"
    fi
  fi
  break
done
WORKER_RC="$RC"

mkdir -p "$(dirname "$LOCAL_OUT")" 2>/dev/null || true
RSYNC_RC=0
log "RSYNC stdout=~/lanes/ext/$REMOTE_STDOUT out=$(basename "$LOCAL_OUT")"
"$RSYNC_CMD" -aq "$SSH_ALIAS:~/lanes/ext/$REMOTE_STDOUT" "$LOCAL_OUT" || RSYNC_RC=$?
if [ "$NATIVE_MODE" -eq 1 ]; then
  NATIVE_TERMINAL="$LOG_DIR/${ID}.native-terminal.json"
  if "$RSYNC_CMD" -aq "$SSH_ALIAS:~/lanes/ext/lanes/${ID}.native-terminal.json" "$NATIVE_TERMINAL" &&
     "$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" native-settle "$NATIVE_TERMINAL" "$HERE" "$ID" "$ORCH_ID" "$LEASE_ID" "$POOL_ACCOUNT" "$HOST_ARG" "$MODE" "$MODEL" "$RC"
  then PRESERVE_LEASE=0; log "NATIVE_SETTLED receipt=$(basename "$NATIVE_TERMINAL")"
  else PRESERVE_LEASE=1; log "NATIVE_EFFECT_UNKNOWN same_carrier_reconciliation_required=1"
  fi
fi

# Ordinary profiles have no separate native terminal receipt. Their remote RC
# file is written only after remote_sub_exec exits. That executor now returns
# 76 whenever cleanup is unproven, so a different observed RC is sufficient to
# release provider custody. RC 76 is released only for the explicit
# capture-truncated marker; otherwise it remains effect-unknown.
if [ "$NATIVE_MODE" -ne 1 ] && [ "$RC_OBSERVED" -eq 1 ]; then
  if [ "$RSYNC_RC" -eq 0 ]; then
    if [ "$WORKER_RC" -ne 76 ]; then
      PRESERVE_LEASE=0
    elif grep -q "REMOTE_CAPTURE_TRUNCATED" "$LOCAL_OUT" 2>/dev/null; then
      PRESERVE_LEASE=0
      RESULT_FAILURE_REASON=remote_capture_truncated
    else
      PRESERVE_LEASE=1
      log "REMOTE_EFFECT_UNKNOWN worker_rc=76 same_run_reconciliation_required=1"
    fi
  elif [ "$WORKER_RC" -ne 76 ]; then
    # The child is terminal and cleanup-proven; only result delivery failed.
    PRESERVE_LEASE=0
  fi
fi

if [ "$RSYNC_RC" -ne 0 ]; then
  log "RSYNC_FAILED rc=$RSYNC_RC (remote rc=$WORKER_RC); remote artifacts preserved"
  RESULT_FAILURE_REASON=result_unavailable
  log "RESULT_UNAVAILABLE worker_rc=$WORKER_RC rsync_rc=$RSYNC_RC"
  RC=76
elif [ "$PRESERVE_LEASE" = "1" ]; then
  log "REMOTE_ARTIFACTS_PRESERVED effect_unknown=1"
else
  LOCAL_PROCESS_RECEIPT="$LOG_DIR/${ID}.process.jsonl"
  LOCAL_USAGE_RECEIPT="$LOG_DIR/${ID}.usage.json"
  VALIDATED_USAGE_FILE="$LOG_DIR/${ID}.usage.validated"
  RECEIPT_SAVED=0
  USAGE_SAVED=0
  if "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
      "test -f \"\$HOME/lanes/ext/lanes/${ID}.process.jsonl\"" >/dev/null 2>&1; then
    if "$RSYNC_CMD" -aq "$SSH_ALIAS:~/lanes/ext/lanes/${ID}.process.jsonl" "$LOCAL_PROCESS_RECEIPT"; then
      RECEIPT_SAVED=1
      log "PROCESS_RECEIPT_SAVED file=$(basename "$LOCAL_PROCESS_RECEIPT")"
    else
      log "PROCESS_RECEIPT_RSYNC_FAILED; remote receipt preserved"
    fi
  fi
  if "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
      "test -f \"\$HOME/lanes/ext/lanes/${ID}.usage.json\"" >/dev/null 2>&1; then
    if "$RSYNC_CMD" -aq "$SSH_ALIAS:~/lanes/ext/lanes/${ID}.usage.json" "$LOCAL_USAGE_RECEIPT"; then
      USAGE_SAVED=1
      log "USAGE_RECEIPT_SAVED file=$(basename "$LOCAL_USAGE_RECEIPT")"
    else
      log "USAGE_RECEIPT_RSYNC_FAILED; remote usage preserved"
    fi
  else
    log "USAGE_RECEIPT_MISSING"
  fi
  USAGE_TOKEN_ARGS=()
  if [ "$USAGE_SAVED" -eq 1 ]; then
    if "$REMOTE_SUB_PYTHON" "$HERE/remote_sub_helpers.py" validate-usage "$LOCAL_USAGE_RECEIPT" "$ID" > "$VALIDATED_USAGE_FILE"
    then
      {
        read -r usage_input
        read -r usage_cached
        read -r usage_output
        read -r usage_total
        read -r usage_source
        read -r native_compactions
      } < "$VALIDATED_USAGE_FILE"
      case "$native_compactions" in
        legacy) ;;
        unknown) log "CODEX_COMPACTION_UNKNOWN reason=malformed_count" ;;
        ''|*[!0-9]*) log "CODEX_COMPACTION_UNKNOWN reason=invalid_observation" ;;
        *) log "CODEX_COMPACTION_OBSERVED native_records=$native_compactions" ;;
      esac
      USAGE_TOKEN_ARGS+=(--input-tokens "$usage_input" --cached-tokens "$usage_cached"
        --output-tokens "$usage_output" --usage-source "$usage_source")
      USAGE_VALID=1
      log "USAGE_VALIDATED total_tokens=$usage_total"
    else
      log "USAGE_VALIDATION_FAILED tokens_unknown=1"
    fi
  fi
  CLEAN_RECEIPT=''
  [ "$RECEIPT_SAVED" -eq 1 ] && CLEAN_RECEIPT=" \"\$HOME/lanes/ext/lanes/${ID}.process.jsonl\""
  CLEAN_USAGE=''
  [ "$USAGE_SAVED" -eq 1 ] && CLEAN_USAGE=" \"\$HOME/lanes/ext/lanes/${ID}.usage.json\""
  if "$SSH_CMD" -o BatchMode=yes -o ConnectTimeout=15 "$SSH_ALIAS" \
      "rm -f \"\$HOME/lanes/tmp/${ID}.txt\" \"\$HOME/lanes/ext/$REMOTE_RC\" \"\$HOME/lanes/ext/$REMOTE_STDOUT\"$CLEAN_RECEIPT$CLEAN_USAGE && rm -rf -- \"\$HOME/lanes/tmp/${ID}.support-src\""; then
    log "REMOTE_CLEANED transport=1 receipt_saved=$RECEIPT_SAVED usage_saved=$USAGE_SAVED"
  else
    log "REMOTE_CLEANUP_FAILED; completed work remains reconciled"
  fi
fi

fi # Existing remote transport, or scoped Go foreground transport.

# Verify an explicitly requested output token only after confirmed successful
# execution and cleanup. Failure is semantic (79), NOT missing transport or an
# uncertain effect. No duplicate worker launch or key rotation is authorized.
# Never override a nonzero worker rc or an unproven lease/cleanup state.
if [ "$EXPECT_OUTPUT_SPECIFIED" -eq 1 ] &&
   [ "$RC" -eq 0 ] && [ "$PRESERVE_LEASE" != "1" ]; then
  if ! [ -f "$LOCAL_OUT" ] || [ -L "$LOCAL_OUT" ] ||
     ! grep -Fqx -- "$EXPECT_OUTPUT_TOKEN" "$LOCAL_OUT"; then
    RESULT_FAILURE_REASON=output_contract_missing
    RC=79
    log "OUTPUT_CONTRACT_MISSING rc=79 worker_rc=0 effects_already_settled=1"
  else
    log "OUTPUT_CONTRACT_MATCHED"
  fi
fi

case "$MODE" in
  minimax|minimax-codex) LEDGER_POOL=minimax ;;
  cursor) LEDGER_POOL=cursor ;;
esac
# Remote rc=0 proves only worker exit, not a settled native terminal receipt.
# Never publish or return success when cleanup/custody remains effect-unknown.
if [ "$PRESERVE_LEASE" = "1" ] && [ "$RC" -eq 0 ]; then
  RC=76
  log "EFFECT_UNKNOWN_NONZERO controller_rc=76 worker_rc=$WORKER_RC settlement=unproven"
fi
LEDGER_SIGNAL=ok
LEDGER_REASON=""
if [ "$PRESERVE_LEASE" = "1" ]; then
  LEDGER_SIGNAL=effect_unknown
  if [ "$MODE" = go-codex ]; then LEDGER_REASON=go_settlement_unproven
  elif [ "$RC_OBSERVED" -eq 1 ]; then LEDGER_REASON=remote_cleanup_unproven
  else LEDGER_REASON=transport_deadline_without_rc; fi
elif [ -n "$RESULT_FAILURE_REASON" ]; then
  LEDGER_SIGNAL=other
  LEDGER_REASON="$RESULT_FAILURE_REASON"
elif [ "$RC" -eq 75 ]; then
  LEDGER_SIGNAL=admission
  LEDGER_REASON=remote_admission_refused
elif [ "$RC" -eq 77 ]; then
  # Proven wrapper-level failure: the worker stayed alive through its bounded
  # continuation budget but never emitted the required terminal status. Keep
  # this distinct from rc76, which is reserved for lease/cleanup uncertainty.
  LEDGER_SIGNAL=other
  LEDGER_REASON=terminal_status_missing
elif [ "$RC" -eq 76 ]; then
  LEDGER_SIGNAL=lease_lost
  LEDGER_REASON=remote_lease_lost
  if [ "$NATIVE_MODE" -eq 1 ]; then LEDGER_SIGNAL=other; LEDGER_REASON=native_capture_truncated; fi
elif [ "$RC" -eq 124 ]; then
  LEDGER_SIGNAL=timeout
  LEDGER_REASON=owned_child_timeout
elif [ "$RC" -ne 0 ]; then
  LEDGER_SIGNAL=other
  LEDGER_REASON=remote_nonzero
fi
LEDGER_ARGS=(append --pool "$LEDGER_POOL" --task-class "remote-$MODE" --rc "$RC" --signal "$LEDGER_SIGNAL"
  --run-id "$ID" --wall-s "$((SECONDS - RUN_STARTED_SECONDS))")
# MODEL is the explicit request, not an attestation of the served model.
# Missing metadata stays unknown; never infer tokens or acceptance from rc0.
[ -n "$MODEL" ] && LEDGER_ARGS+=(--model "$MODEL")
[ -n "${POOL_TASK_CLASS:-}" ] && LEDGER_ARGS+=(--job-class "$POOL_TASK_CLASS")
[ -n "${POOL_ORCHESTRATOR_ID:-}" ] && LEDGER_ARGS+=(--root-id "$POOL_ORCHESTRATOR_ID")
[ -n "${POOL_PARENT_RUN_ID:-}" ] && LEDGER_ARGS+=(--parent-run-id "$POOL_PARENT_RUN_ID")
[ -n "${POOL_ESCALATION_REASON:-}" ] && LEDGER_ARGS+=(--escalation-reason "$POOL_ESCALATION_REASON")
[ -n "$LEDGER_REASON" ] && LEDGER_ARGS+=(--reason "$LEDGER_REASON")
if [ "$USAGE_VALID" -eq 1 ]; then
  LEDGER_ARGS+=("${USAGE_TOKEN_ARGS[@]}" --tokens "$usage_total")
fi
# Worker settlement and durable terminal publication are separate facts. Do
# not advertise DONE if the canonical ledger did not acknowledge persistence.
if ! ledger "${LEDGER_ARGS[@]}" --strict >/dev/null 2>&1; then
  log "TERMINAL_PUBLICATION_FAILED worker_rc=$RC signal=$LEDGER_SIGNAL recovery_required=1"
  [ -z "$VALIDATED_USAGE_FILE" ] || rm -f "$VALIDATED_USAGE_FILE" 2>/dev/null || true
  RC=74
  exit "$RC"
fi
[ -z "$VALIDATED_USAGE_FILE" ] || rm -f "$VALIDATED_USAGE_FILE" 2>/dev/null || true
log "DONE rc=$RC signal=$LEDGER_SIGNAL${LEDGER_REASON:+ reason=$LEDGER_REASON}"
exit "$RC"
