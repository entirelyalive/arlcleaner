import os
import sys
import json
import shutil
import subprocess
import textwrap

def banner(msg):
    print("\n" + "=" * 60 + f"\n{msg}\n" + "=" * 60)

def main() -> int:
    banner("GDAL core version")
    subprocess.run(["gdalinfo", "--version"], check=True)

    banner("MrSID driver present?")
    formats = subprocess.check_output(["gdalinfo", "--formats"], text=True)
    print("MrSID" in formats and "→ YES, driver registered." or "→ NO!")

    banner("Command-line helper availability")
    print("mrsidgeodecode:",
          "found" if shutil.which("mrsidgeodecode") else "not present (not needed)")

    # check for SID_FILE in env or as first CLI arg
    sid_file = os.environ.get("SID_FILE") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if sid_file:
        banner(f"Inspecting SID file: {sid_file!r}")
        try:
            info_json = subprocess.check_output(
                ["gdalinfo", "-json", sid_file],
                text=True,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            print("Failed to read SID file metadata:")
            print(e.output)
            return 1

        info = json.loads(info_json)

        # size
        sz = info.get("size", [])
        if len(sz) == 2:
            print(f"Raster size: {sz[0]} x {sz[1]} pixels")

        # projection
        cs = info.get("coordinateSystem", {}).get("wkt")
        if cs:
            first_line = cs.splitlines()[0]
            print(f"Projection (WKT head): {first_line} ...")

        # corner coordinates
        corners = info.get("cornerCoordinates", {})
        for label in ("upperLeft", "upperRight", "lowerLeft", "lowerRight"):
            coord = corners.get(label)
            if coord:
                print(f"{label}: {coord}")

        # metadata domain ""
        meta = info.get("metadata", {}).get("", {})
        if meta:
            print("Embedded metadata:")
            for k, v in meta.items():
                print(f"  {k} = {v}")

        banner("SID metadata inspection complete")

    banner("All set – run `make convert-one SID_FILE=<path-to-your.sid>` to try a real file.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
