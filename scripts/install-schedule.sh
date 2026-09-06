#!/usr/bin/env bash
# Register the morning sync with launchd (macOS).
#
# Runs daily at 08:30 — before the 09:00 check-in, so the numbers are already
# in Notion when the coach reads them. launchd also fires a missed run once the
# laptop wakes, so a closed lid at 08:30 doesn't skip the day.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.biometrics.sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HOUR="${SYNC_HOUR:-8}"
MINUTE="${SYNC_MINUTE:-30}"

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "No virtualenv at $ROOT/.venv — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

chmod +x "$ROOT/scripts/sync.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$ROOT/scripts/sync.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$ROOT/logs/sync.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/logs/sync.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLISTEOF

# bootout first so re-running this picks up an edited schedule.
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"

echo "Scheduled $LABEL daily at $(printf '%02d:%02d' "$HOUR" "$MINUTE")."
echo "  run now : launchctl kickstart -p gui/$UID/$LABEL"
echo "  logs    : tail -f $ROOT/logs/sync.log"
echo "  remove  : launchctl bootout gui/$UID/$LABEL && rm $PLIST"
