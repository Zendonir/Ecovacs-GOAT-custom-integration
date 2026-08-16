"""Constants for the Ecovacs GOAT support integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ecovacs_goat"
ECOVACS_DOMAIN: Final = "ecovacs"

# Device classes that ship with a capability definition in deebot-client and are
# used as the blueprint for models that do not have one yet. All GOAT definitions
# in deebot-client are identical apart from their docstring, so any of them works;
# they are tried in order and the first importable one wins.
DONOR_CLASSES: Final[tuple[str, ...]] = (
    "51rcxt",  # GOAT A3000 LiDAR Pro
    "xmp9ds",  # GOAT A1600 RTK
    "300lc5",  # GOAT O500 Panorama
    "2i0fns",  # GOAT O1200 LiDAR
    "5xu9h3",  # GOAT G1
)

# GOAT models that deebot-client does not recognise yet. Each is registered with
# the capability set of a donor class above.
UNSUPPORTED_CLASSES: Final[dict[str, str]] = {
    "e4gqia": "GOAT A1600 LiDAR Pro",
}

CONF_EXTRA_CLASSES: Final = "extra_classes"
