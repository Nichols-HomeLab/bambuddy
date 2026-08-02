# Filament shelf workflow

The custom shelf workflow keeps **physical position** separate from **printer
assignment**. This is important for the Snapmaker U1: a spool stays inside the
sealed U1 live box while it is also assigned to one dedicated tool.

## Recommended layout

Open **Inventory → Shelf workflow** and select **Create recommended layout**.
The action is idempotent and preserves existing locations and spools. It creates:

- six storage boxes (`BOX-A` through `BOX-F`) with four positions each;
- one four-position U1 live box (`U1-T1` through `U1-T4`);
- one four-position X1C staging box, whose first outlet is `X1C-EXT`;
- four X1C AMS positions (`X1C-AMS-1` through `X1C-AMS-4`); and
- one dryer destination (`DRYER-1`).

If an active Snapmaker Moonraker printer and an X1C already exist, setup links
the U1 and X1C destinations automatically. Running **Refresh layout** after a
printer is added updates those links.

## Scan workflow

Label spools with `SPOOL-<id>` (the existing spool QR link is also accepted),
then use **Print QR labels** on the shelf screen to produce the complete cut-out
destination sheet (the same codes can be written to NFC tags). A move is:

1. Scan the spool.
2. Scan the destination.
3. Bambuddy updates the physical position and, for a live destination, its
   printer/tool assignment in one transaction.

Storage and dryer moves clear the old printer assignment. A destination with a
capacity of one rejects a second spool instead of silently overwriting the
physical inventory. Tag UID and tray UUID scans are also accepted.

Moving a spool into `DRYER-1` sets it to **Drying**. Scanning it out after the
cycle sets its drying condition to **Dry**, records `last_dried`, and then sets
the appropriate Stored/Loaded state. **Needs drying** and **Empty** can be set
from the normal spool editor.

## U1 mapping

| Physical outlet | Bambuddy assignment | U1 internal extruder |
|---|---|---|
| `U1-T1` | tool 1 | `extruder` / T0 |
| `U1-T2` | tool 2 | `extruder1` / T1 |
| `U1-T3` | tool 3 | `extruder2` / T2 |
| `U1-T4` | tool 4 | `extruder3` / T3 |

The user-facing labels intentionally remain one-based even though Moonraker's
internal extruder/tool numbering begins at zero.

## Humidity sensors

Each dry-box card accepts a current humidity percentage and a Home Assistant
entity ID such as `sensor.box_a_humidity`. The humidity value is inherited by
the box's four positions and cached on each spool as `storage_box_humidity`, so
it remains visible in inventory exports and table columns. The entity ID is
stored as the stable link for Aqara or ESPHome sensors; humidity can be updated
from the shelf screen or through `PATCH /api/v1/inventory/locations/{id}`.

## Status and data fields

The workflow adds these spool fields without replacing existing inventory data:

- `inventory_status`: Stored, Loaded – U1, Loaded – X1C AMS, Loaded – X1C
  External, Drying, Needs drying, or Empty;
- `drying_status`, `last_dried`, and `storage_box_humidity`;
- `loaded_at`; and
- the existing `location_id` / `storage_location` and `SpoolAssignment` remain
  the physical and printer-assignment sources of truth, respectively.

This workflow is available for Bambuddy's local inventory. Spoolman mode keeps
its own spool IDs and remains read-only on this screen.
