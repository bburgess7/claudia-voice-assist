#!/usr/bin/env bash
# Build Claudia.app — a real menu-bar app bundle (visible UI + global hotkey in one), so the
# Accessibility + Microphone prompts attach to "Claudia" and you can double-click / add to Login Items.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$HOME/Applications/Claudia.app"

mkdir -p "$HOME/Applications"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Claudia</string>
  <key>CFBundleDisplayName</key><string>Claudia</string>
  <key>CFBundleIdentifier</key><string>com.ben.claudia</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>Claudia</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSMicrophoneUsageDescription</key><string>Claudia listens when you hold the talk key.</string>
  <key>NSAppleEventsUsageDescription</key><string>Claudia opens apps and controls your Mac on request.</string>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/Claudia" <<LAUNCH
#!/bin/bash
ROOT="$ROOT"
# make sure the voice daemon + sidecars are up
curl -sf http://127.0.0.1:4242/health >/dev/null 2>&1 || (nohup bash "\$ROOT/scripts/start.sh" >/dev/null 2>&1 &)
exec "\$ROOT/.venv-listen/bin/python" "\$ROOT/app/claudia_app.py"
LAUNCH
chmod +x "$APP/Contents/MacOS/Claudia"

# ad-hoc sign so the bundle has a stable identity for permission grants
codesign --force --deep --sign - "$APP" 2>/dev/null || true

echo "✅ Built $APP"
echo "   Open it:  open \"$APP\"   (or double-click it in ~/Applications)"
echo "   First launch: macOS will ask for Microphone + Accessibility — say yes to both."
echo "   Add to Login Items (System Settings → General → Login Items) to have it always on."
