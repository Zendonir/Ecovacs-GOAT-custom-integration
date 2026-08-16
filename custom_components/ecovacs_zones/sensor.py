"""Sensor-Entity: aktueller Zonen-Mähstatus."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant

from .const import STATUS_INTERVAL_SECONDS
from .entity import controller_device_info
from .zone_api import ZoneApiError

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import EcovacsZonesConfigEntry
    from .zone_api import EcovacsZoneApi

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=STATUS_INTERVAL_SECONDS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcovacsZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the status sensor."""
    async_add_entities([EcovacsZoneStatusSensor(entry.runtime_data.api)])


class EcovacsZoneStatusSensor(SensorEntity):
    """Zeigt den aktuell laufenden Zonen-Mähstatus (motionState/aktuelle Zone)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker-path"
    _attr_unique_id = "ecovacs_zone_status"
    _attr_name = "Zonen-Mähstatus"

    def __init__(self, api: EcovacsZoneApi) -> None:
        self._api = api
        self._attr_native_value: str | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._attr_device_info = controller_device_info(api)

    async def async_update(self) -> None:
        try:
            status = await self._api.async_get_status()
        except ZoneApiError as err:
            if self._attr_available:
                _LOGGER.warning("Status-Abfrage fehlgeschlagen: %s", err)
            self._attr_available = False
            return

        self._attr_available = True

        clean_info = status.get("cleanInfo") or {}
        clean_state = clean_info.get("cleanState") or {}
        content = clean_state.get("content") or {}

        self._attr_native_value = clean_state.get("motionState") or clean_info.get(
            "state"
        )
        self._attr_extra_state_attributes = {
            "state": clean_info.get("state"),
            # Nur bei type "spotArea" ist value eine Zonenliste; bei anderen
            # Mäharten steht dort etwas anderes und wird deshalb ignoriert.
            "aktuelle_zone": (
                content.get("value") if content.get("type") == "spotArea" else None
            ),
            "battery": (status.get("battery") or {}).get("value"),
            "charging": (status.get("chargeState") or {}).get("isCharging"),
        }
