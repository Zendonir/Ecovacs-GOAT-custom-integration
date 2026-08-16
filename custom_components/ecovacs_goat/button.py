"""Button-Entities: Mähen einer einzelnen Zone starten, Zonenmähen stoppen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from .entity import async_setup_zone_entities, controller_device_info, zone_device_info

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import EcovacsGoatConfigEntry
    from .zone_api import EcovacsZoneApi


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcovacsGoatConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the zone buttons."""
    api = entry.runtime_data.api

    async_add_entities([EcovacsZoneStopButton(api)])
    async_setup_zone_entities(
        entry,
        async_add_entities,
        lambda zone_id: [EcovacsZoneStartButton(api, zone_id)],
    )


class EcovacsZoneStartButton(ButtonEntity):
    """Startet das Mähen für genau eine Zone."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:play"
    _attr_name = "Mähen starten"

    def __init__(self, api: EcovacsZoneApi, zone_id: str) -> None:
        self._api = api
        self._zone_id = zone_id
        self._attr_unique_id = f"{api.device_id}_zone_{zone_id}_start"
        self._attr_device_info = zone_device_info(api, zone_id)

    async def async_press(self) -> None:
        await self._api.async_start_zones([self._zone_id])


class EcovacsZoneStopButton(ButtonEntity):
    """Stoppt das laufende Zonenmähen (geräteweit, nicht zonenspezifisch)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:stop"
    _attr_name = "Zonenmähen stoppen"

    def __init__(self, api: EcovacsZoneApi) -> None:
        self._api = api
        self._attr_unique_id = f"{api.device_id}_zone_stop"
        self._attr_device_info = controller_device_info(api)

    async def async_press(self) -> None:
        await self._api.async_stop_zones()
