#!/bin/bash
# Bounded lifecycle controller for fixed Executive OS service groups.
# It never accepts a label, plist path, domain, or arbitrary launchctl verb.
set -euo pipefail
umask 077

CONTROL_LABEL="com.mastermind.executive.control"
WORKER_LABEL="com.mastermind.executive.worker.codex"
RELAY_LABEL="com.mastermind.executive.sol-state-relay"
AGENT_RELAY_LABEL="com.mastermind.executive.agent-relay"
MCP_LABEL="com.mastermind.executive.mcp"
BACKUP_LABEL="com.mastermind.executive.backup"
MCP_PLIST="/Library/LaunchDaemons/$MCP_LABEL.plist"
MCP_CONFIG="/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
MCP_RELEASE_ROOT="/Library/Application Support/MastermindExecutive/releases"
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"
RELAY_PLIST="/Library/LaunchDaemons/$RELAY_LABEL.plist"
AGENT_RELAY_PLIST="/Library/LaunchDaemons/$AGENT_RELAY_LABEL.plist"
SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"

usage() {
  /bin/echo "usage: $0 {start|stop|restart|restart-gateway|start-readside|stop-readside|start-agent-relay|stop-agent-relay|status}" >&2
  /bin/echo "restart-gateway requires --expected-sha <40 lowercase hex characters>" >&2
  exit 64
}

require_root() {
  [ "$(/usr/bin/id -u)" -eq 0 ] || {
    /bin/echo "service lifecycle changes require root" >&2
    exit 77
  }
  [ "$(/usr/bin/uname -s)" = "Darwin" ] || {
    /bin/echo "service-control.sh supports macOS only" >&2
    exit 69
  }
}

validate_plist() {
  local path="$1"
  [ -f "$path" ] && [ ! -L "$path" ] || {
    /bin/echo "missing or unsafe launchd plist: $path" >&2
    exit 65
  }
  /usr/bin/plutil -lint "$path" >/dev/null
}

start_one() {
  local label="$1"
  local plist="$2"
  /bin/launchctl enable "system/$label"
  local before_status=0
  /bin/launchctl print "system/$label" >/dev/null 2>&1 || before_status=$?
  case "$before_status" in
    0) /bin/launchctl kickstart "system/$label" ;;
    113) /bin/launchctl bootstrap system "$plist" ;;
    *)
      /bin/echo "service registration state unknown before start: $label (launchctl print exit $before_status)" >&2
      return 1
      ;;
  esac
  # A zero exit from kickstart/bootstrap is not proof of registration; read back.
  local after_output after_status=0
  after_output="$(/bin/launchctl print "system/$label" 2>/dev/null)" || after_status=$?
  if [ "$after_status" -ne 0 ]; then
    /bin/echo "service registration missing after start: $label (launchctl print exit $after_status)" >&2
    return 1
  fi
  /bin/echo "$after_output" | /usr/bin/awk -v label="$label" '/state =/ {print "service=" label " " $0; exit}'
}

stop_one() {
  local label="$1"
  /bin/launchctl disable "system/$label" || return $?
  # A nonzero bootout alone cannot prove absence or failure; read back.
  /bin/launchctl bootout "system/$label" >/dev/null 2>&1 || true
  # launchd acknowledges bootout before the service has fully disappeared.
  # Observe for at most 30 sleeps; never repeat disable or bootout.
  local after_status check
  for ((check = 0; check <= 30; check++)); do
    after_status=0
    /bin/launchctl print "system/$label" >/dev/null 2>&1 || after_status=$?
    if [ "$after_status" -eq 113 ]; then
      /bin/echo "service=$label state=absent"
      return 0
    fi
    case "$after_status" in
      0) ;;
      *)
        /bin/echo "service registration state unknown after stop: $label (launchctl print exit $after_status)" >&2
        return 1
        ;;
    esac
    if [ "$check" -lt 30 ]; then
      /bin/sleep 1
    fi
  done
  /bin/echo "service still registered after stop wait: $label" >&2
  return 1
}


is_running_output() {
  /bin/echo "$1" | /usr/bin/awk '
    $1 == "state" && $2 == "=" && $3 == "running" {found=1}
    END {exit(found ? 0 : 1)}
  '
}

require_running() {
  local label="$1"
  local output status=0
  output="$(/bin/launchctl print "system/$label" 2>/dev/null)" || status=$?
  if [ "$status" -eq 0 ] && is_running_output "$output"; then
    /bin/echo "service=$label state=running"
    return 0
  fi
  if [ "$status" -eq 0 ]; then
    /bin/echo "service must be running: $label" >&2
  elif [ "$status" -eq 113 ]; then
    /bin/echo "service must be running but is absent: $label" >&2
  else
    /bin/echo "service running state unknown: $label (launchctl print exit $status)" >&2
  fi
  return 1
}

require_absent() {
  local label="$1"
  local status=0
  /bin/launchctl print "system/$label" >/dev/null 2>&1 || status=$?
  if [ "$status" -eq 113 ]; then
    /bin/echo "service=$label state=absent"
    return 0
  fi
  if [ "$status" -eq 0 ]; then
    /bin/echo "service must remain absent: $label" >&2
  else
    /bin/echo "service absence state unknown: $label (launchctl print exit $status)" >&2
  fi
  return 1
}

require_registered() {
  local label="$1"
  local status=0
  /bin/launchctl print "system/$label" >/dev/null 2>&1 || status=$?
  if [ "$status" -eq 0 ]; then
    return 0
  fi
  if [ "$status" -eq 113 ]; then
    /bin/echo "service must be registered before stop: $label" >&2
  else
    /bin/echo "service registration state unknown before stop: $label (launchctl print exit $status)" >&2
  fi
  return 1
}

ensure_running() {
  local label="$1"
  local plist="$2"
  /bin/launchctl enable "system/$label" || return $?
  local before_output before_status=0
  before_output="$(/bin/launchctl print "system/$label" 2>/dev/null)" || before_status=$?
  if [ "$before_status" -eq 0 ] && is_running_output "$before_output"; then
    /bin/echo "service=$label state=running existing=1"
    return 0
  fi
  case "$before_status" in
    0) /bin/launchctl kickstart "system/$label" || return $? ;;
    113) /bin/launchctl bootstrap system "$plist" || return $? ;;
    *)
      /bin/echo "service registration state unknown before read-side start: $label (launchctl print exit $before_status)" >&2
      return 1
      ;;
  esac
  # launchd acknowledges bootstrap/kickstart before the daemon is running.
  # Observe readiness for at most 30 sleeps; never repeat the modifying call.
  local after_output after_status check
  for ((check = 0; check <= 30; check++)); do
    after_status=0
    after_output="$(/bin/launchctl print "system/$label" 2>/dev/null)" || after_status=$?
    if [ "$after_status" -eq 0 ] && is_running_output "$after_output"; then
      /bin/echo "service=$label state=running existing=0"
      return 0
    fi
    case "$after_status" in
      0|113) ;;
      *)
        /bin/echo "service running state unknown after read-side start: $label (launchctl print exit $after_status)" >&2
        return 1
        ;;
    esac
    if [ "$check" -lt 30 ]; then
      /bin/sleep 1
    fi
  done
  /bin/echo "service did not become running within read-side startup wait: $label (launchctl print exit $after_status)" >&2
  return 1
}


# This is a read-only qualification of a generation already published by the
# installed release owner. It neither produces nor edits a config or plist.
gateway_field() {
  /usr/bin/plutil -extract "$2" raw -expect "$3" -o - "$1" 2>/dev/null
}

qualify_gateway_release() {
  local expected_sha="$1" release network_python runtime_pattern service_uid service_user service_group
  release="$MCP_RELEASE_ROOT/$expected_sha"
  # Do not call an exit-using helper here: this same observation runs both
  # before effects (65) and after a cycle (75), with classification by caller.
  [ -f "$MCP_PLIST" ] && [ ! -L "$MCP_PLIST" ] || return 1
  [ -f "$MCP_CONFIG" ] && [ ! -L "$MCP_CONFIG" ] || return 1
  /usr/bin/plutil -lint "$MCP_PLIST" >/dev/null 2>&1 || return 1
  /usr/bin/plutil -lint "$MCP_CONFIG" >/dev/null 2>&1 || return 1
  [ "$(gateway_field "$MCP_CONFIG" schema string)" = "mastermind.executive_mcp_install.v1" ] || return 1
  [ "$(gateway_field "$MCP_CONFIG" release_sha string)" = "$expected_sha" ] || return 1
  service_uid="$(gateway_field "$MCP_CONFIG" service_uid integer)" || return 1
  [[ "$service_uid" =~ ^[0-9]+$ ]] && [ "$service_uid" -gt 0 ] || return 1
  [ "$(gateway_field "$MCP_PLIST" Label string)" = "$MCP_LABEL" ] || return 1
  service_user="$(gateway_field "$MCP_PLIST" UserName string)" || return 1
  service_group="$(gateway_field "$MCP_PLIST" GroupName string)" || return 1
  # Bind the launchd principal to the service UID already published by the
  # sealed install generation without duplicating protected account topology.
  [ "$(/usr/bin/id -u "$service_user" 2>/dev/null)" = "$service_uid" ] || return 1
  [ "$(/usr/bin/id -gn "$service_user" 2>/dev/null)" = "$service_group" ] || return 1
  [ "$(gateway_field "$MCP_PLIST" WorkingDirectory string)" = "$release" ] || return 1
  # A Program override would take precedence over the reviewed argv[0].
  if /usr/bin/plutil -type Program "$MCP_PLIST" >/dev/null 2>&1; then
    return 1
  fi
  [ "$(gateway_field "$MCP_PLIST" ProgramArguments array)" = "6" ] || return 1
  network_python="$(gateway_field "$MCP_PLIST" ProgramArguments.0 string)" || return 1
  runtime_pattern='^/Library/Application Support/MastermindExecutive/network-runtimes/[0-9a-f]{64}/bin/python$'
  [[ "$network_python" =~ $runtime_pattern ]] || return 1
  [ "$(gateway_field "$MCP_PLIST" ProgramArguments.1 string)" = "-I" ] || return 1
  [ "$(gateway_field "$MCP_PLIST" ProgramArguments.2 string)" = "-B" ] || return 1
  [ "$(gateway_field "$MCP_PLIST" ProgramArguments.3 string)" = "$release/ops/executive_os/executive_mcp_entry.py" ] || return 1
  [ "$(gateway_field "$MCP_PLIST" ProgramArguments.4 string)" = "--config" ] || return 1
  [ "$(gateway_field "$MCP_PLIST" ProgramArguments.5 string)" = "$MCP_CONFIG" ] || return 1
}

require_gateway_enabled() {
  local output
  if ! output="$(/bin/launchctl print-disabled system 2>/dev/null)"; then
    /bin/echo "gateway must already be enabled: state unreadable" >&2
    return 1
  fi
  if ! /bin/echo "$output" | /usr/bin/awk -v label="$MCP_LABEL" '
    NF == 0 {next}
    $1 == "disabled" && $2 == "services" && $3 == "=" && $4 == "{" && NF == 4 {header++; next}
    $1 == "}" && NF == 1 {footer++; next}
    NF == 3 && $1 ~ /^"[A-Za-z0-9._-]+"$/ && $2 == "=>" \
        && ($3 == "enabled" || $3 == "disabled" || $3 == "true" || $3 == "false") {
      if ($1 == "\"" label "\"") {
        seen++;
        if ($3 == "disabled" || $3 == "true") disabled=1
      }
      next
    }
    {invalid=1}
    END {
      # print-disabled is an override table, not an inventory.  A valid table
      # with no row for this label means the service is default-enabled.
      exit(header == 1 && footer == 1 && !invalid && seen <= 1 && !disabled ? 0 : 1)
    }
  '; then
    /bin/echo "gateway must already be enabled: disabled or unknown" >&2
    return 1
  fi
}

WORKER_OBSERVED_STATE=""
WORKER_OBSERVED_PID=""

pid_from_output() {
  /bin/echo "$1" | /usr/bin/awk '
    {
      for (i = 1; i <= NF - 2; i++) {
        if ($i == "pid" && $(i + 1) == "=" && $(i + 2) ~ /^[0-9]+$/) {
          print $(i + 2)
          exit 0
        }
      }
    }
  '
}

capture_worker_state() {
  local output status=0 pid
  output="$(/bin/launchctl print "system/$WORKER_LABEL" 2>/dev/null)" || status=$?
  if [ "$status" -eq 113 ]; then
    WORKER_OBSERVED_STATE="absent"
    WORKER_OBSERVED_PID=""
    /bin/echo "service=$WORKER_LABEL state=absent preserved=pre"
    return 0
  fi
  if [ "$status" -eq 0 ] && is_running_output "$output"; then
    pid="$(pid_from_output "$output")"
    if [ -z "$pid" ]; then
      /bin/echo "running worker identity is unreadable: $WORKER_LABEL" >&2
      return 1
    fi
    WORKER_OBSERVED_STATE="running"
    WORKER_OBSERVED_PID="$pid"
    /bin/echo "service=$WORKER_LABEL state=running pid=$pid preserved=pre"
    return 0
  fi
  if [ "$status" -eq 0 ]; then
    /bin/echo "worker is registered in an unsupported non-running state: $WORKER_LABEL" >&2
  else
    /bin/echo "worker state is unknown: $WORKER_LABEL (launchctl print exit $status)" >&2
  fi
  return 1
}

require_worker_unchanged() {
  local output status=0 pid
  output="$(/bin/launchctl print "system/$WORKER_LABEL" 2>/dev/null)" || status=$?
  if [ "$WORKER_OBSERVED_STATE" = "absent" ]; then
    if [ "$status" -eq 113 ]; then
      /bin/echo "service=$WORKER_LABEL state=absent preserved=post"
      return 0
    fi
    /bin/echo "worker state changed during read-side action: expected absent" >&2
    return 1
  fi
  if [ "$WORKER_OBSERVED_STATE" = "running" ] && [ "$status" -eq 0 ] && is_running_output "$output"; then
    pid="$(pid_from_output "$output")"
    if [ -n "$pid" ] && [ "$pid" = "$WORKER_OBSERVED_PID" ]; then
      /bin/echo "service=$WORKER_LABEL state=running pid=$pid preserved=post"
      return 0
    fi
  fi
  /bin/echo "worker state changed during read-side action: expected running pid=$WORKER_OBSERVED_PID" >&2
  return 1
}

readside_preflight() {
  require_running "$MCP_LABEL"
  capture_worker_state
  require_absent "$BACKUP_LABEL"
}

readside_postflight() {
  require_running "$MCP_LABEL"
  require_worker_unchanged
  require_absent "$BACKUP_LABEL"
}

[ "$#" -ge 1 ] || usage
case "$1" in
  restart-gateway)
    [ "$#" -eq 3 ] && [ "$2" = "--expected-sha" ] || usage
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] || usage
    ;;
  *) [ "$#" -eq 1 ] || usage ;;
esac
case "$1" in
  start)
    require_root
    validate_plist "$WORKER_PLIST"
    validate_plist "$CONTROL_PLIST"
    start_one "$WORKER_LABEL" "$WORKER_PLIST"
    start_one "$CONTROL_LABEL" "$CONTROL_PLIST"
    ;;
  stop)
    require_root
    # Stop the control plane before removing its worker execution boundary.
    stop_one "$CONTROL_LABEL"
    stop_one "$WORKER_LABEL"
    ;;
  restart)
    require_root
    validate_plist "$WORKER_PLIST"
    validate_plist "$CONTROL_PLIST"
    stop_one "$CONTROL_LABEL"
    stop_one "$WORKER_LABEL"
    start_one "$WORKER_LABEL" "$WORKER_PLIST"
    start_one "$CONTROL_LABEL" "$CONTROL_PLIST"
    ;;
  restart-gateway)
    require_root
    # Fail before any modifying launchctl verb on a stale/mismatched target.
    if ! qualify_gateway_release "$3"; then
      /bin/echo "gateway release qualification failed" >&2
      exit 65
    fi
    require_gateway_enabled || exit 65
    require_running "$MCP_LABEL" || exit 65
    # Restart may re-enable only the service this invocation observed enabled
    # and running before its own stop. It cannot activate a disabled gateway.
    if ! stop_one "$MCP_LABEL"; then
      /bin/echo "gateway_refresh_effect_unknown stage=stop; do not replay" >&2
      exit 75
    fi
    if ! ensure_running "$MCP_LABEL" "$MCP_PLIST"; then
      /bin/echo "gateway_refresh_effect_unknown stage=start; do not replay" >&2
      exit 75
    fi
    if ! qualify_gateway_release "$3"; then
      /bin/echo "gateway_refresh_effect_unknown stage=postflight; do not replay" >&2
      exit 75
    fi
    /bin/echo "gateway_refresh=running release=$3 catalog_adoption=unverified"
    ;;
  start-readside)
    require_root
    validate_plist "$RELAY_PLIST"
    validate_plist "$CONTROL_PLIST"
    readside_preflight
    # Relay must be available before control binds its read/return path.
    ensure_running "$RELAY_LABEL" "$RELAY_PLIST"
    ensure_running "$CONTROL_LABEL" "$CONTROL_PLIST"
    readside_postflight
    ;;
  stop-readside)
    require_root
    readside_preflight
    # Stop the consumer before removing its Relay return boundary.
    stop_one "$CONTROL_LABEL"
    stop_one "$RELAY_LABEL"
    readside_postflight
    ;;
  start-agent-relay)
    require_root
    # Enrollment/verification is a separate A2 owner. Activation accepts no
    # caller-supplied label or plist and cannot manufacture enrollment state.
    validate_plist "$AGENT_RELAY_PLIST"
    ensure_running "$AGENT_RELAY_LABEL" "$AGENT_RELAY_PLIST"
    ;;
  stop-agent-relay)
    require_root
    # The pre-enrollment disabled override remains owned by A2 host
    # preparation. This lifecycle command may mutate the override only for a
    # service that launchd already proves is registered.
    require_registered "$AGENT_RELAY_LABEL"
    stop_one "$AGENT_RELAY_LABEL"
    ;;
  status)
    exec /bin/bash "$SCRIPT_DIR/status.sh"
    ;;
  *) usage ;;
esac
