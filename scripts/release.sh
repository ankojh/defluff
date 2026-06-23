#!/usr/bin/env bash
set -euo pipefail

# One command to ship a new build: build the DMG and publish it as a GitHub
# Release so people can download it. Usage:
#   ./scripts/release.sh            # tag from the app version (e.g. v0.1.0)
#   ./scripts/release.sh v0.2.0     # explicit tag
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMG_PATH="$ROOT_DIR/dist/Defluff.dmg"
INFO_PLIST="$ROOT_DIR/macos/DefluffMac/AppBundle/Info.plist"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    APP_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$INFO_PLIST")"
    VERSION="v$APP_VERSION"
fi

# 1. Build the DMG.
"$ROOT_DIR/scripts/build-dmg.sh"

# 2. Make sure the GitHub CLI is available and authenticated.
if ! command -v gh >/dev/null 2>&1; then
    echo "Installing GitHub CLI..."
    brew install gh
fi
if ! gh auth status >/dev/null 2>&1; then
    echo "Sign in to GitHub first:"
    gh auth login
fi

# 3. Publish (create the release, or replace the asset if the tag already exists).
NOTES="Defluff $VERSION — drag-drop installer.

Download Defluff.dmg, open it, and drag Defluff to Applications. First launch
sets everything up automatically. macOS will block the unsigned app once — open
**System Settings -> Privacy & Security -> Open Anyway**, or run:
\`xattr -dr com.apple.quarantine /Applications/Defluff.app\`"

if gh release view "$VERSION" >/dev/null 2>&1; then
    echo "Release $VERSION exists; updating the asset..."
    gh release upload "$VERSION" "$DMG_PATH" --clobber
else
    gh release create "$VERSION" "$DMG_PATH" --title "Defluff $VERSION" --notes "$NOTES"
fi

echo "Published $VERSION."
gh release view "$VERSION" --web >/dev/null 2>&1 || true
