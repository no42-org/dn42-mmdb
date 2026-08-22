# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: MIT
"""Shared helpers for reading a dn42 registry checkout.

Every builder parses the same RPSL objects out of the same directory
layout, so the format handling lives here and gets fixed in one place.
"""

import os
import sys

from netaddr import AddrFormatError

# netaddr raises AddrFormatError, which derives straight from Exception rather
# than from ValueError. Catching ValueError alone therefore lets a single
# malformed prefix in ~5000 third-party registry objects abort a whole build
# with a traceback instead of warning and skipping that object.
PREFIX_ERRORS = (AddrFormatError, ValueError, TypeError)


def warn(msg):
    print("WARNING: %s" % msg, file=sys.stderr)


def parse_object(path):
    """Parse an RPSL-style registry object into {key: [values]}.

    Continuation lines (leading whitespace or '+') extend the previous value.
    Unknown keys are kept; the caller picks what it needs.
    """
    attrs = {}
    last_key = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line[0] in (" ", "\t", "+") and last_key:
                cont = line.lstrip("+ \t")
                if cont:
                    attrs[last_key][-1] += " " + cont
                continue
            key, sep, value = line.partition(":")
            if not sep:
                raise ValueError("malformed line: %r" % line)
            key = key.strip().lower()
            attrs.setdefault(key, []).append(value.strip())
            last_key = key
    return attrs


def registry_dir(registry, subdir):
    """Locate an object directory, accepting a checkout with or without data/."""
    dirpath = os.path.join(registry, "data", subdir)
    if not os.path.isdir(dirpath):
        dirpath = os.path.join(registry, subdir)
    return dirpath


def iter_objects(registry, subdir):
    """Yield (name, path) for every object in a registry subdirectory.

    A missing directory warns and yields nothing rather than raising: the
    listing happens inside the caller's `for` statement, outside its
    per-object error handling, so an exception here would escape as a raw
    traceback instead of the caller's own "nothing usable found" error.
    """
    dirpath = registry_dir(registry, subdir)
    try:
        names = sorted(os.listdir(dirpath))
    except OSError as exc:
        warn("cannot read %s: %s" % (dirpath, exc))
        return
    for name in names:
        yield name, os.path.join(dirpath, name)
