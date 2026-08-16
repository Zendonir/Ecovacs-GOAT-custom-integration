"""Config flow für die Ecovacs-GOAT-Integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_DEVICE_NAME,
    CONF_EXTRA_CLASSES,
    DOMAIN,
    ECOVACS_DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema({vol.Optional(CONF_DEVICE_NAME): str})


def _parse_classes(raw: str) -> list[str]:
    """Zerlegt eine mit Komma oder Leerzeichen getrennte Liste von Klassen."""
    return [part for part in raw.replace(",", " ").split() if part]


class EcovacsGoatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ein-Schritt-Flow: optional ein Gerät eingrenzen, sonst nichts zu tun."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if not self.hass.config_entries.async_entries(ECOVACS_DOMAIN):
            return self.async_abort(reason="ecovacs_not_configured")

        if user_input is None:
            # Absichtlich ohne Geräteprüfung: ist eine Geräteklasse noch nicht
            # angemeldet, kennt die Ecovacs-Integration den Mäher an dieser
            # Stelle noch gar nicht. Gesucht wird erst beim Einrichten, nachdem
            # etwaige fehlende Klassen nachgetragen wurden.
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_SCHEMA
            )

        data = {}
        if device_name := user_input.get(CONF_DEVICE_NAME):
            data[CONF_DEVICE_NAME] = device_name

        return self.async_create_entry(title="Ecovacs GOAT", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EcovacsGoatOptionsFlow()


class EcovacsGoatOptionsFlow(OptionsFlow):
    """Erlaubt weitere Geräteklassen ohne Codeänderung."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_EXTRA_CLASSES: _parse_classes(
                        user_input.get(CONF_EXTRA_CLASSES, "")
                    )
                }
            )

        current = " ".join(self.config_entry.options.get(CONF_EXTRA_CLASSES, []))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_EXTRA_CLASSES, default=current): str}
            ),
        )
