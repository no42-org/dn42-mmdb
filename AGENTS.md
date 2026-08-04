# Agent Guidelines: dn42-mmdb

## Build & Test Commands

- `make verify` - Validate Python syntax and script compilation.
- `make build REGISTRY=/path/to/registry` - Build `dn42-asn.mmdb` from a DN42 registry directory.
- `make checksum` - Generate SHA-256 checksum file `dn42-asn.mmdb.sha256`.
- `make clean` - Remove generated MMDB and checksum files.

## Architecture & Design

- `build_asn_mmdb.py` parses RPSL objects from `data/route`, `data/route6`, and `data/aut-num` in a DN42 registry checkout.
- Maps prefix routes to origin ASNs and `as-name` values using MaxMind `mmdb_writer`.
- Outputs a MaxMind MMDB file matching `GeoLite2-ASN` schema for drop-in compatibility with GeoIP tools.

## Conventions

- Every new file carries an SPDX header (`Copyright 2026 Ronny Trommer <ronny@no42.org>`, `SPDX-License-Identifier: MIT`).
- CI workflows invoke `make` targets instead of running raw scripts.
- GitHub Actions are pinned to full 40-character commit SHAs with version comments.
- Commits use Conventional Commits format with `Signed-off-by` and `Assisted-by` trailers.
