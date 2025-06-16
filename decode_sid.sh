#!/usr/bin/env bash
# Convert a MrSID file to GeoJPEG (+ world-file) using GDAL alone.
# Usage:  decode_sid.sh  /absolute/or/relative/path/to/file.sid
set -e

sid=$1
if [ -z "$sid" ]; then
    echo "Usage: decode_sid.sh <file.sid>"
    exit 1
fi

base="${sid%.sid}"
jpg="${base}.jpg"

echo "Converting $sid → $jpg …"
gdal_translate "$sid" "$jpg" \
    -of JPEG \
    -co QUALITY=90 \
    -co WORLDFILE=YES \
    -co TILED=YES

echo "✓  Finished  ($jpg + $(basename "$jpg" .jpg).jgw)"
