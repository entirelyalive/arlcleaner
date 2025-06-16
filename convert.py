"""Utility functions for converting imagery to GeoJPEG format."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


def _convert_to_jpeg(src: str, dst_dir: str) -> str:
    """Convert *src* raster to JPEG in *dst_dir* using ``gdal_translate``.

    Parameters
    ----------
    src : str
        Path to the input raster file.
    dst_dir : str
        Directory where the output JPEG will be written.

    Returns
    -------
    str
        Path to the generated JPEG file.
    """
    if not shutil.which("gdal_translate"):
        raise RuntimeError("gdal_translate not found in PATH. Is GDAL installed?")

    os.makedirs(dst_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(src))[0]
    dst = os.path.join(dst_dir, base + ".jpg")

    cmd = [
        "gdal_translate",
        src,
        dst,
        "-of",
        "JPEG",
        "-co",
        "QUALITY=90",
        "-co",
        "WORLDFILE=YES",
        "-co",
        "TILED=YES",
    ]

    subprocess.run(cmd, check=True)
    return dst


def _has_mrsid_support() -> bool:
    """Return ``True`` if GDAL has the MrSID driver available."""
    if not shutil.which("gdalinfo"):
        return False
    try:
        formats = subprocess.check_output(
            ["gdalinfo", "--formats"], text=True, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError:
        return False
    return "MrSID" in formats


def process_sid(path: str, output_dir: str) -> str:
    """Process a MrSID image and convert it to GeoJPEG.

    Raises
    ------
    RuntimeError
        If the running GDAL installation lacks MrSID support.
    """
    if not path.lower().endswith(".sid"):
        raise ValueError(f"Expected a .sid file, got: {path}")
    if not _has_mrsid_support():
        raise RuntimeError(
            "GDAL does not have MrSID support. Install the MrSID SDK or use a"
            " build that includes the driver."
        )
    return _convert_to_jpeg(path, output_dir)


def process_tiff(path: str, output_dir: str) -> str:
    """Process a GeoTIFF image and convert it to GeoJPEG."""
    if not (path.lower().endswith(".tif") or path.lower().endswith(".tiff")):
        raise ValueError(f"Expected a .tif/.tiff file, got: {path}")
    return _convert_to_jpeg(path, output_dir)

