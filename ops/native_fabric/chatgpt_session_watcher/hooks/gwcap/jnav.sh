#!/bin/bash
# gb2-fix-1632: works for every Orbita + Chrome window now (cjs.sh routes through mjs.sh by PID). Backup .bak-gb2fix-1632
# jnav.sh WINID "Sidebar title" -> click sidebar row via JS, wait, print status
ttl=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$2")
cat > /tmp/jnav.js <<J
(function(){var a=[...document.querySelectorAll('nav a[href*="/c/"]')].find(x=>x.getAttribute('aria-label')===$ttl);if(!a)return 'NOLINK';var o={bubbles:true,cancelable:true,view:window,button:0};['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>a.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o)));return 'clicked';})()
J
~/gwcap/cjs.sh $1 /tmp/jnav.js; sleep ${3:-8}; ~/gwcap/js.sh $1 $HOME/gwcap/side.js | grep -v '^  '
