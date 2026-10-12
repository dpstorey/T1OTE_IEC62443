# Plan for site: Demo Plant

Writes: 29 (11 asset groups, 4 protocol groups, 14 policies, created disabled). Skipped (already exist): 0. Need your input: 0.

| # | Phase | Action | Tool | Name / key arguments | Risk | Undo |
|:---:|:---:|:---:|:---:|:---|:---:|:---:|
| 1 | 0 lookup | lookup | list_schedule_groups | Any Time | low | - |
| 2 | 0 lookup | lookup | list_protocol_groups | Any protocol | low | - |
| 3 | 1 protocol groups | create | create_protocol_group | IEC62443 \| Allowed \| Enterprise to DMZ | low | archive_protocol_group |
| 4 | 1 protocol groups | create | create_protocol_group | IEC62443 \| Allowed \| DMZ to Control | low | archive_protocol_group |
| 5 | 1 protocol groups | create | create_protocol_group | IEC62443 \| Allowed \| Control to Safety | low | archive_protocol_group |
| 6 | 2 zone groups | create | create_asset_group | IEC62443 \| Zone \| Enterprise | low | archive_asset_group |
| 7 | 2 zone groups | create | create_asset_group | IEC62443 \| Zone \| DMZ | low | archive_asset_group |
| 8 | 2 zone groups | create | create_asset_group | IEC62443 \| Zone \| Control \| 1 | low | archive_asset_group |
| 9 | 2 zone groups | create | create_asset_group | IEC62443 \| Zone \| Control \| 2 | low | archive_asset_group |
| 10 | 2 zone groups | create | create_asset_group | IEC62443 \| Zone \| Safety | low | archive_asset_group |
| 11 | 3 sample groups | create | create_asset_group | IEC62443 \| Sample \| PLCs | low | archive_asset_group |
| 12 | 3 sample groups | create | create_asset_group | IEC62443 \| Sample \| RTUs | low | archive_asset_group |
| 13 | 3 sample groups | create | create_asset_group | IEC62443 \| Sample \| IEDs | low | archive_asset_group |
| 14 | 3 sample groups | create | create_asset_group | IEC62443 \| Sample \| HMIs | low | archive_asset_group |
| 15 | 3 sample groups | create | create_asset_group | IEC62443 \| Sample \| OT workstations | low | archive_asset_group |
| 16 | 3 sample groups | create | create_asset_group | IEC62443 \| Sample \| Firewalls | low | archive_asset_group |
| 17 | 4 policies | create | create_conversation_policy | IEC62443 \| Boundary \| Enterprise -> outside | medium | disable_detection_policy |
| 18 | 4 policies | create | create_conversation_policy | IEC62443 \| Boundary \| DMZ -> outside | medium | disable_detection_policy |
| 19 | 4 policies | create | create_conversation_policy | IEC62443 \| Boundary \| Control -> outside | medium | disable_detection_policy |
| 20 | 4 policies | create | create_conversation_policy | IEC62443 \| Boundary \| Safety -> outside | medium | disable_detection_policy |
| 21 | 4 policies | create | create_conversation_policy | IEC62443 \| Boundary \| unzoned -> zones | medium | disable_detection_policy |
| 22 | 4 policies | create | create_conversation_policy | IEC62443 \| Conduit \| Enterprise to DMZ \| Enterprise -> DMZ disallowed protocol | medium | disable_detection_policy |
| 23 | 4 policies | create | create_conversation_policy | IEC62443 \| Conduit \| DMZ to Control \| DMZ -> Control disallowed protocol | medium | disable_detection_policy |
| 24 | 4 policies | create | create_conversation_policy | IEC62443 \| Conduit \| Control to Safety \| Control -> Safety disallowed protocol | medium | disable_detection_policy |
| 25 | 4 policies | create | create_conversation_policy | IEC62443 \| Conduit \| Control to Safety \| Safety -> Control disallowed protocol | medium | disable_detection_policy |
| 26 | 4 policies | create | create_protocol_group | IEC62443 \| Sample \| Remote admin protocols | low | archive_protocol_group |
| 27 | 4 policies | create | create_conversation_policy | IEC62443 \| Sample \| Remote admin to controllers | medium | disable_detection_policy |
| 28 | 4 policies | create | create_asset_policy | IEC62443 \| Sample \| New asset in Enterprise | medium | disable_detection_policy |
| 29 | 4 policies | create | create_asset_policy | IEC62443 \| Sample \| New asset in DMZ | medium | disable_detection_policy |
| 30 | 4 policies | create | create_asset_policy | IEC62443 \| Sample \| New asset in Control | medium | disable_detection_policy |
| 31 | 4 policies | create | create_asset_policy | IEC62443 \| Sample \| New asset in Safety | medium | disable_detection_policy |
| 32 | 5 verify | verify | list_asset_groups |  | low | - |
| 33 | 5 verify | verify | list_detection_policies | IEC62443 | low | - |
