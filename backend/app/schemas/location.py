from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from backend.app.services.location_service import normalize_location_name


class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    identifier: str | None = Field(default=None, max_length=100)
    parent_id: int | None = Field(default=None, gt=0)
    kind: str = Field(default="storage", max_length=30)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    position_order: int | None = Field(default=None, ge=0)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    sensor_entity_id: str | None = Field(default=None, max_length=255)
    linked_printer_id: int | None = Field(default=None, gt=0)
    linked_ams_id: int | None = Field(default=None, ge=0, le=255)
    linked_tray_id: int | None = Field(default=None, ge=0, le=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return normalize_location_name(v)

    @field_validator("identifier", "sensor_entity_id")
    @classmethod
    def normalize_optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    identifier: str | None = Field(default=None, max_length=100)
    parent_id: int | None = Field(default=None, gt=0)
    kind: str | None = Field(default=None, max_length=30)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    position_order: int | None = Field(default=None, ge=0)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    sensor_entity_id: str | None = Field(default=None, max_length=255)
    linked_printer_id: int | None = Field(default=None, gt=0)
    linked_ams_id: int | None = Field(default=None, ge=0, le=255)
    linked_tray_id: int | None = Field(default=None, ge=0, le=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_location_name(v)

    @field_validator("identifier", "sensor_entity_id")
    @classmethod
    def normalize_optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class LocationResponse(BaseModel):
    id: int
    name: str
    identifier: str | None = None
    parent_id: int | None = None
    kind: str = "storage"
    capacity: int | None = None
    position_order: int | None = None
    humidity_pct: float | None = None
    sensor_entity_id: str | None = None
    linked_printer_id: int | None = None
    linked_ams_id: int | None = None
    linked_tray_id: int | None = None
    spool_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowMoveRequest(BaseModel):
    spool_identifier: str = Field(..., min_length=1, max_length=255)
    destination_identifier: str = Field(..., min_length=1, max_length=255)


class WorkflowMoveResponse(BaseModel):
    spool_id: int
    spool_label: str
    location: LocationResponse
    inventory_status: str
    assignment_id: int | None = None
    assignment_label: str | None = None


class WorkflowBootstrapResponse(BaseModel):
    created: int
    updated: int
    total_positions: int
    u1_printer_id: int | None = None
    x1c_printer_id: int | None = None
