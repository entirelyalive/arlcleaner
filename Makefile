IMAGE_NAME ?= arlcleaner
MRSID_SDK_PATH ?= mrsid_sdk_placeholder.tar.gz
# Prefix Docker commands with sudo by default. Set SUDO= to disable.
SUDO ?= sudo

.PHONY: build
build:
	$(SUDO) docker build --build-arg MRSID_SDK_PATH=$(MRSID_SDK_PATH) -t $(IMAGE_NAME) .

.PHONY: sid-test
sid-test: build
	$(SUDO) docker run --rm $(IMAGE_NAME)
