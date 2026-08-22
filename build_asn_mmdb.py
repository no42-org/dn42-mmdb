#!/usr/bin/env python3
# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT
"""Build a GeoLite2-ASN-compatible MMDB from a dn42 registry checkout.

Reads data/route, data/route6 and data/aut-num and writes an mmdb file
whose records look exactly like MaxMind's GeoLite2-ASN database, so it
can be used as a drop-in extra database for any MaxMind reader.
"""

import argparse
import re
import sys

from mmdb_writer import MMDBWriter
from netaddr import IPNetwork, IPSet

from dn42_registry import PREFIX_ERRORS, iter_objects, parse_object, warn

ASN_RE = re.compile(r"AS(\d+)")


def collect_routes(registry, subdir, prefix_key):
    """Yield (IPNetwork, [asn, ...]) for every parseable object; count skips."""
    routes = {}
    skipped = 0
    for name, path in iter_objects(registry, subdir):
        try:
            attrs = parse_object(path)
            prefix = IPNetwork(attrs[prefix_key][0])
            origins = [int(m.group(1))
                       for v in attrs.get("origin", [])
                       for m in [ASN_RE.search(v)] if m]
            if not origins:
                raise ValueError("no origin")
        except (KeyError, OSError, *PREFIX_ERRORS) as exc:
            warn("skipping %s/%s: %s" % (subdir, name, exc))
            skipped += 1
            continue
        routes.setdefault(prefix, []).extend(origins)
    return routes, skipped


def collect_as_names(registry):
    names = {}
    for name, path in iter_objects(registry, "aut-num"):
        m = ASN_RE.fullmatch(name)
        if not m:
            continue
        try:
            attrs = parse_object(path)
            names[int(m.group(1))] = attrs["as-name"][0]
        except (KeyError, OSError, *PREFIX_ERRORS) as exc:
            warn("skipping aut-num/%s: %s" % (name, exc))
    return names


def resolve_origin(prefix, origins):
    """Lowest ASN wins when a prefix has more than one origin."""
    unique = sorted(set(origins))
    if len(unique) > 1:
        warn("%s has multiple origins %s, using AS%d"
             % (prefix, ["AS%d" % a for a in unique], unique[0]))
    return unique[0]


def main():
    parser = argparse.ArgumentParser(
        description="Build a GeoLite2-ASN-compatible mmdb from the dn42 registry")
    parser.add_argument("--registry", required=True,
                        help="path to a dn42 registry checkout")
    parser.add_argument("-o", "--output", default="dn42-asn.mmdb",
                        help="output file (default: %(default)s)")
    args = parser.parse_args()

    routes4, skipped4 = collect_routes(args.registry, "route", "route")
    routes6, skipped6 = collect_routes(args.registry, "route6", "route6")
    as_names = collect_as_names(args.registry)

    entries = [(prefix, resolve_origin(prefix, origins))
               for routes in (routes4, routes6)
               for prefix, origins in routes.items()]
    if not entries:
        print("error: no route objects could be parsed", file=sys.stderr)
        return 1

    writer = MMDBWriter(
        ip_version=6,
        ipv4_compatible=True,
        int_type="u32",
        database_type="GeoLite2-ASN",
        languages=["en"],
        description={"en": "DN42 ASN database built from the dn42 registry"},
    )
    # Broad prefixes first: later inserts overwrite the overlap, so the
    # most specific route wins on lookup, matching BGP semantics.
    for prefix, asn in sorted(entries, key=lambda e: (e[0].prefixlen, str(e[0]))):
        writer.insert_network(IPSet([prefix]), {
            "autonomous_system_number": asn,
            "autonomous_system_organization": as_names.get(asn, "AS%d" % asn),
        })
    writer.to_db_file(args.output)

    print("wrote %s: %d IPv4 + %d IPv6 prefixes, %d ASNs, %d skipped"
          % (args.output, len(routes4), len(routes6),
             len({asn for _, asn in entries}), skipped4 + skipped6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
