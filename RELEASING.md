# Release Process

This document describes how releases are generated, tagged, and verified for `dn42-asn.mmdb`.

## Versioning & Schedule

Releases use ISO date version tags (`vYYYY.MM.DD`).
Releases are built automatically every Monday at 03:00 UTC via GitHub Actions.
Releases can also be triggered on demand using the `workflow_dispatch` trigger in GitHub Actions.

## Release Artifacts

Each release publishes the following assets to GitHub Releases:

- `dn42-asn.mmdb`: MaxMind GeoLite2-ASN compatible database.
- `dn42-asn.mmdb.sha256`: SHA-256 checksum file.
- `sbom.spdx.json`: Software Bill of Materials (SBOM) in SPDX format.
- SLSA Build Provenance attestation via GitHub's attestation service.

## Verification

### Checksum Verification

Verify file integrity using `sha256sum`:

```sh
sha256sum -c dn42-asn.mmdb.sha256
```

### Signature Verification

Verify cosign keyless signatures on published release assets:

```sh
cosign verify-blob \
  --certificate-identity-regexp "^https://github\.com/no42-org/dn42-mmdb/\.github/workflows/release\.yml@refs/tags/v.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --bundle dn42-asn.mmdb.sig \
  dn42-asn.mmdb
```

### Build Provenance Verification

Verify SLSA build provenance using the GitHub CLI:

```sh
gh attestation verify dn42-asn.mmdb --repo no42-org/dn42-mmdb
```
