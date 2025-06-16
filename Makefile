# Name the image whatever you like
IMAGE_NAME ?= arlcleaner
# Location on the host containing one or more .sid files
SID_DIR     ?= /mnt/rawdata/pyarl/TestMaps
# (optional) name of a specific SID inside SID_DIR to convert
SID_FILE    ?=

# host folders (override on the make command-line if you like)
SID_IN     ?= /mnt/rawdata/pyarl/TestSIDInput
SID_OUT    ?= /mnt/rawdata/pyarl/TestSIDOutput
TIFF_IN    ?= /mnt/rawdata/pyarl/TestTIFFInput
TIFF_OUT   ?= /mnt/rawdata/pyarl/TestTIFFOutput

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) .

.PHONY: sid-test           # runs the GDAL/MrSID self-check
sid-test: build
	docker run --rm $(IMAGE_NAME)

.PHONY: convert-one        # convert a single SID → GeoJPEG
convert-one:
	docker build -t arlcleaner .
    docker run --rm \
		-v /mnt/rawdata/pyarl/TestMaps:/data \
		-e SID_FILE=/data/ortho_1-1_1c_s_tx141_2.sid \
		arlcleaner

.PHONY: convert-all        # bulk-convert every *.sid in SID_DIR
convert-all: build
	docker run --rm -v $(SID_DIR):/data $(IMAGE_NAME) \
	    bash -c 'cd /data && for f in *.sid; do decode_sid.sh $$f; done'

.PHONY: test-image
test-image: build
	docker run --rm \
	  --entrypoint python3 \
	  -v $(shell pwd):/app                 \
	  -v $(SID_IN):$(SID_IN)              \
	  -v $(SID_OUT):$(SID_OUT)            \
	  -v $(TIFF_IN):$(TIFF_IN)            \
	  -v $(TIFF_OUT):$(TIFF_OUT)          \
	  -w /app                             \
	  $(IMAGE_NAME)                       \
	  /app/image_test.py
