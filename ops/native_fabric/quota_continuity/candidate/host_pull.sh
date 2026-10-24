#!/bin/bash
# host_pull.sh — P1 fleet telemetry: probe active lane hosts and local seat,
# ext/state/hosts/<host>.json (read by pool_status.py's HOST table).
# usage: bash host_pull.sh --once    one pass over all hosts, then exit
#        bash host_pull.sh           daemon: lanes + local seat every 60 s
#        bash host_pull.sh --diagnose-physical ubuntu0
#          detached physical DATA only; no shared state/readiness/admission
# The local host (hosts.json "local": true) is probed in-process; every remote
# host via ONE  perl -e 'alarm 25; exec @ARGV' ssh -o BatchMode=yes
# -o ConnectTimeout=8 <alias> '<probe>'  call per pass. The probe is a
# platform-aware POSIX sh snippet that sets its own PATH because BatchMode
# shells lack /opt/homebrew/bin.
# Unreachable host -> state file with "reachable": false plus an error class;
# the loop never aborts on one bad host. No gh calls. Kills nothing. Daemon
# mode refuses to double-start (pidfile state/host_pull.pid).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HOSTS_JSON="${HOST_PULL_HOSTS_JSON:-$HERE/hosts.json}"
STATE_DIR="${HOST_PULL_STATE_DIR:-$HERE/state/hosts}"
PIDFILE="${HOST_PULL_PIDFILE:-$HERE/state/host_pull.pid}"
INTERVAL=60

ONCE=0
SELECTED=""
PAID_HOST=""
PAID_REQUESTED=0
INSPECT_HOST=""
PHYSICAL_HOST=""
if [ "$#" -gt 0 ] && [ "$1" = "--diagnose-physical" ]; then
  [ "$#" -eq 2 ] && [ "$2" = "ubuntu0" ] || { echo "host_pull: fixed physical diagnostic arguments refused" >&2; exit 78; }
  PHYSICAL_HOST="$2"
  shift 2
fi
if [ "$#" -gt 0 ] && [ "$1" = "--inspect-host-env" ]; then
  [ "$#" -eq 2 ] && [ "$2" = "ubuntu0" ] || { echo "host_pull: fixed inspection arguments refused" >&2; exit 78; }
  INSPECT_HOST="$2"
  shift 2
fi
if [ "$#" -gt 0 ] && [ "$1" = "--paid-qualification" ]; then
  [ "$#" -eq 2 ] || { echo "host_pull: paid qualification arguments refused" >&2; exit 78; }
  PAID_REQUESTED=1
  PAID_HOST="$2"
  shift 2
fi
while [ "$#" -gt 0 ]; do
  case "$1" in
    --once) ONCE=1 ;;
    --host)
      [ "$#" -ge 2 ] || { echo "host_pull: --host requires HOST" >&2; exit 2; }
      shift
      case "$1" in
        ''|*[!A-Za-z0-9_.:-]*) echo "host_pull: unsafe host" >&2; exit 2 ;;
      esac
      case "$1" in
        [A-Za-z0-9]*) ;;
        *) echo "host_pull: unsafe host" >&2; exit 2 ;;
      esac
      SELECTED="$SELECTED $1"
      ;;
    *) echo "usage: host_pull.sh [--once [--host HOST ...]]" >&2; exit 2 ;;
  esac
  shift
done
if [ -n "$SELECTED" ] && [ "$ONCE" -ne 1 ]; then
  echo "host_pull: selected hosts require --once" >&2
  exit 2
fi

# One probe snippet, POSIX sh, branches on uname (darwin vs linux).
# @@WR@@ is worktree_root; @@LR@@ is the shell-quoted canonical runtime path.
PROBE_FILE="$HERE/host_pull_probe.template"
BACKEND_FILE="$HERE/host_pull_backend.py"
GLM_PROBE_FILE="$HERE/glm_host_account_probe.py"
ACCOUNTS_POLICY="${POOL_ACCOUNTS_YAML:-$HERE/../orch/fabric/accounts.yaml}"
# These are code/data for the existing collector, never credential stores.
# Missing/symlinked dependencies fail closed before any fleet probe.
if [ ! -f "$PROBE_FILE" ] || [ -L "$PROBE_FILE" ] ||
   [ ! -f "$BACKEND_FILE" ] || [ -L "$BACKEND_FILE" ]; then
  echo "host_pull: local probe dependencies unavailable" >&2
  exit 78
fi
# Bash built-in file read: no heredoc pipe, no cat subprocess.
PROBE_TEMPLATE="$(< "$PROBE_FILE")"
[ -n "$PROBE_TEMPLATE" ] || { echo "host_pull: empty probe template" >&2; exit 78; }

# host|is_local|ssh_alias|worktree_root — one line per probeable host.
read_hosts() {
  python3 -B "$BACKEND_FILE" read-hosts "$HOSTS_JSON" "$SELECTED" "$ONCE" --glm-readiness
}

write_state() { # $1 host, $2 probe rc, $3 probe stdout
  python3 -B "$BACKEND_FILE" write-state "$STATE_DIR" "$1" "$2" "$3" "$4"
}

# Both modes use this one incumbent authenticated transport. Qualification
# never enters the telemetry writer, daemon, account-readiness or fleet loop.
# A fixed, short SSH command receives the full generated probe on stdin. On
# Linux the original single remote argv reached ~140.5 KB (MAX_ARG_STRLEN
# 131072 bytes), masking healthy hosts as probe_exit_1. A private 0600 remote
# spool separates the script from child stdin, preserves shell status, and
# removes the spool on normal exit or catchable signals. Keep the existing
# fixed host, SSH policy, probe, and single collector unchanged.
HOST_PULL_REMOTE_STDIN_EXEC='umask 077; t=$(/usr/bin/mktemp "${TMPDIR:-/tmp}/host_pull_probe.XXXXXXXX") || exit 70; trap '"'"'/bin/rm -f -- "$t"'"'"' EXIT HUP INT TERM; /bin/cat >"$t" || exit 70; "${SHELL:-/bin/sh}" "$t" </dev/null'
run_probe() {
  local is_local="$1" alias="$2" probe="$3" key_guard="${4:-}"
  local key_options=()
  if [ "$key_guard" = "fixed-hook-inspection" ] || [ "$key_guard" = "fixed-physical-diagnostic" ]; then
    # This read-only inspection must never enroll/update a host key. Normal
    # telemetry retains its existing inherited transport policy unchanged.
    key_options=(-o StrictHostKeyChecking=yes -o UpdateHostKeys=no)
  elif [ -n "$key_guard" ]; then
    return 78
  fi
  if [ "$is_local" = "1" ]; then
    sh -c "$probe" 2>/dev/null
  elif [ -z "$alias" ]; then
    return 255
  else
    perl -e 'alarm 25; exec @ARGV' ssh -o BatchMode=yes -o ConnectTimeout=8 "${key_options[@]}" "$alias" "$HOST_PULL_REMOTE_STDIN_EXEC" 2>/dev/null <<< "$probe"
  fi
}

if [ -n "$PHYSICAL_HOST" ]; then
  # Diagnostic return only: never publish shared telemetry, load account
  # config, source HOST_ENV, start a daemon, or call the readiness builder.
  PREPARED=$(python3 -B "$BACKEND_FILE" physical-diagnostic-prepare "$HOSTS_JSON" "$PHYSICAL_HOST") || exit 78
  case "$PREPARED" in *$'\n'*) ;; *) exit 78 ;; esac
  PHYSICAL_ALIAS="${PREPARED%%$'\n'*}"
  PHYSICAL_PROBE="${PREPARED#*$'\n'}"
  OUT=$(run_probe 0 "$PHYSICAL_ALIAS" "$PHYSICAL_PROBE" fixed-physical-diagnostic)
  PHYSICAL_RC=$?
  printf '%s' "$OUT" | python3 -B "$BACKEND_FILE" physical-diagnostic-result "$PHYSICAL_RC"
  exit $?
fi

if [ -n "$INSPECT_HOST" ]; then
  # This separate read-only mode never builds/sources a readiness block and
  # never enters pass_once, shared telemetry writes, or daemon startup.
  PREPARED=$(python3 -B "$BACKEND_FILE" inspect-host-env-prepare "$HOSTS_JSON" "$INSPECT_HOST") || exit 78
  case "$PREPARED" in *$'\n'*) ;; *) exit 78 ;; esac
  INSPECT_ALIAS="${PREPARED%%$'\n'*}"
  INSPECT_PROBE="${PREPARED#*$'\n'}"
  OUT=$(run_probe 0 "$INSPECT_ALIAS" "$INSPECT_PROBE" fixed-hook-inspection)
  INSPECT_RC=$?
  printf '%s' "$OUT" | python3 -B "$BACKEND_FILE" inspect-host-env-result "$INSPECT_RC"
  exit $?
fi

if [ "$PAID_REQUESTED" -eq 1 ]; then
  # Only DATA exits this CLI. The actual installer-owned parent child handle,
  # pinned source, challenge and result join are required for qualification.
  PREPARED=$(python3 -I -S -B "$BACKEND_FILE" paid-qualification "$PAID_HOST") || exit 78
  case "$PREPARED" in
    *$'\n'*) ;;
    *) exit 78 ;;
  esac
  PAID_ALIAS="${PREPARED%%$'\n'*}"
  PAID_PROBE="${PREPARED#*$'\n'}"
  run_probe 0 "$PAID_ALIAS" "$PAID_PROBE"
  exit $?
fi

pass_once() {
  local host is_local alias wr probe rc t0 summary runtime local_runtime rows glm_probe glm_admitted
  rows=$(read_hosts) || return $?
  mkdir -p "$STATE_DIR" || return $?
  local_runtime=$(python3 -c 'import shlex, sys; print(shlex.quote(sys.argv[1]))' "$HERE/lane_runtime.py")
  while IFS='|' read -r host is_local alias wr glm_admitted; do
    [ -n "$host" ] || continue
    t0=$(date +%s)
    probe="${PROBE_TEMPLATE//@@WR@@/$wr}"
    runtime='"$HOME/lanes/ext/lane_runtime.py"'
    [ "$is_local" = "1" ] && runtime="$local_runtime"
    probe="${probe//@@LR@@/$runtime}"
    # Same existing transport. Nonsecret validator source and policy aliases only.
    # A failed projection stays absent; the eventual GLM join fails closed.
    glm_probe=":"
    if [ "$glm_admitted" = "1" ]; then
      glm_probe=$(python3 -B "$GLM_PROBE_FILE" "$host" "$alias" "$ACCOUNTS_POLICY" 2>/dev/null) || glm_probe=":"
    fi
    # Diagnostics are closed DATA, not admission. Keep the original shell
    # context and final readiness-block status; never salvage a failed probe.
    probe="printf '%s\n' 'HOST_PULL_STAGE_V1 PHYSICAL_BEGIN'
$probe
HOST_PULL_DIAG_PHYSICAL_RC=\$?
printf 'HOST_PULL_STAGE_V1 PHYSICAL_EXIT %s\n' \"\$HOST_PULL_DIAG_PHYSICAL_RC\"
printf '%s\n' 'HOST_PULL_STAGE_V1 READINESS_BEGIN'
$glm_probe
HOST_PULL_DIAG_READINESS_RC=\$?
printf 'HOST_PULL_STAGE_V1 READINESS_EXIT %s\n' \"\$HOST_PULL_DIAG_READINESS_RC\"
exit \"\$HOST_PULL_DIAG_READINESS_RC\""
    OUT=$(run_probe "$is_local" "$alias" "$probe")
    rc=$?
    summary=$(write_state "$host" "$rc" "$OUT" "$alias") || return $?
    echo "$(date -u +%Y-%m-%dT%H:%MZ) [pull] host=$host rc=$rc secs=$(( $(date +%s) - t0 )) $summary"
  done <<< "$rows"
}

if [ "$ONCE" -eq 0 ]; then
  mkdir -p "$(dirname "$PIDFILE")" || exit $?
  if [ -f "$PIDFILE" ]; then
    OLD=$(head -n 1 "$PIDFILE" 2>/dev/null | tr -dc '0-9')
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
      echo "REFUSED: host_pull daemon already running (pidfile=$PIDFILE pid=$OLD)" >&2
      exit 4
    fi
  fi
  echo $$ > "$PIDFILE"
  echo "$(date -u +%Y-%m-%dT%H:%MZ) [pull] daemon start pid=$$ interval=${INTERVAL}s state_dir=$STATE_DIR"
fi

while true; do
  pass_once
  PASS_RC=$?
  [ "$ONCE" -eq 1 ] && exit "$PASS_RC"
  sleep "$INTERVAL"
done
