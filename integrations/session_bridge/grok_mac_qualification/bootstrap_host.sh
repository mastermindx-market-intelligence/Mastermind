#!/bin/bash
# Sudoless lane-host bootstrap. Full mode installs pinned CLI tools and mirrors ext/.
# --runtime-only preserves already-installed CLIs and prepares only the non-secret lane runtime.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOSTS_JSON="${BOOTSTRAP_HOSTS_JSON:-$HERE/hosts.json}"
STATE_DIR="${BOOTSTRAP_STATE_DIR:-$HERE/state/hosts}"
CODEX_VERSION="0.160.1"
CLAUDE_VERSION="2.1.259"
# Static pins below make the requested package contract inspectable.
PINNED_CODEX_PACKAGE='@openai/codex@0.160.1'
PINNED_CLAUDE_PACKAGE='@anthropic-ai/claude-code@2.1.259'
RPATH='export PATH=$HOME/.npm-global/bin:$HOME/.local/bin:/opt/homebrew/bin:$HOME/lanes/venv/bin:$PATH'
HEALTH_URL='http://127.0.0.1:4141/health'

usage() {
  echo "usage: bash $(basename "$0") <host> [--dry-run] [--verify-only] [--runtime-only]" >&2
  echo "       <ubuntu3> --repair-original-b-lanes-mode (one fixed original-B maintenance operation)" >&2
  echo "       <ubuntu3> --reconcile-original-b-hostname (one exact recorded pre-effect refusal)" >&2
  echo "       The host argument must be first." >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
HOST_KEY="${1:-}"
shift || true
DRY_RUN=0
VERIFY_ONLY=0
RUNTIME_ONLY=0
ORIGINAL_B_MODE_REPAIR=0
ORIGINAL_B_HOST_RECONCILE=0
ORIGINAL_B_SHARING=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --verify-only) VERIFY_ONLY=1 ;;
    --runtime-only) RUNTIME_ONLY=1 ;;
    --repair-original-b-lanes-mode) ORIGINAL_B_MODE_REPAIR=$((ORIGINAL_B_MODE_REPAIR + 1)) ;;
    --reconcile-original-b-hostname) ORIGINAL_B_HOST_RECONCILE=$((ORIGINAL_B_HOST_RECONCILE + 1)) ;;
    --qualify-original-b-sharing) ORIGINAL_B_SHARING=$((ORIGINAL_B_SHARING + 1)) ;;
    *) usage ;;
  esac
done
case "$HOST_KEY" in
  ''|*[!A-Za-z0-9_.:-]*) usage ;;
esac

json_field() {
  python3 -c '
import json, sys
try:
    db = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit(3)
entry = db.get(sys.argv[2])
if not isinstance(entry, dict):
    raise SystemExit(4)
value = entry.get(sys.argv[3])
if not isinstance(value, str) or not value:
    raise SystemExit(4)
print(value)
' "$HOSTS_JSON" "$HOST_KEY" "$1"
}

json_number_field() {
  python3 -c '
import json, sys
try:
    db = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit(3)
entry = db.get(sys.argv[2])
if not isinstance(entry, dict):
    raise SystemExit(4)
value = entry.get(sys.argv[3])
if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
    raise SystemExit(4)
print(value)
' "$HOSTS_JSON" "$HOST_KEY" "$1"
}

SSH_ALIAS="$(json_field ssh_alias)" || {
  echo "bootstrap_host: no ssh_alias for host=$HOST_KEY" >&2
  exit 4
}
MIN_FREE_GB="$(json_number_field min_free_gb)" || MIN_FREE_GB="6"
case "$MIN_FREE_GB" in
  ''|*[!0-9.]*) MIN_FREE_GB="6" ;;
esac

if [ -n "${BOOTSTRAP_SSH_CMD:-}" ]; then
  SSH_REMOTE=("$BOOTSTRAP_SSH_CMD")
else
  SSH_REMOTE=(perl -e 'alarm 30; exec @ARGV' ssh -o BatchMode=yes -o ConnectTimeout=8)
fi
if [ -n "${BOOTSTRAP_RSYNC_CMD:-}" ]; then
  RSYNC_CMD="$BOOTSTRAP_RSYNC_CMD"
else
  RSYNC_CMD=rsync
fi
if [ -n "${BOOTSTRAP_RSYNC_SSH:-}" ]; then
  RSYNC_SSH="$BOOTSTRAP_RSYNC_SSH"
else
  RSYNC_SSH="perl -e 'alarm 30; exec @ARGV' ssh -o BatchMode=yes -o ConnectTimeout=8"
fi

# This fixed maintenance branch precedes every normal bootstrap effect.
if [ "$ORIGINAL_B_MODE_REPAIR" -ne 0 ] || [ "$ORIGINAL_B_HOST_RECONCILE" -ne 0 ] || [ "$ORIGINAL_B_SHARING" -ne 0 ]; then
  [ "$((ORIGINAL_B_MODE_REPAIR + ORIGINAL_B_HOST_RECONCILE + ORIGINAL_B_SHARING))" -eq 1 ] && [ "$HOST_KEY" = "ubuntu3" ] \
    && [ "$DRY_RUN" -eq 0 ] && [ "$VERIFY_ONLY" -eq 0 ] && [ "$RUNTIME_ONLY" -eq 0 ] || usage
  if [ "$ORIGINAL_B_SHARING" -eq 1 ]; then
    exec python3 "$HERE/bootstrap_original_b_mode.py" --state-dir "$STATE_DIR" --qualify-sharing \
      -- "${SSH_REMOTE[@]}" "$SSH_ALIAS" python3 - --remote-sharing
  fi
  if [ "$ORIGINAL_B_HOST_RECONCILE" -eq 1 ]; then
    exec python3 "$HERE/bootstrap_original_b_mode.py" --state-dir "$STATE_DIR" --reconcile-hostname \
      -- "${SSH_REMOTE[@]}" "$SSH_ALIAS" python3 - --remote
  fi
  exec python3 "$HERE/bootstrap_original_b_mode.py" --state-dir "$STATE_DIR" \
    -- "${SSH_REMOTE[@]}" "$SSH_ALIAS" python3 - --remote
fi

STEPS_FILE="$(mktemp "${TMPDIR:-/tmp}/bootstrap_steps.XXXXXX")"
cleanup() { rm -f "$STEPS_FILE"; }
trap cleanup EXIT INT TERM HUP
mark() {
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$STEPS_FILE"
}

mkdir_SCRIPT='mkdir -p "$HOME/lanes/ext" "$HOME/lanes/tmp" "$HOME/lanes/wt" "$HOME/lanes/nm_cache" "$HOME/lanes/ext/lanes" "$HOME/lanes/ext/active"'
OCCUPANCY_INIT_SCRIPT='RPATH_PLACEHOLDER
python3 - <<'"'"'PY'"'"'
import os
from pathlib import Path
import stat

active = Path.home() / "lanes" / "ext" / "active"
lock = active / ".admission.lock"
flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(lock, flags, 0o600)
try:
    opened = os.fstat(fd)
    visible = os.lstat(lock)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or opened.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) != 0o600
        or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
    ):
        raise SystemExit("occupancy_lock_invalid")
finally:
    os.close(fd)
print("occupancy_lock=ready")
PY'
OCCUPANCY_INIT_SCRIPT="${OCCUPANCY_INIT_SCRIPT//RPATH_PLACEHOLDER/$RPATH}"
TOOLS_SCRIPT="RPATH_PLACEHOLDER
npm config set prefix \"\$HOME/.npm-global\"
npm config set ignore-scripts false
npm config set allow-scripts=@anthropic-ai/claude-code
npm config set omit \"\"
export npm_config_include=optional
export npm_config_foreground_scripts=true
if ! codex --version 2>/dev/null | grep -q 'CODEX_VERSION_PLACEHOLDER'; then
  npm install -g @openai/codex@CODEX_VERSION_PLACEHOLDER > \"\$HOME/lanes/tmp/bootstrap-codex.stdout\" 2>&1
fi
if ! claude --version 2>/dev/null | grep -q 'CLAUDE_VERSION_PLACEHOLDER'; then
  npm install -g @anthropic-ai/claude-code@CLAUDE_VERSION_PLACEHOLDER > \"\$HOME/lanes/tmp/bootstrap-claude.stdout\" 2>&1
fi
"
TOOLS_SCRIPT="${TOOLS_SCRIPT//RPATH_PLACEHOLDER/$RPATH}"
TOOLS_SCRIPT="${TOOLS_SCRIPT//CODEX_VERSION_PLACEHOLDER/$CODEX_VERSION}"
TOOLS_SCRIPT="${TOOLS_SCRIPT//CLAUDE_VERSION_PLACEHOLDER/$CLAUDE_VERSION}"

RSYNC_EXCLUDES=(
  --exclude='state/'
  --exclude='broker/leases.sqlite*'
  --exclude='broker/leases.lock'
  --exclude='glm_shim/usage.jsonl'
  --exclude='glm_shim/shim.*'
  --exclude='glm_shim/.token'
  --exclude='go_shim/.token'
  --exclude='.host_glm_token.sh'
  --exclude='*.log'
  --exclude='*.stdout'
  --exclude='*.pid'
  --exclude='lanes/'
  --exclude='active/'
  --exclude='__pycache__/'
  --exclude='codex_*/auth.json'
  --exclude='codex_*/sessions/'
  --exclude='*_pid.txt'
)
ENV_SCRIPT="mkdir -p \"\$HOME/lanes/ext\"
TOKEN_FILE=\"\$HOME/lanes/ext/glm_shim/.token\"
if [ -f \"\$TOKEN_FILE\" ]; then
  printf 'export GLM_SHIM_TOKEN=\"%s\"\\n' \"\$(tr -d ' \\n\\r' < \"\$TOKEN_FILE\")\" > \"\$HOME/lanes/ext/.host_glm_token.sh\"
  chmod 600 \"\$HOME/lanes/ext/.host_glm_token.sh\"
fi
cat > \"\$HOME/lanes/ext/HOST_ENV.sh\" <<'HOST_ENV_EOF'
$RPATH
export GLM_SHIM_URL=http://127.0.0.1:4141
# Bind MiniMax admission to the *real* immutable source commit on Ubuntu.
# An absent checkout leaves the source gate closed; no fallback or bypass.
[ -d \"\$HOME/lanes/authority/mastermind-minimax-4d1f45bf600afc2d264a74852c69887084aa52ff/.git\" ] && export MINIMAX_GIT_OBJECT_ROOT=\"\$HOME/lanes/authority/mastermind-minimax-4d1f45bf600afc2d264a74852c69887084aa52ff\"
[ -f \"\$HOME/lanes/ext/.host_glm_token.sh\" ] && . \"\$HOME/lanes/ext/.host_glm_token.sh\"
HOST_ENV_EOF
chmod 755 \"\$HOME/lanes/ext/HOST_ENV.sh\"
"
RUNTIME_VERIFY_SCRIPT="$RPATH
codex_line=\$(codex --version 2>&1 | tail -1 || true)
claude_line=\$(claude --version 2>&1 | tail -1 || true)
node_line=\$(node --version 2>&1 | tail -1 || true)
python_ok=0
python3 -c 'import json' >/dev/null 2>&1 && python_ok=1
runtime_ok=0
if cd \"\$HOME/lanes/ext\" \
  && python3 -m py_compile host_pick.py lane_runtime.py remote_sub_exec.py >/dev/null 2>&1 \
  && python3 -c 'import host_pick, lane_runtime, remote_sub_exec' >/dev/null 2>&1 \
  && bash -n remote_sub.sh sub.sh >/dev/null 2>&1 \
  && test -f hosts.json; then
  runtime_ok=1
fi
disk_line=\$(df -Pk \"\$HOME/lanes\" 2>/dev/null | awk 'NR==2 {printf \"%.1f\", \$4/1048576}')
printf 'codex=%s\n' \"\$codex_line\"
printf 'claude=%s\n' \"\$claude_line\"
printf 'node=%s\n' \"\$node_line\"
printf 'python_ok=%s\n' \"\$python_ok\"
printf 'runtime_ok=%s\n' \"\$runtime_ok\"
printf 'macro=skipped\n'
printf 'disk_free_gb=%s\n' \"\$disk_line\"
printf 'tunnel=000\n'
"

VERIFY_SCRIPT="$RPATH
codex_line=\$(codex --version 2>&1 | tail -1 || true)
claude_line=\$(claude --version 2>&1 | tail -1 || true)
node_line=\$(node --version 2>&1 | tail -1 || true)
python_ok=0
python3 -c 'import json' >/dev/null 2>&1 && python_ok=1
macro_line=\$(git -C \"\$HOME/lanes/repos/macro\" rev-parse --is-inside-work-tree 2>&1 | tail -1 || true)
disk_line=\$(df -Pk \"\$HOME/lanes\" 2>/dev/null | awk 'NR==2 {printf \"%.1f\", \$4/1048576}')
tunnel_line=\$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:4141/health 2>/dev/null || true)
printf 'codex=%s\n' \"\$codex_line\"
printf 'claude=%s\n' \"\$claude_line\"
printf 'node=%s\n' \"\$node_line\"
printf 'python_ok=%s\n' \"\$python_ok\"
printf 'macro=%s\n' \"\$macro_line\"
printf 'disk_free_gb=%s\n' \"\$disk_line\"
printf 'tunnel=%s\n' \"\$tunnel_line\"
"

if [ "$DRY_RUN" -eq 1 ]; then
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    echo "DRY_RUN host=$HOST_KEY alias=$SSH_ALIAS RUNTIME_ONLY"
  else
    echo "DRY_RUN host=$HOST_KEY alias=$SSH_ALIAS"
  fi
  printf 'REMOTE mkdir: '
  printf '%q ' "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$mkdir_SCRIPT"
  echo
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    echo "REMOTE tools: SKIPPED runtime-only"
    echo "REMOTE mirror: $RSYNC_CMD -a ${RSYNC_EXCLUDES[*]} -e \"$RSYNC_SSH\" \"$HERE/\" \"$SSH_ALIAS:~/lanes/ext/\""
  else
    printf 'REMOTE tools: '
    printf '%q ' "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$TOOLS_SCRIPT"
    echo
    echo "REMOTE mirror: $RSYNC_CMD -a --delete ${RSYNC_EXCLUDES[*]} -e \"$RSYNC_SSH\" \"$HERE/\" \"$SSH_ALIAS:~/lanes/ext/\""
  fi
  printf 'REMOTE occupancy_lock: '
  printf '%q ' "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$OCCUPANCY_INIT_SCRIPT"
  echo
  printf 'REMOTE HOST_ENV: '
  printf '%q ' "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$ENV_SCRIPT"
  echo
  printf 'REMOTE verify: '
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    printf '%q ' "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$RUNTIME_VERIFY_SCRIPT"
  else
    printf '%q ' "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$VERIFY_SCRIPT"
  fi
  echo
  exit 0
fi

mkdir -p "$STATE_DIR"
run_remote() {
  local name="$1" script="$2"
  if "${SSH_REMOTE[@]}" "$SSH_ALIAS" "$script"; then
    mark "$name" ok ""
    return 0
  fi
  local rc=$?
  mark "$name" fail "remote command exited $rc"
  return "$rc"
}

write_receipt() {
  local exit_code="$1" codex="$2" claude="$3" node="$4" tunnel_ok="$5"
  local receipt="$STATE_DIR/$HOST_KEY.bootstrap.json"
  python3 - "$receipt" "$HOST_KEY" "$codex" "$claude" "$node" "$tunnel_ok" "$STEPS_FILE" <<'PY'
import json
import os
import sys
import datetime

path, host, codex, claude, node, tunnel_ok, steps_path = sys.argv[1:]
steps = []
with open(steps_path, encoding="utf-8") as handle:
    for line in handle:
        fields = line.rstrip("\n").split("\t", 2)
        if len(fields) != 3:
            continue
        name, status, detail = fields
        steps.append({"name": name, "status": status, "detail": detail[:500]})
receipt = {
    "host": host,
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "codex": codex,
    "claude": claude,
    "node": node,
    "tunnel_ok": tunnel_ok == "true",
    "steps": steps,
}
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as handle:
    json.dump(receipt, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
  echo "receipt=$receipt"
}

FAILED=0
if [ "$VERIFY_ONLY" -eq 0 ]; then
  run_remote directories "$mkdir_SCRIPT" || FAILED=1
  if [ "$FAILED" -eq 0 ]; then
    if [ "$RUNTIME_ONLY" -eq 1 ]; then
      mark tools skipped "runtime-only"
    else
      run_remote tools "$TOOLS_SCRIPT" || FAILED=1
    fi
  fi
  if [ "$FAILED" -eq 0 ]; then
    if [ "$RUNTIME_ONLY" -eq 1 ]; then
      MIRROR_DELETE=()
    else
      MIRROR_DELETE=(--delete)
    fi
    if "$RSYNC_CMD" -a "${MIRROR_DELETE[@]}" "${RSYNC_EXCLUDES[@]}" -e "$RSYNC_SSH" \
      "$HERE/" "$SSH_ALIAS:~/lanes/ext/"; then
      mark mirror ok ""
    else
      rc=$?
      mark mirror fail "rsync exited $rc"
      FAILED=1
    fi
  fi
  if [ "$FAILED" -eq 0 ]; then
    run_remote occupancy_lock "$OCCUPANCY_INIT_SCRIPT" || FAILED=1
  fi
  if [ "$FAILED" -eq 0 ]; then
    run_remote host_env "$ENV_SCRIPT" || FAILED=1
  fi
else
  mark directories skipped "verify-only"
  mark tools skipped "verify-only"
  mark mirror skipped "verify-only"
  mark occupancy_lock skipped "verify-only"
  mark host_env skipped "verify-only"
fi

CODEX_LINE=""
CLAUDE_LINE=""
NODE_LINE=""
TUNNEL_OK=false
PYTHON_OK=0
MACRO_LINE=""
RUNTIME_OK=0
DISK_FREE_GB=""
TUNNEL_CODE=""
if [ "$FAILED" -eq 0 ]; then
  VERIFY_OUTPUT=""
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    VERIFY_TO_RUN="$RUNTIME_VERIFY_SCRIPT"
  else
    VERIFY_TO_RUN="$VERIFY_SCRIPT"
  fi
  if VERIFY_OUTPUT="$("${SSH_REMOTE[@]}" "$SSH_ALIAS" "$VERIFY_TO_RUN" 2>&1)"; then
    mark remote_verify ok ""
  else
    rc=$?
    mark remote_verify fail "verify ssh exited $rc"
    VERIFY_ONLY_OUT="$VERIFY_OUTPUT"
    printf '%s\n' "$VERIFY_OUTPUT" | sed -n '1,20p' >&2
    write_receipt 1 "$CODEX_LINE" "$CLAUDE_LINE" "$NODE_LINE" false
    exit 1
  fi
  while IFS= read -r line; do
    case "$line" in
      codex=*) CODEX_LINE="${line#codex=}" ;;
      claude=*) CLAUDE_LINE="${line#claude=}" ;;
      node=*) NODE_LINE="${line#node=}" ;;
      python_ok=*) PYTHON_OK="${line#python_ok=}" ;;
      runtime_ok=*) RUNTIME_OK="${line#runtime_ok=}" ;;
      macro=*) MACRO_LINE="${line#macro=}" ;;
      disk_free_gb=*) DISK_FREE_GB="${line#disk_free_gb=}" ;;
      tunnel=*) TUNNEL_CODE="${line#tunnel=}" ;;
    esac
  done <<VERIFY_INPUT_EOF
$VERIFY_OUTPUT
VERIFY_INPUT_EOF
  TUNNEL_STATUS=1
  if [ "$RUNTIME_ONLY" -eq 0 ]; then
    if tunnel_output="$(TUNNEL_HOSTS_JSON="${TUNNEL_HOSTS_JSON:-$HOSTS_JSON}" TUNNEL_STATE_DIR="${TUNNEL_STATE_DIR:-$STATE_DIR}" bash "$HERE/glm_tunnel.sh" "$HOST_KEY" status 2>/dev/null)"; then
      TUNNEL_STATUS=0
    fi
  fi
  [ "$TUNNEL_CODE" = "200" ] && TUNNEL_OK=true
  verify_pair() {
    local name="$1" actual="$2" expected="$3"
    case "$actual" in
      *"$expected"*) mark "$name" ok "$actual" ;;
      *) mark "$name" fail "expected $expected, got ${actual:-missing}"; FAILED=1 ;;
    esac
  }
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    if [ -n "$CODEX_LINE" ]; then mark verify_codex ok "$CODEX_LINE"; else mark verify_codex fail "codex missing"; FAILED=1; fi
    if [ -n "$CLAUDE_LINE" ]; then mark verify_claude ok "$CLAUDE_LINE"; else mark verify_claude fail "claude missing"; FAILED=1; fi
  else
    verify_pair verify_codex "$CODEX_LINE" "$CODEX_VERSION"
    verify_pair verify_claude "$CLAUDE_LINE" "$CLAUDE_VERSION"
  fi
  if [ -n "$NODE_LINE" ]; then
    mark verify_node ok "$NODE_LINE"
  else
    mark verify_node fail "node version missing"
    FAILED=1
  fi
  if [ "${PYTHON_OK:-0}" = "1" ]; then
    mark verify_python ok "import json"
  else
    mark verify_python fail "import json failed"
    FAILED=1
  fi
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    if [ "${RUNTIME_OK:-0}" = "1" ]; then
      mark verify_runtime ok "runtime syntax/import surface"
    else
      mark verify_runtime fail "runtime verification failed"
      FAILED=1
    fi
    mark verify_macro skipped "runtime-only"
  else
    if [ "${MACRO_LINE:-}" = "true" ]; then
      mark verify_macro ok "inside work tree"
    else
      mark verify_macro fail "macro=${MACRO_LINE:-missing}"
      FAILED=1
    fi
  fi
  DISK_OK=0
  awk -v got="${DISK_FREE_GB:-}" -v want="$MIN_FREE_GB" 'BEGIN { if ((got != "") && (got+0 > want+0)) exit 0; exit 1 }' && DISK_OK=1
  if [ "$DISK_OK" -eq 1 ]; then
    mark verify_disk ok "${DISK_FREE_GB} GB free > $MIN_FREE_GB GB"
  else
    mark verify_disk fail "disk_free_gb=${DISK_FREE_GB:-missing} required=$MIN_FREE_GB"
    FAILED=1
  fi
  if [ "$RUNTIME_ONLY" -eq 1 ]; then
    mark verify_tunnel skipped "runtime-only"
  elif [ "$TUNNEL_STATUS" -eq 0 ]; then
    if [ "$TUNNEL_CODE" = "200" ]; then
      mark verify_tunnel ok "health=200"
    else
      mark verify_tunnel fail "health=${TUNNEL_CODE:-missing}"
      FAILED=1
    fi
  elif [[ "$tunnel_output" == pid-alive\ * ]]; then
    mark verify_tunnel fail "managed tunnel unhealthy"
    FAILED=1
  else
    mark verify_tunnel skipped "tunnel manager not running"
  fi
else
  mark remote_verify fail "prior bootstrap step failed"
  mark verify_codex skipped "not reached"
  mark verify_claude skipped "not reached"
  mark verify_node skipped "not reached"
  mark verify_python skipped "not reached"
  mark verify_runtime skipped "not reached"
  mark verify_macro skipped "not reached"
  mark verify_disk skipped "not reached"
  mark verify_tunnel skipped "not reached"
fi

write_receipt "$FAILED" "$CODEX_LINE" "$CLAUDE_LINE" "$NODE_LINE" "$TUNNEL_OK"
exit "$FAILED"
