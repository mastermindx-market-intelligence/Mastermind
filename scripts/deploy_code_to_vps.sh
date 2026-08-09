#!/usr/bin/env bash
# Transactional deployment of a clean Git archive to the authoritative VPS.
# Call through deploy_from_git.sh; arbitrary local working trees are refused.
set -euo pipefail

LOG="${MASTERMIND_DEPLOY_LOG:-/tmp/mm_vps_deploy.log}"
log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG"
}

case "$(printf '%s' "${MASTERMIND_SERVE_ONLY:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) log "deploy refused: serve-only mode"; exit 2 ;;
esac
if [[ "${MASTERMIND_VPS_CODE_DEPLOY:-1}" == "0" ]]; then
  log "deploy refused: MASTERMIND_VPS_CODE_DEPLOY=0"
  exit 2
fi

SRC="${MASTERMIND_DEPLOY_SOURCE:-}"
EXPECTED_SHA="${MASTERMIND_DEPLOY_EXPECT_SHA:-}"
if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "Use scripts/deploy_from_git.sh; a clean archive source is required." >&2
  exit 2
fi
if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full merged git SHA is required for deployment provenance." >&2
  exit 2
fi
SRC="${SRC%/}/"

BOXHOST="${MASTERMIND_VPS_HOST:-root@146.190.142.17}"
DPATH="${MASTERMIND_VPS_PATH:-/opt/mastermind}"
KEY="${MASTERMIND_VPS_KEY:-/Users/chriswong/.ssh/macro_dashboard_deploy_v2}"
SVC="${MASTERMIND_VPS_SERVICE:-mastermind.service}"
HEALTH="${MASTERMIND_VPS_HEALTH:-http://127.0.0.1:8001/health}"

if [[ ! -f "$KEY" ]]; then
  log "deploy failed: SSH key is missing at $KEY"
  exit 1
fi

SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20)
RSYNC_SSH="ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=20"

# HTTP 200 alone is insufficient for a reasoning service: a stale environment could boot cleanly
# while silently reverting every nightly portfolio to a direct Claude backend, or an old process
# could answer after a failed restart. The open health contract exposes only non-secret policy and
# release state, so require both the Codex-first waterfall and the exact expected commit. Codex
# availability itself remains observable but is not a hard gate because the shared Claude OAuth rung
# is the authorized capacity fallback. Passing an empty SHA is reserved for verifying a rollback
# from a legacy deployment that had no valid provenance marker.
probe_health() {
  local expected_sha="${1:-}"
  local require_scheduler="${2:-1}"
  local probe
  if [[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]]; then
    probe="$("${SSH[@]}" "$BOXHOST" \
      "body=\$(curl -fsS -m 6 '$HEALTH') &&
       printf '%s' \"\$body\" | grep -Eq '\"reasoning_policy_ok\"[[:space:]]*:[[:space:]]*true' &&
       { [ '$require_scheduler' != '1' ] || printf '%s' \"\$body\" | grep -Eq '\"scheduled_runtime_ok\"[[:space:]]*:[[:space:]]*true'; } &&
       printf '%s' \"\$body\" | grep -Eq '\"commit\"[[:space:]]*:[[:space:]]*\"$expected_sha\"' &&
       printf '200'" 2>/dev/null || true)"
  else
    probe="$("${SSH[@]}" "$BOXHOST" \
      "body=\$(curl -fsS -m 6 '$HEALTH') &&
       printf '%s' \"\$body\" | grep -Eq '\"reasoning_policy_ok\"[[:space:]]*:[[:space:]]*true' &&
       { [ '$require_scheduler' != '1' ] || printf '%s' \"\$body\" | grep -Eq '\"scheduled_runtime_ok\"[[:space:]]*:[[:space:]]*true'; } &&
       printf '200'" 2>/dev/null || true)"
  fi
  if [[ "$probe" == "200" ]]; then
    printf '200'
  else
    printf '503'
  fi
}

DIRS="app brain bot portfolio data_layer loop bridge control_plane scripts config ops .claude .codex"
FILES="pyproject.toml DOCTRINE.md README.md AGENTS.md .deployed_git_sha"
EXC=(
  --exclude='.git' --exclude='.github'
  --exclude='.worktrees' --exclude='.venv' --exclude='venv'
  --exclude='data' --exclude='vendor' --exclude='vendor_*'
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo'
  --exclude='node_modules' --exclude='*.sqlite' --exclude='*.sqlite-*'
  --exclude='*.db' --exclude='*.log' --exclude='.DS_Store' --exclude='*.lock'
  --exclude='.pytest_cache' --exclude='.mypy_cache' --exclude='.ruff_cache'
  --exclude='.env' --exclude='.env.*' --exclude='tmp' --exclude='catboost_info'
  --exclude='{_DB}' --exclude='tests' --exclude='.deploy_prev'
  --exclude='.deployed_git_sha'
)

RAW="$(rsync -azn --delete --out-format='%n' -e "$RSYNC_SSH" \
  "${EXC[@]}" "$SRC" "$BOXHOST:$DPATH/")" || {
    log "deploy failed: VPS dry-run/SSH check failed"
    exit 1
  }
CHANGED="$(printf '%s\n' "$RAW" | grep -vE '/$|^$' || true)"
N="$(printf '%s\n' "$CHANGED" | grep -c . || true)"

if [[ "${N:-0}" -eq 0 ]] && [[ "$(probe_health "$EXPECTED_SHA")" == "200" ]]; then
  log "deploy no-op: $EXPECTED_SHA already in sync and healthy"
  exit 0
fi

if [[ "${N:-0}" -eq 0 ]]; then
  log "code is in sync but release attestation or policy is stale; refreshing $EXPECTED_SHA"
else
  log "deploying $EXPECTED_SHA ($N changed path(s))"
fi
printf '%s\n' "$CHANGED" | sed 's/^/    /' | tee -a "$LOG"

PREVIOUS_SHA="$("${SSH[@]}" "$BOXHOST" \
  "cat '$DPATH/.deployed_git_sha' 2>/dev/null || true" 2>/dev/null || true)"
if [[ ! "$PREVIOUS_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  PREVIOUS_SHA=""
fi

"${SSH[@]}" "$BOXHOST" \
  "cd '$DPATH' &&
   rm -rf .deploy_prev &&
   mkdir -p .deploy_prev &&
   for d in $DIRS; do [ ! -e \"\$d\" ] || cp -a \"\$d\" .deploy_prev/; done &&
   for f in $FILES; do [ ! -e \"\$f\" ] || cp -a \"\$f\" .deploy_prev/; done"

# From this point forward the remote release tree is mutable. Every failure—including a partial
# rsync, marker write, or restart transport error—must take the identical bounded restore path.
# Otherwise the next service restart could boot a mixture of old and new code that never reached a
# health probe. The backup directory itself is excluded from rsync, so it survives partial copies.
rollback_release() {
  local reason="$1"
  local restore_status=0
  log "deploy failed: $reason; rolling back"
  if ! "${SSH[@]}" "$BOXHOST" \
    "cd '$DPATH' &&
     restore_failed=0
     for d in $DIRS; do
       if [ -e \".deploy_prev/\$d\" ]; then
         rm -rf \"\$d\" && cp -a \".deploy_prev/\$d\" \"\$d\" || restore_failed=1
       else
         # A directory introduced by the failed release has no previous snapshot. Remove that
         # bounded release path so rolled-back code cannot observe a mismatched agent policy.
         rm -rf \"\$d\" || restore_failed=1
       fi
     done
     for f in $FILES; do
       if [ -e \".deploy_prev/\$f\" ]; then
         cp -a \".deploy_prev/\$f\" \"\$f\" || restore_failed=1
       else
         rm -f \"\$f\" || restore_failed=1
       fi
     done
     systemctl restart '$SVC'
     restart_status=\$?
     [ \"\$restore_failed\" -eq 0 ] && [ \"\$restart_status\" -eq 0 ]"; then
    restore_status=1
    log "rollback transport or restore command failed"
  fi
  sleep 4
  CODE="$(probe_health "$PREVIOUS_SHA" 0)"
  log "rollback complete; health returned $CODE"
  return "$restore_status"
}

fail_release() {
  rollback_release "$1" || true
  exit 1
}

if ! rsync -az --delete --out-format='%n' -e "$RSYNC_SSH" \
  "${EXC[@]}" "$SRC" "$BOXHOST:$DPATH/" >>"$LOG" 2>&1; then
  fail_release "rsync did not complete"
fi

# The application resolves this marker once at startup. Write it before the restart so the
# first health response can attest the exact code archive that was just synchronized.
if ! "${SSH[@]}" "$BOXHOST" \
  "printf '%s\n' '$EXPECTED_SHA' > '$DPATH/.deployed_git_sha'"; then
  fail_release "release marker write failed"
fi
if ! "${SSH[@]}" "$BOXHOST" "systemctl restart '$SVC'"; then
  fail_release "service restart failed"
fi
CODE="000"
for _ in 1 2 3 4 5 6 7 8; do
  sleep 3
  CODE="$(probe_health "$EXPECTED_SHA")"
  [[ "$CODE" == "200" ]] && break
done

if [[ "$CODE" == "200" ]]; then
  log "deploy OK: $SVC healthy at commit $EXPECTED_SHA"
  exit 0
fi

fail_release "health check returned $CODE"
