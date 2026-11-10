#!/bin/sh
set -eu
HOME_DIR="$HOME"
ROOT="$HOME_DIR/.t3/tools/adaptive_compaction"
LABEL="com.mastermind.t3.adaptive-compaction"
PLIST="$HOME_DIR/Library/LaunchAgents/$LABEL.plist"
PYTHON="$(command -v python3)"
test -x "$PYTHON"
test -f "$ROOT/compaction.py"
mkdir -p "$HOME_DIR/Library/LaunchAgents"
chmod 700 "$ROOT"
touch "$ROOT/stdout.log" "$ROOT/stderr.log"
chmod 600 "$ROOT/stdout.log" "$ROOT/stderr.log"
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  echo "ERROR: existing launchd job; inspect before replacement" >&2
  exit 1
fi
if test -e "$PLIST"; then
  echo "ERROR: existing plist path; inspect before replacement" >&2
  exit 1
fi
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
 <key>Label</key><string>$LABEL</string>
 <key>ProgramArguments</key>
 <array><string>$PYTHON</string><string>$ROOT/compaction.py</string><string>--apply</string></array>
 <key>StartInterval</key><integer>300</integer>
 <key>RunAtLoad</key><true/>
 <key>ProcessType</key><string>Background</string>
 <key>Nice</key><integer>10</integer>
 <key>LowPriorityIO</key><true/>
 <key>StandardOutPath</key><string>$ROOT/stdout.log</string>
 <key>StandardErrorPath</key><string>$ROOT/stderr.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
plutil -lint "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" | head -n 14