FROM ubuntu:24.04

# Optional path to a locally available MrSID SDK archive
ARG MRSID_SDK_PATH=mrsid_sdk.tar.gz

# Install Python and GDAL for the follow-up conversion step
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip gdal-bin ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the MrSID SDK when the archive is provided
WORKDIR /opt
COPY ${MRSID_SDK_PATH} /tmp/mrsid_sdk.tar.gz
RUN if [ -s /tmp/mrsid_sdk.tar.gz ]; then \
        tar xf /tmp/mrsid_sdk.tar.gz && \
        cp -r Geo_DSDK*/* /usr/local/ && \
        ldconfig && \
        rm -rf Geo_DSDK* /tmp/mrsid_sdk.tar.gz; \
    else \
        echo "MrSID SDK not provided" && rm /tmp/mrsid_sdk.tar.gz; \
    fi

ENV PATH="/usr/local/bin:${PATH}" \
    LD_LIBRARY_PATH="/usr/local/lib"

# Add the test and helper scripts
WORKDIR /app
COPY sidtest.py /app/sidtest.py
COPY decode_sid.sh /usr/local/bin/decode_sid.sh
RUN chmod +x /usr/local/bin/decode_sid.sh

ENTRYPOINT ["python3", "/app/sidtest.py"]
