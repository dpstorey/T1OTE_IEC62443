# IEC 62443 onboarding for Tenable OT

An agent skill that turns an IEC 62443 zones-and-conduits design into Tenable OT objects: address-based **asset groups** for zones and **detection policies** for conduits. It asks guided questions (or reads a spreadsheet), validates the model, shows a plan, and changes nothing until you approve it.

Tenable OT has no native IEC 62443 zones or conduits (its own "zones" are a different concept). This skill implements them with what exists:

| IEC 62443 | Tenable OT object |
|:---|:---|
| Zone (a set of assets) | One or more asset groups, by CIDR, range, IP list, VLAN or picked assets |
| Conduit (an allowed path between zones) | Unauthorized-conversation policies that fire when traffic leaves the allowed path |

## Requirements

- The **Tenable OT MCP, Enterprise Manager edition** with write tools enabled, in a build that includes the narrow policy-creation tools (`create_conversation_policy` and friends). See [EM-MCP](https://github.com/dpstorey/EM-MCP) and its [Exchange listing](https://exchange.tenable.com/mcp-servers/tenable-ot-mcp-em-edition/). Without write tools the skill still works in plan-only mode.
- An agent client that supports skills and MCP tools (tested design target: LibreChat with local models; Claude Code and Claude Desktop also fit).
- Python 3.9+ for the helper scripts; `openpyxl` only for spreadsheet input and the template.

## Install

1. Copy `skill/T1OTE-iec62443-onboarding/` into your client's skills directory.
2. In the client, enable these tools from the MCP server and leave the rest off:
   - `list_paired_icps`, `tenable_ot_status`
   - `list_asset_groups`, `list_protocol_groups`, `list_schedule_groups`, `list_detection_policies`, `get_policy`
   - `create_asset_group`, `create_protocol_group`, `create_conversation_policy`, `disable_detection_policy`
   - optional: `create_asset_policy` (sample policies), `query_assets` (picking specific assets)
3. Install the one dependency if you want spreadsheet input: `pip install openpyxl`.

## Quick start

Ask the agent to onboard a site to IEC 62443. It will:

1. list your paired sites and ask which one (it never infers the site);
2. offer a spreadsheet (`templates/onboarding-template.xlsx`, or generated with `generate_template.py`) or chat questions;
3. validate the model (overlaps, bad CIDRs, missing directions, unknown protocols);
4. show a numbered plan with object counts;
5. apply it only after you say yes: every write is a dry run first, policies are created **disabled** by default, and a journal records each result so the run can be undone.

Try the scripts without a Tenable system:

```
cd skill/T1OTE-iec62443-onboarding/scripts
python validate_model.py ../../../examples/sample-model.json
python build_plan.py ../../../examples/sample-model.json --format md
```

## How conduits are enforced

Per run it creates one boundary policy per zone (traffic to anywhere except the zone itself and its permitted targets), one policy for traffic from outside any declared zone into a zone, and one conformance policy per conduit direction that alerts on any protocol outside the conduit's allowed set. Each conduit has **one declared direction** (who may initiate). Tenable infers direction from the TCP handshake, so for UDP and mid-connection flows it can guess wrongly; the validator warns about one-way conduits that carry UDP-heavy protocols. See [docs/policy-model.md](docs/policy-model.md).

## Safety and disclosures

- **Outbound network:** the skill's scripts make none. All traffic is the MCP server talking to your own Enterprise Manager and Tenable OT sites.
- **State changes:** creates asset groups, protocol groups and detection policies on the selected site; disables policies on undo. Archiving is never done automatically.
- **Approval:** nothing is written before you approve the plan; the site is never inferred; failed calls are never retried identically.
- **Secrets:** none are read, stored or requested by the skill. API credentials belong to the MCP server configuration.
- **Input handling:** zone and conduit names are validated (no separator characters, reserved words rejected) and addresses are parsed, not interpreted.

## Status

Draft. The unit tests pass (`pytest tests/unit`) and CI is green.

Verified on a live Tenable OT site: an unauthorized-conversation (boundary) policy created with empty policy actions and created disabled (`initial_state=disabled`, a create followed by a disable), the system "Any Time" schedule and "Any Protocol" protocol groups, and a destination of one negated list per zone block, which shows in the UI as "(Not in zone A) and (Not in zone B)".

Also verified live: protocol groups using the enum values `ETHIP` (EtherNet/IP), `IEC61850` and `PROFINET`, and that Tenable accepts a user-defined group whose name matches a predefined one.

Sample filter groups: Tenable accepts a Filter group created with `type In [...]` (tested with `Controller`; it matched 8 assets). The other sample types (`Plc`, `Rtu`, `Ied`, `Hmi`, `OtWorkstation`, `Firewall`) come from the asset-type list the Tenable OT MCP already uses for asset queries; they are expected to work but were not each created live.

Not yet verified live: direction behaviour with UDP. Treat the first run as a dry run on a test site.

## Layout

```
skill/T1OTE-iec62443-onboarding/   SKILL.md, scripts/, references/
templates/                   onboarding-template.xlsx
examples/                    sample model, filled workbook, sample plan
tests/unit/                  unit tests
docs/                        policy model notes
```

## License

Apache-2.0. See [LICENSE](LICENSE).
