# arlcleaner

A small collection of Docker helpers for converting MrSID and GeoTIFF imagery into GeoJPEG files.

## Prerequisites
* Docker installed on the host.
* (Optional) the proprietary MrSID SDK archive if you need to process `.sid` images.  Place the archive in the project root and pass its filename via `--build-arg MRSID_SDK_PATH=<archive>` when building.

## Building the image
```bash
make build
```
The `IMAGE_NAME` variable may be overridden if you want a custom tag:
```bash
make build IMAGE_NAME=mytag
```

## Make targets
The `Makefile` exposes a few convenience commands:

- `make sid-test` – run `sidtest.py` inside the container to verify GDAL and MrSID support.
- `make convert-one` – example rule that converts a single SID file using `decode_sid.sh` (edit the rule or the `SID_FILE` variable to point at your image).
- `make convert-all` – convert every `.sid` in `SID_DIR` to GeoJPEG.
- `make test-image` – execute `image_test.py` which converts all files from the folders defined in `config.py`.

The input and output folders used by `test-image` can be adjusted in `config.py` or overridden by passing variables `SID_IN`, `SID_OUT`, `TIFF_IN` and `TIFF_OUT` when invoking make.

## Configuration
`config.py` defines runtime options such as JPEG quality, tile size for SID images, the number of parallel workers, and whether to enforce a geographic bounding‑box check.  Adjust these settings to match your dataset and hardware.

The conversion helpers attempt to read the input image's spatial reference via `gdalinfo` and any accompanying `.aux.xml` file.  If no EPSG code can be determined, the tools still create a JPEG but only keep it when the resulting bounding box falls inside a reasonable range.

---
After building, run one of the make commands above to start converting imagery.
