"""Anmeldung fehlender GOAT-Geräteklassen bei deebot-client.

deebot-client löst die Fähigkeiten eines Geräts über dessen Geräteklasse auf
(z.B. e4gqia für den GOAT A1600 LiDAR Pro), indem es
``deebot_client.hardware.<klasse>`` importiert. Für Modelle ohne so ein Modul
erscheint "Device class '<klasse>' not recognized" im Log, und es entstehen
überhaupt keine Entities - die offizielle Ecovacs-Integration legt für so ein
Gerät nicht einmal ein Device-Objekt an.

Modelle, die sich einen Capability-Satz teilen, pflegt deebot-client selbst über
Symlinks im hardware-Verzeichnis (in 18.4.0 sind 198 der 244 Einträge Symlinks;
der GOAT A1600 LiDAR Pro etwa als e4gqia.py -> aadham.py -> 51rcxt.py). Für ein
Modell, das dort noch fehlt, macht dieses Modul dasselbe zur Laufzeit: es trägt
einen Eintrag in die Registry von deebot-client ein, der auf eine vorhandene
Definition zeigt, statt eine Kopie auszuliefern - so bleibt es über
deebot-client-Versionen hinweg korrekt.

Da der Import einer per Symlink versorgten Klasse ganz normal gelingt, gilt sie
korrekt als "von upstream unterstützt", und dieses Modul tritt beiseite.

Einmal angemeldete Klassen werden nicht wieder entfernt: die Ecovacs-Integration
hält ihre Device-Objekte ohnehin bis zum nächsten Neustart, und ein Entfernen
würde weitere Config-Entries dieser Integration beschädigen.

Alle Zugriffe auf deebot-client-Interna sind defensiv: ändert sich der Aufbau
der Bibliothek, scheitert die Anmeldung mit einer klaren Meldung, statt die
Ecovacs-Integration zu beschädigen.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from .const import DONOR_CLASSES

_LOGGER = logging.getLogger(__name__)

_HARDWARE_PACKAGE = "deebot_client.hardware"
# Aufbau von deebot-client < 13, als Rückfallebene.
_LEGACY_HARDWARE_PACKAGE = "deebot_client.hardware.deebot"


class RegistrationError(Exception):
    """Eine Geräteklasse konnte nicht angemeldet werden."""


def _import_hardware_module(name: str) -> Any | None:
    """Importiert ein deebot-client-Hardware-Modul, oder None wenn es fehlt.

    Nennt der ModuleNotFoundError das Modul selbst oder eines seiner
    Elternpakete, ist es schlicht nicht vorhanden. Jeder andere Name bedeutet,
    dass eine Abhängigkeit des Moduls fehlt - ein echter Fehler, der nicht als
    "Modell unbekannt" durchgehen darf.
    """
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as err:
        if err.name and (name == err.name or name.startswith(f"{err.name}.")):
            return None
        raise RegistrationError(
            f"Import von {name} fehlgeschlagen, weil {err.name!r} fehlt. "
            "Das deutet auf eine beschädigte deebot-client-Installation hin."
        ) from err


def _load_donor_device_info() -> tuple[str, Any]:
    """Liefert Name und StaticDeviceInfo der ersten brauchbaren Vorlage."""
    errors: list[str] = []
    for donor in DONOR_CLASSES:
        for package in (_HARDWARE_PACKAGE, _LEGACY_HARDWARE_PACKAGE):
            if (module := _import_hardware_module(f"{package}.{donor}")) is None:
                continue
            get_device_info = getattr(module, "get_device_info", None)
            if get_device_info is None:
                errors.append(f"{package}.{donor} hat kein get_device_info()")
                continue
            return donor, get_device_info()
    raise RegistrationError(
        "Keine brauchbare GOAT-Definition in deebot-client gefunden "
        f"(geprüft: {', '.join(DONOR_CLASSES)}). Details: {'; '.join(errors) or 'keine'}"
    )


def _hardware_registry() -> tuple[dict[str, Any], set[str]]:
    """Liefert die beiden Caches der deebot-client-Hardware-Registry."""
    try:
        hardware = importlib.import_module(_HARDWARE_PACKAGE)
    except ModuleNotFoundError as err:  # pragma: no cover - deebot-client fehlt
        raise RegistrationError(
            "deebot-client ist nicht installiert. Bitte zuerst die offizielle "
            "Ecovacs-Integration einrichten."
        ) from err

    devices = getattr(hardware, "_DEVICES", None)
    not_found = getattr(hardware, "_NOT_FOUND", None)
    if not isinstance(devices, dict) or not isinstance(not_found, set):
        raise RegistrationError(
            "Die Hardware-Registry von deebot-client hat einen unerwarteten "
            "Aufbau. Diese Integration muss für die installierte "
            "deebot-client-Version angepasst werden."
        )
    return devices, not_found


def register_classes(classes: dict[str, str]) -> dict[str, str]:
    """Meldet Capability-Definitionen für die angegebenen Geräteklassen an.

    Liefert je Geräteklasse einen Status. Blockierend (importiert Module),
    daher aus einem Executor aufrufen.
    """
    devices, not_found = _hardware_registry()
    donor: str | None = None
    device_info: Any = None
    results: dict[str, str] = {}

    for class_, model in classes.items():
        # Klasse, die deebot-client schon kennt - entweder gibt es upstream eine
        # Definition, oder wir haben sie vorhin angemeldet. Upstream gewinnt.
        if class_ in devices:
            results[class_] = "already_registered"
            _LOGGER.debug("Geräteklasse %s (%s) ist bereits bekannt", class_, model)
            continue

        if _import_hardware_module(f"{_HARDWARE_PACKAGE}.{class_}") is not None:
            # Upstream unterstützt die Klasse inzwischen selbst.
            not_found.discard(class_)
            results[class_] = "supported_upstream"
            _LOGGER.info(
                "deebot-client unterstützt %s (%s) inzwischen selbst, nichts zu tun",
                class_,
                model,
            )
            continue

        if device_info is None:
            donor, device_info = _load_donor_device_info()

        devices[class_] = device_info
        # Negativ-Cache leeren, sonst liefert eine Abfrage, die in diesem
        # Home-Assistant-Lauf schon fehlgeschlagen ist, weiter "nicht unterstützt".
        not_found.discard(class_)
        results[class_] = "registered"
        _LOGGER.info(
            "Geräteklasse %s (%s) mit den Fähigkeiten von %s angemeldet",
            class_,
            model,
            donor,
        )

    return results
