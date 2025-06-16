IMAGE_NAME ?= arlcleaner
MRSID_SDK_PATH ?= mrsid_sd.tar.gz

.PHONY: build
build:
	docker build --build-arg MRSID_SDK_PATH=$(MRSID_SDK_PATH) -t $(IMAGE_NAME) .

.PHONY: sid-test
sid-test: build
	docker run --rm $(IMAGE_NAME)
