#!/bin/zsh
# usage: gclick.sh PID WIN GX GY
for i in {1..20}; do idle=$(ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print int($NF/1000000000); exit}'); [ $idle -ge 4 ] && break; sleep 1; done
[ $idle -ge 4 ] || { echo "NO_IDLE_GAP"; exit 1; }
peekaboo window focus --app PID:$1 --window-id $2 --no-remote >/dev/null 2>&1
sleep 0.5
peekaboo click --at $3,$4 --global --foreground --input-strategy synthOnly --no-remote >/dev/null 2>&1 && echo "clicked $3,$4"
