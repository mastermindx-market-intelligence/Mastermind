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
CONTROL_PLIST="/Library/LaunchDaemons/$CONTROL_LABEL.plist"
WORKER_PLIST="/Library/LaunchDaemons/$WORKER_LABEL.plist"
RELAY_PLIST="/Library/LaunchDaemons/$RELAY_LABEL.plist"
AGENT_RELAY_PLIST="/Library/LaunchDaemons/$AGENT_RELAY_LABEL.plist"
SCRIPT_DIR="$(cd -P "$(/usr/bin/dirname "$0")" && /bin/pwd)"

usage() {
  /bin/echo "usage: $0 {start|stop|restart|start-readside|stop-readside|start-agent-relay|stop-agent-relay|status-agent-relay|status}" >&2
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
  /bin/launchctl disable "system/$label"
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

agent_relay_disabled_state() {
  local output status=0 state
  output="$(/bin/launchctl print-disabled system 2>/dev/null)" || status=$?
  if [ "$status" -ne 0 ]; then
    return 1
  fi
  state="$(
    /bin/echo "$output" | /usr/bin/awk -v label="\"$AGENT_RELAY_LABEL\"" '
      index($0, label) {
        if ($0 ~ /=>[[:space:]]*(disabled|true)([[:space:]]|$)/) {
          print "disabled"
          found=1
          exit
        }
        if ($0 ~ /=>[[:space:]]*(enabled|false)([[:space:]]|$)/) {
          print "enabled"
          found=1
          exit
        }
        bad=1
      }
      END {
        if (!found) {
          exit(bad ? 2 : 1)
        }
      }
    '
  )" || return 1
  case "$state" in
    enabled|disabled) /bin/echo "$state" ;;
    *) return 1 ;;
  esac
}

agent_relay_registration_state() {
  local output status=0
  output="$(/bin/launchctl print "system/$AGENT_RELAY_LABEL" 2>/dev/null)" || status=$?
  case "$status" in
    0)
      if is_running_output "$output"; then
        /bin/echo "running"
      else
        /bin/echo "registered"
      fi
      ;;
    113) /bin/echo "absent" ;;
    *) return 1 ;;
  esac
}

agent_relay_effect_unknown() {
  local stage="$1"
  /bin/echo "service=$AGENT_RELAY_LABEL state=effect_unknown stage=$stage" >&2
  return 75
}

agent_relay_status() {
  local disabled registration
  disabled="$(agent_relay_disabled_state)" || {
    /bin/echo "service=$AGENT_RELAY_LABEL state=unknown disabled=unknown" >&2
    return 1
  }
  registration="$(agent_relay_registration_state)" || {
    /bin/echo "service=$AGENT_RELAY_LABEL state=unknown disabled=$disabled" >&2
    return 1
  }
  /bin/echo "service=$AGENT_RELAY_LABEL state=$registration disabled=$disabled"
}

start_agent_relay() {
  local disabled registration action rc=0 check

  disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "preflight-disabled"
  if [ "$disabled" = "disabled" ]; then
    rc=0
    /bin/launchctl enable "system/$AGENT_RELAY_LABEL" || rc=$?
    disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "enable-reconcile"
    [ "$disabled" = "enabled" ] || agent_relay_effect_unknown "enable-reconcile"
    if [ "$rc" -ne 0 ]; then
      /bin/echo "service=$AGENT_RELAY_LABEL effect=enable recovered=1"
    fi
  fi

  registration="$(agent_relay_registration_state)" || agent_relay_effect_unknown "pre-start-registration"
  if [ "$registration" = "running" ]; then
    disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "start-final-disabled"
    [ "$disabled" = "enabled" ] || agent_relay_effect_unknown "start-final-disabled"
    /bin/echo "service=$AGENT_RELAY_LABEL state=running existing=1 disabled=enabled"
    return 0
  fi

  case "$registration" in
    registered)
      action="kickstart"
      rc=0
      /bin/launchctl kickstart "system/$AGENT_RELAY_LABEL" || rc=$?
      ;;
    absent)
      action="bootstrap"
      rc=0
      /bin/launchctl bootstrap system "$AGENT_RELAY_PLIST" || rc=$?
      ;;
    *) agent_relay_effect_unknown "pre-start-registration" ;;
  esac

  for ((check = 0; check <= 30; check++)); do
    registration="$(agent_relay_registration_state)" || agent_relay_effect_unknown "$action-reconcile"
    if [ "$registration" = "running" ]; then
      disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "start-final-disabled"
      [ "$disabled" = "enabled" ] || agent_relay_effect_unknown "start-final-disabled"
      if [ "$rc" -ne 0 ]; then
        /bin/echo "service=$AGENT_RELAY_LABEL effect=$action recovered=1"
      fi
      /bin/echo "service=$AGENT_RELAY_LABEL state=running existing=0 disabled=enabled"
      return 0
    fi
    case "$registration" in
      registered|absent) ;;
      *) agent_relay_effect_unknown "$action-reconcile" ;;
    esac
    if [ "$check" -lt 30 ]; then
      /bin/sleep 1
    fi
  done
  agent_relay_effect_unknown "$action-reconcile"
}

stop_agent_relay() {
  local disabled registration rc=0 check

  # Pre-enrollment disabled+absent state belongs to A2 preparation. This
  # lifecycle owner may begin a stop only for an exactly registered service.
  require_registered "$AGENT_RELAY_LABEL"

  disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "pre-stop-disabled"
  if [ "$disabled" = "enabled" ]; then
    rc=0
    /bin/launchctl disable "system/$AGENT_RELAY_LABEL" || rc=$?
    disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "disable-reconcile"
    [ "$disabled" = "disabled" ] || agent_relay_effect_unknown "disable-reconcile"
    if [ "$rc" -ne 0 ]; then
      /bin/echo "service=$AGENT_RELAY_LABEL effect=disable recovered=1"
    fi
  fi

  registration="$(agent_relay_registration_state)" || agent_relay_effect_unknown "pre-bootout-registration"
  if [ "$registration" = "absent" ]; then
    /bin/echo "service=$AGENT_RELAY_LABEL state=absent disabled=disabled"
    return 0
  fi

  rc=0
  /bin/launchctl bootout "system/$AGENT_RELAY_LABEL" >/dev/null 2>&1 || rc=$?
  for ((check = 0; check <= 30; check++)); do
    registration="$(agent_relay_registration_state)" || agent_relay_effect_unknown "bootout-reconcile"
    if [ "$registration" = "absent" ]; then
      disabled="$(agent_relay_disabled_state)" || agent_relay_effect_unknown "stop-final-disabled"
      [ "$disabled" = "disabled" ] || agent_relay_effect_unknown "stop-final-disabled"
      if [ "$rc" -ne 0 ]; then
        /bin/echo "service=$AGENT_RELAY_LABEL effect=bootout recovered=1"
      fi
      /bin/echo "service=$AGENT_RELAY_LABEL state=absent disabled=disabled"
      return 0
    fi
    case "$registration" in
      running|registered) ;;
      *) agent_relay_effect_unknown "bootout-reconcile" ;;
    esac
    if [ "$check" -lt 30 ]; then
      /bin/sleep 1
    fi
  done
  agent_relay_effect_unknown "bootout-reconcile"
}

ensure_running() {
  local label="$1"
  local plist="$2"
  /bin/launchctl enable "system/$label"
  local before_output before_status=0
  before_output="$(/bin/launchctl print "system/$label" 2>/dev/null)" || before_status=$?
  if [ "$before_status" -eq 0 ] && is_running_output "$before_output"; then
    /bin/echo "service=$label state=running existing=1"
    return 0
  fi
  case "$before_status" in
    0) /bin/launchctl kickstart "system/$label" ;;
    113) /bin/launchctl bootstrap system "$plist" ;;
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

[ "$#" -eq 1 ] || usage
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
    start_agent_relay
    ;;
  stop-agent-relay)
    require_root
    stop_agent_relay
    ;;
  status-agent-relay)
    require_root
    agent_relay_status
    ;;
  status)
    exec /bin/bash "$SCRIPT_DIR/status.sh"
    ;;
  *) usage ;;
esac
