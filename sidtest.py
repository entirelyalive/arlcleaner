import os
import subprocess

def main():
    print("Running sidtest.py")
    try:
        subprocess.run(["gdalinfo", "--version"], check=True)
    except Exception as e:
        print("GDAL not available:", e)
    if os.path.exists("/opt/mrsid"):
        print("MrSID SDK installed")
    else:
        print("MrSID SDK not installed")

if __name__ == "__main__":
    main()
