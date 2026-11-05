#!/bin/bash
# pastev.sh PID WIN sx sy promptfile "Exact window title"  -> gated paste ONLY if window title matches before AND after click
cd ~/gwcap
title(){ peekaboo window list --app PID:$1 --json --no-remote 2>/dev/null | python3 -c "import json,sys
for w in json.load(sys.stdin)['data']['windows']:
  if str(w['window_id'])=='$2': print(w.get('window_title',''))"; }
[ "$(title $1 $2)" = "$6" ] || { echo "TITLE_MISMATCH_BEFORE: $(title $1 $2)"; exit 2; }
./waitidle.sh 240 || exit 1
[ "$(title $1 $2)" = "$6" ] || { echo "TITLE_MISMATCH_GATED: $(title $1 $2)"; exit 2; }
pbpaste > clip_save.txt
./gw.sh click $1 $2 $3 $4; sleep 0.4
fp=$(osascript -e 'tell application "System Events" to get unix id of first process whose frontmost is true')
if [ "$fp" = "$1" ] && [ "$(title $1 $2)" = "$6" ]; then pbcopy < $5; peekaboo press cmd+a --foreground --no-remote >/dev/null 2>&1; peekaboo press cmd+v --foreground --no-remote >/dev/null 2>&1; osascript -e 'tell application "System Events" to key up command'; echo PASTED; else echo "ABORT front=$fp title=$(title $1 $2)"; fi
sleep 0.3; pbcopy < clip_save.txt
