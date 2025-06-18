"""Run bulk conversion tests for SID and TIFF imagery."""

from __future__ import annotations

import os
from typing import Iterable
from concurrent.futures import ThreadPoolExecutor

import config
from sid_convert import process_sid
from tiff_convert import process_tiff


def _iter_files(folder: str, extensions: Iterable[str]):
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and any(name.lower().endswith(ext) for ext in extensions):
            yield path


def _process_sid(src: str) -> None:
    print(f"Processing SID: {src}")
    try:
        dst_files = process_sid(src, config.SID_OUTPUT)
        for d in dst_files:
            print(f"  -> {d}")
    except Exception as e:
        print(f"Failed to process {src}: {e}")


def _process_tiff(src: str) -> None:
    print(f"Processing TIFF: {src}")
    try:
        dst = process_tiff(src, config.TIFF_OUTPUT)
        print(f"  -> {dst}")
    except Exception as e:
        print(f"Failed to process {src}: {e}")


def main() -> None:
    sid_files = list(_iter_files(config.SID_INPUT, [".sid"]))
    tiff_files = list(_iter_files(config.TIFF_INPUT, [".tif", ".tiff"]))

    workers = getattr(config, "MAX_WORKERS", 4)

    with ThreadPoolExecutor(max_workers=workers) as exe:
        for src in sid_files:
            exe.submit(_process_sid, src)
        for src in tiff_files:
            exe.submit(_process_tiff, src)


if __name__ == "__main__":
    main()
