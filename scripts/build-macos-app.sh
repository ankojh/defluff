#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/macos/DefluffMac"
APP_NAME="Defluff"
APP_DIR="$PACKAGE_DIR/.build/app/$APP_NAME.app"
LEGACY_APP_DIR="$PACKAGE_DIR/.build/app/DefluffMac.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
ICON_SOURCE="$PACKAGE_DIR/AppBundle/Assets/DefluffIcon.png"
ICONSET_DIR="$PACKAGE_DIR/.build/DefluffIcon.iconset"

swift build --package-path "$PACKAGE_DIR"

BIN_DIR="$(swift build --package-path "$PACKAGE_DIR" --show-bin-path)"

rm -rf "$APP_DIR" "$LEGACY_APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$PACKAGE_DIR/AppBundle/Info.plist" "$CONTENTS_DIR/Info.plist"
cp "$BIN_DIR/$APP_NAME" "$MACOS_DIR/$APP_NAME"
chmod +x "$MACOS_DIR/$APP_NAME"

# In-app logo art (loaded at runtime via Bundle.main).
cp "$PACKAGE_DIR/AppBundle/Assets/DefluffIcon.png" "$RESOURCES_DIR/DefluffIcon.png"
cp "$PACKAGE_DIR/AppBundle/Assets/DefluffIcon-light.png" "$RESOURCES_DIR/DefluffIcon-light.png"

if [[ -f "$ICON_SOURCE" ]]; then
    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"

    sips -z 16 16 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
    sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
    sips -z 64 64 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
    sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
    sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
    sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null

    iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/DefluffIcon.icns"
fi

echo "$APP_DIR"
