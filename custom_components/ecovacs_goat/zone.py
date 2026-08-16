"""Zonensteuerung - die Ergänzung dieses Forks gegenüber dem Original.

Alles Zonenspezifische steckt bewusst in dieser einen Datei; die aus dem
Original übernommenen Module bleiben dadurch fast unverändert und lassen sich
später leicht gegen eine neuere Fassung des Originals abgleichen. Die
Plattform-Module rufen von hier nur je eine Setup-Funktion auf.

Die Kommandos (getAreaParameter/setAreaParameter/clean mit spotArea) kennt
deebot-client nicht als eigene Klassen; sie stammen aus einer MQTT-Aufzeichnung
des GOAT-Protokolls und laufen über denselben authentifizierten Kanal wie alle
eingebauten Kommandos (siehe zone_api).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from deebot_client.capabilities import DeviceType

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    ZONE_FIELD_SPECS,
    ZONE_STATUS_INTERVAL_SECONDS,
    ZONE_UPDATE_INTERVAL_SECONDS,
)
from .push import AreaParameterEvent, register_message
from .zone_api import EcovacsZoneApi, ZoneApiError

if TYPE_CHECKING:
    from deebot_client.device import Device

    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import EcovacsConfigEntry
    from .controller import EcovacsController

_LOGGER = logging.getLogger(__name__)

type ZoneCoordinator = DataUpdateCoordinator[list[dict[str, Any]]]


@dataclass
class ZoneRuntime:
    """Zonen-Laufzeitdaten eines Mähers."""

    api: EcovacsZoneApi
    coordinator: ZoneCoordinator


def zone_ids_from(data: list[dict[str, Any]] | None) -> list[str]:
    """Extrahiert die areaIDs aus einer getAreaParameter-Antwort."""
    return [str(zone["areaID"]) for zone in (data or []) if "areaID" in zone]


async def async_setup_zones(
    hass: HomeAssistant, entry: EcovacsConfigEntry, controller: EcovacsController
) -> None:
    """Legt für jeden Mäher einen Zonen-Coordinator an.

    Ein Fehlschlag ist bewusst nicht fatal: der Mäher selbst funktioniert dann
    weiterhin, und die Zonen-Entities kommen dazu, sobald eine Abfrage klappt.
    """
    for device in controller.devices:
        if device.capabilities.device_type is not DeviceType.MOWER:
            continue

        api = EcovacsZoneApi(device)

        async def _async_update(api: EcovacsZoneApi = api) -> list[dict[str, Any]]:
            try:
                zones = await api.async_refresh_zones()
            except ZoneApiError as err:
                raise UpdateFailed(str(err)) from err
            # Namen nur nachladen, wenn ein unbekannter Bereich auftaucht.
            await api.async_ensure_area_names(zone_ids_from(zones))
            return zones

        coordinator: ZoneCoordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{api.device_label} Zonen",
            update_method=_async_update,
            update_interval=timedelta(seconds=ZONE_UPDATE_INTERVAL_SECONDS),
        )
        await coordinator.async_refresh()

        if zone_ids := [
            zone for zone in zone_ids_from(coordinator.data) if not api.is_orphan(zone)
        ]:
            _LOGGER.info(
                "%s: %d Zone(n) gefunden: %s",
                api.device_label,
                len(zone_ids),
                ", ".join(f"{z} ({api.area_name(z) or 'ohne Namen'})" for z in zone_ids),
            )
        elif coordinator.last_update_success:
            _LOGGER.warning(
                "%s meldet keine Zonen. Lege in der Ecovacs-App Zonen an - sie "
                "erscheinen dann automatisch",
                api.device_label,
            )

        if register_message():
            _async_subscribe_push(entry, api, coordinator)

        controller.zones[api.device_id] = ZoneRuntime(api=api, coordinator=coordinator)


def _async_subscribe_push(
    entry: EcovacsConfigEntry, api: EcovacsZoneApi, coordinator: ZoneCoordinator
) -> None:
    """Lässt gemeldete Zonenparameter direkt in den Coordinator laufen."""

    async def _on_area_parameter(event: AreaParameterEvent) -> None:
        api.apply_parameters(event.parameters)
        await api.async_ensure_area_names(zone_ids_from(event.parameters))
        # Setzt die Daten und benachrichtigt die Entities, ohne abzufragen.
        coordinator.async_set_updated_data(event.parameters)

    entry.async_on_unload(
        api.subscribe(AreaParameterEvent, _on_area_parameter)
    )


# --- Geräte ------------------------------------------------------------------


def _zone_device_info(api: EcovacsZoneApi, zone_id: str) -> DeviceInfo:
    """Gerät für eine einzelne Zone, aufgehängt unter dem Mäher.

    Der Name kommt aus der Karte („Mähfläche 1"); ohne Karte bleibt es bei der
    areaID. Umbenennen in Home Assistant überschreibt das dauerhaft.
    """
    label = api.area_name(zone_id) or f"Zone {zone_id}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"{api.device_id}_zone_{zone_id}")},
        name=f"{api.device_label} {label}",
        manufacturer="Ecovacs",
        model=api.model,
        via_device=(DOMAIN, api.device_id),
    )


def _controller_device_info(api: EcovacsZoneApi) -> DeviceInfo:
    """Gerät für die zonenübergreifenden Entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{api.device_id}_zones")},
        name=f"{api.device_label} Zonensteuerung",
        manufacturer="Ecovacs",
        model=api.model,
        via_device=(DOMAIN, api.device_id),
    )


# --- Setup je Plattform ------------------------------------------------------


@callback
def _async_add_per_zone(
    entry: EcovacsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[ZoneRuntime, str], Iterable[Entity]],
) -> None:
    """Legt Entities je Zone an - auch für Zonen, die erst später dazukommen.

    Wer in der Ecovacs-App eine Zone ergänzt, bekommt sie so beim nächsten
    Aktualisierungslauf automatisch. Das deckt auch den Fall ab, dass beim
    Einrichten noch keine Zonen abrufbar waren.
    """
    for runtime in entry.runtime_data.zones.values():
        known: set[str] = set()

        @callback
        def _add_new(runtime: ZoneRuntime = runtime, known: set[str] = known) -> None:
            new = [
                zone
                for zone in zone_ids_from(runtime.coordinator.data)
                if zone not in known and not runtime.api.is_orphan(zone)
            ]
            if not new:
                return
            known.update(new)
            if entities := [e for zone in new for e in factory(runtime, zone)]:
                async_add_entities(entities)

        _add_new()
        entry.async_on_unload(runtime.coordinator.async_add_listener(_add_new))


@callback
def async_setup_zone_numbers(
    entry: EcovacsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Number-Entities je Zone und Parameter."""
    _async_add_per_zone(
        entry,
        async_add_entities,
        lambda runtime, zone_id: [
            EcovacsZoneNumber(runtime, zone_id, field) for field in ZONE_FIELD_SPECS
        ],
    )


@callback
def async_setup_zone_buttons(
    entry: EcovacsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Start-Button je Zone plus ein Stopp-Button je Mäher."""
    async_add_entities(
        EcovacsZoneStopButton(runtime) for runtime in entry.runtime_data.zones.values()
    )
    _async_add_per_zone(
        entry,
        async_add_entities,
        lambda runtime, zone_id: [EcovacsZoneStartButton(runtime, zone_id)],
    )


@callback
def async_setup_zone_sensors(
    entry: EcovacsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Mähstatus-Sensor je Mäher."""
    async_add_entities(
        EcovacsZoneStatusSensor(runtime) for runtime in entry.runtime_data.zones.values()
    )


# --- Entities ----------------------------------------------------------------


class EcovacsZoneNumber(CoordinatorEntity, NumberEntity):
    """Ein einzelner Zonen-Parameter, z.B. die Schnitthöhe von Zone 2."""

    _attr_has_entity_name = True

    def __init__(self, runtime: ZoneRuntime, zone_id: str, field: str) -> None:
        """Initialize entity."""
        super().__init__(runtime.coordinator)
        self._api = runtime.api
        self._zone_id = zone_id
        self._field = field
        spec = ZONE_FIELD_SPECS[field]

        self._attr_unique_id = f"{self._api.device_id}_zone_{zone_id}_{field}"
        # has_entity_name stellt den Gerätenamen ("... Zone 2") voran, hier steht
        # deshalb nur der Parameter.
        self._attr_name = spec["label"]
        self._attr_icon = spec["icon"]
        self._attr_native_min_value = spec["min"]
        self._attr_native_max_value = spec["max"]
        self._attr_native_step = spec["step"]
        self._attr_native_unit_of_measurement = spec.get("unit")
        self._attr_device_info = _zone_device_info(self._api, zone_id)

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
        """Return the current value."""
        cached = self._api.get_cached(self._zone_id)
        if not cached:
            return None
        return cached.get(self._field)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new value."""
        await self._api.async_set_zone_parameter(self._zone_id, self._field, int(value))
        self.async_write_ha_state()
        # Der Mäher quittiert jedes setAreaParameter mit "ok", auch wenn er den
        # Wert nicht übernimmt. Ohne Rückfrage stünde bis zum nächsten regulären
        # Lauf (zwei Minuten) der gewünschte statt des tatsächlichen Werts da.
        # Der Coordinator entprellt die Anfrage, schnelle Klickfolgen lösen
        # deshalb nur eine Abfrage aus.
        await self.coordinator.async_request_refresh()


class EcovacsZoneStartButton(ButtonEntity):
    """Startet das Mähen für genau eine Zone."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:play"
    _attr_name = "Mähen starten"

    def __init__(self, runtime: ZoneRuntime, zone_id: str) -> None:
        """Initialize entity."""
        self._api = runtime.api
        self._zone_id = zone_id
        self._attr_unique_id = f"{self._api.device_id}_zone_{zone_id}_start"
        self._attr_device_info = _zone_device_info(self._api, zone_id)

    async def async_press(self) -> None:
        """Press the button."""
        await self._api.async_start_zones([self._zone_id])


class EcovacsZoneStopButton(ButtonEntity):
    """Stoppt das laufende Zonenmähen (geräteweit, nicht zonenspezifisch)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:stop"
    _attr_name = "Zonenmähen stoppen"

    def __init__(self, runtime: ZoneRuntime) -> None:
        """Initialize entity."""
        self._api = runtime.api
        self._attr_unique_id = f"{self._api.device_id}_zone_stop"
        self._attr_device_info = _controller_device_info(self._api)

    async def async_press(self) -> None:
        """Press the button."""
        await self._api.async_stop_zones()


class EcovacsZoneStatusSensor(SensorEntity):
    """Zeigt den aktuell laufenden Zonen-Mähstatus."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker-path"
    _attr_name = "Mähstatus"
    _attr_should_poll = True

    def __init__(self, runtime: ZoneRuntime) -> None:
        """Initialize entity."""
        self._api = runtime.api
        self._attr_unique_id = f"{self._api.device_id}_zone_status"
        self._attr_native_value: str | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._attr_device_info = _controller_device_info(self._api)

    async def async_update(self) -> None:
        """Poll the current status."""
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
