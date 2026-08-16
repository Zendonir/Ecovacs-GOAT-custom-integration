"""Tests for the deebot-client registry patching.

Run with an installed deebot-client, e.g.::

    pip install deebot-client pytest
    pytest

The registry module is imported directly from the file so the tests do not need
Home Assistant installed.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest

deebot_hardware = pytest.importorskip("deebot_client.hardware")

_COMPONENT = Path(__file__).parent.parent / "custom_components" / "ecovacs_goat"


def _load_module(name: str) -> types.ModuleType:
    """Import a module of the component without running its package __init__."""
    if "ecovacs_goat" not in sys.modules:
        package = types.ModuleType("ecovacs_goat")
        package.__path__ = [str(_COMPONENT)]  # type: ignore[attr-defined]
        sys.modules["ecovacs_goat"] = package
    return importlib.import_module(f"ecovacs_goat.{name}")


registry = _load_module("registry")
const = _load_module("const")

# Bewusst eine Klasse, die es bei deebot-client nicht gibt und nie geben wird.
# Nicht e4gqia nehmen: der GOAT A1600 LiDAR Pro ist seit 18.x über einen Symlink
# (e4gqia.py -> aadham.py -> 51rcxt.py) unterstützt - ein Test darauf würde je
# nach installierter Version kippen.
UNKNOWN = "zz0test"


@pytest.fixture(autouse=True)
def clean_registry():
    """Keep deebot-client's caches unchanged between tests."""
    devices = dict(deebot_hardware._DEVICES)
    not_found = set(deebot_hardware._NOT_FOUND)
    yield
    deebot_hardware._DEVICES.clear()
    deebot_hardware._DEVICES.update(devices)
    deebot_hardware._NOT_FOUND.clear()
    deebot_hardware._NOT_FOUND.update(not_found)


def _lookup(class_):
    return asyncio.run(deebot_hardware.get_static_device_info(class_))


def test_unknown_class_is_unsupported_without_the_patch():
    assert _lookup(UNKNOWN) is None


def test_symlinked_models_count_as_upstream_support():
    """deebot-client teilt Definitionen über Symlinks - das gilt als Support.

    e4gqia (GOAT A1600 LiDAR Pro) ist so versorgt; wir dürfen es nicht
    überschreiben, sondern müssen beiseite treten.
    """
    if registry._import_hardware_module("deebot_client.hardware.e4gqia") is None:
        pytest.skip("installierte deebot-client-Version kennt e4gqia noch nicht")
    assert registry.register_classes({"e4gqia": "Testmodell"}) == {
        "e4gqia": "supported_upstream"
    }


def test_registration_makes_the_class_resolve_as_a_mower():
    _lookup(UNKNOWN)  # populates deebot-client's negative cache first

    assert registry.register_classes({UNKNOWN: "Testmodell"}) == {
        UNKNOWN: "registered"
    }

    info = _lookup(UNKNOWN)
    assert info is not None
    assert str(info.capabilities.device_type) == "mower"


def test_registration_is_idempotent():
    classes = {UNKNOWN: "Testmodell"}
    registry.register_classes(classes)
    assert registry.register_classes(classes) == {UNKNOWN: "already_registered"}


def test_upstream_support_takes_precedence():
    """A class deebot-client ships itself must not be overridden."""
    donor = next(
        d
        for d in const.DONOR_CLASSES
        if registry._import_hardware_module(f"deebot_client.hardware.{d}") is not None
    )
    assert registry.register_classes({donor: "donor"}) == {donor: "supported_upstream"}
    assert _lookup(donor) is not None


def test_missing_dependency_is_not_reported_as_unknown_model():
    """A broken install must raise, not silently look like an unknown model."""
    with pytest.raises(registry.RegistrationError, match="fehlt"):
        registry._import_hardware_module("tests.helper_broken_import")


def test_absent_module_returns_none():
    assert registry._import_hardware_module("deebot_client.hardware.zzzzzz") is None
    assert registry._import_hardware_module("no_such_package.zzzzzz") is None
