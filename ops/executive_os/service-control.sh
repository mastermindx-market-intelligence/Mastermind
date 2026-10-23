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
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(builtin cd -P "$(/usr/bin/dirname "$SCRIPT_SOURCE")" && /bin/pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(/usr/bin/basename "$SCRIPT_SOURCE")"
GATEWAY_PREFLIGHT_PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"

usage() {
  /bin/echo "usage: $0 {start|stop|restart|restart-gateway|start-finite|stop-finite|status-finite|prepare-paid|qualify-paid|stage-paid|reconcile-paid|status-paid|start-readside|stop-readside|stop-incident-broker|start-agent-relay|stop-agent-relay|status-agent-relay|status}" >&2
  /bin/echo "restart-gateway requires --expected-sha <40 lowercase hex characters>" >&2
  /bin/echo "finite actions require --expected-sha <40 lowercase hex> --expected-manifest-sha256 <64 lowercase hex>" >&2
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
  # Drain captured output under pipefail; the builtin also avoids exec argv limits.
  builtin printf '%s\n' "$after_output" | /usr/bin/awk -v label="$label" '!found && /state =/ {print "service=" label " " $0; found=1}'
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
  builtin printf '%s\n' "$1" | /usr/bin/awk '
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
    builtin printf '%s\n' "$output" | /usr/bin/awk -v label="\"$AGENT_RELAY_LABEL\"" '
      !found && index($0, label) {
        if ($0 ~ /=>[[:space:]]*(disabled|true)([[:space:]]|$)/) {
          print "disabled"
          found=1
          next
        }
        if ($0 ~ /=>[[:space:]]*(enabled|false)([[:space:]]|$)/) {
          print "enabled"
          found=1
          next
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

agent_relay_precondition_unknown() {
  local stage="$1"
  /bin/echo "service=$AGENT_RELAY_LABEL state=unknown stage=$stage" >&2
  return 1
}

agent_relay_effect_unknown() {
  local stage="$1"
  /bin/echo "service=$AGENT_RELAY_LABEL state=effect_unknown stage=$stage" >&2
  return 75
}

agent_relay_observation_failure() {
  local stage="$1"
  local effect_started="$2"
  if [ "$effect_started" -eq 0 ]; then
    agent_relay_precondition_unknown "$stage"
  else
    agent_relay_effect_unknown "$stage"
  fi
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
  local disabled registration action rc=0 check effect_started=0

  disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "preflight-disabled" "$effect_started"
  if [ "$disabled" = "disabled" ]; then
    effect_started=1
    rc=0
    /bin/launchctl enable "system/$AGENT_RELAY_LABEL" || rc=$?
    disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "enable-reconcile" "$effect_started"
    [ "$disabled" = "enabled" ] || agent_relay_effect_unknown "enable-reconcile"
    if [ "$rc" -ne 0 ]; then
      /bin/echo "service=$AGENT_RELAY_LABEL effect=enable recovered=1"
    fi
  fi

  registration="$(agent_relay_registration_state)" || agent_relay_observation_failure "pre-start-registration" "$effect_started"
  if [ "$registration" = "running" ]; then
    disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "start-final-disabled" "$effect_started"
    [ "$disabled" = "enabled" ] || agent_relay_observation_failure "start-final-disabled" "$effect_started"
    /bin/echo "service=$AGENT_RELAY_LABEL state=running existing=1 disabled=enabled"
    return 0
  fi

  case "$registration" in
    registered)
      action="kickstart"
      effect_started=1
      rc=0
      /bin/launchctl kickstart "system/$AGENT_RELAY_LABEL" || rc=$?
      ;;
    absent)
      action="bootstrap"
      effect_started=1
      rc=0
      /bin/launchctl bootstrap system "$AGENT_RELAY_PLIST" || rc=$?
      ;;
    *) agent_relay_observation_failure "pre-start-registration" "$effect_started" ;;
  esac

  for ((check = 0; check <= 30; check++)); do
    registration="$(agent_relay_registration_state)" || agent_relay_observation_failure "$action-reconcile" "$effect_started"
    if [ "$registration" = "running" ]; then
      disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "start-final-disabled" "$effect_started"
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
  local disabled registration rc=0 check effect_started=0

  # Pre-enrollment disabled+absent state belongs to A2 preparation. This
  # lifecycle owner may begin a stop only for an exactly registered service.
  require_registered "$AGENT_RELAY_LABEL"

  disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "pre-stop-disabled" "$effect_started"
  if [ "$disabled" = "enabled" ]; then
    effect_started=1
    rc=0
    /bin/launchctl disable "system/$AGENT_RELAY_LABEL" || rc=$?
    disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "disable-reconcile" "$effect_started"
    [ "$disabled" = "disabled" ] || agent_relay_effect_unknown "disable-reconcile"
    if [ "$rc" -ne 0 ]; then
      /bin/echo "service=$AGENT_RELAY_LABEL effect=disable recovered=1"
    fi
  fi

  registration="$(agent_relay_registration_state)" || agent_relay_observation_failure "pre-bootout-registration" "$effect_started"
  if [ "$registration" = "absent" ]; then
    /bin/echo "service=$AGENT_RELAY_LABEL state=absent disabled=disabled"
    return 0
  fi

  effect_started=1
  rc=0
  /bin/launchctl bootout "system/$AGENT_RELAY_LABEL" >/dev/null 2>&1 || rc=$?
  for ((check = 0; check <= 30; check++)); do
    registration="$(agent_relay_registration_state)" || agent_relay_observation_failure "bootout-reconcile" "$effect_started"
    if [ "$registration" = "absent" ]; then
      disabled="$(agent_relay_disabled_state)" || agent_relay_observation_failure "stop-final-disabled" "$effect_started"
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
  # plutil -lint accepts plist input only. Parse the JSON config through its
  # conversion reader without rewriting it; deep preflight still owns schema,
  # policy, principal and sealed-generation qualification before any effect.
  /usr/bin/plutil -convert json -o /dev/null "$MCP_CONFIG" >/dev/null 2>&1 || return 1
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

qualify_gateway_refresh_preflight() {
  local expected_sha="$1"
  local expected_dir="$MCP_RELEASE_ROOT/$expected_sha/ops/executive_os"
  local controller="$expected_dir/service-control.sh"
  local helper="$expected_dir/gateway_refresh_preflight.py"
  # The lifecycle controller and deep verifier must be the same installed
  # generation being qualified. Bind the raw BASH_SOURCE path first: unlike
  # derived cd/pwd state, it cannot be changed by caller-defined shell
  # functions. Canonical lifecycle callers execute this exact absolute path.
  [[ "$SCRIPT_SOURCE" == "$controller" ]] || return 1
  [[ "$SCRIPT_DIR" == "$expected_dir" ]] || return 1
  [[ "$SCRIPT_PATH" == "$controller" ]] || return 1
  [[ -f "$controller" && ! -L "$controller" ]] || return 1
  [[ -f "$helper" && ! -L "$helper" ]] || return 1
  "$GATEWAY_PREFLIGHT_PYTHON" -I -S -B "$helper" \
    --expected-sha "$expected_sha" >/dev/null
}


require_gateway_enabled() {
  local output
  if ! output="$(/bin/launchctl print-disabled system 2>/dev/null)"; then
    /bin/echo "gateway must already be enabled: state unreadable" >&2
    return 1
  fi
  if ! builtin printf '%s\n' "$output" | /usr/bin/awk -v label="$MCP_LABEL" '
    NF == 0 {next}
    $1 == "disabled" && $2 == "services" && $3 == "=" && $4 == "{" && NF == 4 {
      if (state != 0) invalid=1
      state=1; header++; next
    }
    $1 == "}" && NF == 1 {
      if (state != 1) invalid=1
      state=2; footer++; next
    }
    NF == 3 && $1 ~ /^"[A-Za-z0-9._-]+"$/ && $2 == "=>" \
        && ($3 == "enabled" || $3 == "disabled" || $3 == "true" || $3 == "false") {
      if (state != 1 || labels[$1]++) {
        invalid=1
        next
      }
      if ($1 == "\"" label "\"") {
        seen++;
        if ($3 == "disabled" || $3 == "true") disabled=1
      }
      next
    }
    {invalid=1}
    END {
      # print-disabled is an override table, not an inventory. A structurally
      # complete table with no row for this label means default-enabled.
      exit(state == 2 && header == 1 && footer == 1 && !invalid && seen <= 1 && !disabled ? 0 : 1)
    }
  '; then
    /bin/echo "gateway must already be enabled: disabled or unknown" >&2
    return 1
  fi
}

WORKER_OBSERVED_STATE=""
WORKER_OBSERVED_PID=""

pid_from_output() {
  builtin printf '%s\n' "$1" | /usr/bin/awk '
    !found {
      for (i = 1; i <= NF - 2; i++) {
        if ($i == "pid" && $(i + 1) == "=" && $(i + 2) ~ /^[0-9]+$/) {
          print $(i + 2)
          found=1
          break
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
  prepare-paid|qualify-paid|stage-paid|reconcile-paid|status-paid)
    [ "$#" -ge 3 ] && [ "$2" = "--expected-sha" ] || usage
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] || usage
    ;;
  start-finite|stop-finite|status-finite)
    [ "$#" -eq 5 ] && [ "$2" = "--expected-sha" ] && [ "$4" = "--expected-manifest-sha256" ] || usage
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] && [[ "$5" =~ ^[0-9a-f]{64}$ ]] || usage
    ;;
  restart-gateway)
    [ "$#" -eq 3 ] && [ "$2" = "--expected-sha" ] || usage
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] || usage
    ;;
  start-restored-a2-readside)
    [ "$#" -eq 15 ] && [ "$2" = "--expected-sha" ] || usage
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] || usage
    ;;
  *) [ "$#" -eq 1 ] || usage ;;
esac
case "$1" in
  prepare-paid|qualify-paid|stage-paid|reconcile-paid|status-paid)
    require_root
    paid_dir="$MCP_RELEASE_ROOT/$3/ops/executive_os"
    [[ "$SCRIPT_SOURCE" == "$paid_dir/service-control.sh" ]] || exit 65
    [[ "$SCRIPT_DIR" == "$paid_dir" ]] && [[ "$SCRIPT_PATH" == "$paid_dir/service-control.sh" ]] || exit 65
    exec "$GATEWAY_PREFLIGHT_PYTHON" -I -S -B "$paid_dir/canonical_paid_actions.py" "$@"
    ;;
  stop-incident-broker)
    require_root
    exec "$GATEWAY_PREFLIGHT_PYTHON" -I -S -B "$SCRIPT_DIR/../../scripts/executive_os_incident_maintenance.py"
    ;;
  start-finite|stop-finite|status-finite)
    require_root
    finite_dir="$MCP_RELEASE_ROOT/$3/ops/executive_os"
    [[ "$SCRIPT_SOURCE" == "$finite_dir/service-control.sh" ]] || exit 65
    [[ "$SCRIPT_DIR" == "$finite_dir" ]] && [[ "$SCRIPT_PATH" == "$finite_dir/service-control.sh" ]] || exit 65
    exec "$GATEWAY_PREFLIGHT_PYTHON" -I -S -B "$finite_dir/finite_service_lifecycle.py" "$@"
    ;;
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
    if ! qualify_gateway_refresh_preflight "$3"; then
      /bin/echo "gateway deep preflight failed" >&2
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
    if ! qualify_gateway_release "$3" \
        || ! qualify_gateway_refresh_preflight "$3"; then
      /bin/echo "gateway_refresh_effect_unknown stage=postflight; do not replay" >&2
      exit 75
    fi
    # The replacement may exit while deep postflight qualification walks the
    # sealed release/runtime closure. Rejoin enabled + running state only after
    # postflight completes before reporting success.
    if ! require_gateway_enabled || ! require_running "$MCP_LABEL"; then
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
  start-restored-a2-readside)
    # Same fixed-label service owner; A2 CAS and Control restore settled first.
    [ "$#" -eq 15 ] \
      && [ "$2" = "--expected-sha" ] \
      && [ "$4" = "--expected-control-sha256" ] \
      && [ "$6" = "--expected-previous-release-sha" ] \
      && [ "$8" = "--expected-previous-tree-sha" ] \
      && [ "${10}" = "--expected-previous-config-sha256" ] \
      && [ "${12}" = "--expected-previous-plist-sha256" ] \
      && [ "${14}" = "--expected-bot-user-id" ] || usage
    [[ "$3" =~ ^[0-9a-f]{40}$ ]] \
      && [[ "$5" =~ ^[0-9a-f]{64}$ ]] \
      && [[ "$7" =~ ^[0-9a-f]{40}$ ]] \
      && [[ "$9" =~ ^[0-9a-f]{40}$ ]] \
      && [[ "${11}" =~ ^[0-9a-f]{64}$ ]] \
      && [[ "${13}" =~ ^[0-9a-f]{64}$ ]] \
      && [[ "${15}" =~ ^U[0-9A-Z]{9,}$ ]] || usage
    require_root
    local_release_root="$MCP_RELEASE_ROOT/$3"
    local_release_dir="$local_release_root/ops/executive_os"
    local_recovery_script="$local_release_dir/service-control.sh"
    # Root Python import must bind to the exact installed service controller.
    [[ "$SCRIPT_SOURCE" == "$local_recovery_script" ]] || exit 65
    [[ "$SCRIPT_DIR" == "$local_release_dir" ]] || exit 65
    [[ "$SCRIPT_PATH" == "$local_recovery_script" ]] || exit 65
    [[ -f "$local_recovery_script" && ! -L "$local_recovery_script" ]] || exit 65
    validate_plist "$AGENT_RELAY_PLIST"
    validate_plist "$RELAY_PLIST"
    validate_plist "$CONTROL_PLIST"
    readside_preflight
    require_absent "$AGENT_RELAY_LABEL"
    require_absent "$RELAY_LABEL"
    require_absent "$CONTROL_LABEL"
    [ "$(agent_relay_disabled_state)" = "disabled" ] || {
      /bin/echo "A2 must be unloaded and disabled before restoration" >&2
      exit 65
    }
    "$GATEWAY_PREFLIGHT_PYTHON" -I -S -B - "$local_release_root" "$@" <<'PY_RESTORED_A2'
import sys
sys.path.insert(0, sys.argv[1])
from ops.executive_os.autonomy_control import main
raise SystemExit(main(["a2-restored-readside-preflight", *sys.argv[3:]]))
PY_RESTORED_A2
    if ! start_agent_relay; then
      /bin/echo "a2_restore_effect_unknown stage=agent-relay-start" >&2
      exit 75
    fi
    if ! require_running "$AGENT_RELAY_LABEL"; then
      /bin/echo "a2_restore_effect_unknown stage=agent-relay-running" >&2
      exit 75
    fi
    if ! ensure_running "$RELAY_LABEL" "$RELAY_PLIST"; then
      /bin/echo "a2_restore_effect_unknown stage=c1-start" >&2
      exit 75
    fi
    if ! ensure_running "$CONTROL_LABEL" "$CONTROL_PLIST"; then
      /bin/echo "a2_restore_effect_unknown stage=control-start" >&2
      exit 75
    fi
    if ! readside_postflight; then
      /bin/echo "a2_restore_effect_unknown stage=readside-postflight" >&2
      exit 75
    fi
    /bin/echo "a2_restored_readside=running release=$3 previous_a2_release=$7 live_slack_return=unverified"
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
