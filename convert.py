"""Utility functions for converting imagery to GeoJPEG format."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional, List

import json
import math
import re
import xml.etree.ElementTree as ET

import config


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run a subprocess command quietly and return the CompletedProcess."""
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)


def _gdalinfo_json(path: str) -> dict:
    out = subprocess.check_output(["gdalinfo", "-json", path], text=True)
    return json.loads(out)


def _extract_epsg_from_aux(path: str) -> Optional[int]:
    """Attempt to parse an EPSG code from a ``.aux.xml`` sidecar file."""
    candidates = [path + ".aux.xml", os.path.splitext(path)[0] + ".aux.xml"]
    for aux in candidates:
        try:
            tree = ET.parse(aux)
            root = tree.getroot()
            text = ET.tostring(root, encoding="unicode")
            m = re.search(r"EPSG[:\"]?(\d+)", text)
            if m:
                return int(m.group(1))
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return None


def _extract_epsg(info: dict, path: Optional[str] = None) -> Optional[int]:
    cs_info = info.get("coordinateSystem", {})
    epsg_field = cs_info.get("epsg")
    if epsg_field:
        try:
            return int(epsg_field)
        except ValueError:
            pass
    cs = cs_info.get("wkt")
    if cs:
        matches = re.findall(r"AUTHORITY\[\"EPSG\",\s*\"(\d+)\"\]", cs)
        if matches:
            try:
                return int(matches[-1])
            except ValueError:
                pass
        m = re.search(r"EPSG:(\d+)", cs)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    if path:
        return _extract_epsg_from_aux(path)
    return None


def _bbox_from_info(info: dict) -> Optional[tuple]:
    corners = info.get("cornerCoordinates")
    if not corners:
        return None
    xs = []
    ys = []
    for c in ("upperLeft", "lowerLeft", "upperRight", "lowerRight"):
        if corners.get(c):
            x, y = corners[c]
            xs.append(x)
            ys.append(y)
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_valid(bbox: tuple) -> bool:
    if not getattr(config, "BBOX_CHECK", True):
        return True
    minx, miny, maxx, maxy = bbox
    if minx < -170 or maxx > -50 or miny < 15 or maxy > 75:
        return False
    if (maxx - minx) >= 1 or (maxy - miny) >= 1:
        return False
    return True


def _log_error(base: str, message: str) -> None:
    os.makedirs(config.ERROR_LOGS, exist_ok=True)
    log_path = os.path.join(config.ERROR_LOGS, base + ".log")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(message + "\n")
    print(f"[ERROR] {base}: {message} (logged to {log_path})")


def _move_to_failed(src: str) -> None:
    os.makedirs(config.FAILED_PROCESSING, exist_ok=True)
    directory = os.path.dirname(src)
    base = os.path.splitext(os.path.basename(src))[0]
    for name in os.listdir(directory):
        if name.startswith(base):
            try:
                shutil.copy2(os.path.join(directory, name),
                             os.path.join(config.FAILED_PROCESSING, name))
                print(f"[FAILED] Copied {name} to {config.FAILED_PROCESSING}")
            except Exception:
                pass


def _warp_to_4269(src: str, dst: str, src_epsg: Optional[int] = None) -> None:
    cmd = ["gdalwarp", "-q"]
    if src_epsg:
        cmd.extend(["-s_srs", f"EPSG:{src_epsg}"])
    cmd.extend(["-t_srs", "EPSG:4269", src, dst])
    _run(cmd)


def _guess_epsg_and_warp(src: str) -> Optional[str]:
    """Try a set of common EPSG codes and return warped filename if valid."""
    # Common projections plus a range of UTM zones (WGS84 datum)
    candidates = [4269, 4326, 3857] + [32600 + z for z in range(10, 20)]

    base = os.path.splitext(os.path.basename(src))[0]
    tmp_dir = tempfile.mkdtemp()
    for cand in candidates:
        tmp = os.path.join(tmp_dir, f"{base}_guess_{cand}.tif")
        try:
            _warp_to_4269(src, tmp, cand)
            info = _gdalinfo_json(tmp)
            bbox = _bbox_from_info(info)
            if bbox and _bbox_valid(bbox):
                return tmp
        except Exception:
            pass
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None


def _convert_to_jpeg(src: str, dst_dir: str, *, dst_name: Optional[str] = None,
                     quality: int = config.JPEG_QUALITY) -> str:
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

    if dst_name is None:
        base = os.path.splitext(os.path.basename(src))[0]
    else:
        base = dst_name
    dst = os.path.join(dst_dir, base + ".jpg")

    cmd = [
        "gdal_translate",
        src,
        dst,
        "-of",
        "JPEG",
        "-co",
        f"QUALITY={quality}",
        "-co",
        "WORLDFILE=YES",
        "-co",
        "TILED=YES",
    ]

    subprocess.run(cmd, check=True)
    return dst


def process_sid(path: str, output_dir: str) -> List[str]:
    """Process a MrSID image, convert to EPSG:4269 and tile to GeoJPEGs."""
    if not path.lower().endswith(".sid"):
        raise ValueError(f"Expected a .sid file, got: {path}")


    base = os.path.splitext(os.path.basename(path))[0]
    try:
        info = _gdalinfo_json(path)
    except Exception as exc:
        _log_error(base, f"gdalinfo failed: {exc}")
        _move_to_failed(path)
        return []

    epsg = _extract_epsg(info, path)
    src = path
    tmp_files = []

    try:
        if epsg is None:
            guess = _guess_epsg_and_warp(src)
            if guess:
                src = guess
                tmp_files.append(guess)
            else:
                dst = _convert_to_jpeg(src, output_dir, dst_name=base)
                info = _gdalinfo_json(dst)
                bbox = _bbox_from_info(info)
                if not bbox or not _bbox_valid(bbox):
                    raise RuntimeError("could not determine EPSG for SID")
                return [dst]
        elif epsg != 4269:
            tmp = os.path.join(output_dir, base + "_warp.tif")
            _warp_to_4269(src, tmp, epsg)
            src = tmp
            tmp_files.append(tmp)
        info = _gdalinfo_json(src)
        bbox = _bbox_from_info(info)
        if not bbox or not _bbox_valid(bbox):
            raise RuntimeError(f"invalid bbox after warp: {bbox}")

        width, height = info.get("size", [0, 0])
        if not width or not height:
            raise RuntimeError("missing raster size")

        os.makedirs(output_dir, exist_ok=True)
        tiles: List[str] = []
        nx = math.ceil(width / config.SID_TILE_WIDTH)
        ny = math.ceil(height / config.SID_TILE_HEIGHT)
        for y in range(ny):
            for x in range(nx):
                xoff = x * config.SID_TILE_WIDTH
                yoff = y * config.SID_TILE_HEIGHT
                w = min(config.SID_TILE_WIDTH, width - xoff)
                h = min(config.SID_TILE_HEIGHT, height - yoff)
                dst = os.path.join(output_dir, f"{base}_{x+1}_{y+1}.jpg")
                cmd = [
                    "gdal_translate",
                    src,
                    dst,
                    "-of",
                    "JPEG",
                    "-co",
                    f"QUALITY={config.JPEG_QUALITY}",
                    "-co",
                    "WORLDFILE=YES",
                    "-co",
                    "TILED=YES",
                    "-srcwin",
                    str(xoff),
                    str(yoff),
                    str(w),
                    str(h),
                ]
                _run(cmd)
                tiles.append(dst)
        return tiles
    except Exception as exc:
        _log_error(base, str(exc))
        _move_to_failed(path)
        return []
    finally:
        for f in tmp_files:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass


def process_tiff(path: str, output_dir: str) -> Optional[str]:
    """Process a GeoTIFF image and convert it to GeoJPEG."""
    if not (path.lower().endswith(".tif") or path.lower().endswith(".tiff")):
        raise ValueError(f"Expected a .tif/.tiff file, got: {path}")

    base = os.path.splitext(os.path.basename(path))[0]
    try:
        info = _gdalinfo_json(path)
    except Exception as exc:
        _log_error(base, f"gdalinfo failed: {exc}")
        _move_to_failed(path)
        return None

    epsg = _extract_epsg(info, path)
    src = path
    tmp_files = []

    try:
        if epsg is None:
            guess = _guess_epsg_and_warp(src)
            if guess:
                src = guess
                tmp_files.append(guess)
            else:
                # attempt conversion without reprojection
                dst = _convert_to_jpeg(src, output_dir, dst_name=base)
                info = _gdalinfo_json(dst)
                bbox = _bbox_from_info(info)
                if not bbox or not _bbox_valid(bbox):
                    raise RuntimeError("could not determine EPSG for TIFF")
                return dst
        elif epsg != 4269:
            tmp = os.path.join(output_dir, base + "_warp.tif")
            _warp_to_4269(src, tmp, epsg)
            src = tmp
            tmp_files.append(tmp)

        info = _gdalinfo_json(src)
        bbox = _bbox_from_info(info)
        if not bbox or not _bbox_valid(bbox):
            raise RuntimeError(f"invalid bbox after warp: {bbox}")

        dst = _convert_to_jpeg(src, output_dir, dst_name=base)
        return dst
    except Exception as exc:
        _log_error(base, str(exc))
        _move_to_failed(path)
        return None
    finally:
        for f in tmp_files:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass

