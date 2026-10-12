# Naming and idempotency

All objects created carry the name prefix (default `IEC62443`) and use ` | ` as a separator, so a prefix search finds everything a run created.

| Object | Name |
|---|---|
| Zone asset group | `<prefix> | Zone | <zone>` (several blocks: `... | <zone> | 1`, `| 2`) |
| Conduit protocol group | `<prefix> | Allowed | <conduit>` |
| Boundary policy | `<prefix> | Boundary | <zone> -> outside` |
| Unzoned policy | `<prefix> | Boundary | unzoned -> zones` |
| Conformance policy | `<prefix> | Conduit | <conduit> | <A> -> <B> disallowed protocol` |
| Sample group | `<prefix> | Sample | <name>` |
| Sample policy | `<prefix> | Sample | <name>` |

Zone and conduit names must not contain `|`.

Re-running with the same model is safe: names that already exist become `skip` steps and their ids are reused. A changed definition under an existing name is **not** updated automatically; ask the user, then use `update_asset_group` / `update_policy` (full replace) on that one object.

Changing the prefix creates a second, parallel set.
