"""Umrechnung zwischen den Stufen des Mähers und den Werten der App.

Bewusst ohne Abhängigkeiten, damit die Umrechnung unabhängig von
deebot-client und Home Assistant geprüft werden kann.
"""

from __future__ import annotations

# Der Mäher speichert Stufen, die App zeigt physikalische Werte - und bei Höhe
# und Geschwindigkeit laufen beide Skalen GEGENLÄUFIG. Die Entities zeigen und
# nehmen deshalb den Wert der App; umgerechnet wird mit
#
#     Anzeige = offset + faktor * Stufe        Stufe = (Anzeige - offset) / faktor
#
# Belegt am GOAT A1600 LiDAR Pro gegen die App-Anzeige zweier Flächen:
#   Höhe          Stufe 1 = 9 cm,   Stufe 7 = 3 cm
#   Geschwindigkeit Stufe 1 = 0,7 m/s, Stufe 7 = 0,4 m/s, Stufe 4 = 0,55 m/s
#   Hindernishöhe Stufe 1 = 10 cm,  Stufe 2 = 15 cm
#
# Die Hindernishöhe ist nur an zwei Punkten belegt, ihre Skala also
# extrapoliert. Der Winkel wird unverändert durchgereicht.
ZONE_FIELD_SPECS: dict[str, dict] = {
    "mowHeightLevel": {
        "label": "Schnitthöhe",
        "min": 3, "max": 9, "step": 1,
        "unit": "cm",
        "offset": 10, "faktor": -1,
        "icon": "mdi:grass",
        "observed": "3-9 cm",
    },
    "cutMode": {
        "label": "Geschwindigkeit",
        "min": 0.4, "max": 0.7, "step": 0.05,
        "unit": "m/s",
        "offset": 0.75, "faktor": -0.05,
        "icon": "mdi:speedometer",
        "observed": "0,4-0,7 m/s",
    },
    "obstacleHeight": {
        "label": "Hinderniserkennung",
        "min": 5, "max": 20, "step": 5,
        "unit": "cm",
        "offset": 5, "faktor": 5,
        "icon": "mdi:sign-caution",
        "observed": "10 und 15 cm",
    },
    "angle": {
        "label": "Mährichtung",
        "min": 0, "max": 360, "step": 1,
        "unit": "°",
        "offset": 0, "faktor": 1,
        "icon": "mdi:compass",
        "observed": "90-268°",
    },
}


def to_display(field: str, level: float | None) -> float | None:
    """Rechnet die Gerätestufe in den Wert um, den die Ecovacs-App zeigt."""
    if level is None:
        return None
    spec = ZONE_FIELD_SPECS[field]
    return round(spec["offset"] + spec["faktor"] * level, 2)


def to_device(field: str, value: float) -> int:
    """Rechnet den angezeigten Wert zurück in die Gerätestufe."""
    spec = ZONE_FIELD_SPECS[field]
    return round((value - spec["offset"]) / spec["faktor"])
