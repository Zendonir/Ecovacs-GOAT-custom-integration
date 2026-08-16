"""Number-Entities: ein Entity pro Zone x Parameter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import FIELD_SPECS
from .entity import async_setup_zone_entities, zone_device_info

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import EcovacsZonesConfigEntry
    from .zone_api import EcovacsZoneApi


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EcovacsZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the zone number entities."""
    runtime = entry.runtime_data

    async_setup_zone_entities(
        entry,
        async_add_entities,
        lambda zone_id: [
            EcovacsZoneNumber(runtime.coordinator, runtime.api, zone_id, field)
            for field in FIELD_SPECS
        ],
    )


class EcovacsZoneNumber(CoordinatorEntity, NumberEntity):
    """Ein einzelner Zonen-Parameter (z.B. Schnitthöhe von Zone 2)."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: Any, api: EcovacsZoneApi, zone_id: str, field: str
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._zone_id = zone_id
        self._field = field
        spec = FIELD_SPECS[field]

        self._attr_unique_id = f"ecovacs_zone_{zone_id}_{field}"
        self._attr_name = f"Zone {zone_id} {spec['label']}"
        self._attr_icon = spec["icon"]
        self._attr_native_min_value = spec["min"]
        self._attr_native_max_value = spec["max"]
        self._attr_native_step = spec["step"]
        self._attr_device_info = zone_device_info(api, zone_id)

        # Die echten Grenzen der Ecovacs-App sind unbekannt; min/max oben sind
        # geschätzt. Der beobachtete Bereich macht sichtbar, was tatsächlich
        # belegt ist - Werte ausserhalb davon sind ungetestet.
        observed_min, observed_max = spec["observed"]
        self._attr_extra_state_attributes = {
            "beobachteter_bereich": f"{observed_min}-{observed_max}",
            "areaID": zone_id,
        }

    @property
    def available(self) -> bool:
        """Nur verfügbar, solange die Zone noch existiert."""
        return super().available and self._api.get_cached(self._zone_id) is not None

    @property
    def native_value(self) -> float | None:
        cached = self._api.get_cached(self._zone_id)
        if not cached:
            return None
        return cached.get(self._field)

    async def async_set_native_value(self, value: float) -> None:
        await self._api.async_set_zone_parameter(
            self._zone_id, self._field, int(value)
        )
        self.async_write_ha_state()
