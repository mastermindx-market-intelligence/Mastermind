#!/bin/bash
# cjs.sh WINID jsfile -> run js in active tab (or TAB=<n>) of window WINID in WHICHEVER browser process owns it.
# gb2-fix-1632 (Nov 2 2026): routed through ~/gwcap/mjs.sh (ScriptingBridge by PID, 20 s guard, gpt_sel.js prepended).
# The old APP=/CPID= env vars are ignored now: 'tell application <mimic path>' reached only ONE Orbita instance.
# Previous version: cjs.sh.bak-gb2fix-1632
exec ~/gwcap/mjs.sh auto "$2" "$1"
