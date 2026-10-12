#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply-time journal: record results, resolve symbolic refs, produce an undo plan.

  journal.py record   --journal J --step N --tool T [--ref R] --status ok|error|dry_run [--id ID] [--message M]
  journal.py resolve  --plan P --journal J --step N       # prints the step's args with $ref ids substituted
  journal.py next     --plan P --journal J                # first step not yet 'ok' (or skipped), as JSON
  journal.py undo-plan --plan P --journal J               # reverse-order undo calls for created objects
  journal.py status   --plan P --journal J

Journal = JSON lines. Stop-on-first-error is enforced by `next`: it returns the
failed step again with "blocked": true until the agent records a decision
(`record --status skipped`). Identical failed calls must not be resubmitted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iec_common import dump_json, load_json  # noqa: E402



def read_journal(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def ref_ids(plan: dict[str, Any], journal: list[dict[str, Any]]) -> dict[str, str]:
    ids = dict(plan.get("known_refs") or {})
    for r in journal:
        if r.get("status") == "ok" and r.get("ref") and r.get("id"):
            ids[r["ref"]] = r["id"]
    return ids


def substitute(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        if value.startswith("$ref:") or value.startswith("!$ref:"):
            neg = value.startswith("!")
            ref = value[len("!$ref:") if neg else len("$ref:"):]
            if ref not in ids:
                raise KeyError(ref)
            return ("!" if neg else "") + ids[ref]
        return value
    if isinstance(value, list):
        return [substitute(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, ids) for k, v in value.items()}
    return value


def step_by_n(plan: dict[str, Any], n: int) -> dict[str, Any]:
    for s in plan["steps"]:
        if s["n"] == n:
            return s
    raise SystemExit(f"no step {n} in plan")


def cmd_record(a: argparse.Namespace) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "step": a.step,
        "tool": a.tool,
        "ref": a.ref,
        "status": a.status,
        "id": a.id,
        "message": a.message,
    }
    with open(a.journal, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))


def cmd_resolve(a: argparse.Namespace) -> None:
    plan, j = load_json(a.plan), read_journal(a.journal)
    step = step_by_n(plan, a.step)
    try:
        args = substitute(step["args"], ref_ids(plan, j))
    except KeyError as exc:
        raise SystemExit(f"unresolved reference {exc.args[0]!r}: an earlier step has not been recorded as ok") from None
    dump_json({"step": step["n"], "tool": step["tool"], "action": step["action"], "args": args})


def cmd_next(a: argparse.Namespace) -> None:
    plan, j = load_json(a.plan), read_journal(a.journal)
    last: dict[int, str] = {}
    for r in j:
        if r["status"] in ("ok", "skipped"):
            last[r["step"]] = "done"
        elif r["status"] == "error":
            last[r["step"]] = "error"
        elif r["status"] == "dry_run" and last.get(r["step"]) != "done":
            last[r["step"]] = "dry"
    for s in plan["steps"]:
        if s["action"] == "skip":
            continue
        st = last.get(s["n"])
        if st == "done":
            continue
        if st == "error":
            dump_json({"blocked": True, "step": s["n"], "reason": "previous attempt failed; decide continue/skip/undo, do not resubmit identically"})
            return
        dump_json({"blocked": False, "step": s["n"], "tool": s["tool"], "action": s["action"], "dry_run_done": st == "dry"})
        return
    dump_json({"done": True})


def cmd_undo(a: argparse.Namespace) -> None:
    plan, j = load_json(a.plan), read_journal(a.journal)
    done = [r for r in j if r["status"] == "ok" and r.get("id")]
    out = []
    for r in reversed(done):
        step = step_by_n(plan, r["step"])
        u = step.get("undo")
        if not u:
            continue
        args = json.loads(json.dumps(u["args"]).replace('"$id"', json.dumps(r["id"])))
        out.append({"undo_of_step": step["n"], "ref": r.get("ref"), "tool": u["tool"], "args": args, "note": u.get("note", "")})
    dump_json({"undo_calls": out, "advice": "Run policy disables first (reverse order does this). Archive is irreversible: confirm each archive with the user."})


def cmd_status(a: argparse.Namespace) -> None:
    plan, j = load_json(a.plan), read_journal(a.journal)
    c: dict[str, int] = {}
    for r in j:
        c[r["status"]] = c.get(r["status"], 0) + 1
    dump_json({"steps": len(plan["steps"]), "journal_records": len(j), "by_status": c})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--journal", required=True)
    r.add_argument("--step", type=int, required=True)
    r.add_argument("--tool", required=True)
    r.add_argument("--ref")
    r.add_argument("--status", required=True, choices=("ok", "error", "dry_run", "skipped"))
    r.add_argument("--id")
    r.add_argument("--message")
    r.set_defaults(fn=cmd_record)
    for name, fn in (("resolve", cmd_resolve), ("next", cmd_next), ("undo-plan", cmd_undo), ("status", cmd_status)):
        s = sub.add_parser(name)
        s.add_argument("--plan", required=True)
        s.add_argument("--journal", required=True)
        if name == "resolve":
            s.add_argument("--step", type=int, required=True)
        s.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
