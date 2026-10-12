---
name: T1OTE-iec62443-onboarding
description: Guided onboarding of a Tenable OT site to an IEC 62443 zones-and-conduits baseline. Collects zones, CIDR blocks and conduits from chat or a spreadsheet, shows a plan, and only after approval creates asset groups and detection policies through the Tenable OT MCP (Enterprise Manager edition).
status: draft
---

# IEC 62443 onboarding for Tenable OT

Tenable OT has no native IEC 62443 objects. This skill builds them from what exists:

- **Zone** (horizontal: which assets) = one or more **asset groups**, address-based so new assets in the range join automatically.
- **Conduit** (vertical: which paths are allowed) = **detection policies** that fire when traffic strays outside the allowed path.

Native Tenable "zones" are a different concept and are out of scope. Never conflate them.

The rules below are written for small local models, which tend to recite a rule rather than perform it: each check produces visible output.

## Hard rules

1. **No write before approval.** Every create tool defaults to `dry_run=true`. Real writes happen only after the user has seen the plan and said yes.
2. **State the tool-call plan in visible text before the first write**: the numbered plan from `build_plan.py`, not a summary.
3. **Never infer the site.** Call `list_paired_icps`, show names and ids, let the user choose. Pass `site_uuid` on every call.
4. **Never assume direction.** Each conduit has one declared initiator direction (`a_to_b` or `b_to_a`); `bidirectional` only if the user says both sides initiate. Ask, do not default.
5. **Stop on first error.** Record it in the journal, tell the user, and offer continue / skip / undo. **Never resubmit an identical failed call.**
6. **Use the scripts, not your own arithmetic.** CIDR maths, overlap detection, plan ordering and id substitution are done by `scripts/*.py`. Do not compute them in your head and do not edit a plan by hand; change the model and rebuild.
7. **Prefer disable over archive** for undo. Archive is irreversible.
8. Policies are created **disabled** unless the user explicitly chooses enabled. Recommend disabled for a first onboarding, then enable after a review period.

## Structural checks (load-bearing, not decorative)

Models without visible reasoning recite rules rather than perform them, so these are steps with output, not reminders:

- **Before showing the plan**, write one trace line per conduit: `<conduit>: <A> -> <B> (<direction>), allowed: <protocols>, policies: <titles from the plan>`. Copy titles from `plan.json`; if a conduit has no policy line, say why (no allowed protocols, or unknown protocol).
- **Before each write**, state the call you are about to make as one line (`step N: create_conversation_policy "<title>" dry_run=true`). Use only the output of `journal.py resolve`; never retype ids.
- **Tables**: keep the `:---:` alignment markers in markdown table separator rows (dropping them breaks rendering on this stack). Paste `build_plan.py --format md` output unchanged rather than re-typing it.
- Any value not traceable to a script output or tool result is "unknown", never invented.

## Scripts (all under `scripts/`, Python 3.9+, `openpyxl` only for xlsx)

| Script | Purpose |
|---|---|
| `generate_template.py [--site NAME] --out FILE.xlsx` | Blank workbook with dropdowns and example rows |
| `parse_workbook.py INPUT` | xlsx / CSV directory / JSON to model plus `gaps` (questions to ask) |
| `validate_model.py MODEL.json` | Errors block planning; warnings are shown to the user. Exit 1 on errors |
| `build_plan.py MODEL.json [--existing E.json] [--format md]` | Ordered plan with symbolic `$ref:` ids |
| `journal.py record / resolve / next / undo-plan / status` | Apply-time bookkeeping and undo |

The model format is in `scripts/iec_common.py`; a worked example is `examples/sample-model.json`.

## Flow

### 0. Preflight

Call `tenable_ot_status`. If write tools are not enabled, say so and offer the **plan-only path** (produce and explain the plan and the workbook, apply nothing). Confirm `create_conversation_policy` (and `create_asset_policy` if sample policies are wanted) exist in the tool list; tick them in the client if they are unloaded; if not, say the EM-MCP build predates policy creation and stop at the plan.

### 1. Site

`list_paired_icps`. Ask which site. Record its `site_uuid`; use it on every later call. Ask for the customer's name for the site (goes into the model).

### 2. Input method

Ask: "Fill in a spreadsheet, answer questions here, or paste a list?"

- **Spreadsheet**: run `generate_template.py --site "<name>"`, deliver the file (and an Artifact version where the client supports it). When the user returns it, run `parse_workbook.py`. Every entry in `gaps` becomes a follow-up question.
- **Chat**: ask in the order below and build the model JSON as you go (see `references/guided-questions.md` for wording).
- **Paste**: accept CSV-like text, map it to the same model, confirm back.

### 3. Collect (chat path)

1. **Zones**: names, optional description, Purdue level 0-5, SL-T 1-4, criticality.
2. **Address space per zone**. Offer in this order: CIDR (best, dynamic), address range, IP list, VLAN, "pick specific assets" (`asset_names`). A zone may have several blocks.
3. **Conduits**: which zone pairs talk, **who initiates**, and over which protocols (names from `references/protocols.json`, e.g. Modbus, S7, CIP, EtherNet/IP, DNP3, IEC 104, OPC UA, HTTPS).
4. **Options**: sample groups, sample policies, severity, enabled or disabled, name prefix (default `IEC62443`).

### 4. Validate

Write the model to a file, run `validate_model.py`.

- **Errors**: fix with the user, re-run. Do not plan until clean. Overlapping zones are an error unless the user insists (`allow_overlap`).
- **Warnings**: read them out. Pay particular attention to `DIRECTION_SENSITIVE` (UDP or mixed protocols on a one-way conduit: Tenable infers direction from the TCP handshake and falls back to "higher port is the source", so UDP and missed handshakes can flip it, causing false alerts or misses) and `ZONE_NO_CONDUIT`.

### 5. Existing state

Call `list_asset_groups`, `list_protocol_groups`, `list_schedule_groups`, `list_detection_policies` (search by the prefix). Assemble `existing.json` (`name`/`title` and `id` pairs) and pass it to `build_plan.py` so existing objects become `skip` steps. Do not update or archive anything that exists unless the user asks.

### 6. Plan and approval

Run `build_plan.py --format md`, show the whole table, then summarise in plain words:

- how many groups, protocol groups and policies will be created and in which state;
- the policy logic in one sentence each: *boundary* (a zone talking anywhere other than itself and its permitted targets), *unzoned to zones*, *conduit conformance* (a permitted pair using a protocol outside the allowed set);
- the direction rule: strict, as declared, and which conduits are direction-sensitive;
- anything `needs_input` (static asset picks) and anything unknown that was left out.

Ask for explicit approval: "Apply this plan to site X? (yes / change something / plan only)". Per-section approval is allowed.

### 7. Apply

Loop until `journal.py next` reports done:

1. `journal.py next` gives the next step number (blocked means an earlier error; stop and ask).
2. `journal.py resolve --step N` gives the real arguments with ids substituted. Use exactly those.
3. **Lookup steps**: call the list tool, find the system group by name (`system: true`), then `journal.py record --status ok --ref <ref> --id <id>`. If it is absent, stop and tell the user.
4. **Create steps**: call the tool with `dry_run=true`, check the preview, record `dry_run`. Then call with `dry_run=false`, read the id from the result (`id` in the group result; `policy_id` for the create_*_policy tools), record `ok` with `--id`. A failure is recorded as `error` and the loop stops.
5. **needs_input steps** (`asset_names`): `query_assets` with the names, show matches, user confirms ids, then `create_asset_group(asset_ids=[...])`.
6. **Verify steps**: re-read with the list tools and diff against the plan.

For the policy tools pass the resolved arguments unchanged; they include `initial_state` (`disabled` means Tenable creates then disables, two calls; check `state_applied` in the result and report any `warning`).

### 8. Report

Summarise created / skipped / failed with ids, the final state of each policy (enabled or disabled), and the journal path. Offer the undo plan (`journal.py undo-plan`), which disables policies first, then lists archives that need confirmation. Suggest the tuning step: review findings after a soak period, then enable policies; use conversation exclusions for legitimate traffic.

## Policy semantics (for explaining the plan)

Policies use Tenable's source/destination lists in conjunctive normal form: the outer list is AND, each inner list is OR, and each member can be negated. A zone with several address blocks is one OR-list. "Not in zone Z" is one negated list per block. Protocol policies match conversations per direction.

Generated per run (strategy S1): one **boundary** policy per zone, one **unzoned to zones** policy, and one **conformance** policy per conduit direction using the negated allowed-protocol group. Count = zones + 1 + conduit directions. Boundary alerts on *any* traffic from a zone to outside itself and its permitted targets, which includes traffic to unmanaged addresses (DNS, NTP servers outside the zones): expect tuning.

## Failure handling

| Symptom | Action |
|---|---|
| A create_*_policy tool rejects a group or event | Run `describe_policy_type`, correct the **model or plan**, rebuild. Do not retry the same call |
| Protocol enum rejected on `create_protocol_group` | Plan notes list unverified protocol names; fix `references/protocols.json`, rebuild, apply the remaining steps |
| Filter group rejected (sample groups) | Skip the sample groups, tell the user; they are optional |
| Unresolved `$ref` | An earlier step is not recorded `ok`. Do not guess ids |
| Disable step failed after create | The policy is live and enabled. Say so plainly and call `disable_detection_policy` |
| Write tools disabled | Offer the plan-only path |

## References

- `references/guided-questions.md` question wording and defaults
- `references/naming.md` object naming and idempotency
- `references/protocols.json` protocol catalogue and aliases
- `references/sample-groups.json` sample asset groups
- `docs/` in the repository for the design notes and the policy model
