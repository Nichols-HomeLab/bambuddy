"""Tests for profile-aware routing across simultaneous slicer sidecars."""

from unittest.mock import MagicMock, patch

import pytest

from backend.app.services import slicer_routing


@pytest.mark.parametrize(
    "profile",
    [
        '{"name":"Snapmaker U1 (0.4 nozzle)"}',
        '{"inherits":"Snapmaker U1 0.6 nozzle"}',
        '{"printer_model":"Snapmaker U1"}',
        '{"printer_settings_id":["Snapmaker U1 (0.4 nozzle)"]}',
    ],
)
def test_identifies_snapmaker_u1_profiles(profile):
    assert slicer_routing.is_snapmaker_u1_profile(profile) is True


@pytest.mark.parametrize("profile", ['{"name":"Bambu Lab X1 Carbon"}', "not json", "[]"])
def test_rejects_non_u1_profiles(profile):
    assert slicer_routing.is_snapmaker_u1_profile(profile) is False


@pytest.mark.asyncio
async def test_u1_profile_uses_dedicated_snapmaker_url():
    async def fake_get_setting(_db, key):
        return {
            "preferred_slicer": "bambu_studio",
            "bambu_studio_api_url": "http://bambu:3000",
            "snapmaker_orca_api_url": "http://snapmaker:3000",
        }.get(key)

    with patch("backend.app.api.routes.settings.get_setting", new=fake_get_setting):
        url = await slicer_routing.resolve_sidecar_url_for_profile(MagicMock(), '{"name":"Snapmaker U1 (0.4 nozzle)"}')

    assert url == "http://snapmaker:3000"


@pytest.mark.asyncio
async def test_bambu_profile_preserves_preferred_sidecar():
    async def fake_get_setting(_db, key):
        return {
            "preferred_slicer": "bambu_studio",
            "bambu_studio_api_url": "http://bambu:3000",
            "snapmaker_orca_api_url": "http://snapmaker:3000",
        }.get(key)

    with patch("backend.app.api.routes.settings.get_setting", new=fake_get_setting):
        url = await slicer_routing.resolve_sidecar_url_for_profile(
            MagicMock(), '{"name":"Bambu Lab X1 Carbon 0.4 nozzle"}'
        )

    assert url == "http://bambu:3000"


@pytest.mark.asyncio
async def test_all_urls_are_unique_when_defaults_overlap():
    async def fake_get_setting(_db, key):
        return {
            "preferred_slicer": "orcaslicer",
            "orcaslicer_api_url": "http://same:3000",
            "snapmaker_orca_api_url": "http://same:3000",
        }.get(key)

    with patch("backend.app.api.routes.settings.get_setting", new=fake_get_setting):
        urls = await slicer_routing.resolve_all_sidecar_urls(MagicMock())

    assert urls == ["http://same:3000"]
