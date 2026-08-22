#!/usr/bin/env python3
# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT
"""Build GeoLite2-Country and GeoLite2-City compatible MMDBs from a dn42 registry.

Reads data/inetnum and data/inet6num for the `country:` attribute, and an
optional geofeed snapshot (see tools/sync_geofeed.py) for city-level detail.
Both databases come out of one pass: City is Country plus the geofeed overlay,
so parsing the registry twice would be wasted work.

The records carry the GeoLite2 structure, and the metadata database_type is
`GeoLite2-Country` and `GeoLite2-City` respectively, so any MaxMind reader
accepts the files unchanged.
"""

import argparse
import csv
import os
import re
import sys

from mmdb_writer import MMDBWriter
from netaddr import IPNetwork, IPSet

import iso_countries
from dn42_registry import PREFIX_ERRORS, iter_objects, parse_object, warn

# ISO 3166-2 subdivision codes look like `US-CA` or `JP-13`. Geofeeds in the
# wild also carry free text ("Bavaria", "California") and bare numbers; those
# are dropped rather than guessed at.
SUBDIVISION_RE = re.compile(r"^([A-Z]{2})-([A-Z0-9]{1,3})$")

REMARKS_GEOFEED_RE = re.compile(r"^geofeed\s+(\S+)$", re.IGNORECASE)

# Carries the parsed region between load_geofeed and merge. Popped before the
# record is written, so it never reaches the database.
_REGION = "_region"


def country_record(code):
    return {"iso_code": code, "names": {"en": iso_countries.name(code)}}


def collect_allocations(registry, subdir):
    """Yield (IPNetwork, record) for every inetnum/inet6num with usable country.

    Returns (allocations, registered, declaring, stats) where `registered` maps
    a network to its registry country code, which the city builder needs for
    registered_country even when a geofeed overrides the located country, and
    `declaring` maps each declared geofeed URL to the networks that declare it.

    Keying by URL rather than collecting one flat set matters: a row may only
    describe space held by the object that published the feed the row came
    from. A flat set would let one member's feed vouch for another member's
    prefixes, which is exactly what RFC 9632 discovery is meant to prevent.
    """
    allocations = {}
    registered = {}
    declaring = {}
    stats = {"objects": 0, "no_country": 0, "unusable": 0, "skipped": 0,
             "anycast": 0}

    for name, path in iter_objects(registry, subdir):
        try:
            attrs = parse_object(path)
            prefix = IPNetwork(attrs["cidr"][0])
        except (KeyError, OSError, *PREFIX_ERRORS) as exc:
            warn("skipping %s/%s: %s" % (subdir, name, exc))
            stats["skipped"] += 1
            continue

        stats["objects"] += 1

        # Collected before any country handling: an object may declare a
        # geofeed without carrying a country of its own. Empty values are
        # ignored, since a bare `geofeed:` line publishes nothing and must not
        # become an authority for anyone's prefixes.
        for url in attrs.get("geofeed", []):
            if url.strip():
                declaring.setdefault(url.strip(), []).append(prefix)
        for remark in attrs.get("remarks", []):
            m = REMARKS_GEOFEED_RE.match(remark.strip())
            if m:
                declaring.setdefault(m.group(1), []).append(prefix)

        raw = attrs.get("country", [])
        if not raw:
            stats["no_country"] += 1
            continue

        codes = []
        for value in raw:
            code = iso_countries.normalize(value)
            if code is None:
                warn("%s/%s: unusable country %r" % (subdir, name, value))
                continue
            if code not in codes:
                codes.append(code)

        if not codes:
            # Every value on this object was unusable. Counted once per
            # object, so the totals stay comparable with the object count.
            stats["unusable"] += 1
            continue

        if len(codes) > 1:
            # An allocation spanning several countries is anycast or
            # multi-site. There is no correct single country, and saying
            # "anycast" is truer than picking one.
            warn("%s/%s spans %s, marking anycast"
                 % (subdir, name, ", ".join(sorted(codes))))
            stats["anycast"] += 1
            allocations[prefix] = {"traits": {"is_anycast": True}}
            continue

        code = codes[0]
        registered[prefix] = code
        allocations[prefix] = {
            "country": country_record(code),
            "registered_country": country_record(code),
        }

    return allocations, registered, declaring, stats


def load_geofeed(path, declaring):
    """Read the geofeed snapshot into {IPNetwork: record}.

    Rows are re-validated against the registry here, not only in the sync
    tool, so an unreviewed row cannot reach a signed artifact. Authority
    comes from `declaring`, which is built from the registry checkout. The
    snapshot's own `inetnum` column is provenance metadata and is never
    trusted to authorize anything.
    """
    overlay = {}
    stats = {"rows": 0, "rejected": 0, "unbounded": 0}
    if not path:
        return overlay, stats
    if not os.path.exists(path):
        warn("no geofeed snapshot at %s, building city data from the registry "
             "alone" % path)
        return overlay, stats

    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            try:
                prefix = IPNetwork(row["prefix"])
            except (KeyError, *PREFIX_ERRORS):
                warn("geofeed: unparseable prefix %r" % row.get("prefix"))
                stats["rejected"] += 1
                continue

            source = (row.get("source") or "").strip()
            if not _authorized(prefix, row.get("inetnum") or "", source,
                               declaring):
                warn("geofeed: %s is not held by any object declaring %r, "
                     "rejecting" % (prefix, source or "<no source>"))
                stats["unbounded"] += 1
                continue

            code = iso_countries.normalize(row.get("country"))
            record = {}
            if code:
                record["country"] = country_record(code)

            city = (row.get("city") or "").strip()
            if city:
                record["city"] = {"names": {"en": city}}

            # The subdivision is resolved in merge(), where the record's final
            # country is known. A row may legitimately omit the country and
            # still name a valid region for the allocation's country.
            region = _region_code(row.get("region"))
            if region:
                record[_REGION] = region

            if not record:
                stats["rejected"] += 1
                continue

            overlay[prefix] = record

    return overlay, stats


def _authorized(prefix, claimed, source, declaring):
    """True when the object publishing `source` actually holds this prefix.

    Authority is per feed, not registry-wide. A row is accepted only if the
    registry object that declares the row's own source URL contains its
    prefix, so one member's feed cannot describe another member's space even
    though both publish geofeeds.

    `claimed` is the snapshot's own `inetnum` column. It is provenance, not
    authority: when present it must name one of the real declaring objects,
    so a hand-edited row cannot vouch for itself.
    """
    if not source:
        return False
    covering = [net for net in declaring.get(source, []) if prefix in net]
    if not covering:
        return False
    if not claimed:
        return True
    try:
        return IPNetwork(claimed) in covering
    except PREFIX_ERRORS:
        return False


def _region_code(region):
    """Split an ISO 3166-2 region into (country, subdivision), or None.

    Geofeeds in the wild also carry free text ("Bavaria", "California") and
    bare numbers. Those are dropped rather than guessed at.
    """
    if not region:
        return None
    m = SUBDIVISION_RE.match(region.strip().upper())
    return (m.group(1), m.group(2)) if m else None


def merge(base, overlay_record, registered_code):
    """Overlay a geofeed record onto the allocation's registry data.

    `country` is where the address is located and comes from the geofeed when
    present. `registered_country` is where the block is registered and always
    comes from the registry. That is MaxMind's own distinction.
    """
    record = dict(overlay_record)
    region = record.pop(_REGION, None)
    if registered_code:
        record["registered_country"] = country_record(registered_code)
    if "country" not in record and "country" in base:
        record["country"] = base["country"]
    # Resolve the subdivision against whichever country the record ends up
    # with, so `DE-BY` on a row with no country still applies under a German
    # allocation, while `US-CA` never rides along on a German one.
    if region:
        located = record.get("country", {}).get("iso_code")
        if located and region[0] == located:
            record["subdivisions"] = [{"iso_code": region[1],
                                       "names": {"en": region[1]}}]
    # An anycast allocation stays anycast when a geofeed adds detail inside
    # it, or the two databases would contradict each other for the same address.
    if "traits" in base:
        record["traits"] = base["traits"]
    return record


def write_db(path, database_type, description, entries):
    writer = MMDBWriter(
        ip_version=6,
        ipv4_compatible=True,
        int_type="u32",
        database_type=database_type,
        languages=["en"],
        description={"en": description},
    )
    # Broad prefixes first: later inserts overwrite the overlap, so the most
    # specific network wins on lookup. This is what lets a geofeed /32 beat
    # the /27 it sits inside.
    for prefix, record in sorted(entries.items(),
                                 key=lambda e: (e[0].prefixlen, str(e[0]))):
        writer.insert_network(IPSet([prefix]), record)
    writer.to_db_file(path)


def main():
    parser = argparse.ArgumentParser(
        description="Build GeoLite2-Country and GeoLite2-City compatible mmdbs "
                    "from the dn42 registry")
    parser.add_argument("--registry", required=True,
                        help="path to a dn42 registry checkout")
    parser.add_argument("--geofeed", default="data/geofeed.csv",
                        help="geofeed snapshot to overlay (default: %(default)s)")
    parser.add_argument("--country-output", default="dn42-country.mmdb",
                        help="country database (default: %(default)s)")
    parser.add_argument("--city-output", default="dn42-city.mmdb",
                        help="city database (default: %(default)s)")
    args = parser.parse_args()

    allocations = {}
    registered = {}
    declaring = {}
    totals = {"objects": 0, "no_country": 0, "unusable": 0, "skipped": 0,
              "anycast": 0}
    for subdir in ("inetnum", "inet6num"):
        found, reg, decl, stats = collect_allocations(args.registry, subdir)
        allocations.update(found)
        registered.update(reg)
        for url, nets in decl.items():
            declaring.setdefault(url, []).extend(nets)
        for key, value in stats.items():
            totals[key] += value

    if not allocations:
        print("error: no inetnum objects yielded a country", file=sys.stderr)
        return 1

    overlay, geo_stats = load_geofeed(args.geofeed, declaring)

    city = dict(allocations)
    for prefix, record in overlay.items():
        base = allocations.get(prefix) or _covering_record(prefix, allocations)
        code = registered.get(prefix) or _registered_for(prefix, registered)
        city[prefix] = merge(base, record, code)

    write_db(args.country_output, "GeoLite2-Country",
             "DN42 country database built from the dn42 registry", allocations)
    write_db(args.city_output, "GeoLite2-City",
             "DN42 city database built from the dn42 registry and geofeeds",
             city)

    print("wrote %s: %d networks" % (args.country_output, len(allocations)))
    print("wrote %s: %d networks (%d from geofeeds)"
          % (args.city_output, len(city), len(overlay)))
    print("registry: %d objects, %d without country, %d with only unusable "
          "country values, %d anycast, %d unparseable"
          % (totals["objects"], totals["no_country"], totals["unusable"],
             totals["anycast"], totals["skipped"]))
    print("geofeed: %d rows, %d rejected, %d outside their declaring object"
          % (geo_stats["rows"], geo_stats["rejected"], geo_stats["unbounded"]))
    return 0


def _registered_for(prefix, registered):
    """Registry country of the most specific allocation covering a prefix."""
    best = None
    for net, code in registered.items():
        if prefix not in net:
            continue
        if best is None or net.prefixlen > best[0].prefixlen:
            best = (net, code)
    return best[1] if best else None


def _covering_record(prefix, allocations):
    """Record of the most specific allocation covering a prefix, or {}.

    A geofeed row usually names space inside an allocation rather than the
    allocation itself, so traits such as is_anycast have to be inherited.
    """
    best = None
    for net, record in allocations.items():
        if prefix not in net:
            continue
        if best is None or net.prefixlen > best[0].prefixlen:
            best = (net, record)
    return best[1] if best else {}


if __name__ == "__main__":
    sys.exit(main())
