"""Test-Setup.

Die Tests decken die Protokollschicht ab und sollen ohne eine vollständige
Home-Assistant-Installation laufen. Fehlt homeassistant, wird nur das eine
benötigte Symbol (HomeAssistantError) nachgebildet.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

COMPONENTS = Path(__file__).parent.parent / "custom_components"

try:  # pragma: no cover - abhängig von der Testumgebung
    import homeassistant.exceptions  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    package = types.ModuleType("homeassistant")
    package.__path__ = []  # type: ignore[attr-defined]
    exceptions = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Stub für homeassistant.exceptions.HomeAssistantError."""

    exceptions.HomeAssistantError = HomeAssistantError  # type: ignore[attr-defined]
    package.exceptions = exceptions  # type: ignore[attr-defined]
    sys.modules["homeassistant"] = package
    sys.modules["homeassistant.exceptions"] = exceptions


def load_component_module(package_name: str, module: str) -> types.ModuleType:
    """Importiert ein Modul einer Custom Integration ohne deren __init__.py."""
    import importlib

    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(COMPONENTS / package_name)]  # type: ignore[attr-defined]
        sys.modules[package_name] = package
    return importlib.import_module(f"{package_name}.{module}")
