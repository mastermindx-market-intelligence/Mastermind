idle(){ echo $(( $(ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF; exit}') / 1000000000 )); }
gate(){ for i in $(seq 1 15); do [ $(idle) -ge 4 ] && return 0; sleep 1; done; echo "NO IDLE GAP"; return 1; }
