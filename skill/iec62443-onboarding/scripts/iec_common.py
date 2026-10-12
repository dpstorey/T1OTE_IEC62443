# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for the IEC 62443 onboarding scripts (stdlib only).

The normalised model (what every channel produces and every script consumes):

{
  "site":     {"name": str, "customer": str, "notes": str},
  "zones":    [{"name", "description", "purdue_level": int|None, "sl_target": int|None, "criticality": str}],
  "members":  [{"zone", "method", "value", "end", "comment"}],
  "conduits": [{"name", "zone_a", "zone_b", "direction", "allowed_protocols": [str], "description"}],
  "options":  {"create_sample_groups": bool, "create_sample_policies": bool, "policies_enabled": bool,
               "severity": "low|medium|high", "name_prefix": str, "direction_tolerant": bool,
               "allow_overlap": bool}
}

Zone = a set of asset groups (horizontal). Conduit = detection policies (vertical).
Direction is single and strict by default (a_to_b | b_to_a); "bidirectional" must be explicit.
"""

from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

METHODS = ("cidr", "range", "ip_list", "vlan", "asset_names", "filter")
DIRECTIONS = ("a_to_b", "b_to_a", "bidirectional")
SEVERITIES = ("low", "medium", "high")
RESERVED_ZONE_NAMES = {"any", "all", "none", "internet", "external", "unzoned", "outside"}

SKILL_DIR = Path(__file__).resolve().parent.parent

DEFAULT_OPTIONS: dict[str, Any] = {
    "create_sample_groups": False,
    "create_sample_policies": False,
    "policies_enabled": False,  # recommended for a first onboarding
    "severity": "medium",
    "name_prefix": "IEC62443",
    "direction_tolerant": False,
    "allow_overlap": False,
}


def load_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj: Any, path: str | None = None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    if path and path != "-":
        Path(path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def load_protocols() -> dict[str, Any]:
    return load_json(SKILL_DIR / "references" / "protocols.json")


def protocol_key(name: str, catalog: dict[str, Any] | None = None) -> str | None:
    """Canonical catalogue key for a protocol name, or None if unknown."""
    cat = catalog or load_protocols()
    k = re.sub(r"\s+", " ", (name or "").strip().lower())
    k = cat["aliases"].get(k, k)
    return k if k in cat["protocols"] else None


def to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    return str(v).strip().lower() in ("y", "yes", "true", "1", "x", "on")


def to_int(v: Any) -> int | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return int(float(str(v).strip()))
    except ValueError:
        return None


def split_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [p.strip() for p in re.split(r"[,;\n]+", str(v)) if p.strip()]


def split_ips(v: Any) -> list[str]:
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [p for p in re.split(r"[\s,;]+", str(v or "")) if p]


def normalize_model(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a loosely-typed model (from xlsx/csv/chat) into canonical form."""
    site = {k: str((raw.get("site") or {}).get(k) or "").strip() for k in ("name", "customer", "notes")}
    zones = []
    for z in raw.get("zones") or []:
        zones.append(
            {
                "name": str(z.get("name") or "").strip(),
                "description": str(z.get("description") or "").strip(),
                "purdue_level": to_int(z.get("purdue_level")),
                "sl_target": to_int(z.get("sl_target")),
                "criticality": str(z.get("criticality") or "").strip().lower(),
            }
        )
    members = []
    for m in raw.get("members") or []:
        members.append(
            {
                "zone": str(m.get("zone") or "").strip(),
                "method": str(m.get("method") or "").strip().lower().replace("-", "_").replace(" ", "_"),
                "value": m.get("value") if isinstance(m.get("value"), (list, dict)) else str(m.get("value") or "").strip(),
                "end": str(m.get("end") or "").strip(),
                "comment": str(m.get("comment") or "").strip(),
            }
        )
    conduits = []
    for c in raw.get("conduits") or []:
        d = str(c.get("direction") or "").strip().lower().replace("-", "_").replace(" ", "_")
        d = {"a>b": "a_to_b", "b>a": "b_to_a", "both": "bidirectional", "two_way": "bidirectional"}.get(d, d)
        conduits.append(
            {
                "name": str(c.get("name") or "").strip(),
                "zone_a": str(c.get("zone_a") or "").strip(),
                "zone_b": str(c.get("zone_b") or "").strip(),
                "direction": d,
                "allowed_protocols": split_list(c.get("allowed_protocols")),
                "description": str(c.get("description") or "").strip(),
            }
        )
    o = {**DEFAULT_OPTIONS, **{k: v for k, v in (raw.get("options") or {}).items() if v not in (None, "")}}
    for k in ("create_sample_groups", "create_sample_policies", "policies_enabled", "direction_tolerant", "allow_overlap"):
        o[k] = to_bool(o[k], DEFAULT_OPTIONS[k])
    o["severity"] = str(o["severity"]).strip().lower()
    o["name_prefix"] = str(o["name_prefix"]).strip()
    return {"site": site, "zones": zones, "members": members, "conduits": conduits, "options": o}


# ---- address maths ---------------------------------------------------------


def member_ranges(m: dict[str, Any]) -> list[tuple[int, int, int]] | None:
    """(ip_version, first, last) integer ranges for a member, or None if the
    method has no address meaning (vlan/asset_names/filter). Raises ValueError
    on malformed input."""
    method = m["method"]
    if method == "cidr":
        net = ipaddress.ip_network(str(m["value"]), strict=True)
        return [(net.version, int(net.network_address), int(net.broadcast_address))]
    if method == "range":
        a, b = m["value"], m.get("end") or ""
        if not b and "-" in str(a):
            a, b = [p.strip() for p in str(a).split("-", 1)]
        lo, hi = ipaddress.ip_address(str(a).strip()), ipaddress.ip_address(str(b).strip())
        if lo.version != hi.version:
            raise ValueError("range mixes IPv4 and IPv6")
        if int(lo) > int(hi):
            raise ValueError(f"range start {lo} is after end {hi}")
        return [(lo.version, int(lo), int(hi))]
    if method == "ip_list":
        ips = split_ips(m["value"])
        if not ips:
            raise ValueError("ip_list is empty")
        out = []
        for ip in ips:
            a = ipaddress.ip_address(ip)
            out.append((a.version, int(a), int(a)))
        return out
    return None


def range_text(version: int, lo: int, hi: int) -> str:
    cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    return str(cls(lo)) if lo == hi else f"{cls(lo)}-{cls(hi)}"


def overlaps(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    return a[0] == b[0] and a[1] <= b[2] and b[1] <= a[2]


def zone_names(model: dict[str, Any]) -> list[str]:
    return [z["name"] for z in model["zones"]]


def members_of(model: dict[str, Any], zone: str) -> list[dict[str, Any]]:
    return [m for m in model["members"] if m["zone"].lower() == zone.lower()]
