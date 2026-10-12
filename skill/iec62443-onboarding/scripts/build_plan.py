#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the ordered plan of EM-MCP calls from a validated model.

usage: build_plan.py model.json [--existing existing.json] [--out plan.json] [--format json|md]

--existing (assembled by the agent from list_* calls, all optional):
  {"asset_groups":[{"name","id"}], "protocol_groups":[{"name","id"}],
   "schedule_groups":[{"name","id"}], "policies":[{"title","id"}]}
Objects whose name already exists become action "skip" with their id recorded.

Symbolic references: tool arguments contain "$ref:<kind>:<name>" (optionally
prefixed "!" for negation). journal.py resolves them to real ids as steps are
applied. Nothing here talks to Tenable.

Tools used: create_asset_group, create_protocol_group, create_conversation_policy (all core policies)
and create_asset_policy (sample 'new asset in zone' only).

Policy set (strategy S1, single strict direction):
  * boundary-out per zone: zone -> not in zone and not in a zone it may initiate to
  * unzoned -> zones: source in no declared zone, destination in any zone
  * conformance per conduit direction: A -> B using a protocol NOT in the conduit's allowed set
Count = zones + 1 + one per conduit direction (with allowed protocols).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iec_common import (  # noqa: E402
    dump_json,
    load_json,
    load_protocols,
    members_of,
    normalize_model,
    protocol_key,
    split_ips,
    SKILL_DIR,
)

SEP = " | "
POLICY_TOOLS = {"protocol": "create_conversation_policy", "asset": "create_asset_policy"}
SCHED_NAME = "Any Time"
ANY_PROTO_NAME = "Any protocol"


class Plan:
    def __init__(self, existing: dict[str, Any]):
        self.steps: list[dict[str, Any]] = []
        self.known: dict[str, str] = {}
        self.warnings: list[str] = []
        self.blocked: list[str] = []

        def idx(items: list[dict[str, Any]] | None, key: str) -> dict[str, str]:
            return {str(i.get(key, "")).strip().lower(): str(i.get("id")) for i in (items or []) if i.get("id")}

        self.ex_ag = idx(existing.get("asset_groups"), "name")
        self.ex_pg = idx(existing.get("protocol_groups"), "name")
        self.ex_sg = idx(existing.get("schedule_groups"), "name")
        self.ex_pol = idx(existing.get("policies"), "title")

    def add(self, phase: str, tool: str, args: dict[str, Any], *, ref: str | None = None, risk: str = "low",
            reversible: bool = True, undo: dict[str, Any] | None = None, note: str = "", action: str = "create",
            existing_id: str | None = None) -> None:
        if action == "skip" and ref and existing_id:
            self.known[ref] = existing_id
        step = {
            "n": len(self.steps) + 1,
            "phase": phase,
            "action": action,
            "tool": tool,
            "args": args,
            "ref": ref,
            "risk": risk,
            "reversible": reversible,
            "undo": undo,
            "note": note,
        }
        if existing_id:
            step["existing_id"] = existing_id
        self.steps.append(step)


def _group_name(prefix: str, zone: str, i: int, total: int) -> str:
    base = f"{prefix}{SEP}Zone{SEP}{zone}"
    return base if total == 1 else f"{base}{SEP}{i}"


def _member_args(m: dict[str, Any], name: str, zone: str) -> tuple[dict[str, Any] | None, str]:
    desc = f"IEC 62443 zone '{zone}'" + (f" - {m['comment']}" if m["comment"] else "")
    a: dict[str, Any] = {"name": name, "description": desc, "display_tag": True}
    meth = m["method"]
    if meth == "cidr":
        a["cidr"] = str(m["value"])
    elif meth == "range":
        lo, hi = m["value"], m.get("end")
        if not hi and "-" in str(lo):
            lo, hi = [p.strip() for p in str(lo).split("-", 1)]
        a["start_ip"], a["end_ip"] = str(lo).strip(), str(hi).strip()
    elif meth == "ip_list":
        a["ips"] = split_ips(m["value"])
    elif meth == "vlan":
        a["vlan"] = str(m["value"])
    elif meth == "filter":
        import json

        a["filter"] = json.loads(m["value"]) if isinstance(m["value"], str) else m["value"]
    else:  # asset_names
        return None, "Static membership: the agent must search assets (query_assets) for these names and have the user confirm the ids."
    return a, ""


def build(model: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    model = normalize_model(model)
    o = model["options"]
    p = o["name_prefix"]
    pl = Plan(existing or {})
    cat = load_protocols()
    state = "enabled" if o["policies_enabled"] else "disabled"
    zones = [z["name"] for z in model["zones"]]

    def undo_group(tool: str) -> dict[str, Any]:
        return {"tool": tool, "args": {"group_id": "$id"}, "note": "archive is irreversible; groups are unreferenced once policies are disabled"}

    # ---- phase 0: system groups
    sched_ref, anyp_ref = f"sched:{SCHED_NAME}", f"pg:{ANY_PROTO_NAME}"
    for ref, name, tool, ex in ((sched_ref, SCHED_NAME, "list_schedule_groups", pl.ex_sg), (anyp_ref, ANY_PROTO_NAME, "list_protocol_groups", pl.ex_pg)):
        if name.lower() in ex:
            pl.known[ref] = ex[name.lower()]
        else:
            pl.add("0 lookup", tool, {"find_name": name}, ref=ref, action="lookup",
                   note=f"Find the system group named '{name}' (system=true) and record its id with journal.py. Stop if absent.")

    # ---- phase 1: allowed-protocol groups per conduit
    conduit_pg: dict[str, str] = {}
    for c in model["conduits"]:
        items: list[dict[str, Any]] = []
        verify: list[str] = []
        for pr in c["allowed_protocols"]:
            k = protocol_key(pr, cat)
            if k is None:
                pl.warnings.append(f"Conduit '{c['name']}': unknown protocol '{pr}' left out of its allowed set.")
                continue
            for it in cat["protocols"][k]["items"]:
                if it not in items:
                    items.append(it)
            if cat["protocols"][k].get("verify"):
                verify.append(cat["protocols"][k]["label"])
        if not items:
            continue
        name = f"{p}{SEP}Allowed{SEP}{c['name']}"
        ref = f"pg:{name}"
        conduit_pg[c["name"]] = ref
        note = "Allowed protocols for this conduit." + (f" Confirm protocol enum names for: {', '.join(verify)} (dry run will reject bad values)." if verify else "")
        if name.lower() in pl.ex_pg:
            pl.add("1 protocol groups", "create_protocol_group", {"name": name, "items": items}, ref=ref, action="skip",
                   existing_id=pl.ex_pg[name.lower()], note="Already exists; verify its items match.")
        else:
            pl.add("1 protocol groups", "create_protocol_group", {"name": name, "items": items}, ref=ref,
                   undo=undo_group("archive_protocol_group"), note=note)

    # ---- phase 2: zone asset groups
    zone_refs: dict[str, list[str]] = {}
    for z in zones:
        ms = members_of(model, z)
        refs = []
        for i, m in enumerate(ms, start=1):
            name = _group_name(p, z, i, len(ms))
            ref = f"ag:{name}"
            refs.append(ref)
            args, why = _member_args(m, name, z)
            if args is None:
                pl.blocked.append(name)
                pl.add("2 zone groups", "query_assets", {"search": [x.strip() for x in str(m["value"]).split(",")], "then": f"create_asset_group name='{name}' asset_ids=<confirmed ids>"},
                       ref=ref, action="needs_input", note=why)
            elif name.lower() in pl.ex_ag:
                pl.add("2 zone groups", "create_asset_group", args, ref=ref, action="skip", existing_id=pl.ex_ag[name.lower()],
                       note="Already exists; verify its membership matches.")
            else:
                pl.add("2 zone groups", "create_asset_group", args, ref=ref, undo=undo_group("archive_asset_group"),
                       note=f"{m['method']} membership; dynamic for address-based methods.")
        zone_refs[z.lower()] = refs

    # ---- sample groups
    sample = {}
    if o["create_sample_groups"] or o["create_sample_policies"]:
        sg = load_json(SKILL_DIR / "references" / "sample-groups.json")
        for g in sg["groups"]:
            name = f"{p}{SEP}{g['name']}"
            ref = f"ag:{name}"
            sample[g["key"]] = ref
            args = {"name": name, "filter": {"field": "type", "op": "In", "values": g["types"]}, "description": g["description"], "display_tag": True}
            if name.lower() in pl.ex_ag:
                pl.add("3 sample groups", "create_asset_group", args, ref=ref, action="skip", existing_id=pl.ex_ag[name.lower()])
            else:
                pl.add("3 sample groups", "create_asset_group", args, ref=ref, undo=undo_group("archive_asset_group"), note="Sample tag group (Filter on asset type; lab-verify the filter shape on first apply).")

    # ---- phase 4: policies
    def pos(refs: list[str]) -> list[list[str]]:
        return [[f"$ref:{r}" for r in refs]]

    def neg(refs: list[str]) -> list[list[str]]:
        return [[f"!$ref:{r}"] for r in refs]

    def policy(title: str, ptype: str, extra: dict[str, Any], note: str) -> None:
        ref = f"pol:{title}"
        tool = POLICY_TOOLS[ptype]
        extra = {k: v for k, v in extra.items() if not (ptype == "protocol" and k == "event")}
        args = {"title": title, "level": o["severity"], "initial_state": state, **extra}
        if title.lower() in pl.ex_pol:
            pl.add("4 policies", tool, args, ref=ref, action="skip", existing_id=pl.ex_pol[title.lower()], note="Already exists; verify definition.")
        else:
            pl.add("4 policies", tool, args, ref=ref, risk="medium",
                   undo={"tool": "disable_detection_policy", "args": {"policy_id": "$id"}, "note": "disable is reversible; prefer it over archive"}, note=note)

    sched = f"$ref:{sched_ref}"
    anyp = f"$ref:{anyp_ref}"
    zl = {z.lower(): z for z in zones}
    permitted: dict[str, list[str]] = {z.lower(): [] for z in zones}
    for c in model["conduits"]:
        a, b = c["zone_a"].lower(), c["zone_b"].lower()
        if a not in zl or b not in zl:
            continue
        both = c["direction"] == "bidirectional" or o["direction_tolerant"]
        if c["direction"] == "a_to_b" or both:
            permitted[a].append(b)
        if c["direction"] == "b_to_a" or both:
            permitted[b].append(a)

    for z in zones:
        zk = z.lower()
        dst = neg(zone_refs[zk])
        for t in dict.fromkeys(permitted[zk]):
            dst += neg(zone_refs[t])
        peers = ", ".join(zl[t] for t in dict.fromkeys(permitted[zk])) or "none"
        policy(f"{p}{SEP}Boundary{SEP}{z} -> outside", "protocol",
               {"event": "Conversation", "src": pos(zone_refs[zk]), "dst": dst, "schedule_group_id": sched, "protocol_group_id": anyp},
               f"Traffic from '{z}' to anywhere except itself and permitted targets ({peers}).")
    if zones:
        all_refs = [r for z in zones for r in zone_refs[z.lower()]]
        policy(f"{p}{SEP}Boundary{SEP}unzoned -> zones", "protocol",
               {"event": "Conversation", "src": neg(all_refs), "dst": pos(all_refs), "schedule_group_id": sched, "protocol_group_id": anyp},
               "Traffic from assets in no declared zone into any declared zone.")
    for c in model["conduits"]:
        pg = conduit_pg.get(c["name"])
        a, b = c["zone_a"].lower(), c["zone_b"].lower()
        if not pg or a not in zl or b not in zl:
            continue
        dirs = [(a, b)] if c["direction"] == "a_to_b" else [(b, a)] if c["direction"] == "b_to_a" else [(a, b), (b, a)]
        for s, d in dirs:
            policy(f"{p}{SEP}Conduit{SEP}{c['name']}{SEP}{zl[s]} -> {zl[d]} disallowed protocol", "protocol",
                   {"event": "Conversation", "src": pos(zone_refs[s]), "dst": pos(zone_refs[d]), "schedule_group_id": sched, "protocol_group_id": f"!$ref:{pg}"},
                   f"{zl[s]} -> {zl[d]} using anything outside the conduit's allowed protocols.")

    if o["create_sample_policies"]:
        ctrl = [sample[k] for k in load_json(SKILL_DIR / "references" / "sample-groups.json")["controller_keys"]]
        items: list[dict[str, Any]] = []
        for k in cat["remote_admin"]:
            items += [i for i in cat["protocols"][k]["items"] if i not in items]
        name = f"{p}{SEP}Sample{SEP}Remote admin protocols"
        ref = f"pg:{name}"
        if name.lower() in pl.ex_pg:
            pl.add("4 policies", "create_protocol_group", {"name": name, "items": items}, ref=ref, action="skip", existing_id=pl.ex_pg[name.lower()])
        else:
            pl.add("4 policies", "create_protocol_group", {"name": name, "items": items}, ref=ref, undo=undo_group("archive_protocol_group"), note="RDP/SSH/Telnet for the sample policy.")
        policy(f"{p}{SEP}Sample{SEP}Remote admin to controllers", "protocol",
               {"event": "Conversation", "src": neg(ctrl), "dst": pos(ctrl), "schedule_group_id": sched, "protocol_group_id": f"$ref:{ref}"},
               "Non-controller assets using remote-admin protocols to PLCs/RTUs/IEDs.")
        for z in zones:
            policy(f"{p}{SEP}Sample{SEP}New asset in {z}", "asset",
                   {"event": "NewAssetDiscovered", "src": pos(zone_refs[z.lower()]), "schedule_group_id": sched},
                   f"A new asset appears inside zone '{z}'.")

    # ---- phase 5: verify
    pl.add("5 verify", "list_asset_groups", {}, action="verify", note="Confirm every planned group exists.")
    pl.add("5 verify", "list_detection_policies", {"search": p}, action="verify", note="Confirm policies exist with the expected enabled state.")

    n = lambda t, a=None: sum(1 for s in pl.steps if s["tool"] == t and (a is None or s["action"] == a))  # noqa: E731
    summary = {
        "asset_groups_create": n("create_asset_group", "create"),
        "protocol_groups_create": n("create_protocol_group", "create"),
        "policies_create": sum(1 for s in pl.steps if s["tool"] in POLICY_TOOLS.values() and s["action"] == "create"),
        "skipped_existing": sum(1 for s in pl.steps if s["action"] == "skip"),
        "needs_input": sum(1 for s in pl.steps if s["action"] == "needs_input"),
        "policies_initial_state": state,
        "writes_total": sum(1 for s in pl.steps if s["action"] == "create"),
    }
    if state == "enabled":
        pl.warnings.append("Policies will be created ENABLED: expect alerts immediately. Consider initial_state=disabled for the first run.")
    return {
        "site": model["site"],
        "options": o,
        "summary": summary,
        "warnings": pl.warnings,
        "blocked_on": pl.blocked,
        "known_refs": pl.known,
        "steps": pl.steps,
    }


def render_md(plan: dict[str, Any]) -> str:
    s = plan["summary"]
    out = [
        f"# Plan for site: {plan['site']['name']}",
        "",
        f"Writes: {s['writes_total']} ({s['asset_groups_create']} asset groups, {s['protocol_groups_create']} protocol groups, "
        f"{s['policies_create']} policies, created {s['policies_initial_state']}). Skipped (already exist): {s['skipped_existing']}. Need your input: {s['needs_input']}.",
        "",
        "| # | Phase | Action | Tool | Name / key arguments | Risk | Undo |",
        "|:---:|:---:|:---:|:---:|:---|:---:|:---:|",
    ]
    for st in plan["steps"]:
        a = st["args"]
        label = a.get("name") or a.get("title") or a.get("find_name") or a.get("search") or ""
        undo = st["undo"]["tool"] if st.get("undo") else "-"
        label = str(label).replace("|", "\\|")
        out.append(f"| {st['n']} | {st['phase']} | {st['action']} | {st['tool']} | {label} | {st['risk']} | {undo} |")
    if plan["warnings"]:
        out += ["", "Warnings:"] + [f"- {w}" for w in plan["warnings"]]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model")
    ap.add_argument("--existing")
    ap.add_argument("--out")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    a = ap.parse_args()
    data = load_json(a.model)
    plan = build(data.get("model", data), load_json(a.existing) if a.existing else None)
    if a.format == "md":
        text = render_md(plan)
        (open(a.out, "w", encoding="utf-8").write(text) if a.out else sys.stdout.write(text))
    else:
        dump_json(plan, a.out)


if __name__ == "__main__":
    main()
