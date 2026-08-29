#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd -P)"
runtime_root="${1:-/Volumes/Mastermind/worker-browser-b1/runtime}"
cache_root="${2:-/Volumes/Mastermind/npm-cache-worker-browser-b1}"

case "$runtime_root" in
  /Volumes/Mastermind/*) ;;
  *) echo "refusing runtime root outside /Volumes/Mastermind" >&2; exit 64 ;;
esac
case "$cache_root" in
  /Volumes/Mastermind/*) ;;
  *) echo "refusing npm cache outside /Volumes/Mastermind" >&2; exit 64 ;;
esac

/usr/bin/install -d -m 0700 "$runtime_root" "$runtime_root/home" "$cache_root"
/usr/bin/install -m 0600 \
  "$repo_root/integrations/worker_browser_runtime/package.json" \
  "$runtime_root/package.json"
/usr/bin/install -m 0600 \
  "$repo_root/integrations/worker_browser_runtime/package-lock.json" \
  "$runtime_root/package-lock.json"

env \
  HOME="$runtime_root/home" \
  npm ci \
    --prefix "$runtime_root" \
    --cache "$cache_root" \
    --ignore-scripts \
    --no-audit \
    --no-fund

version="$($runtime_root/node_modules/.bin/playwright-mcp --version)"
if [ "$version" != "Version 0.0.79" ]; then
  echo "refusing unexpected Playwright MCP version: $version" >&2
  exit 65
fi
echo "WORKER_BROWSER_B1_RUNTIME_READY package=@playwright/mcp version=0.0.79 root=$runtime_root"
