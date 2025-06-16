# arlcleaner

Full AI gen MrSID and Tiff Processor

## Building the Docker image

The repository includes a `Dockerfile` that installs Python 3 and GDAL.  The proprietary MrSID SDK can be added at build time when you have downloaded the archive separately.

Download the SDK from LizardTech and place the tarball in this directory (the filename used below matches the current release).

### Without the SDK

Build a basic image that only contains GDAL:

```bash
docker build -t arlcleaner .
```

### Including the MrSID SDK

Copy the SDK archive into the project root and pass its name via the `MRSID_SDK_PATH` build argument:

```bash
cp /mnt/rawdata/pyarl/SID/MrSID_DSDK-9.5.4.4709-rhel6.x86-64.gcc531.tar.gz .
docker build --build-arg MRSID_SDK_PATH=MrSID_DSDK-9.5.4.4709-rhel6.x86-64.gcc531.tar.gz -t arlcleaner .
```

Alternatively, you can place the archive elsewhere and reference the relative path when building.

## Running

The container executes `sidtest.py` by default.  To run it:

```bash
docker run --rm arlcleaner
```

The script reports the GDAL version and whether the MrSID SDK is available.
