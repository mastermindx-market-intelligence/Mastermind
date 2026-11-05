#!/bin/bash
# usage: gw.sh cap PID WID name | gw.sh click PID WID sx sy (sx,sy in 1024-wide capture space)
cmd=$1; pid=$2; wid=$3
b=$(peekaboo window list --app PID:$pid --json --no-remote 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin)
for w in d['data']['windows']:
  if str(w['window_id'])=='$wid': bb=w['bounds']; print(bb['x'],bb['y'],bb['width'],bb['height'])")
read X Y W H <<< "$b"
if [ "$cmd" = cap ]; then
  rm -f /tmp/gw2/$4.png; screencapture -x -o -l $wid /tmp/gw2/$4.png
  sips -Z 1024 /tmp/gw2/$4.png --out ~/gwcap/$4.png >/dev/null; echo "captured $4 bounds $b"
elif [ "$cmd" = click ]; then
  gx=$(python3 -c "print(round($X+$4*$W/1024))"); gy=$(python3 -c "print(round($Y+$5*$W/1024))")
  idle=$(ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF/1000000000; exit}')
  echo "idle=$idle click global $gx,$gy"
  peekaboo window focus --app PID:$pid --window-id $wid --no-remote >/dev/null 2>&1
  peekaboo click --at $gx,$gy --global --foreground --input-strategy synthOnly --no-remote 2>&1 | tail -1
  date +%T >> ~/gwcap/lastinput
fi
