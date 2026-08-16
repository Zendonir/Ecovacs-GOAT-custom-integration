"""Registration of missing GOAT device classes into deebot-client.

deebot-client resolves a device's capabilities from its device class (e.g.
``e4gqia`` for the GOAT A1600 LiDAR Pro) by importing
``deebot_client.hardware.<class>``. Models without such a module are reported as
"Device class '<class>' not recognized" and get no entities at all.

Every GOAT capability definition that ships with deebot-client is byte-identical
apart from its docstring, so a missing model can be served by reusing an existing
one. This module injects those entries into deebot-client's in-memory registry
rather than shipping a copy of the definition, which keeps it correct across
deebot-client releases.

All access to deebot-client internals is defensive: if the library's layout
changes, registration fails with a clear error instead of breaking Home
Assistant's Ecovacs integration.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from .const import DONOR_CLASSES

_LOGGER = logging.getLogger(__name__)

_HARDWARE_PACKAGE = "deebot_client.hardware"
# Layout used by deebot-client < 13, kept as a fallback.
_LEGACY_HARDWARE_PACKAGE = "deebot_client.hardware.deebot"


class RegistrationError(Exception):
    """Raised when a device class could not be registered."""


def _import_hardware_module(name: str) -> Any | None:
    """Import a deebot-client hardware module, or return None if it does not exist.

    A ``ModuleNotFoundError`` naming the module itself, or one of its parent
    packages, means it simply is not there. Any other name means a dependency of
    the module is missing — a real failure that must not be reported as "this
    model is unknown".
    """
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as err:
        if err.name and (name == err.name or name.startswith(f"{err.name}.")):
            return None
        raise RegistrationError(
            f"Importing {name} failed because {err.name!r} is missing. "
            "This points at a broken deebot-client installation."
        ) from err


def _load_donor_device_info() -> tuple[str, Any]:
    """Return the class name and static device info of the first usable donor."""
    errors: list[str] = []
    for donor in DONOR_CLASSES:
        for package in (_HARDWARE_PACKAGE, _LEGACY_HARDWARE_PACKAGE):
            if (module := _import_hardware_module(f"{package}.{donor}")) is None:
                continue
            get_device_info = getattr(module, "get_device_info", None)
            if get_device_info is None:
                errors.append(f"{package}.{donor} has no get_device_info()")
                continue
            return donor, get_device_info()
    raise RegistrationError(
        "No usable GOAT capability definition found in deebot-client "
        f"(tried {', '.join(DONOR_CLASSES)}). Details: {'; '.join(errors) or 'none'}"
    )


def _hardware_registry() -> tuple[Any, dict[str, Any], set[str]]:
    """Return the deebot-client hardware module and its caches."""
    try:
        hardware = importlib.import_module(_HARDWARE_PACKAGE)
    except ModuleNotFoundError as err:  # pragma: no cover - deebot-client missing
        raise RegistrationError(
            "deebot-client is not installed. Set up the Ecovacs integration first."
        ) from err

    devices = getattr(hardware, "_DEVICES", None)
    not_found = getattr(hardware, "_NOT_FOUND", None)
    if not isinstance(devices, dict) or not isinstance(not_found, set):
        raise RegistrationError(
            "deebot-client's hardware registry has an unexpected layout. "
            "This integration needs an update for the installed deebot-client version."
        )
    return hardware, devices, not_found


def register_classes(classes: dict[str, str]) -> dict[str, str]:
    """Register capability definitions for the given device classes.

    Returns a mapping of device class to a short status describing what happened.
    Blocking: imports modules, so call from an executor.
    """
    _, devices, not_found = _hardware_registry()
    donor: str | None = None
    device_info: Any = None
    results: dict[str, str] = {}

    for class_, model in classes.items():
        # A class deebot-client already knows about natively — either an upstream
        # definition exists or we registered it earlier. Never override upstream.
        if class_ in devices:
            results[class_] = "already_registered"
            _LOGGER.debug("Device class %s (%s) is already known", class_, model)
            continue
        if _import_hardware_module(f"{_HARDWARE_PACKAGE}.{class_}") is not None:
            # Upstream added support in the meantime; let deebot-client handle it.
            not_found.discard(class_)
            results[class_] = "supported_upstream"
            _LOGGER.info(
                "deebot-client now supports %s (%s) natively, nothing to do",
                class_,
                model,
            )
            continue

        if device_info is None:
            donor, device_info = _load_donor_device_info()

        devices[class_] = device_info
        # Drop the negative cache entry, otherwise a lookup that already failed
        # during this Home Assistant run would keep returning "unsupported".
        not_found.discard(class_)
        results[class_] = "registered"
        _LOGGER.info(
            "Registered device class %s (%s) using the capabilities of %s",
            class_,
            model,
            donor,
        )

    return results


def unregister_classes(classes: dict[str, str], results: dict[str, str]) -> None:
    """Remove the entries added by :func:`register_classes`."""
    try:
        _, devices, _ = _hardware_registry()
    except RegistrationError:  # pragma: no cover - library vanished
        return
    for class_ in classes:
        if results.get(class_) == "registered":
            devices.pop(class_, None)
            _LOGGER.debug("Unregistered device class %s", class_)
