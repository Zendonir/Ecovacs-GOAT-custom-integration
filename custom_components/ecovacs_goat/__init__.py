"""Ecovacs GOAT für Home Assistant.

Die Integration erledigt zwei Dinge, die aufeinander aufbauen:

1. Sie meldet GOAT-Geräteklassen bei deebot-client an, die die Bibliothek noch
   nicht kennt (z.B. e4gqia = GOAT A1600 LiDAR Pro). Ohne diesen Schritt legt
   die offizielle Ecovacs-Integration für den Mäher nicht einmal ein
   Device-Objekt an, und es entstehen gar keine Entities.
2. Sie ergänzt die zonenspezifische Steuerung (Schnitthöhe, Mährichtung,
   Mähmodus und Hinderniserkennung je Zone, gezieltes Starten einzelner oder
   mehrerer Zonen), die deebot-client nicht als eingebaute Kommandos kennt.

WICHTIG: Es wird KEINE zweite Verbindung zum Ecovacs-Konto aufgebaut. Die
Integration nutzt die bereits von der offiziellen "ecovacs"-Integration
aufgebaute Verbindung (Authenticator + Device-Objekt) aus deren Config-Entry
und sendet ihre Kommandos über exakt denselben, bereits authentifizierten Kanal
(``Device.execute_command()``).

Voraussetzung: Die offizielle "Ecovacs"-Integration muss eingerichtet und
verbunden sein.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_NAME,
    CONF_EXTRA_CLASSES,
    ECOVACS_DOMAIN,
    PLATFORMS,
    UNSUPPORTED_CLASSES,
    UPDATE_INTERVAL_SECONDS,
)
from .registry import RegistrationError, register_classes
from .zone_api import EcovacsZoneApi, ZoneApiError

if TYPE_CHECKING:
    from deebot_client.device import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class EcovacsGoatRuntimeData:
    """Laufzeitdaten eines Config-Entry."""

    api: EcovacsZoneApi
    coordinator: DataUpdateCoordinator[list[dict[str, Any]]]
    zone_ids: list[str] = field(default_factory=list)


type EcovacsGoatConfigEntry = ConfigEntry[EcovacsGoatRuntimeData]


class EcovacsNotReadyError(Exception):
    """Die offizielle Ecovacs-Integration ist (noch) nicht verwendbar."""


def _classes_for_entry(entry: EcovacsGoatConfigEntry) -> dict[str, str]:
    """Die anzumeldenden Geräteklassen dieses Entry."""
    classes = dict(UNSUPPORTED_CLASSES)
    for class_ in entry.options.get(CONF_EXTRA_CLASSES, []):
        classes.setdefault(class_, "manuell ergänzt")
    return classes


def _device_label(device: Device) -> str:
    info = device.device_info
    return str(info.get("nick") or info.get("deviceName") or info.get("did") or "")


def find_ecovacs_devices(hass: HomeAssistant, device_name: str | None) -> list[Device]:
    """Liefert die passenden Device-Objekte der geladenen Ecovacs-Integration.

    Wirft EcovacsNotReadyError, wenn die offizielle Integration nicht geladen
    ist oder kein passendes Gerät hat. Ein gesetzter device_name filtert per
    Teilstring über nick/deviceName.
    """
    entries = hass.config_entries.async_entries(ECOVACS_DOMAIN)
    loaded = [
        e for e in entries if e.state.recoverable and getattr(e, "runtime_data", None)
    ]

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


def zone_ids_from(data: list[dict[str, Any]] | None) -> list[str]:
    """Extrahiert die areaIDs aus einer getAreaParameter-Antwort."""
    return [str(zone["areaID"]) for zone in (data or []) if "areaID" in zone]


async def _async_reload_ecovacs(hass: HomeAssistant) -> None:
    """Lädt die Ecovacs-Integration neu, damit sie die Fähigkeiten neu ausliest.

    Die Ecovacs-Integration löst die Geräteklassen einmal beim Einrichten auf.
    Da sie über ``dependencies`` vor dieser Integration geladen wird, kennt sie
    eine gerade erst angemeldete Klasse noch nicht - erst ein Neuladen legt das
    Device-Objekt für den Mäher an.
    """
    for entry in hass.config_entries.async_entries(ECOVACS_DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        _LOGGER.info("Lade Ecovacs-Eintrag '%s' neu", entry.title)
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: EcovacsGoatConfigEntry) -> bool:
    """Set up Ecovacs GOAT from a config entry."""
    # Schritt 1: fehlende Geräteklassen anmelden.
    try:
        results = await hass.async_add_executor_job(
            register_classes, _classes_for_entry(entry)
        )
    except RegistrationError as err:
        raise ConfigEntryError(str(err)) from err

    # Schritt 2: das Device-Objekt der offiziellen Integration holen. Ist es noch
    # nicht da, weil die Geräteklasse gerade erst dazugekommen ist, hilft ein
    # Neuladen der Ecovacs-Integration.
    device_name = entry.data.get(CONF_DEVICE_NAME)
    try:
        devices = find_ecovacs_devices(hass, device_name)
    except EcovacsNotReadyError as err:
        if not any(status == "registered" for status in results.values()):
            # Beim Start ist die Ecovacs-Integration womöglich noch nicht fertig;
            # Home Assistant versucht es dann automatisch erneut.
            raise ConfigEntryNotReady(str(err)) from err

        _LOGGER.debug("Gerät noch nicht bekannt (%s), lade Ecovacs neu", err)
        await _async_reload_ecovacs(hass)
        try:
            devices = find_ecovacs_devices(hass, device_name)
        except EcovacsNotReadyError as retry_err:
            raise ConfigEntryNotReady(str(retry_err)) from retry_err

    if len(devices) > 1:
        _LOGGER.warning(
            "Mehrere Ecovacs-Geräte gefunden, verwende '%s'. Über das Feld "
            "'Gerätename' lässt sich gezielt eines auswählen.",
            _device_label(devices[0]),
        )

    api = EcovacsZoneApi(devices[0])

    # Schritt 3: Zonen laden. Ein Fehlschlag ist hier bewusst nicht fatal - der
    # Mäher selbst funktioniert dann trotzdem über die offizielle Integration,
    # und die Zonen-Entities kommen dazu, sobald eine Abfrage klappt.
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
    await coordinator.async_refresh()

    zone_ids = zone_ids_from(coordinator.data)
    if zone_ids:
        _LOGGER.info("%d Zone(n) gefunden: %s", len(zone_ids), ", ".join(zone_ids))
    elif coordinator.last_update_success:
        _LOGGER.warning(
            "Der Mäher '%s' meldet keine Zonen. Lege in der Ecovacs-App Zonen an - "
            "sie erscheinen dann automatisch.",
            api.device_label,
        )
    else:
        _LOGGER.warning(
            "Zonen konnten nicht geladen werden; die Zonen-Entities erscheinen, "
            "sobald die Abfrage klappt. Der Mäher selbst ist davon nicht betroffen."
        )

    entry.runtime_data = EcovacsGoatRuntimeData(
        api=api, coordinator=coordinator, zone_ids=zone_ids
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: EcovacsGoatConfigEntry
) -> bool:
    """Unload a config entry.

    Die angemeldeten Geräteklassen bleiben bestehen: die Ecovacs-Integration
    hält ihre Device-Objekte ohnehin bis zum nächsten Neustart, und ein
    Entfernen würde weitere Einträge dieser Integration beschädigen.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: EcovacsGoatConfigEntry
) -> None:
    """Lädt den Eintrag neu, wenn die Optionen geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)
