# Release Process

This document describes how releases are generated, tagged, and verified.

## Versioning & Schedule

Releases use ISO date version tags (`vYYYY.MM.DD`).
Releases are built automatically every Monday at 03:00 UTC via GitHub Actions.
Releases can also be triggered on demand using the `workflow_dispatch` trigger in GitHub Actions.

A separate workflow refreshes the geofeed snapshot every Monday at 00:00 UTC, three hours ahead of the release.
It opens a pull request against `data/geofeed.csv` rather than feeding the build directly, with auto-merge enabled, so the snapshot lands on `main` once CI is green and ships in that same Monday's release.
The pull request is opened with a GitHub App token so that CI runs on it; see `CONTRIBUTING.md` for the setup.
The release build itself performs no network access beyond cloning the registry.

## Release Artifacts

Each release publishes the following assets to GitHub Releases:

| Asset | Description |
| --- | --- |
| `dn42-asn.mmdb` | MaxMind GeoLite2-ASN compatible database |
| `dn42-asn.mmdb.sha256` | SHA-256 checksum |
| `dn42-asn.mmdb.sig` | cosign signature bundle |
| `dn42-country.mmdb` | MaxMind GeoLite2-Country compatible database |
| `dn42-country.mmdb.sha256` | SHA-256 checksum |
| `dn42-country.mmdb.sig` | cosign signature bundle |
| `dn42-city.mmdb` | MaxMind GeoLite2-City compatible database |
| `dn42-city.mmdb.sha256` | SHA-256 checksum |
| `dn42-city.mmdb.sig` | cosign signature bundle |
| `sbom.spdx.json` | Software Bill of Materials (SBOM) in SPDX format |

SLSA Build Provenance attestation via GitHub's attestation service covers all three databases and their checksum files.

Note that MMDB output is not byte-reproducible: `mmdb_writer` stamps a `build_epoch` into the file metadata, so two builds from an identical registry checkout produce identical records but different checksums.
Integrity is established by the published checksum and signature for a given release, not by rebuilding.

## Verification

### Checksum Verification

Verify file integrity using `sha256sum`:

```sh
sha256sum -c dn42-asn.mmdb.sha256
sha256sum -c dn42-country.mmdb.sha256
sha256sum -c dn42-city.mmdb.sha256
```

### Signature Verification

Verify cosign keyless signatures on published release assets.
Each database has its own bundle, so run this once per database:

The certificate identity ends in `@refs/heads/main`, not a tag: the release workflow is triggered by `schedule` and `workflow_dispatch` from the default branch, and the tag is created afterwards by the job itself.

```sh
for db in dn42-asn.mmdb dn42-country.mmdb dn42-city.mmdb; do
  cosign verify-blob \
    --certificate-identity "https://github.com/no42-org/dn42-mmdb/.github/workflows/release.yml@refs/heads/main" \
    --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
    --bundle "$db.sig" \
    "$db"
done
```

### Build Provenance Verification

Verify SLSA build provenance using the GitHub CLI:

```sh
gh attestation verify dn42-asn.mmdb --repo no42-org/dn42-mmdb
gh attestation verify dn42-country.mmdb --repo no42-org/dn42-mmdb
gh attestation verify dn42-city.mmdb --repo no42-org/dn42-mmdb
```
