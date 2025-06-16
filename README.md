# arlcleaner

Tools for converting MrSID and GeoTIFF imagery inside a container.

## Building the Docker image

The Docker image installs Python, GDAL and, optionally, the proprietary MrSID SDK.  Because the SDK cannot be redistributed, download the tarball separately and place it in this directory before building.

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

Alternatively, you can build the image and run the test via `make`:

```bash
make sid-test
```

The script reports the GDAL version and whether the MrSID SDK is available.

### Converting SID files

When the SDK is included, you can convert a `.sid` file to a GeoJPEG using the helper script:

```bash
docker run --rm -v /path/to/data:/data arlcleaner \
    decode_sid.sh /data/input.sid
```

This produces `input.jpg` and `input.jgw` alongside the source file.
