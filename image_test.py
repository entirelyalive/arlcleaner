"""Run bulk conversion tests for SID and TIFF imagery."""

from __future__ import annotations

import os
from typing import Iterable

import config
from convert import process_sid, process_tiff


def _iter_files(folder: str, extensions: Iterable[str]):
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and any(name.lower().endswith(ext) for ext in extensions):
            yield path


def main() -> None:
    # Process SID files
    for src in _iter_files(config.SID_INPUT, [".sid"]):
        print(f"Processing SID: {src}")
        try:
            dst_files = process_sid(src, config.SID_OUTPUT)
            for d in dst_files:
                print(f"  -> {d}")
        except Exception as e:
            print(f"Failed to process {src}: {e}")

    # Process GeoTIFF files
    for src in _iter_files(config.TIFF_INPUT, [".tif", ".tiff"]):
        print(f"Processing TIFF: {src}")
        try:
            dst = process_tiff(src, config.TIFF_OUTPUT)
            print(f"  -> {dst}")
        except Exception as e:
            print(f"Failed to process {src}: {e}")


if __name__ == "__main__":
    main()
