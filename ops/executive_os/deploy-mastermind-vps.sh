#!/bin/bash
# Closed privileged carrier for exact-origin/master Mastermind VPS releases.
# Caller selects only one 40-hex commit. Host, key, paths and deploy semantics are fixed.
set -euo pipefail
umask 077

usage() {
  echo "usage: deploy-mastermind-vps.sh --commit-sha <40-hex>" >&2
  exit 64
}

[ "$#" -eq 2 ] && [ "$1" = "--commit-sha" ] || usage
TARGET_SHA="$2"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || usage
[ "$EUID" -eq 0 ] || { echo "root broker identity required" >&2; exit 65; }

RELEASE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
case "$RELEASE_ROOT" in
  "/Library/Application Support/MastermindExecutive/releases/"????????????????????????????????????????) ;;
  *) echo "installed Executive release root required" >&2; exit 65 ;;
esac

REMOTE="https://github.com/mastermindx-market-intelligence/Mastermind.git"
BASE_BRANCH="master"
SOURCE_REPO="/Users/chriswong/Documents/GitHub/Mastermind"
BOXHOST="root@146.190.142.17"
DPATH="/opt/mastermind"
KEY="/Users/chriswong/.ssh/macro_dashboard_deploy_v2"
KNOWN_HOSTS="/Users/chriswong/.ssh/known_hosts"
HEALTH="http://127.0.0.1:8001/health"
for tool in /usr/bin/git /usr/bin/tar /usr/bin/ssh /usr/bin/cmp /usr/bin/mktemp /usr/bin/awk /usr/bin/stat /usr/bin/sudo /usr/bin/env /bin/bash; do
  [ -x "$tool" ] || { echo "required release tool unavailable: $tool" >&2; exit 65; }
done
[ -f "$KEY" ] && [ ! -L "$KEY" ] || { echo "fixed VPS key unavailable" >&2; exit 65; }
[ "$(/usr/bin/stat -f '%Su:%Lp:%l' "$KEY")" = "chriswong:600:1" ] || {
  echo "fixed VPS key metadata invalid" >&2
  exit 65
}
[ -f "$KNOWN_HOSTS" ] && [ ! -L "$KNOWN_HOSTS" ] || {
  echo "fixed known_hosts unavailable" >&2
  exit 65
}
KNOWN_META="$(/usr/bin/stat -f '%Su:%Lp:%l' "$KNOWN_HOSTS")"
case "$KNOWN_META" in
  chriswong:600:1|chriswong:644:1) ;;
  *) echo "fixed known_hosts metadata invalid" >&2; exit 65 ;;
esac

[ -d "$SOURCE_REPO/.git" ] && [ ! -L "$SOURCE_REPO" ] && [ ! -L "$SOURCE_REPO/.git" ] || {
  echo "fixed M2 source repository unavailable" >&2
  exit 65
}
[ "$(/usr/bin/stat -f '%Su' "$SOURCE_REPO")" = "chriswong" ] || {
  echo "fixed M2 source repository owner invalid" >&2
  exit 65
}
GIT_OWNER=(
  /usr/bin/sudo -H -u chriswong
  /usr/bin/env GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false
  /usr/bin/git -C "$SOURCE_REPO" -c core.hooksPath=/dev/null
)
SSH=(/usr/bin/ssh -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes
  -o ConnectTimeout=20 -o "UserKnownHostsFile=$KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
remote_marker() {
  "${SSH[@]}" "$BOXHOST" "cat '$DPATH/.deployed_git_sha' 2>/dev/null || true" 2>/dev/null || true
}
remote_health_for() {
  local sha="$1"
  "${SSH[@]}" "$BOXHOST" "body=\$(curl -fsS -m 6 '$HEALTH') &&
    printf '%s' \"\$body\" | grep -Eq '\"reasoning_policy_ok\"[[:space:]]*:[[:space:]]*true' &&
    printf '%s' \"\$body\" | grep -Eq '\"scheduled_runtime_ok\"[[:space:]]*:[[:space:]]*true' &&
    printf '%s' \"\$body\" | grep -Eq '\"commit\"[[:space:]]*:[[:space:]]*\"$sha\"'" >/dev/null 2>&1
}
TMP_ROOT="$(/usr/bin/mktemp -d /private/tmp/mmx-vps-release.XXXXXX)"
cleanup() {
  case "$TMP_ROOT" in
    /private/tmp/mmx-vps-release.*) /bin/rm -rf -- "$TMP_ROOT" ;;
  esac
}
trap cleanup EXIT INT TERM HUP

"${GIT_OWNER[@]}" fetch -q --no-tags --force "$REMOTE" \
  "refs/heads/$BASE_BRANCH:refs/remotes/mmx-release/$BASE_BRANCH"
REMOTE_SHA="$("${GIT_OWNER[@]}" rev-parse "refs/remotes/mmx-release/$BASE_BRANCH^{commit}")"
[[ "$REMOTE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "remote master identity unavailable" >&2; exit 65; }
[ "$REMOTE_SHA" = "$TARGET_SHA" ] || {
  echo "refusing deploy: requested commit is not current origin/master" >&2
  exit 65
}

/bin/mkdir "$TMP_ROOT/stage"
"${GIT_OWNER[@]}" archive "$TARGET_SHA" | /usr/bin/tar -xf - -C "$TMP_ROOT/stage"
INSTALLED_DEPLOY="$RELEASE_ROOT/scripts/deploy_code_to_vps.sh"
TARGET_DEPLOY="$TMP_ROOT/stage/scripts/deploy_code_to_vps.sh"
[ -x "$INSTALLED_DEPLOY" ] && [ -f "$TARGET_DEPLOY" ] || {
  echo "trusted deployment implementation unavailable" >&2
  exit 65
}
/usr/bin/cmp -s "$INSTALLED_DEPLOY" "$TARGET_DEPLOY" || {
  echo "target deployment semantics differ from installed trusted executor" >&2
  exit 65
}

"${GIT_OWNER[@]}" fetch -q --no-tags --force "$REMOTE" \
  "refs/heads/$BASE_BRANCH:refs/remotes/mmx-release/$BASE_BRANCH"
REMOTE_SHA_BEFORE_EFFECT="$("${GIT_OWNER[@]}" rev-parse "refs/remotes/mmx-release/$BASE_BRANCH^{commit}")"
[ "$REMOTE_SHA_BEFORE_EFFECT" = "$TARGET_SHA" ] || {
  echo "origin/master moved before the production effect boundary" >&2
  exit 65
}

PREVIOUS_SHA="$(remote_marker)"
if [[ ! "$PREVIOUS_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "current production release marker is unavailable; refusing before effect" >&2
  exit 65
fi
DEPLOY_LOG="$TMP_ROOT/deploy.log"
set +e
MASTERMIND_DEPLOY_SOURCE="$TMP_ROOT/stage/" MASTERMIND_DEPLOY_EXPECT_SHA="$TARGET_SHA" MASTERMIND_VPS_HOST="$BOXHOST" MASTERMIND_VPS_PATH="$DPATH" MASTERMIND_VPS_KEY="$KEY" MASTERMIND_VPS_KNOWN_HOSTS="$KNOWN_HOSTS" MASTERMIND_DEPLOY_LOG="$DEPLOY_LOG"   /bin/bash "$INSTALLED_DEPLOY" >"$TMP_ROOT/stdout.log" 2>"$TMP_ROOT/stderr.log"
DEPLOY_RC=$?
set -e
FINAL_SHA="$(remote_marker)"
if [ "$DEPLOY_RC" -eq 0 ]; then
  if [ "$FINAL_SHA" = "$TARGET_SHA" ] && remote_health_for "$TARGET_SHA"; then
    printf 'DEPLOYED %s\n' "$TARGET_SHA"
    exit 0
  fi
  echo "deployment returned success but final production state is unproven" >&2
  exit 75
fi

if [ -n "$PREVIOUS_SHA" ] && [ "$FINAL_SHA" = "$PREVIOUS_SHA" ] && remote_health_for "$PREVIOUS_SHA"; then
  echo "deployment failed and rollback to prior healthy release is proven" >&2
  /usr/bin/tail -n 20 "$TMP_ROOT/stderr.log" >&2 || true
  exit 1
fi

echo "deployment failed and final production effect is uncertain" >&2
/usr/bin/tail -n 20 "$TMP_ROOT/stderr.log" >&2 || true
exit 75
