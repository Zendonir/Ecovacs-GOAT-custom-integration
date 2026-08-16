"""Config flow für die Ecovacs GOAT Zonensteuerung."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from . import EcovacsNotReadyError, find_ecovacs_devices
from .const import CONF_DEVICE_NAME, DOMAIN, ECOVACS_DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Optional(CONF_DEVICE_NAME): str})


class EcovacsZonesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ein-Schritt-Flow: optional ein Gerät auswählen, sonst nichts zu tun."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if not self.hass.config_entries.async_entries(ECOVACS_DOMAIN):
            return self.async_abort(reason="ecovacs_not_configured")

        errors: dict[str, str] = {}
        # Immer gesetzt, damit der {error}-Platzhalter im Formulartext auch beim
        # ersten Aufruf aufgelöst werden kann.
        placeholders: dict[str, str] = {"error": ""}

        if user_input is not None:
            device_name = user_input.get(CONF_DEVICE_NAME) or None
            try:
                devices = find_ecovacs_devices(self.hass, device_name)
            except EcovacsNotReadyError as err:
                errors["base"] = "no_device"
                placeholders["error"] = str(err)
            else:
                device = devices[0]
                # Verhindert, dass dasselbe Gerät zweimal eingebunden wird - die
                # Entity- und Geräte-IDs der Zonen sind nicht mehrgerätefähig.
                await self.async_set_unique_id(str(device.device_info["did"]))
                self._abort_if_unique_id_configured()

                label = str(
                    device.device_info.get("nick")
                    or device.device_info.get("deviceName")
                    or "Mäher"
                )
                data = {CONF_DEVICE_NAME: device_name} if device_name else {}
                return self.async_create_entry(title=f"{label} Zonen", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )
