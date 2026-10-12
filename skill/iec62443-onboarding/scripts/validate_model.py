#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate a normalised model. Exit 0 = no errors (warnings allowed), 1 = errors.

usage: validate_model.py model.json [--out report.json]

Errors (block planning): bad CIDR/range/IP, host bits set in a CIDR, duplicate or
reserved zone names, zones with no address space, members of unknown zones,
conduits with unknown zones / same zone both ends / missing or invalid direction /
duplicate zone pair in the same direction, overlapping address space between
different zones (unless options.allow_overlap), bad severity.
Warnings: unknown protocols, conduits with no allowed protocols, zones with no
conduit, address methods that cannot be overlap-checked, direction-sensitive
(UDP/mixed) protocols on a strict conduit, unverified protocol names.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iec_common import (  # noqa: E402
    DIRECTIONS,
    METHODS,
    RESERVED_ZONE_NAMES,
    SEVERITIES,
    dump_json,
    load_json,
    load_protocols,
    member_ranges,
    normalize_model,
    overlaps,
    protocol_key,
    range_text,
)


def validate(model: dict) -> dict:
    model = normalize_model(model)
    errors: list[dict] = []
    warnings: list[dict] = []

    def err(code: str, msg: str, **kw) -> None:
        errors.append({"code": code, "message": msg, **kw})

    def warn(code: str, msg: str, **kw) -> None:
        warnings.append({"code": code, "message": msg, **kw})

    opts = model["options"]
    if not model["site"]["name"]:
        err("SITE_MISSING", "Site name is required.")
    if opts["severity"] not in SEVERITIES:
        err("BAD_SEVERITY", f"severity must be one of {SEVERITIES}; got {opts['severity']!r}.")
    if not opts["name_prefix"]:
        err("BAD_PREFIX", "name_prefix must not be empty (it marks everything the agent creates).")

    # ---- zones
    seen: dict[str, str] = {}
    for z in model["zones"]:
        n = z["name"]
        if not n:
            err("ZONE_NAME", "A zone has no name.")
            continue
        low = n.lower()
        if low in seen:
            err("ZONE_DUP", f"Duplicate zone name '{n}' (names are case-insensitive).", zone=n)
        seen[low] = n
        if low in RESERVED_ZONE_NAMES:
            err("ZONE_RESERVED", f"Zone name '{n}' is reserved; pick a descriptive name.", zone=n)
        if "|" in n:
            err("ZONE_CHARS", f"Zone name '{n}' contains '|', which the generated names use as a separator.", zone=n)
        if z["purdue_level"] is not None and not 0 <= z["purdue_level"] <= 5:
            err("PURDUE_RANGE", f"Zone '{n}': Purdue level must be 0-5.", zone=n)
        if z["sl_target"] is not None and not 1 <= z["sl_target"] <= 4:
            err("SLT_RANGE", f"Zone '{n}': SL-T must be 1-4.", zone=n)
    zset = set(seen)

    # ---- members
    zone_ranges: dict[str, list[tuple[tuple[int, int, int], str]]] = {}
    has_members: set[str] = set()
    for i, m in enumerate(model["members"], start=1):
        where = f"Address Space row {i}"
        if m["zone"].lower() not in zset:
            err("MEMBER_ZONE", f"{where}: zone '{m['zone']}' is not defined on the Zones sheet.", row=i)
            continue
        zlow = m["zone"].lower()
        if m["method"] not in METHODS:
            err("MEMBER_METHOD", f"{where}: method {m['method']!r} must be one of {METHODS}.", row=i)
            continue
        has_members.add(zlow)
        try:
            if m["method"] == "cidr":
                try:
                    ipaddress.ip_network(str(m["value"]), strict=True)
                except ValueError:
                    net = ipaddress.ip_network(str(m["value"]), strict=False)
                    raise ValueError(f"host bits set in '{m['value']}' - did you mean {net}?") from None
            rngs = member_ranges(m)
        except ValueError as exc:
            err("MEMBER_VALUE", f"{where} ({m['zone']}, {m['method']}): {exc}", row=i)
            continue
        if m["method"] == "filter":
            try:
                f = json.loads(m["value"]) if isinstance(m["value"], str) else m["value"]
                if not isinstance(f, dict):
                    raise ValueError("filter must be a JSON object")
            except ValueError as exc:
                err("MEMBER_FILTER", f"{where}: {exc}", row=i)
        if rngs is None:
            warn("NO_OVERLAP_CHECK", f"{where}: '{m['method']}' membership cannot be overlap-checked.", zone=m["zone"], row=i)
            continue
        for r in rngs:
            zone_ranges.setdefault(zlow, []).append((r, m["zone"]))
    for z in model["zones"]:
        if z["name"] and z["name"].lower() not in has_members:
            err("ZONE_EMPTY", f"Zone '{z['name']}' has no address space.", zone=z["name"])

    # ---- overlaps between different zones
    zl = sorted(zone_ranges)
    for ai in range(len(zl)):
        for bi in range(ai + 1, len(zl)):
            for ra, na in zone_ranges[zl[ai]]:
                for rb, nb in zone_ranges[zl[bi]]:
                    if overlaps(ra, rb):
                        lo, hi = max(ra[1], rb[1]), min(ra[2], rb[2])
                        msg = f"Zones '{na}' and '{nb}' overlap on {range_text(ra[0], lo, hi)}."
                        (warn if opts["allow_overlap"] else err)("ZONE_OVERLAP", msg, zones=[na, nb])

    # ---- conduits
    cat = load_protocols()
    pairs: set[tuple[str, str]] = set()
    names: set[str] = set()
    zones_with_conduit: set[str] = set()
    for c in model["conduits"]:
        label = c["name"] or f"{c['zone_a']}->{c['zone_b']}"
        if not c["name"]:
            err("CONDUIT_NAME", f"Conduit {c['zone_a']}/{c['zone_b']} has no name.")
        elif c["name"].lower() in names:
            err("CONDUIT_DUP", f"Duplicate conduit name '{c['name']}'.", conduit=c["name"])
        names.add(c["name"].lower())
        if "|" in c["name"]:
            err("CONDUIT_CHARS", f"Conduit '{c['name']}' contains '|'.", conduit=c["name"])
        a, b = c["zone_a"].lower(), c["zone_b"].lower()
        bad = False
        for side, z in (("A", c["zone_a"]), ("B", c["zone_b"])):
            if z.lower() not in zset:
                err("CONDUIT_ZONE", f"Conduit '{label}': zone {side} '{z}' is not defined.", conduit=label)
                bad = True
        if a == b and not bad:
            err("CONDUIT_SAME_ZONE", f"Conduit '{label}': both ends are zone '{c['zone_a']}'.", conduit=label)
            bad = True
        if c["direction"] not in DIRECTIONS:
            err("CONDUIT_DIRECTION", f"Conduit '{label}': direction must be one of {DIRECTIONS} (got {c['direction']!r}); it is never assumed.", conduit=label)
            bad = True
        if bad:
            continue
        zones_with_conduit |= {a, b}
        dirs = [(a, b)] if c["direction"] == "a_to_b" else [(b, a)] if c["direction"] == "b_to_a" else [(a, b), (b, a)]
        for d in dirs:
            if d in pairs:
                err("CONDUIT_DUP_PAIR", f"Conduit '{label}' repeats an already-declared initiator direction {d[0]} -> {d[1]}.", conduit=label)
            pairs.add(d)
        if not c["allowed_protocols"]:
            warn("CONDUIT_NO_PROTOCOLS", f"Conduit '{label}' lists no allowed protocols: no conformance policy will be generated, so any protocol passes.", conduit=label)
        sensitive = []
        for p in c["allowed_protocols"]:
            k = protocol_key(p, cat)
            if k is None:
                warn("PROTOCOL_UNKNOWN", f"Conduit '{label}': protocol '{p}' is not in the catalogue; add it to references/protocols.json or give TCP/UDP ports.", conduit=label, protocol=p)
                continue
            if cat["protocols"][k]["transport"] in ("udp", "mixed") and c["direction"] != "bidirectional" and not opts["direction_tolerant"]:
                sensitive.append(cat["protocols"][k]["label"])
        if sensitive:
            warn("DIRECTION_SENSITIVE", f"Conduit '{label}' is strict one-way but carries UDP/mixed protocols ({', '.join(sensitive)}); Tenable may infer direction wrongly for these, giving false alerts or misses.", conduit=label)
    if model["conduits"]:
        for z in model["zones"]:
            if z["name"] and z["name"].lower() not in zones_with_conduit:
                warn("ZONE_NO_CONDUIT", f"Zone '{z['name']}' has no conduit: all of its outbound traffic will be flagged.", zone=z["name"])
    else:
        warn("NO_CONDUITS", "No conduits declared: every cross-zone conversation will be flagged.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "zones": len(model["zones"]),
            "members": len(model["members"]),
            "conduits": len(model["conduits"]),
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", help="model.json (or parse_workbook output containing a 'model' key)")
    ap.add_argument("--out")
    a = ap.parse_args()
    data = load_json(a.model)
    report = validate(data.get("model", data))
    dump_json(report, a.out)
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
