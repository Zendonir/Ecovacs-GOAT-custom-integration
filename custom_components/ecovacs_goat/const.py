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

ZONE_UPDATE_INTERVAL_SECONDS = 120
# Einstellungen ändern sich selten; entsprechend gemächlich abfragen.
SETTINGS_INTERVAL_SECONDS = 300
ZONE_STATUS_INTERVAL_SECONDS = 60
