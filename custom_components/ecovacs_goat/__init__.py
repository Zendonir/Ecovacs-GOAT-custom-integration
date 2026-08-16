"""Ecovacs GOAT - eigenständige Integration für Ecovacs-Mähroboter.

Fork der offiziellen Home-Assistant-Ecovacs-Integration (Apache-2.0), auf
Mähroboter zugeschnitten und um die Zonensteuerung ergänzt, die dort fehlt.

Unterschiede zum Original:

* Eigene Anmeldung und eigene MQTT-Verbindung. Die Integration ist vollständig
  unabhängig von der offiziellen Ecovacs-Integration und braucht sie nicht.
* Der Legacy-Pfad (XMPP, ``py-sucks``) und die Vacuum-Plattform sind entfernt -
  ein GOAT spricht JSON über MQTT.
* Zusätzlich: Zonenparameter (Schnitthöhe, Mähmodus, Hinderniserkennung,
  Mährichtung) je Zone und gezieltes Starten einzelner Zonen.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_OVERRIDE_REST_URL, DOMAIN, UNSUPPORTED_CLASSES
from .controller import EcovacsController
from .registry import RegistrationError, register_classes
from .util import get_client_device_id
from .zone import async_setup_zones

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.LAWN_MOWER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
type EcovacsConfigEntry = ConfigEntry[EcovacsController]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EcovacsConfigEntry) -> bool:
    """Set up this integration using UI."""
    # Geräteklassen nachtragen, die deebot-client noch nicht kennt. Standardmäßig
    # ist die Liste leer; ohne passende Definition legt deebot-client für ein
    # Gerät gar kein Device-Objekt an.
    if UNSUPPORTED_CLASSES:
        try:
            await hass.async_add_executor_job(
                register_classes, dict(UNSUPPORTED_CLASSES)
            )
        except RegistrationError as err:
            raise ConfigEntryError(str(err)) from err

    controller = EcovacsController(hass, entry.data)
    entry.async_on_unload(controller.teardown)

    await controller.initialize()
    entry.runtime_data = controller

    await async_setup_zones(hass, entry, controller)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcovacsConfigEntry) -> bool:
    """Unload config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: EcovacsConfigEntry) -> bool:
    """Migrate an old entry."""
    if CONF_USERNAME not in entry.data:
        # Einträge der früheren Fassung, die auf der offiziellen Integration
        # aufsetzte und deshalb keine eigenen Zugangsdaten hatte. Die lassen
        # sich nicht migrieren - der Eintrag muss neu angelegt werden.
        _LOGGER.error(
            "Dieser Eintrag stammt aus einer Fassung ohne eigene Zugangsdaten. "
            "Bitte entfernen und die Integration neu hinzufügen"
        )
        return False

    if entry.version == 1 and entry.minor_version < 2:
        # Persist the client device ID, which was generated on every start before
        rest_url = entry.data.get(CONF_OVERRIDE_REST_URL)
        device_id = get_client_device_id(hass, rest_url is not None, entry.data)
        hass.config_entries.async_update_entry(
            entry,
            data=entry.data | {CONF_DEVICE_ID: device_id},
            minor_version=2,
        )

    return True
