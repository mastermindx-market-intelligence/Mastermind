#!/bin/bash
# gb2-fix-1632: works for every Orbita + Chrome window now (cjs.sh routes through mjs.sh by PID). Backup .bak-gb2fix-1632
# jallow.sh WINID "Exact title" -> click the card's "Always allow" button (Chris t13u/t24u: always click Always allow).
# Fallback: if no Always allow button, open Approval options and pick "Always allow", else "for this conversation".
ttl=$(python3 -c "import sys,json; print(json.dumps(sys.argv[1]))" "$2")
cat > /tmp/ja0.js <<J
(function(){if(document.title!==$ttl)return 'TITLE_MISMATCH';var vis=e=>{var r=e.getBoundingClientRect();return r.width>0&&r.height>0};var b=[...document.querySelectorAll('main button')].filter(vis).find(x=>/^always allow$/i.test(x.innerText.trim()));if(!b)return 'NO_ALWAYS';var o={bubbles:true,cancelable:true,view:window,button:0,pointerType:'mouse'};['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>b.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o)));return 'PICKED Always allow';})()
J
r=$(~/gwcap/cjs.sh $1 /tmp/ja0.js); echo "$r"
case "$r" in *PICKED*|*TITLE_MISMATCH*) exit 0;; esac
cat > /tmp/ja1.js <<J
(function(){if(document.title!==$ttl)return 'TITLE_MISMATCH';var vis=e=>{var r=e.getBoundingClientRect();return r.width>0&&r.height>0};var b=[...document.querySelectorAll('main button')].filter(vis).find(x=>x.getAttribute('aria-label')==='Approval options');if(!b)return 'NO_MENU';var o={bubbles:true,cancelable:true,view:window,button:0,pointerType:'mouse'};['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>b.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o)));return 'OPENED';})()
J
~/gwcap/cjs.sh $1 /tmp/ja1.js; sleep 1
cat > /tmp/ja2.js <<J
(function(){var it=[...document.querySelectorAll('[role=menuitem],[role=menuitemradio],[role=option]')];var names=it.map(x=>x.innerText.trim());var pick=it.find(x=>/always allow/i.test(x.innerText))||it.find(x=>/this conversation/i.test(x.innerText));if(!pick)return 'NOPICK '+JSON.stringify(names);var o={bubbles:true,cancelable:true,view:window,button:0};['pointerdown','mousedown','pointerup','mouseup','click'].forEach(t=>pick.dispatchEvent(t.startsWith('pointer')?new PointerEvent(t,o):new MouseEvent(t,o)));return 'PICKED '+pick.innerText.trim()+' of '+JSON.stringify(names);})()
J
~/gwcap/cjs.sh $1 /tmp/ja2.js
