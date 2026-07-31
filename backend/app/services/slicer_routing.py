"""Select the correct slicer sidecar for a resolved printer profile."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings as app_settings


def is_snapmaker_u1_profile(printer_profile_json: str) -> bool:
    """Return whether a resolved/stub printer profile targets Snapmaker U1."""
    try:
        profile = json.loads(printer_profile_json)
    except (TypeError, ValueError):
        return False
    if not isinstance(profile, dict):
        return False
    identifying_fields = (
        profile.get("name"),
        profile.get("inherits"),
        profile.get("printer_model"),
        profile.get("printer_settings_id"),
    )
    return any("snapmaker u1" in str(value).lower() for value in identifying_fields if value)


async def resolve_preferred_sidecar_url(db: AsyncSession) -> str | None:
    """Resolve the existing preferred Bambu/Orca sidecar without changing semantics."""
    from backend.app.api.routes.settings import get_setting

    preferred = (await get_setting(db, "preferred_slicer")) or "bambu_studio"
    if preferred == "orcaslicer":
        configured = await get_setting(db, "orcaslicer_api_url")
        url = (configured or app_settings.slicer_api_url).strip()
    elif preferred == "bambu_studio":
        configured = await get_setting(db, "bambu_studio_api_url")
        url = (configured or app_settings.bambu_studio_api_url).strip()
    else:
        return None
    return url or None


async def resolve_snapmaker_sidecar_url(db: AsyncSession) -> str | None:
    """Resolve the dedicated Snapmaker Orca sidecar URL."""
    from backend.app.api.routes.settings import get_setting

    configured = await get_setting(db, "snapmaker_orca_api_url")
    url = (configured or app_settings.snapmaker_orca_api_url).strip()
    return url or None


async def resolve_sidecar_url_for_profile(db: AsyncSession, printer_profile_json: str) -> str | None:
    """Route U1 profiles to Snapmaker Orca and all others to the preferred sidecar."""
    if is_snapmaker_u1_profile(printer_profile_json):
        return await resolve_snapmaker_sidecar_url(db)
    return await resolve_preferred_sidecar_url(db)


async def resolve_all_sidecar_urls(db: AsyncSession) -> list[str]:
    """Return unique active sidecar URLs for merged profiles/progress polling."""
    urls = [await resolve_preferred_sidecar_url(db), await resolve_snapmaker_sidecar_url(db)]
    return list(dict.fromkeys(url for url in urls if url))
