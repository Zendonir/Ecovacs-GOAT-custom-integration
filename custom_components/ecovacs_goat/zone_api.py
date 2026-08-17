"""Rohe Area-/Zonen-Kommandos über das bereits verbundene deebot_client-Device.

Nutzt Device.execute_command(), also exakt denselben authentifizierten Kanal
(iot/devmanager.do über den bestehenden Authenticator), den die offizielle
Ecovacs-Integration auch für ihre eingebauten Kommandos verwendet. Es wird
keine eigene Verbindung/Session zum Ecovacs-Konto aufgebaut.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import lzma
from typing import Any

from deebot_client.commands.json.common import JsonCommand
from deebot_client.message import HandlingResult, HandlingState

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

# Pflichtfelder von setAreaParameter, Namen exakt wie von der Ecovacs-App
# gesendet (aus einer MQTT-Aufzeichnung des GOAT-Protokolls).
AREA_PARAM_FIELDS = ("mowHeightLevel", "cutMode", "obstacleHeight", "angle")



def decompress_subsets(payload: str) -> Any:
    """Entpackt ein base64+LZMA-Feld, wie Ecovacs es für Kartendaten nutzt.

    Format: 5 Byte LZMA-Properties, 4 Byte Länge (little endian), dann die
    Daten. Der Dekompressor erwartet an dieser Stelle das 8-Byte-Feld des
    .lzma-Containers, deshalb wird es durch "Länge unbekannt" ersetzt.
    """
    raw = base64.b64decode(payload)
    decompressor = lzma.LZMADecompressor(lzma.FORMAT_ALONE)
    data = decompressor.decompress(raw[:5] + b"\xff" * 8 + raw[9:])
    return json.loads(data.decode("utf-8"))


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
        # areaID -> Name aus der Karte; leerer Name = verwaister Datensatz
        self._area_names: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @property
    def device_label(self) -> str:
        info = self._device.device_info
        return str(info.get("nick") or info.get("deviceName") or "Mäher")

    @property
    def model(self) -> str:
        """Die Modellbezeichnung, z.B. 'GOAT A1600 LiDAR Pro'."""
        return str(self._device.device_info.get("deviceName") or "GOAT")

    @property
    def device_id(self) -> str:
        """Die did des Mähers - eindeutig pro Gerät im Ecovacs-Konto."""
        return str(self._device.device_info["did"])

    def subscribe(self, event_type: Any, callback: Any) -> Any:
        """Abonniert ein Event des Geräts; liefert die Abmeldefunktion."""
        return self._device.events.subscribe(event_type, callback)

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

    async def async_send_raw(
        self, cmd_name: str, data: dict[str, Any] | list[Any] | None = None
    ) -> dict[str, Any]:
        """Setzt ein beliebiges Kommando ab und gibt die Antwort zurück.

        Einstieg für den send_command-Dienst; die Auswertung bleibt dem Aufrufer
        überlassen.
        """
        return await self._send(cmd_name, data)

    @staticmethod
    def body_data(resp: dict[str, Any]) -> dict[str, Any]:
        """Der data-Teil einer Antwort, oder {} wenn er fehlt."""
        data = resp.get("body", {}).get("data")
        return data if isinstance(data, dict) else {}


    # --- Bereichsnamen ------------------------------------------------------

    def area_name(self, area_id: str) -> str | None:
        """Der in der App vergebene Name, oder None wenn unbekannt."""
        return self._area_names.get(str(area_id)) or None

    def is_orphan(self, area_id: str) -> bool:
        """True, wenn der Datensatz zu keiner Mähfläche mehr gehört.

        getAreaParameter liefert auch Reste gelöschter Flächen. In der Karte
        haben die einen leeren Namen; solange die Karte nicht gelesen werden
        konnte, gilt niemand als verwaist.
        """
        return str(area_id) in self._area_names and not self._area_names[str(area_id)]

    async def _async_active_map_id(self) -> str:
        """Die mid der Karte, die der Mäher gerade benutzt."""
        resp = await self._send("getCachedMapInfo")
        for info in self.body_data(resp).get("info") or []:
            if info.get("using"):
                return str(info["mid"])
        raise ZoneApiError("Keine aktive Karte gefunden.")

    async def async_refresh_area_names(self) -> dict[str, str]:
        """Liest die Bereichsnamen aus der aktiven Karte.

        getAreaSet liefert je Zeile [aid, mssid, Name, ?, x, y, ?]. Wichtig ist
        die aid der *aktiven* Karte und aid "0" für "alle Bereiche" - genau so
        fragt auch die Ecovacs-App.
        """
        resp = await self._send(
            "getAreaSet", {"mid": await self._async_active_map_id(), "aid": "0", "type": "ar"}
        )
        subsets = self.body_data(resp).get("subsets")
        if not subsets:
            raise ZoneApiError("Karte enthält keine Bereichsdaten.")

        try:
            rows = decompress_subsets(subsets)
        except (lzma.LZMAError, ValueError, UnicodeDecodeError) as err:
            raise ZoneApiError(f"Bereichsdaten nicht lesbar: {err}") from err

        names = {
            str(row[0]): str(row[2]).strip()
            for row in rows
            if isinstance(row, list) and len(row) >= 3
        }
        async with self._lock:
            self._area_names = names
        return names

    async def async_ensure_area_names(self, area_ids: list[str]) -> None:
        """Holt die Namen nach, sobald ein unbekannter Bereich auftaucht."""
        if all(str(a) in self._area_names for a in area_ids):
            return
        try:
            await self.async_refresh_area_names()
        except ZoneApiError as err:
            # Nicht schlimm: ohne Namen laufen die Zonen unter "Zone N".
            _LOGGER.debug("Bereichsnamen nicht abrufbar: %s", err)

    async def async_refresh_zones(self) -> list[dict[str, Any]]:
        """Lädt alle Zonen-Parameter frisch vom Gerät (getAreaParameter)."""
        resp = await self._send("getAreaParameter", {})
        params = self.body_data(resp).get("areaParameters") or []

        async with self._lock:
            # Vollständig ersetzen, damit in der App gelöschte Zonen nicht als
            # Karteileichen im Cache zurückbleiben.
            self._zone_cache = {
                str(p["areaID"]): dict(p) for p in params if "areaID" in p
            }
        return params

    def apply_parameters(self, params: list[dict[str, Any]]) -> None:
        """Übernimmt Zonenparameter aus einer Push-Nachricht.

        Gleiche Wirkung wie async_refresh_zones, nur ohne Abfrage: der Mäher hat
        die Werte gerade selbst geschickt.
        """
        self._zone_cache = {
            str(p["areaID"]): dict(p) for p in params if "areaID" in p
        }

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

    async def async_stop_zones(self, clean_type: str = "spotArea") -> None:
        """Stoppt den laufenden Auftrag.

        Der Mäher erwartet im stop-Kommando denselben Typ, mit dem gestartet
        wurde ("spotArea" beim Zonenmähen, "borderrotate" beim Kantenschnitt).
        """
        await self._send("clean", {"act": "stop", "content": {"type": clean_type}})

    async def async_running_clean_type(self) -> str | None:
        """Der Typ des gerade laufenden Auftrags, oder None wenn keiner läuft."""
        resp = await self._send("getCleanInfo")
        clean_state = self.body_data(resp).get("cleanState") or {}
        content = clean_state.get("content") or {}
        return content.get("type") or None

    async def async_stop_current(self) -> None:
        """Stoppt, was gerade läuft - egal ob Zonenmähen oder Kantenschnitt."""
        try:
            clean_type = await self.async_running_clean_type()
        except ZoneApiError as err:
            _LOGGER.debug("Laufenden Auftrag nicht ermittelbar: %s", err)
            clean_type = None
        await self.async_stop_zones(clean_type or "spotArea")

    # --- Kantenschnitt ------------------------------------------------------

    async def async_border_rotate_ids(self) -> str:
        """Die reid-Liste für den Kantenschnitt.

        Die App schickt beim Kantenschnitt eine Liste der zu umfahrenden Kanten
        ("reid:1;reid:3;..."). Dieselbe Liste steht im Mähplan in dem Eintrag
        mit mowType 3, dort zusätzlich mit einem "vid:"-Eintrag, den das
        clean-Kommando nicht enthält. Sie wird deshalb von dort gelesen statt
        fest verdrahtet - wer in der App Bereiche ergänzt, bekommt sie so mit.
        """
        resp = await self._send("getSchedules")
        for plan in self.body_data(resp).get("list") or []:
            if not (subsets := plan.get("subsets")):
                continue
            try:
                rows = decompress_subsets(subsets)
            except (lzma.LZMAError, ValueError, UnicodeDecodeError) as err:
                _LOGGER.debug("Mähplan '%s' nicht lesbar: %s", plan.get("name"), err)
                continue
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or row.get("mowType") != 3:
                    continue
                ids = [
                    part
                    for part in str(row.get("ids") or "").split(";")
                    if part.startswith("reid:")
                ]
                if ids:
                    return ";".join(ids)

        raise ZoneApiError(
            "Keine Kanten für den Kantenschnitt gefunden. Lege in der Ecovacs-App "
            "einmal einen Kantenschnitt im Mähplan an, damit die Kantenliste "
            "bekannt ist."
        )

    async def async_start_border_rotate(self) -> None:
        """Startet den Kantenschnitt (Trimmer-Schnitt) für die ganze Karte."""
        await self._send(
            "clean",
            {
                "act": "start",
                "content": {
                    "type": "borderrotate",
                    "value": await self.async_border_rotate_ids(),
                },
            },
        )

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
                status[name] = self.body_data(result)

        if len(errors) == len(names):
            raise ZoneApiError(f"Statusabfrage fehlgeschlagen: {errors[0]}")

        return {
            "cleanInfo": status["getCleanInfo"],
            "battery": status["getBattery"],
            "chargeState": status["getChargeState"],
        }
