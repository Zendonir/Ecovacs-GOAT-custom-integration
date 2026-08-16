"""Rohe Area-/Zonen-Kommandos über das bereits verbundene deebot_client-Device.

Nutzt Device.execute_command(), also exakt denselben authentifizierten Kanal
(iot/devmanager.do über den bestehenden Authenticator), den die offizielle
Ecovacs-Integration auch für ihre eingebauten Kommandos verwendet. Es wird
keine eigene Verbindung/Session zum Ecovacs-Konto aufgebaut.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from deebot_client.commands.json.common import JsonCommand
from deebot_client.message import HandlingResult, HandlingState

from homeassistant.exceptions import HomeAssistantError

from .const import AREA_PARAM_FIELDS

_LOGGER = logging.getLogger(__name__)


class ZoneApiError(HomeAssistantError):
    """Ein Zonen-Kommando konnte nicht ausgeführt werden."""


class ZoneOfflineError(ZoneApiError):
    """Der Mäher ist offline und nicht erreichbar."""


class _RawJsonCommand(JsonCommand):
    """Minimaler Command-Wrapper für Kommandonamen, die deebot_client nicht als
    eigene Klasse kennt (setAreaParameter, getAreaParameter, clean/spotArea).

    Erbt von JsonCommand, damit der Payload-Aufbau (header/body) und der
    REST-Transport zu 100% dem entsprechen, was deebot_client für seine
    eingebauten Kommandos tut - auch wenn sich das Format upstream ändert.
    """

    NAME = "_raw_"  # Platzhalter, wird pro Instanz überschrieben

    def __init__(self, name: str, data: dict[str, Any] | list[Any] | None = None) -> None:
        super().__init__(data if isinstance(data, (dict, list)) else {})
        # Command liest den Namen über self.NAME; das Instanzattribut verdeckt
        # das Klassenattribut, ohne andere Instanzen zu beeinflussen.
        self.NAME = name  # type: ignore[misc]

    def _handle_response(
        self, event_bus: Any, response: dict[str, Any]
    ) -> HandlingResult:
        # Die Antwort wird von EcovacsZoneApi._send selbst ausgewertet; hier
        # reicht ein neutrales "erfolgreich verarbeitet".
        return HandlingResult(HandlingState.SUCCESS)


class EcovacsZoneApi:
    """Kapselt Lesen/Schreiben der Zonen-Parameter und Zonen-Start/Stop."""

    def __init__(self, device: Any) -> None:
        self._device = device
        self._zone_cache: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    @property
    def device_label(self) -> str:
        info = self._device.device_info
        return str(info.get("nick") or info.get("deviceName") or "Mäher")

    @property
    def device_id(self) -> str:
        """Die did des Mähers - eindeutig pro Gerät im Ecovacs-Konto."""
        return str(self._device.device_info["did"])

    async def _send(
        self, cmd_name: str, data: dict[str, Any] | list[Any] | None = None
    ) -> dict[str, Any]:
        """Sendet ein Kommando und gibt den ausgepackten resp-Teil zurück."""
        result = await self._device.execute_command(_RawJsonCommand(cmd_name, data))

        # Device.execute_command() liefert in deebot_client 17.x-18.x direkt das
        # rohe Antwort-dict. Ältere/neuere Versionen geben ein DeviceCommandResult
        # zurück - beide Formen werden unterstützt.
        response = getattr(result, "raw_response", result)
        if not isinstance(response, dict):
            raise ZoneApiError(
                f"Unerwartete Antwort auf '{cmd_name}': {response!r}"
            )

        if not response:
            # Command.execute() fängt jede Exception ab und gibt dann eine leere
            # Antwort zurück; der eigentliche Fehler steht nur im deebot_client-Log.
            raise ZoneApiError(
                f"Kommando '{cmd_name}' lieferte keine Antwort. Details stehen im "
                "Log unter 'deebot_client' (dort ggf. Debug-Logging aktivieren)."
            )

        if response.get("ret") != "ok":
            if response.get("errno") == 4200:
                raise ZoneOfflineError(
                    f"Mäher ist offline (Kommando '{cmd_name}')."
                )
            raise ZoneApiError(f"Ecovacs-API-Fehler für '{cmd_name}': {response}")

        return response.get("resp", response)

    @staticmethod
    def _body_data(resp: dict[str, Any]) -> dict[str, Any]:
        data = resp.get("body", {}).get("data")
        return data if isinstance(data, dict) else {}

    async def async_refresh_zones(self) -> list[dict[str, Any]]:
        """Lädt alle Zonen-Parameter frisch vom Gerät (getAreaParameter)."""
        resp = await self._send("getAreaParameter", {})
        params = self._body_data(resp).get("areaParameters") or []

        async with self._lock:
            # Vollständig ersetzen, damit in der App gelöschte Zonen nicht als
            # Karteileichen im Cache zurückbleiben.
            self._zone_cache = {
                str(p["areaID"]): dict(p) for p in params if "areaID" in p
            }
        return params

    def get_cached(self, area_id: str) -> dict[str, Any] | None:
        return self._zone_cache.get(str(area_id))

    async def async_set_zone_parameter(
        self, area_id: str, field: str, value: int
    ) -> None:
        """Setzt EIN Feld einer Zone; die übrigen Pflichtfelder werden aus dem
        zuletzt bekannten Stand ergänzt (die Ecovacs-API erwartet immer alle)."""
        area_id = str(area_id)

        async with self._lock:
            current = dict(self._zone_cache.get(area_id, {}))

        if not current:
            await self.async_refresh_zones()
            async with self._lock:
                current = dict(self._zone_cache.get(area_id, {}))

        if not current:
            raise ZoneApiError(f"Unbekannte Zone '{area_id}'.")

        merged: dict[str, Any] = {"areaID": area_id}
        for name in AREA_PARAM_FIELDS:
            merged[name] = value if name == field else current.get(name)

        if missing := [name for name in AREA_PARAM_FIELDS if merged[name] is None]:
            raise ZoneApiError(
                f"Fehlende Parameter für Zone {area_id}: {', '.join(missing)}. "
                "Bitte die Integration neu laden, damit die Werte geladen werden."
            )

        await self._send("setAreaParameter", merged)

        async with self._lock:
            self._zone_cache[area_id] = dict(merged)

    async def async_start_zones(self, area_ids: list[str]) -> None:
        """Startet das Mähen für eine oder mehrere Zonen."""
        if not area_ids:
            raise ZoneApiError("Keine Zone zum Starten angegeben.")
        value = ",".join(str(a) for a in area_ids)
        await self._send(
            "clean", {"act": "start", "content": {"type": "spotArea", "value": value}}
        )

    async def async_stop_zones(self) -> None:
        """Stoppt das laufende Zonenmähen."""
        await self._send("clean", {"act": "stop", "content": {"type": "spotArea"}})

    async def async_get_status(self) -> dict[str, Any]:
        """Fragt Mähstatus, Akku und Ladezustand ab.

        Nutzt die drei einzeln verifizierten Kommandos statt eines Sammel-
        kommandos. Schlägt eines fehl, bleibt sein Wert None statt die ganze
        Abfrage scheitern zu lassen.
        """
        names = ("getCleanInfo", "getBattery", "getChargeState")
        results = await asyncio.gather(
            *(self._send(name) for name in names), return_exceptions=True
        )

        status: dict[str, Any] = {}
        errors: list[BaseException] = []
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                errors.append(result)
                status[name] = None
                _LOGGER.debug("Statusabfrage '%s' fehlgeschlagen: %s", name, result)
            else:
                status[name] = self._body_data(result)

        if len(errors) == len(names):
            raise ZoneApiError(f"Statusabfrage fehlgeschlagen: {errors[0]}")

        return {
            "cleanInfo": status["getCleanInfo"],
            "battery": status["getBattery"],
            "chargeState": status["getChargeState"],
        }
