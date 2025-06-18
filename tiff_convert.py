from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import json
import re
from pathlib import Path
from typing import Optional, Dict
import xml.etree.ElementTree as ET

from osgeo import gdal, osr

import config


def _ensure_worldfile(tif_path: str) -> None:
    """Ensure GDAL can read a world file when only .tfwx exists."""
    stem = Path(tif_path).with_suffix("")
    tfwx = stem.with_suffix(".tfwx")
    tfw = stem.with_suffix(".tfw")
    if tfwx.exists() and not tfw.exists():
        try:
            shutil.copy2(tfwx, tfw)
            print(f"[INFO] Copied {tfwx.name} -> {tfw.name}")
        except Exception as exc:
            print(f"[WARN] Could not copy {tfwx} to {tfw}: {exc}")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"[DEBUG] Running command: {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _extract_epsg(info: dict, path: Optional[str] = None) -> Optional[int]:
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


def _primary_process(file_path: str, output_dir: str) -> Optional[Dict]:
    _ensure_worldfile(file_path)
    base = os.path.splitext(os.path.basename(file_path))[0]
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tif = os.path.join(tmpdir, f"{base}_to_{config.TARGET_EPSG}.tif")
        info_json = gdal.Info(file_path, format="json")
        src_epsg = _extract_epsg(info_json, file_path)
        print(f"Source EPSG: {src_epsg} for {base}")
        if src_epsg is None:
            print(f"[WARN] Cannot determine CRS for {file_path}; skipping.")
            return None
        if src_epsg == config.TARGET_EPSG:
            gdal.Translate(tmp_tif, file_path, format="GTiff")
        else:
            warp_opts = gdal.WarpOptions(srcSRS=f"EPSG:{src_epsg}", dstSRS=f"EPSG:{config.TARGET_EPSG}", multithread=True)
            gdal.Warp(tmp_tif, file_path, options=warp_opts)
        tmp_jpg = os.path.join(tmpdir, f"{base}.jpg")
        gdal.Translate(tmp_jpg, tmp_tif, format="JPEG", creationOptions=["WORLDFILE=YES", f"QUALITY={config.JPEG_QUALITY}"])
        os.makedirs(output_dir, exist_ok=True)
        final_jpg = os.path.join(output_dir, os.path.basename(tmp_jpg))
        final_aux = final_jpg + ".aux.xml"
        shutil.move(tmp_jpg, final_jpg)
        tmp_aux = tmp_jpg + ".aux.xml"
        if os.path.exists(tmp_aux):
            shutil.move(tmp_aux, final_aux)
    return {"jpg_path": final_jpg, "aux_xml_path": final_aux}


def _secondary_process(file_path: str, output_dir: str) -> Optional[Dict]:
    base = os.path.splitext(os.path.basename(file_path))[0]
    tif_path = file_path
    aux_path = tif_path + ".aux.xml"
    corrected_tif = os.path.join(output_dir, f"{base}_corrected.tif")
    reprojected_tif = os.path.join(output_dir, f"{base}_EPSG{config.TARGET_EPSG}.tif")
    geo_jpg = os.path.join(output_dir, f"{base}_EPSG{config.TARGET_EPSG}.jpg")

    spatial_ref = None
    gcp_list = []

    if os.path.exists(aux_path):
        try:
            tree = ET.parse(aux_path)
            root = tree.getroot()
            for element in root.iter():
                if element.tag == "WKT":
                    spatial_ref = element.text
                elif element.tag == "SourceGCPs":
                    gcp_elements = root.findall("SourceGCPs/Double")
                    if gcp_elements:
                        gcp_list = [tuple(map(float, el.text.split())) for el in gcp_elements]
        except Exception as e:
            print(f"Error parsing .aux.xml for {file_path}: {e}")

    if not spatial_ref:
        dataset = gdal.Open(tif_path)
        if dataset:
            crs_wkt = dataset.GetProjection()
            if crs_wkt:
                spatial_ref = crs_wkt
        else:
            print(f"Could not open dataset for {file_path}.")

    if not spatial_ref:
        tfwx_path = tif_path.replace(".tif", ".tfwx")
        if os.path.exists(tfwx_path):
            print(f"Inferred CRS from TFWX for {file_path}. Assigning EPSG:4326.")
            spatial_ref = "EPSG:4326"

    if not spatial_ref:
        print(f"No spatial reference found for {file_path}.")
        return None

    if gcp_list:
        vrt_path = tif_path + ".vrt"
        gdal.Translate(vrt_path, tif_path, GCPs=gcp_list, outputSRS=spatial_ref)
        gdal.Warp(corrected_tif, vrt_path, dstSRS=f"EPSG:{config.TARGET_EPSG}")
        os.remove(vrt_path)
    else:
        gdal.Translate(corrected_tif, tif_path, outputSRS=spatial_ref)

    gdal.Warp(reprojected_tif, corrected_tif, dstSRS=f"EPSG:{config.TARGET_EPSG}")
    gdal.Translate(geo_jpg, reprojected_tif, format="JPEG", creationOptions=["WORLDFILE=YES", f"QUALITY={config.JPEG_QUALITY}"])
    os.remove(corrected_tif)
    os.remove(reprojected_tif)
    return {"jpg_path": geo_jpg, "aux_xml_path": geo_jpg + ".aux.xml"}


def process_tiff(path: str, output_dir: str) -> Optional[str]:
    if not path.lower().endswith(('.tif', '.tiff')):
        raise ValueError(f"Expected a .tif or .tiff file, got: {path}")

    base = os.path.splitext(os.path.basename(path))[0]
    print(f"[INFO] Starting TIFF conversion for {path}")
    res = _primary_process(path, output_dir)
    if res:
        info = gdal.Info(res["jpg_path"], format="json")
        bbox = _bbox_from_info(info)
        if bbox and _bbox_valid(bbox):
            print(f"successfully out put {res['jpg_path']}")
            return res["jpg_path"]
    res = _secondary_process(path, output_dir)
    if res:
        info = gdal.Info(res["jpg_path"], format="json")
        bbox = _bbox_from_info(info)
        if bbox and _bbox_valid(bbox):
            print(f"successfully out put {res['jpg_path']}")
            return res["jpg_path"]
    _log_error(base, "TIFF processing failed")
    _move_to_failed(path)
    return None
