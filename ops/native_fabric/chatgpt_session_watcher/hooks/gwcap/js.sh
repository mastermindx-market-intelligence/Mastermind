#!/bin/bash
# gb2-fix-1632: works for every Orbita + Chrome window now (cjs.sh routes through mjs.sh by PID). Backup .bak-gb2fix-1632
# js.sh WINID jsfile -> pretty status
~/gwcap/cjs.sh $1 $2 | python3 -c 'import json,sys
d=json.loads(sys.stdin.read())
print("TITLE:",d["t"],"BTN:",d["btn"],"FLAGS:",d["flags"])
for s in d["side"]:
  if "::  ::" not in s or "SPIN" in s: print(" ",s)
print("TAIL:",d["tail"])'
