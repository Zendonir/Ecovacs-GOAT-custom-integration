"""Push-Empfang für Zonenparameter.

Der Mäher schickt bei jeder Änderung von sich aus ein ``onAreaParameter`` über
MQTT — egal ob die Änderung aus der Ecovacs-App, vom Gerät selbst oder aus Home
Assistant kam. Ohne das müsste bis zum nächsten Abfragelauf gewartet werden.

deebot-client löst eingehende Nachrichten über eine Registry auf
(``deebot_client.messages.json.MESSAGES``, Name -> Message-Klasse) und kennt
``onAreaParameter`` nicht. Hier wird ein Eintrag ergänzt, der ein eigenes Event
auf den Event-Bus des Geräts legt; der Bus verträgt unbekannte Event-Typen, weil
er für sie schlicht keine Refresh-Kommandos findet.

Fällt der Push aus, bleibt das reguläre Abfragen im Coordinator die
Rückfallebene — Push ist eine Beschleunigung, keine Voraussetzung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from deebot_client.events.base import Event
from deebot_client.message import HandlingResult, MessageBodyDataDict

_LOGGER = logging.getLogger(__name__)

MESSAGE_NAME = "onAreaParameter"


@dataclass(frozen=True)
class AreaParameterEvent(Event):
    """Die Zonenparameter, wie der Mäher sie gerade gemeldet hat."""

    parameters: list[dict[str, Any]] = field(default_factory=list)


class OnAreaParameter(MessageBodyDataDict):
    """Nimmt onAreaParameter entgegen und legt es auf den Event-Bus."""

    NAME = MESSAGE_NAME

    @classmethod
    def _handle_body_data_dict(
        cls, event_bus: Any, data: dict[str, Any]
    ) -> HandlingResult:
        parameters = data.get("areaParameters")
        if not isinstance(parameters, list):
            return HandlingResult.analyse()
        event_bus.notify(AreaParameterEvent(parameters))
        return HandlingResult.success()


def register_message() -> bool:
    """Trägt onAreaParameter in die Registry von deebot-client ein.

    Liefert True, wenn der Push danach nutzbar ist. Ein bereits vorhandener
    Eintrag - etwa weil deebot-client die Nachricht inzwischen selbst kennt -
    wird nicht überschrieben.
    """
    try:
        from deebot_client.messages.json import MESSAGES
    except ImportError:  # pragma: no cover - Aufbau der Bibliothek geändert
        _LOGGER.debug("Nachrichten-Registry von deebot-client nicht gefunden")
        return False

    if not isinstance(MESSAGES, dict):  # pragma: no cover
        _LOGGER.debug("Nachrichten-Registry hat einen unerwarteten Aufbau")
        return False

    if MESSAGE_NAME in MESSAGES:
        return True

    MESSAGES[MESSAGE_NAME] = OnAreaParameter
    _LOGGER.debug("Push für %s angemeldet", MESSAGE_NAME)
    return True
