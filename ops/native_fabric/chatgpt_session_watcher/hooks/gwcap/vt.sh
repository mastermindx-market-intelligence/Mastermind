#!/bin/bash
# gb2-fix-1632: works for every Orbita + Chrome window now (cjs.sh routes through mjs.sh by PID). Backup .bak-gb2fix-1632
# vt.sh WINID "Sidebar title" [wait] -> sidebar nav then read VISIBLE main only (side.js tail can be stale/hidden-pane)
ttl=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$2")
cat > /tmp/vnav.js <<J
(function(){if(document.title===$ttl)return 'already';var a=[...document.querySelectorAll('nav a[href*="/c/"]')].find(x=>x.getAttribute('aria-label')===$ttl);if(!a)return 'NOLINK';var o={bubbles:true,cancelable:true,view:window,button:0};['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>a.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o)));return 'clicked';})()
J
r=$(~/gwcap/cjs.sh $1 /tmp/vnav.js); [ "$r" = clicked ] && sleep ${3:-10}; [ "$r" = NOLINK ] && echo NOLINK
~/gwcap/cjs.sh $1 ~/gwcap/vmain.js
