"""Snapmaker U1 adapter for its open-source Moonraker interface.

The rest of Bambuddy consumes ``PrinterState`` and a small command surface
historically supplied by ``BambuMQTTClient``.  This adapter presents that same
surface while polling Moonraker and maps the U1's four independent tools to a
synthetic four-slot filament unit.  Existing inventory assignment and filament
mapping UI can therefore be reused without pretending the U1 speaks Bambu MQTT.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from backend.app.services.bambu_mqtt import MQTTLogEntry, NozzleInfo, PrinterState

logger = logging.getLogger(__name__)


_MOONRAKER_STATE = {
    "standby": "IDLE",
    "complete": "FINISH",
    "completed": "FINISH",
    "error": "FAILED",
    "cancelled": "FAILED",
    "printing": "RUNNING",
    "paused": "PAUSE",
}


class SnapmakerMoonrakerClient:
    """Small synchronous/polling Moonraker client with Bambuddy callbacks."""

    POLL_SECONDS = 2.0
    STALE_SECONDS = 12.0

    def __init__(
        self,
        *,
        ip_address: str,
        serial_number: str,
        access_code: str = "",
        port: int = 7125,
        model: str | None = "Snapmaker U1",
        on_state_change: Callable[[PrinterState], None] | None = None,
        on_print_start: Callable[[dict], None] | None = None,
        on_print_complete: Callable[[dict], None] | None = None,
        on_ams_change: Callable[[list], None] | None = None,
        on_layer_change: Callable[[int], None] | None = None,
        on_bed_temp_update: Callable[[float], None] | None = None,
        on_assignment_verified: Callable[[int, int, bool, dict], None] | None = None,
        **_: Any,
    ) -> None:
        self.ip_address = ip_address
        self.serial_number = serial_number
        self.access_code = access_code
        self.port = port
        self.model = model or "Snapmaker U1"
        self.base_url = f"http://{ip_address}:{port}"
        self.state = PrinterState()
        self.state.nozzles = [NozzleInfo("hardened_steel", "0.4") for _ in range(4)]
        self.state.raw_data = {
            "device_model": "Snapmaker U1",
            "ams": [
                {
                    "id": 0,
                    "serial_number": f"{serial_number}-TOOLS",
                    "module_type": "snapmaker_u1_tools",
                    "tray": [self._empty_tool_slot(i) for i in range(4)],
                }
            ],
            "ams_mapping": [0, 1, 2, 3],
        }
        self.state.sdcard = True
        self.state.store_to_sdcard = True
        self.state.wired_network = True
        self.state.developer_mode = True

        self._on_state_change = on_state_change
        self._on_print_start = on_print_start
        self._on_print_complete = on_print_complete
        self._on_ams_change = on_ams_change
        self._on_layer_change = on_layer_change
        self._on_bed_temp_update = on_bed_temp_update
        self._on_assignment_verified = on_assignment_verified
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_update = 0.0
        self._previous_state = "unknown"
        self._previous_layer = 0
        self._logging_enabled = False
        self._logs: list[MQTTLogEntry] = []
        self._drying_targets: dict[int, dict] = {}
        self._power_off_forced = False

    @staticmethod
    def _empty_tool_slot(index: int) -> dict:
        return {
            "id": index,
            "extruder_id": index,
            "tray_color": "",
            "tray_type": "",
            "tray_sub_brands": "",
            "tray_info_idx": "",
            "remain": -1,
            "state": 11,
            "exists": True,
            "nozzle_temp_min": None,
            "nozzle_temp_max": None,
        }

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.access_code:
            headers["X-Api-Key"] = self.access_code
        return headers

    def _log(self, direction: str, topic: str, payload: dict) -> None:
        if not self._logging_enabled:
            return
        self._logs.append(
            MQTTLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                topic=topic,
                direction=direction,
                payload=payload,
            )
        )
        del self._logs[:-500]

    def _request_json(self, path: str, *, method: str = "GET", data: dict | None = None, timeout: float = 5.0) -> dict:
        body = json.dumps(data).encode() if data is not None else None
        headers = self._headers()
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        self._log("out", path, data or {})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode() or "{}")
        self._log("in", path, payload if isinstance(payload, dict) else {"result": payload})
        return payload

    @classmethod
    def probe(cls, ip_address: str, port: int, access_code: str = "") -> dict:
        client = cls(ip_address=ip_address, serial_number="PROBE", access_code=access_code, port=port)
        info = client._request_json("/server/info", timeout=8.0)
        result = info.get("result", info)
        return {
            "success": bool(result),
            "state": result.get("klippy_state", "ready"),
            "model": "Snapmaker U1",
            "moonraker_version": result.get("moonraker_version"),
            "camera": client.discover_camera_urls(),
        }

    def connect(self, loop=None) -> None:  # noqa: ARG002 - mirrors Bambu client
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._poll_loop, name=f"moonraker-{self.serial_number}", daemon=True)
        self._thread.start()

    def disconnect(self, timeout: float = 0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and timeout:
            self._thread.join(timeout=timeout)
        self.state.connected = False

    def mark_power_off(self) -> bool:
        """Immediately reflect an external smart-plug power-off in the UI."""
        if not self.state.connected:
            return False
        self._power_off_forced = True
        self.state.connected = False
        return True

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception as exc:
                was_connected = self.state.connected
                self.state.connected = False
                if was_connected and self._on_state_change:
                    self._on_state_change(self.state)
                logger.debug("[%s] Moonraker poll failed: %s", self.serial_number, exc)
            self._stop.wait(self.POLL_SECONDS)

    def _poll_once(self) -> None:
        query = "print_stats&display_status&virtual_sdcard&heater_bed&extruder&extruder1&extruder2&extruder3&toolhead&webhooks"
        payload = self._request_json(f"/printer/objects/query?{query}")
        status = payload.get("result", {}).get("status", {})
        if not status:
            raise RuntimeError("Moonraker returned no printer status")

        print_stats = status.get("print_stats", {})
        display = status.get("display_status", {})
        virtual_sd = status.get("virtual_sdcard", {})
        raw_state = str(print_stats.get("state", "standby")).lower()
        mapped_state = _MOONRAKER_STATE.get(raw_state, raw_state.upper())
        filename = print_stats.get("filename") or None
        progress = float(display.get("progress", virtual_sd.get("progress", 0)) or 0) * 100
        duration = float(print_stats.get("print_duration", 0) or 0)
        remaining = int(duration * (100 - progress) / progress / 60) if progress > 0 else 0

        temps: dict[str, float | bool] = {}
        for index, key in enumerate(("extruder", "extruder1", "extruder2", "extruder3")):
            extruder = status.get(key, {})
            temp_key = "nozzle" if index == 0 else f"nozzle_{index + 1}"
            target_key = "nozzle_target" if index == 0 else f"nozzle_{index + 1}_target"
            if extruder:
                temps[temp_key] = float(extruder.get("temperature", 0) or 0)
                temps[target_key] = float(extruder.get("target", 0) or 0)
        bed = status.get("heater_bed", {})
        temps["bed"] = float(bed.get("temperature", 0) or 0)
        temps["bed_target"] = float(bed.get("target", 0) or 0)

        previous = self.state.state
        self.state.connected = True
        self._power_off_forced = False
        self.state.state = mapped_state
        self.state.current_print = filename
        self.state.subtask_name = Path(filename).stem if filename else None
        self.state.gcode_file = filename
        self.state.subtask_id = filename
        self.state.progress = round(progress, 2)
        self.state.remaining_time = remaining
        self.state.temperatures = temps
        self.state.layer_num = int(print_stats.get("info", {}).get("current_layer", 0) or 0)
        self.state.total_layers = int(print_stats.get("info", {}).get("total_layer", 0) or 0)
        self.state.active_extruder = self._active_extruder(status.get("toolhead", {}).get("extruder"))
        self.state.tray_now = self.state.active_extruder
        self._last_update = time.monotonic()

        if previous not in ("RUNNING", "PAUSE") and mapped_state == "RUNNING" and self._on_print_start:
            self._on_print_start(self._event_payload("running"))
        if (
            previous in ("RUNNING", "PAUSE")
            and mapped_state in ("FINISH", "FAILED", "IDLE")
            and self._on_print_complete
        ):
            outcome = "completed" if mapped_state == "FINISH" else "failed" if mapped_state == "FAILED" else "aborted"
            self._on_print_complete(self._event_payload(outcome))
        if self.state.layer_num != self._previous_layer and self._on_layer_change:
            self._on_layer_change(self.state.layer_num)
        self._previous_layer = self.state.layer_num
        if self._on_bed_temp_update:
            self._on_bed_temp_update(float(temps.get("bed", 0)))
        if self._on_state_change:
            self._on_state_change(self.state)

    @staticmethod
    def _active_extruder(name: Any) -> int:
        if name == "extruder":
            return 0
        if isinstance(name, str) and name.startswith("extruder"):
            try:
                return int(name.removeprefix("extruder"))
            except ValueError:
                pass
        return 0

    def _event_payload(self, status: str) -> dict:
        return {
            "filename": self.state.gcode_file or "",
            "subtask_name": self.state.subtask_name or "",
            "subtask_id": self.state.subtask_id or "",
            "status": status,
            "progress": self.state.progress,
        }

    def check_staleness(self) -> bool:
        if self.state.connected and self._last_update and time.monotonic() - self._last_update > self.STALE_SECONDS:
            self.state.connected = False
            if self._on_state_change:
                self._on_state_change(self.state)
        return self.state.connected

    def request_status_update(self) -> bool:
        try:
            self._poll_once()
            return True
        except Exception:
            return False

    def _command(self, path: str, data: dict | None = None) -> bool:
        if not self.state.connected:
            return False
        try:
            self._request_json(path, method="POST", data=data or {})
            return True
        except Exception as exc:
            logger.warning("[%s] Moonraker command %s failed: %s", self.serial_number, path, exc)
            return False

    def start_print(self, filename: str, *args, **kwargs) -> bool:  # noqa: ARG002
        return self._command("/printer/print/start", {"filename": filename})

    def pause_print(self) -> bool:
        return self._command("/printer/print/pause")

    def resume_print(self) -> bool:
        return self._command("/printer/print/resume")

    def stop_print(self) -> bool:
        return self._command("/printer/print/cancel")

    def set_bed_temperature(self, target: int) -> bool:
        return self._command("/printer/gcode/script", {"script": f"M140 S{int(target)}"})

    def set_nozzle_temperature(self, target: int, nozzle: int = 0) -> bool:
        if not 0 <= nozzle <= 3:
            return False
        tool = f"T{nozzle} " if nozzle else ""
        return self._command("/printer/gcode/script", {"script": f"{tool}M104 S{int(target)}"})

    def set_print_speed(self, mode: int) -> bool:
        percentages = {1: 50, 2: 100, 3: 124, 4: 166}
        percent = percentages.get(mode)
        return bool(percent and self._command("/printer/gcode/script", {"script": f"M220 S{percent}"}))

    def set_part_fan(self, speed: int) -> bool:
        pwm = max(0, min(255, round(speed * 2.55)))
        return self._command("/printer/gcode/script", {"script": f"M106 S{pwm}"})

    def set_fan_speed(self, fan: int, speed: int) -> bool:  # noqa: ARG002
        return self.set_part_fan(speed)

    def set_chamber_light(self, on: bool) -> bool:
        # U1's Fluidd/Moonraker configuration exposes the light as an output pin.
        value = 1 if on else 0
        return self._command(
            "/printer/gcode/script",
            {"script": f"SET_PIN PIN=chamber_light VALUE={value}"},
        )

    def send_drying_command(self, *args, **kwargs) -> bool:  # noqa: ARG002
        return False

    async def upload_file(self, local_path: Path, remote_filename: str, progress_callback=None) -> bool:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=600.0, headers=headers) as client:
                with local_path.open("rb") as handle:
                    response = await client.post(
                        f"{self.base_url}/server/files/upload",
                        data={"root": "gcodes", "path": "", "print": "false"},
                        files={"file": (remote_filename, handle, "text/x.gcode")},
                    )
                response.raise_for_status()
            if progress_callback:
                total = local_path.stat().st_size
                progress_callback(total, total)
            return True
        except Exception as exc:
            logger.error("[%s] Moonraker upload failed: %s", self.serial_number, exc)
            return False

    async def delete_file(self, remote_filename: str) -> bool:
        encoded = urllib.parse.quote(remote_filename, safe="")
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=self._headers()) as client:
                response = await client.delete(f"{self.base_url}/server/files/gcodes/{encoded}")
            return response.status_code in (200, 204, 404)
        except Exception:
            return False

    def ams_set_filament_setting(self, *, ams_id: int, tray_id: int, **values) -> bool:
        if ams_id != 0 or not 0 <= tray_id <= 3:
            return False
        tray = self.state.raw_data["ams"][0]["tray"][tray_id]
        tray.update(values)
        tray["extruder_id"] = tray_id
        tray["state"] = 11
        tray["exists"] = True
        self.state.last_ams_update = time.time()
        if self._on_ams_change:
            self._on_ams_change(self.state.raw_data["ams"])
        if self._on_state_change:
            self._on_state_change(self.state)
        return True

    def extrusion_cali_sel(self, **kwargs) -> bool:  # noqa: ARG002
        return True

    def register_assignment_verification(self, *, ams_id: int, tray_id: int, **detail) -> None:
        if self._on_assignment_verified:
            self._on_assignment_verified(ams_id, tray_id, True, detail)

    def discover_camera_urls(self) -> dict | None:
        try:
            payload = self._request_json("/server/webcams/list")
        except Exception:
            return None
        webcams = payload.get("result", {}).get("webcams", [])
        if not webcams:
            return None
        webcam = next((cam for cam in webcams if cam.get("enabled", True)), webcams[0])

        def absolute(value: str | None) -> str | None:
            if not value:
                return None
            return urllib.parse.urljoin(f"http://{self.ip_address}/", value)

        return {
            "stream_url": absolute(webcam.get("stream_url")),
            "snapshot_url": absolute(webcam.get("snapshot_url")),
            "name": webcam.get("name"),
        }

    def enable_logging(self, enabled: bool = True) -> None:
        self._logging_enabled = enabled

    @property
    def logging_enabled(self) -> bool:
        return self._logging_enabled

    def get_logs(self) -> list[MQTTLogEntry]:
        return list(self._logs)

    def clear_logs(self) -> None:
        self._logs.clear()
