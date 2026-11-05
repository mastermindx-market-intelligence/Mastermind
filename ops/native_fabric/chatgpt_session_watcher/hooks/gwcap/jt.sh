#!/bin/bash
# gb2-fix-1632: works for every Orbita + Chrome window now (cjs.sh routes through mjs.sh by PID). Backup .bak-gb2fix-1632
# jt.sh WINID "Title" [wait] -> nav (if needed) then short status (TAB env honored)
cur=$(~/gwcap/cjs.sh $1 $HOME/gwcap/side.js | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["t"])')
if [ "$cur" != "$2" ]; then ttl=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$2")
cat > /tmp/jnav.js <<J
(function(){var a=[...document.querySelectorAll('nav a[href*="/c/"]')].find(x=>x.getAttribute('aria-label')===$ttl);if(!a)return 'NOLINK';var o={bubbles:true,cancelable:true,view:window,button:0};['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>a.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o)));return 'clicked';})()
J
~/gwcap/cjs.sh $1 /tmp/jnav.js >/dev/null; sleep ${3:-9}; fi
~/gwcap/cjs.sh $1 $HOME/gwcap/side.js | python3 -c 'import json,sys
d=json.loads(sys.stdin.read()); print("TITLE:",d["t"],"BTN:",d["btn"],"FLAGS:",d["flags"]); print("TAIL:",d["tail"][-'${N:-450}':].replace("\n"," | "))'
