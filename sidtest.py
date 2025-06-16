#sidtest.py
import shutil
import subprocess

def main():
    print("Running sidtest.py")
    try:
        subprocess.run(["gdalinfo", "--version"], check=True)
    except Exception as e:
        print("GDAL not available:", e)

    if shutil.which("mrsidgeodecode"):
        print("mrsidgeodecode available")
    else:
        print("mrsidgeodecode not found")

    try:
        out = subprocess.check_output(["gdalinfo", "--formats"], text=True)
        if "MrSID" in out:
            print("GDAL reports MrSID support")
        else:
            print("GDAL does not report MrSID support")
    except Exception as e:
        print("Could not query GDAL formats:", e)

if __name__ == "__main__":
    main()
