#!/usr/bin/env bash
# Runs the add-on's automatic tests without a real TRELLIS.2 (a fake one stands in).
#
#   pip install bpy        # Blender as a Python module (needs the Python version bpy is built for)
#   bash tests/run_tests.sh
#
# Everything is written into tests/_work (deleted and re-made on each run).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
W="${I23D_TEST_WORK:-$HERE/_work}"
export I23D_TEST_WORK="$W"
PY="${PYTHON:-python3}"

rm -rf "$W"; mkdir -p "$W/fake_trellis/.venv/bin"
cp "$HERE/fixtures/fake_trellis/generate.py" "$W/fake_trellis/"
ln -s "$(command -v "$PY")" "$W/fake_trellis/.venv/bin/python"   # the add-on expects .venv/bin/python
cp "$HERE/fixtures/brown_photo.png" "$W/picture.png"

echo "== 1. Runner (no Blender needed)"
"$PY" "$HERE/make_messy.py" "$W/messy.glb" >/dev/null       # a deliberately messy "AI" model
"$PY" "$HERE/test_runner.py" "$W/fake_trellis"

echo "== 2. Add-on inside Blender (bpy)"
for t in test_ui_bpy test_quality_bpy test_addon_bpy test_colours_bpy; do
  echo "-- $t"
  "$PY" "$HERE/$t.py"
done
echo
echo "ALL TESTS PASSED"
