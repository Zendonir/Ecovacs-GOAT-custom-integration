"""Dienst zum Absetzen roher Gerätekommandos.

Gedacht fürs Erkunden des Protokolls: deebot-client kennt deutlich mehr
Kommandos, als im Capability-Satz eines Modells hinterlegt sind, und Ecovacs
dokumentiert nichts davon. Mit diesem Dienst lässt sich ausprobieren, worauf ein
Gerät tatsächlich antwortet, ohne dafür Code zu ändern.

Der Dienst nutzt denselben authentifizierten Kanal wie alle übrigen Kommandos
(siehe zone_api) und gibt die Antwort unverändert zurück.

Vorsicht: ``get``-Kommandos fragen nur ab, ``set``- und Aktionskommandos ändern
Einstellungen oder setzen das Gerät in Bewegung.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN
from .zone_api import EcovacsZoneApi

if TYPE_CHECKING:
    from deebot_client.device import Device

SERVICE_SEND_COMMAND = "send_command"

ATTR_COMMAND = "command"
ATTR_PAYLOAD = "payload"
ATTR_DEVICE_ID = "device_id"

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Optional(ATTR_PAYLOAD): vol.Any(dict, list),
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)


def _find_device(hass: HomeAssistant, device_id: str | None) -> Device:
    """Sucht das deebot-Device zu einer Home-Assistant-Geräte-ID."""
    devices: list[Device] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if runtime := getattr(entry, "runtime_data", None):
            devices.extend(runtime.devices)

    if not devices:
        raise ServiceValidationError(
            "Kein Ecovacs-Gerät geladen. Ist die Integration eingerichtet?"
        )

    if device_id is None:
        if len(devices) > 1:
            raise ServiceValidationError(
                "Mehrere Geräte vorhanden - bitte 'device_id' angeben."
            )
        return devices[0]

    entry = dr.async_get(hass).async_get(device_id)
    if entry is None:
        raise ServiceValidationError(f"Unbekannte Geräte-ID '{device_id}'.")

    dids = {ident[1] for ident in entry.identifiers if ident[0] == DOMAIN}
    for device in devices:
        if device.device_info["did"] in dids:
            return device

    raise ServiceValidationError(
        f"Gerät '{device_id}' gehört nicht zu dieser Integration."
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the services."""

    async def _async_send_command(call: ServiceCall) -> ServiceResponse:
        device = _find_device(hass, call.data.get(ATTR_DEVICE_ID))
        api = EcovacsZoneApi(device)
        response = await api.async_send_raw(
            call.data[ATTR_COMMAND], call.data.get(ATTR_PAYLOAD)
        )
        return {"response": response}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _async_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
