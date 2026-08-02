from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.spool import Spool


class Location(Base):
    """Physical storage location for filament spools (shelf, drawer, drybox, etc.)."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Case-insensitive uniqueness — LOWER(TRIM(name)); enforced via migration index.
    name_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Reserved for Phase 3 RFID shelf tags — unused in Phase 1.
    identifier: Mapped[str | None] = mapped_column(String(100))
    # Optional hierarchy and workflow metadata.  A spool is assigned to a
    # leaf position (for example BOX-A-1); parent rows model the shelf/box.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="storage")
    capacity: Mapped[int | None] = mapped_column(Integer)
    position_order: Mapped[int | None] = mapped_column(Integer)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    sensor_entity_id: Mapped[str | None] = mapped_column(String(255))
    # A live-box/AMS position may also represent a printer destination.  This
    # remains independent from Spool.location_id so the physical and logical
    # assignment are both retained.
    linked_printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id", ondelete="SET NULL"))
    linked_ams_id: Mapped[int | None] = mapped_column(Integer)
    linked_tray_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    spools: Mapped[list["Spool"]] = relationship(back_populates="location")
    parent: Mapped["Location | None"] = relationship("Location", remote_side="Location.id", back_populates="children")
    children: Mapped[list["Location"]] = relationship("Location", back_populates="parent")
