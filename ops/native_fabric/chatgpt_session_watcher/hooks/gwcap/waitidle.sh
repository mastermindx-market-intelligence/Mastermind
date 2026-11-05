#!/bin/bash
# wait up to $1 seconds for HID idle >= 4s
end=$((SECONDS+${1:-40}))
while [ $SECONDS -lt $end ]; do
  i=$(ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print int($NF/1000000000); exit}')
  if [ "$i" -ge 4 ]; then echo "IDLE_OK $i"; exit 0; fi
  sleep 1
done
echo IDLE_TIMEOUT; exit 1
