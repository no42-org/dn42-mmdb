# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT

REGISTRY ?= registry
OUTPUT ?= dn42-asn.mmdb
PYTHON ?= python3

.PHONY: all build checksum verify clean

all: verify build checksum

verify:
	$(PYTHON) -m py_compile build_asn_mmdb.py

build:
	$(PYTHON) build_asn_mmdb.py --registry $(REGISTRY) -o $(OUTPUT)

checksum:
	sha256sum $(OUTPUT) > $(OUTPUT).sha256

clean:
	rm -f $(OUTPUT) $(OUTPUT).sha256
