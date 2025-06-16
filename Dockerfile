FROM klokantech/gdal:latest

# still need python if you want it:
RUN apt-get update -qq \
      --allow-releaseinfo-change \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY sidtest.py .
COPY decode_sid.sh /usr/local/bin/decode_sid.sh
RUN chmod +x /usr/local/bin/decode_sid.sh

ENTRYPOINT ["python3", "/app/sidtest.py"]
