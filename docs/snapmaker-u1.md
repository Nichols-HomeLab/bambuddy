# Snapmaker U1

Bambuddy can connect to a Snapmaker U1 through the printer's Moonraker API.
This integration keeps the existing inventory and queue workflow while mapping
the U1's four independent tools to four filament slots:

| Bambuddy slot | U1 tool | UI label |
|---|---|---|
| 1 | `extruder` / T0 | Nozzle 1 |
| 2 | `extruder1` / T1 | Nozzle 2 |
| 3 | `extruder2` / T2 | Nozzle 3 |
| 4 | `extruder3` / T3 | Nozzle 4 |

## Add the printer

1. Open **Printers → Add printer**.
2. Select **Snapmaker U1 (Moonraker)**.
3. Enter the printer IP or hostname and a unique serial/name.
4. Leave port `7125` unless the U1's Moonraker service uses a different port.
5. Enter a Moonraker API key only if authentication is enabled.

Bambuddy probes `/server/info`, creates a four-nozzle printer, and imports the
first enabled webcam returned by `/server/webcams/list`. The automatically
detected stream and snapshot URLs remain editable as normal external-camera
settings.

Assign an inventory spool to **Nozzle 1–4** on the printer card. Bambuddy saves
that assignment and restores it after reconnecting. Slicer filament mapping
uses the nozzle number as the Orca extruder ID.

## Snapmaker Orca sidecar

Start the supplied sidecar stack:

```bash
cd slicer-api
docker compose up -d
curl http://localhost:3003/health
```

The stack starts both the existing Bambu Studio sidecar on port 3001 and the
Snapmaker sidecar on port 3003. It pulls
`git.nicholstech.org/nichols-homelab/snapmaker-orca-api:2.3.5`, built from the
official Snapmaker Orca 2.3.5 Linux AppImage. Configure Bambuddy's dedicated
**Snapmaker U1 Orca sidecar URL** as `http://snapmaker-orca-api:3000` on a
shared Docker network, or `http://<sidecar-host>:3003` through the host port.
Keep the preferred Bambu sidecar set to `http://bambu-studio-api:3000` (or
`http://<sidecar-host>:3001`). Bambuddy chooses between them from the selected
printer profile, so both remain active at the same time.

The sidecar also accepts exported JSON profiles directly. Names are
alphanumeric identifiers used later by the slice request:

```bash
curl -F name=MyU1Printer -F file=@printer.json \
  http://localhost:3003/profiles/printers
curl -F name=MyU1Process -F file=@process.json \
  http://localhost:3003/profiles/presets
curl -F name=MyU1Filament -F file=@filament.json \
  http://localhost:3003/profiles/filaments

curl -F file=@model.stl \
  -F printer=MyU1Printer -F preset=MyU1Process -F filament=MyU1Filament \
  -F exportType=3mf http://localhost:3003/slice -o model.gcode.3mf
```

When a sliced `.gcode.3mf` reaches the queue, Bambuddy extracts the selected
plate's raw G-code, uploads it to Moonraker's `gcodes` root, and starts it with
the U1 print endpoint.
