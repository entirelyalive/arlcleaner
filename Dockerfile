FROM python:3.10-slim

ARG MRSID_SDK_PATH=mrsid_sdk_placeholder.tar.gz

# Install GDAL
RUN apt-get update \ 
    && apt-get install -y gdal-bin libgdal-dev \ 
    && rm -rf /var/lib/apt/lists/*

# Copy test script
WORKDIR /app
COPY sidtest.py /app/sidtest.py

# Optionally install MrSID SDK
COPY ${MRSID_SDK_PATH} /tmp/mrsid_sdk.tar.gz
RUN if [ -s /tmp/mrsid_sdk.tar.gz ]; then \
        mkdir -p /opt/mrsid && \
        tar -xzf /tmp/mrsid_sdk.tar.gz -C /opt/mrsid --strip-components=1 && \
        rm /tmp/mrsid_sdk.tar.gz && \
        echo "MrSID SDK installed"; \
    else \
        echo "MrSID SDK not provided" && rm /tmp/mrsid_sdk.tar.gz; \
    fi

ENV PATH="/opt/mrsid/bin:${PATH}"

ENTRYPOINT ["python", "/app/sidtest.py"]
