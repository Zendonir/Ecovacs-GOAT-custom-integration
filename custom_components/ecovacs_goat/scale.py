"""Umrechnung zwischen den Stufen des Mähers und den Werten der App.

Bewusst ohne Abhängigkeiten, damit die Umrechnung unabhängig von
deebot-client und Home Assistant geprüft werden kann.
"""

from __future__ import annotations

# Der Mäher speichert Stufen, die App zeigt physikalische Werte - und alle drei
# Skalen laufen GEGENLÄUFIG zur Stufe. Die Entities zeigen und nehmen den Wert
# der App; umgerechnet wird mit
#
#     Anzeige = offset + faktor * Stufe        Stufe = (Anzeige - offset) / faktor
#
# Am GOAT A1600 LiDAR Pro belegt:
#   Höhe    Stufe 1 = 9 cm,    Stufe 7 = 3 cm      (Gerät kann nur 3-9 cm)
#   Tempo   Stufe 1 = 0,7 m/s, Stufe 7 = 0,4 m/s   (schneller/langsamer geht nicht)
#   Winkel  Gerät 270 = 0°,    Gerät 180 = 90°     (App erlaubt 0-180°)
#
# Die Winkelformel deckt sich mit einer App-Anzeige zweier Flächen: gespeicherte
# 152 und 268 erscheinen dort als 118° und 2°.
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
    "angle": {
        "label": "Mährichtung",
        "min": 0, "max": 180, "step": 1,
        "unit": "°",
        "offset": 270, "faktor": -1,
        "icon": "mdi:compass",
        "observed": "0-180°",
    },
}

# obstacleHeight ist keine Längenangabe, sondern die Wahl der Umgebung. Stufe 0
# lässt das Gerät nicht zu, deshalb beginnt die Liste bei 1.
OBSTACLE_OPTIONS: dict[int, str] = {
    1: "Flacher Untergrund, kurzes Gras",
    2: "Normale Umgebung",
    3: "Hohes Gras",
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


def obstacle_label(level: int | None) -> str | None:
    """Der Klartext zu einer obstacleHeight-Stufe."""
    return OBSTACLE_OPTIONS.get(level) if level is not None else None


def obstacle_level(label: str) -> int:
    """Die Stufe zu einem Klartext; wirft KeyError bei unbekanntem Text."""
    return next(
        level for level, text in OBSTACLE_OPTIONS.items() if text == label
    )
