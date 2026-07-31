# dn42-mmdb

Builds a GeoLite2-ASN-compatible MaxMind database (`dn42-asn.mmdb`) from a [dn42 registry](https://git.dn42.dev/dn42/registry) checkout.
It maps every registered prefix (`data/route/`, `data/route6/`) to its origin ASN and the ASN's `as-name` (`data/aut-num/`), so flow collectors and anything else speaking MaxMind MMDB can enrich DN42 traffic the same way they enrich public internet traffic with GeoLite2-ASN.

The records carry the exact GeoLite2-ASN structure (`autonomous_system_number`, `autonomous_system_organization`) and metadata type `GeoLite2-ASN`, so any MaxMind reader accepts the file unchanged.

All registry sources are included (DN42, ICVPN, NEONETWORK, CRXN, CHAOSVPN).
When a prefix has multiple origins, the numerically lowest ASN wins and a warning is printed.
Overlapping prefixes resolve by longest-prefix match, like BGP.

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

Add the file as an extra GeoIP database, no other configuration needed:

```yaml
geoip:
    databases:
      - /usr/share/GeoIP/GeoLite2-ASN.mmdb
      - /usr/share/GeoIP/GeoLite2-City.mmdb
      - /usr/share/GeoIP/dn42-asn.mmdb
```

## License

[MIT](LICENSE)
