#!/usr/bin/env bash
# Packs the Blender add-on into an installable extension zip: dist/image_to_game_asset-<version>.zip
#   bash scripts/build_addon.sh
# Then in Blender: Edit > Preferences > Get Extensions > (top-right menu) > Install from Disk...
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/addon/image_to_game_asset"
VERSION=$(grep -E '^version *= *"' "$SRC/blender_manifest.toml" | head -1 | sed -E 's/.*"(.*)".*/\1/')
OUT="$ROOT/dist/image_to_game_asset-$VERSION.zip"
mkdir -p "$ROOT/dist"; rm -f "$OUT"
cp "$ROOT/addon/README.md" "$SRC/README.md"           # the user guide travels inside the zip
( cd "$SRC" && zip -q -r "$OUT" . -x '__pycache__/*' '*.pyc' '.DS_Store' )
rm -f "$SRC/README.md"
echo "Built: $OUT"
