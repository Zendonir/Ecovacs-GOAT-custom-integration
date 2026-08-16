"""Konstanten des Ecovacs-GOAT-Forks."""

from enum import StrEnum

from deebot_client.commands import StationAction
from deebot_client.events import LifeSpan

DOMAIN = "ecovacs_goat"

CONF_CONTINENT = "continent"
CONF_OVERRIDE_REST_URL = "override_rest_url"
CONF_OVERRIDE_MQTT_URL = "override_mqtt_url"
CONF_VERIFICATION_CODE = "verification_code"
CONF_VERIFY_MQTT_CERTIFICATE = "verify_mqtt_certificate"

SUPPORTED_LIFESPANS = (
    LifeSpan.AIR_FRESHENER,
    LifeSpan.BLADE,
    LifeSpan.BRUSH,
    LifeSpan.CLEANING_SOLUTION,
    LifeSpan.DUST_BAG,
    LifeSpan.FILTER,
    LifeSpan.HAND_FILTER,
    LifeSpan.LENS_BRUSH,
    LifeSpan.ROUND_MOP,
    LifeSpan.SEWAGE_BOX,
    LifeSpan.SIDE_BRUSH,
    LifeSpan.STATION_FILTER,
    LifeSpan.TRIMMER_BRUSH,
    LifeSpan.UNIT_CARE,
    LifeSpan.UV_SANITIZER,
    LifeSpan.WATER_SINK,
    LifeSpan.WEED_ROPE,
)

SUPPORTED_STATION_ACTIONS = (
    StationAction.CLEAN_BASE,
    StationAction.DRY_MOP,
    StationAction.EMPTY_DUSTBIN,
)

class InstanceMode(StrEnum):
    """Instance mode."""

    CLOUD = "cloud"
    SELF_HOSTED = "self_hosted"


# --- Ergänzungen dieses Forks -----------------------------------------------

# Modelle, die deebot-client noch nicht kennt. Standardmässig leer: Modelle mit
# geteiltem Capability-Satz pflegt deebot-client über Symlinks im
# hardware-Verzeichnis, der GOAT A1600 LiDAR Pro etwa als
# e4gqia.py -> aadham.py -> 51rcxt.py. Wessen Modell im Log als
# "Device class '...' not recognized" auftaucht, trägt es hier nach.
UNSUPPORTED_CLASSES: dict[str, str] = {}

# "min"/"max" sind vorsichtig geschätzt - die echten Grenzen der Ecovacs-App
# sind nicht bekannt. "observed" hält fest, welche Werte in der Aufzeichnung
# tatsächlich vorkamen; alles ausserhalb davon ist ungetestet und wird als
# Attribut an jeder Number-Entity ausgewiesen.
ZONE_FIELD_SPECS: dict[str, dict] = {
    # Der Name sagt "Level", der Wert ist aber die Schnitthöhe in Zentimetern:
    # die Ecovacs-App zeigt für mowHeightLevel 5 bzw. 7 genau "5cm" und "7cm".
    "mowHeightLevel": {
        "label": "Schnitthöhe",
        "min": 1, "max": 11, "step": 1,
        "unit": "cm",
        "icon": "mdi:grass", "observed": (3, 7),
    },
    "cutMode": {
        "label": "Mähmodus",
        "min": 1, "max": 10, "step": 1,
        "icon": "mdi:tune", "observed": (4, 7),
    },
    "obstacleHeight": {
        "label": "Hinderniserkennung",
        "min": 0, "max": 3, "step": 1,
        "icon": "mdi:sign-caution", "observed": (1, 2),
    },
    "angle": {
        "label": "Mährichtung",
        "min": 0, "max": 360, "step": 1,
        "icon": "mdi:compass", "observed": (90, 268),
    },
}

ZONE_UPDATE_INTERVAL_SECONDS = 120
# Einstellungen ändern sich selten; entsprechend gemächlich abfragen.
SETTINGS_INTERVAL_SECONDS = 300
ZONE_STATUS_INTERVAL_SECONDS = 60
