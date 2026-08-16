"""Ecovacs GOAT support for Home Assistant.

Teaches deebot-client about GOAT models it does not recognise yet, so the
official Ecovacs integration can create entities for them. This integration
provides no entities of its own.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.start import async_at_started

from .const import CONF_EXTRA_CLASSES, ECOVACS_DOMAIN, UNSUPPORTED_CLASSES
from .registry import RegistrationError, register_classes, unregister_classes

_LOGGER = logging.getLogger(__name__)

type GoatConfigEntry = ConfigEntry[dict[str, str]]


def _classes_for_entry(entry: GoatConfigEntry) -> dict[str, str]:
    """Return the device classes to register for this entry."""
    classes = dict(UNSUPPORTED_CLASSES)
    for class_ in entry.options.get(CONF_EXTRA_CLASSES, []):
        classes.setdefault(class_, "user configured")
    return classes


async def async_setup_entry(hass: HomeAssistant, entry: GoatConfigEntry) -> bool:
    """Set up Ecovacs GOAT support from a config entry."""
    classes = _classes_for_entry(entry)
    try:
        results = await hass.async_add_executor_job(register_classes, classes)
    except RegistrationError as err:
        raise ConfigEntryError(str(err)) from err

    entry.runtime_data = results
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if any(status == "registered" for status in results.values()):
        # The Ecovacs integration resolves capabilities once, while setting up.
        # If it did that before us, its devices are still marked unsupported and
        # only a reload picks them up. Waiting for startup to finish keeps this
        # clear of Home Assistant's own setup.
        async_at_started(hass, _reload_ecovacs_entries)

    return True


async def _reload_ecovacs_entries(hass: HomeAssistant) -> None:
    """Reload the Ecovacs integration so it re-reads device capabilities."""
    entries = hass.config_entries.async_entries(ECOVACS_DOMAIN)
    if not entries:
        _LOGGER.warning(
            "No Ecovacs integration configured — set it up to get GOAT entities"
        )
        return

    for ecovacs_entry in entries:
        if ecovacs_entry.state is not ConfigEntryState.LOADED:
            continue
        _LOGGER.info("Reloading Ecovacs entry %s to apply GOAT support", ecovacs_entry.title)
        await hass.config_entries.async_reload(ecovacs_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: GoatConfigEntry) -> bool:
    """Unload a config entry."""
    classes = _classes_for_entry(entry)
    await hass.async_add_executor_job(
        unregister_classes, classes, entry.runtime_data or {}
    )
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: GoatConfigEntry) -> None:
    """Reload the config entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
