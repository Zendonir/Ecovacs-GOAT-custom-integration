"""Konstanten für ecovacs_zones."""

from __future__ import annotations

from typing import Any, Final

DOMAIN: Final = "ecovacs_zones"
ECOVACS_DOMAIN: Final = "ecovacs"

CONF_DEVICE_NAME: Final = "device_name"

PLATFORMS: Final = ["number", "button", "sensor"]

# Aus dem Reverse Engineering des GOAT-Protokolls bekannte Pflichtfelder für
# setAreaParameter. Reihenfolge/Namen exakt wie von der Ecovacs-App gesendet.
AREA_PARAM_FIELDS: Final = ("mowHeightLevel", "cutMode", "obstacleHeight", "angle")

# Die Grenzwerte ("min"/"max") sind vorsichtig geschätzt - die echten Grenzen der
# Ecovacs-App sind nicht bekannt. "observed" hält fest, welche Werte in der
# MQTT-Aufzeichnung tatsächlich vorkamen; alles ausserhalb davon ist ungetestet.
# Der beobachtete Bereich wird als Attribut an jeder Number-Entity ausgewiesen.
FIELD_SPECS: Final[dict[str, dict[str, Any]]] = {
    "mowHeightLevel": {
        "label": "Schnitthöhe",
        "min": 1,
        "max": 11,
        "step": 1,
        "icon": "mdi:grass",
        "observed": (3, 5),
    },
    "cutMode": {
        "label": "Mähmodus",
        "min": 1,
        "max": 10,
        "step": 1,
        "icon": "mdi:tune",
        "observed": (4, 7),
    },
    "obstacleHeight": {
        "label": "Hinderniserkennung",
        "min": 0,
        "max": 3,
        "step": 1,
        "icon": "mdi:sign-caution",
        "observed": (1, 2),
    },
    "angle": {
        "label": "Mährichtung",
        "min": 0,
        "max": 360,
        "step": 1,
        "icon": "mdi:compass",
        "observed": (90, 268),
    },
}

UPDATE_INTERVAL_SECONDS: Final = 120
STATUS_INTERVAL_SECONDS: Final = 60
