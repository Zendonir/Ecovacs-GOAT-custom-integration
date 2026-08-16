# Ecovacs GOAT Support

Home Assistant custom integration that makes the **Ecovacs GOAT A1600 LiDAR Pro**
(and other GOAT models deebot-client does not recognise yet) work with the
official [Ecovacs integration](https://www.home-assistant.io/integrations/ecovacs/).

## The problem

The Ecovacs integration talks to the cloud through
[`deebot-client`](https://github.com/DeebotUniverse/client.py). That library
resolves a device's capabilities from its **device class** — a six-character code
the cloud reports per model. For a model without a capability definition you get
this in the log and **no entities at all**:

```
Device class 'e4gqia' not recognized. Please add support for it
```

`e4gqia` is the GOAT A1600 LiDAR Pro (`GOAT_INT_A1600_LIDAR_PLUS_EU`).

## The approach

Every GOAT capability definition shipped by deebot-client is byte-identical apart
from its docstring — `51rcxt` (A3000 LiDAR Pro) and `xmp9ds` (A1600 RTK) differ
only in one comment line. So an unknown GOAT model can be served by reusing an
existing definition.

This integration registers the missing device class in deebot-client's in-memory
registry, pointing it at a sibling GOAT definition, and then reloads the Ecovacs
integration so it re-reads the capabilities. It **reuses** the existing
definition instead of shipping a copy, so it stays correct when deebot-client
changes its GOAT capabilities.

It provides no entities of its own — the mower, sensors, switches and buttons all
come from the official Ecovacs integration.

When deebot-client adds the device class upstream, this integration detects that,
steps aside, and can be removed.

## Requirements

- Home Assistant 2024.12 or newer
- The official **Ecovacs** integration set up with your Ecovacs account

## Installation

### HACS

1. HACS → three-dot menu → *Custom repositories*
2. Add `https://github.com/zendonir/ecovacs-goat-custom-integration`, category
   *Integration*
3. Install **Ecovacs GOAT Support** and restart Home Assistant

### Manual

Copy `custom_components/ecovacs_goat` into your `config/custom_components/`
directory and restart Home Assistant.

## Setup

*Settings → Devices & Services → Add Integration → **Ecovacs GOAT Support***.

There is nothing to configure. The Ecovacs integration is reloaded once during
setup, after which the mower's device and entities appear under it.

### Another unsupported GOAT model

If your log names a device class other than the ones handled out of the box, add
it under the integration's *Configure* option — space or comma separated. It is
registered the same way. Please also open an issue here (and upstream at
[DeebotUniverse/client.py](https://github.com/DeebotUniverse/client.py/issues))
with the class and model name so it can be added by default.

## Supported out of the box

| Device class | Model |
| --- | --- |
| `e4gqia` | GOAT A1600 LiDAR Pro |

## Limitations

Capabilities are taken from a sibling model, so anything the A1600 LiDAR Pro does
differently from the rest of the GOAT line is not covered. Entity availability
and state reporting come straight from the official integration. Zone or area
based mowing is not part of deebot-client's GOAT capability set.

## Troubleshooting

Enable debug logging to see what was registered:

```yaml
logger:
  logs:
    custom_components.ecovacs_goat: debug
    deebot_client: debug
```

Setup fails with a message about deebot-client's registry layout when the library
has changed internally — please open an issue with your deebot-client version
(visible in the Ecovacs integration's diagnostics).
