# Policy model

## Scoping lists

Tenable OT policies take source and destination as a list of lists of groups, in conjunctive normal form: the **outer list is AND**, each **inner list is OR**, and each member can be negated. `[[A,B],[C,not D],[E]]` means `(A or B) and (C or not D) and E`.

- A zone with several address blocks is one inner list: `[[Z1,Z2,Z3]]`.
- "Not in zone Z" is one inner list per block: `[[not Z1],[not Z2]]`.

## Policies generated per run

For zones Z and conduits C:

1. **Boundary** (one per zone): source = the zone; destination = not the zone itself and not any zone it may initiate to. Event: conversation, any protocol.
2. **Unzoned to zones** (one): source = not in any declared zone; destination = any declared zone.
3. **Conduit conformance** (one per conduit direction that has allowed protocols): source = zone A, destination = zone B, protocol group = the conduit's allowed set, negated. Alerts on any protocol outside the allowed set.

Count = zones + 1 + conduit directions. Optional samples add a remote-admin-to-controllers policy and a new-asset-in-zone policy per zone.

## Direction

Each conduit declares one direction: `a_to_b`, `b_to_a`, or `bidirectional` (only when both sides genuinely initiate). Policies match conversations per direction. Tenable OT infers direction from the TCP handshake and falls back to "higher port is the source" when the handshake is missed (UDP, long-lived connections, sensor restarts, asymmetric routing). A wrongly inferred direction can fire a policy (false positive) or mask a stray flow (miss). TCP effects are mostly transient; UDP and asymmetric paths can persist. Mitigations: the validator flags direction-sensitive conduits, `direction_tolerant` treats every conduit as symmetric for boundary checks, and policies are created disabled for a review period.

## Naming

All objects carry a prefix (default `IEC62443`) and use ` | ` as a separator, so a prefix search finds everything a run created. See `skill/T1OTE-iec62443-onboarding/references/naming.md`.
