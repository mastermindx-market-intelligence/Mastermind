#!/bin/bash
# pool — thin machine-wide wrapper for agent-pools
# Absolute path to kit; one source of truth for all scripts.
# Bash 3.2 compatible.

set -u

KIT_DIR="/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08"
PICK="$KIT_DIR/ext/pick.py"
LEASE_BROKER="$KIT_DIR/ext/lease_broker.py"
SUB="$KIT_DIR/ext/sub.sh"
LEDGER="$KIT_DIR/ext/pool_ledger.py"

usage() {
  echo "usage: pool <run|remote|onboard|hosts|placement|refresh|pick|status|plan|stats|ledger> [args...]" >&2
  echo "  run    <grok|cursor|qwen|minimax|glm|glm-codex|minimax-codex|go-codex|go-claude|oc-free> \"<prompt>\" [cwd] [model]" >&2
  echo "  remote <host|auto> <mode> <packet_file> <remote_cwd> [model] [--out F] [--dry-run]   # R34 remote placement" >&2
  echo "  hosts  <mode> [--seat-ok]        # host eligibility table (R34 remote-first)" >&2
  echo "  pick   <task-class> [--prefer <pool>] [--pool <pool>] [--needs vision] [--subject-pool <pool>]" >&2
  echo "  placement --mode <mode> [--json]  # read-only host/provider/route boundaries" >&2
  echo "  refresh HOST [HOST...]            # bounded selected-host telemetry refresh" >&2
  echo "  onboard HOST [--install-missing] # idempotent CLI setup; authentication and routing stay separate" >&2
  echo "  status" >&2
  echo "  plan   --class <c> --need <n>   # size fan-out from grant_now (R14)" >&2
  echo "  stats  [--class C]              # R22 metrics" >&2
  echo "  ledger outcome <run_id> …       # after-the-fact outcome (R22)" >&2
  exit 2
}

if [ "$#" -lt 1 ]; then
  usage
fi

CMD="$1"; shift

case "$CMD" in
  run)
    POOL="${1:?pool}"; PROMPT="${2:?prompt}"; CWD="${3:-$PWD}"; MODEL="${4:-}"
    exec bash "$SUB" "$POOL" "$PROMPT" "$CWD" "$MODEL" ;;
  remote)
    # R34: place a packet on a remote lanes host (host|auto) via ext/remote_sub.sh
    exec bash "$KIT_DIR/ext/remote_sub.sh" "$@" ;;
  onboard)
    exec python3 "$KIT_DIR/ext/bootstrap_clis.py" "$@" ;;
  hosts)
    # host eligibility table for a lane mode (glm|glm-codex|minimax|minimax-codex|cursor)
    MODE="${1:?mode}"; shift
    exec python3 "$KIT_DIR/ext/host_pick.py" --mode "$MODE" --explain "$@" ;;
  placement)
    # Advisory only; no grant, probe, reservation or process launch.
    exec python3 "$KIT_DIR/ext/placement_view.py" "$@" ;;
  pick)
    exec python3 "$PICK" --task-class "$@" ;;
  refresh)
    [ "$#" -gt 0 ] || { echo "pool refresh requires HOST [HOST...]" >&2; exit 2; }
    REFRESH_ARGS=(--once)
    for host in "$@"; do REFRESH_ARGS+=(--host "$host"); done
    exec bash "$KIT_DIR/ext/host_pull.sh" "${REFRESH_ARGS[@]}" ;;
  status)
    exec python3 "$LEASE_BROKER" status "$@" ;;
  plan)
    exec python3 "$LEASE_BROKER" plan "$@" ;;
  stats)
    exec python3 "$LEDGER" stats "$@" ;;
  ledger)
    exec python3 "$LEDGER" "$@" ;;
  -h|--help)
    usage ;;
  *)
    echo "unknown subcommand: $CMD" >&2
    usage ;;
esac
