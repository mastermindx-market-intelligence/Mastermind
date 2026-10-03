#!/bin/bash
# Forced-command SSH relay for mini-hosted Codex release requests.
# The SSH key grants only this grammar; the Executive privileged broker owns effects.
set -euo pipefail
umask 077

MMX_ADMIN="/Library/Application Support/MastermindExecutive/bin/mmx-admin"
COMMAND="${SSH_ORIGINAL_COMMAND:-}"

[ "$#" -eq 1 ] || { echo "release relay identity missing" >&2; exit 64; }
LABEL="$1"
[[ "$LABEL" =~ ^mini[1-9][0-9]*$ ]] || { echo "release relay identity invalid" >&2; exit 64; }
[ -x "$MMX_ADMIN" ] || { echo "release relay unavailable" >&2; exit 69; }

if [ "$COMMAND" = "preflight" ]; then
  request_id="$LABEL-relay-preflight"
  set +e
  "$MMX_ADMIN" status --request-id "$request_id" >/dev/null
  rc=$?
  set -e
  case "$rc" in
    0|4) printf 'READY %s\n' "$LABEL"; exit 0 ;;
    75) exit 75 ;;
    *) exit 69 ;;
  esac
fi
if [[ "$COMMAND" =~ ^status[[:space:]]([A-Za-z0-9][A-Za-z0-9._-]{2,63})$ ]]; then
  request_id="${BASH_REMATCH[1]}"
  [[ "$request_id" == "$LABEL-"* ]] || { echo "release relay request identity mismatch" >&2; exit 64; }
  exec "$MMX_ADMIN" status --request-id "$request_id"
fi

if [[ "$COMMAND" =~ ^deploy[[:space:]]([0-9a-f]{40})[[:space:]]([A-Za-z0-9][A-Za-z0-9._-]{2,63})$ ]]; then
  commit_sha="${BASH_REMATCH[1]}"
  request_id="${BASH_REMATCH[2]}"
  [[ "$request_id" == "$LABEL-"* ]] || { echo "release relay request identity mismatch" >&2; exit 64; }
  exec "$MMX_ADMIN" executive.vps.deploy_mastermind --commit-sha "$commit_sha" --request-id "$request_id"
fi

echo "release relay refused command" >&2
exit 64
