# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT

REGISTRY ?= registry
GEOFEED ?= data/geofeed.csv
PYTHON ?= python3

ASN_DB ?= dn42-asn.mmdb
COUNTRY_DB ?= dn42-country.mmdb
CITY_DB ?= dn42-city.mmdb
DATABASES = $(ASN_DB) $(COUNTRY_DB) $(CITY_DB)

SCRIPTS = build_asn_mmdb.py build_geo_mmdb.py dn42_registry.py iso_countries.py \
          tools/sync_geofeed.py

# The databases are always rebuilt: the registry changes underneath them and
# make cannot see that. Declaring them phony keeps `make build` doing the same
# thing on every invocation, as it did when it wrapped the script directly.
.PHONY: all build checksum verify sync clean geo $(DATABASES)

all: verify build checksum

verify:
	$(PYTHON) -m py_compile $(SCRIPTS)

build: $(DATABASES)

$(ASN_DB):
	$(PYTHON) build_asn_mmdb.py --registry $(REGISTRY) -o $@

# One pass over the registry writes both geo databases, so both targets hang
# off a single recipe. Avoids GNU Make 4.3 grouped targets (`&:`), which parse
# as unrelated targets on the make 3.81 that ships with macOS.
$(COUNTRY_DB) $(CITY_DB): geo

geo:
	$(PYTHON) build_geo_mmdb.py --registry $(REGISTRY) --geofeed $(GEOFEED) \
	    --country-output $(COUNTRY_DB) --city-output $(CITY_DB)

checksum: $(DATABASES:=.sha256)

%.mmdb.sha256: %.mmdb
	sha256sum $< > $@

# Refresh the committed geofeed snapshot. Not part of `build`: the build
# stays offline and reads whatever snapshot is committed.
sync:
	$(PYTHON) tools/sync_geofeed.py --registry $(REGISTRY) -o $(GEOFEED)

clean:
	rm -f $(DATABASES) $(DATABASES:=.sha256)
