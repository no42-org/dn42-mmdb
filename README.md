# dn42-mmdb

[![CI Status](https://github.com/no42-org/dn42-mmdb/actions/workflows/release.yml/badge.svg)](https://github.com/no42-org/dn42-mmdb/actions/workflows/release.yml)
[![Latest Release](https://img.shields.io/github/v/release/no42-org/dn42-mmdb)](https://github.com/no42-org/dn42-mmdb/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Builds MaxMind-compatible databases from a [dn42 registry](https://git.dn42.dev/dn42/registry) checkout, so flow collectors and anything else speaking MMDB can enrich DN42 traffic the same way they enrich public internet traffic with GeoLite2.

MaxMind ships GeoLite2 as three separate files, and so does this project:

| File | `database_type` | Reader method | Built from |
| --- | --- | --- | --- |
| `dn42-asn.mmdb` | `GeoLite2-ASN` | `.asn()` | `data/route`, `data/route6`, `data/aut-num` |
| `dn42-country.mmdb` | `GeoLite2-Country` | `.country()` | `country:` on `data/inetnum`, `data/inet6num` |
| `dn42-city.mmdb` | `GeoLite2-City` | `.city()` | the above plus RFC 8805 geofeeds |

The records carry the exact GeoLite2 structure, so any MaxMind reader accepts the files unchanged.
Note that the MaxMind reader gates its methods on `database_type`: `.country()` does not work against a City database, exactly as with upstream GeoLite2.

All registry sources are included (DN42, ICVPN, NEONETWORK, CRXN, CHAOSVPN).
When a prefix has multiple origins, the numerically lowest ASN wins and a warning is printed.
Overlapping prefixes resolve by longest-prefix match, like BGP, which is also what lets a geofeed `/32` override the allocation it sits inside.

## Coverage

Location data in dn42 is partial, and these databases do not hide that.
Against a recent registry snapshot:

- **ASN**: 5138 routed prefixes, essentially complete.
- **Country**: 3717 networks. About 72% of routed prefixes resolve to a single country; roughly 28% have no `country:` anywhere in their allocation chain, and those simply miss on lookup.
- **City**: 4236 networks, of which 520 carry geofeed detail. City-level data exists only where an operator publishes a geofeed.

An allocation listing several countries is treated as anycast: it carries `traits.is_anycast` and no `country`, because there is no correct single answer.
Geofeed detail inside such an allocation keeps the anycast marker.
Registry country values that are not ISO 3166-1 alpha-2 are rejected with a warning, except `UK`, which is normalized to `GB`.

Two limits worth knowing before you rely on the city database:

- Subdivision records carry the ISO 3166-2 subdivision code (`CA` for `US-CA`, matching MaxMind's own schema) but no proper name, so readers display the code where they would normally show "California". Geofeeds supply only the code.
- Region values that are not valid ISO 3166-2 are dropped entirely rather than guessed at. Feeds in the wild carry values like `Bavaria`, `California` and bare numbers.

## Weekly Releases

Pre-built releases are automatically built and published every week driven by GitHub Actions.
You can download the latest database and SHA-256 checksum from GitHub Releases:

```sh
BASE=https://github.com/no42-org/dn42-mmdb/releases/latest/download
for db in dn42-asn.mmdb dn42-country.mmdb dn42-city.mmdb; do
  curl -LO "$BASE/$db"
  curl -LO "$BASE/$db.sha256"
  sha256sum -c "$db.sha256"
done
```

Fetch only the databases you need; they are independent files.

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
nix run .#dn42-mmdb -- --help
```

The package installs three entry points: `dn42-mmdb` (ASN), `dn42-geo-mmdb` (country and city), and `dn42-geofeed-sync`.

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
            # Defaults to all three; narrow it if you only need some.
            databases = [ "asn" "country" "city" ];
            stateDir = "/var/lib/dn42";
          };
        }
      ];
    };
  };
}
```

## Usage

You need a [dn42 registry](https://git.dn42.dev/dn42/registry) git checkout which requires an account:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make build REGISTRY=/path/to/registry PYTHON=.venv/bin/python
```

`make build` writes all three databases.
`make dn42-asn.mmdb` builds only the ASN database; the two geo databases come out of a single builder, so asking for either writes both.
The builders print a summary on success and exit non-zero if nothing could be built:

```
wrote dn42-asn.mmdb: 2536 IPv4 + 2602 IPv6 prefixes, 2551 ASNs, 0 skipped
wrote dn42-country.mmdb: 3717 networks
wrote dn42-city.mmdb: 4236 networks (520 from geofeeds)
registry: 5334 objects, 1612 without country, 18 anycast, 5 rejected
geofeed: 520 rows, 0 rejected, 0 outside their declaring object
```

The build performs no network access. It reads the registry checkout and the committed geofeed snapshot at `data/geofeed.csv`, nothing else.

## Geofeed Data

City-level detail comes from [RFC 8805](https://www.rfc-editor.org/rfc/rfc8805.html) geofeeds, discovered through the `geofeed:` attribute on `inetnum` and `inet6num` objects as described by [RFC 9632](https://www.rfc-editor.org/rfc/rfc9632.html).

Fetching them is a separate stage from building, so the release build stays offline and every change to third-party data arrives as a reviewable diff:

```sh
make sync REGISTRY=/path/to/registry     # refreshes data/geofeed.csv
```

A geofeed is an arbitrary URL naming IP prefixes, so the registry object that declares a feed bounds what that feed may describe.
Rows naming space outside the declaring `inetnum` are rejected, by the sync tool and again at build time.

The weekly release workflow runs this and opens a pull request when the snapshot changes.
Roughly half the declared feeds are on `.dn42` hostnames and are unreachable from GitHub-hosted runners; the tool reports them as unreachable and keeps their existing rows rather than dropping them.
**If you have a dn42-connected host, running `make sync` there and opening a pull request is the only way that data reaches the database.**

## Refreshing

The database is a snapshot of the registry checkout.
After pulling registry updates, rebuild and redeploy:

```sh
git -C /path/to/registry pull
make build REGISTRY=/path/to/registry PYTHON=.venv/bin/python
cp dn42-asn.mmdb dn42-country.mmdb dn42-city.mmdb /usr/share/GeoIP/
```

## Example: Riptide

Add the file as an extra GeoIP database in [Riptide](https://riptide.space/), no other configuration needed:

```yaml
geoip:
    databases:
      - /usr/share/GeoIP/GeoLite2-ASN.mmdb
      - /usr/share/GeoIP/GeoLite2-City.mmdb
      - /usr/share/GeoIP/dn42-asn.mmdb
      - /usr/share/GeoIP/dn42-city.mmdb
```

`dn42-country.mmdb` is deliberately absent.
`dn42-city.mmdb` already answers for every prefix it covers, and carries the located country as well as the registered one, so loading both adds nothing.
Use the country database instead of the city one if you want the smaller file or need `.country()`, which a City database refuses, but not both.
The same is true upstream, which is why the example lists `GeoLite2-City.mmdb` and not `GeoLite2-Country.mmdb`.

## Documentation

- [Contributing Guidelines](CONTRIBUTING.md)
- [Release Process](RELEASING.md)
- [Security Policy](SECURITY.md)

## License

[MIT](LICENSE)
