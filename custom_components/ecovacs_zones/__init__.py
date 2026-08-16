"""Ecovacs GOAT Zonensteuerung.

Ergänzt die offizielle Home-Assistant-Ecovacs-Integration um zonenspezifische
Funktionen (Schnitthöhe/Mährichtung/Mähmodus/Hinderniserkennung pro Zone,
gezieltes Starten einzelner oder mehrerer Zonen), die deebot_client selbst noch
nicht als eingebaute Kommandos kennt.

WICHTIG: Es wird KEINE zweite Verbindung zum Ecovacs-Konto aufgebaut. Diese
Integration nutzt die bereits von der offiziellen "ecovacs"-Integration
aufgebaute Verbindung (Authenticator + Device-Objekt) aus deren Config-Entry
(`entry.runtime_data.devices`) und sendet ihre Kommandos über exakt denselben,
bereits authentifizierten Kanal (`Device.execute_command()`).

Voraussetzung: Die offizielle "Ecovacs"-Integration muss eingerichtet und
geladen sein. Die Einrichtung erfolgt über die Home-Assistant-Oberfläche
(Einstellungen -> Geräte & Dienste -> Integration hinzufügen).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_NAME,
    ECOVACS_DOMAIN,
    PLATFORMS,
    UPDATE_INTERVAL_SECONDS,
)
from .zone_api import EcovacsZoneApi, ZoneApiError

if TYPE_CHECKING:
    from deebot_client.device import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class EcovacsZonesRuntimeData:
    """Laufzeitdaten eines Config-Entry."""

    api: EcovacsZoneApi
    coordinator: DataUpdateCoordinator[list[dict[str, Any]]]
    zone_ids: list[str] = field(default_factory=list)


type EcovacsZonesConfigEntry = ConfigEntry[EcovacsZonesRuntimeData]


class EcovacsNotReadyError(Exception):
    """Die offizielle Ecovacs-Integration ist (noch) nicht verwendbar."""


def find_ecovacs_devices(hass: HomeAssistant, device_name: str | None) -> list[Device]:
    """Liefert die passenden Device-Objekte der geladenen Ecovacs-Integration.

    Wirft EcovacsNotReadyError, wenn die offizielle Integration nicht geladen
    ist oder keine Geräte hat. Ein gesetzter device_name filtert per Teilstring
    über nick/deviceName.
    """
    entries = hass.config_entries.async_entries(ECOVACS_DOMAIN)
    loaded = [e for e in entries if e.state.recoverable and getattr(e, "runtime_data", None)]

    if not loaded:
        raise EcovacsNotReadyError(
            "Keine geladene Ecovacs-Integration gefunden. Bitte zuerst die "
            "offizielle 'Ecovacs'-Integration einrichten."
        )

    devices: list[Device] = []
    for entry in loaded:
        devices.extend(getattr(entry.runtime_data, "devices", []))

    if not devices:
        raise EcovacsNotReadyError(
            "Die Ecovacs-Integration ist geladen, hat aber keine Geräte gefunden."
        )

    if device_name:
        needle = device_name.lower()
        filtered = [d for d in devices if needle in _device_label(d).lower()]
        if not filtered:
            known = ", ".join(_device_label(d) for d in devices)
            raise EcovacsNotReadyError(
                f"Kein Ecovacs-Gerät passt auf '{device_name}'. Gefunden: {known}."
            )
        devices = filtered

    return devices


def _device_label(device: Device) -> str:
    info = device.device_info
    return str(info.get("nick") or info.get("deviceName") or info.get("did") or "")


def zone_ids_from(data: list[dict[str, Any]] | None) -> list[str]:
    """Extrahiert die areaIDs aus einer getAreaParameter-Antwort."""
    return [str(zone["areaID"]) for zone in (data or []) if "areaID" in zone]


async def async_setup_entry(
    hass: HomeAssistant, entry: EcovacsZonesConfigEntry
) -> bool:
    """Set up Ecovacs GOAT Zonensteuerung from a config entry."""
    device_name = entry.data.get(CONF_DEVICE_NAME)

    try:
        devices = find_ecovacs_devices(hass, device_name)
    except EcovacsNotReadyError as err:
        # Beim Start ist die Ecovacs-Integration womöglich noch nicht fertig;
        # Home Assistant versucht es dann automatisch erneut.
        raise ConfigEntryNotReady(str(err)) from err

    if len(devices) > 1:
        _LOGGER.warning(
            "Mehrere Ecovacs-Geräte gefunden, verwende '%s'. Über die Option "
            "'Gerätename' lässt sich gezielt eines auswählen.",
            _device_label(devices[0]),
        )

    api = EcovacsZoneApi(devices[0])

    async def _async_update() -> list[dict[str, Any]]:
        try:
            return await api.async_refresh_zones()
        except ZoneApiError as err:
            raise UpdateFailed(str(err)) from err

    coordinator: DataUpdateCoordinator[list[dict[str, Any]]] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=f"{entry.title} Zonen",
        update_method=_async_update,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
    )

    # Wirft ConfigEntryNotReady, wenn das erste Laden scheitert - Home Assistant
    # wiederholt die Einrichtung dann selbstständig.
    await coordinator.async_config_entry_first_refresh()

    zone_ids = zone_ids_from(coordinator.data)
    if zone_ids:
        _LOGGER.info("%d Zone(n) gefunden: %s", len(zone_ids), ", ".join(zone_ids))
    else:
        _LOGGER.warning(
            "Der Mäher '%s' meldet keine Zonen. Lege in der Ecovacs-App Zonen an "
            "und lade diese Integration danach neu.",
            api.device_label,
        )

    entry.runtime_data = EcovacsZonesRuntimeData(
        api=api, coordinator=coordinator, zone_ids=zone_ids
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: EcovacsZonesConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
