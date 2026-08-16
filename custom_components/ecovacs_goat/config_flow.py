"""Config flow for Ecovacs GOAT support."""

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

from .const import CONF_EXTRA_CLASSES, DOMAIN, ECOVACS_DOMAIN, UNSUPPORTED_CLASSES


def _parse_classes(raw: str) -> list[str]:
    """Split a comma or whitespace separated list of device classes."""
    return [part for part in raw.replace(",", " ").split() if part]


class GoatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

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
            models = ", ".join(UNSUPPORTED_CLASSES.values())
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                description_placeholders={"models": models},
            )

        return self.async_create_entry(title="Ecovacs GOAT support", data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return GoatOptionsFlow()


class GoatOptionsFlow(OptionsFlow):
    """Allow registering further device classes without a code change."""

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
