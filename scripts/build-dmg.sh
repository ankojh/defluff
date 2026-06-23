#!/usr/bin/env bash
set -euo pipefail

# Build a drag-drop Defluff.dmg: compile the SwiftUI app, stage the Python
# backend + installer scripts inside its Resources so it can bootstrap itself on
# first launch, ad-hoc codesign it, and pack it into a compressed disk image.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/macos/DefluffMac"
APP_DIR="$PACKAGE_DIR/.build/app/Defluff.app"
RESOURCES_DIR="$APP_DIR/Contents/Resources"
DIST_DIR="$ROOT_DIR/dist"
DMG_PATH="$DIST_DIR/Defluff.dmg"
STAGE_DIR="$ROOT_DIR/.build/dmg-stage"

# 1. Build Defluff.app (icons, Info.plist, binary).
"$ROOT_DIR/scripts/build-macos-app.sh" >/dev/null

# 2. Stage the backend source so the app can install it on first run.
echo "Staging backend + installer into the app bundle..."
rsync -a --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '*.egg-info' \
    --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude 'tests' \
    "$ROOT_DIR/backend/" "$RESOURCES_DIR/backend/"

for s in bootstrap.sh run-backend.sh start-backend-service.sh \
         stop-backend-service.sh setup-local-db.sh uninstall.sh; do
    cp "$ROOT_DIR/scripts/$s" "$RESOURCES_DIR/$s"
    chmod +x "$RESOURCES_DIR/$s"
done
cp "$ROOT_DIR/.env.example" "$RESOURCES_DIR/.env.example"

# 3. Ad-hoc codesign (seals the bundle after staging resources). Without a paid
#    Developer ID, other Macs show Gatekeeper "unidentified developer" once —
#    recipients right-click -> Open. See README.
echo "Codesigning (ad-hoc)..."
codesign --force --deep --sign - "$APP_DIR"

# 4. Pack into a drag-drop dmg with an /Applications shortcut.
echo "Building disk image..."
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR" "$DIST_DIR"
cp -R "$APP_DIR" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

rm -f "$DMG_PATH"
hdiutil create \
    -volname "Defluff" \
    -srcfolder "$STAGE_DIR" \
    -fs HFS+ \
    -format UDZO \
    -ov \
    "$DMG_PATH" >/dev/null

rm -rf "$STAGE_DIR"
echo "Built: $DMG_PATH"
