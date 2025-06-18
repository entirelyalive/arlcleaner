from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import math
import json
import re
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET

from osgeo import gdal, osr

import config


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run a subprocess command and return the CompletedProcess."""
    print(f"[DEBUG] Running command: {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _gdalinfo_json(path: str) -> dict:
    out = subprocess.check_output(["gdalinfo", "-json", path], text=True)
    return json.loads(out)


def _extract_epsg(info: dict, path: Optional[str] = None) -> Optional[int]:
    """Best-effort extraction of an EPSG code."""
    cs_info = info.get("coordinateSystem", {})
    epsg_field = cs_info.get("epsg")
    if epsg_field:
        try:
            return int(epsg_field)
        except ValueError:
            pass

    wkt = cs_info.get("wkt")
    if wkt:
        m = re.search(r'AUTHORITY\["EPSG",\s*"(\d+)"\]', wkt) or re.search(r"EPSG:(\d+)", wkt)
        if m:
            return int(m.group(1))

    if path:
        try:
            ds = gdal.Open(path, gdal.GA_ReadOnly)
            if ds:
                projection = ds.GetProjection()
                srs = osr.SpatialReference(wkt=projection)
                for node in ("PROJCS", "GEOGCS", None):
                    code = srs.GetAuthorityCode(node)
                    if code and int(code) != 7019:
                        return int(code)
                srs.AutoIdentifyEPSG()
                code = srs.GetAuthorityCode(None)
                if code and int(code) != 7019:
                    return int(code)
        except Exception:
            pass

    if path:
        stem, _ = os.path.splitext(path)
        for xml_path in (stem + ".aux.xml", stem + ".prj", path + ".aux.xml"):
            if not os.path.exists(xml_path):
                continue
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                for tag in ("WKID", "LatestWKID"):
                    elem = root.find(f".//{{*}}{tag}")
                    if elem is not None and elem.text and elem.text.isdigit():
                        return int(elem.text)
                wkt_elem = root.find(".//{*}WKT")
                if wkt_elem is not None and wkt_elem.text:
                    m = re.search(r'AUTHORITY\["EPSG",\s*"(\d+)"\]', wkt_elem.text)
                    if m:
                        return int(m.group(1))
            except ET.ParseError:
                with open(xml_path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                m = re.search(r'AUTHORITY\["EPSG",\s*"(\d+)"\]', content) or re.search(r"EPSG:(\d+)", content)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
    return None


def _bbox_from_info(info: dict) -> Optional[tuple]:
    corners = info.get("cornerCoordinates")
    if not corners:
        return None
    xs, ys = [], []
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


def _warp_to_target(src: str, dst: str, src_epsg: Optional[int] = None) -> None:
    cmd = ["gdalwarp", "-q"]
    if src_epsg:
        cmd.extend(["-s_srs", f"EPSG:{src_epsg}"])
    cmd.extend(["-t_srs", f"EPSG:{config.TARGET_EPSG}", src, dst])
    _run(cmd)


def _guess_epsg_and_warp(src: str) -> Optional[str]:
    candidates = [4269, 4326, 3857] + [32600 + z for z in range(10, 20)]
    base = os.path.splitext(os.path.basename(src))[0]
    tmp_dir = tempfile.mkdtemp()
    for cand in candidates:
        tmp = os.path.join(tmp_dir, f"{base}_guess_{cand}.tif")
        try:
            _warp_to_target(src, tmp, cand)
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
    if not shutil.which("gdal_translate"):
        raise RuntimeError("gdal_translate not found in PATH")
    os.makedirs(dst_dir, exist_ok=True)
    base = dst_name if dst_name else os.path.splitext(os.path.basename(src))[0]
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
    ]
    subprocess.run(cmd, check=True)
    return dst


def _validate_epsg(epsg: int) -> bool:
    if epsg == 7019:
        print(f"[WARN] EPSG:{epsg} is not suitable for imagery processing")
        return False
    return True


def process_sid(path: str, output_dir: str) -> List[str]:
    """Convert a MrSID image to tiled GeoJPEGs in the target projection."""
    if not path.lower().endswith(".sid"):
        raise ValueError(f"Expected a .sid file, got: {path}")
    print(f"[INFO] Starting SID conversion for {path}")
    base = os.path.splitext(os.path.basename(path))[0]
    try:
        info = _gdalinfo_json(path)
    except Exception as exc:
        _log_error(base, f"gdalinfo failed: {exc}")
        _move_to_failed(path)
        return []

    epsg = _extract_epsg(info, path)
    if epsg is not None and not _validate_epsg(epsg):
        epsg = None

    src = path
    tmp_files: List[str] = []
    try:
        if epsg is None:
            dst = _convert_to_jpeg(src, output_dir, dst_name=base, quality=60)
            info = _gdalinfo_json(dst)
            bbox = _bbox_from_info(info)
            if not bbox or not _bbox_valid(bbox):
                guessed = _guess_epsg_and_warp(src)
                if guessed:
                    dst = _convert_to_jpeg(guessed, output_dir, dst_name=base, quality=60)
                    print(f"successfully out put {dst}")
                    return [dst]
                raise RuntimeError("could not determine EPSG for SID")
            print(f"successfully out put {dst}")
            return [dst]
        else:
            if epsg != config.TARGET_EPSG:
                tmp = os.path.join(output_dir, base + "_warp.tif")
                _warp_to_target(src, tmp, epsg)
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
        print(f"[DEBUG] Raster size {width}x{height}, tiling to {nx}x{ny} tiles")
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
                    f"QUALITY={60}",
                    "-co",
                    "WORLDFILE=YES",
                    "-srcwin",
                    str(xoff),
                    str(yoff),
                    str(w),
                    str(h),
                ]
                _run(cmd)
                tiles.append(dst)
                print(f"successfully out put {dst}")
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
