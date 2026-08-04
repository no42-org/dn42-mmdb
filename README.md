# dn42-mmdb

[![CI Status](https://github.com/no42-org/dn42-mmdb/actions/workflows/release.yml/badge.svg)](https://github.com/no42-org/dn42-mmdb/actions/workflows/release.yml)
[![Latest Release](https://img.shields.io/github/v/release/no42-org/dn42-mmdb)](https://github.com/no42-org/dn42-mmdb/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Builds a GeoLite2-ASN-compatible MaxMind database (`dn42-asn.mmdb`) from a [dn42 registry](https://git.dn42.dev/dn42/registry) checkout.
It maps every registered prefix (`data/route/`, `data/route6/`) to its origin ASN and the ASN's `as-name` (`data/aut-num/`), so flow collectors and anything else speaking MaxMind MMDB can enrich DN42 traffic the same way they enrich public internet traffic with GeoLite2-ASN.

The records carry the exact GeoLite2-ASN structure (`autonomous_system_number`, `autonomous_system_organization`) and metadata type `GeoLite2-ASN`, so any MaxMind reader accepts the file unchanged.

All registry sources are included (DN42, ICVPN, NEONETWORK, CRXN, CHAOSVPN).
When a prefix has multiple origins, the numerically lowest ASN wins and a warning is printed.
Overlapping prefixes resolve by longest-prefix match, like BGP.

## Weekly Releases

Pre-built releases are automatically built and published every week driven by GitHub Actions.
You can download the latest database and SHA-256 checksum from GitHub Releases:

```sh
curl -LO https://github.com/no42-org/dn42-mmdb/releases/latest/download/dn42-asn.mmdb
curl -LO https://github.com/no42-org/dn42-mmdb/releases/latest/download/dn42-asn.mmdb.sha256
sha256sum -c dn42-asn.mmdb.sha256
```

## Automated Weekly Updates via Systemd

A Systemd service and timer unit are included in `systemd/` to fetch and verify the latest release weekly:

```sh
# Copy systemd unit files
sudo cp systemd/dn42-mmdb-update.service /etc/systemd/system/
sudo cp systemd/dn42-mmdb-update.timer /etc/systemd/system/

# Enable and start weekly timer (runs Mondays at 04:00 UTC)
sudo systemctl daemon-reload
sudo systemctl enable --now dn42-mmdb-update.timer
```

To run an immediate update manually:

```sh
sudo systemctl start dn42-mmdb-update.service
```

## Nix & NixOS Support

This repository includes a `flake.nix` for Nix and NixOS users:

### Development Shell

Drop into a pre-configured development environment:

```sh
nix develop
```

### Build & Run via Nix

Build or run the database generator directly:

```sh
nix build
nix run . -- --registry /path/to/registry -o dn42-asn.mmdb
```

### NixOS Module

Import the module in your NixOS configuration to enable automated weekly updates:

```nix
{
  inputs.dn42-mmdb.url = "github:no42-org/dn42-mmdb";

  outputs = { self, nixpkgs, dn42-mmdb, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      modules = [
        dn42-mmdb.nixosModules.default
        {
          services.dn42-mmdb = {
            enable = true;
            autoUpdate.enable = true;
          };
        }
      ];
    };
  };
}
```

## Usage

You need a dn42 registry checkout (requires dn42 access, or use the [public mirror](https://git.dn42.dev/dn42/registry)):

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build_asn_mmdb.py --registry /path/to/registry -o dn42-asn.mmdb
```

The script prints a summary on success and exits non-zero if nothing could be built:

```
wrote dn42-asn.mmdb: 2536 IPv4 + 2602 IPv6 prefixes, 2551 ASNs, 0 skipped
```

## Refreshing

The database is a snapshot of the registry checkout.
After pulling registry updates, rebuild and redeploy:

```sh
git -C /path/to/registry pull
.venv/bin/python build_asn_mmdb.py --registry /path/to/registry -o /usr/share/GeoIP/dn42-asn.mmdb
```

## Example: Riptide

Add the file as an extra GeoIP database in [Riptide](https://riptide.space/docs/), no other configuration needed:

```yaml
geoip:
    databases:
      - /usr/share/GeoIP/GeoLite2-ASN.mmdb
      - /usr/share/GeoIP/GeoLite2-City.mmdb
      - /usr/share/GeoIP/dn42-asn.mmdb
```

## Documentation

- [Contributing Guidelines](CONTRIBUTING.md)
- [Release Process](RELEASING.md)
- [Security Policy](SECURITY.md)

## License

[MIT](LICENSE)
