#!/usr/bin/env bash
# Simple wrapper to convert a MrSID file to GeoJPEG inside the container.
# Usage: decode_sid.sh /path/to/input.sid

sid=$1
if [ -z "$sid" ]; then
    echo "Usage: decode_sid.sh <file.sid>"
    exit 1
fi

jpg="${sid%.sid}.jpg"

mrsidgeodecode -i "$sid" -o temp.tif -of tifg -wf

gdal_translate temp.tif "$jpg" -of JPEG -co WORLDFILE=YES -co QUALITY=90 -co TILED=YES

rm temp.tif

echo "Finished -> $jpg (+ .jgw)"
