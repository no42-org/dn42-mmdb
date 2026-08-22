#!/usr/bin/env python3
# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT
"""Fetch RFC 8805 geofeeds declared in the dn42 registry into a snapshot.

Discovery follows RFC 9632: a feed is found *through* the registry object
that holds the prefix, and that object bounds what the feed may describe.
Rows naming space outside the declaring object are rejected, so a feed can
only ever describe address space its own maintainer holds.

The result is committed to data/geofeed.csv rather than fetched at build
time, which keeps the release build offline and makes every change to
third-party data a reviewable diff.
"""

import argparse
import concurrent.futures
import csv
import io
import ipaddress
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dn42_registry import iter_objects, parse_object, warn  # noqa: E402

FIELDNAMES = ("prefix", "country", "region", "city", "source", "inetnum")

# The registry has a first-class `geofeed:` key. A handful of objects still
# use the older `remarks: geofeed <url>` convention, so both are accepted.
REMARKS_GEOFEED_RE = re.compile(r"^geofeed\s+(\S+)$", re.IGNORECASE)

USER_AGENT = "dn42-mmdb geofeed sync (+https://github.com/no42-org/dn42-mmdb)"

# Feed URLs come from third-party registry objects, so they are untrusted
# input to urlopen. The allowlist stops non-network schemes such as file://
# from reading the runner's filesystem.
#
# It does NOT make this SSRF-proof: urlopen follows redirects, so a declared
# https:// URL can still redirect to an internal address. Blocking that needs
# per-hop address filtering, which is not implemented here.
ALLOWED_SCHEMES = ("http", "https")

# A feed is a short CSV. Anything larger is a mistake or an attempt to
# exhaust the runner, and --timeout does not bound total transfer size.
MAX_FEED_BYTES = 8 * 1024 * 1024


def discover(registry):
    """Return {url: [IPNetwork, ...]} of feeds and the space that declares them."""
    feeds = {}
    for subdir in ("inetnum", "inet6num"):
        for name, path in iter_objects(registry, subdir):
            try:
                attrs = parse_object(path)
            except (ValueError, OSError) as exc:
                warn("skipping %s/%s: %s" % (subdir, name, exc))
                continue

            urls = list(attrs.get("geofeed", []))
            for remark in attrs.get("remarks", []):
                m = REMARKS_GEOFEED_RE.match(remark.strip())
                if m:
                    urls.append(m.group(1))
            if not urls:
                continue

            try:
                cidr = ipaddress.ip_network(attrs["cidr"][0], strict=False)
            except (KeyError, ValueError):
                warn("%s/%s declares a geofeed but has no usable cidr" % (subdir, name))
                continue

            for url in urls:
                feeds.setdefault(url.strip(), []).append(cidr)
    return feeds


def fetch(url, timeout):
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError("refusing %r scheme, expected one of %s"
                         % (scheme, ", ".join(ALLOWED_SCHEMES)))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read(MAX_FEED_BYTES + 1)
    if len(body) > MAX_FEED_BYTES:
        raise ValueError("feed exceeds %d bytes" % MAX_FEED_BYTES)
    return body.decode("utf-8", "replace")


def parse_feed(body, allowed):
    """Yield accepted rows; return counts of what was rejected and why."""
    rows = []
    counts = {"unparseable": 0, "empty": 0, "unbounded": 0}

    for row in csv.reader(io.StringIO(body)):
        if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
            continue
        fields = [c.strip() for c in row] + [""] * (4 - len(row))
        try:
            prefix = ipaddress.ip_network(fields[0], strict=False)
        except ValueError:
            counts["unparseable"] += 1
            continue

        declaring = _declaring(prefix, allowed)
        if declaring is None:
            counts["unbounded"] += 1
            continue

        if not any(fields[1:4]):
            # A row naming a prefix and nothing else carries no information.
            counts["empty"] += 1
            continue

        rows.append({
            "prefix": str(prefix),
            "country": fields[1].upper(),
            "region": fields[2].upper(),
            "city": fields[3],
            "inetnum": str(declaring),
        })

    return rows, counts


def _declaring(prefix, allowed):
    """The most specific declaring network containing this prefix, or None."""
    best = None
    for net in allowed:
        if net.version != prefix.version or not prefix.subnet_of(net):
            continue
        if best is None or net.prefixlen > best.prefixlen:
            best = net
    return best


def load_existing(path):
    """Existing snapshot grouped by source URL, so unreachable feeds survive."""
    by_source = {}
    if not os.path.exists(path):
        return by_source
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            by_source.setdefault(row.get("source", ""), []).append(row)
    return by_source


def write_snapshot(path, rows):
    """Write rows in a stable order so an unchanged upstream is an empty diff."""
    rows = sorted(rows, key=lambda r: (
        ipaddress.ip_network(r["prefix"]).version,
        ipaddress.ip_network(r["prefix"]),
        r["source"],
    ))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})


def main():
    parser = argparse.ArgumentParser(
        description="Sync RFC 8805 geofeeds declared in the dn42 registry")
    parser.add_argument("--registry", required=True,
                        help="path to a dn42 registry checkout")
    parser.add_argument("-o", "--output", default="data/geofeed.csv",
                        help="snapshot to write (default: %(default)s)")
    parser.add_argument("--timeout", type=int, default=15,
                        help="per-feed timeout in seconds (default: %(default)s)")
    parser.add_argument("--jobs", type=int, default=12,
                        help="concurrent fetches (default: %(default)s)")
    args = parser.parse_args()

    feeds = discover(args.registry)
    if not feeds:
        print("error: no geofeed declarations found in the registry",
              file=sys.stderr)
        return 1

    existing = load_existing(args.output)
    accepted = []
    ok = unreachable = 0
    totals = {"unparseable": 0, "empty": 0, "unbounded": 0}

    def work(item):
        url, allowed = item
        try:
            return url, fetch(url, args.timeout), None
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad. One misbehaving feed must not abort the run
            # and lose the whole snapshot. http.client exceptions in
            # particular (IncompleteRead, BadStatusLine) are not OSError
            # subclasses, so naming families here would keep missing cases.
            return url, None, exc

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        for url, body, err in pool.map(work, sorted(feeds.items())):
            if err is not None:
                unreachable += 1
                kept = existing.get(url, [])
                warn("unreachable, keeping %d existing row(s): %s (%s)"
                     % (len(kept), url, err))
                accepted.extend(kept)
                continue

            ok += 1
            rows, counts = parse_feed(body, feeds[url])
            for key, value in counts.items():
                totals[key] += value
            if counts["unbounded"]:
                warn("%s: %d row(s) outside the declaring object, rejected"
                     % (url, counts["unbounded"]))
            for row in rows:
                row["source"] = url
            accepted.extend(rows)

    write_snapshot(args.output, accepted)

    print("wrote %s: %d rows from %d feed(s)"
          % (args.output, len(accepted), len(feeds)))
    print("feeds: %d fetched, %d unreachable" % (ok, unreachable))
    print("rows rejected: %d unparseable, %d without any location, "
          "%d outside their declaring object"
          % (totals["unparseable"], totals["empty"], totals["unbounded"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
