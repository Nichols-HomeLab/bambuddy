"""Integration coverage for the shelf/live-feeder workflow."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.printer import Printer


async def _add_workflow_printers(db: AsyncSession) -> tuple[Printer, Printer]:
    u1 = Printer(
        name="Workshop U1",
        serial_number="WORKFLOW-U1",
        ip_address="10.0.0.41",
        access_code="",
        connection_type="snapmaker_moonraker",
        connection_port=7125,
        model="Snapmaker U1",
        nozzle_count=4,
        is_active=True,
    )
    x1c = Printer(
        name="Workshop X1C",
        serial_number="WORKFLOW-X1C",
        ip_address="10.0.0.42",
        access_code="12345678",
        connection_type="bambu",
        connection_port=8883,
        model="X1C",
        nozzle_count=1,
        is_active=True,
    )
    db.add_all([u1, x1c])
    await db.commit()
    await db.refresh(u1)
    await db.refresh(x1c)
    return u1, x1c


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bootstrap_and_scan_move_preserve_location_and_assignment(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    u1, x1c = await _add_workflow_printers(db_session)

    first = await async_client.post("/api/v1/inventory/workflow/bootstrap")
    assert first.status_code == 200, first.text
    assert first.json()["total_positions"] == 37
    assert first.json()["u1_printer_id"] == u1.id
    assert first.json()["x1c_printer_id"] == x1c.id
    assert first.json()["created"] > 0

    second = await async_client.post("/api/v1/inventory/workflow/bootstrap")
    assert second.status_code == 200, second.text
    assert second.json()["created"] == 0

    listed = await async_client.get("/api/v1/inventory/locations")
    locations = {item["identifier"]: item for item in listed.json() if item["identifier"]}
    assert locations["BOX-A-1"]["parent_id"] == locations["BOX-A"]["id"]
    assert locations["U1-T3"]["linked_printer_id"] == u1.id
    assert locations["U1-T3"]["linked_tray_id"] == 2
    assert locations["X1C-AMS-2"]["linked_printer_id"] == x1c.id

    humidity = await async_client.patch(
        f"/api/v1/inventory/locations/{locations['BOX-A']['id']}",
        json={"humidity_pct": 18.5, "sensor_entity_id": "sensor.box_a_humidity"},
    )
    assert humidity.status_code == 200, humidity.text

    spool_response = await async_client.post(
        "/api/v1/inventory/spools",
        json={
            "material": "PLA",
            "brand": "SUNLU",
            "color_name": "Grey",
            "tag_uid": "AABBCCDD",
        },
    )
    assert spool_response.status_code == 200, spool_response.text
    spool_id = spool_response.json()["id"]

    stored = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": "AABBCCDD", "destination_identifier": "BOX-A-1"},
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["inventory_status"] == "stored"
    assert stored.json()["assignment_id"] is None
    stored_spool = (await async_client.get(f"/api/v1/inventory/spools/{spool_id}")).json()
    assert stored_spool["location_id"] == locations["BOX-A-1"]["id"]
    assert stored_spool["storage_box_humidity"] == 18.5
    humidity_update = await async_client.patch(
        f"/api/v1/inventory/locations/{locations['BOX-A']['id']}",
        json={"humidity_pct": 19.0},
    )
    assert humidity_update.status_code == 200
    stored_spool = (await async_client.get(f"/api/v1/inventory/spools/{spool_id}")).json()
    assert stored_spool["storage_box_humidity"] == 19.0

    loaded_u1 = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": f"SPOOL-{spool_id}", "destination_identifier": "U1-T3"},
    )
    assert loaded_u1.status_code == 200, loaded_u1.text
    assert loaded_u1.json()["inventory_status"] == "loaded_u1"
    assert loaded_u1.json()["assignment_label"] == "U1-T3"
    assignments = (await async_client.get("/api/v1/inventory/assignments")).json()
    assert len(assignments) == 1
    assert assignments[0]["printer_id"] == u1.id
    assert assignments[0]["ams_id"] == 0
    assert assignments[0]["tray_id"] == 2

    loaded_ams = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": str(spool_id), "destination_identifier": "X1C-AMS-2"},
    )
    assert loaded_ams.status_code == 200, loaded_ams.text
    assert loaded_ams.json()["inventory_status"] == "loaded_x1c_ams"
    assignments = (await async_client.get("/api/v1/inventory/assignments")).json()
    assert len(assignments) == 1
    assert assignments[0]["printer_id"] == x1c.id
    assert assignments[0]["tray_id"] == 1

    drying = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": str(spool_id), "destination_identifier": "DRYER-1"},
    )
    assert drying.status_code == 200, drying.text
    assert drying.json()["inventory_status"] == "drying"
    drying_spool = (await async_client.get(f"/api/v1/inventory/spools/{spool_id}")).json()
    assert drying_spool["drying_status"] == "drying"

    back_to_storage = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": str(spool_id), "destination_identifier": "BOX-B-4"},
    )
    assert back_to_storage.status_code == 200, back_to_storage.text
    assert back_to_storage.json()["assignment_id"] is None
    assert (await async_client.get("/api/v1/inventory/assignments")).json() == []
    dried_spool = (await async_client.get(f"/api/v1/inventory/spools/{spool_id}")).json()
    assert dried_spool["drying_status"] == "dry"
    assert dried_spool["last_dried"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scan_move_rejects_an_occupied_position(async_client: AsyncClient):
    await async_client.post("/api/v1/inventory/workflow/bootstrap")
    first = (await async_client.post("/api/v1/inventory/spools", json={"material": "PLA"})).json()
    second = (await async_client.post("/api/v1/inventory/spools", json={"material": "PETG"})).json()

    moved = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": str(first["id"]), "destination_identifier": "BOX-C-2"},
    )
    assert moved.status_code == 200
    blocked = await async_client.post(
        "/api/v1/inventory/workflow/move",
        json={"spool_identifier": str(second["id"]), "destination_identifier": "BOX-C-2"},
    )
    assert blocked.status_code == 409
    assert "occupied" in blocked.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_writes_require_auth(async_client: AsyncClient):
    await async_client.post(
        "/api/v1/auth/setup",
        json={
            "auth_enabled": True,
            "admin_username": "workflowadmin",
            "admin_password": "AdminPass1!",
        },
    )
    assert (await async_client.post("/api/v1/inventory/workflow/bootstrap")).status_code == 401
    assert (
        await async_client.post(
            "/api/v1/inventory/workflow/move",
            json={"spool_identifier": "1", "destination_identifier": "BOX-A-1"},
        )
    ).status_code == 401
