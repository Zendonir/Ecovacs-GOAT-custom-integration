"""Mäher-Einstellungen, die deebot-client nicht kennt.

Regenverzögerung, Tierschutz, automatischer Richtungswechsel, Mähplan und
Position. Die Kommandonamen stammen aus einer MQTT-Aufzeichnung der
Ecovacs-App, die Antwortformate sind am GOAT A1600 LiDAR Pro (Firmware 1.11.31)
abgefragt:

    getRainDelay        -> {"enable": 1, "delay": 150}
    getAnimProtect      -> {"enable": 1, "start": "19:0", "end": "7:15"}
    getAutoCutDirection -> {"enable": 1}
    getSchedules        -> {"list": [{"sid", "name", "subsets": <lzma>}]}
    getPos {"type": "deebotPos"}
                        -> {"deebotPos": {"x", "y", "a", "invalid"}, ...}

Geschrieben wird wie bei den Zonenparametern: das ``set``-Kommando erwartet den
vollständigen Datensatz, nicht nur das geänderte Feld.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from deebot_client.capabilities import DeviceType

from homeassistant.components.number import NumberEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, SETTINGS_INTERVAL_SECONDS
from .zone_api import EcovacsZoneApi, ZoneApiError, decompress_subsets

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import EcovacsConfigEntry
    from .controller import EcovacsController

_LOGGER = logging.getLogger(__name__)

type SettingsCoordinator = DataUpdateCoordinator[dict[str, dict[str, Any]]]

# Wochentage, wie sDay/eDay im Mähplan sie zählen (0 = Montag).
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


@dataclass(frozen=True)
class Reading:
    """Ein Kommandopaar zum Lesen und optional Schreiben einer Einstellung."""

    key: str
    get: str
    set: str | None = None
    payload: dict[str, Any] | None = None


READINGS: tuple[Reading, ...] = (
    Reading("rain_delay", "getRainDelay", "setRainDelay"),
    Reading("anim_protect", "getAnimProtect", "setAnimProtect"),
    Reading("auto_cut_direction", "getAutoCutDirection", "setAutoCutDirection"),
    Reading("schedules", "getSchedules"),
    Reading("position", "getPos", payload={"type": "deebotPos"}),
)
_BY_KEY = {reading.key: reading for reading in READINGS}


@dataclass
class SettingsRuntime:
    """Laufzeitdaten der Mäher-Einstellungen."""

    api: EcovacsZoneApi
    coordinator: SettingsCoordinator


async def async_setup_settings(
    hass: HomeAssistant, entry: EcovacsConfigEntry, controller: EcovacsController
) -> None:
    """Legt für jeden Mäher einen Einstellungs-Coordinator an."""
    for device in controller.devices:
        if device.capabilities.device_type is not DeviceType.MOWER:
            continue

        api = EcovacsZoneApi(device)

        async def _async_update(
            api: EcovacsZoneApi = api,
        ) -> dict[str, dict[str, Any]]:
            results = await asyncio.gather(
                *(api.async_send_raw(r.get, r.payload) for r in READINGS),
                return_exceptions=True,
            )
            data: dict[str, dict[str, Any]] = {}
            errors: list[BaseException] = []
            for reading, result in zip(READINGS, results, strict=True):
                if isinstance(result, BaseException):
                    errors.append(result)
                    _LOGGER.debug("%s fehlgeschlagen: %s", reading.get, result)
                else:
                    data[reading.key] = api.body_data(result)
            if len(errors) == len(READINGS):
                raise UpdateFailed(f"Keine Einstellung lesbar: {errors[0]}")
            try:
                # Hält is_busy aktuell; solange der Mäher fährt, sind die
                # schreibbaren Einstellungen gesperrt.
                await api.async_get_clean_info()
            except ZoneApiError as err:
                _LOGGER.debug("Mähstatus nicht abrufbar: %s", err)
            return data

        coordinator: SettingsCoordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{api.device_label} Einstellungen",
            update_method=_async_update,
            update_interval=timedelta(seconds=SETTINGS_INTERVAL_SECONDS),
        )
        await coordinator.async_refresh()
        controller.settings[api.device_id] = SettingsRuntime(
            api=api, coordinator=coordinator
        )


def _device_info(api: EcovacsZoneApi) -> DeviceInfo:
    """Die Einstellungen gehören an den Mäher selbst."""
    return DeviceInfo(identifiers={(DOMAIN, api.device_id)})


# --- Setup je Plattform ------------------------------------------------------


@callback
def async_setup_setting_switches(
    entry: EcovacsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Schalter für die Ja/Nein-Einstellungen."""
    async_add_entities(
        GoatSettingSwitch(runtime, key, name, icon)
        for runtime in entry.runtime_data.settings.values()
        for key, name, icon in (
            ("rain_delay", "Regenverzögerung", "mdi:weather-rainy"),
            ("anim_protect", "Tierschutz", "mdi:paw"),
            ("auto_cut_direction", "Richtung wöchentlich wechseln", "mdi:autorenew"),
        )
    )


@callback
def async_setup_setting_numbers(
    entry: EcovacsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Die Wartezeit der Regenverzögerung."""
    async_add_entities(
        GoatRainDelayMinutes(runtime)
        for runtime in entry.runtime_data.settings.values()
    )


@callback
def async_setup_setting_sensors(
    entry: EcovacsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Mähplan, Tierschutzfenster und Position."""
    entities: list[SensorEntity] = []
    for runtime in entry.runtime_data.settings.values():
        entities.append(GoatScheduleSensor(runtime))
        entities.append(GoatQuietHoursSensor(runtime))
        entities.append(GoatPositionSensor(runtime))
    async_add_entities(entities)


# --- Entities ----------------------------------------------------------------


class _GoatSettingEntity(CoordinatorEntity):
    """Gemeinsame Basis: liest einen Datensatz aus dem Coordinator."""

    _attr_has_entity_name = True

    def __init__(self, runtime: SettingsRuntime, key: str, suffix: str) -> None:
        """Initialize entity."""
        super().__init__(runtime.coordinator)
        self._api = runtime.api
        self._key = key
        self._attr_unique_id = f"{self._api.device_id}_{suffix}"
        self._attr_device_info = _device_info(self._api)

    @property
    def _data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._key) or {}

    @property
    def available(self) -> bool:
        """Nur verfügbar, wenn dieser Datensatz auch gelesen werden konnte."""
        return super().available and bool(self._data)

    async def _async_write(self, changes: dict[str, Any]) -> None:
        """Schreibt den vollständigen Datensatz mit den Änderungen darin.

        Die set-Kommandos erwarten alle Felder, nicht nur das geänderte.
        """
        reading = _BY_KEY[self._key]
        if reading.set is None:
            raise ZoneApiError(f"'{self._key}' ist nicht schreibbar.")
        # Wie bei den Zonenparametern: nur im Stand ändern.
        await self._api.async_assert_idle()
        await self._api.async_send_raw(reading.set, {**self._data, **changes})
        await self.coordinator.async_request_refresh()


class _GoatWritableEntity(_GoatSettingEntity):
    """Basis für Einstellungen, die geschrieben werden können.

    Während der Fahrt sind sie gesperrt - der Mäher übernimmt Änderungen dann
    nicht zuverlässig.
    """

    @property
    def available(self) -> bool:
        """Nur verfügbar, wenn der Mäher pausiert oder angedockt ist."""
        return super().available and not self._api.is_busy


class GoatSettingSwitch(_GoatWritableEntity, SwitchEntity):
    """Eine Einstellung mit enable-Feld."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, runtime: SettingsRuntime, key: str, name: str, icon: str
    ) -> None:
        """Initialize entity."""
        super().__init__(runtime, key, key)
        self._attr_name = name
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return true if the setting is enabled."""
        value = self._data.get("enable")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._async_write({"enable": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._async_write({"enable": 0})


class GoatRainDelayMinutes(_GoatWritableEntity, NumberEntity):
    """Wie lange der Mäher nach Regen wartet."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Regenverzögerung Wartezeit"
    _attr_icon = "mdi:timer-sand"
    _attr_native_min_value = 0
    _attr_native_max_value = 1440
    _attr_native_step = 10
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, runtime: SettingsRuntime) -> None:
        """Initialize entity."""
        super().__init__(runtime, "rain_delay", "rain_delay_minutes")

    @property
    def native_value(self) -> float | None:
        """Return the configured delay."""
        return self._data.get("delay")

    async def async_set_native_value(self, value: float) -> None:
        """Set a new delay."""
        await self._async_write({"delay": int(value)})


class GoatQuietHoursSensor(_GoatSettingEntity, SensorEntity):
    """Das Zeitfenster, in dem der Tierschutz das Mähen unterbindet."""

    _attr_name = "Tierschutz-Zeitfenster"
    _attr_icon = "mdi:sleep"

    def __init__(self, runtime: SettingsRuntime) -> None:
        """Initialize entity."""
        super().__init__(runtime, "anim_protect", "anim_protect_window")

    @staticmethod
    def _clock(value: Any) -> str | None:
        """Macht aus '19:0' die übliche Schreibweise '19:00'."""
        if not isinstance(value, str) or ":" not in value:
            return None
        hours, _, minutes = value.partition(":")
        return f"{int(hours):02d}:{int(minutes):02d}"

    @property
    def native_value(self) -> str | None:
        """Return the quiet-hours window."""
        start = self._clock(self._data.get("start"))
        end = self._clock(self._data.get("end"))
        if not start or not end:
            return None
        return f"{start}-{end}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw window plus whether it is active."""
        return {
            "aktiv": bool(self._data.get("enable")),
            "start": self._clock(self._data.get("start")),
            "ende": self._clock(self._data.get("end")),
        }


class GoatScheduleSensor(_GoatSettingEntity, SensorEntity):
    """Der Mähplan: Anzahl aktiver Einträge plus der Plan als Attribut."""

    _attr_name = "Mähplan"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, runtime: SettingsRuntime) -> None:
        """Initialize entity."""
        super().__init__(runtime, "schedules", "schedule")

    def _entries(self) -> list[dict[str, Any]]:
        """Entpackt die Einträge aller Pläne.

        getSchedules liefert je Plan ein LZMA-Feld mit den einzelnen Zeiten.
        """
        entries: list[dict[str, Any]] = []
        for plan in self._data.get("list") or []:
            if not (subsets := plan.get("subsets")):
                continue
            try:
                rows = decompress_subsets(subsets)
            except Exception:  # noqa: BLE001 - Format ist nicht dokumentiert
                _LOGGER.debug("Mähplan '%s' nicht lesbar", plan.get("name"))
                continue
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                day = row.get("sDay")
                entries.append(
                    {
                        "plan": plan.get("name"),
                        "tag": WEEKDAYS[day] if isinstance(day, int) and day < 7 else day,
                        "von": row.get("sTime"),
                        "bis": row.get("eTime"),
                        "aktiv": bool(row.get("isOpen")),
                        # 1 = Fläche mähen, 3 = Kante; weitere Werte unbekannt.
                        "typ": row.get("mowType"),
                    }
                )
        return entries

    @property
    def native_value(self) -> int | None:
        """Return how many schedule entries are active."""
        if not self._data:
            return None
        return sum(1 for entry in self._entries() if entry["aktiv"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full schedule."""
        return {"eintraege": self._entries()}


class GoatPositionSensor(_GoatSettingEntity, SensorEntity):
    """Die Position des Mähers auf der Karte.

    Der Mäher meldet ``invalid``, solange er keine gültige Position hat - etwa
    in der Ladestation. Die Entity ist dann nicht verfügbar.
    """

    _attr_name = "Position"
    _attr_icon = "mdi:crosshairs-gps"
    _attr_entity_registry_enabled_default = False

    def __init__(self, runtime: SettingsRuntime) -> None:
        """Initialize entity."""
        super().__init__(runtime, "position", "position")

    @property
    def _pos(self) -> dict[str, Any]:
        pos = self._data.get("deebotPos")
        return pos if isinstance(pos, dict) else {}

    @property
    def available(self) -> bool:
        """Nur verfügbar, solange die Position gültig ist."""
        return super().available and not self._pos.get("invalid")

    @property
    def native_value(self) -> str | None:
        """Return the position as x/y."""
        pos = self._pos
        if "x" not in pos or "y" not in pos:
            return None
        return f"{pos['x']}, {pos['y']}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw coordinates and heading."""
        pos = self._pos
        return {"x": pos.get("x"), "y": pos.get("y"), "richtung": pos.get("a")}
