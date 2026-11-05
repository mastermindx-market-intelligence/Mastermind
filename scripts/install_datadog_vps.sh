#!/usr/bin/env bash
# Install/configure Datadog on the authoritative Mastermind VPS.
# Requires DD_API_KEY at runtime; never prints or duplicates it into Mastermind config.
set -euo pipefail

DD_SITE="${DD_SITE:-us5.datadoghq.com}"
DD_ENVIRONMENT="${DD_ENVIRONMENT:-production}"
DD_SERVICE_NAME="${DD_SERVICE_NAME:-mastermind-api}"
DD_TEAM="${DD_TEAM:-mastermind}"
DD_ROLE="${DD_ROLE:-authoritative-vps}"
DD_PYTHON_TRACER_MAJOR="${DD_PYTHON_TRACER_MAJOR:-4}"
MASTERMIND_SERVICE="${MASTERMIND_SERVICE:-mastermind.service}"
MASTERMIND_HEALTH="${MASTERMIND_HEALTH:-http://127.0.0.1:8001/health}"
MASTERMIND_ROOT="${MASTERMIND_ROOT:-/opt/mastermind}"
DD_RELEASE_SHA="${DD_RELEASE_SHA:-}"
APP_DROPIN="/etc/systemd/system/${MASTERMIND_SERVICE}.d/80-datadog.conf"
AGENT_DROPIN="/etc/systemd/system/datadog-agent.service.d/80-mastermind-tags.conf"
JOURNAL_CONF="/etc/datadog-agent/conf.d/journald.d/conf.yaml"
DATADOG_YAML="/etc/datadog-agent/datadog.yaml"
INSTALL_URL="https://install.datadoghq.com/scripts/install_script_agent7.sh"
SSI_PRELOAD_FILE="${SSI_PRELOAD_FILE:-/etc/ld.so.preload}"

fail() { printf 'datadog setup failed: %s\n' "$*" >&2; exit 1; }
log() { printf '[mastermind-datadog] %s\n' "$*"; }
valid_token() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]
}
resolve_release_sha() {
  local value="$DD_RELEASE_SHA"
  if [[ -z "$value" && -r "$MASTERMIND_ROOT/.deployed_git_sha" ]]; then
    value="$(tr -d "\r\n" < "$MASTERMIND_ROOT/.deployed_git_sha")"
  fi
  [[ "$value" =~ ^[0-9a-f]{40}$ ]] || return 1
  printf "%s" "$value"
}
ssi_is_armed() {
  [[ -r "$SSI_PRELOAD_FILE" ]] || return 1
  grep -Eq '(^|[[:space:]])/[^[:space:]]*datadog[^[:space:]]*/launcher\.preload\.so([[:space:]]|$)' "$SSI_PRELOAD_FILE"
}

render_app_dropin() {
  local release_sha=""
  release_sha="$(resolve_release_sha 2>/dev/null || true)"
  cat <<EOF
[Service]
Environment=DD_SERVICE=${DD_SERVICE_NAME}
Environment=DD_ENV=${DD_ENVIRONMENT}
Environment=DD_TRACE_ENABLED=true
Environment=DD_LOGS_INJECTION=true
Environment=DD_RUNTIME_METRICS_ENABLED=true
Environment="DD_TAGS=team:${DD_TEAM} role:${DD_ROLE}"
SyslogIdentifier=${DD_SERVICE_NAME}
EOF
  [[ -z "$release_sha" ]] || printf "Environment=DD_VERSION=%s\n" "$release_sha"
}

render_agent_dropin() {
  cat <<EOF
[Service]
Environment="DD_TAGS=env:${DD_ENVIRONMENT} service:${DD_SERVICE_NAME} team:${DD_TEAM} role:${DD_ROLE}"
EOF
}
render_journald_conf() {
  cat <<EOF
logs:
  - type: journald
    service: ${DD_SERVICE_NAME}
    source: mastermind
    include_units:
      - ${MASTERMIND_SERVICE}
    tags:
      - env:${DD_ENVIRONMENT}
      - team:${DD_TEAM}
      - role:${DD_ROLE}
EOF
}

render_all() {
  printf '%s\n' '--- app-systemd-dropin ---'
  render_app_dropin
  printf '%s\n' '--- datadog-agent-systemd-dropin ---'
  render_agent_dropin
  printf '%s\n' '--- journald-config ---'
  render_journald_conf
}

for value in "$DD_ENVIRONMENT" "$DD_SERVICE_NAME" "$DD_TEAM" "$DD_ROLE"; do
  valid_token "$value" || fail "invalid tag/service token: $value"
done
if [[ "${1:-}" == "--render-only" ]]; then
  render_all
  exit 0
fi
if [[ "${1:-}" == "--check-ssi-only" ]]; then
  if ssi_is_armed; then
    printf '%s\n' armed
    exit 0
  fi
  printf '%s\n' not_armed
  exit 1
fi

[[ "$(id -u)" == "0" ]] || fail "run as root on the authoritative VPS"
[[ -n "${DD_API_KEY:-}" ]] || fail "DD_API_KEY is required in the process environment"
DD_RELEASE_SHA="$(resolve_release_sha)" || fail "valid deployed Git SHA is required at $MASTERMIND_ROOT/.deployed_git_sha"
command -v curl >/dev/null || fail "curl is required"
command -v systemctl >/dev/null || fail "systemd is required"

health_ok() {
  curl -fsS -m 6 "$MASTERMIND_HEALTH" >/dev/null 2>&1
}

health_ok || fail "Mastermind health preflight failed at $MASTERMIND_HEALTH"
SSI_PREEXISTING=0
if ssi_is_armed; then
  SSI_PREEXISTING=1
fi
APP_BACKUP=""
APP_DROPIN_TOUCHED=0
APP_RESTART_ATTEMPTED=0
ROLLBACK_ARMED=1

rollback_application_instrumentation() {
  local rollback_failed=0
  local rollback_healthy=0
  log "rolling back Mastermind Datadog application instrumentation"
  if [[ "$APP_DROPIN_TOUCHED" == "1" ]]; then
    if [[ -n "$APP_BACKUP" && -f "$APP_BACKUP" ]]; then
      cp -a "$APP_BACKUP" "$APP_DROPIN" || rollback_failed=1
    else
      rm -f "$APP_DROPIN" || rollback_failed=1
    fi
    systemctl daemon-reload || rollback_failed=1
  fi
  if [[ "$SSI_PREEXISTING" == "0" ]] && ssi_is_armed; then
    log "removing Single Step Instrumentation introduced by this rollout"
    if command -v dd-host-install >/dev/null 2>&1; then
      dd-host-install --uninstall || rollback_failed=1
    else
      log "dd-host-install unavailable; cannot remove newly introduced SSI"
      rollback_failed=1
    fi
  fi
  if [[ "$SSI_PREEXISTING" == "0" ]] && ssi_is_armed; then
    log "newly introduced SSI is still armed after rollback"
    rollback_failed=1
  fi
  if [[ "$APP_RESTART_ATTEMPTED" == "1" ]]; then
    systemctl restart "$MASTERMIND_SERVICE" || rollback_failed=1
  fi
  for _ in $(seq 1 10); do
    if health_ok; then rollback_healthy=1; break; fi
    sleep 2
  done
  [[ "$rollback_healthy" == "1" ]] || rollback_failed=1
  return "$rollback_failed"
}

rollback_on_exit() {
  local rc="$1"
  trap - EXIT
  if [[ "$rc" != "0" && "$ROLLBACK_ARMED" == "1" ]]; then
    if rollback_application_instrumentation; then
      log "rollback recovered Mastermind health"
    else
      log "rollback did not recover cleanly"
      rc=70
    fi
  fi
  exit "$rc"
}
trap 'rollback_on_exit $?' EXIT

log "installing/updating Agent 7 with Python Single Step Instrumentation"
if ! DD_API_KEY="$DD_API_KEY" \
  DD_SITE="$DD_SITE" \
  DD_APM_INSTRUMENTATION_ENABLED=host \
  DD_APM_INSTRUMENTATION_LIBRARIES="python:${DD_PYTHON_TRACER_MAJOR}" \
  DD_ENV="$DD_ENVIRONMENT" \
  bash -c "$(curl -fsSL "$INSTALL_URL")"; then
  fail "Datadog Agent/SSI installer failed"
fi
if [[ "$SSI_PREEXISTING" == "0" ]] && ! ssi_is_armed; then
  fail "Datadog host SSI did not arm after installer success"
fi

log "enabling host log collection and Mastermind journald intake"
if grep -Eq '^[[:space:]]*logs_enabled:' "$DATADOG_YAML"; then
  sed -i -E 's/^[[:space:]]*logs_enabled:.*/logs_enabled: true/' "$DATADOG_YAML"
else
  printf '\nlogs_enabled: true\n' >> "$DATADOG_YAML"
fi

install -d -m 0755 "$(dirname "$JOURNAL_CONF")"
render_journald_conf > "$JOURNAL_CONF"
chmod 0644 "$JOURNAL_CONF"
usermod -a -G systemd-journal dd-agent

install -d -m 0755 "$(dirname "$AGENT_DROPIN")"
render_agent_dropin > "$AGENT_DROPIN"
chmod 0644 "$AGENT_DROPIN"

log "reloading systemd and restarting Datadog Agent"
systemctl daemon-reload
systemctl restart datadog-agent
systemctl is-active --quiet datadog-agent || fail "datadog-agent did not become active"
datadog-agent configcheck >/dev/null
datadog-agent status >/dev/null

install -d -m 0755 "$(dirname "$APP_DROPIN")"
if [[ -f "$APP_DROPIN" ]]; then
  APP_BACKUP="$(mktemp /tmp/mastermind-datadog-app-dropin.XXXXXX)"
  cp -a "$APP_DROPIN" "$APP_BACKUP"
fi
APP_DROPIN_TOUCHED=1
render_app_dropin > "$APP_DROPIN"
chmod 0644 "$APP_DROPIN"
systemctl daemon-reload

log "restarting ${MASTERMIND_SERVICE} so SSI can instrument Python"
APP_RESTART_ATTEMPTED=1
systemctl restart "$MASTERMIND_SERVICE" || fail "Mastermind restart failed after Datadog instrumentation"

APP_HEALTHY=0
for _ in $(seq 1 20); do
  if health_ok; then APP_HEALTHY=1; break; fi
  sleep 2
done
[[ "$APP_HEALTHY" == "1" ]] || fail "Mastermind health did not recover after Datadog instrumentation"

[[ -z "$APP_BACKUP" ]] || rm -f "$APP_BACKUP"
ROLLBACK_ARMED=0
trap - EXIT
log "local setup proof passed"
printf 'MASTERMIND_DATADOG_SETUP_OK service=%s env=%s unit=%s\n' \
  "$DD_SERVICE_NAME" "$DD_ENVIRONMENT" "$MASTERMIND_SERVICE"
printf '%s\n' 'Verify external intake from Datadog before declaring PROVEN_LIVE.'
