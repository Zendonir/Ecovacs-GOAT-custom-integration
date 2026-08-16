"""Konstanten für die Ecovacs-GOAT-Integration."""

from __future__ import annotations

from typing import Any, Final

DOMAIN: Final = "ecovacs_goat"
ECOVACS_DOMAIN: Final = "ecovacs"

CONF_DEVICE_NAME: Final = "device_name"
CONF_EXTRA_CLASSES: Final = "extra_classes"

PLATFORMS: Final = ["number", "button", "sensor"]

# --- Geräteklassen -----------------------------------------------------------

# Geräteklassen, für die deebot-client eine Capability-Definition mitbringt. Sie
# dienen als Vorlage für Modelle, die noch keine haben. Alle GOAT-Definitionen in
# deebot-client sind bis auf ihren Docstring identisch, es passt also jede; sie
# werden der Reihe nach probiert, die erste importierbare gewinnt.
DONOR_CLASSES: Final[tuple[str, ...]] = (
    "51rcxt",  # GOAT A3000 LiDAR Pro
    "xmp9ds",  # GOAT A1600 RTK
    "300lc5",  # GOAT O500 Panorama
    "2i0fns",  # GOAT O1200 LiDAR
    "5xu9h3",  # GOAT G1
)

# GOAT-Modelle, die deebot-client noch nicht kennt. Jedes wird mit dem
# Capability-Satz einer Vorlage von oben angemeldet.
#
# Standardmässig leer: deebot-client pflegt Modelle, die sich einen Capability-
# Satz teilen, über Symlinks im hardware-Verzeichnis (198 der 244 Einträge in
# 18.4.0 sind Symlinks). Der GOAT A1600 LiDAR Pro ist darüber längst versorgt -
# e4gqia.py -> aadham.py -> 51rcxt.py (GOAT A3000 LiDAR Pro).
#
# Wer ein Modell hat, das im Log als "Device class '...' not recognized"
# auftaucht, trägt dessen Klasse über die Optionen der Integration nach.
UNSUPPORTED_CLASSES: Final[dict[str, str]] = {}

# --- Zonenparameter ----------------------------------------------------------

# Aus dem Reverse Engineering des GOAT-Protokolls bekannte Pflichtfelder für
# setAreaParameter. Namen exakt wie von der Ecovacs-App gesendet.
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
