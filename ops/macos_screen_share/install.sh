#!/bin/zsh
set -eu
umask 077

ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"
LA_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
BIN="$BIN_DIR/mmx-screen-share"
LABEL="com.mastermind.screen-share-janitor"
PLIST="$LA_DIR/$LABEL.plist"

mkdir -p "$BIN_DIR" "$LA_DIR" "$LOG_DIR"
install -m 700 "$ROOT/mmx-screen-share" "$BIN"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BIN</string>
    <string>reap</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>30</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/mmx-screen-share-janitor.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/mmx-screen-share-janitor.err</string>
</dict>
</plist>
EOF

/bin/zsh -n "$BIN"
/usr/bin/plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl print "gui/$(id -u)/$LABEL" >/dev/null

echo "installed=$BIN"
"$BIN" doctor
