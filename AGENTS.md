# Agent Guidelines: dn42-mmdb

## Build & Test Commands

- `make verify` - Validate Python syntax and script compilation.
- `make build REGISTRY=/path/to/registry` - Build all three databases.
- `make dn42-asn.mmdb` - Build only the ASN database. `make dn42-country.mmdb` and `make dn42-city.mmdb` both run the single geo builder, which writes both geo databases.
- `make checksum` - Generate a SHA-256 checksum file next to each database. The database targets are phony, so this rebuilds them first and needs a registry; use `make build checksum` in one invocation to build each database exactly once.
- `make sync REGISTRY=/path/to/registry` - Refresh the committed geofeed snapshot. Requires network; not part of `build`.
- `make clean` - Remove generated MMDB and checksum files.

`OUTPUT=` is no longer honored; use the per-database targets or the `ASN_DB`, `COUNTRY_DB`, `CITY_DB` variables.

## Architecture & Design

Three databases, mirroring MaxMind's own GeoLite2 product split:

- `build_asn_mmdb.py` reads `data/route`, `data/route6` and `data/aut-num`, mapping prefixes to origin ASNs and `as-name`. Output: `dn42-asn.mmdb`, type `GeoLite2-ASN`.
- `build_geo_mmdb.py` reads `data/inetnum` and `data/inet6num` in one pass and writes both geo databases. Output: `dn42-country.mmdb` (type `GeoLite2-Country`) from `country:` alone, and `dn42-city.mmdb` (type `GeoLite2-City`) from that plus the geofeed overlay.
- `tools/sync_geofeed.py` fetches RFC 8805 geofeeds declared via `geofeed:` and writes the committed snapshot `data/geofeed.csv`.
- `dn42_registry.py` holds the shared RPSL parser; `iso_countries.py` holds the vendored ISO 3166-1 table.

Key invariants:

- **The build never touches the network.** Geofeed fetching is a separate stage whose output is committed and reviewed, which keeps the signed release reproducible in its inputs.
- **Geofeed rows are bounded by the object that declared the feed.** Rows naming space outside the declaring `inetnum` are rejected in the sync tool and again at build time.
- **Broad prefixes are inserted first** so longest-prefix match wins, which is what lets a geofeed `/32` override its allocation.
- `country` is where an address is located; `registered_country` is what the registry says. Only the city database can differ between them.

## Conventions

- Every new file carries an SPDX header (`Copyright 2026 Ronny Trommer <ronny@no42.org>`, `SPDX-License-Identifier: MIT`).
- CI workflows invoke `make` targets instead of running raw scripts.
- GitHub Actions are pinned to full 40-character commit SHAs with version comments.
- Commits use Conventional Commits format with `Signed-off-by` and `Assisted-by` trailers.
- The Makefile avoids GNU Make 4.3 grouped targets (`&:`); macOS ships make 3.81, which misparses them.
