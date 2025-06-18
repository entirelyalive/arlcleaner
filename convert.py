"""Utility functions for converting imagery to GeoJPEG format."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional, List
from pathlib import Path

import json
import math
import re
import xml.etree.ElementTree as ET
from osgeo import gdal, osr
#try:
#    from osgeo import gdal, osr
#except Exception:  # pragma: no cover - optional dependency
#    gdal = None

import config


def _ensure_worldfile(tif_path: str) -> None:
    """
    If *tif_path* is 'xxx.tif' and a 'xxx.tfwx' file exists while no
    'xxx.tfw' (or '.tifw') does, copy it so that GDAL can read the
    geotransform.  Silently returns if nothing has to be done.
    """
    stem = Path(tif_path).with_suffix("")          # 'xxx'
    tfwx = stem.with_suffix(".tfwx")               # xxx.tfwx
    tfw  = stem.with_suffix(".tfw")                # xxx.tfw

    if tfwx.exists() and not tfw.exists():
        try:
            shutil.copy2(tfwx, tfw)
            print(f"[INFO] Copied {tfwx.name} → {tfw.name} so GDAL sees the world-file.")
        except Exception as exc:                   # pragma: no cover
            print(f"[WARN] Could not copy {tfwx} to {tfw}: {exc}")


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run a subprocess command quietly and return the CompletedProcess."""
    print(f"[DEBUG] Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        return result
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {' '.join(cmd)}")
        print(f"[ERROR] stdout: {e.stdout}")
        print(f"[ERROR] stderr: {e.stderr}")
        raise


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
    """
    Best-effort extraction of an EPSG code.
    """
    print(f"[DEBUG] Extracting EPSG for {path}")
    
    # --- 1. whatever came back from gdalinfo --json -------------------------
    cs_info = info.get("coordinateSystem", {})
    epsg_field = cs_info.get("epsg")
    if epsg_field:
        try:
            epsg_val = int(epsg_field)
            print(f"[DEBUG] Found EPSG from coordinateSystem.epsg: {epsg_val}")
            return epsg_val
        except ValueError:
            pass

    wkt = cs_info.get("wkt")
    if wkt:
        print(f"[DEBUG] WKT: {wkt[:200]}...")
        m = re.search(r'AUTHORITY\["EPSG",\s*"(\d+)"\]', wkt) or \
            re.search(r"EPSG:(\d+)", wkt)
        if m:
            epsg_val = int(m.group(1))
            print(f"[DEBUG] Found EPSG from WKT: {epsg_val}")
            return epsg_val

    # --- 2. open the raster directly with GDAL ------------------------------
    if path:
        try:
            ds = gdal.Open(path, gdal.GA_ReadOnly)
            if ds:
                projection = ds.GetProjection()
                print(f"[DEBUG] Direct GDAL projection: {projection[:200]}...")

                srs = osr.SpatialReference(wkt=projection)

                # Try the projected coordinate system first, then the geographic one
                for node in ("PROJCS", "GEOGCS", None):
                    code = srs.GetAuthorityCode(node)
                    if code:
                        epsg_val = int(code)
                        # Ignore the geocentric spheroid code 7019 or other
                        # codes that are known to be useless for rasters.
                        if epsg_val == 7019:
                            continue
                        print(f"[DEBUG] Found EPSG from GDAL ({node}): {epsg_val}")
                        return epsg_val

                # One more try: ask GDAL to auto-identify
                srs.AutoIdentifyEPSG()
                code = srs.GetAuthorityCode(None)
                if code and int(code) != 7019:
                    epsg_val = int(code)
                    print(f"[DEBUG] Found EPSG from AutoIdentify: {epsg_val}")
                    return epsg_val
        except Exception as e:
            print(f"[DEBUG] GDAL direct access failed: {e}")
            pass

    # --- 3. look for ArcGIS or ESRI side-cars -------------------------------
    if path:
        stem, _ = os.path.splitext(path)
        print(f"[DEBUG] Checking sidecar files for {stem}")

        for xml_path in (stem + ".aux.xml", stem + ".prj", path + ".aux.xml"):
            if not os.path.exists(xml_path):
                continue
            print(f"[DEBUG] Found sidecar: {xml_path}")
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()

                # (a) dedicated <WKID> or <LatestWKID> tags
                for tag in ("WKID", "LatestWKID"):
                    elem = root.find(f".//{{*}}{tag}")
                    if elem is not None and elem.text and elem.text.isdigit():
                        epsg_val = int(elem.text)
                        print(f"[DEBUG] Found EPSG from {tag}: {epsg_val}")
                        return epsg_val

                # (b) EPSG authority embedded in WKT text
                wkt_elem = root.find(".//{*}WKT")
                if wkt_elem is not None and wkt_elem.text:
                    print(f"[DEBUG] Sidecar WKT: {wkt_elem.text[:200]}...")
                    m = re.search(r'AUTHORITY\["EPSG",\s*"(\d+)"\]', wkt_elem.text)
                    if m:
                        epsg_val = int(m.group(1))
                        print(f"[DEBUG] Found EPSG from sidecar WKT: {epsg_val}")
                        return epsg_val
            except ET.ParseError:
                # *.prj* files are plain text  treat the whole file as WKT
                with open(xml_path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                print(f"[DEBUG] PRJ content: {content[:200]}...")
                m = re.search(r'AUTHORITY\["EPSG",\s*"(\d+)"\]', content) or \
                    re.search(r"EPSG:(\d+)", content)
                if m:
                    epsg_val = int(m.group(1))
                    print(f"[DEBUG] Found EPSG from PRJ: {epsg_val}")
                    return epsg_val
            except Exception as e:
                print(f"[DEBUG] Error parsing {xml_path}: {e}")
                pass

    print(f"[DEBUG] No EPSG found for {path}")
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
        # The JPEG driver does not understand TILED – it is for JPEG-in-TIFF
    ]

    subprocess.run(cmd, check=True)
    return dst


def _validate_epsg(epsg: int) -> bool:
    """Check if an EPSG code is suitable for imagery processing."""
    # EPSG:7019 is geocentric - not suitable for imagery
    # Add other problematic codes as needed
    problematic_codes = {7019}  # Geocentric coordinate systems
    
    if epsg in problematic_codes:
        print(f"[WARN] EPSG:{epsg} is not suitable for imagery processing")
        return False
    
    return True

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
    
    # Validate the EPSG code
    if epsg is not None and not _validate_epsg(epsg):
        print(f"[WARN] Invalid EPSG:{epsg} detected for {path}, trying to guess...")
        epsg = None
    
    src = path
    tmp_files = []

    try:
        if epsg is None:
            print(f"[INFO] No valid EPSG found for {path}, attempting direct conversion...")
            dst = _convert_to_jpeg(src, output_dir, dst_name=base, quality=60)
            info = _gdalinfo_json(dst)
            bbox = _bbox_from_info(info)
            if not bbox or not _bbox_valid(bbox):
                print(f"[INFO] Direct conversion failed, trying EPSG guessing...")
                # Try the guessing approach
                guessed_path = _guess_epsg_and_warp(src)
                if guessed_path:
                    dst = _convert_to_jpeg(guessed_path, output_dir, dst_name=base, quality=60)
                    return [dst]
                else:
                    raise RuntimeError("could not determine EPSG for SID")
            return [dst]
        else:
            # We now have a *valid* EPSG.  Tile it – the single-file
            # conversion would either exceed libjpeg’s 65 500-pixel limit
            # or create an unusable output.
            if epsg != 4269:
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


def _print_epsg_bbox(label: str, path: str) -> None:
    """Dump EPSG and corner‐bbox to the console."""
    info = gdal.Info(path, format="json")
    # Try JSON coordinateSystem.epsg first
    cs = info.get("coordinateSystem", {}) or {}
    epsg = cs.get("epsg", None)
    try:
        epsg = int(epsg)
    except Exception:
        epsg = None
    bbox = _bbox_from_info(info)
    print(f"[DEBUG] {label}: {path}")
    print(f"        → EPSG={epsg!r}, bbox={bbox!r}")

def _primary_process(file_path: str, output_dir: str) -> Optional[Dict]:
    if gdal is None:
        raise RuntimeError("GDAL Python bindings are required")

    _ensure_worldfile(file_path)

    base = os.path.splitext(os.path.basename(file_path))[0]

    # 1) debug print on the input TIFF
    _print_epsg_bbox("Input TIFF", file_path)

    # create a temp workspace for everything
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tif = os.path.join(tmpdir, f"{base}_to_{config.TARGET_EPSG}.tif")

        # reproject or copy into tmp_tif
        info_json = gdal.Info(file_path, format="json")
        src_epsg = _extract_epsg(info_json, file_path)
        print(f"Source EPSG: {src_epsg} for {base}")
        if src_epsg is None:
            print(f"[WARN] Cannot determine CRS for {file_path}; skipping.")
            return None

        if src_epsg == config.TARGET_EPSG:
            gdal.Translate(tmp_tif, file_path, format="GTiff")
        else:
            warp_opts = gdal.WarpOptions(
                srcSRS=f"EPSG:{src_epsg}", dstSRS=f"EPSG:{config.TARGET_EPSG}", multithread=True
            )
            gdal.Warp(tmp_tif, file_path, options=warp_opts)

        # produce the final JPEG _inside_ tmpdir
        tmp_jpg = os.path.join(tmpdir, f"{base}.jpg")
        gdal.Translate(
            tmp_jpg,
            tmp_tif,
            format="JPEG",
            creationOptions=["WORLDFILE=YES", "QUALITY=80"],
        )

        # debug print on the just‐created JPG
        _print_epsg_bbox("Temp JPG", tmp_jpg)

        # now atomically move just the JPG + sidecar into your real output_dir
        os.makedirs(output_dir, exist_ok=True)
        final_jpg = os.path.join(output_dir, os.path.basename(tmp_jpg))
        final_aux = final_jpg + ".aux.xml"
        shutil.move(tmp_jpg, final_jpg)
        # the .aux.xml will also be in tmpdir, so move it too if it exists
        tmp_aux = tmp_jpg + ".aux.xml"
        if os.path.exists(tmp_aux):
            shutil.move(tmp_aux, final_aux)

    # by the time we get here, tmpdir is cleaned up automatically
    # and only final_jpg (+ .aux.xml) live in output_dir
    return {"jpg_path": final_jpg, "aux_xml_path": final_aux}


def _secondary_process(file_path: str, output_dir: str) -> Optional[dict]:
    """More expensive fallback workflow for troublesome GeoTIFFs."""
    if gdal is None:
        raise RuntimeError("GDAL Python bindings are required for TIFF processing")
    base = os.path.splitext(os.path.basename(file_path))[0]
    tif_path = file_path
    aux_path = tif_path + ".aux.xml"
    corrected_tif = os.path.join(output_dir, f"{base}_corrected.tif")
    reprojected_tif = os.path.join(output_dir, f"{base}_EPSG4269.tif")
    geo_jpg = os.path.join(output_dir, f"{base}_EPSG4269.jpg")

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
        gdal.Warp(corrected_tif, vrt_path, dstSRS="EPSG:4269")
        os.remove(vrt_path)
    else:
        gdal.Translate(corrected_tif, tif_path, outputSRS=spatial_ref)

    gdal.Warp(reprojected_tif, corrected_tif, dstSRS="EPSG:4269")

    gdal.Translate(
        geo_jpg,
        reprojected_tif,
        format="JPEG",
        creationOptions=["WORLDFILE=YES", "QUALITY=80"],
    )

    os.remove(corrected_tif)
    os.remove(reprojected_tif)

    return {"jpg_path": geo_jpg, "aux_xml_path": geo_jpg + ".aux.xml"}


def process_tiff(path: str, output_dir: str) -> Optional[str]:
    base = os.path.splitext(os.path.basename(path))[0]

    # 1st try the primary pipeline
    res = _primary_process(path, output_dir)
    if res:
        info = gdal.Info(res["jpg_path"], format="json")
        bbox = _bbox_from_info(info)
        if bbox and _bbox_valid(bbox):
            return res["jpg_path"]

    # fallback to secondary
    res = _secondary_process(path, output_dir)
    if res:
        info = gdal.Info(res["jpg_path"], format="json")
        bbox = _bbox_from_info(info)
        if bbox and _bbox_valid(bbox):
            return res["jpg_path"]

    _log_error(base, "TIFF processing failed")
    _move_to_failed(path)
    return None

def _create_vrt_with_worldfile(tif_path: str) -> str:
    """Create a VRT that explicitly references the world file."""
    import tempfile
    
    base = os.path.splitext(os.path.basename(tif_path))[0]
    stem = Path(tif_path).with_suffix("")
    tfw_path = stem.with_suffix(".tfw")
    
    if not tfw_path.exists():
        return tif_path  # No world file, return original
    
    # Read world file parameters
    try:
        with open(tfw_path, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
        if len(lines) >= 6:
            pixel_x_size = float(lines[0])
            rotation_y = float(lines[1])  
            rotation_x = float(lines[2])
            pixel_y_size = float(lines[3])  # Usually negative
            x_origin = float(lines[4])
            y_origin = float(lines[5])
            
            # Create temporary VRT
            vrt_path = os.path.join(tempfile.gettempdir(), f"{base}_with_worldfile.vrt")
            
            # Use gdal.Translate to create VRT with proper geotransform
            gdal.Translate(
                vrt_path,
                tif_path,
                format="VRT",
                outputSRS="EPSG:26914",  # Your source EPSG
                GCPs=None,
                outputBounds=None,
                # Set the geotransform explicitly
                options=[f"-a_ullr {x_origin} {y_origin + pixel_y_size * 0} {x_origin + pixel_x_size * 0} {y_origin}"]
            )
            
            return vrt_path
    except Exception as e:
        print(f"[WARN] Could not create VRT for {tif_path}: {e}")
    
    return tif_path
