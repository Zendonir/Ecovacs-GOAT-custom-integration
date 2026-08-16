"""Tests für die Zonen-Protokollschicht (custom_components/ecovacs_zones).

Prüft die gesendeten Kommandos gegen das per MQTT-Aufzeichnung verifizierte
GOAT-Protokoll und die Auswertung der Antworten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.conftest import load_component_module

pytest.importorskip("deebot_client")

zone_api = load_component_module("ecovacs_zones", "zone_api")

EcovacsZoneApi = zone_api.EcovacsZoneApi
ZoneApiError = zone_api.ZoneApiError
ZoneOfflineError = zone_api.ZoneOfflineError

AREA_PARAMETERS = [
    {"areaID": "1", "mowHeightLevel": 4, "cutMode": 7, "obstacleHeight": 2, "angle": 180},
    {"areaID": "2", "mowHeightLevel": 5, "cutMode": 7, "obstacleHeight": 2, "angle": 152},
    {"areaID": "3", "mowHeightLevel": 3, "cutMode": 4, "obstacleHeight": 1, "angle": 268},
]


def ok(data: Any) -> dict[str, Any]:
    """Baut eine Antwort im Format des Ecovacs-devmanager-Endpunkts."""
    return {"ret": "ok", "resp": {"body": {"code": 0, "msg": "ok", "data": data}}}


@dataclass
class Sent:
    """Ein gesendetes Kommando, so wie es auf die Leitung ginge."""

    name: str
    payload: dict[str, Any]

    @property
    def data(self) -> Any:
        return self.payload.get("body", {}).get("data")


@dataclass
class FakeDevice:
    """Ersetzt deebot_client.device.Device."""

    responses: dict[str, Any] = field(default_factory=dict)
    sent: list[Sent] = field(default_factory=list)
    wrap_result: bool = False
    device_info: dict[str, Any] = field(
        default_factory=lambda: {
            "did": "87a9557f-1411-4a6d-9ffb-62ab597a5506",
            "class": "e4gqia",
            "resource": "VnY5sE4r",
            "deviceName": "GOAT A1600 LiDAR Pro",
            "nick": "iHans V 2.0",
        }
    )

    async def execute_command(self, command: Any) -> Any:
        self.sent.append(Sent(command.NAME, command._get_payload()))
        response = self.responses.get(command.NAME, ok({}))
        if callable(response):
            response = response()
        if self.wrap_result:
            # Manche deebot_client-Versionen liefern ein DeviceCommandResult.
            return type(
                "DeviceCommandResult", (), {"raw_response": response, "device_reached": True}
            )()
        return response


def make_api(**kwargs: Any) -> tuple[Any, FakeDevice]:
    device = FakeDevice(**kwargs)
    return EcovacsZoneApi(device), device


# --- Antwort-Auspacken -------------------------------------------------------


async def test_plain_dict_response_is_accepted():
    """Device.execute_command liefert in 17.x-18.x ein rohes dict."""
    api, _ = make_api(responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})})
    assert await api.async_refresh_zones() == AREA_PARAMETERS


async def test_device_command_result_response_is_accepted():
    """Ein DeviceCommandResult-artiges Objekt funktioniert genauso."""
    api, _ = make_api(
        responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})},
        wrap_result=True,
    )
    assert await api.async_refresh_zones() == AREA_PARAMETERS


async def test_empty_response_points_at_the_deebot_log():
    """Command.execute() schluckt Fehler und liefert dann {}."""
    api, _ = make_api(responses={"getAreaParameter": {}})
    with pytest.raises(ZoneApiError, match="deebot_client"):
        await api.async_refresh_zones()


async def test_offline_device_raises_offline_error():
    api, _ = make_api(responses={"getAreaParameter": {"ret": "fail", "errno": 4200}})
    with pytest.raises(ZoneOfflineError, match="offline"):
        await api.async_refresh_zones()


async def test_other_api_error_raises():
    api, _ = make_api(responses={"getAreaParameter": {"ret": "fail", "errno": 500}})
    with pytest.raises(ZoneApiError):
        await api.async_refresh_zones()


# --- Zonen lesen -------------------------------------------------------------


async def test_refresh_fills_the_cache():
    api, _ = make_api(responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})})
    await api.async_refresh_zones()
    assert api.get_cached("2") == AREA_PARAMETERS[1]
    assert api.get_cached("9") is None


async def test_getter_sends_no_body():
    api, device = make_api(responses={"getAreaParameter": ok({"areaParameters": []})})
    await api.async_refresh_zones()
    assert device.sent[0].name == "getAreaParameter"
    assert "body" not in device.sent[0].payload
    assert "header" in device.sent[0].payload


async def test_deleted_zones_disappear_from_the_cache():
    responses = {"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})}
    api, _ = make_api(responses=responses)
    await api.async_refresh_zones()
    assert api.get_cached("3") is not None

    responses["getAreaParameter"] = ok({"areaParameters": AREA_PARAMETERS[:2]})
    await api.async_refresh_zones()
    assert api.get_cached("3") is None


# --- Zonen schreiben ---------------------------------------------------------


async def test_set_parameter_sends_all_required_fields():
    """Ein geändertes Feld, die übrigen aus dem Cache - exakt wie die App."""
    api, device = make_api(
        responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})}
    )
    await api.async_refresh_zones()
    await api.async_set_zone_parameter("3", "cutMode", 4)

    sent = device.sent[-1]
    assert sent.name == "setAreaParameter"
    assert sent.data == {
        "areaID": "3",
        "mowHeightLevel": 3,
        "cutMode": 4,
        "obstacleHeight": 1,
        "angle": 268,
    }


async def test_set_parameter_updates_the_cache():
    api, _ = make_api(responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})})
    await api.async_refresh_zones()
    await api.async_set_zone_parameter("2", "mowHeightLevel", 4)
    assert api.get_cached("2")["mowHeightLevel"] == 4


async def test_set_parameter_refreshes_when_cache_is_cold():
    """Ohne Vorwissen wird zuerst gelesen, dann geschrieben."""
    api, device = make_api(
        responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})}
    )
    await api.async_set_zone_parameter("1", "angle", 90)
    assert [s.name for s in device.sent] == ["getAreaParameter", "setAreaParameter"]
    assert device.sent[-1].data["angle"] == 90


async def test_set_parameter_for_unknown_zone_raises():
    api, _ = make_api(responses={"getAreaParameter": ok({"areaParameters": AREA_PARAMETERS})})
    with pytest.raises(ZoneApiError, match="Unbekannte Zone"):
        await api.async_set_zone_parameter("42", "angle", 90)


async def test_incomplete_zone_data_raises_instead_of_sending_null():
    api, device = make_api(
        responses={"getAreaParameter": ok({"areaParameters": [{"areaID": "1", "angle": 90}]})}
    )
    await api.async_refresh_zones()
    with pytest.raises(ZoneApiError, match="Fehlende Parameter"):
        await api.async_set_zone_parameter("1", "angle", 120)
    assert all(s.name != "setAreaParameter" for s in device.sent)


# --- Starten und Stoppen -----------------------------------------------------


async def test_start_single_zone():
    api, device = make_api()
    await api.async_start_zones(["2"])
    assert device.sent[-1].name == "clean"
    assert device.sent[-1].data == {
        "act": "start",
        "content": {"type": "spotArea", "value": "2"},
    }


async def test_start_multiple_zones_is_comma_separated():
    api, device = make_api()
    await api.async_start_zones(["3", "2"])
    assert device.sent[-1].data["content"]["value"] == "3,2"


async def test_start_without_zones_raises():
    api, device = make_api()
    with pytest.raises(ZoneApiError):
        await api.async_start_zones([])
    assert device.sent == []


async def test_stop():
    api, device = make_api()
    await api.async_stop_zones()
    assert device.sent[-1].data == {"act": "stop", "content": {"type": "spotArea"}}


# --- Status ------------------------------------------------------------------

CLEAN_INFO = {
    "trigger": "app",
    "state": "clean",
    "cleanState": {
        "motionState": "working",
        "cid": "122",
        "content": {"type": "spotArea", "value": "2", "subContent": {"type": "idle"}},
    },
}


async def test_status_uses_verified_commands():
    api, device = make_api(
        responses={
            "getCleanInfo": ok(CLEAN_INFO),
            "getBattery": ok({"value": 87}),
            "getChargeState": ok({"isCharging": 0}),
        }
    )
    status = await api.async_get_status()

    assert sorted(s.name for s in device.sent) == [
        "getBattery",
        "getChargeState",
        "getCleanInfo",
    ]
    assert status["cleanInfo"]["cleanState"]["content"]["value"] == "2"
    assert status["battery"]["value"] == 87


async def test_status_tolerates_a_single_failing_command():
    api, _ = make_api(
        responses={
            "getCleanInfo": ok(CLEAN_INFO),
            "getBattery": {},
            "getChargeState": ok({"isCharging": 1}),
        }
    )
    status = await api.async_get_status()
    assert status["battery"] is None
    assert status["cleanInfo"]["state"] == "clean"


async def test_status_raises_when_everything_fails():
    api, _ = make_api(
        responses={"getCleanInfo": {}, "getBattery": {}, "getChargeState": {}}
    )
    with pytest.raises(ZoneApiError):
        await api.async_get_status()


# --- Transport ---------------------------------------------------------------


async def test_payload_matches_the_builtin_json_command_format():
    """Der Wrapper muss denselben Umschlag bauen wie deebot_client selbst."""
    from deebot_client.commands.json.battery import GetBattery

    api, device = make_api()
    await api.async_stop_zones()

    builtin = GetBattery()._get_payload()
    assert set(device.sent[-1].payload["header"]) == set(builtin["header"])


async def test_device_label_and_id():
    api, _ = make_api()
    assert api.device_label == "iHans V 2.0"
    assert api.device_id == "87a9557f-1411-4a6d-9ffb-62ab597a5506"
