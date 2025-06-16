FROM klokantech/gdal:latest

# Lightweight Python runtime just for the self-test script
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

# Helper + test scripts
WORKDIR /app
COPY sidtest.py  sidtest.py
COPY decode_sid.sh /usr/local/bin/decode_sid.sh
RUN chmod +x /usr/local/bin/decode_sid.sh

ENTRYPOINT ["python3", "/app/sidtest.py"]
