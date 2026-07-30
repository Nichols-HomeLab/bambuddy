import zipfile
from pathlib import Path

from backend.app.services.print_scheduler import extract_plate_gcode
from backend.app.services.snapmaker_moonraker import SnapmakerMoonrakerClient


def test_extract_plate_gcode_selects_requested_plate(tmp_path: Path):
    project = tmp_path / "project.gcode.3mf"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "G1 X1\n")
        archive.writestr("Metadata/plate_2.gcode", "G1 X2\n")

    extracted = extract_plate_gcode(project, 2)
    try:
        assert extracted.read_text() == "G1 X2\n"
    finally:
        extracted.unlink()


def test_moonraker_maps_u1_state_and_four_tools(monkeypatch):
    client = SnapmakerMoonrakerClient(
        ip_address="192.0.2.10",
        serial_number="U1-TEST",
        port=7125,
    )

    monkeypatch.setattr(
        client,
        "_request_json",
        lambda *args, **kwargs: {
            "result": {
                "status": {
                    "print_stats": {
                        "state": "printing",
                        "filename": "four-colour.gcode",
                        "print_duration": 120,
                        "info": {"current_layer": 3, "total_layer": 20},
                    },
                    "display_status": {"progress": 0.25},
                    "virtual_sdcard": {"progress": 0.25},
                    "heater_bed": {"temperature": 55, "target": 60},
                    "extruder": {"temperature": 210, "target": 215},
                    "extruder1": {"temperature": 205, "target": 210},
                    "extruder2": {"temperature": 200, "target": 205},
                    "extruder3": {"temperature": 195, "target": 200},
                    "toolhead": {"extruder": "extruder2"},
                }
            }
        },
    )

    client._poll_once()

    assert client.state.connected is True
    assert client.state.state == "RUNNING"
    assert client.state.active_extruder == 2
    assert client.state.temperatures["nozzle_4"] == 195
    trays = client.state.raw_data["ams"][0]["tray"]
    assert [tray["extruder_id"] for tray in trays] == [0, 1, 2, 3]


def test_assigning_filament_updates_the_matching_nozzle_slot():
    client = SnapmakerMoonrakerClient(ip_address="192.0.2.10", serial_number="U1-TEST")

    assert client.ams_set_filament_setting(
        ams_id=0,
        tray_id=3,
        tray_type="PETG",
        tray_color="12AB34FF",
    )

    tray = client.state.raw_data["ams"][0]["tray"][3]
    assert tray["extruder_id"] == 3
    assert tray["tray_type"] == "PETG"
    assert tray["tray_color"] == "12AB34FF"
