"""Gemeinsame Bausteine für die Zonen-Entities."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from . import zone_ids_from
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import EcovacsZonesConfigEntry
    from .zone_api import EcovacsZoneApi


def zone_device_info(api: EcovacsZoneApi, zone_id: str) -> DeviceInfo:
    """Gerät für eine einzelne Zone."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"zone_{zone_id}")},
        name=f"Mäher Zone {zone_id}",
        manufacturer="Ecovacs",
        model=api.device_label,
    )


def controller_device_info(api: EcovacsZoneApi) -> DeviceInfo:
    """Gerät für die zonenübergreifenden Entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, "controller")},
        name="Mäher Zonensteuerung",
        manufacturer="Ecovacs",
        model=api.device_label,
    )


@callback
def async_setup_zone_entities(
    entry: EcovacsZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[str], Iterable[Entity]],
) -> None:
    """Legt Entities je Zone an - auch für Zonen, die erst später dazukommen.

    Wer in der Ecovacs-App eine Zone ergänzt, bekommt sie so beim nächsten
    Aktualisierungslauf automatisch, ohne die Integration neu zu laden.
    """
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _async_add_new_zones() -> None:
        new = [zone for zone in zone_ids_from(coordinator.data) if zone not in known]
        if not new:
            return
        known.update(new)
        if entities := [entity for zone in new for entity in factory(zone)]:
            async_add_entities(entities)

    _async_add_new_zones()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_zones))
