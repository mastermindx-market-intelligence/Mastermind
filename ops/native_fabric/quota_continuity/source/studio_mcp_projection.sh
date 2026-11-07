#!/bin/sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
PROVIDER="${1:?provider}"
FIELD="${2:-url}"
TASK="${POOL_TASK_CLASS:-default}"
[ -n "$TASK" ] || TASK=default
READ_URL="${STUDIO_MCP_READ_URL:-https://m2studio.taila6eca1.ts.net/studio-fabric}"
DESIGN_URL="${STUDIO_MCP_DESIGN_URL:-https://m2studio.taila6eca1.ts.net/studio-design}"
OPERATOR_FLAG=""
[ -z "${FABRIC_OPERATOR_CAPABILITY:-}" ] || OPERATOR_FLAG="--operator-delegation"
OUT="$(python3 "$HERE/fabric_client_projection.py" --provider "$PROVIDER" --task-class "$TASK" --read-url "$READ_URL" --design-url "$DESIGN_URL" $OPERATOR_FLAG)" || exit $?
printf '%s' "$OUT" | python3 -c '''
import json,sys
field=sys.argv[1]
d=json.load(sys.stdin)
if field=="url":
    print(d["url"])
elif field=="config":
    print(d["config_text"])
elif field=="route":
    print(d["route"])
elif field=="codex-override":
    print("mcp_servers.mastermindStudio.url="+json.dumps(d["url"], ensure_ascii=True))
else:
    raise SystemExit("STUDIO_MCP_FIELD_REFUSED")
''' "$FIELD"
