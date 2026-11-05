#!/bin/bash
# mjs.sh <session_name|chrome:Profile|auto> <jsfile> [window_id|active]
#  Runs JS in a ChatGPT tab of the exact browser PROCESS via ScriptingBridge (works for every Orbita/Mimic instance,
#  unlike `tell application <path>` which reaches only one). Window ids are re-listed every call. TAB=<1-based> honored.
#  "auto" = find whichever process owns window_id. 20 s guard (kills osascript). gpt_sel.js is prepended (GS.*).
tgt="$1"; jsf="$2"; win="${3:-active}"
mjs_pid(){ # $1 session_name or chrome:Profile -> "pid profile"
 case "$1" in
  chrome:*) p=""; for cand in $(pgrep -x "Google Chrome"); do args=$(ps -p "$cand" -o command= 2>/dev/null); case "$args" in *--type=*|*--headless*) continue;; esac; p=$cand; break; done; echo "$p ${1#chrome:}";;
  *) p=$(ps axo pid=,command= | grep '[m]imic_.*/Chromium.app/Contents/MacOS/Chromium' | grep -v -- '--type=' | grep -F -- "--session_name=$1 " | awk '{print $1; exit}')
     [ -z "$p" ] && p=$(ps axo pid=,command= | grep '[m]imic_.*/Chromium.app/Contents/MacOS/Chromium' | grep -v -- '--type=' | grep -iF -- "--session_name=$1" | awk '{print $1; exit}'); echo "$p ";;
 esac; }
mjs_all(){ ps axo pid=,command= | grep '[m]imic_.*/Chromium.app/Contents/MacOS/Chromium' | grep -v -- '--type=' | awk '{print $1}'; for cand in $(pgrep -x "Google Chrome"); do args=$(ps -p "$cand" -o command= 2>/dev/null); case "$args" in *--type=*|*--headless*) continue;; esac; echo "$cand"; break; done; }

guard(){ out=$(mktemp /tmp/mjs.XXXX); osascript -l JavaScript ~/gwcap/mjs_core.js "$@" >"$out" 2>&1 & op=$!
 for i in $(seq 1 40); do kill -0 $op 2>/dev/null || break; sleep 0.5; done
 if kill -0 $op 2>/dev/null; then kill $op 2>/dev/null; echo "TIMEOUT_20S"; else cat "$out"; fi; rm -f "$out"; }
if [ "$tgt" = auto ]; then
 for p in $(mjs_all); do r=$(guard exec "$p" "" "$win" "$jsf" "${TAB:-}"); case "$r" in NOWIN*|NOAPP*) ;; *) echo "$r"; exit 0;; esac; done
 echo "NOWIN $win in any browser"; exit 3; fi
read pid prof <<<"$(mjs_pid "$tgt")"; [ -z "$pid" ] && { echo "NOPROC $tgt"; exit 3; }
guard exec "$pid" "$prof" "$win" "$jsf" "${TAB:-}"
